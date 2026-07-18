"""
rask.ui.screens.backup_screen
=============================

Backup screen — encrypted backup / restore UI.

Mirrors ``web/index.html`` ``#screen-backup`` (accessible from the
settings screen) and provides:

    * **Backup Now** — large gold button, opens a password prompt and
      creates an encrypted ``.raskbk`` file in :data:`config.BACKUP_DIR`
    * **Restore from Backup** — opens a file picker + password dialog
      and restores the selected backup
    * **Auto-backup setting** — segmented control (off / daily / weekly /
      monthly)
    * **Last-backup info card** — timestamp, size, status of the most
      recent local backup
    * **Local backups list** — each row shows filename, size, date, with
      actions: Restore, Verify, Delete, Share
    * **Storage usage indicator** — total bytes used by all backups
    * **Backup rotation** — keep last N
    * **Export data** (JSON)
    * **Import data** (JSON file picker)
    * **Clear all data** (strong confirm)

Auto-refresh
------------
Subscribes to ``backup.created`` / ``backup.restored`` /
``settings.changed`` / ``language.changed`` / ``data.imported`` /
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
from ...services import (
    backup_service, export_service, settings_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, DangerButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.empty_state import EmptyState
from ..widgets.inputs import PasswordEntry, GoldEntry
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toggles import SegmentedControl
from ..widgets.sliders import ProgressBar
from ..widgets.sheets import ActionSheet
from ..widgets.dialogs import (
    ConfirmDialog, PromptDialog, AlertDialog, BottomSheet,
)

__all__ = ["BackupScreen"]


# =============================================================================
# === Auto-backup labels                                                     ===
# =============================================================================

AUTO_BACKUP_LABELS_FA: Dict[str, str] = {
    "off": "خاموش",
    "daily": "روزانه",
    "weekly": "هفتگی",
    "monthly": "ماهانه",
}
AUTO_BACKUP_LABELS_EN: Dict[str, str] = {
    "off": "Off",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
}


def _ab_label(value: str, lang: str) -> str:
    if lang == "fa":
        return AUTO_BACKUP_LABELS_FA.get(value, value)
    return AUTO_BACKUP_LABELS_EN.get(value, value)


def _format_size(size_bytes: int, lang: str) -> str:
    """Human-readable file size."""
    try:
        size_bytes = int(size_bytes)
    except (TypeError, ValueError):
        size_bytes = 0
    if size_bytes < 1024:
        s = str(size_bytes)
        unit = "B"
    elif size_bytes < 1024 * 1024:
        s = f"{size_bytes / 1024:.1f}"
        unit = "KB"
    elif size_bytes < 1024 * 1024 * 1024:
        s = f"{size_bytes / (1024 * 1024):.1f}"
        unit = "MB"
    else:
        s = f"{size_bytes / (1024 * 1024 * 1024):.2f}"
        unit = "GB"
    if lang == "fa":
        s = i18n.to_fa_digits(s)
    return f"{s} {unit}"


def _format_date(iso_str: str, lang: str) -> str:
    """Format an ISO timestamp as a localized date string."""
    if not iso_str:
        return "—"
    try:
        # Try Jalali first
        return jalali.format_jalali(iso_str[:10], fmt="long", lang=lang)
    except Exception:
        return iso_str[:10]


# =============================================================================
# === PasswordDialog                                                        ===
# =============================================================================

class _PasswordDialog(BottomSheet):
    """Bottom sheet that prompts for a password."""

    def __init__(
        self,
        master: Any,
        title: str,
        message: str = "",
        confirm_text: str = "تأیید",
        cancel_text: str = "لغو",
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[str]], Any]] = None,
    ) -> None:
        self._message = message
        self._confirm_text = confirm_text
        self._cancel_text = cancel_text
        self._on_result = on_result
        kwargs = {"height": 280}
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        if self._message:
            ctk.CTkLabel(
                self._content, text=self._message,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                wraplength=380,
                anchor="e" if rtl else "w",
            ).pack(fill="x", pady=(0, 8))
        self._entry = PasswordEntry(
            self._content, placeholder="••••••",
            lang=self._lang, height=44,
        )
        self._entry.pack(fill="x", pady=(0, 12))
        try:
            self._entry._entry.bind("<Return>",
                                       lambda _e: self._confirm(), add="+")
        except Exception:
            pass
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        cancel = GhostButton(
            btn_row, text=self._cancel_text,
            command=lambda: self.close(None),
            lang=self._lang, height=38,
        )
        confirm = GoldButton(
            btn_row, text=self._confirm_text,
            command=self._confirm,
            lang=self._lang, height=38,
        )
        if rtl:
            confirm.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            confirm.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        try:
            self._entry._entry.focus_set()
        except Exception:
            pass

    def _confirm(self) -> None:
        pw = self._entry.value
        self.close(pw)

    def close(self, result: Any = None) -> None:
        if self._on_result:
            try:
                self._on_result(result if isinstance(result, str)
                                  else None)
            except Exception:
                pass
        super().close(result)


# =============================================================================
# === BackupScreen                                                           ===
# =============================================================================

class BackupScreen(ctk.CTkFrame):
    """Backup / restore / export screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``confirm_delete(message, on_confirm)``
            * ``reload_ui()``
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
        self._backup_rows: List[ctk.CTkBaseClass] = []
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header with back button
        rtl = i18n.is_rtl(self._lang)
        self._header = Header(
            self, title=self._tr("backup", "Backup"),
            back_icon=True,
            on_back=self._on_back,
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
        # Sections
        self._section_row = 0
        self._build_actions_card()
        self._build_auto_backup_card()
        self._build_last_backup_card()
        self._build_storage_card()
        self._build_local_backups_list()
        self._build_data_section()
        Spacer(self._scroll, height=config.SPACE_XXL).grid(
            row=self._next_row(), column=0, sticky="ew")

    def _build_actions_card(self) -> None:
        """Backup Now + Restore buttons."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                                   config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        # Big "Backup Now" button
        self._backup_now_btn = GoldButton(
            section, text=self._tr("backupNow", "Backup now"),
            command=self._on_backup_now, lang=self._lang,
            height=52, font_size=config.FONT_SIZE_BODY_LG,
            icon_name="download",
        )
        self._backup_now_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        # Restore button
        self._restore_btn = GhostButton(
            section, text=self._tr("restoreBackup", "Restore from backup"),
            command=self._on_restore, lang=self._lang,
            height=44, font_size=config.FONT_SIZE_BODY,
            icon_name="upload",
        )
        self._restore_btn.grid(row=1, column=0, sticky="ew")

    def _build_auto_backup_card(self) -> None:
        """Auto-backup frequency picker."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_SM)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Title
        ctk.CTkLabel(
            card.content, text=self._tr("autoBackup", "Auto-backup"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Hint
        ctk.CTkLabel(
            card.content,
            text=self._tr("autoBackupHint",
                           "Automatically back up to a password-protected file"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w", wraplength=380,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Segmented control
        ab_labels = [
            _ab_label(v, self._lang)
            for v in ("off", "daily", "weekly", "monthly")
        ]
        self._ab_seg = SegmentedControl(
            card.content, values=ab_labels, lang=self._lang,
            on_change=lambda v: self._on_ab_change(v, ab_labels),
            height=36,
        )
        self._ab_seg.grid(row=2, column=0, sticky="ew",
                            pady=(config.SPACE_MD, 0))
        # Next-scheduled label
        self._next_scheduled_label = ctk.CTkLabel(
            card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
        )
        self._next_scheduled_label.grid(row=3, column=0, sticky="ew",
                                          pady=(4, 0))

    def _build_last_backup_card(self) -> None:
        """Last backup info: timestamp, size, status."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_SM)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Title
        ctk.CTkLabel(
            card.content, text=self._tr("lastBackup", "Last backup"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Date
        self._last_date_label = ctk.CTkLabel(
            card.content, text="—",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._last_date_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Size + status row
        info_row = ctk.CTkFrame(card.content, fg_color="transparent")
        info_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        info_row.grid_columnconfigure(1, weight=1)
        self._last_size_label = ctk.CTkLabel(
            info_row, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        )
        self._last_size_label.grid(row=0, column=0,
                                     sticky="e" if rtl else "w")
        self._last_status_label = ctk.CTkLabel(
            info_row, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.SUCCESS,
        )
        self._last_status_label.grid(row=0, column=1,
                                       sticky="e" if rtl else "w")

    def _build_storage_card(self) -> None:
        """Storage usage indicator."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_SM)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=self._tr("storageUsage", "Storage usage"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._storage_size_label = ctk.CTkLabel(
            card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        )
        self._storage_size_label.grid(row=1, column=0, sticky="ew",
                                        pady=(4, 0))
        self._storage_progress = ProgressBar(
            card.content, value=0.0, height=6, animated=True,
        )
        self._storage_progress.grid(row=2, column=0, sticky="ew",
                                      pady=(config.SPACE_SM, 0))
        self._storage_count_label = ctk.CTkLabel(
            card.content, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        )
        self._storage_count_label.grid(row=3, column=0, sticky="ew",
                                         pady=(2, 0))

    def _build_local_backups_list(self) -> None:
        """List of local backups with actions per row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_SM)
        section.grid_columnconfigure(0, weight=1)
        # Header row: title + rotation button
        header_row = ctk.CTkFrame(section, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            header_row, text=self._tr("localBackups", "Local backups"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        TextButton(
            header_row, text=self._tr("rotation", "Rotation"),
            command=self._on_rotation, lang=self._lang, height=28,
            color=config.GOLD, font_size=config.FONT_SIZE_CAPTION,
        ).grid(row=0, column=1, sticky="e" if rtl else "w")
        self._backups_frame = ctk.CTkFrame(section, fg_color="transparent")
        self._backups_frame.grid(row=1, column=0, sticky="ew",
                                   pady=(config.SPACE_SM, 0))
        self._backups_frame.grid_columnconfigure(0, weight=1)

    def _build_data_section(self) -> None:
        """Export / Import / Clear data row."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_SM)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=self._tr("dataManagement", "Data management"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Export
        GoldButton(
            card.content, text=self._tr("exportJson", "Export (JSON)"),
            command=self._on_export, lang=self._lang,
            height=40, font_size=config.FONT_SIZE_BODY,
            icon_name="share",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 4))
        # Import
        GhostButton(
            card.content, text=self._tr("importJson", "Import (JSON)"),
            command=self._on_import, lang=self._lang,
            height=40, font_size=config.FONT_SIZE_BODY,
            icon_name="upload",
        ).grid(row=2, column=0, sticky="ew", pady=4)
        # Clear all data (danger)
        DangerButton(
            card.content, text=self._tr("clearAllData", "Clear all data"),
            command=self._on_clear_data, lang=self._lang,
            height=40, font_size=config.FONT_SIZE_BODY,
            icon_name="trash",
        ).grid(row=3, column=0, sticky="ew", pady=4)

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
            "backup.created", "backup.restored",
            "settings.changed", "language.changed",
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
        """Re-render every section with the latest data."""
        self._refresh_auto_backup()
        self._refresh_last_backup()
        self._refresh_storage()
        self._refresh_local_list()

    def _refresh_auto_backup(self) -> None:
        try:
            cur = settings_service.auto_backup()
            labels = [_ab_label(v, self._lang)
                       for v in ("off", "daily", "weekly", "monthly")]
            target = _ab_label(cur, self._lang)
            if target in labels:
                self._ab_seg.value = target
        except Exception:
            pass
        # Next-scheduled
        try:
            nxt = backup_service.next_scheduled()
            if nxt:
                date_str = _format_date(nxt, self._lang)
                text = (f"{self._tr('nextBackup', 'Next backup')}: "
                        f"{date_str}")
                self._next_scheduled_label.configure(text=text)
            else:
                self._next_scheduled_label.configure(text="")
        except Exception:
            pass

    def _refresh_last_backup(self) -> None:
        try:
            last = backup_service.last_backup()
            if last:
                created = last.get("created_at") or ""
                date_str = _format_date(created, self._lang)
                self._last_date_label.configure(text=date_str)
                size_str = _format_size(int(last.get("size", 0) or 0),
                                         self._lang)
                self._last_size_label.configure(text=size_str)
                status = (self._tr("valid", "Valid")
                           if last.get("valid")
                           else self._tr("invalid", "Invalid"))
                color = config.SUCCESS if last.get("valid") else config.DANGER
                self._last_status_label.configure(text=status,
                                                    text_color=color)
            else:
                self._last_date_label.configure(text="—")
                self._last_size_label.configure(text="")
                self._last_status_label.configure(text="")
        except Exception:
            pass

    def _refresh_storage(self) -> None:
        try:
            backups = backup_service.list_local()
            total = sum(int(b.get("size", 0) or 0) for b in backups)
            count = len(backups)
            size_str = _format_size(total, self._lang)
            self._storage_size_label.configure(text=size_str)
            # Progress bar — assume 100 MB cap for visualization
            cap = 100 * 1024 * 1024
            pct = min(1.0, total / cap) if cap else 0.0
            self._storage_progress.set_value(pct, animate=True)
            count_str = (i18n.to_fa_digits(str(count))
                          if self._lang == "fa" else str(count))
            self._storage_count_label.configure(
                text=f"{count_str} {self._tr('files', 'files')}")
        except Exception:
            pass

    def _refresh_local_list(self) -> None:
        """Rebuild the local backups list."""
        for child in self._backups_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._backup_rows = []
        try:
            backups = backup_service.list_local()
        except Exception:
            backups = []
        if not backups:
            EmptyState(
                self._backups_frame, icon="database",
                title=self._tr("noBackups", "No backups yet"),
                subtitle=self._tr("noBackupsHint",
                                   "Tap Backup Now to create one"),
                lang=self._lang,
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_MD)
            return
        # Build a row per backup
        for i, b in enumerate(backups):
            row = self._build_backup_row(b)
            row.grid(row=i, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 4))

    def _build_backup_row(self, backup: Dict[str, Any]) -> ctk.CTkFrame:
        """Build a single backup-file row."""
        rtl = i18n.is_rtl(self._lang)
        row = ctk.CTkFrame(self._backups_frame, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER,
                           padding=config.SPACE_MD)
        row.grid_columnconfigure(1, weight=1)
        # Icon (leading)
        icon_label = ctk.CTkLabel(row, text="", width=32, height=32,
                                   fg_color="transparent")
        img = _icons.icon("database", 22, color=config.GOLD)
        if img is not None:
            icon_label.configure(image=img)
        else:
            icon_label.configure(text=_icons.icon_glyph("database"),
                                  text_color=config.GOLD)
        icon_label.grid(row=0, column=0, padx=4, sticky="nsew")
        # Filename + date column
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=4)
        info.grid_columnconfigure(0, weight=1)
        filename = backup.get("filename") or "—"
        ctk.CTkLabel(
            info, text=filename,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        date_str = _format_date(backup.get("created_at", ""), self._lang)
        size_str = _format_size(int(backup.get("size", 0) or 0), self._lang)
        meta_text = f"{date_str} · {size_str}"
        ctk.CTkLabel(
            info, text=meta_text,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM, anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Action buttons (trailing)
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=2, padx=4, sticky="nsew")
        IconButton(
            actions, icon_name="upload",
            command=lambda p=backup.get("path"): self._on_restore_file(p),
            size=32, lang=self._lang,
        ).pack(side="right" if rtl else "left", padx=2)
        IconButton(
            actions, icon_name="check",
            command=lambda p=backup.get("path"): self._on_verify_file(p),
            size=32, lang=self._lang,
        ).pack(side="right" if rtl else "left", padx=2)
        IconButton(
            actions, icon_name="share",
            command=lambda p=backup.get("path"): self._on_share_file(p),
            size=32, lang=self._lang,
        ).pack(side="right" if rtl else "left", padx=2)
        IconButton(
            actions, icon_name="trash",
            command=lambda p=backup.get("path"): self._on_delete_file(p),
            size=32, lang=self._lang, hover_color=config.DANGER_DIM,
        ).pack(side="right" if rtl else "left", padx=2)
        self._backup_rows.append(row)
        return row

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_back(self) -> None:
        if self._app and hasattr(self._app, "switch_tab"):
            try:
                self._app.switch_tab("settings")
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.tab_changed", {"tab": "settings"})
        except Exception:
            pass

    def _on_backup_now(self) -> None:
        """Open password dialog and create a backup."""
        dlg = _PasswordDialog(
            self, title=self._tr("backupNow", "Backup now"),
            message=self._tr("backupPasswordHint",
                              "Enter a password to encrypt the backup"),
            confirm_text=self._tr("backup", "Backup"),
            cancel_text=self._tr("cancel", "Cancel"),
            lang=self._lang,
            on_result=lambda pw: self._do_backup(pw) if pw else None,
        )

    def _do_backup(self, password: str) -> None:
        if not password or len(password) < 4:
            self._show_toast(self._tr("passwordTooShort",
                                       "Password too short"))
            return
        try:
            self._backup_now_btn.configure(state="disabled",
                                             text=self._tr("creating",
                                                            "Creating…"))
        except Exception:
            pass
        # Defer to next tick so the UI updates
        self.after(50, lambda: self._do_backup_step(password))

    def _do_backup_step(self, password: str) -> None:
        try:
            result = backup_service.create(password=password)
            if result.get("success"):
                size_str = _format_size(int(result.get("size", 0)),
                                          self._lang)
                self._show_toast(
                    f"{self._tr('backupCreated', 'Backup created')} · "
                    f"{size_str}")
            else:
                self._show_toast(result.get("error",
                                              self._tr("backupFailed",
                                                        "Backup failed")))
        except Exception as exc:
            self._show_toast(str(exc))
        finally:
            try:
                self._backup_now_btn.configure(
                    state="normal",
                    text=self._tr("backupNow", "Backup now"))
            except Exception:
                pass
            self.refresh()

    def _on_restore(self) -> None:
        """File picker + password dialog + restore."""
        path = self._pick_file(
            title=self._tr("selectBackup", "Select backup file"),
            filetypes=(("Rask backup", "*.raskbk"), ("All files", "*.*")))
        if not path:
            return
        dlg = _PasswordDialog(
            self, title=self._tr("restoreBackup", "Restore"),
            message=self._tr("restorePasswordHint",
                              "Enter the backup password"),
            confirm_text=self._tr("restore", "Restore"),
            cancel_text=self._tr("cancel", "Cancel"),
            lang=self._lang,
            on_result=lambda pw: self._do_restore(path, pw) if pw
            else None,
        )

    def _do_restore(self, path: str, password: str) -> None:
        try:
            result = backup_service.restore(path, password)
            if result.get("success"):
                cnt = int(result.get("record_count", 0) or 0)
                cnt_str = (i18n.to_fa_digits(str(cnt))
                            if self._lang == "fa" else str(cnt))
                self._show_toast(
                    f"{self._tr('restoreDone', 'Restored')} · "
                    f"{cnt_str} {self._tr('records', 'records')}")
                # Reload UI
                if self._app and hasattr(self._app, "reload_ui"):
                    try:
                        self._app.reload_ui()
                    except Exception:
                        pass
            else:
                self._show_toast(result.get("error",
                                              self._tr("restoreFailed",
                                                        "Restore failed")))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_restore_file(self, path: str) -> None:
        """Restore action from a list row."""
        self._on_restore()  # use the file picker — simpler & safer
        # Or: skip file picker and use the path directly
        # dlg = _PasswordDialog(...); on_result -> _do_restore(path, pw)

    def _on_verify_file(self, path: str) -> None:
        """Verify a backup file's integrity."""
        # No password needed — just check header
        try:
            meta = backup_service.export_metadata(path)
            if meta.get("valid"):
                size_str = _format_size(int(meta.get("size", 0)),
                                          self._lang)
                self._show_toast(
                    f"{self._tr('fileValid', 'File valid')} · "
                    f"{size_str}")
            else:
                self._show_toast(self._tr("fileInvalid",
                                            "File invalid or corrupt"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_share_file(self, path: str) -> None:
        """Open the OS file manager at the backup location."""
        try:
            export_service.open_in_file_manager(path)
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_delete_file(self, path: str) -> None:
        """Confirm and delete a backup file."""
        dlg = ConfirmDialog(
            self, title=self._tr("deleteBackup", "Delete backup"),
            message=self._tr("deleteBackupConfirm",
                              "Delete this backup file?"),
            yes_text=self._tr("delete", "Delete"),
            no_text=self._tr("cancel", "Cancel"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_delete_file(path) if ok
                       else None)

    def _do_delete_file(self, path: str) -> None:
        try:
            ok = backup_service.delete(path)
            if ok:
                self._show_toast(self._tr("deleted", "Deleted"))
            else:
                self._show_toast(self._tr("deleteFailed",
                                            "Delete failed"))
        except Exception as exc:
            self._show_toast(str(exc))
        self.refresh()

    def _on_rotation(self) -> None:
        """Open a prompt to set the keep-N rotation count."""
        try:
            cur = config.BACKUP_KEEP_LOCAL
            dlg = PromptDialog(
                self, title=self._tr("rotation", "Rotation"),
                message=self._tr("rotationHint",
                                  "Keep the N most recent backups"),
                initial=str(cur), lang=self._lang,
            )
            dlg.on_result(lambda v: self._apply_rotation(v) if v
                           else None)
        except Exception:
            pass

    def _apply_rotation(self, value: str) -> None:
        try:
            n = int(value)
            if n < 1:
                n = 1
            deleted = backup_service.rotate(keep=n)
            if deleted:
                d_str = (i18n.to_fa_digits(str(deleted))
                          if self._lang == "fa" else str(deleted))
                self._show_toast(
                    f"{self._tr('rotated', 'Rotated')} · "
                    f"{d_str} {self._tr('removed', 'removed')}")
            else:
                self._show_toast(self._tr("nothingToDo",
                                            "Nothing to rotate"))
        except ValueError:
            self._show_toast(self._tr("invalidNumber",
                                        "Invalid number"))
        except Exception as exc:
            self._show_toast(str(exc))
        self.refresh()

    def _on_ab_change(self, label: str, labels: List[str]) -> None:
        vals = ("off", "daily", "weekly", "monthly")
        if label not in labels:
            return
        v = vals[labels.index(label)]
        try:
            settings_service.set_auto_backup(v)
        except Exception:
            pass
        self.refresh()

    # --- Data management ---
    def _on_export(self) -> None:
        try:
            today = time_utils.today_iso()
            year_ago = time_utils.add_days(today, -365)
            result = export_service.export_json(year_ago, today)
            if result.get("success"):
                self._show_toast(self._tr("exportDone",
                                            "Export complete"))
            else:
                self._show_toast(result.get("error") or
                                  self._tr("exportFailed",
                                            "Export failed"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_import(self) -> None:
        path = self._pick_file(
            title=self._tr("selectJson", "Select JSON file"),
            filetypes=(("JSON", "*.json"), ("All files", "*.*")))
        if not path:
            return
        dlg = ConfirmDialog(
            self, title=self._tr("importData", "Import data"),
            message=self._tr("importConfirm",
                              "This will replace current data. Continue?"),
            yes_text=self._tr("yes", "Yes"),
            no_text=self._tr("no", "No"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_import(path) if ok else None)

    def _do_import(self, path: str) -> None:
        import json
        from pathlib import Path
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            db.import_from_dict(data, replace=True)
            self._show_toast(self._tr("importDone",
                                        "Import complete"))
            if self._app and hasattr(self._app, "reload_ui"):
                try:
                    self._app.reload_ui()
                except Exception:
                    pass
        except Exception as exc:
            self._show_toast(self._tr("importFailed",
                                        "Import failed") + f": {exc}")

    def _on_clear_data(self) -> None:
        dlg = ConfirmDialog(
            self, title=self._tr("clearAllData", "Clear all data"),
            message=self._tr("clearDataConfirm",
                              "This will PERMANENTLY delete all activities, "
                              "goals, streaks, templates, badges, and "
                              "reminders. This cannot be undone. Continue?"),
            yes_text=self._tr("clear", "Clear"),
            no_text=self._tr("cancel", "Cancel"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_clear_data() if ok else None)

    def _do_clear_data(self) -> None:
        try:
            for table in ("activities", "categories", "goals", "streaks",
                           "templates", "badges", "reminders", "recurring",
                           "sessions", "tags", "activity_tags"):
                try:
                    db.get_conn().execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            try:
                db.get_conn().commit()
            except Exception:
                pass
            try:
                event_bus.bus.publish("data.cleared", {})
            except Exception:
                pass
            self._show_toast(self._tr("dataCleared",
                                        "Data cleared"))
            if self._app and hasattr(self._app, "reload_ui"):
                try:
                    self._app.reload_ui()
                except Exception:
                    pass
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

    def _pick_file(self, title: str = "Open",
                   filetypes: tuple = (("All files", "*.*"),)) -> Optional[str]:
        try:
            from tkinter import filedialog
            return filedialog.askopenfilename(title=title,
                                              filetypes=filetypes)
        except Exception:
            return None

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
    print("BackupScreen module: actions + auto-backup + last + storage + "
          "local list + data mgmt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
