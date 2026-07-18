"""
rask.ui.screens.insights_screen
===============================

Insights screen — personality-style analysis of the user's activity
patterns over the last 30 days, with charts and recommendations.

Distinct from :mod:`stats_screen` (which is purely descriptive): the
insights screen interprets the data and answers questions like
"are you a morning person?", "what's your best day?", "which goal
needs attention?".

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"بینش‌ها"``
    2. **Personality card** — large hero card with an icon, a
       "type" label (e.g. ``"سحرخیز"``, ``"شب‌بیدار"``, ``"متعادل"``)
       and a short description derived from the user's hourly
       distribution
    3. **Productivity score** — circular progress ring (0-100) with
       animated count-up + explanation breakdown
    4. **Best time of day** — bar chart of minutes per hour (peak
       highlighted gold)
    5. **Best day of week** — bar chart of minutes per weekday (peak
       highlighted gold)
    6. **Top categories** — ranked list with progress bars showing
       each category's share of total time
    7. **Streak analysis** — current vs best streak, with motivational
       message
    8. **Weekly comparison** — this week vs last week, day-by-day
       grouped bar chart
    9. **Goals overview** — which goals are on-track vs behind, with
       progress bars
    10. **Recommendations** — bullet list of tailored suggestions
        ("برای بهبود زنجیره‌ات، هر روز صبح ۱۵ دقیقه تمرکز کن")

Auto-refresh
------------
Subscribes to ``activity.added`` / ``activity.updated`` /
``activity.deleted`` / ``goal.added`` / ``goal.updated`` /
``goal.deleted`` / ``streak.incremented`` / ``language.changed`` /
``data.imported`` / ``data.cleared``.
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
from ...services import (
    stats_service, activity_service, goal_service, streak_service,
    settings_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.cards import Card, SummaryCard
from ..widgets.badges import Chip, StreakBadge
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.progress_ring import ProgressRing
from ..widgets.charts import BarChart, LineChart, DonutChart
from ..widgets.sliders import ProgressBar
from ..widgets.animated_label import CountUpLabel
from ..widgets.scrollable import SmoothScrollFrame

__all__ = ["InsightsScreen"]


# =============================================================================
# === Personality types                                                      ===
# =============================================================================

PERSONALITIES: List[Dict[str, Any]] = [
    {"key": "early_bird", "name_fa": "سحرخیز", "name_en": "Early Bird",
     "desc_fa": "صبح‌ها بیشترین تمرکز را داری. از انرژی صبحگاهی‌ات برای کارهای سخت استفاده کن.",
     "desc_en": "You're most focused in the mornings. Use that energy for hard work.",
     "icon": "sunrise", "color": config.GOLD,
     "peak_hours": (5, 11)},
    {"key": "day_owl", "name_fa": "متعادل", "name_en": "Balanced",
     "desc_fa": "در طول روز به‌طور یکنواخت فعالیت می‌کنی. الگوی متعادلی داری.",
     "desc_en": "You spread activity evenly through the day.",
     "icon": "sun", "color": config.GOLD_SOFT,
     "peak_hours": (10, 17)},
    {"key": "night_owl", "name_fa": "شب‌بیدار", "name_en": "Night Owl",
     "desc_fa": "شب‌ها بیشترین تمرکز را داری. مراقب خوابت باش — استراحت کافی مهم است.",
     "desc_en": "You're most focused at night. Watch your sleep — rest matters.",
     "icon": "moon", "color": config.INFO,
     "peak_hours": (20, 26)},  # 26 wraps to 2 AM next day
    {"key": "balanced", "name_fa": "همه‌فصل", "name_en": "All-Rounder",
     "desc_fa": "الگوی فعالیتت متنوع است. در همه ساعات روز فعال هستی.",
     "desc_en": "Your activity is varied across all hours.",
     "icon": "star", "color": config.GOLD_BRIGHT,
     "peak_hours": (6, 22)},
]


def _detect_personality(hour_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick a personality type from per-hour totals.

    ``hour_rows`` is a list of ``{hour: int, total_min: int}`` dicts.
    Returns the matching entry from :data:`PERSONALITIES`.
    """
    if not hour_rows:
        return PERSONALITIES[3]  # balanced / all-rounder
    # Sum minutes per personality's peak window
    best_score = -1
    best = PERSONALITIES[3]
    for p in PERSONALITIES:
        start, end = p["peak_hours"]
        score = 0
        for h in range(start, end):
            real_h = h % 24
            row = next((r for r in hour_rows
                         if r.get("hour") == real_h), None)
            if row:
                score += int(row.get("total_min", 0) or 0)
        if score > best_score:
            best_score = score
            best = p
    # If all personalities have 0 score, fall back to balanced
    if best_score <= 0:
        best = PERSONALITIES[3]
    return best


# =============================================================================
# === InsightsScreen                                                        ===
# =============================================================================

class InsightsScreen(ctk.CTkFrame):
    """Insights & analysis screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``switch_tab(tab)``
            * ``show_toast(message)``
            * ``open_goal_dialog(goal_id)``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        range_days: int = 30,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._range_days = max(7, int(range_days))
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._build()
        self._subscribe_events()
        self.after(120, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the insights screen."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self,
            title=(i18n.t("insightsTitle", self._lang)
                   if "insightsTitle" in _keys()
                   else ("بینش‌ها" if self._lang == "fa" else "Insights")),
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
        self._build_personality_card()
        self._build_productivity_card()
        self._build_best_time_card()
        self._build_best_day_card()
        self._build_top_categories_card()
        self._build_streak_card()
        self._build_weekly_comparison_card()
        self._build_goals_card()
        self._build_recommendations_card()

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_personality_card(self) -> None:
        """Hero personality card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._personality_card = Card(section, lang=self._lang,
                                        padding=config.SPACE_LG)
        self._personality_card.grid(row=0, column=0, sticky="ew")
        self._personality_card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Icon (leading side in RTL)
        self._personality_icon_label = ctk.CTkLabel(
            self._personality_card.content, text="", width=72, height=72,
            fg_color="transparent",
        )
        self._personality_icon_label.grid(row=0, column=0, rowspan=2,
                                            padx=4, sticky="nsew")
        # Info column (trailing side in RTL)
        info = ctk.CTkFrame(self._personality_card.content,
                              fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        # Subtitle
        ctk.CTkLabel(
            info, text=("شخصیت زمانی تو" if self._lang == "fa"
                         else "Your time personality"),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Name (large gold)
        self._personality_name = ctk.CTkLabel(
            info, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._personality_name.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Description
        self._personality_desc = ctk.CTkLabel(
            info, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
            wraplength=320,
        )
        self._personality_desc.grid(row=2, column=0, sticky="ew",
                                       pady=(4, 0))

    def _build_productivity_card(self) -> None:
        """Productivity score ring + breakdown."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            card.content,
            text=("امتیاز بهره‌وری" if self._lang == "fa"
                   else "Productivity score"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Ring + score
        score_row = ctk.CTkFrame(card.content, fg_color="transparent")
        score_row.grid(row=1, column=0, sticky="ew", pady=(config.SPACE_SM,
                                                              0))
        score_row.grid_columnconfigure(1, weight=1)
        self._prod_ring = ProgressRing(
            score_row, progress=0.0, size=96, line_width=8,
            show_percentage=False, animated=True, lang=self._lang,
            label="",
        )
        self._prod_ring.grid(row=0, column=0 if rtl else 0, padx=8,
                              pady=4)
        # Score number (animated count-up)
        self._prod_score_label = CountUpLabel(
            score_row, value=0, duration_ms=900,
            lang=self._lang, size=config.FONT_SIZE_HEADING_LG,
            color=config.GOLD,
        )
        self._prod_score_label.grid(row=0, column=1, sticky="nsew",
                                       padx=8)
        # Explanation
        self._prod_explain = ctk.CTkLabel(
            card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
            wraplength=380,
        )
        self._prod_explain.grid(row=2, column=0, sticky="ew",
                                  pady=(config.SPACE_SM, 0))

    def _build_best_time_card(self) -> None:
        """Best time of day chart."""
        self._best_time_card = self._make_card(
            self._next_row(),
            ("بهترین ساعت روز" if self._lang == "fa"
              else "Best time of day"))
        self._best_time_chart = BarChart(
            self._best_time_card.content, data=[], width=460, height=140,
            lang=self._lang,
        )
        self._best_time_chart.grid(row=1, column=0, sticky="ew",
                                     padx=4, pady=4)

    def _build_best_day_card(self) -> None:
        """Best day of week chart."""
        self._best_day_card = self._make_card(
            self._next_row(),
            ("بهترین روز هفته" if self._lang == "fa"
              else "Best day of week"))
        self._best_day_chart = BarChart(
            self._best_day_card.content, data=[], width=460, height=140,
            lang=self._lang,
        )
        self._best_day_chart.grid(row=1, column=0, sticky="ew",
                                    padx=4, pady=4)

    def _build_top_categories_card(self) -> None:
        """Top categories ranking with progress bars."""
        self._top_cats_card = self._make_card(
            self._next_row(),
            ("دسته‌های برتر" if self._lang == "fa" else "Top categories"))
        self._top_cats_frame = ctk.CTkFrame(self._top_cats_card.content,
                                              fg_color="transparent")
        self._top_cats_frame.grid(row=1, column=0, sticky="ew",
                                    padx=4, pady=4)
        self._top_cats_frame.grid_columnconfigure(0, weight=1)

    def _build_streak_card(self) -> None:
        """Streak analysis: current vs best + motivational text."""
        self._streak_card = self._make_card(
            self._next_row(),
            ("تحلیل زنجیره" if self._lang == "fa" else "Streak analysis"))
        # Two columns: current vs best
        cols_row = ctk.CTkFrame(self._streak_card.content,
                                  fg_color="transparent")
        cols_row.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        cols_row.grid_columnconfigure(0, weight=1)
        cols_row.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Current
        cur_col = 0 if rtl else 0
        cur_frame = ctk.CTkFrame(cols_row, fg_color="transparent")
        cur_frame.grid(row=0, column=cur_col, sticky="ew", padx=4)
        cur_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cur_frame, text=(i18n.t("currentStreak", self._lang)
                              if "currentStreak" in _keys()
                              else ("زنجیره فعلی" if self._lang == "fa"
                                     else "Current streak")),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="center",
        ).grid(row=0, column=0, sticky="ew")
        self._streak_current = CountUpLabel(
            cur_frame, value=0, duration_ms=800, lang=self._lang,
            size=config.FONT_SIZE_HEADING_LG, color=config.GOLD,
        )
        self._streak_current.grid(row=1, column=0, pady=(2, 0))
        # Best
        best_col = 1 if rtl else 1
        best_frame = ctk.CTkFrame(cols_row, fg_color="transparent")
        best_frame.grid(row=0, column=best_col, sticky="ew", padx=4)
        best_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            best_frame, text=(i18n.t("longestStreak", self._lang)
                              if "longestStreak" in _keys()
                              else ("بهترین زنجیره" if self._lang == "fa"
                                     else "Longest streak")),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="center",
        ).grid(row=0, column=0, sticky="ew")
        self._streak_best = CountUpLabel(
            best_frame, value=0, duration_ms=800, lang=self._lang,
            size=config.FONT_SIZE_HEADING_LG, color=config.GOLD,
        )
        self._streak_best.grid(row=1, column=0, pady=(2, 0))
        # Motivational message
        self._streak_msg = ctk.CTkLabel(
            self._streak_card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
            wraplength=380,
        )
        self._streak_msg.grid(row=2, column=0, sticky="ew",
                                pady=(config.SPACE_SM, 0))

    def _build_weekly_comparison_card(self) -> None:
        """Weekly comparison: this week vs last week, day by day."""
        self._weekly_card = self._make_card(
            self._next_row(),
            ("مقایسه هفتگی" if self._lang == "fa" else "Weekly comparison"))
        self._weekly_chart = BarChart(
            self._weekly_card.content, data=[], width=460, height=140,
            lang=self._lang,
        )
        self._weekly_chart.grid(row=1, column=0, sticky="ew",
                                  padx=4, pady=4)

    def _build_goals_card(self) -> None:
        """Goals overview: on-track vs behind."""
        self._goals_card = self._make_card(
            self._next_row(),
            ("وضعیت اهداف" if self._lang == "fa" else "Goals overview"))
        self._goals_frame = ctk.CTkFrame(self._goals_card.content,
                                            fg_color="transparent")
        self._goals_frame.grid(row=1, column=0, sticky="ew",
                                 padx=4, pady=4)
        self._goals_frame.grid_columnconfigure(0, weight=1)

    def _build_recommendations_card(self) -> None:
        """Recommendations bullet list."""
        self._recs_card = self._make_card(
            self._next_row(),
            ("پیشنهادات" if self._lang == "fa" else "Recommendations"))
        self._recs_frame = ctk.CTkFrame(self._recs_card.content,
                                          fg_color="transparent")
        self._recs_frame.grid(row=1, column=0, sticky="ew",
                                padx=4, pady=4)
        self._recs_frame.grid_columnconfigure(0, weight=1)

    def _make_card(self, row: int, title: str) -> Card:
        """Helper: create a titled card at `row`."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
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

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "activity.added", "activity.updated", "activity.deleted",
            "goal.added", "goal.updated", "goal.deleted",
            "streak.incremented", "streak.reset",
            "language.changed",
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
        try:
            today = time_utils.today_iso()
            start = time_utils.add_days(today, -(self._range_days - 1))
            self._render_personality(start, today)
            self._render_productivity(start, today)
            self._render_best_time(start, today)
            self._render_best_day(start, today)
            self._render_top_categories(start, today)
            self._render_streak()
            self._render_weekly_comparison()
            self._render_goals_overview()
            self._render_recommendations(start, today)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------
    def _render_personality(self, start: str, end: str) -> None:
        """Pick + render the personality card."""
        try:
            hour_rows = stats_service.by_hour(start, end)
        except Exception:
            hour_rows = []
        p = _detect_personality(hour_rows)
        name = p["name_fa"] if self._lang == "fa" else p["name_en"]
        desc = p["desc_fa"] if self._lang == "fa" else p["desc_en"]
        try:
            self._personality_name.configure(text=name, text_color=p["color"])
            self._personality_desc.configure(text=desc)
        except Exception:
            pass
        # Icon
        try:
            img = _icons.icon(p["icon"], 56, color=p["color"])
            if img is not None:
                self._personality_icon_label.configure(image=img, text="")
            else:
                self._personality_icon_label.configure(
                    text=_icons.icon_glyph(p["icon"]),
                    text_color=p["color"],
                    font=_theme.theme.font(size=56, weight="normal",
                                            lang="en"))
        except Exception:
            pass

    def _render_productivity(self, start: str, end: str) -> None:
        """Compute + render the productivity score (0-100).

        Score is a weighted blend of:
            * consistency (% of days with activity)  — 30%
            * goal hit rate                            — 30%
            * total time vs target                     — 20%
            * streak length                            — 20%
        """
        try:
            s = stats_service.summary(start, end)
        except Exception:
            s = {}
        total_days = max(1, time_utils.days_between(start, end) + 1)
        day_count = int(s.get("day_count", 0) or 0)
        consistency = day_count / total_days
        try:
            hit_rate = float(stats_service.goal_hit_rate(days=self._range_days)
                              or 0.0)
        except Exception:
            hit_rate = 0.0
        # Total time vs target (target = 2 hours/day × days)
        target_total = total_days * 120
        total_min = int(s.get("total_min", 0) or 0)
        time_score = min(1.0, total_min / max(1, target_total))
        # Streak length (current / 30 days)
        try:
            streak = int(stats_service.current_streak() or 0)
        except Exception:
            streak = 0
        streak_score = min(1.0, streak / 30.0)
        score = int(100 * (consistency * 0.30 + hit_rate * 0.30
                            + time_score * 0.20 + streak_score * 0.20))
        score = max(0, min(100, score))
        try:
            self._prod_ring.set_progress(score / 100.0, animate=True)
            self._prod_score_label.set_value(score, animate=True)
        except Exception:
            pass
        # Explanation
        if self._lang == "fa":
            parts = [
                f"استمرار: {int(consistency * 100)}٪",
                f"نرخ موفقیت هدف: {int(hit_rate * 100)}٪",
                f"زمان کل: {total_min} دقیقه",
                f"زنجیره: {streak} روز",
            ]
            explain = " · ".join(parts)
        else:
            parts = [
                f"Consistency: {int(consistency * 100)}%",
                f"Goal hit rate: {int(hit_rate * 100)}%",
                f"Total time: {total_min} min",
                f"Streak: {streak} days",
            ]
            explain = " · ".join(parts)
        try:
            self._prod_explain.configure(text=explain)
        except Exception:
            pass

    def _render_best_time(self, start: str, end: str) -> None:
        """Bar chart of minutes per hour (peak highlighted)."""
        try:
            rows = stats_service.by_hour(start, end)
        except Exception:
            rows = []
        if not rows:
            try:
                self._best_time_chart.set_data([])
            except Exception:
                pass
            return
        peak_row = max(rows, key=lambda r: int(r.get("total_min", 0) or 0))
        peak_hour = peak_row["hour"]
        data: List[Dict[str, Any]] = []
        for h in range(24):
            row = next((r for r in rows if r.get("hour") == h), None)
            minutes = int(row.get("total_min", 0) if row else 0)
            label = (i18n.to_fa_digits(f"{h:02d}")
                      if self._lang == "fa" else f"{h:02d}")
            color = config.GOLD_BRIGHT if h == peak_hour else config.GOLD
            data.append({"label": label, "value": minutes, "color": color})
        try:
            self._best_time_chart.set_data(data)
        except Exception:
            pass

    def _render_best_day(self, start: str, end: str) -> None:
        """Bar chart of minutes per weekday (peak highlighted)."""
        try:
            rows = stats_service.by_weekday(start, end)
        except Exception:
            rows = []
        if not rows:
            try:
                self._best_day_chart.set_data([])
            except Exception:
                pass
            return
        peak_row = max(rows, key=lambda r: int(r.get("total_min", 0) or 0))
        peak_wd = peak_row["weekday"]
        from ...core.time_utils import weekday_name
        ref_dates = ["2025-03-22", "2025-03-23", "2025-03-24",
                     "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28"]
        data: List[Dict[str, Any]] = []
        for i, ref in enumerate(ref_dates):
            row = next((r for r in rows if r.get("weekday") == i), None)
            minutes = int(row.get("total_min", 0) if row else 0)
            try:
                label = weekday_name(ref, self._lang)[:3]
            except Exception:
                label = str(i)
            color = (config.GOLD_BRIGHT if i == peak_wd
                      else config.GOLD)
            data.append({"label": label, "value": minutes, "color": color})
        try:
            self._best_day_chart.set_data(data)
        except Exception:
            pass

    def _render_top_categories(self, start: str, end: str) -> None:
        """Ranked list of categories with progress bars."""
        # Clear
        for child in self._top_cats_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            rows = stats_service.by_category(start, end)
        except Exception:
            rows = []
        if not rows:
            ctk.CTkLabel(
                self._top_cats_frame, text="—",
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_FAINT,
            ).grid(row=0, column=0, sticky="ew")
            return
        total = sum(int(r.get("total_min", 0) or 0) for r in rows) or 1
        rtl = i18n.is_rtl(self._lang)
        for i, r in enumerate(rows[:5]):
            name = (r.get("category_name_fa") if self._lang == "fa"
                     else r.get("category_en")) or "—"
            color = r.get("category_color") or config.GOLD
            minutes = int(r.get("total_min", 0) or 0)
            pct = minutes / total
            pct_str = (i18n.to_fa_digits(str(int(pct * 100))) + "٪"
                        if self._lang == "fa" else f"{int(pct * 100)}%")
            min_str = (i18n.to_fa_digits(str(minutes))
                        if self._lang == "fa" else str(minutes))
            unit = "دقیقه" if self._lang == "fa" else "min"
            row_frame = ctk.CTkFrame(self._top_cats_frame,
                                       fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", pady=2)
            row_frame.grid_columnconfigure(0, weight=1)
            # Top: name + percent
            top_row = ctk.CTkFrame(row_frame, fg_color="transparent")
            top_row.grid(row=0, column=0, sticky="ew")
            top_row.grid_columnconfigure(0, weight=1)
            # Name + color dot
            name_row = ctk.CTkFrame(top_row, fg_color="transparent")
            name_row.grid(row=0, column=0, sticky="e" if rtl else "w")
            dot = ctk.CTkFrame(name_row, width=10, height=10,
                                fg_color=color,
                                corner_radius=config.RADIUS_PILL)
            dot.pack(side="right" if rtl else "left", padx=(0, 6))
            ctk.CTkLabel(
                name_row, text=f"{i + 1}. {name}",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT,
            ).pack(side="right" if rtl else "left")
            # Percent (right side)
            ctk.CTkLabel(
                top_row, text=f"{min_str} {unit} · {pct_str}",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).grid(row=0, column=1, sticky="e" if rtl else "w")
            # Progress bar
            bar = ProgressBar(row_frame, value=pct, height=4)
            bar.grid(row=1, column=0, sticky="ew", pady=(2, 0))

    def _render_streak(self) -> None:
        """Streak analysis: current + best + motivational text."""
        try:
            current = int(stats_service.current_streak() or 0)
        except Exception:
            current = 0
        try:
            best = int(stats_service.longest_streak_ever() or 0)
        except Exception:
            best = 0
        try:
            self._streak_current.set_value(current, animate=True)
            self._streak_best.set_value(best, animate=True)
        except Exception:
            pass
        # Motivational message
        if self._lang == "fa":
            if current == 0:
                msg = "برای شروع زنجیره، امروز یک فعالیت ثبت کن."
            elif current < best:
                msg = (f"زنجیره‌ات را ادامه بده — رکوردت {best} روز است.")
            elif current == best and best > 0:
                msg = ("تبریک! رکوردت را شکستی. همین‌طور ادامه بده.")
            else:
                msg = "زنجیره‌ات عالی است. هر روز کمی بهبود پیدا کن."
        else:
            if current == 0:
                msg = "Log an activity today to start your streak."
            elif current < best:
                msg = f"Keep going — your record is {best} days."
            elif current == best and best > 0:
                msg = "Congratulations! You broke your record."
            else:
                msg = "Your streak is excellent. Keep improving daily."
        try:
            self._streak_msg.configure(text=msg)
        except Exception:
            pass

    def _render_weekly_comparison(self) -> None:
        """This week vs last week, day-by-day grouped bar chart."""
        today = time_utils.today_iso()
        # This week (Sat-Fri) — use Persian week starting Saturday
        week_start = time_utils.start_of_week(today, first_day=6)
        week_end = time_utils.end_of_week(today, first_day=6)
        last_week_start = time_utils.add_days(week_start, -7)
        last_week_end = time_utils.add_days(week_end, -7)
        try:
            this_week = stats_service.by_day(week_start, week_end)
            last_week = stats_service.by_day(last_week_start, last_week_end)
        except Exception:
            this_week, last_week = [], []
        # Build combined bar chart: 14 bars (7 last week + 7 this week)
        # with a separator gap. Color: this week = gold, last week = dim.
        from ...core.time_utils import weekday_name
        ref_dates = ["2025-03-22", "2025-03-23", "2025-03-24",
                     "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28"]
        # Map by date
        this_map = {r.get("date_iso"): r for r in this_week}
        last_map = {r.get("date_iso"): r for r in last_week}
        data: List[Dict[str, Any]] = []
        # Last week (7 bars)
        for i in range(7):
            d = time_utils.add_days(last_week_start, i)
            row = last_map.get(d)
            minutes = int(row.get("total_min", 0) if row else 0)
            data.append({"label": "", "value": minutes,
                          "color": config.SURFACE_HI})
        # This week (7 bars)
        for i in range(7):
            d = time_utils.add_days(week_start, i)
            row = this_map.get(d)
            minutes = int(row.get("total_min", 0) if row else 0)
            try:
                label = weekday_name(d, self._lang)[:2]
            except Exception:
                label = ""
            data.append({"label": label, "value": minutes,
                          "color": config.GOLD})
        try:
            self._weekly_chart.set_data(data)
        except Exception:
            pass

    def _render_goals_overview(self) -> None:
        """Goals overview: on-track vs behind, with progress bars."""
        for child in self._goals_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            goals = goal_service.list(only_active=True)
        except Exception:
            goals = []
        if not goals:
            ctk.CTkLabel(
                self._goals_frame,
                text=(i18n.t("noGoals", self._lang) if "noGoals" in _keys()
                       else ("هدفی تعریف نشده" if self._lang == "fa"
                              else "No goals yet")),
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_FAINT,
                anchor="e" if i18n.is_rtl(self._lang) else "w",
            ).grid(row=0, column=0, sticky="ew")
            return
        rtl = i18n.is_rtl(self._lang)
        for i, g in enumerate(goals[:6]):
            try:
                progress = goal_service.progress_for(g["id"])
            except Exception:
                progress = {}
            target = int(progress.get("target_min", 1) or 1)
            current = int(progress.get("current_min", 0) or 0)
            pct = current / target if target > 0 else 0.0
            pct = max(0.0, min(1.0, pct))
            period_label = (PERIOD_LABELS_FA.get(g.get("period", "daily"))
                             if self._lang == "fa"
                             else PERIOD_LABELS_EN.get(g.get("period",
                                                                "daily")))
            status = (i18n.t("goalOnTrack", self._lang)
                       if "goalOnTrack" in _keys()
                       else ("در مسیر" if self._lang == "fa"
                              else "On track")) if pct >= 0.7 else (
                          i18n.t("goalBehind", self._lang)
                          if "goalBehind" in _keys()
                          else ("عقب‌تر" if self._lang == "fa"
                                 else "Behind"))
            status_color = config.SUCCESS if pct >= 0.7 else (
                config.WARNING if pct >= 0.4 else config.DANGER)
            row_frame = ctk.CTkFrame(self._goals_frame,
                                       fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", pady=3)
            row_frame.grid_columnconfigure(0, weight=1)
            # Top: period + status
            top = ctk.CTkFrame(row_frame, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew")
            top.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                top, text=period_label,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0, sticky="e" if rtl else "w")
            ctk.CTkLabel(
                top, text=status,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=status_color,
            ).grid(row=0, column=1, sticky="e" if rtl else "w")
            # Progress bar
            bar = ProgressBar(row_frame, value=pct, height=4)
            bar.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            # Pct label
            pct_str = (i18n.to_fa_digits(str(int(pct * 100))) + "٪"
                        if self._lang == "fa" else f"{int(pct * 100)}%")
            ctk.CTkLabel(
                row_frame, text=pct_str,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
                anchor="e" if rtl else "w",
            ).grid(row=2, column=0, sticky="e" if rtl else "w", pady=(2, 0))

    def _render_recommendations(self, start: str, end: str) -> None:
        """Tailored recommendations bullet list."""
        for child in self._recs_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        recs: List[str] = []
        # Gather data
        try:
            s = stats_service.summary(start, end)
            total_min = int(s.get("total_min", 0) or 0)
            day_count = int(s.get("day_count", 0) or 0)
            total_days = max(1, time_utils.days_between(start, end) + 1)
            consistency = day_count / total_days
            streak = int(stats_service.current_streak() or 0)
            hour_rows = stats_service.by_hour(start, end)
            p = _detect_personality(hour_rows)
        except Exception:
            total_min = 0
            consistency = 0
            streak = 0
            p = PERSONALITIES[3]
        # Build recommendations
        if self._lang == "fa":
            if consistency < 0.5:
                recs.append("برای بهبود استمرار، هر روز حتی ۵ دقیقه فعالیت ثبت کن.")
            if streak == 0:
                recs.append("امروز یک فعالیت ثبت کن تا زنجیره‌ات را شروع کنی.")
            elif streak < 7:
                recs.append(f"زنجیره‌ات را تا {streak + 1} روز گسترش بده.")
            if p["key"] == "night_owl":
                recs.append("برای تعادل، یک فعالیت صبحگاهی کوتاه امتحان کن.")
            elif p["key"] == "early_bird":
                recs.append("از انرژی صبحگاهی‌ات برای کارهای مهم استفاده کن.")
            if total_min < 600:
                recs.append("هدف روزانه‌ات را ۳۰ دقیقه تعیین کن و سعی کن به آن برسی.")
            if not recs:
                recs.append("الگوی فعالیتت متعادل است — همین‌طور ادامه بده.")
        else:
            if consistency < 0.5:
                recs.append("Log even 5 minutes daily to improve consistency.")
            if streak == 0:
                recs.append("Log an activity today to start your streak.")
            elif streak < 7:
                recs.append(f"Extend your streak to {streak + 1} days.")
            if p["key"] == "night_owl":
                recs.append("Try a short morning activity for balance.")
            elif p["key"] == "early_bird":
                recs.append("Use your morning energy for important work.")
            if total_min < 600:
                recs.append("Set a 30-minute daily goal and try to hit it.")
            if not recs:
                recs.append("Your activity pattern is balanced — keep it up.")
        # Render
        rtl = i18n.is_rtl(self._lang)
        for i, rec in enumerate(recs):
            row = ctk.CTkFrame(self._recs_frame, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(1, weight=1)
            # Bullet dot
            dot = ctk.CTkFrame(row, width=6, height=6,
                                fg_color=config.GOLD,
                                corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=0, padx=(0, 8),
                      sticky="e" if rtl else "w")
            # Text
            ctk.CTkLabel(
                row, text=rec,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                justify="right" if rtl else "left",
                wraplength=380,
            ).grid(row=0, column=1, sticky="ew")

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
# === Period labels (mirrored from goals_screen for the goals-overview row) ===
# =============================================================================

PERIOD_LABELS_FA: Dict[str, str] = {
    "daily": "روزانه",
    "weekly": "هفتگی",
    "monthly": "ماهانه",
}
PERIOD_LABELS_EN: Dict[str, str] = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
}


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

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
    print("InsightsScreen module: personality + score + 2 charts + categories + streak + weekly + goals + recs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
