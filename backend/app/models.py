"""Shapes of the documents we store in MongoDB and of the API requests/responses.

Collections: products, orders, returns, customers, sessions.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Grade = Literal["A", "B", "C", "D"]
Decision = Literal["GREEN", "YELLOW", "RED", "REVIEW"]
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"  # ids come from clients: keep them to safe characters


# ---------- stored documents ----------
class Product(BaseModel):
    sku: str
    name: str
    price_usd: float = Field(ge=0)
    expected_weight_g: float | None = Field(default=None, ge=0)
    has_serial: bool = True
    listing_photo_url: str | None = None
    resale_value_by_grade: dict[str, float] = {}  # {"A": 40, "B": 28, "C": 12}


class Fingerprint(BaseModel):
    """What we recorded about this exact unit when it shipped out."""
    weight_g: float | None = Field(default=None, ge=0)
    photo_keys: list[str] = []
    serial: str | None = None
    defects: list[str] = []
    grade: Grade = "A"
    shake_signature: float | None = None
    mag_reading: float | None = None


class Order(BaseModel):
    order_id: str
    sku: str
    customer_id: str
    shipped_at: datetime | None = None
    fingerprint: Fingerprint | None = None


class Customer(BaseModel):
    """Synthetic demo data."""
    customer_id: str
    orders: int = Field(default=1, ge=0)
    flagged_returns: int = Field(default=0, ge=0)


class ReturnChecks(BaseModel):
    weight_delta_pct: float | None = None
    code_visible: bool = False
    phash_reused: bool = False
    same_item: bool | None = None
    same_unit: bool | None = None
    new_damage: list[str] = []
    grade: Grade | None = None


class ReturnRecord(BaseModel):
    order_id: str
    session_id: str
    created_at: datetime
    photo_keys: list[str] = []
    sha256: list[str] = []
    checks: ReturnChecks = ReturnChecks()
    risk_score: float | None = None
    decision: Decision = "REVIEW"
    reasons: list[str] = []
    disposition: str | None = None
    reviewer: str | None = None


# ---------- API ----------
class SessionRequest(BaseModel):
    order_id: str = Field(pattern=ID_PATTERN)


class SessionResponse(BaseModel):
    token: str
    code: str
    expires_at: int  # Unix timestamp (seconds)
