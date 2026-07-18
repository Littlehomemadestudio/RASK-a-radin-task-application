"""exporters.py — PDF + CSV exports (mirror of web/js/export-pdf.js + export-csv.js)."""
from __future__ import annotations
import csv
import io
import os
import datetime as _dt
from typing import List, Tuple
from . import database
from .date_utils import fmt_human, fmt_short_date
from .i18n import t


def _safe(s) -> str:
    if s is None:
        return ""
    return str(s)


def export_csv(start_iso: str, end_iso: str, path: str) -> int:
    """Export activities in [start_iso, end_iso] to CSV at path. Returns row count."""
    if start_iso and end_iso:
        acts = database.activities_by_date_range(start_iso, end_iso)
    else:
        acts = database.all_activities()
    out = io.StringIO()
    out.write("\uFEFF")
    w = csv.writer(out)
    w.writerow([
        "id", "title", "category_id", "kind", "date", "start", "end",
        "duration_sec", "duration_hhmm", "note", "voice_input", "created_at",
    ])
    for a in acts:
        d = int(a.get("duration_sec", 0) or 0)
        hh = f"{d // 3600:02d}:{(d % 3600) // 60:02d}"
        w.writerow([
            a.get("id"), _safe(a.get("title")), a.get("category_id") or "",
            _safe(a.get("kind")), _safe(a.get("date_iso")),
            _safe(a.get("start_iso")), _safe(a.get("end_iso")),
            d, hh, _safe(a.get("note")), 1 if a.get("voice_input") else 0,
            _safe(a.get("created_at")),
        ])
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out.getvalue())
    return len(acts)


def export_pdf(start_iso: str, end_iso: str, lang: str, path: str) -> None:
    """Generate a PDF report (mirror of export-pdf.js exportReport)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib.colors import HexColor

    c = _canvas.Canvas(path, pagesize=A4)
    W, H = A4
    M = 40
    y = H - M

    # Title
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(HexColor("#D4AF37"))
    c.drawString(M, y, "Rask — Time Report")
    y -= 30
    c.setFont("Helvetica", 11)
    c.setFillColor(HexColor("#505050"))
    c.drawString(M, y, f"Period: {start_iso} -> {end_iso}")
    y -= 24

    acts = database.activities_by_date_range(start_iso, end_iso)
    total = sum(int(a.get("duration_sec", 0) or 0) for a in acts)

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(HexColor("#141414"))
    c.drawString(M, y, f"Total: {fmt_human(total, lang)}")
    y -= 26

    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#282828"))

    cats = database.all_categories()
    cat_map = {cat["id"]: cat for cat in cats}

    for a in acts:
        if y < M + 20:
            c.showPage()
            y = H - M
            c.setFont("Helvetica", 10)
            c.setFillColor(HexColor("#282828"))
        cat = cat_map.get(a.get("category_id")) if a.get("category_id") else None
        cat_name = cat["name_fa"] if lang == "fa" and cat else (cat["name_en"] if cat else "—")
        title = (a.get("title") or "(no title)")[:40].ljust(40)
        line = f"{a.get('date_iso', '')}  {title}  {cat_name[:12].ljust(12)}  {fmt_human(int(a.get('duration_sec', 0) or 0), lang)}"
        c.drawString(M, y, line)
        y -= 14

    # Summary page
    c.showPage()
    y = H - M
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(HexColor("#D4AF37"))
    c.drawString(M, y, "Summary")
    y -= 24
    c.setFont("Helvetica", 11)
    c.setFillColor(HexColor("#282828"))
    c.drawString(M, y, f"Activities: {len(acts)}")
    y -= 16
    c.drawString(M, y, f"Total time: {fmt_human(total, lang)}")
    y -= 16
    # Per-category breakdown
    per_cat: dict = {}
    for a in acts:
        cid = a.get("category_id") or 0
        per_cat[cid] = per_cat.get(cid, 0) + int(a.get("duration_sec", 0) or 0)
    c.drawString(M, y, "By category:")
    y -= 16
    for cid, sec in sorted(per_cat.items(), key=lambda x: -x[1]):
        cat = cat_map.get(cid)
        name = cat["name_fa"] if lang == "fa" and cat else (cat["name_en"] if cat else "—")
        c.drawString(M, y, f"  {name}: {fmt_human(sec, lang)}")
        y -= 14

    c.save()
