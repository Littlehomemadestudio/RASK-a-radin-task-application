"""
rask.ui.widgets.tooltips
========================

Hover tooltip service.

Usage
-----
>>> from rask.ui.widgets.tooltips import Tooltip
>>> Tooltip.attach(my_button, "Save the current document", delay=500)
>>> ...
>>> Tooltip.detach(my_button)
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from weakref import WeakKeyDictionary

import customtkinter as ctk

from ... import config
from ... import i18n
from . import theme as _theme

__all__ = ["Tooltip"]


# =============================================================================
# === Tooltip                                                              ===
# =============================================================================

class Tooltip:
    """Attach/detach hover tooltips to any Tk widget.

    Tooltips are styled: dark background, gold border, small text.
    Multiple widgets can have tooltips simultaneously — each attachment
    is tracked in a weak-ref dictionary so the widget can be garbage
    collected cleanly.
    """

    _instances: "WeakKeyDictionary[Any, Tooltip]" = WeakKeyDictionary()

    def __init__(
        self,
        widget: Any,
        text: str,
        delay: int = 500,
        duration: int = 3000,
        lang: str = "fa",
    ) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._duration = duration
        self._lang = lang
        self._after_enter: Optional[str] = None
        self._tip_win: Optional[ctk.CTkToplevel] = None
        try:
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
            widget.bind("<Button-1>", self._on_leave, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_enter(self, _evt: Any = None) -> None:
        if self._after_enter:
            try:
                self._widget.after_cancel(self._after_enter)
            except Exception:
                pass
        self._after_enter = self._widget.after(self._delay, self._show)

    def _on_leave(self, _evt: Any = None) -> None:
        if self._after_enter:
            try:
                self._widget.after_cancel(self._after_enter)
            except Exception:
                pass
            self._after_enter = None
        self._hide()

    def _show(self) -> None:
        self._after_enter = None
        if self._tip_win is not None:
            return
        try:
            tip = ctk.CTkToplevel(self._widget)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            try:
                tip.attributes("-alpha", 0.95)
            except Exception:
                pass
            # Build content
            lbl = ctk.CTkLabel(
                tip, text=self._text,
                fg_color=config.SURFACE_HIGHER,
                text_color=config.TEXT,
                corner_radius=config.RADIUS_SM,
                border_width=1,
                border_color=config.GOLD_DIM,
                padx=10, pady=6,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
                wraplength=240,
            )
            lbl.pack()
            # Position near widget
            self._widget.update_idletasks()
            x = self._widget.winfo_rootx() + 16
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
            tip.geometry(f"+{x}+{y}")
            self._tip_win = tip
            # Auto-hide after duration
            if self._duration > 0:
                self._widget.after(self._duration, self._hide)
        except Exception:
            pass

    def _hide(self) -> None:
        if self._tip_win is not None:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None

    def set_text(self, text: str) -> None:
        self._text = text

    def destroy(self) -> None:
        self._hide()
        try:
            self._widget.unbind("<Enter>")
            self._widget.unbind("<Leave>")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Class-level attach/detach API
    # ------------------------------------------------------------------
    @classmethod
    def attach(
        cls,
        widget: Any,
        text: str,
        delay: int = 500,
        duration: int = 3000,
        lang: str = "fa",
    ) -> "Tooltip":
        """Attach a tooltip to `widget`.  Replaces any existing one."""
        cls.detach(widget)
        tip = cls(widget, text, delay=delay, duration=duration, lang=lang)
        cls._instances[widget] = tip
        return tip

    @classmethod
    def detach(cls, widget: Any) -> None:
        """Detach the tooltip from `widget` if any."""
        tip = cls._instances.pop(widget, None)
        if tip is not None:
            tip.destroy()


def _self_test() -> int:
    classes = [Tooltip]
    print(f"Tooltips module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
