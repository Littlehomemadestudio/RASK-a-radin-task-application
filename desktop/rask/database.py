"""
rask.database
=============

SQLite persistence layer for Rask.

Schema mirrors the web/PWA IndexedDB schema 1:1 so the two products
remain conceptually identical:

    activities   — every logged activity
    categories   — user-defined categories (seeded with 7 defaults)
    goals        — daily/weekly/monthly targets
    streaks      — per-goal streak counters
    templates    — quick-log templates
    badges       — earned achievement badges
    reminders    — scheduled notifications
    kv           — generic key/value store (settings, timer state, etc.)
    tags         — many-to-many tag table for activities
    activity_tags— join table
    backups_log  — audit log of backup operations
    exports_log  — audit log of export operations
    sessions     — focus session metadata (for Pomodoro-like flows)
    settings     — typed settings (mirror of kv but with schema)
    changelog    — internal versioned migration log

This module is intentionally framework-free: pure sqlite3 from stdlib.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from . import config


# =============================================================================
# === Schema version                                                          ===
# =============================================================================

SCHEMA_VERSION: int = 1

SCHEMA_SQL: str = """
-- ============================================================================
-- activities: every logged activity
-- ============================================================================
CREATE TABLE IF NOT EXISTS activities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    duration_min    INTEGER NOT NULL DEFAULT 0,
    date_iso        TEXT NOT NULL,             -- YYYY-MM-DD (Gregorian)
    jalali_iso      TEXT,                      -- YYYY-MM-DD (Jalali, denormalized)
    start_ts        TEXT,                      -- ISO8601 start timestamp
    end_ts          TEXT,                      -- ISO8601 end timestamp
    notes           TEXT,
    tags_json       TEXT,                      -- JSON array of strings
    kind            TEXT NOT NULL DEFAULT 'manual',  -- manual | stopwatch | template | voice | recurring
    source          TEXT NOT NULL DEFAULT 'desktop', -- desktop | web | import
    template_id     INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    recurring_id    INTEGER REFERENCES recurring(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date_iso);
CREATE INDEX IF NOT EXISTS idx_activities_category ON activities(category_id);
CREATE INDEX IF NOT EXISTS idx_activities_kind ON activities(kind);
CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at);
CREATE INDEX IF NOT EXISTS idx_activities_deleted ON activities(deleted_at);

-- ============================================================================
-- categories: user-defined activity categories
-- ============================================================================
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL UNIQUE,
    name_en         TEXT NOT NULL,
    name_fa         TEXT NOT NULL,
    color           TEXT NOT NULL,
    icon            TEXT NOT NULL DEFAULT 'ring',
    order_index     INTEGER NOT NULL DEFAULT 0,
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- ============================================================================
-- goals: daily/weekly/monthly activity targets
-- ============================================================================
CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL CHECK(period IN ('daily','weekly','monthly')),
    category_id     INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    target_minutes  INTEGER NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    title           TEXT,
    color           TEXT,
    reminder_enabled INTEGER NOT NULL DEFAULT 0,
    reminder_time   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goals_active ON goals(active);
CREATE INDEX IF NOT EXISTS idx_goals_period ON goals(period);

-- ============================================================================
-- streaks: per-goal streak counters
-- ============================================================================
CREATE TABLE IF NOT EXISTS streaks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id         INTEGER REFERENCES goals(id) ON DELETE CASCADE,
    current         INTEGER NOT NULL DEFAULT 0,
    best            INTEGER NOT NULL DEFAULT 0,
    last_hit_iso    TEXT,
    started_iso     TEXT,
    history_json    TEXT,
    updated_at      TEXT NOT NULL,
    UNIQUE(goal_id)
);

-- ============================================================================
-- templates: quick-log templates
-- ============================================================================
CREATE TABLE IF NOT EXISTS templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    title           TEXT NOT NULL,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    duration_min    INTEGER,
    tags_json       TEXT,
    notes           TEXT,
    shortcut        TEXT,
    icon            TEXT,
    color           TEXT,
    use_count       INTEGER NOT NULL DEFAULT 0,
    last_used_iso   TEXT,
    order_index     INTEGER NOT NULL DEFAULT 0,
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- ============================================================================
-- badges: earned achievement badges
-- ============================================================================
CREATE TABLE IF NOT EXISTS badges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL UNIQUE,
    name_en         TEXT,
    name_fa         TEXT,
    desc_en         TEXT,
    desc_fa         TEXT,
    icon            TEXT,
    tier            TEXT,
    earned_at       TEXT NOT NULL,
    metadata_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_badges_earned ON badges(earned_at);

-- ============================================================================
-- reminders: scheduled notifications
-- ============================================================================
CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    message         TEXT,
    time_hhmm       TEXT NOT NULL,            -- "HH:MM"
    days_mask       INTEGER NOT NULL DEFAULT 127,  -- bitmask: Sat=1 ... Fri=64
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    goal_id         INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_fired_iso  TEXT,
    snooze_until    TEXT,
    sound           INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_enabled ON reminders(enabled);

-- ============================================================================
-- kv: generic key/value store
-- ============================================================================
CREATE TABLE IF NOT EXISTS kv (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TEXT NOT NULL
);

-- ============================================================================
-- tags: distinct tags for autocomplete
-- ============================================================================
CREATE TABLE IF NOT EXISTS tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    color           TEXT,
    use_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- ============================================================================
-- activity_tags: many-to-many between activities and tags
-- ============================================================================
CREATE TABLE IF NOT EXISTS activity_tags (
    activity_id     INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_activity_tags_tag ON activity_tags(tag_id);

-- ============================================================================
-- recurring: recurring activity rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS recurring (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    duration_min    INTEGER NOT NULL,
    frequency       TEXT NOT NULL,             -- daily | weekly | monthly
    days_mask       INTEGER NOT NULL DEFAULT 127,
    time_hhmm       TEXT,
    end_date_iso    TEXT,
    next_run_iso    TEXT,
    last_run_iso    TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recurring_active ON recurring(active);
CREATE INDEX IF NOT EXISTS idx_recurring_next ON recurring(next_run_iso);

-- ============================================================================
-- sessions: focus session metadata (Pomodoro-like)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id     INTEGER REFERENCES activities(id) ON DELETE SET NULL,
    planned_min     INTEGER NOT NULL,
    actual_min      INTEGER,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    state           TEXT NOT NULL DEFAULT 'running',  -- running | paused | completed | abandoned
    pause_count     INTEGER NOT NULL DEFAULT 0,
    pause_total_sec INTEGER NOT NULL DEFAULT 0,
    metadata_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);

-- ============================================================================
-- backups_log: audit log
-- ============================================================================
CREATE TABLE IF NOT EXISTS backups_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,             -- backup | restore
    file_path       TEXT,
    file_size       INTEGER,
    success         INTEGER NOT NULL,
    error_message   TEXT,
    created_at      TEXT NOT NULL
);

-- ============================================================================
-- exports_log: audit log
-- ============================================================================
CREATE TABLE IF NOT EXISTS exports_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,             -- pdf | csv | png
    file_path       TEXT,
    file_size       INTEGER,
    record_count    INTEGER,
    success         INTEGER NOT NULL,
    error_message   TEXT,
    created_at      TEXT NOT NULL
);

-- ============================================================================
-- settings: typed settings (mirror of kv, but with schema)
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    type            TEXT NOT NULL DEFAULT 'string',  -- string | int | float | bool | json
    updated_at      TEXT NOT NULL
);

-- ============================================================================
-- changelog: internal versioned migration log
-- ============================================================================
CREATE TABLE IF NOT EXISTS changelog (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT NOT NULL,
    description     TEXT
);
"""


# =============================================================================
# === Connection management                                                   ===
# =============================================================================

_local = threading.local()


def _connect() -> sqlite3.Connection:
    """Create a new SQLite connection.  One per thread."""
    conn = sqlite3.connect(
        str(config.DB_PATH),
        timeout=30.0,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-65536;")  # 64MB cache
    return conn


def get_conn() -> sqlite3.Connection:
    """Get the thread-local connection, opening one if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _connect()
    return _local.conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success, rolls back on exception."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_all() -> None:
    """Close all connections on the current thread."""
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None


# =============================================================================
# === Initialization                                                          ===
# =============================================================================

def open_db() -> None:
    """Open the database and apply the schema.  Idempotent."""
    conn = get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    _record_schema_version(conn)
    _seed_defaults(conn)
    _run_migrations(conn)
    conn.commit()


def _record_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO changelog(version, applied_at, description) "
        "VALUES (?, ?, ?)",
        (SCHEMA_VERSION, _now_iso(), "Initial schema"),
    )


def _seed_defaults(conn: sqlite3.Connection) -> None:
    """Seed default categories, default goal, first_run flag."""
    cur = conn.execute("SELECT COUNT(*) AS c FROM categories")
    row = cur.fetchone()
    if row and row["c"] > 0:
        return

    now = _now_iso()
    for cat in config.DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT INTO categories(key, name_en, name_fa, color, icon, "
            "order_index, archived, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cat["key"], cat["name_en"], cat["name_fa"], cat["color"],
             cat["icon"], cat["order_index"], cat["archived"], now, now),
        )

    # Default daily goal: 120 minutes, no specific category
    conn.execute(
        "INSERT INTO goals(period, category_id, target_minutes, active, "
        "created_at, updated_at) VALUES (?, NULL, ?, 1, ?, ?)",
        ("daily", config.DEFAULT_GOAL_MINUTES, now, now),
    )

    # Default settings
    defaults: list[tuple[str, str, str]] = [
        ("lang", config.DEFAULT_LANG, "string"),
        ("theme", config.DEFAULT_THEME, "string"),
        ("font_scale", str(config.DEFAULT_FONT_SCALE), "float"),
        ("reduced_motion", str(int(config.DEFAULT_REDUCED_MOTION)), "bool"),
        ("high_contrast", str(int(config.DEFAULT_HIGH_CONTRAST)), "bool"),
        ("lock_mode", "none", "string"),
        ("auto_lock_seconds", "0", "int"),
        ("first_day_of_week", "6", "int"),  # Saturday=6
        ("time_format", "24", "string"),
        ("date_format", "short", "string"),
        ("calendar_system", "jalali", "string"),
        ("notify_sound", str(int(config.NOTIFY_SOUND_DEFAULT)), "bool"),
        ("notify_vibrate", str(int(config.NOTIFY_VIBRATE_DEFAULT)), "bool"),
        ("auto_backup", "off", "string"),
        ("developer_mode", "0", "bool"),
    ]
    for key, value, kind in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, type, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (key, value, kind, now),
        )

    # Default kv entries
    kv_defaults = [
        ("first_run", "1"),
        ("onboarded", "0"),
        ("app_version", config.APP_VERSION),
        ("app_build", str(config.APP_BUILD)),
        ("total_launches", "0"),
        ("last_launch_iso", now),
        ("active_timer", ""),
        ("active_session_id", ""),
    ]
    for key, value in kv_defaults:
        conn.execute(
            "INSERT OR IGNORE INTO kv(key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply incremental migrations.  Currently a no-op placeholder."""
    # Future migrations will be applied here based on changelog.version.
    pass


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _now_iso() -> str:
    """ISO8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [{k: r[k] for k in r.keys()} for r in rows]


def _json_loads(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _json_dumps(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return "[]"


# =============================================================================
# === Activity repository                                                     ===
# =============================================================================

def activity_add(
    title: str,
    category_id: Optional[int],
    duration_min: int,
    date_iso: str,
    *,
    jalali_iso: Optional[str] = None,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list[str]] = None,
    kind: str = "manual",
    source: str = "desktop",
    template_id: Optional[int] = None,
    recurring_id: Optional[int] = None,
) -> int:
    """Insert a new activity.  Returns the new row id."""
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO activities("
        "title, category_id, duration_min, date_iso, jalali_iso, "
        "start_ts, end_ts, notes, tags_json, kind, source, "
        "template_id, recurring_id, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, category_id, duration_min, date_iso, jalali_iso,
         start_ts, end_ts, notes, _json_dumps(tags or []),
         kind, source, template_id, recurring_id, now, now),
    )
    activity_id = cur.lastrowid or 0
    # Update tag table + activity_tags
    if tags:
        _sync_activity_tags(activity_id, tags)
    # Increment template use count
    if template_id:
        conn.execute(
            "UPDATE templates SET use_count = use_count + 1, "
            "last_used_iso = ? WHERE id = ?",
            (now, template_id),
        )
    conn.commit()
    return activity_id


def activity_update(activity_id: int, **fields) -> bool:
    """Update an activity.  Returns True if a row was updated."""
    if not fields:
        return False
    # Whitelist columns
    allowed = {
        "title", "category_id", "duration_min", "date_iso", "jalali_iso",
        "start_ts", "end_ts", "notes", "tags_json", "kind", "source",
        "template_id", "recurring_id", "deleted_at",
    }
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "tags" and isinstance(v, list):
            updates.append("tags_json = ?")
            values.append(_json_dumps(v))
            _sync_activity_tags(activity_id, v)
        else:
            updates.append(f"{k} = ?")
            values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(activity_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE activities SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def activity_delete(activity_id: int, *, soft: bool = True) -> bool:
    """Delete an activity.  Soft-delete by default."""
    conn = get_conn()
    if soft:
        cur = conn.execute(
            "UPDATE activities SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (_now_iso(), _now_iso(), activity_id),
        )
    else:
        cur = conn.execute(
            "DELETE FROM activities WHERE id = ?",
            (activity_id,),
        )
    conn.commit()
    return (cur.rowcount or 0) > 0


def activity_get(activity_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM activities WHERE id = ? AND deleted_at IS NULL",
        (activity_id,),
    )
    return _row_to_dict(cur.fetchone())


def activity_list(
    *,
    limit: int = 100,
    offset: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_ids: Optional[list[int]] = None,
    kinds: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    search: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
    include_deleted: bool = False,
    order_by: str = "date_iso DESC, created_at DESC",
) -> list[dict]:
    """List activities with optional filters.  Returns dicts."""
    sql = ["SELECT a.* FROM activities a"]
    where: list[str] = []
    args: list[Any] = []
    if not include_deleted:
        where.append("a.deleted_at IS NULL")
    if date_from:
        where.append("a.date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("a.date_iso <= ?")
        args.append(date_to)
    if category_ids:
        ph = ",".join("?" * len(category_ids))
        where.append(f"a.category_id IN ({ph})")
        args.extend(category_ids)
    if kinds:
        ph = ",".join("?" * len(kinds))
        where.append(f"a.kind IN ({ph})")
        args.extend(kinds)
    if min_duration is not None:
        where.append("a.duration_min >= ?")
        args.append(min_duration)
    if max_duration is not None:
        where.append("a.duration_min <= ?")
        args.append(max_duration)
    if search:
        where.append("(a.title LIKE ? OR a.notes LIKE ?)")
        args.extend([f"%{search}%", f"%{search}%"])
    if tags:
        # Subquery: activities that have ALL the given tags
        ph = ",".join("?" * len(tags))
        where.append(
            f"a.id IN (SELECT at.activity_id FROM activity_tags at "
            f"JOIN tags t ON at.tag_id = t.id "
            f"WHERE t.name IN ({ph}) "
            f"GROUP BY at.activity_id HAVING COUNT(DISTINCT t.name) = ?)"
        )
        args.extend(tags)
        args.append(len(tags))
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append(f"ORDER BY a.{order_by}")
    sql.append("LIMIT ? OFFSET ?")
    args.extend([limit, offset])
    cur = get_conn().execute(" ".join(sql), args)
    rows = cur.fetchall()
    out = _rows_to_dicts(rows)
    # Hydrate tags_json
    for a in out:
        a["tags"] = _json_loads(a.get("tags_json"), [])
    return out


def activity_count(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_ids: Optional[list[int]] = None,
    include_deleted: bool = False,
) -> int:
    where: list[str] = []
    args: list[Any] = []
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    if category_ids:
        ph = ",".join("?" * len(category_ids))
        where.append(f"category_id IN ({ph})")
        args.extend(category_ids)
    sql = "SELECT COUNT(*) AS c FROM activities"
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur = get_conn().execute(sql, args)
    row = cur.fetchone()
    return int(row["c"]) if row else 0


def activity_sum_duration(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> int:
    """Return total minutes in the given range."""
    where = ["deleted_at IS NULL"]
    args: list[Any] = []
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    if category_id is not None:
        where.append("category_id = ?")
        args.append(category_id)
    sql = f"SELECT COALESCE(SUM(duration_min), 0) AS s FROM activities WHERE {' AND '.join(where)}"
    cur = get_conn().execute(sql, args)
    row = cur.fetchone()
    return int(row["s"]) if row else 0


def activity_group_by_day(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> list[dict]:
    """Return [{date_iso, count, total_min}] per day."""
    where = ["deleted_at IS NULL"]
    args: list[Any] = []
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    if category_id is not None:
        where.append("category_id = ?")
        args.append(category_id)
    sql = (
        f"SELECT date_iso, COUNT(*) AS count, SUM(duration_min) AS total_min "
        f"FROM activities WHERE {' AND '.join(where)} "
        f"GROUP BY date_iso ORDER BY date_iso ASC"
    )
    cur = get_conn().execute(sql, args)
    return [
        {"date_iso": r["date_iso"], "count": int(r["count"]),
         "total_min": int(r["total_min"] or 0)}
        for r in cur.fetchall()
    ]


def activity_group_by_category(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Return [{category_id, count, total_min}] per category."""
    where = ["a.deleted_at IS NULL"]
    args: list[Any] = []
    if date_from:
        where.append("a.date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("a.date_iso <= ?")
        args.append(date_to)
    sql = (
        f"SELECT a.category_id, COUNT(*) AS count, SUM(a.duration_min) AS total_min "
        f"FROM activities a WHERE {' AND '.join(where)} "
        f"GROUP BY a.category_id ORDER BY total_min DESC"
    )
    cur = get_conn().execute(sql, args)
    return [
        {"category_id": r["category_id"], "count": int(r["count"]),
         "total_min": int(r["total_min"] or 0)}
        for r in cur.fetchall()
    ]


def activity_group_by_hour(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Return [{hour, count, total_min}] per hour-of-day 0..23."""
    where = ["deleted_at IS NULL", "start_ts IS NOT NULL"]
    args: list[Any] = []
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    sql = (
        f"SELECT CAST(strftime('%H', start_ts) AS INTEGER) AS hour, "
        f"COUNT(*) AS count, SUM(duration_min) AS total_min "
        f"FROM activities WHERE {' AND '.join(where)} "
        f"GROUP BY hour ORDER BY hour ASC"
    )
    cur = get_conn().execute(sql, args)
    return [
        {"hour": int(r["hour"]), "count": int(r["count"]),
         "total_min": int(r["total_min"] or 0)}
        for r in cur.fetchall()
    ]


def activity_group_by_weekday(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Return [{weekday, count, total_min}] per weekday 0=Mon..6=Sun."""
    where = ["deleted_at IS NULL"]
    args: list[Any] = []
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    sql = (
        f"SELECT CAST(strftime('%w', date_iso) AS INTEGER) AS weekday, "
        f"COUNT(*) AS count, SUM(duration_min) AS total_min "
        f"FROM activities WHERE {' AND '.join(where)} "
        f"GROUP BY weekday ORDER BY weekday ASC"
    )
    cur = get_conn().execute(sql, args)
    return [
        {"weekday": int(r["weekday"]), "count": int(r["count"]),
         "total_min": int(r["total_min"] or 0)}
        for r in cur.fetchall()
    ]


def activity_group_by_month(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Return [{month, count, total_min}] per YYYY-MM."""
    where = ["deleted_at IS NULL"]
    args: list[Any] = []
    if date_from:
        where.append("date_iso >= ?")
        args.append(date_from)
    if date_to:
        where.append("date_iso <= ?")
        args.append(date_to)
    sql = (
        f"SELECT strftime('%Y-%m', date_iso) AS month, "
        f"COUNT(*) AS count, SUM(duration_min) AS total_min "
        f"FROM activities WHERE {' AND '.join(where)} "
        f"GROUP BY month ORDER BY month ASC"
    )
    cur = get_conn().execute(sql, args)
    return [
        {"month": r["month"], "count": int(r["count"]),
         "total_min": int(r["total_min"] or 0)}
        for r in cur.fetchall()
    ]


def _sync_activity_tags(activity_id: int, tags: list[str]) -> None:
    conn = get_conn()
    now = _now_iso()
    # Remove existing joins
    conn.execute("DELETE FROM activity_tags WHERE activity_id = ?", (activity_id,))
    for tag_name in tags:
        tag_name = tag_name.strip()
        if not tag_name:
            continue
        # Upsert tag
        conn.execute(
            "INSERT INTO tags(name, color, use_count, created_at) "
            "VALUES (?, NULL, 1, ?) "
            "ON CONFLICT(name) DO UPDATE SET use_count = use_count + 1",
            (tag_name, now),
        )
        cur = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "INSERT OR IGNORE INTO activity_tags(activity_id, tag_id) "
                "VALUES (?, ?)",
                (activity_id, row["id"]),
            )


# =============================================================================
# === Category repository                                                     ===
# =============================================================================

def category_add(key: str, name_en: str, name_fa: str, color: str,
                  icon: str = "ring", order_index: int = 0) -> int:
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO categories(key, name_en, name_fa, color, icon, "
        "order_index, archived, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (key, name_en, name_fa, color, icon, order_index, now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def category_update(category_id: int, **fields) -> bool:
    allowed = {"key", "name_en", "name_fa", "color", "icon",
               "order_index", "archived"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        updates.append(f"{k} = ?")
        values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(category_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE categories SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def category_delete(category_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def category_get(category_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM categories WHERE id = ?", (category_id,),
    )
    return _row_to_dict(cur.fetchone())


def category_get_by_key(key: str) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM categories WHERE key = ?", (key,),
    )
    return _row_to_dict(cur.fetchone())


def category_list(*, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM categories"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY order_index ASC, id ASC"
    cur = get_conn().execute(sql)
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === Goal repository                                                          ===
# =============================================================================

def goal_add(period: str, target_minutes: int,
              category_id: Optional[int] = None,
              title: Optional[str] = None, color: Optional[str] = None,
              reminder_enabled: bool = False,
              reminder_time: Optional[str] = None) -> int:
    assert period in ("daily", "weekly", "monthly"), f"bad period: {period}"
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO goals(period, category_id, target_minutes, active, "
        "title, color, reminder_enabled, reminder_time, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
        (period, category_id, target_minutes, title, color,
         int(reminder_enabled), reminder_time, now, now),
    )
    goal_id = cur.lastrowid or 0
    # Initialize streak row
    conn.execute(
        "INSERT INTO streaks(goal_id, current, best, history_json, updated_at) "
        "VALUES (?, 0, 0, '[]', ?)",
        (goal_id, now),
    )
    conn.commit()
    return goal_id


def goal_update(goal_id: int, **fields) -> bool:
    allowed = {"period", "category_id", "target_minutes", "active",
               "title", "color", "reminder_enabled", "reminder_time"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "reminder_enabled":
            v = int(bool(v))
        updates.append(f"{k} = ?")
        values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(goal_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE goals SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def goal_delete(goal_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def goal_get(goal_id: int) -> Optional[dict]:
    cur = get_conn().execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
    return _row_to_dict(cur.fetchone())


def goal_list(*, only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM goals"
    if only_active:
        sql += " WHERE active = 1"
    sql += " ORDER BY created_at ASC"
    cur = get_conn().execute(sql)
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === Streak repository                                                       ===
# =============================================================================

def streak_get(goal_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM streaks WHERE goal_id = ?", (goal_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = _row_to_dict(row) or {}
    d["history"] = _json_loads(d.get("history_json"), [])
    return d


def streak_update(goal_id: int, *, current: Optional[int] = None,
                   best: Optional[int] = None,
                   last_hit_iso: Optional[str] = None,
                   history: Optional[list[str]] = None) -> bool:
    updates = []
    values: list[Any] = []
    if current is not None:
        updates.append("current = ?")
        values.append(current)
    if best is not None:
        updates.append("best = ?")
        values.append(best)
    if last_hit_iso is not None:
        updates.append("last_hit_iso = ?")
        values.append(last_hit_iso)
    if history is not None:
        updates.append("history_json = ?")
        values.append(_json_dumps(history))
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(goal_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE streaks SET {', '.join(updates)} WHERE goal_id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def streak_increment(goal_id: int, hit_iso: str) -> dict:
    """Increment streak for goal.  Returns the updated streak dict."""
    s = streak_get(goal_id) or {}
    current = int(s.get("current", 0)) + 1
    best = max(int(s.get("best", 0)), current)
    history = list(s.get("history", []))
    history.append(hit_iso)
    # Keep only the most recent 365 entries
    history = history[-365:]
    streak_update(
        goal_id, current=current, best=best,
        last_hit_iso=hit_iso, history=history,
    )
    return {"current": current, "best": best, "history": history,
            "last_hit_iso": hit_iso}


def streak_reset(goal_id: int, *, zero_out: bool = True) -> bool:
    """Reset the current streak (typically after a missed day)."""
    return streak_update(
        goal_id,
        current=0 if zero_out else None,
        last_hit_iso=None if zero_out else None,
    )


# =============================================================================
# === Template repository                                                     ===
# =============================================================================

def template_add(name: str, title: str,
                  category_id: Optional[int] = None,
                  duration_min: Optional[int] = None,
                  tags: Optional[list[str]] = None,
                  notes: Optional[str] = None,
                  shortcut: Optional[str] = None,
                  icon: Optional[str] = None,
                  color: Optional[str] = None,
                  order_index: int = 0) -> int:
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO templates(name, title, category_id, duration_min, "
        "tags_json, notes, shortcut, icon, color, use_count, last_used_iso, "
        "order_index, archived, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, 0, ?, ?)",
        (name, title, category_id, duration_min, _json_dumps(tags or []),
         notes, shortcut, icon, color, order_index, now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def template_update(template_id: int, **fields) -> bool:
    allowed = {"name", "title", "category_id", "duration_min", "tags",
               "notes", "shortcut", "icon", "color", "order_index",
               "archived"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "tags" and isinstance(v, list):
            updates.append("tags_json = ?")
            values.append(_json_dumps(v))
        else:
            updates.append(f"{k} = ?")
            values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(template_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE templates SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def template_delete(template_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def template_get(template_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM templates WHERE id = ?", (template_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = _row_to_dict(row) or {}
    d["tags"] = _json_loads(d.get("tags_json"), [])
    return d


def template_list(*, include_archived: bool = False,
                   order_by: str = "use_count DESC, order_index ASC") -> list[dict]:
    sql = "SELECT * FROM templates"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += f" ORDER BY {order_by}"
    cur = get_conn().execute(sql)
    out = []
    for r in cur.fetchall():
        d = {k: r[k] for k in r.keys()}
        d["tags"] = _json_loads(d.get("tags_json"), [])
        out.append(d)
    return out


# =============================================================================
# === Badge repository                                                        ===
# =============================================================================

def badge_add(key: str, name_en: str, name_fa: str,
               desc_en: str, desc_fa: str, icon: str, tier: str,
               metadata: Optional[dict] = None) -> int:
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO badges(key, name_en, name_fa, desc_en, desc_fa, "
        "icon, tier, earned_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, name_en, name_fa, desc_en, desc_fa, icon, tier, now,
         _json_dumps(metadata or {})),
    )
    conn.commit()
    return cur.lastrowid or 0


def badge_get_by_key(key: str) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM badges WHERE key = ?", (key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = _row_to_dict(row) or {}
    d["metadata"] = _json_loads(d.get("metadata_json"), {})
    return d


def badge_list() -> list[dict]:
    cur = get_conn().execute(
        "SELECT * FROM badges ORDER BY earned_at DESC",
    )
    out = []
    for r in cur.fetchall():
        d = {k: r[k] for k in r.keys()}
        d["metadata"] = _json_loads(d.get("metadata_json"), {})
        out.append(d)
    return out


def badge_has(key: str) -> bool:
    cur = get_conn().execute(
        "SELECT 1 FROM badges WHERE key = ? LIMIT 1", (key,),
    )
    return cur.fetchone() is not None


def badge_delete(key: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM badges WHERE key = ?", (key,))
    conn.commit()
    return (cur.rowcount or 0) > 0


# =============================================================================
# === Reminder repository                                                     ===
# =============================================================================

def reminder_add(title: str, time_hhmm: str,
                  message: Optional[str] = None,
                  days_mask: int = 127,
                  category_id: Optional[int] = None,
                  goal_id: Optional[int] = None,
                  enabled: bool = True,
                  sound: bool = True) -> int:
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO reminders(title, message, time_hhmm, days_mask, "
        "category_id, goal_id, enabled, last_fired_iso, snooze_until, sound, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
        (title, message, time_hhmm, days_mask, category_id, goal_id,
         int(enabled), int(sound), now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def reminder_update(reminder_id: int, **fields) -> bool:
    allowed = {"title", "message", "time_hhmm", "days_mask", "category_id",
               "goal_id", "enabled", "last_fired_iso", "snooze_until",
               "sound"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("enabled", "sound"):
            v = int(bool(v))
        updates.append(f"{k} = ?")
        values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(reminder_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE reminders SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def reminder_delete(reminder_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def reminder_list(*, only_enabled: bool = False) -> list[dict]:
    sql = "SELECT * FROM reminders"
    if only_enabled:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY time_hhmm ASC"
    cur = get_conn().execute(sql)
    return _rows_to_dicts(cur.fetchall())


def reminder_get(reminder_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM reminders WHERE id = ?", (reminder_id,),
    )
    return _row_to_dict(cur.fetchone())


# =============================================================================
# === Recurring repository                                                    ===
# =============================================================================

def recurring_add(title: str, duration_min: int,
                   frequency: str,
                   category_id: Optional[int] = None,
                   days_mask: int = 127,
                   time_hhmm: Optional[str] = None,
                   end_date_iso: Optional[str] = None,
                   next_run_iso: Optional[str] = None,
                   notes: Optional[str] = None) -> int:
    assert frequency in ("daily", "weekly", "monthly"), f"bad frequency: {frequency}"
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO recurring(title, category_id, duration_min, frequency, "
        "days_mask, time_hhmm, end_date_iso, next_run_iso, last_run_iso, "
        "active, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?, ?)",
        (title, category_id, duration_min, frequency, days_mask, time_hhmm,
         end_date_iso, next_run_iso, notes, now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def recurring_update(recurring_id: int, **fields) -> bool:
    allowed = {"title", "category_id", "duration_min", "frequency",
               "days_mask", "time_hhmm", "end_date_iso", "next_run_iso",
               "last_run_iso", "active", "notes"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        updates.append(f"{k} = ?")
        values.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    values.append(_now_iso())
    values.append(recurring_id)
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE recurring SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def recurring_delete(recurring_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM recurring WHERE id = ?", (recurring_id,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def recurring_list(*, only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM recurring"
    if only_active:
        sql += " WHERE active = 1"
    sql += " ORDER BY next_run_iso ASC NULLS LAST"
    cur = get_conn().execute(sql)
    return _rows_to_dicts(cur.fetchall())


def recurring_due_now(now_iso: Optional[str] = None) -> list[dict]:
    """Return recurring rules that are due now or in the past."""
    now_iso = now_iso or _now_iso()
    cur = get_conn().execute(
        "SELECT * FROM recurring WHERE active = 1 "
        "AND (next_run_iso IS NULL OR next_run_iso <= ?) "
        "AND (end_date_iso IS NULL OR end_date_iso >= date(?)) "
        "ORDER BY next_run_iso ASC",
        (now_iso, now_iso[:10]),
    )
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === Session repository                                                      ===
# =============================================================================

def session_add(planned_min: int, started_at: Optional[str] = None,
                 activity_id: Optional[int] = None,
                 metadata: Optional[dict] = None) -> int:
    now = _now_iso()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sessions(activity_id, planned_min, actual_min, "
        "started_at, ended_at, state, pause_count, pause_total_sec, "
        "metadata_json) VALUES (?, ?, NULL, ?, NULL, 'running', 0, 0, ?)",
        (activity_id, planned_min, started_at or now,
         _json_dumps(metadata or {})),
    )
    conn.commit()
    return cur.lastrowid or 0


def session_update(session_id: int, **fields) -> bool:
    allowed = {"activity_id", "planned_min", "actual_min", "started_at",
               "ended_at", "state", "pause_count", "pause_total_sec",
               "metadata"}
    updates = []
    values: list[Any] = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "metadata" and isinstance(v, dict):
            updates.append("metadata_json = ?")
            values.append(_json_dumps(v))
        else:
            updates.append(f"{k} = ?")
            values.append(v)
    if not updates:
        return False
    conn = get_conn()
    cur = conn.execute(
        f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
        values + [session_id],
    )
    conn.commit()
    return (cur.rowcount or 0) > 0


def session_get(session_id: int) -> Optional[dict]:
    cur = get_conn().execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = _row_to_dict(row) or {}
    d["metadata"] = _json_loads(d.get("metadata_json"), {})
    return d


def session_list_active() -> list[dict]:
    cur = get_conn().execute(
        "SELECT * FROM sessions WHERE state IN ('running','paused') "
        "ORDER BY started_at DESC",
    )
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === Tag repository                                                          ===
# =============================================================================

def tag_list(*, min_count: int = 1, limit: int = 200) -> list[dict]:
    cur = get_conn().execute(
        "SELECT * FROM tags WHERE use_count >= ? "
        "ORDER BY use_count DESC, name ASC LIMIT ?",
        (min_count, limit),
    )
    return _rows_to_dicts(cur.fetchall())


def tag_search(query: str, limit: int = 10) -> list[dict]:
    cur = get_conn().execute(
        "SELECT * FROM tags WHERE name LIKE ? "
        "ORDER BY use_count DESC LIMIT ?",
        (f"%{query}%", limit),
    )
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === KV store                                                                ===
# =============================================================================

def kv_get(key: str, default: Optional[str] = None) -> Optional[str]:
    cur = get_conn().execute("SELECT value FROM kv WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def kv_set(key: str, value: str) -> None:
    now = _now_iso()
    conn = get_conn()
    conn.execute(
        "INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value, now),
    )
    conn.commit()


def kv_get_int(key: str, default: int = 0) -> int:
    v = kv_get(key)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def kv_set_int(key: str, value: int) -> None:
    kv_set(key, str(value))


def kv_get_bool(key: str, default: bool = False) -> bool:
    v = kv_get(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def kv_set_bool(key: str, value: bool) -> None:
    kv_set(key, "1" if value else "0")


def kv_get_json(key: str, default: Any = None) -> Any:
    v = kv_get(key)
    if v is None:
        return default
    return _json_loads(v, default)


def kv_set_json(key: str, value: Any) -> None:
    kv_set(key, _json_dumps(value))


def kv_delete(key: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM kv WHERE key = ?", (key,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def kv_keys(prefix: str = "") -> list[str]:
    if prefix:
        cur = get_conn().execute(
            "SELECT key FROM kv WHERE key LIKE ? ORDER BY key ASC",
            (f"{prefix}%",),
        )
    else:
        cur = get_conn().execute("SELECT key FROM kv ORDER BY key ASC")
    return [r["key"] for r in cur.fetchall()]


# =============================================================================
# === Settings store (typed)                                                  ===
# =============================================================================

def setting_get(key: str, default: Any = None) -> Any:
    cur = get_conn().execute(
        "SELECT value, type FROM settings WHERE key = ?", (key,),
    )
    row = cur.fetchone()
    if not row:
        return default
    v = row["value"]
    t = row["type"]
    if t == "int":
        try:
            return int(v)
        except Exception:
            return default
    if t == "float":
        try:
            return float(v)
        except Exception:
            return default
    if t == "bool":
        return v.lower() in ("1", "true", "yes", "on")
    if t == "json":
        return _json_loads(v, default)
    return v


def setting_set(key: str, value: Any, type_: Optional[str] = None) -> None:
    if type_ is None:
        if isinstance(value, bool):
            type_ = "bool"
            v = "1" if value else "0"
        elif isinstance(value, int):
            type_ = "int"
            v = str(value)
        elif isinstance(value, float):
            type_ = "float"
            v = str(value)
        elif isinstance(value, (dict, list)):
            type_ = "json"
            v = _json_dumps(value)
        else:
            type_ = "string"
            v = str(value)
    else:
        if type_ == "bool":
            v = "1" if value else "0"
        elif type_ == "int":
            v = str(int(value))
        elif type_ == "float":
            v = str(float(value))
        elif type_ == "json":
            v = _json_dumps(value)
        else:
            v = str(value)
    now = _now_iso()
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key, value, type, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "type = excluded.type, updated_at = excluded.updated_at",
        (key, v, type_, now),
    )
    conn.commit()


def setting_delete(key: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.commit()
    return (cur.rowcount or 0) > 0


def setting_list() -> list[dict]:
    cur = get_conn().execute(
        "SELECT key, value, type, updated_at FROM settings ORDER BY key ASC",
    )
    return _rows_to_dicts(cur.fetchall())


# =============================================================================
# === Audit log helpers                                                       ===
# =============================================================================

def log_backup(kind: str, file_path: Optional[str], file_size: Optional[int],
                success: bool, error_message: Optional[str] = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO backups_log(kind, file_path, file_size, success, "
        "error_message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (kind, file_path, file_size, int(success), error_message, _now_iso()),
    )
    conn.commit()


def log_export(kind: str, file_path: Optional[str], file_size: Optional[int],
                record_count: Optional[int], success: bool,
                error_message: Optional[str] = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO exports_log(kind, file_path, file_size, record_count, "
        "success, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kind, file_path, file_size, record_count, int(success),
         error_message, _now_iso()),
    )
    conn.commit()


# =============================================================================
# === Backup / restore (raw SQL dump)                                         ===
# =============================================================================

def export_to_dict() -> dict:
    """Export the entire database as a JSON-serializable dict.

    This is the in-memory representation that gets encrypted by the
    backup service before being written to disk.
    """
    conn = get_conn()
    tables = [
        "activities", "categories", "goals", "streaks", "templates",
        "badges", "reminders", "kv", "tags", "activity_tags",
        "recurring", "sessions", "settings",
    ]
    out: dict[str, Any] = {
        "meta": {
            "app": config.APP_NAME,
            "version": config.APP_VERSION,
            "build": config.APP_BUILD,
            "schema_version": SCHEMA_VERSION,
            "exported_at": _now_iso(),
        },
        "data": {},
    }
    for t in tables:
        cur = conn.execute(f"SELECT * FROM {t}")
        out["data"][t] = _rows_to_dicts(cur.fetchall())
    return out


def import_from_dict(data: dict, *, replace: bool = True) -> None:
    """Import a previously exported dict.

    If `replace` is True, the existing tables are wiped first.
    """
    conn = get_conn()
    if replace:
        # Wipe in FK-safe order
        for t in ("activity_tags", "tags", "activities", "sessions",
                  "recurring", "reminders", "badges", "templates",
                  "streaks", "goals", "categories", "settings", "kv"):
            conn.execute(f"DELETE FROM {t}")
    data = data.get("data", data)
    # Insert in FK-safe order
    insert_order = [
        "categories", "kv", "settings", "goals", "streaks", "templates",
        "badges", "reminders", "recurring", "sessions",
        "tags", "activities", "activity_tags",
    ]
    for t in insert_order:
        if t not in data:
            continue
        rows = data[t]
        if not rows:
            continue
        cols = list(rows[0].keys())
        ph = ",".join("?" * len(cols))
        colnames = ",".join(cols)
        for row in rows:
            conn.execute(
                f"INSERT OR REPLACE INTO {t}({colnames}) VALUES ({ph})",
                [row.get(c) for c in cols],
            )
    conn.commit()


# =============================================================================
# === Maintenance                                                            ===
# =============================================================================

def vacuum() -> None:
    """Vacuum the database to reclaim space."""
    get_conn().execute("VACUUM")


def integrity_check() -> list[str]:
    cur = get_conn().execute("PRAGMA integrity_check")
    return [r[0] for r in cur.fetchall()]


def db_file_size() -> int:
    p = Path(config.DB_PATH)
    return p.stat().st_size if p.exists() else 0


def stats() -> dict:
    """Return table row counts for diagnostics."""
    tables = [
        "activities", "categories", "goals", "streaks", "templates",
        "badges", "reminders", "kv", "tags", "activity_tags",
        "recurring", "sessions", "settings",
    ]
    out: dict[str, int] = {}
    for t in tables:
        cur = get_conn().execute(f"SELECT COUNT(*) AS c FROM {t}")
        row = cur.fetchone()
        out[t] = int(row["c"]) if row else 0
    out["_db_size_bytes"] = db_file_size()
    return out


__all__ = [
    # Connection
    "open_db", "get_conn", "transaction", "close_all",
    "SCHEMA_VERSION", "SCHEMA_SQL",
    # Activities
    "activity_add", "activity_update", "activity_delete", "activity_get",
    "activity_list", "activity_count", "activity_sum_duration",
    "activity_group_by_day", "activity_group_by_category",
    "activity_group_by_hour", "activity_group_by_weekday",
    "activity_group_by_month",
    # Categories
    "category_add", "category_update", "category_delete",
    "category_get", "category_get_by_key", "category_list",
    # Goals
    "goal_add", "goal_update", "goal_delete", "goal_get", "goal_list",
    # Streaks
    "streak_get", "streak_update", "streak_increment", "streak_reset",
    # Templates
    "template_add", "template_update", "template_delete",
    "template_get", "template_list",
    # Badges
    "badge_add", "badge_get_by_key", "badge_list", "badge_has", "badge_delete",
    # Reminders
    "reminder_add", "reminder_update", "reminder_delete",
    "reminder_list", "reminder_get",
    # Recurring
    "recurring_add", "recurring_update", "recurring_delete",
    "recurring_list", "recurring_due_now",
    # Sessions
    "session_add", "session_update", "session_get", "session_list_active",
    # Tags
    "tag_list", "tag_search",
    # KV
    "kv_get", "kv_set", "kv_get_int", "kv_set_int", "kv_get_bool",
    "kv_set_bool", "kv_get_json", "kv_set_json", "kv_delete", "kv_keys",
    # Settings
    "setting_get", "setting_set", "setting_delete", "setting_list",
    # Audit
    "log_backup", "log_export",
    # Backup
    "export_to_dict", "import_from_dict",
    # Maintenance
    "vacuum", "integrity_check", "db_file_size", "stats",
]
