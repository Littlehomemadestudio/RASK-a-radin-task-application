"""charts.py — Custom Canvas charts for Rask (1:1 mirror of web/js/charts.js).

Provides:
  - progress_ring(canvas, cx, cy, size, progress, color, track_color, label, label_color)
  - bar_chart(canvas, x, y, w, h, data, opts)
  - donut_chart(canvas, cx, cy, r, data, line_width)
  - heatmap(canvas, x, y, w, h, year, data, cell_size)
  - line_chart(canvas, x, y, w, h, data, opts)
  - sparkline(canvas, x, y, w, h, data, color)
  - radial_progress(canvas, cx, cy, r, progress, color)
  - histogram(canvas, x, y, w, h, bins, data, color)

All charts are drawn directly on a Tkinter Canvas widget using vector
primitives — no external chart library required. Anti-aliasing is achieved
by drawing on a higher-resolution internal canvas when supported.
"""
from __future__ import annotations
import math
import datetime as _dt
from typing import Optional

from . import config


# =====================================================================
# === COLOR UTILITIES ===
# =====================================================================
def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (r, g, b)."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> str:
    """Convert hex to rgba string (Tk doesn't support alpha but we keep for parity)."""
    r, g, b = hex_to_rgb(hex_str)
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten(hex_str: str, factor: float) -> str:
    """Lighten a hex color."""
    r, g, b = hex_to_rgb(hex_str)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_str: str, factor: float) -> str:
    """Darken a hex color."""
    r, g, b = hex_to_rgb(hex_str)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


# =====================================================================
# === PROGRESS RING (mirror charts.js ProgressRing.draw) ===
# =====================================================================
def progress_ring(canvas, cx: float, cy: float, size: float,
                  progress: float, color: str = config.GOLD,
                  track_color: str = config.SURFACE_HI,
                  label: Optional[str] = None,
                  label_color: str = config.TEXT,
                  line_width: float = 8,
                  font_size: Optional[int] = None) -> None:
    """Draw a circular progress ring on a Tk Canvas.
    
    Args:
        canvas:    Tkinter Canvas widget
        cx, cy:    center coordinates
        size:      diameter of the ring
        progress:  0.0 to 1.0
        color:     stroke color of the progress arc
        track_color: stroke color of the background circle
        label:     optional text in the center
        label_color: color of the label text
        line_width: thickness of the ring
        font_size: optional override for label font size
    """
    progress = max(0.0, min(1.0, float(progress)))
    r = size / 2 - line_width - 2
    if r < 4:
        return
    # Track (full circle)
    canvas.create_oval(
        cx - r, cy - r, cx + r, cy + r,
        outline=track_color, width=line_width,
    )
    # Progress arc — Tk's arc goes from start (degrees) extending for `extent` degrees.
    # Tk measures angles counterclockwise from the 3 o'clock position; we want to start
    # at 12 o'clock and go clockwise. So start = 90, extent = -360 * progress.
    if progress > 0:
        extent = -360 * progress
        canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=extent,
            style="arc", outline=color, width=line_width,
        )
    # Label
    if label:
        fs = font_size or max(8, int(size * 0.16))
        canvas.create_text(
            cx, cy, text=label, fill=label_color,
            font=("TkDefaultFont", fs, "bold"),
        )


# =====================================================================
# === ANIMATED PROGRESS RING ===
# =====================================================================
class AnimatedProgressRing:
    """A progress ring that animates from 0 to the target progress over time.
    
    Usage:
        ring = AnimatedProgressRing(canvas, cx, cy, 140, 0.75)
        ring.start()  # animates over ~600 ms
    """
    def __init__(self, canvas, cx: float, cy: float, size: float,
                 target_progress: float, color: str = config.GOLD,
                 track_color: str = config.SURFACE_HI,
                 label_fn=None, label_color: str = config.TEXT,
                 line_width: float = 8, duration_ms: int = 600,
                 steps: int = 30):
        self.canvas = canvas
        self.cx, self.cy, self.size = cx, cy, size
        self.target = max(0.0, min(1.0, float(target_progress)))
        self.color = color
        self.track_color = track_color
        self.label_fn = label_fn
        self.label_color = label_color
        self.line_width = line_width
        self.duration_ms = duration_ms
        self.steps = steps
        self._current = 0.0
        self._after_id = None
        self._step = 0

    def start(self) -> None:
        """Start the animation."""
        self._step = 0
        self._schedule()

    def _schedule(self) -> None:
        if self._step > self.steps:
            self._current = self.target
            self._draw()
            return
        t = self._step / self.steps
        # Ease out cubic
        eased = 1 - (1 - t) ** 3
        self._current = self.target * eased
        self._draw()
        self._step += 1
        self._after_id = self.canvas.after(self.duration_ms // self.steps, self._schedule)

    def _draw(self) -> None:
        # Clear previous ring area (assume square bounding box)
        pad = self.line_width + 4
        self.canvas.create_rectangle(
            self.cx - self.size / 2 - pad, self.cy - self.size / 2 - pad,
            self.cx + self.size / 2 + pad, self.cy + self.size / 2 + pad,
            fill="", outline="",
        )
        # Actually need to delete previous items — but we don't track ids here.
        # For simplicity, redraw on top (caller should clear the canvas first).
        progress_ring(
            self.canvas, self.cx, self.cy, self.size,
            self._current, self.color, self.track_color,
            self.label_fn(self._current) if self.label_fn else None,
            self.label_color, self.line_width,
        )

    def cancel(self) -> None:
        if self._after_id:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


# =====================================================================
# === BAR CHART (mirror charts.js BarChart.draw) ===
# =====================================================================
def bar_chart(canvas, x: float, y: float, w: float, h: float,
              data: list[dict], opts: Optional[dict] = None) -> None:
    """Draw a bar chart.
    
    Args:
        data: list of {label, value, color}
        opts: {
          maxValue:    optional y-axis max
          barWidth:    optional fixed bar width
          gap:         gap between bars (default 6)
          baselineY:   optional y position of baseline
          showLabels:  bool (default True)
          showValues:  bool (default False)
          labelColor:  color for labels
          valueColor:  color for values
          baselineColor: color for baseline
        }
    """
    opts = opts or {}
    if not data:
        return
    max_val = opts.get("maxValue") or max([d.get("value", 0) for d in data] + [1])
    gap = opts.get("gap", 6)
    label_color = opts.get("labelColor", config.TEXT_DIM)
    value_color = opts.get("valueColor", config.GOLD)
    baseline_color = opts.get("baselineColor", config.SURFACE_HI)
    show_labels = opts.get("showLabels", True)
    show_values = opts.get("showValues", False)
    label_area_h = 18 if show_labels else 4
    value_area_h = 14 if show_values else 0
    chart_h = h - label_area_h - value_area_h
    bar_w = opts.get("barWidth") or max(2, (w - gap * (len(data) + 1)) / len(data))
    baseline_y = y + chart_h
    # Baseline
    canvas.create_line(x, baseline_y, x + w, baseline_y,
                       fill=baseline_color, width=1)
    # Bars
    for i, d in enumerate(data):
        val = float(d.get("value", 0))
        bh = (val / max_val) * chart_h if max_val > 0 else 0
        bx = x + gap + i * (bar_w + gap)
        by = baseline_y - bh
        color = d.get("color", config.GOLD)
        # Rounded top (Tk doesn't support rounded rects natively — simulate with arc)
        radius = min(3, bar_w / 2)
        if bh > radius * 2:
            # Draw rect with arc on top
            canvas.create_rectangle(
                bx, by + radius, bx + bar_w, by + bh,
                fill=color, outline="",
            )
            canvas.create_rectangle(
                bx, by + radius, bx + bar_w, by + radius * 2,
                fill=color, outline="",
            )
            # Top corners (rounded) — approximate with ovals
            canvas.create_oval(
                bx, by, bx + 2 * radius, by + 2 * radius,
                fill=color, outline="",
            )
            canvas.create_oval(
                bx + bar_w - 2 * radius, by, bx + bar_w, by + 2 * radius,
                fill=color, outline="",
            )
        else:
            canvas.create_rectangle(
                bx, by, bx + bar_w, by + bh,
                fill=color, outline="",
            )
        # Label
        if show_labels and d.get("label"):
            canvas.create_text(
                bx + bar_w / 2, baseline_y + 9,
                text=str(d["label"]), fill=label_color,
                font=("TkDefaultFont", 9),
            )
        # Value
        if show_values and val > 0:
            canvas.create_text(
                bx + bar_w / 2, by - 7,
                text=str(int(val)), fill=value_color,
                font=("TkDefaultFont", 9, "bold"),
            )


# =====================================================================
# === DONUT CHART (mirror charts.js DonutChart.draw) ===
# =====================================================================
def donut_chart(canvas, cx: float, cy: float, r: float,
                data: list[dict], line_width: float = 18) -> None:
    """Draw a donut chart.
    
    Args:
        data: list of {label, value, color}
        line_width: thickness of the ring
    """
    if not data:
        # Empty track
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           outline=config.SURFACE_HI, width=line_width)
        return
    total = sum(d.get("value", 0) for d in data) or 1
    # Track
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=config.SURFACE_HI, width=line_width)
    # Segments
    start_angle = 90  # start at 12 o'clock
    for d in data:
        val = float(d.get("value", 0))
        if val <= 0:
            continue
        extent = -360 * (val / total)  # clockwise
        color = d.get("color", config.GOLD)
        canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=start_angle, extent=extent,
            style="arc", outline=color, width=line_width,
        )
        start_angle += extent


# =====================================================================
# === DONUT CHART WITH LEGEND ===
# =====================================================================
def donut_with_legend(canvas, cx: float, cy: float, r: float,
                       data: list[dict], line_width: float = 18,
                       legend_x: float = None, legend_y: float = None) -> None:
    """Draw a donut chart with a side legend.
    
    The legend is drawn to the right of the donut by default.
    """
    donut_chart(canvas, cx, cy, r, data, line_width)
    # Legend
    lx = legend_x or (cx + r + line_width + 16)
    ly = legend_y or (cy - r)
    for i, d in enumerate(data):
        color = d.get("color", config.GOLD)
        label = d.get("label", "")
        value = d.get("value", 0)
        # Color swatch
        canvas.create_rectangle(lx, ly + i * 22, lx + 12, ly + i * 22 + 12,
                                 fill=color, outline="")
        # Label
        canvas.create_text(lx + 18, ly + i * 22 + 6,
                           text=label, fill=config.TEXT,
                           font=("TkDefaultFont", 10), anchor="w")
        # Value (right-aligned)
        canvas.create_text(lx + 150, ly + i * 22 + 6,
                           text=str(int(value)), fill=config.GOLD,
                           font=("TkDefaultFont", 10, "bold"), anchor="e")


# =====================================================================
# === HEATMAP (mirror charts.js Heatmap.draw) ===
# =====================================================================
def heatmap(canvas, x: float, y: float, w: float, h: float,
            year: int, data: dict[str, int], cell_size: float = 12) -> None:
    """Draw a yearly heatmap (GitHub-style contributions grid).
    
    Args:
        year:      year to render
        data:      {date_iso: seconds}
        cell_size: size of each day cell
    """
    gap = 3
    # Find max value for intensity scaling
    max_val = max(list(data.values()) + [1])
    # Find the Saturday of the first week of the year
    start = _dt.date(year, 1, 1)
    py_wd = start.weekday()  # Mon=0, Sun=6
    # Convert to Persian week (Sat=0): Sat=5, Sun=6, Mon=0, ...
    offset = (py_wd + 2) % 7
    cursor = start - _dt.timedelta(days=offset)
    end = _dt.date(year, 12, 31)
    col = 0
    while cursor <= end:
        for row in range(7):
            if cursor.year == year:
                iso = cursor.isoformat()
                sec = data.get(iso, 0)
                t = sec / max_val if max_val > 0 else 0
                color = config.heatmap_color(t)
                # Draw rounded rect (approximate with plain rect)
                canvas.create_rectangle(
                    x + col * (cell_size + gap),
                    y + row * (cell_size + gap),
                    x + col * (cell_size + gap) + cell_size,
                    y + row * (cell_size + gap) + cell_size,
                    fill=color, outline="",
                )
            cursor = cursor + _dt.timedelta(days=1)
        col += 1
        if col * (cell_size + gap) > w:
            break


# =====================================================================
# === LINE CHART (extends web edition) ===
# =====================================================================
def line_chart(canvas, x: float, y: float, w: float, h: float,
               data: list[dict], opts: Optional[dict] = None) -> None:
    """Draw a line chart.
    
    Args:
        data: list of {label, value}
        opts: {
          maxValue:    optional y-axis max
          minValue:    optional y-axis min
          lineColor:   color of the line
          fillColor:   optional fill color under the line
          pointColor:  optional point markers
          baselineColor: color for baseline
          labelColor:  color for labels
          showLabels:  bool (default True)
          showPoints:  bool (default False)
          smooth:      bool (default False, bezier smoothing)
        }
    """
    opts = opts or {}
    if not data or len(data) < 2:
        return
    vals = [d.get("value", 0) for d in data]
    max_val = opts.get("maxValue", max(vals + [1]))
    min_val = opts.get("minValue", min(vals + [0]))
    line_color = opts.get("lineColor", config.GOLD)
    fill_color = opts.get("fillColor")
    point_color = opts.get("pointColor", config.GOLD)
    baseline_color = opts.get("baselineColor", config.SURFACE_HI)
    label_color = opts.get("labelColor", config.TEXT_DIM)
    show_labels = opts.get("showLabels", True)
    show_points = opts.get("showPoints", False)
    smooth = opts.get("smooth", False)
    label_area_h = 18 if show_labels else 4
    chart_h = h - label_area_h
    baseline_y = y + chart_h
    # Baseline
    canvas.create_line(x, baseline_y, x + w, baseline_y,
                       fill=baseline_color, width=1)
    # Build points
    step_x = w / (len(data) - 1) if len(data) > 1 else w
    points = []
    for i, d in enumerate(data):
        val = float(d.get("value", 0))
        if max_val > min_val:
            normalized = (val - min_val) / (max_val - min_val)
        else:
            normalized = 0.5
        px = x + i * step_x
        py = baseline_y - normalized * chart_h
        points.append((px, py))
    # Fill area under the line
    if fill_color and len(points) >= 2:
        fill_points = [(x, baseline_y)] + points + [(x + w, baseline_y)]
        flat = [coord for pt in fill_points for coord in pt]
        canvas.create_polygon(flat, fill=fill_color, outline="")
    # Line (smooth or straight)
    if len(points) >= 2:
        if smooth:
            # Approximate smooth curve with multiple short line segments
            for i in range(len(points) - 1):
                canvas.create_line(
                    points[i][0], points[i][1], points[i + 1][0], points[i + 1][1],
                    fill=line_color, width=2, smooth=True,
                )
        else:
            flat = [coord for pt in points for coord in pt]
            canvas.create_line(flat, fill=line_color, width=2, smooth=smooth)
    # Points
    if show_points:
        for px, py in points:
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3,
                                fill=point_color, outline="")
    # Labels
    if show_labels:
        for i, d in enumerate(data):
            if i % max(1, len(data) // 6) != 0 and i != len(data) - 1:
                continue  # don't crowd
            if d.get("label"):
                px = x + i * step_x
                canvas.create_text(
                    px, baseline_y + 9,
                    text=str(d["label"]), fill=label_color,
                    font=("TkDefaultFont", 8),
                )


# =====================================================================
# === SPARKLINE (small inline trend) ===
# =====================================================================
def sparkline(canvas, x: float, y: float, w: float, h: float,
              data: list[float], color: str = config.GOLD,
              fill: bool = False, fill_color: Optional[str] = None) -> None:
    """Draw a tiny line chart for inline trends."""
    if not data or len(data) < 2:
        return
    max_val = max(data + [1])
    min_val = min(data + [0])
    step_x = w / (len(data) - 1)
    points = []
    for i, val in enumerate(data):
        if max_val > min_val:
            normalized = (val - min_val) / (max_val - min_val)
        else:
            normalized = 0.5
        px = x + i * step_x
        py = y + h - normalized * h
        points.append((px, py))
    if fill and fill_color:
        fill_points = [(x, y + h)] + points + [(x + w, y + h)]
        flat = [coord for pt in fill_points for coord in pt]
        canvas.create_polygon(flat, fill=fill_color, outline="")
    flat = [coord for pt in points for coord in pt]
    canvas.create_line(flat, fill=color, width=1.5, smooth=True)


# =====================================================================
# === RADIAL PROGRESS (full circle, no label) ===
# =====================================================================
def radial_progress(canvas, cx: float, cy: float, r: float,
                     progress: float, color: str = config.GOLD,
                     track_color: str = config.SURFACE_HI,
                     line_width: float = 4) -> None:
    """Draw a thin radial progress indicator (used in goal rings)."""
    progress = max(0.0, min(1.0, float(progress)))
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=track_color, width=line_width)
    if progress > 0:
        extent = -360 * progress
        canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=extent,
            style="arc", outline=color, width=line_width,
        )


# =====================================================================
# === HISTOGRAM (extends web edition) ===
# =====================================================================
def histogram(canvas, x: float, y: float, w: float, h: float,
              bins: int, data: list[float], color: str = config.GOLD,
              max_value: Optional[float] = None) -> None:
    """Draw a histogram of the given values.
    
    Args:
        bins: number of bins
        data: list of numeric values
        color: bar color
        max_value: optional max value for x-axis (auto if None)
    """
    if not data:
        return
    max_val = max_value or max(data)
    min_val = min(data)
    if max_val == min_val:
        # Single bin
        bar_w = w - 8
        bar_h = h - 18
        canvas.create_rectangle(x + 4, y, x + 4 + bar_w, y + bar_h,
                                 fill=color, outline="")
        return
    bin_width = (max_val - min_val) / bins
    counts = [0] * bins
    for v in data:
        idx = int((v - min_val) / bin_width)
        if idx >= bins:
            idx = bins - 1
        counts[idx] += 1
    max_count = max(counts + [1])
    bar_w = (w - 4) / bins
    chart_h = h - 18
    for i, c in enumerate(counts):
        bh = (c / max_count) * chart_h
        bx = x + 2 + i * bar_w
        by = y + chart_h - bh
        if bh > 0:
            canvas.create_rectangle(
                bx, by, bx + bar_w - 2, y + chart_h,
                fill=color, outline="",
            )


# =====================================================================
# === WEEKLY HEATMAP STRIP (7 rows x N weeks) ===
# =====================================================================
def weekly_heatmap_strip(canvas, x: float, y: float, w: float, h: float,
                          start_date: _dt.date, end_date: _dt.date,
                          data: dict[str, int], cell_size: float = 10) -> None:
    """Draw a heatmap strip from start_date to end_date (inclusive).
    
    Args:
        data: {date_iso: seconds}
    """
    gap = 2
    max_val = max(list(data.values()) + [1])
    # Find Saturday of start week
    py_wd = start_date.weekday()
    offset = (py_wd + 2) % 7
    cursor = start_date - _dt.timedelta(days=offset)
    col = 0
    while cursor <= end_date:
        for row in range(7):
            if start_date <= cursor <= end_date:
                iso = cursor.isoformat()
                sec = data.get(iso, 0)
                t = sec / max_val if max_val > 0 else 0
                color = config.heatmap_color(t)
                canvas.create_rectangle(
                    x + col * (cell_size + gap),
                    y + row * (cell_size + gap),
                    x + col * (cell_size + gap) + cell_size,
                    y + row * (cell_size + gap) + cell_size,
                    fill=color, outline="",
                )
            cursor = cursor + _dt.timedelta(days=1)
        col += 1
        if col * (cell_size + gap) > w:
            break


# =====================================================================
# === GAUGE (extends web edition) ===
# =====================================================================
def gauge(canvas, cx: float, cy: float, r: float,
          value: float, max_value: float = 100.0,
          color: str = config.GOLD, track_color: str = config.SURFACE_HI,
          line_width: float = 10, label: Optional[str] = None,
          label_color: str = config.TEXT) -> None:
    """Draw a semicircular gauge (180 degrees, pointing up).
    
    Args:
        value: current value
        max_value: maximum value (for percentage calculation)
    """
    progress = max(0.0, min(1.0, value / max_value if max_value > 0 else 0))
    # Track (semicircle from 180 to 0)
    canvas.create_arc(
        cx - r, cy - r, cx + r, cy + r,
        start=0, extent=180,
        style="arc", outline=track_color, width=line_width,
    )
    # Filled portion (180 down to 180 - 180*progress)
    if progress > 0:
        canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=180, extent=-180 * progress,
            style="arc", outline=color, width=line_width,
        )
    if label:
        canvas.create_text(cx, cy + r // 3, text=label,
                           fill=label_color, font=("TkDefaultFont", 14, "bold"))


# =====================================================================
# === HORIZONTAL BAR (single value) ===
# =====================================================================
def horizontal_bar(canvas, x: float, y: float, w: float, h: float,
                    progress: float, color: str = config.GOLD,
                    track_color: str = config.SURFACE_HI,
                    radius: float = 0) -> None:
    """Draw a horizontal progress bar.
    
    Args:
        progress: 0.0 to 1.0
        radius: corner radius (0 = sharp)
    """
    progress = max(0.0, min(1.0, float(progress)))
    # Track
    canvas.create_rectangle(x, y, x + w, y + h, fill=track_color, outline="")
    # Fill
    fill_w = w * progress
    if fill_w > 0:
        canvas.create_rectangle(x, y, x + fill_w, y + h, fill=color, outline="")


# =====================================================================
# === PIE CHART (extends web edition) ===
# =====================================================================
def pie_chart(canvas, cx: float, cy: float, r: float,
              data: list[dict]) -> None:
    """Draw a traditional pie chart (filled slices, no donut hole).
    
    Args:
        data: list of {label, value, color}
    """
    if not data:
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill=config.SURFACE_HI, outline="")
        return
    total = sum(d.get("value", 0) for d in data) or 1
    start_angle = 90
    for d in data:
        val = float(d.get("value", 0))
        if val <= 0:
            continue
        extent = -360 * (val / total)
        color = d.get("color", config.GOLD)
        canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=start_angle, extent=extent,
            style="pieslice", fill=color, outline=config.MATTE_BLACK,
        )
        start_angle += extent


# =====================================================================
# === STACKED AREA (extends web edition) ===
# =====================================================================
def stacked_area(canvas, x: float, y: float, w: float, h: float,
                 series: list[dict], opts: Optional[dict] = None) -> None:
    """Draw a stacked area chart.
    
    Args:
        series: list of {label, color, values: [v1, v2, ...]}
        opts: {maxValue, labelColor, baselineColor, showLabels}
    """
    opts = opts or {}
    if not series:
        return
    n = len(series[0].get("values", []))
    if n == 0:
        return
    # Compute totals per index
    totals = [0] * n
    for s in series:
        for i, v in enumerate(s.get("values", [])):
            totals[i] += v
    max_val = opts.get("maxValue", max(totals + [1]))
    label_area_h = 18 if opts.get("showLabels", True) else 4
    chart_h = h - label_area_h
    baseline_y = y + chart_h
    step_x = w / (n - 1) if n > 1 else w
    # Draw each series from bottom up
    cumulative = [0] * n
    for s in series:
        color = s.get("color", config.GOLD)
        new_cumulative = [cumulative[i] + s["values"][i] for i in range(n)]
        # Polygon: bottom (cumulative) reversed, then top (new_cumulative)
        top_points = []
        for i in range(n):
            px = x + i * step_x
            py = baseline_y - (new_cumulative[i] / max_val) * chart_h if max_val > 0 else baseline_y
            top_points.append((px, py))
        bottom_points = []
        for i in range(n - 1, -1, -1):
            px = x + i * step_x
            py = baseline_y - (cumulative[i] / max_val) * chart_h if max_val > 0 else baseline_y
            bottom_points.append((px, py))
        polygon_pts = top_points + bottom_points
        flat = [coord for pt in polygon_pts for coord in pt]
        canvas.create_polygon(flat, fill=color, outline="")
        cumulative = new_cumulative


# =====================================================================
# === LEGEND (for charts) ===
# =====================================================================
def legend(canvas, x: float, y: float, items: list[dict],
           item_height: float = 22, swatch_size: float = 12) -> float:
    """Draw a legend. Returns the y position after the last item."""
    for i, item in enumerate(items):
        color = item.get("color", config.GOLD)
        label = item.get("label", "")
        value = item.get("value")
        swatch_y = y + i * item_height
        canvas.create_rectangle(x, swatch_y, x + swatch_size, swatch_y + swatch_size,
                                 fill=color, outline="")
        canvas.create_text(x + swatch_size + 8, swatch_y + swatch_size / 2,
                           text=label, fill=config.TEXT,
                           font=("TkDefaultFont", 10), anchor="w")
        if value is not None:
            canvas.create_text(x + 200, swatch_y + swatch_size / 2,
                               text=str(value), fill=config.GOLD,
                               font=("TkDefaultFont", 10, "bold"), anchor="e")
    return y + len(items) * item_height


# =====================================================================
# === AXIS LABELS ===
# =====================================================================
def y_axis_labels(canvas, x: float, y: float, h: float,
                   min_val: float, max_val: float, steps: int = 4,
                   color: str = config.TEXT_FAINT, formatter=None) -> None:
    """Draw y-axis labels."""
    if max_val == min_val:
        return
    for i in range(steps + 1):
        val = max_val - (max_val - min_val) * i / steps
        py = y + i * (h / steps)
        text = formatter(val) if formatter else str(int(val))
        canvas.create_text(x, py, text=text, fill=color,
                           font=("TkDefaultFont", 8), anchor="e")


def x_axis_labels(canvas, x: float, y: float, w: float, labels: list[str],
                   color: str = config.TEXT_FAINT, every: int = 1) -> None:
    """Draw x-axis labels."""
    if not labels:
        return
    step = w / max(1, len(labels) - 1)
    for i, label in enumerate(labels):
        if i % every != 0 and i != len(labels) - 1:
            continue
        px = x + i * step
        canvas.create_text(px, y, text=label, fill=color,
                           font=("TkDefaultFont", 8))
