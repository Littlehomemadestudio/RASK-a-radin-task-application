"""
rask.tests.test_helpers
=======================

Unit tests for :mod:`rask.core.helpers`.

Covers:

  • Math: clamp, lerp
  • Easing functions: ease_out_cubic, ease_in_cubic, ease_in_out_cubic,
    ease_out_quint, ease_spring
  • Color: hex_to_rgb, rgb_to_hex, lighten_color, darken_color,
    mix_colors, hex_to_rgba
  • Strings: slugify, truncate, pluralize, format_file_size
  • Type coercion: safe_int, safe_float, safe_str
  • Collections: chunks, dedupe, merge_dicts, deep_get, deep_set
  • IDs / time: now_timestamp, uid, short_id
"""
from __future__ import annotations

import math
import unittest
from typing import List, Tuple

from rask.core import helpers
from rask.core.helpers import (
    chunks,
    clamp,
    darken_color,
    dedupe,
    deep_get,
    deep_set,
    ease_in_cubic,
    ease_in_out_cubic,
    ease_out_cubic,
    ease_out_quint,
    ease_spring,
    format_file_size,
    hex_to_rgb,
    hex_to_rgba,
    lighten_color,
    lerp,
    merge_dicts,
    mix_colors,
    now_timestamp,
    pluralize,
    rgb_to_hex,
    safe_float,
    safe_int,
    safe_str,
    short_id,
    slugify,
    truncate,
    uid,
)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestClamp(unittest.TestCase):
    """clamp(v, lo, hi) bounds v to [lo, hi]."""

    def test_value_in_range_unchanged(self) -> None:
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(5.5, 0.0, 10.0), 5.5)

    def test_below_lo_returns_lo(self) -> None:
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(-100, -5, 5), -5)

    def test_above_hi_returns_hi(self) -> None:
        self.assertEqual(clamp(99, 0, 10), 10)
        self.assertEqual(clamp(100, 0, 50), 50)

    def test_equal_lo_and_hi(self) -> None:
        self.assertEqual(clamp(5, 7, 7), 7)
        self.assertEqual(clamp(7, 7, 7), 7)

    def test_float_inputs(self) -> None:
        self.assertAlmostEqual(clamp(1.5, 0.0, 1.0), 1.0)
        self.assertAlmostEqual(clamp(-0.5, 0.0, 1.0), 0.0)


class TestLerp(unittest.TestCase):
    """lerp(a, b, t) — linear interpolation."""

    def test_t_zero_returns_a(self) -> None:
        self.assertEqual(lerp(0.0, 10.0, 0.0), 0.0)

    def test_t_one_returns_b(self) -> None:
        self.assertEqual(lerp(0.0, 10.0, 1.0), 10.0)

    def test_t_half_returns_midpoint(self) -> None:
        self.assertEqual(lerp(0.0, 10.0, 0.5), 5.0)

    def test_t_below_zero_clamped(self) -> None:
        # t < 0 should be clamped to 0.
        self.assertEqual(lerp(0.0, 10.0, -1.0), 0.0)

    def test_t_above_one_clamped(self) -> None:
        # t > 1 should be clamped to 1.
        self.assertEqual(lerp(0.0, 10.0, 2.0), 10.0)

    def test_negative_range(self) -> None:
        self.assertEqual(lerp(-10.0, 10.0, 0.5), 0.0)

    def test_decreasing_range(self) -> None:
        # lerp(10, 0, 0.5) = 5.
        self.assertEqual(lerp(10.0, 0.0, 0.5), 5.0)


class TestEasingFunctions(unittest.TestCase):
    """Easing curves all start at 0 and end at 1."""

    def test_ease_out_cubic_endpoints(self) -> None:
        self.assertEqual(ease_out_cubic(0.0), 0.0)
        self.assertEqual(ease_out_cubic(1.0), 1.0)

    def test_ease_out_cubic_monotonic(self) -> None:
        # The curve should be monotonically increasing.
        prev = -1
        for i in range(11):
            t = i / 10
            v = ease_out_cubic(t)
            self.assertGreaterEqual(v, prev)
            prev = v

    def test_ease_in_cubic_endpoints(self) -> None:
        self.assertEqual(ease_in_cubic(0.0), 0.0)
        self.assertEqual(ease_in_cubic(1.0), 1.0)

    def test_ease_in_cubic_at_quarter(self) -> None:
        # ease_in_cubic(0.25) = 0.015625
        self.assertAlmostEqual(ease_in_cubic(0.25), 0.015625)

    def test_ease_in_out_cubic_endpoints(self) -> None:
        self.assertEqual(ease_in_out_cubic(0.0), 0.0)
        self.assertEqual(ease_in_out_cubic(1.0), 1.0)

    def test_ease_in_out_cubic_midpoint(self) -> None:
        self.assertAlmostEqual(ease_in_out_cubic(0.5), 0.5)

    def test_ease_out_quint_endpoints(self) -> None:
        self.assertEqual(ease_out_quint(0.0), 0.0)
        self.assertEqual(ease_out_quint(1.0), 1.0)

    def test_ease_out_quint_above_cubic_at_quarter(self) -> None:
        # At t=0.25, ease_out_quint = 1 - 0.75^5 ≈ 0.763
        # ease_out_cubic = 1 - 0.75^3 ≈ 0.578
        # So quint > cubic at small t (steeper exit curve).
        self.assertGreater(ease_out_quint(0.25), ease_out_cubic(0.25))

    def test_ease_spring_endpoints(self) -> None:
        self.assertEqual(ease_spring(0.0), 0.0)
        self.assertEqual(ease_spring(1.0), 1.0)

    def test_ease_spring_may_overshoot(self) -> None:
        # The spring easing can momentarily exceed 1.0 in the middle.
        # Just check that it stays within a reasonable range.
        for i in range(11):
            t = i / 10
            v = ease_spring(t)
            self.assertGreaterEqual(v, -0.5)
            self.assertLessEqual(v, 1.5)

    def test_all_easings_clamp_input(self) -> None:
        # Values outside [0, 1] should be clamped.
        for fn in (ease_out_cubic, ease_in_cubic,
                   ease_in_out_cubic, ease_out_quint, ease_spring):
            self.assertEqual(fn(-0.5), fn(0.0))
            self.assertEqual(fn(1.5), fn(1.0))


class TestColorConversion(unittest.TestCase):
    """hex_to_rgb / rgb_to_hex."""

    def test_hex_to_rgb_six_digit(self) -> None:
        self.assertEqual(hex_to_rgb("#D4AF37"), (212, 175, 55))

    def test_hex_to_rgb_no_hash(self) -> None:
        self.assertEqual(hex_to_rgb("D4AF37"), (212, 175, 55))

    def test_hex_to_rgb_three_digit(self) -> None:
        # "FFF" expands to "FFFFFF" -> (255, 255, 255).
        self.assertEqual(hex_to_rgb("#FFF"), (255, 255, 255))

    def test_hex_to_rgb_eight_digit(self) -> None:
        # 8-digit form (with alpha) — alpha is ignored.
        self.assertEqual(hex_to_rgb("#FFAA2299"), (255, 170, 34))

    def test_hex_to_rgb_lowercase(self) -> None:
        self.assertEqual(hex_to_rgb("#d4af37"), (212, 175, 55))

    def test_hex_to_rgb_empty(self) -> None:
        self.assertEqual(hex_to_rgb(""), (0, 0, 0))

    def test_hex_to_rgb_none(self) -> None:
        self.assertEqual(hex_to_rgb(None), (0, 0, 0))  # type: ignore[arg-type]

    def test_hex_to_rgb_invalid(self) -> None:
        self.assertEqual(hex_to_rgb("#XYZ"), (0, 0, 0))
        self.assertEqual(hex_to_rgb("garbage"), (0, 0, 0))

    def test_rgb_to_hex_basic(self) -> None:
        self.assertEqual(rgb_to_hex((212, 175, 55)), "#d4af37")

    def test_rgb_to_hex_black(self) -> None:
        self.assertEqual(rgb_to_hex((0, 0, 0)), "#000000")

    def test_rgb_to_hex_white(self) -> None:
        self.assertEqual(rgb_to_hex((255, 255, 255)), "#ffffff")

    def test_rgb_to_hex_clamps_overflow(self) -> None:
        self.assertEqual(rgb_to_hex((300, -10, 128)), "#ff0080")

    def test_rgb_to_hex_list_input(self) -> None:
        # Should also accept a list.
        self.assertEqual(rgb_to_hex([0, 0, 0]), "#000000")

    def test_rgb_to_hex_invalid_input(self) -> None:
        self.assertEqual(rgb_to_hex(None), "#000000")  # type: ignore[arg-type]
        self.assertEqual(rgb_to_hex((1,)), "#000000")

    def test_round_trip(self) -> None:
        for r, g, b in [(0, 0, 0), (255, 255, 255), (212, 175, 55),
                        (128, 64, 32), (1, 2, 3)]:
            hex_str = rgb_to_hex((r, g, b))
            self.assertEqual(hex_to_rgb(hex_str), (r, g, b))


class TestLightenDarkenMix(unittest.TestCase):
    """lighten_color / darken_color / mix_colors / hex_to_rgba."""

    def test_lighten_black_to_white(self) -> None:
        self.assertEqual(lighten_color("#000000", 1.0), "#ffffff")

    def test_lighten_zero_returns_original(self) -> None:
        self.assertEqual(lighten_color("#808080", 0.0), "#808080")

    def test_lighten_half(self) -> None:
        self.assertEqual(lighten_color("#808080", 0.5), "#c0c0c0")

    def test_darken_white_to_black(self) -> None:
        self.assertEqual(darken_color("#ffffff", 1.0), "#000000")

    def test_darken_zero_returns_original(self) -> None:
        self.assertEqual(darken_color("#808080", 0.0), "#808080")

    def test_darken_half(self) -> None:
        self.assertEqual(darken_color("#808080", 0.5), "#404040")

    def test_mix_at_zero_returns_first(self) -> None:
        self.assertEqual(mix_colors("#000000", "#ffffff", 0.0), "#000000")

    def test_mix_at_one_returns_second(self) -> None:
        self.assertEqual(mix_colors("#000000", "#ffffff", 1.0), "#ffffff")

    def test_mix_at_half_returns_midpoint(self) -> None:
        self.assertEqual(mix_colors("#000000", "#ffffff", 0.5), "#808080")

    def test_hex_to_rgba_basic(self) -> None:
        self.assertEqual(hex_to_rgba("#D4AF37", 0.5),
                         "rgba(212, 175, 55, 0.5)")

    def test_hex_to_rgba_full_opacity(self) -> None:
        self.assertEqual(hex_to_rgba("#000000", 1.0),
                         "rgba(0, 0, 0, 1)")

    def test_hex_to_rgba_zero_opacity(self) -> None:
        self.assertEqual(hex_to_rgba("#000000", 0.0),
                         "rgba(0, 0, 0, 0)")

    def test_hex_to_rgba_clamps_alpha(self) -> None:
        # Alpha > 1 should be clamped to 1.
        self.assertEqual(hex_to_rgba("#000000", 2.0),
                         "rgba(0, 0, 0, 1)")
        # Alpha < 0 should be clamped to 0.
        self.assertEqual(hex_to_rgba("#000000", -1.0),
                         "rgba(0, 0, 0, 0)")


class TestSlugify(unittest.TestCase):
    """slugify produces URL-friendly slugs."""

    def test_basic(self) -> None:
        self.assertEqual(slugify("Hello World!"), "hello-world")

    def test_multiple_spaces(self) -> None:
        self.assertEqual(slugify("  Multiple   Spaces  "), "multiple-spaces")

    def test_punctuation_stripped(self) -> None:
        self.assertEqual(slugify("Rask — Time, Refined"), "rask-time-refined")

    def test_custom_separator(self) -> None:
        self.assertEqual(slugify("Hello World", "_"), "hello_world")

    def test_empty(self) -> None:
        self.assertEqual(slugify(""), "")

    def test_none(self) -> None:
        self.assertEqual(slugify(None), "")

    def test_integer(self) -> None:
        self.assertEqual(slugify(123), "")  # type: ignore[arg-type]

    def test_only_punctuation(self) -> None:
        self.assertEqual(slugify("!!!"), "")

    def test_strips_diacritics(self) -> None:
        # café -> cafe
        self.assertEqual(slugify("café"), "cafe")

    def test_uppercase_normalized(self) -> None:
        self.assertEqual(slugify("HELLO"), "hello")


class TestTruncate(unittest.TestCase):
    """truncate adds ellipsis if the string is too long."""

    def test_short_string_unchanged(self) -> None:
        self.assertEqual(truncate("Hi", 5), "Hi")

    def test_exact_length_unchanged(self) -> None:
        self.assertEqual(truncate("Hello", 5), "Hello")

    def test_long_string_truncated(self) -> None:
        result = truncate("Hello World", 5)
        self.assertEqual(result, "Hell…")
        self.assertEqual(len(result), 5)

    def test_custom_suffix(self) -> None:
        result = truncate("Hello World", 8, suffix="...")
        self.assertEqual(result, "Hello...")

    def test_empty_suffix(self) -> None:
        result = truncate("Hello World", 5, suffix="")
        self.assertEqual(result, "Hello")

    def test_none_returns_empty(self) -> None:
        self.assertEqual(truncate(None, 5), "")

    def test_non_string_returns_empty(self) -> None:
        self.assertEqual(truncate(12345, 3), "")  # type: ignore[arg-type]

    def test_negative_n_returns_empty(self) -> None:
        self.assertEqual(truncate("Hi", -1), "")

    def test_n_smaller_than_suffix(self) -> None:
        # n=2 with default "…" suffix (1 char) — should return "…" truncated.
        self.assertEqual(truncate("Hello", 2), "H…")

    def test_n_equal_suffix_length(self) -> None:
        self.assertEqual(truncate("Hello", 1), "…")


class TestPluralize(unittest.TestCase):
    """pluralize picks singular / plural based on count."""

    def test_singular(self) -> None:
        self.assertEqual(pluralize(1, "minute"), "1 minute")

    def test_plural_default(self) -> None:
        self.assertEqual(pluralize(5, "minute"), "5 minutes")

    def test_zero_is_plural(self) -> None:
        self.assertEqual(pluralize(0, "minute"), "0 minutes")

    def test_custom_plural(self) -> None:
        self.assertEqual(pluralize(2, "child", "children"),
                         "2 children")

    def test_custom_plural_singular(self) -> None:
        self.assertEqual(pluralize(1, "child", "children"),
                         "1 child")

    def test_negative_is_plural(self) -> None:
        self.assertEqual(pluralize(-1, "minute"), "-1 minutes")


class TestFormatFileSize(unittest.TestCase):
    """format_file_size — SI units, localized."""

    def test_zero_bytes_en(self) -> None:
        self.assertEqual(format_file_size(0, "en"), "0 B")

    def test_one_kb_en(self) -> None:
        self.assertEqual(format_file_size(1000, "en"), "1 KB")

    def test_1_5_kb_en(self) -> None:
        self.assertEqual(format_file_size(1500, "en"), "1.5 KB")

    def test_one_mb_en(self) -> None:
        self.assertEqual(format_file_size(1_000_000, "en"), "1 MB")

    def test_one_gb_en(self) -> None:
        self.assertEqual(format_file_size(1_000_000_000, "en"), "1 GB")

    def test_zero_bytes_fa(self) -> None:
        self.assertEqual(format_file_size(0, "fa"), "۰ بایت")

    def test_1_5_kb_fa(self) -> None:
        self.assertEqual(format_file_size(1500, "fa"), "۱.۵ کیلوبایت")

    def test_one_mb_fa(self) -> None:
        self.assertEqual(format_file_size(1_000_000, "fa"), "۱ مگابایت")

    def test_negative_returns_zero(self) -> None:
        self.assertEqual(format_file_size(-100, "en"), "0 B")

    def test_non_numeric_returns_zero(self) -> None:
        self.assertEqual(format_file_size("garbage", "en"), "0 B")  # type: ignore[arg-type]

    def test_large_value_tb(self) -> None:
        # 1 TB
        self.assertEqual(format_file_size(10**12, "en"), "1 TB")


class TestSafeInt(unittest.TestCase):
    """safe_int coercion."""

    def test_string_digit(self) -> None:
        self.assertEqual(safe_int("42"), 42)

    def test_persian_digits(self) -> None:
        self.assertEqual(safe_int("۳۰"), 30)

    def test_trailing_chars(self) -> None:
        self.assertEqual(safe_int("30px"), 30)

    def test_failure_returns_default(self) -> None:
        self.assertEqual(safe_int("abc"), 0)
        self.assertEqual(safe_int("abc", -1), -1)

    def test_none_returns_default(self) -> None:
        self.assertEqual(safe_int(None, 99), 99)

    def test_int_input(self) -> None:
        self.assertEqual(safe_int(42), 42)

    def test_float_input(self) -> None:
        self.assertEqual(safe_int(3.7), 3)

    def test_bool_input(self) -> None:
        self.assertEqual(safe_int(True), 1)
        self.assertEqual(safe_int(False), 0)


class TestSafeFloat(unittest.TestCase):
    """safe_float coercion."""

    def test_basic(self) -> None:
        self.assertEqual(safe_float("3.14"), 3.14)

    def test_percent(self) -> None:
        self.assertEqual(safe_float("50%"), 50.0)

    def test_failure_returns_default(self) -> None:
        self.assertEqual(safe_float("abc"), 0.0)
        self.assertEqual(safe_float("abc", -1.0), -1.0)

    def test_none_returns_default(self) -> None:
        self.assertEqual(safe_float(None, 9.9), 9.9)

    def test_int_input(self) -> None:
        self.assertEqual(safe_float(42), 42.0)

    def test_float_input(self) -> None:
        self.assertEqual(safe_float(3.14), 3.14)


class TestSafeStr(unittest.TestCase):
    """safe_str coercion."""

    def test_string_passthrough(self) -> None:
        self.assertEqual(safe_str("hello"), "hello")

    def test_int_to_str(self) -> None:
        self.assertEqual(safe_str(42), "42")

    def test_none_default_empty(self) -> None:
        self.assertEqual(safe_str(None), "")

    def test_none_custom_default(self) -> None:
        self.assertEqual(safe_str(None, "n/a"), "n/a")

    def test_list_to_str(self) -> None:
        # str(list) — let Python decide the format.
        result = safe_str([1, 2, 3])
        self.assertIsInstance(result, str)
        self.assertIn("1", result)


class TestChunks(unittest.TestCase):
    """chunks(lst, n) yields n-sized chunks."""

    def test_basic(self) -> None:
        result = list(chunks([1, 2, 3, 4, 5], 2))
        self.assertEqual(result, [[1, 2], [3, 4], [5]])

    def test_even_split(self) -> None:
        result = list(chunks([1, 2, 3, 4], 2))
        self.assertEqual(result, [[1, 2], [3, 4]])

    def test_empty_list(self) -> None:
        result = list(chunks([], 3))
        self.assertEqual(result, [])

    def test_chunk_size_larger_than_list(self) -> None:
        result = list(chunks([1, 2], 5))
        self.assertEqual(result, [[1, 2]])

    def test_chunk_size_one(self) -> None:
        result = list(chunks([1, 2, 3], 1))
        self.assertEqual(result, [[1], [2], [3]])

    def test_zero_chunk_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            list(chunks([1, 2], 0))

    def test_negative_chunk_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            list(chunks([1, 2], -1))

    def test_returns_lists_not_tuples(self) -> None:
        for chunk in chunks([1, 2, 3], 2):
            self.assertIsInstance(chunk, list)


class TestDedupe(unittest.TestCase):
    """dedupe preserves order, drops duplicates."""

    def test_ints(self) -> None:
        self.assertEqual(dedupe([1, 2, 2, 3, 1, 4]), [1, 2, 3, 4])

    def test_strings(self) -> None:
        self.assertEqual(dedupe(["a", "b", "a", "c"]),
                         ["a", "b", "c"])

    def test_empty(self) -> None:
        self.assertEqual(dedupe([]), [])

    def test_all_same(self) -> None:
        self.assertEqual(dedupe([1, 1, 1, 1]), [1])

    def test_preserves_first_occurrence(self) -> None:
        self.assertEqual(dedupe([3, 1, 2, 1, 3, 4]),
                         [3, 1, 2, 4])

    def test_unhashable_items(self) -> None:
        # Lists are unhashable — dedupe uses a set, which will fail.
        # But the function should still work for hashable items.
        with self.assertRaises(TypeError):
            dedupe([[1], [2], [1]])


class TestMergeDicts(unittest.TestCase):
    """merge_dicts shallow-merges multiple dicts."""

    def test_basic_merge(self) -> None:
        result = merge_dicts({"a": 1}, {"b": 2}, {"a": 3, "c": 4})
        self.assertEqual(result, {"a": 3, "b": 2, "c": 4})

    def test_with_none_entries(self) -> None:
        result = merge_dicts(None, {"x": 1}, None)
        self.assertEqual(result, {"x": 1})

    def test_all_none(self) -> None:
        self.assertEqual(merge_dicts(None, None, None), {})

    def test_empty(self) -> None:
        self.assertEqual(merge_dicts(), {})

    def test_single_dict(self) -> None:
        self.assertEqual(merge_dicts({"a": 1}), {"a": 1})

    def test_later_overrides_earlier(self) -> None:
        result = merge_dicts({"a": 1}, {"a": 2}, {"a": 3})
        self.assertEqual(result, {"a": 3})


class TestDeepGetSet(unittest.TestCase):
    """deep_get / deep_set traverse dotted paths."""

    def test_deep_get_hit(self) -> None:
        d = {"a": {"b": {"c": 42}}}
        self.assertEqual(deep_get(d, "a.b.c"), 42)

    def test_deep_get_miss_returns_default(self) -> None:
        d = {"a": {}}
        self.assertEqual(deep_get(d, "a.b.c", "default"), "default")

    def test_deep_get_missing_root_key(self) -> None:
        self.assertIsNone(deep_get({}, "a.b"))
        self.assertEqual(deep_get({}, "a.b", "fallback"), "fallback")

    def test_deep_get_none_input(self) -> None:
        self.assertIsNone(deep_get(None, "a.b"))

    def test_deep_get_empty_path_returns_default(self) -> None:
        self.assertIsNone(deep_get({"a": 1}, ""))

    def test_deep_get_non_dict_intermediate(self) -> None:
        # Path traverses through a non-dict — should return default.
        d = {"a": "string"}
        self.assertIsNone(deep_get(d, "a.b"))

    def test_deep_set_basic(self) -> None:
        d: dict = {}
        result = deep_set(d, "a.b.c", 42)
        self.assertEqual(result, {"a": {"b": {"c": 42}}})

    def test_deep_set_returns_same_dict(self) -> None:
        d: dict = {}
        result = deep_set(d, "a.b", 1)
        self.assertIs(result, d)

    def test_deep_set_overwrites_existing(self) -> None:
        d: dict = {"a": {"b": 1}}
        deep_set(d, "a.b", 2)
        self.assertEqual(d["a"]["b"], 2)

    def test_deep_set_creates_intermediate_dicts(self) -> None:
        d: dict = {"x": 1}
        deep_set(d, "a.b.c", 99)
        self.assertEqual(d["a"]["b"]["c"], 99)
        self.assertEqual(d["x"], 1)  # original key preserved

    def test_deep_set_non_dict_raises(self) -> None:
        with self.assertRaises(TypeError):
            deep_set("not-a-dict", "a.b", 1)  # type: ignore[arg-type]

    def test_deep_set_empty_path_noop(self) -> None:
        d: dict = {"x": 1}
        result = deep_set(d, "", 99)
        self.assertEqual(result, {"x": 1})


class TestNowTimestamp(unittest.TestCase):
    """now_timestamp returns Unix time in milliseconds."""

    def test_returns_int(self) -> None:
        self.assertIsInstance(now_timestamp(), int)

    def test_reasonable_magnitude(self) -> None:
        # Should be > year 2020 (1577836800 seconds = 1577836800000 ms).
        self.assertGreater(now_timestamp(), 1_577_836_800_000)

    def test_increases_over_time(self) -> None:
        t1 = now_timestamp()
        import time as _t
        _t.sleep(0.01)
        t2 = now_timestamp()
        self.assertGreater(t2, t1)


class TestUid(unittest.TestCase):
    """uid returns a 32-char hex UUID4 string."""

    def test_length(self) -> None:
        self.assertEqual(len(uid()), 32)

    def test_no_dashes(self) -> None:
        u = uid()
        self.assertNotIn("-", u)

    def test_is_hex(self) -> None:
        u = uid()
        self.assertTrue(all(c in "0123456789abcdef" for c in u))

    def test_two_uids_differ(self) -> None:
        u1 = uid()
        u2 = uid()
        self.assertNotEqual(u1, u2)

    def test_many_uids_unique(self) -> None:
        uids = {uid() for _ in range(100)}
        self.assertEqual(len(uids), 100)


class TestShortId(unittest.TestCase):
    """short_id returns a short base36 ID."""

    def test_default_length(self) -> None:
        self.assertEqual(len(short_id()), 8)

    def test_custom_length(self) -> None:
        self.assertEqual(len(short_id(12)), 12)
        self.assertEqual(len(short_id(20)), 20)

    def test_base36_alphabet(self) -> None:
        sid = short_id(50)
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
        self.assertTrue(all(c in alphabet for c in sid))

    def test_two_ids_differ(self) -> None:
        s1 = short_id()
        s2 = short_id()
        self.assertNotEqual(s1, s2)

    def test_many_ids_unique(self) -> None:
        ids = {short_id() for _ in range(200)}
        # Collision is astronomically unlikely.
        self.assertEqual(len(ids), 200)

    def test_zero_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            short_id(0)

    def test_negative_length_raises(self) -> None:
        with self.assertRaises(ValueError):
            short_id(-1)

    def test_length_one(self) -> None:
        sid = short_id(1)
        self.assertEqual(len(sid), 1)


class TestConstantsExported(unittest.TestCase):
    """All public names are exported."""

    def test_all_exports_present(self) -> None:
        expected = [
            "clamp", "lerp", "ease_out_cubic", "ease_in_cubic",
            "ease_in_out_cubic", "ease_out_quint", "ease_spring",
            "hex_to_rgb", "rgb_to_hex", "lighten_color", "darken_color",
            "mix_colors", "hex_to_rgba", "slugify", "truncate", "pluralize",
            "format_file_size", "safe_int", "safe_float", "safe_str",
            "chunks", "dedupe", "merge_dicts", "deep_get", "deep_set",
            "now_timestamp", "uid", "short_id",
        ]
        for name in expected:
            self.assertTrue(hasattr(helpers, name),
                            f"Missing public name: {name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
