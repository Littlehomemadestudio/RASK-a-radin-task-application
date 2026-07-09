"""
repositories.py — Data-access layer.

Each repository wraps SQL queries for one entity and returns typed dataclasses.
Mirrors the repository pattern from the Kotlin version.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional

from rask import config as cfg
from rask.data import database as db
from rask.data.models import (
    Activity, Badge, Category, Goal, Streak, Template,
)


# === Category ===

class CategoryRepository:
    @staticmethod
    def all(include_archived: bool = False) -> list[Category]:
        sql = "SELECT * FROM categories"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY order_index ASC"
        return [_row_to_category(r) for r in db.query_all(sql)]

    @staticmethod
    def by_id(cid: int) -> Optional[Category]:
        r = db.query_one("SELECT * FROM categories WHERE id=?", (cid,))
        return _row_to_category(r) if r else None

    @staticmethod
    def by_key(key: str) -> Optional[Category]:
        r = db.query_one("SELECT * FROM categories WHERE key=?", (key,))
        return _row_to_category(r) if r else None

    @staticmethod
    def upsert(c: Category) -> int:
        if c.id:
            db.execute(
                "UPDATE categories SET key=?,color=?,name_en=?,name_fa=?,"
                "icon=?,order_index=?,archived=? WHERE id=?",
                (c.key, c.color, c.name_en, c.name_fa, c.icon,
                 c.order_index, int(c.archived), c.id),
            )
            return c.id
        return db.execute(
            "INSERT INTO categories(key,color,name_en,name_fa,icon,order_index,archived) "
            "VALUES (?,?,?,?,?,?,?)",
            (c.key, c.color, c.name_en, c.name_fa, c.icon, c.order_index, int(c.archived)),
        )

    @staticmethod
    def delete(cid: int) -> None:
        db.execute("UPDATE categories SET archived=1 WHERE id=?", (cid,))


# === Activity ===

class ActivityRepository:
    @staticmethod
    def insert(a: Activity) -> int:
        return db.execute(
            "INSERT INTO activities(title,category_id,kind,date_iso,start_iso,"
            "end_iso,duration_sec,note,template_id,voice_input,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (a.title, a.category_id, a.kind, a.date_iso, a.start_iso, a.end_iso,
             a.duration_sec, a.note, a.template_id, int(a.voice_input), a.created_at),
        )

    @staticmethod
    def update(a: Activity) -> None:
        db.execute(
            "UPDATE activities SET title=?,category_id=?,kind=?,date_iso=?,"
            "start_iso=?,end_iso=?,duration_sec=?,note=?,template_id=?,"
            "voice_input=? WHERE id=?",
            (a.title, a.category_id, a.kind, a.date_iso, a.start_iso, a.end_iso,
             a.duration_sec, a.note, a.template_id, int(a.voice_input), a.id),
        )

    @staticmethod
    def delete(aid: int) -> None:
        db.execute("DELETE FROM activities WHERE id=?", (aid,))

    @staticmethod
    def by_id(aid: int) -> Optional[Activity]:
        r = db.query_one("SELECT * FROM activities WHERE id=?", (aid,))
        return _row_to_activity(r) if r else None

    @staticmethod
    def recent(limit: int = 20) -> list[Activity]:
        rows = db.query_all(
            "SELECT * FROM activities ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_activity(r) for r in rows]

    @staticmethod
    def by_date_range(start_iso: str, end_iso: str) -> list[Activity]:
        rows = db.query_all(
            "SELECT * FROM activities WHERE date_iso >= ? AND date_iso <= ? "
            "ORDER BY date_iso DESC, created_at DESC",
            (start_iso, end_iso),
        )
        return [_row_to_activity(r) for r in rows]

    @staticmethod
    def by_date(date_iso: str) -> list[Activity]:
        rows = db.query_all(
            "SELECT * FROM activities WHERE date_iso=? "
            "ORDER BY start_iso DESC NULLS LAST, created_at DESC",
            (date_iso,),
        )
        return [_row_to_activity(r) for r in rows]

    @staticmethod
    def total_seconds_between(start_iso: str, end_iso: str,
                              category_id: Optional[int] = None) -> int:
        sql = ("SELECT COALESCE(SUM(duration_sec),0) FROM activities "
               "WHERE date_iso >= ? AND date_iso <= ?")
        params: list = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        return int(db.fetch_val(sql, params) or 0)

    @staticmethod
    def total_seconds_on(date_iso: str,
                         category_id: Optional[int] = None) -> int:
        sql = "SELECT COALESCE(SUM(duration_sec),0) FROM activities WHERE date_iso=?"
        params: list = [date_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        return int(db.fetch_val(sql, params) or 0)

    @staticmethod
    def last_stopwatch() -> Optional[Activity]:
        r = db.query_one(
            "SELECT * FROM activities WHERE kind='stopwatch' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        return _row_to_activity(r) if r else None

    @staticmethod
    def all_for_export() -> list[Activity]:
        rows = db.query_all(
            "SELECT * FROM activities ORDER BY date_iso ASC, start_iso ASC"
        )
        return [_row_to_activity(r) for r in rows]

    @staticmethod
    def seconds_per_day(start_iso: str, end_iso: str,
                        category_id: Optional[int] = None) -> dict[str, int]:
        sql = ("SELECT date_iso, COALESCE(SUM(duration_sec),0) AS s "
               "FROM activities WHERE date_iso >= ? AND date_iso <= ? ")
        params: list = [start_iso, end_iso]
        if category_id is not None:
            sql += " AND category_id=?"
            params.append(category_id)
        sql += " GROUP BY date_iso"
        rows = db.query_all(sql, params)
        return {r["date_iso"]: int(r["s"]) for r in rows}

    @staticmethod
    def seconds_per_category(start_iso: str, end_iso: str) -> list[tuple[int, int]]:
        sql = ("SELECT category_id, COALESCE(SUM(duration_sec),0) AS s "
               "FROM activities WHERE date_iso >= ? AND date_iso <= ? "
               "GROUP BY category_id ORDER BY s DESC")
        rows = db.query_all(sql, [start_iso, end_iso])
        return [(int(r["category_id"]) if r["category_id"] is not None else 0,
                 int(r["s"])) for r in rows]

    @staticmethod
    def seconds_per_hour(date_iso: str) -> list[int]:
        """Returns 24 buckets of seconds for a single day."""
        rows = db.query_all(
            "SELECT strftime('%H', COALESCE(start_iso, created_at)) AS h, "
            "COALESCE(SUM(duration_sec),0) AS s FROM activities "
            "WHERE date_iso=? GROUP BY h",
            [date_iso],
        )
        out = [0] * 24
        for r in rows:
            try:
                h = int(r["h"])
                if 0 <= h < 24:
                    out[h] = int(r["s"])
            except (ValueError, TypeError):
                pass
        return out


# === Goal ===

class GoalRepository:
    @staticmethod
    def all(active_only: bool = True) -> list[Goal]:
        sql = "SELECT * FROM goals"
        if active_only:
            sql += " WHERE active=1"
        return [_row_to_goal(r) for r in db.query_all(sql)]

    @staticmethod
    def by_id(gid: int) -> Optional[Goal]:
        r = db.query_one("SELECT * FROM goals WHERE id=?", (gid,))
        return _row_to_goal(r) if r else None

    @staticmethod
    def upsert(g: Goal) -> int:
        if g.id:
            db.execute(
                "UPDATE goals SET period=?,category_id=?,target_minutes=?,"
                "active=? WHERE id=?",
                (g.period, g.category_id, g.target_minutes, int(g.active), g.id),
            )
            return g.id
        return db.execute(
            "INSERT INTO goals(period,category_id,target_minutes,active,created_at) "
            "VALUES (?,?,?,?,?)",
            (g.period, g.category_id, g.target_minutes, int(g.active), g.created_at),
        )

    @staticmethod
    def delete(gid: int) -> None:
        db.execute("DELETE FROM goals WHERE id=?", (gid,))


# === Streak ===

class StreakRepository:
    @staticmethod
    def for_goal(goal_id: int) -> Optional[Streak]:
        r = db.query_one("SELECT * FROM streaks WHERE goal_id=?", (goal_id,))
        return _row_to_streak(r) if r else None

    @staticmethod
    def upsert(s: Streak) -> int:
        if s.id:
            db.execute(
                "UPDATE streaks SET goal_id=?,current=?,longest=?,last_hit_date=? "
                "WHERE id=?",
                (s.goal_id, s.current, s.longest, s.last_hit_date, s.id),
            )
            return s.id
        return db.execute(
            "INSERT INTO streaks(goal_id,current,longest,last_hit_date) "
            "VALUES (?,?,?,?)",
            (s.goal_id, s.current, s.longest, s.last_hit_date),
        )

    @staticmethod
    def all_longest(limit: int = 10) -> list[Streak]:
        rows = db.query_all(
            "SELECT * FROM streaks ORDER BY longest DESC LIMIT ?", (limit,)
        )
        return [_row_to_streak(r) for r in rows]


# === Template ===

class TemplateRepository:
    @staticmethod
    def all() -> list[Template]:
        rows = db.query_all("SELECT * FROM templates ORDER BY created_at DESC")
        return [_row_to_template(r) for r in rows]

    @staticmethod
    def upsert(t: Template) -> int:
        if t.id:
            db.execute(
                "UPDATE templates SET title=?,category_id=?,"
                "default_duration_min=?,icon=? WHERE id=?",
                (t.title, t.category_id, t.default_duration_min, t.icon, t.id),
            )
            return t.id
        return db.execute(
            "INSERT INTO templates(title,category_id,default_duration_min,icon,created_at) "
            "VALUES (?,?,?,?,?)",
            (t.title, t.category_id, t.default_duration_min, t.icon, t.created_at),
        )

    @staticmethod
    def delete(tid: int) -> None:
        db.execute("DELETE FROM templates WHERE id=?", (tid,))


# === Badge ===

class BadgeRepository:
    @staticmethod
    def all() -> list[Badge]:
        rows = db.query_all("SELECT * FROM badges ORDER BY earned_at DESC")
        return [_row_to_badge(r) for r in rows]

    @staticmethod
    def has_key(key: str) -> bool:
        return db.fetch_val(
            "SELECT 1 FROM badges WHERE key=?", (key,)
        ) is not None

    @staticmethod
    def award(key: str, title_en: str, title_fa: str) -> None:
        if BadgeRepository.has_key(key):
            return
        db.execute(
            "INSERT INTO badges(key,title_en,title_fa,earned_at) VALUES (?,?,?,?)",
            (key, title_en, title_fa,
             datetime.now().isoformat(timespec="seconds")),
        )


# === Row -> dataclass mappers ===

def _row_to_category(r) -> Category:
    return Category(
        id=r["id"], key=r["key"], color=r["color"],
        name_en=r["name_en"], name_fa=r["name_fa"],
        icon=r["icon"], order_index=r["order_index"],
        archived=bool(r["archived"]),
    )


def _row_to_activity(r) -> Activity:
    return Activity(
        id=r["id"], title=r["title"], category_id=r["category_id"],
        kind=r["kind"], date_iso=r["date_iso"],
        start_iso=r["start_iso"], end_iso=r["end_iso"],
        duration_sec=r["duration_sec"], note=r["note"],
        template_id=r["template_id"], voice_input=bool(r["voice_input"]),
        created_at=r["created_at"],
    )


def _row_to_goal(r) -> Goal:
    return Goal(
        id=r["id"], period=r["period"], category_id=r["category_id"],
        target_minutes=r["target_minutes"], active=bool(r["active"]),
        created_at=r["created_at"],
    )


def _row_to_streak(r) -> Streak:
    return Streak(
        id=r["id"], goal_id=r["goal_id"], current=r["current"],
        longest=r["longest"], last_hit_date=r["last_hit_date"],
    )


def _row_to_template(r) -> Template:
    return Template(
        id=r["id"], title=r["title"], category_id=r["category_id"],
        default_duration_min=r["default_duration_min"], icon=r["icon"],
        created_at=r["created_at"],
    )


def _row_to_badge(r) -> Badge:
    return Badge(
        id=r["id"], key=r["key"], title_en=r["title_en"],
        title_fa=r["title_fa"], earned_at=r["earned_at"],
    )
