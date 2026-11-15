"""Exercise the real seeded launcher in an isolated container, without model calls."""

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from pathlib import Path

import httpx


def graph_digest(value):
    assert value["nodes"] and value["edges"], "empty trained graph"
    canonical = {
        **value,
        **{
            key: sorted(value[key], key=lambda item: json.dumps(item, sort_keys=True))
            for key in ("nodes", "edges")
        },
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        occupied = False
        for port in (7687, 8443, 9090, 7860):
            with socket.socket() as connection:
                connection.settimeout(0.1)
                occupied |= connection.connect_ex(("127.0.0.1", port)) == 0
        if not occupied:
            return
        time.sleep(0.1)
    raise RuntimeError("launcher ports did not close")


def check(args):
    assert os.getuid() != 0, "run as a non-root user"
    assert not Path("/var/run/docker.sock").exists(), "do not mount a Docker socket"
    assert not os.access(args.source / "lore", os.W_OK), "source must be read-only"
    assert not (args.state / "store").exists(), "start with a fresh engine state"
    args.state.mkdir(parents=True, exist_ok=True)
    for name in ("home", "config"):
        (args.state / name).mkdir(exist_ok=True)
    expected = {
        d["id"]: d["rules"] for d in json.loads(
            (args.source / "results/r4/demo.json").read_text()
        )["databases"]
    }
    assert len(expected) == 4
    env = {
        "PATH": os.environ["PATH"],
        "LANG": "C.UTF-8",
        "HOME": str(args.state / "home"),
        "XDG_CONFIG_HOME": str(args.state / "config"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(args.source),
        "LORE_ROOT": str(args.source),
        "LORE_DATA_DIR": str(args.source / "data"),
        "LORE_HOST_STATE": str(args.state),
        "FACTORY_API_KEY": "cold-check-no-model",
        "SPACE_SIGNING_SECRET": secrets.token_hex(32),
    }
    durations, snapshots = [], []
    with httpx.Client(base_url="http://127.0.0.1:7860", timeout=60, trust_env=False) as client:
        for iteration in range(2):
            started = time.monotonic()
            with (args.state / f"launcher-{iteration}.log").open("wb") as log:
                process = subprocess.Popen(
                    [sys.executable, str(args.source / "deploy/hf/app.py")],
                    cwd=args.source, env=env, stdout=log, stderr=log,
                    start_new_session=True,
                )
                try:
                    deadline = started + args.startup_timeout
                    while True:
                        assert process.poll() is None, "launcher exited before readiness"
                        try:
                            if client.get("/healthz", timeout=2).status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        assert time.monotonic() < deadline, "seeded startup timed out"
                        time.sleep(0.2)
                    durations.append(time.monotonic() - started)
                    databases = client.get("/api/dbs")
                    databases.raise_for_status()
                    rows = databases.json()["databases"]
                    assert {d["id"] for d in rows} == set(expected)
                    assert all(d["trained"] and d["rules"] == expected[d["id"]] for d in rows)
                    frontend = client.get("/")
                    assert frontend.status_code == 200
                    scripts = re.findall(r'<script[^>]+src="([^"]+)"', frontend.text)
                    assert scripts
                    for path in scripts:
                        asset = client.get(path)
                        assert asset.status_code == 200
                        assert "javascript" in asset.headers.get("content-type", "")
                    assert client.get("/hosting/").status_code == 200
                    current = {}
                    for db in sorted(expected):
                        scope = {"db": db, "mode": "trained", "session": "0" * 32}
                        response = client.get("/api/graph", params=scope)
                        response.raise_for_status()
                        current[db] = graph_digest(response.json())
                        response = client.post("/api/certify", json={
                            **scope, "relation_id": "not-a-rule",
                        })
                        assert response.status_code == 403
                        after = client.get("/api/graph", params=scope)
                        assert graph_digest(after.json()) == current[db]
                    for path in (
                        "/hosting/gradio_api/file=" + str(args.state / "auth-token"),
                        "/hosting/gradio_api/file=" + str(args.source / "data/bird/paths.json"),
                    ):
                        assert client.get(path).status_code in (400, 403, 404, 422)
                    snapshots.append(current)
                    (args.state / f"graph-digests-{iteration}.json").write_text(
                        json.dumps(current, indent=2)
                    )
                finally:
                    stop(process)
    assert snapshots[0] == snapshots[1], "trained graph changed after restart"
    cache = args.state / "app/cache/factory-sdk-v2.sqlite"
    with sqlite3.connect(f"file:{cache}?mode=ro", uri=True) as database:
        calls = database.execute("SELECT COALESCE(SUM(calls),0) FROM usage").fetchone()[0]
    assert calls == 0
    return {
        "passed": True,
        "source": "clean committed runtime plus measured demo manifest/data",
        "source_sha256": {
            name: hashlib.sha256((args.source / name).read_bytes()).hexdigest()
            for name in (
                "lore/api.py", "lore/connection_pool.py", "lore/live_reader.py",
                "deploy/hf/app.py", "deploy/hf/droid_runtime.py",
                "deploy/hf/FACTORY_NOTICE.md",
            )
        },
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "uid": os.getuid(),
        "read_only_root": True,
        "docker_socket": False,
        "databases": sorted(expected),
        "trained_databases": 4,
        "expected_and_restored_rules": expected,
        "graph_comparison": "exact node/edge record multisets, independent of response order",
        "cold_start_seconds": durations[0],
        "restart_seconds": durations[1],
        "real_launcher": True,
        "frontend_javascript_served": True,
        "gradio_mount": True,
        "trained_certification_forbidden": True,
        "trained_graph_unchanged_after_forbidden_write": True,
        "private_file_requests_denied": True,
        "engine_restart_restored_identical_graphs": True,
        "model_consuming_routes_called": 0,
        "metered_model_calls": calls,
        "public_ports": 0,
        "limitation": "Local isolated startup/restoration proof, not HF deployment or hosted teaching",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/app"))
    parser.add_argument("--state", type=Path, default=Path("/state"))
    parser.add_argument("--startup-timeout", type=int, default=600)
    arguments = parser.parse_args()
    try:
        print(json.dumps(check(arguments), indent=2))
    except Exception as error:
        print(json.dumps({
            "passed": False, "error_type": type(error).__name__,
            "checker_line": traceback.extract_tb(error.__traceback__)[-1].lineno,
        }), flush=True)
        raise SystemExit(1) from None
