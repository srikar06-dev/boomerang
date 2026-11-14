"""Demo data: 5 products, 20 orders with ship-out fingerprints, 10 synthetic customers.

Everything here is SYNTHETIC and labelled as such. Weights and prices are placeholders:
real fingerprints are recorded through POST /shipout at the station.
"""
import random
from datetime import datetime, timedelta, timezone

from .models import Customer, Fingerprint, Order, Product

COLLECTIONS = ("products", "orders", "customers", "returns", "sessions")

PRODUCTS = [
    Product(sku="LAPTOP-01", name="Laptop 14-inch", price_usd=899, expected_weight_g=1400, has_serial=True,
            resale_value_by_grade={"A": 720, "B": 560, "C": 380, "D": 120}),
    Product(sku="HEADPH-01", name="Over-ear headphones", price_usd=149, expected_weight_g=260, has_serial=True,
            resale_value_by_grade={"A": 110, "B": 80, "C": 45, "D": 10}),
    Product(sku="MOUSE-01", name="Wireless mouse", price_usd=39, expected_weight_g=95, has_serial=True,
            resale_value_by_grade={"A": 27, "B": 18, "C": 8, "D": 0}),
    Product(sku="BOTTLE-01", name="Insulated water bottle 1 L", price_usd=29, expected_weight_g=420, has_serial=False,
            resale_value_by_grade={"A": 18, "B": 10, "C": 4, "D": 0}),
    Product(sku="LAPBAG-01", name="Laptop bag", price_usd=59, expected_weight_g=780, has_serial=False,
            resale_value_by_grade={"A": 40, "B": 28, "C": 12, "D": 0}),
]

ORDERS_PER_PRODUCT = 4
N_CUSTOMERS = 10


def build(now: datetime | None = None) -> dict[str, list[dict]]:
    """Returns the documents to insert. Same output every time (fixed random seed), apart from dates."""
    rng = random.Random(9)
    now = now or datetime.now(timezone.utc)

    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        orders = rng.randint(3, 25)
        # two customers with a heavy return-abuse history, the rest clean or nearly clean
        flagged = round(orders * 0.5) if i in (4, 9) else rng.choice([0, 0, 0, 1])
        customers.append(Customer(customer_id=f"CUST-{i:03d}", orders=orders, flagged_returns=flagged))

    orders = []
    n = 0
    for product in PRODUCTS:
        for _ in range(ORDERS_PER_PRODUCT):
            n += 1
            weight = round(product.expected_weight_g * rng.uniform(0.98, 1.02))  # unit-to-unit variation
            orders.append(Order(
                order_id=f"ORD-{1000 + n}",
                sku=product.sku,
                customer_id=customers[(n - 1) % N_CUSTOMERS].customer_id,
                shipped_at=now - timedelta(days=rng.randint(2, 28)),
                fingerprint=Fingerprint(
                    weight_g=weight,
                    serial=f"SN{rng.randrange(10**8):08d}" if product.has_serial else None,
                ),
            ))

    return {
        "products": [p.model_dump() | {"synthetic": True} for p in PRODUCTS],
        "orders": [o.model_dump() | {"synthetic": True} for o in orders],
        "customers": [c.model_dump() | {"synthetic": True} for c in customers],
    }


def run(database) -> dict[str, int]:
    """Wipes the five demo collections and reloads the seed data. Returns counts per collection."""
    data = build()
    for name in COLLECTIONS:
        database[name].delete_many({})
    for name, docs in data.items():
        database[name].insert_many(docs)
    database.products.create_index("sku", unique=True)
    database.orders.create_index("order_id", unique=True)
    database.customers.create_index("customer_id", unique=True)
    database.sessions.create_index("session_id", unique=True)
    database.returns.create_index("order_id")
    return {name: len(data.get(name, [])) for name in COLLECTIONS}
