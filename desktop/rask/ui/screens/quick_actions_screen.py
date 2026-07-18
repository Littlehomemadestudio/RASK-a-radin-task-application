"""
rask.ui.screens.quick_actions_screen
====================================

Quick actions screen — a grid of shortcut buttons for common
operations.

Mirrors the *Quick Actions* view from the web app.  Uses
:class:`rask.features.quick_actions.QuickActionsService` as the source
of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"اقدامات سریع"``
    2. **Grid of quick action buttons** (3 columns):
       - Start 25-min focus
       - Start 50-min focus
       - Log 30-min reading
       - Log 1-hour workout
       - Start timer with last category
       - Quick log last activity
       - Open weekly review
       - Export today's report
       - Backup now
       - Lock app
       - New activity (opens quick log)
       - New goal
    3. Each button: icon + label, gold accent
    4. Edit mode (optional): rearrange, add custom actions

Auto-refresh
------------
Subscribes to ``quick_action.executed`` / ``quick_action.added`` /
``quick_action.removed`` / ``language.changed`` / ``data.cleared``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus
from ...features.quick_actions import quick_actions_service
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.dialogs import AlertDialog

__all__ = ["QuickActionsScreen"]


# =============================================================================
# === Quick action button cell                                               ===
# =============================================================================

class _ActionCell(ctk.CTkFrame):
    """One quick action button in the grid."""

    def __init__(
        self,
        master: Any,
        icon: str,
        label: str,
        shortcut: Optional[str] = None,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        super().__init__(master, **kwargs)
        self._on_click = on_click
        self._lang = lang
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        # Click binding
        self.bind("<Button-1>", self._tapped, add="+")
        # Content frame
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew", padx=8, pady=12)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)
        # Icon (emoji-style unicode)
        ctk.CTkLabel(
            content, text=icon,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="normal", lang="en"),
            text_color=config.GOLD,
        ).grid(row=0, column=0, pady=(0, 4))
        # Label
        ctk.CTkLabel(
            content, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            wraplength=120, justify="center", anchor="center",
        ).grid(row=1, column=0)
        # Shortcut (small, dimmed)
        if shortcut:
            ctk.CTkLabel(
                content, text=shortcut,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION - 1,
                                        weight="normal", lang="en"),
                text_color=config.TEXT_FAINT,
            ).grid(row=2, column=0, pady=(2, 0))
        # Hover effect
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        for child in self.winfo_children():
            child.bind("<Button-1>", self._tapped, add="+")
            child.bind("<Enter>", self._on_enter, add="+")
            child.bind("<Leave>", self._on_leave, add="+")
            for sub in child.winfo_children():
                try:
                    sub.bind("<Button-1>", self._tapped, add="+")
                    sub.bind("<Enter>", self._on_enter, add="+")
                    sub.bind("<Leave>", self._on_leave, add="+")
                except Exception:
                    pass

    def _tapped(self, _event: Any) -> None:
        if self._on_click is not None:
            try:
                self._on_click()
            except Exception:
                pass

    def _on_enter(self, _event: Any) -> None:
        try:
            self.configure(fg_color=config.SURFACE_HI,
                            border_color=config.GOLD)
        except Exception:
            pass

    def _on_leave(self, _event: Any) -> None:
        try:
            self.configure(fg_color=config.CHARCOAL,
                            border_color=config.SURFACE_HI)
        except Exception:
            pass


# =============================================================================
# === QuickActionsScreen                                                     ===
# =============================================================================

class QuickActionsScreen(ctk.CTkFrame):
    """Quick actions screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``open_quick_log()``
            * ``open_goal_dialog()``
            * ``switch_tab(tab)``
            * ``show_export_dialog()``
            * ``show_lock()``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._subscriptions: List[tuple] = []
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._action_cells: List[_ActionCell] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._header = Header(
            self, title=self._tr("اقدامات سریع",
                                   "Quick Actions"),
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_intro()
        self._build_grid()
        self._build_help()

    def _build_intro(self) -> None:
        """Intro card explaining quick actions."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content,
            text=self._tr("یک میان‌بر را برای اجرای سریع انتخاب کن",
                            "Pick a shortcut to execute quickly"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
            wraplength=420, justify="right" if rtl else "left",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")

    def _build_grid(self) -> None:
        """The 3-column actions grid."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        self._grid_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._grid_frame.grid(row=0, column=0, sticky="ew")
        for i in range(3):
            self._grid_frame.grid_columnconfigure(i, weight=1,
                                                    uniform="act")

    def _build_help(self) -> None:
        """Tip card."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section,
            text=self._tr("میان‌برهای صفحه‌کلید نیز قابل استفاده هستند.",
                            "Keyboard shortcuts are also available."),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT, justify="center",
            wraplength=420,
        ).grid(row=0, column=0)

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "quick_action.executed", "quick_action.added",
            "quick_action.removed", "language.changed", "data.cleared",
        ]
        for ev in events:
            try:
                bus.subscribe(ev, self._on_data_changed)
                self._subscriptions.append((ev, self._on_data_changed))
            except Exception:
                pass

    def _unsubscribe_events(self) -> None:
        bus = event_bus.bus
        for ev, cb in self._subscriptions:
            try:
                bus.unsubscribe(ev, cb)
            except Exception:
                pass
        self._subscriptions.clear()

    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(150, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the actions grid."""
        # Clear old cells
        for child in self._grid_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._action_cells = []
        # Fetch actions
        try:
            actions = quick_actions_service.list()
        except Exception:
            actions = []
        if not actions:
            EmptyState(
                self._grid_frame, icon="bolt",
                title=self._tr("اقدامی موجود نیست",
                                "No actions available"),
                subtitle=self._tr("اقدامات پیش‌فرض به‌زودی بارگذاری می‌شوند",
                                    "Default actions will load shortly"),
                lang=self._lang,
            ).grid(row=0, column=0, columnspan=3, sticky="ew",
                     pady=config.SPACE_LG)
            return
        # Add the 2 system actions: New activity + New goal (which
        # aren't in the default quick_actions_service list).
        extra_actions = [
            {
                "id": "_new_activity",
                "name": self._tr("فعالیت جدید", "New activity"),
                "icon": "➕",
                "shortcut": "Ctrl+N",
                "_handler": self._on_new_activity,
            },
            {
                "id": "_new_goal",
                "name": self._tr("هدف جدید", "New goal"),
                "icon": "🎯",
                "shortcut": "Ctrl+G",
                "_handler": self._on_new_goal,
            },
        ]
        # Combine
        all_actions = list(actions) + extra_actions
        # Build grid (3 columns)
        for i, a in enumerate(all_actions):
            row = i // 3
            col = (2 - (i % 3)) if i18n.is_rtl(self._lang) else (i % 3)
            icon = a.get("icon") or "•"
            name = a.get("name", "—")
            shortcut = a.get("shortcut")
            cell = _ActionCell(
                self._grid_frame, icon=icon, label=name,
                shortcut=shortcut, lang=self._lang,
                on_click=lambda _a=a: self._on_action_tap(_a),
            )
            cell.grid(row=row, column=col, sticky="nsew",
                       padx=4, pady=4)
            self._action_cells.append(cell)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_action_tap(self, action: Dict[str, Any]) -> None:
        """Tap a quick action — execute it."""
        action_id = action.get("id")
        # Check for the system actions
        if action_id == "_new_activity":
            self._on_new_activity()
            return
        if action_id == "_new_goal":
            self._on_new_goal()
            return
        # Execute via the service
        try:
            ok = quick_actions_service.execute(str(action_id))
            if ok:
                self._show_toast(
                    self._tr("اجرا شد", "Executed"))
            else:
                self._show_toast(
                    self._tr("اجرای ناموفق", "Execution failed"))
        except Exception:
            # Fallback: try common actions directly
            self._fallback_execute(action_id)

    def _fallback_execute(self, action_id: Optional[str]) -> None:
        """Fallback execution for known action IDs."""
        if action_id is None:
            return
        if action_id in ("focus_25", "focus_50"):
            # Start focus mode
            try:
                from ...features.focus_mode import focus_mode
                dur = 25 if action_id == "focus_25" else 50
                focus_mode.start(duration_min=dur,
                                  title=self._tr("تمرکز", "Focus"))
                self._show_toast(
                    self._tr("تمرکز شروع شد", "Focus started"))
            except Exception:
                pass
        elif action_id == "weekly_review":
            if self._app and hasattr(self._app, "switch_tab"):
                try:
                    self._app.switch_tab("weekly_review")
                except Exception:
                    pass
        elif action_id == "export_today":
            if self._app and hasattr(self._app, "show_export_dialog"):
                try:
                    self._app.show_export_dialog()
                except Exception:
                    pass
        elif action_id == "backup_now":
            if self._app and hasattr(self._app, "switch_tab"):
                try:
                    self._app.switch_tab("backup")
                except Exception:
                    pass
        elif action_id == "lock_app":
            if self._app and hasattr(self._app, "show_lock"):
                try:
                    self._app.show_lock()
                except Exception:
                    pass
        elif action_id in ("quick_log_last", "quick_log"):
            if self._app and hasattr(self._app, "open_quick_log"):
                try:
                    self._app.open_quick_log()
                except Exception:
                    pass

    def _on_new_activity(self) -> None:
        if self._app and hasattr(self._app, "open_quick_log"):
            try:
                self._app.open_quick_log()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.quick_log_requested")
        except Exception:
            pass

    def _on_new_goal(self) -> None:
        if self._app and hasattr(self._app, "open_goal_dialog"):
            try:
                self._app.open_goal_dialog()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.goal_dialog_requested")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            v = i18n.t(fa, self._lang)
            if v != fa:
                return v
        except Exception:
            pass
        return fa if self._lang == "fa" else en

    def _show_toast(self, message: str) -> None:
        if self._app and hasattr(self._app, "show_toast"):
            try:
                self._app.show_toast(message)
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.toast", {"message": message})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        self._unsubscribe_events()
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("QuickActionsScreen module: 3-col grid of shortcut buttons "
          "+ intro + help + fallback execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
