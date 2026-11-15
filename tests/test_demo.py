import json
import sqlite3

import pytest

from lore.bench import demo
from lore.bench.demo import select_databases, teaching_hint
from lore.config import ROOT


def test_demo_selection_uses_measured_gains_and_strict_size_limit():
    summary = {"per_db": [{"db_id": str(i), "floor": 50, "lore": 60 + i} for i in range(6)]}
    sizes = {str(i): 10 for i in range(6)}
    sizes["5"] = 100_000_000
    assert [row["db_id"] for row in select_databases(summary, sizes)] == ["4", "3", "2", "1"]
    summary["per_db"][0]["lore"] = None
    with pytest.raises(ValueError):
        select_databases(summary, sizes)


def test_teaching_hint_keeps_the_rule_explanation():
    note = "Use the lab test date, not the patient's first hospital visit."
    hint = teaching_hint("hospital visit date for a lab test", {
        "sql": "Laboratory.Date", "note": note,
    })
    assert "Laboratory.Date" in hint and note in hint
    assert teaching_hint("male", {"sql": "Patient.SEX = 'M'"}) == (
        "In this database, male means Patient.SEX = 'M'."
    )


def test_teaching_hint_checks_the_exact_api_limit_without_truncation():
    properties = {"sql": "t.c", "note": ""}
    prefix = teaching_hint("term", properties)
    properties["note"] = "x" * (2000 - len(prefix) - 1)
    assert len(teaching_hint("term", properties)) == 2000
    properties["note"] += "x"
    with pytest.raises(ValueError, match="API hint limit"):
        teaching_hint("term", properties)


def test_portable_bundle_keeps_data_attribution_and_database_bytes(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "results/fixture").mkdir(parents=True)
    (root / "results/fixture/demo.json").write_text(json.dumps({"databases": [{"id": "fixture"}]}))
    notice = (ROOT / "DATA_LICENSE.md").read_bytes()
    (root / "DATA_LICENSE.md").write_bytes(notice)
    source = tmp_path / "source"
    (source / "minidev").mkdir(parents=True)
    (source / "minidev/sqlite.json").write_text("[]")
    (source / "minidev/prompt_template.txt").write_text("Schema\nQuestion")
    database = source / "fixture.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE items (value INTEGER)")
        db.execute("INSERT INTO items VALUES (7)")
    descriptions = source / "descriptions"
    descriptions.mkdir()
    (descriptions / "items.csv").write_text("column_name,column_description\nvalue,A value\n")
    monkeypatch.setattr(demo, "ROOT", root)
    monkeypatch.setattr(demo, "settings", type("Settings", (), {"bird_dir": source})())
    monkeypatch.setattr(demo, "db_path", lambda _db: database)
    monkeypatch.setattr(demo, "description_dir", lambda _db: descriptions)
    layout = {
        "databases": {"fixture": "databases/fixture.sqlite"},
        "descriptions": {"fixture": "descriptions/fixture"},
    }
    monkeypatch.setattr(demo, "paths", lambda: layout)

    target = demo.bundle("fixture", tmp_path / "bundles") / "data/bird"
    assert (target / "DATA_LICENSE.md").read_bytes() == notice
    assert (target / "databases/fixture.sqlite").read_bytes() == database.read_bytes()
    assert (target / "descriptions/fixture/items.csv").read_bytes() == (
        descriptions / "items.csv"
    ).read_bytes()
    assert json.loads((target / "paths.json").read_text()) == layout
