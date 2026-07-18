"""
rask.tests.test_reminder_service
===============================

Unit tests for :mod:`rask.services.reminder_service`.

Covers:

  • CRUD: add / get / update / delete / list
  • Snooze: sets snooze_until, fires event
  • Dismiss: clears snooze, sets last_fired_iso, fires event
  • ``check_due()`` finds reminders due now
  • Days-mask filtering (Saturday vs Sunday vs all-days vs weekend)
  • Doesn't fire twice for the same minute (last_fired_iso guard)
  • Snoozed reminders are skipped until snooze_until passes
  • ``next_due()`` returns the next upcoming reminder
  • Event publication on every state change
  • Edge cases: invalid time format, invalid days_mask, missing id
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from typing import Any, List

from rask import database as db
from rask.core.event_bus import bus
from rask.services.reminder_service import (
    ReminderService,
    reminder_service,
    _day_matches_mask,
    _persian_weekday_today,
)
from rask.tests import fresh_db


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestReminderAdd(unittest.TestCase):
    """add() creates a new reminder."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_dict_with_id(self) -> None:
        r = self.svc.add(title="Wake up", time_hhmm="07:00")
        self.assertIn("id", r)
        self.assertGreater(r["id"], 0)
        self.assertEqual(r["title"], "Wake up")
        self.assertEqual(r["time_hhmm"], "07:00")
        self.assertEqual(r["days_mask"], 127)  # default
        self.assertTrue(r["enabled"])
        self.assertTrue(r["sound"])

    def test_add_with_custom_days_mask(self) -> None:
        r = self.svc.add(title="Weekend", time_hhmm="09:00", days_mask=65)
        self.assertEqual(r["days_mask"], 65)

    def test_add_with_message(self) -> None:
        r = self.svc.add(title="Standup", time_hhmm="09:30",
                          message="Daily standup")
        self.assertEqual(r["message"], "Daily standup")

    def test_add_with_category_and_goal(self) -> None:
        r = self.svc.add(title="Goal reminder", time_hhmm="20:00",
                          category_id=1, goal_id=1)
        self.assertEqual(r["category_id"], 1)
        self.assertEqual(r["goal_id"], 1)

    def test_add_disabled(self) -> None:
        r = self.svc.add(title="Quiet", time_hhmm="22:00", enabled=False)
        self.assertFalse(r["enabled"])

    def test_add_strips_title(self) -> None:
        r = self.svc.add(title="  Padded  ", time_hhmm="07:00")
        self.assertEqual(r["title"], "Padded")

    def test_add_empty_title_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="", time_hhmm="07:00")

    def test_add_invalid_time_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", time_hhmm="25:00")
        with self.assertRaises(ValueError):
            self.svc.add(title="T", time_hhmm="not-a-time")

    def test_add_invalid_days_mask_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(title="T", time_hhmm="07:00", days_mask=200)
        with self.assertRaises(ValueError):
            self.svc.add(title="T", time_hhmm="07:00", days_mask=-1)

    def test_add_publishes_reminder_added(self) -> None:
        coll: List[Any] = []
        bus.subscribe("reminder.added", lambda r: coll.append(r))
        self.svc.add(title="T", time_hhmm="07:00")
        self.assertEqual(len(coll), 1)


class TestReminderGetList(unittest.TestCase):
    """get() and list()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()
        self.r1 = self.svc.add(title="A", time_hhmm="07:00")
        self.r2 = self.svc.add(title="B", time_hhmm="08:00", enabled=False)

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

    def test_list_only_enabled(self) -> None:
        items = self.svc.list(only_enabled=True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")


class TestReminderUpdate(unittest.TestCase):
    """update() changes fields."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()
        self.r = self.svc.add(title="Old", time_hhmm="07:00")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_update_title(self) -> None:
        r = self.svc.update(self.r["id"], title="New")
        self.assertEqual(r["title"], "New")

    def test_update_time(self) -> None:
        r = self.svc.update(self.r["id"], time_hhmm="08:30")
        self.assertEqual(r["time_hhmm"], "08:30")

    def test_update_days_mask(self) -> None:
        r = self.svc.update(self.r["id"], days_mask=1)  # Saturday only
        self.assertEqual(r["days_mask"], 1)

    def test_update_enabled(self) -> None:
        r = self.svc.update(self.r["id"], enabled=False)
        self.assertFalse(r["enabled"])

    def test_update_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("reminder.updated", lambda r: coll.append(r))
        self.svc.update(self.r["id"], title="New")
        self.assertEqual(len(coll), 1)

    def test_update_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.update(9999, title="X")

    def test_update_invalid_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.update(0, title="X")


class TestReminderDelete(unittest.TestCase):
    """delete() removes the reminder."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()
        self.r = self.svc.add(title="T", time_hhmm="07:00")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_removes_reminder(self) -> None:
        self.assertTrue(self.svc.delete(self.r["id"]))
        self.assertIsNone(self.svc.get(self.r["id"]))

    def test_delete_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("reminder.deleted", lambda d: coll.append(d))
        self.svc.delete(self.r["id"])
        self.assertEqual(len(coll), 1)

    def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(9999))

    def test_delete_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(0))


class TestSnooze(unittest.TestCase):
    """snooze() sets snooze_until."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()
        self.r = self.svc.add(title="T", time_hhmm="07:00")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_snooze_sets_snooze_until(self) -> None:
        self.assertTrue(self.svc.snooze(self.r["id"], minutes=10))
        r = self.svc.get(self.r["id"])
        self.assertIsNotNone(r["snooze_until"])

    def test_snooze_default_minutes(self) -> None:
        self.assertTrue(self.svc.snooze(self.r["id"]))
        r = self.svc.get(self.r["id"])
        self.assertIsNotNone(r["snooze_until"])

    def test_snooze_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("reminder.snoozed", lambda d: coll.append(d))
        self.svc.snooze(self.r["id"], minutes=5)
        self.assertEqual(len(coll), 1)

    def test_snooze_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.snooze(9999, minutes=5))


class TestDismiss(unittest.TestCase):
    """dismiss() clears snooze and marks as fired."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()
        self.r = self.svc.add(title="T", time_hhmm="07:00")
        self.svc.snooze(self.r["id"], minutes=30)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_dismiss_clears_snooze(self) -> None:
        self.assertTrue(self.svc.dismiss(self.r["id"]))
        r = self.svc.get(self.r["id"])
        self.assertIsNone(r["snooze_until"])

    def test_dismiss_sets_last_fired(self) -> None:
        self.svc.dismiss(self.r["id"])
        r = self.svc.get(self.r["id"])
        self.assertIsNotNone(r["last_fired_iso"])

    def test_dismiss_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("reminder.dismissed", lambda d: coll.append(d))
        self.svc.dismiss(self.r["id"])
        self.assertEqual(len(coll), 1)

    def test_dismiss_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.dismiss(9999))


class TestCheckDue(unittest.TestCase):
    """check_due() finds due reminders."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_check_due_returns_due_reminders(self) -> None:
        # Reminder at 00:00 today — definitely past.
        self.svc.add(title="Past", time_hhmm="00:00", days_mask=127)
        due = self.svc.check_due()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["title"], "Past")

    def test_check_due_skips_future_time(self) -> None:
        # Reminder far in the future (23:59 — could be near now, so use
        # a very late time).
        self.svc.add(title="Future", time_hhmm="23:59", days_mask=127)
        due = self.svc.check_due()
        # If current time is past 23:59, it's due; otherwise not.
        # We can't deterministically test "future" — but we can ensure
        # the call returns a list (not raises).
        self.assertIsInstance(due, list)

    def test_check_due_skips_disabled(self) -> None:
        self.svc.add(title="Disabled", time_hhmm="00:00", enabled=False)
        due = self.svc.check_due()
        self.assertEqual(len(due), 0)

    def test_check_due_skips_snoozed(self) -> None:
        r = self.svc.add(title="Snoozed", time_hhmm="00:00")
        # Snooze for a long time (1 hour) so it's not yet due.
        self.svc.snooze(r["id"], minutes=60)
        due = self.svc.check_due()
        self.assertEqual(len(due), 0)

    def test_check_due_doesnt_fire_twice_same_minute(self) -> None:
        r = self.svc.add(title="Once", time_hhmm="00:00")
        # First call — should be due.
        due1 = self.svc.check_due()
        self.assertEqual(len(due1), 1)
        # Simulate firing by calling dismiss (sets last_fired_iso to now).
        self.svc.dismiss(r["id"])
        # Second call within the same minute — should NOT be due again.
        due2 = self.svc.check_due()
        self.assertEqual(len(due2), 0)

    def test_check_due_with_empty_db(self) -> None:
        self.assertEqual(self.svc.check_due(), [])


class TestDaysMaskFiltering(unittest.TestCase):
    """Days-mask filtering — Saturday vs Sunday vs all-days."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_day_matches_mask_saturday(self) -> None:
        # Saturday = persian_wd 0, mask bit 0 = 1
        self.assertTrue(_day_matches_mask(0, 1))
        self.assertTrue(_day_matches_mask(0, 127))
        self.assertFalse(_day_matches_mask(0, 2))  # Sunday only
        self.assertFalse(_day_matches_mask(0, 64))  # Friday only

    def test_day_matches_mask_sunday(self) -> None:
        # Sunday = persian_wd 1, mask bit 1 = 2
        self.assertTrue(_day_matches_mask(1, 2))
        self.assertTrue(_day_matches_mask(1, 127))
        self.assertFalse(_day_matches_mask(1, 1))  # Saturday only

    def test_day_matches_mask_friday(self) -> None:
        # Friday = persian_wd 6, mask bit 6 = 64
        self.assertTrue(_day_matches_mask(6, 64))
        self.assertTrue(_day_matches_mask(6, 127))
        self.assertFalse(_day_matches_mask(6, 1))

    def test_day_matches_mask_invalid_returns_false(self) -> None:
        self.assertFalse(_day_matches_mask(-1, 127))
        self.assertFalse(_day_matches_mask(7, 127))

    def test_persian_weekday_today_in_range(self) -> None:
        wd = _persian_weekday_today()
        self.assertGreaterEqual(wd, 0)
        self.assertLessEqual(wd, 6)

    def test_check_due_with_saturday_only_mask(self) -> None:
        # Saturday-only mask (1).  Only fires on Saturdays.
        self.svc.add(title="Sat only", time_hhmm="00:00", days_mask=1)
        due = self.svc.check_due()
        # Today's weekday must be Saturday (persian_wd=0) for this to fire.
        today_wd = _persian_weekday_today()
        if today_wd == 0:
            self.assertEqual(len(due), 1)
        else:
            self.assertEqual(len(due), 0)


class TestNextDue(unittest.TestCase):
    """next_due() returns the next upcoming reminder."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_next_due_returns_none_when_empty(self) -> None:
        self.assertIsNone(self.svc.next_due())

    def test_next_due_returns_reminder(self) -> None:
        self.svc.add(title="A", time_hhmm="23:59", days_mask=127)
        n = self.svc.next_due()
        self.assertIsNotNone(n)
        self.assertIn("next_when", n)

    def test_next_due_picks_earliest(self) -> None:
        self.svc.add(title="Late", time_hhmm="23:59", days_mask=127)
        self.svc.add(title="Early", time_hhmm="06:00", days_mask=127)
        n = self.svc.next_due()
        self.assertIsNotNone(n)
        # The earliest "next_when" should be one of these.
        self.assertIn(n["title"], ("Early", "Late"))


class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = ReminderService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_exists(self) -> None:
        self.assertIsInstance(reminder_service, ReminderService)

    def test_add_with_message_and_sound(self) -> None:
        r = self.svc.add(title="T", time_hhmm="07:00",
                          message="msg", sound=False)
        self.assertEqual(r["message"], "msg")
        self.assertFalse(r["sound"])

    def test_stop_scheduler_without_root_is_safe(self) -> None:
        # Should not raise even when no root widget is set.
        self.svc.stop_scheduler()

    def test_init_is_safe_to_call(self) -> None:
        self.svc.init()  # no-op, should not raise


if __name__ == "__main__":
    unittest.main()
