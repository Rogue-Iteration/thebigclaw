"""
Tests for db.py — Core database layer.

Tests cover:
- Database initialization (table creation, idempotency)
- WAL mode and pragmas
- Settings get/set
- Default rules storage
- Agent data key-value store (put, get, list, delete)
- Research log (insert, query with filters)
"""

import json
import sqlite3

import pytest

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from db import (
    get_connection,
    init_db,
    get_setting,
    set_setting,
    get_default_rules,
    set_default_rules,
    agent_put,
    agent_get,
    agent_list,
    agent_delete,
    log_event,
    get_recent_events,
    DEFAULT_RULES,
    DEFAULT_GLOBAL_SETTINGS,
)


@pytest.fixture
def conn():
    """In-memory database connection with schema initialized."""
    c = get_connection(":memory:")
    init_db(c)
    yield c
    c.close()


# ─── Initialization ──────────────────────────────────────────────


class TestInitDb:
    def test_creates_all_tables(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = sorted(row["name"] for row in tables)
        assert "agent_data" in table_names
        assert "research_log" in table_names
        assert "research_tasks" in table_names
        assert "settings" in table_names
        assert "watchlist" in table_names

    def test_idempotent(self, conn):
        """Calling init_db twice should not error or duplicate data."""
        init_db(conn)  # already called in fixture
        init_db(conn)  # should be safe
        count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        # Default settings should not be duplicated
        assert count == len(DEFAULT_GLOBAL_SETTINGS) + 1  # +1 for default_rules

    def test_wal_mode(self):
        c = get_connection(":memory:")
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        # In-memory DBs may report 'memory' instead of 'wal'
        assert mode in ("wal", "memory")
        c.close()

    def test_seeds_default_rules(self, conn):
        rules = get_default_rules(conn)
        assert rules == DEFAULT_RULES

    def test_seeds_global_settings(self, conn):
        for key, expected in DEFAULT_GLOBAL_SETTINGS.items():
            actual = get_setting(conn, key)
            assert actual == expected


# ─── Settings ─────────────────────────────────────────────────────


class TestSettings:
    def test_get_missing_key_returns_default(self, conn):
        assert get_setting(conn, "nonexistent", "fallback") == "fallback"

    def test_get_missing_key_returns_none(self, conn):
        assert get_setting(conn, "nonexistent") is None

    def test_set_and_get_string(self, conn):
        set_setting(conn, "test_key", "hello")
        assert get_setting(conn, "test_key") == "hello"

    def test_set_and_get_number(self, conn):
        set_setting(conn, "threshold", 42)
        assert get_setting(conn, "threshold") == 42

    def test_set_and_get_bool(self, conn):
        set_setting(conn, "enabled", True)
        assert get_setting(conn, "enabled") is True

    def test_set_and_get_dict(self, conn):
        data = {"a": 1, "b": [2, 3]}
        set_setting(conn, "complex", data)
        assert get_setting(conn, "complex") == data

    def test_overwrite_setting(self, conn):
        set_setting(conn, "key", "old")
        set_setting(conn, "key", "new")
        assert get_setting(conn, "key") == "new"


class TestDefaultRules:
    def test_get_default_rules(self, conn):
        rules = get_default_rules(conn)
        assert "price_movement_pct" in rules
        assert isinstance(rules["price_movement_pct"], int)

    def test_set_default_rules(self, conn):
        new_rules = {"price_movement_pct": 10, "sentiment_shift": False}
        set_default_rules(conn, new_rules)
        assert get_default_rules(conn) == new_rules


# ─── Agent Data KV Store ─────────────────────────────────────────


class TestAgentData:
    def test_put_and_get(self, conn):
        agent_put(conn, "luna", "reddit", "post_123", {"title": "Test", "score": 42})
        result = agent_get(conn, "luna", "reddit", "post_123")
        assert result == {"title": "Test", "score": 42}

    def test_get_missing_returns_default(self, conn):
        assert agent_get(conn, "luna", "reddit", "nope") is None
        assert agent_get(conn, "luna", "reddit", "nope", "fallback") == "fallback"

    def test_put_overwrites(self, conn):
        agent_put(conn, "luna", "cache", "key1", "v1")
        agent_put(conn, "luna", "cache", "key1", "v2")
        assert agent_get(conn, "luna", "cache", "key1") == "v2"

    def test_namespace_isolation(self, conn):
        agent_put(conn, "luna", "ns1", "key", "value1")
        agent_put(conn, "luna", "ns2", "key", "value2")
        assert agent_get(conn, "luna", "ns1", "key") == "value1"
        assert agent_get(conn, "luna", "ns2", "key") == "value2"

    def test_agent_isolation(self, conn):
        agent_put(conn, "luna", "ns", "key", "luna_val")
        agent_put(conn, "nova", "ns", "key", "nova_val")
        assert agent_get(conn, "luna", "ns", "key") == "luna_val"
        assert agent_get(conn, "nova", "ns", "key") == "nova_val"

    def test_list_namespace(self, conn):
        agent_put(conn, "luna", "reddit", "p1", {"score": 10})
        agent_put(conn, "luna", "reddit", "p2", {"score": 20})
        agent_put(conn, "luna", "other", "x", "ignored")

        items = agent_list(conn, "luna", "reddit")
        assert len(items) == 2
        keys = {item["key"] for item in items}
        assert keys == {"p1", "p2"}

    def test_list_empty_namespace(self, conn):
        items = agent_list(conn, "luna", "empty_ns")
        assert items == []

    def test_delete(self, conn):
        agent_put(conn, "luna", "ns", "key", "value")
        deleted = agent_delete(conn, "luna", "ns", "key")
        assert deleted is True
        assert agent_get(conn, "luna", "ns", "key") is None

    def test_delete_nonexistent(self, conn):
        deleted = agent_delete(conn, "luna", "ns", "nope")
        assert deleted is False

    def test_expires_at(self, conn):
        agent_put(conn, "luna", "cache", "k", "v", expires_at="2026-03-01T00:00:00")
        items = agent_list(conn, "luna", "cache")
        assert items[0]["expires_at"] == "2026-03-01T00:00:00"


# ─── Research Log ────────────────────────────────────────────────


class TestResearchLog:
    def test_log_event(self, conn):
        row_id = log_event(conn, "CAKE", "nova", "gather", summary="Found 5 articles")
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_log_with_metadata(self, conn):
        meta = {"articles": 5, "sources": ["google", "reddit"]}
        log_event(conn, "CAKE", "nova", "gather", metadata=meta)
        events = get_recent_events(conn, limit=1)
        assert events[0]["metadata"] == meta

    def test_get_recent_events_default(self, conn):
        for i in range(5):
            log_event(conn, "CAKE", "nova", "gather", summary=f"Event {i}")
        events = get_recent_events(conn, limit=3)
        assert len(events) == 3

    def test_filter_by_symbol(self, conn):
        log_event(conn, "CAKE", "nova", "gather")
        log_event(conn, "HOG", "nova", "gather")
        events = get_recent_events(conn, symbol="CAKE")
        assert len(events) == 1
        assert events[0]["symbol"] == "CAKE"

    def test_filter_by_agent(self, conn):
        log_event(conn, "CAKE", "nova", "gather")
        log_event(conn, "CAKE", "luna", "gather")
        events = get_recent_events(conn, agent_id="luna")
        assert len(events) == 1
        assert events[0]["agent_id"] == "luna"

    def test_filter_by_event_type(self, conn):
        log_event(conn, "CAKE", "nova", "gather")
        log_event(conn, "CAKE", "nova", "analyze")
        events = get_recent_events(conn, event_type="analyze")
        assert len(events) == 1
        assert events[0]["event_type"] == "analyze"

    def test_combined_filters(self, conn):
        log_event(conn, "CAKE", "nova", "gather")
        log_event(conn, "CAKE", "luna", "gather")
        log_event(conn, "HOG", "nova", "gather")
        events = get_recent_events(conn, symbol="CAKE", agent_id="nova")
        assert len(events) == 1
