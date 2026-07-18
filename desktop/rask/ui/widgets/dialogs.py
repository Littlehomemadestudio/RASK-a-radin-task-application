"""
rask.ui.widgets.dialogs
=======================

Base dialog primitives:

  * ``BaseDialog``   — modal toplevel with overlay + fade-in
  * ``AlertDialog``  — title + message + OK button
  * ``ConfirmDialog`` — Yes/No dialog, callback returns boolean
  * ``PromptDialog``  — text input dialog, returns string
  * ``ChoiceDialog``  — pick from list
  * ``BottomSheet``   — slides up from bottom (mobile-style), drag-to-dismiss

All dialogs:
  * Gold title, dark bg, semi-transparent overlay backdrop
  * ESC to close, click-outside to close (configurable)
  * Animated entrance (200ms ease-out)
  * ``.result`` attribute for synchronous-style usage
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .buttons import GoldButton, GhostButton, TextButton
from .inputs import GoldEntry

__all__ = [
    "BaseDialog", "AlertDialog", "ConfirmDialog",
    "PromptDialog", "ChoiceDialog", "BottomSheet",
]


# =============================================================================
# === BaseDialog                                                            ===
# =============================================================================

class BaseDialog(ctk.CTkToplevel):
    """Base modal dialog with overlay backdrop.

    Subclasses override :meth:`_build_content` to add widgets inside the
    dialog body.  ``self.result`` holds the final value (set by
    subclasses when the user confirms).
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        width: int = 460,
        height: int = 240,
        close_on_overlay: bool = True,
        close_on_esc: bool = True,
        animated: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.MATTE_BLACK)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", config.GOLD_DIM)
        kwargs.setdefault("corner_radius", config.RADIUS_LG)
        super().__init__(master, **kwargs)
        self._title = title
        self._width = width
        self._height = height
        self._close_on_overlay = close_on_overlay
        self._close_on_esc = close_on_esc
        self._animated = animated
        self._lang = lang
        self.result: Any = None
        self._on_result: Optional[Callable[[Any], Any]] = None
        self._overlay: Optional[ctk.CTkFrame] = None
        self._fade_job = None
        self._drag_start_y: Optional[int] = None
        # Window setup
        try:
            self.title(title)
            self.geometry(f"{width}x{height}")
            self.resizable(False, False)
            self.transient(master)
            self.grab_set()
            # Center on parent
            self._center_on_parent(master)
            self.attributes("-topmost", True)
        except Exception:
            pass
        # Build overlay + content
        self._build_overlay(master)
        self._build_ui()
        self._bind_keys()
        # Animate in
        if animated:
            try:
                self.attributes("-alpha", 0.0)
                self._fade_in()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _center_on_parent(self, parent: Any) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - self._width) // 2
            y = py + (ph - self._height) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build_overlay(self, parent: Any) -> None:
        try:
            if parent is None:
                return
            self._overlay = ctk.CTkFrame(parent,
                                          fg_color=(config.MATTE_BLACK,
                                                    config.MATTE_BLACK))
            # Note: CTk doesn't support real transparency; we use a dark
            # translucent-looking overlay by setting bg to a darkened matte.
            self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._overlay.lower()
            if self._close_on_overlay:
                self._overlay.bind("<Button-1>", lambda _e: self.close(), add="+")
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Title bar
        if self._title:
            title_row = ctk.CTkFrame(self, fg_color="transparent")
            title_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
            title_row.grid_columnconfigure(0, weight=1)
            rtl = i18n.is_rtl(self._lang)
            self._title_label = ctk.CTkLabel(
                title_row, text=self._title,
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
                anchor="e" if rtl else "w",
            )
            self._title_label.grid(row=0, column=0, sticky="ew")
            # Close button
            close = ctk.CTkButton(
                title_row, text="",
                width=28, height=28,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_PILL, cursor="hand2",
                command=self.close,
            )
            close_img = _icons.icon("x", 16, color=config.TEXT_DIM)
            if close_img is not None:
                close.configure(image=close_img)
            else:
                close.configure(text="×", text_color=config.TEXT_DIM)
            close.grid(row=0, column=1, padx=(8, 0))
        # Content frame
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=1, column=0, sticky="nsew",
                            padx=20, pady=(0, 16))
        self._content.grid_columnconfigure(0, weight=1)
        self._build_content()

    def _build_content(self) -> None:
        """Subclass hook — populate ``self._content``."""
        pass

    def _bind_keys(self) -> None:
        try:
            self.bind("<Escape>", lambda _e: self.close() if self._close_on_esc
                       else None, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------
    def _fade_in(self) -> None:
        self._fade_step = 0
        self._fade_total = max(2, config.ANIM_NORMAL // 16)
        self._tick_fade(in_=True)

    def _fade_out_and_close(self) -> None:
        self._fade_step = 0
        self._fade_total = max(2, config.ANIM_FAST // 16)
        self._tick_fade(in_=False)

    def _tick_fade(self, in_: bool = True) -> None:
        self._fade_step += 1
        t = helpers.ease_out_cubic(self._fade_step / self._fade_total)
        alpha = t if in_ else 1.0 - t
        try:
            self.attributes("-alpha", float(helpers.clamp(alpha, 0.0, 1.0)))
        except Exception:
            pass
        if self._fade_step < self._fade_total:
            self._fade_job = self.after(16, lambda: self._tick_fade(in_))
        else:
            self._fade_job = None
            if not in_:
                self._destroy()

    # ------------------------------------------------------------------
    # Close API
    # ------------------------------------------------------------------
    def close(self, result: Any = None) -> None:
        if result is not None:
            self.result = result
        if self._on_result:
            try:
                self._on_result(self.result)
            except Exception:
                pass
        if self._animated:
            self._fade_out_and_close()
        else:
            self._destroy()

    def _destroy(self) -> None:
        try:
            if self._overlay is not None:
                self._overlay.destroy()
                self._overlay = None
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def on_result(self, callback: Callable[[Any], Any]) -> "BaseDialog":
        """Register a callback invoked when the dialog closes."""
        self._on_result = callback
        return self


# =============================================================================
# === AlertDialog                                                           ===
# =============================================================================

class AlertDialog(BaseDialog):
    """Simple OK dialog with title + message."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        message: str = "",
        ok_text: str = "تأیید",
        on_ok: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._message = message
        self._ok_text = ok_text
        self._on_ok = on_ok
        kwargs.setdefault("height", 200)
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        msg = ctk.CTkLabel(
            self._content, text=self._message,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            wraplength=380,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
        )
        msg.pack(fill="x", pady=(0, 12))
        ok = GoldButton(
            self._content, text=self._ok_text,
            command=lambda: (self._on_ok() if self._on_ok else None,
                              self.close(True)),
            lang=self._lang, height=38,
            font_size=config.FONT_SIZE_BODY,
        )
        ok.pack(anchor="e" if rtl else "s", pady=(8, 0))


# =============================================================================
# === ConfirmDialog                                                         ===
# =============================================================================

class ConfirmDialog(BaseDialog):
    """Yes/No dialog.  ``.result`` is ``True``/``False``."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        message: str = "",
        yes_text: str = "بله",
        no_text: str = "خیر",
        danger: bool = False,
        on_result: Optional[Callable[[bool], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._message = message
        self._yes_text = yes_text
        self._no_text = no_text
        self._danger = danger
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        msg = ctk.CTkLabel(
            self._content, text=self._message,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            wraplength=380,
            anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
        )
        msg.pack(fill="x", pady=(0, 16))
        # Buttons row
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        from .buttons import DangerButton
        if self._danger:
            yes = DangerButton(btn_row, text=self._yes_text,
                                command=lambda: self.close(True),
                                lang=self._lang, height=38)
        else:
            yes = GoldButton(btn_row, text=self._yes_text,
                              command=lambda: self.close(True),
                              lang=self._lang, height=38)
        no = GhostButton(btn_row, text=self._no_text,
                          command=lambda: self.close(False),
                          lang=self._lang, height=38)
        if rtl:
            yes.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            no.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            no.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            yes.grid(row=0, column=1, sticky="ew", padx=(2, 4))


# =============================================================================
# === PromptDialog                                                          ===
# =============================================================================

class PromptDialog(BaseDialog):
    """Text input dialog.  ``.result`` is the entered string or None."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        message: str = "",
        initial: str = "",
        placeholder: str = "",
        ok_text: str = "تأیید",
        cancel_text: str = "لغو",
        on_result: Optional[Callable[[Optional[str]], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._message = message
        self._initial = initial
        self._placeholder = placeholder
        self._ok_text = ok_text
        self._cancel_text = cancel_text
        super().__init__(master, title=title, lang=lang,
                          height=240, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        msg = ctk.CTkLabel(
            self._content, text=self._message,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            wraplength=380,
            anchor="e" if rtl else "w",
        )
        msg.pack(fill="x", pady=(0, 8))
        self._entry = GoldEntry(
            self._content, placeholder=self._placeholder,
            lang=self._lang, height=42,
        )
        self._entry.value = self._initial
        self._entry.pack(fill="x", pady=(0, 12))
        self._entry.bind("<Return>", lambda _e: self.close(self._entry.value),
                          add="+")
        # Buttons
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        cancel = GhostButton(btn_row, text=self._cancel_text,
                              command=lambda: self.close(None),
                              lang=self._lang, height=38)
        ok = GoldButton(btn_row, text=self._ok_text,
                         command=lambda: self.close(self._entry.value),
                         lang=self._lang, height=38)
        if rtl:
            ok.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            cancel.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            cancel.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            ok.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        try:
            self._entry.focus_set()
        except Exception:
            pass


# =============================================================================
# === ChoiceDialog                                                          ===
# =============================================================================

class ChoiceDialog(BaseDialog):
    """Pick from a list of strings.  ``.result`` is the chosen item."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        choices: Sequence[str] = (),
        initial: Optional[str] = None,
        on_result: Optional[Callable[[Optional[str]], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._choices: List[str] = list(choices)
        self._initial = initial
        kwargs.setdefault("height", 320)
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        for choice in self._choices:
            btn = ctk.CTkButton(
                self._content, text=choice,
                command=lambda c=choice: self.close(c),
                fg_color="transparent",
                hover_color=config.SURFACE,
                text_color=config.TEXT,
                border_width=1 if choice == self._initial else 0,
                border_color=config.GOLD,
                corner_radius=config.RADIUS_MD,
                height=42,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                anchor="e" if rtl else "w",
                cursor="hand2",
            )
            btn.pack(fill="x", pady=2)


# =============================================================================
# === BottomSheet                                                           ===
# =============================================================================

class BottomSheet(BaseDialog):
    """Mobile-style bottom sheet — slides up from the bottom edge.

    Has a grab handle at the top and supports drag-to-dismiss (drag
    down more than 25% of the sheet height to dismiss).
    """

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        height: int = 480,
        close_on_overlay: bool = True,
        drag_to_dismiss: bool = True,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._drag_to_dismiss = drag_to_dismiss
        kwargs.setdefault("height", height)
        super().__init__(master, title=title, close_on_overlay=close_on_overlay,
                          lang=lang, **kwargs)
        # Position at bottom of parent
        try:
            parent = master
            parent.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            # Sheet width = parent width, height as specified
            self._width = min(540, pw)
            x = px + (pw - self._width) // 2
            y = py + ph - height
            self.geometry(f"{self._width}x{height}+{x}+{y}")
            # Round only the top corners (CTk doesn't support per-corner;
            # use a moderate radius)
            self.configure(corner_radius=config.RADIUS_LG)
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        # Grab handle (top)
        handle = ctk.CTkFrame(self, width=40, height=4,
                               fg_color=config.TEXT_FAINT,
                               corner_radius=config.RADIUS_PILL)
        handle.grid(row=0, column=0, pady=(8, 4))
        # Title bar
        if self._title:
            title_row = ctk.CTkFrame(self, fg_color="transparent")
            title_row.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
            title_row.grid_columnconfigure(0, weight=1)
            rtl = i18n.is_rtl(self._lang)
            ctk.CTkLabel(
                title_row, text=self._title,
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang=self._lang),
                text_color=config.GOLD,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0, sticky="ew")
            close = ctk.CTkButton(
                title_row, text="",
                width=28, height=28,
                fg_color="transparent", hover_color=config.SURFACE_HI,
                corner_radius=config.RADIUS_PILL, cursor="hand2",
                command=self.close,
            )
            close_img = _icons.icon("x", 16, color=config.TEXT_DIM)
            if close_img is not None:
                close.configure(image=close_img)
            else:
                close.configure(text="×", text_color=config.TEXT_DIM)
            close.grid(row=0, column=1, padx=(8, 0))
        # Content frame
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=2, column=0, sticky="nsew",
                            padx=20, pady=(0, 16))
        self._content.grid_columnconfigure(0, weight=1)
        self._build_content()
        # Drag bindings
        if self._drag_to_dismiss:
            try:
                handle.bind("<ButtonPress-1>", self._drag_start, add="+")
                handle.bind("<B1-Motion>", self._drag_motion, add="+")
                handle.bind("<ButtonRelease-1>", self._drag_end, add="+")
            except Exception:
                pass

    def _drag_start(self, evt: Any) -> None:
        self._drag_start_y = evt.y_root

    def _drag_motion(self, evt: Any) -> None:
        if self._drag_start_y is None:
            return
        try:
            dy = evt.y_root - self._drag_start_y
            if dy > 0:
                # Move sheet down with the drag
                parent = self.master
                py = parent.winfo_rooty()
                ph = parent.winfo_height()
                h = self._height - dy
                if h < 100:
                    return
                # Just shift the y position
                self.geometry(f"+{self.winfo_rootx()}+{py + ph - h}")
        except Exception:
            pass

    def _drag_end(self, evt: Any) -> None:
        if self._drag_start_y is None:
            return
        try:
            dy = evt.y_root - self._drag_start_y
            if dy > self._height * 0.25:
                self.close()
            else:
                # Snap back
                parent = self.master
                py = parent.winfo_rooty()
                ph = parent.winfo_height()
                self.geometry(f"+{self.winfo_rootx()}+{py + ph - self._height}")
        except Exception:
            pass
        self._drag_start_y = None

    def _build_content(self) -> None:
        pass


def _self_test() -> int:
    classes = [BaseDialog, AlertDialog, ConfirmDialog,
                PromptDialog, ChoiceDialog, BottomSheet]
    print(f"Dialogs module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
