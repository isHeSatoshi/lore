"""Gradio-SDK launcher. HydraDB remains a private, loopback-only child process."""

import asyncio
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

try:  # Uploaded release is flat; repository imports use the namespace package.
    from .droid_runtime import SDK_VERSION, provision_droid
except ImportError:
    from droid_runtime import SDK_VERSION, provision_droid

IMAGE = "ghcr.io/hydra-db/hydradb@sha256:ab71d651fefee13ebb23eb56d72316065bdca563ff7587442e07be663f2bf880"
BINARY_SHA256 = "821533e10c13228809ca62e16cc6f9c791f2c94a3a7f155394c002080a6cc979"


async def hosting_redirect():
    from starlette.responses import RedirectResponse

    return RedirectResponse("/hosting/", status_code=307)


def hosting_root():
    """Use HF's server-owned hostname, never caller-supplied proxy headers."""
    host = os.getenv("SPACE_HOST")
    if not host:
        return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.hf\.space", host):
        raise RuntimeError("Space hostname is invalid")
    return f"https://{host}/hosting"


def image_path(root, name):
    """Resolve image symlinks within the image, never against the host root."""
    root = Path(root)
    parts = name.lstrip("/").split("/")
    resolved = []
    for _ in range(100):
        if not parts:
            return root.joinpath(*resolved)
        part, *parts = parts
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                raise ValueError("Image path escapes its root")
            resolved.pop()
            continue
        path = root.joinpath(*resolved, part)
        if path.is_symlink():
            target = os.readlink(path)
            if target.startswith("/"):
                resolved = []
            parts = target.split("/") + parts
        else:
            resolved.append(part)
    raise ValueError("Too many image symlinks")


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def engine_files(state):
    if platform.machine() not in ("x86_64", "AMD64"):
        raise RuntimeError("This pinned engine requires x86_64")
    target = state / "engine"
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix="engine-build-", dir=state) as temporary:
            temporary = Path(temporary)
            subprocess.run(
                [
                    "skopeo",
                    "copy",
                    "--override-os",
                    "linux",
                    "--override-arch",
                    "amd64",
                    "docker://" + IMAGE,
                    "oci:" + str(temporary / "oci") + ":hydra",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=600,
            )
            subprocess.run(
                [
                    "umoci",
                    "unpack",
                    "--rootless",
                    "--image",
                    str(temporary / "oci") + ":hydra",
                    str(temporary / "bundle"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
            )
            (temporary / "bundle/image.json").write_text(json.dumps({"image": IMAGE}))
            (temporary / "bundle").rename(target)
    if json.loads((target / "image.json").read_text())["image"] != IMAGE:
        raise RuntimeError("Engine cache provenance differs")
    root = target / "rootfs"
    binary = image_path(root, "/usr/local/bin/graph-node")
    if file_hash(binary) != BINARY_SHA256:
        raise RuntimeError("Engine binary checksum differs")
    return (
        image_path(root, "/lib64/ld-linux-x86-64.so.2"),
        image_path(root, "/usr/lib/x86_64-linux-gnu"),
        binary,
    )


def configure(state):
    signing = os.getenv("SPACE_SIGNING_SECRET", "")
    token = os.getenv("HYDRA_TOKEN") or (
        hashlib.sha256((signing + ":lore-hydra").encode()).hexdigest()
        if signing
        else secrets.token_urlsafe(32)
    )
    auth = state / "auth-token"
    auth.write_text(token)
    auth.chmod(0o600)
    for directory in ("store", "cache", "app", "tmp"):
        (state / directory).mkdir(exist_ok=True)
    os.environ.update(
        HYDRA_TOKEN=token,
        HYDRA_BOLT_URI="bolt://127.0.0.1:7687",
        HYDRA_HTTP_URL="http://127.0.0.1:8443",
        HYDRA_ADMIN_URL="http://127.0.0.1:9090",
        LORE_STATE_DIR=str(state / "app"),
        TMPDIR=str(state / "tmp"),
        LORE_LLM_TRANSPORT="factory",
        LORE_LLM_MODEL="minimax-m3.1-flash",
        LORE_LLM_EFFORT="medium",
        LORE_LLM_MAX_TOKENS="0",
        LORE_RUN="r4",
        LORE_RESULTS_RUN="r4",
        FACTORY_DROID_AUTO_UPDATE_ENABLED="false",
        LORE_BEHIND_CLOUDFLARE="0",
        LORE_LLM_CONCURRENCY="2",
        LORE_LLM_MIN_INTERVAL_S="2",
        GRADIO_ANALYTICS_ENABLED="False",
        HF_HUB_DISABLE_TELEMETRY="1",
    )
    return {
        **{key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ},
        "CLOUD_PROVIDER": "local",
        "LOCAL_PATH": str(state / "store"),
        "GRAPH_NAMESPACE": "local",
        "GRAPH_ID": "default",
        "GRAPH_CELL_ID": "cell-0",
        "GRAPH_CELLS": "cell-0",
        "GRAPH_DATA_PATH": "data",
        "GRAPH_ALLOW_PLAINTEXT": "true",
        "GRAPH_AUTH_TOKEN_FILE": str(auth),
        "GRAPH_DATA_CACHE_BYTES": "67108864",
        "GRAPH_DATA_CACHE_DIR": str(state / "cache"),
        "GRAPH_NODE_ID": "node-0",
        "GRAPH_BOLT_ADDR": "127.0.0.1:7687",
        "GRAPH_ADVERTISED_BOLT_ADDR": "127.0.0.1:7687",
        "GRAPH_BOLT_NODE_ADDRESSES": "node-0=127.0.0.1:7687",
        "GRAPH_HTTP_ADDR": "127.0.0.1:8443",
        "GRAPH_ADMIN_ADDR": "127.0.0.1:9090",
        "RUST_MIN_STACK": "33554432",
        "RUST_LOG": "error",
        "OMP_NUM_THREADS": "2",
    }


class SpaceOrigin:
    """Restore HF's known HTTPS origin without trusting forwarded headers or IPs."""

    def __init__(self, app):
        self.app = app
        root = hosting_root()
        self.host = urlsplit(root).netloc if root else None

    async def __call__(self, scope, receive, send):
        if self.host and scope["type"] in ("http", "websocket"):
            scope = {
                **scope,
                "scheme": "https" if scope["type"] == "http" else "wss",
                "server": (self.host, 443),
                "headers": [
                    (name, value) for name, value in scope["headers"]
                    if name.lower() not in (b"host", b"forwarded")
                    and not name.lower().startswith(b"x-forwarded-")
                ] + [(b"host", self.host.encode("ascii"))],
            }
        await self.app(scope, receive, send)


class PublicDeadline:
    """Bound model-facing requests; cancellation reaches SDK session cleanup."""

    def __init__(self, app, seconds=60):
        self.app, self.seconds = app, seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in ("/api/ask", "/api/feedback"):
            return await self.app(scope, receive, send)
        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with asyncio.timeout(self.seconds):
                await self.app(scope, receive, tracked_send)
        except TimeoutError:
            if not started:
                from starlette.responses import JSONResponse

                await JSONResponse(
                    {"detail": "The model request timed out. Please retry shortly."}, status_code=504
                )(scope, receive, send)


async def ready(process):
    async with asyncio.timeout(60):
        while process.returncode is None:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", 7687)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.1)
    raise RuntimeError("HydraDB exited before readiness")


async def main():
    os.umask(0o077)
    state = Path(os.getenv("LORE_HOST_STATE", str(Path.home() / ".cache/lore-space")))
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = configure(state)
    if version("droid-sdk") != SDK_VERSION or version("gradio") != "6.32.0":
        raise RuntimeError("Space runtime dependency versions differ")
    if not os.getenv("FACTORY_API_KEY"):
        raise RuntimeError("FACTORY_API_KEY runtime Secret is required")
    droid = await asyncio.to_thread(provision_droid, state)
    os.environ["PATH"] = str(droid.parent) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")
    # FactoryLLM makes a fresh temporary HOME/cwd per completion. tempfile caches
    # its directory, so set it explicitly before any Lore/SDK imports.
    tempfile.tempdir = str(state / "tmp")
    loader, libraries, binary = await asyncio.to_thread(engine_files, state)
    process = await asyncio.create_subprocess_exec(
        str(loader),
        "--library-path",
        str(libraries),
        str(binary),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await ready(process)
        import gradio as gr
        import uvicorn

        from lore.api import create_app
        from lore.config import ROOT, settings

        with gr.Blocks(analytics_enabled=False) as panel:
            gr.Markdown(
                "# Lore\n[Open the full application](/)\n\n"
                "HydraDB runs privately on this Space. Trained seeds restore on startup. "
                "Visitor state can reset when free hosting sleeps or restarts."
            )
        api = create_app()
        api.add_middleware(PublicDeadline)
        api.add_middleware(SpaceOrigin)
        api.add_api_route("/hosting", hosting_redirect, include_in_schema=False)
        app = gr.mount_gradio_app(
            api,
            panel,
            path="/hosting",
            show_error=False,
            ssr_mode=False,
            mcp_server=False,
            enable_monitoring=False,
            blocked_paths=[str(state), str(settings.data_dir), str(ROOT / ".env")],
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=7860,
                access_log=False,
                proxy_headers=False,
                limit_concurrency=64,
                log_level="warning",
            )
        )
        serving = asyncio.create_task(server.serve())
        exited = asyncio.create_task(process.wait())
        await asyncio.wait((serving, exited), return_when=asyncio.FIRST_COMPLETED)
        server.should_exit = True
        await serving
        if process.returncode is not None:
            raise RuntimeError("HydraDB stopped")
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 15)
            except TimeoutError:
                process.kill()
                await process.wait()


if __name__ == "__main__":
    asyncio.run(main())
