import json
import shutil

import pytest

from deploy.hf.app import configure, image_path
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
    monkeypatch.setenv("LORE_LLM_API_KEY", "offline-fixture")
    monkeypatch.setenv("SPACE_SIGNING_SECRET", "offline-signing-fixture")
    monkeypatch.setenv("HUGGING_FACE", "offline-hosting-fixture")
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
        assert not {"LORE_LLM_API_KEY", "SPACE_SIGNING_SECRET", "HUGGING_FACE"} & env.keys()
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
    (results / "demo.json").write_text(json.dumps({"databases": [{"id": d} for d in databases]}))
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
