"""Task 3: check the vision prompt on real photo pairs before trusting it in the loop.

One pair (prints Nova's JSON, time, tokens and cost):
    python scripts/vision_test.py ITEM.jpg SERIAL.jpg [--product "Over-ear headphones"]
                                  [--weight 262] [--serial SN48213377] [--code 4821]

A whole folder (scores against the Task 3 targets):
    python scripts/vision_test.py --dir data/vision_set

    data/vision_set/cases.csv   columns: case,product,weight_g,serial
    data/vision_set/<case>/item.jpg  and  serial.jpg

Targets: valid JSON on 5/5, scale within 100 g on 4/5+, serial correct on 4/5+.
Uses the same sanitize step and prompt as the API. Model from BEDROCK_MODEL_ID in .env.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402  (loads .env)
from app.stages import vision  # noqa: E402
from app.stages.sanitize import sanitize  # noqa: E402

WEIGHT_TOL_G = 100


def norm(serial):
    return re.sub(r"[^A-Z0-9]", "", (serial or "").upper()) or None


def find(folder: Path, stem: str) -> Path:
    for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
        if (folder / f"{stem}{ext}").is_file():
            return folder / f"{stem}{ext}"
    raise FileNotFoundError(f"{folder / stem}.jpg is missing")


def check(item: Path, serial: Path, product: str, weight, expected_serial, code: str) -> dict:
    jpgs = [sanitize(p.read_bytes()).jpeg for p in (item, serial)]
    fingerprint = {"product": product, "defects": [], "grade": "A"}
    result, model = vision.grade(jpgs[0], jpgs[1], fingerprint, code)
    out = {"model": model, "json_ok": result is not None, "usage": dict(vision.last_usage) if result else {}}
    if result is None:
        return out
    out["result"] = result.model_dump()
    if weight is not None:
        got = result.scale_reading_g
        out["weight_ok"] = got is not None and abs(got - weight) <= WEIGHT_TOL_G
    if expected_serial:
        out["serial_ok"] = norm(result.serial_read) == norm(expected_serial)
    return out


def show(name: str, r: dict, weight, expected_serial) -> None:
    if not r["json_ok"]:
        print(f"{name}: FAILED - no valid JSON after retries and fallback ({r['model']})")
        return
    res, u = r["result"], r["usage"]
    cost = f"${u['cost_usd']:.5f}" if u.get("cost_usd") is not None else "cost n/a"
    print(f"{name}: {r['model']}  {u.get('seconds', '?')} s  {u.get('input_tokens', '?')}+{u.get('output_tokens', '?')} tokens  {cost}")
    if weight is not None:
        print(f"   scale  read {res['scale_reading_g']} g, expected {weight} g  -> {'PASS' if r['weight_ok'] else 'FAIL'}")
    if expected_serial:
        print(f"   serial read {res['serial_read']!r}, expected {expected_serial!r}  -> {'PASS' if r['serial_ok'] else 'FAIL'}")
    print(f"   same_item={res['same_item']} same_unit={res['same_unit']} conf={res['confidence']} "
          f"grade={res['grade']} damage={res['new_damage']}  notes: {res['notes']}")


def number(text):
    text = (text or "").strip()
    return float(text) if text else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", nargs="?")
    ap.add_argument("serial", nargs="?")
    ap.add_argument("--product", default="unknown product")
    ap.add_argument("--weight", type=float)
    ap.add_argument("--serial", dest="expected_serial")
    ap.add_argument("--code", default="0000")
    ap.add_argument("--dir", type=Path, help="folder with cases.csv and one subfolder per case")
    ap.add_argument("--json", action="store_true", help="also print the full JSON")
    args = ap.parse_args()
    print(f"Model: {config.BEDROCK_MODEL_ID} (fallback {config.BEDROCK_FALLBACK_ID})")

    if not args.dir:
        if not (args.item and args.serial):
            sys.exit(__doc__)
        r = check(Path(args.item), Path(args.serial), args.product, args.weight, args.expected_serial, args.code)
        show("pair", r, args.weight, args.expected_serial)
        if args.json and r["json_ok"]:
            print(json.dumps(r["result"], indent=2))
        return

    rows = list(csv.DictReader((args.dir / "cases.csv").open(newline="")))
    results = []
    for row in rows:
        folder = args.dir / row["case"]
        weight, ser = number(row.get("weight_g")), (row.get("serial") or "").strip() or None
        try:
            r = check(find(folder, "item"), find(folder, "serial"), row.get("product") or "unknown product",
                      weight, ser, args.code)
        except Exception as e:
            print(f"{row['case']}: ERROR {type(e).__name__}: {e}")
            continue
        show(row["case"], r, weight, ser)
        results.append(r)

    n = len(results)
    json_ok = sum(r["json_ok"] for r in results)
    w = [r["weight_ok"] for r in results if "weight_ok" in r]
    s = [r["serial_ok"] for r in results if "serial_ok" in r]
    costs = [r["usage"]["cost_usd"] for r in results if r["usage"].get("cost_usd") is not None]
    print(f"\nValid JSON      {json_ok}/{n}   (target {n}/{n})")
    print(f"Scale +-{WEIGHT_TOL_G} g    {sum(w)}/{len(w)}   (target 4/5 or better)")
    print(f"Serial correct  {sum(s)}/{len(s)}   (target 4/5 or better)")
    if costs:
        print(f"Avg cost/check  ${sum(costs) / len(costs):.5f}  (target < $0.01)")


if __name__ == "__main__":
    main()
