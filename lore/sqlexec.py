"""Read-only SQLite execution and BIRD's strict set-of-row-tuples metric."""

import asyncio
import base64
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from lore.config import settings

_sql_slots = asyncio.Semaphore(4)
_allowed = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


def _execute(db_path, sql, timeout_s=30.0, max_rows=None):
    start = time.monotonic()
    conn = timer = None
    try:
        conn = sqlite3.connect(
            Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False
        )
        conn.execute("PRAGMA query_only=ON")
        if max_rows is not None:
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_VDBE_OP, 100_000)
        conn.set_authorizer(
            lambda action, *_: sqlite3.SQLITE_OK if action in _allowed else sqlite3.SQLITE_DENY
        )
        conn.set_progress_handler(lambda: time.monotonic() - start >= timeout_s, 1000)
        timer = threading.Timer(timeout_s, conn.interrupt)
        timer.daemon = True
        timer.start()
        cur = conn.execute(sql)
        columns = [c[0] for c in (cur.description or [])]
        if max_rows is None:
            rows = cur.fetchall()
        else:
            rows, size = [], 0
            for _ in range(max_rows):
                row = cur.fetchone()
                if row is None:
                    break
                size += sum(len(v) if isinstance(v, bytes) else len(str(v).encode()) for v in row)
                if size > 1_000_000:
                    break
                rows.append(row)
        return rows, None, int((time.monotonic() - start) * 1000), columns
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}", int((time.monotonic() - start) * 1000), []
    finally:
        if timer:
            timer.cancel()
            timer.join()
        if conn:
            conn.close()


def run_sql(db_path, sql, timeout_s=30.0, max_rows=None):
    """Return (rows, error, ms); benchmark callers must not truncate rows."""
    return _execute(db_path, sql, timeout_s, max_rows)[:3]


async def execute(db_path, sql, timeout_s=30.0, max_rows=None):
    async with _sql_slots:
        return await asyncio.to_thread(run_sql, db_path, sql, timeout_s, max_rows)


async def execute_table(db_path, sql, timeout_s=10.0, max_rows=200):
    async with _sql_slots:
        return await asyncio.to_thread(_execute, db_path, sql, timeout_s, max_rows)


def ex_match(pred_rows, gold_rows):
    return pred_rows is not None and gold_rows is not None and set(pred_rows) == set(gold_rows)


def _encode(value):
    if isinstance(value, bytes):
        return {"__blob__": base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)


def _decode(value):
    if set(value) == {"__blob__"}:
        return base64.b64decode(value["__blob__"])
    return value


class GoldCache:
    def __init__(self, path=None):
        self.path = Path(path or settings.data_dir / "cache" / "gold.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.memory = {}
        self.locks = {}
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS gold (key TEXT PRIMARY KEY, rows TEXT)")

    async def get(self, q):
        stat = q.db_path.stat()
        key = hashlib.sha256(
            json.dumps([str(q.db_path), stat.st_size, stat.st_mtime_ns, q.gold_sql]).encode()
        ).hexdigest()
        async with self.locks.setdefault(key, asyncio.Lock()):
            if key in self.memory:
                return self.memory[key]
            with sqlite3.connect(self.path) as db:
                row = db.execute("SELECT rows FROM gold WHERE key=?", (key,)).fetchone()
            if row:
                rows = [tuple(r) for r in json.loads(row[0], object_hook=_decode)]
                result = (rows, None, 0)
            else:
                result = await execute(q.db_path, q.gold_sql)
                if result[1] is None:
                    with sqlite3.connect(self.path) as db:
                        db.execute(
                            "INSERT OR REPLACE INTO gold VALUES (?, ?)",
                            (key, json.dumps(result[0], default=_encode)),
                        )
            self.memory[key] = result
            return result
