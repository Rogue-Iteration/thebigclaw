#!/usr/bin/env python3
"""
SQLite database layer for the Gradient Research Assistant.

Provides a shared database accessed by all agents (Max, Nova, Luna, Ace).
The DB file lives on the Docker volume at ~/.openclaw/research.db for
persistence across container restarts.

Tables:
- watchlist:       tracked tickers (replaces watchlist.json)
- settings:        global config (default rules, model prefs)
- research_tasks:  research tasks assigned to agents
- agent_data:      flexible key-value store per agent
- research_log:    activity log for auditing/debugging

Usage:
    from db import get_connection, init_db

    conn = get_connection()       # uses default path
    init_db(conn)                 # creates tables (idempotent)

CLI:
    python3 db.py --init          # initialize the database
    python3 db.py --status        # show table row counts
"""

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional


# ─── Default DB path ─────────────────────────────────────────────

DEFAULT_DB_PATH = os.path.join(
    os.environ.get("HOME", "/root"), ".openclaw", "research.db"
)


# ─── Connection ──────────────────────────────────────────────────


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and busy timeout.

    Args:
        db_path: Path to the database file. Defaults to ~/.openclaw/research.db.
                 Use ":memory:" for testing.

    Returns:
        A configured sqlite3.Connection.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    # Ensure parent directory exists (unless in-memory)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # dict-like access to rows
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ──────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Tracked tickers (replaces watchlist.json tickers[])
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    theme TEXT,
    directive TEXT,
    explore_adjacent INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (date('now')),
    rules TEXT DEFAULT '{}'
);

-- Global settings (replaces watchlist.json default_rules + global_settings)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Research tasks assigned to agents
CREATE TABLE IF NOT EXISTS research_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    title TEXT NOT NULL,
    description TEXT,
    assigned_agent TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    result_summary TEXT
);

-- Flexible per-agent key-value storage
CREATE TABLE IF NOT EXISTS agent_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT,
    UNIQUE(agent_id, namespace, key)
);

-- Research activity log
CREATE TABLE IF NOT EXISTS research_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT
);

-- Scheduled updates (morning briefings, evening wraps, etc.)
CREATE TABLE IF NOT EXISTS scheduled_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    schedule_type TEXT NOT NULL DEFAULT 'daily',
    time TEXT NOT NULL,
    days TEXT DEFAULT '*',
    agent TEXT NOT NULL DEFAULT 'max',
    prompt TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

# Default alert rules (seeded on first init)
DEFAULT_RULES = {
    "price_movement_pct": 5,
    "sentiment_shift": True,
    "social_volume_spike": True,
    "sec_filing": True,
    "competitive_news": True,
}

DEFAULT_GLOBAL_SETTINGS = {
    "significance_threshold": 6,
    "cheap_model": "openai-gpt-oss-120b",
    "strong_model": "openai-gpt-oss-120b",
}


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist and seed default settings.

    Idempotent — safe to call on every startup.
    """
    conn.executescript(SCHEMA_SQL)

    # Seed default rules if not already set
    cursor = conn.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("default_rules", json.dumps(DEFAULT_RULES)),
        )
        for key, value in DEFAULT_GLOBAL_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        conn.commit()


# ─── Settings Helpers ────────────────────────────────────────────


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """Get a setting value by key. Returns parsed JSON."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Set a setting value (stored as JSON)."""
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    conn.commit()


def get_default_rules(conn: sqlite3.Connection) -> dict:
    """Get the default alert rules dict."""
    return get_setting(conn, "default_rules", DEFAULT_RULES)


def set_default_rules(conn: sqlite3.Connection, rules: dict) -> None:
    """Set the default alert rules dict."""
    set_setting(conn, "default_rules", rules)


# ─── Agent Data Helpers ──────────────────────────────────────────


def agent_put(
    conn: sqlite3.Connection,
    agent_id: str,
    namespace: str,
    key: str,
    value: Any,
    expires_at: Optional[str] = None,
) -> None:
    """Store a value in the agent key-value store.

    Uses INSERT OR REPLACE so existing entries are updated.
    Value is stored as JSON.
    """
    conn.execute(
        """INSERT OR REPLACE INTO agent_data
           (agent_id, namespace, key, value, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (agent_id, namespace, key, json.dumps(value), expires_at),
    )
    conn.commit()


def agent_get(
    conn: sqlite3.Connection,
    agent_id: str,
    namespace: str,
    key: str,
    default: Any = None,
) -> Any:
    """Retrieve a value from the agent key-value store."""
    row = conn.execute(
        """SELECT value FROM agent_data
           WHERE agent_id = ? AND namespace = ? AND key = ?""",
        (agent_id, namespace, key),
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def agent_list(
    conn: sqlite3.Connection,
    agent_id: str,
    namespace: str,
) -> list[dict]:
    """List all entries in an agent's namespace.

    Returns list of dicts with keys: key, value, created_at, expires_at.
    """
    rows = conn.execute(
        """SELECT key, value, created_at, expires_at FROM agent_data
           WHERE agent_id = ? AND namespace = ?
           ORDER BY created_at DESC""",
        (agent_id, namespace),
    ).fetchall()
    results = []
    for row in rows:
        try:
            val = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            val = row["value"]
        results.append({
            "key": row["key"],
            "value": val,
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        })
    return results


def agent_delete(
    conn: sqlite3.Connection,
    agent_id: str,
    namespace: str,
    key: str,
) -> bool:
    """Delete an entry from the agent key-value store.

    Returns True if a row was deleted.
    """
    cursor = conn.execute(
        """DELETE FROM agent_data
           WHERE agent_id = ? AND namespace = ? AND key = ?""",
        (agent_id, namespace, key),
    )
    conn.commit()
    return cursor.rowcount > 0


# ─── Research Log Helpers ────────────────────────────────────────


def log_event(
    conn: sqlite3.Connection,
    symbol: str,
    agent_id: str,
    event_type: str,
    summary: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Log a research event. Returns the new row ID."""
    cursor = conn.execute(
        """INSERT INTO research_log
           (symbol, agent_id, event_type, summary, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (
            symbol,
            agent_id,
            event_type,
            summary,
            json.dumps(metadata) if metadata else None,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_events(
    conn: sqlite3.Connection,
    limit: int = 20,
    symbol: Optional[str] = None,
    agent_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> list[dict]:
    """Get recent research log events with optional filters."""
    query = "SELECT * FROM research_log WHERE 1=1"
    params: list = []

    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        entry = dict(row)
        if entry.get("metadata"):
            try:
                entry["metadata"] = json.loads(entry["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(entry)
    return results


# ─── CLI Interface ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Research database management")
    parser.add_argument(
        "--init", action="store_true", help="Initialize the database (create tables)"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show table row counts"
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB_PATH, help="Path to database file"
    )
    args = parser.parse_args()

    conn = get_connection(args.db)

    if args.init:
        init_db(conn)
        print(f"✓ Database initialized at {args.db}")
        return

    if args.status:
        init_db(conn)  # ensure tables exist
        tables = ["watchlist", "settings", "research_tasks", "agent_data", "research_log", "scheduled_updates"]
        print(f"📊 Database: {args.db}")
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
