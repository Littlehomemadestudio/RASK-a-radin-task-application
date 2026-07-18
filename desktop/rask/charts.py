"""charts.py — Canvas-drawn charts (mirror of web/js/charts.js).

Renders on a tkinter.Canvas:
    ProgressRing.draw(canvas, cx, cy, size, progress, color, track, label, label_color)
    BarChart.draw(canvas, x, y, w, h, data, opts)
    DonutChart.draw(canvas, cx, cy, r, data, line_width)
    Heatmap.draw(canvas, x, y, w, h, year, data, cell_size)
"""
from __future__ import annotations
import colorsys
import datetime as _dt
import math
from typing import Dict, List, Optional, Tuple
from . import config


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    h = (hex_str or config.GOLD).lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> str:
    r, g, b = hex_to_rgb(hex_str)
    # tkinter uses #RRGGBB; alpha is ignored by tkinter Canvas, but we expose it for API parity.
    return f"#{r:02x}{g:02x}{b:02x}"


# === ProgressRing (mirror of charts.js ProgressRing.draw) ===
def progress_ring(canvas, cx: float, cy: float, size: float, progress: float,
                  color: str = config.GOLD, track_color: str = config.SURFACE_HI,
                  label: str = "", label_color: str = config.TEXT) -> None:
    progress = max(0.0, min(1.0, progress))
    r = size / 2 - 8
    lw = 8
    # Track (full circle)
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=track_color, width=lw)
    # Progress arc (start at top, clockwise)
    if progress > 0:
        # Tkinter arc goes counterclockwise from start (degrees, east=0).
        # charts.js starts at -90° (top) and goes clockwise.
        # Tkinter arc: start=90 (top) and extent=-360*progress (clockwise = negative extent).
        extent = -360 * progress
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                          start=90, extent=extent, style="arc",
                          outline=color, width=lw)
    # Label
    if label:
        canvas.create_text(cx, cy, text=label, fill=label_color,
                           font=("Vazirmatn", max(10, int(size * 0.16)), "bold"))


# === BarChart (mirror of charts.js BarChart.draw) ===
def bar_chart(canvas, x: float, y: float, w: float, h: float,
              data: List[Dict[str, object]], opts: Optional[dict] = None) -> None:
    opts = opts or {}
    if not data:
        return
    values = [float(d.get("value", 0) or 0) for d in data]
    max_val = float(opts.get("maxValue") or max([1.0] + values))
    gap = 6
    bar_w = max(2.0, (w - gap * (len(data) + 1)) / len(data))
    base_y = y + h - 18
    # Baseline
    canvas.create_line(x, base_y, x + w, base_y, fill=config.SURFACE_HI, width=1)
    for i, d in enumerate(data):
        v = float(d.get("value", 0) or 0)
        bh = (v / max_val) * (h - 30) if max_val > 0 else 0
        bx = x + gap + i * (bar_w + gap)
        by = base_y - bh
        color = d.get("color") or config.GOLD
        # Rounded top (approximate with a rectangle — tkinter has no rounded rect natively)
        canvas.create_rectangle(bx, by, bx + bar_w, base_y, fill=color, outline="")
        # Label
        lbl = d.get("label")
        if lbl:
            canvas.create_text(bx + bar_w / 2, base_y + 6, text=str(lbl),
                               fill=config.TEXT_DIM, font=("Vazirmatn", 8))


# === DonutChart (mirror of charts.js DonutChart.draw) ===
def donut_chart(canvas, cx: float, cy: float, r: float,
                data: List[Dict[str, object]], line_width: int = 18) -> None:
    total = sum(float(d.get("value", 0) or 0) for d in data) or 1.0
    # Track
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=config.SURFACE_HI, width=line_width)
    angle = 90.0  # start at top
    for d in data:
        v = float(d.get("value", 0) or 0)
        if not v:
            continue
        seg = (v / total) * 360.0
        color = d.get("color") or config.GOLD
        # Clockwise = negative extent in tkinter
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                          start=angle, extent=-seg, style="arc",
                          outline=color, width=line_width)
        angle -= seg


# === Heatmap (mirror of charts.js Heatmap.draw) ===
def heatmap(canvas, x: float, y: float, w: float, h: float, year: int,
            data: Dict[str, int], cell_size: int = 12) -> None:
    gap = 3
    start = _dt.date(year, 1, 1)
    # Sunday of first week (mirror of charts.js: (getDay()+1)%7)
    py_weekday_to_js = lambda d: (d.weekday() + 1) % 7  # Mon=1, Sun=0, Sat=6
    offset = (py_weekday_to_js(start) + 1) % 7
    cursor = start - _dt.timedelta(days=offset)
    end = _dt.date(year, 12, 31)
    col = 0
    max_val = max([1] + list(data.values()))
    while cursor <= end:
        for row in range(7):
            if cursor.year == year:
                iso = cursor.isoformat()
                sec = data.get(iso, 0)
                tt = sec / max_val if max_val > 0 else 0
                color = _intensity_color(tt)
                cx0 = x + col * (cell_size + gap)
                cy0 = y + row * (cell_size + gap)
                canvas.create_rectangle(cx0, cy0, cx0 + cell_size, cy0 + cell_size,
                                        fill=color, outline="")
            cursor += _dt.timedelta(days=1)
        col += 1


def _intensity_color(t: float) -> str:
    steps = config.HEATMAP_STEPS
    idx = min(len(steps) - 1, int(t * len(steps)))
    r, g, b = steps[idx]
    return f"#{r:02x}{g:02x}{b:02x}"
