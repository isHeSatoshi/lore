import argparse
import asyncio
import json
from pathlib import Path

from lore.bird import db_path, description_dir, paths
from lore.config import ROOT, settings
from lore.graphdb import open_graph
from lore.schema_ingest import ingest_schema


def validate_seeds(facts):
    for entity in facts.get("entities", []):
        if entity["type"] == "Example" and entity.get("properties", {}).get("key", "").startswith(
            "t"
        ):
            raise ValueError("A held-out example cannot be imported as learned knowledge")
    for relation in facts.get("relations", []):
        if relation["type"] == "MEANS" and relation.get("properties", {}).get(
            "origin", ""
        ).startswith("t"):
            raise ValueError("A held-out rule cannot be imported as learned knowledge")


async def export_graph(graph):
    entities = []
    for entity in [e async for e in graph.entities.iterate()]:
        if entity.type in ("Term", "Example"):
            entities.append(
                {
                    "id": entity.id,
                    "type": entity.type,
                    "name": entity.name,
                    "aliases": entity.aliases,
                    "properties": entity.properties,
                }
            )
        elif entity.type == "Column" and entity.properties.get("profile"):
            entities.append(
                {
                    "id": entity.id,
                    "type": entity.type,
                    "name": entity.name,
                    "properties": {"profile": entity.properties["profile"]},
                }
            )
    relations = []
    for kind in ("MEANS", "TOUCHES", "JOIN_PATH", "JOINS"):
        async for r in graph.relations.iterate(type=kind):
            if kind == "JOINS" and r.properties.get("declared") and not r.properties.get("wins"):
                continue
            props = dict(r.properties)
            if r.certified_at:
                props["_seed_certified_by"] = r.certified_by or "analyst"
            relations.append(
                {
                    "from_entity": r.from_entity,
                    "type": r.type,
                    "to_entity": r.to_entity,
                    "properties": props,
                }
            )
    facts = {"entities": entities, "relations": relations}
    validate_seeds(facts)
    return facts


async def import_seeds(graph, path, db_id=None):
    path = Path(path)
    db_id = db_id or path.stem
    facts = json.loads(path.read_text())
    validate_seeds(facts)
    schema = await ingest_schema(graph, db_path(db_id), description_dir(db_id))
    for offset in range(0, len(facts["entities"]), 200):
        await graph.insert.facts({"entities": facts["entities"][offset : offset + 200]})
    for offset in range(0, len(facts["relations"]), 400):
        await graph.insert.facts({"relations": facts["relations"][offset : offset + 400]})
    from selfgraph import relation_id

    for r in facts["relations"]:
        if by := r["properties"].get("_seed_certified_by"):
            await graph.relations.certify(
                relation_id(r["from_entity"], r["type"], r["to_entity"]), by=by
            )
    return schema


async def export(run, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"run": run, "databases": {}}
    for db in sorted(paths()["databases"]):
        state_path = settings.data_dir / "runs" / run / f"state.lore.{db}.json"
        if not state_path.exists() or not json.loads(state_path.read_text())["complete"]:
            raise RuntimeError(f"Cannot publish seeds from an unfinished Lore run: {db}")
        graph = await open_graph(f"{run}.lore.{db}")
        try:
            facts = await export_graph(graph)
        finally:
            await graph.close()
        (out / f"{db}.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")
        manifest["databases"][db] = {
            "entities": len(facts["entities"]),
            "relations": len(facts["relations"]),
        }
    target = ROOT / "results" / run
    target.mkdir(parents=True, exist_ok=True)
    (target / "seeds.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("export")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True, type=Path)
    p = commands.add_parser("import")
    p.add_argument("--namespace", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "export":
        asyncio.run(export(args.run, args.out.resolve()))
    else:

        async def restore():
            graph = await open_graph(args.namespace)
            try:
                await import_seeds(graph, args.file.resolve(), args.db)
            finally:
                await graph.close()

        asyncio.run(restore())
