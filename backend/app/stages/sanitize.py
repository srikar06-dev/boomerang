"""Sanitize an uploaded photo: fingerprint the original, then re-encode a clean copy.

- SHA-256 of the ORIGINAL bytes goes in the evidence pack (proves what was uploaded).
- Re-encoding to a fresh JPEG drops EXIF/GPS and anything hidden after the image data.
- The perceptual hash (pHash) lets us spot the same picture being used twice.
"""
import hashlib
import io
from dataclasses import dataclass

import imagehash
from PIL import Image, ImageOps

MAX_SIDE = 1280
MAX_PIXELS = 40_000_000           # refuse "decompression bomb" images
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}   # MPO = what some phones call a JPEG
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class BadImage(Exception):
    """Not an image we accept."""


@dataclass
class Sanitized:
    jpeg: bytes          # clean copy: what the vision model sees
    sha256: str          # of the original upload
    phash: str           # 16 hex chars
    width: int
    height: int


def sanitize(original: bytes) -> Sanitized:
    try:
        probe = Image.open(io.BytesIO(original))
        if probe.format not in ALLOWED_FORMATS:
            raise BadImage(f"format {probe.format}")
        probe.verify()                                   # catches truncated / corrupt files
        img = Image.open(io.BytesIO(original))           # verify() leaves the object unusable
        img = ImageOps.exif_transpose(img).convert("RGB")
    except BadImage:
        raise
    except Exception as e:                               # includes DecompressionBombError
        raise BadImage(type(e).__name__) from None
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)             # no exif= argument, so none is written
    return Sanitized(jpeg=out.getvalue(), sha256=hashlib.sha256(original).hexdigest(),
                     phash=str(imagehash.phash(img)), width=img.width, height=img.height)
