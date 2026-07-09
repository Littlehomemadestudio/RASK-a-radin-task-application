"""
onboarding.py — 3-screen onboarding flow.

Screens:
  1. Welcome — "Track time beautifully"
  2. Goals — "Set goals. Build streaks."
  3. Privacy — "100% offline. Your data stays on your device."

Persian/English text + gold-on-dark illustrations drawn with Kivy canvas.
"""
from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from rask import config as cfg
from rask.data import database as db
from rask.ui.components import GoldButton, OutlinedButton


SLIDES = [
    {
        "icon": "ring",
        "title_en": "Track time beautifully",
        "title_fa": "زمان را زیبا پیگیری کن",
        "body_en": "Log activities with a tap, run a background stopwatch, "
                   "and watch your day take shape.",
        "body_fa": "فعالیت‌ها را با یک ضبط ثبت کن، کرنومتر پس‌زمینه را اجرا کن "
                   "و روزت را شکل بده.",
    },
    {
        "icon": "goal",
        "title_en": "Set goals. Build streaks.",
        "title_fa": "هدف تعیین کن. زنجیره بساز.",
        "body_en": "Daily, weekly, monthly goals. Keep your streak alive and "
                   "earn milestone badges.",
        "body_fa": "اهداف روزانه، هفتگی و ماهانه. زنجیره‌ات را زنده نگه‌دار و "
                   "نشان‌های قدم‌به‌قدم بگیر.",
    },
    {
        "icon": "lock",
        "title_en": "100% offline. Private.",
        "title_fa": "۱۰۰٪ آفلاین. خصوصی.",
        "body_en": "Your data lives on your device. Encrypted backups when "
                   "you want them. No accounts, no servers, no tracking.",
        "body_fa": "داده‌هایت روی دستگاهت می‌مانند. پشتیبان رمزنگاری‌شده "
                   "هر وقت بخواهی. بدون حساب، بدون سرور، بدون ردیابی.",
    },
]


class OnboardingView(FloatLayout):
    def __init__(self, on_done, lang: str = "fa", **kw):
        super().__init__(**kw)
        self._on_done = on_done
        self._lang = lang
        self._index = 0
        self._build()
        self._show(0)

    def _build(self):
        # Background
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        # Slide container
        self._slide_box = BoxLayout(orientation="vertical",
                                    padding=[cfg.SPACE["xxxl"]] * 2,
                                    spacing=cfg.SPACE["lg"])
        self.add_widget(self._slide_box)

        # Bottom bar: dots + buttons
        self._bottom = BoxLayout(orientation="horizontal",
                                 size_hint_y=None, height=64,
                                 padding=[cfg.SPACE["xl"], 8],
                                 spacing=cfg.SPACE["md"])
        self.add_widget(self._bottom)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _show(self, idx: int) -> None:
        self._slide_box.clear_widgets()
        self._bottom.clear_widgets()
        slide = SLIDES[idx]
        title = slide["title_fa"] if self._lang == "fa" else slide["title_en"]
        body = slide["body_fa"] if self._lang == "fa" else slide["body_en"]

        # Illustration
        self._slide_box.add_widget(_Illustration(slide["icon"],
                                                  size_hint_y=0.45))
        # Title
        self._slide_box.add_widget(Label(
            text=title, color=cfg.GOLD, font_size=cfg.FONT_SIZES["h2"],
            bold=True, halign="center",
            size_hint_y=None, height=80,
        ))
        # Body
        body_lbl = Label(
            text=body, color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["body"],
            halign="center", valign="top",
            size_hint_y=None, height=120,
        )
        body_lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self._slide_box.add_widget(body_lbl)

        # Dots
        dots = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=24, spacing=8)
        for i in range(len(SLIDES)):
            d = _Dot(active=(i == idx))
            dots.add_widget(d)
        self._bottom.add_widget(dots)

        # Spacer
        self._bottom.add_widget(Label(size_hint_x=1))

        # Buttons
        if idx < len(SLIDES) - 1:
            skip = OutlinedButton(
                text="رد شدن" if self._lang == "fa" else "Skip",
                size_hint_x=0.4, size_hint_y=None, height=44,
            )
            skip.bind(on_release=lambda *_: self._finish())
            self._bottom.add_widget(skip)
            nxt = GoldButton(
                text="بعدی" if self._lang == "fa" else "Next",
                size_hint_x=0.4, size_hint_y=None, height=44,
            )
            nxt.bind(on_release=lambda *_: self._next())
            self._bottom.add_widget(nxt)
        else:
            start = GoldButton(
                text="شروع" if self._lang == "fa" else "Get started",
                size_hint_x=0.6, size_hint_y=None, height=44,
            )
            start.bind(on_release=lambda *_: self._finish())
            self._bottom.add_widget(start)

    def _next(self):
        if self._index < len(SLIDES) - 1:
            self._index += 1
            self._show(self._index)

    def _finish(self):
        db.pref_set_bool(cfg.PREF_ONBOARDED, True)
        self._on_done()


class _Dot(FloatLayout):
    def __init__(self, active: bool = False, **kw):
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = (10 if active else 6, 10 if active else 6)
        self.active = active
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*cfg.GOLD if self.active else cfg.TEXT_FAINT)
            Ellipse(pos=self.pos, size=self.size)


class _Illustration(FloatLayout):
    """Draws a simple gold-on-dark illustration per slide."""
    def __init__(self, kind: str, **kw):
        super().__init__(**kw)
        self.kind = kind
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*cfg.GOLD)
            cx, cy = self.center
            r = min(self.width, self.height) * 0.25
            if self.kind == "ring":
                Line(circle=(cx, cy, r, 0, 360), width=4)
                Line(circle=(cx, cy, r * 0.5, 0, 270), width=8)
            elif self.kind == "goal":
                # Target (concentric rings)
                for i, ratio in enumerate([1.0, 0.66, 0.33]):
                    Line(circle=(cx, cy, r * ratio, 0, 360), width=2)
                # Arrow stub
                Line(points=[cx - r, cy + r, cx + r, cy - r], width=2)
            elif self.kind == "lock":
                # Padlock body
                RoundedRectangle(pos=(cx - r, cy - r),
                                 size=(2 * r, 1.4 * r),
                                 radius=[6])
                # Shackle
                Line(circle=(cx, cy + r * 0.7, r * 0.5, 0, 180), width=3)
