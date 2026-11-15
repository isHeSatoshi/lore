"""Apply a documented connection-pool cap, then invoke the frozen Factory runner."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime


def record_runtime(root, run):
    from lore.connection_pool import GRAPH_POOL_SIZE

    files = ("lore/connection_pool.py", "lore/bench/factory_runtime.py")
    configuration = {
        "driver_option": "max_connection_pool_size",
        "per_namespace_connection_pool_size": GRAPH_POOL_SIZE,
        "scope": "Client connection scheduling only; graph queries, prompts, model, learning and metric unchanged",
        "file_sha256": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files
        },
    }
    target = root / "results" / run / "runtime_configuration.json"
    if target.exists():
        old = json.loads(target.read_text())
        if any(old.get(k) != v for k, v in configuration.items()):
            raise ValueError("Graph runtime configuration changed")
        return
    journal = root / "data" / "runs" / run / "answers.jsonl"
    counts = Counter()
    if journal.exists():
        for line in journal.read_text().splitlines():
            row = json.loads(line)
            counts[(row["system"], row["phase"], row["checkpoint"])] += 1
    configuration["introduced_after"] = [
        dict(system=s, phase=p, checkpoint=c, answers=n)
        for (s, p, c), n in sorted(counts.items())
    ]
    configuration["captured_at"] = datetime.now(UTC).isoformat()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(configuration, indent=2) + "\n")


def main():
    from lore.bench.factory import configure

    configure()  # Settings must not be imported before selecting the SDK.
    from lore.bench import factory, run
    from lore.config import ROOT
    from lore.connection_pool import configure_graph_pool

    args = run.parser().parse_args()
    record_runtime(ROOT, args.run)
    configure_graph_pool()
    factory.main()


if __name__ == "__main__":
    main()
