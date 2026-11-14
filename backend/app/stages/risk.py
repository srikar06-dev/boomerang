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


@dataclass
class RiskResult:
    score: float
    terms: dict
    reasons: list = field(default_factory=list)


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
    W = weight_term(s.shipout_weight_g, s.return_weight_g)
    if W > 0:
        reasons.append(f"WEIGHT_MISMATCH ({s.shipout_weight_g:.0f} g -> {s.return_weight_g:.0f} g)")

    V = 1.0 - max(0.0, min(1.0, s.same_unit_confidence))
    if s.serial_match is False:
        V = 1.0
        reasons.append("SERIAL_MISMATCH")
    elif V > 0.5:
        reasons.append("UNIT_MATCH_LOW")

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
    return RiskResult(score=round(total, 3), terms=terms, reasons=reasons)
