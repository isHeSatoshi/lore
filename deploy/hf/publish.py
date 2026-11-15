"""Validate a private release snapshot; publish a NEW free Space only with --publish."""

import argparse
import hashlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

try:
    from .prepare import ROOT, prepare, release_databases
except ImportError:
    from prepare import ROOT, prepare, release_databases

OWNER = "isHeSatoshi"
RUN = "r4"
COLD_SOURCES = {
    "lore/api.py": "lore/api.py",
    "lore/connection_pool.py": "lore/connection_pool.py",
    "deploy/hf/app.py": "app.py",
    "deploy/hf/droid_runtime.py": "droid_runtime.py",
    "deploy/hf/FACTORY_NOTICE.md": "FACTORY_NOTICE.md",
}
COLD_FLAGS = (
    "passed", "read_only_root", "real_launcher", "frontend_javascript_served",
    "gradio_mount", "trained_certification_forbidden",
    "trained_graph_unchanged_after_forbidden_write", "private_file_requests_denied",
    "engine_restart_restored_identical_graphs",
)
VARIABLES = {
    "LORE_LLM_TRANSPORT": "factory",
    "LORE_LLM_MODEL": "minimax-m3.1-flash",
    "LORE_LLM_EFFORT": "medium",
    "LORE_LLM_MAX_TOKENS": "0",
    "LORE_RUN": RUN,
    "LORE_RESULTS_RUN": RUN,
    "FACTORY_DROID_AUTO_UPDATE_ENABLED": "false",
}


class Blocked(Exception):
    """Only static, non-sensitive failure reasons may cross the CLI boundary."""


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def read_json(path):
    return json.loads(path.read_text())


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), "package-type")
    found = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "package-symlink")
        parts = path.relative_to(root).parts
        require(
            all(
                not p.startswith(".") and p not in {
                    "__pycache__", "node_modules", "cache", "history", "runs",
                }
                for p in parts
            ),
            "private-or-mutable-package-path",
        )
        require(path.is_file() or path.is_dir(), "package-special-file")
        found.add(path.relative_to(root).as_posix())
    return found


def scan_credentials(root, credentials):
    values = {value.encode() for value in credentials if value}
    overlap = max(map(len, values), default=1) - 1
    for path in root.rglob("*"):
        require(not any(v in path.relative_to(root).as_posix().encode() for v in values), "credential-in-package")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            previous = b""
            while chunk := stream.read(1024 * 1024):
                chunk = previous + chunk
                require(not any(v in chunk for v in values), "credential-in-package")
                previous = chunk[-overlap:] if overlap else b""


def measured_gates(root, *, packaged=False):
    databases = release_databases(root, RUN)
    results = root / "results" / RUN
    summary = read_json(results / "summary.json")
    require(summary["model"] == VARIABLES["LORE_LLM_MODEL"] and summary["effort"] == "medium", "model-effort")
    require(summary["complete"] is True, "incomplete-summary")
    require(set(summary["systems"]) == {"floor", "ceiling", "lore", "vector", "flat"}, "comparison-systems")
    for points in summary["systems"].values():
        require(len(points) == len({p["checkpoint"] for p in points}), "duplicate-checkpoints")
        for p in points:
            require(
                p["complete"] is True and type(p["correct"]) is int and 0 <= p["correct"] <= 500
                and math.isfinite(p["accuracy"])
                and math.isclose(p["accuracy"], 100 * p["correct"] / 500, abs_tol=1e-9),
                "invalid-accuracy",
            )
    protocol = read_json(results / "learning_configuration.json")
    require(
        protocol["protocol"] == "factory-sdk-v2"
        and protocol["model"] == summary["model"] and protocol["effort"] == summary["effort"]
        and protocol["max_tokens_metadata_sentinel"] == 0
        and protocol["sdk_version"] == "0.5.0" and protocol["droid_version"] == "1.12.1"
        and protocol["tools"] == [],
        "protocol",
    )
    hashes = protocol["file_sha256"]
    require(
        {"lore/factory_llm.py", "lore/providers.py", "lore/bench/factory.py", "lore/bench/run.py"} <= hashes.keys(),
        "missing-protocol-hashes",
    )
    for name, expected in hashes.items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts and path.parts[0] == "lore" and path.suffix == ".py", "protocol-path")
        require(fingerprint(root / path) == expected, "protocol-source-drift")
    runtime = read_json(results / "runtime_configuration.json")
    require(
        runtime["driver_option"] == "max_connection_pool_size"
        and runtime["per_namespace_connection_pool_size"] == 4
        and set(runtime["file_sha256"]) == {
            "lore/connection_pool.py", "lore/bench/factory_runtime.py",
        },
        "graph-runtime",
    )
    for name, expected in runtime["file_sha256"].items():
        require(fingerprint(root / name) == expected, "runtime-source-drift")
    demo = read_json(results / "demo.json")
    require(demo["run"] == RUN and len(demo["databases"]) == 4, "demo-run")
    cold = read_json(results / "hosting_cold.json")
    require(
        all(cold.get(flag) is True for flag in COLD_FLAGS)
        and cold.get("docker_socket") is False
        and type(cold.get("uid")) is int and cold["uid"] > 0
        and cold.get("trained_databases") == 4
        and set(cold.get("databases", [])) == set(databases)
        and cold.get("expected_and_restored_rules") == {
            entry["id"]: entry["rules"] for entry in demo["databases"]
        }
        and all(type(cold.get(key)) is int and cold[key] == 0 for key in (
            "metered_model_calls", "model_consuming_routes_called", "public_ports",
        )),
        "seeded-cold-start",
    )
    require(set(cold.get("source_sha256", {})) == set(COLD_SOURCES), "cold-source-hashes")
    for original, flat in COLD_SOURCES.items():
        require(
            fingerprint(root / (flat if packaged else original))
            == cold["source_sha256"][original],
            "cold-source-drift",
        )
    replays = read_json(results / "demo_replays.json")
    seed_manifest = read_json(results / "seeds.json")
    require(seed_manifest["run"] == RUN, "seed-run")
    load = read_json(results / "load.json")
    require(len(load["levels"]) == 3, "load-levels")
    require(load.get("per_namespace_connection_pool_size") == 4, "load-pool")
    for entry in demo["databases"]:
        db = entry["id"]
        passed = [
            r["suggestion"] for r in replays
            if r["db"] == db and r["passed"] is True
            and r["model"] == summary["model"] and r["effort"] == summary["effort"]
        ]
        suggestions = entry["suggestions"]
        require(
            len({json.dumps(s, sort_keys=True) for s in suggestions}) >= 3
            and all(s in passed and {"question", "hint", "followup"} <= s.keys() for s in suggestions),
            "demo-passed-pairs",
        )
        seed = read_json(root / "seeds" / f"{db}.json")
        entities, relations = seed["entities"], seed["relations"]
        counts = seed_manifest["databases"][db]
        require(entities and relations and counts == {"entities": len(entities), "relations": len(relations)}, "seed-counts")
        require(
            not any(e["type"] == "Example" and e.get("properties", {}).get("key", "").startswith("t") for e in entities)
            and not any(r["type"] == "MEANS" and r.get("properties", {}).get("origin", "").startswith("t") for r in relations),
            "heldout-seed",
        )
    return databases


def validate_snapshot(package, root, temporary, credentials):
    """Reconstruct the allowlist from trusted source, not an uploaded manifest."""
    observed = inventory(package)
    scan_credentials(package, credentials)
    databases = measured_gates(root)
    require(measured_gates(package, packaged=True) == databases, "package-databases")
    bird = package / "data/bird"
    original = root / "data/bird"
    source_layout = read_json(original / "paths.json")
    expected_layout = {
        "databases": {db: source_layout["databases"][db] for db in databases},
        "descriptions": {
            db: source_layout["descriptions"][db] for db in databases
            if db in source_layout["descriptions"] and (original / source_layout["descriptions"][db]).is_dir()
        },
    }
    require(read_json(bird / "paths.json") == expected_layout, "data-layout")
    data_files = ["minidev/sqlite.json", "minidev/prompt_template.txt", *expected_layout["databases"].values()]
    for relative in expected_layout["descriptions"].values():
        data_files.extend(p.relative_to(original).as_posix() for p in (original / relative).rglob("*") if p.is_file())
    require(
        {p.relative_to(bird).as_posix() for p in bird.rglob("*") if p.is_file()}
        == {"paths.json", "DATA_LICENSE.md", *data_files},
        "unknown-data-files",
    )
    for relative in data_files:
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "data-path")
        require(fingerprint(bird / path) == fingerprint(original / path), "data-source-drift")
    # prepare() rechecks full checkpoints/replays/trained load and builds only its
    # explicit source/data/result allowlist. Unknown files cannot enter the commit.
    rebuilt = prepare(root, RUN, package, temporary)
    expected = inventory(rebuilt)
    require(observed == expected, "unknown-or-missing-package-files")
    files = sorted(p for p in expected if (rebuilt / p).is_file())
    for name in files:
        path = Path(name)
        if path.parts[0] == "lore":
            require(path.suffix == ".py", "unknown-source-file")
        if path.parts[:2] == ("web", "dist"):
            require(path.suffix in {".html", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp", ".woff", ".woff2", ".json"}, "unknown-frontend-file")
        require(fingerprint(package / name) == fingerprint(rebuilt / name), "stale-package")
    return files


def private_configuration(root):
    config = {**dotenv_values(root / ".env"), **os.environ}
    token = next((config.get(k) for k in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGING_FACE") if config.get(k)), None)
    factory = config.get("FACTORY_API_KEY")
    require(token and factory, "missing-runtime-or-deployment-credential")
    known = [
        v for k, v in config.items() if v and (
            k.endswith(("_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY"))
            or "SECRET" in k.split("_") or k == "HUGGING_FACE"
        )
    ]
    return token, factory, known


def publish(package, repo, *, root=ROOT, execute=False, api_factory=None):
    require(re.fullmatch(r"isHeSatoshi/[A-Za-z0-9][A-Za-z0-9._-]{0,95}", repo), "approved-owner-or-repo")
    require(not repo.endswith((".", ".git")) and "--" not in repo and ".." not in repo, "repo-name")
    token, factory, known = private_configuration(root)
    signing = secrets.token_urlsafe(48)
    stage = "local-validation"
    try:
        # Never let SDK debug traces emit Authorization headers or protected secrets.
        os.environ["HF_DEBUG"] = "0"
        os.environ["HF_HUB_VERBOSITY"] = "critical"
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        for name in ("huggingface_hub", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        with tempfile.TemporaryDirectory(prefix="lore-publish-") as directory:
            temporary = Path(directory)
            inventory(package)
            snapshot = temporary / "package"
            shutil.copytree(package, snapshot, symlinks=True)
            files = validate_snapshot(snapshot, root, temporary / "rebuild", [*known, token, factory, signing])
            from huggingface_hub import CommitOperationAdd, HfApi, SpaceHardware, constants
            from huggingface_hub.utils import disable_progress_bars

            constants.HF_DEBUG = False
            disable_progress_bars()
            logging.getLogger("huggingface_hub").setLevel(logging.CRITICAL)

            stage = "access-check"
            api = (api_factory or HfApi)(endpoint="https://huggingface.co", token=token)
            who = api.whoami()
            require(who.get("name") == OWNER and who.get("type") == "user", "authenticated-owner")
            access = who.get("auth", {}).get("accessToken", {})
            fine = access.get("fineGrained", {})
            writable = access.get("role") == "write" or "repo.write" in fine.get("global", []) or any(
                s.get("entity", {}).get("name") == OWNER and "repo.write" in s.get("permissions", [])
                for s in fine.get("scoped", [])
            )
            require(writable, "token-write-scope")
            require(not api.repo_exists(repo_id=repo, repo_type="space"), "repo-already-exists-no-clobber")
            zero_spaces = 0
            for space in api.list_spaces(author=OWNER):
                runtime = api.get_space_runtime(space.id)
                zero_spaces += any(
                    hardware == SpaceHardware.ZERO_A10G
                    for hardware in (runtime.hardware, runtime.requested_hardware)
                )
            require(zero_spaces < 2, "no-free-zerogpu-slot")
            if not execute:
                return "Validated locally and read-only; no remote writes"
            stage = "free-create"
            api.create_repo(
                repo_id=repo, repo_type="space", private=False, exist_ok=False,
                space_sdk="gradio", space_hardware=SpaceHardware.ZERO_A10G, space_storage=None,
                space_secrets=[
                    {"key": "FACTORY_API_KEY", "value": factory},
                    {"key": "SPACE_SIGNING_SECRET", "value": signing},
                ],
                space_variables=[{"key": key, "value": value} for key, value in VARIABLES.items()],
            )
            stage = "upload-new-space"
            api.create_commit(
                repo_id=repo, repo_type="space",
                operations=[CommitOperationAdd(path_in_repo=p, path_or_fileobj=snapshot / p) for p in files],
                commit_message="Publish reviewed Lore r4 free Space release",
                num_threads=2,
            )
            return f"Published https://huggingface.co/spaces/{repo}"
    except Blocked:
        raise
    except Exception as exc:
        # Never include raw SDK exceptions, response bodies, filenames or tokens.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        code = f" HTTP {status}" if type(status) is int and 400 <= status <= 599 else ""
        raise Blocked(f"{stage}{code}; no paid fallback; a newly created empty Space may remain if upload failed") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--publish", action="store_true", help="Explicitly enable creation/upload")
    args = parser.parse_args(argv)
    try:
        print(publish(args.package.resolve(), args.repo, execute=args.publish))
        return 0
    except Blocked as exc:
        print(f"Publication blocked ({exc})", file=sys.stderr)
        return 1
    except Exception:
        print("Publication blocked (local configuration)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
