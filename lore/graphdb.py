import asyncio

from selfgraph import HydraDBStore, SelfGraph

from lore.config import settings


async def open_graph(ns):
    store = HydraDBStore(settings.bolt_uri, auth=("neo4j", settings.hydra_token))
    graph = SelfGraph(store=store, namespace=ns, max_tier="balanced")
    await graph.initialize()
    return graph


async def close_graph(graph):
    await graph.close()


class GraphReader:
    def __init__(self, graph, frozen=False):
        self.graph = graph
        self.frozen = frozen
        self.cache = {}

    def freeze(self, frozen=True):
        self.frozen = frozen
        self.cache.clear()

    async def _read(self, key, read):
        if not self.frozen:
            return await read()
        if key not in self.cache:
            self.cache[key] = asyncio.create_task(read())
        task = self.cache[key]
        try:
            return await asyncio.shield(task)
        except Exception:
            if self.cache.get(key) is task:
                self.cache.pop(key)
            raise

    async def seeds(self, question, k=30):
        async def read():
            result = await self.graph.retrieve(question, depth=0, k=k, max_nodes=max(1, k))
            maximum = max((seed.score for seed in result.seeds), default=1) or 1
            return {seed.id: max(0, min(1, seed.score / maximum)) for seed in result.seeds}

        return await self._read(("seeds", question, k), read)

    async def _relations(self, **kwargs):
        result = []
        cursor = None
        while True:
            page = await self.graph.relations.list(**kwargs, cursor=cursor, limit=200)
            result.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                return result

    async def out(self, entity_id, rel_type):
        return await self._read(
            ("out", entity_id, rel_type),
            lambda: self._relations(from_entity=entity_id, type=rel_type),
        )

    async def inc(self, entity_id, rel_type):
        return await self._read(
            ("inc", entity_id, rel_type),
            lambda: self._relations(to_entity=entity_id, type=rel_type),
        )

    async def all(self, rel_type):
        async def read():
            return [r async for r in self.graph.relations.iterate(type=rel_type)]

        return await self._read(("all", rel_type), read)

    async def entity(self, entity_id):
        return await self._read(("entity", entity_id), lambda: self.graph.entities.get(entity_id))
