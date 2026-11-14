"""LOCAL_MODE=1: run the whole loop on one laptop with no cloud at all.

- database: in memory, seeded with the demo data (lost when the server stops)
- photos:   saved under captures/local/ in the repo (git ignores captures/)
- vision:   SIMULATED - it always answers "same unit, undamaged" and reads no scale,
            so the typed weight drives the decision. Never present this as the real model.

For building pages and the station script before AWS/MongoDB are ready, and as a
last-resort demo fallback if the venue Wi-Fi fails.
"""
import copy
import hashlib
import hmac
import re
import time
from pathlib import Path

from . import config

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "captures" / "local"
KEY_PATTERN = re.compile(r"^(return|shipout)/[A-Za-z0-9_-]{1,64}/(item|serial)\.jpg$")   # blocks ../ tricks
LINK_TTL_S = 300


# ---------------------------------------------------------------- in-memory database
class MemoryCollection:
    """The handful of MongoDB collection methods Boomerang uses, on a plain list."""
    def __init__(self, docs=()):
        self.docs = [dict(d) for d in docs]

    def _match(self, doc, query):
        return all(doc.get(k) == v for k, v in (query or {}).items())

    def find_one(self, query=None, projection=None):
        return next((copy.deepcopy(d) for d in self.docs if self._match(d, query)), None)

    def find(self, query=None, projection=None):
        return [copy.deepcopy(d) for d in self.docs if self._match(d, query)]

    def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    def insert_many(self, docs):
        for d in docs:
            self.insert_one(d)

    def delete_many(self, query):
        self.docs = [d for d in self.docs if not self._match(d, query)]

    def update_one(self, query, update):
        for d in self.docs:
            if self._match(d, query):
                d.update(copy.deepcopy(update["$set"]))
                return

    def find_one_and_update(self, query, update):
        for d in self.docs:
            if self._match(d, query):
                before = copy.deepcopy(d)
                d.update(copy.deepcopy(update["$set"]))
                return before
        return None

    def create_index(self, *args, **kwargs):
        pass


class MemoryDB(dict):
    def __missing__(self, name):
        self[name] = MemoryCollection()
        return self[name]

    __getattr__ = dict.__getitem__


# ---------------------------------------------------------------- local photo storage
def _sig(method: str, key: str, exp: int) -> str:
    msg = f"{method}:{key}:{exp}".encode()
    return hmac.new(config.LINK_SIGNING_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def link(method: str, key: str) -> str:
    """A signed, 5-minute, same-site URL that stands in for an S3 presigned URL."""
    exp = int(time.time()) + LINK_TTL_S
    route = "local-upload" if method == "PUT" else "local-file"
    return f"/{route}/{key}?exp={exp}&sig={_sig(method, key, exp)}"


def link_ok(method: str, key: str, exp: int, sig: str) -> bool:
    return (bool(KEY_PATTERN.match(key)) and exp > time.time()
            and hmac.compare_digest(sig, _sig(method, key, exp)))


def path_for(key: str) -> Path:
    if not KEY_PATTERN.match(key):
        raise ValueError("bad key")
    return UPLOAD_DIR / key


def save(key: str, data: bytes) -> None:
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def load(key: str) -> bytes | None:
    target = path_for(key)
    return target.read_bytes() if target.is_file() else None
