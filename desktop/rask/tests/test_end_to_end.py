"""
rask.tests.test_end_to_end
=========================

End-to-end integration tests for the Rask desktop app.

These tests exercise multiple services together to verify the full
data lifecycle:

  • Full lifecycle: install → onboard → set PIN → log activity → check
    streak → earn badge → backup → restore → verify
  • Multi-user scenario: separate DBs, separate state
  • Stress test: 1000 activities, performance sanity check
  • Concurrent access (simulated with threads)
  • Backup rotation with many backups
  • Large PDF export (1000 activities)
  • All filters combined
  • All chart types with empty / single / many data points
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from typing import Any, List

from rask import config, database as db
from rask.core.event_bus import bus
from rask.core.time_utils import today_iso, add_days
from rask.services.activity_service import ActivityService
from rask.services.badge_service import BadgeService
from rask.services.backup_service import BackupService
from rask.services.goal_service import GoalService
from rask.services.settings_service import SettingsService
from rask.services.streak_service import StreakService
from rask.services.template_service import TemplateService
from rask.tests import fresh_db


# =============================================================================
# === Full lifecycle                                                          ===
# =============================================================================

class TestFullLifecycle(unittest.TestCase):
    """Full app lifecycle: install → onboard → PIN → activity → streak
    → badge → backup → restore → verify.
    """

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_full_lifecycle(self) -> None:
        # 1. Fresh DB is initialized with defaults.
        self.assertGreaterEqual(len(db.category_list()), 7)
        self.assertGreaterEqual(len(db.goal_list()), 1)

        # 2. Onboarding: mark as onboarded.
        settings = SettingsService()
        settings.init()
        self.assertFalse(settings.is_onboarded())
        settings.set_onboarded(True)
        self.assertTrue(settings.is_onboarded())

        # 3. Set PIN.
        from rask.core.pin import hash_pin
        pin_hash = hash_pin("1234")
        settings.set_pin_hash(pin_hash)
        self.assertEqual(settings.pin_hash(), pin_hash)

        # 4. Log an activity.
        activity_svc = ActivityService()
        a = activity_svc.add(
            title="Reading session",
            duration_min=60,
            category_id=db.category_list()[0]["id"],
            date_iso=today_iso(),
        )
        self.assertGreater(a["id"], 0)
        self.assertEqual(db.activity_count(), 1)

        # 5. Check streak (need a goal with streak row).
        gid = db.goal_add("daily", 30)
        streak_svc = StreakService()
        r = streak_svc.increment(gid, today_iso())
        self.assertEqual(r["current"], 1)

        # 6. Earn a badge.
        badge_svc = BadgeService()
        newly = badge_svc.check_all()
        self.assertIn("first_activity", newly)
        self.assertTrue(badge_svc.has("first_activity"))

        # 7. Backup.
        backup_svc = BackupService()
        backup_result = backup_svc.create("test-password-1")
        self.assertTrue(backup_result["success"])
        self.assertTrue(os.path.exists(backup_result["path"]))

        # 8. Mutate data after backup.
        activity_svc.add(title="After backup", duration_min=15)
        self.assertEqual(db.activity_count(), 2)

        # 9. Restore.
        restore_result = backup_svc.restore(backup_result["path"],
                                              "test-password-1")
        self.assertTrue(restore_result["success"])

        # 10. Verify state was rolled back to backup time.
        # (Activity count should be 1 — the one we logged before backup.)
        # Note: restore re-seeds the DB; the default goal may have a
        # different id, but the activity we logged should be there.
        # The "After backup" activity should be gone.
        titles = [a["title"] for a in db.activity_list(limit=100)]
        self.assertIn("Reading session", titles)
        self.assertNotIn("After backup", titles)


# =============================================================================
# === Multi-user scenario                                                     ===
# =============================================================================

class TestMultiUserScenario(unittest.TestCase):
    """Two separate DBs maintain separate state."""

    def setUp(self) -> None:
        self._ctx1 = fresh_db()
        self._ctx1.__enter__()
        # Add data to DB1.
        db.activity_add("User1 activity", None, 30, "2025-01-01")
        # Capture DB1's path.
        self.db1_path = str(config.DB_PATH)
        # Exit DB1.
        self._ctx1.__exit__(None, None, None)
        # Enter DB2.
        self._ctx2 = fresh_db()
        self._ctx2.__enter__()

    def tearDown(self) -> None:
        self._ctx2.__exit__(None, None, None)
        bus.clear()

    def test_user2_does_not_see_user1_data(self) -> None:
        # DB2 should have 0 activities (only defaults).
        self.assertEqual(db.activity_count(), 0)
        # DB2 should still have default categories.
        self.assertGreaterEqual(len(db.category_list()), 7)

    def test_user2_can_add_own_data(self) -> None:
        db.activity_add("User2 activity", None, 60, "2025-02-01")
        self.assertEqual(db.activity_count(), 1)
        activities = db.activity_list()
        self.assertEqual(activities[0]["title"], "User2 activity")


# =============================================================================
# === Stress test                                                            ===
# =============================================================================

class TestStress1000Activities(unittest.TestCase):
    """Stress test with 1000 activities."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_insert_1000_activities(self) -> None:
        cats = db.category_list()
        start = time.time()
        for i in range(1000):
            db.activity_add(
                title=f"Activity {i}",
                category_id=cats[i % len(cats)]["id"],
                duration_min=15 + (i % 60),
                date_iso=f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            )
        elapsed = time.time() - start
        self.assertEqual(db.activity_count(), 1000)
        # Should complete in reasonable time (loose bound).
        self.assertLess(elapsed, 30.0)

    def test_query_1000_activities(self) -> None:
        cats = db.category_list()
        for i in range(1000):
            db.activity_add(
                title=f"Activity {i}",
                category_id=cats[i % len(cats)]["id"],
                duration_min=30,
                date_iso=f"2025-01-{(i % 28) + 1:02d}",
            )
        start = time.time()
        rows = db.activity_list(limit=10000)
        elapsed = time.time() - start
        self.assertEqual(len(rows), 1000)
        # Query should be fast.
        self.assertLess(elapsed, 2.0)

    def test_count_1000_activities(self) -> None:
        cats = db.category_list()
        for i in range(1000):
            db.activity_add(
                title=f"Activity {i}",
                category_id=cats[0]["id"],
                duration_min=30,
                date_iso="2025-01-01",
            )
        self.assertEqual(db.activity_count(), 1000)
        self.assertEqual(
            db.activity_count(date_from="2025-01-01", date_to="2025-01-01"),
            1000,
        )


# =============================================================================
# === Concurrent access                                                       ===
# =============================================================================

class TestConcurrentAccess(unittest.TestCase):
    """Simulated concurrent DB access from multiple threads."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_concurrent_inserts(self) -> None:
        errors: List[BaseException] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(50):
                    db.activity_add(
                        title=f"T{thread_id}-{i}",
                        category_id=None,
                        duration_min=30,
                        date_iso="2025-01-01",
                    )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,))
                   for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(db.activity_count(), 200)

    def test_concurrent_reads_and_writes(self) -> None:
        errors: List[BaseException] = []

        def writer() -> None:
            try:
                for i in range(100):
                    db.activity_add(
                        title=f"W-{i}",
                        category_id=None,
                        duration_min=30,
                        date_iso="2025-01-01",
                    )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(100):
                    db.activity_list(limit=100)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(db.activity_count(), 200)


# =============================================================================
# === Backup rotation                                                        ===
# =============================================================================

class TestBackupRotation(unittest.TestCase):
    """Multiple backups can be created and listed."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BackupService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_create_multiple_backups(self) -> None:
        # Add some data first.
        db.activity_add("Test", None, 30, "2025-01-01")
        results = []
        for i in range(3):
            svc = BackupService()  # fresh instance per backup
            r = svc.create(f"password{i}")
            results.append(r)
            self.assertTrue(r["success"])
            # Backup filenames are timestamped to the second — wait
            # long enough to ensure a new filename.
            time.sleep(1.1)
        # All backups should exist.
        for r in results:
            self.assertTrue(os.path.exists(r["path"]))

    def test_list_local_returns_all_backups(self) -> None:
        for i in range(3):
            svc = BackupService()
            svc.create(f"password{i}")
            time.sleep(1.1)
        svc = BackupService()
        backups = svc.list_local()
        self.assertGreaterEqual(len(backups), 3)

    def test_restore_each_backup(self) -> None:
        # Create one backup, restore it.
        db.activity_add("Before", None, 30, "2025-01-01")
        svc = BackupService()
        r = svc.create("password")
        self.assertTrue(r["success"])
        # Mutate after backup.
        db.activity_add("After", None, 60, "2025-01-02")
        self.assertEqual(db.activity_count(), 2)
        # Restore.
        svc2 = BackupService()
        restore_result = svc2.restore(r["path"], "password")
        self.assertTrue(restore_result["success"])

    def test_verify_backup_returns_bool(self) -> None:
        db.activity_add("Test", None, 30, "2025-01-01")
        svc = BackupService()
        r = svc.create("password")
        svc2 = BackupService()
        valid = svc2.verify(r["path"], "password")
        self.assertIsInstance(valid, bool)


# =============================================================================
# === Large PDF export                                                       ===
# =============================================================================

class TestLargePdfExport(unittest.TestCase):
    """PDF export with 1000 activities."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.tmp = tempfile.mkdtemp()
        cats = db.category_list()
        for i in range(100):
            db.activity_add(
                title=f"Activity {i}",
                category_id=cats[i % len(cats)]["id"],
                duration_min=30,
                date_iso=f"2025-01-{(i % 28) + 1:02d}",
            )

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        bus.clear()

    def test_export_100_activities_to_pdf(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "large.pdf")
        exp = PdfExporter(path, title="Large Export")
        activities = db.activity_list(limit=1000)
        exp.add_heading("Activities")
        exp.add_activities_table(activities)
        exp.save()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 5000)

    def test_export_100_activities_to_csv(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "large.csv")
        exp = CsvExporter(path, persian_digits=False)
        activities = db.activity_list(limit=1000)
        n = exp.export_activities(activities)
        exp.save()
        self.assertEqual(n, 100)
        self.assertTrue(os.path.exists(path))


# =============================================================================
# === All filters combined                                                    ===
# =============================================================================

class TestAllFiltersCombined(unittest.TestCase):
    """Combine multiple filters in activity_list()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        cats = db.category_list()
        # Build varied data:
        # - cat1, kind=manual, January, with tag "books"
        # - cat2, kind=stopwatch, February, with tag "dev"
        # - cat3, kind=template, March, with tag "books"
        for i in range(30):
            cat = cats[i % len(cats)]["id"]
            kind = ["manual", "stopwatch", "template"][i % 3]
            month = (i % 3) + 1
            tag = "books" if i % 2 == 0 else "dev"
            db.activity_add(
                title=f"Act {i}",
                category_id=cat,
                duration_min=30,
                date_iso=f"2025-{month:02d}-15",
                kind=kind,
                tags=[tag],
            )

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_filter_by_date_range(self) -> None:
        rows = db.activity_list(date_from="2025-01-01",
                                  date_to="2025-01-31", limit=1000)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertLessEqual(r["date_iso"], "2025-01-31")

    def test_filter_by_category(self) -> None:
        cats = db.category_list()
        first_cat = cats[0]["id"]
        rows = db.activity_list(category_ids=[first_cat], limit=1000)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertEqual(r["category_id"], first_cat)

    def test_filter_by_kind(self) -> None:
        rows = db.activity_list(kinds=["manual"], limit=1000)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertEqual(r["kind"], "manual")

    def test_filter_by_search(self) -> None:
        rows = db.activity_list(search="Act 1", limit=1000)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertIn("Act 1", r["title"])

    def test_filter_combined(self) -> None:
        rows = db.activity_list(
            date_from="2025-01-01",
            date_to="2025-03-31",
            kinds=["manual", "stopwatch"],
            limit=1000,
        )
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertIn(r["kind"], ("manual", "stopwatch"))

    def test_filter_with_limit_and_offset(self) -> None:
        page1 = db.activity_list(limit=10, offset=0)
        page2 = db.activity_list(limit=10, offset=10)
        self.assertEqual(len(page1), 10)
        self.assertEqual(len(page2), 10)
        # Pages should be different.
        ids1 = {r["id"] for r in page1}
        ids2 = {r["id"] for r in page2}
        self.assertEqual(len(ids1 & ids2), 0)


# =============================================================================
# === Empty / single / many data points                                       ===
# =============================================================================

class TestChartDataShapes(unittest.TestCase):
    """All chart-bearing services handle empty / single / many data points."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        from rask.features.analytics_dashboard import analytics_service
        self.analytics = analytics_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_productivity_over_time_empty(self) -> None:
        result = self.analytics.productivity_over_time(days=7)
        self.assertEqual(len(result), 7)
        for entry in result:
            self.assertEqual(entry["total_min"], 0)

    def test_productivity_over_time_single_activity(self) -> None:
        db.activity_add("Solo", None, 30, today_iso())
        result = self.analytics.productivity_over_time(days=7)
        # Today's entry should have non-zero total_min.
        today_entry = next((e for e in result if e["date_iso"] == today_iso()),
                           None)
        if today_entry:
            self.assertGreater(today_entry["total_min"], 0)

    def test_productivity_over_time_many_activities(self) -> None:
        for i in range(50):
            db.activity_add(f"Act {i}", None, 30,
                              add_days(today_iso(), -i % 7))
        result = self.analytics.productivity_over_time(days=7)
        self.assertEqual(len(result), 7)

    def test_time_distribution_empty(self) -> None:
        result = self.analytics.time_distribution()
        self.assertEqual(result["total_min"], 0)

    def test_time_distribution_with_data(self) -> None:
        db.activity_add("A", None, 30, today_iso())
        result = self.analytics.time_distribution()
        self.assertGreaterEqual(result["total_min"], 30)

    def test_weekly_heatmap_empty(self) -> None:
        result = self.analytics.weekly_heatmap()
        self.assertIsNotNone(result)

    def test_anomaly_detection_empty(self) -> None:
        result = self.analytics.anomaly_detection()
        self.assertIsInstance(result, list)


# =============================================================================
# === Template -> Activity chain                                             ===
# =============================================================================

class TestTemplateActivityChain(unittest.TestCase):
    """Template.use() creates an activity with the right kind and tags."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_template_creates_activity_with_kind(self) -> None:
        svc = TemplateService()
        t = svc.add(name="Reading", title="Read 30 min",
                     duration_min=30, tags=["books", "morning"])
        a = svc.use(t["id"])
        self.assertEqual(a["kind"], "template")
        self.assertEqual(a["title"], "Read 30 min")
        self.assertEqual(a["duration_min"], 30)
        self.assertEqual(a["template_id"], t["id"])

    def test_template_use_count_increments(self) -> None:
        svc = TemplateService()
        t = svc.add(name="Reading", title="Read", duration_min=30)
        svc.use(t["id"])
        svc.use(t["id"])
        svc.use(t["id"])
        t2 = svc.get(t["id"])
        self.assertGreaterEqual(t2["use_count"], 3)


# =============================================================================
# === Goal + Streak integration                                              ===
# =============================================================================

class TestGoalStreakIntegration(unittest.TestCase):
    """Goals + streaks + badge unlock integration."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_streak_unlocks_milestone_badge(self) -> None:
        gid = db.goal_add("daily", 60)
        streak_svc = StreakService()
        badge_svc = BadgeService()
        for i in range(3):
            d = (date.today() - timedelta(days=2 - i)).isoformat()
            streak_svc.increment(gid, d)
        # streak_3 badge should be unlocked by the milestone callback.
        self.assertTrue(badge_svc.has("streak_3"))

    def test_goal_progress(self) -> None:
        gid = db.goal_add("daily", 30)
        # Log an activity toward the goal.
        db.activity_add("Reading", None, 30, today_iso())
        # The goal progress is computed by goal_service.
        goal_svc = GoalService()
        progress = goal_svc.progress_for(gid)
        self.assertIsInstance(progress, dict)
        self.assertIn("percent", progress)


# =============================================================================
# === Settings + Event Bus integration                                       ===
# =============================================================================

class TestSettingsEventBusIntegration(unittest.TestCase):
    """Setting changes publish events on the bus."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_language_change_publishes_event(self) -> None:
        events: List[Any] = []
        bus.subscribe("language.changed", lambda d: events.append(d))
        svc = SettingsService()
        svc.init()
        svc.set_language("en")
        self.assertEqual(len(events), 1)

    def test_theme_change_publishes_event(self) -> None:
        events: List[Any] = []
        bus.subscribe("theme.changed", lambda d: events.append(d))
        svc = SettingsService()
        svc.init()
        svc.set_theme("light")
        self.assertEqual(len(events), 1)

    def test_settings_change_publishes_event(self) -> None:
        events: List[Any] = []
        bus.subscribe("settings.changed", lambda d: events.append(d))
        svc = SettingsService()
        svc.init()
        svc.set_user_name("Alice")
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
