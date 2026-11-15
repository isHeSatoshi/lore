import asyncio
import hashlib
import sqlite3

import numpy as np

from lore.config import settings


class Embedder:
    model_name = "BAAI/bge-small-en-v1.5"

    def __init__(self):
        self.path = settings.data_dir / "cache/embeddings.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.model = None
        self.lock = asyncio.Lock()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector BLOB)")

    def _compute(self, texts):
        if self.model is None:
            from fastembed import TextEmbedding

            self.model = TextEmbedding(
                self.model_name, threads=1, cache_dir=str(settings.data_dir / "cache/models")
            )
        return list(self.model.embed(texts))

    async def embed(self, texts):
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        keys = [
            hashlib.sha256((self.model_name + "\0" + text).encode()).hexdigest() for text in texts
        ]
        async with self.lock:
            found = {}
            with sqlite3.connect(self.path) as db:
                for key in keys:
                    row = db.execute("SELECT vector FROM vectors WHERE key=?", (key,)).fetchone()
                    if row:
                        found[key] = np.frombuffer(row[0], dtype=np.float32)
            missing = list(dict.fromkeys(key for key in keys if key not in found))
            if missing:
                by_key = dict(zip(keys, texts, strict=True))
                vectors = await asyncio.to_thread(self._compute, [by_key[key] for key in missing])
                with sqlite3.connect(self.path) as db:
                    for key, vector in zip(missing, vectors, strict=True):
                        vector = np.asarray(vector, dtype=np.float32)
                        vector = vector / (np.linalg.norm(vector) or 1)
                        db.execute(
                            "INSERT OR REPLACE INTO vectors VALUES (?, ?)", (key, vector.tobytes())
                        )
                        found[key] = vector
            return np.stack([found[key] for key in keys])
