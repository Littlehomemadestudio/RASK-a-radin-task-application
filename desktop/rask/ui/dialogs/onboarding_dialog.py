"""
rask.ui.dialogs.onboarding_dialog
=================================

Post-install onboarding dialog shown on first launch.

A multi-page modal that:
  * Welcomes the user with 2-3 friendly intro slides
  * Asks for language preference (Persian default)
  * Asks for theme preference (Dark default)
  * Optionally asks for the user's name
  * Optionally offers a PIN setup shortcut
  * Has a "Skip" button (uses defaults)
  * Has a "Start using Rask" button to finish

Pages
-----
  1. Welcome — 3-slide mini-carousel using
     :data:`config.ONBOARDING_SLIDES` (same slides as the splash
     onboarding screen, but presented inside a modal dialog for
     post-install context).
  2. Preferences — language + theme pickers + optional name.
  3. Security (optional) — PIN setup shortcut, or "skip for now".

Mirrors the post-install onboarding flow that appears on the first
launch of the desktop app.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ... import i18n
from ...core import helpers
from ...services import settings_service
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.dialogs import BaseDialog
from ..widgets.buttons import GoldButton, GhostButton, TextButton
from ..widgets.inputs import GoldEntry
from ..widgets.toggles import SegmentedControl
from ..widgets.dividers import Divider, SectionTitle
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.toasts import Toast
from .pin_setup_dialog import PinSetupDialog

__all__ = ["OnboardingDialog"]


# =============================================================================
# === Pages                                                                  ===
# =============================================================================

PAGE_WELCOME = "welcome"
PAGE_PREFS = "prefs"
PAGE_SECURITY = "security"


# =============================================================================
# === Slide illustration (simplified circular badge with icon)               ===
# =============================================================================

class _SlideIllustration(ctk.CTkFrame):
    """Circular badge with an icon for an onboarding slide."""

    def __init__(
        self,
        master: Any,
        icon_name: str = "ring",
        accent: str = config.GOLD,
        size: int = 120,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("width", size + 20)
        kwargs.setdefault("height", size + 20)
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        # Outer ring
        ring = ctk.CTkFrame(
            self, width=size + 16, height=size + 16,
            fg_color="transparent",
            border_width=2, border_color=accent,
            corner_radius=(size + 16) // 2,
        )
        ring.grid(row=0, column=0)
        # Inner circle
        inner = ctk.CTkFrame(
            self, width=size, height=size,
            fg_color=config.SURFACE,
            border_width=2, border_color=accent,
            corner_radius=size // 2,
        )
        inner.grid(row=0, column=0)
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=1)
        icon_lbl = ctk.CTkLabel(inner, text="")
        icon_lbl.grid(row=0, column=0)
        img = _icons.icon(icon_name, size // 2, color=accent)
        if img is not None:
            icon_lbl.configure(image=img)
        else:
            icon_lbl.configure(
                text=_icons.icon_glyph(icon_name),
                text_color=accent,
                font=_theme.theme.font(size=size // 2, weight="bold",
                                         lang="en"))


# =============================================================================
# === OnboardingDialog                                                       ===
# =============================================================================

class OnboardingDialog(BaseDialog):
    """Multi-page post-install onboarding modal.

    Parameters
    ----------
    master
        Parent widget.
    lang
        UI language (initial).
    on_result
        Callback receiving ``{"action": "completed",
        "language": str, "theme": str, "user_name": str,
        "pin_set": bool}``.
    """

    def __init__(
        self,
        master: Any,
        *,
        lang: str = "fa",
        on_result: Optional[Callable[[Optional[Dict[str, Any]]], Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._page = PAGE_WELCOME
        self._slide_index = 0
        self._language = lang or config.DEFAULT_LANG
        self._theme = config.DEFAULT_THEME
        self._user_name = ""
        self._pin_set = False
        self._pin_dlg = None
        kwargs.setdefault("height", 580)
        kwargs.setdefault("width", 460)
        kwargs.setdefault("close_on_overlay", False)
        kwargs.setdefault("close_on_esc", False)
        super().__init__(
            master, title="", lang=lang, **kwargs,
        )
        if on_result:
            self.on_result(on_result)

    # ------------------------------------------------------------------
    def _build_content(self) -> None:
        # Container for the current page
        self._page_frame = ctk.CTkFrame(self._content, fg_color="transparent")
        self._page_frame.pack(fill="both", expand=True)
        self._page_frame.grid_columnconfigure(0, weight=1)
        self._page_frame.grid_rowconfigure(0, weight=1)
        # Footer (page indicator + Skip / Next buttons)
        footer = ctk.CTkFrame(self._content, fg_color="transparent")
        footer.pack(fill="x", pady=(8, 0))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=0)
        # Skip button (top of footer)
        self._skip_btn = TextButton(
            footer,
            text=(i18n.t("skip", self._lang)
                   if i18n.t("skip", self._lang) != "skip"
                   else "رد شدن"),
            command=self._on_skip,
            lang=self._lang, height=38,
            color=config.TEXT_DIM, hover_color=config.GOLD,
        )
        self._skip_btn.grid(row=0, column=0, sticky="w")
        # Next / Start button
        self._next_btn = GoldButton(
            footer,
            text=(i18n.t("next", self._lang)
                   if i18n.t("next", self._lang) != "next"
                   else "بعدی"),
            command=self._on_next,
            lang=self._lang, height=42,
            icon_name="arrow_left", icon_size=14,
            width=120,
        )
        self._next_btn.grid(row=0, column=1, sticky="e", padx=4)
        # Render the initial page
        self._render_page()

    # ------------------------------------------------------------------
    def _clear_page_frame(self) -> None:
        for child in self._page_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _render_page(self) -> None:
        self._clear_page_frame()
        if self._page == PAGE_WELCOME:
            self._render_welcome_page()
        elif self._page == PAGE_PREFS:
            self._render_prefs_page()
        elif self._page == PAGE_SECURITY:
            self._render_security_page()
        # Update next button label
        try:
            if self._page == PAGE_SECURITY:
                self._next_btn.configure(
                    text=(i18n.t("start", self._lang)
                           if i18n.t("start", self._lang) != "start"
                           else "شروع"),
                    icon_name="check")
            else:
                self._next_btn.configure(
                    text=(i18n.t("next", self._lang)
                           if i18n.t("next", self._lang) != "next"
                           else "بعدی"),
                    icon_name="arrow_left")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Page 1: Welcome carousel
    # ------------------------------------------------------------------
    def _render_welcome_page(self) -> None:
        page = ctk.CTkFrame(self._page_frame, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        # Slide content
        slides = config.ONBOARDING_SLIDES
        if self._slide_index >= len(slides):
            self._slide_index = 0
        slide = slides[self._slide_index]
        title = (slide.get("title_fa") if self._lang == "fa"
                  else slide.get("title_en", ""))
        body = (slide.get("body_fa") if self._lang == "fa"
                 else slide.get("body_en", ""))
        accent = slide.get("accent", config.GOLD)
        icon_name = slide.get("icon", "ring")
        # Illustration
        ill = _SlideIllustration(
            page, icon_name=icon_name, accent=accent, size=140,
        )
        ill.grid(row=0, column=0, pady=(8, 12))
        # Title
        ctk.CTkLabel(
            page, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            wraplength=380, justify="center",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        # Body
        ctk.CTkLabel(
            page, text=body,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            wraplength=380, justify="center",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 12))
        # Progress dots
        dots_row = ctk.CTkFrame(page, fg_color="transparent")
        dots_row.grid(row=3, column=0, pady=(0, 8))
        for i in range(len(slides)):
            is_active = (i == self._slide_index)
            dot = ctk.CTkFrame(
                dots_row,
                width=(24 if is_active else 8), height=8,
                fg_color=config.GOLD if is_active else config.TEXT_FAINT,
                corner_radius=config.RADIUS_PILL,
            )
            dot.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Page 2: Preferences
    # ------------------------------------------------------------------
    def _render_prefs_page(self) -> None:
        page = ctk.CTkFrame(self._page_frame, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        # Title
        ctk.CTkLabel(
            page,
            text=("تنظیمات اولیه" if self._lang == "fa"
                    else "Initial preferences"),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=0, column=0, pady=(8, 12))
        # Language picker
        SectionTitle(
            page,
            text=(i18n.t("language", self._lang)
                   if i18n.t("language", self._lang) != "language"
                   else "زبان"),
            lang=self._lang,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 4))
        lang_options = ["فارسی", "English"]
        self._lang_seg = SegmentedControl(
            page, values=lang_options,
            on_change=lambda v: self._on_lang_change(v, lang_options),
            lang=self._lang, height=38,
        )
        # Set initial selection
        initial_lang_label = "فارسی" if self._language == "fa" else "English"
        self._lang_seg.set(initial_lang_label)
        self._lang_seg.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        # Theme picker
        SectionTitle(
            page,
            text=(i18n.t("theme", self._lang)
                   if i18n.t("theme", self._lang) != "theme"
                   else "پوسته"),
            lang=self._lang,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 4))
        theme_options = [
            (i18n.t("darkTheme", self._lang)
              if i18n.t("darkTheme", self._lang) != "darkTheme"
              else "تیره"),
            (i18n.t("lightTheme", self._lang)
              if i18n.t("lightTheme", self._lang) != "lightTheme"
              else "روشن"),
            (i18n.t("systemTheme", self._lang)
              if i18n.t("systemTheme", self._lang) != "systemTheme"
              else "همراه سیستم"),
        ]
        self._theme_seg = SegmentedControl(
            page, values=theme_options,
            on_change=lambda v: self._on_theme_change(v, theme_options),
            lang=self._lang, height=38,
        )
        # Set initial selection
        initial_theme_label = {
            "dark": theme_options[0],
            "light": theme_options[1],
            "system": theme_options[2],
        }.get(self._theme, theme_options[0])
        self._theme_seg.set(initial_theme_label)
        self._theme_seg.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        # User name (optional)
        SectionTitle(
            page,
            text=("نام (اختیاری)" if self._lang == "fa"
                    else "Name (optional)"),
            lang=self._lang,
        ).grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self._name_entry = GoldEntry(
            page, lang=self._lang, height=42,
            placeholder=("نامت را وارد کن" if self._lang == "fa"
                          else "Enter your name"),
        )
        self._name_entry.value = self._user_name
        self._name_entry.grid(row=6, column=0, sticky="ew", pady=(0, 8))

    # ------------------------------------------------------------------
    # Page 3: Security (optional PIN setup)
    # ------------------------------------------------------------------
    def _render_security_page(self) -> None:
        page = ctk.CTkFrame(self._page_frame, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        # Title
        ctk.CTkLabel(
            page,
            text=("حریم خصوصی" if self._lang == "fa" else "Privacy"),
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=0, column=0, pady=(8, 8))
        # Description
        ctk.CTkLabel(
            page,
            text=("برای حفظ حریم خصوصی می‌توانی یک پین ۴ رقمی تنظیم کنی. "
                   "این پین برای باز کردن قفل برنامه استفاده می‌شود."
                    if self._lang == "fa"
                    else "For privacy you can set a 4-digit PIN to "
                         "unlock the app."),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT,
            wraplength=380, justify="center",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 16))
        # Illustration
        ill = _SlideIllustration(
            page, icon_name="shield", accent=config.INFO, size=100,
        )
        ill.grid(row=2, column=0, pady=(0, 12))
        # PIN setup button
        self._set_pin_btn = GoldButton(
            page,
            text=(i18n.t("setPin", self._lang)
                   if i18n.t("setPin", self._lang) != "setPin"
                   else "تنظیم پین"),
            command=self._open_pin_setup,
            lang=self._lang, height=46,
            icon_name="lock", icon_size=16,
        )
        self._set_pin_btn.grid(row=3, column=0, sticky="ew", padx=40,
                                  pady=(0, 8))
        # Status label
        self._pin_status_label = ctk.CTkLabel(
            page, text="",
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="bold", lang=self._lang),
            text_color=config.SUCCESS,
        )
        self._pin_status_label.grid(row=4, column=0, pady=(0, 8))
        if self._pin_set:
            self._pin_status_label.configure(
                text=("پین تنظیم شد ✓" if self._lang == "fa"
                       else "PIN set ✓"))
        # "Skip for now" hint
        ctk.CTkLabel(
            page,
            text=("می‌توانی بعداً از تنظیمات تنظیم کنی" if self._lang == "fa"
                    else "You can set this later in Settings"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        ).grid(row=5, column=0, pady=(0, 8))

    # ------------------------------------------------------------------
    # Page navigation
    # ------------------------------------------------------------------
    def _on_next(self) -> None:
        if self._page == PAGE_WELCOME:
            # Advance slide; if last slide, go to prefs page
            slides = config.ONBOARDING_SLIDES
            if self._slide_index < len(slides) - 1:
                self._slide_index += 1
                self._render_page()
            else:
                self._page = PAGE_PREFS
                self._render_page()
        elif self._page == PAGE_PREFS:
            # Save user_name from the entry
            try:
                self._user_name = self._name_entry.value.strip()
            except Exception:
                pass
            self._page = PAGE_SECURITY
            self._render_page()
        elif self._page == PAGE_SECURITY:
            self._finish()

    def _on_skip(self) -> None:
        # Skip all remaining pages — finish immediately with defaults
        self._finish()

    def _finish(self) -> None:
        # Persist settings
        try:
            settings_service.set_language(self._language)
        except Exception:
            pass
        try:
            settings_service.set_theme(self._theme)
        except Exception:
            pass
        if self._user_name:
            try:
                settings_service.set_user_name(self._user_name)
            except Exception:
                pass
        try:
            settings_service.set_onboarded(True)
            settings_service.clear_first_run()
        except Exception:
            pass
        try:
            i18n.set_language(self._language)
        except Exception:
            pass
        try:
            Toast.show(
                self,
                (i18n.t("welcome", self._language)
                  if i18n.t("welcome", self._language) != "welcome"
                  else "خوش آمدی"),
                kind="success", lang=self._language,
            )
        except Exception:
            pass
        self.close({
            "action": "completed",
            "language": self._language,
            "theme": self._theme,
            "user_name": self._user_name,
            "pin_set": self._pin_set,
        })

    # ------------------------------------------------------------------
    def _on_lang_change(self, label: str, labels: List[str]) -> None:
        # labels = ["فارسی", "English"]
        if label == labels[0]:
            self._language = "fa"
        else:
            self._language = "en"
        # Update the dialog's lang so subsequent pages use the new lang.
        self._lang = self._language
        try:
            i18n.set_language(self._language)
        except Exception:
            pass

    def _on_theme_change(self, label: str, labels: List[str]) -> None:
        # labels = [dark, light, system]
        if label == labels[0]:
            self._theme = "dark"
        elif label == labels[1]:
            self._theme = "light"
        elif label == labels[2]:
            self._theme = "system"

    # ------------------------------------------------------------------
    def _open_pin_setup(self) -> None:
        try:
            self._pin_dlg = PinSetupDialog(
                self, mode="setup",
                lang=self._lang,
                on_result=self._on_pin_setup_done,
            )
        except Exception:
            pass

    def _on_pin_setup_done(self, result: Optional[Dict[str, Any]]) -> None:
        if not result:
            return
        if result.get("action") == "set":
            self._pin_set = True
            try:
                self._pin_status_label.configure(
                    text=("پین تنظیم شد ✓" if self._lang == "fa"
                           else "PIN set ✓"),
                    text_color=config.SUCCESS)
            except Exception:
                pass


def _self_test() -> int:
    print("onboarding_dialog module: 1 class (OnboardingDialog)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
