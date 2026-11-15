import json

import pytest

from lore.bench.factory_runtime import record_runtime
from lore.connection_pool import configure_graph_pool


def test_pool_cap_preserves_constructor_arguments_and_is_idempotent(monkeypatch):
    import selfgraph

    from lore import graphdb

    calls = []
    monkeypatch.setattr(graphdb, "HydraDBStore", graphdb.HydraDBStore)
    monkeypatch.setattr(
        selfgraph, "HydraDBStore", lambda *a, **kw: calls.append((a, kw))
    )
    for _ in range(2):
        assert configure_graph_pool() == 4
        graphdb.HydraDBStore("bolt://fixture", auth=("user", "private-fixture"))
    assert calls == [
        (("bolt://fixture",), {
            "auth": ("user", "private-fixture"), "max_connection_pool_size": 4,
        })
    ] * 2


def test_runtime_record_retains_pre_cap_progress_and_rejects_drift(tmp_path):
    for name in ("lore/connection_pool.py", "lore/bench/factory_runtime.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    journal = tmp_path / "data/runs/r4/answers.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({
        "system": "lore", "phase": "test", "checkpoint": 1.0,
    }) + "\n")
    record_runtime(tmp_path, "r4")
    target = tmp_path / "results/r4/runtime_configuration.json"
    original = target.read_text()
    record_runtime(tmp_path, "r4")
    assert target.read_text() == original
    assert json.loads(original)["introduced_after"] == [
        {"system": "lore", "phase": "test", "checkpoint": 1.0, "answers": 1}
    ]
    (tmp_path / "lore/connection_pool.py").write_text("drift")
    with pytest.raises(ValueError, match="configuration changed"):
        record_runtime(tmp_path, "r4")
