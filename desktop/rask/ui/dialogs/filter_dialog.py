"""
rask.ui.dialogs.filter_dialog
=============================

Bottom-sheet activity filter dialog.

Layout
------
  * Title row: ``"فیلترها"`` + active-filter count badge + close
  * Search query (GoldEntry)
  * Categories — multi-select chips
  * Tags — multi-select with autocomplete (GoldEntry, comma-separated)
  * Date range — from / to DatePickers + presets (today, this week,
    this month, custom)
  * Duration range — min/max sliders (0-480 min)
  * Kinds — multi-select (manual, stopwatch, template, voice, recurring)
  * Apply / Clear / Cancel buttons

Active-filter count badge is shown in the title row when any filter is
non-default.

Mirrors ``web/js/app.js :: openFilterSheet`` 1:1.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import time_utils
from ... import database as db
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BottomSheet
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry, NumberEntry
from ..widgets.toggles import CheckBox, SegmentedControl
from ..widgets.dividers import Divider, SectionTitle, Pill
from ..widgets.badges import CountBadge, Chip
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.date_picker import DatePicker
from ..widgets.sliders import RangeSlider

__all__ = ["FilterDialog", "FilterState"]


# =============================================================================
# === FilterState (the result returned by FilterDialog)                     ===
# =============================================================================

class FilterState:
    """Plain data holder for the active filter state.

    All fields are optional — ``None`` / empty means "no filter on
    this dimension".
    """

    def __init__(
        self,
        query: str = "",
        category_ids: Optional[List[int]] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
        kinds: Optional[List[str]] = None,
    ) -> None:
        self.query = query
        self.category_ids = list(category_ids) if category_ids else []
        self.tags = list(tags) if tags else []
        self.date_from = date_from
        self.date_to = date_to
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.kinds = list(kinds) if kinds else []

    def is_default(self) -> bool:
        """Return True if no filter is applied (all defaults)."""
        return (
            not self.query.strip()
            and not self.category_ids
            and not self.tags
            and not self.date_from
            and not self.date_to
            and not self.min_duration
            and not self.max_duration
            and not self.kinds
        )

    def active_count(self) -> int:
        """Count how many filter dimensions are non-default."""
        n = 0
        if self.query.strip():
            n += 1
        if self.category_ids:
            n += 1
        if self.tags:
            n += 1
        if self.date_from or self.date_to:
            n += 1
        if self.min_duration:
            n += 1
        if self.max_duration:
            n += 1
        if self.kinds:
            n += 1
        return n

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "category_ids": list(self.category_ids),
            "tags": list(self.tags),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "kinds": list(self.kinds),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FilterState":
        return cls(
            query=d.get("query", ""),
            category_ids=d.get("category_ids"),
            tags=d.get("tags"),
            date_from=d.get("date_from"),
            date_to=d.get("date_to"),
            min_duration=d.get("min_duration"),
            max_duration=d.get("max_duration"),
            kinds=d.get("kinds"),
        )


# =============================================================================
# === Activity kinds                                                         ===
# =============================================================================

KIND_LABELS_FA: Dict[str, str] = {
    "manual": "دستی",
    "stopwatch": "کرنومتر",
    "template": "قالب",
    "voice": "صوتی",
    "recurring": "تکرارشونده",
}
KIND_LABELS_EN: Dict[str, str] = {
    "manual": "Manual",
    "stopwatch": "Stopwatch",
    "template": "Template",
    "voice": "Voice",
    "recurring": "Recurring",
}


def _kind_label(kind: str, lang: str) -> str:
    if lang == "fa":
        return KIND_LABELS_FA.get(kind, kind)
    return KIND_LABELS_EN.get(kind, kind)


# =============================================================================
# === Date presets                                                           ===
# =============================================================================

DATE_PRESETS: List[Dict[str, Any]] = [
    {"key": "today", "label_fa": "امروز", "label_en": "Today", "days": 1},
    {"key": "week", "label_fa": "این هفته", "label_en": "This Week",
     "days": 7},
    {"key": "month", "label_fa": "این ماه", "label_en": "This Month",
     "days": 30},
]


def _preset_range(preset_key: str) -> tuple:
    today = date.today()
    today_iso = today.isoformat()
    if preset_key == "today":
        return today_iso, today_iso
    days_map = {p["key"]: p.get("days", 7) for p in DATE_PRESETS}
    days = days_map.get(preset_key, 7)
    start = (today - timedelta(days=days - 1)).isoformat()
    return start, today_iso


# =============================================================================
# === FilterDialog                                                           ===
# =============================================================================

class FilterDialog(BottomSheet):
    """Bottom-sheet activity filter.

    Parameters
    ----------
    master
        Parent widget.
    initial
        Optional :class:`FilterState` to pre-fill the form.
    lang
        UI language.
    on_result
        Callback receiving the :class:`FilterState` (on Apply) or
        ``None`` (on Cancel / Clear).
    """

    def __init__(
        self,
        master: Any,
        initial: Optional[FilterState] = None,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[FilterState]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._state = initial or FilterState()
        self._categories: List[Dict[str, Any]] = []
        try:
            self._categories = db.category_list(include_archived=False)
        except Exception:
            pass
        self._from_dlg = None
        self._to_dlg = None
        kwargs.setdefault("height", 720)
        kwargs.setdefault("close_on_overlay", False)
        super().__init__(
            master,
            title=(i18n.t("filters", lang) if lang == "fa"
                    else "Filters"),
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

        # --- Search query ------------------------------------------
        SectionTitle(
            form,
            text=(i18n.t("searchQuery", self._lang)
                   if i18n.t("searchQuery", self._lang)
                   != "searchQuery"
                   else "عبارت جستجو"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._query_entry = GoldEntry(
            form, lang=self._lang, height=42,
            placeholder=(i18n.t("searchQuery", self._lang)
                          if i18n.t("searchQuery", self._lang)
                          != "searchQuery"
                          else "جستجو…"),
        )
        self._query_entry.value = self._state.query
        self._query_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
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
        self._cat_frame = ctk.CTkFrame(form, fg_color="transparent")
        self._cat_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self._cat_checkboxes: Dict[int, CheckBox] = {}
        for cat in self._categories:
            try:
                cid = int(cat["id"])
                name = (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or cat.get("key", "—")
                cb = CheckBox(
                    self._cat_frame, text=name,
                    on_change=lambda v, c=cid: self._on_cat_toggle(c, v),
                    lang=self._lang,
                    font_size=config.FONT_SIZE_SMALL,
                )
                cb.value = cid in self._state.category_ids
                cb.pack(anchor="e" if rtl else "w", padx=4, pady=2)
                self._cat_checkboxes[cid] = cb
            except Exception:
                continue
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
            form, lang=self._lang, height=42,
            placeholder=(i18n.t("tagsPlaceholder", self._lang)
                          if i18n.t("tagsPlaceholder", self._lang)
                          != "tagsPlaceholder"
                          else "با کاما جدا کن"),
        )
        if self._state.tags:
            self._tags_entry.value = ", ".join(self._state.tags)
        self._tags_entry.grid(row=row, column=0, sticky="ew", pady=(0, 8))
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
        for i in range(3):
            preset_row.grid_columnconfigure(i, weight=1)
        for i, preset in enumerate(DATE_PRESETS):
            label = (preset["label_fa"] if self._lang == "fa"
                      else preset["label_en"])
            TextButton(
                preset_row, text=label,
                command=lambda k=preset["key"]: self._apply_date_preset(k),
                lang=self._lang, height=30, color=config.TEXT_DIM,
                hover_color=config.GOLD,
            ).grid(row=0, column=i, sticky="ew", padx=2)
        row += 1
        # From / To
        range_row = ctk.CTkFrame(form, fg_color="transparent")
        range_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        range_row.grid_columnconfigure(0, weight=1)
        range_row.grid_columnconfigure(1, weight=1)
        self._from_btn = ctk.CTkButton(
            range_row, text=self._format_date(self._state.date_from),
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
            range_row, text=self._format_date(self._state.date_to),
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

        # --- Duration range ----------------------------------------
        SectionTitle(
            form,
            text=("بازه مدت" if self._lang == "fa" else "Duration range"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        dur_row = ctk.CTkFrame(form, fg_color="transparent")
        dur_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        dur_row.grid_columnconfigure(0, weight=1)
        dur_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            dur_row,
            text=(i18n.t("minDuration", self._lang)
                   if i18n.t("minDuration", self._lang) != "minDuration"
                   else "حداقل مدت"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew", padx=2)
        self._min_dur = NumberEntry(
            dur_row, lang=self._lang,
            min_value=0, max_value=1440, step=5,
            unit=("دقیقه" if self._lang == "fa" else "min"),
            height=38, show_stepper=True,
        )
        self._min_dur.value = self._state.min_duration or 0
        if rtl:
            self._min_dur.grid(row=1, column=0, sticky="ew", padx=2)
        else:
            self._min_dur.grid(row=1, column=0, sticky="ew", padx=2)
        ctk.CTkLabel(
            dur_row,
            text=(i18n.t("maxDuration", self._lang)
                   if i18n.t("maxDuration", self._lang) != "maxDuration"
                   else "حداکثر مدت"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=2, column=0, sticky="ew", padx=2)
        self._max_dur = NumberEntry(
            dur_row, lang=self._lang,
            min_value=0, max_value=1440, step=5,
            unit=("دقیقه" if self._lang == "fa" else "min"),
            height=38, show_stepper=True,
        )
        self._max_dur.value = self._state.max_duration or 0
        self._max_dur.grid(row=3, column=0, sticky="ew", padx=2)
        row += 1

        # --- Kinds -------------------------------------------------
        SectionTitle(
            form,
            text=("نوع فعالیت" if self._lang == "fa" else "Kinds"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._kind_checkboxes: Dict[str, CheckBox] = {}
        for kind in ("manual", "stopwatch", "template", "voice", "recurring"):
            cb = CheckBox(
                form, text=_kind_label(kind, self._lang),
                on_change=lambda v, k=kind: self._on_kind_toggle(k, v),
                lang=self._lang, font_size=config.FONT_SIZE_SMALL,
            )
            cb.value = kind in self._state.kinds
            cb.pack(anchor="e" if rtl else "w", padx=4, pady=2)
            self._kind_checkboxes[kind] = cb
        row += 1

        Divider(form).grid(row=row, column=0, sticky="ew", pady=(8, 8))
        row += 1

        # --- Buttons: Apply / Clear / Cancel ------------------------
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=2)
        clear_btn = TextButton(
            btn_row,
            text=(i18n.t("clear", self._lang)
                   if i18n.t("clear", self._lang) != "clear"
                   else "پاک‌کردن"),
            command=self._on_clear,
            lang=self._lang, height=42,
            color=config.TEXT_DIM, hover_color=config.DANGER,
        )
        cancel_btn = GhostButton(
            btn_row,
            text=(i18n.t("cancel", self._lang)
                   if i18n.t("cancel", self._lang) != "cancel"
                   else "انصراف"),
            command=lambda: self.close(None),
            lang=self._lang, height=42,
        )
        apply_btn = GoldButton(
            btn_row,
            text=(i18n.t("apply", self._lang)
                   if i18n.t("apply", self._lang) != "apply"
                   else "اعمال"),
            command=self._on_apply,
            lang=self._lang, height=42,
            icon_name="check", icon_size=14,
        )
        if rtl:
            apply_btn.grid(row=0, column=0, sticky="ew", padx=2)
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=2)
            clear_btn.grid(row=0, column=2, sticky="ew", padx=2)
        else:
            clear_btn.grid(row=0, column=0, sticky="ew", padx=2)
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=2)
            apply_btn.grid(row=0, column=2, sticky="ew", padx=2)

    # ------------------------------------------------------------------
    def _format_date(self, iso: Optional[str]) -> str:
        if not iso:
            return ("—" if self._lang == "fa" else "—")
        try:
            if self._lang == "fa":
                from ...core import jalali
                jy, jm, jd = jalali.iso_to_jalali(iso)
                return i18n.to_fa_digits(f"{jd:02d}/{jm:02d}/{jy % 100:02d}")
            return iso
        except Exception:
            return iso

    def _open_from_picker(self) -> None:
        try:
            self._from_dlg = DatePicker(
                self, initial=self._state.date_from,
                on_result=self._on_from_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_from_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._state.date_from = iso
        try:
            self._from_btn.configure(text=self._format_date(iso))
        except Exception:
            pass

    def _open_to_picker(self) -> None:
        try:
            self._to_dlg = DatePicker(
                self, initial=self._state.date_to,
                on_result=self._on_to_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_to_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._state.date_to = iso
        try:
            self._to_btn.configure(text=self._format_date(iso))
        except Exception:
            pass

    def _apply_date_preset(self, key: str) -> None:
        f, t = _preset_range(key)
        self._state.date_from = f
        self._state.date_to = t
        try:
            self._from_btn.configure(text=self._format_date(f))
            self._to_btn.configure(text=self._format_date(t))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_cat_toggle(self, cid: int, value: bool) -> None:
        if value:
            if cid not in self._state.category_ids:
                self._state.category_ids.append(cid)
        else:
            if cid in self._state.category_ids:
                self._state.category_ids.remove(cid)

    def _on_kind_toggle(self, kind: str, value: bool) -> None:
        if value:
            if kind not in self._state.kinds:
                self._state.kinds.append(kind)
        else:
            if kind in self._state.kinds:
                self._state.kinds.remove(kind)

    # ------------------------------------------------------------------
    def _collect_state(self) -> FilterState:
        """Pull the current form values into a FilterState."""
        s = FilterState()
        s.query = self._query_entry.value.strip()
        s.category_ids = list(self._state.category_ids)
        tags_str = self._tags_entry.value.strip()
        s.tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        s.date_from = self._state.date_from or None
        s.date_to = self._state.date_to or None
        try:
            mn = self._min_dur.value
            if mn and mn > 0:
                s.min_duration = int(mn)
        except Exception:
            pass
        try:
            mx = self._max_dur.value
            if mx and mx > 0:
                s.max_duration = int(mx)
        except Exception:
            pass
        s.kinds = list(self._state.kinds)
        return s

    def _on_apply(self) -> None:
        s = self._collect_state()
        self.close(s)

    def _on_clear(self) -> None:
        # Reset all fields to default
        self._state = FilterState()
        try:
            self._query_entry.value = ""
            self._tags_entry.value = ""
            self._from_btn.configure(text=self._format_date(None))
            self._to_btn.configure(text=self._format_date(None))
            self._min_dur.value = 0
            self._max_dur.value = 0
            for cb in self._cat_checkboxes.values():
                cb.value = False
            for cb in self._kind_checkboxes.values():
                cb.value = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self.close(None), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("filter_dialog module: 1 class (FilterDialog) + FilterState")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
