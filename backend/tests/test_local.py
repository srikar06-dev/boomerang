"""Local mode: signed upload links and path safety. No network needed."""
import time

import pytest

from app import config, local


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LINK_SIGNING_SECRET", "a" * 64)
    monkeypatch.setattr(local, "UPLOAD_DIR", tmp_path)


def parse(url):
    path, query = url.split("?")
    args = dict(pair.split("=") for pair in query.split("&"))
    return path.split("/", 2)[2], int(args["exp"]), args["sig"]


def test_link_round_trip_and_storage():
    key, exp, sig = parse(local.link("PUT", "return/abc123/item.jpg"))
    assert local.link_ok("PUT", key, exp, sig)
    local.save(key, b"jpeg-bytes")
    assert local.load(key) == b"jpeg-bytes"
    assert local.load("return/abc123/serial.jpg") is None


def test_link_is_bound_to_method_key_and_time():
    key, exp, sig = parse(local.link("PUT", "return/abc123/item.jpg"))
    assert not local.link_ok("GET", key, exp, sig)                          # upload link cannot read
    assert not local.link_ok("PUT", "return/other/item.jpg", exp, sig)      # nor write elsewhere
    assert not local.link_ok("PUT", key, exp + 999, sig)                    # nor be extended
    assert not local.link_ok("PUT", key, int(time.time()) - 1, local._sig("PUT", key, int(time.time()) - 1))


@pytest.mark.parametrize("bad", ["../../etc/passwd", "return/../../x/item.jpg", "return/a/b/item.jpg",
                                 "other/abc/item.jpg", "return/abc/item.png", "/abs/item.jpg", ""])
def test_unsafe_keys_are_refused(bad):
    exp = int(time.time()) + 60
    assert not local.link_ok("PUT", bad, exp, local._sig("PUT", bad, exp))
    with pytest.raises(ValueError):
        local.save(bad, b"x")
