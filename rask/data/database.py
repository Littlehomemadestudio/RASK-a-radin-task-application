"""
database.py — SQLite database layer (replaces Room).

Schema mirrors the Room entities from the original Kotlin version:
    activities, categories, goals, streaks, templates, badges.

Uses the stdlib sqlite3 module — no extra dependency needed on Android.
Thread-safe access via a single connection with check_same_thread=False
plus a re-entrant lock; Kivy's UI thread is the only writer.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from rask import config as cfg

_LOCK = threading.RLock()
_CONN: Optional[sqlite3.Connection] = None
_DB_PATH: Optional[Path] = None


def _app_data_dir() -> Path:
    """Return a writable app data dir (works on Android + desktop)."""
    # On Android, user_data_dir is set by Kivy's App
    from kivy.app import App
    app = App.get_running_app()
    if app is not None:
        return Path(app.user_data_dir)
    # Desktop fallback
    return Path.home() / ".rask"


def db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _app_data_dir() / cfg.DB_NAME
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        p = db_path()
        _CONN = sqlite3.connect(str(p), check_same_thread=False, isolation_level=None)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute("PRAGMA foreign_keys=ON")
        _CONN.execute("PRAGMA synchronous=NORMAL")
        _create_schema(_CONN)
        _seed_defaults(_CONN)
    return _CONN


def close() -> None:
    global _CONN
    if _CONN is not None:
        _CONN.close()
        _CONN = None


# === Schema ===

_SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    color       TEXT NOT NULL DEFAULT '#D4AF37',
    name_en     TEXT NOT NULL,
    name_fa     TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '',
    order_index INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL DEFAULT '',
    category_id   INTEGER,
    kind          TEXT NOT NULL DEFAULT 'manual',
    date_iso      TEXT NOT NULL,
    start_iso     TEXT,
    end_iso       TEXT,
    duration_sec  INTEGER NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    template_id   INTEGER,
    voice_input   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_act_date ON activities(date_iso);
CREATE INDEX IF NOT EXISTS idx_act_cat  ON activities(category_id);
CREATE INDEX IF NOT EXISTS idx_act_kind ON activities(kind);

CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL DEFAULT 'daily',
    category_id     INTEGER,
    target_minutes  INTEGER NOT NULL DEFAULT 60,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS streaks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id        INTEGER NOT NULL,
    current        INTEGER NOT NULL DEFAULT 0,
    longest        INTEGER NOT NULL DEFAULT 0,
    last_hit_date  TEXT,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS templates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    title                TEXT NOT NULL,
    category_id          INTEGER,
    default_duration_min INTEGER NOT NULL DEFAULT 30,
    icon                 TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS badges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    title_en   TEXT NOT NULL,
    title_fa   TEXT NOT NULL,
    earned_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_store (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _create_schema(conn: sqlite3.Connection) -> None:
    with _LOCK:
        conn.executescript(_SCHEMA)


def _seed_defaults(conn: sqlite3.Connection) -> None:
    with _LOCK:
        cur = conn.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] > 0:
            return
        for i, (key, color, name) in enumerate(cfg.DEFAULT_CATEGORIES):
            conn.execute(
                "INSERT INTO categories(key,color,name_en,name_fa,order_index) "
                "VALUES (?,?,?,?,?)",
                (key, color, name, name, i),  # name_fa same as en for now
            )
        # Default daily goal: 120 min focus across all categories
        conn.execute(
            "INSERT INTO goals(period,category_id,target_minutes,active,created_at) "
            "VALUES ('daily',NULL,120,1,?)",
            (_now_iso(),),
        )


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


# === kv_store (replaces SharedPreferences / DataStore) ===

def pref_get(key: str, default: str = "") -> str:
    with _LOCK:
        cur = get_connection().execute(
            "SELECT value FROM kv_store WHERE key=?", (key,)
        )
        row = cur.fetchone()
        return row["value"] if row else default


def pref_set(key: str, value: str) -> None:
    with _LOCK:
        get_connection().execute(
            "INSERT INTO kv_store(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def pref_get_int(key: str, default: int = 0) -> int:
    v = pref_get(key)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def pref_set_int(key: str, value: int) -> None:
    pref_set(key, str(value))


def pref_get_bool(key: str, default: bool = False) -> bool:
    v = pref_get(key)
    if not v:
        return default
    return v == "1" or v.lower() == "true"


def pref_set_bool(key: str, value: bool) -> None:
    pref_set(key, "1" if value else "0")


# === Low-level helpers used by repositories ===

def query_all(sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    with _LOCK:
        cur = get_connection().execute(sql, tuple(params))
        return cur.fetchall()


def query_one(sql: str, params: Iterable = ()) -> Optional[sqlite3.Row]:
    with _LOCK:
        cur = get_connection().execute(sql, tuple(params))
        return cur.fetchone()


def execute(sql: str, params: Iterable = ()) -> int:
    """Execute and return lastrowid."""
    with _LOCK:
        cur = get_connection().execute(sql, tuple(params))
        return cur.lastrowid


def execute_many(sql: str, params: Iterable[Iterable]) -> None:
    with _LOCK:
        get_connection().executemany(sql, [tuple(p) for p in params])


def fetch_val(sql: str, params: Iterable = ()) -> Any:
    row = query_one(sql, params)
    if row is None:
        return None
    return row[0]
