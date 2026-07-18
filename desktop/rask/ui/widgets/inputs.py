"""
rask.ui.widgets.inputs
======================

Gold-themed input widgets for the Rask desktop app.

All inputs expose a ``.value`` property (returns the current value as a
string or appropriate Python type) and a ``.validate()`` method that
returns ``True`` when the input passes validation and raises
``ValueError`` (or returns ``False`` if ``raise_on_fail=False``) on a
bad value.

Variants
--------
``GoldEntry``       — single-line text entry, gold underline on focus
``PasswordEntry``   — GoldEntry + show/hide toggle button
``SearchEntry``     — GoldEntry + search icon + clear button
``TextArea``        — multiline Textbox, gold focus border
``NumberEntry``     — numeric-only entry with optional ±stepper
``TimeEntry``       — HH:MM entry with up/down steppers
``DurationEntry``   — hours + minutes combined entry
``PinEntry``        — 4-box PIN input, auto-advance, dots displayed
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import validators
from . import theme as _theme
from . import icons as _icons

__all__ = [
    "GoldEntry", "PasswordEntry", "SearchEntry", "TextArea",
    "NumberEntry", "TimeEntry", "DurationEntry", "PinEntry",
]


# =============================================================================
# === GoldEntry                                                             ===
# =============================================================================

class GoldEntry(ctk.CTkEntry):
    """Single-line text entry with gold underline on focus.

    The default CTk border is replaced with a thin gold bottom border
    that brightens when the entry has focus.  Supports RTL via
    ``lang="fa"``.
    """

    def __init__(
        self,
        master: Any = None,
        placeholder: str = "",
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 50,
        max_chars: Optional[int] = None,
        show: str = "",
        on_change: Optional[Callable[[str], Any]] = None,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("bg_color", config.MATTE_BLACK)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("placeholder_text_color", config.TEXT_FAINT)
        kwargs.setdefault("border_width", 2)
        kwargs.setdefault("border_color", config.DIVIDER)
        kwargs.setdefault("corner_radius", config.RADIUS_SM)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        if placeholder:
            kwargs.setdefault("placeholder_text", placeholder)
        if show:
            kwargs.setdefault("show", show)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._max_chars = max_chars
        self._on_change = on_change
        self._base_border = config.DIVIDER
        self._focus_border = config.GOLD
        try:
            self.bind("<FocusIn>", self._on_focus_in, add="+")
            self.bind("<FocusOut>", self._on_focus_out, add="+")
            # CTkEntry delegates keystrokes to an inner tk.Entry — bind there too.
            inner = self._entry  # type: ignore[attr-defined]
            inner.bind("<KeyRelease>", self._on_key_release, add="+")
            if _is_rtl(lang):
                # RTL: justify right
                try:
                    inner.configure(justify="right")
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Focus / change callbacks
    # ------------------------------------------------------------------
    def _on_focus_in(self, _evt: Any = None) -> None:
        try:
            self.configure(border_color=self._focus_border)
        except Exception:
            pass

    def _on_focus_out(self, _evt: Any = None) -> None:
        try:
            self.configure(border_color=self._base_border)
        except Exception:
            pass

    def _on_key_release(self, _evt: Any = None) -> None:
        if self._max_chars:
            try:
                v = self.get()
                if len(v) > self._max_chars:
                    self.delete(self._max_chars, "end")
            except Exception:
                pass
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        try:
            return self.get()
        except Exception:
            return ""

    @value.setter
    def value(self, v: str) -> None:
        self.delete(0, "end")
        self.insert(0, str(v))

    def validate(self, raise_on_fail: bool = True) -> bool:
        v = self.value
        if not v:
            if raise_on_fail:
                raise ValueError("Value cannot be empty")
            return False
        return True

    def clear(self) -> None:
        self.delete(0, "end")


def _is_rtl(lang: str) -> bool:
    from ... import i18n
    return i18n.is_rtl(lang)


# =============================================================================
# === PasswordEntry                                                         ===
# =============================================================================

class PasswordEntry(ctk.CTkFrame):
    """GoldEntry with a show/hide toggle button on the trailing side."""

    def __init__(
        self,
        master: Any = None,
        placeholder: str = "",
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 50,
        on_change: Optional[Callable[[str], Any]] = None,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("corner_radius", config.RADIUS_SM)
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._shown = False
        rtl = _is_rtl(lang)
        # Entry
        self._entry = GoldEntry(
            self,
            placeholder=placeholder,
            lang=lang,
            height=height,
            show="•",
            on_change=on_change,
            font_size=font_size,
            fg_color=config.MATTE_BLACK,
            border_width=0,
        )
        # Toggle button
        self._toggle = ctk.CTkButton(
            self,
            text="",
            width=height - 8,
            height=height - 8,
            fg_color="transparent",
            hover_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_SM,
            cursor="hand2",
            command=self._toggle_show,
        )
        self._set_toggle_icon()
        if rtl:
            self._toggle.pack(side="left", padx=(4, 8), pady=4)
            self._entry.pack(side="right", fill="both", expand=True,
                             padx=(8, 4), pady=4)
        else:
            self._toggle.pack(side="right", padx=(8, 4), pady=4)
            self._entry.pack(side="left", fill="both", expand=True,
                             padx=(4, 8), pady=4)

    def _set_toggle_icon(self) -> None:
        icon_name = "eye_off" if self._shown else "eye"
        img = _icons.icon(icon_name, 20, color=config.GOLD)
        if img is not None:
            self._toggle.configure(image=img, text="")
        else:
            self._toggle.configure(text=_icons.icon_glyph(icon_name))

    def _toggle_show(self) -> None:
        self._shown = not self._shown
        try:
            self._entry._entry.configure(show="" if self._shown else "•")  # type: ignore[attr-defined]
        except Exception:
            try:
                self._entry.configure(show="" if self._shown else "•")
            except Exception:
                pass
        self._set_toggle_icon()

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return self._entry.value

    @value.setter
    def value(self, v: str) -> None:
        self._entry.value = v

    def validate(self, raise_on_fail: bool = True) -> bool:
        v = self.value
        if len(v) < 4:
            if raise_on_fail:
                raise ValueError("Password too short")
            return False
        return True

    def clear(self) -> None:
        self._entry.clear()


# =============================================================================
# === SearchEntry                                                           ===
# =============================================================================

class SearchEntry(ctk.CTkFrame):
    """GoldEntry with a search icon on the leading side and clear on trailing."""

    def __init__(
        self,
        master: Any = None,
        placeholder: str = "جستجو…",
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 44,
        on_change: Optional[Callable[[str], Any]] = None,
        on_submit: Optional[Callable[[str], Any]] = None,
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._on_submit = on_submit
        rtl = _is_rtl(lang)
        # Search icon
        self._search_btn = ctk.CTkLabel(
            self, text="",
            width=height - 12, height=height - 12,
            fg_color="transparent",
        )
        img = _icons.icon("search", 18, color=config.TEXT_DIM)
        if img is not None:
            self._search_btn.configure(image=img)
        else:
            self._search_btn.configure(text=_icons.icon_glyph("search"),
                                       text_color=config.TEXT_DIM)
        # Entry
        self._entry = GoldEntry(
            self,
            placeholder=placeholder,
            lang=lang,
            height=height - 8,
            on_change=on_change,
            font_size=font_size,
            fg_color="transparent",
            border_width=0,
            corner_radius=config.RADIUS_PILL,
        )
        self._entry.bind("<Return>", lambda _e: self._submit(), add="+")
        # Clear button
        self._clear_btn = ctk.CTkButton(
            self, text="",
            width=height - 12, height=height - 12,
            fg_color="transparent",
            hover_color=config.SURFACE_HI,
            corner_radius=config.RADIUS_PILL,
            cursor="hand2",
            command=self._clear,
        )
        clr = _icons.icon("x_circle", 16, color=config.TEXT_FAINT)
        if clr is not None:
            self._clear_btn.configure(image=clr)
        else:
            self._clear_btn.configure(text=_icons.icon_glyph("x"),
                                      text_color=config.TEXT_FAINT)
        if rtl:
            # Persian: search icon on right, clear on left
            self._clear_btn.pack(side="left", padx=(2, 6), pady=4)
            self._entry.pack(side="right", fill="both", expand=True,
                             padx=(6, 2), pady=4)
            self._search_btn.pack(side="right", padx=(2, 8), pady=4)
        else:
            self._search_btn.pack(side="left", padx=(8, 2), pady=4)
            self._entry.pack(side="left", fill="both", expand=True,
                             padx=(2, 6), pady=4)
            self._clear_btn.pack(side="right", padx=(6, 2), pady=4)

    def _submit(self) -> None:
        if self._on_submit:
            try:
                self._on_submit(self.value)
            except Exception:
                pass

    def _clear(self) -> None:
        self._entry.clear()
        if self._on_submit:
            try:
                self._on_submit("")
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return self._entry.value

    @value.setter
    def value(self, v: str) -> None:
        self._entry.value = v

    def validate(self, raise_on_fail: bool = True) -> bool:
        return True  # search is always valid

    def clear(self) -> None:
        self._clear()

    def focus(self) -> None:
        try:
            self._entry.focus_set()
        except Exception:
            pass


# =============================================================================
# === TextArea                                                              ===
# =============================================================================

class TextArea(ctk.CTkTextbox):
    """Multiline text area with gold focus border."""

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 120,
        max_chars: Optional[int] = None,
        placeholder: str = "",
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("bg_color", config.MATTE_BLACK)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("border_width", 2)
        kwargs.setdefault("border_color", config.DIVIDER)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._max_chars = max_chars
        self._placeholder = placeholder
        self._placeholder_active = False
        if _is_rtl(lang):
            try:
                self.configure(justify="right")
            except Exception:
                pass
        try:
            self.bind("<FocusIn>", self._on_focus_in, add="+")
            self.bind("<FocusOut>", self._on_focus_out, add="+")
            if max_chars:
                self.bind("<KeyRelease>", self._enforce_max, add="+")
        except Exception:
            pass
        if placeholder:
            self._set_placeholder()

    def _on_focus_in(self, _evt: Any = None) -> None:
        try:
            self.configure(border_color=config.GOLD)
        except Exception:
            pass
        if self._placeholder_active:
            self._clear_placeholder()

    def _on_focus_out(self, _evt: Any = None) -> None:
        try:
            self.configure(border_color=config.DIVIDER)
        except Exception:
            pass
        if not self.get("1.0", "end-1c"):
            self._set_placeholder()

    def _set_placeholder(self) -> None:
        try:
            self.insert("1.0", self._placeholder)
            self._placeholder_active = True
            try:
                self._textbox.configure(foreground=config.TEXT_FAINT)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def _clear_placeholder(self) -> None:
        try:
            self.delete("1.0", "end")
            self._placeholder_active = False
            try:
                self._textbox.configure(foreground=config.TEXT)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def _enforce_max(self, _evt: Any = None) -> None:
        if not self._max_chars:
            return
        try:
            v = self.get("1.0", "end-1c")
            if len(v) > self._max_chars:
                self.delete(f"1.0 + {self._max_chars} chars", "end")
        except Exception:
            pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        if self._placeholder_active:
            return ""
        try:
            return self.get("1.0", "end-1c")
        except Exception:
            return ""

    @value.setter
    def value(self, v: str) -> None:
        try:
            self.delete("1.0", "end")
            if v:
                self.insert("1.0", str(v))
                self._placeholder_active = False
        except Exception:
            pass

    def validate(self, raise_on_fail: bool = True) -> bool:
        return True

    def clear(self) -> None:
        try:
            self.delete("1.0", "end")
        except Exception:
            pass


# =============================================================================
# === NumberEntry                                                           ===
# =============================================================================

class NumberEntry(ctk.CTkFrame):
    """Numeric-only entry with optional ±stepper buttons."""

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        width: Optional[int] = None,
        height: int = 44,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        step: float = 1,
        show_stepper: bool = True,
        unit: str = "",
        on_change: Optional[Callable[[Optional[float]], Any]] = None,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._min = min_value
        self._max = max_value
        self._step = step
        self._unit = unit
        self._on_change = on_change
        rtl = _is_rtl(lang)
        # Entry
        self._entry = ctk.CTkEntry(
            self,
            fg_color="transparent",
            text_color=config.TEXT,
            border_width=0,
            corner_radius=config.RADIUS_MD,
            justify="right" if rtl else "left",
            font=_theme.theme.font(
                size=font_size, weight="bold", lang=lang),
            height=height - 4,
        )
        self._entry.bind("<KeyRelease>", self._on_key_release, add="+")
        # Stepper buttons
        if show_stepper:
            self._dec = ctk.CTkButton(
                self, text="−",
                width=height - 8, height=height - 8,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                text_color=config.GOLD,
                corner_radius=config.RADIUS_SM, cursor="hand2",
                font=_theme.theme.font(size=font_size + 4, weight="bold"),
                command=self._dec_value,
            )
            self._inc = ctk.CTkButton(
                self, text="+",
                width=height - 8, height=height - 8,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                text_color=config.GOLD,
                corner_radius=config.RADIUS_SM, cursor="hand2",
                font=_theme.theme.font(size=font_size + 4, weight="bold"),
                command=self._inc_value,
            )
        if show_stepper:
            if rtl:
                self._dec.pack(side="right", padx=4, pady=2)
                self._entry.pack(side="right", fill="both", expand=True,
                                 padx=4, pady=2)
                self._inc.pack(side="left", padx=4, pady=2)
            else:
                self._inc.pack(side="right", padx=4, pady=2)
                self._entry.pack(side="left", fill="both", expand=True,
                                 padx=4, pady=2)
                self._dec.pack(side="left", padx=4, pady=2)
        else:
            self._entry.pack(fill="both", expand=True, padx=4, pady=2)

    def _on_key_release(self, _evt: Any = None) -> None:
        # Strip non-digit/decimal characters
        try:
            v = self._entry.get()
            cleaned = "".join(c for c in v if c.isdigit() or c in ".-")
            # Convert Persian digits to western for validation
            from ... import i18n
            cleaned = i18n.to_en_digits(cleaned)
            if cleaned != v:
                pos = self._entry.index("insert")
                self._entry.delete(0, "end")
                self._entry.insert(0, cleaned)
                try:
                    self._entry.icursor(pos)
                except Exception:
                    pass
        except Exception:
            pass
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    def _inc_value(self) -> None:
        cur = self.value or 0
        new = cur + self._step
        if self._max is not None and new > self._max:
            new = self._max
        self.value = new

    def _dec_value(self) -> None:
        cur = self.value or 0
        new = cur - self._step
        if self._min is not None and new < self._min:
            new = self._min
        self.value = new

    # ------------------------------------------------------------------
    @property
    def value(self) -> Optional[float]:
        try:
            v = self._entry.get().strip()
            if not v:
                return None
            return float(v)
        except Exception:
            return None

    @value.setter
    def value(self, v: Any) -> None:
        try:
            if v is None:
                self._entry.delete(0, "end")
                return
            num = float(v)
            if self._min is not None and num < self._min:
                num = self._min
            if self._max is not None and num > self._max:
                num = self._max
            self._entry.delete(0, "end")
            if num == int(num):
                s = str(int(num))
            else:
                s = str(num)
            if self._lang == "fa":
                from ... import i18n
                s = i18n.to_fa_digits(s)
            self._entry.insert(0, s + (f" {self._unit}" if self._unit else ""))
        except Exception:
            pass

    def validate(self, raise_on_fail: bool = True) -> bool:
        v = self.value
        if v is None:
            if raise_on_fail:
                raise ValueError("Enter a number")
            return False
        if self._min is not None and v < self._min:
            if raise_on_fail:
                raise ValueError(f"Must be ≥ {self._min}")
            return False
        if self._max is not None and v > self._max:
            if raise_on_fail:
                raise ValueError(f"Must be ≤ {self._max}")
            return False
        return True


# =============================================================================
# === TimeEntry                                                             ===
# =============================================================================

class TimeEntry(ctk.CTkFrame):
    """HH:MM entry with up/down steppers."""

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        initial: str = "12:00",
        format_24: bool = True,
        width: Optional[int] = None,
        height: int = 44,
        on_change: Optional[Callable[[str], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._format_24 = format_24
        self._on_change = on_change
        h, m = (initial.split(":") + ["0", "0"])[:2]
        self._hour = int(h) if str(h).isdigit() else 12
        self._minute = int(m) if str(m).isdigit() else 0
        rtl = _is_rtl(lang)
        # Display label
        self._label = ctk.CTkLabel(
            self,
            text=self._format(),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
        )
        # Up/down buttons
        self._up = ctk.CTkButton(
            self, text="▴",
            width=height - 12, height=(height - 12) // 2,
            fg_color="transparent", hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            corner_radius=config.RADIUS_SM, cursor="hand2",
            command=self._inc,
        )
        self._down = ctk.CTkButton(
            self, text="▾",
            width=height - 12, height=(height - 12) // 2,
            fg_color="transparent", hover_color=config.SURFACE_HI,
            text_color=config.GOLD,
            corner_radius=config.RADIUS_SM, cursor="hand2",
            command=self._dec,
        )
        if rtl:
            self._label.pack(side="right", fill="both", expand=True,
                             padx=4, pady=2)
            self._up.pack(side="left", padx=2, pady=2)
            self._down.pack(side="left", padx=2, pady=2)
        else:
            self._label.pack(side="left", fill="both", expand=True,
                             padx=4, pady=2)
            self._up.pack(side="right", padx=2, pady=2)
            self._down.pack(side="right", padx=2, pady=2)

    def _format(self) -> str:
        h = self._hour
        if not self._format_24:
            suffix = "AM" if h < 12 else "PM"
            h12 = h % 12
            if h12 == 0:
                h12 = 12
            s = f"{h12:02d}:{self._minute:02d} {suffix}"
        else:
            s = f"{h:02d}:{self._minute:02d}"
        if self._lang == "fa":
            from ... import i18n
            s = i18n.to_fa_digits(s)
        return s

    def _inc(self) -> None:
        self._minute += 5
        if self._minute >= 60:
            self._minute = 0
            self._hour = (self._hour + 1) % 24
        self._label.configure(text=self._format())
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    def _dec(self) -> None:
        self._minute -= 5
        if self._minute < 0:
            self._minute = 55
            self._hour = (self._hour - 1) % 24
        self._label.configure(text=self._format())
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return f"{self._hour:02d}:{self._minute:02d}"

    @value.setter
    def value(self, v: str) -> None:
        try:
            h, m = (v.split(":") + ["0", "0"])[:2]
            self._hour = int(h)
            self._minute = int(m)
            self._label.configure(text=self._format())
        except Exception:
            pass

    def validate(self, raise_on_fail: bool = True) -> bool:
        if not (0 <= self._hour <= 23 and 0 <= self._minute <= 59):
            if raise_on_fail:
                raise ValueError("Invalid time")
            return False
        return True


# =============================================================================
# === DurationEntry                                                         ===
# =============================================================================

class DurationEntry(ctk.CTkFrame):
    """Combined hours + minutes entry for duration input."""

    def __init__(
        self,
        master: Any = None,
        lang: str = "fa",
        initial_minutes: int = 0,
        width: Optional[int] = None,
        height: int = 60,
        on_change: Optional[Callable[[int], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.SURFACE_HI)
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._on_change = on_change
        self._hours = initial_minutes // 60
        self._minutes = initial_minutes % 60
        from ... import i18n
        hour_label = "ساعت" if lang == "fa" else "h"
        min_label = "دقیقه" if lang == "fa" else "m"
        self._hour_entry = NumberEntry(
            self, lang=lang, min_value=0, max_value=23, step=1,
            show_stepper=True, unit=hour_label,
            height=height - 8, fg_color="transparent", border_width=0,
        )
        self._hour_entry.value = self._hours
        self._hour_entry._on_change = lambda _v: self._on_field_change()
        self._min_entry = NumberEntry(
            self, lang=lang, min_value=0, max_value=59, step=5,
            show_stepper=True, unit=min_label,
            height=height - 8, fg_color="transparent", border_width=0,
        )
        self._min_entry.value = self._minutes
        self._min_entry._on_change = lambda _v: self._on_field_change()
        rtl = _is_rtl(lang)
        if rtl:
            self._min_entry.pack(side="right", fill="both", expand=True,
                                 padx=4, pady=2)
            self._hour_entry.pack(side="right", fill="both", expand=True,
                                  padx=4, pady=2)
        else:
            self._hour_entry.pack(side="left", fill="both", expand=True,
                                  padx=4, pady=2)
            self._min_entry.pack(side="left", fill="both", expand=True,
                                 padx=4, pady=2)

    def _on_field_change(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> int:
        h = int(self._hour_entry.value or 0)
        m = int(self._min_entry.value or 0)
        return h * 60 + m

    @value.setter
    def value(self, minutes: int) -> None:
        try:
            self._hours = int(minutes) // 60
            self._minutes = int(minutes) % 60
            self._hour_entry.value = self._hours
            self._min_entry.value = self._minutes
        except Exception:
            pass

    def validate(self, raise_on_fail: bool = True) -> bool:
        if self.value <= 0:
            if raise_on_fail:
                raise ValueError("Duration must be > 0")
            return False
        return True


# =============================================================================
# === PinEntry                                                              ===
# =============================================================================

class PinEntry(ctk.CTkFrame):
    """4-box PIN input with auto-advance and dot display."""

    def __init__(
        self,
        master: Any = None,
        length: int = 4,
        lang: str = "fa",
        box_size: int = 56,
        gap: int = 12,
        on_complete: Optional[Callable[[str], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._length = length
        self._lang = lang
        self._on_complete = on_complete
        self._digits: list[str] = []
        self._boxes: list[ctk.CTkFrame] = []
        self._labels: list[ctk.CTkLabel] = []
        self._active_index = 0
        self._build(box_size, gap)
        try:
            self.bind("<KeyPress>", self._on_key, add="+")
            self.bind("<Button-1>", lambda _e: self.focus_set(), add="+")
            self.bind("<FocusIn>", self._redraw, add="+")
        except Exception:
            pass

    def _build(self, box_size: int, gap: int) -> None:
        for i in range(self._length):
            box = ctk.CTkFrame(
                self,
                width=box_size, height=box_size,
                fg_color=config.MATTE_BLACK,
                border_width=2,
                border_color=config.DIVIDER,
                corner_radius=config.RADIUS_MD,
            )
            label = ctk.CTkLabel(
                box, text="",
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                        weight="bold", lang="en"),
                text_color=config.GOLD,
            )
            label.pack(expand=True, fill="both")
            box.grid(row=0, column=i, padx=gap // 2)
            self.grid_columnconfigure(i, weight=0)
            self._boxes.append(box)
            self._labels.append(label)
        self._redraw()

    def _redraw(self, _evt: Any = None) -> None:
        for i, (box, label) in enumerate(zip(self._boxes, self._labels)):
            if i < len(self._digits):
                # Show filled dot instead of digit (privacy)
                label.configure(text="●", text_color=config.GOLD)
            else:
                label.configure(text="", text_color=config.TEXT)
            if i == self._active_index:
                box.configure(border_color=config.GOLD)
            elif i < len(self._digits):
                box.configure(border_color=config.GOLD_DIM)
            else:
                box.configure(border_color=config.DIVIDER)

    def _on_key(self, evt: Any) -> None:
        keysym = getattr(evt, "keysym", "")
        char = getattr(evt, "char", "")
        if keysym in ("BackSpace", "Delete"):
            if self._digits:
                self._digits.pop()
                self._active_index = max(0, len(self._digits))
                self._redraw()
            return "break"
        if keysym in ("Return", "KP_Enter"):
            self._try_complete()
            return "break"
        if char and char.isdigit() and len(self._digits) < self._length:
            self._digits.append(char)
            self._active_index = min(self._length - 1, len(self._digits))
            self._redraw()
            if len(self._digits) == self._length:
                self._try_complete()
            return "break"

    def _try_complete(self) -> None:
        if len(self._digits) == self._length and self._on_complete:
            try:
                self._on_complete("".join(self._digits))
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return "".join(self._digits)

    @value.setter
    def value(self, v: str) -> None:
        self._digits = [c for c in str(v) if c.isdigit()][:self._length]
        self._active_index = min(self._length - 1, len(self._digits))
        self._redraw()

    def validate(self, raise_on_fail: bool = True) -> bool:
        if len(self._digits) != self._length:
            if raise_on_fail:
                raise ValueError(f"PIN must be {self._length} digits")
            return False
        return True

    def clear(self) -> None:
        self._digits = []
        self._active_index = 0
        self._redraw()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    classes = [GoldEntry, PasswordEntry, SearchEntry, TextArea,
               NumberEntry, TimeEntry, DurationEntry, PinEntry]
    print(f"Inputs module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
