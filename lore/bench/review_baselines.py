"""Prepare execution and extraction evidence for the required manual ceiling review."""

import argparse
import asyncio
import hashlib
import json
import sqlite3

from lore.bench.run import read_answers
from lore.bird import extract_sql, load_test, published
from lore.config import ROOT, settings
from lore.sqlexec import GoldCache, ex_match, execute


async def review(run, count=10):
    directory = settings.data_dir / "runs" / run
    meta = json.loads((directory / "metadata.json").read_text())
    questions = {(q.db_id, q.key): q for q in load_test()}
    prompts = {(r["db_id"], f"t{r['question_id']}"): r["prompt"] for r in published()}
    wrong = [
        r
        for r in read_answers(directory / "answers.jsonl")
        if r["system"] == "ceiling"
        and not r["correct"]
        and not r["error"]
        and not r.get("gold_error")
    ][:count]
    if len(wrong) < count:
        raise SystemExit("Not enough completed, non-error wrong ceiling answers to review yet")
    gold = GoldCache()
    report = []
    for row in wrong:
        q = questions[(row["db_id"], row["key"])]
        prompt = prompts[(q.db_id, q.key)]
        key = hashlib.sha256(
            json.dumps([meta["model"], meta["effort"], prompt], ensure_ascii=False).encode()
        ).hexdigest()
        with sqlite3.connect(settings.data_dir / "cache/llm.sqlite") as cache:
            cached = cache.execute("SELECT result FROM cache WHERE key=?", (key,)).fetchone()
        model_text = json.loads(cached[0])["text"] if cached else None
        extracted = extract_sql(model_text) if model_text is not None else None
        pred_rows, error, ms = await execute(q.db_path, row["sql"])
        gold_rows, gold_error, _ = await gold.get(q)
        item = dict(
            key=q.key,
            db_id=q.db_id,
            question=q.question,
            gold_sql=q.gold_sql,
            predicted_sql=row["sql"],
            model_text=model_text,
            extraction_matches_cache=extracted == row["sql"],
            execution_error=error,
            gold_error=gold_error,
            sql_ms=ms,
            predicted_row_count=len(pred_rows) if pred_rows is not None else None,
            gold_row_count=len(gold_rows) if gold_rows is not None else None,
            rerun_correct=ex_match(pred_rows, gold_rows),
        )
        report.append(item)
    target = ROOT / "results" / run / "ceiling_review.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    asyncio.run(review(args.run))
