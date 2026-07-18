"""
rask.ui.dialogs.reminder_dialog
===============================

Modal dialog for creating / editing a scheduled reminder.

Layout
------
  * Title row: ``"یادآوری جدید"`` / ``"ویرایش یادآوری"``  +  close (×)
  * Title (GoldEntry, required)
  * Message (GoldEntry, optional)
  * Time (TimePicker, default 09:00)
  * Repeat days — 7 checkboxes (Sat..Fri, default all)
  * Quick presets: Every day / Weekdays / Weekends / Custom
  * Linked category (PickerSheet, optional)
  * Linked goal (PickerSheet, optional)
  * Sound toggle
  * Save / Cancel / Delete (if editing)

Mirrors ``web/js/app.js :: openReminderDialog`` 1:1.
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
from ...core import helpers
from ...services import reminder_service, goal_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry
from ..widgets.toggles import Toggle, CheckBox
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.sheets import PickerSheet
from ..widgets.time_picker import TimePicker
from .confirm_dialog import ConfirmDialog

__all__ = ["ReminderDialog"]


# =============================================================================
# === Day-of-week labels (Persian week: Sat..Fri)                            ===
# =============================================================================

DAY_LABELS_FA: List[str] = [
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه",
    "چهارشنبه", "پنجشنبه", "جمعه",
]
DAY_LABELS_EN: List[str] = [
    "Saturday", "Sunday", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday",
]
# Persian weekday bit indices: Sat=0..Fri=6 (matches reminder_service).
DAY_BITS: List[int] = [1, 2, 4, 8, 16, 32, 64]


def _day_labels(lang: str) -> List[str]:
    return DAY_LABELS_FA if lang == "fa" else DAY_LABELS_EN


# =============================================================================
# === Day-of-week checkboxes row                                             ===
# =============================================================================

class _DayCheckRow(ctk.CTkFrame):
    """Horizontal row of 7 day-of-week checkboxes."""

    def __init__(
        self,
        master: Any,
        lang: str = "fa",
        initial_mask: int = 127,
        on_change: Optional[Callable[[int], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._lang = lang
        self._on_change = on_change
        self._mask = initial_mask
        self._checks: List[CheckBox] = []
        labels = _day_labels(lang)
        for i, label in enumerate(labels):
            cb = CheckBox(
                self, text=label,
                on_change=lambda v, b=DAY_BITS[i]: self._on_toggle(b, v),
                lang=lang, font_size=config.FONT_SIZE_CAPTION,
            )
            cb.value = bool(initial_mask & DAY_BITS[i])
            cb.pack(side="right" if i18n.is_rtl(lang) else "left",
                     padx=2, pady=4)
            self._checks.append(cb)

    def _on_toggle(self, bit: int, value: bool) -> None:
        if value:
            self._mask |= bit
        else:
            self._mask &= ~bit
        if self._on_change:
            try:
                self._on_change(self._mask)
            except Exception:
                pass

    @property
    def value(self) -> int:
        return self._mask

    @value.setter
    def value(self, mask: int) -> None:
        self._mask = int(mask)
        for cb, bit in zip(self._checks, DAY_BITS):
            try:
                cb.value = bool(mask & bit)
            except Exception:
                pass


# =============================================================================
# === ReminderDialog                                                         ===
# =============================================================================

class ReminderDialog(BaseDialog):
    """Modal create / edit reminder dialog.

    Parameters
    ----------
    master
        Parent widget.
    reminder_id
        Optional reminder id to edit.  ``None`` creates a new one.
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str, "reminder": dict}``.
    """

    def __init__(
        self,
        master: Any,
        reminder_id: Optional[int] = None,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._reminder_id = reminder_id
        self._reminder: Optional[Dict[str, Any]] = None
        if reminder_id is not None:
            try:
                self._reminder = reminder_service.get(reminder_id)
            except Exception:
                self._reminder = None
        if self._reminder:
            self._title_text = self._reminder.get("title", "")
            self._message = self._reminder.get("message", "") or ""
            self._time_hhmm = self._reminder.get("time_hhmm") or "09:00"
            self._days_mask = int(self._reminder.get("days_mask") or 127)
            self._category_id = self._reminder.get("category_id")
            self._goal_id = self._reminder.get("goal_id")
            self._sound = bool(self._reminder.get("sound", True))
            self._enabled = bool(self._reminder.get("enabled", True))
        else:
            self._title_text = ""
            self._message = ""
            self._time_hhmm = "09:00"
            self._days_mask = 127
            self._category_id = None
            self._goal_id = None
            self._sound = True
            self._enabled = True
        self._dirty = False
        self._saving = False
        self._cat_dlg = None
        self._goal_dlg = None
        self._time_dlg = None
        kwargs.setdefault("height", 680)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("editReminder", lang) if self._reminder
                  else i18n.t("newReminder", lang))
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        scroll = SmoothScrollFrame(self._content, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        form = ctk.CTkFrame(scroll, fg_color="transparent")
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(0, weight=1)

        row = 0

        # --- Title --------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("reminderTitle", self._lang)
                   if i18n.t("reminderTitle", self._lang)
                   != "reminderTitle"
                   else "عنوان یادآوری"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._title_entry = GoldEntry(
            form, lang=self._lang, height=46,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._title_entry.value = self._title_text
        self._title_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Message ------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("reminderMessage", self._lang)
                   if i18n.t("reminderMessage", self._lang)
                   != "reminderMessage"
                   else "پیام یادآوری"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._message_entry = GoldEntry(
            form, lang=self._lang, height=42,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._message_entry.value = self._message
        self._message_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Time ---------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("reminderTime", self._lang)
                   if i18n.t("reminderTime", self._lang)
                   != "reminderTime"
                   else "زمان یادآوری"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._time_btn = ctk.CTkButton(
            form,
            text=(i18n.to_fa_digits(self._time_hhmm)
                   if self._lang == "fa" else self._time_hhmm),
            command=self._open_time_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._time_btn.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Repeat days --------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("reminderDays", self._lang)
                   if i18n.t("reminderDays", self._lang)
                   != "reminderDays"
                   else "روزهای تکرار"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._day_row = _DayCheckRow(
            form, lang=self._lang, initial_mask=self._days_mask,
            on_change=lambda m: self._on_days_change(m),
        )
        self._day_row.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        # --- Quick presets ------------------------------------------
        preset_row = ctk.CTkFrame(form, fg_color="transparent")
        preset_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        for i in range(4):
            preset_row.grid_columnconfigure(i, weight=1)
        everyday_text = (i18n.t("everyDay", self._lang)
                          if i18n.t("everyDay", self._lang) != "everyDay"
                          else "هر روز")
        weekdays_text = (i18n.t("weekdays", self._lang)
                          if i18n.t("weekdays", self._lang) != "weekdays"
                          else "روزهای هفته")
        weekends_text = (i18n.t("weekends", self._lang)
                          if i18n.t("weekends", self._lang) != "weekends"
                          else "آخر هفته")
        custom_text = (i18n.t("custom", self._lang)
                        if i18n.t("custom", self._lang) != "custom"
                        else "دلخواه")
        # Weekdays = Sat..Thu (bits 0..5) = 63
        # Weekends = Fri only (bit 6) = 64
        TextButton(preset_row, text=everyday_text,
                    command=lambda: self._set_preset(127),
                    lang=self._lang, height=32).grid(
                        row=0, column=0, sticky="ew", padx=2)
        TextButton(preset_row, text=weekdays_text,
                    command=lambda: self._set_preset(63),
                    lang=self._lang, height=32).grid(
                        row=0, column=1, sticky="ew", padx=2)
        TextButton(preset_row, text=weekends_text,
                    command=lambda: self._set_preset(64),
                    lang=self._lang, height=32).grid(
                        row=0, column=2, sticky="ew", padx=2)
        TextButton(preset_row, text=custom_text,
                    command=lambda: None,
                    lang=self._lang, height=32,
                    color=config.TEXT_FAINT).grid(
                        row=0, column=3, sticky="ew", padx=2)
        row += 1

        # --- Linked category ----------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("reminderCategory", self._lang)
                   if i18n.t("reminderCategory", self._lang)
                   != "reminderCategory"
                   else "دسته مرتبط"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._cat_btn = ctk.CTkButton(
            form, text=self._category_label(),
            command=self._open_category_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._cat_btn.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Linked goal --------------------------------------------
        SectionTitle(
            form,
            text=("هدف مرتبط" if self._lang == "fa" else "Linked goal"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._goal_btn = ctk.CTkButton(
            form, text=self._goal_label(),
            command=self._open_goal_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._goal_btn.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Sound toggle -------------------------------------------
        sound_row = ctk.CTkFrame(form, fg_color="transparent")
        sound_row.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        sound_row.grid_columnconfigure(0, weight=1)
        sound_row.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            sound_row,
            text=("صدا" if self._lang == "fa" else "Sound"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._sound_toggle = Toggle(
            sound_row, text="", on_change=self._on_sound_toggle,
            lang=self._lang,
        )
        self._sound_toggle.value = self._sound
        self._sound_toggle.grid(row=0, column=1, padx=4)
        row += 1

        # --- Enabled toggle -----------------------------------------
        enabled_row = ctk.CTkFrame(form, fg_color="transparent")
        enabled_row.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        enabled_row.grid_columnconfigure(0, weight=1)
        enabled_row.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            enabled_row,
            text=(i18n.t("reminderEnabled", self._lang)
                   if i18n.t("reminderEnabled", self._lang)
                   != "reminderEnabled"
                   else "فعال"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._enabled_toggle = Toggle(
            enabled_row, text="", on_change=self._on_enabled_toggle,
            lang=self._lang,
        )
        self._enabled_toggle.value = self._enabled
        self._enabled_toggle.grid(row=0, column=1, padx=4)
        row += 1

        # --- Error caption ------------------------------------------
        self._error_label = ctk.CTkLabel(
            form, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="e" if rtl else "w",
        )
        self._error_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        Divider(form).grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1

        # --- Delete (if editing) ------------------------------------
        if self._reminder:
            delete_btn = TextButton(
                form,
                text=(i18n.t("delete", self._lang)
                       if i18n.t("delete", self._lang) != "delete"
                       else "حذف"),
                command=self._on_delete,
                lang=self._lang, height=38,
                color=config.DANGER, hover_color=config.DANGER_DIM,
                icon_name="delete", icon_size=14,
            )
            delete_btn.pack(fill="x", pady=(0, 6))

        # --- Buttons ------------------------------------------------
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=2)
        cancel_btn = GhostButton(
            btn_row,
            text=(i18n.t("cancel", self._lang)
                   if i18n.t("cancel", self._lang) != "cancel"
                   else "انصراف"),
            command=self._on_cancel,
            lang=self._lang, height=46,
        )
        self._save_btn = GoldButton(
            btn_row,
            text=(i18n.t("save", self._lang)
                   if i18n.t("save", self._lang) != "save" else "ذخیره"),
            command=self._on_save,
            lang=self._lang, height=46,
            icon_name="check", icon_size=16,
        )
        if rtl:
            self._save_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._save_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    # ------------------------------------------------------------------
    def _category_label(self) -> str:
        if not self._category_id:
            return (i18n.t("allCategories", self._lang)
                     if i18n.t("allCategories", self._lang)
                     != "allCategories"
                     else "همه دسته‌ها")
        try:
            cat = db.category_get(int(self._category_id))
            if cat:
                return (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or cat.get("key", "—")
        except Exception:
            pass
        return "—"

    def _goal_label(self) -> str:
        if not self._goal_id:
            return ("—" if self._lang == "fa" else "—")
        try:
            goal = goal_service.get(int(self._goal_id))
            if goal:
                if goal.get("title"):
                    return goal["title"]
                # Build a label from period + target
                period_label = {
                    "daily": "روزانه" if self._lang == "fa" else "Daily",
                    "weekly": "هفتگی" if self._lang == "fa" else "Weekly",
                    "monthly": "ماهانه" if self._lang == "fa"
                                else "Monthly",
                }.get(goal.get("period", ""), goal.get("period", ""))
                target = int(goal.get("target_minutes") or 0)
                target_str = i18n.to_fa_digits(str(target)) \
                    if self._lang == "fa" else str(target)
                return f"{period_label} — {target_str} " + \
                       ("دقیقه" if self._lang == "fa" else "min")
        except Exception:
            pass
        return "—"

    def _open_category_picker(self) -> None:
        try:
            cats = db.category_list(include_archived=False)
        except Exception:
            cats = []
        options: List[str] = [
            (i18n.t("allCategories", self._lang)
              if i18n.t("allCategories", self._lang)
              != "allCategories"
              else "همه دسته‌ها"),
        ]
        cat_ids: List[Optional[int]] = [None]
        for c in cats:
            name = (c.get("name_fa") if self._lang == "fa"
                     else c.get("name_en")) or c.get("key", "—")
            options.append(name)
            cat_ids.append(int(c["id"]))
        try:
            self._cat_dlg = PickerSheet(
                self,
                title=(i18n.t("reminderCategory", self._lang)
                        if i18n.t("reminderCategory", self._lang)
                        != "reminderCategory"
                        else "دسته"),
                options=options,
                selected=self._category_label(),
                on_result=lambda label: self._on_category_picked(label,
                                                                   cat_ids,
                                                                   options),
                lang=self._lang,
            )
        except Exception:
            pass

    def _on_category_picked(
        self,
        label: Optional[str],
        cat_ids: List[Optional[int]],
        options: List[str],
    ) -> None:
        if not label:
            return
        try:
            idx = options.index(label)
            self._category_id = cat_ids[idx]
        except (ValueError, IndexError):
            self._category_id = None
        self._dirty = True
        try:
            self._cat_btn.configure(text=self._category_label())
        except Exception:
            pass

    def _open_goal_picker(self) -> None:
        try:
            goals = goal_service.list()
        except Exception:
            goals = []
        options: List[str] = ["—"]
        goal_ids: List[Optional[int]] = [None]
        for g in goals:
            label = self._format_goal_label(g)
            options.append(label)
            goal_ids.append(int(g["id"]))
        try:
            self._goal_dlg = PickerSheet(
                self,
                title=("هدف مرتبط" if self._lang == "fa"
                        else "Linked goal"),
                options=options,
                selected=self._goal_label(),
                on_result=lambda label: self._on_goal_picked(label,
                                                                goal_ids,
                                                                options),
                lang=self._lang,
            )
        except Exception:
            pass

    def _format_goal_label(self, g: Dict[str, Any]) -> str:
        if g.get("title"):
            return g["title"]
        period_label = {
            "daily": "روزانه" if self._lang == "fa" else "Daily",
            "weekly": "هفتگی" if self._lang == "fa" else "Weekly",
            "monthly": "ماهانه" if self._lang == "fa" else "Monthly",
        }.get(g.get("period", ""), g.get("period", ""))
        target = int(g.get("target_minutes") or 0)
        target_str = i18n.to_fa_digits(str(target)) \
            if self._lang == "fa" else str(target)
        return f"{period_label} — {target_str} " + \
               ("دقیقه" if self._lang == "fa" else "min")

    def _on_goal_picked(
        self,
        label: Optional[str],
        goal_ids: List[Optional[int]],
        options: List[str],
    ) -> None:
        if not label:
            return
        try:
            idx = options.index(label)
            self._goal_id = goal_ids[idx]
        except (ValueError, IndexError):
            self._goal_id = None
        self._dirty = True
        try:
            self._goal_btn.configure(text=self._goal_label())
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _open_time_picker(self) -> None:
        try:
            self._time_dlg = TimePicker(
                self, initial=self._time_hhmm,
                on_result=self._on_time_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_time_picked(self, hhmm: Optional[str]) -> None:
        if not hhmm:
            return
        self._time_hhmm = hhmm
        self._dirty = True
        try:
            self._time_btn.configure(
                text=i18n.to_fa_digits(hhmm) if self._lang == "fa" else hhmm)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_days_change(self, mask: int) -> None:
        self._days_mask = int(mask)
        self._dirty = True

    def _set_preset(self, mask: int) -> None:
        self._days_mask = int(mask)
        self._dirty = True
        try:
            self._day_row.value = mask
        except Exception:
            pass

    def _on_sound_toggle(self, value: bool) -> None:
        self._sound = bool(value)
        self._dirty = True

    def _on_enabled_toggle(self, value: bool) -> None:
        self._enabled = bool(value)
        self._dirty = True

    # ------------------------------------------------------------------
    def _mark_dirty(self, _v: Any = None) -> None:
        self._dirty = True
        try:
            self._error_label.configure(text="")
        except Exception:
            pass

    def _show_error(self, msg: str) -> None:
        try:
            self._error_label.configure(text=msg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        if self._saving:
            return
        title = self._title_entry.value.strip()
        if not title:
            self._show_error(
                "عنوان الزامی است" if self._lang == "fa"
                else "Title is required")
            return
        message = self._message_entry.value.strip() or None
        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            if self._reminder:
                updated = reminder_service.update(
                    self._reminder_id,
                    title=title,
                    message=message,
                    time_hhmm=self._time_hhmm,
                    days_mask=self._days_mask,
                    category_id=self._category_id,
                    goal_id=self._goal_id,
                    enabled=self._enabled,
                    sound=self._sound,
                )
                try:
                    Toast.show(self,
                                (i18n.t("reminderSaved", self._lang)
                                  if i18n.t("reminderSaved", self._lang)
                                  != "reminderSaved"
                                  else "یادآوری ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "reminder": updated})
            else:
                new_r = reminder_service.add(
                    title=title,
                    time_hhmm=self._time_hhmm,
                    message=message,
                    days_mask=self._days_mask,
                    category_id=self._category_id,
                    goal_id=self._goal_id,
                    enabled=self._enabled,
                    sound=self._sound,
                )
                try:
                    Toast.show(self,
                                (i18n.t("reminderSaved", self._lang)
                                  if i18n.t("reminderSaved", self._lang)
                                  != "reminderSaved"
                                  else "یادآوری ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "reminder": new_r})
        except Exception as exc:
            self._saving = False
            try:
                self._save_btn.configure(state="normal",
                                           text=(i18n.t("save", self._lang)
                                                  if i18n.t("save", self._lang)
                                                  != "save" else "ذخیره"))
            except Exception:
                pass
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    def _on_delete(self) -> None:
        try:
            ConfirmDialog(
                self,
                title=i18n.t("delete", self._lang),
                message=("این یادآوری حذف شود؟" if self._lang == "fa"
                          else "Delete this reminder?"),
                danger=True,
                confirm_text=i18n.t("delete", self._lang),
                on_result=self._do_delete,
                lang=self._lang,
            )
        except Exception:
            self._do_delete({"confirmed": True})

    def _do_delete(self, result: Optional[Dict[str, Any]]) -> None:
        if not result or not result.get("confirmed"):
            return
        try:
            reminder_service.delete(self._reminder_id)
            try:
                Toast.show(self,
                            (i18n.t("reminderDeleted", self._lang)
                              if i18n.t("reminderDeleted", self._lang)
                              != "reminderDeleted"
                              else "یادآوری حذف شد"),
                            kind="info", lang=self._lang)
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "deleted",
                         "reminder_id": self._reminder_id})
        except Exception as exc:
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    def _on_cancel(self) -> None:
        if self._dirty:
            try:
                ConfirmDialog(
                    self,
                    title=i18n.t("discardActivity", self._lang),
                    message=("تغییرات ذخیره نشده‌اند." if self._lang == "fa"
                              else "Unsaved changes will be lost."),
                    danger=True,
                    confirm_text=i18n.t("discardActivity", self._lang),
                    on_result=lambda r: self.close(
                        {"action": "cancelled"})
                                        if (r and r.get("confirmed")) else None,
                    lang=self._lang,
                )
            except Exception:
                self.close({"action": "cancelled"})
        else:
            self.close({"action": "cancelled"})

    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("reminder_dialog module: 1 class (ReminderDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
