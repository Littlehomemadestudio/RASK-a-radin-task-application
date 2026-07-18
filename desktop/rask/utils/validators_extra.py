"""
rask.utils.validators_extra
===========================

Extra input validators beyond :mod:`rask.core.validators`.

Functions
---------

  • ``is_valid_color_name(s)``      — CSS color name
  • ``is_valid_hex_color(s)``       — strict (#RRGGBB or #RGB)
  • ``is_valid_rgb_tuple(t)``       — (r, g, b) each 0..255
  • ``is_valid_iso_week(s)``        — "2025-W32"
  • ``is_valid_iso_month(s)``       — "2025-07"
  • ``is_valid_cron(s)``            — basic cron syntax check
  • ``is_valid_recurrence(s)``      — "FREQ=DAILY;INTERVAL=2"
  • ``is_valid_phone(s)``           — international phone format
  • ``is_valid_username(s)``        — alphanumeric + underscore, 3..20 chars
  • ``is_valid_password(s)``        — min 8 chars, mixed case, digit
  • ``password_strength(s)``        — score 0..4
  • ``sanitize_html(s)``            — strip dangerous tags
  • ``sanitize_sql_identifier(s)``  — only allow alphanumeric + underscore

Example
-------

    >>> from rask.utils.validators_extra import is_valid_hex_color
    >>> is_valid_hex_color("#D4AF37")
    True
    >>> is_valid_hex_color("D4AF37")
    False
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "is_valid_color_name",
    "is_valid_hex_color",
    "is_valid_rgb_tuple",
    "is_valid_iso_week",
    "is_valid_iso_month",
    "is_valid_cron",
    "is_valid_recurrence",
    "is_valid_phone",
    "is_valid_username",
    "is_valid_password",
    "password_strength",
    "sanitize_html",
    "sanitize_sql_identifier",
]


# =============================================================================
# === Color validators                                                       ===
# =============================================================================

#: Set of valid CSS3 color names.
CSS_COLOR_NAMES: set = {
    "aliceblue", "antiquewhite", "aqua", "aquamarine", "azure", "beige",
    "bisque", "black", "blanchedalmond", "blue", "blueviolet", "brown",
    "burlywood", "cadetblue", "chartreuse", "chocolate", "coral",
    "cornflowerblue", "cornsilk", "crimson", "cyan", "darkblue",
    "darkcyan", "darkgoldenrod", "darkgray", "darkgreen", "darkgrey",
    "darkkhaki", "darkmagenta", "darkolivegreen", "darkorange",
    "darkorchid", "darkred", "darksalmon", "darkseagreen", "darkslateblue",
    "darkslategray", "darkslategrey", "darkturquoise", "darkviolet",
    "deeppink", "deepskyblue", "dimgray", "dimgrey", "dodgerblue",
    "firebrick", "floralwhite", "forestgreen", "fuchsia", "gainsboro",
    "ghostwhite", "gold", "goldenrod", "gray", "green", "greenyellow",
    "grey", "honeydew", "hotpink", "indianred", "indigo", "ivory",
    "khaki", "lavender", "lavenderblush", "lawngreen", "lemonchiffon",
    "lightblue", "lightcoral", "lightcyan", "lightgoldenrodyellow",
    "lightgray", "lightgreen", "lightgrey", "lightpink", "lightsalmon",
    "lightseagreen", "lightskyblue", "lightslategray", "lightslategrey",
    "lightsteelblue", "lightyellow", "lime", "limegreen", "linen",
    "magenta", "maroon", "mediumaquamarine", "mediumblue",
    "mediumorchid", "mediumpurple", "mediumseagreen", "mediumslateblue",
    "mediumspringgreen", "mediumturquoise", "mediumvioletred",
    "midnightblue", "mintcream", "mistyrose", "moccasin", "navajowhite",
    "navy", "oldlace", "olive", "olivedrab", "orange", "orangered",
    "orchid", "palegoldenrod", "palegreen", "paleturquoise",
    "palevioletred", "papayawhip", "peachpuff", "peru", "pink", "plum",
    "powderblue", "purple", "rebeccapurple", "red", "rosybrown",
    "royalblue", "saddlebrown", "salmon", "sandybrown", "seagreen",
    "seashell", "sienna", "silver", "skyblue", "slateblue", "slategray",
    "slategrey", "snow", "springgreen", "steelblue", "tan", "teal",
    "thistle", "tomato", "turquoise", "violet", "wheat", "white",
    "whitesmoke", "yellow", "yellowgreen", "transparent",
}


def is_valid_color_name(s: str) -> bool:
    """Return True if `s` is a valid CSS3 color name (case-insensitive)."""
    if not isinstance(s, str) or not s:
        return False
    return s.lower() in CSS_COLOR_NAMES


def is_valid_hex_color(s: str) -> bool:
    """Return True if `s` is a valid hex color (#RRGGBB or #RGB, case-insensitive).

    Strict: requires the leading '#'.
    """
    if not isinstance(s, str) or not s:
        return False
    return bool(re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", s))


def is_valid_rgb_tuple(t: object) -> bool:
    """Return True if `t` is a (r, g, b) tuple with each value 0..255."""
    if not isinstance(t, (tuple, list)) or len(t) != 3:
        return False
    for v in t:
        if not isinstance(v, int) or isinstance(v, bool):
            return False
        if v < 0 or v > 255:
            return False
    return True


# =============================================================================
# === Date / time validators                                                 ===
# =============================================================================

def is_valid_iso_week(s: str) -> bool:
    """Return True if `s` matches "YYYY-Www" (e.g. "2025-W32")."""
    if not isinstance(s, str) or not s:
        return False
    return bool(re.match(r"^\d{4}-W([0-4]\d|5[0-3])$", s))


def is_valid_iso_month(s: str) -> bool:
    """Return True if `s` matches "YYYY-MM" (e.g. "2025-07")."""
    if not isinstance(s, str) or not s:
        return False
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", s):
        return False
    return True


# =============================================================================
# === Cron / recurrence                                                      ===
# =============================================================================

def is_valid_cron(s: str) -> bool:
    """Return True if `s` looks like a basic cron expression.

    Checks for 5 whitespace-separated fields, each either ``*`` or a
    number/range/list.  Does NOT validate range semantics (e.g. 0..23
    for hours) — only syntax.
    """
    if not isinstance(s, str) or not s:
        return False
    parts = s.split()
    if len(parts) != 5:
        return False
    # Each field must match: * | number | number-number | number,number | */number
    field_re = re.compile(
        r"^(\*|\d+(-\d+)?(,\d+(-\d+)?)*|\*\/\d+|\d+\/\d+)$"
    )
    for p in parts:
        if not field_re.match(p):
            return False
    return True


def is_valid_recurrence(s: str) -> bool:
    """Return True if `s` is a valid RFC 5545-style recurrence rule.

    Examples:
      "FREQ=DAILY;INTERVAL=2"
      "FREQ=WEEKLY;BYDAY=MO,WE,FR"
      "FREQ=MONTHLY;BYMONTHDAY=15"
    """
    if not isinstance(s, str) or not s:
        return False
    parts = s.split(";")
    if not parts:
        return False
    has_freq = False
    valid_keys = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY",
                   "BYMONTHDAY", "BYMONTH", "BYWEEKNO", "BYYEARDAY",
                   "WKST"}
    for p in parts:
        if "=" not in p:
            return False
        key, _ = p.split("=", 1)
        if key not in valid_keys:
            return False
        if key == "FREQ":
            has_freq = True
    return has_freq


# =============================================================================
# === Phone / username / password                                            ===
# =============================================================================

def is_valid_phone(s: str) -> bool:
    """Return True if `s` is a valid international phone number.

    Accepts:
      • +<country><number> (e.g. +989121234567)
      • 00<country><number> (e.g. 00989121234567)

    Total digits must be 7..15 (per E.164).
    """
    if not isinstance(s, str) or not s:
        return False
    s = s.strip()
    if s.startswith("+"):
        digits = s[1:]
    elif s.startswith("00"):
        digits = s[2:]
    else:
        return False
    if not digits.isdigit():
        return False
    return 7 <= len(digits) <= 15


def is_valid_username(s: str) -> bool:
    """Return True if `s` is a valid username (3..20 chars, alphanumeric + _)."""
    if not isinstance(s, str) or not s:
        return False
    if len(s) < 3 or len(s) > 20:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_]+$", s))


def is_valid_password(s: str) -> bool:
    """Return True if `s` is a valid password.

    Requirements:
      • At least 8 characters
      • At least one uppercase letter
      • At least one lowercase letter
      • At least one digit
    """
    if not isinstance(s, str) or len(s) < 8:
        return False
    if not re.search(r"[A-Z]", s):
        return False
    if not re.search(r"[a-z]", s):
        return False
    if not re.search(r"\d", s):
        return False
    return True


def password_strength(s: str) -> int:
    """Return a 0..4 password strength score.

    0: very weak (under 8 chars or no complexity)
    1: weak (8+ chars, only one category)
    2: fair (8+ chars, two categories)
    3: good (8+ chars, three categories)
    4: strong (12+ chars, all four categories: upper, lower, digit, special)
    """
    if not isinstance(s, str) or not s:
        return 0
    score = 0
    if len(s) >= 8:
        score += 1
    if len(s) >= 12:
        score += 1
    has_upper = bool(re.search(r"[A-Z]", s))
    has_lower = bool(re.search(r"[a-z]", s))
    has_digit = bool(re.search(r"\d", s))
    has_special = bool(re.search(r"[^a-zA-Z0-9]", s))
    categories = sum([has_upper, has_lower, has_digit, has_special])
    if categories >= 2:
        score += 1
    if categories >= 3:
        score += 1
    if categories == 4 and len(s) >= 12:
        score += 1
    return min(4, score)


# =============================================================================
# === Sanitizers                                                             ===
# =============================================================================

#: HTML tags that are stripped entirely (with their content).
_DANGEROUS_TAGS: set = {
    "script", "iframe", "object", "embed", "applet", "form",
    "input", "button", "textarea", "select", "option", "link",
    "meta", "base", "style",
}


def sanitize_html(s: str) -> str:
    """Strip dangerous HTML tags and attributes from `s`.

    Removes ``<script>``, ``<iframe>``, ``<object>``, ``<embed>``,
    ``<form>``, etc. entirely (with their content).  Also strips
    ``javascript:`` URLs and event-handler attributes (``onclick``,
    ``onload``, etc.).

    Returns the sanitized HTML string.  This is a *basic* sanitizer —
    for production use, consider a proper library like ``bleach``.
    """
    if not isinstance(s, str) or not s:
        return ""
    out = s
    # Remove dangerous tags and their content.
    for tag in _DANGEROUS_TAGS:
        out = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            "",
            out,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # Also remove standalone (self-closing) versions.
        out = re.sub(
            rf"<{tag}\b[^>]*/?>",
            "",
            out,
            flags=re.IGNORECASE,
        )
    # Remove event-handler attributes.
    out = re.sub(
        r'\s+on\w+\s*=\s*"[^"]*"',
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\s+on\w+\s*=\s*'[^']*'",
        "",
        out,
        flags=re.IGNORECASE,
    )
    # Remove javascript: URLs.
    out = re.sub(
        r'(href|src)\s*=\s*"(javascript:[^"]*)"',
        r'\1=""',
        out,
        flags=re.IGNORECASE,
    )
    return out


def sanitize_sql_identifier(s: str) -> str:
    """Sanitize a string for use as a SQL identifier.

    Only allows alphanumeric characters and underscores.  Returns the
    cleaned string.  If the input is empty or has no valid chars,
    returns ``"_"``.
    """
    if not isinstance(s, str) or not s:
        return "_"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", s)
    if not cleaned:
        return "_"
    # Identifiers shouldn't start with a digit.
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.validators_extra``."""
    tests = [
        ("is_valid_color_name", is_valid_color_name, "gold", True),
        ("is_valid_color_name", is_valid_color_name, "notacolor", False),
        ("is_valid_hex_color", is_valid_hex_color, "#D4AF37", True),
        ("is_valid_hex_color", is_valid_hex_color, "D4AF37", False),
        ("is_valid_rgb_tuple", is_valid_rgb_tuple, (212, 175, 55), True),
        ("is_valid_rgb_tuple", is_valid_rgb_tuple, (256, 0, 0), False),
        ("is_valid_iso_week", is_valid_iso_week, "2025-W32", True),
        ("is_valid_iso_month", is_valid_iso_month, "2025-07", True),
        ("is_valid_cron", is_valid_cron, "0 9 * * *", True),
        ("is_valid_recurrence", is_valid_recurrence, "FREQ=DAILY;INTERVAL=2", True),
        ("is_valid_phone", is_valid_phone, "+989121234567", True),
        ("is_valid_username", is_valid_username, "alice_99", True),
        ("is_valid_password", is_valid_password, "Abcdef1!", True),
        ("password_strength", password_strength, "Abcdef1!", 3),
    ]
    passed = 0
    failed = 0
    for name, fn, inp, expected in tests:
        got = fn(inp)
        if got == expected:
            print(f"  OK   {name}({inp!r}) = {got!r}")
            passed += 1
        else:
            print(f"  FAIL {name}({inp!r}) = {got!r}, expected {expected!r}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_main())
