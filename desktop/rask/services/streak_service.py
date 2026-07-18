"""
rask.services.streak_service
============================

Per-goal streak counters.

Each goal (daily / weekly / monthly) tracks a streak: the number of
consecutive periods in which the goal's target was met.  This service
handles:

  • Incrementing a streak when a goal is hit (called from goal_service)
  • Resetting a streak when a period is missed (called by the scheduler)
  • Detecting milestone unlocks (3, 7, 14, 30, 60, 100, 365 days) and
    triggering :func:`badge_service.unlock` for the corresponding badge
  • Publishing ``streak.incremented`` / ``streak.reset`` events

The "period" depends on the goal:
  - daily   -> calendar days
  - weekly  -> weeks (since the start of the streak)
  - monthly -> months

Mirrors the ``bumpStreak`` function in ``web/js/timer.js``.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    days_between,
    end_of_month,
    end_of_week,
    start_of_month,
    start_of_week,
    today_iso,
)

__all__ = ["StreakService", "streak_service"]

_log = get_logger("services.streak")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _row_to_streak(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB streak row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    raw = out.pop("history_json", None)
    if isinstance(raw, str) and raw:
        try:
            out["history"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            out["history"] = []
    elif isinstance(raw, list):
        out["history"] = list(raw)
    else:
        out["history"] = []
    return out


def _milestone_for(current: int) -> Optional[int]:
    """Return the milestone equal to `current`, if any.

    A streak "reaches" a milestone exactly once — when its current
    value equals one of :data:`config.STREAK_MILESTONES`.
    """
    if current <= 0:
        return None
    if current in config.STREAK_MILESTONES:
        return current
    return None


def _streak_period_goal(goal: Optional[Dict[str, Any]]) -> str:
    """Return 'daily' / 'weekly' / 'monthly' for a goal dict."""
    if not goal:
        return "daily"
    return goal.get("period", "daily")


# =============================================================================
# === StreakService                                                          ===
# =============================================================================

class StreakService:
    """Per-goal streak counters with milestone detection."""

    def __init__(self) -> None:
        # Cache of goal_id -> last known current streak, to detect
        # milestone crossings without re-reading the DB.  We always
        # read fresh on demand; the cache is just for the
        # milestone_reached() helper.
        self._last_known: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Pre-load all streaks into the cache for milestone detection."""
        try:
            for goal in db.goal_list():
                s = db.streak_get(goal["id"])
                if s:
                    self._last_known[goal["id"]] = int(s.get("current", 0))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        _log.debug("StreakService initialized (cache: %d goals)",
                   len(self._last_known))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, goal_id: int) -> Dict[str, Any]:
        """Return the streak for `goal_id`, creating an empty one if missing.

        Always returns a dict (never ``None``) so callers can index
        safely.  If the goal does not exist, returns an empty dict.
        """
        if not isinstance(goal_id, int) or goal_id <= 0:
            return {}
        try:
            s = db.streak_get(goal_id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            return {}
        if s is None:
            return {
                "goal_id": goal_id,
                "current": 0,
                "best": 0,
                "last_hit_iso": None,
                "history": [],
            }
        return _row_to_streak(s) or {}

    def current(self, goal_id: int) -> int:
        """Return the current streak value for `goal_id` (0 if unknown)."""
        return int(self.get(goal_id).get("current", 0))

    def best(self, goal_id: int) -> int:
        """Return the best (longest) streak ever for `goal_id`."""
        return int(self.get(goal_id).get("best", 0))

    def last_hit(self, goal_id: int) -> Optional[str]:
        """Return the ISO date of the last streak hit, or ``None``."""
        return self.get(goal_id).get("last_hit_iso")

    def history(self, goal_id: int) -> List[str]:
        """Return the list of ISO dates when this goal was hit (oldest first)."""
        return list(self.get(goal_id).get("history", []))

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def increment(self, goal_id: int, hit_iso: Optional[str] = None) -> Dict[str, Any]:
        """Increment the streak for `goal_id`.

        Idempotent for the same `hit_iso` — calling twice with the
        same date does not double-count.  Computes the new "current"
        value based on the gap between `hit_iso` and the previous
        ``last_hit_iso``:

          - Same period as last hit -> no-op (return current state)
          - Exactly one period after -> current += 1
          - Any larger gap -> reset current to 1

        "Period" depends on the goal: day / week / month.

        Publishes ``streak.incremented`` and, if a milestone is
        crossed, also calls :func:`badge_service.unlock`.
        """
        if not isinstance(goal_id, int) or goal_id <= 0:
            return {}

        if hit_iso is None:
            hit_iso = today_iso()
        # Normalize to date-only
        hit_iso = hit_iso[:10]

        # Look up the goal to determine the period.
        try:
            goal = db.goal_get(goal_id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            goal = None
        period = _streak_period_goal(goal)

        streak = self.get(goal_id)
        last_hit = streak.get("last_hit_iso")
        prev_current = int(streak.get("current", 0))

        # Idempotent: same period
        if last_hit and self._is_same_period(last_hit, hit_iso, period):
            # No increment, but ensure best is updated if current > best
            # (this shouldn't normally happen — best is set when current
            # increases — but be defensive).
            if prev_current > int(streak.get("best", 0)):
                try:
                    db.streak_update(goal_id, best=prev_current)
                except Exception as exc:  # noqa: BLE001
                    log_exception(_log, exc, {"goal_id": goal_id})
            return streak

        # Determine if this is a continuation (exactly one period after)
        # or a reset.
        is_continuation = self._is_next_period(last_hit, hit_iso, period) \
            if last_hit else False

        new_current = prev_current + 1 if is_continuation else 1
        new_best = max(int(streak.get("best", 0)), new_current)
        history = list(streak.get("history", []))
        history.append(hit_iso)
        # Cap history at 365 entries (matches DB layer behavior).
        history = history[-365:]

        try:
            db.streak_update(
                goal_id,
                current=new_current,
                best=new_best,
                last_hit_iso=hit_iso,
                history=history,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            return streak

        updated = {
            "goal_id": goal_id,
            "current": new_current,
            "best": new_best,
            "last_hit_iso": hit_iso,
            "history": history,
            "period": period,
        }

        bus.publish("streak.incremented", updated)
        self._last_known[goal_id] = new_current
        _log.info("Streak for goal %s: %d (best %d)",
                  goal_id, new_current, new_best)

        # Milestone check
        milestone = _milestone_for(new_current)
        if milestone is not None:
            self._on_milestone(goal_id, milestone)

        return updated

    def reset(self, goal_id: int) -> bool:
        """Reset the current streak to 0 (best is preserved).

        Publishes ``streak.reset``.  Returns ``True`` if a row was
        updated.
        """
        if not isinstance(goal_id, int) or goal_id <= 0:
            return False
        try:
            ok = db.streak_reset(goal_id, zero_out=True)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            return False
        if ok:
            self._last_known[goal_id] = 0
            bus.publish("streak.reset", {"goal_id": goal_id})
            _log.info("Streak reset for goal %s", goal_id)
        return ok

    # ------------------------------------------------------------------
    # Period-boundary helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_same_period(iso_a: str, iso_b: str, period: str) -> bool:
        """Return True if both dates fall within the same goal period."""
        try:
            a = date.fromisoformat(iso_a[:10])
            b = date.fromisoformat(iso_b[:10])
        except ValueError:
            return False
        if period == "daily":
            return a == b
        if period == "weekly":
            # Use Saturday-first week boundaries.
            sa = start_of_week(a.isoformat())
            sb = start_of_week(b.isoformat())
            return sa == sb
        if period == "monthly":
            return a.year == b.year and a.month == b.month
        return a == b

    @staticmethod
    def _is_next_period(prev_iso: str, cur_iso: str, period: str) -> bool:
        """Return True if `cur_iso` is exactly one period after `prev_iso`."""
        try:
            prev = date.fromisoformat(prev_iso[:10])
            cur = date.fromisoformat(cur_iso[:10])
        except ValueError:
            return False
        if period == "daily":
            return (cur - prev).days == 1
        if period == "weekly":
            # 7 days, and not in the same week
            if StreakService._is_same_period(prev_iso, cur_iso, "weekly"):
                return False
            return 7 <= (cur - prev).days <= 13
        if period == "monthly":
            if StreakService._is_same_period(prev_iso, cur_iso, "monthly"):
                return False
            # Same day of next month, or just "next month"
            months_diff = (cur.year - prev.year) * 12 + (cur.month - prev.month)
            return months_diff == 1
        return (cur - prev).days == 1

    # ------------------------------------------------------------------
    # Missed-day detection
    # ------------------------------------------------------------------

    def check_missed(self, goal_id: int) -> bool:
        """Check whether the streak for `goal_id` should be reset.

        Returns ``True`` if the streak was reset because a period was
        missed.  The check is based on the gap between ``last_hit_iso``
        and today: if more than one period has elapsed since the last
        hit (with a 1-period grace window), the streak is broken.

        For a daily goal: if last hit was >1 day ago (i.e. yesterday
        was missed), reset.
        For a weekly goal: if last hit was >1 week ago, reset.
        For a monthly goal: if last hit was >1 month ago, reset.
        """
        streak = self.get(goal_id)
        last_hit = streak.get("last_hit_iso")
        if not last_hit:
            return False  # no streak to break

        try:
            goal = db.goal_get(goal_id)
        except Exception:  # noqa: BLE001
            goal = None
        period = _streak_period_goal(goal)

        today = today_iso()
        try:
            last = date.fromisoformat(last_hit[:10])
            today_d = date.fromisoformat(today)
        except ValueError:
            return False

        if period == "daily":
            # Streak is broken if today is more than 1 day past last_hit
            # (i.e. yesterday was missed).
            if (today_d - last).days > 1:
                return self.reset(goal_id)
        elif period == "weekly":
            # Broken if we've passed a full week without a hit.
            if (today_d - last).days > 7:
                return self.reset(goal_id)
        elif period == "monthly":
            months_diff = (today_d.year - last.year) * 12 + \
                (today_d.month - last.month)
            if months_diff > 1:
                return self.reset(goal_id)
        return False

    # ------------------------------------------------------------------
    # Milestones
    # ------------------------------------------------------------------

    def milestone_reached(self, goal_id: int) -> Optional[int]:
        """Return the new milestone reached, if any.

        Compares the current streak to ``config.STREAK_MILESTONES``.
        Returns the milestone value (e.g. 7) if the current streak
        exactly equals it, otherwise ``None``.
        """
        return _milestone_for(self.current(goal_id))

    def _on_milestone(self, goal_id: int, milestone: int) -> None:
        """Internal: notify badge service and publish a milestone event.

        Wrapped in try/except so a broken badge service cannot break
        the streak flow.
        """
        try:
            # Lazy import to avoid a circular import at module load time.
            from .badge_service import badge_service
            badge_service.unlock(f"streak_{milestone}", metadata={
                "goal_id": goal_id,
                "milestone": milestone,
            })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id,
                                       "milestone": milestone})
        bus.publish("streak.milestone", {
            "goal_id": goal_id,
            "milestone": milestone,
        })

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def check_all_missed(self) -> int:
        """Run :meth:`check_missed` for every active goal.

        Returns the number of streaks that were reset.  Called by the
        daily scheduler (typically at app startup and at midnight).
        """
        count = 0
        try:
            goals = db.goal_list(only_active=True)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0
        for g in goals:
            try:
                if self.check_missed(g["id"]):
                    count += 1
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"goal_id": g.get("id")})
        if count:
            _log.info("Reset %d missed streaks", count)
        return count


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

streak_service: StreakService = StreakService()
