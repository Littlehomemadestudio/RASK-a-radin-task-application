# Rask — Desktop Edition (Python + Tkinter)

A 1:1 desktop port of the Rask web PWA. Same gold-on-dark theme, same screens,
same flows, same charts, same encrypted backup, same Jalali calendar, same
onboarding + splash + lock. Runs on any OS with Python 3.9+.

## Run

```bash
cd desktop
pip install -r requirements.txt
python main.py
```

That's it. The window opens at 540x900 (mobile-aspect), shows the splash for
2.2s, runs through onboarding on first launch, then lands on the main view
with Home / Goals / Stats / Settings bottom-nav and a gold FAB.

## Modules

```
desktop/
├── main.py                       ← entry point
├── requirements.txt
└── rask/
    ├── __init__.py
    ├── config.py                 ← colors, spacing, defaults (mirror of styles.css :root)
    ├── i18n.py                   ← Persian + English string catalog (mirror of i18n.js)
    ├── date_utils.py             ← Gregorian + Jalali calendar (mirror of date-utils.js)
    ├── database.py               ← SQLite schema + queries (mirror of db.js IndexedDB)
    ├── crypto.py                 ← PIN hashing + AES-256-GCM backup (mirror of biometric.js + backup.js)
    ├── timer_service.py          ← Background stopwatch + goal/streak logic (mirror of timer.js)
    ├── charts.py                 ← Canvas: ProgressRing / BarChart / DonutChart / Heatmap (mirror of charts.js)
    ├── exporters.py              ← PDF (reportlab) + CSV export (mirror of export-pdf.js + export-csv.js)
    ├── voice.py                  ← Voice input (mirror of voice.js; optional)
    ├── app.py                    ← Main controller (mirror of app.js)
    └── ui/
        ├── __init__.py
        ├── theme.py              ← Tkinter styling helpers (mirror of styles.css)
        ├── screens_splash.py     ← Splash + Onboarding + Lock (mirror of #splash / #onboarding / #lock)
        ├── screens_main.py       ← Home / Goals / Stats / Settings (mirror of #screen-*)
        └── modals.py             ← QuickLog / Template / Goal modals (mirror of #*Modal)
```

## Feature parity with the web edition

| Web (browser API) | Desktop (Python API) |
|---|---|
| IndexedDB | `sqlite3` (WAL mode, thread-safe RLock) |
| localStorage (timer state) | `kv` table in SQLite |
| Web Crypto (AES-256-GCM) | `cryptography.hazmat.primitives.ciphers.aead.AESGCM` |
| Web Crypto (PBKDF2 PIN) | `hashlib.pbkdf2_hmac('sha256', …)` |
| WebAuthn (biometric) | N/A on desktop → `is_biometric_available()` returns False (UI shows the same fallback) |
| Web Speech API | `speech_recognition` package (optional — pip install) |
| Canvas 2D charts | `tkinter.Canvas` drawings |
| jsPDF | `reportlab` |
| Blob download | `filedialog.asksaveasfilename` |
| Service Worker offline | Native — runs fully offline by design |
| `:root` CSS variables | `rask.config` constants |

## Data location

The SQLite database lives at `~/.rask/rask.db` (created on first run).

## Notes

- The desktop edition has no WebAuthn, so biometric setup will show "Biometric
  unavailable" — exactly like the web edition on a browser without a platform
  authenticator. PIN lock works identically.
- Voice input requires `speech_recognition` + a working microphone. If not
  installed, the voice button shows the same "❌" feedback as the web edition
  on an unsupported browser.
- All 7 features are functional: smart logging (manual + stopwatch + templates
  + voice), goals & streaks (with badges at 3/7/30/100 days), time aggregation
  (5 preset ranges + custom range queries), statistics (bar + donut + heatmap
  + trends + PDF/CSV export), notifications (live timer in window title),
  backup/restore (AES-256-GCM `.rask` files), and splash + 3-screen onboarding.
