"""Verify suggested teaching pairs through the real API in fresh, isolated sandboxes."""

import argparse
import asyncio
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from lore.api import Service, create_app
from lore.bench.demo import build
from lore.bird import load_stream, load_test
from lore.config import ROOT, settings
from lore.providers import create_llm
from lore.sqlexec import GoldCache, ex_match, execute


class SandboxReplay(Service):
    async def startup(self):
        # This validator must not re-import or write shared trained namespaces.
        pass


def diverse_pairs(pairs):
    """Try different follow-ups before exhausting one question's possible teachers."""
    groups = {}
    for pair in pairs:
        groups.setdefault(pair["b"], []).append(pair)
    return [
        group[index]
        for index in range(max(map(len, groups.values()), default=0))
        for group in groups.values()
        if index < len(group)
    ]


async def matches_answer(answer, question, gold):
    if answer.get("error"):
        return False
    # API rows are display-capped. Verify its actual SQL using the full benchmark result.
    rows, error, _ = await execute(question.db_path, answer["sql"])
    expected, gold_error, _ = await gold.get(question)
    return not error and not gold_error and ex_match(rows, expected)


async def post(client, path, body):
    response = await client.post(path, json=body)
    response.raise_for_status()  # Infrastructure failures stop validation, not a semantic failure.
    return response.json()


async def replay_pair(client, service, scope, pair, questions, gold):
    a, b = questions[pair["a"]], questions[pair["b"]]
    assert a.key.startswith("s") and b.key.startswith("t")
    assert a.db_id == b.db_id == scope["db"] == pair["db"]
    result = {"db": pair["db"], "a": a.key, "b": b.key, "passed": False}
    before = await post(client, "/api/ask", {**scope, "question": b.question})
    if await matches_answer(before, b, gold):
        return {**result, "reason": "followup_already_correct"}
    first = await post(client, "/api/ask", {**scope, "question": a.question})
    if await matches_answer(first, a, gold):
        return {**result, "reason": "teaching_question_already_correct"}
    proposal = (
        await post(
            client,
            "/api/feedback",
            {
                "ask_id": first["ask_id"],
                "verdict": "down",
                "hint": pair["hint"],
            },
        )
    )["proposal"]
    if not await matches_answer(proposal, a, gold):
        return {**result, "reason": "hint_proposal_not_correct"}
    saved = await post(
        client,
        "/api/feedback",
        {
            "ask_id": proposal["ask_id"],
            "verdict": "confirm",
            "sql": proposal["sql"],
        },
    )
    if not saved["learned"]:
        return {**result, "reason": "no_reusable_rule"}
    after = await post(client, "/api/ask", {**scope, "question": b.question})
    if not await matches_answer(after, b, gold):
        return {**result, "reason": "followup_still_wrong"}
    context = await service.context(scope["db"], "sandbox", scope["session"])
    contributing = []
    for edge in after["graph"]["edges"]:
        if edge["type"] == "MEANS" and edge.get("used"):
            rule = await context.graph.relations.get(edge["id"])
            if rule and rule.properties.get("origin") == "u" + first["ask_id"]:
                contributing.append(hashlib.sha256(rule.properties["sql"].encode()).hexdigest())
    if not contributing:
        return {**result, "reason": "new_rule_not_used"}
    return {
        **result,
        "passed": True,
        "reason": "wrong_before_correct_after_with_new_rule_used",
        "used_rule_sql_hashes": sorted(contributing),
        "suggestion": {
            "question": a.question,
            "hint": pair["hint"],
            "followup": b.question,
            "verified": True,
        },
    }


async def run(run, attempts_per_db):
    if attempts_per_db < 3:
        raise ValueError("At least three candidate attempts per database are required")
    directory = settings.data_dir / "runs" / run
    metadata = json.loads((directory / "metadata.json").read_text())
    for key, value in (
        ("model", settings.model),
        ("effort", settings.effort),
        ("max_tokens", settings.max_tokens),
    ):
        if metadata[key] != value:
            raise ValueError(f"Replay {key} differs from the measured run")
    await build(run)
    candidates = json.loads((directory / "demo_candidates.json").read_text())
    streams = load_stream(metadata["seed"], metadata["stream_cap"])
    questions = {q.key: q for group in streams.values() for q in group}
    questions.update({q.key: q for q in load_test()})
    target = ROOT / "results" / run / "demo_replays.json"
    records = json.loads(target.read_text()) if target.exists() else []
    attempted = {(r["db"], r["a"], r["b"]) for r in records}
    gold = GoldCache()
    for db, pairs in candidates.items():
        for pair in diverse_pairs(pairs):
            existing = [r for r in records if r["db"] == db]
            if sum(r["passed"] for r in existing) >= 3 or len(existing) >= attempts_per_db:
                break
            if (db, pair["a"], pair["b"]) in attempted:
                continue
            # Each trial starts with schema only. Never reuse a benchmark/trained namespace.
            with tempfile.TemporaryDirectory(prefix="demo-replay-") as state:
                completion = create_llm(
                    run + "-demo-replay", cache_path=Path(state) / "completions.sqlite"
                )
                service = SandboxReplay(
                    Path(state),
                    run=run,
                    # Independent generation, not a benchmark/cache replay. Every candidate
                    # starts with both a fresh graph and a fresh completion cache.
                    llm=completion,
                )
                app = create_app(service)
                scope = {"db": db, "mode": "sandbox", "session": uuid4().hex}
                async with (
                    app.router.lifespan_context(app),
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://replay"
                    ) as client,
                ):
                    record = await replay_pair(client, service, scope, pair, questions, gold)
                # Retain metering, not private prompts, answers or capability-bearing state.
                record["llm_usage"] = completion.usage()
            record.update(
                model=settings.model, effort=settings.effort, at=datetime.now(UTC).isoformat(),
                hint_protocol=pair.get("hint_protocol", "rule-fragment-v1"),
                hint_sha256=hashlib.sha256(pair.get("hint", "").encode()).hexdigest(),
            )
            records.append(record)
            attempted.add((db, pair["a"], pair["b"]))
            temporary = target.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(records, indent=2) + "\n")
            temporary.replace(target)
            print(
                json.dumps({k: record[k] for k in ("db", "a", "b", "passed", "reason")}), flush=True
            )
    await build(run)
    counts = {db: sum(r["passed"] for r in records if r["db"] == db) for db in candidates}
    if any(count < 3 for count in counts.values()):
        raise SystemExit(f"Three verified pairs per database are not ready: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--attempts-per-db", type=int, default=12)
    args = parser.parse_args()
    asyncio.run(run(args.run, args.attempts_per_db))
