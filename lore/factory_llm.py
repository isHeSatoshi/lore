"""Opt-in Factory agent protocol. Never interchangeable with the raw r2 protocol."""

import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from types import SimpleNamespace

from lore.config import settings
from lore.llm import LLM

MODEL = "minimax-m3.1-flash"
EFFORT = "medium"
SYSTEM_PROMPT = (
    "Respond directly to the user's request. Return only the requested SQL or JSON. "
    "Do not use tools."
)
PROTOCOL = "factory-sdk-v2"


class FactoryMessages:
    def __init__(self, owner, api_key):
        self.owner, self.api_key = owner, api_key
        self.messages = self

    async def create(self, *, model, max_tokens, messages, extra_body):
        from droid_sdk import (
            ReasoningEffort,
            Runtime,
            Session,
            SessionConfig,
            ToolCall,
            ToolUseBlock,
        )

        if (
            model != MODEL
            or max_tokens != 0
            or extra_body != {"output_config": {"effort": EFFORT}}
            or len(messages) != 1
            or messages[0]["role"] != "user"
        ):
            raise ValueError("Factory protocol requires its frozen model, effort, and one user turn")
        config = SessionConfig(
            system_prompt=SYSTEM_PROMPT,
            disable_builtin_skills=True,
            auto_reject_permission_requests=True,
            enabled_tools=(),
            # An empty allowlist means "no restriction" in the CLI. The intersection of
            # this nonempty allowlist and explicit denylist is genuinely empty.
            disabled_tools={"Read"},
            restrict_tools={"Read"},
        )
        # Fresh empty HOME/cwd prevent repository instructions, saved sessions, and custom skills
        # from becoming benchmark context. The API key stays in the child environment, not argv.
        with tempfile.TemporaryDirectory(prefix="lore-factory-") as directory:
            env = {
                key: ""
                for key in os.environ
                if any(
                    word in key.upper()
                    for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "HUGGING_FACE")
                )
            }
            env.update(HOME=directory, XDG_CONFIG_HOME=directory, FACTORY_API_KEY=self.api_key)
            session = Session(
                cwd=directory,
                model=MODEL,
                reasoning_effort=ReasoningEffort.MEDIUM,
                config=config,
                runtime=Runtime(env=env),
                api_key=self.api_key,
            )
            failed = False
            try:
                await session.open()
                if (
                    session.settings.model != MODEL
                    or session.settings.reasoning_effort != ReasoningEffort.MEDIUM
                ):
                    raise RuntimeError("Factory did not select the requested model and effort")
                if any(tool.allowed for tool in await session.list_tools()):
                    raise RuntimeError("Factory tool policy is not empty")
                stream = session.stream(messages[0]["content"], timeout=180)
                async with stream:
                    async for _ in stream:
                        pass
                result = stream.result
            except Exception as exc:
                failed = True
                # SDK errors may include subprocess diagnostics. Do not expose them through
                # benchmark tracebacks or the public API.
                raise RuntimeError(f"Factory SDK request failed ({type(exc).__name__})") from None
            except asyncio.CancelledError:
                failed = True
                raise
            finally:
                try:
                    await asyncio.shield(session.close())
                except Exception as exc:
                    if not failed:
                        raise RuntimeError(
                            f"Factory SDK cleanup failed ({type(exc).__name__})"
                        ) from None
        if result.usage is not None:
            native = asdict(result.usage)
            with self.owner._db() as db:
                db.execute(
                    "INSERT INTO factory_usage VALUES (?, ?, ?, ?)",
                    (
                        self.owner.run,
                        hashlib.sha256(messages[0]["content"].encode()).hexdigest(),
                        result.subtype,
                        json.dumps(native),
                    ),
                )
        if (
            not result.success
            or not result.text.strip()
            or result.usage is None
            or any(
                isinstance(message, ToolCall)
                or any(
                    isinstance(block, ToolUseBlock)
                    for block in getattr(message, "content", ())
                )
                for message in result.messages
            )
        ):
            if result.usage is not None:
                usage = result.usage
                self.owner._record(
                    usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens,
                    usage.output_tokens + usage.thinking_tokens,
                )
            raise RuntimeError("Factory returned an unsuccessful, empty, unmetered, or tool-using turn")
        usage = result.usage
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=result.text)],
            usage=SimpleNamespace(
                input_tokens=usage.input_tokens,
                cache_read_input_tokens=usage.cache_read_tokens,
                cache_creation_input_tokens=usage.cache_creation_tokens,
                output_tokens=usage.output_tokens + usage.thinking_tokens,
            ),
            stop_reason="end_turn",
        )


class FactoryLLM(LLM):
    def __init__(self, run=None, cfg=settings, cache_path=None):
        if (cfg.model, cfg.effort, cfg.max_tokens) != (MODEL, EFFORT, 0):
            raise ValueError("Factory requires minimax-m3.1-flash, medium, max_tokens=0 (SDK-managed)")
        api_key = os.getenv("FACTORY_API_KEY", "")
        if not api_key:
            raise RuntimeError("FACTORY_API_KEY is not configured")
        # Separate storage prevents reuse of raw-provider completions, even for identical prompts.
        super().__init__(
            run,
            cfg=cfg,
            cache_path=cache_path or cfg.data_dir / "cache" / f"{PROTOCOL}.sqlite",
        )
        self._unused_raw_client = self.client
        self.client = FactoryMessages(self, api_key)
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS factory_usage "
                "(run TEXT, prompt_hash TEXT, subtype TEXT, components TEXT)"
            )

    async def close(self):
        await self._unused_raw_client.close()
