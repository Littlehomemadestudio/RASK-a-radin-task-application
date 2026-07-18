"""analytics.py — Analytics engine for Rask stats screen.

Provides rich statistics computations beyond the basic aggregations
in database.py:
  - daily/weekly/monthly trends
  - comparison vs previous period
  - percentile distributions (p25, p50, p75, p90)
  - productivity / consistency / balance scores
  - hourly / weekday distributions
  - top activities / categories
  - insights generation
  - streak health check
"""
from __future__ import annotations
import datetime as _dt
import statistics
from typing import Optional

from . import database
from . import date_utils
from . import config
from .i18n import t, to_fa_digits


# =====================================================================
# === PERIOD COMPARISON ===
# =====================================================================
def compare_periods(current_start: str, current_end: str,
                    previous_start: str, previous_end: str) -> dict:
    """Compare two periods. Returns dict with totals, delta, percent change."""
    current = database.total_seconds_between(current_start, current_end)
    previous = database.total_seconds_between(previous_start, previous_end)
    delta = current - previous
    pct = (delta / previous * 100) if previous > 0 else (
        100.0 if current > 0 else 0.0
    )
    return {
        "current_sec": current,
        "previous_sec": previous,
        "delta_sec": delta,
        "delta_percent": pct,
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


def previous_period_range(start_iso: str, end_iso: str) -> tuple[str, str]:
    """Given a date range, return the equivalent previous-period range.
    
    For a 7-day range starting 2024-01-08, returns the 7 days before that.
    """
    d1 = date_utils.parse_date(start_iso)
    d2 = date_utils.parse_date(end_iso)
    days = (d2 - d1).days + 1
    prev_end = d1 - _dt.timedelta(days=1)
    prev_start = prev_end - _dt.timedelta(days=days - 1)
    return (prev_start.isoformat(), prev_end.isoformat())


# =====================================================================
# === DISTRIBUTION ANALYSIS ===
# =====================================================================
def duration_distribution(start_iso: str, end_iso: str,
                          category_id: Optional[int] = None) -> dict:
    """Return distribution statistics for activity durations in the range."""
    stats = database.activity_duration_stats(start_iso, end_iso, category_id)
    return stats


def hourly_distribution(date_iso: str) -> list[int]:
    """Return 24-element list of seconds per hour for the given date."""
    return database.seconds_per_hour(date_iso)


def hourly_distribution_range(start_iso: str, end_iso: str) -> list[int]:
    """Return 24-element list of total seconds per hour across the range."""
    buckets = [0] * 24
    activities = database.activities_by_date_range(start_iso, end_iso)
    for a in activities:
        ts = a.get("start_iso") or a.get("created_at")
        if not ts or len(ts) < 13:
            continue
        try:
            h = int(ts[11:13])
            if 0 <= h < 24:
                buckets[h] += int(a.get("duration_sec", 0) or 0)
        except ValueError:
            continue
    return buckets


def weekday_distribution(start_iso: str, end_iso: str) -> list[int]:
    """Return 7-element list of total seconds per weekday (Mon=0, Sun=6)."""
    return database.seconds_per_weekday(start_iso, end_iso)


def weekend_vs_weekday(start_iso: str, end_iso: str) -> dict:
    """Compare weekend vs weekday totals."""
    per_day = database.seconds_per_day(start_iso, end_iso)
    weekend_sec = 0
    weekday_sec = 0
    weekend_days = 0
    weekday_days = 0
    for date_iso, sec in per_day.items():
        try:
            d = _dt.date.fromisoformat(date_iso)
        except ValueError:
            continue
        # Python weekday(): Mon=0, Sun=6 — Persian weekend is Thu (3) and Fri (4)
        if d.weekday() in (3, 4):
            weekend_sec += sec
            weekend_days += 1
        else:
            weekday_sec += sec
            weekday_days += 1
    return {
        "weekend_sec": weekend_sec,
        "weekday_sec": weekday_sec,
        "weekend_days": weekend_days,
        "weekday_days": weekday_days,
        "weekend_avg": weekend_sec / weekend_days if weekend_days > 0 else 0,
        "weekday_avg": weekday_sec / weekday_days if weekday_days > 0 else 0,
    }


# =====================================================================
# === TOP ACTIVITIES / CATEGORIES ===
# =====================================================================
def top_categories(start_iso: str, end_iso: str, limit: int = 5) -> list[dict]:
    """Return top N categories by total duration in the range."""
    breakdown = database.seconds_per_category(start_iso, end_iso)
    cats = database.all_categories()
    cat_map = {c["id"]: c for c in cats}
    total = sum(s for _, s in breakdown) or 1
    result = []
    for cid, sec in breakdown[:limit]:
        cat = cat_map.get(cid)
        result.append({
            "category_id": cid,
            "category": cat,
            "seconds": sec,
            "percent": (sec / total * 100) if total > 0 else 0,
        })
    return result


def top_activities_by_title(start_iso: str, end_iso: str, limit: int = 10) -> list[dict]:
    """Return top N activity titles by total duration."""
    rows = database.top_activities(start_iso, end_iso, limit)
    return [{"title": title, "seconds": sec} for title, sec in rows]


# =====================================================================
# === SCORING SYSTEMS ===
# =====================================================================
def productivity_score(start_iso: str, end_iso: str, daily_goal_min: int = 120) -> float:
    """Compute a 0-100 productivity score for the range.
    
    The score is based on how often the daily goal was met:
      - 100 = met goal every day
      - 50 = met goal half the days
      - 0 = never met goal
    """
    per_day = database.seconds_per_day(start_iso, end_iso)
    if not per_day:
        return 0.0
    d1 = date_utils.parse_date(start_iso)
    d2 = date_utils.parse_date(end_iso)
    total_days = (d2 - d1).days + 1
    target_sec = daily_goal_min * 60
    if target_sec <= 0:
        return 0.0
    met_days = sum(1 for sec in per_day.values() if sec >= target_sec)
    return (met_days / total_days * 100) if total_days > 0 else 0.0


def consistency_score(start_iso: str, end_iso: str) -> float:
    """Compute a 0-100 consistency score.
    
    Based on how many distinct days had any activity vs total days.
    """
    per_day = database.seconds_per_day(start_iso, end_iso)
    d1 = date_utils.parse_date(start_iso)
    d2 = date_utils.parse_date(end_iso)
    total_days = (d2 - d1).days + 1
    if total_days <= 0:
        return 0.0
    active_days = len(per_day)
    return (active_days / total_days * 100)


def balance_score(start_iso: str, end_iso: str) -> float:
    """Compute a 0-100 balance score.
    
    Based on how evenly distributed activity is across categories.
    A perfectly balanced distribution (equal time in every category) = 100.
    """
    breakdown = database.seconds_per_category(start_iso, end_iso)
    if not breakdown:
        return 0.0
    total = sum(s for _, s in breakdown) or 1
    n = len(breakdown)
    if n <= 1:
        return 0.0
    # Shannon entropy normalized by max entropy
    import math
    entropy = 0.0
    for _, sec in breakdown:
        p = sec / total
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(n)
    return (entropy / max_entropy * 100) if max_entropy > 0 else 0.0


# =====================================================================
# === INSIGHTS ===
# =====================================================================
def generate_insights(start_iso: str, end_iso: str, lang: str = "fa",
                       daily_goal_min: int = 120) -> list[str]:
    """Generate a list of human-readable insight strings for the range."""
    insights = []
    # Most productive day
    best = database.best_day(start_iso, end_iso)
    if best:
        date_iso, sec = best
        if sec > 0:
            from .date_utils import fmt_date, fmt_human
            d = date_utils.parse_date(date_iso)
            day_str = fmt_date(d, lang)
            insights.append(t("insightMostProductiveDay", lang).format(day_str))
    # Most used category
    top_cats = top_categories(start_iso, end_iso, limit=1)
    if top_cats and top_cats[0]["seconds"] > 0:
        cat = top_cats[0]["category"]
        if cat:
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            insights.append(t("insightMostUsedCategory", lang).format(name))
    # Peak hour
    hour_buckets = hourly_distribution_range(start_iso, end_iso)
    if any(hour_buckets):
        peak_h = max(range(24), key=lambda h: hour_buckets[h])
        h_str = to_fa_digits(f"{peak_h:02d}:00") if lang == "fa" else f"{peak_h:02d}:00"
        insights.append(t("insightPeakHour", lang).format(h_str))
    # Goal progress
    today_total = database.total_seconds_on(date_utils.today_iso())
    target_sec = daily_goal_min * 60
    if target_sec > 0:
        pct = (today_total / target_sec * 100) if target_sec > 0 else 0
        pct_str = f"{pct:.0f}%"
        if lang == "fa":
            pct_str = to_fa_digits(pct_str)
        insights.append(t("insightGoalProgress", lang).format(pct_str))
    # Streak advice
    top_streaks = database.top_streaks(1)
    if not top_streaks or top_streaks[0].get("current", 0) == 0:
        insights.append(t("insightStreakAdvice", lang))
    return insights


# =====================================================================
# === STREAK HEALTH ===
# =====================================================================
def streak_health(streak: dict, lang: str = "fa") -> dict:
    """Assess the health of a streak.
    
    Returns:
      {
        "status": "alive" | "in_danger" | "broken",
        "message": localized status message,
        "days_to_break": int  # how many days until the streak breaks
      }
    """
    today = _dt.date.today()
    last_hit = streak.get("last_hit_date")
    if not last_hit:
        return {
            "status": "broken",
            "message": t("streakBroken", lang),
            "days_to_break": 0,
        }
    try:
        last = _dt.date.fromisoformat(last_hit)
    except ValueError:
        return {"status": "broken", "message": t("streakBroken", lang),
                "days_to_break": 0}
    delta = (today - last).days
    if delta == 0:
        return {"status": "alive", "message": t("keepStreakAlive", lang),
                "days_to_break": 1}
    if delta == 1:
        # Streak is in danger — must log today
        return {"status": "in_danger", "message": t("streakInDanger", lang),
                "days_to_break": 0}
    # delta >= 2: streak is broken
    return {"status": "broken", "message": t("streakBroken", lang),
            "days_to_break": 0}


# =====================================================================
# === SUMMARY BUILDER (used by stats screen + exporters) ===
# =====================================================================
def build_summary(start_iso: str, end_iso: str, lang: str = "fa") -> dict:
    """Build a comprehensive stats summary for the date range."""
    activities = database.activities_by_date_range(start_iso, end_iso)
    total_sec = sum(int(a.get("duration_sec", 0) or 0) for a in activities)
    active_days = len(set(a["date_iso"] for a in activities if a.get("date_iso")))
    # Daily average
    d1 = date_utils.parse_date(start_iso)
    d2 = date_utils.parse_date(end_iso)
    days = (d2 - d1).days + 1
    daily_avg = total_sec / days if days > 0 else 0
    # Best day
    per_day: dict[str, int] = {}
    for a in activities:
        d = a.get("date_iso")
        if d:
            per_day[d] = per_day.get(d, 0) + int(a.get("duration_sec", 0) or 0)
    best_day_iso = max(per_day.items(), key=lambda kv: kv[1])[0] if per_day else None
    best_day_sec = per_day.get(best_day_iso, 0) if best_day_iso else 0
    # Peak hour
    hour_buckets = hourly_distribution_range(start_iso, end_iso)
    peak_hour = max(range(24), key=lambda h: hour_buckets[h]) if any(hour_buckets) else None
    # Peak weekday
    wd_buckets = weekday_distribution(start_iso, end_iso)
    peak_weekday = max(range(7), key=lambda d: wd_buckets[d]) if any(wd_buckets) else None
    # Category breakdown
    cat_breakdown = database.seconds_per_category(start_iso, end_iso)
    # Duration stats
    duration_stats = database.activity_duration_stats(start_iso, end_iso)
    # Previous period comparison
    prev_start, prev_end = previous_period_range(start_iso, end_iso)
    comparison = compare_periods(start_iso, end_iso, prev_start, prev_end)
    # Top categories with details
    top_cats = top_categories(start_iso, end_iso, limit=5)
    # Top activities
    top_acts = top_activities_by_title(start_iso, end_iso, limit=5)
    # Weekend vs weekday
    wkend = weekend_vs_weekday(start_iso, end_iso)
    # Scores
    productivity = productivity_score(start_iso, end_iso)
    consistency = consistency_score(start_iso, end_iso)
    balance = balance_score(start_iso, end_iso)
    # Insights
    insights = generate_insights(start_iso, end_iso, lang)
    return {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "days": days,
        "count": len(activities),
        "total_sec": total_sec,
        "daily_avg_sec": daily_avg,
        "active_days": active_days,
        "best_day": best_day_iso,
        "best_day_sec": best_day_sec,
        "peak_hour": peak_hour,
        "peak_weekday": peak_weekday,
        "category_breakdown": cat_breakdown,
        "duration_stats": duration_stats,
        "comparison": comparison,
        "top_categories": top_cats,
        "top_activities": top_acts,
        "weekend_vs_weekday": wkend,
        "productivity_score": productivity,
        "consistency_score": consistency,
        "balance_score": balance,
        "insights": insights,
        "per_day": per_day,
        "hourly": hour_buckets,
        "weekday": wd_buckets,
    }
