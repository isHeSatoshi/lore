import asyncio
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from lore.api import AppState, Service, create_app, validate_sql
from lore.llm import request_guard


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM items",
        "SELECT 1; SELECT 2",
        "PRAGMA table_info(items)",
        "ATTACH DATABASE ':memory:' AS another",
        "CREATE TABLE items(x)",
        "WITH x AS (DELETE FROM items RETURNING *) SELECT * FROM x",
    ],
)
def test_rejects_non_query_or_multiple_statements(sql):
    with pytest.raises(HTTPException):
        validate_sql(sql)


def test_query_validation_and_persistent_limits(tmp_path):
    for sql in ("SELECT 1", "WITH x AS (SELECT 1 AS n) SELECT * FROM x", "SELECT 1 UNION SELECT 2"):
        assert validate_sql(sql) == sql
    path = tmp_path / "app.sqlite"
    state = AppState(path)

    def reserve(_):
        try:
            AppState(path).reserve("same-ip", now=100_000)
            return True
        except HTTPException:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(31))) == 30
    with pytest.raises(HTTPException):
        state.reserve("same-ip", now=100_001)
    state.reserve("same-ip", now=103_600)
    with state.connect() as db:
        db.execute("DELETE FROM calls")
        db.executemany(
            "INSERT INTO calls VALUES (?, ?)", [(f"visitor-{i}", 103_600) for i in range(1999)]
        )
    state.reserve("last-visitor", now=103_601)
    with pytest.raises(HTTPException):
        state.reserve("next-visitor", now=103_601)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_api_sandbox_proposal_confirmation_isolation_reset_and_retries(
    tmp_path, monkeypatch
):
    if os.getenv("LORE_INTEGRATION") != "1":
        pytest.skip("Set LORE_INTEGRATION=1 for real HydraDB API integration")
    from lore import api

    path = tmp_path / "fixture.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE orders (id INTEGER, amount REAL, status INTEGER)")
        db.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(1, 10, 1), (2, 20, 2), (3, 30, 3)])
    monkeypatch.setattr(api, "paths", lambda: {"databases": {"fixture": "fixture.sqlite"}})
    monkeypatch.setattr(api, "db_path", lambda _: path)
    monkeypatch.setattr(api, "description_dir", lambda _: None)
    monkeypatch.setattr(api, "render_prompt", lambda db, q: "Schema: orders\nQuestion:\n" + q)

    class Model:
        reflection_calls = 0

        async def complete(self, prompt):
            if guard := request_guard.get():
                await guard()
            if prompt.startswith("You maintain"):
                self.reflection_calls += 1
                text = json.dumps(
                    {
                        "rules": [
                            {
                                "term": "booked revenue",
                                "aliases": ["net sales"],
                                "columns": ["orders.status"],
                                "sql": "orders.status IN (2,3)",
                                "note": "Revenue excludes unbooked orders.",
                            }
                        ]
                    }
                )
            else:
                text = (
                    "SELECT SUM(amount)\nFROM orders\nWHERE status IN (2,3)"
                    if "Analyst hint:" in prompt or "orders.status IN (2,3)" in prompt
                    else "SELECT SUM(amount)\nFROM orders"
                )
            return SimpleNamespace(text=text, input_tokens=100)

        async def close(self):
            pass

    model = Model()
    service = Service(tmp_path / "state", run="fixture", llm=model)
    app = create_app(service)
    scope = {"db": "fixture", "mode": "sandbox", "session": uuid4().hex}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.post("/api/ask", content=b"x" * 50_001)).status_code == 413
        invalid = await client.post(
            "/api/ask",
            content=b'{"db":"fixture","question":"\\ud800"}',
            headers={"Content-Type": "application/json"},
        )
        assert invalid.status_code == 422 and "unicode" in invalid.json()["detail"].lower()
        first = await client.post(
            "/api/ask", json={**scope, "question": "What is\nbooked revenue?"}
        )
        assert first.status_code == 200, first.text
        first = first.json()
        assert first["rows"] == [[60.0]] and first["block"] == ""
        proposal = await client.post(
            "/api/feedback",
            json={
                "ask_id": first["ask_id"],
                "verdict": "down",
                "hint": "Use only statuses 2 and 3 for revenue.",
            },
        )
        assert proposal.status_code == 200, proposal.text
        proposal = proposal.json()["proposal"]
        assert proposal["rows"] == [[50.0]]
        before = (await client.get("/api/graph", params=scope)).json()
        assert not before["edges"]
        confirmation = {"ask_id": proposal["ask_id"], "verdict": "confirm", "sql": proposal["sql"]}
        repeated = await asyncio.gather(
            *(client.post("/api/feedback", json=confirmation) for _ in range(2))
        )
        assert all(r.status_code == 200 for r in repeated), [r.text for r in repeated]
        assert len(repeated[0].json()["learned"]) == 1 and model.reflection_calls == 1
        second = await client.post(
            "/api/ask", json={**scope, "question": "How much are net sales?"}
        )
        assert second.status_code == 200, second.text
        second = second.json()
        assert second["rows"] == [[50.0]] and "orders.status IN (2,3)" in second["block"]
        assert any(edge["used"] and edge["type"] == "MEANS" for edge in second["graph"]["edges"])
        other = (await client.get("/api/graph", params={**scope, "session": uuid4().hex})).json()
        assert not other["nodes"]
        rule = repeated[0].json()["learned"][0]["id"]
        assert (
            await client.post("/api/certify", json={**scope, "relation_id": rule})
        ).status_code == 200
        assert (
            await client.post(
                "/api/certify", json={**scope, "mode": "trained", "relation_id": rule}
            )
        ).status_code == 403
        assert (
            await client.post("/api/sandbox/reset", json={k: scope[k] for k in ("session", "db")})
        ).status_code == 200
        assert not (await client.get("/api/graph", params=scope)).json()["nodes"]
        assert (await client.post("/api/feedback", json=confirmation)).status_code == 409
