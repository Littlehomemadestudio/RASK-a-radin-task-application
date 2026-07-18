"""
rask.utils.export_templates
============================

Pre-built PDF export templates for Rask.

Each template is a function that takes data + a PdfExporter, populates
the exporter with the appropriate sections, and returns it ready to
save.  Templates are tuned for Persian RTL output and use the
gold-on-dark theme consistently.

Available templates:
  • daily_log       — single-day detailed activity log
  • weekly_summary  — 7-day overview with charts
  • monthly_report  — full month analytics
  • yearly_review   — 12-month retrospective with heatmap

Usage:
    from rask.utils.export_templates import monthly_report
    from rask.export.pdf_export import PdfExporter

    pdf = PdfExporter("/tmp/june-report.pdf", lang="fa")
    monthly_report.populate(pdf, year=1405, month=4)
    pdf.save()
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from .. import config
from ..i18n import t, to_fa_digits
from ..core import jalali, time_utils

if TYPE_CHECKING:
    from ..export.pdf_export import PdfExporter


# =============================================================================
# === Helper functions                                                         ===
# =============================================================================

def _p(value, lang: str = "fa") -> str:
    """Localize a number/date to Persian if lang == 'fa'."""
    if lang == "fa":
        return to_fa_digits(value)
    return str(value)


def _format_duration_long(min: int, lang: str = "fa") -> str:
    """Format minutes as 'N ساعت و M دقیقه' or 'N hours M minutes'."""
    if min <= 0:
        return t("noData", lang)
    hours = min // 60
    mins = min % 60
    parts = []
    if hours > 0:
        parts.append(f"{_p(hours, lang)} {t('hours', lang)}")
    if mins > 0:
        parts.append(f"{_p(mins, lang)} {t('minutes', lang)}")
    if not parts:
        return t("noData", lang)
    sep = " و " if lang == "fa" else " and "
    return sep.join(parts)


def _format_jalali_date_long(iso: str, lang: str = "fa") -> str:
    """Format an ISO date as a long Jalali date string."""
    try:
        jy, jm, jd = jalali.iso_to_jalali(iso)
        month_name = jalali.jalali_month_name(jm, lang)
        if lang == "fa":
            return f"{to_fa_digits(jd)} {month_name} {to_fa_digits(jy)}"
        return f"{jd} {month_name} {jy}"
    except Exception:
        return iso


# =============================================================================
# === Daily log template                                                       ===
# =============================================================================

class DailyLogTemplate:
    """Detailed activity log for a single day.

    Includes:
      • Date header (Jalali + Gregorian)
      • Summary stats (total time, activity count, by-category breakdown)
      • Goal progress for the day
      • Full timeline of activities (start time, end time, title, category, duration, notes)
      • Mood/energy if a journal entry exists
    """

    name = "daily_log"
    name_fa = "گزارش روزانه"
    name_en = "Daily Log"

    def __init__(self, lang: str = "fa"):
        self.lang = lang

    def populate(self, pdf: "PdfExporter", date_iso: Optional[str] = None) -> None:
        from .. import database
        from ..services import stats_service, goal_service

        date_iso = date_iso or time_utils.today_iso()
        activities = database.activity_list(date_from=date_iso, date_to=date_iso,
                                            limit=10000)
        summary = stats_service.summary(date_iso, date_iso)

        # Header
        pdf.set_title(f"{t('todaySummary', self.lang)} — {_format_jalali_date_long(date_iso, self.lang)}")
        pdf.set_subtitle(date_iso)
        pdf.set_author(config.APP_NAME)
        pdf.add_heading(t("todaySummary", self.lang), level=1)
        pdf.add_paragraph(_format_jalali_date_long(date_iso, self.lang))

        # Summary block
        pdf.add_heading(t("statistics", self.lang), level=2)
        pdf.add_summary_table({
            t("totalTime", self.lang): _format_duration_long(summary.get("total_min", 0), self.lang),
            t("totalActivities", self.lang): _p(summary.get("total_activities", 0), self.lang),
            t("avgPerActivity", self.lang): _format_duration_long(
                summary.get("avg_per_activity", 0), self.lang),
        })

        # By category
        by_cat = stats_service.by_category(date_iso, date_iso)
        if by_cat:
            cats = database.category_list(include_archived=True)
            cat_map = {c["id"]: c for c in cats}
            pdf.add_heading(t("byCategory", self.lang), level=2)
            rows = []
            for item in by_cat[:10]:
                cat = cat_map.get(item["category_id"], {})
                name = cat.get(f"name_{self.lang}") or cat.get("name_en") or "—"
                rows.append({
                    t("category", self.lang): name,
                    t("totalActivities", self.lang): _p(item["count"], self.lang),
                    t("totalTime", self.lang): _format_duration_long(item["total_min"], self.lang),
                })
            pdf.add_activities_table(rows)

        # Activity timeline
        if activities:
            pdf.add_heading(t("recentActivities", self.lang), level=2)
            rows = []
            for a in activities:
                start = (a.get("start_ts") or "")[11:16] or "—"
                end = (a.get("end_ts") or "")[11:16] or "—"
                cat = cat_map.get(a.get("category_id"), {}) if by_cat else {}
                cat_name = cat.get(f"name_{self.lang}") or cat.get("name_en") or "—"
                rows.append({
                    t("startTime", self.lang): _p(start, self.lang),
                    t("endTime", self.lang): _p(end, self.lang),
                    t("activityTitle", self.lang): a.get("title") or "—",
                    t("category", self.lang): cat_name,
                    t("duration", self.lang): _format_duration_long(a.get("duration_min", 0), self.lang),
                })
            pdf.add_activities_table(rows)

        # Goal progress
        goals = database.goal_list(only_active=True)
        if goals:
            pdf.add_heading(t("dailyGoalProgress", self.lang), level=2)
            for g in goals:
                if g["period"] != "daily":
                    continue
                progress = goal_service.progress_for(g["id"], date_iso)
                title = g.get("title") or t("allCategories", self.lang)
                pct = int(progress.get("percent", 0))
                pdf.add_paragraph(
                    f"• {title}: {_format_duration_long(progress.get('current_min', 0), self.lang)} "
                    f"/ {_format_duration_long(progress.get('target_min', 0), self.lang)} "
                    f"({_p(pct, self.lang)}٪)"
                )

        # Footer
        pdf.add_page_break()
        pdf.add_paragraph(
            f"\n{config.APP_NAME} {config.APP_VERSION} • "
            f"{_format_jalali_date_long(time_utils.today_iso(), self.lang)}"
        )


# =============================================================================
# === Weekly summary template                                                  ===
# =============================================================================

class WeeklySummaryTemplate:
    """7-day overview with mini-charts."""

    name = "weekly_summary"
    name_fa = "خلاصه هفتگی"
    name_en = "Weekly Summary"

    def __init__(self, lang: str = "fa"):
        self.lang = lang

    def populate(self, pdf: "PdfExporter", week_start_iso: Optional[str] = None) -> None:
        from .. import database
        from ..services import stats_service, goal_service
        from ..core.time_utils import add_days, start_of_week

        week_start_iso = week_start_iso or start_of_week(time_utils.today_iso(), first_day=6)
        week_end_iso = add_days(week_start_iso, 6)

        pdf.set_title(f"{t('weeklyOverview', self.lang)} — "
                      f"{_format_jalali_date_long(week_start_iso, self.lang)} "
                      f"− {_format_jalali_date_long(week_end_iso, self.lang)}")
        pdf.add_heading(t("weeklyOverview", self.lang), level=1)
        pdf.add_paragraph(
            f"{_format_jalali_date_long(week_start_iso, self.lang)} "
            f"{t('to', self.lang)} "
            f"{_format_jalali_date_long(week_end_iso, self.lang)}"
        )

        # Summary stats
        summary = stats_service.summary(week_start_iso, week_end_iso)
        pdf.add_heading(t("statistics", self.lang), level=2)
        pdf.add_summary_table({
            t("totalTime", self.lang): _format_duration_long(summary.get("total_min", 0), self.lang),
            t("totalActivities", self.lang): _p(summary.get("total_activities", 0), self.lang),
            t("avgPerDay", self.lang): _format_duration_long(
                summary.get("avg_per_day", 0), self.lang),
            t("bestDay", self.lang): _format_jalali_date_long(
                summary.get("best_day_iso", "") or week_start_iso, self.lang)
                if summary.get("best_day_iso") else "—",
        })

        # Daily breakdown bar chart
        by_day = stats_service.by_day(week_start_iso, week_end_iso)
        if by_day:
            pdf.add_heading(t("byDayOfWeek", self.lang), level=2)
            data = [{"label": _format_jalali_date_long(d["date_iso"], self.lang),
                     "value": d["total_min"],
                     "color": config.GOLD}
                    for d in by_day]
            pdf.add_bar_chart(data, t("totalTime", self.lang))

        # By category
        by_cat = stats_service.by_category(week_start_iso, week_end_iso)
        if by_cat:
            cats = database.category_list(include_archived=True)
            cat_map = {c["id"]: c for c in cats}
            pdf.add_heading(t("byCategory", self.lang), level=2)
            data = []
            for item in by_cat[:7]:
                cat = cat_map.get(item["category_id"], {})
                name = cat.get(f"name_{self.lang}") or cat.get("name_en") or "—"
                color = cat.get("color") or config.GOLD
                data.append({"label": name, "value": item["total_min"], "color": color})
            pdf.add_donut_chart(data, t("byCategory", self.lang))

        # Goals progress
        goals = database.goal_list(only_active=True)
        if goals:
            pdf.add_heading(t("goalProgress", self.lang), level=2)
            for g in goals:
                if g["period"] != "weekly":
                    continue
                progress = goal_service.progress_for(g["id"], week_start_iso)
                title = g.get("title") or t("allCategories", self.lang)
                pct = int(progress.get("percent", 0))
                pdf.add_paragraph(
                    f"• {title}: {_p(pct, self.lang)}٪ "
                    f"({_format_duration_long(progress.get('current_min', 0), self.lang)} "
                    f"/ {_format_duration_long(progress.get('target_min', 0), self.lang)})"
                )


# =============================================================================
# === Monthly report template                                                  ===
# =============================================================================

class MonthlyReportTemplate:
    """Full month analytics with charts and insights."""

    name = "monthly_report"
    name_fa = "گزارش ماهانه"
    name_en = "Monthly Report"

    def __init__(self, lang: str = "fa"):
        self.lang = lang

    def populate(self, pdf: "PdfExporter",
                 year: Optional[int] = None,
                 month: Optional[int] = None) -> None:
        from .. import database
        from ..services import stats_service, goal_service
        from ..core.time_utils import today_iso

        today = today_iso()
        if year is None or month is None:
            jy, jm, _ = jalali.iso_to_jalali(today)
            year = year or jy
            month = month or jm
        # Build a 28-to-31-day window based on Jalali month length
        # Convert Jalali year-month-1 to Gregorian ISO
        start_jalali = f"{year:04d}-{month:02d}-01"
        try:
            start_iso = jalali.jalali_to_iso(year, month, 1)
        except Exception:
            start_iso = today
        # Compute end of month
        mlen = jalali.jalali_month_length(year, month)
        try:
            end_iso = jalali.jalali_to_iso(year, month, mlen)
        except Exception:
            end_iso = today

        month_name = jalali.jalali_month_name(month, self.lang)
        pdf.set_title(f"{t('monthOverview', self.lang)} — {month_name} {_p(year, self.lang)}")
        pdf.add_heading(f"{t('monthOverview', self.lang)} — {month_name} {_p(year, self.lang)}", level=1)
        pdf.add_paragraph(
            f"{_format_jalali_date_long(start_iso, self.lang)} "
            f"{t('to', self.lang)} "
            f"{_format_jalali_date_long(end_iso, self.lang)}"
        )

        # Summary
        summary = stats_service.summary(start_iso, end_iso)
        pdf.add_heading(t("statistics", self.lang), level=2)
        pdf.add_summary_table({
            t("totalTime", self.lang): _format_duration_long(summary.get("total_min", 0), self.lang),
            t("totalActivities", self.lang): _p(summary.get("total_activities", 0), self.lang),
            t("avgPerDay", self.lang): _format_duration_long(
                summary.get("avg_per_day", 0), self.lang),
            t("avgPerActivity", self.lang): _format_duration_long(
                summary.get("avg_per_activity", 0), self.lang),
            t("bestDay", self.lang): _format_jalali_date_long(
                summary.get("best_day_iso", "") or start_iso, self.lang)
                if summary.get("best_day_iso") else "—",
            t("longestStreak", self.lang): _p(summary.get("longest_streak", 0), self.lang)
                + " " + t("days", self.lang),
        })

        # Daily breakdown bar chart
        by_day = stats_service.by_day(start_iso, end_iso)
        if by_day:
            pdf.add_heading(t("byDayOfWeek", self.lang), level=2)
            data = [{"label": _format_jalali_date_long(d["date_iso"], self.lang),
                     "value": d["total_min"], "color": config.GOLD}
                    for d in by_day]
            pdf.add_bar_chart(data, t("totalTime", self.lang))

        # By category donut
        by_cat = stats_service.by_category(start_iso, end_iso)
        if by_cat:
            cats = database.category_list(include_archived=True)
            cat_map = {c["id"]: c for c in cats}
            pdf.add_heading(t("byCategory", self.lang), level=2)
            data = []
            for item in by_cat:
                cat = cat_map.get(item["category_id"], {})
                name = cat.get(f"name_{self.lang}") or cat.get("name_en") or "—"
                color = cat.get("color") or config.GOLD
                data.append({"label": name, "value": item["total_min"], "color": color})
            pdf.add_donut_chart(data, t("byCategory", self.lang))

        # By weekday
        by_wd = stats_service.by_weekday(start_iso, end_iso)
        if by_wd:
            pdf.add_heading(t("byDayOfWeek", self.lang), level=2)
            # %w: 0=Sun..6=Sat
            wd_names_fa = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه",
                           "پنجشنبه", "جمعه", "شنبه"]
            wd_names_en = ["Sunday", "Monday", "Tuesday", "Wednesday",
                           "Thursday", "Friday", "Saturday"]
            data = []
            for item in by_wd:
                idx = item["weekday"]
                name = wd_names_fa[idx] if self.lang == "fa" else wd_names_en[idx]
                data.append({"label": name, "value": item["total_min"],
                             "color": config.GOLD})
            pdf.add_bar_chart(data, t("byDayOfWeek", self.lang))

        # Insights
        try:
            insights = stats_service.insights(start_iso, end_iso)
            if insights:
                pdf.add_heading(t("insightsTitle", self.lang), level=2)
                for ins in insights:
                    title = ins.get("title_fa") if self.lang == "fa" else ins.get("title_en")
                    body = ins.get("body_fa") if self.lang == "fa" else ins.get("body_en")
                    if title:
                        pdf.add_paragraph(f"• {title}")
                    if body:
                        pdf.add_paragraph(f"   {body}")
        except Exception:
            pass

        # Goals progress
        goals = database.goal_list(only_active=True)
        if goals:
            pdf.add_heading(t("goalProgress", self.lang), level=2)
            for g in goals:
                if g["period"] != "monthly":
                    continue
                progress = goal_service.progress_for(g["id"], start_iso)
                title = g.get("title") or t("allCategories", self.lang)
                pct = int(progress.get("percent", 0))
                pdf.add_paragraph(
                    f"• {title}: {_p(pct, self.lang)}٪ "
                    f"({_format_duration_long(progress.get('current_min', 0), self.lang)} "
                    f"/ {_format_duration_long(progress.get('target_min', 0), self.lang)})"
                )


# =============================================================================
# === Yearly review template                                                   ===
# =============================================================================

class YearlyReviewTemplate:
    """12-month retrospective with yearly heatmap."""

    name = "yearly_review"
    name_fa = "مرور سالانه"
    name_en = "Yearly Review"

    def __init__(self, lang: str = "fa"):
        self.lang = lang

    def populate(self, pdf: "PdfExporter", year: Optional[int] = None) -> None:
        from ..services import stats_service
        from ..core.time_utils import today_iso

        today = today_iso()
        if year is None:
            jy, _, _ = jalali.iso_to_jalali(today)
            year = jy
        try:
            start_iso = jalali.jalali_to_iso(year, 1, 1)
            end_iso = jalali.jalali_to_iso(year, 12, 29)
        except Exception:
            start_iso = today
            end_iso = today

        pdf.set_title(f"{t('thisYear', self.lang)} — {_p(year, self.lang)}")
        pdf.add_heading(f"{t('thisYear', self.lang)} — {_p(year, self.lang)}", level=1)

        # Yearly stats
        summary = stats_service.summary(start_iso, end_iso)
        pdf.add_heading(t("statistics", self.lang), level=2)
        pdf.add_summary_table({
            t("totalTime", self.lang): _format_duration_long(summary.get("total_min", 0), self.lang),
            t("totalActivities", self.lang): _p(summary.get("total_activities", 0), self.lang),
            t("avgPerDay", self.lang): _format_duration_long(
                summary.get("avg_per_day", 0), self.lang),
            t("longestStreak", self.lang): _p(summary.get("longest_streak", 0), self.lang)
                + " " + t("days", self.lang),
        })

        # Yearly heatmap
        try:
            heatmap = stats_service.heatmap_data(year)
            if heatmap:
                pdf.add_heading(t("heatmap", self.lang), level=2)
                pdf.add_heatmap(heatmap, t("heatmap", self.lang))
        except Exception:
            pass

        # Month-by-month breakdown
        by_month = stats_service.by_month(start_iso, end_iso)
        if by_month:
            pdf.add_heading(t("byMonth", self.lang), level=2)
            data = []
            for item in by_month:
                ym = item["month"]  # "YYYY-MM"
                try:
                    m = int(ym.split("-")[1])
                except Exception:
                    m = 0
                month_name = jalali.jalali_month_name(m, self.lang) or ym
                data.append({"label": month_name, "value": item["total_min"],
                             "color": config.GOLD})
            pdf.add_bar_chart(data, t("totalTime", self.lang))

        # Top categories
        by_cat = stats_service.by_category(start_iso, end_iso)
        if by_cat:
            from .. import database
            cats = database.category_list(include_archived=True)
            cat_map = {c["id"]: c for c in cats}
            pdf.add_heading(t("byCategory", self.lang), level=2)
            data = []
            for item in by_cat:
                cat = cat_map.get(item["category_id"], {})
                name = cat.get(f"name_{self.lang}") or cat.get("name_en") or "—"
                color = cat.get("color") or config.GOLD
                data.append({"label": name, "value": item["total_min"], "color": color})
            pdf.add_donut_chart(data, t("byCategory", self.lang))

        # Year insights
        try:
            insights = stats_service.insights(start_iso, end_iso)
            if insights:
                pdf.add_heading(t("insightsTitle", self.lang), level=2)
                for ins in insights[:10]:
                    title = ins.get("title_fa") if self.lang == "fa" else ins.get("title_en")
                    body = ins.get("body_fa") if self.lang == "fa" else ins.get("body_en")
                    if title:
                        pdf.add_paragraph(f"• {title}")
                    if body:
                        pdf.add_paragraph(f"   {body}")
        except Exception:
            pass


# =============================================================================
# === Registry                                                                 ===
# =============================================================================

TEMPLATES: dict[str, type] = {
    "daily_log": DailyLogTemplate,
    "weekly_summary": WeeklySummaryTemplate,
    "monthly_report": MonthlyReportTemplate,
    "yearly_review": YearlyReviewTemplate,
}


def get_template(name: str, lang: str = "fa"):
    """Get a template instance by name."""
    cls = TEMPLATES.get(name)
    if cls is None:
        raise KeyError(f"Unknown template: {name!r}.  Available: {list(TEMPLATES)}")
    return cls(lang=lang)


def available_templates() -> list[str]:
    """Return list of available template names."""
    return sorted(TEMPLATES.keys())


__all__ = [
    "DailyLogTemplate", "WeeklySummaryTemplate",
    "MonthlyReportTemplate", "YearlyReviewTemplate",
    "TEMPLATES", "get_template", "available_templates",
]
