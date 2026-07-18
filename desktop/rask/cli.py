"""
rask.cli
========

Command-line interface for the Rask desktop application.

Subcommands
-----------
``rask init``                — initialise the SQLite database
``rask stats``               — show quick stats (total activities, total time,
                                current streak)
``rask backup create <pw>``  — create an encrypted backup
``rask backup restore <file> <pw>`` — restore from a backup
``rask backup list``         — list local backups
``rask export csv``          — export activities as CSV
``rask export pdf``          — export a PDF report
``rask export json``         — export all data as JSON
``rask activity add``        — add an activity
``rask activity list``       — list activities
``rask activity delete ID``  — delete an activity
``rask goal add``            — add a goal
``rask goal list``           — list goals
``rask category list``       — list categories
``rask category add``        — add a category
``rask db vacuum``           — vacuum the database
``rask db info``             — show DB info (path, size, table counts)
``rask db reset --yes``      — wipe all data
``rask lang list``           — list supported languages
``rask version``             — show version info
``rask doctor``              — probe the runtime environment
``rask help``                — show help

Output formats
--------------
Most commands accept a ``--format`` flag (``text`` (default), ``json``,
``csv``).  Exit codes follow the Unix convention:
  0  — success
  1  — runtime error (DB not found, encryption failed, …)
  2  — bad arguments

Usage
-----
::

    python -m rask.cli stats
    python -m rask.cli activity add --title "Reading" --duration 30 --category LEARN
    python -m rask.cli backup create "my-password"
    python -m rask.cli export csv --from 2025-01-01 --to 2025-01-31
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import config
from . import database as db
from . import i18n
from .core.logging_utils import get_logger, setup_logging

__all__ = ["main", "build_parser", "run_command"]

_log = get_logger("cli")


# =============================================================================
# === Exit codes                                                              ===
# =============================================================================

EXIT_OK: int = 0
EXIT_ERROR: int = 1
EXIT_BAD_ARGS: int = 2


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _ensure_db() -> None:
    """Open the database.  Idempotent — safe to call from every command."""
    try:
        db.open_db()
    except Exception as exc:  # noqa: BLE001 — surface to user
        _log.error("Database initialisation failed: %s", exc)
        raise


def _print_json(data: Any) -> None:
    """Pretty-print a JSON payload to stdout."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _print_table(
    rows: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    header: bool = True,
) -> None:
    """Print a list of dicts as a fixed-width text table.

    ``columns`` is a list of ``(key)`` tuples or just strings; we use
    the key for both lookup and header label (callers can pre-rename
    keys for prettier headers).
    """
    if not rows:
        print("  (no rows)")
        return
    # Compute column widths
    widths: Dict[str, int] = {}
    for col in columns:
        widths[col] = len(col)
        for r in rows:
            v = r.get(col, "")
            s = str(v) if v is not None else ""
            if len(s) > widths[col]:
                widths[col] = len(s)
    # Header
    if header:
        header_line = "  " + "  ".join(
            col.ljust(widths[col]) for col in columns)
        print(header_line)
        print("  " + "  ".join("-" * widths[col] for col in columns))
    # Rows
    for r in rows:
        line = "  " + "  ".join(
            str(r.get(col, "") or "").ljust(widths[col]) for col in columns)
        print(line)


def _format_minutes(minutes: int, lang: str = "fa") -> str:
    """Format a minute count as ``"۲ ساعت و ۳۰ دقیقه"`` style."""
    try:
        minutes = int(minutes or 0)
    except (TypeError, ValueError):
        return "0"
    if minutes <= 0:
        return "0" if lang != "fa" else "۰"
    h, m = divmod(minutes, 60)
    if lang == "fa":
        if h > 0:
            s = f"{h}س {m}د"
        else:
            s = f"{m}د"
        return i18n.to_fa_digits(s)
    return f"{h}h {m}m" if h > 0 else f"{m}m"


def _parse_date(s: Optional[str], *, default: Optional[str] = None) -> Optional[str]:
    """Parse a YYYY-MM-DD string.  Returns ``None`` on invalid input."""
    if not s:
        return default
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return None


def _default_date_range() -> tuple[str, str]:
    """Return the last 30 days as a ``(from, to)`` ISO date tuple."""
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
    return start, today


# =============================================================================
# === Sub-command implementations                                            ===
# =============================================================================

def cmd_init(args: argparse.Namespace) -> int:
    """``rask init`` — initialise the SQLite database."""
    _ensure_db()
    print(f"Database initialised at {config.DB_PATH}")
    return EXIT_OK


def cmd_version(args: argparse.Namespace) -> int:
    """``rask version`` — show version info."""
    info = {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "build": config.APP_BUILD,
        "author": config.APP_AUTHOR,
        "license": config.APP_LICENSE,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "db_path": str(config.DB_PATH),
        "data_dir": str(config.DATA_DIR),
    }
    if getattr(args, "format", "text") == "json":
        _print_json(info)
    else:
        print(f"  {config.APP_NAME} v{config.APP_VERSION} "
              f"(build {config.APP_BUILD})")
        print(f"  Author : {config.APP_AUTHOR}")
        print(f"  License: {config.APP_LICENSE}")
        print(f"  Python : {info['python']}  ({info['platform']})")
        print(f"  Data   : {info['data_dir']}")
        print(f"  DB     : {info['db_path']}")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    """``rask doctor`` — probe the runtime environment."""
    from . import check_env
    report = check_env.check_environment()
    if getattr(args, "format", "text") == "json":
        _print_json(report)
        return EXIT_OK if report["all_required_present"] else EXIT_ERROR
    check_env.print_report(report)
    return EXIT_OK if report["all_required_present"] else EXIT_ERROR


def cmd_stats(args: argparse.Namespace) -> int:
    """``rask stats`` — show quick stats."""
    _ensure_db()
    from .services import stats_service, streak_service
    today = datetime.now().strftime("%Y-%m-%d")
    summary = stats_service.summary(today, today)
    # All-time stats
    all_summary = stats_service.summary("1970-01-01", today)
    current_streak = stats_service.current_streak()
    longest_streak = stats_service.longest_streak_ever()
    if getattr(args, "format", "text") == "json":
        _print_json({
            "today": summary,
            "all_time": all_summary,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
        })
        return EXIT_OK
    print(f"\n  Rask quick stats ({today})\n  {'─' * 40}")
    print(f"  Today's activities : {i18n.to_fa_digits(summary['total_activities'])}")
    print(f"  Today's total      : {_format_minutes(summary['total_min'])}")
    print(f"  Current streak     : {i18n.to_fa_digits(current_streak)} days")
    print(f"  Longest streak     : {i18n.to_fa_digits(longest_streak)} days")
    print(f"\n  All-time\n  {'─' * 40}")
    print(f"  Total activities   : {i18n.to_fa_digits(all_summary['total_activities'])}")
    print(f"  Total time         : {_format_minutes(all_summary['total_min'])}")
    print(f"  Active days        : {i18n.to_fa_digits(all_summary['day_count'])}")
    if all_summary.get("longest_session"):
        ls = all_summary["longest_session"]
        print(f"  Longest session    : {ls.get('title', '—')} "
              f"({_format_minutes(int(ls.get('duration_min', 0)))})")
    print()
    return EXIT_OK


# ------------------------------------------------------------------
# Backup commands
# ------------------------------------------------------------------

def cmd_backup_create(args: argparse.Namespace) -> int:
    """``rask backup create <password>``."""
    _ensure_db()
    from .services import backup_service
    password = args.password
    if not password:
        print("ERROR: password is required", file=sys.stderr)
        return EXIT_BAD_ARGS
    try:
        result = backup_service.create(password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(result)
    else:
        print(f"  Backup created: {result.get('path')}")
        size = result.get("size", 0)
        print(f"  Size: {size} bytes")
    return EXIT_OK


def cmd_backup_restore(args: argparse.Namespace) -> int:
    """``rask backup restore <file> <password>``."""
    _ensure_db()
    from .services import backup_service
    if not os.path.isfile(args.file):
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return EXIT_BAD_ARGS
    try:
        result = backup_service.restore(args.file, args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(result)
    else:
        print(f"  Backup restored from {args.file}")
    return EXIT_OK


def cmd_backup_list(args: argparse.Namespace) -> int:
    """``rask backup list`` — list local backups."""
    _ensure_db()
    from .services import backup_service
    try:
        backups = backup_service.list_local()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(backups)
        return EXIT_OK
    if not backups:
        print("  (no backups)")
        return EXIT_OK
    print(f"\n  Local backups ({len(backups)} total)\n  {'─' * 60}")
    rows = []
    for b in backups:
        rows.append({
            "filename": os.path.basename(b.get("path", "")),
            "size": _human_size(b.get("size", 0)),
            "modified": b.get("modified", "")[:19],
        })
    _print_table(rows, ("filename", "size", "modified"))
    print()
    return EXIT_OK


def _human_size(num_bytes: int) -> str:
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ------------------------------------------------------------------
# Export commands
# ------------------------------------------------------------------

def cmd_export_csv(args: argparse.Namespace) -> int:
    """``rask export csv``."""
    _ensure_db()
    from .services import export_service
    date_from, date_to = _resolve_range(args)
    out = args.out or None
    try:
        result = export_service.export_csv(date_from, date_to, out)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(result)
    else:
        print(f"  CSV exported: {result.get('path')}")
        print(f"  Rows: {result.get('record_count')}, "
              f"Size: {_human_size(result.get('size', 0))}")
    return EXIT_OK


def cmd_export_pdf(args: argparse.Namespace) -> int:
    """``rask export pdf``."""
    _ensure_db()
    from .services import export_service
    date_from, date_to = _resolve_range(args)
    out = args.out or None
    options = {
        "lang": getattr(args, "lang", None) or "fa",
        "include_charts": not getattr(args, "no_charts", False),
        "include_top_activities": True,
    }
    try:
        result = export_service.export_pdf(date_from, date_to, out, options)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(result)
    else:
        print(f"  PDF exported: {result.get('path')}")
        print(f"  Size: {_human_size(result.get('size', 0))}")
    return EXIT_OK


def cmd_export_json(args: argparse.Namespace) -> int:
    """``rask export json`` — full database export."""
    _ensure_db()
    from .services import export_service
    out = args.out or None
    # Use a wide range to capture everything
    date_from = "1970-01-01"
    date_to = datetime.now().strftime("%Y-%m-%d")
    try:
        result = export_service.export_json(date_from, date_to, out)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not result.get("success"):
        print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(result)
    else:
        print(f"  JSON exported: {result.get('path')}")
        print(f"  Rows: {result.get('record_count')}, "
              f"Size: {_human_size(result.get('size', 0))}")
    return EXIT_OK


def _resolve_range(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve a date range from CLI args.

    Accepts either explicit ``--from`` / ``--to`` or a ``--preset``
    shortcut (``today`` / ``week`` / ``month`` / ``year`` / ``all``).
    Defaults to the last 30 days.
    """
    if getattr(args, "preset", None):
        today = datetime.now().strftime("%Y-%m-%d")
        preset = args.preset
        if preset == "today":
            return today, today
        if preset == "yesterday":
            y = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            return y, y
        if preset == "week":
            start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
            return start, today
        if preset == "month":
            start = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
            return start, today
        if preset == "year":
            start = (datetime.now() - timedelta(days=364)).strftime("%Y-%m-%d")
            return start, today
        if preset == "all":
            return "1970-01-01", today
    date_from = _parse_date(getattr(args, "from_date", None))
    date_to = _parse_date(getattr(args, "to_date", None))
    if not date_from and not date_to:
        return _default_date_range()
    if not date_from:
        date_from = (datetime.strptime(date_to, "%Y-%m-%d")
                      - timedelta(days=29)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


# ------------------------------------------------------------------
# Activity commands
# ------------------------------------------------------------------

def cmd_activity_add(args: argparse.Namespace) -> int:
    """``rask activity add``."""
    _ensure_db()
    from .services import activity_service
    title = args.title
    if not title:
        print("ERROR: --title is required", file=sys.stderr)
        return EXIT_BAD_ARGS
    # Resolve category by key
    category_id: Optional[int] = None
    if args.category:
        cat = db.category_get_by_key(args.category.upper())
        if cat is None:
            print(f"ERROR: unknown category key: {args.category}",
                  file=sys.stderr)
            return EXIT_BAD_ARGS
        category_id = int(cat["id"])
    try:
        activity = activity_service.add(
            title=title,
            category_id=category_id,
            duration_min=int(args.duration or 0),
            date_iso=args.date,
            notes=args.notes,
            kind="manual",
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_BAD_ARGS
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(activity)
    else:
        print(f"  Activity added: id={activity['id']}, "
              f"title={activity['title']}, "
              f"duration={activity.get('duration_min', 0)}m")
    return EXIT_OK


def cmd_activity_list(args: argparse.Namespace) -> int:
    """``rask activity list``."""
    _ensure_db()
    limit = int(args.limit or 20)
    try:
        rows = db.activity_list(limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json([dict(r) for r in rows])
        return EXIT_OK
    if not rows:
        print("  (no activities)")
        return EXIT_OK
    # Build a category map for nicer display
    cats = {int(c["id"]): c for c in db.category_list(include_archived=True)}
    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        cat_id = r.get("category_id")
        cat = cats.get(int(cat_id)) if cat_id else None
        cat_name = (cat.get("name_en") or cat.get("name_fa")) if cat else "—"
        out_rows.append({
            "id": r.get("id"),
            "date": r.get("date_iso", ""),
            "title": r.get("title", ""),
            "category": cat_name,
            "min": r.get("duration_min", 0),
            "kind": r.get("kind", "manual"),
        })
    print(f"\n  Recent activities (showing {len(out_rows)})\n  {'─' * 60}")
    _print_table(out_rows, ("id", "date", "title", "category", "min", "kind"))
    print()
    return EXIT_OK


def cmd_activity_delete(args: argparse.Namespace) -> int:
    """``rask activity delete ID``."""
    _ensure_db()
    try:
        activity_id = int(args.id)
    except (TypeError, ValueError):
        print("ERROR: ID must be an integer", file=sys.stderr)
        return EXIT_BAD_ARGS
    try:
        ok = db.activity_delete(activity_id, soft=True)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not ok:
        print(f"ERROR: activity {activity_id} not found", file=sys.stderr)
        return EXIT_ERROR
    print(f"  Activity {activity_id} deleted.")
    return EXIT_OK


# ------------------------------------------------------------------
# Goal commands
# ------------------------------------------------------------------

def cmd_goal_add(args: argparse.Namespace) -> int:
    """``rask goal add``."""
    _ensure_db()
    from .services import goal_service
    period = args.period
    if period not in ("daily", "weekly", "monthly"):
        print(f"ERROR: --period must be daily/weekly/monthly, got {period}",
              file=sys.stderr)
        return EXIT_BAD_ARGS
    target = int(args.target or 0)
    if target <= 0:
        print("ERROR: --target is required and must be > 0", file=sys.stderr)
        return EXIT_BAD_ARGS
    category_id: Optional[int] = None
    if args.category:
        cat = db.category_get_by_key(args.category.upper())
        if cat is None:
            print(f"ERROR: unknown category: {args.category}", file=sys.stderr)
            return EXIT_BAD_ARGS
        category_id = int(cat["id"])
    try:
        goal = goal_service.add(
            period=period,
            target_minutes=target,
            category_id=category_id,
            title=args.title,
        )
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_BAD_ARGS
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(goal)
    else:
        print(f"  Goal added: id={goal['id']}, period={goal['period']}, "
              f"target={goal['target_minutes']}m")
    return EXIT_OK


def cmd_goal_list(args: argparse.Namespace) -> int:
    """``rask goal list``."""
    _ensure_db()
    from .services import goal_service
    try:
        goals = goal_service.list(only_active=False)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json(goals)
        return EXIT_OK
    if not goals:
        print("  (no goals)")
        return EXIT_OK
    cats = {int(c["id"]): c for c in db.category_list(include_archived=True)}
    out_rows: List[Dict[str, Any]] = []
    for g in goals:
        cat_id = g.get("category_id")
        cat = cats.get(int(cat_id)) if cat_id else None
        cat_name = (cat.get("name_en") if cat else "—") if cat else "—"
        out_rows.append({
            "id": g.get("id"),
            "period": g.get("period", ""),
            "target": g.get("target_minutes", 0),
            "category": cat_name,
            "title": g.get("title") or "—",
            "active": "yes" if g.get("active", 1) else "no",
        })
    print(f"\n  Goals ({len(out_rows)} total)\n  {'─' * 60}")
    _print_table(out_rows, ("id", "period", "target", "category", "title", "active"))
    print()
    return EXIT_OK


# ------------------------------------------------------------------
# Category commands
# ------------------------------------------------------------------

def cmd_category_list(args: argparse.Namespace) -> int:
    """``rask category list``."""
    _ensure_db()
    include_archived = getattr(args, "all", False)
    try:
        cats = db.category_list(include_archived=include_archived)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json([dict(c) for c in cats])
        return EXIT_OK
    if not cats:
        print("  (no categories)")
        return EXIT_OK
    out_rows = [{
        "id": c.get("id"),
        "key": c.get("key", ""),
        "name_en": c.get("name_en", ""),
        "name_fa": c.get("name_fa", ""),
        "color": c.get("color", ""),
        "archived": "yes" if c.get("archived") else "no",
    } for c in cats]
    print(f"\n  Categories ({len(out_rows)} total)\n  {'─' * 60}")
    _print_table(out_rows, ("id", "key", "name_en", "name_fa", "color", "archived"))
    print()
    return EXIT_OK


def cmd_category_add(args: argparse.Namespace) -> int:
    """``rask category add``."""
    _ensure_db()
    key = (args.key or "").upper()
    if not key:
        print("ERROR: --key is required", file=sys.stderr)
        return EXIT_BAD_ARGS
    if not args.name_en or not args.name_fa:
        print("ERROR: --name-en and --name-fa are required", file=sys.stderr)
        return EXIT_BAD_ARGS
    color = args.color or config.GOLD
    # Hex validation (basic)
    if not (color.startswith("#") and len(color) in (4, 7)):
        print(f"ERROR: --color must be a hex like #D4AF37, got {color}",
              file=sys.stderr)
        return EXIT_BAD_ARGS
    if db.category_get_by_key(key) is not None:
        print(f"ERROR: category with key '{key}' already exists",
              file=sys.stderr)
        return EXIT_BAD_ARGS
    try:
        new_id = db.category_add(
            key=key, name_en=args.name_en, name_fa=args.name_fa,
            color=color, icon=args.icon or "ring",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if getattr(args, "format", "text") == "json":
        _print_json({"id": new_id, "key": key,
                      "name_en": args.name_en, "name_fa": args.name_fa,
                      "color": color})
    else:
        print(f"  Category added: id={new_id}, key={key}")
    return EXIT_OK


# ------------------------------------------------------------------
# Database commands
# ------------------------------------------------------------------

def cmd_db_vacuum(args: argparse.Namespace) -> int:
    """``rask db vacuum``."""
    _ensure_db()
    try:
        db.vacuum()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"  Database vacuumed. "
          f"New size: {_human_size(db.db_file_size())}")
    return EXIT_OK


def cmd_db_info(args: argparse.Namespace) -> int:
    """``rask db info``."""
    _ensure_db()
    try:
        counts = db.stats()
        integrity = db.integrity_check()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    info = {
        "path": str(config.DB_PATH),
        "size_bytes": db.db_file_size(),
        "size_human": _human_size(db.db_file_size()),
        "table_counts": {k: v for k, v in counts.items() if not k.startswith("_")},
        "integrity_check": integrity,
    }
    if getattr(args, "format", "text") == "json":
        _print_json(info)
        return EXIT_OK
    print(f"\n  Database info\n  {'─' * 40}")
    print(f"  Path     : {info['path']}")
    print(f"  Size     : {info['size_human']}")
    print(f"  Integrity: {'OK' if integrity == ['ok'] else integrity}")
    print(f"\n  Table counts\n  {'─' * 40}")
    for table, n in info["table_counts"].items():
        print(f"  {table:<16}: {i18n.to_fa_digits(n)}")
    print()
    return EXIT_OK


def cmd_db_reset(args: argparse.Namespace) -> int:
    """``rask db reset --yes``."""
    if not getattr(args, "yes", False):
        print("ERROR: --yes is required to confirm data wipe",
              file=sys.stderr)
        return EXIT_BAD_ARGS
    _ensure_db()
    try:
        # Wipe every table
        conn = db.get_conn()
        for t in ("activity_tags", "tags", "activities", "sessions",
                   "recurring", "reminders", "badges", "templates",
                   "streaks", "goals", "categories", "settings", "kv"):
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:  # noqa: BLE001 — table may not exist
                pass
        conn.commit()
        # Re-seed defaults
        db.open_db()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print("  Database reset. Default categories and settings re-seeded.")
    return EXIT_OK


# ------------------------------------------------------------------
# Language commands
# ------------------------------------------------------------------

def cmd_lang_list(args: argparse.Namespace) -> int:
    """``rask lang list`` — list supported languages."""
    langs = []
    for code, info in config.SUPPORTED_LANGUAGES.items():
        langs.append({
            "code": code,
            "name_en": info.get("name_en", ""),
            "name_fa": info.get("name_fa", ""),
            "rtl": info.get("rtl", False),
        })
    if getattr(args, "format", "text") == "json":
        _print_json(langs)
        return EXIT_OK
    print(f"\n  Supported languages ({len(langs)})\n  {'─' * 40}")
    _print_table(langs, ("code", "name_en", "name_fa", "rtl"))
    print()
    return EXIT_OK


# =============================================================================
# === Argument parser                                                          ===
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser.

    Exposed as a function so callers (e.g. tests) can introspect the
    parser without invoking :func:`main`.
    """
    parser = argparse.ArgumentParser(
        prog="rask",
        description="Rask — beautiful offline time-tracking. "
                    "Run `rask <command> -h` for per-command help.",
    )
    parser.add_argument(
        "--format", choices=("text", "json", "csv"), default="text",
        help="Output format (default: text)")
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable verbose debug logging")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # --- init ---
    p_init = sub.add_parser("init", help="Initialise the database")
    p_init.set_defaults(func=cmd_init)

    # --- version ---
    p_version = sub.add_parser("version", help="Show version info")
    p_version.set_defaults(func=cmd_version)

    # --- doctor ---
    p_doc = sub.add_parser("doctor", help="Probe the runtime environment")
    p_doc.set_defaults(func=cmd_doctor)
    p_doc.add_argument("--format", choices=("text", "json"),
                        default="text", help="Output format")

    # --- stats ---
    p_stats = sub.add_parser("stats", help="Show quick stats")
    p_stats.set_defaults(func=cmd_stats)

    # --- backup ---
    p_backup = sub.add_parser("backup", help="Encrypted backup operations")
    bsub = p_backup.add_subparsers(dest="backup_command", metavar="<sub>")
    p_b_create = bsub.add_parser("create", help="Create a backup")
    p_b_create.add_argument("password", help="Encryption password")
    p_b_create.set_defaults(func=cmd_backup_create)
    p_b_restore = bsub.add_parser("restore", help="Restore from a backup")
    p_b_restore.add_argument("file", help="Backup file path")
    p_b_restore.add_argument("password", help="Decryption password")
    p_b_restore.set_defaults(func=cmd_backup_restore)
    p_b_list = bsub.add_parser("list", help="List local backups")
    p_b_list.set_defaults(func=cmd_backup_list)

    # --- export ---
    p_export = sub.add_parser("export", help="Export data")
    esub = p_export.add_subparsers(dest="export_command", metavar="<sub>")
    p_e_csv = esub.add_parser("csv", help="Export activities as CSV")
    _add_date_args(p_e_csv)
    p_e_csv.add_argument("--out", help="Output file path")
    p_e_csv.set_defaults(func=cmd_export_csv)
    p_e_pdf = esub.add_parser("pdf", help="Export a PDF report")
    _add_date_args(p_e_pdf)
    p_e_pdf.add_argument("--out", help="Output file path")
    p_e_pdf.add_argument("--no-charts", action="store_true",
                          help="Disable chart rendering")
    p_e_pdf.add_argument("--lang", default="fa",
                          help="Report language (default: fa)")
    p_e_pdf.set_defaults(func=cmd_export_pdf)
    p_e_json = esub.add_parser("json", help="Export all data as JSON")
    p_e_json.add_argument("--out", help="Output file path")
    p_e_json.set_defaults(func=cmd_export_json)

    # --- activity ---
    p_act = sub.add_parser("activity", help="Activity CRUD")
    asub = p_act.add_subparsers(dest="activity_command", metavar="<sub>")
    p_a_add = asub.add_parser("add", help="Add an activity")
    p_a_add.add_argument("--title", required=True, help="Activity title")
    p_a_add.add_argument("--duration", type=int, default=0,
                          help="Duration in minutes")
    p_a_add.add_argument("--category", help="Category key (e.g. FOCUS)")
    p_a_add.add_argument("--date", help="ISO date YYYY-MM-DD (default: today)")
    p_a_add.add_argument("--notes", help="Free-form notes")
    p_a_add.set_defaults(func=cmd_activity_add)
    p_a_list = asub.add_parser("list", help="List activities")
    p_a_list.add_argument("--limit", type=int, default=20,
                           help="Max rows (default: 20)")
    p_a_list.set_defaults(func=cmd_activity_list)
    p_a_del = asub.add_parser("delete", help="Delete an activity")
    p_a_del.add_argument("id", help="Activity ID")
    p_a_del.set_defaults(func=cmd_activity_delete)

    # --- goal ---
    p_goal = sub.add_parser("goal", help="Goal CRUD")
    gsub = p_goal.add_subparsers(dest="goal_command", metavar="<sub>")
    p_g_add = gsub.add_parser("add", help="Add a goal")
    p_g_add.add_argument("--period", required=True,
                          choices=("daily", "weekly", "monthly"))
    p_g_add.add_argument("--target", type=int, required=True,
                          help="Target minutes for the period")
    p_g_add.add_argument("--category", help="Category key (optional)")
    p_g_add.add_argument("--title", help="Optional title")
    p_g_add.set_defaults(func=cmd_goal_add)
    p_g_list = gsub.add_parser("list", help="List goals")
    p_g_list.set_defaults(func=cmd_goal_list)

    # --- category ---
    p_cat = sub.add_parser("category", help="Category CRUD")
    csub = p_cat.add_subparsers(dest="category_command", metavar="<sub>")
    p_c_list = csub.add_parser("list", help="List categories")
    p_c_list.add_argument("--all", action="store_true",
                           help="Include archived categories")
    p_c_list.set_defaults(func=cmd_category_list)
    p_c_add = csub.add_parser("add", help="Add a category")
    p_c_add.add_argument("--key", required=True,
                          help="Uppercase unique key (e.g. FOCUS)")
    p_c_add.add_argument("--name-en", required=True, help="English name")
    p_c_add.add_argument("--name-fa", required=True, help="Persian name")
    p_c_add.add_argument("--color", help="Hex colour (e.g. #D4AF37)")
    p_c_add.add_argument("--icon", default="ring",
                          help="Icon name (default: ring)")
    p_c_add.set_defaults(func=cmd_category_add)

    # --- db ---
    p_db = sub.add_parser("db", help="Database operations")
    dsub = p_db.add_subparsers(dest="db_command", metavar="<sub>")
    p_d_vac = dsub.add_parser("vacuum", help="Vacuum the database")
    p_d_vac.set_defaults(func=cmd_db_vacuum)
    p_d_info = dsub.add_parser("info", help="Show DB info")
    p_d_info.set_defaults(func=cmd_db_info)
    p_d_reset = dsub.add_parser("reset", help="Wipe all data")
    p_d_reset.add_argument("--yes", action="store_true",
                             help="Confirm data wipe")
    p_d_reset.set_defaults(func=cmd_db_reset)

    # --- lang ---
    p_lang = sub.add_parser("lang", help="Language utilities")
    lsub = p_lang.add_subparsers(dest="lang_command", metavar="<sub>")
    p_l_list = lsub.add_parser("list", help="List supported languages")
    p_l_list.set_defaults(func=cmd_lang_list)

    return parser


def _add_date_args(p: argparse.ArgumentParser) -> None:
    """Add ``--from`` / ``--to`` / ``--preset`` arguments to a parser."""
    p.add_argument("--from", dest="from_date",
                    help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date",
                    help="End date (YYYY-MM-DD)")
    p.add_argument("--preset",
                    choices=("today", "yesterday", "week",
                              "month", "year", "all"),
                    help="Quick date-range preset")


# =============================================================================
# === Entry points                                                            ===
# =============================================================================

def run_command(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments and dispatch to the matching sub-command.

    Returns the Unix exit code (0/1/2).  Does not call ``sys.exit``
    so callers can reuse this from tests.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    # Configure logging level
    level = 10  # DEBUG
    if getattr(args, "debug", False):
        setup_logging(level=level, also_stderr=True, force=True)
    else:
        setup_logging(level=20, also_stderr=False)  # INFO
    # No sub-command given — print help and exit.
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return EXIT_OK
    try:
        return func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level CLI catch-all
        _log.exception("Unhandled CLI error: %s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Module entry point — used by ``python -m rask.cli``."""
    return run_command(argv)


if __name__ == "__main__":
    sys.exit(main())
