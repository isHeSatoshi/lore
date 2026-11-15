import asyncio
import json
import resource
import time

import numpy as np

from lore.bird import load_test
from lore.config import ROOT
from lore.embeddings import Embedder


async def main():
    questions = load_test()
    texts = [max(questions, key=lambda q: len(q.question)).question, questions[0].question]
    embedder = Embedder()
    began = time.monotonic()
    vectors = await embedder.embed(texts)
    cold_ms = 1000 * (time.monotonic() - began)
    assert vectors.shape == (2, 384)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    cached = Embedder()
    began = time.monotonic()
    again = await cached.embed(texts)
    cache_ms = 1000 * (time.monotonic() - began)
    assert cached.model is None and np.array_equal(vectors, again)
    report = {
        "model": embedder.model_name,
        "dimension": vectors.shape[1],
        "cold_ms_including_download": cold_ms,
        "disk_cache_ms": cache_ms,
        "max_question_chars": max(map(len, texts)),
        "threads": 1,
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    target = ROOT / "results/smoke/embeddings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
