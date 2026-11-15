"""Public demo API. Benchmark namespaces and shared learned facts are never trained here."""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import sqlite3
import time
import unicodedata
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anthropic
import sqlglot
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from selfgraph import entity_id
from sqlglot import exp

from lore.bird import (
    Question,
    db_path,
    description_dir,
    extract_sql,
    insert_knowledge,
    paths,
    render_prompt,
)
from lore.config import ROOT, settings
from lore.graphdb import GraphReader, open_graph
from lore.ground import ground
from lore.ids import example_id, table_id
from lore.learn import learn
from lore.llm import LLM, request_guard
from lore.schema_ingest import ingest_schema
from lore.seeds import import_seeds
from lore.sqlexec import execute_table
from lore.systems import Outcome
from lore.text import entity_label, trace_summary

Mode = Literal["trained", "sandbox"]
Session = str


class Input(BaseModel):
    @field_validator("*")
    @classmethod
    def valid_text(cls, value):
        if isinstance(value, str) and any(
            unicodedata.category(c) == "Cs"
            or (unicodedata.category(c) == "Cc" and c not in "\n\r\t")
            for c in value
        ):
            raise ValueError("Text contains an unsupported control or Unicode character")
        return value


class Scope(Input):
    db: str = Field(max_length=80)
    mode: Mode = "sandbox"
    session: Session = Field(default="", max_length=32)


class Ask(Scope):
    question: str = Field(min_length=1, max_length=4000)


class Feedback(Input):
    ask_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    verdict: Literal["up", "down", "confirm"]
    hint: str | None = Field(default=None, max_length=2000)
    corrected_sql: str | None = Field(default=None, max_length=20000)
    sql: str | None = Field(default=None, max_length=20000)


class Certify(Scope):
    relation_id: str = Field(min_length=1, max_length=500)


class Reset(Input):
    session: str = Field(pattern=r"^[a-f0-9]{32}$")
    db: str = Field(max_length=80)


def validate_sql(sql):
    try:
        statements = [node for node in sqlglot.parse(sql, read="sqlite") if node is not None]
    except sqlglot.errors.ParseError as exc:
        raise HTTPException(400, "SQL could not be parsed as a single read-only query") from exc
    if (
        len(statements) != 1
        or not isinstance(statements[0], exp.Query)
        or any(isinstance(node, (exp.DDL, exp.DML, exp.Command)) for node in statements[0].walk())
        or statements[0].find(exp.Into)
    ):
        raise HTTPException(400, "Only one SELECT or WITH query is allowed")
    return sql


class AppState:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS calls (ip TEXT, at REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS calls_at ON calls(at)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions (key TEXT PRIMARY KEY, generation TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS asks (id TEXT PRIMARY KEY, at REAL, record TEXT)"
            )
            db.execute("CREATE TABLE IF NOT EXISTS namespaces (id TEXT PRIMARY KEY)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, ip, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM calls WHERE at < ?", (min(now - 3600, now // 86400 * 86400),))
            hourly = db.execute(
                "SELECT COUNT(*) FROM calls WHERE ip=? AND at>?", (ip, now - 3600)
            ).fetchone()[0]
            daily = db.execute(
                "SELECT COUNT(*) FROM calls WHERE at>=?", (now // 86400 * 86400,)
            ).fetchone()[0]
            if hourly >= 30:
                raise HTTPException(
                    429, "This IP has reached the hourly LLM-call limit. Try again later."
                )
            if daily >= 2000:
                raise HTTPException(
                    429, "The demo has reached its daily LLM-call limit. Please return tomorrow."
                )
            db.execute("INSERT INTO calls VALUES (?, ?)", (ip, now))

    def namespace(self, db_id, mode, session):
        if mode == "trained":
            return f"app.trained.{db_id}"
        import re

        if not re.fullmatch(r"[a-f0-9]{32}", session):
            raise HTTPException(400, "A sandbox needs a random browser session identifier")
        key = f"{session}.{db_id}"
        with self.connect() as db:
            row = db.execute("SELECT generation FROM sessions WHERE key=?", (key,)).fetchone()
        return f"app.sbx.{session}{'-' + row[0] if row else ''}.{db_id}"

    def reset(self, db_id, session):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?, ?)",
                (f"{session}.{db_id}", uuid4().hex[:8]),
            )

    def save_ask(self, ask_id, record):
        self.save_asks({ask_id: record})

    def save_asks(self, records):
        with self.connect() as db:
            db.execute("DELETE FROM asks WHERE at < ?", (time.time() - 86400,))
            db.executemany(
                "INSERT OR REPLACE INTO asks VALUES (?, ?, ?)",
                [(ask_id, time.time(), json.dumps(record)) for ask_id, record in records.items()],
            )

    def known_namespace(self, namespace):
        with self.connect() as db:
            return (
                db.execute("SELECT 1 FROM namespaces WHERE id=?", (namespace,)).fetchone()
                is not None
            )

    def register_namespace(self, namespace):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO namespaces VALUES (?)", (namespace,))

    def ask(self, ask_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT record FROM asks WHERE id=? AND at>=?", (ask_id, time.time() - 86400)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Answer not found or expired; ask the question again")
        return json.loads(row[0])


@dataclass
class Context:
    db: str
    namespace: str
    graph: object
    schema: dict
    reader: GraphReader
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def json_value(value):
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


async def learned_graph(context, trace=None, new=()):
    trace = trace or {}
    used = set(trace.get("rules", [])) | set(trace.get("joins", []))
    seeds = set(trace.get("seeds", {}))
    columns = set(trace.get("columns", []))
    new = set(new)
    entities = {e.id: e async for e in context.graph.entities.iterate()}
    relations = [r async for r in context.graph.relations.iterate()]
    edges, wanted = [], set()
    for r in relations:
        if r.type == "TOUCHES" and r.from_entity in trace.get("examples", []):
            used.add(r.id)
        if r.type not in ("MEANS", "JOIN_PATH") and r.id not in used:
            continue
        wanted.update((r.from_entity, r.to_entity))
        p = r.properties
        edges.append(
            {
                "id": r.id,
                "source": r.from_entity,
                "target": r.to_entity,
                "type": r.type,
                "wins": p.get("wins", 0),
                "losses": p.get("losses", 0),
                "certified": bool(r.certified_at),
                "used": r.id in used,
                "sql": p.get("sql", p.get("from_sql", "")),
                "note": p.get("note", ""),
            }
        )
    wanted |= columns | seeds | new
    for key in list(wanted):
        entity = entities.get(key)
        if entity and entity.type == "Column":
            wanted.add(table_id(entity.properties["table"]))
    for r in relations:
        if r.type == "HAS_COLUMN" and r.from_entity in wanted and r.to_entity in wanted:
            edges.append(
                {
                    "id": r.id,
                    "source": r.from_entity,
                    "target": r.to_entity,
                    "type": r.type,
                    "wins": 0,
                    "losses": 0,
                    "certified": False,
                    "used": False,
                }
            )
    used_nodes = {key for r in edges if r["used"] for key in (r["source"], r["target"])}
    nodes = [
        {
            "id": key,
            "type": entities[key].type,
            "label": entities[key].name,
            "state": "new"
            if key in new
            else "used"
            if key in used_nodes
            else "seed"
            if key in seeds
            else "reached",
        }
        for key in sorted(wanted)
        if key in entities
    ]
    return {"nodes": nodes, "edges": edges}


class Service:
    def __init__(self, state_dir=None, run=None, llm=None):
        state_dir = Path(state_dir or os.getenv("LORE_STATE_DIR", str(settings.data_dir)))
        self.run = run or os.getenv("LORE_RESULTS_RUN", "r2")
        self.state = AppState(state_dir / "app.sqlite")
        self.llm = llm or LLM("app", cfg=replace(settings, data_dir=state_dir))
        self.contexts, self.create_lock = {}, asyncio.Lock()
        manifest = ROOT / "results" / self.run / "demo.json"
        if manifest.exists():
            self.demo = json.loads(manifest.read_text())
        else:
            # Development mode only. Final selection must come from measured per-database gains.
            schema_path = ROOT / "results" / self.run / "schema.json"
            schema = json.loads(schema_path.read_text()) if schema_path.exists() else {}
            available = [
                db
                for db in sorted(paths()["databases"])
                if db_path(db).exists() and db_path(db).stat().st_size < 100_000_000
            ][:4]
            self.demo = {
                "selection_status": "provisional; final benchmark selection pending",
                "databases": [
                    {"id": db, "tables": schema.get(db, {}).get("tables"), "suggestions": []}
                    for db in available
                ],
            }
        self.dbs = {db["id"]: db for db in self.demo["databases"]}

    async def startup(self):
        for db in self.dbs:
            if (ROOT / "seeds" / f"{db}.json").exists():
                await self.context(db, "trained", "")

    async def context(self, db, mode, session, create=True):
        if db not in self.dbs:
            raise HTTPException(404, "Unknown demo database")
        namespace = self.state.namespace(db, mode, session)
        if namespace in self.contexts:
            return self.contexts[namespace]
        known = self.state.known_namespace(namespace)
        if not create and not known:
            return None
        async with self.create_lock:
            if namespace in self.contexts:
                return self.contexts[namespace]
            if len(self.contexts) >= 128:
                raise HTTPException(
                    503, "Sandbox capacity reached. Please reuse an existing sandbox."
                )
            seed_path = ROOT / "seeds" / f"{db}.json"
            if mode == "trained" and not seed_path.exists():
                raise HTTPException(
                    503, "Trained seeds are not ready yet. You can use an empty sandbox."
                )
            graph = await open_graph(namespace)
            try:
                if mode == "trained":
                    digest = hashlib.sha256(seed_path.read_bytes()).hexdigest()
                    marker_id = entity_id("AppState", "seed-import")
                    marker = await graph.entities.get(marker_id)
                    if not marker or marker.properties.get("digest") != digest:
                        schema = await import_seeds(graph, seed_path, db)
                        await graph.insert.facts(
                            {
                                "entities": [
                                    {
                                        "id": marker_id,
                                        "type": "AppState",
                                        "name": "seed-import",
                                        "properties": {"digest": digest},
                                    }
                                ]
                            }
                        )
                    else:
                        from lore.schema_ingest import read_schema

                        schema, _ = await asyncio.to_thread(read_schema, db_path(db))
                elif known:
                    from lore.schema_ingest import read_schema

                    schema, _ = await asyncio.to_thread(read_schema, db_path(db))
                else:
                    schema = await ingest_schema(graph, db_path(db), description_dir(db))
                context = Context(db, namespace, graph, schema, GraphReader(graph))
                self.contexts[namespace] = context
                self.state.register_namespace(namespace)
                return context
            except Exception:
                await graph.close()
                raise

    async def answer(self, body, ip, proposal_of=None, hint=None):
        began = time.monotonic()
        if not body.question.strip():
            raise HTTPException(400, "Enter a question")
        context = await self.context(body.db, body.mode, body.session)
        async with context.lock:
            has_examples = bool((await context.graph.entities.list(type="Example", limit=1)).items)
            grounded = (
                await ground(context.reader, context.schema, body.question)
                if has_examples
                else None
            )
        block = grounded.block if grounded else ""
        trace = grounded.trace if grounded else {}
        question = body.question + (f"\nAnalyst hint: {hint}" if hint else "")
        prompt = insert_knowledge(render_prompt(body.db, question), block)
        completion = await self.llm.complete(prompt)
        sql = extract_sql(completion.text)
        try:
            validate_sql(sql)
            rows, error, _, columns = await execute_table(db_path(body.db), sql)
        except HTTPException as exc:
            rows, error, columns = None, exc.detail, []
        ask_id = uuid4().hex
        async with context.lock:
            if context.namespace != self.state.namespace(body.db, body.mode, body.session):
                raise HTTPException(409, "The sandbox was reset while answering. Please ask again.")
            await context.graph.decisions.create(
                title=entity_label(body.question, 120),
                id=f"decision:{ask_id}",
                steps=trace.get("rules", []) + trace.get("joins", []),
                summary=trace_summary(sql),
            )
            graph = await learned_graph(context, trace)
        record = {
            "db": body.db,
            "mode": body.mode,
            "session": body.session,
            "namespace": context.namespace,
            "question": body.question,
            "sql": sql,
            "error": error,
            "trace": trace,
            "hint": hint,
            "proposal_of": proposal_of,
            "root_ask": self.state.ask(proposal_of).get("root_ask", proposal_of)
            if proposal_of
            else ask_id,
        }
        self.state.save_ask(ask_id, record)
        return {
            "ask_id": ask_id,
            "sql": sql,
            "columns": columns,
            "rows": [[json_value(v) for v in row] for row in rows] if rows is not None else [],
            "error": error,
            "block": block,
            "graph": graph,
            "prompt_tokens": completion.input_tokens,
            "ms": int((time.monotonic() - began) * 1000),
            "proposal": bool(proposal_of),
        }

    async def feedback(self, body, ip):
        record = self.state.ask(body.ask_id)
        if record["mode"] != "sandbox":
            raise HTTPException(
                403, "The shared trained graph is read-only. Switch to a sandbox to teach Lore."
            )
        context = await self.context(record["db"], record["mode"], record["session"])
        if context.namespace != record["namespace"]:
            raise HTTPException(
                409, "That answer belongs to an old sandbox. Ask the question again."
            )
        if body.verdict == "down" and body.hint and not body.corrected_sql:
            if self.state.ask(record.get("root_ask", body.ask_id)).get("verified_sql"):
                raise HTTPException(
                    409, "This answer was already verified. Ask again for another correction."
                )
            return {
                "proposal": await self.answer(
                    Ask(**{k: record[k] for k in ("db", "mode", "session", "question")}),
                    ip,
                    proposal_of=body.ask_id,
                    hint=body.hint,
                )
            }
        if body.verdict == "up":
            if record["error"]:
                raise HTTPException(400, "A failed query cannot be confirmed as correct")
            sql, correct = record["sql"], True
        else:
            sql = body.sql if body.verdict == "confirm" else body.corrected_sql
            correct = False
            if not sql:
                raise HTTPException(
                    400, "Supply a hint or corrected SQL, then confirm the proposed query"
                )
        validate_sql(sql)
        rows, error, _, columns = await execute_table(db_path(record["db"]), sql)
        if error:
            raise HTTPException(400, "The verified SQL must execute successfully: " + error)
        async with context.lock:
            if context.namespace != self.state.namespace(
                record["db"], "sandbox", record["session"]
            ):
                raise HTTPException(409, "That sandbox has been reset")
            # Re-read inside the lock so overlapping feedback cannot apply two different corrections.
            record = self.state.ask(body.ask_id)
            root_id = record.get("root_ask", body.ask_id)
            original = self.state.ask(root_id)
            if original.get("verified_sql"):
                if original["verified_sql"] != sql:
                    raise HTTPException(
                        409, "This answer was already verified with different SQL. Ask again."
                    )
                return original["feedback"]
            previous = await context.graph.entities.get(example_id("u" + root_id))
            if previous and previous.properties["sql"] != sql:
                raise HTTPException(
                    409, "A different correction is partly applied. Retry that correction first."
                )
            q = Question(
                "u" + root_id,
                record["db"],
                record["question"],
                "",
                sql,
                "",
                db_path(record["db"]),
            )
            result = await learn(
                context.graph,
                context.schema,
                q,
                Outcome(
                    original["sql"],
                    not original["error"],
                    original["error"],
                    correct and not record.get("proposal_of"),
                    original["trace"],
                ),
                sql,
                hint=body.hint or record.get("hint"),
                llm=self.llm,
            )
            graph = await learned_graph(context, new=result["new_entities"])
            response = {
                "learned": result["rules"],
                "graph": graph,
                "verified": {
                    "sql": sql,
                    "columns": columns,
                    "error": None,
                    "rows": [[json_value(v) for v in row] for row in rows],
                },
            }
            record.update(verified_sql=sql, feedback=response)
            original.update(verified_sql=sql, feedback=response)
            self.state.save_asks({body.ask_id: record, root_id: original})
            return response

    async def close(self):
        await asyncio.gather(*(c.graph.close() for c in self.contexts.values()))
        await self.llm.close()


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = service or Service()
        await app.state.service.startup()
        try:
            yield
        finally:
            await app.state.service.close()

    app = FastAPI(title="Lore", lifespan=lifespan)

    @app.exception_handler(anthropic.APIError)
    async def model_error(request, exc):
        logging.getLogger(__name__).warning("Model request failed (%s)", type(exc).__name__)
        return JSONResponse(
            {
                "detail": "The model is temporarily unavailable. Retry the same action to finish safely."
            },
            status_code=503,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc):
        # Do not echo invalid input, including unencodable Unicode, in the response.
        return JSONResponse(
            {"detail": "Invalid request data: " + exc.errors()[0]["msg"]},
            status_code=422,
        )

    @app.middleware("http")
    async def limits(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 50_000:
                    return JSONResponse({"detail": "Request body is too large"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        ip = request.client.host if request.client else "unknown"
        if os.getenv("LORE_BEHIND_CLOUDFLARE") == "1" and request.url.path in (
            "/api/ask",
            "/api/feedback",
        ):
            try:
                ip = str(ipaddress.ip_address(request.headers.get("cf-connecting-ip", "")))
            except ValueError:
                return JSONResponse(
                    {"detail": "Missing trusted tunnel client address"}, status_code=400
                )
        # Trust only the peer address; do not let a caller spoof X-Forwarded-For.
        digest = hmac.new(settings.hydra_token.encode(), ip.encode(), hashlib.sha256).hexdigest()

        async def reserve():
            app.state.service.state.reserve(digest)

        token = request_guard.set(reserve)
        request.state.ip = digest
        try:
            return await call_next(request)
        finally:
            request_guard.reset(token)

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/api/dbs")
    async def databases():
        result = []
        for db, info in app.state.service.dbs.items():
            context = await app.state.service.context(db, "trained", "", create=False)
            count = len(await context.reader.all("MEANS")) if context else None
            result.append({**info, "rules": count, "trained": context is not None})
        return {"databases": result, "selection_status": app.state.service.demo["selection_status"]}

    @app.post("/api/ask")
    async def ask(body: Ask, request: Request):
        return await app.state.service.answer(body, request.state.ip)

    @app.post("/api/feedback")
    async def feedback(body: Feedback, request: Request):
        return await app.state.service.feedback(body, request.state.ip)

    @app.get("/api/graph")
    async def graph(db: str, mode: Mode, session: str = ""):
        context = await app.state.service.context(db, mode, session, create=False)
        return await learned_graph(context) if context else {"nodes": [], "edges": []}

    @app.post("/api/certify")
    async def certify(body: Certify):
        if body.mode != "sandbox":
            raise HTTPException(403, "Only sandbox rules can be certified by visitors")
        context = await app.state.service.context(body.db, body.mode, body.session, create=False)
        if not context:
            raise HTTPException(404, "Sandbox not found")
        async with context.lock:
            if context.namespace != app.state.service.state.namespace(
                body.db, body.mode, body.session
            ):
                raise HTTPException(409, "That sandbox has been reset")
            relation = await context.graph.relations.get(body.relation_id)
            if not relation or relation.type != "MEANS":
                raise HTTPException(404, "Rule not found")
            await context.graph.relations.certify(relation.id, by="analyst")
            return await learned_graph(context)

    @app.post("/api/sandbox/reset")
    async def reset(body: Reset):
        service = app.state.service
        context = await service.context(body.db, "sandbox", body.session, create=False)
        if context:
            async with context.lock:
                service.state.reset(body.db, body.session)
        else:
            service.state.reset(body.db, body.session)
        return {"graph": {"nodes": [], "edges": []}}

    @app.get("/api/results")
    async def results():
        target = ROOT / "results" / app.state.service.run
        return {
            name: json.loads((target / f"{name}.json").read_text())
            if (target / f"{name}.json").exists()
            else None
            for name in ("summary", "load")
        }

    dist = ROOT / "web/dist"
    if dist.exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
