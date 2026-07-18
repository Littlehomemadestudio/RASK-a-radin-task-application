"""
rask.services.export_service
============================

Export activities to PDF / CSV / JSON / PNG.

Mirrors ``web/js/export-pdf.js`` and ``web/js/export-csv.js``.  All
exports are written to :data:`config.EXPORT_DIR` by default and
logged via :func:`rask.database.log_export`.

PDF generation uses ``reportlab``.  CSV is UTF-8 with BOM
(:data:`config.EXPORT_CSV_ENCODING`) so Excel opens it correctly.
JSON is UTF-8 with ``ensure_ascii=False`` to preserve Persian glyphs.

PNG export uses Pillow (PIL) to grab a screenshot of a Tk widget —
useful for saving chart screenshots.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_utc, today_iso
from ..core.validators import is_valid_iso_date

__all__ = ["ExportService", "export_service"]

_log = get_logger("services.export")


# =============================================================================
# === Optional dependencies                                                 ===
# =============================================================================

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REPORTLAB_AVAILABLE = False

try:
    from PIL import ImageGrab  # type: ignore[import-not-found]
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _filename(prefix: str, ext: str, date_from: str, date_to: str) -> str:
    """Build an export filename."""
    return f"{prefix}_{date_from}_to_{date_to}.{ext}"


def _hex_to_reportlab_color(hex_str: str):
    """Convert a hex color string to a reportlab color object."""
    if not _REPORTLAB_AVAILABLE:
        return None
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return colors.black
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return colors.Color(r, g, b)
    except ValueError:
        return colors.black


def _categories_map() -> Dict[int, Dict[str, Any]]:
    """Return a dict: category_id -> category dict."""
    out: Dict[int, Dict[str, Any]] = {}
    try:
        for c in db.category_list(include_archived=True):
            out[int(c["id"])] = c
    except Exception as exc:  # noqa: BLE001
        log_exception(_log, exc, {})
    return out


# =============================================================================
# === ExportService                                                          ===
# =============================================================================

class ExportService:
    """Export activities to PDF / CSV / JSON / PNG."""

    def __init__(self) -> None:
        try:
            config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        _log.debug("ExportService initialized (dir=%s)", config.EXPORT_DIR)

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_csv(
        self,
        date_from: str,
        date_to: str,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export activities in the date range as a CSV file.

        Columns: ``date, jalali_date, title, category, duration_min,
        start_time, end_time, notes, tags, kind``.

        Encoding: UTF-8 with BOM (so Excel opens Persian text correctly).
        """
        if not is_valid_iso_date(date_from) or not is_valid_iso_date(date_to):
            return self._failure("pdf", "invalid date range")
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        try:
            rows = db.activity_list(date_from=date_from, date_to=date_to,
                                     limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return self._failure("csv", str(exc))

        if path is None:
            path = str(config.EXPORT_DIR / _filename(
                "rask_export", "csv", date_from, date_to))

        cats = _categories_map()
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with out_path.open("w", encoding=config.EXPORT_CSV_ENCODING,
                                newline="") as f:
                writer = csv.writer(f, delimiter=config.EXPORT_CSV_DELIMITER)
                writer.writerow([
                    "date", "jalali_date", "title", "category",
                    "duration_min", "start_time", "end_time",
                    "notes", "tags", "kind",
                ])
                for r in rows:
                    cat_id = r.get("category_id")
                    cat_name = ""
                    if cat_id and cat_id in cats:
                        c = cats[cat_id]
                        cat_name = c.get("name_en", "") or c.get("name_fa", "")
                    tags_raw = r.get("tags_json", "[]")
                    try:
                        tags_list = json.loads(tags_raw) if tags_raw else []
                    except (json.JSONDecodeError, TypeError):
                        tags_list = []
                    tags_str = ";".join(tags_list)
                    writer.writerow([
                        r.get("date_iso", ""),
                        r.get("jalali_iso", ""),
                        r.get("title", ""),
                        cat_name,
                        int(r.get("duration_min", 0) or 0),
                        (r.get("start_ts", "") or "")[11:19],
                        (r.get("end_ts", "") or "")[11:19],
                        r.get("notes", "") or "",
                        tags_str,
                        r.get("kind", "manual"),
                    ])
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_export("csv", path, None, None, False, str(exc))
            return self._failure("csv", str(exc), path)

        size = out_path.stat().st_size if out_path.exists() else 0
        db.log_export("csv", path, size, len(rows), True, None)
        self._set_last_export(path)
        result = {
            "kind": "csv", "path": path, "size": size,
            "record_count": len(rows), "success": True, "error": None,
        }
        bus.publish("export.completed", result)
        _log.info("CSV exported: %s (%d rows, %d bytes)",
                  path, len(rows), size)
        return result

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_json(
        self,
        date_from: str,
        date_to: str,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export activities in the date range as a JSON file."""
        if not is_valid_iso_date(date_from) or not is_valid_iso_date(date_to):
            return self._failure("json", "invalid date range")
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        try:
            rows = db.activity_list(date_from=date_from, date_to=date_to,
                                     limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return self._failure("json", str(exc))

        if path is None:
            path = str(config.EXPORT_DIR / _filename(
                "rask_export", "json", date_from, date_to))

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        cats = _categories_map()
        payload = {
            "meta": {
                "app": config.APP_NAME,
                "version": config.APP_VERSION,
                "exported_at": now_iso_utc(),
                "date_from": date_from,
                "date_to": date_to,
                "record_count": len(rows),
            },
            "activities": [],
        }
        for r in rows:
            cat_id = r.get("category_id")
            cat = cats.get(cat_id) if cat_id else None
            tags_raw = r.get("tags_json", "[]")
            try:
                tags_list = json.loads(tags_raw) if tags_raw else []
            except (json.JSONDecodeError, TypeError):
                tags_list = []
            payload["activities"].append({
                "id": r.get("id"),
                "date_iso": r.get("date_iso"),
                "jalali_iso": r.get("jalali_iso"),
                "title": r.get("title"),
                "category_id": cat_id,
                "category_name_en": cat.get("name_en") if cat else None,
                "category_name_fa": cat.get("name_fa") if cat else None,
                "duration_min": int(r.get("duration_min", 0) or 0),
                "start_ts": r.get("start_ts"),
                "end_ts": r.get("end_ts"),
                "notes": r.get("notes"),
                "tags": tags_list,
                "kind": r.get("kind"),
            })

        try:
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_export("json", path, None, None, False, str(exc))
            return self._failure("json", str(exc), path)

        size = out_path.stat().st_size if out_path.exists() else 0
        db.log_export("json", path, size, len(rows), True, None)
        self._set_last_export(path)
        result = {
            "kind": "json", "path": path, "size": size,
            "record_count": len(rows), "success": True, "error": None,
        }
        bus.publish("export.completed", result)
        _log.info("JSON exported: %s (%d rows, %d bytes)",
                  path, len(rows), size)
        return result

    # ------------------------------------------------------------------
    # PDF export
    # ------------------------------------------------------------------

    def export_pdf(
        self,
        date_from: str,
        date_to: str,
        path: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Export a PDF report.

        The PDF contains:
          • Header with title, date range, total time, activity count
          • Summary statistics (best day, longest session, etc.)
          • Per-category breakdown table
          • Per-day totals table
          • Top activities list

        ``options`` may include:
          ``lang``     — language code (default: current settings)
          ``include_charts`` — bool (default True)
          ``include_top_activities`` — bool (default True)
        """
        if not _REPORTLAB_AVAILABLE:
            msg = "reportlab not installed (pip install reportlab)"
            _log.error(msg)
            db.log_export("pdf", path, None, None, False, msg)
            return self._failure("pdf", msg, path)

        if not is_valid_iso_date(date_from) or not is_valid_iso_date(date_to):
            return self._failure("pdf", "invalid date range")
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        options = options or {}
        lang = options.get("lang", "fa")
        include_top = options.get("include_top_activities", True)

        try:
            rows = db.activity_list(date_from=date_from, date_to=date_to,
                                     limit=100000)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return self._failure("pdf", str(exc))

        if path is None:
            path = str(config.EXPORT_DIR / _filename(
                "rask_report", "pdf", date_from, date_to))

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._render_pdf(out_path, date_from, date_to, rows, lang,
                              include_top)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_export("pdf", path, None, None, False, str(exc))
            return self._failure("pdf", str(exc), path)

        size = out_path.stat().st_size if out_path.exists() else 0
        db.log_export("pdf", path, size, len(rows), True, None)
        self._set_last_export(path)
        result = {
            "kind": "pdf", "path": path, "size": size,
            "record_count": len(rows), "success": True, "error": None,
        }
        bus.publish("export.completed", result)
        _log.info("PDF exported: %s (%d rows, %d bytes)",
                  path, len(rows), size)
        return result

    def _render_pdf(
        self,
        out_path: Path,
        date_from: str,
        date_to: str,
        rows: List[Dict[str, Any]],
        lang: str,
        include_top: bool,
    ) -> None:
        """Render the PDF document at `out_path`."""
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "RaskTitle", parent=styles["Title"],
            textColor=_hex_to_reportlab_color(config.GOLD),
            fontSize=24, spaceAfter=12, alignment=0,
        )
        heading_style = ParagraphStyle(
            "RaskHeading", parent=styles["Heading2"],
            textColor=_hex_to_reportlab_color(config.GOLD),
            fontSize=14, spaceAfter=8, spaceBefore=16,
        )
        body_style = ParagraphStyle(
            "RaskBody", parent=styles["BodyText"],
            fontSize=10, textColor=colors.HexColor("#222222"),
            spaceAfter=4,
        )
        small_style = ParagraphStyle(
            "RaskSmall", parent=styles["BodyText"],
            fontSize=9, textColor=colors.HexColor("#666666"),
            spaceAfter=2,
        )

        doc = SimpleDocTemplate(
            str(out_path), pagesize=A4,
            leftMargin=config.EXPORT_PDF_MARGIN,
            rightMargin=config.EXPORT_PDF_MARGIN,
            topMargin=config.EXPORT_PDF_MARGIN,
            bottomMargin=config.EXPORT_PDF_MARGIN,
            title="Rask Time Report",
            author=config.APP_AUTHOR,
        )
        story: List[Any] = []

        # --- Header ---
        story.append(Paragraph("Rask — Time Report", title_style))
        story.append(Paragraph(
            f"Period: {date_from} → {date_to}", small_style))
        story.append(Spacer(1, 12))

        total_min = sum(int(r.get("duration_min", 0) or 0) for r in rows)
        hours = total_min // 60
        mins = total_min % 60
        story.append(Paragraph(
            f"<b>Total time:</b> {hours}h {mins}m "
            f"({len(rows)} activities)", body_style))
        story.append(Spacer(1, 16))

        # --- Per-category breakdown ---
        story.append(Paragraph("By Category", heading_style))
        cats = _categories_map()
        cat_totals: Dict[int, int] = {}
        cat_counts: Dict[int, int] = {}
        for r in rows:
            cid = r.get("category_id")
            if cid is None:
                cid = 0
            cat_totals[cid] = cat_totals.get(cid, 0) + int(
                r.get("duration_min", 0) or 0)
            cat_counts[cid] = cat_counts.get(cid, 0) + 1

        cat_data = [["Category", "Activities", "Total (min)", "Total (h:m)"]]
        for cid in sorted(cat_totals.keys(), key=lambda c: -cat_totals[c]):
            name = "—"
            if cid and cid in cats:
                c = cats[cid]
                name = c.get("name_en", "") or c.get("name_fa", "")
            tot = cat_totals[cid]
            cnt = cat_counts[cid]
            cat_data.append([
                name, str(cnt), str(tot),
                f"{tot // 60}h {tot % 60}m",
            ])
        cat_table = Table(cat_data, colWidths=[
            70 * mm, 30 * mm, 35 * mm, 35 * mm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             _hex_to_reportlab_color(config.CHARCOAL)),
            ("TEXTCOLOR", (0, 0), (-1, 0),
             _hex_to_reportlab_color(config.GOLD)),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F8F6F0")]),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 20))

        # --- Per-day totals ---
        story.append(Paragraph("By Day", heading_style))
        day_totals: Dict[str, int] = {}
        day_counts: Dict[str, int] = {}
        for r in rows:
            d = r.get("date_iso", "")
            if not d:
                continue
            day_totals[d] = day_totals.get(d, 0) + int(
                r.get("duration_min", 0) or 0)
            day_counts[d] = day_counts.get(d, 0) + 1

        day_data = [["Date", "Activities", "Total (min)"]]
        for d in sorted(day_totals.keys()):
            day_data.append([
                d, str(day_counts[d]), str(day_totals[d]),
            ])
        # Cap to first 50 days to avoid runaway tables.
        if len(day_data) > 51:
            day_data = day_data[:51]
            day_data.append(["…", "…", "…"])
        day_table = Table(day_data, colWidths=[55 * mm, 40 * mm, 40 * mm])
        day_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             _hex_to_reportlab_color(config.CHARCOAL)),
            ("TEXTCOLOR", (0, 0), (-1, 0),
             _hex_to_reportlab_color(config.GOLD)),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F8F6F0")]),
        ]))
        story.append(day_table)
        story.append(Spacer(1, 20))

        # --- Top activities ---
        if include_top and rows:
            story.append(PageBreak())
            story.append(Paragraph("Top Activities", heading_style))
            top = sorted(rows, key=lambda r: -int(
                r.get("duration_min", 0) or 0))[:20]
            top_data = [["#", "Title", "Category", "Date", "Min"]]
            for i, r in enumerate(top, 1):
                cat_id = r.get("category_id")
                cat_name = "—"
                if cat_id and cat_id in cats:
                    c = cats[cat_id]
                    cat_name = c.get("name_en", "") or c.get("name_fa", "")
                title = (r.get("title", "") or "")[:40]
                top_data.append([
                    str(i), title, cat_name[:15],
                    r.get("date_iso", ""),
                    str(int(r.get("duration_min", 0) or 0)),
                ])
            top_table = Table(top_data, colWidths=[
                10 * mm, 60 * mm, 35 * mm, 30 * mm, 20 * mm])
            top_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0),
                 _hex_to_reportlab_color(config.CHARCOAL)),
                ("TEXTCOLOR", (0, 0), (-1, 0),
                 _hex_to_reportlab_color(config.GOLD)),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F8F6F0")]),
            ]))
            story.append(top_table)

        # --- Footer ---
        story.append(Spacer(1, 30))
        story.append(Paragraph(
            f"Generated by {config.APP_NAME} v{config.APP_VERSION} "
            f"on {now_iso_utc()}", small_style))

        doc.build(story)

    # ------------------------------------------------------------------
    # PNG (widget screenshot)
    # ------------------------------------------------------------------

    def export_png(
        self,
        chart_widget: Any,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save a screenshot of a Tk widget as a PNG file.

        `chart_widget` must be a Tk widget with a ``winfo_id()`` method.
        Uses Pillow's ``ImageGrab`` (platform-specific).
        """
        if not _PIL_AVAILABLE:
            msg = "Pillow not installed (pip install Pillow)"
            _log.error(msg)
            db.log_export("png", path, None, None, False, msg)
            return self._failure("png", msg, path)

        if chart_widget is None:
            return self._failure("png", "no widget provided")

        if path is None:
            path = str(config.EXPORT_DIR / f"rask_chart_{now_iso_utc().replace(':', '-')}.png")

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Get widget geometry on screen.
            chart_widget.update_idletasks()
            x = chart_widget.winfo_rootx()
            y = chart_widget.winfo_rooty()
            w = chart_widget.winfo_width()
            h = chart_widget.winfo_height()
            bbox = (x, y, x + w, y + h)
            img = ImageGrab.grab(bbox=bbox)
            img.save(str(out_path), "PNG")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_export("png", path, None, None, False, str(exc))
            return self._failure("png", str(exc), path)

        size = out_path.stat().st_size if out_path.exists() else 0
        db.log_export("png", path, size, 1, True, None)
        self._set_last_export(path)
        result = {
            "kind": "png", "path": path, "size": size,
            "record_count": 1, "success": True, "error": None,
        }
        bus.publish("export.completed", result)
        _log.info("PNG exported: %s (%d bytes)", path, size)
        return result

    # ------------------------------------------------------------------
    # Share / open
    # ------------------------------------------------------------------

    def share(self, path: str) -> bool:
        """Open the OS share dialog for `path`.

        On macOS uses ``open -R`` (reveal in Finder).  On Windows
        invokes the shell "To:" share verb.  On Linux falls back to
        ``xdg-open`` of the containing folder.

        Returns True if a command was launched (does not guarantee
        success — the user might cancel the dialog).
        """
        p = Path(path)
        if not p.is_file():
            _log.warning("share: file not found: %s", path)
            return False
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(p)])
            elif sys.platform == "win32":
                # Use explorer to reveal the file.
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                # Linux: open the parent folder.
                subprocess.Popen(["xdg-open", str(p.parent)])
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            return False
        _log.info("Share launched for: %s", path)
        return True

    def open_in_file_manager(self, path: str) -> bool:
        """Reveal `path` in the OS file manager."""
        return self.share(path)

    # ------------------------------------------------------------------
    # Last export
    # ------------------------------------------------------------------

    def last_export(self) -> Optional[Dict[str, Any]]:
        """Return metadata about the most recent export, or ``None``."""
        try:
            from .settings_service import settings_service
            iso = settings_service.last_export_iso()
            if not iso:
                return None
            return {"timestamp": iso}
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _failure(self, kind: str, error: str,
                  path: Optional[str] = None) -> Dict[str, Any]:
        return {
            "kind": kind, "path": path, "size": 0,
            "record_count": 0, "success": False, "error": error,
        }

    def _set_last_export(self, path: str) -> None:
        try:
            from .settings_service import settings_service
            settings_service.set_last_export_iso(now_iso_utc())
        except Exception:  # noqa: BLE001
            pass


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

export_service: ExportService = ExportService()
