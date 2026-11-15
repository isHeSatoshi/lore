"""Resumable, execution-checked benchmark. Network failures stop the run."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from lore.bird import extract_sql, load_stream, load_test
from lore.config import ROOT, settings
from lore.llm import LLM
from lore.sqlexec import GoldCache, ex_match, execute
from lore.systems import Ceiling, Flat, Floor, Lore, Outcome, Vector


def answer_key(row):
    return row["system"], row["phase"], row["checkpoint"], row["key"]


def read_answers(path):
    path = Path(path)
    if not path.exists():
        return []
    content = path.read_bytes()
    lines = content.splitlines(keepends=True)
    result = []
    for i, line in enumerate(lines):
        try:
            result.append(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if i != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError(f"Corrupt answer journal at line {i + 1}") from None
    return result


class Answers:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows = read_answers(self.path)
        self.done = {answer_key(r): r for r in self.rows}
        if len(self.done) != len(self.rows):
            raise ValueError("Answer journal contains duplicate evaluation keys")
        # A power loss may leave an incomplete final append; preserve complete rows only.
        if self.path.exists() and not self.path.read_bytes().endswith(b"\n"):
            self.path.write_text("".join(json.dumps(r) + "\n" for r in self.rows))

    def append(self, row):
        key = answer_key(row)
        if key in self.done:
            return
        with self.path.open("a") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())
        self.rows.append(row)
        self.done[key] = row

    def get(self, system, phase, checkpoint, key):
        return self.done.get((system, phase, checkpoint, key))


@contextmanager
def run_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another benchmark process is writing this run") from None
        yield


async def evaluate(system, q, llm, gold, journal, phase="test", checkpoint=0, extras=None):
    existing = journal.get(system.name, phase, checkpoint, q.key)
    if existing:
        return existing
    start = time.monotonic()
    visible = q if system.name == "ceiling" else q.without_evidence()
    prompt, trace = await system.build_prompt(visible)
    if system.name != "ceiling" and q.evidence and q.evidence in prompt:
        raise AssertionError(f"Evidence leak in {system.name} prompt for {q.key}")
    try:
        completion = await llm.complete(prompt)
    except Exception as exc:
        exc.add_note(f"Benchmark request: {system.name}/{phase}/{checkpoint}/{q.db_id}/{q.key}")
        raise
    sql = extract_sql(completion.text)
    rows, error, sql_ms = await execute(q.db_path, sql)
    gold_rows, gold_error, _ = await gold.get(q)
    correct = ex_match(rows, gold_rows)
    row = dict(
        system=system.name,
        phase=phase,
        checkpoint=checkpoint,
        db_id=q.db_id,
        key=q.key,
        sql=sql,
        error=error,
        gold_error=gold_error,
        rows_ok=error is None,
        correct=correct,
        prompt_tokens=completion.input_tokens,
        completion_tokens=completion.output_tokens,
        ms=int((time.monotonic() - start) * 1000),
        sql_ms=sql_ms,
        block_chars=trace.get("block_chars", 0),
        trace=trace,
        cached=completion.cached,
        prompt_hash=hashlib.sha256(prompt.encode()).hexdigest(),
    )
    row.update(extras or {})
    journal.append(row)
    n = sum(r["system"] == system.name and r["phase"] == phase for r in journal.rows)
    if n % 25 == 0:
        print(f"{system.name} {phase}: {n} complete", flush=True)
    return row


def outcome(row):
    return Outcome(row["sql"], row["rows_ok"], row["error"], row["correct"], row["trace"])


def baseline_report(journal, run):
    systems = {}
    for name in ("floor", "ceiling"):
        rows = [r for r in journal.rows if r["system"] == name and r["phase"] == "test"]
        if rows:
            systems[name] = {
                "n": len(rows),
                "correct": sum(r["correct"] for r in rows),
                "accuracy": 100 * sum(r["correct"] for r in rows) / len(rows),
                "mean_prompt_tokens": sum(r["prompt_tokens"] for r in rows) / len(rows),
            }
    report = {"model": settings.model, "effort": settings.effort, "systems": systems}
    if all(systems.get(s, {}).get("n") == 500 for s in ("floor", "ceiling")):
        difference = systems["ceiling"]["correct"] - systems["floor"]["correct"]
        report["gap_points"] = 100 * difference / 500
        report["gap_gate_pass"] = difference >= 25
        report["ceiling_debug_required"] = systems["ceiling"]["correct"] < 200
    target = ROOT / "results" / run
    target.mkdir(parents=True, exist_ok=True)
    (target / "baseline.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def require_baseline(run):
    path = ROOT / "results" / run / "baseline.json"
    if not path.exists():
        raise RuntimeError("Full floor/ceiling baseline gate is not finished")
    report = json.loads(path.read_text())
    if report.get("model") != settings.model or report.get("effort") != settings.effort:
        raise RuntimeError("Baseline model settings differ from this run")
    full = all(report.get("systems", {}).get(s, {}).get("n") == 500 for s in ("floor", "ceiling"))
    systems = report.get("systems", {})
    if (
        not full
        or systems["ceiling"]["correct"] - systems["floor"]["correct"] < 25
        or systems["ceiling"]["correct"] < 200
    ):
        raise RuntimeError("Baseline gate did not pass; stop and ask the owner")


async def run_stream(system, streams, test, checkpoints, llm, gold, journal, directory):
    async def database(db):
        stream = streams[db]
        held_out = [q for q in test if q.db_id == db]
        points = {}
        for fraction in checkpoints:
            points.setdefault(max(1, math.ceil(len(stream) * fraction)), []).append(fraction)
        for index, q in enumerate(stream, start=1):
            row = await evaluate(
                system, q, llm, gold, journal, phase="stream", extras={"stream_index": index}
            )
            await system.observe(q.without_evidence(), outcome(row))
            for fraction in points.get(index, []):
                await system.freeze(True, db)
                try:
                    await asyncio.gather(
                        *(
                            evaluate(
                                system,
                                held,
                                llm,
                                gold,
                                journal,
                                checkpoint=fraction,
                                extras={"stream_seen": index, "stream_total": len(stream)},
                            )
                            for held in held_out
                        )
                    )
                finally:
                    await system.freeze(False, db)
                state = {
                    "system": system.name,
                    "db_id": db,
                    "stream_seen": index,
                    "stream_total": len(stream),
                    "checkpoint": fraction,
                    "complete": index == len(stream) and fraction == 1.0,
                }
                target = directory / f"state.{system.name}.{db}.json"
                temp = target.with_suffix(".tmp")
                temp.write_text(json.dumps(state, indent=2) + "\n")
                temp.replace(target)

    await asyncio.gather(*(database(db) for db in sorted(streams)))


async def run(args):
    directory = settings.data_dir / "runs" / args.run
    with run_lock(directory):
        journal = Answers(directory / "answers.jsonl")
        meta_path = directory / "metadata.json"
        metadata = {
            "model": settings.model,
            "effort": settings.effort,
            "max_tokens": settings.max_tokens,
            "seed": args.seed,
            "stream_cap": args.stream_cap,
            "concurrency": settings.concurrency,
        }
        if meta_path.exists():
            old = json.loads(meta_path.read_text())
            for key in ("model", "effort", "max_tokens", "seed", "stream_cap"):
                if old[key] != metadata[key]:
                    raise ValueError(f"Run configuration changed at {key}; use a new run id")
            metadata = old
            metadata.setdefault(
                "execution_history",
                [
                    {
                        "at": old["date"],
                        "concurrency": old["concurrency"],
                        "min_interval_s": 0,
                    }
                ],
            )
        else:
            metadata["date"] = datetime.now(UTC).isoformat()
            metadata["execution_history"] = []
        metadata["execution_history"].append(
            {
                "at": datetime.now(UTC).isoformat(),
                "concurrency": settings.concurrency,
                "min_interval_s": settings.min_interval_s,
                "systems": args.systems,
            }
        )
        test = load_test()
        if args.dbs:
            wanted = set(args.dbs.split(","))
            unknown = wanted - {q.db_id for q in test}
            if unknown:
                raise ValueError(f"Unknown databases: {sorted(unknown)}")
            test = [q for q in test if q.db_id in wanted]
        dbs = sorted({q.db_id for q in test})
        if metadata.get("dbs", dbs) != dbs:
            raise ValueError("Run databases changed; use a new run id")
        metadata["dbs"] = dbs
        metadata.setdefault("protocols", {})
        checkpoints = sorted(set(float(x) for x in args.checkpoints.split(",")))
        if not checkpoints or any(not 0 < x <= 1 for x in checkpoints) or checkpoints[-1] != 1:
            raise ValueError("Checkpoints must be in (0, 1] and include 1.0")
        if args.stream_cap < 1:
            raise ValueError("Stream cap must be positive")
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
        llm, gold = LLM(args.run), GoldCache()
        try:
            for name in args.systems.split(","):
                if name in ("lore", "vector", "flat"):
                    require_baseline(args.baseline_run or args.from_run or args.run)
                if name == "floor":
                    system = Floor()
                elif name == "ceiling":
                    system = Ceiling()
                elif name == "lore":
                    system = await Lore.create(args.run, dbs, llm)
                elif name == "vector":
                    system = Vector()
                elif name == "flat":
                    if not args.from_run:
                        raise ValueError("Flat retrieval needs --from-run")
                    protocol = {"from_run": args.from_run}
                    if metadata["protocols"].get(name, protocol) != protocol:
                        raise ValueError("Flat source changed; use a fresh run")
                    metadata["protocols"][name] = protocol
                    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
                    for db in dbs:
                        state_path = (
                            settings.data_dir / "runs" / args.from_run / f"state.lore.{db}.json"
                        )
                        if (
                            not state_path.exists()
                            or not json.loads(state_path.read_text())["complete"]
                        ):
                            raise RuntimeError(f"Lore source is not finished for {db}")
                    system = await Flat.create(args.from_run, dbs)
                else:
                    raise ValueError(f"Unknown system: {name}")
                try:
                    if system.learns:
                        protocol = {
                            "checkpoints": checkpoints,
                            "seed": args.seed,
                            "stream_cap": args.stream_cap,
                        }
                        previous = metadata["protocols"].get(name)
                        if previous and previous != protocol:
                            raise ValueError("Learning protocol changed; use a fresh run")
                        metadata["protocols"][name] = protocol
                        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
                        streams = load_stream(args.seed, args.stream_cap, run=args.run)
                        streams = {db: streams[db] for db in dbs}
                        await run_stream(
                            system, streams, test, checkpoints, llm, gold, journal, directory
                        )
                    else:
                        await asyncio.gather(
                            *(
                                evaluate(
                                    system,
                                    q,
                                    llm,
                                    gold,
                                    journal,
                                    checkpoint=1.0 if name == "flat" else 0,
                                )
                                for q in test
                            )
                        )
                finally:
                    await system.close()
                report = baseline_report(journal, args.run)
                print(json.dumps(report), flush=True)
            if report.get("ceiling_debug_required"):
                raise SystemExit(
                    "Ceiling below 40%; inspect extraction, timeouts, and model mistakes"
                )
            if report.get("gap_gate_pass") is False:
                raise SystemExit("Floor-to-ceiling gap is under 5 points; stop and ask the owner")
            print("Benchmark evaluation finished", flush=True)
        finally:
            await llm.close()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--systems", required=True)
    p.add_argument("--dbs")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--stream-cap", type=int, default=80)
    p.add_argument("--checkpoints", default="0.25,0.5,1.0")
    p.add_argument("--from-run")
    p.add_argument("--baseline-run")
    return p


if __name__ == "__main__":
    asyncio.run(run(parser().parse_args()))
