import asyncio
import json
from dataclasses import dataclass, field

from lore.schema_ingest import Schema

INTRO = (
    "Learned knowledge about this database, from earlier verified queries. "
    "Use it when it applies to the question."
)


def reliability(relation):
    p = relation.properties
    return (p.get("wins", 0) + 1) / (p.get("wins", 0) + p.get("losses", 0) + 2)


def certified(relation):
    return bool(relation.certified_at)


def hidden(relation):
    p = relation.properties
    return (
        p.get("wins", 0) + p.get("losses", 0) >= 3
        and reliability(relation) < 0.34
        and not certified(relation)
    )


@dataclass
class Grounding:
    rules: list = field(default_factory=list)
    values: list = field(default_factory=list)
    joins: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    block: str = ""
    trace: dict = field(default_factory=dict)


def render_block(items, limit=3600):
    """Items carry section, text, score and id; trim whole items and retain exact trace ids."""
    items = list(items)
    headings = (
        ("rules", "Rules:"),
        ("values", "Column values:"),
        ("joins", "Known joins:"),
        ("examples", "Verified examples:"),
    )

    def render():
        sections = [
            heading + "\n" + "\n".join(i["text"] for i in items if i["section"] == section)
            for section, heading in headings
            if any(i["section"] == section for i in items)
        ]
        return INTRO + "\n" + "\n".join(sections) + "\n\n" if sections else ""

    while items and limit is not None and len(render()) > limit:
        lowest = min(
            range(len(items)), key=lambda i: (items[i]["score"], -len(items[i]["text"]), i)
        )
        items.pop(lowest)
    return render(), items


def value_line(entity, small_only=True):
    try:
        profile = json.loads(entity.properties.get("profile", "{}"))
    except (TypeError, ValueError):
        return None
    if "distinct" not in profile or (small_only and profile["distinct"] > 25):
        return None
    values = ", ".join("NULL" if v is None else repr(v) for v in profile.get("top", []))
    return f"- {entity.name}: {values}"


async def ground(reader, schema, question, cfg=None):
    schema = schema if isinstance(schema, Schema) else Schema(schema)
    seeds = await reader.seeds(question, k=30)
    rules, cols = {}, {}

    def add_rule(r, score):
        if r.id not in rules or score > rules[r.id][1]:
            rules[r.id] = (r, score)
        if r.to_entity in schema.by_id:
            cols[r.to_entity] = max(cols.get(r.to_entity, 0), score)

    term_seeds = [(key, score) for key, score in seeds.items() if key.startswith("term:")]
    for (_tid, score), relations in zip(
        term_seeds,
        await asyncio.gather(*(reader.out(tid, "MEANS") for tid, _ in term_seeds)),
        strict=True,
    ):
        for r in relations:
            add_rule(r, score)
    column_seeds = [(key, score) for key, score in seeds.items() if key in schema.by_id]
    for (cid, score), relations in zip(
        column_seeds,
        await asyncio.gather(*(reader.inc(cid, "MEANS") for cid, _ in column_seeds)),
        strict=True,
    ):
        cols[cid] = max(cols.get(cid, 0), score)
        for r in relations:
            add_rule(r, 0.7 * score)
    ranked = sorted(
        (
            (r, score * reliability(r) * (1.5 if certified(r) else 1))
            for r, score in rules.values()
            if not hidden(r)
        ),
        key=lambda x: (-x[1], x[0].id),
    )
    top, seen = [], set()
    for r, score in ranked:
        sql = r.properties.get("sql", "").strip()
        if sql and sql not in seen:
            top.append((r, score))
            seen.add(sql)
        if len(top) == 8:
            break
    for r, score in top:
        if r.to_entity in schema.by_id:
            cols[r.to_entity] = max(cols.get(r.to_entity, 0), score)
    cols = dict(sorted(cols.items(), key=lambda x: (-x[1], x[0]))[:25])
    entities = await asyncio.gather(*(reader.entity(cid) for cid in cols))
    items = []
    for (r, score), term in zip(
        top, await asyncio.gather(*(reader.entity(r.from_entity) for r, _ in top)), strict=True
    ):
        if term:
            items.append(
                dict(
                    section="rules",
                    id=r.id,
                    score=score,
                    text=f"- {json.dumps(term.name, ensure_ascii=False)} means: {r.properties['sql']} "
                    f"(confirmed {r.properties.get('wins', 0)} times)",
                )
            )
    values = []
    for (cid, score), entity in zip(cols.items(), entities, strict=True):
        if entity and (line := value_line(entity)):
            values.append(dict(section="values", id=cid, text=line, score=score))
    items.extend(values[:5])
    counts = {}
    for (_cid, score), edges in zip(
        cols.items(),
        await asyncio.gather(*(reader.inc(cid, "TOUCHES") for cid in cols)),
        strict=True,
    ):
        for edge in edges:
            counts[edge.from_entity] = counts.get(edge.from_entity, 0) + score
    for key, score in seeds.items():
        if key.startswith("example:"):
            counts[key] = counts.get(key, 0) + 2 * score
    example_ids = sorted(counts, key=lambda key: (-counts[key], key))
    examples = []
    for eid in example_ids:
        entity = await reader.entity(eid)
        if entity and len(entity.properties.get("sql", "")) <= 3000:
            examples.append(entity)
        if len(examples) == 3:
            break
    maximum = max(counts.values(), default=1) or 1
    for entity in examples:
        items.append(
            dict(
                section="examples",
                id=entity.id,
                score=counts[entity.id] / maximum,
                text=f"Q: {entity.name}\nSQL: {entity.properties['sql']}",
            )
        )
    tables = {schema.by_id[cid][0] for cid in cols}
    joins = []
    for r in await reader.all("JOINS"):
        a, b = schema.by_id.get(r.from_entity), schema.by_id.get(r.to_entity)
        if a and b and a[0] in tables and b[0] in tables and not hidden(r):
            joins.append(r)
    joins.sort(key=lambda r: (-reliability(r), r.id))
    for r in joins[:6]:
        a, b = schema.by_id[r.from_entity], schema.by_id[r.to_entity]
        items.append(
            dict(
                section="joins",
                id=r.id,
                score=reliability(r),
                text=f"- {a[0]}.{a[1]} = {b[0]}.{b[1]}",
            )
        )
    limit = cfg.get("block_chars", 3600) if isinstance(cfg, dict) else 3600
    block, selected = render_block(items, limit)
    trace = {
        section: [i["id"] for i in selected if i["section"] == section]
        for section in ("rules", "joins", "examples")
    }
    trace.update(seeds=seeds, columns=list(cols), block_chars=len(block))
    return Grounding(
        rules=[r for r, _ in top if r.id in trace["rules"]],
        values=[i["text"] for i in selected if i["section"] == "values"],
        joins=[r for r in joins if r.id in trace["joins"]],
        examples=[e for e in examples if e.id in trace["examples"]],
        block=block,
        trace=trace,
    )
