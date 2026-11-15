"""Choose demo databases from measured gains, not from hand-picked success stories."""

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from lore.bench.run import read_answers
from lore.bird import db_path, description_dir, load_stream, load_test, paths
from lore.config import ROOT, settings
from lore.graphdb import open_graph
from lore.schema_ingest import read_schema


def select_databases(summary, sizes):
    if any(row["floor"] is None or row["lore"] is None for row in summary["per_db"]):
        raise ValueError("Finish floor and final Lore evaluation before selecting the demo")
    eligible = [row for row in summary["per_db"] if sizes[row["db_id"]] < 100_000_000]
    eligible.sort(key=lambda row: (-(row["lore"] - row["floor"]), row["db_id"]))
    if len(eligible) < 4:
        raise ValueError("Fewer than four measured databases meet the size limit")
    return eligible[:4]


async def build(run):
    result_dir = ROOT / "results" / run
    summary = json.loads((result_dir / "summary.json").read_text())
    directory = settings.data_dir / "runs" / run
    metadata = json.loads((directory / "metadata.json").read_text())
    sizes = {db: db_path(db).stat().st_size for db in paths()["databases"]}
    selected = select_databases(summary, sizes)
    streams = load_stream(metadata["seed"], metadata["stream_cap"])
    stream = {q.key: q for group in streams.values() for q in group}
    test = {q.key: q for q in load_test()}
    rows = read_answers(directory / "answers.jsonl")
    floor = {r["key"]: r for r in rows if r["system"] == "floor" and r["phase"] == "test"}
    replays_path = result_dir / "demo_replays.json"
    replays = json.loads(replays_path.read_text()) if replays_path.exists() else []
    demo = {
        "run": run,
        "selection_status": "measured Lore-minus-floor gain; database size under limit",
        "databases": [],
    }
    candidates = {}
    for row in selected:
        db = row["db_id"]
        graph = await open_graph(f"{run}.lore.{db}")
        try:
            relations = {r.id: r async for r in graph.relations.iterate(type="MEANS")}
            terms = {e.id: e async for e in graph.entities.iterate(type="Term")}
        finally:
            await graph.close()
        pairs, seen = [], set()
        for answer in rows:
            if (
                answer["system"] != "lore"
                or answer["phase"] != "test"
                or answer["checkpoint"] != 1.0
                or answer["db_id"] != db
                or not answer["correct"]
                or floor[answer["key"]]["correct"]
            ):
                continue
            for rid in answer["trace"].get("rules", []):
                relation = relations.get(rid)
                origin = relation.properties.get("origin") if relation else None
                if origin not in stream or (origin, answer["key"]) in seen:
                    continue
                seen.add((origin, answer["key"]))
                term = terms[relation.from_entity].name
                pairs.append(
                    {
                        "db": db,
                        "a": origin,
                        "b": answer["key"],
                        "relation_id": rid,
                        "question": stream[origin].question,
                        "hint": f"In this database, {term} means {relation.properties['sql']}.",
                        "followup": test[answer["key"]].question,
                    }
                )
        candidates[db] = pairs
        verified = [r["suggestion"] for r in replays if r.get("passed") and r.get("db") == db]
        # Only independently replayed pairs can be suggested. Otherwise offer honest single questions.
        suggestions = verified[:3] or [{"question": q.question} for q in streams[db][:3]]
        schema, _ = read_schema(db_path(db))
        demo["databases"].append(
            {
                "id": db,
                "tables": len(schema),
                "rules": row["rules"],
                "database_bytes": sizes[db],
                "gain_points": row["lore"] - row["floor"],
                "suggestions": suggestions,
                "suggestion_status": "replayed pairs"
                if verified
                else "single questions; no verified pair yet",
            }
        )
    (directory / "demo_candidates.json").write_text(json.dumps(candidates, indent=2) + "\n")
    (result_dir / "demo.json").write_text(json.dumps(demo, indent=2) + "\n")
    print(
        json.dumps(
            {
                "selected": [d["id"] for d in demo["databases"]],
                "candidate_pairs": {db: len(items) for db, items in candidates.items()},
            },
            indent=2,
        )
    )


def bundle(run, parent):
    manifest = json.loads((ROOT / "results" / run / "demo.json").read_text())
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix=f"{run}-demo-", dir=parent))
    bird = target / "data/bird"
    bird.mkdir(parents=True)
    shutil.copy2(ROOT / "DATA_LICENSE.md", bird / "DATA_LICENSE.md")
    layout = {"databases": {}, "descriptions": {}}
    for entry in manifest["databases"]:
        db = entry["id"]
        if db_path(db).stat().st_size >= 100_000_000:
            raise ValueError(f"Demo database no longer meets the size limit: {db}")
        relative = Path(paths()["databases"][db])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Database bundle paths must be portable")
        dest = bird / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path(db), dest)
        layout["databases"][db] = str(relative)
        if description_dir(db) and description_dir(db).exists():
            desc_relative = Path(paths()["descriptions"][db])
            if desc_relative.is_absolute() or ".." in desc_relative.parts:
                raise ValueError("Description paths must be portable")
            shutil.copytree(description_dir(db), bird / desc_relative)
            layout["descriptions"][db] = str(desc_relative)
    (bird / "minidev").mkdir()
    for file in ("sqlite.json", "prompt_template.txt"):
        shutil.copy2(settings.bird_dir / "minidev" / file, bird / "minidev" / file)
    (bird / "paths.json").write_text(json.dumps(layout, indent=2) + "\n")
    print(target.resolve())
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.bundle:
        bundle(args.run, args.bundle.resolve())
    else:
        asyncio.run(build(args.run))
