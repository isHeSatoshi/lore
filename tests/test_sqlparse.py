import pytest

from lore.bird import db_path, load_test
from lore.config import settings
from lore.schema_ingest import Schema, read_schema
from lore.sqlparse import parse_sql

SCHEMA = Schema(
    {
        "orders": {"id": "INT", "customer_id": "INT", "amount": "REAL", "status": "INT"},
        "customers": {"id": "INT", "kind": "TEXT"},
    }
)


def test_columns_joins_filters_and_scoped_aliases():
    parsed = parse_sql(
        """SELECT SUM(o.amount) FROM orders o JOIN customers c
        ON o.customer_id=c.id WHERE o.status IN (2,3,4) AND c.kind='active'""",
        SCHEMA,
    )
    assert parsed.tables == {"orders", "customers"}
    assert ("orders", "amount") in parsed.columns
    assert parsed.joins == {(("customers", "id"), ("orders", "customer_id"))}
    assert parsed.filter_columns == {("orders", "status"), ("customers", "kind")}
    parsed = parse_sql(
        """SELECT t.id FROM orders t WHERE EXISTS
        (SELECT 1 FROM customers t WHERE t.kind='active')""",
        SCHEMA,
    )
    assert ("orders", "id") in parsed.columns and ("customers", "kind") in parsed.columns


def test_ctes_and_join_literal_filters():
    parsed = parse_sql(
        """WITH paid AS (SELECT id, customer_id FROM orders WHERE status=2)
        SELECT c.kind FROM paid p JOIN customers c ON p.customer_id=c.id AND c.kind='active'""",
        SCHEMA,
    )
    assert parsed.tables == {"orders", "customers"}
    assert ("orders", "status") in parsed.filter_columns
    assert ("customers", "kind") in parsed.filter_columns
    assert "paid" not in parsed.tables


@pytest.mark.integration
def test_thirty_real_gold_queries_only_reference_real_tables():
    if not (settings.bird_dir / "paths.json").exists():
        pytest.skip("Download BIRD data")
    schemas = {}
    for q in load_test()[::16][:30]:
        schema = schemas.setdefault(q.db_id, read_schema(db_path(q.db_id))[0])
        parsed = parse_sql(q.gold_sql, schema)
        assert parsed.tables and parsed.tables <= schema.keys(), q.key
        assert all(t in schema and c in schema[t] for t, c in parsed.columns)
