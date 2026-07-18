# Rask — Desktop Edition

A luxurious, minimal time & activity tracker. Gold-on-dark. Fully offline. 1:1 mirror of the [web/PWA edition](../web/).

```
   ┌────────────────────────────────┐
   │                                │
   │              ╱╲                │
   │             ╱  ╲               │
   │            │  R  │              │
   │             ╲  ╱               │
   │              ╲╱                │
   │                                │
   │            رَسک                 │
   │         زمان، ظریف.            │
   │                                │
   └────────────────────────────────┘
```

## Quick start

```bash
# 1. From the desktop/ folder
cd desktop

# 2. (Optional but recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.\.venv\Scripts\Activate.ps1     # Windows PowerShell

# 3. Install the two optional packages
pip install cryptography reportlab

# 4. Run
python main.py
```

Requires **Python 3.9+** (3.11 or 3.12 recommended). The UI uses **Tkinter**, which ships with Python — no extra UI library needed.

## Why Tkinter?

The original Rask was prototyped in Kivy (archived), but Kivy on Windows requires SDL2 wheels that often break on newer Python versions. Tkinter is built into Python, ships with native widgets on every platform, and has zero install friction. The custom Canvas-drawn widgets in `rask/widgets.py` match the gold-on-dark aesthetic of the web edition pixel-for-pixel.

## Features (1:1 mirror of web edition)

| # | Feature                    | Description                                                         |
|---|----------------------------|--------------------------------------------------------------------|
| 1 | Smart Activity Logging     | Manual HH:MM + stopwatch + quick-log FAB + voice input + templates |
| 2 | Goals & Streaks            | Daily / weekly / monthly goals, progress rings, streaks, milestone badges |
| 3 | Advanced Time Aggregation  | Custom date ranges, presets (today/7d/30d/month/year), comparison vs previous period |
| 4 | Rich Statistics & Insights | Bar / donut / heatmap charts, trends, percentile distribution, PDF + CSV export |
| 5 | Widgets & Quick Actions    | Live timer card with Pause/Stop, keyboard shortcuts, search        |
| 6 | Backup/Sync/Privacy        | Offline-first, AES-256-GCM encrypted backup, PIN lock (PBKDF2-SHA256) |
| 7 | Minimal Splash & Onboarding | Splash + 3-screen onboarding flow                                  |

Plus desktop-only extensions:
- **Recurring activities** (daily / weekly / monthly / weekdays / weekends / custom)
- **Edit activities** (click any activity in the list to edit/delete)
- **Full-text search** (Ctrl+F)
- **Keyboard shortcuts** (Ctrl+1-4 for tabs, Ctrl+N for quick log, Ctrl+T to toggle timer, Ctrl+Z to undo, ? for help)
- **Custom categories** (create your own with color picker)
- **Statistics scoring** (productivity / consistency / balance 0-100 scores)
- **Insights** (auto-generated observations about your patterns)

## Keyboard shortcuts

| Shortcut       | Action                    |
|----------------|---------------------------|
| `Ctrl+1`       | Go to Home                |
| `Ctrl+2`       | Go to Goals               |
| `Ctrl+3`       | Go to Stats               |
| `Ctrl+4`       | Go to Settings            |
| `Ctrl+N`       | Quick log                 |
| `Ctrl+T`       | Start/pause timer         |
| `Ctrl+S`       | Stop & save timer         |
| `Ctrl+E`       | Export CSV                |
| `Ctrl+P`       | Export PDF                |
| `Ctrl+B`       | Export backup             |
| `Ctrl+L`       | Lock app                  |
| `Ctrl+F`       | Search activities         |
| `Ctrl+Z`       | Undo last activity        |
| `Ctrl+R`       | Refresh current screen    |
| `Ctrl+,`       | Settings                  |
| `?`            | Show all shortcuts        |
| `Esc`          | Close modal               |

## Project layout

```
desktop/
├── main.py                  # ← python main.py
├── requirements.txt
├── README.md
└── rask/
    ├── __init__.py
    ├── config.py            # Theme constants, defaults, animations
    ├── i18n.py              # Persian + English string catalog (~450 strings)
    ├── date_utils.py        # Gregorian + Jalali (Borkowski algorithm)
    ├── database.py          # SQLite schema + CRUD + analytics queries
    ├── crypto.py            # PBKDF2-SHA256 PIN + AES-256-GCM backups
    ├── timer_service.py     # Background stopwatch with persistence
    ├── charts.py            # ProgressRing, BarChart, DonutChart, Heatmap, LineChart
    ├── exporters.py         # CSV, JSON, PDF exports
    ├── icons.py             # 80+ SVG-rendered icons
    ├── widgets.py           # 25+ custom Canvas-drawn widgets (GoldButton, Card, Chip, FAB, …)
    ├── analytics.py         # Trends, percentiles, scores, insights
    ├── recurring.py         # Recurring activities engine
    ├── notifications.py     # Desktop notifications (Windows/macOS/Linux)
    ├── voice.py             # Voice input (optional)
    └── ui/
        ├── __init__.py
        ├── theme.py         # apply_theme + widget factories
        ├── screens_splash.py # Splash + Onboarding + Lock screens
        ├── screens_main.py  # Home + Goals + Stats + Settings screens
        └── modals.py        # QuickLog + Template + Goal + EditActivity + Search + Recurring + Shortcuts
```

## Where your data lives

All data is stored locally at:
- **Windows**: `%LOCALAPPDATA%\rask\rask.db`
- **macOS**: `~/Library/Application Support/rask/rask.db`
- **Linux**: `~/.local/share/rask/rask.db`

Encrypted backups (`.rask` files) are AES-256-GCM sealed with a password you choose — safe to drop into Google Drive or email. The format is identical to the web edition, so backups are interchangeable.

## Privacy

- **No accounts.** No signup, no login, no cloud.
- **No tracking.** No analytics, no telemetry, no ads.
- **No internet required.** The app works fully offline. The only network call is optional voice recognition (Google's free API), and only if you explicitly tap the microphone button.

## Troubleshooting

| Problem                                    | Fix                                                                                    |
|--------------------------------------------|----------------------------------------------------------------------------------------|
| `ModuleNotFoundError: tkinter`             | Reinstall Python from python.org and tick "tcl/tk and IDLE" in the installer.          |
| Persian text shows as squares              | Install **Vazirmatn** font from Google Fonts.                                          |
| `pip install cryptography` fails on 3.13+  | Use Python 3.11 or 3.12, or upgrade pip: `pip install --upgrade pip`.                  |
| Voice input doesn't work                   | `pip install SpeechRecognition pyaudio` (Linux: also `apt install portaudio19-dev`).   |
| Window opens then closes immediately       | Run from terminal so you can see the traceback.                                        |
| Want to reset everything                   | Delete the `rask.db` file in the data directory above.                                 |

## License

© 2026 Littlehomemade Studio. All rights reserved.
