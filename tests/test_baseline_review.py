import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest

from lore.bench import review_baselines as review
from lore.bird import Question
from lore.sqlexec import GoldCache


@pytest.mark.asyncio
async def test_sdk_review_reads_recorded_cache_not_raw_provider_cache(tmp_path, monkeypatch):
    run, prompt = "fixture", "published fixture prompt"
    cfg = replace(review.settings, data_dir=tmp_path / "data")
    directory = cfg.data_dir / "runs" / run
    directory.mkdir(parents=True)
    result = tmp_path / "results" / run
    result.mkdir(parents=True)
    (result / "learning_configuration.json").write_text(
        json.dumps({"protocol": "factory-sdk-v2"})
    )
    metadata = {"model": "minimax-m3.1-flash", "effort": "medium"}
    (directory / "metadata.json").write_text(json.dumps(metadata))
    (directory / "answers.jsonl").write_text(
        json.dumps({"system": "ceiling", "correct": False, "error": None, "gold_error": None,
                    "db_id": "fixture", "key": "t0", "sql": "SELECT 1"}) + "\n"
    )
    database = tmp_path / "fixture.sqlite"
    sqlite3.connect(database).close()
    question = Question("t0", "fixture", "fixture", "", "SELECT 2", "", database)
    cache_dir = cfg.data_dir / "cache"
    cache_dir.mkdir()
    key = hashlib.sha256(
        json.dumps([metadata["model"], metadata["effort"], prompt], ensure_ascii=False).encode()
    ).hexdigest()
    for filename, text in (
        ("llm.sqlite", "SELECT 999"),
        ("factory-sdk-v2.sqlite", "```sql\nSELECT 1;\n```"),
    ):
        with sqlite3.connect(cache_dir / filename) as cache:
            cache.execute("CREATE TABLE cache (key TEXT, result TEXT)")
            cache.execute("INSERT INTO cache VALUES (?,?)", (key, json.dumps({"text": text})))
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(review, "settings", cfg)
    monkeypatch.setattr(review, "load_test", lambda: [question])
    monkeypatch.setattr(review, "published", lambda: [
        {"db_id": "fixture", "question_id": 0, "prompt": prompt}
    ])
    monkeypatch.setattr(review, "GoldCache", lambda: GoldCache(tmp_path / "gold.sqlite"))
    rows = await review.review(run, count=1)
    assert rows[0]["extraction_matches_cache"] is True
    assert rows[0]["cache_source"] == "cache/factory-sdk-v2.sqlite"
    assert rows[0]["model_text"] == "```sql\nSELECT 1;\n```"
    assert rows[0]["rerun_correct"] is False


def test_cache_selection_preserves_legacy_and_rejects_path_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(review, "settings", replace(review.settings, data_dir=tmp_path / "data"))
    assert review.completion_cache("raw") == tmp_path / "data/cache/llm.sqlite"
    directory = tmp_path / "results/invalid"
    directory.mkdir(parents=True)
    (directory / "learning_configuration.json").write_text(
        json.dumps({"protocol": "factory-sdk-../../private"})
    )
    with pytest.raises(ValueError):
        review.completion_cache("invalid")
