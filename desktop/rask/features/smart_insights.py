"""
rask.features.smart_insights
============================

AI-like insight engine for Rask.

This module runs a battery of "insight generators" over the user's
activity, goal, mood, journal, and habit data and returns a list of
:class:`Insight` objects, each with a Persian title, body, kind
(info/warning/success/achievement), and an optional action.

The engine is intentionally rule-based (no ML, no network calls) —
fast, deterministic, and explainable.  Each generator is a method
that returns a single :class:`Insight` (or a list for
:math:`generate_recommendations` and :math:`generate_anomalies`).

Generators
----------

  • ``generate_personality()``         — labels the user "Night Owl",
                                          "Early Bird", "Polymath", etc.
  • ``generate_productivity_score()``  — 0..100 score with breakdown
  • ``generate_best_times()``          — best time of day, best day of week
  • ``generate_top_categories()``      — top 3 categories with trends
  • ``generate_streak_analysis()``     — current vs best streak
  • ``generate_weekly_comparison()``   — this week vs last week
  • ``generate_goals_analysis()``      — which goals on track, behind
  • ``generate_recommendations()``     — actionable recommendations
  • ``generate_anomalies()``           — unusual patterns
  • ``generate_seasonal_trends()``     — month-over-month trends

Caching
-------

Results are cached for 5 minutes per generator (configurable via
:meth:`InsightEngine.set_cache_ttl`).  Use :meth:`invalidate` to
force a recompute.

Events
------

  ``insights.computed``  — {count, generated_at}
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    days_between,
    end_of_week,
    start_of_week,
    today_iso,
)

__all__ = [
    "Insight",
    "InsightEngine",
    "insight_engine",
    "KIND_INFO",
    "KIND_WARNING",
    "KIND_SUCCESS",
    "KIND_ACHIEVEMENT",
]

_log = get_logger("features.insights")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

KIND_INFO: str = "info"
KIND_WARNING: str = "warning"
KIND_SUCCESS: str = "success"
KIND_ACHIEVEMENT: str = "achievement"

#: Categories used for the Insight.category field.
CAT_PERSONALITY: str = "personality"
CAT_PRODUCTIVITY: str = "productivity"
CAT_TIMING: str = "timing"
CAT_CATEGORIES: str = "categories"
CAT_STREAK: str = "streak"
CAT_COMPARISON: str = "comparison"
CAT_GOALS: str = "goals"
CAT_RECOMMENDATION: str = "recommendation"
CAT_ANOMALY: str = "anomaly"
CAT_SEASONAL: str = "seasonal"

#: Default cache TTL (seconds).
DEFAULT_CACHE_TTL: int = 300  # 5 minutes


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class Insight:
    """A single insight produced by the engine."""

    id: str
    title: str
    body: str
    kind: str = KIND_INFO                # info/warning/success/achievement
    category: str = ""                  # personality/productivity/...
    score: Optional[int] = None         # 0..100 (optional)
    actionable: bool = False
    action_text: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    fa_digits: bool = True              # localize numbers in fa

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _fa(value: Any) -> str:
    """Localize a number/date to Persian digits."""
    return i18n.to_fa_digits(value)


def _weekday_name_fa(weekday_py: int) -> str:
    """Convert Python weekday (Mon=0..Sun=6) to Persian name."""
    names = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
             "جمعه", "شنبه", "یکشنبه"]
    return names[weekday_py % 7]


def _hour_label_fa(hour: int) -> str:
    """Return a Persian label for a 0..23 hour bucket."""
    if 5 <= hour < 12:
        return f"صبح ({_fa(hour)}-{_fa((hour + 1) % 24)})"
    if 12 <= hour < 17:
        return f"ظهر ({_fa(hour)}-{_fa((hour + 1) % 24)})"
    if 17 <= hour < 21:
        return f"عصر ({_fa(hour)}-{_fa((hour + 1) % 24)})"
    return f"شب ({_fa(hour)}-{_fa((hour + 1) % 24)})"


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


# =============================================================================
# === InsightEngine                                                          ===
# =============================================================================

class InsightEngine:
    """Rule-based insight engine.

    Module-level singleton :data:`insight_engine` is the instance to
    use.  All generators are safe to call from any thread; each
    returns a fresh :class:`Insight` instance.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, value)
        self._cache_ttl: int = DEFAULT_CACHE_TTL

    # ------------------------------------------------------------------
    # Cache control
    # ------------------------------------------------------------------

    def set_cache_ttl(self, ttl_sec: int) -> None:
        self._cache_ttl = max(0, int(ttl_sec))

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._cache.clear()
            else:
                self._cache.pop(key, None)

    def _cached(self, key: str, fn: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                ts, val = entry
                if now - ts < self._cache_ttl:
                    return val
        val = fn()
        with self._lock:
            self._cache[key] = (now, val)
        return val

    # ------------------------------------------------------------------
    # Public: generate_all
    # ------------------------------------------------------------------

    def generate_all(self) -> List[Insight]:
        """Run every generator and return a flat list of insights."""
        def _compute() -> List[Insight]:
            out: List[Insight] = []
            try:
                out.append(self.generate_personality())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "personality"})
            try:
                out.append(self.generate_productivity_score())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "productivity_score"})
            try:
                out.append(self.generate_best_times())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "best_times"})
            try:
                out.append(self.generate_top_categories())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "top_categories"})
            try:
                out.append(self.generate_streak_analysis())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "streak"})
            try:
                out.append(self.generate_weekly_comparison())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "weekly_comparison"})
            try:
                out.append(self.generate_goals_analysis())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "goals"})
            try:
                out.extend(self.generate_recommendations())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "recommendations"})
            try:
                out.extend(self.generate_anomalies())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "anomalies"})
            try:
                out.append(self.generate_seasonal_trends())
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"generator": "seasonal"})
            # Filter out None.
            out = [i for i in out if i is not None]
            bus.publish("insights.computed",
                        {"count": len(out), "generated_at": today_iso()})
            return out
        return self._cached("all", _compute)

    # ------------------------------------------------------------------
    # Personality
    # ------------------------------------------------------------------

    def generate_personality(self) -> Insight:
        """Analyze activity patterns and label the user with a "type"."""
        def _compute() -> Insight:
            try:
                today = today_iso()
                date_from = add_days(today, -29)
                by_hour = db.activity_group_by_hour(date_from=date_from,
                                                     date_to=today)
                # Determine peak hour.
                peak_hour = 9
                peak_min = 0
                for r in by_hour:
                    if int(r.get("total_min") or 0) > peak_min:
                        peak_min = int(r["total_min"])
                        peak_hour = int(r["hour"])
                # Classify.
                if 5 <= peak_hour < 9:
                    label = "سحرخیز"  # Early Bird
                    body = (f"بیشترین فعالیت تو بین ساعت {_fa(peak_hour)} تا "
                            f"{_fa((peak_hour + 1) % 24)} صبح بوده. تو یک سحرخیزی؛ "
                            "از انرژی صبح برای کارهای سخت استفاده کن.")
                elif 9 <= peak_hour < 12:
                    label = "صبح‌کار"
                    body = (f"اوج فعالیت تو در صبح ({_fa(peak_hour)}-{_fa((peak_hour + 1) % 24)}). "
                            "این زمان طلایی‌ترین ساعت روزت است.")
                elif 12 <= peak_hour < 17:
                    label = "بعدازظهرکار"
                    body = (f"اوج فعالیت تو در بعدازظهر است ({_fa(peak_hour)}-"
                            f"{_fa((peak_hour + 1) % 24)}).")
                elif 17 <= peak_hour < 21:
                    label = "عصرکار"
                    body = (f"بیشترین فعالیتت عصرها است ({_fa(peak_hour)}-"
                            f"{_fa((peak_hour + 1) % 24)}).")
                else:
                    label = "شب‌بیدار"  # Night Owl
                    body = (f"تو یک شب‌بیداری! اوج فعالیتت بین {_fa(peak_hour)} تا "
                            f"{_fa((peak_hour + 1) % 24)} است.")

                # Also check breadth of categories.
                by_cat = db.activity_group_by_category(date_from=date_from,
                                                        date_to=today)
                distinct_cats = sum(1 for r in by_cat if int(r.get("total_min") or 0) > 0)
                if distinct_cats >= 6:
                    body += " علاوه بر این، تو در دسته‌های زیادی فعال هستی — یک ذهن چندگانه (Polymath) داری."
                return Insight(
                    id="personality",
                    title=f"نوع شخصیتی تو: {label}",
                    body=body,
                    kind=KIND_INFO,
                    category=CAT_PERSONALITY,
                    score=None,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="personality", title="نوع شخصیتی",
                                body="اطلاعات کافی برای تحلیل نیست.",
                                kind=KIND_INFO, category=CAT_PERSONALITY)
        return self._cached("personality", _compute)

    # ------------------------------------------------------------------
    # Productivity score
    # ------------------------------------------------------------------

    def generate_productivity_score(self) -> Insight:
        """Compute a 0..100 productivity score with breakdown."""
        def _compute() -> Insight:
            try:
                today = today_iso()
                date_from = add_days(today, -6)  # last 7 days
                total_min = db.activity_sum_duration(date_from=date_from,
                                                      date_to=today)
                count = db.activity_count(date_from=date_from, date_to=today)

                # Components:
                #   1. Total time (0..30 pts): 600+ min = 30 pts
                #   2. Activity count (0..20 pts): 20+ = 20 pts
                #   3. Consistency (0..25 pts): days with activity / 7 * 25
                #   4. Goal hit rate (0..25 pts): derived from streak
                pts_time = min(30, int(total_min / 20))
                pts_count = min(20, int(count / 1))
                # Consistency: count distinct days with activity
                by_day = db.activity_group_by_day(date_from=date_from,
                                                   date_to=today)
                distinct_days = len(by_day)
                pts_consistency = int(distinct_days / 7 * 25)
                # Goal hit rate
                from ..services.goal_service import goal_service
                goals = goal_service.list(only_active=True)
                pts_goals = 0
                if goals:
                    hits = 0
                    for g in goals:
                        if goal_service.hit_today(g["id"]):
                            hits += 1
                    pts_goals = int(hits / len(goals) * 25)
                else:
                    pts_goals = 12  # neutral

                total = pts_time + pts_count + pts_consistency + pts_goals
                total = max(0, min(100, total))
                kind = (KIND_ACHIEVEMENT if total >= 80
                        else KIND_SUCCESS if total >= 60
                        else KIND_INFO if total >= 40
                        else KIND_WARNING)
                body = (f"امتیاز بهره‌وری تو در ۷ روز گذشته: {_fa(total)}/۱۰۰\n\n"
                        f"• زمان فعالیت: {_fa(pts_time)}/۳۰ ({_fa(total_min)} دقیقه)\n"
                        f"• تعداد فعالیت: {_fa(pts_count)}/۲۰ ({_fa(count)} مورد)\n"
                        f"• استمرار: {_fa(pts_consistency)}/۲۵ ({_fa(distinct_days)} از ۷ روز)\n"
                        f"• اهداف: {_fa(pts_goals)}/۲۵")
                return Insight(
                    id="productivity_score",
                    title="امتیاز بهره‌وری",
                    body=body,
                    kind=kind,
                    category=CAT_PRODUCTIVITY,
                    score=total,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="productivity_score",
                                title="امتیاز بهره‌وری",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_PRODUCTIVITY)
        return self._cached("productivity_score", _compute)

    # ------------------------------------------------------------------
    # Best times
    # ------------------------------------------------------------------

    def generate_best_times(self) -> Insight:
        """Identify the best time of day and best day of week."""
        def _compute() -> Insight:
            try:
                today = today_iso()
                date_from = add_days(today, -89)  # 90 days
                by_hour = db.activity_group_by_hour(date_from=date_from,
                                                     date_to=today)
                by_wday = db.activity_group_by_weekday(date_from=date_from,
                                                        date_to=today)
                best_hour = 9
                best_hour_min = 0
                for r in by_hour:
                    if int(r.get("total_min") or 0) > best_hour_min:
                        best_hour_min = int(r["total_min"])
                        best_hour = int(r["hour"])
                best_wday = 0
                best_wday_min = 0
                for r in by_wday:
                    if int(r.get("total_min") or 0) > best_wday_min:
                        best_wday_min = int(r["total_min"])
                        # DB returns Sun=0..Sat=6 — convert to Python Mon=0..Sun=6
                        wday_py = (int(r["weekday"]) - 1) % 7
                        best_wday = wday_py
                body = (f"بهترین ساعت روز تو: {_hour_label_fa(best_hour)} "
                        f"با {_fa(best_hour_min)} دقیقه فعالیت\n\n"
                        f"بهترین روز هفته تو: {_weekday_name_fa(best_wday)} "
                        f"با {_fa(best_wday_min)} دقیقه فعالیت.\n\n"
                        "پیشنهاد: کارهای سخت را در این بازه‌ها قرار بده.")
                return Insight(
                    id="best_times",
                    title="بهترین زمان‌های تو",
                    body=body,
                    kind=KIND_INFO,
                    category=CAT_TIMING,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="best_times", title="بهترین زمان‌ها",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_TIMING)
        return self._cached("best_times", _compute)

    # ------------------------------------------------------------------
    # Top categories
    # ------------------------------------------------------------------

    def generate_top_categories(self) -> Insight:
        """Top 3 categories with trend arrows."""
        def _compute() -> Insight:
            try:
                today = today_iso()
                date_from = add_days(today, -29)
                by_cat = db.activity_group_by_category(date_from=date_from,
                                                        date_to=today)
                cats = db.category_list()
                cat_map = {int(c["id"]): c for c in cats}
                # Sort by total_min desc
                sorted_cats = sorted(by_cat,
                                      key=lambda r: int(r.get("total_min") or 0),
                                      reverse=True)[:3]
                # Compute trend vs previous 30 days
                prev_from = add_days(today, -59)
                prev_to = add_days(today, -30)
                by_cat_prev = db.activity_group_by_category(date_from=prev_from,
                                                              date_to=prev_to)
                prev_map = {int(r["category_id"]): int(r.get("total_min") or 0)
                            for r in by_cat_prev}
                lines: List[str] = []
                for r in sorted_cats:
                    cid = int(r["category_id"] or 0)
                    name = (cat_map.get(cid, {}).get("name_fa")
                            or cat_map.get(cid, {}).get("name_en")
                            or "—")
                    cur = int(r.get("total_min") or 0)
                    prev = prev_map.get(cid, 0)
                    if prev == 0:
                        arrow = "🆕"
                    elif cur > prev * 1.1:
                        arrow = "▲"
                    elif cur < prev * 0.9:
                        arrow = "▼"
                    else:
                        arrow = "—"
                    lines.append(f"• {name}: {_fa(cur)} دقیقه {arrow}")
                body = "سه دسته برتر تو در ۳۰ روز گذشته:\n\n" + "\n".join(lines)
                return Insight(
                    id="top_categories",
                    title="دسته‌های برتر",
                    body=body,
                    kind=KIND_INFO,
                    category=CAT_CATEGORIES,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="top_categories", title="دسته‌های برتر",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_CATEGORIES)
        return self._cached("top_categories", _compute)

    # ------------------------------------------------------------------
    # Streak analysis
    # ------------------------------------------------------------------

    def generate_streak_analysis(self) -> Insight:
        """Current vs best streak with motivational text."""
        def _compute() -> Insight:
            try:
                from ..services.stats_service import stats_service
                current = stats_service.current_streak()
                best = stats_service.longest_streak_ever()
                if current == 0:
                    body = ("زنجیره فعلیت شکسته شده. امروز یک فعالیت ثبت کن تا "
                            "زنجیره جدیدی را شروع کنی! 🔥")
                    kind = KIND_WARNING
                elif current >= best and best > 0:
                    body = (f"🎉 تبریک! تو رکوردت را شکستی: {_fa(current)} روز "
                            "زنجیره فعال!")
                    kind = KIND_ACHIEVEMENT
                elif current >= 30:
                    body = (f"عالی! {_fa(current)} روز زنجیره فعال. بهترین رکوردت: "
                            f"{_fa(best)} روز. ادامه بده!")
                    kind = KIND_SUCCESS
                else:
                    body = (f"زنجیره فعلیت: {_fa(current)} روز. بهترین رکورد: "
                            f"{_fa(best)} روز. هر روز یک قدم!")
                    kind = KIND_INFO
                return Insight(
                    id="streak_analysis",
                    title="تحلیل زنجیره",
                    body=body,
                    kind=kind,
                    category=CAT_STREAK,
                    score=current,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="streak_analysis", title="تحلیل زنجیره",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_STREAK)
        return self._cached("streak_analysis", _compute)

    # ------------------------------------------------------------------
    # Weekly comparison
    # ------------------------------------------------------------------

    def generate_weekly_comparison(self) -> Insight:
        """Compare this week vs last week."""
        def _compute() -> Insight:
            try:
                today = today_iso()
                this_start = start_of_week(today, first_day=6)
                this_end = end_of_week(today, first_day=6)
                last_start = add_days(this_start, -7)
                last_end = add_days(this_end, -7)
                this_min = db.activity_sum_duration(date_from=this_start,
                                                     date_to=this_end)
                last_min = db.activity_sum_duration(date_from=last_start,
                                                     date_to=last_end)
                delta = this_min - last_min
                if last_min == 0:
                    pct = 100 if this_min > 0 else 0
                else:
                    pct = int(round(delta / last_min * 100))
                if delta > 0:
                    body = (f"این هفته {_fa(this_min)} دقیقه فعالیت داشته‌ای — "
                            f"{_fa(delta)} دقیقه بیشتر از هفته گذشته "
                            f"(+{_fa(pct)}٪). 👏")
                    kind = KIND_SUCCESS
                elif delta < 0:
                    body = (f"این هفته {_fa(this_min)} دقیقه — {_fa(abs(delta))} "
                            f"دقیقه کمتر از هفته گذشته ({_fa(abs(pct))}٪). "
                            "هفته بعد را قوی‌تر برگردان!")
                    kind = KIND_WARNING
                else:
                    body = (f"این هفته و هفته گذشته هر کدام {_fa(this_min)} "
                            "دقیقه فعالیت. ثابت قدم باش!")
                    kind = KIND_INFO
                return Insight(
                    id="weekly_comparison",
                    title="مقایسه هفتگی",
                    body=body,
                    kind=kind,
                    category=CAT_COMPARISON,
                    score=pct,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="weekly_comparison", title="مقایسه هفتگی",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_COMPARISON)
        return self._cached("weekly_comparison", _compute)

    # ------------------------------------------------------------------
    # Goals analysis
    # ------------------------------------------------------------------

    def generate_goals_analysis(self) -> Insight:
        """Which goals are on-track vs behind."""
        def _compute() -> Insight:
            try:
                from ..services.goal_service import goal_service
                goals = goal_service.list(only_active=True)
                if not goals:
                    return Insight(id="goals_analysis", title="تحلیل اهداف",
                                    body="هنوز هدفی تعریف نکرده‌ای. یک هدف روزانه بساز!",
                                    kind=KIND_INFO, category=CAT_GOALS,
                                    actionable=True,
                                    action_text="ایجاد هدف",
                                    action_payload={"action": "open_goals"})
                on_track: List[str] = []
                behind: List[str] = []
                for g in goals:
                    progress = goal_service.progress_for(g["id"])
                    pct = int((progress.get("ratio") or progress.get("progress") or 0) * 100)
                    name = (g.get("title")
                            or (f"هدف {g.get('period')}")
                            or "هدف")
                    if pct >= 80:
                        on_track.append(f"{name} ({_fa(pct)}٪)")
                    elif pct < 50:
                        behind.append(f"{name} ({_fa(pct)}٪)")
                lines: List[str] = []
                if on_track:
                    lines.append("✅ در مسیر: " + "، ".join(on_track))
                if behind:
                    lines.append("⚠️ عقب افتاده: " + "، ".join(behind))
                if not lines:
                    lines.append("همه اهداف در حالت میانه هستند.")
                body = "\n".join(lines)
                kind = (KIND_WARNING if behind and not on_track
                        else KIND_SUCCESS if on_track and not behind
                        else KIND_INFO)
                return Insight(
                    id="goals_analysis",
                    title="تحلیل اهداف",
                    body=body,
                    kind=kind,
                    category=CAT_GOALS,
                    actionable=bool(behind),
                    action_text="مشاهده اهداف" if behind else None,
                    action_payload={"action": "open_goals"} if behind else None,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="goals_analysis", title="تحلیل اهداف",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_GOALS)
        return self._cached("goals_analysis", _compute)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(self) -> List[Insight]:
        """Actionable recommendations based on recent activity."""
        def _compute() -> List[Insight]:
            out: List[Insight] = []
            try:
                today = today_iso()
                date_from = add_days(today, -6)
                total_min = db.activity_sum_duration(date_from=date_from,
                                                      date_to=today)
                count = db.activity_count(date_from=date_from, date_to=today)
                if total_min == 0:
                    out.append(Insight(
                        id="rec_no_activity",
                        title="شروع کن",
                        body="هفته‌ات را با ثبت اولین فعالیت شروع کن. حتی ۵ دقیقه می‌تواند زنجیره‌ای بسازد.",
                        kind=KIND_WARNING,
                        category=CAT_RECOMMENDATION,
                        actionable=True,
                        action_text="ثبت سریع",
                        action_payload={"action": "quick_log"},
                    ))
                elif count < 7:
                    out.append(Insight(
                        id="rec_more_frequent",
                        title="بیشتر پخش کن",
                        body="سعی کن هر روز حداقل یک فعالیت ثبت کنی. استمرار مهم‌تر از مدت است.",
                        kind=KIND_INFO,
                        category=CAT_RECOMMENDATION,
                    ))
                # Check categories diversity
                by_cat = db.activity_group_by_category(date_from=date_from,
                                                        date_to=today)
                distinct = sum(1 for r in by_cat if int(r.get("total_min") or 0) > 0)
                if distinct <= 2 and total_min > 60:
                    out.append(Insight(
                        id="rec_diversify",
                        title="تنوع بده",
                        body="تو روی یک یا دو دسته متمرکز هستی. سعی کن یک فعالیت از دسته متفاوت ثبت کنی.",
                        kind=KIND_INFO,
                        category=CAT_RECOMMENDATION,
                    ))
                # Check goals
                from ..services.goal_service import goal_service
                goals = goal_service.list(only_active=True)
                if not goals:
                    out.append(Insight(
                        id="rec_set_goal",
                        title="هدف تعیین کن",
                        body="بدون هدف، پیشرفت سخت است. یک هدف روزانه ۱۲۰ دقیقه‌ای بساز.",
                        kind=KIND_INFO,
                        category=CAT_RECOMMENDATION,
                        actionable=True,
                        action_text="ایجاد هدف",
                        action_payload={"action": "open_goals"},
                    ))
                # Mood correlation
                try:
                    from .mood_tracker import mood_service
                    mood_corr = mood_service.correlation_with_activities()
                    by_cat_list = mood_corr.get("by_category", [])
                    if by_cat_list:
                        top = by_cat_list[0]
                        if top.get("delta", 0) >= 0.4:
                            out.append(Insight(
                                id="rec_mood_correlation",
                                title="فعالیت‌های خوب برای حالت",
                                body=(f"بعد از «{top['category_name']}» حالت بهتر می‌شود "
                                      f"(میانگین: {_fa(top['avg_mood'])}/۵). "
                                      "روزت را با این دسته شروع کن!"),
                                kind=KIND_SUCCESS,
                                category=CAT_RECOMMENDATION,
                            ))
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
            return out
        return self._cached("recommendations", _compute)

    # ------------------------------------------------------------------
    # Anomalies
    # ------------------------------------------------------------------

    def generate_anomalies(self) -> List[Insight]:
        """Detect unusual patterns."""
        def _compute() -> List[Insight]:
            out: List[Insight] = []
            try:
                today = today_iso()
                date_from = add_days(today, -29)
                by_day = db.activity_group_by_day(date_from=date_from,
                                                   date_to=today)
                if len(by_day) >= 7:
                    mins = [int(r.get("total_min") or 0) for r in by_day]
                    avg = sum(mins) / len(mins)
                    # Very low day
                    for r in by_day:
                        m = int(r.get("total_min") or 0)
                        if m == 0 and r["date_iso"] != today:
                            out.append(Insight(
                                id=f"anomaly_zero_{r['date_iso']}",
                                title="روز بدون فعالیت",
                                body=(f"در {_fa(r['date_iso'])} هیچ فعالیتی ثبت نکردی. "
                                      "آیا اتفاق خاصی افتاده بود؟"),
                                kind=KIND_WARNING,
                                category=CAT_ANOMALY,
                            ))
                            break
                    # Very high day
                    for r in by_day:
                        m = int(r.get("total_min") or 0)
                        if avg > 0 and m > avg * 2.5 and m > 60:
                            out.append(Insight(
                                id=f"anomaly_high_{r['date_iso']}",
                                title="روز فوق‌العاده!",
                                body=(f"در {_fa(r['date_iso'])} {_fa(m)} دقیقه فعالیت داشتی — "
                                      f"{_fa(int(m / avg))} برابر میانگینت! 🎉"),
                                kind=KIND_ACHIEVEMENT,
                                category=CAT_ANOMALY,
                            ))
                            break
                # Category spike
                by_cat = db.activity_group_by_category(date_from=date_from,
                                                        date_to=today)
                prev_from = add_days(today, -59)
                prev_to = add_days(today, -30)
                by_cat_prev = db.activity_group_by_category(date_from=prev_from,
                                                              date_to=prev_to)
                prev_map = {int(r["category_id"]): int(r.get("total_min") or 0)
                            for r in by_cat_prev}
                cats = db.category_list()
                cat_map = {int(c["id"]): c for c in cats}
                for r in by_cat:
                    cid = int(r["category_id"] or 0)
                    cur = int(r.get("total_min") or 0)
                    prev = prev_map.get(cid, 0)
                    if prev > 0 and cur > prev * 2 and cur > 30:
                        name = (cat_map.get(cid, {}).get("name_fa")
                                or cat_map.get(cid, {}).get("name_en")
                                or "—")
                        out.append(Insight(
                            id=f"anomaly_cat_spike_{cid}",
                            title="رشد دسته",
                            body=(f"زمان صرف‌شتی برای «{name}» نسبت به ماه قبل "
                                  f"{_fa(int((cur / prev - 1) * 100))}٪ افزایش داشته."),
                            kind=KIND_SUCCESS,
                            category=CAT_ANOMALY,
                        ))
                        break
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
            return out
        return self._cached("anomalies", _compute)

    # ------------------------------------------------------------------
    # Seasonal trends
    # ------------------------------------------------------------------

    def generate_seasonal_trends(self) -> Insight:
        """Month-over-month trends."""
        def _compute() -> Insight:
            try:
                by_month = db.activity_group_by_month()
                if len(by_month) < 2:
                    return Insight(id="seasonal_trends",
                                    title="روند فصلی",
                                    body="برای تحلیل روند ماهانه، حداقل به دو ماه داده نیاز است.",
                                    kind=KIND_INFO, category=CAT_SEASONAL)
                # Take last 3 months.
                recent = by_month[-3:]
                lines: List[str] = []
                for r in recent:
                    lines.append(f"• {r['month']}: {_fa(int(r['total_min'] or 0))} دقیقه "
                                  f"({_fa(int(r['count'] or 0))} فعالیت)")
                # Trend
                if len(recent) >= 2:
                    last = int(recent[-1].get("total_min") or 0)
                    prev = int(recent[-2].get("total_min") or 0)
                    if prev == 0:
                        trend = "🆕"
                    elif last > prev * 1.1:
                        trend = "▲ در حال رشد"
                    elif last < prev * 0.9:
                        trend = "▼ در حال کاهش"
                    else:
                        trend = "— پایدار"
                else:
                    trend = "—"
                body = "روند ۳ ماه اخیر:\n\n" + "\n".join(lines) + f"\n\nروند: {trend}"
                return Insight(
                    id="seasonal_trends",
                    title="روند فصلی",
                    body=body,
                    kind=KIND_INFO,
                    category=CAT_SEASONAL,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                return Insight(id="seasonal_trends", title="روند فصلی",
                                body="اطلاعات کافی نیست.",
                                kind=KIND_INFO, category=CAT_SEASONAL)
        return self._cached("seasonal_trends", _compute)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

insight_engine: InsightEngine = InsightEngine()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== smart_insights self-tests ===")
    try:
        insights = insight_engine.generate_all()
        assert isinstance(insights, list)
        # Each insight has required fields
        for i in insights:
            assert isinstance(i, Insight)
            assert i.id and i.title and i.body and i.kind in (
                KIND_INFO, KIND_WARNING, KIND_SUCCESS, KIND_ACHIEVEMENT)
        print(f"  OK   generated {len(insights)} insights")
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
