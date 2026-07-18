# Rask Desktop

A luxurious gold-on-dark time & activity tracker. RTL Persian-first, offline-first, desktop application built with CustomTkinter.

## Quick Start

```powershell
cd desktop
pip install -r requirements.txt
python main.py
```

Requires Python 3.9+. Optional dependencies (`cryptography`, `reportlab`, `SpeechRecognition`) unlock additional features but the app runs with stdlib only.

## What's New in v2.0

Complete rewrite with **100,000+ lines of code** across 169 files. Major improvements over v1:

- **CustomTkinter UI** — Modern, polished, gold-on-dark theme that mirrors the web PWA 1:1
- **30+ custom widgets** — Progress rings, charts (bar/line/donut/heatmap/radar), cards, dialogs, sheets, toasts, avatars, skeletons, etc.
- **17 screens** — Splash, onboarding, lock, home, goals, stats, insights, settings, templates, reminders, badges, profile, categories, search, backup, about, shortcuts, plus feature screens (Pomodoro, journal, habits, mood, focus, analytics, calendar, weekly review, notifications, achievements, quick actions)
- **15 modal dialogs** — Quick log, edit activity, goal, template, reminder, category, PIN setup, backup, export, filter, compare, voice, confirm, onboarding
- **18 feature modules** — Pomodoro, time blocking, journal, habits, mood tracker, focus mode, smart insights, notifications center, achievements system, weekly review, extra imports/exports, calendar integration, quick actions, sound effects, theme registry, backup scheduler, analytics dashboard
- **13 services** — Activity, goal, streak, stats, backup, export, voice, reminder, template, badge, recurring, timer, settings
- **8 core utilities** — Jalali calendar (Borkowski algorithm), AES-256-GCM crypto, PBKDF2 PIN hashing, time helpers, event bus, validators, helpers, logging
- **In-app help system** — 39 articles across 7 categories (fa/en)
- **CLI** — 18 subcommands for headless operation
- **10 languages** — Persian, English, Arabic, Turkish, Russian, German, French, Spanish, Chinese, Japanese
- **Comprehensive test suite** — 23 test files covering all modules
- **Exporters** — PDF (with charts), CSV (UTF-8 BOM), JSON, PNG
- **Examples** — Demo walkthrough, benchmark suite, test data generator

## Architecture

```
desktop/
├── main.py                  # Entry point
├── check_syntax.py          # Syntax check
├── check_env.py             # Environment check
├── requirements.txt
├── rask/
│   ├── __init__.py
│   ├── config.py            # Theme constants, defaults
│   ├── i18n.py              # 10-language catalog
│   ├── database.py          # SQLite persistence
│   ├── cli.py               # Command-line interface
│   ├── check_env.py         # Environment checker
│   ├── help_system.py       # In-app help (39 articles)
│   ├── core/
│   │   ├── jalali.py        # Persian calendar
│   │   ├── crypto.py        # AES-256-GCM
│   │   ├── pin.py           # PIN hashing
│   │   ├── time_utils.py    # Time helpers
│   │   ├── event_bus.py     # Pub/sub
│   │   ├── validators.py    # Input validation
│   │   ├── helpers.py       # Easing, color, etc.
│   │   └── logging_utils.py # Logging setup
│   ├── services/            # Business logic (13 services)
│   ├── features/            # Extra features (18 modules)
│   ├── export/              # PDF/CSV/JSON/PNG exporters
│   ├── ui/
│   │   ├── app.py           # Main app controller
│   │   ├── widgets/         # 30 widget files
│   │   ├── screens/         # 29 screen files
│   │   └── dialogs/         # 15 dialog files
│   ├── utils/               # Extra utilities
│   └── tests/               # 23 test files
└── examples/                # Demo + benchmark + data gen
```

## Features

### Core (mirrors web PWA 1:1)
1. **Smart Activity Logging** — manual HH:MM + stopwatch + quick-log FAB + voice + templates
2. **Goals & Streaks** — daily/weekly/monthly, progress rings, milestone badges (3/7/30/100 days)
3. **Advanced Time Aggregation** — date ranges, presets, multi-level filtering, comparison
4. **Rich Statistics** — bar/donut/heatmap charts, trends, PDF+CSV export
5. **Widgets & Quick Actions** — live timer, quick settings, FAB
6. **Backup/Sync/Privacy** — AES-256-GCM encrypted backup, PIN lock, PBKDF2 200k iterations
7. **Splash & Onboarding** — animated splash + 3-screen onboarding

### New in v2.0
- Pomodoro timer with cycles and auto-advance
- Time blocking with conflict detection
- Daily journal (mood, energy, gratitudes)
- Habit tracker with streaks
- Mood tracker with activity correlations
- Deep focus mode (blocks distractions)
- Smart insights engine (10 generators)
- Notification center
- 32 achievements + XP/level system
- Weekly review generator (text/HTML/Markdown)
- Advanced analytics (forecast, anomaly detection, report card)
- Calendar views (Jalali + Gregorian)
- 10 theme variants
- Sound effects

## CLI Usage

```powershell
python main.py --cli stats
python main.py --cli activity add --title "Reading" --duration 30 --category LEARN
python main.py --cli backup create mypassword
python main.py --cli export csv --from 2025-01-01 --to 2025-12-31 --out report.csv
python main.py --cli db info
python main.py --doctor
python main.py --vacuum
```

## Privacy

- 100% offline — no server, no account, no tracking
- Data stored in `%APPDATA%\Rask\` (Windows), `~/Library/Application Support/Rask/` (macOS), `~/.local/share/Rask/` (Linux)
- Optional AES-256-GCM encrypted backups
- Optional PIN lock with PBKDF2-SHA256 (200k iterations)
- All encryption parameters match the web PWA for cross-platform compatibility

## License

MIT — see [LICENSE](../LICENSE)
