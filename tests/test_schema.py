import sqlite3
from types import SimpleNamespace

import pytest

from lore.graphdb import GraphReader
from lore.ids import column_id, example_id, short, slug, table_id
from lore.schema_ingest import descriptions, read_schema


def test_ids_are_stable_and_distinguish_slug_collisions():
    assert slug(" A__(B)  ") == "a-b"
    assert slug("??") == "x"
    assert len(short("abc")) == 6
    assert table_id("a-b") != table_id("a_b")
    assert column_id("x", "a b") != column_id("x", "a-b")
    assert example_id("s123") == "example:s123"


def test_schema_quotes_and_implicit_composite_fk(tmp_path):
    db = tmp_path / "quoted.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE "Parent Table" ("a (id)" INTEGER, b TEXT, PRIMARY KEY ("a (id)", b));
            CREATE TABLE child (x INTEGER, y TEXT, FOREIGN KEY (x,y) REFERENCES "Parent Table");
        """)
    schema, joins = read_schema(db)
    assert len(schema) == 2 and sum(map(len, schema.values())) == 4
    assert schema.resolve("PARENT TABLE", "A (ID)") == ("Parent Table", "a (id)")
    assert len(joins) == 2
    assert schema.lookup["parent table.a (id)"] == "Parent Table.a (id)"


def test_description_encoding_and_normalization(tmp_path):
    (tmp_path / "child.csv").write_bytes(
        "original_column_name,column_name,column_description,value_description\n x ,Café,owner’s code,1 means active\n".encode(
            "cp1252"
        )
    )
    assert descriptions(tmp_path)[("child", "x")]["column_name"] == "Café"


@pytest.mark.asyncio
async def test_reader_pages_and_freeze_coalesce_and_invalidate():
    calls = []

    async def listing(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            items=[kwargs["cursor"] or "first"],
            next_cursor="second" if kwargs["cursor"] is None else None,
        )

    graph = SimpleNamespace(relations=SimpleNamespace(list=listing))
    reader = GraphReader(graph, frozen=True)
    assert await reader.inc("column:x", "MEANS") == ["first", "second"]
    assert await reader.inc("column:x", "MEANS") == ["first", "second"]
    assert len(calls) == 2
    assert calls[0]["to_entity"] == "column:x"
    reader.freeze(False)
    await reader.inc("column:x", "MEANS")
    await reader.inc("column:x", "MEANS")
    assert len(calls) == 6
