"""
rask.ui.widgets.progress_ring
=============================

Animated circular progress ring drawn on a Tk Canvas.

Mirrors the web ``RaskCharts.ProgressRing`` exactly:

  * Round-capped arc starting at 12 o'clock, going clockwise
  * Track ring in :data:`config.SURFACE_HI`
  * Progress arc in :data:`config.GOLD`
  * Optional center label (percentage or custom text)
  * Smooth animation from old to new value (ease_out_cubic)
  * Optional multi-segment variant for showing multiple categories

Public classes
--------------
``ProgressRing``      — single-segment ring
``MultiProgressRing`` — multi-segment ring (stacked arcs)
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

try:
    import customtkinter as ctk
    _CTK_OK = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme

__all__ = ["ProgressRing", "MultiProgressRing"]


def _to_fa(s: str, lang: str) -> str:
    if lang == "fa":
        return i18n.to_fa_digits(s)
    return s


# =============================================================================
# === ProgressRing                                                          ===
# =============================================================================

class ProgressRing(ctk.CTkCanvas):  # type: ignore[misc]
    """Animated circular progress indicator.

    Parameters
    ----------
    progress
        Initial progress value in ``[0.0, 1.0]``.
    size
        Diameter of the ring in pixels.
    line_width
        Thickness of the arc stroke.
    color
        Hex colour of the progress arc (defaults to gold).
    track_color
        Hex colour of the background track.
    label
        Optional custom center label.  If ``None`` and
        ``show_percentage`` is True, the percentage is shown.
    label_color
        Color of the label text.
    show_percentage
        Show the percentage as the center label.
    animated
        Animate changes via :meth:`set_progress`.
    animation_duration_ms
        Duration of the animation in milliseconds.
    lang
        ``"fa"`` for Persian digits, ``"en"`` for Western.
    """

    def __init__(
        self,
        master: Any = None,
        progress: float = 0.0,
        size: int = 96,
        line_width: int = 8,
        color: str = config.GOLD,
        track_color: str = config.SURFACE_HI,
        label: Optional[str] = None,
        label_color: str = config.TEXT,
        show_percentage: bool = False,
        animated: bool = True,
        animation_duration_ms: int = config.ANIM_NORMAL,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("bg", config.MATTE_BLACK)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(master, **kwargs)
        self._progress = float(helpers.clamp(progress, 0.0, 1.0))
        self._target = self._progress
        self._size = size
        self._line_width = line_width
        self._color = color
        self._track_color = track_color
        self._label = label
        self._label_color = label_color
        self._show_percentage = show_percentage
        self._animated = animated
        self._duration = animation_duration_ms
        self._lang = lang
        self._anim_job = None
        self._anim_step = 0
        self._anim_total = 0
        self._anim_start = 0.0
        # Bind resize to redraw
        try:
            self.bind("<Configure>", lambda _e: self.redraw(), add="+")
        except Exception:
            pass
        self.redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def redraw(self) -> None:
        """Repaint the ring at its current progress value."""
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        size = min(w, h)
        if size < 4:
            return
        cx, cy = size / 2, size / 2
        r = max(self._line_width, size / 2 - self._line_width)
        # Track
        try:
            self.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=self._track_color,
                width=self._line_width,
                style="arc",
                start=0, extent=359.9,  # full circle
            )
        except Exception:
            pass
        # Progress arc — Tk arc starts at 3 o'clock and goes counter-clockwise.
        # We want to start at 12 o'clock and go clockwise, so we use
        # start = 90° and a negative extent.
        if self._progress > 0:
            extent = -360 * self._progress
            try:
                self.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    outline=self._color,
                    width=self._line_width,
                    style="arc",
                    start=90,
                    extent=extent,
                )
            except Exception:
                pass
        # Center label
        text = self._label
        if text is None and self._show_percentage:
            text = _to_fa(f"{int(self._progress * 100)}%", self._lang)
        if text:
            try:
                font = _theme.theme.font(
                    size=int(size * 0.18), weight="bold", lang=self._lang)
                self.create_text(
                    cx, cy, text=text, fill=self._label_color,
                    font=font,
                )
            except Exception:
                try:
                    self.create_text(cx, cy, text=text, fill=self._label_color)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------
    def set_progress(self, p: float, animate: Optional[bool] = None) -> None:
        """Set the progress value (0..1), optionally animating."""
        p = float(helpers.clamp(p, 0.0, 1.0))
        if animate is None:
            animate = self._animated
        if not animate:
            self._progress = p
            self._target = p
            self.redraw()
            return
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._anim_start = self._progress
        self._target = p
        self._anim_step = 0
        self._anim_total = max(2, self._duration // 16)
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total)
        self._progress = self._anim_start + (self._target - self._anim_start) * t
        self.redraw()
        if self._anim_step < self._anim_total:
            self._anim_job = self.after(16, self._tick_anim)
        else:
            self._progress = self._target
            self.redraw()
            self._anim_job = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, v: float) -> None:
        self.set_progress(v)

    def set_label(self, text: Optional[str]) -> None:
        self._label = text
        self.redraw()

    def set_color(self, color: str) -> None:
        self._color = color
        self.redraw()


# =============================================================================
# === MultiProgressRing                                                     ===
# =============================================================================

class MultiProgressRing(ctk.CTkCanvas):  # type: ignore[misc]
    """Multi-segment ring — used for showing multiple category progresses.

    Each segment is a separate arc laid out around the same circle.
    Segments are drawn in order; the total of all ``value`` fields
    should ideally sum to 1.0 but will be normalised if not.

    Parameters
    ----------
    segments
        Iterable of dicts ``{"label", "value", "color"}``.
    size
        Diameter of the ring.
    line_width
        Stroke thickness.
    show_legend
        Whether to render a small legend below the ring.
    """

    def __init__(
        self,
        master: Any = None,
        segments: Sequence[dict] = (),
        size: int = 160,
        line_width: int = 16,
        show_legend: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size + (60 if show_legend else 0))
        kwargs.setdefault("bg", config.MATTE_BLACK)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(master, **kwargs)
        self._segments: List[dict] = list(segments)
        self._size = size
        self._line_width = line_width
        self._show_legend = show_legend
        self._lang = lang
        try:
            self.bind("<Configure>", lambda _e: self.redraw(), add="+")
        except Exception:
            pass
        self.redraw()

    def set_data(self, segments: Sequence[dict]) -> None:
        self._segments = list(segments)
        self.redraw()

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        size = min(w, self._size)
        cx, cy = size / 2, size / 2
        r = max(self._line_width, size / 2 - self._line_width)
        # Track
        try:
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             outline=config.SURFACE_HI,
                             width=self._line_width)
        except Exception:
            pass
        total = sum(s.get("value", 0) for s in self._segments) or 1
        angle = 90  # start at 12 o'clock
        for seg in self._segments:
            val = seg.get("value", 0)
            if val <= 0:
                continue
            extent = -360 * (val / total)
            color = seg.get("color", config.GOLD)
            try:
                self.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    outline=color, width=self._line_width,
                    style="arc", start=angle, extent=extent,
                )
            except Exception:
                pass
            angle += extent
        # Center label (sum of values as percentage)
        try:
            total_pct = int(min(1.0, total) * 100) if total <= 1.0 else 100
            text = _to_fa(f"{total_pct}%", self._lang)
            font = _theme.theme.font(size=int(size * 0.18), weight="bold",
                                      lang=self._lang)
            self.create_text(cx, cy, text=text, fill=config.TEXT, font=font)
        except Exception:
            pass
        # Legend below ring
        if self._show_legend and self._segments:
            leg_y = size + 8
            x = 8
            for seg in self._segments:
                color = seg.get("color", config.GOLD)
                label = seg.get("label", "")
                try:
                    self.create_oval(x, leg_y, x + 10, leg_y + 10,
                                     fill=color, outline="")
                    self.create_text(x + 14, leg_y + 5, text=label,
                                     fill=config.TEXT_DIM, anchor="w",
                                     font=_theme.theme.font(
                                         size=config.FONT_SIZE_CAPTION,
                                         weight="normal", lang=self._lang))
                    x += 14 + len(label) * 6 + 12
                    if x > w - 60:
                        leg_y += 16
                        x = 8
                except Exception:
                    pass


def _self_test() -> int:
    classes = [ProgressRing, MultiProgressRing]
    print(f"Progress ring module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
