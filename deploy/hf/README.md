# Free Hugging Face hosting

Status: **local compatibility passed, not deployed**. This is separate from
the Docker/VM deployment. No paid plan or hardware is authorized.

## Access gate

Current [Spaces rules](https://huggingface.co/docs/hub/spaces-overview) require
PRO/Team for new Docker compute Spaces, even when CPU Basic costs zero hourly.
The [free Gradio/ZeroGPU exception](https://huggingface.co/docs/hub/spaces-zerogpu)
allows up to two Spaces for eligible verified personal accounts older than
30 days. The owner's account eligibility is not yet verified.

`HUGGING_FACE` is not available in this running computer. Keep it out of chat
and Git. A protected private `.env` can make it available without restarting
the computer and killing the benchmark. Saved-secret changes alone do not
refresh a running computer.

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
- Runtime Secrets need the existing `LORE_LLM_API_KEY` and a strong random
  `SPACE_SIGNING_SECRET`, plus the measured model/effort configuration.
  Do not upload `.env`, the deployment token, benchmark tokens or caches.
  Model calls still consume the owner's MiniMax plan.
- Gradio analytics, MCP and monitoring are disabled. Private state/data paths
  are blocked from Gradio's file route. Caller-provided proxy headers are not
  trusted; the hosting proxy can make visitors share the stricter hourly limit.
- Free storage is ephemeral. Seeds restore on startup; visitor graphs,
  answer caches and counters can reset on replacement. No durable storage is
  claimed or purchased.

## Prepare after the measurement gates

Finish full `r2` comparisons, seeds, teaching replays and trained load first.
Build the frontend and create the existing portable data bundle:

```sh
.venv/bin/python -m lore.bench.demo --run r2 --bundle /tmp/lore-demo-data
.venv/bin/python deploy/hf/prepare.py --run r2 \
  --data-bundle /tmp/lore-demo-data/<printed-bundle-directory> \
  --out /tmp/lore-hf-release
```

The command prints a new local folder, not a URL. It performs no publication.
It refuses incomplete benchmark/replay/load artifacts and copies selected
data/results, not the working directory or Git history.

After final source, secret and trained-cold-start checks, use the authorized
Hub client to verify identity and free eligibility. Create only a Gradio Space
on free ZeroGPU hardware, add protected runtime Secrets, and upload only the
reviewed folder. Never pass `HUGGING_FACE` to the app as a runtime secret.
Check the actual public health, UI, trained graphs, sandbox teaching/reuse,
budget/error states and restart restoration before claiming a live demo.

## Local evidence and limits

[`results/smoke/hf_native.json`](../../results/smoke/hf_native.json) records a
tiny graph's insert/read and engine-child restart, lifecycle preservation,
and the actual unseeded launcher in a non-root isolated container. The initial
copied-binary test had networking disabled; the pinned-image installer test
needed outbound public-registry access. Neither made model calls or published
ports. These checks do **not** establish account eligibility, a trained cold
start, hosted latency, persistent storage or public uptime.
