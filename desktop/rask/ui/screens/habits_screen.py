"""
rask.ui.screens.habits_screen
=============================

Habit tracker screen — daily habit checklist + weekly grid + per-habit
streaks and completion rates.

Mirrors the *Habits* pattern from the web app.  Uses
:class:`rask.features.habits.HabitService` as the source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"عادت‌ها"`` with a "+ New Habit" button
    2. **Overall success-rate card** — ``"نرخ موفقیت"`` with the % of
       habits completed today + a mini bar chart of the last 7 days
    3. **Today section** — list of active habits with checkmark
       toggles for today (tap to toggle)
    4. **Weekly view** — 7 columns (days) × N rows (habits) grid
       with checkmarks.  Days are Persian weekday abbreviations.
    5. **Per-habit cards** — each habit gets a card with: name,
       streak (with flame icon), 30-day completion rate, mini bar
       chart, tap to edit, long-press for Edit / Archive / Delete.
    6. **Empty state** — ``"اولین عادتت را بساز"`` with a CTA.

Auto-refresh
------------
Subscribes to ``habit.added`` / ``habit.updated`` / ``habit.deleted`` /
``habit.logged`` / ``habit.unlogged`` / ``habit.streak_changed`` /
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
from ...features.habits import (
    habit_service, FREQ_DAILY, FREQ_WEEKLY, FREQ_3X_WEEK,
)
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
    DangerButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.badges import Chip
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.inputs import GoldEntry
from ..widgets.toggles import SegmentedControl
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.charts import Sparkline, BarChart
from ..widgets.dialogs import AlertDialog
from ..widgets.sheets import ActionSheet

__all__ = ["HabitsScreen"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

_WEEKDAY_ABBR_FA: List[str] = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
_WEEKDAY_ABBR_EN: List[str] = ["Sa", "Su", "Mo", "Tu", "We", "Th", "Fr"]

_FREQ_LABELS_FA: Dict[str, str] = {
    FREQ_DAILY: "روزانه",
    FREQ_WEEKLY: "هفتگی",
    FREQ_3X_WEEK: "۳ بار در هفته",
}
_FREQ_LABELS_EN: Dict[str, str] = {
    FREQ_DAILY: "Daily",
    FREQ_WEEKLY: "Weekly",
    FREQ_3X_WEEK: "3x / week",
}


def _weekday_abbr(weekday_sat_first: int, lang: str) -> str:
    """Return the abbreviation for a weekday.

    ``weekday_sat_first`` is 0=Sat..6=Fri (Persian convention).
    """
    if lang == "fa":
        return _WEEKDAY_ABBR_FA[weekday_sat_first % 7]
    return _WEEKDAY_ABBR_EN[weekday_sat_first % 7]


def _weekday_short_from_iso(iso: str, lang: str) -> str:
    """Get the weekday abbreviation for an ISO date."""
    try:
        from datetime import date
        py_wd = date.fromisoformat(iso[:10]).weekday()  # Mon=0..Sun=6
        # Convert to Sat-first: Sat=5, Sun=6, Mon=0..Fri=4
        sat_first = (py_wd + 2) % 7
        return _weekday_abbr(sat_first, lang)
    except Exception:
        return "—"


def _freq_label(freq: str, lang: str) -> str:
    if lang == "fa":
        return _FREQ_LABELS_FA.get(freq, freq)
    return _FREQ_LABELS_EN.get(freq, freq)


# =============================================================================
# === Habit cell widgets                                                     ===
# =============================================================================

class _TodayHabitRow(ctk.CTkFrame):
    """One row in the 'today' section: name + checkmark toggle."""

    def __init__(
        self,
        master: Any,
        habit: Dict[str, Any],
        completed: bool,
        streak: int,
        completion_rate: float,
        lang: str = "fa",
        on_toggle: Optional[Callable[[int, bool], Any]] = None,
        on_long_press: Optional[Callable[[int], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        super().__init__(master, **kwargs)
        self._habit = habit
        self._lang = lang
        self._on_toggle = on_toggle
        self._completed = completed
        self.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(lang)
        # Color stripe (leading in RTL)
        color = habit.get("color") or config.GOLD
        stripe = ctk.CTkFrame(self, width=4, fg_color=color)
        stripe.grid(row=0, column=1 if rtl else 0, sticky="ns",
                     padx=0, pady=8)
        # Checkbox (trailing in RTL)
        self._check_btn = ctk.CTkButton(
            self, text=("✓" if completed else ""),
            command=self._on_tap,
            width=36, height=36,
            fg_color=(config.GOLD if completed else config.SURFACE_HI),
            hover_color=config.GOLD_BRIGHT,
            text_color=config.MATTE_BLACK,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang="en"),
            corner_radius=config.RADIUS_PILL,
            border_width=2,
            border_color=(config.GOLD if completed
                           else config.SURFACE_HIGHER),
        )
        self._check_btn.grid(row=0, column=0 if rtl else 2,
                              padx=(8 if rtl else 0, 0 if rtl else 8),
                              pady=8)
        # Name + sub
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=0, column=1, sticky="ew", padx=8)
        name_frame.grid_columnconfigure(0, weight=1)
        name = habit.get("name", "—")
        ctk.CTkLabel(
            name_frame, text=name,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold",
                                    lang=lang),
            text_color=config.TEXT if completed else config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Sub: streak + completion rate
        sub_parts: List[str] = []
        if streak > 0:
            s_str = (i18n.to_fa_digits(str(streak))
                     if lang == "fa" else str(streak))
            sub_parts.append(f"🔥 {s_str}")
        pct = int(completion_rate * 100)
        pct_str = (i18n.to_fa_digits(str(pct)) + "٪"
                   if lang == "fa" else f"{pct}%")
        sub_parts.append(pct_str)
        sub_parts.append(_freq_label(habit.get("frequency", FREQ_DAILY),
                                       lang))
        ctk.CTkLabel(
            name_frame, text="  •  ".join(sub_parts),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w")
        # Long-press support
        if on_long_press is not None:
            self._long_press_job: Optional[Any] = None
            self._on_long_press = on_long_press
            self._check_btn.bind("<ButtonPress-1>",
                                  self._on_press, add="+")
            self._check_btn.bind("<ButtonRelease-1>",
                                  self._on_release, add="+")
            self.bind("<ButtonPress-1>", self._on_press, add="+")
            self.bind("<ButtonRelease-1>", self._on_release, add="+")
            for child in self.winfo_children():
                child.bind("<ButtonPress-1>", self._on_press, add="+")
                child.bind("<ButtonRelease-1>", self._on_release,
                            add="+")

    def _on_press(self, _event: Any) -> None:
        self._long_press_job = self.after(600, self._fire_long_press)

    def _on_release(self, _event: Any) -> None:
        if self._long_press_job is not None:
            try:
                self.after_cancel(self._long_press_job)
            except Exception:
                pass
            self._long_press_job = None

    def _fire_long_press(self) -> None:
        self._long_press_job = None
        if self._on_long_press is not None:
            try:
                self._on_long_press(int(self._habit.get("id") or 0))
            except Exception:
                pass

    def _on_tap(self) -> None:
        new_state = not self._completed
        self._completed = new_state
        try:
            self._check_btn.configure(
                text="✓" if new_state else "",
                fg_color=(config.GOLD if new_state
                           else config.SURFACE_HI),
                border_color=(config.GOLD if new_state
                               else config.SURFACE_HIGHER),
            )
        except Exception:
            pass
        if self._on_toggle is not None:
            try:
                self._on_toggle(int(self._habit.get("id") or 0),
                                  new_state)
            except Exception:
                pass


class _WeeklyCell(ctk.CTkButton):
    """One cell in the weekly grid: empty / checkmark / future-muted."""

    def __init__(
        self,
        master: Any,
        completed: bool,
        is_future: bool,
        is_today: bool,
        lang: str = "fa",
        on_tap: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._completed = completed
        self._is_future = is_future
        self._on_tap = on_tap
        if completed:
            fg = config.GOLD
            txt = "✓"
            tc = config.MATTE_BLACK
        elif is_future:
            fg = config.SURFACE
            txt = ""
            tc = config.TEXT_FAINT
        else:
            fg = config.SURFACE_HI
            txt = ""
            tc = config.TEXT_DIM
        bd = config.GOLD if is_today else config.SURFACE_HI
        super().__init__(
            master, text=txt, command=self._tapped,
            width=32, height=32,
            fg_color=fg, hover_color=config.GOLD_BRIGHT,
            text_color=tc,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang="en"),
            corner_radius=config.RADIUS_SM,
            border_width=2 if is_today else 1,
            border_color=bd,
        )

    def _tapped(self) -> None:
        if self._is_future:
            return
        if self._on_tap is not None:
            try:
                self._on_tap()
            except Exception:
                pass


# =============================================================================
# === HabitsScreen                                                           ===
# =============================================================================

class HabitsScreen(ctk.CTkFrame):
    """Habit tracker screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``confirm_delete(on_confirm)``
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
        self._today_rows: List[_TodayHabitRow] = []
        self._today_iso: str = time_utils.today_iso()
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
            self, title=self._tr("عادت‌ها", "Habits"),
            lang=self._lang, height=56,
            action_text=self._tr("+ عادت جدید", "+ New"),
            on_action=self._on_add_habit,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_overall_card()
        self._build_today_section()
        self._build_weekly_section()
        self._build_habits_detail()

    def _build_overall_card(self) -> None:
        """Success rate card at top."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Big % label
        self._overall_pct = ctk.CTkLabel(
            card.content, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._overall_pct.grid(row=0, column=0, padx=8)
        # Right side: label + sparkline
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=self._tr("نرخ موفقیت امروز", "Today's success rate"),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._overall_subtitle = ctk.CTkLabel(
            info, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._overall_subtitle.grid(row=1, column=0, sticky="e" if rtl
                                      else "w", pady=(2, 0))
        # Sparkline (last 7 days % completed)
        self._sparkline = Sparkline(
            card.content, data=[], width=120, height=36,
            color=config.GOLD, lang=self._lang,
        )
        self._sparkline.grid(row=0, column=2, padx=8)

    def _build_today_section(self) -> None:
        """Today's checklist section."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_SM, 0))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("امروز", "Today"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._today_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._today_frame.grid(row=1, column=0, sticky="ew",
                                 pady=(config.SPACE_SM, 0))
        self._today_frame.grid_columnconfigure(0, weight=1)

    def _build_weekly_section(self) -> None:
        """7-day weekly grid: header row of weekdays + habit rows."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_LG, 0))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("نمای هفتگی", "Weekly view"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        # Card to hold the grid
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_MD)
        card.grid(row=1, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        # Header row: name column + 7 day columns
        self._weekly_grid = ctk.CTkFrame(card.content,
                                           fg_color="transparent")
        self._weekly_grid.grid(row=0, column=0, sticky="ew")
        self._weekly_grid.grid_columnconfigure(0, weight=1)
        for i in range(1, 8):
            self._weekly_grid.grid_columnconfigure(i, weight=0,
                                                     uniform="day")
        # Empty placeholder — actual content built in refresh()
        self._weekly_placeholder = ctk.CTkLabel(
            self._weekly_grid, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        )

    def _build_habits_detail(self) -> None:
        """Per-habit detail cards section."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_LG, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("جزئیات عادت‌ها", "Habit details"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._details_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._details_frame.grid(row=1, column=0, sticky="ew",
                                   pady=(config.SPACE_SM, 0))
        self._details_frame.grid_columnconfigure(0, weight=1)
        # Empty state placeholder
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
            "habit.added", "habit.updated", "habit.deleted",
            "habit.logged", "habit.unlogged", "habit.streak_changed",
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
        self._refresh_job = self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render everything from the service state."""
        self._today_iso = time_utils.today_iso()
        self._refresh_overall()
        self._refresh_today_list()
        self._refresh_weekly_grid()
        self._refresh_details()

    def _refresh_overall(self) -> None:
        """Update the success-rate card."""
        try:
            today_data = habit_service.for_date(self._today_iso)
        except Exception:
            today_data = []
        total = len(today_data)
        done = sum(1 for d in today_data if d.get("completed_today"))
        pct = (done / total * 100) if total > 0 else 0.0
        pct_str = (i18n.to_fa_digits(str(int(pct))) + "٪"
                   if self._lang == "fa" else f"{int(pct)}%")
        try:
            self._overall_pct.configure(text=pct_str)
        except Exception:
            pass
        try:
            sub = (f"{i18n.to_fa_digits(str(done)) if self._lang == 'fa' else str(done)}"
                   f" / "
                   f"{i18n.to_fa_digits(str(total)) if self._lang == 'fa' else str(total)}"
                   f" {self._tr('انجام شده', 'done')}")
            self._overall_subtitle.configure(text=sub)
        except Exception:
            pass
        # Sparkline: last 7 days completion %
        try:
            from ...core.time_utils import range_days
            spark_values: List[float] = []
            start = time_utils.add_days(self._today_iso, -6)
            for d in range_days(start, self._today_iso):
                day_data = habit_service.for_date(d)
                t = len(day_data)
                dn = sum(1 for x in day_data if x.get("completed_today"))
                spark_values.append((dn / t) if t > 0 else 0.0)
            self._sparkline.set_data(spark_values)
        except Exception:
            pass

    def _refresh_today_list(self) -> None:
        """Rebuild the today checklist."""
        for child in self._today_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._today_rows = []
        try:
            today_data = habit_service.for_date(self._today_iso)
        except Exception:
            today_data = []
        if not today_data:
            EmptyState(
                self._today_frame, icon="check",
                title=self._tr("اولین عادتت را بساز",
                                "Create your first habit"),
                subtitle=self._tr("روی + بزن تا یک عادت جدید اضافه کنی",
                                    "Tap + to add a new habit"),
                action_text=self._tr("عادت جدید", "New habit"),
                on_action=self._on_add_habit,
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_LG)
            return
        for i, d in enumerate(today_data):
            habit = d.get("habit", {})
            row = _TodayHabitRow(
                self._today_frame, habit=habit,
                completed=bool(d.get("completed_today")),
                streak=int(d.get("streak", 0) or 0),
                completion_rate=float(d.get("completion_rate_30d", 0.0)
                                       or 0.0),
                lang=self._lang,
                on_toggle=self._on_toggle_habit,
                on_long_press=self._on_long_press,
            )
            row.grid(row=i, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 4))
            self._today_rows.append(row)

    def _refresh_weekly_grid(self) -> None:
        """Rebuild the 7-day weekly grid."""
        # Clear placeholder + grid children
        try:
            self._weekly_placeholder.grid_forget()
        except Exception:
            pass
        for child in self._weekly_grid.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        # Fetch data for the current week
        try:
            week_data = habit_service.for_week(self._today_iso)
        except Exception:
            week_data = {}
        # Sort dates (Sat..Fri)
        try:
            dates = sorted(week_data.keys())
        except Exception:
            dates = []
        if not dates:
            self._weekly_placeholder.configure(
                text=self._tr("عادتی برای نمایش وجود ندارد",
                                "No habits to display"))
            self._weekly_placeholder.grid(row=0, column=0, columnspan=8)
            return
        # Header row: empty cell + 7 weekday cells
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            self._weekly_grid, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
        ).grid(row=0, column=0, sticky="ew")
        for i, d in enumerate(dates):
            col = (7 - i) if rtl else (i + 1)
            label = _weekday_short_from_iso(d, self._lang)
            is_today = (d == self._today_iso)
            ctk.CTkLabel(
                self._weekly_grid, text=label,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=(config.GOLD if is_today else config.TEXT_DIM),
            ).grid(row=0, column=col, padx=2, pady=(0, 4))
        # For each habit, build a row
        try:
            first_day_data = week_data.get(dates[0], [])
            habits = [d.get("habit", {}) for d in first_day_data]
        except Exception:
            habits = []
        if not habits:
            self._weekly_placeholder.configure(
                text=self._tr("عادتی برای نمایش وجود ندارد",
                                "No habits to display"))
            self._weekly_placeholder.grid(row=1, column=0, columnspan=8)
            return
        for r, habit in enumerate(habits):
            grid_row = r + 1
            # Habit name (truncated)
            name = habit.get("name", "—")
            color = habit.get("color") or config.GOLD
            ctk.CTkLabel(
                self._weekly_grid, text=name[:14] + ("…" if len(name) > 14
                                                      else ""),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
            ).grid(row=grid_row, column=0, sticky="e" if rtl else "w",
                    padx=(0, 4))
            hid = int(habit.get("id") or 0)
            for i, d in enumerate(dates):
                col = (7 - i) if rtl else (i + 1)
                # Find this habit's status on this date
                completed = False
                day_list = week_data.get(d, [])
                for entry in day_list:
                    if int(entry.get("habit", {}).get("id") or 0) == hid:
                        completed = bool(entry.get("completed_today"))
                        break
                is_future = (d > self._today_iso)
                is_today = (d == self._today_iso)
                cell = _WeeklyCell(
                    self._weekly_grid, completed=completed,
                    is_future=is_future, is_today=is_today,
                    lang=self._lang,
                    on_tap=lambda _hid=hid, _d=d: self._on_weekly_tap(
                        _hid, _d),
                )
                cell.grid(row=grid_row, column=col, padx=2, pady=2)

    def _refresh_details(self) -> None:
        """Rebuild the per-habit detail cards."""
        for child in self._details_frame.winfo_children():
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
            today_data = habit_service.for_date(self._today_iso)
        except Exception:
            today_data = []
        if not today_data:
            self._empty_state = EmptyState(
                self._details_frame, icon="leaf",
                title=self._tr("عادتی ثبت نشده",
                                "No habits yet"),
                subtitle=self._tr("برای شروع یک عادت جدید بساز",
                                    "Create a new habit to begin"),
                action_text=self._tr("عادت جدید", "New habit"),
                on_action=self._on_add_habit,
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                     pady=config.SPACE_LG)
            return
        for i, d in enumerate(today_data):
            habit = d.get("habit", {})
            card = self._make_habit_detail_card(habit, d)
            card.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))

    def _make_habit_detail_card(self, habit: Dict[str, Any],
                                  data: Dict[str, Any]) -> Card:
        """A per-habit detail card with streak + 30-day bar chart."""
        card = Card(self._details_frame, lang=self._lang,
                     padding=config.SPACE_MD,
                     on_click=lambda _hid=habit.get("id"):
                     self._on_edit_habit(int(_hid or 0)))
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Color stripe
        color = habit.get("color") or config.GOLD
        stripe = ctk.CTkFrame(card.content, width=4, fg_color=color)
        stripe.grid(row=0, column=1 if rtl else 0, sticky="ns",
                     padx=0, pady=4)
        # Info column
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        name = habit.get("name", "—")
        ctk.CTkLabel(
            info, text=name,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Streak + completion + frequency
        streak = int(data.get("streak", 0) or 0)
        rate = float(data.get("completion_rate_30d", 0.0) or 0.0)
        rate_pct = int(rate * 100)
        rate_str = (i18n.to_fa_digits(str(rate_pct)) + "٪"
                    if self._lang == "fa" else f"{rate_pct}%")
        s_str = (i18n.to_fa_digits(str(streak))
                 if self._lang == "fa" else str(streak))
        sub = (f"🔥 {s_str}  •  "
               f"{self._tr('نرخ تکمیل', 'Completion')}: {rate_str}  •  "
               f"{_freq_label(habit.get('frequency', FREQ_DAILY),
                                self._lang)}")
        ctk.CTkLabel(
            info, text=sub,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))
        # 30-day mini bar chart
        try:
            trend = habit_service.trend(int(habit.get("id") or 0),
                                          days=30)
            bar_data = [
                {"label": "", "value": (1.0 if t.get("completed") else 0.0),
                 "color": color}
                for t in trend
            ]
            chart = BarChart(
                info, data=bar_data, width=260, height=36,
                max_value=1.0, lang=self._lang,
            )
            chart.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        except Exception:
            pass
        return card

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_toggle_habit(self, habit_id: int, completed: bool) -> None:
        """Toggle the habit's completion for today."""
        try:
            if completed:
                habit_service.log_completion(habit_id,
                                               date_iso=self._today_iso)
            else:
                habit_service.unlog_completion(habit_id,
                                                date_iso=self._today_iso)
        except Exception:
            pass
        # Refresh immediately so streak / overall update
        self._schedule_refresh()

    def _on_weekly_tap(self, habit_id: int, date_iso: str) -> None:
        """Tap a weekly cell — toggle completion for that date."""
        try:
            log = habit_service.get_log(habit_id, date_iso)
            if log and log.completed:
                habit_service.unlog_completion(habit_id,
                                                date_iso=date_iso)
            else:
                habit_service.log_completion(habit_id,
                                               date_iso=date_iso)
        except Exception:
            pass
        self._schedule_refresh()

    def _on_long_press(self, habit_id: int) -> None:
        """Long-press → action sheet (Edit / Archive / Delete)."""
        actions = [
            (self._tr("ویرایش", "Edit"),
             lambda: self._on_edit_habit(habit_id)),
            (self._tr("آرشیو", "Archive"),
             lambda: self._on_archive_habit(habit_id)),
            (self._tr("حذف", "Delete"),
             lambda: self._on_delete_habit(habit_id)),
        ]
        try:
            ActionSheet(
                self, title=self._tr("عملیات عادت", "Habit actions"),
                actions=actions, lang=self._lang,
            )
        except Exception:
            # Fallback to alert
            AlertDialog(
                self, title=self._tr("عملیات عادت", "Habit actions"),
                message=self._tr("ویرایش / آرشیو / حذف",
                                  "Edit / Archive / Delete"),
                lang=self._lang,
            )

    def _on_add_habit(self) -> None:
        """Open a simple add-habit dialog."""
        self._show_add_dialog()

    def _show_add_dialog(self) -> None:
        """Show an add-habit dialog (uses AlertDialog as a fallback)."""
        # Build a small inline dialog using CTkToplevel
        try:
            dlg = ctk.CTkToplevel(self)
            dlg.title(self._tr("عادت جدید", "New habit"))
            dlg.geometry("380x300")
            dlg.configure(fg_color=config.MATTE_BLACK)
            dlg.transient(self)
            dlg.grab_set()
            # Center
            dlg.after(50, lambda: dlg.focus_force())
            rtl = i18n.is_rtl(self._lang)
            # Title
            ctk.CTkLabel(
                dlg, text=self._tr("عادت جدید", "New habit"),
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).pack(pady=(20, 8))
            # Name entry
            name_entry = GoldEntry(
                dlg, lang=self._lang,
                placeholder=self._tr("نام عادت", "Habit name"),
            )
            name_entry.pack(fill="x", padx=24, pady=4)
            # Frequency segmented
            ctk.CTkLabel(
                dlg, text=self._tr("تناوب", "Frequency"),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).pack(anchor="e" if rtl else "w", padx=24, pady=(8, 0))
            freq_var = ctk.StringVar(value=FREQ_DAILY)
            freq_seg = SegmentedControl(
                dlg, values=[FREQ_DAILY, FREQ_WEEKLY, FREQ_3X_WEEK],
                lang=self._lang,
            )
            freq_seg.set(FREQ_DAILY)
            freq_seg.pack(fill="x", padx=24, pady=4)
            # Buttons row
            btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
            btn_row.pack(fill="x", padx=24, pady=(16, 8))

            def _submit() -> None:
                name = name_entry.get().strip()
                if not name:
                    return
                try:
                    habit_service.add_habit(
                        name=name,
                        frequency=str(freq_seg.get()) or FREQ_DAILY,
                    )
                    self._show_toast(self._tr("عادت اضافه شد",
                                                "Habit added"))
                except Exception:
                    self._show_toast(self._tr("خطا در افزودن",
                                                "Error adding"))
                dlg.destroy()
                self._schedule_refresh()

            GoldButton(
                btn_row, text=self._tr("افزودن", "Add"),
                command=_submit, lang=self._lang, height=36,
            ).pack(side="right" if rtl else "left", fill="x",
                    expand=True, padx=4)
            GhostButton(
                btn_row, text=self._tr("انصراف", "Cancel"),
                command=dlg.destroy, lang=self._lang, height=36,
            ).pack(side="right" if rtl else "left", fill="x",
                    expand=True, padx=4)
            name_entry.bind("<Return>", lambda _e: _submit())
        except Exception:
            self._show_toast(self._tr("خطا در باز کردن دیالوگ",
                                        "Dialog error"))

    def _on_edit_habit(self, habit_id: int) -> None:
        """Edit a habit — for now, just show its details."""
        try:
            h = habit_service.get_habit(habit_id)
            if h is None:
                return
            name = h.name
            freq = _freq_label(h.frequency, self._lang)
            streak = habit_service.streak(habit_id)
            s_str = (i18n.to_fa_digits(str(streak))
                     if self._lang == "fa" else str(streak))
            msg = (
                f"{name}\n\n"
                f"{self._tr('تناوب', 'Frequency')}: {freq}\n"
                f"{self._tr('زنجیره فعلی', 'Current streak')}: {s_str}\n"
                f"{self._tr('بهترین زنجیره', 'Best streak')}: "
                f"{i18n.to_fa_digits(str(habit_service.best_streak(habit_id))) if self._lang == 'fa' else str(habit_service.best_streak(habit_id))}\n"
            )
            AlertDialog(
                self, title=self._tr("جزئیات عادت", "Habit details"),
                message=msg, lang=self._lang,
                ok_text=self._tr("بستن", "Close"),
            )
        except Exception:
            pass

    def _on_archive_habit(self, habit_id: int) -> None:
        try:
            habit_service.update_habit(habit_id, active=False)
            self._show_toast(self._tr("عادت آرشیو شد",
                                        "Habit archived"))
        except Exception:
            pass
        self._schedule_refresh()

    def _on_delete_habit(self, habit_id: int) -> None:
        """Confirm + delete a habit."""
        try:
            h = habit_service.get_habit(habit_id)
            if h is None:
                return
            name = h.name
        except Exception:
            name = ""

        def _do_delete() -> None:
            try:
                habit_service.delete_habit(habit_id)
                self._show_toast(self._tr("عادت حذف شد",
                                            "Habit deleted"))
            except Exception:
                pass
            self._schedule_refresh()

        # Use app.confirm_delete if available, else just delete
        if self._app and hasattr(self._app, "confirm_delete"):
            try:
                self._app.confirm_delete(
                    on_confirm=_do_delete,
                    name=name,
                )
                return
            except Exception:
                pass
        _do_delete()

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
    print("HabitsScreen module: success-rate card + today list + "
          "weekly grid + per-habit cards + add/edit/archive/delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
