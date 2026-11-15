"""Run inside the production image, without publishing ports or calling the model."""

import asyncio
import importlib.util
import json
import os

import httpx

from lore.api import app
from lore.config import ROOT


async def main():
    assert os.getuid() == 10002
    assert str(ROOT) == "/app"
    assert importlib.util.find_spec("fastembed") is None
    assert not os.access("/app/data", os.W_OK)
    probe = ROOT / "state/.image-check"
    probe.write_text("writable")
    probe.unlink()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://image-check"
        ) as client:
            assert (await client.get("/healthz")).status_code == 200
            databases = await client.get("/api/dbs")
            assert databases.status_code == 200 and databases.json()["databases"]
            frontend = await client.get("/")
            assert frontend.status_code == 200 and "<html" in frontend.text
            invalid = await client.post(
                "/api/ask",
                content=b'{"db":"invalid","question":"\\ud800"}',
                headers={"Content-Type": "application/json"},
            )
            assert invalid.status_code == 422
    print(
        json.dumps(
            {
                "non_root": True,
                "read_only_database_mount": True,
                "writable_state": True,
                "health": True,
                "database_listing": True,
                "frontend": True,
                "invalid_unicode_rejected": True,
                "bench_dependencies_absent": True,
                "model_calls": 0,
                "public_ports": 0,
            },
            indent=2,
        )
    )


asyncio.run(main())
