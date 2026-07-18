"""
rask.ui.widgets.sliders
=======================

Gold-themed slider & progress widgets:

  * ``GoldSlider``     — single-handle slider with optional value label
  * ``RangeSlider``    — dual-handle (min/max) slider
  * ``ProgressBar``    — horizontal progress bar, gold
  * ``StepProgress``   — multi-step indicator (1 ─ 2 ─ 3 ─ 4)
  * ``RatingStars``    — 5-star rating input
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

import customtkinter as ctk

from ... import config
from ...core import helpers
from . import theme as _theme
from . import icons as _icons

__all__ = ["GoldSlider", "RangeSlider", "ProgressBar",
           "StepProgress", "RatingStars"]


# =============================================================================
# === GoldSlider                                                            ===
# =============================================================================

class GoldSlider(ctk.CTkFrame):
    """Slider with optional value label below the handle."""

    def __init__(
        self,
        master: Any = None,
        min_value: float = 0,
        max_value: float = 100,
        value: float = 50,
        step: float = 1,
        on_change: Optional[Callable[[float], Any]] = None,
        show_label: bool = True,
        label_format: str = "{:.0f}",
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 40,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._min = min_value
        self._max = max_value
        self._step = step
        self._on_change = on_change
        self._lang = lang
        self._label_format = label_format
        self._show_label = show_label
        self._slider = ctk.CTkSlider(
            self,
            from_=min_value,
            to=max_value,
            number_of_steps=int((max_value - min_value) / step) if step else 0,
            width=width or 200,
            height=20,
            fg_color=config.SURFACE_HI,
            progress_color=config.GOLD,
            button_color=config.GOLD_BRIGHT,
            button_hover_color=config.GOLD_GLOW,
            button_length=22,
            corner_radius=config.RADIUS_PILL,
            command=self._on_slider_change,
        )
        self._slider.set(value)
        self._slider.pack(fill="x", expand=True, padx=4, pady=4)
        if show_label:
            self._label = ctk.CTkLabel(
                self,
                text=self._format(value),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=lang),
                text_color=config.GOLD,
            )
            self._label.pack(anchor="e", padx=8)

    def _format(self, v: float) -> str:
        try:
            s = self._label_format.format(float(v))
        except Exception:
            s = str(v)
        if self._lang == "fa":
            from ... import i18n
            s = i18n.to_fa_digits(s)
        return s

    def _on_slider_change(self, v: float) -> None:
        if self._show_label:
            try:
                self._label.configure(text=self._format(v))
            except Exception:
                pass
        if self._on_change:
            try:
                self._on_change(float(v))
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> float:
        try:
            return float(self._slider.get())
        except Exception:
            return 0.0

    @value.setter
    def value(self, v: float) -> None:
        try:
            self._slider.set(float(v))
            if self._show_label:
                self._label.configure(text=self._format(v))
        except Exception:
            pass


# =============================================================================
# === RangeSlider                                                           ===
# =============================================================================

class RangeSlider(ctk.CTkFrame):
    """Dual-handle range slider (min/max)."""

    def __init__(
        self,
        master: Any = None,
        min_value: float = 0,
        max_value: float = 100,
        low: float = 25,
        high: float = 75,
        step: float = 1,
        on_change: Optional[Callable[[float, float], Any]] = None,
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 40,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._min = min_value
        self._max = max_value
        self._step = step
        self._on_change = on_change
        self._lang = lang
        # Two sliders stacked on top of each other; the upper one is
        # transparent so both handles are visible.  This is a pragmatic
        # workaround for CTk not having a native RangeSlider.
        self._low = ctk.DoubleVar(value=low)
        self._high = ctk.DoubleVar(value=high)
        # Container for the two sliders
        self._track = ctk.CTkFrame(self, fg_color="transparent", height=24)
        self._track.pack(fill="x", padx=4, pady=8)
        # Track background
        self._bg = ctk.CTkFrame(self._track, fg_color=config.SURFACE_HI,
                                height=6, corner_radius=config.RADIUS_PILL)
        self._bg.place(relx=0, rely=0.5, relwidth=1, anchor="w")
        # Selected range bar (gold)
        self._sel = ctk.CTkFrame(self._track, fg_color=config.GOLD,
                                 height=6, corner_radius=config.RADIUS_PILL)
        # Low handle
        self._low_btn = ctk.CTkButton(
            self._track, text="",
            width=22, height=22,
            fg_color=config.GOLD_BRIGHT, hover_color=config.GOLD_GLOW,
            corner_radius=config.RADIUS_PILL, cursor="hand2",
        )
        # High handle
        self._high_btn = ctk.CTkButton(
            self._track, text="",
            width=22, height=22,
            fg_color=config.GOLD_BRIGHT, hover_color=config.GOLD_GLOW,
            corner_radius=config.RADIUS_PILL, cursor="hand2",
        )
        self._low_btn.place(x=0, rely=0.5, anchor="center")
        self._high_btn.place(x=0, rely=0.5, anchor="center")
        self._sel.place(x=0, rely=0.5, anchor="w")
        # Drag bindings
        self._dragging: Optional[str] = None
        try:
            self._low_btn.bind("<ButtonPress-1>",
                                lambda e: self._start_drag("low", e))
            self._high_btn.bind("<ButtonPress-1>",
                                  lambda e: self._start_drag("high", e))
            self.bind("<B1-Motion>", self._on_drag)
            self.bind("<ButtonRelease-1>", self._end_drag)
            self.bind("<Configure>", lambda _e: self._update_positions())
        except Exception:
            pass
        self._update_positions()

    def _start_drag(self, which: str, _evt: Any) -> None:
        self._dragging = which

    def _end_drag(self, _evt: Any) -> None:
        self._dragging = None

    def _on_drag(self, evt: Any) -> None:
        if not self._dragging:
            return
        try:
            w = self._track.winfo_width()
            if w <= 0:
                return
            x = evt.x - 11  # half handle width
            t = helpers.clamp(x / max(1, w - 22), 0.0, 1.0)
            val = self._min + t * (self._max - self._min)
            # Snap to step
            if self._step:
                val = round(val / self._step) * self._step
            if self._dragging == "low":
                if val <= self._high.get() - self._step:
                    self._low.set(val)
            else:
                if val >= self._low.get() + self._step:
                    self._high.set(val)
            self._update_positions()
            if self._on_change:
                self._on_change(self._low.get(), self._high.get())
        except Exception:
            pass

    def _update_positions(self) -> None:
        try:
            w = self._track.winfo_width()
            if w <= 0:
                self.after(50, self._update_positions)
                return
            span = max(1, w - 22)
            lo_t = (self._low.get() - self._min) / max(1, self._max - self._min)
            hi_t = (self._high.get() - self._min) / max(1, self._max - self._min)
            lo_x = 11 + lo_t * span
            hi_x = 11 + hi_t * span
            self._low_btn.place(x=lo_x, rely=0.5, anchor="center")
            self._high_btn.place(x=hi_x, rely=0.5, anchor="center")
            self._sel.place(x=lo_x, rely=0.5, anchor="w")
            self._sel.configure(width=max(1, int(hi_x - lo_x)))
        except Exception:
            pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> Tuple[float, float]:
        return (float(self._low.get()), float(self._high.get()))

    @value.setter
    def value(self, v: Tuple[float, float]) -> None:
        try:
            lo, hi = v
            self._low.set(lo)
            self._high.set(hi)
            self._update_positions()
        except Exception:
            pass


# =============================================================================
# === ProgressBar                                                           ===
# =============================================================================

class ProgressBar(ctk.CTkProgressBar):
    """Gold horizontal progress bar with optional animated transition."""

    def __init__(
        self,
        master: Any = None,
        value: float = 0.0,
        animated: bool = False,
        height: int = 8,
        width: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE_HI)
        kwargs.setdefault("progress_color", config.GOLD)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", height)
        if width is not None:
            kwargs.setdefault("width", width)
        super().__init__(master, **kwargs)
        self._animated = animated
        self._target = float(value)
        self._anim_job = None
        if not animated:
            self.set(value)

    def set_value(self, v: float, animate: Optional[bool] = None) -> None:
        """Set the progress value (0..1).  Animates if enabled."""
        if animate is None:
            animate = self._animated
        v = helpers.clamp(v, 0.0, 1.0)
        if not animate:
            self.set(v)
            self._target = v
            return
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._target = v
        self._anim_start = float(self.get())
        self._anim_step = 0
        self._anim_total = max(2, config.ANIM_NORMAL // 16)
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total)
        v = self._anim_start + (self._target - self._anim_start) * t
        self.set(v)
        if self._anim_step < self._anim_total:
            self._anim_job = self.after(16, self._tick_anim)
        else:
            self._anim_job = None

    @property
    def value(self) -> float:
        try:
            return float(self.get())
        except Exception:
            return 0.0


# =============================================================================
# === StepProgress                                                          ===
# =============================================================================

class StepProgress(ctk.CTkFrame):
    """Multi-step indicator (1 ─ 2 ─ 3 ─ 4)."""

    def __init__(
        self,
        master: Any = None,
        steps: Sequence[str] = ("۱", "۲", "۳", "۴"),
        current: int = 0,
        lang: str = "fa",
        height: int = 60,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._steps: List[str] = list(steps)
        self._current = current
        self._lang = lang
        self._circles: List[ctk.CTkFrame] = []
        self._labels: List[ctk.CTkLabel] = []
        self._build()

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._circles = []
        self._labels = []
        n = len(self._steps)
        for i, label in enumerate(self._steps):
            color = config.GOLD if i <= self._current else config.SURFACE_HI
            text_color = (config.MATTE_BLACK if i < self._current
                          else config.TEXT if i == self._current
                          else config.TEXT_DIM)
            circle = ctk.CTkFrame(
                self,
                width=32, height=32,
                fg_color=color,
                corner_radius=16,
                border_width=2 if i == self._current else 0,
                border_color=config.GOLD_BRIGHT,
            )
            txt = "✓" if i < self._current else label
            lbl = ctk.CTkLabel(
                circle, text=txt,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold", lang=self._lang),
                text_color=text_color,
            )
            lbl.pack(expand=True, fill="both")
            circle.grid(row=0, column=i * 2, padx=4)
            self.grid_columnconfigure(i * 2, weight=0)
            self._circles.append(circle)
            self._labels.append(lbl)
            if i < n - 1:
                line = ctk.CTkFrame(
                    self, height=2,
                    fg_color=config.GOLD if i < self._current else config.SURFACE_HI,
                )
                line.grid(row=0, column=i * 2 + 1, sticky="ew", padx=2)
                self.grid_columnconfigure(i * 2 + 1, weight=1)

    def set_current(self, idx: int) -> None:
        idx = helpers.clamp(idx, 0, len(self._steps) - 1)
        self._current = idx
        self._build()

    @property
    def value(self) -> int:
        return self._current


# =============================================================================
# === RatingStars                                                           ===
# =============================================================================

class RatingStars(ctk.CTkFrame):
    """5-star rating input."""

    def __init__(
        self,
        master: Any = None,
        value: int = 0,
        max_stars: int = 5,
        on_change: Optional[Callable[[int], Any]] = None,
        lang: str = "fa",
        star_size: int = 28,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._value = value
        self._max = max_stars
        self._on_change = on_change
        self._lang = lang
        self._star_size = star_size
        self._stars: List[ctk.CTkButton] = []
        self._build()

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._stars = []
        for i in range(self._max):
            filled = i < self._value
            color = config.GOLD if filled else config.TEXT_FAINT
            btn = ctk.CTkButton(
                self, text="★",
                width=self._star_size, height=self._star_size,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                text_color=color,
                font=_theme.theme.font(size=self._star_size, weight="bold",
                                        lang="en"),
                corner_radius=config.RADIUS_SM, cursor="hand2",
                command=lambda n=i + 1: self._set_value(n),
            )
            btn.grid(row=0, column=i, padx=2)
            try:
                btn.bind("<Enter>", lambda _e, n=i: self._preview(n + 1),
                          add="+")
                btn.bind("<Leave>", lambda _e: self._preview(self._value),
                          add="+")
            except Exception:
                pass
            self._stars.append(btn)

    def _preview(self, n: int) -> None:
        for i, btn in enumerate(self._stars):
            color = config.GOLD if i < n else config.TEXT_FAINT
            btn.configure(text_color=color)

    def _set_value(self, n: int) -> None:
        if n == self._value:
            n = 0  # click again to clear
        self._value = n
        self._preview(n)
        if self._on_change:
            try:
                self._on_change(n)
            except Exception:
                pass

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, v: int) -> None:
        self._value = helpers.clamp(int(v), 0, self._max)
        self._preview(self._value)


def _self_test() -> int:
    classes = [GoldSlider, RangeSlider, ProgressBar, StepProgress, RatingStars]
    print(f"Sliders module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
