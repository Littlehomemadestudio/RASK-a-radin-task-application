"""theme.py — Tkinter styling helpers (mirror of web/styles.css).

Provides:
  - apply_theme(root): set window bg, font, geometry
  - font(size, weight): get a tkfont.Font
  - family(): get the resolved font family name
  - Plus all the widget factories that delegate to widgets.py:
      styled_button, chip, card, field, section_header, greeting,
      date_label, toast

This module is kept for backwards-compatibility with the older codebase
that called these helper functions directly. New code should use the
widgets in widgets.py directly.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from .. import config
from .. import widgets
from ..widgets import get_font, _resolve_family


# =====================================================================
# === FONT HELPERS ===
# =====================================================================
def family() -> str:
    """Return the resolved font family name."""
    return _resolve_family()


def font(size: int = 14, weight: str = "normal") -> tkfont.Font:
    """Get a Font object at the given size and weight."""
    return get_font(size, weight)


# =====================================================================
# === THEME APPLICATION ===
# =====================================================================
def apply_theme(root: tk.Tk) -> None:
    """Apply the Rask gold-on-dark theme to the root window."""
    root.configure(bg=config.MATTE_BLACK)
    root.title(config.APP_NAME)
    root.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
    root.minsize(config.MIN_WIDTH, config.MIN_HEIGHT)
    # Set default font
    try:
        root.option_add("*Font", get_font(14))
        root.option_add("*Background", config.MATTE_BLACK)
        root.option_add("*Foreground", config.TEXT)
    except Exception:
        pass


# =====================================================================
# === WIDGET FACTORIES (delegate to widgets.py) ===
# =====================================================================
def styled_button(parent: tk.Widget, kind: str, text: str,
                   command: Optional[Callable[[], None]] = None,
                   small: bool = False, icon: Optional[str] = None,
                   lang: str = "fa", full_width: bool = False) -> widgets.GoldButton:
    """Create a GoldButton. kind: 'gold' | 'outline' | 'ghost' | 'danger'."""
    size = "sm" if small else "md"
    return widgets.GoldButton(parent, text=text, command=command, kind=kind,
                                size=size, icon=icon, lang=lang,
                                full_width=full_width)


def chip(parent: tk.Widget, text: str, selected: bool = False,
          command: Optional[Callable[[], None]] = None,
          lang: str = "fa", icon: Optional[str] = None,
          color: Optional[str] = None) -> widgets.Chip:
    """Create a Chip."""
    return widgets.Chip(parent, text=text, command=command, selected=selected,
                         lang=lang, icon=icon, color=color)


def card(parent: tk.Widget, padding: int = 16,
          bg: Optional[str] = None) -> widgets.Card:
    """Create a Card."""
    return widgets.Card(parent, padding=padding, bg=bg)


def field(parent: tk.Widget, show: str = "", placeholder: str = "",
           lang: str = "fa", on_change: Optional[Callable[[str], None]] = None) -> widgets.Field:
    """Create a Field (entry with gold underline)."""
    return widgets.Field(parent, placeholder=placeholder, show=show,
                          lang=lang, on_change=on_change)


def section_header(parent: tk.Widget, text: str,
                    lang: str = "fa") -> tk.Label:
    """Return a section-header label."""
    return widgets.section_header(parent, text, lang)


def greeting(parent: tk.Widget, text: str) -> tk.Label:
    """Return a greeting label."""
    return widgets.greeting_label(parent, text)


def date_label(parent: tk.Widget, text: str) -> tk.Label:
    """Return a date label."""
    return widgets.date_label(parent, text)


def toast(root: tk.Tk, text: str, duration_ms: int = 2600,
           kind: str = "info") -> widgets.Toast:
    """Show a transient toast notification."""
    return widgets.Toast(root, text, duration_ms=duration_ms, kind=kind)


# =====================================================================
# === COLOR HELPERS ===
# =====================================================================
def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (r, g, b)."""
    return config.hex_to_rgb(hex_str)


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> str:
    """Convert hex to rgba string."""
    return config.hex_to_rgba(hex_str, alpha)


def lighten(hex_str: str, factor: float) -> str:
    """Lighten a hex color."""
    return config.lighten(hex_str, factor)


def darken(hex_str: str, factor: float) -> str:
    """Darken a hex color."""
    return config.darken(hex_str, factor)
