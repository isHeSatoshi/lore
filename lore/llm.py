import asyncio
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import anthropic

from lore.config import settings


class TokenBudgetExceeded(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    ms: int
    cached: bool = False


_semaphore = asyncio.Semaphore(max(1, settings.concurrency))


class LLM:
    def __init__(self, run=None, cfg=settings, cache_path=None):
        self.cfg = cfg
        self.run = run or cfg.run
        self.cache_path = Path(cache_path or cfg.data_dir / "cache" / "llm.sqlite")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = anthropic.AsyncAnthropic(
            base_url=cfg.base_url,
            api_key=cfg.api_key or "not-configured",
            max_retries=4,
            timeout=180,
        )
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, result TEXT)")
            db.execute("""CREATE TABLE IF NOT EXISTS usage (
                run TEXT, input_tokens INTEGER, output_tokens INTEGER, calls INTEGER)""")

    def _db(self):
        return sqlite3.connect(self.cache_path, timeout=30)

    def _record(self, inp, out):
        with self._db() as db:
            db.execute("INSERT INTO usage VALUES (?, ?, ?, 1)", (self.run, inp, out))
        usage = self.usage()
        target = self.cfg.data_dir / "runs" / self.run / "usage.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        # The database is authoritative, the JSON is a convenient snapshot.
        tmp = target.with_suffix(f".{id(self)}.tmp")
        tmp.write_text(json.dumps(usage, indent=2) + "\n")
        tmp.replace(target)
        if usage["input_tokens"] > 80_000_000:
            raise TokenBudgetExceeded("Run exceeded 80 million input tokens; ask the owner.")

    def usage(self):
        with self._db() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), "
                "COALESCE(SUM(calls),0) FROM usage WHERE run=?",
                (self.run,),
            ).fetchone()
        return dict(zip(("input_tokens", "output_tokens", "calls"), row, strict=True))

    async def complete(self, prompt, *, cache=True):
        key = hashlib.sha256(
            json.dumps([self.cfg.model, self.cfg.effort, prompt], ensure_ascii=False).encode()
        ).hexdigest()
        if cache:
            with self._db() as db:
                row = db.execute("SELECT result FROM cache WHERE key=?", (key,)).fetchone()
            if row:
                return LLMResult(**{**json.loads(row[0]), "cached": True})
        if self.usage()["input_tokens"] > 80_000_000:
            raise TokenBudgetExceeded("Run exceeded 80 million input tokens; ask the owner.")
        start = time.monotonic()
        async with _semaphore:
            inp = out = 0
            for attempt in range(2):
                kwargs = dict(
                    model=self.cfg.model,
                    max_tokens=self.cfg.max_tokens * (2**attempt),
                    messages=[{"role": "user", "content": prompt}],
                )
                if self.cfg.effort:
                    kwargs["extra_body"] = {"output_config": {"effort": self.cfg.effort}}
                msg = await self.client.messages.create(**kwargs)
                text = "".join(b.text for b in msg.content if b.type == "text")
                prompt_tokens = (
                    msg.usage.input_tokens
                    + (getattr(msg.usage, "cache_read_input_tokens", 0) or 0)
                    + (getattr(msg.usage, "cache_creation_input_tokens", 0) or 0)
                )
                inp += prompt_tokens
                out += msg.usage.output_tokens
                self._record(prompt_tokens, msg.usage.output_tokens)
                if text.strip() or msg.stop_reason != "max_tokens":
                    break
            if not text.strip():
                raise RuntimeError(
                    "LLM returned no text after retry; stop and inspect the endpoint."
                )
        result = LLMResult(text, inp, out, int((time.monotonic() - start) * 1000))
        if cache:
            with self._db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO cache VALUES (?, ?)", (key, json.dumps(asdict(result)))
                )
        return result

    async def close(self):
        await self.client.close()
