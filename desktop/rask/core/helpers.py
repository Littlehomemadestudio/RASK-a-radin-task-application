"""
rask.core.helpers
=================

Grab-bag of small, dependency-free utilities used throughout Rask:

  • Math: clamp, lerp, easing curves
  • Color: hex ↔ rgb, lighten / darken / mix
  • Strings: slugify, truncate, pluralize
  • Collections: chunks, dedupe, merge_dicts, deep_get / deep_set
  • Type coercion: safe_int / safe_float / safe_str
  • IDs / time: now_timestamp, uid (UUID4 hex), short_id (base36)

All functions are pure (no I/O, no globals) and tolerate ``None`` input
by returning a sensible default.
"""
from __future__ import annotations

import math
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from .. import i18n

__all__ = [
    # Math
    "clamp", "lerp",
    "ease_out_cubic", "ease_in_cubic", "ease_in_out_cubic",
    "ease_out_quint", "ease_spring",
    # Color
    "hex_to_rgb", "rgb_to_hex",
    "lighten_color", "darken_color", "mix_colors", "hex_to_rgba",
    # Strings
    "slugify", "truncate", "pluralize",
    "format_file_size",
    # Type coercion
    "safe_int", "safe_float", "safe_str",
    # Collections
    "chunks", "dedupe", "merge_dicts", "deep_get", "deep_set",
    # IDs / time
    "now_timestamp", "uid", "short_id",
]


# =============================================================================
# === Math                                                                  ===
# =============================================================================

def clamp(v: Union[int, float], lo: Union[int, float], hi: Union[int, float]) -> Union[int, float]:
    """Clamp `v` to the inclusive range ``[lo, hi]``.

    Examples
    --------
    >>> clamp(5, 0, 10)
    5
    >>> clamp(-1, 0, 10)
    0
    >>> clamp(99, 0, 10)
    10
    """
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between `a` and `b` by parameter `t` in [0, 1].

    Examples
    --------
    >>> lerp(0.0, 10.0, 0.5)
    5.0
    >>> lerp(0.0, 10.0, 0.0)
    0.0
    >>> lerp(0.0, 10.0, 1.0)
    10.0
    """
    t = clamp(t, 0.0, 1.0)
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    """Ease-out cubic curve: ``1 - (1-t)^3``.

    Fast start, slow end.  Common for entrance animations.
    """
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    """Ease-in cubic curve: ``t^3``.

    Slow start, fast end.  Common for exit animations.
    """
    t = clamp(t, 0.0, 1.0)
    return t ** 3


def ease_in_out_cubic(t: float) -> float:
    """Ease-in-out cubic curve.

    Slow at both ends, fast in the middle.
    """
    t = clamp(t, 0.0, 1.0)
    if t < 0.5:
        return 4 * t ** 3
    return 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_quint(t: float) -> float:
    """Ease-out quintic curve: ``1 - (1-t)^5``.

    Stronger slow-down than ease-out cubic — feels more "deliberate".
    """
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 5


def ease_spring(t: float) -> float:
    """Damped spring easing — overshoots ~once then settles.

    Implements: ``1 - cos(t * π * 1.7) * (1 - t)``.

    Use sparingly — overshoot can feel cheap if overused.
    """
    t = clamp(t, 0.0, 1.0)
    return 1 - math.cos(t * math.pi * 1.7) * (1 - t)


# =============================================================================
# === Color                                                                 ===
# =============================================================================

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Parse a hex color string into an ``(r, g, b)`` tuple (0..255 each).

    Accepts 3, 6, or 8 hex digits with an optional leading ``#``.

    Examples
    --------
    >>> hex_to_rgb("#D4AF37")
    (212, 175, 55)
    >>> hex_to_rgb("FFF")
    (255, 255, 255)
    >>> hex_to_rgb("")
    (0, 0, 0)
    """
    if not isinstance(hex_str, str) or not hex_str:
        return (0, 0, 0)
    s = hex_str.lstrip("#").strip()
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) not in (6, 8) or not all(c in "0123456789abcdefABCDEF" for c in s):
        return (0, 0, 0)
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (r, g, b)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert an ``(r, g, b)`` tuple to a lowercase ``#rrggbb`` string.

    Examples
    --------
    >>> rgb_to_hex((212, 175, 55))
    '#d4af37'
    >>> rgb_to_hex((0, 0, 0))
    '#000000'
    >>> rgb_to_hex((255, 255, 255))
    '#ffffff'
    """
    if not isinstance(rgb, (tuple, list)) or len(rgb) < 3:
        return "#000000"
    r = int(clamp(rgb[0], 0, 255))
    g = int(clamp(rgb[1], 0, 255))
    b = int(clamp(rgb[2], 0, 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix_channel(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * clamp(t, 0.0, 1.0)))


def lighten_color(hex_str: str, amount: float) -> str:
    """Return a hex color mixed toward white by `amount` in [0, 1].

    Examples
    --------
    >>> lighten_color("#000000", 1.0)
    '#ffffff'
    >>> lighten_color("#808080", 0.5)
    '#c0c0c0'
    """
    r, g, b = hex_to_rgb(hex_str)
    return rgb_to_hex((_mix_channel(r, 255, amount),
                       _mix_channel(g, 255, amount),
                       _mix_channel(b, 255, amount)))


def darken_color(hex_str: str, amount: float) -> str:
    """Return a hex color mixed toward black by `amount` in [0, 1].

    Examples
    --------
    >>> darken_color("#ffffff", 1.0)
    '#000000'
    >>> darken_color("#808080", 0.5)
    '#404040'
    """
    r, g, b = hex_to_rgb(hex_str)
    return rgb_to_hex((_mix_channel(r, 0, amount),
                       _mix_channel(g, 0, amount),
                       _mix_channel(b, 0, amount)))


def mix_colors(c1: str, c2: str, t: float) -> str:
    """Linearly mix two hex colors by parameter `t` in [0, 1].

    ``t=0`` returns ``c1``, ``t=1`` returns ``c2``.

    Examples
    --------
    >>> mix_colors("#000000", "#ffffff", 0.0)
    '#000000'
    >>> mix_colors("#000000", "#ffffff", 1.0)
    '#ffffff'
    >>> mix_colors("#000000", "#ffffff", 0.5)
    '#808080'
    """
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((_mix_channel(r1, r2, t),
                       _mix_channel(g1, g2, t),
                       _mix_channel(b1, b2, t)))


def hex_to_rgba(hex_str: str, alpha: float) -> str:
    """Return a CSS ``rgba(r, g, b, a)`` string for a hex color.

    Examples
    --------
    >>> hex_to_rgba("#D4AF37", 0.5)
    'rgba(212, 175, 55, 0.5)'
    >>> hex_to_rgba("#000000", 1.0)
    'rgba(0, 0, 0, 1)'
    """
    r, g, b = hex_to_rgb(hex_str)
    alpha = clamp(alpha, 0.0, 1.0)
    # Trim trailing zeros for cleaner output (1.0 -> "1", 0.5 -> "0.5").
    if alpha == int(alpha):
        a_str = str(int(alpha))
    else:
        a_str = f"{alpha:.3f}".rstrip("0").rstrip(".")
    return f"rgba({r}, {g}, {b}, {a_str})"


# =============================================================================
# === Strings                                                                ===
# =============================================================================

_SLUG_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_WS_RE = re.compile(r"[-\s]+")


def slugify(s: Any, separator: str = "-") -> str:
    """Convert `s` to a URL-friendly slug.

    Lowercases, strips diacritics from ASCII characters, replaces
    whitespace and runs of separator with a single separator.

    Examples
    --------
    >>> slugify("Hello World!")
    'hello-world'
    >>> slugify("  Multiple   Spaces  ")
    'multiple-spaces'
    >>> slugify("Rask — Time, Refined")
    'rask-time-refined'
    """
    if not isinstance(s, str):
        return ""
    s = unicodedata_normalize(s)
    s = s.lower().strip()
    s = _SLUG_RE.sub("", s)
    s = _WS_RE.sub(separator, s)
    if separator:
        s = s.strip(separator)
    return s


def unicodedata_normalize(s: str) -> str:
    """NFKD-normalize and drop combining marks (best-effort ASCII fold)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    out = []
    for ch in s:
        if unicodedata.category(ch) != "Mn":
            out.append(ch)
    return "".join(out)


def truncate(s: Any, n: int, suffix: str = "…") -> str:
    """Truncate `s` to at most `n` characters, appending `suffix` if cut.

    Examples
    --------
    >>> truncate("Hello World", 5)
    'Hell…'
    >>> truncate("Hi", 5)
    'Hi'
    >>> truncate(None, 5)
    ''
    """
    if not isinstance(s, str):
        return ""
    if n < 0:
        return ""
    if len(s) <= n:
        return s
    if n <= len(suffix):
        return suffix[:n]
    return s[: n - len(suffix)] + suffix


def pluralize(n: int, singular: str, plural: Optional[str] = None) -> str:
    """Return ``singular`` if ``n == 1`` else ``plural``.

    If `plural` is ``None``, the English ``"s`` suffix is appended.

    Examples
    --------
    >>> pluralize(1, "minute")
    '1 minute'
    >>> pluralize(5, "minute")
    '5 minutes'
    >>> pluralize(2, "child", "children")
    '2 children'
    """
    if plural is None:
        plural = singular + "s"
    word = singular if n == 1 else plural
    return f"{n} {word}"


# File-size suffixes (SI units).
_SIZE_SUFFIXES: Tuple[str, ...] = ("B", "KB", "MB", "GB", "TB", "PB")


def format_file_size(num_bytes: int, lang: str = "fa") -> str:
    """Format a byte count as a localized human-readable size string.

    Uses SI units (1 KB = 1000 bytes).  Returns ``"۰ بایت"`` / ``"0 B"``
    for non-positive input.

    Examples
    --------
    >>> format_file_size(0, "en")
    '0 B'
    >>> format_file_size(1500, "en")
    '1.5 KB'
    >>> format_file_size(1024 * 1024, "en")
    '1 MB'
    >>> format_file_size(1500, "fa")
    '۱.۵ کیلوبایت'
    """
    if not isinstance(num_bytes, (int, float)) or num_bytes < 0:
        num_bytes = 0
    size = float(num_bytes)
    idx = 0
    while size >= 1000 and idx < len(_SIZE_SUFFIXES) - 1:
        size /= 1000.0
        idx += 1
    # Format with one decimal place if there's a fractional part after
    # rounding, otherwise as an integer.  This gives "1 KB" for exactly
    # 1000 bytes but "1.5 KB" for 1500 bytes.
    rounded = round(size, 1)
    if rounded == int(rounded):
        num_str = f"{int(rounded)}"
    else:
        num_str = f"{rounded:.1f}"
    if lang == "fa":
        fa_suffixes = ("بایت", "کیلوبایت", "مگابایت", "گیگابایت", "ترابایت", "پتابایت")
        suffix = fa_suffixes[idx]
        return f"{i18n.to_fa_digits(num_str)} {suffix}"
    return f"{num_str} {_SIZE_SUFFIXES[idx]}"


# =============================================================================
# === Type coercion                                                         ===
# =============================================================================

def safe_int(v: Any, default: int = 0) -> int:
    """Coerce `v` to ``int``; return `default` on failure.

    Equivalent to :func:`rask.core.validators.parse_int_safe` — kept
    here as a shorter alias for ergonomic inline use.
    """
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return default
        return int(v)
    if isinstance(v, str):
        from . import validators
        return validators.parse_int_safe(v, default)
    return default


def safe_float(v: Any, default: float = 0.0) -> float:
    """Coerce `v` to ``float``; return `default` on failure."""
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        if v != v:
            return default
        return float(v)
    if isinstance(v, str):
        from . import validators
        return validators.parse_float_safe(v, default)
    return default


def safe_str(v: Any, default: str = "") -> str:
    """Coerce `v` to ``str``; return `default` for ``None``.

    Examples
    --------
    >>> safe_str(42)
    '42'
    >>> safe_str(None)
    ''
    >>> safe_str(None, 'n/a')
    'n/a'
    >>> safe_str("hello")
    'hello'
    """
    if v is None:
        return default
    if isinstance(v, str):
        return v
    return str(v)


# =============================================================================
# === Collections                                                           ===
# =============================================================================

def chunks(lst: Sequence[Any], n: int) -> Iterator[List[Any]]:
    """Yield successive n-sized chunks from `lst`.

    The final chunk may be shorter than `n`.  Yields lists (not tuples)
    so callers can mutate.

    Examples
    --------
    >>> list(chunks([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    >>> list(chunks([], 3))
    []
    """
    if n < 1:
        raise ValueError(f"chunk size must be ≥ 1, got {n}")
    for i in range(0, len(lst), n):
        yield list(lst[i:i + n])


def dedupe(lst: Iterable[Any]) -> List[Any]:
    """Return a list with duplicates removed, preserving first-occurrence order.

    Examples
    --------
    >>> dedupe([1, 2, 2, 3, 1, 4])
    [1, 2, 3, 4]
    >>> dedupe(["a", "b", "a", "c"])
    ['a', 'b', 'c']
    """
    seen: set = set()
    out: List[Any] = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def merge_dicts(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge multiple dicts; later keys override earlier.

    Examples
    --------
    >>> merge_dicts({"a": 1}, {"b": 2}, {"a": 3, "c": 4})
    {'a': 3, 'b': 2, 'c': 4}
    >>> merge_dicts(None, {"x": 1}, None)
    {'x': 1}
    """
    out: Dict[str, Any] = {}
    for d in dicts:
        if isinstance(d, dict):
            out.update(d)
    return out


def deep_get(d: Any, path: str, default: Any = None) -> Any:
    """Traverse a nested dict by dotted `path`; return `default` on miss.

    Examples
    --------
    >>> deep_get({"a": {"b": {"c": 42}}}, "a.b.c")
    42
    >>> deep_get({"a": {}}, "a.b.c", "default")
    'default'
    >>> deep_get(None, "a.b")
    """
    if not isinstance(path, str) or not path:
        return default
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def deep_set(d: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """Set a value in a nested dict by dotted `path`, creating dicts as needed.

    Mutates and returns `d` for convenience.

    Examples
    --------
    >>> d = {}
    >>> deep_set(d, "a.b.c", 42)
    {'a': {'b': {'c': 42}}}
    >>> deep_set(d, "a.b.d", "hi")["a"]["b"]["d"]
    'hi'
    """
    if not isinstance(d, dict):
        raise TypeError(f"deep_set requires a dict, got {type(d).__name__}")
    if not isinstance(path, str) or not path:
        return d
    parts = path.split(".")
    cur = d
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value
    return d


# =============================================================================
# === IDs / time                                                            ===
# =============================================================================

def now_timestamp() -> int:
    """Return the current Unix time in milliseconds."""
    return int(time.time() * 1000)


def uid() -> str:
    """Return a random 32-character hex string (UUID4, no dashes).

    Example
    -------
    >>> len(uid())
    32
    """
    return uuid.uuid4().hex


_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def short_id(length: int = 8) -> str:
    """Return a short random base36 ID (default 8 chars).

    Uses ``os.urandom`` for cryptographic-quality randomness.  With the
    default length of 8, the collision space is ~2.8 trillion — fine
    for UI element IDs and per-session tokens.

    Examples
    --------
    >>> len(short_id())
    8
    >>> len(short_id(12))
    12
    """
    if length < 1:
        raise ValueError(f"length must be ≥ 1, got {length}")
    # Read enough bytes to cover `length` chars (5 bits per char ≈ 1.6
    # bits per byte; we read 2x for safety and trim).
    n_bytes = max(8, length * 2)
    raw = os.urandom(n_bytes)
    n = int.from_bytes(raw, "big")
    out = []
    while len(out) < length:
        out.append(_BASE36_ALPHABET[n % 36])
        n //= 36
    return "".join(out)


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.helpers"""
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

    print("=== Math ===")
    check("clamp mid", clamp(5, 0, 10), 5)
    check("clamp low", clamp(-1, 0, 10), 0)
    check("clamp high", clamp(99, 0, 10), 10)
    check("lerp 0.5", lerp(0, 10, 0.5), 5.0)
    check("lerp 0", lerp(0, 10, 0), 0.0)
    check("lerp 1", lerp(0, 10, 1), 10.0)
    check("ease_out_cubic(0)", ease_out_cubic(0), 0.0)
    check("ease_out_cubic(1)", ease_out_cubic(1), 1.0)
    check("ease_in_out_cubic(0.5)", round(ease_in_out_cubic(0.5), 3), 0.5)
    check("ease_spring 0..1.5", 0 <= ease_spring(0.5) <= 1.5, True)

    print("\n=== Color ===")
    check("hex_to_rgb 6-digit", hex_to_rgb("#D4AF37"), (212, 175, 55))
    check("hex_to_rgb 3-digit", hex_to_rgb("#FFF"), (255, 255, 255))
    check("hex_to_rgb empty", hex_to_rgb(""), (0, 0, 0))
    check("rgb_to_hex", rgb_to_hex((212, 175, 55)), "#d4af37")
    check("lighten black to white", lighten_color("#000000", 1.0), "#ffffff")
    check("darken white to black", darken_color("#ffffff", 1.0), "#000000")
    check("mix 0", mix_colors("#000000", "#ffffff", 0.0), "#000000")
    check("mix 1", mix_colors("#000000", "#ffffff", 1.0), "#ffffff")
    check("mix 0.5", mix_colors("#000000", "#ffffff", 0.5), "#808080")
    check("hex_to_rgba 0.5", hex_to_rgba("#D4AF37", 0.5),
          "rgba(212, 175, 55, 0.5)")
    check("hex_to_rgba 1.0", hex_to_rgba("#000000", 1.0),
          "rgba(0, 0, 0, 1)")

    print("\n=== Strings ===")
    check("slugify basic", slugify("Hello World!"), "hello-world")
    check("slugify multi ws", slugify("  Multiple   Spaces  "), "multiple-spaces")
    check("truncate short", truncate("Hi", 5), "Hi")
    check("truncate long", truncate("Hello World", 5), "Hell…")
    check("truncate None", truncate(None, 5), "")
    check("pluralize 1", pluralize(1, "minute"), "1 minute")
    check("pluralize 5", pluralize(5, "minute"), "5 minutes")
    check("pluralize custom", pluralize(2, "child", "children"), "2 children")
    check("format_file_size 0 en", format_file_size(0, "en"), "0 B")
    check("format_file_size 1500 en", format_file_size(1500, "en"), "1.5 KB")
    check("format_file_size 1MB en", format_file_size(1024 * 1024, "en"), "1 MB")

    print("\n=== Type coercion ===")
    check("safe_int '42'", safe_int("42"), 42)
    check("safe_int None", safe_int(None, -1), -1)
    check("safe_int 3.7", safe_int(3.7), 3)
    check("safe_float '3.14'", safe_float("3.14"), 3.14)
    check("safe_float None", safe_float(None, -1.0), -1.0)
    check("safe_str 42", safe_str(42), "42")
    check("safe_str None default", safe_str(None), "")
    check("safe_str None custom", safe_str(None, "n/a"), "n/a")

    print("\n=== Collections ===")
    check("chunks", list(chunks([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])
    check("chunks empty", list(chunks([], 3)), [])
    check("dedupe ints", dedupe([1, 2, 2, 3, 1, 4]), [1, 2, 3, 4])
    check("dedupe strings", dedupe(["a", "b", "a", "c"]), ["a", "b", "c"])
    check("merge_dicts",
          merge_dicts({"a": 1}, {"b": 2}, {"a": 3, "c": 4}),
          {"a": 3, "b": 2, "c": 4})
    check("merge_dicts with None",
          merge_dicts(None, {"x": 1}, None), {"x": 1})
    check("deep_get hit", deep_get({"a": {"b": {"c": 42}}}, "a.b.c"), 42)
    check("deep_get miss", deep_get({"a": {}}, "a.b.c", "default"), "default")
    check("deep_get None", deep_get(None, "a.b"), None)
    d: dict = {}
    deep_set(d, "a.b.c", 42)
    check("deep_set", d, {"a": {"b": {"c": 42}}})
    deep_set(d, "a.b.d", "hi")
    check("deep_set second", d["a"]["b"]["d"], "hi")

    print("\n=== IDs / time ===")
    check("now_timestamp is int", isinstance(now_timestamp(), int), True)
    check("uid length", len(uid()), 32)
    check("short_id default length", len(short_id()), 8)
    check("short_id custom length", len(short_id(12)), 12)
    sid1 = short_id()
    sid2 = short_id()
    check("short_id unique", sid1 != sid2, True)
    # All chars in base36 alphabet.
    check("short_id base36",
          all(c in _BASE36_ALPHABET for c in short_id(20)), True)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
