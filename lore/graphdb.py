from selfgraph import HydraDBStore, SelfGraph

from lore.config import settings


async def open_graph(ns):
    store = HydraDBStore(settings.bolt_uri, auth=("neo4j", settings.hydra_token))
    graph = SelfGraph(store=store, namespace=ns, max_tier="balanced")
    await graph.initialize()
    return graph


async def close_graph(graph):
    await graph.close()
