from app import catalog, seed
from tests.fakes import FakeDB


def test_add_item_creates_product_and_new_orders():
    db = FakeDB()
    seed.run(db)
    ids = catalog.add_item(db, "Anker charger", 30, 120, True, orders=3)
    assert ids == ["ORD-2001", "ORD-2002", "ORD-2003"]
    assert db.products.find_one({"name": "Anker charger"})["price_usd"] == 30
    assert db.orders.find_one({"order_id": "ORD-2002"})["sku"] == db.products.find_one({"name": "Anker charger"})["sku"]
    assert catalog.add_item(db, "Water bottle", 20, None, False) == ["ORD-2004", "ORD-2005"]   # numbering continues


def test_new_customer_is_created_if_missing():
    db = FakeDB()
    catalog.add_item(db, "Mug", 12, 300, False, customer_id="CUST-777")
    assert db.customers.find_one({"customer_id": "CUST-777"}) is not None


def test_profile_is_stored_and_box_counts_as_a_code():
    from app import catalog
    from app.models import unit_id_of
    from tests.fakes import FakeDB
    db = FakeDB()
    catalog.add_item(db, "Arduino Nano", 45, None, has_serial=False, orders=1, unit_id="box")
    p = db.products.find_one({"sku": "ARDUINO-NANO-X"})
    assert p["unit_id"] == "box" and p["has_serial"] is True and unit_id_of(p) == "box"
    assert unit_id_of({"has_serial": False}) == "none" and unit_id_of({}) == "device"
