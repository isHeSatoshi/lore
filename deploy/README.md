# Deployment

Nothing here is permission to expose this machine or publish the repository.
Obtain the owner's hosting approval first.

The current approved release uses only [free Hugging Face hosting](hf/README.md).
The VM and tunnel sections below are reference instructions, not authorization
to create paid infrastructure or expose the benchmark machine.

## Reference VM, not approved for the current release

Use a Linux VM with Docker/Compose already installed, SSH access, a domain
pointing at the VM, and inbound HTTP/HTTPS permitted. The script does not use
`sudo`, install Docker, or change firewall rules.

After the full benchmark and demo replay validation finish:

```sh
.venv/bin/python -m lore.bench.demo --run r2
.venv/bin/python -m lore.bench.replay_demo --run r2
.venv/bin/python -m lore.seeds export --run r2 --out seeds/
.venv/bin/python -m lore.bench.demo --run r2 --bundle /absolute/path/to/bundle-parent
```

Copy the code, generated results, seeds, private `.env`, and the bundle's
`data/` directory to the approved VM. Keep credentials out of source control
and logs. Do not copy unrelated local data or model caches.

On that VM, from the repository root:

```sh
sh deploy/deploy.sh r2 your-approved-host.example
```

The app image builds the frontend and installs Python without embedding or
benchmark extras. When `LORE_LLM_TRANSPORT=factory`, Compose also selects the
pinned SDK/CLI image layer. Set the matching model to `minimax-m3.1-flash`,
effort to `medium`, and max tokens to `0` (SDK-managed); keep `FACTORY_API_KEY`
private. Raw MiniMax remains the default for historical setups.
The image runs as a non-root user, with a read-only root filesystem
and read-only SQLite data. Mutable app/cache/rate-limit state lives in its own
volume. Caddy terminates TLS and overwrites the forwarded client address.

The app binds only to loopback on the host. Only Caddy should be public.
Do not expose the Docker network's app port directly: production Uvicorn trusts
forwarded headers because Caddy is the intended entry point.

The deployment script changes HydraDB's advertised Bolt address to
`hydradb:7687` for container-to-container connections. **Do not run it against
the development stack while benchmarks are running.**

Validate `/healthz`, database selection, trained read-only mode, a complete
sandbox correction/reuse/certification/reset flow, and the proof page from a
different network before sharing the URL.

## Temporary tunnel

A public tunnel also requires explicit owner approval and keeps this machine
responsible for uptime. No tunnel is started by these instructions or scripts.
When using Cloudflare, bind the origin to loopback and set
`LORE_BEHIND_CLOUDFLARE=1`; this requires the tunnel-provided client IP header
for model-consuming routes. Never enable that trust mode on a directly public
origin, where callers could forge the header.

## Current validation boundary

Image build, non-root packaging checks and Caddy configuration validation have
passed locally. Public TLS, VM networking, external-browser operation and
uptime are unverified until an approved deployment exists.
