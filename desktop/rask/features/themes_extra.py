"""
rask.features.themes_extra
==========================

Extended theme registry beyond the default gold-on-dark.

Eight themes are pre-registered:

  • ``midnight_gold``    — gold on matte black (default)
  • ``noir``             — white on pure black (high contrast)
  • ``rose_gold``        — rose gold on dark gray
  • ``emerald``          — emerald green on charcoal
  • ``sapphire``         — sapphire blue on charcoal
  • ``amber``            — amber on dark brown
  • ``minimal``          — monochrome (white on black)
  • ``persian_night``    — deep blue + gold accent

Each theme is a :class:`Theme` dataclass with:

  • ``name``             — internal id
  • ``display_name_fa``  — Persian display name
  • ``display_name_en``  — English display name
  • ``palette``          — dict of color name → hex
  • ``typography``       — dict of font scale + family overrides
  • ``spacing``          — dict of spacing scale overrides

:meth:`ThemeRegistry.apply` applies a theme to the running
CustomTkinter app by:

  • Setting the CTk appearance mode + color theme
  • Patching ``config`` module color constants (in-memory only)
  • Publishing ``theme.changed`` so widgets can re-render

Themes are designed to be safe to swap at runtime; the user's
preference is persisted in settings.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import config
from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception

__all__ = [
    "Theme",
    "ThemeRegistry",
    "theme_registry",
]

_log = get_logger("features.themes")


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class Theme:
    """A complete theme definition."""

    name: str
    display_name_fa: str
    display_name_en: str
    palette: Dict[str, str] = field(default_factory=dict)
    typography: Dict[str, Any] = field(default_factory=dict)
    spacing: Dict[str, int] = field(default_factory=dict)
    appearance_mode: str = "dark"  # dark | light | system

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# === Pre-registered themes                                                  ===
# =============================================================================

def _default_palette() -> Dict[str, str]:
    """Return the default gold-on-dark palette."""
    return {
        "matte_black": config.MATTE_BLACK,
        "charcoal": config.CHARCOAL,
        "surface": config.SURFACE,
        "surface_hi": config.SURFACE_HI,
        "surface_higher": config.SURFACE_HIGHER,
        "gold": config.GOLD,
        "gold_soft": config.GOLD_SOFT,
        "gold_dim": config.GOLD_DIM,
        "gold_bright": config.GOLD_BRIGHT,
        "gold_glow": config.GOLD_GLOW,
        "text": config.TEXT,
        "text_dim": config.TEXT_DIM,
        "text_faint": config.TEXT_FAINT,
        "text_muted": config.TEXT_MUTED,
        "success": config.SUCCESS,
        "warning": config.WARNING,
        "danger": config.DANGER,
        "info": config.INFO,
        "divider": config.DIVIDER,
    }


THEME_MIDNIGHT_GOLD: Theme = Theme(
    name="midnight_gold",
    display_name_fa="طلایی نیمه‌شب",
    display_name_en="Midnight Gold",
    palette=_default_palette(),
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_NOIR: Theme = Theme(
    name="noir",
    display_name_fa="نوآر",
    display_name_en="Noir",
    palette={
        "matte_black": "#000000",
        "charcoal": "#0A0A0A",
        "surface": "#141414",
        "surface_hi": "#1F1F1F",
        "surface_higher": "#2A2A2A",
        "gold": "#FFFFFF",
        "gold_soft": "#E0E0E0",
        "gold_dim": "#707070",
        "gold_bright": "#FFFFFF",
        "gold_glow": "#FFFFFF",
        "text": "#FFFFFF",
        "text_dim": "#C0C0C0",
        "text_faint": "#808080",
        "text_muted": "#404040",
        "success": "#FFFFFF",
        "warning": "#C0C0C0",
        "danger": "#FFFFFF",
        "info": "#FFFFFF",
        "divider": "#222222",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_ROSE_GOLD: Theme = Theme(
    name="rose_gold",
    display_name_fa="طلایی رز",
    display_name_en="Rose Gold",
    palette={
        "matte_black": "#1C1417",
        "charcoal": "#2A1F23",
        "surface": "#3A2C30",
        "surface_hi": "#4A3840",
        "surface_higher": "#5A4850",
        "gold": "#E8B4A8",
        "gold_soft": "#D49A8C",
        "gold_dim": "#8B6258",
        "gold_bright": "#F5C8BC",
        "gold_glow": "#FFE0D4",
        "text": "#F0E0DC",
        "text_dim": "#B89890",
        "text_faint": "#785850",
        "text_muted": "#4A3838",
        "success": "#A8C8A8",
        "warning": "#D4B4A8",
        "danger": "#D4625A",
        "info": "#A8B4D4",
        "divider": "#3A2C30",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_EMERALD: Theme = Theme(
    name="emerald",
    display_name_fa="زمردی",
    display_name_en="Emerald",
    palette={
        "matte_black": "#0E1410",
        "charcoal": "#1A221C",
        "surface": "#222B25",
        "surface_hi": "#2C3530",
        "surface_higher": "#34403A",
        "gold": "#4ADE80",
        "gold_soft": "#3FBF70",
        "gold_dim": "#2A8050",
        "gold_bright": "#6FF0A0",
        "gold_glow": "#A0FFC8",
        "text": "#E8F0E8",
        "text_dim": "#9AB8A0",
        "text_faint": "#5C7860",
        "text_muted": "#3F5444",
        "success": "#4ADE80",
        "warning": "#F0C060",
        "danger": "#E06060",
        "info": "#60A0E0",
        "divider": "#2C3530",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_SAPPHIRE: Theme = Theme(
    name="sapphire",
    display_name_fa="یاقوتی",
    display_name_en="Sapphire",
    palette={
        "matte_black": "#0E1014",
        "charcoal": "#1A1F26",
        "surface": "#222830",
        "surface_hi": "#2C323A",
        "surface_higher": "#343C44",
        "gold": "#7B9BC9",
        "gold_soft": "#6A88B0",
        "gold_dim": "#3F5C80",
        "gold_bright": "#A0C0E8",
        "gold_glow": "#C8D8F0",
        "text": "#E8EEF4",
        "text_dim": "#9AAEC0",
        "text_faint": "#5C6E80",
        "text_muted": "#3F4F60",
        "success": "#7BC97B",
        "warning": "#E8B85A",
        "danger": "#D4625A",
        "info": "#7B9BC9",
        "divider": "#2C323A",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_AMBER: Theme = Theme(
    name="amber",
    display_name_fa="کهربایی",
    display_name_en="Amber",
    palette={
        "matte_black": "#1A1410",
        "charcoal": "#241C16",
        "surface": "#2E2520",
        "surface_hi": "#382E26",
        "surface_higher": "#42372E",
        "gold": "#FFA040",
        "gold_soft": "#E08830",
        "gold_dim": "#805020",
        "gold_bright": "#FFC060",
        "gold_glow": "#FFE0A0",
        "text": "#F0E0D0",
        "text_dim": "#B89878",
        "text_faint": "#786050",
        "text_muted": "#4A3A30",
        "success": "#A0C870",
        "warning": "#F0A040",
        "danger": "#E06040",
        "info": "#60A0C0",
        "divider": "#382E26",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_MINIMAL: Theme = Theme(
    name="minimal",
    display_name_fa="مینیمال",
    display_name_en="Minimal",
    palette={
        "matte_black": "#000000",
        "charcoal": "#0A0A0A",
        "surface": "#161616",
        "surface_hi": "#202020",
        "surface_higher": "#2A2A2A",
        "gold": "#F5F5F5",
        "gold_soft": "#D0D0D0",
        "gold_dim": "#707070",
        "gold_bright": "#FFFFFF",
        "gold_glow": "#FFFFFF",
        "text": "#F5F5F5",
        "text_dim": "#A0A0A0",
        "text_faint": "#707070",
        "text_muted": "#404040",
        "success": "#F5F5F5",
        "warning": "#A0A0A0",
        "danger": "#FFFFFF",
        "info": "#D0D0D0",
        "divider": "#222222",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_PERSIAN_NIGHT: Theme = Theme(
    name="persian_night",
    display_name_fa="شب ایرانی",
    display_name_en="Persian Night",
    palette={
        "matte_black": "#0A0E2A",
        "charcoal": "#141838",
        "surface": "#1E2248",
        "surface_hi": "#282C58",
        "surface_higher": "#323668",
        "gold": "#D4AF37",
        "gold_soft": "#C9A84C",
        "gold_dim": "#7A6620",
        "gold_bright": "#F0CE6B",
        "gold_glow": "#FFE89A",
        "text": "#E8E8F0",
        "text_dim": "#9A9AB0",
        "text_faint": "#5C5C78",
        "text_muted": "#3F3F58",
        "success": "#7BC97B",
        "warning": "#E8B85A",
        "danger": "#D4625A",
        "info": "#7B9BC9",
        "divider": "#282C58",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)


THEME_CYBER: Theme = Theme(
    name="cyber",
    display_name_fa="سایبر",
    display_name_en="Cyber",
    palette={
        "matte_black": "#0A0A14",
        "charcoal": "#14142A",
        "surface": "#1E1E3A",
        "surface_hi": "#28284E",
        "surface_higher": "#32326A",
        "gold": "#00FFCC",
        "gold_soft": "#00CCAA",
        "gold_dim": "#006655",
        "gold_bright": "#5FFFE0",
        "gold_glow": "#A0FFEE",
        "text": "#E0E0FF",
        "text_dim": "#8888B8",
        "text_faint": "#5C5C78",
        "text_muted": "#3F3F58",
        "success": "#00FFAA",
        "warning": "#FFAA00",
        "danger": "#FF3366",
        "info": "#0088FF",
        "divider": "#28284E",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "JetBrains Mono"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)

THEME_SUNSET: Theme = Theme(
    name="sunset",
    display_name_fa="غروب",
    display_name_en="Sunset",
    palette={
        "matte_black": "#1A0E14",
        "charcoal": "#2A1820",
        "surface": "#3A2228",
        "surface_hi": "#4A2C32",
        "surface_higher": "#5A3640",
        "gold": "#FF6B6B",
        "gold_soft": "#E05555",
        "gold_dim": "#803040",
        "gold_bright": "#FF8A8A",
        "gold_glow": "#FFB0B0",
        "text": "#F0E0E0",
        "text_dim": "#B89898",
        "text_faint": "#785858",
        "text_muted": "#4A3838",
        "success": "#7BC97B",
        "warning": "#FFB060",
        "danger": "#FF4040",
        "info": "#C0A0E0",
        "divider": "#4A2C32",
    },
    typography={"font_scale": 1.0, "family_fa": "Vazirmatn",
                 "family_en": "Inter"},
    spacing={"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32},
    appearance_mode="dark",
)


DEFAULT_THEMES: List[Theme] = [
    THEME_MIDNIGHT_GOLD,
    THEME_NOIR,
    THEME_ROSE_GOLD,
    THEME_EMERALD,
    THEME_SAPPHIRE,
    THEME_AMBER,
    THEME_MINIMAL,
    THEME_PERSIAN_NIGHT,
    THEME_CYBER,
    THEME_SUNSET,
]


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _palette_to_ctk_colors(palette: Dict[str, str]) -> Dict[str, Any]:
    """Convert a Rask palette into a CTk color theme dict.

    CTk color themes use the keys: ``CTk``, ``CTkFrame``, ``CTkButton``,
    etc.  We map the gold-on-dark palette to a sensible CTk theme.
    """
    return {
        "CTk": {
            "fg_color": palette["matte_black"],
            "bg_color": palette["matte_black"],
        },
        "CTkFrame": {
            "fg_color": palette["charcoal"],
            "top_fg_color": palette["surface"],
        },
        "CTkButton": {
            "fg_color": palette["gold"],
            "hover_color": palette["gold_soft"],
            "text_color": palette["matte_black"],
            "border_color": palette["gold_dim"],
        },
        "CTkLabel": {
            "fg_color": "transparent",
            "text_color": palette["text"],
        },
        "CTkEntry": {
            "fg_color": palette["surface"],
            "border_color": palette["surface_higher"],
            "text_color": palette["text"],
        },
        "CTkProgressBar": {
            "fg_color": palette["surface_hi"],
            "progress_color": palette["gold"],
        },
        "CTkSwitch": {
            "fg_color": palette["surface_hi"],
            "progress_color": palette["gold"],
            "button_color": palette["text"],
            "button_hover_color": palette["gold_soft"],
        },
    }


# =============================================================================
# === ThemeRegistry                                                          ===
# =============================================================================

class ThemeRegistry:
    """Registry + applier for themes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._themes: Dict[str, Theme] = {t.name: t for t in DEFAULT_THEMES}
        self._active: str = "midnight_gold"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, theme: Theme) -> None:
        """Register a new theme (overwrites if name exists)."""
        with self._lock:
            self._themes[theme.name] = theme

    def get(self, name: str) -> Optional[Theme]:
        with self._lock:
            return self._themes.get(name)

    def list(self) -> List[Theme]:
        with self._lock:
            return list(self._themes.values())

    def list_names(self) -> List[str]:
        with self._lock:
            return sorted(self._themes.keys())

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, name: str, root_widget: Optional[Any] = None) -> bool:
        """Apply the named theme.

        Patches the in-memory ``config`` module color constants and
        publishes ``theme.changed``.  If `root_widget` is given and
        CustomTkinter is available, also calls ``set_appearance_mode``
        on the CTk app.

        Returns True on success, False if the theme name is unknown.
        """
        theme = self.get(name)
        if theme is None:
            _log.warning("Unknown theme: %s", name)
            return False
        with self._lock:
            self._active = name
            # Patch config color constants.
            self._patch_config(theme)
            # Persist preference.
            try:
                db.setting_set("theme_extra", name)
            except Exception:  # noqa: BLE001
                pass
            # Apply to CTk if available.
            if root_widget is not None:
                self._apply_to_ctk(root_widget, theme)
        bus.publish("theme.changed", {
            "name": name,
            "appearance_mode": theme.appearance_mode,
        })
        _log.info("Theme applied: %s", name)
        return True

    def active(self) -> str:
        """Return the currently active theme name."""
        return self._active

    def active_theme(self) -> Theme:
        """Return the currently active Theme object."""
        return self.get(self._active) or THEME_MIDNIGHT_GOLD

    def restore_from_settings(self, root_widget: Optional[Any] = None) -> str:
        """Restore the saved theme (or the default if none saved)."""
        try:
            saved = db.setting_get("theme_extra", "midnight_gold")
            if saved and self.get(saved):
                self.apply(saved, root_widget=root_widget)
                return saved
        except Exception:  # noqa: BLE001
            pass
        return self._active

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _patch_config(self, theme: Theme) -> None:
        """Patch the in-memory ``config`` module color constants.

        This is intentionally a soft patch — we only touch the colors
        that the theme defines, and we leave defaults for the rest.
        """
        palette = theme.palette
        # Map our palette keys to config attributes.
        # We use a name->attribute lookup table.
        attr_map = {
            "matte_black": "MATTE_BLACK",
            "charcoal": "CHARCOAL",
            "surface": "SURFACE",
            "surface_hi": "SURFACE_HI",
            "surface_higher": "SURFACE_HIGHER",
            "gold": "GOLD",
            "gold_soft": "GOLD_SOFT",
            "gold_dim": "GOLD_DIM",
            "gold_bright": "GOLD_BRIGHT",
            "gold_glow": "GOLD_GLOW",
            "text": "TEXT",
            "text_dim": "TEXT_DIM",
            "text_faint": "TEXT_FAINT",
            "text_muted": "TEXT_MUTED",
            "success": "SUCCESS",
            "warning": "WARNING",
            "danger": "DANGER",
            "info": "INFO",
            "divider": "DIVIDER",
        }
        for key, attr in attr_map.items():
            if key in palette:
                try:
                    setattr(config, attr, palette[key])
                except Exception:  # noqa: BLE001
                    pass
        # Patch ALL_COLORS dict too.
        try:
            for k, v in palette.items():
                config.ALL_COLORS[k] = v
        except Exception:  # noqa: BLE001
            pass
        # Typography overrides
        ty = theme.typography
        if ty.get("font_scale"):
            try:
                config.DEFAULT_FONT_SCALE = float(ty["font_scale"])
            except Exception:  # noqa: BLE001
                pass

    def _apply_to_ctk(self, root: Any, theme: Theme) -> None:
        """Apply the theme to the CTk root widget."""
        try:
            import customtkinter as ctk  # type: ignore
            ctk.set_appearance_mode(theme.appearance_mode)
            # Build a CTk color theme from the palette.
            colors = _palette_to_ctk_colors(theme.palette)
            # CTk's set_default_color_theme expects a JSON file path, so we
            # take the simpler approach: just set the appearance mode and
            # let each widget read colors from `config` at render time.
            # (Widgets in this codebase read from `config` directly, so
            # the patching in _patch_config is sufficient.)
        except Exception as exc:  # noqa: BLE001
            _log.debug("CTk theme apply failed: %s", exc)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

theme_registry: ThemeRegistry = ThemeRegistry()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== themes_extra self-tests ===")
    try:
        names = theme_registry.list_names()
        assert len(names) >= 8, f"expected >=8 themes, got {len(names)}"
        assert "midnight_gold" in names
        # Apply each theme without crashing.
        original_active = theme_registry.active()
        for name in names:
            ok = theme_registry.apply(name)
            assert ok, f"apply({name!r}) failed"
            t = theme_registry.get(name)
            assert t is not None
        # Restore.
        theme_registry.apply(original_active)
        print(f"  OK   {len(names)} themes registered + applied")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
