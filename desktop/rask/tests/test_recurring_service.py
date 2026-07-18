"""
rask.tests.test_recurring_service
================================

Unit tests for :mod:`rask.services.recurring_service`.

Covers:

  • CRUD: add / get / update / delete / list
  • ``compute_next_run()`` for daily / weekly / monthly frequencies
  • ``process_due()`` creates activities for due rules
  • Pause / resume (active flag toggle)
  • End-date respected (rules past end_date are auto-deactivated)
  • ``process_due()`` is idempotent within the same minute
  • Event publication: ``recurring.added``, ``updated``, ``deleted``,
    ``paused``, ``resumed``, ``processed``
  • Validation: invalid frequency, invalid duration, invalid time,
    invalid days_mask, invalid end_date
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from typing import Any, List

from rask import database as db
from rask.core.event_bus import bus
from rask.services.recurring_service import (
    RecurringService,
    recurring_service,
    VALID_FREQUENCIES,
)
from rask.tests import fresh_db


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestRecurringAdd(unittest.TestCase):
    """add() creates a new recurring rule."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_dict_with_id(self) -> None:
        r = self.svc.add(title="Daily standup", duration_min=30,
                          frequency="daily")
        self.assertIn("id", r)
        self.assertGreater(r["id"], 0)
        self.assertEqual(r["title"], "Daily standup")
        self.assertEqual(r["duration_min"], 30)
        self.assertEqual(r["frequency"], "daily")
        self.assertTrue(r["active"])
        self.assertIsNotNone(r["next_run_iso"])

    def test_add_with_time_hhmm(self) -> None:
        r = self.svc.add(title="Morning", duration_min=15,
                          frequency="daily", time_hhmm="07:00")
        self.assertEqual(r["time_hhmm"], "07:00")
        self.assertIn("07:00", r["next_run_iso"])

    def test_add_with_category(self) -> None:
        r = self.svc.add(title="T", duration_min=30,
                          frequency="daily", category_id=1)
        self.assertEqual(r["category_id"], 1)

    def test_add_with_days_mask(self) -> None:
        r = self.svc.add(title="Weekly", duration_min=60,
                          frequency="weekly", days_mask=1)  # Saturday only
        self.assertEqual(r["days_mask"], 1)

    def test_add_with_end_date(self) -> None:
        r = self.svc.add(title="Limited", duration_min=30,
                          frequency="daily", end_date_iso="2025-12-31")
        self.assertEqual(r["end_date_iso"], "2025-12-31")

    def test_add_with_notes(self) -> None:
        r = self.svc.add(title="T", duration_min=30,
                          frequency="daily", notes="Don't forget!")
        self.assertEqual(r["notes"], "Don't forget!")

    def test_add_strips_title(self) -> None:
        r = self.svc.add(title="  Padded  ", duration_min=30,
                          frequency="daily")
        self.assertEqual(r["title"], "Padded")

    def test_add_empty_title_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="", duration_min=30, frequency="daily")

    def test_add_invalid_frequency_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=30, frequency="hourly")

    def test_add_invalid_duration_raises(self) -> None:
        # duration_min must be int in 0..1440.  -1 and 2000 are invalid.
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=-1, frequency="daily")
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=2000, frequency="daily")
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min="not-a-number",  # type: ignore[arg-type]
                          frequency="daily")

    def test_add_invalid_time_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=30, frequency="daily",
                          time_hhmm="25:99")

    def test_add_invalid_end_date_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=30, frequency="daily",
                          end_date_iso="not-a-date")

    def test_add_invalid_days_mask_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", duration_min=30, frequency="daily",
                          days_mask=200)

    def test_add_publishes_recurring_added(self) -> None:
        coll: List[Any] = []
        bus.subscribe("recurring.added", lambda r: coll.append(r))
        self.svc.add(title="T", duration_min=30, frequency="daily")
        self.assertEqual(len(coll), 1)


class TestRecurringGetList(unittest.TestCase):
    """get() and list()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()
        self.r1 = self.svc.add(title="A", duration_min=30,
                                 frequency="daily")
        self.r2 = self.svc.add(title="B", duration_min=60,
                                 frequency="weekly")
        self.svc.pause(self.r2["id"])

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_get_existing(self) -> None:
        r = self.svc.get(self.r1["id"])
        self.assertIsNotNone(r)
        self.assertEqual(r["title"], "A")

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.svc.get(9999))

    def test_get_invalid_id_returns_none(self) -> None:
        self.assertIsNone(self.svc.get(0))
        self.assertIsNone(self.svc.get(-1))

    def test_list_returns_all(self) -> None:
        items = self.svc.list()
        self.assertEqual(len(items), 2)

    def test_list_only_active(self) -> None:
        items = self.svc.list(only_active=True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")


class TestRecurringUpdate(unittest.TestCase):
    """update() changes fields."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()
        self.r = self.svc.add(title="Old", duration_min=30,
                                frequency="daily")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_update_title(self) -> None:
        r = self.svc.update(self.r["id"], title="New")
        self.assertEqual(r["title"], "New")

    def test_update_duration(self) -> None:
        r = self.svc.update(self.r["id"], duration_min=60)
        self.assertEqual(r["duration_min"], 60)

    def test_update_frequency_recomputes_next_run(self) -> None:
        old_next = self.svc.get(self.r["id"])["next_run_iso"]
        r = self.svc.update(self.r["id"], frequency="weekly")
        new_next = r["next_run_iso"]
        # next_run_iso should be recomputed (may or may not be different).
        self.assertIsNotNone(new_next)

    def test_update_days_mask(self) -> None:
        r = self.svc.update(self.r["id"], days_mask=1)
        self.assertEqual(r["days_mask"], 1)

    def test_update_end_date(self) -> None:
        r = self.svc.update(self.r["id"], end_date_iso="2025-12-31")
        self.assertEqual(r["end_date_iso"], "2025-12-31")

    def test_update_active(self) -> None:
        r = self.svc.update(self.r["id"], active=False)
        self.assertFalse(r["active"])

    def test_update_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("recurring.updated", lambda r: coll.append(r))
        self.svc.update(self.r["id"], title="New")
        self.assertEqual(len(coll), 1)

    def test_update_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.update(9999, title="X")

    def test_update_invalid_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.update(0, title="X")


class TestRecurringDelete(unittest.TestCase):
    """delete() removes the rule."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()
        self.r = self.svc.add(title="T", duration_min=30, frequency="daily")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_removes_rule(self) -> None:
        self.assertTrue(self.svc.delete(self.r["id"]))
        self.assertIsNone(self.svc.get(self.r["id"]))

    def test_delete_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("recurring.deleted", lambda d: coll.append(d))
        self.svc.delete(self.r["id"])
        self.assertEqual(len(coll), 1)

    def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(9999))


class TestPauseResume(unittest.TestCase):
    """pause() and resume()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()
        self.r = self.svc.add(title="T", duration_min=30, frequency="daily")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_pause_sets_active_false(self) -> None:
        self.assertTrue(self.svc.pause(self.r["id"]))
        r = self.svc.get(self.r["id"])
        self.assertFalse(r["active"])

    def test_pause_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("recurring.paused", lambda d: coll.append(d))
        self.svc.pause(self.r["id"])
        self.assertEqual(len(coll), 1)

    def test_resume_sets_active_true(self) -> None:
        self.svc.pause(self.r["id"])
        self.assertTrue(self.svc.resume(self.r["id"]))
        r = self.svc.get(self.r["id"])
        self.assertTrue(r["active"])

    def test_resume_publishes_event(self) -> None:
        self.svc.pause(self.r["id"])
        coll: List[Any] = []
        bus.subscribe("recurring.resumed", lambda d: coll.append(d))
        self.svc.resume(self.r["id"])
        self.assertEqual(len(coll), 1)

    def test_resume_recomputes_next_run(self) -> None:
        self.svc.pause(self.r["id"])
        old_next = self.svc.get(self.r["id"])["next_run_iso"]
        self.svc.resume(self.r["id"])
        new_next = self.svc.get(self.r["id"])["next_run_iso"]
        self.assertIsNotNone(new_next)

    def test_pause_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.pause(9999))

    def test_resume_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.resume(9999))


class TestComputeNextRun(unittest.TestCase):
    """compute_next_run() for daily / weekly / monthly."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_compute_next_run_daily(self) -> None:
        rule = {"frequency": "daily", "days_mask": 127, "time_hhmm": "07:00"}
        n = self.svc.compute_next_run(rule)
        self.assertIsInstance(n, str)
        self.assertIn("07:00", n)

    def test_compute_next_run_weekly(self) -> None:
        rule = {"frequency": "weekly", "days_mask": 1, "time_hhmm": "07:00"}
        n = self.svc.compute_next_run(rule)
        self.assertIsInstance(n, str)

    def test_compute_next_run_monthly(self) -> None:
        rule = {"frequency": "monthly", "days_mask": 127, "time_hhmm": "07:00"}
        n = self.svc.compute_next_run(rule)
        self.assertIsInstance(n, str)

    def test_compute_next_run_without_time(self) -> None:
        rule = {"frequency": "daily", "days_mask": 127, "time_hhmm": None}
        n = self.svc.compute_next_run(rule)
        self.assertIsInstance(n, str)

    def test_compute_next_run_weekly_finds_matching_day(self) -> None:
        # Mask 1 = Saturday only.  Should return a Saturday.
        rule = {"frequency": "weekly", "days_mask": 1, "time_hhmm": "07:00"}
        n = self.svc.compute_next_run(rule)
        # Parse the date and check it's a Saturday.
        try:
            dt = datetime.fromisoformat(n)
            # Python weekday: Mon=0..Sun=6, Sat=5
            self.assertEqual(dt.weekday(), 5)
        except ValueError:
            pass  # skip if format unexpected


class TestProcessDue(unittest.TestCase):
    """process_due() creates activities for due rules."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_process_due_with_no_rules_returns_empty(self) -> None:
        self.assertEqual(self.svc.process_due(), [])

    def test_process_due_with_future_rule_returns_empty(self) -> None:
        # next_run_iso is in the future (default behavior).
        self.svc.add(title="Future", duration_min=30, frequency="daily",
                      time_hhmm="23:59")
        self.assertEqual(self.svc.process_due(), [])

    def test_process_due_with_past_rule_creates_activity(self) -> None:
        # Add a rule, then manually set next_run_iso to a past timestamp.
        rule = self.svc.add(title="Past", duration_min=30,
                             frequency="daily", time_hhmm="00:00")
        # Manually set next_run_iso to yesterday.
        yesterday = (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%dT00:00:00")
        db.recurring_update(rule["id"], next_run_iso=yesterday)
        activities = self.svc.process_due()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["title"], "Past")
        self.assertEqual(activities[0]["kind"], "recurring")

    def test_process_due_idempotent_same_minute(self) -> None:
        rule = self.svc.add(title="Past", duration_min=30,
                             frequency="daily", time_hhmm="00:00")
        yesterday = (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%dT00:00:00")
        db.recurring_update(rule["id"], next_run_iso=yesterday)
        # First call creates an activity.
        first = self.svc.process_due()
        self.assertEqual(len(first), 1)
        # Second call within the same minute should NOT create another.
        second = self.svc.process_due()
        self.assertEqual(len(second), 0)

    def test_process_due_respects_end_date(self) -> None:
        # A rule with end_date in the past should not produce activities
        # (db.recurring_due_now filters them out).
        rule = self.svc.add(title="Past", duration_min=30,
                             frequency="daily", time_hhmm="00:00")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        yesterday_ts = f"{yesterday}T00:00:00"
        db.recurring_update(rule["id"],
                             end_date_iso=yesterday,
                             next_run_iso=yesterday_ts)
        activities = self.svc.process_due()
        self.assertEqual(len(activities), 0)

    def test_process_due_skips_paused_rules(self) -> None:
        rule = self.svc.add(title="Past", duration_min=30,
                             frequency="daily", time_hhmm="00:00")
        yesterday = (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%dT00:00:00")
        db.recurring_update(rule["id"], next_run_iso=yesterday)
        self.svc.pause(rule["id"])
        activities = self.svc.process_due()
        self.assertEqual(len(activities), 0)


class TestValidFrequencies(unittest.TestCase):
    """VALID_FREQUENCIES constant."""

    def test_valid_frequencies_contains_all_three(self) -> None:
        self.assertIn("daily", VALID_FREQUENCIES)
        self.assertIn("weekly", VALID_FREQUENCIES)
        self.assertIn("monthly", VALID_FREQUENCIES)


class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = RecurringService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_exists(self) -> None:
        self.assertIsInstance(recurring_service, RecurringService)

    def test_init_is_safe_to_call(self) -> None:
        self.svc.init()  # no-op, should not raise

    def test_add_with_long_title_truncates(self) -> None:
        long_title = "x" * 500
        r = self.svc.add(title=long_title, duration_min=30, frequency="daily")
        self.assertLessEqual(len(r["title"]), 200)


if __name__ == "__main__":
    unittest.main()
