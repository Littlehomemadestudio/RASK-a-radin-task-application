"""
config.py — Theme colors, fonts, constants for Rask.

Centralises the gold-on-dark palette so every screen uses identical values.
"""
from kivy.utils import get_color_from_hex


# === Color palette (gold-on-dark, from spec) ===
class C:
    # Backgrounds
    MATTE_BLACK = get_color_from_hex("#0E0E10")
    CHARCOAL = get_color_from_hex("#1A1A1D")
    SURFACE = get_color_from_hex("#222226")
    SURFACE_HI = get_color_from_hex("#2C2C30")

    # Gold accents
    GOLD = get_color_from_hex("#D4AF37")
    GOLD_SOFT = get_color_from_hex("#C9A84C")
    GOLD_DIM = get_color_from_hex("#7A6620")

    # Text
    TEXT = get_color_from_hex("#E8E8E8")
    TEXT_DIM = get_color_from_hex("#9A9A9F")
    TEXT_FAINT = get_color_from_hex("#5C5C60")

    # Semantic
    SUCCESS = get_color_from_hex("#7BC97B")
    WARNING = get_color_from_hex("#E8B85A")
    DANGER = get_color_from_hex("#D4625A")

    # Separators
    DIVIDER = get_color_from_hex("#2C2C30")


# === Typography ===
FONT_REGULAR = "assets/fonts/vazirmatn.ttf"
FONT_BOLD = "assets/fonts/vazirmatn.ttf"  # variable font; weight chosen via markup
FONT_FALLBACK = "DejaVuSans"

FONT_SIZES = {
    "tiny": 10,
    "caption": 12,
    "small": 13,
    "body": 15,
    "h6": 16,
    "h5": 18,
    "h4": 22,
    "h3": 26,
    "h2": 32,
    "h1": 42,
    "hero": 56,
}

# === Spacing (dp) ===
SPACE = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
    "xxxl": 48,
}

# === Radii ===
RADIUS_SM = 6
RADIUS_MD = 12
RADIUS_LG = 18
RADIUS_PILL = 999

# === Animation durations ===
DUR_FAST = 0.15
DUR_MED = 0.28
DUR_SLOW = 0.5

# === Database ===
DB_NAME = "rask.db"
DB_VERSION = 1

# === Categories (preseeded) ===
DEFAULT_CATEGORIES = [
    ("_FOCUS", "#D4AF37", "Focus"),
    ("LEARN", "#7B9BC9", "Learn"),
    ("WORK", "#C9A84C", "Work"),
    ("HEALTH", "#7BC97B", "Health"),
    ("CREATIVE", "#D49ABF", "Creative"),
    ("SOCIAL", "#E8B85A", "Social"),
    ("REST", "#9A9A9F", "Rest"),
]

# === Activity kind ===
KIND_MANUAL = "manual"   # user enters HH:MM
KIND_STOPWATCH = "stopwatch"  # user starts/stops a timer

# === Goal period ===
PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"

# === App lock ===
LOCK_NONE = "none"
LOCK_PIN = "pin"
LOCK_BIOMETRIC = "biometric"

# === Onboarding flag ===
PREF_ONBOARDED = "onboarded"
PREF_LOCK_MODE = "lock_mode"
PREF_PIN_HASH = "pin_hash"
PREF_PIN_SALT = "pin_salt"
PREF_RTL = "rtl"
PREF_LANG = "lang"
PREF_FIRST_RUN = "first_run"
PREF_DAILY_GOAL_MIN = "daily_goal_min"

# === Notifications ===
NOTIF_CHANNEL_TIMER = "rask_timer"
NOTIF_CHANNEL_REMINDERS = "rask_reminders"
NOTIF_CHANNEL_GENERAL = "rask_general"

NOTIF_ID_TIMER = 1001
NOTIF_ID_REMINDER_BASE = 2000

# === Backup ===
BACKUP_MAGIC = b"RASK"
BACKUP_VERSION = 1
BACKUP_KDF_ITERATIONS = 200_000
BACKUP_SALT_LEN = 16
BACKUP_IV_LEN = 16
BACKUP_KEY_LEN = 32

# === Persian / RTL ===
SUPPORTED_LANGS = ("fa", "en")
DEFAULT_LANG = "fa"

# === Build info ===
APP_NAME = "Rask"
APP_VERSION = "1.0.0"
