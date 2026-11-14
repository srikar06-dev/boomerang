"""Boomerang API entry point.

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""
from fastapi import FastAPI
from pydantic import BaseModel

from . import config
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

# TODO (WP3): /session, /upload-url, /shipout, /return, /review/{id}, /returns, /stats, /evidence/{id}, /seed
