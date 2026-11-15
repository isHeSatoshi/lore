import sqlite3
from types import SimpleNamespace

import pytest

from lore.sqlexec import GoldCache, ex_match, execute_table, run_sql


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "has spaces?#.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE items (value)")
        conn.executemany("INSERT INTO items VALUES (?)", [(1,), (1,), (2,)])
    return path


def test_strict_set_comparison():
    assert ex_match([(1,), (1,), (2,)], [(2,), (1,)])
    assert not ex_match([(1, 2)], [(2, 1)])
    assert not ex_match(None, [])
    assert not ex_match([], None)
    assert ex_match([], [])


def test_read_only_and_row_cap(db, tmp_path):
    assert run_sql(db, "SELECT value FROM items")[0] == [(1,), (1,), (2,)]
    assert run_sql(db, "SELECT value FROM items", max_rows=1)[0] == [(1,)]
    for sql in (
        "DELETE FROM items",
        "CREATE TABLE evil(x)",
        "PRAGMA writable_schema=1",
        f"ATTACH DATABASE '{tmp_path / 'evil.sqlite'}' AS evil",
        "SELECT 1; DELETE FROM items",
    ):
        assert run_sql(db, sql)[1] is not None
    assert not (tmp_path / "evil.sqlite").exists()
    assert run_sql(db, "SELECT COUNT(*) FROM items")[0] == [(3,)]


def test_timeout(db):
    rows, error, ms = run_sql(
        db,
        """WITH RECURSIVE cnt(x) AS
        (SELECT 1 UNION ALL SELECT x+1 FROM cnt) SELECT SUM(x) FROM cnt""",
        timeout_s=0.03,
    )
    assert rows is None and "interrupt" in error.lower()
    assert ms < 2000


@pytest.mark.asyncio
async def test_gold_cache_round_trip_and_db_change(db, tmp_path):
    q = SimpleNamespace(db_path=db, gold_sql="SELECT value FROM items")
    path = tmp_path / "gold.sqlite"
    a = await GoldCache(path).get(q)
    b = await GoldCache(path).get(q)
    assert a[0] == b[0] and b[2] == 0
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO items VALUES (3)")
    assert len((await GoldCache(path).get(q))[0]) == 4


@pytest.mark.asyncio
async def test_ui_bounds_large_values_without_changing_benchmark(db):
    assert (await execute_table(db, "SELECT randomblob(1000001)"))[1] is not None
    rows, error, _ = run_sql(db, "SELECT length(randomblob(1000001))")
    assert error is None and rows == [(1000001,)]
