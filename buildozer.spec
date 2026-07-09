[app]

# App metadata
title = Rask
package.name = rask
package.domain = com.rask

# Source code entry point
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,otf,json,xml,cfg,md,txt

# Versioning
version = 1.0.0

# Runtime requirements (Python packages that get bundled into the APK)
requirements =
    python3==3.11.6,
    kivy==2.3.0,
    kivymd==1.2.0,
    pyjnius==1.6.1,
    sqlite3,
    cryptography==42.0.5,
    Pillow==10.3.0,
    python-dateutil==2.9.0,
    requests==2.31.0,
    certifi==2024.2.2,
    six==1.16.0

# Android-specific build configuration
android.archs = arm64-v8a, armeabi-v7a
android.minapi = 24
android.api = 34
android.ndk = 25b

# Build settings (smaller APK)
android.debuggable = False
android.release_artifact = aab
android.add_compile_resources = True
android.allow_backup = False

# Permissions (offline-first — NO internet permission)
android.permissions =
    RECEIVE_BOOT_COMPLETED,
    FOREGROUND_SERVICE,
    FOREGROUND_SERVICE_SPECIAL_USE,
    POST_NOTIFICATIONS,
    SCHEDULE_EXACT_ALARM,
    USE_BIOMETRIC,
    USE_FINGERPRINT,
    WRITE_EXTERNAL_STORAGE,
    READ_EXTERNAL_STORAGE,
    VIBRATE,
    WAKE_LOCK,
    BIND_APPWIDGET

# Android manifest meta-data
android.meta_data =
    com.google.android.gms.car.application.SmallIcon=@drawable/ic_launcher

# Foreground service type
android.foreground_service_type = specialUse

# App class entry
orientation = portrait

# Splash screen
presplash.filename = presplash/presplash.png
presplash.color = #0E0E10

# Icon
icon.filename = assets/icons/ic_launcher.png

# Theme
android.theme = @style/Theme.Rask
android.windowSoftInputMode = adjustResize

# Buildozer
fullscreen = 0

# Logs
log_level = 2

# Enable RStrip for size
android.skip_compile_setup_py = True
android.use_setup_py = False

# Native SQLite + crypto
p4a.bootstrap = sdl2
p4a.download_p4a = True
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1

# Custom Java hooks for foreground service + notifications + widgets
# These are added to the Android project at build time
android.add_src = java-src
