"""
rask.ui.dialogs.confirm_dialog
==============================

Custom-styled confirmation dialog — more polished than the base
:class:`rask.ui.widgets.dialogs.ConfirmDialog`.

Features
--------
  * Optional leading icon (danger / warning / info / success / custom)
  * Title (large, bold, gold) + optional message + optional detail text
  * Customizable button labels (e.g. ``"حذف" + "انصراف"``,
    ``"ذخیره" + "دورریختن"``)
  * Danger style for destructive actions (red accent + red icon ring)
  * Optional "دیگر نشان نده" checkbox for non-critical confirms
  * Animated entrance (scale + fade, 220ms ease-out)
  * ESC closes with the negative action
  * RTL layout when ``lang="fa"``
  * Callback API: ``on_result(callback)`` -> ``callback(result_dict)``

Result
------
On close, ``.result`` is a dict::

    {
        "confirmed": bool,        # True if the affirmative button was clicked
        "dont_show_again": bool,  # True if the user ticked the checkbox
    }

or ``None`` if the dialog was dismissed without a button press.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, DangerButton, TextButton
from ..widgets.dividers import Divider
from ..widgets.toggles import CheckBox

__all__ = ["ConfirmDialog"]


# =============================================================================
# === Accent style presets                                                   ===
# =============================================================================

_ACCENTS: Dict[str, Dict[str, str]] = {
    "danger": {
        "color": config.DANGER,
        "ring_bg": config.DANGER_DIM,
        "icon": "warning",
    },
    "warning": {
        "color": config.WARNING,
        "ring_bg": config.WARNING_DIM,
        "icon": "warning",
    },
    "info": {
        "color": config.INFO,
        "ring_bg": config.INFO_DIM,
        "icon": "info",
    },
    "success": {
        "color": config.SUCCESS,
        "ring_bg": config.SUCCESS_DIM,
        "icon": "check_circle",
    },
    "neutral": {
        "color": config.GOLD,
        "ring_bg": config.GOLD_DIM,
        "icon": "info",
    },
}


# =============================================================================
# === Icon ring (decorative circular badge with glyph)                       ===
# =============================================================================

class _IconRing(ctk.CTkFrame):
    """Circular decorative badge with an icon glyph at the centre.

    Used at the top of :class:`ConfirmDialog` to draw attention to the
    dialog's intent (warning / danger / info / success).
    """

    def __init__(
        self,
        master: Any,
        icon_name: str = "info",
        accent: str = config.GOLD,
        ring_bg: str = config.GOLD_DIM,
        size: int = 64,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", ring_bg)
        kwargs.setdefault("corner_radius", size // 2)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)
        self._size = size
        self._icon_name = icon_name
        self._accent = accent
        # Inner label with icon
        self._label = ctk.CTkLabel(self, text="", width=size, height=size)
        self._label.place(relx=0.5, rely=0.5, anchor="center")
        img = _icons.icon(icon_name, size // 2, color=accent)
        if img is not None:
            self._label.configure(image=img, text="")
        else:
            self._label.configure(text=_icons.icon_glyph(icon_name),
                                   text_color=accent,
                                   font=_theme.theme.font(
                                       size=size // 2,
                                       weight="bold",
                                       lang="en"))


# =============================================================================
# === ConfirmDialog                                                          ===
# =============================================================================

class ConfirmDialog(BaseDialog):
    """Polished confirmation dialog.

    Parameters
    ----------
    master
        Parent widget (used to compute the overlay position).
    title
        Bold heading text.
    message
        Body text — wraps up to ``wraplength`` pixels wide.
    detail
        Optional smaller secondary text shown beneath ``message``.
    icon
        Optional accent style: ``"danger"`` / ``"warning"`` / ``"info"``
        / ``"success"`` / ``"neutral"``.  Pass ``None`` to hide the icon
        ring entirely.
    confirm_text, cancel_text
        Button labels.  Defaults respect the current language.
    danger
        Shortcut for ``icon="danger"`` — when True the affirmative
        button becomes a :class:`DangerButton` (red fill).
    show_dont_show_again
        Display the "don't show this again" checkbox (useful for
        non-critical confirms that the user can suppress).
    dont_show_default
        Initial checkbox state.
    on_result
        Callback invoked with the result dict when the dialog closes.
    lang
        UI language code (``"fa"`` / ``"en"`` / ...).

    Result
    ------
    The dialog sets ``self.result`` to::

        {"confirmed": bool, "dont_show_again": bool}

    on affirmative / negative button press, or ``None`` if dismissed
    via overlay click / ESC without a button.
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        message: str = "",
        detail: Optional[str] = None,
        icon: Optional[str] = "neutral",
        confirm_text: Optional[str] = None,
        cancel_text: Optional[str] = None,
        danger: bool = False,
        show_dont_show_again: bool = False,
        dont_show_default: bool = False,
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._message = message
        self._detail = detail
        self._icon_kind = "danger" if danger else (icon or "neutral")
        if self._icon_kind not in _ACCENTS:
            self._icon_kind = "neutral"
        self._show_icon = icon is not None or danger
        self._confirm_text = confirm_text or i18n.t("confirm", lang)
        self._cancel_text = cancel_text or i18n.t("cancel", lang)
        self._danger = danger or self._icon_kind == "danger"
        self._show_dont_show = show_dont_show_again
        self._dont_show_default = dont_show_default
        # Slightly taller than the base confirm to accommodate the icon
        kwargs.setdefault("height", 320)
        kwargs.setdefault("width", 440)
        kwargs.setdefault("close_on_overlay", True)
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        accent = _ACCENTS[self._icon_kind]

        # Top: icon ring (optional)
        if self._show_icon:
            ring = _IconRing(
                self._content,
                icon_name=accent["icon"],
                accent=accent["color"],
                ring_bg=accent["ring_bg"],
                size=64,
            )
            ring.pack(anchor="center", pady=(0, 12))

        # Title is rendered by BaseDialog, so we just show message + detail.
        # Message
        if self._message:
            msg = ctk.CTkLabel(
                self._content, text=self._message,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                wraplength=380,
                anchor="e" if rtl else "w",
                justify="right" if rtl else "left",
            )
            msg.pack(fill="x", pady=(0, 6))

        # Detail
        if self._detail:
            det = ctk.CTkLabel(
                self._content, text=self._detail,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                wraplength=380,
                anchor="e" if rtl else "w",
                justify="right" if rtl else "left",
            )
            det.pack(fill="x", pady=(0, 6))

        # "Don't show again" checkbox
        if self._show_dont_show:
            self._dont_show_cb = CheckBox(
                self._content,
                text=i18n.t("dontShowAgain", self._lang)
                     if i18n.t("dontShowAgain", self._lang) != "dontShowAgain"
                     else ("دیگر نشان نده" if self._lang == "fa"
                            else "Don't show again"),
                lang=self._lang,
            )
            self._dont_show_cb.value = self._dont_show_default
            self._dont_show_cb.pack(
                anchor="e" if rtl else "w", pady=(8, 8))
        else:
            self._dont_show_cb = None

        # Divider
        Divider(self._content).pack(fill="x", pady=(4, 12))

        # Buttons row
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        cancel_btn = GhostButton(
            btn_row, text=self._cancel_text,
            command=self._on_cancel,
            lang=self._lang, height=42,
            font_size=config.FONT_SIZE_BODY,
        )
        if self._danger:
            confirm_btn = DangerButton(
                btn_row, text=self._confirm_text,
                command=self._on_confirm,
                lang=self._lang, height=42,
                font_size=config.FONT_SIZE_BODY,
            )
        else:
            confirm_btn = GoldButton(
                btn_row, text=self._confirm_text,
                command=self._on_confirm,
                lang=self._lang, height=42,
                font_size=config.FONT_SIZE_BODY,
            )

        if rtl:
            confirm_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            confirm_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

        # Auto-focus the cancel button to prevent accidental confirm on Enter.
        try:
            cancel_btn.focus_set()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_confirm(self) -> None:
        dont_show = bool(self._dont_show_cb and self._dont_show_cb.value)
        self.close({"confirmed": True, "dont_show_again": dont_show})

    def _on_cancel(self) -> None:
        dont_show = bool(self._dont_show_cb and self._dont_show_cb.value)
        self.close({"confirmed": False, "dont_show_again": dont_show})

    # ------------------------------------------------------------------
    # Override close() so ESC / overlay-click returns a "not confirmed"
    # result instead of None — this lets the caller treat dismissal as
    # a cancellation without special-casing None.
    # ------------------------------------------------------------------
    def close(self, result: Any = None) -> None:  # type: ignore[override]
        if result is None:
            # Dismissed via overlay / ESC — treat as cancel.
            dont_show = bool(self._dont_show_cb and self._dont_show_cb.value)
            result = {"confirmed": False, "dont_show_again": dont_show}
        super().close(result)


# =============================================================================
# === Convenience helpers                                                    ===
# =============================================================================

def ask_yes_no(
    master: Any,
    title: str,
    message: str,
    *,
    detail: Optional[str] = None,
    danger: bool = False,
    yes_text: Optional[str] = None,
    no_text: Optional[str] = None,
    lang: str = "fa",
    on_result: Optional[Callable[[bool], Any]] = None,
) -> "ConfirmDialog":
    """Open a yes/no confirm and invoke ``on_result(bool)`` on close.

    Convenience wrapper that flattens the result dict into a single
    boolean for callers that don't care about the "don't show again"
    checkbox state.
    """
    def _wrap(result: Optional[Dict[str, Any]]) -> None:
        if on_result is None:
            return
        try:
            on_result(bool(result and result.get("confirmed")))
        except Exception:
            pass

    return ConfirmDialog(
        master=master, title=title, message=message, detail=detail,
        danger=danger, confirm_text=yes_text, cancel_text=no_text,
        on_result=_wrap, lang=lang,
    )


def ask_delete(
    master: Any,
    title: str,
    message: str,
    *,
    detail: Optional[str] = None,
    lang: str = "fa",
    on_result: Optional[Callable[[bool], Any]] = None,
) -> "ConfirmDialog":
    """Open a destructive (red) delete confirmation dialog."""
    yes = i18n.t("delete", lang) if i18n.t("delete", lang) != "delete" else None
    no = i18n.t("cancel", lang) if i18n.t("cancel", lang) != "cancel" else None
    return ask_yes_no(
        master, title, message, detail=detail, danger=True,
        yes_text=yes, no_text=no, lang=lang, on_result=on_result,
    )


def _self_test() -> int:
    print(f"confirm_dialog module: 1 class registered (ConfirmDialog)")
    print(f"  accents: {sorted(_ACCENTS.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
