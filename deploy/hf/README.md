# Free Hugging Face hosting

Status: **local compatibility passed, not deployed**. This is separate from
the Docker/VM deployment. No paid plan or hardware is authorized.

## Access gate

Current [Spaces rules](https://huggingface.co/docs/hub/spaces-overview) require
PRO/Team for new Docker compute Spaces, even when CPU Basic costs zero hourly.
The [free Gradio/ZeroGPU exception](https://huggingface.co/docs/hub/spaces-zerogpu)
allows up to two Spaces for eligible verified personal accounts older than
30 days.

Authenticated read-only recheck: owner **`isHeSatoshi`**, personal account,
not PRO, older than 30 days. The fine-grained token has owner-scoped
`repo.write` and repository-read permissions. All 13 owned Space runtimes
were readable; none has current or requested ZeroGPU hardware, so the
documented two free ZeroGPU slots appear unused. Email verification and
good-standing eligibility are not exposed by the account metadata checked;
actual creation acceptance remains unproven. The candidate
`isHeSatoshi/lore` returned 404 and is not currently allocated.
[`evidence/hf_access.json`](evidence/hf_access.json) contains only sanitized
access/capacity findings, not the token, raw account metadata or PII.

**Only after all r4 measurement/seeds/replay/load/package gates pass**, use the
official Hub SDK with the token held only in memory:

```python
api.create_repo(
    repo_id="isHeSatoshi/lore",
    repo_type="space",
    space_sdk="gradio",
    space_hardware=SpaceHardware.ZERO_A10G,  # official value: "zero-a10g"
    private=False,
    space_storage=None,
    exist_ok=False,
)
```

Here `api` is an authenticated `HfApi` instance and `SpaceHardware` comes from
`huggingface_hub`. Explicit ZeroGPU selection is essential: do not accept the
default CPU Basic creation path. No paid storage or hardware is requested.
No creation, upload, billing mutation or existing-Space restart was performed.
Existing paused upgraded-hardware configurations were left untouched; do not
resume/reuse them. Keep the deployment token out of app runtime Secrets, chat,
Git and argv. Do not restart the benchmark computer.

Do not create CPU Basic by default, upgrade the account, accept paid hardware,
or switch providers. If free creation is rejected, stop and report the reason.

## Runtime

- Gradio 6.32.0, Python 3.12; React/FastAPI stays at `/`, Gradio at `/hosting`.
- `packages.txt` uses the documented
  [Debian dependency mechanism](https://huggingface.co/docs/hub/spaces-dependencies).
- `skopeo` and rootless `umoci` download and unpack the pinned HydraDB 0.4.0
  image. They do not require a Docker daemon or privileged container.
- The binary hash is checked. The image's own ELF loader avoids a newer-glibc
  dependency on the host. Original upstream filesystem/notices are retained.
- Bolt, HTTP and admin bind only to loopback. Only the app uses port 7860.
  The wrapper supervises the engine and cleans it up on shutdown.
- State defaults to `~/.cache/lore-space`, which must be writable and executable.
  `LORE_HOST_STATE` can override it. Do not use a `noexec` filesystem.
- `droid_runtime.py` downloads the reviewed official CLI **1.12.1** into
  `<state>/droid/1.12.1/<architecture>/droid`, checks its pinned SHA256 before
  execution and checks `--version` on both install and cache reuse. Linux x64
  and x64-baseline have separate pins; no Node/npm, shell installer or global
  executable replacement is used. The cache retains provenance and
  [`FACTORY_NOTICE.md`](FACTORY_NOTICE.md); the binary is unchanged.
- Runtime Secrets need `FACTORY_API_KEY` and a strong
  `SPACE_SIGNING_SECRET`, plus the measured model/effort configuration.
  Do not upload `.env`, the deployment token, benchmark tokens or caches.
  Free hosting does not make model calls free.
- Before Lore imports, the launcher fixes `LORE_LLM_TRANSPORT=factory`,
  `LORE_LLM_MODEL=minimax-m3.1-flash`, `LORE_LLM_EFFORT=medium`,
  `LORE_LLM_MAX_TOKENS=0` (SDK-managed limit), `LORE_RUN=r4` and
  `LORE_RESULTS_RUN=r4`. It checks SDK/Gradio versions, prepends the private
  CLI directory to `PATH`, and disables CLI auto-updates with the documented
  `FACTORY_DROID_AUTO_UPDATE_ENABLED=false`.
- Model-facing public requests have a 60-second cancellation deadline.
  Concurrency is capped at two model calls with a two-second start interval.
  FactoryLLM v2 uses `disabled_tools={"Read"}`, `restrict_tools={"Read"}` and
  `enabled_tools=()`, then verifies every discovered tool has `allowed=False`
  before each completion. An empty restriction alone does **not** disable tools.
  It creates/deletes an empty HOME/cwd for
  each completion under `<state>/tmp`; no login state is uploaded. Cancellation
  reaches its session cleanup. Hydra never inherits the Factory credential.
- Gradio analytics, MCP and monitoring are disabled. Private state/data paths
  are blocked from Gradio's file route. Caller-provided proxy headers are not
  trusted; the hosting proxy can make visitors share the stricter hourly limit.
- Free storage is ephemeral. Seeds restore on startup; visitor graphs,
  answer caches and counters can reset on replacement. No durable storage is
  claimed or purchased.

## Factory SDK release gate

The new measured release is **r4**, using the official Factory Droid SDK,
model **`minimax-m3.1-flash`**, reasoning effort **`medium`**, consistently
across comparisons, teaching replays, demo and app. Do not relabel or overwrite
the frozen r2 results, silently use the direct MiniMax transport, or use `auto`.
The protocol is **factory-sdk-v2**, with a separate cache. r3 is retained as a
failed tool-policy preflight, not a valid comparison or release. The isolated
v2 tool-policy smoke and the completed four-database local trained cold start
passed. Actual HF creation, public teaching and hosted restoration remain unproven.

### Seeded local cold-start proof

[`hosting_cold.json`](../../results/r4/hosting_cold.json) records the real launcher,
not a fixture: non-root uid 1002, read-only root, no Docker socket or published
port, and zero model-consuming routes or metered model calls. Fresh setup
(including pinned binary provisioning and seed import) took **41.65 seconds**;
restart took **5.42 seconds**. All **345 MEANS rules** across the measured four
databases were restored, and exact node/edge records survived restart. Trained
certification returned 403 without modifying the graph; private Gradio file
requests were denied and the React JavaScript and Gradio mount were served.
These are local observations, not an HF startup-time guarantee.

The first two check-harness attempts stopped before engine startup because of
private mount uid mismatch and a missing copied attribution notice. Both
records remain under `results/smoke/hf_seeded_cold.*_failure.json`. Neither
required an application change.

After the normal data setup and frontend build, reproduce from the repository
root as a non-root user:

```sh
docker build --build-arg LORE_LLM_TRANSPORT=factory \
  -f deploy/Dockerfile.app -t lore:factory-release .
docker build --build-arg LORE_CHECK_UID="$(id -u)" \
  -f deploy/hf/Dockerfile.check -t lore:hf-check .
state="$(mktemp -d /tmp/lore-hf-check-XXXXXX)"
docker run --rm --read-only --cap-drop ALL \
  --security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "$state:/state:rw" -v "$PWD/data:/app/data:ro" \
  -v "$PWD/results/r4:/app/results/r4:ro" lore:hf-check
```

The validator supplies a dummy model credential; no real key is needed.
`publish.py` now refuses publication when this proof is missing, its checks
fail, its four rule counts differ, or its application/launcher/notice hashes
do not match the source and reconstructed package. It still requires every
benchmark, replay and trained-load gate separately.

The official [Python SDK](https://docs.factory.com/sdk/python.md), found via
[`llms.txt`](https://docs.factory.ai/llms.txt), requires Python 3.10+, the
`droid-sdk` Python package, **a separate local `droid` executable**, and an
authenticated CLI or `FACTORY_API_KEY`. Python 3.12 already meets the version
requirement, but installing the SDK alone is insufficient. Space requirements
now install `.[factory]` (which pins **droid-sdk==0.5.0**) and
**gradio==6.32.0**. The CLI's
[documented direct-download contract and auto-update control](https://docs.factory.com/droid-cli/cli-reference)
and [official installer](https://app.factory.ai/cli) were reviewed without
executing the installer. The x64 hash also matches the trusted local 1.12.1
executable; both pins match the official public SHA256 companions:

```text
x64          ffd1196837f680327258094bc12dc993ff9232036c964bf8354ffb7ed1fdcf00
x64-baseline 0b066177663e2d792a7fe13c04f2ad8b9e8df20c474d29e7543cadfa887b30f7
```

Before publication:
- Store `FACTORY_API_KEY` only as a protected runtime Secret, never a public
  variable or uploaded CLI login/settings directory. Keep SDK sessions,
  logs and CLI private state outside served paths and the release folder;
  the SDK saves resumable sessions. The Hydra child environment is allowlisted
  and must continue to exclude both Factory and hosting credentials.
- With the release credential, use documented `list_models()` to confirm
  `minimax-m3.1-flash` supports `medium`; fail closed if unavailable. Verify
  outbound HTTPS works on the actual Space (HF permits ports 80/443/8080).
- Recheck child cleanup, finite timeouts, disabled agent tools, private file
  blocking, budgets and bounded concurrency in a non-root trained cold start.
  SDK runtime environment entries extend the parent's environment; do not
  assume they isolate credentials. Do not copy this computer's login state.

Hugging Face's [dependency mechanism](https://huggingface.co/docs/hub/spaces-dependencies)
installs Python requirements and Debian packages; it does not promise a Droid
binary. `prepare.py` now explicitly allowlists the selected helper and notice.
No paid compute, GPU invocation, tunnel, Docker socket or privileged install
is needed or authorized.

## Prepare after the measurement gates

Finish full `r4` comparisons, seeds, teaching replays and trained load first.
Build the frontend and create the existing portable data bundle:

```sh
.venv/bin/python -m lore.bench.demo --run r4 --bundle /tmp/lore-demo-data
.venv/bin/python deploy/hf/prepare.py --run r4 \
  --data-bundle /tmp/lore-demo-data/<printed-bundle-directory> \
  --out /tmp/lore-hf-release
```

The command prints a new local folder, not a URL. It performs no publication.
It refuses incomplete benchmark/replay/load artifacts and copies selected
data/results, not the working directory or Git history.
The preparation CLI defaults to `r4`; the launcher fixes the runtime settings
listed above. Verify them against the release summary; preparation does not
configure remote Secrets or prove transport/model consistency by itself.

After final source, secret and trained-cold-start checks, use the authorized
Hub client to verify identity and free eligibility. Create only a Gradio Space
on free ZeroGPU hardware, add protected runtime Secrets, and upload only the
reviewed folder. Never pass any of the hosting-token aliases to the app as
runtime Secrets.
Check the actual public health, UI, trained graphs, sandbox teaching/reuse,
budget/error states and restart restoration before claiming a live demo.

## Gated release publisher

`publish.py` defaults to **validation plus read-only access checks**. It does
not create/upload unless `--publish` is explicitly supplied. Install the
separate pinned publisher requirements; no app/root dependency change is needed:

```sh
.venv/bin/pip install -r deploy/hf/publisher-requirements.txt
.venv/bin/python deploy/hf/publish.py --repo isHeSatoshi/lore \
  --package /tmp/lore-hf-release/<prepared-folder>
# Only after every gate and final trained cold-start/source review:
.venv/bin/python deploy/hf/publish.py --repo isHeSatoshi/lore \
  --package /tmp/lore-hf-release/<prepared-folder> --publish
```

No secret belongs in argv. The helper reads environment/private repository
`.env` (environment wins), snapshots the package privately, and validates both
the current source results and the snapshot **before any remote write**:

- All full 500-question systems/checkpoints, consistent accuracy counts,
  complete r4 summary, exact model/effort and frozen v2 source hashes.
- r4 `seeds.json` provenance/counts, nonempty seed payloads without held-out
  examples/rules, three distinct passed replay pairs per database, three
  replay-backed demo suggestions per database, and trained unfrozen zero-call
  10/50/100-concurrency load reports with 1000 requests and zero errors each.
- Exact reconstruction through `prepare.py`'s allowlist, byte-for-byte current
  source/results/frontend/seeds and original selected data/descriptions.
  Symlinks, dotfiles, Git, history, caches, unknown/missing files and stale
  packages are rejected. Known credential byte values are scanned in every
  package file (including binary data and chunk boundaries) and path.

The helper then rechecks authenticated owner `isHeSatoshi`, write scope,
absence of the target Space, and apparent free ZeroGPU capacity. It refuses
**every** existing target, including one left by an interrupted previous run.
Creation uses only Gradio, `zero-a10g`, no paid storage, `exist_ok=False`, and
sets protected `FACTORY_API_KEY` plus a fresh generated `SPACE_SIGNING_SECRET`.
Only nonsecret fixed r4/model/effort/transport/max-token settings are variables;
the HF deployment token is never an app Secret or uploaded file.

The upload is a single SDK commit containing only the validated snapshot's
explicit file list, with two transfer threads. Diagnostics are sanitized and
SDK debug/progress output is disabled. Free-creation rejection stops without
fallback, upgrades, resuming another Space, deletion or automatic recovery.
If upload fails after creation, a new configured empty Space may remain:
inspect it before any separately authorized recovery. A successful upload
reports the public repository URL, **not** a healthy/live application claim.
No real remote publication has been performed while developing this helper;
publisher tests use fake SDK APIs exclusively.

## Local evidence and limits

[`evidence/droid_native_v2.json`](evidence/droid_native_v2.json) records a fresh
non-root/read-only-source check of the actual explicit v2 policy:
**42 discovered tools, zero allowed**, CLI 1.12.1 and SDK 0.5.0. It made no
model inference, started no Hydra, and reverified the private CLI cache.
`smoke_droid.py --check-tools` performs this bounded check; `--completion`
also runs the policy check before exercising the frozen v2 provider.

[`evidence/droid_native.json`](evidence/droid_native.json) is explicitly marked
historical and **not valid tool-policy/r4 evidence**. It records installation
from the official pinned artifact, hash/version verification, cache reuse, and
one metered exact-model Factory completion in a non-root Linux user/mount
namespace with the source tree bound read-only and private executable state.
It used a separate venv installed from the Space requirements and no Docker
socket. Download/verification took 17.20s; the tiny SQL completion took 4.18s
and child peak RSS was 263528 KiB. Those old completion numbers do not validate
the corrected v2 protocol. The completion's private HOME was removed.
The x64-baseline checksum is pinned but that binary has not been executed here.
Cached hash/version verification also passed in a separate network namespace
with no external networking and zero model calls.
`smoke_droid.py` is a reusable local check, not a published runtime entrypoint.
No Hydra was started or restarted, no ports were published, and the existing
`/usr/local/bin/droid` remained unchanged. This is not a trained-app or hosted
cold-start claim.

[`results/smoke/hf_native.json`](../../results/smoke/hf_native.json) records a
tiny graph's insert/read and engine-child restart, lifecycle preservation,
and the actual unseeded launcher in a non-root isolated container. The initial
copied-binary test had networking disabled; the pinned-image installer test
needed outbound public-registry access. Neither made model calls or published
ports. These checks do **not** establish account eligibility, a trained cold
start, hosted latency, persistent storage or public uptime.
