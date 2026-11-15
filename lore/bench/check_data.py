import argparse
import asyncio
import json

from lore.bird import db_path, load_stream, load_test, published, render_prompt
from lore.config import ROOT
from lore.sqlexec import GoldCache


async def check(run="r1", seed=0, cap=80):
    test = load_test()
    stream = load_stream(seed, cap, run=run)
    rows = published()
    equal = sum(
        render_prompt(r["db_id"], r["question"], r["evidence"]) == r["prompt"] for r in rows
    )
    empty = [r for r in rows if not r["evidence"]]
    floor_equal = sum(render_prompt(r["db_id"], r["question"]) == r["prompt"] for r in empty)
    gold = GoldCache()
    progress = 0

    async def one(q):
        nonlocal progress
        result = await gold.get(q)
        progress += 1
        if progress % 50 == 0:
            print(f"Gold execution: {progress}/{len(test)}", flush=True)
        return q.key, result

    results = await asyncio.gather(*(one(q) for q in test))
    failures = [
        {"key": key, "error": r[1], "empty": not r[0]} for key, r in results if r[1] or not r[0]
    ]
    report = {
        "test_count": len(test),
        "prompt_equal": equal,
        "prompt_total": len(rows),
        "empty_evidence": len(empty),
        "floor_equal_empty": floor_equal,
        "gold_with_rows": len(test) - len(failures),
        "gold_failures": failures,
        "stream_per_db": {k: len(v) for k, v in stream.items()},
        "db_bytes": {db: db_path(db).stat().st_size for db in sorted(stream)},
    }
    out = ROOT / "results" / run
    out.mkdir(parents=True, exist_ok=True)
    (out / "data_check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    if len(test) != 500 or equal != 500 or floor_equal != len(empty) or len(failures) > 5:
        raise SystemExit(
            "M1 gate failed; inspect data_check.json. Use --minidev-dbs if gold data differ."
        )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", default="r1")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--stream-cap", type=int, default=80)
    a = p.parse_args()
    asyncio.run(check(a.run, a.seed, a.stream_cap))
