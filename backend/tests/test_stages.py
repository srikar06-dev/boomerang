"""Sanitize, authenticity and disposition. No network needed."""
import io

import pytest
from PIL import Image

from app.stages import authenticity, disposition
from app.stages.sanitize import BadImage, sanitize


def jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (3000, 2000), "navy")
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"          # Make
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_sanitize_strips_exif_and_shrinks():
    original = jpeg_with_exif()
    assert b"SecretPhoneMaker" in original
    clean = sanitize(original)
    assert b"SecretPhoneMaker" not in clean.jpeg
    assert max(clean.width, clean.height) == 1280
    assert len(clean.sha256) == 64 and len(clean.phash) == 16


def test_sanitize_drops_trailing_payload():
    clean = sanitize(jpeg_with_exif() + b"<script>alert(1)</script>")
    assert b"<script>" not in clean.jpeg


@pytest.mark.parametrize("bad", [b"", b"hello", b"GIF89a" + b"\x00" * 50, b"\xff\xd8\xff\xe0" + b"\x00" * 20])
def test_sanitize_rejects_non_images(bad):
    with pytest.raises(BadImage):
        sanitize(bad)


def test_resaved_copy_counts_as_reused():
    a = sanitize(jpeg_with_exif())
    again = sanitize(a.jpeg)                   # re-encoded: different bytes, same picture
    assert a.sha256 != again.sha256
    assert authenticity.is_reused(again.sha256, again.phash, set(), [a.phash])
    assert authenticity.is_reused(a.sha256, a.phash, {a.sha256}, [])


def test_bad_stored_hash_is_ignored():
    a = sanitize(jpeg_with_exif())
    assert not authenticity.is_reused(a.sha256, a.phash, set(), ["not-hex", ""])


RESALE = {"A": 110, "B": 80, "C": 45, "D": 10}


def test_disposition_by_grade():
    assert disposition.choose("A", RESALE, "GREEN")["action"] == "RESTOCK"
    assert disposition.choose("B", RESALE, "YELLOW")["action"] == "RESELL_OPEN_BOX"
    assert disposition.choose("C", RESALE, "GREEN")["action"] == "REFURBISH"
    d = disposition.choose("D", RESALE, "GREEN")
    assert d["action"] == "RESELL_LOCALLY" and d["ship_back"] is False


def test_cheap_item_is_not_shipped_back():
    d = disposition.choose("B", {"A": 18, "B": 10, "C": 4, "D": 0}, "GREEN")   # water bottle
    assert d["ship_back"] is False


def test_held_returns_get_no_disposition():
    for decision in ("RED", "REVIEW"):
        assert disposition.choose("A", RESALE, decision)["action"] == "HOLD_FOR_REVIEW"
    assert disposition.choose(None, RESALE, "GREEN")["action"] == "HOLD_FOR_REVIEW"
