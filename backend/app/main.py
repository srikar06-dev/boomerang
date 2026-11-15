"""Boomerang API entry point.

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path as FilePath

import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog, config, local, security, seed, storage
from .db import db
from .models import (SLOTS, Decision, Fingerprint, NewItemRequest, ShipoutCheckRequest, unit_id_of, ReturnChecks, ReturnRecord, ReturnRequest, ReturnResponse,
                     ReviewRequest, SessionRequest, SessionResponse, ShipoutRequest, UploadUrlRequest, UploadUrlResponse)
from .stages import authenticity, disposition, estimate, impact, serial, vision, visual_match
from .stages.policy import LED, decide
from .stages.risk import Signals, score, unit_confidence
from .stages.sanitize import BadImage, sanitize

app = FastAPI(title="Boomerang", version="0.3.0")
log = logging.getLogger("boomerang")

# Browsers on other sites may call this API only if their exact origin is listed in ALLOWED_ORIGINS.
if config.ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-Station-Key"])

# The web pages (capture, review, dashboard) are served from /app on the same address as the API.
FRONTEND_DIR = FilePath(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="app")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/capture.html")

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
        "local_mode": config.LOCAL_MODE,     # True = no cloud, SIMULATED model
        "demo_mode": config.DEMO_MODE,       # True = demo key is literally "demo"
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
    return SessionResponse(token=token, code=code, expires_at=expires_at, code_required=config.REQUIRE_CODE)


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
@app.post("/shipout/check", dependencies=[Depends(require_station)])
def shipout_check(req: ShipoutCheckRequest):
    """Staff, BEFORE saving a ship-out: is the item in the photo the product on this order?

    Catches a wrong pick before it reaches the customer (who would otherwise return it as "wrong
    item"), suggests the serial read from photo 2, and notes damage already present at ship-out.
    Evidence only: the station shows a warning and staff decide. Does not use up the session.
    """
    session = _open_session(req.token, "shipout")
    _, clean = _load_photos(session)
    order = db().orders.find_one({"order_id": session["order_id"]}) or {}
    product = db().products.find_one({"sku": order.get("sku")}) or {}
    name = product.get("name") or order.get("sku") or "unknown product"
    result, model_used = vision.grade(clean[0].jpeg, clean[1].jpeg, {"product": name}, session["code"])
    if result is None:
        check = {"product_match": None, "product_name": name, "serial_suggestion": None, "label_codes": [],
                 "seal_intact": None, "defects": [], "notes": "Pick check unavailable (model did not answer).",
                 "model_used": model_used}
    else:
        check = {"product_match": bool(result.same_item and result.confidence >= 0.6),
                 "product_name": name,
                 "serial_suggestion": _norm_serial(result.serial_read),
                 "label_codes": result.label_codes,
                 "seal_intact": result.seal_intact,
                 "defects": result.new_damage,      # nothing recorded yet, so all damage seen is "already there"
                 "notes": result.notes,
                 "model_used": model_used}
    db().sessions.update_one({"session_id": session["session_id"]}, {"$set": {"pick_check": check}})
    # The product's return profile, so the station only asks what applies (no serial prompt for "none").
    return {**check, "unit_id": unit_id_of(product), "sealed_consumable": bool(product.get("sealed_consumable"))}


@app.post("/shipout", dependencies=[Depends(require_station)])
def shipout(req: ShipoutRequest):
    session = _open_session(req.token, "shipout")
    keys, clean = _load_photos(session)
    check = session.get("pick_check") or {}
    match = check.get("product_match")
    if match is False and not req.ship_anyway:     # refuse BEFORE claiming, so staff can retry
        raise HTTPException(status_code=409, detail="Pick check says this is not the ordered product")
    _claim(session)
    notes = check.get("notes") or ""
    if match is False:
        notes = f"SHIPPED ANYWAY after a pick-check warning: {notes}"
    fingerprint = Fingerprint(
        weight_g=req.weight_g,
        photo_keys=keys,
        sha256=[c.sha256 for c in clean],
        phash=[c.phash for c in clean],
        serial=_norm_serial(req.serial),
        defects=list(check.get("defects") or [])[:10],
        pick_verified=match,
        pick_notes=notes[:300],
        seal_intact=check.get("seal_intact"),
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


_STOPWORDS = {"the", "and", "with", "for", "inch", "new", "item", "pro", "max", "mini"}


def _words(text: str | None) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOPWORDS}


def _describes_product(seen: str | None, product_name: str | None) -> bool:
    """Does the model's own description of photo 1 share a word with the product name?

    A cheap cross-check of the model against itself. Nothing to compare (no description, or a
    name with no usable words) counts as yes, so it can only ever add caution, never remove it.
    """
    a, b = _words(seen), _words(product_name)
    return not a or not b or bool(a & b)


def _safe_result(future):
    """Result of an optional check, or None if it raised: optional checks never break a return."""
    try:
        return future.result()
    except Exception:
        log.exception("optional object check failed")
        return None


def _ship_item_photo(fp: dict) -> bytes | None:
    """The ship-out photo of the item, so the model compares pictures instead of guessing from a name."""
    keys = fp.get("photo_keys") or []
    if not keys:
        return None
    try:
        return sanitize(storage.get_bytes(keys[0])).jpeg
    except Exception:          # missing or unreadable: grade without the reference photo
        return None


def _visual_check(fp: dict, clean: list):
    """Compares this return's photos with the ship-out photos. Any problem -> None (no effect)."""
    keys = fp.get("photo_keys") or []
    if len(keys) < 2:
        return None
    try:
        ship = [sanitize(storage.get_bytes(k)) for k in keys[:2]]
        return visual_match.compare(ship[0].jpeg, ship[1].jpeg, clean[0].jpeg, clean[1].jpeg)
    except Exception:          # missing photo, bad image, OpenCV error: the cross-check is optional
        return None


@app.post("/return", response_model=ReturnResponse)
def submit_return(req: ReturnRequest, x_station_key: str | None = Header(default=None)):
    """Contract with the station: an internal error comes back as REVIEW / L:Y, never a bare 500.

    Deliberate client errors (bad token 401, missing photo 400, already submitted 409) still raise.
    """
    try:
        return _submit_return(req, x_station_key)
    except HTTPException:
        raise
    except Exception:
        log.exception("/return failed; answering REVIEW")
        return ReturnResponse(return_id="", decision="REVIEW", led=LED["REVIEW"], risk_score=0.0,
                              reasons=["INTERNAL_ERROR"],
                              disposition={"action": "HOLD_FOR_REVIEW", "ship_back": False, "net_recovery_usd": 0.0})


def _submit_return(req: ReturnRequest, x_station_key: str | None):
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
    evidence = {"product": product.get("name") or order.get("sku"), "weight_g": fp.get("weight_g"),
                "serial": fp.get("serial"), "defects": fp.get("defects") or [], "grade": fp.get("grade")}
    ship_item = _ship_item_photo(fp)
    extra_usage: dict = {}
    # The main check and the two unbiased object checks run in parallel (about 1 s extra, not 3).
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_grade = pool.submit(vision.grade, clean[0].jpeg, clean[1].jpeg, evidence, session["code"],
                              ship_item_jpg=ship_item)
        f_blind = pool.submit(vision.describe_object, clean[0].jpeg, extra_usage)
        f_pair = pool.submit(vision.compare_objects, ship_item, clean[0].jpeg, extra_usage) if ship_item else None
        result, model_used = f_grade.result()
        blind = _safe_result(f_blind)
        pair = _safe_result(f_pair) if f_pair else None
    usage = dict(vision.last_usage) if result is not None else {}
    for k in ("input_tokens", "output_tokens"):
        usage[k] = usage.get(k, 0) + extra_usage.get(k, 0)
    if extra_usage.get("cost_usd") is not None:
        usage["cost_usd"] = round((usage.get("cost_usd") or 0.0) + extra_usage["cost_usd"], 6)
    product_name = product.get("name") or order.get("sku")
    blind_says_different = bool(blind) and not _describes_product(blind, product_name)
    pair_says_different = bool(pair) and pair["same_kind"] is False

    # Local OpenCV cross-check against the ship-out photos. Evidence only; None if unavailable.
    visual = _visual_check(fp, clean)

    price = float(product.get("price_usd") or 0.0)
    ship_weight = fp.get("weight_g")
    serial_near = False
    if result is None:
        return_weight = req.weight_g
        # No model evidence: neutral unit/serial values. The policy sends model_ok=False to REVIEW.
        signals = Signals(shipout_weight_g=ship_weight, return_weight_g=return_weight,
                          same_unit_confidence=1.0, serial_match=None, serial_expected=False, price_usd=price)
    else:
        # Prefer the scale as read from the photo; the typed number is only a backup.
        return_weight = result.scale_reading_g if result.scale_reading_g is not None else req.weight_g
        serial_expected = bool(product.get("has_serial", True) and fp.get("serial"))
        # Tolerant compare: look-alike characters, one misread, and every code on the label count.
        reads = [result.serial_read, *result.label_codes]
        serial_match = serial.matches(fp.get("serial"), reads) if serial_expected else None
        if serial_match is False and serial.near_miss(fp.get("serial"), reads):
            serial_match, serial_near = None, True      # likely a misread: "can't tell", capped at YELLOW
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

    # Return profile: only a serial on the device itself proves it is the same unit. A box label
    # (FNSKU) only proves it is the same listing; an opened sealed product can never be resold.
    unit_provable = unit_id_of(product) == "device" and bool(fp.get("serial"))
    seal_broken = bool(product.get("sealed_consumable") and result is not None and result.seal_intact is not True)

    risk = score(signals)
    decision, reasons = decide(
        risk,
        model_ok=result is not None,
        model_confidence=result.confidence if result else 0.0,
        # The code check only counts when REQUIRE_CODE=1; otherwise live capture alone is enough.
        code_visible=(not config.REQUIRE_CODE) or bool(result and result.code_visible),
        image_reused=image_reused,
        price_usd=price,
        visual_disagrees=bool(result and visual and visual.looks_different
                              and result.same_item and result.same_unit),
        unit_provable=unit_provable,
        seal_broken=seal_broken,
        different_item=bool(result and not result.same_item and result.confidence >= 0.6)
                       or (blind_says_different and pair_says_different),
        description_mismatch=bool(result and result.same_item
                                  and not _describes_product(result.item_seen, product.get("name"))),
        looks_different=blind_says_different or pair_says_different,
    )
    if serial_near:
        reasons = ["SERIAL_NEAR_MATCH" if x == "SERIAL_UNREADABLE" else x for x in reasons]
    plan = disposition.choose(result.grade if result else None,
                              product.get("resale_value_by_grade") or {}, decision,
                              opened_consumable=seal_broken)

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
        model_usage=usage,
        object_check={"blind": blind, "pair": pair},
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
            visual_match=visual.score if visual else None,
            visual_inliers=[visual.item_inliers, visual.serial_inliers] if visual else [],
            seal_intact=result.seal_intact if result else None,
        ),
        risk_score=risk.score,
        decision=decision,
        reasons=reasons,
        disposition=plan["action"],
        ship_back=plan["ship_back"],
        net_recovery_usd=plan["net_recovery_usd"],
        sku=order.get("sku"),
        price_usd=price,
        label=req.label if security.station_key_ok(x_station_key) else None,
    )
    db().returns.insert_one(record.model_dump())
    return ReturnResponse(return_id=record.return_id, decision=decision, led=LED[decision],
                          risk_score=risk.score, reasons=reasons, disposition=plan)


# --------------------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------------------
@app.post("/orders", dependencies=[Depends(require_station)])
def new_order(req: NewItemRequest):
    """Staff only: create a product + order for a new demo item, so it can be shipped out right away."""
    order_id = catalog.add_item(db(), req.name, req.price_usd, req.weight_g, req.has_serial,
                                orders=1, customer_id=req.customer_id, unit_id=req.unit_id,
                                sealed_consumable=req.sealed_consumable)[0]
    product = db().orders.find_one({"order_id": order_id}) or {}
    product = db().products.find_one({"sku": product.get("sku")}) or {}
    return {"order_id": order_id, "name": req.name, "price_usd": req.price_usd,
            "has_serial": product.get("has_serial", req.has_serial), "unit_id": unit_id_of(product),
            "sealed_consumable": bool(product.get("sealed_consumable"))}


@app.post("/seed", dependencies=[Depends(require_station)])
def reseed():
    """Wipes and reloads the demo data. Needs the station key AND DEMO_MODE=1 in .env on this machine."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Seeding is disabled (set DEMO_MODE=1 in .env)")
    return {"seeded": seed.run(db())}



# --------------------------------------------------------------------------------------
# Staff views: review queue, evidence pack, dashboard numbers
# --------------------------------------------------------------------------------------
RETURN_ID = Path(pattern=r"^[0-9a-f]{32}$")
FLAGGED = ("RED", "REVIEW")


def _public(doc: dict) -> dict:
    doc.pop("_id", None)          # MongoDB's internal id is not JSON-friendly and not needed
    return doc


def _get_return(return_id: str) -> dict:
    doc = db().returns.find_one({"return_id": return_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Unknown return")
    return _public(doc)


@app.get("/returns", dependencies=[Depends(require_station)])
def list_returns(decision: Decision | None = None, limit: int = Query(default=50, ge=1, le=200)):
    """Newest first. Filter with ?decision=RED (or GREEN / YELLOW / REVIEW) for the reviewer queue."""
    query = {"decision": decision} if decision else {}
    docs = sorted((_public(d) for d in db().returns.find(query)), key=lambda d: d["created_at"], reverse=True)
    keep = ("return_id", "order_id", "sku", "created_at", "decision", "risk_score", "reasons",
            "disposition", "price_usd", "review", "label")
    return {"returns": [{k: d.get(k) for k in keep} for d in docs[:limit]]}


def _utc(t):
    """Mongo hands back naive UTC datetimes; make every timestamp timezone-aware before comparing."""
    if t is None:
        return None
    if isinstance(t, str):
        # A "+" in an unencoded query string arrives as a space; accept both, and "Z" for UTC.
        t = datetime.fromisoformat(t.strip().replace(" ", "+").replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


@app.get("/station/events", dependencies=[Depends(require_station)])
def station_events(after: str | None = Query(default=None, max_length=40)):
    """For a display-only station (UNO Q): what happened since `after`?

    Call with no `after` first: you get a cursor and no events (old history is not replayed).
    Then pass the returned cursor each time. Events are oldest first, so lights show in order.
    """
    now = datetime.now(timezone.utc)
    def iso(t):                                   # "...Z": no "+" to escape in a URL
        return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    if not after:
        return {"cursor": iso(now), "events": []}
    try:
        since = _utc(after)
    except ValueError:
        raise HTTPException(status_code=422, detail="after must be an ISO timestamp")
    events = []
    for r in db().returns.find({}):
        t = _utc(r.get("created_at"))
        if t and t > since:
            events.append({"type": "return", "at": t, "order_id": r["order_id"], "decision": r.get("decision"),
                           "led": LED.get(r.get("decision"), "L:Y"), "disposition": r.get("disposition"),
                           "reasons": (r.get("reasons") or [])[:3]})
    for o in db().orders.find({}):
        t = _utc(o.get("shipped_at"))
        if t and t > since:
            pick = (o.get("fingerprint") or {}).get("pick_verified")
            events.append({"type": "shipout", "at": t, "order_id": o["order_id"], "pick_verified": pick,
                           "led": "L:Y" if pick is False else "L:G"})
    events.sort(key=lambda e: e["at"])
    cursor = events[-1]["at"] if events else since
    return {"cursor": iso(cursor), "events": [{**e, "at": iso(e["at"])} for e in events[:20]]}


PACKAGE_STATUS = Literal["all", "not_shipped", "shipped", "returned", "held"]


@app.get("/packages", dependencies=[Depends(require_station)])
def list_packages(q: str = Query(default="", max_length=80), status: PACKAGE_STATUS = "all",
                  limit: int = Query(default=300, ge=1, le=1000)):
    """Every package in one place: the order, its ship-out fingerprint and its latest return.

    Search with ?q= (order ID, product, SKU, serial or customer). Filter with ?status=.
    """
    products = {p["sku"]: p for p in db().products.find({})}
    latest, counts = {}, {}
    for r in db().returns.find({}):
        oid = r["order_id"]
        counts[oid] = counts.get(oid, 0) + 1
        if oid not in latest or r["created_at"] > latest[oid]["created_at"]:
            latest[oid] = r
    needle = q.strip().lower()
    rows = []
    for o in db().orders.find({}):
        product = products.get(o.get("sku")) or {}
        fp = o.get("fingerprint") or {}
        r = latest.get(o["order_id"])
        review = (r or {}).get("review") or {}
        held = bool(r) and r.get("decision") in FLAGGED and review.get("action") != "approve"
        state = "returned" if r else ("shipped" if o.get("shipped_at") else "not_shipped")
        row = {
            "order_id": o["order_id"], "sku": o.get("sku"), "product": product.get("name") or o.get("sku"),
            "price_usd": product.get("price_usd"), "customer_id": o.get("customer_id"),
            "unit_id": unit_id_of(product) if product else None,
            "sealed_consumable": bool(product.get("sealed_consumable")),
            "state": state, "held": held,
            "shipped_at": o.get("shipped_at"),
            "shipout": {"weight_g": fp.get("weight_g"), "serial": fp.get("serial"),
                        "photos": len(fp.get("photo_keys") or []), "pick_verified": fp.get("pick_verified"),
                        "pick_notes": fp.get("pick_notes") or "", "seal_intact": fp.get("seal_intact"),
                        "defects": fp.get("defects") or []} if fp else None,
            "returns": counts.get(o["order_id"], 0),
            "return": {"return_id": r["return_id"], "created_at": r["created_at"], "decision": r.get("decision"),
                       "disposition": r.get("disposition"), "weight_g": r.get("return_weight_g"),
                       "reasons": r.get("reasons") or [], "review": review.get("action"),
                       "reviewer": review.get("reviewer")} if r else None,
        }
        if needle:
            hay = " ".join(str(x or "") for x in (row["order_id"], row["product"], row["sku"], row["customer_id"],
                                                  fp.get("serial"))).lower()
            if needle not in hay:
                continue
        if status == "held" and not held:
            continue
        if status not in ("all", "held") and state != status:
            continue
        rows.append(row)

    def last_activity(row):
        t = (row["return"] or {}).get("created_at") or row["shipped_at"]
        return t.timestamp() if t else 0

    rows.sort(key=lambda r: (last_activity(r), r["order_id"]), reverse=True)
    summary = {k: sum(1 for r in rows if r["state"] == k) for k in ("not_shipped", "shipped", "returned")}
    summary["held"] = sum(1 for r in rows if r["held"])
    return {"total": len(rows), "summary": summary, "packages": rows[:limit]}


@app.post("/review/{return_id}", dependencies=[Depends(require_station)])
def review(req: ReviewRequest, return_id: str = RETURN_ID):
    """A person confirms or releases a held return. The automatic decision is kept for the audit trail."""
    _get_return(return_id)
    verdict = {"action": req.action, "reviewer": req.reviewer, "note": req.note,
               "at": datetime.now(timezone.utc)}
    db().returns.update_one({"return_id": return_id}, {"$set": {"review": verdict}})
    return _get_return(return_id)


@app.get("/evidence/{return_id}", dependencies=[Depends(require_station)])
def evidence(return_id: str = RETURN_ID):
    """Everything behind one decision: the record, the ship-out fingerprint, and 5-minute photo links."""
    record = _get_return(return_id)
    order = _public(db().orders.find_one({"order_id": record["order_id"]}) or {})
    fingerprint = order.get("fingerprint") or {}
    return {
        "return": record,
        "order": {"order_id": order.get("order_id"), "sku": order.get("sku"),
                  "customer_id": order.get("customer_id"), "shipped_at": order.get("shipped_at")},
        "shipout_fingerprint": fingerprint,
        "photos": {
            "return": [storage.presign_get(k) for k in record.get("photo_keys") or []],
            "shipout": [storage.presign_get(k) for k in fingerprint.get("photo_keys") or []],
        },
    }


def _usage_summary(docs: list[dict]) -> dict:
    """Average model cost and median model time per return, for the metrics table."""
    used = [d.get("model_usage") or {} for d in docs if d.get("model_usage")]
    costs = [u["cost_usd"] for u in used if u.get("cost_usd") is not None]
    secs = sorted(u["seconds"] for u in used if u.get("seconds") is not None)
    return {
        "calls": len(used),
        "avg_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "median_seconds": secs[len(secs) // 2] if secs else None,
    }


def _wrong_picks_stopped() -> list[float | None]:
    """Ship-outs the pick check flagged and staff did NOT ship (session never submitted).

    Returns the expected weight of each, one entry per order, for the CO2 estimate.
    """
    orders = {}
    for sess in db().sessions.find({"purpose": "shipout"}):
        if (sess.get("pick_check") or {}).get("product_match") is False and not sess.get("used"):
            orders[sess["order_id"]] = None
    for oid in orders:
        order = db().orders.find_one({"order_id": oid}) or {}
        if ((order.get("fingerprint") or {}).get("pick_verified")) is False:
            orders[oid] = "shipped-anyway"         # a later override shipped the wrong item after all
            continue
        product = db().products.find_one({"sku": order.get("sku")}) or {}
        orders[oid] = product.get("expected_weight_g")
    return [w for w in orders.values() if w != "shipped-anyway"]


@app.get("/industry")
def industry():
    """Public context for the dashboard: US return fraud by year, with sources. Holds no station data,
    so it needs no key and renders before anyone signs in."""
    return estimate.industry()


@app.get("/stats", dependencies=[Depends(require_station)])
def stats():
    """Dashboard numbers. Dollar figures use the seed prices and the disposition cost assumptions."""
    docs = list(db().returns.find({}))
    by_decision = {d: 0 for d in ("GREEN", "YELLOW", "RED", "REVIEW")}
    for d in docs:
        by_decision[d["decision"]] = by_decision.get(d["decision"], 0) + 1

    def released(d):   # a reviewer approved it, so the money is no longer held
        return (d.get("review") or {}).get("action") == "approve"

    held = [d for d in docs if d["decision"] in FLAGGED and not released(d)]
    not_shipped = [d for d in docs if d["decision"] not in FLAGGED and not d.get("ship_back")]
    fraud = [d for d in docs if d.get("label") == "fraud"]
    honest = [d for d in docs if d.get("label") == "honest"]
    test_set = {
        "fraud_total": len(fraud),
        "fraud_caught": sum(d["decision"] != "GREEN" for d in fraud),
        "fraud_instant_refunds": sum(d["decision"] == "GREEN" for d in fraud),
        "honest_total": len(honest),
        "honest_flagged": sum(d["decision"] in FLAGGED for d in honest),
        "honest_green": sum(d["decision"] == "GREEN" for d in honest),
    }
    return {
        "total": len(docs),
        "by_decision": by_decision,
        "money_held_usd": round(sum(d.get("price_usd") or 0 for d in held), 2),
        "instant_refunds_usd": round(sum(d.get("price_usd") or 0 for d in docs if d["decision"] == "GREEN"), 2),
        "net_recovery_usd": round(sum(d.get("net_recovery_usd") or 0 for d in docs), 2),
        "shipping_avoided_usd": round(len(not_shipped) * disposition.SHIP_BACK_USD, 2),
        "awaiting_review": sum(1 for d in held if not d.get("review")),
        "model": _usage_summary(docs),
        "impact": impact.summarise(docs, _wrong_picks_stopped(), FLAGGED),
        "test_set": test_set,
        "us_estimate": estimate.us_estimate(test_set),
    }


# --------------------------------------------------------------------------------------
# Local mode only: stand-ins for S3's presigned PUT and GET (see app/local.py)
# --------------------------------------------------------------------------------------
if config.LOCAL_MODE:
    logging.getLogger("uvicorn.error").warning(
        "LOCAL_MODE=1: in-memory database, photos on disk, SIMULATED vision model. Not for real decisions.")

    @app.put("/local-upload/{key:path}", include_in_schema=False)
    async def local_upload(key: str, exp: int, sig: str, request: Request):
        if not local.link_ok("PUT", key, exp, sig):
            raise HTTPException(status_code=403, detail="Bad or expired upload link")
        if int(request.headers.get("content-length") or 0) > storage.MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Photo is too large")
        data = await request.body()
        if len(data) > storage.MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Photo is too large")
        local.save(key, data)
        return Response(status_code=200)

    @app.get("/local-file/{key:path}", include_in_schema=False)
    def local_file(key: str, exp: int, sig: str):
        if not local.link_ok("GET", key, exp, sig):
            raise HTTPException(status_code=403, detail="Bad or expired link")
        data = local.load(key)
        if data is None:
            raise HTTPException(status_code=404, detail="No such photo")
        return Response(content=data, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})
