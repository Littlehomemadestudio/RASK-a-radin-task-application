"""icons.py — SVG-rendered icon library for Rask.

Provides:
  - icon(name, size, color) — return a PhotoImage for the given icon name
  - icon_names() — list all available icon names
  - ICON_PATHS — dict of name -> SVG path data

All icons are 24x24 SVG paths (Feather-style stroke icons matching the
web edition's bottom-nav SVGs). They are rendered to PhotoImage via
Tkinter's create_polygon / create_line when needed, or returned as raw
SVG path data for canvas drawing.

Mirrors the bottom-nav SVG icons in web/index.html and extends with many
more icons for categories, actions, and badges.
"""
from __future__ import annotations
import math
from typing import Optional


# =====================================================================
# === ICON PATHS (24x24 viewBox, stroke-based Feather-style) ===
# =====================================================================
ICON_PATHS: dict[str, str] = {
    # Navigation
    "home":       "M3 12l9-9 9 9 M5 10v10h14V10",
    "goals":      "circle:12,12,9 | circle:12,12,5 | circle:12,12,1.5",
    "stats":      "M4 20V10 M10 20V4 M16 20v-7 M22 20H2",
    "settings":   "circle:12,12,3 | M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",

    # Categories (mirror db.js default categories)
    "ring":       "circle:12,12,9 | circle:12,12,5",
    "book":       "M4 19.5A2.5 2.5 0 0 1 6.5 17H20 M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
    "briefcase":  "rect:2,7,20,14,2 | M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16",
    "heart":      "M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z",
    "palette":    "circle:13.5,6.5,1.5 | circle:17.5,10.5,1.5 | circle:8.5,11.5,1.5 | circle:6.5,16.5,1.5 | M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.555C21.965 6.012 17.461 2 12 2z",
    "users":      "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
    "moon":       "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z",

    # Actions
    "plus":       "M12 5v14 M5 12h14",
    "minus":      "M5 12h14",
    "check":      "M20 6L9 17l-5-5",
    "x":          "M18 6L6 18 M6 6l12 12",
    "edit":       "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
    "trash":      "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2 M10 11v6 M14 11v6",
    "save":       "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8",
    "download":   "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3",
    "upload":     "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
    "search":     "circle:11,11,8 | M21 21l-4.35-4.35",
    "filter":     "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
    "refresh":    "M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0 1 14.85-3.36L23 10 M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
    "play":       "polygon:5,3,19,12,5,21",
    "pause":      "rect:6,4,4,16 | rect:14,4,4,16",
    "stop":       "rect:6,6,12,12",
    "mic":        "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z M19 10v2a7 7 0 0 1-14 0v-2 M12 19v4 M8 23h8",
    "speaker":    "M11 5L6 9H2v6h4l5 4V5z M19.07 4.93a10 10 0 0 1 0 14.14 M15.54 8.46a5 5 0 0 1 0 7.07",
    "lock":       "rect:3,11,18,11,2,2 | M7 11V7a5 5 0 0 1 10 0v4",
    "unlock":     "rect:3,11,18,11,2,2 | M7 11V7a5 5 0 0 1 9.9-1",
    "fingerprint":"M12 11a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4 M14 13.12c0 2.38 4-2.12 5-.12 M9.13 9a3 3 0 0 1 5.74 1.55c0 1.18.42 2.2 1 3 M6 12a6 6 0 0 1 12 0c0 2 .5 3 1 4",
    "key":        "M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4",
    "eye":        "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z | circle:12,12,3",
    "eye-off":    "M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24 M1 1l22 22",

    # Time
    "clock":      "circle:12,12,10 | M12 6v6l4 2",
    "calendar":   "rect:3,4,18,18,2,2 | M16 2v4 M8 2v4 M3 10h18",
    "timer":      "M10 2h4 M12 14V8 M12 14a6 6 0 1 0 0-12 6 6 0 0 0 0 12z",
    "hourglass":  "M6 2h12 M6 22h12 M6 2v6a6 6 0 0 0 12 0V2 M6 22v-6a6 6 0 0 1 12 0v6",
    "stopwatch":  "M12 6v6l4 2 M9 2h6 M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z",
    "history":    "M3 3v5h5 M3.05 13A9 9 0 1 0 6 5.3L3 8 M12 7v5l4 2",

    # Trends / badges
    "trending-up":   "M23 6l-9.5 9.5-5-5L1 18 M17 6h6v6",
    "trending-down": "M23 18l-9.5-9.5-5 5L1 6 M17 18h6v-6",
    "award":      "circle:12,8,7 | M8.21 13.89L7 23l5-3 5 3-1.21-9.12",
    "trophy":     "M6 9H4.5a2.5 2.5 0 0 1 0-5H6 M18 9h1.5a2.5 2.5 0 0 0 0-5H18 M4 22h16 M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22 M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22 M18 2H6v7a6 6 0 0 0 12 0V2z",
    "star":       "polygon:12,2,15.09,8.26,22,9.27,17,14.14,18.18,21.02,12,17.77,5.82,21.02,7,14.14,2,9.27,8.91,8.26",
    "flag":       "M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z M4 22v-7",
    "target":     "circle:12,12,10 | circle:12,12,6 | circle:12,12,2",
    "zap":        "polygon:13,2,3,14,12,14,11,22,21,10,12,10",
    "fire":       "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z",
    "sun":        "circle:12,12,5 | M12 1v2 M12 21v2 M4.22 4.22l1.42 1.42 M18.36 18.36l1.42 1.42 M1 12h2 M21 12h2 M4.22 19.78l1.42-1.42 M18.36 5.64l1.42-1.42",
    "cloud":      "M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z",

    # Files / data
    "file":       "M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z M13 2v7h7",
    "file-text":  "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8",
    "folder":     "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",
    "database":   "M12 2a9 9 0 0 0-9 9c0 4.97 4.03 9 9 9s9-4.03 9-9-4.03-9-9-9z M12 6v12 M6 12h12",
    "shield":     "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    "info":       "circle:12,12,10 | M12 16v-4 M12 8h.01",
    "help":       "circle:12,12,10 | M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3 M12 17h.01",
    "warning":    "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01",
    "alert":      "circle:12,12,10 | M12 8v4 M12 16h.01",

    # Communication
    "mail":       "M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z M22 6l-10 7L2 6",
    "send":       "M22 2L11 13 M22 2l-7 20-4-9-9-4 20-7z",
    "share":      "circle:18,5,3 | circle:6,12,3 | circle:18,19,3 | M8.59 13.51l6.83 3.98 M15.41 6.51l-6.82 3.98",
    "link":       "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71 M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",

    # Misc
    "chevron-right":  "M9 18l6-6-6-6",
    "chevron-left":   "M15 18l-6-6 6-6",
    "chevron-up":     "M18 15l-6-6-6 6",
    "chevron-down":   "M6 9l6 6 6-6",
    "arrow-right":    "M5 12h14 M12 5l7 7-7 7",
    "arrow-left":     "M19 12H5 M12 19l-7-7 7-7",
    "arrow-up":       "M12 19V5 M5 12l7-7 7 7",
    "arrow-down":     "M12 5v14 M19 12l-7 7-7-7",
    "more":           "circle:12,12,1 | circle:19,12,1 | circle:5,12,1",
    "more-vertical":  "circle:12,12,1 | circle:12,5,1 | circle:12,19,1",
    "menu":           "M3 12h18 M3 6h18 M3 18h18",
    "grid":           "rect:3,3,7,7,1 | rect:14,3,7,7,1 | rect:14,14,7,7,1 | rect:3,14,7,7,1",
    "list":           "M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01",
    "bookmark":       "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z",
    "tag":            "M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z M7 7h.01",
    "hash":           "M4 9h16 M4 15h16 M10 3L8 21 M16 3l-2 18",
    "bold":           "M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z",
    "italic":         "M19 4h-9 M14 20H5 M15 4L9 20",
    "underline":      "M6 3v7a6 6 0 0 0 6 6 6 6 0 0 0 6-6V3 M4 21h16",

    # Categories extra
    "code":       "M16 18l6-6-6-6 M8 6l-6 6 6 6",
    "music":      "M9 18V5l12-2v13 M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    "camera":     "M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z | circle:12,13,4",
    "video":      "M23 7l-7 5 7 5V7z | rect:1,5,15,14,2,2",
    "phone":      "M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z",

    # Places / things
    "home-fill":  "M3 12l9-9 9 9v9a2 2 0 0 1-2 2h-4v-7h-6v7H5a2 2 0 0 1-2-2v-9z",
    "globe":      "circle:12,12,10 | M2 12h20 M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z",
    "map":        "M1 6v15l7-3 8 3 7-3V3l-7 3-8-3-7 3z M8 3v15 M16 6v15",
    "navigation": "M3 11l19-9-9 19-2-8-8-2z",
    "compass":    "circle:12,12,10 | polygon:16.24,7.76,14.12,14.12,7.76,16.24,9.88,9.88",

    # Misc utilities
    "settings-2": "circle:12,12,3 | M12 1v6 M12 17v6 M4.22 4.22l4.24 4.24 M15.54 15.54l4.24 4.24 M1 12h6 M17 12h6 M4.22 19.78l4.24-4.24 M15.54 8.46l4.24-4.24",
    "sliders":    "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6",
    "battery":    "rect:1,7,18,10,2,2 | M23 10v4 M17 9v6",
    "wifi":       "M5 12.55a11 11 0 0 1 14.08 0 M1.42 9a16 16 0 0 1 21.16 0 M8.53 16.11a6 6 0 0 1 6.95 0 M12 20h.01",
    "printer":    "M6 9V2h12v7 M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2 M6 14h12v8H6z",
    "clipboard":  "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2 M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z",

    # Badges (for goals/streaks)
    "medal":      "circle:12,9,6 | M8.21 13.89L7 23l5-3 5 3-1.21-9.12 M9 12l1.5 1.5L13 9",
    "ribbon":     "M12 2L9 9l-7 .5 5.5 5L6 22l6-3 6 3-1.5-7.5L22 9.5 15 9z",
    "badge":      "circle:12,12,10 | M12 8v8 M8 12h8",
    "milestone":  "M12 2v20 M5 12h14 M9 5l3-3 3 3",
}


# =====================================================================
# === ICON RENDERING ===
# =====================================================================
def icon_names() -> list[str]:
    """Return all available icon names."""
    return sorted(ICON_PATHS.keys())


def icon_exists(name: str) -> bool:
    """Return True if the given icon name exists."""
    return name in ICON_PATHS


def get_icon_path(name: str) -> str:
    """Return the raw SVG path data for the given icon name."""
    return ICON_PATHS.get(name, ICON_PATHS["info"])


# =====================================================================
# === DRAW ICON ON CANVAS ===
# =====================================================================
def draw_icon(canvas, x: float, y: float, size: float, name: str,
              color: str = "#E8E8E8", stroke_width: float = 2.0) -> None:
    """Draw an icon on a Tk Canvas at (x, y) with the given size.
    
    The icon is drawn within a `size` x `size` bounding box starting at (x, y).
    """
    path = ICON_PATHS.get(name)
    if not path:
        # Draw a fallback square
        canvas.create_rectangle(x, y, x + size, y + size, outline=color)
        return
    scale = size / 24.0
    # Parse path: split by " | " to get multiple commands
    for cmd in path.split(" | "):
        cmd = cmd.strip()
        if not cmd:
            continue
        try:
            if cmd.startswith("circle:"):
                # circle:cx,cy,r
                parts = cmd[7:].split(",")
                cx, cy, r = float(parts[0]), float(parts[1]), float(parts[2])
                _draw_circle(canvas, x + cx * scale, y + cy * scale, r * scale, color, stroke_width)
            elif cmd.startswith("rect:"):
                # rect:x,y,w,h,rx,ry  or  rect:x,y,w,h
                parts = cmd[5:].split(",")
                rx, ry, rw, rh = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                _draw_rect(canvas, x + rx * scale, y + ry * scale,
                           rw * scale, rh * scale, color, stroke_width)
            elif cmd.startswith("polygon:"):
                # polygon:x1,y1,x2,y2,...
                parts = cmd[8:].split(",")
                pts = []
                for i in range(0, len(parts), 2):
                    pts.append(x + float(parts[i]) * scale)
                    pts.append(y + float(parts[i + 1]) * scale)
                canvas.create_polygon(pts, fill="", outline=color, width=stroke_width)
            elif cmd.startswith("M") or cmd.startswith("L"):
                # SVG path — split by space and parse commands
                _draw_svg_path(canvas, cmd, x, y, scale, color, stroke_width)
        except (ValueError, IndexError):
            continue


def _draw_circle(canvas, cx: float, cy: float, r: float, color: str, width: float) -> None:
    """Draw a stroked circle on the canvas."""
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=color, width=width)


def _draw_rect(canvas, x: float, y: float, w: float, h: float,
               color: str, width: float, radius: float = 0) -> None:
    """Draw a stroked rectangle (optionally rounded) on the canvas."""
    canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=width)


def _draw_svg_path(canvas, path: str, x: float, y: float, scale: float,
                   color: str, width: float) -> None:
    """Draw a simple SVG path (M, L, H, V, Z) on a Tk Canvas.
    
    This is a minimal parser supporting the path syntax used in ICON_PATHS.
    Curves (C, S, Q, T, A) are approximated by treating them as line segments.
    """
    tokens = []
    current = ""
    for ch in path:
        if ch in "MLHVZCSQTAmlhvzcsqta":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(ch)
        elif ch == " " or ch == ",":
            if current:
                tokens.append(current)
                current = ""
        else:
            current += ch
    if current:
        tokens.append(current)
    # Parse tokens
    cx, cy = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    points = []
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd in ("M", "L"):
            while i < len(tokens) and not tokens[i].isalpha():
                x_val = float(tokens[i]); i += 1
                y_val = float(tokens[i]); i += 1
                cx, cy = x_val, y_val
                if cmd == "M":
                    start_x, start_y = cx, cy
                    points = [(cx, cy)]
                else:
                    points.append((cx, cy))
        elif cmd == "H":
            while i < len(tokens) and not tokens[i].isalpha():
                cx = float(tokens[i]); i += 1
                points.append((cx, cy))
        elif cmd == "V":
            while i < len(tokens) and not tokens[i].isalpha():
                cy = float(tokens[i]); i += 1
                points.append((cx, cy))
        elif cmd == "Z" or cmd == "z":
            points.append((start_x, start_y))
            cx, cy = start_x, start_y
        elif cmd in ("C", "S", "Q", "T", "A"):
            # Approximate curves: skip control points, take endpoint
            # Cubic: C x1,y1 x2,y2 x,y
            # Quadratic: Q x1,y1 x,y
            # Smooth: S x2,y2 x,y / T x,y
            # Arc: A rx,ry rot large,sweep x,y
            if cmd == "C":
                # Skip 4 numbers (2 control points), take last 2 as endpoint
                while i < len(tokens) and not tokens[i].isalpha():
                    # Each C takes 6 numbers (x1,y1,x2,y2,x,y)
                    try:
                        i += 4  # skip control points
                        cx = float(tokens[i]); i += 1
                        cy = float(tokens[i]); i += 1
                        points.append((cx, cy))
                    except (IndexError, ValueError):
                        break
            elif cmd == "Q":
                # Q x1,y1 x,y (4 numbers)
                while i < len(tokens) and not tokens[i].isalpha():
                    try:
                        i += 2  # skip control point
                        cx = float(tokens[i]); i += 1
                        cy = float(tokens[i]); i += 1
                        points.append((cx, cy))
                    except (IndexError, ValueError):
                        break
            elif cmd == "S" or cmd == "T":
                # S x2,y2 x,y (4 numbers) / T x,y (2 numbers)
                step = 4 if cmd == "S" else 2
                while i < len(tokens) and not tokens[i].isalpha():
                    try:
                        if cmd == "S":
                            i += 2  # skip control point
                        cx = float(tokens[i]); i += 1
                        cy = float(tokens[i]); i += 1
                        points.append((cx, cy))
                    except (IndexError, ValueError):
                        break
            elif cmd == "A":
                # A rx,ry rotation large_arc sweep x,y (7 numbers)
                while i < len(tokens) and not tokens[i].isalpha():
                    try:
                        i += 5  # skip rx,ry,rot,large,sweep
                        cx = float(tokens[i]); i += 1
                        cy = float(tokens[i]); i += 1
                        points.append((cx, cy))
                    except (IndexError, ValueError):
                        break
    # Draw lines connecting the points
    if len(points) >= 2:
        flat = []
        for px, py in points:
            flat.append(x + px * scale)
            flat.append(y + py * scale)
        canvas.create_line(flat, fill=color, width=width, smooth=True, joinstyle="round", capstyle="round")


# =====================================================================
# === ICON BITMAP (for buttons that need a real bitmap) ===
# =====================================================================
def icon_bitmap(name: str, size: int = 24) -> Optional[str]:
    """Return a bitmap for the given icon name (X11 bitmap format).
    
    Returns None if the icon name doesn't exist. Used for window icons.
    """
    # This is a placeholder — Tk doesn't make it easy to convert SVG paths to bitmaps.
    # For now, we return None and rely on draw_icon() for canvas rendering.
    return None


# =====================================================================
# === ICON ALIASES (for category icons) ===
# =====================================================================
CATEGORY_ICON_ALIASES = {
    "FOCUS":    "ring",
    "LEARN":    "book",
    "WORK":     "briefcase",
    "HEALTH":   "heart",
    "CREATIVE": "palette",
    "SOCIAL":   "users",
    "REST":     "moon",
}


def category_icon(category_key: str) -> str:
    """Return the icon name for a category key, with fallback to 'ring'."""
    return CATEGORY_ICON_ALIASES.get(category_key, "ring")
