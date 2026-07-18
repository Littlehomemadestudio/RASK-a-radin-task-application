"""
examples/benchmark.py
=====================

Performance benchmark suite for Rask.

Runs a battery of performance tests against the local database and
services, then prints a formatted report.  Compares against baseline
numbers (if a baseline JSON file is present) and exits with code 1 if
any regression is detected.

Usage:
    python examples/benchmark.py
    python examples/benchmark.py --baseline /path/to/baseline.json
    python examples/benchmark.py --save-baseline /path/to/baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))


# =============================================================================
# === Benchmark framework                                                      ===
# =============================================================================

class Benchmark:
    """A single benchmark test."""

    def __init__(self, name: str, func: Callable[[], None],
                 target_ms: float = 0.0, iterations: int = 1):
        self.name = name
        self.func = func
        self.target_ms = target_ms
        self.iterations = iterations
        self.times_ms: list[float] = []
        self.error: str | None = None

    def run(self) -> None:
        for _ in range(self.iterations):
            try:
                start = time.perf_counter()
                self.func()
                elapsed_ms = (time.perf_counter() - start) * 1000
                self.times_ms.append(elapsed_ms)
            except Exception as e:
                self.error = str(e)
                return

    def avg_ms(self) -> float:
        return statistics.mean(self.times_ms) if self.times_ms else 0.0

    def min_ms(self) -> float:
        return min(self.times_ms) if self.times_ms else 0.0

    def max_ms(self) -> float:
        return max(self.times_ms) if self.times_ms else 0.0

    def passed(self) -> bool:
        if self.error:
            return False
        if self.target_ms <= 0:
            return True
        return self.avg_ms() <= self.target_ms

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target_ms": self.target_ms,
            "avg_ms": round(self.avg_ms(), 2),
            "min_ms": round(self.min_ms(), 2),
            "max_ms": round(self.max_ms(), 2),
            "iterations": self.iterations,
            "error": self.error,
            "passed": self.passed(),
        }


# =============================================================================
# === Benchmark suite                                                          ===
# =============================================================================

def _seed_database(n_activities: int = 1000) -> None:
    """Seed the database with N activities for benchmarking."""
    from rask import database
    now = datetime.now(timezone.utc)
    cats = database.category_list()
    if not cats:
        return
    titles = ["Reading", "Coding", "Writing", "Exercise", "Meditation",
              "Meeting", "Research", "Planning", "Review", "Learning"]
    for i in range(n_activities):
        day_offset = i // 10  # 10 activities per day
        d = now - timedelta(days=day_offset)
        date_iso = d.strftime("%Y-%m-%d")
        cat = cats[i % len(cats)]
        duration = 15 + (i % 90)  # 15-104 minutes
        hour = 8 + (i % 12)  # 8 AM to 8 PM
        start_ts = f"{date_iso}T{hour:02d}:{(i % 60):02d}:00+00:00"
        end_ts = f"{date_iso}T{hour + (duration // 60):02d}:{(i % 60 + duration % 60) % 60:02d}:00+00:00"
        database.activity_add(
            title=titles[i % len(titles)],
            category_id=cat["id"],
            duration_min=duration,
            date_iso=date_iso,
            start_ts=start_ts,
            end_ts=end_ts,
            kind="manual" if i % 5 else "stopwatch",
            tags=[f"tag-{i % 5}"],
        )


def build_suite() -> list[Benchmark]:
    """Build the complete benchmark suite."""
    from rask import database
    from rask.services import stats_service, backup_service, export_service

    def bench_db_insert_100():
        """Insert 100 activities in one transaction."""
        titles = ["Bench activity"]
        for i in range(100):
            database.activity_add(
                title=f"Bench-{i}",
                category_id=1,
                duration_min=30,
                date_iso="2025-01-01",
            )

    def bench_db_list_10k():
        """List activities from a 10K-row table."""
        # Filter to ensure index usage
        database.activity_list(date_from="2025-01-01", date_to="2025-12-31",
                                limit=10000)

    def bench_db_count():
        """Count activities (uses index)."""
        database.activity_count()

    def bench_db_sum_duration():
        """Sum total duration in date range."""
        database.activity_sum_duration(date_from="2025-01-01",
                                        date_to="2025-12-31")

    def bench_db_group_by_day():
        """Group by day."""
        database.activity_group_by_day(date_from="2025-01-01",
                                        date_to="2025-12-31")

    def bench_db_group_by_category():
        """Group by category."""
        database.activity_group_by_category(date_from="2025-01-01",
                                              date_to="2025-12-31")

    def bench_stats_summary():
        """Stats summary over 1 year."""
        stats_service.summary("2025-01-01", "2025-12-31")

    def bench_stats_by_day():
        """Stats by_day over 1 year."""
        stats_service.by_day("2025-01-01", "2025-12-31")

    def bench_stats_by_category():
        """Stats by_category over 1 year."""
        stats_service.by_category("2025-01-01", "2025-12-31")

    def bench_stats_heatmap():
        """Heatmap data for current year."""
        stats_service.heatmap_data(year=2025)

    def bench_backup_create():
        """Create encrypted backup."""
        with tempfile.NamedTemporaryFile(suffix=".raskbk", delete=False) as f:
            path = f.name
        try:
            backup_service.create("benchmark-password-123", path=path)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def bench_export_csv():
        """Export CSV."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            from rask.export import CsvExporter
            activities = database.activity_list(limit=10000)
            exp = CsvExporter(path, lang="fa")
            exp.export_activities(activities)
            exp.save()
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def bench_export_json():
        """Export JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            from rask.export import JsonExporter
            exp = JsonExporter(path)
            exp.export_all()
            exp.save()
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def bench_jalali_convert_1000():
        """Convert 1000 Gregorian dates to Jalali."""
        from rask.core import jalali
        for d in range(1, 1001):
            jalali.gregorian_to_jalali(2025, 1, 1)

    def bench_pin_hash():
        """Hash a PIN (PBKDF2 200k iterations)."""
        from rask.core import pin
        pin.hash_pin("1234")

    def bench_pin_verify():
        """Verify a PIN (PBKDF2 200k iterations)."""
        from rask.core import pin
        stored = pin.hash_pin("1234")
        pin.verify_pin("1234", stored)

    return [
        # DB operations
        Benchmark("db_insert_100", bench_db_insert_100, target_ms=500, iterations=3),
        Benchmark("db_list_10k", bench_db_list_10k, target_ms=100, iterations=5),
        Benchmark("db_count", bench_db_count, target_ms=20, iterations=10),
        Benchmark("db_sum_duration", bench_db_sum_duration, target_ms=50, iterations=10),
        Benchmark("db_group_by_day", bench_db_group_by_day, target_ms=100, iterations=5),
        Benchmark("db_group_by_category", bench_db_group_by_category, target_ms=50, iterations=5),
        # Stats
        Benchmark("stats_summary_year", bench_stats_summary, target_ms=500, iterations=3),
        Benchmark("stats_by_day_year", bench_stats_by_day, target_ms=300, iterations=3),
        Benchmark("stats_by_category_year", bench_stats_by_category, target_ms=200, iterations=3),
        Benchmark("stats_heatmap_year", bench_stats_heatmap, target_ms=300, iterations=3),
        # Crypto
        Benchmark("backup_create", bench_backup_create, target_ms=5000, iterations=1),
        Benchmark("pin_hash", bench_pin_hash, target_ms=2000, iterations=1),
        Benchmark("pin_verify", bench_pin_verify, target_ms=2000, iterations=1),
        # Exports
        Benchmark("export_csv", bench_export_csv, target_ms=2000, iterations=1),
        Benchmark("export_json", bench_export_json, target_ms=1000, iterations=1),
        # Core
        Benchmark("jalali_convert_1000", bench_jalali_convert_1000, target_ms=50, iterations=3),
    ]


# =============================================================================
# === Report formatting                                                        ===
# =============================================================================

def colorize(text: str, color: str) -> str:
    codes = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    if not sys.stdout.isatty():
        return text
    return f"{codes.get(color, '')}{text}{codes['reset']}"


def format_report(benchmarks: list[Benchmark],
                   baseline: dict | None = None) -> str:
    lines: list[str] = []
    lines.append(colorize("=" * 78, "bold"))
    lines.append(colorize(" Rask Benchmark Report", "bold"))
    lines.append(colorize("=" * 78, "bold"))
    lines.append("")
    lines.append(f"  {'Name':<28} {'Target':>8} {'Avg':>8} {'Min':>8} {'Max':>8}  {'Status':<8}")
    lines.append(f"  {'-' * 28} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8}  {'-' * 8}")
    for b in benchmarks:
        if b.error:
            status = colorize("ERROR", "red")
            avg_str = "—"
            min_str = "—"
            max_str = "—"
        else:
            avg_str = f"{b.avg_ms():.1f}"
            min_str = f"{b.min_ms():.1f}"
            max_str = f"{b.max_ms():.1f}"
            if b.passed():
                status = colorize("PASS", "green")
            else:
                status = colorize("FAIL", "red")
        target_str = f"{b.target_ms:.0f}" if b.target_ms else "—"
        lines.append(f"  {b.name:<28} {target_str:>8} {avg_str:>8} {min_str:>8} {max_str:>8}  {status}")
        if baseline and b.name in baseline:
            base_avg = baseline[b.name].get("avg_ms", 0)
            if base_avg > 0:
                delta_pct = ((b.avg_ms() - base_avg) / base_avg) * 100
                sign = "+" if delta_pct >= 0 else ""
                color = "red" if delta_pct > 10 else ("yellow" if delta_pct > 0 else "green")
                lines.append(f"  {'':<28} {'':>8} {colorize(f'{sign}{delta_pct:.1f}% vs baseline', color):<30}")
        if b.error:
            lines.append(f"    error: {b.error}")
    lines.append("")
    passed = sum(1 for b in benchmarks if b.passed())
    total = len(benchmarks)
    color = "green" if passed == total else ("yellow" if passed > total * 0.7 else "red")
    lines.append(colorize(f"  Result: {passed}/{total} benchmarks passed", color))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rask performance benchmark suite")
    parser.add_argument("--baseline", type=str, default=None,
                        help="Baseline JSON file to compare against")
    parser.add_argument("--save-baseline", type=str, default=None,
                        help="Save current results as baseline to this file")
    parser.add_argument("--seed", type=int, default=1000,
                        help="Number of activities to seed (default: 1000)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    # Setup
    from rask import database
    database.open_db()

    # Seed
    print(f"Seeding database with {args.seed} activities...", file=sys.stderr)
    _seed_database(args.seed)
    print(f"  DB now has {database.activity_count()} activities", file=sys.stderr)

    # Build + run suite
    suite = build_suite()
    print(f"Running {len(suite)} benchmarks...", file=sys.stderr)
    for b in suite:
        print(f"  → {b.name}...", file=sys.stderr, end="")
        b.run()
        if b.error:
            print(f" ERROR", file=sys.stderr)
        else:
            print(f" {b.avg_ms():.1f}ms", file=sys.stderr)

    # Load baseline if provided
    baseline = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline) as f:
            baseline = json.load(f).get("benchmarks", {})

    # Save baseline if requested
    if args.save_baseline:
        results = {b.name: b.to_dict() for b in suite}
        with open(args.save_baseline, "w") as f:
            json.dump({"benchmarks": results, "saved_at": datetime.now().isoformat()}, f, indent=2)
        print(f"Baseline saved to: {args.save_baseline}", file=sys.stderr)

    # Print report
    if args.json:
        results = {b.name: b.to_dict() for b in suite}
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_report(suite, baseline))

    # Exit code
    all_passed = all(b.passed() for b in suite)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
