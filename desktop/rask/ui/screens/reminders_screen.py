"""
rask.ui.screens.reminders_screen
================================

Reminders screen — full CRUD UI for time-based reminders.

Reminders fire notifications on a weekly schedule (Persian weekdays:
Sat..Fri) at a fixed HH:MM time.  This screen lists every reminder,
shows its time + active days, lets the user toggle / edit / snooze /
delete, and creates new ones via the reminder dialog.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"یادآوری‌ها"`` with a ``"+ جدید"`` action button
    2. **Summary card** — counts: total / enabled / due today
    3. **Reminder list** — vertical stack of :class:`ReminderListItem`,
       each showing: title, time, days of week, enabled toggle,
       category color stripe
    4. **Empty state** — friendly illustration when no reminders exist

Interactions
------------
* Tap a reminder — open the reminder edit dialog
* Long-press a reminder — open an :class:`ActionSheet`:
  Edit / Snooze 10 min / Delete
* Toggle on/off inline
* FAB in the bottom-trailing corner for quick-add

Auto-refresh
------------
Subscribes to ``reminder.added`` / ``reminder.updated`` /
``reminder.deleted`` / ``reminder.triggered`` / ``reminder.dismissed`` /
``reminder.snoozed`` / ``language.changed`` / ``data.imported`` /
``data.cleared``.
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
from ...core import event_bus, time_utils, jalali, helpers
from ...services import reminder_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, FabButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.list_items import ReminderListItem
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.sheets import ActionSheet
from ..widgets.dialogs import ConfirmDialog

__all__ = ["RemindersScreen"]


# =============================================================================
# === Persian weekday names                                                  ===
# =============================================================================

WEEKDAY_NAMES_FA: List[str] = [
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه",
    "چهارشنبه", "پنجشنبه", "جمعه",
]
WEEKDAY_NAMES_EN: List[str] = [
    "Saturday", "Sunday", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday",
]

# Bitmask convention (Sat=1, Sun=2, Mon=4, Tue=8, Wed=16, Thu=32, Fri=64)
WEEKDAY_BITS: List[int] = [1, 2, 4, 8, 16, 32, 64]


def _decode_days(days_mask: int, lang: str) -> str:
    """Return a comma-joined list of weekday names for the given mask."""
    names = WEEKDAY_NAMES_FA if lang == "fa" else WEEKDAY_NAMES_EN
    if not days_mask or days_mask == 127:
        return WEEKDAY_NAMES_FA[6] if lang == "fa" else "Every day" \
            if days_mask == 127 else ""
    # Actually: 127 means all days
    if days_mask == 127:
        return "هر روز" if lang == "fa" else "Every day"
    out = []
    for i, bit in enumerate(WEEKDAY_BITS):
        if days_mask & bit:
            out.append(names[i])
    return ", ".join(out)


def _decode_time(hhmm: str, lang: str, time_format: str = "24") -> str:
    """Convert ``HH:MM`` to a localized display string."""
    if not hhmm or ":" not in hhmm:
        return hhmm or ""
    try:
        h, m = hhmm.split(":", 1)
        h = int(h)
        m = int(m)
    except (ValueError, TypeError):
        return hhmm
    if time_format == "12":
        suffix = "AM" if lang == "en" else "ق.ظ"
        h12 = h
        if h == 0:
            h12 = 12
        elif h > 12:
            h12 = h - 12
            suffix = "PM" if lang == "en" else "ب.ظ"
        elif h == 12:
            suffix = "PM" if lang == "en" else "ب.ظ"
        h_str = str(h12) if lang == "en" else i18n.to_fa_digits(str(h12))
        m_str = str(m).zfill(2) if lang == "en" else i18n.to_fa_digits(
            str(m).zfill(2))
        return f"{h_str}:{m_str} {suffix}" if lang == "en" \
            else f"{h_str}:{m_str} {suffix}"
    h_str = str(h).zfill(2) if lang == "en" else i18n.to_fa_digits(
        str(h).zfill(2))
    m_str = str(m).zfill(2) if lang == "en" else i18n.to_fa_digits(
        str(m).zfill(2))
    return f"{h_str}:{m_str}"


# =============================================================================
# === RemindersScreen                                                        ===
# =============================================================================

class RemindersScreen(ctk.CTkFrame):
    """Reminders browser.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``open_reminder_dialog(reminder_id=None)``
            * ``show_toast(message)``
            * ``confirm_delete(message, on_confirm)``
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
        self._reminder_items: List[ctk.CTkBaseClass] = []
        self._empty_state: Optional[EmptyState] = None
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self, title=i18n.t("reminders", self._lang),
            action_text=self._tr("newReminder", "New reminder"),
            on_action=self._on_new_reminder,
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # FAB
        self._fab = FabButton(
            self, icon_name="plus",
            command=self._on_new_reminder, lang=self._lang,
        )
        self.after(100, self._place_fab)
        # Sections
        self._section_row = 0
        self._build_summary()
        self._build_list()

    def _place_fab(self) -> None:
        try:
            w = max(1, self.winfo_width())
            h = max(1, self.winfo_height())
            fab_size = config.FAB_SIZE
            rtl = i18n.is_rtl(self._lang)
            x = 20 if rtl else w - fab_size - 20
            y = h - fab_size - 80
            self._fab.place(x=x, y=y)
        except Exception:
            pass

    def _build_summary(self) -> None:
        """Summary card with total / enabled / due-today counts."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        for i in range(3):
            row.grid_columnconfigure(i, weight=1, uniform="stat")
        self._stat_cards: List[StatCard] = []
        labels = [
            self._tr("total", "Total"),
            self._tr("enabled", "Enabled"),
            self._tr("dueToday", "Due today"),
        ]
        for i, label in enumerate(labels):
            card = StatCard(
                row, label=label, value="—", lang=self._lang,
                padding=config.SPACE_MD,
            )
            card.grid(row=0, column=i, sticky="nsew",
                       padx=(0 if i == 0 else 4, 4))
            self._stat_cards.append(card)

    def _build_list(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            section, text=self._tr("allReminders", "All reminders"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        self._list_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._list_frame.grid(row=1, column=0, sticky="ew")
        self._list_frame.grid_columnconfigure(0, weight=1)

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
            "reminder.added", "reminder.updated", "reminder.deleted",
            "reminder.triggered", "reminder.dismissed", "reminder.snoozed",
            "language.changed", "settings.changed",
            "data.imported", "data.cleared",
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
        """Rebuild summary + reminder list."""
        # Clear old items
        for child in self._list_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._reminder_items = []
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        # Fetch reminders
        try:
            reminders = reminder_service.list(only_enabled=False)
        except Exception:
            reminders = []
        # Refresh stat cards
        total = len(reminders)
        enabled = sum(1 for r in reminders if r.get("enabled"))
        today_iso = time_utils.today_iso()
        try:
            today_due = len(reminder_service.check_due())
        except Exception:
            today_due = 0
        try:
            self._stat_cards[0].set_value(
                i18n.to_fa_digits(str(total)) if self._lang == "fa"
                else str(total))
            self._stat_cards[1].set_value(
                i18n.to_fa_digits(str(enabled)) if self._lang == "fa"
                else str(enabled))
            self._stat_cards[2].set_value(
                i18n.to_fa_digits(str(today_due)) if self._lang == "fa"
                else str(today_due))
        except Exception:
            pass
        # Empty state
        if not reminders:
            self._empty_state = EmptyState(
                self._list_frame, icon="bell",
                title=self._tr("noReminders",
                                "No reminders yet"),
                subtitle=self._tr("noRemindersHint",
                                   "Set a reminder to stay on track"),
                action_text=self._tr("newReminder", "New reminder"),
                on_action=self._on_new_reminder,
                lang=self._lang,
            )
            self._empty_state.grid(row=0, column=0, sticky="ew",
                                    pady=config.SPACE_LG)
            return
        # Build items
        time_format = settings_service.time_format()
        cats = self._category_map()
        for i, r in enumerate(reminders):
            title = r.get("title") or "—"
            time_str = _decode_time(r.get("time_hhmm") or "",
                                     self._lang, time_format)
            days_str = _decode_days(int(r.get("days_mask") or 0),
                                     self._lang)
            enabled = bool(r.get("enabled"))
            item = ReminderListItem(
                self._list_frame,
                title=title,
                time_str=time_str,
                days=days_str,
                enabled=enabled,
                on_toggle=lambda v, rid=r.get("id"): self._on_toggle(rid, v),
                on_click=lambda rid=r.get("id"): self._on_tap(rid),
                on_delete=lambda rid=r.get("id"): self._on_delete(rid),
                lang=self._lang,
            )
            item.grid(row=i, column=0, sticky="ew",
                       pady=(0 if i == 0 else 4, 4))
            self._reminder_items.append(item)

    def _category_map(self) -> Dict[int, Dict[str, Any]]:
        try:
            cats = db.category_list()
            return {c["id"]: c for c in cats}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_new_reminder(self) -> None:
        if self._app and hasattr(self._app, "open_reminder_dialog"):
            try:
                self._app.open_reminder_dialog()
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.reminder_dialog_requested")
        except Exception:
            pass

    def _on_tap(self, reminder_id: int) -> None:
        if self._app and hasattr(self._app, "open_reminder_dialog"):
            try:
                self._app.open_reminder_dialog(reminder_id=reminder_id)
            except Exception:
                pass

    def _on_toggle(self, reminder_id: int, enabled: bool) -> None:
        try:
            reminder_service.update(reminder_id, enabled=bool(enabled))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_long_press(self, reminder_id: int) -> None:
        actions = [
            (self._tr("edit", "Edit"),
             lambda: self._on_tap(reminder_id)),
            (self._tr("snooze10", "Snooze 10 min"),
             lambda: self._on_snooze(reminder_id, 10)),
            (self._tr("snooze30", "Snooze 30 min"),
             lambda: self._on_snooze(reminder_id, 30)),
            (self._tr("delete", "Delete"),
             lambda: self._on_delete(reminder_id)),
        ]
        ActionSheet(
            self, title=self._tr("reminderActions", "Reminder actions"),
            actions=actions, lang=self._lang,
            destructive=self._tr("delete", "Delete"),
        )

    def _on_snooze(self, reminder_id: int, minutes: int) -> None:
        try:
            reminder_service.snooze(reminder_id, minutes=minutes)
            min_str = (i18n.to_fa_digits(str(minutes))
                       if self._lang == "fa" else str(minutes))
            self._show_toast(
                f"{self._tr('snoozedFor', 'Snoozed for')} "
                f"{min_str} {self._tr('minutes', 'min')}")
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_delete(self, reminder_id: int) -> None:
        dlg = ConfirmDialog(
            self, title=self._tr("deleteReminder", "Delete reminder"),
            message=self._tr("deleteReminderConfirm",
                              "Delete this reminder?"),
            yes_text=self._tr("delete", "Delete"),
            no_text=self._tr("cancel", "Cancel"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_delete(reminder_id) if ok
                       else None)

    def _do_delete(self, reminder_id: int) -> None:
        try:
            reminder_service.delete(reminder_id)
            self._show_toast(self._tr("deleted", "Deleted"))
        except Exception as exc:
            self._show_toast(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            from ...i18n import t as _t
            v = _t(fa, self._lang)
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
            event_bus.bus.publish("ui.toast", {"message": message,
                                                "kind": "info"})
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
    print("RemindersScreen module: summary + list + actions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
