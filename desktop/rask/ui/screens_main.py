"""screens_main.py — Home, Goals, Stats, Settings screens.

Mirror of:
  - web/index.html #screen-home (greeting, date, today-card with ring, timer card, templates row, recent list)
  - web/index.html #screen-goals (goals list with rings + streaks + badges)
  - web/index.html #screen-stats (preset chips, total card, bar/donut/heatmap, trends, PDF/CSV buttons)
  - web/index.html #screen-settings (language, app lock, backup/restore, about)
"""
from __future__ import annotations
import datetime as _dt
import os
import tkinter as tk
from tkinter import filedialog, simpledialog
from typing import Callable, Optional
from .. import config
from .. import database
from .. import timer_service
from .. import crypto
from .. import exporters
from .. import charts as charts_mod
from .. import voice
from ..date_utils import (
    today_iso, fmt_date, fmt_short_date, fmt_relative, fmt_human, fmt_duration,
    add_days, start_of_week, end_of_week, start_of_month, end_of_month,
    start_of_year, end_of_year, date_range,
)
from ..i18n import t, to_fa_digits
from .theme import (
    font, family, styled_button, chip, card, field, section_header,
    greeting, date_label, toast,
)


class BaseScreen(tk.Frame):
    """Base class for the four main screens. Provides scrollable container."""

    def __init__(self, parent: tk.Widget, app, lang: str):
        super().__init__(parent, bg=config.MATTE_BLACK)
        self.app = app
        self.lang = lang
        # Use a Canvas + inner Frame for scrolling
        outer = tk.Frame(self, bg=config.MATTE_BLACK)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, bg=config.MATTE_BLACK,
                                 highlightthickness=0, bd=0)
        self.scroll = tk.Scrollbar(outer, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=config.MATTE_BLACK)
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner,
                                                        anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Mouse-wheel scrolling
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def _on_inner_configure(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self._inner_window, width=e.width)

    def _on_wheel(self, event):
        # Windows / macOS
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def render(self):
        """Subclasses override. Called when this screen becomes visible."""
        for child in self.inner.winfo_children():
            child.destroy()

    def set_lang(self, lang: str):
        self.lang = lang


# =================== HOME ===================
class HomeScreen(BaseScreen):
    def render(self):
        super().render()
        lang = self.lang
        # Greeting
        h = _dt.datetime.now().hour
        if h < 12:
            gk = "goodMorning"
        elif h < 18:
            gk = "goodAfternoon"
        else:
            gk = "goodEvening"
        greeting(self.inner, t(gk, lang)).pack(anchor="w", padx=24, pady=(24, 0))
        date_label(self.inner, fmt_date(_dt.datetime.now(), lang)).pack(anchor="w", padx=24)

        # Today card: ring + total + goal + streak
        today_card = card(self.inner)
        today_card.pack(fill="x", padx=24, pady=16)
        # Two columns: ring (left), text (right)
        ring_col = tk.Frame(today_card, bg=config.CHARCOAL)
        ring_col.pack(side="left", padx=(16, 8), pady=16)
        ring_cv = tk.Canvas(ring_col, width=140, height=140,
                            bg=config.CHARCOAL, highlightthickness=0)
        ring_cv.pack()
        info_col = tk.Frame(today_card, bg=config.CHARCOAL)
        info_col.pack(side="left", fill="x", expand=True, padx=(8, 16), pady=16)

        # Today total + goal
        today = today_iso()
        total = database.total_seconds_on(today)
        goals = database.all_goals(active_only=True)
        daily_goal = next((g for g in goals if g["period"] == "daily" and not g["category_id"]), None) or (goals[0] if goals else None)
        target_sec = (daily_goal["target_minutes"] * 60) if daily_goal else (config.DEFAULT_DAILY_GOAL_MIN * 60)
        progress = min(1.0, total / target_sec) if target_sec > 0 else 0
        charts_mod.progress_ring(ring_cv, 70, 70, 140, progress,
                                  config.GOLD, config.SURFACE_HI,
                                  fmt_human(total, lang), config.TEXT)

        tk.Label(info_col, text=t("today", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=font(12), anchor="w").pack(anchor="w")
        tk.Label(info_col, text=fmt_human(total, lang), bg=config.CHARCOAL,
                 fg=config.GOLD, font=font(26, "bold"), anchor="w").pack(anchor="w")
        if daily_goal:
            tk.Label(info_col, text=f"{t('goal', lang)}: {fmt_human(daily_goal['target_minutes'] * 60, lang)}",
                     bg=config.CHARCOAL, fg=config.TEXT_DIM, font=font(12), anchor="w").pack(anchor="w")
        top_streaks = database.top_streaks(1)
        if top_streaks and top_streaks[0]["current"] > 0:
            cur = top_streaks[0]["current"]
            tk.Label(info_col,
                     text=f"🔥 {t('streak', lang)}: {to_fa_digits(cur) if lang == 'fa' else cur} {t('days', lang)}",
                     bg=config.CHARCOAL, fg=config.GOLD, font=font(13, "bold"), anchor="w").pack(anchor="w")

        # Active timer card (only shown when timer is running)
        self._render_timer_card()

        # Quick templates
        section_header(self.inner, t("quickTemplates", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        tpls_row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        tpls_row.pack(fill="x", padx=24)
        tpls = database.all_templates()
        if not tpls:
            empty = tk.Label(tpls_row, text=t("noTemplates", lang) + " — " + t("addTemplate", lang),
                             bg=config.MATTE_BLACK, fg=config.TEXT_FAINT, font=font(13), anchor="w")
            empty.pack(anchor="w")
            empty.bind("<Button-1>", lambda e: self.app.open_template_modal())
        else:
            for tp in tpls:
                c = chip(tpls_row, tp["title"], selected=False,
                          command=lambda _t=tp: self._start_template(_t))
                c.pack(side="left", padx=(0, 8))

        # Recent activities
        section_header(self.inner, t("recentActivities", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        recent = database.recent_activities(15)
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        if not recent:
            tk.Label(self.inner, text=t("noActivities", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_FAINT, font=font(13)).pack(anchor="w", padx=24, pady=32)
        else:
            list_frame = tk.Frame(self.inner, bg=config.MATTE_BLACK)
            list_frame.pack(fill="x", padx=24, pady=(0, 24))
            for a in recent:
                cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
                cat_name = (cat["name_fa"] if lang == "fa" else cat["name_en"]) if cat else "—"
                cat_color = cat["color"] if cat else config.TEXT_DIM
                row = tk.Frame(list_frame, bg=config.MATTE_BLACK)
                row.pack(fill="x", pady=8)
                # Divider above (except first)
                top_row = tk.Frame(row, bg=config.MATTE_BLACK)
                top_row.pack(fill="x")
                tk.Label(top_row, text=(a.get("title") or "(no title)")[:60],
                         bg=config.MATTE_BLACK, fg=config.TEXT, font=font(14, "bold"),
                         anchor="w").pack(side="left", fill="x", expand=True)
                tk.Label(top_row, text=cat_name, bg=config.MATTE_BLACK,
                         fg=cat_color, font=font(11, "bold"), anchor="e").pack(side="right")
                bot_row = tk.Frame(row, bg=config.MATTE_BLACK)
                bot_row.pack(fill="x")
                tk.Label(bot_row, text=fmt_human(int(a.get("duration_sec", 0) or 0), lang),
                         bg=config.MATTE_BLACK, fg=config.GOLD, font=font(12, "bold"),
                         anchor="w").pack(side="left")
                tk.Label(bot_row, text=fmt_relative(a.get("date_iso", ""), lang),
                         bg=config.MATTE_BLACK, fg=config.TEXT_FAINT, font=font(11),
                         anchor="e").pack(side="right")
                # Divider line below
                tk.Frame(row, bg=config.DIVIDER, height=1).pack(fill="x", pady=(8, 0))

    def _render_timer_card(self):
        if not (timer_service.is_running() or timer_service.elapsed_sec() > 0):
            return
        tc = card(self.inner)
        tc.configure(bg=config.CHARCOAL, highlightbackground=config.GOLD_DIM,
                     highlightthickness=1)
        # Place it just above the templates section by inserting at index 2 of inner children.
        tc.pack(fill="x", padx=24, pady=8, after=self.inner.winfo_children()[1] if len(self.inner.winfo_children()) > 1 else None)
        tk.Label(tc, text=timer_service.current_title() or t("recording", self.lang),
                 bg=config.CHARCOAL, fg=config.TEXT, font=font(13, "bold"),
                 anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
        self._timer_lbl = tk.Label(tc, text=fmt_duration(timer_service.elapsed_sec()),
                                    bg=config.CHARCOAL, fg=config.GOLD, font=font(32, "bold"))
        self._timer_lbl.pack(anchor="w", padx=16, pady=4)
        btns = tk.Frame(tc, bg=config.CHARCOAL)
        btns.pack(fill="x", padx=16, pady=(0, 12))
        pause_label = t("pause", self.lang) if timer_service.is_running() else t("resume", self.lang)
        pb = styled_button(btns, "outline", pause_label, small=True,
                            command=self._toggle_pause)
        pb.pack(side="left", fill="x", expand=True, padx=(0, 4))
        sb = styled_button(btns, "gold", t("stopSave", self.lang), small=True,
                            command=self._stop_save)
        sb.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _toggle_pause(self):
        if timer_service.is_running():
            timer_service.pause()
        else:
            timer_service.resume()
        self.render()

    def _stop_save(self):
        timer_service.stop_and_save()
        self.render()

    def _start_template(self, tp):
        timer_service.start(tp["title"], tp.get("category_id"), tp["id"])
        toast(self.app.root, f"{t('recording', self.lang)}: {tp['title']}")
        self.render()

    def on_timer_tick(self, elapsed: int, running: bool):
        # Update timer card label only (cheap)
        if hasattr(self, "_timer_lbl") and self._timer_lbl.winfo_exists():
            self._timer_lbl.config(text=fmt_duration(elapsed))


# =================== GOALS ===================
class GoalsScreen(BaseScreen):
    def render(self):
        super().render()
        lang = self.lang
        tk.Label(self.inner, text=t("goalsStreaks", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=font(24, "bold"), anchor="w").pack(anchor="w", padx=24, pady=(24, 12))

        goals = database.all_goals()
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        if not goals:
            tk.Label(self.inner, text=t("noGoals", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_FAINT, font=font(13)).pack(anchor="w", padx=24, pady=24)
        else:
            today = _dt.datetime.now()
            for g in goals:
                if g["period"] == "daily":
                    s, e = today, today
                elif g["period"] == "weekly":
                    s, e = start_of_week(today), end_of_week(today)
                else:
                    s, e = start_of_month(today), end_of_month(today)
                total = database.total_seconds_between(
                    s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), g.get("category_id")
                )
                target = g["target_minutes"] * 60
                progress = min(1.0, total / target) if target > 0 else 0
                cat = cat_map.get(g.get("category_id")) if g.get("category_id") else None
                cat_name = (cat["name_fa"] if lang == "fa" else cat["name_en"]) if cat else t("all", lang)
                st = database.streak_for_goal(g["id"])

                gc = card(self.inner)
                gc.pack(fill="x", padx=24, pady=8)
                # Ring on the left
                ring_col = tk.Frame(gc, bg=config.CHARCOAL)
                ring_col.pack(side="left", padx=(12, 8), pady=12)
                r_cv = tk.Canvas(ring_col, width=80, height=80,
                                  bg=config.CHARCOAL, highlightthickness=0)
                r_cv.pack()
                charts_mod.progress_ring(r_cv, 40, 40, 80, progress,
                                          config.GOLD, config.SURFACE_HI,
                                          f"{int(progress * 100)}%", config.TEXT)
                info_col = tk.Frame(gc, bg=config.CHARCOAL)
                info_col.pack(side="left", fill="x", expand=True, padx=(8, 12), pady=12)
                tk.Label(info_col, text=f"{t(g['period'], lang)} — {cat_name}",
                         bg=config.CHARCOAL, fg=config.TEXT, font=font(14, "bold"),
                         anchor="w").pack(anchor="w")
                tk.Label(info_col, text=f"{fmt_human(total, lang)} / {fmt_human(target, lang)}",
                         bg=config.CHARCOAL, fg=config.GOLD, font=font(12),
                         anchor="w").pack(anchor="w")
                if st:
                    cur = st["current"]; lng = st["longest"]
                    tk.Label(info_col,
                             text=f"{t('streak', lang)}: {to_fa_digits(cur) if lang == 'fa' else cur} {t('days', lang)} ({t('best', lang)}: {to_fa_digits(lng) if lang == 'fa' else lng})",
                             bg=config.CHARCOAL, fg=config.TEXT_DIM, font=font(11),
                             anchor="w").pack(anchor="w")
                del_btn = tk.Button(gc, text=t("delete", lang), bg=config.CHARCOAL,
                                     fg=config.DANGER, font=font(11), relief="flat",
                                     bd=0, cursor="hand2",
                                     command=lambda _g=g: self._delete_goal(_g))
                del_btn.pack(side="right", padx=12)

        # Badges
        section_header(self.inner, t("badges", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        badges = database.all_badges()
        if not badges:
            tk.Label(self.inner, text=t("noBadges", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_FAINT, font=font(13)).pack(anchor="w", padx=24, pady=24)
        else:
            bwrap = tk.Frame(self.inner, bg=config.MATTE_BLACK)
            bwrap.pack(fill="x", padx=24, pady=(0, 8))
            for b in badges:
                row = tk.Frame(bwrap, bg=config.MATTE_BLACK)
                row.pack(fill="x", pady=4)
                tk.Label(row, text="🏅", bg=config.MATTE_BLACK, font=font(24)).pack(side="left")
                tk.Label(row, text=(b["title_fa"] if lang == "fa" else b["title_en"]),
                         bg=config.MATTE_BLACK, fg=config.GOLD, font=font(14, "bold")).pack(side="left", padx=8)

        # New goal button
        styled_button(self.inner, "gold", t("newGoal", lang),
                       command=self.app.open_goal_modal).pack(fill="x", padx=24, pady=16)

    def _delete_goal(self, g):
        from tkinter import messagebox
        if messagebox.askyesno(t("delete", self.lang), f"{t('delete', self.lang)}?"):
            database.delete_goal(g["id"])
            self.render()


# =================== STATS ===================
class StatsScreen(BaseScreen):
    PRESETS = [
        ("today", "todayPreset"),
        ("7d", "sevenDays"),
        ("30d", "thirtyDays"),
        ("month", "thisMonth"),
        ("year", "thisYear"),
    ]

    def __init__(self, parent, app, lang):
        super().__init__(parent, app, lang)
        self.preset = "7d"
        self._preset_chips = {}

    def _range(self):
        today = _dt.datetime.now()
        if self.preset == "today":
            return today, today
        if self.preset == "7d":
            return add_days(today, -6), today
        if self.preset == "30d":
            return add_days(today, -29), today
        if self.preset == "month":
            return start_of_month(today), end_of_month(today)
        if self.preset == "year":
            return start_of_year(today), end_of_year(today)
        return add_days(today, -6), today

    def render(self):
        super().render()
        lang = self.lang
        tk.Label(self.inner, text=t("statistics", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=font(24, "bold"), anchor="w").pack(anchor="w", padx=24, pady=(24, 12))

        # Preset chips row
        chips_row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        chips_row.pack(fill="x", padx=24, pady=(0, 12))
        self._preset_chips.clear()
        for k, lk in self.PRESETS:
            c = chip(chips_row, t(lk, lang), selected=(k == self.preset),
                      command=lambda _k=k: self._select_preset(_k))
            c.pack(side="left", padx=(0, 8))
            self._preset_chips[k] = c

        start, end = self._range()
        s_iso = start.strftime("%Y-%m-%d")
        e_iso = end.strftime("%Y-%m-%d")
        acts = database.activities_by_date_range(s_iso, e_iso)
        total = sum(int(a.get("duration_sec", 0) or 0) for a in acts)

        # Total card
        tc = card(self.inner)
        tc.pack(fill="x", padx=24, pady=8)
        tk.Label(tc, text=t("total", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=font(12), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(tc, text=fmt_human(total, lang), bg=config.CHARCOAL,
                 fg=config.GOLD, font=font(32, "bold"), anchor="w").pack(anchor="w", padx=16, pady=4)
        tk.Label(tc, text=f"{fmt_short_date(start, lang)} → {fmt_short_date(end, lang)}",
                 bg=config.CHARCOAL, fg=config.TEXT_FAINT, font=font(11),
                 anchor="w").pack(anchor="w", padx=16, pady=(0, 12))

        if not acts:
            tk.Label(self.inner, text=t("noData", lang), bg=config.MATTE_BLACK,
                     fg=config.TEXT_FAINT, font=font(13)).pack(anchor="w", padx=24, pady=32)
        else:
            # Bar chart (daily trend) for ≤31-day ranges
            if (end - start).days <= 31:
                days = list(date_range(start, end))
                per_day = database.seconds_per_day(s_iso, e_iso)
                bar_data = [{
                    "label": to_fa_digits(d.day) if lang == "fa" else str(d.day),
                    "value": per_day.get(d.strftime("%Y-%m-%d"), 0),
                    "color": config.GOLD,
                } for d in days]
                bc = card(self.inner)
                bc.pack(fill="x", padx=24, pady=8)
                tk.Label(bc, text=t("dailyTrend", lang), bg=config.CHARCOAL,
                         fg=config.TEXT, font=font(14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
                bar_cv = tk.Canvas(bc, width=460, height=160,
                                    bg=config.CHARCOAL, highlightthickness=0)
                bar_cv.pack(padx=8, pady=(0, 12))
                charts_mod.bar_chart(bar_cv, 8, 8, 444, 144, bar_data)

            # Donut chart (category share)
            cats = database.all_categories()
            cat_map = {c["id"]: c for c in cats}
            per_cat = database.seconds_per_category(s_iso, e_iso)
            donut_data = []
            for cid, sec in per_cat[:6]:
                c = cat_map.get(cid)
                donut_data.append({
                    "label": (c["name_fa"] if lang == "fa" else c["name_en"]) if c else "—",
                    "value": sec,
                    "color": c["color"] if c else config.TEXT_DIM,
                })
            dc = card(self.inner)
            dc.pack(fill="x", padx=24, pady=8)
            tk.Label(dc, text=t("categoryShare", lang), bg=config.CHARCOAL,
                     fg=config.TEXT, font=font(14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
            drow = tk.Frame(dc, bg=config.CHARCOAL)
            drow.pack(fill="x", padx=16, pady=(0, 12))
            d_cv = tk.Canvas(drow, width=140, height=140,
                              bg=config.CHARCOAL, highlightthickness=0)
            d_cv.pack(side="left")
            charts_mod.donut_chart(d_cv, 70, 70, 50, donut_data, 18)
            legend = tk.Frame(drow, bg=config.CHARCOAL)
            legend.pack(side="left", fill="x", expand=True, padx=16)
            for d in donut_data[:4]:
                lr = tk.Frame(legend, bg=config.CHARCOAL)
                lr.pack(fill="x", pady=2)
                tk.Frame(lr, bg=d["color"], width=10, height=10).pack(side="left", padx=(0, 6))
                tk.Label(lr, text=d["label"], bg=config.CHARCOAL,
                         fg=config.TEXT_DIM, font=font(11), anchor="w").pack(side="left", fill="x", expand=True)
                tk.Label(lr, text=fmt_human(d["value"], lang), bg=config.CHARCOAL,
                         fg=config.GOLD, font=font(11, "bold")).pack(side="right")

            # Heatmap (year)
            hc = card(self.inner)
            hc.pack(fill="x", padx=24, pady=8)
            tk.Label(hc, text=t("yearHeatmap", lang), bg=config.CHARCOAL,
                     fg=config.TEXT, font=font(14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
            h_cv = tk.Canvas(hc, width=540, height=110,
                              bg=config.CHARCOAL, highlightthickness=0)
            h_cv.pack(padx=8, pady=(0, 12))
            year_start = start_of_year(_dt.datetime.now())
            year_end = end_of_year(_dt.datetime.now())
            heat_data = database.seconds_per_day(
                year_start.strftime("%Y-%m-%d"), year_end.strftime("%Y-%m-%d")
            )
            charts_mod.heatmap(h_cv, 4, 4, 530, 100, _dt.datetime.now().year, heat_data, 11)

            # Trends card
            trc = card(self.inner)
            trc.pack(fill="x", padx=24, pady=8)
            tk.Label(trc, text=t("trends", lang), bg=config.CHARCOAL,
                     fg=config.TEXT, font=font(14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
            # Best day
            per_day = database.seconds_per_day(s_iso, e_iso)
            best_day, best_sec = None, 0
            for k, v in per_day.items():
                if v > best_sec:
                    best_sec = v
                    best_day = k
            # Peak hour (today only)
            peak_hour, peak_sec = -1, 0
            if (end - start).days <= 1:
                hours = database.seconds_per_hour(e_iso)
                for hr, sc in enumerate(hours):
                    if sc > peak_sec:
                        peak_sec = sc
                        peak_hour = hr
            n_days = max(1, (end - start).days + 1)
            avg = total // n_days
            trends = []
            if best_day:
                bd = _dt.datetime.strptime(best_day, "%Y-%m-%d")
                trends.append((t("bestDay", lang),
                               f"{fmt_short_date(bd, lang)} — {fmt_human(best_sec, lang)}"))
            if peak_hour >= 0:
                ph_txt = to_fa_digits(f"{peak_hour:02d}") if lang == "fa" else f"{peak_hour:02d}"
                trends.append((t("peakHour", lang), f"{ph_txt}:00 — {fmt_human(peak_sec, lang)}"))
            trends.append((t("dailyAvg", lang), fmt_human(avg, lang)))
            for k, v in trends:
                row = tk.Frame(trc, bg=config.CHARCOAL)
                row.pack(fill="x", padx=16, pady=4)
                tk.Label(row, text=k, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                         font=font(12), anchor="w").pack(side="left")
                tk.Label(row, text=v, bg=config.CHARCOAL, fg=config.GOLD,
                         font=font(12, "bold"), anchor="e").pack(side="right")
            # Bottom padding inside trends card
            tk.Frame(trc, bg=config.CHARCOAL, height=12).pack()

        # Export buttons
        ex_row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        ex_row.pack(fill="x", padx=24, pady=(16, 24))
        styled_button(ex_row, "outline", t("exportPdf", lang), small=True,
                       command=self._export_pdf).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(ex_row, "outline", t("exportCsv", lang), small=True,
                       command=self._export_csv).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _select_preset(self, key):
        self.preset = key
        for k, c in self._preset_chips.items():
            new_sel = (k == key)
            # Re-create chip styling: easiest is to reconfigure
            if new_sel:
                c.config(bg=config.GOLD, fg=config.MATTE_BLACK,
                         activebackground=config.GOLD_SOFT,
                         highlightbackground=config.GOLD,
                         font=font(12, "bold"))
            else:
                c.config(bg=config.CHARCOAL, fg=config.TEXT,
                         activebackground=config.SURFACE_HI,
                         highlightbackground=config.SURFACE_HI,
                         font=font(12, "normal"))
        self.render()

    def _export_pdf(self):
        s, e = self._range()
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"rask_report_{s.strftime('%Y-%m-%d')}_to_{e.strftime('%Y-%m-%d')}.pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            exporters.export_pdf(s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), self.lang, path)
            toast(self.app.root, t("pdfSaved", self.lang))
        except Exception as ex:
            toast(self.app.root, f"PDF error: {ex}")

    def _export_csv(self):
        s, e = self._range()
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"rask_export_{s.strftime('%Y-%m-%d')}_to_{e.strftime('%Y-%m-%d')}.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            n = exporters.export_csv(s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), path)
            toast(self.app.root, f"{t('csvSaved', self.lang)}: {to_fa_digits(n) if self.lang == 'fa' else n}")
        except Exception as ex:
            toast(self.app.root, f"CSV error: {ex}")


# =================== SETTINGS ===================
class SettingsScreen(BaseScreen):
    def render(self):
        super().render()
        lang = self.lang
        tk.Label(self.inner, text=t("settingsTitle", lang), bg=config.MATTE_BLACK,
                 fg=config.TEXT, font=font(24, "bold"), anchor="w").pack(anchor="w", padx=24, pady=(24, 12))

        # Appearance
        section_header(self.inner, t("appearance", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        app_card = card(self.inner)
        app_card.pack(fill="x", padx=24)
        row = tk.Frame(app_card, bg=config.CHARCOAL)
        row.pack(fill="x", padx=16, pady=12)
        tk.Label(row, text=t("language", lang), bg=config.CHARCOAL,
                 fg=config.TEXT, font=font(14)).pack(side="left")
        lang_row = tk.Frame(row, bg=config.CHARCOAL)
        lang_row.pack(side="right")
        self.lang_fa = chip(lang_row, "فارسی", selected=(lang == "fa"),
                             command=lambda: self._set_lang("fa"))
        self.lang_fa.pack(side="left", padx=(0, 4))
        self.lang_en = chip(lang_row, "English", selected=(lang == "en"),
                             command=lambda: self._set_lang("en"))
        self.lang_en.pack(side="left")

        # App lock
        section_header(self.inner, t("appLock", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        lock_card = card(self.inner)
        lock_card.pack(fill="x", padx=24)
        lr = tk.Frame(lock_card, bg=config.CHARCOAL)
        lr.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(lr, text=t("currentMode", lang), bg=config.CHARCOAL,
                 fg=config.TEXT, font=font(14)).pack(side="left")
        mode = database.kv_get("lock_mode", "none") or "none"
        mode_label = t("pin", lang) if mode == "pin" else (t("biometric", lang) if mode == "biometric" else t("none", lang))
        tk.Label(lr, text=mode_label, bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=font(13)).pack(side="right")
        self.pin_entry = tk.Entry(lock_card, show="•", bg=config.MATTE_BLACK,
                                   fg=config.TEXT, insertbackground=config.GOLD,
                                   font=font(15), relief="flat", width=20)
        self.pin_entry.pack(fill="x", padx=16, pady=8)
        # Bottom underline
        tk.Frame(lock_card, bg=config.GOLD, height=2).pack(fill="x", padx=16)
        lock_btns = tk.Frame(lock_card, bg=config.CHARCOAL)
        lock_btns.pack(fill="x", padx=16, pady=12)
        styled_button(lock_btns, "gold", t("setPin", lang), small=True,
                       command=self._set_pin).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(lock_btns, "outline", t("enableBiometric", lang), small=True,
                       command=self._enable_bio).pack(side="left", fill="x", expand=True, padx=(4, 0))
        styled_button(lock_card, "ghost", t("clearLock", lang), small=True,
                       command=self._clear_lock).pack(fill="x", padx=16, pady=(0, 12))

        # Backup & restore
        section_header(self.inner, t("backupRestore", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        bk_card = card(self.inner)
        bk_card.pack(fill="x", padx=24)
        self.bk_pwd = tk.Entry(bk_card, show="•", bg=config.MATTE_BLACK,
                                fg=config.TEXT, insertbackground=config.GOLD,
                                font=font(15), relief="flat")
        self.bk_pwd.pack(fill="x", padx=16, pady=(12, 4))
        self.bk_pwd.insert(0, t("backupPassword", lang))
        self.bk_pwd.bind("<FocusIn>", lambda _e: self._clear_placeholder(self.bk_pwd, t("backupPassword", lang)))
        self.bk_pwd.bind("<FocusOut>", lambda _e: self._restore_placeholder(self.bk_pwd, t("backupPassword", lang)))
        tk.Frame(bk_card, bg=config.GOLD, height=2).pack(fill="x", padx=16)
        bk_btns = tk.Frame(bk_card, bg=config.CHARCOAL)
        bk_btns.pack(fill="x", padx=16, pady=12)
        styled_button(bk_btns, "gold", t("exportBackup", lang), small=True,
                       command=self._export_backup).pack(side="left", fill="x", expand=True, padx=(0, 4))
        styled_button(bk_btns, "outline", t("restoreBackup", lang), small=True,
                       command=self._restore_backup).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # About
        section_header(self.inner, t("about", lang)).pack(anchor="w", padx=24, pady=(16, 8))
        ab_card = card(self.inner)
        ab_card.pack(fill="x", padx=24, pady=(0, 24))
        tk.Label(ab_card, text=f"Rask v{config.APP_VERSION}", bg=config.CHARCOAL,
                 fg=config.GOLD, font=font(16, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(ab_card, text=t("aboutTagline", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=font(12), anchor="w").pack(anchor="w", padx=16, pady=(4, 0))
        tk.Label(ab_card, text="© 2026 Littlehomemade Studio", bg=config.CHARCOAL,
                 fg=config.TEXT_FAINT, font=font(10), anchor="w").pack(anchor="w", padx=16, pady=(8, 12))

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=config.TEXT)

    def _restore_placeholder(self, entry, placeholder):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg=config.TEXT_FAINT)

    def _set_lang(self, lang):
        self.lang = lang
        self.app.set_lang(lang)
        self.render()

    def _set_pin(self):
        pin = self.pin_entry.get()
        if len(pin) < config.PIN_MIN_LEN:
            toast(self.app.root, t("pinTooShort", self.lang))
            return
        try:
            crypto.setup_pin(pin)
            self.pin_entry.delete(0, tk.END)
            toast(self.app.root, t("pinSet", self.lang))
            self.render()
        except Exception as ex:
            toast(self.app.root, str(ex))

    def _enable_bio(self):
        try:
            crypto.setup_biometric()
            toast(self.app.root, t("biometricEnabled", self.lang))
            self.render()
        except Exception as ex:
            toast(self.app.root, str(ex) or t("biometricUnavailable", self.lang))

    def _clear_lock(self):
        crypto.clear_lock()
        toast(self.app.root, t("lockCleared", self.lang))
        self.render()

    def _export_backup(self):
        pwd = self.bk_pwd.get()
        if pwd == t("backupPassword", self.lang) or len(pwd) < 6:
            toast(self.app.root, t("passwordTooShort", self.lang))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".rask",
            initialfile="rask_backup.rask",
            filetypes=[("Rask backup", "*.rask")],
        )
        if not path:
            return
        try:
            crypto.export_to_file(path, pwd)
            toast(self.app.root, t("backupSaved", self.lang))
        except Exception as ex:
            toast(self.app.root, f"Backup error: {ex}")

    def _restore_backup(self):
        pwd = self.bk_pwd.get()
        if pwd == t("backupPassword", self.lang) or not pwd:
            toast(self.app.root, t("enterPassword", self.lang))
            return
        path = filedialog.askopenfilename(
            filetypes=[("Rask backup", "*.rask"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            crypto.import_from_file(path, pwd)
            toast(self.app.root, t("restored", self.lang))
            self.app.switch_tab("home")
        except Exception as ex:
            toast(self.app.root, f"Restore error: {ex}")
