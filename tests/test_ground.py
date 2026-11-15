import json
from types import SimpleNamespace

import pytest

from lore.ground import ground, hidden, reliability, render_block
from lore.ids import column_id
from lore.learn import validate_rules
from lore.schema_ingest import Schema


def test_reliability_hidden_certified_and_budget():
    r = SimpleNamespace(properties={"wins": 0, "losses": 3}, certified_at=None)
    assert reliability(r) == 0.2 and hidden(r)
    r.certified_at = "fixture"
    assert not hidden(r)
    block, items = render_block(
        [
            dict(section="rules", text="- best", score=1, id="r1"),
            dict(section="examples", text="X" * 4000, score=0.1, id="e1"),
        ]
    )
    assert len(block) <= 3600 and [i["id"] for i in items] == ["r1"]
    assert render_block([]) == ("", [])


def test_reflection_validation_ignores_unknown_columns_and_bad_shapes():
    schema = Schema({"orders": {"Status": "INT"}})
    text = """prefix {"rules":[
        {"term":"revenue status","aliases":["sales"],"columns":["ORDERS.STATUS","bad.x"],
         "sql":"orders.Status IN (2,3,4)","note":"Reusable"},
        {"term":"bad","columns":["missing.x"],"sql":"oops"}
    ]} suffix"""
    result = validate_rules(text, schema)
    assert len(result) == 1 and result[0]["columns"] == ["orders.Status"]
    assert validate_rules("not JSON", schema) == []
    assert validate_rules('{"rules": null}', schema) == []


def test_reflection_fragments_validate_sql_and_target_columns():
    schema = Schema({"orders": {"status": "INT", "amount": "REAL", "created": "TEXT"}})

    def validate(sql, columns=None, allowed_columns=None):
        return validate_rules(
            json.dumps(
                {
                    "rules": [
                        {
                            "term": "receipt amount",
                            "sql": sql,
                            "columns": columns or ["orders.amount", "orders.status"],
                        }
                    ]
                }
            ),
            schema,
            allowed_columns=allowed_columns,
        )

    assert validate("orders.amount")[0]["columns"] == ["orders.amount"]
    assert validate("orders.amount, orders.status")[0]["columns"] == [
        "orders.amount",
        "orders.status",
    ]
    assert validate("orders.status IN (2, 3, 4)")[0]["columns"] == ["orders.status"]
    assert validate("ORDER BY orders.amount DESC")
    assert validate("strftime('%Y', orders.created)", ["orders.created"])
    assert validate("EXISTS (SELECT 1 FROM orders WHERE orders.amount > 0)", ["orders.amount"])
    for bad in (
        "SELECT orders.amount FROM orders AS o",
        "orders.amount FROM orders AS o",
        "FROM orders",
        "ORDER BY orders.amount DESC LIMIT 1",
        "PARTITION BY orders.status",
        "o.amount",
        "orders.missing",
        "amount",
        "orders.amount > :threshold",
        "orders.amount > ?",
        "orders.amount > <minimum>",
        "orders.amount; SELECT 1",
        "EXISTS (SELECT 1 FROM missing WHERE orders.amount > 0)",
        "orders.amount = (SELECT orders.amount FROM orders ORDER BY orders.amount LIMIT 1)",
    ):
        assert validate(bad) == [], bad
    assert validate("orders.amount", ["orders.status"]) == []
    assert validate("orders.amount", allowed_columns={"orders.status"}) == []
    assert validate("orders.amount", allowed_columns={"orders.amount"})


@pytest.mark.asyncio
async def test_column_walk_finds_differently_worded_rules_and_trace_is_exact():
    schema = Schema({"orders": {"status": "INT"}})
    cid = column_id("orders", "status")
    rule = SimpleNamespace(
        id="r1",
        from_entity="term:revenue",
        to_entity=cid,
        properties={"sql": "orders.status IN (2,3,4)", "wins": 4, "losses": 0},
        certified_at=None,
    )
    entities = {
        cid: SimpleNamespace(id=cid, name="orders.status", properties={}),
        "term:revenue": SimpleNamespace(id="term:revenue", name="revenue", properties={}),
    }

    class Reader:
        async def seeds(self, question, k):
            return {cid: 1}

        async def inc(self, entity_id, rel_type):
            return [rule] if rel_type == "MEANS" else []

        async def all(self, rel_type):
            return []

        async def entity(self, entity_id):
            return entities.get(entity_id)

    result = await ground(Reader(), schema, "which status codes count?")
    assert '"revenue" means:' in result.block
    assert result.trace["rules"] == ["r1"]
    assert result.trace["examples"] == []
