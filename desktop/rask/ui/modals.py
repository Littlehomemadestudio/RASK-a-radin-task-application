"""modals.py — Modal dialogs for Rask.

1:1 mirror of:
  - web/index.html #quickLogModal (Quick log: title, voice, category, duration, save/cancel)
  - web/index.html #templateModal (New template: title, category, duration, create)
  - web/index.html #goalModal    (New goal: period, category, target, save)

Desktop-only extensions:
  - EditActivityModal (edit title/category/duration/note/date)
  - CategoryModal     (create custom category with color picker)
  - SearchModal       (search activities by title)
  - RecurringModal    (create recurring activity rule)
"""
from __future__ import annotations
import datetime as _dt
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from .. import config
from .. import database
from .. import timer_service
from .. import voice
from .. import recurring
from ..i18n import t, to_fa_digits
from .. import widgets
from ..widgets import (
    GoldButton, IconButton, Chip, Card, Field, TextArea, Switch,
    Modal, SegmentedControl, get_font, section_header,
)
from ..date_utils import today_iso, now_iso


# =====================================================================
# === QUICK LOG MODAL (mirror web #quickLogModal) ===
# =====================================================================
class QuickLogModal(Modal):
    """The Quick Log modal. Logs a manual activity or starts a stopwatch."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None):
        self._lang = lang
        self._on_saved = on_saved
        self._selected_category: Optional[int] = None
        super().__init__(root, title=t("quickLog", lang), lang=lang,
                          on_close=None, height=720)
        self._build()
        # Auto-close on backdrop click (Toplevel doesn't have a backdrop —
        # we just rely on Escape and the close button)
        self.focus_set()

    def _build(self):
        lang = self._lang
        # Title field
        tk.Label(self.content, text=t("activityTitle", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._title_entry = Field(self.content, placeholder=t("activityTitle", lang),
                                   lang=lang)
        self._title_entry.pack(fill="x", pady=(0, 12))
        # Voice button
        self._voice_btn = GoldButton(self.content, text=t("voiceInput", lang),
                                       command=self._on_voice, kind="outline",
                                       icon="mic", size="sm", full_width=True)
        self._voice_btn.pack(fill="x", pady=(0, 12))
        # Category
        tk.Label(self.content, text=t("category", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._cats_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._cats_frame.pack(fill="x", pady=(0, 12))
        self._render_categories()
        # Duration
        tk.Label(self.content, text=t("duration", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        dur_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        dur_frame.pack(fill="x", pady=(0, 12))
        self._hours_entry = Field(dur_frame, placeholder="HH", lang=lang, height=44)
        self._hours_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Label(dur_frame, text=":", bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=get_font(24, "bold")).pack(side="left", padx=4)
        self._minutes_entry = Field(dur_frame, placeholder="MM", lang=lang, height=44)
        self._minutes_entry.pack(side="right", fill="x", expand=True, padx=(4, 0))
        # Stopwatch button
        GoldButton(self.content, text=t("startStopwatch", lang),
                    command=self._on_stopwatch, kind="ghost",
                    full_width=True).pack(fill="x", pady=(0, 16))
        # Cancel / Save buttons
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _render_categories(self):
        lang = self._lang
        for child in self._cats_frame.winfo_children():
            child.destroy()
        cats = database.all_categories()
        for cat in cats:
            color = cat["color"]
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            chip = Chip(self._cats_frame, text=name,
                         selected=(self._selected_category == cat["id"]),
                         command=lambda _c=cat: self._on_category(_c),
                         color=color, lang=lang)
            chip.pack(side="left", padx=(0, 4))

    def _on_category(self, cat: dict):
        self._selected_category = cat["id"]
        self._render_categories()

    def _on_voice(self):
        lang = self._lang
        if not voice.voice_available():
            widgets.Toast(self, t("voiceNotAvailable", lang), kind="danger")
            return
        widgets.Toast(self, t("listening", lang), kind="info")
        def on_result(text):
            self._title_entry.set(text)
        def on_error(msg):
            widgets.Toast(self, msg, kind="danger")
        voice.listen_async(lang=lang, on_result=on_result, on_error=on_error)

    def _on_stopwatch(self):
        lang = self._lang
        title = self._title_entry.get() or ""
        timer_service.start(title, self._selected_category, None)
        widgets.Toast(self, f"{t('stopwatchStarted', lang)}", kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()

    def _on_save(self):
        lang = self._lang
        title = self._title_entry.get() or t("untitled", lang)
        try:
            h = int(self._hours_entry.get() or "0")
        except ValueError:
            h = 0
        try:
            m = int(self._minutes_entry.get() or "0")
        except ValueError:
            m = 0
        sec = h * 3600 + m * 60
        if sec <= 0:
            # No duration — start a stopwatch instead
            timer_service.start(title, self._selected_category, None)
            widgets.Toast(self, f"{t('stopwatchStarted', lang)}", kind="success")
            self.close()
            if self._on_saved:
                self._on_saved()
            return
        # Insert activity
        now = _dt.datetime.now()
        activity = {
            "title": title,
            "category_id": self._selected_category,
            "kind": "manual",
            "date_iso": now.strftime("%Y-%m-%d"),
            "start_iso": None,
            "end_iso": None,
            "duration_sec": sec,
            "note": "",
            "voice_input": 0,
            "created_at": now.isoformat(),
        }
        database.insert_activity(activity)
        widgets.Toast(self, t("quickLogSaved", lang), kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()


# =====================================================================
# === TEMPLATE MODAL (mirror web #templateModal) ===
# =====================================================================
class TemplateModal(Modal):
    """The New Template modal."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None,
                 template: Optional[dict] = None):
        self._lang = lang
        self._on_saved = on_saved
        self._template = template
        self._selected_category: Optional[int] = template.get("category_id") if template else None
        title = t("editTemplate", lang) if template else t("addTemplate", lang)
        super().__init__(root, title=title, lang=lang, height=560)
        self._build()

    def _build(self):
        lang = self._lang
        # Title
        tk.Label(self.content, text=t("templateTitle", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._title_entry = Field(self.content, placeholder=t("templateTitle", lang),
                                   lang=lang)
        self._title_entry.pack(fill="x", pady=(0, 12))
        if self._template:
            self._title_entry.set(self._template.get("title", ""))
        # Category
        tk.Label(self.content, text=t("category", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._cats_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._cats_frame.pack(fill="x", pady=(0, 12))
        self._render_categories()
        # Default duration
        tk.Label(self.content, text=t("templateDuration", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._dur_entry = Field(self.content, placeholder="30", lang=lang, height=44)
        self._dur_entry.pack(fill="x", pady=(0, 16))
        if self._template:
            self._dur_entry.set(str(self._template.get("default_duration_min", 30)))
        # Cancel / Create buttons
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("create", lang) if not self._template else t("save", lang),
                    command=self._on_save, kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _render_categories(self):
        lang = self._lang
        for child in self._cats_frame.winfo_children():
            child.destroy()
        cats = database.all_categories()
        for cat in cats:
            color = cat["color"]
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            chip = Chip(self._cats_frame, text=name,
                         selected=(self._selected_category == cat["id"]),
                         command=lambda _c=cat: self._on_category(_c),
                         color=color, lang=lang)
            chip.pack(side="left", padx=(0, 4))

    def _on_category(self, cat: dict):
        self._selected_category = cat["id"]
        self._render_categories()

    def _on_save(self):
        lang = self._lang
        title = self._title_entry.get().strip()
        if not title:
            return
        try:
            dur = int(self._dur_entry.get() or "30")
        except ValueError:
            dur = 30
        template = {
            "title": title,
            "category_id": self._selected_category,
            "default_duration_min": dur,
        }
        if self._template:
            template["id"] = self._template["id"]
        database.upsert_template(template)
        widgets.Toast(self, t("templateCreated", lang), kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()


# =====================================================================
# === GOAL MODAL (mirror web #goalModal) ===
# =====================================================================
class GoalModal(Modal):
    """The New Goal modal."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None,
                 goal: Optional[dict] = None):
        self._lang = lang
        self._on_saved = on_saved
        self._goal = goal
        self._selected_period: str = goal.get("period", "daily") if goal else "daily"
        self._selected_category: Optional[int] = goal.get("category_id") if goal else None
        title = t("editGoal", lang) if goal else t("newGoal", lang)
        super().__init__(root, title=title, lang=lang, height=620)
        self._build()

    def _build(self):
        lang = self._lang
        # Period
        tk.Label(self.content, text=t("goalPeriod", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        period_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        period_frame.pack(fill="x", pady=(0, 12))
        for i, period in enumerate(["daily", "weekly", "monthly"]):
            Chip(period_frame, text=t(period, lang),
                  selected=(period == self._selected_period),
                  command=lambda _p=period: self._on_period(_p),
                  lang=lang).pack(side="left", padx=(0, 4))
        # Category
        tk.Label(self.content, text=t("goalCategory", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._cats_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._cats_frame.pack(fill="x", pady=(0, 12))
        self._render_categories()
        # Target
        tk.Label(self.content, text=t("targetMinutes", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._target_entry = Field(self.content, placeholder="60", lang=lang, height=44)
        self._target_entry.pack(fill="x", pady=(0, 16))
        if self._goal:
            self._target_entry.set(str(self._goal.get("target_minutes", 60)))
        # Cancel / Save
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _render_categories(self):
        lang = self._lang
        for child in self._cats_frame.winfo_children():
            child.destroy()
        # "All" chip
        Chip(self._cats_frame, text=t("all", lang),
              selected=(self._selected_category is None),
              command=lambda: self._on_category(None),
              lang=lang).pack(side="left", padx=(0, 4))
        cats = database.all_categories()
        for cat in cats:
            color = cat["color"]
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            chip = Chip(self._cats_frame, text=name,
                         selected=(self._selected_category == cat["id"]),
                         command=lambda _c=cat: self._on_category(_c),
                         color=color, lang=lang)
            chip.pack(side="left", padx=(0, 4))

    def _on_period(self, period: str):
        self._selected_period = period
        # Re-render period chips
        for child in self._cats_frame.winfo_children():
            child.destroy()
        self._build()  # Simple rebuild

    def _on_category(self, cat: Optional[dict]):
        self._selected_category = cat["id"] if cat else None
        self._render_categories()

    def _on_save(self):
        lang = self._lang
        try:
            target = int(self._target_entry.get() or "60")
        except ValueError:
            target = 60
        goal = {
            "period": self._selected_period,
            "category_id": self._selected_category,
            "target_minutes": target,
            "active": 1,
        }
        if self._goal:
            goal["id"] = self._goal["id"]
        database.upsert_goal(goal)
        widgets.Toast(self, t("saved", lang), kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()


# =====================================================================
# === EDIT ACTIVITY MODAL (desktop-only) ===
# =====================================================================
class EditActivityModal(Modal):
    """Edit an existing activity's title, category, duration, note, date."""

    def __init__(self, root, activity: dict, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None):
        self._lang = lang
        self._activity = activity
        self._on_saved = on_saved
        self._selected_category = activity.get("category_id")
        super().__init__(root, title=t("editActivity", lang), lang=lang, height=720)
        self._build()

    def _build(self):
        lang = self._lang
        # Title
        tk.Label(self.content, text=t("activityTitle", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._title_entry = Field(self.content, placeholder=t("activityTitle", lang),
                                   lang=lang)
        self._title_entry.pack(fill="x", pady=(0, 12))
        self._title_entry.set(self._activity.get("title", ""))
        # Category
        tk.Label(self.content, text=t("category", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._cats_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._cats_frame.pack(fill="x", pady=(0, 12))
        self._render_categories()
        # Duration
        tk.Label(self.content, text=t("duration", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        dur_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        dur_frame.pack(fill="x", pady=(0, 12))
        sec = int(self._activity.get("duration_sec", 0) or 0)
        h_init = sec // 3600
        m_init = (sec % 3600) // 60
        self._hours_entry = Field(dur_frame, placeholder="HH", lang=lang, height=44)
        self._hours_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._hours_entry.set(str(h_init) if h_init else "")
        tk.Label(dur_frame, text=":", bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=get_font(24, "bold")).pack(side="left", padx=4)
        self._minutes_entry = Field(dur_frame, placeholder="MM", lang=lang, height=44)
        self._minutes_entry.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self._minutes_entry.set(str(m_init) if m_init else "")
        # Date
        tk.Label(self.content, text=t("activityDate", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._date_entry = Field(self.content, placeholder="YYYY-MM-DD", lang=lang, height=44)
        self._date_entry.pack(fill="x", pady=(0, 12))
        self._date_entry.set(self._activity.get("date_iso", today_iso()))
        # Note
        tk.Label(self.content, text=t("activityNote", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._note_entry = TextArea(self.content, placeholder=t("activityNotePlaceholder", lang),
                                     lang=lang, height=80)
        self._note_entry.pack(fill="x", pady=(0, 12))
        self._note_entry.set(self._activity.get("note", ""))
        # Buttons
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=t("deleteActivity", lang),
                    command=self._on_delete, kind="danger", size="sm",
                    full_width=True).pack(fill="x", pady=(0, 8))
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _render_categories(self):
        lang = self._lang
        for child in self._cats_frame.winfo_children():
            child.destroy()
        cats = database.all_categories()
        for cat in cats:
            color = cat["color"]
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            chip = Chip(self._cats_frame, text=name,
                         selected=(self._selected_category == cat["id"]),
                         command=lambda _c=cat: self._on_category(_c),
                         color=color, lang=lang)
            chip.pack(side="left", padx=(0, 4))

    def _on_category(self, cat: dict):
        self._selected_category = cat["id"]
        self._render_categories()

    def _on_save(self):
        lang = self._lang
        title = self._title_entry.get() or t("untitled", lang)
        try:
            h = int(self._hours_entry.get() or "0")
        except ValueError:
            h = 0
        try:
            m = int(self._minutes_entry.get() or "0")
        except ValueError:
            m = 0
        sec = h * 3600 + m * 60
        date_iso = self._date_entry.get() or today_iso()
        note = self._note_entry.get()
        activity = {
            **self._activity,
            "title": title,
            "category_id": self._selected_category,
            "duration_sec": sec,
            "date_iso": date_iso,
            "note": note,
        }
        database.update_activity(activity)
        widgets.Toast(self, t("saved", lang), kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()

    def _on_delete(self):
        lang = self._lang
        if messagebox.askyesno(config.APP_NAME, t("confirmDeleteActivity", lang)):
            database.delete_activity(self._activity["id"])
            widgets.Toast(self, t("toastDeleted", lang), kind="info")
            self.close()
            if self._on_saved:
                self._on_saved()


# =====================================================================
# === SEARCH MODAL (desktop-only) ===
# =====================================================================
class SearchModal(Modal):
    """Search activities by title or note."""

    def __init__(self, root, lang: str = "fa",
                 on_activity_click: Optional[Callable[[dict], None]] = None):
        self._lang = lang
        self._on_activity_click = on_activity_click
        super().__init__(root, title=t("search", lang), lang=lang, height=720)
        self._build()

    def _build(self):
        lang = self._lang
        # Search bar
        self._search_entry = Field(self.content, placeholder=t("searchActivities", lang),
                                    lang=lang, on_change=self._on_search)
        self._search_entry.pack(fill="x", pady=(0, 12))
        # Results
        self._results_frame = widgets.ScrollableFrame(self.content, bg=config.MATTE_BLACK)
        self._results_frame.pack(fill="both", expand=True)
        # Show initial empty state
        self._render_results([])

    def _on_search(self, query: str):
        if not query or len(query) < 2:
            self._render_results([])
            return
        results = database.search_activities(query, limit=50)
        self._render_results(results)

    def _render_results(self, results: list[dict]):
        lang = self._lang
        self._results_frame.clear()
        if not results:
            tk.Label(self._results_frame.inner, text=t("noResults", lang),
                     bg=config.MATTE_BLACK, fg=config.TEXT_FAINT,
                     font=get_font(13)).pack(pady=24)
            return
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        for a in results:
            cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
            row = widgets.ActivityRow(self._results_frame.inner, a, cat, lang,
                                       on_click=self._on_click)
            row.pack(fill="x")

    def _on_click(self, activity: dict):
        self.close()
        if self._on_activity_click:
            self._on_activity_click(activity)


# =====================================================================
# === RECURRING MODAL (desktop-only) ===
# =====================================================================
class RecurringModal(Modal):
    """Create a new recurring activity rule."""

    def __init__(self, root, lang: str = "fa",
                 on_saved: Optional[Callable[[], None]] = None):
        self._lang = lang
        self._on_saved = on_saved
        self._selected_category: Optional[int] = None
        self._selected_pattern: str = "daily"
        super().__init__(root, title=t("addRecurring", lang), lang=lang, height=720)
        self._build()

    def _build(self):
        lang = self._lang
        # Title
        tk.Label(self.content, text=t("activityTitle", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._title_entry = Field(self.content, placeholder=t("activityTitle", lang),
                                   lang=lang)
        self._title_entry.pack(fill="x", pady=(0, 12))
        # Category
        tk.Label(self.content, text=t("category", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._cats_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        self._cats_frame.pack(fill="x", pady=(0, 12))
        self._render_categories()
        # Pattern
        tk.Label(self.content, text=t("goalPeriod", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        patterns = [
            ("daily",    "recurringDaily"),
            ("weekly",   "recurringWeekly"),
            ("monthly",  "recurringMonthly"),
            ("weekdays", "recurringWeekdays"),
            ("weekends", "recurringWeekends"),
        ]
        pattern_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        pattern_frame.pack(fill="x", pady=(0, 12))
        for pattern, label_key in patterns:
            Chip(pattern_frame, text=t(label_key, lang),
                  selected=(pattern == self._selected_pattern),
                  command=lambda _p=pattern: self._on_pattern(_p),
                  lang=lang).pack(side="left", padx=(0, 4))
        # Duration
        tk.Label(self.content, text=t("duration", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        dur_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        dur_frame.pack(fill="x", pady=(0, 12))
        self._hours_entry = Field(dur_frame, placeholder="HH", lang=lang, height=44)
        self._hours_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Label(dur_frame, text=":", bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=get_font(24, "bold")).pack(side="left", padx=4)
        self._minutes_entry = Field(dur_frame, placeholder="MM", lang=lang, height=44)
        self._minutes_entry.pack(side="right", fill="x", expand=True, padx=(4, 0))
        # Cancel / Save
        btn_frame = tk.Frame(self.content, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", side="bottom")
        GoldButton(btn_frame, text=t("cancel", lang), command=self.close,
                    kind="outline", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("save", lang), command=self._on_save,
                    kind="gold", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _render_categories(self):
        lang = self._lang
        for child in self._cats_frame.winfo_children():
            child.destroy()
        cats = database.all_categories()
        for cat in cats:
            color = cat["color"]
            name = cat["name_fa"] if lang == "fa" else cat["name_en"]
            chip = Chip(self._cats_frame, text=name,
                         selected=(self._selected_category == cat["id"]),
                         command=lambda _c=cat: self._on_category(_c),
                         color=color, lang=lang)
            chip.pack(side="left", padx=(0, 4))

    def _on_category(self, cat: dict):
        self._selected_category = cat["id"]
        self._render_categories()

    def _on_pattern(self, pattern: str):
        self._selected_pattern = pattern
        # Could re-render the pattern chips here

    def _on_save(self):
        lang = self._lang
        title = self._title_entry.get() or t("untitled", lang)
        try:
            h = int(self._hours_entry.get() or "0")
        except ValueError:
            h = 0
        try:
            m = int(self._minutes_entry.get() or "0")
        except ValueError:
            m = 0
        sec = h * 3600 + m * 60
        if sec <= 0:
            widgets.Toast(self, t("selectDuration", lang), kind="danger")
            return
        recurring.create_recurring(
            title=title,
            category_id=self._selected_category,
            pattern=self._selected_pattern,
            duration_sec=sec,
        )
        widgets.Toast(self, t("saved", lang), kind="success")
        self.close()
        if self._on_saved:
            self._on_saved()


# =====================================================================
# === SHORTCUTS MODAL (desktop-only) ===
# =====================================================================
class ShortcutsModal(Modal):
    """Show all keyboard shortcuts."""

    def __init__(self, root, lang: str = "fa"):
        self._lang = lang
        super().__init__(root, title=t("keyboardShortcuts", lang), lang=lang, height=640)
        self._build()

    def _build(self):
        lang = self._lang
        from ..config import SHORTCUTS
        for shortcut, action, _desc in SHORTCUTS:
            row = tk.Frame(self.content, bg=config.MATTE_BLACK)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=shortcut, bg=config.SURFACE, fg=config.GOLD,
                     font=get_font(12, "bold"), padx=8, pady=4).pack(side="left")
            tk.Label(row, text=t(f"shortcut_{action}", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT, font=get_font(12)).pack(side="left", padx=12)
