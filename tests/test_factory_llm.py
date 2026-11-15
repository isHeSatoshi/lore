import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from lore.config import settings
from lore.factory_llm import EFFORT, MODEL, SYSTEM_PROMPT, FactoryLLM
from lore.llm import LLM, request_guard
from lore.providers import create_llm

sdk = pytest.importorskip("droid_sdk")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_API_KEY", "fixture-private-credential")
    return replace(settings, data_dir=tmp_path, model=MODEL, effort=EFFORT, max_tokens=0)


@pytest.fixture
def fake_session(monkeypatch):
    calls = []

    class Stream:
        def __init__(self):
            self.result = SimpleNamespace(
                success=True, text="SELECT 1;", subtype="success", messages=(),
                usage=sdk.Usage(
                    input_tokens=11, output_tokens=7, cache_creation_tokens=3,
                    cache_read_tokens=5, thinking_tokens=2,
                ),
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class Session:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.settings = SimpleNamespace(model=MODEL, reasoning_effort=sdk.ReasoningEffort.MEDIUM)
            self.closed = False
            self.response = Stream()
            calls.append(self)

        async def open(self):
            assert Path(self.kwargs["cwd"]).is_dir()

        def stream(self, prompt, timeout):
            self.prompt, self.timeout = prompt, timeout
            return self.response

        async def list_tools(self):
            return []

        async def close(self):
            self.closed = True

    monkeypatch.setattr(sdk, "Session", Session)
    return calls


@pytest.mark.asyncio
async def test_fresh_isolated_sessions_cache_and_native_metering(cfg, fake_session):
    llm = FactoryLLM("unit-factory", cfg=cfg)
    try:
        a = await llm.complete("one")
        cached = await llm.complete("one")
        b = await llm.complete("two")
        assert a.text == b.text == cached.text == "SELECT 1;"
        assert cached.cached and len(fake_session) == 2
        assert llm.usage() == {"input_tokens": 38, "output_tokens": 18, "calls": 2}
        assert llm.cache_path.name == "factory-sdk-v2.sqlite"
        with llm._db() as db:
            native = db.execute("SELECT components FROM factory_usage").fetchall()
        assert len(native) == 2 and json.loads(native[0][0])["thinking_tokens"] == 2
        for call in fake_session:
            assert call.kwargs["model"] == MODEL
            assert call.kwargs["reasoning_effort"] == sdk.ReasoningEffort.MEDIUM
            config = call.kwargs["config"]
            assert config.system_prompt == SYSTEM_PROMPT
            assert config.restrict_tools == config.disabled_tools == frozenset({"Read"})
            assert config.enabled_tools == frozenset()
            assert config.auto_reject_permission_requests and config.disable_builtin_skills
            assert call.closed and call.timeout == 180
            assert not Path(call.kwargs["cwd"]).exists()
        assert fake_session[0].kwargs["cwd"] != fake_session[1].kwargs["cwd"]
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_public_guard_covers_sdk_and_cached_requests(cfg, fake_session):
    calls = []

    async def guard():
        calls.append(True)

    llm = FactoryLLM("guard", cfg=cfg)
    token = request_guard.set(guard)
    try:
        await llm.complete("guarded")
        await llm.complete("guarded")
        assert len(calls) == 2 and len(fake_session) == 1
    finally:
        request_guard.reset(token)
        await llm.close()


@pytest.mark.asyncio
async def test_reject_model_fallback_and_sanitize_sdk_diagnostics(cfg, fake_session, monkeypatch):
    original = sdk.Session

    class WrongModel(original):
        async def open(self):
            self.settings.model = "auto"

    monkeypatch.setattr(sdk, "Session", WrongModel)
    llm = FactoryLLM("reject", cfg=cfg)
    try:
        with pytest.raises(RuntimeError, match="Factory SDK request failed") as error:
            await llm.complete("never fall back")
        assert "fixture-private-credential" not in str(error.value)
        assert fake_session[0].closed
        assert llm.usage()["calls"] == 0
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_tool_policy_is_checked_before_inference(cfg, fake_session, monkeypatch):
    original = sdk.Session

    class Unsafe(original):
        async def list_tools(self):
            return [SimpleNamespace(id="Read", allowed=True)]

    monkeypatch.setattr(sdk, "Session", Unsafe)
    llm = FactoryLLM("policy", cfg=cfg)
    try:
        with pytest.raises(RuntimeError, match="Factory SDK request failed"):
            await llm.complete("must not reach inference")
        assert not hasattr(fake_session[0], "prompt")
        assert llm.usage()["calls"] == 0
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_tool_call_message_is_rejected_and_failed_usage_is_metered(
    cfg, fake_session, monkeypatch
):
    original = sdk.Session

    class ToolMessage(original):
        def stream(self, prompt, timeout):
            stream = super().stream(prompt, timeout)
            stream.result.messages = (sdk.ToolCall("Read", "fixture", {}),)
            return stream

    monkeypatch.setattr(sdk, "Session", ToolMessage)
    llm = FactoryLLM("tool-message", cfg=cfg)
    try:
        with pytest.raises(RuntimeError, match="tool-using"):
            await llm.complete("reproduce heterogeneous result messages")
        assert llm.usage() == {"input_tokens": 19, "output_tokens": 9, "calls": 1}
        assert fake_session[0].closed
    finally:
        await llm.close()


def test_reject_incompatible_settings_and_missing_key(cfg, monkeypatch):
    for field, value in (("model", "auto"), ("effort", "high"), ("max_tokens", 8192)):
        with pytest.raises(ValueError):
            FactoryLLM(cfg=replace(cfg, **{field: value}))
    monkeypatch.delenv("FACTORY_API_KEY")
    with pytest.raises(RuntimeError, match="not configured"):
        FactoryLLM(cfg=cfg)


@pytest.mark.asyncio
async def test_explicit_transport_selection_preserves_raw_default(cfg, monkeypatch):
    monkeypatch.delenv("LORE_LLM_TRANSPORT", raising=False)
    raw = create_llm(cfg=cfg)
    assert type(raw) is LLM
    await raw.close()
    monkeypatch.setenv("LORE_LLM_TRANSPORT", "factory")
    factory = create_llm(cfg=cfg)
    assert type(factory) is FactoryLLM
    await factory.close()
    monkeypatch.setenv("LORE_LLM_TRANSPORT", "unknown")
    with pytest.raises(ValueError, match="Unknown"):
        create_llm(cfg=cfg)
