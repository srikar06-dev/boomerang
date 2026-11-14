"""Unit tests for the decision rules. No network needed:  pytest -q"""
from app.stages.policy import GREEN, RED, REVIEW, YELLOW, decide
from app.stages.risk import Signals, score, unit_confidence, weight_term


def run(price=50.0, model_conf=0.9, code=True, reused=False, **kw):
    s = Signals(**{"shipout_weight_g": 1000, "return_weight_g": 1000, "same_unit_confidence": 0.95,
                   "serial_match": True, "price_usd": price, **kw})
    return decide(score(s), model_ok=True, model_confidence=model_conf,
                  code_visible=code, image_reused=reused, price_usd=price)[0]


def test_weight_tolerance():
    assert weight_term(1000, 1100) == 0.0          # within max(150 g, 15%)
    assert weight_term(1000, 400) == 1.0           # 60% off -> full
    assert 0 < weight_term(1000, 700) < 1


def test_honest_return_is_green():
    assert run() == GREEN


def test_empty_box_is_red():
    assert run(return_weight_g=200) == RED


def test_serial_swap_is_red():
    assert run(serial_match=False) == RED


def test_model_unsure_goes_to_review():
    assert run(model_conf=0.3) == REVIEW


def test_missing_code_goes_to_review():
    assert run(code=False) == REVIEW


def test_reused_image_goes_to_review():
    assert run(reused=True) == REVIEW


def test_expensive_item_never_instant():
    assert run(price=450) == YELLOW


def test_sensor_alone_only_reviews():
    assert run(sensor_distance=0.9) == REVIEW


def test_missing_return_weight_is_never_instant():
    assert run(return_weight_g=None) == REVIEW


def test_unreadable_serial_is_never_instant():
    assert run(serial_match=None) == YELLOW


def test_item_without_serial_can_be_green():
    assert run(serial_match=None, serial_expected=False) == GREEN


def test_unit_confidence_flips_when_model_says_different():
    assert unit_confidence(True, True, 0.9) == 0.9
    assert abs(unit_confidence(True, False, 0.9) - 0.1) < 1e-9
    assert abs(unit_confidence(False, True, 0.9) - 0.1) < 1e-9


def test_model_says_different_unit_is_never_green():
    for conf in (0.6, 0.7, 0.8, 0.9, 1.0):
        got = run(same_unit_confidence=unit_confidence(True, False, conf), serial_match=None)
        assert got in (YELLOW, RED), (conf, got)
    assert run(same_unit_confidence=unit_confidence(True, False, 0.9), serial_match=None) == RED


def test_vision_reply_parsing_handles_fences_and_chatter():
    import json as _json

    import pytest as _pytest

    from app.stages.vision import VisionResult, _json_object
    body = '{"same_item": true, "same_unit": false, "confidence": 0.8, "grade": "B"}'
    for reply in (body, f"```json\n{body}\n```", f"Here is my answer:\n{body}\nThanks."):
        r = VisionResult(**_json.loads(_json_object(reply)))
        assert r.same_unit is False and r.grade == "B"
    with _pytest.raises(_json.JSONDecodeError):
        _json_object("I cannot see the item.")
