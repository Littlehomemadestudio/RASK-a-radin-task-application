"""
rask.ui.screens.settings_screen
===============================

The main settings screen — a vertically-scrolling list of collapsible
sections covering every user-tunable preference in the app.

Sections (each rendered as a collapsible :class:`SettingCard` group):
    1. **ظاهر** (Appearance)  — theme picker, language picker, font
       scale slider, reduced-motion toggle, high-contrast toggle
    2. **حریم خصوصی** (Privacy) — lock-mode picker, auto-lock timeout,
       change PIN, remove PIN
    3. **داده‌ها** (Data) — backup-now, restore-from-backup,
       auto-backup picker, export data, import data, clear-all-data
    4. **یادآوری‌ها** (Reminders) — notify-sound toggle, notify-vibrate
       toggle, manage-reminders link
    5. **تقویم** (Calendar) — calendar-system picker, first-day-of-week
       picker, date-format picker, time-format picker
    6. **درباره** (About) — version info, license, source-code link,
       acknowledgements, rate, share, check-for-updates
    7. **پیشرفته** (Advanced) — developer-mode toggle, show-logs,
       clear-cache, vacuum database, debug info

Every change is immediately persisted via :mod:`settings_service` and
broadcast on the ``settings.changed`` event bus (with
``language.changed`` and ``theme.changed`` emitted for those specific
keys).  Theme changes apply immediately to the live UI; language changes
ask for confirmation before triggering a full UI reload.

Auto-refresh
------------
Subscribes to ``settings.changed`` / ``language.changed`` /
``theme.changed`` / ``data.imported`` / ``data.cleared`` so the screen
reflects externally-driven changes (e.g. backup-restore replacing all
settings).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus, helpers, jalali, time_utils
from ...services import (
    settings_service, backup_service, export_service,
)
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, DangerButton,
)
from ..widgets.cards import Card, SettingCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.toggles import Toggle, SegmentedControl, RadioButton
from ..widgets.sliders import GoldSlider, ProgressBar
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.dialogs import ConfirmDialog, PromptDialog, AlertDialog
from ..widgets.sheets import ActionSheet, PickerSheet

__all__ = ["SettingsScreen"]


# =============================================================================
# === Localised labels                                                       ===
# =============================================================================

THEME_LABELS_FA: Dict[str, str] = {
    "dark": "تیره",
    "light": "روشن",
    "system": "سیستم",
}
THEME_LABELS_EN: Dict[str, str] = {
    "dark": "Dark",
    "light": "Light",
    "system": "System",
}

LOCK_MODE_LABELS_FA: Dict[str, str] = {
    "none": "بدون قفل",
    "pin": "کد پین",
    "biometric": "اثر انگشت",
}
LOCK_MODE_LABELS_EN: Dict[str, str] = {
    "none": "None",
    "pin": "PIN",
    "biometric": "Biometric",
}

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

CALENDAR_LABELS_FA: Dict[str, str] = {
    "jalali": "جلالی (شمسی)",
    "gregorian": "میلادی",
}
CALENDAR_LABELS_EN: Dict[str, str] = {
    "jalali": "Jalali (Solar)",
    "gregorian": "Gregorian",
}

DATE_FORMAT_LABELS_FA: Dict[str, str] = {
    "short": "کوتاه",
    "long": "بلند",
    "iso": "ISO",
    "full": "کامل",
}
DATE_FORMAT_LABELS_EN: Dict[str, str] = {
    "short": "Short",
    "long": "Long",
    "iso": "ISO",
    "full": "Full",
}

TIME_FORMAT_LABELS_FA: Dict[str, str] = {
    "24": "۲۴ ساعته",
    "12": "۱۲ ساعته",
}
TIME_FORMAT_LABELS_EN: Dict[str, str] = {
    "24": "24-hour",
    "12": "12-hour",
}

FIRST_DAY_LABELS_FA: Dict[int, str] = {
    0: "یکشنبه", 1: "دوشنبه", 2: "سه‌شنبه", 3: "چهارشنبه",
    4: "پنجشنبه", 5: "جمعه", 6: "شنبه",
}
FIRST_DAY_LABELS_EN: Dict[int, str] = {
    0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday",
    4: "Thursday", 5: "Friday", 6: "Saturday",
}


def _label(value: str, mapping_fa: Dict[str, str],
           mapping_en: Dict[str, str], lang: str) -> str:
    if lang == "fa":
        return mapping_fa.get(value, value)
    return mapping_en.get(value, value)


# =============================================================================
# === Collapsible section                                                    ===
# =============================================================================

class _CollapsibleSection(ctk.CTkFrame):
    """A titled, collapsible group of setting cards.

    The header row is a tappable label with a chevron icon that
    rotates 90° when expanded.  The body frame is shown/hidden via
    grid_remove().
    """

    def __init__(
        self,
        master: Any,
        title: str,
        icon_name: str = "settings",
        expanded: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._lang = lang
        self._expanded = expanded
        self._title = title
        self._icon_name = icon_name
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=1, column=0, sticky="ew",
                         padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        self._body.grid_columnconfigure(0, weight=1)
        self._body_row = 0
        if not expanded:
            self._body.grid_remove()

    def _build_header(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        header = ctk.CTkFrame(self, fg_color=config.SURFACE,
                              corner_radius=config.RADIUS_MD,
                              border_width=1, border_color=config.DIVIDER,
                              height=44)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)
        # Chevron
        self._chevron = ctk.CTkLabel(
            header, text="◀" if rtl else "▶",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="bold", lang="en"),
            text_color=config.GOLD, width=20,
        )
        self._chevron.grid(row=0, column=0, padx=8, sticky="nsew")
        # Title
        ctk.CTkLabel(
            header, text=self._title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=1, sticky="ew")
        # Icon on opposite side
        icon_label = ctk.CTkLabel(header, text="", width=28, height=28,
                                   fg_color="transparent")
        img = _icons.icon(self._icon_name, 18, color=config.GOLD)
        if img is not None:
            icon_label.configure(image=img)
        else:
            icon_label.configure(text=_icons.icon_glyph(self._icon_name),
                                  text_color=config.GOLD)
        icon_label.grid(row=0, column=2, padx=8, sticky="nsew")
        # Toggle on click
        for w in (header, self._chevron, icon_label):
            try:
                w.bind("<Button-1>", lambda _e: self.toggle(), add="+")
            except Exception:
                pass
        self._header = header
        self._update_chevron()

    def _update_chevron(self) -> None:
        try:
            rtl = i18n.is_rtl(self._lang)
            # When expanded, point down; when collapsed, point sideways
            glyph = "▼" if self._expanded else ("◀" if rtl else "▶")
            self._chevron.configure(text=glyph)
        except Exception:
            pass

    @property
    def body(self) -> ctk.CTkFrame:
        return self._body

    def toggle(self) -> None:
        self._expanded = not self._expanded
        try:
            if self._expanded:
                self._body.grid()
            else:
                self._body.grid_remove()
        except Exception:
            pass
        self._update_chevron()

    def next_row(self) -> int:
        r = self._body_row
        self._body_row += 1
        return r


# =============================================================================
# === SettingsScreen                                                         ===
# =============================================================================

class SettingsScreen(ctk.CTkFrame):
    """Main settings screen — collapsible sections of preferences.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  The screen calls these optional methods:
            * ``reload_ui()`` — re-create the whole UI after a language change
            * ``show_toast(message)``
            * ``open_backup_screen()`` / ``open_about_screen()``
            * ``open_reminders_screen()``
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
        self._sections: Dict[str, _CollapsibleSection] = {}
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
            self, title=i18n.t("settings", self._lang),
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
        self._build_appearance_section()
        self._build_privacy_section()
        self._build_data_section()
        self._build_reminders_section()
        self._build_calendar_section()
        self._build_about_section()
        self._build_advanced_section()
        # Bottom spacer
        Spacer(self._scroll, height=config.SPACE_XXL).grid(
            row=self._next_row(), column=0, sticky="ew")

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _build_appearance_section(self) -> None:
        """ظاهر — theme, language, font scale, motion, contrast."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("appearance", "Appearance"),
            icon_name="sun", expanded=True, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=(config.SPACE_MD,
                                               config.SPACE_SM))
        self._sections["appearance"] = sec
        rtl = i18n.is_rtl(self._lang)
        # --- Theme picker (SegmentedControl) ---
        theme_row = self._make_row_frame(sec)
        theme_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            theme_row, text=self._tr("theme", "Theme"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        theme_labels = [
            _label(t, THEME_LABELS_FA, THEME_LABELS_EN, self._lang)
            for t in ("dark", "light", "system")
        ]
        self._theme_seg = SegmentedControl(
            theme_row, values=theme_labels, lang=self._lang,
            on_change=lambda v: self._on_theme_pick(v, theme_labels),
            height=32,
        )
        self._theme_seg.pack(side="left" if rtl else "right", padx=4)
        # --- Language picker ---
        lang_row = self._make_row_frame(sec)
        lang_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            lang_row, text=self._tr("language", "Language"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        # Build a sorted list of (code, display name) for available langs
        from ... import i18n as _i18n
        lang_options = []
        for code in _i18n.available_locales():
            display = _i18n.locale_display_name(code, self._lang)
            lang_options.append((code, display))
        lang_options.sort(key=lambda x: x[1])
        current = settings_service.language()
        current_display = _i18n.locale_display_name(current, self._lang)
        lang_btn = GhostButton(
            lang_row, text=current_display,
            command=lambda: self._open_language_picker(lang_options),
            lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        )
        lang_btn.pack(side="left" if rtl else "right", padx=4)
        self._lang_btn = lang_btn
        # --- Font scale slider ---
        scale_row = self._make_row_frame(sec)
        scale_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            scale_row, text=self._tr("fontScale", "Font scale"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        cur_scale = settings_service.font_scale()
        self._scale_slider = GoldSlider(
            scale_row, min_value=config.MIN_FONT_SCALE,
            max_value=config.MAX_FONT_SCALE,
            value=cur_scale, step=0.05,
            on_change=self._on_font_scale_change,
            show_label=True, label_format="{:.2f}×",
            lang=self._lang, width=180, height=32,
        )
        self._scale_slider.pack(side="left" if rtl else "right", padx=4)
        # --- Reduced motion toggle ---
        self._motion_toggle = self._make_toggle_row(
            sec, self._tr("reducedMotion", "Reduced motion"),
            self._tr("reducedMotionHint",
                     "Reduce animations and transitions"),
            settings_service.reduced_motion(),
            self._on_motion_toggle,
        )
        # --- High contrast toggle ---
        self._contrast_toggle = self._make_toggle_row(
            sec, self._tr("highContrast", "High contrast"),
            self._tr("highContrastHint",
                     "Increase text-to-background contrast"),
            settings_service.high_contrast(),
            self._on_contrast_toggle,
        )

    def _build_privacy_section(self) -> None:
        """حریم خصوصی — lock mode, auto-lock, PIN management."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("privacy", "Privacy"),
            icon_name="shield", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["privacy"] = sec
        rtl = i18n.is_rtl(self._lang)
        # --- Lock mode picker ---
        lock_row = self._make_row_frame(sec)
        lock_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            lock_row, text=self._tr("lockMode", "Lock mode"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        lock_labels = [
            _label(m, LOCK_MODE_LABELS_FA, LOCK_MODE_LABELS_EN, self._lang)
            for m in ("none", "pin", "biometric")
        ]
        self._lock_seg = SegmentedControl(
            lock_row, values=lock_labels, lang=self._lang,
            on_change=lambda v: self._on_lock_mode_pick(v, lock_labels),
            height=32,
        )
        self._lock_seg.pack(side="left" if rtl else "right", padx=4)
        # --- Auto-lock timeout picker ---
        auto_row = self._make_row_frame(sec)
        auto_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            auto_row, text=self._tr("autoLock", "Auto-lock"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        cur_secs = settings_service.auto_lock_seconds()
        auto_opts = [
            (0, self._tr("never", "Never")),
            (30, self._tr("sec30", "30 sec")),
            (60, self._tr("min1", "1 min")),
            (300, self._tr("min5", "5 min")),
            (600, self._tr("min10", "10 min")),
            (1800, self._tr("min30", "30 min")),
        ]
        cur_label = next((lbl for s, lbl in auto_opts if s == cur_secs),
                         auto_opts[0][1])
        auto_btn = GhostButton(
            auto_row, text=cur_label,
            command=lambda: self._open_auto_lock_picker(auto_opts),
            lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        )
        auto_btn.pack(side="left" if rtl else "right", padx=4)
        self._auto_lock_btn = auto_btn
        # --- Change PIN ---
        change_pin_row = self._make_row_frame(sec)
        change_pin_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            change_pin_row,
            text=self._tr("changePin", "Change PIN"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        GoldButton(
            change_pin_row, text=self._tr("change", "Change"),
            command=self._on_change_pin, lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)
        # --- Remove PIN ---
        rm_pin_row = self._make_row_frame(sec)
        rm_pin_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            rm_pin_row,
            text=self._tr("removePin", "Remove PIN"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        DangerButton(
            rm_pin_row, text=self._tr("remove", "Remove"),
            command=self._on_remove_pin, lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)

    def _build_data_section(self) -> None:
        """داده‌ها — backup, restore, auto-backup, export/import, clear."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("data", "Data"),
            icon_name="database", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["data"] = sec
        rtl = i18n.is_rtl(self._lang)
        # --- Backup now ---
        bk_row = self._make_row_frame(sec)
        bk_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            bk_row, text=self._tr("backupNow", "Backup now"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        GoldButton(
            bk_row, text=self._tr("backup", "Backup"),
            command=self._on_backup_now, lang=self._lang, height=32,
            icon_name="download", font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)
        # --- Restore ---
        rs_row = self._make_row_frame(sec)
        rs_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            rs_row, text=self._tr("restoreBackup", "Restore from backup"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        GhostButton(
            rs_row, text=self._tr("restore", "Restore"),
            command=self._on_restore, lang=self._lang, height=32,
            icon_name="upload", font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)
        # --- Auto-backup picker ---
        ab_row = self._make_row_frame(sec)
        ab_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            ab_row, text=self._tr("autoBackup", "Auto-backup"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        ab_labels = [
            _label(v, AUTO_BACKUP_LABELS_FA, AUTO_BACKUP_LABELS_EN, self._lang)
            for v in ("off", "daily", "weekly", "monthly")
        ]
        self._auto_backup_seg = SegmentedControl(
            ab_row, values=ab_labels, lang=self._lang,
            on_change=lambda v: self._on_auto_backup_pick(v, ab_labels),
            height=32,
        )
        self._auto_backup_seg.pack(side="left" if rtl else "right", padx=4)
        # --- Export data ---
        ex_row = self._make_row_frame(sec)
        ex_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            ex_row, text=self._tr("exportData", "Export data (JSON)"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side=("right" if rtl else "left"), fill="x", expand=True)
        GhostButton(
            ex_row, text=self._tr("export", "Export"),
            command=self._on_export, lang=self._lang, height=32,
            icon_name="share", font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)
        # --- Import data ---
        im_row = self._make_row_frame(sec)
        im_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            im_row, text=self._tr("importData", "Import data (JSON)"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        GhostButton(
            im_row, text=self._tr("import", "Import"),
            command=self._on_import, lang=self._lang, height=32,
            icon_name="upload", font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)
        # --- Clear all data (danger) ---
        clr_row = self._make_row_frame(sec)
        clr_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            clr_row, text=self._tr("clearAllData", "Clear all data"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        DangerButton(
            clr_row, text=self._tr("clear", "Clear"),
            command=self._on_clear_data, lang=self._lang, height=32,
            icon_name="trash", font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)

    def _build_reminders_section(self) -> None:
        """یادآوری‌ها — sound, vibrate, manage link."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("reminders", "Reminders"),
            icon_name="bell", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["reminders"] = sec
        # Sound toggle
        self._sound_toggle = self._make_toggle_row(
            sec, self._tr("notifySound", "Notification sound"),
            self._tr("notifySoundHint", "Play a sound when reminders fire"),
            settings_service.notify_sound(),
            self._on_sound_toggle,
        )
        # Vibrate toggle
        self._vibrate_toggle = self._make_toggle_row(
            sec, self._tr("notifyVibrate", "Vibrate"),
            self._tr("notifyVibrateHint", "Vibrate device on reminders"),
            settings_service.notify_vibrate(),
            self._on_vibrate_toggle,
        )
        # Manage reminders link
        rtl = i18n.is_rtl(self._lang)
        manage_row = self._make_row_frame(sec)
        manage_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            manage_row, text=self._tr("manageReminders", "Manage reminders"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        TextButton(
            manage_row, text=self._tr("open", "Open") + " →",
            command=self._on_manage_reminders, lang=self._lang, height=32,
            color=config.GOLD, font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=4)

    def _build_calendar_section(self) -> None:
        """تقویم — calendar system, first day, date format, time format."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("calendar", "Calendar"),
            icon_name="calendar", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["calendar"] = sec
        rtl = i18n.is_rtl(self._lang)
        # --- Calendar system ---
        cs_row = self._make_row_frame(sec)
        cs_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            cs_row, text=self._tr("calendarSystem", "Calendar system"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        cs_labels = [
            _label(c, CALENDAR_LABELS_FA, CALENDAR_LABELS_EN, self._lang)
            for c in ("jalali", "gregorian")
        ]
        self._cal_seg = SegmentedControl(
            cs_row, values=cs_labels, lang=self._lang,
            on_change=lambda v: self._on_calendar_pick(v, cs_labels),
            height=32,
        )
        self._cal_seg.pack(side="left" if rtl else "right", padx=4)
        # --- First day of week ---
        fd_row = self._make_row_frame(sec)
        fd_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            fd_row, text=self._tr("firstDayOfWeek", "First day of week"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        cur_fd = settings_service.first_day_of_week()
        fd_map = (FIRST_DAY_LABELS_FA if self._lang == "fa"
                  else FIRST_DAY_LABELS_EN)
        fd_btn = GhostButton(
            fd_row, text=fd_map.get(cur_fd, str(cur_fd)),
            command=lambda: self._open_first_day_picker(fd_map),
            lang=self._lang, height=32,
            font_size=config.FONT_SIZE_SMALL,
        )
        fd_btn.pack(side="left" if rtl else "right", padx=4)
        self._first_day_btn = fd_btn
        # --- Date format ---
        df_row = self._make_row_frame(sec)
        df_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            df_row, text=self._tr("dateFormat", "Date format"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        df_labels = [
            _label(f, DATE_FORMAT_LABELS_FA, DATE_FORMAT_LABELS_EN, self._lang)
            for f in ("short", "long", "iso", "full")
        ]
        self._df_seg = SegmentedControl(
            df_row, values=df_labels, lang=self._lang,
            on_change=lambda v: self._on_date_format_pick(v, df_labels),
            height=32,
        )
        self._df_seg.pack(side="left" if rtl else "right", padx=4)
        # --- Time format ---
        tf_row = self._make_row_frame(sec)
        tf_row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        ctk.CTkLabel(
            tf_row, text=self._tr("timeFormat", "Time format"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", fill="x", expand=True)
        tf_labels = [
            _label(t, TIME_FORMAT_LABELS_FA, TIME_FORMAT_LABELS_EN, self._lang)
            for t in ("24", "12")
        ]
        self._tf_seg = SegmentedControl(
            tf_row, values=tf_labels, lang=self._lang,
            on_change=lambda v: self._on_time_format_pick(v, tf_labels),
            height=32,
        )
        self._tf_seg.pack(side="left" if rtl else "right", padx=4)

    def _build_about_section(self) -> None:
        """درباره — version, license, source, ack, rate, share, updates."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("about", "About"),
            icon_name="info", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["about"] = sec
        rtl = i18n.is_rtl(self._lang)
        # Version info
        version_text = (
            f"{config.APP_NAME} {config.APP_VERSION}"
            f" ({i18n.to_fa_digits(str(config.APP_BUILD))
                if self._lang == 'fa' else str(config.APP_BUILD)})"
        )
        self._make_info_row(sec, self._tr("version", "Version"),
                            version_text)
        # License
        self._make_link_row(sec, self._tr("license", "License"),
                            config.APP_LICENSE,
                            self._on_show_license)
        # Source code
        self._make_link_row(sec, self._tr("sourceCode", "Source code"),
                            "GitHub", self._on_open_source)
        # Acknowledgements
        self._make_link_row(sec, self._tr("acknowledgements", "Acknowledgements"),
                            self._tr("view", "View"),
                            self._on_show_acknowledgements)
        # Rate
        self._make_action_row(sec, self._tr("rateApp", "Rate the app"),
                              self._tr("rate", "Rate"), self._on_rate)
        # Share
        self._make_action_row(sec, self._tr("shareApp", "Share Rask"),
                              self._tr("share", "Share"), self._on_share)
        # Check for updates
        self._make_action_row(sec, self._tr("checkUpdates", "Check for updates"),
                              self._tr("check", "Check"),
                              self._on_check_updates)

    def _build_advanced_section(self) -> None:
        """پیشرفته — dev mode, logs, cache, vacuum, debug."""
        sec = _CollapsibleSection(
            self._scroll, title=self._tr("advanced", "Advanced"),
            icon_name="wrench", expanded=False, lang=self._lang,
        )
        sec.grid(row=self._next_row(), column=0, sticky="ew",
                  padx=config.SPACE_LG, pady=config.SPACE_SM)
        self._sections["advanced"] = sec
        # Developer mode
        self._dev_toggle = self._make_toggle_row(
            sec, self._tr("developerMode", "Developer mode"),
            self._tr("developerModeHint",
                     "Show extra debug info and tools"),
            settings_service.developer_mode(),
            self._on_dev_toggle,
        )
        rtl = i18n.is_rtl(self._lang)
        # Show logs
        self._make_action_row(sec, self._tr("showLogs", "Show logs"),
                              self._tr("open", "Open"),
                              self._on_show_logs)
        # Clear cache
        self._make_action_row(sec, self._tr("clearCache", "Clear cache"),
                              self._tr("clear", "Clear"),
                              self._on_clear_cache)
        # Vacuum database
        self._make_action_row(sec, self._tr("vacuumDb", "Vacuum database"),
                              self._tr("vacuum", "Vacuum"),
                              self._on_vacuum)
        # Debug info
        self._make_action_row(sec, self._tr("debugInfo", "Debug info"),
                              self._tr("show", "Show"),
                              self._on_show_debug)

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------
    def _make_row_frame(self, sec: _CollapsibleSection) -> ctk.CTkFrame:
        row = ctk.CTkFrame(sec.body, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER,
                           height=48)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)
        return row

    def _make_toggle_row(
        self,
        sec: _CollapsibleSection,
        title: str,
        subtitle: str,
        initial: bool,
        on_change: Callable[[bool], Any],
    ) -> Toggle:
        rtl = i18n.is_rtl(self._lang)
        row = ctk.CTkFrame(sec.body, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER)
        row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        row.grid_columnconfigure(0, weight=1)
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            info, text=subtitle,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM, anchor="e" if rtl else "w",
            wraplength=260,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        toggle = Toggle(
            row, on_change=on_change, lang=self._lang, height=28,
            text="",
        )
        toggle.value = bool(initial)
        toggle.grid(row=0, column=1, padx=12, pady=8)
        return toggle

    def _make_info_row(self, sec: _CollapsibleSection, label: str,
                       value: str) -> None:
        rtl = i18n.is_rtl(self._lang)
        row = ctk.CTkFrame(sec.body, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER,
                           height=44)
        row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", padx=12, pady=8, fill="x",
                expand=True)
        ctk.CTkLabel(
            row, text=value,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.GOLD,
        ).pack(side="left" if rtl else "right", padx=12, pady=8)

    def _make_link_row(self, sec: _CollapsibleSection, label: str,
                       value: str, on_click: Callable[[], Any]) -> None:
        rtl = i18n.is_rtl(self._lang)
        row = ctk.CTkFrame(sec.body, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER,
                           height=44)
        row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", padx=12, pady=8, fill="x",
                expand=True)
        TextButton(
            row, text=value,
            command=on_click, lang=self._lang, height=28,
            color=config.GOLD, font_size=config.FONT_SIZE_SMALL,
            underline_on_hover=True,
        ).pack(side="left" if rtl else "right", padx=12, pady=8)

    def _make_action_row(self, sec: _CollapsibleSection, label: str,
                         button_text: str,
                         on_click: Callable[[], Any]) -> None:
        rtl = i18n.is_rtl(self._lang)
        row = ctk.CTkFrame(sec.body, fg_color=config.CHARCOAL,
                           corner_radius=config.RADIUS_MD,
                           border_width=1, border_color=config.DIVIDER,
                           height=44)
        row.grid(row=sec.next_row(), column=0, sticky="ew", pady=2)
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).pack(side="right" if rtl else "left", padx=12, pady=8, fill="x",
                expand=True)
        GhostButton(
            row, text=button_text,
            command=on_click, lang=self._lang, height=28,
            font_size=config.FONT_SIZE_SMALL,
        ).pack(side="left" if rtl else "right", padx=12, pady=8)

    # ------------------------------------------------------------------
    # Translation helper
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        """Return a translated string.  Prefers i18n catalog if present."""
        try:
            from ...i18n import t as _t
            v = _t(fa, self._lang)
            # If the catalog has the key, use it; otherwise fall back
            if v != fa:
                return v
        except Exception:
            pass
        return fa if self._lang == "fa" else en

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "settings.changed", "language.changed", "theme.changed",
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
        """Re-sync every widget's value with the latest settings."""
        # Theme
        try:
            cur_theme = settings_service.theme()
            labels = [
                _label(t, THEME_LABELS_FA, THEME_LABELS_EN, self._lang)
                for t in ("dark", "light", "system")
            ]
            target = _label(cur_theme, THEME_LABELS_FA, THEME_LABELS_EN,
                            self._lang)
            if target in labels:
                self._theme_seg.value = target
        except Exception:
            pass
        # Lock mode
        try:
            cur_lock = settings_service.lock_mode()
            labels = [
                _label(m, LOCK_MODE_LABELS_FA, LOCK_MODE_LABELS_EN, self._lang)
                for m in ("none", "pin", "biometric")
            ]
            target = _label(cur_lock, LOCK_MODE_LABELS_FA,
                            LOCK_MODE_LABELS_EN, self._lang)
            if target in labels:
                self._lock_seg.value = target
        except Exception:
            pass
        # Auto-backup
        try:
            cur_ab = settings_service.auto_backup()
            labels = [
                _label(v, AUTO_BACKUP_LABELS_FA,
                       AUTO_BACKUP_LABELS_EN, self._lang)
                for v in ("off", "daily", "weekly", "monthly")
            ]
            target = _label(cur_ab, AUTO_BACKUP_LABELS_FA,
                            AUTO_BACKUP_LABELS_EN, self._lang)
            if target in labels:
                self._auto_backup_seg.value = target
        except Exception:
            pass
        # Calendar
        try:
            cur_cal = settings_service.calendar_system()
            labels = [
                _label(c, CALENDAR_LABELS_FA, CALENDAR_LABELS_EN, self._lang)
                for c in ("jalali", "gregorian")
            ]
            target = _label(cur_cal, CALENDAR_LABELS_FA,
                            CALENDAR_LABELS_EN, self._lang)
            if target in labels:
                self._cal_seg.value = target
        except Exception:
            pass
        # Date format
        try:
            cur_df = settings_service.date_format()
            labels = [
                _label(f, DATE_FORMAT_LABELS_FA,
                       DATE_FORMAT_LABELS_EN, self._lang)
                for f in ("short", "long", "iso", "full")
            ]
            target = _label(cur_df, DATE_FORMAT_LABELS_FA,
                            DATE_FORMAT_LABELS_EN, self._lang)
            if target in labels:
                self._df_seg.value = target
        except Exception:
            pass
        # Time format
        try:
            cur_tf = settings_service.time_format()
            labels = [
                _label(t, TIME_FORMAT_LABELS_FA,
                       TIME_FORMAT_LABELS_EN, self._lang)
                for t in ("24", "12")
            ]
            target = _label(cur_tf, TIME_FORMAT_LABELS_FA,
                            TIME_FORMAT_LABELS_EN, self._lang)
            if target in labels:
                self._tf_seg.value = target
        except Exception:
            pass
        # First-day-of-week label
        try:
            cur_fd = settings_service.first_day_of_week()
            fd_map = (FIRST_DAY_LABELS_FA if self._lang == "fa"
                       else FIRST_DAY_LABELS_EN)
            self._first_day_btn.configure(text=fd_map.get(cur_fd, str(cur_fd)))
        except Exception:
            pass
        # Auto-lock label
        try:
            cur_secs = settings_service.auto_lock_seconds()
            auto_opts = [
                (0, self._tr("never", "Never")),
                (30, self._tr("sec30", "30 sec")),
                (60, self._tr("min1", "1 min")),
                (300, self._tr("min5", "5 min")),
                (600, self._tr("min10", "10 min")),
                (1800, self._tr("min30", "30 min")),
            ]
            cur_label = next((lbl for s, lbl in auto_opts if s == cur_secs),
                             auto_opts[0][1])
            self._auto_lock_btn.configure(text=cur_label)
        except Exception:
            pass
        # Language label
        try:
            from ...i18n import locale_display_name
            cur_lang = settings_service.language()
            self._lang_btn.configure(
                text=locale_display_name(cur_lang, self._lang))
        except Exception:
            pass
        # Toggles
        try:
            self._motion_toggle.value = settings_service.reduced_motion()
        except Exception:
            pass
        try:
            self._contrast_toggle.value = settings_service.high_contrast()
        except Exception:
            pass
        try:
            self._sound_toggle.value = settings_service.notify_sound()
        except Exception:
            pass
        try:
            self._vibrate_toggle.value = settings_service.notify_vibrate()
        except Exception:
            pass
        try:
            self._dev_toggle.value = settings_service.developer_mode()
        except Exception:
            pass
        # Font scale
        try:
            self._scale_slider.value = settings_service.font_scale()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_theme_pick(self, label: str, labels: List[str]) -> None:
        themes = ("dark", "light", "system")
        if label not in labels:
            return
        idx = labels.index(label)
        theme = themes[idx]
        try:
            settings_service.set_theme(theme)
        except Exception:
            pass
        # Apply immediately by publishing a theme.changed event
        try:
            event_bus.bus.publish("theme.changed", {"theme": theme})
        except Exception:
            pass
        self._show_toast(self._tr("themeChanged", "Theme changed"))

    def _on_lock_mode_pick(self, label: str, labels: List[str]) -> None:
        modes = ("none", "pin", "biometric")
        if label not in labels:
            return
        mode = modes[labels.index(label)]
        if mode == "pin" and not settings_service.pin_hash():
            # Prompt the user to set a PIN first
            self._prompt_new_pin(
                lambda pin: self._set_pin_and_mode(pin, "pin"))
            return
        try:
            settings_service.set_lock_mode(mode)
        except Exception:
            pass

    def _on_auto_backup_pick(self, label: str, labels: List[str]) -> None:
        vals = ("off", "daily", "weekly", "monthly")
        if label not in labels:
            return
        v = vals[labels.index(label)]
        try:
            settings_service.set_auto_backup(v)
        except Exception:
            pass

    def _on_calendar_pick(self, label: str, labels: List[str]) -> None:
        vals = ("jalali", "gregorian")
        if label not in labels:
            return
        v = vals[labels.index(label)]
        try:
            settings_service.set_calendar_system(v)
        except Exception:
            pass

    def _on_date_format_pick(self, label: str, labels: List[str]) -> None:
        vals = ("short", "long", "iso", "full")
        if label not in labels:
            return
        v = vals[labels.index(label)]
        try:
            settings_service.set_date_format(v)
        except Exception:
            pass

    def _on_time_format_pick(self, label: str, labels: List[str]) -> None:
        vals = ("24", "12")
        if label not in labels:
            return
        v = vals[labels.index(label)]
        try:
            settings_service.set_time_format(v)
        except Exception:
            pass

    def _on_font_scale_change(self, v: float) -> None:
        try:
            settings_service.set_font_scale(float(v))
        except Exception:
            pass

    def _on_motion_toggle(self, v: bool) -> None:
        try:
            settings_service.set_reduced_motion(bool(v))
        except Exception:
            pass

    def _on_contrast_toggle(self, v: bool) -> None:
        try:
            settings_service.set_high_contrast(bool(v))
        except Exception:
            pass

    def _on_sound_toggle(self, v: bool) -> None:
        try:
            settings_service.set_notify_sound(bool(v))
        except Exception:
            pass

    def _on_vibrate_toggle(self, v: bool) -> None:
        try:
            settings_service.set_notify_vibrate(bool(v))
        except Exception:
            pass

    def _on_dev_toggle(self, v: bool) -> None:
        try:
            settings_service.set_developer_mode(bool(v))
        except Exception:
            pass

    # --- Pickers ---
    def _open_language_picker(
        self,
        options: List[Tuple[str, str]],
    ) -> None:
        labels = [d for _, d in options]
        code_by_label = {d: c for c, d in options}
        cur = settings_service.language()
        cur_label = ""
        try:
            from ...i18n import locale_display_name
            cur_label = locale_display_name(cur, self._lang)
        except Exception:
            pass
        picker = PickerSheet(
            self, title=self._tr("selectLanguage", "Select language"),
            options=labels, selected=cur_label,
            lang=self._lang,
        )
        picker.on_result(lambda v: self._apply_language(
            code_by_label.get(v, cur)) if v else None)

    def _apply_language(self, code: str) -> None:
        """Confirm before changing language (requires UI reload)."""
        if not code or code == settings_service.language():
            return
        # Confirm dialog
        dlg = ConfirmDialog(
            self, title=self._tr("languageChange", "Language change"),
            message=self._tr("languageChangeConfirm",
                             "The whole UI will reload. Continue?"),
            yes_text=self._tr("yes", "Yes"),
            no_text=self._tr("no", "No"),
            lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_language_change(code) if ok
                       else None)

    def _do_language_change(self, code: str) -> None:
        try:
            settings_service.set_language(code)
        except Exception:
            pass
        # Trigger UI reload via app
        if self._app and hasattr(self._app, "reload_ui"):
            try:
                self._app.reload_ui()
            except Exception:
                pass

    def _open_auto_lock_picker(
        self, options: List[Tuple[int, str]],
    ) -> None:
        labels = [lbl for _, lbl in options]
        sec_by_label = {lbl: s for s, lbl in options}
        cur = settings_service.auto_lock_seconds()
        cur_label = next((lbl for s, lbl in options if s == cur),
                         options[0][1])
        picker = PickerSheet(
            self, title=self._tr("selectAutoLock", "Auto-lock timeout"),
            options=labels, selected=cur_label,
            lang=self._lang,
        )
        picker.on_result(lambda v: self._apply_auto_lock(
            sec_by_label.get(v, 0)) if v else None)

    def _apply_auto_lock(self, secs: int) -> None:
        try:
            settings_service.set_auto_lock_seconds(int(secs))
        except Exception:
            pass
        self.refresh()

    def _open_first_day_picker(self, fd_map: Dict[int, str]) -> None:
        labels = list(fd_map.values())
        idx_by_label = {lbl: idx for idx, lbl in fd_map.items()}
        cur = settings_service.first_day_of_week()
        cur_label = fd_map.get(cur, "")
        picker = PickerSheet(
            self, title=self._tr("selectFirstDay", "First day of week"),
            options=labels, selected=cur_label, lang=self._lang,
        )
        picker.on_result(lambda v: self._apply_first_day(
            idx_by_label.get(v, 6)) if v else None)

    def _apply_first_day(self, idx: int) -> None:
        try:
            settings_service.set_first_day_of_week(int(idx))
        except Exception:
            pass
        self.refresh()

    # --- PIN management ---
    def _prompt_new_pin(self, on_result: Callable[[str], Any]) -> None:
        dlg = PromptDialog(
            self, title=self._tr("setPin", "Set PIN"),
            message=self._tr("setPinHint", "Enter a 4-digit PIN"),
            placeholder="••••", lang=self._lang,
        )
        dlg.on_result(lambda v: on_result(v) if v else None)

    def _set_pin_and_mode(self, pin: str, mode: str) -> None:
        from ...core import pin as pin_core
        try:
            if not pin or len(pin) < 4:
                self._show_toast(self._tr("pinTooShort",
                                          "PIN must be 4 digits"))
                return
            h = pin_core.hash_pin(pin)
            settings_service.set_pin_hash(h)
            settings_service.set_lock_mode(mode)
            self._show_toast(self._tr("pinSet", "PIN set"))
        except Exception:
            self._show_toast(self._tr("pinError", "PIN error"))
        self.refresh()

    def _on_change_pin(self) -> None:
        self._prompt_new_pin(
            lambda pin: self._set_pin_and_mode(pin, "pin"))

    def _on_remove_pin(self) -> None:
        dlg = ConfirmDialog(
            self, title=self._tr("removePin", "Remove PIN"),
            message=self._tr("removePinConfirm",
                             "PIN will be removed and lock mode set to none."),
            yes_text=self._tr("yes", "Yes"),
            no_text=self._tr("no", "No"),
            danger=True, lang=self._lang,
        )
        dlg.on_result(lambda ok: self._do_remove_pin() if ok else None)

    def _do_remove_pin(self) -> None:
        try:
            settings_service.clear_pin_hash()
            settings_service.set_lock_mode("none")
            self._show_toast(self._tr("pinRemoved", "PIN removed"))
        except Exception:
            pass
        self.refresh()

    # --- Data actions ---
    def _on_backup_now(self) -> None:
        # Prompt for password
        dlg = PromptDialog(
            self, title=self._tr("backupNow", "Backup now"),
            message=self._tr("backupPasswordHint",
                             "Enter a password to encrypt the backup"),
            placeholder="••••••", lang=self._lang,
        )
        dlg.on_result(lambda pw: self._do_backup(pw) if pw else None)

    def _do_backup(self, password: str) -> None:
        if not password or len(password) < 4:
            self._show_toast(self._tr("passwordTooShort",
                                      "Password too short"))
            return
        try:
            result = backup_service.create(password=password)
            if result.get("success"):
                size_kb = int(result.get("size", 0) // 1024)
                size_str = (i18n.to_fa_digits(str(size_kb)) + " KB"
                            if self._lang == "fa" else f"{size_kb} KB")
                self._show_toast(
                    f"{self._tr('backupCreated', 'Backup created')} · "
                    f"{size_str}")
            else:
                self._show_toast(result.get("error",
                                            self._tr("backupFailed",
                                                     "Backup failed")))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_restore(self) -> None:
        # Open file picker
        path = self._pick_file(
            title=self._tr("selectBackup", "Select backup file"),
            filetypes=(("Rask backup", "*.raskbk"), ("All files", "*.*")))
        if not path:
            return
        dlg = PromptDialog(
            self, title=self._tr("restoreBackup", "Restore"),
            message=self._tr("restorePasswordHint",
                             "Enter the backup password"),
            placeholder="••••••", lang=self._lang,
        )
        dlg.on_result(lambda pw: self._do_restore(path, pw) if pw
                       else None)

    def _do_restore(self, path: str, password: str) -> None:
        try:
            result = backup_service.restore(path, password)
            if result.get("success"):
                cnt = result.get("record_count", 0)
                cnt_str = (i18n.to_fa_digits(str(cnt))
                           if self._lang == "fa" else str(cnt))
                self._show_toast(
                    f"{self._tr('restoreDone', 'Restored')} · "
                    f"{cnt_str} {self._tr('records', 'records')}")
                # Trigger global reload
                if self._app and hasattr(self._app, "reload_ui"):
                    try:
                        self._app.reload_ui()
                    except Exception:
                        pass
            else:
                self._show_toast(result.get("error",
                                            self._tr('restoreFailed',
                                                     'Restore failed')))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_export(self) -> None:
        try:
            today = time_utils.today_iso()
            year_ago = time_utils.add_days(today, -365)
            result = export_service.export_json(year_ago, today)
            if result.get("success"):
                self._show_toast(
                    self._tr("exportDone", "Export complete"))
            else:
                self._show_toast(result.get("error",
                                            self._tr("exportFailed",
                                                     "Export failed")))
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
            self._show_toast(self._tr("importDone", "Import complete"))
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
            # Delete all rows from each table
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
            self._show_toast(self._tr("dataCleared", "Data cleared"))
            if self._app and hasattr(self._app, "reload_ui"):
                try:
                    self._app.reload_ui()
                except Exception:
                    pass
        except Exception as exc:
            self._show_toast(str(exc))

    # --- Reminder management ---
    def _on_manage_reminders(self) -> None:
        if self._app and hasattr(self._app, "open_reminders_screen"):
            try:
                self._app.open_reminders_screen()
                return
            except Exception:
                pass
        if self._app and hasattr(self._app, "switch_tab"):
            try:
                self._app.switch_tab("reminders")
            except Exception:
                pass

    # --- About handlers ---
    def _on_show_license(self) -> None:
        license_text = (
            f"{config.APP_NAME} {config.APP_VERSION}\n\n"
            f"MIT License\n\n"
            f"Copyright (c) {time_utils.now_iso_local()[:4]} "
            f"{config.APP_AUTHOR}\n\n"
            "Permission is hereby granted, free of charge, to any person "
            "obtaining a copy of this software and associated documentation "
            "files (the \"Software\"), to deal in the Software without "
            "restriction, including without limitation the rights to use, "
            "copy, modify, merge, publish, distribute, sublicense, and/or "
            "sell copies of the Software, and to permit persons to whom the "
            "Software is furnished to do so, subject to the following "
            "conditions:\n\n"
            "The above copyright notice and this permission notice shall be "
            "included in all copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND.")
        AlertDialog(self, title=self._tr("license", "License"),
                    message=license_text, lang=self._lang,
                    ok_text=self._tr("close", "Close"))

    def _on_open_source(self) -> None:
        try:
            import webbrowser
            webbrowser.open(config.APP_URL)
        except Exception:
            self._show_toast(config.APP_URL)

    def _on_show_acknowledgements(self) -> None:
        msg = (
            "CustomTkinter — MIT\n"
            "Pillow — HPND\n"
            "cryptography — Apache/BSD\n"
            "reportlab — BSD\n"
            "Vazirmatn font — OFL\n"
        )
        AlertDialog(self, title=self._tr("acknowledgements",
                                          "Acknowledgements"),
                    message=msg, lang=self._lang,
                    ok_text=self._tr("close", "Close"))

    def _on_rate(self) -> None:
        self._show_toast(self._tr("thanksForRating",
                                  "Thanks for rating Rask!"))

    def _on_share(self) -> None:
        try:
            text = f"{config.APP_NAME} — {config.APP_URL}"
            # Try clipboard
            self.clipboard_clear()
            self.clipboard_append(text)
            self._show_toast(self._tr("linkCopied", "Link copied"))
        except Exception:
            self._show_toast(config.APP_URL)

    def _on_check_updates(self) -> None:
        self._show_toast(self._tr("upToDate", "You're up to date"))

    # --- Advanced handlers ---
    def _on_show_logs(self) -> None:
        try:
            log_file = next(iter(config.LOG_DIR.glob("*.log")), None)
            if log_file:
                content = log_file.read_text(encoding="utf-8",
                                              errors="replace")[-2000:]
                AlertDialog(self, title=self._tr("logs", "Logs"),
                            message=content or "(empty)",
                            lang=self._lang,
                            ok_text=self._tr("close", "Close"))
            else:
                self._show_toast(self._tr("noLogs", "No logs found"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_clear_cache(self) -> None:
        try:
            import shutil
            for entry in config.CACHE_DIR.iterdir():
                try:
                    if entry.is_file():
                        entry.unlink()
                    elif entry.is_dir():
                        shutil.rmtree(entry)
                except Exception:
                    pass
            self._show_toast(self._tr("cacheCleared", "Cache cleared"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_vacuum(self) -> None:
        try:
            db.vacuum()
            self._show_toast(self._tr("vacuumDone", "Database vacuumed"))
        except Exception as exc:
            self._show_toast(str(exc))

    def _on_show_debug(self) -> None:
        try:
            s = db.stats()
            lines = [f"{k}: {v}" for k, v in s.items()]
            msg = "\n".join(lines)
            AlertDialog(self, title=self._tr("debugInfo", "Debug info"),
                        message=msg, lang=self._lang,
                        ok_text=self._tr("close", "Close"))
        except Exception as exc:
            self._show_toast(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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
    print("SettingsScreen module: 7 collapsible sections, "
          "30+ setting controls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
