"""
rask.ui.widgets.toggles
=======================

Gold-themed switch / radio / checkbox / segmented widgets.

All toggles expose a ``.value`` property (returning ``bool`` for
Toggle/CheckBox, the selected string for RadioButton/SegmentedControl)
and an ``.on_change`` callback attribute.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import customtkinter as ctk

from ... import config
from . import theme as _theme

__all__ = ["Toggle", "RadioButton", "CheckBox", "SegmentedControl"]


# =============================================================================
# === Toggle                                                                ===
# =============================================================================

class Toggle(ctk.CTkSwitch):
    """Gold toggle switch.

    Example
    -------
    >>> t = Toggle(parent, text="اعلان‌ها", on_change=lambda v: print(v))
    >>> t.pack(anchor="e")
    >>> t.value = True
    """

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        on_change: Optional[Callable[[bool], Any]] = None,
        lang: str = "fa",
        width: int = 56,
        height: int = 30,
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE_HI)
        kwargs.setdefault("progress_color", config.GOLD)
        kwargs.setdefault("button_color", config.TEXT,
                           )
        kwargs.setdefault("button_hover_color", config.GOLD_BRIGHT)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("border_color", config.GOLD_DIM)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        kwargs.setdefault("width", width + 80)
        kwargs.setdefault("height", height)
        super().__init__(master, text=text, **kwargs)
        self._on_change = on_change
        self._lang = lang
        try:
            self.bind("<Button-1>", self._handle_change, add="+")
        except Exception:
            pass

    def _handle_change(self, _evt: Any = None) -> None:
        # CTkSwitch toggles its state on click before/after our binding.
        # Defer callback so cget("onvalue") reflects the new state.
        self.after(20, self._fire_change)

    def _fire_change(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> bool:
        try:
            return bool(self.get())
        except Exception:
            return False

    @value.setter
    def value(self, v: bool) -> None:
        try:
            if v:
                self.select()
            else:
                self.deselect()
        except Exception:
            pass


# =============================================================================
# === RadioButton                                                           ===
# =============================================================================

class RadioButton(ctk.CTkRadioButton):
    """Gold-themed radio button."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        value: str = "",
        on_change: Optional[Callable[[str], Any]] = None,
        lang: str = "fa",
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.GOLD)
        kwargs.setdefault("hover_color", config.GOLD_BRIGHT)
        kwargs.setdefault("border_color", config.GOLD_DIM)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        kwargs.setdefault("radiobutton_width", 20)
        kwargs.setdefault("radiobutton_height", 20)
        kwargs.setdefault("value", value)
        super().__init__(master, text=text, **kwargs)
        self._on_change = on_change
        self._value_str = value
        try:
            self.bind("<Button-1>", self._handle_change, add="+")
        except Exception:
            pass

    def _handle_change(self, _evt: Any = None) -> None:
        self.after(20, self._fire_change)

    def _fire_change(self) -> None:
        if self._on_change and self.value:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        return self._value_str


# =============================================================================
# === CheckBox                                                              ===
# =============================================================================

class CheckBox(ctk.CTkCheckBox):
    """Gold-themed checkbox."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        on_change: Optional[Callable[[bool], Any]] = None,
        lang: str = "fa",
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.GOLD)
        kwargs.setdefault("hover_color", config.GOLD_BRIGHT)
        kwargs.setdefault("border_color", config.GOLD_DIM)
        kwargs.setdefault("checkmark_color", config.MATTE_BLACK)
        kwargs.setdefault("text_color", config.TEXT)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        kwargs.setdefault("checkbox_width", 22)
        kwargs.setdefault("checkbox_height", 22)
        kwargs.setdefault("corner_radius", config.RADIUS_SM)
        super().__init__(master, text=text, **kwargs)
        self._on_change = on_change
        try:
            self.bind("<Button-1>", self._handle_change, add="+")
        except Exception:
            pass

    def _handle_change(self, _evt: Any = None) -> None:
        self.after(20, self._fire_change)

    def _fire_change(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> bool:
        try:
            var = self._variable
            return bool(var.get())
        except Exception:
            return False

    @value.setter
    def value(self, v: bool) -> None:
        try:
            if v:
                self.select()
            else:
                self.deselect()
        except Exception:
            pass


# =============================================================================
# === SegmentedControl                                                      ===
# =============================================================================

class SegmentedControl(ctk.CTkSegmentedButton):
    """Wrapped CTk segmented button with the gold theme pre-applied."""

    def __init__(
        self,
        master: Any = None,
        values: Sequence[str] = (),
        on_change: Optional[Callable[[str], Any]] = None,
        lang: str = "fa",
        height: int = 36,
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("selected_color", config.GOLD)
        kwargs.setdefault("selected_hover_color", config.GOLD_BRIGHT)
        kwargs.setdefault("unselected_color", config.SURFACE_HI)
        kwargs.setdefault("unselected_hover_color", config.SURFACE_HIGHER)
        kwargs.setdefault("text_color", config.TEXT_DIM)
        kwargs.setdefault("text_color_disabled", config.TEXT_FAINT)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        kwargs.setdefault("height", height)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("values", list(values))
        super().__init__(master, **kwargs)
        self._on_change = on_change
        if on_change:
            try:
                self.configure(command=on_change)
            except Exception:
                pass

    # ------------------------------------------------------------------
    @property
    def value(self) -> str:
        try:
            return str(self.get())
        except Exception:
            return ""

    @value.setter
    def value(self, v: str) -> None:
        try:
            self.set(v)
        except Exception:
            pass


def _self_test() -> int:
    classes = [Toggle, RadioButton, CheckBox, SegmentedControl]
    print(f"Toggles module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
