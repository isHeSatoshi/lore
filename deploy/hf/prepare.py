"""Build a local allowlisted Space folder, never create or publish a remote resource."""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def release_databases(root, run):
    if run == "r3":
        raise ValueError("r3 is a failed tool-policy preflight, not a public release")
    results = root / "results" / run
    summary = json.loads((results / "summary.json").read_text())
    for system in ("floor", "ceiling", "lore", "vector", "flat"):
        points = summary["systems"].get(system, [])
        if not points or any(not p["complete"] or p["n"] != 500 for p in points):
            raise ValueError("Finish every full-test system before preparing a public Space")
        expected = (
            {0.25, 0.5, 1.0} if system in ("lore", "vector") else {1.0} if system == "flat" else {0}
        )
        if {p["checkpoint"] for p in points} != expected:
            raise ValueError("Required benchmark checkpoints are missing")
    demo = json.loads((results / "demo.json").read_text())
    databases = [d["id"] for d in demo["databases"]]
    if len(set(databases)) != 4:
        raise ValueError("The measured demo needs four different databases")
    replays = json.loads((results / "demo_replays.json").read_text())
    for db in databases:
        passed = {
            (r["a"], r["b"])
            for r in replays
            if r["db"] == db
            and r["passed"]
            and r["model"] == summary["model"]
            and r["effort"] == summary["effort"]
        }
        if len(passed) < 3 or not (root / "seeds" / f"{db}.json").exists():
            raise ValueError("Finished seeds and three measured replays per database are required")
    load = json.loads((results / "load.json").read_text())
    if load["trained"] is not True or load["frozen"] is not False or load["llm_calls"] != 0:
        raise ValueError("The load report must exercise real unfrozen trained graphs")
    if {r["concurrency"] for r in load["levels"]} != {10, 50, 100} or any(
        r["requests"] != 1000 or r["error_count"] != 0 for r in load["levels"]
    ):
        raise ValueError("Finish the required trained load test without errors")
    return databases


def prepare(root, run, data_bundle, parent):
    databases = release_databases(root, run)
    bird = data_bundle / "data/bird"
    layout = json.loads((bird / "paths.json").read_text())
    if set(layout["databases"]) != set(databases):
        raise ValueError("Bundle databases differ from the measured demo")
    for relative in [*layout["databases"].values(), *layout["descriptions"].values()]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Nonportable bundle path")
    for relative in layout["databases"].values():
        if (bird / relative).stat().st_size >= 100_000_000:
            raise ValueError("Demo database exceeds the required size limit")
    if not (root / "web/dist/index.html").exists():
        raise ValueError("Build the frontend first")
    parent.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="lore-space-", dir=parent))
    for name in ("pyproject.toml", "LICENSE", "DATA_LICENSE.md"):
        shutil.copy2(root / name, target / name)
    shutil.copy2(root / "README.md", target / "PROJECT_README.md")
    for source, dest in (
        ("space.md", "README.md"),
        ("app.py", "app.py"),
        ("droid_runtime.py", "droid_runtime.py"),
        ("FACTORY_NOTICE.md", "FACTORY_NOTICE.md"),
        ("packages.txt", "packages.txt"),
        ("requirements.txt", "requirements.txt"),
    ):
        shutil.copy2(root / "deploy/hf" / source, target / dest)
    shutil.copytree(
        root / "lore", target / "lore", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    shutil.copytree(root / "web/dist", target / "web/dist")
    destination = target / "data/bird"
    destination.mkdir(parents=True)
    for relative in (
        "paths.json",
        "DATA_LICENSE.md",
        "minidev/sqlite.json",
        "minidev/prompt_template.txt",
        *layout["databases"].values(),
    ):
        dest = destination / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bird / relative, dest)
    for relative in layout["descriptions"].values():
        shutil.copytree(bird / relative, destination / relative)
    (target / "seeds").mkdir()
    for db in databases:
        shutil.copy2(root / "seeds" / f"{db}.json", target / "seeds" / f"{db}.json")
    result_destination = target / "results" / run
    result_destination.mkdir(parents=True)
    for name in (
        "summary.json",
        "counts.json",
        "per_db.json",
        "curve.json",
        "curve.png",
        "demo.json",
        "demo_replays.json",
        "load.json",
        "seeds.json",
        "baseline.json",
        "learning_configuration.json",
        "runtime_configuration.json",
        "connection_pool_validation.json",
        "interruption.hydra.1.json",
        "interruption.hydra.2.json",
        "interruption.sdk.1.json",
        "ceiling_review.json",
        "ceiling_review.md",
    ):
        source = root / "results" / run / name
        if source.exists():
            shutil.copy2(source, result_destination / name)
    for path in target.rglob("*"):
        if path.name.startswith(".env") or path.name in ("llm.sqlite", "app.sqlite"):
            raise ValueError("Private configuration or mutable state found in release")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="r4")
    parser.add_argument("--data-bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(prepare(ROOT, args.run, args.data_bundle.resolve(), args.out.resolve()))
    except (OSError, ValueError, KeyError) as exc:
        print(f"Space preparation blocked ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
