import asyncio
import json
from uuid import uuid4

from selfgraph import entity_id

from lore.graphdb import open_graph


async def main():
    graph = await open_graph("smoke-" + uuid4().hex[:10])
    try:
        term = entity_id("Term", "school level")
        await graph.insert.facts(
            {
                "entities": [
                    {"id": "table:schools", "type": "Table", "name": "schools"},
                    {
                        "id": "column:schools.rtype",
                        "type": "Column",
                        "name": "schools.rtype",
                        "aliases": ["aliasquasar"],
                        "properties": {"description": "descriptionpulsar"},
                    },
                    {"type": "Term", "name": "school level"},
                ],
                "relations": [
                    {
                        "from_entity": "table:schools",
                        "type": "HAS_COLUMN",
                        "to_entity": "column:schools.rtype",
                    },
                    {
                        "from_entity": term,
                        "type": "MEANS",
                        "to_entity": "column:schools.rtype",
                        "properties": {"sql": "schools.rtype = 'S'", "wins": 0, "losses": 0},
                    },
                ],
            }
        )
        edges = (await graph.relations.list(from_entity=term, type="MEANS")).items
        assert len(edges) == 1 and edges[0].properties["wins"] == 0
        await graph.relations.update(edges[0].id, set_properties={"wins": 1})
        versions = await graph.relations.versions(edges[0].id)
        assert len(versions) == 2, versions
        print("MEANS properties and two revisions: PASS")
        depth = 0
        try:
            result = await graph.retrieve("school level", depth=depth, k=10)
        except Exception as exc:
            print("depth=0 rejected:", type(exc).__name__)
            depth = 1
            result = await graph.retrieve("school level", depth=depth, k=10)
        print("depth", depth, "seeds", result.seeds)
        for word in ("aliasquasar", "descriptionpulsar"):
            r = await graph.retrieve(word, depth=depth, k=10)
            print("seeding field probe", word, r.seeds)
        merged = await graph.insert.facts(
            {"entities": [{"type": "Term", "name": "school levels"}]}, resolver="fuzzy"
        )
        print("fuzzy entity ids:", [e.id for e in merged.entities])
        print("fuzzy merges:", merged.merges)
        print("readiness:", json.dumps((await graph.readiness()).counts))
    finally:
        await graph.close()


if __name__ == "__main__":
    asyncio.run(main())
