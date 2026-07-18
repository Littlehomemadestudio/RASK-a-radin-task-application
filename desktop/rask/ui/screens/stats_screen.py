"""
rask.ui.screens.stats_screen
============================

Statistics & charts screen — date-range presets, summary cards,
bar/donut/heatmap/line charts, insights, and CSV/PDF export.

Mirrors ``web/index.html`` ``#screen-stats`` and the corresponding
``renderStats`` function in ``web/js/app.js``, extended with the
``FilterSheet`` for category/tag/duration filtering.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"آمار"`` + export menu (PDF / CSV / PNG)
    2. **Date-range segmented control** — ``امروز / این هفته / این ماه /
       امسال / همه`` + ``"بازه دلخواه"`` button that opens a date picker
    3. **Summary cards row** — 4 cards:
            * total time
            * total activities
            * avg per day
            * longest streak
    4. **Comparison card** — vs previous period (with up/down arrow + %)
    5. **Filter chips** — categories, tags, min/max duration (opens
       ``FilterSheet``)
    6. **Bar chart** — by day of week (Sat-Fri, 7 bars)
    7. **Bar chart** — by hour of day (24 bars)
    8. **Donut chart** — by category (with legend)
    9. **Heatmap** — year-grid (53×7) showing daily activity intensity
    10. **Line chart** — trends over the period (per-day totals)
    11. **Insights section** — bullet list of human-readable insights

Auto-refresh
------------
Subscribes to ``activity.added`` / ``activity.updated`` /
``activity.deleted`` / ``language.changed`` / ``data.imported`` /
``data.cleared`` / ``settings.changed``.  Heavy stats computations
are debounced (120ms) and run on a background-friendly ``after()``
tick so the UI doesn't freeze.

While computing, a ``SkeletonList`` is shown as a loading placeholder.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus, time_utils, jalali, helpers
from ...services import stats_service, activity_service, settings_service
from ...services import export_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card, StatCard, SummaryCard
from ..widgets.badges import Chip, CategoryBadge
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.skeleton import Skeleton, SkeletonCard, SkeletonList
from ..widgets.charts import (
    BarChart, LineChart, DonutChart, Heatmap, Sparkline,
)
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toggles import SegmentedControl
from ..widgets.sheets import FilterSheet

__all__ = ["StatsScreen"]


# =============================================================================
# === Presets                                                                ===
# =============================================================================

PRESETS: List[Dict[str, Any]] = [
    {"key": "today", "label_fa": "امروز", "label_en": "Today", "days": 1},
    {"key": "week", "label_fa": "این هفته", "label_en": "This Week",
     "days": 7, "week": True},
    {"key": "month", "label_fa": "این ماه", "label_en": "This Month",
     "days": 30, "month": True},
    {"key": "year", "label_fa": "امسال", "label_en": "This Year",
     "days": 365, "year": True},
    {"key": "all", "label_fa": "همه", "label_en": "All Time",
     "days": 99999},
]


def _preset_label(p: Dict[str, Any], lang: str) -> str:
    return p["label_fa"] if lang == "fa" else p["label_en"]


def _preset_range(p: Dict[str, Any]) -> Tuple[str, str]:
    """Compute (date_from, date_to) for a preset."""
    today = time_utils.today_iso()
    if p["key"] == "today":
        return today, today
    if p.get("week"):
        return time_utils.start_of_week(today), time_utils.end_of_week(today)
    if p.get("month"):
        return time_utils.start_of_month(today), time_utils.end_of_month(today)
    if p.get("year"):
        return time_utils.start_of_year(today), time_utils.end_of_year(today)
    if p["key"] == "all":
        return time_utils.add_days(today, -365 * 5), today
    # Last N days
    return time_utils.add_days(today, -(p["days"] - 1)), today


# =============================================================================
# === StatsScreen                                                           ===
# =============================================================================

class StatsScreen(ctk.CTkFrame):
    """Statistics & charts screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_date_picker(on_select)``
            * ``open_filter_sheet(...)``
            * ``show_toast(message)``
            * ``show_export_dialog(...)``
    lang
        ``"fa"`` (default) or ``"en"``.
    initial_preset
        Initial preset key (default ``"week"``).
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        initial_preset: str = "week",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        # Active preset (or None for custom range)
        self._preset_key: str = (initial_preset
                                   if any(p["key"] == initial_preset
                                          for p in PRESETS)
                                   else "week")
        self._custom_range: Optional[Tuple[str, str]] = None
        # Active filters
        self._filters: Dict[str, Any] = {
            "categories": [],
            "tags": [],
            "min_duration": None,
            "max_duration": None,
        }
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._loading: bool = False
        self._build()
        self._subscribe_events()
        self.after(120, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the stats screen."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self,
            title=i18n.t("stats", self._lang),
            action_icon="dots",
            on_action=self._on_export_menu,
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_presets()
        self._build_summary_cards()
        self._build_comparison_card()
        self._build_filter_row()
        self._build_chart_cards()
        self._build_insights_section()

    def _build_presets(self) -> None:
        """Date-range segmented control + custom-range button."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # Horizontal scroll of preset chips
        chips_row = ctk.CTkScrollableFrame(
            section, fg_color="transparent", orientation="horizontal",
            height=40,
        )
        chips_row.grid(row=0, column=0, sticky="ew")
        chips_row.grid_columnconfigure(0, weight=1)
        self._preset_chips: Dict[str, ctk.CTkBaseClass] = {}
        for p in PRESETS:
            chip = Pill(
                chips_row, text=_preset_label(p, self._lang),
                selected=(p["key"] == self._preset_key),
                on_click=lambda key=p["key"]: self._on_preset(key),
                lang=self._lang, height=32,
            )
            chip.pack(side="right" if i18n.is_rtl(self._lang)
                       else "left", padx=4, pady=4)
            self._preset_chips[p["key"]] = chip
        # Custom range button
        custom_text = (i18n.t("customRange", self._lang)
                       if "customRange" in _keys()
                       else ("بازه دلخواه" if self._lang == "fa"
                              else "Custom range"))
        custom_btn = GhostButton(
            section, text=custom_text,
            command=self._on_custom_range,
            lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        )
        custom_btn.grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_summary_cards(self) -> None:
        """4 summary stat cards in a 2x2 grid (or 4x1 on wide windows)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM,
                                                   config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        section.grid_columnconfigure(1, weight=1)
        self._summary_cards: List[StatCard] = []
        labels = [
            (i18n.t("totalTime", self._lang) if "totalTime" in _keys()
              else ("زمان کل" if self._lang == "fa" else "Total time"),
             "—"),
            (i18n.t("totalActivities", self._lang)
              if "totalActivities" in _keys()
              else ("فعالیت‌ها" if self._lang == "fa"
                     else "Activities"), "—"),
            (i18n.t("avgPerDay", self._lang) if "avgPerDay" in _keys()
              else ("میانگین روزانه" if self._lang == "fa"
                     else "Avg / day"), "—"),
            (i18n.t("longestStreak", self._lang)
              if "longestStreak" in _keys()
              else ("طولانی‌ترین زنجیره" if self._lang == "fa"
                     else "Longest streak"), "—"),
        ]
        for i, (label, value) in enumerate(labels):
            row = i // 2
            col = i % 2
            card = StatCard(
                section, label=label, value=value, lang=self._lang,
                padding=config.SPACE_MD,
            )
            card.grid(row=row, column=col, sticky="nsew",
                       padx=(0 if col == 0 else 4, 4 if col == 0 else 0),
                       pady=(0 if row == 0 else 4, 4))
            self._summary_cards.append(card)

    def _build_comparison_card(self) -> None:
        """Comparison vs previous period."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._comparison_card = Card(section, lang=self._lang,
                                       padding=config.SPACE_LG)
        self._comparison_card.grid(row=0, column=0, sticky="ew")
        self._comparison_card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Title
        SectionTitle(
            self._comparison_card.content,
            text=(i18n.t("comparison", self._lang)
                  if "comparison" in _keys()
                  else ("مقایسه با دوره قبل" if self._lang == "fa"
                         else "vs previous period")),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Value
        self._comparison_value = ctk.CTkLabel(
            self._comparison_card.content, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._comparison_value.grid(row=1, column=0, sticky="ew",
                                       pady=(4, 0))
        # Subtitle
        self._comparison_sub = ctk.CTkLabel(
            self._comparison_card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._comparison_sub.grid(row=2, column=0, sticky="ew", pady=(2, 0))

    def _build_filter_row(self) -> None:
        """Filter chips row (categories + tags + custom)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # Filter chips strip
        self._filter_strip = ctk.CTkScrollableFrame(
            section, fg_color="transparent", orientation="horizontal",
            height=36,
        )
        self._filter_strip.grid(row=0, column=0, sticky="ew")
        self._filter_strip.grid_columnconfigure(0, weight=1)
        # Add-filter button
        add_filter_text = (i18n.t("addFilter", self._lang)
                           if "addFilter" in _keys()
                           else ("+ فیلتر" if self._lang == "fa"
                                  else "+ Filter"))
        self._add_filter_btn = Pill(
            self._filter_strip, text=add_filter_text,
            on_click=self._on_open_filters,
            lang=self._lang, height=32,
        )
        self._add_filter_btn.pack(side="right" if i18n.is_rtl(self._lang)
                                    else "left", padx=4, pady=2)

    def _build_chart_cards(self) -> None:
        """Bar / donut / heatmap / line chart cards."""
        # --- Bar chart: by weekday ---
        self._weekday_card = self._make_chart_card(
            self._next_row(),
            i18n.t("byDayOfWeek", self._lang) if "byDayOfWeek" in _keys()
            else ("بر اساس روز هفته" if self._lang == "fa"
                   else "By day of week"))
        self._weekday_chart = BarChart(
            self._weekday_card.content, data=[], width=460, height=160,
            lang=self._lang,
        )
        self._weekday_chart.grid(row=1, column=0, sticky="ew", padx=4,
                                   pady=4)
        # --- Bar chart: by hour ---
        self._hour_card = self._make_chart_card(
            self._next_row(),
            i18n.t("byHourOfDay", self._lang) if "byHourOfDay" in _keys()
            else ("بر اساس ساعت" if self._lang == "fa"
                   else "By hour of day"))
        self._hour_chart = BarChart(
            self._hour_card.content, data=[], width=460, height=120,
            lang=self._lang,
        )
        self._hour_chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        # --- Donut chart: by category ---
        self._category_card = self._make_chart_card(
            self._next_row(),
            i18n.t("byCategory", self._lang) if "byCategory" in _keys()
            else ("بر اساس دسته" if self._lang == "fa"
                   else "By category"))
        # Donut + legend side-by-side
        donut_row = ctk.CTkFrame(self._category_card.content,
                                   fg_color="transparent")
        donut_row.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        donut_row.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        self._donut_chart = DonutChart(
            donut_row, data=[], width=140, height=140,
            line_width=18, lang=self._lang,
        )
        self._donut_chart.grid(row=0, column=0 if rtl else 0,
                                 padx=8, pady=4)
        self._donut_legend = ctk.CTkFrame(donut_row, fg_color="transparent")
        self._donut_legend.grid(row=0, column=1, sticky="nsew",
                                  padx=8, pady=4)
        self._donut_legend.grid_columnconfigure(0, weight=1)
        # --- Heatmap ---
        self._heatmap_card = self._make_chart_card(
            self._next_row(),
            i18n.t("heatmap", self._lang) if "heatmap" in _keys()
            else ("نقشه فعالیت سالانه" if self._lang == "fa"
                   else "Year heatmap"))
        self._heatmap_card.content.grid_columnconfigure(0, weight=1)
        # Heatmap canvas
        self._heatmap = Heatmap(
            self._heatmap_card.content, year=date.today().year,
            data={}, cell_size=10, gap=2, lang=self._lang,
        )
        self._heatmap.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        # --- Line chart: trends ---
        self._trends_card = self._make_chart_card(
            self._next_row(),
            i18n.t("trends", self._lang) if "trends" in _keys()
            else ("روندها" if self._lang == "fa" else "Trends"))
        self._trends_chart = LineChart(
            self._trends_card.content, data=[], labels=[],
            width=460, height=160, area_fill=True, lang=self._lang,
        )
        self._trends_chart.grid(row=1, column=0, sticky="ew", padx=4,
                                  pady=4)

    def _make_chart_card(self, row: int, title: str) -> Card:
        """Helper: create a titled chart card at `row`."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_MD)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            card.content, text=title, lang=self._lang,
            size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        return card

    def _build_insights_section(self) -> None:
        """Insights bullet list section."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section,
            text=(i18n.t("insightsTitle", self._lang)
                  if "insightsTitle" in _keys()
                  else ("بینش‌ها" if self._lang == "fa" else "Insights")),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._insights_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._insights_frame.grid(row=1, column=0, sticky="ew")
        self._insights_frame.grid_columnconfigure(0, weight=1)
        self._empty_state: Optional[EmptyState] = None

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "activity.added", "activity.updated", "activity.deleted",
            "language.changed", "settings.changed",
            "data.imported", "data.cleared",
        ]
        for ev in events:
            try:
                bus.subscribe(ev, self._on_data_changed)
                self._subscriptions.append((ev, self._on_data_changed))
            except Exception:
                pass

    def _unsubscribe_events(self) -> None:
        bus = event_bus.bus
        for ev, cb in self._subscriptions:
            try:
                bus.unsubscribe(ev, cb)
            except Exception:
                pass
        self._subscriptions.clear()

    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(150, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render all sections with the latest data."""
        if self._loading:
            return
        self._loading = True
        try:
            date_from, date_to = self._current_range()
            # Compute summary
            self._render_summary(date_from, date_to)
            # Comparison
            self._render_comparison(date_from, date_to)
            # Charts
            self._render_weekday_chart(date_from, date_to)
            self._render_hour_chart(date_from, date_to)
            self._render_category_chart(date_from, date_to)
            self._render_heatmap()
            self._render_trends_chart(date_from, date_to)
            # Insights
            self._render_insights(date_from, date_to)
            # Filter chips
            self._render_filter_chips()
        except Exception:
            pass
        finally:
            self._loading = False

    def set_preset(self, key: str) -> None:
        """Switch the active preset (clears any custom range)."""
        if not any(p["key"] == key for p in PRESETS):
            return
        self._preset_key = key
        self._custom_range = None
        # Update chip selection
        for k, chip in self._preset_chips.items():
            try:
                chip.configure(selected=(k == key))
            except Exception:
                pass
        self.refresh()

    def set_custom_range(self, start: str, end: str) -> None:
        """Switch to a custom date range (clears preset selection)."""
        self._preset_key = ""
        self._custom_range = (start, end)
        for k, chip in self._preset_chips.items():
            try:
                chip.configure(selected=False)
            except Exception:
                pass
        self.refresh()

    # ------------------------------------------------------------------
    # Range + filters
    # ------------------------------------------------------------------
    def _current_range(self) -> Tuple[str, str]:
        if self._custom_range:
            return self._custom_range
        preset = next((p for p in PRESETS if p["key"] == self._preset_key),
                      PRESETS[1])
        return _preset_range(preset)

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------
    def _render_summary(self, date_from: str, date_to: str) -> None:
        try:
            s = stats_service.summary(date_from, date_to)
        except Exception:
            s = {}
        # Card 1: total time
        total_min = int(s.get("total_min", 0) or 0)
        try:
            self._summary_cards[0].set_value(
                time_utils.format_duration(total_min, lang=self._lang,
                                            short=True))
        except Exception:
            pass
        # Card 2: total activities
        total_act = int(s.get("total_activities", 0) or 0)
        act_str = (i18n.to_fa_digits(str(total_act))
                   if self._lang == "fa" else str(total_act))
        try:
            self._summary_cards[1].set_value(act_str)
        except Exception:
            pass
        # Card 3: avg per day
        avg = float(s.get("avg_per_day", 0.0) or 0.0)
        avg_str = (i18n.to_fa_digits(str(int(avg)))
                   if self._lang == "fa" else str(int(avg)))
        unit = "دقیقه" if self._lang == "fa" else "min"
        try:
            self._summary_cards[2].set_value(f"{avg_str} {unit}")
        except Exception:
            pass
        # Card 4: longest streak
        try:
            streak = stats_service.longest_streak_ever()
        except Exception:
            streak = 0
        streak_str = (i18n.to_fa_digits(str(streak))
                       if self._lang == "fa" else str(streak))
        days_word = i18n.t("days", self._lang)
        try:
            self._summary_cards[3].set_value(
                f"{streak_str} {days_word}" if streak else "—")
        except Exception:
            pass

    def _render_comparison(self, date_from: str, date_to: str) -> None:
        """Compute comparison vs the previous period of the same length."""
        try:
            days = time_utils.days_between(date_from, date_to) + 1
            prev_from = time_utils.add_days(date_from, -days)
            prev_to = time_utils.add_days(date_from, -1)
            comp = stats_service.comparison(
                (prev_from, prev_to), (date_from, date_to))
            pct = comp.get("percent_change")
            delta_min = comp.get("delta_min", 0) or 0
        except Exception:
            pct = None
            delta_min = 0
        if pct is None:
            value_text = "—"
            sub_text = ""
            color = config.TEXT_DIM
        else:
            pct_val = float(pct)
            pct_str = (i18n.to_fa_digits(f"{abs(pct_val):.0f}")
                        if self._lang == "fa"
                        else f"{abs(pct_val):.0f}%")
            sign = "▲" if pct_val > 0 else ("▼" if pct_val < 0 else "–")
            if pct_val > 5:
                word = ("افزایش" if self._lang == "fa" else "Increase")
                color = config.SUCCESS
            elif pct_val < -5:
                word = ("کاهش" if self._lang == "fa" else "Decrease")
                color = config.DANGER
            else:
                word = ("تثبیت" if self._lang == "fa" else "Stable")
                color = config.TEXT_DIM
            value_text = f"{sign} {pct_str}٪" if self._lang == "fa" else f"{sign} {pct_str}"
            sub_text = (f"{word} — {i18n.to_fa_digits(str(int(abs(delta_min))))} "
                         f"{'دقیقه' if self._lang == 'fa' else 'min'}"
                         if self._lang == "fa"
                         else f"{word} — {int(abs(delta_min))} min")
        try:
            self._comparison_value.configure(text=value_text, text_color=color)
            self._comparison_sub.configure(text=sub_text)
        except Exception:
            pass

    def _render_weekday_chart(self, date_from: str, date_to: str) -> None:
        """Bar chart of minutes per weekday (Sat-Fri)."""
        try:
            rows = stats_service.by_weekday(date_from, date_to)
        except Exception:
            rows = []
        # Sort by Saturday-first index (which the service already returns)
        # Map weekday index -> short Persian name
        from ...core.time_utils import weekday_name
        # Use a fixed reference week to get weekday names
        ref_dates = ["2025-03-22", "2025-03-23", "2025-03-24",
                     "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28"]
        data: List[Dict[str, Any]] = []
        for i, ref in enumerate(ref_dates):
            row = next((r for r in rows if r.get("weekday") == i), None)
            minutes = int(row.get("total_min", 0) if row else 0)
            try:
                label = weekday_name(ref, self._lang)[:2]
            except Exception:
                label = str(i)
            data.append({"label": label, "value": minutes,
                          "color": config.GOLD})
        try:
            self._weekday_chart.set_data(data)
        except Exception:
            pass

    def _render_hour_chart(self, date_from: str, date_to: str) -> None:
        """Bar chart of minutes per hour of day (24 bars)."""
        try:
            rows = stats_service.by_hour(date_from, date_to)
        except Exception:
            rows = []
        data: List[Dict[str, Any]] = []
        for h in range(24):
            row = next((r for r in rows if r.get("hour") == h), None)
            minutes = int(row.get("total_min", 0) if row else 0)
            label = (i18n.to_fa_digits(f"{h:02d}")
                      if self._lang == "fa" else f"{h:02d}")
            data.append({"label": label, "value": minutes,
                          "color": config.GOLD})
        try:
            self._hour_chart.set_data(data)
        except Exception:
            pass

    def _render_category_chart(self, date_from: str, date_to: str) -> None:
        """Donut chart of minutes per category + legend."""
        try:
            rows = stats_service.by_category(date_from, date_to)
        except Exception:
            rows = []
        # Limit to top 6 categories
        rows = rows[:6]
        data: List[Dict[str, Any]] = []
        for r in rows:
            name = (r.get("category_name_fa") if self._lang == "fa"
                     else r.get("category_name_en")) or "—"
            color = r.get("category_color") or config.GOLD
            minutes = int(r.get("total_min", 0) or 0)
            if minutes <= 0:
                continue
            data.append({"label": name, "value": minutes, "color": color})
        try:
            self._donut_chart.set_data(data)
        except Exception:
            pass
        # Rebuild legend
        for child in self._donut_legend.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        rtl = i18n.is_rtl(self._lang)
        total_min = sum(d["value"] for d in data) or 1
        for i, d in enumerate(data[:6]):
            row = ctk.CTkFrame(self._donut_legend, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)
            # Color swatch
            swatch = ctk.CTkFrame(row, width=10, height=10,
                                   fg_color=d["color"],
                                   corner_radius=config.RADIUS_SM)
            swatch.grid(row=0, column=0, padx=(0, 6),
                         sticky="e" if rtl else "w")
            # Name
            name_label = ctk.CTkLabel(
                row, text=d["label"],
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            )
            name_label.grid(row=0, column=1, sticky="ew")
            # Minutes
            pct = int(d["value"] / total_min * 100)
            min_str = (i18n.to_fa_digits(str(int(d["value"])))
                        if self._lang == "fa" else str(int(d["value"])))
            pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                        if self._lang == "fa" else f"{pct}%")
            ctk.CTkLabel(
                row, text=f"{min_str} · {pct_str}",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).grid(row=0, column=2, padx=(6, 0))

    def _render_heatmap(self) -> None:
        """Year-grid heatmap."""
        try:
            year = date.today().year
            rows = stats_service.heatmap_data(year)
            # Convert to {iso_date: total_min} dict (Heatmap widget
            # uses raw minutes — intensity is computed internally)
            data = {r["date_iso"]: int(r.get("total_min", 0) or 0)
                     for r in rows}
            self._heatmap._data = data
            self._heatmap._year = year
            self._heatmap.redraw()
        except Exception:
            pass

    def _render_trends_chart(self, date_from: str, date_to: str) -> None:
        """Line chart of per-day totals over the range."""
        try:
            rows = stats_service.by_day(date_from, date_to)
        except Exception:
            rows = []
        # Build single-series data
        series_values: List[float] = []
        labels: List[str] = []
        # Iterate through all days in the range to fill gaps
        try:
            days = time_utils.range_days(date_from, date_to)
        except Exception:
            days = [r.get("date_iso") for r in rows]
        # Map rows by date_iso
        row_map = {r.get("date_iso"): r for r in rows}
        for d_iso in days:
            row = row_map.get(d_iso)
            minutes = int(row.get("total_min", 0) if row else 0)
            series_values.append(float(minutes))
            # Short label (day-of-month in Persian digits)
            try:
                day_num = int(d_iso[8:10])
                label = (i18n.to_fa_digits(str(day_num))
                          if self._lang == "fa" else str(day_num))
            except Exception:
                label = ""
            labels.append(label)
        # Cap to last 30 points for readability
        if len(series_values) > 30:
            series_values = series_values[-30:]
            labels = labels[-30:]
        # Subsample labels so they don't overlap
        if len(labels) > 8:
            n = len(labels)
            step = max(1, n // 8)
            sparse_labels = []
            for i, l in enumerate(labels):
                sparse_labels.append(l if i % step == 0 else "")
            labels = sparse_labels
        data = [{"label": ("Total" if self._lang == "en" else "کل"),
                  "values": series_values, "color": config.GOLD}]
        try:
            self._trends_chart.set_data(data)
            # labels are passed at construction — we need to re-assign
            self._trends_chart._labels = labels
            self._trends_chart.redraw()
        except Exception:
            pass

    def _render_insights(self, date_from: str, date_to: str) -> None:
        """Render the bullet list of human-readable insights."""
        # Clear old
        for child in self._insights_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        try:
            insights = stats_service.insights(date_from, date_to)
        except Exception:
            insights = []
        if not insights:
            self._empty_state = EmptyState(
                self._insights_frame,
                icon="chart_bar",
                title=(i18n.t("emptyStats", self._lang)
                       if "emptyStats" in _keys()
                       else (i18n.t("noData", self._lang)
                             if "noData" in _keys()
                             else ("داده‌ای موجود نیست"
                                    if self._lang == "fa"
                                    else "No data yet"))),
                subtitle=("برای دیدن بینش‌ها، فعالیت‌هایی ثبت کن"
                          if self._lang == "fa"
                          else "Log some activities to see insights"),
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build bullet rows
        rtl = i18n.is_rtl(self._lang)
        for i, ins in enumerate(insights):
            row = ctk.CTkFrame(self._insights_frame, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(1, weight=1)
            # Bullet dot
            dot = ctk.CTkFrame(row, width=8, height=8,
                                fg_color=config.GOLD,
                                corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=0, padx=(0, 8),
                      sticky="e" if rtl else "w")
            # Text
            text = ins.get("text", "")
            kind = ins.get("kind", "")
            color = config.TEXT
            if kind.startswith("comparison"):
                color = config.GOLD
            elif kind == "streak":
                color = config.GOLD
            ctk.CTkLabel(
                row, text=text,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=color,
                anchor="e" if rtl else "w",
                justify="right" if rtl else "left",
                wraplength=420,
            ).grid(row=0, column=1, sticky="ew")

    def _render_filter_chips(self) -> None:
        """Render active filter chips (categories + tags + duration)."""
        # Clear existing chips (keep the + button)
        for child in self._filter_strip.winfo_children():
            if child is self._add_filter_btn:
                continue
            try:
                child.destroy()
            except Exception:
                pass
        rtl = i18n.is_rtl(self._lang)
        # Category chips
        for cat_id in self._filters.get("categories", []):
            try:
                cat = db.category_get(cat_id) if cat_id else None
                if not cat:
                    continue
                name = (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or "—"
                chip = Pill(
                    self._filter_strip, text=name, closable=True,
                    on_close=lambda cid=cat_id: self._remove_filter(
                        "categories", cid),
                    lang=self._lang, height=32,
                )
                chip.pack(side="right" if rtl else "left", padx=4, pady=2)
            except Exception:
                pass
        # Tag chips
        for tag in self._filters.get("tags", []):
            chip = Pill(
                self._filter_strip, text=f"#{tag}", closable=True,
                on_close=lambda t=tag: self._remove_filter("tags", t),
                lang=self._lang, height=32,
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=2)
        # Duration chips
        mind = self._filters.get("min_duration")
        maxd = self._filters.get("max_duration")
        if mind is not None or maxd is not None:
            label = (f"≥ {i18n.to_fa_digits(str(mind))} "
                      f"{'دقیقه' if self._lang == 'fa' else 'min'}"
                      if mind is not None else "")
            if maxd is not None:
                label += (f" ≤ {i18n.to_fa_digits(str(maxd))}"
                           f" {'دقیقه' if self._lang == 'fa' else 'min'}")
            chip = Pill(
                self._filter_strip, text=label.strip(), closable=True,
                on_close=lambda: self._clear_duration_filters(),
                lang=self._lang, height=32,
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=2)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def _on_preset(self, key: str) -> None:
        self.set_preset(key)

    def _on_custom_range(self) -> None:
        """Open the date picker for a custom range."""
        if self._app and hasattr(self._app, "open_date_picker"):
            try:
                self._app.open_date_picker(
                    on_select=lambda start, end: self.set_custom_range(
                        start, end))
                return
            except Exception:
                pass
        # Fallback: publish event
        try:
            event_bus.bus.publish("ui.date_picker_requested",
                                    {"on_select": self.set_custom_range})
        except Exception:
            pass

    def _on_open_filters(self) -> None:
        """Open the FilterSheet."""
        if self._app and hasattr(self._app, "open_filter_sheet"):
            try:
                self._app.open_filter_sheet(
                    initial=self._filters,
                    on_apply=self._apply_filters)
                return
            except Exception:
                pass
        try:
            sheet = FilterSheet(
                self, initial=self._filters, lang=self._lang,
                on_apply=self._apply_filters,
            )
            sheet.show()
        except Exception:
            pass

    def _apply_filters(self, filters: Dict[str, Any]) -> None:
        self._filters.update(filters)
        self.refresh()

    def _remove_filter(self, key: str, value: Any) -> None:
        try:
            self._filters[key].remove(value)
        except Exception:
            pass
        self._render_filter_chips()
        self.refresh()

    def _clear_duration_filters(self) -> None:
        self._filters["min_duration"] = None
        self._filters["max_duration"] = None
        self._render_filter_chips()
        self.refresh()

    def _on_export_menu(self) -> None:
        """Show the export menu (PDF / CSV / PNG)."""
        from ..widgets.sheets import ActionSheet
        date_from, date_to = self._current_range()
        actions = [
            ("PDF", "pdf", lambda: self._export("pdf", date_from, date_to)),
            ("CSV", "csv", lambda: self._export("csv", date_from, date_to)),
            ("PNG", "image", lambda: self._export("png", date_from, date_to)),
        ]
        try:
            sheet = ActionSheet(
                self,
                title=(i18n.t("export", self._lang) if "export" in _keys()
                        else ("خروجی بگیر" if self._lang == "fa"
                               else "Export")),
                actions=[(lbl, cb) for lbl, _, cb in actions],
                lang=self._lang,
            )
            sheet.show()
        except Exception:
            # Fallback: just trigger the PDF export directly
            self._export("pdf", date_from, date_to)

    def _export(self, kind: str, date_from: str, date_to: str) -> None:
        """Trigger an export via export_service."""
        try:
            if kind == "csv":
                result = export_service.export_csv(date_from, date_to)
            elif kind == "pdf":
                result = export_service.export_pdf(
                    date_from, date_to,
                    options={"lang": self._lang})
            elif kind == "png":
                result = export_service.export_png(self)
            else:
                return
            ok = bool(result.get("ok", False))
            path = result.get("path", "")
            if self._app and hasattr(self._app, "show_toast"):
                if ok:
                    msg = (f"{i18n.t('exportSuccess', self._lang) if 'exportSuccess' in _keys() else ('ذخیره شد' if self._lang == 'fa' else 'Saved')}: {path}")
                    self._app.show_toast(msg)
                else:
                    self._app.show_toast(
                        i18n.t("exportFailed", self._lang)
                        if "exportFailed" in _keys()
                        else ("خطا در خروجی" if self._lang == "fa"
                               else "Export failed"))
        except Exception as exc:
            if self._app and hasattr(self._app, "show_toast"):
                self._app.show_toast(f"Error: {exc}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        self._unsubscribe_events()
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        super().destroy()


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

class Pill(ctk.CTkFrame):
    """Quick inline pill chip used in the preset / filter strips.

    A small wrapper around the ``Chip`` widget that exposes a simpler
    ``selected`` / ``on_click`` / ``closable`` / ``on_close`` API for
    our use case.
    """

    def __init__(
        self,
        master: Any,
        text: str = "",
        selected: bool = False,
        on_click: Optional[Callable[[], Any]] = None,
        closable: bool = False,
        on_close: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        height: int = 32,
        **kwargs: Any,
    ) -> None:
        fg = config.GOLD if selected else config.CHARCOAL
        tc = config.MATTE_BLACK if selected else config.TEXT
        bc = config.GOLD if selected else config.SURFACE_HI
        kwargs.setdefault("fg_color", fg)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", height)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", bc)
        super().__init__(master, **kwargs)
        self._on_click = on_click
        self._on_close = on_close
        self._selected = selected
        self._lang = lang
        rtl = i18n.is_rtl(lang)
        label = ctk.CTkLabel(
            self, text=text,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="bold" if selected else "normal",
                                    lang=lang),
            text_color=tc, cursor="hand2",
        )
        label.pack(side="right" if rtl else "left", padx=10, pady=4)
        if closable:
            close_btn = ctk.CTkButton(
                self, text="✕", width=18, height=18,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                text_color=tc,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                command=lambda: self._on_close() if self._on_close else None,
                cursor="hand2",
            )
            close_btn.pack(side="left" if rtl else "right", padx=(0, 6))
        if on_click:
            try:
                self.bind("<Button-1>", lambda _e: on_click(), add="+")
                label.bind("<Button-1>", lambda _e: on_click(), add="+")
            except Exception:
                pass

    def configure(self, **kwargs: Any) -> Any:  # type: ignore[override]
        """Override to support the ``selected`` kwarg."""
        if "selected" in kwargs:
            sel = kwargs.pop("selected")
            self._selected = sel
            fg = config.GOLD if sel else config.CHARCOAL
            tc = config.MATTE_BLACK if sel else config.TEXT
            bc = config.GOLD if sel else config.SURFACE_HI
            super().configure(fg_color=fg, border_color=bc)
            # Update children (label + close button) colors
            for child in self.winfo_children():
                try:
                    child.configure(text_color=tc)
                except Exception:
                    pass
        return super().configure(**kwargs)


def _keys() -> List[str]:
    global _CACHED_KEYS
    if _CACHED_KEYS is None:
        try:
            _CACHED_KEYS = list(i18n.LOCALES.get("fa", {}).keys())
        except Exception:
            _CACHED_KEYS = []
    return _CACHED_KEYS


_CACHED_KEYS: Optional[List[str]] = None


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("StatsScreen module: presets + summary + 4 charts + insights + export.")
    print(f"  Presets: {[p['key'] for p in PRESETS]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
