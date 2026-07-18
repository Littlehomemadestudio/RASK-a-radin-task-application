"""
rask.services.stats_service
===========================

Activity statistics & analytics.

Computes summary metrics, time-series breakdowns, trends, comparisons,
and human-readable insights from the activity database.

Key methods:
  • :meth:`summary` — high-level metrics for a date range
  • :meth:`by_category` / :meth:`by_day` / :meth:`by_weekday` /
    :meth:`by_hour` / :meth:`by_month` — grouped aggregations
  • :meth:`heatmap_data` — yearly heatmap (date -> level 0..4)
  • :meth:`trends` — bucketed time-series
  • :meth:`comparison` — period-A vs period-B comparison
  • :meth:`top_activities` / :meth:`longest_session` / :meth:`best_day`
  • :meth:`current_streak` / :meth:`longest_streak_ever` — any-activity streaks
  • :meth:`goal_hit_rate` — % of days any goal was hit
  • :meth:`predicted_today` — linear-regression forecast
  • :meth:`insights` — human-readable insights

All methods take ISO date strings and return plain dicts / lists.
Heavy aggregations are cached with ``functools.lru_cache`` (1-second
TTL via a manual cache key — Python's lru_cache doesn't support TTL
natively, so we wrap with a time-based key).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    days_between,
    end_of_month,
    end_of_week,
    format_duration,
    range_days,
    start_of_month,
    start_of_week,
    today_iso,
)
from ..core.validators import is_valid_iso_date

__all__ = ["StatsService", "stats_service"]

_log = get_logger("services.stats")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _ensure_dates(date_from: Optional[str],
                   date_to: Optional[str]) -> Tuple[str, str]:
    """Return a valid (date_from, date_to) tuple, defaulting sensibly."""
    today = today_iso()
    if date_from is None:
        date_from = add_days(today, -30)
    if date_to is None:
        date_to = today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _categories_map() -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    try:
        for c in db.category_list(include_archived=True):
            out[int(c["id"])] = c
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {})
    return out


def _normalize_weekday(weekday_py_wday_fmt: int) -> int:
    """Convert Python-Sunday-first weekday (0..6) to Saturday-first (0..6).

    The DB layer's ``activity_group_by_weekday`` returns weekday in
    Python's strftime('%w') format (Sun=0..Sat=6).  We convert to
    Saturday-first (Sat=0..Fri=6) to match the Persian convention.
    """
    # Sun=0, Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6
    # Sat=0, Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6
    mapping = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}
    return mapping.get(weekday_py_wday_fmt, 0)


# =============================================================================
# === StatsService                                                           ===
# =============================================================================

class StatsService:
    """Aggregations, trends, and insights over activities."""

    def __init__(self) -> None:
        # Manual cache for expensive calls.  Keyed by (method, args, minute).
        # We use minute-granularity timestamps so a fresh result is
        # computed at most once per minute.
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl_sec: float = 30.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        _log.debug("StatsService initialized")

    def _cache_get(self, key: str) -> Optional[Any]:
        """Return cached value if not expired, else None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, val = entry
        if (datetime.now().timestamp() - ts) > self._cache_ttl_sec:
            return None
        return val

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (datetime.now().timestamp(), value)

    def invalidate_cache(self) -> None:
        """Clear all cached stats (call after a data mutation)."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(
        self,
        date_from: str,
        date_to: str,
        category_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Return high-level summary metrics for the date range.

        Returns a dict with::

            {
              "total_min": int,
              "total_activities": int,
              "avg_per_day": float,           # minutes
              "avg_per_activity": float,      # minutes
              "best_day": dict | None,        # {date_iso, total_min}
              "worst_day": dict | None,
              "longest_session": dict | None, # {title, duration_min, date_iso}
              "day_count": int,               # distinct days with activity
              "category_ids": list[int] | None,
            }
        """
        cache_key = f"summary:{date_from}:{date_to}:{category_ids}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_list(
                date_from=date_from, date_to=date_to,
                category_ids=category_ids, limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return self._empty_summary(category_ids)

        total_min = sum(int(r.get("duration_min", 0) or 0) for r in rows)
        total_count = len(rows)

        # Days with activity
        days_with_activity = set(r.get("date_iso") for r in rows if r.get("date_iso"))
        day_count = len(days_with_activity)

        # Distinct days in range
        total_days = max(1, days_between(date_from, date_to) + 1)
        avg_per_day = total_min / total_days if total_days else 0.0
        avg_per_activity = total_min / total_count if total_count else 0.0

        # Best / worst day
        day_totals: Dict[str, int] = defaultdict(int)
        for r in rows:
            d = r.get("date_iso")
            if d:
                day_totals[d] += int(r.get("duration_min", 0) or 0)
        best_day = ({"date_iso": d, "total_min": t}
                     for d, t in day_totals.items())
        best_day = max(day_totals.items(), key=lambda kv: kv[1]) \
            if day_totals else None
        worst_day = min(day_totals.items(), key=lambda kv: kv[1]) \
            if day_totals else None
        best_day_dict = ({"date_iso": best_day[0], "total_min": best_day[1]}
                          if best_day else None)
        worst_day_dict = ({"date_iso": worst_day[0], "total_min": worst_day[1]}
                          if worst_day else None)

        # Longest session
        longest = None
        if rows:
            longest_row = max(
                rows, key=lambda r: int(r.get("duration_min", 0) or 0))
            longest = {
                "title": longest_row.get("title"),
                "duration_min": int(longest_row.get("duration_min", 0) or 0),
                "date_iso": longest_row.get("date_iso"),
                "category_id": longest_row.get("category_id"),
            }

        result = {
            "total_min": total_min,
            "total_activities": total_count,
            "avg_per_day": round(avg_per_day, 1),
            "avg_per_activity": round(avg_per_activity, 1),
            "best_day": best_day_dict,
            "worst_day": worst_day_dict,
            "longest_session": longest,
            "day_count": day_count,
            "date_from": date_from,
            "date_to": date_to,
            "category_ids": category_ids,
        }
        self._cache_set(cache_key, result)
        return result

    def _empty_summary(self, category_ids: Optional[List[int]]) -> Dict[str, Any]:
        return {
            "total_min": 0, "total_activities": 0,
            "avg_per_day": 0.0, "avg_per_activity": 0.0,
            "best_day": None, "worst_day": None,
            "longest_session": None, "day_count": 0,
            "category_ids": category_ids,
        }

    # ------------------------------------------------------------------
    # By-X aggregations
    # ------------------------------------------------------------------

    def by_category(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """Return per-category totals, sorted by total_min descending."""
        cache_key = f"by_category:{date_from}:{date_to}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_category(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        cats = _categories_map()
        out: List[Dict[str, Any]] = []
        for r in rows:
            cid = r.get("category_id")
            cat = cats.get(cid) if cid else None
            out.append({
                "category_id": cid,
                "category_name_en": cat.get("name_en") if cat else None,
                "category_name_fa": cat.get("name_fa") if cat else None,
                "color": cat.get("color") if cat else None,
                "icon": cat.get("icon") if cat else None,
                "count": int(r.get("count", 0)),
                "total_min": int(r.get("total_min", 0) or 0),
            })
        out.sort(key=lambda r: -r["total_min"])
        self._cache_set(cache_key, out)
        return out

    def by_day(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """Return per-day totals (chronological order)."""
        cache_key = f"by_day:{date_from}:{date_to}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_day(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        out = [{"date_iso": r["date_iso"],
                 "count": int(r["count"]),
                 "total_min": int(r["total_min"] or 0)}
                for r in rows]
        self._cache_set(cache_key, out)
        return out

    def by_weekday(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """Return per-weekday totals (Saturday-first index 0..6)."""
        cache_key = f"by_weekday:{date_from}:{date_to}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_weekday(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        out: List[Dict[str, Any]] = []
        for r in rows:
            py_wd = int(r.get("weekday", 0))
            sat_wd = _normalize_weekday(py_wd)
            out.append({
                "weekday": sat_wd,
                "weekday_py": py_wd,
                "count": int(r.get("count", 0)),
                "total_min": int(r.get("total_min", 0) or 0),
            })
        # Sort by Saturday-first weekday index.
        out.sort(key=lambda r: r["weekday"])
        self._cache_set(cache_key, out)
        return out

    def by_hour(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """Return per-hour-of-day totals (0..23)."""
        cache_key = f"by_hour:{date_from}:{date_to}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_hour(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        out = [{"hour": int(r["hour"]),
                 "count": int(r["count"]),
                 "total_min": int(r["total_min"] or 0)}
                for r in rows]
        out.sort(key=lambda r: r["hour"])
        self._cache_set(cache_key, out)
        return out

    def by_month(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        """Return per-month totals (YYYY-MM, chronological)."""
        cache_key = f"by_month:{date_from}:{date_to}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_month(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        out = [{"month": r["month"],
                 "count": int(r["count"]),
                 "total_min": int(r["total_min"] or 0)}
                for r in rows]
        out.sort(key=lambda r: r["month"])
        self._cache_set(cache_key, out)
        return out

    # ------------------------------------------------------------------
    # Heatmap
    # ------------------------------------------------------------------

    def heatmap_data(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return yearly heatmap data: ``[{date_iso, total_min, level}]``.

        `level` is 0..4 (0 = no activity, 4 = very high).  Thresholds
        are derived from the 25th/50th/75th/90th percentiles of all
        non-zero days in the year.
        """
        if year is None:
            year = date.today().year
        cache_key = f"heatmap:{year}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"
        try:
            rows = db.activity_group_by_day(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

        # Build a date -> total_min map.
        totals = {r["date_iso"]: int(r["total_min"] or 0) for r in rows}

        # Compute percentile thresholds from non-zero days.
        non_zero = sorted(t for t in totals.values() if t > 0)
        if len(non_zero) >= 4:
            q25 = non_zero[len(non_zero) // 4]
            q50 = non_zero[len(non_zero) // 2]
            q75 = non_zero[(3 * len(non_zero)) // 4]
            q90 = non_zero[int(0.9 * len(non_zero))]
        else:
            q25 = q50 = q75 = q90 = max(1, max(non_zero, default=0))

        def level_for(t: int) -> int:
            if t <= 0:
                return 0
            if t < q25:
                return 1
            if t < q50:
                return 2
            if t < q75:
                return 3
            return 4

        out: List[Dict[str, Any]] = []
        # Generate all days of the year.
        d = date(year, 1, 1)
        end = date(year, 12, 31)
        while d <= end:
            iso = d.isoformat()
            total = totals.get(iso, 0)
            out.append({
                "date_iso": iso,
                "total_min": total,
                "level": level_for(total),
            })
            d += timedelta(days=1)

        self._cache_set(cache_key, out)
        return out

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def trends(
        self,
        date_from: str,
        date_to: str,
        bucket: str = "day",
    ) -> List[Dict[str, Any]]:
        """Return a time-series with `bucket` granularity.

        `bucket` may be ``"day"`` (default), ``"week"``, or ``"month"``.
        Each entry has ``{bucket_start, bucket_end, total_min, count}``.
        """
        cache_key = f"trends:{date_from}:{date_to}:{bucket}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_group_by_day(
                date_from=date_from, date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

        # Build a date -> total map.
        day_map: Dict[str, int] = {r["date_iso"]: int(r["total_min"] or 0)
                                     for r in rows}
        day_count_map: Dict[str, int] = {r["date_iso"]: int(r["count"])
                                            for r in rows}

        out: List[Dict[str, Any]] = []
        if bucket == "day":
            for d in range_days(date_from, date_to):
                out.append({
                    "bucket_start": d, "bucket_end": d,
                    "total_min": day_map.get(d, 0),
                    "count": day_count_map.get(d, 0),
                })
        elif bucket == "week":
            cur = start_of_week(date_from)
            end = date_to
            while cur <= end:
                wk_end = end_of_week(cur)
                if wk_end > end:
                    wk_end = end
                total = sum(day_map.get(d, 0) for d in range_days(cur, wk_end))
                count = sum(day_count_map.get(d, 0)
                             for d in range_days(cur, wk_end))
                out.append({
                    "bucket_start": cur, "bucket_end": wk_end,
                    "total_min": total, "count": count,
                })
                cur = add_days(wk_end, 1)
        elif bucket == "month":
            cur = start_of_month(date_from)
            end = date_to
            while cur <= end:
                m_end = end_of_month(cur)
                if m_end > end:
                    m_end = end
                total = sum(day_map.get(d, 0) for d in range_days(cur, m_end))
                count = sum(day_count_map.get(d, 0)
                             for d in range_days(cur, m_end))
                out.append({
                    "bucket_start": cur, "bucket_end": m_end,
                    "total_min": total, "count": count,
                })
                # Advance to next month.
                y, m = cur.year, cur.month
                if m == 12:
                    cur = date(y + 1, 1, 1).isoformat()
                else:
                    cur = date(y, m + 1, 1).isoformat()
        else:
            for d in range_days(date_from, date_to):
                out.append({
                    "bucket_start": d, "bucket_end": d,
                    "total_min": day_map.get(d, 0),
                    "count": day_count_map.get(d, 0),
                })

        self._cache_set(cache_key, out)
        return out

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def comparison(
        self,
        period_a: Tuple[str, str],
        period_b: Tuple[str, str],
    ) -> Dict[str, Any]:
        """Compare two date ranges.

        Returns ``{a_total, b_total, change, percent_change}``.
        ``change`` is ``b - a`` (positive = improvement).
        ``percent_change`` is ``100 * change / a_total`` (None if a=0).
        """
        a_from, a_to = period_a
        b_from, b_to = period_b
        a_total = self.summary(a_from, a_to).get("total_min", 0)
        b_total = self.summary(b_from, b_to).get("total_min", 0)
        change = b_total - a_total
        if a_total > 0:
            pct = (change / a_total) * 100.0
        else:
            pct = None
        return {
            "a_total": a_total,
            "b_total": b_total,
            "change": change,
            "percent_change": round(pct, 1) if pct is not None else None,
            "a_period": {"from": a_from, "to": a_to},
            "b_period": {"from": b_from, "to": b_to},
        }

    # ------------------------------------------------------------------
    # Top-N
    # ------------------------------------------------------------------

    def top_activities(
        self,
        date_from: str,
        date_to: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return the N longest activities in the range."""
        date_from, date_to = _ensure_dates(date_from, date_to)
        try:
            rows = db.activity_list(
                date_from=date_from, date_to=date_to, limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        rows = sorted(rows,
                       key=lambda r: -int(r.get("duration_min", 0) or 0))
        return rows[:limit]

    def longest_session(
        self,
        date_from: str,
        date_to: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the single longest activity in the range (or None)."""
        top = self.top_activities(date_from, date_to, limit=1)
        return top[0] if top else None

    def best_day(
        self,
        date_from: str,
        date_to: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the day with the highest total minutes (or None)."""
        s = self.summary(date_from, date_to)
        return s.get("best_day")

    # ------------------------------------------------------------------
    # Streaks (any-activity, not goal-specific)
    # ------------------------------------------------------------------

    def current_streak(self) -> int:
        """Return the current any-activity streak (consecutive days with ≥1
        activity, counting back from today).
        """
        try:
            today = today_iso()
            streak = 0
            d = today
            for _ in range(365):
                cnt = db.activity_count(date_from=d, date_to=d)
                if cnt > 0:
                    streak += 1
                    d = add_days(d, -1)
                else:
                    break
            return streak
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    def longest_streak_ever(self) -> int:
        """Return the longest any-activity streak ever recorded.

        Scans the entire activity history (capped at 3650 days = 10 years).
        """
        try:
            today = today_iso()
            # Find earliest activity date.
            rows = db.activity_list(limit=1, order_by="date_iso ASC")
            if not rows:
                return 0
            earliest = rows[0].get("date_iso", today)
            if not earliest:
                return 0
            days = range_days(earliest, today)
            # Reverse so we scan newest-first for early exit.
            # Actually, for longest streak we need to scan the whole range.
            best = 0
            current = 0
            for d in days:
                cnt = db.activity_count(date_from=d, date_to=d)
                if cnt > 0:
                    current += 1
                    if current > best:
                        best = current
                else:
                    current = 0
            return best
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    # ------------------------------------------------------------------
    # Goal hit rate
    # ------------------------------------------------------------------

    def goal_hit_rate(self, days: int = 30) -> float:
        """Return the fraction of the last `days` days any goal was hit.

        Returns a float in ``[0.0, 1.0]``.
        """
        if days <= 0:
            return 0.0
        try:
            from .goal_service import goal_service
            today = today_iso()
            distinct_hit_days: set = set()
            for g in goal_service.list(only_active=True):
                try:
                    from .streak_service import streak_service
                    history = streak_service.history(g["id"])
                    distinct_hit_days.update(h[:10] for h in history)
                except Exception:  # noqa: BLE001
                    pass
            # Count how many of the last `days` days are in the hit set.
            count = 0
            for offset in range(days):
                d = add_days(today, -offset)
                if d in distinct_hit_days:
                    count += 1
            return count / days
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0.0

    # ------------------------------------------------------------------
    # Linear-regression prediction
    # ------------------------------------------------------------------

    def predicted_today(self) -> int:
        """Predict today's total minutes using linear regression on the
        last 14 days.

        Returns the predicted integer minutes (≥ 0).  If insufficient
        data, returns the average of available days.
        """
        try:
            today = today_iso()
            days_x: List[int] = []
            mins_y: List[int] = []
            for i in range(14, 0, -1):
                d = add_days(today, -i)
                total = db.activity_sum_duration(date_from=d, date_to=d)
                days_x.append(14 - i)  # 0..13
                mins_y.append(int(total or 0))
            if not mins_y:
                return 0
            if len(mins_y) < 2:
                return mins_y[0]
            # Simple OLS linear regression.
            n = len(days_x)
            sum_x = sum(days_x)
            sum_y = sum(mins_y)
            sum_xy = sum(x * y for x, y in zip(days_x, mins_y))
            sum_x2 = sum(x * x for x in days_x)
            denom = n * sum_x2 - sum_x * sum_x
            if denom == 0:
                return sum_y // n
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            # Predict for x = 14 (today).
            pred = slope * 14 + intercept
            return max(0, int(round(pred)))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def insights(
        self,
        date_from: str,
        date_to: str,
    ) -> List[Dict[str, Any]]:
        """Generate human-readable insights about the date range.

        Returns a list of dicts::

            {"kind": str, "text": str, "data": dict}

        Kinds: ``"peak_weekday"``, ``"peak_hour"``, ``"top_category"``,
        ``"comparison_vs_last_week"``, ``"consistency"``, ``"streak"``.
        """
        out: List[Dict[str, Any]] = []
        date_from, date_to = _ensure_dates(date_from, date_to)

        # Peak weekday
        try:
            wd_rows = self.by_weekday(date_from, date_to)
            if wd_rows:
                peak = max(wd_rows, key=lambda r: r["total_min"])
                if peak["total_min"] > 0:
                    # Saturday-first index -> name.
                    from ..core.time_utils import weekday_name
                    sample_iso = add_days(today_iso(), -(date.today().weekday() -
                                                          (peak["weekday"] - 2) % 7))
                    # Simpler: just use a fixed reference date.
                    ref_date = date(2025, 3, 22)  # a Saturday
                    for offset in range(7):
                        d = ref_date + timedelta(days=offset)
                        # Sat-first index = offset
                        # Map: Sat=0, Sun=1, ... Fri=6
                        # date(2025,3,22) is a Saturday
                        if offset == peak["weekday"]:
                            name = weekday_name(d.isoformat(), "fa")
                            break
                    else:
                        name = "?"
                    out.append({
                        "kind": "peak_weekday",
                        "text": f"پرکاربردترین روز: {name} "
                                f"({peak['total_min']} دقیقه)",
                        "data": peak,
                    })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Peak hour
        try:
            hr_rows = self.by_hour(date_from, date_to)
            if hr_rows:
                peak = max(hr_rows, key=lambda r: r["total_min"])
                if peak["total_min"] > 0:
                    out.append({
                        "kind": "peak_hour",
                        "text": f"ساعت اوج فعالیت: {peak['hour']:02d}:00 "
                                f"({peak['total_min']} دقیقه)",
                        "data": peak,
                    })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Top category
        try:
            cat_rows = self.by_category(date_from, date_to)
            if cat_rows:
                top = cat_rows[0]
                if top["total_min"] > 0:
                    name = top.get("category_name_fa") or \
                        top.get("category_name_en") or "—"
                    out.append({
                        "kind": "top_category",
                        "text": f"بیشترین زمان: {name} "
                                f"({top['total_min']} دقیقه)",
                        "data": top,
                    })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Comparison vs previous period of same length
        try:
            days = days_between(date_from, date_to) + 1
            prev_from = add_days(date_from, -days)
            prev_to = add_days(date_from, -1)
            comp = self.comparison(
                (prev_from, prev_to), (date_from, date_to))
            if comp["percent_change"] is not None:
                pct = comp["percent_change"]
                if pct > 5:
                    arrow = "افزایش"
                elif pct < -5:
                    arrow = "کاهش"
                else:
                    arrow = "تثبیت"
                out.append({
                    "kind": "comparison_vs_last_period",
                    "text": f"{arrow} {abs(pct):.0f}٪ نسبت به دوره قبل",
                    "data": comp,
                })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Current streak
        try:
            streak = self.current_streak()
            if streak >= 2:
                out.append({
                    "kind": "streak",
                    "text": f"زنجیره فعلی: {streak} روز",
                    "data": {"current_streak": streak},
                })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Consistency: % of days in range with at least 1 activity
        try:
            s = self.summary(date_from, date_to)
            total_days = max(1, days_between(date_from, date_to) + 1)
            consistency = s.get("day_count", 0) / total_days
            if consistency > 0:
                out.append({
                    "kind": "consistency",
                    "text": f"استمرار: {consistency * 100:.0f}٪ روزها فعال",
                    "data": {"consistency": round(consistency, 2)},
                })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        return out

    # ------------------------------------------------------------------
    # Duration formatting (delegate to time_utils)
    # ------------------------------------------------------------------

    def format_duration_localized(self, min: int, lang: str = "fa") -> str:
        """Format `min` minutes as a localized string."""
        return format_duration(min, lang=lang, short=True)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

stats_service: StatsService = StatsService()
