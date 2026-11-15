"""Run inside the production image, without publishing ports or calling the model."""

import asyncio
import importlib.metadata
import importlib.util
import json
import logging
import os
import subprocess
from types import SimpleNamespace

import httpx

from lore.api import app, create_app
from lore.config import ROOT


async def main():
    assert os.getuid() == 10002
    assert str(ROOT) == "/app"
    assert importlib.util.find_spec("fastembed") is None
    factory = os.getenv("LORE_LLM_TRANSPORT") == "factory"
    if factory:
        assert importlib.metadata.version("droid-sdk") == "0.5.0"
        assert subprocess.check_output(["droid", "--version"], text=True).strip() == "1.12.1"
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
            trained = sum(db["trained"] for db in databases.json()["databases"])
            if os.getenv("LORE_IMAGE_REQUIRE_TRAINED") == "1":
                assert len(databases.json()["databases"]) == trained == 4
            frontend = await client.get("/")
            assert frontend.status_code == 200 and "<html" in frontend.text
            invalid = await client.post(
                "/api/ask",
                content=b'{"db":"invalid","question":"\\ud800"}',
                headers={"Content-Type": "application/json"},
            )
            assert invalid.status_code == 422

    async def noop():
        pass

    async def fail(*_args):
        raise RuntimeError("private image-check request detail")

    boundary = create_app(SimpleNamespace(startup=noop, close=noop, answer=fail))
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("lore.api")
    capture = Capture()
    logger.addHandler(capture)
    try:
        async with boundary.router.lifespan_context(boundary):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=boundary), base_url="http://image-check"
            ) as client:
                response = await client.post(
                    "/api/ask", json={"db": "fixture", "question": "A question"}
                )
                assert response.status_code == 503
                assert "private image-check" not in response.text
                assert all("private image-check" not in line for line in records)
                assert any("RuntimeError" in line for line in records)
    finally:
        logger.removeHandler(capture)
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
                "unexpected_service_error_sanitized": True,
                "bench_dependencies_absent": True,
                "trained_databases": trained,
                "factory_runtime_verified": factory,
                "model_calls": 0,
                "public_ports": 0,
            },
            indent=2,
        )
    )


asyncio.run(main())
