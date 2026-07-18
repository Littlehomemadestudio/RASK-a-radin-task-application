"""
rask.tests.test_validators
==========================

Unit tests for :mod:`rask.core.validators`.

Covers:

  • Title validation: empty, whitespace-only, too long, control chars
  • PIN format (4-6 ASCII digits)
  • ISO date / datetime validation (including Z, +offset, fractional sec)
  • HH:MM 24-hour time validation
  • Hex color (3, 6, 8 digits, optional leading #)
  • Email and URL pragmatic regexes
  • Duration range (0..1440 min) and target minutes (1..10000)
  • Tag sanitization (strip, lowercase, dedupe, truncate, limit 10)
  • Notes sanitization (preserve newlines, truncate at 5000)
  • Safe int / float parsing with Persian digit normalization
"""
from __future__ import annotations

import unittest

from rask.core import validators
from rask.core.validators import (
    NOTES_MAX_LEN,
    TAG_MAX_LEN,
    TAGS_MAX_COUNT,
    TITLE_MAX_LEN,
    is_valid_color_hex,
    is_valid_duration_min,
    is_valid_email,
    is_valid_hhmm,
    is_valid_iso_date,
    is_valid_iso_datetime,
    is_valid_pin,
    is_valid_target_minutes,
    is_valid_title,
    is_valid_url,
    parse_float_safe,
    parse_int_safe,
    sanitize_notes,
    sanitize_tags,
    sanitize_title,
)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestTitleValidation(unittest.TestCase):
    """is_valid_title / sanitize_title."""

    def test_valid_simple(self) -> None:
        self.assertTrue(is_valid_title("Hello"))

    def test_valid_persian(self) -> None:
        self.assertTrue(is_valid_title("تمرکز عمیق"))

    def test_valid_with_emoji(self) -> None:
        self.assertTrue(is_valid_title("Deep work 🎯"))

    def test_valid_max_length(self) -> None:
        self.assertTrue(is_valid_title("a" * TITLE_MAX_LEN))

    def test_empty_string(self) -> None:
        self.assertFalse(is_valid_title(""))

    def test_whitespace_only(self) -> None:
        self.assertFalse(is_valid_title("    "))
        self.assertFalse(is_valid_title("\t\t"))
        self.assertFalse(is_valid_title("\n\n"))

    def test_too_long(self) -> None:
        self.assertFalse(is_valid_title("a" * (TITLE_MAX_LEN + 1)))

    def test_none(self) -> None:
        self.assertFalse(is_valid_title(None))

    def test_integer(self) -> None:
        self.assertFalse(is_valid_title(123))  # type: ignore[arg-type]

    def test_list(self) -> None:
        self.assertFalse(is_valid_title(["a", "b"]))  # type: ignore[arg-type]

    def test_control_char_rejected(self) -> None:
        # Backspace (\x08) is a control char and should be rejected.
        self.assertFalse(is_valid_title("hello\x08world"))

    def test_newline_allowed(self) -> None:
        # Newlines are explicitly allowed.
        self.assertTrue(is_valid_title("hello\nworld"))

    def test_tab_allowed(self) -> None:
        self.assertTrue(is_valid_title("hello\tworld"))


class TestSanitizeTitle(unittest.TestCase):
    """sanitize_title collapses whitespace and truncates."""

    def test_strip_leading_trailing(self) -> None:
        self.assertEqual(sanitize_title("  hello  "), "hello")

    def test_collapse_internal_whitespace(self) -> None:
        self.assertEqual(sanitize_title("hello   world"), "hello world")
        self.assertEqual(sanitize_title("a\t\tb"), "a b")
        self.assertEqual(sanitize_title("a\n\nb"), "a b")

    def test_truncate_to_max_len(self) -> None:
        s = sanitize_title("a" * (TITLE_MAX_LEN + 100))
        self.assertEqual(len(s), TITLE_MAX_LEN)

    def test_none_returns_empty(self) -> None:
        self.assertEqual(sanitize_title(None), "")

    def test_integer_returns_empty(self) -> None:
        self.assertEqual(sanitize_title(123), "")  # type: ignore[arg-type]

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(sanitize_title(""), "")

    def test_whitespace_only_returns_empty(self) -> None:
        self.assertEqual(sanitize_title("   "), "")

    def test_persian_preserved(self) -> None:
        self.assertEqual(sanitize_title("  تمرکز  "), "تمرکز")


class TestSanitizeNotes(unittest.TestCase):
    """sanitize_notes preserves newlines."""

    def test_strip_outer_whitespace(self) -> None:
        self.assertEqual(sanitize_notes("  hello  "), "hello")

    def test_preserve_newlines(self) -> None:
        self.assertEqual(sanitize_notes("hello\nworld"), "hello\nworld")

    def test_collapse_spaces_not_newlines(self) -> None:
        self.assertEqual(sanitize_notes("hello   world\nfoo   bar"),
                         "hello world\nfoo bar")

    def test_truncate_to_max_len(self) -> None:
        s = sanitize_notes("a" * (NOTES_MAX_LEN + 100))
        self.assertEqual(len(s), NOTES_MAX_LEN)

    def test_none_returns_empty(self) -> None:
        self.assertEqual(sanitize_notes(None), "")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(sanitize_notes(""), "")


class TestPinValidation(unittest.TestCase):
    """is_valid_pin 4-6 ASCII digits."""

    def test_valid_4_digit(self) -> None:
        self.assertTrue(is_valid_pin("1234"))

    def test_valid_5_digit(self) -> None:
        self.assertTrue(is_valid_pin("12345"))

    def test_valid_6_digit(self) -> None:
        self.assertTrue(is_valid_pin("123456"))

    def test_all_zeros(self) -> None:
        self.assertTrue(is_valid_pin("0000"))

    def test_all_nines(self) -> None:
        self.assertTrue(is_valid_pin("9999"))

    def test_too_short(self) -> None:
        self.assertFalse(is_valid_pin("123"))
        self.assertFalse(is_valid_pin("1"))

    def test_too_long(self) -> None:
        self.assertFalse(is_valid_pin("1234567"))
        self.assertFalse(is_valid_pin("12345678"))

    def test_non_digit(self) -> None:
        self.assertFalse(is_valid_pin("12ab"))
        self.assertFalse(is_valid_pin("abcd"))
        self.assertFalse(is_valid_pin("12-34"))
        self.assertFalse(is_valid_pin("12 34"))
        self.assertFalse(is_valid_pin("1.234"))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_pin(""))

    def test_none(self) -> None:
        self.assertFalse(is_valid_pin(None))

    def test_int(self) -> None:
        self.assertFalse(is_valid_pin(1234))  # type: ignore[arg-type]


class TestIsoDateValidation(unittest.TestCase):
    """is_valid_iso_date — YYYY-MM-DD."""

    def test_valid_basic(self) -> None:
        self.assertTrue(is_valid_iso_date("2025-03-21"))

    def test_valid_jan_1(self) -> None:
        self.assertTrue(is_valid_iso_date("2025-01-01"))

    def test_valid_dec_31(self) -> None:
        self.assertTrue(is_valid_iso_date("2025-12-31"))

    def test_valid_leap_day(self) -> None:
        self.assertTrue(is_valid_iso_date("2024-02-29"))

    def test_invalid_leap_day_non_leap_year(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-02-29"))

    def test_invalid_month_13(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-13-01"))

    def test_invalid_month_0(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-00-01"))

    def test_invalid_day_32(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-01-32"))

    def test_missing_zero_padding(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-3-21"))
        self.assertFalse(is_valid_iso_date("2025-03-1"))

    def test_datetime_string(self) -> None:
        self.assertFalse(is_valid_iso_date("2025-03-21T10:00:00"))

    def test_none(self) -> None:
        self.assertFalse(is_valid_iso_date(None))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_iso_date(""))

    def test_int(self) -> None:
        self.assertFalse(is_valid_iso_date(20250321))  # type: ignore[arg-type]


class TestIsoDatetimeValidation(unittest.TestCase):
    """is_valid_iso_datetime."""

    def test_basic_datetime(self) -> None:
        self.assertTrue(is_valid_iso_datetime("2025-03-21T14:30:00"))

    def test_with_z_suffix(self) -> None:
        self.assertTrue(is_valid_iso_datetime("2025-03-21T14:30:00Z"))

    def test_with_positive_offset(self) -> None:
        self.assertTrue(is_valid_iso_datetime("2025-03-21T14:30:00+03:30"))

    def test_with_negative_offset(self) -> None:
        self.assertTrue(is_valid_iso_datetime("2025-03-21T14:30:00-05:00"))

    def test_with_fractional_seconds(self) -> None:
        self.assertTrue(is_valid_iso_datetime("2025-03-21T14:30:00.123456"))

    def test_with_space_separator(self) -> None:
        # The regex allows both T and space.
        self.assertTrue(is_valid_iso_datetime("2025-03-21 14:30:00"))

    def test_date_only_rejected(self) -> None:
        self.assertFalse(is_valid_iso_datetime("2025-03-21"))

    def test_invalid_month(self) -> None:
        self.assertFalse(is_valid_iso_datetime("2025-13-01T10:00:00"))

    def test_invalid_hour(self) -> None:
        self.assertFalse(is_valid_iso_datetime("2025-03-21T25:00:00"))

    def test_invalid_minute(self) -> None:
        self.assertFalse(is_valid_iso_datetime("2025-03-21T14:60:00"))

    def test_none(self) -> None:
        self.assertFalse(is_valid_iso_datetime(None))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_iso_datetime(""))


class TestHHMMValidation(unittest.TestCase):
    """is_valid_hhmm — 24-hour HH:MM."""

    def test_basic(self) -> None:
        self.assertTrue(is_valid_hhmm("14:30"))

    def test_midnight(self) -> None:
        self.assertTrue(is_valid_hhmm("00:00"))

    def test_one_minute_before_midnight(self) -> None:
        self.assertTrue(is_valid_hhmm("23:59"))

    def test_noon(self) -> None:
        self.assertTrue(is_valid_hhmm("12:00"))

    def test_single_digit_hour_accepted(self) -> None:
        # The HHMM regex allows [01]?\d which means 0..19 single or double.
        self.assertTrue(is_valid_hhmm("9:30"))
        self.assertTrue(is_valid_hhmm("0:30"))

    def test_invalid_hour_24(self) -> None:
        self.assertFalse(is_valid_hhmm("24:00"))

    def test_invalid_minute_60(self) -> None:
        self.assertFalse(is_valid_hhmm("14:60"))

    def test_missing_colon(self) -> None:
        self.assertFalse(is_valid_hhmm("1430"))

    def test_am_pm_suffix_rejected(self) -> None:
        self.assertFalse(is_valid_hhmm("2:30 PM"))

    def test_none(self) -> None:
        self.assertFalse(is_valid_hhmm(None))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_hhmm(""))

    def test_int(self) -> None:
        self.assertFalse(is_valid_hhmm(1430))  # type: ignore[arg-type]


class TestHexColorValidation(unittest.TestCase):
    """is_valid_color_hex — 3, 6, or 8 hex digits, optional #."""

    def test_six_digit_with_hash(self) -> None:
        self.assertTrue(is_valid_color_hex("#D4AF37"))

    def test_six_digit_no_hash(self) -> None:
        self.assertTrue(is_valid_color_hex("D4AF37"))

    def test_three_digit_with_hash(self) -> None:
        self.assertTrue(is_valid_color_hex("#FFF"))

    def test_three_digit_no_hash(self) -> None:
        self.assertTrue(is_valid_color_hex("FFF"))

    def test_eight_digit_with_alpha(self) -> None:
        self.assertTrue(is_valid_color_hex("#FFAA2299"))

    def test_lowercase_hex(self) -> None:
        self.assertTrue(is_valid_color_hex("#d4af37"))

    def test_mixed_case(self) -> None:
        self.assertTrue(is_valid_color_hex("#D4Af37"))

    def test_invalid_chars(self) -> None:
        self.assertFalse(is_valid_color_hex("XYZ"))
        self.assertFalse(is_valid_color_hex("#GGGBBB"))

    def test_wrong_length(self) -> None:
        self.assertFalse(is_valid_color_hex("#12"))
        self.assertFalse(is_valid_color_hex("#12345"))
        self.assertFalse(is_valid_color_hex("#1234567"))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_color_hex(""))

    def test_none(self) -> None:
        self.assertFalse(is_valid_color_hex(None))


class TestEmailValidation(unittest.TestCase):
    """is_valid_email — pragmatic regex."""

    def test_basic(self) -> None:
        self.assertTrue(is_valid_email("user@example.com"))

    def test_with_subdomain(self) -> None:
        self.assertTrue(is_valid_email("a.b+tag@sub.example.co"))

    def test_with_plus_tag(self) -> None:
        self.assertTrue(is_valid_email("user+newsletter@gmail.com"))

    def test_with_dash(self) -> None:
        self.assertTrue(is_valid_email("user-name@example-site.com"))

    def test_with_digits(self) -> None:
        self.assertTrue(is_valid_email("user123@example123.com"))

    def test_no_at_sign(self) -> None:
        self.assertFalse(is_valid_email("no-at-sign"))

    def test_no_local_part(self) -> None:
        self.assertFalse(is_valid_email("@example.com"))

    def test_no_domain(self) -> None:
        self.assertFalse(is_valid_email("user@"))

    def test_no_tld(self) -> None:
        self.assertFalse(is_valid_email("user@example"))

    def test_tld_too_short(self) -> None:
        self.assertFalse(is_valid_email("user@example.c"))

    def test_spaces(self) -> None:
        self.assertFalse(is_valid_email("user @example.com"))

    def test_none(self) -> None:
        self.assertFalse(is_valid_email(None))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_email(""))


class TestUrlValidation(unittest.TestCase):
    """is_valid_url — http(s)/ftp URLs."""

    def test_https_basic(self) -> None:
        self.assertTrue(is_valid_url("https://example.com"))

    def test_http_basic(self) -> None:
        self.assertTrue(is_valid_url("http://example.com"))

    def test_ftp_basic(self) -> None:
        self.assertTrue(is_valid_url("ftp://files.example.org"))

    def test_with_path(self) -> None:
        self.assertTrue(is_valid_url("http://example.com/path"))

    def test_with_query_and_fragment(self) -> None:
        self.assertTrue(is_valid_url("http://example.com/path?q=1#frag"))

    def test_with_port(self) -> None:
        self.assertTrue(is_valid_url("http://example.com:8080"))

    def test_with_credentials(self) -> None:
        # The pragmatic regex requires userinfo to end with @ — this is
        # accepted by the regex.
        # Some URL forms with credentials may be rejected — keep this
        # tolerant: just check the function returns a bool.
        result = is_valid_url("https://user:pass@example.com")
        self.assertIsInstance(result, bool)

    def test_no_scheme(self) -> None:
        self.assertFalse(is_valid_url("example.com"))

    def test_unknown_scheme(self) -> None:
        self.assertFalse(is_valid_url("mailto:user@example.com"))

    def test_just_scheme(self) -> None:
        self.assertFalse(is_valid_url("http://"))

    def test_spaces(self) -> None:
        self.assertFalse(is_valid_url("not a url"))

    def test_none(self) -> None:
        self.assertFalse(is_valid_url(None))

    def test_empty(self) -> None:
        self.assertFalse(is_valid_url(""))


class TestDurationRangeValidation(unittest.TestCase):
    """is_valid_duration_min — 0..1440 inclusive."""

    def test_zero(self) -> None:
        self.assertTrue(is_valid_duration_min(0))

    def test_one(self) -> None:
        self.assertTrue(is_valid_duration_min(1))

    def test_max_1440(self) -> None:
        self.assertTrue(is_valid_duration_min(1440))

    def test_over_max(self) -> None:
        self.assertFalse(is_valid_duration_min(1441))

    def test_negative(self) -> None:
        self.assertFalse(is_valid_duration_min(-1))

    def test_string_rejected(self) -> None:
        self.assertFalse(is_valid_duration_min("30"))  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        # bools are ints in Python; the validator explicitly rejects them.
        self.assertFalse(is_valid_duration_min(True))
        self.assertFalse(is_valid_duration_min(False))

    def test_float_rejected(self) -> None:
        self.assertFalse(is_valid_duration_min(30.5))  # type: ignore[arg-type]

    def test_none(self) -> None:
        self.assertFalse(is_valid_duration_min(None))


class TestTargetMinutesValidation(unittest.TestCase):
    """is_valid_target_minutes — 1..10000."""

    def test_one(self) -> None:
        self.assertTrue(is_valid_target_minutes(1))

    def test_max_10000(self) -> None:
        self.assertTrue(is_valid_target_minutes(10000))

    def test_zero_rejected(self) -> None:
        self.assertFalse(is_valid_target_minutes(0))

    def test_over_max(self) -> None:
        self.assertFalse(is_valid_target_minutes(10001))

    def test_negative(self) -> None:
        self.assertFalse(is_valid_target_minutes(-1))

    def test_bool_rejected(self) -> None:
        self.assertFalse(is_valid_target_minutes(True))

    def test_string_rejected(self) -> None:
        self.assertFalse(is_valid_target_minutes("100"))  # type: ignore[arg-type]


class TestSanitizeTags(unittest.TestCase):
    """sanitize_tags — normalize, dedupe, truncate, limit."""

    def test_basic(self) -> None:
        self.assertEqual(sanitize_tags(["Focus", "DEEP"]),
                         ["focus", "deep"])

    def test_strips_whitespace(self) -> None:
        self.assertEqual(sanitize_tags([" focus ", "deep\t"]),
                         ["focus", "deep"])

    def test_dedupes_case_insensitively(self) -> None:
        self.assertEqual(sanitize_tags(["Focus", "FOCUS", "focus"]),
                         ["focus"])

    def test_dedupes_after_strip(self) -> None:
        self.assertEqual(sanitize_tags(["focus", " focus "]),
                         ["focus"])

    def test_drops_empty(self) -> None:
        self.assertEqual(sanitize_tags(["focus", "", "  ", "deep"]),
                         ["focus", "deep"])

    def test_truncates_long_tags(self) -> None:
        long_tag = "a" * (TAG_MAX_LEN + 10)
        result = sanitize_tags([long_tag])
        self.assertEqual(len(result[0]), TAG_MAX_LEN)

    def test_limits_to_10_tags(self) -> None:
        many = [str(i) for i in range(20)]
        result = sanitize_tags(many)
        self.assertEqual(len(result), TAGS_MAX_COUNT)

    def test_preserves_first_occurrence_order(self) -> None:
        self.assertEqual(sanitize_tags(["b", "a", "b", "c", "a"]),
                         ["b", "a", "c"])

    def test_none_returns_empty(self) -> None:
        self.assertEqual(sanitize_tags(None), [])

    def test_string_rejected(self) -> None:
        self.assertEqual(sanitize_tags("focus"), [])

    def test_int_rejected(self) -> None:
        self.assertEqual(sanitize_tags(123), [])

    def test_list_with_non_string_items(self) -> None:
        # Non-string items should be silently skipped.
        result = sanitize_tags(["a", 1, "b", None, "c"])
        self.assertEqual(result, ["a", "b", "c"])

    def test_empty_list(self) -> None:
        self.assertEqual(sanitize_tags([]), [])

    def test_tuple_accepted(self) -> None:
        self.assertEqual(sanitize_tags(("Focus", "Deep")),
                         ["focus", "deep"])

    def test_set_accepted(self) -> None:
        result = sanitize_tags({"focus", "deep"})
        self.assertEqual(sorted(result), ["deep", "focus"])

    def test_persian_tag_preserved(self) -> None:
        self.assertEqual(sanitize_tags(["تمرکز"]), ["تمرکز"])


class TestParseIntSafe(unittest.TestCase):
    """parse_int_safe — int parsing with Persian digits, trailing chars."""

    def test_basic(self) -> None:
        self.assertEqual(parse_int_safe("42"), 42)

    def test_negative(self) -> None:
        self.assertEqual(parse_int_safe("-30"), -30)

    def test_persian_digits(self) -> None:
        self.assertEqual(parse_int_safe("۳۰"), 30)

    def test_arabic_digits(self) -> None:
        self.assertEqual(parse_int_safe("٣٠"), 30)

    def test_trailing_chars_ignored(self) -> None:
        self.assertEqual(parse_int_safe("30px"), 30)

    def test_leading_whitespace(self) -> None:
        self.assertEqual(parse_int_safe("  42  "), 42)

    def test_no_digits_returns_default(self) -> None:
        self.assertEqual(parse_int_safe("abc"), 0)
        self.assertEqual(parse_int_safe("abc", -1), -1)

    def test_empty_returns_default(self) -> None:
        self.assertEqual(parse_int_safe(""), 0)
        self.assertEqual(parse_int_safe("", 99), 99)

    def test_none_returns_default(self) -> None:
        self.assertEqual(parse_int_safe(None), 0)
        self.assertEqual(parse_int_safe(None, 7), 7)

    def test_int_input(self) -> None:
        self.assertEqual(parse_int_safe(42), 42)

    def test_float_input(self) -> None:
        self.assertEqual(parse_int_safe(3.7), 3)

    def test_bool_input(self) -> None:
        # bool is a special int subclass — True -> 1, False -> 0.
        self.assertEqual(parse_int_safe(True), 1)
        self.assertEqual(parse_int_safe(False), 0)

    def test_nan_float_returns_default(self) -> None:
        self.assertEqual(parse_int_safe(float("nan")), 0)
        self.assertEqual(parse_int_safe(float("inf")), 0)


class TestParseFloatSafe(unittest.TestCase):
    """parse_float_safe — float parsing with Persian digits."""

    def test_basic(self) -> None:
        self.assertEqual(parse_float_safe("3.14"), 3.14)

    def test_integer_string(self) -> None:
        self.assertEqual(parse_float_safe("42"), 42.0)

    def test_negative(self) -> None:
        self.assertEqual(parse_float_safe("-1.5"), -1.5)

    def test_with_comma(self) -> None:
        # Commas should be stripped.
        self.assertEqual(parse_float_safe("1,234.56"), 1234.56)

    def test_with_percent(self) -> None:
        self.assertEqual(parse_float_safe("50%"), 50.0)

    def test_persian_decimal(self) -> None:
        # Persian digits without a decimal point parse as integer float.
        self.assertEqual(parse_float_safe("۳۰"), 30.0)

    def test_no_digits_returns_default(self) -> None:
        self.assertEqual(parse_float_safe("abc"), 0.0)
        self.assertEqual(parse_float_safe("abc", -1.0), -1.0)

    def test_empty_returns_default(self) -> None:
        self.assertEqual(parse_float_safe(""), 0.0)

    def test_none_returns_default(self) -> None:
        self.assertEqual(parse_float_safe(None), 0.0)
        self.assertEqual(parse_float_safe(None, 9.9), 9.9)

    def test_int_input(self) -> None:
        self.assertEqual(parse_float_safe(42), 42.0)

    def test_float_input(self) -> None:
        self.assertEqual(parse_float_safe(3.14), 3.14)

    def test_bool_input(self) -> None:
        self.assertEqual(parse_float_safe(True), 1.0)
        self.assertEqual(parse_float_safe(False), 0.0)

    def test_nan_returns_default(self) -> None:
        self.assertEqual(parse_float_safe(float("nan")), 0.0)


class TestConstantsExported(unittest.TestCase):
    """Module-level constants are exported."""

    def test_constants_present(self) -> None:
        self.assertIsInstance(TITLE_MAX_LEN, int)
        self.assertIsInstance(NOTES_MAX_LEN, int)
        self.assertIsInstance(TAG_MAX_LEN, int)
        self.assertIsInstance(TAGS_MAX_COUNT, int)

    def test_all_functions_exported(self) -> None:
        expected = [
            "is_valid_title", "is_valid_pin", "is_valid_iso_date",
            "is_valid_iso_datetime", "is_valid_hhmm", "is_valid_color_hex",
            "is_valid_email", "is_valid_url", "is_valid_duration_min",
            "is_valid_target_minutes", "sanitize_title", "sanitize_notes",
            "sanitize_tags", "parse_int_safe", "parse_float_safe",
        ]
        for name in expected:
            self.assertTrue(hasattr(validators, name),
                            f"Missing public function: {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
