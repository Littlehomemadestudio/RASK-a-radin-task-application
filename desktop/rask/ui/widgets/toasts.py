"""
rask.ui.widgets.toasts
======================

Toast notifications:

  * ``Toast`` — non-blocking toast that slides in from the top
  * ``Toast.show(parent, message, kind, duration)`` — convenience class method
  * ``ToastManager`` — queues and dispatches toasts, stacks vertically

Kinds
-----
``info``         — blue accent
``success``      — green accent
``warning``      — amber accent
``error``        — red accent
``achievement``  — gold accent + sparkle icon, larger, longer duration
"""
from __future__ import annotations

import time
from typing import Any, Callable, List, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons

__all__ = ["Toast", "ToastManager"]


# =============================================================================
# === Toast kind configuration                                              ===
# =============================================================================

TOAST_COLORS: dict[str, dict] = {
    "info": {
        "color": config.INFO,
        "icon": "info",
        "duration": 3500,
    },
    "success": {
        "color": config.SUCCESS,
        "icon": "check_circle",
        "duration": 3500,
    },
    "warning": {
        "color": config.WARNING,
        "icon": "warning",
        "duration": 4000,
    },
    "error": {
        "color": config.DANGER,
        "icon": "danger",
        "duration": 4500,
    },
    "achievement": {
        "color": config.GOLD,
        "icon": "trophy",
        "duration": 5500,
    },
}


# =============================================================================
# === ToastManager                                                          ===
# =============================================================================

class ToastManager:
    """Manages a vertical stack of active toasts on a parent widget.

    A single instance per top-level window is enough.  Use
    :func:`Toast.show` which lazily creates a manager per parent.
    """

    _managers: dict[int, "ToastManager"] = {}

    def __init__(self, parent: Any) -> None:
        self._parent = parent
        self._active: List["Toast"] = []
        # Container frame at the top of the parent
        self._container = ctk.CTkFrame(parent, fg_color="transparent")
        # Place at the top, full width
        self._container.place(relx=0.5, rely=0.0, anchor="n",
                               relwidth=1.0)
        # Lower so it doesn't block clicks elsewhere
        self._container.lower()

    @classmethod
    def for_parent(cls, parent: Any) -> "ToastManager":
        try:
            key = id(parent)
        except Exception:
            key = 0
        mgr = cls._managers.get(key)
        if mgr is None:
            mgr = cls(parent)
            cls._managers[key] = mgr
        return mgr

    def add(self, toast: "Toast") -> None:
        self._active.append(toast)
        toast.pack(in_=self._container, fill="x", padx=12, pady=(8, 0))
        self._relayout()

    def remove(self, toast: "Toast") -> None:
        if toast in self._active:
            self._active.remove(toast)
        self._relayout()

    def _relayout(self) -> None:
        # Reposition each active toast
        for i, toast in enumerate(self._active):
            try:
                toast.pack_forget()
                toast.pack(in_=self._container, fill="x",
                            padx=12, pady=(8 if i == 0 else 4, 0))
            except Exception:
                pass


# =============================================================================
# === Toast                                                                 ===
# =============================================================================

class Toast(ctk.CTkFrame):
    """Single toast notification.

    Use the class method :meth:`show` rather than constructing directly.
    """

    def __init__(
        self,
        master: Any = None,
        message: str = "",
        kind: str = "info",
        duration: Optional[int] = None,
        on_click: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        cfg = TOAST_COLORS.get(kind, TOAST_COLORS["info"])
        kwargs.setdefault("fg_color", config.SURFACE_HIGHER)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", cfg["color"])
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        super().__init__(master, **kwargs)
        self._message = message
        self._kind = kind
        self._duration = duration or cfg["duration"]
        self._on_click = on_click
        self._lang = lang
        self._manager: Optional[ToastManager] = None
        self._dismiss_job = None
        self._slide_job = None
        self._build(cfg)

    def _build(self, cfg: dict) -> None:
        rtl = i18n.is_rtl(self._lang)
        self.grid_columnconfigure(1, weight=1)
        # Icon
        icon = ctk.CTkLabel(self, text="", width=28, height=28,
                             fg_color="transparent")
        img = _icons.icon(cfg["icon"], 22, color=cfg["color"])
        if img is not None:
            icon.configure(image=img)
        else:
            icon.configure(text=_icons.icon_glyph(cfg["icon"]),
                            text_color=cfg["color"],
                            font=_theme.theme.font(size=18,
                                                    weight="bold", lang="en"))
        icon.grid(row=0, column=0 if not rtl else 2, padx=(12, 6), pady=10)
        # Message
        is_achievement = self._kind == "achievement"
        msg = ctk.CTkLabel(
            self, text=self._message,
            font=_theme.theme.font(
                size=config.FONT_SIZE_BODY_LG if is_achievement
                       else config.FONT_SIZE_BODY,
                weight="bold" if is_achievement else "normal",
                lang=self._lang),
            text_color=config.TEXT,
            wraplength=380,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
        )
        msg.grid(row=0, column=1, sticky="ew", padx=4, pady=10)
        # Bind click to dismiss
        try:
            self.bind("<Button-1>", lambda _e: self.dismiss(), add="+")
            for c in self.winfo_children():
                c.bind("<Button-1>", lambda _e: self.dismiss(), add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Slide animation
    # ------------------------------------------------------------------
    def slide_in(self) -> None:
        try:
            # Start fully transparent and slide down from above
            self.configure(border_width=0)
            self.update_idletasks()
            self._anim_step = 0
            self._anim_total = max(2, config.ANIM_NORMAL // 16)
            self._tick_slide(in_=True)
        except Exception:
            pass

    def slide_out(self) -> None:
        try:
            self._anim_step = 0
            self._anim_total = max(2, config.ANIM_FAST // 16)
            self._tick_slide(in_=False)
        except Exception:
            self._destroy()

    def _tick_slide(self, in_: bool = True) -> None:
        self._anim_step += 1
        t = helpers.ease_out_cubic(self._anim_step / self._anim_total) if in_ \
            else helpers.ease_in_cubic(self._anim_step / self._anim_total)
        try:
            # Move y from -50 to 0 (in) or 0 to -50 (out)
            dy = int((1 - t) * -50) if in_ else int(t * -50)
            self.place_configure(y=dy)
        except Exception:
            pass
        if self._anim_step < self._anim_total:
            self._slide_job = self.after(16, lambda: self._tick_slide(in_))
        else:
            self._slide_job = None
            if not in_:
                self._destroy()

    # ------------------------------------------------------------------
    # Show / dismiss
    # ------------------------------------------------------------------
    def show_on(self, parent: Any) -> None:
        """Add this toast to the parent's toast stack and start the timer."""
        try:
            mgr = ToastManager.for_parent(parent)
            mgr.add(self)
            self._manager = mgr
            self.slide_in()
            # Auto-dismiss after duration
            self._dismiss_job = self.after(self._duration, self.dismiss)
        except Exception:
            pass

    def dismiss(self) -> None:
        if self._dismiss_job:
            try:
                self.after_cancel(self._dismiss_job)
            except Exception:
                pass
            self._dismiss_job = None
        try:
            if self._manager:
                self._manager.remove(self)
        except Exception:
            pass
        self.slide_out()

    def _destroy(self) -> None:
        try:
            self.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Class-method convenience API
    # ------------------------------------------------------------------
    @classmethod
    def show(
        cls,
        parent: Any,
        message: str,
        kind: str = "info",
        duration: Optional[int] = None,
        lang: str = "fa",
        on_click: Optional[Callable[[], Any]] = None,
    ) -> "Toast":
        """Create, position, and auto-dismiss a toast.

        Example
        -------
        >>> Toast.show(root, "ذخیره شد", kind="success")
        """
        toast = cls(parent=parent, message=message, kind=kind,
                     duration=duration, on_click=on_click, lang=lang)
        toast.show_on(parent)
        return toast


# =============================================================================
# === Convenience functions                                                  ===
# =============================================================================

def show_info(parent: Any, message: str, lang: str = "fa") -> Toast:
    return Toast.show(parent, message, kind="info", lang=lang)


def show_success(parent: Any, message: str, lang: str = "fa") -> Toast:
    return Toast.show(parent, message, kind="success", lang=lang)


def show_warning(parent: Any, message: str, lang: str = "fa") -> Toast:
    return Toast.show(parent, message, kind="warning", lang=lang)


def show_error(parent: Any, message: str, lang: str = "fa") -> Toast:
    return Toast.show(parent, message, kind="error", lang=lang)


def show_achievement(parent: Any, message: str, lang: str = "fa") -> Toast:
    return Toast.show(parent, message, kind="achievement", lang=lang)


def _self_test() -> int:
    classes = [Toast, ToastManager]
    print(f"Toasts module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
