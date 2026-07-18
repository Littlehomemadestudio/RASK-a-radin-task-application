"""date_utils.py — Gregorian + Jalali (Persian) calendar helpers (mirror of date-utils.js)."""
from __future__ import annotations
import datetime as _dt
from typing import Iterator, Tuple
from .i18n import to_fa_digits, t


def today_iso() -> str:
    return _dt.date.today().isoformat()


def now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso(s: str) -> _dt.datetime:
    if not s:
        return _dt.datetime.now()
    try:
        return _dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            return _dt.datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return _dt.datetime.now()


def is_leap(y: int) -> bool:
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def start_of_day(d: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(d.year, d.month, d.day)


def end_of_day(d: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(d.year, d.month, d.day, 23, 59, 59, 999000)


def start_of_week(d: _dt.datetime) -> _dt.datetime:
    """Saturday-start week (match JS: (getDay()+1)%7 — Sat=0)."""
    x = start_of_day(d)
    offset = (x.weekday() + 1) % 7  # Monday=0 in Python; +1 makes Sun=0 ... wait, match JS.
    # In JS getDay(): Sun=0..Sat=6. (getDay()+1)%7 makes Sat=0.
    # Python weekday(): Mon=0..Sun=6. To map to JS getDay(): (weekday()+1)%7 gives Mon=1, Sun=0.
    # Actually Python weekday Mon=0 → JS getDay Mon=1. (weekday()+1)%7 == 1 for Mon == JS Mon. ✓
    # For Sat: Python weekday=5 → JS getDay=6. (5+1)%7=6 ✓.
    # So (weekday()+1)%7 == JS getDay() value.
    js_day = (x.weekday() + 1) % 7
    # We want week to start on Saturday (JS offset (getDay()+1)%7). Wait: the JS code does
    #   day = (x.getDay() + 1) % 7; x.setDate(x.getDate() - day);
    # For Sat: getDay=6 → day=(6+1)%7=0 → no shift (Sat is the start). ✓
    # For Sun: getDay=0 → day=1 → shift back 1 to Sat. ✓
    # So the JS code: subtract ((getDay()+1)%7) days.
    offset_days = (js_day + 1) % 7
    return x - _dt.timedelta(days=offset_days)


def end_of_week(d: _dt.datetime) -> _dt.datetime:
    s = start_of_week(d)
    return end_of_day(s + _dt.timedelta(days=6))


def start_of_month(d: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(d.year, d.month, 1)


def end_of_month(d: _dt.datetime) -> _dt.datetime:
    if d.month == 12:
        nxt = _dt.datetime(d.year + 1, 1, 1)
    else:
        nxt = _dt.datetime(d.year, d.month + 1, 1)
    return nxt - _dt.timedelta(milliseconds=1)


def start_of_year(d: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(d.year, 1, 1)


def end_of_year(d: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(d.year, 12, 31, 23, 59, 59, 999000)


def date_range(start: _dt.datetime, end: _dt.datetime) -> Iterator[_dt.datetime]:
    cur = start_of_day(start)
    stop = start_of_day(end)
    while cur <= stop:
        yield cur
        cur += _dt.timedelta(days=1)


def add_days(d: _dt.datetime, n: int) -> _dt.datetime:
    return d + _dt.timedelta(days=n)


def diff_days(a: _dt.datetime, b: _dt.datetime) -> int:
    a0 = start_of_day(a)
    b0 = start_of_day(b)
    return (a0 - b0).days


# === Jalali conversion (Borkowski algorithm — mirror of date-utils.js) ===

_G_NONLEAP = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
_G_LEAP = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    if gm <= 2:
        gy -= 1
    if gm <= 2:
        days = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400 + gd + _G_NONLEAP[gm - 1]
    else:
        days = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400 + gd + _G_LEAP[gm - 1]
    j_days = days - 79
    j_np = j_days // 12053
    rem = j_days % 12053
    jy = 979 + 33 * j_np + 4 * (rem // 1461)
    rem = rem % 1461
    if rem >= 366:
        jy += (rem - 1) // 365
        rem = (rem - 1) % 365
    if rem < 186:
        jm = 1 + rem // 31
        jd = 1 + (rem % 31)
    else:
        jm = 7 + (rem - 186) // 30
        jd = 1 + ((rem - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    jy -= 979
    j_days = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    j_days += (jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186
    g_days = j_days + 79
    gy = 1600 + 400 * (g_days // 146097)
    g_days = g_days % 146097
    if g_days >= 36525:
        g_days -= 1
        gy += 100 * (g_days // 36524)
        g_days = g_days % 36524
        if g_days >= 365:
            g_days += 1
    gy += 4 * (g_days // 1461)
    g_days = g_days % 1461
    if g_days >= 366:
        gy += (g_days - 1) // 365
        g_days = (g_days - 1) % 365
    sal_a = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if is_leap(gy):
        sal_a[2] = 29
    gm = 0
    while gm < 13 and g_days > sal_a[gm]:
        g_days -= sal_a[gm]
        gm += 1
    return gy, gm, g_days


_EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_WEEKDAY_KEYS = ["weekdayMon", "weekdayTue", "weekdayWed", "weekdayThu",
                 "weekdayFri", "weekdaySat", "weekdaySun"]


def fmt_date(d: _dt.datetime, lang: str) -> str:
    if lang == "fa":
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{to_fa_digits(jd)} {t('jMonth' + str(jm), lang)} {to_fa_digits(jy)}"
    return f"{d.day} {_EN_MONTHS[d.month - 1]} {d.year}"


def fmt_short_date(d: _dt.datetime, lang: str) -> str:
    if lang == "fa":
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{to_fa_digits(jd)}/{to_fa_digits(jm)}/{to_fa_digits(jy)}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def fmt_weekday(d: _dt.datetime, lang: str) -> str:
    # Python weekday(): Mon=0..Sun=6 → matches _WEEKDAY_KEYS directly.
    return t(_WEEKDAY_KEYS[d.weekday()], lang)


def fmt_relative(iso: str, lang: str) -> str:
    d = parse_iso(iso)
    today = _dt.datetime.now()
    a = _dt.datetime(d.year, d.month, d.day)
    b = _dt.datetime(today.year, today.month, today.day)
    diff = (b - a).days
    if diff == 0:
        return t("today_", lang)
    if diff == 1:
        return t("yesterday", lang)
    if diff < 7:
        return f"{to_fa_digits(diff)} {t('days', lang)} {t('ago', lang)}" if lang == "fa" \
            else f"{diff} {t('days', lang)} {t('ago', lang)}"
    if diff < 30:
        w = diff // 7
        sfx = "" if lang == "fa" else "s"
        return f"{to_fa_digits(w)} {t('week', lang)}{sfx} {t('ago', lang)}"
    if diff < 365:
        m = diff // 30
        sfx = "" if lang == "fa" else "s"
        return f"{to_fa_digits(m)} {t('month', lang)}{sfx} {t('ago', lang)}"
    y = diff // 365
    sfx = "" if lang == "fa" else "s"
    return f"{to_fa_digits(y)} {t('year', lang)}{sfx} {t('ago', lang)}"


def fmt_duration(sec: int) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_human(sec: int, lang: str) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    if lang == "fa":
        parts = []
        if h:
            parts.append(f"{to_fa_digits(h)} {t('hour', lang)}")
        if m:
            parts.append(f"{to_fa_digits(m)} {t('minute', lang)}")
        return " ".join(parts) or f"{to_fa_digits(0)} {t('minute', lang)}"
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "0m"
