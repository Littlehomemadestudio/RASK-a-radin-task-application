"""
settings.py — Settings screen.

Sections:
  - Appearance: language (fa/en), RTL toggle
  - App lock: PIN / biometric
  - Backup & restore: export encrypted file, import encrypted file
  - About: version, licenses
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from rask import config as cfg
from rask.data import database as db
from rask.data import backup as backup_mod
from rask.services import biometric
from rask.ui.components import (
    GoldCard, GoldButton, OutlinedButton, SectionHeader, GoldTextField,
)


class SettingsScreen(FloatLayout):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._build()

    def _build(self):
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        root = BoxLayout(orientation="vertical",
                         padding=[cfg.SPACE["lg"], cfg.SPACE["xl"]],
                         spacing=cfg.SPACE["md"])
        root.add_widget(Label(
            text="تنظیمات" if self._lang == "fa" else "Settings",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h3"], bold=True,
            size_hint_y=None, height=44,
        ))

        scroll = ScrollView()
        list_ = BoxLayout(orientation="vertical", spacing=cfg.SPACE["md"],
                          size_hint_y=None)
        list_.bind(minimum_height=list_.setter("height"))
        scroll.add_widget(list_)
        root.add_widget(scroll)
        self.add_widget(root)

        # === Appearance ===
        list_.add_widget(SectionHeader(
            text="ظاهر" if self._lang == "fa" else "Appearance"
        ))
        app_card = GoldCard(size_hint_y=None, height=120)
        app_card.add_widget(Label(
            text=f"زبان: {_cur_lang_name(self._lang)}",
            color=cfg.TEXT, font_size=cfg.FONT_SIZES["body"],
            halign="left", size_hint_y=None, height=28,
        ))
        lang_btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                              height=40, spacing=cfg.SPACE["sm"])
        fa_btn = OutlinedButton(text="فارسی", size_hint_x=0.5)
        en_btn = OutlinedButton(text="English", size_hint_x=0.5)
        fa_btn.bind(on_release=lambda *_: self._set_lang("fa"))
        en_btn.bind(on_release=lambda *_: self._set_lang("en"))
        lang_btns.add_widget(fa_btn)
        lang_btns.add_widget(en_btn)
        app_card.add_widget(lang_btns)
        list_.add_widget(app_card)

        # === App lock ===
        list_.add_widget(SectionHeader(
            text="قفل برنامه" if self._lang == "fa" else "App lock"
        ))
        lock_card = GoldCard(size_hint_y=None, height=180)
        lock_card.add_widget(Label(
            text=(
                f"حالت فعلی: {_lock_mode_label(biometric.lock_mode(), self._lang)}"
            ),
            color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["small"],
            halign="left", size_hint_y=None, height=24,
        ))
        pin_field = GoldTextField(
            hint_text="پین جدید (۴-۶ رقم)" if self._lang == "fa"
                      else "New PIN (4-6 digits)",
            input_filter="int", multiline=False, password=True,
            size_hint_y=None, height=44,
        )
        lock_card.add_widget(pin_field)
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=40, spacing=cfg.SPACE["sm"])
        set_pin = GoldButton(
            text="تنظیم پین" if self._lang == "fa" else "Set PIN",
            size_hint_x=0.5,
        )
        set_pin.bind(on_release=lambda *_: self._set_pin(pin_field.text))
        bio = OutlinedButton(
            text="فعال‌سازی اثر انگشت" if self._lang == "fa"
                 else "Enable biometric",
            size_hint_x=0.5,
        )
        bio.bind(on_release=lambda *_: self._enable_biometric())
        btns.add_widget(set_pin)
        btns.add_widget(bio)
        lock_card.add_widget(btns)

        clr = OutlinedButton(
            text="حذف قفل" if self._lang == "fa" else "Clear lock",
            size_hint_y=None, height=32,
        )
        clr.bind(on_release=lambda *_: self._clear_lock())
        lock_card.add_widget(clr)
        list_.add_widget(lock_card)

        # === Backup ===
        list_.add_widget(SectionHeader(
            text="پشتیبان و بازیابی" if self._lang == "fa"
                 else "Backup & restore"
        ))
        bk_card = GoldCard(size_hint_y=None, height=180)
        self._bk_pass = GoldTextField(
            hint_text="رمز پشتیبان" if self._lang == "fa" else "Backup password",
            password=True, multiline=False,
            size_hint_y=None, height=44,
        )
        bk_card.add_widget(self._bk_pass)
        exp_btn = GoldButton(
            text="خروجی پشتیبان" if self._lang == "fa" else "Export backup",
            size_hint_y=None, height=40,
        )
        exp_btn.bind(on_release=self._export_backup)
        bk_card.add_widget(exp_btn)
        imp_btn = OutlinedButton(
            text="بازیابی پشتیبان" if self._lang == "fa" else "Restore backup",
            size_hint_y=None, height=40,
        )
        imp_btn.bind(on_release=self._import_backup)
        bk_card.add_widget(imp_btn)
        list_.add_widget(bk_card)

        # === About ===
        list_.add_widget(SectionHeader(
            text="درباره" if self._lang == "fa" else "About"
        ))
        about = GoldCard(size_hint_y=None, height=100)
        about.add_widget(Label(
            text=f"Rask v{cfg.APP_VERSION}",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["body"], bold=True,
            halign="left", size_hint_y=None, height=28,
        ))
        about.add_widget(Label(
            text="آفلاین. خصوصی. زیبا."
                 if self._lang == "fa"
                 else "Offline. Private. Beautiful.",
            color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["small"],
            halign="left", size_hint_y=None, height=22,
        ))
        about.add_widget(Label(
            text="© 2026 Littlehomemade Studio",
            color=cfg.TEXT_FAINT, font_size=cfg.FONT_SIZES["tiny"],
            halign="left", size_hint_y=None, height=20,
        ))
        list_.add_widget(about)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _set_lang(self, lang: str):
        db.pref_set(cfg.PREF_LANG, lang)
        self.app.lang = lang
        self.app.rebuild_ui()

    def _set_pin(self, pin: str):
        if len(pin) < 4:
            self.app.toast("پین کوتاه است" if self._lang == "fa"
                           else "PIN too short")
            return
        biometric.setup_pin(pin)
        self.app.toast("پین تنظیم شد" if self._lang == "fa"
                       else "PIN set")

    def _enable_biometric(self):
        if biometric.is_biometric_available():
            biometric.set_lock_mode(cfg.LOCK_BIOMETRIC)
            self.app.toast(
                "اثر انگشت فعال شد" if self._lang == "fa"
                else "Biometric enabled"
            )
        else:
            self.app.toast(
                "اثر انگشت در دسترس نیست" if self._lang == "fa"
                else "Biometric unavailable"
            )

    def _clear_lock(self):
        biometric.clear_lock()
        self.app.toast("قفل حذف شد" if self._lang == "fa"
                       else "Lock cleared")

    def _export_backup(self, *_):
        pwd = self._bk_pass.text
        if len(pwd) < 6:
            self.app.toast("رمز کوتاه است (≥۶)"
                           if self._lang == "fa"
                           else "Password too short (≥6)")
            return
        from datetime import datetime
        out_dir = self.app.user_data_dir
        out = f"{out_dir}/rask_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.rask"
        try:
            backup_mod.export_to_file(Path(out), pwd)
            self.app.toast(
                f"پشتیبان ذخیره شد" if self._lang == "fa"
                else f"Backup saved"
            )
        except Exception as ex:
            self.app.toast(f"Error: {ex}")

    def _import_backup(self, *_):
        pwd = self._bk_pass.text
        if not pwd:
            self.app.toast("رمز را وارد کن" if self._lang == "fa"
                           else "Enter password")
            return
        # Pick most recent backup file
        out_dir = Path(self.app.user_data_dir)
        bks = sorted(out_dir.glob("rask_backup_*.rask"), reverse=True)
        if not bks:
            self.app.toast("پشتیبانی پیدا نشد" if self._lang == "fa"
                           else "No backup file found")
            return
        try:
            backup_mod.import_from_file(bks[0], pwd)
            self.app.toast("بازیابی شد" if self._lang == "fa"
                           else "Restored")
            self.app.rebuild_ui()
        except Exception as ex:
            self.app.toast(f"Error: {ex}")


def _cur_lang_name(lang: str) -> str:
    return "فارسی" if lang == "fa" else "English"


def _lock_mode_label(mode: str, lang: str) -> str:
    if mode == cfg.LOCK_PIN:
        return "پین" if lang == "fa" else "PIN"
    if mode == cfg.LOCK_BIOMETRIC:
        return "اثر انگشت" if lang == "fa" else "Biometric"
    return "هیچ" if lang == "fa" else "None"
