"""What Boomerang would save across US online returns: a sourced, three-scenario estimate.

Every input names its source (SOURCES) or says it is an assumption. Where our own test set has
enough labelled returns, the measured rate replaces the assumed one (see us_estimate).
Same model as the team's "Boomerang - US real-world savings estimate" sheet.
"""
SOURCES = {
    "census": ("US Census Bureau: 2025 e-commerce sales $1,233.7B",
               "https://www.census.gov/retail/ecommerce.html"),
    "nrf_rate": ("NRF / Happy Returns 2025: 19.3% online return rate; 9% of returns fraudulent",
                 "https://www.cahoot.ai/ecommerce-returns-and-refund-fraud"),
    "appriss": ("Appriss Retail 2026 Total Retail Loss report: $706B returned in 2025; 14.2% fraud + abuse "
                "(abuse 12%, fraud 2%)", "https://www.businesswire.com/news/home/20260219293604/en/Appriss-Retail-Benchmark-Report-Uncovers-$796B-in-Total-Retail-Loss"),
    "intermec": ("Intermec / Honeywell survey: average mis-pick costs about $22",
                 "https://www.sdcexec.com/warehousing/automation/news/10857269/intermec-inc-division-of-honeywell-international-dc-challenges-unveiled-during-promat-2013mispicks-cost-businesses-nearly-390000-yearly"),
    "warehouseos": ("WarehouseOS: 35% of facilities run mis-pick rates of 1% or more; ~$30 per mis-pick",
                    "https://warehouseos.com/the-cost-of-picking-mistakes-for-small-businesses/"),
    "opensend": ("Opensend: return shipping averages $8-12 per item",
                 "https://www.opensend.com/post/return-shipping-cost-statistics"),
    "clickpost": ("ClickPost: inspection and grading labor $2-5 per return",
                  "https://www.clickpost.ai/en-us/blog/returns-protection-cost-roi-for-ecommerce"),
    "umich": ("Univ. of Michigan (ES&T 2021): 167 g CO2 per package, best last-mile case",
              "https://www.sciencedaily.com/releases/2021/08/210818135230.htm"),
    "oliver_wyman": ("Oliver Wyman 2023: 1 kg parcel delivered home = 1,075 g CO2e",
                     "https://www.oliverwyman.com/our-expertise/journals/retail-and-consumer-journal/2023/delivery-decarbonization-pathway.html"),
    "optoro": ("Optoro 2019: 3.5B items returned, 15M t CO2 from return transport (about 4.3 kg per item)",
               "https://info.optoro.com/hubfs/Optoro 2019 Impact Report.pdf"),
    "nova": ("AWS Bedrock: Amazon Nova Lite $0.06 / $0.24 per million input / output tokens",
             "https://aws.amazon.com/bedrock/pricing/"),
}
SCENARIOS = ("conservative", "base", "optimistic")

# name: (conservative, base, optimistic, source key or None for an assumption, label)
INPUTS = {
    "ecom_sales_b":     (1233.7, 1233.7, 1233.7, "census", "US e-commerce sales, 2025 ($B)"),
    "return_rate":      (0.193, 0.193, 0.193, "nrf_rate", "Online return rate"),
    "item_value":       (60, 60, 60, None, "Average returned item value ($)"),
    "adoption":         (0.01, 0.05, 0.10, None, "Share of US online returns using Boomerang"),
    "fraud_share":      (0.02, 0.09, 0.142, "appriss", "Fraud share of return value (Appriss fraud / NRF / Appriss fraud+abuse)"),
    "fraud_catch":      (0.50, 0.65, 0.80, None, "Share of that fraud Boomerang catches"),
    "mispick_rate":     (0.005, 0.01, 0.01, "warehouseos", "Mis-pick rate at ship-out"),
    "mispick_catch":    (0.60, 0.75, 0.85, None, "Mis-picks the ship-out check catches"),
    "mispick_cost":     (22, 22, 30, "intermec", "Cost per mis-pick ($)"),
    "low_value_share":  (0.05, 0.10, 0.15, None, "Returns not worth shipping back"),
    "label_usd":        (8, 10, 12, "opensend", "Return label avoided per skipped trip ($)"),
    "green_share":      (0.50, 0.60, 0.70, None, "Returns cleared GREEN at the counter"),
    "grading_usd":      (2, 3, 5, "clickpost", "Grading labor saved per GREEN return ($)"),
    "co2_per_trip_kg":  (0.167, 1.075, 4.3, "oliver_wyman", "CO2 per avoided parcel trip (kg): UMich / Oliver Wyman / Optoro"),
    "model_usd":        (0.00025, 0.00025, 0.00025, "nova", "Vision model cost per check ($), ~3k in + 300 out tokens"),
    "counter_seconds":  (30, 30, 30, None, "Extra counter time per return (s)"),
    "wage_usd":         (18, 18, 18, None, "Staff cost per hour ($)"),
}
MIN_LABELLED = 5     # labelled test-set returns needed before a measured rate replaces an assumption


def _measured(test_set: dict) -> dict:
    out = {}
    if test_set.get("fraud_total", 0) >= MIN_LABELLED:
        out["fraud_catch"] = test_set["fraud_caught"] / test_set["fraud_total"]
    if test_set.get("honest_total", 0) >= MIN_LABELLED:
        out["green_share"] = test_set["honest_green"] / test_set["honest_total"]
    return out


def _run(v: dict) -> dict:
    value_m = v["ecom_sales_b"] * 1000 * v["return_rate"] * v["adoption"]      # $M of returns checked
    returns_m = value_m / v["item_value"]                                        # million returns
    orders_m = v["ecom_sales_b"] * 1000 / v["item_value"] * v["adoption"]        # million orders shipped
    fraud = value_m * v["fraud_share"] * v["fraud_catch"]
    picks_m = orders_m * v["mispick_rate"] * v["mispick_catch"]
    picks = picks_m * v["mispick_cost"]
    skipped_m = returns_m * v["low_value_share"]
    shipping = skipped_m * v["label_usd"]
    grading = returns_m * v["green_share"] * v["grading_usd"]
    running = returns_m * (v["model_usd"] + v["counter_seconds"] / 3600 * v["wage_usd"])
    net = fraud + picks + shipping + grading - running
    trips_m = skipped_m + 2 * picks_m
    co2_t = trips_m * 1e6 * v["co2_per_trip_kg"] / 1000
    per100k = 0.1 / returns_m
    r = lambda x, n=1: round(x, n)
    return {
        "returns_m": r(returns_m), "orders_m": r(orders_m),
        "fraud_stopped_musd": r(fraud), "wrong_pick_musd": r(picks), "shipping_musd": r(shipping),
        "grading_musd": r(grading), "running_musd": r(running), "net_musd": r(net),
        "net_per_return_usd": r(net / returns_m, 2), "trips_avoided_m": r(trips_m), "co2_t": r(co2_t, 0),
        "per_100k": {"fraud_usd": r(fraud * 1e6 * per100k, 0), "wrong_pick_usd": r(picks * 1e6 * per100k, 0),
                     "shipping_usd": r(shipping * 1e6 * per100k, 0), "grading_usd": r(grading * 1e6 * per100k, 0),
                     "running_usd": r(running * 1e6 * per100k, 0), "net_usd": r(net * 1e6 * per100k, 0),
                     "co2_t": r(co2_t * per100k, 1)},
    }


def us_estimate(test_set: dict) -> dict:
    measured = _measured(test_set)
    scenarios = {}
    for i, name in enumerate(SCENARIOS):
        values = {k: measured.get(k, spec[i]) for k, spec in INPUTS.items()}
        scenarios[name] = _run(values)
    inputs = [{"key": k, "label": spec[4], "values": [measured.get(k, spec[i]) for i in range(3)],
               "source": spec[3], "measured": k in measured} for k, spec in INPUTS.items()]
    return {"scenarios": scenarios, "inputs": inputs, "measured": measured,
            "sources": {k: {"title": t, "url": u} for k, (t, u) in SOURCES.items()}}
