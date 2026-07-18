"""
rask.ui.widgets.bottom_nav
==========================

Bottom navigation bar with 4-5 tabs (Home / Goals / Stats / Settings)
and an optional FAB slot.

  * Active tab: gold text + icon, small gold dot indicator above
  * Inactive: TEXT_DIM colour
  * Smooth animated indicator slides between tabs
  * Each tab supports a numeric badge (e.g. active reminder count)
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .badges import CountBadge

__all__ = ["BottomNav"]


# =============================================================================
# === NavItem                                                               ===
# =============================================================================

class _NavItem(ctk.CTkFrame):
    """One tab in the bottom nav: icon + label + optional badge."""

    def __init__(
        self,
        master: Any = None,
        icon_name: str = "home",
        label: str = "",
        active: bool = False,
        badge: int = 0,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)
        self._icon_name = icon_name
        self._label = label
        self._active = active
        self._badge_count = badge
        self._lang = lang
        self._on_click = on_click
        # Icon
        self._icon = ctk.CTkLabel(self, text="",
                                   width=24, height=24,
                                   fg_color="transparent")
        self._icon.pack(pady=(8, 2))
        # Label
        self._label_w = ctk.CTkLabel(
            self, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold" if active else "normal",
                                    lang=lang),
            text_color=config.GOLD if active else config.TEXT_DIM,
        )
        self._label_w.pack(pady=(0, 6))
        # Badge (top-right of icon)
        if badge > 0:
            self._badge = CountBadge(self, count=badge, size=16)
            self._badge.place(x=self.winfo_reqwidth() - 18, y=2, anchor="ne")
        else:
            self._badge = None
        # Indicator dot at the top
        self._indicator = ctk.CTkFrame(
            self, width=6, height=6,
            fg_color=config.GOLD if active else "transparent",
            corner_radius=3,
        )
        self._indicator.place(relx=0.5, y=2, anchor="n")
        self._update_icon()
        try:
            self.bind("<Button-1>", lambda _e: self._handle_click(), add="+")
            for c in self.winfo_children():
                c.bind("<Button-1>", lambda _e: self._handle_click(), add="+")
        except Exception:
            pass

    def _update_icon(self) -> None:
        color = config.GOLD if self._active else config.TEXT_DIM
        img = _icons.icon(self._icon_name, 22, color=color)
        if img is not None:
            self._icon.configure(image=img, text="")
        else:
            self._icon.configure(text=_icons.icon_glyph(self._icon_name),
                                  text_color=color,
                                  font=_theme.theme.font(size=18,
                                                          weight="bold",
                                                          lang="en"))

    def _handle_click(self) -> None:
        if self._on_click:
            try:
                self._on_click()
            except Exception:
                pass

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_icon()
        try:
            self._label_w.configure(
                text_color=config.GOLD if active else config.TEXT_DIM,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold" if active else "normal",
                                        lang=self._lang))
            self._indicator.configure(
                fg_color=config.GOLD if active else "transparent")
        except Exception:
            pass

    def set_badge(self, count: int) -> None:
        self._badge_count = count
        if count > 0:
            if self._badge is None:
                self._badge = CountBadge(self, count=count, size=16)
                self._badge.place(relx=0.75, rely=0.1, anchor="center")
            else:
                self._badge.set_count(count)
        elif self._badge is not None:
            self._badge.set_count(0)


# =============================================================================
# === BottomNav                                                             ===
# =============================================================================

class BottomNav(ctk.CTkFrame):
    """Bottom navigation bar.

    Parameters
    ----------
    items
        Iterable of dicts ``{"key", "icon", "label", "badge"}``.
    active_tab
        Initial active key.
    on_tab
        Callback invoked with the key when the user taps a tab.
    fab_slot
        If True, reserve space on the right edge for a floating action
        button.  The actual FAB should be placed as a sibling of this
        widget (raised above it).
    """

    def __init__(
        self,
        master: Any = None,
        items: Optional[List[dict]] = None,
        active_tab: Optional[str] = None,
        on_tab: Optional[Callable[[str], Any]] = None,
        fab_slot: bool = True,
        lang: str = "fa",
        height: int = config.BOTTOM_NAV_HEIGHT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.CHARCOAL)
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.DIVIDER)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        if items is None:
            items = [
                {"key": "home", "icon": "home", "label": "خانه"},
                {"key": "goals", "icon": "goals", "label": "اهداف"},
                {"key": "stats", "icon": "stats", "label": "آمار"},
                {"key": "settings", "icon": "settings", "label": "تنظیمات"},
            ]
        self._items: List[dict] = list(items)
        self._on_tab = on_tab
        self._fab_slot = fab_slot
        self._lang = lang
        self._active_tab: Optional[str] = active_tab or (
            items[0]["key"] if items else None)
        self._tab_widgets: Dict[str, _NavItem] = {}
        self._indicator: Optional[ctk.CTkFrame] = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._tab_widgets = {}
        n = len(self._items)
        # If FAB slot reserved, add an extra empty column
        cols = n + (1 if self._fab_slot else 0)
        for i in range(cols):
            self.grid_columnconfigure(i, weight=1, uniform="tab")
        rtl = i18n.is_rtl(self._lang)
        for i, item in enumerate(self._items):
            tab = _NavItem(
                self,
                icon_name=item.get("icon", "dot"),
                label=item.get("label", ""),
                active=(item.get("key") == self._active_tab),
                badge=item.get("badge", 0),
                lang=self._lang,
                on_click=lambda k=item.get("key"): self.set_active(k),
            )
            col = (cols - 1 - i) if rtl else i
            tab.grid(row=0, column=col, sticky="nsew")
            self._tab_widgets[item["key"]] = tab
        # Sliding indicator at the top of the active tab
        self._indicator = ctk.CTkFrame(
            self, width=24, height=3,
            fg_color=config.GOLD,
            corner_radius=config.RADIUS_PILL,
        )
        self._position_indicator(animate=False)

    def _position_indicator(self, animate: bool = True) -> None:
        if not self._active_tab or self._indicator is None:
            return
        tab = self._tab_widgets.get(self._active_tab)
        if tab is None:
            return
        try:
            self.update_idletasks()
            x = tab.winfo_x()
            w = tab.winfo_width()
            # Animate by stepwise move
            if animate:
                self._animate_indicator_to(x, w)
            else:
                self._indicator.place(x=x, y=0, width=w, height=3, anchor="nw")
        except Exception:
            pass

    def _animate_indicator_to(self, target_x: int, target_w: int) -> None:
        try:
            cur_x = self._indicator.winfo_x()
            cur_w = self._indicator.winfo_width()
        except Exception:
            cur_x, cur_w = 0, 0
        steps = max(2, config.ANIM_FAST // 16)
        self._ind_step = 0
        self._ind_start = (cur_x, cur_w)
        self._ind_target = (target_x, target_w)
        self._ind_total = steps
        self._tick_indicator()

    def _tick_indicator(self) -> None:
        self._ind_step += 1
        t = helpers.ease_out_cubic(self._ind_step / self._ind_total)
        x = helpers.lerp(self._ind_start[0], self._ind_target[0], t)
        w = helpers.lerp(self._ind_start[1], self._ind_target[1], t)
        try:
            self._indicator.place(x=int(x), y=0, width=int(w), height=3,
                                   anchor="nw")
        except Exception:
            pass
        if self._ind_step < self._ind_total:
            self.after(16, self._tick_indicator)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_active(self, key: str) -> None:
        if key == self._active_tab:
            return
        if key not in self._tab_widgets:
            return
        prev = self._active_tab
        self._active_tab = key
        if prev and prev in self._tab_widgets:
            self._tab_widgets[prev].set_active(False)
        self._tab_widgets[key].set_active(True)
        self._position_indicator(animate=True)
        if self._on_tab:
            try:
                self._on_tab(key)
            except Exception:
                pass

    def get_active(self) -> Optional[str]:
        return self._active_tab

    @property
    def active_tab(self) -> Optional[str]:
        return self._active_tab

    def set_badge(self, key: str, count: int) -> None:
        """Update the badge count for tab ``key``."""
        tab = self._tab_widgets.get(key)
        if tab is not None:
            tab.set_badge(count)

    def add_tab(self, item: dict) -> None:
        self._items.append(item)
        self._build()

    def remove_tab(self, key: str) -> None:
        self._items = [i for i in self._items if i.get("key") != key]
        if self._active_tab == key and self._items:
            self._active_tab = self._items[0]["key"]
        self._build()


def _self_test() -> int:
    classes = [BottomNav]
    print(f"Bottom nav module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
