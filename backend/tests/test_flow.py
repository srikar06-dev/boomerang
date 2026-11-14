"""End-to-end flow with stand-ins for MongoDB, S3 and the vision model. No network needed.

ship-out (staff) -> return session -> upload -> /return -> decision
"""
import io

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw

from app import config, main, seed
from app.models import ReturnRequest, SessionRequest, ShipoutRequest, UploadUrlRequest
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
    answer = {"result": VisionResult(same_item=True, same_unit=True, confidence=0.95, code_visible=True,
                                     scale_reading_g=1400, serial_read="SN-0000 0001", grade="A")}
    monkeypatch.setattr(main.vision, "grade", lambda *a, **k: (answer["result"], "fake-model"))
    return database, s3, answer


def upload(s3, token, pics):
    for slot, data in zip(("item", "serial"), pics):
        r = main.upload_url(UploadUrlRequest(token=token, slot=slot))
        s3.objects[r.key] = data


def do_shipout(s3, order="ORD-1001", weight=1400, serial="SN00000001", pics=None):
    s = main.create_session(SessionRequest(order_id=order, purpose="shipout"), x_station_key=KEY)
    upload(s3, s.token, pics or (photo(1), photo(2)))
    return main.shipout(ShipoutRequest(token=s.token, weight_g=weight, serial=serial))


def do_return(s3, order="ORD-1001", pics=None, weight=None):
    s = main.create_session(SessionRequest(order_id=order))
    upload(s3, s.token, pics or (photo(3), photo(4)))
    return main.submit_return(ReturnRequest(token=s.token, weight_g=weight)), s


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


def test_missing_code_goes_to_review(world):
    _, s3, answer = world
    do_shipout(s3)
    answer["result"] = answer["result"].model_copy(update={"code_visible": False})
    assert do_return(s3)[0].decision == "REVIEW"


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
