"""
rask.tests.test_exporters
========================

Unit tests for the :mod:`rask.export` package and the extra
import/export functions in :mod:`rask.features.import_export_extra`.

Covers:

  • CsvExporter: writes valid CSV with BOM, columns correct, Persian
    text preserved
  • JsonExporter: valid JSON, schema correct, round-trip with DB
  • PdfExporter: writes non-empty PDF, has expected sections
  • ImageExporter: writes valid PNG report
  • ImportFromCSV: parses Toggl-style CSV
  • ImportFromJSON: round-trip with JsonExporter
  • ImportFromWebPWA: parses IndexedDB JSON
  • ExportToMarkdown: produces valid Markdown
  • ExportToHTML: produces valid HTML
  • ExportToICal: produces valid iCal
"""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, List

from rask import database as db
from rask.core.event_bus import bus
from rask.tests import fresh_db


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _seed_activities(n: int = 3) -> List[dict]:
    """Insert n activities and return their dicts."""
    out: List[dict] = []
    cats = db.category_list()
    for i in range(n):
        aid = db.activity_add(
            title=f"Activity {i}",
            category_id=cats[i % len(cats)]["id"],
            duration_min=30 + i * 15,
            date_iso=f"2025-01-{i+1:02d}",
            notes=f"Notes {i}" if i % 2 == 0 else None,
            tags=[f"tag{i}", "common"],
            kind="manual",
        )
        out.append(db.activity_get(aid))
    return out


# =============================================================================
# === CsvExporter                                                             ===
# =============================================================================

class TestCsvExporter(unittest.TestCase):
    """CsvExporter writes valid CSV with BOM and Persian text."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        self.activities = _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_writes_file(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "out.csv")
        exp = CsvExporter(path)
        n = exp.export_activities(self.activities)
        exp.save()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)
        self.assertEqual(n, 3)

    def test_csv_has_bom(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "out.csv")
        exp = CsvExporter(path)
        exp.export_activities(self.activities)
        exp.save()
        with open(path, "rb") as f:
            head = f.read(3)
        self.assertEqual(head[:3], b"\xef\xbb\xbf")  # UTF-8 BOM

    def test_csv_columns_correct(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "out.csv")
        exp = CsvExporter(path, persian_digits=False)
        exp.export_activities(self.activities)
        exp.save()
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
        # Check that some expected columns are present.
        self.assertIn("date", header)
        self.assertIn("title", header)
        self.assertIn("duration_min", header)
        self.assertIn("kind", header)

    def test_csv_rows_count_matches(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "out.csv")
        exp = CsvExporter(path, persian_digits=False)
        exp.export_activities(self.activities)
        exp.save()
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        # 1 header + 3 data rows.
        self.assertEqual(len(rows), 4)

    def test_csv_preserves_persian_text(self) -> None:
        """Persian text in titles survives the round-trip."""
        from rask.export.csv_export import CsvExporter
        aid = db.activity_add("مطالعه کتاب", None, 30, "2025-01-01",
                                notes="یک یادداشت فارسی")
        activities = [db.activity_get(aid)]
        path = os.path.join(self.tmp, "persian.csv")
        exp = CsvExporter(path, persian_digits=False)
        exp.export_activities(activities)
        exp.save()
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        self.assertIn("مطالعه کتاب", content)
        self.assertIn("یک یادداشت فارسی", content)

    def test_csv_with_metadata_columns(self) -> None:
        from rask.export.csv_export import CsvExporter
        path = os.path.join(self.tmp, "meta.csv")
        exp = CsvExporter(path, include_metadata=True, persian_digits=False)
        exp.export_activities(self.activities)
        exp.save()
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
        self.assertIn("id", header)


# =============================================================================
# === JsonExporter                                                            ===
# =============================================================================

class TestJsonExporter(unittest.TestCase):
    """JsonExporter writes valid JSON."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        self.activities = _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_all_writes_file(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "out.json")
        exp = JsonExporter(path)
        exp.export_all()
        exp.save()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_json_is_valid(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "out.json")
        exp = JsonExporter(path)
        exp.export_all()
        exp.save()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_json_has_meta_block(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "out.json")
        exp = JsonExporter(path)
        exp.export_all()
        exp.save()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("meta", data)
        meta = data["meta"]
        self.assertEqual(meta["app"], "Rask")
        self.assertIn("version", meta)
        self.assertIn("exported_at", meta)

    def test_json_contains_activities(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "out.json")
        exp = JsonExporter(path)
        exp.export_all()
        exp.save()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # export_all wraps tables under "data".
        self.assertIn("data", data)
        self.assertGreaterEqual(len(data["data"]["activities"]), 3)

    def test_json_export_activities_filtered(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "filtered.json")
        exp = JsonExporter(path)
        result = exp.export_activities(date_from="2025-01-01",
                                        date_to="2025-01-02")
        exp.save()
        # export_activities returns a dict payload (not a count).
        self.assertIsInstance(result, dict)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # export_activities returns mode="activities" with an "activities" list.
        self.assertIn("activities", data)

    def test_json_export_stats(self) -> None:
        from rask.export.json_export import JsonExporter
        path = os.path.join(self.tmp, "stats.json")
        exp = JsonExporter(path)
        exp.export_stats()
        exp.save()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # export_stats returns mode="stats" with a "summary" block.
        self.assertIn("summary", data)

    def test_json_preserves_persian_text(self) -> None:
        from rask.export.json_export import JsonExporter
        db.activity_add("مطالعه", None, 30, "2025-01-01")
        path = os.path.join(self.tmp, "persian.json")
        exp = JsonExporter(path)
        exp.export_all()
        exp.save()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        titles = [a["title"] for a in data["data"]["activities"]]
        self.assertIn("مطالعه", titles)


# =============================================================================
# === PdfExporter                                                             ===
# =============================================================================

class TestPdfExporter(unittest.TestCase):
    """PdfExporter writes a non-empty PDF."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        self.activities = _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_writes_pdf(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "out.pdf")
        exp = PdfExporter(path, title="Test Report", lang="fa")
        exp.add_heading("Section 1")
        exp.add_paragraph("Hello world.")
        exp.save()
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000)

    def test_pdf_starts_with_pdf_magic(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "magic.pdf")
        exp = PdfExporter(path)
        exp.add_heading("T")
        exp.save()
        with open(path, "rb") as f:
            head = f.read(4)
        self.assertEqual(head, b"%PDF")

    def test_pdf_with_activities_table(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "table.pdf")
        exp = PdfExporter(path, title="Activities")
        exp.add_activities_table(self.activities)
        exp.save()
        self.assertGreater(os.path.getsize(path), 1000)

    def test_pdf_with_summary_table(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "summary.pdf")
        exp = PdfExporter(path, title="Summary")
        summary = {"total_min": 100, "total_activities": 3,
                   "avg_per_day": 33.3}
        exp.add_summary_table(summary)
        exp.save()
        self.assertGreater(os.path.getsize(path), 1000)

    def test_pdf_with_multiple_sections(self) -> None:
        from rask.export.pdf_export import PdfExporter
        path = os.path.join(self.tmp, "multi.pdf")
        exp = PdfExporter(path, title="Multi")
        exp.add_heading("Section A")
        exp.add_paragraph("Content A.")
        exp.add_page_break()
        exp.add_heading("Section B")
        exp.add_paragraph("Content B.")
        exp.add_bullet_list(["Item 1", "Item 2", "Item 3"])
        exp.save()
        self.assertGreater(os.path.getsize(path), 2000)


# =============================================================================
# === ImageExporter                                                           ===
# =============================================================================

class TestImageExporter(unittest.TestCase):
    """ImageExporter writes a valid PNG report."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_report_writes_png(self) -> None:
        from rask.export.image_export import ImageExporter
        path = os.path.join(self.tmp, "report.png")
        exp = ImageExporter(path)
        ok = exp.export_report(
            stats={"total_min": 100, "total_activities": 5},
            charts=[],
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000)

    def test_export_report_with_title(self) -> None:
        from rask.export.image_export import ImageExporter
        path = os.path.join(self.tmp, "titled.png")
        exp = ImageExporter(path)
        ok = exp.export_report(
            stats={"total_min": 200},
            charts=[],
            title="My Report",
        )
        self.assertTrue(ok)

    def test_png_starts_with_png_signature(self) -> None:
        from rask.export.image_export import ImageExporter
        path = os.path.join(self.tmp, "sig.png")
        exp = ImageExporter(path)
        exp.export_report(stats={"total_min": 0}, charts=[])
        with open(path, "rb") as f:
            head = f.read(8)
        # PNG magic bytes.
        self.assertEqual(head, b"\x89PNG\r\n\x1a\n")


# =============================================================================
# === ImportFromCSV                                                           ===
# =============================================================================

class TestImportFromCSV(unittest.TestCase):
    """ImportFromCSV parses Toggl-style CSV."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_toggl_style_csv(self) -> None:
        from rask.features.import_export_extra import ImportFromCSV
        path = os.path.join(self.tmp, "toggl.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Description,Start time,End time,Duration,Tags,Project\n")
            f.write("Reading,2025-01-01 09:00:00,2025-01-01 10:00:00,"
                    "3600,books,Learn\n")
            f.write("Coding,2025-01-01 10:30:00,2025-01-01 12:00:00,"
                    "5400,dev,Work\n")
        result = ImportFromCSV(path)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 2)

    def test_import_csv_with_empty_file(self) -> None:
        from rask.features.import_export_extra import ImportFromCSV
        path = os.path.join(self.tmp, "empty.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Description,Start time,End time,Duration,Tags,Project\n")
        result = ImportFromCSV(path)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    def test_import_csv_returns_path(self) -> None:
        from rask.features.import_export_extra import ImportFromCSV
        path = os.path.join(self.tmp, "p.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Description,Start time,End time,Duration,Tags,Project\n")
            f.write("Test,2025-01-01 09:00:00,2025-01-01 09:30:00,"
                    "1800,t,Work\n")
        result = ImportFromCSV(path)
        self.assertEqual(result["path"], path)


# =============================================================================
# === ImportFromJSON (round-trip)                                             ===
# =============================================================================

class TestImportFromJSON(unittest.TestCase):
    """ImportFromJSON round-trips with JsonExporter."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip_export_then_import(self) -> None:
        from rask.export.json_export import JsonExporter
        from rask.features.import_export_extra import ImportFromJSON
        # Export to JSON.
        export_path = os.path.join(self.tmp, "export.json")
        exp = JsonExporter(export_path)
        exp.export_all()
        exp.save()
        # Wipe DB activities (soft delete).
        for a in db.activity_list(limit=1000):
            db.activity_delete(a["id"], soft=False)
        self.assertEqual(db.activity_count(), 0)
        # Import back.
        result = ImportFromJSON(export_path)
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["count"], 3)


# =============================================================================
# === ImportFromWebPWA                                                        ===
# =============================================================================

class TestImportFromWebPWA(unittest.TestCase):
    """ImportFromWebPWA parses IndexedDB JSON."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_pwa_style_json(self) -> None:
        from rask.features.import_export_extra import ImportFromWebPWA
        path = os.path.join(self.tmp, "pwa.json")
        # IndexedDB-style export: activities array.
        payload = {
            "activities": [
                {"title": "Reading", "duration": 30, "date": "2025-01-01",
                 "category": "Learn"},
                {"title": "Workout", "duration": 60, "date": "2025-01-02",
                 "category": "Health"},
            ],
            "categories": [],
            "goals": [],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        result = ImportFromWebPWA(path)
        # The function should succeed and import the activities.
        self.assertTrue(result["success"])


# =============================================================================
# === ExportToMarkdown                                                        ===
# =============================================================================

class TestExportToMarkdown(unittest.TestCase):
    """ExportToMarkdown produces valid Markdown."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_markdown_writes_file(self) -> None:
        from rask.features.import_export_extra import ExportToMarkdown
        path = os.path.join(self.tmp, "out.md")
        result = ExportToMarkdown(path)
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_markdown_starts_with_heading(self) -> None:
        from rask.features.import_export_extra import ExportToMarkdown
        path = os.path.join(self.tmp, "head.md")
        ExportToMarkdown(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Markdown headings start with '#'.
        self.assertIn("#", content)


# =============================================================================
# === ExportToHTML                                                            ===
# =============================================================================

class TestExportToHTML(unittest.TestCase):
    """ExportToHTML produces valid HTML."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_html_writes_file(self) -> None:
        from rask.features.import_export_extra import ExportToHTML
        path = os.path.join(self.tmp, "out.html")
        result = ExportToHTML(path)
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_html_contains_html_tag(self) -> None:
        from rask.features.import_export_extra import ExportToHTML
        path = os.path.join(self.tmp, "tagged.html")
        ExportToHTML(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Should contain HTML structural tags.
        self.assertTrue("<html" in content.lower() or
                        "<!doctype" in content.lower())


# =============================================================================
# === ExportToICal                                                            ===
# =============================================================================

class TestExportToICal(unittest.TestCase):
    """ExportToICal produces valid iCal."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.tmp = tempfile.mkdtemp()
        _seed_activities(3)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_ical_writes_file(self) -> None:
        from rask.features.import_export_extra import ExportToICal
        path = os.path.join(self.tmp, "out.ics")
        result = ExportToICal(path)
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_ical_starts_with_vcalendar(self) -> None:
        from rask.features.import_export_extra import ExportToICal
        path = os.path.join(self.tmp, "cal.ics")
        ExportToICal(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("END:VCALENDAR", content)


if __name__ == "__main__":
    unittest.main()
