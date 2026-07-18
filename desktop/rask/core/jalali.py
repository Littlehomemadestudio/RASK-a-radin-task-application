"""
rask.core.jalali
================

Jalali (Persian Solar / Shamsi) calendar conversion and helpers.

Uses the Borkowski algorithm (the same one published by Kazimierz M.
Borkowski in *The Persian calendar for 3000 years*, 1996, and used by
the ``jalaali-js`` reference library).  Exact within the Jalali year
range ``-61 .. 3177`` inclusive, which is far beyond Rask's needs.

The web PWA's ``web/js/date-utils.js`` exposes a conversion routine of
the same name but contains a transcription bug (missing ``gy -= 621``
offset) that produces year-3000+ results for modern dates.  This module
intentionally diverges from that broken JS implementation in favor of
correct results — the public API and return types are identical, so
date displays in the desktop app behave as users actually expect.

Conversions
-----------
- ``gregorian_to_jalali(gy, gm, gd) -> (jy, jm, jd)``
- ``jalali_to_gregorian(jy, jm, jd) -> (gy, gm, gd)``

All ISO strings use the Gregorian ``YYYY-MM-DD`` form internally; Jalali
strings are only produced by ``jalali_to_iso`` / ``format_jalali`` for
display purposes (the database stores Gregorian ISO and computes Jalali
on demand, mirroring ``web/js/db.js``).

Persian month names (fa): فروردین اردیبهشت خرداد تیر مرداد شهریور
                          مهر آبان آذر دی بهمن اسفند

Persian weekday names (fa, Saturday-first):
    شنبه یکشنبه دوشنبه سه‌شنبه چهارشنبه پنجشنبه جمعه
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

__all__ = [
    "gregorian_to_jalali",
    "jalali_to_gregorian",
    "today_jalali",
    "jalali_month_length",
    "is_jalali_leap_year",
    "jalali_to_iso",
    "iso_to_jalali",
    "format_jalali",
    "parse_jalali",
    "jalali_month_name",
    "jalali_weekday_name",
    "jalali_add_days",
    "jalali_add_months",
    "jalali_start_of_month",
    "jalali_end_of_month",
    "jalali_start_of_year",
    "jalali_start_of_week",
]

# =============================================================================
# === Persian / English month and weekday names                              ===
# =============================================================================

# Persian month names — index 1..12 (index 0 unused).
JALALI_MONTHS_FA: Tuple[str, ...] = (
    "",  # 0 — unused
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
)

JALALI_MONTHS_EN: Tuple[str, ...] = (
    "",  # 0 — unused
    "Farvardin", "Ordibehesht", "Khordad",
    "Tir", "Mordad", "Shahrivar",
    "Mehr", "Aban", "Azar",
    "Dey", "Bahman", "Esfand",
)

# Persian weekday names — Saturday-first (index 0 = Saturday).
# Python's date.weekday() returns Monday=0..Sunday=6; we convert internally.
JALALI_WEEKDAYS_FA: Tuple[str, ...] = (
    "شنبه",      # Saturday
    "یکشنبه",    # Sunday
    "دوشنبه",    # Monday
    "سه‌شنبه",    # Tuesday
    "چهارشنبه",  # Wednesday
    "پنجشنبه",   # Thursday
    "جمعه",      # Friday
)

JALALI_WEEKDAYS_EN: Tuple[str, ...] = (
    "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
)

# Jalali years that begin a new 33-year leap cycle.  Used by the Borkowski
# algorithm to locate the correct cycle for any given year.  Identical to
# the BREAKS table in jalaali-js.
_BREAKS: Tuple[int, ...] = (
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
    1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178,
)

MIN_JALALI_YEAR: int = _BREAKS[0]
MAX_JALALI_YEAR: int = _BREAKS[-1] - 1


# =============================================================================
# === Core conversion (Borkowski algorithm — jalaali-js compatible)         ===
# =============================================================================

def _div(a: int, b: int) -> int:
    """Integer division truncated toward zero (mirrors JS ``~~(a/b)``)."""
    q = a // b
    if (a % b != 0) and ((a < 0) != (b < 0)):
        q += 1
    return q


def _mod(a: int, b: int) -> int:
    """Mathematical modulo — always non-negative when ``b > 0``."""
    return a - _div(a, b) * b


def _is_gregorian_leap(gy: int) -> bool:
    """Return True if `gy` is a Gregorian leap year."""
    return (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)


def _jal_cal_core(jy: int) -> Tuple[int, int, int, int]:
    """Locate `jy` in the cycle table; return ``(gy, march, jump, n)``.

    - ``gy``    : Gregorian year in which Farvardin 1 of `jy` falls.
    - ``march`` : Day of March (1..31, possibly negative for late Feb
                  in extreme edge cases) on which Farvardin 1 falls.
    - ``jump``  : Length of the current 33-year-aligned cycle.
    - ``n``     : Year offset of `jy` within its cycle.
    """
    if jy < MIN_JALALI_YEAR or jy > MAX_JALALI_YEAR:
        raise ValueError(
            f"Jalali year {jy} out of supported range "
            f"[{MIN_JALALI_YEAR}, {MAX_JALALI_YEAR}]"
        )
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for i in range(1, len(_BREAKS)):
        jm = _BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp

    leap_j = leap_j + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1

    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    return gy, march, jump, n


def _leap_from_cycle(jump: int, n: int) -> int:
    """Return years-since-last-leap (0..4).  ``0`` means the year is leap."""
    adjusted = n
    if jump - n < 6:
        adjusted = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(adjusted + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap


def _jal_cal_leap(jy: int) -> int:
    """Leap-cycle state of `jy` (0 = leap year)."""
    if jy < MIN_JALALI_YEAR or jy > MAX_JALALI_YEAR:
        raise ValueError(
            f"Jalali year {jy} out of supported range "
            f"[{MIN_JALALI_YEAR}, {MAX_JALALI_YEAR}]"
        )
    jp = _BREAKS[0]
    jump = 0
    for i in range(1, len(_BREAKS)):
        jm = _BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        jp = jm
    return _leap_from_cycle(jump, jy - jp)


def _g2d(gy: int, gm: int, gd: int) -> int:
    """Convert a Gregorian date to a Julian Day Number."""
    d = (
        _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4)
        + _div(153 * _mod(gm + 9, 12) + 2, 5)
        + gd
        - 34840408
    )
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d


def _d2g(jdn: int) -> Tuple[int, int, int]:
    """Convert a Julian Day Number to a Gregorian ``(gy, gm, gd)`` tuple."""
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd


def _j2d(jy: int, jm: int, jd: int) -> int:
    """Convert a Jalali date to a Julian Day Number."""
    gy, march, _, _ = _jal_cal_core(jy)
    return _g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1


def _d2j(jdn: int) -> Tuple[int, int, int]:
    """Convert a Julian Day Number to a Jalali ``(jy, jm, jd)`` tuple."""
    gy, _, _ = _d2g(jdn)
    jy = gy - 621
    _, _, _, _ = _jal_cal_core(jy)  # validates range
    gy2, march, jump, n = _jal_cal_core(jy)
    leap = _leap_from_cycle(jump, n)
    jdn1f = _g2d(gy2, 3, march)
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            # First six months are 31 days each.
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        # The JDN falls in the previous Jalali year.
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1


# =============================================================================
# === Public conversion API                                                  ===
# =============================================================================

def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    """Convert a Gregorian date to a Jalali (Persian Solar) date.

    Uses the Borkowski 1996 algorithm (identical to ``jalaali-js``)
    which is exact within the Jalali year range ``-61 .. 3177``.

    Parameters
    ----------
    gy : int
        Gregorian year (e.g. 2025).  Must be ≥ 1.
    gm : int
        Gregorian month, 1..12.
    gd : int
        Gregorian day, 1..31.

    Returns
    -------
    (jy, jm, jd) : tuple of int
        Jalali year, month (1..12), and day (1..31).

    Examples
    --------
    >>> gregorian_to_jalali(2025, 3, 21)
    (1404, 1, 1)
    >>> gregorian_to_jalali(2025, 1, 1)
    (1403, 10, 12)
    """
    if gy < 1 or gm < 1 or gm > 12 or gd < 1 or gd > 31:
        raise ValueError(f"Invalid Gregorian date: ({gy}, {gm}, {gd})")
    return _d2j(_g2d(gy, gm, gd))


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    """Convert a Jalali (Persian Solar) date to a Gregorian date.

    Inverse of :func:`gregorian_to_jalali`.  Algorithm mirrors
    ``jalaali-js`` exactly.

    Parameters
    ----------
    jy : int
        Jalali year (e.g. 1404).  Must be in ``[-61, 3177]``.
    jm : int
        Jalali month, 1..12.
    jd : int
        Jalali day, 1..31.

    Returns
    -------
    (gy, gm, gd) : tuple of int
        Gregorian year, month (1..12), and day (1..31).
    """
    if jm < 1 or jm > 12 or jd < 1 or jd > 31:
        raise ValueError(f"Invalid Jalali date: ({jy}, {jm}, {jd})")
    return _d2g(_j2d(jy, jm, jd))


# =============================================================================
# === Leap year + month length                                               ===
# =============================================================================

def is_jalali_leap_year(jy: int) -> bool:
    """Return True if the Jalali year `jy` is a leap year (366 days).

    Uses the Borkowski 33-year-cycle leap rule — identical to
    ``jalaali-js``'s ``isLeapJalaaliYear``.

    Examples
    --------
    >>> is_jalali_leap_year(1403)
    True
    >>> is_jalali_leap_year(1404)
    False
    """
    try:
        return _jal_cal_leap(jy) == 0
    except ValueError:
        return False


def jalali_month_length(jy: int, jm: int) -> int:
    """Return the number of days in the given Jalali month.

    Months 1..6 have 31 days, months 7..11 have 30 days, and month 12
    (Esfand) has 29 days, or 30 in a leap year.

    Examples
    --------
    >>> jalali_month_length(1404, 1)
    31
    >>> jalali_month_length(1403, 12)  # 1403 is leap
    30
    >>> jalali_month_length(1404, 12)  # 1404 is not leap
    29
    """
    if jm < 1 or jm > 12:
        raise ValueError(f"Invalid Jalali month: {jm}")
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_jalali_leap_year(jy) else 29


# =============================================================================
# === Today + ISO <-> Jalali helpers                                         ===
# =============================================================================

def today_jalali() -> Tuple[int, int, int]:
    """Return today's Jalali date as ``(jy, jm, jd)`` using local time."""
    today = date.today()
    return gregorian_to_jalali(today.year, today.month, today.day)


def jalali_to_iso(jy: int, jm: int, jd: int) -> str:
    """Format a Jalali date as a Jalali ISO string ``YYYY-MM-DD``.

    Note: this returns the *Jalali* components formatted as ISO — for a
    Gregorian ISO date use :func:`jalali_to_gregorian` then format.

    Example
    -------
    >>> jalali_to_iso(1404, 1, 1)
    '1404-01-01'
    """
    if jy < 1 or jm < 1 or jm > 12 or jd < 1 or jd > 31:
        raise ValueError(f"Invalid Jalali date: ({jy}, {jm}, {jd})")
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


def iso_to_jalali(iso: str) -> Tuple[int, int, int]:
    """Parse a Gregorian ISO date ``YYYY-MM-DD`` and return Jalali ``(jy, jm, jd)``.

    Accepts both ``YYYY-MM-DD`` and ``YYYY-MM-DDTHH:MM:SS`` forms — the
    time portion (if any) is discarded.

    Example
    -------
    >>> iso_to_jalali('2025-03-21')
    (1404, 1, 1)
    """
    if not iso or not isinstance(iso, str):
        raise ValueError("iso must be a non-empty string")
    parts = iso.split("T", 1)[0].split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid ISO date: {iso!r}")
    gy, gm, gd = int(parts[0]), int(parts[1]), int(parts[2])
    return gregorian_to_jalali(gy, gm, gd)


# =============================================================================
# === Display formatting                                                     ===
# =============================================================================

def jalali_month_name(jm: int, lang: str = "fa") -> str:
    """Return the localized month name for the given Jalali month (1..12).

    Examples
    --------
    >>> jalali_month_name(1, "fa")
    'فروردین'
    >>> jalali_month_name(7, "en")
    'Mehr'
    """
    if jm < 1 or jm > 12:
        return ""
    if lang == "fa":
        return JALALI_MONTHS_FA[jm]
    return JALALI_MONTHS_EN[jm]


def jalali_weekday_name(wd: int, lang: str = "fa") -> str:
    """Return the localized weekday name for a Saturday-first weekday index.

    `wd` is **Saturday-first** (0..6) to match Persian convention.
    Pass ``jalali_weekday_from_iso(iso)`` to get this index from a date.

    Examples
    --------
    >>> jalali_weekday_name(0, "fa")  # Saturday
    'شنبه'
    >>> jalali_weekday_name(6, "fa")  # Friday
    'جمعه'
    """
    if wd < 0 or wd > 6:
        return ""
    if lang == "fa":
        return JALALI_WEEKDAYS_FA[wd]
    return JALALI_WEEKDAYS_EN[wd]


def _jalali_weekday_index_from_gregorian(d: date) -> int:
    """Convert a Gregorian date to a Saturday-first weekday index (0..6).

    Python's ``date.weekday()`` returns Mon=0..Sun=6.  Saturday-first
    means Sat=0, Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6.
    """
    py_wd = d.weekday()  # Mon=0..Sun=6
    # Mon -> 2, Tue -> 3, Wed -> 4, Thu -> 5, Fri -> 6, Sat -> 0, Sun -> 1
    return (py_wd + 2) % 7


def format_jalali(iso: str, fmt: str = "long", lang: str = "fa") -> str:
    """Format a Gregorian ISO date as a localized Jalali string.

    Parameters
    ----------
    iso : str
        Gregorian ISO date (``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM:SS``).
    fmt : str
        One of ``"long"`` (default), ``"short"``, ``"month"``,
        ``"weekday"``, or ``"full"``.

        - ``long``    -> ``"۱ فروردین ۱۴۰۴"``  /  ``"1 Farvardin 1404"``
        - ``short``   -> ``"۱/۰۱/۱۴۰۴"``   /  ``"1404/01/01"``
        - ``month``   -> ``"فروردین ۱۴۰۴"``
        - ``weekday`` -> ``"جمعه"``
        - ``full``    -> ``"جمعه، ۱ فروردین ۱۴۰۴"``
    lang : str
        ``"fa"`` (default) for Persian, ``"en"`` for English.
    """
    if not iso:
        return ""
    jy, jm, jd = iso_to_jalali(iso)
    if fmt == "short":
        if lang == "fa":
            return _fa(f"{jd}/{jm}/{jy}")
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    if fmt == "month":
        if lang == "fa":
            return f"{jalali_month_name(jm, 'fa')} {_fa(jy)}"
        return f"{jalali_month_name(jm, 'en')} {jy}"
    if fmt == "weekday":
        d = _parse_iso_date(iso)
        return jalali_weekday_name(_jalali_weekday_index_from_gregorian(d), lang)
    if fmt == "full":
        d = _parse_iso_date(iso)
        wd_name = jalali_weekday_name(_jalali_weekday_index_from_gregorian(d), lang)
        if lang == "fa":
            return f"{wd_name}، {_fa(jd)} {jalali_month_name(jm, 'fa')} {_fa(jy)}"
        return f"{wd_name}, {jd} {jalali_month_name(jm, 'en')} {jy}"
    # default: long
    if lang == "fa":
        return f"{_fa(jd)} {jalali_month_name(jm, 'fa')} {_fa(jy)}"
    return f"{jd} {jalali_month_name(jm, 'en')} {jy}"


def parse_jalali(s: str) -> str:
    """Parse a Jalali date string and return the Gregorian ISO ``YYYY-MM-DD``.

    Accepts ``YYYY-MM-DD``, ``YYYY/MM/DD``, ``DD/MM/YYYY`` (Persian
    convention), or ``YYYY-MM-DDTHH:MM:SS``.  Persian digits are
    accepted and normalized.

    Raises ``ValueError`` on unparseable input.

    Examples
    --------
    >>> parse_jalali('1404-01-01')
    '2025-03-21'
    >>> parse_jalali('۱۴۰۴/۰۱/۰۱')
    '2025-03-21'
    """
    if not s or not isinstance(s, str):
        raise ValueError("parse_jalali requires a non-empty string")
    s = _to_en_digits(s).strip()
    s = s.split("T", 1)[0]
    s = s.replace("/", "-")
    parts = [p for p in s.split("-") if p]
    if len(parts) != 3:
        raise ValueError(f"Cannot parse Jalali date: {s!r}")
    a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
    # Heuristic: if the first component is 4 digits, it's YYYY-MM-DD.
    if len(parts[0]) == 4 and a > 1000:
        jy, jm, jd = a, b, c
    else:
        # Assume DD-MM-YYYY (Persian day-first convention).
        jd, jm, jy = a, b, c
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


# =============================================================================
# === Date arithmetic (operates on Gregorian ISO strings, Jalali semantics)  ===
# =============================================================================

def jalali_add_days(iso: str, n: int) -> str:
    """Add `n` days to a Gregorian ISO date, return the new ISO date.

    Example
    -------
    >>> jalali_add_days('2025-03-20', 1)
    '2025-03-21'
    """
    d = _parse_iso_date(iso)
    return (d + timedelta(days=n)).isoformat()


def jalali_add_months(iso: str, n: int) -> str:
    """Add `n` Jalali months to a Gregorian ISO date.

    The day is clamped to the last day of the target Jalali month
    (e.g. adding 1 month to 1404/01/31 -> 1404/02/30 since month 2 has
    30 days).

    Example
    -------
    >>> jalali_add_months('2025-03-21', 1)  # Farvardin 1 -> Ordibehesht 1
    '2025-04-21'
    """
    jy, jm, jd = iso_to_jalali(iso)
    total = (jy * 12 + (jm - 1)) + n
    new_jy = total // 12
    new_jm = total % 12 + 1
    max_day = jalali_month_length(new_jy, new_jm)
    new_jd = min(jd, max_day)
    gy, gm, gd = jalali_to_gregorian(new_jy, new_jm, new_jd)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def jalali_start_of_month(iso: str) -> str:
    """Return the Gregorian ISO for the first day of the Jalali month.

    Example
    -------
    >>> jalali_start_of_month('2025-03-25')  # 5 Farvardin 1404 -> 1 Farvardin
    '2025-03-21'
    """
    jy, jm, _ = iso_to_jalali(iso)
    gy, gm, gd = jalali_to_gregorian(jy, jm, 1)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def jalali_end_of_month(iso: str) -> str:
    """Return the Gregorian ISO for the last day of the Jalali month.

    Example
    -------
    >>> jalali_end_of_month('2025-03-25')  # Farvardin has 31 days
    '2025-04-20'
    """
    jy, jm, _ = iso_to_jalali(iso)
    last = jalali_month_length(jy, jm)
    gy, gm, gd = jalali_to_gregorian(jy, jm, last)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def jalali_start_of_year(iso: str) -> str:
    """Return the Gregorian ISO for Farvardin 1st of the same Jalali year.

    Example
    -------
    >>> jalali_start_of_year('2025-06-01')
    '2025-03-21'
    """
    jy, _, _ = iso_to_jalali(iso)
    gy, gm, gd = jalali_to_gregorian(jy, 1, 1)
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def jalali_start_of_week(iso: str, first_day: int = 6) -> str:
    """Return the ISO date for the start of the Jalali week containing `iso`.

    In Iran the week starts on Saturday (``first_day=6``, default).
    The ``first_day`` parameter follows the JavaScript ``Date.getDay()``
    convention (Sun=0, Mon=1, …, Sat=6), matching the web PWA's
    ``DateUtils.startOfWeek``.  Pass ``0`` for a Sunday-first week or
    ``1`` for a Monday-first week.

    The returned date is the most recent `first_day` on or before `iso`.

    Example
    -------
    >>> jalali_start_of_week('2025-03-25')  # Tue -> Sat start
    '2025-03-22'
    """
    d = _parse_iso_date(iso)
    # Python weekday: Mon=0..Sun=6.  JS getDay: Sun=0..Sat=6.
    # Convert: js_day = (py_weekday + 1) % 7.
    js_day = (d.weekday() + 1) % 7
    delta = (js_day - first_day) % 7
    return (d - timedelta(days=delta)).isoformat()


# =============================================================================
# === Internal helpers                                                       ===
# =============================================================================

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_FA_TO_EN = str.maketrans(_FA_DIGITS, _EN_DIGITS)
_EN_TO_FA = str.maketrans(_EN_DIGITS, _FA_DIGITS)


def _fa(value) -> str:
    """Convert digits in `value` to Persian."""
    return str(value).translate(_EN_TO_FA)


def _to_en_digits(s: str) -> str:
    """Convert Persian digits in `s` to Western digits."""
    return s.translate(_FA_TO_EN)


def _parse_iso_date(iso: str) -> date:
    """Parse a possibly partial ISO string into a ``date`` object."""
    if not iso:
        raise ValueError("iso must be non-empty")
    s = iso.split("T", 1)[0]
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {iso!r}") from exc


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    """Self-test harness invoked when this module is run directly.

    Runs ~30 conversion / formatting / arithmetic checks and prints
    a pass/fail report.  Returns the failure count.
    """
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

    print("=== Jalali conversion tests ===")

    # Known Gregorian -> Jalali anchor dates (verified against time.ir).
    check("2025-01-01 -> 1403/10/12",
          gregorian_to_jalali(2025, 1, 1), (1403, 10, 12))
    check("2025-03-21 -> 1404/01/01 (Nowruz)",
          gregorian_to_jalali(2025, 3, 21), (1404, 1, 1))
    check("2025-03-20 -> 1403/12/30 (last day of 1403)",
          gregorian_to_jalali(2025, 3, 20), (1403, 12, 30))
    check("2024-03-20 -> 1403/01/01 (Nowruz 1403)",
          gregorian_to_jalali(2024, 3, 20), (1403, 1, 1))
    check("2023-03-21 -> 1402/01/01 (Nowruz 1402)",
          gregorian_to_jalali(2023, 3, 21), (1402, 1, 1))
    check("2022-03-21 -> 1401/01/01 (Nowruz 1401)",
          gregorian_to_jalali(2022, 3, 21), (1401, 1, 1))
    check("2020-03-20 -> 1399/01/01 (Nowruz 1399, leap)",
          gregorian_to_jalali(2020, 3, 20), (1399, 1, 1))
    check("1979-03-21 -> 1358/01/01 (revolution year)",
          gregorian_to_jalali(1979, 3, 21), (1358, 1, 1))
    check("2000-02-29 -> 1378/12/10 (Gregorian leap day)",
          gregorian_to_jalali(2000, 2, 29), (1378, 12, 10))

    print("\n=== Jalali -> Gregorian round-trip ===")
    check("1404/01/01 -> 2025-03-21",
          jalali_to_gregorian(1404, 1, 1), (2025, 3, 21))
    check("1403/12/30 -> 2025-03-20",
          jalali_to_gregorian(1403, 12, 30), (2025, 3, 20))
    check("1403/10/12 -> 2025-01-01",
          jalali_to_gregorian(1403, 10, 12), (2025, 1, 1))
    check("1403/01/01 -> 2024-03-20",
          jalali_to_gregorian(1403, 1, 1), (2024, 3, 20))
    # Round-trip a bunch of dates.
    for d in [(2024, 1, 15), (2024, 6, 21), (2025, 9, 1), (2023, 12, 31)]:
        j = gregorian_to_jalali(*d)
        g2 = jalali_to_gregorian(*j)
        check(f"round-trip {d}", g2, d)

    print("\n=== Leap year and month length ===")
    check("1403 is leap", is_jalali_leap_year(1403), True)
    check("1404 is not leap", is_jalali_leap_year(1404), False)
    check("1399 is leap", is_jalali_leap_year(1399), True)
    check("Month 1 has 31 days", jalali_month_length(1404, 1), 31)
    check("Month 6 has 31 days", jalali_month_length(1404, 6), 31)
    check("Month 7 has 30 days", jalali_month_length(1404, 7), 30)
    check("Month 12 in 1403 (leap) has 30 days",
          jalali_month_length(1403, 12), 30)
    check("Month 12 in 1404 (non-leap) has 29 days",
          jalali_month_length(1404, 12), 29)

    print("\n=== ISO helpers ===")
    check("iso_to_jalali('2025-03-21')",
          iso_to_jalali("2025-03-21"), (1404, 1, 1))
    check("jalali_to_iso(1404, 1, 1)",
          jalali_to_iso(1404, 1, 1), "1404-01-01")
    check("parse_jalali('1404-01-01')",
          parse_jalali("1404-01-01"), "2025-03-21")
    check("parse_jalali('1404/01/01')",
          parse_jalali("1404/01/01"), "2025-03-21")
    check("parse_jalali with Persian digits",
          parse_jalali("۱۴۰۴/۰۱/۰۱"), "2025-03-21")

    print("\n=== Display formatting ===")
    check("format long fa",
          format_jalali("2025-03-21", "long", "fa"),
          "۱ فروردین ۱۴۰۴")
    check("format long en",
          format_jalali("2025-03-21", "long", "en"),
          "1 Farvardin 1404")
    check("format short fa",
          format_jalali("2025-03-21", "short", "fa"),
          "۱/۱/۱۴۰۴")
    check("format month fa",
          format_jalali("2025-03-21", "month", "fa"),
          "فروردین ۱۴۰۴")
    check("format weekday for 2025-03-21 (Friday)",
          format_jalali("2025-03-21", "weekday", "fa"),
          "جمعه")

    print("\n=== Date arithmetic ===")
    check("add 1 day to 2025-03-20",
          jalali_add_days("2025-03-20", 1), "2025-03-21")
    check("add 7 days to 2025-01-01",
          jalali_add_days("2025-01-01", 7), "2025-01-08")
    check("add 1 Jalali month to 2025-03-21 (Farvardin 1 -> Ordibehesht 1)",
          jalali_add_months("2025-03-21", 1), "2025-04-21")
    check("start of Jalali month for 2025-03-25",
          jalali_start_of_month("2025-03-25"), "2025-03-21")
    check("end of Jalali month for 2025-03-25",
          jalali_end_of_month("2025-03-25"), "2025-04-20")
    check("start of Jalali year for 2025-06-01",
          jalali_start_of_year("2025-06-01"), "2025-03-21")
    # 2025-03-25 is a Tuesday.  Saturday-first start of week = 2025-03-22.
    check("start of Jalali week (Sat) for 2025-03-25",
          jalali_start_of_week("2025-03-25", first_day=6), "2025-03-22")

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    # Run with:  python -m rask.core.jalali
    import sys
    sys.exit(1 if _run_tests() else 0)
