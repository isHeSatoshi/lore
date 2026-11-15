"""Bounded non-root provisioning/provider smoke; never starts Hydra or publishes."""

import argparse
import asyncio
import json
import os
import resource
import shutil
import stat
import sys
import tempfile
import time
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

try:
    from .app import configure
    from .droid_runtime import SDK_VERSION, VERSION, architecture, digest, provision_droid
except ImportError:
    from app import configure
    from droid_runtime import SDK_VERSION, VERSION, architecture, digest, provision_droid


async def verify_tool_policy(state):
    """Mirror frozen v2's deny/restrict intersection, without model inference."""
    from droid_sdk import ReasoningEffort, Runtime, Session, SessionConfig

    from lore.factory_llm import PROTOCOL, SYSTEM_PROMPT

    if PROTOCOL != "factory-sdk-v2":
        raise RuntimeError("Install the current frozen factory-sdk-v2 provider first")
    config = SessionConfig(
        system_prompt=SYSTEM_PROMPT,
        disable_builtin_skills=True,
        auto_reject_permission_requests=True,
        enabled_tools=(),
        disabled_tools={"Read"},
        restrict_tools={"Read"},
    )
    with tempfile.TemporaryDirectory(prefix="lore-factory-policy-", dir=state / "tmp") as home:
        env = {
            key: ""
            for key in os.environ
            if any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "HUGGING_FACE"))
        }
        env.update(HOME=home, XDG_CONFIG_HOME=home, FACTORY_API_KEY=os.environ["FACTORY_API_KEY"])
        session = Session(
            cwd=home,
            model="minimax-m3.1-flash",
            reasoning_effort=ReasoningEffort.MEDIUM,
            config=config,
            runtime=Runtime(env=env),
            api_key=os.environ["FACTORY_API_KEY"],
        )
        try:
            async with asyncio.timeout(30):
                await session.open()
                if (
                    session.settings.model != "minimax-m3.1-flash"
                    or session.settings.reasoning_effort != ReasoningEffort.MEDIUM
                ):
                    raise RuntimeError("Requested model/effort not selected")
                tools = await session.list_tools()
                if not tools or any(tool.allowed for tool in tools):
                    raise RuntimeError("Expected a nonempty catalog with zero allowed tools")
                return {"protocol": PROTOCOL, "catalog_tools": len(tools), "allowed_tools": 0}
        finally:
            await asyncio.shield(session.close())


async def smoke(state, completion, check_tools=False):
    if os.getuid() == 0:
        raise RuntimeError("Run this smoke as a non-root user")
    if not os.statvfs(__file__).f_flag & os.ST_RDONLY:
        raise RuntimeError("Bind the source tree read-only for this smoke")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = configure(state)
    assert "FACTORY_API_KEY" not in environment
    assert version("droid-sdk") == SDK_VERSION
    assert version("gradio") == "6.32.0"
    start = time.monotonic()
    binary = await asyncio.to_thread(provision_droid, state)
    assert await asyncio.to_thread(provision_droid, state) == binary
    os.environ["PATH"] = str(binary.parent) + os.pathsep + os.environ.get("PATH", "")
    tempfile.tempdir = str(state / "tmp")
    assert Path(shutil.which("droid")) == binary
    assert stat.S_IMODE(binary.stat().st_mode) == 0o500
    report = {
        "nonroot_uid": os.getuid(),
        "readonly_code": True,
        "executable_private_state": True,
        "sdk_version": version("droid-sdk"),
        "gradio_version": version("gradio"),
        "cli_version": VERSION,
        "cli_architecture": architecture(),
        "cli_sha256": digest(binary),
        "download_and_cached_verification_passed": True,
        "provision_seconds": round(time.monotonic() - start, 2),
        "hydra_started": False,
        "published": False,
        "completion_requested": completion,
        "release_run": "r4",
        "tool_policy_checked": False,
    }
    if completion or check_tools:
        report.update(await verify_tool_policy(state))
        report["tool_policy_checked"] = True
    if completion:
        from lore.config import settings
        from lore.providers import create_llm

        llm = create_llm("hf-provision-smoke", cfg=replace(settings, data_dir=state / "app"))
        assert type(llm).__name__ == "FactoryLLM"
        start = time.monotonic()
        try:
            async with asyncio.timeout(60):
                result = await llm.complete("Return only this SQL statement: SELECT 1;", cache=False)
            assert result.text.strip().rstrip(";") == "SELECT 1"
            report.update(
                completion_passed=True,
                model=settings.model,
                effort=settings.effort,
                max_tokens=settings.max_tokens,
                completion_seconds=round(time.monotonic() - start, 2),
                metered_calls=llm.usage()["calls"],
            )
        finally:
            await llm.close()
        assert not list((state / "tmp").glob("lore-factory-*"))
        report["fresh_home_removed_after_completion"] = True
    report["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--completion", action="store_true")
    parser.add_argument("--check-tools", action="store_true", help="Check v2 tools without inference")
    args = parser.parse_args()
    try:
        report = asyncio.run(smoke(args.state.resolve(), args.completion, args.check_tools))
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    except Exception as exc:
        print(f"Isolated Droid smoke failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
