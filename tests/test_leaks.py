import os
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from lore.bird import load_stream, load_test
from lore.graphdb import open_graph
from lore.systems import Flat, Floor, Lore, Outcome, Vector


@pytest.mark.asyncio
async def test_no_evidence_in_non_ceiling_prompts_for_fifty_questions(monkeypatch):
    questions = load_test()[::10][:50]
    lore = Lore("fixture", None)
    for q in questions:
        lore.has_knowledge[q.db_id] = False

    class Embedder:
        async def embed(self, texts):
            return np.ones((len(texts), 2), dtype=np.float32) / np.sqrt(2)

    vector = Vector(Embedder())
    flat = Flat(Embedder())
    for system in (Floor(), lore, vector, flat):
        for q in questions:
            # Pass the full object too: systems must ignore evidence themselves,
            # independently of the runner's additional without_evidence guard.
            prompt, _ = await system.build_prompt(q)
            assert not q.evidence or q.evidence not in prompt

    async def grounded(*args):
        return SimpleNamespace(
            block="Rules:\n- fixture meaning: fixture.status = 'DONE'",
            trace={"rules": ["fixture-rule"], "block_chars": 57},
        )

    monkeypatch.setattr("lore.systems.ground", grounded)
    streams = load_stream(seed=0, cap_per_db=1)
    for db in {q.db_id for q in questions}:
        source = streams[db][0]
        await vector.observe(source, Outcome(source.gold_sql, True, None, True))
        lore.has_knowledge[db] = True
        lore.readers[db], lore.schemas[db] = object(), {}
        flat.items[db] = [
            dict(section="rules", id="fixture-rule", text="- fixture status is DONE"),
            dict(section="values", id="fixture-values", text="- fixture.status: DONE"),
            dict(
                section="examples",
                id=f"example:{source.key}",
                text=f"Q: {source.question}\nSQL: {source.gold_sql}",
            ),
        ]
        flat.vectors[db] = await flat.embedder.embed(["fixture"] * len(flat.items[db]))
    for system in (lore, vector, flat):
        for q in questions:
            prompt, trace = await system.build_prompt(q)
            assert trace["block_chars"] > 0
            assert not q.evidence or q.evidence not in prompt


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_test_examples_or_origins_in_any_lore_namespace():
    if os.getenv("LORE_INTEGRATION") != "1":
        pytest.skip("Set LORE_INTEGRATION=1 to inspect all HydraDB benchmark namespaces")
    graph = await open_graph("leak-audit-" + uuid4().hex)
    try:
        namespaces, after = set(), -1
        while True:
            result = await graph.run_cypher(
                "MATCH (n:Entity) WHERE n.id > $after "
                "RETURN n.id AS id, n.ns AS ns ORDER BY n.id LIMIT 200",
                {"after": after},
            )
            namespaces.update(r["ns"] for r in result.rows if ".lore." in r["ns"])
            if len(result.rows) < 200:
                break
            after = result.rows[-1]["id"]
    finally:
        await graph.close()
    for namespace in sorted(namespaces):
        graph = await open_graph(namespace)
        try:
            async for entity in graph.entities.iterate(type="Example"):
                assert not entity.properties.get("key", "").startswith("t"), namespace
            async for relation in graph.relations.iterate(type="MEANS"):
                assert not relation.properties.get("origin", "").startswith("t"), namespace
        finally:
            await graph.close()
