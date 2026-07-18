"""screens_main.py — Home, Goals, Stats, Settings screens.

1:1 mirror of:
  - web/index.html #screen-home  (greeting, date, today-card with ring,
    active timer card, quick templates, recent activities)
  - web/index.html #screen-goals (goals list with rings + streaks, badges,
    "+ New goal" button)
  - web/index.html #screen-stats (preset chips, total card, bar/donut/heatmap,
    trends, PDF/CSV export buttons)
  - web/index.html #screen-settings (language, app lock, backup/restore, about)

Each screen extends BaseScreen which provides a scrollable container.
The render() method is called whenever the screen becomes visible.
"""
from __future__ import annotations
import datetime as _dt
import os
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from typing import Callable, Optional

from .. import config
from .. import database
from .. import timer_service
from .. import crypto
from .. import exporters
from .. import charts as charts_mod
from .. import analytics
from .. import voice
from .. import recurring
from .. import notifications
from .. import widgets
from ..widgets import (
    GoldButton, IconButton, Chip, Card, Field, TextArea, Switch, Slider,
    ProgressBar, FAB, BottomNav, Toast, Modal, Spinner, Divider, Badge,
    Avatar, SegmentedControl, SearchBar, Toolbar, EmptyState, StatCard,
    ActivityRow, GoalCard, ScrollableFrame,
    section_header, greeting_label, date_label, body_label, stat_label,
    get_font,
)
from ..date_utils import (
    today_iso, now_iso, fmt_date, fmt_short_date, fmt_relative, fmt_human,
    fmt_duration, fmt_human_short, fmt_long_date,
    add_days, start_of_week, end_of_week, start_of_month, end_of_month,
    start_of_year, end_of_year, date_range, preset_range, preset_label,
    today_jalali, gregorian_to_jalali,
)
from ..i18n import t, to_fa_digits, is_rtl


# =====================================================================
# === BASE SCREEN ===
# =====================================================================
class BaseScreen(ScrollableFrame):
    """Base class for the four main screens."""

    def __init__(self, parent, app, lang: str = "fa"):
        super().__init__(parent, bg=config.MATTE_BLACK)
        self.app = app
        self.lang = lang
        # Add some padding to the inner frame
        self.inner.config(padx=0, pady=0)

    def render(self):
        """Called when this screen becomes visible. Subclasses override."""
        self.clear()

    def set_lang(self, lang: str):
        self.lang = lang
        self.render()

    def _add_section_header(self, text: str, pady=(16, 8)) -> tk.Label:
        """Add a section header to the inner frame."""
        lbl = section_header(self.inner, text, self.lang)
        lbl.pack(anchor="w", padx=24, pady=pady)
        return lbl


# =====================================================================
# === HOME SCREEN (mirror web #screen-home) ===
# =====================================================================
class HomeScreen(BaseScreen):
    """The Home screen: greeting, today's progress ring, timer card,
    quick templates, and recent activities."""

    def __init__(self, parent, app, lang: str = "fa"):
        super().__init__(parent, app, lang)
        self._timer_card: Optional[tk.Frame] = None
        self._timer_time_label: Optional[tk.Label] = None

    def render(self):
        super().render()
        lang = self.lang
        # === Greeting ===
        h = _dt.datetime.now().hour
        if h < 12:
            gk = "goodMorning"
        elif h < 18:
            gk = "goodAfternoon"
        else:
            gk = "goodEvening"
        greeting_label(self.inner, t(gk, lang)).pack(anchor="w", padx=24, pady=(24, 0))
        date_label(self.inner, fmt_long_date(_dt.datetime.now(), lang)).pack(anchor="w", padx=24, pady=(0, 8))
        # === Today card ===
        self._render_today_card()
        # === Active timer card (only if timer is running or has elapsed) ===
        self._render_timer_card()
        # === Quick templates ===
        self._add_section_header(t("quickTemplates", lang))
        self._render_templates()
        # === Recent activities ===
        self._add_section_header(t("recentActivities", lang))
        self._render_recent_activities()
        # Bottom spacer (for FAB)
        tk.Frame(self.inner, bg=config.MATTE_BLACK, height=80).pack()

    def _render_today_card(self):
        lang = self.lang
        card = Card(self.inner, padding=0)
        card.pack(fill="x", padx=24, pady=8)
        # Two-column layout: ring on left, info on right
        left = tk.Frame(card, bg=config.CHARCOAL)
        left.pack(side="left", padx=(16, 8), pady=16)
        ring_canvas = tk.Canvas(left, width=140, height=140, bg=config.CHARCOAL,
                                 highlightthickness=0, bd=0)
        ring_canvas.pack()
        # Compute today's progress
        today = today_iso()
        total = database.total_seconds_on(today)
        goals = database.all_goals(active_only=True)
        daily_goal = next((g for g in goals if g["period"] == "daily" and not g.get("category_id")), None)
        if not daily_goal and goals:
            daily_goal = goals[0]
        target_sec = (int(daily_goal["target_minutes"]) * 60) if daily_goal else (config.DEFAULT_DAILY_GOAL_MIN * 60)
        progress = min(1.0, total / target_sec) if target_sec > 0 else 0
        ring_label = fmt_human(total, lang)
        color = config.SUCCESS if progress >= 1.0 else config.GOLD
        charts_mod.progress_ring(ring_canvas, 70, 70, 140, progress, color,
                                  config.SURFACE_HI, ring_label, config.TEXT,
                                  line_width=8, font_size=14)
        # Right column: today label, total, goal, streak
        right = tk.Frame(card, bg=config.CHARCOAL)
        right.pack(side="left", fill="x", expand=True, padx=(8, 16), pady=16)
        tk.Label(right, text=t("today", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(12), anchor="w").pack(anchor="w")
        tk.Label(right, text=fmt_human(total, lang), bg=config.CHARCOAL,
                 fg=config.GOLD, font=get_font(26, "bold"), anchor="w").pack(anchor="w", pady=(2, 4))
        if daily_goal:
            tk.Label(right, text=f"{t('goal', lang)}: {fmt_human(int(daily_goal['target_minutes']) * 60, lang)}",
                     bg=config.CHARCOAL, fg=config.TEXT_DIM, font=get_font(12), anchor="w").pack(anchor="w")
        # Streak
        top_streaks = database.top_streaks(1)
        if top_streaks and top_streaks[0].get("current", 0) > 0:
            cur = top_streaks[0]["current"]
            cur_str = to_fa_digits(cur) if lang == "fa" else str(cur)
            streak_text = f"🔥 {t('streak', lang)}: {cur_str} {t('days', lang)}"
            tk.Label(right, text=streak_text, bg=config.CHARCOAL,
                     fg=config.GOLD, font=get_font(13, "bold"), anchor="w").pack(anchor="w", pady=(4, 0))

    def _render_timer_card(self):
        lang = self.lang
        # Show only if timer is running OR has elapsed > 0
        if not (timer_service.is_running() or timer_service.elapsed_sec() > 0):
            return
        card = Card(self.inner, padding=16, bg=config.CHARCOAL,
                     border_color=config.GOLD_DIM)
        card.pack(fill="x", padx=24, pady=8)
        # Title
        title = timer_service.current_title() or t("recording", lang)
        tk.Label(card, text=title, bg=config.CHARCOAL, fg=config.TEXT,
                 font=get_font(13, "bold"), anchor="w").pack(anchor="w")
        # Time
        elapsed = timer_service.elapsed_sec()
        time_str = fmt_duration(elapsed)
        if lang == "fa":
            time_str = to_fa_digits(time_str)
        self._timer_time_label = tk.Label(card, text=time_str, bg=config.CHARCOAL,
                                            fg=config.GOLD, font=get_font(32, "bold"),
                                            anchor="w")
        self._timer_time_label.pack(anchor="w", pady=(4, 8))
        # Buttons
        btn_frame = tk.Frame(card, bg=config.CHARCOAL)
        btn_frame.pack(fill="x")
        pause_label = t("pause", lang) if timer_service.is_running() else t("resume", lang)
        GoldButton(btn_frame, text=pause_label, command=self._on_pause,
                    kind="outline", size="sm", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("stopSave", lang), command=self._on_stop,
                    kind="gold", size="sm", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _on_pause(self):
        if timer_service.is_running():
            timer_service.pause()
        else:
            timer_service.resume()
        self.render()

    def _on_stop(self):
        activity_id = timer_service.stop_and_save()
        if activity_id:
            widgets.Toast(self.app.root, t("quickLogSaved", self.lang), kind="success")
        self.render()

    def _render_templates(self):
        lang = self.lang
        tpls = database.all_templates()
        if not tpls:
            empty = tk.Frame(self.inner, bg=config.MATTE_BLACK)
            empty.pack(fill="x", padx=24, pady=8)
            tk.Label(empty, text=t("noTemplates", lang) + " — ", bg=config.MATTE_BLACK,
                     fg=config.TEXT_FAINT, font=get_font(13)).pack(side="left")
            link = tk.Label(empty, text=t("addTemplate", lang), bg=config.MATTE_BLACK,
                            fg=config.GOLD, font=get_font(13, "bold"), cursor="hand2")
            link.pack(side="left")
            link.bind("<Button-1>", lambda e: self.app.open_template_modal())
            return
        row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        row.pack(fill="x", padx=24)
        for tp in tpls:
            cat = database.category_by_id(tp.get("category_id")) if tp.get("category_id") else None
            color = cat["color"] if cat else config.GOLD
            chip = Chip(row, text=tp["title"], selected=False, lang=lang,
                         command=lambda _t=tp: self._start_template(_t),
                         color=color)
            chip.pack(side="left", padx=(0, 8))

    def _start_template(self, template: dict):
        title = template["title"]
        cat_id = template.get("category_id")
        timer_service.start(title, cat_id, template.get("id"))
        widgets.Toast(self.app.root, f"{t('recording', self.lang)}: {title}",
                       kind="info")

    def _render_recent_activities(self):
        lang = self.lang
        recent = database.recent_activities(15)
        if not recent:
            empty = EmptyState(self.inner, icon="clock",
                                title=t("noActivities", lang),
                                subtitle=t("noActivitiesHint", lang), lang=lang)
            empty.pack(fill="x", pady=24)
            return
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        list_frame = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        list_frame.pack(fill="x", padx=24, pady=(0, 16))
        for a in recent:
            cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
            row = ActivityRow(list_frame, a, cat, lang,
                               on_click=lambda _a=a: self._on_activity_click(_a))
            row.pack(fill="x")

    def _on_activity_click(self, activity: dict):
        """Open edit activity modal (delegated to app)."""
        if hasattr(self.app, "open_edit_activity_modal"):
            self.app.open_edit_activity_modal(activity)

    def on_timer_tick(self, elapsed: int, running: bool):
        """Called when the timer ticks. Updates the timer card if visible."""
        if self._timer_time_label and self._timer_card and self._timer_card.winfo_exists():
            time_str = fmt_duration(elapsed)
            if self.lang == "fa":
                time_str = to_fa_digits(time_str)
            self._timer_time_label.config(text=time_str)
        else:
            # Timer card not visible — re-render to show it
            self.render()


# =====================================================================
# === GOALS SCREEN (mirror web #screen-goals) ===
# =====================================================================
class GoalsScreen(BaseScreen):
    """The Goals screen: list of goals with progress rings, streaks, badges."""

    def render(self):
        super().render()
        lang = self.lang
        # Title
        greeting_label(self.inner, t("goalsStreaks", lang)).pack(
            anchor="w", padx=24, pady=(24, 8))
        # Goals list
        self._render_goals()
        # Badges
        self._add_section_header(t("badges", lang))
        self._render_badges()
        # New goal button
        GoldButton(self.inner, text=t("newGoal", lang),
                    command=lambda: self.app.open_goal_modal(),
                    kind="gold", full_width=True).pack(
            fill="x", padx=24, pady=(16, 8))
        # Bottom spacer
        tk.Frame(self.inner, bg=config.MATTE_BLACK, height=80).pack()

    def _render_goals(self):
        lang = self.lang
        goals = database.all_goals(active_only=False)
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        if not goals:
            empty = EmptyState(self.inner, icon="target",
                                title=t("noGoals", lang),
                                subtitle=t("noGoalsHint", lang), lang=lang)
            empty.pack(fill="x", pady=24)
            return
        for g in goals:
            # Compute current total for this goal's period
            today = _dt.date.today()
            if g["period"] == "daily":
                start = end = today
            elif g["period"] == "weekly":
                start = start_of_week(today).date()
                end = end_of_week(today).date()
            else:  # monthly
                start = start_of_month(today).date()
                end = end_of_month(today).date()
            total = database.total_seconds_between(start.isoformat(), end.isoformat(),
                                                     g.get("category_id"))
            target = int(g["target_minutes"]) * 60
            progress = min(1.0, total / target) if target > 0 else 0
            cat = cat_map.get(g.get("category_id")) if g.get("category_id") else None
            streak = database.streak_for_goal(g["id"])
            card = GoalCard(self.inner, g, progress, total, target,
                             streak, cat, lang,
                             on_delete=lambda _g=g: self._on_delete_goal(_g))
            card.pack(fill="x", padx=24, pady=4)

    def _on_delete_goal(self, goal: dict):
        if messagebox.askyesno(config.APP_NAME, t("confirmDeleteGoal", self.lang)):
            database.delete_goal(goal["id"])
            self.render()

    def _render_badges(self):
        lang = self.lang
        badges = database.all_badges()
        if not badges:
            empty = EmptyState(self.inner, icon="award",
                                title=t("noBadges", lang),
                                subtitle=t("noBadgesHint", lang), lang=lang)
            empty.pack(fill="x", pady=24)
            return
        grid = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        grid.pack(fill="x", padx=24, pady=8)
        for i, b in enumerate(badges):
            cell = tk.Frame(grid, bg=config.CHARCOAL,
                            highlightbackground=config.DIVIDER,
                            highlightthickness=1)
            cell.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
            grid.grid_columnconfigure(i % 3, weight=1)
            # Badge icon
            icon_c = tk.Canvas(cell, width=48, height=48, bg=config.CHARCOAL,
                                highlightthickness=0, bd=0)
            icon_c.pack(pady=(8, 0))
            from .. import icons
            icons.draw_icon(icon_c, 10, 10, 28, "award",
                             color=config.GOLD, stroke_width=2)
            # Title
            title = b["title_fa"] if lang == "fa" else b["title_en"]
            tk.Label(cell, text=title, bg=config.CHARCOAL, fg=config.GOLD,
                     font=get_font(10, "bold"), wraplength=120,
                     justify="center").pack(pady=(0, 8), padx=4)


# =====================================================================
# === STATS SCREEN (mirror web #screen-stats) ===
# =====================================================================
class StatsScreen(BaseScreen):
    """The Stats screen: preset chips, total card, charts, trends, exports."""

    def __init__(self, parent, app, lang: str = "fa"):
        super().__init__(parent, app, lang)
        self._preset = "7d"

    def render(self):
        super().render()
        lang = self.lang
        # Title
        greeting_label(self.inner, t("statistics", lang)).pack(
            anchor="w", padx=24, pady=(24, 8))
        # Preset chips
        self._render_presets()
        # Stats content
        self._render_stats()
        # Export buttons
        self._render_exports()
        # Bottom spacer
        tk.Frame(self.inner, bg=config.MATTE_BLACK, height=80).pack()

    def _render_presets(self):
        lang = self.lang
        row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        row.pack(fill="x", padx=24, pady=(0, 16))
        presets = [
            ("today", "todayPreset"),
            ("7d",    "sevenDays"),
            ("30d",   "thirtyDays"),
            ("month", "thisMonth"),
            ("year",  "thisYear"),
        ]
        for key, label_key in presets:
            chip = Chip(row, text=t(label_key, lang),
                         selected=(key == self._preset),
                         command=lambda _k=key: self._on_preset(_k),
                         lang=lang)
            chip.pack(side="left", padx=(0, 8))

    def _on_preset(self, preset: str):
        self._preset = preset
        self.render()

    def _render_stats(self):
        lang = self.lang
        start, end = preset_range(self._preset)
        summary = analytics.build_summary(start, end, lang)
        if summary["count"] == 0:
            empty = EmptyState(self.inner, icon="bar-chart-2",
                                title=t("noData", lang),
                                subtitle=t("noDataHint", lang), lang=lang)
            empty.pack(fill="x", pady=48)
            return
        # Total card
        total_card = Card(self.inner, padding=16)
        total_card.pack(fill="x", padx=24, pady=4)
        tk.Label(total_card, text=t("total", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(11), anchor="w").pack(anchor="w")
        tk.Label(total_card, text=fmt_human(int(summary["total_sec"]), lang),
                 bg=config.CHARCOAL, fg=config.GOLD, font=get_font(32, "bold"),
                 anchor="w").pack(anchor="w", pady=(2, 4))
        period_label = preset_label(self._preset, lang)
        tk.Label(total_card, text=period_label, bg=config.CHARCOAL,
                 fg=config.TEXT_FAINT, font=get_font(11), anchor="w").pack(anchor="w")
        # Comparison vs previous period
        comp = summary.get("comparison", {})
        if comp and comp.get("previous_sec", 0) > 0:
            delta_pct = comp["delta_percent"]
            trend_kind = "up" if delta_pct > 0 else ("down" if delta_pct < 0 else "info")
            arrow = "↑" if delta_pct > 0 else ("↓" if delta_pct < 0 else "→")
            color = config.SUCCESS if delta_pct > 0 else (
                config.DANGER if delta_pct < 0 else config.TEXT_DIM
            )
            pct_str = f"{arrow} {abs(delta_pct):.1f}%"
            if lang == "fa":
                pct_str = to_fa_digits(pct_str)
            tk.Label(total_card, text=f"{t('vsLastPeriod', lang)}: {pct_str}",
                     bg=config.CHARCOAL, fg=color,
                     font=get_font(11, "bold"), anchor="w").pack(anchor="w", pady=(4, 0))
        # Stat cards row: count + active days
        stats_row = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        stats_row.pack(fill="x", padx=24, pady=8)
        count_card = StatCard(stats_row, label=t("totalActivities", lang),
                                value=to_fa_digits(summary["count"]) if lang == "fa" else str(summary["count"]),
                                lang=lang)
        count_card.pack(side="left", fill="x", expand=True, padx=(0, 4))
        days_card = StatCard(stats_row, label=t("activeDays", lang),
                              value=to_fa_digits(summary["active_days"]) if lang == "fa" else str(summary["active_days"]),
                              lang=lang)
        days_card.pack(side="right", fill="x", expand=True, padx=(4, 0))
        # Daily trend bar chart
        self._add_section_header(t("dailyTrend", lang))
        self._render_daily_trend(summary)
        # Category share donut
        self._add_section_header(t("categoryShare", lang))
        self._render_category_donut(summary)
        # Year heatmap
        self._add_section_header(t("yearHeatmap", lang))
        self._render_heatmap()
        # Trends & peaks
        self._add_section_header(t("trends", lang))
        self._render_trends(summary)
        # Insights
        if summary.get("insights"):
            self._add_section_header(t("insights", lang))
            insights_frame = tk.Frame(self.inner, bg=config.MATTE_BLACK)
            insights_frame.pack(fill="x", padx=24, pady=8)
            for insight in summary["insights"]:
                tk.Label(insights_frame, text=f"• {insight}", bg=config.MATTE_BLACK,
                         fg=config.TEXT_DIM, font=get_font(12), anchor="w",
                         wraplength=440, justify="left").pack(anchor="w", pady=2)
        # Scores
        self._add_section_header(t("productivityScore", lang))
        scores_frame = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        scores_frame.pack(fill="x", padx=24, pady=8)
        scores = [
            (t("productivityScore", lang), summary["productivity_score"]),
            (t("consistencyScore", lang), summary["consistency_score"]),
            (t("balanceScore", lang), summary["balance_score"]),
        ]
        for label, score in scores:
            row = tk.Frame(scores_frame, bg=config.CHARCOAL,
                          highlightbackground=config.DIVIDER,
                          highlightthickness=1)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=config.CHARCOAL, fg=config.TEXT,
                     font=get_font(12)).pack(side="left", padx=12, pady=10)
            score_str = f"{score:.0f} / 100"
            if lang == "fa":
                score_str = to_fa_digits(score_str)
            tk.Label(row, text=score_str, bg=config.CHARCOAL, fg=config.GOLD,
                     font=get_font(14, "bold")).pack(side="right", padx=12, pady=10)

    def _render_daily_trend(self, summary: dict):
        lang = self.lang
        per_day = summary.get("per_day", {})
        if not per_day:
            return
        start, end = preset_range(self._preset)
        # Build daily data for the range
        days = list(date_range(start, end))
        if len(days) > 60:
            # Aggregate by week
            return
        data = []
        for d in days:
            iso = d.date().isoformat() if isinstance(d, _dt.datetime) else d.isoformat()
            sec = per_day.get(iso, 0)
            label = ""
            if len(days) <= 7:
                # Show weekday short
                wd_keys = ["weekdayMonShort", "weekdayTueShort", "weekdayWedShort",
                            "weekdayThuShort", "weekdayFriShort", "weekdaySatShort",
                            "weekdaySunShort"]
                py_wd = (d.date() if isinstance(d, _dt.datetime) else d).weekday()
                label = t(wd_keys[py_wd], lang)
            elif len(days) <= 31:
                # Show day of month
                day = (d.date() if isinstance(d, _dt.datetime) else d).day
                label = str(day)
                if lang == "fa":
                    label = to_fa_digits(label)
            data.append({"label": label, "value": sec / 60, "color": config.GOLD})
        chart_card = Card(self.inner, padding=8)
        chart_card.pack(fill="x", padx=24, pady=4)
        chart_canvas = tk.Canvas(chart_card, width=460, height=180,
                                  bg=config.CHARCOAL, highlightthickness=0, bd=0)
        chart_canvas.pack(fill="x", padx=8, pady=8)
        charts_mod.bar_chart(chart_canvas, 8, 8, 444, 160, data,
                              {"showLabels": True, "showValues": False})

    def _render_category_donut(self, summary: dict):
        lang = self.lang
        top_cats = summary.get("top_categories", [])
        if not top_cats:
            return
        cats = database.all_categories()
        cat_map = {c["id"]: c for c in cats}
        data = []
        for tc in top_cats[:7]:
            cat = cat_map.get(tc["category_id"])
            color = cat["color"] if cat else config.GOLD
            name = (cat["name_fa"] if lang == "fa" else cat["name_en"]) if cat else "—"
            data.append({
                "label": name,
                "value": tc["seconds"],
                "color": color,
            })
        chart_card = Card(self.inner, padding=8)
        chart_card.pack(fill="x", padx=24, pady=4)
        chart_canvas = tk.Canvas(chart_card, width=460, height=180,
                                  bg=config.CHARCOAL, highlightthickness=0, bd=0)
        chart_canvas.pack(fill="x", padx=8, pady=8)
        charts_mod.donut_chart(chart_canvas, 100, 90, 50, data, line_width=18)
        # Legend on right
        from ..charts import legend
        legend(chart_canvas, 200, 30, [
            {"label": d["label"], "color": d["color"],
             "value": fmt_human(int(d["value"]), lang)}
            for d in data
        ])

    def _render_heatmap(self):
        lang = self.lang
        year = _dt.date.today().year
        data = database.yearly_heatmap(year)
        chart_card = Card(self.inner, padding=8)
        chart_card.pack(fill="x", padx=24, pady=4)
        chart_canvas = tk.Canvas(chart_card, width=460, height=180,
                                  bg=config.CHARCOAL, highlightthickness=0, bd=0)
        chart_canvas.pack(fill="x", padx=8, pady=8)
        charts_mod.heatmap(chart_canvas, 8, 20, 440, 140, year, data, cell_size=10)
        # Year label
        year_str = to_fa_digits(year) if lang == "fa" else str(year)
        chart_canvas.create_text(8, 8, text=year_str, fill=config.TEXT_DIM,
                                  font=get_font(11), anchor="nw")

    def _render_trends(self, summary: dict):
        lang = self.lang
        rows = []
        # Best day
        if summary.get("best_day"):
            d = _dt.date.fromisoformat(summary["best_day"])
            day_str = fmt_date(d, lang)
            sec_str = fmt_human(int(summary["best_day_sec"]), lang)
            rows.append((t("bestDay", lang), f"{day_str} — {sec_str}"))
        # Peak hour
        if summary.get("peak_hour") is not None:
            h = summary["peak_hour"]
            h_str = to_fa_digits(f"{h:02d}:00") if lang == "fa" else f"{h:02d}:00"
            rows.append((t("peakHour", lang), h_str))
        # Daily average
        avg_str = fmt_human(int(summary["daily_avg_sec"]), lang)
        rows.append((t("dailyAvg", lang), avg_str))
        # Average session
        ds = summary.get("duration_stats", {})
        if ds.get("count", 0) > 0:
            mean_str = fmt_human(int(ds["mean"]), lang)
            rows.append((t("averageSession", lang), mean_str))
            median_str = fmt_human(int(ds["median"]), lang)
            rows.append((t("medianSession", lang), median_str))
            longest_str = fmt_human(int(ds["max"]), lang)
            rows.append((t("longestSession", lang), longest_str))
        card = Card(self.inner, padding=8)
        card.pack(fill="x", padx=24, pady=4)
        for label, value in rows:
            row = tk.Frame(card, bg=config.CHARCOAL)
            row.pack(fill="x", padx=8, pady=4)
            tk.Label(row, text=label, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(12), anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=config.CHARCOAL, fg=config.GOLD,
                     font=get_font(12, "bold"), anchor="e").pack(side="right")

    def _render_exports(self):
        lang = self.lang
        btn_frame = tk.Frame(self.inner, bg=config.MATTE_BLACK)
        btn_frame.pack(fill="x", padx=24, pady=(16, 0))
        GoldButton(btn_frame, text=t("exportPdf", lang),
                    command=self._on_export_pdf, kind="outline", size="sm",
                    full_width=True).pack(side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("exportCsv", lang),
                    command=self._on_export_csv, kind="outline", size="sm",
                    full_width=True).pack(side="right", fill="x", expand=True, padx=(4, 0))

    def _on_export_pdf(self):
        lang = self.lang
        start, end = preset_range(self._preset)
        summary = exporters.build_summary(start, end, lang)
        activities = database.activities_by_date_range(start, end)
        default_name = f"rask-report-{start}-to-{end}.pdf"
        path = filedialog.asksaveasfilename(
            title=t("exportPdf", lang),
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            bytes_written = exporters.export_pdf(path, summary, activities, lang)
            widgets.Toast(self.app.root, t("pdfSaved", lang), kind="success")
        except Exception as e:
            widgets.Toast(self.app.root, f"{t('exportFailed', lang)}: {e}",
                           kind="danger")

    def _on_export_csv(self):
        lang = self.lang
        start, end = preset_range(self._preset)
        activities = database.activities_by_date_range(start, end)
        default_name = f"rask-activities-{start}-to-{end}.csv"
        path = filedialog.asksaveasfilename(
            title=t("exportCsv", lang),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            rows = exporters.export_csv(path, activities, lang)
            widgets.Toast(self.app.root, t("csvSaved", lang), kind="success")
        except Exception as e:
            widgets.Toast(self.app.root, f"{t('exportFailed', lang)}: {e}",
                           kind="danger")


# =====================================================================
# === SETTINGS SCREEN (mirror web #screen-settings) ===
# =====================================================================
class SettingsScreen(BaseScreen):
    """The Settings screen: language, app lock, backup/restore, about."""

    def render(self):
        super().render()
        lang = self.lang
        # Title
        greeting_label(self.inner, t("settingsTitle", lang)).pack(
            anchor="w", padx=24, pady=(24, 8))
        # === Appearance ===
        self._add_section_header(t("appearance", lang))
        self._render_appearance()
        # === App lock ===
        self._add_section_header(t("appLock", lang))
        self._render_app_lock()
        # === Backup & restore ===
        self._add_section_header(t("backupRestore", lang))
        self._render_backup()
        # === Reminders ===
        self._add_section_header(t("reminders", lang))
        self._render_reminders()
        # === Data management ===
        self._add_section_header(t("dataManagement", lang))
        self._render_data_management()
        # === About ===
        self._add_section_header(t("about", lang))
        self._render_about()
        # Bottom spacer
        tk.Frame(self.inner, bg=config.MATTE_BLACK, height=80).pack()

    def _render_appearance(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        # Language row
        row = tk.Frame(card, bg=config.CHARCOAL)
        row.pack(fill="x")
        tk.Label(row, text=t("language", lang), bg=config.CHARCOAL,
                 fg=config.TEXT, font=get_font(14)).pack(side="left")
        chips_frame = tk.Frame(card, bg=config.CHARCOAL)
        chips_frame.pack(side="right")
        Chip(chips_frame, text="فارسی", selected=(lang == "fa"),
              command=lambda: self._on_lang_change("fa"), lang=lang).pack(side="left", padx=(0, 4))
        Chip(chips_frame, text="English", selected=(lang == "en"),
              command=lambda: self._on_lang_change("en"), lang=lang).pack(side="left")
        # Divider
        tk.Frame(card, bg=config.DIVIDER, height=1).pack(fill="x", pady=8)

    def _on_lang_change(self, lang: str):
        self.app.set_lang(lang)

    def _render_app_lock(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        # Current mode
        mode = database.kv_get("lock_mode", "none") or "none"
        mode_label = t(mode, lang) if mode in ("none", "pin", "biometric") else mode
        row = tk.Frame(card, bg=config.CHARCOAL)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=t("currentMode", lang), bg=config.CHARCOAL,
                 fg=config.TEXT, font=get_font(14)).pack(side="left")
        tk.Label(row, text=mode_label, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                 font=get_font(13)).pack(side="right")
        # New PIN entry
        tk.Label(card, text=t("newPin", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(8, 4))
        self._pin_entry = Field(card, placeholder=t("newPin", lang), lang=lang)
        self._pin_entry.pack(fill="x", pady=(0, 8))
        # Buttons
        btn_frame = tk.Frame(card, bg=config.CHARCOAL)
        btn_frame.pack(fill="x")
        GoldButton(btn_frame, text=t("setPin", lang), command=self._on_set_pin,
                    kind="gold", size="sm", full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("clearLock", lang), command=self._on_clear_lock,
                    kind="ghost", size="sm", full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _on_set_pin(self):
        lang = self.lang
        pin = self._pin_entry.get()
        if not pin:
            return
        try:
            pin_hash = crypto.set_pin(pin)
            database.kv_set("pin_hash", pin_hash)
            database.kv_set("lock_mode", "pin")
            widgets.Toast(self.app.root, t("pinSet", lang), kind="success")
            self._pin_entry.clear()
            self.render()
        except ValueError as e:
            widgets.Toast(self.app.root, str(e), kind="danger")

    def _on_clear_lock(self):
        lang = self.lang
        database.kv_delete("pin_hash")
        database.kv_delete("lock_mode")
        widgets.Toast(self.app.root, t("lockCleared", lang), kind="info")
        self.render()

    def _render_backup(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        # Password entry
        tk.Label(card, text=t("backupPassword", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(11)).pack(anchor="w", pady=(0, 4))
        self._backup_pwd = Field(card, placeholder=t("backupPassword", lang),
                                  lang=lang)
        self._backup_pwd.pack(fill="x", pady=(0, 8))
        # Buttons
        btn_frame = tk.Frame(card, bg=config.CHARCOAL)
        btn_frame.pack(fill="x")
        if not crypto.crypto_available():
            tk.Label(card, text=t("err_crypto_unavailable", lang),
                     bg=config.CHARCOAL, fg=config.WARNING,
                     font=get_font(10)).pack(anchor="w", pady=(0, 4))
            return
        GoldButton(btn_frame, text=t("exportBackup", lang),
                    command=self._on_export_backup, kind="gold", size="sm",
                    full_width=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        GoldButton(btn_frame, text=t("restoreBackup", lang),
                    command=self._on_restore_backup, kind="outline", size="sm",
                    full_width=True).pack(
            side="right", fill="x", expand=True, padx=(4, 0))

    def _on_export_backup(self):
        lang = self.lang
        pwd = self._backup_pwd.get()
        if len(pwd) < config.BACKUP_MIN_PWD_LEN:
            widgets.Toast(self.app.root, t("passwordTooShort", lang), kind="danger")
            return
        default_name = f"rask-backup-{today_iso()}.rask"
        path = filedialog.asksaveasfilename(
            title=t("exportBackup", lang),
            defaultextension=config.BACKUP_FILE_EXT,
            filetypes=[("Rask Backup", f"*{config.BACKUP_FILE_EXT}"),
                       ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            payload = database.export_all()
            bytes_written = crypto.write_backup_file(path, payload, pwd)
            widgets.Toast(self.app.root, t("backupSaved", lang), kind="success")
        except Exception as e:
            widgets.Toast(self.app.root, f"{t('backupFailed', lang)}: {e}",
                           kind="danger")

    def _on_restore_backup(self):
        lang = self.lang
        pwd = self._backup_pwd.get()
        if not pwd:
            widgets.Toast(self.app.root, t("enterPassword", lang), kind="danger")
            return
        path = filedialog.askopenfilename(
            title=t("restoreBackup", lang),
            filetypes=[("Rask Backup", f"*{config.BACKUP_FILE_EXT}"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(config.APP_NAME, t("restoreConfirm", lang)):
            return
        try:
            payload = crypto.read_backup_file(path, pwd)
            database.replace_all(payload)
            widgets.Toast(self.app.root, t("restored", lang), kind="success")
            self.render()
        except Exception as e:
            widgets.Toast(self.app.root, f"{t('restoreFailed', lang)}: {e}",
                           kind="danger")

    def _render_reminders(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        row = tk.Frame(card, bg=config.CHARCOAL)
        row.pack(fill="x")
        tk.Label(row, text=t("enableReminders", lang), bg=config.CHARCOAL,
                 fg=config.TEXT, font=get_font(14)).pack(side="left")
        enabled = database.kv_get_bool("reminders_enabled", False)
        switch = Switch(row, value=enabled,
                         command=lambda v: database.kv_set_bool("reminders_enabled", v))
        switch.pack(side="right")

    def _render_data_management(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        # DB stats
        stats = database.stats_summary()
        rows = [
            (t("activitiesCount", lang), str(stats["activities"])),
            (t("categoriesCount", lang), str(stats["categories"])),
            (t("goalsCount", lang), str(stats["goals"])),
            (t("templatesCount", lang), str(stats["templates"])),
            (t("badgesCount", lang), str(stats["badges"])),
            (t("dbSize", lang), database.db_size_human()),
            (t("dataLocation", lang), str(config.DB_PATH)),
        ]
        for label, value in rows:
            row = tk.Frame(card, bg=config.CHARCOAL)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=config.CHARCOAL, fg=config.TEXT_DIM,
                     font=get_font(12), anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=config.CHARCOAL, fg=config.TEXT,
                     font=get_font(11), anchor="e").pack(side="right")
        # Action buttons
        btn_frame = tk.Frame(card, bg=config.CHARCOAL)
        btn_frame.pack(fill="x", pady=(12, 0))
        GoldButton(btn_frame, text=t("exportAllData", lang),
                    command=self._on_export_json, kind="ghost", size="sm",
                    full_width=True).pack(fill="x", pady=(0, 4))
        GoldButton(btn_frame, text=t("clearAllData", lang),
                    command=self._on_clear_data, kind="danger", size="sm",
                    full_width=True).pack(fill="x")

    def _on_export_json(self):
        lang = self.lang
        default_name = f"rask-data-{today_iso()}.json"
        path = filedialog.asksaveasfilename(
            title=t("exportAllData", lang),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            payload = database.export_all()
            bytes_written = exporters.export_json(path, payload)
            widgets.Toast(self.app.root, t("jsonSaved", lang), kind="success")
        except Exception as e:
            widgets.Toast(self.app.root, f"{t('exportFailed', lang)}: {e}",
                           kind="danger")

    def _on_clear_data(self):
        lang = self.lang
        if not messagebox.askyesno(config.APP_NAME, t("confirmClearAllData", lang)):
            return
        database.clear_all_data()
        widgets.Toast(self.app.root, t("toastCleared", lang), kind="info")
        self.render()

    def _render_about(self):
        lang = self.lang
        card = Card(self.inner, padding=16)
        card.pack(fill="x", padx=24, pady=4)
        tk.Label(card, text=f"{config.APP_NAME} v{config.APP_VERSION}",
                 bg=config.CHARCOAL, fg=config.GOLD,
                 font=get_font(16, "bold"), anchor="w").pack(anchor="w")
        tk.Label(card, text=t("aboutTagline", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(12), anchor="w").pack(anchor="w", pady=(2, 0))
        tk.Label(card, text=t("aboutDescription", lang), bg=config.CHARCOAL,
                 fg=config.TEXT_DIM, font=get_font(11), anchor="w",
                 wraplength=440, justify="left").pack(anchor="w", pady=(4, 0))
        tk.Label(card, text=config.APP_COPYRIGHT, bg=config.CHARCOAL,
                 fg=config.TEXT_FAINT, font=get_font(10), anchor="w").pack(anchor="w", pady=(8, 0))
