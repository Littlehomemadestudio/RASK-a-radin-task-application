"""database.py — SQLite storage layer (mirror of web/js/db.js).

Schema: activities, categories, goals, streaks, templates, badges, kv.
Defaults are seeded on first open (7 categories + 1 daily goal).
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple
from . import config
from .date_utils import now_iso


_DB_PATH = os.path.join(os.path.expanduser("~"), ".rask", "rask.db")
_LOCK = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _conn = c
    return _conn


def open_db() -> None:
    """Create tables and seed defaults. Idempotent."""
    with _LOCK:
        c = _connect()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, category_id INTEGER, kind TEXT,
                date_iso TEXT, start_iso TEXT, end_iso TEXT,
                duration_sec INTEGER, note TEXT, voice_input INTEGER,
                template_id INTEGER, created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_act_date ON activities(date_iso);
            CREATE INDEX IF NOT EXISTS idx_act_cat  ON activities(category_id);
            CREATE INDEX IF NOT EXISTS idx_act_kind ON activities(kind);
            CREATE INDEX IF NOT EXISTS idx_act_ct   ON activities(created_at);

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE, color TEXT,
                name_en TEXT, name_fa TEXT, icon TEXT,
                order_index INTEGER, archived INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT, category_id INTEGER, target_minutes INTEGER,
                active INTEGER DEFAULT 1, created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS streaks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER UNIQUE, current INTEGER, longest INTEGER,
                last_hit_date TEXT
            );

            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, category_id INTEGER,
                default_duration_min INTEGER, icon TEXT, created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE, title_en TEXT, title_fa TEXT, earned_at TEXT
            );

            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY, value TEXT
            );
            """
        )
        _seed_defaults(c)
        c.commit()


def _seed_defaults(c: sqlite3.Connection) -> None:
    cur = c.execute("SELECT COUNT(*) AS n FROM categories")
    if cur.fetchone()["n"] > 0:
        return
    for cat in config.DEFAULT_CATEGORIES:
        c.execute(
            "INSERT INTO categories (key,color,name_en,name_fa,icon,order_index,archived) "
            "VALUES (?,?,?,?,?,?,0)",
            (cat["key"], cat["color"], cat["name_en"], cat["name_fa"],
             cat["icon"], cat["order_index"]),
        )
    c.execute(
        "INSERT INTO goals (period,category_id,target_minutes,active,created_at) "
        "VALUES ('daily', NULL, ?, 1, ?)",
        (config.DEFAULT_DAILY_GOAL_MIN, now_iso()),
    )
    c.execute("INSERT OR REPLACE INTO kv (key,value) VALUES ('first_run','1')")


# === KV ===
def kv_get(key: str, default: Any = None) -> Any:
    with _LOCK:
        r = _connect().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def kv_set(key: str, value: Any) -> None:
    with _LOCK:
        _connect().execute(
            "INSERT OR REPLACE INTO kv (key,value) VALUES (?,?)",
            (key, "" if value is None else str(value)),
        )
        _connect().commit()


def kv_get_bool(key: str, default: bool = False) -> bool:
    v = kv_get(key, "1" if default else "0")
    return v in ("1", "true", "True", 1, True)


def kv_get_json(key: str, default: Any = None) -> Any:
    v = kv_get(key, None)
    if v is None:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def kv_set_json(key: str, obj: Any) -> None:
    kv_set(key, json.dumps(obj))


# === Activities ===
def insert_activity(a: Dict[str, Any]) -> int:
    if not a.get("created_at"):
        a["created_at"] = now_iso()
    with _LOCK:
        cur = _connect().execute(
            "INSERT INTO activities "
            "(title,category_id,kind,date_iso,start_iso,end_iso,duration_sec,note,voice_input,template_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (a.get("title", ""), a.get("category_id"), a.get("kind", "manual"),
             a.get("date_iso"), a.get("start_iso"), a.get("end_iso"),
             int(a.get("duration_sec", 0) or 0), a.get("note", ""),
             1 if a.get("voice_input") else 0, a.get("template_id"),
             a["created_at"]),
        )
        _connect().commit()
        return cur.lastrowid


def update_activity(a: Dict[str, Any]) -> None:
    with _LOCK:
        _connect().execute(
            "UPDATE activities SET title=?,category_id=?,kind=?,date_iso=?,start_iso=?,"
            "end_iso=?,duration_sec=?,note=?,voice_input=?,template_id=? WHERE id=?",
            (a.get("title", ""), a.get("category_id"), a.get("kind", "manual"),
             a.get("date_iso"), a.get("start_iso"), a.get("end_iso"),
             int(a.get("duration_sec", 0) or 0), a.get("note", ""),
             1 if a.get("voice_input") else 0, a.get("template_id"), a["id"]),
        )
        _connect().commit()


def delete_activity(aid: int) -> None:
    with _LOCK:
        _connect().execute("DELETE FROM activities WHERE id=?", (aid,))
        _connect().commit()


def get_activity(aid: int) -> Optional[Dict[str, Any]]:
    r = _connect().execute("SELECT * FROM activities WHERE id=?", (aid,)).fetchone()
    return dict(r) if r else None


def all_activities() -> List[Dict[str, Any]]:
    return [dict(r) for r in _connect().execute("SELECT * FROM activities").fetchall()]


def recent_activities(limit: int = 20) -> List[Dict[str, Any]]:
    rows = _connect().execute(
        "SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def activities_by_date_range(start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    rows = _connect().execute(
        "SELECT * FROM activities WHERE date_iso >= ? AND date_iso <= ? "
        "ORDER BY date_iso DESC, created_at DESC",
        (start_iso, end_iso),
    ).fetchall()
    return [dict(r) for r in rows]


def activities_by_date(date_iso: str) -> List[Dict[str, Any]]:
    rows = _connect().execute(
        "SELECT * FROM activities WHERE date_iso=?", (date_iso,)
    ).fetchall()
    return [dict(r) for r in rows]


def total_seconds_between(start_iso: str, end_iso: str, category_id: Optional[int] = None) -> int:
    if category_id:
        q = ("SELECT COALESCE(SUM(duration_sec),0) AS s FROM activities "
             "WHERE date_iso >= ? AND date_iso <= ? AND category_id=?")
        r = _connect().execute(q, (start_iso, end_iso, category_id)).fetchone()
    else:
        q = ("SELECT COALESCE(SUM(duration_sec),0) AS s FROM activities "
             "WHERE date_iso >= ? AND date_iso <= ?")
        r = _connect().execute(q, (start_iso, end_iso)).fetchone()
    return int(r["s"] or 0)


def total_seconds_on(date_iso: str, category_id: Optional[int] = None) -> int:
    return total_seconds_between(date_iso, date_iso, category_id)


def seconds_per_day(start_iso: str, end_iso: str, category_id: Optional[int] = None) -> Dict[str, int]:
    if category_id:
        rows = _connect().execute(
            "SELECT date_iso, SUM(duration_sec) AS s FROM activities "
            "WHERE date_iso >= ? AND date_iso <= ? AND category_id=? "
            "GROUP BY date_iso",
            (start_iso, end_iso, category_id),
        ).fetchall()
    else:
        rows = _connect().execute(
            "SELECT date_iso, SUM(duration_sec) AS s FROM activities "
            "WHERE date_iso >= ? AND date_iso <= ? GROUP BY date_iso",
            (start_iso, end_iso),
        ).fetchall()
    return {r["date_iso"]: int(r["s"] or 0) for r in rows}


def seconds_per_category(start_iso: str, end_iso: str) -> List[Tuple[int, int]]:
    rows = _connect().execute(
        "SELECT category_id, SUM(duration_sec) AS s FROM activities "
        "WHERE date_iso >= ? AND date_iso <= ? GROUP BY category_id "
        "ORDER BY s DESC",
        (start_iso, end_iso),
    ).fetchall()
    return [(int(r["category_id"] or 0), int(r["s"] or 0)) for r in rows]


def seconds_per_hour(date_iso: str) -> List[int]:
    rows = _connect().execute(
        "SELECT start_iso, created_at, duration_sec FROM activities WHERE date_iso=?",
        (date_iso,),
    ).fetchall()
    buckets = [0] * 24
    for r in rows:
        ts = r["start_iso"] or r["created_at"]
        if not ts:
            continue
        try:
            h = int(ts[11:13])
        except (ValueError, IndexError):
            continue
        if 0 <= h < 24:
            buckets[h] += int(r["duration_sec"] or 0)
    return buckets


# === Categories ===
def all_categories(include_archived: bool = False) -> List[Dict[str, Any]]:
    rows = _connect().execute(
        "SELECT * FROM categories ORDER BY order_index ASC"
    ).fetchall()
    out = [dict(r) for r in rows]
    return out if include_archived else [c for c in out if not c["archived"]]


def category_by_id(cid: Optional[int]) -> Optional[Dict[str, Any]]:
    if not cid:
        return None
    r = _connect().execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def upsert_category(c: Dict[str, Any]) -> int:
    with _LOCK:
        if c.get("id"):
            _connect().execute(
                "UPDATE categories SET key=?,color=?,name_en=?,name_fa=?,icon=?,"
                "order_index=?,archived=? WHERE id=?",
                (c["key"], c["color"], c["name_en"], c["name_fa"], c["icon"],
                 c["order_index"], c["archived"], c["id"]),
            )
            _connect().commit()
            return c["id"]
        cur = _connect().execute(
            "INSERT INTO categories (key,color,name_en,name_fa,icon,order_index,archived) "
            "VALUES (?,?,?,?,?,?,0)",
            (c["key"], c["color"], c["name_en"], c["name_fa"], c["icon"], c["order_index"]),
        )
        _connect().commit()
        return cur.lastrowid


def archive_category(cid: int) -> None:
    with _LOCK:
        _connect().execute("UPDATE categories SET archived=1 WHERE id=?", (cid,))
        _connect().commit()


# === Goals ===
def all_goals(active_only: bool = False) -> List[Dict[str, Any]]:
    if active_only:
        rows = _connect().execute(
            "SELECT * FROM goals WHERE active=1 ORDER BY id"
        ).fetchall()
    else:
        rows = _connect().execute("SELECT * FROM goals ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def upsert_goal(g: Dict[str, Any]) -> int:
    if not g.get("created_at"):
        g["created_at"] = now_iso()
    with _LOCK:
        if g.get("id"):
            _connect().execute(
                "UPDATE goals SET period=?,category_id=?,target_minutes=?,active=? WHERE id=?",
                (g["period"], g.get("category_id"), g["target_minutes"],
                 1 if g.get("active", True) else 0, g["id"]),
            )
            _connect().commit()
            return g["id"]
        cur = _connect().execute(
            "INSERT INTO goals (period,category_id,target_minutes,active,created_at) "
            "VALUES (?,?,?,?,?)",
            (g["period"], g.get("category_id"), g["target_minutes"],
             1 if g.get("active", True) else 0, g["created_at"]),
        )
        _connect().commit()
        return cur.lastrowid


def delete_goal(gid: int) -> None:
    with _LOCK:
        _connect().execute("DELETE FROM goals WHERE id=?", (gid,))
        _connect().execute("DELETE FROM streaks WHERE goal_id=?", (gid,))
        _connect().commit()


# === Streaks ===
def streak_for_goal(gid: int) -> Optional[Dict[str, Any]]:
    r = _connect().execute("SELECT * FROM streaks WHERE goal_id=?", (gid,)).fetchone()
    return dict(r) if r else None


def upsert_streak(s: Dict[str, Any]) -> None:
    with _LOCK:
        if s.get("id"):
            _connect().execute(
                "UPDATE streaks SET goal_id=?,current=?,longest=?,last_hit_date=? WHERE id=?",
                (s["goal_id"], s["current"], s["longest"], s["last_hit_date"], s["id"]),
            )
        else:
            _connect().execute(
                "INSERT OR REPLACE INTO streaks (goal_id,current,longest,last_hit_date) "
                "VALUES (?,?,?,?)",
                (s["goal_id"], s["current"], s["longest"], s["last_hit_date"]),
            )
        _connect().commit()


def top_streaks(limit: int = 10) -> List[Dict[str, Any]]:
    rows = _connect().execute(
        "SELECT * FROM streaks ORDER BY longest DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# === Templates ===
def all_templates() -> List[Dict[str, Any]]:
    rows = _connect().execute("SELECT * FROM templates ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def upsert_template(t: Dict[str, Any]) -> int:
    if not t.get("created_at"):
        t["created_at"] = now_iso()
    with _LOCK:
        if t.get("id"):
            _connect().execute(
                "UPDATE templates SET title=?,category_id=?,default_duration_min=?,icon=? WHERE id=?",
                (t["title"], t.get("category_id"), t.get("default_duration_min", 30),
                 t.get("icon", ""), t["id"]),
            )
            _connect().commit()
            return t["id"]
        cur = _connect().execute(
            "INSERT INTO templates (title,category_id,default_duration_min,icon,created_at) "
            "VALUES (?,?,?,?,?)",
            (t["title"], t.get("category_id"), t.get("default_duration_min", 30),
             t.get("icon", ""), t["created_at"]),
        )
        _connect().commit()
        return cur.lastrowid


def delete_template(tid: int) -> None:
    with _LOCK:
        _connect().execute("DELETE FROM templates WHERE id=?", (tid,))
        _connect().commit()


# === Badges ===
def all_badges() -> List[Dict[str, Any]]:
    rows = _connect().execute("SELECT * FROM badges ORDER BY earned_at").fetchall()
    return [dict(r) for r in rows]


def has_badge(key: str) -> bool:
    r = _connect().execute("SELECT 1 FROM badges WHERE key=?", (key,)).fetchone()
    return r is not None


def award_badge(key: str, title_en: str, title_fa: str) -> None:
    if has_badge(key):
        return
    with _LOCK:
        _connect().execute(
            "INSERT OR IGNORE INTO badges (key,title_en,title_fa,earned_at) VALUES (?,?,?,?)",
            (key, title_en, title_fa, now_iso()),
        )
        _connect().commit()


# === Backup payload ===
STORES = ["activities", "categories", "goals", "streaks", "templates", "badges", "kv"]


def export_all() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "activities": all_activities(),
        "categories": all_categories(include_archived=True),
        "goals": all_goals(),
        "streaks": [dict(r) for r in _connect().execute("SELECT * FROM streaks").fetchall()],
        "templates": all_templates(),
        "badges": all_badges(),
        "kv": [dict(r) for r in _connect().execute("SELECT * FROM kv").fetchall()],
    }


def replace_all(payload: Dict[str, Any]) -> None:
    with _LOCK:
        c = _connect()
        for tbl in STORES:
            c.execute(f"DELETE FROM {tbl}")
        for row in payload.get("activities", []):
            c.execute(
                "INSERT INTO activities "
                "(id,title,category_id,kind,date_iso,start_iso,end_iso,duration_sec,note,voice_input,template_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (row.get("id"), row.get("title", ""), row.get("category_id"),
                 row.get("kind", "manual"), row.get("date_iso"),
                 row.get("start_iso"), row.get("end_iso"),
                 int(row.get("duration_sec", 0) or 0), row.get("note", ""),
                 1 if row.get("voice_input") else 0, row.get("template_id"),
                 row.get("created_at")),
            )
        for row in payload.get("categories", []):
            c.execute(
                "INSERT INTO categories (id,key,color,name_en,name_fa,icon,order_index,archived) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (row.get("id"), row["key"], row.get("color"), row.get("name_en"),
                 row.get("name_fa"), row.get("icon"), row.get("order_index", 0),
                 1 if row.get("archived") else 0),
            )
        for row in payload.get("goals", []):
            c.execute(
                "INSERT INTO goals (id,period,category_id,target_minutes,active,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (row.get("id"), row["period"], row.get("category_id"),
                 row["target_minutes"], 1 if row.get("active", True) else 0,
                 row.get("created_at")),
            )
        for row in payload.get("streaks", []):
            c.execute(
                "INSERT OR REPLACE INTO streaks (id,goal_id,current,longest,last_hit_date) "
                "VALUES (?,?,?,?,?)",
                (row.get("id"), row["goal_id"], row.get("current", 0),
                 row.get("longest", 0), row.get("last_hit_date")),
            )
        for row in payload.get("templates", []):
            c.execute(
                "INSERT INTO templates (id,title,category_id,default_duration_min,icon,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (row.get("id"), row["title"], row.get("category_id"),
                 row.get("default_duration_min", 30), row.get("icon", ""),
                 row.get("created_at")),
            )
        for row in payload.get("badges", []):
            c.execute(
                "INSERT OR IGNORE INTO badges (id,key,title_en,title_fa,earned_at) VALUES (?,?,?,?,?)",
                (row.get("id"), row["key"], row.get("title_en"), row.get("title_fa"),
                 row.get("earned_at")),
            )
        for row in payload.get("kv", []):
            c.execute(
                "INSERT OR REPLACE INTO kv (key,value) VALUES (?,?)",
                (row["key"], row.get("value", "")),
            )
        c.commit()
