import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lore.bench.replay_demo import matches_answer, replay_pair
from lore.bird import Question
from lore.sqlexec import GoldCache


@pytest.mark.asyncio
async def test_replay_verifies_full_sql_not_display_capped_rows(tmp_path):
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE numbers (value INTEGER)")
        db.executemany("INSERT INTO numbers VALUES (?)", [(i,) for i in range(250)])
    q = Question("t1", "fixture", "all", "", "SELECT value FROM numbers", "", path)
    answer = {"sql": q.gold_sql, "error": None, "rows": [[i] for i in range(200)]}
    assert await matches_answer(answer, q, GoldCache(tmp_path / "gold.sqlite"))


@pytest.mark.asyncio
async def test_replay_never_teaches_followup_and_requires_rule_provenance(tmp_path):
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE numbers (value INTEGER)")
    questions = {
        "s1": Question("s1", "fixture", "A", "", "SELECT 1", "", path),
        "t1": Question("t1", "fixture", "B", "", "SELECT 2", "", path),
    }
    responses = [
        {"ask_id": "private-before-b", "sql": "SELECT 0"},
        {"ask_id": "private-ask-a", "sql": "SELECT 0"},
        {"proposal": {"ask_id": "private-proposal", "sql": "SELECT 1"}},
        {"learned": ["r1"]},
        {"sql": "SELECT 2", "graph": {"edges": [{"id": "r1", "type": "MEANS", "used": True}]}},
    ]
    original_responses = list(responses)
    calls = []

    class Client:
        async def post(self, path, json):
            calls.append((path, json))
            data = responses.pop(0)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)

    rule = SimpleNamespace(properties={"origin": "uprivate-ask-a", "sql": "numbers.value = 1"})
    context = SimpleNamespace(
        graph=SimpleNamespace(relations=SimpleNamespace(get=AsyncMock(return_value=rule)))
    )
    service = SimpleNamespace(context=AsyncMock(return_value=context))
    pair = {"db": "fixture", "a": "s1", "b": "t1", "hint": "A reusable rule"}
    result = await replay_pair(
        Client(),
        service,
        {"db": "fixture", "session": "fixture", "mode": "sandbox"},
        pair,
        questions,
        GoldCache(tmp_path / "gold.sqlite"),
    )
    assert result["passed"] and result["suggestion"]["verified"]
    feedback_ids = [body["ask_id"] for path, body in calls if path == "/api/feedback"]
    assert feedback_ids == ["private-ask-a", "private-proposal"]
    assert all(
        secret not in str(result)
        for secret in ("private-ask-a", "private-before-b", "private-proposal")
    )
    responses.extend(original_responses)
    rule.properties["origin"] = "unrelated"
    rejected = await replay_pair(
        Client(),
        service,
        {"db": "fixture", "session": "fixture", "mode": "sandbox"},
        pair,
        questions,
        GoldCache(tmp_path / "gold.sqlite"),
    )
    assert not rejected["passed"] and rejected["reason"] == "new_rule_not_used"
