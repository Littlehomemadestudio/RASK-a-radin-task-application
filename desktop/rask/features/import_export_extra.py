"""
rask.features.import_export_extra
=================================

Extra import/export formats beyond the built-in CSV / JSON / PDF /
PNG.

Functions
---------

  • :func:`ImportFromCSV`        — import activities from a Toggl-style CSV
  • :func:`ImportFromJSON`       — import from another Rask JSON export
  • :func:`ImportFromWebPWA`     — import from the web PWA's IndexedDB export
  • :func:`ExportToMarkdown`     — daily log as Markdown
  • :func:`ExportToHTML`         — interactive HTML report
  • :func:`ExportToICal`         — iCal (.ics) for calendar apps

Each function returns::

    {success: bool, count: int, path: str, error: str | None}

CSV format (Toggl-compatible)::

    Description,Start time,End time,Duration,Tags,Project
    Reading,2025-01-01 09:00:00,2025-01-01 10:00:00,3600,books,Learn

iCal output is a standard VCALENDAR with one VEVENT per activity
(DTSTART/DTEND from ``start_ts``/``end_ts``, SUMMARY from title).
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, today_iso

__all__ = [
    "ImportFromCSV",
    "ImportFromJSON",
    "ImportFromWebPWA",
    "ExportToMarkdown",
    "ExportToHTML",
    "ExportToICal",
]

_log = get_logger("features.import_export_extra")


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _result(success: bool, count: int = 0, path: str = "",
             error: Optional[str] = None) -> Dict[str, Any]:
    return {"success": success, "count": count, "path": path, "error": error}


def _find_category_by_name(name: str) -> Optional[int]:
    """Look up a category by name (en/fa) or key.  Returns id or None."""
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    try:
        for c in db.category_list(include_archived=True):
            if (c.get("name_en", "").lower() == name.lower()
                    or c.get("name_fa", "") == name
                    or c.get("key", "").upper() == name.upper()):
                return int(c["id"])
    except Exception:  # noqa: BLE001
        pass
    return None


def _ensure_path_dir(path: str) -> bool:
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# =============================================================================
# === Importers                                                              ===
# =============================================================================

def ImportFromCSV(path: str) -> Dict[str, Any]:  # noqa: N802 (public API)
    """Import activities from a Toggl-style CSV file.

    Expected columns (case-insensitive):
        Description | Start time | End time | Duration | Tags | Project

    "Start time" / "End time" can be in any of these formats:
        2025-01-01 09:00:00
        2025-01-01T09:00:00
        2025-01-01 09:00 AM

    "Duration" is optional (computed from Start/End if missing).  If
    present, it's interpreted as seconds (Toggl format) unless it
    contains "h"/"m" (then parsed by ``parse_duration``).

    "Project" is matched against category names; if no match, the
    activity is left uncategorized.

    Returns ``{success, count, path, error}``.
    """
    if not path or not os.path.exists(path):
        return _result(False, error=f"File not found: {path}")
    if not _ensure_path_dir(path):
        return _result(False, error="Cannot access path")

    count = 0
    errors: List[str] = []
    try:
        # Read with UTF-8 BOM tolerance.
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return _result(False, error="Empty CSV file")
            # Normalize field names to lowercase.
            reader.fieldnames = [n.strip().lower() if n else "" for n in reader.fieldnames]
            for i, row in enumerate(reader, start=2):  # 1=header, 2=first row
                try:
                    title = (row.get("description")
                              or row.get("title")
                              or row.get("name")
                              or "").strip()
                    if not title:
                        continue
                    start = (row.get("start time")
                              or row.get("start")
                              or row.get("start_ts")
                              or "").strip()
                    end = (row.get("end time")
                            or row.get("end")
                            or row.get("end_ts")
                            or "").strip()
                    duration_raw = (row.get("duration")
                                     or row.get("duration_min")
                                     or "").strip()
                    tags_raw = (row.get("tags") or "").strip()
                    project = (row.get("project")
                                or row.get("category")
                                or "").strip()

                    # Parse start/end.
                    start_dt = _parse_csv_datetime(start)
                    end_dt = _parse_csv_datetime(end) if end else None

                    # Compute duration.
                    duration_min = 0
                    if duration_raw:
                        duration_min = _parse_duration_field(duration_raw)
                    if duration_min == 0 and start_dt and end_dt:
                        delta = (end_dt - start_dt).total_seconds()
                        duration_min = max(0, int(delta // 60))
                    if duration_min <= 0:
                        # Skip rows with no duration info.
                        continue

                    date_iso = (start_dt.date().isoformat() if start_dt
                                 else today_iso())
                    # Category lookup
                    cat_id = _find_category_by_name(project)
                    # Tags
                    tags = [t.strip() for t in tags_raw.split(";") if t.strip()]
                    if not tags:
                        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

                    db.activity_add(
                        title=title,
                        category_id=cat_id,
                        duration_min=duration_min,
                        date_iso=date_iso,
                        start_ts=start_dt.isoformat() if start_dt else None,
                        end_ts=end_dt.isoformat() if end_dt else None,
                        tags=tags,
                        kind="manual",
                        source="import",
                    )
                    count += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Row {i}: {exc}")
                    continue
        bus.publish("data.imported", {"source": "csv", "count": count})
        _log.info("CSV import: %d activities from %s", count, path)
        error = "; ".join(errors[:3]) if errors else None
        return _result(True, count=count, path=path, error=error)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


def _parse_csv_datetime(s: str) -> Optional[datetime]:
    """Parse a CSV date/time field.  Returns None on failure."""
    if not s:
        return None
    s = s.strip()
    # Try common formats.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p",
                "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_duration_field(s: str) -> int:
    """Parse a duration field (seconds if pure int, else parse_duration)."""
    if not s:
        return 0
    s = s.strip()
    # Pure int → seconds (Toggl style)
    try:
        n = int(s)
        return max(0, n // 60)
    except ValueError:
        pass
    # HH:MM:SS
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return 0
        if len(nums) == 3:
            return max(0, nums[0] * 60 + nums[1] + (1 if nums[2] >= 30 else 0))
        if len(nums) == 2:
            return max(0, nums[0] + (1 if nums[1] >= 30 else 0))
    # 1h 30m
    from ..core.time_utils import parse_duration
    return parse_duration(s)


def ImportFromJSON(path: str) -> Dict[str, Any]:  # noqa: N802
    """Import from another Rask JSON export.

    Expects the schema produced by ``rask.database.export_to_dict``.
    """
    if not path or not os.path.exists(path):
        return _result(False, error=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "data" not in data:
            return _result(False, error="Not a Rask JSON export (missing 'data' key)")
        count = sum(len(rows) for rows in data["data"].values())
        db.import_from_dict(data, replace=False)
        bus.publish("data.imported", {"source": "json", "count": count})
        _log.info("JSON import: %d rows from %s", count, path)
        return _result(True, count=count, path=path)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


def ImportFromWebPWA(path: str) -> Dict[str, Any]:  # noqa: N802
    """Import from the web PWA's IndexedDB export.

    The web PWA exports a JSON file with an ``activities`` array (each
    activity has fields like ``title``, ``duration`` (in seconds),
    ``category`` (key string), ``date``, ``tags``, etc.).
    """
    if not path or not os.path.exists(path):
        return _result(False, error=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # The web export can be either {activities: [...]} or
        # {stores: {activities: [...]}}.
        activities: List[Dict[str, Any]] = []
        if isinstance(data, list):
            activities = data
        elif isinstance(data, dict):
            if "activities" in data:
                activities = data["activities"]
            elif "stores" in data and isinstance(data["stores"], dict):
                activities = data["stores"].get("activities", [])
            else:
                # Maybe it's {data: {activities: [...]}} (Rask desktop format).
                inner = data.get("data", {})
                if isinstance(inner, dict) and "activities" in inner:
                    activities = inner["activities"]
        count = 0
        for a in activities:
            try:
                title = (a.get("title") or "").strip()
                if not title:
                    continue
                duration_min = 0
                if "duration_min" in a:
                    duration_min = int(a["duration_min"])
                elif "duration" in a:
                    # Web PWA stores duration in seconds.
                    duration_min = int(a["duration"]) // 60
                if duration_min <= 0:
                    continue
                date_iso = a.get("date_iso") or a.get("date") or today_iso()
                # Web PWA category is stored as a key string.
                cat_id = None
                cat_key = a.get("category") or a.get("category_key")
                if cat_key:
                    cat = db.category_get_by_key(cat_key)
                    if cat:
                        cat_id = int(cat["id"])
                else:
                    cat_name = a.get("category_name") or ""
                    if cat_name:
                        cat_id = _find_category_by_name(cat_name)
                tags = a.get("tags") or []
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:  # noqa: BLE001
                        tags = [t.strip() for t in tags.split(",")]
                db.activity_add(
                    title=title,
                    category_id=cat_id,
                    duration_min=duration_min,
                    date_iso=date_iso[:10],
                    start_ts=a.get("start_ts") or a.get("started_at"),
                    end_ts=a.get("end_ts") or a.get("ended_at"),
                    tags=tags,
                    notes=a.get("notes"),
                    kind="manual",
                    source="import",
                )
                count += 1
            except Exception as exc:  # noqa: BLE001
                _log.debug("WebPWA import row skipped: %s", exc)
                continue
        bus.publish("data.imported", {"source": "web_pwa", "count": count})
        _log.info("WebPWA import: %d activities from %s", count, path)
        return _result(True, count=count, path=path)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


# =============================================================================
# === Exporters                                                              ===
# =============================================================================

def ExportToMarkdown(path: str,  # noqa: N802
                     date_from: Optional[str] = None,
                     date_to: Optional[str] = None) -> Dict[str, Any]:
    """Export activities as a Markdown daily log.

    The output is grouped by date, with each day's activities listed
    under a ``## YYYY-MM-DD`` heading.
    """
    if not _ensure_path_dir(path):
        return _result(False, error="Cannot write to path")
    if date_from is None:
        date_from = add_days(today_iso(), -29)
    if date_to is None:
        date_to = today_iso()
    try:
        activities = db.activity_list(date_from=date_from, date_to=date_to,
                                       limit=10000, order_by="date_iso ASC, id ASC")
        cats = {int(c["id"]): c for c in db.category_list()}
        # Group by date.
        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for a in activities:
            by_date.setdefault(a["date_iso"], []).append(a)
        lines: List[str] = []
        lines.append("# گزارش فعالیت‌های رَسک")
        lines.append("")
        lines.append(f"**بازه:** {_fa_date_range(date_from, date_to)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        # Walk in reverse-chronological order (most recent first).
        for d in sorted(by_date.keys(), reverse=True):
            lines.append(f"## {_fa_date(d)}")
            lines.append("")
            day_total = sum(int(a.get("duration_min") or 0) for a in by_date[d])
            lines.append(f"**مجموع روز:** {_fa_minutes(day_total)}")
            lines.append("")
            lines.append("| عنوان | دسته | مدت | تگ‌ها |")
            lines.append("|-------|-------|------|-------|")
            for a in by_date[d]:
                title = a.get("title", "")
                cat_id = a.get("category_id")
                cat = cats.get(int(cat_id), {}) if cat_id else {}
                cat_name = cat.get("name_fa") or cat.get("name_en") or "—"
                dur = _fa_minutes(int(a.get("duration_min") or 0))
                try:
                    tags = json.loads(a.get("tags_json") or "[]")
                except Exception:  # noqa: BLE001
                    tags = []
                tags_str = "، ".join(tags) if tags else "—"
                lines.append(f"| {title} | {cat_name} | {dur} | {tags_str} |")
            lines.append("")
        out = "\n".join(lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        bus.publish("export.completed", {"format": "markdown",
                                           "count": len(activities),
                                           "path": path})
        _log.info("Markdown export: %d activities -> %s",
                  len(activities), path)
        return _result(True, count=len(activities), path=path)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


def ExportToHTML(path: str,  # noqa: N802
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None) -> Dict[str, Any]:
    """Export an interactive HTML report (charts + tables)."""
    if not _ensure_path_dir(path):
        return _result(False, error="Cannot write to path")
    if date_from is None:
        date_from = add_days(today_iso(), -29)
    if date_to is None:
        date_to = today_iso()
    try:
        activities = db.activity_list(date_from=date_from, date_to=date_to,
                                       limit=10000, order_by="date_iso DESC, id DESC")
        cats = {int(c["id"]): c for c in db.category_list()}
        # Aggregates
        total_min = sum(int(a.get("duration_min") or 0) for a in activities)
        # By category
        by_cat: Dict[int, int] = {}
        for a in activities:
            cid = int(a.get("category_id") or 0)
            by_cat[cid] = by_cat.get(cid, 0) + int(a.get("duration_min") or 0)
        # Build rows HTML.
        rows_html: List[str] = []
        for a in activities:
            title = a.get("title", "")
            cat_id = a.get("category_id")
            cat = cats.get(int(cat_id), {}) if cat_id else {}
            cat_name = cat.get("name_fa") or cat.get("name_en") or "—"
            cat_color = cat.get("color") or "#9A9A9F"
            dur = int(a.get("duration_min") or 0)
            try:
                tags = json.loads(a.get("tags_json") or "[]")
            except Exception:  # noqa: BLE001
                tags = []
            tags_html = "".join(
                f"<span style='background:{cat_color}22;color:{cat_color};"
                f"padding:2px 6px;border-radius:4px;margin:0 2px;'>{t}</span>"
                for t in tags
            )
            rows_html.append(
                f"<tr><td>{a.get('date_iso','')}</td><td>{title}</td>"
                f"<td><span style='color:{cat_color}'>●</span> {cat_name}</td>"
                f"<td style='text-align:left'>{i18n.to_fa_digits(dur)}</td>"
                f"<td>{tags_html}</td></tr>"
            )
        # Build category bar chart HTML.
        cat_bars: List[str] = []
        max_min = max(by_cat.values()) if by_cat else 1
        for cid, minutes in sorted(by_cat.items(),
                                     key=lambda x: x[1], reverse=True):
            cat = cats.get(cid, {})
            name = cat.get("name_fa") or cat.get("name_en") or "—"
            color = cat.get("color") or "#9A9A9F"
            pct = int(minutes / max_min * 100) if max_min else 0
            cat_bars.append(
                f"<div style='margin:8px 0'>"
                f"<div style='color:#9A9A9F;font-size:12px'>{name} — "
                f"{i18n.to_fa_digits(minutes)} دقیقه</div>"
                f"<div style='background:#1A1A1D;border-radius:4px;height:8px;'>"
                f"<div style='background:{color};width:{pct}%;height:8px;"
                f"border-radius:4px;'></div></div></div>"
            )
        html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head><meta charset="utf-8"><title>گزارش رَسک</title>
<style>
body {{ font-family: 'Vazirmatn', Tahoma, sans-serif;
        background: #0E0E10; color: #E8E8E8; padding: 24px;
        max-width: 900px; margin: 0 auto; }}
h1 {{ color: #D4AF37; border-bottom: 1px solid #2C2C30;
      padding-bottom: 12px; }}
h2 {{ color: #C9A84C; margin-top: 32px; }}
.stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.stat {{ background: #1A1A1D; padding: 16px 24px; border-radius: 12px;
          min-width: 120px; }}
.stat .label {{ color: #9A9A9F; font-size: 12px; }}
.stat .value {{ color: #D4AF37; font-size: 24px; font-weight: bold; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
th, td {{ padding: 8px 12px; text-align: right;
           border-bottom: 1px solid #2C2C30; }}
th {{ color: #C9A84C; font-weight: bold; font-size: 12px; }}
.footer {{ color: #5C5C60; font-size: 11px; margin-top: 32px;
            border-top: 1px solid #2C2C30; padding-top: 12px;
            text-align: center; }}
</style></head>
<body>
<h1>📊 گزارش فعالیت‌های رَسک</h1>
<p style="color:#9A9A9F">بازه: {i18n.to_fa_digits(date_from)} تا {i18n.to_fa_digits(date_to)}</p>

<div class="stats">
<div class="stat"><div class="label">تعداد فعالیت</div>
    <div class="value">{i18n.to_fa_digits(len(activities))}</div></div>
<div class="stat"><div class="label">مجموع زمان</div>
    <div class="value">{i18n.to_fa_digits(total_min // 60)} ساعت</div></div>
<div class="stat"><div class="label">دسته‌های فعال</div>
    <div class="value">{i18n.to_fa_digits(len(by_cat))}</div></div>
</div>

<h2>دسته‌ها</h2>
{"".join(cat_bars)}

<h2>فعالیت‌ها</h2>
<table>
<thead><tr><th>تاریخ</th><th>عنوان</th><th>دسته</th><th>دقیقه</th><th>تگ‌ها</th></tr></thead>
<tbody>
{"".join(rows_html)}
</tbody>
</table>

<div class="footer">رَسک — زمان، ظریف.</div>
</body></html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        bus.publish("export.completed", {"format": "html",
                                           "count": len(activities),
                                           "path": path})
        _log.info("HTML export: %d activities -> %s", len(activities), path)
        return _result(True, count=len(activities), path=path)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


def ExportToICal(path: str,  # noqa: N802
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None) -> Dict[str, Any]:
    """Export activities as an iCal (.ics) calendar file.

    Each activity becomes a VEVENT with DTSTART/DTEND derived from
    ``start_ts``/``end_ts``.  Activities without ``start_ts`` are
    skipped (they can't be placed on a calendar).
    """
    if not _ensure_path_dir(path):
        return _result(False, error="Cannot write to path")
    if date_from is None:
        date_from = add_days(today_iso(), -29)
    if date_to is None:
        date_to = today_iso()
    try:
        activities = db.activity_list(date_from=date_from, date_to=date_to,
                                       limit=10000)
        cats = {int(c["id"]): c for c in db.category_list()}
        lines: List[str] = []
        lines.append("BEGIN:VCALENDAR")
        lines.append("VERSION:2.0")
        lines.append("PRODID:-//Rask//Desktop//EN")
        lines.append("CALSCALE:GREGORIAN")
        lines.append("METHOD:PUBLISH")
        count = 0
        for a in activities:
            start_ts = a.get("start_ts")
            end_ts = a.get("end_ts")
            if not start_ts:
                # If we only have a date, treat it as an all-day event.
                d = a.get("date_iso")
                if not d:
                    continue
                try:
                    d_obj = date.fromisoformat(d[:10])
                except Exception:  # noqa: BLE001
                    continue
                lines.append("BEGIN:VEVENT")
                lines.append(f"UID:rask-activity-{a['id']}@rask.app")
                lines.append(f"DTSTART;VALUE=DATE:{d_obj.strftime('%Y%m%d')}")
                # All-day event: end is the day after.
                next_day = d_obj + timedelta(days=1)
                lines.append(f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}")
                lines.append(f"SUMMARY:{_ical_escape(a.get('title', ''))}")
                dur = a.get("duration_min", 0)
                lines.append(f"DESCRIPTION:Duration: {dur} minutes")
                lines.append("END:VEVENT")
                count += 1
                continue
            # Parse start/end.
            start_dt = _parse_iso_for_ical(start_ts)
            end_dt = _parse_iso_for_ical(end_ts) if end_ts else None
            if start_dt is None:
                continue
            if end_dt is None:
                # Use duration.
                dur_min = int(a.get("duration_min") or 0)
                end_dt = start_dt + timedelta(minutes=dur_min)
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:rask-activity-{a['id']}@rask.app")
            lines.append(f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}")
            lines.append(f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}")
            lines.append(f"SUMMARY:{_ical_escape(a.get('title', ''))}")
            cat_id = a.get("category_id")
            if cat_id:
                cat = cats.get(int(cat_id), {})
                cat_name = cat.get("name_en") or cat.get("name_fa")
                if cat_name:
                    lines.append(f"CATEGORIES:{_ical_escape(cat_name)}")
            if a.get("notes"):
                lines.append(f"DESCRIPTION:{_ical_escape(a['notes'])}")
            lines.append("END:VEVENT")
            count += 1
        lines.append("END:VCALENDAR")
        out = "\r\n".join(lines) + "\r\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        bus.publish("export.completed", {"format": "ical",
                                           "count": count,
                                           "path": path})
        _log.info("iCal export: %d events -> %s", count, path)
        return _result(True, count=count, path=path)
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {"path": path})
        return _result(False, error=str(exc))


def _ical_escape(s: str) -> str:
    """Escape a string for iCal (RFC 5545)."""
    if not s:
        return ""
    return (s.replace("\\", "\\\\")
             .replace(";", "\\;")
             .replace(",", "\\,")
             .replace("\n", "\\n"))


def _parse_iso_for_ical(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


# =============================================================================
# === Persian-formatting helpers                                             ===
# =============================================================================

def _fa_date(s: str) -> str:
    """Format an ISO date as 'DayName، DD Month YYYY' in Persian."""
    try:
        d = date.fromisoformat(s[:10])
    except Exception:  # noqa: BLE001
        return i18n.to_fa_digits(s)
    months = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
              "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]
    weekdays = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
                "جمعه", "شنبه", "یکشنبه"]
    return f"{weekdays[d.weekday()]}, {i18n.to_fa_digits(d.day)} {months[d.month - 1]} {i18n.to_fa_digits(d.year)}"


def _fa_date_range(d1: str, d2: str) -> str:
    return f"{_fa_date(d1)} — {_fa_date(d2)}"


def _fa_minutes(m: int) -> str:
    m = max(0, int(m))
    h = m // 60
    mm = m % 60
    if h and mm:
        return f"{i18n.to_fa_digits(h)}س {i18n.to_fa_digits(mm)}د"
    if h:
        return f"{i18n.to_fa_digits(h)} ساعت"
    return f"{i18n.to_fa_digits(mm)} دقیقه"


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== import_export_extra self-tests ===")
    try:
        # CSV round-trip.
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                          delete=False, encoding="utf-8") as f:
            f.write("Description,Start time,End time,Duration,Tags,Project\n")
            f.write("Test activity,2025-01-01 09:00:00,2025-01-01 10:00:00,3600,books,Learn\n")
            csv_path = f.name
        r = ImportFromCSV(csv_path)
        assert r["success"], f"CSV import failed: {r['error']}"
        assert r["count"] >= 1, f"expected >=1, got {r['count']}"
        # Markdown export
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                          delete=False, encoding="utf-8") as f:
            md_path = f.name
        r = ExportToMarkdown(md_path, date_from="2025-01-01", date_to="2025-01-31")
        assert r["success"]
        # iCal export
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ics",
                                          delete=False, encoding="utf-8") as f:
            ics_path = f.name
        r = ExportToICal(ics_path, date_from="2025-01-01", date_to="2025-01-31")
        assert r["success"]
        # HTML export
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html",
                                          delete=False, encoding="utf-8") as f:
            html_path = f.name
        r = ExportToHTML(html_path, date_from="2025-01-01", date_to="2025-01-31")
        assert r["success"]
        # Cleanup
        for p in (csv_path, md_path, ics_path, html_path):
            try:
                os.unlink(p)
            except Exception:  # noqa: BLE001
                pass
        print("  OK   CSV import + Markdown/iCal/HTML exports")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
