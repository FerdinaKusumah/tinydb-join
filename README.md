# tinydb-join

Join TinyDB tables in memory: tables in the same database, in different database files, or on
different storages (JSON file, memory, Redis or S3 through
[tinydb-storage](https://github.com/FerdinaKusumah/tinydb-storage)). One small dependency: `tinydb`.

Made for small machines (Raspberry Pi, set-top boxes), proofs of concept and sampling data, where a
database server is more than the job needs.

> **Not an official TinyDB project.** TinyDB leaves relationships out on purpose
> ("Why Not Use TinyDB?" in its docs) and leaves extras like this to extensions.

## Installation

```shell
pip install tinydbjoin
```

Requires Python 3.10+ and TinyDB 4.8+.

## The data

A TinyDB database holds **many tables**. On disk, each table is a JSON object of documents keyed by
`doc_id`. Here, `shop.json` holds two tables:

```json
{
  "customers": {
    "1": {"id": 1, "name": "Ani",   "city": "Bandung"},
    "2": {"id": 2, "name": "Budi",  "city": "Jakarta"},
    "3": {"id": 3, "name": "Citra", "city": "Bandung"}
  },
  "orders": {
    "1": {"id": 101, "customer_id": 1,    "sku": "A-1", "qty": 2},
    "2": {"id": 102, "customer_id": 1,    "sku": "B-7", "qty": 1},
    "3": {"id": 103, "customer_id": 2,    "sku": "A-1", "qty": 5},
    "4": {"id": 104, "customer_id": null, "sku": "C-3", "qty": 1}
  }
}
```

A second file, `catalog.json`, holds the products:

```json
{
  "products": {
    "1": {"sku": "A-1", "title": "Kopi Aceh 250g", "price": "45000"},
    "2": {"sku": "B-7", "title": "Teh Melati",     "price": "18000"}
  }
}
```

Relationships are plain fields you store yourself (`orders.customer_id` → `customers.id`,
`orders.sku` → `products.sku`). There are no foreign keys and nothing checks them.

## Picking the tables

A join takes **tables**, never databases, so where a table lives makes no difference:

```python
from tinydb import TinyDB

shop = TinyDB("shop.json")
catalog = TinyDB("catalog.json")

customers = shop.table("customers")   # same database...
orders = shop.table("orders")         # ...two tables
products = catalog.table("products")  # another file

# or another storage, e.g. Redis via tinydb-storage:
# stock = TinyDB(storage=RedisStorage, ...).table("stock")
```

Each side of a join can be:

| Input | Read as |
|---|---|
| a `Table` (`db.table("orders")`) | all its documents |
| a `TinyDB` | its default table (`_default`) |
| a list of dicts or documents, e.g. `orders.search(Query().qty > 1)` or rows loaded from an Excel export | as given |

There is no `where`: filter with TinyDB's own `Query` (or plain Python) first, then join the result.

## Joining

```python
from tinydbjoin import Join
```

Three functions, all on `Join`:

```python
Source = Table | TinyDB | Iterable[Mapping[str, Any]]
Key = str | Callable[[Mapping[str, Any]], Any]

Join.inner(left: Source, right: Source, on: tuple[Key, Key]) -> list[tuple[Document, Document]]
Join.left(left: Source, right: Source, on: tuple[Key, Key]) -> list[tuple[Document, Document | None]]
Join.attach(parents: Source, children: Source, local: Key, foreign: Key, as_: str, many: bool = True) -> list[Document]
```

Each side of `on` is chosen on its own: a `str` is a field name, anything callable is a key
function, so `on=(lambda c: str(c["id"]), "Customer ID")` mixes both. Anything else raises
`TypeError` before reading the tables. (`Document` above means whatever the source holds: TinyDB
documents, or your own dicts when you pass a list.)

### `Join.inner(left, right, on=(left_key, right_key))`

Pairs every left document with every right document whose key matches. The result is a list of
`(left, right)` tuples, in the order of the left table, then the right one:

```python
Join.inner(orders, customers, on=("customer_id", "id"))
```

```python
[
    ({"id": 101, "customer_id": 1, "sku": "A-1", "qty": 2}, {"id": 1, "name": "Ani",  "city": "Bandung"}),
    ({"id": 102, "customer_id": 1, "sku": "B-7", "qty": 1}, {"id": 1, "name": "Ani",  "city": "Bandung"}),
    ({"id": 103, "customer_id": 2, "sku": "A-1", "qty": 5}, {"id": 2, "name": "Budi", "city": "Jakarta"}),
]
```

Order 104 has no customer, so it is left out. Customer 3 has no order, so that customer is left out too.

The same call works across files:

```python
Join.inner(orders, products, on=("sku", "sku"))
```

```python
[
    ({"id": 101, ..., "sku": "A-1"}, {"sku": "A-1", "title": "Kopi Aceh 250g", "price": "45000"}),
    ({"id": 102, ..., "sku": "B-7"}, {"sku": "B-7", "title": "Teh Melati",     "price": "18000"}),
    ({"id": 103, ..., "sku": "A-1"}, {"sku": "A-1", "title": "Kopi Aceh 250g", "price": "45000"}),
]
```

**Why tuples and not one merged dict?** Both sides usually share field names (`id` here). Merging
would need a renaming rule, or would silently overwrite one side. With tuples, you pick the fields
yourself, in one line:

```python
[
    {"order": o["id"], "customer": c["name"], "qty": o["qty"]}
    for o, c in Join.inner(orders, customers, on=("customer_id", "id"))
]
# [{"order": 101, "customer": "Ani", "qty": 2},
#  {"order": 102, "customer": "Ani", "qty": 1},
#  {"order": 103, "customer": "Budi", "qty": 5}]
```

### `Join.left(left, right, on=(left_key, right_key))`

Like `inner`, but every left document stays. One without a match is paired with `None`:

```python
Join.left(orders, customers, on=("customer_id", "id"))
```

```python
[
    ({"id": 101, ...}, {"id": 1, "name": "Ani",  ...}),
    ({"id": 102, ...}, {"id": 1, "name": "Ani",  ...}),
    ({"id": 103, ...}, {"id": 2, "name": "Budi", ...}),
    ({"id": 104, "customer_id": None, "sku": "C-3", "qty": 1}, None),
]
```

### `Join.attach(parents, children, local, foreign, as_, many=True)`

Nests the matching children inside each parent, under a new field, like eager loading in an ORM.
Every parent stays.

**One to many** (`many=True`, the default): a list, empty when there is none.

```python
Join.attach(customers, orders, local="id", foreign="customer_id", as_="orders")
```

```python
[
    {"id": 1, "name": "Ani", "city": "Bandung", "orders": [
        {"id": 101, "customer_id": 1, "sku": "A-1", "qty": 2},
        {"id": 102, "customer_id": 1, "sku": "B-7", "qty": 1},
    ]},
    {"id": 2, "name": "Budi", "city": "Jakarta", "orders": [
        {"id": 103, "customer_id": 2, "sku": "A-1", "qty": 5},
    ]},
    {"id": 3, "name": "Citra", "city": "Bandung", "orders": []},
]
```

**Belongs to** (`many=False`): one document, or `None`.

```python
Join.attach(orders, customers, local="customer_id", foreign="id", as_="customer", many=False)
```

```python
[
    {"id": 101, "customer_id": 1, "sku": "A-1", "qty": 2, "customer": {"id": 1, "name": "Ani", ...}},
    {"id": 102, "customer_id": 1, "sku": "B-7", "qty": 1, "customer": {"id": 1, "name": "Ani", ...}},
    {"id": 103, "customer_id": 2, "sku": "A-1", "qty": 5, "customer": {"id": 2, "name": "Budi", ...}},
    {"id": 104, "customer_id": None, "sku": "C-3", "qty": 1, "customer": None},
]
```

**Chaining.** The output of `attach` is a list of documents, so it can be the input of any join,
including another `attach`. The output of `inner` and `left` is a list of tuples, which is not a
source: turn it into documents first (see the one-liner above).

**Two levels**, across two files: attach the product to each order, then the orders to each
customer:

```python
orders_with_product = Join.attach(orders, products, local="sku", foreign="sku", as_="product", many=False)
Join.attach(customers, orders_with_product, local="id", foreign="customer_id", as_="orders")[0]
```

```python
{"id": 1, "name": "Ani", "city": "Bandung", "orders": [
    {"id": 101, "customer_id": 1, "sku": "A-1", "qty": 2,
     "product": {"sku": "A-1", "title": "Kopi Aceh 250g", "price": "45000"}},
    {"id": 102, "customer_id": 1, "sku": "B-7", "qty": 1,
     "product": {"sku": "B-7", "title": "Teh Melati", "price": "18000"}},
]}
```

**Filter first:** only customers in Bandung.

```python
from tinydb import Query

bandung = customers.search(Query().city == "Bandung")
Join.attach(bandung, orders, local="id", foreign="customer_id", as_="orders")
# Ani with her 2 orders, Citra with []
```

**What you get back:**

- Each parent is a shallow copy with the new field, so the input is never changed. A parent read
  from TinyDB stays a `Document` and keeps its `doc_id` (`[1, 2, 3]` above).
- Children are the documents as read, not copies: TinyDB documents keep their `doc_id` too, so
  `orders.update({"qty": 3}, doc_ids=[child.doc_id])` works.
- With `many=False`, parents with the same key share **one** child object (both orders of Ani point
  at the same customer document). Editing it in place shows under every one of them.
- The tables themselves are never changed: TinyDB hands out fresh documents on every read.

## Keys

A key is a **field name** or a **function** of the document. A function covers what a field name
can't:

| Need | Key |
|---|---|
| nested field | `lambda d: d["meta"]["sku"]` |
| two fields together | `lambda d: (d["store"], d["date"])` |
| different types on each side | `lambda d: str(d["id"])` |

**Missing fields.** A field name that a document lacks gives `None`, so that document never matches
(rule 1). A key function is your own code and runs as written: `d["meta"]["sku"]` raises `KeyError`
on a document without `meta`, and the join stops with that error. This is on purpose. Swallowing
errors would turn a typo in a field name into "no matches", with nothing to tell you why. When some
documents really lack the field, say so in the function:

```python
lambda d: d.get("meta", {}).get("sku")   # None when missing, so no match
```

The last one matters for data from spreadsheets, where numbers often arrive as text. Without it,
nothing matches, and that is not an error:

```python
excel = [{"Customer ID": "1", "Note": "VIP"}, {"Customer ID": "3", "Note": "new"}]

Join.inner(customers, excel, on=("id", "Customer ID"))
# []  (1 is not "1")

Join.inner(customers, excel, on=(lambda c: str(c["id"]), "Customer ID"))
# [({"id": 1, "name": "Ani", ...},   {"Customer ID": "1", "Note": "VIP"}),
#  ({"id": 3, "name": "Citra", ...}, {"Customer ID": "3", "Note": "new"})]
```

## Rules

1. **A missing, `None` or `NaN` key never matches**, on either side, like `NULL` in SQL. Order 104
   (`customer_id: null`) matches nothing, not even another document with no key.
2. **`doc_id` is never used as a key unless you ask for it.** TinyDB gives a deleted document's
   `doc_id` to the next new one once the database is reopened (checked: delete document 3, reopen,
   insert, and the new document is 3 again). A child still pointing at 3 would then join the wrong
   parent, silently. Store your own id. If you must, ask explicitly:
   `on=("customer_id", lambda d: d.doc_id)`.
3. **Order is stable:** the left (or parent) order, then the right (or children) order.
4. **Keys compare like Python's `==`:** `1`, `1.0` and `True` are the same key, `"1"` is not. A key
   must be hashable: a list raises `TypeError`, so turn it into a tuple in a key function.
5. **Duplicate keys** on the right give one pair per match (`inner`, `left`), or every match in the
   list (`attach`). With `many=False`, the first match wins.
6. **Nothing is written.** Joins read the tables and return new lists.
7. **Cost:** a hash join, O(n + m). Memory is about the size of both tables, which TinyDB already
   reads whole anyway. See [Performance](#performance).

## Performance

Everything runs in memory, in pure Python. A join reads each side once, indexes the right side in a
dict, then walks the left side, so the time grows in a straight line with the number of documents.

Measured with 10k customers × 50k orders in memory storage (best of 5 runs):

| Machine | Reading both tables | `inner`, `left` or `attach` (reading included) |
|---|---|---|
| Desktop, Intel i5-13400F, Python 3.12 | 31 ms | 54 to 65 ms |
| Set-top box, Amlogic S905X (4× Cortex-A53, 1.9 GB RAM), Python 3.10 | 0.66 s | 1.4 to 2.1 s |

On the set-top box the whole process peaked at 128 MiB of memory. Joining 1k customers stored in
Redis on another machine with 5k orders in a local JSON file took 171 ms there, network included,
and gave the same pairs as a brute-force nested loop.

What that means in practice:

- Thousands to tens of thousands of documents: fine, even on a Raspberry Pi or a set-top box.
- Hundreds of thousands, or a join on every web request: use a real database (SQLite, DuckDB).
- Half the time is TinyDB reading the tables, and a table is read again on every join. To join the
  same table several times, read it once and pass the list: `customers_rows = list(customers)`.
- With a remote storage (Redis, S3), every read is a round trip; the list trick helps even more.

## Not included

- `right` and `full` outer joins (swap the arguments of `left`)
- `where`, `order_by`, `limit` (use `Query`, `sorted`, slicing)
- group by and aggregates
- many to many through a pivot table (two `attach` calls)
- model classes with relations, ORM-style
- data larger than memory, streaming
- writing joined results back

**Use something else when:** the data does not fit in memory, or you need analytical queries
(**DuckDB**). If your data is already in DataFrames, use `pandas.merge`.

## Development

```shell
make install   # poetry install
make test      # pytest with coverage
make format    # black
```

- Tests with `pytest`, 100% line and branch coverage (CI fails below it): every rule above has a
  test, plus empty tables, self-joins, generators and joins across a JSON file and memory storage.
- Full type hints on every function.
- CI on Python 3.10 to 3.14, and TinyDB 4.8 (the oldest supported). A GitHub release publishes to
  PyPI.

## License

MIT
