"""
rask.services.settings_service
==============================

High-level typed settings API on top of :mod:`rask.database`'s
``settings`` table.

Provides:
  • ``get(key, default=None)`` / ``set(key, value)`` / ``delete(key)``
    / ``list()`` — generic typed access
  • Convenience accessors for every well-known setting
    (``language()``, ``theme()``, ``font_scale()``, etc.)
  • In-memory cache that is invalidated on every ``set()``
  • Event publication (``settings.changed`` always; ``language.changed``
    and ``theme.changed`` when those specific keys change)

Default values are seeded by :func:`rask.database.open_db` on first run.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception

__all__ = ["SettingsService", "settings_service"]

_log = get_logger("services.settings")


# =============================================================================
# === Settings keys                                                          ===
# =============================================================================

# Single source of truth for the well-known settings keys.  Mirrors
# the defaults seeded in rask.database._seed_defaults.
KEY_LANGUAGE: str = "lang"
KEY_THEME: str = "theme"
KEY_FONT_SCALE: str = "font_scale"
KEY_REDUCED_MOTION: str = "reduced_motion"
KEY_HIGH_CONTRAST: str = "high_contrast"
KEY_LOCK_MODE: str = "lock_mode"
KEY_AUTO_LOCK_SECONDS: str = "auto_lock_seconds"
KEY_FIRST_DAY_OF_WEEK: str = "first_day_of_week"
KEY_TIME_FORMAT: str = "time_format"
KEY_DATE_FORMAT: str = "date_format"
KEY_CALENDAR_SYSTEM: str = "calendar_system"
KEY_NOTIFY_SOUND: str = "notify_sound"
KEY_NOTIFY_VIBRATE: str = "notify_vibrate"
KEY_AUTO_BACKUP: str = "auto_backup"
KEY_DEVELOPER_MODE: str = "developer_mode"
KEY_USER_NAME: str = "user_name"
KEY_USER_EMAIL: str = "user_email"
KEY_USER_AVATAR_PATH: str = "user_avatar_path"
KEY_PIN_HASH: str = "pin_hash"
KEY_LAST_BACKUP_ISO: str = "last_backup_iso"
KEY_LAST_EXPORT_ISO: str = "last_export_iso"
KEY_ONBOARDED: str = "onboarded"
KEY_FIRST_RUN: str = "first_run"


# =============================================================================
# === SettingsService                                                        ===
# =============================================================================

class SettingsService:
    """Cached, typed wrapper around the ``settings`` table."""

    def __init__(self) -> None:
        # In-memory cache: key -> typed value.
        self._cache: Dict[str, Any] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Pre-load all settings into the cache."""
        self._load_all()
        _log.debug("SettingsService initialized (%d keys)", len(self._cache))

    def _load_all(self) -> None:
        """Load all settings from the DB into the cache."""
        try:
            rows = db.setting_list()
            self._cache = {}
            for r in rows:
                key = r.get("key")
                if not key:
                    continue
                # Use the DB's typed getter so values come back as the
                # right Python type (int / float / bool / json / string).
                self._cache[key] = db.setting_get(key)
            self._loaded = True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _refresh_key(self, key: str) -> None:
        """Refresh a single key in the cache from the DB."""
        try:
            self._cache[key] = db.setting_get(key)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})

    # ------------------------------------------------------------------
    # Generic typed access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the typed value of `key`, or `default` if not set."""
        if not key:
            return default
        if not self._loaded:
            self._load_all()
        if key in self._cache:
            v = self._cache[key]
            return v if v is not None else default
        # Fall back to DB (in case cache was invalidated by another process).
        try:
            v = db.setting_get(key, default)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return default
        self._cache[key] = v
        return v if v is not None else default

    def set(self, key: str, value: Any) -> None:
        """Set `key` to `value` (typed auto-detected).

        Publishes ``settings.changed`` with ``{key, value}``.  Also
        publishes ``language.changed`` / ``theme.changed`` when those
        specific keys change.
        """
        if not key:
            return
        try:
            db.setting_set(key, value)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key, "value": value})
            return
        # Update cache.
        self._refresh_key(key)
        new_val = self._cache.get(key, value)
        bus.publish("settings.changed", {"key": key, "value": new_val})
        if key == KEY_LANGUAGE:
            bus.publish("language.changed", {"language": new_val})
        elif key == KEY_THEME:
            bus.publish("theme.changed", {"theme": new_val})
        _log.debug("Setting %s = %r", key, new_val)

    def delete(self, key: str) -> bool:
        """Delete a setting.  Returns True if a row was deleted."""
        if not key:
            return False
        try:
            ok = db.setting_delete(key)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return False
        if ok and key in self._cache:
            del self._cache[key]
        return ok

    def list(self) -> Dict[str, Any]:
        """Return all settings as a dict (key -> typed value)."""
        if not self._loaded:
            self._load_all()
        return dict(self._cache)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    # Each pair (getter / setter) below mirrors a well-known key.

    # --- Language ---
    def language(self) -> str:
        return str(self.get(KEY_LANGUAGE, config.DEFAULT_LANG))

    def set_language(self, lang: str) -> None:
        if lang not in config.SUPPORTED_LANGUAGES:
            _log.warning("Unknown language %r, allowing anyway", lang)
        self.set(KEY_LANGUAGE, lang)

    # --- Theme ---
    def theme(self) -> str:
        return str(self.get(KEY_THEME, config.DEFAULT_THEME))

    def set_theme(self, theme: str) -> None:
        if theme not in (config.THEME_DARK, config.THEME_LIGHT,
                         config.THEME_SYSTEM):
            _log.warning("Unknown theme %r, allowing anyway", theme)
        self.set(KEY_THEME, theme)

    # --- Font scale ---
    def font_scale(self) -> float:
        v = self.get(KEY_FONT_SCALE, config.DEFAULT_FONT_SCALE)
        try:
            return float(v)
        except (TypeError, ValueError):
            return config.DEFAULT_FONT_SCALE

    def set_font_scale(self, s: float) -> None:
        try:
            s = float(s)
        except (TypeError, ValueError):
            return
        s = max(config.MIN_FONT_SCALE, min(config.MAX_FONT_SCALE, s))
        self.set(KEY_FONT_SCALE, s)

    # --- Lock mode ---
    def lock_mode(self) -> str:
        return str(self.get(KEY_LOCK_MODE, "none"))

    def set_lock_mode(self, mode: str) -> None:
        if mode not in ("none", "pin", "biometric"):
            _log.warning("Unknown lock_mode %r", mode)
        self.set(KEY_LOCK_MODE, mode)

    # --- Auto-lock seconds ---
    def auto_lock_seconds(self) -> int:
        v = self.get(KEY_AUTO_LOCK_SECONDS, 0)
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def set_auto_lock_seconds(self, s: int) -> None:
        try:
            s = int(s)
        except (TypeError, ValueError):
            return
        s = max(0, min(3600, s))
        self.set(KEY_AUTO_LOCK_SECONDS, s)

    # --- Notification sound ---
    def notify_sound(self) -> bool:
        return bool(self.get(KEY_NOTIFY_SOUND, config.NOTIFY_SOUND_DEFAULT))

    def set_notify_sound(self, b: bool) -> None:
        self.set(KEY_NOTIFY_SOUND, bool(b))

    # --- Notification vibrate ---
    def notify_vibrate(self) -> bool:
        return bool(self.get(KEY_NOTIFY_VIBRATE,
                              config.NOTIFY_VIBRATE_DEFAULT))

    def set_notify_vibrate(self, b: bool) -> None:
        self.set(KEY_NOTIFY_VIBRATE, bool(b))

    # --- First day of week ---
    def first_day_of_week(self) -> int:
        """Return the first-day-of-week index (Saturday=6 by JS convention)."""
        v = self.get(KEY_FIRST_DAY_OF_WEEK, 6)
        try:
            return int(v)
        except (TypeError, ValueError):
            return 6

    def set_first_day_of_week(self, d: int) -> None:
        try:
            d = int(d)
        except (TypeError, ValueError):
            return
        d = max(0, min(6, d))
        self.set(KEY_FIRST_DAY_OF_WEEK, d)

    # --- Time format ---
    def time_format(self) -> str:
        return str(self.get(KEY_TIME_FORMAT, "24"))

    def set_time_format(self, f: str) -> None:
        if f not in ("12", "24"):
            _log.warning("Unknown time_format %r", f)
        self.set(KEY_TIME_FORMAT, f)

    # --- Date format ---
    def date_format(self) -> str:
        return str(self.get(KEY_DATE_FORMAT, "short"))

    def set_date_format(self, f: str) -> None:
        if f not in ("short", "long", "iso", "full"):
            _log.warning("Unknown date_format %r", f)
        self.set(KEY_DATE_FORMAT, f)

    # --- Calendar system ---
    def calendar_system(self) -> str:
        return str(self.get(KEY_CALENDAR_SYSTEM, "jalali"))

    def set_calendar_system(self, c: str) -> None:
        if c not in ("jalali", "gregorian"):
            _log.warning("Unknown calendar_system %r", c)
        self.set(KEY_CALENDAR_SYSTEM, c)

    # --- Auto-backup ---
    def auto_backup(self) -> str:
        return str(self.get(KEY_AUTO_BACKUP, "off"))

    def set_auto_backup(self, s: str) -> None:
        if s not in ("off", "daily", "weekly", "monthly"):
            _log.warning("Unknown auto_backup %r", s)
        self.set(KEY_AUTO_BACKUP, s)

    # --- Developer mode ---
    def developer_mode(self) -> bool:
        return bool(self.get(KEY_DEVELOPER_MODE, False))

    def set_developer_mode(self, b: bool) -> None:
        self.set(KEY_DEVELOPER_MODE, bool(b))

    # --- Reduced motion ---
    def reduced_motion(self) -> bool:
        return bool(self.get(KEY_REDUCED_MOTION,
                              config.DEFAULT_REDUCED_MOTION))

    def set_reduced_motion(self, b: bool) -> None:
        self.set(KEY_REDUCED_MOTION, bool(b))

    # --- High contrast ---
    def high_contrast(self) -> bool:
        return bool(self.get(KEY_HIGH_CONTRAST,
                              config.DEFAULT_HIGH_CONTRAST))

    def set_high_contrast(self, b: bool) -> None:
        self.set(KEY_HIGH_CONTRAST, bool(b))

    # --- User profile ---
    def user_name(self) -> str:
        return str(self.get(KEY_USER_NAME, ""))

    def set_user_name(self, s: str) -> None:
        self.set(KEY_USER_NAME, str(s or ""))

    def user_email(self) -> str:
        return str(self.get(KEY_USER_EMAIL, ""))

    def set_user_email(self, s: str) -> None:
        self.set(KEY_USER_EMAIL, str(s or ""))

    def user_avatar_path(self) -> str:
        return str(self.get(KEY_USER_AVATAR_PATH, ""))

    def set_user_avatar_path(self, s: str) -> None:
        self.set(KEY_USER_AVATAR_PATH, str(s or ""))

    # --- PIN hash ---
    def pin_hash(self) -> Optional[str]:
        v = self.get(KEY_PIN_HASH, None)
        if not v:
            return None
        return str(v)

    def set_pin_hash(self, s: str) -> None:
        self.set(KEY_PIN_HASH, str(s))

    def clear_pin_hash(self) -> None:
        self.delete(KEY_PIN_HASH)

    # --- Onboarding ---
    def is_onboarded(self) -> bool:
        return bool(self.get(KEY_ONBOARDED, False))

    def set_onboarded(self, b: bool = True) -> None:
        self.set(KEY_ONBOARDED, bool(b))

    def is_first_run(self) -> bool:
        return bool(self.get(KEY_FIRST_RUN, True))

    def clear_first_run(self) -> None:
        self.set(KEY_FIRST_RUN, False)

    # --- Last backup / export timestamps ---
    def last_backup_iso(self) -> Optional[str]:
        v = self.get(KEY_LAST_BACKUP_ISO, None)
        return str(v) if v else None

    def set_last_backup_iso(self, iso: str) -> None:
        self.set(KEY_LAST_BACKUP_ISO, iso)

    def last_export_iso(self) -> Optional[str]:
        v = self.get(KEY_LAST_EXPORT_ISO, None)
        return str(v) if v else None

    def set_last_export_iso(self, iso: str) -> None:
        self.set(KEY_LAST_EXPORT_ISO, iso)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

settings_service: SettingsService = SettingsService()
