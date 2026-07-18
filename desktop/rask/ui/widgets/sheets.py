"""
rask.ui.widgets.sheets
======================

Bottom-sheet variants:

  * ``ActionSheet``  — list of action buttons (iOS-style)
  * ``PickerSheet``   — pick from list with checkmark on selected
  * ``FilterSheet``   — multi-select filter UI with apply/clear
  * ``SortSheet``     — pick sort field + direction
  * ``ShareSheet``    — share options (copy, save, open)
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme
from . import icons as _icons
from .dialogs import BottomSheet
from .buttons import GoldButton, GhostButton, IconButton
from .toggles import CheckBox

__all__ = ["ActionSheet", "PickerSheet", "FilterSheet",
           "SortSheet", "ShareSheet"]


# =============================================================================
# === ActionSheet                                                           ===
# =============================================================================

class ActionSheet(BottomSheet):
    """List of action buttons with optional cancel at the bottom."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        actions: Sequence[Tuple[str, Callable[[], Any]]] = (),
        cancel_text: str = "لغو",
        destructive: Optional[str] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._actions: List[Tuple[str, Callable[[], Any]]] = list(actions)
        self._cancel_text = cancel_text
        self._destructive = destructive
        kwargs.setdefault("height", 320)
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Actions list
        for label, callback in self._actions:
            color = config.DANGER if label == self._destructive else config.TEXT
            btn = ctk.CTkButton(
                self._content, text=label,
                command=lambda cb=callback: (cb(), self.close()),
                fg_color="transparent",
                hover_color=config.SURFACE,
                text_color=color,
                border_width=0,
                corner_radius=config.RADIUS_MD,
                height=46,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                anchor="e" if rtl else "w",
                cursor="hand2",
            )
            btn.pack(fill="x", pady=2)
        # Spacer + cancel
        ctk.CTkFrame(self._content, fg_color="transparent",
                      height=8).pack(fill="x")
        cancel = GhostButton(
            self._content, text=self._cancel_text,
            command=lambda: self.close(None),
            lang=self._lang, height=46,
            font_size=config.FONT_SIZE_BODY,
        )
        cancel.pack(fill="x", pady=(8, 0))


# =============================================================================
# === PickerSheet                                                           ===
# =============================================================================

class PickerSheet(BottomSheet):
    """Pick from list with checkmark on selected."""

    def __init__(
        self,
        master: Any = None,
        title: str = "",
        options: Sequence[str] = (),
        selected: Optional[str] = None,
        on_result: Optional[Callable[[Optional[str]], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._options: List[str] = list(options)
        self._selected = selected
        kwargs.setdefault("height", 360)
        super().__init__(master, title=title, lang=lang, **kwargs)
        if on_result:
            self.on_result(on_result)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        for opt in self._options:
            row = ctk.CTkFrame(self._content, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(0, weight=1)
            btn = ctk.CTkButton(
                row, text=opt,
                command=lambda o=opt: self.close(o),
                fg_color="transparent",
                hover_color=config.SURFACE,
                text_color=config.TEXT,
                border_width=0,
                corner_radius=config.RADIUS_MD,
                height=44,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                anchor="e" if rtl else "w",
                cursor="hand2",
            )
            btn.grid(row=0, column=0, sticky="ew")
            if opt == self._selected:
                check = ctk.CTkLabel(
                    row, text="✓",
                    font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                            weight="bold", lang="en"),
                    text_color=config.GOLD,
                )
                check.grid(row=0, column=1, padx=(0, 8) if rtl else (8, 0))


# =============================================================================
# === FilterSheet                                                           ===
# =============================================================================

class FilterSheet(BottomSheet):
    """Multi-select filter UI with apply / clear buttons."""

    def __init__(
        self,
        master: Any = None,
        title: str = "فیلتر",
        options: Sequence[str] = (),
        selected: Optional[Sequence[str]] = None,
        on_apply: Optional[Callable[[List[str]], Any]] = None,
        on_clear: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._options: List[str] = list(options)
        self._selected: List[str] = list(selected or [])
        self._on_apply = on_apply
        self._on_clear = on_clear
        kwargs.setdefault("height", 440)
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        self._checkboxes: List[CheckBox] = []
        for opt in self._options:
            cb = CheckBox(
                self._content, text=opt,
                on_change=lambda v, o=opt: self._toggle(o, v),
                lang=self._lang,
            )
            if opt in self._selected:
                cb.value = True
            cb.pack(anchor="e" if rtl else "w", padx=4, pady=4)
            self._checkboxes.append(cb)
        # Spacer
        ctk.CTkFrame(self._content, fg_color="transparent",
                      height=12).pack(fill="x")
        # Buttons
        btn_row = ctk.CTkFrame(self._content, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        clear = GhostButton(
            btn_row, text="پاک کردن" if self._lang == "fa" else "Clear",
            command=self._handle_clear,
            lang=self._lang, height=42,
        )
        apply_btn = GoldButton(
            btn_row, text="اعمال" if self._lang == "fa" else "Apply",
            command=self._handle_apply,
            lang=self._lang, height=42,
        )
        if rtl:
            apply_btn.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            clear.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        else:
            clear.grid(row=0, column=0, sticky="ew", padx=(4, 2))
            apply_btn.grid(row=0, column=1, sticky="ew", padx=(2, 4))

    def _toggle(self, opt: str, selected: bool) -> None:
        if selected:
            if opt not in self._selected:
                self._selected.append(opt)
        else:
            if opt in self._selected:
                self._selected.remove(opt)

    def _handle_apply(self) -> None:
        if self._on_apply:
            try:
                self._on_apply(list(self._selected))
            except Exception:
                pass
        self.close(self._selected)

    def _handle_clear(self) -> None:
        self._selected = []
        for cb in self._checkboxes:
            cb.value = False
        if self._on_clear:
            try:
                self._on_clear()
            except Exception:
                pass


# =============================================================================
# === SortSheet                                                             ===
# =============================================================================

class SortSheet(BottomSheet):
    """Pick sort field + direction (ascending / descending)."""

    def __init__(
        self,
        master: Any = None,
        title: str = "مرتب‌سازی",
        fields: Sequence[str] = (),
        initial_field: Optional[str] = None,
        initial_descending: bool = False,
        on_result: Optional[Callable[[str, bool], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._fields: List[str] = list(fields)
        self._current_field = initial_field or (fields[0] if fields else None)
        self._descending = initial_descending
        self._on_result = on_result
        kwargs.setdefault("height", 380)
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        # Field list
        for field in self._fields:
            btn = ctk.CTkButton(
                self._content, text=field,
                command=lambda f=field: self._set_field(f),
                fg_color=config.GOLD if field == self._current_field
                          else "transparent",
                hover_color=config.SURFACE,
                text_color=(config.MATTE_BLACK
                             if field == self._current_field else config.TEXT),
                border_width=0,
                corner_radius=config.RADIUS_MD,
                height=42,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="bold"
                                        if field == self._current_field
                                        else "normal", lang=self._lang),
                anchor="e" if rtl else "w",
                cursor="hand2",
            )
            btn.pack(fill="x", pady=2)
        # Direction toggle
        ctk.CTkFrame(self._content, fg_color="transparent",
                      height=12).pack(fill="x")
        dir_row = ctk.CTkFrame(self._content, fg_color="transparent")
        dir_row.pack(fill="x", pady=(8, 0))
        from .buttons import SegmentedButton
        asc_text = "صعودی" if self._lang == "fa" else "Ascending"
        desc_text = "نزولی" if self._lang == "fa" else "Descending"
        seg = SegmentedButton(
            dir_row, segments=[asc_text, desc_text],
            on_change=self._set_direction,
            lang=self._lang, height=36,
        )
        seg.set(desc_text if self._descending else asc_text)
        seg.pack(fill="x")
        # Apply button
        apply_btn = GoldButton(
            self._content,
            text="اعمال" if self._lang == "fa" else "Apply",
            command=self._handle_apply,
            lang=self._lang, height=42,
        )
        apply_btn.pack(fill="x", pady=(16, 0))

    def _set_field(self, field: str) -> None:
        self._current_field = field
        self._build_content()  # rebuild to update highlight

    def _set_direction(self, val: str) -> None:
        asc_text = "صعودی" if self._lang == "fa" else "Ascending"
        self._descending = (val != asc_text)

    def _handle_apply(self) -> None:
        if self._on_result and self._current_field:
            try:
                self._on_result(self._current_field, self._descending)
            except Exception:
                pass
        self.close((self._current_field, self._descending))


# =============================================================================
# === ShareSheet                                                            ===
# =============================================================================

class ShareSheet(BottomSheet):
    """Share options — copy, save, open in app."""

    def __init__(
        self,
        master: Any = None,
        title: str = "اشتراک‌گذاری",
        on_copy: Optional[Callable[[], Any]] = None,
        on_save: Optional[Callable[[], Any]] = None,
        on_open: Optional[Callable[[], Any]] = None,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        self._on_copy = on_copy
        self._on_save = on_save
        self._on_open = on_open
        kwargs.setdefault("height", 320)
        super().__init__(master, title=title, lang=lang, **kwargs)

    def _build_content(self) -> None:
        rtl = i18n.is_rtl(self._lang)
        options = [
            ("copy", "کپی" if self._lang == "fa" else "Copy", self._on_copy),
            ("save", "ذخیره" if self._lang == "fa" else "Save", self._on_save),
            ("open", "باز کردن" if self._lang == "fa" else "Open", self._on_open),
        ]
        for icon_name, label, cb in options:
            row = ctk.CTkFrame(self._content, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(1, weight=1)
            icon = ctk.CTkLabel(row, text="", width=28, height=28,
                                 fg_color="transparent")
            img = _icons.icon(icon_name, 22, color=config.GOLD)
            if img is not None:
                icon.configure(image=img)
            else:
                icon.configure(text=_icons.icon_glyph(icon_name),
                                text_color=config.GOLD)
            icon.grid(row=0, column=0 if not rtl else 2,
                       padx=4 if rtl else (12, 4))
            btn = ctk.CTkButton(
                row, text=label,
                command=lambda c=cb: (c() if c else None, self.close()),
                fg_color="transparent", hover_color=config.SURFACE,
                text_color=config.TEXT, border_width=0,
                corner_radius=config.RADIUS_MD, height=46,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                anchor="e" if rtl else "w",
                cursor="hand2",
            )
            btn.grid(row=0, column=1, sticky="ew")


def _self_test() -> int:
    classes = [ActionSheet, PickerSheet, FilterSheet, SortSheet, ShareSheet]
    print(f"Sheets module: {len(classes)} classes registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
