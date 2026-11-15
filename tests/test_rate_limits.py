import asyncio
from dataclasses import replace
from types import SimpleNamespace

import anthropic
import httpx
import pytest

import lore.llm as module
from lore.config import settings
from lore.llm import LLM, RequestPacer, retry_delay


@pytest.mark.asyncio
async def test_request_spacing_and_shared_cooldown():
    now = [0.0]
    starts = []

    async def sleep(seconds):
        now[0] += seconds
        await asyncio.sleep(0)

    pacer = RequestPacer(2, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        await pacer.wait()
        starts.append(now[0])
    assert starts == [0, 2, 4]
    pacer.defer(30)
    await pacer.wait()
    assert now[0] == 34


def error(status=429, retry_after="1"):
    response = httpx.Response(
        status,
        headers={"retry-after": retry_after},
        request=httpx.Request("POST", "https://example.invalid/messages"),
    )
    return anthropic.RateLimitError("fixture rate limit", response=response, body={})


def test_retry_after_is_a_minimum_not_a_cap():
    assert retry_delay(error(retry_after="120"), 0) == 120
    assert retry_delay(error(retry_after="invalid"), 1) == 30


@pytest.mark.asyncio
async def test_cooldown_extends_an_already_waiting_request():
    now = [0.0]
    entered, release = asyncio.Event(), asyncio.Event()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            entered.set()
            await release.wait()
        now[0] += seconds

    pacer = RequestPacer(2, clock=lambda: now[0], sleep=sleep)
    await pacer.wait()
    waiting = asyncio.create_task(pacer.wait())
    await entered.wait()
    pacer.defer(30)
    release.set()
    await waiting
    assert sleeps == [2, 28]
    assert now[0] == 30


@pytest.mark.asyncio
async def test_rate_limit_retries_share_cooldown_without_scoring_failure(tmp_path, monkeypatch):
    class Pacer:
        waits = 0
        cooldowns = []

        async def wait(self):
            self.waits += 1

        def defer(self, seconds):
            self.cooldowns.append(seconds)

    pacer = Pacer()
    monkeypatch.setattr(module, "_pacer", pacer)
    llm = LLM("fixture", cfg=replace(settings, data_dir=tmp_path, api_key="fixture"))
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 2:
            raise error()
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="SELECT 1")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            stop_reason="end_turn",
        )

    llm.client.messages.create = create
    try:
        assert (await llm.complete("fixture")).text == "SELECT 1"
        assert pacer.waits == 3 and pacer.cooldowns == [15, 30]
        assert llm.usage() == {"input_tokens": 10, "output_tokens": 5, "calls": 1}
        with llm._db() as db:
            assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
    finally:
        await llm.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected_calls", [(429, 5), (401, 1)])
async def test_retries_are_bounded_and_auth_failures_are_not_retried(
    tmp_path, monkeypatch, status, expected_calls
):
    class Pacer:
        async def wait(self):
            pass

        def defer(self, seconds):
            pass

    monkeypatch.setattr(module, "_pacer", Pacer())
    llm = LLM("fixture", cfg=replace(settings, data_dir=tmp_path, api_key="fixture"))
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if status == 429:
            raise error()
        response = httpx.Response(
            401, request=httpx.Request("POST", "https://example.invalid/messages")
        )
        raise anthropic.AuthenticationError("fixture", response=response, body={})

    llm.client.messages.create = create
    try:
        with pytest.raises(anthropic.APIStatusError):
            await llm.complete("fixture")
        assert len(calls) == expected_calls
        assert llm.usage()["calls"] == 0
    finally:
        await llm.close()
