"""theme.py — Tkinter styling helpers (mirror of web/styles.css rules).

Provides:
  - apply_theme(root): set bg, font, geometry
  - font(family, size, weight): get a tkfont.Font
  - styled_button(parent, kind, text, command): a tk.Button matching .btn .btn-gold etc.
  - chip(parent, text, selected, command): a tk.Button matching .chip / .chip.selected
  - card(parent): a tk.Frame matching .card
  - field(parent, **kw): a tk.Entry matching .field
  - section_header(parent, text): a tk.Label matching .section-header
  - toast(root, text): transient toplevel matching .toast
"""
from __future__ import annotations
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional
from .. import config


# Font family that supports Persian. We try a list and fall back.
def _resolve_font_family() -> str:
    families = set(tkfont.families())
    for cand in ("Vazirmatn", "Vazir", "Noto Sans Arabic", "Noto Naskh Arabic",
                 "DejaVu Sans", "Segoe UI", "Helvetica"):
        if cand in families:
            return cand
    return "TkDefaultFont"


_FAMILY: Optional[str] = None


def family() -> str:
    global _FAMILY
    if _FAMILY is None:
        _FAMILY = _resolve_font_family()
    return _FAMILY


def font(size: int = 14, weight: str = "normal") -> tkfont.Font:
    return tkfont.Font(family=family(), size=size, weight=weight)


def apply_theme(root: tk.Tk) -> None:
    root.configure(bg=config.MATTE_BLACK)
    root.title(config.APP_NAME)
    root.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
    root.minsize(380, 600)
    # Try to make it look like a mobile app: no window decorations on some platforms.
    try:
        root.option_add("*Font", font(14))
    except Exception:
        pass


def styled_button(parent: tk.Widget, kind: str, text: str,
                  command: Optional[Callable[[], None]] = None,
                  small: bool = False) -> tk.Button:
    """kind: 'gold' | 'outline' | 'ghost' | 'danger'"""
    height = 2 if not small else 1
    if kind == "gold":
        bg, fg, active = config.GOLD, config.MATTE_BLACK, config.GOLD_SOFT
    elif kind == "outline":
        bg, fg, active = config.MATTE_BLACK, config.GOLD, config.CHARCOAL
    elif kind == "ghost":
        bg, fg, active = config.SURFACE, config.TEXT, config.SURFACE_HI
    elif kind == "danger":
        bg, fg, active = config.DANGER, "#FFFFFF", "#B04A42"
    else:
        bg, fg, active = config.SURFACE, config.TEXT, config.SURFACE_HI
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=active, activeforeground=fg,
        font=font(12 if small else 14, "bold"),
        relief="flat", bd=0, height=height,
        cursor="hand2", highlightthickness=0,
        padx=config.SPACE_LG, pady=config.SPACE_SM,
    )
    if kind == "outline":
        btn.configure(highlightbackground=config.GOLD, highlightthickness=2, bd=0)
    return btn


def chip(parent: tk.Widget, text: str, selected: bool = False,
         command: Optional[Callable[[], None]] = None) -> tk.Button:
    bg = config.GOLD if selected else config.CHARCOAL
    fg = config.MATTE_BLACK if selected else config.TEXT
    active = config.GOLD_SOFT if selected else config.SURFACE_HI
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=active, activeforeground=fg,
        font=font(12, "bold" if selected else "normal"),
        relief="flat", bd=0, cursor="hand2",
        highlightthickness=1,
        highlightbackground=config.SURFACE_HI if not selected else config.GOLD,
        padx=14, pady=8,
    )
    return btn


def card(parent: tk.Widget) -> tk.Frame:
    f = tk.Frame(parent, bg=config.CHARCOAL,
                 highlightbackground=config.DIVIDER, highlightthickness=1, bd=0)
    return f


def field(parent: tk.Widget, show: str = "", placeholder: str = "") -> tk.Entry:
    e = tk.Entry(
        parent, show=show,
        bg=config.MATTE_BLACK, fg=config.TEXT,
        insertbackground=config.GOLD,
        font=font(15),
        relief="flat", bd=0,
        highlightthickness=0,
    )
    # Bottom gold underline (mirror of .field border-bottom)
    underline = tk.Frame(parent, bg=config.GOLD, height=2)
    e._underline = underline  # type: ignore[attr-defined]
    if placeholder:
        _attach_placeholder(e, placeholder)
    return e


def _attach_placeholder(entry: tk.Entry, placeholder: str) -> None:
    has_text = tk.StringVar()

    def _on_change(*_):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg=config.TEXT_FAINT)
        else:
            entry.config(fg=config.TEXT)

    def _on_focus_in(_):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=config.TEXT)

    def _on_focus_out(_):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg=config.TEXT_FAINT)

    entry.insert(0, placeholder)
    entry.config(fg=config.TEXT_FAINT)
    entry.bind("<FocusIn>", _on_focus_in)
    entry.bind("<FocusOut>", _on_focus_out)


def section_header(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=parent["bg"], fg=config.TEXT,
        font=font(14, "bold"), anchor="w",
    )


def greeting(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=parent["bg"], fg=config.TEXT,
        font=font(22, "bold"), anchor="w",
    )


def date_label(parent: tk.Widget, text: str) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=parent["bg"], fg=config.TEXT_DIM,
        font=font(12), anchor="w",
    )


def toast(root: tk.Tk, text: str, duration_ms: int = 2600) -> None:
    tw = tk.Toplevel(root)
    tw.configure(bg=config.SURFACE_HI)
    tw.overrideredirect(True)
    lbl = tk.Label(tw, text=text, bg=config.SURFACE_HI, fg=config.TEXT,
                   font=font(13), padx=20, pady=10)
    lbl.pack()
    # Position near bottom-center of parent
    root.update_idletasks()
    w = lbl.winfo_reqwidth() + 40
    h = lbl.winfo_reqheight() + 20
    x = root.winfo_x() + (root.winfo_width() - w) // 2
    y = root.winfo_y() + root.winfo_height() - h - 100
    tw.geometry(f"{w}x{h}+{x}+{y}")
    tw.attributes("-topmost", True)
    root.after(duration_ms, tw.destroy)
