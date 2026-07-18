"""app.py — Main app controller (1:1 mirror of web/js/app.js).

Flow:
    Splash (2.2s) → Onboarding (if first_run) → Lock (if lock_mode != none) → Main

Main view:
    +--------------------------------------+
    |  Scrollable screen (Home/Goals/...)  |
    |                                      |
    |                                      |
    +--------------------------------------+
    |  Bottom nav (Home/Goals/Stats/Set)   |
    +--------------------------------------+
                                       [FAB +]

Modals:
    QuickLog (FAB), Template (Home), Goal (Goals),
    EditActivity (Home activity click), Search (Ctrl+F),
    Recurring (Settings), Shortcuts (?).
"""
from __future__ import annotations
import tkinter as tk
from typing import Optional

from . import config
from . import database
from . import timer_service
from .i18n import t, is_rtl
from .ui.theme import apply_theme
from .ui.screens_splash import SplashView, OnboardingView, LockView
from .ui.screens_main import HomeScreen, GoalsScreen, StatsScreen, SettingsScreen
from .ui.modals import (
    QuickLogModal, TemplateModal, GoalModal,
    EditActivityModal, SearchModal, RecurringModal, ShortcutsModal,
)
from . import widgets
from .widgets import FAB, BottomNav, Toast, get_font


class RaskApp:
    """The main Rask application controller."""

    def __init__(self):
        self.root = tk.Tk()
        apply_theme(self.root)
        # Open DB and seed defaults
        database.open_db()
        # Register timer root for tick scheduling
        timer_service.set_root(self.root)
        # Language
        self.lang = database.kv_get("lang", "fa") or "fa"
        # Apply RTL/LTR direction
        self._apply_direction()
        # Timer listener
        timer_service.add_listener(self._on_timer_tick)
        timer_service.init_on_startup()
        # State
        self.current_tab = "home"
        self.screens: dict[str, object] = {}
        self._active_modal: Optional[tk.Toplevel] = None
        self._main_view: Optional[tk.Frame] = None
        self._nav: Optional[BottomNav] = None
        self._fab: Optional[FAB] = None
        # Setup keyboard shortcuts
        self._setup_shortcuts()
        # Show splash
        self._show_splash()

    # =================================================================
    # === DIRECTION (RTL/LTR) ===
    # =================================================================
    def _apply_direction(self):
        """Apply RTL/LTR based on current language."""
        # Tkinter doesn't have great RTL support, but we can at least set
        # the option for child widgets.
        rtl = is_rtl(self.lang)
        try:
            self.root.option_add("*justify", "right" if rtl else "left")
        except Exception:
            pass

    # =================================================================
    # === SPLASH FLOW ===
    # =================================================================
    def _show_splash(self):
        self._container = tk.Frame(self.root, bg=config.MATTE_BLACK)
        self._container.pack(fill="both", expand=True)
        self._splash = SplashView(self._container, self._after_splash,
                                   lang=self.lang)
        self._splash.pack(fill="both", expand=True)

    def _after_splash(self):
        first_run = database.kv_get("first_run", "1")
        onboarded = database.kv_get("onboarded", "0")
        if first_run == "1" or onboarded != "1":
            self._show_onboarding()
        else:
            self._proceed_after_onboarding()

    def _show_onboarding(self):
        database.kv_set("first_run", "0")
        database.kv_set("onboarded", "1")
        # Clear splash
        for child in self._container.winfo_children():
            child.destroy()
        self._onboarding = OnboardingView(self._container, self.lang,
                                            self._proceed_after_onboarding)
        self._onboarding.pack(fill="both", expand=True)

    def _proceed_after_onboarding(self):
        mode = database.kv_get("lock_mode", "none") or "none"
        if mode == "pin":
            self._show_lock()
        else:
            self._show_main()

    def _show_lock(self):
        for child in self._container.winfo_children():
            child.destroy()
        self._lock = LockView(self._container, self.lang, self._show_main)
        self._lock.pack(fill="both", expand=True)

    # =================================================================
    # === MAIN VIEW ===
    # =================================================================
    def _show_main(self):
        # Clear splash/onboarding/lock
        for child in self._container.winfo_children():
            child.destroy()
        # Main view container
        self._main_view = tk.Frame(self._container, bg=config.MATTE_BLACK)
        self._main_view.pack(fill="both", expand=True)
        # Screen container (above the bottom nav)
        screen_wrap = tk.Frame(self._main_view, bg=config.MATTE_BLACK)
        screen_wrap.pack(fill="both", expand=True)
        # Build all screens
        self.screens = {
            "home":     HomeScreen(screen_wrap, self, self.lang),
            "goals":    GoalsScreen(screen_wrap, self, self.lang),
            "stats":    StatsScreen(screen_wrap, self, self.lang),
            "settings": SettingsScreen(screen_wrap, self, self.lang),
        }
        for s in self.screens.values():
            s.pack_forget()
        # Bottom nav
        self._nav = BottomNav(self._main_view, on_tab=self.switch_tab,
                                lang=self.lang, active_tab="home")
        self._nav.pack(side="bottom", fill="x")
        # FAB
        self._fab = FAB(self._main_view, command=self.open_quick_log, lang=self.lang)
        self._fab.place(relx=1.0, rely=1.0, x=-20, y=-80, anchor="se")
        # Show default tab
        self.switch_tab("home")
        # Update title
        self.root.title(config.APP_NAME)
        # Check for due recurring activities
        try:
            from . import recurring
            new_ids = recurring.check_due_recurring()
            if new_ids:
                # Show a toast
                Toast(self.root, f"+{len(new_ids)} recurring", kind="info")
        except Exception:
            pass

    # =================================================================
    # === NAVIGATION ===
    # =================================================================
    def switch_tab(self, tab: str):
        if tab not in self.screens:
            return
        self.current_tab = tab
        # Show/hide screens
        for k, s in self.screens.items():
            if k == tab:
                s.pack(fill="both", expand=True)
                s.render()
            else:
                s.pack_forget()
        # Update nav
        if self._nav:
            self._nav.set_active(tab)
        # Update window title
        if timer_service.is_running():
            e = timer_service.elapsed_sec()
            h = e // 3600
            m = (e % 3600) // 60
            s = e % 60
            txt = f"{h:02d}:{m:02d}:{s:02d} — {timer_service.current_title() or 'Rask'}"
            self.root.title(txt)
        else:
            self.root.title(config.APP_NAME)

    # =================================================================
    # === MODALS ===
    # =================================================================
    def open_quick_log(self):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = QuickLogModal(self.root, self.lang, self._after_modal_saved)

    def open_template_modal(self, template=None):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = TemplateModal(self.root, self.lang,
                                            self._after_modal_saved, template)

    def open_goal_modal(self, goal=None):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = GoalModal(self.root, self.lang, self._after_modal_saved, goal)

    def open_edit_activity_modal(self, activity: dict):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = EditActivityModal(self.root, activity, self.lang,
                                                 self._after_modal_saved)

    def open_search_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = SearchModal(self.root, self.lang,
                                          on_activity_click=self.open_edit_activity_modal)

    def open_recurring_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = RecurringModal(self.root, self.lang, self._after_modal_saved)

    def open_shortcuts_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.focus_set()
            return
        self._active_modal = ShortcutsModal(self.root, self.lang)

    def _after_modal_saved(self):
        # Re-render current screen so new data shows up
        if self.current_tab in self.screens:
            self.screens[self.current_tab].render()

    # =================================================================
    # === LANGUAGE ===
    # =================================================================
    def set_lang(self, lang: str):
        self.lang = lang
        database.kv_set("lang", lang)
        self._apply_direction()
        # Update nav labels
        if self._nav:
            self._nav.set_lang(lang)
        # Update all screens
        for s in self.screens.values():
            s.set_lang(lang)
        # Re-render current
        self.switch_tab(self.current_tab)
        # Toast
        Toast(self.root, t("saved", lang), kind="success")

    # =================================================================
    # === TIMER TICK ===
    # =================================================================
    def _on_timer_tick(self, elapsed: int, running: bool):
        # Update window title
        if running:
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.root.title(f"{h:02d}:{m:02d}:{s:02d} — {timer_service.current_title() or 'Rask'}")
        else:
            self.root.title(config.APP_NAME)
        # Update home screen if visible
        if self.current_tab == "home" and "home" in self.screens:
            try:
                self.screens["home"].on_timer_tick(elapsed, running)
            except Exception:
                pass

    # =================================================================
    # === KEYBOARD SHORTCUTS ===
    # =================================================================
    def _setup_shortcuts(self):
        """Bind keyboard shortcuts from config.SHORTCUTS."""
        for shortcut, action, _desc in config.SHORTCUTS:
            handler = self._make_shortcut_handler(action)
            if handler:
                try:
                    self.root.bind(shortcut, lambda e, _h=handler: _h())
                except Exception:
                    pass

    def _make_shortcut_handler(self, action: str):
        mapping = {
            "switch_home":      lambda: self.switch_tab("home"),
            "switch_goals":     lambda: self.switch_tab("goals"),
            "switch_stats":     lambda: self.switch_tab("stats"),
            "switch_settings":  lambda: self.switch_tab("settings"),
            "quick_log":        self.open_quick_log,
            "toggle_timer":     self._toggle_timer,
            "stop_save_timer":  self._stop_save_timer,
            "export_csv":       self._export_csv,
            "export_pdf":       self._export_pdf,
            "export_backup":    self._export_backup,
            "lock_app":         self._lock_app,
            "settings":         lambda: self.switch_tab("settings"),
            "close_modal":      self._close_modal,
            "undo_last":        self._undo_last,
            "search":           self.open_search_modal,
            "refresh":          lambda: self.switch_tab(self.current_tab),
            "show_shortcuts":   self.open_shortcuts_modal,
        }
        return mapping.get(action)

    def _toggle_timer(self):
        if timer_service.is_running():
            timer_service.pause()
        elif timer_service.elapsed_sec() > 0:
            timer_service.resume()
        else:
            self.open_quick_log()

    def _stop_save_timer(self):
        activity_id = timer_service.stop_and_save()
        if activity_id:
            Toast(self.root, t("quickLogSaved", self.lang), kind="success")
        if self.current_tab in self.screens:
            self.screens[self.current_tab].render()

    def _export_csv(self):
        if "stats" in self.screens:
            self.screens["stats"]._on_export_csv()

    def _export_pdf(self):
        if "stats" in self.screens:
            self.screens["stats"]._on_export_pdf()

    def _export_backup(self):
        if "settings" in self.screens:
            self.switch_tab("settings")

    def _lock_app(self):
        # Re-show the lock screen
        if self._main_view:
            self._main_view.destroy()
            self._main_view = None
        self.screens.clear()
        self._show_lock()

    def _close_modal(self):
        if self._active_modal and self._active_modal.winfo_exists():
            self._active_modal.close()
            self._active_modal = None

    def _undo_last(self):
        """Undo the last activity (delete it)."""
        from .i18n import t
        from tkinter import messagebox
        recent = database.recent_activities(1)
        if not recent:
            Toast(self.root, t("cannotUndo", self.lang), kind="info")
            return
        last = recent[0]
        if messagebox.askyesno(config.APP_NAME, t("confirmUndo", self.lang)):
            database.delete_activity(last["id"])
            Toast(self.root, t("undone", self.lang), kind="info")
            if self.current_tab in self.screens:
                self.screens[self.current_tab].render()

    # =================================================================
    # === RUN ===
    # =================================================================
    def run(self):
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        try:
            database.close_db()
        except Exception:
            pass
        self.root.destroy()
