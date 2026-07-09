"""
stats.py — Statistics & insights screen.

Includes:
  - Date-range presets (today / 7d / 30d / month / year / custom)
  - Total time card
  - Bar chart: last 7 days
  - Donut chart: category share
  - Heatmap: full-year intensity
  - Trends: best day, peak hour, weekly avg
  - Year in review (compact)
  - Export PDF / CSV buttons
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from rask import config as cfg
from rask.data import repositories as repos
from rask.data.models import fmt_minutes_human
from rask.ui.components import (
    GoldCard, GoldButton, OutlinedButton, SectionHeader, EmptyState, Chip,
)
from rask.widgets.charts import BarChart, DonutChart, HeatmapView
from rask.utils import date_utils as du


PRESETS = [
    ("today", "امروز", "Today"),
    ("7d", "۷ روز", "7 days"),
    ("30d", "۳۰ روز", "30 days"),
    ("month", "این ماه", "This month"),
    ("year", "این سال", "This year"),
]


class StatsScreen(FloatLayout):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self._lang = app.lang
        self._preset = "7d"
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
            text="آمار و بینش" if self._lang == "fa" else "Statistics",
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h3"], bold=True,
            size_hint_y=None, height=44,
        ))

        # Preset chips
        presets = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=36, spacing=cfg.SPACE["sm"])
        for key, fa, en in PRESETS:
            chip = Chip(label=fa if self._lang == "fa" else en)
            chip.size_hint_x = None
            chip.width = 80
            chip.selected = (key == self._preset)
            chip.bind(on_release=lambda inst, k=key: self._set_preset(k))
            presets.add_widget(chip)
        root.add_widget(presets)

        self._scroll = ScrollView()
        self._list = BoxLayout(orientation="vertical", spacing=cfg.SPACE["md"],
                               size_hint_y=None)
        self._list.bind(minimum_height=self._list.setter("height"))
        self._scroll.add_widget(self._list)
        root.add_widget(self._scroll)

        # Export buttons
        exp = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=44, spacing=cfg.SPACE["sm"])
        pdf = OutlinedButton(
            text="خروجی PDF" if self._lang == "fa" else "Export PDF",
            size_hint_x=0.5,
        )
        pdf.bind(on_release=self._on_export_pdf)
        csv = OutlinedButton(
            text="خروجی CSV" if self._lang == "fa" else "Export CSV",
            size_hint_x=0.5,
        )
        csv.bind(on_release=self._on_export_csv)
        exp.add_widget(pdf)
        exp.add_widget(csv)
        root.add_widget(exp)

        self.add_widget(root)

    def _redraw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*cfg.MATTE_BLACK)
            Rectangle(pos=self.pos, size=self.size)

    def _set_preset(self, key: str):
        self._preset = key
        self.refresh()

    def _range(self) -> tuple[date, date]:
        today = date.today()
        if self._preset == "today":
            return today, today
        if self._preset == "7d":
            return today - timedelta(days=6), today
        if self._preset == "30d":
            return today - timedelta(days=29), today
        if self._preset == "month":
            return du.start_of_month(today), du.end_of_month(today)
        if self._preset == "year":
            return du.start_of_year(today), du.end_of_year(today)
        return today - timedelta(days=6), today

    def refresh(self, *_):
        self._list.clear_widgets()
        start, end = self._range()
        s_iso, e_iso = start.isoformat(), end.isoformat()

        acts = repos.ActivityRepository.by_date_range(s_iso, e_iso)
        total = sum(a.duration_sec for a in acts)

        # === Total card ===
        card = GoldCard(size_hint_y=None, height=110)
        card.add_widget(Label(
            text="مجموع زمان" if self._lang == "fa" else "Total time",
            color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["caption"],
            halign="left", size_hint_y=None, height=22,
        ))
        card.add_widget(Label(
            text=fmt_minutes_human(total, lang=self._lang),
            color=cfg.GOLD, font_size=cfg.FONT_SIZES["h2"], bold=True,
            halign="left", size_hint_y=None, height=44,
        ))
        card.add_widget(Label(
            text=f"{du.fmt_short_date(start, self._lang)} → "
                 f"{du.fmt_short_date(end, self._lang)}",
            color=cfg.TEXT_FAINT, font_size=cfg.FONT_SIZES["tiny"],
            halign="left", size_hint_y=None, height=18,
        ))
        self._list.add_widget(card)

        if not acts:
            self._list.add_widget(EmptyState(
                text="داده‌ای در این بازه نیست"
                     if self._lang == "fa"
                     else "No data in this range"
            ))
            return

        # === Bar chart: per-day for the range (max 30 bars) ===
        if (end - start).days <= 30:
            days = list(du.daterange(start, end))
            per_day = repos.ActivityRepository.seconds_per_day(s_iso, e_iso)
            bar_data = []
            for d in days:
                label = (str(d.day) if self._lang == "en"
                         else _fa(d.day))
                bar_data.append((label, per_day.get(d.isoformat(), 0),
                                 "#D4AF37"))
            bar_card = GoldCard(size_hint_y=None, height=200)
            bar_card.add_widget(SectionHeader(
                text="روند روزانه" if self._lang == "fa" else "Daily trend"
            ))
            bar = BarChart(size_hint_y=None, height=160)
            bar.data = bar_data
            bar_card.add_widget(bar)
            self._list.add_widget(bar_card)

        # === Donut: category share ===
        cat_card = GoldCard(size_hint_y=None, height=240)
        cat_card.add_widget(SectionHeader(
            text="سهم دسته‌ها" if self._lang == "fa" else "Category share"
        ))
        cats = {c.id: c for c in repos.CategoryRepository.all()}
        per_cat = repos.ActivityRepository.seconds_per_category(s_iso, e_iso)
        donut_data = []
        for cid, sec in per_cat[:6]:  # top 6
            c = cats.get(cid)
            name = (c.name_fa if self._lang == "fa" and c
                    else c.name_en) if c else "—"
            color = c.color if c else "#9A9A9F"
            donut_data.append((name, sec, color))
        donut = DonutChart(size_hint_y=None, height=160)
        donut.data = donut_data
        cat_card.add_widget(donut)
        # Legend
        legend = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=40, spacing=4, padding=[4, 0])
        for name, sec, color in donut_data[:4]:
            lbl = Label(
                text=f"{name}: {fmt_minutes_human(sec, lang=self._lang)}",
                color=cfg.TEXT_DIM, font_size=cfg.FONT_SIZES["tiny"],
                halign="center", size_hint_x=0.25,
            )
            lbl.bind(size=lambda inst, val:
                     setattr(inst, "text_size", val))
            legend.add_widget(lbl)
        cat_card.add_widget(legend)
        self._list.add_widget(cat_card)

        # === Heatmap (year) ===
        heat_card = GoldCard(size_hint_y=None, height=180)
        heat_card.add_widget(SectionHeader(
            text="نقشه فعالیت سال" if self._lang == "fa" else "Year heatmap"
        ))
        # Build per-day dict for the whole year
        ystart = du.start_of_year(date.today())
        yend = du.end_of_year(date.today())
        heat_data = repos.ActivityRepository.seconds_per_day(
            ystart.isoformat(), yend.isoformat()
        )
        heat = HeatmapView(size_hint_y=None, height=110,
                           data=heat_data, year=date.today().year)
        heat_card.add_widget(heat)
        self._list.add_widget(heat_card)

        # === Trends ===
        trend_card = GoldCard(size_hint_y=None, height=160)
        trend_card.add_widget(SectionHeader(
            text="روند و نقاط اوج" if self._lang == "fa" else "Trends & peaks"
        ))
        # Best day
        best_day, best_sec = None, 0
        for d_iso, s in repos.ActivityRepository.seconds_per_day(s_iso, e_iso).items():
            if s > best_sec:
                best_sec = s
                best_day = d_iso
        # Peak hour (today only when range=today; else last day in range)
        peak_hour = -1
        peak_sec = 0
        if (end - start).days <= 1:
            for h, s in enumerate(repos.ActivityRepository.seconds_per_hour(e_iso)):
                if s > peak_sec:
                    peak_sec = s
                    peak_hour = h
        # Weekly avg
        n_days = max(1, (end - start).days + 1)
        avg_per_day = total / n_days

        trends = []
        if best_day:
            trends.append((
                "بهترین روز" if self._lang == "fa" else "Best day",
                f"{du.fmt_short_date(du.iso_to_date(best_day), self._lang)} — "
                f"{fmt_minutes_human(best_sec, lang=self._lang)}",
            ))
        if peak_hour >= 0:
            trends.append((
                "ساعت اوج" if self._lang == "fa" else "Peak hour",
                f"{_fa(peak_hour):>02}:00 — "
                f"{fmt_minutes_human(peak_sec, lang=self._lang)}",
            ))
        trends.append((
            "میانگین روزانه" if self._lang == "fa" else "Daily average",
            fmt_minutes_human(int(avg_per_day), lang=self._lang),
        ))
        for k, v in trends:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=22)
            k_lbl = Label(text=k, color=cfg.TEXT_DIM,
                          font_size=cfg.FONT_SIZES["small"],
                          halign="left", size_hint_x=0.5)
            k_lbl.bind(size=lambda inst, val:
                       setattr(inst, "text_size", val))
            v_lbl = Label(text=v, color=cfg.GOLD,
                          font_size=cfg.FONT_SIZES["small"], bold=True,
                          halign="right", size_hint_x=0.5)
            v_lbl.bind(size=lambda inst, val:
                       setattr(inst, "text_size", val))
            row.add_widget(k_lbl)
            row.add_widget(v_lbl)
            trend_card.add_widget(row)
        self._list.add_widget(trend_card)

    def _on_export_pdf(self, *_):
        from rask.utils.pdf_export import export_pdf
        s, e = self._range()
        out_dir = self.app.user_data_dir
        out = f"{out_dir}/rask_report_{s.isoformat()}_to_{e.isoformat()}.pdf"
        try:
            export_pdf(out, s.isoformat(), e.isoformat(), lang=self._lang)
            self.app.toast(
                "گزارش PDF ذخیره شد" if self._lang == "fa"
                else f"PDF saved: {out}"
            )
        except Exception as ex:
            self.app.toast(f"PDF error: {ex}")

    def _on_export_csv(self, *_):
        from rask.utils.csv_export import export_csv
        s, e = self._range()
        out_dir = self.app.user_data_dir
        out = f"{out_dir}/rask_export_{s.isoformat()}_to_{e.isoformat()}.csv"
        try:
            n = export_csv(out, s.isoformat(), e.isoformat())
            self.app.toast(
                f"{_fa(n)} ردیف ذخیره شد" if self._lang == "fa"
                else f"CSV saved: {n} rows"
            )
        except Exception as ex:
            self.app.toast(f"CSV error: {ex}")


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
def _fa(n) -> str:
    return str(n).translate(_FA_DIGITS)
