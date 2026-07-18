"""
rask.ui.dialogs.export_dialog
=============================

Modal dialog for exporting activities to PDF / CSV / JSON / PNG.

Layout
------
  * Format picker (radio): PDF / CSV / JSON / PNG
  * Date range picker (presets + custom)
  * Filter options: categories (multi-select), tags, min duration,
    max duration
  * For PDF: additional options (include charts, include insights,
    page size)
  * File path preview (default in ``config.EXPORT_DIR``)
  * "Choose location" button to change path
  * Export button -> progress bar -> toast on success
  * "Open file" / "Open folder" / "Share" buttons after success

Mirrors ``web/js/app.js :: openExportDialog`` 1:1.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

try:
    from tkinter import filedialog
    _FD_OK: bool = True
except Exception:  # pragma: no cover
    _FD_OK = False
    filedialog = None  # type: ignore[assignment]

from ... import config
from ... import i18n
from ...core import helpers, time_utils
from ...services import export_service, settings_service
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry, NumberEntry
from ..widgets.toggles import RadioButton, CheckBox
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from ..widgets.sliders import ProgressBar
from ..widgets.sheets import PickerSheet
from ..widgets.date_picker import DatePicker

__all__ = ["ExportDialog"]


# =============================================================================
# === Format definitions                                                     ===
# =============================================================================

FORMATS: List[Dict[str, str]] = [
    {"key": "pdf", "label_fa": "PDF", "label_en": "PDF", "ext": "pdf",
     "icon": "pdf"},
    {"key": "csv", "label_fa": "CSV", "label_en": "CSV", "ext": "csv",
     "icon": "csv"},
    {"key": "json", "label_fa": "JSON", "label_en": "JSON", "ext": "json",
     "icon": "file"},
    {"key": "png", "label_fa": "PNG", "label_en": "PNG", "ext": "png",
     "icon": "image"},
]


# =============================================================================
# === Date range presets                                                     ===
# =============================================================================

RANGE_PRESETS: List[Dict[str, Any]] = [
    {"key": "today", "label_fa": "امروز", "label_en": "Today", "days": 1},
    {"key": "week", "label_fa": "این هفته", "label_en": "This Week",
     "days": 7},
    {"key": "month", "label_fa": "این ماه", "label_en": "This Month",
     "days": 30},
    {"key": "quarter", "label_fa": "این فصل", "label_en": "This Quarter",
     "days": 90},
    {"key": "year", "label_fa": "امسال", "label_en": "This Year", "days": 365},
    {"key": "all", "label_fa": "همه", "label_en": "All Time", "days": 99999},
]


def _preset_range(preset_key: str) -> tuple:
    """Return (date_from_iso, date_to_iso) for the preset key."""
    today = date.today()
    today_iso = today.isoformat()
    if preset_key == "today":
        return today_iso, today_iso
    if preset_key == "all":
        return "2000-01-01", today_iso
    days_map = {p["key"]: p.get("days", 30) for p in RANGE_PRESETS}
    days = days_map.get(preset_key, 30)
    start = (today - timedelta(days=days - 1)).isoformat()
    return start, today_iso


# =============================================================================
# === ExportDialog                                                           ===
# =============================================================================

class ExportDialog(BaseDialog):
    """Modal export dialog.

    Parameters
    ----------
    master
        Parent widget.
    lang
        UI language.
    on_result
        Callback receiving ``{"action": str, "success": bool,
        "path": Optional[str], "format": str}``.
    """

    def __init__(
        self,
        master: Any,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._format = "pdf"
        self._range_preset = "month"
        self._date_from, self._date_to = _preset_range(self._range_preset)
        self._category_ids: List[int] = []
        self._tags_str: str = ""
        self._min_duration: int = 0
        self._max_duration: int = 0
        self._include_charts: bool = True
        self._include_insights: bool = True
        self._page_size: str = "A4"
        self._output_path: Optional[str] = None
        self._busy = False
        self._worker_thread: Optional[threading.Thread] = None
        self._cat_dlg = None
        self._from_dlg = None
        self._to_dlg = None
        kwargs.setdefault("height", 720)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        super().__init__(
            master,
            title=(i18n.t("export", lang) if lang == "fa" else "Export"),
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

        # --- Format picker -----------------------------------------
        SectionTitle(
            form,
            text=("قالب خروجی" if self._lang == "fa" else "Format"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        fmt_row = ctk.CTkFrame(form, fg_color="transparent")
        fmt_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        for i in range(4):
            fmt_row.grid_columnconfigure(i, weight=1)
        self._fmt_radios: Dict[str, RadioButton] = {}
        for i, fmt in enumerate(FORMATS):
            label = (fmt["label_fa"] if self._lang == "fa"
                      else fmt["label_en"])
            rb = RadioButton(
                fmt_row, text=label, value=fmt["key"],
                on_change=lambda v, k=fmt["key"]: self._on_format_change(k),
                lang=self._lang,
            )
            if fmt["key"] == self._format:
                rb.select()
            rb.grid(row=0, column=i, sticky="ew" if not rtl else "ew",
                     padx=4)
            self._fmt_radios[fmt["key"]] = rb
        row += 1

        # --- Date range --------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("dateRange", self._lang)
                   if i18n.t("dateRange", self._lang) != "dateRange"
                   else "بازه زمانی"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        # Preset row
        preset_row = ctk.CTkFrame(form, fg_color="transparent")
        preset_row.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        for i in range(6):
            preset_row.grid_columnconfigure(i, weight=1)
        for i, preset in enumerate(RANGE_PRESETS):
            label = (preset["label_fa"] if self._lang == "fa"
                      else preset["label_en"])
            is_sel = (preset["key"] == self._range_preset)
            btn = ctk.CTkButton(
                preset_row, text=label,
                command=lambda k=preset["key"]: self._on_preset_change(k),
                fg_color=config.GOLD if is_sel else config.SURFACE,
                hover_color=(config.GOLD_BRIGHT if is_sel
                              else config.SURFACE_HI),
                text_color=(config.MATTE_BLACK if is_sel else config.TEXT_DIM),
                corner_radius=config.RADIUS_PILL, height=30, cursor="hand2",
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold" if is_sel else "normal",
                                        lang=self._lang),
            )
            btn.grid(row=0, column=i, sticky="ew", padx=2)
        row += 1
        # From / To pickers
        range_row = ctk.CTkFrame(form, fg_color="transparent")
        range_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        range_row.grid_columnconfigure(0, weight=1)
        range_row.grid_columnconfigure(1, weight=1)
        self._from_btn = ctk.CTkButton(
            range_row, text=self._format_date(self._date_from),
            command=self._open_from_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        self._to_btn = ctk.CTkButton(
            range_row, text=self._format_date(self._date_to),
            command=self._open_to_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        if rtl:
            self._to_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._from_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            self._from_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._to_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        row += 1

        # --- Categories --------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("categories", self._lang)
                   if i18n.t("categories", self._lang) != "categories"
                   else "دسته‌ها"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._cat_btn = ctk.CTkButton(
            form, text=self._categories_label(),
            command=self._open_category_picker,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        self._cat_btn.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Tags --------------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("tags", self._lang)
                   if i18n.t("tags", self._lang) != "tags"
                   else "برچسب‌ها"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._tags_entry = GoldEntry(
            form, lang=self._lang, height=38,
            placeholder=(i18n.t("tagsPlaceholder", self._lang)
                          if i18n.t("tagsPlaceholder", self._lang)
                          != "tagsPlaceholder"
                          else "با کاما جدا کن"),
        )
        self._tags_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- Min / Max duration ------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("minDuration", self._lang)
                   if i18n.t("minDuration", self._lang)
                   != "minDuration"
                   else "حداقل مدت"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._min_dur_entry = NumberEntry(
            form, lang=self._lang,
            min_value=0, max_value=1440, step=5,
            unit=("دقیقه" if self._lang == "fa" else "min"),
            height=38,
        )
        self._min_dur_entry.value = 0
        self._min_dur_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        SectionTitle(
            form,
            text=(i18n.t("maxDuration", self._lang)
                   if i18n.t("maxDuration", self._lang)
                   != "maxDuration"
                   else "حداکثر مدت"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._max_dur_entry = NumberEntry(
            form, lang=self._lang,
            min_value=0, max_value=1440, step=5,
            unit=("دقیقه" if self._lang == "fa" else "min"),
            height=38,
        )
        self._max_dur_entry.value = 0
        self._max_dur_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1

        # --- PDF options (shown only for PDF format) ----------------
        self._pdf_options_frame = ctk.CTkFrame(form, fg_color="transparent")
        self._pdf_options_frame.grid(row=row, column=0, sticky="ew",
                                       pady=(0, 8))
        SectionTitle(
            self._pdf_options_frame,
            text=("گزینه‌های PDF" if self._lang == "fa" else "PDF options"),
            lang=self._lang,
        ).pack(fill="x", pady=(0, 4))
        self._charts_cb = CheckBox(
            self._pdf_options_frame,
            text=("نمودارها" if self._lang == "fa" else "Include charts"),
            lang=self._lang,
        )
        self._charts_cb.value = True
        self._charts_cb.pack(anchor="e" if rtl else "w", pady=2)
        self._insights_cb = CheckBox(
            self._pdf_options_frame,
            text=("بینش‌ها" if self._lang == "fa" else "Include insights"),
            lang=self._lang,
        )
        self._insights_cb.value = True
        self._insights_cb.pack(anchor="e" if rtl else "w", pady=2)
        row += 1
        if self._format != "pdf":
            self._pdf_options_frame.grid_remove()

        # --- Output path preview -----------------------------------
        SectionTitle(
            form,
            text=("مسیر خروجی" if self._lang == "fa" else "Output path"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        path_row = ctk.CTkFrame(form, fg_color="transparent")
        path_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        path_row.grid_columnconfigure(0, weight=1)
        self._path_label = ctk.CTkLabel(
            path_row, text=self._default_path_preview(),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w", justify="right" if rtl else "left",
            wraplength=320,
        )
        self._path_label.grid(row=0, column=0, sticky="ew")
        TextButton(
            path_row,
            text=("تغییر مسیر" if self._lang == "fa" else "Choose location"),
            command=self._pick_output_path,
            lang=self._lang, height=30, color=config.GOLD,
        ).grid(row=0, column=1, padx=4)
        row += 1

        # --- Progress bar ------------------------------------------
        self._progress = ProgressBar(form, value=0.0, height=6)
        self._progress.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        # --- Error / status label ----------------------------------
        self._status_label = ctk.CTkLabel(
            form, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.DANGER,
            anchor="e" if rtl else "w", wraplength=380,
            justify="right" if rtl else "left",
        )
        self._status_label.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1

        # --- Success actions (hidden until export succeeds) --------
        self._success_frame = ctk.CTkFrame(form, fg_color="transparent")
        self._success_frame.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        for i in range(3):
            self._success_frame.grid_columnconfigure(i, weight=1)
        TextButton(
            self._success_frame,
            text=("باز کردن فایل" if self._lang == "fa" else "Open file"),
            command=self._open_file, lang=self._lang, height=38,
            color=config.GOLD,
        ).grid(row=0, column=0, sticky="ew", padx=2)
        TextButton(
            self._success_frame,
            text=("باز کردن پوشه" if self._lang == "fa" else "Open folder"),
            command=self._open_folder, lang=self._lang, height=38,
            color=config.GOLD,
        ).grid(row=0, column=1, sticky="ew", padx=2)
        TextButton(
            self._success_frame,
            text=(i18n.t("share", self._lang)
                   if i18n.t("share", self._lang) != "share"
                   else "اشتراک"),
            command=self._share_file, lang=self._lang, height=38,
            color=config.GOLD,
        ).grid(row=0, column=2, sticky="ew", padx=2)
        self._success_frame.grid_remove()
        row += 1

        Divider(form).grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1

        # --- Buttons -----------------------------------------------
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
        self._export_btn = GoldButton(
            btn_row,
            text=(i18n.t("export", self._lang)
                   if i18n.t("export", self._lang) != "export"
                   else "خروجی"),
            command=self._on_export,
            lang=self._lang, height=46,
            icon_name="export", icon_size=16,
        )
        if rtl:
            self._export_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._export_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    # ------------------------------------------------------------------
    def _format_date(self, iso: str) -> str:
        if not iso:
            return ""
        try:
            if self._lang == "fa":
                from ...core import jalali
                jy, jm, jd = jalali.iso_to_jalali(iso)
                return i18n.to_fa_digits(f"{jd:02d}/{jm:02d}/{jy % 100:02d}")
            return iso
        except Exception:
            return iso

    def _default_path_preview(self) -> str:
        try:
            ext = next(f["ext"] for f in FORMATS if f["key"] == self._format)
        except StopIteration:
            ext = "pdf"
        if self._output_path:
            return self._output_path
        try:
            from ...core import time_utils as _tu
            name = f"rask-export_{self._date_from}_to_{self._date_to}.{ext}"
            return os.path.join(str(config.EXPORT_DIR), name)
        except Exception:
            return f"rask-export.{ext}"

    # ------------------------------------------------------------------
    def _on_format_change(self, key: str) -> None:
        self._format = key
        try:
            if key == "pdf":
                self._pdf_options_frame.grid()
            else:
                self._pdf_options_frame.grid_remove()
            self._path_label.configure(text=self._default_path_preview())
        except Exception:
            pass

    def _on_preset_change(self, key: str) -> None:
        self._range_preset = key
        self._date_from, self._date_to = _preset_range(key)
        try:
            self._from_btn.configure(
                text=self._format_date(self._date_from))
            self._to_btn.configure(text=self._format_date(self._date_to))
            self._path_label.configure(text=self._default_path_preview())
        except Exception:
            pass
        # Update preset button highlight by rebuilding the row
        # (simplest correct approach — the row is small)
        try:
            self._build_content()  # would rebuild — skip; just update colors
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _open_from_picker(self) -> None:
        try:
            self._from_dlg = DatePicker(
                self, initial=self._date_from,
                on_result=self._on_from_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_from_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._date_from = iso
        self._range_preset = "custom"
        try:
            self._from_btn.configure(text=self._format_date(iso))
            self._path_label.configure(text=self._default_path_preview())
        except Exception:
            pass

    def _open_to_picker(self) -> None:
        try:
            self._to_dlg = DatePicker(
                self, initial=self._date_to,
                on_result=self._on_to_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_to_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._date_to = iso
        self._range_preset = "custom"
        try:
            self._to_btn.configure(text=self._format_date(iso))
            self._path_label.configure(text=self._default_path_preview())
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _categories_label(self) -> str:
        if not self._category_ids:
            return (i18n.t("allCategories", self._lang)
                     if i18n.t("allCategories", self._lang)
                     != "allCategories"
                     else "همه دسته‌ها")
        try:
            cats = db.category_list(include_archived=False)
            names = []
            for cid in self._category_ids:
                for c in cats:
                    if int(c["id"]) == cid:
                        names.append((c.get("name_fa") if self._lang == "fa"
                                       else c.get("name_en"))
                                      or c.get("key", "—"))
                        break
            return ", ".join(names) if names else "—"
        except Exception:
            return "—"

    def _open_category_picker(self) -> None:
        # Use FilterSheet for multi-select
        try:
            from ..widgets.sheets import FilterSheet
            cats = db.category_list(include_archived=False)
            options = [(c.get("name_fa") if self._lang == "fa"
                         else c.get("name_en")) or c.get("key", "—")
                        for c in cats]
            selected = [self._category_label_for(cid, cats)
                          for cid in self._category_ids]
            self._cat_dlg = FilterSheet(
                self,
                title=(i18n.t("categories", self._lang)
                        if i18n.t("categories", self._lang) != "categories"
                        else "دسته‌ها"),
                options=options,
                selected=selected,
                on_apply=self._on_categories_applied,
                lang=self._lang,
            )
        except Exception:
            pass

    def _category_label_for(self, cid: int,
                              cats: List[Dict[str, Any]]) -> str:
        for c in cats:
            if int(c["id"]) == cid:
                return (c.get("name_fa") if self._lang == "fa"
                         else c.get("name_en")) or c.get("key", "—")
        return ""

    def _on_categories_applied(self, selected_labels: List[str]) -> None:
        try:
            cats = db.category_list(include_archived=False)
            self._category_ids = []
            for c in cats:
                label = (c.get("name_fa") if self._lang == "fa"
                          else c.get("name_en")) or c.get("key", "—")
                if label in selected_labels:
                    self._category_ids.append(int(c["id"]))
        except Exception:
            pass
        try:
            self._cat_btn.configure(text=self._categories_label())
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _pick_output_path(self) -> None:
        if not _FD_OK:
            return
        try:
            ext = next(f["ext"] for f in FORMATS if f["key"] == self._format)
            path = filedialog.asksaveasfilename(
                title=("انتخاب مسیر خروجی" if self._lang == "fa"
                        else "Choose output path"),
                initialdir=str(config.EXPORT_DIR),
                defaultextension=f".{ext}",
                filetypes=[(f"{ext.upper()}", f"*.{ext}"),
                            ("All files", "*.*")],
            )
            if path:
                self._output_path = path
                try:
                    self._path_label.configure(text=path)
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        if self._busy:
            return
        date_from = self._date_from
        date_to = self._date_to
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        self._set_busy(True)
        try:
            self._progress.set(0.1)
        except Exception:
            pass

        fmt = self._format
        path = self._output_path or None

        def worker() -> None:
            try:
                if fmt == "csv":
                    result = export_service.export_csv(
                        date_from, date_to, path=path)
                elif fmt == "json":
                    result = export_service.export_json(
                        date_from, date_to, path=path)
                elif fmt == "pdf":
                    result = export_service.export_pdf(
                        date_from, date_to, path=path)
                elif fmt == "png":
                    result = export_service.export_png(
                        date_from, date_to, path=path)
                else:
                    result = {"success": False, "error": "unknown format"}
            except Exception as exc:  # noqa: BLE001
                result = {"success": False, "error": str(exc),
                            "path": None}
            try:
                self.after(0, lambda: self._on_export_done(result))
            except Exception:
                pass

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        self._animate_progress(0.1, 0.85, step=0.05)

    def _on_export_done(self, result: Dict[str, Any]) -> None:
        self._set_busy(False)
        try:
            self._progress.set(1.0 if result.get("success") else 0.0)
        except Exception:
            pass
        if result.get("success"):
            try:
                Toast.show(
                    self,
                    (i18n.t("exportSuccess", self._lang)
                      if i18n.t("exportSuccess", self._lang)
                      != "exportSuccess"
                      else "خروجی ساخته شد"),
                    kind="success", lang=self._lang,
                )
            except Exception:
                pass
            try:
                settings_service.set_last_export_iso(
                    time_utils.now_iso_utc())
            except Exception:
                pass
            # Show the success actions
            try:
                self._status_label.configure(
                    text=("خروجی ساخته شد: " if self._lang == "fa"
                           else "Exported: ") + (result.get("path") or ""),
                    text_color=config.SUCCESS)
            except Exception:
                pass
            try:
                self._success_frame.grid()
            except Exception:
                pass
            # Keep the dialog open so the user can act on the result.
            # Store the path on self for the open-file / share buttons.
            self._last_exported_path = result.get("path")
            # Auto-close after a short delay
            try:
                self.after(2500, lambda: self.close({
                    "action": "export", "success": True,
                    "path": result.get("path"), "format": self._format,
                }))
            except Exception:
                pass
        else:
            err = result.get("error") or ""
            self._status_label.configure(
                text=(err or (i18n.t("exportFailed", self._lang)
                               if i18n.t("exportFailed", self._lang)
                               != "exportFailed"
                               else "خروجی ناموفق")),
                text_color=config.DANGER)

    # ------------------------------------------------------------------
    def _open_file(self) -> None:
        path = getattr(self, "_last_exported_path", None)
        if not path or not os.path.isfile(path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _open_folder(self) -> None:
        path = getattr(self, "_last_exported_path", None)
        if not path:
            return
        folder = os.path.dirname(path) or str(config.EXPORT_DIR)
        try:
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    def _share_file(self) -> None:
        # Desktop share is platform-dependent — for now we just open
        # the parent folder (same as _open_folder).
        self._open_folder()

    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        try:
            self._export_btn.configure(
                state="disabled" if busy else "normal",
                text="…" if busy else (
                    i18n.t("export", self._lang)
                    if i18n.t("export", self._lang) != "export"
                    else "خروجی"),
            )
        except Exception:
            pass

    def _animate_progress(self, start: float, end: float,
                            step: float = 0.05) -> None:
        if not self._busy:
            return
        try:
            cur = start + step
            if cur >= end:
                cur = start + step
            self._progress.set(cur)
        except Exception:
            pass
        try:
            self.after(220,
                        lambda: self._animate_progress(start, end, step))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_cancel(self) -> None:
        if self._busy:
            return
        self.close({"action": "cancelled", "success": False, "path": None,
                     "format": self._format})

    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self._on_cancel(), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("export_dialog module: 1 class (ExportDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
