"""Signed return-session tokens (HMAC-SHA256). No outside services, so it is easy to test.

A token proves "the server issued this session for this order, and it has not expired".
One-time use is enforced separately, in the database, when the return is submitted.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from . import config

SESSION_TTL_S = 600  # 10 minutes
_DEFAULT_SECRET = "dev-only-change-me"


class TokenError(Exception):
    """Token is malformed, tampered with, or expired. Never tell the caller which one."""


def _key() -> bytes:
    secret = config.LINK_SIGNING_SECRET
    if not secret or secret == _DEFAULT_SECRET:
        # Refuse to sign with the placeholder: anyone could forge tokens.
        raise RuntimeError("LINK_SIGNING_SECRET is not set - run ./install.sh or fill in .env")
    return secret.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())


def new_session_id() -> str:
    return secrets.token_urlsafe(16)


def new_code() -> str:
    """4-digit code the shopper must show in the photo (proves the photo is fresh)."""
    return f"{secrets.randbelow(10_000):04d}"


def issue_token(session_id: str, order_id: str, now: float | None = None) -> tuple[str, int]:
    """Returns (token, expires_at as a Unix timestamp)."""
    exp = int((now if now is not None else time.time()) + SESSION_TTL_S)
    body = _b64(json.dumps({"sid": session_id, "oid": order_id, "exp": exp}, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}", exp


def verify_token(token: str, now: float | None = None) -> dict:
    """Returns {"sid", "oid", "exp"} or raises TokenError."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(body)):  # constant-time compare
            raise TokenError("invalid")
        claims = json.loads(_unb64(body))
        if not isinstance(claims, dict) or not {"sid", "oid", "exp"} <= claims.keys():
            raise TokenError("invalid")
    except TokenError:
        raise
    except Exception:
        raise TokenError("invalid") from None
    if (now if now is not None else time.time()) >= claims["exp"]:
        raise TokenError("invalid")
    return claims
