"""
rask.ui.app
===========

Main application controller for the Rask desktop app.

This module ties together every other package — services, screens,
dialogs, widgets, event-bus, database — into a single
:class:`RaskApp` class that owns the top-level CTk window and
manages the application lifecycle.

Responsibilities
----------------
1. **Window + theme setup** — create the 540×900 CTk root, centre it
   on screen, set title / icon, apply the gold-on-dark theme.

2. **Service initialisation** — open the DB, call
   :func:`rask.services.init_all`, hand the Tk root to the timer and
   reminder services so their ``after()`` loops can fire.

3. **Boot flow** — splash (2.2 s) → onboarding (first run only) →
   lock (if PIN/biometric enabled) → main app.

4. **Main view** — scrollable content area + bottom nav + FAB +
   per-screen switching with a 250 ms slide animation.

5. **Dialog dispatchers** — one ``open_*()`` method per dialog
   (quick-log, edit-activity, goal, template, reminder, category,
   pin-setup, backup, export, filter, compare, voice, search,
   shortcuts).  These are the methods called by screens and keyboard
   shortcuts.

6. **Keyboard shortcuts** — Ctrl+N / F / T / S / B / E / , / 1-4 /
   L, ``?``, ``Esc``.  All routed through a single ``_on_key`` handler.

7. **Auto-lock** — schedule a periodic idle check based on
   :meth:`settings_service.auto_lock_seconds`.

8. **Background tasks** — reminder scheduler (handled by the service),
   recurring-processor (every 5 min), auto-backup checker (every
   hour), total-launches counter (on startup).

9. **Event-bus subscriptions** — UI toast, tab change, language /
   theme change, badge unlocked, reminder triggered, timer started /
   stopped.

10. **Cleanup** — close DB, save state, cancel timers on quit.

The class is intentionally a **god-object**: in a desktop GUI app
that needs to be reachable from every screen and dialog, a single
coordinator is the simplest correct architecture.  Internal state
is kept on private attributes (``_state_*``) to keep the public
API surface small.

Typical usage
-------------
::

    from rask.ui import RaskApp
    app = RaskApp()
    app.run()
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover — CTk may be missing in CI
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from .. import config
from .. import i18n
from .. import database as db
from ..core import event_bus
from ..core import helpers
from ..core.logging_utils import get_logger, log_exception, setup_logging
from ..core.time_utils import now_iso_local, today_iso, format_duration
from ..services import (
    activity_service, goal_service, streak_service, stats_service,
    backup_service, export_service, voice_service, reminder_service,
    template_service, badge_service, recurring_service, timer_service,
    settings_service,
)

_log = get_logger("ui.app")


__all__ = ["RaskApp"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

# Bottom-nav tab keys (in display order, RTL-aware).
_TAB_KEYS: Tuple[str, ...] = ("home", "goals", "stats", "settings")

# Mapping from tab key -> (icon name, i18n key).
_TAB_META: Dict[str, Tuple[str, str]] = {
    "home":     ("home",     "home"),
    "goals":    ("goals",    "goals"),
    "stats":    ("stats",    "stats"),
    "settings": ("settings", "settings"),
}

# Slide animation duration (ms) for tab switches.
_SLIDE_DURATION_MS: int = 250

# Auto-launches counter — bumped once per process start.
_LAUNCH_COUNTER_KEY: str = "total_launches"

# Last-activity-timestamp key — used for auto-lock idle detection.
_LAST_ACTIVITY_KEY: str = "last_activity_iso"

# Persisted current-tab key — restored on next launch.
_CURRENT_TAB_KEY: str = "current_tab"


# =============================================================================
# === RaskApp                                                                  ===
# =============================================================================

class RaskApp:
    """The main Rask application controller.

    A single instance owns the CTk root window, the active screen,
    the bottom navigation, the FAB, the toast manager, the
    dialog-stack, and all event-bus subscriptions.  Construct with
    no arguments and call :meth:`run` to enter the main loop.

    The class is safe to instantiate even when CustomTkinter is
    missing — :meth:`__init__` raises :class:`RuntimeError` in that
    case so callers can fall back to a CLI-only mode.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        """Construct the app shell and prepare the boot flow.

        Side-effects in order:
          1. Verify CustomTkinter is available (raise otherwise).
          2. Configure logging.
          3. Create the CTk root window + theme.
          4. Initialise services (DB + init_all).
          5. Hand the Tk root to the timer + reminder services.
          6. Load settings (language / theme) and apply RTL.
          7. Set up event-bus subscriptions.
          8. Set up keyboard shortcuts.
          9. Bump the total-launches counter.
         10. Schedule background tasks.
         11. Show the splash screen (boot flow continues in
             :meth:`_after_splash`).

        The constructor does **not** enter the main loop — call
        :meth:`run` separately.
        """
        if not _CTK_OK:
            raise RuntimeError(
                "CustomTkinter is not installed — install it with "
                "`pip install customtkinter>=5.2.2`")
        # --- Internal state ---
        self._root: Optional[ctk.CTk] = None
        self._content_frame: Optional[ctk.CTkFrame] = None
        self._nav: Optional[Any] = None  # BottomNav
        self._fab: Optional[Any] = None  # FabButton
        self._current_tab: str = "home"
        self._current_screen: Optional[ctk.CTkFrame] = None
        self._splash: Optional[ctk.CTkFrame] = None
        self._onboarding: Optional[ctk.CTkFrame] = None
        self._lock_view: Optional[ctk.CTkFrame] = None
        self._search_screen: Optional[ctk.CTkFrame] = None
        self._shortcuts_screen: Optional[ctk.CTkFrame] = None
        self._active_dialogs: List[Any] = []
        self._subscriptions: List[Tuple[str, Callable[..., Any]]] = []
        self._bg_jobs: List[Tuple[str, int]] = []  # (label, after_id)
        self._lang: str = settings_service.language() or config.DEFAULT_LANG
        self._theme: str = settings_service.theme() or config.DEFAULT_THEME
        self._locked: bool = False
        self._quitting: bool = False
        self._last_activity_ts: float = time.time()
        self._auto_lock_check_handle: Optional[str] = None
        self._slide_animation_handle: Optional[str] = None

        # --- Build the window ---
        self._setup_window()
        self._setup_content_area()
        # --- Apply theme + language + direction ---
        self._apply_theme()
        self._apply_direction()
        # --- Set up event-bus subscriptions + shortcuts ---
        self._setup_events()
        self._setup_shortcuts()
        # --- Set up background tasks ---
        self._setup_background_tasks()
        # --- Track launches ---
        self._increment_launch_counter()
        # --- Boot flow: show splash ---
        self._show_splash()

    # ------------------------------------------------------------------
    # Window + content area setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        """Create the CTk root window and apply base geometry.

        Sets the title, size, minimum size, and centres the window
        on the primary monitor.  Tries to set the window icon from
        ``rask/assets/icon.png`` if present (best-effort, ignored
        on failure).
        """
        try:
            ctk.set_appearance_mode("dark")
            try:
                ctk.set_default_color_theme("dark-blue")
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        self._root = ctk.CTk()
        self._root.title(
            f"{config.APP_NAME} — {config.APP_TAGLINE} "
            f"v{config.APP_VERSION}")
        try:
            self._root.geometry(
                f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
            self._root.minsize(
                config.WINDOW_MIN_WIDTH,
                config.WINDOW_MIN_HEIGHT)
            self._root.resizable(True, True)
        except Exception:  # noqa: BLE001
            pass
        # Try to set the icon (best-effort)
        try:
            icon_path = Path(__file__).resolve().parents[1] / "assets" / "icon.png"
            if icon_path.is_file():
                self._root.iconbitmap(str(icon_path))
        except Exception:  # noqa: BLE001
            pass
        # Centre on screen
        self._center_on_screen()
        # Window close handler
        try:
            self._root.protocol("WM_DELETE_WINDOW", self.quit_app)
        except Exception:  # noqa: BLE001
            pass
        # Apply theme manager
        from .widgets.theme import theme
        theme.apply(self._root)
        theme.register_fonts()
        # Configure root grid (content + bottom nav rows)
        self._root.grid_columnconfigure(0, weight=1)
        self._root.grid_rowconfigure(0, weight=1)  # content
        # row 1 is the bottom nav (fixed height)

    def _center_on_screen(self) -> None:
        """Centre the main window on the primary monitor."""
        if self._root is None:
            return
        try:
            self._root.update_idletasks()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = max(0, (sw - config.WINDOW_WIDTH) // 2)
            y = max(0, (sh - config.WINDOW_HEIGHT) // 2)
            self._root.geometry(f"+{x}+{y}")
        except Exception:  # noqa: BLE001
            pass

    def _setup_content_area(self) -> None:
        """Create the main content frame + bottom nav + FAB.

        Layout (grid):

            row 0: content_frame (stretches, fills remaining height)
            row 1: bottom nav (fixed height = config.BOTTOM_NAV_HEIGHT)

        The FAB is *placed* (not gridded) on top of the content frame
        so it can float above the bottom-right (or bottom-left in RTL)
        corner.
        """
        if self._root is None:
            return
        # Content frame — fills the area above the bottom nav
        self._content_frame = ctk.CTkFrame(
            self._root,
            fg_color=config.MATTE_BLACK,
            corner_radius=0,
        )
        self._content_frame.grid(row=0, column=0, sticky="nsew")
        self._content_frame.grid_columnconfigure(0, weight=1)
        self._content_frame.grid_rowconfigure(0, weight=1)
        # Bottom nav
        from .widgets.bottom_nav import BottomNav
        nav_items = []
        for key in _TAB_KEYS:
            icon, i18n_key = _TAB_META[key]
            label = i18n.t(i18n_key, self._lang)
            nav_items.append({"key": key, "icon": icon, "label": label})
        self._nav = BottomNav(
            self._root,
            items=nav_items,
            active_tab=self._current_tab,
            on_tab=self._on_nav_tab,
            fab_slot=True,
            lang=self._lang,
            height=config.BOTTOM_NAV_HEIGHT,
        )
        self._nav.grid(row=1, column=0, sticky="ew")
        # FAB — placed inside the content_frame so it floats above the
        # active screen.
        from .widgets.buttons import FabButton
        self._fab = FabButton(
            self._content_frame,
            icon_name="plus",
            command=self._on_fab,
            lang=self._lang,
        )
        # Position the FAB after the window is mapped
        try:
            self._root.after(150, self._place_fab)
            self._root.bind("<Configure>", lambda _e: self._place_fab(),
                             add="+")
        except Exception:  # noqa: BLE001
            pass

    def _place_fab(self) -> None:
        """Position the FAB in the bottom-trailing corner above the nav."""
        if self._fab is None or self._content_frame is None:
            return
        try:
            self._content_frame.update_idletasks()
            w = max(1, self._content_frame.winfo_width())
            h = max(1, self._content_frame.winfo_height())
            fab_size = config.FAB_SIZE
            margin = config.FAB_MARGIN
            rtl = i18n.is_rtl(self._lang)
            # In RTL, "trailing" = left; in LTR, "trailing" = right.
            x = margin if rtl else w - fab_size - margin
            y = h - fab_size - 16
            self._fab.place(x=x, y=y)
            self._fab.lift()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Boot flow: splash → onboarding → lock → main
    # ------------------------------------------------------------------

    def _show_splash(self) -> None:
        """Show the splash screen for ~2.2 s, then call :meth:`_after_splash`."""
        if self._root is None or self._content_frame is None:
            return
        # Hide nav + FAB while splash is up
        try:
            self._nav.grid_remove()
            self._fab.place_forget()
        except Exception:  # noqa: BLE001
            pass
        from .screens.splash_screen import SplashView
        self._splash = SplashView(
            self._root,
            app=self,
            lang=self._lang,
            on_complete=self._after_splash,
        )
        # Place splash above content_frame
        self._splash.grid(row=0, column=0, sticky="nsew")
        # Bring to front
        try:
            self._splash.lift()
        except Exception:  # noqa: BLE001
            pass

    def _after_splash(self) -> None:
        """Called once the splash animation finishes.

        Tears down the splash view and continues the boot flow:
        onboarding (first run) → lock (if enabled) → main.
        """
        # Destroy splash
        if self._splash is not None:
            try:
                self._splash.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._splash = None
        # Mark first_run as cleared if user has finished onboarding
        # (this is set by the onboarding dialog itself).
        if not settings_service.is_onboarded():
            self._show_onboarding()
        elif self._should_lock():
            self._show_lock()
        else:
            self._show_main()

    def _show_onboarding(self) -> None:
        """Show the 3-slide onboarding flow.

        On completion, marks the user as onboarded and proceeds to
        the lock-or-main branch.
        """
        if self._root is None:
            return
        try:
            from .screens.onboarding_screen import OnboardingView
            self._onboarding = OnboardingView(
                self._root,
                app=self,
                lang=self._lang,
                on_complete=self._after_onboarding,
            )
            self._onboarding.grid(row=0, column=0, sticky="nsew")
            try:
                self._onboarding.lift()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            # Fallback: skip onboarding
            settings_service.set_onboarded(True)
            self._after_onboarding()

    def _after_onboarding(self) -> None:
        """Tear down onboarding, mark onboarded, continue boot flow."""
        if self._onboarding is not None:
            try:
                self._onboarding.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._onboarding = None
        try:
            settings_service.set_onboarded(True)
            settings_service.clear_first_run()
        except Exception:  # noqa: BLE001
            pass
        # Reload lang/theme in case the onboarding dialog changed them
        self._lang = settings_service.language()
        self._theme = settings_service.theme()
        self._apply_theme()
        self._apply_direction()
        if self._should_lock():
            self._show_lock()
        else:
            self._show_main()

    def _show_lock(self) -> None:
        """Show the full-screen PIN pad.

        On successful unlock, transitions to the main view.
        """
        if self._root is None:
            return
        self._locked = True
        # Hide nav + FAB
        try:
            if self._nav is not None:
                self._nav.grid_remove()
            if self._fab is not None:
                self._fab.place_forget()
        except Exception:  # noqa: BLE001
            pass
        try:
            from .screens.lock_screen import LockView
            pin_hash = settings_service.pin_hash()
            self._lock_view = LockView(
                self._root,
                app=self,
                lang=self._lang,
                pin_hash=pin_hash,
                lock_mode=settings_service.lock_mode(),
                on_unlock=self._after_unlock,
                on_forgot=self._on_forgot_pin,
                biometric_available=False,
            )
            self._lock_view.grid(row=0, column=0, sticky="nsew")
            try:
                self._lock_view.lift()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            # Fallback: skip lock
            self._after_unlock()

    def _after_unlock(self) -> None:
        """Tear down lock view, show main app."""
        if self._lock_view is not None:
            try:
                self._lock_view.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._lock_view = None
        self._locked = False
        self._last_activity_ts = time.time()
        self._show_main()

    def _on_forgot_pin(self) -> None:
        """Handle the "Forgot PIN" link — offer to wipe & re-onboard."""
        msg = (i18n.t("forgotPinMsg", self._lang)
                if i18n.t("forgotPinMsg", self._lang) != "forgotPinMsg"
                else "فراموشی پین باعث پاک شدن داده‌ها می‌شود. ادامه می‌دهی؟")
        self.confirm(
            msg,
            on_yes=self._do_forgot_pin_wipe,
            danger=True,
        )

    def _do_forgot_pin_wipe(self) -> None:
        """Wipe the database + PIN hash, then restart onboarding."""
        try:
            conn = db.get_conn()
            for t in ("activity_tags", "tags", "activities", "sessions",
                       "recurring", "reminders", "badges", "templates",
                       "streaks", "goals", "categories", "settings", "kv"):
                try:
                    conn.execute(f"DELETE FROM {t}")
                except Exception:  # noqa: BLE001
                    pass
            conn.commit()
            db.open_db()  # re-seed defaults
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        # Tear down lock view, show onboarding
        if self._lock_view is not None:
            try:
                self._lock_view.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._lock_view = None
        self._locked = False
        self._show_onboarding()

    def _should_lock(self) -> bool:
        """Return True if the app should show the lock screen at boot."""
        try:
            mode = settings_service.lock_mode()
            if mode in ("pin", "biometric"):
                return bool(settings_service.pin_hash())
        except Exception:  # noqa: BLE001
            pass
        return False

    def _show_main(self) -> None:
        """Show the main app: nav + FAB + the current tab's screen."""
        # Restore nav + FAB
        try:
            if self._nav is not None:
                self._nav.grid()
            if self._fab is not None:
                self._place_fab()
        except Exception:  # noqa: BLE001
            pass
        # Restore last-used tab (or default to home)
        try:
            saved = db.kv_get(_CURRENT_TAB_KEY)
            if saved and saved in _TAB_KEYS:
                self._current_tab = saved
        except Exception:  # noqa: BLE001
            pass
        # Update nav indicator
        try:
            if self._nav is not None:
                self._nav.set_active(self._current_tab)
        except Exception:  # noqa: BLE001
            pass
        # Render the screen
        self._render_screen(self._current_tab, animate=False)
        # Start auto-lock idle check
        self._schedule_auto_lock_check()

    # ------------------------------------------------------------------
    # Tab switching + screen rendering
    # ------------------------------------------------------------------

    def switch_tab(self, tab: str) -> None:
        """Switch to a different bottom-nav tab.

        Parameters
        ----------
        tab
            One of ``"home"``, ``"goals"``, ``"stats"``, ``"settings"``.
            Unknown values are silently ignored.

        Side-effects:
          * Tears down the current screen (calls ``destroy()`` if it
            has one).
          * Builds the new screen with a 250 ms slide animation.
          * Publishes ``ui.tab_changed`` on the event bus.
          * Persists the new tab to the ``kv`` store (so it can be
            restored on next launch).
        """
        if tab not in _TAB_KEYS:
            _log.warning("switch_tab: unknown tab %r", tab)
            return
        if tab == self._current_tab and self._current_screen is not None:
            # Same tab — just refresh
            self._refresh_current_screen()
            return
        self._render_screen(tab, animate=True)
        # Update nav indicator
        try:
            if self._nav is not None:
                self._nav.set_active(tab)
        except Exception:  # noqa: BLE001
            pass
        # Persist + publish
        try:
            db.kv_set(_CURRENT_TAB_KEY, tab)
        except Exception:  # noqa: BLE001
            pass
        event_bus.bus.publish("ui.tab_changed", {"tab": tab,
                                                   "previous": self._current_tab})
        self._current_tab = tab
        self._bump_activity()

    def _on_nav_tab(self, tab: str) -> None:
        """BottomNav callback — just delegates to :meth:`switch_tab`."""
        self.switch_tab(tab)

    def _render_screen(self, tab: str, *, animate: bool = True) -> None:
        """Tear down the current screen and build the new one.

        When ``animate`` is True, the new screen slides in from the
        trailing edge (250 ms ease-out).  When False (boot, tab
        restoration), the screen appears instantly.
        """
        if self._content_frame is None:
            return
        # Tear down current screen
        if self._current_screen is not None:
            try:
                # Slide-out animation
                if animate and self._slide_animation_handle is None:
                    self._slide_out(self._current_screen)
                else:
                    self._current_screen.destroy()
            except Exception:  # noqa: BLE001
                try:
                    self._current_screen.destroy()
                except Exception:  # noqa: BLE001
                    pass
            self._current_screen = None
        # Build the new screen
        try:
            from .screens import SCREENS
            screen_cls = SCREENS.get(tab)
            if screen_cls is None:
                _log.error("No screen class for tab %r", tab)
                return
            new_screen = screen_cls(
                self._content_frame,
                app=self,
                lang=self._lang,
            )
            new_screen.grid(row=0, column=0, sticky="nsew")
            self._current_screen = new_screen
            # Slide-in animation
            if animate:
                self._slide_in(new_screen)
            # Lift FAB above the new screen
            try:
                if self._fab is not None:
                    self._fab.lift()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"tab": tab})
            # Show an error toast if we can
            try:
                self.show_toast(
                    f"Could not load {tab} screen: {exc}",
                    kind="error")
            except Exception:  # noqa: BLE001
                pass
        self._current_tab = tab

    def _slide_in(self, widget: ctk.CTkFrame) -> None:
        """Animate a slide-in from the trailing edge (250 ms ease-out)."""
        if widget is None or self._content_frame is None:
            return
        try:
            self._content_frame.update_idletasks()
            w = max(1, self._content_frame.winfo_width())
            rtl = i18n.is_rtl(self._lang)
            # In RTL, trailing edge = right; LTR = left.
            start_x = w if not rtl else -w
            widget.place(x=start_x, y=0)
            widget.lift()
            self._animate_slide(widget, start_x, 0, _SLIDE_DURATION_MS,
                                 in_=True)
        except Exception:  # noqa: BLE001
            try:
                widget.place(x=0, y=0)
            except Exception:  # noqa: BLE001
                pass

    def _slide_out(self, widget: ctk.CTkFrame) -> None:
        """Animate a slide-out to the leading edge (200 ms ease-in)."""
        if widget is None or self._content_frame is None:
            return
        try:
            self._content_frame.update_idletasks()
            w = max(1, self._content_frame.winfo_width())
            rtl = i18n.is_rtl(self._lang)
            # In RTL, leading = left; LTR = right.
            end_x = -w if rtl else w
            self._animate_slide(widget, 0, end_x, 200, in_=False,
                                 on_done=lambda: self._safe_destroy(widget))
        except Exception:  # noqa: BLE001
            try:
                widget.destroy()
            except Exception:  # noqa: BLE001
                pass

    def _animate_slide(
        self,
        widget: ctk.CTkFrame,
        start_x: int,
        end_x: int,
        duration_ms: int,
        *,
        in_: bool = True,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """Animate ``widget`` from ``start_x`` to ``end_x`` over ``duration_ms``.

        Uses :func:`helpers.ease_out_cubic` for ``in_`` and
        :func:`helpers.ease_in_cubic` for slide-out.
        """
        if widget is None or self._root is None:
            if on_done:
                on_done()
            return
        steps = max(4, duration_ms // 16)
        state = {"step": 0, "total": steps}

        def tick() -> None:
            try:
                state["step"] += 1
                t = state["step"] / state["total"]
                t = max(0.0, min(1.0, t))
                eased = (helpers.ease_out_cubic(t) if in_
                          else helpers.ease_in_cubic(t))
                cur_x = int(start_x + (end_x - start_x) * eased)
                widget.place(x=cur_x, y=0)
                if state["step"] < state["total"]:
                    self._slide_animation_handle = self._root.after(16, tick)
                else:
                    self._slide_animation_handle = None
                    if in_:
                        # Switch from place to grid so the widget
                        # properly fills the frame.
                        try:
                            widget.place_forget()
                            widget.grid(row=0, column=0, sticky="nsew")
                        except Exception:  # noqa: BLE001
                            pass
                    if on_done:
                        on_done()
            except Exception:  # noqa: BLE001
                self._slide_animation_handle = None
                if on_done:
                    on_done()

        # Cancel any in-flight animation
        if self._slide_animation_handle is not None:
            try:
                self._root.after_cancel(self._slide_animation_handle)
            except Exception:  # noqa: BLE001
                pass
            self._slide_animation_handle = None
        try:
            self._root.after(0, tick)
        except Exception:  # noqa: BLE001
            if on_done:
                on_done()

    def _safe_destroy(self, widget: Any) -> None:
        """Destroy a widget, swallowing any exception."""
        try:
            widget.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_current_screen(self) -> None:
        """Call ``refresh()`` on the current screen if it has one."""
        if self._current_screen is None:
            return
        try:
            refresh = getattr(self._current_screen, "refresh", None)
            if callable(refresh):
                refresh()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def reload_ui(self) -> None:
        """Reload the current screen from scratch.

        Used by settings changes (language / theme / font scale) that
        require a full rebuild of the visible UI.
        """
        self._lang = settings_service.language()
        self._theme = settings_service.theme()
        self._apply_theme()
        self._apply_direction()
        # Rebuild nav labels (in case language changed)
        self._rebuild_nav()
        # Rebuild current screen
        try:
            if self._current_screen is not None:
                self._current_screen.destroy()
                self._current_screen = None
        except Exception:  # noqa: BLE001
            pass
        self._render_screen(self._current_tab, animate=False)

    def _rebuild_nav(self) -> None:
        """Rebuild the bottom nav with the current language's labels."""
        if self._nav is None or self._root is None:
            return
        try:
            # Destroy old nav
            self._nav.destroy()
        except Exception:  # noqa: BLE001
            pass
        from .widgets.bottom_nav import BottomNav
        nav_items = []
        for key in _TAB_KEYS:
            icon, i18n_key = _TAB_META[key]
            label = i18n.t(i18n_key, self._lang)
            nav_items.append({"key": key, "icon": icon, "label": label})
        self._nav = BottomNav(
            self._root,
            items=nav_items,
            active_tab=self._current_tab,
            on_tab=self._on_nav_tab,
            fab_slot=True,
            lang=self._lang,
            height=config.BOTTOM_NAV_HEIGHT,
        )
        self._nav.grid(row=1, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # FAB handler
    # ------------------------------------------------------------------

    def _on_fab(self) -> None:
        """FAB tap — open the quick-log dialog."""
        self._bump_activity()
        self.open_quick_log()

    # ------------------------------------------------------------------
    # Dialog dispatchers
    # ------------------------------------------------------------------
    # Each method here is called by screens and/or keyboard shortcuts.
    # They all defer-import the dialog class so the app shell itself
    # does not pay the import cost until a dialog is actually needed.

    def open_quick_log(self) -> None:
        """Open the bottom-sheet quick-log dialog (FAB tap).

        Pre-fills the title/category/duration from any active voice
        result or template selection.  On save, publishes
        ``activity.added`` (handled by the service) and shows a
        success toast.
        """
        if self._root is None:
            return
        try:
            from .dialogs.quick_log_dialog import QuickLogDialog
            dlg = QuickLogDialog(
                self._root,
                lang=self._lang,
                on_result=lambda r: self._on_quick_log_result(r),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open quick log: {exc}",
                             kind="error")

    def _on_quick_log_result(self, result: Any) -> None:
        """Handle the result of a quick-log dialog (success / cancel)."""
        if not result:
            return
        try:
            if isinstance(result, dict):
                title = result.get("title") or ""
                if result.get("stopwatch_mode"):
                    msg = (i18n.t("recording", self._lang)
                            if i18n.t("recording", self._lang) != "recording"
                            else f"در حال ضبط: {title}")
                    self.show_toast(msg, kind="info")
                elif title:
                    msg = (i18n.t("activitySaved", self._lang)
                            if i18n.t("activitySaved", self._lang) != "activitySaved"
                            else "فعالیت ذخیره شد")
                    self.show_toast(msg, kind="success")
        except Exception:  # noqa: BLE001
            pass
        self._bump_activity()

    def open_activity_dialog(self, activity_id: int) -> None:
        """Open the edit-activity dialog for an existing activity.

        Alias for :meth:`open_edit_activity` (the home / search
        screens call this name).
        """
        self.open_edit_activity(activity_id)

    def open_edit_activity(self, activity_id: int) -> None:
        """Open the edit-activity dialog.

        Parameters
        ----------
        activity_id
            The DB id of the activity to edit.
        """
        if self._root is None:
            return
        try:
            activity = activity_service.get(int(activity_id))
            if activity is None:
                self.show_toast(
                    f"Activity {activity_id} not found", kind="error")
                return
            from .dialogs.edit_activity_dialog import EditActivityDialog
            dlg = EditActivityDialog(
                self._root,
                activity=activity,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"activity_id": activity_id})
            self.show_toast(f"Could not open activity: {exc}",
                             kind="error")

    def open_goal_dialog(self, goal_id: Optional[int] = None) -> None:
        """Open the create/edit goal dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.goal_dialog import GoalDialog
            dlg = GoalDialog(
                self._root,
                goal_id=goal_id,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"goal_id": goal_id})
            self.show_toast(f"Could not open goal dialog: {exc}",
                             kind="error")

    def open_template_dialog(self, template_id: Optional[int] = None) -> None:
        """Open the create/edit template dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.template_dialog import TemplateDialog
            dlg = TemplateDialog(
                self._root,
                template_id=template_id,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"template_id": template_id})
            self.show_toast(f"Could not open template dialog: {exc}",
                             kind="error")

    def open_reminder_dialog(self, reminder_id: Optional[int] = None) -> None:
        """Open the create/edit reminder dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.reminder_dialog import ReminderDialog
            dlg = ReminderDialog(
                self._root,
                reminder_id=reminder_id,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"reminder_id": reminder_id})
            self.show_toast(f"Could not open reminder dialog: {exc}",
                             kind="error")

    def open_category_dialog(self, category_id: Optional[int] = None) -> None:
        """Open the create/edit category dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.category_dialog import CategoryDialog
            dlg = CategoryDialog(
                self._root,
                category_id=category_id,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"category_id": category_id})
            self.show_toast(f"Could not open category dialog: {exc}",
                             kind="error")

    def open_pin_setup(self, mode: str = "setup") -> None:
        """Open the PIN setup dialog (mode = setup / change)."""
        if self._root is None:
            return
        try:
            from .dialogs.pin_setup_dialog import PinSetupDialog
            dlg = PinSetupDialog(
                self._root,
                mode=mode,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"mode": mode})
            self.show_toast(f"Could not open PIN setup: {exc}",
                             kind="error")

    def open_backup_dialog(self, mode: str = "backup") -> None:
        """Open the backup / restore dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.backup_dialog import BackupDialog
            dlg = BackupDialog(
                self._root,
                mode=mode,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"mode": mode})
            self.show_toast(f"Could not open backup dialog: {exc}",
                             kind="error")

    def open_export_dialog(self) -> None:
        """Open the export (PDF / CSV / JSON / PNG) dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.export_dialog import ExportDialog
            dlg = ExportDialog(
                self._root,
                lang=self._lang,
                on_result=lambda r: self._refresh_current_screen(),
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open export dialog: {exc}",
                             kind="error")

    def open_filter_dialog(self, on_apply: Optional[Callable] = None,
                              initial: Any = None) -> None:
        """Open the activity-filter bottom sheet.

        ``on_apply`` is called with the new :class:`FilterState` when
        the user taps Apply.
        """
        if self._root is None:
            return
        try:
            from .dialogs.filter_dialog import FilterDialog
            dlg = FilterDialog(
                self._root,
                initial=initial,
                lang=self._lang,
                on_result=on_apply,
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open filter: {exc}", kind="error")

    # Aliases used by stats_screen / search_screen
    def open_filter_sheet(self, initial: Any = None,
                            on_apply: Optional[Callable] = None) -> None:
        """Alias for :meth:`open_filter_dialog` (matches stats_screen API)."""
        self.open_filter_dialog(on_apply=on_apply, initial=initial)

    def open_compare_dialog(self) -> None:
        """Open the period-comparison dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.compare_dialog import CompareDialog
            dlg = CompareDialog(
                self._root,
                lang=self._lang,
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open compare dialog: {exc}",
                             kind="error")

    def open_voice_dialog(self) -> None:
        """Open the voice (speech-to-text) input dialog."""
        if self._root is None:
            return
        try:
            from .dialogs.voice_dialog import VoiceDialog
            dlg = VoiceDialog(
                self._root,
                lang=self._lang,
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            # Voice often unavailable — friendlier message
            if not voice_service.is_available():
                self.show_toast(
                    "Voice recognition not available — install "
                    "SpeechRecognition and pyaudio",
                    kind="warning")
            else:
                self.show_toast(f"Could not open voice dialog: {exc}",
                                 kind="error")

    def open_date_picker(self, on_select: Optional[Callable] = None) -> None:
        """Open the date-picker bottom sheet.

        ``on_select`` is called with ``(start_iso, end_iso)`` when the
        user confirms a range.
        """
        if self._root is None:
            return
        try:
            from .widgets.date_picker import DatePicker
            dlg = DatePicker(
                self._root,
                lang=self._lang,
                on_select=on_select,
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open date picker: {exc}",
                             kind="error")

    def open_search(self) -> None:
        """Open the full-screen search overlay."""
        if self._root is None or self._content_frame is None:
            return
        if self._search_screen is not None:
            try:
                self._search_screen.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._search_screen = None
        try:
            from .screens.search_screen import SearchScreen
            self._search_screen = SearchScreen(
                self._root,
                app=self,
                lang=self._lang,
            )
            self._search_screen.grid(row=0, column=0, sticky="nsew")
            try:
                self._search_screen.lift()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open search: {exc}", kind="error")

    def close_search(self) -> None:
        """Tear down the search overlay."""
        if self._search_screen is not None:
            try:
                self._search_screen.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._search_screen = None

    def open_shortcuts(self) -> None:
        """Open the keyboard-shortcuts help screen."""
        if self._root is None:
            return
        if self._shortcuts_screen is not None:
            try:
                self._shortcuts_screen.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._shortcuts_screen = None
        try:
            from .screens.shortcuts_screen import ShortcutsScreen
            self._shortcuts_screen = ShortcutsScreen(
                self._root,
                app=self,
                lang=self._lang,
            )
            self._shortcuts_screen.grid(row=0, column=0, sticky="nsew")
            try:
                self._shortcuts_screen.lift()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open shortcuts: {exc}",
                             kind="error")

    def close_shortcuts(self) -> None:
        """Tear down the shortcuts screen."""
        if self._shortcuts_screen is not None:
            try:
                self._shortcuts_screen.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._shortcuts_screen = None

    def open_reminders_screen(self) -> None:
        """Switch to the reminders tab (used by settings screen)."""
        # The reminders screen isn't part of the bottom nav, so we
        # render it as a temporary overlay.
        if self._root is None:
            return
        try:
            from .screens.reminders_screen import RemindersScreen
            # Reuse the content_frame
            old = self._current_screen
            screen = RemindersScreen(
                self._content_frame,
                app=self,
                lang=self._lang,
            )
            screen.grid(row=0, column=0, sticky="nsew")
            self._current_screen = screen
            try:
                if old is not None:
                    old.destroy()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not open reminders: {exc}",
                             kind="error")

    def show_export_dialog(self, *args: Any, **kwargs: Any) -> None:
        """Alias for :meth:`open_export_dialog` (matches stats_screen API)."""
        self.open_export_dialog()

    # ------------------------------------------------------------------
    # Confirm + toast helpers
    # ------------------------------------------------------------------

    def show_toast(
        self,
        message: str,
        kind: str = "info",
        duration: int = 3500,
    ) -> None:
        """Show a non-blocking toast notification at the top of the window.

        Parameters
        ----------
        message
            Text to display.  Multi-line is supported.
        kind
            One of ``"info"``, ``"success"``, ``"warning"``,
            ``"error"``, ``"achievement"``.
        duration
            How long to display (ms).  Default 3500.
        """
        if not message or self._root is None:
            return
        try:
            from .widgets.toasts import Toast
            Toast.show(
                self._root, message, kind=kind,
                duration=duration, lang=self._lang)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"message": message, "kind": kind})

    def confirm(
        self,
        message: str,
        on_yes: Optional[Callable[[], Any]] = None,
        on_no: Optional[Callable[[], Any]] = None,
        *,
        danger: bool = False,
        title: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Show a confirmation dialog.

        Parameters
        ----------
        message
            The main prompt.
        on_yes
            Callback invoked when the user confirms.
        on_no
            Callback invoked when the user cancels (optional).
        danger
            If True, use the red "danger" style (used for destructive
            actions like delete / wipe).
        title
            Optional dialog title (default: localised "Confirm").
        detail
            Optional secondary text shown below the message.
        """
        if self._root is None:
            return
        try:
            from .dialogs.confirm_dialog import ConfirmDialog
            title_str = title or (
                i18n.t("confirm", self._lang)
                if i18n.t("confirm", self._lang) != "confirm"
                else "تأیید")
            dlg = ConfirmDialog(
                self._root,
                title=title_str,
                message=message,
                detail=detail,
                danger=danger,
                on_result=lambda r: self._on_confirm_result(
                    r, on_yes, on_no),
                lang=self._lang,
            )
            self._track_dialog(dlg)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            # Fallback to a standard messagebox
            try:
                from tkinter import messagebox
                if messagebox.askyesno(title_str, message):
                    if on_yes:
                        on_yes()
                else:
                    if on_no:
                        on_no()
            except Exception:  # noqa: BLE001
                pass

    def _on_confirm_result(
        self,
        result: Any,
        on_yes: Optional[Callable[[], Any]],
        on_no: Optional[Callable[[], Any]],
    ) -> None:
        """Dispatch a confirmation dialog's result to the right callback."""
        confirmed = False
        if isinstance(result, dict):
            confirmed = bool(result.get("confirmed"))
        elif result is True:
            confirmed = True
        if confirmed and on_yes:
            try:
                on_yes()
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
        elif not confirmed and on_no:
            try:
                on_no()
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})

    def confirm_delete(
        self,
        message: str,
        on_confirm: Optional[Callable[[], Any]] = None,
    ) -> None:
        """Alias for :meth:`confirm` with ``danger=True``.

        Matches the API used by goals_screen / templates_screen /
        categories_screen / reminders_screen / backup_screen /
        settings_screen.
        """
        self.confirm(message, on_yes=on_confirm, danger=True)

    # ------------------------------------------------------------------
    # Lock app
    # ------------------------------------------------------------------

    def lock_app(self) -> None:
        """Manually lock the app (Ctrl+L)."""
        if not self._should_lock():
            self.show_toast(
                "No PIN set — open Settings → Privacy to enable lock.",
                kind="warning")
            return
        # Tear down current screen
        if self._current_screen is not None:
            try:
                self._current_screen.destroy()
                self._current_screen = None
            except Exception:  # noqa: BLE001
                pass
        self._show_lock()

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def quit_app(self) -> None:
        """Confirm quit, save state, and close the window.

        Called by:
          * The window's WM_DELETE_WINDOW protocol handler
          * The ``Ctrl+Q`` shortcut (registered in :meth:`_setup_shortcuts`)
        """
        if self._quitting:
            return
        self._quitting = True
        # Confirm quit
        try:
            from tkinter import messagebox
            if not messagebox.askyesno(
                config.APP_NAME,
                "Exit Rask?",
                default=messagebox.NO,
                icon="question"):
                self._quitting = False
                return
        except Exception:  # noqa: BLE001
            pass
        # Save state
        try:
            db.kv_set(_CURRENT_TAB_KEY, self._current_tab)
            db.kv_set(_LAST_ACTIVITY_KEY, now_iso_local())
        except Exception:  # noqa: BLE001
            pass
        # Cleanup
        self.destroy()
        try:
            if self._root is not None:
                self._root.quit()
                self._root.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Tear down everything: cancel timers, close DB, save state."""
        # Cancel background jobs
        for label, after_id in list(self._bg_jobs):
            try:
                if self._root is not None:
                    self._root.after_cancel(after_id)
            except Exception:  # noqa: BLE001
                pass
        self._bg_jobs.clear()
        # Cancel auto-lock check
        if self._auto_lock_check_handle is not None and self._root is not None:
            try:
                self._root.after_cancel(self._auto_lock_check_handle)
            except Exception:  # noqa: BLE001
                pass
            self._auto_lock_check_handle = None
        # Unsubscribe from event bus
        for event, callback in list(self._subscriptions):
            try:
                event_bus.bus.unsubscribe(event, callback)
            except Exception:  # noqa: BLE001
                pass
        self._subscriptions.clear()
        # Stop the reminder scheduler
        try:
            reminder_service.stop_scheduler()
        except Exception:  # noqa: BLE001
            pass
        # Close active dialogs
        for dlg in list(self._active_dialogs):
            try:
                dlg.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._active_dialogs.clear()
        # Destroy current screen
        if self._current_screen is not None:
            try:
                self._current_screen.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._current_screen = None
        # Save state
        try:
            db.kv_set(_CURRENT_TAB_KEY, self._current_tab)
            db.kv_set(_LAST_ACTIVITY_KEY, now_iso_local())
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the CustomTkinter main loop.

        Blocks until the window is closed or :meth:`quit_app` is
        called.  Handles :class:`KeyboardInterrupt` gracefully.
        """
        if self._root is None:
            return
        try:
            self._root.mainloop()
        except KeyboardInterrupt:
            print("\nInterrupted.")
            try:
                self.destroy()
            except Exception:  # noqa: BLE001
                pass

    # ==================================================================
    # === Setup helpers                                            ===
    # ==================================================================

    def _setup_events(self) -> None:
        """Subscribe to event-bus events."""
        sub = event_bus.bus.subscribe
        # UI events
        self._subscribe("ui.toast", self._on_ui_toast)
        self._subscribe("ui.tab_changed", self._on_ui_tab_changed)
        # Language + theme
        self._subscribe("language.changed", self._on_language_changed)
        self._subscribe("theme.changed", self._on_theme_changed)
        self._subscribe("settings.changed", self._on_settings_changed)
        # Badge unlocked — show toast + confetti
        self._subscribe("badge.unlocked", self._on_badge_unlocked)
        # Reminder triggered
        self._subscribe("reminder.triggered", self._on_reminder_triggered)
        # Timer events — update FAB icon
        self._subscribe("timer.started", self._on_timer_started)
        self._subscribe("timer.stopped", self._on_timer_stopped)
        # Activity events — refresh current screen
        self._subscribe("activity.added", self._on_data_changed)
        self._subscribe("activity.updated", self._on_data_changed)
        self._subscribe("activity.deleted", self._on_data_changed)
        self._subscribe("goal.added", self._on_data_changed)
        self._subscribe("goal.updated", self._on_data_changed)
        self._subscribe("goal.deleted", self._on_data_changed)
        self._subscribe("template.added", self._on_data_changed)
        self._subscribe("template.updated", self._on_data_changed)
        self._subscribe("template.deleted", self._on_data_changed)
        self._subscribe("reminder.added", self._on_data_changed)
        self._subscribe("reminder.updated", self._on_data_changed)
        self._subscribe("reminder.deleted", self._on_data_changed)
        self._subscribe("category.added", self._on_data_changed)
        self._subscribe("category.updated", self._on_data_changed)
        self._subscribe("category.deleted", self._on_data_changed)
        self._subscribe("data.imported", self._on_data_imported)
        self._subscribe("data.cleared", self._on_data_cleared)
        # Backup / restore
        self._subscribe("backup.created", self._on_backup_created)
        self._subscribe("backup.restored", self._on_backup_restored)

    def _subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Subscribe + remember so we can unsubscribe on destroy."""
        try:
            event_bus.bus.subscribe(event, callback)
            self._subscriptions.append((event, callback))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"event": event})

    def _setup_shortcuts(self) -> None:
        """Bind the keyboard shortcuts to the root window."""
        if self._root is None:
            return
        try:
            self._root.bind_all("<Control-n>", lambda e: self.open_quick_log())
            self._root.bind_all("<Control-N>", lambda e: self.open_quick_log())
            self._root.bind_all("<Control-f>", lambda e: self.open_search())
            self._root.bind_all("<Control-F>", lambda e: self.open_search())
            self._root.bind_all("<Control-t>",
                                  lambda e: self._start_default_timer())
            self._root.bind_all("<Control-T>",
                                  lambda e: self._start_default_timer())
            self._root.bind_all("<Control-s>",
                                  lambda e: self._stop_timer())
            self._root.bind_all("<Control-S>",
                                  lambda e: self._stop_timer())
            self._root.bind_all("<Control-b>",
                                  lambda e: self.open_backup_dialog())
            self._root.bind_all("<Control-B>",
                                  lambda e: self.open_backup_dialog())
            self._root.bind_all("<Control-e>",
                                  lambda e: self.open_export_dialog())
            self._root.bind_all("<Control-E>",
                                  lambda e: self.open_export_dialog())
            self._root.bind_all("<Control-comma>",
                                  lambda e: self.switch_tab("settings"))
            self._root.bind_all("<Control-1>",
                                  lambda e: self.switch_tab("home"))
            self._root.bind_all("<Control-2>",
                                  lambda e: self.switch_tab("goals"))
            self._root.bind_all("<Control-3>",
                                  lambda e: self.switch_tab("stats"))
            self._root.bind_all("<Control-4>",
                                  lambda e: self.switch_tab("settings"))
            self._root.bind_all("<Control-l>",
                                  lambda e: self.lock_app())
            self._root.bind_all("<Control-L>",
                                  lambda e: self.lock_app())
            self._root.bind_all("<Control-q>",
                                  lambda e: self.quit_app())
            self._root.bind_all("<Control-Q>",
                                  lambda e: self.quit_app())
            self._root.bind_all("<question>",
                                  lambda e: self.open_shortcuts())
            self._root.bind_all("<Escape>",
                                  lambda e: self._on_escape())
            # Track activity for auto-lock
            self._root.bind_all("<Any-KeyPress>",
                                  lambda e: self._bump_activity(),
                                  add="+")
            self._root.bind_all("<Button-1>",
                                  lambda e: self._bump_activity(),
                                  add="+")
            self._root.bind_all("<Motion>",
                                  lambda e: self._bump_activity(),
                                  add="+")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _start_default_timer(self) -> None:
        """Ctrl+T — start a quick timer with a default title."""
        try:
            if timer_service.is_running():
                self.show_toast(
                    "Timer already running — stop it first (Ctrl+S).",
                    kind="warning")
                return
            timer_service.start(
                title=(i18n.t("quickSession", self._lang)
                       if i18n.t("quickSession", self._lang) != "quickSession"
                       else "نشست سریع"))
            msg = (i18n.t("recording", self._lang)
                    if i18n.t("recording", self._lang) != "recording"
                    else "در حال ضبط")
            self.show_toast(msg, kind="info")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not start timer: {exc}",
                             kind="error")

    def _stop_timer(self) -> None:
        """Ctrl+S — stop the running timer (and save the activity)."""
        try:
            if not timer_service.is_running() and not timer_service.is_paused():
                self.show_toast("No timer running.", kind="info")
                return
            activity = timer_service.stop(save=True)
            if activity is None:
                self.show_toast("Timer stopped (too short to save).",
                                 kind="info")
            else:
                msg = (i18n.t("activitySaved", self._lang)
                        if i18n.t("activitySaved", self._lang) != "activitySaved"
                        else "فعالیت ذخیره شد")
                self.show_toast(msg, kind="success")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self.show_toast(f"Could not stop timer: {exc}", kind="error")

    def _on_escape(self) -> None:
        """Esc — close the topmost dialog or the search/shortcuts overlay."""
        # Close topmost dialog if any
        if self._active_dialogs:
            dlg = self._active_dialogs[-1]
            try:
                close = getattr(dlg, "close", None)
                if callable(close):
                    close()
                else:
                    dlg.destroy()
            except Exception:  # noqa: BLE001
                pass
            return
        # Close overlays
        if self._search_screen is not None:
            self.close_search()
            return
        if self._shortcuts_screen is not None:
            self.close_shortcuts()
            return

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    def _setup_background_tasks(self) -> None:
        """Schedule recurring background tasks via Tk's ``after()`` loop.

        Schedules:
          * Reminder scheduler (every 30 s — also handled by the
            service itself once ``set_root`` is called).
          * Recurring-activity processor (every 5 min).
          * Auto-backup checker (every hour).
          * Auto-lock idle check (every 60 s — only when auto-lock is
            enabled).
          * Total-launches counter bump (immediate).
        """
        if self._root is None:
            return
        # Hand the Tk root to the timer + reminder services so their
        # internal after-loops can fire.
        try:
            timer_service.set_root(self._root)
            reminder_service.set_root(self._root)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        # Recurring processor (every 5 minutes)
        self._schedule_recurring(5 * 60 * 1000)
        # Auto-backup checker (every 1 hour)
        self._schedule_auto_backup(60 * 60 * 1000)
        # Profile / stats periodic refresh (every 60 s) — used to
        # recompute "today's focus" on the home screen
        self._schedule_periodic_refresh(60 * 1000)

    def _schedule_recurring(self, interval_ms: int) -> None:
        """Schedule the recurring-activity processor."""
        if self._root is None:
            return
        try:
            handle = self._root.after(interval_ms, self._process_recurring)
            self._bg_jobs.append(("recurring", handle))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _process_recurring(self) -> None:
        """Process due recurring rules and re-arm the timer."""
        try:
            due = recurring_service.process_due()
            if due:
                _log.info("Processed %d recurring rules", len(due))
                msg = (i18n.t("recurringProcessed", self._lang)
                        if i18n.t("recurringProcessed", self._lang) != "recurringProcessed"
                        else f"{len(due)} فعالیت تکرارشونده ثبت شد")
                self.show_toast(msg, kind="info")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        # Re-arm
        self._schedule_recurring(5 * 60 * 1000)

    def _schedule_auto_backup(self, interval_ms: int) -> None:
        """Schedule the auto-backup checker."""
        if self._root is None:
            return
        try:
            handle = self._root.after(interval_ms, self._check_auto_backup)
            self._bg_jobs.append(("auto_backup", handle))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _check_auto_backup(self) -> None:
        """Check whether an auto-backup is due and run it if so."""
        try:
            result = backup_service.maybe_run_auto()
            if result and result.get("success"):
                msg = (i18n.t("autoBackupDone", self._lang)
                        if i18n.t("autoBackupDone", self._lang) != "autoBackupDone"
                        else "پشتیبان خودکار ساخته شد")
                self.show_toast(msg, kind="success")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        # Re-arm
        self._schedule_auto_backup(60 * 60 * 1000)

    def _schedule_periodic_refresh(self, interval_ms: int) -> None:
        """Schedule a periodic refresh of the current screen.

        Ensures the UI always reflects the latest DB state, even if
        no event was published (e.g. when a background timer tick
        crosses a day boundary).
        """
        if self._root is None:
            return
        try:
            handle = self._root.after(interval_ms, self._periodic_refresh)
            self._bg_jobs.append(("periodic_refresh", handle))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _periodic_refresh(self) -> None:
        """Periodic 60 s refresh of the current screen + auto-lock check."""
        try:
            self._refresh_current_screen()
        except Exception:  # noqa: BLE001
            pass
        # Auto-lock check
        try:
            self._check_auto_lock()
        except Exception:  # noqa: BLE001
            pass
        # Re-arm
        self._schedule_periodic_refresh(60 * 1000)

    # ------------------------------------------------------------------
    # Auto-lock
    # ------------------------------------------------------------------

    def _schedule_auto_lock_check(self) -> None:
        """Schedule the periodic auto-lock idle check (every 30 s)."""
        if self._root is None:
            return
        try:
            self._auto_lock_check_handle = self._root.after(
                30_000, self._auto_lock_tick)
        except Exception:  # noqa: BLE001
            pass

    def _auto_lock_tick(self) -> None:
        """One tick of the auto-lock idle checker."""
        self._check_auto_lock()
        # Re-arm
        if self._root is not None and not self._quitting:
            try:
                self._auto_lock_check_handle = self._root.after(
                    30_000, self._auto_lock_tick)
            except Exception:  # noqa: BLE001
                pass

    def _check_auto_lock(self) -> None:
        """Lock the app if the user has been idle for too long."""
        if self._locked or self._quitting:
            return
        try:
            auto_lock_seconds = settings_service.auto_lock_seconds()
            if auto_lock_seconds <= 0:
                return
            if not self._should_lock():
                return
            idle = time.time() - self._last_activity_ts
            if idle >= auto_lock_seconds:
                _log.info("Auto-locking after %d s idle", int(idle))
                self.lock_app()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _bump_activity(self) -> None:
        """Record that the user is active (reset the auto-lock timer)."""
        self._last_activity_ts = time.time()

    # ------------------------------------------------------------------
    # Launch counter
    # ------------------------------------------------------------------

    def _increment_launch_counter(self) -> None:
        """Increment the total-launches counter in the kv store."""
        try:
            current = db.kv_get_int(_LAUNCH_COUNTER_KEY, 0)
            db.kv_set_int(_LAUNCH_COUNTER_KEY, current + 1)
            db.kv_set("last_launch_iso", now_iso_local())
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Language / theme / direction
    # ------------------------------------------------------------------

    def apply_language(self, lang: str) -> None:
        """Switch the UI language at runtime and reload the current screen."""
        if lang not in config.SUPPORTED_LANGUAGES:
            _log.warning("Unknown language %r — ignoring", lang)
            return
        try:
            settings_service.set_language(lang)
        except Exception:  # noqa: BLE001
            pass
        i18n.set_language(lang)
        self._lang = lang
        self._apply_direction()
        # Reload UI
        self.reload_ui()
        # Notify subscribers
        event_bus.bus.publish("language.changed", {"lang": lang})

    def apply_theme(self, mode: str) -> None:
        """Switch the colour theme at runtime."""
        if mode not in ("dark", "light", "system"):
            _log.warning("Unknown theme %r — ignoring", mode)
            return
        try:
            settings_service.set_theme(mode)
        except Exception:  # noqa: BLE001
            pass
        self._theme = mode
        self._apply_theme()
        event_bus.bus.publish("theme.changed", {"theme": mode})

    def apply_direction(self) -> None:
        """Apply RTL/LTR based on the current language."""
        self._apply_direction()

    def _apply_theme(self) -> None:
        """Push the theme through to CustomTkinter's appearance mode."""
        try:
            ctk.set_appearance_mode(self._theme)
        except Exception:  # noqa: BLE001
            pass

    def _apply_direction(self) -> None:
        """Apply RTL/LTR to the root window (Tk's ``ttk::setDirection``)."""
        try:
            if self._root is not None:
                # Tk does not have a global direction setting — we
                # rely on each widget respecting i18n.is_rtl(lang)
                # at construction time.  Here we just toggle a root
                # attribute that widgets can query if they wish.
                self._root._rask_rtl = i18n.is_rtl(self._lang)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # === Event handlers                                          ===
    # ==================================================================

    def _on_ui_toast(self, *args: Any, **kwargs: Any) -> None:
        """``ui.toast`` event handler — show a toast."""
        try:
            message = kwargs.get("message") or (args[0] if args else "")
            kind = kwargs.get("kind", "info")
            duration = kwargs.get("duration", 3500)
            self.show_toast(message, kind=kind, duration=duration)
        except Exception:  # noqa: BLE001
            pass

    def _on_ui_tab_changed(self, *args: Any, **kwargs: Any) -> None:
        """``ui.tab_changed`` event handler — switch tab if requested."""
        try:
            tab = kwargs.get("tab") or (args[0] if args else {}).get("tab")
            if tab and tab != self._current_tab:
                self.switch_tab(tab)
        except Exception:  # noqa: BLE001
            pass

    def _on_language_changed(self, *args: Any, **kwargs: Any) -> None:
        """``language.changed`` event handler."""
        try:
            lang = kwargs.get("lang") or (args[0] if args else {}).get("lang")
            if lang and lang != self._lang:
                self._lang = lang
                self._apply_direction()
                self.reload_ui()
        except Exception:  # noqa: BLE001
            pass

    def _on_theme_changed(self, *args: Any, **kwargs: Any) -> None:
        """``theme.changed`` event handler."""
        try:
            theme = kwargs.get("theme") or (args[0] if args else {}).get("theme")
            if theme and theme != self._theme:
                self._theme = theme
                self._apply_theme()
        except Exception:  # noqa: BLE001
            pass

    def _on_settings_changed(self, *args: Any, **kwargs: Any) -> None:
        """``settings.changed`` event handler — refresh current screen."""
        self._refresh_current_screen()

    def _on_badge_unlocked(self, *args: Any, **kwargs: Any) -> None:
        """``badge.unlocked`` event handler — toast + confetti."""
        try:
            badge = kwargs.get("badge") or (args[0] if args else {})
            if not badge:
                return
            name = (badge.get("name_fa") if self._lang == "fa"
                     else badge.get("name_en")) or "Badge"
            msg = (i18n.t("badgeUnlocked", self._lang)
                    if i18n.t("badgeUnlocked", self._lang) != "badgeUnlocked"
                    else f"نشان جدید: {name}")
            self.show_toast(msg, kind="achievement")
            # Fire confetti
            try:
                from .widgets.confetti import Confetti
                Confetti.burst(self._root)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_reminder_triggered(self, *args: Any, **kwargs: Any) -> None:
        """``reminder.triggered`` event handler — toast + sound."""
        try:
            reminder = kwargs.get("reminder") or (args[0] if args else {})
            if not reminder:
                return
            title = reminder.get("title", "Reminder")
            msg = reminder.get("message") or ""
            text = f"{title}"
            if msg:
                text += f"\n{msg}"
            self.show_toast(text, kind="info", duration=5500)
            # Play sound (best-effort)
            try:
                if settings_service.notify_sound():
                    self._play_notify_sound()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _play_notify_sound(self) -> None:
        """Play a short notification sound (best-effort, cross-platform)."""
        try:
            if sys.platform == "darwin":
                import subprocess
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform == "win32":
                import winsound  # type: ignore[import-not-found]
                winsound.MessageBeep()
            else:
                # Linux — try paplay / aplay
                import subprocess
                subprocess.Popen(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001
            pass

    def _on_timer_started(self, *args: Any, **kwargs: Any) -> None:
        """``timer.started`` — update FAB icon to a stop icon."""
        try:
            if self._fab is not None:
                from .widgets import icons as _icons
                img = _icons.icon("stop", int(config.FAB_SIZE * 0.45),
                                    color=config.MATTE_BLACK)
                if img is not None:
                    self._fab.configure(image=img, text="")
                self._fab.configure(command=self._stop_timer)
        except Exception:  # noqa: BLE001
            pass

    def _on_timer_stopped(self, *args: Any, **kwargs: Any) -> None:
        """``timer.stopped`` — restore FAB icon to a plus icon."""
        try:
            if self._fab is not None:
                from .widgets import icons as _icons
                img = _icons.icon("plus", int(config.FAB_SIZE * 0.45),
                                    color=config.MATTE_BLACK)
                if img is not None:
                    self._fab.configure(image=img, text="")
                self._fab.configure(command=self._on_fab)
        except Exception:  # noqa: BLE001
            pass

    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        """Activity/goal/template/etc. CRUD — refresh current screen."""
        try:
            self._refresh_current_screen()
        except Exception:  # noqa: BLE001
            pass

    def _on_data_imported(self, *args: Any, **kwargs: Any) -> None:
        """``data.imported`` — full UI reload."""
        try:
            self.reload_ui()
            self.show_toast("Data imported.", kind="success")
        except Exception:  # noqa: BLE001
            pass

    def _on_data_cleared(self, *args: Any, **kwargs: Any) -> None:
        """``data.cleared`` — full UI reload."""
        try:
            self.reload_ui()
            self.show_toast("Data cleared.", kind="info")
        except Exception:  # noqa: BLE001
            pass

    def _on_backup_created(self, *args: Any, **kwargs: Any) -> None:
        """``backup.created`` — toast + refresh."""
        try:
            self.show_toast("Backup created.", kind="success")
            self._refresh_current_screen()
        except Exception:  # noqa: BLE001
            pass

    def _on_backup_restored(self, *args: Any, **kwargs: Any) -> None:
        """``backup.restored`` — full UI reload."""
        try:
            self.reload_ui()
            self.show_toast("Backup restored.", kind="success")
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # === Dialog tracking                                          ===
    # ==================================================================

    def _track_dialog(self, dlg: Any) -> None:
        """Register an active dialog so we can close it on Esc / quit."""
        if dlg is None:
            return
        self._active_dialogs.append(dlg)
        # Try to register an on-destroy callback to remove it from
        # the active list automatically.
        try:
            dlg.bind("<Destroy>",
                      lambda _e, d=dlg: self._untrack_dialog(d),
                      add="+")
        except Exception:  # noqa: BLE001
            pass

    def _untrack_dialog(self, dlg: Any) -> None:
        """Remove a dialog from the active list."""
        try:
            self._active_dialogs.remove(dlg)
        except ValueError:
            pass

    # ==================================================================
    # === Public properties                                         ===
    # ==================================================================

    @property
    def root(self) -> Optional[ctk.CTk]:
        """The CTk root window (None before :meth:`__init__` finishes)."""
        return self._root

    @property
    def lang(self) -> str:
        """The current UI language code."""
        return self._lang

    @property
    def theme(self) -> str:
        """The current colour theme."""
        return self._theme

    @property
    def current_tab(self) -> str:
        """The currently-active bottom-nav tab key."""
        return self._current_tab

    @property
    def locked(self) -> bool:
        """True when the app is currently showing the lock screen."""
        return self._locked


# =============================================================================
# === Self-test                                                                ===
# =============================================================================

def _self_test() -> int:
    """Lightweight smoke test — verifies the class can be imported.

    A full instantiation requires CustomTkinter + a running Tk loop,
    which is not appropriate for unit tests.  We just verify that
    the module imports cleanly and the class is defined.
    """
    if not _CTK_OK:
        print("SKIP: CustomTkinter not installed")
        return 0
    assert RaskApp is not None
    print("RaskApp class defined and importable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
