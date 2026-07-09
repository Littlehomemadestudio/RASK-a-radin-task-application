"""
home.py — Home screen.

Shows:
  - Today's progress ring (minutes vs daily goal)
  - Active stopwatch (if running) with Pause/Stop
  - Quick-log templates (horizontal chips)
  - Recent activities list
  - FAB to start a new activity
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from rask import config as cfg
from rask.data import database as db
from rask.data import repositories as repos
from rask.data.models import Activity, fmt_minutes_human
from rask.services import timer_service
from rask.ui.components import (
    GoldCard, GoldButton, OutlinedButton, FabButton, GoldDivider,
    SectionHeader, EmptyState, Chip, GoldTextField,
)
from rask.widgets.charts import ProgressRing
from rask.utils import date_utils as du


class HomeScreen(FloatLayout):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._build()
        self._tick_event = None
        timer_service.add_listener(self._on_timer_tick)
        Clock.schedule_once(self._refresh)

    def _build(self):
        # Background
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._redraw_bg, size=self._redraw_bg)

        # Root container
        root = BoxLayout(orientation="vertical",
                         padding=[cfg.SPACE["lg"], cfg.SPACE["xl"]],
                         spacing=cfg.SPACE["md"])

        # === Top: greeting + date ===
        self._greeting = Label(
            text=self._greeting_text(),
            color=cfg.TEXT, font_size=cfg.FONT_SIZES["h4"],
            bold=True, size_hint_y=None, height=40, halign="left",
        )
        self._greeting.bind(size=lambda inst, val:
                            setattr(inst, "text_size", val))
        root.add_widget(self._greeting)

        self._date_lbl = Label(
            text=du.fmt_date(date.today(), lang=self._lang),
            color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["caption"],
            size_hint_y=None, height=22, halign="left",
        )
        self._date_lbl.bind(size=lambda inst, val:
                            setattr(inst, "text_size", val))
        root.add_widget(self._date_lbl)

        # === Progress ring ===
        ring_box = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=180, spacing=cfg.SPACE["lg"])
        self._ring = ProgressRing(size_hint=(None, None), size=(160, 160))
        ring_box.add_widget(self._ring)

        info_box = BoxLayout(orientation="vertical", spacing=4)
        self._today_total = Label(
            text="", color=cfg.TEXT, font_size=cfg.FONT_SIZES["h3"],
            bold=True, size_hint_y=None, height=40, halign="left",
        )
        self._today_total.bind(size=lambda inst, val:
                               setattr(inst, "text_size", val))
        info_box.add_widget(self._today_total)

        self._goal_lbl = Label(
            text="", color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["caption"],
            size_hint_y=None, height=20, halign="left",
        )
        self._goal_lbl.bind(size=lambda inst, val:
                            setattr(inst, "text_size", val))
        info_box.add_widget(self._goal_lbl)

        self._streak_lbl = Label(
            text="", color=cfg.GOLD, font_size=cfg.FONT_SIZES["body"],
            bold=True, size_hint_y=None, height=24, halign="left",
        )
        self._streak_lbl.bind(size=lambda inst, val:
                              setattr(inst, "text_size", val))
        info_box.add_widget(self._streak_lbl)

        ring_box.add_widget(info_box)
        root.add_widget(ring_box)

        # === Active stopwatch card ===
        self._timer_card = _ActiveTimerCard(app=self.app, lang=self._lang,
                                            size_hint_y=None, height=110)
        self._timer_card.set_visibility(False)
        root.add_widget(self._timer_card)

        # === Quick-log templates ===
        root.add_widget(SectionHeader(
            text="قالب‌های سریع" if self._lang == "fa" else "Quick templates"
        ))
        self._templates_box = BoxLayout(orientation="horizontal",
                                        size_hint_y=None, height=44,
                                        spacing=cfg.SPACE["sm"])
        self._templates_scroll = ScrollView(size_hint_y=None, height=44,
                                            do_scroll_y=False,
                                            bar_width=0)
        self._templates_scroll.add_widget(self._templates_box)
        root.add_widget(self._templates_scroll)

        # === Recent ===
        root.add_widget(SectionHeader(
            text="فعالیت‌های اخیر" if self._lang == "fa" else "Recent activities"
        ))
        self._recent_scroll = ScrollView()
        self._recent_list = BoxLayout(orientation="vertical",
                                      spacing=cfg.SPACE["sm"],
                                      size_hint_y=None)
        self._recent_list.bind(minimum_height=self._recent_list.setter("height"))
        self._recent_scroll.add_widget(self._recent_list)
        root.add_widget(self._recent_list)

        self.add_widget(root)

        # === FAB ===
        self._fab = FabButton(size_val=56)
        self._fab.pos = (self.width - 72, 80)
        self._fab.bind(on_release=self._open_quick_log)
        self.add_widget(self._fab)
        self.bind(size=self._reposition_fab)

    def _reposition_fab(self, *_):
        self._fab.pos = (self.width - 72, 80)

    def _greeting_text(self) -> str:
        h = datetime.now().hour
        if self._lang == "fa":
            if h < 12: return "صبح بخیر"
            if h < 18: return "عصر بخیر"
            return "شب بخیر"
        if h < 12: return "Good morning"
        if h < 18: return "Good afternoon"
        return "Good evening"

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _open_quick_log(self, *_):
        self.app.open_quick_log()

    def _on_timer_tick(self, elapsed: int, running: bool):
        Clock.schedule_once(lambda dt: self._refresh())

    def _refresh(self, *_):
        today = du.today_iso()
        # Today total
        total = repos.ActivityRepository.total_seconds_on(today)
        # Goal
        goal = next((g for g in repos.GoalRepository.all()
                     if g.period == cfg.PERIOD_DAILY and not g.category_id), None)
        target_sec = (goal.target_minutes * 60) if goal else (120 * 60)
        progress = min(1.0, total / target_sec) if target_sec > 0 else 0.0

        self._ring.progress = progress
        self._ring.label_text = fmt_minutes_human(total, lang=self._lang)
        self._today_total.text = fmt_minutes_human(total, lang=self._lang)

        if goal:
            self._goal_lbl.text = (
                f"هدف: {fmt_minutes_human(goal.target_minutes * 60, lang=self._lang)}"
                if self._lang == "fa"
                else f"Goal: {fmt_minutes_human(goal.target_minutes * 60)}"
            )
        # Streak
        longest = repos.StreakRepository.all_longest(limit=1)
        if longest:
            s = longest[0]
            self._streak_lbl.text = (
                (f"🔥 زنجیره: {_fa(s.current)} روز" if self._lang == "fa"
                 else f"Streak: {s.current} days")
            )

        # Timer card
        if timer_service.is_running() or timer_service.elapsed_sec() > 0:
            self._timer_card.set_visibility(True)
            self._timer_card.refresh()
        else:
            self._timer_card.set_visibility(False)

        # Templates
        self._templates_box.clear_widgets()
        tpls = repos.TemplateRepository.all()
        if not tpls:
            self._templates_box.add_widget(Label(
                text="—" if self._lang == "fa" else "No templates yet",
                color=cfg.TEXT_FAINT, size_hint_x=None, width=120,
            ))
        else:
            for t in tpls:
                chip = Chip(label=t.title)
                chip.width = max(80, len(t.title) * 12 + 32)
                chip.size_hint_x = None
                chip.bind(on_release=lambda inst, tt=t: self._use_template(tt))
                self._templates_box.add_widget(chip)

        # Recent activities
        self._recent_list.clear_widgets()
        recent = repos.ActivityRepository.recent(limit=15)
        if not recent:
            self._recent_list.add_widget(EmptyState(
                text="هنوز فعالیتی ثبت نشده"
                     if self._lang == "fa"
                     else "No activities yet"
            ))
        else:
            cats = {c.id: c for c in repos.CategoryRepository.all()}
            for a in recent:
                self._recent_list.add_widget(
                    _ActivityRow(a, cats.get(a.category_id), self._lang)
                )

    def _use_template(self, t):
        # Start a stopwatch with this template
        timer_service.start(t.title, category_id=t.category_id,
                            template_id=t.id)
        self._refresh()

    def on_enter(self):
        self._refresh()


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
def _fa(n) -> str:
    return str(n).translate(_FA_DIGITS)


# === Active timer card ===

class _ActiveTimerCard(GoldCard):
    def __init__(self, app, lang: str, **kw):
        self.app = app
        self._lang = lang
        super().__init__(**kw)
        self.padding = [cfg.SPACE["md"], cfg.SPACE["sm"]]
        self._build()
        self._tick = Clock.schedule_interval(self._tick_cb, 0.5)

    def _build(self):
        self._title = Label(
            text="", color=cfg.TEXT, font_size=cfg.FONT_SIZES["body"],
            bold=True, size_hint_y=None, height=22, halign="left",
        )
        self._title.bind(size=lambda inst, val:
                         setattr(inst, "text_size", val))
        self.add_widget(self._title)

        self._time = Label(
            text="00:00", color=cfg.GOLD, font_size=cfg.FONT_SIZES["h2"],
            bold=True, size_hint_y=None, height=44, halign="left",
        )
        self._time.bind(size=lambda inst, val:
                        setattr(inst, "text_size", val))
        self.add_widget(self._time)

        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=32, spacing=cfg.SPACE["sm"])
        self._btn_pause = OutlinedButton(
            text="توقف" if self._lang == "fa" else "Pause",
            size_hint_x=0.5, height=32,
        )
        self._btn_pause.bind(on_release=self._on_pause)
        self._btn_stop = GoldButton(
            text="ذخیره و پایان" if self._lang == "fa" else "Stop & save",
            size_hint_x=0.5, height=32,
        )
        self._btn_stop.bind(on_release=self._on_stop)
        btns.add_widget(self._btn_pause)
        btns.add_widget(self._btn_stop)
        self.add_widget(btns)

    def refresh(self):
        self._title.text = timer_service.current_title() or (
            "در حال ثبت" if self._lang == "fa" else "Recording"
        )
        self._time.text = self._fmt(timer_service.elapsed_sec())
        self._btn_pause.text = (
            "ادامه" if self._lang == "fa" else "Resume"
        ) if not timer_service.is_running() else (
            "توقف" if self._lang == "fa" else "Pause"
        )

    def _tick_cb(self, *_):
        if timer_service.is_running() or timer_service.elapsed_sec() > 0:
            self.refresh()

    def _fmt(self, sec: int) -> str:
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _on_pause(self, *_):
        if timer_service.is_running():
            timer_service.pause()
        else:
            timer_service.resume()
        self.refresh()

    def _on_stop(self, *_):
        timer_service.stop_and_save()
        self.refresh()

    def set_visibility(self, visible: bool):
        self.height = 110 if visible else 0
        self.opacity = 1 if visible else 0
        self.disabled = not visible


# === Activity row ===

class _ActivityRow(GoldCard):
    def __init__(self, activity: Activity, category, lang: str, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", 72)
        kw.setdefault("padding", [cfg.SPACE["md"]] * 2)
        super().__init__(**kw)
        self._lang = lang
        self._activity = activity

        # Title row
        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=22)
        title = Label(
            text=activity.title or "(no title)",
            color=cfg.TEXT, font_size=cfg.FONT_SIZES["body"], bold=True,
            halign="left", valign="middle", size_hint_x=0.7,
        )
        title.bind(size=lambda inst, val:
                   setattr(inst, "text_size", val))
        top.add_widget(title)
        cat_color = category.color if category else "#D4AF37"
        cat_name = (category.name_fa if lang == "fa" and category.name_fa
                    else category.name_en) if category else ""
        cat_lbl = Label(
            text=cat_name, color=get_color_from_hex_safe(cat_color),
            font_size=cfg.FONT_SIZES["caption"],
            halign="right", size_hint_x=0.3,
        )
        cat_lbl.bind(size=lambda inst, val:
                     setattr(inst, "text_size", val))
        top.add_widget(cat_lbl)
        self.add_widget(top)

        # Sub row: duration + relative date
        sub = BoxLayout(orientation="horizontal", size_hint_y=None, height=18)
        dur = Label(
            text=fmt_minutes_human(activity.duration_sec, lang=lang),
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["small"],
            halign="left", size_hint_x=0.5,
        )
        dur.bind(size=lambda inst, val:
                 setattr(inst, "text_size", val))
        sub.add_widget(dur)
        when = Label(
            text=du.fmt_relative(activity.date_iso, lang=lang),
            color=cfg.TEXT_FAINT, font_size=cfg.FONT_SIZES["tiny"],
            halign="right", size_hint_x=0.5,
        )
        when.bind(size=lambda inst, val:
                  setattr(inst, "text_size", val))
        sub.add_widget(when)
        self.add_widget(sub)


def get_color_from_hex_safe(h: str):
    from kivy.utils import get_color_from_hex
    try:
        return get_color_from_hex(h)
    except Exception:
        return cfg.GOLD
