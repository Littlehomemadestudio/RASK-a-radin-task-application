"""cli.py — Command-line interface for Rask.

Provides a `python -m rask.cli` interface for common operations:
  - python -m rask.cli stats                  # show summary stats
  - python -m rask.cli activities --limit 10  # list recent activities
  - python -m rask.cli add --title "Read" --category LEARN --duration 30
  - python -m rask.cli backup --password X --output backup.rask
  - python -m rask.cli restore --password X --input backup.rask
  - python -m rask.cli goals                  # list goals
  - python -m rask.cli templates              # list templates
  - python -m rask.cli categories             # list categories
  - python -m rask.cli search "Python"        # search activities
  - python -m rask.cli clear                  # clear all data
  - python -m rask.cli version                # show version
  - python -m rask.cli help                   # show help

Useful for automation, scripting, and headless operation.
"""
from __future__ import annotations
import argparse
import json
import sys
from typing import Optional


# =====================================================================
# === COMMAND IMPLEMENTATIONS ===
# =====================================================================
def cmd_stats(args: argparse.Namespace) -> int:
    """Show summary statistics."""
    from . import database
    from . import date_utils
    from .i18n import t
    database.open_db()
    today = date_utils.today_iso()
    # Today's stats
    today_total = database.total_seconds_on(today)
    today_count = len(database.activities_by_date(today))
    # 7-day stats
    seven_start, seven_end = date_utils.preset_range("7d")
    seven_total = database.total_seconds_between(seven_start, seven_end)
    seven_count = len(database.activities_by_date_range(seven_start, seven_end))
    # 30-day stats
    thirty_start, thirty_end = date_utils.preset_range("30d")
    thirty_total = database.total_seconds_between(thirty_start, thirty_end)
    thirty_count = len(database.activities_by_date_range(thirty_start, thirty_end))
    # All-time
    all_activities = database.all_activities()
    all_count = len(all_activities)
    all_total = sum(int(a.get("duration_sec", 0) or 0) for a in all_activities)
    # Print
    print(f"Rask Statistics")
    print(f"===============")
    print()
    print(f"Today ({today}):")
    print(f"  Activities: {today_count}")
    print(f"  Total time: {date_utils.fmt_human(today_total, 'en')}")
    print()
    print(f"Last 7 days ({seven_start} to {seven_end}):")
    print(f"  Activities: {seven_count}")
    print(f"  Total time: {date_utils.fmt_human(seven_total, 'en')}")
    print(f"  Daily avg:  {date_utils.fmt_human(seven_total // 7, 'en')}")
    print()
    print(f"Last 30 days ({thirty_start} to {thirty_end}):")
    print(f"  Activities: {thirty_count}")
    print(f"  Total time: {date_utils.fmt_human(thirty_total, 'en')}")
    print(f"  Daily avg:  {date_utils.fmt_human(thirty_total // 30, 'en')}")
    print()
    print(f"All time:")
    print(f"  Activities: {all_count}")
    print(f"  Total time: {date_utils.fmt_human(all_total, 'en')}")
    # Goals
    goals = database.all_goals(active_only=True)
    print()
    print(f"Active goals: {len(goals)}")
    for g in goals:
        cat = database.category_by_id(g.get("category_id")) if g.get("category_id") else None
        cat_name = cat["name_en"] if cat else "All"
        print(f"  {g['period'].capitalize()} — {cat_name}: {g['target_minutes']} min")
    # Categories
    cats = database.all_categories()
    print()
    print(f"Categories: {len(cats)}")
    for c in cats:
        count = len(database.activities_by_date_range("2000-01-01", "2099-12-31", c["id"]))
        print(f"  {c['key']:12s} ({c['name_en']}/{c['name_fa']}): {count} activities")
    # Badges
    badges = database.all_badges()
    print()
    print(f"Badges earned: {len(badges)}")
    for b in badges:
        print(f"  {b['key']}: {b['title_en']} / {b['title_fa']}")
    # Streaks
    streaks = database.all_streaks()
    print()
    print(f"Streaks: {len(streaks)}")
    for s in streaks:
        g = database.goal_by_id(s.get("goal_id"))
        period = g["period"] if g else "?"
        print(f"  {period}: current={s['current']}, longest={s['longest']}")
    return 0


def cmd_activities(args: argparse.Namespace) -> int:
    """List recent activities."""
    from . import database
    from . import date_utils
    database.open_db()
    limit = args.limit or 20
    activities = database.recent_activities(limit, include_archived=args.archived)
    if not activities:
        print("No activities found.")
        return 0
    cats = database.all_categories()
    cat_map = {c["id"]: c for c in cats}
    print(f"Recent {len(activities)} activities:")
    print(f"{'ID':>4}  {'Date':<12}  {'Title':<30}  {'Category':<10}  {'Duration':<10}  {'Kind':<10}")
    print("-" * 90)
    for a in activities:
        cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
        cat_name = cat["name_en"] if cat else "—"
        title = (a.get("title") or "")[:30]
        dur = date_utils.fmt_human(int(a.get("duration_sec", 0) or 0), "en")
        print(f"{a['id']:>4}  {a.get('date_iso', ''):<12}  {title:<30}  {cat_name:<10}  {dur:<10}  {a.get('kind', 'manual'):<10}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Add a new activity."""
    from . import database
    from . import date_utils
    database.open_db()
    title = args.title or "(no title)"
    # Find category by key or name
    cat_id = None
    if args.category:
        cat = database.category_by_key(args.category.upper())
        if not cat:
            cats = database.all_categories()
            for c in cats:
                if args.category.lower() in (c["name_en"].lower(), c["name_fa"]):
                    cat = c
                    break
        if cat:
            cat_id = cat["id"]
        else:
            print(f"Warning: Category '{args.category}' not found")
    # Duration
    duration_sec = 0
    if args.duration:
        # Parse "30" (minutes), "1h30m", "90m", "3600s"
        d = args.duration.lower()
        if d.endswith("h"):
            try:
                duration_sec = int(float(d[:-1]) * 3600)
            except ValueError:
                pass
        elif d.endswith("m"):
            try:
                duration_sec = int(float(d[:-1]) * 60)
            except ValueError:
                pass
        elif d.endswith("s"):
            try:
                duration_sec = int(d[:-1])
            except ValueError:
                pass
        else:
            try:
                duration_sec = int(float(d) * 60)  # default minutes
            except ValueError:
                pass
    # Date
    date_iso = args.date or date_utils.today_iso()
    # Insert
    activity_id = database.insert_activity({
        "title": title,
        "category_id": cat_id,
        "kind": "manual",
        "date_iso": date_iso,
        "duration_sec": duration_sec,
        "note": args.note or "",
    })
    print(f"Added activity #{activity_id}: '{title}' ({date_utils.fmt_human(duration_sec, 'en')})")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    """Create an encrypted backup."""
    from . import database
    from . import crypto
    database.open_db()
    if not crypto.crypto_available():
        print("ERROR: cryptography library not installed. Run: pip install cryptography")
        return 1
    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("Backup password: ")
    if len(password) < 6:
        print("ERROR: Password must be at least 6 characters")
        return 1
    payload = database.export_all()
    output = args.output or f"rask-backup-{date_utils.today_iso()}.rask"
    try:
        bytes_written = crypto.write_backup_file(output, payload, password)
        print(f"Backup saved to {output} ({bytes_written} bytes)")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore from an encrypted backup."""
    from . import database
    from . import crypto
    database.open_db()
    if not crypto.crypto_available():
        print("ERROR: cryptography library not installed")
        return 1
    if not args.input:
        print("ERROR: --input required")
        return 1
    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("Backup password: ")
    try:
        payload = crypto.read_backup_file(args.input, password)
        print(f"Restoring backup with {sum(len(v) for v in payload.values() if isinstance(v, list))} records...")
        database.replace_all(payload)
        print("Restore complete.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def cmd_goals(args: argparse.Namespace) -> int:
    """List goals."""
    from . import database
    database.open_db()
    goals = database.all_goals()
    if not goals:
        print("No goals found.")
        return 0
    print(f"Goals ({len(goals)}):")
    for g in goals:
        cat = database.category_by_id(g.get("category_id")) if g.get("category_id") else None
        cat_name = cat["name_en"] if cat else "All"
        active = "✓" if g.get("active") else "✗"
        print(f"  [{active}] #{g['id']}: {g['period']} — {cat_name} — {g['target_minutes']} min")
        streak = database.streak_for_goal(g["id"])
        if streak:
            print(f"          Streak: current={streak['current']}, longest={streak['longest']}")
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    """List templates."""
    from . import database
    database.open_db()
    templates = database.all_templates()
    if not templates:
        print("No templates found.")
        return 0
    print(f"Templates ({len(templates)}):")
    for t in templates:
        cat = database.category_by_id(t.get("category_id")) if t.get("category_id") else None
        cat_name = cat["name_en"] if cat else "—"
        print(f"  #{t['id']}: {t['title']} — {cat_name} — {t.get('default_duration_min', 30)} min")
    return 0


def cmd_categories(args: argparse.Namespace) -> int:
    """List categories."""
    from . import database
    database.open_db()
    cats = database.all_categories(include_archived=True)
    print(f"Categories ({len(cats)}):")
    for c in cats:
        archived = " (archived)" if c.get("archived") else ""
        custom = " (custom)" if c.get("custom") else ""
        print(f"  #{c['id']}: {c['key']:12s} — {c['name_en']}/{c['name_fa']} — {c['color']}{archived}{custom}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search activities."""
    from . import database
    database.open_db()
    if not args.query:
        print("ERROR: search query required")
        return 1
    results = database.search_activities(args.query, limit=args.limit or 50)
    if not results:
        print(f"No results for '{args.query}'")
        return 0
    print(f"Search results for '{args.query}' ({len(results)} found):")
    for a in results:
        print(f"  #{a['id']} [{a.get('date_iso', '')}] {a.get('title', '')} ({a.get('duration_sec', 0)}s)")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """Clear all data."""
    from . import database
    if not args.force:
        response = input("This will permanently delete ALL data. Type 'yes' to confirm: ")
        if response.lower() != "yes":
            print("Aborted.")
            return 1
    database.open_db()
    database.clear_all_data()
    print("All data cleared.")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    """Show version info."""
    from . import config
    print(f"{config.APP_NAME} v{config.APP_VERSION}")
    print(f"  {config.APP_COPYRIGHT}")
    print(f"  Data dir: {config.DATA_DIR}")
    print(f"  DB path:  {config.DB_PATH}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export activities to CSV/JSON."""
    from . import database
    from . import exporters
    from . import date_utils
    database.open_db()
    fmt = args.format or "csv"
    start, end = date_utils.preset_range(args.preset or "30d")
    activities = database.activities_by_date_range(start, end,
                                                     include_archived=args.archived)
    if not activities:
        print(f"No activities in range {start} to {end}")
        return 0
    output = args.output or f"rask-export-{start}-to-{end}.{fmt}"
    if fmt == "csv":
        rows = exporters.export_csv(output, activities, "en")
        print(f"Exported {rows} activities to {output}")
    elif fmt == "json":
        payload = database.export_all()
        bytes_written = exporters.export_json(output, payload)
        print(f"Exported to {output} ({bytes_written} bytes)")
    elif fmt == "pdf":
        summary = exporters.build_summary(start, end, "en")
        bytes_written = exporters.export_pdf(output, summary, activities, "en")
        print(f"Exported PDF to {output} ({bytes_written} bytes)")
    elif fmt == "txt":
        summary = exporters.build_summary(start, end, "en")
        bytes_written = exporters.export_text(output, summary, activities, "en")
        print(f"Exported text to {output} ({bytes_written} bytes)")
    else:
        print(f"ERROR: Unknown format '{fmt}'")
        return 1
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Run the test suite."""
    from . import tests
    return tests.run_all()


# =====================================================================
# === MAIN ENTRY POINT ===
# =====================================================================
def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="rask",
        description="Rask — a luxurious, minimal time & activity tracker",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show summary statistics")
    p_stats.set_defaults(func=cmd_stats)

    # activities
    p_act = subparsers.add_parser("activities", help="List recent activities")
    p_act.add_argument("--limit", type=int, default=20, help="Max activities to show")
    p_act.add_argument("--archived", action="store_true", help="Include archived")
    p_act.set_defaults(func=cmd_activities)

    # add
    p_add = subparsers.add_parser("add", help="Add a new activity")
    p_add.add_argument("--title", help="Activity title")
    p_add.add_argument("--category", help="Category key or name (e.g., FOCUS, Focus, or تمرکز)")
    p_add.add_argument("--duration", help='Duration (e.g., "30" for 30 min, "1h30m", "90m", "3600s")')
    p_add.add_argument("--date", help="Date (YYYY-MM-DD, default today)")
    p_add.add_argument("--note", help="Note")
    p_add.set_defaults(func=cmd_add)

    # backup
    p_backup = subparsers.add_parser("backup", help="Create encrypted backup")
    p_backup.add_argument("--password", help="Backup password")
    p_backup.add_argument("--output", "-o", help="Output file (default: rask-backup-YYYY-MM-DD.rask)")
    p_backup.set_defaults(func=cmd_backup)

    # restore
    p_restore = subparsers.add_parser("restore", help="Restore from encrypted backup")
    p_restore.add_argument("--input", "-i", help="Backup file to restore")
    p_restore.add_argument("--password", help="Backup password")
    p_restore.set_defaults(func=cmd_restore)

    # goals
    p_goals = subparsers.add_parser("goals", help="List goals")
    p_goals.set_defaults(func=cmd_goals)

    # templates
    p_templates = subparsers.add_parser("templates", help="List templates")
    p_templates.set_defaults(func=cmd_templates)

    # categories
    p_cats = subparsers.add_parser("categories", help="List categories")
    p_cats.set_defaults(func=cmd_categories)

    # search
    p_search = subparsers.add_parser("search", help="Search activities")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=50, help="Max results")
    p_search.set_defaults(func=cmd_search)

    # clear
    p_clear = subparsers.add_parser("clear", help="Clear all data (destructive)")
    p_clear.add_argument("--force", action="store_true", help="Skip confirmation")
    p_clear.set_defaults(func=cmd_clear)

    # version
    p_version = subparsers.add_parser("version", help="Show version info")
    p_version.set_defaults(func=cmd_version)

    # export
    p_export = subparsers.add_parser("export", help="Export activities")
    p_export.add_argument("--format", choices=["csv", "json", "pdf", "txt"], default="csv")
    p_export.add_argument("--preset", choices=["today", "7d", "30d", "month", "year"], default="30d")
    p_export.add_argument("--output", "-o", help="Output file")
    p_export.add_argument("--archived", action="store_true", help="Include archived")
    p_export.set_defaults(func=cmd_export)

    # test
    p_test = subparsers.add_parser("test", help="Run test suite")
    p_test.set_defaults(func=cmd_test)

    # help
    p_help = subparsers.add_parser("help", help="Show help")
    p_help.set_defaults(func=lambda args: parser.print_help() or 0)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
