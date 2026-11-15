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

# ---------- the size of the problem, year by year (US retail; nobody publishes Amazon's own figures) ----------
# Each year: merchandise returned, the share of returns deemed fraudulent or abusive, and the dollars lost to it,
# as reported by the NRF's annual returns survey (with Appriss Retail to 2023, Happy Returns from 2024) and by
# Appriss Retail's own benchmark from 2024. The two series differ in method from 2024 on, so both are shown.
# Amazon's fiscal year is the calendar year.
HISTORY_SOURCES = {
    "nrf2021": ("NRF / Appriss Retail, Jan 2022: $761B returned in 2021; $10.30 of every $100 returned lost to fraud; "
                "online $218B returned, $23.2B (10.6%) fraudulent",
                "https://nrf.com/media-center/press-releases/retail-returns-increased-761-billion-2021-result-overall-sales-growth"),
    "nrf2022": ("NRF / Appriss Retail, 2022 Consumer Returns in the Retail Industry: $816B returned; $84.9B (10.4%) fraudulent; "
                "online $212B returned, $22.8B (10.7%) fraudulent",
                "https://cdn.nrf.com/sites/default/files/2023-01/Customer%20Returns%20in%20the%20Retail%20Industry_2022_Final_1.pdf"),
    "nrf2023": ("NRF / Appriss Retail, Dec 2023 (via Retail Dive): $743B returned in 2023; $101B (13.7%) lost to fraud and abuse",
                "https://www.retaildive.com/news/retailers-took-back-743b-in-returns-last-year-with-101b-lost-to-fraud-n/703516/"),
    "appriss2024": ("Appriss Retail / Deloitte, 2024 Consumer Returns in the Retail Industry: $685B returned; "
                    "$103B (15.14%) lost to fraud and abuse",
                    "https://chainstoreage.com/losses-return-fraud-and-abuse-exceed-100-billion"),
    "nrf2024": ("NRF / Happy Returns, Dec 2024: $890B of 2024 sales projected to be returned (16.9%)",
                "https://nrf.com/research/2024-consumer-returns-retail-industry"),
    "nrf2025": ("NRF / Happy Returns, 2025 Retail Returns Landscape: $849.9B projected returned (15.8%); 9% of returns fraudulent",
                "https://a-us.storyblok.com/f/1021220/x/6e22cae2b7/2025-retail-returns-landscape.pdf"),
    "appriss2025": ("Appriss Retail, 2026 Total Retail Loss report: $706B returned in 2025; $100B (14.2%) preventable fraud and abuse",
                    "https://www.just-style.com/news/appriss-retail-loss-2025-report/"),
}
# year, returned $B, fraud+abuse $B, fraud share of returns, series, source key, note
HISTORY = [
    {"year": 2021, "returned_b": 761.0, "fraud_b": 78.4, "fraud_share": 0.103, "series": "NRF / Appriss",
     "source": "nrf2021", "note": "$10.30 lost per $100 returned; online returns $218B, $23.2B fraudulent"},
    {"year": 2022, "returned_b": 816.0, "fraud_b": 84.9, "fraud_share": 0.104, "series": "NRF / Appriss",
     "source": "nrf2022", "note": "online returns $212B, $22.8B (10.7%) fraudulent"},
    {"year": 2023, "returned_b": 743.0, "fraud_b": 101.0, "fraud_share": 0.137, "series": "NRF / Appriss",
     "source": "nrf2023", "note": "fraud and abuse"},
    {"year": 2024, "returned_b": 685.0, "fraud_b": 103.0, "fraud_share": 0.1514, "series": "Appriss / Deloitte",
     "source": "appriss2024", "note": "NRF / Happy Returns put total 2024 returns at $890B", "also": "nrf2024"},
    {"year": 2025, "returned_b": 706.0, "fraud_b": 100.0, "fraud_share": 0.142, "series": "Appriss",
     "source": "appriss2025", "note": "NRF / Happy Returns: $849.9B returned, 9% fraudulent", "also": "nrf2025"},
]


def industry() -> dict:
    """Public, sourced context for the dashboard: US return fraud by year. No station data in here."""
    return {"history": HISTORY, "sources": {k: {"title": t, "url": u} for k, (t, u) in HISTORY_SOURCES.items()},
            "caveat": "US retail industry totals from the NRF and Appriss Retail surveys. Amazon does not publish "
                      "its own return-fraud figures; its fiscal year is the calendar year."}

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
