"""Unit tests for the decision rules. No network needed:  pytest -q"""
from app.stages.policy import GREEN, RED, REVIEW, YELLOW, decide
from app.stages.risk import Signals, score, unit_confidence, weight_term


def run(price=50.0, model_conf=0.9, code=True, reused=False, **kw):
    s = Signals(**{"shipout_weight_g": 1000, "return_weight_g": 1000, "same_unit_confidence": 0.95,
                   "serial_match": True, "price_usd": price, **kw})
    return decide(score(s), model_ok=True, model_confidence=model_conf,
                  code_visible=code, image_reused=reused, price_usd=price)[0]


def test_weight_tolerance():
    assert weight_term(1000, 1060) == 0.0          # within max(10 g, 8%)
    assert weight_term(31, 33) == 0.0              # 2 g on a mousepad: within the 10 g floor
    assert weight_term(340, 230) > 0               # test set: phone missing a third used to pass
    assert weight_term(1000, 400) == 1.0           # 60% off -> full
    assert 0 < weight_term(1000, 700) < 1


def test_honest_return_is_green():
    assert run() == GREEN


def test_empty_box_is_red():
    assert run(return_weight_g=200) == RED


def test_serial_swap_is_red():
    assert run(serial_match=False) == REVIEW                      # serial alone: likely a misread
    assert run(serial_match=False, return_weight_g=200) == RED      # serial + weight: a real swap
    assert run(serial_match=False, same_unit_confidence=0.2) == RED  # serial + model says different


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


def test_prompt_never_reveals_the_recorded_serial_or_weight():
    from app.stages.vision import build_prompt
    text = build_prompt({"product": "Wireless mouse", "serial": "SN99887766", "weight_g": 95.0,
                         "defects": ["scuff on left side"]}, "4821")
    assert "Wireless mouse" in text and "scuff on left side" in text
    assert "SN99887766" not in text and "95" not in text


def test_prompt_mentions_code_only_when_required(monkeypatch):
    from app import config
    from app.stages.vision import build_prompt
    monkeypatch.setattr(config, "REQUIRE_CODE", False)
    assert "6093" not in build_prompt({}, "6093")
    monkeypatch.setattr(config, "REQUIRE_CODE", True)
    assert "6093" in build_prompt({}, "6093")


def test_cost_estimate():
    from app.stages.vision import estimate_cost
    assert estimate_cost("us.amazon.nova-lite-v1:0", 1_000_000, 0) == 0.06
    assert estimate_cost("us.amazon.nova-lite-v1:0", 3000, 150) == round((3000 * 0.06 + 150 * 0.24) / 1e6, 6)
    assert estimate_cost("us.amazon.nova-pro-v1:0", 3000, 150) is None


def test_profile_rules_only_lower_a_decision():
    from app.stages.policy import decide
    from app.stages.risk import RiskResult
    r = RiskResult(score=0.0, terms={"W": 0, "V": 0, "S": 0, "D": 0, "H": 0, "P": 0}, reasons=[], missing=[])
    base = dict(model_ok=True, model_confidence=0.9, code_visible=True, image_reused=False)
    assert decide(r, **base, price_usd=50, unit_provable=False)[0] == "YELLOW"
    assert decide(r, **base, price_usd=29, unit_provable=False)[0] == "GREEN"
    assert decide(r, **base, price_usd=10, seal_broken=True) == ("YELLOW", ["SEAL_BROKEN"])


def test_vision_reply_tolerates_common_nova_variations():
    from app.stages.vision import VisionResult
    r = VisionResult(**{"same_item": "true", "same_unit": True, "confidence": 95, "serial_read": "null",
                        "label_codes": None, "scale_reading_g": "81 g", "code_visible": "yes",
                        "new_damage": "none", "seal_intact": "unknown", "grade": "a", "notes": None})
    assert (r.same_item, r.confidence, r.serial_read, r.label_codes, r.scale_reading_g) == (True, 0.95, None, [], 81.0)
    assert (r.code_visible, r.new_damage, r.seal_intact, r.grade, r.notes) == (True, [], None, "A", "")
    r = VisionResult(**{"same_item": True, "same_unit": False, "confidence": "0.8",
                        "label_codes": "BMR-UYTUJ", "scale_reading_g": "unreadable", "grade": "excellent"})
    assert (r.label_codes, r.scale_reading_g, r.confidence, r.grade) == (["BMR-UYTUJ"], None, 0.8, "C")


def test_vision_reply_still_rejects_missing_core_fields():
    import pytest as _pytest
    from pydantic import ValidationError

    from app.stages.vision import VisionResult
    with _pytest.raises(ValidationError):
        VisionResult(**{"confidence": 0.9})                  # no same_item / same_unit: unusable
