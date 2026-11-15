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


def test_serial_swap_is_red(world):
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"serial_read": "SN99999999"})
    assert do_return(s3)[0].decision == "RED"


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
                             "honest_total": 1, "honest_flagged": 0}

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


# ---------------------------------------------------------------- serial misreads
def test_serial_near_miss_is_yellow_not_red(world):
    _, s3, answer = world
    do_shipout(s3, order="ORD-1005", weight=260, serial="BMR-UYTUJ")      # headphones, $149
    answer["result"] = answer["result"].model_copy(update={"serial_read": "BMR-VYTUJ", "scale_reading_g": 262})
    r, _ = do_return(s3, order="ORD-1005")
    assert r.decision == "YELLOW"
    assert any(x.startswith("SERIAL_NEAR_MATCH") for x in r.reasons)


def test_clearly_different_serial_is_still_red(world):
    _, s3, answer = world
    do_shipout(s3, order="ORD-1005", weight=260, serial="BMR-UYTUJ")
    answer["result"] = answer["result"].model_copy(update={"serial_read": "BMR-9DUHR", "scale_reading_g": 262})
    assert do_return(s3, order="ORD-1005")[0].decision == "RED"


def test_serial_compare_rules():
    assert main._compare_serial("sn-1234 5678", "SN12345678") == (True, None)
    assert main._compare_serial(None, "SN12345678") == (None, None)
    assert main._compare_serial("SN12345679", "SN12345678")[0] is None
    assert main._compare_serial("XQ99887766", "SN12345678") == (False, None)
    assert main._edit_distance("BMRUYTUJ", "BMRVYTUJ") == 1
