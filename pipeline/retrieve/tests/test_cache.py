"""The SQLite cache: round trip, expiry, namespaces, and running without it."""

import sqlite3
import time
from datetime import timedelta

from pipeline.retrieve import cache as cache_module
from pipeline.retrieve.cache import Cache, NoCache, default_cache

DAY = timedelta(days=1)


def test_round_trip_and_namespaces(tmp_path):
    c = Cache(tmp_path / "r.sqlite")
    c.put("article", "https://a.example/x", {"title": "Città", "ids": ["G-1"]})
    assert c.get("article", "https://a.example/x", DAY) == {"title": "Città", "ids": ["G-1"]}
    assert c.get("feeds", "https://a.example/x", DAY) is None
    assert c.get("article", "https://a.example/y", DAY) is None
    c.put("article", "https://a.example/x", {})  # a remembered miss replaces the value
    assert c.get("article", "https://a.example/x", DAY) == {}


def test_old_values_are_not_returned(tmp_path, monkeypatch):
    c = Cache(tmp_path / "r.sqlite")
    c.put("feeds", "k", [1])
    later = time.time() + 3600
    monkeypatch.setattr(cache_module.time, "time", lambda: later)
    assert c.get("feeds", "k", timedelta(minutes=10)) is None
    assert c.get("feeds", "k", timedelta(hours=2)) == [1]


def test_values_survive_a_new_connection(tmp_path):
    Cache(tmp_path / "r.sqlite").put("rdap", "example.it", {"at": None})
    assert Cache(tmp_path / "r.sqlite").get("rdap", "example.it", DAY) == {"at": None}


def test_a_broken_database_is_a_miss_not_an_error(tmp_path):
    c = Cache(tmp_path / "r.sqlite")
    c._db.execute("DROP TABLE kv")
    assert c.get("feeds", "k", DAY) is None
    c.put("feeds", "k", [1])  # logged, not raised


def test_no_cache():
    c = NoCache()
    c.put("feeds", "k", [1])
    assert c.get("feeds", "k", DAY) is None


def test_default_cache_location_and_switch(tmp_path, monkeypatch):
    default_cache.cache_clear()
    try:
        monkeypatch.setenv("RETRIEVAL_DB_PATH", str(tmp_path / "sub" / "r.sqlite"))
        assert isinstance(default_cache(), Cache)
        assert (tmp_path / "sub" / "r.sqlite").exists()

        default_cache.cache_clear()
        monkeypatch.setenv("RETRIEVAL_CACHE", "0")
        assert isinstance(default_cache(), NoCache)

        default_cache.cache_clear()
        monkeypatch.delenv("RETRIEVAL_CACHE")
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        monkeypatch.setenv("RETRIEVAL_DB_PATH", str(blocker / "r.sqlite"))
        assert isinstance(default_cache(), NoCache)  # unusable path: run without a cache
    finally:
        default_cache.cache_clear()


def test_the_file_is_sqlite_in_wal_mode(tmp_path):
    Cache(tmp_path / "r.sqlite")
    mode = sqlite3.connect(tmp_path / "r.sqlite").execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
