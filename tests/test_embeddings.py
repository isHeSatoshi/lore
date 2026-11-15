from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from lore import embeddings
from lore.ground import value_line


@pytest.mark.asyncio
async def test_embedding_deduplication_normalization_and_fresh_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings, "settings", replace(embeddings.settings, data_dir=tmp_path))
    calls = []
    embedder = embeddings.Embedder()

    def compute(texts):
        calls.append(texts)
        return [np.array([3, 4], dtype=np.float32) for _ in texts]

    monkeypatch.setattr(embedder, "_compute", compute)
    matrix = await embedder.embed(["first", "first", "second"])
    assert calls == [["first", "second"]]
    assert np.allclose(matrix, [[0.6, 0.8]] * 3)
    cached = embeddings.Embedder()
    assert np.array_equal(await cached.embed(["second", "first"]), matrix[:2])
    assert cached.model is None


def test_flat_value_items_include_all_profiled_columns():
    entity = SimpleNamespace(
        name="orders.code",
        properties={"profile": '{"distinct": 100, "nulls": 0, "top": ["A", "B"]}'},
    )
    assert value_line(entity) is None
    assert value_line(entity, small_only=False) == "- orders.code: 'A', 'B'"


@pytest.mark.asyncio
async def test_flat_duplicate_meaning_edges_do_not_consume_retrieval_slots(monkeypatch):
    from lore import systems

    class Embedder:
        async def embed(self, texts):
            return np.array([[1.0, 0.0]] * len(texts), dtype=np.float32)

    monkeypatch.setattr(systems, "render_prompt", lambda db, q: "\nQuestion:\n" + q)
    flat = systems.Flat(Embedder())
    flat.items["fixture"] = [
        dict(section="rules", id=f"r{i}", text="- first reusable meaning") for i in range(8)
    ] + [dict(section="rules", id="r9", text="- second reusable meaning")]
    flat.vectors["fixture"] = np.array([[1.0, 0.0]] * 8 + [[0.8, 0.6]], dtype=np.float32)
    prompt, trace = await flat.build_prompt(
        SimpleNamespace(db_id="fixture", question="Which meanings apply?")
    )
    assert prompt.count("- first reusable meaning") == 1
    assert "- second reusable meaning" in prompt
    assert trace["rules"] == ["r0", "r9"]
