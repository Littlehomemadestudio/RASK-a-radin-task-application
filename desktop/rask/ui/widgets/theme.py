"""
rask.ui.widgets.theme
=====================

CustomTkinter theme manager for the Rask desktop app.

Provides a single ``ThemeManager`` singleton (imported as ``theme``) that:

  * calls ``ctk.set_appearance_mode("dark")`` and overrides the default
    blue theme with our gold-on-dark palette
  * registers Persian (Vazirmatn) and English (Inter) fonts from the
    system, with a graceful fallback chain
  * exposes ``font(family, size, weight, lang)`` returning a
    :class:`ctk.CTkFont` instance
  * exposes ``color(name)`` to look up any color from
    :data:`rask.config.ALL_COLORS`
  * provides ``pad()`` and ``margin()`` helpers to apply uniform spacing
    to a widget without writing ``grid_configure`` boilerplate

The module is import-safe — every side-effecting call (font registration,
appearance mode change) is wrapped in try/except so importing this module
from any thread or test never crashes.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import customtkinter as ctk
    _CTK_OK: bool = True
except Exception:  # pragma: no cover — CTk may be unavailable in CI
    ctk = None  # type: ignore[assignment]
    _CTK_OK = False

from ... import config
from ...core import helpers
from ... import i18n

__all__ = [
    "ThemeManager",
    "theme",
    "get_font",
    "GOLD",
    "MATTE_BLACK",
]


# =============================================================================
# === Font registration helpers                                              ===
# =============================================================================

# Cache of families we've already located on the system.
_FAMILY_CACHE: Dict[str, Optional[str]] = {}


def _available_families() -> List[str]:
    """Return the list of font families installed on the system.

    Returns an empty list if Tk is not yet initialised (e.g. at import
    time before ``Tk()`` has been constructed).  This is fine — the
    caller falls back to ``None`` which makes CTk pick a default.
    """
    try:
        # ``tkfont.families`` needs a Tk root — use the hidden default root
        # if one exists, otherwise skip silently.
        if not tk._default_root:  # type: ignore[attr-defined]
            return []
        from tkinter import font as tkfont
        return list(tkfont.families())
    except Exception:
        return []


def _find_family(candidates: Tuple[str, ...]) -> Optional[str]:
    """Return the first family in ``candidates`` that exists on this system."""
    if not candidates:
        return None
    cache_key = "|".join(candidates)
    if cache_key in _FAMILY_CACHE:
        return _FAMILY_CACHE[cache_key]
    available = set(_available_families())
    chosen: Optional[str] = None
    for fam in candidates:
        if fam in available:
            chosen = fam
            break
    _FAMILY_CACHE[cache_key] = chosen
    return chosen


def _register_font_dir() -> None:
    """Add ``rask/assets/fonts`` to the fontconfig / Tk search path.

    Best-effort — if no font files exist this is a no-op.  On Windows
    we can use ``win32api`` to install fonts per-user; on Linux we rely
    on fontconfig picking up files placed in ``~/.local/share/fonts``.
    For portability we just attempt to load any ``.ttf`` we find into
    the Tk default root via ``tkfont.Font``.
    """
    try:
        fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        if not fonts_dir.is_dir():
            return
        if not tk._default_root:  # type: ignore[attr-defined]
            return
        from tkinter import font as tkfont
        for ttf in fonts_dir.glob("*.ttf"):
            try:
                # Tk's ``font_names`` cannot register a file directly,
                # but on X11 we can use ``fontconfig`` via the system.
                # As a cross-platform no-op fallback, we register a
                # named family pointing at the file when possible.
                tkfont.Font(name=ttf.stem, file=str(ttf), family=ttf.stem)
            except Exception:
                pass
    except Exception:
        pass


# =============================================================================
# === ThemeManager                                                          ===
# =============================================================================

class ThemeManager:
    """Centralised theme + font + spacing manager.

    Use the module-level ``theme`` singleton rather than instantiating
    directly — there is no benefit to having more than one.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self) -> None:
        self._mode: str = "dark"
        self._fonts_registered: bool = False
        self._applied: bool = False
        # Map weight strings -> tk font weight constants.
        self._weight_map: Dict[str, str] = {
            "light": "normal",
            "normal": "normal",
            "bold": "bold",
            "black": "bold",
        }
        # Cached CTkFont instances keyed by (family, size, weight).
        self._font_cache: Dict[Tuple[Optional[str], int, str], Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def apply(self, root: Any = None) -> None:
        """Apply the dark gold theme to CTk globally.

        Safe to call multiple times — subsequent calls are no-ops after
        the first successful application.
        """
        if not _CTK_OK:
            return
        try:
            ctk.set_appearance_mode("dark")
            # CTk ships a "dark-blue" / "blue" / "green" JSON theme.  We
            # pick "dark-blue" as the closest base, then override the
            # colours at the widget level via our own classes.
            try:
                ctk.set_default_color_theme("dark-blue")
            except Exception:
                pass
        except Exception:
            pass
        self._applied = True

    def setup_appearance(self, mode: str = "dark") -> None:
        """Switch the global CTk appearance mode (dark/light/system)."""
        if not _CTK_OK:
            return
        mode = mode if mode in ("dark", "light", "system") else "dark"
        self._mode = mode
        try:
            ctk.set_appearance_mode(mode)
        except Exception:
            pass

    def register_fonts(self) -> None:
        """Probe the system for Vazirmatn / Inter and cache the result.

        Idempotent — calling repeatedly is cheap (the family lookup is
        cached after the first call).
        """
        if self._fonts_registered:
            return
        _register_font_dir()
        _find_family(config.FONT_FAMILIES_FA)
        _find_family(config.FONT_FAMILIES_EN)
        _find_family(config.FONT_FAMILIES_MONO)
        self._fonts_registered = True

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------
    def font_family(self, lang: str = "fa") -> str:
        """Return the best available font family for `lang`."""
        if lang in ("fa", "ar", "ur", "ps"):
            candidates = config.FONT_FAMILIES_FA
        elif lang == "mono":
            candidates = config.FONT_FAMILIES_MONO
        else:
            candidates = config.FONT_FAMILIES_EN
        fam = _find_family(candidates)
        return fam or candidates[0]

    def font(
        self,
        family: Optional[str] = None,
        size: Optional[int] = None,
        weight: str = "normal",
        lang: str = "fa",
    ) -> Any:
        """Return a cached :class:`ctk.CTkFont`.

        ``size`` defaults to :data:`config.FONT_SIZE_DEFAULT`.
        ``weight`` may be ``"light"``, ``"normal"``, ``"bold"``, or
        ``"black"`` (the latter two collapse to ``bold``).
        """
        if not _CTK_OK:
            return None
        if not self._fonts_registered:
            self.register_fonts()
        if family is None:
            family = self.font_family(lang)
        if size is None:
            size = config.FONT_SIZE_DEFAULT
        weight = self._weight_map.get(weight, "normal")
        key = (family, int(size), weight)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        try:
            f = ctk.CTkFont(
                family=family,
                size=int(size),
                weight=weight,
            )
        except Exception:
            f = ctk.CTkFont(size=int(size), weight=weight)
        self._font_cache[key] = f
        return f

    def color(self, name: str, default: Optional[str] = None) -> str:
        """Look up a color by name from :data:`config.ALL_COLORS`.

        Names are case-insensitive and accept both ``"gold"`` and
        ``"GOLD"`` forms.  Returns ``default`` (or ``config.TEXT`` if
        ``default`` is None) when the name is unknown.
        """
        if not name:
            return default or config.TEXT
        key = name.lower().strip()
        if key in config.ALL_COLORS:
            return config.ALL_COLORS[key]
        # Allow "GOLD" without lowercasing if user passed an upper name
        upper = name.upper()
        if hasattr(config, upper):
            val = getattr(config, upper)
            if isinstance(val, str) and val.startswith("#"):
                return val
        return default or config.TEXT

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def pad(
        self,
        widget: Any,
        *args: int,
        **kwargs: int,
    ) -> Any:
        """Apply uniform padding to `widget` via ``grid_configure``.

        Accepts either positional ``pad(w, h)`` or keyword
        ``pad(widget, padx=8, pady=8)``.  Returns the widget so the
        call can be chained: ``theme.pad(GoldButton(...), 8).pack(...)``.
        """
        if not args and not kwargs:
            return widget
        if args:
            # Positional form: pad(x, y) or pad(x)
            padx = args[0]
            pady = args[1] if len(args) > 1 else args[0]
            kwargs.setdefault("padx", padx)
            kwargs.setdefault("pady", pady)
        try:
            widget.grid_configure(**kwargs)
        except Exception:
            try:
                widget.pack_configure(**kwargs)
            except Exception:
                pass
        return widget

    def margin(self, widget: Any, *args: int, **kwargs: int) -> Any:
        """Alias for :meth:`pad` — Tk treats padding and margin the same."""
        return self.pad(widget, *args, **kwargs)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self._mode != "light"

    def radius(self, name: str = "md") -> int:
        """Return a corner-radius integer by short name."""
        return {
            "sm": config.RADIUS_SM,
            "md": config.RADIUS_MD,
            "lg": config.RADIUS_LG,
            "xl": config.RADIUS_XL,
            "pill": config.RADIUS_PILL,
        }.get(name, config.RADIUS_MD)

    def space(self, name: str = "md") -> int:
        """Return a spacing integer by short name."""
        return {
            "xs": config.SPACE_XS,
            "sm": config.SPACE_SM,
            "md": config.SPACE_MD,
            "lg": config.SPACE_LG,
            "xl": config.SPACE_XL,
            "xxl": config.SPACE_XXL,
            "xxxl": config.SPACE_XXXL,
        }.get(name, config.SPACE_MD)


# Module-level singleton — always import this, never instantiate.
theme = ThemeManager()


# =============================================================================
# === Module-level helpers                                                   ===
# =============================================================================

def get_font(
    size: int,
    weight: str = "normal",
    lang: str = "fa",
) -> Tuple[Any, str]:
    """Return a ``(CTkFont, color)`` pair for quick label styling.

    The colour is :data:`config.TEXT` for normal weight, or
    :data:`config.GOLD` for bold/black weight — a common idiom in our
    gold-on-dark UI where emphasis == gold.
    """
    f = theme.font(size=size, weight=weight, lang=lang)
    color = config.GOLD if weight in ("bold", "black") else config.TEXT
    return f, color


def _init_module() -> None:
    """Run safe side-effects at import time.

    We do NOT call ``set_appearance_mode`` here because that requires
    a Tk root on some platforms.  ``theme.apply()`` should be called
    explicitly from the app's bootstrap code (``rask.app``).
    """
    theme.register_fonts()


_init_module()


# Re-export the most-used colours for star-import convenience.
GOLD = config.GOLD
MATTE_BLACK = config.MATTE_BLACK
CHARCOAL = config.CHARCOAL
SURFACE = config.SURFACE
SURFACE_HI = config.SURFACE_HI
TEXT = config.TEXT
TEXT_DIM = config.TEXT_DIM
TEXT_FAINT = config.TEXT_FAINT
GOLD_SOFT = config.GOLD_SOFT
GOLD_DIM = config.GOLD_DIM
GOLD_BRIGHT = config.GOLD_BRIGHT
SUCCESS = config.SUCCESS
WARNING = config.WARNING
DANGER = config.DANGER
INFO = config.INFO
DIVIDER = config.DIVIDER
