"""
rask.ui.widgets.charts
======================

Canvas chart widgets mirroring ``web/js/charts.js`` exactly.

All charts:
  * Are based on :class:`customtkinter.CTkCanvas`
  * Accept data via ``set_data(data)`` and repaint via ``redraw()``
  * Auto-scale axes
  * Animate transitions from old to new values (ease_out_cubic)
  * Display Persian digits when ``lang="fa"``
  * Mirror layout (RTL) when ``lang="fa"``

Charts
------
``BarChart``    — vertical bars with labels, colors, hover tooltip, grid
``LineChart``  — line + optional area fill, multiple series, hover crosshair
``DonutChart``  — donut with multiple segments + center label
``Heatmap``     — year-grid heatmap (53 weeks × 7 days), gold intensity
``Sparkline``   — tiny inline trend line (no axes), used in stat cards
``RadarChart``  — radar / spider chart for category comparison
``Histogram``   — distribution histogram with bins
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import customtkinter as ctk
    _CTK_OK = True
except Exception:
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme

__all__ = ["BarChart", "LineChart", "DonutChart", "Heatmap",
           "Sparkline", "RadarChart", "Histogram"]


# =============================================================================
# === Helpers                                                               ===
# =============================================================================

def _to_fa(s: str, lang: str) -> str:
    if lang == "fa":
        return i18n.to_fa_digits(s)
    return s


def _nice_max(value: float) -> float:
    """Round `value` up to a 'nice' round number for axis ticks."""
    if value <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(value))
    frac = value / exp
    if frac <= 1:
        return exp
    if frac <= 2:
        return 2 * exp
    if frac <= 5:
        return 5 * exp
    return 10 * exp


def _round_rect(canvas: Any, x1: float, y1: float, x2: float, y2: float,
                r: float, **kwargs: Any) -> int:
    """Draw a rounded rectangle on `canvas`."""
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
        x1 + r, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# =============================================================================
# === AnimatedCanvas base                                                   ===
# =============================================================================

class _AnimatedCanvas(ctk.CTkCanvas):  # type: ignore[misc]
    """Common base for all charts — handles resize + animation."""

    def __init__(self, master: Any = None, lang: str = "fa",
                 animated: bool = True,
                 animation_duration_ms: int = config.ANIM_NORMAL,
                 **kwargs: Any) -> None:
        kwargs.setdefault("bg", config.MATTE_BLACK)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._animated = animated
        self._duration = animation_duration_ms
        self._anim_job = None
        self._anim_step = 0
        self._anim_total = 0
        self._anim_start_state: Any = None
        self._target_state: Any = None
        self._hover_id: Optional[int] = None
        self._tooltip_win = None
        try:
            self.bind("<Configure>", lambda _e: self.redraw(), add="+")
            self.bind("<Motion>", self._on_motion, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # API to be overridden
    # ------------------------------------------------------------------
    def redraw(self) -> None:
        """Repaint the chart.  Subclasses override."""
        pass

    def set_data(self, data: Any) -> None:
        """Update chart data and (optionally) animate."""
        old = self._get_state_snapshot()
        self._apply_data(data)
        new = self._get_state_snapshot()
        if not self._animated or old is None:
            self.redraw()
            return
        self._animate_state(old, new)

    def _apply_data(self, data: Any) -> None:
        """Subclass hook — store data into instance attributes."""
        pass

    def _get_state_snapshot(self) -> Any:
        """Subclass hook — return a snapshot of the current state."""
        return None

    def _animate_state(self, old: Any, new: Any) -> None:
        """Subclass hook — animate from `old` to `new`."""
        self.redraw()

    # ------------------------------------------------------------------
    # Hover tooltip
    # ------------------------------------------------------------------
    def _show_tooltip(self, x: float, y: float, text: str) -> None:
        try:
            if self._tooltip_win is not None:
                self._tooltip_win.destroy()
            tip = ctk.CTkToplevel(self)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            try:
                tip.attributes("-alpha", 0.95)
            except Exception:
                pass
            lbl = ctk.CTkLabel(
                tip, text=text,
                fg_color=config.SURFACE_HIGHER,
                text_color=config.TEXT,
                corner_radius=config.RADIUS_SM,
                padx=8, pady=4,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
            )
            lbl.pack()
            # Position near cursor
            abs_x = self.winfo_rootx() + int(x) + 12
            abs_y = self.winfo_rooty() + int(y) + 12
            tip.geometry(f"+{abs_x}+{abs_y}")
            self._tooltip_win = tip
        except Exception:
            pass

    def _hide_tooltip(self) -> None:
        if self._tooltip_win is not None:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None

    def _on_motion(self, evt: Any) -> None:
        pass

    def _on_leave(self, _evt: Any) -> None:
        self._hide_tooltip()
        if self._hover_id is not None:
            try:
                self.delete(self._hover_id)
            except Exception:
                pass
            self._hover_id = None


# =============================================================================
# === BarChart                                                              ===
# =============================================================================

class BarChart(_AnimatedCanvas):
    """Vertical bar chart.

    Data format
    -----------
    Iterable of dicts ``{"label", "value", "color"}``.  If ``color`` is
    omitted, gold is used.  ``label`` is shown beneath each bar.
    """

    def __init__(
        self,
        master: Any = None,
        data: Sequence[dict] = (),
        width: int = 320,
        height: int = 180,
        max_value: Optional[float] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, **kwargs)
        self._data: List[dict] = list(data)
        self._max_value = max_value
        self._animated_values: List[float] = [d.get("value", 0) for d in self._data]
        self.redraw()

    # ------------------------------------------------------------------
    def _apply_data(self, data: Any) -> None:
        self._data = list(data) if data else []
        # Pad or trim animated_values
        while len(self._animated_values) < len(self._data):
            self._animated_values.append(0.0)
        self._animated_values = self._animated_values[:len(self._data)]

    def _get_state_snapshot(self) -> Any:
        return list(self._animated_values)

    def _animate_state(self, old: Any, new: Any) -> None:
        if not isinstance(old, list) or not isinstance(new, list):
            return
        self._anim_start_state = list(old)
        self._target_state = list(new)
        # Pad to same length
        while len(self._anim_start_state) < len(self._target_state):
            self._anim_start_state.append(0.0)
        self._anim_start_state = self._anim_start_state[:len(self._target_state)]
        self._anim_step = 0
        self._anim_total = max(2, self._duration // 16)
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total)
        self._animated_values = [
            helpers.lerp(s, e, t)
            for s, e in zip(self._anim_start_state, self._target_state)
        ]
        self.redraw()
        if self._anim_step < self._anim_total:
            self._anim_job = self.after(16, self._tick_anim)
        else:
            self._animated_values = list(self._target_state)
            self.redraw()
            self._anim_job = None

    # ------------------------------------------------------------------
    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20 or not self._data:
            return
        rtl = i18n.is_rtl(self._lang)
        # Compute max
        max_val = self._max_value or max(
            [d.get("value", 0) for d in self._data] + [1])
        max_val = _nice_max(max_val)
        # Layout
        pad_top = 8
        pad_bot = 24  # space for labels
        gap = 6
        n = len(self._data)
        bar_w = max(2, (w - gap * (n + 1)) / n)
        chart_h = h - pad_top - pad_bot
        baseline_y = h - pad_bot
        # Grid lines (3 horizontal)
        for i in range(1, 4):
            y = pad_top + chart_h * i / 4
            try:
                self.create_line(0, y, w, y, fill=config.DIVIDER, dash=(2, 4))
            except Exception:
                pass
        # Baseline
        try:
            self.create_line(0, baseline_y, w, baseline_y,
                              fill=config.DIVIDER)
        except Exception:
            pass
        # Bars
        for i, d in enumerate(self._data):
            val = self._animated_values[i] if i < len(self._animated_values) else 0
            bh = (val / max_val) * chart_h if max_val > 0 else 0
            bx = gap + i * (bar_w + gap)
            if rtl:
                bx = w - gap - (i + 1) * bar_w - i * gap
            by = baseline_y - bh
            color = d.get("color", config.GOLD)
            try:
                _round_rect(self, bx, by, bx + bar_w, baseline_y,
                            min(3, bar_w / 2), fill=color, outline="")
            except Exception:
                self.create_rectangle(bx, by, bx + bar_w, baseline_y,
                                       fill=color, outline="")
            # Label
            label = d.get("label", "")
            if label:
                try:
                    self.create_text(
                        bx + bar_w / 2, h - 8,
                        text=_to_fa(label, self._lang),
                        fill=config.TEXT_DIM,
                        font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                                weight="normal",
                                                lang=self._lang),
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    def _on_motion(self, evt: Any) -> None:
        if not self._data:
            return
        try:
            w = int(self.cget("width"))
            n = len(self._data)
            gap = 6
            bar_w = max(2, (w - gap * (n + 1)) / n)
            for i, d in enumerate(self._data):
                bx = gap + i * (bar_w + gap)
                if bx <= evt.x <= bx + bar_w:
                    label = d.get("label", "")
                    val = d.get("value", 0)
                    text = f"{label}: {_to_fa(str(val), self._lang)}"
                    self._show_tooltip(evt.x, evt.y, text)
                    return
            self._hide_tooltip()
        except Exception:
            pass


# =============================================================================
# === LineChart                                                             ===
# =============================================================================

class LineChart(_AnimatedCanvas):
    """Line chart with optional area fill and multiple series.

    Data format
    -----------
    Iterable of dicts ``{"label", "values": [y0, y1, ...], "color"}``.
    All series must have the same length.  ``label`` is the series name
    shown in the legend.
    """

    def __init__(
        self,
        master: Any = None,
        data: Sequence[dict] = (),
        labels: Optional[Sequence[str]] = None,
        width: int = 320,
        height: int = 180,
        max_value: Optional[float] = None,
        area_fill: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, **kwargs)
        self._data: List[dict] = list(data)
        self._labels: List[str] = list(labels or [])
        self._max_value = max_value
        self._area_fill = area_fill
        self._animated_values: List[List[float]] = [
            list(s.get("values", [])) for s in self._data
        ]
        self.redraw()

    # ------------------------------------------------------------------
    def _apply_data(self, data: Any) -> None:
        self._data = list(data) if data else []
        self._animated_values = [list(s.get("values", [])) for s in self._data]

    def _get_state_snapshot(self) -> Any:
        return [list(s) for s in self._animated_values]

    def _animate_state(self, old: Any, new: Any) -> None:
        if not isinstance(old, list) or not isinstance(new, list):
            return
        self._anim_start_state = old
        self._target_state = new
        self._anim_step = 0
        self._anim_total = max(2, self._duration // 16)
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total)
        new_vals: List[List[float]] = []
        for s_old, s_new in zip(self._anim_start_state, self._target_state):
            series: List[float] = []
            for v_old, v_new in zip(s_old, s_new):
                series.append(helpers.lerp(v_old, v_new, t))
            new_vals.append(series)
        self._animated_values = new_vals
        self.redraw()
        if self._anim_step < self._anim_total:
            self._anim_job = self.after(16, self._tick_anim)
        else:
            self._animated_values = [list(s) for s in self._target_state]
            self.redraw()
            self._anim_job = None

    # ------------------------------------------------------------------
    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20 or not self._data:
            return
        rtl = i18n.is_rtl(self._lang)
        pad_top, pad_bot, pad_lr = 8, 24, 12
        chart_w = w - pad_lr * 2
        chart_h = h - pad_top - pad_bot
        baseline_y = h - pad_bot
        # Max value across all series
        all_vals = [v for s in self._animated_values for v in s]
        max_val = self._max_value or max(all_vals + [1])
        max_val = _nice_max(max_val)
        # Grid lines
        for i in range(1, 4):
            y = pad_top + chart_h * i / 4
            try:
                self.create_line(pad_lr, y, w - pad_lr, y,
                                  fill=config.DIVIDER, dash=(2, 4))
            except Exception:
                pass
        # Each series
        n_points = max((len(s) for s in self._animated_values), default=0)
        if n_points == 0:
            return
        for series_idx, (series_def, series_vals) in enumerate(
                zip(self._data, self._animated_values)):
            color = series_def.get("color", config.GOLD)
            points: List[Tuple[float, float]] = []
            for i, v in enumerate(series_vals):
                x = pad_lr + (chart_w * i / max(1, n_points - 1))
                if rtl:
                    x = w - pad_lr - (chart_w * i / max(1, n_points - 1))
                y = baseline_y - (v / max_val) * chart_h if max_val > 0 else baseline_y
                points.append((x, y))
            if len(points) < 2:
                continue
            # Area fill (semi-transparent gold)
            if self._area_fill:
                fill_pts = points + [(points[-1][0], baseline_y),
                                      (points[0][0], baseline_y)]
                try:
                    # Tk doesn't support alpha; approximate with a darkened gold
                    fill_color = helpers.mix_colors(color, config.MATTE_BLACK, 0.78)
                    self.create_polygon(fill_pts, fill=fill_color, outline="")
                except Exception:
                    pass
            # Line
            try:
                self.create_line(points, fill=color, width=2, smooth=True,
                                  splinesteps=8)
            except Exception:
                pass
            # Dots on each point
            for x, y in points:
                try:
                    r = 3
                    self.create_oval(x - r, y - r, x + r, y + r,
                                      fill=color, outline="")
                except Exception:
                    pass
        # X-axis labels
        if self._labels:
            for i, label in enumerate(self._labels):
                x = pad_lr + (chart_w * i / max(1, n_points - 1))
                if rtl:
                    x = w - pad_lr - (chart_w * i / max(1, n_points - 1))
                try:
                    self.create_text(x, h - 8,
                                      text=_to_fa(label, self._lang),
                                      fill=config.TEXT_DIM,
                                      font=_theme.theme.font(
                                          size=config.FONT_SIZE_CAPTION,
                                          weight="normal", lang=self._lang))
                except Exception:
                    pass

    # ------------------------------------------------------------------
    def _on_motion(self, evt: Any) -> None:
        if not self._data:
            return
        try:
            w = int(self.cget("width"))
            h = int(self.cget("height"))
            pad_top, pad_bot, pad_lr = 8, 24, 12
            chart_w = w - pad_lr * 2
            n_points = max((len(s) for s in self._animated_values), default=0)
            if n_points == 0:
                return
            # Find closest x index
            x = evt.x
            if i18n.is_rtl(self._lang):
                t = (w - pad_lr - x) / chart_w
            else:
                t = (x - pad_lr) / chart_w
            idx = int(round(t * (n_points - 1)))
            idx = helpers.clamp(idx, 0, n_points - 1)
            label = self._labels[idx] if idx < len(self._labels) else str(idx)
            parts = [label]
            for s in self._data:
                vals = s.get("values", [])
                if idx < len(vals):
                    parts.append(f"{s.get('label', '')}: "
                                  f"{_to_fa(str(vals[idx]), self._lang)}")
            self._show_tooltip(evt.x, evt.y, "\n".join(parts))
        except Exception:
            pass


# =============================================================================
# === DonutChart                                                            ===
# =============================================================================

class DonutChart(_AnimatedCanvas):
    """Donut chart with multiple segments + center label.

    Data format
    -----------
    Iterable of dicts ``{"label", "value", "color"}``.
    """

    def __init__(
        self,
        master: Any = None,
        data: Sequence[dict] = (),
        width: int = 200,
        height: int = 200,
        line_width: int = 18,
        center_label: Optional[str] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, **kwargs)
        self._data: List[dict] = list(data)
        self._line_width = line_width
        self._center_label = center_label
        self._animated_values: List[float] = [d.get("value", 0) for d in self._data]
        self.redraw()

    def _apply_data(self, data: Any) -> None:
        self._data = list(data) if data else []
        while len(self._animated_values) < len(self._data):
            self._animated_values.append(0.0)
        self._animated_values = self._animated_values[:len(self._data)]

    def _get_state_snapshot(self) -> Any:
        return list(self._animated_values)

    def _animate_state(self, old: Any, new: Any) -> None:
        if not isinstance(old, list) or not isinstance(new, list):
            return
        self._anim_start_state = list(old)
        self._target_state = list(new)
        while len(self._anim_start_state) < len(self._target_state):
            self._anim_start_state.append(0.0)
        self._anim_start_state = self._anim_start_state[:len(self._target_state)]
        self._anim_step = 0
        self._anim_total = max(2, self._duration // 16)
        self._tick_anim()

    def _tick_anim(self) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total)
        self._animated_values = [
            helpers.lerp(s, e, t)
            for s, e in zip(self._anim_start_state, self._target_state)
        ]
        self.redraw()
        if self._anim_step < self._anim_total:
            self._anim_job = self.after(16, self._tick_anim)
        else:
            self._animated_values = list(self._target_state)
            self.redraw()
            self._anim_job = None

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20:
            return
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - self._line_width
        # Track
        try:
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                              outline=config.SURFACE_HI,
                              width=self._line_width)
        except Exception:
            pass
        total = sum(self._animated_values) or 1
        angle = 90
        for i, seg in enumerate(self._data):
            val = self._animated_values[i] if i < len(self._animated_values) else 0
            if val <= 0:
                continue
            extent = -360 * (val / total)
            color = seg.get("color", config.GOLD)
            try:
                self.create_arc(cx - r, cy - r, cx + r, cy + r,
                                outline=color, width=self._line_width,
                                style="arc", start=angle, extent=extent)
            except Exception:
                pass
            angle += extent
        # Center label
        text = self._center_label
        if text is None:
            total_val = sum(self._animated_values)
            text = _to_fa(str(int(total_val)), self._lang)
        try:
            self.create_text(cx, cy, text=text, fill=config.TEXT,
                              font=_theme.theme.font(
                                  size=int(min(w, h) * 0.18),
                                  weight="bold", lang=self._lang))
        except Exception:
            pass


# =============================================================================
# === Heatmap                                                               ===
# =============================================================================

class Heatmap(_AnimatedCanvas):
    """Year-grid heatmap (53 weeks × 7 days), gold intensity scale."""

    def __init__(
        self,
        master: Any = None,
        year: Optional[int] = None,
        data: Optional[Dict[str, int]] = None,
        cell_size: int = 12,
        gap: int = 3,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        if year is None:
            year = date.today().year
        self._year = year
        self._data: Dict[str, int] = dict(data or {})
        self._cell_size = cell_size
        self._gap = gap
        width = 53 * (cell_size + gap) + gap
        height = 7 * (cell_size + gap) + gap + 24
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, animated=False, **kwargs)
        self.redraw()

    def _apply_data(self, data: Any) -> None:
        if isinstance(data, dict):
            self._data = dict(data)
        elif isinstance(data, (list, tuple)) and len(data) == 2:
            self._year, self._data = data  # type: ignore[assignment]
            self._data = dict(self._data)
        else:
            self._data = {}

    def _intensity_color(self, t: float) -> str:
        """Return a gold-intensity colour for `t` in [0, 1]."""
        levels = config.HEATMAP_LEVELS
        idx = min(len(levels) - 1, int(t * len(levels)))
        return levels[idx]

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20:
            return
        cell = self._cell_size
        gap = self._gap
        max_val = max(list(self._data.values()) + [1])
        # Walk every day of the year, find week column + day row
        start = date(self._year, 1, 1)
        # Find Sunday of the first week (Saturday for Persian calendar
        # would be index 6 in Python's date.weekday()).
        offset = (start.weekday() + 1) % 7
        cursor = start - timedelta(days=offset)
        end = date(self._year, 12, 31)
        col = 0
        rtl = i18n.is_rtl(self._lang)
        while cursor <= end:
            for row in range(7):
                if cursor.year == self._year:
                    iso = cursor.isoformat()
                    val = self._data.get(iso, 0)
                    t = val / max_val if max_val > 0 else 0
                    color = self._intensity_color(t)
                    x = col * (cell + gap) + gap
                    if rtl:
                        x = w - x - cell
                    y = row * (cell + gap) + gap
                    try:
                        self.create_rectangle(
                            x, y, x + cell, y + cell,
                            fill=color, outline="",
                        )
                    except Exception:
                        pass
                cursor += timedelta(days=1)
            col += 1
        # Month labels along the top
        try:
            months = ["۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹", "۱۰",
                       "۱۱", "۱۲"] if self._lang == "fa" else [
                "J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
            for m in range(12):
                x = (m * 4 + 2) * (cell + gap)
                if rtl:
                    x = w - x
                self.create_text(x, h - 8, text=months[m],
                                  fill=config.TEXT_DIM,
                                  font=_theme.theme.font(
                                      size=config.FONT_SIZE_CAPTION,
                                      weight="normal", lang=self._lang))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_motion(self, evt: Any) -> None:
        try:
            cell = self._cell_size
            gap = self._gap
            w = int(self.cget("width"))
            rtl = i18n.is_rtl(self._lang)
            col = (evt.x - gap) // (cell + gap)
            row = (evt.y - gap) // (cell + gap)
            if not (0 <= col < 53 and 0 <= row < 7):
                self._hide_tooltip()
                return
            # Find the date for this col/row
            start = date(self._year, 1, 1)
            offset = (start.weekday() + 1) % 7
            cursor = start - timedelta(days=offset)
            cursor += timedelta(days=col * 7 + row)
            if cursor.year != self._year:
                self._hide_tooltip()
                return
            iso = cursor.isoformat()
            val = self._data.get(iso, 0)
            minutes = val // 60
            text = (f"{_to_fa(cursor.strftime('%Y-%m-%d'), self._lang)}\n"
                    f"{_to_fa(str(minutes), self._lang)} "
                    f"{'دقیقه' if self._lang == 'fa' else 'min'}")
            self._show_tooltip(evt.x, evt.y, text)
        except Exception:
            pass


# =============================================================================
# === Sparkline                                                             ===
# =============================================================================

class Sparkline(_AnimatedCanvas):
    """Tiny inline trend line — no axes, no labels.

    Used in :class:`StatCard` and inline next to a value.
    """

    def __init__(
        self,
        master: Any = None,
        data: Sequence[float] = (),
        width: int = 80,
        height: int = 24,
        color: str = config.GOLD,
        area_fill: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, animated=False, **kwargs)
        self._data: List[float] = list(data)
        self._color = color
        self._area_fill = area_fill
        self.redraw()

    def _apply_data(self, data: Any) -> None:
        self._data = list(data) if data else []

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 4 or h < 4 or len(self._data) < 2:
            return
        max_v = max(self._data) or 1
        min_v = min(self._data)
        span = max(1, max_v - min_v)
        pts: List[Tuple[float, float]] = []
        for i, v in enumerate(self._data):
            x = w * i / (len(self._data) - 1)
            y = h - 2 - (v - min_v) / span * (h - 4)
            pts.append((x, y))
        if self._area_fill:
            try:
                fill_pts = pts + [(pts[-1][0], h), (pts[0][0], h)]
                fill_color = helpers.mix_colors(self._color, config.MATTE_BLACK,
                                                 0.7)
                self.create_polygon(fill_pts, fill=fill_color, outline="")
            except Exception:
                pass
        try:
            self.create_line(pts, fill=self._color, width=1.5, smooth=True,
                              splinesteps=4)
        except Exception:
            pass


# =============================================================================
# === RadarChart                                                            ===
# =============================================================================

class RadarChart(_AnimatedCanvas):
    """Radar / spider chart for category comparison.

    Data format
    -----------
    Iterable of dicts ``{"label", "value", "color"}`` where ``value``
    is in ``[0, max_value]``.  Typically 5-7 axes.
    """

    def __init__(
        self,
        master: Any = None,
        data: Sequence[dict] = (),
        max_value: float = 100,
        width: int = 240,
        height: int = 240,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, animated=False, **kwargs)
        self._data: List[dict] = list(data)
        self._max_value = max_value
        self.redraw()

    def _apply_data(self, data: Any) -> None:
        self._data = list(data) if data else []

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20 or not self._data:
            return
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 24
        n = len(self._data)
        if n < 3:
            return
        # Grid rings (3 concentric polygons)
        for ring in (0.25, 0.5, 0.75, 1.0):
            pts = []
            for i in range(n):
                angle = -math.pi / 2 + i * 2 * math.pi / n
                x = cx + math.cos(angle) * r * ring
                y = cy + math.sin(angle) * r * ring
                pts.append((x, y))
            try:
                self.create_polygon(pts, outline=config.DIVIDER, fill="",
                                     width=1)
            except Exception:
                pass
        # Axis lines
        for i in range(n):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + math.cos(angle) * r
            y = cy + math.sin(angle) * r
            try:
                self.create_line(cx, cy, x, y, fill=config.DIVIDER)
            except Exception:
                pass
        # Data polygon
        data_pts = []
        for i, d in enumerate(self._data):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            val = helpers.clamp(d.get("value", 0) / self._max_value, 0, 1)
            x = cx + math.cos(angle) * r * val
            y = cy + math.sin(angle) * r * val
            data_pts.append((x, y))
        color = config.GOLD
        try:
            fill_color = helpers.mix_colors(color, config.MATTE_BLACK, 0.6)
            self.create_polygon(data_pts, outline=color, fill=fill_color,
                                 width=2)
        except Exception:
            pass
        # Dots on vertices
        for x, y in data_pts:
            try:
                self.create_oval(x - 3, y - 3, x + 3, y + 3,
                                  fill=color, outline="")
            except Exception:
                pass
        # Labels
        for i, d in enumerate(self._data):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            lx = cx + math.cos(angle) * (r + 14)
            ly = cy + math.sin(angle) * (r + 14)
            try:
                self.create_text(lx, ly, text=_to_fa(d.get("label", ""),
                                                       self._lang),
                                  fill=config.TEXT_DIM,
                                  font=_theme.theme.font(
                                      size=config.FONT_SIZE_CAPTION,
                                      weight="normal", lang=self._lang))
            except Exception:
                pass


# =============================================================================
# === Histogram                                                             ===
# =============================================================================

class Histogram(_AnimatedCanvas):
    """Distribution histogram with N bins."""

    def __init__(
        self,
        master: Any = None,
        values: Sequence[float] = (),
        bins: int = 10,
        width: int = 320,
        height: int = 180,
        color: str = config.GOLD,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, lang=lang, animated=False, **kwargs)
        self._values: List[float] = list(values)
        self._bins: int = bins
        self._color = color
        self.redraw()

    def _apply_data(self, data: Any) -> None:
        if isinstance(data, dict):
            self._values = list(data.get("values", []))
            self._bins = int(data.get("bins", self._bins))
        elif isinstance(data, (list, tuple)):
            self._values = list(data)
        else:
            self._values = []

    def redraw(self) -> None:
        try:
            self.delete("all")
        except Exception:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if w < 20 or h < 20 or not self._values or self._bins <= 0:
            return
        min_v = min(self._values)
        max_v = max(self._values)
        span = max(1e-9, max_v - min_v)
        bin_w = span / self._bins
        counts = [0] * self._bins
        for v in self._values:
            idx = min(self._bins - 1, int((v - min_v) / bin_w))
            counts[idx] += 1
        max_count = max(counts + [1])
        pad_top, pad_bot = 8, 24
        chart_h = h - pad_top - pad_bot
        bar_w = max(2, (w - 8) / self._bins)
        for i, c in enumerate(counts):
            bh = (c / max_count) * chart_h
            bx = 4 + i * bar_w
            by = h - pad_bot - bh
            try:
                _round_rect(self, bx, by, bx + bar_w - 1, h - pad_bot,
                            min(3, bar_w / 2),
                            fill=self._color, outline="")
            except Exception:
                self.create_rectangle(bx, by, bx + bar_w - 1, h - pad_bot,
                                       fill=self._color, outline="")
        # Baseline
        try:
            self.create_line(0, h - pad_bot, w, h - pad_bot,
                              fill=config.DIVIDER)
        except Exception:
            pass


def _self_test() -> int:
    classes = [BarChart, LineChart, DonutChart, Heatmap, Sparkline,
                RadarChart, Histogram]
    print(f"Charts module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
