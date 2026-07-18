"""modals_extra.py — Additional modal dialogs for Rask.

Extends modals.py with more specialized modals:
  - CategoryModal         — create / edit / delete custom categories
  - BackupManagerModal    — list, restore, delete saved backups
  - RemindersModal        — configure daily reminders
  - RecurringListModal    — view / edit / delete recurring rules
  - ActivityDetailModal   — read-only view of activity details
  - AboutModal            — extended about dialog with credits + licenses
  - OnboardingExtendedModal — 5-slide onboarding (extends original 3-slide)
  - StatisticsDetailModal — detailed stats drill-down for a specific metric
  - ExportOptionsModal    — choose export format and options
  - BulkEditModal         — bulk edit multiple activities
  - HelpModal             — general help / FAQ
  - ThemeModal            — theme customization (font size, accent color)
  - PrivacyModal          — privacy policy / data usage explanation
  - ChangelogModal        — version changelog
  - FeedbackModal         — feedback / contact form (offline)
"""
from __future__ import annotations
import datetime as _dt
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from . import config
from . import database
from . import crypto
from . import exporters
from . import recurring
from . import icons
from .i18n import t, to_fa_digits
from . import widgets
from .widgets import (
    GoldButton, IconButton, Chip, Card, Field, TextArea, Switch, Slider,
    Modal, SegmentedControl, get_font, section_header,
)
from .widgets_extra import (
    ColorPicker, NumberStepper, DatePicker, Dropdown, ToggleGroup,
    MultiSelectChips, ConfirmDialog, AlertDialog, ProgressDialog,
    PillButtonGroup, IconBadge, ProgressRingWithText, ListItem, InfoRow,
    StatusIndicator,
)
from .date_utils import today_iso, now_iso, fmt_date, fmt_human


# =====================================================================
# === CATEGORY MODAL (desktop-only) ===
# =====================================================================
class CategoryModal(Modal):
    """Create, edit, or delete custom categories."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None,
                 category: Optional[dict] = None):
        self._lang = lang
        self._on_saved = on_saved
        self._category = category
        self._selected_color = category["color"] if category else config.GOLD
        title = t("editCategory", lang) if category else t("addCategory", lang)
        super().__init__(root, title=title, lang=lang, height=560)
        self._build()

    def _build(self):
        lang = self._lang
        # Name (English)
        tk.Label(self.content, text=f"{t('categoryName', lang)} (EN)", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._name_en = Field(self.content, placeholder="Focus", lang=lang)
        self._name_en.pack(fill="x", pady=(0, 12))
        # Name (Persian)
        tk.Label(self.content, text=f"{t('categoryName', lang)} (FA)", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._name_fa = Field(self.content, placeholder="تمرکز", lang=lang)
        self._name_fa.pack(fill="x", pady=(0, 12))
        # Key (unique identifier)
        tk.Label(self.content, text="Key", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._key_entry = Field(self.content, placeholder="FOCUS", lang=lang)
        self._key_entry.pack(fill="x", pady=(0, 12))
        # Icon picker (preset)
        tk.Label(self.content, text=t("categoryIcon", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        icon_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        icon_frame.pack(fill="x", pady=(0, 12))
        preset_icons = ["ring", "book", "briefcase", "heart", "palette",
                         "users", "moon", "code", "music", "camera",
                         "video", "phone", "globe", "map"]
        self._selected_icon = preset_icons[0]
        self._icon_chips: list = []
        for i, icon_name in enumerate(preset_icons):
            chip = Chip(icon_frame, text=icon_name, selected=(i == 0),
                         command=lambda _i=icon_name: self._on_icon(_i), lang=lang)
            chip.pack(side="left", padx=(0, 4))
            self._icon_chips.append((chip, icon_name))
        # Color picker button
        tk.Label(self.content, text=t("categoryColor", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._color_btn = GoldButton(self.content, text=self._selected_color,
                                       command=self._open_color_picker, kind="ghost",
                                       full_width=True)
        self._color_btn.pack(fill="x", pady=(0, 16))
        # Pre-fill if editing
        if self._category:
            self._name_en.set(self._category.get("name_en", ""))
            self._name_fa.set(self._category.get("name_fa", ""))
            self._key_entry.set(self._category.get("key", ""))
            self._selected_icon = self._category.get("icon", "ring")
        # Cancel / Save buttons
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        if self._category:
            GoldButton(btn_frame, text=t("delete", lang), command=self._on_delete,
                        kind="danger", size="sm", full_width=True).pack(fill="x", pady=(0, 8))
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _on_icon(self, icon_name: str):
        self._selected_icon = icon_name
        for chip, name in self._icon_chips:
            chip.set_selected(name == icon_name)

    def _open_color_picker(self):
        def on_pick(color):
            self._selected_color = color
            self._color_btn.set_text(color)
        ColorPicker(self, self._lang, on_pick=on_pick,
                     initial_color=self._selected_color)

    def _on_save(self):
        lang = self._lang
        name_en = self._name_en.get().strip()
        name_fa = self._name_fa.get().strip()
        key = self._key_entry.get().strip().upper()
        if not name_en or not name_fa or not key:
            widgets.Toast(self, "All fields required", kind="danger")
            return
        category = {
            "key": key,
            "name_en": name_en,
            "name_fa": name_fa,
            "icon": self._selected_icon,
            "color": self._selected_color,
            "order_index": 99,
        }
        if self._category:
            category["id"] = self._category["id"]
        try:
            database.upsert_category(category)
            widgets.Toast(self, t("saved", lang), kind="success")
            self.close()
            if self._on_saved:
                self._on_saved()
        except Exception as e:
            widgets.Toast(self, str(e), kind="danger")

    def _on_delete(self):
        lang = self._lang
        if not self._category:
            return
        if messagebox.askyesno(config.APP_NAME, t("confirmDeleteCategory", lang)):
            database.delete_category(self._category["id"])
            widgets.Toast(self, t("toastDeleted", lang), kind="info")
            self.close()
            if self._on_saved:
                self._on_saved()


# =====================================================================
# === RECURRING LIST MODAL ===
# =====================================================================
class RecurringListModal(Modal):
    """View, edit, and delete recurring rules."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None):
        self._lang = lang
        self._on_saved = on_saved
        super().__init__(root, title=t("recurringActivities", lang), lang=lang, height=620)
        self._build()

    def _build(self):
        lang = self._lang
        # List of recurring rules
        self._list_frame = widgets.ScrollableFrame(self.content, bg=config.MATTE_BLACK)
        self._list_frame.pack(fill="both", expand=True, pady=(0, 12))
        # Add new button
        GoldButton(self.content, text=t("addRecurring", lang),
                    command=self._on_add, kind="gold",
                    full_width=True).pack(fill="x", side="bottom")
        self._render_list()

    def _render_list(self):
        self._list_frame.clear()
        lang = self._lang
        rules = recurring.list_all()
        if not rules:
            tk.Label(self._list_frame.inner, text=t("noRecurring", lang),
                     bg=config.MATTE_BLACK, fg=config.TEXT_FAINT,
                     font=get_font(13)).pack(pady=24)
            return
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        for r in rules:
            card = Card(self._list_frame.inner, padding=12)
            card.pack(fill="x", pady=4)
            # Title row
            top = tk.Frame(card, bg=config.CHARCOAL)
            top.pack(fill="x")
            tk.Label(top, text=r["title"], bg=config.CHARCOAL, fg=config.TEXT,
                     font=get_font(14, "bold")).pack(side="left")
            IconButton(top, "trash",
                        command=lambda _r=r: self._on_delete(_r),
                        size=28, icon_size=14,
                        color=config.TEXT_DIM, hover_color=config.DANGER).pack(side="right")
            # Pattern + duration
            pat_label = recurring.format_pattern(r, lang)
            dur = fmt_human(int(r.get("duration_sec", 0) or 0), lang)
            cat = cat_map.get(r.get("category_id"))
            cat_name = (cat["name_fa"] if lang == "fa" and cat else
                        cat["name_en"] if cat else "—")
            tk.Label(card, text=f"{pat_label} · {dur} · {cat_name}",
                     bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(11)).pack(anchor="w", pady=(4, 0))
            # Next run
            next_run = r.get("next_run_iso", "")
            if next_run:
                tk.Label(card, text=f"⏰ {next_run}", bg=config.CHARCOAL,
                         fg=config.GOLD, font=get_font(10)).pack(anchor="w", pady=(2, 0))

    def _on_add(self):
        from .ui.modals import RecurringModal
        def on_saved():
            self._render_list()
            if self._on_saved:
                self._on_saved()
        RecurringModal(self.master, self._lang, on_saved)

    def _on_delete(self, rule: dict):
        lang = self._lang
        if messagebox.askyesno(config.APP_NAME, t("confirmDeleteActivity", lang)):
            recurring.delete_recurring(rule["id"])
            self._render_list()
            if self._on_saved:
                self._on_saved()


# =====================================================================
# === ACTIVITY DETAIL MODAL (read-only) ===
# =====================================================================
class ActivityDetailModal(Modal):
    """Read-only view of activity details."""

    def __init__(self, root, activity: dict, lang: str = "fa"):
        self._lang = lang
        self._activity = activity
        super().__init__(root, title=t("activityTitle", lang), lang=lang, height=520)
        self._build()

    def _build(self):
        lang = self._lang
        a = self._activity
        # Title
        tk.Label(self.content, text=a.get("title", ""), bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(18, "bold"),
                 wraplength=400).pack(anchor="w", pady=(0, 12))
        # Category badge
        cat = database.category_by_id(a.get("category_id")) if a.get("category_id") else None
        cat_name = ""
        if cat:
            cat_name = cat["name_fa"] if lang == "fa" else cat["name_en"]
        if cat_name:
            tk.Label(self.content, text=cat_name, bg=cat["color"] if cat else config.SURFACE,
                     fg=config.MATTE_BLACK, font=get_font(11, "bold"),
                     padx=8, pady=2).pack(anchor="w", pady=(0, 12))
        # Info rows
        from .date_utils import fmt_relative, fmt_human, fmt_date, parse_date
        InfoRow(self.content, label=t("activityDate", lang),
                value=fmt_date(parse_date(a.get("date_iso", "")), lang)).pack(fill="x")
        InfoRow(self.content, label=t("activityDuration", lang),
                value=fmt_human(int(a.get("duration_sec", 0)), lang)).pack(fill="x")
        InfoRow(self.content, label=t("activityKind", lang),
                value=t(f"kind{a.get('kind', 'manual').capitalize()}", lang)).pack(fill="x")
        if a.get("start_iso"):
            InfoRow(self.content, label=t("activityStartTime", lang),
                    value=a["start_iso"][11:19]).pack(fill="x")
        if a.get("end_iso"):
            InfoRow(self.content, label=t("activityEndTime", lang),
                    value=a["end_iso"][11:19]).pack(fill="x")
        InfoRow(self.content, label=t("recentActivities", lang),
                value=fmt_relative(a.get("date_iso", ""), lang)).pack(fill="x")
        # Note
        note = a.get("note", "")
        if note:
            tk.Label(self.content, text=t("activityNote", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(12, 4))
            tk.Label(self.content, text=note, bg=config.MATTE_BLACK, fg=config.TEXT,
                     font=get_font(12), wraplength=400, justify="left").pack(anchor="w")
        # Close button
        GoldButton(self.content, text=t("close", lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(16, 0))


# =====================================================================
# === ABOUT MODAL (extended) ===
# =====================================================================
class AboutModal(Modal):
    """Extended about dialog with credits and version info."""

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title=t("about", lang), lang=lang, height=640)
        self._build()

    def _build(self):
        lang = self._lang
        # Logo
        logo = widgets.Avatar(self.content, letter="R", size=100,
                                color=config.GOLD, bg=config.MATTE_BLACK)
        logo.pack(pady=(0, 16))
        # App name
        tk.Label(self.content, text=config.APP_NAME, bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(28, "bold")).pack()
        # Version
        tk.Label(self.content, text=f"v{config.APP_VERSION}", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(12)).pack(pady=(4, 0))
        # Tagline
        tk.Label(self.content, text=t("tagline", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(13)).pack(pady=(8, 16))
        # Description
        tk.Label(self.content, text=t("aboutDescription", lang),
                 bg=config.MATTE_BLACK, fg=config.TEXT,
                 font=get_font(12), wraplength=400, justify="center").pack(pady=(0, 24))
        # Credits
        tk.Label(self.content, text=config.APP_STUDIO, bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(13, "bold")).pack()
        tk.Label(self.content, text=config.APP_COPYRIGHT, bg=config.MATTE_BLACK,
                 fg=config.TEXT_FAINT, font=get_font(10)).pack(pady=(4, 24))
        # Tech stack
        tech_text = "Python · Tkinter · SQLite · AES-256-GCM · PBKDF2"
        tk.Label(self.content, text=tech_text, bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(10)).pack()
        # Close button
        GoldButton(self.content, text=t("close", lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(24, 0))


# =====================================================================
# === HELP MODAL (FAQ) ===
# =====================================================================
class HelpModal(Modal):
    """General help / FAQ dialog."""

    FAQ_ITEMS = [
        ("How do I log an activity?",
         "Tap the + (plus) button at the bottom-right. Enter a title, pick a category, "
         "set the duration (HH:MM), and tap Save. Or tap 'Start stopwatch' to time a live session."),
        ("How do I create a template?",
         "From the Home screen, tap '+ New template' next to the templates row. "
         "Enter a title, pick a category and default duration, then tap Create."),
        ("How do goals and streaks work?",
         "Goals track your activity per day/week/month. When you meet a goal, "
         "your streak increases by 1. Miss a day and your streak resets to 0. "
         "Earn badges at 3, 7, 30, and 100 days."),
        ("Is my data private?",
         "Yes. All data is stored locally on your device. No accounts, no servers, "
         "no internet. Encrypted backups use AES-256-GCM and are safe to share."),
        ("How do I back up my data?",
         "Go to Settings → Backup & restore. Enter a password (≥6 chars), "
         "tap 'Export backup', choose a save location. To restore, use the same password."),
        ("How do I lock the app with a PIN?",
         "Settings → App lock → enter a 4-6 digit PIN → Set PIN. "
         "Next time you launch Rask, you'll be asked to enter the PIN."),
        ("How do I change the language?",
         "Settings → Appearance → tap فارسی for Persian or English for English. "
         "All UI text updates instantly."),
        ("What are the keyboard shortcuts?",
         "Press ? to see all shortcuts. Common: Ctrl+N (quick log), "
         "Ctrl+T (toggle timer), Ctrl+F (search), Ctrl+1-4 (switch tabs)."),
    ]

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title="Help", lang=lang, height=720)
        self._build()

    def _build(self):
        # Scrollable FAQ list
        scroll = widgets.ScrollableFrame(self.content, bg=config.MATTE_BLACK)
        scroll.pack(fill="both", expand=True)
        for i, (q, a) in enumerate(self.FAQ_ITEMS):
            # Question
            tk.Label(scroll.inner, text=f"Q: {q}", bg=config.MATTE_BLACK,
                     fg=config.GOLD, font=get_font(13, "bold"),
                     wraplength=400, anchor="w", justify="left").pack(
                anchor="w", pady=(16 if i else 0, 4))
            # Answer
            tk.Label(scroll.inner, text=a, bg=config.MATTE_BLACK,
                     fg=config.TEXT_DIM, font=get_font(12),
                     wraplength=400, anchor="w", justify="left").pack(
                anchor="w", pady=(0, 4))
        # Close
        GoldButton(self.content, text=t("close", self._lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(16, 0))


# =====================================================================
# === CHANGELOG MODAL ===
# =====================================================================
class ChangelogModal(Modal):
    """Version changelog dialog."""

    CHANGELOG = [
        ("v1.0.0", [
            "Initial release",
            "Smart activity logging (manual + stopwatch + voice + templates)",
            "Goals & streaks with milestone badges",
            "Statistics with bar/donut/heatmap charts",
            "AES-256-GCM encrypted backup & restore",
            "PIN lock (PBKDF2-SHA256)",
            "Full RTL Persian + Jalali calendar",
            "PDF + CSV + JSON export",
            "Recurring activities engine",
            "Keyboard shortcuts",
            "Custom categories with color picker",
            "Search and filter activities",
            "Productivity / consistency / balance scores",
        ]),
    ]

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title="Changelog", lang=lang, height=620)
        self._build()

    def _build(self):
        scroll = widgets.ScrollableFrame(self.content, bg=config.MATTE_BLACK)
        scroll.pack(fill="both", expand=True)
        for version, changes in self.CHANGELOG:
            tk.Label(scroll.inner, text=version, bg=config.MATTE_BLACK,
                     fg=config.GOLD, font=get_font(16, "bold")).pack(
                anchor="w", pady=(16, 4))
            for change in changes:
                tk.Label(scroll.inner, text=f"• {change}", bg=config.MATTE_BLACK,
                         fg=config.TEXT_DIM, font=get_font(12),
                         wraplength=400, anchor="w", justify="left").pack(
                    anchor="w", pady=2)
        GoldButton(self.content, text=t("close", self._lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(16, 0))


# =====================================================================
# === PRIVACY MODAL ===
# =====================================================================
class PrivacyModal(Modal):
    """Privacy policy / data usage explanation."""

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title="Privacy", lang=lang, height=620)
        self._build()

    def _build(self):
        lang = self._lang
        scroll = widgets.ScrollableFrame(self.content, bg=config.MATTE_BLACK)
        scroll.pack(fill="both", expand=True)
        # Privacy sections
        sections = [
            ("Data Storage",
             "All your data — activities, goals, templates, streaks, and badges — "
             "is stored locally in a SQLite database on your device. "
             "Location: ~/.local/share/rask/rask.db (Linux), "
             "~/Library/Application Support/rask/rask.db (macOS), or "
             "%LOCALAPPDATA%/rask/rask.db (Windows)."),
            ("No Accounts",
             "Rask does not require you to create an account. There is no signup, "
             "no login, no email verification. Just open the app and start using it."),
            ("No Internet",
             "The app works fully offline. The only network call is optional voice "
             "recognition (Google's free Web Speech API), and only if you explicitly "
             "tap the microphone button. Everything else stays on your device."),
            ("No Tracking",
             "There is no analytics, no telemetry, no advertising, no third-party "
             "tracking SDKs. We don't know you exist, and we like it that way."),
            ("Encrypted Backups",
             "When you create a backup, it's encrypted with AES-256-GCM using a "
             "password you choose. The password is never stored — if you forget it, "
             "the backup is unrecoverable. The encrypted file is safe to email, "
             "upload to cloud storage, or share anywhere."),
            ("PIN Lock",
             "The optional PIN lock uses PBKDF2-SHA256 with 200,000 iterations to "
             "hash your PIN before storing it. The hash cannot be reversed to "
             "recover the PIN. Even if someone steals your database file, they "
             "cannot unlock the app without your PIN."),
            ("Data Deletion",
             "To delete all your data: Settings → Data management → Clear all data. "
             "This permanently erases your database. Alternatively, just delete the "
             "rask.db file in your data directory."),
            ("Open Source",
             "The desktop edition of Rask is open source. You can audit every line "
             "of code to verify our privacy claims."),
        ]
        for title, body in sections:
            tk.Label(scroll.inner, text=title, bg=config.MATTE_BLACK,
                     fg=config.GOLD, font=get_font(14, "bold")).pack(
                anchor="w", pady=(16, 4))
            tk.Label(scroll.inner, text=body, bg=config.MATTE_BLACK,
                     fg=config.TEXT_DIM, font=get_font(12),
                     wraplength=440, anchor="w", justify="left").pack(
                anchor="w", pady=(0, 4))
        GoldButton(self.content, text=t("close", lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(16, 0))


# =====================================================================
# === THEME MODAL (customization) ===
# =====================================================================
class ThemeModal(Modal):
    """Theme customization: font size, accent color, density."""

    def __init__(self, root, lang: str = "fa",
                 on_change: Optional[Callable] = None):
        self._lang = lang
        self._on_change = on_change
        super().__init__(root, title=t("appearance", lang), lang=lang, height=520)
        self._build()

    def _build(self):
        lang = self._lang
        # Font size
        tk.Label(self.content, text=t("fontSize", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        current_size = database.kv_get_int("font_size", 14)
        self._font_slider = Slider(self.content, min_val=10, max_val=20,
                                     value=current_size, command=self._on_font_size,
                                     width=400)
        self._font_slider.pack(fill="x", pady=(0, 16))
        # Density
        tk.Label(self.content, t("settings", lang) + " density", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        density_options = [
            (t("compact", lang), "compact"),
            (t("comfortable", lang), "comfortable"),
            (t("spacious", lang), "spacious"),
        ]
        current_density = database.kv_get("density", "comfortable")
        PillButtonGroup(self.content, density_options, value=current_density,
                         command=lambda v: database.kv_set("density", v),
                         lang=lang).pack(fill="x", pady=(0, 16))
        # Theme mode
        tk.Label(self.content, text=t("themeMode", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        theme_options = [
            (t("themeDark", lang), "dark"),
            (t("themeLight", lang), "light"),
            (t("themeAuto", lang), "auto"),
        ]
        current_theme = database.kv_get("theme_mode", "dark")
        PillButtonGroup(self.content, theme_options, value=current_theme,
                         command=lambda v: database.kv_set("theme_mode", v),
                         lang=lang).pack(fill="x", pady=(0, 16))
        # Save button
        GoldButton(self.content, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(fill="x", side="bottom")

    def _on_font_size(self, value: float):
        database.kv_set_int("font_size", int(value))

    def _on_save(self):
        if self._on_change:
            self._on_change()
        self.close()


# =====================================================================
# === EXPORT OPTIONS MODAL ===
# =====================================================================
class ExportOptionsModal(Modal):
    """Choose export format and options."""

    def __init__(self, root, lang: str = "fa",
                 on_export: Optional[Callable[[str, dict], None]] = None):
        self._lang = lang
        self._on_export = on_export
        self._format = "csv"
        self._include_archived = False
        self._include_notes = True
        super().__init__(root, title=t("exportCsv", lang), lang=lang, height=520)
        self._build()

    def _build(self):
        lang = self._lang
        # Format
        tk.Label(self.content, text="Format", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        format_options = [
            ("CSV", "csv"),
            ("JSON", "json"),
            ("PDF", "pdf"),
            ("TXT", "txt"),
        ]
        PillButtonGroup(self.content, format_options, value=self._format,
                         command=lambda v: self._set_format(v),
                         lang=lang).pack(fill="x", pady=(0, 16))
        # Options
        tk.Label(self.content, text="Options", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        # Include archived
        opt_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        opt_frame.pack(fill="x", pady=(0, 4))
        tk.Label(opt_frame, text="Include archived", bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=get_font(12)).pack(side="left")
        Switch(opt_frame, value=self._include_archived,
                command=lambda v: self._set_archived(v)).pack(side="right")
        # Export button
        GoldButton(self.content, text=t("exportCsv", lang),
                    command=self._on_export_click, kind="gold",
                    full_width=True).pack(fill="x", side="bottom", pady=(16, 0))

    def _set_format(self, fmt: str):
        self._format = fmt

    def _set_archived(self, val: bool):
        self._include_archived = val

    def _on_export_click(self):
        if self._on_export:
            self._on_export(self._format, {
                "include_archived": self._include_archived,
                "include_notes": self._include_notes,
            })
        self.close()


# =====================================================================
# === REMINDERS MODAL ===
# =====================================================================
class RemindersModal(Modal):
    """Configure daily reminders."""

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title=t("reminders", lang), lang=lang, height=420)
        self._build()

    def _build(self):
        lang = self._lang
        # Enable toggle
        row = tk.Frame(self.content, bg=config.MATTE_BLACK)
        row.pack(fill="x", pady=(0, 16))
        tk.Label(row, text=t("enableReminders", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=get_font(14)).pack(side="left")
        enabled = database.kv_get_bool("reminders_enabled", False)
        Switch(row, value=enabled,
                command=lambda v: database.kv_set_bool("reminders_enabled", v)).pack(side="right")
        # Time picker (HH:MM)
        tk.Label(self.content, text=t("reminderTime", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        time_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        time_frame.pack(fill="x", pady=(0, 16))
        current_time = database.kv_get("reminder_time", "20:00")
        try:
            h_init, m_init = current_time.split(":")
            h_init, m_init = int(h_init), int(m_init)
        except (ValueError, AttributeError):
            h_init, m_init = 20, 0
        # Hour stepper
        self._hour = NumberStepper(time_frame, value=h_init, min_val=0, max_val=23,
                                     command=lambda v: self._save_time())
        self._hour.pack(side="left", padx=(0, 8))
        tk.Label(time_frame, text=":", bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=get_font(20, "bold")).pack(side="left", padx=4)
        self._minute = NumberStepper(time_frame, value=m_init, min_val=0, max_val=59,
                                       step=5, command=lambda v: self._save_time())
        self._minute.pack(side="left", padx=(8, 0))
        # Message
        tk.Label(self.content, text=t("reminderMessage", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._msg_entry = Field(self.content, placeholder=t("defaultReminderMessage", lang),
                                 lang=lang)
        self._msg_entry.pack(fill="x", pady=(0, 16))
        current_msg = database.kv_get("reminder_message", "")
        if current_msg:
            self._msg_entry.set(current_msg)
        # Close
        GoldButton(self.content, text=t("save", lang), command=self._save_and_close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom")

    def _save_time(self):
        h = self._hour.get()
        m = self._minute.get()
        database.kv_set("reminder_time", f"{h:02d}:{m:02d}")

    def _save_and_close(self):
        self._save_time()
        msg = self._msg_entry.get()
        if msg:
            database.kv_set("reminder_message", msg)
        self.close()


# =====================================================================
# === STATISTICS DETAIL MODAL ===
# =====================================================================
class StatisticsDetailModal(Modal):
    """Detailed stats drill-down for a specific metric."""

    def __init__(self, root, metric: str, summary: dict, lang: str = "fa"):
        self._lang = lang
        self._metric = metric
        self._summary = summary
        super().__init__(root, title=t(metric, lang), lang=lang, height=560)
        self._build()

    def _build(self):
        lang = self._lang
        from .date_utils import fmt_human
        s = self._summary
        # Big number
        if self._metric == "total":
            value = fmt_human(int(s.get("total_sec", 0)), lang)
        elif self._metric == "totalActivities":
            value = str(s.get("count", 0))
            if lang == "fa":
                value = to_fa_digits(value)
        elif self._metric == "activeDays":
            value = str(s.get("active_days", 0))
            if lang == "fa":
                value = to_fa_digits(value)
        elif self._metric == "dailyAvg":
            value = fmt_human(int(s.get("daily_avg_sec", 0)), lang)
        else:
            value = "—"
        # Large value display
        tk.Label(self.content, text=value, bg=config.MATTE_BLACK,
                 fg=config.GOLD, font=get_font(36, "bold")).pack(pady=(24, 16))
        # Period label
        from .date_utils import preset_label
        period_label = preset_label(s.get("start_iso", "") == s.get("end_iso", "") and "today" or "7d", lang)
        tk.Label(self.content, text=period_label, bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(12)).pack(pady=(0, 24))
        # Comparison
        comp = s.get("comparison", {})
        if comp and comp.get("previous_sec", 0) > 0:
            delta_pct = comp["delta_percent"]
            arrow = "↑" if delta_pct > 0 else ("↓" if delta_pct < 0 else "→")
            color = config.SUCCESS if delta_pct > 0 else (
                config.DANGER if delta_pct < 0 else config.TEXT_DIM
            )
            pct_str = f"{arrow} {abs(delta_pct):.1f}%"
            if lang == "fa":
                pct_str = to_fa_digits(pct_str)
            tk.Label(self.content, text=f"{t('vsLastPeriod', lang)}: {pct_str}",
                     bg=config.MATTE_BLACK, fg=color,
                     font=get_font(14, "bold")).pack(pady=(0, 24))
        # Details list
        if self._metric == "total":
            InfoRow(self.content, label=t("totalActivities", lang),
                     value=str(s.get("count", 0))).pack(fill="x")
            InfoRow(self.content, label=t("dailyAvg", lang),
                     value=fmt_human(int(s.get("daily_avg_sec", 0)), lang)).pack(fill="x")
            InfoRow(self.content, label=t("activeDays", lang),
                     value=str(s.get("active_days", 0))).pack(fill="x")
            if s.get("best_day"):
                from .date_utils import parse_date, fmt_date
                d = parse_date(s["best_day"])
                InfoRow(self.content, label=t("bestDay", lang),
                         value=fmt_date(d, lang)).pack(fill="x")
        # Close
        GoldButton(self.content, text=t("close", lang), command=self.close,
                    kind="gold", full_width=True).pack(fill="x", side="bottom", pady=(24, 0))


# =====================================================================
# === FEEDBACK MODAL (offline) ===
# =====================================================================
class FeedbackModal(Modal):
    """Offline feedback form (saved to file)."""

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title="Feedback", lang=lang, height=520)
        self._build()

    def _build(self):
        lang = self._lang
        # Description
        tk.Label(self.content,
                 text="Send us your feedback. It will be saved as a text file you can email to us.",
                 bg=config.MATTE_BLACK, fg=config.TEXT_DIM,
                 font=get_font(12), wraplength=400).pack(pady=(0, 16))
        # Rating
        tk.Label(self.content, text="Rating", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        from .widgets_extra import RatingStars
        self._rating = RatingStars(self.content, value=5)
        self._rating.pack(anchor="w", pady=(0, 16))
        # Comments
        tk.Label(self.content, text="Comments", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._comments = TextArea(self.content, placeholder="Tell us what you think...",
                                    lang=lang, height=120)
        self._comments.pack(fill="x", pady=(0, 16))
        # Save button
        GoldButton(self.content, text=t("save", lang),
                    command=self._on_save, kind="gold",
                    full_width=True).pack(fill="x", side="bottom")

    def _on_save(self):
        lang = self._lang
        rating = self._rating.get()
        comments = self._comments.get()
        if not comments:
            return
        # Save to file
        import json
        from .date_utils import now_iso
        feedback = {
            "rating": rating,
            "comments": comments,
            "timestamp": now_iso(),
            "version": config.APP_VERSION,
        }
        feedback_dir = config.DATA_DIR / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_path = feedback_dir / f"feedback-{now_iso().replace(':', '-')}.json"
        try:
            with open(feedback_path, "w", encoding="utf-8") as f:
                json.dump(feedback, f, ensure_ascii=False, indent=2)
            widgets.Toast(self, f"Saved to {feedback_path}", kind="success")
            self.close()
        except Exception as e:
            widgets.Toast(self, f"Save failed: {e}", kind="danger")
