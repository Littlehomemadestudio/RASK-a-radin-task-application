"""
rask.ui.widgets.avatars
=======================

Circular avatar widget with initials or image.

  * ``Avatar`` — circular avatar with optional decorative ring
  * Pre-set color palette derived from name hash (so the same name
    always gets the same colour — useful for category icons)
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

import customtkinter as ctk

from ... import config
from ...core import helpers
from ... import i18n
from . import theme as _theme

__all__ = ["Avatar", "AVATAR_COLORS"]


# =============================================================================
# === Pre-set colour palette                                                ===
# =============================================================================

AVATAR_COLORS: list[str] = [
    config.GOLD,
    config.CAT_LEARN,
    config.CAT_WORK,
    config.CAT_HEALTH,
    config.CAT_CREATIVE,
    config.CAT_SOCIAL,
    config.CAT_REST,
    "#D49ABF",
    "#9B7BD4",
    "#7BC9B8",
    "#E8B85A",
    "#C97B9B",
]


def color_for_name(name: str) -> str:
    """Return a stable colour from :data:`AVATAR_COLORS` based on `name` hash."""
    if not name:
        return config.GOLD
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(AVATAR_COLORS)
    return AVATAR_COLORS[idx]


def initials_for(name: str, max_chars: int = 2) -> str:
    """Return up to `max_chars` uppercase initials from `name`."""
    if not name:
        return "?"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        # First letter or first two letters
        s = parts[0]
        return s[0].upper() if max_chars == 1 else s[:2].upper()
    return "".join(p[0].upper() for p in parts[:max_chars])


# =============================================================================
# === Avatar                                                                ===
# =============================================================================

class Avatar(ctk.CTkFrame):
    """Circular avatar.

    Parameters
    ----------
    size
        Diameter in pixels.
    text
        Initials or short text shown in the centre.
    image_path
        Optional path to an image file (PNG/JPG).  When set, the image
        is shown cropped to a circle; ``text`` is ignored.
    color
        Background colour when no image is set.  Defaults to a colour
        derived from ``text``.
    ring_color
        Optional decorative ring around the avatar.
    ring_width
        Thickness of the ring in pixels.
    """

    def __init__(
        self,
        master: Any = None,
        size: int = 48,
        text: str = "",
        image_path: Optional[str] = None,
        color: Optional[str] = None,
        ring_color: Optional[str] = None,
        ring_width: int = 2,
        lang: str = "fa",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", size // 2)
        super().__init__(master, **kwargs)
        self._size = size
        self._text = text
        self._image_path = image_path
        self._color = color or color_for_name(text)
        self._ring_color = ring_color
        self._ring_width = ring_width
        self._lang = lang
        # Inner frame holds the coloured circle / image
        self._inner = ctk.CTkFrame(
            self,
            width=size, height=size,
            fg_color=self._color,
            corner_radius=size // 2,
            border_width=ring_width if ring_color else 0,
            border_color=ring_color or "",
        )
        self._inner.place(relx=0.5, rely=0.5, anchor="center")
        # Label for initials
        self._label = ctk.CTkLabel(
            self._inner,
            text=initials_for(text),
            font=_theme.theme.font(size=int(size * 0.4),
                                    weight="bold", lang=lang),
            text_color=config.MATTE_BLACK,
        )
        self._label.place(relx=0.5, rely=0.5, anchor="center")
        if image_path:
            self._load_image(image_path)

    # ------------------------------------------------------------------
    def _load_image(self, path: str) -> None:
        try:
            from PIL import Image, ImageTk, ImageDraw
            img = Image.open(path).resize((self._size, self._size),
                                            Image.LANCZOS)
            # Apply a circular mask
            mask = Image.new("L", (self._size, self._size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, self._size, self._size), fill=255)
            img.putalpha(mask)
            # Convert to CTkImage-compatible
            try:
                photo = ctk.CTkImage(
                    light_image=img, dark_image=img,
                    size=(self._size, self._size),
                )
                self._label.configure(image=photo, text="")
                self._label.image = photo  # type: ignore[attr-defined]
            except Exception:
                # Fallback: use plain PhotoImage on inner label
                photo = ImageTk.PhotoImage(img)
                self._label.configure(image=photo, text="")
                self._label.image = photo  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_image(self, path: str) -> None:
        self._image_path = path
        self._load_image(path)

    def set_initials(self, name: str) -> None:
        self._text = name
        try:
            self._label.configure(text=initials_for(name))
        except Exception:
            pass

    def set_color(self, color: str) -> None:
        self._color = color
        try:
            self._inner.configure(fg_color=color)
        except Exception:
            pass

    def set_ring(self, color: Optional[str], width: int = 2) -> None:
        self._ring_color = color
        self._ring_width = width
        try:
            self._inner.configure(border_width=width if color else 0,
                                   border_color=color or "")
        except Exception:
            pass


def _self_test() -> int:
    classes = [Avatar]
    print(f"Avatars module: {len(classes)} classes registered.")
    # Smoke-test helpers
    assert initials_for("Ali Reza") == "AR"
    assert initials_for("Ali") == "AL"
    assert initials_for("Ali", max_chars=1) == "A"
    assert color_for_name("Ali") == color_for_name("Ali")
    print("Initials + color_for_name OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
