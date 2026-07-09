"""
app.py — RaskApp, the main Kivy App.

Manages:
  - Theme, language, RTL
  - Splash → onboarding → lock → main flow
  - Bottom navigation between Home / Goals / Stats / Settings
  - Quick-log modal overlay
  - Toast notifications
  - Lifecycle: ensures DB is opened, channels created, reminders scheduled
"""
from __future__ import annotations

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.animation import Animation

from rask import config as cfg
from rask.data import database as db
from rask.utils import date_utils, locale_utils
from rask.services import notifications, reminders, biometric
from rask.ui.splash import SplashView
from rask.ui.onboarding import OnboardingView
from rask.ui.lock import LockScreen
from rask.ui.navigation import BottomNav
from rask.ui.home import HomeScreen
from rask.ui.goals import GoalsScreen
from rask.ui.stats import StatsScreen
from rask.ui.settings import SettingsScreen
from rask.ui.quick_log import QuickLogView


class RaskApp(App):
    """Rask application root."""
    use_kivy_settings = False
    title = "Rask"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.lang = "fa"
        self._root = FloatLayout()
        self._nav: BottomNav | None = None
        self._content: BoxLayout | None = None
        self._screens: dict[int, FloatLayout] = {}
        self._modal: FloatLayout | None = None
        self._toast_lbl: Label | None = None

    # === Lifecycle ===

    def build(self):
        # Open DB / seed
        db.get_connection()
        # Determine language
        self.lang = db.pref_get(cfg.PREF_LANG, locale_utils.detect_language())
        cfg._active_lang = self.lang
        # Apply RTL to window if needed
        if locale_utils.is_rtl(self.lang):
            # Kivy doesn't have a global RTL flag; each widget handles its own.
            pass

        # Ensure notif channels
        notifications.ensure_channels()
        # Schedule daily reminder
        reminders.schedule_daily_reminder(hour=21, minute=0)

        Window.clearcolor = cfg.MATTE_BLACK
        self._show_splash()
        return self._root

    def on_pause(self):
        # Returning True keeps the app in memory (timer continues in foreground service)
        return True

    def on_resume(self):
        pass

    # === Flow ===

    def _show_splash(self):
        self._root.clear_widgets()
        self._root.add_widget(SplashView(on_done=self._after_splash))

    def _after_splash(self):
        onboarded = db.pref_get_bool(cfg.PREF_ONBOARDED, False)
        if not onboarded:
            self._show_onboarding()
        else:
            self._maybe_show_lock()

    def _show_onboarding(self):
        self._root.clear_widgets()
        self._root.add_widget(
            OnboardingView(on_done=self._maybe_show_lock, lang=self.lang)
        )

    def _maybe_show_lock(self):
        mode = biometric.lock_mode()
        if mode == cfg.LOCK_NONE:
            self._show_main()
        else:
            self._root.clear_widgets()
            self._root.add_widget(
                LockScreen(app=self, on_unlock=self._show_main)
            )

    def _show_main(self):
        self._root.clear_widgets()
        container = BoxLayout(orientation="vertical")
        self._content = BoxLayout(orientation="vertical")
        container.add_widget(self._content)
        self._nav = BottomNav(on_select=self._on_nav_select, lang=self.lang)
        container.add_widget(self._nav)
        self._root.add_widget(container)
        # Build screens lazily
        self._screens = {}
        self._on_nav_select(0)

    def _on_nav_select(self, idx: int):
        if self._content is None:
            return
        self._content.clear_widgets()
        if idx not in self._screens:
            if idx == 0:
                self._screens[0] = HomeScreen(app=self)
            elif idx == 1:
                self._screens[1] = GoalsScreen(app=self)
            elif idx == 2:
                self._screens[2] = StatsScreen(app=self)
            elif idx == 3:
                self._screens[3] = SettingsScreen(app=self)
        screen = self._screens[idx]
        self._content.add_widget(screen)
        # Refresh on display
        if hasattr(screen, "refresh"):
            screen.refresh()
        elif hasattr(screen, "on_enter"):
            screen.on_enter()

    # === Quick-log modal ===

    def open_quick_log(self):
        if self._modal is not None:
            return
        self._modal = FloatLayout()
        with self._modal.canvas.before:
            Color(0, 0, 0, 0.75)
            self._modal_bg = Rectangle(pos=(0, 0), size=Window.size)
        view = QuickLogView(app=self, on_close=self.close_quick_log,
                            size=Window.size, pos=(0, 0))
        self._modal.add_widget(view)
        self._root.add_widget(self._modal)

    def close_quick_log(self):
        if self._modal is None:
            return
        self._root.remove_widget(self._modal)
        self._modal = None
        # Refresh home
        if 0 in self._screens and isinstance(self._screens[0], HomeScreen):
            self._screens[0].refresh()

    # === Toast ===

    def toast(self, text: str):
        if self._toast_lbl is None:
            self._toast_lbl = Label(
                text="", color=cfg.TEXT, font_size=cfg.FONT_SIZES["small"],
                size_hint=(None, None), padding=(20, 12),
            )
            with self._toast_lbl.canvas.before:
                Color(*cfg.SURFACE)
                self._toast_bg = Rectangle(pos=(0, 0), size=(0, 0))
            self._toast_lbl.bind(size=self._upd_toast_bg,
                                 pos=self._upd_toast_bg)
        self._toast_lbl.text = text
        self._toast_lbl.texture_update()
        w = self._toast_lbl.texture.size[0] + 40
        h = self._toast_lbl.texture.size[1] + 24
        self._toast_lbl.size = (w, h)
        self._toast_lbl.pos = ((Window.width - w) / 2, 96)
        self._root.add_widget(self._toast_lbl)
        # Auto-dismiss
        Clock.schedule_once(lambda dt: self._dismiss_toast(), 2.5)

    def _dismiss_toast(self):
        if self._toast_lbl and self._toast_lbl.parent:
            self._root.remove_widget(self._toast_lbl)

    def _upd_toast_bg(self, *_):
        self._toast_bg.pos = self._toast_lbl.pos
        self._toast_bg.size = self._toast_lbl.size

    # === Rebuild (e.g., after language change) ===

    def rebuild_ui(self):
        cfg._active_lang = self.lang
        self._screens.clear()
        if self._nav:
            self._nav.parent.remove_widget(self._nav)
            self._nav = None
        self._show_main()
