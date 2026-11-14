"""Resets the demo data in MongoDB. Run from the repo root:

    python scripts/seed.py

WARNING: deletes everything in products, orders, customers, returns and sessions first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config, seed  # noqa: E402
from app.db import db  # noqa: E402

counts = seed.run(db())
print(f"Seeded database '{config.MONGODB_DB}':")
for name, n in counts.items():
    print(f"  {name:10s} {n}")
