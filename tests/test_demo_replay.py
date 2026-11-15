import json
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lore.bench.replay_demo import diverse_pairs, matches_answer, replay_pair
from lore.bird import Question
from lore.sqlexec import GoldCache


def test_replay_explores_different_followups_without_dropping_pairs():
    pairs = [{"a": str(i), "b": b} for i, b in enumerate(["t1", "t1", "t2", "t2", "t3"])]
    diverse = diverse_pairs(pairs)
    assert [p["b"] for p in diverse] == ["t1", "t2", "t3", "t1", "t2"]
    assert sorted(p["a"] for p in diverse) == sorted(p["a"] for p in pairs)
    assert diverse_pairs([]) == []


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


@pytest.mark.asyncio
async def test_runner_uses_a_fresh_completion_cache_for_every_trial(tmp_path, monkeypatch):
    from lore.bench import replay_demo as replay

    run = "fixture-replay"
    cfg = replace(replay.settings, data_dir=tmp_path / "data")
    directory = cfg.data_dir / "runs" / run
    directory.mkdir(parents=True)
    target = tmp_path / "results" / run
    target.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"model": cfg.model, "effort": cfg.effort, "max_tokens": cfg.max_tokens,
                    "seed": 0, "stream_cap": 80})
    )
    pairs = [{"db": "fixture", "a": f"s{i}", "b": f"t{i}"} for i in range(3)]
    (directory / "demo_candidates.json").write_text(json.dumps({"fixture": pairs}))
    caches = []

    def llm(label, *, cache_path):
        assert label == run + "-demo-replay"
        assert cache_path.parent.is_dir()
        caches.append(cache_path)
        return SimpleNamespace(usage=lambda: {"input_tokens": 13, "output_tokens": 7, "calls": 2})

    @asynccontextmanager
    async def lifespan(app):
        yield

    async def passed(client, service, scope, pair, questions, gold):
        return {**pair, "passed": True, "reason": "fixture"}

    monkeypatch.setattr(replay, "settings", cfg)
    monkeypatch.setattr(replay, "ROOT", tmp_path)
    monkeypatch.setattr(replay, "build", AsyncMock())
    monkeypatch.setattr(replay, "create_llm", llm)
    monkeypatch.setattr(replay, "SandboxReplay", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        replay, "create_app",
        lambda service: SimpleNamespace(router=SimpleNamespace(lifespan_context=lifespan)),
    )
    monkeypatch.setattr(replay, "load_stream", lambda *args: {"fixture": []})
    monkeypatch.setattr(replay, "load_test", lambda: [])
    monkeypatch.setattr(replay, "replay_pair", passed)
    await replay.run(run, 3)
    assert len(caches) == len(set(caches)) == 3
    assert all(path.name == "completions.sqlite" and not path.parent.exists() for path in caches)
    records = json.loads((target / "demo_replays.json").read_text())
    assert all(r["llm_usage"] == {"input_tokens": 13, "output_tokens": 7, "calls": 2} for r in records)
