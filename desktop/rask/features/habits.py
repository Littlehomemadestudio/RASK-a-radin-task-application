"""
rask.features.habits
====================

Habit tracker with daily/weekly completion logs, streaks, and
completion-rate analytics.

Each habit has a frequency (``daily``, ``weekly``, or ``3x_week``)
and a target count (default 1).  Each day the user marks the habit
"completed" (or un-completed) via :meth:`HabitService.log_completion`.

Streaks count consecutive hit-days (a "hit" is a day where the
completed count >= target).  For weekly / 3x_week habits the streak
counts consecutive *weeks* in which the target was met.

Schema
------

::

    CREATE TABLE habits (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        description     TEXT,
        color           TEXT,
        icon            TEXT,
        frequency       TEXT NOT NULL,    -- daily | weekly | 3x_week
        target_count    INTEGER NOT NULL DEFAULT 1,
        active          INTEGER NOT NULL DEFAULT 1,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE habit_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id        INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
        date_iso        TEXT NOT NULL,
        completed       INTEGER NOT NULL DEFAULT 1,
        count           INTEGER NOT NULL DEFAULT 1,
        note            TEXT,
        created_at      TEXT NOT NULL,
        UNIQUE(habit_id, date_iso)
    );

Events
------

  ``habit.added``       — {habit: dict}
  ``habit.updated``     — {id, fields: dict, habit: dict}
  ``habit.deleted``     — {id}
  ``habit.logged``      — {habit_id, date_iso, completed, count}
  ``habit.streak_changed`` — {habit_id, streak, best}
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, end_of_week, start_of_week, today_iso

__all__ = [
    "Habit",
    "HabitLog",
    "HabitService",
    "habit_service",
    "FREQ_DAILY",
    "FREQ_WEEKLY",
    "FREQ_3X_WEEK",
]

_log = get_logger("features.habits")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

FREQ_DAILY: str = "daily"
FREQ_WEEKLY: str = "weekly"
FREQ_3X_WEEK: str = "3x_week"

VALID_FREQUENCIES = (FREQ_DAILY, FREQ_WEEKLY, FREQ_3X_WEEK)


SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS habits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    color           TEXT,
    icon            TEXT,
    frequency       TEXT NOT NULL,
    target_count    INTEGER NOT NULL DEFAULT 1,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS habit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id        INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    date_iso        TEXT NOT NULL,
    completed       INTEGER NOT NULL DEFAULT 1,
    count           INTEGER NOT NULL DEFAULT 1,
    note            TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(habit_id, date_iso)
);
CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs(habit_id);
CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(date_iso);
"""


# =============================================================================
# === Data classes                                                           ===
# =============================================================================

@dataclass
class Habit:
    """A habit definition."""

    name: str
    frequency: str = FREQ_DAILY
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    target_count: int = 1
    active: bool = True
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["active"] = 1 if self.active else 0
        return d

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Habit":
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            name=row["name"],
            description=row.get("description"),
            color=row.get("color"),
            icon=row.get("icon"),
            frequency=row.get("frequency", FREQ_DAILY),
            target_count=int(row.get("target_count", 1)),
            active=bool(row.get("active", 1)),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class HabitLog:
    """A single completion record for a habit on a specific date."""

    habit_id: int
    date_iso: str
    completed: bool = True
    count: int = 1
    note: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["completed"] = 1 if self.completed else 0
        return d

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "HabitLog":
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            habit_id=int(row["habit_id"]),
            date_iso=row["date_iso"],
            completed=bool(row.get("completed", 1)),
            count=int(row.get("count", 1)),
            note=row.get("note"),
            created_at=row.get("created_at"),
        )


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _json_dumps(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return "[]"


# =============================================================================
# === Schema bootstrap                                                       ===
# =============================================================================

_schema_initialized: bool = False
_schema_lock = threading.Lock()


def _ensure_schema() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        try:
            conn = db.get_conn()
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            _schema_initialized = True
            _log.debug("habits schema initialized")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === HabitService                                                           ===
# =============================================================================

class HabitService:
    """Habit tracker with streaks and completion analytics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        _ensure_schema()

    # ------------------------------------------------------------------
    # CRUD: habits
    # ------------------------------------------------------------------

    def add_habit(self, name: str, frequency: str = FREQ_DAILY,
                  color: Optional[str] = None, icon: Optional[str] = None,
                  description: Optional[str] = None,
                  target_count: int = 1) -> int:
        """Add a new habit.  Returns the new id (0 on failure)."""
        if not name or not name.strip():
            raise ValueError("Habit name must be non-empty")
        if frequency not in VALID_FREQUENCIES:
            raise ValueError(f"Invalid frequency: {frequency!r}")
        target_count = max(1, int(target_count))
        now = _now_iso()
        try:
            conn = db.get_conn()
            cur = conn.execute(
                "INSERT INTO habits(name, description, color, icon, frequency, "
                "target_count, active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name.strip(), description, color, icon, frequency,
                 target_count, now, now),
            )
            conn.commit()
            new_id = int(cur.lastrowid or 0)
            habit = self.get_habit(new_id)
            bus.publish("habit.added", {"habit": habit.to_dict() if habit else {}})
            _log.info("Habit added: id=%d name=%r", new_id, name)
            return new_id
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"name": name})
            return 0

    def update_habit(self, id: int, **fields: Any) -> Optional[Habit]:
        if not isinstance(id, int) or id <= 0:
            return None
        existing = self.get_habit(id)
        if existing is None:
            return None
        allowed = {"name", "description", "color", "icon", "frequency",
                   "target_count", "active"}
        updates: List[str] = []
        values: List[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "frequency" and v not in VALID_FREQUENCIES:
                _log.warning("Ignoring invalid frequency=%r", v)
                continue
            if k == "target_count":
                v = max(1, int(v))
            if k == "active":
                v = 1 if v else 0
            updates.append(f"{k} = ?")
            values.append(v)
        if not updates:
            return existing
        updates.append("updated_at = ?")
        values.append(_now_iso())
        values.append(id)
        try:
            conn = db.get_conn()
            conn.execute(
                f"UPDATE habits SET {', '.join(updates)} WHERE id = ?",
                values)
            conn.commit()
            updated = self.get_habit(id)
            bus.publish("habit.updated",
                        {"id": id, "fields": fields,
                         "habit": updated.to_dict() if updated else None})
            return updated
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return existing

    def delete_habit(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            conn = db.get_conn()
            # Cascade delete logs (FK constraint should do it, but be explicit).
            conn.execute("DELETE FROM habit_logs WHERE habit_id = ?", (id,))
            cur = conn.execute("DELETE FROM habits WHERE id = ?", (id,))
            conn.commit()
            ok = (cur.rowcount or 0) > 0
            if ok:
                bus.publish("habit.deleted", {"id": id})
            return ok
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False

    def get_habit(self, id: int) -> Optional[Habit]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM habits WHERE id = ?", (id,))
            row = cur.fetchone()
            if not row:
                return None
            return Habit.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list_habits(self, active: bool = True) -> List[Habit]:
        try:
            sql = "SELECT * FROM habits"
            if active:
                sql += " WHERE active = 1"
            sql += " ORDER BY created_at ASC"
            cur = db.get_conn().execute(sql)
            return [Habit.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    # ------------------------------------------------------------------
    # Logging completions
    # ------------------------------------------------------------------

    def log_completion(self, habit_id: int, date_iso: Optional[str] = None,
                       completed: bool = True, count: int = 1,
                       note: Optional[str] = None) -> bool:
        """Mark a habit as completed (or un-completed) on a date.

        If a log already exists for that date, it is updated.
        Returns True on success.
        """
        if not isinstance(habit_id, int) or habit_id <= 0:
            return False
        target = self.get_habit(habit_id)
        if target is None:
            return False
        date_iso = (date_iso or today_iso())[:10]
        count = max(1, int(count))
        now = _now_iso()
        try:
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO habit_logs(habit_id, date_iso, completed, count, "
                "note, created_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(habit_id, date_iso) DO UPDATE SET "
                "completed = excluded.completed, count = excluded.count, "
                "note = excluded.note",
                (habit_id, date_iso, 1 if completed else 0, count, note, now),
            )
            conn.commit()
            bus.publish("habit.logged",
                        {"habit_id": habit_id, "date_iso": date_iso,
                         "completed": completed, "count": count})
            # Publish streak change.
            s = self.streak(habit_id)
            b = self.best_streak(habit_id)
            bus.publish("habit.streak_changed",
                        {"habit_id": habit_id, "streak": s, "best": b})
            return True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"habit_id": habit_id, "date_iso": date_iso})
            return False

    def unlog_completion(self, habit_id: int,
                         date_iso: Optional[str] = None) -> bool:
        """Remove a completion log (alias for log_completion(completed=False))."""
        return self.log_completion(habit_id, date_iso=date_iso,
                                    completed=False, count=0)

    def is_completed_today(self, habit_id: int) -> bool:
        """True if the habit has a completed log for today."""
        if not isinstance(habit_id, int) or habit_id <= 0:
            return False
        today = today_iso()
        try:
            cur = db.get_conn().execute(
                "SELECT completed FROM habit_logs "
                "WHERE habit_id = ? AND date_iso = ?",
                (habit_id, today))
            row = cur.fetchone()
            return bool(row and row["completed"])
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"habit_id": habit_id})
            return False

    def get_log(self, habit_id: int, date_iso: str) -> Optional[HabitLog]:
        try:
            cur = db.get_conn().execute(
                "SELECT * FROM habit_logs "
                "WHERE habit_id = ? AND date_iso = ?",
                (habit_id, date_iso[:10]))
            row = cur.fetchone()
            if not row:
                return None
            return HabitLog.from_row({k: row[k] for k in row.keys()})
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"habit_id": habit_id, "date_iso": date_iso})
            return None

    def logs_for_habit(self, habit_id: int,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None) -> List[HabitLog]:
        try:
            where = ["habit_id = ?"]
            args: List[Any] = [habit_id]
            if date_from:
                where.append("date_iso >= ?")
                args.append(date_from[:10])
            if date_to:
                where.append("date_iso <= ?")
                args.append(date_to[:10])
            sql = (f"SELECT * FROM habit_logs WHERE {' AND '.join(where)} "
                   "ORDER BY date_iso ASC")
            cur = db.get_conn().execute(sql, args)
            return [HabitLog.from_row({k: r[k] for k in r.keys()})
                    for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"habit_id": habit_id})
            return []

    # ------------------------------------------------------------------
    # Streak & completion analytics
    # ------------------------------------------------------------------

    def streak(self, habit_id: int) -> int:
        """Current consecutive-day completion streak.

        For daily habits: counts today (or yesterday) backward through
        days where the habit was completed.

        For weekly / 3x_week habits: counts consecutive weeks where
        the target was met.
        """
        habit = self.get_habit(habit_id)
        if habit is None:
            return 0
        if habit.frequency == FREQ_DAILY:
            return self._daily_streak(habit_id, habit.target_count)
        return self._weekly_streak(habit_id, habit.target_count,
                                    habit.frequency)

    def best_streak(self, habit_id: int) -> int:
        """Longest historical streak (days for daily, weeks for weekly)."""
        habit = self.get_habit(habit_id)
        if habit is None:
            return 0
        if habit.frequency == FREQ_DAILY:
            return self._best_daily_streak(habit_id, habit.target_count)
        return self._best_weekly_streak(habit_id, habit.target_count,
                                         habit.frequency)

    def _daily_streak(self, habit_id: int, target: int) -> int:
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, count FROM habit_logs "
                "WHERE habit_id = ? AND completed = 1 "
                "ORDER BY date_iso DESC",
                (habit_id,))
            rows = [(r["date_iso"], int(r["count"])) for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return 0
        if not rows:
            return 0
        today = today_iso()
        yesterday = add_days(today, -1)
        if rows[0][0] == today:
            start = today
        elif rows[0][0] == yesterday:
            start = yesterday
        else:
            return 0
        date_to_count = {d: c for d, c in rows}
        streak = 0
        cur_date = start
        while cur_date in date_to_count and date_to_count[cur_date] >= target:
            streak += 1
            cur_date = add_days(cur_date, -1)
        return streak

    def _weekly_streak(self, habit_id: int, target: int,
                       frequency: str) -> int:
        """Count consecutive weeks where the weekly target was met."""
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, count FROM habit_logs "
                "WHERE habit_id = ? AND completed = 1 "
                "ORDER BY date_iso ASC",
                (habit_id,))
            rows = [(r["date_iso"], int(r["count"])) for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return 0
        if not rows:
            return 0
        # Group by week (start_of_week, Saturday)
        week_to_count: Dict[str, int] = {}
        for d_iso, c in rows:
            wk = start_of_week(d_iso, first_day=6)
            week_to_count[wk] = week_to_count.get(wk, 0) + c
        # Effective weekly target depends on frequency
        if frequency == FREQ_WEEKLY:
            weekly_target = target  # user-defined target
        elif frequency == FREQ_3X_WEEK:
            weekly_target = 3
        else:
            weekly_target = target
        # Walk backward from current week.
        today = today_iso()
        current_week = start_of_week(today, first_day=6)
        streak = 0
        cursor = current_week
        while cursor in week_to_count and week_to_count[cursor] >= weekly_target:
            streak += 1
            cursor = add_days(cursor, -7)
        # If the current week hasn't reached target yet but last week did,
        # the streak counts from last week.
        if streak == 0:
            cursor = add_days(current_week, -7)
            while cursor in week_to_count and week_to_count[cursor] >= weekly_target:
                streak += 1
                cursor = add_days(cursor, -7)
        return streak

    def _best_daily_streak(self, habit_id: int, target: int) -> int:
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, count FROM habit_logs "
                "WHERE habit_id = ? AND completed = 1 "
                "ORDER BY date_iso ASC",
                (habit_id,))
            rows = [(r["date_iso"], int(r["count"])) for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return 0
        if not rows:
            return 0
        best = 0
        current = 0
        prev_date: Optional[date] = None
        for d_iso, c in rows:
            if c < target:
                current = 0
                prev_date = None
                continue
            try:
                d = date.fromisoformat(d_iso)
            except Exception:  # noqa: BLE001
                continue
            if prev_date is not None and (d - prev_date).days == 1:
                current += 1
            else:
                current = 1
            if current > best:
                best = current
            prev_date = d
        return best

    def _best_weekly_streak(self, habit_id: int, target: int,
                            frequency: str) -> int:
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, count FROM habit_logs "
                "WHERE habit_id = ? AND completed = 1 "
                "ORDER BY date_iso ASC",
                (habit_id,))
            rows = [(r["date_iso"], int(r["count"])) for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return 0
        if not rows:
            return 0
        week_to_count: Dict[str, int] = {}
        for d_iso, c in rows:
            wk = start_of_week(d_iso, first_day=6)
            week_to_count[wk] = week_to_count.get(wk, 0) + c
        weekly_target = 3 if frequency == FREQ_3X_WEEK else target
        sorted_weeks = sorted(week_to_count.keys())
        best = 0
        current = 0
        prev_week: Optional[date] = None
        for wk in sorted_weeks:
            if week_to_count[wk] < weekly_target:
                current = 0
                prev_week = None
                continue
            try:
                d = date.fromisoformat(wk)
            except Exception:  # noqa: BLE001
                continue
            if prev_week is not None and (d - prev_week).days == 7:
                current += 1
            else:
                current = 1
            if current > best:
                best = current
            prev_week = d
        return best

    def completion_rate(self, habit_id: int, days: int = 30) -> float:
        """Fraction (0..1) of the last `days` days where the habit was completed.

        Only applies to daily habits.  Weekly habits return the
        fraction of weeks (out of weeks partially covered by the
        window) where the target was met.
        """
        habit = self.get_habit(habit_id)
        if habit is None:
            return 0.0
        if habit.frequency == FREQ_DAILY:
            date_from = add_days(today_iso(), -(days - 1))
            try:
                cur = db.get_conn().execute(
                    "SELECT COUNT(*) AS c FROM habit_logs "
                    "WHERE habit_id = ? AND completed = 1 AND date_iso >= ?",
                    (habit_id, date_from))
                row = cur.fetchone()
                completed_days = int(row["c"]) if row else 0
                return round(completed_days / max(1, days), 3)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"habit_id": habit_id})
                return 0.0
        # Weekly habits
        weekly_target = 3 if habit.frequency == FREQ_3X_WEEK else habit.target_count
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT date_iso, count FROM habit_logs "
                "WHERE habit_id = ? AND completed = 1 AND date_iso >= ?",
                (habit_id, date_from))
            rows = [(r["date_iso"], int(r["count"])) for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return 0.0
        week_to_count: Dict[str, int] = {}
        for d_iso, c in rows:
            wk = start_of_week(d_iso, first_day=6)
            week_to_count[wk] = week_to_count.get(wk, 0) + c
        if not week_to_count:
            return 0.0
        hits = sum(1 for c in week_to_count.values() if c >= weekly_target)
        return round(hits / len(week_to_count), 3)

    # ------------------------------------------------------------------
    # Aggregations for UI
    # ------------------------------------------------------------------

    def for_date(self, date_iso: str) -> List[Dict[str, Any]]:
        """Return all habits with their completion status for the date."""
        out: List[Dict[str, Any]] = []
        for h in self.list_habits(active=True):
            log = self.get_log(h.id or 0, date_iso)
            out.append({
                "habit": h.to_dict(),
                "completed_today": bool(log and log.completed),
                "count": int(log.count) if log else 0,
                "streak": self.streak(h.id or 0),
                "best_streak": self.best_streak(h.id or 0),
                "completion_rate_30d": self.completion_rate(h.id or 0, 30),
            })
        return out

    def for_week(self, week_iso: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Return {date_iso: [habit_status, ...]} for the week containing week_iso."""
        anchor = week_iso or today_iso()
        start = start_of_week(anchor, first_day=6)
        end = end_of_week(anchor, first_day=6)
        out: Dict[str, List[Dict[str, Any]]] = {}
        from ..core.time_utils import range_days
        for d in range_days(start, end):
            out[d] = self.for_date(d)
        return out

    def trend(self, habit_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, completed, count}]`` for the last `days` days.

        Days with no log appear as ``{completed: False, count: 0}``.
        """
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        logs = {(l.date_iso): l for l in
                self.logs_for_habit(habit_id, date_from=date_from)}
        out: List[Dict[str, Any]] = []
        cursor = date_from
        from ..core.time_utils import range_days
        for d in range_days(date_from, today_iso()):
            l = logs.get(d)
            out.append({
                "date_iso": d,
                "completed": bool(l and l.completed),
                "count": int(l.count) if l else 0,
            })
        return out

    def count(self) -> int:
        try:
            cur = db.get_conn().execute("SELECT COUNT(*) AS c FROM habits")
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        except Exception:  # noqa: BLE001
            return 0

    # ------------------------------------------------------------------
    # Aggregate analytics for dashboards
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a dashboard summary dict for all active habits."""
        out: List[Dict[str, Any]] = []
        for h in self.list_habits(active=True):
            streak = self.streak(h.id or 0)
            best = self.best_streak(h.id or 0)
            rate_30d = self.completion_rate(h.id or 0, 30)
            out.append({
                "id": h.id,
                "name": h.name,
                "frequency": h.frequency,
                "color": h.color,
                "icon": h.icon,
                "target_count": h.target_count,
                "streak": streak,
                "best_streak": best,
                "completion_rate_30d": rate_30d,
                "completed_today": self.is_completed_today(h.id or 0),
            })
        # Sort: completed-today first, then by streak desc.
        out.sort(key=lambda x: (not x["completed_today"], -x["streak"]))
        return {
            "habits": out,
            "total_active": len(out),
            "completed_today_count": sum(1 for h in out if h["completed_today"]),
            "longest_current_streak": max((h["streak"] for h in out), default=0),
            "longest_best_streak": max((h["best_streak"] for h in out), default=0),
            "average_completion_rate_30d": (
                round(sum(h["completion_rate_30d"] for h in out) / len(out), 3)
                if out else 0.0
            ),
        }

    def leaderboard(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the top-N habits by current streak (for gamification)."""
        rows = []
        for h in self.list_habits(active=True):
            rows.append({
                "habit_id": h.id,
                "name": h.name,
                "frequency": h.frequency,
                "streak": self.streak(h.id or 0),
                "best": self.best_streak(h.id or 0),
                "completion_rate_30d": self.completion_rate(h.id or 0, 30),
            })
        rows.sort(key=lambda x: x["streak"], reverse=True)
        return rows[:limit]

    def consistency_score(self, days: int = 30) -> float:
        """Return a 0..1 score for how consistently the user is hitting
        at least one habit per day in the last `days` days.

        A score of 1.0 means every day had at least one completed habit.
        """
        date_from = add_days(today_iso(), -(days - 1))
        try:
            cur = db.get_conn().execute(
                "SELECT DISTINCT date_iso FROM habit_logs "
                "WHERE completed = 1 AND date_iso >= ?",
                (date_from,))
            hit_days = {r["date_iso"] for r in cur.fetchall()}
        except Exception:  # noqa: BLE001
            return 0.0
        if not hit_days:
            return 0.0
        from ..core.time_utils import range_days
        total_days = 0
        for d in range_days(date_from, today_iso()):
            total_days += 1
        if total_days == 0:
            return 0.0
        return round(len(hit_days) / total_days, 3)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

habit_service: HabitService = HabitService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== habits self-tests ===")
    try:
        hid = habit_service.add_habit("Test habit", frequency=FREQ_DAILY)
        assert hid > 0
        habit_service.log_completion(hid, date_iso=today_iso())
        assert habit_service.is_completed_today(hid)
        assert habit_service.streak(hid) == 1
        assert habit_service.completion_rate(hid, days=1) == 1.0
        habit_service.delete_habit(hid)
        print("  OK   basic CRUD + streak")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
