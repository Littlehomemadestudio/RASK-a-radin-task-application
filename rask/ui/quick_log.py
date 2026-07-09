"""
quick_log.py — Quick-log modal for adding an activity fast.

Fields: title, category chips, duration (HH:MM), voice input button.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from rask import config as cfg
from rask.data import repositories as repos
from rask.data.models import Activity
from rask.services import timer_service
from rask.ui.components import (
    GoldButton, OutlinedButton, GoldCard, GoldTextField, Chip,
    SectionHeader, FabButton,
)


class QuickLogView(FloatLayout):
    def __init__(self, app, on_close, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._on_close = on_close
        self._selected_cat_id: Optional[int] = None
        self._build()

    def _build(self):
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        root = BoxLayout(orientation="vertical",
                         padding=[cfg.SPACE["lg"], cfg.SPACE["xl"]],
                         spacing=cfg.SPACE["md"])
        self.add_widget(root)

        # Title
        root.add_widget(Label(
            text="ثبت سریع" if self._lang == "fa" else "Quick log",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h4"], bold=True,
            size_hint_y=None, height=40,
        ))

        # Title field
        self._title_field = GoldTextField(
            hint_text="عنوان فعالیت" if self._lang == "fa" else "Activity title",
            size_hint_y=None, height=50,
        )
        root.add_widget(self._title_field)

        # Voice button
        voice_btn = OutlinedButton(
            text="🎤 ورودی صوتی" if self._lang == "fa" else "Voice input",
            size_hint_y=None, height=40,
        )
        voice_btn.bind(on_release=self._on_voice)
        root.add_widget(voice_btn)

        # Categories
        root.add_widget(SectionHeader(
            text="دسته‌بندی" if self._lang == "fa" else "Category"
        ))
        cat_scroll = ScrollView(size_hint_y=None, height=44,
                                do_scroll_y=False, bar_width=0)
        self._cat_box = BoxLayout(orientation="horizontal",
                                  size_hint_y=None, height=44,
                                  spacing=cfg.SPACE["sm"])
        self._populate_categories()
        cat_scroll.add_widget(self._cat_box)
        root.add_widget(cat_scroll)

        # Duration
        root.add_widget(SectionHeader(
            text="مدت زمان (HH:MM)" if self._lang == "fa" else "Duration (HH:MM)"
        ))
        dur_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=50, spacing=cfg.SPACE["sm"])
        self._dur_h = GoldTextField(hint_text="HH", input_filter="int",
                                    multiline=False, size_hint_x=0.3)
        self._dur_m = GoldTextField(hint_text="MM", input_filter="int",
                                    multiline=False, size_hint_x=0.3)
        dur_box.add_widget(Label(text=":", color=cfg.GOLD,
                                 size_hint_x=0.05, font_size=cfg.FONT_SIZES["h4"]))
        dur_box.add_widget(self._dur_h)
        dur_box.add_widget(self._dur_m)
        root.add_widget(dur_box)

        # Stopwatch option
        self._stopwatch_btn = OutlinedButton(
            text="شروع کرنومتر به جای مدت ثابت"
            if self._lang == "fa"
            else "Start stopwatch instead",
            size_hint_y=None, height=44,
        )
        self._stopwatch_btn.bind(on_release=self._on_start_stopwatch)
        root.add_widget(self._stopwatch_btn)

        # Spacer
        root.add_widget(Label(size_hint_y=1))

        # Save / Cancel
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=50, spacing=cfg.SPACE["sm"])
        cancel = OutlinedButton(
            text="انصراف" if self._lang == "fa" else "Cancel",
            size_hint_x=0.5,
        )
        cancel.bind(on_release=lambda *_: self._on_close())
        save = GoldButton(
            text="ذخیره" if self._lang == "fa" else "Save",
            size_hint_x=0.5,
        )
        save.bind(on_release=self._on_save)
        btns.add_widget(cancel)
        btns.add_widget(save)
        root.add_widget(btns)

    def _populate_categories(self):
        cats = repos.CategoryRepository.all()
        for c in cats:
            chip = Chip(label=c.name_en, color_hex=c.color)
            chip.size_hint_x = None
            chip.width = max(70, len(c.name_en) * 12 + 32)
            chip.bind(on_release=lambda inst, cc=c: self._select_cat(cc.id, inst))
            self._cat_box.add_widget(chip)

    def _select_cat(self, cid: int, chip):
        self._selected_cat_id = cid
        for c in self._cat_box.children:
            c.selected = (c is chip)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _on_voice(self, *_):
        from rask.utils.voice import start_voice_input
        def cb(text):
            if text:
                self._title_field.text = text
        start_voice_input(cb,
                          language="fa-IR" if self._lang == "fa" else "en-US")

    def _on_start_stopwatch(self, *_):
        title = self._title_field.text.strip()
        timer_service.start(title, category_id=self._selected_cat_id)
        self._on_close()

    def _on_save(self, *_):
        title = self._title_field.text.strip() or "(no title)"
        try:
            h = int(self._dur_h.text or "0")
        except ValueError:
            h = 0
        try:
            m = int(self._dur_m.text or "0")
        except ValueError:
            m = 0
        sec = (h * 3600) + (m * 60)
        if sec <= 0:
            # No duration -> start a stopwatch instead
            timer_service.start(title, category_id=self._selected_cat_id)
            self._on_close()
            return

        now = datetime.now()
        a = Activity(
            title=title,
            category_id=self._selected_cat_id,
            kind=cfg.KIND_MANUAL,
            date_iso=now.date().isoformat(),
            duration_sec=sec,
        )
        repos.ActivityRepository.insert(a)
        self._on_close()
