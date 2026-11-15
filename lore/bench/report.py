"""Report complete and partial runs without replacing missing results with guesses."""

import argparse
import asyncio
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime

import numpy as np

from lore.bench.run import read_answers
from lore.bench.stats import graph_counts
from lore.bird import load_stream, load_test
from lore.config import ROOT, settings


def paired_bootstrap(a, b, n=10000, seed=0):
    if not a or len(a) != len(b):
        raise ValueError("Bootstrap inputs must be nonempty paired observations")
    a, b = np.array(a), np.array(b)
    idx = np.random.default_rng(seed).integers(0, len(a), size=(n, len(a)))
    diffs = (a[idx].mean(axis=1) - b[idx].mean(axis=1)) * 100
    return float((a.mean() - b.mean()) * 100), [
        float(np.percentile(diffs, 2.5)),
        float(np.percentile(diffs, 97.5)),
    ]


def accuracy_interval(rows):
    n, k = len(rows), sum(r["correct"] for r in rows)
    if not n:
        return None
    # Wilson interval for each accuracy; comparisons below use the specified paired bootstrap.
    z, p = 1.959963984540054, k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [100 * max(0, center - half), 100 * min(1, center + half)]


def group_metrics(rows, expected, checkpoint, seen):
    n = len(rows)
    return {
        "checkpoint": checkpoint,
        "questions_seen": seen,
        "n": n,
        "expected": expected,
        "complete": n == expected,
        "correct": sum(r["correct"] for r in rows),
        "accuracy": 100 * sum(r["correct"] for r in rows) / n if n else None,
        "ci95": accuracy_interval(rows),
        "mean_prompt_tokens": sum(r["prompt_tokens"] for r in rows) / n if n else None,
        "mean_block_chars": sum(r["block_chars"] for r in rows) / n if n else None,
    }


def summarize(rows, metadata, split, test):
    dbs = set(metadata.get("dbs", {q.db_id for q in test}))
    expected = len([q for q in test if q.db_id in dbs])
    expected_db = Counter(q.db_id for q in test if q.db_id in dbs)
    groups = defaultdict(list)
    for row in rows:
        if row["phase"] == "test" and row["db_id"] in dbs:
            groups[row["system"], row["checkpoint"]].append(row)
    checkpoints = metadata.get("protocols", {}).get("lore", {}).get("checkpoints", [0.25, 0.5, 1.0])
    stream_counts = split.get("stream_per_db", {})
    systems, missing = {}, []
    for name in ("floor", "ceiling", "lore", "vector", "flat"):
        points = [0] if name in ("floor", "ceiling") else [1.0] if name == "flat" else checkpoints
        systems[name] = []
        for checkpoint in points:
            selected = groups[name, checkpoint]
            if len({(r["db_id"], r["key"]) for r in selected}) != len(selected):
                raise ValueError("Duplicate held-out observations")
            seen = sum(math.ceil(stream_counts.get(db, 0) * checkpoint) for db in dbs)
            entry = group_metrics(selected, expected, checkpoint, seen)
            systems[name].append(entry)
            if not entry["complete"]:
                missing.append(f"{name}@{checkpoint:g}: {len(selected)}/{expected}")
    comparisons = {}
    final = {(r["db_id"], r["key"]): r for r in groups["lore", 1.0]}
    for other in ("floor", "vector", "flat"):
        comparison = {
            (r["db_id"], r["key"]): r for r in groups[other, 0 if other == "floor" else 1.0]
        }
        if final.keys() == comparison.keys() and len(final) == expected:
            keys = sorted(final)
            delta, interval = paired_bootstrap(
                [int(final[k]["correct"]) for k in keys],
                [int(comparison[k]["correct"]) for k in keys],
            )
            comparisons[f"lore_minus_{other}"] = {"points": delta, "ci95": interval, "n": len(keys)}
    gap_closed = None
    floor, ceiling, lore = systems["floor"][0], systems["ceiling"][0], systems["lore"][-1]
    if all(r["complete"] for r in (floor, ceiling, lore)):
        gap = ceiling["correct"] - floor["correct"]
        if 100 * gap >= 5 * expected:
            gap_closed = (lore["correct"] - floor["correct"]) / gap
    per_db = []
    for db in sorted(dbs):
        entry = {"db_id": db, "n": expected_db[db]}
        for name in ("floor", "ceiling", "vector", "flat", "lore"):
            selected = [
                r
                for r in groups[name, 0 if name in ("floor", "ceiling") else 1.0]
                if r["db_id"] == db
            ]
            entry[name] = (
                100 * sum(r["correct"] for r in selected) / len(selected)
                if len(selected) == expected_db[db]
                else None
            )
        per_db.append(entry)
    thirds = {"first": [], "last": []}
    for row in rows:
        if row["system"] == "lore" and row["phase"] == "stream" and row["db_id"] in dbs:
            total = stream_counts.get(row["db_id"], 0)
            third = total // 3
            if third and row.get("stream_index", 0) <= third:
                thirds["first"].append(row)
            if third and row.get("stream_index", 0) > total - third:
                thirds["last"].append(row)
    stream_accuracy = {
        part: {
            "n": len(rs),
            "accuracy": 100 * sum(r["correct"] for r in rs) / len(rs) if rs else None,
        }
        for part, rs in thirds.items()
    }
    return {
        "model": metadata["model"],
        "effort": metadata["effort"],
        "date": metadata["date"],
        "seed": metadata["seed"],
        "stream_cap": metadata["stream_cap"],
        "split": split,
        "expected_test_count": expected,
        "systems": systems,
        "comparisons": comparisons,
        "gap_closed": gap_closed,
        "per_db": per_db,
        "stream_accuracy": stream_accuracy,
        "missing": missing,
        "complete": not missing,
        "metric": "set(predicted_rows) == set(gold_rows); errors/timeouts are incorrect",
        "intervals": {
            "accuracy": "Wilson 95%",
            "differences": "paired bootstrap; 10000 samples; seed 0",
        },
        "mechanisms": {
            "native_path_search": False,
            "path_compression": False,
            "fuzzy_merge": False,
            "certification": "supported, not used in benchmark",
        },
    }


def plot(summary, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    for name, color in (("floor", "#7b8794"), ("ceiling", "#b68c49")):
        point = summary["systems"][name][0]
        if point["complete"]:
            ax.axhline(point["accuracy"], label=name, color=color, linestyle="--")
    floor = summary["systems"]["floor"][0]
    for name, color in (("lore", "#386a5a"), ("vector", "#6e77a6")):
        points = [p for p in summary["systems"][name] if p["complete"]]
        if points:
            if floor["complete"]:
                points = [floor] + points
            ax.plot(
                [p["questions_seen"] for p in points],
                [p["accuracy"] for p in points],
                marker="o",
                label=name,
                color=color,
            )
    flat = summary["systems"]["flat"][0]
    if flat["complete"]:
        ax.scatter(
            [flat["questions_seen"]], [flat["accuracy"]], marker="D", label="flat", color="#ad6f6f"
        )
    ax.set(
        xlabel="Stream questions seen (summed across databases)",
        ylabel="Held-out execution accuracy (%)",
        title=f"Lore · {summary['model']} · effort {summary['effort'] or 'default'}",
    )
    ax.grid(alpha=0.2)
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend()
    if summary["missing"]:
        fig.text(0.01, 0.01, "Partial run: incomplete checkpoints are not plotted.", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


async def report(run):
    directory = settings.data_dir / "runs" / run
    metadata = json.loads((directory / "metadata.json").read_text())
    test = load_test()
    load_stream(metadata["seed"], metadata["stream_cap"], run=run)
    target = ROOT / "results" / run
    split = json.loads((target / "split.json").read_text())
    summary = summarize(read_answers(directory / "answers.jsonl"), metadata, split, test)
    summary.update(run=run, generated_at=datetime.now(UTC).isoformat())
    dbs = [r["db_id"] for r in summary["per_db"]]
    counts = await graph_counts(run, dbs)
    summary["counts"] = counts
    for row in summary["per_db"]:
        row["rules"] = counts["per_db"][row["db_id"]]["rules"]
    usage_path = directory / "usage.json"
    summary["usage"] = json.loads(usage_path.read_text()) if usage_path.exists() else None
    (target / "counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    table = [
        "| Database | floor | ceiling | vector | flat | Lore | rules |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["per_db"]:
        scores = [
            f"{row[name]:.2f}%" if row[name] is not None else "pending"
            for name in ("floor", "ceiling", "vector", "flat", "lore")
        ]
        table.append(f"| {row['db_id']} | " + " | ".join(scores) + f" | {row['rules']} |")
    (target / "per_db.md").write_text("\n".join(table) + "\n")
    plot(summary, target / "curve.png")
    print(
        json.dumps(
            {
                "complete": summary["complete"],
                "missing": summary["missing"],
                "comparisons": summary["comparisons"],
            },
            indent=2,
        )
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    asyncio.run(report(parser.parse_args().run))
