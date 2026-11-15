#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/python - <<'PY'
import time
import httpx
from lore.config import settings

deadline = time.monotonic() + 120
while True:
    try:
        if httpx.get(settings.admin_url + "/readyz", timeout=3).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    if time.monotonic() >= deadline:
        raise SystemExit("HydraDB did not become ready in 120 seconds")
    time.sleep(1)

headers = {"Authorization": "Bearer " + settings.hydra_token, "X-Graph-Namespace": "local"}
def run(query):
    r = httpx.post(settings.http_url + "/v1/graphs/default/query",
                   json={"cell_id": "cell-0", "query": query}, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    assert "rows" in data and "error" not in data, data
    return data
try:
    run("MERGE (a {id: 999999})-[:SMOKE]->(b {id: 999998})")
    result = run("MATCH (a {id: 999999})-[:SMOKE]->(b) RETURN b.id AS id")
    assert result["rows"] == [[{"type": "vertex_id", "value": 999998}]], result
    print("HydraDB HTTP write/read: PASS", result["rows"])
finally:
    for node in (999999, 999998):
        run(f"MATCH (a {{id: {node}}}) DETACH DELETE a")
PY
