"""
rask.ui.screens.goals_screen
============================

Goals & streaks screen — daily / weekly / monthly goals with progress
rings, streak counts, hit-rate, and a 7-day mini bar chart per goal.

Mirrors ``web/index.html`` ``#screen-goals`` and the corresponding
``renderGoals`` function in ``web/js/app.js``, extended with the
``SegmentedControl`` for period switching and a hit-rate summary card.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"اهداف"`` + ``"+ هدف جدید"`` action button
    2. **Hit-rate summary card** — overall hit rate across all goals
       for the last 30 days, with a mini progress bar
    3. **Segmented control** — ``روزانه / هفتگی / ماهانه``
    4. **Goal list** — one ``GoalCard`` per goal in the active period,
       each showing:
            * Period title (e.g. ``"روزانه — تمرکز"``)
            * Category color dot if specific category
            * Progress ring (current / target minutes)
            * Streak count (current + best) with flame icon
            * Hit rate %
            * Last-7-days mini bar chart
            * Tap to edit, long-press to delete
    5. **Empty state** — friendly illustration + ``"اولین هدفت را بساز"``
       + create button
    6. **FAB-like quick-add** — same ``+`` button as home screen for
       consistency, opens the goal dialog

Auto-refresh
------------
Subscribes to ``goal.added`` / ``goal.updated`` / ``goal.deleted`` /
``goal.progress`` / ``streak.incremented`` / ``streak.reset`` /
``activity.added`` / ``activity.updated`` / ``activity.deleted`` /
``language.changed`` / ``data.imported`` / ``data.cleared``.
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
from ...core import event_bus, time_utils, jalali, helpers
from ...services import (
    goal_service, streak_service, activity_service, settings_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, FabButton,
)
from ..widgets.cards import Card, GoalCard, SummaryCard
from ..widgets.badges import Chip, StreakBadge, CategoryBadge
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.progress_ring import ProgressRing
from ..widgets.charts import BarChart
from ..widgets.sliders import ProgressBar
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toggles import SegmentedControl

__all__ = ["GoalsScreen"]


# =============================================================================
# === Period labels                                                          ===
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


def _period_label(period: str, lang: str) -> str:
    if lang == "fa":
        return PERIOD_LABELS_FA.get(period, period)
    return PERIOD_LABELS_EN.get(period, period)


# =============================================================================
# === Goal list item (custom card with extra details)                        ===
# =============================================================================

class _GoalItemCard(Card):
    """Extended goal card with progress ring + streak + hit rate + mini bar."""

    def __init__(
        self,
        master: Any,
        goal: Dict[str, Any],
        progress: Dict[str, Any],
        streak: Dict[str, Any],
        hit_rate: float,
        last_7_days: List[Dict[str, Any]],
        category: Optional[Dict[str, Any]],
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        on_long_press: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, lang=lang, on_click=on_click,
                          on_long_press=on_long_press,
                          padding=config.SPACE_MD, **kwargs)
        self._goal = goal
        self._progress = progress
        self._streak = streak
        self._hit_rate = hit_rate
        self._lang = lang
        self._category = category
        rtl = i18n.is_rtl(lang)
        # Grid: ring (col 0) | info (col 1) | sparkline (col 2)
        self.content.grid_columnconfigure(1, weight=1)
        # Ring (leading side in RTL)
        ring_col = 0 if rtl else 2
        target = int(progress.get("target_min", 1) or 1)
        current = int(progress.get("current_min", 0) or 0)
        pct = current / target if target > 0 else 0.0
        pct = max(0.0, min(1.0, pct))
        ring_size = 64
        ring = ProgressRing(
            self.content, progress=pct, size=ring_size,
            line_width=6, show_percentage=False,
            animated=True, lang=lang,
            label=f"{int(pct * 100)}%",
        )
        ring.grid(row=0, column=ring_col, rowspan=3, padx=4, pady=4,
                   sticky="nsew")
        # Info column (trailing side in RTL)
        info_col = 1 if rtl else 1
        info = ctk.CTkFrame(self.content, fg_color="transparent")
        info.grid(row=0, column=info_col, rowspan=3, sticky="nsew",
                   padx=8, pady=4)
        info.grid_columnconfigure(0, weight=1)
        # Row 1: title + category dot
        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(1, weight=1)
        period_label = _period_label(goal.get("period", "daily"), lang)
        if category:
            cat_name = (category.get("name_fa") if lang == "fa"
                         else category.get("name_en")) or "—"
            cat_color = category.get("color") or config.GOLD
            # Color dot
            dot = ctk.CTkFrame(title_row, width=10, height=10,
                                fg_color=cat_color,
                                corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=0, padx=(0, 6), sticky="e" if rtl
                      else "w")
            # Period + category name
            title_text = f"{period_label} — {cat_name}"
        else:
            all_label = i18n.t("allCategories", lang) if "allCategories" in _keys() else (
                "همه دسته‌ها" if lang == "fa" else "All categories")
            title_text = f"{period_label} — {all_label}"
        ctk.CTkLabel(
            title_row, text=title_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=1, sticky="ew")
        # Row 2: progress text (current / target)
        cur_str = (i18n.to_fa_digits(str(current)) if lang == "fa"
                    else str(current))
        tgt_str = (i18n.to_fa_digits(str(target)) if lang == "fa"
                    else str(target))
        unit = "دقیقه" if lang == "fa" else "min"
        progress_text = f"{cur_str} / {tgt_str} {unit}"
        ctk.CTkLabel(
            info, text=progress_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Row 3: streak + hit rate
        meta_row = ctk.CTkFrame(info, fg_color="transparent")
        meta_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        meta_row.grid_columnconfigure(0, weight=1)
        current_streak = int(streak.get("current", 0) or 0)
        best_streak = int(streak.get("best", 0) or 0)
        if current_streak > 0:
            streak_str = (i18n.to_fa_digits(str(current_streak))
                          if lang == "fa" else str(current_streak))
            best_str = (i18n.to_fa_digits(str(best_streak))
                         if lang == "fa" else str(best_streak))
            streak_text = (
                f"🔥 {streak_str} {i18n.t('days', lang)}"
                f" ({i18n.t('best', lang)}: {best_str})"
                if lang == "en"
                else f"🔥 {streak_str} {i18n.t('days', lang)}"
                f" ({i18n.t('best', lang)}: {best_str})"
            )
        else:
            streak_text = ""
        if streak_text:
            ctk.CTkLabel(
                meta_row, text=streak_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.GOLD,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Hit rate label
        hr_pct = int(hit_rate * 100) if hit_rate else 0
        hr_str = (i18n.to_fa_digits(str(hr_pct)) + "٪"
                   if lang == "fa" else f"{hr_pct}%")
        hr_label = (f"{i18n.t('goalHitRate', lang) if 'goalHitRate' in _keys() else ('نرخ موفقیت' if lang == 'fa' else 'Hit rate')}: {hr_str}")
        ctk.CTkLabel(
            meta_row, text=hr_label,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w", pady=(2, 0))
        # Row 4: last 7 days mini bar chart
        if last_7_days:
            bar_row = ctk.CTkFrame(info, fg_color="transparent")
            bar_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
            bar_row.grid_columnconfigure(0, weight=1)
            bar = BarChart(
                bar_row, data=last_7_days,
                width=200, height=48, lang=lang,
                max_value=None,
            )
            bar.grid(row=0, column=0, sticky="ew")


# =============================================================================
# === GoalsScreen                                                           ===
# =============================================================================

class GoalsScreen(ctk.CTkFrame):
    """Goals & streaks screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_goal_dialog(goal_id=None)``
            * ``show_toast(message)``
            * ``confirm_delete(message, on_confirm)``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        initial_period: str = "daily",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._period: str = initial_period if initial_period in (
            "daily", "weekly", "monthly") else "daily"
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._goal_cards: List[ctk.CTkBaseClass] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the goals screen: header + summary + tabs + list."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self,
            title=i18n.t("goals", self._lang),
            action_text=i18n.t("newGoal", self._lang),
            on_action=self._on_new_goal,
            lang=self._lang,
            height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # FAB
        self._fab = FabButton(
            self, icon_name="plus",
            command=self._on_new_goal, lang=self._lang,
        )
        self.after(100, self._place_fab)
        # Sections
        self._section_row = 0
        self._build_summary_card()
        self._build_period_tabs()
        self._build_goals_list()
        self._build_badges_section()

    def _place_fab(self) -> None:
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            fab_size = config.FAB_SIZE
            rtl = i18n.is_rtl(self._lang)
            x = 20 if rtl else w - fab_size - 20
            y = h - fab_size - 80
            self._fab.place(x=x, y=y)
        except Exception:
            pass

    def _build_summary_card(self) -> None:
        """Overall hit-rate summary card at the top of the screen."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._summary_card = Card(section, lang=self._lang,
                                    padding=config.SPACE_LG)
        self._summary_card.grid(row=0, column=0, sticky="ew")
        self._summary_card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Title row
        title_row = ctk.CTkFrame(self._summary_card.content,
                                  fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(1, weight=1)
        # Icon
        icon_label = ctk.CTkLabel(title_row, text="", width=32, height=32,
                                    fg_color="transparent")
        img = _icons.icon("trophy", 22, color=config.GOLD)
        if img is not None:
            icon_label.configure(image=img)
        else:
            icon_label.configure(text=_icons.icon_glyph("trophy"),
                                  text_color=config.GOLD)
        icon_label.grid(row=0, column=0, padx=(0, 8))
        # Label + hit rate %
        info_frame = ctk.CTkFrame(title_row, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew")
        info_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info_frame,
            text=(i18n.t("goalHitRate", self._lang)
                  if "goalHitRate" in _keys()
                  else ("نرخ موفقیت کلی" if self._lang == "fa"
                          else "Overall hit rate")),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._summary_hit_rate_label = ctk.CTkLabel(
            info_frame, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._summary_hit_rate_label.grid(row=1, column=0, sticky="ew",
                                            pady=(2, 0))
        # Progress bar
        self._summary_progress = ProgressBar(
            self._summary_card.content, value=0.0, height=6,
            animated=True,
        )
        self._summary_progress.grid(row=1, column=0, sticky="ew",
                                      pady=(config.SPACE_MD, 0))
        # Sub-text
        self._summary_subtitle = ctk.CTkLabel(
            self._summary_card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._summary_subtitle.grid(row=2, column=0, sticky="ew",
                                       pady=(4, 0))

    def _build_period_tabs(self) -> None:
        """Segmented control for period switching."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM,
                                                   config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        labels = [
            _period_label("daily", self._lang),
            _period_label("weekly", self._lang),
            _period_label("monthly", self._lang),
        ]
        self._period_seg = SegmentedControl(
            section, values=labels, lang=self._lang,
            on_change=self._on_period_change, height=40,
        )
        self._period_seg.grid(row=0, column=0, sticky="ew")
        # Set initial selection
        try:
            self._period_seg.value = _period_label(self._period,
                                                     self._lang)
        except Exception:
            pass

    def _build_goals_list(self) -> None:
        """Container for goal cards (and empty state)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        self._goals_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._goals_frame.grid(row=0, column=0, sticky="ew")
        self._goals_frame.grid_columnconfigure(0, weight=1)
        self._empty_state: Optional[EmptyState] = None

    def _build_badges_section(self) -> None:
        """Optional badges section (matches the web layout)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=i18n.t("badges", self._lang),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._badges_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._badges_frame.grid(row=1, column=0, sticky="ew")
        self._badges_frame.grid_columnconfigure(0, weight=1)

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
            "goal.added", "goal.updated", "goal.deleted", "goal.progress",
            "streak.incremented", "streak.reset",
            "activity.added", "activity.updated", "activity.deleted",
            "badge.unlocked",
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
        self._refresh_job = self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render summary + goals list + badges."""
        self._refresh_summary()
        self._refresh_goals()
        self._refresh_badges()

    def set_period(self, period: str) -> None:
        """Switch the active period (``daily`` / ``weekly`` / ``monthly``)."""
        if period not in ("daily", "weekly", "monthly"):
            return
        self._period = period
        try:
            self._period_seg.value = _period_label(period, self._lang)
        except Exception:
            pass
        self._refresh_goals()

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------
    def _refresh_summary(self) -> None:
        """Compute overall hit rate across all goals (last 30 days)."""
        try:
            rate = goal_service.goal_hit_rate(0, days=30)  # 0 = all goals
        except Exception:
            rate = 0.0
        # Some implementations may not support goal_id=0; fall back to averaging
        if not rate:
            try:
                goals = goal_service.list(only_active=True)
                rates = []
                for g in goals:
                    try:
                        r = goal_service.goal_hit_rate(g["id"], days=30)
                        if r:
                            rates.append(float(r))
                    except Exception:
                        pass
                rate = (sum(rates) / len(rates)) if rates else 0.0
            except Exception:
                rate = 0.0
        rate = max(0.0, min(1.0, float(rate or 0.0)))
        pct = int(rate * 100)
        pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                    if self._lang == "fa" else f"{pct}%")
        try:
            self._summary_hit_rate_label.configure(text=pct_str)
        except Exception:
            pass
        try:
            self._summary_progress.set_value(rate, animate=True)
        except Exception:
            pass
        try:
            days_label = (i18n.to_fa_digits("۳۰")
                          if self._lang == "fa" else "30")
            sub_text = (
                f"{days_label} {i18n.t('days', self._lang)}"
                if self._lang == "en"
                else f"در {days_label} {i18n.t('days', self._lang)} اخیر")
            self._summary_subtitle.configure(text=sub_text)
        except Exception:
            pass

    def _refresh_goals(self) -> None:
        """Rebuild the goal cards for the active period."""
        # Clear old cards
        for child in self._goals_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._goal_cards = []
        # Hide empty state if shown
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        # Fetch goals for the active period
        try:
            all_goals = goal_service.list(only_active=True)
        except Exception:
            all_goals = []
        goals = [g for g in all_goals if g.get("period") == self._period]
        # Category map
        try:
            cats = db.category_list()
            cat_map = {c["id"]: c for c in cats}
        except Exception:
            cat_map = {}
        if not goals:
            self._empty_state = EmptyState(
                self._goals_frame,
                icon="goals",
                title=(i18n.t("emptyGoals", self._lang)
                       if "emptyGoals" in _keys()
                       else (i18n.t("noGoals", self._lang)
                             if "noGoals" in _keys()
                             else ("هدفی تعریف نشده"
                                    if self._lang == "fa"
                                    else "No goals yet"))),
                subtitle=("اولین هدفت را بساز"
                          if self._lang == "fa"
                          else "Create your first goal"),
                action_text=i18n.t("newGoal", self._lang),
                on_action=self._on_new_goal,
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build a card per goal
        for i, g in enumerate(goals):
            try:
                progress = goal_service.progress_for(g["id"])
                streak = streak_service.get(g["id"])
                try:
                    hit_rate = float(goal_service.goal_hit_rate(g["id"],
                                                                 days=30))
                except Exception:
                    hit_rate = 0.0
                last_7_days = self._compute_last_7_days(g)
                cat = cat_map.get(g.get("category_id")) if g.get(
                    "category_id") else None
            except Exception:
                continue
            card = _GoalItemCard(
                self._goals_frame,
                goal=g, progress=progress, streak=streak,
                hit_rate=hit_rate, last_7_days=last_7_days,
                category=cat, lang=self._lang,
                on_click=lambda gid=g["id"]: self._on_goal_tap(gid),
                on_long_press=lambda gid=g["id"]: self._on_goal_long(gid),
            )
            card.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 6, 6))
            self._goal_cards.append(card)

    def _refresh_badges(self) -> None:
        """Stub — actual badge rendering is on the dedicated Badges screen."""
        # Show a small "view badges" link
        for child in self._badges_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        from ..widgets.list_items import BadgeListItem
        try:
            from ...services import badge_service
            earned = badge_service.list_earned()
        except Exception:
            earned = []
        if not earned:
            ctk.CTkLabel(
                self._badges_frame,
                text=(i18n.t("noBadges", self._lang)
                      if "noBadges" in _keys()
                      else ("هنوز نشان‌ای کسب نکرده‌ای"
                             if self._lang == "fa"
                             else "No badges earned yet")),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_FAINT,
                anchor="e" if i18n.is_rtl(self._lang) else "w",
            ).grid(row=0, column=0, sticky="ew")
            return
        for i, b in enumerate(earned[:3]):
            try:
                item = BadgeListItem(
                    self._badges_frame,
                    name=(b.get("name_fa") if self._lang == "fa"
                           else b.get("name_en")) or "—",
                    description=(b.get("desc_fa") if self._lang == "fa"
                                  else b.get("desc_en")) or "",
                    tier=b.get("tier", "gold"),
                    icon_name=b.get("icon", "trophy"),
                    earned=True,
                    lang=self._lang,
                )
                item.grid(row=i, column=0, sticky="ew", pady=2)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _compute_last_7_days(self, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compute the last 7 days' minutes for `goal` as bar-chart data."""
        out: List[Dict[str, Any]] = []
        try:
            today = time_utils.today_iso()
            cat_id = goal.get("category_id")
            for i in range(6, -1, -1):
                day_iso = time_utils.add_days(today, -i)
                # Sum activity for that day (with goal's category)
                try:
                    total_sec = db.activity_sum_duration(
                        date_from=day_iso, date_to=day_iso,
                        category_id=cat_id,
                    )
                except Exception:
                    total_sec = 0
                minutes = int((total_sec or 0) // 60)
                # Day label: short weekday name in current language
                try:
                    label = time_utils.weekday_name(day_iso, self._lang)[:1]
                except Exception:
                    label = str(i)
                out.append({"label": label, "value": minutes,
                             "color": config.GOLD})
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def _on_new_goal(self) -> None:
        if self._app and hasattr(self._app, "open_goal_dialog"):
            try:
                self._app.open_goal_dialog()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.goal_dialog_requested")
        except Exception:
            pass

    def _on_goal_tap(self, goal_id: int) -> None:
        if self._app and hasattr(self._app, "open_goal_dialog"):
            try:
                self._app.open_goal_dialog(goal_id=goal_id)
            except Exception:
                pass

    def _on_goal_long(self, goal_id: int) -> None:
        """Long-press — confirm delete."""
        if self._app and hasattr(self._app, "confirm_delete"):
            try:
                msg = (f"{i18n.t('deleteGoalConfirm', self._lang)}?"
                       if "deleteGoalConfirm" in _keys()
                       else ("هدف حذف شود؟" if self._lang == "fa"
                              else "Delete this goal?"))
                self._app.confirm_delete(msg, lambda: self._do_delete(goal_id))
                return
            except Exception:
                pass
        # Fallback: just delete
        self._do_delete(goal_id)

    def _do_delete(self, goal_id: int) -> None:
        try:
            goal_service.delete(goal_id)
            if self._app and hasattr(self._app, "show_toast"):
                self._app.show_toast(i18n.t("goalDeleted", self._lang)
                                      if "goalDeleted" in _keys()
                                      else ("حذف شد" if self._lang == "fa"
                                             else "Deleted"))
        except Exception:
            pass
        self.refresh()

    def _on_period_change(self, label: str) -> None:
        """Segmented control callback — switch period."""
        # Reverse-lookup the period from the label
        labels_map = (_period_label("daily", self._lang),
                       _period_label("weekly", self._lang),
                       _period_label("monthly", self._lang))
        if label == labels_map[0]:
            self._period = "daily"
        elif label == labels_map[1]:
            self._period = "weekly"
        elif label == labels_map[2]:
            self._period = "monthly"
        self._refresh_goals()

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
    print("GoalsScreen module: summary + segmented + goal cards + badges.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
