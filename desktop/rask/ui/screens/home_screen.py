"""
rask.ui.screens.home_screen
===========================

The main home screen — the landing view after unlock.

Mirrors ``web/index.html`` ``#screen-home`` and the corresponding
``renderHome`` function in ``web/js/app.js``.

Layout (top-to-bottom, RTL Persian):
    1. **Greeting header** — "صبح بخیر / عصر بخیر / شب بخیر" with the
       user's name (if set) and a circular avatar (initials or image)
    2. **Date label** — Persian (Jalali) long-format date, e.g.
       "پنجشنبه ۱۴ اسفند ۱۴۰۳"
    3. **Live timer card** (conditional) — if a stopwatch is running,
       a gold-bordered card with title, big tabular-numeric time, and
       pause / stop / cancel buttons.  Subscribes to ``timer.*`` events.
    4. **Today summary card** — large progress ring showing the % of
       the daily goal achieved today, with the total focus time and
       the goal target.  Three stat cards below show:
            * today's focus time
            * current streak (days)
            * daily goal progress %
    5. **Quick templates** — horizontal scroll of template chips.
       Tapping a chip starts a stopwatch with that template's title
       and category.
    6. **Recent activities** — vertical list of the last 5 activities,
       each with a category color stripe, title, duration, and
       relative time.  Tap to edit (calls ``app.open_activity_dialog``).
    7. **FAB** — gold ``"+"`` floating action button anchored to the
       bottom-trailing corner (above the bottom nav).  Calls
       ``app.open_quick_log()``.

Auto-refresh
------------
The screen subscribes to:
    * ``activity.added`` / ``activity.updated`` / ``activity.deleted``
    * ``timer.started`` / ``timer.paused`` / ``timer.resumed`` / ``timer.stopped``
    * ``timer.tick`` — updates the live timer card every second
    * ``goal.added`` / ``goal.updated`` / ``goal.deleted``
    * ``streak.incremented`` / ``streak.reset``
    * ``template.added`` / ``template.updated`` / ``template.deleted``
    * ``language.changed``
    * ``settings.changed``

All subscriptions are torn down in ``destroy()``.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

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
    activity_service, goal_service, streak_service, stats_service,
    template_service, badge_service, timer_service, settings_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, FabButton, PillButton,
)
from ..widgets.cards import Card, StatCard, ActivityCard, SummaryCard
from ..widgets.badges import Chip, StreakBadge, CategoryBadge
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.avatars import Avatar
from ..widgets.progress_ring import ProgressRing
from ..widgets.live_timer import LiveTimer
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.pull_to_refresh import PullToRefresh

__all__ = ["HomeScreen"]


# =============================================================================
# === HomeScreen                                                            ===
# =============================================================================

class HomeScreen(ctk.CTkFrame):
    """The main home screen.

    Parameters
    ----------
    parent
        Parent widget (the app shell's main content frame).
    app
        The main application object.  The screen uses the following
        optional methods on ``app`` if present:
            * ``open_quick_log()``
            * ``open_activity_dialog(activity_id)``
            * ``open_template_dialog()``
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
        self._recent_activity_cards: List[ctk.CTkBaseClass] = []
        self._template_chips: List[ctk.CTkBaseClass] = []
        self._build()
        self._subscribe_events()
        # Defer first refresh so the widget is mapped
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the home screen: scroll area + FAB overlay."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        # Scrollable content area
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK,
            corner_radius=0,
        )
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # FAB
        self._fab = FabButton(
            self, icon_name="plus",
            command=self._on_fab,
            lang=self._lang,
        )
        # Place FAB in the bottom-trailing corner (above the nav)
        # RTL: trailing = left; LTR: trailing = right
        rtl = i18n.is_rtl(self._lang)
        fab_side = "left" if rtl else "right"
        # Use place after the widget is mapped
        self.after(100, lambda: self._place_fab(fab_side))

        # Build content sections (in order)
        self._section_row = 0
        self._build_greeting()
        self._build_live_timer()
        self._build_today_summary()
        self._build_quick_templates()
        self._build_recent_activities()

    def _place_fab(self, side: str) -> None:
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            fab_size = config.FAB_SIZE
            x = 20 if side == "left" else w - fab_size - 20
            y = h - fab_size - 80  # above bottom nav (64px)
            self._fab.place(x=x, y=y)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_greeting(self) -> None:
        """Top greeting header: avatar + greeting + date."""
        header = ctk.CTkFrame(self._scroll, fg_color="transparent")
        header.grid(row=self._next_row(), column=0, sticky="ew",
                     padx=config.SPACE_LG, pady=(config.SPACE_LG,
                                                  config.SPACE_SM))
        header.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Avatar (trailing side in RTL)
        avatar_col = 0 if rtl else 2
        self._avatar = Avatar(
            header, size=44, text=self._user_initials(),
            color=None, ring_color=config.GOLD, ring_width=2,
        )
        self._avatar.grid(row=0, column=avatar_col, padx=4, sticky="nsew")
        # Greeting + date (middle column)
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=1, sticky="ew", padx=8)
        title_frame.grid_columnconfigure(0, weight=1)
        self._greeting_label = ctk.CTkLabel(
            title_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._greeting_label.grid(row=0, column=0, sticky="ew")
        self._date_label = ctk.CTkLabel(
            title_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._date_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Stats icon button (leading side in RTL) — opens insights tab
        insights_col = 2 if rtl else 0
        insights_btn = IconButton(
            header, icon_name="chart_bar",
            command=lambda: self._app_switch_tab("insights"),
            size=40, lang=self._lang,
        )
        insights_btn.grid(row=0, column=insights_col, padx=4, sticky="nsew")

    def _build_live_timer(self) -> None:
        """Live timer card — hidden until a stopwatch is running."""
        container = ctk.CTkFrame(self._scroll, fg_color="transparent")
        container.grid(row=self._next_row(), column=0, sticky="ew",
                        padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        container.grid_columnconfigure(0, weight=1)
        self._timer_container = container
        # LiveTimer auto-hides itself when no timer is running
        try:
            self._live_timer = LiveTimer(
                container, service=timer_service, lang=self._lang,
                on_stopped=self._on_timer_stopped,
            )
            self._live_timer.grid(row=0, column=0, sticky="ew")
        except Exception:
            self._live_timer = None

    def _build_today_summary(self) -> None:
        """Today summary: ring card + 3 stat cards."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM,
                                                   config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        # Ring card — large ring + total + goal
        ring_card = Card(section, lang=self._lang,
                          padding=config.SPACE_LG)
        ring_card.grid(row=0, column=0, sticky="ew")
        ring_card.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Ring (leading side in RTL)
        ring_col = 0 if rtl else 2
        self._today_ring = ProgressRing(
            ring_card.content, progress=0.0, size=120,
            line_width=10, show_percentage=False,
            animated=True, lang=self._lang,
        )
        self._today_ring.grid(row=0, column=ring_col, padx=8)
        # Info column (trailing side in RTL)
        info_col = 1 if rtl else 1
        info_frame = ctk.CTkFrame(ring_card.content, fg_color="transparent")
        info_frame.grid(row=0, column=info_col, sticky="ew", padx=8)
        info_frame.grid_columnconfigure(0, weight=1)
        # Subtitle
        ctk.CTkLabel(
            info_frame, text=i18n.t("today", self._lang),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Total focus time (big gold)
        self._today_total_label = ctk.CTkLabel(
            info_frame, text="۰ " + ( "دقیقه" if self._lang == "fa" else "min"),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._today_total_label.grid(row=1, column=0, sticky="ew",
                                       pady=(2, 0))
        # Goal target
        self._today_goal_label = ctk.CTkLabel(
            info_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._today_goal_label.grid(row=2, column=0, sticky="ew",
                                      pady=(2, 0))
        # Streak
        self._today_streak_label = ctk.CTkLabel(
            info_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._today_streak_label.grid(row=3, column=0, sticky="ew",
                                        pady=(4, 0))

        # 3 stat cards in a row
        stats_row = ctk.CTkFrame(section, fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew", pady=(config.SPACE_MD,
                                                             0))
        for i in range(3):
            stats_row.grid_columnconfigure(i, weight=1, uniform="stat")
        self._stat_cards: List[StatCard] = []
        labels = [
            i18n.t("card_today_focus", self._lang) if "card_today_focus" in _keys()
            else ("تمرکز امروز" if self._lang == "fa" else "Today focus"),
            i18n.t("card_streak", self._lang) if "card_streak" in _keys()
            else ("زنجیره" if self._lang == "fa" else "Streak"),
            i18n.t("card_goal_progress", self._lang) if "card_goal_progress" in _keys()
            else ("پیشرفت هدف" if self._lang == "fa" else "Goal %"),
        ]
        for i, label in enumerate(labels):
            card = StatCard(
                stats_row, label=label, value="—",
                lang=self._lang,
                padding=config.SPACE_MD,
            )
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0
                                                              else 4, 4))
            self._stat_cards.append(card)

    def _build_quick_templates(self) -> None:
        """Quick templates horizontal chip scroll."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # Section title
        title_row = ctk.CTkFrame(section, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            title_row, text=i18n.t("quickTemplates", self._lang),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # "All templates" link (trailing side in RTL)
        TextButton(
            title_row, text=i18n.t("all", self._lang),
            command=lambda: self._app_switch_tab("templates")
            if self._app_has("switch_tab") else None,
            lang=self._lang, height=28,
            font_size=config.FONT_SIZE_CAPTION,
            color=config.GOLD,
        ).grid(row=0, column=1, sticky="e" if rtl else "w")
        # Horizontal chip strip
        self._templates_strip = ctk.CTkFrame(section, fg_color="transparent")
        self._templates_strip.grid(row=1, column=0, sticky="ew",
                                    pady=(config.SPACE_SM, 0))
        self._templates_strip.grid_columnconfigure(0, weight=1)
        # Use a CTkScrollableFrame for horizontal scroll
        self._templates_row = ctk.CTkScrollableFrame(
            self._templates_strip, fg_color="transparent",
            orientation="horizontal", height=44,
        )
        self._templates_row.grid(row=0, column=0, sticky="ew")
        self._templates_row.grid_columnconfigure(0, weight=1)

    def _build_recent_activities(self) -> None:
        """Recent activities list."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        # Section title
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=i18n.t("recentActivities", self._lang),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Container for activity cards
        self._recent_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._recent_frame.grid(row=1, column=0, sticky="ew",
                                 pady=(config.SPACE_SM, 0))
        self._recent_frame.grid_columnconfigure(0, weight=1)
        # Empty-state placeholder (shown when no activities)
        self._empty_state: Optional[EmptyState] = None

    def _next_row(self) -> int:
        """Return the next available grid row in the scroll frame."""
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        """Wire up event_bus subscriptions for auto-refresh."""
        bus = event_bus.bus
        events = [
            "activity.added",
            "activity.updated",
            "activity.deleted",
            "goal.added",
            "goal.updated",
            "goal.deleted",
            "streak.incremented",
            "streak.reset",
            "template.added",
            "template.updated",
            "template.deleted",
            "template.used",
            "language.changed",
            "data.imported",
            "data.cleared",
        ]
        for ev in events:
            try:
                bus.subscribe(ev, self._on_data_changed)
                self._subscriptions.append((ev, self._on_data_changed))
            except Exception:
                pass
        # Timer events use a more granular handler
        for ev in ("timer.started", "timer.paused", "timer.resumed",
                    "timer.stopped"):
            try:
                bus.subscribe(ev, self._on_timer_event)
                self._subscriptions.append((ev, self._on_timer_event))
            except Exception:
                pass

    def _unsubscribe_events(self) -> None:
        """Tear down all event_bus subscriptions."""
        bus = event_bus.bus
        for ev, cb in self._subscriptions:
            try:
                bus.unsubscribe(ev, cb)
            except Exception:
                pass
        self._subscriptions.clear()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        """Generic data-change handler — schedule a refresh."""
        self._schedule_refresh()

    def _on_timer_event(self, *args: Any, **kwargs: Any) -> None:
        """Timer state change — refresh only the timer card + today total."""
        # LiveTimer self-refreshes on its own; we just need to refresh
        # the today-total when a stopwatch is saved.
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        """Debounce refreshes so rapid bursts of events don't thrash."""
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Refresh — re-render all data
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render all sections with the latest data."""
        self._refresh_greeting()
        self._refresh_today_summary()
        self._refresh_quick_templates()
        self._refresh_recent_activities()

    def _refresh_greeting(self) -> None:
        """Update greeting + date + avatar."""
        # Greeting based on local hour
        try:
            hour = int(time_utils.now_iso_local()[11:13])
        except Exception:
            hour = 0
        if hour < 12:
            g_key = "goodMorning"
        elif hour < 18:
            g_key = "goodAfternoon"
        else:
            g_key = "goodEvening"
        greeting = i18n.t(g_key, self._lang)
        # Append user name if set
        try:
            user_name = settings_service.user_name() or ""
        except Exception:
            user_name = ""
        if user_name:
            greeting = f"{greeting}، {user_name}"
        try:
            self._greeting_label.configure(text=greeting)
        except Exception:
            pass
        # Date label — Persian (Jalali) long format
        try:
            iso = time_utils.today_iso()
            date_str = jalali.format_jalali(iso, fmt="long", lang=self._lang)
            self._date_label.configure(text=date_str)
        except Exception:
            pass
        # Avatar — update initials
        try:
            initials = (user_name[:2].upper() if user_name else "R")
            # Re-create avatar content (Avatar doesn't expose setter)
            # Simplest: just leave as-is — initials rarely change.
            pass
        except Exception:
            pass

    def _refresh_today_summary(self) -> None:
        """Update today's progress ring + total + goal + streak + stat cards."""
        # Today's total focus seconds
        try:
            total_sec = int(activity_service.today_total() or 0)
        except Exception:
            total_sec = 0
        # Find daily goal (any-category first, else first daily goal)
        try:
            goals = goal_service.list(only_active=True)
            daily_goal = next(
                (g for g in goals
                 if g.get("period") == "daily" and not g.get("category_id")),
                None,
            )
            if daily_goal is None:
                daily_goal = next(
                    (g for g in goals if g.get("period") == "daily"),
                    None,
                )
        except Exception:
            daily_goal = None
        target_sec = (daily_goal.get("target_minutes", 0) * 60
                       if daily_goal else config.DEFAULT_GOAL_MINUTES * 60)
        progress = (total_sec / target_sec) if target_sec > 0 else 0.0
        progress = max(0.0, min(1.0, progress))
        # Ring
        try:
            self._today_ring.set_progress(progress, animate=True)
        except Exception:
            pass
        # Total time label
        try:
            total_str = time_utils.seconds_to_human(total_sec, lang=self._lang)
            self._today_total_label.configure(text=total_str)
        except Exception:
            pass
        # Goal label
        try:
            if daily_goal:
                target_str = time_utils.seconds_to_human(
                    target_sec, lang=self._lang)
                goal_text = (f"{i18n.t('goal', self._lang)}: {target_str}"
                             if self._lang == "en"
                             else f"{i18n.t('goal', self._lang)}: {target_str}")
                self._today_goal_label.configure(text=goal_text)
            else:
                # No goal set — show a hint
                hint = ("هدف روزانه تعیین کن" if self._lang == "fa"
                        else "Set a daily goal")
                self._today_goal_label.configure(text=hint)
        except Exception:
            pass
        # Streak label — find the longest current streak across all goals
        try:
            streaks = []
            for g in (goals if 'goals' in locals() else []):
                try:
                    s = streak_service.get(g["id"])
                    streaks.append(int(s.get("current", 0)))
                except Exception:
                    pass
            max_streak = max(streaks) if streaks else 0
            if max_streak > 0:
                if self._lang == "fa":
                    streak_text = (f"🔥 {i18n.t('streak', self._lang)}: "
                                    f"{i18n.to_fa_digits(str(max_streak))} "
                                    f"{i18n.t('days', self._lang)}")
                else:
                    streak_text = (f"🔥 {i18n.t('streak', self._lang)}: "
                                    f"{max_streak} {i18n.t('days', self._lang)}")
                self._today_streak_label.configure(text=streak_text)
            else:
                self._today_streak_label.configure(text="")
        except Exception:
            pass
        # 3 stat cards
        try:
            # Card 1: today focus time
            self._stat_cards[0].set_value(
                time_utils.seconds_to_human(total_sec, lang=self._lang))
            # Card 2: streak (current best)
            streak_val = (max_streak if 'max_streak' in locals()
                          else 0)
            streak_str = (i18n.to_fa_digits(str(streak_val))
                          if self._lang == "fa" else str(streak_val))
            unit = (i18n.t("days", self._lang)
                    if streak_val > 0 else "—")
            self._stat_cards[1].set_value(
                streak_str if streak_val == 0 else f"{streak_str} {unit}")
            # Card 3: goal %
            pct = int(progress * 100)
            pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                       if self._lang == "fa" else f"{pct}%")
            self._stat_cards[2].set_value(pct_str)
        except Exception:
            pass

    def _refresh_quick_templates(self) -> None:
        """Rebuild the horizontal templates chip strip."""
        # Clear old chips
        for child in self._templates_row.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._template_chips = []
        # Fetch templates
        try:
            templates = template_service.list(include_archived=False)
        except Exception:
            templates = []
        if not templates:
            # Show a "no templates" hint chip
            hint_text = (f"+ {i18n.t('addTemplate', self._lang)}"
                         if "addTemplate" in _keys()
                         else ("+ قالب جدید" if self._lang == "fa"
                                else "+ Add template"))
            chip = PillButton(
                self._templates_row, text=hint_text,
                command=self._on_add_template,
                lang=self._lang, height=36,
                color=config.SURFACE_HI,
                text_color=config.GOLD,
                font_size=config.FONT_SIZE_SMALL,
            )
            chip.pack(side="right" if i18n.is_rtl(self._lang)
                       else "left", padx=4, pady=4)
            self._template_chips.append(chip)
            return
        # Build chips
        rtl = i18n.is_rtl(self._lang)
        for t in templates[:8]:  # cap at 8 visible
            title = t.get("title", "—")
            t_id = t.get("id")
            chip = PillButton(
                self._templates_row, text=title,
                command=lambda tid=t_id: self._on_template_tap(tid),
                lang=self._lang, height=36,
                color=config.CHARCOAL,
                text_color=config.TEXT,
                font_size=config.FONT_SIZE_SMALL,
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=4)
            self._template_chips.append(chip)

    def _refresh_recent_activities(self) -> None:
        """Rebuild the recent activities list."""
        # Clear old cards
        for child in self._recent_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._recent_activity_cards = []
        # Fetch recent activities (last 5)
        try:
            recent = activity_service.recent(limit=5)
        except Exception:
            recent = []
        # Hide old empty state if any
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        if not recent:
            # Show empty state
            self._empty_state = EmptyState(
                self._recent_frame,
                icon="clock",
                title=(i18n.t("emptyActivities", self._lang)
                       if "emptyActivities" in _keys()
                       else (i18n.t("noActivities", self._lang)
                             if "noActivities" in _keys()
                             else ("هنوز فعالیتی ثبت نشده"
                                    if self._lang == "fa"
                                    else "No activities yet"))),
                subtitle=("برای شروع دکمه + را بزن"
                          if self._lang == "fa"
                          else "Tap + to start"),
                action_text=i18n.t("quickLog", self._lang)
                if "quickLog" in _keys()
                else ("ثبت سریع" if self._lang == "fa" else "Quick log"),
                on_action=self._on_fab,
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build activity cards
        rtl = i18n.is_rtl(self._lang)
        # Category map
        try:
            cats = db.category_list()
            cat_map = {c["id"]: c for c in cats}
        except Exception:
            cat_map = {}
        for i, a in enumerate(recent):
            cat_id = a.get("category_id")
            cat = cat_map.get(cat_id) if cat_id else None
            if cat:
                cat_name = (cat.get("name_fa") if self._lang == "fa"
                             else cat.get("name_en")) or "—"
                cat_color = cat.get("color") or config.GOLD
            else:
                cat_name = "—"
                cat_color = config.GOLD
            # Duration
            try:
                duration_sec = int(a.get("duration_sec", 0) or 0)
                duration_str = time_utils.seconds_to_human(
                    duration_sec, lang=self._lang)
            except Exception:
                duration_str = "—"
            # Time (relative)
            try:
                date_iso = a.get("date_iso") or ""
                start_iso = a.get("start_ts") or ""
                ref = start_iso or (date_iso + "T00:00:00")
                time_str = time_utils.format_relative(ref, lang=self._lang)
            except Exception:
                time_str = ""
            # Title
            title = a.get("title") or "—"
            # Notes preview (truncated)
            notes = (a.get("notes") or "")[:80]
            card = ActivityCard(
                self._recent_frame,
                title=title,
                category_name=cat_name,
                category_color=cat_color,
                duration=duration_str,
                time_str=time_str,
                notes=notes,
                lang=self._lang,
                on_click=lambda aid=a.get("id"): self._on_activity_tap(aid),
            )
            card.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            self._recent_activity_cards.append(card)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def _on_fab(self) -> None:
        """FAB tap — open the quick-log dialog."""
        if self._app and hasattr(self._app, "open_quick_log"):
            try:
                self._app.open_quick_log()
                return
            except Exception:
                pass
        # Fallback: publish a ui event
        try:
            event_bus.bus.publish("ui.quick_log_requested")
        except Exception:
            pass

    def _on_template_tap(self, template_id: int) -> None:
        """Template chip tap — start a stopwatch with that template."""
        try:
            t = template_service.get(template_id)
            if not t:
                return
            title = t.get("title", "Timer")
            category_id = t.get("category_id")
            timer_service.start(title, category_id)
            # Show a toast
            if self._app and hasattr(self._app, "show_toast"):
                msg = (f"{i18n.t('recording', self._lang)}: {title}"
                       if self._lang == "fa"
                       else f"{i18n.t('recording', self._lang)}: {title}")
                self._app.show_toast(msg)
        except Exception:
            pass

    def _on_add_template(self) -> None:
        """'Add template' chip — open the template dialog."""
        if self._app and hasattr(self._app, "open_template_dialog"):
            try:
                self._app.open_template_dialog()
            except Exception:
                pass

    def _on_activity_tap(self, activity_id: int) -> None:
        """Activity card tap — open the activity edit dialog."""
        if self._app and hasattr(self._app, "open_activity_dialog"):
            try:
                self._app.open_activity_dialog(activity_id)
            except Exception:
                pass

    def _on_timer_stopped(self, payload: dict) -> None:
        """LiveTimer stopped callback — refresh today total."""
        self._schedule_refresh()

    def _app_switch_tab(self, tab: str) -> None:
        """Helper — call app.switch_tab(tab) if available."""
        if self._app and hasattr(self._app, "switch_tab"):
            try:
                self._app.switch_tab(tab)
            except Exception:
                pass

    def _app_has(self, method: str) -> bool:
        return bool(self._app) and hasattr(self._app, method)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _user_initials(self) -> str:
        try:
            name = settings_service.user_name() or ""
        except Exception:
            name = ""
        if not name:
            return "R"
        parts = [p for p in name.strip().split() if p]
        if not parts:
            return "R"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return "".join(p[0].upper() for p in parts[:2])

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
# === Module-level helpers                                                   ===
# =============================================================================

def _keys() -> List[str]:
    """Return the list of i18n keys for the current language (cached)."""
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
    print("HomeScreen module: greeting + ring + templates + recent + FAB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
