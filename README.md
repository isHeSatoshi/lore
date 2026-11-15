# Lore

A text-to-SQL semantic layer that learns reusable database knowledge from verified corrections, built on HydraDB and SelfGraph.

**Live demo:** local preview only so far. Free Hugging Face hosting is approved;
the native Gradio adapter passes local compatibility checks, but account access
and free-tier eligibility are still unverified. No public app exists yet.
See [hosting status and release steps](deploy/hf/README.md).

## The problem

Database schemas say what columns exist. They rarely explain what “revenue”
means, which status codes count, or which join an analyst trusts. Prompting
the same model again does not retain that correction.

Lore stores those meanings as inspectable graph facts and retrieves a small
knowledge block for the next question. It does not fine-tune the model.

## Results, still in progress

No learned-system improvement claim is established yet. Both baselines have
completed; learning checkpoints and ablations must finish before conclusions.
The run is paused on MiniMax's 2056 usage quota. Progress is saved: the first
two Lore checkpoints cover 500/500 questions; the final checkpoint is 258/500.
Vector and flat have not started. No automatic model retry is running.

| System | Strict execution accuracy | 95% Wilson interval | Evaluated |
|---|---:|---:|---:|
| Floor, schema and question only | 45.4% | 41.1–49.8% | 500/500 |
| Ceiling, supplied per-question evidence | 51.6% | 47.2–56.0% | 500/500 |
| Lore, learned graph | Pending | Pending | Not complete |
| Vector, verified-example retrieval | Pending | Pending | Not complete |
| Flat, retrieval from the same learned facts | Pending | Pending | Not complete |

Source: [`results/r2/summary.json`](results/r2/summary.json).
The baseline gap is 6.2 percentage points and passes the predeclared gate.
That gap measures the effect of supplied evidence, not a Lore improvement.
The [per-database report](results/r2/per_db.md) and
[manual ceiling review](results/r2/ceiling_review.md) preserve the current evidence.
Incomplete points are explicitly marked and are not plotted as completed scores.

An exploratory two-database validation (`s1`) scored 34/95 for floor and 45/95
for Lore. Its paired difference interval includes zero, and its rule-quality
audit failed. It is preserved in [`results/s1/`](results/s1/) with the
[audit findings](results/s1/rule_review.md), not presented as a final gain.
A second exploratory run (`s2`) scored 34/95 for floor and 50/95 for Lore, but
[its audit](results/s2/rule_review.md) still found overbroad meanings and aliases.
Those runs are not used to select the best reported accuracy. Final small-run
validation (`s3`) scored 34/95 for floor and 49/95 for Lore. All 87 MEANS
relations were inspected and both leak checks passed. The
[review](results/s3/rule_review.md) records final validator repairs and remaining
noisy meanings/aliases. These exploratory results are not a full-test gain.
The recorded `s3` score predates its final post-review validator guards and was
not rescored afterward.

![Current, incomplete benchmark snapshot](results/r2/curve.png)

## How it works

```text
Question → lexical graph grounding → bounded knowledge block → model → read-only SQL
                     ↑                                                   ↓
              reusable graph facts ← verified SQL and analyst correction
```

The graph model is small:

- `Table → HAS_COLUMN → Column` stores the real SQLite schema.
- `Term → MEANS → Column` stores a reusable SQL meaning, provenance and feedback.
- `Column → JOINS → Column` stores declared and observed joins.
- `Example → TOUCHES → Column` connects verified SQL to its structure.
- Column profiles record distinct counts, null counts and bounded example values.

Correct feedback strengthens relevant rules. Incorrect feedback can weaken
rules that pointed at the wrong columns. Certified rules are not silently
rewritten. Learning is isolated from frozen test evaluation.

## What the graph adds

The graph exposes rule provenance, revisions, certification and structural
connections, rather than only retrieving similar question text.
Whether that improves accuracy over flat retrieval remains **unmeasured**.
The flat ablation uses the same finished Lore facts and must be reported,
including if it performs better.
Identical rendered facts share one retrieval slot, so a meaning attached to
multiple columns does not crowd other facts out of the flat comparison.

## HydraDB and SelfGraph

HydraDB persists the graph. SelfGraph supplies entities, relations, revisions,
certification, namespaced facts and lexical retrieval. Grounding expands those
facts and ranks rules using their feedback history.

Current grounding uses stored direct joins. Native multi-hop path search,
path compression and synonym merging are not implemented. The application
does not pretend these mechanisms are enabled.

## Benchmark protocol and limits

- Fixed model and effort: MiniMax-M3.1-Flash, medium.
- Held-out BIRD Mini-Dev SQLite questions; published prompts are reproduced
  exactly. Floor removes only the supplied evidence, not the schema.
- Learning uses the public BIRD dev stream after same-database question/SQL
  overlap and token-Jaccard filtering. Split and seed are recorded in the report.
- Lore and vector learn sequentially within each database, then freeze at each
  checkpoint. Test questions and their evidence never become learned facts.
- Strict execution compares complete sets of row tuples. Output row order and
  duplicate multiplicity are ignored; column order and exact values matter.
  Execution failures are not treated as empty results.
- Model/network failures retry or stop the run rather than silently becoming
  wrong answers. SQL timeouts remain execution failures.
- Frozen learning sources and runtime adjustments are recorded in
  [`learning_configuration.json`](results/r2/learning_configuration.json).
- Wilson intervals describe accuracy; paired bootstrap intervals compare the
  same completed test questions. Partial runs are not evidence of a gain.

This is one model, one public benchmark and a simulated analyst-feedback
stream, not a claim of general production performance. Gold SQL and execution
timeouts can limit the benchmark. The interactive app caps displayed results;
the benchmark evaluates full results without that display cap.
Rule confidence is feedback-based, not semantic proof. A query can succeed
despite an irrelevant retrieved rule, and source labels can encode quirks.

## Load test

The trained-graph load test is pending. The existing
[`load.smoke.json`](results/r2/load.smoke.json) is explicitly a schema-only
connectivity smoke, not the required trained result.

The final test exercises `ground()` without an LLM, with unfrozen readers so
requests actually read HydraDB. It reports latency percentiles, throughput,
errors and graph size in `results/r2/load.json`.

## Run locally in five commands

Requires Python 3.11+, Node 24, Docker with Compose, and MiniMax credentials.
Run these from the repository root. After command 2, edit the private `.env`:
set `HYDRA_TOKEN` to a fresh secret, add the model API key, and set
`LORE_LLM_EFFORT=medium`. Never commit `.env`.

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[bench,dev]'
cp .env.example .env
docker compose up -d hydradb && .venv/bin/python -m lore.bench.download
(cd web && npm ci && npm run build)
LORE_LLM_CONCURRENCY=2 LORE_LLM_MIN_INTERVAL_S=2 .venv/bin/uvicorn lore.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open `http://127.0.0.1:8000`. Without completed seeds and a measured demo
manifest, the app deliberately offers an untrained sandbox, not a claimed
trained demo. Benchmark downloads are separate from Git.

The sandbox accepts read-only queries. A correction is only a proposal until
the analyst confirms it. Execution checking does not prove semantic correctness:
the person confirming SQL is responsible for its meaning. Sandbox state is
separate from shared trained facts and all benchmark namespaces.

## Reproduce the benchmark

Use a new run ID if changing the model, effort, split, database selection or
learning protocol. The measured run ID is `r2`; do not mix it with the earlier
incomplete maximum-effort `r1`.

```sh
export LORE_LLM_EFFORT=medium LORE_LLM_CONCURRENCY=2 LORE_LLM_MIN_INTERVAL_S=2
.venv/bin/python -m lore.bench.check_data --run r2
.venv/bin/python -m lore.bench.run --run r2 --systems floor,ceiling
.venv/bin/python -m lore.bench.review_baselines --run r2
```

First inspect the complete baseline gap and manual review. Do not bypass the
baseline gate. Then run and inspect the small learning validation before the
full systems:

```sh
.venv/bin/python -m lore.bench.run --run validation --baseline-run r2 --systems floor,lore --dbs financial,california_schools --stream-cap 30 --checkpoints 1.0
.venv/bin/python -m lore.bench.inspect_rules --run validation
export LORE_LLM_CONCURRENCY=4
.venv/bin/python -m lore.bench.run --run r2 --systems lore --stream-cap 80 --checkpoints 0.25,0.5,1.0
.venv/bin/python -m lore.bench.run --run r2 --systems vector --stream-cap 80 --checkpoints 0.25,0.5,1.0
.venv/bin/python -m lore.bench.run --run r2 --systems flat --from-run r2
.venv/bin/python -m lore.bench.report --run r2
.venv/bin/python -m lore.seeds export --run r2 --out seeds/
.venv/bin/python -m lore.bench.load --run r2 --concurrency 10,50,100 --requests 1000
```

Run `.venv/bin/pytest -q` for local tests. For real HydraDB integration checks,
run `LORE_INTEGRATION=1 .venv/bin/pytest -q`.
Use an unused validation run ID. The recorded `s1`–`s3` runs are historical
calibrations, not results to overwrite with the final code.

## Built but not established by reported numbers

The sandbox UI, correction confirmation, rule certification, seed round-trip,
vector and flat implementations, paired reporting and deployment image exist.
Their unit/integration checks are not substitutes for the unfinished accuracy,
trained-load and final live-demo gates.

VM deployment instructions are in [`deploy/README.md`](deploy/README.md);
the approved free-hosting route is in [`deploy/hf/README.md`](deploy/hf/README.md).
Hosting access and deployment remain pending. Public repository publication is
approved only after final checks; nothing has been published yet.
The [submission handoff](SUBMISSION.md) tracks owner actions and outstanding gates.

## Data attribution

Benchmark questions, SQL and databases come from [BIRD](https://bird-bench.github.io/)
and the [BIRD Mini-Dev release](https://huggingface.co/datasets/birdsql/bird_mini_dev).
Source URLs and hashes are recorded in
[`results/data/sources.json`](results/data/sources.json).
BIRD data and derived benchmark/seed data retain **CC BY-SA 4.0** terms.
Downloaded databases are not included in this repository.
See [data attribution and modification notices](DATA_LICENSE.md).

## License

Lore code is [MIT licensed](LICENSE). Dataset rights and attribution are separate.
