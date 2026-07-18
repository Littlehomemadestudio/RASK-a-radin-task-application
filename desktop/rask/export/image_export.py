"""
rask.export.image_export
========================

Image (PNG) exporter for Rask.

Three modes:

* :meth:`ImageExporter.export_chart`     — screenshot of a single
  CTkCanvas-based chart widget (uses Pillow's ``ImageGrab``)
* :meth:`ImageExporter.export_dashboard`  — screenshot of a full
  dashboard frame (any CTk widget with ``winfo_id()``)
* :meth:`ImageExporter.export_report`    — composed image with title,
  stats text, and one or more chart images laid out vertically

All output uses the in-app gold-on-dark palette.  The composed
report image is built with Pillow's ``Image`` / ``ImageDraw`` /
``ImageFont`` — no Tk involvement required, so it can run from a
background thread.

Persian font handling
---------------------
Same as the PDF exporter — we probe for ``Vazirmatn.ttf`` and fall
back to ``Tahoma`` / ``Arial``.  Persian shaping is best-effort:
Pillow's default text layout does not do full RTL shaping, so
Persian text in the composed report may look slightly off.  For
production use we recommend the chart-only export mode.

Mirrors the PNG export path in
:mod:`rask.services.export_service` (which delegates here for the
composed-report use case).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .. import config
from .. import i18n
from ..core.logging_utils import get_logger

__all__ = ["ImageExporter"]

_log = get_logger("export.image")


# =============================================================================
# === Optional dependencies                                                  ===
# =============================================================================

try:
    from PIL import Image, ImageDraw, ImageFont, ImageGrab  # type: ignore[import-not-found]
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover — optional dep
    _PIL_AVAILABLE = False


# =============================================================================
# === Font helpers                                                            ===
# =============================================================================

_FONT_CANDIDATES: Tuple[str, ...] = (
    "Vazirmatn", "Tahoma", "Segoe UI", "Noto Sans", "DejaVu Sans", "Arial",
)


def _find_font_file() -> Optional[str]:
    """Locate a TrueType font file on the system.

    Returns ``None`` if no suitable font is found — Pillow then falls
    back to its built-in bitmap font.
    """
    # 1. Bundled
    try:
        bundled = Path(__file__).resolve().parents[1] / "assets" / "fonts"
        if bundled.is_dir():
            for ttf in sorted(bundled.glob("*.ttf")):
                return str(ttf)
    except Exception:  # noqa: BLE001
        pass
    # 2. Platform dirs
    candidates = [
        Path.home() / ".local" / "share" / "fonts",
        Path("/usr/share/fonts/truetype"),
        Path("/usr/local/share/fonts"),
        Path("C:/Windows/Fonts"),
        Path.home() / "Library" / "Fonts",
    ]
    name_priority = ("vazir", "tahoma", "arial", "dejavusans", "liberationsans")
    found: List[Tuple[int, str]] = []
    for d in candidates:
        if not d.is_dir():
            continue
        try:
            for ttf in d.rglob("*.ttf"):
                name = ttf.stem.lower().replace("-", "").replace("_", "")
                for i, key in enumerate(name_priority):
                    if name.startswith(key):
                        found.append((i, str(ttf)))
                        break
        except (PermissionError, OSError):
            continue
    if found:
        found.sort()
        return found[0][1]
    return None


def _load_font(size: int = 18) -> Any:
    """Return a Pillow font object of the requested size.

    Falls back to the default bitmap font if no TTF is available.
    """
    if not _PIL_AVAILABLE:
        return None
    path = _find_font_file()
    if path and os.path.isfile(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 — defensive
            pass
    try:
        return ImageFont.load_default()
    except Exception:  # noqa: BLE001
        return None


def _hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert ``"#RRGGBB"`` to an ``(r, g, b)`` 0-255 tuple."""
    h = (hex_str or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (14, 14, 16)  # MATTE_BLACK fallback
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (14, 14, 16)


# =============================================================================
# === ImageExporter                                                            ===
# =============================================================================

class ImageExporter:
    """Reusable image exporter.

    Parameters
    ----------
    file_path
        Destination path.  Parent directories are created on save.

    Examples
    --------
    >>> exp = ImageExporter("/tmp/chart.png")
    >>> exp.export_chart(bar_chart_widget)
    True
    """

    def __init__(self, file_path: Union[str, Path]) -> None:
        if not _PIL_AVAILABLE:
            raise RuntimeError(
                "Pillow is not installed — install it with "
                "`pip install Pillow` to enable image export")
        self._path: Path = Path(file_path)
        self._font_title = _load_font(28)
        self._font_body = _load_font(16)
        self._font_small = _load_font(12)
        self._lang: str = "fa"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_chart(
        self,
        canvas_widget: Any,
        fmt: str = "png",
    ) -> bool:
        """Save a screenshot of a Tk widget as an image file.

        The widget must be realised (mapped on screen) — call
        ``update_idletasks()`` first if in doubt.

        Parameters
        ----------
        canvas_widget
            Any Tk widget with ``winfo_rootx`` / ``winfo_rooty`` /
            ``winfo_width`` / ``winfo_height``.
        fmt
            Output format: ``"png"`` (default), ``"jpg"``, ``"webp"``.
        """
        if canvas_widget is None:
            _log.error("export_chart: canvas_widget is None")
            return False
        fmt = (fmt or "png").lower()
        try:
            canvas_widget.update_idletasks()
            x = canvas_widget.winfo_rootx()
            y = canvas_widget.winfo_rooty()
            w = max(1, canvas_widget.winfo_width())
            h = max(1, canvas_widget.winfo_height())
            bbox = (x, y, x + w, y + h)
            img = ImageGrab.grab(bbox=bbox)
        except Exception as exc:  # noqa: BLE001 — ImageGrab errors
            _log.error("export_chart: ImageGrab failed: %s", exc)
            return False
        return self._write(img, fmt)

    def export_dashboard(self, widget: Any, fmt: str = "png") -> bool:
        """Save a screenshot of a full dashboard widget.

        Identical to :meth:`export_chart` (kept as a separate method
        for API clarity — the spec asks for both).
        """
        return self.export_chart(widget, fmt=fmt)

    def export_report(
        self,
        stats: Dict[str, Any],
        charts: Sequence[Union[str, Path]],
        file_path: Optional[Union[str, Path]] = None,
        *,
        title: str = "",
        lang: str = "fa",
        width: int = 800,
    ) -> bool:
        """Compose a single PNG with title, stats text, and chart images.

        Parameters
        ----------
        stats
            Dict of label -> value (displayed as a left-aligned list).
        charts
            Sequence of paths to existing PNG files (e.g. produced by
            :meth:`export_chart` earlier).  They are stacked vertically
            below the stats block.
        file_path
            Override the instance-level output path (useful when
            composing multiple reports in a loop).
        title
            Optional big title rendered at the top of the image.
        lang
            UI language.  Default ``"fa"``.
        width
            Image width in pixels.  Default 800.

        Returns True on success.
        """
        self._lang = lang if lang in config.SUPPORTED_LANGUAGES else "fa"
        out_path = Path(file_path) if file_path else self._path
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error("Cannot create parent dir for %s: %s", out_path, exc)
            return False
        matte = _hex_to_rgb(config.MATTE_BLACK)
        charcoal = _hex_to_rgb(config.CHARCOAL)
        gold = _hex_to_rgb(config.GOLD)
        text_color = _hex_to_rgb(config.TEXT)
        text_dim = _hex_to_rgb(config.TEXT_DIM)
        divider = _hex_to_rgb(config.DIVIDER)

        # Pre-load chart images and measure their heights
        chart_imgs: List[Any] = []
        for cp in charts:
            try:
                ci = Image.open(str(cp)).convert("RGB")
                # Scale to fit width
                if ci.width > width - 40:
                    new_h = int(ci.height * (width - 40) / ci.width)
                    ci = ci.resize((width - 40, new_h), Image.LANCZOS)
                chart_imgs.append(ci)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Could not open chart image %s: %s", cp, exc)

        # Compute total image height
        pad = 20
        title_h = 60 if title else 0
        stats_h = max(80, 30 + len(stats) * 26)
        charts_h = sum(ci.height + 12 for ci in chart_imgs)
        total_h = pad + title_h + stats_h + 20 + charts_h + pad

        # Create canvas
        img = Image.new("RGB", (width, total_h), matte)
        draw = ImageDraw.Draw(img)
        # Title
        y = pad
        if title:
            draw.text((pad, y), title, fill=gold, font=self._font_title)
            y += title_h
            draw.line([(pad, y), (width - pad, y)], fill=divider, width=1)
            y += 10
        # Stats
        draw.text((pad, y), "Stats" if lang != "fa" else "آمار",
                   fill=gold, font=self._font_body)
        y += 30
        for label, value in stats.items():
            label_str = str(label)
            value_str = self._format_value(value)
            line = f"• {label_str}: {value_str}"
            draw.text((pad + 4, y), line, fill=text_color, font=self._font_body)
            y += 26
        y += 10
        draw.line([(pad, y), (width - pad, y)], fill=divider, width=1)
        y += 14
        # Charts
        for ci in chart_imgs:
            img.paste(ci, (pad, y))
            y += ci.height + 12
        # Footer
        footer = f"{config.APP_NAME} v{config.APP_VERSION} • {datetime.now().strftime('%Y-%m-%d')}"
        draw.text((pad, total_h - 20), footer, fill=text_dim,
                   font=self._font_small)
        return self._write_to(img, out_path, "png")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_value(self, v: Any) -> str:
        """Format a scalar for the stats block."""
        if v is None:
            return "—"
        if isinstance(v, bool):
            return "بله" if v else "خیر" if self._lang == "fa" else (
                "Yes" if v else "No")
        if isinstance(v, dict):
            if "total_min" in v:
                return self._fmt_duration(int(v["total_min"]))
            if "duration_min" in v:
                return self._fmt_duration(int(v["duration_min"]))
            if "date_iso" in v:
                return str(v["date_iso"])
            return str(v)
        if isinstance(v, float):
            s = f"{v:.1f}" if not v.is_integer() else str(int(v))
            return i18n.to_fa_digits(s) if self._lang == "fa" else s
        if isinstance(v, int):
            s = str(v)
            return i18n.to_fa_digits(s) if self._lang == "fa" else s
        return str(v)

    def _fmt_duration(self, minutes: int) -> str:
        try:
            minutes = int(minutes or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            return "—"
        h, m = divmod(minutes, 60)
        if self._lang == "fa":
            s = (f"{h} ساعت و {m} دقیقه" if h > 0 else f"{m} دقیقه")
            return i18n.to_fa_digits(s)
        return f"{h}h {m}m" if h > 0 else f"{m}m"

    def _write(self, img: Any, fmt: str) -> bool:
        """Save an image to the instance path."""
        return self._write_to(img, self._path, fmt)

    def _write_to(self, img: Any, path: Path, fmt: str) -> bool:
        """Save an image to an explicit path."""
        fmt = (fmt or "png").lower()
        if fmt == "jpg":
            fmt = "JPEG"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(path), fmt)
        except (OSError, ValueError, KeyError) as exc:
            _log.error("Failed to write image %s: %s", path, exc)
            return False
        size = path.stat().st_size if path.exists() else 0
        _log.info("Image written: %s (%d bytes, %s)", path, size, fmt)
        return True


# =============================================================================
# === Self-test                                                                ===
# =============================================================================

def _self_test() -> int:
    """Run with:  python -m rask.export.image_export"""
    if not _PIL_AVAILABLE:
        print("SKIP: Pillow not installed")
        return 0
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "report.png")
        try:
            exp = ImageExporter(path)
            ok = exp.export_report(
                stats={"total_min": 240, "total_activities": 5,
                       "best_day": {"date_iso": "2025-07-18", "total_min": 90}},
                charts=[],
                title="Test Report",
                lang="en",
            )
            if ok:
                size = os.path.getsize(path)
                print(f"OK: report.png written ({size} bytes)")
            else:
                print("FAIL: export_report returned False")
                return 1
        except Exception as exc:  # noqa: BLE001 — defensive
            print(f"FAIL: {exc}")
            return 1
    print("image_export self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
