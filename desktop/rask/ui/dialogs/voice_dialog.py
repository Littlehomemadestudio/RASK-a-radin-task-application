"""
rask.ui.dialogs.voice_dialog
============================

Modal voice-input dialog.

Wraps :data:`rask.services.voice_service` in a friendly UI:

  * Large pulsing microphone icon (animated ring while listening)
  * Status label: ``"Tap to speak"`` -> ``"Listening..."`` ->
    ``"Processing..."`` -> ``"Did you say: X?"``
  * Waveform-style animated bars while listening (decorative)
  * Cancel / Retry / Confirm buttons

The dialog gracefully degrades when ``voice_service`` is unavailable
(no microphone, missing ``speech_recognition`` / ``pyaudio``): the
status label shows "ورودی صوتی در دسترس نیست" and the Confirm button
lets the user manually type the title in the host dialog.

Result
------
``self.result`` is a dict::

    {"text": str,         # recognized text (may be empty)
     "confirmed": bool}   # True if the user pressed Confirm

or ``None`` if cancelled.
"""
from __future__ import annotations

import math
import threading
from typing import Any, Callable, Dict, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers
from ...services import voice_service
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.dividers import Divider

__all__ = ["VoiceDialog"]


# =============================================================================
# === States                                                                 ===
# =============================================================================

STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_PROCESSING = "processing"
STATE_CONFIRM = "confirm"
STATE_ERROR = "error"
STATE_UNAVAILABLE = "unavailable"


# =============================================================================
# === Pulsing mic icon                                                       ===
# =============================================================================

class _PulsingMic(ctk.CTkFrame):
    """Large microphone icon with a pulsing gold ring animation."""

    def __init__(
        self,
        master: Any,
        size: int = 120,
        accent: str = config.GOLD,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("width", size + 60)
        kwargs.setdefault("height", size + 60)
        super().__init__(master, **kwargs)
        self._size = size
        self._accent = accent
        self._pulse_job = None
        self._pulse_step = 0
        self._active = False
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        # Outer ring (animated scale)
        self._ring = ctk.CTkFrame(
            self, width=size + 40, height=size + 40,
            fg_color="transparent",
            border_width=2, border_color=accent,
            corner_radius=(size + 40) // 2,
        )
        self._ring.grid(row=0, column=0)
        # Inner circle with mic icon
        self._inner = ctk.CTkFrame(
            self, width=size, height=size,
            fg_color=config.SURFACE,
            border_width=2, border_color=accent,
            corner_radius=size // 2,
        )
        self._inner.grid(row=0, column=0)
        self._inner.grid_rowconfigure(0, weight=1)
        self._inner.grid_columnconfigure(0, weight=1)
        # Mic icon
        self._icon_lbl = ctk.CTkLabel(self._inner, text="")
        self._icon_lbl.grid(row=0, column=0)
        img = _icons.icon("mic", size // 2, color=accent)
        if img is not None:
            self._icon_lbl.configure(image=img)
        else:
            self._icon_lbl.configure(
                text=_icons.icon_glyph("mic"),
                text_color=accent,
                font=_theme.theme.font(size=size // 2, weight="bold",
                                         lang="en"))

    # ------------------------------------------------------------------
    def start_pulse(self) -> None:
        self._active = True
        self._pulse_step = 0
        self._tick_pulse()

    def stop_pulse(self) -> None:
        self._active = False
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        try:
            self._ring.configure(border_color=self._accent)
        except Exception:
            pass

    def _tick_pulse(self) -> None:
        if not self._active:
            return
        self._pulse_step += 1
        # 2-second pulse cycle
        t = (self._pulse_step % 60) / 60.0
        # Smooth ease-in-out using sine
        alpha = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        try:
            # CTk doesn't support per-widget alpha; we vary the border
            # colour between dim and bright gold.
            color = helpers.mix_colors(config.GOLD_DIM, config.GOLD_BRIGHT,
                                         alpha)
            self._ring.configure(border_color=color)
        except Exception:
            pass
        self._pulse_job = self.after(33, self._tick_pulse)


# =============================================================================
# === Waveform (decorative bars)                                             ===
# =============================================================================

class _Waveform(ctk.CTkFrame):
    """Decorative animated equalizer bars shown while listening."""

    def __init__(
        self,
        master: Any,
        bars: int = 7,
        bar_width: int = 6,
        bar_gap: int = 6,
        max_height: int = 40,
        color: str = config.GOLD,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("height", max_height + 8)
        super().__init__(master, **kwargs)
        self._bars = bars
        self._bar_width = bar_width
        self._bar_gap = bar_gap
        self._max_height = max_height
        self._color = color
        self._active = False
        self._tick_job = None
        self._step = 0
        self._bar_widgets = []
        for i in range(bars):
            b = ctk.CTkFrame(
                self, width=bar_width, height=max_height // 4,
                fg_color=color, corner_radius=bar_width // 2,
            )
            b.pack(side="left", padx=bar_gap // 2, pady=4)
            self._bar_widgets.append(b)

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._active = True
        self._step = 0
        self._tick()

    def stop(self) -> None:
        self._active = False
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        # Reset to small
        for b in self._bar_widgets:
            try:
                b.configure(height=self._max_height // 4)
            except Exception:
                pass

    def _tick(self) -> None:
        if not self._active:
            return
        self._step += 1
        import random
        for i, b in enumerate(self._bar_widgets):
            try:
                # Pseudo-random heights that look like audio levels
                phase = (self._step + i * 3) * 0.5
                level = 0.5 + 0.5 * math.sin(phase) + 0.2 * random.random()
                level = max(0.1, min(1.0, level))
                h = max(4, int(self._max_height * level))
                b.configure(height=h)
            except Exception:
                pass
        self._tick_job = self.after(80, self._tick)


# =============================================================================
# === VoiceDialog                                                            ===
# =============================================================================

class VoiceDialog(BaseDialog):
    """Modal voice input dialog.

    Parameters
    ----------
    master
        Parent widget.
    lang
        Recognition language (e.g. ``"fa"`` -> ``"fa-IR"``).
    on_result
        Callback invoked with ``{"text": str, "confirmed": bool}`` on
        close.

    Result
    ------
    ``self.result`` is a dict (see above) or ``None`` if cancelled.
    """

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._state = STATE_IDLE
        self._recognized_text = ""
        self._listen_thread: Optional[threading.Thread] = None
        self._waveform = None
        kwargs.setdefault("height", 460)
        kwargs.setdefault("width", 440)
        kwargs.setdefault("close_on_overlay", False)
        super().__init__(
            master,
            title=(i18n.t("voiceInput", lang) if lang == "fa"
                    else "Voice Input"),
            lang=lang, **kwargs,
        )
        if on_result:
            self.on_result(on_result)
        # If voice_service is available, auto-start listening shortly
        # after the dialog finishes animating in.
        if voice_service.is_available():
            try:
                self.after(280, self._start_listening)
            except Exception:
                pass
        else:
            self._set_state(STATE_UNAVAILABLE)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Mic illustration
        self._mic = _PulsingMic(self._content, size=100,
                                  accent=config.GOLD)
        self._mic.pack(anchor="center", pady=(8, 12))
        # Waveform
        self._waveform = _Waveform(self._content, bars=7)
        self._waveform.pack(anchor="center", pady=(0, 12))
        # Status label
        self._status = ctk.CTkLabel(
            self._content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            wraplength=360,
            justify="center",
        )
        self._status.pack(fill="x", pady=(0, 8))
        # Recognized text preview (shown in STATE_CONFIRM)
        self._preview = ctk.CTkLabel(
            self._content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            wraplength=360,
            justify="right" if rtl else "left",
        )
        self._preview.pack(fill="x", pady=(0, 8))
        # Divider
        Divider(self._content).pack(fill="x", pady=(4, 12))
        # Buttons row
        self._btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        self._btn_row.pack(fill="x")
        self._btn_row.grid_columnconfigure(0, weight=1)
        self._btn_row.grid_columnconfigure(1, weight=1)
        self._btn_row.grid_columnconfigure(2, weight=1)
        # Initially just a cancel button
        self._cancel_btn = GhostButton(
            self._btn_row,
            text=(i18n.t("cancel", self._lang)
                   if i18n.t("cancel", self._lang) != "cancel"
                   else "انصراف"),
            command=self._on_cancel,
            lang=self._lang, height=42,
        )
        self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)
        self._retry_btn = TextButton(
            self._btn_row,
            text=(i18n.t("tryAgain", self._lang)
                   if i18n.t("tryAgain", self._lang) != "tryAgain"
                   else "تلاش دوباره"),
            command=self._start_listening,
            lang=self._lang, height=42,
            color=config.TEXT_DIM, hover_color=config.GOLD,
        )
        self._confirm_btn = GoldButton(
            self._btn_row,
            text=(i18n.t("confirm", self._lang)
                   if i18n.t("confirm", self._lang) != "confirm"
                   else "تأیید"),
            command=self._on_confirm,
            lang=self._lang, height=42,
            icon_name="check", icon_size=16,
        )
        # Set initial state
        self._set_state(STATE_IDLE)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        self._state = state
        try:
            self._update_ui_for_state()
        except Exception:
            pass

    def _update_ui_for_state(self) -> None:
        s = self._state
        rtl = i18n.is_rtl(self._lang)
        # Default: hide all buttons except cancel
        self._cancel_btn.grid_forget() if False else None
        # Remove retry/confirm from grid (we'll re-add as needed)
        try:
            self._retry_btn.grid_forget()
            self._confirm_btn.grid_forget()
        except Exception:
            pass

        if s == STATE_IDLE:
            self._status.configure(
                text=("برای صحبت ضربه بزن" if self._lang == "fa"
                       else "Tap to speak"),
                text_color=config.GOLD)
            self._preview.configure(text="")
            self._mic.stop_pulse()
            self._waveform.stop()
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)
            # Show a "Start" button in the centre
            try:
                if not hasattr(self, "_start_btn"):
                    self._start_btn = GoldButton(
                        self._btn_row,
                        text=("شروع" if self._lang == "fa" else "Start"),
                        command=self._start_listening,
                        lang=self._lang, height=42,
                        icon_name="mic", icon_size=16,
                    )
                self._start_btn.grid(row=0, column=1, sticky="ew", padx=2)
            except Exception:
                pass

        elif s == STATE_LISTENING:
            self._status.configure(
                text=(i18n.t("voiceListening", self._lang)
                       if i18n.t("voiceListening", self._lang)
                       != "voiceListening"
                       else "در حال شنیدن..."),
                text_color=config.GOLD_BRIGHT)
            self._preview.configure(text="")
            self._mic.start_pulse()
            self._waveform.start()
            try:
                if hasattr(self, "_start_btn"):
                    self._start_btn.grid_forget()
            except Exception:
                pass
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)

        elif s == STATE_PROCESSING:
            self._status.configure(
                text=(i18n.t("processing", self._lang)
                       if i18n.t("processing", self._lang)
                       != "processing"
                       else "در حال پردازش..."),
                text_color=config.GOLD)
            self._preview.configure(text="")
            self._mic.stop_pulse()
            self._waveform.stop()
            try:
                if hasattr(self, "_start_btn"):
                    self._start_btn.grid_forget()
            except Exception:
                pass
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)

        elif s == STATE_CONFIRM:
            prompt = ("آیا منظورت این بود:" if self._lang == "fa"
                       else "Did you say:")
            self._status.configure(text=prompt, text_color=config.GOLD)
            self._preview.configure(text=f"«{self._recognized_text}»"
                                     if self._recognized_text else "—")
            self._mic.stop_pulse()
            self._waveform.stop()
            try:
                if hasattr(self, "_start_btn"):
                    self._start_btn.grid_forget()
            except Exception:
                pass
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)
            self._retry_btn.grid(row=0, column=1, sticky="ew", padx=2)
            self._confirm_btn.grid(row=0, column=2, sticky="ew", padx=2)

        elif s == STATE_ERROR:
            err = (i18n.t("voiceError", self._lang)
                    if i18n.t("voiceError", self._lang) != "voiceError"
                    else "خطای ورودی صوتی")
            self._status.configure(text=err, text_color=config.DANGER)
            self._preview.configure(text="")
            self._mic.stop_pulse()
            self._waveform.stop()
            try:
                if hasattr(self, "_start_btn"):
                    self._start_btn.grid_forget()
            except Exception:
                pass
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)
            self._retry_btn.grid(row=0, column=1, sticky="ew", padx=2)

        elif s == STATE_UNAVAILABLE:
            msg = (i18n.t("voiceNotAvailable", self._lang)
                    if i18n.t("voiceNotAvailable", self._lang)
                    != "voiceNotAvailable"
                    else "ورودی صوتی در دسترس نیست")
            self._status.configure(text=msg, text_color=config.WARNING)
            self._preview.configure(text="")
            self._mic.stop_pulse()
            self._waveform.stop()
            try:
                if hasattr(self, "_start_btn"):
                    self._start_btn.grid_forget()
            except Exception:
                pass
            self._cancel_btn.grid(row=0, column=0, sticky="ew", padx=2)

    # ------------------------------------------------------------------
    # Listen (background thread)
    # ------------------------------------------------------------------
    def _start_listening(self) -> None:
        if not voice_service.is_available():
            self._set_state(STATE_UNAVAILABLE)
            return
        if self._state == STATE_LISTENING:
            return
        self._set_state(STATE_LISTENING)
        # Run the (blocking) listen() call in a worker thread so the
        # UI animation stays smooth.
        self._listen_thread = threading.Thread(
            target=self._listen_worker, daemon=True,
        )
        self._listen_thread.start()

    def _listen_worker(self) -> None:
        def on_result(text: str) -> None:
            self._recognized_text = text or ""
            try:
                self.after(0, lambda: self._set_state(STATE_CONFIRM))
            except Exception:
                pass

        def on_error(msg: str) -> None:
            try:
                self.after(0, lambda: self._set_state(STATE_ERROR))
            except Exception:
                pass

        def on_end() -> None:
            # If still in LISTENING state (no result yet), transition
            # to PROCESSING.
            try:
                if self._state == STATE_LISTENING:
                    self.after(0, lambda: self._set_state(STATE_PROCESSING))
            except Exception:
                pass

        # Slight delay so the "Listening..." state has time to render.
        try:
            voice_service.listen(
                callback=on_result,
                lang=self._lang,
                on_error=on_error,
                on_end=on_end,
            )
        except Exception:
            try:
                self.after(0, lambda: self._set_state(STATE_ERROR))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _on_confirm(self) -> None:
        self.close({
            "text": self._recognized_text,
            "confirmed": True,
        })

    def _on_cancel(self) -> None:
        # Stop any in-progress listening
        try:
            voice_service.cancel()
        except Exception:
            pass
        self.close(None)

    # ------------------------------------------------------------------
    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _destroy(self) -> None:  # type: ignore[override]
        try:
            voice_service.cancel()
        except Exception:
            pass
        super()._destroy()


def _self_test() -> int:
    print("voice_dialog module: 1 class registered (VoiceDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
