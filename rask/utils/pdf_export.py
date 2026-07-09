"""
pdf_export.py — Generate a PDF report of activities.

Uses reportlab if available on the host (desktop testing) — but on Android
we can't easily ship reportlab. The Android implementation falls back to
drawing the PDF via Kivy's graphics + pyjnius's Android PdfDocument.

For broad compatibility, this module exposes one function: `export_pdf()`.
On Android it uses pyjnius; on desktop it uses reportlab if installed.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from rask.data import repositories as repos
from rask.data.models import fmt_minutes_human
from rask.utils import date_utils


def export_pdf(path: Path, start_iso: str, end_iso: str, lang: str = "en") -> None:
    """Export a PDF weekly/monthly report to `path`."""
    try:
        from jnius import autoclass  # type: ignore  # Android
        _export_android(path, start_iso, end_iso, lang)
    except ImportError:
        _export_desktop(path, start_iso, end_iso, lang)


# === Desktop path (reportlab) ===

def _export_desktop(path: Path, start_iso: str, end_iso: str, lang: str) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import simpleSplit
    except ImportError:
        # No reportlab — write a plain-text .pdf-like marker
        path.write_text("PDF export requires reportlab on desktop.\n", encoding="utf-8")
        return

    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFillColorRGB(0.83, 0.69, 0.22)  # gold
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, y, "Rask — Time Report")
    y -= 30
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Period: {start_iso} → {end_iso}")
    y -= 30

    acts = repos.ActivityRepository.by_date_range(start_iso, end_iso)
    total = sum(a.duration_sec for a in acts)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Total: {fmt_minutes_human(total, lang=lang)}")
    y -= 25

    c.setFont("Helvetica", 11)
    for a in acts:
        if y < 60:
            c.showPage()
            y = h - 60
        line = f"{a.date_iso}  {a.title or '(no title)':30.30s}  {fmt_minutes_human(a.duration_sec, lang=lang)}"
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(40, y, line)
        y -= 18
    c.save()


# === Android path (PdfDocument via pyjnius) ===

def _export_android(path: Path, start_iso: str, end_iso: str, lang: str) -> None:
    from jnius import autoclass  # type: ignore
    PdfDocument = autoclass("android.graphics.pdf.PdfDocument")
    Paint = autoclass("android.graphics.Paint")
    Color = autoclass("android.graphics.Color")
    Rect = autoclass("android.graphics.Rect")

    doc = PdfDocument()
    page_info = PdfDocument.PageInfo.Builder(595, 842, 1).create()
    page = doc.startPage(page_info)
    canvas = page.getCanvas()

    paint = Paint()
    paint.setAntiAlias(True)

    # Title (gold)
    paint.setColor(Color.parseColor("#D4AF37"))
    paint.setTextSize(28)
    canvas.drawText("Rask — Time Report", 40, 60, paint)

    # Subtitle
    paint.setColor(Color.parseColor("#888888"))
    paint.setTextSize(12)
    canvas.drawText(f"Period: {start_iso} -> {end_iso}", 40, 85, paint)

    acts = repos.ActivityRepository.by_date_range(start_iso, end_iso)
    total = sum(a.duration_sec for a in acts)

    paint.setColor(Color.parseColor("#222222"))
    paint.setTextSize(14)
    canvas.drawText(f"Total: {fmt_minutes_human(total, lang=lang)}", 40, 120, paint)

    paint.setTextSize(11)
    y = 150
    for a in acts:
        if y > 820:
            doc.finishPage(page)
            page_info = PdfDocument.PageInfo.Builder(595, 842, 2).create()
            page = doc.startPage(page_info)
            canvas = page.getCanvas()
            y = 60
        line = f"{a.date_iso}  {a.title or '(no title)':30.30s}  {fmt_minutes_human(a.duration_sec, lang=lang)}"
        canvas.drawText(line, 40, y, paint)
        y += 18

    doc.finishPage(page)

    # Write to file
    fos = autoclass("java.io.FileOutputStream")(str(path))
    doc.writeTo(fos)
    fos.close()
    doc.close()
