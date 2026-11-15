"""Logistics and CO2 impact of the returns in our own database, from sourced per-unit figures.

Boomerang saves trips in three places:
  1. A return that is not worth shipping back (resell locally, donate, dispose) skips the trip
     from the customer to the returns centre.
  2. A wrong pick caught at ship-out skips two trips: the wrong item coming back and the
     replacement going out.
  3. Items routed to resale (restock, open box, refurbish, local resale) stay in use.

CO2 per avoided trip: Oliver Wyman 2023, a 1 kg parcel delivered home = 1,075 g CO2e (one way).
Wrong-pick cost: Intermec / Honeywell survey, about $22 per mis-pick. Sources: estimate.SOURCES.
"""
from . import disposition

PARCEL_TRIP_KG_CO2 = 1.075     # Oliver Wyman 2023, 1 kg parcel, home delivery
DEFAULT_WEIGHT_G = 1000.0      # used for "kept in use" kg when no weight was recorded
WRONG_PICK_COST_USD = 22.0     # Intermec / Honeywell mis-pick survey
KEPT_IN_USE = {"RESTOCK", "RESELL_OPEN_BOX", "REFURBISH", "RESELL_LOCALLY"}
NOT_SHIPPED_BACK = {"RESELL_LOCALLY", "DONATE_OR_RECYCLE", "DISPOSE"}


def trip_co2_kg(weight_g: float | None = None) -> float:
    """CO2 of one parcel trip (per-parcel figure from Oliver Wyman; weight-independent)."""
    return PARCEL_TRIP_KG_CO2


def summarise(returns: list[dict], wrong_picks: list[float | None], flagged: tuple[str, ...]) -> dict:
    """returns: stored return records. wrong_picks: item weights of wrong picks stopped at ship-out."""
    def weight(d):
        return d.get("return_weight_g") or DEFAULT_WEIGHT_G

    def released(d):
        return (d.get("review") or {}).get("action") == "approve"

    def rejected_(d):
        return (d.get("review") or {}).get("action") == "reject"

    # Confirmed fraud (a reviewer rejected it) is refused at the counter: that parcel never travels.
    rejected = [d for d in returns if rejected_(d)]
    acted = [d for d in returns if (d.get("decision") not in flagged or released(d)) and not rejected_(d)]
    skipped = [d for d in acted if d.get("disposition") in NOT_SHIPPED_BACK] + rejected
    kept = [d for d in acted if d.get("disposition") in KEPT_IN_USE]
    disposed = [d for d in acted if d.get("disposition") == "DISPOSE"]
    stopped = [d for d in returns if (d.get("decision") == "RED" and not released(d)) or rejected_(d)]

    co2_returns = sum(trip_co2_kg(weight(d)) for d in skipped)
    co2_picks = sum(2 * trip_co2_kg(w) for w in wrong_picks)
    return {
        "co2_avoided_kg": round(co2_returns + co2_picks, 2),
        "trips_avoided": len(skipped) + 2 * len(wrong_picks),
        "ship_backs_avoided": len(skipped),
        "fraud_rejected": len(rejected),
        "wrong_picks_stopped": len(wrong_picks),
        "wrong_pick_cost_avoided_usd": round(len(wrong_picks) * WRONG_PICK_COST_USD, 2),
        "kept_in_use_kg": round(sum(weight(d) for d in kept) / 1000, 2),
        "kept_in_use_items": len(kept),
        "unsafe_items_kept_off_shelves": len(disposed),
        "refunds_stopped_usd": round(sum(d.get("price_usd") or 0 for d in stopped), 2),
        "returns_counted": len(returns),
        "assumptions": {
            "parcel_trip_kg_co2": PARCEL_TRIP_KG_CO2,
            "wrong_pick_cost_usd": WRONG_PICK_COST_USD,
            "return_label_usd": disposition.SHIP_BACK_USD,
            "default_weight_g": DEFAULT_WEIGHT_G,
        },
    }
