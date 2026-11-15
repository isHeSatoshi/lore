import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from lore.config import ROOT, settings


@dataclass(frozen=True)
class Question:
    key: str
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    difficulty: str
    db_path: Path

    def without_evidence(self):
        return replace(self, evidence="")


def normalize(text):
    return " ".join(text.lower().split())


def tokens(text):
    return set(re.findall(r"\w+", normalize(text)))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


@lru_cache
def paths():
    return json.loads((settings.bird_dir / "paths.json").read_text())


def db_path(db_id):
    return settings.bird_dir / paths()["databases"][db_id]


def description_dir(db_id):
    value = paths().get("descriptions", {}).get(db_id)
    return settings.bird_dir / value if value else None


def _question(row, prefix, index):
    return Question(
        key=f"{prefix}{row.get('question_id', index)}",
        db_id=row["db_id"],
        question=row["question"],
        evidence=row.get("evidence") or "",
        gold_sql=row["SQL"],
        difficulty=row.get("difficulty", ""),
        db_path=db_path(row["db_id"]),
    )


@lru_cache
def published():
    return [
        json.loads(line)
        for line in (settings.bird_dir / "minidev/published.jsonl").read_text().splitlines()
        if line.strip()
    ]


def load_test():
    rows = [
        json.loads(line)
        for line in (settings.bird_dir / "minidev/test.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return [_question(r, "t", i) for i, r in enumerate(rows)]


def leak_guard(stream, test):
    by_db = defaultdict(list)
    for q in test:
        by_db[q.db_id].append(
            (normalize(q.question), normalize(q.gold_sql), tokens(q.question), tokens(q.gold_sql))
        )
    removed = Counter(
        dict.fromkeys(("question_equal", "sql_equal", "question_jaccard", "sql_jaccard"), 0)
    )
    kept = []
    for q in stream:
        question, sql = normalize(q.question), normalize(q.gold_sql)
        qt, st = tokens(q.question), tokens(q.gold_sql)
        checks = (
            ("question_equal", lambda t, value=question: value == t[0]),
            ("sql_equal", lambda t, value=sql: value == t[1]),
            ("question_jaccard", lambda t, value=qt: jaccard(value, t[2]) >= 0.6),
            ("sql_jaccard", lambda t, value=st: jaccard(value, t[3]) >= 0.8),
        )
        # Attribute each removal once, to the first matching rule in the specified order.
        for name, check in checks:
            if any(check(t) for t in by_db[q.db_id]):
                removed[name] += 1
                break
        else:
            kept.append(q)
    return kept, dict(removed)


def load_stream(seed=0, cap_per_db=80, run=None):
    rows = json.loads((settings.bird_dir / paths()["dev"]).read_text())
    dbs = {q.db_id for q in load_test()}
    raw = [_question(r, "s", i) for i, r in enumerate(rows) if r["db_id"] in dbs]
    kept, removed = leak_guard(raw, load_test())
    result = {}
    for db in sorted(dbs):
        group = [q.without_evidence() for q in kept if q.db_id == db]
        random.Random(seed).shuffle(group)
        result[db] = group[:cap_per_db]
    if run:
        target = ROOT / "results" / run
        target.mkdir(parents=True, exist_ok=True)
        report = {
            "seed": seed,
            "stream_cap": cap_per_db,
            "raw_stream": len(raw),
            "test_count": len(load_test()),
            "removed": removed,
            "remaining": len(kept),
            "eligible_per_db": dict(Counter(q.db_id for q in kept)),
            "stream_per_db": {k: len(v) for k, v in result.items()},
            "tokenization": "lowercase Unicode word tokens; each removal attributed to the first matching rule",
        }
        (target / "split.json").write_text(json.dumps(report, indent=2) + "\n")
    return result


@lru_cache
def prompt_assets():
    root = settings.bird_dir / "minidev"
    return (root / "prompt_template.txt").read_text(), json.loads(
        (root / "sqlite.json").read_text()
    )


def render_prompt(db_id, question, evidence=None):
    template, schemas = prompt_assets()
    block = f"{evidence}\n{question}" if evidence else question
    return template.format(engine="SQLite", schema=schemas[db_id], question_block=block)


def insert_knowledge(prompt, block):
    if not block:
        return prompt
    marker = "\nQuestion:\n"
    if marker not in prompt:
        raise ValueError("Published prompt has no Question: insertion point")
    return prompt.replace(marker, "\n" + block + "Question:\n", 1)


def extract_sql(text):
    fences = list(re.finditer(r"```([^\n`]*)\n(.*?)```", text, flags=re.DOTALL))
    sql_fences = [m for m in fences if m[1].strip().lower() == "sql"]
    if sql_fences or fences:
        value = (sql_fences or fences)[-1][2].strip()
    else:
        start = re.search(r"\b(SELECT|WITH)\b", text, re.IGNORECASE)
        value = text[start.start() :].strip() if start else ""
    return value.rstrip().removesuffix(";").strip()


def assert_can_learn(q):
    if not q.key.startswith(("s", "u")):
        raise AssertionError("Held-out test questions must never be used for learning")
