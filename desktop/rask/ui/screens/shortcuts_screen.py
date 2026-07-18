"""
rask.ui.screens.shortcuts_screen
================================

Keyboard shortcuts help modal — shows all keyboard shortcuts defined in
:data:`config.SHORTCUTS`.

Layout (top-to-bottom, RTL Persian):
    1. **Title bar** — ``"میانبرهای صفحه‌کلید"`` + close button
    2. **Search bar** — filter shortcuts by name or key combo
    3. **Shortcuts list** — each row shows a gold pill with the key
       combo + the action name (in the current language)
    4. **Close button** — at the bottom

The screen is intended to be displayed as a modal dialog (the App
shell can wrap it in a Toplevel), but it can also be used as a regular
screen — the parent decides.

Subscribes to ``language.changed`` so labels re-render on language
switch.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import event_bus, helpers
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.inputs import SearchEntry
from ..widgets.scrollable import SmoothScrollFrame

__all__ = ["ShortcutsScreen"]


# =============================================================================
# === ShortcutsScreen                                                        ===
# =============================================================================

class ShortcutsScreen(ctk.CTkFrame):
    """Keyboard-shortcuts help screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``close_shortcuts()``
    lang
        ``"fa"`` (default) or ``"en"``.
    """

    def __init__(
        self,
        parent: Any = None,
        app: Any = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        super().__init__(parent, **kwargs)
        self._app = app
        self._lang = lang
        self._subscriptions: List[tuple] = []
        self._query: str = ""
        self._build()
        self._subscribe_events()
        # Esc to close
        try:
            self.bind_all("<Escape>", lambda _e: self._on_close(), add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        # Title bar
        title_bar = ctk.CTkFrame(self, fg_color=config.MATTE_BLACK,
                                  height=56)
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        # Close button
        close_col = 0 if rtl else 2
        IconButton(
            title_bar, icon_name="x",
            command=self._on_close, size=40, lang=self._lang,
        ).grid(row=0, column=close_col, padx=4, pady=8)
        # Title
        ctk.CTkLabel(
            title_bar,
            text=self._tr("keyboardShortcuts", "Keyboard shortcuts"),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD, anchor="e" if rtl else "w",
        ).grid(row=0, column=1, sticky="ew", padx=8)
        # Search bar
        search_bar = ctk.CTkFrame(self, fg_color=config.MATTE_BLACK,
                                   height=48)
        search_bar.grid(row=1, column=0, sticky="ew")
        search_bar.grid_columnconfigure(0, weight=1)
        self._search = SearchEntry(
            search_bar,
            placeholder=self._tr("filterShortcuts",
                                   "Filter shortcuts…"),
            lang=self._lang, height=40,
            on_change=self._on_search_change,
        )
        self._search.grid(row=0, column=0, sticky="ew",
                           padx=config.SPACE_LG, pady=4)
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # Shortcuts container
        self._list_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._list_frame.grid(row=0, column=0, sticky="ew",
                                padx=config.SPACE_LG,
                                pady=(config.SPACE_SM, config.SPACE_LG))
        self._list_frame.grid_columnconfigure(0, weight=1)
        # Render
        self.refresh()
        # Bottom close button
        bottom = ctk.CTkFrame(self, fg_color=config.MATTE_BLACK, height=56)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        GoldButton(
            bottom, text=self._tr("close", "Close"),
            command=self._on_close, lang=self._lang,
            height=42, font_size=config.FONT_SIZE_BODY,
        ).grid(row=0, column=0, padx=config.SPACE_LG, pady=8)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        for ev in ("language.changed",):
            try:
                bus.subscribe(ev, self._on_data_changed)
                self._subscriptions.append((ev, self._on_data_changed))
            except Exception:
                pass

    def _unsubscribe_events(self) -> None:
        bus = event_bus.bus
        for ev, cb in self._subscriptions:
            try:
                bus.unsubscribe(ev, cb)
            except Exception:
                pass
        self._subscriptions.clear()

    def _on_data_changed(self, *args: Any, **kwargs: Any) -> None:
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the shortcuts list."""
        # Clear
        for child in self._list_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        # Filter shortcuts
        shortcuts = self._filtered_shortcuts()
        if not shortcuts:
            ctk.CTkLabel(
                self._list_frame,
                text=self._tr("noShortcutsMatch",
                                "No shortcuts match your filter"),
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                anchor="e" if i18n.is_rtl(self._lang) else "w",
            ).grid(row=0, column=0, sticky="ew", pady=config.SPACE_LG)
            return
        rtl = i18n.is_rtl(self._lang)
        # Render one row per shortcut
        for i, sc in enumerate(shortcuts):
            row = ctk.CTkFrame(self._list_frame, fg_color=config.CHARCOAL,
                                corner_radius=config.RADIUS_MD,
                                border_width=1, border_color=config.DIVIDER,
                                height=48)
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_propagate(False)
            row.grid_columnconfigure(1, weight=1)
            # Action name (main text)
            name = (sc.get("name_fa") if self._lang == "fa"
                     else sc.get("name_en")) or sc.get("action", "")
            ctk.CTkLabel(
                row, text=name,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT, anchor="e" if rtl else "w",
            ).grid(row=0, column=1, sticky="ew", padx=12)
            # Key combo (gold pill) — opposite side
            key_text = sc.get("keys", "")
            key_pill = ctk.CTkFrame(
                row, height=28,
                fg_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_PILL,
                border_width=1, border_color=config.GOLD_DIM,
            )
            key_pill.grid(row=0, column=0 if rtl else 2,
                            padx=12, pady=10)
            key_pill.grid_propagate(False)
            ctk.CTkLabel(
                key_pill, text=key_text,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang="en"),
                text_color=config.GOLD,
            ).pack(padx=12, pady=4)

    def _filtered_shortcuts(self) -> List[Dict[str, Any]]:
        """Return shortcuts filtered by the current search query."""
        if not self._query.strip():
            return list(config.SHORTCUTS)
        q = self._query.lower().strip()
        out = []
        for sc in config.SHORTCUTS:
            name_fa = (sc.get("name_fa") or "").lower()
            name_en = (sc.get("name_en") or "").lower()
            keys = (sc.get("keys") or "").lower()
            action = (sc.get("action") or "").lower()
            if q in name_fa or q in name_en or q in keys or q in action:
                out.append(sc)
        return out

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_search_change(self, value: str) -> None:
        self._query = value
        self.refresh()

    def _on_close(self) -> None:
        if self._app and hasattr(self._app, "close_shortcuts"):
            try:
                self._app.close_shortcuts()
                return
            except Exception:
                pass
        try:
            self.place_forget()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            from ...i18n import t as _t
            v = _t(fa, self._lang)
            if v != fa:
                return v
        except Exception:
            pass
        return fa if self._lang == "fa" else en

    def _show_toast(self, message: str) -> None:
        if self._app and hasattr(self._app, "show_toast"):
            try:
                self._app.show_toast(message)
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.toast", {"message": message,
                                                "kind": "info"})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        self._unsubscribe_events()
        try:
            self.unbind_all("<Escape>")
        except Exception:
            pass
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("ShortcutsScreen module: filterable list of config.SHORTCUTS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
