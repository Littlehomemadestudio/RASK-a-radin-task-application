"""
rask.ui.screens.weekly_review_screen
====================================

Weekly review screen — a beautiful, email-newsletter-style summary of
the past week.

Mirrors the *Weekly Review* view from the web app.  Uses
:class:`rask.features.weekly_review.WeeklyReview` as the source of
truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"مرور هفتگی"`` with share button
    2. **Week navigation** — prev / next week, this week
    3. **Summary card** — total time, total activities, top category,
       longest streak
    4. **Goal hits card** — X / Y goals achieved
    5. **Mood/energy summary** — averages for the week
    6. **Comparison vs last week** — % change with arrow
    7. **Highlights** — auto-generated bullet list
    8. **Lowlights** — auto-generated bullet list
    9. **Recommendations** — auto-generated bullet list
    10. **Share buttons** — Copy as Text, Copy as Markdown,
        Copy as HTML, Export PDF

Auto-refresh
------------
Subscribes to ``weekly_review.generated`` / ``activity.added`` /
``activity.updated`` / ``activity.deleted`` / ``goal.added`` /
``goal.updated`` / ``goal.deleted`` / ``journal.added`` /
``journal.updated`` / ``habit.logged`` / ``habit.unlogged`` /
``language.changed`` / ``data.cleared``.
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
from ...core import event_bus, time_utils, jalali
from ...features.weekly_review import weekly_review
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.charts import BarChart

__all__ = ["WeeklyReviewScreen"]


# =============================================================================
# === WeeklyReviewScreen                                                     ===
# =============================================================================

class WeeklyReviewScreen(ctk.CTkFrame):
    """Weekly review screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``show_export_dialog()``
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
        # Anchor = today's date (the week containing it is shown)
        self._anchor_iso: str = time_utils.today_iso()
        self._current_review: Optional[Dict[str, Any]] = None
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
            self, title=self._tr("مرور هفتگی", "Weekly Review"),
            lang=self._lang, height=56,
            action_icon="share",
            on_action=self._on_share_text,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_week_nav()
        # All other sections are built dynamically in refresh()
        self._content_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._content_frame.grid(row=self._next_row(), column=0,
                                   sticky="ew")
        self._content_frame.grid_columnconfigure(0, weight=1)

    def _build_week_nav(self) -> None:
        """Prev / next week, this week button + week range label."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        prev_btn = IconButton(
            section, icon_name="chevron_right" if rtl else "chevron_left",
            command=lambda: self._go_week(-1),
            size=40, lang=self._lang,
        )
        prev_btn.grid(row=0, column=0 if rtl else 2, padx=4)
        self._week_label = ctk.CTkLabel(
            section, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._week_label.grid(row=0, column=1)
        next_btn = IconButton(
            section, icon_name="chevron_left" if rtl else "chevron_right",
            command=lambda: self._go_week(1),
            size=40, lang=self._lang,
        )
        next_btn.grid(row=0, column=2 if rtl else 0, padx=4)
        TextButton(
            section, text=self._tr("این هفته", "This week"),
            command=self._go_this_week, lang=self._lang,
            height=24, font_size=config.FONT_SIZE_CAPTION,
            color=config.GOLD,
        ).grid(row=1, column=0, columnspan=3, pady=(4, 0))

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
            "weekly_review.generated",
            "activity.added", "activity.updated", "activity.deleted",
            "goal.added", "goal.updated", "goal.deleted",
            "journal.added", "journal.updated",
            "habit.logged", "habit.unlogged",
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
        """Re-render the weekly review."""
        # Generate the review
        try:
            review = weekly_review.generate(self._anchor_iso)
        except Exception:
            review = {}
        self._current_review = review
        # Update week label
        try:
            start = review.get("week_start", "")
            end = review.get("week_end", "")
            if start and end:
                start_str = jalali.format_jalali(
                    start, fmt="short", lang=self._lang)
                end_str = jalali.format_jalali(
                    end, fmt="short", lang=self._lang)
                self._week_label.configure(
                    text=f"{start_str} — {end_str}")
        except Exception:
            pass
        # Clear old content
        for child in self._content_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        if not review:
            EmptyState(
                self._content_frame, icon="doc",
                title=self._tr("داده‌ای موجود نیست",
                                "No data available"),
                subtitle=self._tr("فعالیت‌های این هفته را ثبت کن",
                                    "Log activities this week"),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_XL)
            return
        # Build sections
        self._build_summary_card(review)
        self._build_goals_card(review)
        self._build_mood_card(review)
        self._build_comparison_card(review)
        self._build_highlights_card(review)
        self._build_lowlights_card(review)
        self._build_recommendations_card(review)
        self._build_by_day_chart(review)
        self._build_share_buttons()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_summary_card(self, review: Dict[str, Any]) -> None:
        """Top summary card with 4 stats."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Title
        ctk.CTkLabel(
            card.content, text=self._tr("خلاصه هفته", "Week summary"),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # 2x2 stats grid
        stats_grid = ctk.CTkFrame(card.content, fg_color="transparent")
        stats_grid.grid(row=1, column=0, sticky="ew",
                         pady=(config.SPACE_SM, 0))
        for i in range(4):
            stats_grid.grid_rowconfigure(i // 2, weight=1)
            stats_grid.grid_columnconfigure(i % 2, weight=1,
                                              uniform="ws")
        # Total time
        total_min = int(review.get("total_min", 0) or 0)
        total_str = self._format_minutes(total_min)
        self._make_mini_stat(stats_grid, 0,
                              self._tr("زمان کل", "Total time"),
                              total_str)
        # Total activities
        total_act = int(review.get("total_activities", 0) or 0)
        act_str = (i18n.to_fa_digits(str(total_act))
                   if self._lang == "fa" else str(total_act))
        self._make_mini_stat(stats_grid, 1,
                              self._tr("فعالیت‌ها", "Activities"),
                              act_str)
        # Top category
        top_cat = review.get("top_category", "—")
        self._make_mini_stat(stats_grid, 2,
                              self._tr("دسته برتر", "Top category"),
                              top_cat)
        # Longest streak
        longest = int(review.get("longest_streak", 0) or 0)
        longest_str = (i18n.to_fa_digits(str(longest))
                       if self._lang == "fa" else str(longest))
        longest_str += " " + self._tr("روز", "days")
        self._make_mini_stat(stats_grid, 3,
                              self._tr("بیشترین زنجیره", "Longest streak"),
                              longest_str)

    def _make_mini_stat(self, parent: ctk.CTkFrame, idx: int,
                          label: str, value: str) -> None:
        row = idx // 2
        col = (1 - (idx % 2)) if i18n.is_rtl(self._lang) else (idx % 2)
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=col, sticky="nsew",
                   padx=4, pady=4)
        wrap.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            wrap, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            wrap, text=value,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_goals_card(self, review: Dict[str, Any]) -> None:
        """Goal hits card: X / Y achieved."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Big number
        hits = int(review.get("goal_hits", 0) or 0)
        misses = int(review.get("goal_misses", 0) or 0)
        total = hits + misses
        hits_str = (i18n.to_fa_digits(str(hits))
                     if self._lang == "fa" else str(hits))
        total_str = (i18n.to_fa_digits(str(total))
                      if self._lang == "fa" else str(total))
        ctk.CTkLabel(
            card.content, text=f"{hits_str} / {total_str}",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=0, column=0 if rtl else 1, padx=8)
        # Title + subtitle
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1 if rtl else 0, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=self._tr("اهداف محقق شده",
                                  "Goals achieved"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        if misses > 0:
            misses_str = (i18n.to_fa_digits(str(misses))
                           if self._lang == "fa" else str(misses))
            sub = f"{misses_str} {self._tr('هدف محقق نشد', 'goals missed')}"
        else:
            sub = self._tr("همه اهداف محقق شد! 🎉",
                            "All goals hit! 🎉")
        ctk.CTkLabel(
            info, text=sub,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_mood_card(self, review: Dict[str, Any]) -> None:
        """Mood/energy summary card."""
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
            text=self._tr("حال و انرژی", "Mood & Energy"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # 2 mini-stats
        row = ctk.CTkFrame(card.content, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew",
                  pady=(config.SPACE_SM, 0))
        for i in range(2):
            row.grid_columnconfigure(i, weight=1, uniform="mood")
        mood_avg = float(review.get("mood_avg", 0.0) or 0.0)
        energy_avg = float(review.get("energy_avg", 0.0) or 0.0)
        mood_str = (f"{i18n.to_fa_digits(str(round(mood_avg, 1)))} "
                     f"/ ۵" if self._lang == "fa"
                     else f"{mood_avg:.1f} / 5")
        energy_str = (f"{i18n.to_fa_digits(str(round(energy_avg, 1)))} "
                        f"/ ۵" if self._lang == "fa"
                        else f"{energy_avg:.1f} / 5")
        # Mood mini-stat
        mood_wrap = ctk.CTkFrame(row, fg_color="transparent")
        mood_wrap.grid(row=0, column=0, sticky="nsew", padx=4)
        mood_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            mood_wrap, text=self._tr("میانگین حال", "Avg mood"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            mood_wrap, text=mood_str,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))
        # Energy mini-stat
        energy_wrap = ctk.CTkFrame(row, fg_color="transparent")
        energy_wrap.grid(row=0, column=1, sticky="nsew", padx=4)
        energy_wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            energy_wrap, text=self._tr("میانگین انرژی", "Avg energy"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            energy_wrap, text=energy_str,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_comparison_card(self, review: Dict[str, Any]) -> None:
        """Comparison vs last week with arrow."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Comparison %
        delta_min = int(review.get("delta_vs_last_week_min", 0) or 0)
        pct = int(review.get("comparison_vs_last_week_pct", 0) or 0)
        if delta_min > 0:
            arrow = "↑"
            color = config.SUCCESS
            label = self._tr("بیشتر", "more")
        elif delta_min < 0:
            arrow = "↓"
            color = config.DANGER
            label = self._tr("کمتر", "less")
        else:
            arrow = "—"
            color = config.TEXT_DIM
            label = self._tr("بدون تغییر", "no change")
        pct_str = (i18n.to_fa_digits(str(abs(pct))) + "٪"
                    if self._lang == "fa" else f"{abs(pct)}%")
        ctk.CTkLabel(
            card.content, text=f"{arrow} {pct_str}",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=color,
        ).grid(row=0, column=0 if rtl else 1, padx=8)
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1 if rtl else 0, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=self._tr("نسبت به هفته قبل",
                                  "vs last week"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        delta_str = self._format_minutes(abs(delta_min))
        ctk.CTkLabel(
            info, text=f"{delta_str} {label}",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=color,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_highlights_card(self, review: Dict[str, Any]) -> None:
        """Highlights bullet list."""
        highlights = review.get("highlights", []) or []
        if not highlights:
            return
        self._make_bullet_card(
            self._next_row(),
            self._tr("نقاط روشن", "Highlights"),
            highlights, config.SUCCESS, "★",
        )

    def _build_lowlights_card(self, review: Dict[str, Any]) -> None:
        """Lowlights bullet list."""
        lowlights = review.get("lowlights", []) or []
        if not lowlights:
            return
        self._make_bullet_card(
            self._next_row(),
            self._tr("نقاط تاریک", "Lowlights"),
            lowlights, config.WARNING, "•",
        )

    def _build_recommendations_card(self,
                                       review: Dict[str, Any]) -> None:
        """Recommendations bullet list."""
        recs = review.get("recommendations", []) or []
        if not recs:
            return
        self._make_bullet_card(
            self._next_row(),
            self._tr("پیشنهادات", "Recommendations"),
            recs, config.INFO, "→",
        )

    def _make_bullet_card(self, row: int, title: str,
                            items: List[str], color: str,
                            bullet: str) -> None:
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=color,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, item in enumerate(items):
            item_row = ctk.CTkFrame(card.content, fg_color="transparent")
            item_row.grid(row=i + 1, column=0, sticky="ew",
                           pady=(0 if i == 0 else 4, 0))
            item_row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                item_row, text=bullet,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=color,
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            ctk.CTkLabel(
                item_row, text=item,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=380, justify="right" if rtl else "left",
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w")

    def _build_by_day_chart(self, review: Dict[str, Any]) -> None:
        """Bar chart of minutes per day."""
        by_day = review.get("by_day", []) or []
        if not by_day:
            return
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
            text=self._tr("فعالیت روزانه", "Daily activity"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        # Build bar chart data
        try:
            bar_data = []
            for d in by_day:
                date_iso = d.get("date_iso", "")
                try:
                    label = jalali.format_jalali(
                        date_iso, fmt="short", lang=self._lang)
                    # Just the day number
                    label = label.split(" ")[-1] if label else "—"
                except Exception:
                    label = "—"
                bar_data.append({
                    "label": label,
                    "value": int(d.get("total_min", 0) or 0),
                    "color": config.GOLD,
                })
            chart = BarChart(
                card.content, data=bar_data, width=460, height=160,
                lang=self._lang,
            )
            chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        except Exception:
            pass

    def _build_share_buttons(self) -> None:
        """Share buttons row."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("اشتراک‌گذاری", "Share"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        # 4 buttons in a 2x2 grid
        buttons_grid = ctk.CTkFrame(section, fg_color="transparent")
        buttons_grid.grid(row=1, column=0, sticky="ew")
        for i in range(4):
            buttons_grid.grid_rowconfigure(i // 2, weight=1)
            buttons_grid.grid_columnconfigure(i % 2, weight=1,
                                                 uniform="share")
        share_options = [
            (self._tr("متن", "Text"), self._on_share_text),
            (self._tr("مارک‌داون", "Markdown"),
             self._on_share_markdown),
            (self._tr("HTML", "HTML"), self._on_share_html),
            (self._tr("PDF", "PDF"), self._on_share_pdf),
        ]
        for i, (label, cmd) in enumerate(share_options):
            row = i // 2
            col = (1 - (i % 2)) if rtl else (i % 2)
            btn = GhostButton(
                buttons_grid, text=label, command=cmd,
                lang=self._lang, height=40,
            )
            btn.grid(row=row, column=col, sticky="ew",
                      padx=4, pady=4)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _go_week(self, delta: int) -> None:
        """Go forward/backward by N weeks."""
        try:
            self._anchor_iso = time_utils.add_days(
                self._anchor_iso, delta * 7)
        except Exception:
            pass
        self.refresh()

    def _go_this_week(self) -> None:
        self._anchor_iso = time_utils.today_iso()
        self.refresh()

    def _on_share_text(self) -> None:
        if not self._current_review:
            return
        try:
            text = weekly_review.format_text(
                self._current_review, lang=self._lang)
            self._copy_to_clipboard(text)
            self._show_toast(self._tr("متن کپی شد", "Text copied"))
        except Exception:
            self._show_toast(self._tr("خطا در کپی", "Copy failed"))

    def _on_share_markdown(self) -> None:
        if not self._current_review:
            return
        try:
            text = weekly_review.format_markdown(
                self._current_review, lang=self._lang)
            self._copy_to_clipboard(text)
            self._show_toast(self._tr("مارک‌داون کپی شد",
                                        "Markdown copied"))
        except Exception:
            self._show_toast(self._tr("خطا در کپی", "Copy failed"))

    def _on_share_html(self) -> None:
        if not self._current_review:
            return
        try:
            text = weekly_review.format_html(
                self._current_review, lang=self._lang)
            self._copy_to_clipboard(text)
            self._show_toast(self._tr("HTML کپی شد",
                                        "HTML copied"))
        except Exception:
            self._show_toast(self._tr("خطا در کپی", "Copy failed"))

    def _on_share_pdf(self) -> None:
        """Export the weekly review as PDF."""
        if self._app and hasattr(self._app, "show_export_dialog"):
            try:
                self._app.show_export_dialog()
                return
            except Exception:
                pass
        self._show_toast(self._tr("قابلیت PDF به‌زودی",
                                    "PDF export coming soon"))

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
        except Exception:
            try:
                from ...features.weekly_review import _copy_to_clipboard
                _copy_to_clipboard(text)
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

    def _format_minutes(self, m: int) -> str:
        """Format minutes as 'Xh Ym' or 'X ساعت Y دقیقه'."""
        if m <= 0:
            return "۰ " + (self._tr("دقیقه", "min")
                            if self._lang == "fa" else "min")
        h = m // 60
        min_remainder = m % 60
        if self._lang == "fa":
            parts: List[str] = []
            if h > 0:
                parts.append(f"{i18n.to_fa_digits(str(h))} ساعت")
            if min_remainder > 0:
                parts.append(f"{i18n.to_fa_digits(str(min_remainder))} دقیقه")
            return " ".join(parts) if parts else "—"
        parts = []
        if h > 0:
            parts.append(f"{h}h")
        if min_remainder > 0:
            parts.append(f"{min_remainder}m")
        return " ".join(parts) if parts else "—"

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
    print("WeeklyReviewScreen module: week nav + summary + goals + "
          "mood/energy + comparison + highlights + lowlights + "
          "recommendations + daily chart + share buttons.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
