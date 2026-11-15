# Lore build spec

> For the model that builds this. Read `ABOUT_PROJECT.md` first for the what and why. This file is the how.
> Project root: `/mnt/bigdrive/aditya/projects/hydradb`, called ROOT below. All paths are relative to ROOT.
> Hard deadline: **16 Nov 2026, 9:00 AM IST**. Aim to submit by 8:30 AM.

## 0. Ground rules

1. **Work in milestone order** (section 6). Finish every P0 item before any P1 item. P2 only if everything else is done.
2. **Run the "Done when" check** of each milestone before moving on. Append one line per milestone to `PROGRESS.md`: time, milestone, pass or fail, one sentence.
3. **Never invent a number.** Every number in the README, the app or a post must come from a file under `results/` that the code produced.
4. **Never change the metric** to improve a result. The metric is strict execution accuracy (section 7).
5. **Two leak rules, each with a test:**
   - BIRD `evidence` text must never appear in a prompt of any system except `ceiling`.
   - A test question must never be used for learning.
6. **Secrets:** read keys from `.env`. Never print, log or commit them. `.env` is in `.gitignore`.
7. **Do not commit** `data/`, any `.sqlite` file, `.venv/`, `node_modules/`.
8. **Git:** `git init` at the start, one commit per milestone. Do not push and do not create a GitHub repo until the owner says yes.
9. **Time boxes:** if a P1 item is not working after its time box, stop, note it in `PROGRESS.md`, and move on.
10. **Stop and ask the owner** when: HydraDB will not start after 45 minutes, the LLM endpoint keeps failing, the floor-to-ceiling gap is under 5 points (M2), total input tokens for the run pass 80 million, or anything needs sudo.
11. **Read these first** (they are written for coding agents): HydraDB `USING-HYDRADB.md` and `AGENTS.md`, SelfGraph `SKILL.md` and `docs/` (links in section 2).
12. Run long jobs in the background with a log file. Do not block on them.

## 1. Clock (IST)

| Latest finish | Milestone |
|---|---|
| 4:00 PM | M0 environment |
| 5:30 PM | M1 data and evaluator |
| 6:30 PM | M2 floor and ceiling |
| 7:30 PM | M3 schema graph |
| 10:30 PM | M4 learning loop, first small curve |
| 11:00 PM | M5 full benchmark launched in the background |
| 1:00 AM | M6 load test, then P1 items |
| 4:00 AM | M7 app |
| 5:30 AM | M8 deploy |
| 6:30 AM | M9 README and submission pack |
| 8:30 AM | Owner submits |

Three times do not move even if earlier work slipped: **start the app by 1:00 AM**, **start deploying by 4:00 AM**, **freeze benchmark numbers at 4:00 AM** (whatever is finished then is what gets reported).

## 2. Fixed facts

### 2.1 Machine

Linux Mint 22.3 (Ubuntu 24.04 base), x86_64, 8 CPUs, 7.5 GB RAM (about 2.7 GB was free at planning time), Python 3.12.3, uv 0.12.5, Node 22, npm 10, git, gh (logged in). No passwordless sudo. Docker is installed by the owner before you start.

RAM is tight. Do not run the full benchmark, an embedding model and a frontend build at high concurrency all at once.

If `docker ps` says permission denied, the owner's shell has not picked up the `docker` group. Run docker commands as `sg docker -c "<command>"`.

### 2.2 `.env` (the owner creates it; create `.env.example` with the same keys and empty secrets)

```
LORE_LLM_BASE_URL=https://api.minimax.io/anthropic
LORE_LLM_API_KEY=
LORE_LLM_MODEL=MiniMax-M3.1-Flash
LORE_LLM_EFFORT=
LORE_LLM_MAX_TOKENS=8192
LORE_LLM_CONCURRENCY=8
HYDRA_TOKEN=
HYDRA_BOLT_URI=bolt://127.0.0.1:17687
HYDRA_ADMIN_URL=http://127.0.0.1:19091
HYDRA_HTTP_URL=http://127.0.0.1:18443
LORE_DATA_DIR=./data
```

`HYDRA_TOKEN` must be at least 32 characters. Generate one with `python3 -c "import secrets; print(secrets.token_hex(24))"`.

### 2.3 HydraDB (verified from its README, AGENTS.md and Dockerfile)

- Image: `ghcr.io/hydra-db/hydradb:0.4.0`, public. Entrypoint `/usr/local/bin/graph-node`. Runs as uid 10001. Container ports: 7687 Bolt, 8443 HTTP query API, 9090 admin.
- Health: `GET /readyz` and `GET /metrics` on the admin port. `/readyz` returns 200 with an empty body. `GET /healthz` is on the HTTP port.
- Auth is a bearer token. Over Bolt it is the password, with user `neo4j`.
- Graph id is `default`, cell id is `cell-0`.
- Docs: https://github.com/hydra-db/hydradb/blob/main/USING-HYDRADB.md and https://github.com/hydra-db/hydradb/blob/main/AGENTS.md

`docker-compose.yml` to start from. The env names come from HydraDB's AGENTS.md step 7. **This file has not been run yet. If the node exits, read `docker compose logs hydradb` and compare with that step.**

```yaml
name: lore
services:
  hydradb-init:
    image: ghcr.io/hydra-db/hydradb:0.4.0
    user: "0:0"
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        mkdir -p /data/store /data/cache
        printf '%s\n' "$$HYDRA_TOKEN" > /data/auth-token
        chown -R 10001:10001 /data
    environment:
      HYDRA_TOKEN: ${HYDRA_TOKEN:?set HYDRA_TOKEN in .env}
    volumes:
      - hydra_data:/data

  hydradb:
    image: ghcr.io/hydra-db/hydradb:0.4.0
    depends_on:
      hydradb-init:
        condition: service_completed_successfully
    restart: unless-stopped
    environment:
      CLOUD_PROVIDER: local
      LOCAL_PATH: /data/store
      GRAPH_NAMESPACE: local
      GRAPH_ID: default
      GRAPH_CELL_ID: cell-0
      GRAPH_CELLS: cell-0
      GRAPH_DATA_PATH: data
      GRAPH_ALLOW_PLAINTEXT: "true"
      GRAPH_AUTH_TOKEN_FILE: /data/auth-token
      GRAPH_DATA_CACHE_BYTES: "268435456"
      GRAPH_DATA_CACHE_DIR: /data/cache
      GRAPH_NODE_ID: node-0
      GRAPH_BOLT_ADDR: 0.0.0.0:7687
      GRAPH_ADVERTISED_BOLT_ADDR: ${HYDRA_ADVERTISED:-127.0.0.1:17687}
      GRAPH_BOLT_NODE_ADDRESSES: node-0=${HYDRA_ADVERTISED:-127.0.0.1:17687}
      GRAPH_HTTP_ADDR: 0.0.0.0:8443
      GRAPH_ADMIN_ADDR: 0.0.0.0:9090
      RUST_MIN_STACK: "33554432"
      RUST_LOG: info
    ports:
      - "127.0.0.1:17687:7687"
      - "127.0.0.1:18443:8443"
      - "127.0.0.1:19091:9090"
    volumes:
      - hydra_data:/data

volumes:
  hydra_data:
```

### 2.4 SelfGraph 0.2.1 (signatures copied from its source)

Install: `selfgraph==0.2.1` from PyPI. Docs: https://github.com/hydra-db/selfgraph/tree/main/docs and https://github.com/hydra-db/selfgraph/blob/main/SKILL.md

```python
from selfgraph import SelfGraph, HydraDBStore, entity_id, relation_id

HydraDBStore(uri, *, auth=None, database=None)            # database defaults to "default"
SelfGraph(store, *, namespace="default", schema=None, resolver=None, level="balanced", max_tier=..., ...)

await graph.insert.facts(facts, *, source_id=None, event_time=None, resolver=None, ...) -> InsertResult
#   facts = {"entities": [{"id"?, "type", "name", "aliases"?, "properties"?}], "relations": [{"from_entity", "type", "to_entity", "properties"?}]}
#   InsertResult: .entities .relations .merges .warnings

await graph.entities.create(name, type, *, id=None, aliases=None, properties=None) -> Entity
await graph.entities.get(id) -> Entity | None
await graph.entities.update(id, **fields)                 # name, aliases, remove_aliases, properties, remove_properties
graph.entities.iterate(*, type=None)                      # async iterator
await graph.entities.merges(id); await graph.entities.unmerge(merge_id)

await graph.relations.create(from_entity, type, to_entity, *, id=None, properties=None) -> Relation
await graph.relations.get(id) -> Relation | None
await graph.relations.list(*, from_entity=None, type=None, to_entity=None, cursor=None, limit=...) -> Page   # .items .next_cursor
graph.relations.iterate(*, from_entity=None, type=None, to_entity=None)
await graph.relations.update(id, *, set_properties=None, remove_properties=()) -> Relation   # writes a new version
await graph.relations.versions(id)
await graph.relations.certify(id, by="analyst"); await graph.relations.uncertify(id)

await graph.decisions.create(title, *, steps=(), id=None, summary=None, rationale=None) -> DecisionTrace

await graph.retrieve(query, *, strategy=None, depth=3, k=20, max_nodes=200, budget_tokens=3000, as_of=None, known_at=None) -> RetrievalResult
#   RetrievalResult: .seeds (list of {id, score}, best first) .subgraph .context
await graph.check_answerable(question, *, terms=None, depth=3) -> AnswerabilityReport   # .verdict .terms .missing
await graph.readiness() -> Readiness                      # .ready .counts
await graph.run_cypher(query, params=None) -> CypherResult   # .rows; NOT scoped to the namespace
```

Model fields you will use: `Entity(id, type, name, aliases, properties, source_count)`, `Relation(id, revision, from_entity, type, to_entity, properties, is_current, source_count, certified_at, certified_by)`.

Open a graph like this, one store object per graph:

```python
store = HydraDBStore(os.environ["HYDRA_BOLT_URI"], auth=("neo4j", os.environ["HYDRA_TOKEN"]))
graph = SelfGraph(store=store, namespace=ns, max_tier="balanced")   # balanced = SelfGraph makes no LLM calls
await graph.initialize()
...
await graph.close()
```

### 2.5 LLM (verified from MiniMax docs)

- Anthropic-compatible. Base URL `https://api.minimax.io/anthropic`. Model `MiniMax-M3.1-Flash` (the only other model on this route is `MiniMax-M3`).
- It is a thinking model. **Thinking tokens count toward `max_tokens`.** Too small a value gives `stop_reason == "max_tokens"` and no text.
- The response has `thinking` blocks and `text` blocks. Read only `text` blocks.
- Thinking depth is set with `output_config={"effort": ...}`. The docs only show `"max"`. Other values are unverified.

### 2.6 Data (verified)

| What | Where | Notes |
|---|---|---|
| BIRD dev set | `https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip` | 346,207,293 bytes. Has `dev.json` (1,534 questions) and the 11 SQLite databases with `database_description/*.csv`. The inner layout is unverified and may contain a nested zip. Find files by searching, not by fixed paths. |
| Mini-Dev test set | `https://huggingface.co/datasets/birdsql/bird_mini_dev/resolve/main/data/mini_dev_sqlite.jsonl` | 500 rows. Keys: `question_id`, `db_id`, `question`, `evidence`, `SQL`, `difficulty`. 135 rows have empty evidence. |
| Published prompts | `.../resolve/main/baseline_inference/mini_dev_sqlite.jsonl` | Same rows plus `prompt`, the exact published prompt including evidence |
| Prompt template | `.../resolve/main/baseline_inference/prompt_template.txt` | Placeholders `{engine}`, `{schema}`, `{question_block}` |
| Schema text | `.../resolve/main/baseline_inference/schemas/` | One JSON per dialect mapping database to schema text. List the folder to get the SQLite file name. |

Test questions per database: california_schools 49, card_games 69, codebase_community 31, debit_card_specializing 14, european_football_2 31, financial 46, formula_1 55, student_club 37, superhero 50, thrombosis_prediction 86, toxicology 32.

## 3. Repo layout

```
ABOUT_PROJECT.md   spec-plan.md   README.md   PROGRESS.md   LICENSE (MIT)
pyproject.toml     .env.example   .gitignore  docker-compose.yml
deploy/Dockerfile.app   deploy/Caddyfile   deploy/deploy.sh
scripts/smoke_hydradb.sh   scripts/smoke_selfgraph.py   scripts/smoke_llm.py   scripts/spike_paths.py
lore/
  config.py         settings from .env, paths, defaults
  llm.py            MiniMax client, retries, on-disk cache, token accounting
  sqlexec.py        read-only SQLite execution with timeout, strict EX
  bird.py           load test set and stream, leak guard, prompt rendering
  sqlparse.py       tables, columns, joins and filter columns of a SQL string
  ids.py            slugs and entity ids
  graphdb.py        open and close graphs, GraphReader
  schema_ingest.py  database schema -> Table, Column, HAS_COLUMN, declared JOINS
  ground.py         seeds, graph walk, ranking, context block
  learn.py          reinforce, profile, reflect, compress
  topology.py       P1: native join-path search in HydraDB
  systems.py        floor, ceiling, vector, lore, flat, dump_all behind one interface
  seeds.py          export and import a namespace's learned facts as JSON
  api.py            FastAPI app
  bench/check_data.py   bench/run.py   bench/report.py   bench/load.py
web/                Vite + React + TypeScript frontend
tests/
seeds/              committed: learned facts per demo database
results/            committed: summary JSON, charts
data/               ignored: bird/, runs/, cache/
```

`pyproject.toml`: package `lore`, Python 3.11 or newer. Dependencies: `selfgraph==0.2.1`, `anthropic`, `sqlglot`, `numpy`, `fastapi`, `uvicorn[standard]`, `python-dotenv`, `httpx`. Extra `bench`: `fastembed`, `matplotlib`. Extra `dev`: `pytest`, `ruff`. Create the environment with `uv venv --python 3.12 .venv` and `uv pip install --python .venv/bin/python -e ".[bench,dev]"`.

## 4. Graph model

One SelfGraph namespace per database and purpose:

- Benchmark: `<run>.<system>.<db>`, for example `r1.lore.financial`.
- App: `app.trained.<db>` and `app.sbx.<session>.<db>`.

### 4.1 Ids (`lore/ids.py`)

```python
def slug(s):   # lowercase; every run of characters outside [a-z0-9] becomes "-"; strip "-"; "" -> "x"
def short(s):  # first 6 hex characters of sha1(s)

table_id(table)           = f"table:{slug(table)}-{short(table)}"
column_id(table, column)  = f"column:{slug(table)}.{slug(column)}-{short(table + '.' + column)}"
example_id(key)           = f"example:{slug(key)}"        # key is "q<question_id>" in the benchmark, "u<uuid8>" in the app
term_id(name)             = selfgraph.entity_id("Term", name)   # name is the phrase, lowercased and stripped
```

### 4.2 Entities

| Type | id | name | aliases | properties |
|---|---|---|---|---|
| Table | `table_id` | table name | | `{"table": name}` |
| Column | `column_id` | `"<table>.<column>"` | column name alone, and the description's display name if different | `{"table", "column", "sqltype", "description", "value_description", "profile"}` |
| Term | derived | the phrase | synonyms | `{}` |
| Example | `example_id` | the question text (max 300 characters) | | `{"sql": ..., "key": ...}` |

Keep `description` and `value_description` under 500 characters each and `profile` (a JSON string) under 2,000. HydraDB limits each stored node or edge to 32,000 bytes in total.

### 4.3 Relations

| Type | From, to | Properties |
|---|---|---|
| HAS_COLUMN | Table to Column | none |
| JOINS | Column to Column, lower id first | `{"declared": bool, "wins": int, "losses": int}` |
| MEANS | Term to Column (or Table when no column fits) | `{"sql": str up to 400, "note": str up to 300, "wins": int, "losses": int, "origin": str}` |
| TOUCHES | Example to Column | none |
| JOIN_PATH (P1) | Table to Table | `{"from_sql": str, "hops": int, "wins": int}` |

Relation ids are derived by SelfGraph: `relation_id(from_entity, type, to_entity)`.

### 4.4 Reliability of a rule or join

```python
reliability = (wins + 1) / (wins + losses + 2)
hidden      = (wins + losses) >= 3 and reliability < 0.34 and not certified
```

Hidden rules stay in the graph (history is kept) but are not put in a prompt.

## 5. Prompts

### 5.1 SQL generation

Use BIRD's published template unchanged. `render_prompt(db_id, question, evidence)` fills `{engine}` with `SQLite`, `{schema}` with the published schema text for that database, and `{question_block}`.

How the evidence is laid out inside `{question_block}` is not documented. Work it out from the published prompts, then prove it: for all 500 rows, `render_prompt(db_id, question, evidence)` must equal the row's published `prompt` byte for byte.

- `ceiling` prompt: the published `prompt`.
- `floor` prompt: `render_prompt(db_id, question, None)`. For the 135 rows with empty evidence this must equal the published prompt.
- Every other system: the floor prompt with a knowledge block inserted just before the line `Question:`.

Knowledge block format (omit a section when it is empty; omit the whole block when all are empty, so the prompt equals the floor prompt):

```
Learned knowledge about this database, from earlier verified queries. Use it when it applies to the question.
Rules:
- "school-level" means: satscores.rtype = 'S' (confirmed 4 times)
Column values:
- satscores.rtype: 'S', 'D'
Known joins:
- frpm.CDSCode = satscores.cds
Verified examples:
Q: <question>
SQL: <sql>

```

Limits: 8 rules, 5 value lines, 6 join lines, 3 examples, and about 3,600 characters in total. Drop the lowest-ranked items first.

Extract the SQL from the reply: the last fenced `sql` block; if none, the last fenced block; if none, the text from the first `SELECT` or `WITH`. Strip a trailing semicolon.

### 5.2 Reflection (only after a wrong stream answer)

```
You maintain a knowledge base about one SQLite database so that future questions are answered correctly.

A question was answered with wrong SQL. An analyst supplied the correct SQL.

Question: {question}
Wrong SQL: {predicted_sql}
What happened: {error text, or "It ran but returned a different result."}
Correct SQL: {correct_sql}
{optional line: Analyst hint: {hint}}

Columns used by the correct SQL:
{one line per column: table.column | type | description | sample values}

Write up to 3 reusable rules that explain what the wrong SQL misunderstood.
A rule must help with OTHER questions on this database. Good rules say what a business phrase means as a SQL condition or formula, how a value is stored (codes, formats, units), which column a phrase refers to, or a filter that is always needed.
Do not restate the whole query. Do not include constants that only matter for this one question unless they define the phrase.

Return only JSON:
{"rules": [{"term": "<2 to 5 word phrase a user would say>", "aliases": ["<other phrasings>"], "sql": "<SQL fragment using table.column names>", "columns": ["<table.column>"], "note": "<one sentence>"}]}
If nothing reusable was learned, return {"rules": []}.
```

Parse: take the text from the first `{` to the last `}` and `json.loads` it. Validate each rule: `term` is 2 to 60 characters; every entry of `columns` matches a real `table.column` of this database, ignoring case (map it to the real spelling); drop the rule when no column is valid; cut `sql` to 400 and `note` to 300 characters. On any parse error, learn nothing and continue.

## 6. Milestones

### M0. Environment (P0, 1 hour)

1. `git init`. Write `.gitignore` (`data/`, `.env`, `.venv/`, `node_modules/`, `web/dist/`, `__pycache__/`, `*.sqlite`), `.env.example`, `pyproject.toml`, `LICENSE`.
2. Create the Python environment (section 3).
3. Write `docker-compose.yml` (section 2.3). `docker compose up -d hydradb`. Poll `$HYDRA_ADMIN_URL/readyz` until it returns 200, for up to 120 seconds.
4. `scripts/smoke_hydradb.sh`: through the HTTP API write `MERGE (a {id: 999999})-[:SMOKE]->(b {id: 999998})`, read it back with `MATCH (a {id: 999999})-[:SMOKE]->(b) RETURN b.id AS id`, then `DETACH DELETE` both nodes. Request body: `{"cell_id":"cell-0","query":"..."}`, header `Authorization: Bearer $HYDRA_TOKEN`. If it returns an error about the namespace, add the header `X-Graph-Namespace: local`.
5. `scripts/smoke_selfgraph.py`, in a fresh namespace `smoke-<random>`:
   - `insert.facts` with one Table, one Column, one Term and the relations HAS_COLUMN and MEANS (with `sql`, `wins`, `losses` properties).
   - `relations.list(from_entity=<term id>, type="MEANS")` returns the edge with its properties.
   - `relations.update(id, set_properties={"wins": 1})`, then `relations.versions(id)` shows 2 versions.
   - `retrieve("<a question using the term>", depth=0, k=10)` and print `.seeds`. If `depth=0` is rejected, use `depth=1` and note it.
   - Print which entity fields the seeding matches: test a word that is only in an alias, and a word that is only in `properties["description"]`.
   - Insert a second Term with a near-identical name using `resolver="fuzzy"` and print `result.entities` and `result.merges`, to learn how a merge is reported.
6. `scripts/smoke_llm.py`: one call that asks for `SELECT 1` in a fenced block. Then 16 calls at once with a real floor-size prompt. Print median latency, tokens in and out, and any rate-limit errors. Try `LORE_LLM_EFFORT` values `low` and `medium`; if the API rejects them, leave it empty. Choose the concurrency that gives no rate-limit errors.

**Done when:** all three smoke scripts succeed and their key outputs are in `PROGRESS.md`.

**If HydraDB will not start:** check the logs, compare the env block with HydraDB's AGENTS.md step 7, and confirm the image has the binary with `docker run --rm --entrypoint /bin/sh ghcr.io/hydra-db/hydradb:0.4.0 -c "ls -l /usr/local/bin"`. After 45 minutes, stop and ask the owner. The last resort is building from source, which needs sudo for `clang cmake libcypher-parser-dev libgraphblas-dev`.

### M1. Data and evaluator (P0, 1.5 hours)

1. Download `dev.zip` to `data/bird/` and unzip it. If it contains another zip of databases, unzip that too. Locate `dev.json` and every `*.sqlite` with a recursive search. Record the paths in `data/bird/paths.json`.
2. Download the four Mini-Dev files (section 2.6) to `data/bird/minidev/`.
3. `lore/sqlexec.py`:

```python
def run_sql(db_path, sql, timeout_s=30.0, max_rows=None):
    """Return (rows, error, ms). rows is a list of tuples, or None when there was an error."""
    start = time.monotonic()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    timer = threading.Timer(timeout_s, conn.interrupt)
    timer.start()
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        return rows, None, int((time.monotonic() - start) * 1000)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}", int((time.monotonic() - start) * 1000)
    finally:
        timer.cancel()
        conn.close()

def ex_match(pred_rows, gold_rows):
    return pred_rows is not None and gold_rows is not None and set(pred_rows) == set(gold_rows)
```

   Call it with `asyncio.to_thread`, at most 4 at a time. Cache gold results per question in memory and on disk.
4. `lore/bird.py`:
   - `Question` dataclass: `key` (`"t<id>"` for test, `"s<id>"` for stream), `db_id`, `question`, `evidence`, `gold_sql`, `difficulty`, `db_path`.
   - `load_test()` returns the 500 Mini-Dev questions.
   - `load_stream(seed, cap_per_db=80)` returns stream questions per database from `dev.json` after the leak guard, shuffled with the seed, cut to the cap.
   - **Leak guard.** Remove a dev question when, against any test question of the same database: (a) the normalized question text is equal, or (b) the normalized gold SQL is equal, or (c) the token Jaccard similarity of the questions is 0.6 or more, or (d) the token Jaccard similarity of the gold SQL is 0.8 or more. Normalize by lowercasing and collapsing whitespace. Write the counts removed by each rule to `results/<run>/split.json`.
   - `render_prompt` (section 5.1).
5. `lore/bench/check_data.py` prints: test count, stream count per database, counts removed by the guard, how many of 500 rendered prompts equal the published ones, how many of 500 gold queries ran and returned at least one row, and each database's `.sqlite` size.
6. Tests: `tests/test_sqlexec.py` (timeout, read-only, set comparison), `tests/test_bird.py` (prompt equality on 20 rows, no test question in the stream).

**Done when:** `check_data` reports 500 of 500 prompts equal and at least 495 of 500 gold queries running with rows, and the tests pass.

**If more than 5 gold queries fail:** the databases in `dev.zip` differ from the ones Mini-Dev expects. Download `https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip` (800 MB) and use its SQLite databases instead.

### M2. Floor and ceiling (P0, 1 hour)

1. `lore/llm.py`:

```python
client = anthropic.AsyncAnthropic(base_url=BASE_URL, api_key=API_KEY, max_retries=4, timeout=180)

async def complete(prompt) -> LLMResult:        # LLMResult: text, input_tokens, output_tokens, ms, cached
    kwargs = dict(model=MODEL, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": prompt}])
    if EFFORT:
        kwargs["extra_body"] = {"output_config": {"effort": EFFORT}}
    msg = await client.messages.create(**kwargs)
    text = "".join(b.text for b in msg.content if b.type == "text")
```

   - One global `asyncio.Semaphore(LORE_LLM_CONCURRENCY)`.
   - If the text is empty and `stop_reason == "max_tokens"`, retry once with double `max_tokens`.
   - **Disk cache** in `data/cache/llm.sqlite`, keyed by sha256 of model, effort and prompt. A cache hit returns the stored text. This makes identical prompts give identical answers across systems, and makes reruns free.
   - Keep running totals of input and output tokens in `data/runs/<run>/usage.json`.
2. `lore/systems.py`: the interface every system follows.

```python
class System:
    name: str
    async def build_prompt(self, q: Question) -> tuple[str, dict]: ...   # prompt, trace (what was used)
    async def observe(self, q: Question, outcome: Outcome) -> None: ...  # learning hook, stream only; default does nothing
# Outcome: sql, rows_ok, error, correct, trace
```

   Implement `Floor` and `Ceiling`.
3. `lore/bench/run.py`, first version: run the given systems on the test set. Write one JSON line per answer to `data/runs/<run>/answers.jsonl` with: `system, phase, checkpoint, db_id, key, sql, error, correct, prompt_tokens, completion_tokens, ms, block_chars, trace`. On start, skip any `(system, phase, checkpoint, key)` already in the file, so a rerun resumes.
4. Run: `python -m lore.bench.run --run r1 --systems floor,ceiling`.
5. Look at 10 wrong ceiling answers by hand. Make sure they are real model mistakes, not SQL-extraction or timeout bugs.

**Done when:** `answers.jsonl` has 500 floor and 500 ceiling rows and the two accuracies are in `PROGRESS.md`.

**Gate:** published scores for flash-class models with hints are 51 to 70%. If the ceiling is under 40%, look for a bug first. If `ceiling - floor` is under 5 points, **stop and ask the owner.** Hints then add little for this model, and the pitch has to change before more time is spent.

### M3. Schema graph (P0, 1 hour)

1. `lore/graphdb.py`: `open_graph(ns)` and `close_graph(graph)` (section 2.4), and `GraphReader`:

```python
class GraphReader:
    def __init__(self, graph, frozen=False): ...     # frozen=True memoizes every read; use it during test evaluation
    async def seeds(self, question, k=30) -> dict[str, float]     # entity id -> score scaled to 0..1, from graph.retrieve(question, depth=0, k=k)
    async def out(self, entity_id, rel_type) -> list[Relation]    # relations.list(from_entity=..., type=...), all pages
    async def inc(self, entity_id, rel_type) -> list[Relation]    # relations.list(to_entity=..., type=...), all pages
    async def all(self, rel_type) -> list[Relation]               # relations.iterate(type=...)
    async def entity(self, entity_id) -> Entity | None
```

2. `lore/schema_ingest.py`: `ingest_schema(graph, db_path, description_dir)`:
   - Tables and columns from `PRAGMA table_list` and `PRAGMA table_info("<table>")`. Skip `sqlite_` tables.
   - Descriptions from `database_description/<table>.csv` (columns such as `original_column_name`, `column_name`, `column_description`, `value_description`). These files are not always UTF-8: try `utf-8-sig`, then `cp1252`. Match rows to columns by `original_column_name`, ignoring case and surrounding spaces. A missing file or row is fine.
   - Declared joins from `PRAGMA foreign_key_list("<table>")` as JOINS edges with `{"declared": true, "wins": 0, "losses": 0}`. When the referenced column is empty, use the referenced table's primary key.
   - Write with `insert.facts` in chunks of at most 200 entities and 400 relations. It is idempotent, so a rerun is safe.
   - Return an in-memory schema dict: `{table: {column: sqltype}}` plus a lookup from lowercase `table.column` to the real spelling. Systems keep this dict; it is not learned knowledge.
3. Ingest all 11 databases into `r1.lore.<db>`. Print `readiness().counts` for each.
4. Sanity check: for three questions, print the top 10 seeds and confirm obvious columns appear.

**Done when:** for every database the entity count equals tables plus columns and the HAS_COLUMN count equals the number of columns.

### M4. Learning loop (P0, 3 hours)

1. `lore/sqlparse.py`: `parse_sql(sql, schema) -> Parsed(tables, columns, joins, filter_columns)`.
   - Parse with `sqlglot.parse_one(sql, read="sqlite")`. Try `sqlglot.optimizer.qualify.qualify(tree, schema=..., dialect="sqlite")` inside a try block to resolve which table each column belongs to; if it raises, continue with the unqualified tree.
   - Map aliases to tables from `exp.Table` nodes. For each `exp.Column`, resolve its table through the alias; when it has no table, use the only table in the query that has that column, else skip it. Map names to the real spelling through the schema lookup.
   - `joins`: each `exp.EQ` whose two sides are columns of two different tables.
   - `filter_columns`: columns that appear inside `WHERE`, `HAVING`, or a join condition that also contains a literal.
   - If parsing fails entirely, fall back to scanning the SQL text for real column names of the tables it mentions, longest names first.
   - Test on 30 gold queries: every table found must be a real table.
2. `lore/ground.py`: `ground(reader, schema, question, cfg) -> Grounding(rules, values, joins, examples, block, trace)`.

```
seeds  = await reader.seeds(question, k=30)             # split by id prefix: term:, column:, table:, example:
rules  = {}                                              # relation id -> (Relation, score)
cols   = {}                                              # column id -> score

for each term seed t:                                    # the wording matched a learned phrase
    for r in await reader.out(t, "MEANS"):
        rules[r.id] = max score with seeds[t]
        cols[r.to_entity] = max score with seeds[t]     # when the target is a column

for each column seed c:                                  # the wording matched the schema
    cols[c] = max score with seeds[c]
    for r in await reader.inc(c, "MEANS"):               # rules attached to that column, whatever phrase taught them
        rules[r.id] = max score with 0.7 * seeds[c]

for each rule: skip if hidden (section 4.4)
               final = score * reliability * (1.5 if certified else 1.0)
top rules = best 8 by final, one per distinct sql text
reached columns = cols plus the target columns of the top rules, best 25 by score

values = for reached columns whose profile has 25 or fewer distinct values: one "Column values" line, best 5

examples: counts = {}
    for each reached column c:  for r in await reader.inc(c, "TOUCHES"):  counts[r.from_entity] += cols[c]
    for each example seed e:    counts[e] += 2 * seeds[e]
    top 3 by count; load each with reader.entity(id); skip any whose sql is longer than 3,000 characters

tables = tables of the reached columns
joins  = every JOINS edge (from await reader.all("JOINS")) whose two columns belong to two of those tables, not hidden, best 6 by reliability

block  = the text from section 5.1
trace  = {"rules": [relation ids], "joins": [relation ids], "examples": [entity ids], "seeds": {...}}
```

   Run the `out` and `inc` calls with `asyncio.gather`.
3. `lore/learn.py`: `learn(graph, schema, q, outcome, verified_sql, hint=None)`. `verified_sql` is the model's SQL when it was right, otherwise the corrected SQL.

```
parsed = parse_sql(verified_sql, schema)

A. Example.   insert.facts: Example entity (id example_id(q.key), name = question, properties sql and key)
              plus one TOUCHES relation to every column in parsed.columns. source_id = q.key.

B. Joins.     for each join in parsed.joins: rid = relation_id(low column id, "JOINS", high column id)
              existing = await graph.relations.get(rid)
              none      -> relations.create(..., properties={"declared": False, "wins": 1, "losses": 0})
              otherwise -> relations.update(rid, set_properties={"wins": existing wins + 1})

C. Reweight.  for each rule id in outcome.trace["rules"]:
              skip when the relation is certified (updating would drop the certification)
              right answer -> wins + 1
              wrong answer -> losses + 1, but only when the rule's target column is NOT in parsed.columns

D. Only when the answer was wrong:
   D1. Profile. For up to 5 columns of parsed.filter_columns that have no profile yet:
         SELECT COUNT(DISTINCT "c"), SUM("c" IS NULL) FROM "t"
         SELECT "c", COUNT(*) FROM "t" GROUP BY 1 ORDER BY 2 DESC LIMIT 25
       10 second timeout each. Store {"distinct": n, "nulls": n, "top": [values cut to 40 characters]} as a JSON
       string in the Column entity's "profile" property with entities.update(id, properties={"profile": ...}).
   D2. Reflect. One LLM call with the prompt from section 5.2, including the profiles just taken.
   D3. Write each valid rule:
         term entity: insert.facts({"entities": [{"type": "Term", "name": term, "aliases": aliases}]}, source_id=q.key, resolver="default")
         use the id of the entity that comes back (it may be an existing Term)
         for each column of the rule: rid = relation_id(term id, "MEANS", column id); existing = await graph.relations.get(rid)
           none                                   -> relations.create with {"sql", "note", "wins": 0, "losses": 0, "origin": q.key}
           existing with the same sql             -> leave it
           existing, different sql, reliability < 0.5 -> relations.update with the new sql and note, wins 0, losses 0
           existing, different sql, reliability >= 0.5 -> leave it
```

   `learn` must never be called with a test question. Assert `q.key.startswith("s")` in the benchmark path.
4. `Lore` system in `lore/systems.py`: `build_prompt` calls `ground` and inserts the block; `observe` calls `learn`. It holds one graph per database and a `frozen` flag that switches the reader's memoization on during test evaluation.
5. Extend `lore/bench/run.py` with the stream protocol (section 7.2).
6. Small run: `python -m lore.bench.run --run s1 --systems floor,lore --dbs financial,california_schools --stream-cap 30 --checkpoints 1.0`.
7. Print every learned rule of the small run and read them. Fix the reflection prompt if they are question-specific or wrong.
8. Tests: `tests/test_leaks.py` asserts (a) no prompt of a non-ceiling system contains a non-empty evidence string of its question, checked over a sample of 50, and (b) in every `*.lore.*` namespace, no Example `key` property and no MEANS `origin` property starts with `t` (test questions have keys starting with `t`, stream questions with `s`).

**Done when:** the small run finishes, at least 10 rules were learned, the two leak tests pass, and the accuracy of floor and Lore on those two databases is in `PROGRESS.md`, whichever direction it went.

### M5. Full benchmark (P0, 30 minutes to launch, then in the background)

1. Add the remaining systems to `lore/systems.py`:
   - `Vector`: memory is a list of (question, verified SQL, embedding) per database. `observe` appends the stream question with its gold SQL. `build_prompt` adds a block with only "Verified examples": the 3 nearest by cosine similarity. Embed with `fastembed.TextEmbedding("BAAI/bge-small-en-v1.5")`.
   - `Flat`: built from a finished Lore namespace. Items are every non-hidden rule as the text `"<term> means <sql>. <note>"`, every column profile as a "Column values" line, and every Example. Retrieve the 8 nearest rules, 3 nearest value lines and 3 nearest examples by cosine similarity. Same block format. No joins section.
   - `DumpAll` (P1): every non-hidden rule, every value line, and the 3 most recent examples, with no retrieval and no size limit.
2. Launch in the background, in this order, so the most important numbers land first:

```
python -m lore.bench.run --run r1 --systems lore   --stream-cap 80 --checkpoints 0.25,0.5,1.0
python -m lore.bench.run --run r1 --systems vector --stream-cap 80 --checkpoints 0.25,0.5,1.0
python -m lore.bench.run --run r1 --systems flat   --from-run r1
python -m lore.bench.run --run r1 --systems dump_all --from-run r1          # P1
```

3. `lore/bench/report.py --run r1` writes `results/r1/summary.json`, `results/r1/curve.png`, `results/r1/per_db.md` (section 7.4). It must work on a partly finished run and say which parts are missing.
4. Export what Lore learned: `python -m lore.seeds export --run r1 --out seeds/` (M7 step 2 defines the format).

**Done when:** `results/r1/summary.json` has floor, ceiling, Lore and vector at every checkpoint and the flat ablation at the end, and `curve.png` exists.

### M6. Load test (P0, 30 minutes), then HydraDB-native path search and the other P1 items

**6.1 Load test (P0).** `lore/bench/load.py --run r1 --concurrency 10,50,100 --requests 1000`: fire `ground()` calls (no LLM) for random test questions against the `r1.lore.*` namespaces, with unfrozen readers so every call reads HydraDB. Report p50, p95, p99 in milliseconds, requests per second and error count per concurrency level, plus the total number of entities and relations in those namespaces. Save `results/r1/load.json`.

**6.2 Native join-path search (P1, 60-minute time box).** Goal: when a question needs tables that no known join connects directly, HydraDB finds the path.

Keep a small derived layer in HydraDB next to SelfGraph's records, written with raw Cypher:

- One node per table: label `LoreTable`, string property `key = "<namespace>|<table>"`, integer id `int.from_bytes(hashlib.blake2b(f"lore-topo\0{ns}\0{table}".encode(), digest_size=8).digest(), "big") >> 1`.
- One edge per pair of tables that has a JOINS edge. The type carries the learning, so no edge ever needs updating: `LORE_JOIN` for any join, `LORE_PROVEN` when its wins are 2 or more, `LORE_SHORTCUT` for a compressed path (6.3).

`scripts/spike_paths.py` proves these three statements on a toy graph first. Run them with `graph.run_cypher`:

```cypher
UNWIND $rows AS row MERGE (n {id: row.id}) SET n:LoreTable, n.key = row.key
```

```cypher
MERGE (a {id: $src})-[:LORE_JOIN]->(b {id: $dst})
```

```cypher
CALL algo.MSpaths({
  sourceLabel: 'LoreTable', sourceProperty: 'key',
  sourceValues: ['ns|a', 'ns|c'], targetValues: ['ns|a', 'ns|c'],
  relTypes: ['LORE_SHORTCUT', 'LORE_PROVEN', 'LORE_JOIN'], relDirection: 'both',
  maxLen: 3, pathCount: 1, pairwise: true, resultLimit: 50
})
YIELD path
RETURN path
```

Rules that matter here: write the node batch before the edges. The value lists must be written into the query text, because list parameters are rejected (the keys are slugs, so this is safe; still escape single quotes). `maxLen` counts edges. Print the returned rows to learn their shape, then map each path back to table names.

If this works: `lore/topology.py` gets `sync(graph, schema)` (rewrite nodes and edges from the current JOINS relations; call it after schema ingest and after each stream question's learning) and `connect(ns, tables) -> list of table paths`. In `ground`, when the selected tables are not all connected by the joins already found, call `connect` and add the JOINS edges along the returned paths.

If the time box runs out: do the same search with a breadth-first search in Python over `reader.all("JOINS")`, and write in the README that path search runs client-side. Do not claim native path search unless it runs.

**6.3 Path compression (P1, 40 minutes).** In `learn`, when the verified SQL joins 3 or more tables in a simple chain: build the canonical text `"A JOIN B ON a.x = b.y JOIN C ON b.z = c.w"`, and create or update a JOIN_PATH relation between the two end tables with `{"from_sql", "hops", "wins"}`. When its wins reach 2, `ground` prints one line `Proven join path: FROM ...` in place of the separate join lines for those tables, and `topology.sync` adds a `LORE_SHORTCUT` edge between the end tables.

**6.4 Synonym merge and certification (P1, 40 minutes).**
- Merge: write Terms with `resolver="fuzzy"` instead of `"default"`. Use what M0 step 5 showed about how the surviving id is reported. Count merges per run from `InsertResult.merges`.
- Certification: `graph.relations.certify(id, by="analyst")`. `ground` already ranks certified rules higher and never hides them; `learn` already skips them.

**6.5 If P1 changed what Lore puts in prompts,** rerun Lore as run `r2` (`--systems lore`, plus `flat`) and report `r2`. If there is no time for that, report `r1` and list the P1 items in the README as "built, not in the reported numbers".

**Done when:** `results/r1/load.json` exists. Each P1 item is either working with a test, or marked skipped in `PROGRESS.md`.

### M7. App (P0, 3 hours). Start by 1:00 AM.

**1. Demo databases.** Pick 4 databases: the ones with the largest Lore gain in `per_db.md` among those whose `.sqlite` file is under 100 MB.

**2. Seeds** (`lore/seeds.py`). `export` writes, per database, a JSON file in the shape `insert.facts` accepts: every Term and Example entity, every MEANS, TOUCHES, JOIN_PATH and learned JOINS relation with its properties, and every column profile. `import_seeds(graph, path)` ingests the schema and then the file. No LLM calls. This is how the hosted app gets the trained graph, and how anyone can reproduce the demo.

**3. Backend** (`lore/api.py`, FastAPI):

| Route | Does |
|---|---|
| `GET /healthz` | 200 |
| `GET /api/dbs` | The demo databases, with table and rule counts and 3 suggested question pairs each |
| `POST /api/ask` `{db, mode, session, question}` | Ground, call the LLM, run the SQL. Returns `{ask_id, sql, columns, rows, error, block, graph, prompt_tokens, ms}`. `mode` is `trained` or `sandbox`. Also saves a SelfGraph decision trace: `decisions.create(title=question[:120], id="decision:<ask_id>", steps=<rule and join relation ids>, summary=sql)`. |
| `POST /api/feedback` `{ask_id, verdict, hint?, corrected_sql?}` | `up`: learn as correct. `down` with `corrected_sql`: learn from it. `down` with `hint`: ask the LLM again with the line `Analyst hint: <hint>` added to the question, run it, and return the new answer as a proposal. `confirm` `{ask_id, sql}`: learn with that SQL as verified and the hint passed to reflection. Returns `{learned: [rules], graph}`. |
| `GET /api/graph?db&mode&session` | Nodes and edges of the learned layer: Terms, their MEANS edges, the columns and tables they reach, JOIN_PATH edges. Not every column. |
| `POST /api/certify` `{db, mode, session, relation_id}` | Certify a rule |
| `POST /api/sandbox/reset` `{session, db}` | Start that sandbox over in a new namespace |
| `GET /api/results` | `results/<run>/summary.json` and `load.json` |

   - `graph` in a response: `{"nodes": [{"id", "type", "label", "state"}], "edges": [{"id", "source", "target", "type", "wins", "losses", "certified"}]}`. `state` is `seed`, `reached`, `used` or `new`.
   - Sandbox namespaces are `app.sbx.<session>.<db>`, created on first use by ingesting the schema.
   - On startup, for each demo database: if `app.trained.<db>` is empty, import its seed file.
   - Feedback in `trained` mode does not write. Only sandboxes learn. This keeps one visitor from spoiling the shared graph.
   - **Safety:** accept only a single `SELECT` or `WITH` statement (check with sqlglot), run it read-only with a 10 second timeout and return at most 200 rows. Limit each IP to 30 LLM calls per hour and the whole app to 2,000 per day; after that return a clear message. The API key stays on the server.
   - Serve the built frontend from `web/dist` at `/`.

**4. Suggested question pairs.** From the benchmark answers, find pairs in the same database where: the floor got question B wrong, Lore got B right, and a rule Lore used for B has an `origin` that is a different question A. Show A, then a short hint that teaches the rule, then B. Check each pair by hand in a fresh sandbox before listing it. If no pair works reliably, list single questions and say what to try.

**5. Frontend** (`web/`, Vite + React + TypeScript, plain CSS, `react-force-graph-2d` for the graph, `recharts` for charts). One page, three tabs:
   - **Ask:** database picker, trained or sandbox switch, question box with suggested questions, the SQL, the result table, the graph that was walked with used rules highlighted, the knowledge block that went to the model, and thumbs up, thumbs down with a hint box or a corrected-SQL box. After feedback, list what was learned and mark the new nodes.
   - **Graph:** the learned layer, a table of rules with term, SQL fragment, wins, losses and certified state, and a certify button.
   - **Proof:** the accuracy curve with floor and ceiling lines, the final comparison table (floor, ceiling, vector, flat, Lore, with confidence intervals), tokens per question, the per-database table, the load numbers, and a short plain description of the method.
   - A header line states what it is and that it runs on HydraDB and SelfGraph.

**Done when:** locally, a full round works in a sandbox: ask, thumbs down with a hint, confirm, see the new rule, ask a second question that uses it. `ruff check lore tests`, `pytest -q` and `npm run build` all pass.

### M8. Deploy (P0, 1.5 hours). Start by 4:00 AM.

The owner provides a Linux VM (Ubuntu 24.04, 4 GB RAM) and SSH access.

1. Add to `docker-compose.yml`, both under `profiles: ["prod"]`:
   - `app`: built from `deploy/Dockerfile.app` (a Node stage builds `web/`, then `python:3.12-slim` installs the package without the `bench` extra, copies `seeds/`, `results/` and `web/dist`, and runs `uvicorn lore.api:app --host 0.0.0.0 --port 8000`). Env from `.env`, with `HYDRA_BOLT_URI=bolt://hydradb:7687`. Mounts `./data` read-only at `/app/data`.
   - `caddy`: image `caddy:2`, ports 80 and 443, `deploy/Caddyfile`:

```
{$SITE_HOST} {
    encode gzip
    reverse_proxy app:8000
}
```

   `SITE_HOST` is `lore.<the VM IP with dots replaced by dashes>.sslip.io`. Caddy gets the certificate by itself. Set `HYDRA_ADVERTISED=hydradb:7687` in the VM's `.env`.
2. On the VM: install Docker (`curl -fsSL https://get.docker.com | sh`), copy the repo, copy `.env`, and copy only the 4 demo databases with their description folders and the Mini-Dev schema and template files into `data/` at the same relative paths.
3. `docker compose --profile prod up -d --build`. Wait for `https://<SITE_HOST>/healthz`.
4. From outside the VM, run one full sandbox round through the public URL.
5. Leave it running. Tell the owner the URL.

**If there is no VM by 4:00 AM:** run the app on this machine with `docker compose --profile prod up -d` without caddy, download the `cloudflared` binary from its GitHub releases (no sudo needed), and run `cloudflared tunnel --url http://localhost:8000`. Give the owner the printed URL and tell them this machine must stay on and online until judging ends.

**Done when:** the public URL serves the app and a sandbox round works through it.

### M9. README and submission pack (P0, 1 hour)

1. `README.md`, in this order: one-line description and the live link; the problem; the result table and `curve.png`; how it works (the loop diagram and the graph model); what the graph adds (the flat ablation number); how HydraDB and SelfGraph are used (and honestly, whether path search is native or client-side); the benchmark protocol and its limits; the load test; how to run it locally in 5 commands; how to reproduce the benchmark; what is built but not in the reported numbers; data attribution (BIRD, CC BY-SA 4.0); license.
2. Fill the `[FILL]` blanks in `ABOUT_PROJECT.md` sections 10 and 13 from `summary.json`.
3. Ask the owner for approval, then `gh repo create <name> --public --source . --push`.
4. Final pass: fresh clone, follow the README's local steps, confirm they work.

**Done when:** the repo is public, the README numbers match `summary.json`, and the owner has the live link, the repo link, the Loom outline and the filled posts.

## 7. Benchmark protocol

### 7.1 Split

- Test: all 500 Mini-Dev questions.
- Stream: BIRD dev questions on the same databases, after the leak guard (M1), shuffled with `--seed` (default 0), cut to `--stream-cap` per database (default 80).

### 7.2 Stream and checkpoints

Each database is independent: its own namespace, its own stream. Run the databases in parallel as asyncio tasks. Inside one database:

```
for i, q in enumerate(stream, start=1):
    prompt, trace = await system.build_prompt(q)          # uses what has been learned so far
    answer the question, run the SQL, correct = ex_match(pred_rows, gold_rows)
    write the answer row (phase "stream")
    await system.observe(q, outcome)                       # learning; the system is given the gold SQL as the correction
    if i is a checkpoint (25%, 50%, 100% of this database's stream):
        freeze the system (no writes, memoized reads)
        answer every test question of this database, concurrently; write rows (phase "test", checkpoint = fraction)
        unfreeze
```

- Checkpoint 0 is the floor by construction: with nothing learned the prompt equals the floor prompt.
- The x axis of the curve is the number of stream questions seen, summed over databases.
- `--from-run` builds `Flat` and `DumpAll` from a finished run's Lore namespaces and evaluates them at the final checkpoint only.

### 7.3 Metric

Strict execution accuracy, as BIRD defines it: run the predicted SQL and the gold SQL on the same database; the answer is correct when `set(predicted_rows) == set(gold_rows)`. An error or a timeout (30 seconds) is wrong.

### 7.4 Report (`results/<run>/summary.json`)

- Model name, effort, date, seed, stream cap, split counts and leak-guard counts.
- Per system and checkpoint: accuracy in percent, number of questions, mean prompt tokens, mean knowledge-block size.
- At the final checkpoint: `lore - floor`, `lore - vector`, `lore - flat`, each with a 95% interval from a paired bootstrap:

```python
def paired_bootstrap(a, b, n=10000, seed=0):      # a, b: 0/1 lists for the same questions in the same order
    a, b = np.array(a), np.array(b)
    idx = np.random.default_rng(seed).integers(0, len(a), size=(n, len(a)))
    diffs = (a[idx].mean(axis=1) - b[idx].mean(axis=1)) * 100
    return float((a.mean() - b.mean()) * 100), [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
```

- `gap_closed = (lore - floor) / (ceiling - floor)`, only when `ceiling - floor` is 5 points or more.
- Per database: floor, ceiling, vector, Lore, number of rules learned.
- Stream accuracy of Lore in the first and last third of the stream.
- Counts: rules learned, rules hidden, joins learned, columns profiled, examples stored, merges.
- Token totals and the number of LLM calls.
- `curve.png`: held-out accuracy against questions seen, with lines for Lore and vector, horizontal lines for floor and ceiling, and a marker for the flat ablation.

## 8. Known traps

**HydraDB**

- Auto-commit only. No transactions.
- A node's `id` is an upsert key. A plain `CREATE` of an edge run twice makes two edges. Use `MERGE`, or the `UNWIND` batch form.
- Every relationship pattern must be directed and name exactly one type. `-[r]->`, `-[:A|B]->` and undirected patterns are rejected.
- `RETURN` accepts only `x.property`, aliases and aggregates. No `RETURN *`, no `RETURN n`, no arithmetic.
- Every `MATCH` needs an id, a label or a property to anchor it.
- Variable-length patterns need an upper bound.
- `UNWIND` needs a parameter as input. The node batch needs exactly one `SET n:Label` first; properties may follow it.
- A single-statement `MERGE` cannot be followed by `SET`.
- List parameters are rejected in procedure calls. Write lists into the query text.
- Fewer rows than expected can mean a query budget was hit, not that data is missing.
- `RUST_MIN_STACK` must be set or the node aborts. The auth token must be 32 characters or more.

**SelfGraph**

- Every method is async. One store object per graph. Closing the graph closes the store.
- On HydraDB, writes to one graph object run one at a time. Do not write to the same namespace from two processes.
- An explicit entity id must be `type:name`, and the prefix must match the type.
- Reserved entity types: Entity, Profile, DecisionTrace, DecisionStep, Source, SourceVersion, Chunk, Evidence, EntityMerge, EntityMergeEntry. Reserved relation types: PREFERS, AVOIDS, HAS_PROFILE, MADE_DECISION, HAS_STEP, FROM, TO, RESULTED_IN, CONSIDERED, HAS_VERSION, HAS_CHUNK.
- `relations.create` on an existing id raises `ConflictError`. Use get, then create or update.
- `relations.update` writes a new version. A new version is not certified, so never update a certified relation.
- Property values are JSON. No datetime objects, no integers beyond 2^53. A `None` value removes the key.
- Unknown keys in `insert.facts` raise `ValidationError`.
- `retrieve` scores every entity in the namespace. That is fine for hundreds of entities.
- `run_cypher` is not scoped to a namespace. On HydraDB SelfGraph nodes have the label `Entity` and the properties `sid` (the SelfGraph id), `ns`, `type`, `name`; edges are `RELATES` with `etype` and `is_current`.
- A custom decision id must be `decision:<name>`.

**MiniMax**

- Thinking tokens count toward `max_tokens`. Empty text with `stop_reason == "max_tokens"` means raise it.
- Read only `text` blocks.

**BIRD**

- Column names contain spaces, parentheses and percent signs. Always quote them.
- Description CSV files are not always UTF-8.
- Some gold queries are slow. Use the 30 second timeout and cache gold results.
- Strict EX compares sets of row tuples: column order matters, duplicate rows collapse.
- Some stream labels are wrong. Do not try to fix them.

## 9. Fallbacks and cut order

| Problem | Do this |
|---|---|
| SelfGraph has a blocking bug on HydraDB | Write a thin `lore/graphdb.py` replacement that keeps the same `GraphReader` and write functions but talks to HydraDB directly over Bolt with the `neo4j` driver (nodes with one label per kind, typed edges, properties inline). Say so in the README. Report the bug to the owner so it can be filed upstream. |
| The LLM is slow or rate-limited | Lower concurrency. Cut `--stream-cap` to 50. Use checkpoints 0.5 and 1.0 only. |
| The curve is flat at M4 | Read 20 wrong Lore answers. Usual causes: rules too specific, rules not retrieved (print the seeds), block ignored by the model. Fix the cause. Do not touch the metric or the split. |
| Vector memory beats Lore | Report it. Lead with the flat ablation, the token cost and what the graph adds beyond accuracy. |
| No VM | Cloudflare tunnel from this machine (M8). |

If time runs short, cut in this order: term split, time-travel view, MCP endpoint, `DumpAll`, synonym merge, path compression, native path search (keep the client-side search), extra seeds. Never cut: floor, ceiling, vector and Lore on the full test set, the flat ablation, the load test, the live app, the README.

## 10. Final checklist

- [ ] `results/<run>/summary.json`, `curve.png`, `per_db.md`, `load.json` exist and are committed
- [ ] Leak tests pass
- [ ] `ruff check lore tests`, `pytest -q`, `npm run build` pass
- [ ] README numbers equal `summary.json`
- [ ] README says which mechanisms are in the reported numbers and whether path search is native
- [ ] No key, no `.env`, no database file in the repo
- [ ] Live URL works from another network; one sandbox round completes
- [ ] Repo is public (owner approved)
- [ ] `ABOUT_PROJECT.md` blanks filled; owner has the Loom outline and the posts
- [ ] `PROGRESS.md` is up to date
