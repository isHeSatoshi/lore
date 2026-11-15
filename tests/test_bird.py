from dataclasses import replace
from pathlib import Path

import pytest

from lore.bird import (
    Question,
    assert_can_learn,
    extract_sql,
    insert_knowledge,
    leak_guard,
    load_stream,
    load_test,
    normalize,
    prompt_assets,
    published,
    render_prompt,
)
from lore.config import settings


def test_sql_extraction():
    assert extract_sql("```sql\nSELECT 1;\n```\n```sql\nSELECT 2;\n```") == "SELECT 2"
    assert extract_sql("```python\nWITH x AS (SELECT 1) SELECT * FROM x;\n```").startswith("WITH")
    assert extract_sql("Answer:\nSELECT 1;") == "SELECT 1"
    assert extract_sql("No query.") == ""


def test_leak_guard_each_rule():
    q = Question("t1", "db", "count red cars today", "", "SELECT price FROM car", "", Path("x"))
    cases = [
        replace(q, key="s1", question=" COUNT  RED CARS TODAY ", gold_sql="SELECT id FROM cars"),
        replace(q, key="s2", question="another question", gold_sql="select price   from car"),
        replace(q, key="s3", question="count red cars yesterday", gold_sql="SELECT b FROM c"),
        replace(q, key="s4", question="unrelated utterance", gold_sql="SELECT price FROM car c"),
    ]
    kept, counts = leak_guard(cases, [q])
    assert kept == []
    assert counts == dict.fromkeys(
        ("question_equal", "sql_equal", "question_jaccard", "sql_jaccard"), 1
    )
    other_db = replace(q, key="s5", db_id="other")
    assert leak_guard([other_db], [q])[0] == [other_db]
    with pytest.raises(AssertionError):
        assert_can_learn(q)
    assert_can_learn(replace(q, key="s1"))
    assert_can_learn(replace(q, key="u1"))


@pytest.mark.integration
def test_published_prompt_equality_and_split():
    if not (settings.bird_dir / "paths.json").exists():
        pytest.skip("Download BIRD data to run the published-data gate")
    rows = published()
    for row in rows[:20]:
        assert render_prompt(row["db_id"], row["question"], row["evidence"]) == row["prompt"]
    for row in rows:
        if not row["evidence"]:
            assert render_prompt(row["db_id"], row["question"]) == row["prompt"]
    stream = [q for group in load_stream().values() for q in group]
    assert len(load_test()) == 500
    assert not {normalize(q.question) for q in stream} & {
        normalize(q.question) for q in load_test()
    }
    assert not {q.key for q in stream} & {q.key for q in load_test()}
    assert all(not q.evidence for q in stream)
    assert leak_guard(stream, load_test())[0] == stream
    prompt_assets.cache_clear()
    p = render_prompt(rows[0]["db_id"], rows[0]["question"])
    assert insert_knowledge(p, "") == p
    assert "\nRules:\n" in insert_knowledge(p, "Rules:\n- fixture\n\n")
