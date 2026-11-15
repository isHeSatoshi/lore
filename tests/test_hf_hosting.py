import asyncio
import hashlib
import json
import os
import shutil
import tomllib
from types import SimpleNamespace

import pytest

from deploy.hf import droid_runtime
from deploy.hf.app import PublicDeadline, configure, image_path
from deploy.hf.prepare import ROOT, prepare, release_databases


def test_image_absolute_links_stay_inside_the_image(tmp_path):
    (tmp_path / "usr/lib").mkdir(parents=True)
    (tmp_path / "usr/lib/loader").write_text("image loader")
    (tmp_path / "lib").symlink_to("/usr/lib")
    assert image_path(tmp_path, "/lib/loader") == tmp_path / "usr/lib/loader"
    (tmp_path / "escape").symlink_to("../../outside")
    with pytest.raises(ValueError):
        image_path(tmp_path, "/escape")


def test_incomplete_or_changed_checkpoints_block_space_preparation(tmp_path):
    results = tmp_path / "results/r2"
    results.mkdir(parents=True)
    summary = {
        "systems": {
            name: [{"checkpoint": 0, "n": 500, "complete": True}] for name in ("floor", "ceiling")
        }
    }
    (results / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="full-test"):
        release_databases(tmp_path, "r2")
    summary["systems"].update(
        {
            name: [{"checkpoint": 1.0, "n": 500, "complete": True}]
            for name in ("lore", "vector", "flat")
        }
    )
    (results / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="checkpoints"):
        release_databases(tmp_path, "r2")


def test_engine_does_not_inherit_model_or_hosting_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setenv("LORE_LLM_API_KEY", "offline-fixture")
    monkeypatch.setenv("SPACE_SIGNING_SECRET", "offline-signing-fixture")
    monkeypatch.setenv("HUGGING_FACE", "offline-hosting-fixture")
    monkeypatch.setenv("FACTORY_API_KEY", "offline-factory-fixture")
    monkeypatch.setenv("HF_TOKEN", "offline-hf-fixture")
    monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", "offline-hub-fixture")
    with monkeypatch.context() as patch:
        for key in (
            "HYDRA_TOKEN",
            "HYDRA_BOLT_URI",
            "HYDRA_HTTP_URL",
            "HYDRA_ADMIN_URL",
            "LORE_STATE_DIR",
            "LORE_BEHIND_CLOUDFLARE",
            "LORE_LLM_CONCURRENCY",
            "LORE_LLM_MIN_INTERVAL_S",
            "GRADIO_ANALYTICS_ENABLED",
            "HF_HUB_DISABLE_TELEMETRY",
        ):
            patch.setenv(key, "")
        env = configure(tmp_path)
        assert not {
            "LORE_LLM_API_KEY", "SPACE_SIGNING_SECRET", "HUGGING_FACE",
            "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "FACTORY_API_KEY",
        } & env.keys()
        assert os.environ["LORE_LLM_TRANSPORT"] == "factory"
        assert os.environ["LORE_LLM_MODEL"] == "minimax-m3.1-flash"
        assert os.environ["LORE_LLM_EFFORT"] == "medium"
        assert os.environ["LORE_LLM_MAX_TOKENS"] == "0"
        assert os.environ["LORE_RESULTS_RUN"] == "r4"
        assert os.environ["LORE_RUN"] == "r4"
        assert os.environ["FACTORY_DROID_AUTO_UPDATE_ENABLED"] == "false"
        assert os.environ["TMPDIR"] == str(tmp_path / "tmp")
        assert env["GRAPH_BOLT_ADDR"] == "127.0.0.1:7687"
        assert (tmp_path / "auth-token").stat().st_mode & 0o777 == 0o600


def test_finished_release_is_allowlisted_and_rejects_smoke_load(tmp_path):
    root = tmp_path / "repo"
    results = root / "results/r2"
    results.mkdir(parents=True)
    summary = {"model": "fixture", "effort": "medium", "systems": {}}
    for name in ("floor", "ceiling", "lore", "vector", "flat"):
        points = [0.25, 0.5, 1.0] if name in ("lore", "vector") else [1] if name == "flat" else [0]
        summary["systems"][name] = [{"checkpoint": cp, "n": 500, "complete": True} for cp in points]
    (results / "summary.json").write_text(json.dumps(summary))
    databases = [f"fixture{i}" for i in range(4)]
    suggestions = [
        {"question": f"q{i}", "hint": f"h{i}", "followup": f"f{i}"} for i in range(3)
    ]
    (results / "demo.json").write_text(json.dumps({
        "databases": [{"id": d, "suggestions": suggestions} for d in databases],
    }))
    (results / "demo_replays.json").write_text(
        json.dumps(
            [
                {
                    "db": db,
                    "a": f"s{i}",
                    "b": f"t{i}",
                    "passed": True,
                    "model": "fixture",
                    "effort": "medium",
                    "suggestion": suggestions[i],
                }
                for db in databases
                for i in range(3)
            ]
        )
    )
    (root / "seeds").mkdir()
    for db in databases:
        (root / "seeds" / f"{db}.json").write_text("{}")
    load = {
        "trained": False,
        "frozen": False,
        "llm_calls": 0,
        "levels": [{"concurrency": c, "requests": 1000, "error_count": 0} for c in (10, 50, 100)],
    }
    (results / "load.json").write_text(json.dumps(load))
    with pytest.raises(ValueError, match="unfrozen trained"):
        release_databases(root, "r2")
    load["trained"] = True
    (results / "load.json").write_text(json.dumps(load))
    assert release_databases(root, "r2") == databases
    bundle = tmp_path / "bundle"
    bird = bundle / "data/bird"
    bird.mkdir(parents=True)
    layout = {"databases": {db: f"{db}.sqlite" for db in databases}, "descriptions": {}}
    (bird / "paths.json").write_text(json.dumps(layout))
    (bird / "DATA_LICENSE.md").write_text("data notice")
    (bird / "minidev").mkdir()
    (bird / "minidev/sqlite.json").write_text("[]")
    (bird / "minidev/prompt_template.txt").write_text("template")
    for db in databases:
        (bird / f"{db}.sqlite").write_bytes(b"fixture data")
    (bundle / "data/private-owner-note").write_text("never publish")
    (results / "private-owner-note").write_text("never publish")
    (root / "lore").mkdir()
    (root / "lore/__init__.py").write_text("")
    (root / "web/dist").mkdir(parents=True)
    (root / "web/dist/index.html").write_text("<html></html>")
    for name in ("pyproject.toml", "LICENSE", "DATA_LICENSE.md", "README.md"):
        (root / name).write_text("public fixture")
    shutil.copytree(
        ROOT / "deploy/hf", root / "deploy/hf", ignore=shutil.ignore_patterns("__pycache__")
    )
    target = prepare(root, "r2", bundle, tmp_path / "output")
    assert not list(target.rglob("private-owner-note"))
    assert (target / "data/bird/fixture0.sqlite").read_bytes() == b"fixture data"
    assert (target / "data/bird/DATA_LICENSE.md").read_text() == "data notice"
    assert (target / "droid_runtime.py").exists()
    assert (target / "FACTORY_NOTICE.md").exists()
    requirements = set((target / "requirements.txt").read_text().splitlines())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert set(project["dependencies"] + project["optional-dependencies"]["factory"]) <= requirements
    assert "gradio==6.32.0" in requirements
    assert not any(line.startswith((".", "-e", "file:")) for line in requirements)


def test_droid_download_is_verified_atomic_and_cached(tmp_path, monkeypatch):
    payload, calls = b"offline CLI fixture", []
    monkeypatch.setattr(droid_runtime, "architecture", lambda: "x64")
    monkeypatch.setitem(droid_runtime.HASHES, "x64", hashlib.sha256(payload).hexdigest())

    def download(url, dest):
        calls.append(url)
        assert not dest.exists()
        dest.write_bytes(payload)

    def version(argv, **kwargs):
        assert argv[1:] == ["--version"]
        assert kwargs["timeout"] == 15
        assert kwargs["env"]["FACTORY_DROID_AUTO_UPDATE_ENABLED"] == "false"
        assert "FACTORY_API_KEY" not in kwargs["env"]
        return SimpleNamespace(stdout="1.12.1\n")

    monkeypatch.setattr(droid_runtime, "download", download)
    monkeypatch.setattr(droid_runtime.subprocess, "run", version)
    binary = droid_runtime.provision_droid(tmp_path)
    assert binary.stat().st_mode & 0o777 == 0o500
    assert (binary.parent / "FACTORY_NOTICE.md").exists()
    assert "version=1.12.1" in (binary.parent / "provenance.txt").read_text()
    assert droid_runtime.provision_droid(tmp_path) == binary
    assert calls == [droid_runtime.BASE_URL + "/x64/droid"]
    binary.chmod(0o600)
    binary.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="checksum"):
        droid_runtime.provision_droid(tmp_path)
    assert len(calls) == 1


@pytest.mark.parametrize("bad_hash", [True, False])
def test_unverified_or_wrong_version_droid_is_never_installed(tmp_path, monkeypatch, bad_hash):
    monkeypatch.setattr(droid_runtime, "architecture", lambda: "x64")
    monkeypatch.setattr(droid_runtime, "download", lambda url, dest: dest.write_bytes(b"fixture"))
    if not bad_hash:
        monkeypatch.setitem(droid_runtime.HASHES, "x64", hashlib.sha256(b"fixture").hexdigest())

    def version(*args, **kwargs):
        assert not bad_hash, "Unverified binary was executed"
        return SimpleNamespace(stdout="newer-unreviewed-version")

    monkeypatch.setattr(droid_runtime.subprocess, "run", version)
    with pytest.raises(RuntimeError, match="checksum|version"):
        droid_runtime.provision_droid(tmp_path)
    assert not (tmp_path / "droid/1.12.1/x64").exists()
    assert not list(tmp_path.rglob(".provision-*"))


@pytest.mark.asyncio
async def test_public_deadline_cancels_work_before_returning_safe_error():
    cleaned, sent = [], []

    async def slow(scope, receive, send):
        try:
            await asyncio.sleep(10)
        finally:
            cleaned.append(True)

    async def send(message):
        sent.append(message)

    await PublicDeadline(slow, seconds=0.01)(
        {"type": "http", "path": "/api/ask"}, None, send
    )
    assert cleaned == [True]
    assert sent[0]["status"] == 504
    assert b"timed out" in sent[1]["body"]


def test_failed_r3_preflight_cannot_be_prepared(tmp_path):
    with pytest.raises(ValueError, match="failed tool-policy preflight"):
        release_databases(tmp_path, "r3")


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [[], [False, False], [True]])
async def test_hosting_smoke_checks_actual_tool_catalog_and_cleans_up(tmp_path, monkeypatch, allowed):
    sdk = pytest.importorskip("droid_sdk")
    from deploy.hf.smoke_droid import verify_tool_policy

    monkeypatch.setenv("FACTORY_API_KEY", "offline-factory-fixture")
    monkeypatch.setenv("HF_TOKEN", "offline-hosting-fixture")
    (tmp_path / "tmp").mkdir()
    closed = []

    class Session:
        def __init__(self, **kwargs):
            config = kwargs["config"]
            assert set(config.disabled_tools) == {"Read"}
            assert set(config.restrict_tools) == {"Read"}
            assert not config.enabled_tools
            assert config.auto_reject_permission_requests
            assert kwargs["runtime"].env["HF_TOKEN"] == ""
            self.settings = SimpleNamespace(
                model=kwargs["model"], reasoning_effort=kwargs["reasoning_effort"]
            )

        async def open(self):
            pass

        async def list_tools(self):
            return [SimpleNamespace(allowed=value) for value in allowed]

        def stream(self, *args, **kwargs):
            raise AssertionError("Tool-policy smoke must never perform inference")

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(sdk, "Session", Session)
    if not allowed or any(allowed):
        with pytest.raises(RuntimeError, match="zero allowed tools"):
            await verify_tool_policy(tmp_path)
    else:
        result = await verify_tool_policy(tmp_path)
        assert result == {"protocol": "factory-sdk-v2", "catalog_tools": 2, "allowed_tools": 0}
    assert closed == [True]
    assert not list((tmp_path / "tmp").iterdir())
