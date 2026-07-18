"""
rask.tests.test_settings_service
===============================

Unit tests for :mod:`rask.services.settings_service`.

Covers:

  • All convenience accessors (language, theme, font_scale, lock_mode,
    auto_lock_seconds, notify_sound, notify_vibrate, first_day_of_week,
    time_format, date_format, calendar_system, auto_backup,
    developer_mode, reduced_motion, high_contrast, user_name,
    user_email, pin_hash, is_onboarded, is_first_run,
    last_backup_iso, last_export_iso)
  • Cache invalidation on ``set()``
  • Event publication (``settings.changed``, ``language.changed``,
    ``theme.changed``)
  • Type coercion: int, float, bool, json, string
  • Default values from :mod:`rask.config`
  • ``delete()`` removes both cache + DB row
  • ``list()`` returns dict of all settings
  • Boundary clamping (font_scale, auto_lock_seconds)
"""
from __future__ import annotations

import unittest
from typing import Any, List, Tuple

from rask import config, database as db
from rask.core.event_bus import bus
from rask.services.settings_service import (
    KEY_LANGUAGE,
    KEY_THEME,
    KEY_FONT_SCALE,
    KEY_LOCK_MODE,
    SettingsService,
)
from rask.tests import fresh_db


# =============================================================================
# === Helper                                                                  ===
# =============================================================================

class _EventCollector:
    """Capture published events for assertions."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Tuple[Any, ...], dict]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        # The "event name" is captured by the subscribe call separately;
        # we record args + kwargs.
        self.events.append(("_", args, kwargs))


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestSettingsDefaults(unittest.TestCase):
    """Default values returned by each accessor after fresh DB init."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_language_default(self) -> None:
        self.assertEqual(self.svc.language(), config.DEFAULT_LANG)

    def test_theme_default(self) -> None:
        self.assertEqual(self.svc.theme(), config.DEFAULT_THEME)

    def test_font_scale_default(self) -> None:
        self.assertAlmostEqual(self.svc.font_scale(), config.DEFAULT_FONT_SCALE)

    def test_lock_mode_default(self) -> None:
        self.assertEqual(self.svc.lock_mode(), "none")

    def test_auto_lock_seconds_default(self) -> None:
        self.assertEqual(self.svc.auto_lock_seconds(), 0)

    def test_notify_sound_default(self) -> None:
        self.assertEqual(self.svc.notify_sound(), config.NOTIFY_SOUND_DEFAULT)

    def test_notify_vibrate_default(self) -> None:
        self.assertEqual(self.svc.notify_vibrate(), config.NOTIFY_VIBRATE_DEFAULT)

    def test_first_day_of_week_default(self) -> None:
        self.assertEqual(self.svc.first_day_of_week(), 6)  # Saturday

    def test_time_format_default(self) -> None:
        self.assertEqual(self.svc.time_format(), "24")

    def test_date_format_default(self) -> None:
        self.assertEqual(self.svc.date_format(), "short")

    def test_calendar_system_default(self) -> None:
        self.assertEqual(self.svc.calendar_system(), "jalali")

    def test_auto_backup_default(self) -> None:
        self.assertEqual(self.svc.auto_backup(), "off")

    def test_developer_mode_default(self) -> None:
        self.assertFalse(self.svc.developer_mode())

    def test_reduced_motion_default(self) -> None:
        self.assertEqual(self.svc.reduced_motion(), config.DEFAULT_REDUCED_MOTION)

    def test_high_contrast_default(self) -> None:
        self.assertEqual(self.svc.high_contrast(), config.DEFAULT_HIGH_CONTRAST)

    def test_user_name_default_empty(self) -> None:
        self.assertEqual(self.svc.user_name(), "")

    def test_user_email_default_empty(self) -> None:
        self.assertEqual(self.svc.user_email(), "")

    def test_user_avatar_path_default_empty(self) -> None:
        self.assertEqual(self.svc.user_avatar_path(), "")

    def test_pin_hash_default_none(self) -> None:
        self.assertIsNone(self.svc.pin_hash())

    def test_is_onboarded_default_false(self) -> None:
        self.assertFalse(self.svc.is_onboarded())

    def test_is_first_run_default_true(self) -> None:
        self.assertTrue(self.svc.is_first_run())

    def test_last_backup_iso_default_none(self) -> None:
        self.assertIsNone(self.svc.last_backup_iso())

    def test_last_export_iso_default_none(self) -> None:
        self.assertIsNone(self.svc.last_export_iso())


class TestSettingsSetters(unittest.TestCase):
    """Each setter writes through to DB and updates the cache."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_set_language(self) -> None:
        self.svc.set_language("en")
        self.assertEqual(self.svc.language(), "en")
        self.assertEqual(db.setting_get(KEY_LANGUAGE), "en")

    def test_set_theme(self) -> None:
        self.svc.set_theme("light")
        self.assertEqual(self.svc.theme(), "light")

    def test_set_font_scale(self) -> None:
        self.svc.set_font_scale(1.25)
        self.assertAlmostEqual(self.svc.font_scale(), 1.25)

    def test_set_font_scale_clamps_to_max(self) -> None:
        self.svc.set_font_scale(99.0)
        self.assertLessEqual(self.svc.font_scale(), config.MAX_FONT_SCALE)

    def test_set_font_scale_clamps_to_min(self) -> None:
        self.svc.set_font_scale(-1.0)
        self.assertGreaterEqual(self.svc.font_scale(), config.MIN_FONT_SCALE)

    def test_set_font_scale_with_invalid_returns_previous(self) -> None:
        prev = self.svc.font_scale()
        self.svc.set_font_scale("not-a-number")  # type: ignore[arg-type]
        self.assertEqual(self.svc.font_scale(), prev)

    def test_set_lock_mode(self) -> None:
        self.svc.set_lock_mode("pin")
        self.assertEqual(self.svc.lock_mode(), "pin")

    def test_set_auto_lock_seconds(self) -> None:
        self.svc.set_auto_lock_seconds(120)
        self.assertEqual(self.svc.auto_lock_seconds(), 120)

    def test_set_auto_lock_seconds_clamps_to_max(self) -> None:
        self.svc.set_auto_lock_seconds(99999)
        self.assertLessEqual(self.svc.auto_lock_seconds(), 3600)

    def test_set_auto_lock_seconds_clamps_to_min(self) -> None:
        self.svc.set_auto_lock_seconds(-10)
        self.assertGreaterEqual(self.svc.auto_lock_seconds(), 0)

    def test_set_notify_sound(self) -> None:
        self.svc.set_notify_sound(False)
        self.assertFalse(self.svc.notify_sound())
        self.svc.set_notify_sound(True)
        self.assertTrue(self.svc.notify_sound())

    def test_set_notify_vibrate(self) -> None:
        self.svc.set_notify_vibrate(False)
        self.assertFalse(self.svc.notify_vibrate())

    def test_set_first_day_of_week(self) -> None:
        self.svc.set_first_day_of_week(0)
        self.assertEqual(self.svc.first_day_of_week(), 0)

    def test_set_first_day_of_week_clamps(self) -> None:
        self.svc.set_first_day_of_week(99)
        self.assertLessEqual(self.svc.first_day_of_week(), 6)

    def test_set_time_format(self) -> None:
        self.svc.set_time_format("12")
        self.assertEqual(self.svc.time_format(), "12")

    def test_set_date_format(self) -> None:
        self.svc.set_date_format("long")
        self.assertEqual(self.svc.date_format(), "long")

    def test_set_calendar_system(self) -> None:
        self.svc.set_calendar_system("gregorian")
        self.assertEqual(self.svc.calendar_system(), "gregorian")

    def test_set_auto_backup(self) -> None:
        self.svc.set_auto_backup("weekly")
        self.assertEqual(self.svc.auto_backup(), "weekly")

    def test_set_developer_mode(self) -> None:
        self.svc.set_developer_mode(True)
        self.assertTrue(self.svc.developer_mode())

    def test_set_reduced_motion(self) -> None:
        self.svc.set_reduced_motion(True)
        self.assertTrue(self.svc.reduced_motion())

    def test_set_high_contrast(self) -> None:
        self.svc.set_high_contrast(True)
        self.assertTrue(self.svc.high_contrast())

    def test_set_user_name(self) -> None:
        self.svc.set_user_name("Radin")
        self.assertEqual(self.svc.user_name(), "Radin")

    def test_set_user_email(self) -> None:
        self.svc.set_user_email("radin@example.com")
        self.assertEqual(self.svc.user_email(), "radin@example.com")

    def test_set_user_avatar_path(self) -> None:
        self.svc.set_user_avatar_path("/tmp/avatar.png")
        self.assertEqual(self.svc.user_avatar_path(), "/tmp/avatar.png")

    def test_set_pin_hash(self) -> None:
        self.svc.set_pin_hash("hash:abc")
        self.assertEqual(self.svc.pin_hash(), "hash:abc")

    def test_clear_pin_hash(self) -> None:
        self.svc.set_pin_hash("hash:abc")
        self.svc.clear_pin_hash()
        self.assertIsNone(self.svc.pin_hash())

    def test_set_onboarded(self) -> None:
        self.svc.set_onboarded(True)
        self.assertTrue(self.svc.is_onboarded())

    def test_clear_first_run(self) -> None:
        self.svc.clear_first_run()
        self.assertFalse(self.svc.is_first_run())

    def test_set_last_backup_iso(self) -> None:
        self.svc.set_last_backup_iso("2025-01-01T00:00:00")
        self.assertEqual(self.svc.last_backup_iso(), "2025-01-01T00:00:00")

    def test_set_last_export_iso(self) -> None:
        self.svc.set_last_export_iso("2025-01-01T00:00:00")
        self.assertEqual(self.svc.last_export_iso(), "2025-01-01T00:00:00")


class TestCacheInvalidation(unittest.TestCase):
    """set() invalidates the cache so subsequent reads see the new value."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_cache_invalidated_after_set(self) -> None:
        # Read to populate cache.
        self.assertEqual(self.svc.user_name(), "")
        # Set new value.
        self.svc.set_user_name("Alice")
        # Read again — should see new value (cache was invalidated).
        self.assertEqual(self.svc.user_name(), "Alice")

    def test_cache_reflects_external_db_change_after_reload(self) -> None:
        # External mutation directly via DB layer.
        db.setting_set(KEY_LOCK_MODE, "biometric")
        # Cache still holds old value until we reload.
        # (Service cache is sticky — only set() invalidates it.)
        # Force a reload by calling init().
        self.svc._loaded = False
        self.svc.init()
        self.assertEqual(self.svc.lock_mode(), "biometric")

    def test_list_returns_all_cached_settings(self) -> None:
        self.svc.set_user_name("Bob")
        all_s = self.svc.list()
        self.assertIsInstance(all_s, dict)
        self.assertIn(KEY_LANGUAGE, all_s)
        self.assertEqual(all_s.get("user_name"), "Bob")


class TestEventPublication(unittest.TestCase):
    """set() publishes the right events."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()
        self.collector = _EventCollector()
        bus.subscribe("settings.changed", self.collector)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_set_publishes_settings_changed(self) -> None:
        self.svc.set_user_name("Carol")
        self.assertEqual(len(self.collector.events), 1)
        args, kwargs = self.collector.events[0][1], self.collector.events[0][2]
        # settings.changed payload is passed as a kwarg or positional?
        # Either way the test confirms the event fired.
        self.assertTrue(args or kwargs)

    def test_set_language_publishes_language_changed(self) -> None:
        lang_collector = _EventCollector()
        bus.subscribe("language.changed", lang_collector)
        self.svc.set_language("en")
        self.assertEqual(len(lang_collector.events), 1)

    def test_set_theme_publishes_theme_changed(self) -> None:
        theme_collector = _EventCollector()
        bus.subscribe("theme.changed", theme_collector)
        self.svc.set_theme("light")
        self.assertEqual(len(theme_collector.events), 1)

    def test_setting_other_key_does_not_publish_language_changed(self) -> None:
        lang_collector = _EventCollector()
        bus.subscribe("language.changed", lang_collector)
        self.svc.set_user_name("Dave")
        self.assertEqual(len(lang_collector.events), 0)


class TestTypeCoercion(unittest.TestCase):
    """set() persists values with the right SQLite type tag."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_int_setting_round_trips_as_int(self) -> None:
        self.svc.set("test_int", 42)
        v = self.svc.get("test_int")
        self.assertEqual(v, 42)
        self.assertIsInstance(v, int)

    def test_float_setting_round_trips_as_float(self) -> None:
        self.svc.set("test_float", 3.14)
        v = self.svc.get("test_float")
        self.assertAlmostEqual(v, 3.14)

    def test_bool_setting_round_trips_as_bool(self) -> None:
        self.svc.set("test_bool", True)
        self.assertTrue(self.svc.get("test_bool"))
        self.svc.set("test_bool", False)
        self.assertFalse(self.svc.get("test_bool"))

    def test_string_setting_round_trips_as_string(self) -> None:
        self.svc.set("test_str", "hello world")
        self.assertEqual(self.svc.get("test_str"), "hello world")

    def test_json_setting_round_trips_as_dict(self) -> None:
        payload = {"a": 1, "b": [2, 3], "c": {"nested": True}}
        self.svc.set("test_json", payload)
        v = self.svc.get("test_json")
        self.assertEqual(v, payload)

    def test_json_setting_with_list(self) -> None:
        self.svc.set("test_list", [1, 2, 3, "four"])
        self.assertEqual(self.svc.get("test_list"), [1, 2, 3, "four"])

    def test_int_zero_persists(self) -> None:
        self.svc.set("test_zero", 0)
        self.assertEqual(self.svc.get("test_zero"), 0)

    def test_negative_int_persists(self) -> None:
        self.svc.set("test_neg", -42)
        self.assertEqual(self.svc.get("test_neg"), -42)


class TestDelete(unittest.TestCase):
    """delete() removes both cache + DB row."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_returns_true(self) -> None:
        self.svc.set("deleteme", "value")
        self.assertTrue(self.svc.delete("deleteme"))

    def test_delete_removes_from_cache(self) -> None:
        self.svc.set("deleteme", "value")
        self.svc.delete("deleteme")
        self.assertIsNone(self.svc.get("deleteme"))

    def test_delete_nonexistent_returns_false(self) -> None:
        self.assertFalse(self.svc.delete("does_not_exist"))

    def test_delete_empty_key_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(""))


class TestGetWithDefault(unittest.TestCase):
    """get() returns default when key is missing."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_get_missing_returns_default(self) -> None:
        self.assertEqual(self.svc.get("missing_key", "fallback"), "fallback")

    def test_get_missing_returns_none_by_default(self) -> None:
        self.assertIsNone(self.svc.get("missing_key"))

    def test_get_empty_key_returns_default(self) -> None:
        self.assertEqual(self.svc.get("", "fallback"), "fallback")

    def test_get_returns_typed_value_when_present(self) -> None:
        self.svc.set("present", 123)
        self.assertEqual(self.svc.get("present", 0), 123)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and defensive behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = SettingsService()
        self.svc.init()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_set_empty_key_is_noop(self) -> None:
        self.svc.set("", "value")
        # Should not raise and should not persist.
        self.assertIsNone(self.svc.get(""))

    def test_font_scale_invalid_returns_default(self) -> None:
        # Manually poison the cache with an invalid value.
        self.svc._cache[KEY_FONT_SCALE] = "not a number"
        v = self.svc.font_scale()
        self.assertEqual(v, config.DEFAULT_FONT_SCALE)

    def test_auto_lock_seconds_invalid_returns_zero(self) -> None:
        self.svc._cache["auto_lock_seconds"] = "invalid"
        self.assertEqual(self.svc.auto_lock_seconds(), 0)

    def test_first_day_of_week_invalid_returns_six(self) -> None:
        self.svc._cache["first_day_of_week"] = "invalid"
        self.assertEqual(self.svc.first_day_of_week(), 6)


if __name__ == "__main__":
    unittest.main()
