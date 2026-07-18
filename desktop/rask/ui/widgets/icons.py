"""
rask.ui.widgets.icons
=====================

Procedural icon registry for Rask.

Every icon is drawn on a Pillow ``ImageDraw`` canvas at request-time
using simple line-art primitives — no external SVG or PNG files are
required.  This keeps the binary small (no asset shipping) and makes
the icons trivially theme-able (any colour, any size, any DPI).

If Pillow is unavailable, every call falls back to a small unicode
glyph rendered as a ``ctk.CTkLabel``-style text — this keeps the app
functional on a bare-bones install.

Public API
----------
``icon(name, size=24, color=None) -> ctk.CTkImage``
    Return a CTkImage for ``name`` (see :data:`ICON_NAMES`).

``icon_glyph(name) -> str``
    Return a unicode fallback glyph for ``name``.

``has_icon(name) -> bool``
    True if ``name`` is a known icon.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

try:
    from PIL import Image, ImageDraw
    _PIL_OK: bool = True
except Exception:  # pragma: no cover
    _PIL_OK = False
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]

from ... import config

__all__ = ["icon", "icon_glyph", "has_icon", "ICON_NAMES"]


# =============================================================================
# === Unicode fallback glyphs                                                ===
# =============================================================================

# Each entry maps an icon name to a unicode glyph that approximates it.
# These are used when Pillow is unavailable or when the caller asks for
# a text fallback via ``icon_glyph()``.
_GLYPHS: Dict[str, str] = {
    "home": "⌂",
    "goals": "◎",
    "stats": "▤",
    "settings": "⚙",
    "plus": "+",
    "search": "⌕",
    "play": "▶",
    "pause": "❚❚",
    "stop": "■",
    "save": "💾",
    "delete": "🗑",
    "edit": "✎",
    "share": "↗",
    "export": "⤓",
    "backup": "🗄",
    "restore": "↺",
    "lock": "🔒",
    "unlock": "🔓",
    "mic": "🎤",
    "calendar": "📅",
    "clock": "🕐",
    "flame": "🔥",
    "trophy": "🏆",
    "badge": "🏅",
    "check": "✓",
    "x": "✕",
    "arrow_left": "←",
    "arrow_right": "→",
    "chevron_down": "▾",
    "chevron_up": "▴",
    "dots": "⋯",
    "filter": "⋔",
    "sort": "↕",
    "sun": "☀",
    "moon": "☾",
    "sunrise": "🌅",
    "sunset": "🌇",
    "ring": "◯",
    "book": "📖",
    "briefcase": "💼",
    "heart": "♥",
    "palette": "🎨",
    "users": "👥",
    "star": "★",
    "spark": "✦",
    "shield": "⛨",
    "bell": "🔔",
    "snooze": "💤",
    "tag": "🏷",
    "chart_bar": "📊",
    "chart_line": "📈",
    "chart_pie": "🥧",
    "chart_heatmap": "▦",
    "image": "🖼",
    "file": "📄",
    "pdf": "📕",
    "csv": "📗",
    "settings_gear": "⚙",
    "info": "ℹ",
    "help": "?",
    "question": "?",
    "warning": "⚠",
    "danger": "⛔",
    "success": "✓",
    "eye": "👁",
    "eye_off": "🚫",
    "copy": "📋",
    "paste": "📋",
    "clipboard": "📋",
    "refresh": "⟳",
    "sync": "🔄",
    "download": "⤓",
    "upload": "⤒",
    "calendar_plus": "📅",
    "plus_circle": "⊕",
    "minus_circle": "⊖",
    "check_circle": "✓",
    "x_circle": "✕",
    "info_circle": "ℹ",
    "dot": "•",
    "medal": "🏅",
    "bolt": "⚡",
    "diamond": "♦",
    "menu": "≡",
    "back": "←",
    "forward": "→",
    "close": "✕",
    "add": "+",
    "remove": "−",
    "expand": "⤢",
    "collapse": "⤡",
    "pin": "📌",
    "flag": "⚑",
    "key": "🔑",
    "gift": "🎁",
    "crown": "♔",
    "leaf": "🍂",
    "music": "🎵",
    "video": "🎬",
    "camera": "📷",
    "wifi": "📶",
    "battery": "🔋",
    "power": "⏻",
    "user": "👤",
}

ICON_NAMES = tuple(sorted(_GLYPHS.keys()))


def icon_glyph(name: str) -> str:
    """Return a unicode glyph approximating ``name`` (fallback ``"•"``)."""
    return _GLYPHS.get(name, "•")


def has_icon(name: str) -> bool:
    """True if ``name`` is a known icon."""
    return name in _GLYPHS


# =============================================================================
# === Pillow drawing primitives                                              ===
# =============================================================================

def _new_canvas(size: int, color: str) -> Tuple["Image.Image", "ImageDraw.ImageDraw"]:
    """Return a transparent RGBA image + draw object sized `size`×`size`."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def _line(draw: "ImageDraw.ImageDraw", p1: Tuple[float, float],
          p2: Tuple[float, float], fill: str, width: int) -> None:
    draw.line([p1, p2], fill=fill, width=width, joint="curve")


def _poly(draw: "ImageDraw.ImageDraw", pts, fill: Optional[str] = None,
          outline: Optional[str] = None, width: int = 1) -> None:
    draw.polygon(pts, fill=fill, outline=outline, width=width)


def _circle(draw: "ImageDraw.ImageDraw", cx: float, cy: float, r: float,
            fill: Optional[str] = None, outline: Optional[str] = None,
            width: int = 1) -> None:
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.ellipse(bbox, fill=fill, outline=outline, width=width)


def _arc(draw: "ImageDraw.ImageDraw", cx: float, cy: float, r: float,
         start: float, end: float, fill: str, width: int) -> None:
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.arc(bbox, start=start, end=end, fill=fill, width=width)


# =============================================================================
# === Individual icon drawers                                                ===
# =============================================================================

def _draw_home(d, s, c, w):
    _poly(d, [(s*0.5, s*0.15), (s*0.85, s*0.5), (s*0.75, s*0.5),
              (s*0.75, s*0.85), (s*0.25, s*0.85), (s*0.25, s*0.5),
              (s*0.15, s*0.5)], outline=c, width=w, fill=None)
    _line(d, (s*0.42, s*0.85), (s*0.42, s*0.6), c, w)
    _line(d, (s*0.58, s*0.85), (s*0.58, s*0.6), c, w)


def _draw_ring(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _circle(d, s*0.5, s*0.5, s*0.18, fill=None, outline=c, width=w)


def _draw_goals(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _circle(d, s*0.5, s*0.5, s*0.06, fill=c, outline=c, width=w)


def _draw_stats(d, s, c, w):
    _line(d, (s*0.2, s*0.8), (s*0.2, s*0.55), c, w)
    _line(d, (s*0.4, s*0.8), (s*0.4, s*0.4), c, w)
    _line(d, (s*0.6, s*0.8), (s*0.6, s*0.25), c, w)
    _line(d, (s*0.8, s*0.8), (s*0.8, s*0.5), c, w)
    _line(d, (s*0.15, s*0.85), (s*0.85, s*0.85), c, w)


def _draw_settings(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.15, fill=None, outline=c, width=w)
    for i in range(8):
        a = i * math.pi / 4
        x1 = s*0.5 + math.cos(a) * s*0.25
        y1 = s*0.5 + math.sin(a) * s*0.25
        x2 = s*0.5 + math.cos(a) * s*0.4
        y2 = s*0.5 + math.sin(a) * s*0.4
        _line(d, (x1, y1), (x2, y2), c, w)


def _draw_plus(d, s, c, w):
    _line(d, (s*0.5, s*0.2), (s*0.5, s*0.8), c, w)
    _line(d, (s*0.2, s*0.5), (s*0.8, s*0.5), c, w)


def _draw_minus(d, s, c, w):
    _line(d, (s*0.2, s*0.5), (s*0.8, s*0.5), c, w)


def _draw_x(d, s, c, w):
    _line(d, (s*0.25, s*0.25), (s*0.75, s*0.75), c, w)
    _line(d, (s*0.75, s*0.25), (s*0.25, s*0.75), c, w)


def _draw_check(d, s, c, w):
    _line(d, (s*0.2, s*0.5), (s*0.45, s*0.75), c, w)
    _line(d, (s*0.45, s*0.75), (s*0.8, s*0.25), c, w)


def _draw_arrow_left(d, s, c, w):
    _line(d, (s*0.7, s*0.5), (s*0.3, s*0.5), c, w)
    _line(d, (s*0.3, s*0.5), (s*0.45, s*0.35), c, w)
    _line(d, (s*0.3, s*0.5), (s*0.45, s*0.65), c, w)


def _draw_arrow_right(d, s, c, w):
    _line(d, (s*0.3, s*0.5), (s*0.7, s*0.5), c, w)
    _line(d, (s*0.7, s*0.5), (s*0.55, s*0.35), c, w)
    _line(d, (s*0.7, s*0.5), (s*0.55, s*0.65), c, w)


def _draw_chevron_down(d, s, c, w):
    _line(d, (s*0.25, s*0.4), (s*0.5, s*0.65), c, w)
    _line(d, (s*0.5, s*0.65), (s*0.75, s*0.4), c, w)


def _draw_chevron_up(d, s, c, w):
    _line(d, (s*0.25, s*0.6), (s*0.5, s*0.35), c, w)
    _line(d, (s*0.5, s*0.35), (s*0.75, s*0.6), c, w)


def _draw_play(d, s, c, w):
    _poly(d, [(s*0.35, s*0.25), (s*0.35, s*0.75), (s*0.75, s*0.5)],
          fill=c, outline=c)


def _draw_pause(d, s, c, w):
    _line(d, (s*0.4, s*0.25), (s*0.4, s*0.75), c, int(w*2))
    _line(d, (s*0.6, s*0.25), (s*0.6, s*0.75), c, int(w*2))


def _draw_stop(d, s, c, w):
    _poly(d, [(s*0.3, s*0.3), (s*0.7, s*0.3), (s*0.7, s*0.7), (s*0.3, s*0.7)],
          fill=c, outline=c)


def _draw_search(d, s, c, w):
    _circle(d, s*0.45, s*0.45, s*0.2, fill=None, outline=c, width=w)
    _line(d, (s*0.6, s*0.6), (s*0.8, s*0.8), c, w)


def _draw_clock(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.5, s*0.5), (s*0.5, s*0.3), c, w)
    _line(d, (s*0.5, s*0.5), (s*0.65, s*0.55), c, w)


def _draw_calendar(d, s, c, w):
    _poly(d, [(s*0.2, s*0.25), (s*0.8, s*0.25), (s*0.8, s*0.8),
              (s*0.2, s*0.8)], outline=c, width=w, fill=None)
    _line(d, (s*0.2, s*0.4), (s*0.8, s*0.4), c, w)
    _line(d, (s*0.35, s*0.2), (s*0.35, s*0.3), c, w)
    _line(d, (s*0.65, s*0.2), (s*0.65, s*0.3), c, w)


def _draw_flame(d, s, c, w):
    _poly(d, [(s*0.5, s*0.15), (s*0.7, s*0.4), (s*0.75, s*0.6),
              (s*0.65, s*0.8), (s*0.35, s*0.8), (s*0.25, s*0.6),
              (s*0.3, s*0.4)], outline=c, width=w, fill=None)
    _circle(d, s*0.5, s*0.62, s*0.1, fill=c, outline=c, width=w)


def _draw_trophy(d, s, c, w):
    _poly(d, [(s*0.35, s*0.2), (s*0.65, s*0.2), (s*0.6, s*0.5),
              (s*0.4, s*0.5)], outline=c, width=w, fill=None)
    _line(d, (s*0.35, s*0.25), (s*0.25, s*0.3), c, w)
    _line(d, (s*0.25, s*0.3), (s*0.3, s*0.45), c, w)
    _line(d, (s*0.3, s*0.45), (s*0.4, s*0.45), c, w)
    _line(d, (s*0.65, s*0.25), (s*0.75, s*0.3), c, w)
    _line(d, (s*0.75, s*0.3), (s*0.7, s*0.45), c, w)
    _line(d, (s*0.7, s*0.45), (s*0.6, s*0.45), c, w)
    _line(d, (s*0.5, s*0.5), (s*0.5, s*0.65), c, w)
    _line(d, (s*0.35, s*0.8), (s*0.65, s*0.8), c, w)
    _line(d, (s*0.4, s*0.65), (s*0.4, s*0.8), c, w)
    _line(d, (s*0.6, s*0.65), (s*0.6, s*0.8), c, w)


def _draw_star(d, s, c, w):
    pts = []
    cx, cy = s*0.5, s*0.5
    r_out, r_in = s*0.35, s*0.15
    for i in range(10):
        a = -math.pi/2 + i * math.pi/5
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(a)*r, cy + math.sin(a)*r))
    _poly(d, pts, outline=c, width=w, fill=None)


def _draw_heart(d, s, c, w):
    _poly(d, [(s*0.5, s*0.8), (s*0.2, s*0.45), (s*0.2, s*0.3),
              (s*0.35, s*0.2), (s*0.5, s*0.35), (s*0.65, s*0.2),
              (s*0.8, s*0.3), (s*0.8, s*0.45)],
          outline=c, width=w, fill=None)


def _draw_bell(d, s, c, w):
    _poly(d, [(s*0.3, s*0.55), (s*0.3, s*0.7), (s*0.7, s*0.7),
              (s*0.7, s*0.55), (s*0.65, s*0.45), (s*0.65, s*0.35),
              (s*0.5, s*0.2), (s*0.35, s*0.35), (s*0.35, s*0.45)],
          outline=c, width=w, fill=None)
    _line(d, (s*0.25, s*0.7), (s*0.75, s*0.7), c, w)
    _circle(d, s*0.5, s*0.82, s*0.04, fill=c, outline=c, width=w)


def _draw_eye(d, s, c, w):
    _arc(d, s*0.5, s*0.5, s*0.35, 20, 160, c, w)
    _arc(d, s*0.5, s*0.5, s*0.35, 200, 340, c, w)
    _circle(d, s*0.5, s*0.5, s*0.08, fill=c, outline=c, width=w)


def _draw_eye_off(d, s, c, w):
    _draw_eye(d, s, c, w)
    _line(d, (s*0.25, s*0.25), (s*0.75, s*0.75), c, w)


def _draw_lock(d, s, c, w):
    _poly(d, [(s*0.3, s*0.5), (s*0.7, s*0.5), (s*0.7, s*0.8),
              (s*0.3, s*0.8)], outline=c, width=w, fill=None)
    _arc(d, s*0.5, s*0.5, s*0.2, 180, 360, c, w)
    _circle(d, s*0.5, s*0.65, s*0.05, fill=c, outline=c, width=w)


def _draw_unlock(d, s, c, w):
    _poly(d, [(s*0.3, s*0.5), (s*0.7, s*0.5), (s*0.7, s*0.8),
              (s*0.3, s*0.8)], outline=c, width=w, fill=None)
    _arc(d, s*0.55, s*0.5, s*0.2, 30, 270, c, w)


def _draw_trash(d, s, c, w):
    _line(d, (s*0.25, s*0.3), (s*0.75, s*0.3), c, w)
    _poly(d, [(s*0.32, s*0.3), (s*0.68, s*0.3), (s*0.65, s*0.8),
              (s*0.35, s*0.8)], outline=c, width=w, fill=None)
    _line(d, (s*0.42, s*0.2), (s*0.58, s*0.2), c, w)
    _line(d, (s*0.45, s*0.4), (s*0.45, s*0.7), c, w)
    _line(d, (s*0.55, s*0.4), (s*0.55, s*0.7), c, w)


def _draw_edit(d, s, c, w):
    _line(d, (s*0.7, s*0.3), (s*0.3, s*0.7), c, w)
    _line(d, (s*0.65, s*0.25), (s*0.75, s*0.35), c, w)
    _line(d, (s*0.3, s*0.7), (s*0.25, s*0.75), c, w)
    _line(d, (s*0.25, s*0.75), (s*0.3, s*0.7), c, w)


def _draw_share(d, s, c, w):
    _circle(d, s*0.7, s*0.3, s*0.08, fill=None, outline=c, width=w)
    _circle(d, s*0.3, s*0.5, s*0.08, fill=None, outline=c, width=w)
    _circle(d, s*0.7, s*0.7, s*0.08, fill=None, outline=c, width=w)
    _line(d, (s*0.37, s*0.46), (s*0.63, s*0.34), c, w)
    _line(d, (s*0.37, s*0.54), (s*0.63, s*0.66), c, w)


def _draw_download(d, s, c, w):
    _line(d, (s*0.5, s*0.2), (s*0.5, s*0.65), c, w)
    _line(d, (s*0.35, s*0.5), (s*0.5, s*0.65), c, w)
    _line(d, (s*0.65, s*0.5), (s*0.5, s*0.65), c, w)
    _line(d, (s*0.25, s*0.8), (s*0.75, s*0.8), c, w)


def _draw_upload(d, s, c, w):
    _line(d, (s*0.5, s*0.65), (s*0.5, s*0.2), c, w)
    _line(d, (s*0.35, s*0.35), (s*0.5, s*0.2), c, w)
    _line(d, (s*0.65, s*0.35), (s*0.5, s*0.2), c, w)
    _line(d, (s*0.25, s*0.8), (s*0.75, s*0.8), c, w)


def _draw_refresh(d, s, c, w):
    _arc(d, s*0.5, s*0.5, s*0.3, 30, 300, c, w)
    _poly(d, [(s*0.7, s*0.3), (s*0.8, s*0.4), (s*0.65, s*0.45)],
          fill=c, outline=c)


def _draw_filter(d, s, c, w):
    _poly(d, [(s*0.2, s*0.25), (s*0.8, s*0.25), (s*0.55, s*0.55),
              (s*0.55, s*0.75), (s*0.45, s*0.75), (s*0.45, s*0.55)],
          outline=c, width=w, fill=None)


def _draw_sort(d, s, c, w):
    _line(d, (s*0.3, s*0.2), (s*0.3, s*0.8), c, w)
    _line(d, (s*0.3, s*0.8), (s*0.2, s*0.7), c, w)
    _line(d, (s*0.3, s*0.8), (s*0.4, s*0.7), c, w)
    _line(d, (s*0.7, s*0.8), (s*0.7, s*0.2), c, w)
    _line(d, (s*0.7, s*0.2), (s*0.6, s*0.3), c, w)
    _line(d, (s*0.7, s*0.2), (s*0.8, s*0.3), c, w)


def _draw_sun(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.18, fill=None, outline=c, width=w)
    for i in range(8):
        a = i * math.pi / 4
        x1 = s*0.5 + math.cos(a) * s*0.28
        y1 = s*0.5 + math.sin(a) * s*0.28
        x2 = s*0.5 + math.cos(a) * s*0.4
        y2 = s*0.5 + math.sin(a) * s*0.4
        _line(d, (x1, y1), (x2, y2), c, w)


def _draw_moon(d, s, c, w):
    _arc(d, s*0.55, s*0.5, s*0.35, 200, 340, c, w)
    _arc(d, s*0.45, s*0.5, s*0.35, 200, 340, c, w)


def _draw_book(d, s, c, w):
    _poly(d, [(s*0.25, s*0.25), (s*0.5, s*0.3), (s*0.75, s*0.25),
              (s*0.75, s*0.8), (s*0.5, s*0.75), (s*0.25, s*0.8)],
          outline=c, width=w, fill=None)
    _line(d, (s*0.5, s*0.3), (s*0.5, s*0.75), c, w)


def _draw_briefcase(d, s, c, w):
    _poly(d, [(s*0.2, s*0.4), (s*0.8, s*0.4), (s*0.8, s*0.8),
              (s*0.2, s*0.8)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.4, s*0.4), (s*0.4, s*0.3), (s*0.6, s*0.3),
              (s*0.6, s*0.4)], outline=c, width=w, fill=None)
    _line(d, (s*0.2, s*0.55), (s*0.8, s*0.55), c, w)


def _draw_palette(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _circle(d, s*0.35, s*0.4, s*0.04, fill=c, outline=c, width=w)
    _circle(d, s*0.5, s*0.35, s*0.04, fill=c, outline=c, width=w)
    _circle(d, s*0.65, s*0.4, s*0.04, fill=c, outline=c, width=w)
    _circle(d, s*0.6, s*0.6, s*0.05, fill=None, outline=c, width=w)


def _draw_users(d, s, c, w):
    _circle(d, s*0.35, s*0.4, s*0.12, fill=None, outline=c, width=w)
    _arc(d, s*0.35, s*0.85, s*0.2, 180, 360, c, w)
    _circle(d, s*0.65, s*0.4, s*0.1, fill=None, outline=c, width=w)
    _arc(d, s*0.65, s*0.85, s*0.17, 180, 360, c, w)


def _draw_shield(d, s, c, w):
    _poly(d, [(s*0.5, s*0.15), (s*0.8, s*0.3), (s*0.8, s*0.55),
              (s*0.5, s*0.85), (s*0.2, s*0.55), (s*0.2, s*0.3)],
          outline=c, width=w, fill=None)
    _line(d, (s*0.4, s*0.5), (s*0.48, s*0.6), c, w)
    _line(d, (s*0.48, s*0.6), (s*0.65, s*0.4), c, w)


def _draw_mic(d, s, c, w):
    _poly(d, [(s*0.42, s*0.2), (s*0.58, s*0.2), (s*0.58, s*0.55),
              (s*0.42, s*0.55)], outline=c, width=w, fill=None)
    _arc(d, s*0.5, s*0.55, s*0.18, 20, 160, c, w)
    _line(d, (s*0.5, s*0.7), (s*0.5, s*0.8), c, w)
    _line(d, (s*0.35, s*0.8), (s*0.65, s*0.8), c, w)


def _draw_tag(d, s, c, w):
    _poly(d, [(s*0.2, s*0.5), (s*0.5, s*0.2), (s*0.8, s*0.2),
              (s*0.8, s*0.5), (s*0.5, s*0.8)], outline=c, width=w, fill=None)
    _circle(d, s*0.65, s*0.35, s*0.04, fill=c, outline=c, width=w)


def _draw_chart_bar(d, s, c, w):
    _draw_stats(d, s, c, w)


def _draw_chart_line(d, s, c, w):
    _line(d, (s*0.15, s*0.85), (s*0.85, s*0.85), c, w)
    _line(d, (s*0.15, s*0.15), (s*0.15, s*0.85), c, w)
    _line(d, (s*0.2, s*0.7), (s*0.4, s*0.5), c, w)
    _line(d, (s*0.4, s*0.5), (s*0.6, s*0.6), c, w)
    _line(d, (s*0.6, s*0.6), (s*0.8, s*0.3), c, w)


def _draw_chart_pie(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.5, s*0.5), (s*0.5, s*0.15), c, w)
    _line(d, (s*0.5, s*0.5), (s*0.8, s*0.6), c, w)


def _draw_chart_heatmap(d, s, c, w):
    cell = s * 0.18
    for r in range(4):
        for col in range(4):
            x = s*0.15 + col * (cell + s*0.02)
            y = s*0.15 + r * (cell + s*0.02)
            shade = 0.3 + 0.18 * (r * 4 + col) / 16
            try:
                col_rgb = helpers.lighten_color(config.MATTE_BLACK, shade)
            except Exception:
                col_rgb = c
            d.rectangle([x, y, x + cell, y + cell], fill=col_rgb, outline=c)


def _draw_dots(d, s, c, w):
    for cx in (s*0.3, s*0.5, s*0.7):
        _circle(d, cx, s*0.5, s*0.05, fill=c, outline=c, width=w)


def _draw_dot(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.12, fill=c, outline=c, width=w)


def _draw_info(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _circle(d, s*0.5, s*0.3, s*0.04, fill=c, outline=c, width=w)
    _line(d, (s*0.5, s*0.45), (s*0.5, s*0.7), c, w)


def _draw_warning(d, s, c, w):
    _poly(d, [(s*0.5, s*0.15), (s*0.85, s*0.8), (s*0.15, s*0.8)],
          outline=c, width=w, fill=None)
    _line(d, (s*0.5, s*0.4), (s*0.5, s*0.6), c, w)
    _circle(d, s*0.5, s*0.7, s*0.03, fill=c, outline=c, width=w)


def _draw_danger(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.35, s*0.35), (s*0.65, s*0.65), c, w)
    _line(d, (s*0.65, s*0.35), (s*0.35, s*0.65), c, w)


def _draw_check_circle(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.35, s*0.5), (s*0.47, s*0.62), c, w)
    _line(d, (s*0.47, s*0.62), (s*0.68, s*0.38), c, w)


def _draw_x_circle(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.38, s*0.38), (s*0.62, s*0.62), c, w)
    _line(d, (s*0.62, s*0.38), (s*0.38, s*0.62), c, w)


def _draw_plus_circle(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.5, s*0.3), (s*0.5, s*0.7), c, w)
    _line(d, (s*0.3, s*0.5), (s*0.7, s*0.5), c, w)


def _draw_minus_circle(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _line(d, (s*0.3, s*0.5), (s*0.7, s*0.5), c, w)


def _draw_info_circle(d, s, c, w):
    _draw_info(d, s, c, w)


def _draw_calendar_plus(d, s, c, w):
    _draw_calendar(d, s, c, w)
    _line(d, (s*0.5, s*0.55), (s*0.5, s*0.75), c, w)
    _line(d, (s*0.4, s*0.65), (s*0.6, s*0.65), c, w)


def _draw_sunrise(d, s, c, w):
    _line(d, (s*0.15, s*0.7), (s*0.85, s*0.7), c, w)
    _arc(d, s*0.5, s*0.7, s*0.2, 180, 360, c, w)
    _line(d, (s*0.5, s*0.2), (s*0.5, s*0.35), c, w)
    _line(d, (s*0.25, s*0.4), (s*0.35, s*0.5), c, w)
    _line(d, (s*0.75, s*0.4), (s*0.65, s*0.5), c, w)
    _line(d, (s*0.15, s*0.85), (s*0.4, s*0.85), c, w)


def _draw_sunset(d, s, c, w):
    _line(d, (s*0.15, s*0.7), (s*0.85, s*0.7), c, w)
    _arc(d, s*0.5, s*0.7, s*0.2, 180, 360, c, w)
    _line(d, (s*0.5, s*0.7), (s*0.5, s*0.85), c, w)
    _line(d, (s*0.4, s*0.4), (s*0.5, s*0.5), c, w)
    _line(d, (s*0.6, s*0.4), (s*0.5, s*0.5), c, w)


def _draw_save(d, s, c, w):
    _poly(d, [(s*0.2, s*0.2), (s*0.7, s*0.2), (s*0.8, s*0.3),
              (s*0.8, s*0.8), (s*0.2, s*0.8)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.35, s*0.2), (s*0.35, s*0.45), (s*0.65, s*0.45),
              (s*0.65, s*0.2)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.3, s*0.55), (s*0.7, s*0.55), (s*0.7, s*0.8),
              (s*0.3, s*0.8)], outline=c, width=w, fill=None)


def _draw_restore(d, s, c, w):
    _draw_refresh(d, s, c, w)


def _draw_backup(d, s, c, w):
    _draw_save(d, s, c, w)


def _draw_export(d, s, c, w):
    _draw_download(d, s, c, w)


def _draw_pdf(d, s, c, w):
    _poly(d, [(s*0.25, s*0.15), (s*0.65, s*0.15), (s*0.8, s*0.3),
              (s*0.8, s*0.85), (s*0.25, s*0.85)], outline=c, width=w, fill=None)
    _line(d, (s*0.65, s*0.15), (s*0.65, s*0.3), c, w)
    _line(d, (s*0.65, s*0.3), (s*0.8, s*0.3), c, w)


def _draw_csv(d, s, c, w):
    _draw_pdf(d, s, c, w)


def _draw_file(d, s, c, w):
    _draw_pdf(d, s, c, w)


def _draw_image(d, s, c, w):
    _poly(d, [(s*0.2, s*0.25), (s*0.8, s*0.25), (s*0.8, s*0.8),
              (s*0.2, s*0.8)], outline=c, width=w, fill=None)
    _circle(d, s*0.4, s*0.45, s*0.07, fill=c, outline=c, width=w)
    _poly(d, [(s*0.2, s*0.8), (s*0.4, s*0.6), (s*0.55, s*0.75),
              (s*0.7, s*0.55), (s*0.8, s*0.8)], outline=c, width=w, fill=None)


def _draw_copy(d, s, c, w):
    _poly(d, [(s*0.3, s*0.25), (s*0.65, s*0.25), (s*0.65, s*0.75),
              (s*0.3, s*0.75)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.4, s*0.2), (s*0.75, s*0.2), (s*0.75, s*0.65),
              (s*0.7, s*0.65)], outline=c, width=w, fill=None)


def _draw_clipboard(d, s, c, w):
    _poly(d, [(s*0.25, s*0.25), (s*0.75, s*0.25), (s*0.75, s*0.85),
              (s*0.25, s*0.85)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.4, s*0.2), (s*0.6, s*0.2), (s*0.6, s*0.3),
              (s*0.4, s*0.3)], outline=c, width=w, fill=None)


def _draw_paste(d, s, c, w):
    _draw_clipboard(d, s, c, w)


def _draw_sync(d, s, c, w):
    _draw_refresh(d, s, c, w)


def _draw_menu(d, s, c, w):
    for y in (s*0.3, s*0.5, s*0.7):
        _line(d, (s*0.2, y), (s*0.8, y), c, w)


def _draw_close(d, s, c, w):
    _draw_x(d, s, c, w)


def _draw_add(d, s, c, w):
    _draw_plus(d, s, c, w)


def _draw_remove(d, s, c, w):
    _draw_minus(d, s, c, w)


def _draw_snooze(d, s, c, w):
    _draw_moon(d, s, c, w)
    _draw_dots(d, s, c, w)


def _draw_settings_gear(d, s, c, w):
    _draw_settings(d, s, c, w)


def _draw_help(d, s, c, w):
    _circle(d, s*0.5, s*0.5, s*0.35, fill=None, outline=c, width=w)
    _arc(d, s*0.5, s*0.45, s*0.15, 30, 270, c, w)
    _circle(d, s*0.5, s*0.7, s*0.03, fill=c, outline=c, width=w)


def _draw_question(d, s, c, w):
    _draw_help(d, s, c, w)


def _draw_medal(d, s, c, w):
    _circle(d, s*0.5, s*0.6, s*0.22, fill=None, outline=c, width=w)
    _poly(d, [(s*0.35, s*0.15), (s*0.65, s*0.15), (s*0.55, s*0.45),
              (s*0.45, s*0.45)], outline=c, width=w, fill=None)
    _line(d, (s*0.5, s*0.5), (s*0.5, s*0.7), c, w)


def _draw_bolt(d, s, c, w):
    _poly(d, [(s*0.55, s*0.15), (s*0.3, s*0.55), (s*0.5, s*0.55),
              (s*0.45, s*0.85), (s*0.7, s*0.45), (s*0.5, s*0.45)],
          fill=c, outline=c)


def _draw_diamond(d, s, c, w):
    _poly(d, [(s*0.5, s*0.15), (s*0.85, s*0.5), (s*0.5, s*0.85),
              (s*0.15, s*0.5)], outline=c, width=w, fill=None)
    _line(d, (s*0.15, s*0.5), (s*0.85, s*0.5), c, w)


def _draw_crown(d, s, c, w):
    _poly(d, [(s*0.2, s*0.7), (s*0.2, s*0.4), (s*0.35, s*0.55),
              (s*0.5, s*0.3), (s*0.65, s*0.55), (s*0.8, s*0.4),
              (s*0.8, s*0.7)], outline=c, width=w, fill=None)
    _line(d, (s*0.2, s*0.8), (s*0.8, s*0.8), c, w)


def _draw_gift(d, s, c, w):
    _poly(d, [(s*0.2, s*0.4), (s*0.8, s*0.4), (s*0.8, s*0.8),
              (s*0.2, s*0.8)], outline=c, width=w, fill=None)
    _line(d, (s*0.5, s*0.4), (s*0.5, s*0.8), c, w)
    _line(d, (s*0.2, s*0.55), (s*0.8, s*0.55), c, w)
    _poly(d, [(s*0.5, s*0.2), (s*0.4, s*0.4), (s*0.6, s*0.4)],
          outline=c, width=w, fill=None)


def _draw_leaf(d, s, c, w):
    _arc(d, s*0.5, s*0.5, s*0.35, 45, 225, c, w)
    _line(d, (s*0.25, s*0.75), (s*0.65, s*0.35), c, w)


def _draw_user(d, s, c, w):
    _circle(d, s*0.5, s*0.35, s*0.13, fill=None, outline=c, width=w)
    _arc(d, s*0.5, s*0.95, s*0.25, 180, 360, c, w)


def _draw_pin(d, s, c, w):
    _poly(d, [(s*0.4, s*0.2), (s*0.6, s*0.2), (s*0.65, s*0.4),
              (s*0.55, s*0.5), (s*0.55, s*0.7), (s*0.45, s*0.7),
              (s*0.45, s*0.5), (s*0.35, s*0.4)], outline=c, width=w, fill=None)


def _draw_flag(d, s, c, w):
    _line(d, (s*0.3, s*0.2), (s*0.3, s*0.85), c, w)
    _poly(d, [(s*0.3, s*0.2), (s*0.75, s*0.3), (s*0.65, s*0.45),
              (s*0.75, s*0.6), (s*0.3, s*0.5)], outline=c, width=w, fill=None)


def _draw_key(d, s, c, w):
    _circle(d, s*0.35, s*0.5, s*0.15, fill=None, outline=c, width=w)
    _line(d, (s*0.5, s*0.5), (s*0.8, s*0.5), c, w)
    _line(d, (s*0.65, s*0.5), (s*0.65, s*0.65), c, w)
    _line(d, (s*0.75, s*0.5), (s*0.75, s*0.65), c, w)


def _draw_music(d, s, c, w):
    _circle(d, s*0.35, s*0.7, s*0.1, fill=None, outline=c, width=w)
    _circle(d, s*0.65, s*0.6, s*0.1, fill=None, outline=c, width=w)
    _line(d, (s*0.45, s*0.7), (s*0.45, s*0.25), c, w)
    _line(d, (s*0.75, s*0.6), (s*0.75, s*0.15), c, w)
    _line(d, (s*0.45, s*0.25), (s*0.75, s*0.15), c, w)


def _draw_video(d, s, c, w):
    _poly(d, [(s*0.2, s*0.3), (s*0.6, s*0.3), (s*0.6, s*0.7),
              (s*0.2, s*0.7)], outline=c, width=w, fill=None)
    _poly(d, [(s*0.6, s*0.4), (s*0.8, s*0.3), (s*0.8, s*0.7),
              (s*0.6, s*0.6)], outline=c, width=w, fill=None)


def _draw_camera(d, s, c, w):
    _poly(d, [(s*0.2, s*0.35), (s*0.35, s*0.35), (s*0.4, s*0.25),
              (s*0.6, s*0.25), (s*0.65, s*0.35), (s*0.8, s*0.35),
              (s*0.8, s*0.75), (s*0.2, s*0.75)], outline=c, width=w, fill=None)
    _circle(d, s*0.5, s*0.55, s*0.13, fill=None, outline=c, width=w)


def _draw_wifi(d, s, c, w):
    _arc(d, s*0.5, s*0.7, s*0.35, 220, 320, c, w)
    _arc(d, s*0.5, s*0.7, s*0.22, 220, 320, c, w)
    _arc(d, s*0.5, s*0.7, s*0.1, 220, 320, c, w)
    _circle(d, s*0.5, s*0.75, s*0.04, fill=c, outline=c, width=w)


def _draw_battery(d, s, c, w):
    _poly(d, [(s*0.2, s*0.35), (s*0.75, s*0.35), (s*0.75, s*0.65),
              (s*0.2, s*0.65)], outline=c, width=w, fill=None)
    _line(d, (s*0.75, s*0.45), (s*0.8, s*0.45), c, w)
    _line(d, (s*0.75, s*0.55), (s*0.8, s*0.55), c, w)
    _line(d, (s*0.78, s*0.45), (s*0.78, s*0.55), c, w)
    _line(d, (s*0.25, s*0.4), (s*0.25, s*0.6), c, w)


def _draw_power(d, s, c, w):
    _arc(d, s*0.5, s*0.5, s*0.35, 60, 300, c, w)
    _line(d, (s*0.5, s*0.15), (s*0.5, s*0.5), c, w)


def _draw_expand(d, s, c, w):
    _line(d, (s*0.25, s*0.4), (s*0.25, s*0.25), c, w)
    _line(d, (s*0.25, s*0.25), (s*0.4, s*0.25), c, w)
    _line(d, (s*0.75, s*0.4), (s*0.75, s*0.25), c, w)
    _line(d, (s*0.75, s*0.25), (s*0.6, s*0.25), c, w)
    _line(d, (s*0.25, s*0.6), (s*0.25, s*0.75), c, w)
    _line(d, (s*0.25, s*0.75), (s*0.4, s*0.75), c, w)
    _line(d, (s*0.75, s*0.6), (s*0.75, s*0.75), c, w)
    _line(d, (s*0.75, s*0.75), (s*0.6, s*0.75), c, w)


def _draw_collapse(d, s, c, w):
    _line(d, (s*0.4, s*0.25), (s*0.25, s*0.25), c, w)
    _line(d, (s*0.25, s*0.25), (s*0.25, s*0.4), c, w)
    _line(d, (s*0.6, s*0.25), (s*0.75, s*0.25), c, w)
    _line(d, (s*0.75, s*0.25), (s*0.75, s*0.4), c, w)
    _line(d, (s*0.4, s*0.75), (s*0.25, s*0.75), c, w)
    _line(d, (s*0.25, s*0.75), (s*0.25, s*0.6), c, w)
    _line(d, (s*0.6, s*0.75), (s*0.75, s*0.75), c, w)
    _line(d, (s*0.75, s*0.75), (s*0.75, s*0.6), c, w)


def _draw_back(d, s, c, w):
    _draw_arrow_left(d, s, c, w)


def _draw_forward(d, s, c, w):
    _draw_arrow_right(d, s, c, w)


def _draw_spark(d, s, c, w):
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        x1 = s*0.5 + math.cos(a) * s*0.1
        y1 = s*0.5 + math.sin(a) * s*0.1
        x2 = s*0.5 + math.cos(a) * s*0.4
        y2 = s*0.5 + math.sin(a) * s*0.4
        _line(d, (x1, y1), (x2, y2), c, w)
    _circle(d, s*0.5, s*0.5, s*0.06, fill=c, outline=c, width=w)


def _draw_badge(d, s, c, w):
    _draw_medal(d, s, c, w)


def _draw_success(d, s, c, w):
    _draw_check_circle(d, s, c, w)


# Registry of drawers indexed by name.
_DRAWERS: Dict[str, Any] = {
    "home": _draw_home, "ring": _draw_ring, "goals": _draw_goals,
    "stats": _draw_stats, "chart_bar": _draw_chart_bar,
    "chart_line": _draw_chart_line, "chart_pie": _draw_chart_pie,
    "chart_heatmap": _draw_chart_heatmap, "settings": _draw_settings,
    "settings_gear": _draw_settings_gear, "plus": _draw_plus,
    "add": _draw_add, "minus": _draw_minus, "remove": _draw_remove,
    "x": _draw_x, "close": _draw_close, "check": _draw_check,
    "arrow_left": _draw_arrow_left, "arrow_right": _draw_arrow_right,
    "back": _draw_back, "forward": _draw_forward,
    "chevron_down": _draw_chevron_down, "chevron_up": _draw_chevron_up,
    "play": _draw_play, "pause": _draw_pause, "stop": _draw_stop,
    "search": _draw_search, "clock": _draw_clock,
    "calendar": _draw_calendar, "calendar_plus": _draw_calendar_plus,
    "flame": _draw_flame, "trophy": _draw_trophy, "star": _draw_star,
    "heart": _draw_heart, "bell": _draw_bell, "eye": _draw_eye,
    "eye_off": _draw_eye_off, "lock": _draw_lock, "unlock": _draw_unlock,
    "delete": _draw_trash, "edit": _draw_edit, "share": _draw_share,
    "download": _draw_download, "upload": _draw_upload,
    "export": _draw_export, "refresh": _draw_refresh, "sync": _draw_sync,
    "restore": _draw_restore, "backup": _draw_backup,
    "filter": _draw_filter, "sort": _draw_sort, "sun": _draw_sun,
    "moon": _draw_moon, "sunrise": _draw_sunrise, "sunset": _draw_sunset,
    "book": _draw_book, "briefcase": _draw_briefcase,
    "palette": _draw_palette, "users": _draw_users, "shield": _draw_shield,
    "mic": _draw_mic, "tag": _draw_tag, "dots": _draw_dots, "dot": _draw_dot,
    "info": _draw_info, "info_circle": _draw_info_circle,
    "warning": _draw_warning, "danger": _draw_danger,
    "check_circle": _draw_check_circle, "x_circle": _draw_x_circle,
    "plus_circle": _draw_plus_circle, "minus_circle": _draw_minus_circle,
    "success": _draw_success, "save": _draw_save,
    "pdf": _draw_pdf, "csv": _draw_csv, "file": _draw_file,
    "image": _draw_image, "copy": _draw_copy, "paste": _draw_paste,
    "clipboard": _draw_clipboard, "menu": _draw_menu,
    "snooze": _draw_snooze, "help": _draw_help, "question": _draw_question,
    "medal": _draw_medal, "badge": _draw_badge, "bolt": _draw_bolt,
    "diamond": _draw_diamond, "crown": _draw_crown, "gift": _draw_gift,
    "leaf": _draw_leaf, "user": _draw_user, "pin": _draw_pin,
    "flag": _draw_flag, "key": _draw_key, "music": _draw_music,
    "video": _draw_video, "camera": _draw_camera, "wifi": _draw_wifi,
    "battery": _draw_battery, "power": _draw_power,
    "expand": _draw_expand, "collapse": _draw_collapse,
    "spark": _draw_spark,
}


# =============================================================================
# === Public icon()                                                          ===
# =============================================================================

# Cache of CTkImage instances by (name, size, color).
_IMG_CACHE: Dict[Tuple[str, int, str], Any] = {}


def icon(
    name: str,
    size: int = 24,
    color: Optional[str] = None,
) -> Any:
    """Return a :class:`ctk.CTkImage` for ``name``.

    Falls back to a 1×1 transparent image if neither Pillow nor CTk is
    available — the calling widget will then typically render the unicode
    glyph via :func:`icon_glyph` instead.
    """
    if color is None:
        color = config.GOLD
    key = (name, int(size), color)
    cached = _IMG_CACHE.get(key)
    if cached is not None:
        return cached
    if not _CTK_OK:
        return None
    if not _PIL_OK:
        # Without Pillow, CTkImage can still wrap a blank image — but we
        # prefer to signal "no image" by returning None so callers can
        # fall back to a text glyph.
        return None
    img, draw = _new_canvas(size, color)
    drawer = _DRAWERS.get(name)
    if drawer is None:
        # Unknown icon — draw a hollow circle as a graceful fallback.
        _circle(draw, size*0.5, size*0.5, size*0.35, fill=None,
                outline=color, width=max(1, size // 16))
    else:
        try:
            line_w = max(1, size // 12)
            drawer(draw, size, color, line_w)
        except Exception:
            _circle(draw, size*0.5, size*0.5, size*0.35, fill=None,
                    outline=color, width=max(1, size // 16))
    try:
        img_obj = ctk.CTkImage(
            light_image=img,
            dark_image=img,
            size=(size, size),
        )
    except Exception:
        img_obj = None
    if img_obj is not None:
        _IMG_CACHE[key] = img_obj
    return img_obj


def _self_test() -> int:
    """Smoke-test every drawer: ensure none crashes for size=24."""
    if not _PIL_OK:
        print("Pillow not available — skipping icon drawer tests.")
        return 0
    failures = 0
    for name in ICON_NAMES:
        try:
            img, draw = _new_canvas(24, config.GOLD)
            drawer = _DRAWERS.get(name)
            if drawer:
                drawer(draw, 24, config.GOLD, 2)
            else:
                pass  # glyph-only icon
        except Exception as exc:
            print(f"  FAIL {name!r}: {exc}")
            failures += 1
    print(f"Icon drawer smoke test: {len(ICON_NAMES)} icons, "
          f"{failures} failures.")
    return failures


if __name__ == "__main__":
    raise SystemExit(0 if _self_test() == 0 else 1)
