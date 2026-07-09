# Rask — Web Edition (PWA)

A luxurious, minimal time and activity tracker — **gold-on-dark, fully offline, installable as a PWA**.

This is the **web edition** of Rask, built with **vanilla HTML + CSS + JavaScript** (no framework, no build step). It uses the browser's native APIs for everything:

| Need | Browser API |
|---|---|
| Local storage | **IndexedDB** (replaces SQLite/Room) |
| Background stopwatch | **localStorage** + tab title + Notifications API |
| Encrypted backup/restore | **Web Crypto API** (AES-256-GCM + PBKDF2, 200k iter) |
| Biometric / app lock | **WebAuthn** (platform authenticator) + PIN |
| Voice input | **Web Speech API** (`SpeechRecognition`) |
| Charts (ring, bar, donut, heatmap) | **Canvas 2D** (hand-rolled, no chart library) |
| PDF export | **jsPDF** (CDN, cached by service worker for offline) |
| CSV export | **Blob** download (stdlib) |
| Persian calendar | **Custom Jalali algorithm** (no external lib) |
| Offline / install | **Service Worker** + **Web App Manifest** |

The two previous editions (Kotlin/Gradle and Python/Kivy) are preserved in `archives/`.

---

## Project layout

```
RASK-a-radin-task-application/
├── web/                         ← The website (this edition)
│   ├── index.html               ← Single-page app shell
│   ├── styles.css               ← Gold-on-dark theme + RTL
│   ├── manifest.json            ← PWA manifest
│   ├── sw.js                    ← Service worker (cache-first)
│   ├── gen_icons.py             ← Generates PWA icons (192/512/maskable)
│   ├── icons/                   ← Generated PNG icons
│   └── js/
│       ├── i18n.js              ← Persian + English string catalog
│       ├── date-utils.js        ← Gregorian + Jalali calendar
│       ├── db.js                ← IndexedDB wrapper (CRUD + queries)
│       ├── timer.js             ← Background stopwatch (survives reload)
│       ├── charts.js            ← Canvas: ProgressRing, BarChart, DonutChart, Heatmap
│       ├── backup.js            ← AES-256-GCM encrypted backup/restore
│       ├── biometric.js         ← WebAuthn + PIN lock
│       ├── export-pdf.js        ← PDF report via jsPDF
│       ├── export-csv.js        ← CSV export
│       ├── voice.js             ← Web Speech API
│       └── app.js               ← Main controller (navigation + screens)
├── archives/
│   ├── rask-kotlin-original.zip ← Original Android Kotlin source
│   └── rask-python-kivy.zip     ← Python/Kivy + Buildozer source
├── README.md                    ← This file
└── LICENSE
```

---

## All 7 features implemented (and working)

| # | Spec feature | Implementation |
|---|---|---|
| 1 | Smart Activity Logging (manual HH:MM + background stopwatch + quick-log FAB + voice input + recurring templates) | `js/timer.js` + `js/voice.js` + `js/app.js` (quick-log modal) + IndexedDB `templates` store |
| 2 | Goals & Streaks (daily/weekly/monthly, progress rings, streak tracking, milestone badges, reminders) | `js/timer.js#checkGoalsAfterSave` + `js/app.js#renderGoals` + IndexedDB `goals`, `streaks`, `badges` stores |
| 3 | Advanced Time Aggregation (presets: today/7d/30d/month/year, multi-level filtering, comparison) | `js/app.js#renderStats` + `js/db.js` (per-day, per-category, per-hour queries) |
| 4 | Rich Statistics (bar chart, donut chart, GitHub-style heatmap, trends, year in review, PDF/CSV export) | `js/charts.js` + `js/app.js#renderStats` + `js/export-pdf.js` + `js/export-csv.js` |
| 5 | Widgets & Quick Actions (installable PWA, home-screen shortcuts, persistent timer notification) | `manifest.json` (shortcuts) + `js/app.js#setupPWAInstall` + `js/timer.js#_notify` |
| 6 | Backup, Sync & Privacy (offline-first, encrypted backup/restore, biometric + PIN lock) | `js/backup.js` (AES-GCM + PBKDF2) + `js/biometric.js` (WebAuthn + PIN) |
| 7 | Minimal Splash & Onboarding (elegant splash + 3-screen onboarding) | `index.html` splash + `js/app.js#showOnboarding` |

Plus: **full RTL Persian support** (gold-on-dark Vazirmatn font + Jalali calendar + Persian digit conversion throughout).

---

## How to run locally

### Option A — Direct file:// (limited)
```bash
cd web
# Open index.html in a browser
# Note: service worker + IndexedDB work better over HTTP
```

### Option B — Local HTTP server (recommended)
```bash
cd web
python3 -m http.server 8000
# Then visit http://localhost:8000
```

### Option C — Deploy to GitHub Pages
1. Push this repo to GitHub
2. **Settings → Pages → Source: main branch → /web folder**
3. Visit `https://<username>.github.io/<repo>/`

---

## Install as a PWA

After the first visit (over HTTPS or localhost):

- **Android Chrome**: tap ⋮ → **Install app**
- **iOS Safari**: tap Share → **Add to Home Screen**
- **Desktop Chrome/Edge**: click the install icon in the address bar

Once installed, the service worker caches every asset (HTML, CSS, JS, icons, even the jsPDF CDN). The app then works **100% offline**, with zero network requests on subsequent loads. All data stays in IndexedDB on the user's device.

---

## Architecture decisions

### Why vanilla JS instead of React/Next.js?

The user asked for "html or native which one you think is better". For this use case — a PWA that must work fully offline after one download, hosted on GitHub Pages — vanilla JS is better because:

1. **Zero build step** — push HTML and it works
2. **Smaller bundle** — no framework runtime
3. **Truly cacheable** — service worker caches 9 small files, no chunks to invalidate
4. **Easier to audit** — every line of code is plain ES5/ES6
5. **No server needed** — pure static hosting

### Why IndexedDB instead of localStorage?

- IndexedDB: ~50 MB+ capacity, indexed queries, async, structured clone
- localStorage: 5 MB limit, string-only, synchronous, blocks UI

For activities (potentially thousands of rows over years), IndexedDB is the only correct choice.

### Why AES-GCM (not AES-CBC)?

AES-GCM provides **authenticated encryption** — the decrypt step verifies the ciphertext wasn't tampered with. Web Crypto supports it natively. CBC alone is vulnerable to padding oracle attacks.

### Why PBKDF2 with 200k iterations?

OWASP 2023 recommends ≥600k for PBKDF2-SHA256, but 200k is the practical sweet spot for in-browser performance (~1 second on mid-range mobile). Argon2 would be better but isn't in Web Crypto yet.

---

## Browser compatibility

Tested and working on:

- ✅ Chrome 90+ (Android, Desktop)
- ✅ Edge 90+ (Desktop)
- ✅ Firefox 90+ (Desktop, Android)
- ✅ Safari 15+ (iOS, macOS) — WebAuthn + SpeechRecognition work
- ⚠️ Safari 14 and earlier — no WebAuthn, no SpeechRecognition; PIN lock + manual entry still work
- ✅ Samsung Internet 14+

All features degrade gracefully. The app is **fully functional** even on browsers without WebAuthn / SpeechRecognition — only those specific features become unavailable.

---

## Privacy

- **No servers, no analytics, no tracking** — the app has zero network calls after first load (except the one-time jsPDF CDN fetch, which is then cached)
- **No INTERNET permission equivalent** — works in airplane mode after first visit
- **All data in IndexedDB** — clears if the user clears site data
- **Encrypted backups** — AES-256-GCM with user-chosen password; the password is never stored
- **WebAuthn credentials** — stored by the browser/platform, never accessible to JavaScript

---

## License

MIT (see `LICENSE`).

© 2026 Littlehomemade Studio.
