"""Export every learned rule with its stream source for the required manual review."""

import argparse
import asyncio
import json
from collections import Counter

from lore.bird import load_stream
from lore.config import ROOT, settings
from lore.graphdb import open_graph
from lore.ground import certified
from lore.ids import example_id


async def inspect(run):
    directory = settings.data_dir / "runs" / run
    metadata = json.loads((directory / "metadata.json").read_text())
    streams = load_stream(metadata["seed"], metadata["stream_cap"])
    questions = {q.key: q for group in streams.values() for q in group}
    records = []
    for db in metadata["dbs"]:
        state = directory / f"state.lore.{db}.json"
        if not state.exists() or not json.loads(state.read_text())["complete"]:
            raise RuntimeError(f"Finish Lore learning/evaluation for {db} before final rule review")
        graph = await open_graph(f"{run}.lore.{db}")
        try:
            relations = [r async for r in graph.relations.iterate(type="MEANS")]
            for relation in sorted(relations, key=lambda r: r.id):
                origin = relation.properties.get("origin")
                if origin not in questions or questions[origin].db_id != db:
                    raise AssertionError("A benchmark rule has no valid disjoint stream source")
                question = questions[origin]
                term = await graph.entities.get(relation.from_entity)
                column = await graph.entities.get(relation.to_entity)
                example = await graph.entities.get(example_id(origin))
                records.append(
                    {
                        "db": db,
                        "id": relation.id,
                        "term": term.name,
                        "aliases": term.aliases,
                        "column": column.name,
                        "sql": relation.properties["sql"],
                        "note": relation.properties.get("note", ""),
                        "origin": origin,
                        "wins": relation.properties.get("wins", 0),
                        "losses": relation.properties.get("losses", 0),
                        "certified": bool(certified(relation)),
                        "source_question": question.question,
                        "source_gold_sql": question.gold_sql,
                        "source_verified_sql": example.properties["sql"] if example else None,
                    }
                )
        finally:
            await graph.close()
    target = ROOT / "results" / run / "rules.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(records, indent=2) + "\n")
    print(
        json.dumps(
            {
                "file": str(target.relative_to(ROOT)),
                "rules": len(records),
                "per_db": dict(Counter(r["db"] for r in records)),
            },
            indent=2,
        )
    )
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    asyncio.run(inspect(args.run))
