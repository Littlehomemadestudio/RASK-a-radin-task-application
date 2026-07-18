"""config.py — Rask gold-on-dark theme constants (1:1 mirror of web/styles.css :root).

This module centralizes every color, spacing, radius, font size, animation
duration, and default value used throughout the desktop app. Anything that
would live in a CSS variable in the web edition lives here so that the rest
of the codebase can reference a single source of truth.

Mirrors:
  - web/styles.css :root { ... } block
  - web/js/db.js seedDefaults() for default categories
  - web/js/backup.js for backup format constants
  - web/js/biometric.js for PIN KDF constants
  - web/js/timer.js for streak badge milestones
"""
from __future__ import annotations

# =====================================================================
# === COLORS (1:1 with web/styles.css --matte-black, --charcoal, ...) ===
# =====================================================================
MATTE_BLACK  = "#0E0E10"   # app background (deepest)
CHARCOAL     = "#1A1A1D"   # card background
SURFACE      = "#222226"   # raised surface (buttons, chips)
SURFACE_HI   = "#2C2C30"   # hover/active surface, dividers
GOLD         = "#D4AF37"   # primary accent
GOLD_SOFT    = "#C9A84C"   # secondary gold (gradient stop)
GOLD_DIM     = "#7A6620"   # tertiary gold (borders, dim accents)
GOLD_BRIGHT  = "#F0CE5E"   # brighter gold for hover highlights
TEXT         = "#E8E8E8"   # primary text
TEXT_DIM     = "#9A9A9F"   # secondary text
TEXT_FAINT   = "#5C5C60"   # tertiary text (placeholders, disabled)
SUCCESS      = "#7BC97B"   # success states (goal completed, etc.)
WARNING      = "#E8B85A"   # warning states (almost missed streak)
DANGER       = "#D4625A"   # delete / destructive actions
INFO         = "#7B9BC9"   # informational accent
DIVIDER      = "#2C2C30"   # hairline dividers

# Heatmap intensity steps (1:1 with web/js/charts.js Heatmap.intensityColor)
HEATMAP_STEPS = [
    (14, 14, 16),     # 0 — empty
    (48, 40, 16),     # 1 — minimal
    (80, 64, 20),     # 2 — light
    (120, 96, 28),    # 3 — moderate
    (212, 175, 55),   # 4 — full
]

# Category palette (used for donut charts and category dots)
# Matches the default categories but adds extras for custom ones
CATEGORY_PALETTE = [
    "#D4AF37",  # gold
    "#7B9BC9",  # blue
    "#C9A84C",  # amber
    "#7BC97B",  # green
    "#D49ABF",  # pink
    "#E8B85A",  # yellow
    "#9A9A9F",  # gray
    "#9B7BC9",  # purple
    "#C97B9B",  # magenta
    "#7BC9C9",  # teal
    "#C9B07B",  # tan
    "#9BC97B",  # lime
]

# =====================================================================
# === SPACING (1:1 with --space-*) ===
# =====================================================================
SPACE_XS    = 4
SPACE_SM    = 8
SPACE_MD    = 12
SPACE_LG    = 16
SPACE_XL    = 24
SPACE_XXL   = 32
SPACE_XXXL  = 48

# =====================================================================
# === RADIUS (1:1 with --radius-*) ===
# =====================================================================
RADIUS_SM    = 6
RADIUS_MD    = 12
RADIUS_LG    = 18
RADIUS_PILL  = 999   # pill-shaped (chips, buttons)

# =====================================================================
# === TYPOGRAPHY ===
# =====================================================================
FONT_FAMILY_PERSIAN_PRIMARY   = "Vazirmatn"
FONT_FAMILY_PERSIAN_FALLBACK_1 = "Vazir"
FONT_FAMILY_PERSIAN_FALLBACK_2 = "Noto Naskh Arabic"
FONT_FAMILY_PERSIAN_FALLBACK_3 = "Noto Sans Arabic"
FONT_FAMILY_PERSIAN_FALLBACK_4 = "DejaVu Sans"
FONT_FAMILY_PERSIAN_FALLBACK_5 = "Segoe UI"
FONT_FAMILY_PERSIAN_FALLBACK_6 = "Helvetica"
FONT_FAMILY_SYSTEM            = "TkDefaultFont"

# Font sizes (1:1 with web/styles.css font-size values)
FONT_SIZE_H1     = 32    # .onboarding-title
FONT_SIZE_H2     = 24    # screen headings
FONT_SIZE_H3     = 22    # .greeting
FONT_SIZE_H4     = 20    # .modal-title
FONT_SIZE_BODY   = 15    # body text
FONT_SIZE_LABEL  = 14    # .section-header, .settings-label
FONT_SIZE_CAP    = 12    # .card-subtitle, .chip
FONT_SIZE_MICRO  = 10    # .nav-btn span
FONT_SIZE_DISPLAY = 42   # .splash-title
FONT_SIZE_STAT   = 32    # .stat-total, .timer-time
FONT_SIZE_BIG_NUM = 26   # .today-total
FONT_SIZE_XL_NUM  = 96   # .splash-logo letter

# Font weights
WEIGHT_REGULAR  = "normal"
WEIGHT_MEDIUM   = "normal"  # Tkinter only supports normal/bold
WEIGHT_BOLD     = "bold"

# =====================================================================
# === WINDOW ===
# =====================================================================
WINDOW_WIDTH   = 540
WINDOW_HEIGHT  = 900
MIN_WIDTH      = 380
MIN_HEIGHT     = 600
APP_NAME       = "Rask"
APP_NAME_FA    = "رَسک"
APP_VERSION    = "1.0.0"
APP_TAGLINE_FA = "زمان، ظریف."
APP_TAGLINE_EN = "Time, refined."
APP_COPYRIGHT  = "© 2026 Littlehomemade Studio"
APP_STUDIO     = "Littlehomemade Studio"

# =====================================================================
# === ANIMATIONS (1:1 with web/styles.css @keyframes durations) ===
# =====================================================================
SPLASH_DURATION_MS    = 2200   # web/js/app.js setTimeout(... 2200)
SPLASH_FADE_MS        = 400
ONBOARDING_FADE_MS    = 400
SCREEN_FADE_MS        = 250
MODAL_SLIDE_MS        = 300
TOAST_DURATION_MS     = 2600
TIMER_TICK_MS         = 1000
PULSE_INTERVAL_MS     = 2000
GOLD_GLOW_INTERVAL_MS = 3000
SPIN_INTERVAL_MS      = 3000

# Easing curves (used by canvas animations)
EASE_OUT_CUBIC    = lambda t: 1 - (1 - t) ** 3
EASE_IN_OUT_CUBIC = lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
EASE_OUT_BACK     = lambda t: 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2
EASE_OUT_QUART    = lambda t: 1 - (1 - t) ** 4
EASE_OUT_EXPO     = lambda t: 1 if t == 1 else 1 - 2 ** (-10 * t)
LINEAR            = lambda t: t

# =====================================================================
# === SHADOWS / GLOWS (mirror box-shadow rules in styles.css) ===
# =====================================================================
SHADOW_FAB       = "0 6px 16px rgba(212,175,55,0.35)"
SHADOW_TOAST     = "0 4px 12px rgba(0,0,0,0.4)"
GLOW_GOLD_WEAK   = "0 0 8px rgba(212,175,55,0.15)"
GLOW_GOLD_MED    = "0 0 16px rgba(212,175,55,0.25)"
GLOW_GOLD_STRONG = "0 0 24px rgba(212,175,55,0.35)"

# =====================================================================
# === Z-INDEX STACK (mirror styles.css z-index values) ===
# =====================================================================
Z_SPLASH       = 1000
Z_MODAL        = 200
Z_TOAST        = 300
Z_BOTTOM_NAV   = 100
Z_FAB          = 90
Z_SCREEN       = 1

# =====================================================================
# === DEFAULT CATEGORIES (1:1 with web/js/db.js seedDefaults) ===
# =====================================================================
DEFAULT_CATEGORIES = [
    {"key": "FOCUS",    "color": "#D4AF37", "name_en": "Focus",    "name_fa": "تمرکز",     "icon": "ring",       "order_index": 0},
    {"key": "LEARN",    "color": "#7B9BC9", "name_en": "Learn",    "name_fa": "یادگیری",   "icon": "book",       "order_index": 1},
    {"key": "WORK",     "color": "#C9A84C", "name_en": "Work",     "name_fa": "کار",       "icon": "briefcase",  "order_index": 2},
    {"key": "HEALTH",   "color": "#7BC97B", "name_en": "Health",   "name_fa": "سلامتی",    "icon": "heart",      "order_index": 3},
    {"key": "CREATIVE", "color": "#D49ABF", "name_en": "Creative", "name_fa": "خلاقیت",    "icon": "palette",    "order_index": 4},
    {"key": "SOCIAL",   "color": "#E8B85A", "name_en": "Social",   "name_fa": "اجتماعی",   "icon": "users",      "order_index": 5},
    {"key": "REST",     "color": "#9A9A9F", "name_en": "Rest",     "name_fa": "استراحت",   "icon": "moon",       "order_index": 6},
]

DEFAULT_DAILY_GOAL_MIN = 120

# =====================================================================
# === BACKUP FORMAT (1:1 with web/js/backup.js) ===
# =====================================================================
BACKUP_MAGIC      = b"RASK"
BACKUP_VERSION    = 1
BACKUP_KDF_ITER   = 200_000
BACKUP_SALT_LEN   = 16
BACKUP_IV_LEN     = 12
BACKUP_KEY_LEN    = 32      # AES-256
BACKUP_FILE_EXT   = ".rask"
BACKUP_MIN_PWD_LEN = 6

# =====================================================================
# === PIN (1:1 with web/js/biometric.js) ===
# =====================================================================
PIN_KDF_ITER    = 200_000
PIN_SALT_LEN    = 16
PIN_KEY_LEN     = 32
PIN_MIN_LEN     = 4
PIN_MAX_LEN     = 6

# =====================================================================
# === STREAK BADGES (1:1 with web/js/timer.js bumpStreak) ===
# =====================================================================
STREAK_BADGES = [
    (3,   "streak_3",   "3-day streak"),
    (7,   "streak_7",   "7-day streak"),
    (30,  "streak_30",  "30-day streak"),
    (100, "streak_100", "100-day streak"),
]

# Additional milestone badges (extends web edition)
MILESTONE_BADGES = [
    ("first_activity",  "first_activity",  "First activity"),
    ("ten_activities",  "ten_activities",  "10 activities"),
    ("hundred_activities", "hundred_activities", "100 activities"),
    ("thousand_activities", "thousand_activities", "1000 activities"),
    ("first_goal",      "first_goal",      "First goal set"),
    ("first_streak",    "first_streak",    "First streak"),
    ("week_streak",     "week_streak",     "7-day streak"),
    ("month_streak",    "month_streak",    "30-day streak"),
    ("year_streak",     "year_streak",     "100-day streak"),
    ("early_bird",      "early_bird",      "Early bird (before 6am)"),
    ("night_owl",       "night_owl",       "Night owl (after midnight)"),
    ("weekend_warrior", "weekend_warrior", "Weekend warrior"),
    ("perfectionist",   "perfectionist",   "All goals met in a day"),
    ("consistency_king", "consistency_king", "30 days in a row"),
    ("marathon",        "marathon",        "4+ hour single activity"),
    ("explorer",        "explorer",        "All 7 categories used"),
]

# =====================================================================
# === STATS PRESETS (1:1 with web/js/app.js PRESETS) ===
# =====================================================================
STATS_PRESETS = [
    ("today",  "todayPreset"),
    ("7d",     "sevenDays"),
    ("30d",    "thirtyDays"),
    ("month",  "thisMonth"),
    ("year",   "thisYear"),
]

# =====================================================================
# === TIMER STATE KEYS ===
# =====================================================================
TIMER_KV_KEY          = "rask.timer"
TIMER_MIN_SAVE_SEC    = 5        # don't save activities shorter than 5s (mirror timer.js)
TIMER_TICK_MS_DESKTOP = 1000

# =====================================================================
# === NOTIFICATIONS ===
# =====================================================================
REMINDER_DEFAULT_HOUR = 20   # 8 PM default reminder
REMINDER_DEFAULT_MIN  = 0

# =====================================================================
# === KEYBOARD SHORTCUTS (desktop-only feature) ===
# =====================================================================
SHORTCUTS = [
    ("Ctrl+1",      "switch_home",      "Go to Home"),
    ("Ctrl+2",      "switch_goals",     "Go to Goals"),
    ("Ctrl+3",      "switch_stats",     "Go to Stats"),
    ("Ctrl+4",      "switch_settings",  "Go to Settings"),
    ("Ctrl+N",      "quick_log",        "Quick log"),
    ("Ctrl+T",      "toggle_timer",     "Start/pause timer"),
    ("Ctrl+S",      "stop_save_timer",  "Stop & save timer"),
    ("Ctrl+E",      "export_csv",       "Export CSV"),
    ("Ctrl+P",      "export_pdf",       "Export PDF"),
    ("Ctrl+B",      "export_backup",    "Export backup"),
    ("Ctrl+L",      "lock_app",         "Lock app"),
    ("Ctrl+,",      "settings",         "Settings"),
    ("Esc",         "close_modal",      "Close modal"),
    ("Ctrl+Z",      "undo_last",        "Undo last activity"),
    ("Ctrl+F",      "search",           "Search activities"),
    ("Ctrl+R",      "refresh",          "Refresh current screen"),
    ("?",           "show_shortcuts",   "Show shortcuts"),
]

# =====================================================================
# === DATA DIRECTORY ===
# =====================================================================
import os
import sys
from pathlib import Path

def _data_dir() -> Path:
    """Return the per-user data directory for Rask (mirrors web localStorage)."""
    # On Windows: %LOCALAPPDATA%/rask
    # On macOS:   ~/Library/Application Support/rask
    # On Linux:   ~/.local/share/rask
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    p = Path(base) / "rask"
    p.mkdir(parents=True, exist_ok=True)
    return p

DATA_DIR = _data_dir()
DB_PATH  = DATA_DIR / "rask.db"
LOG_PATH = DATA_DIR / "rask.log"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# === DIRECTION ===
# =====================================================================
def is_rtl(lang: str) -> bool:
    """Return True if the given language is right-to-left."""
    return lang in ("fa", "ar", "he", "ur")


# =====================================================================
# === HELPER COLOR FUNCTIONS ===
# =====================================================================
def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (r, g, b) tuple."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert (r, g, b) to #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> str:
    """Convert #RRGGBB to rgba(r, g, b, a) string."""
    r, g, b = hex_to_rgb(hex_str)
    return f"rgba({r}, {g}, {b}, {alpha})"


def lighten(hex_str: str, factor: float) -> str:
    """Lighten a hex color by a factor (0-1, where 1 = white)."""
    r, g, b = hex_to_rgb(hex_str)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return rgb_to_hex(r, g, b)


def darken(hex_str: str, factor: float) -> str:
    """Darken a hex color by a factor (0-1, where 1 = black)."""
    r, g, b = hex_to_rgb(hex_str)
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return rgb_to_hex(r, g, b)


def blend(hex_a: str, hex_b: str, t: float) -> str:
    """Blend two hex colors. t=0 → a, t=1 → b."""
    ar, ag, ab = hex_to_rgb(hex_a)
    br, bg, bb = hex_to_rgb(hex_b)
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    b = int(ab + (bb - ab) * t)
    return rgb_to_hex(r, g, b)


def heatmap_color(t: float) -> str:
    """Return heatmap color for intensity t (0-1). Mirrors charts.js Heatmap.intensityColor."""
    if t <= 0:
        return rgb_to_hex(*HEATMAP_STEPS[0])
    if t >= 1:
        return rgb_to_hex(*HEATMAP_STEPS[-1])
    n = len(HEATMAP_STEPS) - 1
    idx = t * n
    i = int(idx)
    frac = idx - i
    if i >= n:
        return rgb_to_hex(*HEATMAP_STEPS[-1])
    a = HEATMAP_STEPS[i]
    b = HEATMAP_STEPS[i + 1]
    r = int(a[0] + (b[0] - a[0]) * frac)
    g = int(a[1] + (b[1] - a[1]) * frac)
    bb = int(a[2] + (b[2] - a[2]) * frac)
    return rgb_to_hex(r, g, bb)


# =====================================================================
# === APP METADATA ===
# =====================================================================
APP_DESCRIPTION_FA = "پیگیری‌گر زمان و فعالیت، آفلاین و خصوصی"
APP_DESCRIPTION_EN = "Time & activity tracker, offline and private"

APP_FEATURES = [
    ("smart_logging",     "Smart activity logging (manual + stopwatch + voice + templates)"),
    ("goals_streaks",     "Goals & streaks with milestone badges"),
    ("time_aggregation",  "Advanced time aggregation with custom date ranges"),
    ("rich_statistics",   "Rich statistics & insights with charts"),
    ("widgets_actions",   "Live timer widget with quick actions"),
    ("backup_sync",       "AES-256-GCM encrypted backup & restore"),
    ("onboarding",        "Minimal splash & onboarding flow"),
    ("rtl_persian",       "Full RTL Persian + Jalali calendar support"),
    ("offline_first",     "100% offline-first, no internet required"),
    ("pin_biometric",     "PIN lock (PBKDF2-SHA256) + biometric option"),
    ("export_pdf_csv",    "Export reports as PDF and CSV"),
    ("recurring",         "Recurring activities (daily/weekly/monthly)"),
    ("reminders",         "Customizable daily reminders"),
    ("search_filter",     "Search and filter activities"),
    ("custom_categories", "Create custom categories with colors"),
    ("keyboard_shortcuts","Keyboard shortcuts for power users"),
]
