"""Seed data shape. Uses a tiny in-memory stand-in for MongoDB, so no network is needed."""
from app import seed
from app.models import Order, Product


class FakeCollection:
    def __init__(self):
        self.docs, self.indexes = [{"old": True}], []

    def delete_many(self, query):
        assert query == {}
        self.docs = []

    def insert_many(self, docs):
        self.docs.extend(docs)

    def create_index(self, key, **kw):
        self.indexes.append(key)


class FakeDB(dict):
    def __missing__(self, name):
        self[name] = FakeCollection()
        return self[name]

    __getattr__ = dict.__getitem__


def test_counts_and_wipe():
    database = FakeDB()
    counts = seed.run(database)
    assert counts == {"products": 5, "orders": 20, "customers": 10, "returns": 0, "sessions": 0}
    for name in seed.COLLECTIONS:
        assert {"old": True} not in database[name].docs   # old data removed everywhere


def test_documents_are_valid_and_linked():
    data = seed.build()
    skus = {Product(**{k: v for k, v in p.items() if k != "synthetic"}).sku for p in data["products"]}
    customers = {c["customer_id"] for c in data["customers"]}
    order_ids = set()
    for doc in data["orders"]:
        order = Order(**{k: v for k, v in doc.items() if k != "synthetic"})
        assert order.sku in skus and order.customer_id in customers
        assert order.fingerprint.weight_g > 0
        order_ids.add(order.order_id)
    assert len(order_ids) == 20
    assert all(d["synthetic"] for docs in data.values() for d in docs)


def test_serial_only_where_product_has_one():
    data = seed.build()
    has_serial = {p["sku"]: p["has_serial"] for p in data["products"]}
    for order in data["orders"]:
        assert (order["fingerprint"]["serial"] is not None) == has_serial[order["sku"]]


def test_build_is_repeatable():
    a, b = seed.build(), seed.build()
    assert [o["fingerprint"] for o in a["orders"]] == [o["fingerprint"] for o in b["orders"]]
