"""
rask.utils.data_analyzer
========================

Data analysis helpers for the Rask desktop app.

Functions
---------

  • ``analyze_patterns(activities)`` — finds time-of-day patterns and
    day-of-week patterns in activity data
  • ``detect_anomalies(activities)`` — finds statistical outliers
  • ``cluster_activities(activities)`` — groups similar activities by
    title similarity
  • ``compute_productivity_score(activities, goals)`` — 0-100 score
    based on goal hits, streak length, time spent, consistency
  • ``find_correlations(activities, journal_entries)`` — activity-mood
    correlations
  • ``forecast(activities, days=7)`` — predicts the next 7 days of
    activity based on historical averages

Example
-------

    >>> from rask.utils.data_analyzer import analyze_patterns
    >>> patterns = analyze_patterns(activities)
    >>> patterns["peak_hour"]
    9
"""
from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core.logging_utils import get_logger
from ..core.time_utils import today_iso, add_days

__all__ = [
    "analyze_patterns",
    "detect_anomalies",
    "cluster_activities",
    "compute_productivity_score",
    "find_correlations",
    "forecast",
]

_log = get_logger("utils.data_analyzer")


# =============================================================================
# === analyze_patterns                                                       ===
# =============================================================================

def analyze_patterns(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Find time-of-day and day-of-week patterns in `activities`.

    Parameters
    ----------
    activities
        List of activity dicts (must have ``date_iso``, ``duration_min``,
        and optionally ``start_ts``).

    Returns
    -------
    dict
        Keys:
          • ``peak_hour``: int (0..23) — hour with most activity-minutes
          • ``peak_weekday``: int (0..6, Mon=0) — weekday with most
          • ``hour_distribution``: dict {hour: total_minutes}
          • ``weekday_distribution``: dict {weekday: total_minutes}
          • ``avg_per_day``: float
          • ``median_per_day``: float
          • ``most_active_dates``: list of (iso, minutes) top 5
    """
    out: Dict[str, Any] = {
        "peak_hour": 0,
        "peak_weekday": 0,
        "hour_distribution": {h: 0 for h in range(24)},
        "weekday_distribution": {w: 0 for w in range(7)},
        "avg_per_day": 0.0,
        "median_per_day": 0.0,
        "most_active_dates": [],
    }
    if not activities:
        return out

    per_day: Dict[str, int] = defaultdict(int)
    for a in activities:
        try:
            dur = int(a.get("duration_min", 0) or 0)
            iso = a.get("date_iso", "")
            if iso:
                per_day[iso] += dur
                d = date.fromisoformat(iso)
                out["weekday_distribution"][d.weekday()] += dur
            # Extract hour from start_ts if present.
            start_ts = a.get("start_ts")
            if start_ts:
                try:
                    # Handle ISO with or without timezone.
                    s = str(start_ts).split("+")[0].rstrip("Z")
                    if "T" in s:
                        hour = int(s.split("T")[1].split(":")[0])
                    else:
                        hour = 0
                    if 0 <= hour < 24:
                        out["hour_distribution"][hour] += dur
                except (ValueError, IndexError):
                    pass
        except Exception:  # noqa: BLE001
            continue

    # Peak hour.
    if any(out["hour_distribution"].values()):
        out["peak_hour"] = max(out["hour_distribution"].items(),
                                key=lambda kv: kv[1])[0]
    # Peak weekday.
    if any(out["weekday_distribution"].values()):
        out["peak_weekday"] = max(out["weekday_distribution"].items(),
                                    key=lambda kv: kv[1])[0]

    # Per-day stats.
    if per_day:
        day_values = list(per_day.values())
        out["avg_per_day"] = sum(day_values) / len(day_values)
        out["median_per_day"] = statistics.median(day_values)
        # Top 5 most active dates.
        sorted_days = sorted(per_day.items(), key=lambda kv: kv[1],
                              reverse=True)[:5]
        out["most_active_dates"] = [
            {"date": d, "minutes": m} for d, m in sorted_days
        ]
    return out


# =============================================================================
# === detect_anomalies                                                       ===
# =============================================================================

def detect_anomalies(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find statistical outliers in activity durations.

    Uses a simple z-score approach: any activity whose duration is
    more than 2 standard deviations from the mean is flagged.

    Returns
    -------
    list of dict
        Each: ``{activity_id, title, duration_min, z_score, anomaly_type}``
        where ``anomaly_type`` is ``"high"`` or ``"low"``.
    """
    if not activities:
        return []
    durations = [int(a.get("duration_min", 0) or 0) for a in activities]
    if len(durations) < 3:
        return []
    mean = statistics.mean(durations)
    stdev = statistics.stdev(durations)
    if stdev == 0:
        return []
    out: List[Dict[str, Any]] = []
    for a, dur in zip(activities, durations):
        z = (dur - mean) / stdev
        if abs(z) > 2.0:
            out.append({
                "activity_id": a.get("id"),
                "title": a.get("title"),
                "duration_min": dur,
                "z_score": round(z, 2),
                "anomaly_type": "high" if z > 0 else "low",
            })
    return out


# =============================================================================
# === cluster_activities                                                     ===
# =============================================================================

def cluster_activities(
    activities: List[Dict[str, Any]],
    *,
    similarity_threshold: float = 0.6,
) -> List[Dict[str, Any]]:
    """Group similar activities by title similarity.

    Uses a simple character-overlap heuristic (Jaccard on character
    bigrams) — fast, no external deps.  Two titles with similarity
    >= `similarity_threshold` are placed in the same cluster.

    Returns
    -------
    list of dict
        Each: ``{representative_title, count, total_minutes, member_titles}``
    """
    if not activities:
        return []

    def _bigrams(s: str) -> set:
        s = (s or "").lower().strip()
        if len(s) < 2:
            return {s} if s else set()
        return {s[i:i + 2] for i in range(len(s) - 1)}

    def _similarity(a: str, b: str) -> float:
        ba, bb = _bigrams(a), _bigrams(b)
        if not ba or not bb:
            return 1.0 if a == b else 0.0
        intersection = len(ba & bb)
        union = len(ba | bb)
        return intersection / union if union else 0.0

    clusters: List[Dict[str, Any]] = []
    for a in activities:
        title = (a.get("title") or "").strip()
        dur = int(a.get("duration_min", 0) or 0)
        # Find a matching cluster.
        matched = None
        for c in clusters:
            if _similarity(title, c["representative_title"]) >= similarity_threshold:
                matched = c
                break
        if matched:
            matched["count"] += 1
            matched["total_minutes"] += dur
            if title not in matched["member_titles"]:
                matched["member_titles"].append(title)
        else:
            clusters.append({
                "representative_title": title,
                "count": 1,
                "total_minutes": dur,
                "member_titles": [title],
            })
    # Sort by total minutes descending.
    clusters.sort(key=lambda c: c["total_minutes"], reverse=True)
    return clusters


# =============================================================================
# === compute_productivity_score                                             ===
# =============================================================================

def compute_productivity_score(
    activities: List[Dict[str, Any]],
    goals: Optional[List[Dict[str, Any]]] = None,
    *,
    daily_target_min: int = 120,
) -> Dict[str, Any]:
    """Compute a 0-100 productivity score for the given activities.

    Score components (weighted):

      • **Time spent** (40%): ratio of total time to daily_target_min,
        averaged over the activity period.
      • **Consistency** (30%): fraction of days with at least one activity.
      • **Goal hits** (20%): ratio of goal-hit days to total days.
      • **Variety** (10%): ratio of distinct categories used to total
        categories.

    Returns
    -------
    dict
        ``{score, breakdown: {time, consistency, goals, variety},
        total_min, days_active, day_count}``
    """
    if not activities:
        return {
            "score": 0,
            "breakdown": {"time": 0, "consistency": 0, "goals": 0, "variety": 0},
            "total_min": 0,
            "days_active": 0,
            "day_count": 0,
        }

    # Per-day totals.
    per_day: Dict[str, int] = defaultdict(int)
    categories_used: set = set()
    total_min = 0
    for a in activities:
        dur = int(a.get("duration_min", 0) or 0)
        iso = a.get("date_iso", "")
        if iso:
            per_day[iso] += dur
        total_min += dur
        if a.get("category_id"):
            categories_used.add(a["category_id"])

    day_count = len(per_day) if per_day else 1
    days_active = sum(1 for v in per_day.values() if v > 0)

    # Time component (0..1).
    avg_per_day = total_min / day_count if day_count else 0
    time_score = min(1.0, avg_per_day / daily_target_min)

    # Consistency (0..1).
    # Find the date range.
    if per_day:
        min_date = min(per_day.keys())
        max_date = max(per_day.keys())
        try:
            d1 = date.fromisoformat(min_date)
            d2 = date.fromisoformat(max_date)
            span_days = max(1, (d2 - d1).days + 1)
        except ValueError:
            span_days = day_count
    else:
        span_days = 1
    consistency_score = days_active / span_days if span_days else 0

    # Goal hits (0..1).
    goal_hit_days = sum(1 for v in per_day.values()
                         if v >= daily_target_min)
    goals_score = goal_hit_days / span_days if span_days else 0

    # Variety (0..1).
    total_categories = 7  # default
    if goals:
        # Could compute from config.DEFAULT_CATEGORIES, but use 7 default.
        pass
    variety_score = min(1.0, len(categories_used) / total_categories)

    # Weighted sum.
    score = (
        time_score * 40 +
        consistency_score * 30 +
        goals_score * 20 +
        variety_score * 10
    )

    return {
        "score": round(score, 1),
        "breakdown": {
            "time": round(time_score, 3),
            "consistency": round(consistency_score, 3),
            "goals": round(goals_score, 3),
            "variety": round(variety_score, 3),
        },
        "total_min": total_min,
        "days_active": days_active,
        "day_count": day_count,
    }


# =============================================================================
# === find_correlations                                                      ===
# =============================================================================

def find_correlations(
    activities: List[Dict[str, Any]],
    journal_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find correlations between activity categories and mood.

    For each category, computes the average mood on days where the
    category was used vs days where it wasn't.  A positive delta
    means the category is associated with better mood.

    Returns
    -------
    list of dict
        Each: ``{category_id, avg_mood_with, avg_mood_without, delta,
        sample_count}``
    """
    if not activities or not journal_entries:
        return []

    # Map: date_iso -> mood (from journal entries).
    mood_by_date: Dict[str, float] = {}
    for e in journal_entries:
        iso = e.get("date_iso") if isinstance(e, dict) else getattr(e, "date_iso", None)
        mood = e.get("mood") if isinstance(e, dict) else getattr(e, "mood", None)
        if iso and mood is not None:
            try:
                mood_by_date[iso] = float(mood)
            except (TypeError, ValueError):
                pass

    # Map: category_id -> list of dates where it was used.
    cat_dates: Dict[Any, set] = defaultdict(set)
    for a in activities:
        cid = a.get("category_id")
        iso = a.get("date_iso")
        if cid and iso:
            cat_dates[cid].add(iso)

    out: List[Dict[str, Any]] = []
    all_moods = list(mood_by_date.values())
    overall_avg = sum(all_moods) / len(all_moods) if all_moods else 0
    for cid, dates in cat_dates.items():
        moods_with = [mood_by_date[d] for d in dates if d in mood_by_date]
        moods_without = [m for iso, m in mood_by_date.items()
                          if iso not in dates]
        avg_with = (sum(moods_with) / len(moods_with)
                     if moods_with else 0)
        avg_without = (sum(moods_without) / len(moods_without)
                        if moods_without else overall_avg)
        delta = avg_with - avg_without if moods_with else 0
        out.append({
            "category_id": cid,
            "avg_mood_with": round(avg_with, 2),
            "avg_mood_without": round(avg_without, 2),
            "delta": round(delta, 2),
            "sample_count": len(moods_with),
        })
    # Sort by absolute delta descending.
    out.sort(key=lambda c: abs(c["delta"]), reverse=True)
    return out


# =============================================================================
# === forecast                                                               ===
# =============================================================================

def forecast(
    activities: List[Dict[str, Any]],
    days: int = 7,
) -> List[Dict[str, Any]]:
    """Predict the next `days` of activity based on historical averages.

    The forecast is a per-weekday average: for each future day, we
    compute the average minutes spent on that weekday in the historical
    data.

    Returns
    -------
    list of dict
        Each: ``{date_iso, weekday, predicted_minutes, confidence}``
        where ``confidence`` is "high" if >= 30 days of historical data,
        "medium" if >= 7, "low" otherwise.
    """
    if days < 1 or days > 90:
        raise ValueError(f"days must be 1..90, got {days}")

    # Per-weekday totals.
    weekday_totals: Dict[int, int] = defaultdict(int)
    weekday_counts: Dict[int, int] = defaultdict(int)
    for a in activities:
        iso = a.get("date_iso")
        dur = int(a.get("duration_min", 0) or 0)
        if iso:
            try:
                d = date.fromisoformat(iso)
                weekday_totals[d.weekday()] += dur
                weekday_counts[d.weekday()] += 1
            except ValueError:
                pass

    # Confidence based on total sample size.
    total_samples = sum(weekday_counts.values())
    if total_samples >= 30:
        confidence = "high"
    elif total_samples >= 7:
        confidence = "medium"
    else:
        confidence = "low"

    out: List[Dict[str, Any]] = []
    today = date.today()
    for i in range(days):
        d = today + timedelta(days=i + 1)  # start tomorrow
        wd = d.weekday()
        if weekday_counts[wd] > 0:
            avg = weekday_totals[wd] / weekday_counts[wd]
        else:
            # No data for this weekday — use overall average.
            total_avg = (sum(weekday_totals.values()) /
                          max(1, sum(weekday_counts.values())))
            avg = total_avg
        out.append({
            "date_iso": d.isoformat(),
            "weekday": wd,
            "predicted_minutes": round(avg, 1),
            "confidence": confidence,
        })
    return out


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.data_analyzer``."""
    from .. import database as db
    activities = db.activity_list(limit=10000)
    print(f"Loaded {len(activities)} activities.")
    if not activities:
        print("No activities to analyze.  Run seed_demo_data first.")
        return 1
    patterns = analyze_patterns(activities)
    print(f"\nPatterns:")
    print(f"  Peak hour: {patterns['peak_hour']}:00")
    print(f"  Peak weekday: {patterns['peak_weekday']}")
    print(f"  Avg per day: {patterns['avg_per_day']:.0f} min")
    print(f"  Median per day: {patterns['median_per_day']:.0f} min")

    anomalies = detect_anomalies(activities)
    print(f"\nAnomalies: {len(anomalies)}")
    for a in anomalies[:5]:
        print(f"  {a['title']!r} ({a['duration_min']} min, z={a['z_score']})")

    clusters = cluster_activities(activities)
    print(f"\nTop 5 activity clusters:")
    for c in clusters[:5]:
        print(f"  {c['representative_title']!r}: "
              f"{c['count']} activities, {c['total_minutes']} min")

    score = compute_productivity_score(activities)
    print(f"\nProductivity score: {score['score']}/100")
    print(f"  Breakdown: {score['breakdown']}")

    forecast_result = forecast(activities, days=7)
    print(f"\n7-day forecast:")
    for f in forecast_result:
        print(f"  {f['date_iso']} (weekday {f['weekday']}): "
              f"{f['predicted_minutes']:.0f} min ({f['confidence']})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
