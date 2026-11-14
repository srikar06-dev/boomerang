"""Local OpenCV cross-check: same object scores high, a different object scores low, and the
policy only ever moves a return to REVIEW on this signal."""
import io

import numpy as np
from PIL import Image, ImageEnhance

from app.stages import visual_match
from app.stages.policy import GREEN, RED, REVIEW, YELLOW, decide
from app.stages.risk import Signals, score


def textured(seed: int, size=(900, 700)) -> Image.Image:
    """A detailed synthetic 'product': random blocks and lines, unique per seed."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (size[1] // 12, size[0] // 12, 3), dtype=np.uint8)
    img = Image.fromarray(small).resize(size, Image.NEAREST)
    arr = np.array(img)
    for _ in range(40):
        y, x = rng.integers(0, size[1] - 1), rng.integers(0, size[0] - 60)
        arr[y:y + 3, x:x + 60] = rng.integers(0, 255, 3)
    return Image.fromarray(arr)


def jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=85)
    return out.getvalue()


def reshot(img: Image.Image) -> Image.Image:
    """Same object photographed again: slightly rotated, shifted and darker."""
    moved = img.rotate(4, expand=False, fillcolor=(255, 255, 255)).crop((15, 10, img.width - 5, img.height - 12))
    return ImageEnhance.Brightness(moved).enhance(0.85)


def test_same_object_matches():
    item, serial = textured(1), textured(2)
    m = visual_match.compare(jpeg(item), jpeg(serial), jpeg(reshot(item)), jpeg(reshot(serial)))
    assert not m.looks_different
    assert m.score >= 0.5


def test_different_object_does_not_match():
    m = visual_match.compare(jpeg(textured(1)), jpeg(textured(2)), jpeg(textured(3)), jpeg(textured(4)))
    assert m.looks_different


def test_bad_bytes_give_zero_not_crash():
    m = visual_match.compare(b"not a jpeg", b"", jpeg(textured(1)), jpeg(textured(2)))
    assert m.score == 0 and m.looks_different


def _decide(visual_disagrees, **kw):
    args = dict(shipout_weight_g=1000, return_weight_g=1000, same_unit_confidence=0.95,
                serial_match=True, price_usd=50)
    s = Signals(**{**args, **kw})
    return decide(score(s), model_ok=True, model_confidence=0.9, code_visible=True,
                  image_reused=False, price_usd=50, visual_disagrees=visual_disagrees)


def test_visual_disagreement_sends_green_to_review():
    assert _decide(False)[0] == GREEN
    decision, reasons = _decide(True)
    assert decision == REVIEW and "VISUAL_MISMATCH" in reasons


def test_visual_never_overrides_red():
    assert _decide(True, serial_match=False)[0] == RED   # hard red stays red


def test_visual_moves_yellow_to_review():
    assert _decide(False, same_unit_confidence=0.4)[0] == YELLOW    # doubtful unit match -> YELLOW
    assert _decide(True, same_unit_confidence=0.4)[0] == REVIEW
