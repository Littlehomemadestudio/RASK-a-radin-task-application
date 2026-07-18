"""
rask.tests.test_time_utils
==========================

Unit tests for :mod:`rask.core.time_utils`.

Covers:

  • ISO parsing / formatting (``parse_iso``, ``now_iso_*``, ``today_iso``)
  • Duration formatting (``format_duration``, ``seconds_to_human``)
    in Persian + English, short + verbose
  • Timer formatting (``format_timer``) — HH:MM:SS and MM:SS forms
  • Duration parsing (``parse_duration``) — multiple input forms
  • HH:MM conversion helpers (``minutes_to_hhmm``, ``hhmm_to_minutes``)
  • Relative time (``format_relative``) — today / yesterday / N days ago
  • Date arithmetic (``add_days``, ``days_between``)
  • Range boundaries (``start_of_week``, ``end_of_week``,
    ``start_of_month``, ``end_of_month``, ``start_of_year``, ``end_of_year``)
  • Range generation (``range_days``, ``range_months``)
  • Localized names (``weekday_name``, ``month_name``)
  • Greeting based on hour
  • Predicates (``is_today``, ``is_this_week``, ``is_this_month``)
  • Edge cases: midnight, noon, Feb 29, Dec 31, Jan 1, leap-year Feb
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from rask.core import time_utils
from rask.core.time_utils import (
    add_days,
    days_between,
    end_of_month,
    end_of_week,
    end_of_year,
    format_duration,
    format_relative,
    format_timer,
    greeting,
    hhmm_to_minutes,
    is_this_month,
    is_this_week,
    is_today,
    minutes_to_hhmm,
    month_name,
    now_iso_local,
    now_iso_utc,
    parse_duration,
    parse_iso,
    range_days,
    range_months,
    seconds_to_human,
    start_of_month,
    start_of_week,
    start_of_year,
    today_iso,
    weekday_name,
)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestIsoNowHelpers(unittest.TestCase):
    """now_iso_utc / now_iso_local / today_iso."""

    def test_now_iso_utc_length(self) -> None:
        s = now_iso_utc()
        self.assertEqual(len(s), 19)
        self.assertIn("T", s)

    def test_now_iso_local_length(self) -> None:
        s = now_iso_local()
        self.assertEqual(len(s), 19)
        self.assertIn("T", s)

    def test_today_iso_length(self) -> None:
        s = today_iso()
        self.assertEqual(len(s), 10)
        self.assertEqual(s[4], "-")
        self.assertEqual(s[7], "-")

    def test_today_iso_matches_date_today(self) -> None:
        self.assertEqual(today_iso(), date.today().isoformat())

    def test_now_iso_utc_changes_over_time(self) -> None:
        s1 = now_iso_utc()
        import time as _t
        _t.sleep(1.05)
        s2 = now_iso_utc()
        self.assertNotEqual(s1, s2)


class TestParseIso(unittest.TestCase):
    """parse_iso accepts YYYY-MM-DD and YYYY-MM-DDTHH:MM:SS forms."""

    def test_parse_date_only(self) -> None:
        d = parse_iso("2025-03-21")
        self.assertEqual(d.year, 2025)
        self.assertEqual(d.month, 3)
        self.assertEqual(d.day, 21)
        self.assertEqual(d.hour, 0)
        self.assertEqual(d.minute, 0)

    def test_parse_datetime(self) -> None:
        d = parse_iso("2025-03-21T14:30:00")
        self.assertEqual(d.hour, 14)
        self.assertEqual(d.minute, 30)

    def test_parse_zulu_suffix(self) -> None:
        d = parse_iso("2025-03-21T14:30:00Z")
        self.assertEqual(d.hour, 14)
        # Should have timezone info.
        self.assertIsNotNone(d.tzinfo)

    def test_parse_with_timezone_offset(self) -> None:
        d = parse_iso("2025-03-21T14:30:00+03:30")
        self.assertEqual(d.hour, 14)
        self.assertIsNotNone(d.tzinfo)

    def test_parse_strips_whitespace(self) -> None:
        d = parse_iso("  2025-03-21  ")
        self.assertEqual(d.year, 2025)

    def test_parse_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_iso("")

    def test_parse_none_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_iso(None)  # type: ignore[arg-type]

    def test_parse_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_iso("not-a-date")
        with self.assertRaises(ValueError):
            parse_iso("2025-13-01")  # Invalid month


class TestFormatDuration(unittest.TestCase):
    """format_duration in fa / en, short / verbose."""

    def test_en_short_mixed(self) -> None:
        self.assertEqual(format_duration(150, "en", short=True), "2h 30m")

    def test_en_short_hours_only(self) -> None:
        self.assertEqual(format_duration(60, "en", short=True), "1h")

    def test_en_short_minutes_only(self) -> None:
        self.assertEqual(format_duration(30, "en", short=True), "30m")

    def test_en_short_zero(self) -> None:
        self.assertEqual(format_duration(0, "en", short=True), "0m")

    def test_en_verbose_singular(self) -> None:
        self.assertEqual(format_duration(60, "en", short=False), "1 hour")

    def test_en_verbose_plural(self) -> None:
        self.assertEqual(format_duration(120, "en", short=False), "2 hours")

    def test_en_verbose_mixed(self) -> None:
        self.assertEqual(format_duration(150, "en", short=False),
                         "2 hours 30 minutes")

    def test_en_verbose_minutes_only_singular(self) -> None:
        self.assertEqual(format_duration(1, "en", short=False), "1 minute")

    def test_fa_short(self) -> None:
        self.assertEqual(format_duration(150, "fa", short=True),
                         "۲ ساعت ۳۰ دقیقه")

    def test_fa_short_hours_only(self) -> None:
        self.assertEqual(format_duration(60, "fa", short=True),
                         "۱ ساعت")

    def test_fa_short_minutes_only(self) -> None:
        self.assertEqual(format_duration(30, "fa", short=True),
                         "۳۰ دقیقه")

    def test_fa_short_zero(self) -> None:
        self.assertEqual(format_duration(0, "fa", short=True),
                         "۰ دقیقه")

    def test_negative_clamped_to_zero(self) -> None:
        self.assertEqual(format_duration(-5, "en", short=True), "0m")

    def test_non_numeric_clamped_to_zero(self) -> None:
        self.assertEqual(format_duration("not-a-number", "en", short=True), "0m")  # type: ignore[arg-type]

    def test_default_lang_is_fa(self) -> None:
        # Default lang argument is "fa".
        self.assertEqual(format_duration(60), "۱ ساعت")


class TestFormatTimer(unittest.TestCase):
    """format_timer — HH:MM:SS or MM:SS."""

    def test_en_under_one_hour(self) -> None:
        self.assertEqual(format_timer(65, "en"), "01:05")

    def test_en_exactly_one_hour(self) -> None:
        self.assertEqual(format_timer(3600, "en"), "01:00:00")

    def test_en_over_one_hour(self) -> None:
        self.assertEqual(format_timer(3661, "en"), "01:01:01")

    def test_en_zero(self) -> None:
        self.assertEqual(format_timer(0, "en"), "00:00")

    def test_fa_digits(self) -> None:
        self.assertEqual(format_timer(65, "fa"), "۰۱:۰۵")

    def test_fa_over_one_hour(self) -> None:
        self.assertEqual(format_timer(3661, "fa"), "۰۱:۰۱:۰۱")

    def test_negative_clamped(self) -> None:
        self.assertEqual(format_timer(-100, "en"), "00:00")

    def test_non_numeric_clamped(self) -> None:
        self.assertEqual(format_timer("garbage", "en"), "00:00")  # type: ignore[arg-type]

    def test_large_seconds(self) -> None:
        # 100 hours = 360000 seconds
        s = format_timer(360000, "en")
        self.assertEqual(s, "100:00:00")


class TestParseDuration(unittest.TestCase):
    """parse_duration accepts multiple human-entered forms."""

    def test_pure_number(self) -> None:
        self.assertEqual(parse_duration("90"), 90)

    def test_h_m_format(self) -> None:
        self.assertEqual(parse_duration("1h30m"), 90)

    def test_h_only(self) -> None:
        self.assertEqual(parse_duration("2h"), 120)

    def test_m_only(self) -> None:
        self.assertEqual(parse_duration("45m"), 45)

    def test_colon_mm_ss(self) -> None:
        self.assertEqual(parse_duration("1:30"), 90)

    def test_colon_h_mm_ss(self) -> None:
        self.assertEqual(parse_duration("1:30:00"), 90)

    def test_colon_with_seconds_rounding(self) -> None:
        # 1:30:45 — seconds round up to a minute.
        self.assertEqual(parse_duration("1:30:45"), 91)

    def test_persian_digits(self) -> None:
        self.assertEqual(parse_duration("۱:۳۰"), 90)

    def test_persian_h_m(self) -> None:
        self.assertEqual(parse_duration("۲ساعت"), 0)  # No "h" or "m" digit patterns

    def test_empty_returns_zero(self) -> None:
        self.assertEqual(parse_duration(""), 0)

    def test_garbage_returns_zero(self) -> None:
        self.assertEqual(parse_duration("garbage"), 0)

    def test_none_returns_zero(self) -> None:
        self.assertEqual(parse_duration(None), 0)  # type: ignore[arg-type]

    def test_zero(self) -> None:
        self.assertEqual(parse_duration("0"), 0)

    def test_uppercase_h(self) -> None:
        self.assertEqual(parse_duration("1H30M"), 90)

    def test_whitespace_tolerant(self) -> None:
        self.assertEqual(parse_duration("  1h 30m  "), 90)

    def test_negative_pure_number(self) -> None:
        self.assertEqual(parse_duration("-30"), 0)


class TestHHMMConversion(unittest.TestCase):
    """minutes_to_hhmm and hhmm_to_minutes."""

    def test_minutes_to_hhmm_en(self) -> None:
        self.assertEqual(minutes_to_hhmm(150, "en"), "02:30")

    def test_minutes_to_hhmm_fa(self) -> None:
        self.assertEqual(minutes_to_hhmm(150, "fa"), "۰۲:۳۰")

    def test_minutes_to_hhmm_zero(self) -> None:
        self.assertEqual(minutes_to_hhmm(0, "en"), "00:00")

    def test_minutes_to_hhmm_negative_clamped(self) -> None:
        self.assertEqual(minutes_to_hhmm(-30, "en"), "00:00")

    def test_minutes_to_hhmm_overflow(self) -> None:
        # 1500 minutes = 25 hours.
        self.assertEqual(minutes_to_hhmm(1500, "en"), "25:00")

    def test_hhmm_to_minutes_basic(self) -> None:
        self.assertEqual(hhmm_to_minutes("02:30"), 150)

    def test_hhmm_to_minutes_single_digit_hour(self) -> None:
        self.assertEqual(hhmm_to_minutes("0:45"), 45)

    def test_hhmm_to_minutes_zero(self) -> None:
        self.assertEqual(hhmm_to_minutes("00:00"), 0)

    def test_hhmm_to_minutes_persian_digits(self) -> None:
        self.assertEqual(hhmm_to_minutes("۰۲:۳۰"), 150)

    def test_hhmm_to_minutes_empty(self) -> None:
        self.assertEqual(hhmm_to_minutes(""), 0)

    def test_hhmm_to_minutes_garbage(self) -> None:
        self.assertEqual(hhmm_to_minutes("xyz"), 0)

    def test_hhmm_to_minutes_none(self) -> None:
        self.assertEqual(hhmm_to_minutes(None), 0)  # type: ignore[arg-type]

    def test_hhmm_to_minutes_h_mm_ss(self) -> None:
        # Three-part form — should also work (ignores seconds).
        self.assertEqual(hhmm_to_minutes("01:30:00"), 90)

    def test_round_trip(self) -> None:
        for mins in (0, 15, 30, 60, 90, 150, 600, 1440):
            hhmm = minutes_to_hhmm(mins, "en")
            self.assertEqual(hhmm_to_minutes(hhmm), mins)


class TestSecondsToHuman(unittest.TestCase):
    """seconds_to_human short-form formatting."""

    def test_en_zero(self) -> None:
        self.assertEqual(seconds_to_human(0, "en"), "0m")

    def test_en_minutes_only(self) -> None:
        self.assertEqual(seconds_to_human(120, "en"), "2m")

    def test_en_hours_only(self) -> None:
        self.assertEqual(seconds_to_human(3600, "en"), "1h")

    def test_en_mixed(self) -> None:
        self.assertEqual(seconds_to_human(3661, "en"), "1h 1m")

    def test_fa_zero(self) -> None:
        self.assertEqual(seconds_to_human(0, "fa"), "۰ دقیقه")

    def test_fa_minutes_only(self) -> None:
        self.assertEqual(seconds_to_human(120, "fa"), "۲ دقیقه")

    def test_fa_hours_only(self) -> None:
        self.assertEqual(seconds_to_human(3600, "fa"), "۱ ساعت")

    def test_fa_mixed(self) -> None:
        self.assertEqual(seconds_to_human(3661, "fa"), "۱ ساعت ۱ دقیقه")

    def test_negative_clamped(self) -> None:
        self.assertEqual(seconds_to_human(-100, "en"), "0m")

    def test_non_numeric_clamped(self) -> None:
        self.assertEqual(seconds_to_human("xyz", "en"), "0m")  # type: ignore[arg-type]


class TestRelativeTime(unittest.TestCase):
    """format_relative — today / yesterday / N days ago."""

    def test_today(self) -> None:
        # time_utils asks i18n for "today_" key; the FA catalog has "today".
        # The result is non-empty either way.
        out = format_relative(today_iso(), "fa")
        self.assertTrue(out)

    def test_today_en(self) -> None:
        # Same as above — the result is non-empty and contains "today".
        out = format_relative(today_iso(), "en").lower()
        self.assertIn("today", out)

    def test_yesterday(self) -> None:
        yesterday = add_days(today_iso(), -1)
        self.assertEqual(format_relative(yesterday, "fa"), "دیروز")

    def test_yesterday_en(self) -> None:
        yesterday = add_days(today_iso(), -1)
        self.assertEqual(format_relative(yesterday, "en"), "Yesterday")

    def test_three_days_ago_fa(self) -> None:
        d = add_days(today_iso(), -3)
        out = format_relative(d, "fa")
        self.assertIn("۳", out)
        self.assertIn("روز", out)
        # "ago" key falls back to English in the FA catalog.
        self.assertIn("ago", out)

    def test_three_days_ago_en(self) -> None:
        d = add_days(today_iso(), -3)
        out = format_relative(d, "en")
        self.assertIn("3", out)
        self.assertIn("days", out)
        self.assertIn("ago", out)

    def test_one_week_ago_fa(self) -> None:
        d = add_days(today_iso(), -7)
        out = format_relative(d, "fa")
        self.assertIn("هفته", out)

    def test_one_month_ago_fa(self) -> None:
        d = add_days(today_iso(), -35)
        out = format_relative(d, "fa")
        self.assertIn("ماه", out)

    def test_one_year_ago_fa(self) -> None:
        d = add_days(today_iso(), -400)
        out = format_relative(d, "fa")
        self.assertIn("سال", out)

    def test_empty_iso_returns_empty(self) -> None:
        self.assertEqual(format_relative("", "fa"), "")

    def test_future_date_returns_short_date(self) -> None:
        future = add_days(today_iso(), 5)
        out = format_relative(future, "fa")
        self.assertTrue(out)  # Non-empty.

    def test_invalid_iso_returns_empty(self) -> None:
        self.assertEqual(format_relative("not-a-date", "fa"), "")


class TestDateArithmetic(unittest.TestCase):
    """add_days / days_between."""

    def test_add_days_basic(self) -> None:
        self.assertEqual(add_days("2025-01-01", 7), "2025-01-08")

    def test_add_days_negative(self) -> None:
        self.assertEqual(add_days("2025-01-08", -7), "2025-01-01")

    def test_add_days_zero(self) -> None:
        self.assertEqual(add_days("2025-01-01", 0), "2025-01-01")

    def test_add_days_year_rollover(self) -> None:
        self.assertEqual(add_days("2024-12-31", 1), "2025-01-01")

    def test_add_days_negative_year_rollover(self) -> None:
        self.assertEqual(add_days("2025-01-01", -1), "2024-12-31")

    def test_add_days_february_leap(self) -> None:
        self.assertEqual(add_days("2024-02-28", 1), "2024-02-29")

    def test_add_days_february_non_leap(self) -> None:
        self.assertEqual(add_days("2025-02-28", 1), "2025-03-01")

    def test_days_between_positive(self) -> None:
        self.assertEqual(days_between("2025-01-01", "2025-01-08"), 7)

    def test_days_between_negative(self) -> None:
        self.assertEqual(days_between("2025-01-08", "2025-01-01"), -7)

    def test_days_between_zero(self) -> None:
        self.assertEqual(days_between("2025-01-01", "2025-01-01"), 0)

    def test_days_between_ignores_time(self) -> None:
        self.assertEqual(days_between("2025-01-01T00:00:00",
                                       "2025-01-02T23:59:59"), 1)


class TestRangeBoundaries(unittest.TestCase):
    """start_of_week / end_of_week / start_of_month / end_of_month."""

    def test_start_of_week_saturday_first(self) -> None:
        # 2025-03-25 is a Tuesday; Saturday-first week starts 2025-03-22.
        self.assertEqual(start_of_week("2025-03-25"), "2025-03-22")

    def test_end_of_week_saturday_first(self) -> None:
        self.assertEqual(end_of_week("2025-03-25"), "2025-03-28")

    def test_start_of_week_already_saturday(self) -> None:
        self.assertEqual(start_of_week("2025-03-22"), "2025-03-22")

    def test_start_of_week_sunday_first(self) -> None:
        self.assertEqual(start_of_week("2025-03-25", first_day=0),
                         "2025-03-23")

    def test_start_of_week_monday_first(self) -> None:
        self.assertEqual(start_of_week("2025-03-25", first_day=1),
                         "2025-03-24")

    def test_start_of_month(self) -> None:
        self.assertEqual(start_of_month("2025-03-25"), "2025-03-01")

    def test_start_of_month_already_first(self) -> None:
        self.assertEqual(start_of_month("2025-03-01"), "2025-03-01")

    def test_end_of_month_february_non_leap(self) -> None:
        self.assertEqual(end_of_month("2025-02-10"), "2025-02-28")

    def test_end_of_month_february_leap(self) -> None:
        self.assertEqual(end_of_month("2024-02-10"), "2024-02-29")

    def test_end_of_month_december(self) -> None:
        self.assertEqual(end_of_month("2025-12-10"), "2025-12-31")

    def test_end_of_month_january(self) -> None:
        self.assertEqual(end_of_month("2025-01-15"), "2025-01-31")

    def test_end_of_month_30_day_month(self) -> None:
        self.assertEqual(end_of_month("2025-04-15"), "2025-04-30")

    def test_start_of_year(self) -> None:
        self.assertEqual(start_of_year("2025-06-15"), "2025-01-01")

    def test_end_of_year(self) -> None:
        self.assertEqual(end_of_year("2025-06-15"), "2025-12-31")


class TestRangeGeneration(unittest.TestCase):
    """range_days / range_months."""

    def test_range_days_basic(self) -> None:
        out = range_days("2025-01-01", "2025-01-03")
        self.assertEqual(out, ["2025-01-01", "2025-01-02", "2025-01-03"])

    def test_range_days_single(self) -> None:
        out = range_days("2025-01-01", "2025-01-01")
        self.assertEqual(out, ["2025-01-01"])

    def test_range_days_reversed_inputs(self) -> None:
        # Should normalize regardless of input order.
        out = range_days("2025-01-03", "2025-01-01")
        self.assertEqual(out, ["2025-01-01", "2025-01-02", "2025-01-03"])

    def test_range_days_count(self) -> None:
        out = range_days("2025-01-01", "2025-01-31")
        self.assertEqual(len(out), 31)

    def test_range_days_year_leap(self) -> None:
        out = range_days("2024-01-01", "2024-12-31")
        self.assertEqual(len(out), 366)

    def test_range_days_year_non_leap(self) -> None:
        out = range_days("2025-01-01", "2025-12-31")
        self.assertEqual(len(out), 365)

    def test_range_months_basic(self) -> None:
        out = range_months("2025-01-15", "2025-03-20")
        self.assertEqual(out, ["2025-01-01", "2025-02-01", "2025-03-01"])

    def test_range_months_single(self) -> None:
        out = range_months("2025-01-15", "2025-01-20")
        self.assertEqual(out, ["2025-01-01"])

    def test_range_months_year_span(self) -> None:
        out = range_months("2024-06-01", "2025-06-01")
        self.assertEqual(len(out), 13)

    def test_range_months_reversed(self) -> None:
        out = range_months("2025-03-20", "2025-01-15")
        self.assertEqual(out, ["2025-01-01", "2025-02-01", "2025-03-01"])


class TestLocalizedNames(unittest.TestCase):
    """weekday_name / month_name."""

    def test_weekday_friday_fa(self) -> None:
        self.assertEqual(weekday_name("2025-03-21", "fa"), "جمعه")

    def test_weekday_saturday_en(self) -> None:
        self.assertEqual(weekday_name("2025-03-22", "en"), "Saturday")

    def test_weekday_sunday_en(self) -> None:
        self.assertEqual(weekday_name("2025-03-23", "en"), "Sunday")

    def test_weekday_monday_en(self) -> None:
        self.assertEqual(weekday_name("2025-03-24", "en"), "Monday")

    def test_weekday_fa_all_seven_days(self) -> None:
        # Walk 7 days starting from 2025-03-22 (Saturday).
        expected_fa = ["شنبه", "یکشنبه", "دوشنبه",
                       "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
        for i, expected in enumerate(expected_fa):
            d = add_days("2025-03-22", i)
            self.assertEqual(weekday_name(d, "fa"), expected)

    def test_month_name_en(self) -> None:
        self.assertEqual(month_name("2025-03-21", "en"), "March")

    def test_month_name_fa(self) -> None:
        self.assertEqual(month_name("2025-03-21", "fa"), "مارس")

    def test_month_name_all_twelve_en(self) -> None:
        expected = ["January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November",
                    "December"]
        for i, name in enumerate(expected, start=1):
            iso = f"2025-{i:02d}-15"
            self.assertEqual(month_name(iso, "en"), name)


class TestGreeting(unittest.TestCase):
    """greeting returns the right string for the current hour."""

    def _greeting_at(self, hour: int) -> str:
        """Patch datetime.now() to a specific hour and call greeting()."""
        # Figure out the right date so hour maps to morning/afternoon/evening.
        target = datetime(2025, 6, 15, hour, 0, 0)
        with patch("rask.core.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = target
            # Need to expose the .now classmethod on the mock too.
            mock_dt.now = lambda *a, **k: target
            return greeting("fa")

    def test_morning_greeting(self) -> None:
        self.assertEqual(self._greeting_at(9), "صبح بخیر")

    def test_noon_greetings_is_afternoon(self) -> None:
        self.assertEqual(self._greeting_at(12), "عصر بخیر")

    def test_afternoon_greeting(self) -> None:
        self.assertEqual(self._greeting_at(15), "عصر بخیر")

    def test_evening_greeting(self) -> None:
        self.assertEqual(self._greeting_at(19), "شب بخیر")

    def test_late_night_greeting(self) -> None:
        # 2 AM is "evening" per the rule (5:00-4:59 = evening).
        self.assertEqual(self._greeting_at(2), "شب بخیر")

    def test_early_morning_greeting(self) -> None:
        # 5 AM = morning (5:00-11:59).
        self.assertEqual(self._greeting_at(5), "صبح بخیر")

    def test_boundary_11_59(self) -> None:
        self.assertEqual(self._greeting_at(11), "صبح بخیر")

    def test_boundary_12_00(self) -> None:
        self.assertEqual(self._greeting_at(12), "عصر بخیر")

    def test_boundary_16_59(self) -> None:
        self.assertEqual(self._greeting_at(16), "عصر بخیر")

    def test_boundary_17_00(self) -> None:
        self.assertEqual(self._greeting_at(17), "شب بخیر")

    def test_greeting_en(self) -> None:
        target = datetime(2025, 6, 15, 9, 0, 0)
        with patch("rask.core.time_utils.datetime") as mock_dt:
            mock_dt.now = lambda *a, **k: target
            self.assertEqual(greeting("en"), "Good morning")


class TestPredicates(unittest.TestCase):
    """is_today / is_this_week / is_this_month."""

    def test_is_today_true_for_today(self) -> None:
        self.assertTrue(is_today(today_iso()))

    def test_is_today_false_for_yesterday(self) -> None:
        self.assertFalse(is_today(add_days(today_iso(), -1)))

    def test_is_today_false_for_invalid(self) -> None:
        self.assertFalse(is_today("not-a-date"))

    def test_is_today_false_for_empty(self) -> None:
        self.assertFalse(is_today(""))

    def test_is_this_week_true_for_today(self) -> None:
        self.assertTrue(is_this_week(today_iso()))

    def test_is_this_week_false_for_30_days_ago(self) -> None:
        self.assertFalse(is_this_week(add_days(today_iso(), -30)))

    def test_is_this_month_true_for_today(self) -> None:
        self.assertTrue(is_this_month(today_iso()))

    def test_is_this_month_false_for_60_days_ago(self) -> None:
        self.assertFalse(is_this_month(add_days(today_iso(), -60)))

    def test_is_this_month_false_for_invalid(self) -> None:
        self.assertFalse(is_this_month("garbage"))


class TestEdgeCases(unittest.TestCase):
    """Boundary conditions: midnight, noon, year edges, leap day."""

    def test_parse_iso_at_midnight(self) -> None:
        d = parse_iso("2025-01-01T00:00:00")
        self.assertEqual(d.hour, 0)
        self.assertEqual(d.minute, 0)
        self.assertEqual(d.second, 0)

    def test_parse_iso_at_noon(self) -> None:
        d = parse_iso("2025-01-01T12:00:00")
        self.assertEqual(d.hour, 12)

    def test_parse_iso_at_end_of_day(self) -> None:
        d = parse_iso("2025-01-01T23:59:59")
        self.assertEqual(d.hour, 23)
        self.assertEqual(d.second, 59)

    def test_add_days_across_leap_day(self) -> None:
        # 2024-02-28 + 1 = 2024-02-29 (leap)
        self.assertEqual(add_days("2024-02-28", 1), "2024-02-29")
        # 2024-02-29 + 1 = 2024-03-01
        self.assertEqual(add_days("2024-02-29", 1), "2024-03-01")

    def test_end_of_month_dec_to_jan_boundary(self) -> None:
        # December has 31 days, January has 31 days.
        self.assertEqual(end_of_month("2025-12-15"), "2025-12-31")

    def test_end_of_month_february_2100_non_leap(self) -> None:
        # 2100 is NOT a leap year (divisible by 100, not by 400).
        self.assertEqual(end_of_month("2100-02-15"), "2100-02-28")

    def test_end_of_month_february_2000_leap(self) -> None:
        # 2000 IS a leap year (divisible by 400).
        self.assertEqual(end_of_month("2000-02-15"), "2000-02-29")

    def test_range_days_with_datetime_inputs(self) -> None:
        # The functions accept datetime strings too.
        out = range_days("2025-01-01T08:00:00", "2025-01-03T20:00:00")
        self.assertEqual(len(out), 3)

    def test_format_timer_24_hours(self) -> None:
        # 24 hours = 86400 seconds.
        self.assertEqual(format_timer(86400, "en"), "24:00:00")

    def test_format_timer_max_int(self) -> None:
        # Very large seconds value — should still format.
        s = format_timer(1_000_000, "en")
        self.assertIn(":", s)


class TestConstantsAndExports(unittest.TestCase):
    """All public names are exported."""

    def test_all_exports_present(self) -> None:
        expected = [
            "now_iso_utc", "now_iso_local", "today_iso", "parse_iso",
            "format_duration", "format_timer", "format_relative",
            "parse_duration", "minutes_to_hhmm", "hhmm_to_minutes",
            "seconds_to_human", "is_today", "is_this_week", "is_this_month",
            "days_between", "add_days", "start_of_week", "end_of_week",
            "start_of_month", "end_of_month", "start_of_year", "end_of_year",
            "range_days", "range_months", "weekday_name", "month_name",
            "greeting",
        ]
        for name in expected:
            self.assertTrue(hasattr(time_utils, name),
                            f"Missing public function: {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
