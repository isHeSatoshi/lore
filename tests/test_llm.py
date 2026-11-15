import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from lore.config import settings
from lore.llm import LLM, TokenBudgetExceeded


@pytest.mark.asyncio
async def test_cache_and_text_blocks(tmp_path):
    cfg = replace(settings, data_dir=tmp_path, api_key="fixture")
    llm = LLM("unit", cfg=cfg)
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="private reasoning"),
                SimpleNamespace(type="text", text="SELECT 1"),
            ],
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                cache_read_input_tokens=20,
                cache_creation_input_tokens=30,
            ),
            stop_reason="end_turn",
        )

    llm.client.messages.create = create
    try:
        a = await llm.complete("test")
        b = await llm.complete("test")
        assert a.text == b.text == "SELECT 1"
        assert not a.cached and b.cached and len(calls) == 1
        assert llm.usage() == {"input_tokens": 61, "output_tokens": 7, "calls": 1}
        assert json.loads((tmp_path / "runs/unit/usage.json").read_text()) == llm.usage()
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_empty_thinking_response_retries_with_double_budget(tmp_path):
    llm = LLM("unit", cfg=replace(settings, data_dir=tmp_path, api_key="fixture"))
    budgets = []

    async def create(**kwargs):
        budgets.append(kwargs["max_tokens"])
        return SimpleNamespace(
            content=[] if len(budgets) == 1 else [SimpleNamespace(type="text", text="SELECT 1")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
            stop_reason="max_tokens" if len(budgets) == 1 else "end_turn",
        )

    llm.client.messages.create = create
    try:
        r = await llm.complete("retry")
        assert budgets == [settings.max_tokens, 2 * settings.max_tokens]
        assert r.input_tokens == 20 and r.output_tokens == 40
        assert llm.usage()["calls"] == 2
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_budget_gate_blocks_new_network_call(tmp_path):
    llm = LLM("unit", cfg=replace(settings, data_dir=tmp_path, api_key="fixture"))
    try:
        with llm._db() as db:
            db.execute("INSERT INTO usage VALUES ('unit', 80000001, 0, 1)")
        with pytest.raises(TokenBudgetExceeded):
            await llm.complete("must not be sent")
    finally:
        await llm.close()
