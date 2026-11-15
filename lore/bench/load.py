"""Measure uncached grounding, without an LLM, against real learned namespaces."""

import argparse
import asyncio
import hashlib
import json
import random
import time
from datetime import UTC, datetime

import numpy as np

from lore.bench.stats import graph_counts
from lore.bird import db_path, load_test
from lore.config import ROOT, settings
from lore.connection_pool import GRAPH_POOL_SIZE, configure_graph_pool
from lore.graphdb import open_graph
from lore.live_reader import LiveGraphReader, ground
from lore.schema_ingest import read_schema


async def load(args):
    configure_graph_pool()
    if args.requests < 1 or any(c < 1 for c in args.concurrency):
        raise ValueError("Request and concurrency counts must be positive")
    questions = load_test()
    dbs = sorted({q.db_id for q in questions})
    for db in dbs:
        path = settings.data_dir / "runs" / args.run / f"state.lore.{db}.json"
        if not args.allow_untrained and (
            not path.exists() or not json.loads(path.read_text())["complete"]
        ):
            raise RuntimeError(f"Finish the learned namespace before measuring load: {db}")
    graphs, readers, schemas = {}, {}, {}
    try:
        for db in dbs:
            graphs[db] = await open_graph(f"{args.run}.lore.{db}")
            schemas[db], _ = await asyncio.to_thread(read_schema, db_path(db))
            readers[db] = LiveGraphReader(graphs[db], schemas[db])
        print("Opened all trained namespaces; starting measured grounding", flush=True)
        results = []
        for concurrency in args.concurrency:
            rng = random.Random(0)
            choices = [rng.choice(questions) for _ in range(args.requests)]
            latencies, errors = [], []
            queue = iter(choices)
            start = time.monotonic()

            async def worker(
                queue=queue, errors=errors, latencies=latencies, concurrency=concurrency
            ):
                for q in queue:
                    began = time.monotonic()
                    try:
                        await ground(readers[q.db_id], schemas[q.db_id], q.question)
                    except Exception as exc:
                        errors.append(type(exc).__name__ + ": " + str(exc)[:200])
                    finally:
                        latencies.append(1000 * (time.monotonic() - began))
                    if len(latencies) % 100 == 0:
                        print(f"concurrency={concurrency} completed={len(latencies)}", flush=True)

            await asyncio.gather(*(worker() for _ in range(concurrency)))
            elapsed = time.monotonic() - start
            row = {
                "concurrency": concurrency,
                "requests": len(latencies),
                "p50_ms": float(np.percentile(latencies, 50)),
                "p95_ms": float(np.percentile(latencies, 95)),
                "p99_ms": float(np.percentile(latencies, 99)),
                "max_ms": max(latencies),
                "requests_per_second": len(latencies) / elapsed,
                "successes_per_second": (len(latencies) - len(errors)) / elapsed,
                "error_count": len(errors),
                "error_samples": errors[:5],
                "elapsed_s": elapsed,
            }
            results.append(row)
            print(json.dumps(row), flush=True)
        count_path = ROOT / "results" / args.run / "counts.json"
        if count_path.exists() and not args.allow_untrained:
            # Completed benchmark namespaces are immutable. Reuse their full audit,
            # not hundreds of untimed pagination queries before every load run.
            raw_counts = count_path.read_bytes()
            counts = json.loads(raw_counts)
            if set(counts["per_db"]) != set(dbs):
                raise ValueError("Completed graph audit does not cover the load namespaces")
            counts_source = {
                "kind": "completed-run graph audit, not recounted during load",
                "path": f"results/{args.run}/counts.json",
                "sha256": hashlib.sha256(raw_counts).hexdigest(),
            }
        else:
            print("Grounding complete; collecting live graph counts", flush=True)
            counts = await graph_counts(args.run, dbs)
            counts_source = {"kind": "live recount after measured grounding"}
        report = {
            "run": args.run,
            "date": datetime.now(UTC).isoformat(),
            "seed": 0,
            "frozen": False,
            "reader": "request-scoped-anchored-JOINS; no cross-request graph cache",
            "per_namespace_grounding_concurrency": 1,
            "latency_includes_admission_queue": True,
            "llm_calls": 0,
            "per_namespace_connection_pool_size": GRAPH_POOL_SIZE,
            "counts": counts,
            "counts_source": counts_source,
            "levels": results,
            "trained": not args.allow_untrained,
        }
        target = ROOT / "results" / args.run
        target.mkdir(parents=True, exist_ok=True)
        (target / ("load.smoke.json" if args.allow_untrained else "load.json")).write_text(
            json.dumps(report, indent=2) + "\n"
        )
    finally:
        await asyncio.gather(*(graph.close() for graph in graphs.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument(
        "--concurrency", default="10,50,100", type=lambda x: [int(v) for v in x.split(",")]
    )
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--allow-untrained", action="store_true")
    asyncio.run(load(parser.parse_args()))
