"""
rask.export.csv_export
======================

UTF-8-BOM CSV exporter for Rask activities.

The CSV format mirrors what the user sees in the activity list but
adds a few bookkeeping columns (id, template_id, recurring_id) that
are useful for round-trip imports.  The BOM (``\\ufeff``) is written
so Microsoft Excel auto-detects UTF-8 encoding when opening the file.

Layout
------
Columns (in order):

    1.  date           — Gregorian YYYY-MM-DD
    2.  jalali_date    — Jalali YYYY-MM-DD (denormalised for sorting)
    3.  title          — activity title
    4.  category_name  — localised name of the activity's category
    5.  category_color — hex colour (without ``#``)
    6.  duration_min   — integer minutes
    7.  duration_human — ``"۲ ساعت و ۳۰ دقیقه"`` style (localised)
    8.  start_time     — ``HH:MM:SS`` (blank for manual entries)
    9.  end_time       — ``HH:MM:SS`` (blank for manual entries)
    10. notes          — free-form notes
    11. tags           — semicolon-separated tag list
    12. kind           — ``manual`` / ``stopwatch`` / ``template`` /
                        ``voice`` / ``recurring``
    13. source         — ``desktop`` / ``web`` / ``import``
    14. created_at     — ISO-8601 timestamp

Optional metadata columns (``include_metadata=True``, default ``False``):

    - id
    - template_id
    - recurring_id

Persian digits
--------------
By default (``persian_digits=True`` when ``lang="fa"``), numeric values
are converted to Persian digits to match the in-app display.  Pass
``persian_digits=False`` to keep Western digits — recommended for
machine-readable exports (the user can always toggle this in the
export dialog).

Escaping
--------
All values are passed through :func:`csv.writer` which handles quoting
of fields containing commas, double-quotes, or newlines.  Embedded
newlines in notes are preserved (CSV allows CRLF within quoted fields).

Mirrors ``web/js/export-csv.js`` 1:1.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .. import config
from .. import i18n
from ..core.logging_utils import get_logger
from ..core.time_utils import format_duration

__all__ = ["CsvExporter"]

_log = get_logger("export.csv")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _to_hhmmss(iso_ts: Optional[str]) -> str:
    """Extract the ``HH:MM:SS`` portion from an ISO-8601 timestamp.

    Returns an empty string for ``None`` / unparseable input.
    """
    if not iso_ts or not isinstance(iso_ts, str):
        return ""
    # ISO timestamps look like ``2025-07-18T14:30:00`` or
    # ``2025-07-18T14:30:00.123456+00:00``.  We just take chars 11..19.
    try:
        if len(iso_ts) >= 19:
            return iso_ts[11:19]
        return ""
    except Exception:  # noqa: BLE001 — defensive
        return ""


def _parse_tags(tags_json: Any) -> List[str]:
    """Decode a ``tags_json`` column value into a list of strings."""
    if not tags_json:
        return []
    if isinstance(tags_json, (list, tuple)):
        return [str(t) for t in tags_json]
    if isinstance(tags_json, str):
        try:
            v = json.loads(tags_json)
            if isinstance(v, list):
                return [str(t) for t in v]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _category_lookup() -> Dict[int, Dict[str, Any]]:
    """Return a dict ``category_id -> category row``.

    Imports :mod:`rask.database` lazily so this module remains
    importable in environments where the DB has not been opened
    (e.g. when generating a CSV from an in-memory activity list).
    """
    out: Dict[int, Dict[str, Any]] = {}
    try:
        from .. import database as db
        for c in db.category_list(include_archived=True):
            try:
                out[int(c["id"])] = dict(c)
            except (KeyError, TypeError, ValueError):
                continue
    except Exception as exc:  # noqa: BLE001 — best-effort lookup
        _log.debug("category lookup failed: %s", exc)
    return out


def _localize_category_name(cat: Dict[str, Any], lang: str) -> str:
    """Pick the localised name from a category row."""
    if not cat:
        return ""
    if lang == "fa":
        return str(cat.get("name_fa") or cat.get("name_en") or "")
    return str(cat.get("name_en") or cat.get("name_fa") or "")


def _strip_hex(color: Optional[str]) -> str:
    """Return a hex colour string without the leading ``#``.

    Returns an empty string for ``None`` or malformed input.
    """
    if not color or not isinstance(color, str):
        return ""
    s = color.strip()
    if s.startswith("#"):
        s = s[1:]
    return s


def _format_duration_human(minutes: int, lang: str) -> str:
    """Return a localised ``"۲ ساعت و ۳۰ دقیقه"`` style duration string."""
    try:
        minutes = int(minutes or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return ""
    text = format_duration(minutes, lang=lang)
    if lang == "fa":
        text = i18n.to_fa_digits(text)
    return text


# =============================================================================
# === CsvExporter                                                              ===
# =============================================================================

class CsvExporter:
    """Reusable CSV exporter.

    Construct with a target path and optional ``lang`` then call one or
    more of the ``export_*`` methods to append content.  Finally call
    :meth:`save` to flush the file to disk.

    Parameters
    ----------
    file_path
        Destination path.  Parent directories are created on save.
    lang
        UI language for localised column values.  Default ``"fa"``.
    persian_digits
        If True and ``lang == "fa"``, numeric values are converted to
        Persian digits.  Default True (matches in-app display).
    include_metadata
        If True, ``id``, ``template_id``, ``recurring_id`` columns are
        appended to the activities table.  Default False.
    delimiter
        Field separator.  Default :data:`config.EXPORT_CSV_DELIMITER`.
    encoding
        Output encoding.  Default :data:`config.EXPORT_CSV_ENCODING`
        (UTF-8 with BOM).

    Examples
    --------
    >>> from rask.export.csv_export import CsvExporter
    >>> exp = CsvExporter("/tmp/acts.csv", lang="fa")
    >>> exp.export_activities(activities)
    >>> exp.save()
    True
    """

    # Column order — kept as a tuple so callers can introspect it.
    BASE_COLUMNS: Tuple[str, ...] = (
        "date", "jalali_date", "title", "category_name",
        "category_color", "duration_min", "duration_human",
        "start_time", "end_time", "notes", "tags", "kind", "source",
        "created_at",
    )
    METADATA_COLUMNS: Tuple[str, ...] = ("id", "template_id", "recurring_id")

    # ------------------------------------------------------------------
    def __init__(
        self,
        file_path: Union[str, Path],
        lang: str = "fa",
        *,
        persian_digits: Optional[bool] = None,
        include_metadata: bool = False,
        delimiter: Optional[str] = None,
        encoding: Optional[str] = None,
    ) -> None:
        self._path: Path = Path(file_path)
        self._lang: str = lang if lang in config.SUPPORTED_LANGUAGES else "fa"
        # Persian digits default to True when lang=fa, False otherwise.
        if persian_digits is None:
            persian_digits = (self._lang == "fa")
        self._persian_digits: bool = bool(persian_digits)
        self._include_metadata: bool = bool(include_metadata)
        self._delimiter: str = (
            delimiter if delimiter is not None else config.EXPORT_CSV_DELIMITER
        )
        self._encoding: str = (
            encoding if encoding is not None else config.EXPORT_CSV_ENCODING
        )
        # Row buffer (list-of-lists).  Cleared after :meth:`save`.
        self._rows: List[List[str]] = []
        self._header_written: bool = False
        self._header: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_activities(
        self,
        activities: Sequence[Dict[str, Any]],
        *,
        include_metadata: Optional[bool] = None,
    ) -> int:
        """Append the activity rows to the CSV buffer.

        Returns the number of rows appended.  This method can be called
        multiple times — subsequent calls append rows to the same
        buffer.  Pass ``include_metadata=True`` to override the
        instance-level setting for just this call.
        """
        use_meta = (
            self._include_metadata if include_metadata is None
            else bool(include_metadata)
        )
        cats = _category_lookup()
        # First call writes the header.
        if not self._header_written:
            self._header = list(self.BASE_COLUMNS)
            if use_meta:
                self._header.extend(self.METADATA_COLUMNS)
            self._rows.append(self._header)
            self._header_written = True

        count: int = 0
        for act in activities:
            row = self._activity_to_row(act, cats, use_meta)
            self._rows.append(row)
            count += 1
        _log.debug("Queued %d activity rows (total=%d)", count, len(self._rows) - 1)
        return count

    def export_summary(self, stats: Dict[str, Any]) -> int:
        """Append a summary block (total / avg / best day) as 3 rows.

        The block is preceded by a blank line so spreadsheet apps show
        it visually separated from any preceding activity list.
        """
        if not self._header_written:
            # No header yet — write a minimal one.
            self._header = ["metric", "value"]
            self._rows.append(self._header)
            self._header_written = True
        else:
            self._rows.append([])  # blank separator

        rows = [
            ("total_min", stats.get("total_min", 0)),
            ("total_activities", stats.get("total_activities", 0)),
            ("avg_per_day", stats.get("avg_per_day", 0)),
            ("avg_per_activity", stats.get("avg_per_activity", 0)),
            ("day_count", stats.get("day_count", 0)),
            ("best_day", (stats.get("best_day") or {}).get("date_iso", "")),
            ("best_day_min", (stats.get("best_day") or {}).get("total_min", 0)),
            ("longest_session_min",
             (stats.get("longest_session") or {}).get("duration_min", 0)),
            ("date_from", stats.get("date_from", "")),
            ("date_to", stats.get("date_to", "")),
        ]
        count = 0
        for metric, value in rows:
            self._rows.append([metric, self._fmt_value(value)])
            count += 1
        _log.debug("Queued %d summary rows", count)
        return count

    def export_categories(self, categories: Sequence[Dict[str, Any]]) -> int:
        """Append a categories block (key, names, colour, archived)."""
        if self._header_written:
            self._rows.append([])  # blank separator
        self._rows.append([
            "id", "key", "name_en", "name_fa", "color", "icon",
            "order_index", "archived",
        ])
        count = 0
        for c in categories:
            self._rows.append([
                self._fmt_value(c.get("id")),
                str(c.get("key", "")),
                str(c.get("name_en", "")),
                str(c.get("name_fa", "")),
                _strip_hex(c.get("color")),
                str(c.get("icon", "")),
                self._fmt_value(c.get("order_index", 0)),
                self._fmt_value(c.get("archived", 0)),
            ])
            count += 1
        self._header_written = True
        _log.debug("Queued %d category rows", count)
        return count

    def export_goals(self, goals: Sequence[Dict[str, Any]]) -> int:
        """Append a goals block (period, target, category, reminder)."""
        if self._header_written:
            self._rows.append([])  # blank separator
        self._rows.append([
            "id", "period", "target_minutes", "category_id",
            "title", "color", "reminder_enabled", "reminder_time",
            "active",
        ])
        count = 0
        for g in goals:
            self._rows.append([
                self._fmt_value(g.get("id")),
                str(g.get("period", "")),
                self._fmt_value(g.get("target_minutes", 0)),
                self._fmt_value(g.get("category_id")),
                str(g.get("title", "") or ""),
                _strip_hex(g.get("color")),
                self._fmt_value(int(bool(g.get("reminder_enabled")))),
                str(g.get("reminder_time", "") or ""),
                self._fmt_value(int(bool(g.get("active", 1)))),
            ])
            count += 1
        self._header_written = True
        _log.debug("Queued %d goal rows", count)
        return count

    def save(self) -> bool:
        """Write the buffered rows to disk.

        Returns True on success, False on error.  The buffer is
        cleared after a successful save so the exporter can be reused.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error("Cannot create parent dir for %s: %s", self._path, exc)
            return False
        try:
            with self._path.open("w", encoding=self._encoding, newline="") as f:
                writer = csv.writer(
                    f,
                    delimiter=self._delimiter,
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\r\n",  # Excel-friendly
                )
                for row in self._rows:
                    writer.writerow(row)
        except OSError as exc:
            _log.error("Failed to write CSV %s: %s", self._path, exc)
            return False
        size = self._path.stat().st_size if self._path.exists() else 0
        _log.info("CSV written: %s (%d rows, %d bytes)",
                  self._path, max(0, len(self._rows) - 1), size)
        self._rows.clear()
        self._header_written = False
        self._header = []
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _activity_to_row(
        self,
        act: Dict[str, Any],
        cats: Dict[int, Dict[str, Any]],
        include_metadata: bool,
    ) -> List[str]:
        """Convert one activity dict to a CSV row (list of strings)."""
        cat_id = act.get("category_id")
        cat = cats.get(int(cat_id)) if cat_id else None
        cat_name = _localize_category_name(cat, self._lang) if cat else ""
        cat_color = _strip_hex(cat.get("color")) if cat else ""

        duration_min = int(act.get("duration_min", 0) or 0)
        duration_human = _format_duration_human(duration_min, self._lang)

        tags_list = _parse_tags(act.get("tags_json") or act.get("tags"))
        tags_str = ";".join(tags_list)

        row: List[str] = [
            str(act.get("date_iso", "") or ""),
            str(act.get("jalali_iso", "") or ""),
            str(act.get("title", "") or ""),
            cat_name,
            cat_color,
            self._fmt_value(duration_min),
            duration_human,
            _to_hhmmss(act.get("start_ts")),
            _to_hhmmss(act.get("end_ts")),
            str(act.get("notes", "") or ""),
            tags_str,
            str(act.get("kind", "manual") or "manual"),
            str(act.get("source", "desktop") or "desktop"),
            str(act.get("created_at", "") or ""),
        ]
        if include_metadata:
            row.append(self._fmt_value(act.get("id")))
            row.append(self._fmt_value(act.get("template_id")))
            row.append(self._fmt_value(act.get("recurring_id")))
        return row

    def _fmt_value(self, value: Any) -> str:
        """Format a scalar value for a CSV cell, applying Persian digits."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            s = str(value)
        elif isinstance(value, float):
            # Strip trailing .0 for integers stored as float.
            if value.is_integer():
                s = str(int(value))
            else:
                s = f"{value:.2f}".rstrip("0").rstrip(".")
        else:
            s = str(value)
        if self._persian_digits and s:
            # Only convert digit characters, leave punctuation alone.
            s = i18n.to_fa_digits(s)
        return s

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def lang(self) -> str:
        return self._lang

    @property
    def pending_rows(self) -> int:
        """Number of rows queued but not yet written to disk."""
        return len(self._rows)


# =============================================================================
# === Self-test                                                                ===
# =============================================================================

def _self_test() -> int:
    """Lightweight self-test — run with:  python -m rask.export.csv_export"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.csv")
        exp = CsvExporter(path, lang="fa", include_metadata=True)
        activities = [
            {"id": 1, "date_iso": "2025-07-18", "jalali_iso": "1404-04-27",
             "title": "مطالعه", "category_id": None, "duration_min": 90,
             "start_ts": "2025-07-18T10:00:00",
             "end_ts": "2025-07-18T11:30:00",
             "notes": "کتاب اول", "tags_json": '["کتاب", "یادگیری"]',
             "kind": "manual", "source": "desktop",
             "created_at": "2025-07-18T11:30:05"},
        ]
        n1 = exp.export_activities(activities)
        assert n1 == 1, f"expected 1 row, got {n1}"
        ok = exp.save()
        assert ok, "save() returned False"
        size = os.path.getsize(path)
        assert size > 0, "file is empty"
        print(f"OK: wrote {n1} row + header, {size} bytes")
        # Re-open and check the BOM.
        with open(path, "rb") as f:
            head = f.read(3)
        assert head == b"\xef\xbb\xbf", f"BOM missing: {head!r}"
        print("OK: UTF-8 BOM present")
    print("csv_export self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
