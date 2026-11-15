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

API_URL = "auto"   # "auto" = the backend running on this same board; or e.g. http://<laptop-ip>:8000
STATION_KEY = ""                            # the STATION_KEY from the backend's .env
POLL_SECONDS = 2.0

CODE = {"L:G": 1, "L:Y": 2, "L:R": 3}      # same LED commands the backend already sends
READY, ERROR = 0, 4

cursor = None
failures = 0
showing_error = False


def _gateway() -> str | None:
    """The host's address as seen from inside App Lab's container (default route gateway)."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts[1] == "00000000":                         # default route
                    g = int(parts[2], 16)
                    return ".".join(str((g >> s) & 255) for s in (0, 8, 16, 24))
    except OSError:
        pass
    return None


def find_backend() -> str:
    """API_URL, or with "auto" the first local address where the board's own backend answers."""
    if API_URL != "auto":
        return API_URL.rstrip("/")
    candidates = ["http://localhost:8000", "http://127.0.0.1:8000"]
    gw = _gateway()
    if gw:
        candidates.append(f"http://{gw}:8000")
    candidates += ["http://172.17.0.1:8000", "http://host.docker.internal:8000"]
    for base in candidates:
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as res:
                if res.status == 200:
                    print(f"backend found at {base}")
                    return base
        except Exception:
            continue
    raise ConnectionError("no backend answered at " + ", ".join(candidates))


base_url = None


def get(path: str) -> dict:
    global base_url
    if base_url is None:
        base_url = find_backend()
    req = urllib.request.Request(base_url + path,
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
            code = 5 if e.get("decision") == "REVIEW" else CODE.get(e["led"], 2)   # REVIEW = circle
            Bridge.call("show", code)
            what = e["decision"] if e["type"] == "return" else ("ship-out OK" if e.get("pick_verified") is not False
                                                                else "ship-out after pick warning")
            print(f'{e["type"]:8} {e["order_id"]:10} {what}  {", ".join(e.get("reasons") or [])}')
    except Exception as exc:                       # network down, wrong key, backend restarting...
        failures += 1
        if API_URL == "auto":
            globals()["base_url"] = None           # look for the backend again next time
        print(f"poll failed ({failures}): {exc}")
        if failures >= 3 and not showing_error:
            Bridge.call("show", ERROR)
            showing_error = True
    time.sleep(POLL_SECONDS)


if not STATION_KEY:
    print("Set STATION_KEY at the top of main.py first (same value as STATION_KEY in the backend's .env).")
print(f"Boomerang station polling {API_URL}")
App.run(user_loop=loop)
