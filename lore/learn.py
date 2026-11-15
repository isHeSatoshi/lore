import json

import sqlglot
from selfgraph import relation_id
from sqlglot import exp
from sqlglot.errors import ParseError

from lore.bird import assert_can_learn
from lore.ground import certified, reliability
from lore.ids import column_id, example_id
from lore.schema_ingest import Schema, quote
from lore.sqlexec import execute
from lore.sqlparse import parse_sql
from lore.text import entity_label

REFLECTION = """You maintain a knowledge base about one SQLite database so that future questions are answered correctly.

A question was answered with wrong SQL. An analyst supplied the correct SQL.

Question: {question}
Wrong SQL: {predicted_sql}
What happened: {error}
Correct SQL: {correct_sql}
{hint}
Columns used by the correct SQL:
{columns}

Write up to 3 reusable rules that explain what the wrong SQL misunderstood.
A rule must help with OTHER questions on this database. Good rules say what a business phrase means as a SQL condition or formula, how a value is stored (codes, formats, units), which column a phrase refers to, or a filter that is always needed.
Do not restate the whole query. Do not include constants that only matter for this one question unless they define the phrase.

Learn database meanings, not the incidental shape of this answer:
- For variable amounts, dates, years, locations, people, and top-k requests, keep only the relevant column or formula. Do not memorize the requested value, window, threshold, or LIMIT, even by putting it in the term.
- Keep fixed stored category/code mappings, such as monthly statements meaning a frequency code, and fixed formula/format constants. A generic term must not imply one particular requested category or value.
- Do not turn this query's joins, DISTINCT, projections, NULL handling, tie handling, or population restrictions into universal business policies. Do not claim another column is always wrong just because this answer used a different one. Skip uncertain rules.
- The sql must be a column, expression, expression list, predicate, or ORDER BY expression, not a complete SELECT or a FROM/JOIN, GROUP BY, PARTITION BY, or LIMIT clause. Joins are learned separately.
- Qualify every column with its real table name, quote names when needed, and use no table aliases or unbound placeholders. For a variable filter, store its column/formula rather than inventing :threshold or <city>.
- The columns list must contain only real columns actually referenced by this fragment, not other fields from the corrected query.
- A category filter must name its actual category: "express shipping" can mean parcel.service = 'E', but generic "shipping service" cannot mean only express shipping. Aliases must preserve the same category and scope, never introduce a different category.
- A requested entity value is not a fixed business definition: if the question requests recipient bank XYZ, learn the recipient-bank column, not that every recipient bank means XYZ.
- Do not learn counting granularity from one COUNT or DISTINCT query. Keep query-specific cardinality choices in the verified example, not a general rule.

Example: if a request asks for monthly receipts above 2500 during 2024, a reusable rule could map monthly receipts to the stored frequency code, or receipt amount to its amount column. The amount > 2500 and the year 2024 are not reusable rules.

Return only JSON:
{{"rules": [{{"term": "<2 to 5 word phrase a user would say>", "aliases": ["<other phrasings>"], "sql": "<SQL fragment using table.column names>", "columns": ["<table.column>"], "note": "<one sentence>"}}]}}
If nothing reusable was learned, return {{"rules": []}}.
"""


def fragment_columns(sql, schema):
    """Reject broken fragments and return only their actual schema references."""
    prefix = "SELECT 1 " if sql.lstrip().upper().startswith("ORDER BY ") else "SELECT "
    try:
        trees = sqlglot.parse(prefix + sql, read="sqlite")
    except ParseError:
        return set()
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        return set()
    tree = trees[0]
    if any(
        tree.args.get(key)
        for key in ("from_", "joins", "group", "having", "limit", "offset", "with_", "distinct")
    ):
        return set()
    if tree.find(exp.Placeholder, exp.Parameter, exp.Limit, exp.Offset):
        return set()
    tables = {table.lower() for table in schema}
    if any(table.name.lower() not in tables for table in tree.find_all(exp.Table)):
        return set()
    columns = set()
    for column in tree.find_all(exp.Column):
        real = schema.lookup.get(f"{column.table}.{column.name}".lower())
        if not real:
            return set()
        columns.add(real)
    return columns


def validate_rules(text, schema, allowed_columns=None):
    schema = schema if isinstance(schema, Schema) else Schema(schema)
    try:
        data = json.loads(text[text.index("{") : text.rindex("}") + 1])
        rules = data["rules"]
        if not isinstance(rules, list):
            return []
        result = []
        for rule in rules[:3]:
            if not isinstance(rule, dict):
                continue
            term = rule.get("term")
            if not isinstance(term, str) or not 2 <= len(term.strip()) <= 60:
                continue
            term = entity_label(term, 60)
            if len(term) < 2:
                continue
            columns = rule.get("columns", [])
            if not isinstance(columns, list):
                continue
            valid = sorted(
                {
                    schema.lookup[c.strip().lower()]
                    for c in columns
                    if isinstance(c, str) and c.strip().lower() in schema.lookup
                }
            )
            sql = rule.get("sql", "")
            if not valid or not isinstance(sql, str) or not sql.strip():
                continue
            sql = sql[:400].strip()
            referenced = fragment_columns(sql, schema)
            if allowed_columns is not None and not referenced.issubset(allowed_columns):
                continue
            valid = [column for column in valid if column in referenced]
            if not valid:
                continue
            aliases = rule.get("aliases", [])
            aliases = (
                [label for a in aliases if isinstance(a, str) and (label := entity_label(a, 60))][
                    :10
                ]
                if isinstance(aliases, list)
                else []
            )
            note = rule.get("note", "")
            result.append(
                {
                    "term": term.strip().lower(),
                    "columns": valid,
                    "sql": sql,
                    "aliases": aliases,
                    "note": note[:300] if isinstance(note, str) else "",
                }
            )
        return result
    except (ValueError, TypeError, KeyError):
        return []


async def profile_column(graph, db_path, table, column):
    cid = column_id(table, column)
    entity = await graph.entities.get(cid)
    if not entity or entity.properties.get("profile"):
        return
    t, c = quote(table), quote(column)
    stats, error, _ = await execute(
        db_path, f"SELECT COUNT(DISTINCT {c}), SUM({c} IS NULL) FROM {t}", 10
    )
    if error or not stats:
        return
    rows, error, _ = await execute(
        db_path, f"SELECT {c}, COUNT(*) FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 25", 10
    )
    if error:
        return
    top = [r[0] if r[0] is None or isinstance(r[0], (int, float)) else str(r[0])[:40] for r in rows]
    profile = {"distinct": stats[0][0], "nulls": stats[0][1] or 0, "top": top}
    while len(json.dumps(profile, ensure_ascii=False).encode()) >= 2000 and profile["top"]:
        profile["top"].pop()
    await graph.entities.update(
        cid, properties={"profile": json.dumps(profile, ensure_ascii=False)}
    )


async def profile_unseen_columns(graph, db_path, columns, eid):
    example = await graph.entities.get(eid)
    selected = example.properties.get("_profile_columns")
    if selected is None:
        selected = []
        for table, column in sorted(columns):
            entity = await graph.entities.get(column_id(table, column))
            if entity and entity.properties.get("profile"):
                continue
            selected.append([table, column])
            if len(selected) == 5:
                break
        # Retrying a partial observation must not spend another five-column budget.
        await graph.entities.update(eid, properties={"_profile_columns": selected})
    for table, column in selected:
        await profile_column(graph, db_path, table, column)


async def learn(graph, schema, q, outcome, verified_sql, hint=None, llm=None):
    assert_can_learn(q)
    if q.evidence:
        raise AssertionError("Learning must never receive BIRD evidence")
    schema = schema if isinstance(schema, Schema) else Schema(schema)
    eid = example_id(q.key)
    example = await graph.entities.get(eid)
    if example and example.properties.get("learning_complete"):
        return {"rules": [], "new_entities": [], "already_applied": True}
    parsed = parse_sql(verified_sql, schema)
    await graph.insert.facts(
        {
            "entities": [
                {
                    "id": eid,
                    "type": "Example",
                    "name": entity_label(q.question, 300),
                    "properties": {"sql": verified_sql, "key": q.key},
                }
            ]
        },
        source_id=q.key,
    )
    touches = [
        {"from_entity": eid, "type": "TOUCHES", "to_entity": cid}
        for cid in sorted(parsed.column_ids)
    ]
    for offset in range(0, len(touches), 400):
        await graph.insert.facts({"relations": touches[offset : offset + 400]}, source_id=q.key)
    # Source markers make retries safe even after a partly committed auto-commit write.
    for a, b in sorted(parsed.joins):
        low, high = sorted((column_id(*a), column_id(*b)))
        rid = relation_id(low, "JOINS", high)
        existing = await graph.relations.get(rid)
        if not existing:
            await graph.relations.create(
                low,
                "JOINS",
                high,
                properties={
                    "declared": False,
                    "wins": 1,
                    "losses": 0,
                    "_win_sources": [q.key],
                },
            )
        elif not certified(existing) and q.key not in existing.properties.get("_win_sources", []):
            await graph.relations.update(
                rid,
                set_properties={
                    "wins": existing.properties.get("wins", 0) + 1,
                    "_win_sources": [*existing.properties.get("_win_sources", []), q.key],
                },
            )
    for rid in outcome.trace.get("rules", []):
        r = await graph.relations.get(rid)
        if not r or certified(r) or q.key in r.properties.get("_feedback_sources", []):
            continue
        field = "wins" if outcome.correct else "losses"
        if not outcome.correct and r.to_entity in parsed.column_ids:
            continue
        await graph.relations.update(
            rid,
            set_properties={
                field: r.properties.get(field, 0) + 1,
                "_feedback_sources": [*r.properties.get("_feedback_sources", []), q.key],
            },
        )
    learned, new_entities = [], [eid]
    if not outcome.correct:
        await profile_unseen_columns(graph, q.db_path, parsed.filter_columns, eid)
        lines = []
        for table, column in sorted(parsed.columns):
            entity = await graph.entities.get(column_id(table, column))
            props = entity.properties if entity else {}
            lines.append(
                f"{table}.{column} | {schema[table][column]} | "
                f"{props.get('description', '')} | "
                f"Stored value definitions: {props.get('value_description', '')} | "
                f"Sample values: {props.get('profile', '')}"
            )
        if llm is None:
            from lore.llm import LLM

            llm = LLM()
            own_client = True
        else:
            own_client = False
        try:
            response = await llm.complete(
                REFLECTION.format(
                    question=q.question,
                    predicted_sql=outcome.sql,
                    correct_sql=verified_sql,
                    error=outcome.error or "It ran but returned a different result.",
                    hint=f"Analyst hint: {hint}" if hint else "",
                    columns="\n".join(lines),
                )
            )
        finally:
            if own_client:
                await llm.close()
        for rule in validate_rules(
            response.text, schema, allowed_columns={".".join(pair) for pair in parsed.columns}
        ):
            inserted = await graph.insert.facts(
                {
                    "entities": [
                        {
                            "type": "Term",
                            "name": rule["term"],
                        }
                    ]
                },
                source_id=q.key,
                resolver="default",
            )
            term = inserted.entities[0]
            new_entities.append(term.id)
            accepted, blocked = False, False
            for name in rule["columns"]:
                table, column = next(
                    pair for pair in parsed_or_all(schema) if ".".join(pair) == name
                )
                cid = column_id(table, column)
                rid = relation_id(term.id, "MEANS", cid)
                existing = await graph.relations.get(rid)
                props = {k: rule[k] for k in ("sql", "note")}
                props.update(wins=0, losses=0, origin=q.key)
                if not existing:
                    await graph.relations.create(term.id, "MEANS", cid, properties=props)
                    learned.append({"id": rid, "term": term.name, **props})
                    accepted = True
                elif existing.properties.get("sql") == rule["sql"]:
                    accepted = True
                elif (
                    not certified(existing)
                    and existing.properties.get("sql") != rule["sql"]
                    and reliability(existing) < 0.5
                ):
                    await graph.relations.update(rid, set_properties=props)
                    learned.append({"id": rid, "term": term.name, **props})
                    accepted = True
                else:
                    blocked = True
            # Aliases belong to the accepted meaning, not a rejected correction.
            # This also remains safe when retrying partly committed learning.
            if accepted and not blocked and rule["aliases"]:
                aliases = list(dict.fromkeys([*term.aliases, *rule["aliases"]]))
                if aliases != term.aliases:
                    await graph.entities.update(term.id, aliases=aliases)
    await graph.entities.update(eid, properties={"learning_complete": True})
    return {"rules": learned, "new_entities": new_entities, "already_applied": False}


def parsed_or_all(schema):
    return [(table, column) for table in schema for column in schema[table]]
