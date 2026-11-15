"""Request-local anchored join reads, without caching mutable graph state."""

import asyncio
from contextvars import ContextVar

from lore.graphdb import GraphReader
from lore.ground import ground as _ground
from lore.schema_ingest import Schema

_scope = ContextVar("lore_ground_scope", default=None)


class LiveGraphReader(GraphReader):
    def __init__(self, graph, schema):
        super().__init__(graph, frozen=False)
        self.schema = schema if isinstance(schema, Schema) else Schema(schema)
        self.ground_slots = asyncio.Semaphore(1)

    async def entity(self, entity_id):
        scope = _scope.get()
        if scope is not None and scope[0] is self and entity_id in self.schema.by_id:
            scope[1].add(entity_id)
        return await super().entity(entity_id)

    async def all(self, rel_type):
        scope = _scope.get()
        if rel_type != "JOINS" or scope is None or scope[0] is not self:
            return await super().all(rel_type)
        tables = {self.schema.by_id[cid][0] for cid in scope[1]}
        # Grounding retains joins only when both endpoint tables were reached.
        # Read every source column of those tables, not just the selected columns.
        sources = [cid for cid, column in self.schema.by_id.items() if column[0] in tables]
        groups = await asyncio.gather(*(self.out(cid, rel_type) for cid in sources))
        return [relation for group in groups for relation in group]


async def ground(reader, schema, question, cfg=None):
    # Queue whole requests, rather than flooding four driver connections with
    # hundreds of each request's child reads. Callers time this wait as well.
    async with reader.ground_slots:
        token = _scope.set((reader, set()))
        try:
            return await _ground(reader, schema, question, cfg)
        finally:
            _scope.reset(token)
