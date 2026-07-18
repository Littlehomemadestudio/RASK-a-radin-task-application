"""
rask.ui.dialogs.goal_dialog
===========================

Modal dialog for creating / editing a daily / weekly / monthly goal.

Layout
------
  * Title row: ``"هدف جدید"`` / ``"ویرایش هدف"``  +  close (×)
  * Optional title GoldEntry
  * Period :class:`SegmentedControl` — ``روزانه / هفتگی / ماهانه``
  * Target minutes :class:`NumberEntry` with ±stepper (1-10000)
  * Category picker (PickerSheet — pick from categories, or "همه دسته‌ها")
  * Color picker (gold palette + custom)
  * Reminder toggle + reminder time :class:`TimePicker` (shown when on)
  * Save / Cancel buttons
  * Delete button (only when editing)

Validation
----------
  * Target minutes must be 1-10000
  * Title is optional (defaults to ``"هدف <period>"``)

Mirrors ``web/js/app.js :: openGoalDialog`` 1:1.
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
from ...services import goal_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton, DangerButton
from ..widgets.inputs import GoldEntry, NumberEntry
from ..widgets.toggles import SegmentedControl, Toggle
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.sheets import PickerSheet
from ..widgets.time_picker import TimePicker
from .confirm_dialog import ConfirmDialog

__all__ = ["GoalDialog"]


# =============================================================================
# === Period labels                                                          ===
# =============================================================================

PERIOD_LABELS_FA: Dict[str, str] = {
    "daily": "روزانه",
    "weekly": "هفتگی",
    "monthly": "ماهانه",
}
PERIOD_LABELS_EN: Dict[str, str] = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
}


def _period_label(period: str, lang: str) -> str:
    if lang == "fa":
        return PERIOD_LABELS_FA.get(period, period)
    return PERIOD_LABELS_EN.get(period, period)


def _label_to_period(label: str, lang: str) -> str:
    """Reverse lookup: label -> period key."""
    src = PERIOD_LABELS_FA if lang == "fa" else PERIOD_LABELS_EN
    for k, v in src.items():
        if v == label:
            return k
    return "daily"


# =============================================================================
# === Color palette                                                          ===
# =============================================================================

GOLD_PALETTE: List[str] = [
    config.GOLD,
    config.GOLD_SOFT,
    config.CAT_LEARN,
    config.CAT_HEALTH,
    config.CAT_CREATIVE,
    config.CAT_SOCIAL,
    config.CAT_REST,
    config.INFO,
    config.WARNING,
    config.DANGER,
]


# =============================================================================
# === Color swatch grid                                                      ===
# =============================================================================

class _ColorSwatchGrid(ctk.CTkFrame):
    """Grid of colour swatches — click to select one."""

    def __init__(
        self,
        master: Any,
        colors: List[str],
        selected: Optional[str] = None,
        on_change: Optional[Callable[[str], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._colors = list(colors)
        self._selected = selected
        self._on_change = on_change
        self._swatches: List[ctk.CTkFrame] = []
        cols = 5
        for i in range(cols):
            self.grid_columnconfigure(i, weight=1)
        for i, color in enumerate(self._colors):
            r, c = divmod(i, cols)
            sw = ctk.CTkButton(
                self, text="",
                width=40, height=40,
                fg_color=color,
                hover_color=helpers.lighten_color(color, 0.15),
                border_width=3 if color == self._selected else 0,
                border_color=config.TEXT,
                corner_radius=config.RADIUS_PILL,
                cursor="hand2",
                command=lambda col=color: self._select(col),
            )
            sw.grid(row=r, column=c, padx=4, pady=4)
            self._swatches.append(sw)

    def _select(self, color: str) -> None:
        self._selected = color
        # Update border widths
        for sw, col in zip(self._swatches, self._colors):
            try:
                sw.configure(border_width=3 if col == color else 0)
            except Exception:
                pass
        if self._on_change:
            try:
                self._on_change(color)
            except Exception:
                pass

    @property
    def value(self) -> Optional[str]:
        return self._selected


# =============================================================================
# === GoalDialog                                                             ===
# =============================================================================

class GoalDialog(BaseDialog):
    """Modal create / edit goal dialog.

    Parameters
    ----------
    master
        Parent widget.
    goal_id
        Optional goal id to edit.  When ``None``, the dialog creates a
        new goal.
    lang
        UI language.
    on_result
        Callback invoked with ``{"action": str, "goal": dict}`` where
        ``action`` is one of ``"saved"`` / ``"deleted"`` / ``"cancelled"``.
    """

    def __init__(
        self,
        master: Any,
        goal_id: Optional[int] = None,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._goal_id = goal_id
        self._goal: Optional[Dict[str, Any]] = None
        if goal_id is not None:
            try:
                self._goal = goal_service.get(goal_id)
            except Exception:
                self._goal = None
        # Pre-fill state
        if self._goal:
            self._period = self._goal.get("period", "daily")
            self._target_minutes = int(self._goal.get("target_minutes")
                                         or config.DEFAULT_GOAL_MINUTES)
            self._category_id = self._goal.get("category_id")
            self._color = self._goal.get("color") or config.GOLD
            self._reminder_enabled = bool(self._goal.get("reminder_enabled"))
            self._reminder_time = self._goal.get("reminder_time") or "09:00"
            self._title_text = self._goal.get("title") or ""
        else:
            self._period = "daily"
            self._target_minutes = config.DEFAULT_GOAL_MINUTES
            self._category_id = None
            self._color = config.GOLD
            self._reminder_enabled = False
            self._reminder_time = "09:00"
            self._title_text = ""
        self._dirty = False
        self._saving = False
        self._cat_dlg = None
        self._time_dlg = None
        kwargs.setdefault("height", 660)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        title = (i18n.t("editGoal", lang) if self._goal
                  else i18n.t("newGoal", lang))
        if lang != "fa":
            title = "Edit Goal" if self._goal else "New Goal"
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

        # --- Title (optional) ---------------------------------------
        SectionTitle(
            form,
            text=("عنوان (اختیاری)" if self._lang == "fa"
                   else "Title (optional)"),
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

        # --- Period -------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("goalPeriod", self._lang)
                   if i18n.t("goalPeriod", self._lang) != "goalPeriod"
                   else "دوره"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        period_values = [
            _period_label("daily", self._lang),
            _period_label("weekly", self._lang),
            _period_label("monthly", self._lang),
        ]
        self._period_seg = SegmentedControl(
            form, values=period_values,
            on_change=lambda v: self._on_period_change(v),
            lang=self._lang, height=42,
        )
        self._period_seg.set(_period_label(self._period, self._lang))
        self._period_seg.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Target minutes -----------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("targetMinutes", self._lang)
                   if i18n.t("targetMinutes", self._lang)
                   != "targetMinutes"
                   else "هدف (دقیقه)"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._target_entry = NumberEntry(
            form, lang=self._lang,
            min_value=1, max_value=10000, step=5,
            show_stepper=True, unit=("دقیقه" if self._lang == "fa"
                                       else "min"),
            height=50,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._target_entry.value = self._target_minutes
        self._target_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Category picker ----------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("goalCategory", self._lang)
                   if i18n.t("goalCategory", self._lang)
                   != "goalCategory"
                   else "دسته (اختیاری)"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        cat_row = ctk.CTkFrame(form, fg_color="transparent")
        cat_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        cat_row.grid_columnconfigure(0, weight=1)
        self._cat_btn = ctk.CTkButton(
            cat_row, text=self._category_label(),
            command=self._open_category_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._cat_btn.grid(row=0, column=0, sticky="ew")
        row += 1

        # --- Color picker -------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categoryColor", self._lang)
                   if i18n.t("categoryColor", self._lang)
                   != "categoryColor"
                   else "رنگ"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._color_grid = _ColorSwatchGrid(
            form, colors=GOLD_PALETTE, selected=self._color,
            on_change=lambda col: self._on_color_change(col),
        )
        self._color_grid.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Reminder toggle ----------------------------------------
        rem_row = ctk.CTkFrame(form, fg_color="transparent")
        rem_row.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        rem_row.grid_columnconfigure(0, weight=1)
        rem_row.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            rem_row,
            text=(i18n.t("goalReminder", self._lang)
                   if i18n.t("goalReminder", self._lang)
                   != "goalReminder"
                   else "یادآوری هدف"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        self._reminder_toggle = Toggle(
            rem_row, text="", on_change=self._on_reminder_toggle,
            lang=self._lang,
        )
        self._reminder_toggle.value = self._reminder_enabled
        self._reminder_toggle.grid(row=0, column=1, padx=4)
        row += 1

        # Reminder time (shown only when toggle is on)
        self._reminder_time_frame = ctk.CTkFrame(form, fg_color="transparent")
        self._reminder_time_frame.grid(row=row, column=0, sticky="ew",
                                          pady=(0, 8))
        self._reminder_time_frame.grid_columnconfigure(0, weight=1)
        SectionTitle(
            self._reminder_time_frame,
            text=(i18n.t("reminderTime", self._lang)
                   if i18n.t("reminderTime", self._lang)
                   != "reminderTime"
                   else "زمان یادآوری"),
            lang=self._lang,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._reminder_time_btn = ctk.CTkButton(
            self._reminder_time_frame,
            text=i18n.to_fa_digits(self._reminder_time)
                  if self._lang == "fa" else self._reminder_time,
            command=self._open_reminder_time_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._reminder_time_btn.grid(row=1, column=0, sticky="ew")
        row += 1
        if not self._reminder_enabled:
            self._reminder_time_frame.grid_remove()

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
        if self._goal:
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

        # --- Save / Cancel ------------------------------------------
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
        current = self._category_label()
        try:
            self._cat_dlg = PickerSheet(
                self,
                title=(i18n.t("goalCategory", self._lang)
                        if i18n.t("goalCategory", self._lang)
                        != "goalCategory"
                        else "دسته"),
                options=options,
                selected=current,
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

    # ------------------------------------------------------------------
    def _open_reminder_time_picker(self) -> None:
        try:
            self._time_dlg = TimePicker(
                self, initial=self._reminder_time,
                on_result=self._on_reminder_time_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_reminder_time_picked(self, hhmm: Optional[str]) -> None:
        if not hhmm:
            return
        self._reminder_time = hhmm
        self._dirty = True
        try:
            self._reminder_time_btn.configure(
                text=i18n.to_fa_digits(hhmm) if self._lang == "fa" else hhmm)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_period_change(self, label: str) -> None:
        self._period = _label_to_period(label, self._lang)
        self._dirty = True

    def _on_color_change(self, color: str) -> None:
        self._color = color
        self._dirty = True

    def _on_reminder_toggle(self, value: bool) -> None:
        self._reminder_enabled = bool(value)
        self._dirty = True
        try:
            if value:
                self._reminder_time_frame.grid()
            else:
                self._reminder_time_frame.grid_remove()
        except Exception:
            pass

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
        target_val = self._target_entry.value
        if target_val is None or target_val < 1 or target_val > 10000:
            self._show_error(
                "هدف باید بین ۱ تا ۱۰۰۰۰ دقیقه باشد" if self._lang == "fa"
                else "Target must be 1-10000 minutes")
            return
        target_min = int(target_val)
        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            if self._goal:
                updated = goal_service.update(
                    self._goal_id,
                    title=title or None,
                    period=self._period,
                    target_minutes=target_min,
                    category_id=self._category_id,
                    color=self._color,
                    reminder_enabled=self._reminder_enabled,
                    reminder_time=self._reminder_time if
                                    self._reminder_enabled else None,
                )
                try:
                    Toast.show(self,
                                (i18n.t("goalSaved", self._lang)
                                  if i18n.t("goalSaved", self._lang)
                                  != "goalSaved"
                                  else "هدف ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "goal": updated})
            else:
                new_goal = goal_service.add(
                    period=self._period,
                    target_minutes=target_min,
                    category_id=self._category_id,
                    title=title or None,
                    color=self._color,
                    reminder_enabled=self._reminder_enabled,
                    reminder_time=self._reminder_time if
                                    self._reminder_enabled else None,
                )
                try:
                    Toast.show(self,
                                (i18n.t("goalSaved", self._lang)
                                  if i18n.t("goalSaved", self._lang)
                                  != "goalSaved"
                                  else "هدف ذخیره شد"),
                                kind="success", lang=self._lang)
                except Exception:
                    pass
                self._dirty = False
                self.close({"action": "saved", "goal": new_goal})
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
                message=(i18n.t("deleteGoalConfirm", self._lang)
                          if i18n.t("deleteGoalConfirm", self._lang)
                          != "deleteGoalConfirm"
                          else "این هدف حذف شود؟"),
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
            goal_service.delete(self._goal_id)
            try:
                Toast.show(self,
                            (i18n.t("goalDeleted", self._lang)
                              if i18n.t("goalDeleted", self._lang)
                              != "goalDeleted"
                              else "هدف حذف شد"),
                            kind="info", lang=self._lang)
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "deleted", "goal_id": self._goal_id})
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
    print("goal_dialog module: 1 class (GoalDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
