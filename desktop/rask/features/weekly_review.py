"""
rask.features.weekly_review
===========================

Weekly review generator.

Pulls together data from:

  • ``activity_service`` + ``stats_service`` — total time, top category,
    longest streak, goal hits
  • ``journal_service`` — mood & energy averages
  • ``mood_service`` — mood / energy averages (alternative source)
  • ``goal_service`` — goals hit/missed
  • ``habit_service`` — habit completion rate
  • ``time_block_service`` — scheduled vs completed blocks

Then formats the result as:

  • ``format_text``   — plain text (Telegram-friendly)
  • ``format_html``   — HTML email-style
  • ``format_markdown`` — Markdown (for GitHub/Notion)

The :meth:`share` method copies the formatted text to the clipboard
via the platform-appropriate mechanism (``pbcopy`` on macOS,
``clip.exe`` on Windows, ``xclip`` / ``xsel`` on Linux).

Events
------

  ``weekly_review.generated`` — {week_iso, total_min, format}
  ``weekly_review.shared``    — {week_iso, format, success}
"""
from __future__ import annotations

import platform
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    end_of_week,
    range_days,
    start_of_week,
    today_iso,
)

__all__ = [
    "WeeklyReview",
    "weekly_review",
]

_log = get_logger("features.weekly_review")


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _fa(value: Any) -> str:
    return i18n.to_fa_digits(value)


def _weekday_name_fa(weekday_py: int) -> str:
    names = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
             "جمعه", "شنبه", "یکشنبه"]
    return names[weekday_py % 7]


def _format_minutes_fa(m: int) -> str:
    """Format minutes as 'X ساعت Y دقیقه' in Persian."""
    m = max(0, int(m))
    h = m // 60
    mm = m % 60
    if h and mm:
        return f"{_fa(h)} ساعت و {_fa(mm)} دقیقه"
    if h:
        return f"{_fa(h)} ساعت"
    return f"{_fa(mm)} دقیقه"


def _format_minutes_en(m: int) -> str:
    m = max(0, int(m))
    h = m // 60
    mm = m % 60
    if h and mm:
        return f"{h}h {mm}m"
    if h:
        return f"{h}h"
    return f"{mm}m"


def _copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the system clipboard.  Returns True on success."""
    if not text:
        return False
    system = platform.system()
    try:
        if system == "Darwin":
            p = subprocess.run(["pbcopy"], input=text.encode("utf-8"),
                                timeout=5)
            return p.returncode == 0
        if system == "Windows":
            # Use clip.exe — note: clip.exe expects UTF-16 LE with BOM
            # for non-ASCII characters, but cp1256 often works for Persian.
            try:
                p = subprocess.run(["clip.exe"], input=text.encode("utf-16le"),
                                    timeout=5)
                return p.returncode == 0
            except Exception:  # noqa: BLE001
                return False
        # Linux: try xclip then xsel
        for cmd in (["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"]):
            try:
                p = subprocess.run(cmd, input=text.encode("utf-8"),
                                    timeout=5)
                if p.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
            except Exception:  # noqa: BLE001
                continue
        return False
    except Exception as exc:  # noqa: BLE001
        _log.warning("Clipboard copy failed: %s", exc)
        return False


# =============================================================================
# === WeeklyReview                                                           ===
# =============================================================================

class WeeklyReview:
    """Weekly review generator."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def generate(self, week_iso: Optional[str] = None) -> Dict[str, Any]:
        """Generate a weekly review dict for the week containing `week_iso`.

        If `week_iso` is None, the current week is used.
        """
        with self._lock:
            anchor = week_iso or today_iso()
            week_start = start_of_week(anchor, first_day=6)
            week_end = end_of_week(anchor, first_day=6)
            prev_week_start = add_days(week_start, -7)
            prev_week_end = add_days(week_end, -7)

            # Activities
            total_min = db.activity_sum_duration(date_from=week_start,
                                                  date_to=week_end)
            total_count = db.activity_count(date_from=week_start,
                                             date_to=week_end)
            prev_total_min = db.activity_sum_duration(date_from=prev_week_start,
                                                       date_to=prev_week_end)
            delta_min = total_min - prev_total_min

            # Top category
            by_cat = db.activity_group_by_category(date_from=week_start,
                                                    date_to=week_end)
            cats_map = {int(c["id"]): c for c in db.category_list()}
            top_cat_name = "—"
            top_cat_color = "#9A9A9F"
            if by_cat:
                top = max(by_cat,
                            key=lambda r: int(r.get("total_min") or 0))
                cid = int(top["category_id"] or 0)
                cat = cats_map.get(cid, {})
                top_cat_name = cat.get("name_fa") or cat.get("name_en") or "—"
                top_cat_color = cat.get("color") or "#9A9A9F"

            # Streak (any-activity)
            try:
                from ..services.stats_service import stats_service
                longest_streak = stats_service.current_streak()
                best_ever = stats_service.longest_streak_ever()
            except Exception:  # noqa: BLE001
                longest_streak = 0
                best_ever = 0

            # Goal hits
            goal_hits = 0
            goal_misses = 0
            try:
                from ..services.goal_service import goal_service
                for g in goal_service.list(only_active=True):
                    if goal_service.hit_date(g["id"], week_end):
                        goal_hits += 1
                    else:
                        goal_misses += 1
            except Exception:  # noqa: BLE001
                pass

            # Mood & energy (try mood_tracker first, fall back to journal)
            mood_avg: Optional[float] = None
            energy_avg: Optional[float] = None
            try:
                from .mood_tracker import mood_service
                entries = mood_service.list(date_from=week_start,
                                             date_to=week_end, limit=1000)
                if entries:
                    mood_avg = round(sum(e.mood for e in entries) / len(entries), 2)
                    energies = [e.energy for e in entries if e.energy is not None]
                    if energies:
                        energy_avg = round(sum(energies) / len(energies), 2)
            except Exception:  # noqa: BLE001
                pass
            if mood_avg is None:
                try:
                    from .journal import journal_service
                    entries = journal_service.list(date_from=week_start,
                                                    date_to=week_end)
                    moods = [e.mood for e in entries if e.mood is not None]
                    energies = [e.energy for e in entries if e.energy is not None]
                    if moods:
                        mood_avg = round(sum(moods) / len(moods), 2)
                    if energies and energy_avg is None:
                        energy_avg = round(sum(energies) / len(energies), 2)
                except Exception:  # noqa: BLE001
                    pass

            # Habit completion
            habit_completion_rate = 0.0
            try:
                from .habits import habit_service
                habits = habit_service.list_habits()
                if habits:
                    rates = []
                    for h in habits:
                        # completion_rate over 7 days
                        rates.append(habit_service.completion_rate(h.id or 0, 7))
                    habit_completion_rate = round(sum(rates) / len(rates), 2)
            except Exception:  # noqa: BLE001
                pass

            # Highlights & lowlights
            highlights: List[str] = []
            lowlights: List[str] = []
            by_day = db.activity_group_by_day(date_from=week_start,
                                               date_to=week_end)
            if by_day:
                best_day = max(by_day,
                                key=lambda r: int(r.get("total_min") or 0))
                worst_day = min(by_day,
                                 key=lambda r: int(r.get("total_min") or 0))
                if int(best_day.get("total_min") or 0) > 0:
                    highlights.append(
                        f"بهترین روز: {_weekday_name_fa(date.fromisoformat(best_day['date_iso']).weekday())} "
                        f"با {_format_minutes_fa(int(best_day['total_min']))}"
                    )
                if int(worst_day.get("total_min") or 0) == 0:
                    lowlights.append(
                        f"روز بدون فعالیت: {_weekday_name_fa(date.fromisoformat(worst_day['date_iso']).weekday())}"
                    )
            if delta_min > 0:
                highlights.append(
                    f"افزایش {_format_minutes_fa(delta_min)} نسبت به هفته قبل"
                )
            elif delta_min < 0:
                lowlights.append(
                    f"کاهش {_format_minutes_fa(abs(delta_min))} نسبت به هفته قبل"
                )
            if goal_hits > 0:
                highlights.append(f"{_fa(goal_hits)} هدف محقق شد")
            if goal_misses > 0:
                lowlights.append(f"{_fa(goal_misses)} هدف محقق نشد")
            if longest_streak >= 7:
                highlights.append(f"زنجیره {_fa(longest_streak)} روزه")

            # Recommendations
            recommendations: List[str] = []
            if total_min < 300:
                recommendations.append(
                    "زمان کل هفته پایین است. یک هدف روزانه تعیین کن."
                )
            if mood_avg is not None and mood_avg < 3:
                recommendations.append(
                    "میانگین حال پایین است. به دنبال فعالیت‌هایی برو که حالت را بهتر می‌کنند."
                )
            if habit_completion_rate < 0.5:
                recommendations.append(
                    "نرخ تکمیل عادت‌ها پایین است. اهداف کوچک‌تر و واقع‌بینانه تعیین کن."
                )
            if goal_misses > goal_hits:
                recommendations.append(
                    "بیشتر اهداف محقق نشده‌اند. اهداف را بازبینی کن."
                )
            if not recommendations:
                recommendations.append("همه چیز خوب پیش رفت! هفته بعد را قوی‌تر ادامه بده.")

            review = {
                "week_iso": anchor,
                "week_start": week_start,
                "week_end": week_end,
                "total_min": int(total_min),
                "total_activities": int(total_count),
                "delta_vs_last_week_min": int(delta_min),
                "top_category": top_cat_name,
                "top_category_color": top_cat_color,
                "longest_streak": int(longest_streak),
                "best_streak_ever": int(best_ever),
                "goal_hits": int(goal_hits),
                "goal_misses": int(goal_misses),
                "mood_avg": mood_avg,
                "energy_avg": energy_avg,
                "habit_completion_rate": float(habit_completion_rate),
                "comparison_vs_last_week_pct": (
                    int(round(delta_min / prev_total_min * 100))
                    if prev_total_min > 0 else (100 if delta_min > 0 else 0)
                ),
                "highlights": highlights,
                "lowlights": lowlights,
                "recommendations": recommendations,
                "by_day": [
                    {"date_iso": r["date_iso"],
                     "total_min": int(r.get("total_min") or 0),
                     "count": int(r.get("count") or 0)}
                    for r in by_day
                ],
            }
            bus.publish("weekly_review.generated", {
                "week_iso": anchor,
                "total_min": total_min,
                "format": "raw",
            })
            return review

    # ------------------------------------------------------------------
    # Formatters
    # ------------------------------------------------------------------

    def format_text(self, review: Dict[str, Any], lang: str = "fa") -> str:
        """Plain-text format (Telegram / SMS friendly)."""
        if lang == "fa":
            return self._format_text_fa(review)
        return self._format_text_en(review)

    def _format_text_fa(self, r: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("📋 مرور هفتگی")
        lines.append(f"📅 هفته: {_fa(r['week_start'])} تا {_fa(r['week_end'])}")
        lines.append("")
        lines.append("⏱  زمان کل: " + _format_minutes_fa(r["total_min"]))
        lines.append(f"📝 تعداد فعالیت: {_fa(r['total_activities'])}")
        delta = r["delta_vs_last_week_min"]
        if delta > 0:
            lines.append(f"▲ نسبت به هفته قبل: +{_format_minutes_fa(delta)}")
        elif delta < 0:
            lines.append(f"▼ نسبت به هفته قبل: -{_format_minutes_fa(abs(delta))}")
        lines.append(f"🏆 دسته برتر: {r['top_category']}")
        lines.append(f"🔥 زنجیره فعلی: {_fa(r['longest_streak'])} روز "
                      f"(رکورد: {_fa(r['best_streak_ever'])})")
        lines.append(f"✅ اهداف محقق: {_fa(r['goal_hits'])} / "
                      f"{_fa(r['goal_hits'] + r['goal_misses'])}")
        if r.get("mood_avg") is not None:
            lines.append(f"😊 میانگین حال: {_fa(r['mood_avg'])}/۵")
        if r.get("energy_avg") is not None:
            lines.append(f"⚡ میانگین انرژی: {_fa(r['energy_avg'])}/۵")
        lines.append(f"🎯 نرخ تکمیل عادت‌ها: "
                      f"{_fa(int(r['habit_completion_rate'] * 100))}٪")
        if r["highlights"]:
            lines.append("")
            lines.append("✨ نکات مثبت:")
            for h in r["highlights"]:
                lines.append(f"  • {h}")
        if r["lowlights"]:
            lines.append("")
            lines.append("⚠️ نقاط قابل بهبود:")
            for l in r["lowlights"]:
                lines.append(f"  • {l}")
        if r["recommendations"]:
            lines.append("")
            lines.append("💡 پیشنهادات:")
            for rec in r["recommendations"]:
                lines.append(f"  • {rec}")
        lines.append("")
        lines.append("— رَسک")
        return "\n".join(lines)

    def _format_text_en(self, r: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append("Weekly Review")
        lines.append(f"Week: {r['week_start']} to {r['week_end']}")
        lines.append("")
        lines.append(f"Total time: {_format_minutes_en(r['total_min'])}")
        lines.append(f"Activities: {r['total_activities']}")
        delta = r["delta_vs_last_week_min"]
        if delta > 0:
            lines.append(f"vs last week: +{_format_minutes_en(delta)}")
        elif delta < 0:
            lines.append(f"vs last week: -{_format_minutes_en(abs(delta))}")
        lines.append(f"Top category: {r['top_category']}")
        lines.append(f"Current streak: {r['longest_streak']} days "
                      f"(best: {r['best_streak_ever']})")
        lines.append(f"Goals hit: {r['goal_hits']} / "
                      f"{r['goal_hits'] + r['goal_misses']}")
        if r.get("mood_avg") is not None:
            lines.append(f"Average mood: {r['mood_avg']}/5")
        if r.get("energy_avg") is not None:
            lines.append(f"Average energy: {r['energy_avg']}/5")
        lines.append(f"Habit completion: "
                      f"{int(r['habit_completion_rate'] * 100)}%")
        if r["highlights"]:
            lines.append("")
            lines.append("Highlights:")
            for h in r["highlights"]:
                lines.append(f"  - {h}")
        if r["lowlights"]:
            lines.append("")
            lines.append("Lowlights:")
            for l in r["lowlights"]:
                lines.append(f"  - {l}")
        if r["recommendations"]:
            lines.append("")
            lines.append("Recommendations:")
            for rec in r["recommendations"]:
                lines.append(f"  - {rec}")
        lines.append("")
        lines.append("— Rask")
        return "\n".join(lines)

    def format_html(self, review: Dict[str, Any], lang: str = "fa") -> str:
        """HTML email-style format."""
        if lang == "fa":
            return self._format_html_fa(review)
        return self._format_html_en(review)

    def _format_html_fa(self, r: Dict[str, Any]) -> str:
        css = """
        <style>
            body { font-family: 'Vazirmatn', Tahoma, sans-serif;
                    background: #0E0E10; color: #E8E8E8; direction: rtl;
                    padding: 24px; max-width: 540px; margin: 0 auto; }
            h1 { color: #D4AF37; border-bottom: 1px solid #2C2C30;
                  padding-bottom: 12px; }
            h2 { color: #C9A84C; margin-top: 24px; }
            .stat { display: inline-block; padding: 12px 16px;
                     background: #1A1A1D; border-radius: 8px; margin: 4px;
                     min-width: 120px; }
            .stat .label { color: #9A9A9F; font-size: 12px; }
            .stat .value { color: #D4AF37; font-size: 18px; font-weight: bold; }
            ul { padding-right: 20px; }
            li { margin: 6px 0; }
            .highlight { color: #7BC97B; }
            .lowlights { color: #E8B85A; }
            .footer { color: #5C5C60; font-size: 11px;
                       border-top: 1px solid #2C2C30; padding-top: 12px;
                       margin-top: 24px; text-align: center; }
        </style>
        """
        highlights = "".join(f"<li class='highlight'>{h}</li>"
                              for h in r["highlights"])
        lowlights = "".join(f"<li class='lowlights'>{l}</li>"
                             for l in r["lowlights"])
        recs = "".join(f"<li>{rec}</li>" for rec in r["recommendations"])
        return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head><meta charset="utf-8">{css}<title>مرور هفتگی</title></head>
<body>
<h1>📋 مرور هفتگی</h1>
<p>📅 هفته: <b>{_fa(r['week_start'])}</b> تا <b>{_fa(r['week_end'])}</b></p>

<div class='stat'><div class='label'>زمان کل</div>
    <div class='value'>{_format_minutes_fa(r['total_min'])}</div></div>
<div class='stat'><div class='label'>تعداد فعالیت</div>
    <div class='value'>{_fa(r['total_activities'])}</div></div>
<div class='stat'><div class='label'>دسته برتر</div>
    <div class='value'>{r['top_category']}</div></div>
<div class='stat'><div class='label'>زنجیره</div>
    <div class='value'>{_fa(r['longest_streak'])} روز</div></div>
<div class='stat'><div class='label'>اهداف محقق</div>
    <div class='value'>{_fa(r['goal_hits'])} / {_fa(r['goal_hits'] + r['goal_misses'])}</div></div>
{(f"<div class='stat'><div class='label'>میانگین حال</div><div class='value'>{_fa(r['mood_avg'])}/۵</div></div>" if r.get('mood_avg') is not None else '')}

{('<h2>✨ نکات مثبت</h2><ul>' + highlights + '</ul>') if highlights else ''}
{('<h2>⚠️ نقاط قابل بهبود</h2><ul>' + lowlights + '</ul>') if lowlights else ''}
{('<h2>💡 پیشنهادات</h2><ul>' + recs + '</ul>') if recs else ''}

<div class='footer'>رَسک — زمان، ظریف.</div>
</body></html>"""

    def _format_html_en(self, r: Dict[str, Any]) -> str:
        css = """
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                    sans-serif; background: #0E0E10; color: #E8E8E8;
                    padding: 24px; max-width: 540px; margin: 0 auto; }
            h1 { color: #D4AF37; border-bottom: 1px solid #2C2C30;
                  padding-bottom: 12px; }
            h2 { color: #C9A84C; margin-top: 24px; }
            .stat { display: inline-block; padding: 12px 16px;
                     background: #1A1A1D; border-radius: 8px; margin: 4px;
                     min-width: 120px; }
            .stat .label { color: #9A9A9F; font-size: 12px; }
            .stat .value { color: #D4AF37; font-size: 18px; font-weight: bold; }
            ul { padding-left: 20px; }
            li { margin: 6px 0; }
            .highlight { color: #7BC97B; }
            .lowlights { color: #E8B85A; }
            .footer { color: #5C5C60; font-size: 11px;
                       border-top: 1px solid #2C2C30; padding-top: 12px;
                       margin-top: 24px; text-align: center; }
        </style>
        """
        highlights = "".join(f"<li class='highlight'>{h}</li>"
                              for h in r["highlights"])
        lowlights = "".join(f"<li class='lowlights'>{l}</li>"
                             for l in r["lowlights"])
        recs = "".join(f"<li>{rec}</li>" for rec in r["recommendations"])
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">{css}<title>Weekly Review</title></head>
<body>
<h1>📋 Weekly Review</h1>
<p>📅 Week: <b>{r['week_start']}</b> to <b>{r['week_end']}</b></p>

<div class='stat'><div class='label'>Total time</div>
    <div class='value'>{_format_minutes_en(r['total_min'])}</div></div>
<div class='stat'><div class='label'>Activities</div>
    <div class='value'>{r['total_activities']}</div></div>
<div class='stat'><div class='label'>Top category</div>
    <div class='value'>{r['top_category']}</div></div>
<div class='stat'><div class='label'>Streak</div>
    <div class='value'>{r['longest_streak']} days</div></div>
<div class='stat'><div class='label'>Goals hit</div>
    <div class='value'>{r['goal_hits']} / {r['goal_hits'] + r['goal_misses']}</div></div>
{(f"<div class='stat'><div class='label'>Avg mood</div><div class='value'>{r['mood_avg']}/5</div></div>" if r.get('mood_avg') is not None else '')}

{('<h2>✨ Highlights</h2><ul>' + highlights + '</ul>') if highlights else ''}
{('<h2>⚠️ Lowlights</h2><ul>' + lowlights + '</ul>') if lowlights else ''}
{('<h2>💡 Recommendations</h2><ul>' + recs + '</ul>') if recs else ''}

<div class='footer'>Rask — Time, refined.</div>
</body></html>"""

    def format_markdown(self, review: Dict[str, Any], lang: str = "fa") -> str:
        """Markdown format (GitHub / Notion friendly)."""
        r = review
        if lang == "fa":
            lines: List[str] = []
            lines.append("# 📋 مرور هفتگی")
            lines.append("")
            lines.append(f"**هفته:** {_fa(r['week_start'])} — {_fa(r['week_end'])}")
            lines.append("")
            lines.append("## آمار")
            lines.append(f"- **زمان کل:** {_format_minutes_fa(r['total_min'])}")
            lines.append(f"- **تعداد فعالیت:** {_fa(r['total_activities'])}")
            lines.append(f"- **دسته برتر:** {r['top_category']}")
            lines.append(f"- **زنجیره فعلی:** {_fa(r['longest_streak'])} روز "
                          f"(رکورد: {_fa(r['best_streak_ever'])})")
            lines.append(f"- **اهداف محقق:** {_fa(r['goal_hits'])} / "
                          f"{_fa(r['goal_hits'] + r['goal_misses'])}")
            if r.get("mood_avg") is not None:
                lines.append(f"- **میانگین حال:** {_fa(r['mood_avg'])}/۵")
            if r.get("energy_avg") is not None:
                lines.append(f"- **میانگین انرژی:** {_fa(r['energy_avg'])}/۵")
            lines.append(f"- **نرخ تکمیل عادت‌ها:** "
                          f"{_fa(int(r['habit_completion_rate'] * 100))}٪")
            if r["highlights"]:
                lines.append("")
                lines.append("## ✨ نکات مثبت")
                for h in r["highlights"]:
                    lines.append(f"- {h}")
            if r["lowlights"]:
                lines.append("")
                lines.append("## ⚠️ نقاط قابل بهبود")
                for l in r["lowlights"]:
                    lines.append(f"- {l}")
            if r["recommendations"]:
                lines.append("")
                lines.append("## 💡 پیشنهادات")
                for rec in r["recommendations"]:
                    lines.append(f"- {rec}")
            return "\n".join(lines)
        # English
        lines = []
        lines.append("# 📋 Weekly Review")
        lines.append("")
        lines.append(f"**Week:** {r['week_start']} — {r['week_end']}")
        lines.append("")
        lines.append("## Stats")
        lines.append(f"- **Total time:** {_format_minutes_en(r['total_min'])}")
        lines.append(f"- **Activities:** {r['total_activities']}")
        lines.append(f"- **Top category:** {r['top_category']}")
        lines.append(f"- **Current streak:** {r['longest_streak']} days "
                      f"(best: {r['best_streak_ever']})")
        lines.append(f"- **Goals hit:** {r['goal_hits']} / "
                      f"{r['goal_hits'] + r['goal_misses']}")
        if r.get("mood_avg") is not None:
            lines.append(f"- **Average mood:** {r['mood_avg']}/5")
        if r.get("energy_avg") is not None:
            lines.append(f"- **Average energy:** {r['energy_avg']}/5")
        lines.append(f"- **Habit completion:** "
                      f"{int(r['habit_completion_rate'] * 100)}%")
        if r["highlights"]:
            lines.append("")
            lines.append("## ✨ Highlights")
            for h in r["highlights"]:
                lines.append(f"- {h}")
        if r["lowlights"]:
            lines.append("")
            lines.append("## ⚠️ Lowlights")
            for l in r["lowlights"]:
                lines.append(f"- {l}")
        if r["recommendations"]:
            lines.append("")
            lines.append("## 💡 Recommendations")
            for rec in r["recommendations"]:
                lines.append(f"- {rec}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Share
    # ------------------------------------------------------------------

    def share(self, review: Dict[str, Any], format_: str = "text",
              lang: str = "fa") -> str:
        """Format the review and copy to clipboard.

        ``format_`` is one of ``text``, ``html``, ``markdown``.
        Returns the formatted string.
        """
        if format_ == "html":
            text = self.format_html(review, lang)
        elif format_ == "markdown":
            text = self.format_markdown(review, lang)
        else:
            text = self.format_text(review, lang)
        success = _copy_to_clipboard(text)
        bus.publish("weekly_review.shared", {
            "week_iso": review.get("week_iso"),
            "format": format_,
            "success": success,
        })
        return text


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

weekly_review: WeeklyReview = WeeklyReview()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== weekly_review self-tests ===")
    try:
        r = weekly_review.generate()
        assert "total_min" in r and "week_iso" in r
        text = weekly_review.format_text(r, lang="fa")
        assert "مرور هفتگی" in text
        md = weekly_review.format_markdown(r, lang="en")
        assert "Weekly Review" in md
        html = weekly_review.format_html(r, lang="fa")
        assert "<html" in html
        print("  OK   generated + formatted (fa/en, text/html/md)")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
