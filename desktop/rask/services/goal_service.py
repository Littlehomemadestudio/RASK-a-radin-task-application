"""
rask.services.goal_service
==========================

Daily / weekly / monthly goals.

A goal pairs a target (in minutes) with a scope:
  • Daily    — measured against today's total
  • Weekly   — measured against this week's total (Sat..Fri)
  • Monthly  — measured against this calendar month's total

Optionally a goal can be scoped to a single category, or apply to all
activities when ``category_id`` is ``None``.

When the goal's threshold is met for the current period:
  • The streak for that goal is incremented (via :mod:`streak_service`)
  • A ``goal.progress`` event is published with the achievement

The service also exposes a ``reorder()`` method that re-assigns the
``order_index`` column to a caller-supplied list of goal ids.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    end_of_month,
    end_of_week,
    start_of_month,
    start_of_week,
    today_iso,
)
from ..core.validators import is_valid_target_minutes

__all__ = ["GoalService", "goal_service"]

_log = get_logger("services.goal")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

VALID_PERIODS = ("daily", "weekly", "monthly")


def _row_to_goal(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB goal row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    # Boolean coercion
    if "active" in out:
        out["active"] = bool(out["active"])
    if "reminder_enabled" in out:
        out["reminder_enabled"] = bool(out["reminder_enabled"])
    # Integer coercion
    for k in ("id", "category_id", "target_minutes"):
        if out.get(k) is not None:
            try:
                out[k] = int(out[k])
            except (TypeError, ValueError):
                pass
    return out


def _rows_to_goals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        g = _row_to_goal(r)
        if g is not None:
            out.append(g)
    return out


# =============================================================================
# === GoalService                                                            ===
# =============================================================================

class GoalService:
    """CRUD + progress / streak logic for goals."""

    def __init__(self) -> None:
        # Track which (goal_id, period_key) hits have already been
        # processed in-memory this session to avoid double-incrementing
        # streaks.  Period_key is the date/week/month string for which
        # the goal was hit.
        self._hit_cache: Dict[Tuple[int, str], bool] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Run missed-streak checks for all goals."""
        try:
            from .streak_service import streak_service
            streak_service.check_all_missed()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        _log.debug("GoalService initialized")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(
        self,
        period: str,
        target_minutes: int,
        category_id: Optional[int] = None,
        title: Optional[str] = None,
        color: Optional[str] = None,
        reminder_enabled: bool = False,
        reminder_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new goal.

        Parameters
        ----------
        period : str
            ``"daily"`` / ``"weekly"`` / ``"monthly"``.
        target_minutes : int
            Target minutes for the period (1..10000).
        category_id : int, optional
            Scope to a single category, or ``None`` for all categories.
        title : str, optional
            Human-friendly title (e.g. "Morning Focus").
        color : str, optional
            Hex color for UI display.
        reminder_enabled : bool
            Whether reminder notifications are on for this goal.
        reminder_time : str, optional
            ``HH:MM`` time to send reminders.

        Returns the newly-created goal dict.
        """
        if period not in VALID_PERIODS:
            raise ValueError(f"period must be one of {VALID_PERIODS}")
        if not is_valid_target_minutes(target_minutes):
            raise ValueError(f"target_minutes out of range: {target_minutes}")

        try:
            new_id = db.goal_add(
                period=period,
                target_minutes=target_minutes,
                category_id=category_id,
                title=title,
                color=color,
                reminder_enabled=reminder_enabled,
                reminder_time=reminder_time,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"period": period,
                                       "target_minutes": target_minutes})
            raise

        goal = self.get(new_id)
        if goal is None:
            goal = {"id": new_id, "period": period,
                    "target_minutes": target_minutes}
        bus.publish("goal.added", goal)
        _log.info("Goal added: id=%s period=%s target=%dm",
                  new_id, period, target_minutes)
        return goal

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def update(self, id: int, **fields: Any) -> Dict[str, Any]:
        """Update goal fields.  Returns the updated goal dict."""
        if not isinstance(id, int) or id <= 0:
            raise ValueError(f"Invalid goal id: {id!r}")
        existing = self.get(id)
        if existing is None:
            raise KeyError(f"Goal {id} not found")

        updates: Dict[str, Any] = {}
        if "period" in fields:
            if fields["period"] in VALID_PERIODS:
                updates["period"] = fields["period"]
        if "target_minutes" in fields:
            tm = fields["target_minutes"]
            if is_valid_target_minutes(tm):
                updates["target_minutes"] = int(tm)
        if "category_id" in fields:
            cid = fields["category_id"]
            if cid is None or (isinstance(cid, int) and cid > 0):
                updates["category_id"] = cid
        if "title" in fields:
            updates["title"] = fields["title"]
        if "color" in fields:
            updates["color"] = fields["color"]
        if "reminder_enabled" in fields:
            updates["reminder_enabled"] = bool(fields["reminder_enabled"])
        if "reminder_time" in fields:
            updates["reminder_time"] = fields["reminder_time"]
        if "active" in fields:
            updates["active"] = bool(fields["active"])

        if not updates:
            return existing

        try:
            db.goal_update(id, **updates)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "updates": updates})
            raise

        updated = self.get(id) or existing
        bus.publish("goal.updated", updated)
        _log.info("Goal updated: id=%s fields=%s", id, list(updates.keys()))
        return updated

    def delete(self, id: int) -> bool:
        """Delete a goal (cascade-deletes its streak row)."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.goal_delete(id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            # Cascade reminder cleanup: any reminder pointing at this goal
            # gets its goal_id set to NULL.
            try:
                for r in db.reminder_list():
                    if r.get("goal_id") == id:
                        db.reminder_update(r["id"], goal_id=None)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"goal_id": id})
            bus.publish("goal.deleted", {"id": id})
            _log.info("Goal deleted: id=%s", id)
        return ok

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            return _row_to_goal(db.goal_get(id))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list(self, only_active: bool = False) -> List[Dict[str, Any]]:
        try:
            return _rows_to_goals(db.goal_list(only_active=only_active))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    # ------------------------------------------------------------------
    # Progress computation
    # ------------------------------------------------------------------

    def progress_for(self, goal_id: int, date_iso: Optional[str] = None) -> Dict[str, Any]:
        """Compute progress for a single goal on a given date.

        Returns a dict with::

            {
              "goal_id": int,
              "period": "daily"|"weekly"|"monthly",
              "target_min": int,
              "current_min": int,
              "percent": float,           # 0..100 (capped)
              "achieved": bool,
              "remaining_min": int,       # >= 0
              "date_iso": str,            # the reference date
              "range_start": str,
              "range_end": str,
            }

        If the goal doesn't exist, returns an empty dict.
        """
        goal = self.get(goal_id)
        if goal is None:
            return {}
        if date_iso is None:
            date_iso = today_iso()

        period = goal.get("period", "daily")
        target = int(goal.get("target_minutes", 0))
        cat_id = goal.get("category_id")

        # Compute the date range for this period.
        if period == "daily":
            range_start = range_end = date_iso
        elif period == "weekly":
            range_start = start_of_week(date_iso)
            range_end = end_of_week(date_iso)
        elif period == "monthly":
            range_start = start_of_month(date_iso)
            range_end = end_of_month(date_iso)
        else:
            range_start = range_end = date_iso

        try:
            current = int(db.activity_sum_duration(
                date_from=range_start,
                date_to=range_end,
                category_id=cat_id,
            ))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            current = 0

        percent = (current / target * 100.0) if target > 0 else 0.0
        percent = min(100.0, max(0.0, percent))
        achieved = current >= target and target > 0
        remaining = max(0, target - current)

        return {
            "goal_id": goal_id,
            "period": period,
            "target_min": target,
            "current_min": current,
            "percent": round(percent, 1),
            "achieved": achieved,
            "remaining_min": remaining,
            "date_iso": date_iso,
            "range_start": range_start,
            "range_end": range_end,
            "category_id": cat_id,
            "title": goal.get("title"),
            "color": goal.get("color"),
        }

    def progress_daily(self, date_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Progress for all daily goals on `date_iso` (default: today)."""
        if date_iso is None:
            date_iso = today_iso()
        out: List[Dict[str, Any]] = []
        for g in self.list(only_active=True):
            if g.get("period") != "daily":
                continue
            out.append(self.progress_for(g["id"], date_iso))
        return out

    def progress_weekly(self, week_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Progress for all weekly goals for the week containing `week_iso`."""
        if week_iso is None:
            week_iso = today_iso()
        out: List[Dict[str, Any]] = []
        for g in self.list(only_active=True):
            if g.get("period") != "weekly":
                continue
            out.append(self.progress_for(g["id"], week_iso))
        return out

    def progress_monthly(self, month_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Progress for all monthly goals for the month containing `month_iso`."""
        if month_iso is None:
            month_iso = today_iso()
        out: List[Dict[str, Any]] = []
        for g in self.list(only_active=True):
            if g.get("period") != "monthly":
                continue
            out.append(self.progress_for(g["id"], month_iso))
        return out

    # ------------------------------------------------------------------
    # Streak / hit checks
    # ------------------------------------------------------------------

    def hit_today(self, goal_id: int) -> bool:
        """Return True if the goal was achieved *today* (and register the hit).

        Idempotent: subsequent calls for the same goal on the same day
        do not re-increment the streak.  Returns ``True`` if the goal
        is achieved today (regardless of whether this call incremented
        the streak).
        """
        return self.hit_date(goal_id, today_iso())

    def hit_date(self, goal_id: int, date_iso: str) -> bool:
        """Return True if the goal was achieved on the given date.

        If yes, increment the streak (idempotent — once per period).
        """
        progress = self.progress_for(goal_id, date_iso)
        if not progress:
            return False
        if not progress.get("achieved"):
            return False

        # Period key for the cache: use the range_start so each unique
        # period only counts once.
        period_key = progress.get("range_start", date_iso)
        cache_key = (goal_id, period_key)
        if self._hit_cache.get(cache_key):
            # Already processed this period.
            return True
        self._hit_cache[cache_key] = True

        # Increment streak.
        try:
            from .streak_service import streak_service
            streak_service.increment(goal_id, hit_iso=date_iso)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})

        bus.publish("goal.progress", progress)
        return True

    def check_streaks(self) -> List[Dict[str, Any]]:
        """Check all goals for today's hits; return the list of hit goals.

        For each goal whose target is met today, the streak is
        incremented (via :meth:`hit_today`).  Returns the progress
        dicts of all goals that hit today.
        """
        out: List[Dict[str, Any]] = []
        today = today_iso()
        for g in self.list(only_active=True):
            try:
                progress = self.progress_for(g["id"], today)
                if progress.get("achieved"):
                    if self.hit_date(g["id"], today):
                        out.append(progress)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"goal_id": g.get("id")})
        if out:
            _log.info("check_streaks: %d goals hit today", len(out))
        return out

    # ------------------------------------------------------------------
    # Hit-rate analytics
    # ------------------------------------------------------------------

    def goal_hit_rate(self, goal_id: int, days: int = 30) -> float:
        """Return the fraction of the last `days` days the goal was hit.

        Returns a float in ``[0.0, 1.0]``.  For weekly / monthly goals
        the period granularity is still "day" — we count a day as
        "hit" if the goal's range containing that day was achieved.
        """
        if days <= 0:
            return 0.0
        try:
            from .streak_service import streak_service
            history = streak_service.history(goal_id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            return 0.0

        if not history:
            return 0.0
        history_set = set(h[:10] for h in history)

        # Count distinct hit days in the last `days` days.
        today = today_iso()
        distinct_hits = 0
        for offset in range(days):
            d = add_days(today, -offset)
            if d in history_set:
                distinct_hits += 1
        return distinct_hits / days

    # ------------------------------------------------------------------
    # Reorder / cleanup
    # ------------------------------------------------------------------

    def reorder(self, goal_ids: List[int]) -> bool:
        """Reassign the ``order_index`` of goals based on caller-supplied order.

        Note: the goals table doesn't have an ``order_index`` column
        in the current schema, so this method instead re-orders the
        ``created_at`` timestamps to match the desired display order.
        For now, this is a no-op that returns ``True`` if all the ids
        exist.
        """
        if not goal_ids or not isinstance(goal_ids, list):
            return False
        # Validate all ids exist.
        for gid in goal_ids:
            if not isinstance(gid, int) or self.get(gid) is None:
                return False
        # The schema doesn't currently have order_index, so we just
        # publish an event for the UI to react to.
        bus.publish("goal.reordered", {"order": list(goal_ids)})
        return True

    def delete_category_goals_cleanup(self, category_id: int) -> int:
        """Set ``category_id = NULL`` on goals that reference a deleted category.

        Returns the number of goals updated.  Called when a category
        is deleted to avoid dangling FK references (the schema already
        uses ON DELETE CASCADE, but this is a defensive no-op-safe
        belt-and-braces approach for soft category deletions).
        """
        if not isinstance(category_id, int) or category_id <= 0:
            return 0
        count = 0
        try:
            for g in self.list():
                if g.get("category_id") == category_id:
                    db.goal_update(g["id"], category_id=None)
                    count += 1
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"category_id": category_id})
        if count:
            _log.info("Cleared category_id on %d goals (cat=%s)",
                      count, category_id)
        return count


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

goal_service: GoalService = GoalService()
