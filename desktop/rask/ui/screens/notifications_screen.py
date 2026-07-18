"""
rask.ui.screens.notifications_screen
====================================

In-app notification center screen.

Mirrors the *Notifications* view from the web app.  Uses
:class:`rask.features.notifications_center.NotificationCenter` as the
source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"اعلان‌ها"`` with "Mark all read" action button
    2. **Tab control** — Unread / All segmented control
    3. **Notification list** — vertical scroll of notification cards
       (icon, title, body, timestamp, unread indicator)
    4. **Empty state** — ``"اعلانی موجود نیست"``
    5. **Clear all button** — at the bottom, with confirmation

Each notification card:
  • Color stripe by kind (info=blue, success=green, warning=amber,
    error=red, achievement=gold)
  • Icon glyph
  • Title (bold)
  • Body (one line, dimmed)
  • Relative timestamp
  • Unread dot indicator
  • Tap → mark read + perform action (e.g. open activity dialog for
    badge.unlocked)

Auto-refresh
------------
Subscribes to ``notification.added`` / ``notification.updated`` /
``notification.deleted`` / ``notification.read`` /
``language.changed`` / ``data.cleared``.
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
from ...core import event_bus, time_utils
from ...features.notifications_center import (
    notification_center,
    KIND_INFO, KIND_SUCCESS, KIND_WARNING, KIND_ERROR,
    KIND_ACHIEVEMENT,
)
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, DangerButton,
)
from ..widgets.cards import Card
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.toggles import SegmentedControl
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.dialogs import AlertDialog

__all__ = ["NotificationsScreen"]


# =============================================================================
# === Kind → color/icon mapping                                              ===
# =============================================================================

_KIND_COLOR: Dict[str, str] = {
    KIND_INFO: config.INFO,
    KIND_SUCCESS: config.SUCCESS,
    KIND_WARNING: config.WARNING,
    KIND_ERROR: config.DANGER,
    KIND_ACHIEVEMENT: config.GOLD,
}
_KIND_ICON: Dict[str, str] = {
    KIND_INFO: "ℹ",
    KIND_SUCCESS: "✓",
    KIND_WARNING: "⚠",
    KIND_ERROR: "✕",
    KIND_ACHIEVEMENT: "★",
}


def _kind_color(kind: str) -> str:
    return _KIND_COLOR.get(kind, config.GOLD)


def _kind_icon(kind: str) -> str:
    return _KIND_ICON.get(kind, "•")


# =============================================================================
# === Notification card widget                                               ===
# =============================================================================

class _NotificationCard(ctk.CTkFrame):
    """One notification row."""

    def __init__(
        self,
        master: Any,
        notification: Any,
        lang: str = "fa",
        on_click: Optional[Callable[[Any], Any]] = None,
        on_delete: Optional[Callable[[int], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        super().__init__(master, **kwargs)
        self._notification = notification
        self._lang = lang
        self._on_click = on_click
        self._on_delete = on_delete
        self.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(lang)
        # Color stripe (leading in RTL)
        color = _kind_color(notification.kind)
        stripe = ctk.CTkFrame(self, width=4, fg_color=color)
        stripe.grid(row=0, column=1 if rtl else 0, sticky="ns",
                     padx=0, pady=8)
        # Icon (also leading)
        icon_label = ctk.CTkLabel(
            self, text=_kind_icon(notification.kind),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang="en"),
            text_color=color,
        )
        icon_label.grid(row=0, column=2 if rtl else 0, padx=4, pady=8)
        # Title + body + timestamp (center)
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1 if rtl else 2, sticky="ew", padx=8,
                   pady=8)
        info.grid_columnconfigure(0, weight=1)
        # Title row
        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)
        # Unread dot (leading the title in RTL)
        unread = not notification.read
        if unread:
            dot = ctk.CTkFrame(title_row, width=8, height=8,
                                 fg_color=config.GOLD,
                                 corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=1 if rtl else 0, padx=(0 if rtl
                                                            else 0,
                                                            4 if rtl
                                                            else 4))
            dot.grid(pady=8)
        ctk.CTkLabel(
            title_row, text=notification.title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=lang),
            text_color=config.TEXT if unread else config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                else "w")
        # Body
        body = notification.body or ""
        ctk.CTkLabel(
            info, text=body,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
            wraplength=320, justify="right" if rtl else "left",
        ).grid(row=1, column=0, sticky="e" if rtl else "w")
        # Timestamp
        try:
            time_str = time_utils.format_relative(
                notification.timestamp, lang=lang)
        except Exception:
            time_str = ""
        ctk.CTkLabel(
            info, text=time_str,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        ).grid(row=2, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))
        # Delete button (trailing in RTL)
        if on_delete is not None:
            del_btn = IconButton(
                self, icon_name="close",
                command=lambda: on_delete(int(notification.id)),
                size=28, lang=lang,
            )
            del_btn.grid(row=0, column=0 if rtl else 3, padx=4, pady=8)
        # Click binding
        if on_click is not None:
            self.bind("<Button-1>",
                        lambda _e: on_click(notification), add="+")
            for child in self.winfo_children():
                child.bind("<Button-1>",
                            lambda _e: on_click(notification), add="+")
                for sub in child.winfo_children():
                    try:
                        sub.bind("<Button-1>",
                                  lambda _e: on_click(notification),
                                  add="+")
                    except Exception:
                        pass


# =============================================================================
# === NotificationsScreen                                                    ===
# =============================================================================

class NotificationsScreen(ctk.CTkFrame):
    """In-app notifications screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``open_activity_dialog(activity_id)``
            * ``switch_tab(tab)``
            * ``confirm_delete(on_confirm, name)``
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
        self._tab_unread: bool = True
        self._notification_cards: List[_NotificationCard] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        # Header
        self._header = Header(
            self, title=self._tr("اعلان‌ها", "Notifications"),
            lang=self._lang, height=56,
            action_text=self._tr("خوانده شد", "Mark all"),
            on_action=self._on_mark_all_read,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Tab control
        tabs_frame = ctk.CTkFrame(
            self, fg_color=config.MATTE_BLACK,
            corner_radius=0,
        )
        tabs_frame.grid(row=1, column=0, sticky="ew")
        tabs_frame.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Segmented control: Unread / All
        self._tab_seg = SegmentedControl(
            tabs_frame,
            values=[self._tr("خوانده‌نشده", "Unread"),
                     self._tr("همه", "All")],
            on_change=self._on_tab_change,
            lang=self._lang, height=36,
        )
        self._tab_seg.set(self._tr("خوانده‌نشده", "Unread"))
        self._tab_seg.pack(anchor="center", padx=config.SPACE_LG,
                             pady=config.SPACE_SM)
        # Scrollable list
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # Clear-all button row (below the list)
        bottom_frame = ctk.CTkFrame(
            self, fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        bottom_frame.grid(row=3, column=0, sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1)
        self._clear_all_btn = DangerButton(
            bottom_frame,
            text=self._tr("پاک کردن همه", "Clear all"),
            command=self._on_clear_all, lang=self._lang, height=40,
        )
        self._clear_all_btn.pack(anchor="center",
                                   padx=config.SPACE_LG,
                                   pady=config.SPACE_SM)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "notification.added", "notification.updated",
            "notification.deleted", "notification.read",
            "language.changed", "data.cleared",
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
        self._refresh_job = self.after(120, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the notification list."""
        for child in self._scroll.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._notification_cards = []
        try:
            notifications = notification_center.list(
                unread_only=self._tab_unread, limit=100)
        except Exception:
            notifications = []
        if not notifications:
            EmptyState(
                self._scroll, icon="bell",
                title=self._tr("اعلانی موجود نیست",
                                "No notifications"),
                subtitle=(self._tr("اعلان‌های جدید اینجا نمایش داده می‌شوند",
                                     "New notifications will appear here")
                          if self._tab_unread
                          else self._tr("هنوز اعلانی ثبت نشده",
                                          "No notifications yet")),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_XL)
            return
        for i, n in enumerate(notifications):
            card = _NotificationCard(
                self._scroll, notification=n, lang=self._lang,
                on_click=self._on_notification_click,
                on_delete=self._on_notification_delete,
            )
            card.grid(row=i, column=0, sticky="ew",
                       padx=config.SPACE_LG,
                       pady=(0 if i == 0 else 4, 4))
            self._notification_cards.append(card)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_tab_change(self, value: str) -> None:
        """Switch between Unread / All."""
        unread_label = self._tr("خوانده‌نشده", "Unread")
        self._tab_unread = (value == unread_label)
        self.refresh()

    def _on_notification_click(self, notification: Any) -> None:
        """Tap a notification — mark read + perform action."""
        try:
            if not notification.read:
                notification_center.mark_read(int(notification.id))
        except Exception:
            pass
        # Perform action based on action_type
        try:
            action_type = notification.action_type
            payload = notification.action_payload or {}
            if action_type == "open_activity" and "activity_id" in payload:
                if self._app and hasattr(self._app,
                                          "open_activity_dialog"):
                    self._app.open_activity_dialog(int(payload["activity_id"]))
                    return
            elif action_type == "open_tab" and "tab" in payload:
                if self._app and hasattr(self._app, "switch_tab"):
                    self._app.switch_tab(str(payload["tab"]))
                    return
            elif action_type == "open_screen" and "screen" in payload:
                if self._app and hasattr(self._app, "switch_tab"):
                    self._app.switch_tab(str(payload["screen"]))
                    return
        except Exception:
            pass
        # Default: just refresh
        self.refresh()

    def _on_notification_delete(self, notification_id: int) -> None:
        try:
            notification_center.delete(notification_id)
        except Exception:
            pass
        self.refresh()

    def _on_mark_all_read(self) -> None:
        try:
            count = notification_center.mark_all_read()
            if count > 0:
                self._show_toast(
                    f"{i18n.to_fa_digits(str(count)) if self._lang == 'fa' else str(count)} "
                    f"{self._tr('اعلان خوانده شد', 'notifications marked read')}")
        except Exception:
            pass
        self.refresh()

    def _on_clear_all(self) -> None:
        """Confirm + clear all notifications."""
        def _do_clear() -> None:
            try:
                count = notification_center.clear_all()
                self._show_toast(
                    self._tr("همه پاک شدند",
                              "All cleared"))
            except Exception:
                pass
            self.refresh()
        # Confirm
        if self._app and hasattr(self._app, "confirm_delete"):
            try:
                self._app.confirm_delete(
                    on_confirm=_do_clear,
                    name=self._tr("اعلان‌ها", "notifications"),
                )
                return
            except Exception:
                pass
        # Fallback: just do it
        _do_clear()

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
    print("NotificationsScreen module: header + Unread/All tabs + "
          "notification cards + clear all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
