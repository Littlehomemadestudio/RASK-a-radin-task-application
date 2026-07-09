"""
lock.py — App lock screen shown when PIN or biometric lock is enabled.
"""
from __future__ import annotations

from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.clock import Clock

from rask import config as cfg
from rask.services import biometric
from rask.ui.components import GoldButton, OutlinedButton, GoldTextField


class LockScreen(FloatLayout):
    def __init__(self, app, on_unlock, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._on_unlock = on_unlock
        self._build()

    def _build(self):
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        box = BoxLayout(orientation="vertical",
                        padding=[cfg.SPACE["xl"], cfg.SPACE["xxxl"]],
                        spacing=cfg.SPACE["md"])
        box.add_widget(Label(
            text="Rask",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h1"], bold=True,
            size_hint_y=None, height=80,
        ))
        box.add_widget(Label(
            text="قفل را باز کنید" if self._lang == "fa" else "Unlock Rask",
            color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["caption"],
            size_hint_y=None, height=30,
        ))
        box.add_widget(Label(size_hint_y=1))

        self._pin = GoldTextField(
            hint_text="پین خود را وارد کنید" if self._lang == "fa"
                      else "Enter PIN",
            password=True, multiline=False, input_filter="int",
            size_hint_y=None, height=50,
        )
        box.add_widget(self._pin)

        unlock = GoldButton(
            text="باز کردن" if self._lang == "fa" else "Unlock",
            size_hint_y=None, height=48,
        )
        unlock.bind(on_release=self._try_unlock)
        box.add_widget(unlock)

        mode = biometric.lock_mode()
        if mode == cfg.LOCK_BIOMETRIC or biometric.is_biometric_available():
            bio = OutlinedButton(
                text="استفاده از اثر انگشت" if self._lang == "fa"
                     else "Use biometric",
                size_hint_y=None, height=44,
            )
            bio.bind(on_release=self._try_biometric)
            box.add_widget(bio)

        box.add_widget(Label(size_hint_y=1))
        self.add_widget(box)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _try_unlock(self, *_):
        pin = self._pin.text
        if not pin:
            return
        if biometric.verify_pin(pin):
            self._on_unlock()
        else:
            self.app.toast("پین نادرست" if self._lang == "fa"
                           else "Incorrect PIN")
            self._pin.text = ""

    def _try_biometric(self, *_):
        def on_success():
            Clock.schedule_once(lambda *_: self._on_unlock())
        def on_fail(err):
            self.app.toast(f"Biometric failed: {err}")
        biometric.authenticate_biometric(on_success, on_fail)
