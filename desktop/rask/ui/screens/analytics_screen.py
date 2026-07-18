"""
rask.ui.screens.analytics_screen
================================

Advanced analytics screen — productivity trends, category breakdowns,
heatmaps, year-over-year comparison, goal progress, correlations,
anomaly detection, forecast, and report card.

Mirrors the *Advanced Analytics* view from the web app.  Uses
:class:`rask.features.analytics_dashboard.AnalyticsService` as the
source of truth.

Layout (top-to-bottom, RTL Persian):

    1. **Header** — ``"تحلیل‌های پیشرفته"`` with refresh + export
       buttons
    2. **Date range selector** — segmented control
       (7d / 30d / 90d / 1y)
    3. **Productivity over time** — 90-day line chart
    4. **Category trends** — multi-line chart (90 days, top categories)
    5. **Time distribution heatmap** — 7 days × 24 hours grid
    6. **Year-over-year comparison** — 12-month bar chart (this year
       vs last year)
    7. **Goal progress over time** — line chart per goal
    8. **Correlation analysis cards** — ``"وقتی ورزش می‌کنی، حالت بهتره"``
       with strength indicator
    9. **Anomaly detection list** — flagged days
    10. **Forecast tomorrow** — predicted minutes + confidence
    11. **Report card** — letter grades (A-F) for various metrics
    12. **Export analytics report** (PDF) button

Auto-refresh
------------
Subscribes to ``analytics.computed`` / ``activity.added`` /
``activity.updated`` / ``activity.deleted`` / ``goal.added`` /
``goal.updated`` / ``goal.deleted`` / ``mood.added`` / ``mood.updated`` /
``language.changed`` / ``data.cleared``.
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
from ...core import event_bus, time_utils, jalali
from ... import database as db
from ...features.analytics_dashboard import analytics_service
from ..widgets import theme as _theme
from ..widgets.buttons import (
    GoldButton, GhostButton, TextButton, IconButton, PillButton,
)
from ..widgets.cards import Card, StatCard
from ..widgets.dividers import Divider, Spacer, SectionTitle
from ..widgets.headers import Header
from ..widgets.toggles import SegmentedControl
from ..widgets.scrollable import SmoothScrollFrame
from ..widgets.empty_state import EmptyState
from ..widgets.charts import LineChart, BarChart, DonutChart, Heatmap

__all__ = ["AnalyticsScreen"]


# =============================================================================
# === Constants                                                              ===
# =============================================================================

_DATE_RANGES: Dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "1y": 365,
}

_GRADE_COLOR: Dict[str, str] = {
    "A": config.SUCCESS,
    "B": config.GOLD,
    "C": config.WARNING,
    "D": config.WARNING,
    "F": config.DANGER,
}

_HEATMAP_COLORS: List[str] = [
    config.SURFACE,         # 0
    config.GOLD_DIM,        # 1
    config.GOLD_SOFT,       # 2
    config.GOLD,            # 3
    config.GOLD_BRIGHT,     # 4
]


def _intensity_color(level: int) -> str:
    """Return a heatmap color for an intensity level (0..4)."""
    try:
        return _HEATMAP_COLORS[max(0, min(4, int(level)))]
    except Exception:
        return config.SURFACE


def _format_minutes(m: int, lang: str) -> str:
    if m <= 0:
        return ("۰ دقیقه" if lang == "fa" else "0 min")
    h = m // 60
    r = m % 60
    if lang == "fa":
        parts: List[str] = []
        if h > 0:
            parts.append(f"{i18n.to_fa_digits(str(h))} ساعت")
        if r > 0:
            parts.append(f"{i18n.to_fa_digits(str(r))} دقیقه")
        return " ".join(parts) if parts else "—"
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if r > 0:
        parts.append(f"{r}m")
    return " ".join(parts) if parts else "—"


# =============================================================================
# === AnalyticsScreen                                                        ===
# =============================================================================

class AnalyticsScreen(ctk.CTkFrame):
    """Advanced analytics screen.

    Parameters
    ----------
    parent
        Parent widget.
    app
        Main application object.  Uses these optional methods:
            * ``show_toast(message)``
            * ``show_export_dialog()``
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
        self._refresh_job: Optional[Any] = None
        self._refresh_pending: bool = False
        self._date_range: str = "30d"
        self._build()
        self._subscribe_events()
        self.after(80, self.refresh)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._header = Header(
            self, title=self._tr("تحلیل‌های پیشرفته",
                                   "Advanced Analytics"),
            lang=self._lang, height=56,
            action_icon="refresh",
            on_action=self._on_refresh,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._scroll = SmoothScrollFrame(
            self, lang=self._lang,
            fg_color=config.MATTE_BLACK, corner_radius=0,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)
        self._section_row = 0
        self._build_date_range()
        # Dynamic sections built in refresh()
        self._content_frame = ctk.CTkFrame(
            self._scroll, fg_color="transparent")
        self._content_frame.grid(row=self._next_row(), column=0,
                                   sticky="ew")
        self._content_frame.grid_columnconfigure(0, weight=1)

    def _build_date_range(self) -> None:
        """Date range selector."""
        section = ctk.CTkFrame(self._scroll, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            section, text=self._tr("بازه زمانی", "Date range"),
            font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                    weight="normal", lang=self._lang),
            text_color=config.TEXT_DIM,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        # 4 segment buttons
        chips_row = ctk.CTkFrame(section, fg_color="transparent")
        chips_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        for i in range(4):
            chips_row.grid_columnconfigure(i, weight=1, uniform="dr")
        ranges = list(_DATE_RANGES.keys())
        labels = {
            "7d": (self._tr("۷ روز", "7 days")),
            "30d": (self._tr("۳۰ روز", "30 days")),
            "90d": (self._tr("۹۰ روز", "90 days")),
            "1y": (self._tr("۱ سال", "1 year")),
        }
        self._range_buttons: Dict[str, ctk.CTkButton] = {}
        for i, key in enumerate(ranges):
            col = (3 - i) if rtl else i
            btn = ctk.CTkButton(
                chips_row, text=labels[key],
                command=lambda _k=key: self._on_range_change(_k),
                fg_color=(config.GOLD if key == self._date_range
                            else config.CHARCOAL),
                hover_color=config.GOLD_BRIGHT,
                text_color=(config.MATTE_BLACK if key == self._date_range
                              else config.TEXT),
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="bold", lang=self._lang),
                corner_radius=config.RADIUS_MD, height=36,
                border_width=2,
                border_color=(config.GOLD if key == self._date_range
                                else config.SURFACE_HI),
            )
            btn.grid(row=0, column=col, sticky="nsew",
                      padx=2, pady=2)
            self._range_buttons[key] = btn

    def _next_row(self) -> int:
        r = self._section_row
        self._section_row += 1
        return r

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = event_bus.bus
        events = [
            "analytics.computed",
            "activity.added", "activity.updated", "activity.deleted",
            "goal.added", "goal.updated", "goal.deleted",
            "mood.added", "mood.updated",
            "language.changed", "data.cleared",
        ]
        for ev in events:
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
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_job = self.after(250, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self._refresh_job = None
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render the entire analytics dashboard."""
        # Clear old content
        for child in self._content_frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._section_row = 1  # reset to start after date range
        # Build all sections
        self._build_productivity_chart()
        self._build_category_trends()
        self._build_time_distribution_heatmap()
        self._build_year_over_year()
        self._build_goal_progress()
        self._build_correlations()
        self._build_anomalies()
        self._build_forecast()
        self._build_report_card()
        self._build_export_button()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _make_chart_card(self, title: str) -> Card:
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content, text=title,
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        return card

    def _build_productivity_chart(self) -> None:
        """90-day productivity line chart."""
        card = self._make_chart_card(
            self._tr("بهره‌وری در ۹۰ روز گذشته",
                       "Productivity (last 90 days)"))
        try:
            data = analytics_service.productivity_over_time(days=90)
            values = [float(d.get("score", 0.0) or 0.0) for d in data]
            chart = LineChart(
                card.content, data=[{
                    "label": self._tr("امتیاز", "Score"),
                    "values": values,
                    "color": config.GOLD,
                }], width=460, height=160, lang=self._lang,
            )
            chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        except Exception:
            pass

    def _build_category_trends(self) -> None:
        """Multi-line category trends chart."""
        card = self._make_chart_card(
            self._tr("روند دسته‌ها", "Category trends"))
        try:
            trends = analytics_service.category_trends(days=90)
            # Take top 3 categories by total minutes
            cat_totals = []
            for cid, series in trends.items():
                total = sum(int(s.get("total_min", 0) or 0) for s in series)
                cat_totals.append((cid, total, series))
            cat_totals.sort(key=lambda x: x[1], reverse=True)
            top_3 = cat_totals[:3]
            # Fetch category names
            cats = {int(c["id"]): c for c in db.category_list()}
            colors = [config.GOLD, config.INFO, config.SUCCESS]
            series_data = []
            for i, (cid, _, series) in enumerate(top_3):
                cat = cats.get(cid, {})
                name = (cat.get("name_fa") if self._lang == "fa"
                         else cat.get("name_en")) or "—"
                values = [float(s.get("total_min", 0) or 0) for s in series]
                series_data.append({
                    "label": name,
                    "values": values,
                    "color": colors[i % len(colors)],
                })
            if series_data:
                chart = LineChart(
                    card.content, data=series_data,
                    width=460, height=180, lang=self._lang,
                )
                chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
            else:
                ctk.CTkLabel(
                    card.content,
                    text=self._tr("داده‌ای موجود نیست",
                                    "No data available"),
                    font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                            weight="normal",
                                            lang=self._lang),
                    text_color=config.TEXT_DIM,
                ).grid(row=1, column=0, pady=config.SPACE_SM)
        except Exception:
            pass

    def _build_time_distribution_heatmap(self) -> None:
        """7-day × 24-hour heatmap grid."""
        card = self._make_chart_card(
            self._tr("توزیع زمانی (۷ روز × ۲۴ ساعت)",
                       "Time distribution (7d × 24h)"))
        try:
            matrix = analytics_service.weekly_heatmap()
            # Build a manual grid: 7 rows (weekdays) × 24 cols (hours)
            grid = ctk.CTkFrame(card.content, fg_color="transparent")
            grid.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
            for i in range(24):
                grid.grid_columnconfigure(i, weight=1, uniform="hm")
            # Header row: empty + hour markers (every 4 hours)
            for h in [0, 4, 8, 12, 16, 20]:
                h_str = (i18n.to_fa_digits(str(h))
                          if self._lang == "fa" else str(h))
                ctk.CTkLabel(
                    grid, text=h_str,
                    font=_theme.theme.font(size=config.FONT_SIZE_CAPTION - 1,
                                            weight="normal", lang=self._lang),
                    text_color=config.TEXT_DIM,
                ).grid(row=0, column=h, padx=1, pady=(0, 2))
            # 7 weekday rows
            weekday_names_fa = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
            weekday_names_en = ["Sa", "Su", "Mo", "Tu", "We", "Th", "Fr"]
            names = (weekday_names_fa if self._lang == "fa"
                      else weekday_names_en)
            # Find max value for normalization
            max_val = 1
            for row in matrix:
                for v in row:
                    if v > max_val:
                        max_val = v
            for r_idx, row in enumerate(matrix):
                # Weekday label (in column 0)
                ctk.CTkLabel(
                    grid, text=names[r_idx],
                    font=_theme.theme.font(size=config.FONT_SIZE_CAPTION - 1,
                                            weight="bold", lang=self._lang),
                    text_color=config.TEXT_DIM,
                ).grid(row=r_idx + 1, column=0, padx=1, pady=1)
                for h_idx, val in enumerate(row):
                    # Normalize to 0..4 level
                    if val <= 0:
                        level = 0
                    else:
                        level = min(4, int((val / max_val) * 4) + 1)
                    cell = ctk.CTkFrame(
                        grid, width=16, height=16,
                        fg_color=_intensity_color(level),
                        corner_radius=2,
                    )
                    cell.grid(row=r_idx + 1, column=h_idx, padx=1, pady=1)
                    cell.grid_propagate(False)
        except Exception:
            pass

    def _build_year_over_year(self) -> None:
        """Year-over-year 12-month bar chart."""
        card = self._make_chart_card(
            self._tr("مقایسه سالانه", "Year-over-year"))
        try:
            yoy = analytics_service.year_over_year()
            by_month = yoy.get("by_month", []) or []
            bar_data = []
            for m in by_month:
                # Convert "YYYY-MM" to a short label
                label = m.get("month", "")[-2:]
                try:
                    label = (i18n.to_fa_digits(label)
                              if self._lang == "fa" else label)
                except Exception:
                    pass
                bar_data.append({
                    "label": label,
                    "value": int(m.get("this_year_min", 0) or 0),
                    "color": config.GOLD,
                })
            chart = BarChart(
                card.content, data=bar_data, width=460, height=160,
                lang=self._lang,
            )
            chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
            # Summary line
            this_total = int(yoy.get("this_year_total", 0) or 0)
            last_total = int(yoy.get("last_year_total", 0) or 0)
            growth = float(yoy.get("growth_pct", 0.0) or 0.0)
            rtl = i18n.is_rtl(self._lang)
            ctk.CTkLabel(
                card.content,
                text=(f"{self._tr('امسال', 'This year')}: "
                       f"{_format_minutes(this_total, self._lang)}  •  "
                       f"{self._tr('سال گذشته', 'Last year')}: "
                       f"{_format_minutes(last_total, self._lang)}  •  "
                       f"{self._tr('رشد', 'Growth')}: "
                       f"{i18n.to_fa_digits(str(int(growth))) if self._lang == 'fa' else str(int(growth))}٪"),
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
                anchor="e" if rtl else "w",
            ).grid(row=2, column=0, sticky="e" if rtl else "w",
                    pady=(4, 0))
        except Exception:
            pass

    def _build_goal_progress(self) -> None:
        """Goal progress over time — line chart per goal."""
        card = self._make_chart_card(
            self._tr("پیشرفت اهداف در زمان",
                       "Goal progress over time"))
        try:
            from ...services import goal_service
            goals = goal_service.list(only_active=True)
            if not goals:
                ctk.CTkLabel(
                    card.content,
                    text=self._tr("هدفی فعال نیست",
                                    "No active goals"),
                    font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                            weight="normal",
                                            lang=self._lang),
                    text_color=config.TEXT_DIM,
                ).grid(row=1, column=0, pady=config.SPACE_SM)
                return
            colors = [config.GOLD, config.INFO, config.SUCCESS,
                       config.WARNING, config.CAT_CREATIVE]
            series_data = []
            for i, g in enumerate(goals[:5]):  # cap at 5 goals
                gid = int(g.get("id") or 0)
                if gid <= 0:
                    continue
                series = analytics_service.goal_progress_over_time(
                    gid, days=30)
                name = g.get("title", "—")
                values = [float(s.get("ratio", 0.0) or 0.0) * 100
                           for s in series]
                series_data.append({
                    "label": name,
                    "values": values,
                    "color": colors[i % len(colors)],
                })
            if series_data:
                chart = LineChart(
                    card.content, data=series_data,
                    width=460, height=160, lang=self._lang,
                )
                chart.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        except Exception:
            pass

    def _build_correlations(self) -> None:
        """Mood-activity correlation cards."""
        card = self._make_chart_card(
            self._tr("همبستگی حال و فعالیت",
                       "Mood-Activity Correlations"))
        try:
            correlations = analytics_service.correlation_analysis()
        except Exception:
            correlations = []
        if not correlations:
            ctk.CTkLabel(
                card.content,
                text=self._tr("داده کافی نیست",
                                "Not enough data"),
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT_DIM,
            ).grid(row=1, column=0, sticky="ew", pady=config.SPACE_SM)
            return
        rtl = i18n.is_rtl(self._lang)
        # Show top 3 correlations
        for i, c in enumerate(correlations[:3]):
            row = ctk.CTkFrame(card.content, fg_color="transparent")
            row.grid(row=i + 1, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 4))
            row.grid_columnconfigure(1, weight=1)
            name = c.get("category_name", "—")
            color = c.get("category_color") or config.GOLD
            corr = float(c.get("correlation", 0.0) or 0.0)
            # Strength bar (|corr| × 100%)
            strength = abs(corr)
            if strength > 0.5:
                strength_label = self._tr("قوی", "strong")
                strength_color = config.SUCCESS
            elif strength > 0.3:
                strength_label = self._tr("متوسط", "moderate")
                strength_color = config.GOLD
            else:
                strength_label = self._tr("ضعیف", "weak")
                strength_color = config.TEXT_DIM
            # Arrow
            if corr > 0:
                arrow = "↑"
                arrow_color = config.SUCCESS
            elif corr < 0:
                arrow = "↓"
                arrow_color = config.DANGER
            else:
                arrow = "—"
                arrow_color = config.TEXT_DIM
            # Color dot
            dot = ctk.CTkFrame(row, width=10, height=10,
                                 fg_color=color,
                                 corner_radius=config.RADIUS_PILL)
            dot.grid(row=0, column=1 if rtl else 0, padx=4, pady=8,
                      sticky="n")
            # Arrow
            ctk.CTkLabel(
                row, text=arrow,
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang=self._lang),
                text_color=arrow_color,
            ).grid(row=0, column=0 if rtl else 1, padx=4)
            # Description
            desc = c.get("description_fa" if self._lang == "fa"
                          else "description_fa", "")
            if not desc:
                if corr > 0:
                    desc = self._tr(
                        f"وقتی {name} می‌کنی، حالت بهتره",
                        f"Doing {name} improves your mood")
                elif corr < 0:
                    desc = self._tr(
                        f"وقتی {name} می‌کنی، حالت بدتره",
                        f"Doing {name} lowers your mood")
                else:
                    desc = self._tr(
                        f"{name} تاثیر قابل توجهی ندارد",
                        f"{name} has no significant effect")
            ctk.CTkLabel(
                row, text=desc,
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=320, justify="right" if rtl else "left",
            ).grid(row=0, column=2 if rtl else 1, sticky="e" if rtl
                    else "w", padx=4)
            # Strength label
            ctk.CTkLabel(
                row, text=strength_label,
                font=_theme.theme.font(size=config.FONT_SIZE_CAPTION,
                                        weight="bold", lang=self._lang),
                text_color=strength_color,
            ).grid(row=0, column=3 if rtl else 2, padx=4)

    def _build_anomalies(self) -> None:
        """Anomaly detection list."""
        try:
            anomalies = analytics_service.anomaly_detection()
        except Exception:
            anomalies = []
        if not anomalies:
            return
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content,
            text=self._tr("ناهنجاری‌های شناسایی‌شده",
                            "Detected anomalies"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                    weight="bold", lang=self._lang),
            text_color=config.WARNING,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        for i, a in enumerate(anomalies[:5]):
            row = ctk.CTkFrame(card.content, fg_color="transparent")
            row.grid(row=i + 1, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 0))
            row.grid_columnconfigure(1, weight=1)
            # Warning icon
            ctk.CTkLabel(
                row, text="⚠",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                        weight="bold", lang="en"),
                text_color=config.WARNING,
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            # Date + description
            date_iso = a.get("date_iso", "")
            try:
                date_str = jalali.format_jalali(
                    date_iso, fmt="short", lang=self._lang)
            except Exception:
                date_str = date_iso
            kind = a.get("kind", "")
            if "high" in str(kind):
                kind_label = self._tr("فعالیت بسیار زیاد",
                                        "Very high activity")
            elif "low" in str(kind):
                kind_label = self._tr("فعالیت بسیار کم",
                                        "Very low activity")
            else:
                kind_label = self._tr("الگوی غیرعادی",
                                        "Unusual pattern")
            ctk.CTkLabel(
                row, text=f"{date_str}  •  {kind_label}",
                font=_theme.theme.font(size=config.FONT_SIZE_BODY,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w")

    def _build_forecast(self) -> None:
        """Forecast tomorrow card."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(1, weight=1)
        rtl = i18n.is_rtl(self._lang)
        try:
            forecast = analytics_service.forecast_tomorrow()
        except Exception:
            forecast = {}
        # Predicted minutes
        predicted = int(forecast.get("predicted_min", 0) or 0)
        pred_str = _format_minutes(predicted, self._lang)
        ctk.CTkLabel(
            card.content, text=pred_str,
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
        ).grid(row=0, column=0 if rtl else 1, padx=8)
        # Title + confidence
        info = ctk.CTkFrame(card.content, fg_color="transparent")
        info.grid(row=0, column=1 if rtl else 0, sticky="ew", padx=8)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            info, text=self._tr("پیش‌بینی فردا", "Tomorrow's forecast"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.TEXT,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w")
        confidence = float(forecast.get("confidence", 0.0) or 0.0)
        conf_pct = int(confidence * 100)
        conf_str = (i18n.to_fa_digits(str(conf_pct)) + "٪"
                     if self._lang == "fa" else f"{conf_pct}%")
        trend = forecast.get("trend", "flat")
        if trend == "up":
            trend_label = self._tr("رو به افزایش ↑", "trending up ↑")
            trend_color = config.SUCCESS
        elif trend == "down":
            trend_label = self._tr("رو به کاهش ↓", "trending down ↓")
            trend_color = config.DANGER
        else:
            trend_label = self._tr("ثابت —", "flat —")
            trend_color = config.TEXT_DIM
        ctk.CTkLabel(
            info, text=f"{self._tr('اطمینان', 'Confidence')}: {conf_str}  •  {trend_label}",
            font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                    weight="normal", lang=self._lang),
            text_color=trend_color,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(2, 0))

    def _build_report_card(self) -> None:
        """Report card with letter grades."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG, pady=(0, config.SPACE_SM))
        section.grid_columnconfigure(0, weight=1)
        card = Card(section, lang=self._lang,
                     padding=config.SPACE_LG)
        card.grid(row=0, column=0, sticky="ew")
        card.content.grid_columnconfigure(0, weight=1)
        rtl = i18n.is_rtl(self._lang)
        ctk.CTkLabel(
            card.content,
            text=self._tr("کارنامه عملکرد", "Report card"),
            font=_theme.theme.font(size=config.FONT_SIZE_BODY_LG,
                                    weight="bold", lang=self._lang),
            text_color=config.GOLD,
            anchor="e" if rtl else "w",
        ).grid(row=0, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        try:
            report = analytics_service.report_card()
        except Exception:
            report = {}
        # Overall grade
        overall = report.get("overall_grade", "—")
        overall_color = _GRADE_COLOR.get(overall, config.GOLD)
        ctk.CTkLabel(
            card.content,
            text=f"{self._tr('نمره کل', 'Overall grade')}: {overall}",
            font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                    weight="bold", lang=self._lang),
            text_color=overall_color,
            anchor="e" if rtl else "w",
        ).grid(row=1, column=0, sticky="e" if rtl else "w",
                pady=(0, config.SPACE_SM))
        # Metrics list
        metrics = report.get("metrics", []) or []
        for i, m in enumerate(metrics[:6]):
            row = ctk.CTkFrame(card.content, fg_color="transparent")
            row.grid(row=i + 2, column=0, sticky="ew",
                      pady=(0 if i == 0 else 4, 0))
            row.grid_columnconfigure(1, weight=1)
            # Grade letter
            grade = m.get("grade", "—")
            grade_color = _GRADE_COLOR.get(grade, config.GOLD)
            ctk.CTkLabel(
                row, text=grade,
                font=_theme.theme.font(size=config.FONT_SIZE_HEADING_SM,
                                        weight="bold", lang="en"),
                text_color=grade_color,
            ).grid(row=0, column=1 if rtl else 0, padx=4)
            # Label + description
            label = m.get("label_fa" if self._lang == "fa"
                           else "label_fa", "")
            if not label:
                label = m.get("name", "—")
            desc = m.get("description_fa" if self._lang == "fa"
                          else "description_fa", "")
            ctk.CTkLabel(
                row, text=f"{label}  •  {desc}",
                font=_theme.theme.font(size=config.FONT_SIZE_SMALL,
                                        weight="normal", lang=self._lang),
                text_color=config.TEXT,
                anchor="e" if rtl else "w",
                wraplength=380, justify="right" if rtl else "left",
            ).grid(row=0, column=0 if rtl else 1, sticky="e" if rtl
                    else "w")

    def _build_export_button(self) -> None:
        """Export analytics report as PDF button."""
        section = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        section.grid(row=self._next_row(), column=0, sticky="ew",
                      padx=config.SPACE_LG,
                      pady=(config.SPACE_MD, config.SPACE_XL))
        section.grid_columnconfigure(0, weight=1)
        GoldButton(
            section,
            text=self._tr("خروجی گزارش تحلیلی (PDF)",
                            "Export analytics report (PDF)"),
            command=self._on_export, lang=self._lang, height=44,
        ).pack(fill="x", padx=config.SPACE_LG)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_range_change(self, key: str) -> None:
        self._date_range = key
        # Update button highlights
        for k, btn in self._range_buttons.items():
            try:
                btn.configure(
                    fg_color=(config.GOLD if k == key
                                else config.CHARCOAL),
                    text_color=(config.MATTE_BLACK if k == key
                                  else config.TEXT),
                    border_color=(config.GOLD if k == key
                                    else config.SURFACE_HI),
                )
            except Exception:
                pass
        self.refresh()

    def _on_refresh(self) -> None:
        self._show_toast(self._tr("در حال به‌روزرسانی...",
                                    "Refreshing..."))
        self._schedule_refresh()

    def _on_export(self) -> None:
        if self._app and hasattr(self._app, "show_export_dialog"):
            try:
                self._app.show_export_dialog()
                return
            except Exception:
                pass
        self._show_toast(self._tr("خروجی PDF به‌زودی",
                                    "PDF export coming soon"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _tr(self, fa: str, en: str) -> str:
        try:
            v = i18n.t(fa, self._lang)
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
            event_bus.bus.publish("ui.toast", {"message": message})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def destroy(self) -> None:  # type: ignore[override]
        self._unsubscribe_events()
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        super().destroy()


# =============================================================================
# === Self-test                                                              ===
# =============================================================================

def _self_test() -> int:
    print("AnalyticsScreen module: date range selector + productivity "
          "chart + category trends + heatmap + year-over-year + goal "
          "progress + correlations + anomalies + forecast + report "
          "card + export button.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
