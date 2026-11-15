import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from lore.bench.run import Answers, baseline_report, evaluate, read_answers, run_lock
from lore.bird import Question
from lore.sqlexec import GoldCache
from lore.systems import System


def test_journal_recovers_partial_append_and_skips_duplicates(tmp_path):
    path = tmp_path / "answers.jsonl"
    row = dict(system="floor", phase="test", checkpoint=0, key="t1", correct=True)
    path.write_text(json.dumps(row) + '\n{"system": "floo')
    journal = Answers(path)
    journal.append(row)
    assert read_answers(path) == [row]
    assert path.read_text().endswith("\n")
    path.write_text('bad\n{"incomplete"')
    with pytest.raises(ValueError):
        Answers(path)


def test_run_has_only_one_writer(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(RuntimeError, match="Another benchmark"):
            with run_lock(tmp_path):
                pass
    with run_lock(tmp_path):
        pass


@pytest.mark.asyncio
async def test_resume_rejects_changed_databases_before_writing_metadata_or_opening_clients(
    tmp_path, monkeypatch
):
    import lore.bench.run as runner

    cfg = replace(runner.settings, data_dir=tmp_path)
    monkeypatch.setattr(runner, "settings", cfg)
    directory = tmp_path / "runs/fixture"
    directory.mkdir(parents=True)
    metadata = dict(
        model=cfg.model,
        effort=cfg.effort,
        max_tokens=cfg.max_tokens,
        seed=0,
        stream_cap=80,
        concurrency=2,
        date="2026-01-01",
        dbs=["original"],
    )
    path = directory / "metadata.json"
    before = json.dumps(metadata)
    path.write_text(before)
    monkeypatch.setattr(
        runner,
        "load_test",
        lambda: [Question("t1", "changed", "question", "", "SELECT 1", "", Path("unused"))],
    )
    monkeypatch.setattr(
        runner, "LLM", lambda *_: pytest.fail("Opened client before configuration validation")
    )
    args = SimpleNamespace(
        run="fixture", seed=0, stream_cap=80, systems="floor", dbs=None, checkpoints="1.0"
    )
    with pytest.raises(ValueError, match="databases changed"):
        await runner.run(args)
    assert path.read_text() == before


def test_baseline_gap_requires_complete_test_set(tmp_path, monkeypatch):
    import lore.bench.run as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    journal = SimpleNamespace(rows=[])
    for name, correct in (("floor", 250), ("ceiling", 300)):
        journal.rows.extend(
            dict(system=name, phase="test", correct=i < correct, prompt_tokens=100)
            for i in range(500)
        )
    report = baseline_report(journal, "fixture")
    assert report["gap_points"] == 10
    assert report["gap_gate_pass"] is True
    journal.rows.pop()
    assert "gap_gate_pass" not in baseline_report(journal, "fixture")
    journal.rows.append(dict(system="ceiling", phase="test", correct=False, prompt_tokens=100))
    for i, row in enumerate(journal.rows[500:]):
        row["correct"] = i < 270
    report = baseline_report(journal, "fixture")
    assert report["gap_gate_pass"] is False
    assert report["gap_points"] == 4
    for i, row in enumerate(journal.rows[500:]):
        row["correct"] = i < 275
    assert baseline_report(journal, "fixture")["gap_gate_pass"] is True
    journal.rows[500 + 274]["correct"] = False
    assert baseline_report(journal, "fixture")["gap_gate_pass"] is False
    for i, row in enumerate(journal.rows[:500]):
        row["correct"] = i < 318
    for i, row in enumerate(journal.rows[500:]):
        row["correct"] = i < 343
    report = baseline_report(journal, "fixture")
    assert report["gap_gate_pass"] and report["gap_points"] == 5


@pytest.mark.asyncio
async def test_evaluation_uses_full_results_and_resumes(tmp_path):
    db = tmp_path / "db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE x(value)")
        conn.executemany("INSERT INTO x VALUES (?)", [(i,) for i in range(250)])
    q = Question("t1", "db", "list all", "forbidden analyst evidence", "SELECT * FROM x", "", db)

    class Fixture(System):
        name = "floor"

        async def build_prompt(self, visible):
            assert visible.evidence == ""
            return "fixture", {}

    class Client:
        calls = 0

        async def complete(self, prompt):
            self.calls += 1
            return SimpleNamespace(
                text="```sql\nSELECT * FROM x;\n```", input_tokens=10, output_tokens=8, cached=False
            )

    client = Client()
    journal = Answers(tmp_path / "answers.jsonl")
    gold = GoldCache(tmp_path / "gold.sqlite")
    row = await evaluate(Fixture(), q, client, gold, journal)
    assert row["correct"] and row["rows_ok"]
    assert await evaluate(Fixture(), q, client, gold, journal) == row
    assert client.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["grounding", "llm"])
async def test_network_errors_are_not_scored_as_model_failures(tmp_path, failure_at):
    class Broken(System):
        name = "floor"

        async def build_prompt(self, q):
            if failure_at == "grounding":
                raise ConnectionError("graph unavailable")
            return "fixture", {}

    class Client:
        async def complete(self, prompt):
            raise ConnectionError("endpoint unavailable")

    q = Question("t1", "db", "question", "", "", "", Path("x"))
    journal = Answers(tmp_path / "answers.jsonl")
    with pytest.raises(ConnectionError):
        await evaluate(Broken(), q, Client(), None, journal)
    assert journal.rows == []
