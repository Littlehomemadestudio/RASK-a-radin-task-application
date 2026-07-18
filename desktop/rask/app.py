"""app.py — Main app controller (mirror of web/js/app.js).

Flow:
    Splash (2.2s) → Onboarding (if first_run) → Lock (if lock_mode != none) → Main view

Main view = bottom-nav (Home/Goals/Stats/Settings) + scrollable screen + FAB.
Modals: QuickLog (FAB), Template (Home add link), Goal (Goals +New).
"""
from __future__ import annotations
import tkinter as tk
from typing import Optional
from . import config
from . import database
from . import timer_service
from . import voice
from .i18n import t
from .ui.theme import font, apply_theme, styled_button
from .ui.screens_splash import SplashView, OnboardingView, LockView
from .ui.screens_main import HomeScreen, GoalsScreen, StatsScreen, SettingsScreen
from .ui.modals import QuickLogModal, TemplateModal, GoalModal


class RaskApp:
    def __init__(self):
        self.root = tk.Tk()
        apply_theme(self.root)
        # Open DB and seed defaults
        database.open_db()
        # Language
        self.lang = database.kv_get("lang", "fa") or "fa"
        # Timer listener
        timer_service.add_listener(self._on_timer_tick)
        timer_service.init_on_startup()
        # State
        self.current_tab = "home"
        self.screens = {}
        self._active_modal: Optional[tk.Toplevel] = None
        # Initial view: splash
        self._show_splash()

    # === Splash ===
    def _show_splash(self):
        self._container = tk.Frame(self.root, bg=config.MATTE_BLACK)
        self._container.pack(fill="both", expand=True)
        self._splash = SplashView(self._container, self._after_splash)
        self._splash.pack(fill="both", expand=True)

    def _after_splash(self):
        first_run = database.kv_get("first_run", "1")
        if first_run == "1":
            self._show_onboarding()
        else:
            self._proceed_after_onboarding()

    def _show_onboarding(self):
        database.kv_set("first_run", "0")
        self._onboarding = OnboardingView(self._container, self.lang, self._proceed_after_onboarding)
        self._onboarding.pack(fill="both", expand=True)

    def _proceed_after_onboarding(self):
        mode = database.kv_get("lock_mode", "none") or "none"
        if mode == "pin":
            self._show_lock()
        else:
            self._show_main()

    def _show_lock(self):
        self._lock = LockView(self._container, self.lang, self._show_main)
        self._lock.pack(fill="both", expand=True)

    def _show_main(self):
        # Clear splash/onboarding/lock
        for child in self._container.winfo_children():
            child.destroy()
        # Main view container
        main = tk.Frame(self._container, bg=config.MATTE_BLACK)
        main.pack(fill="both", expand=True)
        # Screen container (above the bottom nav)
        screen_wrap = tk.Frame(main, bg=config.MATTE_BLACK)
        screen_wrap.pack(fill="both", expand=True)
        # Build all screens (lazy-render)
        self.screens = {
            "home": HomeScreen(screen_wrap, self, self.lang),
            "goals": GoalsScreen(screen_wrap, self, self.lang),
            "stats": StatsScreen(screen_wrap, self, self.lang),
            "settings": SettingsScreen(screen_wrap, self, self.lang),
        }
        for s in self.screens.values():
            s.pack_forget()
        # Bottom nav (mirror of .bottom-nav)
        nav = tk.Frame(main, bg=config.CHARCOAL, height=64,
                       highlightbackground=config.DIVIDER, highlightthickness=1)
        nav.pack(side="bottom", fill="x")
        self.nav_buttons = {}
        for tab, key, icon in [
            ("home", "home", "⌂"),
            ("goals", "goals", "◎"),
            ("stats", "stats", "▤"),
            ("settings", "settings", "⚙"),
        ]:
            b = tk.Button(nav, text=f"{icon}\n{t(key, self.lang)}",
                           bg=config.CHARCOAL, fg=config.TEXT_FAINT,
                          activebackground=config.CHARCOAL, activeforeground=config.GOLD,
                          font=font(10), relief="flat", bd=0, cursor="hand2",
                          height=2, command=lambda _t=tab: self.switch_tab(_t))
            b.pack(side="left", fill="both", expand=True)
            self.nav_buttons[tab] = b
        # FAB (mirror of .fab — gold circle bottom-right, "+" text)
        self.fab = tk.Button(main, text="+", bg=config.GOLD, fg=config.MATTE_BLACK,
                              font=font(28, "normal"), relief="flat", bd=0, cursor="hand2",
                              width=3, height=2, command=self.open_quick_log,
                              highlightthickness=0)
        # Place FAB relative to root (bottom-right of nav area)
        self.root.update_idletasks()
        self.fab.place(in_=main, relx=1.0, rely=1.0, x=-20, y=-80, anchor="se")
        # Show default tab
        self.switch_tab("home")
        # Refresh title
        self.root.title(config.APP_NAME)

    # === Navigation ===
    def switch_tab(self, tab: str):
        self.current_tab = tab
        for k, s in self.screens.items():
            if k == tab:
                s.pack(fill="both", expand=True)
                s.render()
            else:
                s.pack_forget()
        # Update nav button colors
        for k, b in self.nav_buttons.items():
            if k == tab:
                b.config(fg=config.GOLD)
            else:
                b.config(fg=config.TEXT_FAINT)
        # Update window title for active timer (mirror of timer.js _notify)
        if timer_service.is_running():
            e = timer_service.elapsed_sec()
            h = e // 3600
            m = (e % 3600) // 60
            s = e % 60
            txt = f"{h:02d}:{m:02d}:{s:02d} — {timer_service.current_title() or 'Rask'}"
            self.root.title(txt)
        else:
            self.root.title(config.APP_NAME)

    # === Modals ===
    def open_quick_log(self):
        if self._active_modal and self._active_modal.winfo_exists():
            return
        self._active_modal = QuickLogModal(self.root, self.lang, self._after_modal_saved)

    def open_template_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            return
        self._active_modal = TemplateModal(self.root, self.lang, self._after_modal_saved)

    def open_goal_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            return
        self._active_modal = GoalModal(self.root, self.lang, self._after_modal_saved)

    def _after_modal_saved(self):
        # Re-render current screen so new data shows up
        if self.current_tab in self.screens:
            self.screens[self.current_tab].render()

    # === Language switch ===
    def set_lang(self, lang: str):
        self.lang = lang
        database.kv_set("lang", lang)
        # Update nav labels
        for tab, key in [("home", "home"), ("goals", "goals"),
                         ("stats", "stats"), ("settings", "settings")]:
            icon = {"home": "⌂", "goals": "◎", "stats": "▤", "settings": "⚙"}[tab]
            self.nav_buttons[tab].config(text=f"{icon}\n{t(key, lang)}")
        # Update screen language
        for s in self.screens.values():
            s.set_lang(lang)
        self.switch_tab(self.current_tab)

    # === Timer tick ===
    def _on_timer_tick(self, elapsed: int, running: bool):
        # Update window title
        if running:
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.root.title(f"{h:02d}:{m:02d}:{s:02d} — {timer_service.current_title() or 'Rask'}")
        else:
            self.root.title(config.APP_NAME)
        # Update home screen timer card if visible
        if self.current_tab == "home" and "home" in self.screens:
            try:
                self.screens["home"].on_timer_tick(elapsed, running)
            except Exception:
                pass

    # === Run ===
    def run(self):
        self.root.mainloop()
