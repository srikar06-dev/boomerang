"""MongoDB Atlas connection (lazy, so the app starts even before .env is filled)."""
from pymongo import MongoClient

from . import config

_db = None


def db():
    global _db
    if _db is None and config.LOCAL_MODE:
        from . import local, seed
        _db = local.MemoryDB()
        seed.run(_db)                      # start with the demo products, orders and customers
    if _db is None:
        if not config.MONGODB_URI:
            raise RuntimeError("MONGODB_URI is empty - fill in .env")
        _db = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)[config.MONGODB_DB]
    return _db
