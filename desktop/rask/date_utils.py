"""date_utils.py — Gregorian + Jalali (Persian) calendar helpers.

1:1 mirror of web/js/date-utils.js with additional helpers for the desktop
edition (timezone-aware operations, ISO week numbers, week-of-year, etc.).

The Jalali conversion uses the Borkowski algorithm, identical to the web
edition so dates match exactly between platforms.
"""
from __future__ import annotations
import datetime as _dt
import time
from typing import Iterator, Optional, Tuple


# =====================================================================
# === ISO DATE HELPERS ===
# =====================================================================
def today_iso() -> str:
    """Return today's date as YYYY-MM-DD."""
    return _dt.date.today().isoformat()


def now_iso() -> str:
    """Return current timestamp as YYYY-MM-DDTHH:MM:SS."""
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def now_iso_full() -> str:
    """Return current timestamp with microseconds as ISO 8601."""
    return _dt.datetime.now().isoformat()


def parse_iso(s: str) -> _dt.datetime:
    """Parse an ISO string to datetime. Handles both date-only and datetime."""
    if not s:
        return _dt.datetime.now()
    try:
        if "T" in s:
            return _dt.datetime.fromisoformat(s)
        return _dt.datetime.fromisoformat(s + "T00:00:00")
    except ValueError:
        try:
            return _dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                return _dt.datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return _dt.datetime.now()


def parse_date(s: str) -> _dt.date:
    """Parse an ISO date string to a date object."""
    if not s:
        return _dt.date.today()
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return _dt.date.today()


def is_leap(year: int) -> bool:
    """Return True if the Gregorian year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def is_jalali_leap(jy: int) -> bool:
    """Return True if the Jalali year is a leap year.
    
    Uses the 33-year cycle approximation. A Jalali year is leap if
    (jy - 474 + 65) % 33 % 4 == 0 (after accounting for the cycle).
    """
    jy = jy - 474
    if jy < 0:
        jy += 33
    cycle = jy % 33
    return cycle in (1, 5, 9, 13, 17, 22, 26, 30)


# =====================================================================
# === BOUNDARIES ===
# =====================================================================
def start_of_day(d) -> _dt.datetime:
    x = _dt.datetime(d.year, d.month, d.day) if hasattr(d, "day") and not isinstance(d, _dt.datetime) else _dt.datetime(d.year, d.month, d.day)
    return x


def end_of_day(d) -> _dt.datetime:
    if hasattr(d, "day"):
        return _dt.datetime(d.year, d.month, d.day, 23, 59, 59, 999999)
    return _dt.datetime(d.year, d.month, d.day, 23, 59, 59, 999999)


def start_of_week(d) -> _dt.datetime:
    """Return Saturday as the start of the week (Persian calendar convention)."""
    x = start_of_day(d)
    # Python's weekday(): Mon=0, Tue=1, ..., Sun=6
    # We want Sat=0, Sun=1, Mon=2, ..., Fri=6
    py_wd = x.weekday()
    # Convert: Sat=5, Sun=6, Mon=0, Tue=1, Wed=2, Thu=3, Fri=4
    # So offset = (py_wd + 2) % 7  (Saturday is offset 0)
    offset = (py_wd + 2) % 7
    return x - _dt.timedelta(days=offset)


def end_of_week(d) -> _dt.datetime:
    s = start_of_week(d)
    return end_of_day(s + _dt.timedelta(days=6))


def start_of_month(d) -> _dt.datetime:
    return _dt.datetime(d.year, d.month, 1)


def end_of_month(d) -> _dt.datetime:
    if d.month == 12:
        next_first = _dt.datetime(d.year + 1, 1, 1)
    else:
        next_first = _dt.datetime(d.year, d.month + 1, 1)
    return next_first - _dt.timedelta(microseconds=1)


def start_of_year(d) -> _dt.datetime:
    return _dt.datetime(d.year, 1, 1)


def end_of_year(d) -> _dt.datetime:
    return _dt.datetime(d.year, 12, 31, 23, 59, 59, 999999)


def start_of_jalali_year(d) -> _dt.datetime:
    """Return start of Jalali year (Farvardin 1) for the given date."""
    jy, _, _ = gregorian_to_jalali(d.year, d.month, d.day)
    gy, gm, gd = jalali_to_gregorian(jy, 1, 1)
    return _dt.datetime(gy, gm, gd)


def end_of_jalali_year(d) -> _dt.datetime:
    """Return end of Jalali year (Esfand 29/30) for the given date."""
    jy, _, _ = gregorian_to_jalali(d.year, d.month, d.day)
    # Esfand has 29 days normally, 30 in leap years
    last_day = 30 if is_jalali_leap(jy) else 29
    gy, gm, gd = jalali_to_gregorian(jy, 12, last_day)
    return _dt.datetime(gy, gm, gd, 23, 59, 59, 999999)


def start_of_jalali_month(d) -> _dt.datetime:
    """Return start of Jalali month for the given date."""
    jy, jm, _ = gregorian_to_jalali(d.year, d.month, d.day)
    gy, gm, gd = jalali_to_gregorian(jy, jm, 1)
    return _dt.datetime(gy, gm, gd)


def end_of_jalali_month(d) -> _dt.datetime:
    """Return end of Jalali month for the given date."""
    jy, jm, _ = gregorian_to_jalali(d.year, d.month, d.day)
    # Months 1-6: 31 days, 7-11: 30 days, 12: 29/30
    if jm <= 6:
        last = 31
    elif jm <= 11:
        last = 30
    else:
        last = 30 if is_jalali_leap(jy) else 29
    gy, gm, gd = jalali_to_gregorian(jy, jm, last)
    return _dt.datetime(gy, gm, gd, 23, 59, 59, 999999)


# =====================================================================
# === DATE ITERATION ===
# =====================================================================
def date_range(start, end) -> Iterator[_dt.datetime]:
    """Yield each day from start to end (inclusive)."""
    cur = start_of_day(start)
    stop = start_of_day(end)
    while cur <= stop:
        yield cur
        cur = cur + _dt.timedelta(days=1)


def date_range_iso(start_iso: str, end_iso: str) -> Iterator[str]:
    """Yield each day as ISO string from start to end (inclusive)."""
    start = parse_date(start_iso)
    end = parse_date(end_iso)
    cur = start
    while cur <= end:
        yield cur.isoformat()
        cur = cur + _dt.timedelta(days=1)


def add_days(d, n: int):
    """Return d + n days."""
    if isinstance(d, _dt.datetime):
        return d + _dt.timedelta(days=n)
    return d + _dt.timedelta(days=n)


def add_months(d, n: int):
    """Return d + n months (clamped to last day of month)."""
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    if isinstance(d, _dt.datetime):
        return _dt.datetime(year, month, day, d.hour, d.minute, d.second, d.microsecond)
    return _dt.date(year, month, day)


def add_years(d, n: int):
    """Return d + n years (clamped to last day of month for Feb 29)."""
    year = d.year + n
    day = d.day
    if d.month == 2 and d.day == 29 and not is_leap(year):
        day = 28
    if isinstance(d, _dt.datetime):
        return _dt.datetime(year, d.month, day, d.hour, d.minute, d.second, d.microsecond)
    return _dt.date(year, d.month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if is_leap(year) else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def diff_days(a, b) -> int:
    """Return number of days between a and b (a - b)."""
    a = a.date() if isinstance(a, _dt.datetime) else a
    b = b.date() if isinstance(b, _dt.datetime) else b
    return (a - b).days


def diff_seconds(a, b) -> int:
    """Return number of seconds between two datetimes (a - b)."""
    return int((a - b).total_seconds())


# =====================================================================
# === JALALI CONVERSION (Borkowski algorithm — 1:1 mirror of date-utils.js) ===
# =====================================================================
def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    """Convert a Gregorian date to Jalali (Persian) date.
    
    Returns (jy, jm, jd) where 1 <= jm <= 12 and 1 <= jd <= 31.
    Uses the standard jdf.scr.ir algorithm (Borkowski variant) which is
    correct for all years 1-3000+.
    """
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    jy = 979 if gy > 1600 else 0
    gy = gy - 1600 if gy > 1600 else gy - 621
    gy2 = (gy + 1) if gm > 2 else gy
    days = (365 * gy
            + (gy2 + 3) // 4
            - (gy2 + 99) // 100
            + (gy2 + 399) // 400
            - 80
            + gd
            + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days = days % 12053
    jy += 4 * (days // 1461)
    days = days % 1461
    # Per jdatetime library: only adjust jy when days > 365 (avoids floor-division
    # bug where (-1)//365 = -1 in Python but parseInt(-1/365) = 0 in JS)
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return (jy, jm, jd)


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    """Convert a Jalali date to Gregorian. Returns (gy, gm, gd).
    
    Uses Python's datetime to compute the day offset from the Persian epoch
    (March 22, 622 AD Gregorian = Jalali year 1, day 1), then adds the offset
    to the epoch date. This is exact and avoids the floor-division edge cases
    that plague the jdf.scr.ir arithmetic algorithm when ported from JS.
    """
    import datetime as _dt_mod
    # Persian epoch: Jalali (1, 1, 1) = Gregorian (622, 3, 21)
    # (Matches jdf.scr.ir's arithmetic-algorithm convention.)
    epoch = _dt_mod.date(622, 3, 21)
    # Days from epoch to (jy, jm, jd)
    days = 0
    # Accumulate years
    for y in range(1, jy):
        days += 366 if is_jalali_leap(y) else 365
    # Accumulate months
    for m in range(1, jm):
        if m <= 6:
            days += 31
        elif m <= 11:
            days += 30
        else:  # Esfand
            days += 30 if is_jalali_leap(jy) else 29
    # Add day (1-indexed → 0-indexed)
    days += jd - 1
    result = epoch + _dt_mod.timedelta(days=days)
    return (result.year, result.month, result.day)


def today_jalali() -> Tuple[int, int, int]:
    """Return today's Jalali date as (jy, jm, jd)."""
    t = _dt.date.today()
    return gregorian_to_jalali(t.year, t.month, t.day)


def jalali_to_iso(jy: int, jm: int, jd: int) -> str:
    """Convert Jalali (jy, jm, jd) to ISO Gregorian YYYY-MM-DD."""
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def iso_to_jalali(iso: str) -> Tuple[int, int, int]:
    """Convert ISO Gregorian YYYY-MM-DD to Jalali (jy, jm, jd)."""
    d = parse_date(iso)
    return gregorian_to_jalali(d.year, d.month, d.day)


# =====================================================================
# === FORMATTING ===
# =====================================================================
_GREGORIAN_MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_GREGORIAN_MONTHS_FULL_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _jmonth_name(jm: int, lang: str) -> str:
    """Get the Jalali month name for the given month (1-12)."""
    if lang == "fa":
        from .i18n import t
        return t(f"jMonth{jm}", "fa")
    # English transliterations
    names = [
        "Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
        "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand",
    ]
    return names[jm - 1] if 1 <= jm <= 12 else ""


def fmt_date(d, lang: str = "fa") -> str:
    """Format a date: 'DD MonthName YYYY' (e.g., '۱۸ جولای ۲۰۲۶' or '۱۸ تیر ۱۴۰۵')."""
    if lang == "fa":
        from .i18n import to_fa_digits
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{to_fa_digits(jd)} {_jmonth_name(jm, 'fa')} {to_fa_digits(jy)}"
    return f"{d.day} {_GREGORIAN_MONTHS_EN[d.month - 1]} {d.year}"


def fmt_short_date(d, lang: str = "fa") -> str:
    """Format a date as DD/MM/YYYY (Persian digits if fa)."""
    if lang == "fa":
        from .i18n import to_fa_digits
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{to_fa_digits(jd)}/{to_fa_digits(jm)}/{to_fa_digits(jy)}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def fmt_long_date(d, lang: str = "fa") -> str:
    """Format a date with weekday: 'Monday, 18 July 2026'."""
    wd = fmt_weekday(d, lang)
    if lang == "fa":
        from .i18n import to_fa_digits
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        return f"{wd}، {to_fa_digits(jd)} {_jmonth_name(jm, 'fa')} {to_fa_digits(jy)}"
    return f"{wd}, {d.day} {_GREGORIAN_MONTHS_FULL_EN[d.month - 1]} {d.year}"


def fmt_weekday(d, lang: str = "fa") -> str:
    """Format the weekday name. Python weekday(): Mon=0, Sun=6."""
    from .i18n import t
    py_wd = d.weekday() if hasattr(d, "weekday") else _dt.date(d.year, d.month, d.day).weekday()
    keys = ["weekdayMon", "weekdayTue", "weekdayWed", "weekdayThu",
            "weekdayFri", "weekdaySat", "weekdaySun"]
    return t(keys[py_wd], lang)


def fmt_weekday_short(d, lang: str = "fa") -> str:
    """Format the short weekday name."""
    from .i18n import t
    py_wd = d.weekday() if hasattr(d, "weekday") else _dt.date(d.year, d.month, d.day).weekday()
    keys = ["weekdayMonShort", "weekdayTueShort", "weekdayWedShort", "weekdayThuShort",
            "weekdayFriShort", "weekdaySatShort", "weekdaySunShort"]
    return t(keys[py_wd], lang)


def fmt_relative(iso: str, lang: str = "fa") -> str:
    """Format a date relative to today ('today', 'yesterday', '5 days ago', etc.)."""
    from .i18n import t, to_fa_digits
    if not iso:
        return ""
    try:
        d = parse_date(iso)
    except Exception:
        return ""
    today = _dt.date.today()
    diff = (today - d).days
    if diff == 0:
        return t("today_", lang)
    if diff == 1:
        return t("yesterday", lang)
    if diff == -1:
        return t("tomorrow", lang)
    if diff > 0:
        if diff < 7:
            n = to_fa_digits(diff) if lang == "fa" else diff
            return f"{n} {t('days', lang)} {t('ago', lang)}"
        if diff < 30:
            w = diff // 7
            n = to_fa_digits(w) if lang == "fa" else w
            plural = "" if lang == "fa" or w == 1 else "s"
            return f"{n} {t('week', lang)}{plural} {t('ago', lang)}"
        if diff < 365:
            m = diff // 30
            n = to_fa_digits(m) if lang == "fa" else m
            plural = "" if lang == "fa" or m == 1 else "s"
            return f"{n} {t('month', lang)}{plural} {t('ago', lang)}"
        y = diff // 365
        n = to_fa_digits(y) if lang == "fa" else y
        plural = "" if lang == "fa" or y == 1 else "s"
        return f"{n} {t('year', lang)}{plural} {t('ago', lang)}"
    # Future
    diff = -diff
    if diff < 7:
        n = to_fa_digits(diff) if lang == "fa" else diff
        return f"{t('in', lang)} {n} {t('days', lang)}"
    if diff < 30:
        w = diff // 7
        n = to_fa_digits(w) if lang == "fa" else w
        return f"{t('in', lang)} {n} {t('week', lang)}"
    if diff < 365:
        m = diff // 30
        n = to_fa_digits(m) if lang == "fa" else m
        return f"{t('in', lang)} {n} {t('month', lang)}"
    y = diff // 365
    n = to_fa_digits(y) if lang == "fa" else y
    return f"{t('in', lang)} {n} {t('year', lang)}"


def fmt_duration(sec: int) -> str:
    """Format seconds as HH:MM:SS (or MM:SS if under 1 hour)."""
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_duration_persian(sec: int, lang: str = "fa") -> str:
    """Format seconds with Persian digits."""
    from .i18n import to_fa_digits
    return to_fa_digits(fmt_duration(sec))


def fmt_human(sec: int, lang: str = "fa") -> str:
    """Format seconds in a human-readable form: '2h 30m' or '۲ ساعت ۳۰ دقیقه'."""
    from .i18n import t, to_fa_digits
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if lang == "fa":
        parts = []
        if h:
            parts.append(f"{to_fa_digits(h)} {t('hour', lang)}")
        if m:
            parts.append(f"{to_fa_digits(m)} {t('minute', lang)}")
        if not parts and s:
            parts.append(f"{to_fa_digits(s)} {t('second', lang)}")
        return " ".join(parts) or f"{to_fa_digits(0)} {t('minute', lang)}"
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not parts and s:
        parts.append(f"{s}s")
    return " ".join(parts) or "0m"


def fmt_human_short(sec: int, lang: str = "fa") -> str:
    """Short human format: '2h 30m' (always short, even in Persian)."""
    from .i18n import to_fa_digits
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not parts and s:
        parts.append(f"{s}s")
    out = " ".join(parts) or "0m"
    return to_fa_digits(out) if lang == "fa" else out


def fmt_minutes(min_total: int, lang: str = "fa") -> str:
    """Format a duration given in minutes (e.g., 90 → '1h 30m' or '۱ ساعت ۳۰ دقیقه')."""
    return fmt_human(min_total * 60, lang)


def fmt_seconds_persian(sec: int, lang: str = "fa") -> str:
    """Format seconds always showing HH:MM:SS."""
    from .i18n import to_fa_digits
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    out = f"{h:02d}:{m:02d}:{s:02d}"
    return to_fa_digits(out) if lang == "fa" else out


# =====================================================================
# === TIME HELPERS ===
# =====================================================================
def now_hour() -> int:
    """Return the current hour (0-23)."""
    return _dt.datetime.now().hour


def now_minute() -> int:
    """Return the current minute (0-59)."""
    return _dt.datetime.now().minute


def now_second() -> int:
    """Return the current second (0-59)."""
    return _dt.datetime.now().second


def current_timestamp() -> float:
    """Return current Unix timestamp."""
    return time.time()


def current_millis() -> int:
    """Return current Unix timestamp in milliseconds."""
    return int(time.time() * 1000)


def from_timestamp(ts: float) -> _dt.datetime:
    """Convert a Unix timestamp to datetime."""
    return _dt.datetime.fromtimestamp(ts)


# =====================================================================
# === WEEK / MONTH HELPERS ===
# =====================================================================
def week_of_year(d) -> int:
    """Return ISO week number (1-53)."""
    return d.isocalendar()[1]


def day_of_year(d) -> int:
    """Return day of year (1-366)."""
    return d.timetuple().tm_yday


def quarter_of_year(d) -> int:
    """Return quarter (1-4)."""
    return (d.month - 1) // 3 + 1


def days_in_month(year: int, month: int) -> int:
    """Return number of days in the given Gregorian month."""
    return _days_in_month(year, month)


def days_in_jalali_month(jy: int, jm: int) -> int:
    """Return number of days in the given Jalali month."""
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_jalali_leap(jy) else 29


def jalali_year_length(jy: int) -> int:
    """Return total days in a Jalali year (365 or 366)."""
    return 366 if is_jalali_leap(jy) else 365


# =====================================================================
# === STATS PRESET DATE RANGES (mirror web/js/app.js PRESETS) ===
# =====================================================================
def preset_range(preset: str, ref=None) -> Tuple[str, str]:
    """Return (start_iso, end_iso) for a named preset.
    
    Presets: 'today', '7d', '30d', 'month', 'year', 'yesterday',
             'this_week', 'last_week', 'last_month', 'last_year',
             '90d', '365d', 'all'.
    """
    if ref is None:
        ref = _dt.date.today()
    if preset == "today":
        return (ref.isoformat(), ref.isoformat())
    if preset == "yesterday":
        y = ref - _dt.timedelta(days=1)
        return (y.isoformat(), y.isoformat())
    if preset == "7d":
        return ((ref - _dt.timedelta(days=6)).isoformat(), ref.isoformat())
    if preset == "30d":
        return ((ref - _dt.timedelta(days=29)).isoformat(), ref.isoformat())
    if preset == "90d":
        return ((ref - _dt.timedelta(days=89)).isoformat(), ref.isoformat())
    if preset == "365d":
        return ((ref - _dt.timedelta(days=364)).isoformat(), ref.isoformat())
    if preset == "month":
        s = start_of_month(ref)
        e = end_of_month(ref)
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "year":
        s = start_of_year(ref)
        e = end_of_year(ref)
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "this_week":
        s = start_of_week(ref)
        e = end_of_week(ref)
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "last_week":
        s = start_of_week(ref - _dt.timedelta(days=7))
        e = end_of_week(ref - _dt.timedelta(days=7))
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "last_month":
        s = start_of_month(ref - _dt.timedelta(days=30))
        e = end_of_month(ref - _dt.timedelta(days=30))
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "last_year":
        s = start_of_year(_dt.date(ref.year - 1, 1, 1))
        e = end_of_year(_dt.date(ref.year - 1, 1, 1))
        return (s.date().isoformat(), e.date().isoformat())
    if preset == "all":
        return ("2000-01-01", "2099-12-31")
    return (ref.isoformat(), ref.isoformat())


def preset_label(preset: str, lang: str = "fa") -> str:
    """Return a localized label for a preset key."""
    from .i18n import t
    mapping = {
        "today":      "todayPreset",
        "yesterday":  "yesterday",
        "7d":         "sevenDays",
        "30d":        "thirtyDays",
        "90d":        "thirtyDays",  # reuse
        "365d":       "thisYear",
        "month":      "thisMonth",
        "year":       "thisYear",
        "this_week":  "thisWeek",
        "last_week":  "thisWeek",
        "last_month": "thisMonth",
        "last_year":  "thisYear",
        "all":        "allTime",
    }
    return t(mapping.get(preset, "todayPreset"), lang)


# =====================================================================
# === AGE FORMATTING ===
# =====================================================================
def fmt_age(seconds: int, lang: str = "fa") -> str:
    """Format an age in seconds to a human-readable string (days/weeks/months/years)."""
    from .i18n import t, to_fa_digits
    if seconds < 60:
        n = to_fa_digits(seconds) if lang == "fa" else seconds
        return f"{n} {t('seconds', lang)}"
    if seconds < 3600:
        m = seconds // 60
        n = to_fa_digits(m) if lang == "fa" else m
        return f"{n} {t('minutes', lang)}"
    if seconds < 86400:
        h = seconds // 3600
        n = to_fa_digits(h) if lang == "fa" else h
        return f"{n} {t('hours', lang)}"
    days = seconds // 86400
    if days < 7:
        n = to_fa_digits(days) if lang == "fa" else days
        return f"{n} {t('days', lang)}"
    if days < 30:
        w = days // 7
        n = to_fa_digits(w) if lang == "fa" else w
        return f"{n} {t('week', lang)}"
    if days < 365:
        m = days // 30
        n = to_fa_digits(m) if lang == "fa" else m
        return f"{n} {t('month', lang)}"
    y = days // 365
    n = to_fa_digits(y) if lang == "fa" else y
    return f"{n} {t('year', lang)}"


# =====================================================================
# === TIME COMPARISON ===
# =====================================================================
def is_today(iso: str) -> bool:
    """Return True if the ISO date is today."""
    return iso == today_iso()


def is_yesterday(iso: str) -> bool:
    """Return True if the ISO date is yesterday."""
    y = _dt.date.today() - _dt.timedelta(days=1)
    return iso == y.isoformat()


def is_this_week(iso: str) -> bool:
    """Return True if the ISO date is in the current week (Sat–Fri)."""
    today = _dt.date.today()
    s = start_of_week(today).date()
    e = end_of_week(today).date()
    d = parse_date(iso)
    return s <= d <= e


def is_this_month(iso: str) -> bool:
    """Return True if the ISO date is in the current month."""
    today = _dt.date.today()
    d = parse_date(iso)
    return today.year == d.year and today.month == d.month


def is_this_year(iso: str) -> bool:
    """Return True if the ISO date is in the current year."""
    today = _dt.date.today()
    d = parse_date(iso)
    return today.year == d.year


def is_weekend(d) -> bool:
    """Return True if the date is a weekend day (Thursday or Friday in Persian calendar)."""
    py_wd = d.weekday() if hasattr(d, "weekday") else _dt.date(d.year, d.month, d.day).weekday()
    # Python: Mon=0, Sun=6 — Persian weekend is Thursday (3) and Friday (4)
    return py_wd in (3, 4)


def is_weekday(d) -> bool:
    """Return True if the date is a weekday (not weekend)."""
    return not is_weekend(d)


# =====================================================================
# === ISO WEEK NUMBER ===
# =====================================================================
def iso_year(d) -> int:
    """Return the ISO year (may differ from calendar year for Jan 1 or Dec 31)."""
    return d.isocalendar()[0]


def iso_week(d) -> int:
    """Return the ISO week number (1-53)."""
    return d.isocalendar()[1]


def iso_weekday(d) -> int:
    """Return the ISO weekday (1=Monday, 7=Sunday)."""
    return d.isoweekday()


# =====================================================================
# === TIMEZONE ===
# =====================================================================
def local_tz_offset() -> int:
    """Return local timezone offset from UTC in seconds."""
    return -time.timezone if time.daylight == 0 else -time.altzone


def local_tz_name() -> str:
    """Return local timezone name."""
    return time.tzname[0]


def utc_now() -> _dt.datetime:
    """Return current UTC datetime."""
    return _dt.datetime.utcnow()


def to_utc(d: _dt.datetime) -> _dt.datetime:
    """Convert a naive local datetime to UTC."""
    offset = local_tz_offset()
    return d - _dt.timedelta(seconds=offset)


def from_utc(d: _dt.datetime) -> _dt.datetime:
    """Convert a naive UTC datetime to local time."""
    offset = local_tz_offset()
    return d + _dt.timedelta(seconds=offset)


# =====================================================================
# === HOLIDAYS / SPECIAL DATES (Persian) ===
# =====================================================================
PERSIAN_HOLIDAYS = {
    # (jy, jm, jd) tuples would be year-specific; here we list fixed-month/day
    # holidays that recur every year.
    (1, 1):  "نوروز (جشن نوروز)",
    (1, 2):  "نوروز",
    (1, 3):  "نوروز",
    (1, 4):  "نوروز",
    (1, 12): "روز جمهوری اسلامی",
    (1, 13): "سیزده‌بدر",
    (3, 14): "رحلت امام خمینی",
    (3, 15): "قیام ۱۵ خرداد",
    (11, 22): "پیروزی انقلاب اسلامی",
    (12, 29): "روز ملی شدن صنعت نفت",
}


def persian_holiday(d) -> Optional[str]:
    """Return the Persian holiday name for the given date, or None."""
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return PERSIAN_HOLIDAYS.get((jm, jd))


# =====================================================================
# === FILENAME-SAFE DATE ===
# =====================================================================
def fmt_filename_date(d=None) -> str:
    """Return a filename-safe date string: YYYY-MM-DD."""
    if d is None:
        d = _dt.date.today()
    return d.isoformat() if isinstance(d, _dt.date) else d.date().isoformat()


def fmt_filename_timestamp(d=None) -> str:
    """Return a filename-safe timestamp: YYYY-MM-DD_HHMMSS."""
    if d is None:
        d = _dt.datetime.now()
    return d.strftime("%Y-%m-%d_%H%M%S")
