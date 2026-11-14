"""Tests for signed session tokens. No network needed."""
import pytest

from app import config, security


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(config, "LINK_SIGNING_SECRET", "a" * 64)


def test_round_trip():
    token, exp = security.issue_token("sid1", "ORD-1", now=1000)
    claims = security.verify_token(token, now=1001)
    assert claims == {"sid": "sid1", "oid": "ORD-1", "p": "return", "exp": exp}
    assert exp == 1000 + security.SESSION_TTL_S


def test_expired_token_rejected():
    token, exp = security.issue_token("sid1", "ORD-1", now=1000)
    with pytest.raises(security.TokenError):
        security.verify_token(token, now=exp)


def test_tampered_token_rejected():
    token, _ = security.issue_token("sid1", "ORD-1", now=1000)
    other, _ = security.issue_token("sid1", "ORD-2", now=1000)
    forged = other.split(".")[0] + "." + token.split(".")[1]   # ORD-2 body, ORD-1 signature
    with pytest.raises(security.TokenError):
        security.verify_token(forged, now=1001)


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c", "!!!.???", "e30.e30"])
def test_garbage_rejected(bad):
    with pytest.raises(security.TokenError):
        security.verify_token(bad, now=1001)


def test_token_from_another_secret_rejected(monkeypatch):
    token, _ = security.issue_token("sid1", "ORD-1", now=1000)
    monkeypatch.setattr(config, "LINK_SIGNING_SECRET", "b" * 64)
    with pytest.raises(security.TokenError):
        security.verify_token(token, now=1001)


def test_placeholder_secret_refused(monkeypatch):
    monkeypatch.setattr(config, "LINK_SIGNING_SECRET", "dev-only-change-me")
    with pytest.raises(RuntimeError):
        security.issue_token("sid1", "ORD-1")


def test_code_is_four_digits():
    for _ in range(50):
        code = security.new_code()
        assert len(code) == 4 and code.isdigit()


def test_station_key(monkeypatch):
    monkeypatch.setattr(config, "STATION_KEY", "k" * 48)
    assert security.station_key_ok("k" * 48)
    assert not security.station_key_ok("wrong")
    assert not security.station_key_ok(None)


def test_station_key_fails_closed_when_unset(monkeypatch):
    monkeypatch.setattr(config, "STATION_KEY", None)
    assert not security.station_key_ok("")
    assert not security.station_key_ok("anything")
