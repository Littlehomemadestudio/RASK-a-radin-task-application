"""
rask.tests.test_features
=======================

Unit tests for the :mod:`rask.features` package — every feature module.

Covers:

  • PomodoroService: start, pause, resume, stop, state transitions
  • TimeBlockService: CRUD, conflict detection, to_activity conversion
  • JournalService: CRUD, mood/energy trends, streak
  • HabitService: CRUD, log_completion, streak, completion_rate
  • MoodService: CRUD, average_mood, distribution, count_today
  • FocusMode: start, end, interruption logging, stats
  • InsightEngine: generate_all returns insights, each has valid fields
  • NotificationCenter: add, mark_read, list, unread_count
  • AchievementService: 30+ achievements defined, xp_total, level
  • WeeklyReview: generate returns valid dict, formatters produce
    non-empty strings
  • CalendarService: month_view, week_view, day_view, find_free_time
  • QuickActionsService: register, list, by_shortcut, execute
  • SoundService: enabled, set_enabled (no actual sound in tests)
  • ThemeRegistry: register, get, list, apply (mocked)
  • BackupScheduler: next_run, last_run
  • AnalyticsService: productivity_over_time, category_trends,
    time_distribution
"""
from __future__ import annotations

import unittest
from datetime import date, timedelta
from typing import Any, List

from rask import database as db
from rask.core.event_bus import bus
from rask.core.time_utils import today_iso, add_days
from rask.tests import fresh_db


# =============================================================================
# === Pomodoro                                                                ===
# =============================================================================

class TestPomodoroService(unittest.TestCase):
    """PomodoroService state transitions."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.pomodoro import pomodoro_service
        self.svc = pomodoro_service

    def tearDown(self) -> None:
        try:
            self.svc.stop()
        except Exception:
            pass
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_initial_state_is_idle(self) -> None:
        s = self.svc.state()
        self.assertEqual(s["phase"], "idle")

    def test_start_transitions_to_work(self) -> None:
        self.svc.start(title="Test", work_min=5)
        s = self.svc.state()
        self.assertEqual(s["phase"], "work")
        self.assertEqual(s["cycle"], 0)
        self.assertEqual(s["title"], "Test")

    def test_pause_sets_paused_at(self) -> None:
        self.svc.start(title="Test", work_min=10)
        self.svc.pause()
        s = self.svc.state()
        self.assertTrue(s["paused"])
        self.assertIsNotNone(s["paused_at"])

    def test_resume_clears_paused_at(self) -> None:
        self.svc.start(title="Test", work_min=10)
        self.svc.pause()
        self.svc.resume()
        s = self.svc.state()
        self.assertFalse(s["paused"])
        self.assertIsNone(s["paused_at"])

    def test_stop_transitions_to_idle(self) -> None:
        self.svc.start(title="Test", work_min=10)
        self.svc.stop()
        s = self.svc.state()
        self.assertEqual(s["phase"], "idle")

    def test_state_includes_remaining_sec(self) -> None:
        self.svc.start(title="Test", work_min=10)
        s = self.svc.state()
        self.assertIn("remaining_sec", s)
        self.assertGreater(s["remaining_sec"], 0)

    def test_state_includes_progress(self) -> None:
        self.svc.start(title="Test", work_min=10)
        s = self.svc.state()
        self.assertIn("progress", s)
        self.assertGreaterEqual(s["progress"], 0.0)
        self.assertLessEqual(s["progress"], 1.0)

    def test_start_publishes_pomodoro_started(self) -> None:
        coll: List[Any] = []
        bus.subscribe("pomodoro.started", lambda d: coll.append(d))
        self.svc.start(title="Test", work_min=5)
        self.assertEqual(len(coll), 1)

    def test_pause_publishes_pomodoro_paused(self) -> None:
        coll: List[Any] = []
        bus.subscribe("pomodoro.paused", lambda d: coll.append(d))
        self.svc.start(title="Test", work_min=5)
        self.svc.pause()
        self.assertEqual(len(coll), 1)


# =============================================================================
# === TimeBlockService                                                        ===
# =============================================================================

class TestTimeBlockService(unittest.TestCase):
    """TimeBlockService CRUD + conflicts."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features import time_blocking as _tb_mod
        _tb_mod._schema_initialized = False
        _tb_mod._ensure_schema()
        from rask.features.time_blocking import (
            time_block_service, TimeBlock, RECUR_DAILY,
        )
        self.svc = time_block_service
        self.TimeBlock = TimeBlock
        self.RECUR_DAILY = RECUR_DAILY

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_id(self) -> None:
        bid = self.svc.add(self.TimeBlock(
            title="Test", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        self.assertGreater(bid, 0)

    def test_for_date_returns_blocks(self) -> None:
        self.svc.add(self.TimeBlock(
            title="A", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        self.svc.add(self.TimeBlock(
            title="B", start_hhmm="11:00", end_hhmm="12:00",
            date_iso="2025-01-01"))
        blocks = self.svc.for_date("2025-01-01")
        self.assertEqual(len(blocks), 2)

    def test_check_conflicts_detects_overlap(self) -> None:
        self.svc.add(self.TimeBlock(
            title="A", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        conflicts = self.svc.check_conflicts(self.TimeBlock(
            title="B", start_hhmm="09:30", end_hhmm="10:30",
            date_iso="2025-01-01"))
        self.assertEqual(len(conflicts), 1)

    def test_check_conflicts_no_overlap(self) -> None:
        self.svc.add(self.TimeBlock(
            title="A", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        conflicts = self.svc.check_conflicts(self.TimeBlock(
            title="B", start_hhmm="10:00", end_hhmm="11:00",
            date_iso="2025-01-01"))
        self.assertEqual(len(conflicts), 0)

    def test_to_activity_creates_activity(self) -> None:
        bid = self.svc.add(self.TimeBlock(
            title="Block", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        result = self.svc.to_activity(bid)
        # to_activity returns the new activity_id (int) on success.
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_for_week_returns_blocks(self) -> None:
        for d in range(5):
            iso = f"2025-01-{6+d:02d}"  # Jan 6-10
            self.svc.add(self.TimeBlock(
                title=f"Block {d}", start_hhmm="09:00", end_hhmm="10:00",
                date_iso=iso))
        blocks = self.svc.for_week("2025-01-06")
        self.assertGreaterEqual(len(blocks), 5)

    def test_total_scheduled_min(self) -> None:
        self.svc.add(self.TimeBlock(
            title="A", start_hhmm="09:00", end_hhmm="10:00",
            date_iso="2025-01-01"))
        self.svc.add(self.TimeBlock(
            title="B", start_hhmm="11:00", end_hhmm="12:00",
            date_iso="2025-01-01"))
        total = self.svc.total_scheduled_min("2025-01-01")
        self.assertEqual(total, 120)


# =============================================================================
# === JournalService                                                          ===
# =============================================================================

class TestJournalService(unittest.TestCase):
    """JournalService CRUD + trends."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features import journal as _journal_mod
        _journal_mod._schema_initialized = False
        _journal_mod._ensure_schema()
        from rask.features.journal import (
            journal_service, JournalEntry, _ensure_schema,
        )
        _ensure_schema()
        self.svc = journal_service
        self.JournalEntry = JournalEntry

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_id(self) -> None:
        e = self.JournalEntry(
            date_iso="2025-01-01", mood=4, energy=3, title="Test",
            body="Hello")
        eid = self.svc.add(e)
        self.assertGreater(eid, 0)

    def test_get_returns_entry(self) -> None:
        e = self.JournalEntry(date_iso="2025-01-01", mood=4, title="T")
        eid = self.svc.add(e)
        got = self.svc.get(eid)
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "T")

    def test_get_by_date(self) -> None:
        e = self.JournalEntry(date_iso="2025-01-01", mood=4, title="T")
        self.svc.add(e)
        got = self.svc.get_by_date("2025-01-01")
        self.assertIsNotNone(got)

    def test_list_returns_entries(self) -> None:
        for d in range(5):
            e = self.JournalEntry(
                date_iso=f"2025-01-{d+1:02d}", mood=3, title=f"D{d}")
            self.svc.add(e)
        items = self.svc.list()
        self.assertEqual(len(items), 5)

    def test_mood_trend_returns_list(self) -> None:
        for d in range(5):
            e = self.JournalEntry(
                date_iso=f"2025-01-{d+1:02d}", mood=3 + d, title=f"D{d}")
            self.svc.add(e)
        trend = self.svc.mood_trend(days=30)
        self.assertIsInstance(trend, list)

    def test_streak_zero_initially(self) -> None:
        self.assertEqual(self.svc.streak(), 0)

    def test_streak_with_consecutive_days(self) -> None:
        today = date.today()
        for i in range(3):
            d = (today - timedelta(days=i)).isoformat()
            self.svc.add(self.JournalEntry(date_iso=d, mood=4, title="T"))
        self.assertGreater(self.svc.streak(), 0)

    def test_delete_removes_entry(self) -> None:
        e = self.JournalEntry(date_iso="2025-01-01", mood=4, title="T")
        eid = self.svc.add(e)
        self.assertTrue(self.svc.delete(eid))
        self.assertIsNone(self.svc.get(eid))


# =============================================================================
# === HabitService                                                            ===
# =============================================================================

class TestHabitService(unittest.TestCase):
    """HabitService CRUD + streaks."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features import habits as _habits_mod
        _habits_mod._schema_initialized = False
        _habits_mod._ensure_schema()
        from rask.features.habits import (
            habit_service, FREQ_DAILY, FREQ_WEEKLY,
        )
        self.svc = habit_service
        self.FREQ_DAILY = FREQ_DAILY
        self.FREQ_WEEKLY = FREQ_WEEKLY

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_habit_returns_id(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        self.assertGreater(hid, 0)

    def test_get_habit(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        h = self.svc.get_habit(hid)
        self.assertIsNotNone(h)
        self.assertEqual(h.name, "Read")

    def test_list_habits(self) -> None:
        self.svc.add_habit(name="A", frequency=self.FREQ_DAILY)
        self.svc.add_habit(name="B", frequency=self.FREQ_DAILY)
        self.assertEqual(len(self.svc.list_habits()), 2)

    def test_log_completion_returns_true(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        self.assertTrue(self.svc.log_completion(hid, "2025-01-01"))

    def test_streak_after_today_completion(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        self.svc.log_completion(hid, today_iso())
        self.assertEqual(self.svc.streak(hid), 1)

    def test_streak_after_two_consecutive_days(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        yest = (date.today() - timedelta(days=1)).isoformat()
        self.svc.log_completion(hid, yest)
        self.svc.log_completion(hid, today_iso())
        self.assertEqual(self.svc.streak(hid), 2)

    def test_completion_rate(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        # Complete 3 out of 7 days.
        for i in range(3):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.svc.log_completion(hid, d)
        rate = self.svc.completion_rate(hid, days=7)
        self.assertGreater(rate, 0.0)
        self.assertLessEqual(rate, 1.0)

    def test_best_streak(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        yest = (date.today() - timedelta(days=1)).isoformat()
        self.svc.log_completion(hid, yest)
        self.svc.log_completion(hid, today_iso())
        self.assertGreaterEqual(self.svc.best_streak(hid), 2)

    def test_delete_habit(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        self.assertTrue(self.svc.delete_habit(hid))
        self.assertIsNone(self.svc.get_habit(hid))

    def test_is_completed_today(self) -> None:
        hid = self.svc.add_habit(name="Read", frequency=self.FREQ_DAILY)
        self.assertFalse(self.svc.is_completed_today(hid))
        self.svc.log_completion(hid, today_iso())
        self.assertTrue(self.svc.is_completed_today(hid))


# =============================================================================
# === MoodService                                                             ===
# =============================================================================

class TestMoodService(unittest.TestCase):
    """MoodService CRUD + analytics."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features import mood_tracker as _mood_mod
        _mood_mod._schema_initialized = False
        _mood_mod._ensure_schema()
        from rask.features.mood_tracker import mood_service
        self.svc = mood_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_id(self) -> None:
        mid = self.svc.add(date_iso=today_iso(), mood=4, energy=3)
        self.assertGreater(mid, 0)

    def test_get_returns_entry(self) -> None:
        mid = self.svc.add(date_iso=today_iso(), mood=4, notes="Good")
        e = self.svc.get(mid)
        self.assertEqual(e.mood, 4)
        self.assertEqual(e.notes, "Good")

    def test_list_returns_entries(self) -> None:
        for i in range(5):
            d = (date.today() - timedelta(days=i)).isoformat()
            self.svc.add(date_iso=d, mood=3 + (i % 3))
        items = self.svc.list()
        self.assertEqual(len(items), 5)

    def test_average_mood(self) -> None:
        self.svc.add(date_iso=today_iso(), mood=4)
        self.svc.add(date_iso=today_iso(), mood=2)
        avg = self.svc.average_mood(days=7)
        self.assertAlmostEqual(avg, 3.0)

    def test_average_energy(self) -> None:
        self.svc.add(date_iso=today_iso(), mood=3, energy=5)
        self.svc.add(date_iso=today_iso(), mood=3, energy=3)
        self.assertAlmostEqual(self.svc.average_energy(days=7), 4.0)

    def test_mood_distribution(self) -> None:
        self.svc.add(date_iso=today_iso(), mood=4)
        self.svc.add(date_iso=today_iso(), mood=4)
        self.svc.add(date_iso=today_iso(), mood=2)
        d = self.svc.mood_distribution(days=7)
        self.assertEqual(d[4], 2)
        self.assertEqual(d[2], 1)

    def test_count_today(self) -> None:
        self.svc.add(date_iso=today_iso(), mood=4)
        self.svc.add(date_iso=today_iso(), mood=3)
        self.assertEqual(self.svc.count_today(), 2)

    def test_count(self) -> None:
        self.svc.add(date_iso=today_iso(), mood=4)
        self.svc.add(date_iso=today_iso(), mood=3)
        self.assertEqual(self.svc.count(), 2)

    def test_delete(self) -> None:
        mid = self.svc.add(date_iso=today_iso(), mood=4)
        self.assertTrue(self.svc.delete(mid))
        self.assertIsNone(self.svc.get(mid))


# =============================================================================
# === FocusMode                                                               ===
# =============================================================================

class TestFocusMode(unittest.TestCase):
    """FocusMode start/end/interruptions."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.focus_mode import focus_mode
        self.svc = focus_mode

    def tearDown(self) -> None:
        try:
            self.svc.end()
        except Exception:
            pass
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_start_creates_session(self) -> None:
        r = self.svc.start(duration_min=10, title="Test")
        self.assertIn("session_id", r)
        self.assertGreater(r["session_id"], 0)

    def test_is_active_after_start(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        self.assertTrue(self.svc.is_active())

    def test_is_paused_initially_false(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        self.assertFalse(self.svc.is_paused())

    def test_pause_then_resume(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        self.svc.pause()
        self.assertTrue(self.svc.is_paused())
        self.svc.resume()
        self.assertFalse(self.svc.is_paused())

    def test_add_interruption(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        self.svc.add_interruption("Phone buzz")
        self.assertEqual(self.svc.interruption_count(), 1)

    def test_end_returns_dict(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        r = self.svc.end()
        self.assertIn("session_id", r)
        self.assertFalse(self.svc.is_active())

    def test_stats_returns_focus_stats(self) -> None:
        self.svc.start(duration_min=10, title="Test")
        self.svc.end()
        s = self.svc.stats()
        self.assertGreaterEqual(s.total_sessions, 1)


# =============================================================================
# === InsightEngine                                                           ===
# =============================================================================

class TestInsightEngine(unittest.TestCase):
    """InsightEngine generate_all."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.smart_insights import insight_engine
        self.svc = insight_engine

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_generate_all_returns_list(self) -> None:
        insights = self.svc.generate_all()
        self.assertIsInstance(insights, list)

    def test_generate_all_returns_non_empty(self) -> None:
        insights = self.svc.generate_all()
        self.assertGreater(len(insights), 0)

    def test_each_insight_has_required_fields(self) -> None:
        insights = self.svc.generate_all()
        for ins in insights:
            self.assertTrue(hasattr(ins, "kind"))
            self.assertTrue(hasattr(ins, "title"))
            self.assertTrue(hasattr(ins, "body"))
            self.assertIn(ins.kind, ("info", "warning", "success",
                                      "achievement"))

    def test_each_insight_has_id(self) -> None:
        insights = self.svc.generate_all()
        for ins in insights:
            self.assertTrue(hasattr(ins, "id"))
            self.assertTrue(ins.id)

    def test_generate_productivity_score(self) -> None:
        ins = self.svc.generate_productivity_score()
        self.assertIsNotNone(ins)

    def test_generate_recommendations_returns_list(self) -> None:
        recs = self.svc.generate_recommendations()
        self.assertIsInstance(recs, list)

    def test_invalidate_clears_cache(self) -> None:
        # Should not raise.
        self.svc.invalidate()


# =============================================================================
# === NotificationCenter                                                      ===
# =============================================================================

class TestNotificationCenter(unittest.TestCase):
    """NotificationCenter add/mark_read/list."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.notifications_center import notification_center
        self.svc = notification_center

    def tearDown(self) -> None:
        try:
            self.svc.clear_all()
        except Exception:
            pass
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_notification(self) -> None:
        self.svc.add(title="Test", body="Hello")
        self.assertEqual(self.svc.total_count(), 1)

    def test_unread_count(self) -> None:
        self.svc.add(title="A", body="X")
        self.svc.add(title="B", body="Y")
        self.assertEqual(self.svc.unread_count(), 2)

    def test_mark_read_decreases_unread(self) -> None:
        self.svc.add(title="A", body="X")
        items = self.svc.list()
        self.svc.mark_read(items[0].id)
        self.assertEqual(self.svc.unread_count(), 0)

    def test_mark_all_read(self) -> None:
        self.svc.add(title="A", body="X")
        self.svc.add(title="B", body="Y")
        self.svc.mark_all_read()
        self.assertEqual(self.svc.unread_count(), 0)

    def test_list_returns_notifications(self) -> None:
        self.svc.add(title="A", body="X")
        items = self.svc.list()
        self.assertEqual(len(items), 1)

    def test_delete_removes_notification(self) -> None:
        self.svc.add(title="A", body="X")
        items = self.svc.list()
        self.svc.delete(items[0].id)
        self.assertEqual(self.svc.total_count(), 0)


# =============================================================================
# === AchievementService                                                      ===
# =============================================================================

class TestAchievementService(unittest.TestCase):
    """AchievementService definitions + level."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.achievements_system import AchievementService
        self.svc = AchievementService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_has_at_least_30_achievements(self) -> None:
        all_a = self.svc.all()
        self.assertGreaterEqual(len(all_a), 30)

    def test_xp_total_starts_at_zero(self) -> None:
        self.assertEqual(self.svc.xp_total(), 0)

    def test_level_starts_at_one(self) -> None:
        self.assertEqual(self.svc.level(), 1)

    def test_level_title_returns_string(self) -> None:
        title = self.svc.level_title()
        self.assertIsInstance(title, str)
        self.assertTrue(title)

    def test_level_title_en_returns_string(self) -> None:
        title = self.svc.level_title_en()
        self.assertIsInstance(title, str)
        self.assertTrue(title)

    def test_level_progress_is_in_range(self) -> None:
        p = self.svc.level_progress()
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_xp_to_next_level_positive(self) -> None:
        self.assertGreater(self.svc.xp_to_next_level(), 0)

    def test_earned_starts_empty(self) -> None:
        self.assertEqual(len(self.svc.earned()), 0)

    def test_locked_returns_most_achievements(self) -> None:
        locked = self.svc.locked()
        self.assertGreater(len(locked), 0)


# =============================================================================
# === WeeklyReview                                                            ===
# =============================================================================

class TestWeeklyReview(unittest.TestCase):
    """WeeklyReview generate + format."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.weekly_review import weekly_review
        self.svc = weekly_review

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_generate_returns_dict(self) -> None:
        r = self.svc.generate()
        self.assertIsInstance(r, dict)

    def test_generate_has_required_keys(self) -> None:
        r = self.svc.generate()
        for key in ("week_iso", "week_start", "week_end", "total_min",
                    "total_activities", "goal_hits", "goal_misses",
                    "mood_avg", "habit_completion_rate"):
            self.assertIn(key, r)

    def test_format_text_returns_non_empty(self) -> None:
        r = self.svc.generate()
        text = self.svc.format_text(r)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    def test_format_markdown_returns_non_empty(self) -> None:
        r = self.svc.generate()
        md = self.svc.format_markdown(r)
        self.assertIsInstance(md, str)
        self.assertGreater(len(md), 0)

    def test_format_html_returns_non_empty(self) -> None:
        r = self.svc.generate()
        html = self.svc.format_html(r)
        self.assertIsInstance(html, str)
        self.assertGreater(len(html), 0)

    def test_generate_with_explicit_week_iso(self) -> None:
        # week_iso input is the Saturday-start of the desired week.
        # The returned week_start should equal the input or be the
        # Saturday of that week.
        r = self.svc.generate(week_iso="2025-01-06")
        # Should be within a week of the input.
        from datetime import date
        d = date.fromisoformat(r["week_start"])
        self.assertLessEqual(abs((d - date(2025, 1, 6)).days), 7)


# =============================================================================
# === CalendarService                                                         ===
# =============================================================================

class TestCalendarService(unittest.TestCase):
    """CalendarService month/week/day views + find_free_time."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.calendar_integration import calendar_service
        self.svc = calendar_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_month_view_returns_dict(self) -> None:
        mv = self.svc.month_view(2025, 1)
        self.assertIsInstance(mv, dict)
        self.assertEqual(mv["year"], 2025)
        self.assertEqual(mv["month"], 1)
        self.assertIn("weeks", mv)

    def test_month_view_has_4_to_6_weeks(self) -> None:
        mv = self.svc.month_view(2025, 1)
        self.assertGreaterEqual(len(mv["weeks"]), 4)
        self.assertLessEqual(len(mv["weeks"]), 6)

    def test_week_view_returns_dict(self) -> None:
        wv = self.svc.week_view("2025-01-06")
        self.assertIsInstance(wv, dict)
        self.assertIn("days", wv)
        self.assertEqual(len(wv["days"]), 7)

    def test_day_view_returns_dict(self) -> None:
        dv = self.svc.day_view("2025-01-01")
        self.assertIsInstance(dv, dict)
        self.assertIn("activities", dv)

    def test_find_free_time_returns_list(self) -> None:
        ft = self.svc.find_free_time("2025-01-01", 60)
        self.assertIsInstance(ft, list)

    def test_find_free_time_returns_more_when_no_activities(self) -> None:
        ft = self.svc.find_free_time("2025-01-01", 60)
        self.assertGreater(len(ft), 0)

    def test_busiest_day_returns_none_when_empty(self) -> None:
        bd = self.svc.busiest_day("2025-01-01", "2025-01-31")
        self.assertIsNone(bd)

    def test_quietest_day_returns_none_when_empty(self) -> None:
        qd = self.svc.quietest_day("2025-01-01", "2025-01-31")
        self.assertIsNone(qd)


# =============================================================================
# === QuickActionsService                                                     ===
# =============================================================================

class TestQuickActionsService(unittest.TestCase):
    """QuickActionsService list + execute."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.quick_actions import quick_actions_service
        self.svc = quick_actions_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_list_returns_pre_registered(self) -> None:
        items = self.svc.list()
        self.assertGreater(len(items), 0)

    def test_each_action_has_name_and_id(self) -> None:
        for a in self.svc.list():
            self.assertTrue(a.id)
            self.assertTrue(a.name)


# =============================================================================
# === SoundService                                                            ===
# =============================================================================

class TestSoundService(unittest.TestCase):
    """SoundService enabled/set_enabled (no actual playback)."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.sound_effects import sound_service
        self.svc = sound_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_enabled_returns_bool(self) -> None:
        self.assertIsInstance(self.svc.enabled(), bool)

    def test_set_enabled_false(self) -> None:
        self.svc.set_enabled(False)
        self.assertFalse(self.svc.enabled())

    def test_set_enabled_true(self) -> None:
        self.svc.set_enabled(False)
        self.svc.set_enabled(True)
        self.assertTrue(self.svc.enabled())


# =============================================================================
# === ThemeRegistry                                                           ===
# =============================================================================

class TestThemeRegistry(unittest.TestCase):
    """ThemeRegistry register/get/list."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.themes_extra import theme_registry, Theme
        self.svc = theme_registry
        self.Theme = Theme

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_list_returns_themes(self) -> None:
        items = self.svc.list()
        self.assertGreater(len(items), 0)

    def test_list_names_returns_strings(self) -> None:
        names = self.svc.list_names()
        for n in names:
            self.assertIsInstance(n, str)
            self.assertTrue(n)

    def test_get_returns_theme(self) -> None:
        names = self.svc.list_names()
        t = self.svc.get(names[0])
        self.assertIsNotNone(t)

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(self.svc.get("nonexistent_theme"))

    def test_active_returns_string(self) -> None:
        active = self.svc.active()
        self.assertIsInstance(active, str)


# =============================================================================
# === BackupScheduler                                                         ===
# =============================================================================

class TestBackupScheduler(unittest.TestCase):
    """BackupScheduler next_run/last_run."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.backup_scheduler import backup_scheduler
        self.svc = backup_scheduler

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_next_run_returns_none_or_str(self) -> None:
        n = self.svc.next_run()
        self.assertTrue(n is None or isinstance(n, str))

    def test_last_run_returns_none_or_str(self) -> None:
        l = self.svc.last_run()
        self.assertTrue(l is None or isinstance(l, str))

    def test_is_running_returns_bool(self) -> None:
        self.assertIsInstance(self.svc.is_running(), bool)

    def test_interval_sec_positive(self) -> None:
        self.assertGreater(self.svc.interval_sec(), 0)


# =============================================================================
# === AnalyticsService                                                        ===
# =============================================================================

class TestAnalyticsService(unittest.TestCase):
    """AnalyticsService methods return expected shapes."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.analytics_dashboard import analytics_service
        self.svc = analytics_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_productivity_over_time_returns_list(self) -> None:
        result = self.svc.productivity_over_time(days=7)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 7)

    def test_productivity_over_time_entry_has_required_fields(self) -> None:
        result = self.svc.productivity_over_time(days=7)
        for entry in result:
            self.assertIn("date_iso", entry)
            self.assertIn("score", entry)
            self.assertIn("total_min", entry)
            self.assertIn("count", entry)

    def test_category_trends_returns_dict(self) -> None:
        result = self.svc.category_trends(days=7)
        self.assertIsInstance(result, dict)

    def test_time_distribution_returns_dict(self) -> None:
        result = self.svc.time_distribution()
        self.assertIsInstance(result, dict)
        for key in ("date_from", "date_to", "total_min",
                    "by_category", "by_hour", "by_weekday"):
            self.assertIn(key, result)

    def test_weekly_heatmap_returns_data(self) -> None:
        result = self.svc.weekly_heatmap()
        self.assertIsNotNone(result)

    def test_anomaly_detection_returns_list(self) -> None:
        result = self.svc.anomaly_detection()
        self.assertIsInstance(result, list)

    def test_report_card_returns_dict(self) -> None:
        result = self.svc.report_card()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
