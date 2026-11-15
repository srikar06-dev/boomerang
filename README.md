# Boomerang

AI return grading at the first touch, before return shipping is paid.
Built at SunHacks 9.0.

## Setup (macOS or Ubuntu)

```bash
git clone git@github.com:srikar06-dev/boomerang.git
cd boomerang
./install.sh --system     # first time on a laptop: OS tools + conda env + packages + .env
conda activate boomerang  # or: source .venv/bin/activate  (if you have no conda)
```

1. `install.sh` copies `.env.example` to `.env`. Fill in your values. **Never commit `.env`.**
2. Check every cloud service: `python scripts/check_setup.py`
3. Run the API: `uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000`
   and open http://localhost:8000/docs
4. Tests (no network): `pytest -q`

Rerun `./install.sh` whenever `backend/requirements.txt` changes. The conda env ignores
`~/.local` packages (`PYTHONNOUSERSITE=1`), so every laptop gets the same versions.

## Layout

| Folder | What |
| --- | --- |
| `backend/app/` | FastAPI app: `main.py`, `config.py`, `db.py` |
| `backend/app/stages/` | pipeline stages: `vision.py`, `risk.py`, `policy.py` |
| `backend/tests/` | `pytest` rule tests |
| `frontend/` | capture, review queue, dashboard pages |
| `station/` | counter-station script (webcam + Uno LEDs) |
| `firmware/` | `uno_leds/` (UNO R4 WiFi), `nano_sealed/` (Nano 33 BLE Sense Rev2) |
| `scripts/` | `check_setup.py`, seed data |
| `docs/` | notes, diagrams |

## Rules

- `git status` before every commit: `.env` must never appear.
- Python 3.11; versions pinned in `backend/requirements.txt`.
- Work on a branch (`git switch -c <name>`), push it, merge to `main` with a pull request.

## Return profiles

Set per product when you add a new item at ship-out (`station.py`, press Enter at "Order ID").

| Profile | Example | Return rule |
|---|---|---|
| Serial on the device (`device`) | headphones, laptop | serial + weight + photos prove the unit; can be GREEN |
| Serial only on the box (`box`) | Arduino in its own box | box label names the listing, not the unit: at $30+ held for inspection (YELLOW, `UNIT_NOT_VERIFIABLE`) |
| No serial (`none`) | bottle, bag | same as `box`; under $30 a fast refund is cheaper than an inspection |
| Sealed consumable | cream, cosmetics, food | seal not clearly intact: YELLOW `SEAL_BROKEN`, disposition `DISPOSE` (never restocked) |

At ship-out the station also checks the pick: if the photo is not the ordered product it shows a
warning (yellow LED) and asks "Ship anyway?"; an override is recorded on the order.

## Return policy shown to customers

Boomerang only changes *how fast* a refund is issued; the retailer's posted policy must say so.
US refund rules are mostly state law and the store's posted policy (Arizona: terms are valid when
conspicuously posted; restocking fees must be disclosed, A.R.S. § 44-1377). Our demo policy:

- Refunds on items of $30 or more that cannot be identified by a serial number are issued after a
  warehouse inspection, within 1-2 business days.
- Opened cosmetics, skincare and food cannot be resold (FDA: retailers must not distribute
  adulterated cosmetics). They are refunded after inspection and disposed of safely.
- Some returns are checked by a person. A refund is never denied automatically.
- Return photos are kept only as evidence for that return.
- No restocking fees.

Not legal advice: a real launch needs each state's posting rules (e.g. New York, California) reviewed.

## UNO Q counter station (phone camera + board lights)

No laptop at the counter: a **phone** takes the photos on the Capture page, the **Arduino UNO Q**
shows the verdict (8x13 matrix icon, LEDs, buzzer). The backend runs anywhere the board can reach.

```
phone (Capture page) --photos--> backend (FastAPI, Nova, S3, Mongo) <--"anything new?"-- UNO Q (Wi-Fi)
                                                                                        |- matrix: check / dash / cross
                                                                                        |- LEDs D8 green, D9 yellow, D10 red
                                                                                        '- buzzer D11
```

| UNO Q pin | Part |
| --- | --- |
| D8 → 220 Ω → RGB green leg | one RGB LED (default, `RGB_LED = true`); yellow = red + green |
| D10 → 220 Ω → RGB red leg | longest leg → GND (common cathode) or 3.3V (`RGB_COMMON_ANODE = true`) |
| D11 → buzzer + , buzzer − → GND | buzzer (set `BUZZER_PASSIVE = true` in the sketch for a passive one) |

Three separate LEDs instead: D8 green, D9 yellow, D10 red, each through 220 Ω to GND, and `RGB_LED = false`.
The onboard RGB LED (LED3) always shows the colour too, so the board works with nothing wired.

The UNO Q header pins are 3.3 V, so the LEDs are a little dimmer than on a 5 V Uno.

1. First-time board setup in **Arduino App Lab** over USB-C (sets the board's Wi-Fi and password).
2. App Lab → **Create new app** → `boomerang_station`. Replace `sketch/sketch.ino` and `python/main.py`
   with the files in `unoq/boomerang_station/`.
3. In the board's copy of `main.py` set `API_URL` (backend address) and `STATION_KEY`. **Never commit the key.**
4. Press **Run**. Self-test: check → dash → cross, then the small diamond means "ready". A `?` means the
   board cannot reach the backend (wrong URL/key, Wi-Fi down).
5. On the phone open `<backend>/app/capture.html`, pick the mode, type the order ID and take the two photos.
   The board lights up within ~2 s of the decision. Ship-outs flash green (yellow if shipped after a pick warning).

The board asks `GET /station/events?after=<cursor>` (staff key). The first call returns only a cursor, so
old results are never replayed. Live camera on the phone needs HTTPS (a tunnel or hosting); over plain
HTTP the page falls back to the phone's photo button, which works too.

### Run everything on the UNO Q (no laptop, power bank only)

The board runs Debian 13 (arm64), so it can host the whole backend and the web pages; Nova, S3 and
MongoDB are cloud services it reaches over Wi-Fi.

1. One time, over USB-C in App Lab: name the board, set its password and Wi-Fi (at the venue use a
   phone hotspot - campus Wi-Fi logins do not work for a board).
2. From the laptop: `ssh arduino@<board>.local`, then `git clone https://github.com/srikar06-dev/boomerang.git`.
3. From the laptop: `scp .env arduino@<board>.local:~/boomerang/.env` (secrets never go through git).
4. On the board: `cd ~/boomerang && bash unoq/install_backend.sh` - installs the backend in `.venv` and a
   `boomerang` systemd service that starts at every boot on port 8000.
5. App Lab: create the `boomerang_station` app from `unoq/boomerang_station/`, keep `API_URL = "auto"`
   (finds the backend on the same board), set `STATION_KEY`, Run, then **Run at startup** (▼ next to Run).
6. Phones on the same Wi-Fi open `http://<board-ip>:8000/app/capture.html`. For a public HTTPS link
   (judges, live phone camera) add Tailscale Funnel on the board.

Power on → Wi-Fi → backend service → station app: about a minute from plugging in the power bank.
Logs: `journalctl -u boomerang -f`. Restart: `sudo systemctl restart boomerang`.
