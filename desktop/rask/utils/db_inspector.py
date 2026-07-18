"""
rask.utils.db_inspector
=======================

Database inspection tool for the Rask SQLite DB.

Functions
---------

  • ``inspect()`` — return a dict with table list, row counts, schema,
    indexes
  • ``print_report()`` — pretty-print the inspection
  • ``find_orphans()`` — find activity rows with non-existent category_id
  • ``find_duplicates()`` — find duplicate activities (same title + date
    + duration)
  • ``stats_per_month()`` — activities per month for last 12 months
  • ``suggest_vacuum()`` — recommend vacuum if overhead > 20%

Example
-------

    >>> from rask.utils.db_inspector import inspect, print_report
    >>> report = inspect()
    >>> print_report(report)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from ..core.logging_utils import get_logger

__all__ = [
    "inspect",
    "print_report",
    "find_orphans",
    "find_duplicates",
    "stats_per_month",
    "suggest_vacuum",
]

_log = get_logger("utils.db_inspector")


# =============================================================================
# === Inspection                                                              ===
# =============================================================================

def inspect() -> Dict[str, Any]:
    """Return a comprehensive dict describing the current DB state.

    Returns
    -------
    dict
        Keys: ``tables`` (list of {name, rows, columns, indexes}),
        ``total_rows``, ``db_size_bytes``, ``schema_version``,
        ``integrity_ok``.
    """
    out: Dict[str, Any] = {
        "tables": [],
        "total_rows": 0,
        "db_size_bytes": 0,
        "schema_version": 1,
        "integrity_ok": True,
    }

    try:
        conn = db.get_conn()

        # Table list.
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [r["name"] for r in cur.fetchall()]

        for name in table_names:
            info: Dict[str, Any] = {"name": name, "rows": 0,
                                     "columns": [], "indexes": []}
            # Row count.
            try:
                rc = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
                info["rows"] = int(rc["c"]) if rc else 0
            except Exception:  # noqa: BLE001
                pass
            # Columns.
            try:
                cur2 = conn.execute(f"PRAGMA table_info({name})")
                info["columns"] = [
                    {"name": r["name"], "type": r["type"],
                     "notnull": bool(r["notnull"]),
                     "pk": bool(r["pk"])}
                    for r in cur2.fetchall()
                ]
            except Exception:  # noqa: BLE001
                pass
            # Indexes.
            try:
                cur3 = conn.execute(f"PRAGMA index_list({name})")
                info["indexes"] = [
                    {"name": r["name"], "unique": bool(r["unique"])}
                    for r in cur3.fetchall()
                ]
            except Exception:  # noqa: BLE001
                pass
            out["tables"].append(info)
            out["total_rows"] += info["rows"]

        # DB file size.
        try:
            out["db_size_bytes"] = db.db_file_size()
        except Exception:  # noqa: BLE001
            pass

        # Schema version.
        try:
            cur = conn.execute(
                "SELECT MAX(version) AS v FROM changelog"
            )
            row = cur.fetchone()
            if row and row["v"] is not None:
                out["schema_version"] = int(row["v"])
        except Exception:  # noqa: BLE001
            pass

        # Integrity check.
        try:
            result = db.integrity_check()
            out["integrity_ok"] = (result == ["ok"])
        except Exception:  # noqa: BLE001
            pass

    except Exception as exc:  # noqa: BLE001
        _log.error("inspect failed: %s", exc)
    return out


def print_report(report: Optional[Dict[str, Any]] = None) -> None:
    """Pretty-print an inspection report to stdout."""
    if report is None:
        report = inspect()

    print(f"=== Rask DB Report ===")
    print(f"Schema version: v{report.get('schema_version', '?')}")
    print(f"DB size: {report.get('db_size_bytes', 0):,} bytes")
    print(f"Total rows: {report.get('total_rows', 0):,}")
    print(f"Integrity: {'OK' if report.get('integrity_ok') else 'FAIL'}")
    print()
    print(f"{'Table':<25} {'Rows':>10}  {'Cols':>5}  {'Indexes':>8}")
    print("-" * 55)
    for t in report.get("tables", []):
        print(f"{t['name']:<25} {t['rows']:>10,}  "
              f"{len(t['columns']):>5}  {len(t['indexes']):>8}")
    print()


# =============================================================================
# === find_orphans                                                           ===
# =============================================================================

def find_orphans() -> List[Dict[str, Any]]:
    """Find activity rows with non-existent category_id.

    Returns a list of dicts: ``{activity_id, title, category_id}``.
    """
    orphans: List[Dict[str, Any]] = []
    try:
        conn = db.get_conn()
        cur = conn.execute(
            "SELECT a.id AS activity_id, a.title AS title, a.category_id AS cat "
            "FROM activities a "
            "LEFT JOIN categories c ON a.category_id = c.id "
            "WHERE a.category_id IS NOT NULL AND c.id IS NULL "
            "AND a.deleted_at IS NULL"
        )
        for r in cur.fetchall():
            orphans.append({
                "activity_id": r["activity_id"],
                "title": r["title"],
                "category_id": r["cat"],
            })
    except Exception as exc:  # noqa: BLE001
        _log.error("find_orphans failed: %s", exc)
    return orphans


# =============================================================================
# === find_duplicates                                                        ===
# =============================================================================

def find_duplicates() -> List[Dict[str, Any]]:
    """Find duplicate activities (same title + date + duration).

    Returns a list of dicts: ``{title, date_iso, duration_min, count,
    activity_ids}``.
    """
    dups: List[Dict[str, Any]] = []
    try:
        conn = db.get_conn()
        cur = conn.execute(
            "SELECT title, date_iso, duration_min, COUNT(*) AS cnt, "
            "GROUP_CONCAT(id) AS ids "
            "FROM activities "
            "WHERE deleted_at IS NULL "
            "GROUP BY title, date_iso, duration_min "
            "HAVING cnt > 1 "
            "ORDER BY cnt DESC"
        )
        for r in cur.fetchall():
            dups.append({
                "title": r["title"],
                "date_iso": r["date_iso"],
                "duration_min": r["duration_min"],
                "count": r["cnt"],
                "activity_ids": [int(x) for x in str(r["ids"]).split(",")],
            })
    except Exception as exc:  # noqa: BLE001
        _log.error("find_duplicates failed: %s", exc)
    return dups


# =============================================================================
# === stats_per_month                                                        ===
# =============================================================================

def stats_per_month(months: int = 12) -> List[Dict[str, Any]]:
    """Return activity counts per month for the last `months` months.

    Each entry: ``{month_iso, count, total_min}``.
    """
    out: List[Dict[str, Any]] = []
    try:
        today = date.today()
        for i in range(months):
            # Compute first-of-month and last-of-month for `i` months ago.
            year = today.year - (today.month - i - 1) // 12
            month = (today.month - i - 1) % 12 + 1
            if month == 12:
                next_first = date(year + 1, 1, 1)
            else:
                next_first = date(year, month + 1, 1)
            first = date(year, month, 1)
            last = next_first - timedelta(days=1)
            date_from = first.isoformat()
            date_to = last.isoformat()
            try:
                count = db.activity_count(date_from=date_from,
                                            date_to=date_to)
                total = db.activity_sum_duration(date_from=date_from,
                                                   date_to=date_to)
                out.append({
                    "month_iso": f"{year:04d}-{month:02d}",
                    "count": count,
                    "total_min": total,
                })
            except Exception:  # noqa: BLE001
                out.append({
                    "month_iso": f"{year:04d}-{month:02d}",
                    "count": 0,
                    "total_min": 0,
                })
        # Reverse to chronological order.
        out.reverse()
    except Exception as exc:  # noqa: BLE001
        _log.error("stats_per_month failed: %s", exc)
    return out


# =============================================================================
# === suggest_vacuum                                                         ===
# =============================================================================

def suggest_vacuum() -> Dict[str, Any]:
    """Recommend a VACUUM if overhead > 20%.

    Returns ``{should_vacuum, overhead_percent, db_size_bytes,
    freeable_bytes_estimate}``.
    """
    out: Dict[str, Any] = {
        "should_vacuum": False,
        "overhead_percent": 0.0,
        "db_size_bytes": 0,
        "freeable_bytes_estimate": 0,
    }
    try:
        conn = db.get_conn()
        # PRAGMA auto_vacuum tells us the auto-vacuum mode.
        # PRAGMA freelist_count tells us how many pages are free.
        cur = conn.execute("PRAGMA freelist_count")
        free_pages = int(cur.fetchone()[0]) if cur.fetchone() else 0
        # Page size.
        cur = conn.execute("PRAGMA page_size")
        page_size_row = cur.fetchone()
        page_size = int(page_size_row[0]) if page_size_row else 4096
        # Page count.
        cur = conn.execute("PRAGMA page_count")
        page_count_row = cur.fetchone()
        page_count = int(page_count_row[0]) if page_count_row else 0
        if page_count > 0:
            overhead = (free_pages / page_count) * 100
            out["overhead_percent"] = round(overhead, 2)
            out["db_size_bytes"] = page_count * page_size
            out["freeable_bytes_estimate"] = free_pages * page_size
            out["should_vacuum"] = overhead > 20.0
    except Exception as exc:  # noqa: BLE001
        _log.error("suggest_vacuum failed: %s", exc)
    return out


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.db_inspector``."""
    print_report()
    orphans = find_orphans()
    if orphans:
        print(f"\nOrphan activities (category_id pointing nowhere): "
              f"{len(orphans)}")
        for o in orphans[:10]:
            print(f"  id={o['activity_id']} title={o['title']!r} "
                  f"cat_id={o['category_id']}")
    dups = find_duplicates()
    if dups:
        print(f"\nDuplicate activities: {len(dups)} groups")
        for d in dups[:10]:
            print(f"  {d['title']!r} on {d['date_iso']} "
                  f"({d['duration_min']} min) × {d['count']}")
    print("\nMonthly stats (last 12 months):")
    for m in stats_per_month():
        print(f"  {m['month_iso']}: {m['count']} activities, "
              f"{m['total_min']} min")
    vac = suggest_vacuum()
    print(f"\nVacuum suggestion: {vac}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
