"""
models.py — Plain dataclasses mirroring the Room entities from the Kotlin version.

Kept intentionally framework-agnostic so they can be used by both UI code and
the persistence layer (database.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Category:
    id: Optional[int] = None
    key: str = ""           # short stable key, e.g. "FOCUS"
    color: str = "#D4AF37"  # hex string for UI
    name_en: str = ""
    name_fa: str = ""
    icon: str = ""          # icon key
    order_index: int = 0
    archived: bool = False


@dataclass
class Activity:
    """A single tracked activity session."""
    id: Optional[int] = None
    title: str = ""
    category_id: Optional[int] = None
    kind: str = "manual"        # config.KIND_MANUAL | config.KIND_STOPWATCH
    date_iso: str = field(default_factory=_now_iso)        # calendar day (date)
    start_iso: Optional[str] = None                          # stopwatch start
    end_iso: Optional[str] = None                            # stopwatch end
    duration_sec: int = 0
    note: str = ""
    template_id: Optional[int] = None
    voice_input: bool = False
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Goal:
    """Daily / weekly / monthly time goal for a category (or all categories)."""
    id: Optional[int] = None
    period: str = "daily"        # config.PERIOD_*
    category_id: Optional[int] = None   # None = applies to all
    target_minutes: int = 60
    active: bool = True
    created_at: str = field(default_factory=_now_iso)


@dataclass
class Streak:
    """Tracks consecutive day-streak for hitting a goal."""
    id: Optional[int] = None
    goal_id: int = 0
    current: int = 0
    longest: int = 0
    last_hit_date: Optional[str] = None  # ISO date


@dataclass
class Template:
    """Recurring activity template for the quick-log."""
    id: Optional[int] = None
    title: str = ""
    category_id: Optional[int] = None
    default_duration_min: int = 30
    icon: str = ""
    created_at: str = field(default_factory=_now_iso)


@dataclass
class Badge:
    """Awarded milestone (e.g., 7-day streak)."""
    id: Optional[int] = None
    key: str = ""
    title_en: str = ""
    title_fa: str = ""
    earned_at: str = field(default_factory=_now_iso)


# === Helpers ===

def fmt_duration(sec: int) -> str:
    """Human-friendly HH:MM:SS or MM:SS."""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_minutes_human(sec: int, lang: str = "en") -> str:
    """'2h 15m' / '۲ ساعت ۱۵ دقیقه'."""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, _ = divmod(rem, 60)
    if lang == "fa":
        parts = []
        if h:
            parts.append(f"{_to_fa(h)} ساعت")
        if m:
            parts.append(f"{_to_fa(m)} دقیقه")
        return " ".join(parts) if parts else "۰ دقیقه"
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) if parts else "0m"


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_fa(n) -> str:
    return str(n).translate(_FA_DIGITS)
