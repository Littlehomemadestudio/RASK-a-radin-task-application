"""
rask.config
===========

Central configuration constants for the Rask desktop application.

This module is the single source of truth for:
  • Color palette (gold-on-dark theme)
  • Spacing / radii / typography tokens
  • Window dimensions
  • Default categories, badges, streak milestones
  • Encryption parameters (AES-256-GCM, PBKDF2)
  • Database / backup file locations
  • Animation timings
  • Notification settings

All values are tuned to mirror the web/PWA version 1:1, so the desktop
app feels like the same product, not a port.

Nothing in this module performs side-effects — it is pure data.  Importing
it is cheap and safe from any thread.
"""
from __future__ import annotations

# =============================================================================
# === Application metadata                                                    ===
# =============================================================================

APP_NAME: str = "Rask"
APP_NAME_FA: str = "رَسک"
APP_TAGLINE: str = "زمان، ظریف."
APP_TAGLINE_EN: str = "Time, refined."
APP_VERSION: str = "2.0.0"
APP_AUTHOR: str = "Littlehomemade Studio"
APP_LICENSE: str = "MIT"
APP_URL: str = "https://github.com/Littlehomadestudio/RASK-a-radin-task-application"

# Build identifier — bumped on every release.  Used by backup format
# versioning and the "About" screen.
APP_BUILD: int = 2025_07_18_001

# =============================================================================
# === Window / layout                                                         ===
# =============================================================================

WINDOW_WIDTH: int = 540
WINDOW_HEIGHT: int = 900
WINDOW_MIN_WIDTH: int = 420
WINDOW_MIN_HEIGHT: int = 720

# Density breakpoints (px).  Below these thresholds the layout switches
# to a more compact variant.
DENSITY_COMPACT_BELOW: int = 480
DENSITY_MEDIUM_BELOW: int = 720

# Bottom nav height + FAB diameter must match the web CSS exactly so
# that touch targets feel identical between the two products.
BOTTOM_NAV_HEIGHT: int = 76
FAB_SIZE: int = 56
FAB_MARGIN: int = 20

# =============================================================================
# === Color palette                                                           ===
# =============================================================================
# Hex strings — preferred because they round-trip cleanly to CSS, PIL,
# and Tkinter color parsers.  Where a color is also used by ReportLab
# (which prefers 0-255 tuples) we provide a `_RGB` companion.

MATTE_BLACK: str = "#0E0E10"
CHARCOAL: str = "#1A1A1D"
SURFACE: str = "#222226"
SURFACE_HI: str = "#2C2C30"
SURFACE_HIGHER: str = "#34343A"

GOLD: str = "#D4AF37"
GOLD_SOFT: str = "#C9A84C"
GOLD_DIM: str = "#7A6620"
GOLD_BRIGHT: str = "#F0CE6B"
GOLD_GLOW: str = "#FFE89A"

TEXT: str = "#E8E8E8"
TEXT_DIM: str = "#9A9A9F"
TEXT_FAINT: str = "#5C5C60"
TEXT_MUTED: str = "#3F3F44"

SUCCESS: str = "#7BC97B"
SUCCESS_DIM: str = "#3F6B3F"
WARNING: str = "#E8B85A"
WARNING_DIM: str = "#7A5E2A"
DANGER: str = "#D4625A"
DANGER_DIM: str = "#6B2F2A"
INFO: str = "#7B9BC9"
INFO_DIM: str = "#2F4A6B"

DIVIDER: str = "#2C2C30"
DIVIDER_SOFT: str = "#222226"
OVERLAY: str = "#00000099"
SHADOW: str = "#00000066"

# Category colors — must mirror web/js/db.js seedDefaults
CAT_FOCUS: str = "#D4AF37"
CAT_LEARN: str = "#7B9BC9"
CAT_WORK: str = "#C9A84C"
CAT_HEALTH: str = "#7BC97B"
CAT_CREATIVE: str = "#D49ABF"
CAT_SOCIAL: str = "#E8B85A"
CAT_REST: str = "#9A9A9F"

# Heatmap intensity scale (0..4) — gold on dark.
HEATMAP_LEVELS: tuple[str, ...] = (
    "#1A1A1D",  # 0: no activity
    "#3F3220",  # 1: light
    "#7A6620",  # 2: moderate
    "#C9A84C",  # 3: high
    "#D4AF37",  # 4: very high
)

# =============================================================================
# === Typography tokens                                                       ===
# =============================================================================

# Font family preferences.  On Windows we prefer "Segoe UI" / "Tahoma"
# which both ship with the OS and include Persian glyphs.  On Linux we
# fall back to "Noto Sans" / "DejaVu Sans".  CustomTkinter will pick
# the first available family from each list.
FONT_FAMILIES_FA: tuple[str, ...] = (
    "Vazirmatn", "Tahoma", "Segoe UI", "Noto Sans",
    "DejaVu Sans", "Arial",
)
FONT_FAMILIES_EN: tuple[str, ...] = (
    "Inter", "Segoe UI", "Helvetica Neue", "Arial",
)
FONT_FAMILIES_MONO: tuple[str, ...] = (
    "Cascadia Code", "JetBrains Mono", "Consolas", "DejaVu Sans Mono",
)

# Type scale (size in px, weight as Tk font weight constant).
# Mirrors CSS: 11 / 12 / 13 / 14 / 15 / 16 / 18 / 22 / 28 / 42.
FONT_SIZE_CAPTION: int = 11
FONT_SIZE_SMALL: int = 12
FONT_SIZE_BODY: int = 13
FONT_SIZE_BODY_LG: int = 14
FONT_SIZE_DEFAULT: int = 15
FONT_SIZE_LABEL: int = 16
FONT_SIZE_HEADING_SM: int = 18
FONT_SIZE_HEADING: int = 22
FONT_SIZE_HEADING_LG: int = 28
FONT_SIZE_DISPLAY: int = 42
FONT_SIZE_HERO: int = 64

FONT_WEIGHT_LIGHT: str = "light"
FONT_WEIGHT_NORMAL: str = "normal"
FONT_WEIGHT_BOLD: str = "bold"
FONT_WEIGHT_BLACK: str = "black"

# =============================================================================
# === Spacing / radii / elevation                                             ===
# =============================================================================

SPACE_XS: int = 4
SPACE_SM: int = 8
SPACE_MD: int = 12
SPACE_LG: int = 16
SPACE_XL: int = 24
SPACE_XXL: int = 32
SPACE_XXXL: int = 48

RADIUS_SM: int = 6
RADIUS_MD: int = 12
RADIUS_LG: int = 18
RADIUS_XL: int = 24
RADIUS_PILL: int = 999

# Elevation (box-shadow depth in web).  On desktop we approximate with
# a thin border + slight inner highlight.
ELEVATION_0: int = 0
ELEVATION_1: int = 1
ELEVATION_2: int = 2
ELEVATION_3: int = 4
ELEVATION_4: int = 8

# =============================================================================
# === Animation timings                                                       ===
# =============================================================================

ANIM_INSTANT: int = 0
ANIM_FAST: int = 120
ANIM_NORMAL: int = 220
ANIM_SLOW: int = 380
ANIM_SPLASH: int = 2200
ANIM_ONBOARDING_SLIDE: int = 320

EASE_OUT: str = "ease_out"
EASE_IN: str = "ease_in"
EASE_IN_OUT: str = "ease_in_out"
EASE_SPRING: str = "spring"

# =============================================================================
# === Database / file paths                                                   ===
# =============================================================================

import os
import sys
from pathlib import Path

def _user_data_dir() -> Path:
    """Return a per-user writable directory for Rask data.

    On Windows: %APPDATA%/Rask
    On macOS:   ~/Library/Application Support/Rask
    On Linux:   ~/.local/share/Rask

    Falls back to ./data next to the executable if the platform dir
    is not writable (e.g. read-only home in some sandboxes).
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        p = Path(base) / "Rask"
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / "Rask"
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        p = Path(base) / "Rask"
    try:
        p.mkdir(parents=True, exist_ok=True)
        # Test writability
        (p / ".write_test").touch()
        (p / ".write_test").unlink()
        return p
    except Exception:
        local = Path.cwd() / "data"
        local.mkdir(parents=True, exist_ok=True)
        return local


DATA_DIR: Path = _user_data_dir()
DB_PATH: Path = DATA_DIR / "rask.db"
BACKUP_DIR: Path = DATA_DIR / "backups"
EXPORT_DIR: Path = DATA_DIR / "exports"
LOG_DIR: Path = DATA_DIR / "logs"
CACHE_DIR: Path = DATA_DIR / "cache"

for _d in (BACKUP_DIR, EXPORT_DIR, LOG_DIR, CACHE_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# =============================================================================
# === Encryption parameters                                                   ===
# =============================================================================
# These MUST mirror web/js/backup.js and web/js/biometric.js so that
# backup files are interoperable between the web and desktop versions.

BACKUP_MAGIC: bytes = b"RASK"
BACKUP_VERSION: int = 1
BACKUP_IV_LEN: int = 12
BACKUP_SALT_LEN: int = 16
BACKUP_KDF_ITERATIONS: int = 200_000
BACKUP_KDF_HASH: str = "sha256"
BACKUP_KEY_LEN: int = 32  # AES-256

PIN_SALT_LEN: int = 16
PIN_KDF_ITERATIONS: int = 200_000
PIN_KDF_HASH: str = "sha256"
PIN_KEY_LEN: int = 32
PIN_LENGTH: int = 4

# =============================================================================
# === Default categories (mirrors web/js/db.js seedDefaults)                  ===
# =============================================================================

DEFAULT_CATEGORIES: list[dict] = [
    {"key": "FOCUS", "color": "#D4AF37", "name_en": "Focus",
     "name_fa": "تمرکز", "icon": "ring", "order_index": 0, "archived": 0},
    {"key": "LEARN", "color": "#7B9BC9", "name_en": "Learn",
     "name_fa": "یادگیری", "icon": "book", "order_index": 1, "archived": 0},
    {"key": "WORK", "color": "#C9A84C", "name_en": "Work",
     "name_fa": "کار", "icon": "briefcase", "order_index": 2, "archived": 0},
    {"key": "HEALTH", "color": "#7BC97B", "name_en": "Health",
     "name_fa": "سلامتی", "icon": "heart", "order_index": 3, "archived": 0},
    {"key": "CREATIVE", "color": "#D49ABF", "name_en": "Creative",
     "name_fa": "خلاقیت", "icon": "palette", "order_index": 4, "archived": 0},
    {"key": "SOCIAL", "color": "#E8B85A", "name_en": "Social",
     "name_fa": "اجتماعی", "icon": "users", "order_index": 5, "archived": 0},
    {"key": "REST", "color": "#9A9A9F", "name_en": "Rest",
     "name_fa": "استراحت", "icon": "moon", "order_index": 6, "archived": 0},
]

DEFAULT_GOAL_MINUTES: int = 120

# =============================================================================
# === Streak milestones & badges                                             ===
# =============================================================================

STREAK_MILESTONES: tuple[int, ...] = (3, 7, 14, 30, 60, 100, 365)

BADGE_DEFINITIONS: list[dict] = [
    {"key": "first_activity", "name_en": "First Step", "name_fa": "اولین قدم",
     "desc_en": "Log your first activity", "desc_fa": "اولین فعالیت را ثبت کن",
     "icon": "spark", "tier": "bronze"},
    {"key": "streak_3", "name_en": "Hat Trick", "name_fa": "کلاه‌برداری",
     "desc_en": "3-day streak", "desc_fa": "زنجیره ۳ روزه",
     "icon": "flame", "tier": "bronze"},
    {"key": "streak_7", "name_en": "Week Warrior", "name_fa": "مبارز هفته",
     "desc_en": "7-day streak", "desc_fa": "زنجیره ۷ روزه",
     "icon": "flame", "tier": "silver"},
    {"key": "streak_30", "name_en": "Monthly Master", "name_fa": "استاد ماهانه",
     "desc_en": "30-day streak", "desc_fa": "زنجیره ۳۰ روزه",
     "icon": "flame", "tier": "gold"},
    {"key": "streak_100", "name_en": "Centurion", "name_fa": "صد روز",
     "desc_en": "100-day streak", "desc_fa": "زنجیره ۱۰۰ روزه",
     "icon": "flame", "tier": "platinum"},
    {"key": "early_bird", "name_en": "Early Bird", "name_fa": "سحرخیز",
     "desc_en": "Activity before 6 AM", "desc_fa": "فعالیت قبل از ۶ صبح",
     "icon": "sunrise", "tier": "silver"},
    {"key": "night_owl", "name_en": "Night Owl", "name_fa": "شب‌بیدار",
     "desc_en": "Activity after midnight", "desc_fa": "فعالیت بعد از نیمه‌شب",
     "icon": "moon", "tier": "silver"},
    {"key": "goal_master", "name_en": "Goal Master", "name_fa": "استاد هدف",
     "desc_en": "Hit a daily goal 30 times", "desc_fa": "۳۰ بار به هدف روزانه برس",
     "icon": "trophy", "tier": "gold"},
    {"key": "polyglot", "name_en": "Renaissance", "name_fa": "رنسانس",
     "desc_en": "Log all 7 categories in one week",
     "desc_fa": "همه ۷ دسته را در یک هفته ثبت کن",
     "icon": "palette", "tier": "platinum"},
    {"key": "marathon", "name_en": "Marathon", "name_fa": "ماراتن",
     "desc_en": "5-hour activity in one day",
     "desc_fa": "۵ ساعت فعالیت در یک روز",
     "icon": "medal", "tier": "gold"},
    {"key": "sprint", "name_en": "Sprint", "name_fa": "دو سرعت",
     "desc_en": "10 activities in one day",
     "desc_fa": "۱۰ فعالیت در یک روز",
     "icon": "bolt", "tier": "silver"},
    {"key": "consistency", "name_en": "Consistency", "name_fa": "استمرار",
     "desc_en": "60-day streak", "desc_fa": "زنجیره ۶۰ روزه",
     "icon": "diamond", "tier": "gold"},
]

# =============================================================================
# === Timer / stopwatch                                                       ===
# =============================================================================

TIMER_TICK_MS: int = 1000  # 1Hz UI refresh
TIMER_PERSIST_KEY: str = "active_timer"
TIMER_NOTIFY_EVERY_MIN: int = 5  # gentle reminder while running
TIMER_MAX_HOURS: int = 16  # safety cap to prevent runaway sessions

# =============================================================================
# === Quick-log presets                                                      ===
# =============================================================================

QUICK_DURATIONS_MIN: tuple[int, ...] = (5, 10, 15, 25, 30, 45, 60, 90, 120)

# =============================================================================
# === Statistics presets                                                      ===
# =============================================================================

STATS_PRESETS: list[dict] = [
    {"key": "today", "name_en": "Today", "name_fa": "امروز", "days": 1},
    {"key": "yesterday", "name_en": "Yesterday", "name_fa": "دیروز", "days": 1,
     "offset": 1},
    {"key": "week", "name_en": "This Week", "name_fa": "این هفته", "days": 7},
    {"key": "last_week", "name_en": "Last Week", "name_fa": "هفته گذشته",
     "days": 7, "offset": 7},
    {"key": "month", "name_en": "This Month", "name_fa": "این ماه", "days": 30},
    {"key": "last_month", "name_en": "Last Month", "name_fa": "ماه گذشته",
     "days": 30, "offset": 30},
    {"key": "quarter", "name_en": "This Quarter", "name_fa": "این فصل", "days": 90},
    {"key": "year", "name_en": "This Year", "name_fa": "امسال", "days": 365},
    {"key": "all", "name_en": "All Time", "name_fa": "همه", "days": 99999},
]

# =============================================================================
# === Reminder defaults                                                       ===
# =============================================================================

REMINDER_DEFAULT_SNOOZE_MIN: int = 10
REMINDER_DEFAULT_LEDGE_MIN: int = 60 * 18  # 6 PM
REMINDER_CHECK_INTERVAL_SEC: int = 30

# =============================================================================
# === Notification settings                                                   ===
# =============================================================================

NOTIFY_SOUND_DEFAULT: bool = True
NOTIFY_VIBRATE_DEFAULT: bool = True  # supported via Windows MessageBox flash
NOTIFY_TOAST_DURATION_MS: int = 3500
NOTIFY_MAX_QUEUED: int = 8

# =============================================================================
# === Backup rotation                                                         ===
# =============================================================================

BACKUP_KEEP_LOCAL: int = 10
BACKUP_FILENAME_FMT: str = "rask-backup-{ts}.raskbk"
BACKUP_TIMESTAMP_FMT: str = "%Y%m%d-%H%M%S"

# =============================================================================
# === Export                                                                  ===
# =============================================================================

EXPORT_PDF_PAGE_SIZE: str = "A4"
EXPORT_PDF_MARGIN: int = 36
EXPORT_CSV_DELIMITER: str = ","
EXPORT_CSV_ENCODING: str = "utf-8-sig"  # BOM so Excel opens UTF-8 correctly

# =============================================================================
# === Onboarding                                                              ===
# =============================================================================

ONBOARDING_SLIDES: list[dict] = [
    {
        "title_en": "Track time, beautifully",
        "title_fa": "زمان را زیبا پیگیری کن",
        "body_en": "Log activities with a tap, run a background stopwatch, "
                   "and shape your day with intention.",
        "body_fa": "فعالیت‌ها را با یک ضربه ثبت کن، کرنومتر پس‌زمینه را اجرا کن "
                   "و روزت را شکل بده.",
        "icon": "ring",
        "accent": GOLD,
    },
    {
        "title_en": "Set goals. Build streaks.",
        "title_fa": "هدف تعیین کن. زنجیره بساز.",
        "body_en": "Daily, weekly, and monthly goals. Keep your streak alive "
                   "and earn milestone badges.",
        "body_fa": "اهداف روزانه، هفتگی و ماهانه. زنجیره‌ات را زنده نگه‌دار و "
                   "نشان‌های قدم‌به‌قدم بگیر.",
        "icon": "flame",
        "accent": SUCCESS,
    },
    {
        "title_en": "100% offline. Private.",
        "title_fa": "۱۰۰٪ آفلاین. خصوصی.",
        "body_en": "Your data stays on your device. Encrypted backup whenever "
                   "you want. No account, no server, no tracking.",
        "body_fa": "داده‌هایت روی دستگاهت می‌مانند. پشتیبان رمزنگاری‌شده هر وقت "
                   "بخواهی. بدون حساب، بدون سرور، بدون ردیابی.",
        "icon": "shield",
        "accent": INFO,
    },
]

# =============================================================================
# === Languages                                                               ===
# =============================================================================

SUPPORTED_LANGUAGES: dict[str, dict] = {
    "fa": {"name_en": "Persian", "name_fa": "فارسی", "rtl": True,
            "sample_digits": "۰۱۲۳۴۵۶۷۸۹"},
    "en": {"name_en": "English", "name_fa": "انگلیسی", "rtl": False,
            "sample_digits": "0123456789"},
    "ar": {"name_en": "Arabic", "name_fa": "عربی", "rtl": True,
            "sample_digits": "٠١٢٣٤٥٦٧٨٩"},
    "tr": {"name_en": "Turkish", "name_fa": "ترکی", "rtl": False,
            "sample_digits": "0123456789"},
    "ru": {"name_en": "Russian", "name_fa": "روسی", "rtl": False,
            "sample_digits": "0123456789"},
    "de": {"name_en": "German", "name_fa": "آلمانی", "rtl": False,
            "sample_digits": "0123456789"},
    "fr": {"name_en": "French", "name_fa": "فرانسوی", "rtl": False,
            "sample_digits": "0123456789"},
    "es": {"name_en": "Spanish", "name_fa": "اسپانیایی", "rtl": False,
            "sample_digits": "0123456789"},
    "zh": {"name_en": "Chinese", "name_fa": "چینی", "rtl": False,
            "sample_digits": "0123456789"},
    "ja": {"name_en": "Japanese", "name_fa": "ژاپنی", "rtl": False,
            "sample_digits": "0123456789"},
}

DEFAULT_LANG: str = "fa"

# =============================================================================
# === Theme variants                                                          ===
# =============================================================================

THEME_DARK: str = "dark"
THEME_LIGHT: str = "light"
THEME_SYSTEM: str = "system"

DEFAULT_THEME: str = THEME_DARK

# Light theme overrides (rarely used — Rask is fundamentally a dark app,
# but we support a tasteful light mode for accessibility).
LIGHT_THEME_OVERRIDES: dict[str, str] = {
    "MATTE_BLACK": "#FAFAF8",
    "CHARCOAL": "#F2F0EA",
    "SURFACE": "#FFFFFF",
    "SURFACE_HI": "#F8F6F0",
    "TEXT": "#1A1A1D",
    "TEXT_DIM": "#5C5C60",
    "TEXT_FAINT": "#9A9A9F",
    "DIVIDER": "#E8E4DC",
}

# =============================================================================
# === Accessibility                                                           ===
# =============================================================================

DEFAULT_FONT_SCALE: float = 1.0
MAX_FONT_SCALE: float = 1.6
MIN_FONT_SCALE: float = 0.85

DEFAULT_REDUCED_MOTION: bool = False
DEFAULT_HIGH_CONTRAST: bool = False

# =============================================================================
# === Keyboard shortcuts                                                      ===
# =============================================================================

SHORTCUTS: list[dict] = [
    {"keys": "Ctrl+N", "action": "quick_log", "name_en": "Quick log",
     "name_fa": "ثبت سریع"},
    {"keys": "Ctrl+F", "action": "search", "name_en": "Search",
     "name_fa": "جستجو"},
    {"keys": "Ctrl+T", "action": "start_timer", "name_en": "Start timer",
     "name_fa": "شروع تایمر"},
    {"keys": "Ctrl+S", "action": "stop_timer", "name_en": "Stop timer",
     "name_fa": "توقف تایمر"},
    {"keys": "Ctrl+B", "action": "backup", "name_en": "Backup now",
     "name_fa": "پشتیبان‌گیری"},
    {"keys": "Ctrl+E", "action": "export", "name_en": "Export",
     "name_fa": "خروجی"},
    {"keys": "Ctrl+,", "action": "settings", "name_en": "Settings",
     "name_fa": "تنظیمات"},
    {"keys": "Ctrl+1", "action": "tab_home", "name_en": "Home tab",
     "name_fa": "تب خانه"},
    {"keys": "Ctrl+2", "action": "tab_goals", "name_en": "Goals tab",
     "name_fa": "تب اهداف"},
    {"keys": "Ctrl+3", "action": "tab_stats", "name_en": "Stats tab",
     "name_fa": "تب آمار"},
    {"keys": "Ctrl+4", "action": "tab_settings", "name_en": "Settings tab",
     "name_fa": "تب تنظیمات"},
    {"keys": "Ctrl+L", "action": "lock", "name_en": "Lock app",
     "name_fa": "قفل برنامه"},
    {"keys": "?", "action": "shortcuts_help", "name_en": "Show shortcuts",
     "name_fa": "نمایش میانبرها"},
    {"keys": "Esc", "action": "close_dialog", "name_en": "Close dialog",
     "name_fa": "بستن پنجره"},
]

# =============================================================================
# === User-agent / HTTP                                                       ===
# =============================================================================

USER_AGENT: str = f"RaskDesktop/{APP_VERSION} ({sys.platform}; Python {sys.version_info.major}.{sys.version_info.minor})"

# =============================================================================
# === Build / debug                                                           ===
# =============================================================================

DEBUG: bool = os.environ.get("RASK_DEBUG", "").lower() in ("1", "true", "yes")
VERBOSE: bool = os.environ.get("RASK_VERBOSE", "").lower() in ("1", "true", "yes")
PROFILE: bool = os.environ.get("RASK_PROFILE", "").lower() in ("1", "true", "yes")

# =============================================================================
# === Convenience tuples                                                      ===
# =============================================================================

CATEGORY_COLORS: tuple[str, ...] = (
    CAT_FOCUS, CAT_LEARN, CAT_WORK, CAT_HEALTH,
    CAT_CREATIVE, CAT_SOCIAL, CAT_REST,
)

ALL_COLORS: dict[str, str] = {
    "matte_black": MATTE_BLACK,
    "charcoal": CHARCOAL,
    "surface": SURFACE,
    "surface_hi": SURFACE_HI,
    "surface_higher": SURFACE_HIGHER,
    "gold": GOLD,
    "gold_soft": GOLD_SOFT,
    "gold_dim": GOLD_DIM,
    "gold_bright": GOLD_BRIGHT,
    "gold_glow": GOLD_GLOW,
    "text": TEXT,
    "text_dim": TEXT_DIM,
    "text_faint": TEXT_FAINT,
    "text_muted": TEXT_MUTED,
    "success": SUCCESS,
    "success_dim": SUCCESS_DIM,
    "warning": WARNING,
    "warning_dim": WARNING_DIM,
    "danger": DANGER,
    "danger_dim": DANGER_DIM,
    "info": INFO,
    "info_dim": INFO_DIM,
    "divider": DIVIDER,
    "divider_soft": DIVIDER_SOFT,
    "overlay": OVERLAY,
    "shadow": SHADOW,
}

__all__ = [name for name in dir() if name.isupper() or name.startswith("DEFAULT_") or name.startswith("STREAK_") or name.startswith("BADGE_") or name.startswith("QUICK_") or name.startswith("STATS_") or name.startswith("REMINDER_") or name.startswith("NOTIFY_") or name.startswith("BACKUP_") or name.startswith("EXPORT_") or name.startswith("ONBOARDING_") or name.startswith("SUPPORTED_") or name.startswith("LIGHT_") or name.startswith("CATEGORY_") or name.startswith("ALL_") or name.startswith("FONT_") or name.startswith("SPACE_") or name.startswith("RADIUS_") or name.startswith("ELEVATION_") or name.startswith("ANIM_") or name.startswith("EASE_") or name.startswith("WINDOW_") or name.startswith("BOTTOM_") or name.startswith("FAB_") or name.startswith("DENSITY_") or name.startswith("TIMER_") or name.startswith("SHORTCUTS") or name.startswith("PIN_") or name.startswith("APP_") or name.startswith("USER_") or name.startswith("DATA_") or name.startswith("DB_") or name.startswith("BACKUP_") or name.startswith("EXPORT_") or name.startswith("LOG_") or name.startswith("CACHE_") or name in ("DEBUG", "VERBOSE", "PROFILE", "DEFAULT_LANG", "DEFAULT_THEME", "DEFAULT_FONT_SCALE", "MAX_FONT_SCALE", "MIN_FONT_SCALE", "DEFAULT_REDUCED_MOTION", "DEFAULT_HIGH_CONTRAST", "ONBOARDING_SLIDES", "BADGE_DEFINITIONS", "DEFAULT_CATEGORIES", "DEFAULT_GOAL_MINUTES", "QUICK_DURATIONS_MIN", "STATS_PRESETS", "SHORTCUTS", "SUPPORTED_LANGUAGES", "LIGHT_THEME_OVERRIDES", "HEATMAP_LEVELS", "ALL_COLORS", "CATEGORY_COLORS", "STREAK_MILESTONES", "ONBOARDING_SLIDES") or name.startswith("_")]
