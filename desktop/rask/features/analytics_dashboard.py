"""
rask.features.analytics_dashboard
=================================

Advanced analytics: time-series, trends, correlations, heatmaps,
forecasting, anomaly detection, and a "report card" letter grade.

Distinct from :class:`rask.services.stats_service.StatsService` which
provides basic aggregations, the analytics dashboard produces
**derived** insights:

  • ``productivity_over_time(days)``       — daily productivity score
  • ``category_trends(days)``              — per-category time series
  • ``time_distribution(date_from, date_to)`` — % by category/hour/weekday
  • ``goal_progress_over_time(goal_id, days)`` — goal hit-rate over time
  • ``correlation_analysis()``             — e.g. "Reading in morning
                                              correlates with better mood"
  • ``weekly_heatmap()``                   — 7x24 matrix of activity minutes
  • ``year_over_year()``                   — compare this year vs last by month
  • ``forecast_tomorrow()``                — predict tomorrow's activity
  • ``anomaly_detection()``                — find unusual days
  • ``report_card()``                      — letter grades per metric

All methods return plain dicts/lists ready for charting.  No
CustomTkinter dependency — fully headless-able.

Events
------

  ``analytics.computed`` — {method, days, generated_at}
"""
from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    days_between,
    end_of_month,
    end_of_week,
    range_days,
    start_of_month,
    start_of_week,
    start_of_year,
    today_iso,
)

__all__ = [
    "AnalyticsService",
    "analytics_service",
]

_log = get_logger("features.analytics")


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _fa(value: Any) -> str:
    return i18n.to_fa_digits(value)


def _weekday_index_sat_first(d: date) -> int:
    """0=Sat..6=Fri."""
    mapping = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}
    return mapping[d.weekday()]


def _safe_avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _safe_avg(values)
    variance = sum((v - avg) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _linear_regression(xs: List[float],
                        ys: List[float]) -> Tuple[float, float, float]:
    """Return (slope, intercept, r_squared) for a simple linear fit.

    Returns (0, 0, 0) on any error or if lists are too short.
    """
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0, 0.0, 0.0
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0, 0.0, 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    # R-squared
    avg_y = sum_y / n
    ss_tot = sum((y - avg_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2
                  for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
    return slope, intercept, r2


def _grade_for(value: float, thresholds: List[Tuple[float, str]]) -> str:
    """Return a letter grade for `value` based on descending thresholds."""
    for threshold, grade in thresholds:
        if value >= threshold:
            return grade
    return "F"


# =============================================================================
# === AnalyticsService                                                      ===
# =============================================================================

class AnalyticsService:
    """Advanced analytics & forecasting."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Productivity over time
    # ------------------------------------------------------------------

    def productivity_over_time(self, days: int = 90) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, score, total_min, count}]`` for the last `days` days.

        Score is a 0..100 productivity index computed from minutes +
        count + (penalty for zero days).
        """
        if days <= 0:
            days = 90
        date_from = add_days(today_iso(), -(days - 1))
        by_day = db.activity_group_by_day(date_from=date_from,
                                           date_to=today_iso())
        day_map = {r["date_iso"]: r for r in by_day}
        out: List[Dict[str, Any]] = []
        for d in range_days(date_from, today_iso()):
            r = day_map.get(d)
            total_min = int(r["total_min"]) if r else 0
            count = int(r["count"]) if r else 0
            # Score formula:
            #   minutes: 0..60 pts (cap at 360 min)
            #   count:   0..30 pts (cap at 10 activities)
            #   bonus:   10 pts if both > 0
            score = min(60, int(total_min / 6)) + min(30, count * 3)
            if total_min > 0 and count > 0:
                score += 10
            score = max(0, min(100, score))
            out.append({
                "date_iso": d,
                "score": score,
                "total_min": total_min,
                "count": count,
            })
        bus.publish("analytics.computed",
                    {"method": "productivity_over_time",
                     "days": days, "generated_at": today_iso()})
        return out

    # ------------------------------------------------------------------
    # Category trends
    # ------------------------------------------------------------------

    def category_trends(self, days: int = 90) -> Dict[int, List[Dict[str, Any]]]:
        """Return ``{category_id: [{date_iso, total_min, count}]}`` for the last `days` days.

        Categories with no activity in the window are omitted.
        """
        if days <= 0:
            days = 90
        date_from = add_days(today_iso(), -(days - 1))
        try:
            # We need per-category per-day, which the DB layer doesn't
            # provide directly.  Fetch all activities in the window and
            # aggregate in Python.
            activities = db.activity_list(date_from=date_from,
                                           date_to=today_iso(),
                                           limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return {}
        by_cat_day: Dict[int, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"total_min": 0, "count": 0}))
        for a in activities:
            cid = int(a.get("category_id") or 0)
            d = a.get("date_iso")
            if not d:
                continue
            by_cat_day[cid][d]["total_min"] += int(a.get("duration_min") or 0)
            by_cat_day[cid][d]["count"] += 1
        out: Dict[int, List[Dict[str, Any]]] = {}
        for cid, day_map in by_cat_day.items():
            series: List[Dict[str, Any]] = []
            for d in range_days(date_from, today_iso()):
                e = day_map.get(d, {"total_min": 0, "count": 0})
                series.append({"date_iso": d, **e})
            out[cid] = series
        bus.publish("analytics.computed",
                    {"method": "category_trends", "days": days,
                     "generated_at": today_iso()})
        return out

    # ------------------------------------------------------------------
    # Time distribution
    # ------------------------------------------------------------------

    def time_distribution(self, date_from: Optional[str] = None,
                          date_to: Optional[str] = None) -> Dict[str, Any]:
        """Return % by category, by hour, and by weekday for the range."""
        date_from = date_from or add_days(today_iso(), -29)
        date_to = date_to or today_iso()
        by_cat = db.activity_group_by_category(date_from=date_from,
                                                date_to=date_to)
        by_hour = db.activity_group_by_hour(date_from=date_from,
                                             date_to=date_to)
        by_wday = db.activity_group_by_weekday(date_from=date_from,
                                                date_to=date_to)
        total_min = sum(int(r.get("total_min") or 0) for r in by_cat) or 1
        # By category (% of total)
        cat_pct: List[Dict[str, Any]] = []
        cats = {int(c["id"]): c for c in db.category_list()}
        for r in by_cat:
            cid = int(r["category_id"] or 0)
            minutes = int(r.get("total_min") or 0)
            if minutes == 0:
                continue
            cat = cats.get(cid, {})
            cat_pct.append({
                "category_id": cid,
                "category_name": cat.get("name_fa") or cat.get("name_en") or "—",
                "category_color": cat.get("color") or "#9A9A9F",
                "minutes": minutes,
                "percent": round(minutes / total_min * 100, 1),
            })
        cat_pct.sort(key=lambda x: x["minutes"], reverse=True)
        # By hour (% of total)
        hour_pct: List[Dict[str, Any]] = []
        for h in range(24):
            minutes = next((int(r.get("total_min") or 0)
                             for r in by_hour if int(r["hour"]) == h), 0)
            hour_pct.append({
                "hour": h,
                "minutes": minutes,
                "percent": round(minutes / total_min * 100, 1) if minutes else 0,
            })
        # By weekday (% of total) — convert Sun-first to Sat-first.
        wday_pct: List[Dict[str, Any]] = []
        wday_names_fa = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه",
                          "چهارشنبه", "پنجشنبه", "جمعه"]
        for w in range(7):  # 0=Sat..6=Fri
            # Find the Sun-first index that corresponds to Sat-first w.
            # Sun=0..Sat=6, Sat=0..Fri=6
            sun_first_idx = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}[w]
            minutes = next((int(r.get("total_min") or 0)
                             for r in by_wday
                             if int(r["weekday"]) == sun_first_idx), 0)
            wday_pct.append({
                "weekday": w,
                "weekday_name_fa": wday_names_fa[w],
                "minutes": minutes,
                "percent": round(minutes / total_min * 100, 1) if minutes else 0,
            })
        return {
            "date_from": date_from,
            "date_to": date_to,
            "total_min": int(total_min) if total_min != 1 else 0,
            "by_category": cat_pct,
            "by_hour": hour_pct,
            "by_weekday": wday_pct,
        }

    # ------------------------------------------------------------------
    # Goal progress over time
    # ------------------------------------------------------------------

    def goal_progress_over_time(self, goal_id: int,
                                 days: int = 30) -> List[Dict[str, Any]]:
        """Return ``[{date_iso, hit: bool, ratio: float, minutes: int}]``.

        Walks the last `days` days and checks whether the goal was hit
        on each day.
        """
        if days <= 0:
            days = 30
        date_from = add_days(today_iso(), -(days - 1))
        try:
            from ..services.goal_service import goal_service
            goal = goal_service.get(goal_id)
            if goal is None:
                return []
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            return []
        out: List[Dict[str, Any]] = []
        for d in range_days(date_from, today_iso()):
            try:
                hit = goal_service.hit_date(goal_id, d)
                progress = goal_service.progress_for(goal_id, date_iso=d)
                ratio = float(progress.get("ratio") or 0.0)
                minutes = int(progress.get("minutes") or 0)
                target = int(progress.get("target") or 0)
                out.append({
                    "date_iso": d,
                    "hit": hit,
                    "ratio": ratio,
                    "minutes": minutes,
                    "target": target,
                })
            except Exception:  # noqa: BLE001
                continue
        return out

    # ------------------------------------------------------------------
    # Correlation analysis
    # ------------------------------------------------------------------

    def correlation_analysis(self) -> List[Dict[str, Any]]:
        """Find correlations between mood and activity categories.

        Returns a list of::

            {
                "category_id": int,
                "category_name": str,
                "category_color": str,
                "correlation": float,   # -1..1
                "description_fa": str,
                "sample_size": int,
            }

        Sorted by absolute correlation descending.
        """
        try:
            from .mood_tracker import mood_service
        except Exception:  # noqa: BLE001
            return []
        # Pull last 90 days.
        date_from = add_days(today_iso(), -89)
        # Build date -> avg mood
        date_to_moods: Dict[str, List[int]] = defaultdict(list)
        for e in mood_service.list(date_from=date_from, limit=10000):
            date_to_moods[e.date_iso].append(e.mood)
        date_to_avg_mood = {d: sum(v) / len(v) for d, v in date_to_moods.items() if v}
        # Build date -> set of category_ids
        date_to_cats: Dict[str, set] = defaultdict(set)
        activities = db.activity_list(date_from=date_from, limit=100000)
        for a in activities:
            d = a.get("date_iso")
            cid = a.get("category_id")
            if d and cid:
                date_to_cats[d].add(int(cid))
        # For each category, compute correlation between (had category that
        # day) and (mood that day).  We use a simple binary correlation:
        # correlation = (avg_mood_with_cat - avg_mood_without_cat) / std(mood)
        all_moods = list(date_to_avg_mood.values())
        if not all_moods:
            return []
        std = _safe_std(all_moods) or 1.0
        cats = {int(c["id"]): c for c in db.category_list()}
        out: List[Dict[str, Any]] = []
        for cid in set().union(*date_to_cats.values()) if date_to_cats else []:
            with_cat = [date_to_avg_mood[d]
                         for d in date_to_cats
                         if cid in date_to_cats[d] and d in date_to_avg_mood]
            without_cat = [date_to_avg_mood[d]
                            for d in date_to_cats
                            if cid not in date_to_cats[d] and d in date_to_avg_mood]
            if not with_cat or not without_cat:
                continue
            avg_with = _safe_avg(with_cat)
            avg_without = _safe_avg(without_cat)
            # Effect size (Cohen's d-like)
            correlation = (avg_with - avg_without) / std
            cat = cats.get(cid, {})
            name = cat.get("name_fa") or cat.get("name_en") or "—"
            color = cat.get("color") or "#9A9A9F"
            if correlation > 0.3:
                desc = (f"فعالیت در دسته «{name}» با حال بهتر همبستگی دارد "
                        f"(+{_fa(round(correlation, 2))})")
            elif correlation < -0.3:
                desc = (f"فعالیت در دسته «{name}» با حال بدتر همبستگی دارد "
                        f"({_fa(round(correlation, 2))})")
            else:
                desc = (f"هیچ همبستگی معناداری بین «{name}» و حالت نیست "
                        f"({_fa(round(correlation, 2))})")
            out.append({
                "category_id": cid,
                "category_name": name,
                "category_color": color,
                "correlation": round(correlation, 3),
                "description_fa": desc,
                "sample_size": len(with_cat),
            })
        out.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        return out

    # ------------------------------------------------------------------
    # Weekly heatmap (7 days x 24 hours)
    # ------------------------------------------------------------------

    def weekly_heatmap(self) -> List[List[int]]:
        """Return a 7x24 matrix [weekday][hour] of total activity minutes.

        Weekday index is 0=Sat..6=Fri (Persian convention).
        """
        # Use last 90 days for a stable heatmap.
        date_from = add_days(today_iso(), -89)
        by_hour = db.activity_group_by_hour(date_from=date_from,
                                             date_to=today_iso())
        # We need per-(weekday, hour) — but the DB layer's
        # activity_group_by_hour only groups by hour.  Fetch activities
        # and aggregate in Python.
        activities = db.activity_list(date_from=date_from, limit=100000)
        matrix: List[List[int]] = [[0] * 24 for _ in range(7)]
        for a in activities:
            start_ts = a.get("start_ts")
            if not start_ts:
                continue
            try:
                dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                continue
            wday = _weekday_index_sat_first(dt.date())
            hour = dt.hour
            matrix[wday][hour] += int(a.get("duration_min") or 0)
        return matrix

    # ------------------------------------------------------------------
    # Year over year
    # ------------------------------------------------------------------

    def year_over_year(self) -> Dict[str, Any]:
        """Compare this year vs last year by month.

        Returns::

            {
                "this_year": int,
                "last_year": int,
                "by_month": [
                    {"month": "2025-01", "this_year_min": int, "last_year_min": int}, ...
                ],
                "this_year_total": int,
                "last_year_total": int,
                "growth_pct": float,
            }
        """
        today = date.today()
        this_year = today.year
        last_year = this_year - 1
        # Pull this year's monthly aggregates.
        try:
            from ..core.time_utils import start_of_year, end_of_year
            this_start = start_of_year(today.isoformat())
            this_end = end_of_year(today.isoformat())
            last_start = add_days(this_start, -365)
            last_end = add_days(this_end, -365)
            this_by_month = db.activity_group_by_month(date_from=this_start,
                                                         date_to=this_end)
            last_by_month = db.activity_group_by_month(date_from=last_start,
                                                         date_to=last_end)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return {}
        this_map = {r["month"]: int(r["total_min"] or 0) for r in this_by_month}
        last_map = {r["month"]: int(r["total_min"] or 0) for r in last_by_month}
        # Build per-month comparison (last 12 months of each year).
        by_month: List[Dict[str, Any]] = []
        for m in range(1, 13):
            this_key = f"{this_year}-{m:02d}"
            last_key = f"{last_year}-{m:02d}"
            by_month.append({
                "month": this_key,
                "this_year_min": this_map.get(this_key, 0),
                "last_year_min": last_map.get(last_key, 0),
            })
        this_total = sum(this_map.values())
        last_total = sum(last_map.values())
        growth_pct = (round((this_total - last_total) / last_total * 100, 1)
                       if last_total > 0 else (100.0 if this_total > 0 else 0.0))
        return {
            "this_year": this_year,
            "last_year": last_year,
            "by_month": by_month,
            "this_year_total": this_total,
            "last_year_total": last_total,
            "growth_pct": growth_pct,
        }

    # ------------------------------------------------------------------
    # Forecast tomorrow
    # ------------------------------------------------------------------

    def forecast_tomorrow(self) -> Dict[str, Any]:
        """Predict tomorrow's total activity minutes using linear regression
        on the last 30 days.

        Returns::

            {
                "predicted_min": int,
                "confidence": float,  # 0..1 (r_squared of the fit)
                "trend": str,         # "up" | "down" | "flat"
                "trend_slope": float,
                "based_on_days": int,
            }
        """
        days = 30
        date_from = add_days(today_iso(), -(days - 1))
        by_day = db.activity_group_by_day(date_from=date_from,
                                           date_to=today_iso())
        day_map = {r["date_iso"]: int(r["total_min"] or 0) for r in by_day}
        xs: List[float] = []
        ys: List[float] = []
        for i, d in enumerate(range_days(date_from, today_iso())):
            xs.append(float(i))
            ys.append(float(day_map.get(d, 0)))
        slope, intercept, r2 = _linear_regression(xs, ys)
        # Predict day 30 (tomorrow).
        predicted = max(0, int(slope * (days) + intercept))
        if slope > 1.0:
            trend = "up"
        elif slope < -1.0:
            trend = "down"
        else:
            trend = "flat"
        return {
            "predicted_min": predicted,
            "confidence": round(max(0.0, min(1.0, r2)), 3),
            "trend": trend,
            "trend_slope": round(slope, 3),
            "based_on_days": days,
        }

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    def anomaly_detection(self) -> List[Dict[str, Any]]:
        """Detect days with unusual activity patterns.

        A day is flagged if:
          • Total minutes > mean + 2*std (very high day)
          • Total minutes < mean - 2*std (very low day, only if mean > 0)
          • Zero activities on a weekday (potential gap)
        """
        date_from = add_days(today_iso(), -29)
        by_day = db.activity_group_by_day(date_from=date_from,
                                           date_to=today_iso())
        if not by_day:
            return []
        mins = [int(r.get("total_min") or 0) for r in by_day]
        avg = _safe_avg([float(m) for m in mins])
        std = _safe_std([float(m) for m in mins])
        anomalies: List[Dict[str, Any]] = []
        for r in by_day:
            m = int(r.get("total_min") or 0)
            d = r["date_iso"]
            try:
                d_obj = date.fromisoformat(d)
                wday = _weekday_index_sat_first(d_obj)
            except Exception:  # noqa: BLE001
                wday = 0
            # Very high
            if std > 0 and m > avg + 2 * std and m > 30:
                anomalies.append({
                    "date_iso": d,
                    "kind": "very_high",
                    "minutes": m,
                    "expected": round(avg, 1),
                    "delta": round(m - avg, 1),
                    "description_fa": (
                        f"روز بسیار پر − {_fa(m)} دقیقه (میانگین: {_fa(round(avg))})"
                    ),
                })
            # Very low (only if avg > 0)
            elif std > 0 and m < avg - 2 * std and avg > 0:
                anomalies.append({
                    "date_iso": d,
                    "kind": "very_low",
                    "minutes": m,
                    "expected": round(avg, 1),
                    "delta": round(m - avg, 1),
                    "description_fa": (
                        f"روز بسیار کم − {_fa(m)} دقیقه (میانگین: {_fa(round(avg))})"
                    ),
                })
            # Zero on a weekday
            elif m == 0 and wday < 5:  # Sat..Thu
                anomalies.append({
                    "date_iso": d,
                    "kind": "zero_weekday",
                    "minutes": 0,
                    "expected": round(avg, 1),
                    "delta": round(-avg, 1),
                    "description_fa": (
                        "هیچ فعالیتی ثبت نشده (روز هفته)"
                    ),
                })
        return anomalies

    # ------------------------------------------------------------------
    # Report card
    # ------------------------------------------------------------------

    def report_card(self) -> Dict[str, Any]:
        """Letter grade (A-F) for various metrics.

        Returns::

            {
                "overall_grade": str,
                "metrics": [
                    {"name": str, "value": float, "grade": str,
                     "description_fa": str}, ...
                ],
            }
        """
        metrics: List[Dict[str, Any]] = []
        # 1. Total minutes last 7 days (target: 600+)
        date_from = add_days(today_iso(), -6)
        total_min_7d = db.activity_sum_duration(date_from=date_from,
                                                  date_to=today_iso())
        grade = _grade_for(total_min_7d, [
            (900, "A"), (600, "B"), (300, "C"), (60, "D"),
        ])
        metrics.append({
            "name": "weekly_minutes",
            "label_fa": "دقیقه هفتگی",
            "value": total_min_7d,
            "grade": grade,
            "description_fa": f"{_fa(total_min_7d)} دقیقه در ۷ روز گذشته",
        })
        # 2. Activity count last 7 days
        count_7d = db.activity_count(date_from=date_from,
                                      date_to=today_iso())
        grade = _grade_for(count_7d, [
            (35, "A"), (20, "B"), (10, "C"), (3, "D"),
        ])
        metrics.append({
            "name": "weekly_count",
            "label_fa": "تعداد فعالیت هفتگی",
            "value": count_7d,
            "grade": grade,
            "description_fa": f"{_fa(count_7d)} فعالیت در ۷ روز گذشته",
        })
        # 3. Streak (any-activity)
        try:
            from ..services.stats_service import stats_service
            streak = stats_service.current_streak()
        except Exception:  # noqa: BLE001
            streak = 0
        grade = _grade_for(streak, [
            (30, "A"), (14, "B"), (7, "C"), (3, "D"),
        ])
        metrics.append({
            "name": "streak",
            "label_fa": "زنجیره",
            "value": streak,
            "grade": grade,
            "description_fa": f"{_fa(streak)} روز زنجیره فعال",
        })
        # 4. Goal hit rate (last 30 days)
        try:
            from ..services.goal_service import goal_service
            goals = goal_service.list(only_active=True)
            if goals:
                hits = sum(1 for g in goals
                            if goal_service.hit_today(g["id"]))
                hit_rate = hits / len(goals)
            else:
                hit_rate = 0.5  # neutral
        except Exception:  # noqa: BLE001
            hit_rate = 0.0
        grade = _grade_for(hit_rate * 100, [
            (80, "A"), (60, "B"), (40, "C"), (20, "D"),
        ])
        metrics.append({
            "name": "goal_hit_rate",
            "label_fa": "نرخ موفقیت اهداف",
            "value": round(hit_rate * 100, 1),
            "grade": grade,
            "description_fa": f"{_fa(int(hit_rate * 100))}٪ اهداف محقق شده",
        })
        # 5. Category diversity (last 30 days)
        date_from = add_days(today_iso(), -29)
        by_cat = db.activity_group_by_category(date_from=date_from,
                                                date_to=today_iso())
        distinct = sum(1 for r in by_cat if int(r.get("total_min") or 0) > 0)
        grade = _grade_for(distinct, [
            (6, "A"), (4, "B"), (2, "C"), (1, "D"),
        ])
        metrics.append({
            "name": "category_diversity",
            "label_fa": "تنوع دسته‌ها",
            "value": distinct,
            "grade": grade,
            "description_fa": f"{_fa(distinct)} دسته فعال در ۳۰ روز گذشته",
        })
        # Overall = average grade point
        grade_points = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        avg_point = _safe_avg([float(grade_points.get(m["grade"], 0))
                                for m in metrics])
        if avg_point >= 3.5:
            overall = "A"
        elif avg_point >= 2.5:
            overall = "B"
        elif avg_point >= 1.5:
            overall = "C"
        elif avg_point >= 0.5:
            overall = "D"
        else:
            overall = "F"
        return {
            "overall_grade": overall,
            "metrics": metrics,
        }


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

analytics_service: AnalyticsService = AnalyticsService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== analytics_dashboard self-tests ===")
    try:
        prod = analytics_service.productivity_over_time(days=7)
        assert len(prod) == 7
        trends = analytics_service.category_trends(days=7)
        assert isinstance(trends, dict)
        dist = analytics_service.time_distribution()
        assert "by_category" in dist and "by_hour" in dist
        hm = analytics_service.weekly_heatmap()
        assert len(hm) == 7 and all(len(row) == 24 for row in hm)
        forecast = analytics_service.forecast_tomorrow()
        assert "predicted_min" in forecast
        anomalies = analytics_service.anomaly_detection()
        assert isinstance(anomalies, list)
        rc = analytics_service.report_card()
        assert "overall_grade" in rc and "metrics" in rc
        yoy = analytics_service.year_over_year()
        assert "by_month" in yoy
        print("  OK   all analytics methods returned valid results")
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
