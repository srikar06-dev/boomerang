"""Policy gate: turns the risk score + hard rules into a decision. Fail-safe by design."""
from .risk import RiskResult

GREEN, YELLOW, RED, REVIEW = "GREEN", "YELLOW", "RED", "REVIEW"
LED = {GREEN: "L:G", YELLOW: "L:Y", RED: "L:R", REVIEW: "L:Y"}

# Items at or above this price whose unit cannot be proven (no serial on the device itself) are
# never an instant refund: they are held (YELLOW) until the warehouse opens and checks them.
# Below it, a fast refund plus the customer's history is cheaper than an inspection.
UNPROVABLE_HOLD_USD = 30.0


def decide(
    risk: RiskResult,
    *,
    model_ok: bool,
    model_confidence: float,
    code_visible: bool,
    image_reused: bool,
    price_usd: float,
    visual_disagrees: bool = False,
    unit_provable: bool = True,
    seal_broken: bool = False,
) -> tuple[str, list[str]]:
    reasons = list(risk.reasons)

    # 1. Model problems never refund
    if not model_ok or model_confidence < 0.6:
        return REVIEW, reasons + ["MODEL_UNSURE"]
    # 2. Capture authenticity
    if not code_visible:
        return REVIEW, reasons + ["CODE_NOT_VISIBLE"]
    if image_reused:
        return REVIEW, reasons + ["IMAGE_REUSED"]
    # 3a. A serial mismatch that NOTHING else supports (weight fine, model says same unit, OpenCV
    #     agrees) is most often a misread label: a person checks it instead of an automatic RED.
    serial_only = ("SERIAL_MISMATCH" in reasons and risk.model_v <= 0.5
                   and risk.terms["W"] == 0 and not visual_disagrees)
    if serial_only:
        return REVIEW, reasons + ["SERIAL_ONLY_SIGNAL"]
    # 3. Hard red: empty/filler box or a different unit
    if risk.terms["W"] >= 1.0 or risk.terms["V"] > 0.8:
        return RED, reasons
    # 5. Sensor signal alone may only push to review
    sensor_only = risk.terms["S"] > 0.5 and risk.score - 0.15 * risk.terms["S"] < 0.25

    if risk.score > 0.60:
        decision = RED
    elif risk.score >= 0.25:
        decision = YELLOW
    else:
        decision = GREEN
    if sensor_only:
        decision = REVIEW
    # 4. Expensive items are never instant
    if decision == GREEN and price_usd > 300:
        decision = YELLOW
        reasons.append("HIGH_VALUE")
    # 7. Missing or weak evidence is never an instant refund (reasons were added by risk.score)
    if decision == GREEN and "WEIGHT" in risk.missing:
        decision = REVIEW                  # we recorded a ship-out weight but got no return weight
    if decision == GREEN and ("SERIAL" in risk.missing or risk.terms["V"] > 0.5):
        decision = YELLOW                  # serial unreadable, or the unit match is doubtful
    # 8. Local OpenCV check says the photos do not show the same unit, but the model says they do.
    #    Two independent readers disagree -> a person looks. Never RED on this signal alone.
    if visual_disagrees and decision in (GREEN, YELLOW):
        decision = REVIEW
        reasons.append("VISUAL_MISMATCH")
    # 9. Return profile. Nothing proves it is the same unit (no serial on the device): hold it for
    #    inspection unless it is cheap. An opened sealed product is held too (and disposed, see
    #    disposition) - the refund is a policy call, but it can never go back on the shelf.
    if decision == GREEN and not unit_provable and price_usd >= UNPROVABLE_HOLD_USD:
        decision = YELLOW
        reasons.append("UNIT_NOT_VERIFIABLE")
    if seal_broken and decision in (GREEN, YELLOW):
        decision = YELLOW
        reasons.append("SEAL_BROKEN")
    return decision, reasons
