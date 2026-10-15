import math
from collections.abc import Iterator
from types import MappingProxyType

import pytest
from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage
from tinydb.table import Document, Table

from tinydbjoin import Join

from .conftest import CUSTOMERS, ORDERS, PRODUCTS


def ids(pairs: list[tuple]) -> list[tuple]:
    return [(left["id"], right and right["id"]) for left, right in pairs]


class TestInner:
    def test_pairs_matching_documents_in_left_then_right_order(
        self, orders: Table, customers: Table
    ) -> None:
        pairs = Join.inner(orders, customers, on=("customer_id", "id"))

        assert pairs == [
            (ORDERS[0], CUSTOMERS[0]),
            (ORDERS[1], CUSTOMERS[0]),
            (ORDERS[2], CUSTOMERS[1]),
        ]

    def test_pairs_are_the_documents_as_read(
        self, orders: Table, customers: Table
    ) -> None:
        order, customer = Join.inner(orders, customers, on=("customer_id", "id"))[0]

        assert isinstance(order, Document) and order.doc_id == 1
        assert isinstance(customer, Document) and customer.doc_id == 1

    def test_joins_tables_on_different_storages(
        self, orders: Table, products: Table
    ) -> None:
        pairs = Join.inner(orders, products, on=("sku", "sku"))

        assert [(o["id"], p["title"]) for o, p in pairs] == [
            (101, "Kopi Aceh 250g"),
            (102, "Teh Melati"),
            (103, "Kopi Aceh 250g"),
        ]

    def test_one_pair_per_duplicate_match_in_right_order(self) -> None:
        left = [{"id": 1, "k": "x"}]
        right = [{"id": 10, "k": "x"}, {"id": 11, "k": "y"}, {"id": 12, "k": "x"}]

        assert ids(Join.inner(left, right, on=("k", "k"))) == [(1, 10), (1, 12)]

    def test_self_join(self) -> None:
        staff = [
            {"id": 1, "name": "Boss", "manager_id": None},
            {"id": 2, "name": "Dev", "manager_id": 1},
            {"id": 3, "name": "Ops", "manager_id": 1},
        ]

        pairs = Join.inner(staff, staff, on=("manager_id", "id"))

        assert [(s["name"], m["name"]) for s, m in pairs] == [
            ("Dev", "Boss"),
            ("Ops", "Boss"),
        ]

    @pytest.mark.parametrize(
        "left, right",
        [([], [{"k": 1}]), ([{"k": 1}], []), ([], [])],
        ids=["empty-left", "empty-right", "both-empty"],
    )
    def test_empty_side_gives_no_pairs(self, left: list, right: list) -> None:
        assert Join.inner(left, right, on=("k", "k")) == []

    def test_does_not_change_the_tables(
        self, shop: TinyDB, orders: Table, customers: Table
    ) -> None:
        for order, customer in Join.inner(orders, customers, on=("customer_id", "id")):
            order["qty"] = 0
            customer["name"] = "changed"

        assert orders.all() == ORDERS
        assert customers.all() == CUSTOMERS


class TestLeft:
    def test_keeps_unmatched_left_documents_with_none(
        self, orders: Table, customers: Table
    ) -> None:
        pairs = Join.left(orders, customers, on=("customer_id", "id"))

        assert ids(pairs) == [(101, 1), (102, 1), (103, 2), (104, None)]
        assert pairs[3] == (ORDERS[3], None)

    def test_empty_right_keeps_every_left_document(self) -> None:
        left = [{"id": 1, "k": 1}, {"id": 2, "k": 2}]

        assert Join.left(left, [], on=("k", "k")) == [(left[0], None), (left[1], None)]

    def test_matched_left_document_gets_no_extra_none_pair(self) -> None:
        left = [{"id": 1, "k": 1}]
        right = [{"id": 10, "k": 1}, {"id": 11, "k": 1}]

        assert ids(Join.left(left, right, on=("k", "k"))) == [(1, 10), (1, 11)]


class TestAttach:
    def test_has_many_nests_a_list_and_keeps_every_parent(
        self, customers: Table, orders: Table
    ) -> None:
        result = Join.attach(
            customers, orders, local="id", foreign="customer_id", as_="orders"
        )

        assert result == [
            {**CUSTOMERS[0], "orders": [ORDERS[0], ORDERS[1]]},
            {**CUSTOMERS[1], "orders": [ORDERS[2]]},
            {**CUSTOMERS[2], "orders": []},
        ]

    def test_belongs_to_nests_one_document_or_none(
        self, orders: Table, customers: Table
    ) -> None:
        result = Join.attach(
            orders,
            customers,
            local="customer_id",
            foreign="id",
            as_="customer",
            many=False,
        )

        assert [o["customer"] for o in result] == [
            CUSTOMERS[0],
            CUSTOMERS[0],
            CUSTOMERS[1],
            None,
        ]

    def test_belongs_to_takes_the_first_match(self) -> None:
        children = [{"id": 10, "k": 1}, {"id": 11, "k": 1}]

        result = Join.attach([{"k": 1}], children, "k", "k", "child", many=False)

        assert result[0]["child"]["id"] == 10

    def test_parents_and_children_keep_their_doc_ids(
        self, customers: Table, orders: Table
    ) -> None:
        result = Join.attach(customers, orders, "id", "customer_id", "orders")

        assert all(isinstance(c, Document) for c in result)
        assert [c.doc_id for c in result] == [1, 2, 3]
        assert [o.doc_id for o in result[0]["orders"]] == [1, 2]

    def test_child_doc_id_updates_the_original(
        self, customers: Table, orders: Table
    ) -> None:
        child = Join.attach(customers, orders, "id", "customer_id", "orders")[0][
            "orders"
        ][0]

        orders.update({"qty": 9}, doc_ids=[child.doc_id])

        assert orders.get(doc_id=1)["qty"] == 9

    def test_belongs_to_shares_one_child_object(
        self, orders: Table, customers: Table
    ) -> None:
        result = Join.attach(
            orders, customers, "customer_id", "id", "customer", many=False
        )

        assert result[0]["customer"] is result[1]["customer"]

    def test_duplicate_parents_get_their_own_copy_and_list(self) -> None:
        parent = {"id": 1}
        result = Join.attach([parent, parent], [{"p": 1}], "id", "p", "kids")

        assert result[0] is not result[1]
        assert result[0]["kids"] is not result[1]["kids"]
        assert result[0]["kids"][0] is result[1]["kids"][0]

    def test_does_not_change_list_input(self) -> None:
        parents = [{"id": 1, "kids": "keep me"}]

        result = Join.attach(parents, [{"p": 1}], "id", "p", "kids")

        assert result == [{"id": 1, "kids": [{"p": 1}]}]
        assert parents == [{"id": 1, "kids": "keep me"}]

    def test_plain_mappings_come_back_as_dicts(self) -> None:
        parents = [MappingProxyType({"id": 1})]

        result = Join.attach(parents, [], "id", "p", "kids")

        assert type(result[0]) is dict
        assert result == [{"id": 1, "kids": []}]

    def test_chains_two_levels_across_storages(
        self, customers: Table, orders: Table, products: Table
    ) -> None:
        orders_with_product = Join.attach(
            orders, products, "sku", "sku", "product", many=False
        )

        result = Join.attach(
            customers, orders_with_product, "id", "customer_id", "orders"
        )

        assert [o["product"]["title"] for o in result[0]["orders"]] == [
            "Kopi Aceh 250g",
            "Teh Melati",
        ]
        assert result[2]["orders"] == []

    def test_attach_output_feeds_inner(self, customers: Table, orders: Table) -> None:
        with_orders = Join.attach(customers, orders, "id", "customer_id", "orders")

        pairs = Join.inner(orders, with_orders, on=("customer_id", "id"))

        assert [len(c["orders"]) for _, c in pairs] == [2, 2, 1]

    def test_empty_parents_give_empty_result(self, orders: Table) -> None:
        assert Join.attach([], orders, "id", "customer_id", "orders") == []


class TestMissingKeys:
    def test_none_never_matches_none(self) -> None:
        left = [{"id": 1, "k": None}, {"id": 2}]
        right = [{"id": 10, "k": None}, {"id": 11}]

        assert Join.inner(left, right, on=("k", "k")) == []
        assert ids(Join.left(left, right, on=("k", "k"))) == [(1, None), (2, None)]
        assert [p["kids"] for p in Join.attach(left, right, "k", "k", "kids")] == [
            [],
            [],
        ]

    def test_nan_never_matches_even_the_same_object(self) -> None:
        left = [{"id": 1, "k": math.nan}]
        right = [{"id": 10, "k": math.nan}, {"id": 11, "k": float("nan")}]

        assert Join.inner(left, right, on=("k", "k")) == []
        assert Join.attach(left, right, "k", "k", "kid", many=False)[0]["kid"] is None

    def test_doc_id_is_not_a_key_unless_asked(self) -> None:
        tags = TinyDB(storage=MemoryStorage).table("tags")
        tags.insert_multiple([{"name": "new"}, {"name": "sale"}])
        links = [{"tag_id": 1}, {"tag_id": 2}]

        assert Join.inner(links, tags, on=("tag_id", "id")) == []

        pairs = Join.inner(links, tags, on=("tag_id", lambda d: d.doc_id))
        assert [t["name"] for _, t in pairs] == ["new", "sale"]


class TestKeys:
    def test_key_function_and_field_name_mix(self, customers: Table) -> None:
        excel = [
            {"Customer ID": "1", "Note": "VIP"},
            {"Customer ID": "3", "Note": "new"},
        ]

        assert Join.inner(customers, excel, on=("id", "Customer ID")) == []

        pairs = Join.inner(customers, excel, on=(lambda c: str(c["id"]), "Customer ID"))
        assert [(c["name"], e["Note"]) for c, e in pairs] == [
            ("Ani", "VIP"),
            ("Citra", "new"),
        ]

    def test_nested_field(self) -> None:
        left = [{"meta": {"sku": "A-1"}}]

        pairs = Join.inner(left, PRODUCTS, on=(lambda d: d["meta"]["sku"], "sku"))

        assert pairs == [(left[0], PRODUCTS[0])]

    def test_composite_key(self) -> None:
        sales = [{"store": "BDG", "date": "2026-10-01", "total": 5}]
        targets = [
            {"store": "BDG", "date": "2026-10-02", "target": 9},
            {"store": "BDG", "date": "2026-10-01", "target": 7},
        ]
        key = lambda d: (d["store"], d["date"])

        pairs = Join.inner(sales, targets, on=(key, key))

        assert [t["target"] for _, t in pairs] == [7]

    def test_key_function_errors_propagate(self, orders: Table) -> None:
        with pytest.raises(KeyError, match="meta"):
            Join.inner(orders, PRODUCTS, on=(lambda d: d["meta"]["sku"], "sku"))

    def test_safe_key_function_skips_documents_without_the_field(self) -> None:
        left = [{"id": 1, "meta": {"sku": "A-1"}}, {"id": 2}]

        pairs = Join.left(
            left, PRODUCTS, on=(lambda d: d.get("meta", {}).get("sku"), "sku")
        )

        assert [(l["id"], p and p["sku"]) for l, p in pairs] == [(1, "A-1"), (2, None)]

    def test_keys_compare_with_python_equality(self) -> None:
        left = [{"k": 1}, {"k": "1"}]
        right = [{"k": 1.0, "id": "float"}, {"k": True, "id": "bool"}]

        pairs = Join.inner(left, right, on=("k", "k"))

        assert [r["id"] for _, r in pairs] == ["float", "bool"]

    def test_unicode_keys(self) -> None:
        left = [{"kota": "Cirebon ✓"}]
        right = [{"kota": "Cirebon ✓", "id": 1}]

        assert len(Join.inner(left, right, on=("kota", "kota"))) == 1

    @pytest.mark.parametrize("side", ["left", "right"])
    def test_unhashable_key_value_raises(self, side: str) -> None:
        good, bad = [{"k": 1}], [{"k": [1]}]
        left, right = (bad, good) if side == "left" else (good, bad)

        with pytest.raises(TypeError, match="unhashable"):
            Join.inner(left, right, on=("k", "k"))


class TestSources:
    def test_tinydb_reads_its_default_table(self) -> None:
        db = TinyDB(storage=MemoryStorage)
        db.insert({"id": 1})

        assert ids(Join.inner(db, [{"id": 1}], on=("id", "id"))) == [(1, 1)]

    def test_search_result(self, customers: Table, orders: Table) -> None:
        bandung = customers.search(Query().city == "Bandung")

        result = Join.attach(bandung, orders, "id", "customer_id", "orders")

        assert [(c["name"], len(c["orders"])) for c in result] == [
            ("Ani", 2),
            ("Citra", 0),
        ]

    def test_generators_are_read_once(self) -> None:
        left = (row for row in [{"id": 1, "k": 1}])
        right = (row for row in [{"id": 10, "k": 1}])

        assert ids(Join.left(left, right, on=("k", "k"))) == [(1, 10)]

    def test_reads_each_table_once(
        self, orders: Table, customers: Table, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = []
        original = Table._read_table

        def counting_read(table: Table) -> dict:
            reads.append(table.name)
            return original(table)

        monkeypatch.setattr(Table, "_read_table", counting_read)
        Join.inner(orders, customers, on=("customer_id", "id"))

        assert sorted(reads) == ["customers", "orders"]


class ExplodingSource:
    def __iter__(self) -> Iterator[dict]:
        raise AssertionError("source was read")


class TestValidation:
    @pytest.mark.parametrize("bad_key", [1, None, ("a",), b"id"])
    def test_bad_key_raises_type_error_before_reading(self, bad_key: object) -> None:
        with pytest.raises(TypeError, match="field name or a function"):
            Join.inner(ExplodingSource(), ExplodingSource(), on=("k", bad_key))

        with pytest.raises(TypeError, match="field name or a function"):
            Join.attach(ExplodingSource(), ExplodingSource(), bad_key, "k", "x")

    @pytest.mark.parametrize("on", [("k",), ("k", "k", "k")])
    def test_on_needs_exactly_two_keys(self, on: tuple) -> None:
        with pytest.raises(ValueError):
            Join.inner(ExplodingSource(), ExplodingSource(), on=on)
