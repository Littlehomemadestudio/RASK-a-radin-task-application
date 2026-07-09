# Rask — A Luxurious Time & Activity Tracker

> **A minimal, gold-on-dark time and activity tracker for Android.** Local-first, fully offline, with full RTL Persian support.

<p align="center">
  <img src="app/src/main/res/drawable/ic_splash_logo.xml" width="120" alt="Rask logo" />
</p>

---

## ✨ Features

### 1. Smart Activity Logging
- Title + date picker + duration (manual `HH:MM` or built-in **background stopwatch**)
- Optional category, tag, color label, notes
- **Quick-log FAB** for instant entry from anywhere in the app
- **Recurring templates** — save frequent activities for one-tap logging
- **Voice input** for activity titles (uses the system speech recognizer)

### 2. Goals & Streaks
- Set **daily / weekly / monthly** goals per category or overall
- Visual **progress rings** on the home screen
- **Streak tracking** with deep walk-back computation
- **Milestone badges** at 3 / 7 / 30 / 100 days
- **Gentle reminders** via WorkManager when behind on a daily goal

### 3. Advanced Time Aggregation
- Custom date ranges + presets: today, yesterday, this week, this month, last 30 days, this year, all time
- Multi-level filtering by category and/or tag (SQL-level, not in-memory)
- (Trend / comparison hooks wired into the ViewModel for easy extension)

### 4. Rich Statistics & Insights
- **Bar chart** (by category) and **donut chart** (by tag) via MPAndroidChart
- **GitHub-style heatmap** — 52-week daily activity intensity in shades of gold
- Trends: weekly average, best day, peak hour, monthly growth
- **PDF export** (Android `PdfDocument`) and **CSV export**
- Year-in-review style summary (the heatmap doubles as one)

### 5. Widgets & Quick Actions
- **Home-screen widget** showing today's total + a quick-log button
- Foreground **stopwatch service** with live timer notification + pause/stop controls
- Notification with live elapsed time + tap-to-open

### 6. Backup, Sync & Privacy
- **Local-first** — all data in a Room database on device
- **Encrypted backup** to a `.rask` file (AES-256-CBC + PBKDF2-HMAC-SHA256, 200K iterations)
- **App lock** with biometrics + 4-digit PIN (SHA-256 hashed)
- **No accounts, no telemetry, no network permissions** — data never leaves the device

### 7. Minimal Splash & Onboarding
- Elegant splash: gold "R" wordmark fading in on black (uses the Android 12+ SplashScreen API)
- 3-screen onboarding with gold-on-black illustrations
- No forced sign-ups or invasive permissions

---

## 🎨 Design

| Token | Value |
|-------|-------|
| Background | `#0A0A0B` (deep matte black) |
| Card | `#1B1B1E` with `#2A2A2F` border |
| Primary accent | `#D4AF37` (warm gold) |
| Gold variants | `#C9A84C`, `#E6C66E`, `#7A6420` |
| Text | `#F5EEDC` (cream) / `#B8B8BD` (light gray) / `#7A7A82` (gray) |
| Heatmap gradient | 5-step gold intensity from `#1A1A1D` → `#D4AF37` |

Typography uses the system `sans-serif` family at Light (300) and Regular (400) weights, which guarantees Persian (Farsi) glyph coverage on every Android 7+ device without bundling custom fonts.

Animations are intentionally subtle — soft gold pulse on the FAB, fade transitions between activities, gentle progress ring fills.

---

## 🏗 Architecture

```
com.rask.app/
├── RaskApplication.kt           # Service locator (no DI framework)
├── data/
│   ├── db/                       # Room: entities, DAOs, database, converters
│   │   ├── entity/               # Activity, Category, Goal, Streak, Template
│   │   └── dao/                  # CRUD + aggregation queries
│   ├── repository/               # Activity, Category, Goal, Template repos
│   ├── prefs/PreferenceManager.kt  # DataStore-backed app prefs
│   └── backup/BackupManager.kt     # AES-256 encrypted backup/restore
├── service/TimerService.kt       # Foreground stopwatch service
├── ui/
│   ├── splash/SplashActivity.kt  # Splash + routing
│   ├── onboarding/               # 3-screen intro
│   ├── main/MainActivity.kt      # Bottom-nav host
│   ├── home/                     # Home tab + QuickLog + templates
│   ├── stats/                    # Charts + heatmap + export
│   ├── goals/                    # Goals + streaks
│   ├── settings/                 # Settings + LockActivity + PIN setup
│   ├── common/ProgressRingView.kt  # Shared ring widget
│   └── theme/                    # (styles in res/values)
├── utils/                        # DateUtils, Haptics, LocaleHelper, Notifs
├── widget/                       # Home-screen widget
└── work/ReminderWorker.kt        # Gentle reminders
```

**Pattern:** MVVM with `AndroidViewModel` + `LiveData` + Room `Flow`. View binding throughout. Navigation Component for bottom-nav routing. No DI framework — a small `RaskApplication` service locator keeps the dependency surface minimal.

---

## 📱 Compatibility

| Target | Value |
|--------|-------|
| `minSdk` | 24 (Android 7.0 — covers ~98% of active devices) |
| `targetSdk` | 34 (Android 14) |
| `compileSdk` | 34 |
| Java | 17 |
| Kotlin | 1.9.22 |
| AGP | 8.2.2 |
| `coreLibraryDesugaring` | enabled — `java.time` works on Android 7+ |

The app uses:
- `androidx.core:core-splashscreen` for the Android 12+ splash API with graceful fallback
- Material 3 components via `com.google.android.material:material:1.11.0`
- AppCompat per-app language API (`AppCompatDelegate.setApplicationLocales`) for language switching
- `supportsRtl="true"` + `textDirection="locale"` for full RTL Persian layout

No Compose — keeps the APK small and avoids newer-API surface issues on older devices.

---

## 🛠 Build

### Requirements
- **Android Studio Iguana (2023.2.1)** or newer
- **JDK 17**
- Android SDK with `platform-34` and `build-tools 34.0.0`

### From Android Studio
1. `File → Open` and select the cloned repository root.
2. Let Gradle sync.
3. Press **Run** (or **Shift+F10**) to deploy to a connected device/emulator.

### From command line
```bash
# Debug APK
./gradlew assembleDebug

# Release APK (debug-signed for now — replace with your own keystore for Play Store)
./gradlew assembleRelease

# Install on connected device
./gradlew installDebug
```

After a successful build, the APKs live in:
- `app/build/outputs/apk/debug/app-debug.apk`
- `app/build/outputs/apk/release/app-release.apk`

### First-run setup
The app will seed default categories (Work, Study, Exercise, Reading, Meditation, Hobby, Other) on first launch. You can edit, archive, or add your own in the Quick-Log category dropdown.

---

## 📂 Repository

This is the canonical Rask source. Issues and PRs are welcome.

```
git clone https://github.com/Littlehomemadestudio/RASK-a-radin-task-application.git
cd RASK-a-radin-task-application
```

---

## 🔐 Privacy

Rask has **no INTERNET permission**. Data is stored in a Room database in app-private storage. Encrypted backups use AES-256-CBC with PBKDF2-HMAC-SHA256 key derivation (200,000 iterations). Backups never include your PIN hash.

The app explicitly opts out of Google cloud backup/restore (`fullBackupContent` excludes everything).

---

## 📜 License

MIT — see [LICENSE](LICENSE) for details.

---

## 🙏 Credits

- Charts: [MPAndroidChart](https://github.com/PhilJay/MPAndroidChart) by PhilJay
- Icons: hand-rolled vector drawables inspired by Material Symbols
- The AndroidX team for the per-app language API, SplashScreen API, and DataStore
