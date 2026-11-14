"""Local cache of what retrieval fetched: feeds, extracted articles and domain lookups.

One SQLite file (`RETRIEVAL_DB_PATH`, default `~/.cache/junction-2026/retrieval.sqlite`) with a
key-value table per namespace. Values are JSON; each read states how old a value may be. The
cache is a speed-up only: if the file cannot be opened, retrieval runs without it.
`RETRIEVAL_CACHE=0` turns it off. Article text lives only here, never in the repository.
"""

import json
import logging
import os
import sqlite3
import time
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".cache" / "junction-2026" / "retrieval.sqlite"


class Cache:
    """Used from the event loop thread only; each call is one short local transaction."""

    def __init__(self, path: Path | str):
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " ns TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, stored_at REAL NOT NULL,"
            " PRIMARY KEY (ns, key))"
        )

    def get(self, ns: str, key: str, max_age: timedelta) -> Any | None:
        try:
            row = self._db.execute(
                "SELECT value FROM kv WHERE ns = ? AND key = ? AND stored_at >= ?",
                (ns, key, time.time() - max_age.total_seconds()),
            ).fetchone()
        except sqlite3.Error as e:
            log.warning("retrieval cache read failed (%s)", e)
            return None
        return None if row is None else json.loads(row[0])

    def put(self, ns: str, key: str, value: Any) -> None:
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO kv (ns, key, value, stored_at) VALUES (?, ?, ?, ?)",
                (ns, key, json.dumps(value, ensure_ascii=False), time.time()),
            )
        except sqlite3.Error as e:
            log.warning("retrieval cache write failed (%s)", e)


class NoCache:
    def get(self, ns: str, key: str, max_age: timedelta) -> Any | None:
        return None

    def put(self, ns: str, key: str, value: Any) -> None:
        pass


@cache
def default_cache() -> Cache | NoCache:
    if os.environ.get("RETRIEVAL_CACHE") == "0":
        return NoCache()
    path = Path(os.environ.get("RETRIEVAL_DB_PATH") or DEFAULT_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return Cache(path)
    except (OSError, sqlite3.Error) as e:
        log.warning("retrieval cache unavailable at %s (%s): running without it", path, e)
        return NoCache()
