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
