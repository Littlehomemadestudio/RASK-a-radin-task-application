"""
examples/demo_walkthrough.py
============================

A guided tour of the Rask codebase that exercises every feature
without launching the GUI.

Run from the project root:

    python -m examples.demo_walkthrough

or:

    cd desktop && python examples/demo_walkthrough.py

The script:
  1. Initializes a clean in-memory database
  2. Seeds realistic demo data (1 month of activities)
  3. Walks through each service and prints a narration
  4. Generates sample exports (CSV, JSON, PDF)
  5. Creates + restores an encrypted backup
  6. Runs the analytics engine and prints insights
  7. Generates a weekly review in 3 formats
  8. Tears down the demo cleanly

Output is human-readable, with section banners and Persian text where
appropriate.  Useful for:
  • First-time developers reading the codebase
  • Smoke-testing the build after pulling
  • Generating sample artifacts for screenshots / docs
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root or from desktop/
HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))


def banner(title: str, char: str = "=", width: int = 72) -> None:
    print()
    print(char * width)
    print(f" {title}")
    print(char * width)


def section(title: str) -> None:
    banner(title, char="-")


def narrate(msg: str) -> None:
    print(f"  → {msg}")


def main() -> int:
    banner("Rask Demo Walkthrough", char="=")
    print(f"  Started at: {datetime.now().isoformat()}")
    print(f"  Python:     {sys.version.split()[0]}")
    print(f"  Platform:   {sys.platform}")

    # -- Imports ---------------------------------------------------------
    section("1. Importing modules")
    try:
        narrate("Importing rask.config...")
        from rask import config
        narrate(f"  App version: {config.APP_VERSION}")
        narrate(f"  Data dir:    {config.DATA_DIR}")
        narrate(f"  DB path:     {config.DB_PATH}")
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    try:
        narrate("Importing rask.database...")
        from rask import database
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    try:
        narrate("Importing rask.i18n...")
        from rask import i18n
        i18n.set_language("fa")
        narrate(f"  Active language: {i18n.get_language()}")
        narrate(f"  Available: {', '.join(i18n.available_locales())}")
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    try:
        narrate("Importing rask.services...")
        from rask.services import (
            activity_service, goal_service, streak_service,
            stats_service, backup_service, export_service,
            reminder_service, template_service, badge_service,
            recurring_service, timer_service, settings_service,
        )
        narrate("  All 13 services loaded.")
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    try:
        narrate("Importing rask.features...")
        from rask.features import (
            pomodoro_service, journal_service, habit_service,
            mood_service, focus_mode, achievement_service,
            weekly_review, notification_center, analytics_service,
        )
        narrate("  All feature modules loaded.")
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    # -- DB init ---------------------------------------------------------
    section("2. Initializing database")
    narrate("Opening database...")
    database.open_db()
    stats = database.stats()
    for k, v in stats.items():
        narrate(f"  {k}: {v}")

    # -- Seed data -------------------------------------------------------
    section("3. Seeding demo data (30 days of activities)")
    try:
        from rask.utils.seed_data import seed_demo_data, clear_demo_data
        narrate("Clearing any previous demo data...")
        clear_demo_data()
        narrate("Seeding 30 days of activities...")
        result = seed_demo_data(days=30)
        narrate(f"  Created {result.get('activities', 0)} activities")
        narrate(f"  Created {result.get('goals', 0)} goals")
        narrate(f"  Created {result.get('templates', 0)} templates")
        narrate(f"  Created {result.get('badges', 0)} badges")
    except Exception as e:
        print(f"  FAILED: {e}")
        return 1

    # -- Activity service ------------------------------------------------
    section("4. Activity service")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    narrate(f"Today: {today}")
    narrate(f"Today total minutes: {activity_service.today_total()}")
    narrate(f"Today activity count: {activity_service.today_count()}")
    narrate(f"Week total minutes:   {activity_service.week_total()}")
    narrate(f"Month total minutes:  {activity_service.month_total()}")
    narrate(f"Recent activities:")
    recent = activity_service.recent(limit=5)
    for a in recent:
        title = a.get("title", "—")
        dur = a.get("duration_min", 0)
        date = a.get("date_iso", "—")
        narrate(f"  • {date}  {dur:>4}min  {title}")

    # -- Goal service ----------------------------------------------------
    section("5. Goal service")
    goals = goal_service.list(only_active=True)
    narrate(f"Active goals: {len(goals)}")
    for g in goals:
        progress = goal_service.progress_for(g["id"], today)
        title = g.get("title") or "All categories"
        narrate(f"  • {g['period']} goal '{title}': "
                f"{progress.get('current_min', 0)}/{progress.get('target_min', 0)}min "
                f"({progress.get('percent', 0):.0f}%)")

    # -- Stats service ---------------------------------------------------
    section("6. Stats service (last 30 days)")
    end = today
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    summary = stats_service.summary(start, end)
    narrate(f"Total minutes:    {summary.get('total_min', 0)}")
    narrate(f"Total activities: {summary.get('total_activities', 0)}")
    narrate(f"Avg per day:      {summary.get('avg_per_day', 0):.0f}")
    narrate(f"Avg per activity: {summary.get('avg_per_activity', 0):.0f}")
    if summary.get("best_day_iso"):
        narrate(f"Best day:         {summary['best_day_iso']}")
    narrate("By category:")
    for item in stats_service.by_category(start, end):
        narrate(f"  cat_id={item['category_id']}: {item['total_min']}min in {item['count']} activities")

    # -- Insights --------------------------------------------------------
    section("7. Smart insights")
    try:
        from rask.features.smart_insights import InsightEngine
        engine = InsightEngine()
        insights = engine.generate_all()
        narrate(f"Generated {len(insights)} insights:")
        for ins in insights[:5]:
            title = ins.title_fa if i18n.get_language() == "fa" else ins.title_en
            body = ins.body_fa if i18n.get_language() == "fa" else ins.body_en
            narrate(f"  • [{ins.kind}] {title}")
            if body:
                narrate(f"      {body}")
    except Exception as e:
        print(f"  (insights skipped: {e})")

    # -- Achievements ----------------------------------------------------
    section("8. Achievements")
    try:
        achievements = achievement_service.all()
        earned = [a for a in achievements if a.earned_at]
        narrate(f"Total achievements defined: {len(achievements)}")
        narrate(f"Achievements earned:        {len(earned)}")
        narrate(f"Total XP:                   {achievement_service.xp_total()}")
        narrate(f"Level:                      {achievement_service.level()}")
        narrate(f"Level title:                {achievement_service.level_title()}")
        narrate("Recently earned:")
        for a in earned[:5]:
            narrate(f"  • {a.title_fa} ({a.tier})")
    except Exception as e:
        print(f"  (achievements skipped: {e})")

    # -- Journal + Mood --------------------------------------------------
    section("9. Journal & Mood")
    try:
        # Create a sample journal entry for today
        journal_service.add(
            date_iso=today,
            mood=4,
            energy=3,
            title="یک روز خوب",
            body="امروز بهره‌وری بالایی داشتم.",
            gratitudes=["سلامتی", "خانواده"],
            improvements=["بیشتر بخوابم"],
            tags=["productive"],
        )
        narrate("Added today's journal entry.")
        entry = journal_service.get_by_date(today)
        if entry:
            narrate(f"  Mood: {entry.get('mood')}/5, Energy: {entry.get('energy')}/5")
        narrate(f"Journal streak: {journal_service.streak()} days")
    except Exception as e:
        print(f"  (journal skipped: {e})")

    try:
        mood_service.add(date_iso=today, mood=4, energy=3,
                          notes="_feeling good", triggers=["exercise", "sleep"])
        narrate("Added today's mood entry.")
        narrate(f"Average mood (30d): {mood_service.average_mood(30):.2f}")
        narrate(f"Average energy (30d): {mood_service.average_energy(30):.2f}")
    except Exception as e:
        print(f"  (mood skipped: {e})")

    # -- Backup ----------------------------------------------------------
    section("10. Encrypted backup")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            backup_path = os.path.join(tmp, "demo-backup.raskbk")
            narrate(f"Creating encrypted backup at: {backup_path}")
            result = backup_service.create("demo-password-123", path=backup_path)
            if result.get("success"):
                narrate(f"  Backup created ({result.get('size', 0)} bytes)")
                narrate("Verifying backup with correct password...")
                ok = backup_service.verify(backup_path, "demo-password-123")
                narrate(f"  Verify: {'OK' if ok else 'FAILED'}")
                narrate("Verifying with WRONG password (should fail)...")
                ok_wrong = backup_service.verify(backup_path, "wrong-password")
                narrate(f"  Verify wrong: {'OK (BAD!)' if ok_wrong else 'Correctly rejected'}")
                # List local backups
                backups = backup_service.list_local()
                narrate(f"Local backups: {len(backups)}")
            else:
                narrate(f"  Backup FAILED: {result.get('error')}")
    except Exception as e:
        print(f"  (backup skipped: {e})")

    # -- Exports ---------------------------------------------------------
    section("11. Data exports")
    try:
        from rask.export import CsvExporter, JsonExporter, PdfExporter
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "demo-export.csv")
            narrate(f"Exporting CSV to: {csv_path}")
            activities = database.activity_list(date_from=start, date_to=end, limit=10000)
            exp = CsvExporter(csv_path, lang="fa")
            exp.export_activities(activities)
            exp.save()
            narrate(f"  CSV size: {os.path.getsize(csv_path)} bytes")

            json_path = os.path.join(tmp, "demo-export.json")
            narrate(f"Exporting JSON to: {json_path}")
            jexp = JsonExporter(json_path)
            jexp.export_all()
            jexp.save()
            narrate(f"  JSON size: {os.path.getsize(json_path)} bytes")

            pdf_path = os.path.join(tmp, "demo-report.pdf")
            narrate(f"Exporting PDF to: {pdf_path}")
            pexp = PdfExporter(pdf_path, lang="fa")
            pexp.set_title("Rask Demo Report")
            pexp.add_heading("Rask Demo Report", level=1)
            pexp.add_paragraph(f"Generated: {datetime.now().isoformat()}")
            pexp.add_heading("Summary", level=2)
            pexp.add_summary_table({
                "Total minutes": str(summary.get("total_min", 0)),
                "Total activities": str(summary.get("total_activities", 0)),
                "Avg per day": f"{summary.get('avg_per_day', 0):.0f}",
            })
            pexp.save()
            narrate(f"  PDF size: {os.path.getsize(pdf_path)} bytes")
    except Exception as e:
        print(f"  (exports skipped: {e})")

    # -- Weekly review ---------------------------------------------------
    section("12. Weekly review")
    try:
        from rask.features.weekly_review import WeeklyReview
        wr = WeeklyReview()
        review = wr.generate()
        narrate(f"Generated weekly review:")
        narrate(f"  Week: {review.get('week', '—')}")
        narrate(f"  Total min: {review.get('total_min', 0)}")
        narrate(f"  Total activities: {review.get('total_activities', 0)}")
        narrate(f"  Top category: {review.get('top_category', '—')}")
        text = wr.format_text(review, lang="fa")
        narrate("Text preview (first 300 chars):")
        preview = text[:300].replace("\n", " ")
        print(f"    {preview}...")
    except Exception as e:
        print(f"  (weekly review skipped: {e})")

    # -- Notifications ---------------------------------------------------
    section("13. Notifications")
    try:
        notification_center.add(
            title="به رَسک خوش آمدی",
            body="این یک اعلان نمونه است.",
            kind="info",
        )
        notification_center.add(
            title="نشان جدید!",
            body="اولین فعالیتت را ثبت کردی.",
            kind="achievement",
        )
        items = notification_center.list()
        narrate(f"Notifications: {len(items)}")
        for n in items[:3]:
            narrate(f"  • [{n.kind}] {n.title}")
        narrate(f"Unread count: {notification_center.unread_count()}")
    except Exception as e:
        print(f"  (notifications skipped: {e})")

    # -- Analytics -------------------------------------------------------
    section("14. Advanced analytics")
    try:
        narrate("Productivity over time (90 days)...")
        pot = analytics_service.productivity_over_time(days=90)
        narrate(f"  {len(pot)} data points")
        narrate("Category trends (90 days)...")
        ct = analytics_service.category_trends(days=90)
        narrate(f"  {len(ct)} categories tracked")
        narrate("Weekly heatmap (7x24)...")
        hm = analytics_service.weekly_heatmap()
        narrate(f"  {len(hm)} rows x {len(hm[0]) if hm else 0} cols")
        narrate("Forecast tomorrow...")
        fc = analytics_service.forecast_tomorrow()
        narrate(f"  {fc}")
        narrate("Report card...")
        rc = analytics_service.report_card()
        for k, v in rc.items():
            narrate(f"  {k}: {v}")
    except Exception as e:
        print(f"  (analytics skipped: {e})")

    # -- Themes ----------------------------------------------------------
    section("15. Theme registry")
    try:
        from rask.features.themes_extra import ThemeRegistry
        registry = ThemeRegistry()
        themes = registry.list()
        narrate(f"Available themes: {len(themes)}")
        for name in themes:
            narrate(f"  • {name}")
    except Exception as e:
        print(f"  (themes skipped: {e})")

    # -- Cleanup ---------------------------------------------------------
    section("16. Cleanup")
    try:
        from rask.utils.seed_data import clear_demo_data
        clear_demo_data()
        narrate("Demo data cleared.")
    except Exception as e:
        print(f"  (cleanup skipped: {e})")

    banner("Demo complete!", char="=")
    print(f"  Finished at: {datetime.now().isoformat()}")
    print(f"  Total activities in DB: {database.activity_count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
