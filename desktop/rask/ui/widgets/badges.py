"""
rask.ui.widgets.badges
======================

Small chip / badge widgets:

  * ``Chip``           — generic pill chip with text + optional icon + close
  * ``CategoryBadge``  — coloured chip for a category
  * ``TagChip``        — chip for a tag (smaller)
  * ``TierBadge``      — metallic tier indicator (bronze/silver/gold/platinum)
  * ``StreakBadge``    — flame icon + day count
  * ``CountBadge``     — small circular count indicator (for nav badges)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons

__all__ = ["Chip", "CategoryBadge", "TagChip", "TierBadge",
           "StreakBadge", "CountBadge"]


# =============================================================================
# === Tier colours                                                          ===
# =============================================================================

TIER_COLORS: dict[str, str] = {
    "bronze": "#C28A5C",
    "silver": "#C0C0C8",
    "gold": config.GOLD,
    "platinum": "#E5E4E2",
}

TIER_DIM_COLORS: dict[str, str] = {
    "bronze": "#5A3E25",
    "silver": "#5C5C60",
    "gold": config.GOLD_DIM,
    "platinum": "#7A7A7A",
}


# =============================================================================
# === Chip                                                                  ===
# =============================================================================

class Chip(ctk.CTkFrame):
    """Generic pill chip — text + optional icon + optional close button."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        icon_name: Optional[str] = None,
        color: str = config.SURFACE_HI,
        text_color: str = config.TEXT,
        selected: bool = False,
        closable: bool = False,
        on_close: Optional[Callable[[], Any]] = None,
        on_click: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        height: int = 32,
        font_size: int = config.FONT_SIZE_SMALL,
        **kwargs: Any,
    ) -> None:
        if selected:
            color = config.GOLD
            text_color = config.MATTE_BLACK
        kwargs.setdefault("fg_color", color)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._color = color
        self._text_color = text_color
        self._on_close = on_close
        self._on_click = on_click
        self._lang = lang
        self._selected = selected
        rtl = i18n.is_rtl(lang)
        if icon_name:
            icon = ctk.CTkLabel(self, text="", width=height - 8,
                                 height=height - 8, fg_color="transparent")
            img = _icons.icon(icon_name, height - 12, color=text_color)
            if img is not None:
                icon.configure(image=img)
            else:
                icon.configure(text=_icons.icon_glyph(icon_name),
                                text_color=text_color)
            icon.pack(side="right" if rtl else "left", padx=(4, 2), pady=4)
        self._label = ctk.CTkLabel(
            self, text=text,
            font=_theme.theme.font(size=font_size, weight="bold"
                                    if selected else "normal", lang=lang),
            text_color=text_color,
        )
        self._label.pack(side="right" if rtl else "left",
                         padx=(4 if icon_name else 10, 2 if closable else 10),
                         pady=4)
        if closable:
            close = ctk.CTkButton(
                self, text="",
                width=height - 8, height=height - 8,
                fg_color="transparent", hover_color=config.SURFACE_HIGHER,
                corner_radius=config.RADIUS_PILL, cursor="hand2",
                command=lambda: on_close() if on_close else None,
            )
            clr = _icons.icon("x_circle", height - 14, color=text_color)
            if clr is not None:
                close.configure(image=clr)
            else:
                close.configure(text="×", text_color=text_color)
            close.pack(side="left" if rtl else "right", padx=(2, 4), pady=4)
        if on_click:
            try:
                self.bind("<Button-1>", lambda _e: on_click(), add="+")
                for c in self.winfo_children():
                    c.bind("<Button-1>", lambda _e: on_click(), add="+")
            except Exception:
                pass

    @property
    def value(self) -> str:
        return self._label.cget("text")


# =============================================================================
# === CategoryBadge                                                         ===
# =============================================================================

class CategoryBadge(Chip):
    """Coloured chip for a category."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        color: str = config.GOLD,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        # Background is a dimmed version of the category color, text is
        # the full colour — keeps the chip legible on dark surfaces.
        bg = helpers.mix_colors(color, config.MATTE_BLACK, 0.7)
        super().__init__(master, text=text, color=bg, text_color=color,
                         icon_name="dot", lang=lang, **kwargs)


# =============================================================================
# === TagChip                                                               ===
# =============================================================================

class TagChip(Chip):
    """Smaller chip for a tag."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        lang: str = "fa",
        closable: bool = False,
        on_close: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("icon_name", "tag")
        super().__init__(master, text=text, color=config.SURFACE,
                         text_color=config.TEXT_DIM, lang=lang,
                         closable=closable, on_close=on_close,
                         height=26, font_size=config.FONT_SIZE_CAPTION,
                         **kwargs)


# =============================================================================
# === TierBadge                                                             ===
# =============================================================================

class TierBadge(ctk.CTkFrame):
    """Tier indicator (bronze/silver/gold/platinum) with metallic gradient."""

    def __init__(
        self,
        master: Any = None,
        tier: str = "gold",
        icon_name: str = "trophy",
        size: int = 48,
        earned: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._tier = tier
        self._earned = earned
        color = TIER_COLORS.get(tier, config.GOLD)
        dim = TIER_DIM_COLORS.get(tier, config.GOLD_DIM)
        actual = color if earned else dim
        kwargs.setdefault("fg_color", actual)
        kwargs.setdefault("corner_radius", size // 2)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)
        self._size = size
        # Inner icon (or lock if not earned)
        icon_color = config.MATTE_BLACK if earned else config.TEXT_FAINT
        icon_w = int(size * 0.55)
        if not earned:
            icon_name = "lock"
        img = _icons.icon(icon_name, icon_w, color=icon_color)
        if img is not None:
            self._icon_label = ctk.CTkLabel(self, image=img, text="")
        else:
            self._icon_label = ctk.CTkLabel(
                self, text=_icons.icon_glyph(icon_name),
                text_color=icon_color,
                font=_theme.theme.font(size=icon_w, weight="bold", lang="en"),
            )
        self._icon_label.pack(expand=True, fill="both")
        # Add a subtle "shine" — a thin border ring
        if earned:
            try:
                self.configure(border_width=2,
                                border_color=helpers.lighten_color(actual, 0.3))
            except Exception:
                pass


# =============================================================================
# === StreakBadge                                                           ===
# =============================================================================

class StreakBadge(ctk.CTkFrame):
    """Flame icon + day count, e.g. 🔥 ۷."""

    def __init__(
        self,
        master: Any = None,
        days: int = 0,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", 26)
        super().__init__(master, **kwargs)
        rtl = i18n.is_rtl(lang)
        # Flame icon
        icon = ctk.CTkLabel(self, text="", width=18, height=18,
                             fg_color="transparent")
        img = _icons.icon("flame", 16, color=config.GOLD)
        if img is not None:
            icon.configure(image=img)
        else:
            icon.configure(text=_icons.icon_glyph("flame"),
                            text_color=config.GOLD)
        icon.pack(side="right" if rtl else "left", padx=(6, 2), pady=3)
        # Day count
        day_text = (i18n.to_fa_digits(days) if lang == "fa" else str(days))
        ctk.CTkLabel(
            self, text=day_text,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="bold", lang=lang),
            text_color=config.GOLD,
        ).pack(side="right" if rtl else "left", padx=(2, 6), pady=3)


# =============================================================================
# === CountBadge                                                            ===
# =============================================================================

class CountBadge(ctk.CTkFrame):
    """Small circular count indicator (for nav badges)."""

    def __init__(
        self,
        master: Any = None,
        count: int = 0,
        size: int = 18,
        color: str = config.DANGER,
        text_color: str = "#FFFFFF",
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", color)
        kwargs.setdefault("corner_radius", size // 2)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)
        self._lang = lang
        self._count = count
        self._size = size
        self._label = ctk.CTkLabel(
            self, text=self._format(count),
            font=_theme.theme.font(size=max(8, size - 6),
                                    weight="bold", lang="en"),
            text_color=text_color,
        )
        self._label.pack(expand=True, fill="both")
        if count <= 0:
            self._hide()

    def _format(self, n: int) -> str:
        if n > 99:
            n = 99
        s = str(n)
        if self._lang == "fa":
            from ... import i18n
            s = i18n.to_fa_digits(s)
        return s

    def set_count(self, n: int) -> None:
        self._count = n
        self._label.configure(text=self._format(n))
        if n > 0:
            self._show()
        else:
            self._hide()

    def _hide(self) -> None:
        try:
            self.pack_forget()
        except Exception:
            pass

    def _show(self) -> None:
        try:
            if not self.winfo_ismapped():
                self.pack()
        except Exception:
            pass


def _self_test() -> int:
    classes = [Chip, CategoryBadge, TagChip, TierBadge, StreakBadge, CountBadge]
    print(f"Badges module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
