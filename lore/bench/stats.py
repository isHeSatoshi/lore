from lore.graphdb import open_graph
from lore.ground import hidden


async def graph_counts(run, dbs):
    counts = {}
    for db in dbs:
        graph = await open_graph(f"{run}.lore.{db}")
        try:
            entities = [e async for e in graph.entities.iterate()]
            relations = [r async for r in graph.relations.iterate()]
            rules = [r for r in relations if r.type == "MEANS"]
            merges = await graph.run_cypher(
                "MATCH (n:EntityMerge {ns: $ns}) RETURN count(n.id) AS n",
                {"ns": f"{run}.lore.{db}"},
            )
            counts[db] = {
                "entities": len(entities),
                "relations": len(relations),
                "rules": len(rules),
                "rules_hidden": sum(hidden(r) for r in rules),
                "joins_learned": sum(
                    r.type == "JOINS" and r.properties.get("wins", 0) > 0 for r in relations
                ),
                "columns_profiled": sum(
                    e.type == "Column" and bool(e.properties.get("profile")) for e in entities
                ),
                "examples": sum(e.type == "Example" for e in entities),
                "merges": merges.rows[0]["n"] if merges.rows else 0,
            }
        finally:
            await graph.close()
    return {
        "per_db": counts,
        "total": {
            key: sum(c[key] for c in counts.values()) for key in next(iter(counts.values()), {})
        },
    }
