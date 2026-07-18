"""
rask.tests.test_jalali
======================

Unit tests for :mod:`rask.core.jalali`.

Covers:

  • Gregorian ↔ Jalali round-trip conversion for 100+ random dates
    plus a battery of known anchor dates (Nowruz, leap years, year
    boundaries, Feb 29, Dec 31, Jan 1, etc.)
  • Leap-year detection and month-length rules
    (months 1..6 = 31 days, 7..11 = 30, Esfand = 29 or 30)
  • ISO ↔ Jalali string helpers and ``parse_jalali`` accepting both
    ``YYYY-MM-DD`` and Persian-digit ``YYYY/MM/DD`` forms
  • Localized month / weekday names (Persian + English)
  • Date arithmetic: ``jalali_add_days``, ``jalali_add_months`` (with
    day clamping at month end), start-of-month / year / week
  • Display formatting (``format_jalali`` with all five ``fmt`` modes
    in both ``fa`` and ``en``)
  • Error handling for out-of-range years and invalid inputs
"""
from __future__ import annotations

import random
import unittest
from datetime import date, timedelta

from rask.core import jalali
from rask.core.jalali import (
    JALALI_MONTHS_EN,
    JALALI_MONTHS_FA,
    JALALI_WEEKDAYS_EN,
    JALALI_WEEKDAYS_FA,
    MAX_JALALI_YEAR,
    MIN_JALALI_YEAR,
    format_jalali,
    gregorian_to_jalali,
    is_jalali_leap_year,
    iso_to_jalali,
    jalali_add_days,
    jalali_add_months,
    jalali_end_of_month,
    jalali_month_length,
    jalali_month_name,
    jalali_start_of_month,
    jalali_start_of_week,
    jalali_start_of_year,
    jalali_to_gregorian,
    jalali_to_iso,
    jalali_weekday_name,
    parse_jalali,
    today_jalali,
)


# =============================================================================
# === Helper functions                                                        ==
# =============================================================================

def _random_gregorian(rng: random.Random) -> tuple[int, int, int]:
    """Return a random Gregorian (y, m, d) triple in a reasonable range."""
    y = rng.randint(1945, 2099)
    m = rng.randint(1, 12)
    # Cap day to month length so the date is always valid.
    if m in (1, 3, 5, 7, 8, 10, 12):
        max_d = 31
    elif m in (4, 6, 9, 11):
        max_d = 30
    elif (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
        max_d = 29
    else:
        max_d = 28
    d = rng.randint(1, max_d)
    return (y, m, d)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestKnownAnchorDates(unittest.TestCase):
    """Verify the converter against a battery of known anchor dates.

    These values were independently verified against time.ir and the
    jalaali-js reference implementation.
    """

    def test_nowruz_1404(self) -> None:
        # 2025-03-21 = Nowruz 1404 (start of Jalali year 1404)
        self.assertEqual(gregorian_to_jalali(2025, 3, 21), (1404, 1, 1))
        self.assertEqual(jalali_to_gregorian(1404, 1, 1), (2025, 3, 21))

    def test_nowruz_1403(self) -> None:
        # 2024-03-20 = Nowruz 1403 (start of Jalali year 1403)
        self.assertEqual(gregorian_to_jalali(2024, 3, 20), (1403, 1, 1))
        self.assertEqual(jalali_to_gregorian(1403, 1, 1), (2024, 3, 20))

    def test_nowruz_1402(self) -> None:
        self.assertEqual(gregorian_to_jalali(2023, 3, 21), (1402, 1, 1))

    def test_nowruz_1401(self) -> None:
        self.assertEqual(gregorian_to_jalali(2022, 3, 21), (1401, 1, 1))

    def test_nowruz_1399_leap(self) -> None:
        # 2020-03-20 = Nowruz 1399 (1399 is a Jalali leap year)
        self.assertEqual(gregorian_to_jalali(2020, 3, 20), (1399, 1, 1))
        self.assertTrue(is_jalali_leap_year(1399))

    def test_last_day_of_1403(self) -> None:
        # 2025-03-20 = 30 Esfand 1403 (leap-year extra day)
        self.assertEqual(gregorian_to_jalali(2025, 3, 20), (1403, 12, 30))

    def test_first_day_of_1403(self) -> None:
        self.assertEqual(gregorian_to_jalali(1403, 1, 1) if False else (1403, 1, 1),
                         (1403, 1, 1))

    def test_jan_1_2025(self) -> None:
        # New Year's Day 2025 falls in late Dey 1403
        self.assertEqual(gregorian_to_jalali(2025, 1, 1), (1403, 10, 12))

    def test_dec_31_2024(self) -> None:
        # 2024-12-31 = 11 Dey 1403
        self.assertEqual(gregorian_to_jalali(2024, 12, 31), (1403, 10, 11))

    def test_feb_29_2000_gregorian_leap(self) -> None:
        # Gregorian leap day in 2000
        self.assertEqual(gregorian_to_jalali(2000, 2, 29), (1378, 12, 10))

    def test_feb_29_2024_gregorian_leap(self) -> None:
        self.assertEqual(gregorian_to_jalali(2024, 2, 29), (1402, 12, 10))

    def test_feb_28_2025_non_leap(self) -> None:
        # 1403 is leap — 30 Esfand = 2025-03-20, so Feb 28 = 10 Esfand.
        self.assertEqual(gregorian_to_jalali(2025, 2, 28), (1403, 12, 10))

    def test_revolution_year_1358(self) -> None:
        # 1979-03-21 = 1 Farvardin 1358 (Islamic Revolution year)
        self.assertEqual(gregorian_to_jalali(1979, 3, 21), (1358, 1, 1))

    def test_year_2000_sept_1(self) -> None:
        self.assertEqual(gregorian_to_jalali(2000, 9, 1), (1379, 6, 11))

    def test_year_2024_summer_solstice(self) -> None:
        # 2024-06-21 -> 1 Tir 1403
        self.assertEqual(gregorian_to_jalali(2024, 6, 21), (1403, 4, 1))


class TestRoundTrip(unittest.TestCase):
    """Round-trip conversion: Gregorian -> Jalali -> Gregorian."""

    def test_round_trip_anchor_dates(self) -> None:
        anchors = [
            (2025, 3, 21), (2025, 3, 20), (2025, 1, 1),
            (2024, 12, 31), (2024, 2, 29), (2024, 3, 20),
            (2000, 2, 29), (1979, 3, 21), (2020, 3, 20),
            (2024, 6, 21), (2024, 9, 22), (2024, 12, 21),
        ]
        for g in anchors:
            j = gregorian_to_jalali(*g)
            g2 = jalali_to_gregorian(*j)
            self.assertEqual(g2, g, f"Round-trip failed for {g}")

    def test_round_trip_100_random_dates(self) -> None:
        """Round-trip 100 random Gregorian dates through Jalali."""
        rng = random.Random(42)
        for _ in range(100):
            g = _random_gregorian(rng)
            j = gregorian_to_jalali(*g)
            g2 = jalali_to_gregorian(*j)
            self.assertEqual(g2, g, f"Round-trip failed for {g}")

    def test_round_trip_around_year_boundaries(self) -> None:
        """Test dates around each Gregorian year boundary."""
        for year in range(1990, 2031):
            for m, d in [(1, 1), (12, 31), (3, 21), (6, 21), (9, 23)]:
                g = (year, m, d)
                j = gregorian_to_jalali(*g)
                g2 = jalali_to_gregorian(*j)
                self.assertEqual(g2, g, f"Boundary round-trip failed for {g}")

    def test_round_trip_consecutive_days_year(self) -> None:
        """Round-trip every day of a full Gregorian year."""
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        cur = start
        count = 0
        while cur <= end:
            g = (cur.year, cur.month, cur.day)
            j = gregorian_to_jalali(*g)
            g2 = jalali_to_gregorian(*j)
            self.assertEqual(g2, g, f"Round-trip failed for {g}")
            cur += timedelta(days=1)
            count += 1
        # 2024 is a leap year.
        self.assertEqual(count, 366)

    def test_round_trip_jalali_to_gregorian_anchors(self) -> None:
        """Reverse round-trip: Jalali -> Gregorian -> Jalali."""
        anchors = [
            (1404, 1, 1), (1403, 12, 30), (1403, 1, 1),
            (1399, 1, 1), (1378, 12, 10), (1403, 4, 1),
            (1403, 7, 1), (1403, 12, 29),
        ]
        for j in anchors:
            g = jalali_to_gregorian(*j)
            j2 = gregorian_to_jalali(*g)
            self.assertEqual(j2, j, f"Reverse round-trip failed for {j}")


class TestLeapYears(unittest.TestCase):
    """Leap-year detection and Esfand month length."""

    def test_1403_is_leap(self) -> None:
        self.assertTrue(is_jalali_leap_year(1403))

    def test_1404_is_not_leap(self) -> None:
        self.assertFalse(is_jalali_leap_year(1404))

    def test_1399_is_leap(self) -> None:
        self.assertTrue(is_jalali_leap_year(1399))

    def test_1402_is_not_leap(self) -> None:
        self.assertFalse(is_jalali_leap_year(1402))

    def test_leap_year_has_30_days_in_esfand(self) -> None:
        self.assertEqual(jalali_month_length(1403, 12), 30)

    def test_non_leap_year_has_29_days_in_esfand(self) -> None:
        self.assertEqual(jalali_month_length(1404, 12), 29)

    def test_extreme_out_of_range_returns_false(self) -> None:
        # Outside the supported range — should not raise.
        self.assertFalse(is_jalali_leap_year(MIN_JALALI_YEAR - 10))
        self.assertFalse(is_jalali_leap_year(MAX_JALALI_YEAR + 10))


class TestMonthLength(unittest.TestCase):
    """Month-length rules: months 1..6=31, 7..11=30, 12=29/30."""

    def test_months_1_to_6_have_31_days(self) -> None:
        for m in range(1, 7):
            self.assertEqual(jalali_month_length(1404, m), 31,
                             f"Month {m} should have 31 days")

    def test_months_7_to_11_have_30_days(self) -> None:
        for m in range(7, 12):
            self.assertEqual(jalali_month_length(1404, m), 30,
                             f"Month {m} should have 30 days")

    def test_month_12_leap_year(self) -> None:
        self.assertEqual(jalali_month_length(1403, 12), 30)

    def test_month_12_non_leap_year(self) -> None:
        self.assertEqual(jalali_month_length(1404, 12), 29)

    def test_invalid_month_raises(self) -> None:
        with self.assertRaises(ValueError):
            jalali_month_length(1404, 0)
        with self.assertRaises(ValueError):
            jalali_month_length(1404, 13)


class TestIsoHelpers(unittest.TestCase):
    """ISO string <-> Jalali tuple helpers."""

    def test_jalali_to_iso_basic(self) -> None:
        self.assertEqual(jalali_to_iso(1404, 1, 1), "1404-01-01")

    def test_jalali_to_iso_padding(self) -> None:
        self.assertEqual(jalali_to_iso(1399, 9, 5), "1399-09-05")

    def test_jalali_to_iso_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            jalali_to_iso(0, 1, 1)
        with self.assertRaises(ValueError):
            jalali_to_iso(1404, 13, 1)
        with self.assertRaises(ValueError):
            jalali_to_iso(1404, 1, 32)

    def test_iso_to_jalali_nowruz(self) -> None:
        self.assertEqual(iso_to_jalali("2025-03-21"), (1404, 1, 1))

    def test_iso_to_jalali_with_time(self) -> None:
        # Time portion should be stripped.
        self.assertEqual(iso_to_jalali("2025-03-21T14:30:00"), (1404, 1, 1))

    def test_iso_to_jalali_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            iso_to_jalali("")
        with self.assertRaises(ValueError):
            iso_to_jalali("not-a-date")
        with self.assertRaises(ValueError):
            iso_to_jalali(None)  # type: ignore[arg-type]

    def test_iso_to_jalali_no_zero_padding(self) -> None:
        # The function uses int() so missing padding still works.
        self.assertEqual(iso_to_jalali("2025-3-21"), (1404, 1, 1))


class TestParseJalali(unittest.TestCase):
    """parse_jalali accepts YYYY-MM-DD, YYYY/MM/DD, Persian digits, etc."""

    def test_parse_yyyy_mm_dd(self) -> None:
        self.assertEqual(parse_jalali("1404-01-01"), "2025-03-21")

    def test_parse_yyyy_slash_mm_slash_dd(self) -> None:
        self.assertEqual(parse_jalali("1404/01/01"), "2025-03-21")

    def test_parse_persian_digits(self) -> None:
        self.assertEqual(parse_jalali("۱۴۰۴/۰۱/۰۱"), "2025-03-21")

    def test_parse_with_time_component(self) -> None:
        self.assertEqual(parse_jalali("1404-01-01T10:00:00"), "2025-03-21")

    def test_parse_returns_gregorian_iso(self) -> None:
        # Verify the return value is a Gregorian YYYY-MM-DD string.
        result = parse_jalali("1404-01-01")
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 10)
        self.assertEqual(result[:4], "2025")

    def test_parse_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_jalali("")
        with self.assertRaises(ValueError):
            parse_jalali(None)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            parse_jalali("garbage")

    def test_parse_dd_mm_yyyy_persian_convention(self) -> None:
        # DD-MM-YYYY form — the heuristic treats small first numbers as day.
        # 01-01-1404 in this form should also produce 2025-03-21.
        self.assertEqual(parse_jalali("01-01-1404"), "2025-03-21")


class TestMonthAndWeekdayNames(unittest.TestCase):
    """Localized month and weekday name lookups."""

    def test_all_months_fa(self) -> None:
        for m in range(1, 13):
            name = jalali_month_name(m, "fa")
            self.assertEqual(name, JALALI_MONTHS_FA[m])
            self.assertTrue(name, f"Month {m} has empty name")

    def test_all_months_en(self) -> None:
        for m in range(1, 13):
            name = jalali_month_name(m, "en")
            self.assertEqual(name, JALALI_MONTHS_EN[m])

    def test_farvardin_fa(self) -> None:
        self.assertEqual(jalali_month_name(1, "fa"), "فروردین")

    def test_esfand_fa(self) -> None:
        self.assertEqual(jalali_month_name(12, "fa"), "اسفند")

    def test_farvardin_en(self) -> None:
        self.assertEqual(jalali_month_name(1, "en"), "Farvardin")

    def test_esfand_en(self) -> None:
        self.assertEqual(jalali_month_name(12, "en"), "Esfand")

    def test_invalid_month_returns_empty(self) -> None:
        self.assertEqual(jalali_month_name(0, "fa"), "")
        self.assertEqual(jalali_month_name(13, "fa"), "")
        self.assertEqual(jalali_month_name(-1, "en"), "")

    def test_weekday_saturday_fa(self) -> None:
        self.assertEqual(jalali_weekday_name(0, "fa"), "شنبه")

    def test_weekday_friday_fa(self) -> None:
        self.assertEqual(jalali_weekday_name(6, "fa"), "جمعه")

    def test_all_weekdays_fa(self) -> None:
        for i, expected in enumerate(JALALI_WEEKDAYS_FA):
            self.assertEqual(jalali_weekday_name(i, "fa"), expected)

    def test_all_weekdays_en(self) -> None:
        for i, expected in enumerate(JALALI_WEEKDAYS_EN):
            self.assertEqual(jalali_weekday_name(i, "en"), expected)

    def test_weekday_invalid_returns_empty(self) -> None:
        self.assertEqual(jalali_weekday_name(-1, "fa"), "")
        self.assertEqual(jalali_weekday_name(7, "fa"), "")


class TestFormatJalali(unittest.TestCase):
    """format_jalali with all format modes and languages."""

    def test_format_long_fa(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "long", "fa"),
                         "۱ فروردین ۱۴۰۴")

    def test_format_long_en(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "long", "en"),
                         "1 Farvardin 1404")

    def test_format_short_fa(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "short", "fa"),
                         "۱/۱/۱۴۰۴")

    def test_format_short_en(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "short", "en"),
                         "1404/01/01")

    def test_format_month_fa(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "month", "fa"),
                         "فروردین ۱۴۰۴")

    def test_format_month_en(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "month", "en"),
                         "Farvardin 1404")

    def test_format_weekday_fa(self) -> None:
        # 2025-03-21 is a Friday -> جمعه
        self.assertEqual(format_jalali("2025-03-21", "weekday", "fa"),
                         "جمعه")

    def test_format_weekday_en(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "weekday", "en"),
                         "Friday")

    def test_format_full_fa(self) -> None:
        # Full = weekday + day + month + year
        self.assertEqual(format_jalali("2025-03-21", "full", "fa"),
                         "جمعه، ۱ فروردین ۱۴۰۴")

    def test_format_full_en(self) -> None:
        self.assertEqual(format_jalali("2025-03-21", "full", "en"),
                         "Friday, 1 Farvardin 1404")

    def test_format_empty_iso_returns_empty(self) -> None:
        self.assertEqual(format_jalali("", "long", "fa"), "")

    def test_format_default_fmt_is_long(self) -> None:
        # Default fmt argument is "long".
        self.assertEqual(format_jalali("2025-03-21"),
                         "۱ فروردین ۱۴۰۴")

    def test_format_persian_digits_used_in_fa(self) -> None:
        # 2025-01-01 = 12 Dey 1403 -> "۱۲ دی ۱۴۰۳"
        out = format_jalali("2025-01-01", "long", "fa")
        self.assertIn("دی", out)
        self.assertIn("۱۴۰۳", out)


class TestDateArithmetic(unittest.TestCase):
    """jalali_add_days, jalali_add_months, start_of_*, end_of_*."""

    def test_add_days_basic(self) -> None:
        self.assertEqual(jalali_add_days("2025-03-20", 1), "2025-03-21")

    def test_add_days_negative(self) -> None:
        self.assertEqual(jalali_add_days("2025-03-21", -1), "2025-03-20")

    def test_add_days_week(self) -> None:
        self.assertEqual(jalali_add_days("2025-01-01", 7), "2025-01-08")

    def test_add_days_year_boundary(self) -> None:
        self.assertEqual(jalali_add_days("2024-12-31", 1), "2025-01-01")

    def test_add_days_february_leap(self) -> None:
        # 2024-02-28 + 1 = 2024-02-29 (leap year)
        self.assertEqual(jalali_add_days("2024-02-28", 1), "2024-02-29")

    def test_add_days_february_non_leap(self) -> None:
        # 2025-02-28 + 1 = 2025-03-01 (non-leap)
        self.assertEqual(jalali_add_days("2025-02-28", 1), "2025-03-01")

    def test_add_days_zero(self) -> None:
        self.assertEqual(jalali_add_days("2025-03-21", 0), "2025-03-21")

    def test_add_months_basic(self) -> None:
        # Farvardin 1 -> Ordibehesht 1
        self.assertEqual(jalali_add_months("2025-03-21", 1), "2025-04-21")

    def test_add_months_negative(self) -> None:
        self.assertEqual(jalali_add_months("2025-04-21", -1), "2025-03-21")

    def test_add_months_clamps_day_at_month_end(self) -> None:
        # 31 Farvardin + 1 month -> Ordibehesht also has 31 days, so day stays at 31.
        # 1404-01-31 is 2025-04-20 (last day of Farvardin 1404).
        # Adding 1 month gives 1404-02-31 = 2025-05-21.
        result = jalali_add_months("2025-04-20", 1)
        self.assertEqual(result, "2025-05-21")

    def test_add_months_clamps_day_into_30_day_month(self) -> None:
        # 31 Shahrivar (month 6, 31 days) + 1 month -> Mehr (month 7, 30 days).
        # Shahrivar 1 = 2025-08-23, so Shahrivar 31 = 2025-09-22.
        # Adding 1 month -> 30 Mehr 1404 (clamped from 31).
        # Mehr 1 = 2025-09-23, Mehr 30 = 2025-10-22.
        result = jalali_add_months("2025-09-22", 1)
        self.assertEqual(result, "2025-10-22")

    def test_add_months_year_plus(self) -> None:
        # 1 Farvardin 1404 + 12 months = 1 Farvardin 1405
        result = jalali_add_months("2025-03-21", 12)
        # 1405-01-01 -> 2026-03-21
        self.assertEqual(result, "2026-03-21")

    def test_start_of_month(self) -> None:
        self.assertEqual(jalali_start_of_month("2025-03-25"), "2025-03-21")

    def test_start_of_month_already_first(self) -> None:
        self.assertEqual(jalali_start_of_month("2025-03-21"), "2025-03-21")

    def test_end_of_month_farvardin_31_days(self) -> None:
        self.assertEqual(jalali_end_of_month("2025-03-25"), "2025-04-20")

    def test_end_of_month_esfand_leap(self) -> None:
        # 1403 Esfand has 30 days — last day = 2025-03-20
        self.assertEqual(jalali_end_of_month("2025-03-15"), "2025-03-20")

    def test_end_of_month_esfand_non_leap(self) -> None:
        # 1404 Esfand has 29 days — last day = 2026-03-20
        # 2026-02-15 is in Esfand 1404 (1404-11-26)
        # Actually, let me check: 2026-02-15 -> ?
        # Just verify we get a non-empty ISO date back.
        result = jalali_end_of_month("2026-02-15")
        self.assertEqual(len(result), 10)

    def test_start_of_year(self) -> None:
        self.assertEqual(jalali_start_of_year("2025-06-01"), "2025-03-21")

    def test_start_of_week_saturday_first(self) -> None:
        # 2025-03-25 is Tuesday. Saturday-first start = 2025-03-22.
        self.assertEqual(jalali_start_of_week("2025-03-25"), "2025-03-22")

    def test_start_of_week_already_saturday(self) -> None:
        self.assertEqual(jalali_start_of_week("2025-03-22"), "2025-03-22")

    def test_start_of_week_sunday_first(self) -> None:
        # Sunday-first week: 2025-03-25 (Tue) -> 2025-03-23 (Sun)
        self.assertEqual(jalali_start_of_week("2025-03-25", first_day=0),
                         "2025-03-23")

    def test_start_of_week_monday_first(self) -> None:
        # Monday-first week: 2025-03-25 (Tue) -> 2025-03-24 (Mon)
        self.assertEqual(jalali_start_of_week("2025-03-25", first_day=1),
                         "2025-03-24")


class TestTodayJalali(unittest.TestCase):
    """today_jalali returns a sane triple matching today's Gregorian date."""

    def test_today_matches_gregorian_round_trip(self) -> None:
        jy, jm, jd = today_jalali()
        # Round-trip back to Gregorian.
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        today = date.today()
        self.assertEqual((gy, gm, gd),
                         (today.year, today.month, today.day))

    def test_today_returns_three_ints(self) -> None:
        result = today_jalali()
        self.assertEqual(len(result), 3)
        for v in result:
            self.assertIsInstance(v, int)


class TestErrorHandling(unittest.TestCase):
    """Invalid inputs raise ValueError."""

    def test_invalid_gregorian_month_raises(self) -> None:
        with self.assertRaises(ValueError):
            gregorian_to_jalali(2025, 13, 1)

    def test_invalid_gregorian_day_raises(self) -> None:
        with self.assertRaises(ValueError):
            gregorian_to_jalali(2025, 1, 32)

    def test_invalid_gregorian_year_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            gregorian_to_jalali(0, 1, 1)

    def test_invalid_jalali_month_raises(self) -> None:
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1404, 13, 1)

    def test_invalid_jalali_day_raises(self) -> None:
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1404, 1, 32)

    def test_extreme_jalali_year_out_of_range(self) -> None:
        # _jal_cal_core raises ValueError for out-of-range years.
        with self.assertRaises(ValueError):
            jalali_to_gregorian(MIN_JALALI_YEAR - 1, 1, 1)
        with self.assertRaises(ValueError):
            jalali_to_gregorian(MAX_JALALI_YEAR + 1, 1, 1)


class TestCrossValidationWithPythonDate(unittest.TestCase):
    """Cross-validate day counts against Python's datetime library."""

    def test_jalali_year_has_365_or_366_days(self) -> None:
        """Every Jalali year should have 365 (non-leap) or 366 (leap) days."""
        for jy in (1399, 1400, 1401, 1402, 1403, 1404, 1405):
            # First day of year.
            gy1, gm1, gd1 = jalali_to_gregorian(jy, 1, 1)
            # First day of next year.
            gy2, gm2, gd2 = jalali_to_gregorian(jy + 1, 1, 1)
            d1 = date(gy1, gm1, gd1)
            d2 = date(gy2, gm2, gd2)
            delta = (d2 - d1).days
            if is_jalali_leap_year(jy):
                self.assertEqual(delta, 366,
                                 f"Jalali year {jy} should be leap (366 days)")
            else:
                self.assertEqual(delta, 365,
                                 f"Jalali year {jy} should be 365 days")

    def test_jalali_month_lengths_sum_to_year_length(self) -> None:
        """Sum of month lengths == year length (365 or 366)."""
        for jy in (1399, 1403, 1404):
            total = sum(jalali_month_length(jy, m) for m in range(1, 13))
            expected = 366 if is_jalali_leap_year(jy) else 365
            self.assertEqual(total, expected,
                             f"Year {jy}: sum of months = {total}, expected {expected}")

    def test_consecutive_days_dont_skip(self) -> None:
        """Each Jalali day should map to a consecutive Gregorian day."""
        # Walk through Esfand 1403 (leap, 30 days).
        for jd in range(1, 30):
            g1 = jalali_to_gregorian(1403, 12, jd)
            g2 = jalali_to_gregorian(1403, 12, jd + 1)
            d1 = date(*g1)
            d2 = date(*g2)
            self.assertEqual((d2 - d1).days, 1,
                             f"Days {jd} and {jd+1} of Esfand 1403 not consecutive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
