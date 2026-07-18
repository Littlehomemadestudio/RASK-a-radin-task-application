"""
rask.ui.screens.focus_screen
============================

Deep-focus mode screen — minimalist timer for distraction-free work
sessions.

Mirrors the *Focus Mode* view from the web app.  Uses
:class:`rask.features.focus_mode.FocusMode` as the source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"تمرکز عمیق"`` with settings icon
    2. **Configuration panel** (shown when no session is active):
       - Activity title entry
       - Category picker (chips)
       - Duration preset buttons (25 / 50 / 75 / 90 / 120 min)
       - Block-internet toggle (with warning)
       - Start button ``"شروع جلسه تمرکز"``
    3. **Active session view** (shown when a session is running):
       - Big minimalist timer (MM:SS)
       - Session title
       - ``"پایان زودهنگام"`` (End early) button
       - ``"ثبت وقفه"`` (Log interruption) button
       - Interruption count
    4. **Post-session stats** (shown after a session ends):
       - Duration, interruptions, focus score
    5. **Today's focus sessions** — list with start time, duration, score
    6. **Settings panel** (collapsible):
       - Default duration
       - Default block behavior

Auto-refresh
------------
Subscribes to ``focus.started`` / ``focus.ended`` / ``focus.tick`` /
``focus.interruption`` / ``focus.paused`` / ``focus.resumed`` /
``language.changed`` / ``data.cleared``.

A 1-second ``after()`` poll drives the visible countdown.
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
from ...features.focus_mode import focus_mode, DEFAULT_DURATION_MIN
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
    DangerButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.inputs import GoldEntry
from ..widgets.toggles import Toggle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.dialogs import AlertDialog

__all__ = ["FocusScreen"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

_DURATION_PRESETS: List[int] = [25, 50, 75, 90, 120]


def _format_mmss(seconds: int, lang: str) -> str:
    if seconds < 0:
        seconds = 0
    m = seconds // 60
    s = seconds % 60
    raw = f"{m:02d}:{s:02d}"
    return i18n.to_fa_digits(raw) if lang == "fa" else raw


def _format_clock(iso: str, lang: str) -> str:
    """Format the HH:MM portion of an ISO datetime."""
    try:
        hhmm = iso[11:16]
    except Exception:
        return "—"
    return i18n.to_fa_digits(hhmm) if lang == "fa" else hhmm


# =============================================================================
# === FocusScreen                                                            ===
# =============================================================================

class FocusScreen(ctk.CTkFrame):
    """Deep-focus screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
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
        self._selected_duration: int = DEFAULT_DURATION_MIN
        self._selected_category_id: Optional[int] = None
        self._category_chips: List[ctk.CTkBaseClass] = []
        self._last_session_stats: Optional[Dict[str, Any]] = None
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
        self._header = Header(
            self, title=self._tr("تمرکز عمیق", "Deep Focus"),
            lang=self._lang, height=56,
            action_icon="settings",
            on_action=self._toggle_settings,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_settings_panel()
        self._build_timer()
        self._build_config()
        self._build_active_session()
        self._build_session_stats()
        self._build_today_sessions()
        self._build_help()

    def _build_settings_panel(self) -> None:
        """Collapsible settings."""
        self._settings_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._settings_frame.grid_columnconfigure(0, weight=1)
        card = Card(self._settings_frame, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        # Default duration
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content,
            text=self._tr("مدت پیش‌فرض (دقیقه)",
                            "Default duration (min)"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._default_dur_entry = GoldEntry(
            card.content, lang=self._lang, width=80,
            placeholder=str(focus_mode.get_settings().default_duration_min),
        )
        self._default_dur_entry.grid(row=0, column=1, sticky="e" if rtl
                                       else "w",
                                       padx=config.SPACE_MD)
        self._default_dur_entry.insert(
            0, str(focus_mode.get_settings().default_duration_min))
        # Block internet toggle
        self._block_toggle = Toggle(
            card.content,
            text=self._tr("مسدودسازی اینترنت",
                            "Block internet"),
            on_change=self._on_block_toggle,
            lang=self._lang,
        )
        self._block_toggle.set(focus_mode.get_settings().block_internet)
        self._block_toggle.grid(row=1, column=0, columnspan=2,
                                  sticky="e" if rtl else "w",
                                  pady=(config.SPACE_SM, 0))
        # Apply button
        GoldButton(
            card.content, text=self._tr("اعمال", "Apply"),
            command=self._apply_settings, lang=self._lang, height=36,
        ).grid(row=2, column=0, columnspan=2, sticky="ew",
                pady=(config.SPACE_MD, 0))

    def _build_timer(self) -> None:
        """Big minimalist timer (always visible — value depends on state)."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_LG, config.SPACE_MD))
        section.grid_columnconfigure(0, weight=1)
        wrap = ctk.CTkFrame(section, fg_color="transparent", height=240)
        wrap.grid(row=0, column=0)
        wrap.grid_columnconfigure(0, weight=1)
        self._timer_label = ctk.CTkLabel(
            wrap,
            text=_format_mmss(self._selected_duration * 60, self._lang),
            font=_theme.theme.font(size=config.FONT_SIZE_HERO,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._timer_label.place(relx=0.5, rely=0.5, anchor="center")
        # Subtle ring border (a CTk frame ring)
        ring = ctk.CTkFrame(
            wrap, width=220, height=220,
            fg_color="transparent",
            border_width=2, border_color=config.GOLD_DIM,
            corner_radius=config.RADIUS_PILL,
        )
        ring.place(relx=0.5, rely=0.5, anchor="center")
        # Session title (under the timer)
        self._session_title_label = ctk.CTkLabel(
            wrap, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        )
        self._session_title_label.place(relx=0.5, rely=0.85,
                                          anchor="center")

    def _build_config(self) -> None:
        """Configuration panel: title + category + duration presets +
        block toggle + start button.  Hidden when a session is active."""
        self._config_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._config_frame.grid(row=self._next_row(), column=0,
                                  sticky="ew",
                                  padx=config.SPACE_LG,
                                  pady=(0, config.SPACE_MD))
        self._config_frame.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Activity title
        ctk.CTkLabel(
            self._config_frame,
            text=self._tr("عنوان فعالیت", "Activity title"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._title_entry = GoldEntry(
            self._config_frame, lang=self._lang,
            placeholder=self._tr("چه کاری انجام می‌دهی؟",
                                  "What are you working on?"),
        )
        self._title_entry.grid(row=1, column=0, sticky="ew",
                                pady=(config.SPACE_XS, config.SPACE_SM))
        # Category chips
        ctk.CTkLabel(
            self._config_frame,
            text=self._tr("دسته‌بندی", "Category"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=2, column=0, sticky="e" if rtl else "w")
        self._cats_strip = ctk.CTkScrollableFrame(
            self._config_frame, fg_color="transparent",
            orientation="horizontal", height=44,
        )
        self._cats_strip.grid(row=3, column=0, sticky="ew",
                                pady=(config.SPACE_XS, config.SPACE_SM))
        self._cats_strip.grid_columnconfigure(0, weight=1)
        # Duration presets
        ctk.CTkLabel(
            self._config_frame,
            text=self._tr("مدت زمان", "Duration"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=4, column=0, sticky="e" if rtl else "w")
        durations_row = ctk.CTkFrame(
            self._config_frame, fg_color="transparent")
        durations_row.grid(row=5, column=0, sticky="ew",
                             pady=(config.SPACE_XS, config.SPACE_SM))
        for i, dur in enumerate(_DURATION_PRESETS):
            durations_row.grid_columnconfigure(i, weight=1,
                                                 uniform="dur")
        self._duration_buttons: List[ctk.CTkButton] = []
        for i, dur in enumerate(_DURATION_PRESETS):
            dur_str = (i18n.to_fa_digits(str(dur))
                       if self._lang == "fa" else str(dur))
            btn = ctk.CTkButton(
                durations_row, text=f"{dur_str}\n{self._tr('دقیقه', 'min')}",
                command=lambda _d=dur: self._on_duration_tap(_d),
                fg_color=(config.GOLD if dur == self._selected_duration
                            else config.CHARCOAL),
                hover_color=config.GOLD_BRIGHT,
                text_color=(config.MATTE_BLACK
                              if dur == self._selected_duration
                              else config.TEXT),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                corner_radius=config.RADIUS_MD, height=48,
                border_width=2,
                border_color=(config.GOLD if dur == self._selected_duration
                                else config.SURFACE_HI),
            )
            btn.grid(row=0, column=i, sticky="nsew", padx=2)
            self._duration_buttons.append(btn)
        # Block internet toggle + warning
        block_row = ctk.CTkFrame(self._config_frame, fg_color="transparent")
        block_row.grid(row=6, column=0, sticky="ew",
                         pady=(config.SPACE_SM, 0))
        block_row.grid_columnconfigure(0, weight=1)
        self._block_toggle_cfg = Toggle(
            block_row,
            text=self._tr("مسدودسازی اینترنت", "Block internet"),
            on_change=self._on_block_toggle_cfg,
            lang=self._lang,
        )
        self._block_toggle_cfg.set(False)
        self._block_toggle_cfg.grid(row=0, column=0, sticky="e" if rtl
                                      else "w")
        self._block_warning = ctk.CTkLabel(
            block_row,
            text=self._tr("⚠ نیاز به دسترسی مدیر دارد — در صورت فعال "
                            "بودن، سایت‌های حواس‌پرتی مسدود می‌شوند.",
                            "⚠ Requires admin access — distraction "
                            "sites will be blocked."),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.WARNING, wraplength=420, justify="right"
            if rtl else "left",
        )
        self._block_warning.grid(row=1, column=0, sticky="e" if rtl
                                   else "w", pady=(4, 0))
        # Start button
        self._start_btn = GoldButton(
            self._config_frame, text=self._tr("شروع جلسه تمرکز",
                                                "Start focus session"),
            command=self._on_start, lang=self._lang, height=52,
        )
        self._start_btn.grid(row=7, column=0, sticky="ew",
                               pady=(config.SPACE_LG, 0))

    def _build_active_session(self) -> None:
        """Active session panel — hidden when no session is running."""
        self._active_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._active_frame.grid_columnconfigure(0, weight=1)
        # Interruption count
        self._interrupt_count_label = ctk.CTkLabel(
            self._active_frame, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.WARNING,
        )
        self._interrupt_count_label.grid(row=0, column=0, pady=(
            config.SPACE_SM, 0))
        # Buttons row
        buttons_row = ctk.CTkFrame(self._active_frame, fg_color="transparent")
        buttons_row.grid(row=1, column=0, sticky="ew",
                          pady=(config.SPACE_MD, 0))
        buttons_row.grid_columnconfigure(0, weight=1)
        buttons_row.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Log interruption button
        self._interrupt_btn = GhostButton(
            buttons_row,
            text=self._tr("ثبت وقفه", "Log interruption"),
            command=self._on_interrupt, lang=self._lang, height=44,
        )
        self._interrupt_btn.grid(row=0, column=0 if rtl else 1,
                                   sticky="ew", padx=(0 if rtl else 4,
                                                       4 if rtl else 0))
        # End early button
        self._end_btn = DangerButton(
            buttons_row,
            text=self._tr("پایان زودهنگام", "End early"),
            command=self._on_end_early, lang=self._lang, height=44,
        )
        self._end_btn.grid(row=0, column=1 if rtl else 0,
                             sticky="ew", padx=(4 if rtl else 0,
                                                 0 if rtl else 4))

    def _build_session_stats(self) -> None:
        """Post-session stats card — shown briefly after a session ends."""
        self._stats_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._stats_frame.grid_columnconfigure(0, weight=1)
        self._stats_card = Card(self._stats_frame, lang=self._lang,
                                  padding=config.SPACE_LG)
        self._stats_card.grid(row=0, column=0, sticky="ew")
        self._stats_card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            self._stats_card.content,
            text=self._tr("آمار جلسه", "Session stats"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # Stats grid: 3 stat cards (duration, interruptions, score)
        stats_row = ctk.CTkFrame(self._stats_card.content,
                                   fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew",
                         pady=(config.SPACE_SM, 0))
        for i in range(3):
            stats_row.grid_columnconfigure(i, weight=1, uniform="stat")
        self._stat_duration = StatCard(
            stats_row, label=self._tr("مدت", "Duration"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._stat_duration.grid(row=0, column=0, sticky="nsew",
                                   padx=(0, 4))
        self._stat_interrupts = StatCard(
            stats_row, label=self._tr("وقفه‌ها", "Interruptions"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._stat_interrupts.grid(row=0, column=1, sticky="nsew",
                                     padx=4)
        self._stat_score = StatCard(
            stats_row, label=self._tr("امتیاز تمرکز", "Focus score"),
            value="—", lang=self._lang, padding=config.SPACE_MD,
        )
        self._stat_score.grid(row=0, column=2, sticky="nsew",
                                padx=(4, 0))

    def _build_today_sessions(self) -> None:
        """Today's focus sessions list."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_LG, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("جلسات امروز", "Today's sessions"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        self._today_sessions_frame = ctk.CTkFrame(
            section, fg_color="transparent")
        self._today_sessions_frame.grid(row=1, column=0, sticky="ew",
                                          pady=(config.SPACE_SM, 0))
        self._today_sessions_frame.grid_columnconfigure(0, weight=1)

    def _build_help(self) -> None:
        """Tiny tip line."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=self._tr(
                "حالت تمرکز، ثبت فعالیت با برچسب «تمرکز» است.",
                "Focus mode logs an activity tagged 'focus'."),
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
            "focus.started", "focus.ended", "focus.tick",
            "focus.interruption", "focus.paused", "focus.resumed",
            "language.changed", "data.cleared",
            "activity.added",
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
        # Capture session-ended stats
        try:
            ev_name = kwargs.get("event") or ""
            if "focus.ended" in str(ev_name):
                payload = args[0] if args else {}
                if isinstance(payload, dict):
                    self._last_session_stats = payload
        except Exception:
            pass
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

    def _schedule_tick(self) -> None:
        if self._tick_job is None:
            try:
                self._tick_job = self.after(1000, self._on_tick)
            except Exception:
                self._tick_job = None

    def _on_tick(self) -> None:
        self._tick_job = None
        try:
            self._refresh_timer_only()
        finally:
            self._schedule_tick()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render everything."""
        self._refresh_categories()
        self._refresh_session_view()
        self._refresh_today_sessions()

    def _refresh_timer_only(self) -> None:
        """Lightweight per-second refresh of the timer label."""
        try:
            if focus_mode.is_active():
                remaining = focus_mode.remaining_sec()
                self._timer_label.configure(
                    text=_format_mmss(remaining, self._lang),
                    text_color=config.GOLD)
                # Update session title
                try:
                    title = focus_mode._title or ""  # type: ignore[attr-defined]
                    self._session_title_label.configure(
                        text=title or self._tr("جلسه تمرکز",
                                                 "Focus session"),
                        text_color=config.TEXT_DIM)
                except Exception:
                    pass
                # Update interruption count
                try:
                    count = focus_mode.interruption_count()
                    c_str = (i18n.to_fa_digits(str(count))
                             if self._lang == "fa" else str(count))
                    self._interrupt_count_label.configure(
                        text=f"⚠ {c_str} {self._tr('وقفه', 'interruptions')}",
                        text_color=config.WARNING if count > 0
                                     else config.TEXT_DIM,
                    )
                except Exception:
                    pass
            else:
                # Show selected duration
                self._timer_label.configure(
                    text=_format_mmss(self._selected_duration * 60,
                                       self._lang),
                    text_color=config.GOLD)
                self._session_title_label.configure(text="")
        except Exception:
            pass

    def _refresh_categories(self) -> None:
        """Rebuild the category chip strip."""
        for child in self._cats_strip.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._category_chips = []
        try:
            cats = db.category_list(include_archived=False)
        except Exception:
            cats = []
        rtl = i18n.is_rtl(self._lang)
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

    def _refresh_session_view(self) -> None:
        """Show/hide the config panel vs active-session panel."""
        try:
            is_active = focus_mode.is_active()
        except Exception:
            is_active = False
        try:
            if is_active:
                # Hide config, show active session
                self._config_frame.grid_forget()
                self._stats_frame.grid_forget()
                self._active_frame.grid(row=self._section_row - 2,
                                          column=0, sticky="ew",
                                          padx=config.SPACE_LG,
                                          pady=(0, config.SPACE_MD))
            else:
                # Hide active session, show config
                self._active_frame.grid_forget()
                self._config_frame.grid(row=self._section_row - 2,
                                          column=0, sticky="ew",
                                          padx=config.SPACE_LG,
                                          pady=(0, config.SPACE_MD))
                # Show post-session stats if we just ended
                if self._last_session_stats:
                    self._stats_frame.grid(
                        row=self._section_row - 1, column=0,
                        sticky="ew",
                        padx=config.SPACE_LG,
                        pady=(0, config.SPACE_MD))
                    self._refresh_session_stats()
                else:
                    self._stats_frame.grid_forget()
        except Exception:
            pass
        # Refresh timer label immediately
        self._refresh_timer_only()

    def _refresh_session_stats(self) -> None:
        """Populate the post-session stats card."""
        if not self._last_session_stats:
            return
        s = self._last_session_stats
        try:
            duration_min = int(s.get("duration_min", 0) or 0)
            interruptions = int(s.get("interruptions", 0) or 0)
            # Focus score: 100 - 10*interruptions, clamped 0..100
            score = max(0, min(100, 100 - interruptions * 10))
            dur_str = (f"{i18n.to_fa_digits(str(duration_min)) if self._lang == 'fa' else str(duration_min)} "
                       f"{self._tr('دقیقه', 'min')}")
            int_str = (i18n.to_fa_digits(str(interruptions))
                        if self._lang == "fa" else str(interruptions))
            score_str = (i18n.to_fa_digits(str(score))
                          if self._lang == "fa" else str(score))
            self._stat_duration.set_value(dur_str)
            self._stat_interrupts.set_value(int_str)
            self._stat_score.set_value(score_str)
        except Exception:
            pass

    def _refresh_today_sessions(self) -> None:
        """Rebuild today's sessions list."""
        for child in self._today_sessions_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        try:
            today = time_utils.today_iso()
            # Pull today's focus sessions from the DB (kind='focus').
            # The sessions table stores metadata_json containing the
            # 'kind' marker.  We query directly because db.session_list
            # doesn't support date-range filtering.
            conn = db.get_conn()
            cur = conn.execute(
                "SELECT * FROM sessions "
                "WHERE started_at >= ? AND started_at <= ? "
                "AND metadata_json LIKE '%\"kind\": \"focus\"%' "
                "ORDER BY started_at DESC LIMIT 50",
                (today + "T00:00:00", today + "T23:59:59"),
            )
            rows = cur.fetchall()
            focus_sessions = [
                {k: r[k] for k in r.keys()} for r in rows
            ]
        except Exception:
            focus_sessions = []
        if not focus_sessions:
            EmptyState(
                self._today_sessions_frame, icon="clock",
                title=self._tr("جلسه‌ای نداری",
                                "No sessions yet"),
                subtitle=self._tr("یک جلسه تمرکز را شروع کن",
                                    "Start a focus session"),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_LG)
            return
        rtl = i18n.is_rtl(self._lang)
        for i, s in enumerate(focus_sessions):
            row = ctk.CTkFrame(self._today_sessions_frame,
                                 fg_color=config.CHARCOAL,
                                 corner_radius=config.RADIUS_MD)
            row.grid(row=i, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 4))
            row.grid_columnconfigure(1, weight=1)
            # Start time (HH:MM)
            start_iso = s.get("started_at", "")
            time_str = _format_clock(start_iso, self._lang)
            ctk.CTkLabel(
                row, text=time_str,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
            ).grid(row=0, column=0 if rtl else 2, padx=8, pady=8)
            # Duration + title
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
            info.grid_columnconfigure(0, weight=1)
            dur_min = int(s.get("actual_min", 0) or 0)
            dur_str = (f"{i18n.to_fa_digits(str(dur_min)) if self._lang == 'fa' else str(dur_min)} "
                       f"{self._tr('دقیقه', 'min')}")
            ctk.CTkLabel(
                info, text=dur_str,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0, sticky="e" if rtl else "w")
            # Title + state
            title = (s.get("title") or
                       self._tr("جلسه تمرکز", "Focus session"))
            state = s.get("state", "completed")
            state_label = (self._tr("ناقص", "early-end")
                            if state == "abandoned"
                            else self._tr("کامل", "complete"))
            ctk.CTkLabel(
                info, text=f"{title}  •  {state_label}",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            ).grid(row=1, column=0, sticky="e" if rtl else "w",
                    pady=(2, 0))

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_start(self) -> None:
        """Start a new focus session."""
        try:
            title = self._title_entry.get().strip() or self._tr(
                "تمرکز عمیق", "Deep focus")
            block = bool(self._block_toggle_cfg.value) if hasattr(
                self._block_toggle_cfg, "value") else False
            focus_mode.start(
                duration_min=self._selected_duration,
                title=title,
                block_internet=block,
            )
            self._last_session_stats = None
            self._show_toast(self._tr("جلسه تمرکز شروع شد",
                                        "Focus session started"))
        except Exception:
            self._show_toast(self._tr("خطا در شروع", "Start failed"))
        self.refresh()

    def _on_end_early(self) -> None:
        try:
            self._last_session_stats = focus_mode.end(early=True)
            self._show_toast(self._tr("جلسه پایان یافت",
                                        "Session ended"))
        except Exception:
            pass
        self.refresh()

    def _on_interrupt(self) -> None:
        try:
            count = focus_mode.add_interruption()
            c_str = (i18n.to_fa_digits(str(count))
                     if self._lang == "fa" else str(count))
            self._show_toast(
                self._tr("وقفه ثبت شد", "Interruption logged"))
        except Exception:
            pass
        self._refresh_timer_only()

    def _on_duration_tap(self, dur: int) -> None:
        self._selected_duration = dur
        # Update button highlights
        for i, b in enumerate(self._duration_buttons):
            d = _DURATION_PRESETS[i]
            try:
                b.configure(
                    fg_color=(config.GOLD if d == dur
                                else config.CHARCOAL),
                    text_color=(config.MATTE_BLACK if d == dur
                                  else config.TEXT),
                    border_color=(config.GOLD if d == dur
                                    else config.SURFACE_HI),
                )
            except Exception:
                pass
        # Update timer label
        self._refresh_timer_only()

    def _on_category_tap(self, cid: int) -> None:
        self._selected_category_id = cid
        self._refresh_categories()

    def _toggle_settings(self) -> None:
        self._settings_visible = not self._settings_visible
        try:
            if self._settings_visible:
                self._settings_frame.grid(row=0, column=0, sticky="ew",
                                            padx=config.SPACE_LG,
                                            pady=(config.SPACE_MD, 0))
                self._settings_frame.tkraise()
            else:
                self._settings_frame.grid_forget()
        except Exception:
            pass

    def _on_block_toggle(self, value: bool) -> None:
        try:
            focus_mode.update_settings(block_internet=bool(value))
        except Exception:
            pass

    def _on_block_toggle_cfg(self, value: bool) -> None:
        # Just store locally; applied on start
        pass

    def _apply_settings(self) -> None:
        try:
            dur = int(self._default_dur_entry.get() or
                       DEFAULT_DURATION_MIN)
            focus_mode.update_settings(default_duration_min=dur)
            self._show_toast(self._tr("تنظیمات ذخیره شد",
                                        "Settings saved"))
        except Exception:
            self._show_toast(self._tr("ورودی نامعتبر",
                                        "Invalid input"))

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
    print("FocusScreen module: minimalist timer + config panel + "
          "active session view + post-session stats + today's sessions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
