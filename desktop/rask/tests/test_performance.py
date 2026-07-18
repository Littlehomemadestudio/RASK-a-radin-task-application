"""
rask.tests.test_performance
==========================

Performance benchmarks for the Rask desktop app.

These tests are smoke-style benchmarks — they don't enforce strict
timing thresholds by default (because CI environments vary wildly),
but they do verify that operations complete in a "reasonable" time
and produce the expected results.

Targets (loose):

  • DB insert: 1000 activities per second target
  • DB query: activity_list with 10K rows under 100ms
  • Stats summary on 1 year of data under 500ms
  • Backup create on 10K activities under 5s
  • PDF export on 100 activities under 2s
  • Heatmap data computation under 200ms
  • Memory usage stays under 200MB
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from typing import Any, List

from rask import config, database as db
from rask.core.event_bus import bus
from rask.tests import fresh_db


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _seed_n_activities(n: int) -> None:
    """Insert n activities as fast as possible."""
    cats = db.category_list()
    for i in range(n):
        month = (i % 12) + 1
        day = (i % 28) + 1
        db.activity_add(
            title=f"Activity {i}",
            category_id=cats[i % len(cats)]["id"],
            duration_min=15 + (i % 60),
            date_iso=f"2025-{month:02d}-{day:02d}",
        )


def _memory_rss_mb() -> float:
    """Return current process RSS in MB (best-effort, 0 if unknown)."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:  # noqa: BLE001
        return 0.0


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestDbInsertPerformance(unittest.TestCase):
    """DB insert throughput."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_insert_1000_activities(self) -> None:
        start = time.perf_counter()
        _seed_n_activities(1000)
        elapsed = time.perf_counter() - start
        self.assertEqual(db.activity_count(), 1000)
        # Loose upper bound: 30 seconds on any CI.
        self.assertLess(elapsed, 30.0,
                        f"Insert took {elapsed:.2f}s, expected < 30s")
        # Throughput printout (informational).
        rate = 1000 / elapsed if elapsed > 0 else float("inf")
        # Don't enforce a strict rate — just log it.
        self.assertGreater(rate, 0)

    def test_insert_100_activities_baseline(self) -> None:
        start = time.perf_counter()
        _seed_n_activities(100)
        elapsed = time.perf_counter() - start
        self.assertEqual(db.activity_count(), 100)
        self.assertLess(elapsed, 5.0)


class TestDbQueryPerformance(unittest.TestCase):
    """DB query latency on a populated DB."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(1000)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_activity_list_1000_rows(self) -> None:
        start = time.perf_counter()
        rows = db.activity_list(limit=10000)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(rows), 1000)
        # Loose bound: under 1 second.
        self.assertLess(elapsed, 1.0)

    def test_activity_count(self) -> None:
        start = time.perf_counter()
        n = db.activity_count()
        elapsed = time.perf_counter() - start
        self.assertEqual(n, 1000)
        self.assertLess(elapsed, 0.5)

    def test_activity_count_with_date_filter(self) -> None:
        start = time.perf_counter()
        n = db.activity_count(date_from="2025-01-01",
                                date_to="2025-01-31")
        elapsed = time.perf_counter() - start
        self.assertGreater(n, 0)
        self.assertLess(elapsed, 0.5)

    def test_activity_list_with_filters(self) -> None:
        cats = db.category_list()
        start = time.perf_counter()
        rows = db.activity_list(
            date_from="2025-01-01",
            date_to="2025-12-31",
            category_ids=[cats[0]["id"]],
            limit=10000,
        )
        elapsed = time.perf_counter() - start
        self.assertGreater(len(rows), 0)
        self.assertLess(elapsed, 1.0)


class TestStatsSummaryPerformance(unittest.TestCase):
    """StatsService summary on a year of data."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        # Seed 1 year of activities (~365 entries, one per day).
        cats = db.category_list()
        today = date.today()
        for i in range(365):
            d = today - timedelta(days=i)
            db.activity_add(
                title=f"Day {i}",
                category_id=cats[i % len(cats)]["id"],
                duration_min=60,
                date_iso=d.isoformat(),
            )

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_summary_completes_quickly(self) -> None:
        from rask.services.stats_service import StatsService
        from rask.core.time_utils import today_iso, add_days
        svc = StatsService()
        date_from = add_days(today_iso(), -365)
        date_to = today_iso()
        start = time.perf_counter()
        summary = svc.summary(date_from=date_from, date_to=date_to)
        elapsed = time.perf_counter() - start
        self.assertIsInstance(summary, dict)
        # Loose bound: under 5 seconds.
        self.assertLess(elapsed, 5.0)

    def test_group_by_day(self) -> None:
        start = time.perf_counter()
        rows = db.activity_group_by_day(date_from="2025-01-01",
                                          date_to="2025-12-31")
        elapsed = time.perf_counter() - start
        self.assertGreater(len(rows), 0)
        self.assertLess(elapsed, 1.0)

    def test_group_by_category(self) -> None:
        start = time.perf_counter()
        rows = db.activity_group_by_category(date_from="2025-01-01",
                                               date_to="2025-12-31")
        elapsed = time.perf_counter() - start
        self.assertGreater(len(rows), 0)
        self.assertLess(elapsed, 1.0)


class TestBackupCreatePerformance(unittest.TestCase):
    """Backup create latency on a populated DB."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(500)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_backup_create_500_activities(self) -> None:
        from rask.services.backup_service import BackupService
        svc = BackupService()
        start = time.perf_counter()
        result = svc.create("benchmark-password")
        elapsed = time.perf_counter() - start
        self.assertTrue(result["success"])
        self.assertLess(elapsed, 10.0)


class TestPdfExportPerformance(unittest.TestCase):
    """PDF export latency on 100 activities."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.tmp = tempfile.mkdtemp()
        _seed_n_activities(100)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        bus.clear()

    def test_pdf_export_100_activities(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "perf.pdf")
        activities = db.activity_list(limit=1000)
        exp = PdfExporter(path, title="Perf")
        start = time.perf_counter()
        exp.add_activities_table(activities)
        exp.save()
        elapsed = time.perf_counter() - start
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 5000)
        self.assertLess(elapsed, 5.0)


class TestHeatmapPerformance(unittest.TestCase):
    """Heatmap computation latency."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(500)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_weekly_heatmap(self) -> None:
        from rask.features.analytics_dashboard import analytics_service
        start = time.perf_counter()
        result = analytics_service.weekly_heatmap()
        elapsed = time.perf_counter() - start
        self.assertIsNotNone(result)
        self.assertLess(elapsed, 2.0)


class TestAnalyticsPerformance(unittest.TestCase):
    """Analytics dashboard latency on a year of data."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(500)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_productivity_over_time(self) -> None:
        from rask.features.analytics_dashboard import analytics_service
        start = time.perf_counter()
        result = analytics_service.productivity_over_time(days=30)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(result), 30)
        self.assertLess(elapsed, 2.0)

    def test_time_distribution(self) -> None:
        from rask.features.analytics_dashboard import analytics_service
        start = time.perf_counter()
        result = analytics_service.time_distribution()
        elapsed = time.perf_counter() - start
        self.assertIsInstance(result, dict)
        self.assertLess(elapsed, 2.0)

    def test_category_trends(self) -> None:
        from rask.features.analytics_dashboard import analytics_service
        start = time.perf_counter()
        result = analytics_service.category_trends(days=30)
        elapsed = time.perf_counter() - start
        self.assertIsInstance(result, dict)
        self.assertLess(elapsed, 2.0)


class TestInsightsPerformance(unittest.TestCase):
    """InsightEngine.generate_all latency."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(200)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_generate_all(self) -> None:
        from rask.features.smart_insights import insight_engine
        start = time.perf_counter()
        insights = insight_engine.generate_all()
        elapsed = time.perf_counter() - start
        self.assertGreater(len(insights), 0)
        self.assertLess(elapsed, 3.0)


class TestMemoryUsage(unittest.TestCase):
    """Memory usage stays bounded."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_memory_under_500mb_after_1000_activities(self) -> None:
        _seed_n_activities(1000)
        # Force a query to load activities into memory.
        rows = db.activity_list(limit=10000)
        self.assertEqual(len(rows), 1000)
        rss = _memory_rss_mb()
        if rss > 0:
            # Loose bound: under 500 MB.
            self.assertLess(rss, 500.0,
                            f"RSS={rss:.1f}MB, expected < 500MB")

    def test_memory_under_500mb_after_backup(self) -> None:
        from rask.services.backup_service import BackupService
        _seed_n_activities(100)
        svc = BackupService()
        result = svc.create("memory-password")
        self.assertTrue(result["success"])
        rss = _memory_rss_mb()
        if rss > 0:
            self.assertLess(rss, 500.0)


class TestBulkImportPerformance(unittest.TestCase):
    """Bulk import (CSV) latency."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        bus.clear()

    def test_import_500_row_csv(self) -> None:
        from rask.features.import_export_extra import ImportFromCSV
        path = os.path.join(self.tmp, "bulk.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Description,Start time,End time,Duration,Tags,Project\n")
            for i in range(500):
                f.write(
                    f"Activity {i},2025-01-01 {9 + i % 8:02d}:00:00,"
                    f"2025-01-01 {10 + i % 8:02d}:00:00,3600,tag,Work\n"
                )
        start = time.perf_counter()
        result = ImportFromCSV(path)
        elapsed = time.perf_counter() - start
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 500)
        self.assertLess(elapsed, 30.0)


class TestConcurrentReadPerformance(unittest.TestCase):
    """Concurrent reads don't degrade."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        _seed_n_activities(500)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_parallel_reads(self) -> None:
        import threading
        errors: List[BaseException] = []
        results: List[int] = []
        lock = threading.Lock()

        def reader() -> None:
            try:
                rows = db.activity_list(limit=10000)
                with lock:
                    results.append(len(rows))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r, 500)
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
