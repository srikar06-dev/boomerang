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
