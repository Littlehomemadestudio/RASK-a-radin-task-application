"""
components.py — Reusable UI primitives in the gold-on-dark theme.

    - GoldButton
    - OutlinedButton
    - GoldCard
    - FabButton (floating action button)
    - GoldDivider
    - SectionHeader
    - Chip
    - TextField (gold underlined)
    - EmptyState
"""
from __future__ import annotations

from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.properties import (
    StringProperty, NumericProperty, ListProperty,
    ObjectProperty, BooleanProperty, ColorProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex

from rask import config as cfg


def _hex(h: str, alpha: float = 1.0):
    c = get_color_from_hex(h)
    return (c[0], c[1], c[2], alpha)


# === Button ===

class GoldButton(Button):
    """Filled gold button."""
    bg_color = ColorProperty("#D4AF37")
    text_color = ColorProperty("#0E0E10")
    radius = NumericProperty(cfg.RADIUS_PILL)

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("color", (0, 0, 0, 1))
        kw.setdefault("bold", True)
        kw.setdefault("font_size", cfg.FONT_SIZES["body"])
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, bg_color=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*_hex(self.bg_color))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])


class OutlinedButton(Button):
    """Outlined (ghost) button — transparent with gold border."""
    border_color = ColorProperty("#D4AF37")
    text_color = ColorProperty("#D4AF37")

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, border_color=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*_hex(self.border_color))
            Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                    cfg.RADIUS_PILL), width=1.4)


# === Card ===

class GoldCard(BoxLayout):
    """Dark surface card with subtle border + rounded corners."""
    bg_color = ColorProperty("#1A1A1D")
    border_color = ColorProperty("#2C2C30")
    radius = NumericProperty(cfg.RADIUS_MD)
    padding_val = NumericProperty(cfg.SPACE["lg"])

    def __init__(self, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("padding", [cfg.SPACE["lg"]] * 2)
        kw.setdefault("spacing", cfg.SPACE["sm"])
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*_hex(self.bg_color))
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self.radius])
            Color(*_hex(self.border_color, 0.7))
            Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                    self.radius), width=1.0)


# === FAB ===

class FabButton(ButtonBehavior, FloatLayout):
    """Floating Action Button — gold circle with plus icon."""
    icon_color = ColorProperty("#0E0E10")
    size_val = NumericProperty(56)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = (self.size_val, self.size_val)
        self.bind(pos=self._redraw, size=self._redraw, size_val=self._set_size)
        self._redraw()

    def _set_size(self, *_):
        self.size = (self.size_val, self.size_val)

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*_hex("#D4AF37"))
            Ellipse(pos=self.pos, size=self.size)
            # Plus glyph
            Color(*_hex(self.icon_color))
            cx, cy = self.center
            w = self.width * 0.5
            t = max(2, self.width * 0.06)
            Line(points=[cx - w/2, cy, cx + w/2, cy], width=t)
            Line(points=[cx, cy - w/2, cx, cy + w/2], width=t)

    def on_press(self):
        Animation(size=(self.size_val * 0.92, self.size_val * 0.92),
                  duration=cfg.DUR_FAST, t="out_quad").start(self)

    def on_release(self):
        Animation(size=(self.size_val, self.size_val),
                  duration=cfg.DUR_FAST, t="out_back").start(self)


# === Divider ===

class GoldDivider(BoxLayout):
    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 1)
        super().__init__(**kw)
        with self.canvas.before:
            Color(*_hex("#2C2C30"))
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*_hex("#2C2C30"))
            Rectangle(pos=self.pos, size=self.size)


# === Section header ===

class SectionHeader(Label):
    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 28)
        kw.setdefault("color", cfg.TEXT)
        kw.setdefault("font_size", cfg.FONT_SIZES["h6"])
        kw.setdefault("bold", True)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(size=lambda *_: setattr(self, "text_size", (self.width, None)))


# === Chip ===

class Chip(ButtonBehavior, BoxLayout):
    label = StringProperty("")
    selected = BooleanProperty(False)
    color_hex = StringProperty("#D4AF37")

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 32)
        kw.setdefault("padding", [12, 4])
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, selected=self._redraw,
                  label=self._refresh_label)
        self._lbl = Label(text=self.label, color=cfg.TEXT,
                          font_size=cfg.FONT_SIZES["caption"])
        self.add_widget(self._lbl)
        self._redraw()

    def _refresh_label(self, *_):
        self._lbl.text = self.label

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.selected:
                Color(*_hex(self.color_hex))
                RoundedRectangle(pos=self.pos, size=self.size,
                                 radius=[cfg.RADIUS_PILL])
                self._lbl.color = _hex("#0E0E10")
            else:
                Color(*_hex("#2C2C30"))
                RoundedRectangle(pos=self.pos, size=self.size,
                                 radius=[cfg.RADIUS_PILL])
                Color(*_hex(self.color_hex, 0.5))
                Line(rounded_rectangle=(self.x, self.y, self.width, self.height,
                                        cfg.RADIUS_PILL), width=1.0)
                self._lbl.color = cfg.TEXT


# === Gold underlined text field ===

class GoldTextField(TextInput):
    hint_text_color = ColorProperty("#5C5C60")
    line_color = ColorProperty("#D4AF37")

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_active", "")
        kw.setdefault("foreground_color", cfg.TEXT)
        kw.setdefault("cursor_color", cfg.GOLD)
        kw.setdefault("padding_y", [10, 10])
        kw.setdefault("font_size", cfg.FONT_SIZES["body"])
        super().__init__(**kw)
        with self.canvas.after:
            Color(*_hex(self.line_color, 0.8))
            self._underline = Line(points=[0, 0, 0, 0], width=1.2)
        self.bind(pos=self._upd_underline, size=self._upd_underline)

    def _upd_underline(self, *_):
        self._underline.points = [self.x, self.y + 2,
                                  self.right, self.y + 2]


# === Empty state ===

class EmptyState(BoxLayout):
    text = StringProperty("Nothing here yet")

    def __init__(self, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("spacing", 8)
        super().__init__(**kw)
        lbl = Label(text=self.text, color=cfg.TEXT_DIM,
                    font_size=cfg.FONT_SIZES["body"], halign="center")
        lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(lbl)
