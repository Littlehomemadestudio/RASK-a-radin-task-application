"""
rask.export.pdf_export
======================

Low-level PDF report generator for Rask.

Built on top of ReportLab's Platypus framework (SimpleDocTemplate +
flowables) so we get automatic pagination, table layout, and style
inheritance for free.  The visual style mirrors the in-app
gold-on-dark theme:

    * Page background  — matte black (#0E0E10)
    * Body text        — soft white (#E8E8E8)
    * Headings         — gold (#D4AF37)
    * Tables           — charcoal surface (#1A1A1D) with gold header row
    * Charts           — gold + accent palette (yellow, green, blue)

Persian font handling
---------------------
We probe the system for ``Vazirmatn`` (the same font the web PWA uses),
falling back to ``Tahoma`` → ``Segoe UI`` → ``Arial`` → the reportlab
default.  When the chosen family is registered with reportlab via
``pdfmetrics.registerFont``, Persian glyphs render correctly.  Arabic
shaping is handled by reportlab's built-in bidi support (limited —
the web PWA uses a full-fledged shaper, so for desktop we recommend
installing Vazirmatn for best results).

Persian digits
--------------
All numeric values passed through :meth:`add_summary_table` and
:meth:`add_activities_table` are converted to Persian digits when
``lang="fa"`` to match the in-app display.

Page footer
-----------
Every page carries a footer ``"Rask v{version} • {date} • {page}/{n}"``
so printed copies are traceable.

Mirrors ``web/js/export-pdf.js`` 1:1 (the web PWA's "Export PDF"
button calls a near-identical layout pipeline).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .. import config
from .. import i18n
from ..core.logging_utils import get_logger

__all__ = ["PdfExporter"]

_log = get_logger("export.pdf")


# =============================================================================
# === Optional dependencies                                                  ===
# =============================================================================
# We attempt to import reportlab up-front but tolerate its absence —
# callers that don't need PDF shouldn't have to install it.  When
# reportlab is missing, every PdfExporter method raises a clear
# ``RuntimeError`` at the point of use.

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
        Table, TableStyle, PageBreak, Image as RLImage, KeepTogether,
    )
    from reportlab.platypus.flowables import HRFlowable
    _REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover — optional dep
    _REPORTLAB_AVAILABLE = False


# =============================================================================
# === Colour + font helpers                                                   ===
# =============================================================================

def _hex_to_rl_color(hex_str: str):
    """Convert a ``"#RRGGBB"`` string to a reportlab :class:`Color`."""
    if not _REPORTLAB_AVAILABLE:
        return None
    h = (hex_str or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return colors.black
    try:
        return colors.Color(
            int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0,
        )
    except ValueError:
        return colors.black


# Pre-computed colours (only used when reportlab is present).
if _REPORTLAB_AVAILABLE:
    _C_MATTE = _hex_to_rl_color(config.MATTE_BLACK)
    _C_CHARCOAL = _hex_to_rl_color(config.CHARCOAL)
    _C_SURFACE = _hex_to_rl_color(config.SURFACE)
    _C_GOLD = _hex_to_rl_color(config.GOLD)
    _C_GOLD_DIM = _hex_to_rl_color(config.GOLD_DIM)
    _C_TEXT = _hex_to_rl_color(config.TEXT)
    _C_TEXT_DIM = _hex_to_rl_color(config.TEXT_DIM)
    _C_DIVIDER = _hex_to_rl_color(config.DIVIDER)
    _C_DANGER = _hex_to_rl_color(config.DANGER)
    _C_SUCCESS = _hex_to_rl_color(config.SUCCESS)
    _C_INFO = _hex_to_rl_color(config.INFO)
    _C_WARNING = _hex_to_rl_color(config.WARNING)
else:
    _C_MATTE = _C_CHARCOAL = _C_SURFACE = _C_GOLD = _C_GOLD_DIM = None
    _C_TEXT = _C_TEXT_DIM = _C_DIVIDER = None
    _C_DANGER = _C_SUCCESS = _C_INFO = _C_WARNING = None


_FONT_CANDIDATES: Tuple[str, ...] = (
    "Vazirmatn", "Tahoma", "Segoe UI", "Noto Sans", "DejaVu Sans", "Arial",
)
_FONT_REGISTERED: Dict[str, str] = {}


def _find_persian_font() -> Tuple[Optional[str], Optional[str]]:
    """Locate a TrueType Persian font file on the system.

    Returns ``(family_name, file_path)`` or ``(None, None)`` if no
    suitable font was found.  Search order:

      1. ``rask/assets/fonts/Vazirmatn*.ttf`` (bundled with the app)
      2. Platform font directories (best-effort glob)
    """
    # 1. Bundled font
    try:
        bundled = Path(__file__).resolve().parents[1] / "assets" / "fonts"
        if bundled.is_dir():
            for ttf in sorted(bundled.glob("*.ttf")):
                name = ttf.stem
                if name.lower().startswith("vazir"):
                    return name, str(ttf)
                # Accept any TTF as a fallback.
                return name, str(ttf)
    except Exception:  # noqa: BLE001 — best-effort
        pass
    # 2. Platform fonts
    candidates = [
        Path.home() / ".local" / "share" / "fonts",
        Path("/usr/share/fonts/truetype"),
        Path("/usr/local/share/fonts"),
        Path("C:/Windows/Fonts"),
        Path.home() / "Library" / "Fonts",
    ]
    name_map = {
        "vazirmatn": "Vazirmatn",
        "vazir": "Vazirmatn",
        "tahoma": "Tahoma",
        "tahomabd": "Tahoma-Bold",
        "arial": "Arial",
        "arialbd": "Arial-Bold",
        "dejavusans": "DejaVuSans",
        "notosans": "NotoSans",
    }
    for d in candidates:
        if not d.is_dir():
            continue
        try:
            for ttf in sorted(d.rglob("*.ttf")):
                key = ttf.stem.lower().replace("-", "").replace("_", "")
                mapped = name_map.get(key)
                if mapped:
                    return mapped, str(ttf)
        except (PermissionError, OSError):
            continue
    return None, None


def _ensure_font_registered() -> Tuple[Optional[str], Optional[str]]:
    """Register a Persian-capable font with reportlab.

    Returns ``(regular_name, bold_name)`` — either the same family
    name repeated (if no separate bold variant was found) or two
    distinct names.  ``None`` is returned if no font could be
    registered; callers should then fall back to reportlab's default
    (Helvetica).
    """
    if not _REPORTLAB_AVAILABLE:
        return None, None
    if "regular" in _FONT_REGISTERED:
        return _FONT_REGISTERED["regular"], _FONT_REGISTERED.get("bold")

    family, path = _find_persian_font()
    if not family or not path or not os.path.isfile(path):
        _log.warning("No Persian TTF font found — falling back to Helvetica. "
                     "Install Vazirmatn for proper Persian rendering.")
        _FONT_REGISTERED["regular"] = "Helvetica"
        _FONT_REGISTERED["bold"] = "Helvetica-Bold"
        return "Helvetica", "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont(family, path))
        _FONT_REGISTERED["regular"] = family
        _FONT_REGISTERED["bold"] = family  # same TTF for bold
        _log.info("Registered Persian font: %s (%s)", family, path)
        return family, family
    except Exception as exc:  # noqa: BLE001 — reportlab font errors
        _log.warning("Could not register font %s: %s — using Helvetica", family, exc)
        _FONT_REGISTERED["regular"] = "Helvetica"
        _FONT_REGISTERED["bold"] = "Helvetica-Bold"
        return "Helvetica", "Helvetica-Bold"


# =============================================================================
# === PdfExporter                                                              ===
# =============================================================================

class PdfExporter:
    """Reusable PDF report builder.

    The exporter buffers flowables into a list and only writes the
    PDF when :meth:`save` is called.  This lets callers interleave
    headings, paragraphs, tables, and charts in any order.

    Parameters
    ----------
    file_path
        Destination path.  Parent directories are created on save.
    lang
        UI language.  Default ``"fa"``.
    page_size
        ReportLab page size constant.  Default A4.
    margin
        Page margin in points (1/72 inch).  Default
        :data:`config.EXPORT_PDF_MARGIN` (36 → 0.5 in).
    title, subtitle, author, date_range
        Optional document metadata.  Can also be set via the
        corresponding ``set_*`` methods after construction.

    Examples
    --------
    >>> pdf = PdfExporter("/tmp/report.pdf", lang="fa")
    >>> pdf.set_title("گزارش روزانه")
    >>> pdf.add_heading("خلاصه", level=1)
    >>> pdf.add_paragraph("این یک گزارش آزمایشی است.")
    >>> pdf.save()
    True
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        lang: str = "fa",
        *,
        page_size: Any = None,
        margin: Optional[int] = None,
        title: str = "",
        subtitle: str = "",
        author: str = "",
        date_range: Optional[Tuple[str, str]] = None,
    ) -> None:
        if not _REPORTLAB_AVAILABLE:
            raise RuntimeError(
                "reportlab is not installed — install it with "
                "`pip install reportlab` to enable PDF export")
        self._path: Path = Path(file_path)
        self._lang: str = lang if lang in config.SUPPORTED_LANGUAGES else "fa"
        self._page_size = page_size or A4
        self._margin: int = int(
            margin if margin is not None else config.EXPORT_PDF_MARGIN)
        # Document metadata
        self._title: str = title or config.APP_NAME
        self._subtitle: str = subtitle
        self._author: str = author or config.APP_AUTHOR
        self._date_range: Optional[Tuple[str, str]] = date_range
        # Flowable buffer
        self._story: List[Any] = []
        # Styles
        self._font_regular, self._font_bold = _ensure_font_registered()
        self._styles: Dict[str, ParagraphStyle] = self._build_styles()

    # ------------------------------------------------------------------
    # Style construction
    # ------------------------------------------------------------------

    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        """Build the paragraph styles used throughout the document."""
        font_r = self._font_regular or "Helvetica"
        font_b = self._font_bold or "Helvetica-Bold"
        styles: Dict[str, ParagraphStyle] = {}
        # Body
        styles["body"] = ParagraphStyle(
            "body", fontName=font_r, fontSize=11, leading=18,
            textColor=_C_TEXT, alignment=2, spaceAfter=8,
            wordWrap="RTL" if i18n.is_rtl(self._lang) else "LTR",
        )
        # Caption (smaller, dim)
        styles["caption"] = ParagraphStyle(
            "caption", fontName=font_r, fontSize=9, leading=13,
            textColor=_C_TEXT_DIM, alignment=2, spaceAfter=4,
        )
        # Headings H1-H3
        for level, size in ((1, 22), (2, 17), (3, 14)):
            styles[f"h{level}"] = ParagraphStyle(
                f"h{level}", fontName=font_b, fontSize=size,
                leading=int(size * 1.4), textColor=_C_GOLD,
                alignment=2, spaceBefore=14, spaceAfter=8,
                wordWrap="RTL" if i18n.is_rtl(self._lang) else "LTR",
            )
        # Title (page header)
        styles["title"] = ParagraphStyle(
            "title", fontName=font_b, fontSize=26, leading=34,
            textColor=_C_GOLD, alignment=1, spaceAfter=6,
        )
        styles["subtitle"] = ParagraphStyle(
            "subtitle", fontName=font_r, fontSize=12, leading=18,
            textColor=_C_TEXT_DIM, alignment=1, spaceAfter=20,
        )
        # Bullet list item
        styles["bullet"] = ParagraphStyle(
            "bullet", parent=styles["body"], leftIndent=18,
            bulletIndent=4, spaceAfter=4,
        )
        # Insight card text
        styles["insight"] = ParagraphStyle(
            "insight", fontName=font_r, fontSize=11, leading=18,
            textColor=_C_TEXT, alignment=2, spaceAfter=6,
            leftIndent=12, rightIndent=12,
            borderColor=_C_GOLD_DIM, borderWidth=0, borderPadding=6,
            backColor=_C_CHARCOAL,
        )
        return styles

    # ------------------------------------------------------------------
    # Metadata setters
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> "PdfExporter":
        """Override the document title (shown at top of first page)."""
        self._title = title or ""
        return self

    def set_subtitle(self, subtitle: str) -> "PdfExporter":
        """Override the document subtitle."""
        self._subtitle = subtitle or ""
        return self

    def set_author(self, author: str) -> "PdfExporter":
        """Override the document author (used in PDF metadata)."""
        self._author = author or ""
        return self

    def set_date_range(self, date_from: str, date_to: str) -> "PdfExporter":
        """Set the date range covered by this report."""
        self._date_range = (date_from, date_to)
        return self

    # ------------------------------------------------------------------
    # Flowable builders
    # ------------------------------------------------------------------

    def add_heading(self, text: str, level: int = 1) -> "PdfExporter":
        """Append a heading (level 1, 2, or 3).

        Level 1 headings also get a thin gold underline rule to
        visually separate sections.
        """
        if not text:
            return self
        level = max(1, min(3, int(level)))
        style = self._styles.get(f"h{level}", self._styles["h1"])
        self._story.append(Paragraph(self._escape(text), style))
        if level == 1:
            self._story.append(HRFlowable(
                width="100%", thickness=0.8, color=_C_GOLD_DIM,
                spaceBefore=2, spaceAfter=10))
        return self

    def add_paragraph(self, text: str) -> "PdfExporter":
        """Append a body paragraph."""
        if not text:
            return self
        self._story.append(Paragraph(self._escape(text), self._styles["body"]))
        return self

    def add_bullet_list(self, items: Sequence[str]) -> "PdfExporter":
        """Append a bulleted list of strings."""
        if not items:
            return self
        style = self._styles["bullet"]
        for item in items:
            if not item:
                continue
            bullet = "•" if not i18n.is_rtl(self._lang) else "•"
            text = f"{bullet}  {self._escape(item)}"
            self._story.append(Paragraph(text, style))
        self._story.append(Spacer(1, 6))
        return self

    def add_summary_table(self, stats: Dict[str, Any]) -> "PdfExporter":
        """Append a 2-column summary table of the given stats dict.

        Renders every key/value pair where the value is a scalar.
        Nested dicts (``best_day``, ``longest_session``) are
        serialised via their ``total_min`` / ``duration_min`` field
        for readability.
        """
        if not stats:
            return self
        rows: List[List[str]] = []
        label_map: Dict[str, str] = {
            "total_min": "مجموع زمان (دقیقه)" if self._lang == "fa"
                          else "Total time (min)",
            "total_activities": "تعداد فعالیت‌ها" if self._lang == "fa"
                                  else "Activities",
            "avg_per_day": "میانگین روزانه" if self._lang == "fa"
                            else "Avg / day",
            "avg_per_activity": "میانگین هر فعالیت" if self._lang == "fa"
                                  else "Avg / activity",
            "day_count": "روزهای فعال" if self._lang == "fa"
                          else "Active days",
            "best_day": "بهترین روز" if self._lang == "fa" else "Best day",
            "worst_day": "بدترین روز" if self._lang == "fa" else "Worst day",
            "longest_session": "طولانی‌ترین نشست" if self._lang == "fa"
                                 else "Longest session",
            "date_from": "از تاریخ" if self._lang == "fa" else "From",
            "date_to": "تا تاریخ" if self._lang == "fa" else "To",
        }
        for k, v in stats.items():
            if k in ("category_ids",):
                continue
            label = label_map.get(k, k)
            display = self._format_value(v, k)
            if display is None:
                continue
            rows.append([label, display])
        if not rows:
            return self
        # Header row
        header = [
            "metric" if self._lang == "en" else "نشانگر",
            "value" if self._lang == "en" else "مقدار",
        ]
        rows.insert(0, header)
        table = Table(rows, colWidths=[200, 240])
        table.setStyle(self._summary_table_style())
        self._story.append(table)
        self._story.append(Spacer(1, 12))
        return self

    def add_activities_table(
        self,
        activities: Sequence[Dict[str, Any]],
        *,
        per_page: int = 25,
    ) -> "PdfExporter":
        """Append a paginated table of activities.

        Columns: date, title, category, duration, kind.  When the
        table exceeds ``per_page`` rows, an explicit ``PageBreak`` is
        inserted so each page stays readable.
        """
        if not activities:
            return self
        header = (["تاریخ", "عنوان", "دسته", "مدت", "نوع"]
                  if self._lang == "fa"
                  else ["Date", "Title", "Category", "Duration", "Kind"])
        # Category lookup
        try:
            from .. import database as db
            cats = {int(c["id"]): c for c in db.category_list(include_archived=True)}
        except Exception:  # noqa: BLE001 — best-effort
            cats = {}

        rows: List[List[str]] = []
        rows.append(header)
        for i, act in enumerate(activities):
            cat_id = act.get("category_id")
            cat = cats.get(int(cat_id)) if cat_id else None
            cat_name = ""
            if cat:
                cat_name = (cat.get("name_fa") if self._lang == "fa"
                             else cat.get("name_en")) or ""
            duration = int(act.get("duration_min", 0) or 0)
            rows.append([
                self._fmt_date(act.get("date_iso", "")),
                self._escape(act.get("title", "") or ""),
                self._escape(cat_name),
                self._fmt_duration(duration),
                str(act.get("kind", "manual") or "manual"),
            ])
            # Insert page breaks periodically
            if (i + 1) % per_page == 0 and (i + 1) < len(activities):
                table = Table(rows, colWidths=[70, 180, 90, 70, 60])
                table.setStyle(self._activities_table_style())
                self._story.append(table)
                self._story.append(PageBreak())
                rows = [header]
        # Final page
        if len(rows) > 1:
            table = Table(rows, colWidths=[70, 180, 90, 70, 60])
            table.setStyle(self._activities_table_style())
            self._story.append(table)
        self._story.append(Spacer(1, 12))
        return self

    def add_bar_chart(
        self,
        data: Sequence[Tuple[str, float]],
        title: str = "",
        *,
        width: int = 460,
        height: int = 200,
    ) -> "PdfExporter":
        """Append a bar chart.

        Tries to use matplotlib first (if installed) for nicer
        rendering; falls back to a native reportlab VerticalBarChart.
        """
        if not data:
            return self
        img_path = self._render_bar_chart_matplotlib(data, title, width, height)
        if img_path is not None:
            self._story.append(Paragraph(self._escape(title), self._styles["h3"]))
            self._story.append(RLImage(img_path, width=width, height=height))
            self._story.append(Spacer(1, 10))
            return self
        # Fallback: reportlab's native chart
        try:
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            from reportlab.graphics.shapes import Drawing, String
        except ImportError:
            # No chart support — append a simple table instead
            rows = [["label", "value"]] + [
                [self._escape(k), self._fmt_float(v)] for k, v in data
            ]
            t = Table(rows, colWidths=[200, 240])
            t.setStyle(self._summary_table_style())
            if title:
                self._story.append(Paragraph(self._escape(title), self._styles["h3"]))
            self._story.append(t)
            self._story.append(Spacer(1, 12))
            return self
        drawing = Drawing(width, height + 30)
        chart = VerticalBarChart()
        chart.x = 40
        chart.y = 30
        chart.width = width - 80
        chart.height = height - 30
        chart.data = [[float(v) for _, v in data]]
        chart.categoryAxis.categoryNames = [str(k) for k, _ in data]
        chart.bars[0].fillColor = _C_GOLD
        chart.bars[0].strokeColor = _C_GOLD
        chart.valueAxis.valueMin = 0
        chart.valueAxis.strokeColor = _C_DIVIDER
        chart.categoryAxis.strokeColor = _C_DIVIDER
        chart.valueAxis.labels.fillColor = _C_TEXT_DIM
        chart.categoryAxis.labels.fillColor = _C_TEXT_DIM
        drawing.add(chart)
        if title:
            title_str = String(width / 2, height + 6, title,
                                textAnchor="middle",
                                fontName=self._font_bold or "Helvetica",
                                fontSize=12, fillColor=_C_GOLD)
            drawing.add(title_str)
        if title:
            self._story.append(Paragraph(self._escape(title), self._styles["h3"]))
        self._story.append(drawing)
        self._story.append(Spacer(1, 12))
        return self

    def add_donut_chart(
        self,
        data: Sequence[Tuple[str, float]],
        title: str = "",
        *,
        size: int = 220,
    ) -> "PdfExporter":
        """Append a donut chart (category breakdown)."""
        if not data:
            return self
        try:
            from reportlab.graphics.charts.piecharts import Pie
            from reportlab.graphics.shapes import Drawing, String
        except ImportError:
            # Fallback to a simple table
            return self.add_bar_chart(data, title=title, width=size * 2,
                                        height=size)
        drawing = Drawing(size * 2, size + 40)
        pie = Pie()
        pie.x = size / 2
        pie.y = 20
        pie.width = size
        pie.height = size
        pie.data = [float(v) for _, v in data]
        pie.labels = None
        palette = [_C_GOLD, _C_INFO, _C_SUCCESS, _C_WARNING,
                    _C_DANGER, _hex_to_rl_color("#D49ABF"),
                    _hex_to_rl_color("#9A9A9F")]
        for i, slc in enumerate(pie.slices):
            try:
                color = palette[i % len(palette)]
                slc.fillColor = color
                slc.strokeColor = _C_MATTE
                slc.strokeWidth = 1.5
            except Exception:  # noqa: BLE001 — defensive
                pass
        pie.innerRadiusFraction = 0.55  # donut hole
        drawing.add(pie)
        if title:
            title_str = String(size, size + 28, title,
                                textAnchor="middle",
                                fontName=self._font_bold or "Helvetica",
                                fontSize=12, fillColor=_C_GOLD)
            drawing.add(title_str)
        if title:
            self._story.append(Paragraph(self._escape(title), self._styles["h3"]))
        self._story.append(drawing)
        self._story.append(Spacer(1, 12))
        return self

    def add_heatmap(
        self,
        data: Dict[str, int],
        title: str = "",
    ) -> "PdfExporter":
        """Append a yearly heatmap (date -> level 0..4).

        Renders as a 7-row × 53-column grid of coloured cells using a
        native reportlab :class:`Table`.  Empty days use level 0
        (matte black).
        """
        if not data:
            return self
        if title:
            self._story.append(Paragraph(self._escape(title), self._styles["h3"]))
        # Build a 7×N matrix of cells.
        from datetime import date, timedelta
        try:
            # Find the date range
            dates = sorted(data.keys())
            start = date.fromisoformat(dates[0])
            end = date.fromisoformat(dates[-1])
        except (ValueError, IndexError):
            return self
        # Snap start to the Sunday of its week
        start_sunday = start - timedelta(days=(start.weekday() + 1) % 7)
        # Build rows
        weeks: List[List[str]] = []
        cur = start_sunday
        while cur <= end:
            week: List[str] = []
            for _ in range(7):
                iso = cur.isoformat()
                week.append(iso)
                cur += timedelta(days=1)
            weeks.append(week)
        # Build a transposed grid (rows = weekdays, cols = weeks)
        if not weeks:
            return self
        n_weeks = len(weeks)
        grid: List[List[str]] = [["" for _ in range(n_weeks)] for _ in range(7)]
        for w_idx, week in enumerate(weeks):
            for d_idx, iso in enumerate(week):
                grid[d_idx][w_idx] = iso
        # Render as a table with cell background colours
        rows = [[Paragraph(self._escape(d), self._styles["caption"])
                  for d in row] for row in grid]
        table = Table(rows, colWidths=[12] * n_weeks, rowHeights=[12] * 7)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, -1), _C_MATTE),
            ("GRID", (0, 0), (-1, -1), 0.3, _C_DIVIDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TEXTCOLOR", (0, 0), (-1, -1), _C_TEXT_DIM),
            ("FONTSIZE", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
        # Apply heatmap colours per cell
        for r, row in enumerate(grid):
            for c, iso in enumerate(row):
                level = self._heatmap_level(data.get(iso, 0))
                color = _hex_to_rl_color(config.HEATMAP_LEVELS[level])
                style_cmds.append(("BACKGROUND", (c, r), (c, r), color))
        table.setStyle(TableStyle(style_cmds))
        self._story.append(table)
        self._story.append(Spacer(1, 12))
        return self

    def add_insights(self, insights: Sequence[str]) -> "PdfExporter":
        """Append a list of insight strings, each in a gold-bordered card."""
        if not insights:
            return self
        heading = "بینش‌ها" if self._lang == "fa" else "Insights"
        self._story.append(Paragraph(self._escape(heading), self._styles["h2"]))
        for text in insights:
            if not text:
                continue
            # Use a single-cell table to give the card a gold border
            inner = Paragraph(self._escape(text), self._styles["insight"])
            card = Table([[inner]], colWidths=[440])
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), _C_CHARCOAL),
                ("BOX", (0, 0), (-1, -1), 0.8, _C_GOLD_DIM),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            self._story.append(card)
            self._story.append(Spacer(1, 6))
        self._story.append(Spacer(1, 12))
        return self

    def add_page_break(self) -> "PdfExporter":
        """Insert an explicit page break."""
        self._story.append(PageBreak())
        return self

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self) -> bool:
        """Write the buffered story to disk.

        Returns True on success, False on error.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error("Cannot create parent dir for %s: %s", self._path, exc)
            return False
        # Prepend title block
        header_story: List[Any] = []
        if self._title:
            header_story.append(Paragraph(self._escape(self._title),
                                            self._styles["title"]))
        if self._subtitle:
            header_story.append(Paragraph(self._escape(self._subtitle),
                                            self._styles["subtitle"]))
        if self._date_range:
            d_from, d_to = self._date_range
            range_str = f"{self._fmt_date(d_from)} — {self._fmt_date(d_to)}"
            header_story.append(Paragraph(self._escape(range_str),
                                            self._styles["caption"]))
            header_story.append(Spacer(1, 14))
        full_story = header_story + self._story

        # Build the document with a custom page template (matte black bg +
        # footer with version + page number).
        try:
            doc = BaseDocTemplate(
                str(self._path),
                pagesize=self._page_size,
                leftMargin=self._margin,
                rightMargin=self._margin,
                topMargin=self._margin,
                bottomMargin=self._margin + 18,
                title=self._title,
                author=self._author,
                subject=self._subtitle or "Rask report",
                creator=f"{config.APP_NAME} {config.APP_VERSION}",
            )
            frame = Frame(
                self._margin, self._margin + 18,
                self._page_size[0] - 2 * self._margin,
                self._page_size[1] - 2 * self._margin - 18,
                leftPadding=0, rightPadding=0,
                topPadding=0, bottomPadding=0,
                showBoundary=0,
            )
            template = PageTemplate(
                id="main", frames=[frame],
                onPage=self._draw_page_decoration,
            )
            doc.addPageTemplates([template])
            doc.build(full_story)
        except Exception as exc:  # noqa: BLE001 — reportlab errors
            _log.error("PDF build failed: %s", exc)
            return False
        size = self._path.stat().st_size if self._path.exists() else 0
        _log.info("PDF written: %s (%d bytes)", self._path, size)
        # Clear story so the exporter can be re-used.
        self._story.clear()
        return True

    # ------------------------------------------------------------------
    # Internal: page decoration
    # ------------------------------------------------------------------

    def _draw_page_decoration(self, canvas, doc) -> None:
        """Draw the matte-black background + footer on every page."""
        canvas.saveState()
        # Background fill
        canvas.setFillColor(_C_MATTE)
        canvas.rect(0, 0, self._page_size[0], self._page_size[1],
                     fill=1, stroke=0)
        # Footer
        footer_y = 18
        canvas.setFont(self._font_regular or "Helvetica", 8)
        canvas.setFillColor(_C_TEXT_DIM)
        footer_left = f"{config.APP_NAME} v{config.APP_VERSION}"
        footer_right = datetime.now().strftime("%Y-%m-%d")
        page_num = canvas.getPageNumber()
        footer_center = f"{i18n.to_fa_digits(page_num) if self._lang == 'fa' else page_num}"
        canvas.drawString(self._margin, footer_y, footer_left)
        canvas.drawRightString(self._page_size[0] - self._margin, footer_y,
                                footer_right)
        canvas.drawCentredString(self._page_size[0] / 2, footer_y, footer_center)
        # Top gold accent line
        canvas.setStrokeColor(_C_GOLD_DIM)
        canvas.setLineWidth(0.5)
        canvas.line(self._margin, self._page_size[1] - self._margin + 10,
                     self._page_size[0] - self._margin,
                     self._page_size[1] - self._margin + 10)
        canvas.restoreState()

    # ------------------------------------------------------------------
    # Internal: table styles
    # ------------------------------------------------------------------

    def _summary_table_style(self) -> TableStyle:
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _C_CHARCOAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), _C_GOLD),
            ("FONTNAME", (0, 0), (-1, 0),
             self._font_bold or "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "RIGHT" if i18n.is_rtl(self._lang) else "LEFT"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT" if i18n.is_rtl(self._lang) else "LEFT"),
            ("BACKGROUND", (0, 1), (-1, -1), _C_SURFACE),
            ("TEXTCOLOR", (0, 1), (-1, -1), _C_TEXT),
            ("FONTNAME", (0, 1), (-1, -1),
             self._font_regular or "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_SURFACE, _C_CHARCOAL]),
            ("GRID", (0, 0), (-1, -1), 0.3, _C_DIVIDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])

    def _activities_table_style(self) -> TableStyle:
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _C_GOLD_DIM),
            ("TEXTCOLOR", (0, 0), (-1, 0), _C_MATTE),
            ("FONTNAME", (0, 0), (-1, 0),
             self._font_bold or "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BACKGROUND", (0, 1), (-1, -1), _C_SURFACE),
            ("TEXTCOLOR", (0, 1), (-1, -1), _C_TEXT),
            ("FONTNAME", (0, 1), (-1, -1),
             self._font_regular or "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_SURFACE, _C_CHARCOAL]),
            ("GRID", (0, 0), (-1, -1), 0.3, _C_DIVIDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])

    # ------------------------------------------------------------------
    # Internal: value formatting
    # ------------------------------------------------------------------

    def _escape(self, text: Any) -> str:
        """XML-escape text for reportlab Paragraph rendering."""
        if text is None:
            return ""
        s = str(text)
        # Replace & first to avoid double-escaping
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return s

    def _fmt_date(self, iso: Optional[str]) -> str:
        """Format an ISO date for display (Persian digits if fa)."""
        if not iso:
            return ""
        try:
            from ..core.jalali import iso_to_jalali
            y, m, d = iso_to_jalali(iso)
            s = f"{y:04d}-{m:02d}-{d:02d}"
        except Exception:  # noqa: BLE001 — fall back to Gregorian
            s = str(iso)
        if self._lang == "fa":
            s = i18n.to_fa_digits(s)
        return s

    def _fmt_duration(self, minutes: int) -> str:
        """Format a minute count as ``"۲h 30m"`` or Persian equivalent."""
        try:
            minutes = int(minutes or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            return "—"
        h, m = divmod(minutes, 60)
        if self._lang == "fa":
            if h > 0:
                s = f"{h} ساعت و {m} دقیقه"
            else:
                s = f"{m} دقیقه"
            return i18n.to_fa_digits(s)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    def _fmt_float(self, v: Any) -> str:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        s = f"{f:.1f}" if not f.is_integer() else str(int(f))
        return i18n.to_fa_digits(s) if self._lang == "fa" else s

    def _format_value(self, v: Any, key: str) -> Optional[str]:
        """Format a summary value based on its key's expected type."""
        if v is None:
            return None
        if isinstance(v, dict):
            # best_day / worst_day / longest_session
            if "total_min" in v:
                return self._fmt_duration(int(v["total_min"]))
            if "duration_min" in v:
                return self._fmt_duration(int(v["duration_min"]))
            if "date_iso" in v:
                return self._fmt_date(v["date_iso"])
            return None
        if isinstance(v, bool):
            return "بله" if v else "خیر" if self._lang == "fa" else (
                "Yes" if v else "No")
        if isinstance(v, (int, float)):
            if key in ("avg_per_day", "avg_per_activity"):
                return self._fmt_float(v)
            return i18n.to_fa_digits(str(int(v))) if self._lang == "fa" else str(int(v))
        return str(v)

    def _heatmap_level(self, minutes: int) -> int:
        """Map a minute count to a heatmap level 0..4."""
        try:
            minutes = int(minutes or 0)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            return 0
        if minutes < 30:
            return 1
        if minutes < 90:
            return 2
        if minutes < 180:
            return 3
        return 4

    # ------------------------------------------------------------------
    # Internal: matplotlib chart (optional, for nicer bar charts)
    # ------------------------------------------------------------------

    def _render_bar_chart_matplotlib(
        self,
        data: Sequence[Tuple[str, float]],
        title: str,
        width: int,
        height: int,
    ) -> Optional[str]:
        """Render a bar chart to a temp PNG using matplotlib.

        Returns the path to the PNG, or ``None`` if matplotlib is not
        available.  The PNG is written next to the PDF and given a
        random suffix; it is left in place (callers can clean up the
        ``EXPORT_DIR`` separately).
        """
        try:
            import matplotlib  # type: ignore[import-not-found]
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt  # type: ignore[import-not-found]
        except ImportError:
            return None
        try:
            labels = [str(k) for k, _ in data]
            values = [float(v) for _, v in data]
            fig, ax = plt.subplots(figsize=(width / 100, height / 100),
                                    dpi=100, facecolor=config.MATTE_BLACK)
            ax.set_facecolor(config.MATTE_BLACK)
            ax.bar(labels, values, color=config.GOLD, edgecolor=config.GOLD_BRIGHT,
                    linewidth=0.5)
            ax.tick_params(colors=config.TEXT_DIM)
            for spine in ax.spines.values():
                spine.set_color(config.DIVIDER)
            if title:
                ax.set_title(title, color=config.GOLD,
                              fontsize=12, pad=10)
            ax.yaxis.label.set_color(config.TEXT_DIM)
            ax.xaxis.label.set_color(config.TEXT_DIM)
            plt.tight_layout()
            out_path = str(self._path.parent / f"_chart_{id(data)}.png")
            fig.savefig(out_path, facecolor=config.MATTE_BLACK, dpi=100)
            plt.close(fig)
            return out_path
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning("matplotlib bar chart failed: %s", exc)
            return None


# =============================================================================
# === Self-test                                                                ===
# =============================================================================

def _self_test() -> int:
    """Run with:  python -m rask.export.pdf_export"""
    if not _REPORTLAB_AVAILABLE:
        print("SKIP: reportlab not installed")
        return 0
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.pdf")
        try:
            pdf = PdfExporter(path, lang="fa")
            pdf.set_title("گزارش آزمایشی")
            pdf.add_heading("خلاصه", level=1)
            pdf.add_paragraph("این یک گزارش آزمایشی است.")
            pdf.add_summary_table({
                "total_min": 240, "total_activities": 5,
                "avg_per_day": 48.0, "avg_per_activity": 48.0,
                "day_count": 5, "best_day": {"date_iso": "2025-07-18",
                                                "total_min": 90},
            })
            ok = pdf.save()
            if ok:
                size = os.path.getsize(path)
                print(f"OK: wrote {size} bytes")
            else:
                print("FAIL: save() returned False")
                return 1
        except Exception as exc:  # noqa: BLE001 — defensive
            print(f"FAIL: {exc}")
            return 1
    print("pdf_export self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
