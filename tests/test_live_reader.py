import asyncio
from unittest.mock import AsyncMock

import pytest

from lore import live_reader
from lore.graphdb import GraphReader
from lore.schema_ingest import read_schema


@pytest.fixture
def reader(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "schema.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("CREATE TABLE a(x INT,y INT); CREATE TABLE b(z INT);")
    schema, _ = read_schema(path)
    monkeypatch.setattr(GraphReader, "entity", AsyncMock(return_value=None))
    monkeypatch.setattr(GraphReader, "out", AsyncMock(side_effect=lambda cid, _: [cid]))
    monkeypatch.setattr(GraphReader, "all", AsyncMock(return_value=["unscoped"]))
    return live_reader.LiveGraphReader(object(), schema)


@pytest.mark.asyncio
async def test_reads_all_columns_in_reached_tables_and_no_other_tables(reader, monkeypatch):
    columns = reader.schema.by_id
    a = [cid for cid, value in columns.items() if value[0] == "a"]

    async def grounding(r, *_):
        await r.entity(a[0])
        return await r.all("JOINS")

    monkeypatch.setattr(live_reader, "_ground", grounding)
    assert await live_reader.ground(reader, reader.schema, "a") == a
    assert await reader.all("JOINS") == ["unscoped"]
    assert reader.frozen is False


@pytest.mark.asyncio
async def test_overlapping_requests_do_not_share_reached_columns(reader, monkeypatch):
    reader.ground_slots = asyncio.Semaphore(2)
    by_table = {
        table: [cid for cid, value in reader.schema.by_id.items() if value[0] == table]
        for table in ("a", "b")
    }
    both = asyncio.Event()
    started = []

    async def grounding(r, _, table, cfg):
        await r.entity(by_table[table][0])
        started.append(table)
        if len(started) == 2:
            both.set()
        await both.wait()
        return await r.all("JOINS")

    monkeypatch.setattr(live_reader, "_ground", grounding)
    result = await asyncio.gather(*(
        live_reader.ground(reader, reader.schema, table) for table in ("a", "b")
    ))
    assert result == [by_table["a"], by_table["b"]]
    assert await reader.all("JOINS") == ["unscoped"]


@pytest.mark.asyncio
async def test_failure_cleans_scope_and_each_new_request_reloads_graph(reader, monkeypatch):
    cid = next(iter(reader.schema.by_id))

    async def failure(r, *_):
        await r.entity(cid)
        raise RuntimeError("expected")

    monkeypatch.setattr(live_reader, "_ground", failure)
    with pytest.raises(RuntimeError, match="expected"):
        await live_reader.ground(reader, reader.schema, "a")
    assert await reader.all("JOINS") == ["unscoped"]

    async def grounding(r, *_):
        await r.entity(cid)
        return await r.all("JOINS")

    monkeypatch.setattr(live_reader, "_ground", grounding)
    await live_reader.ground(reader, reader.schema, "a")
    before = GraphReader.out.await_count
    await live_reader.ground(reader, reader.schema, "a")
    assert GraphReader.out.await_count == before * 2


@pytest.mark.asyncio
async def test_admission_queues_every_request_and_recovers_after_cancellation(reader, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def grounding(r, _, question, cfg):
        calls.append(question)
        entered.set()
        await release.wait()
        return question

    monkeypatch.setattr(live_reader, "_ground", grounding)
    first = asyncio.create_task(live_reader.ground(reader, reader.schema, "first"))
    await entered.wait()
    second = asyncio.create_task(live_reader.ground(reader, reader.schema, "cancelled"))
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second
    third = asyncio.create_task(live_reader.ground(reader, reader.schema, "third"))
    assert calls == ["first"]
    release.set()
    assert await asyncio.gather(first, third) == ["first", "third"]
    assert calls == ["first", "third"]
