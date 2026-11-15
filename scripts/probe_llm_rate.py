"""Exercise the failed request and heavy real prompts without leaking evidence."""

import asyncio
import json

from lore.bird import load_test, render_prompt
from lore.config import ROOT, settings
from lore.llm import LLM


async def main():
    test = load_test()
    prompts = {q.key: render_prompt(q.db_id, q.question) for q in test}
    chosen = [
        next(q for q in test if q.key == "t40"),
        max(test, key=lambda q: len(prompts[q.key])),
        max(test, key=lambda q: len(q.question)),
    ]
    llm = LLM("r2")
    results = []
    try:
        for q in {q.key: q for q in chosen}.values():
            response = await llm.complete(prompts[q.key])
            item = {
                "key": q.key,
                "db_id": q.db_id,
                "prompt_chars": len(prompts[q.key]),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "ms": response.ms,
                "cached": response.cached,
                "text_chars": len(response.text),
            }
            results.append(item)
            print(json.dumps(item), flush=True)
    finally:
        await llm.close()
    report = {
        "model": settings.model,
        "effort": settings.effort,
        "concurrency": settings.concurrency,
        "min_interval_s": settings.min_interval_s,
        "responses": results,
    }
    target = ROOT / "results/r2/rate_probe.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
