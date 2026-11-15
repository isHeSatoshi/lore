import sqlite3
from types import SimpleNamespace

import pytest

from lore.bench.run import Answers, evaluate, run_stream
from lore.bird import Question
from lore.sqlexec import GoldCache
from lore.systems import Outcome, Vector


@pytest.mark.asyncio
async def test_checkpoint_state_freezes_and_partial_answer_resume(tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path):
        pass
    streams = {
        "db": [Question(f"s{i}", "db", f"stream {i}", "", "SELECT 1", "", path) for i in (1, 2)]
    }
    test = [Question("t1", "db", "test", "secret hint", "SELECT 1", "", path)]

    class Memory:
        name = "lore"
        frozen = False

        def __init__(self):
            self.observed = set()
            self.states = []

        async def build_prompt(self, q):
            assert q.evidence == ""
            self.states.append((q.key, len(self.observed), self.frozen))
            return "fixture", {}

        async def observe(self, q, outcome):
            assert q.key.startswith("s") and not self.frozen
            self.observed.add(q.key)

        async def freeze(self, frozen=True, db=None):
            self.frozen = frozen

    class Client:
        calls = 0

        async def complete(self, prompt):
            self.calls += 1
            return SimpleNamespace(text="SELECT 1", input_tokens=1, output_tokens=1, cached=False)

    journal = Answers(tmp_path / "answers.jsonl")
    gold, client, memory = GoldCache(tmp_path / "gold.sqlite"), Client(), Memory()
    await evaluate(memory, streams["db"][0], client, gold, journal, phase="stream")
    memory = Memory()  # Saved answer exists, but learning has not happened yet.
    await run_stream(memory, streams, test, [0.5, 1.0], client, gold, journal, tmp_path)
    assert memory.states == [("t1", 1, True), ("s2", 1, False), ("t1", 2, True)]
    assert len(journal.rows) == client.calls == 4
    await run_stream(memory, streams, test, [0.5, 1.0], client, gold, journal, tmp_path)
    assert client.calls == 4


@pytest.mark.asyncio
async def test_vector_only_receives_stream_gold_and_cannot_learn_frozen():
    import numpy as np

    class Embedding:
        async def embed(self, texts):
            return np.array([[1.0, 0] for _ in texts])

    system = Vector(Embedding())
    q = Question("s1", "db", "example", "", "SELECT 2", "", None)
    await system.observe(q, Outcome("SELECT 1", True, None, False))
    assert system.items["db"]["s1"][1] == "SELECT 2"
    await system.freeze(True, "db")
    with pytest.raises(AssertionError):
        await system.observe(q, Outcome("", False, "error", False))
