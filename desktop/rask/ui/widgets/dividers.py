"""
rask.ui.widgets.dividers
========================

Layout helpers: Divider, Spacer, SectionTitle, Pill.
"""
from __future__ import annotations

from typing import Any, Optional

import customtkinter as ctk

from ... import config
from ... import i18n
from . import theme as _theme

__all__ = ["Divider", "Spacer", "SectionTitle", "Pill"]


# =============================================================================
# === Divider                                                               ===
# =============================================================================

class Divider(ctk.CTkFrame):
    """Horizontal or vertical divider line.

    Parameters
    ----------
    orientation
        ``"horizontal"`` (default) or ``"vertical"``.
    color
        Hex colour of the line.  Defaults to :data:`config.DIVIDER`.
    thickness
        Line thickness in pixels (default 1).
    """

    def __init__(
        self,
        master: Any = None,
        orientation: str = "horizontal",
        color: str = config.DIVIDER,
        thickness: int = 1,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", color)
        if orientation == "vertical":
            kwargs.setdefault("width", thickness)
            kwargs.setdefault("height", height or 100)
        else:
            kwargs.setdefault("width", width or 200)
            kwargs.setdefault("height", thickness)
        super().__init__(master, **kwargs)
        self._orientation = orientation


# =============================================================================
# === Spacer                                                                ===
# =============================================================================

class Spacer(ctk.CTkFrame):
    """Flexible space — expands to fill available room.

    Use ``Spacer(parent).pack(fill="both", expand=True)`` at the bottom
    of a column to push other widgets up.
    """

    def __init__(
        self,
        master: Any = None,
        width: int = 1,
        height: int = 1,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)


# =============================================================================
# === SectionTitle                                                          ===
# =============================================================================

class SectionTitle(ctk.CTkLabel):
    """Section heading — bold, slightly larger than body, gold-on-dark."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        lang: str = "fa",
        size: int = config.FONT_SIZE_BODY_LG,
        color: str = config.TEXT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("text", text)
        kwargs.setdefault("font", _theme.theme.font(size=size,
                                                     weight="bold", lang=lang))
        kwargs.setdefault("text_color", color)
        kwargs.setdefault("anchor", "e" if i18n.is_rtl(lang) else "w")
        super().__init__(master, **kwargs)


# =============================================================================
# === Pill                                                                  ===
# =============================================================================

class Pill(ctk.CTkFrame):
    """Generic pill-shaped container — useful for inline pills of content."""

    def __init__(
        self,
        master: Any = None,
        bg: str = config.SURFACE,
        border_color: str = config.SURFACE_HI,
        border_width: int = 1,
        lang: str = "fa",
        height: int = 32,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", bg)
        kwargs.setdefault("border_color", border_color)
        kwargs.setdefault("border_width", border_width)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang


def _self_test() -> int:
    classes = [Divider, Spacer, SectionTitle, Pill]
    print(f"Dividers module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
