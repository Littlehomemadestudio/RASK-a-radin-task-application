"""
date_utils.py — Date helpers shared across the app.

All date math uses the user's local timezone (datetime.now() / date.today()).
Persian (Jalali) formatting is provided without external libs via a small
algorithm (Toomás / Borkowski). Output is purely for display.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional


# === ISO helpers ===

def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iso_to_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def iso_to_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s)


# === Range helpers ===

def start_of_day(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())


def end_of_day(d: date) -> datetime:
    return datetime.combine(d, datetime.max.time())


def start_of_week(d: date, week_start_monday: bool = True) -> date:
    """Returns the Monday (or Sunday) of d's week."""
    delta = d.weekday() if week_start_monday else (d.weekday() + 1) % 7
    return d - timedelta(days=delta)


def end_of_week(d: date, week_start_monday: bool = True) -> date:
    s = start_of_week(d, week_start_monday)
    return s + timedelta(days=6)


def start_of_month(d: date) -> date:
    return d.replace(day=1)


def end_of_month(d: date) -> date:
    if d.month == 12:
        nxt = d.replace(year=d.year + 1, month=1, day=1)
    else:
        nxt = d.replace(month=d.month + 1, day=1)
    return nxt - timedelta(days=1)


def start_of_year(d: date) -> date:
    return d.replace(month=1, day=1)


def end_of_year(d: date) -> date:
    return d.replace(month=12, day=31)


def last_n_days(d: date, n: int) -> tuple[str, str]:
    """Returns (start_iso, end_iso) covering [d-n+1 .. d]."""
    start = d - timedelta(days=n - 1)
    return start.isoformat(), d.isoformat()


def daterange(start: date, end: date):
    """Inclusive date iterator."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


# === Formatting ===

WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_date(d: date, lang: str = "en") -> str:
    if lang == "fa":
        y, m, day = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{_fa(day)} {_jalali_month(m)} {_fa(y)}"
    return f"{d.day:02d} {MONTHS_EN[d.month - 1]} {d.year}"


def fmt_short_date(d: date, lang: str = "en") -> str:
    if lang == "fa":
        y, m, day = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{_fa(day)}/{_fa(m)}/{_fa(y)}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def fmt_weekday(d: date, lang: str = "en") -> str:
    idx = d.weekday()
    if lang == "fa":
        return WEEKDAYS_FA[idx]
    return WEEKDAYS_EN[idx]


def fmt_relative(iso: str, lang: str = "en") -> str:
    """'2 days ago' / '۲ روز پیش'."""
    try:
        d = iso_to_date(iso)
    except Exception:
        return ""
    today = date.today()
    diff = (today - d).days
    if diff == 0:
        return "امروز" if lang == "fa" else "Today"
    if diff == 1:
        return "دیروز" if lang == "fa" else "Yesterday"
    if diff < 7:
        n = _fa(diff) if lang == "fa" else str(diff)
        unit = "روز" if lang == "fa" else "days"
        ago = "پیش" if lang == "fa" else "ago"
        return f"{n} {unit} {ago}"
    if diff < 30:
        weeks = diff // 7
        n = _fa(weeks) if lang == "fa" else str(weeks)
        unit = "هفته" if lang == "fa" else "weeks"
        ago = "پیش" if lang == "fa" else "ago"
        return f"{n} {unit} {ago}"
    if diff < 365:
        months = diff // 30
        n = _fa(months) if lang == "fa" else str(months)
        unit = "ماه" if lang == "fa" else "months"
        ago = "پیش" if lang == "fa" else "ago"
        return f"{n} {unit} {ago}"
    years = diff // 365
    n = _fa(years) if lang == "fa" else str(years)
    unit = "سال" if lang == "fa" else "years"
    ago = "پیش" if lang == "fa" else "ago"
    return f"{n} {unit} {ago}"


# === Jalali (Persian) calendar conversion ===

_JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def _jalali_month(m: int) -> str:
    if 1 <= m <= 12:
        return _JALALI_MONTHS[m - 1]
    return str(m)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Algorithm by Kazimierz M. Borkowski (1996)."""
    if gm <= 2:
        gy -= 1
        g_days = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400 \
                 + gd + (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)[gm - 1]
    else:
        g_days = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400 \
                 + gd + (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)[gm - 1]
    j_days = g_days - 79
    j_np = j_days // 12053
    j_days %= 12053
    jy = 979 + 33 * j_np + 4 * (j_days // 1461)
    j_days %= 1461
    if j_days >= 366:
        jy += (j_days - 1) // 365
        j_days = (j_days - 1) % 365
    if j_days < 186:
        jm = 1 + j_days // 31
        jd = 1 + (j_days % 31)
    else:
        jm = 7 + (j_days - 186) // 30
        jd = 1 + (j_days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy -= 979
    j_days = 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + jd
    if jm < 7:
        j_days += (jm - 1) * 31
    else:
        j_days += (jm - 7) * 30 + 186
    g_days = j_days + 79
    gy = 1600 + 400 * (g_days // 146097)
    g_days %= 146097
    if g_days >= 36525:
        g_days -= 1
        gy += 100 * (g_days // 36524)
        g_days %= 36524
        if g_days >= 365:
            g_days += 1
    gy += 4 * (g_days // 1461)
    g_days %= 1461
    if g_days >= 366:
        gy += (g_days - 1) // 365
        g_days = (g_days - 1) % 365
    sal_a = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    if leap:
        sal_a[2] = 29
    gm = 0
    while gm < 13 and g_days > sal_a[gm]:
        g_days -= sal_a[gm]
        gm += 1
    return gy, gm, g_days


# === Persian digit conversion ===

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _to_fa_digits(s: str) -> str:
    return s.translate(_FA_DIGITS)


def _fa(n) -> str:
    return _to_fa_digits(str(n))
