import asyncio
from dataclasses import dataclass, field

from lore.bird import (
    Question,
    assert_can_learn,
    db_path,
    description_dir,
    insert_knowledge,
    published,
    render_prompt,
)
from lore.graphdb import GraphReader, open_graph
from lore.ground import ground, hidden, render_block, value_line
from lore.ids import example_id
from lore.learn import learn
from lore.schema_ingest import ingest_schema


@dataclass
class Outcome:
    sql: str
    rows_ok: bool
    error: str | None
    correct: bool
    trace: dict = field(default_factory=dict)


class System:
    name: str
    learns = False

    async def build_prompt(self, q: Question) -> tuple[str, dict]:
        raise NotImplementedError

    async def observe(self, q: Question, outcome: Outcome) -> None:
        return None

    async def freeze(self, frozen=True, db=None):
        return None

    async def close(self):
        return None


class Floor(System):
    name = "floor"

    async def build_prompt(self, q):
        return render_prompt(q.db_id, q.question), {}


class Ceiling(System):
    name = "ceiling"

    def __init__(self):
        self.prompts = {(r["db_id"], f"t{r['question_id']}"): r["prompt"] for r in published()}

    async def build_prompt(self, q):
        return self.prompts[(q.db_id, q.key)], {}


class Lore(System):
    name = "lore"
    learns = True

    def __init__(self, run, llm):
        self.run, self.llm = run, llm
        self.graphs, self.schemas, self.readers, self.has_knowledge = {}, {}, {}, {}
        self.frozen = set()

    @classmethod
    async def create(cls, run, dbs, llm):
        self = cls(run, llm)
        try:
            for db in dbs:
                graph = await open_graph(f"{run}.lore.{db}")
                self.graphs[db] = graph
                self.schemas[db] = await ingest_schema(graph, db_path(db), description_dir(db))
                self.readers[db] = GraphReader(graph)
                self.has_knowledge[db] = bool(
                    (await graph.entities.list(type="Example", limit=1)).items
                )
        except Exception:
            await self.close()
            raise
        return self

    async def build_prompt(self, q):
        floor = render_prompt(q.db_id, q.question)
        if not self.has_knowledge[q.db_id]:
            return floor, {"rules": [], "joins": [], "examples": [], "seeds": {}, "block_chars": 0}
        grounded = await ground(self.readers[q.db_id], self.schemas[q.db_id], q.question)
        return insert_knowledge(floor, grounded.block), grounded.trace

    async def observe(self, q, outcome):
        if not q.key.startswith("s"):
            raise AssertionError("Benchmark observations must be stream questions")
        if q.db_id in self.frozen:
            raise AssertionError("Cannot learn during a frozen test checkpoint")
        verified = outcome.sql if outcome.correct else q.gold_sql
        result = await learn(
            self.graphs[q.db_id],
            self.schemas[q.db_id],
            q.without_evidence(),
            outcome,
            verified,
            llm=self.llm,
        )
        self.has_knowledge[q.db_id] = True
        self.readers[q.db_id].freeze(False)
        return result

    async def freeze(self, frozen=True, db=None):
        for name in [db] if db else self.graphs:
            self.readers[name].freeze(frozen)
            if frozen:
                self.frozen.add(name)
            else:
                self.frozen.discard(name)

    async def close(self):
        await asyncio.gather(*(graph.close() for graph in self.graphs.values()))


class Vector(System):
    name = "vector"
    learns = True

    def __init__(self, embedder=None):
        if embedder is None:
            from lore.embeddings import Embedder

            embedder = Embedder()
        self.embedder = embedder
        self.items, self.frozen = {}, set()

    async def observe(self, q, outcome):
        assert_can_learn(q)
        if not q.key.startswith("s") or q.db_id in self.frozen:
            raise AssertionError("Only unfrozen stream questions can teach vector memory")
        db = self.items.setdefault(q.db_id, {})
        if q.key not in db:
            vector = (await self.embedder.embed([q.question]))[0]
            db[q.key] = (q.question, q.gold_sql, vector)

    async def build_prompt(self, q):
        items = list(self.items.get(q.db_id, {}).items())
        if not items:
            return render_prompt(q.db_id, q.question), {"examples": [], "block_chars": 0}
        vector = (await self.embedder.embed([q.question]))[0]
        scores = [(float(item[2] @ vector), key, item) for key, item in items]
        scores.sort(key=lambda x: (-x[0], x[1]))
        selected = [
            dict(
                section="examples",
                id=example_id(key),
                score=score,
                text=f"Q: {item[0]}\nSQL: {item[1]}",
            )
            for score, key, item in scores[:3]
        ]
        block, selected = render_block(selected)
        return insert_knowledge(render_prompt(q.db_id, q.question), block), {
            "examples": [i["id"] for i in selected],
            "block_chars": len(block),
        }

    async def freeze(self, frozen=True, db=None):
        for name in [db] if db else self.items:
            self.frozen.add(name) if frozen else self.frozen.discard(name)


class Flat(System):
    name = "flat"

    def __init__(self, embedder=None):
        if embedder is None:
            from lore.embeddings import Embedder

            embedder = Embedder()
        self.embedder, self.items, self.vectors = embedder, {}, {}

    @classmethod
    async def create(cls, source_run, dbs, embedder=None):
        self = cls(embedder)
        for db in dbs:
            graph = await open_graph(f"{source_run}.lore.{db}")
            try:
                entities = {e.id: e async for e in graph.entities.iterate()}
                items = []
                for r in [r async for r in graph.relations.iterate(type="MEANS")]:
                    if hidden(r):
                        continue
                    term = entities[r.from_entity]
                    p = r.properties
                    text = f"{term.name} means {p.get('sql', '')}. {p.get('note', '')}"
                    items.append(dict(section="rules", id=r.id, embed=text, text="- " + text))
                for entity in entities.values():
                    if entity.type == "Column" and (line := value_line(entity, small_only=False)):
                        items.append(dict(section="values", id=entity.id, embed=line, text=line))
                    elif entity.type == "Example":
                        text = f"Q: {entity.name}\nSQL: {entity.properties['sql']}"
                        items.append(dict(section="examples", id=entity.id, embed=text, text=text))
                self.items[db] = items
                self.vectors[db] = await self.embedder.embed([item["embed"] for item in items])
            finally:
                await graph.close()
        return self

    async def build_prompt(self, q):
        items = self.items.get(q.db_id, [])
        if not items:
            return render_prompt(q.db_id, q.question), {"block_chars": 0}
        vector = (await self.embedder.embed([q.question]))[0]
        scores = self.vectors[q.db_id] @ vector
        selected = []
        for section, limit in (("rules", 8), ("values", 3), ("examples", 3)):
            indices = [i for i, item in enumerate(items) if item["section"] == section]
            indices.sort(key=lambda i: (-float(scores[i]), items[i]["id"]))
            seen = set()
            for i in indices:
                # One reflected meaning can have a MEANS edge to several columns.
                # Repeated identical lines must not consume the retrieval budget.
                if items[i]["text"] in seen:
                    continue
                seen.add(items[i]["text"])
                selected.append({**items[i], "score": float(scores[i])})
                if len(seen) == limit:
                    break
        block, selected = render_block(selected)
        trace = {
            section: [i["id"] for i in selected if i["section"] == section]
            for section in ("rules", "examples")
        }
        trace["block_chars"] = len(block)
        return insert_knowledge(render_prompt(q.db_id, q.question), block), trace
