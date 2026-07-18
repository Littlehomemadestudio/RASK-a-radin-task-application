"""
rask.tests.test_goal_service
============================

Unit tests for :mod:`rask.services.goal_service`.

Covers:

  • ``add()`` with all parameters (period, target, category, title,
    color, reminder)
  • ``progress_for()`` for daily / weekly / monthly goals — current_min,
    percent, achieved, remaining, range_start/end
  • ``check_streaks()`` — increments streak on hit, idempotent per period
  • ``hit_today()`` / ``hit_date()``
  • ``goal_hit_rate()`` — fraction of last N days hit
  • Integration with ``streak_service`` (lazy import)
  • Integration with ``badge_service`` (milestone unlocks)
  • Event-bus publication (``goal.added`` / ``updated`` / ``deleted`` /
    ``goal.progress``)
"""
from __future__ import annotations

import unittest
from typing import List
from unittest.mock import patch

from rask import database as db
from rask.core.event_bus import bus
from rask.core.time_utils import add_days, today_iso
from rask.services.goal_service import GoalService, goal_service
from rask.tests import fresh_db


# =============================================================================
# === Helpers                                                                 ==
# =============================================================================

class _EventCollector:
    """Capture events for assertions."""

    def __init__(self) -> None:
        self.events: List[tuple] = []

    def __call__(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))


def _add_activities_on(date_iso: str, total_min: int) -> int:
    """Insert one activity totaling `total_min` minutes on `date_iso`."""
    return db.activity_add("X", None, total_min, date_iso)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestGoalAdd(unittest.TestCase):
    """GoalService.add()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_daily_returns_dict(self) -> None:
        g = self.svc.add("daily", 120)
        self.assertIn("id", g)
        self.assertGreater(g["id"], 0)
        self.assertEqual(g["period"], "daily")
        self.assertEqual(g["target_minutes"], 120)

    def test_add_weekly(self) -> None:
        g = self.svc.add("weekly", 600)
        self.assertEqual(g["period"], "weekly")

    def test_add_monthly(self) -> None:
        g = self.svc.add("monthly", 2400)
        self.assertEqual(g["period"], "monthly")

    def test_add_with_category(self) -> None:
        g = self.svc.add("daily", 60, category_id=1)
        self.assertEqual(g["category_id"], 1)

    def test_add_with_title(self) -> None:
        g = self.svc.add("daily", 60, title="Morning focus")
        self.assertEqual(g["title"], "Morning focus")

    def test_add_with_color(self) -> None:
        g = self.svc.add("daily", 60, color="#FF0000")
        self.assertEqual(g["color"], "#FF0000")

    def test_add_publishes_goal_added(self) -> None:
        collector = _EventCollector()
        bus.subscribe("goal.added", collector)
        self.svc.add("daily", 60)
        self.assertEqual(len(collector.events), 1)

    def test_add_initializes_streak_row(self) -> None:
        g = self.svc.add("daily", 60)
        s = db.streak_get(g["id"])
        self.assertIsNotNone(s)
        self.assertEqual(s["current"], 0)

    def test_add_invalid_period_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add("hourly", 60)

    def test_add_target_minutes_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add("daily", 0)

    def test_add_target_minutes_too_large_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add("daily", 10001)

    def test_add_negative_target_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add("daily", -1)


class TestGoalUpdate(unittest.TestCase):
    """GoalService.update()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()
        self.gid = self.svc.add("daily", 60)["id"]

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_update_target(self) -> None:
        g = self.svc.update(self.gid, target_minutes=120)
        self.assertEqual(g["target_minutes"], 120)

    def test_update_period(self) -> None:
        g = self.svc.update(self.gid, period="weekly")
        self.assertEqual(g["period"], "weekly")

    def test_update_title(self) -> None:
        g = self.svc.update(self.gid, title="New title")
        self.assertEqual(g["title"], "New title")

    def test_update_publishes_goal_updated(self) -> None:
        collector = _EventCollector()
        bus.subscribe("goal.updated", collector)
        self.svc.update(self.gid, target_minutes=90)
        self.assertEqual(len(collector.events), 1)

    def test_update_nonexistent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.update(9999, target_minutes=100)

    def test_update_invalid_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.update(-1, target_minutes=100)

    def test_update_no_fields_returns_existing(self) -> None:
        g = self.svc.update(self.gid)
        self.assertEqual(g["id"], self.gid)

    def test_update_active_flag(self) -> None:
        g = self.svc.update(self.gid, active=False)
        self.assertFalse(g["active"])


class TestGoalDelete(unittest.TestCase):
    """GoalService.delete()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()
        self.gid = self.svc.add("daily", 60)["id"]

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_returns_true(self) -> None:
        self.assertTrue(self.svc.delete(self.gid))

    def test_delete_removes_goal(self) -> None:
        self.svc.delete(self.gid)
        self.assertIsNone(self.svc.get(self.gid))

    def test_delete_cascades_to_streak(self) -> None:
        self.svc.delete(self.gid)
        self.assertIsNone(db.streak_get(self.gid))

    def test_delete_publishes_goal_deleted(self) -> None:
        collector = _EventCollector()
        bus.subscribe("goal.deleted", collector)
        self.svc.delete(self.gid)
        self.assertEqual(len(collector.events), 1)

    def test_delete_nonexistent_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(9999))


class TestProgressFor(unittest.TestCase):
    """GoalService.progress_for()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_progress_daily_no_activities(self) -> None:
        gid = self.svc.add("daily", 60)["id"]
        p = self.svc.progress_for(gid, "2025-01-01")
        self.assertEqual(p["current_min"], 0)
        self.assertEqual(p["target_min"], 60)
        self.assertEqual(p["percent"], 0.0)
        self.assertFalse(p["achieved"])
        self.assertEqual(p["remaining_min"], 60)

    def test_progress_daily_with_activity_below_target(self) -> None:
        gid = self.svc.add("daily", 60)["id"]
        _add_activities_on("2025-01-01", 30)
        p = self.svc.progress_for(gid, "2025-01-01")
        self.assertEqual(p["current_min"], 30)
        self.assertAlmostEqual(p["percent"], 50.0, places=1)
        self.assertFalse(p["achieved"])
        self.assertEqual(p["remaining_min"], 30)

    def test_progress_daily_with_activity_at_target(self) -> None:
        gid = self.svc.add("daily", 60)["id"]
        _add_activities_on("2025-01-01", 60)
        p = self.svc.progress_for(gid, "2025-01-01")
        self.assertTrue(p["achieved"])
        self.assertEqual(p["percent"], 100.0)
        self.assertEqual(p["remaining_min"], 0)

    def test_progress_daily_with_activity_above_target(self) -> None:
        gid = self.svc.add("daily", 60)["id"]
        _add_activities_on("2025-01-01", 120)
        p = self.svc.progress_for(gid, "2025-01-01")
        # Percent is capped at 100.
        self.assertEqual(p["percent"], 100.0)
        self.assertTrue(p["achieved"])

    def test_progress_weekly_range(self) -> None:
        gid = self.svc.add("weekly", 600)["id"]
        p = self.svc.progress_for(gid, "2025-03-25")
        # Range_start should be Saturday of that week.
        self.assertEqual(p["range_start"], "2025-03-22")
        self.assertEqual(p["range_end"], "2025-03-28")

    def test_progress_monthly_range(self) -> None:
        gid = self.svc.add("monthly", 2400)["id"]
        p = self.svc.progress_for(gid, "2025-03-15")
        self.assertEqual(p["range_start"], "2025-03-01")
        self.assertEqual(p["range_end"], "2025-03-31")

    def test_progress_for_nonexistent_goal_returns_empty(self) -> None:
        self.assertEqual(self.svc.progress_for(9999, "2025-01-01"), {})

    def test_progress_uses_today_by_default(self) -> None:
        gid = self.svc.add("daily", 60)["id"]
        _add_activities_on(today_iso(), 30)
        p = self.svc.progress_for(gid)
        self.assertEqual(p["date_iso"], today_iso())
        self.assertEqual(p["current_min"], 30)

    def test_progress_with_category_filter(self) -> None:
        gid = self.svc.add("daily", 60, category_id=1)["id"]
        # Add activity in category 1.
        db.activity_add("Cat1", 1, 30, "2025-01-01")
        # Add activity in category 2 (should be ignored).
        db.activity_add("Cat2", 2, 100, "2025-01-01")
        p = self.svc.progress_for(gid, "2025-01-01")
        self.assertEqual(p["current_min"], 30)


class TestProgressListHelpers(unittest.TestCase):
    """progress_daily / progress_weekly / progress_monthly."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()
        self.daily = self.svc.add("daily", 60)["id"]
        self.weekly = self.svc.add("weekly", 600)["id"]
        self.monthly = self.svc.add("monthly", 2400)["id"]

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_progress_daily_returns_only_daily(self) -> None:
        out = self.svc.progress_daily("2025-01-01")
        # The default seeded goal is also daily, so we have 2 daily goals.
        self.assertEqual(len(out), 2)
        for p in out:
            self.assertEqual(p["period"], "daily")

    def test_progress_weekly_returns_only_weekly(self) -> None:
        out = self.svc.progress_weekly("2025-01-01")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["period"], "weekly")

    def test_progress_monthly_returns_only_monthly(self) -> None:
        out = self.svc.progress_monthly("2025-01-01")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["period"], "monthly")

    def test_progress_daily_excludes_inactive_goals(self) -> None:
        self.svc.update(self.daily, active=False)
        # Default goal is still active.
        out = self.svc.progress_daily("2025-01-01")
        self.assertEqual(len(out), 1)


class TestHitChecks(unittest.TestCase):
    """hit_today / hit_date / check_streaks."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()
        self.gid = self.svc.add("daily", 60)["id"]

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_hit_date_returns_false_when_not_achieved(self) -> None:
        _add_activities_on("2025-01-01", 30)
        self.assertFalse(self.svc.hit_date(self.gid, "2025-01-01"))

    def test_hit_date_returns_true_when_achieved(self) -> None:
        _add_activities_on("2025-01-01", 60)
        self.assertTrue(self.svc.hit_date(self.gid, "2025-01-01"))

    def test_hit_date_increments_streak(self) -> None:
        _add_activities_on("2025-01-01", 60)
        self.svc.hit_date(self.gid, "2025-01-01")
        from rask.services.streak_service import streak_service
        self.assertEqual(streak_service.current(self.gid), 1)

    def test_hit_date_idempotent_same_period(self) -> None:
        _add_activities_on("2025-01-01", 60)
        self.svc.hit_date(self.gid, "2025-01-01")
        self.svc.hit_date(self.gid, "2025-01-01")  # second call
        from rask.services.streak_service import streak_service
        # Should still be 1, not 2.
        self.assertEqual(streak_service.current(self.gid), 1)

    def test_hit_date_publishes_goal_progress(self) -> None:
        collector = _EventCollector()
        bus.subscribe("goal.progress", collector)
        _add_activities_on("2025-01-01", 60)
        self.svc.hit_date(self.gid, "2025-01-01")
        self.assertEqual(len(collector.events), 1)

    def test_hit_today_uses_today(self) -> None:
        _add_activities_on(today_iso(), 60)
        self.assertTrue(self.svc.hit_today(self.gid))

    def test_check_streaks_returns_hit_goals(self) -> None:
        _add_activities_on(today_iso(), 60)
        hits = self.svc.check_streaks()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["goal_id"], self.gid)

    def test_check_streaks_no_hits_returns_empty(self) -> None:
        # No activities today — no hits.
        hits = self.svc.check_streaks()
        self.assertEqual(len(hits), 0)

    def test_hit_date_multiple_days_increments_streak(self) -> None:
        from rask.services.streak_service import streak_service
        _add_activities_on("2025-01-01", 60)
        _add_activities_on("2025-01-02", 60)
        self.svc.hit_date(self.gid, "2025-01-01")
        # Need to clear the in-memory cache between days — the service
        # caches by period_key (range_start = date for daily goals).
        self.svc._hit_cache.clear()
        self.svc.hit_date(self.gid, "2025-01-02")
        self.assertEqual(streak_service.current(self.gid), 2)


class TestGoalHitRate(unittest.TestCase):
    """GoalService.goal_hit_rate()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()
        self.gid = self.svc.add("daily", 60)["id"]

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_hit_rate_no_history_returns_zero(self) -> None:
        self.assertEqual(self.svc.goal_hit_rate(self.gid, days=7), 0.0)

    def test_hit_rate_with_one_hit_in_last_7_days(self) -> None:
        # Manually increment streak history for today.
        _add_activities_on(today_iso(), 60)
        self.svc.hit_today(self.gid)
        rate = self.svc.goal_hit_rate(self.gid, days=7)
        # 1 hit out of 7 days = ~0.143.
        self.assertAlmostEqual(rate, 1 / 7, places=2)

    def test_hit_rate_zero_days_returns_zero(self) -> None:
        self.assertEqual(self.svc.goal_hit_rate(self.gid, days=0), 0.0)

    def test_hit_rate_for_nonexistent_goal_returns_zero(self) -> None:
        self.assertEqual(self.svc.goal_hit_rate(9999, days=7), 0.0)


class TestIntegrationWithStreakService(unittest.TestCase):
    """Goal hits propagate to streak_service."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_streak_history_grows_with_hits(self) -> None:
        from rask.services.streak_service import streak_service
        gid = self.svc.add("daily", 60)["id"]
        _add_activities_on("2025-01-01", 60)
        self.svc.hit_date(gid, "2025-01-01")
        self.assertEqual(len(streak_service.history(gid)), 1)
        self.svc._hit_cache.clear()
        _add_activities_on("2025-01-02", 60)
        self.svc.hit_date(gid, "2025-01-02")
        self.assertEqual(len(streak_service.history(gid)), 2)

    def test_streak_best_updates_with_multiple_hits(self) -> None:
        from rask.services.streak_service import streak_service
        gid = self.svc.add("daily", 60)["id"]
        for d in ("2025-01-01", "2025-01-02", "2025-01-03"):
            _add_activities_on(d, 60)
            self.svc.hit_date(gid, d)
            self.svc._hit_cache.clear()
        self.assertEqual(streak_service.best(gid), 3)


class TestIntegrationWithBadgeService(unittest.TestCase):
    """Goal hits can trigger streak milestones → badge unlocks."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_streak_3_milestone_unlocks_badge(self) -> None:
        """Hitting a goal 3 days in a row unlocks the streak_3 badge."""
        from rask.services.badge_service import badge_service
        gid = self.svc.add("daily", 60)["id"]
        # The first hit should NOT unlock streak_3 (only 1 day).
        _add_activities_on("2025-01-01", 60)
        self.svc.hit_date(gid, "2025-01-01")
        self.assertFalse(badge_service.has("streak_3"))
        # Second day.
        self.svc._hit_cache.clear()
        _add_activities_on("2025-01-02", 60)
        self.svc.hit_date(gid, "2025-01-02")
        self.assertFalse(badge_service.has("streak_3"))
        # Third day — should unlock streak_3.
        self.svc._hit_cache.clear()
        _add_activities_on("2025-01-03", 60)
        self.svc.hit_date(gid, "2025-01-03")
        self.assertTrue(badge_service.has("streak_3"))

    def test_milestone_unlock_publishes_badge_event(self) -> None:
        collector = _EventCollector()
        bus.subscribe("badge.unlocked", collector)
        gid = self.svc.add("daily", 60)["id"]
        for d in ("2025-01-01", "2025-01-02", "2025-01-03"):
            _add_activities_on(d, 60)
            self.svc.hit_date(gid, d)
            self.svc._hit_cache.clear()
        self.assertGreaterEqual(len(collector.events), 1)


class TestReorderAndCleanup(unittest.TestCase):
    """Reorder / delete_category_goals_cleanup."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = GoalService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_reorder_valid_ids_returns_true(self) -> None:
        g1 = self.svc.add("daily", 30)["id"]
        g2 = self.svc.add("daily", 60)["id"]
        self.assertTrue(self.svc.reorder([g2, g1]))

    def test_reorder_invalid_id_returns_false(self) -> None:
        g1 = self.svc.add("daily", 30)["id"]
        self.assertFalse(self.svc.reorder([g1, 9999]))

    def test_reorder_empty_returns_false(self) -> None:
        self.assertFalse(self.svc.reorder([]))

    def test_reorder_publishes_event(self) -> None:
        collector = _EventCollector()
        bus.subscribe("goal.reordered", collector)
        g1 = self.svc.add("daily", 30)["id"]
        self.svc.reorder([g1])
        self.assertEqual(len(collector.events), 1)

    def test_delete_category_goals_cleanup(self) -> None:
        gid = self.svc.add("daily", 60, category_id=1)["id"]
        count = self.svc.delete_category_goals_cleanup(1)
        self.assertEqual(count, 1)
        # category_id should be None now.
        g = self.svc.get(gid)
        self.assertIsNone(g["category_id"])


class TestModuleSingleton(unittest.TestCase):
    """Module-level singleton works."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_is_goal_service(self) -> None:
        self.assertIsInstance(goal_service, GoalService)

    def test_singleton_add_works(self) -> None:
        g = goal_service.add("daily", 60)
        self.assertGreater(g["id"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
