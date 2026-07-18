"""
rask.ui.dialogs.compare_dialog
==============================

Modal dialog for comparing two periods side-by-side.

Layout
------
  * Title row: ``"مقایسه دوره‌ها"`` + close (×)
  * Period A: preset dropdown + custom date range (from / to)
  * Period B: preset dropdown + custom date range (from / to)
  * Quick swap button (swaps A and B)
  * Compare by: total time / activity count / avg per day
    (SegmentedControl)
  * Compare button → opens the stats screen with comparison view
  * Cancel button

Mirrors ``web/js/app.js :: openCompareDialog`` 1:1.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import time_utils
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton, IconButton
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.toggles import SegmentedControl
from ..widgets.date_picker import DatePicker
from ..widgets.scrollable import SmoothScrollFrame

__all__ = ["CompareDialog", "CompareRequest"]


# =============================================================================
# === CompareRequest (the result returned by CompareDialog)                  ===
# =============================================================================

class CompareRequest:
    """Plain data holder for a compare request."""

    def __init__(
        self,
        a_from: str,
        a_to: str,
        b_from: str,
        b_to: str,
        metric: str = "total_time",
    ) -> None:
        self.a_from = a_from
        self.a_to = a_to
        self.b_from = b_from
        self.b_to = b_to
        self.metric = metric  # "total_time" / "count" / "avg_per_day"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "a_from": self.a_from, "a_to": self.a_to,
            "b_from": self.b_from, "b_to": self.b_to,
            "metric": self.metric,
        }


# =============================================================================
# === Period presets                                                         ===
# =============================================================================

PERIOD_PRESETS: List[Dict[str, Any]] = [
    {"key": "this_week", "label_fa": "این هفته", "label_en": "This Week",
     "days": 7, "offset": 0},
    {"key": "last_week", "label_fa": "هفته گذشته", "label_en": "Last Week",
     "days": 7, "offset": 7},
    {"key": "this_month", "label_fa": "این ماه", "label_en": "This Month",
     "days": 30, "offset": 0},
    {"key": "last_month", "label_fa": "ماه گذشته", "label_en": "Last Month",
     "days": 30, "offset": 30},
    {"key": "this_quarter", "label_fa": "این فصل", "label_en": "This Quarter",
     "days": 90, "offset": 0},
    {"key": "last_quarter", "label_fa": "فصل گذشته", "label_en": "Last Quarter",
     "days": 90, "offset": 90},
    {"key": "custom", "label_fa": "دلخواه", "label_en": "Custom",
     "days": 0, "offset": 0},
]


def _preset_range(preset_key: str) -> Tuple[str, str]:
    """Return (from_iso, to_iso) for the preset key."""
    today = date.today()
    preset = next((p for p in PERIOD_PRESETS if p["key"] == preset_key),
                   None)
    if not preset or preset_key == "custom":
        # Default to "this week"
        start = (today - timedelta(days=6)).isoformat()
        return start, today.isoformat()
    days = preset.get("days", 7)
    offset = preset.get("offset", 0)
    if offset:
        end = today - timedelta(days=offset)
        start = end - timedelta(days=days - 1)
    else:
        end = today
        start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


# =============================================================================
# === CompareDialog                                                          ===
# =============================================================================

class CompareDialog(BaseDialog):
    """Modal period-comparison dialog.

    Parameters
    ----------
    master
        Parent widget.
    lang
        UI language.
    on_result
        Callback receiving a :class:`CompareRequest` on Compare, or
        ``None`` on Cancel.
    """

    METRIC_TOTAL_TIME = "total_time"
    METRIC_COUNT = "count"
    METRIC_AVG_PER_DAY = "avg_per_day"

    def __init__(
        self,
        master: Any,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[CompareRequest]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._a_preset = "this_week"
        self._b_preset = "last_week"
        self._a_from, self._a_to = _preset_range(self._a_preset)
        self._b_from, self._b_to = _preset_range(self._b_preset)
        self._metric = self.METRIC_TOTAL_TIME
        self._a_from_dlg = None
        self._a_to_dlg = None
        self._b_from_dlg = None
        self._b_to_dlg = None
        kwargs.setdefault("height", 600)
        kwargs.setdefault("width", 480)
        kwargs.setdefault("close_on_overlay", False)
        super().__init__(
            master,
            title=(i18n.t("comparison", lang) if lang == "fa"
                    else "Compare"),
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

        # --- Period A ----------------------------------------------
        SectionTitle(
            form, text=("دوره A" if self._lang == "fa" else "Period A"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        # Preset dropdown for A
        self._a_preset_btn = ctk.CTkButton(
            form, text=self._preset_label(self._a_preset),
            command=self._cycle_a_preset,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._a_preset_btn.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        # A from / to
        a_range_row = ctk.CTkFrame(form, fg_color="transparent")
        a_range_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        a_range_row.grid_columnconfigure(0, weight=1)
        a_range_row.grid_columnconfigure(1, weight=1)
        self._a_from_btn = ctk.CTkButton(
            a_range_row, text=self._format_date(self._a_from),
            command=self._open_a_from,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        self._a_to_btn = ctk.CTkButton(
            a_range_row, text=self._format_date(self._a_to),
            command=self._open_a_to,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        if rtl:
            self._a_to_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._a_from_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            self._a_from_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._a_to_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        row += 1

        # --- Swap button -------------------------------------------
        swap_row = ctk.CTkFrame(form, fg_color="transparent")
        swap_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        swap_row.grid_columnconfigure(0, weight=1)
        swap_btn = TextButton(
            swap_row,
            text=("جابه‌جایی A ↔ B" if self._lang == "fa"
                    else "Swap A ↔ B"),
            command=self._swap_periods,
            lang=self._lang, height=32,
            color=config.GOLD, hover_color=config.GOLD_BRIGHT,
            icon_name="refresh", icon_size=14,
        )
        swap_btn.grid(row=0, column=0, sticky="ew")
        row += 1

        # --- Period B ----------------------------------------------
        SectionTitle(
            form, text=("دوره B" if self._lang == "fa" else "Period B"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        self._b_preset_btn = ctk.CTkButton(
            form, text=self._preset_label(self._b_preset),
            command=self._cycle_b_preset,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
        )
        self._b_preset_btn.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        b_range_row = ctk.CTkFrame(form, fg_color="transparent")
        b_range_row.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        b_range_row.grid_columnconfigure(0, weight=1)
        b_range_row.grid_columnconfigure(1, weight=1)
        self._b_from_btn = ctk.CTkButton(
            b_range_row, text=self._format_date(self._b_from),
            command=self._open_b_from,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        self._b_to_btn = ctk.CTkButton(
            b_range_row, text=self._format_date(self._b_to),
            command=self._open_b_to,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            border_width=1, border_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_MD, height=38, cursor="hand2",
            anchor="e" if rtl else "w",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
        )
        if rtl:
            self._b_to_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._b_from_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            self._b_from_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            self._b_to_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        row += 1

        # --- Compare by --------------------------------------------
        SectionTitle(
            form,
            text=("مقایسه بر اساس" if self._lang == "fa"
                    else "Compare by"),
            lang=self._lang,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 4))
        row += 1
        metric_values = [
            (i18n.t("totalTime", self._lang)
              if i18n.t("totalTime", self._lang) != "totalTime"
              else "کل زمان"),
            (i18n.t("totalActivities", self._lang)
              if i18n.t("totalActivities", self._lang)
              != "totalActivities"
              else "تعداد فعالیت"),
            (i18n.t("avgPerDay", self._lang)
              if i18n.t("avgPerDay", self._lang) != "avgPerDay"
              else "میانگین روزانه"),
        ]
        self._metric_seg = SegmentedControl(
            form, values=metric_values,
            on_change=lambda v: self._on_metric_change(v, metric_values),
            lang=self._lang, height=38,
        )
        # Set initial selection
        self._metric_seg.set(metric_values[0])
        self._metric_seg.grid(row=row, column=0, sticky="ew", pady=(0, 8))
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
            command=lambda: self.close(None),
            lang=self._lang, height=46,
        )
        compare_btn = GoldButton(
            btn_row,
            text=(i18n.t("comparison", self._lang)
                   if i18n.t("comparison", self._lang) != "comparison"
                   else "مقایسه"),
            command=self._on_compare,
            lang=self._lang, height=46,
            icon_name="chart_bar", icon_size=16,
        )
        if rtl:
            compare_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            compare_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

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

    def _preset_label(self, key: str) -> str:
        preset = next((p for p in PERIOD_PRESETS if p["key"] == key), None)
        if not preset:
            return key
        return (preset["label_fa"] if self._lang == "fa"
                 else preset["label_en"])

    def _cycle_a_preset(self) -> None:
        keys = [p["key"] for p in PERIOD_PRESETS]
        try:
            idx = keys.index(self._a_preset)
            new_key = keys[(idx + 1) % len(keys)]
        except ValueError:
            new_key = keys[0]
        self._a_preset = new_key
        if new_key != "custom":
            self._a_from, self._a_to = _preset_range(new_key)
        try:
            self._a_preset_btn.configure(text=self._preset_label(new_key))
            self._a_from_btn.configure(text=self._format_date(self._a_from))
            self._a_to_btn.configure(text=self._format_date(self._a_to))
        except Exception:
            pass

    def _cycle_b_preset(self) -> None:
        keys = [p["key"] for p in PERIOD_PRESETS]
        try:
            idx = keys.index(self._b_preset)
            new_key = keys[(idx + 1) % len(keys)]
        except ValueError:
            new_key = keys[1] if len(keys) > 1 else keys[0]
        self._b_preset = new_key
        if new_key != "custom":
            self._b_from, self._b_to = _preset_range(new_key)
        try:
            self._b_preset_btn.configure(text=self._preset_label(new_key))
            self._b_from_btn.configure(text=self._format_date(self._b_from))
            self._b_to_btn.configure(text=self._format_date(self._b_to))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _swap_periods(self) -> None:
        self._a_preset, self._b_preset = self._b_preset, self._a_preset
        self._a_from, self._b_from = self._b_from, self._a_from
        self._a_to, self._b_to = self._b_to, self._a_to
        try:
            self._a_preset_btn.configure(text=self._preset_label(self._a_preset))
            self._b_preset_btn.configure(text=self._preset_label(self._b_preset))
            self._a_from_btn.configure(text=self._format_date(self._a_from))
            self._a_to_btn.configure(text=self._format_date(self._a_to))
            self._b_from_btn.configure(text=self._format_date(self._b_from))
            self._b_to_btn.configure(text=self._format_date(self._b_to))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_metric_change(self, label: str,
                            labels: List[str]) -> None:
        if label == labels[0]:
            self._metric = self.METRIC_TOTAL_TIME
        elif label == labels[1]:
            self._metric = self.METRIC_COUNT
        elif label == labels[2]:
            self._metric = self.METRIC_AVG_PER_DAY

    # ------------------------------------------------------------------
    def _open_a_from(self) -> None:
        try:
            self._a_from_dlg = DatePicker(
                self, initial=self._a_from,
                on_result=self._on_a_from_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_a_from_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._a_from = iso
        self._a_preset = "custom"
        try:
            self._a_from_btn.configure(text=self._format_date(iso))
            self._a_preset_btn.configure(text=self._preset_label("custom"))
        except Exception:
            pass

    def _open_a_to(self) -> None:
        try:
            self._a_to_dlg = DatePicker(
                self, initial=self._a_to,
                on_result=self._on_a_to_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_a_to_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._a_to = iso
        self._a_preset = "custom"
        try:
            self._a_to_btn.configure(text=self._format_date(iso))
            self._a_preset_btn.configure(text=self._preset_label("custom"))
        except Exception:
            pass

    def _open_b_from(self) -> None:
        try:
            self._b_from_dlg = DatePicker(
                self, initial=self._b_from,
                on_result=self._on_b_from_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_b_from_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._b_from = iso
        self._b_preset = "custom"
        try:
            self._b_from_btn.configure(text=self._format_date(iso))
            self._b_preset_btn.configure(text=self._preset_label("custom"))
        except Exception:
            pass

    def _open_b_to(self) -> None:
        try:
            self._b_to_dlg = DatePicker(
                self, initial=self._b_to,
                on_result=self._on_b_to_picked, lang=self._lang,
            )
        except Exception:
            pass

    def _on_b_to_picked(self, iso: Optional[str]) -> None:
        if not iso:
            return
        self._b_to = iso
        self._b_preset = "custom"
        try:
            self._b_to_btn.configure(text=self._format_date(iso))
            self._b_preset_btn.configure(text=self._preset_label("custom"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_compare(self) -> None:
        # Normalize range ordering
        a_from, a_to = sorted([self._a_from, self._a_to])
        b_from, b_to = sorted([self._b_from, self._b_to])
        req = CompareRequest(
            a_from=a_from, a_to=a_to,
            b_from=b_from, b_to=b_to,
            metric=self._metric,
        )
        self.close(req)

    def _bind_keys(self) -> None:  # type: ignore[override]
        try:
            self.bind("<Escape>", lambda _e: self.close(None), add="+")
        except Exception:
            pass


def _self_test() -> int:
    print("compare_dialog module: 1 class (CompareDialog) + CompareRequest")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
