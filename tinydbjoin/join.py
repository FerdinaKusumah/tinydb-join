from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from tinydb import TinyDB
from tinydb.table import Document, Table

Row = Mapping[str, Any]
Source = Table | TinyDB | Iterable[Row]
KeyFunction = Callable[[Row], Any]
Key = str | KeyFunction
Index = dict[Any, list[Row]]


class Join:
    """Hash joins between TinyDB tables, whichever database or storage each one is in."""

    @classmethod
    def inner(
        cls, left: Source, right: Source, on: tuple[Key, Key]
    ) -> list[tuple[Row, Row]]:
        """Pair every left document with every right document whose key matches."""
        return cls._pairs(left, right, on, keep_unmatched=False)

    @classmethod
    def left(
        cls, left: Source, right: Source, on: tuple[Key, Key]
    ) -> list[tuple[Row, Row | None]]:
        """Like `inner`, but a left document without a match is paired with None."""
        return cls._pairs(left, right, on, keep_unmatched=True)

    @classmethod
    def attach(
        cls,
        parents: Source,
        children: Source,
        local: Key,
        foreign: Key,
        as_: str,
        many: bool = True,
    ) -> list[Row]:
        """Copy each parent with its matching children nested under `as_`."""
        local_key, foreign_key = cls._key_function(local), cls._key_function(foreign)
        index = cls._index(children, foreign_key)
        attached = []
        for parent in parents:
            found = cls._matches(index, local_key(parent))
            nested = list(found) if many else next(iter(found), None)
            attached.append(cls._with_field(parent, as_, nested))
        return attached

    @classmethod
    def _pairs(
        cls, left: Source, right: Source, on: tuple[Key, Key], keep_unmatched: bool
    ) -> list[tuple[Row, Row | None]]:
        left_key, right_key = (cls._key_function(key) for key in on)
        index = cls._index(right, right_key)
        pairs: list[tuple[Row, Row | None]] = []
        for row in left:
            found = cls._matches(index, left_key(row))
            if found:
                pairs.extend((row, match) for match in found)
            elif keep_unmatched:
                pairs.append((row, None))
        return pairs

    @classmethod
    def _index(cls, source: Source, key: KeyFunction) -> Index:
        index: Index = defaultdict(list)
        for row in source:
            value = key(row)
            if not cls._is_missing(value):
                index[value].append(row)
        return index

    @classmethod
    def _matches(cls, index: Index, value: Any) -> list[Row]:
        # A dict lookup would match the same NaN object by identity.
        return [] if cls._is_missing(value) else index.get(value, [])

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or value != value

    @staticmethod
    def _key_function(key: Key) -> KeyFunction:
        if isinstance(key, str):
            return lambda row: row.get(key)
        if callable(key):
            return key
        raise TypeError(
            f"A key must be a field name or a function, got {type(key).__name__}"
        )

    @staticmethod
    def _with_field(row: Row, field: str, value: Any) -> Row:
        copy = {**row, field: value}
        return Document(copy, doc_id=row.doc_id) if isinstance(row, Document) else copy
