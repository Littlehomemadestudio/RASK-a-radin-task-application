"""database.py — SQLite data layer for Rask (1:1 mirror of web/js/db.js).

Schema mirrors the IndexedDB stores in the web edition:
  - activities   (manual logs + stopwatch runs)
  - categories   (Focus/Learn/Work/Health/Creative/Social/Rest + custom)
  - goals        (daily/weekly/monthly targets, optionally per-category)
  - streaks      (per-goal current & longest streaks)
  - templates    (quick-log presets)
  - badges       (earned milestone badges)
  - kv           (key-value store: lang, first_run, lock_mode, pin_salt, etc.)
  - recurring    (recurring activity rules — desktop-only extension)

All functions are synchronous (SQLite is fast enough for our scale and the
desktop app calls them from the main Tk thread). The DB file lives at
config.DB_PATH.
"""
from __future__ import annotations
import json
import sqlite3
import threading
import time
import datetime as _dt
from pathlib import Path
from typing import Any, Iterable, Optional

from . import config
from .date_utils import today_iso, now_iso, start_of_week, end_of_week, start_of_month, end_of_month


# =====================================================================
# === CONNECTION MANAGEMENT ===
# =====================================================================
_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL DEFAULT '',
    category_id  INTEGER,
    kind         TEXT NOT NULL DEFAULT 'manual',  -- manual|stopwatch|template|recurring|voice
    date_iso     TEXT NOT NULL,                    -- YYYY-MM-DD
    start_iso    TEXT,                              -- YYYY-MM-DDTHH:MM:SS
    end_iso      TEXT,
    duration_sec INTEGER NOT NULL DEFAULT 0,
    note         TEXT NOT NULL DEFAULT '',
    template_id  INTEGER,
    voice_input  INTEGER NOT NULL DEFAULT 0,
    recurring_id INTEGER,
    created_at   TEXT NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_activities_date     ON activities(date_iso);
CREATE INDEX IF NOT EXISTS idx_activities_category ON activities(category_id);
CREATE INDEX IF NOT EXISTS idx_activities_kind     ON activities(kind);
CREATE INDEX IF NOT EXISTS idx_activities_created  ON activities(created_at);
CREATE INDEX IF NOT EXISTS idx_activities_archived ON activities(archived);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT UNIQUE NOT NULL,
    color       TEXT NOT NULL DEFAULT '#D4AF37',
    name_en     TEXT NOT NULL,
    name_fa     TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '',
    order_index INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    custom      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_categories_key ON categories(key);

CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL DEFAULT 'daily',  -- daily|weekly|monthly
    category_id     INTEGER,
    target_minutes  INTEGER NOT NULL DEFAULT 60,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    reminder_time   TEXT,
    reminder_enabled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_goals_active ON goals(active);

CREATE TABLE IF NOT EXISTS streaks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id       INTEGER NOT NULL UNIQUE,
    current       INTEGER NOT NULL DEFAULT 0,
    longest       INTEGER NOT NULL DEFAULT 0,
    last_hit_date TEXT,
    history       TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS templates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    category_id         INTEGER,
    default_duration_min INTEGER NOT NULL DEFAULT 30,
    icon                TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    color               TEXT
);

CREATE TABLE IF NOT EXISTS badges (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    key       TEXT UNIQUE NOT NULL,
    title_en  TEXT NOT NULL,
    title_fa  TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    meta      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_badges_key ON badges(key);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS recurring (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    category_id     INTEGER,
    pattern         TEXT NOT NULL,  -- daily|weekly|monthly|weekdays|weekends|custom
    custom_days     TEXT NOT NULL DEFAULT '[]',  -- [0..6] for weekly custom
    duration_sec    INTEGER NOT NULL DEFAULT 0,
    start_date_iso  TEXT NOT NULL,
    end_date_iso    TEXT,
    next_run_iso    TEXT NOT NULL,
    last_run_iso    TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    icon            TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_recurring_active ON recurring(active);
CREATE INDEX IF NOT EXISTS idx_recurring_next   ON recurring(next_run_iso);
"""


# =====================================================================
# === OPEN / INITIALIZE ===
# =====================================================================
def open_db() -> sqlite3.Connection:
    """Open (or create) the database and run schema migrations."""
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
        _seed_defaults()
        _migrate()
        return _conn


def close_db() -> None:
    """Close the database connection."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _seed_defaults() -> None:
    """Seed default categories, default goal, and first_run flag (mirror db.js seedDefaults)."""
    cur = _conn.execute("SELECT COUNT(*) AS n FROM categories")
    if cur.fetchone()["n"] > 0:
        # Ensure first_run KV exists even if categories were already seeded
        _conn.execute("INSERT OR IGNORE INTO kv(key, value) VALUES('first_run', '1')")
        _conn.commit()
        return
    for c in config.DEFAULT_CATEGORIES:
        _conn.execute(
            "INSERT INTO categories(key, color, name_en, name_fa, icon, order_index, archived, custom) "
            "VALUES(?, ?, ?, ?, ?, ?, 0, 0)",
            (c["key"], c["color"], c["name_en"], c["name_fa"], c["icon"], c["order_index"]),
        )
    # Default daily goal: 120 minutes
    _conn.execute(
        "INSERT INTO goals(period, category_id, target_minutes, active, created_at) "
        "VALUES('daily', NULL, ?, 1, ?)",
        (config.DEFAULT_DAILY_GOAL_MIN, now_iso()),
    )
    _conn.execute("INSERT OR IGNORE INTO kv(key, value) VALUES('first_run', '1')")
    _conn.commit()


def _migrate() -> None:
    """Run any forward-only migrations (add columns, etc.)."""
    # Future migrations go here. We check PRAGMA table_info for columns.
    pass


# =====================================================================
# === KV STORE (mirror db.js kvGet / kvSet / kvGetBool / kvGetJSON) ===
# =====================================================================
def kv_get(key: str, default: Any = None) -> Optional[str]:
    """Get a string value from the kv store."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def kv_set(key: str, value: Any) -> None:
    """Set a string value in the kv store."""
    with _lock:
        open_db()
        _conn.execute("INSERT INTO kv(key, value) VALUES(?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, str(value)))
        _conn.commit()


def kv_get_bool(key: str, default: bool = False) -> bool:
    """Get a boolean value from the kv store."""
    v = kv_get(key, "1" if default else "0")
    return v in ("1", "true", "True", "yes", "on")


def kv_set_bool(key: str, value: bool) -> None:
    kv_set(key, "1" if value else "0")


def kv_get_int(key: str, default: int = 0) -> int:
    """Get an integer value from the kv store."""
    v = kv_get(key)
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def kv_set_int(key: str, value: int) -> None:
    kv_set(key, str(value))


def kv_get_json(key: str, default: Any = None) -> Any:
    """Get a JSON-encoded value from the kv store."""
    v = kv_get(key)
    if v is None:
        return default
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return default


def kv_set_json(key: str, value: Any) -> None:
    kv_set(key, json.dumps(value, ensure_ascii=False))


def kv_delete(key: str) -> None:
    """Delete a key from the kv store."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM kv WHERE key=?", (key,))
        _conn.commit()


def kv_all() -> dict:
    """Return all KV pairs as a dict."""
    with _lock:
        open_db()
        rows = _conn.execute("SELECT key, value FROM kv").fetchall()
        return {r["key"]: r["value"] for r in rows}


# =====================================================================
# === ACTIVITIES (mirror db.js activities functions) ===
# =====================================================================
def insert_activity(a: dict) -> int:
    """Insert a new activity. Returns the new row id."""
    with _lock:
        open_db()
        if not a.get("created_at"):
            a["created_at"] = now_iso()
        if not a.get("date_iso"):
            a["date_iso"] = today_iso()
        cur = _conn.execute(
            "INSERT INTO activities(title, category_id, kind, date_iso, start_iso, end_iso, "
            "duration_sec, note, template_id, voice_input, recurring_id, created_at, archived) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                a.get("title", ""),
                a.get("category_id"),
                a.get("kind", "manual"),
                a["date_iso"],
                a.get("start_iso"),
                a.get("end_iso"),
                int(a.get("duration_sec", 0) or 0),
                a.get("note", ""),
                a.get("template_id"),
                int(bool(a.get("voice_input", 0))),
                a.get("recurring_id"),
                a["created_at"],
            ),
        )
        _conn.commit()
        return cur.lastrowid


def update_activity(a: dict) -> None:
    """Update an existing activity. Requires 'id'."""
    with _lock:
        open_db()
        _conn.execute(
            "UPDATE activities SET title=?, category_id=?, kind=?, date_iso=?, start_iso=?, "
            "end_iso=?, duration_sec=?, note=?, template_id=?, voice_input=?, archived=? "
            "WHERE id=?",
            (
                a.get("title", ""),
                a.get("category_id"),
                a.get("kind", "manual"),
                a.get("date_iso", today_iso()),
                a.get("start_iso"),
                a.get("end_iso"),
                int(a.get("duration_sec", 0) or 0),
                a.get("note", ""),
                a.get("template_id"),
                int(bool(a.get("voice_input", 0))),
                int(bool(a.get("archived", 0))),
                a["id"],
            ),
        )
        _conn.commit()


def delete_activity(activity_id: int) -> None:
    """Permanently delete an activity."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM activities WHERE id=?", (activity_id,))
        _conn.commit()


def archive_activity(activity_id: int, archived: bool = True) -> None:
    """Archive (or unarchive) an activity without deleting it."""
    with _lock:
        open_db()
        _conn.execute("UPDATE activities SET archived=? WHERE id=?",
                      (1 if archived else 0, activity_id,))
        _conn.commit()


def get_activity(activity_id: int) -> Optional[dict]:
    """Get a single activity by id."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
        return dict(row) if row else None


def all_activities(include_archived: bool = False) -> list[dict]:
    """Return all activities (newest first)."""
    with _lock:
        open_db()
        sql = "SELECT * FROM activities"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY created_at DESC"
        rows = _conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def recent_activities(limit: int = 20, include_archived: bool = False) -> list[dict]:
    """Return the most recent N activities."""
    with _lock:
        open_db()
        sql = "SELECT * FROM activities"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY created_at DESC LIMIT ?"
        rows = _conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


def activities_by_date_range(start_iso: str, end_iso: str,
                              category_id: Optional[int] = None,
                              include_archived: bool = False) -> list[dict]:
    """Return activities within a date range (inclusive)."""
    with _lock:
        open_db()
        sql = "SELECT * FROM activities WHERE date_iso >= ? AND date_iso <= ?"
        params = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        if not include_archived:
            sql += " AND archived=0"
        sql += " ORDER BY date_iso DESC, created_at DESC"
        rows = _conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def activities_by_date(date_iso: str, category_id: Optional[int] = None,
                       include_archived: bool = False) -> list[dict]:
    """Return all activities on a specific date."""
    with _lock:
        open_db()
        sql = "SELECT * FROM activities WHERE date_iso=?"
        params = [date_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        if not include_archived:
            sql += " AND archived=0"
        sql += " ORDER BY created_at DESC"
        rows = _conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def total_seconds_between(start_iso: str, end_iso: str,
                          category_id: Optional[int] = None,
                          include_archived: bool = False) -> int:
    """Return total seconds logged between two dates (inclusive)."""
    with _lock:
        open_db()
        sql = "SELECT COALESCE(SUM(duration_sec), 0) AS s FROM activities " \
              "WHERE date_iso >= ? AND date_iso <= ?"
        params = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        if not include_archived:
            sql += " AND archived=0"
        row = _conn.execute(sql, params).fetchone()
        return int(row["s"] or 0)


def total_seconds_on(date_iso: str, category_id: Optional[int] = None,
                     include_archived: bool = False) -> int:
    """Return total seconds logged on a specific date."""
    return total_seconds_between(date_iso, date_iso, category_id, include_archived)


def seconds_per_day(start_iso: str, end_iso: str,
                    category_id: Optional[int] = None) -> dict[str, int]:
    """Return {date_iso: seconds} for each day in the range."""
    with _lock:
        open_db()
        sql = "SELECT date_iso, SUM(duration_sec) AS s FROM activities " \
              "WHERE date_iso >= ? AND date_iso <= ? AND archived=0"
        params = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        sql += " GROUP BY date_iso"
        rows = _conn.execute(sql, params).fetchall()
        return {r["date_iso"]: int(r["s"] or 0) for r in rows}


def seconds_per_category(start_iso: str, end_iso: str) -> list[tuple[int, int]]:
    """Return [(category_id, seconds)] sorted by seconds descending."""
    with _lock:
        open_db()
        sql = "SELECT category_id, SUM(duration_sec) AS s FROM activities " \
              "WHERE date_iso >= ? AND date_iso <= ? AND archived=0 " \
              "GROUP BY category_id ORDER BY s DESC"
        rows = _conn.execute(sql, (start_iso, end_iso)).fetchall()
        return [(int(r["category_id"]) if r["category_id"] is not None else 0,
                 int(r["s"] or 0)) for r in rows]


def seconds_per_hour(date_iso: str) -> list[int]:
    """Return a 24-element list of seconds per hour for the given date."""
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT start_iso, created_at, duration_sec FROM activities "
            "WHERE date_iso=? AND archived=0",
            (date_iso,),
        ).fetchall()
        buckets = [0] * 24
        for r in rows:
            ts = r["start_iso"] or r["created_at"]
            if not ts:
                continue
            try:
                h = int(ts[11:13]) if len(ts) >= 13 else 0
                if 0 <= h < 24:
                    buckets[h] += int(r["duration_sec"] or 0)
            except (ValueError, IndexError):
                continue
        return buckets


def seconds_per_weekday(start_iso: str, end_iso: str) -> list[int]:
    """Return 7-element list of total seconds per weekday (Mon=0, Sun=6)."""
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT date_iso, SUM(duration_sec) AS s FROM activities "
            "WHERE date_iso >= ? AND date_iso <= ? AND archived=0 "
            "GROUP BY date_iso",
            (start_iso, end_iso),
        ).fetchall()
        buckets = [0] * 7
        for r in rows:
            try:
                d = _dt.date.fromisoformat(r["date_iso"])
                # Python weekday(): Mon=0, Sun=6 — matches our array
                buckets[d.weekday()] += int(r["s"] or 0)
            except (ValueError, IndexError):
                continue
        return buckets


def search_activities(query: str, limit: int = 50) -> list[dict]:
    """Full-text search in title and note."""
    with _lock:
        open_db()
        pattern = f"%{query}%"
        rows = _conn.execute(
            "SELECT * FROM activities WHERE archived=0 AND "
            "(title LIKE ? OR note LIKE ?) ORDER BY created_at DESC LIMIT ?",
            (pattern, pattern, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def count_activities(include_archived: bool = False) -> int:
    """Return total activity count."""
    with _lock:
        open_db()
        sql = "SELECT COUNT(*) AS n FROM activities"
        if not include_archived:
            sql += " WHERE archived=0"
        return int(_conn.execute(sql).fetchone()["n"])


def first_activity_date() -> Optional[str]:
    """Return ISO date of the first activity, or None."""
    with _lock:
        open_db()
        row = _conn.execute(
            "SELECT date_iso FROM activities WHERE archived=0 ORDER BY date_iso ASC LIMIT 1"
        ).fetchone()
        return row["date_iso"] if row else None


def last_activity_date() -> Optional[str]:
    """Return ISO date of the last activity, or None."""
    with _lock:
        open_db()
        row = _conn.execute(
            "SELECT date_iso FROM activities WHERE archived=0 ORDER BY date_iso DESC LIMIT 1"
        ).fetchone()
        return row["date_iso"] if row else None


def activity_duration_stats(start_iso: str, end_iso: str,
                            category_id: Optional[int] = None) -> dict:
    """Return min/max/mean/median/stdev of activity durations in the range."""
    with _lock:
        open_db()
        sql = "SELECT duration_sec FROM activities WHERE date_iso >= ? AND date_iso <= ? AND archived=0"
        params = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        rows = _conn.execute(sql, params).fetchall()
        durations = sorted(int(r["duration_sec"] or 0) for r in rows)
        n = len(durations)
        if n == 0:
            return {"count": 0, "total": 0, "min": 0, "max": 0, "mean": 0,
                    "median": 0, "p25": 0, "p75": 0, "p90": 0, "stdev": 0}
        total = sum(durations)
        mean = total / n
        median = durations[n // 2] if n % 2 else (durations[n // 2 - 1] + durations[n // 2]) / 2
        def _pct(p):
            idx = int(p * (n - 1))
            return durations[idx]
        variance = sum((d - mean) ** 2 for d in durations) / n
        stdev = variance ** 0.5
        return {
            "count": n,
            "total": total,
            "min": durations[0],
            "max": durations[-1],
            "mean": mean,
            "median": median,
            "p25": _pct(0.25),
            "p75": _pct(0.75),
            "p90": _pct(0.90),
            "stdev": stdev,
        }


# =====================================================================
# === CATEGORIES ===
# =====================================================================
def all_categories(include_archived: bool = False) -> list[dict]:
    """Return all categories sorted by order_index."""
    with _lock:
        open_db()
        sql = "SELECT * FROM categories"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY order_index ASC, id ASC"
        rows = _conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def category_by_id(category_id: Optional[int]) -> Optional[dict]:
    """Return a single category by id, or None."""
    if not category_id:
        return None
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        return dict(row) if row else None


def category_by_key(key: str) -> Optional[dict]:
    """Return a single category by its unique key, or None."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM categories WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None


def upsert_category(c: dict) -> int:
    """Insert or update a category. Returns the id."""
    with _lock:
        open_db()
        if c.get("id"):
            _conn.execute(
                "UPDATE categories SET key=?, color=?, name_en=?, name_fa=?, icon=?, "
                "order_index=?, archived=?, custom=? WHERE id=?",
                (
                    c["key"], c.get("color", "#D4AF37"), c["name_en"], c["name_fa"],
                    c.get("icon", ""), c.get("order_index", 0),
                    int(bool(c.get("archived", 0))), int(bool(c.get("custom", 0))),
                    c["id"],
                ),
            )
            _conn.commit()
            return c["id"]
        cur = _conn.execute(
            "INSERT INTO categories(key, color, name_en, name_fa, icon, order_index, archived, custom) "
            "VALUES(?, ?, ?, ?, ?, ?, 0, 1)",
            (
                c["key"], c.get("color", "#D4AF37"), c["name_en"], c["name_fa"],
                c.get("icon", ""), c.get("order_index", 99),
            ),
        )
        _conn.commit()
        return cur.lastrowid


def archive_category(category_id: int, archived: bool = True) -> None:
    """Archive or unarchive a category."""
    with _lock:
        open_db()
        _conn.execute("UPDATE categories SET archived=? WHERE id=?",
                      (1 if archived else 0, category_id))
        _conn.commit()


def delete_category(category_id: int) -> None:
    """Permanently delete a category. Activities are unlinked (category_id set to NULL)."""
    with _lock:
        open_db()
        _conn.execute("UPDATE activities SET category_id=NULL WHERE category_id=?", (category_id,))
        _conn.execute("UPDATE goals SET category_id=NULL WHERE category_id=?", (category_id,))
        _conn.execute("UPDATE templates SET category_id=NULL WHERE category_id=?", (category_id,))
        _conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
        _conn.commit()


# =====================================================================
# === GOALS ===
# =====================================================================
def all_goals(active_only: bool = False) -> list[dict]:
    """Return all goals."""
    with _lock:
        open_db()
        sql = "SELECT * FROM goals"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY created_at ASC, id ASC"
        rows = _conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def goal_by_id(goal_id: int) -> Optional[dict]:
    """Return a single goal by id."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        return dict(row) if row else None


def upsert_goal(g: dict) -> int:
    """Insert or update a goal. Returns the id."""
    with _lock:
        open_db()
        if not g.get("created_at"):
            g["created_at"] = now_iso()
        if g.get("id"):
            _conn.execute(
                "UPDATE goals SET period=?, category_id=?, target_minutes=?, active=?, "
                "name=?, reminder_time=?, reminder_enabled=? WHERE id=?",
                (
                    g.get("period", "daily"), g.get("category_id"),
                    int(g.get("target_minutes", 60)), int(bool(g.get("active", 1))),
                    g.get("name", ""), g.get("reminder_time"),
                    int(bool(g.get("reminder_enabled", 0))), g["id"],
                ),
            )
            _conn.commit()
            return g["id"]
        cur = _conn.execute(
            "INSERT INTO goals(period, category_id, target_minutes, active, created_at, "
            "name, reminder_time, reminder_enabled) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                g.get("period", "daily"), g.get("category_id"),
                int(g.get("target_minutes", 60)), int(bool(g.get("active", 1))),
                g["created_at"], g.get("name", ""), g.get("reminder_time"),
                int(bool(g.get("reminder_enabled", 0))),
            ),
        )
        _conn.commit()
        return cur.lastrowid


def delete_goal(goal_id: int) -> None:
    """Delete a goal and its streak."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM streaks WHERE goal_id=?", (goal_id,))
        _conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        _conn.commit()


# =====================================================================
# === STREAKS ===
# =====================================================================
def streak_for_goal(goal_id: int) -> Optional[dict]:
    """Return the streak record for a goal, or None."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM streaks WHERE goal_id=?", (goal_id,)).fetchone()
        return dict(row) if row else None


def upsert_streak(s: dict) -> int:
    """Insert or update a streak record."""
    with _lock:
        open_db()
        if s.get("id"):
            _conn.execute(
                "UPDATE streaks SET goal_id=?, current=?, longest=?, last_hit_date=?, history=? WHERE id=?",
                (s["goal_id"], int(s.get("current", 0)), int(s.get("longest", 0)),
                 s.get("last_hit_date"), s.get("history", "[]"), s["id"]),
            )
            _conn.commit()
            return s["id"]
        cur = _conn.execute(
            "INSERT INTO streaks(goal_id, current, longest, last_hit_date, history) "
            "VALUES(?, ?, ?, ?, ?)",
            (s["goal_id"], int(s.get("current", 0)), int(s.get("longest", 0)),
             s.get("last_hit_date"), s.get("history", "[]")),
        )
        _conn.commit()
        return cur.lastrowid


def top_streaks(limit: int = 10) -> list[dict]:
    """Return top N streaks sorted by longest."""
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT * FROM streaks ORDER BY longest DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def all_streaks() -> list[dict]:
    """Return all streaks."""
    with _lock:
        open_db()
        rows = _conn.execute("SELECT * FROM streaks ORDER BY current DESC").fetchall()
        return [dict(r) for r in rows]


# =====================================================================
# === TEMPLATES ===
# =====================================================================
def all_templates() -> list[dict]:
    """Return all templates."""
    with _lock:
        open_db()
        rows = _conn.execute("SELECT * FROM templates ORDER BY created_at ASC, id ASC").fetchall()
        return [dict(r) for r in rows]


def template_by_id(template_id: int) -> Optional[dict]:
    """Return a single template by id."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        return dict(row) if row else None


def upsert_template(t: dict) -> int:
    """Insert or update a template. Returns the id."""
    with _lock:
        open_db()
        if not t.get("created_at"):
            t["created_at"] = now_iso()
        if t.get("id"):
            _conn.execute(
                "UPDATE templates SET title=?, category_id=?, default_duration_min=?, icon=?, color=? WHERE id=?",
                (t["title"], t.get("category_id"), int(t.get("default_duration_min", 30)),
                 t.get("icon", ""), t.get("color"), t["id"]),
            )
            _conn.commit()
            return t["id"]
        cur = _conn.execute(
            "INSERT INTO templates(title, category_id, default_duration_min, icon, created_at, color) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (t["title"], t.get("category_id"), int(t.get("default_duration_min", 30)),
             t.get("icon", ""), t["created_at"], t.get("color")),
        )
        _conn.commit()
        return cur.lastrowid


def delete_template(template_id: int) -> None:
    """Delete a template."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        _conn.commit()


# =====================================================================
# === BADGES ===
# =====================================================================
def all_badges() -> list[dict]:
    """Return all earned badges."""
    with _lock:
        open_db()
        rows = _conn.execute("SELECT * FROM badges ORDER BY earned_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]


def has_badge(key: str) -> bool:
    """Return True if the badge with the given key has been earned."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT 1 FROM badges WHERE key=?", (key,)).fetchone()
        return row is not None


def award_badge(key: str, title_en: str, title_fa: str, meta: Optional[dict] = None) -> bool:
    """Award a badge. Returns True if newly awarded, False if already had it."""
    with _lock:
        open_db()
        if has_badge(key):
            return False
        _conn.execute(
            "INSERT INTO badges(key, title_en, title_fa, earned_at, meta) VALUES(?, ?, ?, ?, ?)",
            (key, title_en, title_fa, now_iso(),
             json.dumps(meta or {}, ensure_ascii=False)),
        )
        _conn.commit()
        return True


def delete_badge(key: str) -> None:
    """Remove a badge (used for testing)."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM badges WHERE key=?", (key,))
        _conn.commit()


def count_badges() -> int:
    """Return total badge count."""
    with _lock:
        open_db()
        return int(_conn.execute("SELECT COUNT(*) AS n FROM badges").fetchone()["n"])


# =====================================================================
# === RECURRING ACTIVITIES (desktop-only extension) ===
# =====================================================================
def all_recurring(active_only: bool = False) -> list[dict]:
    """Return all recurring rules."""
    with _lock:
        open_db()
        sql = "SELECT * FROM recurring"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY created_at ASC, id ASC"
        rows = _conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def recurring_by_id(recurring_id: int) -> Optional[dict]:
    """Return a single recurring rule by id."""
    with _lock:
        open_db()
        row = _conn.execute("SELECT * FROM recurring WHERE id=?", (recurring_id,)).fetchone()
        return dict(row) if row else None


def upsert_recurring(r: dict) -> int:
    """Insert or update a recurring rule. Returns the id."""
    with _lock:
        open_db()
        if not r.get("created_at"):
            r["created_at"] = now_iso()
        if r.get("id"):
            _conn.execute(
                "UPDATE recurring SET title=?, category_id=?, pattern=?, custom_days=?, "
                "duration_sec=?, start_date_iso=?, end_date_iso=?, next_run_iso=?, "
                "last_run_iso=?, active=?, icon=?, note=? WHERE id=?",
                (r["title"], r.get("category_id"), r.get("pattern", "daily"),
                 r.get("custom_days", "[]"), int(r.get("duration_sec", 0)),
                 r.get("start_date_iso", today_iso()), r.get("end_date_iso"),
                 r.get("next_run_iso", today_iso()), r.get("last_run_iso"),
                 int(bool(r.get("active", 1))), r.get("icon", ""), r.get("note", ""),
                 r["id"]),
            )
            _conn.commit()
            return r["id"]
        cur = _conn.execute(
            "INSERT INTO recurring(title, category_id, pattern, custom_days, duration_sec, "
            "start_date_iso, end_date_iso, next_run_iso, last_run_iso, active, created_at, icon, note) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["title"], r.get("category_id"), r.get("pattern", "daily"),
             r.get("custom_days", "[]"), int(r.get("duration_sec", 0)),
             r.get("start_date_iso", today_iso()), r.get("end_date_iso"),
             r.get("next_run_iso", today_iso()), r.get("last_run_iso"),
             int(bool(r.get("active", 1))), r["created_at"], r.get("icon", ""),
             r.get("note", "")),
        )
        _conn.commit()
        return cur.lastrowid


def delete_recurring(recurring_id: int) -> None:
    """Delete a recurring rule."""
    with _lock:
        open_db()
        _conn.execute("DELETE FROM recurring WHERE id=?", (recurring_id,))
        _conn.commit()


def due_recurring(today: Optional[str] = None) -> list[dict]:
    """Return all active recurring rules due on the given date (default today)."""
    today = today or today_iso()
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT * FROM recurring WHERE active=1 AND next_run_iso <= ? "
            "AND (end_date_iso IS NULL OR end_date_iso >= ?) "
            "ORDER BY next_run_iso ASC",
            (today, today),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_recurring_run(recurring_id: int, next_run_iso: str) -> None:
    """Mark a recurring rule as having run today, and set the next run date."""
    with _lock:
        open_db()
        _conn.execute(
            "UPDATE recurring SET last_run_iso=?, next_run_iso=? WHERE id=?",
            (today_iso(), next_run_iso, recurring_id),
        )
        _conn.commit()


# =====================================================================
# === BACKUP / RESTORE (mirror db.js exportAll / replaceAll) ===
# =====================================================================
STORES = ["activities", "categories", "goals", "streaks", "templates", "badges", "kv", "recurring"]


def export_all() -> dict:
    """Export all data as a JSON-serializable dict."""
    with _lock:
        open_db()
        result = {}
        for table in STORES:
            rows = _conn.execute(f"SELECT * FROM {table}").fetchall()
            result[table] = [dict(r) for r in rows]
        result["_meta"] = {
            "exported_at": now_iso(),
            "version": config.APP_VERSION,
            "schema_version": 1,
            "counts": {t: len(result[t]) for t in STORES},
        }
        return result


def replace_all(payload: dict) -> None:
    """Replace all data with the given payload (destructive)."""
    with _lock:
        open_db()
        for table in STORES:
            _conn.execute(f"DELETE FROM {table}")
        # Re-insert
        for table in STORES:
            rows = payload.get(table, [])
            for row in rows:
                # Remove the id so SQLite auto-increments
                row = dict(row)
                row.pop("id", None)
                cols = list(row.keys())
                placeholders = ", ".join("?" for _ in cols)
                col_names = ", ".join(cols)
                try:
                    _conn.execute(
                        f"INSERT INTO {table}({col_names}) VALUES({placeholders})",
                        [row[c] for c in cols],
                    )
                except sqlite3.IntegrityError:
                    # Skip duplicate keys
                    pass
        _conn.commit()
        # Re-seed defaults if categories empty
        cur = _conn.execute("SELECT COUNT(*) AS n FROM categories")
        if cur.fetchone()["n"] == 0:
            _seed_defaults()


def clear_all_data() -> None:
    """Delete all user data but keep the schema and default categories."""
    with _lock:
        open_db()
        for table in ["activities", "goals", "streaks", "templates", "badges", "recurring"]:
            _conn.execute(f"DELETE FROM {table}")
        # Reset kv (keep first_run = 0 so onboarding doesn't show again)
        _conn.execute("DELETE FROM kv")
        _conn.execute("INSERT INTO kv(key, value) VALUES('first_run', '0')")
        # Reset categories to defaults
        _conn.execute("DELETE FROM categories")
        _conn.commit()
        _seed_defaults()


def db_size_bytes() -> int:
    """Return the size of the database file in bytes."""
    try:
        return config.DB_PATH.stat().st_size
    except OSError:
        return 0


def db_size_human() -> str:
    """Return human-readable database size."""
    size = db_size_bytes()
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def vacuum() -> None:
    """Run VACUUM to compact the database."""
    with _lock:
        open_db()
        _conn.execute("VACUUM")
        _conn.commit()


# =====================================================================
# === ANALYTICS AGGREGATES (used by stats screen) ===
# =====================================================================
def best_day(start_iso: str, end_iso: str) -> Optional[tuple[str, int]]:
    """Return (date_iso, seconds) for the highest-total day in the range."""
    per_day = seconds_per_day(start_iso, end_iso)
    if not per_day:
        return None
    best = max(per_day.items(), key=lambda kv: kv[1])
    return best


def peak_hour(date_iso: str) -> Optional[int]:
    """Return the hour (0-23) with the most activity on the given date."""
    buckets = seconds_per_hour(date_iso)
    if not any(buckets):
        return None
    return max(range(24), key=lambda h: buckets[h])


def peak_weekday(start_iso: str, end_iso: str) -> Optional[int]:
    """Return the weekday (0=Mon, 6=Sun) with the most activity in the range."""
    buckets = seconds_per_weekday(start_iso, end_iso)
    if not any(buckets):
        return None
    return max(range(7), key=lambda d: buckets[d])


def active_days_count(start_iso: str, end_iso: str) -> int:
    """Return number of distinct days with at least one activity in the range."""
    per_day = seconds_per_day(start_iso, end_iso)
    return len(per_day)


def daily_average(start_iso: str, end_iso: str) -> float:
    """Return average seconds per day over the range (including zero days)."""
    from .date_utils import diff_days, parse_date
    d1 = parse_date(start_iso)
    d2 = parse_date(end_iso)
    days = diff_days(d2, d1) + 1
    if days <= 0:
        return 0.0
    return total_seconds_between(start_iso, end_iso) / days


def top_activities(start_iso: str, end_iso: str, limit: int = 5) -> list[tuple[str, int]]:
    """Return top N activity titles by total duration in the range."""
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT title, SUM(duration_sec) AS s FROM activities "
            "WHERE date_iso >= ? AND date_iso <= ? AND archived=0 "
            "GROUP BY title ORDER BY s DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ).fetchall()
        return [(r["title"] or "(no title)", int(r["s"] or 0)) for r in rows]


def activity_kind_breakdown(start_iso: str, end_iso: str) -> dict[str, int]:
    """Return {kind: total_seconds} for the range."""
    with _lock:
        open_db()
        rows = _conn.execute(
            "SELECT kind, SUM(duration_sec) AS s FROM activities "
            "WHERE date_iso >= ? AND date_iso <= ? AND archived=0 "
            "GROUP BY kind",
            (start_iso, end_iso),
        ).fetchall()
        return {r["kind"]: int(r["s"] or 0) for r in rows}


def yearly_heatmap(year: int) -> dict[str, int]:
    """Return {date_iso: seconds} for every day in the given year that has data."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    return seconds_per_day(start, end)


# =====================================================================
# === SANITY CHECK / DEBUG ===
# =====================================================================
def stats_summary() -> dict:
    """Return a summary dict useful for debugging / Settings screen."""
    return {
        "activities": count_activities(),
        "categories": len(all_categories()),
        "goals": len(all_goals()),
        "templates": len(all_templates()),
        "badges": count_badges(),
        "recurring": len(all_recurring()),
        "streaks": len(all_streaks()),
        "db_size": db_size_bytes(),
        "first_activity": first_activity_date(),
        "last_activity": last_activity_date(),
        "db_path": str(config.DB_PATH),
    }
