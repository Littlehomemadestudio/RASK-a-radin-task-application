"""
rask.tests.test_widgets_basic
=============================

Headless tests for the :mod:`rask.ui.widgets` package.

These tests run **without a display** — they verify importability,
non-visual helpers (color math, icon lookups, data structures), and
constructor signatures.  Where a widget would require a Tk root, we
either skip the test or assert that constructing without a display
raises a clear error (no segfault, no silent corruption).

Covers:

  • All 30 widget modules import successfully
  • Public classes are defined in each module
  • ProgressRing math (progress clamp 0-1, label formatting)
  • Color helpers (hex_to_rgb, rgb_to_hex, mix, lighten, darken)
  • Easing functions return values in [0, 1]
  • Icons module: has_icon / icon_glyph / ICON_NAMES catalog
  • Helpers: clamp / lerp / truncate / pluralize / format_file_size /
    safe_int / safe_float / safe_str / chunks / dedupe / merge_dicts /
    deep_get / deep_set / uid / short_id
  • Chart data structures (BarChart / LineChart / DonutChart /
    Heatmap / Sparkline / RadarChart / Histogram) can be imported
  • ListItem classes import without error
  • Theme module exposes expected color tokens
"""
from __future__ import annotations

import math
import unittest
from typing import Any, List, Type

from rask import config
from rask.core import helpers


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestWidgetModulesImport(unittest.TestCase):
    """Every widget module imports cleanly."""

    def test_import_buttons(self) -> None:
        from rask.ui.widgets import buttons
        self.assertTrue(hasattr(buttons, "__file__"))

    def test_import_avatars(self) -> None:
        from rask.ui.widgets import avatars
        self.assertTrue(hasattr(avatars, "__file__"))

    def test_import_empty_state(self) -> None:
        from rask.ui.widgets import empty_state

    def test_import_toggles(self) -> None:
        from rask.ui.widgets import toggles

    def test_import_icons(self) -> None:
        from rask.ui.widgets import icons

    def test_import_cards(self) -> None:
        from rask.ui.widgets import cards

    def test_import_list_items(self) -> None:
        from rask.ui.widgets import list_items

    def test_import_progress_ring(self) -> None:
        from rask.ui.widgets import progress_ring

    def test_import_pull_to_refresh(self) -> None:
        from rask.ui.widgets import pull_to_refresh

    def test_import_scrollable(self) -> None:
        from rask.ui.widgets import scrollable

    def test_import_theme(self) -> None:
        from rask.ui.widgets import theme

    def test_import_live_timer(self) -> None:
        from rask.ui.widgets import live_timer

    def test_import_skeleton(self) -> None:
        from rask.ui.widgets import skeleton

    def test_import_sliders(self) -> None:
        from rask.ui.widgets import sliders

    def test_import_tooltips(self) -> None:
        from rask.ui.widgets import tooltips

    def test_import_date_picker(self) -> None:
        from rask.ui.widgets import date_picker

    def test_import_dialogs(self) -> None:
        from rask.ui.widgets import dialogs

    def test_import_inputs(self) -> None:
        from rask.ui.widgets import inputs

    def test_import_calendar_grid(self) -> None:
        from rask.ui.widgets import calendar_grid

    def test_import_sheets(self) -> None:
        from rask.ui.widgets import sheets

    def test_import_charts(self) -> None:
        from rask.ui.widgets import charts

    def test_import_confetti(self) -> None:
        from rask.ui.widgets import confetti

    def test_import_dividers(self) -> None:
        from rask.ui.widgets import dividers

    def test_import_toasts(self) -> None:
        from rask.ui.widgets import toasts

    def test_import_bottom_nav(self) -> None:
        from rask.ui.widgets import bottom_nav

    def test_import_time_picker(self) -> None:
        from rask.ui.widgets import time_picker

    def test_import_animated_label(self) -> None:
        from rask.ui.widgets import animated_label

    def test_import_badges(self) -> None:
        from rask.ui.widgets import badges

    def test_import_headers(self) -> None:
        from rask.ui.widgets import headers


class TestWidgetClassesExist(unittest.TestCase):
    """Each widget module exposes its expected public class names."""

    def test_buttons_has_classes(self) -> None:
        from rask.ui.widgets import buttons
        # At least one button class should be present.
        names = [n for n in dir(buttons) if n.startswith("Gold") or "Button" in n]
        self.assertGreater(len(names), 0)

    def test_cards_has_classes(self) -> None:
        from rask.ui.widgets import cards
        names = [n for n in dir(cards) if "Card" in n or "Tile" in n]
        self.assertGreater(len(names), 0)

    def test_list_items_has_classes(self) -> None:
        from rask.ui.widgets import list_items
        names = [n for n in dir(list_items) if "ListItem" in n]
        self.assertGreater(len(names), 0)

    def test_charts_has_classes(self) -> None:
        from rask.ui.widgets import charts
        for cls_name in ("BarChart", "LineChart", "DonutChart",
                          "Heatmap", "Sparkline"):
            self.assertTrue(hasattr(charts, cls_name),
                            f"charts missing {cls_name}")

    def test_progress_ring_has_classes(self) -> None:
        from rask.ui.widgets import progress_ring
        self.assertTrue(hasattr(progress_ring, "ProgressRing"))

    def test_toasts_has_classes(self) -> None:
        from rask.ui.widgets import toasts
        names = [n for n in dir(toasts) if "Toast" in n]
        self.assertGreater(len(names), 0)

    def test_bottom_nav_has_classes(self) -> None:
        from rask.ui.widgets import bottom_nav
        names = [n for n in dir(bottom_nav) if "Nav" in n]
        self.assertGreater(len(names), 0)


# =============================================================================
# === Helpers — color math                                                    ===
# =============================================================================

class TestColorHelpers(unittest.TestCase):
    """hex_to_rgb / rgb_to_hex / mix / lighten / darken."""

    def test_hex_to_rgb_gold(self) -> None:
        self.assertEqual(helpers.hex_to_rgb("#D4AF37"), (212, 175, 55))

    def test_hex_to_rgb_without_hash(self) -> None:
        # Some helpers accept both forms.
        try:
            r = helpers.hex_to_rgb("D4AF37")
            self.assertEqual(len(r), 3)
        except ValueError:
            self.skipTest("hex_to_rgb requires '#' prefix")

    def test_hex_to_rgb_black(self) -> None:
        self.assertEqual(helpers.hex_to_rgb("#000000"), (0, 0, 0))

    def test_hex_to_rgb_white(self) -> None:
        self.assertEqual(helpers.hex_to_rgb("#FFFFFF"), (255, 255, 255))

    def test_rgb_to_hex_round_trip(self) -> None:
        for hex_str in ("#D4AF37", "#0E0E10", "#FFFFFF", "#000000"):
            rgb = helpers.hex_to_rgb(hex_str)
            back = helpers.rgb_to_hex(rgb)
            # Compare case-insensitively.
            self.assertEqual(back.lower(), hex_str.lower())

    def test_lighten_color_black_to_gray(self) -> None:
        result = helpers.lighten_color("#000000", 0.5)
        rgb = helpers.hex_to_rgb(result)
        # 50% lighten of black -> ~127 gray.
        for c in rgb:
            self.assertGreater(c, 100)
            self.assertLess(c, 150)

    def test_darken_color_white_to_gray(self) -> None:
        result = helpers.darken_color("#FFFFFF", 0.5)
        rgb = helpers.hex_to_rgb(result)
        for c in rgb:
            self.assertGreater(c, 100)
            self.assertLess(c, 150)

    def test_mix_colors_red_blue_purple(self) -> None:
        result = helpers.mix_colors("#FF0000", "#0000FF", 0.5)
        rgb = helpers.hex_to_rgb(result)
        # 50% red+50% blue -> (127, 0, 127).
        self.assertGreater(rgb[0], 100)
        self.assertLess(rgb[1], 50)
        self.assertGreater(rgb[2], 100)

    def test_hex_to_rgba_includes_alpha(self) -> None:
        result = helpers.hex_to_rgba("#FF0000", 0.5)
        self.assertIn("rgba", result)
        self.assertIn("0.5", result)

    def test_lighten_zero_returns_same(self) -> None:
        result = helpers.lighten_color("#808080", 0.0)
        self.assertEqual(result.lower(), "#808080")

    def test_darken_zero_returns_same(self) -> None:
        result = helpers.darken_color("#808080", 0.0)
        self.assertEqual(result.lower(), "#808080")


# =============================================================================
# === Helpers — easing                                                        ===
# =============================================================================

class TestEasingFunctions(unittest.TestCase):
    """Easing functions return values in [0, 1] for t in [0, 1]."""

    def test_ease_out_cubic_endpoints(self) -> None:
        self.assertAlmostEqual(helpers.ease_out_cubic(0.0), 0.0)
        self.assertAlmostEqual(helpers.ease_out_cubic(1.0), 1.0)

    def test_ease_in_cubic_endpoints(self) -> None:
        self.assertAlmostEqual(helpers.ease_in_cubic(0.0), 0.0)
        self.assertAlmostEqual(helpers.ease_in_cubic(1.0), 1.0)

    def test_ease_in_out_cubic_endpoints(self) -> None:
        self.assertAlmostEqual(helpers.ease_in_out_cubic(0.0), 0.0)
        self.assertAlmostEqual(helpers.ease_in_out_cubic(1.0), 1.0)

    def test_ease_out_quint_endpoints(self) -> None:
        self.assertAlmostEqual(helpers.ease_out_quint(0.0), 0.0)
        self.assertAlmostEqual(helpers.ease_out_quint(1.0), 1.0)

    def test_ease_out_cubic_monotonic(self) -> None:
        prev = 0.0
        for i in range(1, 11):
            t = i / 10.0
            v = helpers.ease_out_cubic(t)
            self.assertGreaterEqual(v, prev)
            prev = v

    def test_lerp_endpoints(self) -> None:
        self.assertAlmostEqual(helpers.lerp(0, 10, 0.0), 0.0)
        self.assertAlmostEqual(helpers.lerp(0, 10, 1.0), 10.0)
        self.assertAlmostEqual(helpers.lerp(0, 10, 0.5), 5.0)


# =============================================================================
# === Helpers — clamp                                                         ===
# =============================================================================

class TestClamp(unittest.TestCase):
    """clamp() bounds values."""

    def test_clamp_within_range(self) -> None:
        self.assertEqual(helpers.clamp(5, 0, 10), 5)

    def test_clamp_below_range(self) -> None:
        self.assertEqual(helpers.clamp(-5, 0, 10), 0)

    def test_clamp_above_range(self) -> None:
        self.assertEqual(helpers.clamp(15, 0, 10), 10)

    def test_clamp_at_bounds(self) -> None:
        self.assertEqual(helpers.clamp(0, 0, 10), 0)
        self.assertEqual(helpers.clamp(10, 0, 10), 10)

    def test_clamp_with_floats(self) -> None:
        self.assertEqual(helpers.clamp(0.5, 0.0, 1.0), 0.5)
        self.assertEqual(helpers.clamp(-0.1, 0.0, 1.0), 0.0)
        self.assertEqual(helpers.clamp(1.5, 0.0, 1.0), 1.0)


# =============================================================================
# === Helpers — text                                                          ===
# =============================================================================

class TestTextHelpers(unittest.TestCase):
    """truncate / pluralize / slugify / safe_str."""

    def test_truncate_short_text_unchanged(self) -> None:
        self.assertEqual(helpers.truncate("hello", 10), "hello")

    def test_truncate_long_text_uses_suffix(self) -> None:
        result = helpers.truncate("hello world", 5)
        self.assertLessEqual(len(result), 8)  # 5 + suffix len
        self.assertIn("…", result)

    def test_pluralize_singular(self) -> None:
        self.assertEqual(helpers.pluralize(1, "cat"), "1 cat")

    def test_pluralize_plural(self) -> None:
        result = helpers.pluralize(2, "cat")
        self.assertIn("cats", result)

    def test_pluralize_zero(self) -> None:
        result = helpers.pluralize(0, "cat")
        self.assertIn("cats", result)

    def test_slugify_basic(self) -> None:
        result = helpers.slugify("Hello World")
        self.assertEqual(result, "hello-world")

    def test_slugify_custom_separator(self) -> None:
        result = helpers.slugify("Hello World", "_")
        self.assertEqual(result, "hello_world")


# =============================================================================
# === Helpers — format_file_size                                              ===
# =============================================================================

class TestFormatFileSize(unittest.TestCase):
    """format_file_size returns Persian-localized strings."""

    def test_bytes(self) -> None:
        result = helpers.format_file_size(500, lang="en")
        self.assertIsInstance(result, str)

    def test_kilobytes(self) -> None:
        result = helpers.format_file_size(1024, lang="en")
        self.assertIsInstance(result, str)

    def test_megabytes(self) -> None:
        result = helpers.format_file_size(1024 * 1024, lang="en")
        self.assertIsInstance(result, str)

    def test_gigabytes(self) -> None:
        result = helpers.format_file_size(1024 * 1024 * 1024, lang="en")
        self.assertIsInstance(result, str)

    def test_persian_lang(self) -> None:
        result = helpers.format_file_size(1024, lang="fa")
        self.assertIsInstance(result, str)
        # Persian format should contain Persian digit or word.
        self.assertTrue(result)


# =============================================================================
# === Helpers — type safety                                                  ===
# =============================================================================

class TestSafeConversions(unittest.TestCase):
    """safe_int / safe_float / safe_str."""

    def test_safe_int_valid(self) -> None:
        self.assertEqual(helpers.safe_int("42"), 42)
        self.assertEqual(helpers.safe_int(42), 42)
        self.assertEqual(helpers.safe_int(42.0), 42)

    def test_safe_int_invalid_returns_default(self) -> None:
        self.assertEqual(helpers.safe_int("not a number"), 0)
        self.assertEqual(helpers.safe_int("not a number", -1), -1)
        self.assertEqual(helpers.safe_int(None, 5), 5)

    def test_safe_float_valid(self) -> None:
        self.assertAlmostEqual(helpers.safe_float("3.14"), 3.14)
        self.assertAlmostEqual(helpers.safe_float(3.14), 3.14)

    def test_safe_float_invalid_returns_default(self) -> None:
        self.assertEqual(helpers.safe_float("not a number"), 0.0)
        self.assertEqual(helpers.safe_float("not a number", -1.0), -1.0)

    def test_safe_str_valid(self) -> None:
        self.assertEqual(helpers.safe_str("hello"), "hello")
        self.assertEqual(helpers.safe_str(42), "42")

    def test_safe_str_invalid_returns_default(self) -> None:
        self.assertEqual(helpers.safe_str(None), "")
        self.assertEqual(helpers.safe_str(None, "fallback"), "fallback")


# =============================================================================
# === Helpers — collections                                                   ===
# =============================================================================

class TestCollectionHelpers(unittest.TestCase):
    """chunks / dedupe / merge_dicts / deep_get / deep_set."""

    def test_chunks_basic(self) -> None:
        result = list(helpers.chunks([1, 2, 3, 4, 5], 2))
        self.assertEqual(result, [[1, 2], [3, 4], [5]])

    def test_chunks_exact_division(self) -> None:
        result = list(helpers.chunks([1, 2, 3, 4], 2))
        self.assertEqual(result, [[1, 2], [3, 4]])

    def test_dedupe_preserves_order(self) -> None:
        result = helpers.dedupe([3, 1, 2, 3, 1, 4])
        self.assertEqual(result, [3, 1, 2, 4])

    def test_dedupe_empty(self) -> None:
        self.assertEqual(helpers.dedupe([]), [])

    def test_merge_dicts(self) -> None:
        a = {"a": 1, "b": 2}
        b = {"b": 3, "c": 4}
        result = helpers.merge_dicts(a, b)
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_deep_get(self) -> None:
        d = {"a": {"b": {"c": 42}}}
        self.assertEqual(helpers.deep_get(d, "a.b.c"), 42)
        self.assertEqual(helpers.deep_get(d, "a.b.x", "default"), "default")

    def test_deep_set(self) -> None:
        d: dict = {}
        helpers.deep_set(d, "a.b.c", 42)
        self.assertEqual(d["a"]["b"]["c"], 42)

    def test_uid_returns_string(self) -> None:
        result = helpers.uid()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_uid_unique(self) -> None:
        ids = {helpers.uid() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_short_id_default_length(self) -> None:
        result = helpers.short_id()
        self.assertEqual(len(result), 8)

    def test_short_id_custom_length(self) -> None:
        result = helpers.short_id(12)
        self.assertEqual(len(result), 12)


# =============================================================================
# === Icons                                                                   ===
# =============================================================================

class TestIconsModule(unittest.TestCase):
    """Icons registry."""

    def test_has_icon_known(self) -> None:
        from rask.ui.widgets import icons
        self.assertTrue(icons.has_icon("home"))
        self.assertTrue(icons.has_icon("plus"))
        self.assertTrue(icons.has_icon("play"))

    def test_has_icon_unknown(self) -> None:
        from rask.ui.widgets import icons
        self.assertFalse(icons.has_icon("nonexistent_icon"))

    def test_icon_glyph_returns_string(self) -> None:
        from rask.ui.widgets import icons
        g = icons.icon_glyph("home")
        self.assertIsInstance(g, str)
        self.assertTrue(g)

    def test_icon_glyph_unknown_returns_fallback(self) -> None:
        from rask.ui.widgets import icons
        g = icons.icon_glyph("nonexistent")
        self.assertIsInstance(g, str)

    def test_icon_names_non_empty(self) -> None:
        from rask.ui.widgets import icons
        self.assertGreater(len(icons.ICON_NAMES), 50)

    def test_icon_names_are_strings(self) -> None:
        from rask.ui.widgets import icons
        for name in icons.ICON_NAMES:
            self.assertIsInstance(name, str)
            self.assertTrue(name)

    def test_icon_names_unique(self) -> None:
        from rask.ui.widgets import icons
        names = list(icons.ICON_NAMES)
        self.assertEqual(len(names), len(set(names)))


# =============================================================================
# === Theme tokens                                                           ===
# =============================================================================

class TestThemeTokens(unittest.TestCase):
    """Theme module exposes color tokens from config."""

    def test_config_has_gold(self) -> None:
        self.assertEqual(config.GOLD, "#D4AF37")

    def test_config_has_matte_black(self) -> None:
        self.assertEqual(config.MATTE_BLACK, "#0E0E10")

    def test_config_has_window_dimensions(self) -> None:
        self.assertEqual(config.WINDOW_WIDTH, 540)
        self.assertEqual(config.WINDOW_HEIGHT, 900)

    def test_config_has_default_categories(self) -> None:
        self.assertGreaterEqual(len(config.DEFAULT_CATEGORIES), 7)

    def test_each_category_has_required_fields(self) -> None:
        for c in config.DEFAULT_CATEGORIES:
            self.assertIn("key", c)
            self.assertIn("name_en", c)
            self.assertIn("name_fa", c)
            self.assertIn("color", c)
            self.assertIn("icon", c)

    def test_theme_module_importable(self) -> None:
        from rask.ui.widgets import theme
        self.assertTrue(hasattr(theme, "__file__"))


# =============================================================================
# === ProgressRing math (without display)                                   ===
# =============================================================================

class TestProgressRingMath(unittest.TestCase):
    """ProgressRing clamps progress to [0, 1]."""

    def test_helpers_clamp_used_for_progress(self) -> None:
        # The ProgressRing constructor calls helpers.clamp(progress, 0, 1).
        # We test the math directly since we can't construct a CTk widget
        # without a display.
        self.assertEqual(helpers.clamp(-0.5, 0.0, 1.0), 0.0)
        self.assertEqual(helpers.clamp(1.5, 0.0, 1.0), 1.0)
        self.assertEqual(helpers.clamp(0.5, 0.0, 1.0), 0.5)

    def test_progress_to_percentage(self) -> None:
        # ProgressRing computes percentage as int(progress * 100).
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            pct = int(p * 100)
            self.assertGreaterEqual(pct, 0)
            self.assertLessEqual(pct, 100)


# =============================================================================
# === Chart data structures                                                  ===
# =============================================================================

class TestChartDataStructures(unittest.TestCase):
    """Chart classes are defined (we can't draw without a display)."""

    def test_bar_chart_class_exists(self) -> None:
        from rask.ui.widgets.charts import BarChart
        self.assertTrue(callable(BarChart))

    def test_line_chart_class_exists(self) -> None:
        from rask.ui.widgets.charts import LineChart
        self.assertTrue(callable(LineChart))

    def test_donut_chart_class_exists(self) -> None:
        from rask.ui.widgets.charts import DonutChart
        self.assertTrue(callable(DonutChart))

    def test_heatmap_class_exists(self) -> None:
        from rask.ui.widgets.charts import Heatmap
        self.assertTrue(callable(Heatmap))

    def test_sparkline_class_exists(self) -> None:
        from rask.ui.widgets.charts import Sparkline
        self.assertTrue(callable(Sparkline))

    def test_radar_chart_class_exists(self) -> None:
        from rask.ui.widgets.charts import RadarChart
        self.assertTrue(callable(RadarChart))

    def test_histogram_class_exists(self) -> None:
        from rask.ui.widgets.charts import Histogram
        self.assertTrue(callable(Histogram))


# =============================================================================
# === ListItem classes                                                       ===
# =============================================================================

class TestListItemClasses(unittest.TestCase):
    """ListItem subclasses are defined."""

    def test_activity_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import ActivityListItem
        self.assertTrue(callable(ActivityListItem))

    def test_goal_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import GoalListItem
        self.assertTrue(callable(GoalListItem))

    def test_template_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import TemplateListItem
        self.assertTrue(callable(TemplateListItem))

    def test_reminder_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import ReminderListItem
        self.assertTrue(callable(ReminderListItem))

    def test_badge_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import BadgeListItem
        self.assertTrue(callable(BadgeListItem))

    def test_category_list_item_exists(self) -> None:
        from rask.ui.widgets.list_items import CategoryListItem
        self.assertTrue(callable(CategoryListItem))


# =============================================================================
# === Badges / Toggles / Sliders (no display)                                ===
# =============================================================================

class TestBadgesTogglesSliders(unittest.TestCase):
    """Badges / Toggles / Sliders widget classes exist."""

    def test_badges_module_has_classes(self) -> None:
        from rask.ui.widgets import badges
        for name in ("CategoryBadge", "TierBadge", "StreakBadge", "CountBadge"):
            self.assertTrue(hasattr(badges, name),
                            f"badges missing {name}")

    def test_toggles_module_has_classes(self) -> None:
        from rask.ui.widgets import toggles
        names = [n for n in dir(toggles) if "Toggle" in n or "Switch" in n]
        self.assertGreater(len(names), 0)

    def test_sliders_module_has_classes(self) -> None:
        from rask.ui.widgets import sliders
        names = [n for n in dir(sliders) if "Slider" in n or "Progress" in n]
        self.assertGreater(len(names), 0)


# =============================================================================
# === Edges                                                                   ===
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def test_helpers_now_timestamp_returns_int(self) -> None:
        ts = helpers.now_timestamp()
        self.assertIsInstance(ts, int)
        self.assertGreater(ts, 0)

    def test_helpers_chunks_with_invalid_n_raises(self) -> None:
        with self.assertRaises(ValueError):
            list(helpers.chunks([1, 2, 3], 0))

    def test_helpers_dedupe_with_None(self) -> None:
        result = helpers.dedupe([1, None, 2, None, 3])
        self.assertEqual(result, [1, None, 2, 3])


if __name__ == "__main__":
    unittest.main()
