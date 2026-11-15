"""All SDK interactions here are fake: these tests never contact Hugging Face."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.hf.prepare import ROOT, prepare
from deploy.hf.publish import (
    COLD_FLAGS,
    COLD_SOURCES,
    VARIABLES,
    Blocked,
    publish,
    scan_credentials,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "offline-hosting-credential")
    monkeypatch.setenv("FACTORY_API_KEY", "offline-factory-credential")
    root = tmp_path / "repo"
    root.mkdir()
    for name in ("pyproject.toml", "LICENSE", "DATA_LICENSE.md", "README.md"):
        (root / name).write_text("public fixture")
    shutil.copytree(ROOT / "deploy/hf", root / "deploy/hf", ignore=shutil.ignore_patterns("__pycache__"))
    hashes = {}
    for name in ("lore/factory_llm.py", "lore/providers.py", "lore/bench/factory.py", "lore/bench/run.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# frozen public fixture\n")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "web/dist").mkdir(parents=True)
    (root / "web/dist/index.html").write_text("<html>public</html>")
    results = root / "results/r4"
    runtime_hashes = {}
    for name in ("lore/connection_pool.py", "lore/bench/factory_runtime.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# public scheduling fixture\n")
        runtime_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(results / "runtime_configuration.json", {
        "driver_option": "max_connection_pool_size",
        "per_namespace_connection_pool_size": 4,
        "file_sha256": runtime_hashes,
    })
    (root / "lore/api.py").write_text("# public API fixture\n")
    systems = {}
    for name in ("floor", "ceiling", "lore", "vector", "flat"):
        checkpoints = [0.25, 0.5, 1] if name in ("lore", "vector") else [1] if name == "flat" else [0]
        systems[name] = [
            {"checkpoint": c, "n": 500, "complete": True, "correct": 250, "accuracy": 50}
            for c in checkpoints
        ]
    write_json(results / "summary.json", {
        "model": "minimax-m3.1-flash", "effort": "medium", "complete": True, "systems": systems,
    })
    (results / "per_db.md").write_text("All databases, including regressions")
    write_json(results / "demo_replay_round1.json", {"passed_per_db": {}, "usage_limitation": "fixture"})
    write_json(results / "learning_configuration.json", {
        "protocol": "factory-sdk-v2", "model": "minimax-m3.1-flash", "effort": "medium",
        "max_tokens_metadata_sentinel": 0, "sdk_version": "0.5.0", "droid_version": "1.12.1",
        "tools": [], "file_sha256": hashes,
    })
    databases, replays, seeds = [], [], {}
    bird = root / "data/bird"
    layout = {"databases": {}, "descriptions": {}}
    for index in range(4):
        db = f"db{index}"
        suggestions = [
            {"question": f"q{i}", "hint": f"h{i}", "followup": f"f{i}"} for i in range(3)
        ]
        databases.append({"id": db, "rules": 1, "suggestions": suggestions})
        replays.extend({
            "db": db, "a": f"s{i}", "b": f"t{i}", "passed": True,
            "model": "minimax-m3.1-flash", "effort": "medium", "suggestion": s,
        } for i, s in enumerate(suggestions))
        write_json(root / "seeds" / f"{db}.json", {
            "entities": [{"type": "Term"}],
            "relations": [{"type": "MEANS", "properties": {"origin": "s0"}}],
        })
        seeds[db] = {"entities": 1, "relations": 1}
        layout["databases"][db] = f"{db}.sqlite"
        layout["descriptions"][db] = f"{db}/database_description"
        desc = bird / db / "database_description"
        desc.mkdir(parents=True)
        (desc / "table.csv").write_text("column,description\nid,identifier\n")
        (bird / f"{db}.sqlite").write_bytes(b"fixture database")
    write_json(results / "demo.json", {"run": "r4", "databases": databases})
    write_json(results / "hosting_cold.json", {
        **{flag: True for flag in COLD_FLAGS},
        "docker_socket": False, "uid": 1000, "trained_databases": 4,
        "databases": [d["id"] for d in databases],
        "expected_and_restored_rules": {d["id"]: 1 for d in databases},
        "metered_model_calls": 0, "model_consuming_routes_called": 0, "public_ports": 0,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in COLD_SOURCES
        },
    })
    write_json(results / "demo_replays.json", replays)
    write_json(results / "seeds.json", {"run": "r4", "databases": seeds})
    write_json(results / "load.json", {
        "trained": True, "frozen": False, "llm_calls": 0,
        "per_namespace_connection_pool_size": 4,
        "levels": [{"concurrency": c, "requests": 1000, "error_count": 0} for c in (10, 50, 100)],
    })
    write_json(bird / "paths.json", layout)
    (bird / "DATA_LICENSE.md").write_text("data notice")
    write_json(bird / "minidev/sqlite.json", [])
    (bird / "minidev/prompt_template.txt").write_text("public template")
    package = prepare(root, "r4", root, tmp_path / "prepared")
    return root, package


class FakeApi:
    def __init__(self, *, endpoint, token):
        assert endpoint == "https://huggingface.co"
        assert token == "offline-hosting-credential"
        self.writes = []
        self.owner, self.exists, self.zero_count = "isHeSatoshi", False, 0
        self.writable = True
        self.failure = None

    def whoami(self):
        return {
            "name": self.owner, "type": "user",
            "auth": {"accessToken": {"role": "write" if self.writable else "read"}},
        }

    def repo_exists(self, **kwargs):
        return self.exists

    def list_spaces(self, **kwargs):
        return [SimpleNamespace(id=f"existing{i}") for i in range(self.zero_count)]

    def get_space_runtime(self, repo):
        return SimpleNamespace(hardware=None, requested_hardware="zero-a10g")

    def create_repo(self, **kwargs):
        self.writes.append(("create", kwargs))
        if self.failure == "create":
            raise RuntimeError("offline-hosting-credential offline-factory-credential")

    def create_commit(self, **kwargs):
        self.writes.append(("upload", kwargs))
        if self.failure == "upload":
            raise RuntimeError("offline-hosting-credential offline-factory-credential")
        self.uploaded = {op.path_in_repo: Path(op.path_or_fileobj).read_bytes() for op in kwargs["operations"]}


def invoke(release, api, execute=True):
    root, package = release
    return publish(package, "isHeSatoshi/lore", root=root, execute=execute, api_factory=lambda **kwargs: api)


@pytest.fixture
def api():
    return FakeApi(endpoint="https://huggingface.co", token="offline-hosting-credential")


def test_explicit_publish_creates_only_free_new_space_and_uploads_snapshot(release, api):
    assert invoke(release, api) == "Published https://huggingface.co/spaces/isHeSatoshi/lore"
    assert [name for name, _ in api.writes] == ["create", "upload"]
    create = api.writes[0][1]
    assert create["space_hardware"] == "zero-a10g"
    assert create["space_storage"] is None
    assert create["space_sdk"] == "gradio"
    assert create["private"] is False and create["exist_ok"] is False
    protected = {s["key"]: s["value"] for s in create["space_secrets"]}
    assert set(protected) == {"FACTORY_API_KEY", "SPACE_SIGNING_SECRET"}
    assert protected["FACTORY_API_KEY"] == "offline-factory-credential"
    assert len(protected["SPACE_SIGNING_SECRET"]) >= 48
    assert {s["key"]: s["value"] for s in create["space_variables"]} == VARIABLES
    assert "HF_TOKEN" not in str(create)
    assert "publisher-requirements.txt" not in api.uploaded and "publish.py" not in api.uploaded
    assert "results/r4/seeds.json" in api.uploaded
    assert "results/r4/per_db.md" in api.uploaded
    assert "results/r4/demo_replay_round1.json" in api.uploaded
    assert not any(b"offline-hosting-credential" in value or b"offline-factory-credential" in value for value in api.uploaded.values())


def test_default_is_read_only(release, api):
    assert "no remote writes" in invoke(release, api, execute=False)
    assert not api.writes


@pytest.mark.parametrize("location", [0, 1])
def test_cold_proof_pins_api_in_source_and_package_before_api_construction(release, location):
    (release[location] / "lore/api.py").write_text("# changed since cold validation\n")
    with pytest.raises(Blocked, match="cold-source-drift"):
        invoke(release, None)


@pytest.mark.parametrize("attribute,value", [
    ("owner", "another-owner"), ("exists", True), ("writable", False), ("zero_count", 2),
])
def test_access_or_capacity_failure_never_writes(release, api, attribute, value):
    setattr(api, attribute, value)
    with pytest.raises(Blocked):
        invoke(release, api)
    assert not api.writes


@pytest.mark.parametrize("filename", [
    "unknown.txt", ".env", ".git/config", "data/cache/private.sqlite",
    "data/bird/db0/database_description/unknown.txt",
])
def test_unknown_or_private_files_block_before_api_construction(release, filename):
    root, package = release
    path = package / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("never upload")
    with pytest.raises(Blocked):
        publish(package, "isHeSatoshi/lore", root=root, execute=True, api_factory=lambda **kwargs: pytest.fail("API reached"))


def test_symlinks_and_known_credential_bytes_block_before_api(release):
    root, package = release
    (package / "private-link").symlink_to(root / "README.md")
    with pytest.raises(Blocked, match="symlink"):
        invoke(release, None)
    (package / "private-link").unlink()
    (package / "README.md").write_text("offline-hosting-credential")
    with pytest.raises(Blocked, match="credential-in-package"):
        invoke(release, None)


@pytest.mark.parametrize("filename,mutate", [
    ("summary.json", lambda d: d.update(complete=False)),
    ("summary.json", lambda d: d["systems"]["lore"][0].update(n=499)),
    ("summary.json", lambda d: d["systems"]["floor"][0].update(accuracy=99)),
    ("summary.json", lambda d: d.update(model="different-model")),
    ("learning_configuration.json", lambda d: d.update(protocol="factory-sdk-v1")),
    ("runtime_configuration.json", lambda d: d.update(per_namespace_connection_pool_size=100)),
    ("runtime_configuration.json", lambda d: d.update(file_sha256={})),
    ("hosting_cold.json", lambda d: d.update(passed=False)),
    ("hosting_cold.json", lambda d: d.update(read_only_root=False)),
    ("hosting_cold.json", lambda d: d.update(trained_databases=0)),
    ("hosting_cold.json", lambda d: d.update(uid=0)),
    ("hosting_cold.json", lambda d: d.update(metered_model_calls=1)),
    ("hosting_cold.json", lambda d: d.update(engine_restart_restored_identical_graphs=False)),
    ("hosting_cold.json", lambda d: d.update(expected_and_restored_rules={})),
    ("hosting_cold.json", lambda d: d.update(source_sha256={})),
    ("seeds.json", lambda d: d.update(run="r2")),
    ("demo.json", lambda d: d["databases"][0].update(suggestions=[])),
    ("demo_replays.json", lambda d: d[0].update(passed=False)),
    ("load.json", lambda d: d.update(trained=False)),
    ("load.json", lambda d: d.update(llm_calls=1)),
    ("load.json", lambda d: d.update(per_namespace_connection_pool_size=100)),
    ("load.json", lambda d: d["levels"][0].update(error_count=1)),
    ("load.json", lambda d: d["levels"].pop()),
])
def test_every_measurement_gate_precedes_api_construction(release, filename, mutate):
    root, _ = release
    path = root / "results/r4" / filename
    data = json.loads(path.read_text())
    mutate(data)
    write_json(path, data)
    with pytest.raises(Blocked):
        invoke(release, None)


@pytest.mark.parametrize("phase", ["create", "upload"])
def test_sdk_failures_are_sanitized_and_never_fall_back(release, api, phase):
    api.failure = phase
    with pytest.raises(Blocked) as caught:
        invoke(release, api)
    assert "offline-" not in str(caught.value)
    assert len(api.writes) == (1 if phase == "create" else 2)
    assert "no paid fallback" in str(caught.value)


def test_credential_scan_detects_chunk_boundary(tmp_path):
    secret = "offline-boundary-credential"
    (tmp_path / "public.bin").write_bytes(b"x" * (1024 * 1024 - 3) + secret.encode())
    with pytest.raises(Blocked, match="credential-in-package"):
        scan_credentials(tmp_path, [secret])


@pytest.mark.parametrize("target", ["protocol", "runtime", "database", "heldout-seed", "missing-seed"])
def test_source_and_seed_integrity_fail_closed(release, api, target):
    root, package = release
    if target == "protocol":
        (root / "lore/providers.py").write_text("# unmeasured source change")
    elif target == "runtime":
        (root / "lore/connection_pool.py").write_text("# unrecorded runtime change")
    elif target == "database":
        (package / "data/bird/db0.sqlite").write_bytes(b"unreviewed database")
    elif target == "missing-seed":
        (root / "seeds/db0.json").unlink()
    else:
        path = root / "seeds/db0.json"
        seed = json.loads(path.read_text())
        seed["entities"][0] = {"type": "Example", "properties": {"key": "t1"}}
        write_json(path, seed)
    with pytest.raises(Blocked):
        invoke(release, api)
    assert not api.writes


def test_upload_uses_private_validated_snapshot_not_later_package_changes(release, api):
    _, package = release
    expected = (package / "README.md").read_bytes()
    original_create = api.create_repo

    def create_and_modify_original(**kwargs):
        original_create(**kwargs)
        (package / "README.md").write_text("offline-hosting-credential")

    api.create_repo = create_and_modify_original
    invoke(release, api)
    assert api.uploaded["README.md"] == expected


@pytest.mark.parametrize("scope_owner", ["isHeSatoshi", "another-owner"])
def test_fine_grained_token_must_write_correct_owner(release, api, scope_owner):
    api.whoami = lambda: {
        "name": "isHeSatoshi", "type": "user",
        "auth": {"accessToken": {
            "role": "fineGrained",
            "fineGrained": {"scoped": [{
                "entity": {"name": scope_owner, "type": "user"}, "permissions": ["repo.write"],
            }]},
        }},
    }
    if scope_owner == "isHeSatoshi":
        assert "no remote writes" in invoke(release, api, execute=False)
    else:
        with pytest.raises(Blocked, match="token-write-scope"):
            invoke(release, api)
    assert not api.writes


def test_free_creation_rejection_reports_only_safe_http_code(release, api):
    def rejected(**kwargs):
        error = RuntimeError("offline-hosting-credential")
        error.response = SimpleNamespace(status_code=403)
        raise error

    api.create_repo = rejected
    with pytest.raises(Blocked, match="free-create HTTP 403") as caught:
        invoke(release, api)
    assert "offline-" not in str(caught.value)
    assert not api.writes
