"""
rask.ui.widgets.buttons
=======================

Button variants for the Rask gold-on-dark theme.

All button classes derive from :class:`customtkinter.CTkButton` and add:

  * Pre-applied gold theme colors (no need to set ``fg_color`` manually)
  * Smooth color-transition hover animations (via :func:`helpers.lerp`)
  * RTL-aware text direction (set ``lang="fa"`` to right-anchor text)
  * Optional icon support via :mod:`rask.ui.widgets.icons`

Available variants
------------------
``GoldButton``       — primary gold-filled, default for confirmations
``GhostButton``      — outline-only, transparent fill, gold border
``TextButton``       — text-only, no border, hover shows underline
``IconButton``       — square icon-only, gold hover
``DangerButton``     — red filled (for destructive actions)
``SuccessButton``    — green filled (for success confirmations)
``PillButton``       — fully rounded (RADIUS_PILL), gold
``FabButton``        — 56×56 circular floating action button with shadow
``SegmentedButton``  — 3-5 segments, one active at a time
"""
from __future__ import annotations

import customtkinter as ctk
from typing import Any, Callable, List, Optional, Sequence, Tuple

from ... import config
from ...core import helpers
from ... import i18n as _i18n  # noqa: F401  (kept for symmetry)
from . import theme as _theme
from . import icons as _icons

__all__ = [
    "GoldButton", "GhostButton", "TextButton", "IconButton",
    "DangerButton", "SuccessButton", "PillButton", "FabButton",
    "SegmentedButton",
]


# =============================================================================
# === Shared animation mixin                                                 ===
# =============================================================================

class _HoverAnimMixin:
    """Internal mixin: animate ``fg_color``/``text_color`` on hover.

    The owning class must set ``self._hover_target_fg``,
    ``self._hover_target_text``, ``self._hover_normal_fg``,
    ``self._hover_normal_text`` (all hex strings) before calling
    :meth:`_bind_hover`.
    """

    def _bind_hover(self, duration_ms: int = None) -> None:
        """Bind ``<Enter>`` / ``<Leave>`` events to start the tween."""
        if duration_ms is None:
            duration_ms = config.ANIM_FAST
        self._hover_duration = duration_ms
        self._hover_step = 0
        self._hover_job = None
        try:
            self.bind("<Enter>", self._hover_enter, add="+")
            self.bind("<Leave>", self._hover_leave, add="+")
            # Also bind on the inner canvas/label that CTk uses so the
            # hover works when the cursor is over the child widget.
            for child in self.winfo_children():
                child.bind("<Enter>", self._hover_enter, add="+")
                child.bind("<Leave>", self._hover_leave, add="+")
        except Exception:
            pass

    def _hover_enter(self, _evt: Any = None) -> None:
        self._hover_to(target_fg=getattr(self, "_hover_target_fg", None),
                       target_text=getattr(self, "_hover_target_text", None))

    def _hover_leave(self, _evt: Any = None) -> None:
        self._hover_to(target_fg=getattr(self, "_hover_normal_fg", None),
                       target_text=getattr(self, "_hover_normal_text", None))

    def _hover_to(self, target_fg: Optional[str],
                  target_text: Optional[str]) -> None:
        if self._hover_job:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
        self._hover_t0_step = 0
        self._hover_start_fg = self._current_fg()
        self._hover_start_text = self._current_text()
        self._hover_end_fg = target_fg or self._hover_start_fg
        self._hover_end_text = target_text or self._hover_start_text
        self._hover_t0_total = max(2, self._hover_duration // 16)
        self._hover_tick()

    def _hover_tick(self) -> None:
        try:
            self._hover_t0_step += 1
            t = self._hover_t0_step / max(1, self._hover_t0_total)
            t_eased = helpers.ease_out_cubic(t)
            if self._hover_end_fg and self._hover_start_fg:
                fg = helpers.mix_colors(self._hover_start_fg,
                                        self._hover_end_fg, t_eased)
                self.configure(fg_color=fg)
            if self._hover_end_text and self._hover_start_text:
                tx = helpers.mix_colors(self._hover_start_text,
                                        self._hover_end_text, t_eased)
                self.configure(text_color=tx)
        except Exception:
            return
        if self._hover_t0_step < self._hover_t0_total:
            self._hover_job = self.after(16, self._hover_tick)
        else:
            self._hover_job = None

    def _current_fg(self) -> str:
        try:
            c = self.cget("fg_color")
            return c if isinstance(c, str) else config.SURFACE
        except Exception:
            return config.SURFACE

    def _current_text(self) -> str:
        try:
            c = self.cget("text_color")
            return c if isinstance(c, str) else config.TEXT
        except Exception:
            return config.TEXT


# =============================================================================
# === GoldButton                                                             ===
# =============================================================================

class GoldButton(ctk.CTkButton, _HoverAnimMixin):
    """Primary gold-filled button.

    Use this for the main affirmative action on every screen —
    "ثبت", "شروع", "ذخیره" and the like.  Gold fill, dark text,
    subtle darkening on hover.
    """

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 44,
        lang: str = "fa",
        icon_name: Optional[str] = None,
        icon_size: int = 18,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        # Defaults — caller kwargs override.
        kwargs.setdefault("fg_color", config.GOLD)
        kwargs.setdefault("hover_color", config.GOLD_SOFT)
        kwargs.setdefault("text_color", config.MATTE_BLACK)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("border_color", config.GOLD)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="bold", lang=lang))
        if icon_name:
            img = _icons.icon(icon_name, icon_size, color=config.MATTE_BLACK)
            if img is not None:
                kwargs.setdefault("image", img)
                kwargs.setdefault("compound", "left" if lang == "en" else "right")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        # Hover anim targets
        self._hover_normal_fg = config.GOLD
        self._hover_target_fg = config.GOLD_BRIGHT
        self._hover_normal_text = config.MATTE_BLACK
        self._hover_target_text = config.MATTE_BLACK
        self._bind_hover()
        self._apply_rtl(lang)

    def _apply_rtl(self, lang: str) -> None:
        if _i18n.is_rtl(lang):
            try:
                self.configure(justify="right")
            except Exception:
                pass


# =============================================================================
# === GhostButton                                                            ===
# =============================================================================

class GhostButton(ctk.CTkButton, _HoverAnimMixin):
    """Outline-only gold button.  Transparent fill, gold border + text."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 44,
        lang: str = "fa",
        icon_name: Optional[str] = None,
        icon_size: int = 18,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("hover_color", config.SURFACE_HI)
        kwargs.setdefault("text_color", config.GOLD)
        kwargs.setdefault("border_width", 2)
        kwargs.setdefault("border_color", config.GOLD)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="bold", lang=lang))
        if icon_name:
            img = _icons.icon(icon_name, icon_size, color=config.GOLD)
            if img is not None:
                kwargs.setdefault("image", img)
                kwargs.setdefault("compound", "left" if lang == "en" else "right")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        self._hover_normal_fg = config.CHARCOAL
        self._hover_target_fg = config.SURFACE_HI
        self._hover_normal_text = config.GOLD
        self._hover_target_text = config.GOLD_BRIGHT
        self._bind_hover()
        self._apply_rtl(lang)

    def _apply_rtl(self, lang: str) -> None:
        if _i18n.is_rtl(lang):
            try:
                self.configure(justify="right")
            except Exception:
                pass


# =============================================================================
# === TextButton                                                            ===
# =============================================================================

class TextButton(ctk.CTkButton):
    """Text-only button.  No border, no fill.  Hover shows gold text."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 36,
        lang: str = "fa",
        font_size: int = config.FONT_SIZE_BODY,
        color: str = config.TEXT_DIM,
        hover_color: str = config.GOLD,
        underline_on_hover: bool = True,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("hover_color", config.SURFACE_HI)
        kwargs.setdefault("text_color", color)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_SM)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="normal", lang=lang))
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        self._base_color = color
        self._hover_color = hover_color
        self._underline_on_hover = underline_on_hover
        self._lang = lang
        try:
            self.bind("<Enter>", self._on_enter, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
        except Exception:
            pass

    def _on_enter(self, _evt: Any = None) -> None:
        try:
            self.configure(text_color=self._hover_color)
            if self._underline_on_hover:
                # Tk underline attribute on CTkFont
                f = self.cget("font")
                if hasattr(f, "configure"):
                    f.configure(underline=True)
        except Exception:
            pass

    def _on_leave(self, _evt: Any = None) -> None:
        try:
            self.configure(text_color=self._base_color)
            if self._underline_on_hover:
                f = self.cget("font")
                if hasattr(f, "configure"):
                    f.configure(underline=False)
        except Exception:
            pass


# =============================================================================
# === IconButton                                                            ===
# =============================================================================

class IconButton(ctk.CTkButton, _HoverAnimMixin):
    """Square icon-only button.  Gold hover, transparent base."""

    def __init__(
        self,
        master: Any = None,
        icon_name: str = "dots",
        command: Optional[Callable[[], Any]] = None,
        size: int = 40,
        lang: str = "fa",
        icon_size: Optional[int] = None,
        color: str = config.TEXT_DIM,
        hover_color: str = config.GOLD,
        **kwargs: Any,
    ) -> None:
        if icon_size is None:
            icon_size = int(size * 0.55)
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("hover_color", config.SURFACE_HI)
        kwargs.setdefault("text_color", color)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_MD)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("cursor", "hand2")
        img = _icons.icon(icon_name, icon_size, color=color)
        if img is not None:
            kwargs.setdefault("image", img)
            kwargs.setdefault("text", "")
        else:
            kwargs.setdefault("text", _icons.icon_glyph(icon_name))
        super().__init__(master, command=command, **kwargs)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._hover_color = hover_color
        self._base_color = color
        self._hover_normal_fg = config.CHARCOAL
        self._hover_target_fg = config.SURFACE_HI
        self._hover_normal_text = color
        self._hover_target_text = hover_color
        self._bind_hover()
        # Re-bind enter/leave to swap icon color
        try:
            self.bind("<Enter>", self._enter_swap, add="+")
            self.bind("<Leave>", self._leave_swap, add="+")
        except Exception:
            pass

    def _enter_swap(self, _evt: Any = None) -> None:
        img = _icons.icon(self._icon_name, self._icon_size,
                          color=self._hover_color)
        if img is not None:
            try:
                self.configure(image=img)
            except Exception:
                pass

    def _leave_swap(self, _evt: Any = None) -> None:
        img = _icons.icon(self._icon_name, self._icon_size,
                          color=self._base_color)
        if img is not None:
            try:
                self.configure(image=img)
            except Exception:
                pass


# =============================================================================
# === DangerButton & SuccessButton                                          ===
# =============================================================================

class DangerButton(ctk.CTkButton, _HoverAnimMixin):
    """Red filled button — destructive actions (delete, discard)."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 44,
        lang: str = "fa",
        icon_name: Optional[str] = None,
        icon_size: int = 18,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.DANGER)
        kwargs.setdefault("hover_color", config.DANGER_DIM)
        kwargs.setdefault("text_color", "#FFFFFF")
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="bold", lang=lang))
        if icon_name:
            img = _icons.icon(icon_name, icon_size, color="#FFFFFF")
            if img is not None:
                kwargs.setdefault("image", img)
                kwargs.setdefault("compound", "left" if lang == "en" else "right")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        self._hover_normal_fg = config.DANGER
        self._hover_target_fg = "#B04944"
        self._hover_normal_text = "#FFFFFF"
        self._hover_target_text = "#FFFFFF"
        self._bind_hover()


class SuccessButton(ctk.CTkButton, _HoverAnimMixin):
    """Green filled button — confirm/success actions."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 44,
        lang: str = "fa",
        icon_name: Optional[str] = None,
        icon_size: int = 18,
        font_size: int = config.FONT_SIZE_DEFAULT,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SUCCESS)
        kwargs.setdefault("hover_color", config.SUCCESS_DIM)
        kwargs.setdefault("text_color", config.MATTE_BLACK)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="bold", lang=lang))
        if icon_name:
            img = _icons.icon(icon_name, icon_size, color=config.MATTE_BLACK)
            if img is not None:
                kwargs.setdefault("image", img)
                kwargs.setdefault("compound", "left" if lang == "en" else "right")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        self._hover_normal_fg = config.SUCCESS
        self._hover_target_fg = "#92D492"
        self._hover_normal_text = config.MATTE_BLACK
        self._hover_target_text = config.MATTE_BLACK
        self._bind_hover()


# =============================================================================
# === PillButton                                                            ===
# =============================================================================

class PillButton(ctk.CTkButton, _HoverAnimMixin):
    """Fully rounded (RADIUS_PILL) gold button, slightly smaller than GoldButton."""

    def __init__(
        self,
        master: Any = None,
        text: str = "",
        command: Optional[Callable[[], Any]] = None,
        width: Optional[int] = None,
        height: int = 36,
        lang: str = "fa",
        icon_name: Optional[str] = None,
        icon_size: int = 16,
        font_size: int = config.FONT_SIZE_BODY,
        color: str = config.GOLD,
        text_color: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        if text_color is None:
            text_color = (config.MATTE_BLACK if color == config.GOLD
                          else config.TEXT)
        kwargs.setdefault("fg_color", color)
        kwargs.setdefault("hover_color", helpers.lighten_color(color, 0.15))
        kwargs.setdefault("text_color", text_color)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("font", _theme.theme.font(
            size=font_size, weight="bold", lang=lang))
        if icon_name:
            img = _icons.icon(icon_name, icon_size, color=text_color)
            if img is not None:
                kwargs.setdefault("image", img)
                kwargs.setdefault("compound", "left" if lang == "en" else "right")
        if width is not None:
            kwargs.setdefault("width", width)
        kwargs.setdefault("height", height)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, command=command, **kwargs)
        self._hover_normal_fg = color
        self._hover_target_fg = helpers.lighten_color(color, 0.18)
        self._hover_normal_text = text_color
        self._hover_target_text = text_color
        self._bind_hover()


# =============================================================================
# === FabButton                                                             ===
# =============================================================================

class FabButton(ctk.CTkButton, _HoverAnimMixin):
    """56×56 circular floating action button with gold gradient + shadow."""

    def __init__(
        self,
        master: Any = None,
        icon_name: str = "plus",
        command: Optional[Callable[[], Any]] = None,
        size: int = config.FAB_SIZE,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.GOLD)
        kwargs.setdefault("hover_color", config.GOLD_BRIGHT)
        kwargs.setdefault("text_color", config.MATTE_BLACK)
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("corner_radius", size // 2)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("cursor", "hand2")
        icon_size = int(size * 0.45)
        img = _icons.icon(icon_name, icon_size, color=config.MATTE_BLACK)
        if img is not None:
            kwargs.setdefault("image", img)
            kwargs.setdefault("text", "")
        else:
            kwargs.setdefault("text", _icons.icon_glyph(icon_name))
        super().__init__(master, command=command, **kwargs)
        # Approximate box-shadow with a thin gold ring on hover
        self._hover_normal_fg = config.GOLD
        self._hover_target_fg = config.GOLD_BRIGHT
        self._hover_normal_text = config.MATTE_BLACK
        self._hover_target_text = config.MATTE_BLACK
        self._bind_hover(duration_ms=config.ANIM_NORMAL)
        # Subtle press-scale
        try:
            self.bind("<ButtonPress-1>", self._on_press, add="+")
            self.bind("<ButtonRelease-1>", self._on_release, add="+")
        except Exception:
            pass

    def _on_press(self, _evt: Any = None) -> None:
        try:
            self.configure(border_width=2, border_color=config.GOLD_BRIGHT)
        except Exception:
            pass

    def _on_release(self, _evt: Any = None) -> None:
        try:
            self.configure(border_width=0)
        except Exception:
            pass


# =============================================================================
# === SegmentedButton                                                       ===
# =============================================================================

class SegmentedButton(ctk.CTkFrame):
    """Segmented control — 3-5 mutually exclusive options.

    Example
    -------
    >>> seg = SegmentedButton(parent, segments=["روز", "هفته", "ماه"],
    ...                       on_change=lambda v: print(v))
    >>> seg.pack(padx=12, pady=8)
    >>> seg.set("هفته")
    """

    def __init__(
        self,
        master: Any = None,
        segments: Sequence[str] = (),
        on_change: Optional[Callable[[str], Any]] = None,
        lang: str = "fa",
        height: int = 40,
        font_size: int = config.FONT_SIZE_BODY,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", config.SURFACE)
        kwargs.setdefault("corner_radius", config.RADIUS_PILL)
        kwargs.setdefault("height", height)
        super().__init__(master, **kwargs)
        self._segments: List[str] = list(segments)
        self._active: Optional[str] = None
        self._on_change = on_change
        self._lang = lang
        self._font_size = font_size
        self._buttons: List[ctk.CTkButton] = []
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._buttons = []
        for i, seg in enumerate(self._segments):
            btn = ctk.CTkButton(
                self,
                text=seg,
                command=lambda s=seg: self.set(s),
                fg_color="transparent",
                hover_color=config.SURFACE_HI,
                text_color=config.TEXT_DIM,
                corner_radius=config.RADIUS_PILL,
                height=self.cget("height") - 4,
                font=_theme.theme.font(
                    size=self._font_size, weight="normal", lang=self._lang),
                cursor="hand2",
            )
            # Equal-width segments
            btn.grid(row=0, column=i, sticky="nsew",
                     padx=2, pady=2)
            self.grid_columnconfigure(i, weight=1)
            self._buttons.append(btn)
        if self._active in self._segments:
            self._highlight(self._active)
        elif self._segments:
            self.set(self._segments[0])

    def _highlight(self, value: str) -> None:
        for i, btn in enumerate(self._buttons):
            if self._segments[i] == value:
                btn.configure(fg_color=config.GOLD,
                              text_color=config.MATTE_BLACK,
                              font=_theme.theme.font(
                                  size=self._font_size,
                                  weight="bold",
                                  lang=self._lang))
            else:
                btn.configure(fg_color="transparent",
                              text_color=config.TEXT_DIM,
                              font=_theme.theme.font(
                                  size=self._font_size,
                                  weight="normal",
                                  lang=self._lang))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def value(self) -> Optional[str]:
        return self._active

    def set(self, value: str) -> None:
        if value not in self._segments:
            return
        changed = self._active != value
        self._active = value
        self._highlight(value)
        if changed and self._on_change:
            try:
                self._on_change(value)
            except Exception:
                pass

    def set_segments(self, segments: Sequence[str]) -> None:
        """Replace the segment list and rebuild."""
        self._segments = list(segments)
        self._active = None
        self._build()

    def get(self) -> Optional[str]:
        return self._active


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    """Basic smoke test that all classes exist and are CTk subclasses."""
    classes = [GoldButton, GhostButton, TextButton, IconButton,
               DangerButton, SuccessButton, PillButton, FabButton,
               SegmentedButton]
    print(f"Buttons module: {len(classes)} classes registered.")
    for c in classes:
        if not issubclass(c, ctk.CTkBaseClass):
            print(f"  WARN: {c.__name__} not a CTkBaseClass subclass")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
