"""Disposition: what should happen to the item, by simple arithmetic the retailer can read.

Compares what the item can be resold for (by grade) with what it costs to bring it back.
Cost figures are demo assumptions and are returned with the answer so the dashboard can show them.
"""
SHIP_BACK_USD = 9.0      # assumed return-shipping label
HANDLING_USD = 4.0       # assumed warehouse receive + inspect
REFURB_USD = 15.0        # assumed clean/repair for grade C


def choose(grade: str | None, resale_value_by_grade: dict, decision: str) -> dict:
    assumptions = {"ship_back_usd": SHIP_BACK_USD, "handling_usd": HANDLING_USD, "refurb_usd": REFURB_USD}
    if decision in ("RED", "REVIEW") or grade is None:
        return {"action": "HOLD_FOR_REVIEW", "ship_back": False, "net_recovery_usd": 0.0, "assumptions": assumptions}

    value = float(resale_value_by_grade.get(grade, 0.0))
    net_if_shipped = value - SHIP_BACK_USD - HANDLING_USD
    if grade == "A" and net_if_shipped > 0:
        action, ship, net = "RESTOCK", True, net_if_shipped
    elif grade == "B" and net_if_shipped > 0:
        action, ship, net = "RESELL_OPEN_BOX", True, net_if_shipped
    elif grade == "C" and net_if_shipped - REFURB_USD > 0:
        action, ship, net = "REFURBISH", True, net_if_shipped - REFURB_USD
    elif value > 0:
        action, ship, net = "RESELL_LOCALLY", False, value          # not worth the trip back
    else:
        action, ship, net = "DONATE_OR_RECYCLE", False, 0.0
    return {"action": action, "ship_back": ship, "net_recovery_usd": round(net, 2), "assumptions": assumptions}
