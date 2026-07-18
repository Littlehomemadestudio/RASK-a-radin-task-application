"""
rask.core.validators
====================

Input validation helpers for the Rask desktop app.

Every function returns a plain ``bool`` / sanitized value — no
exceptions raised on invalid input.  This makes the helpers easy to
use inline in form handlers:

    if not is_valid_title(title):
        show_error("Invalid title")

For the rare cases where raising is preferred (e.g. service-layer
guards), the underlying predicate can be wrapped in ``if not X: raise``.

All functions are pure (no I/O, no globals) and tolerate ``None``
input by treating it as invalid / empty.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional, Union

__all__ = [
    "is_valid_title",
    "is_valid_pin",
    "is_valid_iso_date",
    "is_valid_iso_datetime",
    "is_valid_hhmm",
    "is_valid_color_hex",
    "is_valid_email",
    "is_valid_url",
    "is_valid_duration_min",
    "is_valid_target_minutes",
    "sanitize_title",
    "sanitize_notes",
    "sanitize_tags",
    "parse_int_safe",
    "parse_float_safe",
]

# =============================================================================
# === Title / notes                                                          ===
# =============================================================================

#: Maximum title length (matches the SQLite schema's TEXT constraint
#: enforced in the UI layer).
TITLE_MAX_LEN: int = 200

#: Maximum notes length.
NOTES_MAX_LEN: int = 5000

#: Maximum number of tags per activity.
TAGS_MAX_COUNT: int = 10

#: Maximum length of a single tag.
TAG_MAX_LEN: int = 20


def is_valid_title(s: Any) -> bool:
    """Return True if `s` is a non-empty title with ≤ 200 non-whitespace chars.

    A valid title:
      - is a ``str``
      - has at least 1 non-whitespace character after stripping
      - has ≤ 200 characters after whitespace normalization
      - does not contain control characters (except tab and newline)

    Examples
    --------
    >>> is_valid_title("Hello")
    True
    >>> is_valid_title("   ")
    False
    >>> is_valid_title(None)
    False
    >>> is_valid_title("")
    False
    """
    if not isinstance(s, str):
        return False
    stripped = s.strip()
    if not stripped:
        return False
    if len(stripped) > TITLE_MAX_LEN:
        return False
    # Reject control characters (except \t \n \r).
    for ch in stripped:
        if unicodedata.category(ch).startswith("C") and ch not in "\t\n\r":
            return False
    return True


def sanitize_title(s: Any) -> str:
    """Strip, collapse whitespace, and truncate `s` to a valid title.

    Returns the empty string for non-string / empty input.

    Examples
    --------
    >>> sanitize_title("  Hello   World  ")
    'Hello World'
    >>> sanitize_title(None)
    ''
    >>> sanitize_title("a" * 300)[:10]
    'aaaaaaaaaa'
    """
    if not isinstance(s, str):
        return ""
    # Normalize unicode whitespace and collapse runs.
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > TITLE_MAX_LEN:
        s = s[:TITLE_MAX_LEN]
    return s


def sanitize_notes(s: Any) -> str:
    """Strip leading/trailing whitespace and truncate `s` to ≤ 5000 chars.

    Internal newlines are preserved (notes may be multi-line).

    Examples
    --------
    >>> sanitize_notes("  Hello\\nWorld  ")
    'Hello\\nWorld'
    >>> sanitize_notes(None)
    ''
    """
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFC", s)
    # Collapse runs of spaces (but not newlines).
    s = re.sub(r"[^\S\n\r]+", " ", s)
    s = s.strip()
    if len(s) > NOTES_MAX_LEN:
        s = s[:NOTES_MAX_LEN]
    return s


# =============================================================================
# === PIN                                                                   ===
# =============================================================================

#: Regex matching a valid 4-6 digit ASCII PIN.
_PIN_RE = re.compile(r"^\d{4,6}$")


def is_valid_pin(s: Any) -> bool:
    """Return True if `s` is a 4-6 digit ASCII PIN.

    Examples
    --------
    >>> is_valid_pin("1234")
    True
    >>> is_valid_pin("123456")
    True
    >>> is_valid_pin("123")
    False
    >>> is_valid_pin("1234567")
    False
    >>> is_valid_pin(None)
    False
    """
    if not isinstance(s, str):
        return False
    return bool(_PIN_RE.match(s))


# =============================================================================
# === ISO date / datetime                                                    ===
# =============================================================================

#: YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: YYYY-MM-DDTHH:MM:SS (with optional fractional seconds / TZ offset)
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def is_valid_iso_date(s: Any) -> bool:
    """Return True if `s` matches ``YYYY-MM-DD`` and is a real calendar date.

    Examples
    --------
    >>> is_valid_iso_date("2025-03-21")
    True
    >>> is_valid_iso_date("2025-13-01")
    False
    >>> is_valid_iso_date("2025-3-21")
    False
    >>> is_valid_iso_date(None)
    False
    """
    if not isinstance(s, str) or not _DATE_RE.match(s):
        return False
    try:
        from datetime import date as _d
        _d.fromisoformat(s)
    except ValueError:
        return False
    return True


def is_valid_iso_datetime(s: Any) -> bool:
    """Return True if `s` is a parseable ISO-8601 datetime string.

    Examples
    --------
    >>> is_valid_iso_datetime("2025-03-21T14:30:00")
    True
    >>> is_valid_iso_datetime("2025-03-21T14:30:00Z")
    True
    >>> is_valid_iso_datetime("2025-03-21T14:30:00+03:30")
    True
    >>> is_valid_iso_datetime("2025-03-21")
    False
    """
    if not isinstance(s, str) or not _DATETIME_RE.match(s):
        return False
    try:
        from datetime import datetime as _dt
        _dt.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


# =============================================================================
# === HH:MM time                                                            ===
# =============================================================================

_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def is_valid_hhmm(s: Any) -> bool:
    """Return True if `s` is a valid 24-hour ``HH:MM`` time string.

    Examples
    --------
    >>> is_valid_hhmm("14:30")
    True
    >>> is_valid_hhmm("00:00")
    True
    >>> is_valid_hhmm("23:59")
    True
    >>> is_valid_hhmm("24:00")
    False
    >>> is_valid_hhmm("14:60")
    False
    """
    if not isinstance(s, str):
        return False
    return bool(_HHMM_RE.match(s))


# =============================================================================
# === Color hex                                                             ===
# =============================================================================

_HEX_RE = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def is_valid_color_hex(s: Any) -> bool:
    """Return True if `s` is a valid hex color (3, 6, or 8 digits, optional #).

    Examples
    --------
    >>> is_valid_color_hex("#D4AF37")
    True
    >>> is_valid_color_hex("D4AF37")
    True
    >>> is_valid_color_hex("#FFF")
    True
    >>> is_valid_color_hex("#FFAA2299")
    True
    >>> is_valid_color_hex("XYZ")
    False
    >>> is_valid_color_hex(None)
    False
    """
    if not isinstance(s, str):
        return False
    return bool(_HEX_RE.match(s))


# =============================================================================
# === Email / URL                                                           ===
# =============================================================================

# Pragmatic email regex — not RFC-strict but catches common typos.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

# Pragmatic URL regex — accepts http/https/ftp and any TLD ≥ 2 chars.
_URL_RE = re.compile(
    r"^(?:https?|ftp)://"
    r"(?:[A-Za-z0-9\-._~%!$&'()*+,;=]+@)?"
    r"(?:\[[0-9a-fA-F:.]+\]|[A-Za-z0-9\-._~%]+)"
    r"(?::\d+)?"
    r"(?:/[A-Za-z0-9\-._~%!$&'()*+,;=:@/]*)?"
    r"(?:\?[A-Za-z0-9\-._~%!$&'()*+,;=:@/?]*)?"
    r"(?:#[A-Za-z0-9\-._~%!$&'()*+,;=:@/?]*)?$"
)


def is_valid_email(s: Any) -> bool:
    """Return True if `s` is a plausible email address.

    Examples
    --------
    >>> is_valid_email("user@example.com")
    True
    >>> is_valid_email("a.b+tag@sub.example.co")
    True
    >>> is_valid_email("no-at-sign")
    False
    >>> is_valid_email(None)
    False
    """
    if not isinstance(s, str):
        return False
    return bool(_EMAIL_RE.match(s))


def is_valid_url(s: Any) -> bool:
    """Return True if `s` is a plausible http(s)/ftp URL.

    Examples
    --------
    >>> is_valid_url("https://example.com")
    True
    >>> is_valid_url("http://example.com/path?q=1#frag")
    True
    >>> is_valid_url("ftp://files.example.org:21/foo")
    True
    >>> is_valid_url("not-a-url")
    False
    >>> is_valid_url(None)
    False
    """
    if not isinstance(s, str):
        return False
    return bool(_URL_RE.match(s))


# =============================================================================
# === Numeric ranges                                                        ===
# =============================================================================

def is_valid_duration_min(n: Any) -> bool:
    """Return True if `n` is an integer in the inclusive range 0..1440.

    1440 = 24 hours in minutes — the longest single activity the app
    supports.  Anything longer should be split into multiple sessions.

    Examples
    --------
    >>> is_valid_duration_min(0)
    True
    >>> is_valid_duration_min(1440)
    True
    >>> is_valid_duration_min(1441)
    False
    >>> is_valid_duration_min(-1)
    False
    >>> is_valid_duration_min("30")
    False
    >>> is_valid_duration_min(None)
    False
    """
    if isinstance(n, bool):
        return False  # bools are ints in Python; reject explicitly
    if not isinstance(n, int):
        return False
    return 0 <= n <= 1440


def is_valid_target_minutes(n: Any) -> bool:
    """Return True if `n` is an integer in the inclusive range 1..10000.

    Used to validate daily / weekly / monthly goal targets.  10,000
    minutes ≈ 166 hours, far beyond any reasonable weekly target.

    Examples
    --------
    >>> is_valid_target_minutes(1)
    True
    >>> is_valid_target_minutes(10000)
    True
    >>> is_valid_target_minutes(0)
    False
    >>> is_valid_target_minutes(10001)
    False
    """
    if isinstance(n, bool):
        return False
    if not isinstance(n, int):
        return False
    return 1 <= n <= 10000


# =============================================================================
# === Tags                                                                  ===
# =============================================================================

def sanitize_tags(tags: Any) -> List[str]:
    """Normalize a list of tag strings into a clean, deduped list.

    - Strips whitespace and lowercases each tag.
    - Truncates each tag to 20 characters.
    - Drops empty tags.
    - Keeps at most 10 tags (the first 10 in input order).
    - Deduplicates case-insensitively (preserves the first occurrence).

    Examples
    --------
    >>> sanitize_tags(["Focus", " focus ", "DEEP", "", "a" * 30])
    ['focus', 'deep', 'aaaaaaaaaaaaaaaaaaaa']
    >>> sanitize_tags(None)
    []
    >>> sanitize_tags("not-a-list")
    []
    """
    if not isinstance(tags, (list, tuple, set)):
        return []
    seen: set = set()
    out: List[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        tag = unicodedata.normalize("NFC", tag).strip().lower()
        if not tag:
            continue
        if len(tag) > TAG_MAX_LEN:
            tag = tag[:TAG_MAX_LEN]
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= TAGS_MAX_COUNT:
            break
    return out


# =============================================================================
# === Safe numeric parsing                                                  ===
# =============================================================================

def parse_int_safe(s: Any, default: int = 0) -> int:
    """Parse `s` as an int, returning `default` on failure.

    Persian / Arabic digits are normalized to Western first.  Trailing
    non-numeric characters are ignored (so ``"30px"`` -> 30).

    Examples
    --------
    >>> parse_int_safe("42")
    42
    >>> parse_int_safe("۳۰")
    30
    >>> parse_int_safe("30px")
    30
    >>> parse_int_safe("abc")
    0
    >>> parse_int_safe("abc", default=-1)
    -1
    >>> parse_int_safe(None)
    0
    >>> parse_int_safe(42)
    42
    """
    if isinstance(s, bool):
        return int(s)
    if isinstance(s, int):
        return s
    if isinstance(s, float):
        if s != s or s in (float("inf"), float("-inf")):
            return default
        return int(s)
    if not isinstance(s, str):
        return default
    # Normalize Persian/Arabic digits.
    from .. import i18n
    s = i18n.to_en_digits(s).strip()
    if not s:
        return default
    m = re.match(r"^([+-]?\d+)", s)
    if not m:
        return default
    try:
        return int(m.group(1))
    except ValueError:
        return default


def parse_float_safe(s: Any, default: float = 0.0) -> float:
    """Parse `s` as a float, returning `default` on failure.

    Persian / Arabic digits are normalized first.  Trailing non-numeric
    characters are ignored.

    Examples
    --------
    >>> parse_float_safe("3.14")
    3.14
    >>> parse_float_safe("۰/۵")
    0.0
    >>> parse_float_safe("50%")
    50.0
    >>> parse_float_safe("abc")
    0.0
    >>> parse_float_safe(None)
    0.0
    """
    if isinstance(s, bool):
        return float(s)
    if isinstance(s, (int, float)):
        if s != s:  # NaN
            return default
        return float(s)
    if not isinstance(s, str):
        return default
    from .. import i18n
    s = i18n.to_en_digits(s).strip().replace(",", "")
    if not s:
        return default
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)", s)
    if not m:
        return default
    try:
        return float(m.group(1))
    except ValueError:
        return default


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.validators"""
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

    print("=== Title ===")
    check("valid title", is_valid_title("Hello"), True)
    check("whitespace-only", is_valid_title("   "), False)
    check("empty", is_valid_title(""), False)
    check("None", is_valid_title(None), False)
    check("too long", is_valid_title("a" * 300), False)
    check("sanitize collapses ws",
          sanitize_title("  Hello   World  "), "Hello World")
    check("sanitize None", sanitize_title(None), "")
    check("sanitize truncates",
          len(sanitize_title("a" * 300)), TITLE_MAX_LEN)

    print("\n=== Notes ===")
    check("sanitize notes preserves newlines",
          sanitize_notes("  Hello\n  World  "), "Hello\n World")
    check("sanitize notes truncates",
          len(sanitize_notes("a" * 6000)), NOTES_MAX_LEN)

    print("\n=== PIN ===")
    check("valid 4-digit pin", is_valid_pin("1234"), True)
    check("valid 6-digit pin", is_valid_pin("123456"), True)
    check("too short", is_valid_pin("123"), False)
    check("too long", is_valid_pin("1234567"), False)
    check("non-digit", is_valid_pin("12ab"), False)
    check("None", is_valid_pin(None), False)

    print("\n=== ISO date ===")
    check("valid date", is_valid_iso_date("2025-03-21"), True)
    check("invalid month", is_valid_iso_date("2025-13-01"), False)
    check("invalid day", is_valid_iso_date("2025-02-30"), False)
    check("missing zero pad", is_valid_iso_date("2025-3-21"), False)
    check("datetime not date", is_valid_iso_date("2025-03-21T10:00"), False)
    check("None", is_valid_iso_date(None), False)

    print("\n=== ISO datetime ===")
    check("valid dt", is_valid_iso_datetime("2025-03-21T14:30:00"), True)
    check("valid dt Z", is_valid_iso_datetime("2025-03-21T14:30:00Z"), True)
    check("valid dt offset",
          is_valid_iso_datetime("2025-03-21T14:30:00+03:30"), True)
    check("date not dt", is_valid_iso_datetime("2025-03-21"), False)

    print("\n=== HH:MM ===")
    check("valid 14:30", is_valid_hhmm("14:30"), True)
    check("valid 00:00", is_valid_hhmm("00:00"), True)
    check("valid 23:59", is_valid_hhmm("23:59"), True)
    check("invalid 24:00", is_valid_hhmm("24:00"), False)
    check("invalid 14:60", is_valid_hhmm("14:60"), False)

    print("\n=== Color hex ===")
    check("valid #D4AF37", is_valid_color_hex("#D4AF37"), True)
    check("valid no #", is_valid_color_hex("D4AF37"), True)
    check("valid 3-digit", is_valid_color_hex("#FFF"), True)
    check("valid 8-digit", is_valid_color_hex("#FFAA2299"), True)
    check("invalid XYZ", is_valid_color_hex("XYZ"), False)

    print("\n=== Email / URL ===")
    check("valid email", is_valid_email("user@example.com"), True)
    check("valid email + tag", is_valid_email("a.b+tag@sub.example.co"), True)
    check("invalid email no @", is_valid_email("no-at-sign"), False)
    check("valid url", is_valid_url("https://example.com"), True)
    check("valid url with path",
          is_valid_url("http://example.com/path?q=1#frag"), True)
    check("invalid url", is_valid_url("not-a-url"), False)

    print("\n=== Numeric ranges ===")
    check("duration 0", is_valid_duration_min(0), True)
    check("duration 1440", is_valid_duration_min(1440), True)
    check("duration 1441", is_valid_duration_min(1441), False)
    check("duration -1", is_valid_duration_min(-1), False)
    check("duration string", is_valid_duration_min("30"), False)
    check("duration bool", is_valid_duration_min(True), False)
    check("target 1", is_valid_target_minutes(1), True)
    check("target 10000", is_valid_target_minutes(10000), True)
    check("target 0", is_valid_target_minutes(0), False)
    check("target 10001", is_valid_target_minutes(10001), False)

    print("\n=== Tags ===")
    check("normalize tags",
          sanitize_tags(["Focus", " focus ", "DEEP", "", "a" * 30]),
          ["focus", "deep", "a" * 20])
    check("dedupe", sanitize_tags(["a", "A", "b"]), ["a", "b"])
    check("limit 10", len(sanitize_tags([str(i) for i in range(20)])), 10)
    check("None", sanitize_tags(None), [])
    check("not a list", sanitize_tags("foo"), [])

    print("\n=== parse_int_safe ===")
    check("int '42'", parse_int_safe("42"), 42)
    check("int '۳۰'", parse_int_safe("۳۰"), 30)
    check("int '30px'", parse_int_safe("30px"), 30)
    check("int 'abc'", parse_int_safe("abc"), 0)
    check("int 'abc' default -1", parse_int_safe("abc", -1), -1)
    check("int None", parse_int_safe(None), 0)
    check("int 42", parse_int_safe(42), 42)
    check("int 3.7", parse_int_safe(3.7), 3)

    print("\n=== parse_float_safe ===")
    check("float '3.14'", parse_float_safe("3.14"), 3.14)
    check("float '50%'", parse_float_safe("50%"), 50.0)
    check("float 'abc'", parse_float_safe("abc"), 0.0)
    check("float None", parse_float_safe(None), 0.0)
    check("float 3.7", parse_float_safe(3.7), 3.7)
    check("float int 42", parse_float_safe(42), 42.0)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
