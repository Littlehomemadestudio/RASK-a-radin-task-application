"""
rask.ui.screens.calendar_screen
===============================

Calendar screen — month-view calendar with intensity heatmap, day
detail panel, week view, free-time finder, and busiest/quietest day
cards.

Mirrors the *Calendar* view from the web app.  Uses
:class:`rask.features.calendar_integration.CalendarService` as the
source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"تقویم"`` with calendar system toggle
       (Jalali/Gregorian segmented control)
    2. **Calendar grid** — large month-view grid
       (uses the CalendarGrid widget):
       • Each day cell shows: day number, total minutes, mini category
         color dots, intensity background
       • Tap day → see day detail below
    3. **Day detail panel** (below calendar):
       • Selected date (large, Persian long format)
       • Total time
       • Activity timeline (vertical list with start times)
       • By category breakdown
       • Mood/energy if journal entry exists
       • Add activity button
    4. **View toggle** — Month / Week segmented control
       • Week view: 7-day columns with hour-by-hour activity blocks
    5. **Jump to today** button
    6. **Free time finder** — ``"۱۵ دقیقه وقت آزاد پیدا کن"``
       button + result list
    7. **Busiest/quietest day cards** — for the current month

Auto-refresh
------------
Subscribes to ``activity.added`` / ``activity.updated`` /
``activity.deleted`` / ``journal.added`` / ``journal.updated`` /
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
from ... import database as db
from ...features.calendar_integration import calendar_service
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.toggles import SegmentedControl
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.calendar_grid import CalendarGrid
from ..widgets.charts import BarChart
from ..widgets.dialogs import AlertDialog

__all__ = ["CalendarScreen"]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _format_minutes(m: int, lang: str) -> str:
    if m <= 0:
        return ("۰ دقیقه" if lang == "fa" else "0 min")
    h = m // 60
    r = m % 60
    if lang == "fa":
        parts: List[str] = []
        if h > 0:
            parts.append(f"{i18n.to_fa_digits(str(h))} ساعت")
        if r > 0:
            parts.append(f"{i18n.to_fa_digits(str(r))} دقیقه")
        return " ".join(parts) if parts else "—"
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if r > 0:
        parts.append(f"{r}m")
    return " ".join(parts) if parts else "—"


def _format_clock_hhmm(hhmm: str, lang: str) -> str:
    try:
        return i18n.to_fa_digits(hhmm) if lang == "fa" else hhmm
    except Exception:
        return hhmm


# =============================================================================
# === CalendarScreen                                                         ===
# =============================================================================

class CalendarScreen(ctk.CTkFrame):
    """Calendar screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``open_quick_log()``
            * ``open_activity_dialog(activity_id)``
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
        self._calendar_system: str = "jalali"
        self._view_mode: str = "month"  # "month" or "week"
        self._selected_iso: str = time_utils.today_iso()
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
            self, title=self._tr("تقویم", "Calendar"),
            lang=self._lang, height=56,
            action_text=self._tr("امروز", "Today"),
            on_action=self._go_to_today,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_view_toggle()
        self._build_calendar_grid()
        self._build_day_detail()
        self._build_week_view()
        self._build_free_time()
        self._build_busiest_quietest()

    def _build_view_toggle(self) -> None:
        """Calendar system + view mode toggles."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(anchor="center")
        rtl = i18n.is_rtl(self._lang)
        # Calendar system segmented
        self._cal_sys_seg = SegmentedControl(
            row, values=["jalali", "gregorian"],
            on_change=self._on_cal_sys_change,
            lang=self._lang, height=32,
        )
        self._cal_sys_seg.set("jalali")
        self._cal_sys_seg.pack(side="right" if rtl else "left", padx=4)
        # View mode segmented
        self._view_mode_seg = SegmentedControl(
            row, values=["month", "week"],
            on_change=self._on_view_mode_change,
            lang=self._lang, height=32,
        )
        self._view_mode_seg.set("month")
        self._view_mode_seg.pack(side="right" if rtl else "left", padx=4)

    def _build_calendar_grid(self) -> None:
        """The CalendarGrid widget."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_SM)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        self._cal_grid = CalendarGrid(
            card.content, calendar_system=self._calendar_system,
            lang=self._lang, on_select=self._on_date_select,
            show_heatmap=True, cell_size=44,
        )
        self._cal_grid.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self._month_grid_section = section

    def _build_day_detail(self) -> None:
        """Day detail panel below the calendar."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._day_detail_card = Card(section, lang=self._lang,
                                       padding=config.SPACE_LG)
        self._day_detail_card.grid(row=0, column=0, sticky="ew")
        self._day_detail_card.content.grid_columnconfigure(0, weight=1)
        # Selected date header
        self._day_date_label = ctk.CTkLabel(
            self._day_detail_card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._day_date_label.grid(row=0, column=0, sticky="ew")
        # Total time
        self._day_total_label = ctk.CTkLabel(
            self._day_detail_card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
        )
        self._day_total_label.grid(row=1, column=0, sticky="ew",
                                      pady=(4, 0))
        # By category + timeline content
        self._day_content_frame = ctk.CTkFrame(
            self._day_detail_card.content, fg_color="transparent")
        self._day_content_frame.grid(row=2, column=0, sticky="ew",
                                       pady=(config.SPACE_SM, 0))
        self._day_content_frame.grid_columnconfigure(0, weight=1)
        # Add activity button
        GoldButton(
            self._day_detail_card.content,
            text=self._tr("+ فعالیت برای این روز",
                            "+ Add activity for this day"),
            command=self._on_add_activity_for_day, lang=self._lang,
            height=36,
        ).grid(row=3, column=0, sticky="ew", pady=(config.SPACE_SM, 0))

    def _build_week_view(self) -> None:
        """Week view panel — hidden by default."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=self._tr("نمای هفته", "Week view"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._week_view_frame = ctk.CTkFrame(
            card.content, fg_color="transparent")
        self._week_view_frame.grid(row=1, column=0, sticky="ew")
        self._week_view_frame.grid_columnconfigure(0, weight=1)
        self._week_view_section = section

    def _build_free_time(self) -> None:
        """Free time finder card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
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
            text=self._tr("یافتن وقت آزاد", "Find free time"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Duration selector + button
        control_row = ctk.CTkFrame(card.content, fg_color="transparent")
        control_row.grid(row=1, column=0, sticky="ew",
                          pady=(config.SPACE_SM, 0))
        control_row.grid_columnconfigure(1, weight=1)
        # Duration presets
        durations_row = ctk.CTkFrame(control_row, fg_color="transparent")
        durations_row.grid(row=0, column=0 if rtl else 1, sticky="e"
                            if rtl else "w")
        self._free_time_durations: List[ctk.CTkButton] = []
        self._free_time_duration: int = 30
        for d in [15, 30, 60, 90]:
            d_str = (i18n.to_fa_digits(str(d))
                      if self._lang == "fa" else str(d))
            btn = ctk.CTkButton(
                durations_row, text=d_str,
                command=lambda _d=d: self._on_free_time_dur(_d),
                fg_color=(config.GOLD if d == self._free_time_duration
                            else config.CHARCOAL),
                hover_color=config.GOLD_BRIGHT,
                text_color=(config.MATTE_BLACK if d == self._free_time_duration
                              else config.TEXT),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                corner_radius=config.RADIUS_PILL, height=28,
                width=44,
            )
            btn.pack(side="right" if rtl else "left", padx=2)
            self._free_time_durations.append(btn)
        # Find button
        self._find_free_btn = GoldButton(
            control_row,
            text=self._tr("پیدا کن", "Find"),
            command=self._on_find_free_time, lang=self._lang, height=32,
        )
        self._find_free_btn.grid(row=0, column=1 if rtl else 0, padx=4)
        # Results
        self._free_time_results = ctk.CTkFrame(
            card.content, fg_color="transparent")
        self._free_time_results.grid(row=2, column=0, sticky="ew",
                                       pady=(config.SPACE_SM, 0))
        self._free_time_results.grid_columnconfigure(0, weight=1)

    def _build_busiest_quietest(self) -> None:
        """Busiest + quietest day cards."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("پرکاربردترین و خلوت‌ترین روز",
                                     "Busiest & quietest"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew")
        for i in range(2):
            row.grid_columnconfigure(i, weight=1, uniform="bq")
        self._busiest_card = StatCard(
            row, label=self._tr("پرکاربردترین", "Busiest"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._busiest_card.grid(row=0, column=0, sticky="nsew",
                                  padx=(0, 4))
        self._quietest_card = StatCard(
            row, label=self._tr("خلوت‌ترین", "Quietest"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._quietest_card.grid(row=0, column=1, sticky="nsew",
                                   padx=(4, 0))

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
            "journal.added", "journal.updated",
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
        """Re-render everything."""
        self._refresh_heatmap()
        self._refresh_day_detail()
        self._refresh_week_view()
        self._refresh_busiest_quietest()
        # Show/hide month vs week sections
        try:
            if self._view_mode == "month":
                self._month_grid_section.grid()
                self._week_view_section.grid_forget()
            else:
                self._month_grid_section.grid_forget()
                self._week_view_section.grid(row=self._section_row - 4,
                                                column=0, sticky="ew",
                                                padx=config.SPACE_LG,
                                                pady=(0, config.SPACE_SM))
        except Exception:
            pass

    def _refresh_heatmap(self) -> None:
        """Build the heatmap data from the activities."""
        try:
            # Get the current visible month
            year = self._cal_grid.current_year()
            month = self._cal_grid.current_month()
            sys_ = self._cal_grid.calendar_system()
            view = calendar_service.month_view(year, month,
                                                 calendar_system=sys_)
            # Build {iso_date: total_seconds} dict
            data: Dict[str, int] = {}
            for week in view.get("weeks", []):
                for day in week:
                    iso = day.get("date_iso")
                    if iso:
                        # Convert minutes to seconds for the heatmap
                        data[iso] = int(day.get("total_min", 0)
                                          or 0) * 60
            self._cal_grid.set_heatmap_data(data)
        except Exception:
            pass

    def _refresh_day_detail(self) -> None:
        """Render the day detail panel."""
        iso = self._selected_iso
        try:
            date_str = jalali.format_jalali(
                iso, fmt="long", lang=self._lang)
        except Exception:
            date_str = iso
        try:
            self._day_date_label.configure(text=date_str)
        except Exception:
            pass
        # Fetch day view
        try:
            day_view = calendar_service.day_view(iso)
        except Exception:
            day_view = {}
        total_min = int(day_view.get("total_min", 0) or 0)
        total_str = _format_minutes(total_min, self._lang)
        try:
            self._day_total_label.configure(text=total_str)
        except Exception:
            pass
        # Clear content
        for child in self._day_content_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        rtl = i18n.is_rtl(self._lang)
        activities = day_view.get("activities", []) or []
        by_cat = day_view.get("by_category", []) or []
        timeline = day_view.get("timeline", []) or []
        if not activities:
            ctk.CTkLabel(
                self._day_content_frame,
                text=self._tr("فعالیتی در این روز ثبت نشده",
                                "No activities on this day"),
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=0, sticky="e" if rtl else "w",
                    pady=config.SPACE_SM)
        else:
            # By category breakdown
            SectionTitle(
                self._day_content_frame,
                text=self._tr("به تفکیک دسته", "By category"),
                lang=self._lang, size=config.FONT_SIZE_BODY,
            ).grid(row=0, column=0, sticky="e" if rtl else "w",
                    pady=(0, config.SPACE_XS))
            for i, c in enumerate(by_cat[:5]):
                row = ctk.CTkFrame(self._day_content_frame,
                                     fg_color="transparent")
                row.grid(row=i + 1, column=0, sticky="ew",
                          pady=(0 if i == 0 else 2, 0))
                row.grid_columnconfigure(1, weight=1)
                color = c.get("category_color") or config.GOLD
                dot = ctk.CTkFrame(row, width=10, height=10,
                                     fg_color=color,
                                     corner_radius=config.RADIUS_PILL)
                dot.grid(row=0, column=1 if rtl else 0, padx=4)
                name = c.get("category_name", "—")
                minutes = int(c.get("total_min", 0) or 0)
                m_str = _format_minutes(minutes, self._lang)
                ctk.CTkLabel(
                    row, text=name,
                    font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                            weight="normal",
                                            lang=self._lang),
                    text_color=config.TEXT,
                    anchor="e" if rtl else "w",
                ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                        else "w")
                ctk.CTkLabel(
                    row, text=m_str,
                    font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                            weight="bold",
                                            lang=self._lang),
                    text_color=config.GOLD,
                ).grid(row=0, column=2 if rtl else 2, padx=4)
            # Activity timeline
            timeline_section_start = len(by_cat[:5]) + 2
            SectionTitle(
                self._day_content_frame,
                text=self._tr("زمان‌بندی", "Timeline"),
                lang=self._lang, size=config.FONT_SIZE_BODY,
            ).grid(row=timeline_section_start, column=0,
                    sticky="e" if rtl else "w",
                    pady=(config.SPACE_SM, config.SPACE_XS))
            for i, a in enumerate(activities[:20]):
                row = ctk.CTkFrame(self._day_content_frame,
                                     fg_color="transparent")
                row.grid(row=timeline_section_start + 1 + i, column=0,
                          sticky="ew", pady=(0 if i == 0 else 2, 0))
                row.grid_columnconfigure(1, weight=1)
                # Time
                start_ts = a.get("start_ts", "")
                time_str = ""
                if start_ts and len(start_ts) >= 16:
                    time_str = _format_clock_hhmm(
                        start_ts[11:16], self._lang)
                ctk.CTkLabel(
                    row, text=time_str,
                    font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                            weight="bold",
                                            lang=self._lang),
                    text_color=config.GOLD,
                ).grid(row=0, column=1 if rtl else 0, padx=4)
                # Title + duration
                title = a.get("title", "—")
                dur_min = int(a.get("duration_min", 0) or 0)
                dur_str = _format_minutes(dur_min, self._lang)
                ctk.CTkLabel(
                    row, text=f"{title}  •  {dur_str}",
                    font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                            weight="normal",
                                            lang=self._lang),
                    text_color=config.TEXT,
                    anchor="e" if rtl else "w",
                ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                        else "w")
        # Mood/energy if journal entry exists
        try:
            from ...features.journal import journal_service
            entry = journal_service.get_by_date(iso)
            if entry is not None and (entry.mood or entry.energy):
                mood_row = ctk.CTkFrame(self._day_content_frame,
                                          fg_color="transparent")
                mood_row.grid(row=100, column=0, sticky="ew",
                                pady=(config.SPACE_SM, 0))
                mood_row.grid_columnconfigure(0, weight=1)
                if entry.mood:
                    emojis = {1: "😞", 2: "😕", 3: "😐",
                              4: "🙂", 5: "😄"}
                    ctk.CTkLabel(
                        mood_row,
                        text=f"{emojis.get(entry.mood, '•')} "
                              f"{self._tr('حال', 'Mood')}: "
                              f"{i18n.to_fa_digits(str(entry.mood)) if self._lang == 'fa' else str(entry.mood)}",
                        font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                                weight="normal",
                                                lang=self._lang),
                        text_color=config.TEXT_DIM,
                        anchor="e" if rtl else "w",
                    ).pack(side="right" if rtl else "left", padx=4)
                if entry.energy:
                    ctk.CTkLabel(
                        mood_row,
                        text=f"⚡ {self._tr('انرژی', 'Energy')}: "
                              f"{i18n.to_fa_digits(str(entry.energy)) if self._lang == 'fa' else str(entry.energy)}",
                        font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                                weight="normal",
                                                lang=self._lang),
                        text_color=config.TEXT_DIM,
                        anchor="e" if rtl else "w",
                    ).pack(side="right" if rtl else "left", padx=4)
        except Exception:
            pass

    def _refresh_week_view(self) -> None:
        """Render the week view: 7 columns × hour-by-hour."""
        for child in self._week_view_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            week_data = calendar_service.week_view(self._selected_iso)
        except Exception:
            week_data = {}
        try:
            days = week_data.get("days", []) or []
        except Exception:
            days = []
        if not days:
            ctk.CTkLabel(
                self._week_view_frame, text="",
            ).grid(row=0, column=0)
            return
        rtl = i18n.is_rtl(self._lang)
        # Header row of weekday abbreviations
        header_row = ctk.CTkFrame(self._week_view_frame,
                                    fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew")
        for i in range(7):
            header_row.grid_columnconfigure(i, weight=1, uniform="day")
        for i, d in enumerate(days):
            col = (6 - i) if rtl else i
            iso = d.get("date_iso", "")
            try:
                py_wd = __import__("datetime").date.fromisoformat(
                    iso[:10]).weekday()
                sat_first = (py_wd + 2) % 7
                if self._lang == "fa":
                    label = ["ش", "ی", "د", "س", "چ", "پ", "ج"][sat_first]
                else:
                    label = ["Sa", "Su", "Mo", "Tu", "We",
                              "Th", "Fr"][sat_first]
            except Exception:
                label = "—"
            ctk.CTkLabel(
                header_row, text=label,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).grid(row=0, column=col, padx=2, pady=2)
        # Activity blocks per day
        blocks_row = ctk.CTkFrame(self._week_view_frame,
                                    fg_color="transparent")
        blocks_row.grid(row=1, column=0, sticky="ew",
                         pady=(0, config.SPACE_SM))
        for i in range(7):
            blocks_row.grid_columnconfigure(i, weight=1, uniform="day")
        for i, d in enumerate(days):
            col = (6 - i) if rtl else i
            day_col = ctk.CTkFrame(blocks_row, fg_color=config.SURFACE,
                                     corner_radius=config.RADIUS_SM)
            day_col.grid(row=0, column=col, sticky="nsew",
                          padx=2, pady=2)
            day_col.grid_columnconfigure(0, weight=1)
            activities = d.get("activities", []) or []
            if not activities:
                ctk.CTkLabel(
                    day_col, text="—",
                    font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                            weight="normal", lang="en"),
                    text_color=config.TEXT_FAINT,
                ).pack(pady=8)
            else:
                for a in activities[:6]:
                    title = (a.get("title") or "—")[:12]
                    dur_min = int(a.get("duration_min", 0) or 0)
                    block = ctk.CTkFrame(
                        day_col, fg_color=config.GOLD_DIM,
                        corner_radius=config.RADIUS_SM,
                    )
                    block.pack(fill="x", padx=2, pady=2)
                    ctk.CTkLabel(
                        block, text=title,
                        font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                                weight="bold",
                                                lang=self._lang),
                        text_color=config.GOLD,
                    ).pack(anchor="e" if rtl else "w", padx=2)
                    ctk.CTkLabel(
                        block, text=_format_minutes(dur_min, self._lang),
                        font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                                weight="normal",
                                                lang=self._lang),
                        text_color=config.TEXT_DIM,
                    ).pack(anchor="e" if rtl else "w", padx=2)
                if len(activities) > 6:
                    more_str = (f"+{i18n.to_fa_digits(str(len(activities) - 6))}"
                                  if self._lang == "fa"
                                  else f"+{len(activities) - 6}")
                    ctk.CTkLabel(
                        day_col, text=more_str,
                        font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                                weight="normal",
                                                lang=self._lang),
                        text_color=config.TEXT_DIM,
                    ).pack(pady=2)

    def _refresh_busiest_quietest(self) -> None:
        """Update the busiest/quietest day cards."""
        try:
            today = time_utils.today_iso()
            month_start = time_utils.add_days(today, -29)
            busiest = calendar_service.busiest_day(
                date_from=month_start, date_to=today)
            quietest = calendar_service.quietest_day(
                date_from=month_start, date_to=today)
            if busiest:
                try:
                    b_str = jalali.format_jalali(
                        busiest.get("date_iso", ""), fmt="short",
                        lang=self._lang)
                except Exception:
                    b_str = busiest.get("date_iso", "—")
                b_str += f"  •  {_format_minutes(int(busiest.get('total_min', 0)), self._lang)}"
            else:
                b_str = "—"
            if quietest:
                try:
                    q_str = jalali.format_jalali(
                        quietest.get("date_iso", ""), fmt="short",
                        lang=self._lang)
                except Exception:
                    q_str = quietest.get("date_iso", "—")
                q_str += f"  •  {_format_minutes(int(quietest.get('total_min', 0)), self._lang)}"
            else:
                q_str = "—"
            self._busiest_card.set_value(b_str)
            self._quietest_card.set_value(q_str)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_date_select(self, iso: str) -> None:
        self._selected_iso = iso
        self._refresh_day_detail()

    def _on_cal_sys_change(self, value: str) -> None:
        self._calendar_system = value
        try:
            # Recreate the grid with the new calendar system
            for child in self._cal_grid.master.winfo_children():
                pass
            # The CalendarGrid doesn't expose a public setter for
            # calendar_system, so we recreate it.
            parent = self._cal_grid.master
            self._cal_grid.destroy()
            self._cal_grid = CalendarGrid(
                parent, calendar_system=self._calendar_system,
                lang=self._lang, on_select=self._on_date_select,
                show_heatmap=True, cell_size=44,
            )
            self._cal_grid.grid(row=0, column=0, sticky="ew",
                                  padx=4, pady=4)
            # Select today
            self._cal_grid.go_today()
            self._refresh_heatmap()
        except Exception:
            pass

    def _on_view_mode_change(self, value: str) -> None:
        self._view_mode = value
        self.refresh()

    def _go_to_today(self) -> None:
        try:
            self._cal_grid.go_today()
            self._selected_iso = time_utils.today_iso()
            self._refresh_day_detail()
        except Exception:
            pass

    def _on_add_activity_for_day(self) -> None:
        """Open quick-log dialog prefilled with the selected date."""
        if self._app and hasattr(self._app, "open_quick_log"):
            try:
                self._app.open_quick_log()
                return
            except Exception:
                pass
        # Publish a generic event as fallback
        try:
            event_bus.bus.publish("ui.quick_log_requested",
                                    {"date_iso": self._selected_iso})
        except Exception:
            pass

    def _on_free_time_dur(self, dur: int) -> None:
        self._free_time_duration = dur
        # Update button highlights
        for i, btn in enumerate(self._free_time_durations):
            d = [15, 30, 60, 90][i]
            try:
                btn.configure(
                    fg_color=(config.GOLD if d == dur
                                else config.CHARCOAL),
                    text_color=(config.MATTE_BLACK if d == dur
                                  else config.TEXT),
                )
            except Exception:
                pass

    def _on_find_free_time(self) -> None:
        """Find free time slots on the selected day."""
        # Clear results
        for child in self._free_time_results.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            slots = calendar_service.find_free_time(
                self._selected_iso,
                duration_min=self._free_time_duration)
        except Exception:
            slots = []
        rtl = i18n.is_rtl(self._lang)
        if not slots:
            ctk.CTkLabel(
                self._free_time_results,
                text=self._tr("وقت آزادی پیدا نشد",
                                "No free slots found"),
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=0, sticky="e" if rtl else "w",
                    pady=config.SPACE_SM)
            return
        for i, s in enumerate(slots[:6]):
            row = ctk.CTkFrame(self._free_time_results,
                                 fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew",
                      pady=(0 if i == 0 else 2, 0))
            row.grid_columnconfigure(1, weight=1)
            start = _format_clock_hhmm(s.get("start_hhmm", ""), self._lang)
            end = _format_clock_hhmm(s.get("end_hhmm", ""), self._lang)
            dur = int(s.get("duration_min", 0) or 0)
            ctk.CTkLabel(
                row, text=f"{start} — {end}",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            ctk.CTkLabel(
                row, text=_format_minutes(dur, self._lang),
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w", padx=4)

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
    print("CalendarScreen module: month grid + day detail + week view "
          "+ free time finder + busiest/quietest cards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
