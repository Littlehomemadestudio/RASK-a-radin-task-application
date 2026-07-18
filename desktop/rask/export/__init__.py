"""
rask.export
===========

Low-level exporter classes for the Rask desktop application.

This package sits **below** :mod:`rask.services.export_service` and
provides reusable, framework-free classes for emitting PDF / CSV /
JSON / PNG output.  Each class is a small builder with a fluent API:

>>> from rask.export.pdf_export import PdfExporter
>>> pdf = PdfExporter("/tmp/rask.pdf", lang="fa")
>>> pdf.set_title("گزارش روزانه").add_heading("خلاصه").save()

The :mod:`rask.services.export_service` singleton wraps these classes
with audit logging, event-bus publication, and DB integration — call
that service from application code rather than these classes directly.

Modules
-------
``pdf_export``    — :class:`PdfExporter` (reportlab-based, gold-on-dark)
``csv_export``    — :class:`CsvExporter` (UTF-8 with BOM, Persian digits)
``json_export``   — :class:`JsonExporter` (pretty-printed, schema-stamped)
``image_export``  — :class:`ImageExporter` (Pillow-composed PNG screenshots)

Persian font support
--------------------
All PDF and image export classes probe the system for the
``Vazirmatn`` font (the same font used by the web PWA).  If it is not
installed, the exporters gracefully fall back to ``Tahoma`` /
``Segoe UI`` / ``Arial`` so output is always readable, even if the
Persian shaping is imperfect.
"""
from __future__ import annotations

__all__ = [
    "PdfExporter",
    "CsvExporter",
    "JsonExporter",
    "ImageExporter",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """PEP 562 lazy importer — heavy deps (reportlab, PIL) load on demand.

    This keeps ``import rask.export`` cheap when the caller only needs
    one of the four exporter classes.  Missing optional dependencies
    (e.g. reportlab) raise a clear :class:`ImportError` at the point
    of use rather than at package import time.
    """
    if name == "PdfExporter":
        from .pdf_export import PdfExporter
        globals()["PdfExporter"] = PdfExporter
        return PdfExporter
    if name == "CsvExporter":
        from .csv_export import CsvExporter
        globals()["CsvExporter"] = CsvExporter
        return CsvExporter
    if name == "JsonExporter":
        from .json_export import JsonExporter
        globals()["JsonExporter"] = JsonExporter
        return JsonExporter
    if name == "ImageExporter":
        from .image_export import ImageExporter
        globals()["ImageExporter"] = ImageExporter
        return ImageExporter
    raise AttributeError(f"module 'rask.export' has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover — introspection helper
    return sorted(set(__all__ + list(globals().keys())))
