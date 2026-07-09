"""
navigation.py — Bottom navigation bar.

Gold-on-dark bottom nav with 4 tabs: Home, Goals, Stats, Settings.
Drawn entirely with Kivy canvas (no external icon font).
"""
from __future__ import annotations

from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, NumericProperty, ColorProperty

from rask import config as cfg


ICONS = ("home", "goals", "stats", "settings")
LABELS_EN = ("Home", "Goals", "Stats", "Settings")
LABELS_FA = ("خانه", "اهداف", "آمار", "تنظیمات")


class BottomNav(BoxLayout):
    def __init__(self, on_select, lang: str = "fa", **kw):
        kw.setdefault("orientation", "horizontal")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 64)
        kw.setdefault("spacing", 0)
        super().__init__(**kw)
        self._on_select = on_select
        self._lang = lang
        self._selected = 0
        self._buttons: list[_NavButton] = []

        labels = LABELS_FA if lang == "fa" else LABELS_EN
        for i, (icon, lbl) in enumerate(zip(ICONS, labels)):
            b = _NavButton(icon=icon, label=lbl)
            b.bind(on_release=lambda inst, idx=i: self._select(idx))
            self.add_widget(b)
            self._buttons.append(b)
        self._refresh()

        # Top divider
        with self.canvas.before:
            Color(*_hex("#2C2C30"))
            self._div = Line(points=[0, 0, 0, 0], width=1)
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_):
        self._div.points = [self.x, self.top, self.right, self.top]

    def _select(self, idx: int):
        self._selected = idx
        self._refresh()
        self._on_select(idx)

    def _refresh(self):
        for i, b in enumerate(self._buttons):
            b.active = (i == self._selected)


def _hex(h: str, alpha: float = 1.0):
    from kivy.utils import get_color_from_hex
    c = get_color_from_hex(h)
    return (c[0], c[1], c[2], alpha)


class _NavButton(ButtonBehavior, FloatLayout):
    icon = StringProperty("home")
    label = StringProperty("")
    active = False

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, active=self._redraw,
                  icon=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            color = cfg.GOLD if self.active else cfg.TEXT_FAINT
            Color(*color)
            # Icon: simple geometric shape per type
            cx, cy = self.center
            s = 18
            cy_icon = cy + 8
            if self.icon == "home":
                # House: triangle on square
                Line(points=[cx - s, cy_icon - s/2,
                             cx, cy_icon + s/2,
                             cx + s, cy_icon - s/2,
                             cx - s, cy_icon - s/2], width=2)
                Line(points=[cx - s*0.6, cy_icon - s/2,
                             cx - s*0.6, cy_icon - s,
                             cx + s*0.6, cy_icon - s,
                             cx + s*0.6, cy_icon - s/2], width=2)
            elif self.icon == "goals":
                # Target: 2 concentric circles + dot
                Line(circle=(cx, cy_icon, s, 0, 360), width=2)
                Line(circle=(cx, cy_icon, s*0.55, 0, 360), width=2)
            elif self.icon == "stats":
                # 3 bars
                Line(points=[cx - s, cy_icon - s/2, cx - s, cy_icon + s/2], width=2)
                Line(points=[cx, cy_icon - s, cx, cy_icon + s/2], width=2)
                Line(points=[cx + s, cy_icon - s/3, cx + s, cy_icon + s/2], width=2)
            elif self.icon == "settings":
                # Gear: circle + 4 spokes
                Line(circle=(cx, cy_icon, s*0.7, 0, 360), width=2)
                Line(points=[cx, cy_icon - s, cx, cy_icon - s*0.4], width=2)
                Line(points=[cx, cy_icon + s*0.4, cx, cy_icon + s], width=2)
                Line(points=[cx - s, cy_icon, cx - s*0.4, cy_icon], width=2)
                Line(points=[cx + s*0.4, cy_icon, cx + s, cy_icon], width=2)

        # Label
        if not hasattr(self, "_lbl"):
            self._lbl = Label(text=self.label, color=cfg.TEXT_FAINT,
                              font_size=cfg.FONT_SIZES["tiny"],
                              pos=(self.x, self.y + 6),
                              size=(self.width, 18))
            self.add_widget(self._lbl)
        self._lbl.pos = (self.x, self.y + 6)
        self._lbl.size = (self.width, 18)
        self._lbl.text = self.label
        self._lbl.color = cfg.GOLD if self.active else cfg.TEXT_FAINT
