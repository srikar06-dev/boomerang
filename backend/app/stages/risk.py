"""Risk score: fixed, readable rules. The model never decides; it only supplies evidence.

risk = 0.30W + 0.30V + 0.15S + 0.10D + 0.10H + 0.05P
"""
from dataclasses import dataclass, field

WEIGHTS = {"W": 0.30, "V": 0.30, "S": 0.15, "D": 0.10, "H": 0.10, "P": 0.05}

# Weight tolerance: below this difference W = 0 (scale reads to ~100 g)
WEIGHT_TOL_G = 150
WEIGHT_TOL_PCT = 0.15
WEIGHT_FULL_PCT = 0.50  # W reaches 1 at a 50% difference


@dataclass
class Signals:
    shipout_weight_g: float | None
    return_weight_g: float | None
    same_unit_confidence: float          # 0..1 from the vision model
    serial_match: bool | None            # None = serial unreadable
    damage_level: float = 0.0            # 0 none, 0.5 minor, 1 major
    flagged_returns: int = 0
    total_orders: int = 1
    price_usd: float = 0.0
    sensor_distance: float | None = None  # 0..1 sealed-box signature mismatch (optional)
    serial_expected: bool = True          # False for products that have no serial (hoodie, bottle)


@dataclass
class RiskResult:
    score: float
    terms: dict
    reasons: list = field(default_factory=list)
    missing: list = field(default_factory=list)  # evidence we expected but did not get: "WEIGHT", "SERIAL"
    model_v: float = 0.0   # V from the vision model alone, before a serial mismatch forces V = 1


def unit_confidence(same_item: bool, same_unit: bool, confidence: float) -> float:
    """Turns the vision model's answer into Signals.same_unit_confidence.

    The model returns ONE confidence for its whole answer. "Different unit, 90% sure" must
    become 0.1 here, not 0.9 - passing the raw confidence through would score a swap as safe.
    """
    c = max(0.0, min(1.0, confidence))
    return c if (same_item and same_unit) else 1.0 - c


def weight_term(ship: float | None, ret: float | None) -> float:
    if not ship or ret is None:
        return 0.0
    diff = abs(ret - ship)
    tol = max(WEIGHT_TOL_G, WEIGHT_TOL_PCT * ship)
    if diff <= tol:
        return 0.0
    pct = diff / ship
    span = WEIGHT_FULL_PCT - WEIGHT_TOL_PCT
    return min(1.0, max(0.0, (pct - WEIGHT_TOL_PCT) / span))


def score(s: Signals) -> RiskResult:
    reasons = []
    missing = []
    W = weight_term(s.shipout_weight_g, s.return_weight_g)
    if s.shipout_weight_g and s.return_weight_g is None:
        missing.append("WEIGHT")           # no reading is not the same as a matching reading
        reasons.append("WEIGHT_MISSING")
    if W > 0:
        reasons.append(f"WEIGHT_MISMATCH ({s.shipout_weight_g:.0f} g -> {s.return_weight_g:.0f} g)")

    V = 1.0 - max(0.0, min(1.0, s.same_unit_confidence))
    model_v = V
    if s.serial_match is False:
        V = 1.0
        reasons.append("SERIAL_MISMATCH")
    elif V > 0.5:
        reasons.append("UNIT_MATCH_LOW")
    if s.serial_match is None and s.serial_expected:
        missing.append("SERIAL")
        reasons.append("SERIAL_UNREADABLE")

    S = max(0.0, min(1.0, s.sensor_distance or 0.0))
    if S > 0.5:
        reasons.append("SEALED_SIGNATURE_DIFF")

    D = s.damage_level
    if D > 0:
        reasons.append("NEW_DAMAGE")

    H = s.flagged_returns / max(1, s.total_orders)
    if H > 0.3:
        reasons.append("HISTORY_FLAGS")

    P = min(1.0, s.price_usd / 500)

    terms = {"W": W, "V": V, "S": S, "D": D, "H": H, "P": P}
    total = sum(WEIGHTS[k] * v for k, v in terms.items())
    return RiskResult(score=round(total, 3), terms=terms, reasons=reasons, missing=missing, model_v=model_v)
