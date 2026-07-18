"""
rask.utils.cli_helpers
======================

Pretty-printing helpers for command-line scripts.

Functions
---------

  • ``format_table(rows, headers, lang)`` — pretty-print ASCII table
  • ``format_tree(nodes, lang)`` — tree-print hierarchy
  • ``format_json(obj, indent)`` — pretty JSON (with Persian digits option)
  • ``format_yaml(obj)`` — basic YAML formatter
  • ``progress_bar(current, total, width)`` — text progress bar
  • ``spinner(message)`` — context manager with rotating spinner
  • ``colorize(text, color)`` — ANSI color codes
  • ``confirm(message, default)`` — interactive Y/N
  • ``prompt(message, default)`` — interactive text input
  • ``select(message, options, default)`` — interactive select

Example
-------

    >>> from rask.utils.cli_helpers import format_table, colorize
    >>> print(format_table(
    ...     [["Alice", "30"], ["Bob", "25"]],
    ...     ["Name", "Age"],
    ... ))
    Name   | Age
    -------|----
    Alice  | 30
    Bob    | 25
"""
from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, TextIO

__all__ = [
    "format_table",
    "format_tree",
    "format_json",
    "format_yaml",
    "progress_bar",
    "spinner",
    "colorize",
    "confirm",
    "prompt",
    "select",
    "supports_color",
]


# =============================================================================
# === ANSI color codes                                                       ===
# =============================================================================

#: ANSI escape codes for common colors.
ANSI_COLORS: Dict[str, str] = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "gold": "\033[93m",  # bright yellow (closest to gold)
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
}


def supports_color(stream: Optional[TextIO] = None) -> bool:
    """Return True if the given stream supports ANSI color.

    Defaults to checking ``sys.stdout``.  Returns False if not a TTY.
    """
    stream = stream or sys.stdout
    try:
        return bool(getattr(stream, "isatty", lambda: False)())
    except Exception:  # noqa: BLE001
        return False


def colorize(text: str, color: str) -> str:
    """Wrap `text` in ANSI color codes for `color`.

    If stdout is not a TTY, returns the text unchanged.
    """
    if not supports_color():
        return text
    code = ANSI_COLORS.get(color, "")
    if not code:
        return text
    return f"{code}{text}{ANSI_COLORS['reset']}"


# =============================================================================
# === Table formatter                                                        ===
# =============================================================================

def format_table(
    rows: Sequence[Sequence[Any]],
    headers: Optional[Sequence[str]] = None,
    lang: str = "fa",
    *,
    separator: str = " | ",
) -> str:
    """Format a list of rows as an ASCII table.

    Parameters
    ----------
    rows
        List of row tuples / lists.
    headers
        Optional column headers.
    lang
        ``"fa"`` to use Persian digits, ``"en"`` otherwise.
    separator
        Column separator (default " | ").

    Returns
    -------
    str
        The formatted table.
    """
    if not rows and not headers:
        return ""
    # Compute column count.
    n_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if n_cols == 0:
        return ""

    # Coerce all rows to strings.
    str_rows: List[List[str]] = []
    for row in rows:
        str_row = [str(v) if v is not None else "" for v in row]
        # Pad to n_cols.
        while len(str_row) < n_cols:
            str_row.append("")
        str_rows.append(str_row[:n_cols])

    # Compute column widths.
    widths = [0] * n_cols
    if headers:
        for i, h in enumerate(headers):
            widths[i] = max(widths[i], len(str(h)))
    for row in str_rows:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(v))

    # Build lines.
    lines: List[str] = []
    if headers:
        cells = [str(h).ljust(widths[i]) for i, h in enumerate(headers)]
        lines.append(separator.join(cells))
        # Separator line.
        sep_cells = ["-" * widths[i] for i in range(n_cols)]
        lines.append("-+-".join(sep_cells))
    for row in str_rows:
        cells = [v.ljust(widths[i]) for i, v in enumerate(row)]
        lines.append(separator.join(cells))

    result = "\n".join(lines)
    if lang == "fa":
        # Convert digits to Persian.
        result = _to_fa_digits(result)
    return result


# =============================================================================
# === Tree formatter                                                         ===
# =============================================================================

def format_tree(
    nodes: Sequence[Dict[str, Any]],
    lang: str = "fa",
    *,
    label_key: str = "label",
    children_key: str = "children",
    indent: str = "  ",
) -> str:
    """Format a hierarchical list of nodes as an ASCII tree.

    Each node is a dict with a ``label_key`` (default "label") and an
    optional ``children_key`` (default "children") containing sub-nodes.

    Example::

        [
            {"label": "Root", "children": [
                {"label": "Child A"},
                {"label": "Child B", "children": [
                    {"label": "Grandchild"},
                ]},
            ]},
        ]
    """
    if not nodes:
        return ""
    lines: List[str] = []

    def _render(node: Dict[str, Any], prefix: str, is_last: bool) -> None:
        label = str(node.get(label_key, ""))
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{label}")
        children = node.get(children_key) or []
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(children):
            _render(child, new_prefix, i == len(children) - 1)

    for i, node in enumerate(nodes):
        _render(node, "", i == len(nodes) - 1)
    result = "\n".join(lines)
    if lang == "fa":
        result = _to_fa_digits(result)
    return result


# =============================================================================
# === JSON / YAML formatters                                                 ===
# =============================================================================

def format_json(obj: Any, indent: int = 2, *, persian_digits: bool = False) -> str:
    """Pretty-print `obj` as JSON."""
    s = json.dumps(obj, indent=indent, ensure_ascii=False, default=str)
    if persian_digits:
        s = _to_fa_digits(s)
    return s


def format_yaml(obj: Any, *, indent: int = 2) -> str:
    """Format `obj` as a basic YAML string.

    Supports dicts, lists, scalars.  Does NOT support all YAML features
    (anchors, multi-line strings, etc.) — for full YAML, use ``pyyaml``.
    """
    lines: List[str] = []

    def _render(value: Any, depth: int) -> None:
        prefix = " " * (depth * indent)
        if isinstance(value, dict):
            if not value:
                lines.append(f"{prefix}{{}}")
                return
            for k, v in value.items():
                if isinstance(v, (dict, list)) and v:
                    lines.append(f"{prefix}{k}:")
                    _render(v, depth + 1)
                else:
                    lines.append(f"{prefix}{k}: {_scalar(v)}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}[]")
                return
            for item in value:
                if isinstance(item, (dict, list)) and item:
                    lines.append(f"{prefix}-")
                    _render(item, depth + 1)
                else:
                    lines.append(f"{prefix}- {_scalar(item)}")
        else:
            lines.append(f"{prefix}{_scalar(value)}")

    def _scalar(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v)
        if any(c in s for c in [":", "#", "-", "\n", "\""]):
            return f'"{s}"'
        return s

    _render(obj, 0)
    return "\n".join(lines)


# =============================================================================
# === Progress bar                                                           ===
# =============================================================================

def progress_bar(
    current: int,
    total: int,
    width: int = 40,
    *,
    fill: str = "█",
    empty: str = "░",
) -> str:
    """Return a text progress bar string.

    Example::

        [████████░░░░░░░░░░░░░░░░░░░░░░] 25%

    Call in a loop, printing with ``\r`` to update in place::

        for i in range(n):
            print(f"\r{progress_bar(i, n)}", end="")
        print()
    """
    if total <= 0:
        return f"[{empty * width}] 0%"
    pct = min(1.0, current / total)
    filled = int(pct * width)
    bar = fill * filled + empty * (width - filled)
    pct_str = f"{int(pct * 100)}%"
    return f"[{bar}] {pct_str}"


# =============================================================================
# === Spinner                                                                ===
# =============================================================================

@contextmanager
def spinner(message: str, *, stream: Optional[TextIO] = None) -> Iterator[None]:
    """Context manager that displays a rotating spinner with `message`.

    Example::

        with spinner("Loading..."):
            time.sleep(2)  # spinner animates during this
    """
    stream = stream or sys.stderr
    if not supports_color(stream):
        # No TTY — just print the message once.
        stream.write(f"{message}...\n")
        try:
            yield
        finally:
            stream.write("done.\n")
        return

    stop_event = threading.Event()
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _spin() -> None:
        i = 0
        while not stop_event.is_set():
            frame = frames[i % len(frames)]
            stream.write(f"\r{frame} {message}")
            stream.flush()
            i += 1
            time.sleep(0.1)

    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop_event.set()
        t.join(timeout=0.5)
        stream.write(f"\r✓ {message}\n")
        stream.flush()


# =============================================================================
# === Interactive prompts                                                    ===
# =============================================================================

def confirm(message: str, default: bool = False) -> bool:
    """Prompt the user for a Y/N confirmation.

    Returns the user's choice, or `default` if they just press Enter.
    """
    hint = "Y/n" if default else "y/N"
    try:
        s = input(f"{message} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not s:
        return default
    return s in ("y", "yes")


def prompt(message: str, default: Optional[str] = None) -> str:
    """Prompt the user for a text input.

    Returns the user's input, or `default` if they just press Enter.
    """
    hint = f" [{default}]" if default is not None else ""
    try:
        s = input(f"{message}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return default or ""
    if not s and default is not None:
        return default
    return s


def select(
    message: str,
    options: Sequence[str],
    default: int = 0,
) -> int:
    """Prompt the user to select from a list of options.

    Returns the 0-based index of the selected option.
    """
    if not options:
        raise ValueError("options must be non-empty")
    print(message)
    for i, opt in enumerate(options):
        marker = " *" if i == default else "  "
        print(f"{marker} {i + 1}. {opt}")
    while True:
        try:
            s = input(f"Choice [{default + 1}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        if not s:
            return default
        try:
            idx = int(s) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"Invalid choice.  Enter 1..{len(options)}.")


# =============================================================================
# === Internal helpers                                                       ===
# =============================================================================

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def _to_fa_digits(s: str) -> str:
    """Convert Western digits in a string to Persian digits."""
    out = []
    for ch in s:
        if ch.isdigit():
            out.append(_FA_DIGITS[int(ch)])
        else:
            out.append(ch)
    return "".join(out)


# =============================================================================
# === CLI                                                                    ===
# =============================================================================

def _main() -> int:
    """CLI entry: ``python -m rask.utils.cli_helpers``."""
    print("=== format_table ===")
    print(format_table(
        [["Alice", 30, "Tehran"], ["Bob", 25, "Shiraz"], ["Carol", 35, "Mashhad"]],
        ["Name", "Age", "City"],
        lang="en",
    ))
    print()
    print("=== format_tree ===")
    print(format_tree([
        {"label": "Rask", "children": [
            {"label": "rask/core"},
            {"label": "rask/services", "children": [
                {"label": "activity_service.py"},
                {"label": "goal_service.py"},
            ]},
            {"label": "rask/ui"},
        ]},
    ], lang="en"))
    print()
    print("=== format_json ===")
    print(format_json({"name": "Rask", "version": "2.0.0", "features": [1, 2, 3]}))
    print()
    print("=== format_yaml ===")
    print(format_yaml({"name": "Rask", "version": "2.0.0", "features": [1, 2, 3]}))
    print()
    print("=== progress_bar ===")
    print(progress_bar(25, 100))
    print()
    print("=== colorize ===")
    print(colorize("Gold text", "gold"))
    print(colorize("Red text", "red"))
    print(colorize("Green text", "green"))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
