"""Add your OWN demo items (product + orders) to the database, next to the seed data.

Orders get IDs ORD-2001, ORD-2002, ... so they never clash with the seed (ORD-1001..1020).
Their fingerprint starts empty: do a ship-out at the station to record photos, weight and serial.
"""
import re

from .models import Customer, Order, Product

FIRST_ORDER = 2001
RESALE_SHARE = {"A": 0.8, "B": 0.6, "C": 0.35, "D": 0.1}   # resale value as a share of the price, per grade


def _sku(name: str) -> str:
    return (re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")[:24] or "ITEM") + "-X"


def _next_order_number(database) -> int:
    numbers = [int(m.group(1)) for o in database.orders.find({}, {"order_id": 1})
               if (m := re.fullmatch(r"ORD-(\d+)", o.get("order_id", ""))) and int(m.group(1)) >= FIRST_ORDER]
    return max(numbers, default=FIRST_ORDER - 1) + 1


def add_item(database, name: str, price_usd: float, weight_g: float | None, has_serial: bool,
             orders: int = 2, customer_id: str = "CUST-001", unit_id: str | None = None,
             sealed_consumable: bool = False) -> list[str]:
    """Creates (or updates) the product and `orders` new orders for it. Returns the new order IDs."""
    sku = _sku(name)
    if unit_id is None:
        unit_id = "device" if has_serial else "none"
    has_serial = unit_id != "none"      # a box label is still a code we record and compare
    product = Product(sku=sku, name=name, price_usd=price_usd, expected_weight_g=weight_g, has_serial=has_serial,
                      unit_id=unit_id, sealed_consumable=sealed_consumable,
                      resale_value_by_grade={g: round(price_usd * s, 2) for g, s in RESALE_SHARE.items()})
    if database.products.find_one({"sku": sku}) is None:
        database.products.insert_one(product.model_dump())
    else:
        database.products.update_one({"sku": sku}, {"$set": product.model_dump()})
    if database.customers.find_one({"customer_id": customer_id}) is None:
        database.customers.insert_one(Customer(customer_id=customer_id, orders=orders, flagged_returns=0).model_dump())
    start = _next_order_number(database)
    ids = [f"ORD-{n}" for n in range(start, start + orders)]
    for oid in ids:
        database.orders.insert_one(Order(order_id=oid, sku=sku, customer_id=customer_id).model_dump())
    return ids
