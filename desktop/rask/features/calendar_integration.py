"""
rask.features.calendar_integration
==================================

Calendar views and helpers built on top of the activity database.

The service exposes three primary views:

  • ``month_view(year, month, calendar_system)`` — a 5-6 week grid for
    a single month, in either Jalali or Gregorian calendar system.
  • ``week_view(week_iso)``                       — 7-day detail
  • ``day_view(date_iso)``                        — single-day timeline

Plus utility methods:

  • ``find_free_time(date_iso, duration_min)``    — gaps in the day
    that are at least `duration_min` minutes long.
  • ``busiest_day(date_from, date_to)``           — day with the most
    total minutes.
  • ``quietest_day(date_from, date_to)``          — day with the least
    non-zero minutes (returns ``None`` if all days are empty).

Persian calendar support uses :mod:`rask.core.jalali`.

No schema changes — uses the existing ``activities`` table.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.jalali import gregorian_to_jalali, jalali_to_gregorian, iso_to_jalali
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    end_of_week,
    range_days,
    start_of_week,
    today_iso,
)

__all__ = [
    "CalendarService",
    "calendar_service",
]

_log = get_logger("features.calendar")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

#: Persian weekday names (Sat-first).
WEEKDAYS_FA: List[str] = [
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه",
    "چهارشنبه", "پنجشنبه", "جمعه",
]
WEEKDAYS_EN: List[str] = [
    "Saturday", "Sunday", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday",
]

#: Persian month names (Jalali).
JALALI_MONTHS_FA: List[str] = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

#: Gregorian month names in Persian.
GREGORIAN_MONTHS_FA: List[str] = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]

GREGORIAN_MONTHS_EN: List[str] = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _fa(value: Any) -> str:
    return i18n.to_fa_digits(value)


def _gregorian_to_jalali_date(d: date) -> Tuple[int, int, int]:
    """Return (jy, jm, jd) for a Gregorian date."""
    return gregorian_to_jalali(d.year, d.month, d.day)


def _jalali_to_gregorian_date(jy: int, jm: int, jd: int) -> date:
    y, m, d = jalali_to_gregorian(jy, jm, jd)
    return date(y, m, d)


def _weekday_index_sat_first(d: date) -> int:
    """Return 0=Sat..6=Fri for a Gregorian date."""
    py_wday = d.weekday()  # Mon=0..Sun=6
    mapping = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}
    return mapping[py_wday]


def _is_today(iso: str) -> bool:
    return iso == today_iso()


# =============================================================================
# === CalendarService                                                        ===
# =============================================================================

class CalendarService:
    """Calendar views over activity data."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Month view
    # ------------------------------------------------------------------

    def month_view(self, year: int, month: int,
                    calendar_system: str = "jalali") -> Dict[str, Any]:
        """Return a 5-6 week grid for the given month.

        Returns::

            {
                "year": int,
                "month": int,
                "month_name": str,
                "calendar_system": str,
                "weeks": [
                    [
                        {
                            "date_iso": str (Gregorian),
                            "day": int,
                            "in_month": bool,
                            "is_today": bool,
                            "total_min": int,
                            "activity_count": int,
                            "level": int (0..4),
                        }, ...
                    ], ...
                ],
            }
        """
        with self._lock:
            if calendar_system == "jalali":
                return self._month_view_jalali(year, month)
            return self._month_view_gregorian(year, month)

    def _month_view_gregorian(self, year: int, month: int) -> Dict[str, Any]:
        try:
            first_of_month = date(year, month, 1)
        except ValueError as exc:
            raise ValueError(f"Invalid year/month: {year}/{month}") from exc
        # Find the Saturday on or before the 1st.
        first_weekday = _weekday_index_sat_first(first_of_month)
        grid_start = first_of_month - timedelta(days=first_weekday)
        # Find the last day of the month.
        if month == 12:
            last_of_month = date(year, 12, 31)
        else:
            last_of_month = date(year, month + 1, 1) - timedelta(days=1)
        last_weekday = _weekday_index_sat_first(last_of_month)
        grid_end = last_of_month + timedelta(days=(6 - last_weekday))
        # Fetch aggregates for the date range.
        by_day = self._day_aggregates(grid_start.isoformat(),
                                       grid_end.isoformat())
        # Build weeks.
        weeks: List[List[Dict[str, Any]]] = []
        cursor = grid_start
        while cursor <= grid_end:
            week: List[Dict[str, Any]] = []
            for _ in range(7):
                iso = cursor.isoformat()
                agg = by_day.get(iso, {"total_min": 0, "count": 0})
                week.append({
                    "date_iso": iso,
                    "day": cursor.day,
                    "in_month": cursor.month == month,
                    "is_today": _is_today(iso),
                    "total_min": agg["total_min"],
                    "activity_count": agg["count"],
                    "level": self._level_for(agg["total_min"]),
                })
                cursor += timedelta(days=1)
            weeks.append(week)
        return {
            "year": year,
            "month": month,
            "month_name": (GREGORIAN_MONTHS_EN[month - 1]
                            if i18n.get_language() == "en"
                            else GREGORIAN_MONTHS_FA[month - 1]),
            "calendar_system": "gregorian",
            "weeks": weeks,
        }

    def _month_view_jalali(self, jy: int, jm: int) -> Dict[str, Any]:
        # Convert (jy, jm, 1) to Gregorian.
        g_start = _jalali_to_gregorian_date(jy, jm, 1)
        # Find the last day of the Jalali month.
        # Jalali months 1-6 have 31 days, 7-11 have 30 days, 12 has 29/30.
        if jm <= 6:
            last_day = 31
        elif jm <= 11:
            last_day = 30
        else:
            # Esfand: 30 in leap years, 29 otherwise.
            # Approximation: assume 30 (safer to over-render).
            last_day = 30  # Will be filtered by in_month flag.
        try:
            g_end = _jalali_to_gregorian_date(jy, jm, last_day)
        except Exception:  # noqa: BLE001
            # Fallback: 29 days
            g_end = _jalali_to_gregorian_date(jy, jm, 29)
        # Compute grid (Sat-start) from g_start.
        first_weekday = _weekday_index_sat_first(g_start)
        grid_start = g_start - timedelta(days=first_weekday)
        last_weekday = _weekday_index_sat_first(g_end)
        grid_end = g_end + timedelta(days=(6 - last_weekday))
        by_day = self._day_aggregates(grid_start.isoformat(),
                                       grid_end.isoformat())
        weeks: List[List[Dict[str, Any]]] = []
        cursor = grid_start
        while cursor <= grid_end:
            week: List[Dict[str, Any]] = []
            for _ in range(7):
                iso = cursor.isoformat()
                # Compute Jalali day/month to know if cursor is in jm.
                _, cj_m, cj_d = _gregorian_to_jalali_date(cursor)
                agg = by_day.get(iso, {"total_min": 0, "count": 0})
                week.append({
                    "date_iso": iso,
                    "day": cj_d,
                    "jalali_month": cj_m,
                    "in_month": cj_m == jm,
                    "is_today": _is_today(iso),
                    "total_min": agg["total_min"],
                    "activity_count": agg["count"],
                    "level": self._level_for(agg["total_min"]),
                })
                cursor += timedelta(days=1)
            weeks.append(week)
        return {
            "year": jy,
            "month": jm,
            "month_name": JALALI_MONTHS_FA[jm - 1],
            "calendar_system": "jalali",
            "weeks": weeks,
        }

    # ------------------------------------------------------------------
    # Week view
    # ------------------------------------------------------------------

    def week_view(self, week_iso: Optional[str] = None) -> Dict[str, Any]:
        """Return a 7-day detail for the week containing `week_iso`.

        Each day contains the full list of activities (capped at 50).
        """
        anchor = week_iso or today_iso()
        start = start_of_week(anchor, first_day=6)
        end = end_of_week(anchor, first_day=6)
        days: List[Dict[str, Any]] = []
        for d in range_days(start, end):
            activities = db.activity_list(date_from=d, date_to=d, limit=50)
            cats = {int(c["id"]): c for c in db.category_list()}
            total = sum(int(a.get("duration_min") or 0) for a in activities)
            # Color = top category color.
            cat_totals: Dict[int, int] = {}
            for a in activities:
                cid = int(a.get("category_id") or 0)
                cat_totals[cid] = cat_totals.get(cid, 0) + int(a.get("duration_min") or 0)
            top_cid = (max(cat_totals, key=lambda k: cat_totals[k])
                        if cat_totals else None)
            color = (cats.get(top_cid, {}).get("color")
                      if top_cid else "#9A9A9F")
            d_obj = date.fromisoformat(d)
            days.append({
                "date_iso": d,
                "weekday_index": _weekday_index_sat_first(d_obj),
                "weekday_name_fa": WEEKDAYS_FA[_weekday_index_sat_first(d_obj)],
                "weekday_name_en": WEEKDAYS_EN[_weekday_index_sat_first(d_obj)],
                "activities": activities,
                "total_min": total,
                "activity_count": len(activities),
                "color": color,
                "is_today": _is_today(d),
            })
        return {
            "week_start": start,
            "week_end": end,
            "days": days,
            "week_total_min": sum(d["total_min"] for d in days),
        }

    # ------------------------------------------------------------------
    # Day view
    # ------------------------------------------------------------------

    def day_view(self, date_iso: str) -> Dict[str, Any]:
        """Return a single-day detail with a per-hour timeline."""
        date_iso = date_iso[:10]
        activities = db.activity_list(date_from=date_iso, date_to=date_iso,
                                       limit=1000)
        cats = {int(c["id"]): c for c in db.category_list()}
        total = sum(int(a.get("duration_min") or 0) for a in activities)
        # By category breakdown.
        by_cat: Dict[int, int] = {}
        for a in activities:
            cid = int(a.get("category_id") or 0)
            by_cat[cid] = by_cat.get(cid, 0) + int(a.get("duration_min") or 0)
        by_category = [
            {
                "category_id": cid,
                "category_name": (cats.get(cid, {}).get("name_fa")
                                   or cats.get(cid, {}).get("name_en")
                                   or "—"),
                "category_color": cats.get(cid, {}).get("color") or "#9A9A9F",
                "total_min": minutes,
            }
            for cid, minutes in sorted(by_cat.items(),
                                         key=lambda x: x[1], reverse=True)
        ]
        # Timeline: list of {hour: 0..23, minutes_in_hour, activity_count}.
        timeline: List[Dict[str, Any]] = []
        hour_to_min: Dict[int, int] = {}
        hour_to_count: Dict[int, int] = {}
        for a in activities:
            start_ts = a.get("start_ts")
            if not start_ts:
                continue
            try:
                dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                h = dt.hour
            except Exception:  # noqa: BLE001
                continue
            hour_to_min[h] = hour_to_min.get(h, 0) + int(a.get("duration_min") or 0)
            hour_to_count[h] = hour_to_count.get(h, 0) + 1
        for h in range(24):
            timeline.append({
                "hour": h,
                "hour_label_fa": _fa(f"{h:02d}:00"),
                "minutes_in_hour": hour_to_min.get(h, 0),
                "activity_count": hour_to_count.get(h, 0),
            })
        return {
            "date_iso": date_iso,
            "is_today": _is_today(date_iso),
            "activities": activities,
            "total_min": total,
            "activity_count": len(activities),
            "by_category": by_category,
            "timeline": timeline,
        }

    # ------------------------------------------------------------------
    # Free-time finder
    # ------------------------------------------------------------------

    def find_free_time(self, date_iso: str,
                       duration_min: int = 30) -> List[Dict[str, Any]]:
        """Find gaps in the day at least `duration_min` minutes long.

        Returns a list of ``{start_hhmm, end_hhmm, duration_min}`` dicts.
        Only considers hours 6:00–23:00 as "available" (sleep hours
        excluded).
        """
        date_iso = date_iso[:10]
        try:
            activities = db.activity_list(date_from=date_iso, date_to=date_iso,
                                           limit=1000)
        except Exception:  # noqa: BLE001
            activities = []
        # Build busy intervals from start_ts/end_ts (or skip if missing).
        busy: List[Tuple[int, int]] = []  # (start_min, end_min) in minutes from 00:00
        for a in activities:
            start_ts = a.get("start_ts")
            end_ts = a.get("end_ts")
            if not start_ts or not end_ts:
                continue
            try:
                s = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                e = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                # Only consider if same date.
                if s.date().isoformat() != date_iso:
                    continue
                sm = s.hour * 60 + s.minute
                em = e.hour * 60 + e.minute
                if em > sm:
                    busy.append((sm, em))
            except Exception:  # noqa: BLE001
                continue
        # Merge overlapping busy intervals.
        busy.sort()
        merged: List[Tuple[int, int]] = []
        for s, e in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        # Walk the day from 06:00 to 23:00 and find gaps.
        day_start = 6 * 60   # 06:00
        day_end = 23 * 60    # 23:00
        out: List[Dict[str, Any]] = []
        cursor = day_start
        for bs, be in merged:
            if be <= day_start:
                continue
            if bs >= day_end:
                break
            # Clamp.
            bs_clamped = max(bs, day_start)
            be_clamped = min(be, day_end)
            # Gap before this busy interval.
            if cursor < bs_clamped:
                gap = bs_clamped - cursor
                if gap >= duration_min:
                    out.append(self._make_free_slot(cursor, bs_clamped))
            cursor = max(cursor, be_clamped)
        # Final gap.
        if cursor < day_end and (day_end - cursor) >= duration_min:
            out.append(self._make_free_slot(cursor, day_end))
        return out

    def _make_free_slot(self, start_min: int, end_min: int) -> Dict[str, Any]:
        return {
            "start_hhmm": f"{start_min // 60:02d}:{start_min % 60:02d}",
            "end_hhmm": f"{end_min // 60:02d}:{end_min % 60:02d}",
            "duration_min": end_min - start_min,
            "duration_label_fa": (
                f"{_fa(end_min - start_min)} دقیقه"),
        }

    # ------------------------------------------------------------------
    # Busiest / quietest
    # ------------------------------------------------------------------

    def busiest_day(self, date_from: Optional[str] = None,
                    date_to: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the day with the most total activity minutes.

        Returns ``None`` if no activities in the range.
        """
        by_day = db.activity_group_by_day(date_from=date_from, date_to=date_to)
        if not by_day:
            return None
        top = max(by_day, key=lambda r: int(r.get("total_min") or 0))
        if int(top.get("total_min") or 0) == 0:
            return None
        return {
            "date_iso": top["date_iso"],
            "total_min": int(top["total_min"]),
            "count": int(top["count"]),
        }

    def quietest_day(self, date_from: Optional[str] = None,
                     date_to: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the day with the least non-zero activity minutes.

        Returns ``None`` if no activities in the range.
        """
        by_day = db.activity_group_by_day(date_from=date_from, date_to=date_to)
        # Filter out zero-min days.
        non_zero = [r for r in by_day if int(r.get("total_min") or 0) > 0]
        if not non_zero:
            return None
        bot = min(non_zero, key=lambda r: int(r["total_min"]))
        return {
            "date_iso": bot["date_iso"],
            "total_min": int(bot["total_min"]),
            "count": int(bot["count"]),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _day_aggregates(self, date_from: str,
                         date_to: str) -> Dict[str, Dict[str, int]]:
        try:
            by_day = db.activity_group_by_day(date_from=date_from,
                                               date_to=date_to)
            return {r["date_iso"]: {
                "total_min": int(r["total_min"] or 0),
                "count": int(r["count"] or 0),
            } for r in by_day}
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return {}

    def _level_for(self, minutes: int) -> int:
        """Heatmap intensity level 0..4 for a given minutes count."""
        if minutes <= 0:
            return 0
        if minutes < 30:
            return 1
        if minutes < 90:
            return 2
        if minutes < 180:
            return 3
        return 4


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

calendar_service: CalendarService = CalendarService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== calendar_integration self-tests ===")
    try:
        mv = calendar_service.month_view(2025, 1, "gregorian")
        assert "weeks" in mv and len(mv["weeks"]) >= 4
        wv = calendar_service.week_view()
        assert "days" in wv and len(wv["days"]) == 7
        dv = calendar_service.day_view(today_iso())
        assert "timeline" in dv and len(dv["timeline"]) == 24
        free = calendar_service.find_free_time(today_iso(), 30)
        assert isinstance(free, list)
        print("  OK   month/week/day views + free-time")
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
