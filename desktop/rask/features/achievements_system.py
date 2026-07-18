"""
rask.features.achievements_system
=================================

Extended achievement / XP / level system.

Built on top of :mod:`rask.services.badge_service` but extends it
with:

  • 30+ achievement definitions (vs ~12 in
    ``config.BADGE_DEFINITIONS``)
  • Per-achievement progress tracking (0..1)
  • XP rewards per achievement
  • User level (1..) computed from total XP
  • Level titles (Apprentice → Adept → Expert → Master → Grandmaster)
  • Level progress (0..1 toward next level)

Each achievement has a ``check`` function that returns the current
progress 0..1 (1.0 = earned).  :meth:`AchievementService.check_all`
scans all unearned achievements, marks any that hit 1.0 as earned,
and returns the list of newly-earned keys.

Schema
------

Uses the existing ``badges`` table (``key`` column is the achievement
key, ``metadata_json`` stores ``xp``, ``tier``, ``progress``, etc.).

Events
------

  ``achievement.earned``      — {key, title, xp, tier}
  ``achievement.progress``    — {key, progress, delta}
  ``achievement.level_up``    — {level, title, total_xp}
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, start_of_week, end_of_week, today_iso

__all__ = [
    "Achievement",
    "AchievementService",
    "achievement_service",
    "LEVEL_TITLES",
    "TIER_BRONZE",
    "TIER_SILVER",
    "TIER_GOLD",
    "TIER_PLATINUM",
    "TIER_DIAMOND",
]

_log = get_logger("features.achievements")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

TIER_BRONZE: str = "bronze"
TIER_SILVER: str = "silver"
TIER_GOLD: str = "gold"
TIER_PLATINUM: str = "platinum"
TIER_DIAMOND: str = "diamond"

#: XP per level (linear progression).
XP_PER_LEVEL: int = 100

#: Level titles.  Each title spans 5 levels.
LEVEL_TITLES: List[Tuple[int, str, str]] = [
    (1,  "Apprentice",   "تازه‌کار"),
    (6,  "Adept",         "آشنا"),
    (11, "Expert",        "متخصص"),
    (16, "Master",        "استاد"),
    (21, "Grandmaster",   "استاد بزرگ"),
    (26, "Legend",        "افسانه"),
]


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class Achievement:
    """An achievement definition."""

    key: str
    title_en: str
    title_fa: str
    description_en: str
    description_fa: str
    icon: str
    tier: str = TIER_BRONZE
    xp_reward: int = 10
    category: str = "general"  # streaks/time/categories/goals/sessions/consistency
    progress: float = 0.0       # 0..1 (1.0 = earned)
    earned_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# === Achievement definitions                                                ===
# =============================================================================

ACHIEVEMENT_DEFS: List[Dict[str, Any]] = [
    # --- Streaks (general, any-activity) ---
    {"key": "streak_3", "title_en": "Hat Trick", "title_fa": "کلاه‌برداری",
     "description_en": "3-day streak", "description_fa": "زنجیره ۳ روزه",
     "icon": "flame", "tier": TIER_BRONZE, "xp_reward": 15, "category": "streaks",
     "check": "streak_at_least(3)"},
    {"key": "streak_7", "title_en": "Week Warrior", "title_fa": "مبارز هفته",
     "description_en": "7-day streak", "description_fa": "زنجیره ۷ روزه",
     "icon": "flame", "tier": TIER_SILVER, "xp_reward": 30, "category": "streaks",
     "check": "streak_at_least(7)"},
    {"key": "streak_14", "title_en": "Fortnight", "title_fa": "دو هفته",
     "description_en": "14-day streak", "description_fa": "زنجیره ۱۴ روزه",
     "icon": "flame", "tier": TIER_SILVER, "xp_reward": 50, "category": "streaks",
     "check": "streak_at_least(14)"},
    {"key": "streak_30", "title_en": "Monthly Master", "title_fa": "استاد ماهانه",
     "description_en": "30-day streak", "description_fa": "زنجیره ۳۰ روزه",
     "icon": "flame", "tier": TIER_GOLD, "xp_reward": 100, "category": "streaks",
     "check": "streak_at_least(30)"},
    {"key": "streak_60", "title_en": "Consistency", "title_fa": "استمرار",
     "description_en": "60-day streak", "description_fa": "زنجیره ۶۰ روزه",
     "icon": "diamond", "tier": TIER_GOLD, "xp_reward": 200, "category": "consistency",
     "check": "streak_at_least(60)"},
    {"key": "streak_100", "title_en": "Centurion", "title_fa": "صد روز",
     "description_en": "100-day streak", "description_fa": "زنجیره ۱۰۰ روزه",
     "icon": "flame", "tier": TIER_PLATINUM, "xp_reward": 500, "category": "streaks",
     "check": "streak_at_least(100)"},
    {"key": "streak_365", "title_en": "Year of Discipline",
     "title_fa": "سال انضباط",
     "description_en": "365-day streak", "description_fa": "زنجیره ۳۶۵ روزه",
     "icon": "diamond", "tier": TIER_DIAMOND, "xp_reward": 1000, "category": "consistency",
     "check": "streak_at_least(365)"},

    # --- Time totals ---
    {"key": "time_10h", "title_en": "First 10 Hours",
     "title_fa": "اولین ۱۰ ساعت",
     "description_en": "Log 10 hours total", "description_fa": "مجموع ۱۰ ساعت فعالیت",
     "icon": "clock", "tier": TIER_BRONZE, "xp_reward": 20, "category": "time",
     "check": "total_minutes_at_least(600)"},
    {"key": "time_100h", "title_en": "Centurion of Time",
     "title_fa": "صد ساعت",
     "description_en": "Log 100 hours total", "description_fa": "مجموع ۱۰۰ ساعت فعالیت",
     "icon": "clock", "tier": TIER_SILVER, "xp_reward": 80, "category": "time",
     "check": "total_minutes_at_least(6000)"},
    {"key": "time_500h", "title_en": "Time Lord", "title_fa": "ارباب زمان",
     "description_en": "Log 500 hours total", "description_fa": "مجموع ۵۰۰ ساعت",
     "icon": "clock", "tier": TIER_GOLD, "xp_reward": 250, "category": "time",
     "check": "total_minutes_at_least(30000)"},
    {"key": "time_1000h", "title_en": "Time Master", "title_fa": "استاد زمان",
     "description_en": "Log 1000 hours total", "description_fa": "مجموع ۱۰۰۰ ساعت",
     "icon": "clock", "tier": TIER_PLATINUM, "xp_reward": 500, "category": "time",
     "check": "total_minutes_at_least(60000)"},

    # --- Categories ---
    {"key": "first_activity", "title_en": "First Step",
     "title_fa": "اولین قدم",
     "description_en": "Log your first activity",
     "description_fa": "اولین فعالیت را ثبت کن",
     "icon": "spark", "tier": TIER_BRONZE, "xp_reward": 10, "category": "categories",
     "check": "activity_count_at_least(1)"},
    {"key": "polyglot", "title_en": "Renaissance", "title_fa": "رنسانس",
     "description_en": "Log all 7 categories in one week",
     "description_fa": "همه ۷ دسته را در یک هفته ثبت کن",
     "icon": "palette", "tier": TIER_PLATINUM, "xp_reward": 200, "category": "categories",
     "check": "all_categories_in_week()"},
    {"key": "category_specialist", "title_en": "Specialist",
     "title_fa": "متخصص",
     "description_en": "100 hours in one category",
     "description_fa": "۱۰۰ ساعت در یک دسته",
     "icon": "medal", "tier": TIER_GOLD, "xp_reward": 150, "category": "categories",
     "check": "category_minutes_at_least(6000)"},
    {"key": "category_explorer", "title_en": "Explorer",
     "title_fa": "کاوشگر",
     "description_en": "Use 5+ categories", "description_fa": "از ۵ دسته مختلف استفاده کن",
     "icon": "compass", "tier": TIER_SILVER, "xp_reward": 60, "category": "categories",
     "check": "distinct_categories_at_least(5)"},

    # --- Goals ---
    {"key": "goal_master", "title_en": "Goal Master", "title_fa": "استاد هدف",
     "description_en": "Hit a daily goal 30 times",
     "description_fa": "۳۰ بار به هدف روزانه برس",
     "icon": "trophy", "tier": TIER_GOLD, "xp_reward": 150, "category": "goals",
     "check": "goal_hits_at_least(30)"},
    {"key": "goal_30days", "title_en": "Monthly Achiever",
     "title_fa": "موفق ماهانه",
     "description_en": "Hit daily goal 30 days in a row",
     "description_fa": "۳۰ روز متوالی به هدف روزانه برس",
     "icon": "calendar", "tier": TIER_GOLD, "xp_reward": 200, "category": "goals",
     "check": "goal_streak_at_least(30)"},
    {"key": "goal_first_hit", "title_en": "First Hit", "title_fa": "اولین برد",
     "description_en": "Hit any goal once", "description_fa": "یک بار به هدف برس",
     "icon": "target", "tier": TIER_BRONZE, "xp_reward": 15, "category": "goals",
     "check": "goal_hits_at_least(1)"},

    # --- Sessions ---
    {"key": "first_session", "title_en": "First Focus", "title_fa": "اولین تمرکز",
     "description_en": "Complete a focus session",
     "description_fa": "یک جلسه تمرکز را کامل کن",
     "icon": "focus", "tier": TIER_BRONZE, "xp_reward": 15, "category": "sessions",
     "check": "focus_sessions_at_least(1)"},
    {"key": "focus_10", "title_en": "Focused Ten", "title_fa": "ده تمرکز",
     "description_en": "Complete 10 focus sessions",
     "description_fa": "۱۰ جلسه تمرکز را کامل کن",
     "icon": "focus", "tier": TIER_SILVER, "xp_reward": 80, "category": "sessions",
     "check": "focus_sessions_at_least(10)"},
    {"key": "focus_100", "title_en": "Deep Diver", "title_fa": "غواص عمیق",
     "description_en": "Complete 100 focus sessions",
     "description_fa": "۱۰۰ جلسه تمرکز را کامل کن",
     "icon": "focus", "tier": TIER_GOLD, "xp_reward": 250, "category": "sessions",
     "check": "focus_sessions_at_least(100)"},
    {"key": "marathon", "title_en": "Marathon", "title_fa": "ماراتن",
     "description_en": "5-hour activity in one day",
     "description_fa": "۵ ساعت فعالیت در یک روز",
     "icon": "medal", "tier": TIER_GOLD, "xp_reward": 100, "category": "sessions",
     "check": "single_day_minutes_at_least(300)"},

    # --- Count milestones ---
    {"key": "sprint", "title_en": "Sprint", "title_fa": "دو سرعت",
     "description_en": "10 activities in one day",
     "description_fa": "۱۰ فعالیت در یک روز",
     "icon": "bolt", "tier": TIER_SILVER, "xp_reward": 40, "category": "sessions",
     "check": "single_day_count_at_least(10)"},
    {"key": "count_100", "title_en": "Century", "title_fa": "صد فعالیت",
     "description_en": "Log 100 activities", "description_fa": "۱۰۰ فعالیت ثبت کن",
     "icon": "list", "tier": TIER_SILVER, "xp_reward": 60, "category": "sessions",
     "check": "activity_count_at_least(100)"},
    {"key": "count_1000", "title_en": "Prolific", "title_fa": "پرکار",
     "description_en": "Log 1000 activities", "description_fa": "۱۰۰۰ فعالیت ثبت کن",
     "icon": "list", "tier": TIER_GOLD, "xp_reward": 300, "category": "sessions",
     "check": "activity_count_at_least(1000)"},

    # --- Time-of-day ---
    {"key": "early_bird", "title_en": "Early Bird", "title_fa": "سحرخیز",
     "description_en": "Activity before 6 AM",
     "description_fa": "فعالیت قبل از ۶ صبح",
     "icon": "sunrise", "tier": TIER_SILVER, "xp_reward": 40, "category": "time",
     "check": "activity_before_hour(6)"},
    {"key": "night_owl", "title_en": "Night Owl", "title_fa": "شب‌بیدار",
     "description_en": "Activity after midnight",
     "description_fa": "فعالیت بعد از نیمه‌شب",
     "icon": "moon", "tier": TIER_SILVER, "xp_reward": 40, "category": "time",
     "check": "activity_after_hour(23)"},

    # --- Habits & Journal ---
    {"key": "habit_3", "title_en": "Habit Builder", "title_fa": "سازنده عادت",
     "description_en": "7-day habit streak",
     "description_fa": "زنجیره ۷ روزه عادت",
     "icon": "target", "tier": TIER_SILVER, "xp_reward": 50, "category": "consistency",
     "check": "habit_streak_at_least(7)"},
    {"key": "habit_30", "title_en": "Habit Master", "title_fa": "استاد عادت",
     "description_en": "30-day habit streak",
     "description_fa": "زنجیره ۳۰ روزه عادت",
     "icon": "target", "tier": TIER_GOLD, "xp_reward": 150, "category": "consistency",
     "check": "habit_streak_at_least(30)"},
    {"key": "journal_7", "title_en": "Journal Keeper",
     "title_fa": "نگه‌دارنده دفتر",
     "description_en": "7-day journal streak",
     "description_fa": "زنجیره ۷ روزه دفترچه",
     "icon": "book", "tier": TIER_SILVER, "xp_reward": 50, "category": "consistency",
     "check": "journal_streak_at_least(7)"},
    {"key": "journal_30", "title_en": "Diary Master", "title_fa": "استاد دفتر",
     "description_en": "30-day journal streak",
     "description_fa": "زنجیره ۳۰ روزه دفترچه",
     "icon": "book", "tier": TIER_GOLD, "xp_reward": 150, "category": "consistency",
     "check": "journal_streak_at_least(30)"},

    # --- Mood ---
    {"key": "mood_tracker_7", "title_en": "Mood Aware",
     "title_fa": "آگاه از حال",
     "description_en": "Log mood for 7 days",
     "description_fa": "حالت را ۷ روز ثبت کن",
     "icon": "heart", "tier": TIER_SILVER, "xp_reward": 50, "category": "consistency",
     "check": "mood_entries_days_at_least(7)"},
]


# =============================================================================
# === Check function implementations                                        ===
# =============================================================================

def _streak_at_least(n: int) -> float:
    try:
        from ..services.stats_service import stats_service
        s = stats_service.current_streak()
        return min(1.0, s / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _total_minutes_at_least(n: int) -> float:
    try:
        total = db.activity_sum_duration()
        return min(1.0, total / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _activity_count_at_least(n: int) -> float:
    try:
        count = db.activity_count()
        return min(1.0, count / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _all_categories_in_week() -> float:
    try:
        today = today_iso()
        start = start_of_week(today, first_day=6)
        end = end_of_week(today, first_day=6)
        by_cat = db.activity_group_by_category(date_from=start, date_to=end)
        distinct = sum(1 for r in by_cat if int(r.get("total_min") or 0) > 0)
        return min(1.0, distinct / 7)
    except Exception:  # noqa: BLE001
        return 0.0


def _category_minutes_at_least(n: int) -> float:
    try:
        by_cat = db.activity_group_by_category()
        if not by_cat:
            return 0.0
        top = max(int(r.get("total_min") or 0) for r in by_cat)
        return min(1.0, top / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _distinct_categories_at_least(n: int) -> float:
    try:
        by_cat = db.activity_group_by_category()
        distinct = sum(1 for r in by_cat if int(r.get("total_min") or 0) > 0)
        return min(1.0, distinct / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _goal_hits_at_least(n: int) -> float:
    try:
        from ..services.goal_service import goal_service
        # Count badge metadata "goal_hits"
        total = 0
        for g in goal_service.list():
            meta = (g.get("metadata") or {})
            total += int(meta.get("hits", 0))
        return min(1.0, total / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _goal_streak_at_least(n: int) -> float:
    try:
        from ..services.goal_service import goal_service
        best = 0
        for g in goal_service.list():
            from ..services.streak_service import streak_service
            s = streak_service.get(g["id"])
            best = max(best, int(s.get("current", 0)))
        return min(1.0, best / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _focus_sessions_at_least(n: int) -> float:
    try:
        import json as _json
        cur = db.get_conn().execute(
            "SELECT COUNT(*) AS c FROM sessions "
            "WHERE state IN ('completed', 'abandoned') "
            "AND metadata_json LIKE '%focus%'")
        row = cur.fetchone()
        count = int(row["c"]) if row else 0
        return min(1.0, count / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _single_day_minutes_at_least(n: int) -> float:
    try:
        by_day = db.activity_group_by_day()
        if not by_day:
            return 0.0
        top = max(int(r.get("total_min") or 0) for r in by_day)
        return min(1.0, top / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _single_day_count_at_least(n: int) -> float:
    try:
        by_day = db.activity_group_by_day()
        if not by_day:
            return 0.0
        top = max(int(r.get("count") or 0) for r in by_day)
        return min(1.0, top / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _activity_before_hour(h: int) -> float:
    """Has the user logged any activity with start_ts before hour h?"""
    try:
        by_hour = db.activity_group_by_hour()
        if not by_hour:
            return 0.0
        has = any(int(r["hour"]) < h for r in by_hour)
        return 1.0 if has else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _activity_after_hour(h: int) -> float:
    try:
        by_hour = db.activity_group_by_hour()
        if not by_hour:
            return 0.0
        has = any(int(r["hour"]) >= h for r in by_hour)
        return 1.0 if has else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _habit_streak_at_least(n: int) -> float:
    try:
        from .habits import habit_service
        best = 0
        for h in habit_service.list_habits():
            best = max(best, habit_service.streak(h.id or 0))
        return min(1.0, best / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _journal_streak_at_least(n: int) -> float:
    try:
        from .journal import journal_service
        s = journal_service.streak()
        return min(1.0, s / n)
    except Exception:  # noqa: BLE001
        return 0.0


def _mood_entries_days_at_least(n: int) -> float:
    try:
        from .mood_tracker import mood_service
        from ..core.time_utils import add_days
        date_from = add_days(today_iso(), -(n - 1))
        cur = db.get_conn().execute(
            "SELECT COUNT(DISTINCT date_iso) AS c FROM mood_entries "
            "WHERE date_iso >= ?", (date_from,))
        row = cur.fetchone()
        days = int(row["c"]) if row else 0
        return min(1.0, days / n)
    except Exception:  # noqa: BLE001
        return 0.0


_CHECK_DISPATCH: Dict[str, Callable[..., float]] = {
    "streak_at_least": _streak_at_least,
    "total_minutes_at_least": _total_minutes_at_least,
    "activity_count_at_least": _activity_count_at_least,
    "all_categories_in_week": _all_categories_in_week,
    "category_minutes_at_least": _category_minutes_at_least,
    "distinct_categories_at_least": _distinct_categories_at_least,
    "goal_hits_at_least": _goal_hits_at_least,
    "goal_streak_at_least": _goal_streak_at_least,
    "focus_sessions_at_least": _focus_sessions_at_least,
    "single_day_minutes_at_least": _single_day_minutes_at_least,
    "single_day_count_at_least": _single_day_count_at_least,
    "activity_before_hour": _activity_before_hour,
    "activity_after_hour": _activity_after_hour,
    "habit_streak_at_least": _habit_streak_at_least,
    "journal_streak_at_least": _journal_streak_at_least,
    "mood_entries_days_at_least": _mood_entries_days_at_least,
}


def _eval_check(expr: str) -> float:
    """Evaluate a check expression like 'streak_at_least(7)'."""
    if "(" not in expr or not expr.endswith(")"):
        return 0.0
    name = expr[:expr.index("(")].strip()
    args_str = expr[expr.index("(") + 1:-1].strip()
    fn = _CHECK_DISPATCH.get(name)
    if fn is None:
        return 0.0
    args: List[Any] = []
    if args_str:
        for a in args_str.split(","):
            a = a.strip()
            try:
                args.append(int(a))
            except ValueError:
                try:
                    args.append(float(a))
                except ValueError:
                    args.append(a.strip("'\""))
    try:
        return float(fn(*args))
    except Exception as exc:  # noqa: BLE001
        _log.debug("check %s failed: %s", expr, exc)
        return 0.0


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _json_dumps(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return "{}"


# =============================================================================
# === AchievementService                                                    ===
# =============================================================================

class AchievementService:
    """Extended achievement / XP / level system."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._defs: Dict[str, Dict[str, Any]] = {d["key"]: d for d in ACHIEVEMENT_DEFS}

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def all(self) -> List[Achievement]:
        """Return all achievements (earned + locked) with current progress."""
        out: List[Achievement] = []
        earned_map = self._earned_map()
        for key, d in self._defs.items():
            earned = earned_map.get(key)
            progress = 1.0 if earned else self._compute_progress(key)
            out.append(Achievement(
                key=key,
                title_en=d["title_en"],
                title_fa=d["title_fa"],
                description_en=d["description_en"],
                description_fa=d["description_fa"],
                icon=d["icon"],
                tier=d["tier"],
                xp_reward=d["xp_reward"],
                category=d["category"],
                progress=progress,
                earned_at=earned.get("earned_at") if earned else None,
            ))
        # Sort: earned first (by earned_at desc), then by progress desc.
        out.sort(key=lambda a: (a.earned_at is None, -a.progress))
        return out

    def earned(self) -> List[Achievement]:
        return [a for a in self.all() if a.earned_at is not None]

    def locked(self) -> List[Achievement]:
        return [a for a in self.all() if a.earned_at is None]

    def get(self, key: str) -> Optional[Achievement]:
        for a in self.all():
            if a.key == key:
                return a
        return None

    def progress(self, key: str) -> float:
        """Current progress 0..1 toward the achievement."""
        earned = self._earned_map().get(key)
        if earned:
            return 1.0
        return self._compute_progress(key)

    # ------------------------------------------------------------------
    # Check & unlock
    # ------------------------------------------------------------------

    def check_all(self) -> List[str]:
        """Scan all unearned achievements.  Returns list of newly-earned keys."""
        newly_earned: List[str] = []
        with self._lock:
            earned_map = self._earned_map()
            for key, d in self._defs.items():
                if key in earned_map:
                    continue
                p = self._compute_progress(key)
                if p >= 1.0:
                    self._unlock(key)
                    newly_earned.append(key)
                    bus.publish("achievement.earned", {
                        "key": key,
                        "title_fa": d["title_fa"],
                        "title_en": d["title_en"],
                        "xp": d["xp_reward"],
                        "tier": d["tier"],
                        "icon": d["icon"],
                    })
                    # Also publish the older badge.unlocked event for
                    # backwards-compat with notification center.
                    bus.publish("badge.unlocked", {
                        "key": key,
                        "name_fa": d["title_fa"],
                        "name_en": d["title_en"],
                        "icon": d["icon"],
                    })
            # If we earned any, possibly level up.
            if newly_earned:
                old_level = self._cached_level()
                self._invalidate_level_cache()
                new_level = self.level()
                if new_level > old_level:
                    bus.publish("achievement.level_up", {
                        "level": new_level,
                        "title": self.level_title(),
                        "total_xp": self.xp_total(),
                    })
        return newly_earned

    def _unlock(self, key: str) -> None:
        d = self._defs.get(key)
        if not d:
            return
        now = _now_iso()
        try:
            db.badge_add(
                key=key,
                name_en=d["title_en"],
                name_fa=d["title_fa"],
                desc_en=d["description_en"],
                desc_fa=d["description_fa"],
                icon=d["icon"],
                tier=d["tier"],
                metadata={"xp": d["xp_reward"], "category": d["category"]},
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
        _log.info("Achievement unlocked: %s (+%d XP)", key, d["xp_reward"])

    # ------------------------------------------------------------------
    # XP & Levels
    # ------------------------------------------------------------------

    def xp_total(self) -> int:
        """Total XP from all earned achievements."""
        try:
            total = 0
            for b in db.badge_list():
                meta = b.get("metadata") or {}
                total += int(meta.get("xp", 0))
            return total
        except Exception:  # noqa: BLE001
            return 0

    def level(self) -> int:
        """Current level (1 + XP // XP_PER_LEVEL)."""
        return 1 + self.xp_total() // XP_PER_LEVEL

    def level_progress(self) -> float:
        """Progress (0..1) toward the next level."""
        xp = self.xp_total()
        remainder = xp % XP_PER_LEVEL
        return remainder / XP_PER_LEVEL

    def level_title(self) -> str:
        """Return the title (Persian) for the current level."""
        level = self.level()
        title_fa = "تازه‌کار"
        for threshold, _, fa in LEVEL_TITLES:
            if level >= threshold:
                title_fa = fa
        return title_fa

    def level_title_en(self) -> str:
        level = self.level()
        title_en = "Apprentice"
        for threshold, en, _ in LEVEL_TITLES:
            if level >= threshold:
                title_en = en
        return title_en

    def xp_to_next_level(self) -> int:
        """XP needed to reach the next level."""
        xp = self.xp_total()
        return XP_PER_LEVEL - (xp % XP_PER_LEVEL)

    def _cached_level(self) -> int:
        return self.level()

    def _invalidate_level_cache(self) -> None:
        pass  # No caching needed since level() is O(n) cheap.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _earned_map(self) -> Dict[str, Dict[str, Any]]:
        try:
            out: Dict[str, Dict[str, Any]] = {}
            for b in db.badge_list():
                out[b["key"]] = b
            return out
        except Exception:  # noqa: BLE001
            return {}

    def _compute_progress(self, key: str) -> float:
        d = self._defs.get(key)
        if not d:
            return 0.0
        check = d.get("check", "")
        if not check:
            return 0.0
        try:
            p = _eval_check(check)
            # Publish progress event (delta unknown but useful for UI).
            bus.publish("achievement.progress",
                        {"key": key, "progress": p, "delta": 0.0})
            return max(0.0, min(1.0, float(p)))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return 0.0

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return a summary dict for UI display."""
        all_ = self.all()
        earned = [a for a in all_ if a.earned_at is not None]
        locked = [a for a in all_ if a.earned_at is None]
        return {
            "total_achievements": len(all_),
            "earned_count": len(earned),
            "locked_count": len(locked),
            "xp_total": self.xp_total(),
            "level": self.level(),
            "level_title": self.level_title(),
            "level_title_en": self.level_title_en(),
            "level_progress": self.level_progress(),
            "xp_to_next_level": self.xp_to_next_level(),
            "completion_rate": (len(earned) / len(all_)) if all_ else 0.0,
        }


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

achievement_service: AchievementService = AchievementService()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== achievements_system self-tests ===")
    try:
        all_ = achievement_service.all()
        assert len(all_) >= 30, f"expected >=30 achievements, got {len(all_)}"
        # Stats
        stats = achievement_service.stats()
        assert "level" in stats and "xp_total" in stats
        # Level title
        assert achievement_service.level_title() in (
            "تازه‌کار", "آشنا", "متخصص", "استاد", "استاد بزرگ", "افسانه")
        # check_all should not raise
        achievement_service.check_all()
        print(f"  OK   {len(all_)} achievements, level={stats['level']}")
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
