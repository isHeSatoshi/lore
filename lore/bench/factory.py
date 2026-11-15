"""Run fresh, consistently configured Factory-only comparisons without altering r2."""

import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
from datetime import UTC, datetime


def configure():
    os.environ.update(
        LORE_LLM_TRANSPORT="factory",
        LORE_LLM_MODEL="minimax-m3.1-flash",
        LORE_LLM_EFFORT="medium",
        LORE_LLM_MAX_TOKENS="0",
    )


def main():
    configure()
    from lore.bench import run as runner
    from lore.config import ROOT, settings
    from lore.factory_llm import EFFORT, MODEL, PROTOCOL, SYSTEM_PROMPT, FactoryLLM

    args = runner.parser().parse_args()
    if args.run in {"r1", "r2", "r3", "s1", "s2", "s3"}:
        raise ValueError("Factory measurements require a fresh, separate run")
    files = [
        "learn", "ground", "sqlparse", "systems", "bird", "graphdb", "schema_ingest",
        "llm", "sqlexec", "embeddings", "factory_llm", "providers",
    ]
    paths = [f"lore/{name}.py" for name in files] + ["lore/bench/run.py", "lore/bench/factory.py"]
    protocol = {
        "protocol": PROTOCOL,
        "model": MODEL,
        "effort": EFFORT,
        "max_tokens": None,
        "max_tokens_metadata_sentinel": 0,
        "output_limit": "Managed by Droid; no explicit output-token control exposed by SDK",
        "system_prompt": SYSTEM_PROMPT,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "tools": [],
        "tool_policy": "restrict_tools={Read}, disabled_tools={Read}; verify zero allowed before every turn",
        "sessions": "Fresh session, empty HOME and working directory for every completion",
        "sdk_version": importlib.metadata.version("droid-sdk"),
        "droid_version": subprocess.check_output(["droid", "--version"], text=True).strip(),
        "file_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        "seed": args.seed,
        "stream_cap": args.stream_cap,
        "checkpoints": [float(x) for x in args.checkpoints.split(",")],
        "usage_accounting": (
            "Input plus cache-read plus cache-creation components; output plus thinking components. "
            "Native SDK components retained separately; SDK-internal retries may be unreported."
        ),
        "r2_policy": "No r2 answers, learned graphs, or completion cache reused",
    }
    target = ROOT / "results" / args.run / "learning_configuration.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = json.loads(target.read_text())
        if {k: v for k, v in old.items() if k != "captured_at"} != protocol:
            raise ValueError("Factory protocol changed; use a fresh run id")
    else:
        target.write_text(
            json.dumps({**protocol, "captured_at": datetime.now(UTC).isoformat()}, indent=2) + "\n"
        )
    # The original runner, prompts, learning logic, and execution metric remain byte-identical.
    runner.LLM = FactoryLLM
    if settings.max_tokens != 0:
        raise RuntimeError("Factory configuration was imported before transport selection")
    asyncio.run(runner.run(args))


if __name__ == "__main__":
    main()
