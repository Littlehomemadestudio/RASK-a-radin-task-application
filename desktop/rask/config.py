"""config.py — Rask gold-on-dark theme constants (identical to web edition)."""

# === Colors (match styles.css :root) ===
MATTE_BLACK = "#0E0E10"
CHARCOAL = "#1A1A1D"
SURFACE = "#222226"
SURFACE_HI = "#2C2C30"
GOLD = "#D4AF37"
GOLD_SOFT = "#C9A84C"
GOLD_DIM = "#7A6620"
TEXT = "#E8E8E8"
TEXT_DIM = "#9A9A9F"
TEXT_FAINT = "#5C5C60"
SUCCESS = "#7BC97B"
WARNING = "#E8B85A"
DANGER = "#D4625A"
DIVIDER = "#2C2C30"

# Heatmap intensity steps (match charts.js Heatmap.intensityColor)
HEATMAP_STEPS = [
    (14, 14, 16),
    (48, 40, 16),
    (80, 64, 20),
    (120, 96, 28),
    (212, 175, 55),
]

# === Spacing (match --space-*) ===
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32
SPACE_XXXL = 48

# === Radii (match --radius-*) ===
RADIUS_SM = 6
RADIUS_MD = 12
RADIUS_LG = 18
RADIUS_PILL = 999

# === Window ===
WINDOW_WIDTH = 540
WINDOW_HEIGHT = 900
APP_NAME = "Rask"
APP_VERSION = "1.0.0"
APP_TAGLINE_FA = "زمان، ظریف."
APP_TAGLINE_EN = "Time, refined."

# === Default categories (match db.js seedDefaults) ===
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

# === Backup format (match backup.js) ===
BACKUP_MAGIC = b"RASK"
BACKUP_VERSION = 1
BACKUP_KDF_ITER = 200_000
BACKUP_SALT_LEN = 16
BACKUP_IV_LEN = 12

# === PIN (match biometric.js) ===
PIN_KDF_ITER = 200_000
PIN_SALT_LEN = 16
PIN_MIN_LEN = 4

# === Badge milestones (match timer.js bumpStreak) ===
STREAK_BADGES = [
    (3,   "streak_3",   "3-day streak"),
    (7,   "streak_7",   "7-day streak"),
    (30,  "streak_30",  "30-day streak"),
    (100, "streak_100", "100-day streak"),
]
