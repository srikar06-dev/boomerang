"""Boomerang counter station: webcam -> Boomerang API -> UNO R4 LED matrix.

Run from the repo root with the env active:
    python station/station.py                      # interactive: ship-out or return, webcam photos
    python station/station.py --no-uno             # without the Arduino plugged in
    python station/station.py --camera 2           # pick another webcam (0, 1, 2 ...)
    python station/station.py --photos item.jpg serial.jpg   # use files instead of the webcam

Settings come from .env: API_URL, SERIAL_PORT, STATION_KEY (optional: CAMERA_INDEX).
Flow (same calls as frontend/capture.js):
  POST /session -> show the 4-digit code -> photo 1 (item + scale + code) -> photo 2 (serial)
  -> POST /upload-url + PUT each JPEG -> POST /shipout or /return -> send `led` to the Uno.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyACM0")
STATION_KEY = os.environ.get("STATION_KEY", "")
CAPTURE_DIR = ROOT / "captures"          # git-ignored; keeps every photo for the test set

# 5-row block digits so the code is easy to read in the photo of the laptop screen.
BIG = {
    "0": ["█████", "█   █", "█   █", "█   █", "█████"], "1": ["  █  ", " ██  ", "  █  ", "  █  ", " ███ "],
    "2": ["█████", "    █", "█████", "█    ", "█████"], "3": ["█████", "    █", " ████", "    █", "█████"],
    "4": ["█   █", "█   █", "█████", "    █", "    █"], "5": ["█████", "█    ", "█████", "    █", "█████"],
    "6": ["█████", "█    ", "█████", "█   █", "█████"], "7": ["█████", "    █", "   █ ", "  █  ", "  █  "],
    "8": ["█████", "█   █", "█████", "█   █", "█████"], "9": ["█████", "█   █", "█████", "    █", "█████"],
}


def big(code: str) -> str:
    return "\n".join("   ".join(BIG[d][row] for d in code) for row in range(5))


# ---------------------------------------------------------------- Uno (optional)
class Uno:
    def __init__(self, port: str | None):
        self.ser = None
        if not port:
            return
        try:
            import serial
            self.ser = serial.Serial(port, 9600, timeout=2)
            time.sleep(1.5)                       # let the board settle after the port opens
            self.ser.reset_input_buffer()
            print(f"Uno connected on {port}")
        except Exception as e:
            print(f"!! Uno not available on {port} ({e}). Continuing without LEDs.")

    def led(self, cmd: str) -> None:
        if not self.ser:
            print(f"(LED {cmd})")
            return
        self.ser.write((cmd + "\n").encode())
        reply = self.ser.readline().decode(errors="ignore").strip()
        print(f"Uno: {reply or 'no reply'}")


# ---------------------------------------------------------------- camera
def _label(img, text, y, color):
    import cv2
    cv2.putText(img, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 5, cv2.LINE_AA)   # outline
    cv2.putText(img, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)


def _fit(img, max_w=1280):
    """Scales a frame down for the screen only; the saved photo keeps full resolution."""
    import cv2
    h, w = img.shape[:2]
    return img if w <= max_w else cv2.resize(img, (max_w, int(h * max_w / w)))


def snap(camera_index: int, name: str, hint: str) -> bytes:
    """Live preview window: SPACE = take photo, then Y = keep / N = retake. Q = cancel this check."""
    import cv2
    print(f"\n[{name}] {hint}\n  Camera window: SPACE = take photo, Q = cancel")
    cam = cv2.VideoCapture(camera_index)
    if not cam.isOpened():
        raise RuntimeError(f"Camera {camera_index} not found. Try --camera 2, or use --photos.")
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    win = f"Boomerang - {name} photo"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    raise RuntimeError("Cancelled")
                continue
            view = _fit(frame.copy())
            _label(view, f"{name.upper()} - SPACE: take photo   Q: cancel", 40, (0, 255, 0))
            cv2.imshow(win, view)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                raise RuntimeError("Cancelled")
            if key != 32:                          # 32 = SPACE
                continue
            still = _fit(frame.copy())
            _label(still, "Y: keep this photo    N: retake", 40, (0, 200, 255))
            cv2.imshow(win, still)
            while (k := cv2.waitKey(0) & 0xFF) not in (ord("y"), ord("n"), ord("q"), 13):
                pass
            if k == ord("q"):
                raise RuntimeError("Cancelled")
            if k in (ord("y"), 13):                # Y or Enter keeps it
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                CAPTURE_DIR.mkdir(exist_ok=True)
                path = CAPTURE_DIR / f"{datetime.now():%H%M%S}_{name}.jpg"
                path.write_bytes(jpg.tobytes())
                h, w = frame.shape[:2]
                print(f"  saved {path.name} ({w}x{h})")
                return jpg.tobytes()
    finally:
        cam.release()
        cv2.destroyWindow(win)
        cv2.waitKey(1)                             # lets the window actually close


# ---------------------------------------------------------------- API
def call(method: str, path: str, staff: bool = False, **kw) -> dict:
    headers = {"X-Station-Key": STATION_KEY} if staff else {}
    try:
        r = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=60, **kw)
    except requests.ConnectionError:
        sys.exit(f"Cannot reach the API at {API_URL}. Is uvicorn running? Is API_URL right in .env?")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:200]
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {detail}")
    return r.json()


def upload(token: str, slot: str, jpeg: bytes) -> None:
    info = call("POST", "/upload-url", json={"token": token, "slot": slot})
    url = info["url"]
    if url.startswith("/"):                     # LOCAL_MODE returns a same-server path, not an S3 URL
        url = API_URL + url
    put = requests.put(url, data=jpeg,
                       headers={"Content-Type": info.get("content_type", "image/jpeg")}, timeout=60)
    if put.status_code >= 300:
        raise RuntimeError(f"S3 upload for '{slot}' failed: {put.status_code} {put.text[:200]}")
    print(f"  uploaded {slot} ({len(jpeg) // 1024} KB)")


def ask_choice(prompt: str, choices: dict[str, str], default: str | None = None) -> str:
    """Asks until the answer is one of the keys (first letter, any case). Enter = default, if any."""
    while True:
        raw = input(prompt).strip().lower()
        if not raw and default is not None:
            return choices[default]
        if raw[:1] in choices and (len(raw) == 1 or raw in ("yes", "no", "ship", "return", "quit")):
            return choices[raw[:1]]
        print(f"  Please answer {' / '.join(choices)}" + (" (Enter = default)" if default else "") + ".")


def ask_float(prompt: str) -> float | None:
    raw = input(prompt).strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        print("  Not a number, leaving it empty.")
        return None


def new_item() -> str:
    """Registers one of our own items (product + order) and returns its new order ID (ORD-2001, ...)."""
    name = ""
    while not name:
        name = input("  Item name (e.g. Anker charger): ").strip()[:60]
    price = None
    while price is None:
        price = ask_float("  Price in USD: ")
    print("  Where is the serial?  d = on the device itself (printed serial/IMEI, or a BMR- tag stuck on it)")
    print("                        b = only on the box/packaging label")
    print("                        n = nowhere (no serial)")
    unit_id = ask_choice("  [D/b/n]: ", {"d": "device", "b": "box", "n": "none"}, default="d")
    sealed = ask_choice("  Factory-sealed consumable (cream, cosmetics, packaged food)? [y/N]: ",
                        {"y": "yes", "n": "no"}, default="n") == "yes"
    out = call("POST", "/orders", staff=True,
               json={"name": name, "price_usd": price, "unit_id": unit_id, "sealed_consumable": sealed})
    print(f"  Created order {out['order_id']} for '{name}' (${price:g}, serial: {out['unit_id']}"
          f"{', sealed' if out['sealed_consumable'] else ''}). Use this ID for the return later.")
    return out["order_id"]


# ---------------------------------------------------------------- one check
def run_once(args, uno: Uno) -> None:
    purpose = ask_choice("\nShip-out or return? [s/r] (q to quit): ",
                         {"s": "shipout", "r": "return", "q": "quit"})
    if purpose == "quit":
        raise KeyboardInterrupt
    if purpose == "shipout":
        order_id = input("Order ID (e.g. ORD-1010), or press Enter to add a NEW item: ").strip().upper()
        if not order_id:
            order_id = new_item()
    else:
        order_id = input("Order ID (e.g. ORD-1010): ").strip().upper()

    session = call("POST", "/session", staff=(purpose == "shipout"),
                   json={"order_id": order_id, "purpose": purpose})
    token, code = session["token"], session["code"]
    if session.get("code_required"):
        print(f"\n{purpose.upper()} {order_id} - put this code in photo 1:\n\n{big(code)}\n\n   CODE {code}\n")
    else:
        print(f"\n{purpose.upper()} {order_id}")

    if args.photos:
        item, serial_photo = (Path(p).read_bytes() for p in args.photos)
    else:
        item = snap(args.camera, "item", "Item ON the scale with the scale display in view" + (" AND the code on screen." if session.get("code_required") else "."))
        serial_photo = snap(args.camera, "serial", "Close-up of the serial label (fill at least 1/3 of the frame).")

    upload(token, "item", item)
    upload(token, "serial", serial_photo)

    started = time.time()
    if purpose == "shipout":
        ship_anyway, suggestion = False, None
        print("Checking the pick (is this the ordered product?)...")
        try:
            check = call("POST", "/shipout/check", staff=True, json={"token": token})
        except RuntimeError as e:
            check = {}
            print(f"  !! pick check failed ({e}) - continuing without it")
        if check.get("product_match") is False:
            uno.led("L:Y")
            print(f"\n  !! WRONG ITEM? This order is for: {check.get('product_name')}")
            print(f"     Model says: {check.get('notes')}")
            if input("  Ship anyway? [y/N]: ").strip().lower() != "y":
                print("Not shipped. Pick the right item and start the ship-out again.")
                return
            ship_anyway = True
        elif check.get("product_match"):
            print(f"  OK - looks like {check.get('product_name')}.")
        if check.get("sealed_consumable") and check.get("seal_intact") is not True:
            print("  !! Sealed product, but the seal is not clearly intact in photo 1 - check it before shipping.")
        for d in check.get("defects") or []:
            print(f"  note: existing damage recorded: {d}")
        suggestion = check.get("serial_suggestion")
        weight = ask_float("Scale reading in grams (Enter to skip): ")
        if check.get("unit_id") == "none":
            serial_text = None                     # this product has no serial: nothing to ask
        elif suggestion:
            typed = input(f"Serial number [{suggestion}] (Enter = accept, '-' = none, or type it): ").strip()
            serial_text = None if typed == "-" else (typed or suggestion)
        else:
            serial_text = input("Serial number as printed (Enter to skip): ").strip() or None
        out = call("POST", "/shipout", staff=True,
                   json={"token": token, "weight_g": weight, "serial": serial_text, "ship_anyway": ship_anyway})
        print(f"\nShip-out saved for {out['order_id']}" + (" (shipped anyway - recorded)." if ship_anyway else "."))
        uno.led("L:G")
        return

    weight = ask_float("Typed backup weight in grams (Enter = read it from the photo): ")
    body = {"token": token, "weight_g": weight}
    if args.label:
        body["label"] = args.label
    try:
        res = call("POST", "/return", staff=bool(args.label), json=body)
    except RuntimeError as e:
        print(f"\n!! {e}\n-> treat as REVIEW")
        uno.led("L:Y")
        return
    uno.led(res["led"])
    print(f"\nDECISION: {res['decision']}   risk {res['risk_score']}   ({time.time() - started:.1f} s)")
    for reason in res.get("reasons") or ["no flags"]:
        print(f"  - {reason}")
    plan = res.get("disposition") or {}
    if plan:
        print(f"  disposition: {plan.get('action')}")


def main() -> None:
    p = argparse.ArgumentParser(description="Boomerang counter station")
    p.add_argument("--camera", type=int, default=int(os.environ.get("CAMERA_INDEX", 0)))
    p.add_argument("--no-uno", action="store_true", help="run without the Arduino")
    p.add_argument("--photos", nargs=2, metavar=("ITEM", "SERIAL"), help="use two files instead of the webcam")
    p.add_argument("--label", choices=["honest", "fraud"], help="test set only: tag returns for /stats")
    args = p.parse_args()

    if not STATION_KEY:
        print("!! STATION_KEY is empty in .env - ship-outs will be refused.")
    print(f"API: {API_URL}")
    uno = Uno(None if args.no_uno else SERIAL_PORT)
    try:
        while True:
            try:
                run_once(args, uno)
            except RuntimeError as e:
                print(f"\n!! {e}")
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")


if __name__ == "__main__":
    main()
