"""
rask.ui.widgets.live_timer
==========================

Live timer widget for the home screen.

Shows the current activity title, the elapsed time in large gold digits,
and pause/resume/stop buttons.  Subscribes to ``timer_service`` events
automatically and persists across tab switches.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers, event_bus
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .buttons import GoldButton, GhostButton, IconButton

__all__ = ["LiveTimer"]


# =============================================================================
# === LiveTimer                                                             ===
# =============================================================================

class LiveTimer(ctk.CTkFrame):
    """Compact timer display for the home screen.

    Auto-subscribes to ``timer.tick``, ``timer.started``,
    ``timer.paused``, ``timer.resumed``, ``timer.stopped`` events on the
    shared :data:`event_bus.bus` singleton, so any timer state change
    anywhere in the app will refresh this widget.

    Call :meth:`set_service` once at startup to wire up the underlying
    :class:`rask.services.timer_service.TimerService`.  If you don't,
    the widget still works but won't drive the service itself — only
    display state.
    """

    def __init__(
        self,
        master: Any = None,
        service: Any = None,
        lang: str = "fa",
        on_stopped: Optional[Callable[[dict], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.GOLD_DIM)
        kwargs.setdefault("corner_radius", config.RADIUS_LG)
        super().__init__(master, **kwargs)
        self._service = service
        self._lang = lang
        self._on_stopped = on_stopped
        self._pulse_job = None
        self._tick_job = None
        self._build()
        self._subscribe_events()
        # Initial sync
        self.after(100, self._sync_from_service)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        self.grid_columnconfigure(0, weight=1)
        # Title row
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        # Activity icon
        icon = ctk.CTkLabel(title_row, text="", width=24, height=24,
                             fg_color="transparent")
        img = _icons.icon("clock", 18, color=config.GOLD)
        if img is not None:
            icon.configure(image=img)
        else:
            icon.configure(text=_icons.icon_glyph("clock"),
                            text_color=config.GOLD)
        icon.pack(side="right" if rtl else "left", padx=(0, 6))
        self._title_label = ctk.CTkLabel(
            title_row, text="فعالیت در حال اجرا" if self._lang == "fa"
                            else "Running activity",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._title_label.pack(side="right" if rtl else "left", fill="x",
                                expand=True)
        # Elapsed time
        self._time_label = ctk.CTkLabel(
            self, text="00:00:00",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._time_label.grid(row=1, column=0, pady=(4, 8))
        # Buttons row
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)
        # Pause/Resume button
        self._pause_btn = GoldButton(
            btn_row, text="توقف موقت" if self._lang == "fa" else "Pause",
            command=self._toggle_pause, lang=self._lang,
            height=32, font_size=config.FONT_SIZE_SMALL,
            icon_name="pause", icon_size=14,
        )
        self._pause_btn.grid(row=0, column=0, sticky="ew", padx=2)
        # Stop button
        self._stop_btn = GhostButton(
            btn_row, text="پایان" if self._lang == "fa" else "Stop",
            command=self._stop, lang=self._lang,
            height=32, font_size=config.FONT_SIZE_SMALL,
            icon_name="stop", icon_size=14,
        )
        self._stop_btn.grid(row=0, column=1, sticky="ew", padx=2)
        # Cancel button
        cancel_btn = ctk.CTkButton(
            btn_row, text="لغو" if self._lang == "fa" else "Cancel",
            command=self._cancel,
            fg_color="transparent", hover_color=config.SURFACE_HI,
            text_color=config.TEXT_DIM,
            border_width=0, corner_radius=config.RADIUS_PILL,
            height=32, cursor="hand2",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
        )
        cancel_btn.grid(row=0, column=2, sticky="ew", padx=2)

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        try:
            bus = event_bus.bus
            bus.subscribe("timer.started", lambda *a, **k: self._sync_from_service())
            bus.subscribe("timer.paused", lambda *a, **k: self._sync_from_service())
            bus.subscribe("timer.resumed", lambda *a, **k: self._sync_from_service())
            bus.subscribe("timer.stopped", lambda *a, **k: self._on_timer_stopped(*a, **k))
            bus.subscribe("timer.tick", lambda *a, **k: self._on_tick(*a, **k))
        except Exception:
            pass

    def _on_timer_stopped(self, *args: Any, **kwargs: Any) -> None:
        # Timer stopped — hide self and notify callback
        try:
            self.grid_remove()
        except Exception:
            pass
        if self._on_stopped and args:
            try:
                self._on_stopped(args[0] if args and isinstance(args[0], dict)
                                  else {})
            except Exception:
                pass

    def _on_tick(self, *args: Any, **kwargs: Any) -> None:
        # args = (elapsed_sec, running) per timer_service listener contract
        try:
            if args:
                elapsed = int(args[0])
                running = bool(args[1]) if len(args) > 1 else True
                self._update_display(elapsed, running)
            else:
                self._sync_from_service()
        except Exception:
            self._sync_from_service()

    # ------------------------------------------------------------------
    # Service sync
    # ------------------------------------------------------------------
    def set_service(self, service: Any) -> None:
        self._service = service
        self._sync_from_service()

    def _sync_from_service(self) -> None:
        if not self._service:
            return
        try:
            state = self._service.get_state()  # type: ignore[attr-defined]
            if not state.get("started_at"):
                self.grid_remove()
                return
            self.grid()  # un-hide
            elapsed = int(state.get("elapsed_sec", 0))
            running = bool(state.get("running"))
            title = state.get("title", "")
            if title:
                self._title_label.configure(text=title)
            self._update_display(elapsed, running)
        except Exception:
            pass

    def _update_display(self, elapsed_sec: int, running: bool) -> None:
        try:
            formatted = _format_timer(elapsed_sec, self._lang)
            self._time_label.configure(text=formatted)
            # Update pause button text/icon
            if running:
                txt = "توقف موقت" if self._lang == "fa" else "Pause"
                icon = "pause"
            else:
                txt = "ادامه" if self._lang == "fa" else "Resume"
                icon = "play"
            self._pause_btn.configure(text=txt)
            # Pulse animation when running
            if running:
                self._start_pulse()
            else:
                self._stop_pulse()
        except Exception:
            pass

    def _start_pulse(self) -> None:
        if self._pulse_job:
            return
        self._pulse_step = 0
        self._pulse_total = max(2, config.ANIM_SLOW // 30)
        self._tick_pulse()

    def _stop_pulse(self) -> None:
        if self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        try:
            self._pause_btn.configure(border_width=0)
        except Exception:
            pass

    def _tick_pulse(self) -> None:
        self._pulse_step += 1
        t = (self._pulse_step % self._pulse_total) / self._pulse_total
        # Use a sine wave for gentle pulse
        import math
        alpha = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
        try:
            # Toggle border color between gold and gold-bright
            border = helpers.mix_colors(config.GOLD, config.GOLD_BRIGHT, alpha)
            self._pause_btn.configure(border_color=border,
                                       border_width=2)
        except Exception:
            pass
        self._pulse_job = self.after(30, self._tick_pulse)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _toggle_pause(self) -> None:
        if not self._service:
            return
        try:
            if self._service.is_running():  # type: ignore[attr-defined]
                self._service.pause()  # type: ignore[attr-defined]
            else:
                self._service.resume()  # type: ignore[attr-defined]
        except Exception:
            pass
        self._sync_from_service()

    def _stop(self) -> None:
        if not self._service:
            return
        try:
            self._service.stop(save=True)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._sync_from_service()

    def _cancel(self) -> None:
        if not self._service:
            return
        try:
            self._service.stop(save=False)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._sync_from_service()


# =============================================================================
# === Formatting helper                                                      ===
# =============================================================================

def _format_timer(seconds: int, lang: str = "fa") -> str:
    """Return ``HH:MM:SS`` (or ``MM:SS`` if < 1h)."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        s = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        s = f"{minutes:02d}:{secs:02d}"
    if lang == "fa":
        s = i18n.to_fa_digits(s)
    return s


def _self_test() -> int:
    classes = [LiveTimer]
    print(f"Live timer module: {len(classes)} classes registered.")
    # Test formatter
    assert _format_timer(0, "en") == "00:00"
    assert _format_timer(65, "en") == "01:05"
    assert _format_timer(3661, "en") == "01:01:01"
    assert _format_timer(65, "fa") == "۰۱:۰۵"
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
