"""Boomerang API entry point.

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
import re
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import config, security, seed, storage
from .db import db
from .models import (SLOTS, Fingerprint, ReturnChecks, ReturnRecord, ReturnRequest, ReturnResponse,
                     SessionRequest, SessionResponse, ShipoutRequest, UploadUrlRequest, UploadUrlResponse)
from .stages import authenticity, disposition, vision
from .stages.policy import LED, decide
from .stages.risk import Signals, score, unit_confidence
from .stages.sanitize import BadImage, sanitize

app = FastAPI(title="Boomerang", version="0.2.0")

BAD_SESSION = HTTPException(status_code=401, detail="Invalid or expired session")


def require_station(x_station_key: str | None = Header(default=None)) -> None:
    """Dependency for staff-only endpoints: send the shared key in the X-Station-Key header."""
    if not security.station_key_ok(x_station_key):
        raise HTTPException(status_code=403, detail="Station key required")


@app.get("/health")
def health():
    """Quick check that the server is up and which settings are filled in (never shows secrets)."""
    return {
        "status": "ok",
        "region": config.AWS_REGION,
        "model": config.BEDROCK_MODEL_ID,
        "s3_bucket_set": bool(config.S3_BUCKET),
        "mongodb_set": bool(config.MONGODB_URI),
        "station_key_set": bool(config.STATION_KEY),
    }


class ScoreRequest(BaseModel):
    """Dry-run of the decision logic without photos or the model (useful for testing the rules)."""
    shipout_weight_g: float | None = None
    return_weight_g: float | None = None
    same_unit_confidence: float = 1.0
    serial_match: bool | None = True
    serial_expected: bool = True
    damage_level: float = 0.0
    flagged_returns: int = 0
    total_orders: int = 1
    price_usd: float = 0.0
    sensor_distance: float | None = None
    model_confidence: float = 0.9
    code_visible: bool = True
    image_reused: bool = False


@app.post("/score")
def score_only(req: ScoreRequest):
    data = req.model_dump()
    model_conf = data.pop("model_confidence")
    code_visible = data.pop("code_visible")
    image_reused = data.pop("image_reused")
    risk = score(Signals(**data))
    decision, reasons = decide(
        risk,
        model_ok=True,
        model_confidence=model_conf,
        code_visible=code_visible,
        image_reused=image_reused,
        price_usd=req.price_usd,
    )
    return {"decision": decision, "led": LED[decision], "risk_score": risk.score,
            "terms": risk.terms, "reasons": reasons}


# --------------------------------------------------------------------------------------
# Sessions and uploads
# --------------------------------------------------------------------------------------
@app.post("/session", response_model=SessionResponse)
def create_session(req: SessionRequest, x_station_key: str | None = Header(default=None)):
    """Starts a return (or, for staff, a ship-out) for one order.

    Returns a signed token (10 min) and the 4-digit code that must be visible in the photo.
    """
    if req.purpose == "shipout" and not security.station_key_ok(x_station_key):
        raise HTTPException(status_code=403, detail="Station key required")
    if db().orders.find_one({"order_id": req.order_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="Unknown order")
    session_id = security.new_session_id()
    code = security.new_code()
    token, expires_at = security.issue_token(session_id, req.order_id, req.purpose)
    db().sessions.insert_one({
        "session_id": session_id,
        "order_id": req.order_id,
        "purpose": req.purpose,
        "code": code,
        "expires_at": expires_at,
        "used": False,               # flipped once on submit, so a token cannot be replayed
        "created_at": datetime.now(timezone.utc),
    })
    return SessionResponse(token=token, code=code, expires_at=expires_at)


def _open_session(token: str, purpose: str) -> dict:
    """Checks the token and returns its live, unused session. Same error for every failure."""
    try:
        claims = security.verify_token(token)
    except security.TokenError:
        raise BAD_SESSION from None
    session = db().sessions.find_one({"session_id": claims["sid"]})
    if (session is None or session.get("used") or session.get("purpose") != purpose
            or claims["p"] != purpose or session.get("order_id") != claims["oid"]):
        raise BAD_SESSION
    return session


def _photo_key(session: dict, slot: str) -> str:
    """Where a session's photo lives in S3. Decided here, so a client can never point us at another object."""
    return f"{session['purpose']}/{session['session_id']}/{slot}.jpg"


@app.post("/upload-url", response_model=UploadUrlResponse)
def upload_url(req: UploadUrlRequest):
    """One presigned S3 PUT URL per photo slot ("item" or "serial"). Works for return and ship-out tokens."""
    try:
        purpose = security.verify_token(req.token)["p"]
    except security.TokenError:
        raise BAD_SESSION from None
    session = _open_session(req.token, purpose)
    key = _photo_key(session, req.slot)
    return UploadUrlResponse(url=storage.presign_put(key), key=key)


def _load_photos(session: dict) -> tuple[list[str], list]:
    """Fetches and sanitizes both photos of a session. Raises 400 with a clear message if one is unusable."""
    keys = [_photo_key(session, slot) for slot in SLOTS]
    clean = []
    for slot, key in zip(SLOTS, keys):
        try:
            clean.append(sanitize(storage.get_bytes(key)))
        except storage.NotFound:
            raise HTTPException(status_code=400, detail=f"Photo '{slot}' has not been uploaded") from None
        except storage.TooLarge:
            raise HTTPException(status_code=400, detail=f"Photo '{slot}' is too large") from None
        except BadImage:
            raise HTTPException(status_code=400, detail=f"Photo '{slot}' is not a valid image") from None
    return keys, clean


def _claim(session: dict) -> None:
    """Marks the session used. Atomic in MongoDB, so two submits of one token cannot both win."""
    won = db().sessions.find_one_and_update(
        {"session_id": session["session_id"], "used": False}, {"$set": {"used": True}})
    if won is None:
        raise HTTPException(status_code=409, detail="This session was already submitted")


# --------------------------------------------------------------------------------------
# Ship-out: record the fingerprint of the exact unit (staff only)
# --------------------------------------------------------------------------------------
@app.post("/shipout", dependencies=[Depends(require_station)])
def shipout(req: ShipoutRequest):
    session = _open_session(req.token, "shipout")
    keys, clean = _load_photos(session)
    _claim(session)
    fingerprint = Fingerprint(
        weight_g=req.weight_g,
        photo_keys=keys,
        sha256=[c.sha256 for c in clean],
        phash=[c.phash for c in clean],
        serial=_norm_serial(req.serial),
    )
    db().orders.update_one(
        {"order_id": session["order_id"]},
        {"$set": {"fingerprint": fingerprint.model_dump(), "shipped_at": datetime.now(timezone.utc)}})
    return {"order_id": session["order_id"], "fingerprint": fingerprint.model_dump()}


# --------------------------------------------------------------------------------------
# Return: check the item against its ship-out fingerprint and decide
# --------------------------------------------------------------------------------------
def _norm_serial(text: str | None) -> str | None:
    """Uppercase letters and digits only, so 'sn-12 34' and 'SN1234' compare equal."""
    cleaned = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    return cleaned or None


def _known_photos(order: dict) -> tuple[set[str], list[str]]:
    """Hashes of every photo we have already seen: this order's ship-out photos and all earlier returns."""
    fp = order.get("fingerprint") or {}
    sha, ph = set(fp.get("sha256") or []), list(fp.get("phash") or [])
    for prior in db().returns.find({}, {"sha256": 1, "phash": 1}):
        sha.update(prior.get("sha256") or [])
        ph.extend(prior.get("phash") or [])
    return sha, ph


@app.post("/return", response_model=ReturnResponse)
def submit_return(req: ReturnRequest):
    session = _open_session(req.token, "return")
    order = db().orders.find_one({"order_id": session["order_id"]})
    if order is None:
        raise BAD_SESSION
    product = db().products.find_one({"sku": order["sku"]}) or {}
    customer = db().customers.find_one({"customer_id": order.get("customer_id")}) or {}
    fp = order.get("fingerprint") or {}

    keys, clean = _load_photos(session)
    known_sha, known_phash = _known_photos(order)     # read BEFORE we store this return
    _claim(session)

    # Authenticity: is either photo one we have seen before?
    image_reused = any(authenticity.is_reused(c.sha256, c.phash, known_sha, known_phash) for c in clean)

    # Vision: evidence only. None means every attempt failed, and the policy sends that to REVIEW.
    evidence = {"weight_g": fp.get("weight_g"), "serial": fp.get("serial"),
                "defects": fp.get("defects") or [], "grade": fp.get("grade")}
    result, model_used = vision.grade(clean[0].jpeg, clean[1].jpeg, evidence, session["code"])

    price = float(product.get("price_usd") or 0.0)
    ship_weight = fp.get("weight_g")
    if result is None:
        return_weight = req.weight_g
        # No model evidence: neutral unit/serial values. The policy sends model_ok=False to REVIEW.
        signals = Signals(shipout_weight_g=ship_weight, return_weight_g=return_weight,
                          same_unit_confidence=1.0, serial_match=None, serial_expected=False, price_usd=price)
    else:
        # Prefer the scale as read from the photo; the typed number is only a backup.
        return_weight = result.scale_reading_g if result.scale_reading_g is not None else req.weight_g
        serial_expected = bool(product.get("has_serial", True) and fp.get("serial"))
        read = _norm_serial(result.serial_read)
        serial_match = None if not (serial_expected and read) else read == _norm_serial(fp.get("serial"))
        damage = 0.0 if not result.new_damage else (1.0 if result.grade == "D" else 0.5)
        signals = Signals(
            shipout_weight_g=ship_weight,
            return_weight_g=return_weight,
            same_unit_confidence=unit_confidence(result.same_item, result.same_unit, result.confidence),
            serial_match=serial_match,
            serial_expected=serial_expected,
            damage_level=damage,
            flagged_returns=int(customer.get("flagged_returns") or 0),
            total_orders=int(customer.get("orders") or 1),
            price_usd=price,
        )

    risk = score(signals)
    decision, reasons = decide(
        risk,
        model_ok=result is not None,
        model_confidence=result.confidence if result else 0.0,
        code_visible=bool(result and result.code_visible),
        image_reused=image_reused,
        price_usd=price,
    )
    plan = disposition.choose(result.grade if result else None,
                              product.get("resale_value_by_grade") or {}, decision)

    delta = None
    if ship_weight and return_weight is not None:
        delta = round(100 * (return_weight - ship_weight) / ship_weight, 1)
    record = ReturnRecord(
        return_id=uuid.uuid4().hex,
        order_id=order["order_id"],
        session_id=session["session_id"],
        created_at=datetime.now(timezone.utc),
        photo_keys=keys,
        sha256=[c.sha256 for c in clean],
        phash=[c.phash for c in clean],
        return_weight_g=return_weight,
        model_used=model_used,
        vision=result.model_dump() if result else None,
        risk_terms=risk.terms,
        checks=ReturnChecks(
            weight_delta_pct=delta,
            code_visible=bool(result and result.code_visible),
            phash_reused=image_reused,
            same_item=result.same_item if result else None,
            same_unit=result.same_unit if result else None,
            new_damage=result.new_damage if result else [],
            grade=result.grade if result else None,
        ),
        risk_score=risk.score,
        decision=decision,
        reasons=reasons,
        disposition=plan["action"],
    )
    db().returns.insert_one(record.model_dump())
    return ReturnResponse(return_id=record.return_id, decision=decision, led=LED[decision],
                          risk_score=risk.score, reasons=reasons, disposition=plan)


# --------------------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------------------
@app.post("/seed", dependencies=[Depends(require_station)])
def reseed():
    """Wipes and reloads the demo data. Needs the station key AND DEMO_MODE=1 in .env on this machine."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Seeding is disabled (set DEMO_MODE=1 in .env)")
    return {"seeded": seed.run(db())}

# TODO (WP5): /review/{id}, /returns, /stats, /evidence/{id}
