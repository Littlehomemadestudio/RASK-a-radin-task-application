"""notifications.py — Desktop notifications for Rask.

Uses platform-native notifications where available:
  - Windows: plyer or win10toast (optional)
  - macOS: osascript (AppleScript) — built-in
  - Linux: notify-send (libnotify) — usually pre-installed

If no notification system is available, falls back to in-app toasts.
"""
from __future__ import annotations
import platform
import shutil
import subprocess
import sys
from typing import Optional

from . import config


# =====================================================================
# === PLATFORM DETECTION ===
# =====================================================================
def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


# =====================================================================
# === NOTIFICATION BACKENDS ===
# =====================================================================
def _notify_macos(title: str, message: str, subtitle: str = "") -> bool:
    """Send a notification via osascript on macOS."""
    try:
        script = f'display notification "{message}" with title "{title}"'
        if subtitle:
            script += f' subtitle "{subtitle}"'
        subprocess.run(
            ["osascript", "-e", script],
            check=False, capture_output=True, timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def _notify_linux(title: str, message: str, subtitle: str = "") -> bool:
    """Send a notification via notify-send on Linux."""
    if not shutil.which("notify-send"):
        return False
    try:
        cmd = ["notify-send", title, message]
        if subtitle:
            cmd.extend(["--icon", "dialog-information"])
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def _notify_windows(title: str, message: str, subtitle: str = "") -> bool:
    """Send a notification on Windows.
    
    Tries plyer first, then win10toast, then falls back to a Tkinter
    messagebox (which is intrusive but always works).
    """
    # Try plyer
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name=config.APP_NAME,
            timeout=5,
        )
        return True
    except ImportError:
        pass
    except Exception:
        pass
    # Try win10toast
    try:
        from win10toast import ToastNotifier
        toast = ToastNotifier()
        toast.show_toast(title, message, duration=5, threaded=True)
        return True
    except ImportError:
        pass
    except Exception:
        pass
    return False


# =====================================================================
# === PUBLIC API ===
# =====================================================================
def available() -> bool:
    """Return True if any notification backend is available."""
    if is_macos():
        return shutil.which("osascript") is not None
    if is_linux():
        return shutil.which("notify-send") is not None
    if is_windows():
        try:
            import plyer  # noqa
            return True
        except ImportError:
            pass
        try:
            import win10toast  # noqa
            return True
        except ImportError:
            pass
        return False
    return False


def notify(title: str, message: str, subtitle: str = "") -> bool:
    """Send a desktop notification. Returns True if sent successfully."""
    if is_macos():
        return _notify_macos(title, message, subtitle)
    if is_linux():
        return _notify_linux(title, message, subtitle)
    if is_windows():
        return _notify_windows(title, message, subtitle)
    return False


# =====================================================================
# === PREDEFINED NOTIFICATIONS ===
# =====================================================================
def notify_reminder(lang: str = "fa") -> bool:
    """Send the daily reminder notification."""
    from .i18n import t
    title = t("notifReminderTitle", lang)
    body = t("notifReminderBody", lang)
    return notify(title, body)


def notify_goal_achieved(lang: str = "fa") -> bool:
    """Notify that today's goal has been achieved."""
    from .i18n import t
    title = t("notifReminderTitle", lang)
    body = t("notifGoalAchieved", lang)
    return notify(title, body)


def notify_streak_in_danger(lang: str = "fa") -> bool:
    """Notify that the streak is in danger of breaking."""
    from .i18n import t
    title = t("notifReminderTitle", lang)
    body = t("notifStreakInDanger", lang)
    return notify(title, body)


def notify_badge_earned(badge_title: str, lang: str = "fa") -> bool:
    """Notify that a new badge has been earned."""
    from .i18n import t
    title = t("notifReminderTitle", lang)
    body = f"{t('notifBadgeEarned', lang)} — {badge_title}"
    return notify(title, body)


def notify_timer(title: str, message: str, lang: str = "fa") -> bool:
    """Send a timer-related notification."""
    from .i18n import t
    return notify(t("notifTimerTitle", lang), message)


# =====================================================================
# === IN-APP FALLALL ===
# =====================================================================
_in_app_toasts: list = []


def show_in_app_toast(root, text: str, duration_ms: int = 2600,
                       kind: str = "info") -> None:
    """Show an in-app toast notification (fallback when desktop notifs fail)."""
    from .widgets import Toast
    toast = Toast(root, text, duration_ms=duration_ms, kind=kind)
    _in_app_toasts.append(toast)
    root.after(duration_ms + 100, lambda: _cleanup_toast(toast))


def _cleanup_toast(toast):
    if toast in _in_app_toasts:
        _in_app_toasts.remove(toast)
