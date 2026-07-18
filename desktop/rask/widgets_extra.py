"""widgets_extra.py — Additional widgets for Rask.

Extends widgets.py with more specialized components:
  - ColorPicker       — color picker dialog with preset swatches
  - NumberStepper     — +/- number input
  - DatePicker        — calendar-style date picker
  - TimePicker        — hour/minute picker
  - Dropdown          — combobox with custom styling
  - TabView           — multi-tab view container
  - CollapsibleSection — expandable section
  - SheetModal        — slide-up bottom sheet (alternative to Modal)
  - ConfirmDialog     — yes/no confirmation dialog
  - AlertDialog       — info alert dialog
  - ProgressDialog    — modal with progress bar
  - MultiSelectChip   — multi-select chip group
  - ToggleGroup       — radio-button-like group
  - RatingStars       — star rating input
  - ProgressBar       — circular progress with label
  - ListItem          — generic list item with icon + text + chevron
  - EmptyIllustration — larger empty state with custom drawing

These complement the core widgets.py and use the same gold-on-dark theme.
"""
from __future__ import annotations
import datetime as _dt
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from . import config
from . import icons
from .i18n import t, to_fa_digits
from .widgets import (
    GoldButton, IconButton, Chip, Card, Field, TextArea, Switch, Slider,
    Modal, Avatar, get_font, rounded_rect, gradient_rect, glow_oval,
    section_header,
)


# =====================================================================
# === COLOR PICKER ===
# =====================================================================
PRESET_COLORS = [
    "#D4AF37", "#C9A84C", "#7B9BC9", "#7BC97B", "#D49ABF",
    "#E8B85A", "#9A9A9F", "#9B7BC9", "#C97B9B", "#7BC9C9",
    "#C9B07B", "#9BC97B", "#D4625A", "#E8E8E8", "#5C5C60",
    "#FF6B6B", "#4ECDC4", "#FFE66D", "#A8E6CF", "#FF8B94",
    "#C9A84C", "#B8E0D2", "#D6E4E5", "#F6F2D4", "#E8B4BC",
    "#955251", "#B5651D", "#8B4513", "#DAA520", "#FFA500",
]


class ColorPicker(Modal):
    """A color picker modal with preset swatches."""

    def __init__(self, root, lang: str = "fa",
                 on_pick: Optional[Callable[[str], None]] = None,
                 initial_color: Optional[str] = None):
        self._lang = lang
        self._on_pick = on_pick
        self._selected = initial_color or config.GOLD
        super().__init__(root, title=t("categoryColor", lang), lang=lang, height=480)
        self._build()

    def _build(self):
        lang = self._lang
        # Preset swatches grid (6 columns)
        grid = tk.Frame(self.content, bg=config.MATTE_BLACK)
        grid.pack(fill="x", pady=(0, 16))
        for i, color in enumerate(PRESET_COLORS):
            cell = tk.Canvas(grid, width=44, height=44, bg=config.MATTE_BLACK,
                              highlightthickness=0, bd=0)
            cell.grid(row=i // 6, column=i % 6, padx=4, pady=4)
            # Filled circle
            cell.create_oval(4, 4, 40, 40, fill=color, outline="")
            # Selected indicator
            if color == self._selected:
                cell.create_oval(14, 14, 30, 30, fill=config.MATTE_BLACK, outline="")
                cell.create_text(22, 22, text="✓", fill=color,
                                  font=get_font(14, "bold"))
            # Click handler
            cell.bind("<Button-1>", lambda e, c=color: self._on_select(c))
            cell.config(cursor="hand2")
        # Custom hex input
        tk.Label(self.content, text="Hex:", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(12)).pack(anchor="w", pady=(0, 4))
        self._hex_entry = Field(self.content, placeholder="#D4AF37", lang=lang)
        self._hex_entry.pack(fill="x", pady=(0, 8))
        if self._selected:
            self._hex_entry.set(self._selected)
        # Save button
        GoldButton(self.content, text=t("save", lang),
                    command=self._on_save, kind="gold",
                    full_width=True).pack(fill="x")

    def _on_select(self, color: str):
        self._selected = color
        self._hex_entry.set(color)
        # Re-render the grid
        for child in self.content.winfo_children():
            child.destroy()
        self._build()

    def _on_save(self):
        hex_val = self._hex_entry.get()
        if hex_val and hex_val.startswith("#") and len(hex_val) == 7:
            try:
                # Validate
                int(hex_val[1:], 16)
                self._selected = hex_val
            except ValueError:
                pass
        if self._on_pick:
            self._on_pick(self._selected)
        self.close()


# =====================================================================
# === NUMBER STEPPER ===
# =====================================================================
class NumberStepper(tk.Frame):
    """A number input with +/- buttons."""
    def __init__(self, parent, value: int = 0, min_val: int = 0,
                 max_val: int = 999, step: int = 1,
                 command: Optional[Callable[[int], None]] = None,
                 width: int = 120, **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        self._value = value
        self._min = min_val
        self._max = max_val
        self._step = step
        self._command = command
        # Minus button
        IconButton(self, "minus", command=self._dec, size=36,
                    color=config.TEXT, hover_color=config.GOLD).pack(side="left")
        # Value display
        self._var = tk.StringVar(value=str(value))
        self._label = tk.Label(self, textvariable=self._var, bg=config.SURFACE,
                                fg=config.GOLD, font=get_font(16, "bold"),
                                width=4)
        self._label.pack(side="left", fill="x", expand=True, padx=4, ipady=4)
        # Plus button
        IconButton(self, "plus", command=self._inc, size=36,
                    color=config.TEXT, hover_color=config.GOLD).pack(side="right")

    def _inc(self):
        new_val = min(self._max, self._value + self._step)
        if new_val != self._value:
            self._value = new_val
            self._var.set(str(self._value))
            if self._command:
                self._command(self._value)

    def _dec(self):
        new_val = max(self._min, self._value - self._step)
        if new_val != self._value:
            self._value = new_val
            self._var.set(str(self._value))
            if self._command:
                self._command(self._value)

    def get(self) -> int:
        return self._value

    def set(self, value: int):
        self._value = max(self._min, min(self._max, value))
        self._var.set(str(self._value))


# =====================================================================
# === DATE PICKER ===
# =====================================================================
class DatePicker(Modal):
    """A simple calendar-style date picker."""

    def __init__(self, root, lang: str = "fa",
                 on_pick: Optional[Callable[[str], None]] = None,
                 initial_date: Optional[str] = None):
        self._lang = lang
        self._on_pick = on_pick
        if initial_date:
            try:
                self._current = _dt.date.fromisoformat(initial_date)
            except ValueError:
                self._current = _dt.date.today()
        else:
            self._current = _dt.date.today()
        self._view_date = self._current.replace(day=1)
        super().__init__(root, title=t("activityDate", lang), lang=lang, height=480)
        self._build()

    def _build(self):
        lang = self._lang
        # Header: month/year + nav
        header = tk.Frame(self.content, bg=config.MATTE_BLACK)
        header.pack(fill="x", pady=(0, 8))
        IconButton(header, "chevron-left", command=self._prev_month, size=32,
                    color=config.GOLD, hover_color=config.GOLD_BRIGHT).pack(side="left")
        from .date_utils import gregorian_to_jalali, fmt_date
        jy, jm, jd = gregorian_to_jalali(self._view_date.year, self._view_date.month, self._view_date.day)
        from .i18n import t
        month_name = t(f"jMonth{jm}", lang) if lang == "fa" else self._view_date.strftime("%B")
        year_str = to_fa_digits(jy) if lang == "fa" else str(jy)
        tk.Label(header, text=f"{month_name} {year_str}", bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(16, "bold")).pack(side="left", fill="x", expand=True)
        IconButton(header, "chevron-right", command=self._next_month, size=32,
                    color=config.GOLD, hover_color=config.GOLD_BRIGHT).pack(side="right")
        # Weekday header (Sat, Sun, Mon, ...)
        wd_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        wd_frame.pack(fill="x", pady=(0, 4))
        # Persian week starts on Saturday
        wd_keys = ["weekdaySatShort", "weekdaySunShort", "weekdayMonShort",
                    "weekdayTueShort", "weekdayWedShort", "weekdayThuShort", "weekdayFriShort"]
        for key in wd_keys:
            tk.Label(wd_frame, text=t(key, lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_DIM, font=get_font(10), width=4).pack(side="left", fill="x", expand=True)
        # Calendar grid
        self._grid_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._grid_frame.pack(fill="x")
        self._render_grid()

    def _render_grid(self):
        for child in self._grid_frame.winfo_children():
            child.destroy()
        # Find Saturday of first week
        first = self._view_date.replace(day=1)
        py_wd = first.weekday()  # Mon=0, Sun=6
        offset = (py_wd + 2) % 7  # Sat=0, Sun=1, Mon=2, ...
        # Last day of month
        if self._view_date.month == 12:
            last_day = 31
        else:
            last_day = (self._view_date.replace(month=self._view_date.month + 1, day=1)
                        - _dt.timedelta(days=1)).day
        row, col = 0, offset
        for day in range(1, last_day + 1):
            is_today = (self._view_date.year == _dt.date.today().year and
                        self._view_date.month == _dt.date.today().month and
                        day == _dt.date.today().day)
            is_selected = (self._view_date.year == self._current.year and
                           self._view_date.month == self._current.month and
                           day == self._current.day)
            bg = config.GOLD if is_selected else (config.SURFACE if is_today else config.CHARCOAL)
            fg = config.MATTE_BLACK if is_selected else config.TEXT
            day_str = to_fa_digits(day) if self._lang == "fa" else str(day)
            cell = tk.Button(self._grid_frame, text=day_str, bg=bg, fg=fg,
                              font=get_font(11, "bold" if is_selected else "normal"),
                              relief="flat", bd=0, cursor="hand2",
                              width=4, height=2,
                              command=lambda _d=day: self._on_pick_day(_d))
            cell.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            col += 1
            if col >= 7:
                col = 0
                row += 1

    def _prev_month(self):
        if self._view_date.month == 1:
            self._view_date = self._view_date.replace(year=self._view_date.year - 1, month=12)
        else:
            self._view_date = self._view_date.replace(month=self._view_date.month - 1)
        self._build()  # rebuild header
        # Re-render grid (after rebuilding content)
        for child in self.content.winfo_children():
            child.destroy()
        self._build()

    def _next_month(self):
        if self._view_date.month == 12:
            self._view_date = self._view_date.replace(year=self._view_date.year + 1, month=1)
        else:
            self._view_date = self._view_date.replace(month=self._view_date.month + 1)
        for child in self.content.winfo_children():
            child.destroy()
        self._build()

    def _on_pick_day(self, day: int):
        self._current = self._view_date.replace(day=day)
        if self._on_pick:
            self._on_pick(self._current.isoformat())
        self.close()


# =====================================================================
# === DROPDOWN (custom-styled OptionMenu) ===
# =====================================================================
class Dropdown(tk.Frame):
    """A dropdown menu with custom styling."""
    def __init__(self, parent, options: list[tuple[str, any]],
                 value: any = None, command: Optional[Callable[[any], None]] = None,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.SURFACE, **kwargs)
        self._options = options  # list of (label, value)
        self._command = command
        self._lang = lang
        self._var = tk.StringVar()
        # Find current label
        current_label = ""
        for label, val in options:
            if val == value:
                current_label = label
                break
        if not current_label and options:
            current_label = options[0][0]
            value = options[0][1]
        self._var.set(current_label)
        self._value = value
        # Use a Button + Toplevel menu (simpler than OptionMenu for custom styling)
        self._button = tk.Button(self, textvariable=self._var,
                                  bg=config.SURFACE, fg=config.TEXT,
                                  font=get_font(13), relief="flat", bd=0,
                                  cursor="hand2", anchor="w",
                                  activebackground=config.SURFACE_HI,
                                  activeforeground=config.GOLD,
                                  command=self._show_menu)
        self._button.pack(fill="x", expand=True, padx=12, pady=10)
        # Chevron
        chevron = tk.Label(self, text="▾", bg=config.SURFACE, fg=config.GOLD,
                            font=get_font(10))
        chevron.place(relx=1.0, rely=0.5, x=-12, anchor="e")

    def _show_menu(self):
        menu = tk.Menu(self, bg=config.SURFACE, fg=config.TEXT,
                        activebackground=config.GOLD, activeforeground=config.MATTE_BLACK,
                        font=get_font(12), tearoff=0, bd=0)
        for label, val in self._options:
            menu.add_command(label=label, command=lambda _l=label, _v=val: self._on_select(_l, _v))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()

    def _on_select(self, label: str, value: any):
        self._var.set(label)
        self._value = value
        if self._command:
            self._command(value)

    def get(self):
        return self._value

    def set(self, value: any):
        for label, val in self._options:
            if val == value:
                self._var.set(label)
                self._value = value
                return


# =====================================================================
# === TAB VIEW ===
# =====================================================================
class TabView(tk.Frame):
    """A multi-tab view container with horizontal tab bar."""
    def __init__(self, parent, tabs: list[tuple[str, tk.Frame]],
                 active: int = 0, lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._lang = lang
        self._tabs = tabs  # list of (title, content_frame)
        self._active = active
        # Tab bar
        bar = tk.Frame(self, bg=config.MATTE_BLACK, height=40)
        bar.pack(fill="x")
        self._tab_buttons: list[tk.Canvas] = []
        for i, (title, _) in enumerate(tabs):
            tab_btn = tk.Canvas(bar, height=40, bg=config.MATTE_BLACK,
                                 highlightthickness=0, bd=0)
            tab_btn.pack(side="left", fill="x", expand=True)
            tab_btn._title = title
            tab_btn._index = i
            self._tab_buttons.append(tab_btn)
            tab_btn.bind("<ButtonPress-1>", lambda e, _i=i: self.switch_to(_i))
            tab_btn.bind("<Configure>", lambda e, _b=tab_btn: self._draw_tab(_b))
        # Content area
        self._content_frame = tk.Frame(self, bg=config.MATTE_BLACK)
        self._content_frame.pack(fill="both", expand=True)
        for i, (_, frame) in enumerate(tabs):
            frame.pack(in_=self._content_frame, fill="both", expand=True)
            if i != active:
                frame.pack_forget()
        self._draw_all()

    def switch_to(self, idx: int):
        if idx < 0 or idx >= len(self._tabs):
            return
        self._active = idx
        # Show/hide frames
        for i, (_, frame) in enumerate(self._tabs):
            if i == idx:
                frame.pack(in_=self._content_frame, fill="both", expand=True)
            else:
                frame.pack_forget()
        self._draw_all()

    def _draw_all(self):
        for btn in self._tab_buttons:
            self._draw_tab(btn)

    def _draw_tab(self, btn):
        btn.delete("all")
        w = btn.winfo_width() if btn.winfo_width() > 10 else 100
        h = 40
        is_active = btn._index == self._active
        color = config.GOLD if is_active else config.TEXT_DIM
        # Title text
        btn.create_text(w / 2, h / 2, text=btn._title, fill=color,
                         font=get_font(12, "bold" if is_active else "normal"))
        # Underline for active
        if is_active:
            btn.create_rectangle(0, h - 2, w, h, fill=config.GOLD, outline="")


# =====================================================================
# === COLLAPSIBLE SECTION ===
# =====================================================================
class CollapsibleSection(tk.Frame):
    """A section that can be expanded/collapsed."""
    def __init__(self, parent, title: str, expanded: bool = True,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._title = title
        self._expanded = expanded
        self._lang = lang
        # Header
        header = tk.Frame(self, bg=config.MATTE_BLACK)
        header.pack(fill="x")
        self._header_btn = tk.Canvas(header, height=32, bg=config.MATTE_BLACK,
                                       highlightthickness=0, bd=0)
        self._header_btn.pack(fill="x", side="left")
        self._header_btn.bind("<Button-1>", lambda e: self.toggle())
        self._header_btn.bind("<Configure>", lambda e: self._draw_header())
        # Content
        self.content = tk.Frame(self, bg=config.MATTE_BLACK)
        if expanded:
            self.content.pack(fill="x")
        self._draw_header()

    def _draw_header(self):
        self._header_btn.delete("all")
        w = self._header_btn.winfo_width() if self._header_btn.winfo_width() > 10 else 200
        h = 32
        # Chevron
        chevron = "▾" if self._expanded else "▸"
        self._header_btn.create_text(8, h / 2, text=chevron, fill=config.GOLD,
                                       font=get_font(12), anchor="w")
        # Title
        self._header_btn.create_text(28, h / 2, text=self._title, fill=config.TEXT,
                                       font=get_font(13, "bold"), anchor="w")

    def toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x")
        else:
            self.content.pack_forget()
        self._draw_header()


# =====================================================================
# === CONFIRM DIALOG ===
# =====================================================================
class ConfirmDialog(Modal):
    """A yes/no confirmation dialog."""
    def __init__(self, root, title: str, message: str,
                 lang: str = "fa",
                 on_confirm: Optional[Callable[[], None]] = None,
                 on_cancel: Optional[Callable[[], None]] = None,
                 confirm_label: Optional[str] = None,
                 cancel_label: Optional[str] = None,
                 danger: bool = False):
        self._lang = lang
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        super().__init__(root, title=title, lang=lang, height=320)
        self._danger = danger
        self._message = message
        self._confirm_label = confirm_label or t("yes", lang)
        self._cancel_label = cancel_label or t("no", lang)
        self._build()

    def _build(self):
        lang = self._lang
        # Message
        tk.Label(self.content, text=self._message, bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=get_font(14), wraplength=400,
                 justify="center").pack(pady=(24, 32))
        # Buttons
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=self._cancel_label, command=self._on_cancel_click,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=self._confirm_label, command=self._on_confirm_click,
                    kind="danger" if self._danger else "gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _on_confirm_click(self):
        if self._on_confirm:
            self._on_confirm()
        self.close()

    def _on_cancel_click(self):
        if self._on_cancel:
            self._on_cancel()
        self.close()


# =====================================================================
# === ALERT DIALOG ===
# =====================================================================
class AlertDialog(Modal):
    """An info alert dialog with a single OK button."""
    def __init__(self, root, title: str, message: str,
                 lang: str = "fa", on_close: Optional[Callable[[], None]] = None):
        self._lang = lang
        self._message = message
        self._on_close = on_close
        super().__init__(root, title=title, lang=lang, height=280)
        self._build()

    def _build(self):
        lang = self._lang
        tk.Label(self.content, text=self._message, bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=get_font(14), wraplength=400,
                 justify="center").pack(pady=(24, 32))
        GoldButton(self.content, text=t("ok", lang), command=self._on_ok,
                    kind="gold", full_width=True).pack(fill="x", side="bottom")

    def _on_ok(self):
        if self._on_close:
            self._on_close()
        self.close()


# =====================================================================
# === PROGRESS DIALOG ===
# =====================================================================
class ProgressDialog(Modal):
    """A modal with a progress bar and status message."""
    def __init__(self, root, title: str, message: str = "",
                 lang: str = "fa", indeterminate: bool = True):
        self._lang = lang
        self._message = message
        self._indeterminate = indeterminate
        self._progress = 0.0
        super().__init__(root, title=title, lang=lang, height=240)
        self._build()

    def _build(self):
        # Message
        self._msg_var = tk.StringVar(value=self._message)
        tk.Label(self.content, textvariable=self._msg_var, bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=get_font(13), wraplength=400,
                 justify="center").pack(pady=(24, 24))
        # Progress bar
        self._bar = tk.Canvas(self.content, width=400, height=8,
                                bg=config.SURFACE, highlightthickness=0, bd=0)
        self._bar.pack(fill="x", padx=24, pady=(0, 24))
        self._draw_bar()

    def _draw_bar(self):
        self._bar.delete("all")
        w = 400
        h = 8
        # Track
        rounded_rect(self._bar, 0, 0, w, h, h / 2,
                     fill=config.SURFACE_HI, outline="")
        # Fill
        fill_w = w * self._progress
        if fill_w > 0:
            rounded_rect(self._bar, 0, 0, fill_w, h, h / 2,
                         fill=config.GOLD, outline="")

    def set_progress(self, progress: float, message: Optional[str] = None):
        self._progress = max(0.0, min(1.0, float(progress)))
        if message is not None:
            self._msg_var.set(message)
        self._draw_bar()

    def set_message(self, message: str):
        self._msg_var.set(message)


# =====================================================================
# === MULTI-SELECT CHIPS ===
# =====================================================================
class MultiSelectChips(tk.Frame):
    """A group of selectable chips (multi-select)."""
    def __init__(self, parent, options: list[tuple[str, any]],
                 selected: Optional[list[any]] = None,
                 command: Optional[Callable[[list[any]], None]] = None,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._options = options
        self._selected = set(selected or [])
        self._command = command
        self._lang = lang
        self._chips: list[tuple[Chip, any]] = []
        self._render()

    def _render(self):
        for child in self.winfo_children():
            child.destroy()
        self._chips = []
        for label, value in self._options:
            chip = Chip(self, text=label, selected=(value in self._selected),
                         command=lambda _v=value: self._toggle(_v), lang=self._lang)
            chip.pack(side="left", padx=(0, 4))
            self._chips.append((chip, value))

    def _toggle(self, value: any):
        if value in self._selected:
            self._selected.remove(value)
        else:
            self._selected.add(value)
        self._render()
        if self._command:
            self._command(list(self._selected))

    def get(self) -> list[any]:
        return list(self._selected)

    def set(self, values: list[any]):
        self._selected = set(values)
        self._render()


# =====================================================================
# === TOGGLE GROUP (radio-button-like) ===
# =====================================================================
class ToggleGroup(tk.Frame):
    """A group of mutually-exclusive chips (radio-button-like)."""
    def __init__(self, parent, options: list[tuple[str, any]],
                 value: any = None, command: Optional[Callable[[any], None]] = None,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.MATTE_BLACK, **kwargs)
        self._options = options
        self._value = value if value is not None else (options[0][1] if options else None)
        self._command = command
        self._lang = lang
        self._chips: list[tuple[Chip, any]] = []
        self._render()

    def _render(self):
        for child in self.winfo_children():
            child.destroy()
        self._chips = []
        for label, value in self._options:
            chip = Chip(self, text=label, selected=(value == self._value),
                         command=lambda _v=value: self._select(_v), lang=self._lang)
            chip.pack(side="left", padx=(0, 4))
            self._chips.append((chip, value))

    def _select(self, value: any):
        self._value = value
        self._render()
        if self._command:
            self._command(value)

    def get(self):
        return self._value

    def set(self, value: any):
        self._value = value
        self._render()


# =====================================================================
# === RATING STARS ===
# =====================================================================
class RatingStars(tk.Frame):
    """A star rating input (1-5 stars)."""
    def __init__(self, parent, value: int = 0, max_stars: int = 5,
                 command: Optional[Callable[[int], None]] = None,
                 **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        self._value = value
        self._max = max_stars
        self._command = command
        self._stars: list[tk.Canvas] = []
        for i in range(max_stars):
            star = tk.Canvas(self, width=32, height=32, bg=parent["bg"],
                              highlightthickness=0, bd=0)
            star.pack(side="left", padx=2)
            star._index = i
            self._stars.append(star)
            star.bind("<Button-1>", lambda e, _i=i: self._set(_i + 1))
            star.bind("<Enter>", lambda e, _i=i: self._preview(_i + 1))
            star.bind("<Leave>", lambda e: self._draw())
        self._draw()

    def _draw(self, preview_value: Optional[int] = None):
        v = preview_value if preview_value is not None else self._value
        for i, star in enumerate(self._stars):
            star.delete("all")
            color = config.GOLD if i < v else config.SURFACE_HI
            # Draw a star (simplified as a circle for now)
            star.create_oval(4, 4, 28, 28, fill=color, outline="")
            # Star icon
            from . import icons
            icons.draw_icon(star, 4, 4, 24, "star", color=color,
                             stroke_width=2)

    def _preview(self, value: int):
        self._draw(preview_value=value)
        self.config(cursor="hand2")

    def _set(self, value: int):
        self._value = value
        self._draw()
        if self._command:
            self._command(value)

    def get(self) -> int:
        return self._value

    def set(self, value: int):
        self._value = max(0, min(self._max, value))
        self._draw()


# =====================================================================
# === LIST ITEM (generic) ===
# =====================================================================
class ListItem(tk.Frame):
    """A generic list item with icon, title, subtitle, and optional chevron."""
    def __init__(self, parent, title: str, subtitle: str = "",
                 icon: Optional[str] = None, icon_color: str = config.GOLD,
                 show_chevron: bool = False, lang: str = "fa",
                 on_click: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=config.CHARCOAL, **kwargs)
        self._title = title
        self._subtitle = subtitle
        self._icon = icon
        self._icon_color = icon_color
        self._on_click = on_click
        self._lang = lang
        self._hover = False
        # Layout: [icon] [text] [chevron]
        if icon:
            icon_c = tk.Canvas(self, width=40, height=40, bg=config.CHARCOAL,
                                highlightthickness=0, bd=0)
            icon_c.pack(side="left", padx=(12, 0), pady=10)
            from . import icons
            icons.draw_icon(icon_c, 8, 8, 24, icon, color=icon_color, stroke_width=2)
        # Text
        text_frame = tk.Frame(self, bg=config.CHARCOAL)
        text_frame.pack(side="left", fill="x", expand=True, padx=(12 if icon else 16, 8), pady=10)
        tk.Label(text_frame, text=title, bg=config.CHARCOAL, fg=config.TEXT,
                 font=get_font(14, "bold"), anchor="w").pack(anchor="w")
        if subtitle:
            tk.Label(text_frame, text=subtitle, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(11), anchor="w").pack(anchor="w")
        # Chevron
        if show_chevron:
            tk.Label(self, text="›", bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(20)).pack(side="right", padx=12)
        # Hover / click
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", lambda e: self._handle_click())
        for child in self.winfo_children():
            child.bind("<Button-1>", lambda e: self._handle_click())
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", lambda e: self._handle_click())

    def _on_enter(self, _e):
        self._hover = True
        self.config(bg=config.SURFACE_HI)
        self.config(cursor="hand2")

    def _on_leave(self, _e):
        self._hover = False
        self.config(bg=config.CHARCOAL)
        self.config(cursor="")

    def _handle_click(self):
        if self._on_click:
            try:
                self._on_click()
            except Exception:
                pass


# =====================================================================
# === EMPTY ILLUSTRATION (large empty state with custom drawing) ===
# =====================================================================
class EmptyIllustration(tk.Frame):
    """A larger empty state with custom-drawn illustration."""
    def __init__(self, parent, illustration: str = "clock",
                 title: str = "", subtitle: str = "",
                 lang: str = "fa", action_text: Optional[str] = None,
                 on_action: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        self._lang = lang
        # Illustration canvas
        ill = tk.Canvas(self, width=120, height=120, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        ill.pack(pady=(32, 16))
        # Draw custom illustration
        cx, cy = 60, 60
        # Outer ring
        ill.create_oval(cx - 40, cy - 40, cx + 40, cy + 40,
                         outline=config.SURFACE_HI, width=2)
        # Inner circle
        ill.create_oval(cx - 32, cy - 32, cx + 32, cy + 32,
                         outline=config.GOLD_DIM, width=1)
        # Icon
        from . import icons
        icons.draw_icon(ill, 40, 40, 40, illustration,
                         color=config.TEXT_FAINT, stroke_width=1.5)
        # Title
        if title:
            tk.Label(self, text=title, bg=parent["bg"], fg=config.TEXT_DIM,
                     font=get_font(16, "bold")).pack(pady=(0, 4))
        # Subtitle
        if subtitle:
            tk.Label(self, text=subtitle, bg=parent["bg"], fg=config.TEXT_FAINT,
                     font=get_font(12), wraplength=320).pack(pady=(0, 16))
        # Action button
        if action_text and on_action:
            GoldButton(self, text=action_text, command=on_action,
                        kind="outline", size="sm").pack(pady=(0, 32))


# =====================================================================
# === BADGE WITH DOT (notification indicator) ===
# =====================================================================
class BadgeWithDot(tk.Canvas):
    """A badge with a small notification dot in the corner."""
    def __init__(self, parent, text: str, dot_color: str = config.DANGER,
                 color: str = config.GOLD, size: int = 32, **kwargs):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                          highlightthickness=0, bd=0, **kwargs)
        self._text = text
        self._color = color
        self._dot_color = dot_color
        self._size = size
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        # Background circle
        self.create_oval(0, 0, s, s, fill=self._color, outline="")
        # Text
        self.create_text(s / 2, s / 2, text=self._text,
                          fill=config.MATTE_BLACK, font=get_font(12, "bold"))
        # Dot in top-right corner
        dot_r = s // 6
        self.create_oval(s - 2 * dot_r, 0, s, 2 * dot_r,
                          fill=self._dot_color, outline="")


# =====================================================================
# === PROGRESS RING WITH CENTER TEXT ===
# =====================================================================
class ProgressRingWithText(tk.Canvas):
    """A progress ring with center text (percentage + label)."""
    def __init__(self, parent, size: int = 100, progress: float = 0,
                 color: str = config.GOLD, track_color: str = config.SURFACE_HI,
                 center_text: str = "", sub_text: str = "",
                 line_width: int = 6, **kwargs):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                          highlightthickness=0, bd=0, **kwargs)
        self._size = size
        self._progress = progress
        self._color = color
        self._track_color = track_color
        self._center_text = center_text
        self._sub_text = sub_text
        self._line_width = line_width
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        cx, cy = s / 2, s / 2
        r = s / 2 - self._line_width - 2
        # Track
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=self._track_color, width=self._line_width)
        # Progress
        if self._progress > 0:
            extent = -360 * self._progress
            self.create_arc(cx - r, cy - r, cx + r, cy + r,
                             start=90, extent=extent,
                             style="arc", outline=self._color,
                             width=self._line_width)
        # Center text
        if self._center_text:
            self.create_text(cx, cy - 4, text=self._center_text,
                              fill=config.GOLD, font=get_font(18, "bold"))
        if self._sub_text:
            self.create_text(cx, cy + 14, text=self._sub_text,
                              fill=config.TEXT_DIM, font=get_font(9))

    def set_progress(self, progress: float, center_text: Optional[str] = None,
                      sub_text: Optional[str] = None):
        self._progress = max(0.0, min(1.0, float(progress)))
        if center_text is not None:
            self._center_text = center_text
        if sub_text is not None:
            self._sub_text = sub_text
        self._draw()


# =====================================================================
# === INFO ROW (label + value, with optional divider) ===
# =====================================================================
class InfoRow(tk.Frame):
    """A simple label-value row, optionally with a divider below."""
    def __init__(self, parent, label: str, value: str = "",
                 value_color: str = config.GOLD, show_divider: bool = True,
                 **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        row = tk.Frame(self, bg=parent["bg"])
        row.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(row, text=label, bg=parent["bg"], fg=config.TEXT_DIM,
                 font=get_font(12)).pack(side="left")
        tk.Label(row, text=value, bg=parent["bg"], fg=value_color,
                 font=get_font(12, "bold")).pack(side="right")
        if show_divider:
            tk.Frame(self, bg=config.DIVIDER, height=1).pack(fill="x")


# =====================================================================
# === PILL BUTTON GROUP (segmented control alternative) ===
# =====================================================================
class PillButtonGroup(tk.Frame):
    """A horizontal group of pill buttons (single-select)."""
    def __init__(self, parent, buttons: list[tuple[str, any]],
                 value: any = None, command: Optional[Callable[[any], None]] = None,
                 lang: str = "fa", **kwargs):
        super().__init__(parent, bg=config.SURFACE, **kwargs)
        self._buttons = buttons
        self._value = value if value is not None else (buttons[0][1] if buttons else None)
        self._command = command
        self._lang = lang
        self._render()

    def _render(self):
        for child in self.winfo_children():
            child.destroy()
        for i, (label, val) in enumerate(self._buttons):
            is_active = (val == self._value)
            btn = tk.Canvas(self, height=32, bg=config.SURFACE,
                             highlightthickness=0, bd=0)
            btn.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            btn._label = label
            btn._value = val
            btn._is_active = is_active
            btn.bind("<ButtonPress-1>", lambda e, _v=val: self._select(_v))
            btn.bind("<Configure>", lambda e, _b=btn: self._draw_button(_b))
            self._draw_button(btn)

    def _draw_button(self, btn):
        btn.delete("all")
        w = btn.winfo_width() if btn.winfo_width() > 10 else 60
        h = 32
        bg = config.GOLD if btn._is_active else config.SURFACE
        fg = config.MATTE_BLACK if btn._is_active else config.TEXT_DIM
        # Background
        rounded_rect(btn, 0, 0, w, h, h / 2, fill=bg, outline="")
        # Label
        btn.create_text(w / 2, h / 2, text=btn._label, fill=fg,
                         font=get_font(12, "bold" if btn._is_active else "normal"))

    def _select(self, value: any):
        self._value = value
        self._render()
        if self._command:
            self._command(value)

    def get(self):
        return self._value

    def set(self, value: any):
        self._value = value
        self._render()


# =====================================================================
# === WINDOW DECORATIONS (custom title bar) ===
# =====================================================================
class CustomTitleBar(tk.Frame):
    """A custom title bar with optional window controls (for borderless windows)."""
    def __init__(self, parent, title: str = "Rask",
                 on_close: Optional[Callable] = None,
                 on_minimize: Optional[Callable] = None,
                 on_maximize: Optional[Callable] = None,
                 **kwargs):
        super().__init__(parent, bg=config.CHARCOAL, height=32, **kwargs)
        self._title = title
        self._on_close = on_close
        self._on_minimize = on_minimize
        self._on_maximize = on_maximize
        # Title (centered)
        tk.Label(self, text=title, bg=config.CHARCOAL, fg=config.TEXT,
                 font=get_font(12, "bold")).pack(side="left", padx=12, pady=6)
        # Window controls (right side)
        if on_minimize:
            tk.Button(self, text="—", bg=config.CHARCOAL, fg=config.TEXT,
                       font=get_font(12), relief="flat", bd=0, cursor="hand2",
                       command=on_minimize, activebackground=config.SURFACE_HI,
                       activeforeground=config.GOLD).pack(side="right", padx=4, pady=4)
        if on_maximize:
            tk.Button(self, text="□", bg=config.CHARCOAL, fg=config.TEXT,
                       font=get_font(12), relief="flat", bd=0, cursor="hand2",
                       command=on_maximize, activebackground=config.SURFACE_HI,
                       activeforeground=config.GOLD).pack(side="right", padx=4, pady=4)
        if on_close:
            tk.Button(self, text="✕", bg=config.CHARCOAL, fg=config.TEXT,
                       font=get_font(12), relief="flat", bd=0, cursor="hand2",
                       command=on_close, activebackground=config.DANGER,
                       activeforeground="#FFFFFF").pack(side="right", padx=4, pady=4)


# =====================================================================
# === ICON BADGE (icon with colored background) ===
# =====================================================================
class IconBadge(tk.Canvas):
    """An icon inside a colored circle."""
    def __init__(self, parent, icon: str, size: int = 36,
                 bg_color: str = config.CHARCOAL,
                 icon_color: str = config.GOLD, **kwargs):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                          highlightthickness=0, bd=0, **kwargs)
        self._icon = icon
        self._size = size
        self._bg_color = bg_color
        self._icon_color = icon_color
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        # Background circle
        self.create_oval(0, 0, s, s, fill=self._bg_color, outline="")
        # Icon (centered)
        from . import icons
        icons.draw_icon(self, s * 0.2, s * 0.2, s * 0.6, self._icon,
                         color=self._icon_color, stroke_width=2)


# =====================================================================
# === STATUS INDICATOR (small colored dot + label) ===
# =====================================================================
class StatusIndicator(tk.Frame):
    """A small status indicator: colored dot + label."""
    def __init__(self, parent, label: str, status: str = "info",
                 **kwargs):
        super().__init__(parent, bg=parent["bg"], **kwargs)
        color_map = {
            "info": config.INFO,
            "success": config.SUCCESS,
            "warning": config.WARNING,
            "danger": config.DANGER,
            "neutral": config.TEXT_FAINT,
        }
        color = color_map.get(status, config.TEXT_FAINT)
        # Dot
        dot = tk.Canvas(self, width=10, height=10, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        dot.pack(side="left", padx=(0, 6))
        dot.create_oval(0, 0, 10, 10, fill=color, outline="")
        # Label
        tk.Label(self, text=label, bg=parent["bg"], fg=color,
                 font=get_font(11, "bold")).pack(side="left")


# =====================================================================
# === ANIMATED TYPING INDICATOR ===
# =====================================================================
class TypingIndicator(tk.Canvas):
    """Three animated dots (typing indicator)."""
    def __init__(self, parent, size: int = 24, color: str = config.GOLD,
                 **kwargs):
        super().__init__(parent, width=size * 3, height=size, bg=parent["bg"],
                          highlightthickness=0, bd=0, **kwargs)
        self._size = size
        self._color = color
        self._phase = 0
        self._after_id = None
        self._draw()
        self._animate()

    def _animate(self):
        self._phase = (self._phase + 1) % 30
        self._draw()
        self._after_id = self.after(80, self._animate)

    def _draw(self):
        self.delete("all")
        s = self._size
        for i in range(3):
            # Phase offset for each dot
            offset = (self._phase + i * 4) % 12
            scale = 0.5 + 0.5 * abs(6 - offset) / 6
            r = s / 4 * scale
            cx = s / 2 + i * s
            cy = s / 2
            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                              fill=self._color, outline="")

    def stop(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
