"""Runs the labelled test set through the real API and prints the metrics table for the judges.

Layout (data/ is ignored by git, so photos never land in the repo):

    data/test_set/cases.csv
    data/test_set/<case>/ship_item.jpg    ship_serial.jpg    ret_item.jpg    ret_serial.jpg

cases.csv columns (one row per return; use each order ID only once):

    case,order_id,label,ship_weight_g,return_weight_g,serial,note
    h01,ORD-1001,honest,1402,1398,SN12345678,laptop clean
    f01,ORD-1002,fraud,1395,310,SN22223333,laptop box with a book

label is honest or fraud. Weights are what the scale showed (leave blank if unknown);
return_weight_g is only a typed backup, the model's reading of the scale wins.

    python scripts/run_testset.py                   # uses API_URL and STATION_KEY from .env
    python scripts/run_testset.py --only f01 h03    # rerun a few cases

Each run re-seeds nothing: reset first with  python scripts/seed.py  for a clean scoreboard.
"""
import argparse
import csv
import io
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SET_DIR = ROOT / "data" / "test_set"
PHOTOS = {"ship": ("ship_item", "ship_serial"), "ret": ("ret_item", "ret_serial")}


def jpeg(path: Path) -> bytes:
    """Re-encode to JPEG (the upload link is signed for image/jpeg)."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def find_photo(folder: Path, stem: str) -> Path:
    for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
        if (folder / f"{stem}{ext}").is_file():
            return folder / f"{stem}{ext}"
    raise FileNotFoundError(f"{folder.name}/{stem}.jpg is missing")


def number(text: str):
    text = (text or "").strip()
    return float(text) if text else None


class Api:
    def __init__(self, base: str, key: str):
        self.base, self.key = base.rstrip("/"), key
        self.http = requests.Session()

    def post(self, path, body, staff=False):
        headers = {"X-Station-Key": self.key} if staff else {}
        r = self.http.post(self.base + path, json=body, headers=headers, timeout=90)
        if not r.ok:
            raise RuntimeError(f"{path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def upload_pair(self, token: str, files: list[Path]):
        for slot, path in zip(("item", "serial"), files):
            u = self.post("/upload-url", {"token": token, "slot": slot})
            url = u["url"] if u["url"].startswith("http") else self.base + u["url"]   # local mode gives a path
            put = self.http.put(url, data=jpeg(path), headers={"Content-Type": u["content_type"]}, timeout=60)
            if not put.ok:
                raise RuntimeError(f"upload {slot} -> {put.status_code}: {put.text[:200]}")


def run_case(api: Api, row: dict) -> dict:
    folder = SET_DIR / row["case"]
    ship = [find_photo(folder, s) for s in PHOTOS["ship"]]
    ret = [find_photo(folder, s) for s in PHOTOS["ret"]]

    s = api.post("/session", {"order_id": row["order_id"], "purpose": "shipout"}, staff=True)
    api.upload_pair(s["token"], ship)
    api.post("/shipout", {"token": s["token"], "weight_g": number(row.get("ship_weight_g")),
                          "serial": (row.get("serial") or "").strip() or None}, staff=True)

    s = api.post("/session", {"order_id": row["order_id"]})
    api.upload_pair(s["token"], ret)
    t0 = time.monotonic()
    r = api.post("/return", {"token": s["token"], "weight_g": number(row.get("return_weight_g")),
                             "label": row["label"]}, staff=True)
    r["seconds"] = round(time.monotonic() - t0, 1)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://localhost:8000"))
    ap.add_argument("--only", nargs="*", help="case names to run")
    args = ap.parse_args()
    key = os.environ.get("STATION_KEY", "")
    if not key:
        sys.exit("STATION_KEY is empty in .env")
    manifest = SET_DIR / "cases.csv"
    if not manifest.is_file():
        sys.exit(f"Missing {manifest.relative_to(ROOT)} - see the top of this file for the layout.")

    rows = list(csv.DictReader(manifest.open(newline="")))
    if args.only:
        rows = [r for r in rows if r["case"] in set(args.only)]
    bad = [r["case"] for r in rows if r.get("label") not in ("honest", "fraud")]
    if bad:
        sys.exit(f"label must be honest or fraud: {', '.join(bad)}")

    api = Api(args.api, key)
    results = []
    print(f"{'case':6} {'label':7} {'decision':8} {'risk':>5} {'secs':>5}  reasons")
    for row in rows:
        try:
            r = run_case(api, row)
            results.append((row, r))
            print(f"{row['case']:6} {row['label']:7} {r['decision']:8} {r['risk_score']:5.2f} {r['seconds']:5.1f}  "
                  f"{', '.join(r['reasons']) or '-'}")
        except Exception as e:      # keep going: one bad photo should not stop the whole set
            print(f"{row['case']:6} {row['label']:7} ERROR    {e}")

    fraud = [r for row, r in results if row["label"] == "fraud"]
    honest = [r for row, r in results if row["label"] == "honest"]
    caught = sum(r["decision"] != "GREEN" for r in fraud)
    flagged = sum(r["decision"] in ("RED", "REVIEW") for r in honest)
    instant_on_fraud = sum(r["decision"] == "GREEN" for r in fraud)
    secs = sorted(r["seconds"] for _, r in results)
    median = secs[len(secs) // 2] if secs else 0
    print("\n| Metric | Target | Result |\n| --- | --- | --- |")
    print(f"| Frauds caught (yellow, red or review) | >= 8 / 10 | {caught} / {len(fraud)} |")
    print(f"| Honest returns flagged (red or review) | <= 1 / 10 | {flagged} / {len(honest)} |")
    print(f"| Wrong instant refunds on fraud | 0 | {instant_on_fraud} |")
    print(f"| Median time for /return | < 20 s | {median} s |")
    print(f"\n{len(results)} of {len(rows)} cases ran. Errors above (if any) are not counted.")


if __name__ == "__main__":
    main()
