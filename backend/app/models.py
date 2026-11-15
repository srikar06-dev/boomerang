"""Shapes of the documents we store in MongoDB and of the API requests/responses.

Collections: products, orders, returns, customers, sessions.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Grade = Literal["A", "B", "C", "D"]
Decision = Literal["GREEN", "YELLOW", "RED", "REVIEW"]
UnitId = Literal["device", "box", "none"]
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
    # Return profile. unit_id says what can prove it is the SAME unit:
    #   device = serial/IMEI printed on the item itself; box = only a packaging label (FNSKU names the
    #   listing, not the unit); none = nothing. None means "work it out from has_serial" (old data).
    unit_id: UnitId | None = None
    sealed_consumable: bool = False   # cream, cosmetics, food: once opened it can never be resold


def unit_id_of(product: dict) -> str:
    """The product's unit_id, falling back to has_serial for products stored before profiles existed."""
    return product.get("unit_id") or ("device" if product.get("has_serial", True) else "none")


class Fingerprint(BaseModel):
    """What we recorded about this exact unit when it shipped out."""
    weight_g: float | None = Field(default=None, ge=0)
    photo_keys: list[str] = []
    sha256: list[str] = []
    phash: list[str] = []
    serial: str | None = None
    defects: list[str] = []
    grade: Grade = "A"
    shake_signature: float | None = None
    mag_reading: float | None = None
    # Ship-out pick check: did the photo show the product on the order? None = not checked.
    pick_verified: bool | None = None
    pick_notes: str = ""
    seal_intact: bool | None = None   # factory seal as seen at ship-out (sealed consumables)


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
    visual_match: float | None = None      # 0..1 from stages/visual_match (local OpenCV)
    visual_inliers: list[int] = []         # [item centre, serial close-up]
    seal_intact: bool | None = None        # sealed consumables only


class ReturnRecord(BaseModel):
    return_id: str
    order_id: str
    session_id: str
    created_at: datetime
    photo_keys: list[str] = []
    sha256: list[str] = []
    phash: list[str] = []
    return_weight_g: float | None = None
    model_used: str = "none"
    model_usage: dict = {}            # tokens, seconds and estimated cost of the model call
    vision: dict | None = None        # the model's raw answer, kept as evidence
    risk_terms: dict = {}
    checks: ReturnChecks = ReturnChecks()
    risk_score: float | None = None
    decision: Decision = "REVIEW"
    reasons: list[str] = []
    disposition: str | None = None
    ship_back: bool = False
    net_recovery_usd: float = 0.0
    sku: str | None = None
    price_usd: float = 0.0
    label: Literal["honest", "fraud"] | None = None   # test-set ground truth, set by staff only
    review: dict | None = None                        # {"action", "reviewer", "note", "at"} once a person decides


# ---------- API ----------
Purpose = Literal["return", "shipout"]
Slot = Literal["item", "serial"]
SLOTS: tuple[str, ...] = ("item", "serial")


class SessionRequest(BaseModel):
    order_id: str = Field(pattern=ID_PATTERN)
    purpose: Purpose = "return"       # "shipout" needs the station key


class SessionResponse(BaseModel):
    token: str
    code: str
    expires_at: int  # Unix timestamp (seconds)
    code_required: bool = False  # show the code to the user only when this is true


class UploadUrlRequest(BaseModel):
    token: str = Field(max_length=600)
    slot: Slot


class UploadUrlResponse(BaseModel):
    url: str
    key: str
    content_type: str = "image/jpeg"  # the PUT must send exactly this Content-Type header


class ShipoutRequest(BaseModel):
    token: str = Field(max_length=600)
    weight_g: float | None = Field(default=None, ge=0, le=100_000)
    serial: str | None = Field(default=None, max_length=64)
    ship_anyway: bool = False   # staff saw the pick-check warning and shipped anyway (recorded)


class ShipoutCheckRequest(BaseModel):
    token: str = Field(max_length=600)


class ReturnRequest(BaseModel):
    token: str = Field(max_length=600)
    weight_g: float | None = Field(default=None, ge=0, le=100_000)   # typed backup if the scale is unreadable
    label: Literal["honest", "fraud"] | None = None   # test set only; ignored without the station key


class ReturnResponse(BaseModel):
    return_id: str
    decision: Decision
    led: str
    risk_score: float
    reasons: list[str]
    disposition: dict


class NewItemRequest(BaseModel):
    """Staff: register one of our own demo items at ship-out time (creates product + one order)."""
    name: str = Field(min_length=1, max_length=60)
    price_usd: float = Field(ge=0, le=100_000)
    has_serial: bool = True
    unit_id: UnitId | None = None
    sealed_consumable: bool = False
    weight_g: float | None = Field(default=None, ge=0, le=100_000)
    customer_id: str = Field(default="CUST-001", pattern=ID_PATTERN)


class ReviewRequest(BaseModel):
    action: Literal["approve", "hold"]
    reviewer: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=500)
