"""
rask.ui.widgets.headers
=======================

Screen-header widgets:

  * ``Header``        — title + optional subtitle + optional action button
  * ``TabHeader``     — Header with tab strip below title
  * ``SearchHeader``  — Header with embedded search bar
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

import customtkinter as ctk

from ... import config
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .buttons import IconButton, GoldButton, GhostButton
from .inputs import SearchEntry
from .toggles import SegmentedControl

__all__ = ["Header", "TabHeader", "SearchHeader"]


# =============================================================================
# === Header                                                                ===
# =============================================================================

class Header(ctk.CTkFrame):
    """Screen header: title + optional subtitle + optional action button.

    Layout (RTL example):

        [back]                            [action]
                                 صفحه عنوان
                              زیرعنوان اینجا
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        subtitle: Optional[str] = None,
        back_icon: bool = False,
        on_back: Optional[Callable[[], Any]] = None,
        action_icon: Optional[str] = None,
        action_text: Optional[str] = None,
        on_action: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        height: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("corner_radius", 0)
        if height is not None:
            kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._lang = lang
        self.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(lang)
        # Back button (column 0 in LTR, last column in RTL)
        back_col = 2 if rtl else 0
        action_col = 0 if rtl else 2
        title_col = 1
        if back_icon:
            self._back_btn = IconButton(
                self, icon_name="arrow_right" if rtl else "arrow_left",
                command=on_back or (lambda: None),
                size=40, lang=lang,
            )
            self._back_btn.grid(row=0, column=back_col, padx=4, pady=8,
                                 sticky="nsew")
        # Action button
        if action_icon or action_text:
            if action_text:
                self._action_btn = GhostButton(
                    self, text=action_text, command=on_action or (lambda: None),
                    lang=lang, height=36, icon_name=action_icon,
                )
            else:
                self._action_btn = IconButton(
                    self, icon_name=action_icon or "dots",
                    command=on_action or (lambda: None),
                    size=40, lang=lang,
                )
            self._action_btn.grid(row=0, column=action_col, padx=4, pady=8,
                                    sticky="nsew")
        # Title + subtitle column
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=title_col, sticky="nsew",
                          padx=8, pady=8)
        self._title_label = ctk.CTkLabel(
            title_frame, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        )
        self._title_label.pack(anchor="e" if rtl else "w")
        if subtitle:
            self._subtitle_label = ctk.CTkLabel(
                title_frame, text=subtitle,
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            )
            self._subtitle_label.pack(anchor="e" if rtl else "w", pady=(2, 0))

    def set_title(self, title: str) -> None:
        try:
            self._title_label.configure(text=title)
        except Exception:
            pass

    def set_subtitle(self, subtitle: str) -> None:
        try:
            if hasattr(self, "_subtitle_label"):
                self._subtitle_label.configure(text=subtitle)
            else:
                rtl = i18n.is_rtl(self._lang)
                self._subtitle_label = ctk.CTkLabel(
                    self, text=subtitle,
                    font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                            weight="normal", lang=self._lang),
                    text_color=config.TEXT_DIM,
                    anchor="e" if rtl else "w",
                )
                self._subtitle_label.pack(anchor="e" if rtl else "w",
                                            pady=(2, 0))
        except Exception:
            pass


# =============================================================================
# === TabHeader                                                             ===
# =============================================================================

class TabHeader(Header):
    """Header with a tab strip below the title."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        tabs: Sequence[str] = (),
        active_tab: Optional[str] = None,
        on_tab: Optional[Callable[[str], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, title=title, lang=lang, **kwargs)
        self._on_tab = on_tab
        # Add a second row for the tabs
        self.grid_rowconfigure(1, weight=0)
        self._tab_strip = ctk.CTkFrame(self, fg_color="transparent",
                                        height=40)
        self._tab_strip.grid(row=1, column=0, columnspan=3,
                              sticky="ew", padx=12, pady=(0, 8))
        self._tab_strip.grid_columnconfigure(0, weight=1)
        self._tabs: dict[str, ctk.CTkButton] = {}
        self._tab_indicator: Optional[ctk.CTkFrame] = None
        self._active_tab: Optional[str] = None
        self._build_tabs(list(tabs))
        if active_tab:
            self.set_active_tab(active_tab)

    def _build_tabs(self, tabs: list[str]) -> None:
        for child in self._tab_strip.winfo_children():
            child.destroy()
        self._tabs = {}
        rtl = i18n.is_rtl(self._lang)
        cols = len(tabs)
        for i, tab in enumerate(tabs):
            self._tab_strip.grid_columnconfigure(i, weight=1, uniform="tab")
            btn = ctk.CTkButton(
                self._tab_strip, text=tab,
                command=lambda t=tab: self.set_active_tab(t),
                fg_color="transparent", hover_color=config.SURFACE_HI,
                text_color=config.TEXT_DIM,
                corner_radius=config.RADIUS_MD,
                height=36,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                cursor="hand2",
            )
            col = (cols - 1 - i) if rtl else i
            btn.grid(row=0, column=col, sticky="ew", padx=2, pady=2)
            self._tabs[tab] = btn
        # Indicator frame (small gold underline)
        self._tab_indicator = ctk.CTkFrame(
            self._tab_strip, height=3, fg_color=config.GOLD,
            corner_radius=config.RADIUS_PILL,
        )

    def set_active_tab(self, tab: str) -> None:
        if tab not in self._tabs:
            return
        self._active_tab = tab
        for t, btn in self._tabs.items():
            if t == tab:
                btn.configure(text_color=config.GOLD,
                              font=_theme.theme.font(
                                  size=config.FONT_SIZE_BODY,
                                  weight="bold", lang=self._lang))
            else:
                btn.configure(text_color=config.TEXT_DIM,
                              font=_theme.theme.font(
                                  size=config.FONT_SIZE_BODY,
                                  weight="normal", lang=self._lang))
        # Position the indicator under the active tab
        try:
            self.update_idletasks()
            btn = self._tabs[tab]
            x = btn.winfo_x()
            w = btn.winfo_width()
            self._tab_indicator.place(x=x, rely=1.0, anchor="sw",
                                       width=w, height=3)
        except Exception:
            pass
        if self._on_tab:
            try:
                self._on_tab(tab)
            except Exception:
                pass

    @property
    def active_tab(self) -> Optional[str]:
        return self._active_tab


# =============================================================================
# === SearchHeader                                                          ===
# =============================================================================

class SearchHeader(Header):
    """Header with an embedded search bar below the title."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        placeholder: str = "جستجو…",
        on_search: Optional[Callable[[str], Any]] = None,
        on_change: Optional[Callable[[str], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, title=title, lang=lang, **kwargs)
        self.grid_rowconfigure(1, weight=0)
        self._search = SearchEntry(
            self, placeholder=placeholder, lang=lang,
            on_change=on_change, on_submit=on_search,
            height=40,
        )
        self._search.grid(row=1, column=0, columnspan=3,
                            sticky="ew", padx=12, pady=(0, 8))

    def clear_search(self) -> None:
        self._search.clear()

    def get_query(self) -> str:
        return self._search.value


def _self_test() -> int:
    classes = [Header, TabHeader, SearchHeader]
    print(f"Headers module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
