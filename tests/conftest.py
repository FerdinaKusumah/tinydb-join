from pathlib import Path

import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage
from tinydb.table import Table

CUSTOMERS = [
    {"id": 1, "name": "Ani", "city": "Bandung"},
    {"id": 2, "name": "Budi", "city": "Jakarta"},
    {"id": 3, "name": "Citra", "city": "Bandung"},
]
ORDERS = [
    {"id": 101, "customer_id": 1, "sku": "A-1", "qty": 2},
    {"id": 102, "customer_id": 1, "sku": "B-7", "qty": 1},
    {"id": 103, "customer_id": 2, "sku": "A-1", "qty": 5},
    {"id": 104, "customer_id": None, "sku": "C-3", "qty": 1},
]
PRODUCTS = [
    {"sku": "A-1", "title": "Kopi Aceh 250g", "price": "45000"},
    {"sku": "B-7", "title": "Teh Melati", "price": "18000"},
]


@pytest.fixture
def shop(tmp_path: Path) -> TinyDB:
    db = TinyDB(tmp_path / "shop.json")
    db.table("customers").insert_multiple(CUSTOMERS)
    db.table("orders").insert_multiple(ORDERS)
    yield db
    db.close()


@pytest.fixture
def customers(shop: TinyDB) -> Table:
    return shop.table("customers")


@pytest.fixture
def orders(shop: TinyDB) -> Table:
    return shop.table("orders")


@pytest.fixture
def products() -> Table:
    table = TinyDB(storage=MemoryStorage).table("products")
    table.insert_multiple(PRODUCTS)
    return table
