import asyncio
import json
import statistics
from dataclasses import replace

from lore.config import settings
from lore.llm import LLM


async def main():
    llm = LLM(run="smoke")
    try:
        one = await llm.complete("Return only SELECT 1 in a fenced sql block.")
        assert "SELECT 1" in one.text.upper(), one.text
        print("SELECT 1: PASS", flush=True)
        for effort in ("low", "medium"):
            candidate = LLM(run="smoke", cfg=replace(settings, effort=effort))
            try:
                r = await candidate.complete("Return only SELECT 1 in a fenced sql block.")
                print("effort", effort, "accepted", r.ms, flush=True)
            except Exception as exc:
                print("effort", effort, "rejected", type(exc).__name__, flush=True)
            finally:
                await candidate.close()
        path = settings.bird_dir / "minidev" / "published.jsonl"
        if not path.exists():
            raise RuntimeError(
                "Download published Mini-Dev prompts before running the latency smoke."
            )
        row = json.loads(path.read_text().splitlines()[0])
        prompt = row["prompt"]
        # Strip evidence for the load probe; ceiling is the only system allowed to use it.
        if row.get("evidence"):
            prompt = prompt.replace(row["evidence"], "")
        results = await asyncio.gather(
            *(llm.complete(prompt, cache=False) for _ in range(16)), return_exceptions=True
        )
        failures = [type(r).__name__ for r in results if isinstance(r, Exception)]
        ok = [r for r in results if not isinstance(r, Exception)]
        summary = {
            "concurrency": settings.concurrency,
            "requests": len(results),
            "median_ms": statistics.median(r.ms for r in ok) if ok else None,
            "input_tokens": sum(r.input_tokens for r in ok),
            "output_tokens": sum(r.output_tokens for r in ok),
            "errors": failures,
        }
        print(json.dumps(summary, indent=2), flush=True)
        target = settings.data_dir.parent / "results" / "smoke" / "llm.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2) + "\n")
        assert not failures, failures
    finally:
        await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
