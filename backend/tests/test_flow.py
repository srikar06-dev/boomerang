"""End-to-end flow with stand-ins for MongoDB, S3 and the vision model. No network needed.

ship-out (staff) -> return session -> upload -> /return -> decision
"""
import io

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw

from app import config, main, seed
from app.models import ReturnRequest, ReviewRequest, SessionRequest, ShipoutRequest, UploadUrlRequest
from app.stages.vision import VisionResult
from tests.fakes import FakeDB, FakeS3

KEY = "k" * 48


def photo(n: int) -> bytes:
    """A distinct, structured test picture per n (so perceptual hashes differ)."""
    img = Image.new("RGB", (640, 480), "white")
    d = ImageDraw.Draw(img)
    for i in range(6):
        x = (n * 97 + i * 131) % 560
        y = (n * 53 + i * 71) % 400
        d.rectangle([x, y, x + 60 + 9 * i, y + 40 + 7 * n % 50], fill=((n * 40) % 255, (i * 45) % 255, 90))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture
def world(monkeypatch):
    database, s3 = FakeDB(), FakeS3()
    seed.run(database)
    monkeypatch.setattr(config, "LINK_SIGNING_SECRET", "a" * 64)
    monkeypatch.setattr(config, "STATION_KEY", KEY)
    monkeypatch.setattr(main, "db", lambda: database)
    monkeypatch.setattr(main.storage, "presign_put", s3.presign_put)
    monkeypatch.setattr(main.storage, "get_bytes", s3.get_bytes)
    monkeypatch.setattr(main.storage, "presign_get", s3.presign_get)
    answer = {"result": VisionResult(same_item=True, same_unit=True, confidence=0.95, code_visible=True,
                                     scale_reading_g=1400, serial_read="SN-0000 0001", grade="A")}
    monkeypatch.setattr(main.vision, "grade", lambda *a, **k: (answer["result"], "fake-model"))
    # These synthetic ship-out/return pictures are unrelated images, so the OpenCV cross-check
    # would (correctly) flag every return. It has its own tests in test_visual.py; switch it off here.
    monkeypatch.setattr(main, "_visual_check", lambda fp, clean: None)
    return database, s3, answer


def upload(s3, token, pics):
    for slot, data in zip(("item", "serial"), pics):
        r = main.upload_url(UploadUrlRequest(token=token, slot=slot))
        s3.objects[r.key] = data


def do_shipout(s3, order="ORD-1001", weight=1400, serial="SN00000001", pics=None):
    s = main.create_session(SessionRequest(order_id=order, purpose="shipout"), x_station_key=KEY)
    upload(s3, s.token, pics or (photo(1), photo(2)))
    return main.shipout(ShipoutRequest(token=s.token, weight_g=weight, serial=serial))


def do_return(s3, order="ORD-1001", pics=None, weight=None, label=None, key=None):
    s = main.create_session(SessionRequest(order_id=order))
    upload(s3, s.token, pics or (photo(3), photo(4)))
    return main.submit_return(ReturnRequest(token=s.token, weight_g=weight, label=label), x_station_key=key), s


def test_honest_return_is_not_flagged(world):
    database, s3, _ = world
    do_shipout(s3)
    r, _ = do_return(s3)
    # LAPTOP-01 costs $899, so the best possible outcome is YELLOW (never instant above $300)
    assert r.decision == "YELLOW" and "HIGH_VALUE" in r.reasons
    saved = database.returns.docs[0]
    assert saved["return_id"] == r.return_id and len(saved["sha256"]) == 2 and saved["model_used"] == "fake-model"


def test_cheap_honest_return_is_green(world):
    _, s3, answer = world
    do_shipout(s3, order="ORD-1005", weight=260, serial="SN00000001")     # headphones, $149
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 262})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "GREEN" and r.led == "L:G"
    assert r.disposition["action"] == "RESTOCK"


def test_rock_in_box_is_red(world):
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 300})
    r, _ = do_return(s3)
    assert r.decision == "RED" and any("WEIGHT_MISMATCH" in x for x in r.reasons)
    assert r.disposition["action"] == "HOLD_FOR_REVIEW"


def test_serial_swap_alone_is_held_for_review(world):
    # Same-model swap: weight matches and the model sees nothing wrong; only the serial differs.
    # A serial read can be wrong (rotated label, wrong line), so a person checks it: REVIEW, never a refund.
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"serial_read": "SN99999999"})
    r, _ = do_return(s3)
    assert r.decision == "REVIEW" and "SERIAL_MISMATCH" in r.reasons and "SERIAL_ONLY_SIGNAL" in r.reasons


def test_serial_swap_with_wrong_weight_is_red(world):
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"serial_read": "SN99999999", "scale_reading_g": 300})
    assert do_return(s3)[0].decision == "RED"


def test_upside_down_label_misread_still_matches_via_label_codes(world):
    _, s3, answer = world
    do_shipout(s3)      # serial SN00000001
    answer["result"] = answer["result"].model_copy(
        update={"serial_read": "X00285289", "label_codes": ["X00285289", "SN0OOOOO1"]})
    r, _ = do_return(s3)
    assert "SERIAL_MISMATCH" not in r.reasons


def test_model_says_different_unit_is_red(world):
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"same_unit": False, "confidence": 0.9, "serial_read": None})
    assert do_return(s3)[0].decision == "RED"


def test_model_failure_goes_to_review(world):
    _, s3, _ = world
    do_shipout(s3)
    main.vision.grade = lambda *a, **k: (None, "none")
    r, _ = do_return(s3, weight=1400)
    assert r.decision == "REVIEW" and r.reasons == ["MODEL_UNSURE"]


def test_missing_code_goes_to_review_when_required(world, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_CODE", True)
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"code_visible": False})
    assert do_return(s3)[0].decision == "REVIEW"


def test_missing_code_is_fine_when_not_required(world, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_CODE", False)
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"code_visible": False})
    r, _ = do_return(s3)
    assert "CODE_NOT_VISIBLE" not in r.reasons and r.decision != "REVIEW"


def test_reusing_the_shipout_photo_goes_to_review(world):
    _, s3, _ = world
    do_shipout(s3, pics=(photo(1), photo(2)))
    r, _ = do_return(s3, pics=(photo(1), photo(4)))       # item photo is the ship-out photo again
    assert r.decision == "REVIEW" and "IMAGE_REUSED" in r.reasons


def test_reusing_an_earlier_return_photo_goes_to_review(world):
    _, s3, _ = world
    do_shipout(s3)
    do_return(s3, pics=(photo(3), photo(4)))
    r, _ = do_return(s3, pics=(photo(3), photo(5)))
    assert "IMAGE_REUSED" in r.reasons


def test_token_works_only_once(world):
    _, s3, _ = world
    do_shipout(s3)
    _, session = do_return(s3)
    with pytest.raises(HTTPException) as e:
        main.submit_return(ReturnRequest(token=session.token))
    assert e.value.status_code == 401


def test_return_without_photos_is_rejected_and_token_survives(world):
    _, s3, _ = world
    do_shipout(s3)
    s = main.create_session(SessionRequest(order_id="ORD-1001"))
    with pytest.raises(HTTPException) as e:
        main.submit_return(ReturnRequest(token=s.token))
    assert e.value.status_code == 400
    upload(s3, s.token, (photo(3), photo(4)))             # shopper can still finish
    assert main.submit_return(ReturnRequest(token=s.token)).decision in ("GREEN", "YELLOW")


def test_non_image_upload_is_rejected(world):
    _, s3, _ = world
    do_shipout(s3)
    s = main.create_session(SessionRequest(order_id="ORD-1001"))
    upload(s3, s.token, (b"<html>not a photo</html>", photo(4)))
    with pytest.raises(HTTPException) as e:
        main.submit_return(ReturnRequest(token=s.token))
    assert e.value.status_code == 400


def test_shipout_session_needs_station_key(world):
    for key in (None, "wrong"):
        with pytest.raises(HTTPException) as e:
            main.create_session(SessionRequest(order_id="ORD-1001", purpose="shipout"), x_station_key=key)
        assert e.value.status_code == 403


def test_return_token_cannot_be_used_for_shipout(world):
    _, s3, _ = world
    s = main.create_session(SessionRequest(order_id="ORD-1001"))
    upload(s3, s.token, (photo(1), photo(2)))
    with pytest.raises(HTTPException) as e:
        main.shipout(ShipoutRequest(token=s.token, weight_g=5))
    assert e.value.status_code == 401


def test_upload_keys_are_scoped_to_the_session(world):
    a = main.create_session(SessionRequest(order_id="ORD-1001"))
    b = main.create_session(SessionRequest(order_id="ORD-1001"))
    ka = main.upload_url(UploadUrlRequest(token=a.token, slot="item")).key
    kb = main.upload_url(UploadUrlRequest(token=b.token, slot="item")).key
    assert ka != kb and ka.startswith("return/") and ka.endswith("/item.jpg")


def test_station_dependency(world):
    main.require_station(KEY)
    with pytest.raises(HTTPException):
        main.require_station(None)


# ---------------------------------------------------------------- staff views
def test_review_queue_evidence_and_stats(world):
    database, s3, answer = world
    do_shipout(s3)                                                     # laptop, $899
    do_shipout(s3, order="ORD-1005", weight=260, serial="SN00000001")  # headphones, $149

    honest = answer["result"].model_copy(update={"scale_reading_g": 262})
    answer["result"] = honest
    green, _ = do_return(s3, order="ORD-1005", pics=(photo(5), photo(6)), label="honest", key=KEY)
    answer["result"] = honest.model_copy(update={"scale_reading_g": 300})
    red, _ = do_return(s3, pics=(photo(7), photo(8)), label="fraud", key=KEY)
    assert (green.decision, red.decision) == ("GREEN", "RED")

    queue = main.list_returns(decision="RED", limit=50)["returns"]
    assert [r["return_id"] for r in queue] == [red.return_id]
    assert len(main.list_returns(decision=None, limit=50)["returns"]) == 2

    pack = main.evidence(red.return_id)
    assert pack["return"]["checks"]["weight_delta_pct"] < -50
    assert len(pack["photos"]["return"]) == 2 and len(pack["photos"]["shipout"]) == 2
    assert pack["shipout_fingerprint"]["serial"] == "SN00000001"

    s = main.stats()
    assert s["by_decision"] == {"GREEN": 1, "YELLOW": 0, "RED": 1, "REVIEW": 0}
    assert s["money_held_usd"] == 899 and s["instant_refunds_usd"] == 149 and s["awaiting_review"] == 1
    assert s["test_set"] == {"fraud_total": 1, "fraud_caught": 1, "fraud_instant_refunds": 0,
                             "honest_total": 1, "honest_flagged": 0, "honest_green": 1}

    after = main.review(ReviewRequest(action="approve", reviewer="Srikar", note="checked by hand"), red.return_id)
    assert after["decision"] == "RED" and after["review"]["action"] == "approve"   # original decision kept
    assert main.stats()["money_held_usd"] == 0


def test_label_is_ignored_without_station_key(world):
    database, s3, _ = world
    do_shipout(s3)
    do_return(s3, label="honest")
    assert database.returns.docs[0]["label"] is None


def test_unknown_return_is_404(world):
    for call in (lambda: main.evidence("0" * 32),
                 lambda: main.review(ReviewRequest(action="hold", reviewer="x"), "0" * 32)):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 404


# ---------------------------------------------------------------- contract: never a bare 500
def test_internal_error_answers_review_not_500(world, monkeypatch):
    database, s3, _ = world
    do_shipout(s3)

    def broken(doc):
        raise RuntimeError("database went away")
    monkeypatch.setattr(database.returns, "insert_one", broken)
    r, _ = do_return(s3)
    assert r.decision == "REVIEW" and r.led == "L:Y" and r.reasons == ["INTERNAL_ERROR"]


def test_client_errors_still_raise(world):
    with pytest.raises(HTTPException) as e:
        main.submit_return(ReturnRequest(token="garbage"), x_station_key=None)
    assert e.value.status_code == 401


def test_model_usage_is_recorded_and_summarised(world, monkeypatch):
    database, s3, _ = world
    monkeypatch.setattr(main.vision, "last_usage", {"model": "us.amazon.nova-lite-v1:0", "input_tokens": 3000,
                                                    "output_tokens": 120, "seconds": 2.5, "cost_usd": 0.000209})
    do_shipout(s3)
    do_return(s3)
    assert database.returns.docs[0]["model_usage"]["input_tokens"] == 3000
    assert main.stats()["model"] == {"calls": 1, "avg_cost_usd": 0.000209, "median_seconds": 2.5}


def test_new_item_at_shipout_then_honest_return(world):
    database, s3, answer = world
    created = main.new_order(main.NewItemRequest(name="Anker charger", price_usd=30, has_serial=True))
    assert created["order_id"] == "ORD-2001"
    do_shipout(s3, order="ORD-2001", weight=1400, serial="SN00000001")
    r, _ = do_return(s3, order="ORD-2001")
    assert r.decision == "GREEN"          # cheap item, same unit, weight and serial match -> instant refund


# ---------- return profiles ----------
def new_item(name, price, unit_id, sealed=False):
    return main.new_order(main.NewItemRequest(name=name, price_usd=price, unit_id=unit_id,
                                              sealed_consumable=sealed))["order_id"]


def test_box_label_only_item_is_held_not_refunded_instantly(world):
    # Arduino in its own box: the label names the listing, not the board. Same everything -> still held.
    _, s3, answer = world
    oid = new_item("Arduino Nano", 45, "box")
    do_shipout(s3, order=oid, serial="SN00000001")
    r, _ = do_return(s3, order=oid)
    assert r.decision == "YELLOW" and "UNIT_NOT_VERIFIABLE" in r.reasons


def test_cheap_unprovable_item_still_gets_fast_refund(world):
    _, s3, answer = world
    oid = new_item("Phone case", 12, "none")
    do_shipout(s3, order=oid, serial=None)
    answer["result"] = answer["result"].model_copy(update={"serial_read": None})
    r, _ = do_return(s3, order=oid)
    assert r.decision == "GREEN" and "UNIT_NOT_VERIFIABLE" not in r.reasons


def test_seeded_bag_without_serial_is_held(world):
    _, s3, answer = world
    do_shipout(s3, order="ORD-1017", weight=780, serial=None)     # laptop bag $59, no serial
    answer["result"] = answer["result"].model_copy(update={"serial_read": None, "scale_reading_g": 780})
    r, _ = do_return(s3, order="ORD-1017")
    assert r.decision == "YELLOW" and "UNIT_NOT_VERIFIABLE" in r.reasons


def test_opened_cream_is_held_and_disposed(world):
    _, s3, answer = world
    oid = new_item("Face cream 50 ml", 25, "none", sealed=True)
    do_shipout(s3, order=oid, serial=None)
    answer["result"] = answer["result"].model_copy(update={"serial_read": None, "seal_intact": False})
    r, _ = do_return(s3, order=oid)
    assert r.decision == "YELLOW" and "SEAL_BROKEN" in r.reasons
    assert r.disposition["action"] == "DISPOSE" and r.disposition["ship_back"] is False


def test_sealed_cream_with_intact_seal_is_green_and_restocked(world):
    _, s3, answer = world
    oid = new_item("Face cream 50 ml", 25, "none", sealed=True)
    do_shipout(s3, order=oid, serial=None)
    answer["result"] = answer["result"].model_copy(update={"serial_read": None, "seal_intact": True})
    r, _ = do_return(s3, order=oid)
    assert r.decision == "GREEN" and r.disposition["action"] == "RESTOCK"


# ---------- ship-out pick check ----------
def shipout_session(s3, order):
    s = main.create_session(SessionRequest(order_id=order, purpose="shipout"), x_station_key=KEY)
    upload(s3, s.token, (photo(1), photo(2)))
    return s.token


def test_pick_check_ok_suggests_serial_and_records_existing_damage(world):
    database, s3, answer = world
    answer["result"] = answer["result"].model_copy(update={"new_damage": ["scuff on lid"]})
    token = shipout_session(s3, "ORD-1001")
    check = main.shipout_check(main.ShipoutCheckRequest(token=token))
    assert check["product_match"] is True and check["serial_suggestion"] == "SN00000001"
    main.shipout(ShipoutRequest(token=token, weight_g=1400, serial=check["serial_suggestion"]))
    fp = database.orders.find_one({"order_id": "ORD-1001"})["fingerprint"]
    assert fp["pick_verified"] is True and fp["defects"] == ["scuff on lid"]


def test_wrong_pick_is_refused_and_session_survives(world):
    database, s3, answer = world
    answer["result"] = answer["result"].model_copy(update={"same_item": False, "notes": "This is a mouse."})
    token = shipout_session(s3, "ORD-1001")
    assert main.shipout_check(main.ShipoutCheckRequest(token=token))["product_match"] is False
    with pytest.raises(HTTPException) as e:
        main.shipout(ShipoutRequest(token=token, weight_g=1400, serial="SN1"))
    assert e.value.status_code == 409
    # Staff override: same token still works, and the override is recorded.
    main.shipout(ShipoutRequest(token=token, weight_g=1400, serial="SN1", ship_anyway=True))
    fp = database.orders.find_one({"order_id": "ORD-1001"})["fingerprint"]
    assert fp["pick_verified"] is False and fp["pick_notes"].startswith("SHIPPED ANYWAY")


def test_pick_check_model_failure_does_not_block(world, monkeypatch):
    database, s3, _ = world
    monkeypatch.setattr(main.vision, "grade", lambda *a, **k: (None, "none"))
    token = shipout_session(s3, "ORD-1001")
    assert main.shipout_check(main.ShipoutCheckRequest(token=token))["product_match"] is None
    main.shipout(ShipoutRequest(token=token, weight_g=1400, serial="SN1"))
    assert database.orders.find_one({"order_id": "ORD-1001"})["fingerprint"]["pick_verified"] is None


# ---------- impact numbers on the dashboard ----------
def test_impact_counts_stopped_wrong_picks_and_skipped_trips(world):
    from app.stages import impact
    database, s3, answer = world
    # A wrong pick that staff refused to ship: counted once, two trips avoided.
    answer["result"] = answer["result"].model_copy(update={"same_item": False})
    main.shipout_check(main.ShipoutCheckRequest(token=shipout_session(s3, "ORD-1002")))
    answer["result"] = answer["result"].model_copy(update={"same_item": True})
    # An opened cream: disposed locally, so no trip back.
    oid = new_item("Face cream 50 ml", 25, "none", sealed=True)
    do_shipout(s3, order=oid, weight=60, serial=None)
    answer["result"] = answer["result"].model_copy(update={"serial_read": None, "seal_intact": False,
                                                           "scale_reading_g": 60})
    do_return(s3, order=oid)
    m = main.stats()["impact"]
    assert m["wrong_picks_stopped"] == 1 and m["wrong_pick_cost_avoided_usd"] == impact.WRONG_PICK_COST_USD
    assert m["ship_backs_avoided"] == 1 and m["trips_avoided"] == 3
    assert m["unsafe_items_kept_off_shelves"] == 1
    expected = impact.trip_co2_kg(60) + 2 * impact.trip_co2_kg(1400)    # laptop weighs 1400 g in the seed
    assert m["co2_avoided_kg"] == round(expected, 2)


def test_trip_co2_uses_sourced_per_parcel_figure():
    from app.stages import impact
    assert impact.trip_co2_kg(5000) == impact.trip_co2_kg(None) == 1.075


# ---------- US estimate ----------
def test_us_estimate_matches_the_sheet_and_cites_every_source():
    from app.stages import estimate
    e = estimate.us_estimate({"fraud_total": 0, "honest_total": 0})
    base = e["scenarios"]["base"]
    # Same inputs as the team sheet: 198.4M returns, ~$1.07B fraud stopped at a 9% fraud share
    assert base["returns_m"] == 198.4 and base["fraud_stopped_musd"] == 696.5
    assert e["measured"] == {}
    for i in e["inputs"]:
        assert i["source"] is None or i["source"] in e["sources"]


def test_us_estimate_uses_measured_rates_once_the_test_set_is_big_enough():
    from app.stages import estimate
    e = estimate.us_estimate({"fraud_total": 10, "fraud_caught": 9, "honest_total": 10, "honest_green": 8})
    assert e["measured"] == {"fraud_catch": 0.9, "green_share": 0.8}
    fc = next(i for i in e["inputs"] if i["key"] == "fraud_catch")
    assert fc["measured"] and fc["values"] == [0.9, 0.9, 0.9]


def test_rejected_fraud_counts_as_a_trip_avoided_and_leaves_the_queue(world):
    from app.stages import impact
    database, s3, answer = world
    do_shipout(s3, order="ORD-1001")
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 300})     # box of rocks: far too light
    red, _ = do_return(s3, order="ORD-1001")
    assert red.decision == "RED"
    assert main.stats()["awaiting_review"] == 1
    main.review(main.ReviewRequest(action="reject", reviewer="Manju", note="rocks"), return_id=red.return_id)
    s = main.stats()
    assert s["awaiting_review"] == 0
    m = s["impact"]
    assert m["fraud_rejected"] == 1 and m["trips_avoided"] == 1
    assert m["co2_avoided_kg"] == round(impact.PARCEL_TRIP_KG_CO2, 2)
    assert m["refunds_stopped_usd"] == 899


# ---------- packages: everything in one place ----------
def test_packages_lists_every_order_with_shipout_and_latest_return(world):
    database, s3, answer = world
    do_shipout(s3, order="ORD-1001", serial="SN00000001")
    do_return(s3, order="ORD-1001")
    do_shipout(s3, order="ORD-1002", serial="SN00000002", pics=(photo(7), photo(8)))
    out = main.list_packages(q="", status="all", limit=300)
    by_id = {p["order_id"]: p for p in out["packages"]}
    assert len(by_id) == len(list(database.orders.find({})))          # every order, shipped or not
    p1, p2 = by_id["ORD-1001"], by_id["ORD-1002"]
    assert p1["state"] == "returned" and p1["return"]["decision"] in ("GREEN", "YELLOW", "RED", "REVIEW") and p1["shipout"]["serial"] == "SN00000001"
    assert p2["state"] == "shipped" and p2["return"] is None and p2["shipout"]["photos"] == 2
    assert out["packages"][0]["order_id"] == "ORD-1002"                 # newest activity first (shipped last)
    # search by serial, and status filters
    assert [p["order_id"] for p in main.list_packages(q="sn00000002", status="all", limit=300)["packages"]] == ["ORD-1002"]
    assert {p["order_id"] for p in main.list_packages(q="", status="returned", limit=300)["packages"]} == {"ORD-1001"}
    assert main.list_packages(q="", status="held", limit=300)["total"] == 0


# ---------- display-only station (UNO Q) ----------
def test_station_events_give_new_results_in_order_and_never_replay(world):
    database, s3, answer = world
    first = main.station_events(after=None)
    assert first["events"] == []                                     # no history on first call
    do_shipout(s3, order="ORD-1001")
    r, _ = do_return(s3, order="ORD-1001")
    out = main.station_events(after=first["cursor"])
    kinds = [(e["type"], e["order_id"]) for e in out["events"]]
    assert kinds == [("shipout", "ORD-1001"), ("return", "ORD-1001")]
    assert out["events"][1]["led"] == main.LED[r.decision]
    assert main.station_events(after=out["cursor"])["events"] == []  # same cursor: nothing new


def test_station_events_rejects_a_bad_cursor(world):
    with pytest.raises(HTTPException):
        main.station_events(after="not-a-date")


def test_station_cursor_has_no_plus_and_tolerates_a_decoded_plus(world):
    c = main.station_events(after=None)["cursor"]
    assert c.endswith("Z") and "+" not in c
    assert main.station_events(after="2026-11-15T05:43:39.114680 00:00")["events"] == []   # "+" sent unencoded


# ---------------------------------------------------------------- test-set regressions (Nov 14)
def _cheap_shipout(s3, serial="SN00000001", weight=260):
    do_shipout(s3, order="ORD-1005", weight=weight, serial=serial)        # headphones, $149


def test_phone_missing_a_third_of_its_weight_is_not_instant(world):
    _, s3, answer = world
    _cheap_shipout(s3, weight=340)
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": None, "serial_read": "SN00000001"})
    r, _ = do_return(s3, order="ORD-1005", weight=230)
    assert r.decision != "GREEN" and any(x.startswith("WEIGHT_MISMATCH") for x in r.reasons)


def test_new_damage_is_never_instant(world):
    _, s3, answer = world
    _cheap_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 261, "serial_read": "SN00000001",
                                                           "new_damage": ["tape across the top"], "grade": "B"})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "YELLOW" and "NEW_DAMAGE" in r.reasons


@pytest.mark.parametrize("shipped,read", [("T4AI12Z8", "THA1X12Z8"), ("BJPTUY", "BUPFTUY"), ("TYZ341A", "T112-341A")])
def test_honest_two_character_misreads_are_yellow_not_review(world, shipped, read):
    _, s3, answer = world
    _cheap_shipout(s3, serial=shipped)
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 261, "serial_read": read,
                                                           "label_codes": [read]})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "YELLOW" and "SERIAL_NEAR_MATCH" in r.reasons


@pytest.mark.parametrize("shipped,read", [("BMRUYTUJ", "DNXTTY2"), ("DNXTYZ", "TY12-341A")])
def test_real_tag_swaps_are_still_caught(world, shipped, read):
    _, s3, answer = world
    _cheap_shipout(s3, serial=shipped)
    answer["result"] = answer["result"].model_copy(update={"scale_reading_g": 261, "serial_read": read,
                                                           "label_codes": [read]})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision in ("RED", "REVIEW") and "SERIAL_MISMATCH" in r.reasons


def test_model_gets_the_shipout_photo_as_reference(world, monkeypatch):
    _, s3, answer = world
    seen = {}

    def fake_grade(item, serial_jpg, fp, code, ship_item_jpg=None):
        seen["ref"] = ship_item_jpg
        return answer["result"].model_copy(update={"scale_reading_g": 261, "serial_read": "SN00000001"}), "fake"
    monkeypatch.setattr(main.vision, "grade", fake_grade)
    _cheap_shipout(s3)
    do_return(s3, order="ORD-1005")
    assert seen["ref"] and seen["ref"][:2] == b"\xff\xd8"           # a JPEG: the sanitized ship-out photo


def test_prompt_with_reference_photo():
    from app.stages.vision import build_prompt
    with_ref = build_prompt({"product": "Headphones"}, "0000", with_reference=True)
    without = build_prompt({"product": "Headphones"}, "0000")
    assert "Photo 0" in with_ref and "tape, stickers or marks" in with_ref and "item_seen" in with_ref
    assert "Photo 0" not in without and "item_seen" in without


# ---------------------------------------------------------------- different-item regressions (Nov 15)
def test_model_says_different_object_at_80_percent_is_red(world):
    # Test set: headphones shipped, umbrella returned. Model: "blue folding umbrella", same_item=false, 0.8.
    _, s3, answer = world
    _cheap_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={
        "item_seen": "blue folding umbrella", "same_item": False, "same_unit": False, "confidence": 0.8,
        "serial_read": None, "label_codes": [], "scale_reading_g": 261})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "RED" and "DIFFERENT_ITEM" in r.reasons


def test_description_that_contradicts_same_item_is_not_instant(world):
    # Test set: phone shipped, power bank returned. Model: item_seen "white power bank" but same_item=true.
    _, s3, answer = world
    _cheap_shipout(s3)                                         # ORD-1005 is "Over-ear headphones"
    answer["result"] = answer["result"].model_copy(update={
        "item_seen": "white power bank", "serial_read": "SN00000001", "scale_reading_g": 261})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "YELLOW" and "ITEM_DESCRIPTION_MISMATCH" in r.reasons


def test_matching_description_stays_green(world):
    _, s3, answer = world
    _cheap_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={
        "item_seen": "white over-ear headphones", "serial_read": "SN00000001", "scale_reading_g": 261})
    assert do_return(s3, order="ORD-1005")[0].decision == "GREEN"


def test_describes_product_rules():
    assert main._describes_product("white over-ear headphones", "Headphones")
    assert main._describes_product("Power Bank", "Power bank")
    assert main._describes_product("silver laptop", "Laptop 16-inch")
    assert not main._describes_product("white power bank", "Phone")
    assert not main._describes_product("blue folding umbrella", "Over-ear headphones")
    assert main._describes_product("", "Phone") and main._describes_product("a mouse", None)
