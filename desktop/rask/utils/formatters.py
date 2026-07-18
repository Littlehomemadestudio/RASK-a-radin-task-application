"""
rask.utils.formatters
=====================

Persian / English formatting helpers for time, dates, durations,
percentages, and file sizes.

All functions accept a ``lang`` parameter (``"fa"`` or ``"en"``) and
return localized strings.  Persian digits are used by default when
``lang="fa"``.

Functions
---------

  • ``format_minutes_long(min, lang)``  — "2 ساعت و 30 دقیقه"
  • ``format_minutes_short(min, lang)`` — "2:30"
  • ``format_seconds(sec, lang)``       — "1:23:45"
  • ``format_percentage(p, lang, digits)`` — "85.5٪"
  • ``format_file_size(bytes, lang)``   — "12.3 مگابایت"
  • ``format_date_long(iso, lang, calendar)``  — "پنجشنبه، 27 تیر 1405"
  • ``format_date_medium(iso, lang, calendar)`` — "27 تیر 1405"
  • ``format_date_short(iso, lang, calendar)``  — "1405/04/27"
  • ``format_time(hhmm, lang, format_24)`` — "14:30" or "2:30 ب.ظ"
  • ``format_datetime(iso, lang)``       — combined
  • ``format_relative_short(iso, lang)`` — "5 دقیقه"
  • ``format_relative_long(iso, lang)``  — "5 دقیقه پیش"
  • ``format_range(from_iso, to_iso, lang)`` — "27 تا 30 تیر 1405"
  • ``format_duration_human(min, lang)`` — "نزدیک به 2 ساعت"

Example
-------

    >>> from rask.utils.formatters import format_minutes_long
    >>> format_minutes_long(150, lang="fa")
    '۲ ساعت و ۳۰ دقیقه'
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from ..core.jalali import gregorian_to_jalali, iso_to_jalali
from ..core.logging_utils import get_logger

__all__ = [
    "format_minutes_long",
    "format_minutes_short",
    "format_seconds",
    "format_percentage",
    "format_file_size",
    "format_date_long",
    "format_date_medium",
    "format_date_short",
    "format_time",
    "format_datetime",
    "format_relative_short",
    "format_relative_long",
    "format_range",
    "format_duration_human",
]

_log = get_logger("utils.formatters")


# =============================================================================
# === Persian digit helpers                                                  ===
# =============================================================================

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def _to_fa(s: str) -> str:
    """Convert Western digits in a string to Persian digits."""
    out = []
    for ch in s:
        if ch.isdigit():
            out.append(_FA_DIGITS[int(ch)])
        else:
            out.append(ch)
    return "".join(out)


def _digit(n: int, lang: str) -> str:
    """Format an integer in the requested language."""
    s = str(n)
    return _to_fa(s) if lang == "fa" else s


def _float(n: float, lang: str, digits: int = 1) -> str:
    """Format a float with `digits` decimal places."""
    s = f"{n:.{digits}f}"
    return _to_fa(s) if lang == "fa" else s


# =============================================================================
# === Persian weekday / month names                                          ===
# =============================================================================

WEEKDAYS_FA: list = [
    "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه",
    "جمعه", "شنبه", "یکشنبه",
]
WEEKDAYS_EN: list = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

JALALI_MONTHS_FA: list = [
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
]

GREGORIAN_MONTHS_FA: list = [
    "ژانویه", "فوریه", "مارس", "آوریل",
    "مه", "ژوئن", "ژوئیه", "اوت",
    "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]

GREGORIAN_MONTHS_EN: list = [
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December",
]


# =============================================================================
# === Duration formatters                                                    ===
# =============================================================================

def format_minutes_long(minutes: int, lang: str = "fa") -> str:
    """Format minutes as a long human string.

    Examples:
      fa: 0 → "۰ دقیقه"
      fa: 30 → "۳۰ دقیقه"
      fa: 60 → "۱ ساعت"
      fa: 90 → "۱ ساعت و ۳۰ دقیقه"
      fa: 150 → "۲ ساعت و ۳۰ دقیقه"
    """
    if minutes is None or minutes < 0:
        return ""
    minutes = int(minutes)
    hours = minutes // 60
    mins = minutes % 60
    parts: list = []
    if hours > 0:
        if lang == "fa":
            parts.append(f"{_digit(hours, lang)} ساعت")
        else:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if mins > 0 or not parts:
        if lang == "fa":
            parts.append(f"{_digit(mins, lang)} دقیقه")
        else:
            parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
    if lang == "fa":
        return " و ".join(parts)
    return " and ".join(parts)


def format_minutes_short(minutes: int, lang: str = "fa") -> str:
    """Format minutes as a short H:MM string.

    Examples: 90 → "1:30", 60 → "1:00", 30 → "0:30"
    """
    if minutes is None or minutes < 0:
        return ""
    minutes = int(minutes)
    hours = minutes // 60
    mins = minutes % 60
    s = f"{hours}:{mins:02d}"
    return _to_fa(s) if lang == "fa" else s


def format_seconds(seconds: int, lang: str = "fa") -> str:
    """Format seconds as H:MM:SS.

    Examples: 3661 → "1:01:01", 60 → "0:01:00"
    """
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    s = f"{hours}:{mins:02d}:{secs:02d}"
    return _to_fa(s) if lang == "fa" else s


def format_duration_human(minutes: int, lang: str = "fa") -> str:
    """Format minutes as a fuzzy human string.

    Examples (fa):
      30 → "نیم ساعت"
      50 → "نزدیک به ۱ ساعت"
      90 → "حدود ۱.۵ ساعت"
      120 → "۲ ساعت"
    """
    if minutes is None or minutes < 0:
        return ""
    minutes = int(minutes)
    if lang == "fa":
        if minutes < 45:
            return f"{_digit(minutes, lang)} دقیقه"
        if minutes < 55:
            return "نزدیک به ۱ ساعت"
        if minutes < 90:
            return "حدود ۱ ساعت"
        if minutes < 110:
            return "نزدیک به ۱.۵ ساعت"
        hours = round(minutes / 60)
        return f"حدود {_digit(hours, lang)} ساعت"
    if minutes < 45:
        return f"{minutes} minutes"
    if minutes < 55:
        return "almost 1 hour"
    if minutes < 90:
        return "about 1 hour"
    if minutes < 110:
        return "almost 1.5 hours"
    hours = round(minutes / 60)
    return f"about {hours} hours"


# =============================================================================
# === Percentage / file size                                                 ===
# =============================================================================

def format_percentage(p: float, lang: str = "fa", digits: int = 1) -> str:
    """Format a percentage value (0..100 or 0..1).

    Examples: 85.5 → "85.5٪" (fa) / "85.5%" (en)
    """
    if p is None:
        return ""
    # Normalize 0..1 to 0..100.
    if 0 <= p <= 1:
        p = p * 100
    s = _float(p, lang, digits)
    return f"{s}٪" if lang == "fa" else f"{s}%"


def format_file_size(num_bytes: int, lang: str = "fa") -> str:
    """Format a byte count as a human-readable file size.

    Examples (fa):
      500 → "۵۰۰ بایت"
      1024 → "۱ کیلوبایت"
      1024 * 1024 → "۱ مگابایت"
    """
    if num_bytes is None:
        return ""
    num_bytes = int(num_bytes)
    units_fa = ["بایت", "کیلوبایت", "مگابایت", "گگابایت", "ترابایت"]
    units_en = ["bytes", "KB", "MB", "GB", "TB"]
    units = units_fa if lang == "fa" else units_en
    size = float(num_bytes)
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    if unit_idx == 0:
        # Integer bytes.
        s = _digit(int(size), lang)
    else:
        s = _float(size, lang, 1)
    return f"{s} {units[unit_idx]}"


# =============================================================================
# === Date formatters                                                        ===
# =============================================================================

def _parse_iso(iso: str) -> Optional[date]:
    """Parse a YYYY-MM-DD ISO date string.  Returns None on failure."""
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except (ValueError, TypeError):
        return None


def format_date_long(
    iso: str,
    lang: str = "fa",
    calendar: str = "jalali",
) -> str:
    """Format a date as a long localized string.

    Examples:
      fa/jalali: "پنجشنبه، 27 تیر 1405"
      fa/gregorian: "پنجشنبه، 27 جولای 2025"
      en/gregorian: "Sunday, July 27, 2025"
    """
    d = _parse_iso(iso)
    if d is None:
        return ""
    weekday_name = (WEEKDAYS_FA if lang == "fa" else WEEKDAYS_EN)[d.weekday()]
    if calendar == "jalali":
        try:
            jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
            month_name = JALALI_MONTHS_FA[jm - 1]
            if lang == "fa":
                return f"{weekday_name}، {_digit(jd, lang)} {month_name} {_digit(jy, lang)}"
            return f"{weekday_name}, {jd} {month_name} {jy}"
        except Exception:  # noqa: BLE001
            pass
    # Gregorian.
    if lang == "fa":
        month_name = GREGORIAN_MONTHS_FA[d.month - 1]
        return f"{weekday_name}، {_digit(d.day, lang)} {month_name} {_digit(d.year, lang)}"
    month_name = GREGORIAN_MONTHS_EN[d.month - 1]
    return f"{weekday_name}, {d.day} {month_name} {d.year}"


def format_date_medium(
    iso: str,
    lang: str = "fa",
    calendar: str = "jalali",
) -> str:
    """Format a date as a medium-length string.

    Examples:
      fa/jalali: "27 تیر 1405"
      en/gregorian: "Jul 27, 2025"
    """
    d = _parse_iso(iso)
    if d is None:
        return ""
    if calendar == "jalali":
        try:
            jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
            month_name = JALALI_MONTHS_FA[jm - 1]
            if lang == "fa":
                return f"{_digit(jd, lang)} {month_name} {_digit(jy, lang)}"
            return f"{jd} {month_name} {jy}"
        except Exception:  # noqa: BLE001
            pass
    if lang == "fa":
        month_name = GREGORIAN_MONTHS_FA[d.month - 1]
        return f"{_digit(d.day, lang)} {month_name} {_digit(d.year, lang)}"
    month_name = GREGORIAN_MONTHS_EN[d.month - 1][:3]
    return f"{month_name} {d.day}, {d.year}"


def format_date_short(
    iso: str,
    lang: str = "fa",
    calendar: str = "jalali",
) -> str:
    """Format a date as a short numeric string.

    Examples:
      fa/jalali: "1405/04/27"
      en/gregorian: "2025/07/27"
    """
    d = _parse_iso(iso)
    if d is None:
        return ""
    if calendar == "jalali":
        try:
            jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
            s = f"{jy:04d}/{jm:02d}/{jd:02d}"
            return _to_fa(s) if lang == "fa" else s
        except Exception:  # noqa: BLE001
            pass
    s = f"{d.year:04d}/{d.month:02d}/{d.day:02d}"
    return _to_fa(s) if lang == "fa" else s


# =============================================================================
# === Time formatters                                                        ===
# =============================================================================

def format_time(
    hhmm: str,
    lang: str = "fa",
    format_24: bool = True,
) -> str:
    """Format a "HH:MM" string.

    Examples:
      24h: "14:30" → "14:30"
      12h fa: "14:30" → "2:30 ب.ظ"
      12h en: "14:30" → "2:30 PM"
    """
    if not hhmm:
        return ""
    try:
        parts = hhmm.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return hhmm
    if format_24:
        s = f"{h:02d}:{m:02d}"
        return _to_fa(s) if lang == "fa" else s
    # 12-hour.
    period_fa = "ق.ظ" if h < 12 else "ب.ظ"
    period_en = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    if lang == "fa":
        return f"{_digit(h12, lang)}:{_digit(m, lang).zfill(2)} {period_fa}"
    return f"{h12}:{m:02d} {period_en}"


def format_datetime(
    iso: str,
    lang: str = "fa",
    format_24: bool = True,
) -> str:
    """Format an ISO datetime as "date, time".

    Examples:
      fa: "27 تیر 1405، 14:30"
      en: "Jul 27, 2025, 14:30"
    """
    if not iso:
        return ""
    # Split date and time.
    date_part = iso[:10]
    time_part = ""
    if "T" in iso:
        time_part = iso.split("T")[1][:5]  # HH:MM
    date_str = format_date_medium(date_part, lang=lang)
    if not time_part:
        return date_str
    time_str = format_time(time_part, lang=lang, format_24=format_24)
    sep = "، " if lang == "fa" else ", "
    return f"{date_str}{sep}{time_str}"


# =============================================================================
# === Relative formatters                                                    ===
# =============================================================================

def format_relative_short(iso: str, lang: str = "fa") -> str:
    """Format a relative duration without "ago" suffix.

    Examples (fa): "5 دقیقه", "2 ساعت", "3 روز"
    """
    d = _parse_iso(iso)
    if d is None:
        return ""
    delta = date.today() - d
    days = delta.days
    if days == 0:
        return "امروز" if lang == "fa" else "today"
    if days == 1:
        return "دیروز" if lang == "fa" else "yesterday"
    if days < 7:
        unit = "روز" if lang == "fa" else "days"
        return f"{_digit(days, lang)} {unit}"
    if days < 30:
        weeks = days // 7
        unit = "هفته" if lang == "fa" else "weeks"
        return f"{_digit(weeks, lang)} {unit}"
    if days < 365:
        months = days // 30
        unit = "ماه" if lang == "fa" else "months"
        return f"{_digit(months, lang)} {unit}"
    years = days // 365
    unit = "سال" if lang == "fa" else "years"
    return f"{_digit(years, lang)} {unit}"


def format_relative_long(iso: str, lang: str = "fa") -> str:
    """Format a relative duration with "ago" suffix.

    Examples (fa): "5 دقیقه پیش", "2 ساعت پیش", "3 روز پیش"
    """
    short = format_relative_short(iso, lang=lang)
    if not short:
        return ""
    if lang == "fa":
        # Persian "ago" suffix.
        if short in ("امروز", "دیروز"):
            return short
        return f"{short} پیش"
    if short in ("today", "yesterday"):
        return short
    return f"{short} ago"


# =============================================================================
# === Range formatter                                                        ===
# =============================================================================

def format_range(
    from_iso: str,
    to_iso: str,
    lang: str = "fa",
    calendar: str = "jalali",
) -> str:
    """Format a date range.

    Examples (fa):
      same day:   "27 تیر 1405"
      same month: "27 تا 30 تیر 1405"
      same year:  "27 تیر تا 30 مرداد 1405"
      different:  "27 تیر 1405 تا 30 مرداد 1406"
    """
    d1 = _parse_iso(from_iso)
    d2 = _parse_iso(to_iso)
    if d1 is None or d2 is None:
        return ""

    def _jalali(d: date) -> tuple:
        return gregorian_to_jalali(d.year, d.month, d.day)

    if calendar == "jalali":
        try:
            jy1, jm1, jd1 = _jalali(d1)
            jy2, jm2, jd2 = _jalali(d2)
            if jy1 == jy2 and jm1 == jm2 and jd1 == jd2:
                return format_date_medium(from_iso, lang=lang, calendar=calendar)
            if jy1 == jy2 and jm1 == jm2:
                # Same month.
                if lang == "fa":
                    return (f"{_digit(jd1, lang)} تا {_digit(jd2, lang)} "
                            f"{JALALI_MONTHS_FA[jm1 - 1]} {_digit(jy1, lang)}")
                return f"{jd1} to {jd2} {JALALI_MONTHS_FA[jm1 - 1]} {jy1}"
            if jy1 == jy2:
                if lang == "fa":
                    return (f"{_digit(jd1, lang)} {JALALI_MONTHS_FA[jm1 - 1]} "
                            f"تا {_digit(jd2, lang)} "
                            f"{JALALI_MONTHS_FA[jm2 - 1]} {_digit(jy1, lang)}")
                return (f"{jd1} {JALALI_MONTHS_FA[jm1 - 1]} to {jd2} "
                        f"{JALALI_MONTHS_FA[jm2 - 1]} {jy1}")
            # Different years.
            return (f"{format_date_medium(from_iso, lang=lang, calendar=calendar)} "
                    f"{'تا' if lang == 'fa' else 'to'} "
                    f"{format_date_medium(to_iso, lang=lang, calendar=calendar)}")
        except Exception:  # noqa: BLE001
            pass
    # Gregorian.
    if d1.year == d2.year and d1.month == d2.month and d1.day == d2.day:
        return format_date_medium(from_iso, lang=lang, calendar=calendar)
    if d1.year == d2.year and d1.month == d2.month:
        if lang == "fa":
            month_name = GREGORIAN_MONTHS_FA[d1.month - 1]
            return (f"{_digit(d1.day, lang)} تا {_digit(d2.day, lang)} "
                    f"{month_name} {_digit(d1.year, lang)}")
        return f"{d1.day} to {d2.day} {GREGORIAN_MONTHS_EN[d1.month - 1][:3]} {d1.year}"
    return (f"{format_date_medium(from_iso, lang=lang, calendar=calendar)} "
            f"{'تا' if lang == 'fa' else 'to'} "
            f"{format_date_medium(to_iso, lang=lang, calendar=calendar)}")


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.formatters``."""
    print("Format examples (fa):")
    print(f"  format_minutes_long(150): {format_minutes_long(150, 'fa')}")
    print(f"  format_minutes_short(90): {format_minutes_short(90, 'fa')}")
    print(f"  format_seconds(3661): {format_seconds(3661, 'fa')}")
    print(f"  format_percentage(85.5): {format_percentage(85.5, 'fa')}")
    print(f"  format_file_size(1024*1024): {format_file_size(1024*1024, 'fa')}")
    print(f"  format_date_long(today): {format_date_long(today_iso(), 'fa')}")
    print(f"  format_date_medium(today): {format_date_medium(today_iso(), 'fa')}")
    print(f"  format_date_short(today): {format_date_short(today_iso(), 'fa')}")
    print(f"  format_time('14:30', 12h): {format_time('14:30', 'fa', False)}")
    print(f"  format_relative_short(7d ago): {format_relative_short((date.today() - timedelta(days=7)).isoformat(), 'fa')}")
    print(f"  format_relative_long(7d ago): {format_relative_long((date.today() - timedelta(days=7)).isoformat(), 'fa')}")
    print(f"  format_duration_human(50): {format_duration_human(50, 'fa')}")
    return 0


if __name__ == "__main__":
    import sys
    from rask.core.time_utils import today_iso
    sys.exit(_main())
