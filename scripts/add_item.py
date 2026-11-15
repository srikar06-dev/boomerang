"""Add one of your own demo items to the database, with new order IDs (ORD-2001, ...).

    python scripts/add_item.py "Anker charger" --price 30 --weight 120 --serial yes --orders 3

Then ship it out at the station with one of the printed order IDs, and return it later.
--serial yes|no : does the item have a printed serial number?   --customer CUST-004 : a customer with
a bad return history (CUST-004 and CUST-009 in the seed data) to show the history signal.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.catalog import add_item  # noqa: E402
from app.db import db  # noqa: E402

p = argparse.ArgumentParser(description="Add a demo item and orders")
p.add_argument("name")
p.add_argument("--price", type=float, required=True, help="price in USD")
p.add_argument("--weight", type=float, help="typical weight in grams (optional)")
p.add_argument("--serial", choices=["yes", "no"], default="yes")
p.add_argument("--orders", type=int, default=2, help="how many orders to create (default 2)")
p.add_argument("--customer", default="CUST-001")
a = p.parse_args()

ids = add_item(db(), a.name, a.price, a.weight, a.serial == "yes", a.orders, a.customer)
print(f"Added '{a.name}' (${a.price:g}, serial: {a.serial}) for {a.customer}. New orders:")
for oid in ids:
    print(f"  {oid}")
