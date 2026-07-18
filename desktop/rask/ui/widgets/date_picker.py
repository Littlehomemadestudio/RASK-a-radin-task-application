"""
rask.ui.widgets.date_picker
===========================

Modal date picker using :class:`CalendarGrid`.

  * ``DatePicker(BottomSheet)``
  * Class method ``DatePicker.ask(parent, initial=None, calendar_system="jalali") -> str | None``
  * Quick links: Today, Yesterday, Tomorrow
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

import customtkinter as ctk

from ... import config
from ...core import jalali
from ... import i18n
from . import theme as _theme
from .calendar_grid import CalendarGrid
from .dialogs import BottomSheet
from .buttons import GoldButton, GhostButton, TextButton
from .dividers import Divider

__all__ = ["DatePicker"]


# =============================================================================
# === DatePicker                                                            ===
# =============================================================================

class DatePicker(BottomSheet):
    """Modal date picker using the :class:`CalendarGrid` widget.

    Quick links
    ------------
    Three buttons at the bottom allow selecting Today, Yesterday, or
    Tomorrow in a single tap.

    Returns
    -------
    On confirm, ``.result`` is the selected ISO date string.  On cancel
    or dismiss, ``.result`` is ``None``.
    """

    def __init__(
        self,
        master: Any = None,
        initial: Optional[str] = None,
        calendar_system: str = "jalali",
        on_result: Optional[Callable] = None,  # noqa: F821
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._initial = initial
        self._calendar_system = calendar_system
        kwargs.setdefault("height", 520)
        super().__init__(master, title="انتخاب تاریخ" if lang == "fa"
                          else "Pick date", lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Calendar grid
        self._calendar = CalendarGrid(
            self._content,
            calendar_system=self._calendar_system,
            lang=self._lang,
            on_select=self._on_select,
            cell_size=44,
        )
        self._calendar.pack(fill="both", expand=True, pady=(0, 8))
        # Pre-select initial date
        if self._initial:
            self._calendar.select_date(self._initial)
        # Quick links row
        quick_row = ctk.CTkFrame(self._content, fg_color="transparent")
        quick_row.pack(fill="x", pady=(0, 8))
        quick_row.grid_columnconfigure(0, weight=1)
        quick_row.grid_columnconfigure(1, weight=1)
        quick_row.grid_columnconfigure(2, weight=1)
        today_text = "امروز" if self._lang == "fa" else "Today"
        yesterday_text = "دیروز" if self._lang == "fa" else "Yesterday"
        tomorrow_text = "فردا" if self._lang == "fa" else "Tomorrow"
        TextButton(quick_row, text=today_text,
                    command=self._pick_today,
                    lang=self._lang).grid(row=0, column=0, sticky="ew", padx=2)
        TextButton(quick_row, text=yesterday_text,
                    command=self._pick_yesterday,
                    lang=self._lang).grid(row=0, column=1, sticky="ew", padx=2)
        TextButton(quick_row, text=tomorrow_text,
                    command=self._pick_tomorrow,
                    lang=self._lang).grid(row=0, column=2, sticky="ew", padx=2)
        # Divider
        Divider(self._content).pack(fill="x", pady=8)
        # Action buttons
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        cancel = GhostButton(
            btn_row, text="لغو" if self._lang == "fa" else "Cancel",
            command=lambda: self.close(None),
            lang=self._lang, height=42,
        )
        confirm = GoldButton(
            btn_row, text="تأیید" if self._lang == "fa" else "Confirm",
            command=self._confirm,
            lang=self._lang, height=42,
        )
        if rtl:
            confirm.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            confirm.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    # ------------------------------------------------------------------
    def _on_select(self, iso: str) -> None:
        self._selected = iso

    def _pick_today(self) -> None:
        iso = date.today().isoformat()
        self._calendar.select_date(iso)
        self._selected = iso

    def _pick_yesterday(self) -> None:
        iso = (date.today() - timedelta(days=1)).isoformat()
        self._calendar.select_date(iso)
        self._selected = iso

    def _pick_tomorrow(self) -> None:
        iso = (date.today() + timedelta(days=1)).isoformat()
        self._calendar.select_date(iso)
        self._selected = iso

    def _confirm(self) -> None:
        sel = getattr(self, "_selected", None) or self._initial
        self.close(sel)

    # ------------------------------------------------------------------
    # Class method convenience API
    # ------------------------------------------------------------------
    @classmethod
    def ask(
        cls,
        parent: Any,
        initial: Optional[str] = None,
        calendar_system: str = "jalali",
        lang: str = "fa",
    ) -> Optional[str]:
        """Open a date picker and return the selected ISO date or None.

        This is a non-blocking helper — it constructs the picker and
        returns immediately.  Use the ``on_result`` callback to receive
        the result.
        """
        try:
            picker = cls(parent, initial=initial,
                          calendar_system=calendar_system, lang=lang)
            return picker  # type: ignore[return-value]
        except Exception:
            return None


def _self_test() -> int:
    classes = [DatePicker]
    print(f"Date picker module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
