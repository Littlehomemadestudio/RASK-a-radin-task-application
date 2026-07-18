"""
rask.core.time_utils
====================

ISO-8601 datetime helpers, duration / relative-time formatting, and
Gregorian calendar range utilities for the Rask desktop app.

All functions accept ISO strings (``YYYY-MM-DD`` or
``YYYY-MM-DDTHH:MM:SS``) for date inputs and return plain Python
types.  Display strings are localized via :mod:`rask.i18n` and Persian
digits are inserted automatically when ``lang="fa"``.

Mirrors the behavior of ``web/js/date-utils.js`` (the public function
names are translated to snake_case) and the time-formatting helpers
sprinkled through ``web/js/timer.js`` and ``web/js/app.js``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

from .. import i18n

__all__ = [
    "now_iso_utc",
    "now_iso_local",
    "today_iso",
    "parse_iso",
    "format_duration",
    "format_timer",
    "format_relative",
    "parse_duration",
    "minutes_to_hhmm",
    "hhmm_to_minutes",
    "seconds_to_human",
    "is_today",
    "is_this_week",
    "is_this_month",
    "days_between",
    "add_days",
    "start_of_week",
    "end_of_week",
    "start_of_month",
    "end_of_month",
    "start_of_year",
    "end_of_year",
    "range_days",
    "range_months",
    "weekday_name",
    "month_name",
    "greeting",
]


# =============================================================================
# === "Now" / today helpers                                                 ===
# =============================================================================

def now_iso_utc() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SS`` (no timezone suffix).

    Example
    -------
    >>> len(now_iso_utc())
    19
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def now_iso_local() -> str:
    """Return the current local time as ``YYYY-MM-DDTHH:MM:SS``.

    Example
    -------
    >>> len(now_iso_local())
    19
    """
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today_iso() -> str:
    """Return today's local date as ``YYYY-MM-DD``.

    Example
    -------
    >>> len(today_iso())
    10
    """
    return date.today().isoformat()


def parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string into a :class:`datetime`.

    Accepts both ``YYYY-MM-DD`` (returns midnight) and
    ``YYYY-MM-DDTHH:MM:SS`` (with optional fractional seconds or
    timezone suffix).  Mirrors ``DateUtils.parseISO`` in the web PWA.

    Raises ``ValueError`` for unparseable input.
    """
    if not s or not isinstance(s, str):
        raise ValueError(f"parse_iso requires a non-empty string, got {s!r}")
    s = s.strip()
    # Python's fromisoformat is strict; handle a few common variants.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Fall back to date-only.
        try:
            return datetime.combine(date.fromisoformat(s[:10]), time())
        except ValueError as exc:
            raise ValueError(f"Cannot parse ISO datetime: {s!r}") from exc


# =============================================================================
# === Duration formatting                                                   ===
# =============================================================================

def format_duration(minutes: int, lang: str = "fa", short: bool = False) -> str:
    """Format a duration in minutes as a localized human-readable string.

    Parameters
    ----------
    minutes : int
        Duration in minutes (clamped to ≥ 0).
    lang : str
        ``"fa"`` (default) for Persian, ``"en"`` for English.
    short : bool
        If ``True``, use the short form ``"2h 30m"`` / ``"۲ ساعت ۳۰ دقیقه"``.
        Otherwise use the verbose form ``"2 hours 30 minutes"`` /
        ``"۲ ساعت ۳۰ دقیقه"``.

    Examples
    --------
    >>> format_duration(150, "en", short=True)
    '2h 30m'
    >>> format_duration(150, "fa", short=True)
    '۲ ساعت ۳۰ دقیقه'
    >>> format_duration(0, "fa", short=True)
    '۰ دقیقه'
    """
    if not isinstance(minutes, (int, float)):
        minutes = 0
    minutes = max(0, int(minutes))
    hours = minutes // 60
    mins = minutes % 60

    if lang == "fa":
        hour_word = i18n.t("hour", "fa")
        min_word = i18n.t("minute", "fa")
        if short:
            parts = []
            if hours:
                parts.append(f"{i18n.to_fa_digits(hours)} {hour_word}")
            if mins or not hours:
                parts.append(f"{i18n.to_fa_digits(mins)} {min_word}")
            return " ".join(parts)
        # Verbose: same as short in Persian.
        parts = []
        if hours:
            parts.append(f"{i18n.to_fa_digits(hours)} {hour_word}")
        if mins or not hours:
            parts.append(f"{i18n.to_fa_digits(mins)} {min_word}")
        return " ".join(parts)

    # English.
    if short:
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if mins or not hours:
            parts.append(f"{mins}m")
        return " ".join(parts)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins or not hours:
        parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    return " ".join(parts)


def format_timer(seconds: int, lang: str = "fa") -> str:
    """Format a stopwatch elapsed time as ``HH:MM:SS`` (or ``MM:SS`` if < 1h).

    Mirrors ``DateUtils.fmtDuration`` in the web PWA.

    Parameters
    ----------
    seconds : int
        Elapsed seconds (clamped to ≥ 0).
    lang : str
        ``"fa"`` (default) converts digits to Persian, ``"en"`` keeps
        Western digits.

    Examples
    --------
    >>> format_timer(65, "en")
    '01:05'
    >>> format_timer(3661, "en")
    '01:01:01'
    >>> format_timer(65, "fa")
    '۰۱:۰۵'
    """
    if not isinstance(seconds, (int, float)):
        seconds = 0
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        out = f"{h:02d}:{m:02d}:{s:02d}"
    else:
        out = f"{m:02d}:{s:02d}"
    return i18n.to_fa_digits(out) if lang == "fa" else out


def format_relative(iso: str, lang: str = "fa") -> str:
    """Format an ISO date as a relative time string (e.g. "۵ روز پیش").

    Mirrors ``DateUtils.fmtRelative`` in the web PWA.  Uses calendar-day
    differences (not 24-hour rolling windows) so "yesterday" stays
    correct near midnight.

    Examples
    --------
    >>> # Assuming today is 2025-03-25:
    >>> format_relative('2025-03-25', 'fa')
    'امروز'
    >>> format_relative('2025-03-24', 'fa')
    'دیروز'
    >>> format_relative('2025-03-20', 'fa')
    '۵ روز پیش'
    """
    if not iso:
        return ""
    try:
        d = parse_iso(iso).date()
    except ValueError:
        return ""
    today = date.today()
    diff = (today - d).days

    if diff == 0:
        return i18n.t("today_", lang)
    if diff == 1:
        return i18n.t("yesterday", lang)
    if diff < 0:
        # Future date — return absolute short form.
        return _format_short_date(d, lang)
    if diff < 7:
        if lang == "fa":
            return f"{i18n.to_fa_digits(diff)} {i18n.t('days', lang)} {i18n.t('ago', lang)}"
        return f"{diff} {i18n.t('days', lang)} {i18n.t('ago', lang)}"
    if diff < 30:
        w = diff // 7
        if lang == "fa":
            return f"{i18n.to_fa_digits(w)} {i18n.t('week', lang)} {i18n.t('ago', lang)}"
        return f"{w} {i18n.t('week', lang)}{'s' if w != 1 else ''} {i18n.t('ago', lang)}"
    if diff < 365:
        m = diff // 30
        if lang == "fa":
            return f"{i18n.to_fa_digits(m)} {i18n.t('month', lang)} {i18n.t('ago', lang)}"
        return f"{m} {i18n.t('month', lang)}{'s' if m != 1 else ''} {i18n.t('ago', lang)}"
    y = diff // 365
    if lang == "fa":
        return f"{i18n.to_fa_digits(y)} {i18n.t('year', lang)} {i18n.t('ago', lang)}"
    return f"{y} {i18n.t('year', lang)}{'s' if y != 1 else ''} {i18n.t('ago', lang)}"


def _format_short_date(d: date, lang: str) -> str:
    """Internal: format a Gregorian date as DD/MM/YYYY."""
    if lang == "fa":
        return i18n.to_fa_digits(f"{d.day}/{d.month}/{d.year}")
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


# =============================================================================
# === Duration parsing                                                      ===
# =============================================================================

def parse_duration(s: str) -> int:
    """Parse a human-entered duration string into minutes.

    Accepts these formats:
      - ``"1h30m"``     -> 90
      - ``"1h"``        -> 60
      - ``"90m"``       -> 90
      - ``"90"``        -> 90  (bare minutes)
      - ``"1:30"``      -> 90  (MM:SS or H:MM — see note below)
      - ``"1:30:00"``   -> 90  (H:MM:SS)
      - ``"1:30:45"``   -> 91  (seconds round up to a minute)
      - Persian digits are accepted.

    Returns 0 for empty / unparseable input.  Never raises.

    Examples
    --------
    >>> parse_duration("1h30m")
    90
    >>> parse_duration("90")
    90
    >>> parse_duration("1:30:00")
    90
    >>> parse_duration("")
    0
    """
    if not s or not isinstance(s, str):
        return 0
    s = i18n.to_en_digits(s).strip().lower()
    if not s:
        return 0

    # Pure number = minutes.
    if s.isdigit():
        return max(0, int(s))

    # H:MM or H:MM:SS form.
    if ":" in s and "h" not in s and "m" not in s:
        parts = s.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return 0
        if len(nums) == 2:
            return max(0, nums[0] * 60 + nums[1])
        if len(nums) == 3:
            return max(0, nums[0] * 60 + nums[1] + (1 if nums[2] >= 30 else 0))
        return 0

    # Hh Mm form (e.g. "1h30m", "2h", "45m").
    total = 0
    import re
    m = re.match(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*$", s)
    if m and (m.group(1) or m.group(2)):
        h = int(m.group(1)) if m.group(1) else 0
        mn = int(m.group(2)) if m.group(2) else 0
        return max(0, h * 60 + mn)

    return 0


def minutes_to_hhmm(mins: int, lang: str = "fa") -> str:
    """Format a minute count as ``HH:MM`` (e.g. ``"02:30"``).

    Negative inputs are clamped to 0.  Hour overflow beyond 99 is allowed.

    Examples
    --------
    >>> minutes_to_hhmm(150, "en")
    '02:30'
    >>> minutes_to_hhmm(150, "fa")
    '۰۲:۳۰'
    """
    if not isinstance(mins, (int, float)):
        mins = 0
    mins = max(0, int(mins))
    out = f"{mins // 60:02d}:{mins % 60:02d}"
    return i18n.to_fa_digits(out) if lang == "fa" else out


def hhmm_to_minutes(s: str) -> int:
    """Parse an ``HH:MM`` string into minutes.

    Returns 0 for empty / unparseable input.

    Examples
    --------
    >>> hhmm_to_minutes("02:30")
    150
    >>> hhmm_to_minutes("0:45")
    45
    >>> hhmm_to_minutes("")
    0
    """
    if not s or not isinstance(s, str):
        return 0
    s = i18n.to_en_digits(s).strip()
    if ":" not in s:
        try:
            return max(0, int(s))
        except ValueError:
            return 0
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0
    if len(nums) == 2:
        return max(0, nums[0] * 60 + nums[1])
    if len(nums) == 3:
        return max(0, nums[0] * 60 + nums[1])
    return 0


def seconds_to_human(sec: int, lang: str = "fa") -> str:
    """Format a number of seconds as a short human string (``"2h 30m"``).

    Mirrors ``DateUtils.fmtHuman`` in the web PWA.

    Examples
    --------
    >>> seconds_to_human(3661, "en")
    '1h 1m'
    >>> seconds_to_human(3661, "fa")
    '۱ ساعت ۱ دقیقه'
    >>> seconds_to_human(0, "fa")
    '۰ دقیقه'
    """
    if not isinstance(sec, (int, float)):
        sec = 0
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    if lang == "fa":
        parts = []
        if h:
            parts.append(f"{i18n.to_fa_digits(h)} {i18n.t('hour', 'fa')}")
        if m or not h:
            parts.append(f"{i18n.to_fa_digits(m)} {i18n.t('minute', 'fa')}")
        return " ".join(parts) or f"{i18n.to_fa_digits(0)} {i18n.t('minute', 'fa')}"
    parts = []
    if h:
        parts.append(f"{h}h")
    if m or not h:
        parts.append(f"{m}m")
    return " ".join(parts) or "0m"


# =============================================================================
# === Today / this-week / this-month predicates                             ===
# =============================================================================

def is_today(iso: str) -> bool:
    """Return True if `iso` (a date or datetime string) is today."""
    try:
        return parse_iso(iso).date() == date.today()
    except ValueError:
        return False


def is_this_week(iso: str, first_day: int = 6) -> bool:
    """Return True if `iso` falls within the current week.

    `first_day` follows the JS ``getDay()`` convention (Sun=0..Sat=6);
    default ``6`` means Saturday (Persian week start).
    """
    try:
        d = parse_iso(iso).date()
    except ValueError:
        return False
    return start_of_week(today_iso(), first_day) <= d.isoformat() <= end_of_week(today_iso(), first_day)


def is_this_month(iso: str) -> bool:
    """Return True if `iso` falls within the current calendar month."""
    try:
        d = parse_iso(iso).date()
    except ValueError:
        return False
    today = date.today()
    return d.year == today.year and d.month == today.month


# =============================================================================
# === Date arithmetic                                                        ===
# =============================================================================

def days_between(iso1: str, iso2: str) -> int:
    """Return the number of calendar days from `iso1` to `iso2`.

    Positive if `iso2` is later than `iso1`.  Both inputs may be
    date or datetime strings (time portion is ignored).

    Examples
    --------
    >>> days_between('2025-01-01', '2025-01-08')
    7
    >>> days_between('2025-01-08', '2025-01-01')
    -7
    """
    d1 = parse_iso(iso1).date()
    d2 = parse_iso(iso2).date()
    return (d2 - d1).days


def add_days(iso: str, n: int) -> str:
    """Add `n` days to an ISO date, returning the new ISO date.

    Example
    -------
    >>> add_days('2025-01-01', 7)
    '2025-01-08'
    """
    d = parse_iso(iso).date()
    return (d + timedelta(days=n)).isoformat()


def start_of_week(iso: str, first_day: int = 6) -> str:
    """Return the ISO date for the start of the week containing `iso`.

    `first_day` follows the JS ``getDay()`` convention (Sun=0..Sat=6);
    default ``6`` means Saturday (Persian week start).

    Example
    -------
    >>> start_of_week('2025-03-25')  # Tuesday -> Saturday start
    '2025-03-22'
    """
    d = parse_iso(iso).date()
    js_day = (d.weekday() + 1) % 7  # Sun=0..Sat=6
    delta = (js_day - first_day) % 7
    return (d - timedelta(days=delta)).isoformat()


def end_of_week(iso: str, first_day: int = 6) -> str:
    """Return the ISO date for the end of the week containing `iso`.

    The end of week is 6 days after the start (so a Sat-first week
    ends on Friday).

    Example
    -------
    >>> end_of_week('2025-03-25')  # Tuesday week -> Friday end
    '2025-03-28'
    """
    start = start_of_week(iso, first_day)
    return add_days(start, 6)


def start_of_month(iso: str) -> str:
    """Return the first day of the Gregorian month containing `iso`."""
    d = parse_iso(iso).date()
    return d.replace(day=1).isoformat()


def end_of_month(iso: str) -> str:
    """Return the last day of the Gregorian month containing `iso`."""
    d = parse_iso(iso).date()
    # Trick: first day of next month minus 1.
    if d.month == 12:
        next_first = d.replace(year=d.year + 1, month=1, day=1)
    else:
        next_first = d.replace(month=d.month + 1, day=1)
    return (next_first - timedelta(days=1)).isoformat()


def start_of_year(iso: str) -> str:
    """Return January 1st of the year containing `iso`."""
    d = parse_iso(iso).date()
    return d.replace(month=1, day=1).isoformat()


def end_of_year(iso: str) -> str:
    """Return December 31st of the year containing `iso`."""
    d = parse_iso(iso).date()
    return d.replace(month=12, day=31).isoformat()


# =============================================================================
# === Ranges                                                                ===
# =============================================================================

def range_days(start_iso: str, end_iso: str) -> List[str]:
    """Return a list of ISO date strings from `start_iso` to `end_iso` inclusive.

    Order is preserved regardless of which date is earlier — the
    returned list always goes from earlier to later.

    Example
    -------
    >>> range_days('2025-01-01', '2025-01-03')
    ['2025-01-01', '2025-01-02', '2025-01-03']
    """
    d1 = parse_iso(start_iso).date()
    d2 = parse_iso(end_iso).date()
    if d1 > d2:
        d1, d2 = d2, d1
    out: List[str] = []
    cur = d1
    while cur <= d2:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def range_months(start_iso: str, end_iso: str) -> List[str]:
    """Return a list of YYYY-MM-01 strings for each month in the range.

    Example
    -------
    >>> range_months('2025-01-15', '2025-03-20')
    ['2025-01-01', '2025-02-01', '2025-03-01']
    """
    d1 = parse_iso(start_iso).date().replace(day=1)
    d2 = parse_iso(end_iso).date().replace(day=1)
    if d1 > d2:
        d1, d2 = d2, d1
    out: List[str] = []
    cur = d1
    while cur <= d2:
        out.append(cur.isoformat())
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return out


# =============================================================================
# === Localized names                                                       ===
# =============================================================================

# Gregorian month names — Persian translation via i18n; English is the
# standard English short form.  These are *Gregorian* names; for the
# Jalali month names use :func:`rask.core.jalali.jalali_month_name`.
_GREG_MONTHS_FA: Tuple[str, ...] = (
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
)
_GREG_MONTHS_EN: Tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
# Persian weekday names: index 0..6 = Saturday..Friday (Jalali convention).
_WEEKDAYS_FA: Tuple[str, ...] = (
    "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه",
)
_WEEKDAYS_EN: Tuple[str, ...] = (
    "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
)


def weekday_name(iso: str, lang: str = "fa") -> str:
    """Return the localized weekday name for an ISO date.

    Uses Saturday-first Persian weekday convention regardless of
    language, to match the rest of Rask.

    Examples
    --------
    >>> weekday_name('2025-03-21', 'fa')  # Friday
    'جمعه'
    >>> weekday_name('2025-03-22', 'en')  # Saturday
    'Saturday'
    """
    d = parse_iso(iso).date()
    # Persian convention: Saturday = 0, Sunday = 1, ..., Friday = 6.
    py_wd = d.weekday()  # Mon=0..Sun=6
    sat_first = (py_wd + 2) % 7
    if lang == "fa":
        return _WEEKDAYS_FA[sat_first]
    return _WEEKDAYS_EN[sat_first]


def month_name(iso: str, lang: str = "fa") -> str:
    """Return the localized *Gregorian* month name for an ISO date.

    For the Jalali month name, use :func:`rask.core.jalali.jalali_month_name`.

    Examples
    --------
    >>> month_name('2025-03-21', 'en')
    'March'
    >>> month_name('2025-03-21', 'fa')
    'مارس'
    """
    d = parse_iso(iso).date()
    if lang == "fa":
        return _GREG_MONTHS_FA[d.month - 1]
    return _GREG_MONTHS_EN[d.month - 1]


def greeting(lang: str = "fa") -> str:
    """Return a time-of-day greeting based on the current local hour.

    - 5:00-11:59 -> goodMorning
    - 12:00-16:59 -> goodAfternoon
    - 17:00-4:59 -> goodEvening

    Example
    -------
    >>> # at 9 AM:
    >>> # greeting('fa') == 'صبح بخیر'
    """
    hour = datetime.now().hour
    if 5 <= hour < 12:
        key = "goodMorning"
    elif 12 <= hour < 17:
        key = "goodAfternoon"
    else:
        key = "goodEvening"
    return i18n.t(key, lang)


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.time_utils"""
    tests_passed = 0
    tests_failed = 0

    def check(label: str, got, expected) -> None:
        nonlocal tests_passed, tests_failed
        if got == expected:
            tests_passed += 1
            print(f"  OK   {label}")
        else:
            tests_failed += 1
            print(f"  FAIL {label}: got {got!r}, expected {expected!r}")

    print("=== Duration formatting ===")
    check("format_duration 150 en short", format_duration(150, "en", True), "2h 30m")
    check("format_duration 150 fa short", format_duration(150, "fa", True), "۲ ساعت ۳۰ دقیقه")
    check("format_duration 60 en short", format_duration(60, "en", True), "1h")
    check("format_duration 0 fa short", format_duration(0, "fa", True), "۰ دقیقه")
    check("format_duration negative", format_duration(-5, "en", True), "0m")

    print("\n=== Timer formatting ===")
    check("format_timer 65 en", format_timer(65, "en"), "01:05")
    check("format_timer 3661 en", format_timer(3661, "en"), "01:01:01")
    check("format_timer 65 fa", format_timer(65, "fa"), "۰۱:۰۵")
    check("format_timer 0", format_timer(0, "en"), "00:00")

    print("\n=== Duration parsing ===")
    check("parse_duration '1h30m'", parse_duration("1h30m"), 90)
    check("parse_duration '90'", parse_duration("90"), 90)
    check("parse_duration '1:30:00'", parse_duration("1:30:00"), 90)
    check("parse_duration '1:30'", parse_duration("1:30"), 90)
    check("parse_duration '1:30:45'", parse_duration("1:30:45"), 91)
    check("parse_duration Persian", parse_duration("۱:۳۰"), 90)
    check("parse_duration empty", parse_duration(""), 0)
    check("parse_duration garbage", parse_duration("abc"), 0)

    print("\n=== HHMM conversion ===")
    check("minutes_to_hhmm 150 en", minutes_to_hhmm(150, "en"), "02:30")
    check("minutes_to_hhmm 150 fa", minutes_to_hhmm(150, "fa"), "۰۲:۳۰")
    check("hhmm_to_minutes '02:30'", hhmm_to_minutes("02:30"), 150)
    check("hhmm_to_minutes '۰۲:۳۰'", hhmm_to_minutes("۰۲:۳۰"), 150)

    print("\n=== Seconds to human ===")
    check("seconds_to_human 3661 en", seconds_to_human(3661, "en"), "1h 1m")
    check("seconds_to_human 3661 fa", seconds_to_human(3661, "fa"), "۱ ساعت ۱ دقیقه")
    check("seconds_to_human 0 fa", seconds_to_human(0, "fa"), "۰ دقیقه")

    print("\n=== Date arithmetic ===")
    check("days_between same", days_between("2025-01-01", "2025-01-08"), 7)
    check("days_between reverse", days_between("2025-01-08", "2025-01-01"), -7)
    check("add_days 7", add_days("2025-01-01", 7), "2025-01-08")
    check("add_days -1", add_days("2025-01-01", -1), "2024-12-31")
    check("start_of_week", start_of_week("2025-03-25"), "2025-03-22")
    check("end_of_week", end_of_week("2025-03-25"), "2025-03-28")
    check("start_of_month", start_of_month("2025-03-25"), "2025-03-01")
    check("end_of_month feb", end_of_month("2025-02-10"), "2025-02-28")
    check("end_of_month feb leap", end_of_month("2024-02-10"), "2024-02-29")
    check("end_of_month dec", end_of_month("2025-12-10"), "2025-12-31")
    check("start_of_year", start_of_year("2025-06-15"), "2025-01-01")
    check("end_of_year", end_of_year("2025-06-15"), "2025-12-31")

    print("\n=== Ranges ===")
    check("range_days 3", range_days("2025-01-01", "2025-01-03"),
          ["2025-01-01", "2025-01-02", "2025-01-03"])
    check("range_days reversed", range_days("2025-01-03", "2025-01-01"),
          ["2025-01-01", "2025-01-02", "2025-01-03"])
    check("range_months 3", range_months("2025-01-15", "2025-03-20"),
          ["2025-01-01", "2025-02-01", "2025-03-01"])

    print("\n=== Localized names ===")
    check("weekday_name Fri fa", weekday_name("2025-03-21", "fa"), "جمعه")
    check("weekday_name Sat en", weekday_name("2025-03-22", "en"), "Saturday")
    check("month_name Mar en", month_name("2025-03-21", "en"), "March")
    check("month_name Mar fa", month_name("2025-03-21", "fa"), "مارس")

    print("\n=== Predicates ===")
    check("is_today today", is_today(today_iso()), True)
    check("is_today yesterday", is_today(add_days(today_iso(), -1)), False)
    check("is_this_month next month",
          is_this_month(add_days(today_iso(), 40)), False)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
