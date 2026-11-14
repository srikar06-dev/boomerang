"""Calibrate the OpenCV cross-check on REAL rig photos.

    python scripts/visual_test.py SHIP_ITEM.jpg SHIP_SERIAL.jpg RETURN_ITEM.jpg RETURN_SERIAL.jpg

Run it on ~5 pairs of the SAME unit and ~5 pairs of DIFFERENT units. Same-unit scores should be
well above MATCH_LOW and different-unit scores below it; adjust MATCH_LOW / INLIERS_FULL in
backend/app/stages/visual_match.py if they overlap.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.stages.sanitize import sanitize            # noqa: E402  (same pipeline as the API)
from app.stages.visual_match import MATCH_LOW, compare  # noqa: E402

if len(sys.argv) != 5:
    sys.exit(__doc__)
ship_item, ship_serial, ret_item, ret_serial = (sanitize(Path(p).read_bytes()).jpeg for p in sys.argv[1:])
m = compare(ship_item, ship_serial, ret_item, ret_serial)
print(f"score={m.score}  item_inliers={m.item_inliers}  serial_inliers={m.serial_inliers}  "
      f"-> {'DIFFERENT (review)' if m.looks_different else 'looks the same'}  (MATCH_LOW={MATCH_LOW})")
