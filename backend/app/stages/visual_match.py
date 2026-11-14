"""Visual cross-check (local OpenCV, no cloud, $0): does the returned unit look like the shipped one?

Compares the ship-out photos with the return photos using ORB keypoints + RANSAC geometry:
a real match needs many keypoints that agree on ONE consistent transform, which random
look-alikes and different objects rarely produce.

Why not compare the whole item photo? Ship-out and return photos share the rig background
(scale, laptop screen), which would "match" even when the item was swapped. So we compare
  - the SERIAL close-up (photo 2): label texture is specific to the product, and
  - the CENTRE of the item photo (photo 1), where the item sits on the scale.

This is EVIDENCE ONLY. The policy may move a return to REVIEW when this disagrees with the
vision model; it never approves or rejects on its own. Thresholds must be calibrated on real
rig photos: run  python scripts/visual_test.py SHIP.jpg RETURN.jpg  on same/different pairs.
"""
from dataclasses import dataclass

import cv2
import numpy as np

ORB_FEATURES = 1500
RATIO = 0.75            # Lowe's ratio test: keep a match only if clearly better than the 2nd best
RANSAC_PX = 5.0         # reprojection error allowed for an inlier, in pixels (at 1280 px max side)
INLIERS_FULL = 40       # this many geometric inliers counts as a confident match (score 1.0)
CENTER_KEEP = 0.6       # keep the middle 60% of the item photo (drops most of the rig background)

MATCH_LOW = 0.5         # below this (20 inliers), the photos do NOT look like the same unit. Calibrate on rig photos!


@dataclass
class VisualMatch:
    score: float                 # 0..1, best of the two comparisons
    item_inliers: int
    serial_inliers: int

    @property
    def looks_different(self) -> bool:
        return self.score < MATCH_LOW


def _gray(jpeg: bytes) -> np.ndarray | None:
    try:
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    except cv2.error:                     # empty or garbage bytes
        return None
    if img is None:
        return None
    return cv2.equalizeHist(img)          # evens out lighting differences between the two shots


def _center(img: np.ndarray, keep: float = CENTER_KEEP) -> np.ndarray:
    h, w = img.shape[:2]
    dh, dw = int(h * (1 - keep) / 2), int(w * (1 - keep) / 2)
    return img[dh:h - dh, dw:w - dw]


def inliers(a: np.ndarray | None, b: np.ndarray | None) -> int:
    """Number of ORB matches that agree on one homography between images a and b."""
    if a is None or b is None:
        return 0
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return 0
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
    if len(good) < 8:
        return 0
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    _, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_PX)
    return int(mask.sum()) if mask is not None else 0


def compare(ship_item: bytes, ship_serial: bytes, ret_item: bytes, ret_serial: bytes) -> VisualMatch:
    """All four inputs are sanitized JPEG bytes (same pipeline, same size limits)."""
    a, b = _gray(ship_item), _gray(ret_item)
    item = inliers(_center(a) if a is not None else None, _center(b) if b is not None else None)
    serial = inliers(_gray(ship_serial), _gray(ret_serial))
    score = min(1.0, max(item, serial) / INLIERS_FULL)
    return VisualMatch(score=round(score, 3), item_inliers=item, serial_inliers=serial)
