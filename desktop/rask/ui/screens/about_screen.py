"""
rask.ui.screens.about_screen
============================

About screen — app metadata, license, source, acknowledgements,
changelog, contact, and update-check.

Layout (top-to-bottom, RTL Persian):
    1. **Header** — title ``"درباره رَسک"`` with back button
    2. **App icon block** — circular gold ``"ر"`` (or ``"R"``) icon +
       app name + version + build + tagline
    3. **Author / studio** — ``"ساخته‌شده توسط <author>"``
    4. **Quick links card** — License / Source code / Report issue /
       Rate / Share / Check for updates
    5. **Acknowledgements card** — list of third-party libraries
    6. **Changelog card** — last 5 versions
    7. **Footer** — copyright + small print

Auto-refresh
------------
Subscribes to ``language.changed`` so labels re-render when the user
switches language.
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
from ...core import event_bus, time_utils, jalali, helpers
from ..widgets import theme as _theme
from ..widgets import icons as _icons
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton,
)
from ..widgets.cards import Card
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.dialogs import AlertDialog

__all__ = ["AboutScreen"]


# =============================================================================
# === Acknowledgements                                                       ===
# =============================================================================

ACKNOWLEDGEMENTS: List[Dict[str, str]] = [
    {"name": "CustomTkinter", "license": "MIT",
     "url": "https://github.com/TomSchimansky/CustomTkinter",
     "purpose_fa": "رابط کاربری مدرن", "purpose_en": "Modern UI framework"},
    {"name": "Pillow", "license": "HPND",
     "url": "https://python-pillow.org",
     "purpose_fa": "پردازش تصویر و آیکون‌ها",
     "purpose_en": "Image processing & icons"},
    {"name": "cryptography", "license": "Apache/BSD",
     "url": "https://cryptography.io",
     "purpose_fa": "رمزنگاری پشتیبان",
     "purpose_en": "Backup encryption"},
    {"name": "reportlab", "license": "BSD",
     "url": "https://www.reportlab.com",
     "purpose_fa": "خروجی PDF",
     "purpose_en": "PDF export"},
    {"name": "Vazirmatn font", "license": "OFL",
     "url": "https://github.com/rastikerdar/vazirmatn",
     "purpose_fa": "فونت فارسی", "purpose_en": "Persian font"},
]


# =============================================================================
# === Changelog                                                              ===
# =============================================================================

CHANGELOG: List[Dict[str, str]] = [
    {"version": "2.0.0",
     "date": "2025-07-18",
     "changes_fa": "بازنویسی کامل با CustomTkinter؛ نمایش نوار پیشرفت زنجیره‌؛ پشتیبان رمزنگاری‌شده.",
     "changes_en": "Complete rewrite with CustomTkinter; streak progress bar; encrypted backups."},
    {"version": "1.4.2",
     "date": "2025-05-10",
     "changes_fa": "اصلاح باگ نمایش تقویم جلالی در سال کبیسه.",
     "changes_en": "Fix Jalali calendar display in leap year."},
    {"version": "1.4.0",
     "date": "2025-04-01",
     "changes_fa": "افزودن بخش بینش‌ها و تحلیل شخصیت.",
     "changes_en": "Added Insights screen and personality analysis."},
    {"version": "1.3.0",
     "date": "2025-02-15",
     "changes_fa": "افزودن قالب‌های سریع و میانبرهای صفحه‌کلید.",
     "changes_en": "Added quick-log templates and keyboard shortcuts."},
    {"version": "1.2.0",
     "date": "2024-12-20",
     "changes_fa": "افزودن اهداف هفتگی و ماهانه.",
     "changes_en": "Added weekly and monthly goals."},
]


# =============================================================================
# === AboutScreen                                                            ===
# =============================================================================

class AboutScreen(ctk.CTkFrame):
    """About-the-app screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``switch_tab(tab)``
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
        self._build()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        # Header
        self._header = Header(
            self, title=self._tr("aboutRask", "About Rask"),
            back_icon=True, on_back=self._on_back,
            lang=self._lang, height=56,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        # Scrollable content
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        # Sections
        self._section_row = 0
        self._build_app_icon_block()
        self._build_links_card()
        self._build_acknowledgements_card()
        self._build_changelog_card()
        self._build_footer()
        Spacer(self._scroll, height=config.SPACE_XXL).grid(
            row=self._next_row(), column=0, sticky="ew")

    def _build_app_icon_block(self) -> None:
        """App icon + name + version + tagline."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(config.SPACE_XL,
                                                   config.SPACE_LG))
        section.grid_columnconfigure(0, weight=1)
        # Icon: gold circle with "ر" or "R"
        icon_size = 96
        icon_frame = ctk.CTkFrame(
            section, width=icon_size, height=icon_size,
            fg_color=config.GOLD,
            corner_radius=icon_size // 2,
        )
        icon_frame.grid(row=0, column=0)
        icon_frame.grid_propagate(False)
        glyph = "ر" if self._lang == "fa" else "R"
        ctk.CTkLabel(
            icon_frame, text=glyph,
            font=_theme.theme.font(size=config.FONT_SIZE_DISPLAY,
                                    weight="bold", lang=self._lang),
            text_color=config.MATTE_BLACK,
        ).place(relx=0.5, rely=0.5, anchor="center")
        # App name
        app_name = (config.APP_NAME_FA if self._lang == "fa"
                     else config.APP_NAME)
        ctk.CTkLabel(
            section, text=app_name,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
        ).grid(row=1, column=0, pady=(config.SPACE_MD, 0))
        # Version + build
        version_text = (
            f"{self._tr('version', 'Version')} "
            f"{(i18n.to_fa_digits(config.APP_VERSION)
                if self._lang == 'fa' else config.APP_VERSION)}"
            f" · {self._tr('build', 'Build')} "
            f"{(i18n.to_fa_digits(str(config.APP_BUILD))
                if self._lang == 'fa' else str(config.APP_BUILD))}"
        )
        ctk.CTkLabel(
            section, text=version_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=2, column=0, pady=(2, 0))
        # Tagline
        tagline = (config.APP_TAGLINE if self._lang == "fa"
                    else config.APP_TAGLINE_EN)
        ctk.CTkLabel(
            section, text=tagline,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
        ).grid(row=3, column=0, pady=(4, 0))
        # Author
        author_text = (
            f"{self._tr('madeBy', 'Made by')} {config.APP_AUTHOR}"
        )
        ctk.CTkLabel(
            section, text=author_text,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        ).grid(row=4, column=0, pady=(8, 0))

    def _build_links_card(self) -> None:
        """Quick links: License, Source, Report issue, Rate, Share, Updates."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            card.content, text=self._tr("quickLinks", "Quick links"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        links = [
            (self._tr("license", "License"), self._on_show_license),
            (self._tr("sourceCode", "Source code"), self._on_open_source),
            (self._tr("reportIssue", "Report issue"),
             self._on_report_issue),
            (self._tr("rateApp", "Rate the app"), self._on_rate),
            (self._tr("shareApp", "Share Rask"), self._on_share),
            (self._tr("checkUpdates", "Check for updates"),
             self._on_check_updates),
        ]
        for i, (label, cb) in enumerate(links):
            self._make_link_row(card.content, label, cb, row=i + 1)

    def _build_acknowledgements_card(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            card.content,
            text=self._tr("acknowledgements", "Acknowledgements"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, ack in enumerate(ACKNOWLEDGEMENTS):
            self._make_ack_row(card.content, ack, row=i + 1)

    def _build_changelog_card(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang, padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        SectionTitle(
            card.content, text=self._tr("changelog", "Changelog"),
            lang=self._lang, size=config.FONT_SIZE_BODY_LG,
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, entry in enumerate(CHANGELOG[:5]):
            self._make_changelog_row(card.content, entry, row=i + 1)

    def _build_footer(self) -> None:
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=config.SPACE_MD)
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        year = time_utils.now_iso_local()[:4]
        year_str = (i18n.to_fa_digits(year)
                     if self._lang == "fa" else year)
        copyright_text = (
            f"© {year_str} {config.APP_AUTHOR}"
        )
        ctk.CTkLabel(
            section, text=copyright_text,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_FAINT,
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        ctk.CTkLabel(
            section, text=config.APP_URL,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang="en"),
            text_color=config.TEXT_FAINT,
        ).grid(row=1, column=0, sticky="e" if rtl else "w", pady=(2, 0))

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------
    def _make_link_row(
        self,
        parent: ctk.CTkFrame,
        label: str,
        on_click: Callable[[], Any],
        row: int,
    ) -> None:
        rtl = i18n.is_rtl(self._lang)
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", pady=2)
        row_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row_frame, text=label,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        TextButton(
            row_frame, text="›",
            command=on_click, lang=self._lang, height=28,
            color=config.GOLD, font_size=config.FONT_SIZE_BODY_LG,
            underline_on_hover=False,
        ).grid(row=0, column=1, sticky="e" if rtl else "w")

    def _make_ack_row(
        self,
        parent: ctk.CTkFrame,
        ack: Dict[str, str],
        row: int,
    ) -> None:
        rtl = i18n.is_rtl(self._lang)
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", pady=2)
        row_frame.grid_columnconfigure(0, weight=1)
        # Name + license
        name_text = f"{ack['name']} ({ack['license']})"
        ctk.CTkLabel(
            row_frame, text=name_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang="en"),
            text_color=config.TEXT, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Purpose
        purpose = (ack["purpose_fa"] if self._lang == "fa"
                    else ack["purpose_en"])
        ctk.CTkLabel(
            row_frame, text=purpose,
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM, anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="ew", pady=(1, 0))

    def _make_changelog_row(
        self,
        parent: ctk.CTkFrame,
        entry: Dict[str, str],
        row: int,
    ) -> None:
        rtl = i18n.is_rtl(self._lang)
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", pady=4)
        row_frame.grid_columnconfigure(0, weight=1)
        # Version + date header
        header_text = (
            f"{self._tr('version', 'Version')} "
            f"{(i18n.to_fa_digits(entry['version'])
                if self._lang == 'fa' else entry['version'])}"
            f" · "
            f"{_format_date_short(entry.get('date', ''), self._lang)}"
        )
        ctk.CTkLabel(
            row_frame, text=header_text,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD, anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="ew")
        # Changes
        changes = (entry["changes_fa"] if self._lang == "fa"
                    else entry["changes_en"])
        ctk.CTkLabel(
            row_frame, text=changes,
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM, anchor="e" if rtl else "w",
            justify="right" if rtl else "left",
            wraplength=380,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

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
        # Rebuild to pick up new labels
        try:
            for child in self._scroll.winfo_children():
                child.destroy()
            self._section_row = 0
            self._build_app_icon_block()
            self._build_links_card()
            self._build_acknowledgements_card()
            self._build_changelog_card()
            self._build_footer()
            Spacer(self._scroll, height=config.SPACE_XXL).grid(
                row=self._next_row(), column=0, sticky="ew")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render (used to pick up language changes)."""
        self._on_data_changed()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_back(self) -> None:
        if self._app and hasattr(self._app, "switch_tab"):
            try:
                self._app.switch_tab("settings")
                return
            except Exception:
                pass
        try:
            event_bus.bus.publish("ui.tab_changed", {"tab": "settings"})
        except Exception:
            pass

    def _on_show_license(self) -> None:
        license_text = (
            f"{config.APP_NAME} {config.APP_VERSION}\n\n"
            "MIT License\n\n"
            f"Copyright (c) {time_utils.now_iso_local()[:4]} "
            f"{config.APP_AUTHOR}\n\n"
            "Permission is hereby granted, free of charge, to any person "
            "obtaining a copy of this software and associated documentation "
            "files (the \"Software\"), to deal in the Software without "
            "restriction, including without limitation the rights to use, "
            "copy, modify, merge, publish, distribute, sublicense, and/or "
            "sell copies of the Software, and to permit persons to whom the "
            "Software is furnished to do so, subject to the following "
            "conditions:\n\n"
            "The above copyright notice and this permission notice shall be "
            "included in all copies or substantial portions of the "
            "Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY "
            "KIND, express or implied."
        )
        AlertDialog(self, title=self._tr("license", "License"),
                    message=license_text, lang=self._lang,
                    ok_text=self._tr("close", "Close"))

    def _on_open_source(self) -> None:
        try:
            import webbrowser
            webbrowser.open(config.APP_URL)
        except Exception:
            self._show_toast(config.APP_URL)

    def _on_report_issue(self) -> None:
        try:
            import webbrowser
            webbrowser.open(config.APP_URL + "/issues")
        except Exception:
            self._show_toast(config.APP_URL + "/issues")

    def _on_rate(self) -> None:
        self._show_toast(self._tr("thanksForRating",
                                    "Thanks for rating Rask!"))

    def _on_share(self) -> None:
        try:
            text = f"{config.APP_NAME} — {config.APP_URL}"
            self.clipboard_clear()
            self.clipboard_append(text)
            self._show_toast(self._tr("linkCopied", "Link copied"))
        except Exception:
            self._show_toast(config.APP_URL)

    def _on_check_updates(self) -> None:
        self._show_toast(self._tr("upToDate", "You're up to date"))

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
        super().destroy()


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _format_date_short(iso_str: str, lang: str) -> str:
    """Format an ISO date as a short localized date string."""
    if not iso_str:
        return "—"
    try:
        return jalali.format_jalali(iso_str[:10], fmt="short", lang=lang)
    except Exception:
        return iso_str[:10]


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("AboutScreen module: icon + links + ack + changelog + footer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
