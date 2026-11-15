import json
import os
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lore.bird import Question
from lore.graphdb import GraphReader, open_graph
from lore.ground import ground
from lore.ids import example_id
from lore.learn import learn
from lore.schema_ingest import ingest_schema
from lore.systems import Outcome

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_hydradb_learning_retry_grounding_and_certification(tmp_path):
    if os.getenv("LORE_INTEGRATION") != "1":
        pytest.skip("Set LORE_INTEGRATION=1 for write/read integration against HydraDB")
    path = tmp_path / "business.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE customers (id INTEGER PRIMARY KEY, kind TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INT REFERENCES customers(id),
                                 amount REAL, status INT);
            INSERT INTO customers VALUES (1,'active');
            INSERT INTO orders VALUES (1,1,10,1),(2,1,20,2),(3,1,30,3);
        """)
    graph = await open_graph("test-learning-" + uuid4().hex)
    schema = await ingest_schema(graph, path)
    correct = (
        "SELECT SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id=c.id "
        "WHERE o.status IN (2,3,4) AND c.kind='active'"
    )
    q = Question("s1", "fixture", "How much\nrevenue?", "", correct, "", path)
    outcome = Outcome("SELECT SUM(amount) FROM orders", True, None, False, {})

    class Reflection:
        calls = 0

        async def complete(self, prompt):
            self.calls += 1
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "rules": [
                            {
                                "term": "revenue status",
                                "aliases": ["sales total"],
                                "columns": ["orders.status"],
                                "sql": "orders.status IN (2,3,4)",
                                "note": "Revenue excludes unbooked orders.",
                            }
                        ]
                    }
                )
            )

    reflection = Reflection()
    try:
        learned = await learn(graph, schema, q, outcome, correct, llm=reflection)
        assert len(learned["rules"]) == 1
        reader = GraphReader(graph)
        joins = await reader.all("JOINS")
        assert len(joins) == 1 and joins[0].properties["wins"] == 1
        result = await ground(reader, schema, "What is the sales total?")
        assert result.trace["rules"] and "orders.status IN (2,3,4)" in result.block
        assert await learn(graph, schema, q, outcome, correct, llm=reflection) == {
            "rules": [],
            "new_entities": [],
            "already_applied": True,
        }
        # Simulate a crash after writes but before the completion marker.
        await graph.entities.update(example_id(q.key), properties={"learning_complete": None})
        await learn(graph, schema, q, outcome, correct, llm=reflection)
        assert (await reader.all("JOINS"))[0].properties["wins"] == 1
        rules = await reader.all("MEANS")
        assert len(rules) == 1

        class ConflictingReflection:
            async def complete(self, prompt):
                assert "Stored value definitions:" in prompt
                return SimpleNamespace(
                    text=json.dumps(
                        {
                            "rules": [
                                {
                                    "term": "revenue status",
                                    "aliases": ["cancelled sales"],
                                    "columns": ["orders.status"],
                                    "sql": "orders.status = 1",
                                    "note": "Contradictory candidate must not change aliases.",
                                }
                            ]
                        }
                    )
                )

        await learn(
            graph,
            schema,
            replace(q, key="s2", question="Show unbooked orders"),
            outcome,
            "SELECT SUM(amount) FROM orders WHERE status = 1",
            llm=ConflictingReflection(),
        )
        unchanged = await graph.relations.get(rules[0].id)
        term = await graph.entities.get(unchanged.from_entity)
        assert unchanged.properties["sql"] == "orders.status IN (2,3,4)"
        assert "sales total" in term.aliases
        assert "cancelled sales" not in term.aliases
        await graph.relations.certify(rules[0].id, by="analyst")
        before = await graph.relations.get(rules[0].id)
        up = Outcome(correct, True, None, True, {"rules": [rules[0].id]})
        await learn(graph, schema, replace(q, key="u2"), up, correct, llm=reflection)
        after = await graph.relations.get(rules[0].id)
        assert after.certified_at and after.revision == before.revision
        with pytest.raises(AssertionError):
            await learn(graph, schema, replace(q, key="t1"), up, correct, llm=reflection)
        with pytest.raises(AssertionError):
            await learn(
                graph,
                schema,
                replace(q, key="s3", evidence="must not learn this"),
                up,
                correct,
                llm=reflection,
            )
    finally:
        await graph.close()


@pytest.mark.asyncio
async def test_real_lore_initialization_and_seed_roundtrip(tmp_path, monkeypatch):
    if os.getenv("LORE_INTEGRATION") != "1":
        pytest.skip("Set LORE_INTEGRATION=1 for HydraDB")
    from lore import seeds, systems

    path = tmp_path / "fixture.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE numbers (value INTEGER)")
        db.execute("INSERT INTO numbers VALUES (1)")
    for module in (seeds, systems):
        monkeypatch.setattr(module, "db_path", lambda db: path)
        monkeypatch.setattr(module, "description_dir", lambda db: None)
    monkeypatch.setattr(systems, "render_prompt", lambda db, question: "\nQuestion:\n" + question)
    lore = await systems.Lore.create("test-" + uuid4().hex, ["fixture"], None)
    clone = await open_graph("test-seed-" + uuid4().hex)
    q = Question("s1", "fixture", "show numbers", "", "SELECT value FROM numbers", "", path)
    try:
        cold, _ = await lore.build_prompt(q)
        assert cold == "\nQuestion:\nshow numbers"
        await lore.freeze(True, "fixture")
        with pytest.raises(AssertionError):
            await lore.observe(q, Outcome(q.gold_sql, True, None, True))
        await lore.freeze(False, "fixture")
        await lore.observe(q, Outcome(q.gold_sql, True, None, True))
        file = tmp_path / "fixture.json"
        file.write_text(json.dumps(await seeds.export_graph(lore.graphs["fixture"])))
        schema = await seeds.import_seeds(clone, file)
        examples = [e async for e in clone.entities.iterate(type="Example")]
        assert len(examples) == 1 and examples[0].properties["sql"] == q.gold_sql
        assert schema == lore.schemas["fixture"]
    finally:
        await lore.close()
        await clone.close()
