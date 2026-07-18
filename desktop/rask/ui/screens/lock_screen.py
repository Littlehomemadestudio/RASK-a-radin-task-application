"""
rask.ui.screens.lock_screen
===========================

Full-screen PIN-pad lock view shown when the app is locked.

Mirrors ``web/index.html`` ``#lock`` and the corresponding
``maybeShowLock`` function in ``web/js/app.js``.

Features
--------
* Centered circular logo (gold-bordered ``"R"`` glyph, 120×120)
* App name ``"رَسک"`` + subtitle ``"کد پین را وارد کن"``
* 4-dot indicator showing entered digits (filled gold when complete)
* 3×4 number pad with Persian digits (۰-۹) on each button
* ``Delete`` (backspace) button on the bottom-trailing corner
* ``Biometric`` button on the bottom-leading corner — only shown when
  ``lock_mode == "biometric"`` and biometric auth is available
* ``Forgot PIN`` text link below the pad — calls ``on_forgot``
* Shake animation on wrong PIN — the dot row wiggles left/right 4
  times over 400ms, the dots flash red, and the pad is cleared
* Subtle gold border glow around the whole view (pulsing 3s cycle)
* On correct PIN, calls ``on_unlock`` exactly once
* ``Enter`` key on the keyboard submits; ``BackSpace`` deletes

Layout (RTL, Persian)
---------------------

        ┌──────────────────────────────────┐
        │              ╭─────╮              │
        │              │  R  │              │
        │              ╰─────╯              │
        │                                   │
        │              رَسک                  │
        │      کد پین را وارد کن             │
        │                                   │
        │           ●  ●  ○  ○              │
        │                                   │
        │     ┌────┬────┬────┐              │
        │     │ ۱  │ ۲  │ ۳  │              │
        │     ├────┼────┼────┤              │
        │     │ ۴  │ ۵  │ ۶  │              │
        │     ├────┼────┼────┤              │
        │     │ ۷  │ ۸  │ ۹  │              │
        │     ├────┼────┼────┤              │
        │     │🔒  │ ۰  │ ⌫  │              │
        │     └────┴────┴────┘              │
        │                                   │
        │         فراموشی پین؟              │
        └──────────────────────────────────┘
"""
from __future__ import annotations

import math
from typing import Any, Callable, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers
from ...core import pin as _pin
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import GhostButton, TextButton

__all__ = ["LockView"]


# =============================================================================
# === PIN pad button                                                         ===
# =============================================================================

class _PadButton(ctk.CTkButton):
    """Single PIN-pad button — circular, large, gold-on-dark.

    Renders Persian digits by default (۰-۹).  The delete and
    biometric buttons use icons instead.
    """

    def __init__(
        self,
        master: Any,
        text: str = "",
        icon_name: Optional[str] = None,
        command: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        size: int = 72,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("hover_color", config.SURFACE_HI)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        kwargs.setdefault("corner_radius", size // 2)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("font", _theme.theme.font(
            size=config.FONT_SIZE_HEADING, weight="bold", lang=lang))
        final_text = text
        if icon_name:
            img = _icons.icon(icon_name, int(size * 0.4),
                              color=config.GOLD)
            if img is not None:
                kwargs.setdefault("image", img)
                final_text = ""
            else:
                final_text = _icons.icon_glyph(icon_name)
                kwargs.setdefault("text_color", config.GOLD)
        super().__init__(master, text=final_text, command=command, **kwargs)
        self._hover_normal_fg = config.CHARCOAL
        self._hover_target_fg = config.SURFACE_HI
        self._hover_normal_text = config.TEXT
        self._hover_target_text = config.GOLD
        self._bind_hover()

    def _bind_hover(self) -> None:
        try:
            self.bind("<Enter>", self._on_enter, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
        except Exception:
            pass

    def _on_enter(self, _evt: Any = None) -> None:
        try:
            self.configure(fg_color=self._hover_target_fg,
                            text_color=self._hover_target_text)
        except Exception:
            pass

    def _on_leave(self, _evt: Any = None) -> None:
        try:
            self.configure(fg_color=self._hover_normal_fg,
                            text_color=self._hover_normal_text)
        except Exception:
            pass


# =============================================================================
# === LockView                                                              ===
# =============================================================================

class LockView(ctk.CTkFrame):
    """Full-screen PIN-pad lock view.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.
    lang
        ``"fa"`` (default) or ``"en"``.
    pin_hash
        The stored PBKDF2-SHA256 PIN hash (Django format).  If ``None``,
        the view will accept any non-empty PIN (used in tests).
    lock_mode
        ``"pin"``, ``"biometric"``, or ``"none"``.  When ``"biometric"``,
        an extra biometric button is shown.
    on_unlock
        Callback invoked once when the correct PIN is entered (or
        biometric auth succeeds).
    on_forgot
        Callback invoked when the user taps the ``Forgot PIN`` link.
    biometric_available
        Whether the host platform supports biometric authentication.
        Defaults to ``False`` (Linux desktop rarely does).
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        pin_hash: Optional[str] = None,
        lock_mode: str = "pin",
        on_unlock: Optional[Callable[[], Any]] = None,
        on_forgot: Optional[Callable[[], Any]] = None,
        biometric_available: bool = False,
        max_digits: int = 4,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._pin_hash = pin_hash
        self._lock_mode = lock_mode
        self._on_unlock = on_unlock
        self._on_forgot = on_forgot
        self._biometric_available = biometric_available
        self._max_digits = max(4, int(max_digits))
        self._digits: List[str] = []
        self._shake_job: Optional[Any] = None
        self._glow_job: Optional[Any] = None
        self._unlocked: bool = False
        self._build()
        self._start_glow()
        # Bind keyboard for desktop convenience
        try:
            self.bind_all("<Key>", self._on_key, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Lay out the lock view: logo, title, dots, pad, forgot link."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)   # top spacer
        self.grid_rowconfigure(1, weight=0)   # logo
        self.grid_rowconfigure(2, weight=0)   # app name
        self.grid_rowconfigure(3, weight=0)   # subtitle
        self.grid_rowconfigure(4, weight=0)   # dots
        self.grid_rowconfigure(5, weight=1)   # middle spacer
        self.grid_rowconfigure(6, weight=0)   # pad
        self.grid_rowconfigure(7, weight=0)   # forgot link
        self.grid_rowconfigure(8, weight=1)   # bottom spacer

        # --- Logo (drawn on a canvas so we can animate the border glow) ---
        self._logo_canvas = ctk.CTkCanvas(
            self, width=120, height=120,
            bg=config.MATTE_BLACK, highlightthickness=0, borderwidth=0,
        )
        self._logo_canvas.grid(row=1, column=0, pady=(0, config.SPACE_MD))
        self._draw_logo(0.0)

        # --- App name ---
        self._name_label = ctk.CTkLabel(
            self, text=i18n.t("appName", self._lang),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._name_label.grid(row=2, column=0, pady=(0, config.SPACE_SM))

        # --- Subtitle ---
        self._subtitle_label = ctk.CTkLabel(
            self, text=i18n.t("enterPin", self._lang),
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        )
        self._subtitle_label.grid(row=3, column=0, pady=(0, config.SPACE_LG))

        # --- Dots row ---
        self._dots_frame = ctk.CTkFrame(self, fg_color="transparent",
                                          height=24)
        self._dots_frame.grid(row=4, column=0, pady=(0, config.SPACE_XL))
        self._dots_frame.grid_columnconfigure(0, weight=1)
        self._dots_row = ctk.CTkFrame(self._dots_frame, fg_color="transparent")
        self._dots_row.grid(row=0, column=0)
        self._dot_widgets: List[ctk.CTkFrame] = []
        for i in range(self._max_digits):
            d = ctk.CTkFrame(
                self._dots_row, width=14, height=14,
                fg_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_PILL,
            )
            d.grid(row=0, column=i, padx=8)
            self._dot_widgets.append(d)

        # --- Number pad (3×4) ---
        self._pad_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._pad_frame.grid(row=6, column=0, padx=config.SPACE_XL,
                              pady=(0, config.SPACE_MD))
        for col in range(3):
            self._pad_frame.grid_columnconfigure(col, weight=1, uniform="pad")
        # Build pad rows: 1-2-3, 4-5-6, 7-8-9, [bio]-0-[del]
        rtl = i18n.is_rtl(self._lang)
        fa_digits = "۰۱۲۳۴۵۶۷۸۹"
        en_digits = "0123456789"
        digit_glyphs = fa_digits if self._lang == "fa" else en_digits
        # 1..9 in row-major
        positions = [(r, c) for r in range(3) for c in range(3)]
        for i, (r, c) in enumerate(positions, start=1):
            txt = digit_glyphs[i]
            self._make_pad_button(txt, str(i), row=r, col=c)
        # Last row: bio / 0 / del
        last_row = 3
        bio_col = 0 if rtl else 2
        del_col = 2 if rtl else 0
        zero_col = 1
        # 0
        self._make_pad_button(digit_glyphs[0], "0",
                               row=last_row, col=zero_col)
        # Delete
        del_btn = _PadButton(
            self._pad_frame, icon_name="back",
            command=self._on_delete, lang=self._lang,
            size=72,
        )
        del_btn.grid(row=last_row, column=del_col, padx=8, pady=6,
                       sticky="nsew")
        # Biometric (only if enabled)
        if (self._lock_mode == "biometric" or self._biometric_available):
            bio_btn = _PadButton(
                self._pad_frame, icon_name="lock",
                command=self._on_biometric, lang=self._lang,
                size=72,
            )
            bio_btn.grid(row=last_row, column=bio_col, padx=8, pady=6,
                          sticky="nsew")
        else:
            # Empty placeholder to keep the grid balanced
            ph = ctk.CTkFrame(self._pad_frame, width=72, height=72,
                               fg_color="transparent")
            ph.grid(row=last_row, column=bio_col, padx=8, pady=6,
                     sticky="nsew")

        # --- Forgot PIN link ---
        self._forgot_btn = TextButton(
            self, text=i18n.t("forgotPin", self._lang) if "forgotPin" in _catalog_keys()
            else "فراموشی پین؟",
            command=self._on_forgot_tap,
            lang=self._lang,
            color=config.TEXT_DIM,
            hover_color=config.GOLD,
            height=32,
            font_size=config.FONT_SIZE_SMALL,
        )
        self._forgot_btn.grid(row=7, column=0, pady=(config.SPACE_MD,
                                                       config.SPACE_LG))

    def _make_pad_button(self, text: str, digit: str, row: int,
                          col: int) -> None:
        """Create and grid a digit pad button."""
        btn = _PadButton(
            self._pad_frame, text=text,
            command=lambda d=digit: self._on_digit(d),
            lang=self._lang, size=72,
        )
        btn.grid(row=row, column=col, padx=8, pady=6, sticky="nsew")

    # ------------------------------------------------------------------
    # Logo drawing (with pulsing glow)
    # ------------------------------------------------------------------
    def _draw_logo(self, t_ms: float) -> None:
        """Paint the logo on ``self._logo_canvas`` at animation time ``t_ms``."""
        try:
            self._logo_canvas.delete("all")
        except Exception:
            return
        try:
            w = int(self._logo_canvas.cget("width"))
            h = int(self._logo_canvas.cget("height"))
        except Exception:
            w, h = 120, 120
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0 - 8.0
        # Pulsing halo (3s cycle)
        phase = (t_ms % 3000.0) / 3000.0
        glow_a = 0.10 + 0.18 * (0.5 + 0.5 * math.sin(phase * 2.0 * math.pi))
        for i in range(4):
            gr = r + 4.0 + i * 4.0
            ga = max(0.0, glow_a * (1.0 - i / 4.0))
            gc = helpers.mix_colors(config.MATTE_BLACK, config.GOLD, ga)
            try:
                self._logo_canvas.create_oval(
                    cx - gr, cy - gr, cx + gr, cy + gr,
                    fill=gc, outline="")
            except Exception:
                pass
        # Ring
        try:
            self._logo_canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=config.GOLD, width=4)
        except Exception:
            pass
        # Glyph "R"
        try:
            font = _theme.theme.font(
                size=int(r * 0.95), weight="bold", lang="en")
            self._logo_canvas.create_text(
                cx, cy, text="R", fill=config.GOLD, font=font)
        except Exception:
            pass

    def _start_glow(self) -> None:
        """Kick off the pulsing glow loop."""
        import time
        self._glow_t0 = time.time() * 1000.0
        self._glow_tick()

    def _glow_tick(self) -> None:
        import time
        t_ms = (time.time() * 1000.0) - self._glow_t0
        self._draw_logo(t_ms)
        self._glow_job = self.after(33, self._glow_tick)

    # ------------------------------------------------------------------
    # Dot indicator
    # ------------------------------------------------------------------
    def _refresh_dots(self, flash_red: bool = False) -> None:
        """Update the dot indicator to reflect ``self._digits``."""
        color_filled = config.DANGER if flash_red else config.GOLD
        for i, d in enumerate(self._dot_widgets):
            if i < len(self._digits):
                d.configure(fg_color=color_filled)
            else:
                d.configure(fg_color=config.SURFACE_HI)

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------
    def _on_digit(self, digit: str) -> None:
        """Append a digit; auto-submit when we reach ``max_digits``."""
        if self._unlocked:
            return
        if len(self._digits) >= self._max_digits:
            return
        self._digits.append(digit)
        self._refresh_dots()
        if len(self._digits) == self._max_digits:
            # Slight delay so the user sees the 4th dot fill before submit
            self.after(120, self._submit)

    def _on_delete(self) -> None:
        """Remove the last entered digit."""
        if self._unlocked:
            return
        if self._digits:
            self._digits.pop()
            self._refresh_dots()

    def _on_biometric(self) -> None:
        """Pretend to run biometric auth — always fails on desktop."""
        if self._unlocked:
            return
        # On desktop, biometric is rarely available.  Show a brief
        # message and fall back to PIN.
        try:
            self._subtitle_label.configure(
                text=i18n.t("biometricUnavailable", self._lang)
                if "biometricUnavailable" in _catalog_keys()
                else "بیومتریک در دسترس نیست — پین را وارد کن")
        except Exception:
            pass
        self.after(1500, lambda: self._subtitle_label.configure(
            text=i18n.t("enterPin", self._lang)))

    def _on_forgot_tap(self) -> None:
        """Forgot PIN link — fire the callback."""
        if self._on_forgot:
            try:
                self._on_forgot()
            except Exception:
                pass

    def _on_key(self, evt: Any) -> None:
        """Keyboard input — digits / BackSpace / Enter."""
        if self._unlocked:
            return
        try:
            keysym = evt.keysym
            char = evt.char
        except Exception:
            return
        if keysym in ("Return", "KP_Enter"):
            if len(self._digits) == self._max_digits:
                self._submit()
            return
        if keysym in ("BackSpace", "Delete"):
            self._on_delete()
            return
        if char and char.isdigit() and 0 <= int(char) <= 9:
            self._on_digit(char)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def _submit(self) -> None:
        """Verify the entered PIN against the stored hash."""
        pin = "".join(self._digits)
        if not pin:
            return
        ok = True
        if self._pin_hash:
            try:
                ok = _pin.verify_pin(pin, self._pin_hash)
            except Exception:
                ok = False
        if ok:
            self._fire_unlock()
        else:
            self._on_wrong_pin()

    def _on_wrong_pin(self) -> None:
        """Trigger the shake + red flash + clear."""
        self._refresh_dots(flash_red=True)
        self._shake()

    def _shake(self) -> None:
        """Animate the dot row left-right 4 times over 400ms."""
        if self._shake_job is not None:
            try:
                self.after_cancel(self._shake_job)
            except Exception:
                pass
        self._shake_step = 0
        self._shake_total = max(2, 400 // 16)
        self._shake_base_x = self._dots_row.winfo_x()
        self._shake_tick()

    def _shake_tick(self) -> None:
        self._shake_step += 1
        t = self._shake_step / max(1, self._shake_total)
        # Damped sine: 4 oscillations, decaying amplitude
        amp = 12.0 * (1.0 - t)
        offset = int(amp * math.sin(t * 4.0 * math.pi * 2.0))
        try:
            self._dots_row.grid_configure(padx=(offset, -offset)
                                            if offset >= 0
                                            else (-offset, offset))
        except Exception:
            pass
        if self._shake_step < self._shake_total:
            self._shake_job = self.after(16, self._shake_tick)
        else:
            self._shake_job = None
            # Reset position + clear digits
            try:
                self._dots_row.grid_configure(padx=(0, 0))
            except Exception:
                pass
            self._digits.clear()
            self._refresh_dots()

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------
    def _fire_unlock(self) -> None:
        """Invoke the on_unlock callback exactly once."""
        if self._unlocked:
            return
        self._unlocked = True
        # Brief green flash before notifying
        try:
            for d in self._dot_widgets:
                d.configure(fg_color=config.SUCCESS)
        except Exception:
            pass
        if self._on_unlock:
            try:
                self.after(200, self._on_unlock)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render labels (called on language change)."""
        try:
            self._name_label.configure(text=i18n.t("appName", self._lang))
            self._subtitle_label.configure(
                text=i18n.t("enterPin", self._lang))
        except Exception:
            pass

    def reset(self) -> None:
        """Clear entered digits and reset to the initial state."""
        self._digits.clear()
        self._unlocked = False
        self._refresh_dots()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        if self._glow_job is not None:
            try:
                self.after_cancel(self._glow_job)
            except Exception:
                pass
            self._glow_job = None
        if self._shake_job is not None:
            try:
                self.after_cancel(self._shake_job)
            except Exception:
                pass
            self._shake_job = None
        try:
            self.unbind_all("<Key>")
        except Exception:
            pass
        super().destroy()


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _catalog_keys() -> List[str]:
    """Return the list of i18n keys for the current language (cached).

    Used by the view to safely probe for optional keys without crashing
    on catalogs that don't include them.
    """
    global _CACHED_CATALOG_KEYS
    if _CACHED_CATALOG_KEYS is None:
        try:
            _CACHED_CATALOG_KEYS = list(i18n.LOCALES.get("fa", {}).keys())
        except Exception:
            _CACHED_CATALOG_KEYS = []
    return _CACHED_CATALOG_KEYS


_CACHED_CATALOG_KEYS: Optional[List[str]] = None


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("LockView module: PIN pad with shake-on-wrong + biometric option.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
