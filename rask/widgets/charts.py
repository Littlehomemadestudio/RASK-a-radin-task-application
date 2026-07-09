"""
charts.py — Custom Kivy widgets for charts:
    - ProgressRing:  circular goal progress indicator
    - BarChart:      vertical bar chart (e.g., last 7 days)
    - DonutChart:    multi-segment donut (e.g., category share)
    - HeatmapView:   GitHub-style year heatmap of activity intensity

All drawn with Kivy Canvas — no external chart library.
Kept lightweight: every widget re-draws only when its data changes.
"""
from __future__ import annotations

from typing import Optional

from kivy.graphics import Color, Line, Rectangle, Ellipse, PushMatrix, PopMatrix, Rotate
from kivy.graphics.instructions import InstructionGroup
from kivy.properties import NumericProperty, StringProperty, ListProperty, BoundedNumericProperty, ObjectProperty, DictProperty
from kivy.uix.widget import Widget
from kivy.core.text import Label as CoreLabel
from kivy.utils import get_color_from_hex

from rask import config as cfg


def _hex_to_rgba(h: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    try:
        c = get_color_from_hex(h)
        return (c[0], c[1], c[2], alpha)
    except Exception:
        return (1, 1, 1, alpha)


# === ProgressRing ===

class ProgressRing(Widget):
    """Circular progress ring drawn with gold gradient + dark track."""
    progress = BoundedNumericProperty(0.0, min=0.0, max=1.0)
    line_width = NumericProperty(8)
    color_hex = StringProperty("#D4AF37")
    track_color_hex = StringProperty("#2C2C30")
    label_text = StringProperty("")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(
            pos=self._redraw, size=self._redraw, progress=self._redraw,
            color_hex=self._redraw, label_text=self._redraw,
            line_width=self._redraw,
        )
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            cx, cy = self.center
            r = min(self.width, self.height) / 2 - self.line_width
            if r <= 0:
                return
            # Track
            Color(*_hex_to_rgba(self.track_color_hex))
            Line(circle=(cx, cy, r, 0, 360), width=self.line_width)
            # Progress arc
            Color(*_hex_to_rgba(self.color_hex))
            end_angle = 360 * float(self.progress)
            if end_angle > 0:
                # Kivy's Line.circle starts at 0deg = right, going CCW.
                # We want clockwise from top, so start at 90 and go down.
                Line(circle=(cx, cy, r, 90, 90 - end_angle), width=self.line_width)

        # Center label
        if self.label_text:
            lbl = CoreLabel(text=self.label_text,
                            font_size=cfg.FONT_SIZES["h4"],
                            color=cfg.TEXT)
            lbl.refresh()
            tex = lbl.texture
            if tex:
                self.canvas.add(Color(*cfg.TEXT))
                Rectangle(texture=tex, pos=(self.center_x - tex.width / 2,
                                            self.center_y - tex.height / 2),
                          size=tex.size)


# === BarChart ===

class BarChart(Widget):
    """Vertical bars. `data` is list of (label, value, color_hex)."""
    data = ListProperty([])            # [(label, value, color_hex), ...]
    max_value = NumericProperty(0, allownone=True)
    bar_color = StringProperty("#D4AF37")
    text_color_hex = StringProperty("#E8E8E8")
    axis_color_hex = StringProperty("#2C2C30")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, data=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        if not self.data:
            return
        max_val = self.max_value or max((v for _, v, _ in self.data), default=1) or 1
        with self.canvas:
            Color(*_hex_to_rgba(self.axis_color_hex))
            # Baseline
            Line(points=[self.x, self.y + 8, self.right, self.y + 8], width=1)

            n = len(self.data)
            gap = 6
            total_gap = gap * (n + 1)
            bar_w = max(2, (self.width - total_gap) / n)
            for i, (label, val, color_hex) in enumerate(self.data):
                h = (val / max_val) * (self.height - 30)
                x = self.x + gap + i * (bar_w + gap)
                y = self.y + 8
                Color(*_hex_to_rgba(color_hex or self.bar_color))
                Rectangle(pos=(x, y), size=(bar_w, h))
                # Label
                if label:
                    lbl = CoreLabel(text=str(label),
                                    font_size=cfg.FONT_SIZES["tiny"],
                                    color=cfg.TEXT_DIM)
                    lbl.refresh()
                    tex = lbl.texture
                    if tex:
                        self.canvas.add(Color(*cfg.TEXT_DIM))
                        Rectangle(texture=tex,
                                  pos=(x + (bar_w - tex.width) / 2, y - 14),
                                  size=tex.size)


# === DonutChart ===

class DonutChart(Widget):
    """Multi-segment donut. `data` is list of (label, value, color_hex)."""
    data = ListProperty([])  # [(label, value, color_hex), ...]
    line_width = NumericProperty(18)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, data=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        if not self.data:
            return
        total = sum(v for _, v, _ in self.data) or 1
        cx, cy = self.center
        r = min(self.width, self.height) / 2 - self.line_width
        if r <= 0:
            return
        with self.canvas:
            # Track
            Color(*_hex_to_rgba("#2C2C30"))
            Line(circle=(cx, cy, r, 0, 360), width=self.line_width)
            # Segments (start at 90deg = top, go CW)
            angle = 90.0
            for label, val, color_hex in self.data:
                seg = 360 * (val / total)
                Color(*_hex_to_rgba(color_hex or "#D4AF37"))
                if seg > 0.1:
                    Line(circle=(cx, cy, r, angle, angle - seg),
                         width=self.line_width)
                angle -= seg


# === HeatmapView (year) ===

class HeatmapView(Widget):
    """GitHub-style year heatmap. `data` is dict {iso_date: seconds}."""
    data = DictProperty({})
    year = NumericProperty(0)
    cell = NumericProperty(12)
    gap = NumericProperty(3)

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.year == 0:
            from datetime import date
            self.year = date.today().year
        self.bind(pos=self._redraw, size=self._redraw, data=self._redraw,
                  year=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return
        from datetime import date, timedelta
        year_start = date(self.year, 1, 1)
        year_end = date(self.year, 12, 31)
        # Lay out weeks as columns
        cell = self.cell
        gap = self.gap
        max_sec = max(self.data.values(), default=1) or 1

        # Find first Monday of year (or Sunday if Sunday-start)
        first = year_start
        offset = (first.weekday() + 1) % 7  # Sunday-start
        start = first - timedelta(days=offset)

        cur = start
        col = 0
        with self.canvas:
            while cur <= year_end:
                for row in range(7):
                    if cur.year != self.year:
                        cur += timedelta(days=1)
                        continue
                    sec = self.data.get(cur.isoformat(), 0)
                    intensity = (sec / max_sec) if max_sec > 0 else 0
                    color = self._intensity_color(intensity)
                    Color(*color)
                    x = self.x + col * (cell + gap)
                    y = self.top - (row + 1) * (cell + gap)
                    Rectangle(pos=(x, y), size=(cell, cell))
                cur += timedelta(days=1)
                col += 1

    def _intensity_color(self, t: float) -> tuple:
        # 5-step scale: dark -> gold
        steps = [
            (0.04, 0.04, 0.06, 1.0),    # empty
            (0.30, 0.25, 0.10, 1.0),
            (0.50, 0.40, 0.13, 1.0),
            (0.70, 0.55, 0.18, 1.0),
            (0.83, 0.69, 0.22, 1.0),    # full gold
        ]
        idx = min(len(steps) - 1, int(t * len(steps)))
        return steps[idx]
