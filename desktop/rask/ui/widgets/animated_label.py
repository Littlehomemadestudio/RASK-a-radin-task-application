"""
rask.ui.widgets.animated_label
==============================

Animated labels:

  * ``AnimatedLabel``    — base class with fade-in / count-up helpers
  * ``TypewriterLabel``  — types out text char by char
  * ``CountUpLabel``     — animates from current number to target
"""
from __future__ import annotations

import math
from typing import Any, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme

__all__ = ["AnimatedLabel", "TypewriterLabel", "CountUpLabel"]


# =============================================================================
# === AnimatedLabel                                                         ===
# =============================================================================

class AnimatedLabel(ctk.CTkLabel):
    """Base class for animated labels.

    Provides ``fade_in``, ``count_up``, and ``animate_text`` helpers
    built on top of ``after()`` loops and the easing functions from
    :mod:`rask.core.helpers`.
    """

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        lang: str = "fa",
        size: int = config.FONT_SIZE_DEFAULT,
        weight: str = "normal",
        color: str = config.TEXT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("text", text)
        kwargs.setdefault("font", _theme.theme.font(size=size,
                                                     weight=weight, lang=lang))
        kwargs.setdefault("text_color", color)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._base_color = color
        self._jobs: list = []

    # ------------------------------------------------------------------
    def fade_in(self, duration: int = 200) -> None:
        """Fade the label's text colour from transparent to base colour.

        Approximates alpha by interpolating between the background colour
        and the base text colour.
        """
        try:
            bg = config.MATTE_BLACK
            steps = max(2, duration // 16)
            self._fade_step = 0
            self._fade_total = steps
            self._fade_start = bg
            self._fade_end = self._base_color
            self._tick_fade()
        except Exception:
            pass

    def _tick_fade(self) -> None:
        self._fade_step += 1
        t = helpers.ease_out_cubic(self._fade_step / self._fade_total)
        col = helpers.mix_colors(self._fade_start, self._fade_end, t)
        try:
            self.configure(text_color=col)
        except Exception:
            return
        if self._fade_step < self._fade_total:
            job = self.after(16, self._tick_fade)
            self._jobs.append(job)
        else:
            try:
                self.configure(text_color=self._fade_end)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def count_up(
        self,
        target_value: float,
        duration: int = 800,
        lang: Optional[str] = None,
        decimals: int = 0,
    ) -> None:
        """Animate the label from its current number to ``target_value``."""
        lang = lang or self._lang
        try:
            cur_text = self.cget("text") or "0"
            from ...core import helpers as _h
            cur = float(_h.safe_int(i18n.to_en_digits(cur_text), 0))
        except Exception:
            cur = 0.0
        self._cu_step = 0
        self._cu_total = max(2, duration // 16)
        self._cu_start = cur
        self._cu_target = float(target_value)
        self._cu_decimals = decimals
        self._cu_lang = lang
        self._tick_count_up()

    def _tick_count_up(self) -> None:
        self._cu_step += 1
        t = helpers.ease_out_cubic(self._cu_step / self._cu_total)
        v = helpers.lerp(self._cu_start, self._cu_target, t)
        if self._cu_decimals == 0:
            s = str(int(round(v)))
        else:
            s = f"{v:.{self._cu_decimals}f}"
        if self._cu_lang == "fa":
            s = i18n.to_fa_digits(s)
        try:
            self.configure(text=s)
        except Exception:
            return
        if self._cu_step < self._cu_total:
            job = self.after(16, self._tick_count_up)
            self._jobs.append(job)

    # ------------------------------------------------------------------
    def animate_text(self, target: str, duration: int = 400) -> None:
        """Cross-fade text by stepping opacity.  Simple version: just sets text after delay."""
        # Simple implementation: instant set with fade-in
        try:
            self.configure(text=target)
            self.fade_in(duration)
        except Exception:
            pass

    def cancel_animations(self) -> None:
        for job in self._jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._jobs = []


# =============================================================================
# === TypewriterLabel                                                       ===
# =============================================================================

class TypewriterLabel(AnimatedLabel):
    """Types out text char-by-char with a configurable delay."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        char_delay_ms: int = 35,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        # Start empty so we can type out
        super().__init__(master, text="", lang=lang, **kwargs)
        self._target_text = text
        self._char_delay = char_delay_ms
        self._type_idx = 0
        self._type_job = None
        # Auto-start typing
        if text:
            self.after(100, self._type_next_char)

    def type_text(self, text: str, char_delay_ms: Optional[int] = None) -> None:
        """Begin typing out ``text``."""
        if char_delay_ms is not None:
            self._char_delay = char_delay_ms
        self._target_text = text
        self._type_idx = 0
        try:
            self.configure(text="")
        except Exception:
            pass
        self._type_next_char()

    def _type_next_char(self) -> None:
        if self._type_idx >= len(self._target_text):
            self._type_job = None
            return
        self._type_idx += 1
        try:
            self.configure(text=self._target_text[:self._type_idx])
        except Exception:
            return
        self._type_job = self.after(self._char_delay, self._type_next_char)
        self._jobs.append(self._type_job)

    def skip(self) -> None:
        """Jump to the full text immediately."""
        if self._type_job:
            try:
                self.after_cancel(self._type_job)
            except Exception:
                pass
            self._type_job = None
        try:
            self.configure(text=self._target_text)
        except Exception:
            pass
        self._type_idx = len(self._target_text)


# =============================================================================
# === CountUpLabel                                                          ===
# =============================================================================

class CountUpLabel(AnimatedLabel):
    """Convenience class pre-tuned for count-up number displays.

    Use :meth:`set_value` to trigger the count-up animation.
    """

    def __init__(
        self,
        master: Any = None,
        value: float = 0,
        duration_ms: int = 800,
        lang: str = "fa",
        size: int = config.FONT_SIZE_HEADING_LG,
        color: str = config.GOLD,
        decimals: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, text="0", lang=lang, size=size,
                          weight="bold", color=color, **kwargs)
        self._duration = duration_ms
        self._decimals = decimals
        self._value = float(value)
        try:
            s = str(int(value)) if decimals == 0 else f"{value:.{decimals}f}"
            if lang == "fa":
                s = i18n.to_fa_digits(s)
            self.configure(text=s)
        except Exception:
            pass

    def set_value(self, value: float, animate: bool = True) -> None:
        """Update the displayed value, animating if requested."""
        if not animate:
            try:
                s = (str(int(value)) if self._decimals == 0
                     else f"{value:.{self._decimals}f}")
                if self._lang == "fa":
                    s = i18n.to_fa_digits(s)
                self.configure(text=s)
            except Exception:
                pass
            self._value = float(value)
            return
        self.count_up(value, duration=self._duration,
                       decimals=self._decimals)
        self._value = float(value)

    @property
    def value(self) -> float:
        return self._value


def _self_test() -> int:
    classes = [AnimatedLabel, TypewriterLabel, CountUpLabel]
    print(f"Animated label module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
