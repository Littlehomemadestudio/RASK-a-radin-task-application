"""widgets.py — Custom Canvas-drawn Tkinter widgets for Rask.

This module provides a complete set of polished widgets that match the
web/styles.css aesthetic 1:1. Each widget is implemented as a Tkinter
Canvas subclass with custom drawing, hover/active states, and animations
where appropriate.

Widgets provided:
  - GoldButton         — pill-shaped gold / outline / ghost / danger button
  - IconButton         — square icon-only button
  - Chip               — pill-shaped selectable chip
  - Card               — rounded card with optional border
  - Field              — entry with gold underline
  - TextArea           — multi-line entry
  - Switch             — toggle switch
  - Slider             — value slider
  - ProgressBar        — horizontal progress bar
  - FAB                — floating action button (gold circle)
  - BottomNav          — 4-tab navigation bar with SVG icons
  - Toast              — transient notification
  - Modal              — bottom-sheet modal container
  - Spinner            — loading spinner
  - Divider            — horizontal hairline divider
  - Badge              — small pill badge
  - Avatar             — circular avatar with letter
  - SegmentedControl   — multi-segment selector
  - SearchBar          — search input with icon
  - Toolbar            — top toolbar with title and actions
  - EmptyState         — centered empty-state placeholder
  - StatCard           — metric card with label, value, and trend
  - ActivityRow        — single activity list row
  - GoalCard           — goal card with progress ring

All widgets accept a `lang` parameter where relevant to handle RTL/LTR.
"""
from __future__ import annotations
import math
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from . import config
from .i18n import t, to_fa_digits, is_rtl
from . import icons


# =====================================================================
# === FONT RESOLUTION ===
# =====================================================================
_family: Optional[str] = None


def _resolve_family() -> str:
    """Resolve the best available font family for Persian + Latin text."""
    global _family
    if _family is not None:
        return _family
    families = set(tkfont.families())
    candidates = [
        "Vazirmatn", "Vazir",
        "Noto Sans Arabic", "Noto Naskh Arabic", "Noto Sans Persian",
        "DejaVu Sans", "Segoe UI", "Helvetica", "Arial",
    ]
    for cand in candidates:
        if cand in families:
            _family = cand
            return _family
    _family = "TkDefaultFont"
    return _family


def get_font(size: int = 14, weight: str = "normal") -> tkfont.Font:
    """Get a Font object at the given size and weight."""
    return tkfont.Font(family=_resolve_family(), size=size, weight=weight)


# =====================================================================
# === DRAWING PRIMITIVES ===
# =====================================================================
def rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Draw a rounded rectangle on a Tk Canvas."""
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    if radius < 1:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)
    # Use polygon with arc points for a smooth rounded rect
    points = []
    # Top edge (left to right)
    for i in range(20):
        angle = math.pi + (math.pi / 2) * (i / 19)
        points.append(x1 + radius + radius * math.cos(angle))
        points.append(y1 + radius + radius * math.sin(angle))
    # Right edge (top to bottom)
    for i in range(20):
        angle = (3 * math.pi / 2) + (math.pi / 2) * (i / 19)
        points.append(x2 - radius + radius * math.cos(angle))
        points.append(y1 + radius + radius * math.sin(angle))
    # Bottom edge (right to left)
    for i in range(20):
        angle = (2 * math.pi) + (math.pi / 2) * (i / 19)
        points.append(x2 - radius + radius * math.cos(angle))
        points.append(y2 - radius + radius * math.sin(angle))
    # Left edge (bottom to top)
    for i in range(20):
        angle = (5 * math.pi / 2) + (math.pi / 2) * (i / 19)
        points.append(x1 + radius + radius * math.cos(angle))
        points.append(y2 - radius + radius * math.sin(angle))
    return canvas.create_polygon(points, smooth=True, **kwargs)


def gradient_rect(canvas, x1, y1, x2, y2, color1, color2, steps=20):
    """Draw a vertical gradient rectangle (approximate with horizontal bands)."""
    r1, g1, b1 = config.hex_to_rgb(color1)
    r2, g2, b2 = config.hex_to_rgb(color2)
    for i in range(steps):
        t = i / (steps - 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        y_top = y1 + (y2 - y1) * i / steps
        y_bot = y1 + (y2 - y1) * (i + 1) / steps
        canvas.create_rectangle(x1, y_top, x2, y_bot + 1,
                                 fill=config.rgb_to_hex(r, g, b), outline="")


def glow_oval(canvas, cx, cy, r, color, glow_radius=4, alpha_steps=5):
    """Draw a glowing oval (multiple concentric ovals with decreasing alpha).
    
    Tk doesn't support alpha natively, so we simulate by drawing progressively
    smaller ovals with darker colors toward the center.
    """
    r1, g1, b1 = config.hex_to_rgb(color)
    for i in range(alpha_steps, 0, -1):
        t = i / alpha_steps
        # Blend with background
        rb = int(r1 * t + 14 * (1 - t))   # 14 = matte black R
        gb = int(g1 * t + 14 * (1 - t))
        bb = int(b1 * t + 16 * (1 - t))
        canvas.create_oval(
            cx - r - i * glow_radius, cy - r - i * glow_radius,
            cx + r + i * glow_radius, cy + r + i * glow_radius,
            fill=config.rgb_to_hex(rb, gb, bb), outline="",
        )


def shadow_rect(canvas, x1, y1, x2, y2, radius=12, color="#000000",
                shadow_color="#000000", shadow_offset=4, shadow_blur=8):
    """Draw a rectangle with a soft drop shadow."""
    # Shadow (just a darker rounded rect offset)
    sh_x1 = x1 + shadow_offset
    sh_y1 = y1 + shadow_offset
    sh_x2 = x2 + shadow_offset
    sh_y2 = y2 + shadow_offset
    rounded_rect(canvas, sh_x1, sh_y1, sh_x2, sh_y2, radius,
                 fill=shadow_color, outline="")
    # Main rect
    rounded_rect(canvas, x1, y1, x2, y2, radius, fill=color, outline="")


# =====================================================================
# === GOLD BUTTON ===
# =====================================================================
class GoldButton(tk.Canvas):
    """A pill-shaped button with gold / outline / ghost / danger styles.
    
    Matches web/styles.css .btn .btn-gold / .btn-outline / .btn-ghost / .btn-danger.
    """
    def __init__(self, parent, text: str, command: Optional[Callable] = None,
                 kind: str = "gold", size: str = "md",  # md | sm
                 icon: Optional[str] = None, lang: str = "fa",
                 width: Optional[int] = None, height: Optional[int] = None,
                 full_width: bool = False, **kwargs):
        # Determine dimensions
        h = 32 if size == "sm" else 44
        if height:
            h = height
        # Estimate width from text
        font_size = 12 if size == "sm" else 14
        font = get_font(font_size, "bold")
        text_width = font.measure(text)
        icon_pad = 24 if icon else 0
        w = max(80, text_width + 32 + icon_pad)
        if width:
            w = width
        if full_width:
            # Will be set by pack/grid; use a default for now
            w = 400
        super().__init__(parent, width=w, height=h, bg=parent["bg"],
                         highlightthickness=0, bd=0, **kwargs)
        self._parent_bg = parent["bg"]
        self._text = text
        self._command = command
        self._kind = kind
        self._size = size
        self._icon = icon
        self._lang = lang
        self._full_width = full_width
        self._width = w
        self._height = h
        self._font = font
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._animating = False
        self._anim_progress = 1.0
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if event.width != self._width:
            self._width = event.width
            self._draw()

    def _on_enter(self, _e):
        if not self._enabled:
            return
        self._hover = True
        self._draw()
        self.config(cursor="hand2")

    def _on_leave(self, _e):
        self._hover = False
        self._pressed = False
        self._draw()
        self.config(cursor="")

    def _on_press(self, _e):
        if not self._enabled:
            return
        self._pressed = True
        self._draw()

    def _on_release(self, _e):
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and self._command:
            try:
                self._command()
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() if self._full_width else self._width
        if w < 10:
            w = self._width
        h = self._height
        # Determine colors based on kind and state
        if self._kind == "gold":
            bg = config.GOLD
            fg = config.MATTE_BLACK
            if self._pressed:
                bg = config.GOLD_SOFT
            elif self._hover:
                bg = config.GOLD_BRIGHT
            if not self._enabled:
                bg = config.GOLD_DIM
                fg = config.TEXT_FAINT
        elif self._kind == "outline":
            bg = "transparent"
            fg = config.GOLD if self._enabled else config.TEXT_FAINT
            border = config.GOLD if self._enabled else config.TEXT_FAINT
            if self._hover and self._enabled:
                bg = config.CHARCOAL
        elif self._kind == "ghost":
            bg = config.SURFACE if self._enabled else config.MATTE_BLACK
            fg = config.TEXT if self._enabled else config.TEXT_FAINT
            if self._hover and self._enabled:
                bg = config.SURFACE_HI
        elif self._kind == "danger":
            bg = config.DANGER
            fg = "#FFFFFF"
            if self._pressed:
                bg = "#B04A42"
            elif self._hover:
                bg = "#E07570"
            if not self._enabled:
                bg = config.TEXT_FAINT
        else:
            bg = config.SURFACE
            fg = config.TEXT
        # Draw background
        radius = h / 2  # pill shape
        if bg == "transparent":
            if self._kind == "outline":
                # Draw outline only
                self.create_oval(0, 0, h, h, fill="", outline=border, width=2)
                self.create_oval(w - h, 0, w, h, fill="", outline=border, width=2)
                self.create_line(h // 2, 1, w - h // 2, 1, fill=border, width=2)
                self.create_line(h // 2, h - 1, w - h // 2, h - 1, fill=border, width=2)
                self.create_rectangle(h // 2, 1, w - h // 2, h - 1, fill="", outline="")
                # Use a single rounded outline
                self.delete("all")
                rounded_rect(self, 1, 1, w - 1, h - 1, radius, fill="", outline=border, width=2)
        else:
            rounded_rect(self, 0, 0, w, h, radius, fill=bg, outline="")
        # Draw icon if specified
        text_x = w / 2
        if self._icon:
            icon_size = 16 if self._size == "sm" else 20
            icons.draw_icon(self, 12, (h - icon_size) / 2, icon_size,
                             self._icon, color=fg, stroke_width=2)
            text_x = w / 2 + icon_size / 2
        # Draw text
        self.create_text(text_x, h / 2, text=self._text, fill=fg,
                         font=self._font, anchor="center")

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._enabled = state == "normal"
        if "kind" in kwargs:
            self._kind = kwargs.pop("kind")
        super().configure(**kwargs)
        self._draw()

    def invoke(self):
        """Programmatically click the button."""
        if self._command:
            self._command()

    def set_text(self, text: str):
        self._text = text
        self._draw()


# =====================================================================
# === ICON BUTTON ===
# =====================================================================
class IconButton(tk.Canvas):
    """A square icon-only button."""
    def __init__(self, parent, icon: str, command: Optional[Callable] = None,
                 size: int = 40, icon_size: Optional[int] = None,
                 color: str = config.TEXT, hover_color: str = config.GOLD,
                 bg: Optional[str] = None, tooltip: Optional[str] = None,
                 **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=bg or parent["bg"],
                         highlightthickness=0, bd=0, **kwargs)
        self._icon = icon
        self._command = command
        self._size = size
        self._icon_size = icon_size or int(size * 0.6)
        self._color = color
        self._hover_color = hover_color
        self._hover = False
        self._tooltip = tooltip
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _e):
        self._hover = True
        self._draw()
        self.config(cursor="hand2")

    def _on_leave(self, _e):
        self._hover = False
        self._draw()
        self.config(cursor="")

    def _on_press(self, _e):
        pass

    def _on_release(self, _e):
        if self._command:
            try:
                self._command()
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        color = self._hover_color if self._hover else self._color
        if self._hover:
            # Subtle background tint on hover
            rounded_rect(self, 2, 2, self._size - 2, self._size - 2, 8,
                         fill=config.SURFACE, outline="")
        icons.draw_icon(self, (self._size - self._icon_size) / 2,
                         (self._size - self._icon_size) / 2,
                         self._icon_size, self._icon, color=color,
                         stroke_width=2)

    def set_icon(self, icon: str):
        self._icon = icon
        self._draw()


# =====================================================================
# === CHIP (pill-shaped selectable) ===
# =====================================================================
class Chip(tk.Canvas):
    """A pill-shaped selectable chip. Matches .chip / .chip.selected."""
    def __init__(self, parent, text: str, command: Optional[Callable] = None,
                 selected: bool = False, lang: str = "fa",
                 icon: Optional[str] = None, color: Optional[str] = None,
                 **kwargs):
        font = get_font(12, "bold" if selected else "normal")
        text_w = font.measure(text)
        icon_pad = 22 if icon else 0
        w = text_w + 32 + icon_pad
        h = 36
        super().__init__(parent, width=w, height=h, bg=parent["bg"],
                         highlightthickness=0, bd=0, **kwargs)
        self._text = text
        self._command = command
        self._selected = selected
        self._lang = lang
        self._icon = icon
        self._color = color or config.GOLD  # color used when selected
        self._width = w
        self._height = h
        self._font = font
        self._hover = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)

    def _on_enter(self, _e):
        self._hover = True
        self._draw()
        self.config(cursor="hand2")

    def _on_leave(self, _e):
        self._hover = False
        self._draw()
        self.config(cursor="")

    def _on_click(self, _e):
        if self._command:
            try:
                self._command()
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        w = self._width
        h = self._height
        radius = h / 2
        if self._selected:
            bg = self._color
            fg = config.MATTE_BLACK
            border = self._color
            font_weight = "bold"
        else:
            bg = config.CHARCOAL
            fg = config.TEXT
            border = config.SURFACE_HI if not self._hover else config.GOLD_DIM
            font_weight = "normal"
        self._font = get_font(12, font_weight)
        rounded_rect(self, 1, 1, w - 1, h - 1, radius, fill=bg, outline=border, width=1)
        # Icon
        text_x = w / 2
        if self._icon:
            icon_size = 16
            icons.draw_icon(self, 10, (h - icon_size) / 2, icon_size,
                             self._icon, color=fg, stroke_width=2)
            text_x = w / 2 + icon_size / 2
        self.create_text(text_x, h / 2, text=self._text, fill=fg,
                         font=self._font, anchor="center")

    def set_selected(self, selected: bool):
        self._selected = selected
        self._draw()

    def is_selected(self) -> bool:
        return self._selected

    def set_text(self, text: str):
        self._text = text
        # Recompute width
        self._font = get_font(12, "bold" if self._selected else "normal")
        self._width = self._font.measure(text) + 32 + (22 if self._icon else 0)
        self.configure(width=self._width)
        self._draw()


# =====================================================================
# === CARD ===
# =====================================================================
class Card(tk.Frame):
    """A rounded card with optional border. Matches .card."""
    def __init__(self, parent, padding: int = 16, bg: Optional[str] = None,
                 border: bool = True, border_color: Optional[str] = None,
                 radius: int = 12, **kwargs):
        super().__init__(parent, bg=bg or config.CHARCOAL,
                         highlightthickness=1 if border else 0,
                         highlightbackground=border_color or config.DIVIDER,
                         bd=0, **kwargs)
        self._padding = padding
        self._radius = radius

    def add_widget(self, widget, **kwargs):
        """Add a widget inside the card with the card's padding."""
        widget.pack(in_=self, **kwargs)


# =====================================================================
# === FIELD (entry with gold underline) ===
# =====================================================================
class Field(tk.Frame):
    """An entry with a gold underline. Matches .field."""
    def __init__(self, parent, placeholder: str = "", show: str = "",
                 lang: str = "fa", on_change: Optional[Callable] = None,
                 height: int = 50, font_size: int = 15, **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK,
                         highlightthickness=0, bd=0, **kwargs)
        self._placeholder = placeholder
        self._show = show
        self._lang = lang
        self._on_change = on_change
        self._height = height
        self._font = get_font(font_size)
        self._placeholder_font = get_font(font_size)
        self._focused = False
        # Entry
        self._var = tk.StringVar()
        self._entry = tk.Entry(
            self, textvariable=self._var, show=show,
            bg=config.MATTE_BLACK, fg=config.TEXT,
            insertbackground=config.GOLD,
            font=self._font, relief="flat", bd=0,
            highlightthickness=0,
        )
        self._entry.pack(fill="x", padx=12, pady=(height - font_size - 8) // 2)
        # Underline
        self._underline = tk.Frame(self, bg=config.GOLD, height=2)
        self._underline.pack(fill="x", side="bottom")
        # Placeholder
        if placeholder:
            self._set_placeholder()
        # Bindings
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._var.trace_add("write", self._on_var_change)

    def _set_placeholder(self):
        if not self._var.get():
            self._entry.delete(0, tk.END)
            self._entry.insert(0, self._placeholder)
            self._entry.config(fg=config.TEXT_FAINT)

    def _on_focus_in(self, _e):
        self._focused = True
        if self._var.get() == self._placeholder:
            self._entry.delete(0, tk.END)
            self._entry.config(fg=config.TEXT)
        self._underline.config(bg=config.GOLD, height=2)

    def _on_focus_out(self, _e):
        self._focused = False
        if not self._var.get():
            self._entry.insert(0, self._placeholder)
            self._entry.config(fg=config.TEXT_FAINT)
        self._underline.config(bg=config.GOLD_DIM, height=1)

    def _on_var_change(self, *_):
        if self._on_change and self._focused:
            try:
                self._on_change(self._var.get())
            except Exception:
                pass

    def get(self) -> str:
        v = self._var.get()
        if v == self._placeholder:
            return ""
        return v

    def set(self, value: str):
        self._var.set(value)
        if value:
            self._entry.config(fg=config.TEXT)

    def clear(self):
        self._var.set("")
        self._set_placeholder()

    def focus(self):
        self._entry.focus_set()

    def configure(self, **kwargs):
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._entry.config(state=state)
        super().configure(**kwargs)


# =====================================================================
# === TEXT AREA ===
# =====================================================================
class TextArea(tk.Frame):
    """A multi-line text area with gold underline."""
    def __init__(self, parent, placeholder: str = "", height: int = 80,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK,
                         highlightthickness=0, bd=0, **kwargs)
        self._placeholder = placeholder
        self._lang = lang
        self._text = tk.Text(
            self, bg=config.MATTE_BLACK, fg=config.TEXT,
            insertbackground=config.GOLD, font=get_font(13),
            relief="flat", bd=0, height=height // 18,
            wrap="word", highlightthickness=0,
        )
        self._text.pack(fill="both", expand=True, padx=12, pady=8)
        # Underline
        self._underline = tk.Frame(self, bg=config.GOLD_DIM, height=1)
        self._underline.pack(fill="x", side="bottom")
        if placeholder:
            self._text.insert("1.0", placeholder)
            self._text.config(fg=config.TEXT_FAINT)
        self._text.bind("<FocusIn>", self._on_focus_in)
        self._text.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, _e):
        if self._text.get("1.0", "end-1c") == self._placeholder:
            self._text.delete("1.0", tk.END)
            self._text.config(fg=config.TEXT)
        self._underline.config(bg=config.GOLD, height=2)

    def _on_focus_out(self, _e):
        if not self._text.get("1.0", "end-1c"):
            self._text.insert("1.0", self._placeholder)
            self._text.config(fg=config.TEXT_FAINT)
        self._underline.config(bg=config.GOLD_DIM, height=1)

    def get(self) -> str:
        v = self._text.get("1.0", "end-1c")
        if v == self._placeholder:
            return ""
        return v

    def set(self, value: str):
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", value)
        self._text.config(fg=config.TEXT)

    def clear(self):
        self._text.delete("1.0", tk.END)
        if self._placeholder:
            self._text.insert("1.0", self._placeholder)
            self._text.config(fg=config.TEXT_FAINT)


# =====================================================================
# === SWITCH (toggle) ===
# =====================================================================
class Switch(tk.Canvas):
    """A toggle switch (iOS-style)."""
    def __init__(self, parent, value: bool = False,
                 command: Optional[Callable[[bool], None]] = None,
                 width: int = 48, height: int = 28, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._value = value
        self._command = command
        self._width = width
        self._height = height
        self._animating = False
        self._anim_progress = 1.0 if value else 0.0
        self._draw()
        self.bind("<ButtonPress-1>", self._on_click)

    def _on_click(self, _e):
        self._value = not self._value
        self._animate_to(1.0 if self._value else 0.0)
        if self._command:
            try:
                self._command(self._value)
            except Exception:
                pass

    def _animate_to(self, target: float):
        """Animate the knob from current position to target (0 or 1)."""
        if self._animating:
            return
        self._animating = True
        start = self._anim_progress
        steps = 12
        for i in range(steps + 1):
            t = i / steps
            eased = 1 - (1 - t) ** 3
            self._anim_progress = start + (target - start) * eased
            self.after(i * 16, lambda p=self._anim_progress: self._draw_at(p))
        self.after(steps * 16 + 16, self._after_anim)
        self._anim_progress = target

    def _after_anim(self):
        self._animating = False
        self._draw()

    def _draw_at(self, progress: float):
        self.delete("all")
        self._draw_with_progress(progress)

    def _draw(self):
        self._draw_with_progress(self._anim_progress)

    def _draw_with_progress(self, progress: float):
        w = self._width
        h = self._height
        radius = h / 2
        # Track
        track_color = config.blend(config.SURFACE_HI, config.GOLD, progress)
        rounded_rect(self, 0, 0, w, h, radius, fill=track_color, outline="")
        # Knob
        knob_r = h / 2 - 3
        knob_x = 3 + knob_r + progress * (w - 2 * knob_r - 6)
        self.create_oval(
            knob_x - knob_r, h / 2 - knob_r,
            knob_x + knob_r, h / 2 + knob_r,
            fill="#FFFFFF", outline="",
        )

    def get(self) -> bool:
        return self._value

    def set(self, value: bool):
        self._value = value
        self._anim_progress = 1.0 if value else 0.0
        self._draw()

    def toggle(self):
        self._on_click(None)


# =====================================================================
# === SLIDER ===
# =====================================================================
class Slider(tk.Canvas):
    """A horizontal value slider."""
    def __init__(self, parent, min_val: float = 0, max_val: float = 100,
                 value: float = 50, command: Optional[Callable[[float], None]] = None,
                 width: int = 200, height: int = 36, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._min = min_val
        self._max = max_val
        self._value = value
        self._command = command
        self._width = width
        self._height = height
        self._dragging = False
        self._draw()
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<B1-Motion>", self._on_motion)

    def _normalized(self) -> float:
        if self._max == self._min:
            return 0.5
        return (self._value - self._min) / (self._max - self._min)

    def _on_press(self, e):
        self._dragging = True
        self._update_from_x(e.x)

    def _on_release(self, _e):
        self._dragging = False

    def _on_motion(self, e):
        if self._dragging:
            self._update_from_x(e.x)

    def _update_from_x(self, x: int):
        norm = max(0.0, min(1.0, x / self._width))
        self._value = self._min + norm * (self._max - self._min)
        self._draw()
        if self._command:
            try:
                self._command(self._value)
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        w = self._width
        h = self._height
        track_y = h / 2
        # Track (full)
        rounded_rect(self, 0, track_y - 2, w, track_y + 2, 2,
                     fill=config.SURFACE_HI, outline="")
        # Filled portion
        norm = self._normalized()
        filled_w = w * norm
        if filled_w > 0:
            rounded_rect(self, 0, track_y - 2, filled_w, track_y + 2, 2,
                         fill=config.GOLD, outline="")
        # Knob
        knob_r = 9
        knob_x = filled_w
        self.create_oval(
            knob_x - knob_r, track_y - knob_r,
            knob_x + knob_r, track_y + knob_r,
            fill="#FFFFFF", outline=config.GOLD, width=2,
        )

    def get(self) -> float:
        return self._value

    def set(self, value: float):
        self._value = max(self._min, min(self._max, value))
        self._draw()


# =====================================================================
# === PROGRESS BAR ===
# =====================================================================
class ProgressBar(tk.Canvas):
    """A horizontal progress bar."""
    def __init__(self, parent, progress: float = 0, width: int = 200,
                 height: int = 8, color: str = config.GOLD,
                 track_color: str = config.SURFACE_HI, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._progress = progress
        self._width = width
        self._height = height
        self._color = color
        self._track_color = track_color
        self._draw()
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if event.width != self._width:
            self._width = event.width
            self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 10 else self._width
        h = self._height
        # Track
        rounded_rect(self, 0, 0, w, h, h / 2,
                     fill=self._track_color, outline="")
        # Fill
        fill_w = w * max(0, min(1, self._progress))
        if fill_w > 0:
            rounded_rect(self, 0, 0, fill_w, h, h / 2,
                         fill=self._color, outline="")

    def set_progress(self, progress: float):
        self._progress = progress
        self._draw()


# =====================================================================
# === FAB (Floating Action Button) ===
# =====================================================================
class FAB(tk.Canvas):
    """A floating action button. Matches .fab (gold circle with +)."""
    def __init__(self, parent, command: Optional[Callable] = None,
                 icon: str = "+", size: int = 56, lang: str = "fa",
                 **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._command = command
        self._icon = icon
        self._size = size
        self._lang = lang
        self._hover = False
        self._pressed = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _e):
        self._hover = True
        self._draw()
        self.config(cursor="hand2")

    def _on_leave(self, _e):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _e):
        self._pressed = True
        self._draw()

    def _on_release(self, _e):
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and self._command:
            try:
                self._command()
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        s = self._size
        # Glow (subtle)
        if self._hover:
            glow_oval(self, s / 2, s / 2, s / 2 - 4, config.GOLD,
                      glow_radius=2, alpha_steps=3)
        # Main circle
        color = config.GOLD_SOFT if self._pressed else (
            config.GOLD_BRIGHT if self._hover else config.GOLD
        )
        self.create_oval(0, 0, s, s, fill=color, outline="")
        # Icon (just a + by default)
        if self._icon == "+":
            # Draw a + with two lines
            line_color = config.MATTE_BLACK
            self.create_line(s / 2, s * 0.3, s / 2, s * 0.7,
                             fill=line_color, width=3, capstyle="round")
            self.create_line(s * 0.3, s / 2, s * 0.7, s / 2,
                             fill=line_color, width=3, capstyle="round")
        else:
            # Draw a custom icon
            icons.draw_icon(self, s * 0.25, s * 0.25, s * 0.5,
                             self._icon, color=config.MATTE_BLACK, stroke_width=2.5)


# =====================================================================
# === BOTTOM NAV ===
# =====================================================================
class BottomNav(tk.Frame):
    """The 4-tab bottom navigation bar. Matches .bottom-nav."""
    def __init__(self, parent, on_tab: Callable[[str], None],
                 tabs: Optional[list[tuple[str, str, str]]] = None,
                 lang: str = "fa", active_tab: str = "home", **kwargs):
        super().__init__(parent, bg=config.CHARCOAL, height=64,
                         highlightbackground=config.DIVIDER,
                         highlightthickness=1, bd=0, **kwargs)
        self._on_tab = on_tab
        self._lang = lang
        self._active = active_tab
        # Default tabs: (id, icon_name, i18n_key)
        self._tabs = tabs or [
            ("home", "home", "home"),
            ("goals", "goals", "goals"),
            ("stats", "stats", "stats"),
            ("settings", "settings", "settings"),
        ]
        self._buttons: dict[str, tk.Canvas] = {}
        for tab_id, icon_name, i18n_key in self._tabs:
            btn = tk.Canvas(self, width=120, height=64,
                             bg=config.CHARCOAL, highlightthickness=0, bd=0)
            btn.pack(side="left", fill="both", expand=True)
            btn._tab_id = tab_id
            btn._icon_name = icon_name
            btn._i18n_key = i18n_key
            btn._hover = False
            self._buttons[tab_id] = btn
            btn.bind("<Enter>", lambda e, b=btn: self._on_enter(b))
            btn.bind("<Leave>", lambda e, b=btn: self._on_leave(b))
            btn.bind("<ButtonPress-1>", lambda e, b=btn: self._on_click(b))
            btn.bind("<Configure>", lambda e, b=btn: self._draw_button(b))
        self._draw_all()

    def _on_enter(self, btn):
        btn._hover = True
        self._draw_button(btn)
        btn.config(cursor="hand2")

    def _on_leave(self, btn):
        btn._hover = False
        self._draw_button(btn)
        btn.config(cursor="")

    def _on_click(self, btn):
        tab_id = btn._tab_id
        self.set_active(tab_id)
        if self._on_tab:
            try:
                self._on_tab(tab_id)
            except Exception:
                pass

    def _draw_all(self):
        for btn in self._buttons.values():
            self._draw_button(btn)

    def _draw_button(self, btn):
        btn.delete("all")
        w = btn.winfo_width() if btn.winfo_width() > 10 else 120
        h = 64
        is_active = btn._tab_id == self._active
        color = config.GOLD if is_active else (
            config.TEXT_DIM if btn._hover else config.TEXT_FAINT
        )
        # Icon (24x24)
        icon_size = 22
        icons.draw_icon(btn, (w - icon_size) / 2, 10, icon_size,
                         btn._icon_name, color=color, stroke_width=2)
        # Label
        label = t(btn._i18n_key, self._lang)
        btn.create_text(w / 2, 48, text=label, fill=color,
                         font=get_font(10), anchor="center")

    def set_active(self, tab_id: str):
        self._active = tab_id
        self._draw_all()

    def set_lang(self, lang: str):
        self._lang = lang
        self._draw_all()


# =====================================================================
# === TOAST ===
# =====================================================================
class Toast(tk.Toplevel):
    """A transient notification toast. Matches .toast."""
    def __init__(self, root, text: str, duration_ms: int = 2600,
                 lang: str = "fa", kind: str = "info"):
        super().__init__(root)
        self.overrideredirect(True)
        self.configure(bg=config.SURFACE_HI)
        self._text = text
        self._lang = lang
        self._kind = kind
        self._root = root
        # Label
        color = {
            "info": config.TEXT,
            "success": config.SUCCESS,
            "warning": config.WARNING,
            "danger": config.DANGER,
        }.get(kind, config.TEXT)
        label = tk.Label(self, text=text, bg=config.SURFACE_HI, fg=color,
                          font=get_font(13), padx=20, pady=10)
        label.pack()
        # Position near bottom-center of parent
        root.update_idletasks()
        w = label.winfo_reqwidth() + 40
        h = label.winfo_reqheight() + 20
        x = root.winfo_x() + (root.winfo_width() - w) // 2
        y = root.winfo_y() + root.winfo_height() - h - 100
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.attributes("-topmost", True)
        # Auto-dismiss
        self.after(duration_ms, self.destroy)


# =====================================================================
# === MODAL (bottom sheet) ===
# =====================================================================
class Modal(tk.Toplevel):
    """A bottom-sheet modal. Matches .modal-backdrop / .modal."""
    def __init__(self, root, title: str, lang: str = "fa",
                 on_close: Optional[Callable] = None, height: Optional[int] = None,
                 **kwargs):
        super().__init__(root, **kwargs)
        self._root = root
        self._title = title
        self._lang = lang
        self._on_close = on_close
        self.configure(bg=config.MATTE_BLACK)
        # Make it modal
        self.transient(root)
        self.grab_set()
        # Set geometry — bottom sheet, 540 wide, up to 90% of parent height
        root.update_idletasks()
        w = min(540, root.winfo_width())
        h = height or int(root.winfo_height() * 0.9)
        x = root.winfo_x() + (root.winfo_width() - w) // 2
        y = root.winfo_y() + root.winfo_height() - h
        self.geometry(f"{w}x{h}+{x}+{y}")
        # Decorations
        self.overrideredirect(True)
        # Build content
        self._build()
        # Close on Escape
        self.bind("<Escape>", lambda e: self.close())

    def _build(self):
        # Title bar
        header = tk.Frame(self, bg=config.MATTE_BLACK, height=60)
        header.pack(fill="x", padx=24, pady=(24, 0))
        tk.Label(header, text=self._title, bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(20, "bold"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        close_btn = IconButton(header, "x", command=self.close,
                                size=32, icon_size=16,
                                color=config.TEXT_DIM, hover_color=config.DANGER)
        close_btn.pack(side="right")
        # Divider
        tk.Frame(self, bg=config.DIVIDER, height=1).pack(fill="x", padx=24, pady=(8, 0))
        # Content area (scrollable)
        content_wrap = tk.Frame(self, bg=config.MATTE_BLACK)
        content_wrap.pack(fill="both", expand=True, padx=24, pady=16)
        self.content = tk.Frame(content_wrap, bg=config.MATTE_BLACK)
        self.content.pack(fill="both", expand=True)

    def close(self):
        if self._on_close:
            try:
                self._on_close()
            except Exception:
                pass
        self.grab_release()
        self.destroy()


# =====================================================================
# === SPINNER (loading) ===
# =====================================================================
class Spinner(tk.Canvas):
    """A rotating loading spinner."""
    def __init__(self, parent, size: int = 32, color: str = config.GOLD,
                 **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._size = size
        self._color = color
        self._angle = 0
        self._running = False
        self._after_id = None
        self._draw()

    def start(self):
        if self._running:
            return
        self._running = True
        self._animate()

    def stop(self):
        self._running = False
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _animate(self):
        if not self._running:
            return
        self._angle = (self._angle + 30) % 360
        self._draw()
        self._after_id = self.after(50, self._animate)

    def _draw(self):
        self.delete("all")
        s = self._size
        cx, cy = s / 2, s / 2
        r = s / 2 - 3
        # Draw 12 arc segments, only some visible (rotating)
        for i in range(12):
            angle = self._angle + i * 30
            # Opacity decreases as we go around
            t = i / 11
            color = config.blend(config.SURFACE_HI, self._color, t)
            x1 = cx + r * math.cos(math.radians(angle - 15))
            y1 = cy + r * math.sin(math.radians(angle - 15))
            x2 = cx + r * math.cos(math.radians(angle + 15))
            y2 = cy + r * math.sin(math.radians(angle + 15))
            self.create_line(cx, cy, x2, y2, fill=color, width=3, capstyle="round")


# =====================================================================
# === DIVIDER ===
# =====================================================================
class Divider(tk.Frame):
    """A horizontal hairline divider. Matches .divider."""
    def __init__(self, parent, color: str = config.DIVIDER,
                 height: int = 1, **kwargs):
        super().__init__(parent, bg=color, height=height, **kwargs)


# =====================================================================
# === BADGE (small pill) ===
# =====================================================================
class Badge(tk.Canvas):
    """A small pill badge (e.g., for streak counts)."""
    def __init__(self, parent, text: str, color: str = config.GOLD,
                 bg: Optional[str] = None, lang: str = "fa", **kwargs):
        font = get_font(11, "bold")
        w = font.measure(text) + 16
        h = 22
        super().__init__(parent, width=w, height=h, bg=parent["bg"],
                         highlightthickness=0, bd=0, **kwargs)
        self._text = text
        self._color = color
        self._bg = bg or config.blend(color, config.MATTE_BLACK, 0.7)
        self._width = w
        self._height = h
        self._font = font
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self._width
        h = self._height
        radius = h / 2
        rounded_rect(self, 0, 0, w, h, radius, fill=self._bg, outline="")
        self.create_text(w / 2, h / 2, text=self._text,
                         fill=self._color, font=self._font, anchor="center")


# =====================================================================
# === AVATAR (circular letter) ===
# =====================================================================
class Avatar(tk.Canvas):
    """A circular avatar with a letter (used in splash, lock, etc.)."""
    def __init__(self, parent, letter: str = "R", size: int = 120,
                 color: str = config.GOLD, bg: Optional[str] = None,
                 animated: bool = False, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=bg or parent["bg"], highlightthickness=0, bd=0, **kwargs)
        self._letter = letter
        self._size = size
        self._color = color
        self._animated = animated
        self._anim_phase = 0
        self._after_id = None
        self._draw()
        if animated:
            self._animate()

    def _animate(self):
        self._anim_phase = (self._anim_phase + 0.05) % (2 * math.pi)
        self._draw()
        self._after_id = self.after(50, self._animate)

    def _draw(self):
        self.delete("all")
        s = self._size
        cx, cy = s / 2, s / 2
        r = s / 2 - 4
        # Outer ring (pulse if animated)
        pulse = 1.0
        if self._animated:
            pulse = 1.0 + 0.04 * math.sin(self._anim_phase)
        # Glow
        glow_oval(self, cx, cy, r, self._color, glow_radius=4, alpha_steps=4)
        # Outer ring
        self.create_oval(cx - r * pulse, cy - r * pulse,
                          cx + r * pulse, cy + r * pulse,
                          outline=self._color, width=4)
        # Letter
        font_size = int(s * 0.5)
        self.create_text(cx, cy, text=self._letter,
                         fill=self._color, font=get_font(font_size, "bold"))

    def stop_animation(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


# =====================================================================
# === SEGMENTED CONTROL ===
# =====================================================================
class SegmentedControl(tk.Frame):
    """A segmented control (like iOS). Used for period pickers, etc."""
    def __init__(self, parent, segments: list[str], command: Optional[Callable[[int], None]] = None,
                 selected: int = 0, lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.SURFACE, **kwargs)
        self._segments = segments
        self._command = command
        self._selected = selected
        self._lang = lang
        self._buttons: list[tk.Canvas] = []
        for i, seg in enumerate(segments):
            btn = tk.Canvas(self, height=36, bg=config.SURFACE,
                             highlightthickness=0, bd=0)
            btn.pack(side="left", fill="both", expand=True, padx=2, pady=2)
            btn._text = seg
            btn._index = i
            btn._hover = False
            self._buttons.append(btn)
            btn.bind("<Enter>", lambda e, b=btn: self._on_enter(b))
            btn.bind("<Leave>", lambda e, b=btn: self._on_leave(b))
            btn.bind("<ButtonPress-1>", lambda e, b=btn: self._on_click(b))
            btn.bind("<Configure>", lambda e, b=btn: self._draw_button(b))
        self._draw_all()

    def _on_enter(self, btn):
        btn._hover = True
        self._draw_button(btn)
        btn.config(cursor="hand2")

    def _on_leave(self, btn):
        btn._hover = False
        self._draw_button(btn)

    def _on_click(self, btn):
        self._selected = btn._index
        self._draw_all()
        if self._command:
            try:
                self._command(self._selected)
            except Exception:
                pass

    def _draw_all(self):
        for btn in self._buttons:
            self._draw_button(btn)

    def _draw_button(self, btn):
        btn.delete("all")
        w = btn.winfo_width() if btn.winfo_width() > 10 else 80
        h = 36
        is_selected = btn._index == self._selected
        bg = config.GOLD if is_selected else config.SURFACE
        fg = config.MATTE_BLACK if is_selected else (
            config.GOLD if btn._hover else config.TEXT
        )
        radius = h / 2
        rounded_rect(btn, 0, 0, w, h, radius, fill=bg, outline="")
        btn.create_text(w / 2, h / 2, text=btn._text, fill=fg,
                         font=get_font(12, "bold" if is_selected else "normal"),
                         anchor="center")

    def get_selected(self) -> int:
        return self._selected

    def set_selected(self, idx: int):
        self._selected = idx
        self._draw_all()


# =====================================================================
# === SEARCH BAR ===
# =====================================================================
class SearchBar(tk.Frame):
    """A search input with a search icon. Matches .search-bar style."""
    def __init__(self, parent, placeholder: str = "Search...", lang: str = "fa",
                 on_search: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(parent, bg=config.SURFACE, **kwargs)
        self._lang = lang
        self._on_search = on_search
        # Icon
        icon_canvas = tk.Canvas(self, width=36, height=40, bg=config.SURFACE,
                                 highlightthickness=0, bd=0)
        icon_canvas.pack(side="left", padx=(8, 0))
        icons.draw_icon(icon_canvas, 6, 8, 20, "search",
                         color=config.TEXT_DIM, stroke_width=2)
        # Entry
        self._var = tk.StringVar()
        self._entry = tk.Entry(
            self, textvariable=self._var, bg=config.SURFACE, fg=config.TEXT,
            insertbackground=config.GOLD, font=get_font(14),
            relief="flat", bd=0, highlightthickness=0,
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)
        if placeholder:
            self._entry.insert(0, placeholder)
            self._entry.config(fg=config.TEXT_FAINT)
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._var.trace_add("write", self._on_change)

    def _on_focus_in(self, _e):
        if self._var.get() == self._placeholder:
            self._entry.delete(0, tk.END)
            self._entry.config(fg=config.TEXT)

    def _on_focus_out(self, _e):
        if not self._var.get():
            self._entry.insert(0, self._placeholder)
            self._entry.config(fg=config.TEXT_FAINT)

    def _on_change(self, *_):
        if self._on_search:
            try:
                self._on_search(self._var.get())
            except Exception:
                pass

    def get(self) -> str:
        return self._var.get()


# =====================================================================
# === TOOLBAR (top bar) ===
# =====================================================================
class Toolbar(tk.Frame):
    """A top toolbar with title and optional action buttons."""
    def __init__(self, parent, title: str, lang: str = "fa",
                 on_back: Optional[Callable] = None,
                 actions: Optional[list[tuple[str, Callable]]] = None, **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, height=56, **kwargs)
        self._title = title
        self._lang = lang
        if on_back:
            back = IconButton(self, "arrow-left", command=on_back, size=40,
                               color=config.GOLD, hover_color=config.GOLD_BRIGHT)
            back.pack(side="left", padx=(8, 0))
        tk.Label(self, text=title, bg=config.MATTE_BLACK, fg=config.TEXT,
                 font=get_font(18, "bold"), anchor="w").pack(
            side="left", fill="x", expand=True, padx=12)
        if actions:
            for icon_name, cmd in actions:
                btn = IconButton(self, icon_name, command=cmd, size=40,
                                  color=config.TEXT_DIM, hover_color=config.GOLD)
                btn.pack(side="right", padx=(0, 8))


# =====================================================================
# === EMPTY STATE ===
# =====================================================================
class EmptyState(tk.Frame):
    """A centered empty-state placeholder."""
    def __init__(self, parent, icon: str = "info", title: str = "",
                 subtitle: str = "", lang: str = "fa", **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        self._lang = lang
        # Icon
        icon_canvas = tk.Canvas(self, width=80, height=80, bg=parent["bg"],
                                 highlightthickness=0, bd=0)
        icon_canvas.pack(pady=(24, 8))
        icons.draw_icon(icon_canvas, 16, 16, 48, icon,
                         color=config.TEXT_FAINT, stroke_width=1.5)
        # Title
        if title:
            tk.Label(self, text=title, bg=parent["bg"], fg=config.TEXT_DIM,
                     font=get_font(15, "bold")).pack(pady=(0, 4))
        # Subtitle
        if subtitle:
            tk.Label(self, text=subtitle, bg=parent["bg"], fg=config.TEXT_FAINT,
                     font=get_font(12), wraplength=300).pack(pady=(0, 24))


# =====================================================================
# === STAT CARD ===
# =====================================================================
class StatCard(tk.Frame):
    """A metric card with a label, large value, and optional trend."""
    def __init__(self, parent, label: str, value: str,
                 trend: Optional[str] = None, trend_kind: str = "info",
                 icon: Optional[str] = None, lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.CHARCOAL, **kwargs)
        self._lang = lang
        # Highlight border
        self.config(highlightbackground=config.DIVIDER, highlightthickness=1)
        # Top row: label + icon
        top = tk.Frame(self, bg=config.CHARCOAL)
        top.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(top, text=label, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                 font=get_font(11)).pack(side="left")
        if icon:
            icon_c = tk.Canvas(top, width=20, height=20, bg=config.CHARCOAL,
                                highlightthickness=0, bd=0)
            icon_c.pack(side="right")
            icons.draw_icon(icon_c, 0, 0, 20, icon,
                             color=config.GOLD, stroke_width=2)
        # Value
        tk.Label(self, text=value, bg=config.CHARCOAL, fg=config.GOLD,
                 font=get_font(26, "bold"), anchor="w").pack(fill="x", padx=16, pady=(4, 12))
        # Trend
        if trend:
            color = {
                "up": config.SUCCESS,
                "down": config.DANGER,
                "info": config.TEXT_DIM,
            }.get(trend_kind, config.TEXT_DIM)
            tk.Label(self, text=trend, bg=config.CHARCOAL, fg=color,
                     font=get_font(11, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(0, 12))


# =====================================================================
# === ACTIVITY ROW ===
# =====================================================================
class ActivityRow(tk.Frame):
    """A single activity row. Matches .activity-row."""
    def __init__(self, parent, activity: dict, category: Optional[dict] = None,
                 lang: str = "fa", on_click: Optional[Callable] = None,
                 **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        self._activity = activity
        self._category = category
        self._lang = lang
        self._on_click = on_click
        # Top row: title + category badge
        top = tk.Frame(self, bg=parent["bg"])
        top.pack(fill="x", padx=16, pady=(10, 0))
        title = (activity.get("title") or t("untitled", lang))[:60]
        tk.Label(top, text=title, bg=parent["bg"], fg=config.TEXT,
                 font=get_font(14, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        cat_name = ""
        cat_color = config.TEXT_DIM
        if category:
            cat_name = category["name_fa"] if lang == "fa" else category["name_en"]
            cat_color = category["color"]
        if cat_name:
            tk.Label(top, text=cat_name, bg=parent["bg"], fg=cat_color,
                     font=get_font(11, "bold"), anchor="e").pack(side="right")
        # Bottom row: duration + relative time
        bot = tk.Frame(self, bg=parent["bg"])
        bot.pack(fill="x", padx=16, pady=(4, 10))
        from .date_utils import fmt_human, fmt_relative
        dur = fmt_human(int(activity.get("duration_sec", 0) or 0), lang)
        tk.Label(bot, text=dur, bg=parent["bg"], fg=config.GOLD,
                 font=get_font(12, "bold"), anchor="w").pack(side="left")
        when = fmt_relative(activity.get("date_iso", ""), lang)
        tk.Label(bot, text=when, bg=parent["bg"], fg=config.TEXT_FAINT,
                 font=get_font(11), anchor="e").pack(side="right")
        # Divider
        tk.Frame(self, bg=config.DIVIDER, height=1).pack(fill="x")
        # Click handler
        if on_click:
            for widget in [self, top, bot]:
                widget.bind("<Button-1>", lambda e: self._handle_click())
            for child in top.winfo_children() + bot.winfo_children():
                child.bind("<Button-1>", lambda e: self._handle_click())

    def _handle_click(self):
        if self._on_click:
            try:
                self._on_click(self._activity)
            except Exception:
                pass


# =====================================================================
# === GOAL CARD ===
# =====================================================================
class GoalCard(tk.Frame):
    """A goal card with a progress ring. Matches .goal-card."""
    def __init__(self, parent, goal: dict, progress: float, current_sec: int,
                 target_sec: int, streak: Optional[dict] = None,
                 category: Optional[dict] = None, lang: str = "fa",
                 on_delete: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=config.CHARCOAL,
                         highlightbackground=config.DIVIDER,
                         highlightthickness=1, **kwargs)
        self._goal = goal
        self._progress = max(0.0, min(1.0, progress))
        self._current_sec = current_sec
        self._target_sec = target_sec
        self._streak = streak
        self._category = category
        self._lang = lang
        self._on_delete = on_delete
        # Layout: ring | info | delete
        ring_canvas = tk.Canvas(self, width=80, height=80, bg=config.CHARCOAL,
                                 highlightthickness=0, bd=0)
        ring_canvas.pack(side="left", padx=(16, 8), pady=16)
        from .charts import progress_ring
        # Determine color (gold for in-progress, success for achieved)
        color = config.SUCCESS if progress >= 1.0 else config.GOLD
        label = f"{int(progress * 100)}%"
        if lang == "fa":
            from .i18n import to_fa_digits
            label = to_fa_digits(label)
        progress_ring(ring_canvas, 40, 40, 80, progress, color,
                       config.SURFACE_HI, label, config.TEXT, line_width=6,
                       font_size=14)
        # Info
        info = tk.Frame(self, bg=config.CHARCOAL)
        info.pack(side="left", fill="x", expand=True, pady=16)
        from .i18n import t, to_fa_digits
        from .date_utils import fmt_human
        period_label = t(goal.get("period", "daily"), lang)
        if category:
            cat_name = category["name_fa"] if lang == "fa" else category["name_en"]
            period_label = f"{period_label} — {cat_name}"
        else:
            period_label = f"{period_label} — {t('all', lang)}"
        tk.Label(info, text=period_label, bg=config.CHARCOAL, fg=config.TEXT,
                 font=get_font(14, "bold"), anchor="w").pack(anchor="w")
        tk.Label(info, text=f"{fmt_human(current_sec, lang)} / {fmt_human(target_sec, lang)}",
                 bg=config.CHARCOAL, fg=config.GOLD,
                 font=get_font(12, "bold"), anchor="w").pack(anchor="w")
        if streak and streak.get("current", 0) > 0:
            cur = streak["current"]
            longest = streak.get("longest", 0)
            cur_str = to_fa_digits(cur) if lang == "fa" else str(cur)
            longest_str = to_fa_digits(longest) if lang == "fa" else str(longest)
            streak_text = f"{t('streak', lang)}: {cur_str} {t('days', lang)} ({t('best', lang)}: {longest_str})"
            tk.Label(info, text=streak_text, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(11), anchor="w").pack(anchor="w")
        # Delete button
        if on_delete:
            del_btn = IconButton(self, "trash", command=lambda: on_delete(goal),
                                  size=32, icon_size=16,
                                  color=config.TEXT_DIM, hover_color=config.DANGER)
            del_btn.pack(side="right", padx=(0, 12))


# =====================================================================
# === SCROLLABLE FRAME ===
# =====================================================================
class ScrollableFrame(tk.Frame):
    """A frame with vertical scrolling support."""
    def __init__(self, parent, bg: Optional[str] = None, **kwargs):
        super().__init__(parent, bg=bg or config.MATTE_BLACK, **kwargs)
        self._canvas = tk.Canvas(self, bg=bg or config.MATTE_BLACK,
                                  highlightthickness=0, bd=0)
        self._scrollbar = tk.Scrollbar(self, orient="vertical",
                                        command=self._canvas.yview,
                                        bg=config.CHARCOAL,
                                        troughcolor=config.MATTE_BLACK)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self._canvas, bg=bg or config.MATTE_BLACK)
        self._window_id = self._canvas.create_window((0, 0), window=self.inner,
                                                      anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Mouse-wheel scrolling
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", lambda e: self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind("<Button-5>", lambda e: self._canvas.yview_scroll(1, "units"))

    def _on_inner_configure(self, _e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._window_id, width=e.width)

    def _on_wheel(self, event):
        try:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def clear(self):
        """Remove all children from the inner frame."""
        for child in self.inner.winfo_children():
            child.destroy()


# =====================================================================
# === LABEL HELPERS ===
# =====================================================================
def section_header(parent, text: str, lang: str = "fa") -> tk.Label:
    """Return a section-header label. Matches .section-header."""
    return tk.Label(parent, text=text, bg=parent["bg"], fg=config.TEXT,
                     font=get_font(14, "bold"), anchor="w")


def greeting_label(parent, text: str) -> tk.Label:
    """Return a greeting label. Matches .greeting."""
    return tk.Label(parent, text=text, bg=parent["bg"], fg=config.TEXT,
                     font=get_font(22, "bold"), anchor="w")


def date_label(parent, text: str) -> tk.Label:
    """Return a date label. Matches .date-label."""
    return tk.Label(parent, text=text, bg=parent["bg"], fg=config.TEXT_DIM,
                     font=get_font(12), anchor="w")


def body_label(parent, text: str, color: str = config.TEXT,
               size: int = 13, weight: str = "normal") -> tk.Label:
    """Return a body text label."""
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                     font=get_font(size, weight), anchor="w", wraplength=400)


def stat_label(parent, text: str, color: str = config.GOLD,
               size: int = 26) -> tk.Label:
    """Return a large stat label. Matches .stat-total."""
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                     font=get_font(size, "bold"), anchor="w")
