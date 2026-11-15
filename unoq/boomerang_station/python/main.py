# Boomerang counter station - Arduino UNO Q, Linux side.
# Asks the Boomerang backend "anything new?" every couple of seconds and lights the result
# on the board (the sketch does the matrix, LEDs and buzzer). Photos are taken on a phone
# with the Capture page, so this board needs no camera and no USB hub.
#
# Fill in the two values below ON THE BOARD ONLY (in App Lab). Never commit the station key.
import json
import time
import urllib.parse
import urllib.request

from arduino.app_utils import App, Bridge

API_URL = "https://YOUR-BACKEND-ADDRESS"   # tunnel URL, or http://<laptop-ip>:8000 on the same Wi-Fi
STATION_KEY = ""                            # the STATION_KEY from the backend's .env
POLL_SECONDS = 2.0

CODE = {"L:G": 1, "L:Y": 2, "L:R": 3}      # same LED commands the backend already sends
READY, ERROR = 0, 4

cursor = None
failures = 0
showing_error = False


def get(path: str) -> dict:
    req = urllib.request.Request(API_URL.rstrip("/") + path,
                                 headers={"X-Station-Key": STATION_KEY, "User-Agent": "boomerang-unoq/1.0"})
    with urllib.request.urlopen(req, timeout=8) as res:
        return json.loads(res.read().decode())


def loop():
    global cursor, failures, showing_error
    try:
        query = "" if cursor is None else "?after=" + urllib.parse.quote(cursor)
        out = get("/station/events" + query)
        cursor = out["cursor"]
        failures = 0
        if showing_error:
            Bridge.call("show", READY)
            showing_error = False
            print("backend reachable again")
        for i, e in enumerate(out["events"]):
            if i:
                time.sleep(3)                      # several at once: show each for a moment
            Bridge.call("show", CODE.get(e["led"], 2))
            what = e["decision"] if e["type"] == "return" else ("ship-out OK" if e.get("pick_verified") is not False
                                                                else "ship-out after pick warning")
            print(f'{e["type"]:8} {e["order_id"]:10} {what}  {", ".join(e.get("reasons") or [])}')
    except Exception as exc:                       # network down, wrong key, backend restarting...
        failures += 1
        print(f"poll failed ({failures}): {exc}")
        if failures >= 3 and not showing_error:
            Bridge.call("show", ERROR)
            showing_error = True
    time.sleep(POLL_SECONDS)


if not STATION_KEY or "YOUR-BACKEND" in API_URL:
    print("Set API_URL and STATION_KEY at the top of main.py first.")
print(f"Boomerang station polling {API_URL}")
App.run(user_loop=loop)
