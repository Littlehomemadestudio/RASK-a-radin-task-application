"""exporters.py — PDF, CSV, and JSON exports (1:1 mirror of web/js/export-*.js).

Provides:
  - export_csv(path, activities, lang) — write CSV report
  - export_json(path, payload) — write JSON dump
  - export_pdf(path, summary, activities, lang) — write PDF report (requires reportlab)
  - export_text(path, summary, lang) — write plain-text report (fallback for PDF)

Mirrors the web edition's PDF (jsPDF) and CSV outputs column-for-column,
with additional desktop-only features (statistics summary on the PDF cover).
"""
from __future__ import annotations
import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Optional

from . import config
from . import database
from . import date_utils
from .i18n import t, to_fa_digits


# =====================================================================
# === CSV EXPORT (mirror web/js/export-csv.js) ===
# =====================================================================
def export_csv(path, activities: list[dict], lang: str = "fa",
               categories: Optional[list[dict]] = None) -> int:
    """Write activities to a CSV file. Returns the number of rows written."""
    if categories is None:
        categories = database.all_categories()
    cat_map = {c["id"]: c for c in categories}
    # Build header
    header = [
        t("exportColumnTitle", lang),
        t("exportColumnCategory", lang),
        t("exportColumnDate", lang),
        t("exportColumnStart", lang),
        t("exportColumnEnd", lang),
        t("exportColumnDuration", lang),
        t("exportColumnNote", lang),
        t("exportColumnKind", lang),
    ]
    rows = 0
    # Open with utf-8-sig so Excel detects UTF-8 (handles Persian)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for a in activities:
            cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
            cat_name = (cat["name_fa"] if lang == "fa" else cat["name_en"]) if cat else ""
            duration_min = (int(a.get("duration_sec", 0) or 0)) / 60.0
            writer.writerow([
                a.get("title", ""),
                cat_name,
                a.get("date_iso", ""),
                a.get("start_iso", "") or "",
                a.get("end_iso", "") or "",
                f"{duration_min:.2f}",
                a.get("note", ""),
                a.get("kind", "manual"),
            ])
            rows += 1
    return rows


# =====================================================================
# === JSON EXPORT (raw data dump) ===
# =====================================================================
def export_json(path, payload: dict) -> int:
    """Write a JSON payload to a file. Returns the number of bytes written."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return len(text)


# =====================================================================
# === TEXT EXPORT (fallback for PDF) ===
# =====================================================================
def export_text(path, summary: dict, activities: list[dict], lang: str = "fa") -> int:
    """Write a plain-text activity report. Returns bytes written."""
    lines = []
    lines.append("=" * 60)
    lines.append(t("exportTitle", lang))
    lines.append("=" * 60)
    lines.append(f"{t('exportDateRange', lang)}: {summary.get('start_iso', '')} - {summary.get('end_iso', '')}")
    lines.append(f"{t('exportGeneratedAt', lang)}: {date_utils.now_iso()}")
    lines.append(f"{t('exportActivityCount', lang)}: {summary.get('count', 0)}")
    lines.append(f"{t('exportTotalDuration', lang)}: {date_utils.fmt_human(int(summary.get('total_sec', 0)), lang)}")
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"{'#':>3}  {t('exportColumnDate', lang):<12}  {t('exportColumnTitle', lang):<30}  {t('exportColumnDuration', lang):<10}")
    lines.append("-" * 60)
    for i, a in enumerate(activities, 1):
        title = (a.get("title") or t("untitled", lang))[:30]
        date = a.get("date_iso", "")
        dur = date_utils.fmt_human(int(a.get("duration_sec", 0) or 0), lang)
        n = to_fa_digits(i) if lang == "fa" else str(i)
        lines.append(f"{n:>3}  {date:<12}  {title:<30}  {dur:<10}")
    lines.append("=" * 60)
    text = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return len(text)


# =====================================================================
# === PDF EXPORT (mirror web/js/export-pdf.js) ===
# =====================================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False


def pdf_available() -> bool:
    """Return True if the reportlab library is available."""
    return _REPORTLAB_AVAILABLE


def _register_persian_font():
    """Try to register a Persian-capable font for PDF rendering.
    
    Looks for Vazirmatn, Noto Sans Arabic, or DejaVu Sans in that order.
    Returns the font name to use, or None if no Persian font is available
    (in which case Persian text will render as squares — caller may want
    to fall back to Latin text only).
    """
    if not _REPORTLAB_AVAILABLE:
        return None
    import os
    candidates = []
    # Linux/Mac paths
    for root in ["/usr/share/fonts/truetype",
                 "/usr/share/fonts",
                 "/Library/Fonts",
                 os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/Library/Fonts")]:
        if os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if fn.lower().endswith(".ttf"):
                        candidates.append(os.path.join(dirpath, fn))
    # Look for Persian-capable fonts in priority order
    priority = [
        "Vazirmatn", "Vazir",
        "NotoSansArabic", "NotoNaskhArabic", "NotoSansPersian",
        "Amiri", "Sahel",
        "DejaVuSans",
    ]
    for prio in priority:
        for c in candidates:
            base = os.path.splitext(os.path.basename(c))[0]
            if base.lower() == prio.lower():
                try:
                    pdfmetrics.registerFont(TTFont(prio, c))
                    return prio
                except Exception:
                    continue
            # Also try bold variants
            if base.lower() == f"{prio.lower()}-bold":
                try:
                    pdfmetrics.registerFont(TTFont(f"{prio}-Bold", c))
                except Exception:
                    pass
    return None


def export_pdf(path, summary: dict, activities: list[dict],
               lang: str = "fa", categories: Optional[list[dict]] = None) -> int:
    """Write a PDF report. Returns the number of bytes written.
    
    Falls back to plain-text export if reportlab is not installed.
    """
    if not _REPORTLAB_AVAILABLE:
        # Fallback to text export
        text_path = str(path).rsplit(".", 1)[0] + ".txt"
        return export_text(text_path, summary, activities, lang)
    if categories is None:
        categories = database.all_categories()
    cat_map = {c["id"]: c for c in categories}
    # Try to register Persian font
    font_name = _register_persian_font() or "Helvetica"
    bold_font = f"{font_name}-Bold" if font_name != "Helvetica" else "Helvetica-Bold"
    # Set up PDF document
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title=t("exportTitle", lang),
        author=config.APP_NAME,
    )
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RaskTitle", parent=styles["Title"],
        fontName=bold_font, fontSize=24, leading=28,
        textColor=HexColor(config.GOLD), alignment=TA_CENTER,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "RaskSubtitle", parent=styles["Normal"],
        fontName=font_name, fontSize=11, leading=14,
        textColor=HexColor(config.TEXT_DIM), alignment=TA_CENTER,
        spaceAfter=24,
    )
    h2_style = ParagraphStyle(
        "RaskH2", parent=styles["Heading2"],
        fontName=bold_font, fontSize=14, leading=18,
        textColor=HexColor(config.GOLD), spaceBefore=16, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "RaskBody", parent=styles["Normal"],
        fontName=font_name, fontSize=10, leading=14,
        textColor=HexColor(config.TEXT), spaceAfter=4,
    )
    metric_style = ParagraphStyle(
        "RaskMetric", parent=styles["Normal"],
        fontName=bold_font, fontSize=11, leading=14,
        textColor=HexColor(config.TEXT), spaceAfter=2,
    )
    metric_value_style = ParagraphStyle(
        "RaskMetricValue", parent=styles["Normal"],
        fontName=bold_font, fontSize=16, leading=20,
        textColor=HexColor(config.GOLD), spaceAfter=8,
    )
    cell_style = ParagraphStyle(
        "RaskCell", parent=styles["Normal"],
        fontName=font_name, fontSize=9, leading=12,
        textColor=HexColor(config.TEXT),
    )
    # Build story
    story = []
    # Title block
    story.append(Paragraph(t("exportTitle", lang), title_style))
    story.append(Paragraph(t("tagline", lang), subtitle_style))
    # Meta block
    story.append(Paragraph(f"{t('exportDateRange', lang)}: "
                           f"{summary.get('start_iso', '')} — {summary.get('end_iso', '')}", body_style))
    story.append(Paragraph(f"{t('exportGeneratedAt', lang)}: {date_utils.now_iso()}", body_style))
    story.append(Spacer(1, 16))
    # Summary metrics
    story.append(Paragraph(t("statistics", lang), h2_style))
    metrics_data = [
        [Paragraph(t("exportActivityCount", lang), cell_style),
         Paragraph(str(summary.get("count", 0)), cell_style)],
        [Paragraph(t("exportTotalDuration", lang), cell_style),
         Paragraph(date_utils.fmt_human(int(summary.get("total_sec", 0)), lang), cell_style)],
        [Paragraph(t("dailyAvg", lang), cell_style),
         Paragraph(date_utils.fmt_human(int(summary.get("daily_avg_sec", 0)), lang), cell_style)],
        [Paragraph(t("activeDays", lang), cell_style),
         Paragraph(str(summary.get("active_days", 0)), cell_style)],
        [Paragraph(t("bestDay", lang), cell_style),
         Paragraph(summary.get("best_day", "—") or "—", cell_style)],
        [Paragraph(t("peakHour", lang), cell_style),
         Paragraph(str(summary.get("peak_hour", "—")), cell_style)],
    ]
    metrics_table = Table(metrics_data, colWidths=[80 * mm, 90 * mm])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor(config.CHARCOAL)),
        ("TEXTCOLOR", (0, 0), (-1, -1), HexColor(config.TEXT)),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, HexColor(config.DIVIDER)),
        ("BOX", (0, 0), (-1, -1), 0.5, HexColor(config.DIVIDER)),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 16))
    # Category breakdown
    cat_breakdown = summary.get("category_breakdown", [])
    if cat_breakdown:
        story.append(Paragraph(t("categoryShare", lang), h2_style))
        cat_data = [[
            Paragraph(t("exportColumnCategory", lang), cell_style),
            Paragraph(t("exportTotalDuration", lang), cell_style),
            Paragraph("%", cell_style),
        ]]
        total_sec = sum(c[1] for c in cat_breakdown) or 1
        for cid, sec in cat_breakdown[:10]:
            cat = cat_map.get(cid)
            name = (cat["name_fa"] if lang == "fa" and cat else
                    cat["name_en"] if cat else "—")
            pct = (sec / total_sec * 100) if total_sec else 0
            cat_data.append([
                Paragraph(name, cell_style),
                Paragraph(date_utils.fmt_human(int(sec), lang), cell_style),
                Paragraph(f"{pct:.1f}%", cell_style),
            ])
        cat_table = Table(cat_data, colWidths=[60 * mm, 70 * mm, 40 * mm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor(config.SURFACE)),
            ("TEXTCOLOR", (0, 0), (-1, -1), HexColor(config.TEXT)),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, HexColor(config.DIVIDER)),
            ("BOX", (0, 0), (-1, -1), 0.5, HexColor(config.DIVIDER)),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 16))
    # Activities table
    story.append(Paragraph(t("recentActivities", lang), h2_style))
    act_data = [[
        Paragraph("#", cell_style),
        Paragraph(t("exportColumnDate", lang), cell_style),
        Paragraph(t("exportColumnTitle", lang), cell_style),
        Paragraph(t("exportColumnCategory", lang), cell_style),
        Paragraph(t("exportColumnDuration", lang), cell_style),
    ]]
    for i, a in enumerate(activities[:200], 1):
        cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
        cat_name = (cat["name_en"] if cat else "—")
        title = (a.get("title") or t("untitled", lang))[:40]
        dur = date_utils.fmt_human(int(a.get("duration_sec", 0) or 0), lang)
        act_data.append([
            Paragraph(str(i), cell_style),
            Paragraph(a.get("date_iso", ""), cell_style),
            Paragraph(title, cell_style),
            Paragraph(cat_name, cell_style),
            Paragraph(dur, cell_style),
        ])
    act_table = Table(act_data, colWidths=[10 * mm, 25 * mm, 70 * mm, 35 * mm, 30 * mm])
    act_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(config.SURFACE)),
        ("TEXTCOLOR", (0, 0), (-1, -1), HexColor(config.TEXT)),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, HexColor(config.DIVIDER)),
        ("BOX", (0, 0), (-1, -1), 0.5, HexColor(config.DIVIDER)),
    ]))
    story.append(act_table)
    # Footer note
    story.append(Spacer(1, 16))
    story.append(Paragraph(f"{config.APP_NAME} v{config.APP_VERSION} — {config.APP_COPYRIGHT}", subtitle_style))
    # Build PDF
    doc.build(story)
    return Path(path).stat().st_size if Path(path).exists() else 0


# =====================================================================
# === BUILD SUMMARY (helper used by all exporters) ===
# =====================================================================
def build_summary(start_iso: str, end_iso: str, lang: str = "fa") -> dict:
    """Build a summary dict for the given date range."""
    activities = database.activities_by_date_range(start_iso, end_iso)
    total_sec = sum(int(a.get("duration_sec", 0) or 0) for a in activities)
    active_days = len(set(a["date_iso"] for a in activities if a.get("date_iso")))
    # Daily average
    from .date_utils import diff_days, parse_date
    d1 = parse_date(start_iso)
    d2 = parse_date(end_iso)
    days = diff_days(d2, d1) + 1 if start_iso != end_iso else 1
    daily_avg = total_sec / days if days > 0 else 0
    # Best day
    per_day: dict[str, int] = {}
    for a in activities:
        d = a.get("date_iso")
        if d:
            per_day[d] = per_day.get(d, 0) + int(a.get("duration_sec", 0) or 0)
    best_day_iso = max(per_day.items(), key=lambda kv: kv[1])[0] if per_day else None
    # Peak hour
    peak_hour = None
    if activities:
        hour_counts: dict[int, int] = {}
        for a in activities:
            ts = a.get("start_iso") or a.get("created_at")
            if ts and len(ts) >= 13:
                try:
                    h = int(ts[11:13])
                    hour_counts[h] = hour_counts.get(h, 0) + int(a.get("duration_sec", 0) or 0)
                except ValueError:
                    continue
        if hour_counts:
            peak_hour = max(hour_counts.items(), key=lambda kv: kv[1])[0]
    # Category breakdown
    cat_breakdown = database.seconds_per_category(start_iso, end_iso)
    return {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "count": len(activities),
        "total_sec": total_sec,
        "daily_avg_sec": daily_avg,
        "active_days": active_days,
        "best_day": best_day_iso,
        "peak_hour": peak_hour,
        "category_breakdown": cat_breakdown,
        "activities": activities,
    }
