"""Unit tests for the decision rules. No network needed:  pytest -q"""
from app.stages.policy import GREEN, RED, REVIEW, YELLOW, decide
from app.stages.risk import Signals, score, weight_term


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
