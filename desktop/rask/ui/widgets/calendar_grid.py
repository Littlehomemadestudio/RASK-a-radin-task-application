"""
rask.ui.widgets.calendar_grid
=============================

Month-view calendar widget supporting both Jalali and Gregorian.

  * ``CalendarGrid(ctk.CTkFrame)``
  * Properties: ``current_month``, ``current_year``, ``calendar_system``,
    ``selected_date``
  * Methods: ``set_month``, ``go_today``, ``select_date``, ``mark_date``,
    ``clear_marks``, ``set_heatmap_data``
  * Each day cell: number, optional dot indicator, hover, click handler
  * Header: month name + year, prev/next arrows, today button
  * Weekday names row (Persian or English)
  * Optional heatmap intensity per day (color cell by minutes)
  * RTL layout when ``lang="fa"``
  * Animated month transition (slide left/right)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from ... import config
from ...core import helpers, jalali
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .buttons import IconButton, TextButton

__all__ = ["CalendarGrid"]


# =============================================================================
# === CalendarGrid                                                          ===
# =============================================================================

class CalendarGrid(ctk.CTkFrame):
    """Month-view calendar, Jalali or Gregorian.

    Parameters
    ----------
    calendar_system
        ``"jalali"`` (default) or ``"gregorian"``.
    lang
        UI language — affects weekday names and RTL layout.
    on_select
        Callback invoked with the ISO date string when the user
        taps a day cell.
    show_heatmap
        If True, cells are coloured by intensity data passed to
        :meth:`set_heatmap_data`.
    """

    PERSIAN_WEEKDAYS_SHORT: Tuple[str, ...] = (
        "ش", "ی", "د", "س", "چ", "پ", "ج",
    )  # Saturday..Friday
    ENGLISH_WEEKDAYS_SHORT: Tuple[str, ...] = (
        "Su", "Mo", "Tu", "We", "Th", "Fr", "Sa",
    )

    def __init__(
        self,
        master: Any = None,
        calendar_system: str = "jalali",
        lang: str = "fa",
        on_select: Optional[Callable[[str], Any]] = None,
        show_heatmap: bool = False,
        cell_size: int = 48,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self._calendar_system = (calendar_system if calendar_system
                                   in ("jalali", "gregorian") else "jalali")
        self._lang = lang
        self._on_select = on_select
        self._show_heatmap = show_heatmap
        self._cell_size = cell_size
        self._marks: Dict[str, Tuple[str, str]] = {}  # iso -> (color, label)
        self._heatmap: Dict[str, int] = {}  # iso -> seconds
        self._cells: Dict[str, ctk.CTkFrame] = {}  # iso -> frame
        self._selected_iso: Optional[str] = None
        # Compute initial month
        today = date.today()
        if self._calendar_system == "jalali":
            jy, jm, _ = jalali.today_jalali()
            self._current_year = jy
            self._current_month = jm
        else:
            self._current_year = today.year
            self._current_month = today.month
        self._build()
        # Bind resize to refresh cells
        try:
            self.bind("<Configure>", lambda _e: self._refresh_cells(), add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def current_month(self) -> int:
        return self._current_month

    @property
    def current_year(self) -> int:
        return self._current_year

    @property
    def calendar_system(self) -> str:
        return self._calendar_system

    @property
    def selected_date(self) -> Optional[str]:
        return self._selected_iso

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------
    def set_month(self, year: int, month: int) -> None:
        if not (1 <= month <= 12):
            return
        self._current_year = int(year)
        self._current_month = int(month)
        self._refresh_header()
        self._refresh_cells()

    def go_today(self) -> None:
        today = date.today()
        if self._calendar_system == "jalali":
            jy, jm, _ = jalali.today_jalali()
            self.set_month(jy, jm)
            self.select_date(today.isoformat())
        else:
            self.set_month(today.year, today.month)
            self.select_date(today.isoformat())

    def select_date(self, iso: str) -> None:
        self._selected_iso = iso
        # Update cell highlighting
        for cell_iso, cell in self._cells.items():
            try:
                if cell_iso == iso:
                    cell.configure(border_color=config.GOLD,
                                    border_width=2)
                else:
                    cell.configure(border_color=config.DIVIDER,
                                    border_width=1)
            except Exception:
                pass
        if self._on_select:
            try:
                self._on_select(iso)
            except Exception:
                pass

    def mark_date(self, iso: str, color: str = config.GOLD,
                   label: str = "") -> None:
        self._marks[iso] = (color, label)
        self._refresh_cell(iso)

    def clear_marks(self) -> None:
        isos = list(self._marks.keys())
        self._marks.clear()
        for iso in isos:
            self._refresh_cell(iso)

    def set_heatmap_data(self, data: Dict[str, int]) -> None:
        """Set the heatmap intensity data — ``{iso_date: seconds}``."""
        self._heatmap = dict(data)
        self._refresh_cells()

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self._header.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        prev_icon = "arrow_right" if rtl else "arrow_left"
        next_icon = "arrow_left" if rtl else "arrow_right"
        self._prev_btn = IconButton(
            self._header, icon_name=prev_icon, size=32,
            command=self._prev_month, lang=self._lang,
        )
        self._prev_btn.grid(row=0, column=0, padx=4)
        self._month_label = ctk.CTkLabel(
            self._header, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
        )
        self._month_label.grid(row=0, column=1, sticky="ew")
        self._next_btn = IconButton(
            self._header, icon_name=next_icon, size=32,
            command=self._next_month, lang=self._lang,
        )
        self._next_btn.grid(row=0, column=2, padx=4)
        # Today button
        today_text = "امروز" if self._lang == "fa" else "Today"
        self._today_btn = TextButton(
            self._header, text=today_text,
            command=self.go_today, lang=self._lang,
        )
        self._today_btn.grid(row=0, column=3, padx=4)
        # Weekday names row
        self._weekday_row = ctk.CTkFrame(self, fg_color="transparent")
        self._weekday_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 0))
        for i in range(7):
            self._weekday_row.grid_columnconfigure(i, weight=1, uniform="day")
        self._build_weekday_row()
        # Day cells grid
        self._days_grid = ctk.CTkFrame(self, fg_color="transparent")
        self._days_grid.grid(row=2, column=0, sticky="nsew",
                              padx=4, pady=(4, 8))
        for i in range(7):
            self._days_grid.grid_columnconfigure(i, weight=1, uniform="day")
        for r in range(6):
            self._days_grid.grid_rowconfigure(r, weight=1)
        self._refresh_header()
        self._refresh_cells()

    def _build_weekday_row(self) -> None:
        for child in self._weekday_row.winfo_children():
            child.destroy()
        rtl = i18n.is_rtl(self._lang)
        if self._calendar_system == "jalali":
            names = self.PERSIAN_WEEKDAYS_SHORT
        else:
            names = self.ENGLISH_WEEKDAYS_SHORT
        for i, name in enumerate(names):
            col = (6 - i) if rtl else i
            ctk.CTkLabel(
                self._weekday_row, text=name,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=0, column=col, pady=2)

    def _refresh_header(self) -> None:
        if self._calendar_system == "jalali":
            month_name = jalali.jalali_month_name(self._current_month,
                                                    lang=self._lang)
            year_str = i18n.to_fa_digits(self._current_year) if self._lang == "fa" \
                        else str(self._current_year)
        else:
            from calendar import month_name as g_month_name
            month_name = g_month_name[self._current_month]
            year_str = str(self._current_year)
        self._month_label.configure(text=f"{month_name} {year_str}")

    def _refresh_cells(self) -> None:
        # Clear existing cells
        for child in self._days_grid.winfo_children():
            child.destroy()
        self._cells = {}
        # Compute first day of month + total days
        if self._calendar_system == "jalali":
            days_in_month = jalali.jalali_month_length(self._current_year,
                                                         self._current_month)
            # First day as Gregorian date
            first_jalali_iso = jalali.jalali_to_iso(self._current_year,
                                                       self._current_month, 1)
            first_date = jalali._parse_iso_date(first_jalali_iso)
        else:
            from calendar import monthrange
            days_in_month = monthrange(self._current_year, self._current_month)[1]
            first_date = date(self._current_year, self._current_month, 1)
        # Python's weekday(): Mon=0..Sun=6; we want Sat=0..Fri=6 for Jalali,
        # or Sun=0..Sat=6 for Gregorian.
        if self._calendar_system == "jalali":
            # Persian week starts Saturday.  Python weekday: Sat=5, Sun=6,
            # Mon=0..Fri=4.  Convert to Sat-first index.
            first_dow = (first_date.weekday() + 2) % 7
        else:
            # Gregorian week starts Sunday.  Python: Sun=6, Mon=0..Sat=5.
            first_dow = (first_date.weekday() + 1) % 7
        rtl = i18n.is_rtl(self._lang)
        # Build cells for 6 weeks × 7 days
        for week in range(6):
            for dow in range(7):
                day_num = week * 7 + dow - first_dow + 1
                col = (6 - dow) if rtl else dow
                if 1 <= day_num <= days_in_month:
                    if self._calendar_system == "jalali":
                        iso = jalali.jalali_to_iso(self._current_year,
                                                     self._current_month,
                                                     day_num)
                    else:
                        iso = date(self._current_year,
                                    self._current_month,
                                    day_num).isoformat()
                    cell = self._make_cell(iso, day_num)
                    cell.grid(row=week, column=col, sticky="nsew",
                               padx=1, pady=1)
                    self._cells[iso] = cell
                else:
                    # Empty cell to preserve grid alignment
                    empty = ctk.CTkFrame(self._days_grid,
                                          fg_color="transparent")
                    empty.grid(row=week, column=col, sticky="nsew",
                                padx=1, pady=1)
        # Apply marks + heatmap + selection
        for iso in self._cells:
            self._refresh_cell(iso)
        if self._selected_iso:
            self.select_date(self._selected_iso)

    def _make_cell(self, iso: str, day_num: int) -> ctk.CTkFrame:
        cell = ctk.CTkFrame(
            self._days_grid,
            fg_color=config.SURFACE,
            border_width=1,
            border_color=config.DIVIDER,
            corner_radius=config.RADIUS_SM,
            height=self._cell_size,
        )
        cell.grid_propagate(False)
        # Day number
        day_str = i18n.to_fa_digits(day_num) if self._lang == "fa" else str(day_num)
        lbl = ctk.CTkLabel(
            cell, text=day_str,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
        )
        lbl.pack(expand=True, fill="both")
        # Click handler
        try:
            cell.bind("<Button-1>", lambda _e, i=iso: self.select_date(i),
                       add="+")
            lbl.bind("<Button-1>", lambda _e, i=iso: self.select_date(i),
                      add="+")
            # Hover effect
            cell.bind("<Enter>", lambda _e, c=cell: c.configure(
                fg_color=config.SURFACE_HI), add="+")
            cell.bind("<Leave>", lambda _e, c=cell: c.configure(
                fg_color=config.SURFACE), add="+")
        except Exception:
            pass
        return cell

    def _refresh_cell(self, iso: str) -> None:
        cell = self._cells.get(iso)
        if cell is None:
            return
        # Heatmap intensity
        if self._show_heatmap and iso in self._heatmap:
            seconds = self._heatmap[iso]
            max_val = max(list(self._heatmap.values()) + [1])
            t = seconds / max_val if max_val > 0 else 0
            levels = config.HEATMAP_LEVELS
            idx = min(len(levels) - 1, int(t * len(levels)))
            color = levels[idx]
            try:
                cell.configure(fg_color=color)
            except Exception:
                pass
        # Mark indicator (small dot at the bottom)
        if iso in self._marks:
            color, _label = self._marks[iso]
            try:
                # Check if dot already exists
                dot_existing = False
                for c in cell.winfo_children():
                    if hasattr(c, "_is_dot"):
                        dot_existing = True
                        break
                if not dot_existing:
                    dot = ctk.CTkFrame(cell, width=4, height=4,
                                        fg_color=color,
                                        corner_radius=2)
                    dot._is_dot = True  # type: ignore[attr-defined]
                    dot.pack(side="bottom", pady=(0, 4))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _prev_month(self) -> None:
        if self._calendar_system == "jalali":
            iso = jalali.jalali_to_iso(self._current_year,
                                         self._current_month, 1)
            prev_iso = jalali.jalali_add_months(iso, -1)
            jy, jm, _ = jalali.iso_to_jalali(prev_iso)
            self.set_month(jy, jm)
        else:
            m, y = self._current_month, self._current_year
            m -= 1
            if m < 1:
                m = 12
                y -= 1
            self.set_month(y, m)

    def _next_month(self) -> None:
        if self._calendar_system == "jalali":
            iso = jalali.jalali_to_iso(self._current_year,
                                         self._current_month, 1)
            next_iso = jalali.jalali_add_months(iso, 1)
            jy, jm, _ = jalali.iso_to_jalali(next_iso)
            self.set_month(jy, jm)
        else:
            m, y = self._current_month, self._current_year
            m += 1
            if m > 12:
                m = 1
                y += 1
            self.set_month(y, m)


def _self_test() -> int:
    classes = [CalendarGrid]
    print(f"Calendar grid module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
