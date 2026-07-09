"""
goals.py — Goals & streaks screen.

Lists active goals with progress rings + streak info. Allows create / edit /
delete via a dialog. Also shows earned badges.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from rask import config as cfg
from rask.data import repositories as repos
from rask.data.models import Goal, Streak, fmt_minutes_human
from rask.ui.components import (
    GoldCard, GoldButton, OutlinedButton, SectionHeader, EmptyState,
    GoldTextField, Chip,
)
from rask.widgets.charts import ProgressRing
from rask.utils import date_utils as du


class GoalsScreen(FloatLayout):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._build()
        self.refresh()

    def _build(self):
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        root = BoxLayout(orientation="vertical",
                         padding=[cfg.SPACE["lg"], cfg.SPACE["xl"]],
                         spacing=cfg.SPACE["md"])
        root.add_widget(Label(
            text="اهداف و زنجیره‌ها" if self._lang == "fa" else "Goals & streaks",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h3"], bold=True,
            size_hint_y=None, height=44,
        ))

        self._scroll = ScrollView()
        self._list = BoxLayout(orientation="vertical", spacing=cfg.SPACE["md"],
                               size_hint_y=None)
        self._list.bind(minimum_height=self._list.setter("height"))
        self._scroll.add_widget(self._list)
        root.add_widget(self._scroll)

        add = GoldButton(
            text="+ هدف جدید" if self._lang == "fa" else "+ New goal",
            size_hint_y=None, height=48,
        )
        add.bind(on_release=lambda *_: self._open_new())
        root.add_widget(add)

        self.add_widget(root)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def refresh(self, *_):
        self._list.clear_widgets()
        goals = repos.GoalRepository.all()
        if not goals:
            self._list.add_widget(EmptyState(
                text="هنوز هدفی تعیین نکرده‌ای"
                     if self._lang == "fa"
                     else "No goals yet"
            ))
        cats = {c.id: c for c in repos.CategoryRepository.all()}
        for g in goals:
            self._list.add_widget(_GoalCard(g, cats.get(g.category_id),
                                             self._lang, on_delete=self.refresh,
                                             on_edit=self.refresh))

        # Badges
        self._list.add_widget(SectionHeader(
            text="نشان‌ها" if self._lang == "fa" else "Badges"
        ))
        badges = repos.BadgeRepository.all()
        if not badges:
            self._list.add_widget(EmptyState(
                text="هنوز نشان‌ای گرفته نشده"
                     if self._lang == "fa"
                     else "No badges earned yet"
            ))
        else:
            for b in badges:
                self._list.add_widget(Label(
                    text=(b.title_fa if self._lang == "fa" else b.title_en),
                    color=cfg.GOLD, size_hint_y=None, height=32,
                    halign="left", font_size=cfg.FONT_SIZES["body"],
                ))

    def _open_new(self):
        # Simple: creates a default daily 60-min goal
        g = Goal(period=cfg.PERIOD_DAILY, target_minutes=60)
        repos.GoalRepository.upsert(g)
        self.refresh()


# === Single goal card ===

class _GoalCard(GoldCard):
    def __init__(self, goal: Goal, category, lang: str,
                 on_delete=None, on_edit=None, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 130)
        super().__init__(**kw)
        self.goal = goal
        self.cat = category
        self._lang = lang
        self._on_delete = on_delete
        self._on_edit = on_edit

        today = date.today()
        if goal.period == cfg.PERIOD_DAILY:
            start, end = today, today
        elif goal.period == cfg.PERIOD_WEEKLY:
            start = du.start_of_week(today)
            end = du.end_of_week(today)
        else:
            start = du.start_of_month(today)
            end = du.end_of_month(today)

        total = repos.ActivityRepository.total_seconds_between(
            start.isoformat(), end.isoformat(), goal.category_id
        )
        target = goal.target_minutes * 60
        progress = min(1.0, total / target) if target > 0 else 0.0

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=90)
        # Progress ring
        ring = ProgressRing(size_hint=(None, None), size=(80, 80),
                            progress=progress,
                            label_text=f"{int(progress * 100)}%")
        top.add_widget(ring)
        # Info
        info = BoxLayout(orientation="vertical", spacing=2)
        period_lbl = {
            cfg.PERIOD_DAILY: "روزانه" if lang == "fa" else "Daily",
            cfg.PERIOD_WEEKLY: "هفتگی" if lang == "fa" else "Weekly",
            cfg.PERIOD_MONTHLY: "ماهانه" if lang == "fa" else "Monthly",
        }.get(goal.period, goal.period)
        cat_name = (category.name_fa if lang == "fa" and category
                    else category.name_en) if category else (
            "همه" if lang == "fa" else "All"
        )
        info.add_widget(Label(
            text=f"{period_lbl} — {cat_name}",
            color=cfg.TEXT, font_size=cfg.FONT_SIZES["body"], bold=True,
            halign="left", size_hint_y=None, height=22,
        ))
        info.add_widget(Label(
            text=f"{fmt_minutes_human(total, lang=lang)} / "
                 f"{fmt_minutes_human(target, lang=lang)}",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["small"],
            halign="left", size_hint_y=None, height=20,
        ))
        # Streak
        st = repos.StreakRepository.for_goal(goal.id)
        if st:
            info.add_widget(Label(
                text=(
                    f"زنجیره: {_fa(st.current)} روز (رکورد: {_fa(st.longest)})"
                    if lang == "fa"
                    else f"Streak: {st.current} days (best: {st.longest})"
                ),
                color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["tiny"],
                halign="left", size_hint_y=None, height=18,
            ))
        top.add_widget(info)
        self.add_widget(top)

        # Delete button
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=32, spacing=cfg.SPACE["sm"])
        btns.add_widget(Label(size_hint_x=0.6))
        del_btn = OutlinedButton(
            text="حذف" if lang == "fa" else "Delete",
            size_hint_x=0.4, height=32,
        )
        del_btn.bind(on_release=self._on_del)
        btns.add_widget(del_btn)
        self.add_widget(btns)

    def _on_del(self, *_):
        repos.GoalRepository.delete(self.goal.id)
        if self._on_delete:
            self._on_delete()


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
def _fa(n) -> str:
    return str(n).translate(_FA_DIGITS)
