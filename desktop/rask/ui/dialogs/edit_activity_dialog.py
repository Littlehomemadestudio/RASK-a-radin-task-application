"""
rask.ui.dialogs.edit_activity_dialog
====================================

Modal dialog for editing an existing activity record.

Shares most of its form layout with :class:`QuickLogDialog`, but adds:

  * Pre-populated fields from the activity dict
  * Activity metadata footer: created date, kind, source
  * Delete button (with confirmation)
  * Duplicate button (creates a copy with today's date)
  * Save / Cancel buttons

Mirrors ``web/js/app.js :: openEditActivityModal`` 1:1.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import time_utils, jalali, helpers
from ...services import activity_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, DangerButton, TextButton
from ..widgets.inputs import GoldEntry, TextArea, DurationEntry
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.badges import Chip
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.date_picker import DatePicker
from ..widgets.time_picker import TimePicker
from .confirm_dialog import ConfirmDialog

__all__ = ["EditActivityDialog"]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _load_categories() -> List[Dict[str, Any]]:
    try:
        return list(db.category_list(include_archived=True))
    except Exception:
        return []


def _category_name(cat_id: Optional[int], lang: str) -> str:
    if not cat_id:
        return (i18n.t("allCategories", lang)
                 if i18n.t("allCategories", lang) != "allCategories"
                 else "همه دسته‌ها")
    try:
        cat = db.category_get(int(cat_id))
        if cat:
            return (cat.get("name_fa") if lang == "fa"
                     else cat.get("name_en")) or cat.get("key", "—")
    except Exception:
        pass
    return "—"


def _format_date(iso: str, lang: str) -> str:
    if not iso:
        return ""
    try:
        if lang == "fa":
            jy, jm, jd = jalali.iso_to_jalali(iso)
            return i18n.to_fa_digits(f"{jd:02d}/{jm:02d}/{jy % 100:02d}")
        return iso
    except Exception:
        return iso


def _format_time(hhmm: str, lang: str) -> str:
    if not hhmm:
        return ""
    return i18n.to_fa_digits(hhmm) if lang == "fa" else hhmm


def _ts_to_hhmm(ts: Optional[str]) -> str:
    if not ts:
        return datetime.now().strftime("%H:%M")
    try:
        s = ts.split("T", 1)[-1]
        if "." in s:
            s = s.split(".", 1)[0]
        if "+" in s:
            s = s.split("+", 1)[0]
        return s[:5]
    except Exception:
        return datetime.now().strftime("%H:%M")


# =============================================================================
# === EditActivityDialog                                                     ===
# =============================================================================

class EditActivityDialog(BaseDialog):
    """Modal dialog for editing an existing activity.

    Parameters
    ----------
    master
        Parent widget.
    activity
        The activity dict to edit (must have an ``id``).
    lang
        UI language.
    on_result
        Callback invoked with ``{"action": str, "activity": dict}``
        where ``action`` is one of ``"saved"`` / ``"deleted"`` /
        ``"duplicated"`` / ``"cancelled"``.
    """

    def __init__(
        self,
        master: Any,
        activity: Dict[str, Any],
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        if not activity or "id" not in activity:
            raise ValueError("activity must have an 'id' field")
        self._activity = dict(activity)
        self._activity_id = int(activity["id"])
        self._categories: List[Dict[str, Any]] = _load_categories()
        self._selected_cat_id: Optional[int] = (
            activity.get("category_id")
            if activity.get("category_id") else None)
        self._selected_date_iso: str = (
            activity.get("date_iso") or time_utils.today_iso())
        start_ts = activity.get("start_ts")
        self._selected_time_hhmm: str = _ts_to_hhmm(start_ts)
        self._dirty: bool = False
        self._saving: bool = False
        self._date_dlg = None
        self._time_dlg = None
        kwargs.setdefault("height", 680)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        super().__init__(
            master,
            title=(i18n.t("edit", lang) if lang == "fa" else "Edit"),
            lang=lang, **kwargs,
        )
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

        # --- Title ----------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("activityTitle", self._lang)
                   if i18n.t("activityTitle", self._lang)
                   != "activityTitle"
                   else "عنوان فعالیت"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._title_entry = GoldEntry(
            form, lang=self._lang, height=46,
            on_change=lambda _v: self._mark_dirty(),
        )
        self._title_entry.value = self._activity.get("title", "")
        self._title_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Category chips ------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("category", self._lang)
                   if i18n.t("category", self._lang) != "category"
                   else "دسته‌بندی"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._cat_frame = ctk.CTkFrame(form, fg_color="transparent")
        self._cat_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self._cat_chips: List[Chip] = []
        self._rebuild_cat_chips()
        row += 1

        # --- Duration ------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("duration", self._lang)
                   if i18n.t("duration", self._lang) != "duration"
                   else "مدت زمان"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._duration_entry = DurationEntry(
            form, lang=self._lang,
            initial_minutes=int(self._activity.get("duration_min") or 0),
            on_change=lambda _v: self._mark_dirty(),
        )
        self._duration_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Date / time ---------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("date", self._lang)
                   if i18n.t("date", self._lang) != "date" else "تاریخ"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        dt_row = ctk.CTkFrame(form, fg_color="transparent")
        dt_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        dt_row.grid_columnconfigure(0, weight=1)
        dt_row.grid_columnconfigure(1, weight=1)
        self._date_btn = ctk.CTkButton(
            dt_row, text=_format_date(self._selected_date_iso, self._lang),
            command=self._open_date_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._time_btn = ctk.CTkButton(
            dt_row, text=_format_time(self._selected_time_hhmm, self._lang),
            command=self._open_time_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=42, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        if rtl:
            self._time_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._date_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            self._date_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._time_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        row += 1

        # --- Notes ---------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("notes", self._lang)
                   if i18n.t("notes", self._lang) != "notes"
                   else "یادداشت"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._notes_entry = TextArea(
            form, lang=self._lang, height=80, max_chars=500,
            placeholder=("یادداشت اختیاری" if self._lang == "fa"
                          else "Optional notes"),
        )
        self._notes_entry.value = self._activity.get("notes", "") or ""
        self._notes_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Tags ----------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("tags", self._lang)
                   if i18n.t("tags", self._lang) != "tags" else "برچسب‌ها"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._tags_entry = GoldEntry(
            form, lang=self._lang, height=42,
            on_change=lambda _v: self._mark_dirty(),
        )
        tags = self._activity.get("tags") or []
        if tags:
            self._tags_entry.value = ", ".join(tags)
        self._tags_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Metadata footer ----------------------------------------
        meta_row = ctk.CTkFrame(form, fg_color="transparent")
        meta_row.grid(row=row, column=0, sticky="ew", pady=(4, 4))
        meta_row.grid_columnconfigure(0, weight=1)
        meta_text = self._format_metadata()
        ctk.CTkLabel(
            meta_row, text=meta_text,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
        ).grid(row=0, column=0, sticky="ew")
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

        # --- Buttons: Delete / Duplicate / Cancel / Save -------------
        # Row 1: Delete (left) | Duplicate (right)
        danger_row = ctk.CTkFrame(form, fg_color="transparent")
        danger_row.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        danger_row.grid_columnconfigure(0, weight=1)
        danger_row.grid_columnconfigure(1, weight=1)
        delete_btn = TextButton(
            danger_row,
            text=(i18n.t("delete", self._lang)
                   if i18n.t("delete", self._lang) != "delete"
                   else "حذف"),
            command=self._on_delete,
            lang=self._lang, height=38,
            color=config.DANGER, hover_color=config.DANGER_DIM,
            icon_name="delete", icon_size=14,
        )
        dup_btn = TextButton(
            danger_row,
            text=(i18n.t("duplicate", self._lang)
                   if i18n.t("duplicate", self._lang) != "duplicate"
                   else "دورنگار"),
            command=self._on_duplicate,
            lang=self._lang, height=38,
            color=config.TEXT_DIM, hover_color=config.GOLD,
            icon_name="copy", icon_size=14,
        )
        if rtl:
            delete_btn.grid(row=0, column=0, sticky="ew", padx=2)
            dup_btn.grid(row=0, column=1, sticky="ew", padx=2)
        else:
            dup_btn.grid(row=0, column=0, sticky="ew", padx=2)
            delete_btn.grid(row=0, column=1, sticky="ew", padx=2)
        row += 1

        # Row 2: Cancel | Save
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="ew")
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
    def _format_metadata(self) -> str:
        """Format the activity's metadata footer text."""
        parts: List[str] = []
        kind = self._activity.get("kind", "manual")
        kind_label = {
            "manual": ("دستی" if self._lang == "fa" else "Manual"),
            "stopwatch": ("کرنومتر" if self._lang == "fa" else "Stopwatch"),
            "template": ("قالب" if self._lang == "fa" else "Template"),
            "voice": ("صوتی" if self._lang == "fa" else "Voice"),
            "recurring": ("تکرارشونده" if self._lang == "fa"
                            else "Recurring"),
        }.get(kind, kind)
        parts.append(kind_label)
        source = self._activity.get("source", "desktop")
        source_label = {
            "desktop": ("دسکتاپ" if self._lang == "fa" else "Desktop"),
            "web": ("وب" if self._lang == "fa" else "Web"),
            "import": ("ورودی" if self._lang == "fa" else "Import"),
        }.get(source, source)
        parts.append(source_label)
        created = self._activity.get("created_at", "")
        if created:
            try:
                dt = created.split("T", 1)[0]
                parts.append(_format_date(dt, self._lang))
            except Exception:
                pass
        sep = " • " if self._lang != "fa" else " • "
        return sep.join(parts)

    # ------------------------------------------------------------------
    def _rebuild_cat_chips(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        for child in self._cat_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._cat_chips = []
        for cat in self._categories:
            try:
                color = cat.get("color") or config.GOLD
                name = (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or cat.get("key", "—")
                selected = (self._selected_cat_id == int(cat["id"]))
                chip = Chip(
                    self._cat_frame, text=name,
                    color=color, selected=selected,
                    on_click=lambda cid=int(cat["id"]): self._select_cat(cid),
                    lang=self._lang,
                )
                chip.pack(side="right" if rtl else "left", padx=4)
                self._cat_chips.append(chip)
            except Exception:
                continue

    def _select_cat(self, cat_id: int) -> None:
        self._selected_cat_id = cat_id
        self._dirty = True
        self._rebuild_cat_chips()

    # ------------------------------------------------------------------
    def _open_date_picker(self) -> None:
        try:
            self._date_dlg = DatePicker(
                self, initial=self._selected_date_iso,
                on_result=self._on_date_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_date_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._selected_date_iso = iso
        self._dirty = True
        try:
            self._date_btn.configure(
                text=_format_date(iso, self._lang))
        except Exception:
            pass

    def _open_time_picker(self) -> None:
        try:
            self._time_dlg = TimePicker(
                self, initial=self._selected_time_hhmm,
                on_result=self._on_time_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_time_picked(self, hhmm: Optional[str]) -> None:
        if not hhmm:
            return
        self._selected_time_hhmm = hhmm
        self._dirty = True
        try:
            self._time_btn.configure(
                text=_format_time(hhmm, self._lang))
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
        if not title:
            self._show_error(
                i18n.t("errorRequired", self._lang)
                if i18n.t("errorRequired", self._lang) != "errorRequired"
                else "عنوان الزامی است")
            return
        duration_min = int(self._duration_entry.value or 0)
        if duration_min <= 0:
            self._show_error(
                "مدت زمان باید بزرگتر از صفر باشد" if self._lang == "fa"
                else "Duration must be > 0")
            return
        notes = self._notes_entry.value.strip() or None
        tags_str = self._tags_entry.value.strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] \
            if tags_str else None
        # Compute start/end timestamps from date + time + duration
        start_ts = None
        end_ts = None
        try:
            h, m = (self._selected_time_hhmm.split(":") + ["0", "0"])[:2]
            start_dt = datetime.fromisoformat(self._selected_date_iso)
            start_dt = start_dt.replace(hour=int(h), minute=int(m))
            start_ts = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
            end_ts = (start_dt + timedelta(minutes=duration_min)).strftime(
                "%Y-%m-%dT%H:%M:%S")
        except Exception:
            pass

        self._saving = True
        try:
            self._save_btn.configure(state="disabled", text="…")
        except Exception:
            pass

        try:
            updated = activity_service.update(
                self._activity_id,
                title=title,
                category_id=self._selected_cat_id,
                duration_min=duration_min,
                date_iso=self._selected_date_iso,
                start_ts=start_ts,
                end_ts=end_ts,
                notes=notes,
                tags=tags,
            )
            try:
                Toast.show(
                    self,
                    (i18n.t("activityUpdated", self._lang)
                     if i18n.t("activityUpdated", self._lang)
                     != "activityUpdated"
                     else "فعالیت به‌روزرسانی شد"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "saved", "activity": updated})
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
        """Confirm + delete the activity."""
        try:
            ConfirmDialog(
                self,
                title=i18n.t("delete", self._lang),
                message=(i18n.t("deleteGoalConfirm", self._lang)
                          if "deleteGoalConfirm" in dir()
                          else ("این فعالیت حذف شود؟"
                                  if self._lang == "fa"
                                  else "Delete this activity?")),
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
            activity_service.delete(self._activity_id)
            try:
                Toast.show(
                    self,
                    (i18n.t("activityDeleted", self._lang)
                     if i18n.t("activityDeleted", self._lang)
                     != "activityDeleted"
                     else "فعالیت حذف شد"),
                    kind="info", lang=self._lang,
                )
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "deleted", "activity_id":
                         self._activity_id})
        except Exception as exc:
            self._show_error(str(exc))

    # ------------------------------------------------------------------
    def _on_duplicate(self) -> None:
        """Duplicate the activity with today's date."""
        try:
            new = activity_service.add(
                title=self._title_entry.value.strip() or
                       self._activity.get("title", ""),
                category_id=self._selected_cat_id,
                duration_min=int(self._duration_entry.value or 0),
                date_iso=time_utils.today_iso(),
                notes=self._notes_entry.value.strip() or None,
                tags=[t.strip() for t in self._tags_entry.value.split(",")
                       if t.strip()] or None,
                kind="manual",
                source="duplicate",
            )
            try:
                Toast.show(
                    self,
                    ("فعالیت دورنگاری شد" if self._lang == "fa"
                      else "Activity duplicated"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            self._dirty = False
            self.close({"action": "duplicated", "activity": new})
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

    # ------------------------------------------------------------------
    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("edit_activity_dialog module: 1 class (EditActivityDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
