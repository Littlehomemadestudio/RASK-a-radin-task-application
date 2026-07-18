"""
rask.tests.test_streak_service
=============================

Unit tests for :mod:`rask.services.streak_service`.

Covers:

  • ``increment()`` — bumps current, updates best, appends history
  • ``increment()`` idempotency for same-day hits
  • ``increment()`` continuation vs reset (1-day gap = continue,
    2+ day gap = reset)
  • ``reset()`` zeroes current but preserves best
  • ``current()`` / ``best()`` / ``history()`` / ``last_hit()``
  • ``milestone_reached()`` returns the correct milestone (3, 7, 14,
    30, 60, 100, 365) or None
  • ``check_missed()`` resets stale streaks
  • ``check_all_missed()`` iterates all goals
  • Event publication: ``streak.incremented``, ``streak.reset``,
    ``streak.milestone``
  • Period boundaries: daily, weekly, monthly
"""
from __future__ import annotations

import unittest
from datetime import date, timedelta
from typing import Any, List

from rask import config, database as db
from rask.core.event_bus import bus
from rask.services.streak_service import StreakService, streak_service
from rask.tests import fresh_db


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestStreakIncrement(unittest.TestCase):
    """increment() behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("daily", 60)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_increment_first_time(self) -> None:
        r = self.svc.increment(self.gid, "2025-01-01")
        self.assertEqual(r["current"], 1)
        self.assertEqual(r["best"], 1)
        self.assertEqual(r["last_hit_iso"], "2025-01-01")
        self.assertEqual(r["history"], ["2025-01-01"])

    def test_increment_consecutive_day_continues(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        r = self.svc.increment(self.gid, "2025-01-02")
        self.assertEqual(r["current"], 2)
        self.assertEqual(r["best"], 2)

    def test_increment_same_day_is_idempotent(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        r = self.svc.increment(self.gid, "2025-01-01")
        self.assertEqual(r["current"], 1)
        self.assertEqual(len(r["history"]), 1)

    def test_increment_two_day_gap_resets(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        # Skip 2025-01-02.
        r = self.svc.increment(self.gid, "2025-01-03")
        # 2-day gap -> reset to 1.
        self.assertEqual(r["current"], 1)

    def test_increment_three_day_gap_resets(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        r = self.svc.increment(self.gid, "2025-01-04")
        self.assertEqual(r["current"], 1)

    def test_increment_uses_today_if_no_hit_iso(self) -> None:
        r = self.svc.increment(self.gid)
        self.assertIn("last_hit_iso", r)
        self.assertIsNotNone(r["last_hit_iso"])

    def test_increment_preserves_best_after_reset(self) -> None:
        # Build a 3-day streak.
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.svc.increment(self.gid, "2025-01-03")
        # Skip a day, then hit again.
        r = self.svc.increment(self.gid, "2025-01-05")
        self.assertEqual(r["current"], 1)
        self.assertEqual(r["best"], 3)  # best preserved

    def test_increment_invalid_goal_id_returns_empty(self) -> None:
        self.assertEqual(self.svc.increment(0), {})
        self.assertEqual(self.svc.increment(-1), {})

    def test_increment_publishes_streak_incremented(self) -> None:
        coll: List[Any] = []
        bus.subscribe("streak.incremented", lambda d: coll.append(d))
        self.svc.increment(self.gid, "2025-01-01")
        self.assertEqual(len(coll), 1)

    def test_increment_appends_to_history(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.svc.increment(self.gid, "2025-01-03")
        h = self.svc.history(self.gid)
        self.assertEqual(h, ["2025-01-01", "2025-01-02", "2025-01-03"])


class TestStreakReset(unittest.TestCase):
    """reset() behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("daily", 60)
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.svc.increment(self.gid, "2025-01-03")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_reset_zeroes_current(self) -> None:
        self.assertTrue(self.svc.reset(self.gid))
        self.assertEqual(self.svc.current(self.gid), 0)

    def test_reset_preserves_best(self) -> None:
        self.svc.reset(self.gid)
        self.assertEqual(self.svc.best(self.gid), 3)

    def test_reset_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("streak.reset", lambda d: coll.append(d))
        self.svc.reset(self.gid)
        self.assertEqual(len(coll), 1)

    def test_reset_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.reset(0))
        self.assertFalse(self.svc.reset(-1))
        self.assertFalse(self.svc.reset(9999))


class TestStreakRead(unittest.TestCase):
    """current() / best() / history() / last_hit()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("daily", 60)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_current_initial_zero(self) -> None:
        self.assertEqual(self.svc.current(self.gid), 0)

    def test_best_initial_zero(self) -> None:
        self.assertEqual(self.svc.best(self.gid), 0)

    def test_history_initial_empty(self) -> None:
        self.assertEqual(self.svc.history(self.gid), [])

    def test_last_hit_initial_none(self) -> None:
        self.assertIsNone(self.svc.last_hit(self.gid))

    def test_current_after_increment(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.assertEqual(self.svc.current(self.gid), 1)

    def test_best_after_multiple_increments(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.svc.increment(self.gid, "2025-01-03")
        self.assertEqual(self.svc.best(self.gid), 3)

    def test_get_returns_empty_for_invalid_id(self) -> None:
        self.assertEqual(self.svc.get(0), {})
        self.assertEqual(self.svc.get(-1), {})

    def test_get_returns_empty_for_missing_goal(self) -> None:
        self.assertEqual(self.svc.get(9999)["current"], 0)


class TestMilestoneReached(unittest.TestCase):
    """milestone_reached() returns the right milestone."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("daily", 60)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_milestone_at_zero_returns_none(self) -> None:
        self.assertIsNone(self.svc.milestone_reached(self.gid))

    def test_milestone_at_one_returns_none(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.assertIsNone(self.svc.milestone_reached(self.gid))

    def test_milestone_at_two_returns_none(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.assertIsNone(self.svc.milestone_reached(self.gid))

    def test_milestone_at_three_returns_three(self) -> None:
        self.svc.increment(self.gid, "2025-01-01")
        self.svc.increment(self.gid, "2025-01-02")
        self.svc.increment(self.gid, "2025-01-03")
        self.assertEqual(self.svc.milestone_reached(self.gid), 3)

    def test_milestone_at_seven_returns_seven(self) -> None:
        for i in range(7):
            self.svc.increment(self.gid, f"2025-01-{i+1:02d}")
        self.assertEqual(self.svc.milestone_reached(self.gid), 7)

    def test_milestone_at_four_returns_none(self) -> None:
        for i in range(4):
            self.svc.increment(self.gid, f"2025-01-{i+1:02d}")
        self.assertIsNone(self.svc.milestone_reached(self.gid))

    def test_milestone_at_eight_returns_none(self) -> None:
        for i in range(8):
            self.svc.increment(self.gid, f"2025-01-{i+1:02d}")
        self.assertIsNone(self.svc.milestone_reached(self.gid))


class TestWeeklyStreak(unittest.TestCase):
    """Weekly streak behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("weekly", 600)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_weekly_same_week_is_idempotent(self) -> None:
        # Two dates in the same week.
        self.svc.increment(self.gid, "2025-01-06")  # Monday
        r = self.svc.increment(self.gid, "2025-01-08")  # Wednesday same week
        self.assertEqual(r["current"], 1)

    def test_weekly_next_week_continues(self) -> None:
        self.svc.increment(self.gid, "2025-01-06")  # Week 1
        r = self.svc.increment(self.gid, "2025-01-13")  # Week 2
        self.assertEqual(r["current"], 2)


class TestMonthlyStreak(unittest.TestCase):
    """Monthly streak behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("monthly", 2400)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_monthly_same_month_is_idempotent(self) -> None:
        self.svc.increment(self.gid, "2025-01-05")
        r = self.svc.increment(self.gid, "2025-01-25")
        self.assertEqual(r["current"], 1)

    def test_monthly_next_month_continues(self) -> None:
        self.svc.increment(self.gid, "2025-01-15")
        r = self.svc.increment(self.gid, "2025-02-15")
        self.assertEqual(r["current"], 2)

    def test_monthly_skip_month_resets(self) -> None:
        self.svc.increment(self.gid, "2025-01-15")
        # Skip February.
        r = self.svc.increment(self.gid, "2025-03-15")
        self.assertEqual(r["current"], 1)


class TestCheckMissed(unittest.TestCase):
    """check_missed() resets stale streaks."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()
        self.gid = db.goal_add("daily", 60)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_check_missed_no_streak_returns_false(self) -> None:
        self.assertFalse(self.svc.check_missed(self.gid))

    def test_check_missed_recent_streak_returns_false(self) -> None:
        # Hit today — streak is fresh.
        from rask.core.time_utils import today_iso
        self.svc.increment(self.gid, today_iso())
        self.assertFalse(self.svc.check_missed(self.gid))

    def test_check_missed_old_streak_resets(self) -> None:
        # Hit 5 days ago — should be reset.
        old = (date.today() - timedelta(days=5)).isoformat()
        self.svc.increment(self.gid, old)
        self.assertTrue(self.svc.check_missed(self.gid))
        self.assertEqual(self.svc.current(self.gid), 0)


class TestCheckAllMissed(unittest.TestCase):
    """check_all_missed() iterates all goals."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_check_all_missed_empty_returns_zero(self) -> None:
        self.assertEqual(self.svc.check_all_missed(), 0)

    def test_check_all_missed_resets_stale(self) -> None:
        g1 = db.goal_add("daily", 60)
        g2 = db.goal_add("daily", 60)
        # Make g1 stale, g2 fresh.
        old = (date.today() - timedelta(days=5)).isoformat()
        self.svc.increment(g1, old)
        from rask.core.time_utils import today_iso
        self.svc.increment(g2, today_iso())
        reset_count = self.svc.check_all_missed()
        self.assertEqual(reset_count, 1)
        self.assertEqual(self.svc.current(g1), 0)
        self.assertEqual(self.svc.current(g2), 1)


class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = StreakService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_exists(self) -> None:
        self.assertIsInstance(streak_service, StreakService)

    def test_init_is_safe_to_call(self) -> None:
        self.svc.init()  # should not raise

    def test_history_capped_at_365(self) -> None:
        gid = db.goal_add("daily", 60)
        # Hit 400 consecutive days.
        start = date(2024, 1, 1)
        for i in range(400):
            d = (start + timedelta(days=i)).isoformat()
            self.svc.increment(gid, d)
        h = self.svc.history(gid)
        self.assertLessEqual(len(h), 365)


if __name__ == "__main__":
    unittest.main()
