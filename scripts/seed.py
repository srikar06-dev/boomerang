"""Resets the demo data in MongoDB. Run from the repo root:

    python scripts/seed.py

WARNING: deletes everything in products, orders, customers, returns and sessions first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config, seed  # noqa: E402
from app.db import db  # noqa: E402

# The Atlas database is SHARED by the whole team. Only the demo laptop (DEMO_MODE=1) may reset it.
if not (config.DEMO_MODE or config.LOCAL_MODE):
    sys.exit("Refusing to seed: DEMO_MODE is not 1 in .env. The database is shared - ask the person "
             "running the demo backend to reset it.")

counts = seed.run(db())
print(f"Seeded database '{config.MONGODB_DB}':")
for name, n in counts.items():
    print(f"  {name:10s} {n}")
