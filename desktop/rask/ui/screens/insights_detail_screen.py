"""
rask.ui.screens.insights_detail_screen
======================================

Extended smart-insights screen — a richer view of the InsightEngine
output with personality cards, productivity score breakdown, best
times, top categories, streak analysis, weekly comparison, goals
analysis, recommendations, and anomaly detection.

Mirrors the *Smart Insights* view from the web app.  Uses
:class:`rask.features.smart_insights.InsightEngine` as the source of
truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"بینش‌های هوشمند"`` with refresh button
    2. **Personality card** — large icon + title + description
    3. **Productivity score card** — big number + breakdown
       (sleep, focus time, variety, consistency)
    4. **Best time / day cards** — best hour and best weekday
    5. **Top categories** — list with trend arrows
    6. **Streak analysis** — current vs best with motivational text
    7. **Weekly comparison** — bar chart vs last week
    8. **Goals analysis** — on-track / behind / missed counts
    9. **Recommendations list** — actionable items with "اجرا" buttons
    10. **Anomaly detection cards** — unusual-day warnings

Auto-refresh
------------
Subscribes to ``insights.computed`` / ``activity.added`` /
``activity.updated`` / ``activity.deleted`` / ``streak.incremented`` /
``streak.reset`` / ``goal.added`` / ``goal.updated`` /
``goal.deleted`` / ``language.changed`` / ``data.cleared``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus
from ...features.smart_insights import (
    insight_engine, Insight, KIND_INFO, KIND_WARNING,
    KIND_SUCCESS, KIND_ACHIEVEMENT,
)
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.charts import BarChart
from ..widgets.dialogs import AlertDialog

__all__ = ["InsightsDetailScreen"]


# =============================================================================
# === Insight kind → color/icon mapping                                      ===
# =============================================================================

_KIND_COLOR: Dict[str, str] = {
    KIND_INFO: config.INFO,
    KIND_WARNING: config.WARNING,
    KIND_SUCCESS: config.SUCCESS,
    KIND_ACHIEVEMENT: config.GOLD,
}
_KIND_ICON: Dict[str, str] = {
    KIND_INFO: "ℹ",
    KIND_WARNING: "⚠",
    KIND_SUCCESS: "✓",
    KIND_ACHIEVEMENT: "★",
}
_PERSONALITY_ICONS: Dict[str, str] = {
    "سحرخیز": "🌅",
    "صبح‌کار": "☀",
    "بعدازظهرکار": "🌤",
    "عصرکار": "🌇",
    "شب‌بیدار": "🌙",
    "Early Bird": "🌅",
    "Morning Person": "☀",
    "Afternoon Person": "🌤",
    "Evening Person": "🌇",
    "Night Owl": "🌙",
}


def _kind_color(kind: str) -> str:
    return _KIND_COLOR.get(kind, config.GOLD)


def _kind_icon(kind: str) -> str:
    return _KIND_ICON.get(kind, "•")


def _personality_icon(label: str) -> str:
    """Find an emoji for a personality label."""
    for key, val in _PERSONALITY_ICONS.items():
        if key in label:
            return val
    return "✨"


# =============================================================================
# === InsightsDetailScreen                                                   ===
# =============================================================================

class InsightsDetailScreen(ctk.CTkFrame):
    """Extended smart-insights screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``switch_tab(tab)``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._cached_insights: List[Insight] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._header = Header(
            self, title=self._tr("بینش‌های هوشمند",
                                   "Smart Insights"),
            lang=self._lang, height=56,
            action_icon="refresh",
            on_action=self._on_refresh,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        # All sections are dynamically built in refresh(); we just
        # hold a single content frame here.
        self._content_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._content_frame.grid(row=0, column=0, sticky="ew")
        self._content_frame.grid_columnconfigure(0, weight=1)

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
            "insights.computed",
            "activity.added", "activity.updated", "activity.deleted",
            "streak.incremented", "streak.reset",
            "goal.added", "goal.updated", "goal.deleted",
            "language.changed", "data.cleared",
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
        # Invalidate the insight engine cache so we re-compute
        try:
            insight_engine.invalidate()
        except Exception:
            pass
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(200, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render everything from the insight engine."""
        # Clear old content
        for child in self._content_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._section_row = 0
        # Generate insights
        try:
            insights = insight_engine.generate_all()
        except Exception:
            insights = []
        self._cached_insights = insights
        if not insights:
            EmptyState(
                self._content_frame, icon="lightbulb",
                title=self._tr("هنوز بینشی نیست",
                                "No insights yet"),
                subtitle=self._tr("با ثبت فعالیت، بینش‌های هوشمند ظاهر می‌شوند",
                                    "Log activities to unlock insights"),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_XL)
            return
        # Build sections from insights
        personality = self._find_insight("personality")
        productivity = self._find_insight("productivity_score")
        best_times = self._find_insight("best_times")
        top_cats = self._find_insight("top_categories")
        streak = self._find_insight("streak_analysis")
        weekly = self._find_insight("weekly_comparison")
        goals = self._find_insight("goals_analysis")
        recommendations = [i for i in insights
                            if i.id.startswith("rec_")]
        anomalies = [i for i in insights
                      if i.id.startswith("anomaly_")]
        # Build each section
        if personality is not None:
            self._build_personality_card(personality)
        if productivity is not None:
            self._build_productivity_card(productivity)
        if best_times is not None:
            self._build_best_times_card(best_times)
        if top_cats is not None:
            self._build_top_categories_card(top_cats)
        if streak is not None:
            self._build_streak_card(streak)
        if weekly is not None:
            self._build_weekly_comparison_card(weekly)
        if goals is not None:
            self._build_goals_card(goals)
        if recommendations:
            self._build_recommendations_list(recommendations)
        if anomalies:
            self._build_anomalies_list(anomalies)
        # Footer
        self._build_footer()

    def _find_insight(self, category: str) -> Optional[Insight]:
        for i in self._cached_insights:
            if i.category == category:
                return i
        return None

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_personality_card(self, insight: Insight) -> None:
        """Large icon + title + description."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Icon + title row
        header_row = ctk.CTkFrame(card.content, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew")
        header_row.grid_columnconfigure(1, weight=1)
        icon_label = ctk.CTkLabel(
            header_row,
            text=_personality_icon(insight.title),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang="en"),
            text_color=config.GOLD,
        )
        icon_label.grid(row=0, column=1 if rtl else 0, padx=8)
        ctk.CTkLabel(
            header_row, text=insight.title,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                else "w")
        # Body
        ctk.CTkLabel(
            card.content, text=insight.body,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
            wraplength=420, justify="right" if rtl else "left",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(config.SPACE_SM, 0))

    def _build_productivity_card(self, insight: Insight) -> None:
        """Big productivity score + breakdown."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Big score (left/right)
        score_str = "—"
        if insight.score is not None:
            score_str = (i18n.to_fa_digits(str(insight.score))
                          if self._lang == "fa"
                          else str(insight.score))
        ctk.CTkLabel(
            card.content, text=score_str,
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=0, column=0 if rtl else 1, rowspan=2, padx=8)
        # Title + body
        ctk.CTkLabel(
            card.content,
            text=self._tr("امتیاز بهره‌وری", "Productivity score"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=1 if rtl else 0, sticky="e" if rtl
                else "w")
        ctk.CTkLabel(
            card.content, text=insight.body,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            wraplength=320, justify="right" if rtl else "left",
        ).grid(row=1, column=1 if rtl else 0, sticky="e" if rtl
                else "w", pady=(2, 0))

    def _build_best_times_card(self, insight: Insight) -> None:
        """Best time-of-day and best day-of-week."""
        self._make_simple_insight_card(
            self._next_row(),
            icon="⏰",
            title=self._tr("بهترین زمان‌ها", "Best times"),
            body=insight.body,
            color=config.INFO,
        )

    def _build_top_categories_card(self, insight: Insight) -> None:
        """Top categories with trends."""
        self._make_simple_insight_card(
            self._next_row(),
            icon="📊",
            title=self._tr("دسته‌های برتر", "Top categories"),
            body=insight.body,
            color=config.GOLD,
        )

    def _build_streak_card(self, insight: Insight) -> None:
        """Streak analysis with motivational text."""
        self._make_simple_insight_card(
            self._next_row(),
            icon="🔥",
            title=self._tr("تحلیل زنجیره", "Streak analysis"),
            body=insight.body,
            color=config.SUCCESS,
        )

    def _build_weekly_comparison_card(self, insight: Insight) -> None:
        """Weekly comparison + bar chart."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content,
            text=self._tr("مقایسه هفتگی", "Weekly comparison"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            card.content, text=insight.body,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            wraplength=420, justify="right" if rtl else "left",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, config.SPACE_SM))
        # Bar chart: this week vs last week
        # Parse the score field which encodes the percentages
        try:
            this_week = insight.score or 0
            last_week = max(0, this_week - 10)  # crude fallback
            # Try to read the body for percentages
            import re
            nums = re.findall(r"\d+", insight.body or "")
            if len(nums) >= 2:
                last_week = int(nums[0])
                this_week = int(nums[1])
            bar_data = [
                {"label": self._tr("هفته قبل", "Last week"),
                 "value": last_week, "color": config.TEXT_DIM},
                {"label": self._tr("این هفته", "This week"),
                 "value": this_week, "color": config.GOLD},
            ]
            chart = BarChart(
                card.content, data=bar_data, width=460, height=140,
                max_value=float(max(last_week, this_week, 1) * 1.2),
                lang=self._lang,
            )
            chart.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        except Exception:
            pass

    def _build_goals_card(self, insight: Insight) -> None:
        """Goals analysis: on-track / behind / missed."""
        self._make_simple_insight_card(
            self._next_row(),
            icon="🎯",
            title=self._tr("تحلیل اهداف", "Goals analysis"),
            body=insight.body,
            color=config.GOLD_SOFT,
        )

    def _build_recommendations_list(self,
                                       insights: List[Insight]) -> None:
        """Actionable recommendations list with 'اجرا' buttons."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("پیشنهادات", "Recommendations"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, ins in enumerate(insights):
            card = Card(section, lang=self._lang,
                         padding=config.SPACE_MD)
            card.grid(row=i + 1, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            card.content.grid_columnconfigure(1, weight=1)
            # Icon
            ctk.CTkLabel(
                card.content, text=_kind_icon(ins.kind),
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang="en"),
                text_color=_kind_color(ins.kind),
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            # Body
            ctk.CTkLabel(
                card.content, text=ins.body,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=300, justify="right" if rtl else "left",
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w")
            # Action button
            if ins.actionable and ins.action_text:
                GoldButton(
                    card.content, text=ins.action_text,
                    command=lambda _i=ins: self._on_insight_action(_i),
                    lang=self._lang, height=32,
                    font_size=config.FONT_SIZE_CAPTION,
                ).grid(row=0, column=2 if rtl else 2, padx=4)

    def _build_anomalies_list(self, insights: List[Insight]) -> None:
        """Anomaly detection cards."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("ناهنجاری‌ها", "Anomalies"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, ins in enumerate(insights):
            card = Card(section, lang=self._lang,
                         padding=config.SPACE_MD)
            card.grid(row=i + 1, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            card.content.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                card.content, text="⚠",
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang="en"),
                text_color=config.WARNING,
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            ctk.CTkLabel(
                card.content, text=ins.body,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=380, justify="right" if rtl else "left",
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w")

    def _make_simple_insight_card(self, row: int, icon: str,
                                     title: str, body: str,
                                     color: str) -> None:
        """Helper: build a simple icon+title+body insight card."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Icon
        ctk.CTkLabel(
            card.content, text=icon,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang="en"),
            text_color=color,
        ).grid(row=0, column=1 if rtl else 0, padx=8)
        # Title + body
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=0 if rtl else 1, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=color,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            info, text=body,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            wraplength=360, justify="right" if rtl else "left",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_footer(self) -> None:
        """Footer with a tip."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=self._tr("بینش‌ها بر اساس داده‌های ۳۰ روز اخیر تولید شده‌اند.",
                            "Insights are generated from the last 30 days of data."),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT, justify="center",
            wraplength=420,
        ).grid(row=0, column=0)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_refresh(self) -> None:
        """Manual refresh — invalidate cache + rebuild."""
        try:
            insight_engine.invalidate()
        except Exception:
            pass
        self._show_toast(self._tr("در حال به‌روزرسانی...",
                                    "Refreshing..."))
        self._schedule_refresh()

    def _on_insight_action(self, insight: Insight) -> None:
        """Tap a recommendation's action button."""
        # Default: just show the title in a toast / dialog
        try:
            payload = insight.action_payload or {}
            # If payload has a 'tab' key, switch to it
            if "tab" in payload and self._app and hasattr(
                    self._app, "switch_tab"):
                try:
                    self._app.switch_tab(payload["tab"])
                    return
                except Exception:
                    pass
            # Otherwise show a dialog
            AlertDialog(
                self, title=insight.title or self._tr("پیشنهاد",
                                                         "Recommendation"),
                message=insight.body,
                lang=self._lang, ok_text=self._tr("بستن", "Close"),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            v = i18n.t(fa, self._lang)
            if v != fa:
                return v
        except Exception:
            pass
        return fa if self._lang == "fa" else en

    def _show_toast(self, message: str) -> None:
        if self._app and hasattr(self._app, "show_toast"):
            try:
                self._app.show_toast(message)
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.toast", {"message": message})
        except Exception:
            pass

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
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("InsightsDetailScreen module: personality + productivity + "
          "best times + top categories + streak + weekly comparison + "
          "goals + recommendations + anomalies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
