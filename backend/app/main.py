"""Boomerang API entry point.

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import config, security, seed
from .db import db
from .models import SessionRequest, SessionResponse
from .stages.policy import LED, decide
from .stages.risk import Signals, score

app = FastAPI(title="Boomerang", version="0.1.0")


@app.get("/health")
def health():
    """Quick check that the server is up and which settings are filled in (never shows secrets)."""
    return {
        "status": "ok",
        "region": config.AWS_REGION,
        "model": config.BEDROCK_MODEL_ID,
        "s3_bucket_set": bool(config.S3_BUCKET),
        "mongodb_set": bool(config.MONGODB_URI),
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



@app.post("/session", response_model=SessionResponse)
def create_session(req: SessionRequest):
    """Starts a return for one order: a signed token (10 min) and the 4-digit code to show in the photo."""
    if db().orders.find_one({"order_id": req.order_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="Unknown order")
    session_id = security.new_session_id()
    code = security.new_code()
    token, expires_at = security.issue_token(session_id, req.order_id)
    db().sessions.insert_one({
        "session_id": session_id,
        "order_id": req.order_id,
        "code": code,
        "expires_at": expires_at,
        "used": False,               # /return flips this once, so a token cannot be replayed
        "created_at": datetime.now(timezone.utc),
    })
    return SessionResponse(token=token, code=code, expires_at=expires_at)

@app.post("/seed")
def reseed():
    """Wipes and reloads the demo data. Only works when DEMO_MODE=1 is set in .env on this machine."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Seeding is disabled (set DEMO_MODE=1 in .env)")
    return {"seeded": seed.run(db())}

# TODO (WP3): /upload-url, /shipout, /return, /review/{id}, /returns, /stats, /evidence/{id}
