"""
rask.ui.widgets.empty_state
===========================

Empty-state placeholder: large icon + title + subtitle + optional
action button.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ... import config
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .buttons import GoldButton

__all__ = ["EmptyState"]


# =============================================================================
# === EmptyState                                                            ===
# =============================================================================

class EmptyState(ctk.CTkFrame):
    """Centered empty-state placeholder.

    Parameters
    ----------
    icon
        Either an icon name (string) drawn via :mod:`rask.ui.widgets.icons`,
        or a unicode glyph used directly as text.
    title
        Big bold heading.
    subtitle
        Smaller dim text below the title.
    action_text
        Optional button text.
    on_action
        Optional callback invoked when the button is clicked.
    """

    def __init__(
        self,
        master: Any = None,
        icon: str = "ring",
        title: str = "",
        subtitle: str = "",
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        icon_size: int = 72,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._lang = lang
        self._on_action = on_action
        self._icon_name = icon
        # Icon
        self._icon_label = ctk.CTkLabel(self, text="",
                                         width=icon_size, height=icon_size,
                                         fg_color="transparent")
        img = _icons.icon(icon, icon_size, color=config.GOLD_DIM)
        if img is not None:
            self._icon_label.configure(image=img)
        else:
            self._icon_label.configure(text=_icons.icon_glyph(icon),
                                         text_color=config.GOLD_DIM,
                                         font=_theme.theme.font(
                                             size=icon_size,
                                             weight="normal", lang="en"))
        self._icon_label.pack(pady=(24, 12))
        # Title
        self._title_label = ctk.CTkLabel(
            self, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
        )
        self._title_label.pack(pady=(4, 4))
        # Subtitle
        if subtitle:
            self._subtitle_label = ctk.CTkLabel(
                self, text=subtitle,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
                wraplength=320,
            )
            self._subtitle_label.pack(pady=(0, 16))
        # Action button
        if action_text:
            self._action_btn = GoldButton(
                self, text=action_text, command=self._handle_action,
                lang=lang,
                height=40, font_size=config.FONT_SIZE_BODY,
            )
            self._action_btn.pack(pady=(8, 24))

    def _handle_action(self) -> None:
        if self._on_action:
            try:
                self._on_action()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def set_title(self, title: str) -> None:
        try:
            self._title_label.configure(text=title)
        except Exception:
            pass

    def set_subtitle(self, subtitle: str) -> None:
        try:
            self._subtitle_label.configure(text=subtitle)
        except Exception:
            pass

    def set_icon(self, icon: str) -> None:
        self._icon_name = icon
        try:
            img = _icons.icon(icon, 72, color=config.GOLD_DIM)
            if img is not None:
                self._icon_label.configure(image=img)
            else:
                self._icon_label.configure(text=_icons.icon_glyph(icon))
        except Exception:
            pass


def _self_test() -> int:
    classes = [EmptyState]
    print(f"Empty state module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
