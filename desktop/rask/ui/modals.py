"""modals.py — Quick log, New template, New goal modals.

Mirror of:
  - web/index.html #quickLogModal
  - web/index.html #templateModal
  - web/index.html #goalModal
"""
from __future__ import annotations
import tkinter as tk
from typing import Optional
from .. import config
from .. import database
from .. import timer_service
from .. import voice
from ..i18n import t
from .theme import font, styled_button, chip, card, section_header


class BaseModal(tk.Toplevel):
    """A bottom-sheet-style modal (mirror of .modal-backdrop + .modal)."""

    def __init__(self, parent: tk.Tk, lang: str, title: str):
        super().__init__(parent)
        self.lang = lang
        self.parent = parent
        self.configure(bg=config.MATTE_BLACK)
        self.transient(parent)
        self.grab_set()
        # Position at bottom of parent
        w = config.WINDOW_WIDTH
        h = 540
        self.geometry(f"{w}x{h}+{parent.winfo_x()}+{parent.winfo_y() + parent.winfo_height() - h}")
        self.overrideredirect(False)
        self._build(title)

    def _build(self, title: str):
        # Title
        tk.Label(self, text=title, bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=font(20, "bold"), anchor="w").pack(anchor="w", padx=24, pady=(24, 16))
        # Body container
        self.body = tk.Frame(self, bg=config.MATTE_BLACK)
        self.body.pack(fill="both", expand=True, padx=24)
        self._build_body()

    def _build_body(self):
        raise NotImplementedError

    def close(self):
        self.destroy()


class QuickLogModal(BaseModal):
    def __init__(self, parent, lang, on_saved):
        self.on_saved = on_saved
        self.selected_category: Optional[int] = None
        super().__init__(parent, lang, t("quickLog", lang))

    def _build_body(self):
        lang = self.lang
        # Title input
        self.title_entry = tk.Entry(self.body, bg=config.MATTE_BLACK, fg=config.TEXT,
                                     insertbackground=config.GOLD, font=font(15),
                                     relief="flat", width=40)
        self.title_entry.pack(fill="x", pady=(0, 4))
        self.title_entry.insert(0, t("activityTitle", lang))
        self.title_entry.config(fg=config.TEXT_FAINT)
        self.title_entry.bind("<FocusIn>", lambda _e: self._clear_ph(self.title_entry, t("activityTitle", lang)))
        self.title_entry.bind("<FocusOut>", lambda _e: self._restore_ph(self.title_entry, t("activityTitle", lang)))
        tk.Frame(self.body, bg=config.GOLD, height=2).pack(fill="x", pady=(0, 12))

        # Voice button
        vb = styled_button(self.body, "outline", f"🎤 {t('voiceInput', lang)}",
                            command=self._on_voice)
        vb.pack(fill="x", pady=(0, 12))

        # Category chips
        section_header(self.body, t("category", lang)).pack(anchor="w", pady=(0, 8))
        cat_row = tk.Frame(self.body, bg=config.MATTE_BLACK)
        cat_row.pack(fill="x", pady=(0, 12))
        self.cat_chips = {}
        for c in database.all_categories():
            name = c["name_fa"] if lang == "fa" else c["name_en"]
            ch = chip(cat_row, name, selected=False,
                      command=lambda _cid=c["id"]: self._select_cat(_cid))
            ch.pack(side="left", padx=(0, 8))
            self.cat_chips[c["id"]] = ch

        # Duration HH:MM
        section_header(self.body, t("duration", lang)).pack(anchor="w", pady=(0, 8))
        dur_row = tk.Frame(self.body, bg=config.MATTE_BLACK)
        dur_row.pack(fill="x", pady=(0, 12))
        self.hours_entry = tk.Entry(dur_row, bg=config.MATTE_BLACK, fg=config.TEXT,
                                     insertbackground=config.GOLD, font=font(18),
                                     relief="flat", width=6, justify="center")
        self.hours_entry.insert(0, "HH")
        self.hours_entry.config(fg=config.TEXT_FAINT)
        self.hours_entry.bind("<FocusIn>", lambda _e: self._clear_ph(self.hours_entry, "HH"))
        self.hours_entry.bind("<FocusOut>", lambda _e: self._restore_ph(self.hours_entry, "HH"))
        self.hours_entry.pack(side="left", fill="x", expand=True)
        tk.Label(dur_row, text=":", bg=config.MATTE_BLACK, fg=config.GOLD,
                 font=font(24)).pack(side="left")
        self.minutes_entry = tk.Entry(dur_row, bg=config.MATTE_BLACK, fg=config.TEXT,
                                       insertbackground=config.GOLD, font=font(18),
                                       relief="flat", width=6, justify="center")
        self.minutes_entry.insert(0, "MM")
        self.minutes_entry.config(fg=config.TEXT_FAINT)
        self.minutes_entry.bind("<FocusIn>", lambda _e: self._clear_ph(self.minutes_entry, "MM"))
        self.minutes_entry.bind("<FocusOut>", lambda _e: self._restore_ph(self.minutes_entry, "MM"))
        self.minutes_entry.pack(side="left", fill="x", expand=True)

        # Stopwatch button
        styled_button(self.body, "ghost", t("startStopwatch", lang),
                       command=self._start_stopwatch).pack(fill="x", pady=(0, 12))

        # Cancel / Save
        bot = tk.Frame(self.body, bg=config.MATTE_BLACK)
        bot.pack(fill="x", pady=(0, 24))
        styled_button(bot, "outline", t("cancel", lang),
                       command=self.close).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(bot, "gold", t("save", lang),
                       command=self._save).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _clear_ph(self, entry, ph):
        if entry.get() == ph:
            entry.delete(0, tk.END)
            entry.config(fg=config.TEXT)

    def _restore_ph(self, entry, ph):
        if not entry.get():
            entry.insert(0, ph)
            entry.config(fg=config.TEXT_FAINT)

    def _select_cat(self, cid):
        self.selected_category = cid
        for k, ch in self.cat_chips.items():
            if k == cid:
                ch.config(bg=config.GOLD, fg=config.MATTE_BLACK,
                          highlightbackground=config.GOLD, font=font(12, "bold"))
            else:
                ch.config(bg=config.CHARCOAL, fg=config.TEXT,
                          highlightbackground=config.SURFACE_HI, font=font(12, "normal"))

    def _on_voice(self):
        if not voice.supported():
            from .theme import toast
            toast(self.parent, f"{t('voiceInput', self.lang)} ❌")
            return
        from .theme import toast
        toast(self.parent, "🎤 ...")
        def on_result(text):
            self.title_entry.delete(0, tk.END)
            self.title_entry.insert(0, text)
            self.title_entry.config(fg=config.TEXT)
        voice.listen(self.lang, on_result, lambda err: toast(self.parent, err))

    def _start_stopwatch(self):
        title = self._get_title()
        timer_service.start(title, self.selected_category, None)
        from .theme import toast
        toast(self.parent, f"{t('recording', self.lang)}: {title or '—'}")
        self.close()
        self.on_saved()

    def _get_title(self):
        v = self.title_entry.get()
        if v == t("activityTitle", self.lang) or not v.strip():
            return "(no title)"
        return v.strip()

    def _save(self):
        title = self._get_title()
        h_raw = self.hours_entry.get()
        m_raw = self.minutes_entry.get()
        h = int(h_raw) if h_raw.isdigit() else 0
        m = int(m_raw) if m_raw.isdigit() else 0
        sec = h * 3600 + m * 60
        if sec <= 0:
            # No duration → start stopwatch instead
            timer_service.start(title, self.selected_category, None)
            from .theme import toast
            toast(self.parent, f"{t('recording', self.lang)}: {title}")
            self.close()
            self.on_saved()
            return
        import datetime as _dt
        now = _dt.datetime.now()
        database.insert_activity({
            "title": title,
            "category_id": self.selected_category,
            "kind": "manual",
            "date_iso": now.strftime("%Y-%m-%d"),
            "start_iso": None, "end_iso": None,
            "duration_sec": sec,
            "note": "", "voice_input": 0,
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        from .theme import toast
        toast(self.parent, t("save", self.lang) + " ✓")
        self.close()
        self.on_saved()


class TemplateModal(BaseModal):
    def __init__(self, parent, lang, on_saved):
        self.on_saved = on_saved
        self.selected_category: Optional[int] = None
        super().__init__(parent, lang, t("addTemplate", lang))

    def _build_body(self):
        lang = self.lang
        self.title_entry = tk.Entry(self.body, bg=config.MATTE_BLACK, fg=config.TEXT,
                                     insertbackground=config.GOLD, font=font(15),
                                     relief="flat", width=40)
        self.title_entry.insert(0, t("templateTitle", lang))
        self.title_entry.config(fg=config.TEXT_FAINT)
        self.title_entry.bind("<FocusIn>", lambda _e: self._clear_ph(self.title_entry, t("templateTitle", lang)))
        self.title_entry.bind("<FocusOut>", lambda _e: self._restore_ph(self.title_entry, t("templateTitle", lang)))
        self.title_entry.pack(fill="x", pady=(0, 4))
        tk.Frame(self.body, bg=config.GOLD, height=2).pack(fill="x", pady=(0, 12))

        section_header(self.body, t("category", lang)).pack(anchor="w", pady=(0, 8))
        cat_row = tk.Frame(self.body, bg=config.MATTE_BLACK)
        cat_row.pack(fill="x", pady=(0, 12))
        self.cat_chips = {}
        for c in database.all_categories():
            name = c["name_fa"] if lang == "fa" else c["name_en"]
            ch = chip(cat_row, name, selected=False,
                      command=lambda _cid=c["id"]: self._select_cat(_cid))
            ch.pack(side="left", padx=(0, 8))
            self.cat_chips[c["id"]] = ch

        section_header(self.body, t("duration", lang)).pack(anchor="w", pady=(0, 8))
        self.dur_entry = tk.Entry(self.body, bg=config.MATTE_BLACK, fg=config.TEXT,
                                   insertbackground=config.GOLD, font=font(15),
                                   relief="flat", width=10, justify="center")
        self.dur_entry.insert(0, "30")
        self.dur_entry.pack(anchor="w", pady=(0, 4))
        tk.Frame(self.body, bg=config.GOLD, height=2).pack(fill="x", pady=(0, 12))

        bot = tk.Frame(self.body, bg=config.MATTE_BLACK)
        bot.pack(fill="x", pady=(24, 0))
        styled_button(bot, "outline", t("cancel", lang),
                       command=self.close).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(bot, "gold", t("create", lang),
                       command=self._create).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _clear_ph(self, entry, ph):
        if entry.get() == ph:
            entry.delete(0, tk.END)
            entry.config(fg=config.TEXT)

    def _restore_ph(self, entry, ph):
        if not entry.get():
            entry.insert(0, ph)
            entry.config(fg=config.TEXT_FAINT)

    def _select_cat(self, cid):
        self.selected_category = cid
        for k, ch in self.cat_chips.items():
            if k == cid:
                ch.config(bg=config.GOLD, fg=config.MATTE_BLACK,
                          highlightbackground=config.GOLD, font=font(12, "bold"))
            else:
                ch.config(bg=config.CHARCOAL, fg=config.TEXT,
                          highlightbackground=config.SURFACE_HI, font=font(12, "normal"))

    def _create(self):
        title = self.title_entry.get().strip()
        if title == t("templateTitle", self.lang) or not title:
            return
        dur = int(self.dur_entry.get() or "30") if self.dur_entry.get().isdigit() else 30
        database.upsert_template({
            "title": title, "category_id": self.selected_category,
            "default_duration_min": dur, "icon": "",
        })
        from .theme import toast
        toast(self.parent, t("save", self.lang) + " ✓")
        self.close()
        self.on_saved()


class GoalModal(BaseModal):
    def __init__(self, parent, lang, on_saved):
        self.on_saved = on_saved
        self.selected_period = "daily"
        self.selected_category: Optional[int] = None
        super().__init__(parent, lang, t("newGoal", lang))

    def _build_body(self):
        lang = self.lang
        # Period chips
        section_header(self.body, t("duration", lang)).pack(anchor="w", pady=(0, 8))
        per_row = tk.Frame(self.body, bg=config.MATTE_BLACK)
        per_row.pack(fill="x", pady=(0, 12))
        self.period_chips = {}
        for key, lbl in [("daily", "daily"), ("weekly", "weekly"), ("monthly", "monthly")]:
            ch = chip(per_row, t(lbl, lang), selected=(key == self.selected_period),
                      command=lambda _k=key: self._select_period(_k))
            ch.pack(side="left", padx=(0, 8))
            self.period_chips[key] = ch

        # Category chips
        section_header(self.body, t("category", lang)).pack(anchor="w", pady=(0, 8))
        cat_row = tk.Frame(self.body, bg=config.MATTE_BLACK)
        cat_row.pack(fill="x", pady=(0, 12))
        self.cat_chips = {}
        # "All" chip
        all_chip = chip(cat_row, t("all", lang), selected=True,
                         command=lambda: self._select_cat(None))
        all_chip.pack(side="left", padx=(0, 8))
        self.cat_chips[None] = all_chip
        for c in database.all_categories():
            name = c["name_fa"] if lang == "fa" else c["name_en"]
            ch = chip(cat_row, name, selected=False,
                      command=lambda _cid=c["id"]: self._select_cat(_cid))
            ch.pack(side="left", padx=(0, 8))
            self.cat_chips[c["id"]] = ch

        # Target minutes
        tk.Label(self.body, text="Target (minutes)", bg=config.MATTE_BLACK,
                 fg=config.TEXT_DIM, font=font(11), anchor="w").pack(anchor="w", pady=(8, 4))
        self.target_entry = tk.Entry(self.body, bg=config.MATTE_BLACK, fg=config.TEXT,
                                      insertbackground=config.GOLD, font=font(15),
                                      relief="flat", width=10, justify="center")
        self.target_entry.insert(0, "60")
        self.target_entry.pack(anchor="w", pady=(0, 4))
        tk.Frame(self.body, bg=config.GOLD, height=2).pack(fill="x", pady=(0, 12))

        bot = tk.Frame(self.body, bg=config.MATTE_BLACK)
        bot.pack(fill="x", pady=(24, 0))
        styled_button(bot, "outline", t("cancel", lang),
                       command=self.close).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(bot, "gold", t("save", lang),
                       command=self._save).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _select_period(self, key):
        self.selected_period = key
        for k, ch in self.period_chips.items():
            if k == key:
                ch.config(bg=config.GOLD, fg=config.MATTE_BLACK,
                          highlightbackground=config.GOLD, font=font(12, "bold"))
            else:
                ch.config(bg=config.CHARCOAL, fg=config.TEXT,
                          highlightbackground=config.SURFACE_HI, font=font(12, "normal"))

    def _select_cat(self, cid):
        self.selected_category = cid
        for k, ch in self.cat_chips.items():
            if k == cid:
                ch.config(bg=config.GOLD, fg=config.MATTE_BLACK,
                          highlightbackground=config.GOLD, font=font(12, "bold"))
            else:
                ch.config(bg=config.CHARCOAL, fg=config.TEXT,
                          highlightbackground=config.SURFACE_HI, font=font(12, "normal"))

    def _save(self):
        target = int(self.target_entry.get() or "60") if self.target_entry.get().isdigit() else 60
        database.upsert_goal({
            "period": self.selected_period,
            "category_id": self.selected_category,
            "target_minutes": target, "active": 1,
        })
        from .theme import toast
        toast(self.parent, t("save", self.lang) + " ✓")
        self.close()
        self.on_saved()
