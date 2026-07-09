"""
splash.py — Splash screen.

Shows gold-on-dark splash with the Rask logo (gold ring + 'R'),
auto-advances to onboarding (first run) or app lock / home (subsequent runs).
"""
from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.utils import get_color_from_hex

from rask import config as cfg
from rask.data import database as db


class SplashView(FloatLayout):
    def __init__(self, on_done, **kw):
        super().__init__(**kw)
        self._on_done = on_done
        self._build()
        Clock.schedule_once(self._animate_in, 0)
        Clock.schedule_once(self._advance, 2.2)

    def _build(self):
        with self.canvas.before:
            Color(*get_color_from_hex("#0E0E10"))
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        # Logo: gold ring with R in the middle (will be drawn via canvas)
        self._ring = _LogoWidget(size_hint=(None, None), size=(180, 180))
        self._ring.pos = (self.center_x - 90, self.center_y - 30)
        self.add_widget(self._ring)

        self._title = Label(
            text="Rask", color=cfg.GOLD, font_size=cfg.FONT_SIZES["h1"],
            bold=True, size_hint=(None, None), size=(200, 60),
            pos=(self.center_x - 100, self.center_y - 100),
        )
        self.add_widget(self._title)

        self._tagline = Label(
            text="Time, refined.", color=cfg.TEXT_DIM,
            font_size=cfg.FONT_SIZES["caption"], italic=True,
            size_hint=(None, None), size=(200, 30),
            pos=(self.center_x - 100, self.center_y - 140),
        )
        self.add_widget(self._tagline)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*get_color_from_hex("#0E0E10"))
            Rectangle(pos=self.pos, size=self.size)

    def _animate_in(self, *_):
        Animation(size=(220, 220), duration=cfg.DUR_SLOW, t="out_back").start(self._ring)
        # Keep logo centered during grow
        def _recenter(*_):
            self._ring.pos = (self.center_x - self._ring.width/2,
                              self.center_y - self._ring.height/2 + 30)
        Clock.schedule_interval(_recenter, 0)

    def _advance(self, *_):
        self._on_done()


class _LogoWidget(FloatLayout):
    """Gold ring + 'R' glyph."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*cfg.GOLD)
            Line(circle=(self.center_x, self.center_y,
                         min(self.width, self.height) / 2 - 8, 0, 360),
                 width=3)
            # 'R' via CoreLabel
            from kivy.core.text import Label as CoreLabel
            lbl = CoreLabel(text="R",
                            font_size=self.height * 0.55,
                            color=cfg.GOLD)
            lbl.refresh()
            tex = lbl.texture
            if tex:
                Rectangle(texture=tex,
                          pos=(self.center_x - tex.width/2,
                               self.center_y - tex.height/2),
                          size=tex.size)
