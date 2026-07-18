"""
rask.ui.screens.pomodoro_screen
===============================

Pomodoro timer screen — a full-screen view of the Pomodoro technique
with a circular progress ring, phase label, cycle dots, activity
binding, and a collapsible settings panel.

Mirrors the *Pomodoro* pattern from the web app but uses the
:class:`rask.features.pomodoro.PomodoroService` as the source of
truth.  Because the service is a module-level singleton, the screen
state always reflects whatever the timer is doing — even if a session
was started from elsewhere (e.g. the quick-actions panel).

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"پومودورو"`` with a settings gear icon
       (toggles the settings panel)
    2. **Big circular progress ring** — the central element.  During
       a *work* phase the ring is gold, during *break* phases it is
       green (short break) or blue (long break).  In the centre: the
       countdown time (``MM:SS``) and the phase label below.
    3. **Cycle dots** — 4 small dots representing the cycles in the
       current run.  Filled dots = completed work phases.
    4. **Activity title** — editable inline entry (becomes the title
       of the activity logged for the work phase)
    5. **Category chips** — horizontal strip of category chips;
       selecting one binds the activity to that category
    6. **Buttons** — Start / Pause / Resume / Stop / Skip
    7. **Today's stats** — Pomodoro count + total focus time today
    8. **Settings panel** (collapsible) — work / break / long-break
       durations, cycles, auto-start-breaks toggle, sound toggle

Auto-refresh
------------
Subscribes to ``pomodoro.started`` / ``pomodoro.phase_changed`` /
``pomodoro.paused`` / ``pomodoro.resumed`` / ``pomodoro.stopped`` /
``pomodoro.skipped`` / ``pomodoro.cycle_complete`` /
``pomodoro.finished`` / ``pomodoro.tick`` / ``language.changed`` /
``category.added`` / ``category.updated`` / ``category.deleted`` /
``activity.added`` / ``data.cleared``.

A 1-second ``after()`` poll drives the visible countdown even when no
``pomodoro.tick`` event is published (the service itself does not
poll — it computes remaining time on demand).
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
from ...core import event_bus, time_utils
from ... import database as db
from ...features.pomodoro import (
    pomodoro_service,
    PHASE_WORK, PHASE_BREAK, PHASE_LONG_BREAK, PHASE_IDLE,
)
from ...features.sound_effects import sound_service
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.inputs import GoldEntry
from ..widgets.toggles import Toggle, SegmentedControl
from ..widgets.progress_ring import ProgressRing
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState

__all__ = ["PomodoroScreen"]


# =============================================================================
# === Phase helpers                                                          ===
# =============================================================================

_PHASE_LABEL_FA: Dict[str, str] = {
    PHASE_WORK: "تمرکز",
    PHASE_BREAK: "استراحت",
    PHASE_LONG_BREAK: "استراحت بلند",
    PHASE_IDLE: "آماده",
}
_PHASE_LABEL_EN: Dict[str, str] = {
    PHASE_WORK: "Focus",
    PHASE_BREAK: "Break",
    PHASE_LONG_BREAK: "Long Break",
    PHASE_IDLE: "Ready",
}
_PHASE_COLOR: Dict[str, str] = {
    PHASE_WORK: config.GOLD,
    PHASE_BREAK: config.SUCCESS,
    PHASE_LONG_BREAK: config.INFO,
    PHASE_IDLE: config.TEXT_DIM,
}


def _phase_label(phase: str, lang: str) -> str:
    if lang == "fa":
        return _PHASE_LABEL_FA.get(phase, phase)
    return _PHASE_LABEL_EN.get(phase, phase)


def _phase_color(phase: str) -> str:
    return _PHASE_COLOR.get(phase, config.GOLD)


def _format_mmss(seconds: int, lang: str) -> str:
    """Format seconds as ``MM:SS`` with localized digits."""
    if seconds < 0:
        seconds = 0
    m = seconds // 60
    s = seconds % 60
    raw = f"{m:02d}:{s:02d}"
    return i18n.to_fa_digits(raw) if lang == "fa" else raw


# =============================================================================
# === PomodoroScreen                                                         ===
# =============================================================================

class PomodoroScreen(ctk.CTkFrame):
    """Full-screen Pomodoro timer UI.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``switch_tab(tab)``
            * ``open_quick_log()``
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
        self._tick_job: Optional[Any] = None
        self._settings_visible: bool = False
        self._selected_category_id: Optional[int] = None
        self._category_chips: List[ctk.CTkBaseClass] = []
        self._last_known_phase: str = PHASE_IDLE
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)
        self._schedule_tick()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header with settings gear
        self._header = Header(
            self, title=self._tr("پومودورو", "Pomodoro"),
            lang=self._lang, height=56,
            action_icon="settings",
            on_action=self._toggle_settings,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # Build sections
        self._section_row = 0
        self._build_settings_panel()
        self._build_ring()
        self._build_cycle_dots()
        self._build_activity()
        self._build_categories()
        self._build_buttons()
        self._build_today_stats()
        self._build_help_text()

    def _build_settings_panel(self) -> None:
        """Collapsible settings panel — hidden by default."""
        self._settings_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent",
        )
        # We do NOT grid it here — it's hidden until toggled.
        self._settings_frame.grid_columnconfigure(0, weight=1)
        card = Card(self._settings_frame, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        # Work duration
        self._work_entry = self._add_setting_row(
            card, 0,
            self._tr("مدت تمرکز (دقیقه)", "Focus duration (min)"),
            str(pomodoro_service.get_settings().work_min),
        )
        # Break duration
        self._break_entry = self._add_setting_row(
            card, 1,
            self._tr("مدت استراحت (دقیقه)", "Break duration (min)"),
            str(pomodoro_service.get_settings().break_min),
        )
        # Long break duration
        self._long_break_entry = self._add_setting_row(
            card, 2,
            self._tr("استراحت بلند (دقیقه)", "Long break (min)"),
            str(pomodoro_service.get_settings().long_break_min),
        )
        # Cycles
        self._cycles_entry = self._add_setting_row(
            card, 3,
            self._tr("تعداد چرخه‌ها", "Cycles"),
            str(pomodoro_service.get_settings().cycles),
        )
        # Auto-start breaks toggle
        toggle_row = ctk.CTkFrame(card.content, fg_color="transparent")
        toggle_row.grid(row=4, column=0, columnspan=2,
                         sticky="ew", pady=(config.SPACE_SM, 0))
        toggle_row.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        self._auto_break_toggle = Toggle(
            toggle_row,
            text=self._tr("شروع خودکار استراحت", "Auto-start breaks"),
            on_change=self._on_auto_break_toggle,
            lang=self._lang,
        )
        self._auto_break_toggle.set(
            pomodoro_service.get_settings().auto_start_breaks)
        self._auto_break_toggle.grid(
            row=0, column=0, sticky="e" if rtl else "w")
        # Sound toggle
        self._sound_toggle = Toggle(
            toggle_row,
            text=self._tr("صدا در پایان فاز", "Sound on phase end"),
            on_change=self._on_sound_toggle,
            lang=self._lang,
        )
        self._sound_toggle.grid(row=1, column=0, sticky="e" if rtl else "w",
                                  pady=(6, 0))
        # Apply button
        self._apply_btn = GoldButton(
            card.content, text=self._tr("اعمال", "Apply"),
            command=self._apply_settings, lang=self._lang, height=36,
        )
        self._apply_btn.grid(row=5, column=0, columnspan=2,
                              sticky="ew", pady=(config.SPACE_MD, 0))

    def _add_setting_row(self, card: Card, row: int,
                          label: str, value: str) -> ctk.CTkEntry:
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=row, column=0, sticky="e" if rtl else "w",
                pady=config.SPACE_XS)
        entry = GoldEntry(
            card.content, lang=self._lang, width=80,
            placeholder=value,
        )
        entry.grid(row=row, column=1, sticky="e" if rtl else "w",
                    padx=config.SPACE_MD, pady=config.SPACE_XS)
        entry.insert(0, value)
        return entry

    def _build_ring(self) -> None:
        """The big circular progress ring with the countdown inside."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_LG,
                                                   config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        # Center the ring inside a square frame
        ring_wrap = ctk.CTkFrame(section, fg_color="transparent",
                                  height=320)
        ring_wrap.grid(row=0, column=0)
        ring_wrap.grid_columnconfigure(0, weight=1)
        # The ProgressRing with a centered time label
        self._ring = ProgressRing(
            ring_wrap, progress=0.0, size=260, line_width=14,
            show_percentage=False, animated=True, lang=self._lang,
            color=config.GOLD,
        )
        self._ring.grid(row=0, column=0, padx=20, pady=20)
        # Overlay: time + phase label (placed on top of the ring centre)
        self._time_label = ctk.CTkLabel(
            ring_wrap, text="۲۵:۰۰" if self._lang == "fa" else "25:00",
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._time_label.place(relx=0.5, rely=0.46, anchor="center")
        self._phase_label = ctk.CTkLabel(
            ring_wrap, text=_phase_label(PHASE_IDLE, self._lang),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        )
        self._phase_label.place(relx=0.5, rely=0.58, anchor="center")

    def _build_cycle_dots(self) -> None:
        """4 small dots showing how many work cycles have completed."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG)
        section.grid_columnconfigure(0, weight=1)
        dots_row = ctk.CTkFrame(section, fg_color="transparent")
        dots_row.pack(anchor="center")
        self._cycle_dots: List[ctk.CTkFrame] = []
        for i in range(4):  # default 4 dots; rebuilt on refresh
            dot = ctk.CTkFrame(
                dots_row, width=12, height=12,
                fg_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_PILL,
            )
            dot.pack(side="right" if i18n.is_rtl(self._lang)
                      else "left", padx=6)
            self._cycle_dots.append(dot)

    def _build_activity(self) -> None:
        """Editable activity title (becomes the activity title on log)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD, 0))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("عنوان فعالیت", "Activity title"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._title_entry = GoldEntry(
            section, lang=self._lang,
            placeholder=self._tr("چه کاری انجام می‌دهی؟",
                                  "What are you working on?"),
        )
        self._title_entry.grid(row=1, column=0, sticky="ew",
                                pady=(config.SPACE_XS, 0))
        # Restore title from current state if any
        try:
            cur_title = pomodoro_service.state().get("title", "")
            if cur_title:
                self._title_entry.delete(0, "end")
                self._title_entry.insert(0, cur_title)
        except Exception:
            pass
        # Bind change to persist title for the next work phase
        self._title_entry.bind(
            "<FocusOut>", lambda _e: self._on_title_changed())

    def _build_categories(self) -> None:
        """Horizontal strip of category chips."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD, 0))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("دسته‌بندی", "Category"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._cats_strip = ctk.CTkScrollableFrame(
            section, fg_color="transparent", orientation="horizontal",
            height=44,
        )
        self._cats_strip.grid(row=1, column=0, sticky="ew",
                                pady=(config.SPACE_XS, 0))
        self._cats_strip.grid_columnconfigure(0, weight=1)

    def _build_buttons(self) -> None:
        """Primary Start/Pause/Resume + Stop + Skip row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_LG, 0))
        section.grid_columnconfigure(0, weight=1)
        # Primary button row
        primary_row = ctk.CTkFrame(section, fg_color="transparent")
        primary_row.grid(row=0, column=0, sticky="ew")
        primary_row.grid_columnconfigure(0, weight=1)
        self._primary_btn = GoldButton(
            primary_row, text=self._tr("شروع", "Start"),
            command=self._on_primary, lang=self._lang, height=52,
        )
        self._primary_btn.pack(anchor="center", fill="x",
                                padx=config.SPACE_LG)
        # Secondary button row
        secondary_row = ctk.CTkFrame(section, fg_color="transparent")
        secondary_row.grid(row=1, column=0, sticky="ew",
                            pady=(config.SPACE_SM, 0))
        secondary_row.grid_columnconfigure(0, weight=1)
        secondary_row.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        self._skip_btn = GhostButton(
            secondary_row, text=self._tr("رد کردن فاز", "Skip phase"),
            command=self._on_skip, lang=self._lang, height=42,
        )
        self._skip_btn.grid(row=0, column=0 if rtl else 1, sticky="ew",
                             padx=(0 if rtl else 4, 4 if rtl else 0))
        self._stop_btn = GhostButton(
            secondary_row, text=self._tr("توقف", "Stop"),
            command=self._on_stop, lang=self._lang, height=42,
        )
        self._stop_btn.grid(row=0, column=1 if rtl else 0, sticky="ew",
                             padx=(4 if rtl else 0, 0 if rtl else 4))

    def _build_today_stats(self) -> None:
        """Two stat cards: pomodoro count + total focus time today."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_LG, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        SectionTitle(
            section, text=self._tr("آمار امروز", "Today's stats"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if i18n.is_rtl(self._lang)
                else "w")
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(config.SPACE_SM, 0))
        for i in range(2):
            row.grid_columnconfigure(i, weight=1, uniform="pomo")
        self._today_count_card = StatCard(
            row, label=self._tr("تعداد پومودورو", "Pomodoros"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._today_count_card.grid(row=0, column=0, sticky="nsew",
                                      padx=(0, 4))
        self._today_focus_card = StatCard(
            row, label=self._tr("زمان تمرکز", "Focus time"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._today_focus_card.grid(row=0, column=1, sticky="nsew",
                                      padx=(4, 0))

    def _build_help_text(self) -> None:
        """Tiny tip line below stats."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        tip = (self._tr(
            "۲۵ دقیقه تمرکز، ۵ دقیقه استراحت — تکرار برای ۴ چرخه.",
            "25 min focus, 5 min break — repeat for 4 cycles."))
        ctk.CTkLabel(
            section, text=tip,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT, justify="center",
            wraplength=420,
        ).grid(row=0, column=0)

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
            "pomodoro.started", "pomodoro.phase_changed",
            "pomodoro.paused", "pomodoro.resumed",
            "pomodoro.stopped", "pomodoro.skipped",
            "pomodoro.cycle_complete", "pomodoro.finished",
            "pomodoro.tick", "language.changed",
            "category.added", "category.updated", "category.deleted",
            "activity.added", "data.cleared",
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
        # Detect phase transitions for sound + toast
        try:
            ev = args[0] if args else None
            if isinstance(ev, dict):
                ev_name = ev.get("event") or ""
                # If we got a cycle_complete, fire a sound + toast
                if "pomodoro.cycle_complete" in str(kwargs.get("event", "")):
                    self._on_phase_ended(is_break=True)
        except Exception:
            pass
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

    def _schedule_tick(self) -> None:
        """1-second poll that drives the visible countdown."""
        if self._tick_job is None:
            try:
                self._tick_job = self.after(1000, self._on_tick)
            except Exception:
                self._tick_job = None

    def _on_tick(self) -> None:
        self._tick_job = None
        try:
            self._refresh_ring_only()
            # Check for phase transition by polling state
            try:
                state = pomodoro_service.state()
                phase = state.get("phase", PHASE_IDLE)
                if phase != self._last_known_phase:
                    prev = self._last_known_phase
                    self._last_known_phase = phase
                    # If we transitioned *out of* work into a break,
                    # play the sound + toast.
                    if prev == PHASE_WORK and phase in (PHASE_BREAK,
                                                          PHASE_LONG_BREAK):
                        self._on_phase_ended(is_break=True)
                    elif prev in (PHASE_BREAK, PHASE_LONG_BREAK) and \
                            phase == PHASE_WORK:
                        self._on_phase_ended(is_break=False)
            except Exception:
                pass
        finally:
            self._schedule_tick()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render the entire screen from the service state."""
        self._refresh_ring()
        self._refresh_cycle_dots()
        self._refresh_buttons()
        self._refresh_categories()
        self._refresh_today_stats()

    def _refresh_ring_only(self) -> None:
        """Lightweight per-second refresh of just the ring + time."""
        try:
            state = pomodoro_service.state()
            phase = state.get("phase", PHASE_IDLE)
            remaining = pomodoro_service.remaining_sec()
            progress = pomodoro_service.progress()
            color = _phase_color(phase)
            # Update time label
            time_str = _format_mmss(remaining, self._lang)
            self._time_label.configure(text=time_str,
                                         text_color=color)
            # Update phase label
            self._phase_label.configure(
                text=_phase_label(phase, self._lang),
                text_color=color)
            # Update ring color + progress
            try:
                # ProgressRing doesn't expose a public color setter;
                # poke the private attribute then ask for a redraw.
                self._ring._color = color  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                self._ring.set_progress(progress, animate=False)
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_ring(self) -> None:
        self._refresh_ring_only()

    def _refresh_cycle_dots(self) -> None:
        """Rebuild the cycle dots based on the current state."""
        try:
            state = pomodoro_service.state()
            cycles_total = int(state.get("cycles_total", 4) or 4)
            completed = int(state.get("completed_cycles", 0) or 0)
        except Exception:
            cycles_total = 4
            completed = 0
        # Rebuild the dots strip if the count changed
        try:
            parent = self._cycle_dots[0].master if self._cycle_dots else None
            if parent is not None and len(self._cycle_dots) != cycles_total:
                for d in self._cycle_dots:
                    d.destroy()
                self._cycle_dots = []
                rtl = i18n.is_rtl(self._lang)
                for i in range(cycles_total):
                    dot = ctk.CTkFrame(
                        parent, width=12, height=12,
                        fg_color=(config.GOLD if i < completed
                                   else config.SURFACE_HI),
                        corner_radius=config.RADIUS_PILL,
                    )
                    dot.pack(side="right" if rtl else "left", padx=6)
                    self._cycle_dots.append(dot)
                return
            # Just update colors
            for i, dot in enumerate(self._cycle_dots):
                try:
                    dot.configure(
                        fg_color=(config.GOLD if i < completed
                                   else config.SURFACE_HI))
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_buttons(self) -> None:
        """Update the primary button label + enabled state."""
        try:
            is_active = pomodoro_service.is_active()
            is_paused = pomodoro_service.is_paused()
        except Exception:
            is_active = False
            is_paused = False
        if not is_active:
            label = self._tr("شروع", "Start")
        elif is_paused:
            label = self._tr("ادامه", "Resume")
        else:
            label = self._tr("توقف موقت", "Pause")
        try:
            self._primary_btn.configure(text=label)
        except Exception:
            pass
        try:
            self._stop_btn.configure(state="normal" if is_active
                                       else "disabled")
            self._skip_btn.configure(state="normal" if is_active
                                       else "disabled")
        except Exception:
            pass

    def _refresh_categories(self) -> None:
        """Rebuild the category chip strip."""
        # Clear old chips
        for child in self._cats_strip.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._category_chips = []
        # Fetch categories
        try:
            cats = db.category_list(include_archived=False)
        except Exception:
            cats = []
        rtl = i18n.is_rtl(self._lang)
        # Restore current selection from state
        try:
            self._selected_category_id = pomodoro_service.state().get(
                "category_id")
        except Exception:
            pass
        for c in cats[:8]:
            cid = c.get("id")
            name = (c.get("name_fa") if self._lang == "fa"
                     else c.get("name_en")) or "—"
            color = c.get("color") or config.GOLD
            selected = (cid == self._selected_category_id)
            chip = PillButton(
                self._cats_strip, text=name,
                command=lambda _cid=cid: self._on_category_tap(_cid),
                lang=self._lang, height=36,
                color=(color if selected else config.CHARCOAL),
                text_color=(config.MATTE_BLACK if selected
                              else config.TEXT),
                font_size=config.FONT_SIZE_SMALL,
            )
            chip.pack(side="right" if rtl else "left", padx=4, pady=4)
            self._category_chips.append(chip)

    def _refresh_today_stats(self) -> None:
        """Update today's pomodoro count + total focus time."""
        # Count pomodoro-kind activities today
        try:
            today = time_utils.today_iso()
            acts = db.activity_list(date_from=today, date_to=today,
                                     limit=1000)
            pomodoro_count = sum(
                1 for a in acts
                if (a.get("kind") == "pomodoro"
                    or (a.get("metadata_json") or "").find("pomodoro") >= 0))
            total_sec = int(db.activity_sum_duration(
                date_from=today, date_to=today) or 0)
        except Exception:
            pomodoro_count = 0
            total_sec = 0
        count_str = (i18n.to_fa_digits(str(pomodoro_count))
                     if self._lang == "fa" else str(pomodoro_count))
        focus_str = time_utils.seconds_to_human(total_sec, lang=self._lang)
        try:
            self._today_count_card.set_value(count_str)
            self._today_focus_card.set_value(focus_str)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_primary(self) -> None:
        """Start / Pause / Resume the timer."""
        try:
            if not pomodoro_service.is_active():
                title = self._title_entry.get().strip() or (
                    self._tr("جلسه پومودورو", "Pomodoro session"))
                pomodoro_service.start(
                    title=title,
                    category_id=self._selected_category_id,
                )
                self._last_known_phase = PHASE_WORK
                self._show_toast(self._tr("شروع تمرکز", "Focus started"))
                self._play_sound("start")
            elif pomodoro_service.is_paused():
                pomodoro_service.resume()
            else:
                pomodoro_service.pause()
        except Exception as exc:  # noqa: BLE001
            self._show_toast(self._tr("خطا در اجرای تایمر",
                                        "Timer error"))
        self.refresh()

    def _on_stop(self) -> None:
        try:
            pomodoro_service.stop()
            self._show_toast(self._tr("تایمر متوقف شد", "Timer stopped"))
            self._play_sound("stop")
        except Exception:
            pass
        self.refresh()

    def _on_skip(self) -> None:
        try:
            pomodoro_service.skip()
            self._show_toast(self._tr("فاز رد شد", "Phase skipped"))
        except Exception:
            pass
        self.refresh()

    def _on_category_tap(self, cid: int) -> None:
        self._selected_category_id = cid
        self._refresh_categories()

    def _on_title_changed(self) -> None:
        """Persist the title so the next work phase uses it."""
        try:
            title = self._title_entry.get().strip()
            # Stash in service state via update_settings would be wrong;
            # use state() setter if exposed, else just leave it.
            # The service's start() takes title=, so we keep it locally.
            pass
        except Exception:
            pass

    def _on_phase_ended(self, is_break: bool) -> None:
        """Called when a phase completes — play sound + show toast."""
        try:
            s = pomodoro_service.get_settings()
            if s.sound_on_complete:
                self._play_sound("complete")
            if is_break:
                self._show_toast(
                    self._tr("تمرکز تمام شد! وقت استراحت.",
                              "Focus done! Time for a break."))
            else:
                self._show_toast(
                    self._tr("استراحت تمام شد! آماده‌ای؟",
                              "Break over! Ready to focus?"))
        except Exception:
            pass

    def _toggle_settings(self) -> None:
        self._settings_visible = not self._settings_visible
        try:
            if self._settings_visible:
                # Show settings at the very top of the scroll area
                self._settings_frame.grid(row=0, column=0, sticky="ew",
                                            padx=config.SPACE_LG,
                                            pady=(config.SPACE_MD, 0))
                # Re-order so settings appears first
                self._settings_frame.tkraise()
            else:
                self._settings_frame.grid_forget()
        except Exception:
            pass

    def _on_auto_break_toggle(self, value: bool) -> None:
        try:
            pomodoro_service.update_settings(auto_start_breaks=bool(value))
        except Exception:
            pass

    def _on_sound_toggle(self, value: bool) -> None:
        try:
            pomodoro_service.update_settings(sound_on_complete=bool(value))
            sound_service.set_enabled(bool(value))
        except Exception:
            pass

    def _apply_settings(self) -> None:
        try:
            work_min = int(self._work_entry.get() or 25)
            break_min = int(self._break_entry.get() or 5)
            long_break_min = int(self._long_break_entry.get() or 15)
            cycles = int(self._cycles_entry.get() or 4)
            pomodoro_service.update_settings(
                work_min=work_min, break_min=break_min,
                long_break_min=long_break_min, cycles=cycles,
            )
            self._show_toast(self._tr("تنظیمات ذخیره شد",
                                        "Settings saved"))
        except Exception:
            self._show_toast(self._tr("ورودی نامعتبر", "Invalid input"))

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

    def _play_sound(self, name: str) -> None:
        try:
            sound_service.play(name)
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
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("PomodoroScreen module: ring + cycle dots + activity + "
          "categories + settings panel + today stats.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
