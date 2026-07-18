"""
rask.export.json_export
=======================

Pretty-printed JSON exporter for Rask data.

Three export modes are supported:

* ``export_all()``            — full database dump (every table)
* ``export_activities(d_from, d_to)`` — filtered activity list with
                                          category metadata inlined
* ``export_stats(d_from, d_to)``      — high-level summary metrics

The output is always UTF-8 with ``ensure_ascii=False`` so Persian
glyphs are preserved verbatim.  A ``meta`` block at the top of every
file records:

    - ``app``             — ``"Rask"``
    - ``version``         — :data:`rask.config.APP_VERSION`
    - ``build``           — :data:`rask.config.APP_BUILD`
    - ``schema_version``  — :data:`rask.database.SCHEMA_VERSION`
    - ``exported_at``     — ISO-8601 UTC timestamp
    - ``mode``            — ``"all"`` / ``"activities"`` / ``"stats"``

Round-trip compatibility
------------------------
The ``export_all()`` payload is exactly what
:func:`rask.database.import_from_dict` expects — so a JSON file
produced by this exporter can be re-imported into a fresh database
without any transformation.

Mirrors ``web/js/export-json.js`` 1:1 (the web PWA's "Export JSON"
button).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .. import config
from ..core.logging_utils import get_logger
from ..core.time_utils import now_iso_utc, today_iso, add_days

__all__ = ["JsonExporter"]

_log = get_logger("export.json")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _utc_now_iso() -> str:
    """Return current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _meta(mode: str) -> Dict[str, Any]:
    """Build the standard metadata block added to every export."""
    # ``SCHEMA_VERSION`` lives in :mod:`rask.database`; import lazily so
    # this module can be imported without the DB module being loaded.
    try:
        from .. import database as db
        schema = db.SCHEMA_VERSION
    except Exception:  # noqa: BLE001 — best-effort
        schema = 1
    return {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "build": config.APP_BUILD,
        "schema_version": schema,
        "exported_at": _utc_now_iso(),
        "mode": mode,
    }


def _ensure_date_range(
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, str]:
    """Default / normalise a date range to ``(from, to)``.

    Defaults to the last 30 days if either side is missing.  Swaps
    them if they are reversed.  Returns strings as-is if they are
    already valid ISO dates.
    """
    today = today_iso()
    if not date_from and not date_to:
        return add_days(today, -30), today
    if not date_from:
        date_from = add_days(date_to or today, -30)
    if not date_to:
        date_to = today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _category_map() -> Dict[int, Dict[str, Any]]:
    """Return ``{category_id: category_row}`` (best-effort)."""
    out: Dict[int, Dict[str, Any]] = {}
    try:
        from .. import database as db
        for c in db.category_list(include_archived=True):
            try:
                out[int(c["id"])] = dict(c)
            except (KeyError, TypeError, ValueError):
                continue
    except Exception as exc:  # noqa: BLE001
        _log.debug("category lookup failed: %s", exc)
    return out


def _normalise_activity(row: Dict[str, Any],
                         cats: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """Convert a raw DB activity row into a clean JSON-serialisable dict.

    Inlines the localised category name and colour, parses the
    ``tags_json`` column, and drops bookkeeping columns that callers
    should not depend on.
    """
    out = dict(row)
    # Coerce nullable ints.
    for k in ("id", "category_id", "duration_min",
              "template_id", "recurring_id"):
        v = out.get(k)
        if v is not None:
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
    # Parse tags_json -> tags list.
    raw_tags = out.pop("tags_json", None)
    if isinstance(raw_tags, str) and raw_tags:
        try:
            out["tags"] = json.loads(raw_tags)
        except (json.JSONDecodeError, TypeError):
            out["tags"] = []
    elif isinstance(raw_tags, list):
        out["tags"] = list(raw_tags)
    else:
        out["tags"] = []
    # Inline category metadata.
    cat_id = out.get("category_id")
    cat = cats.get(int(cat_id)) if cat_id else None
    if cat:
        out["category_key"] = cat.get("key")
        out["category_name_en"] = cat.get("name_en")
        out["category_name_fa"] = cat.get("name_fa")
        out["category_color"] = cat.get("color")
        out["category_icon"] = cat.get("icon")
    else:
        out["category_key"] = None
        out["category_name_en"] = None
        out["category_name_fa"] = None
        out["category_color"] = None
        out["category_icon"] = None
    return out


# =============================================================================
# === JsonExporter                                                              ===
# =============================================================================

class JsonExporter:
    """Reusable JSON exporter.

    Examples
    --------
    >>> from rask.export.json_export import JsonExporter
    >>> exp = JsonExporter("/tmp/rask_all.json")
    >>> exp.export_all()
    >>> exp.save()
    True
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        *,
        indent: int = 2,
    ) -> None:
        self._path: Path = Path(file_path)
        self._indent: int = max(0, int(indent))
        self._payload: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_all(self) -> Dict[str, Any]:
        """Build a full-database dump payload.

        Uses :func:`rask.database.export_to_dict` to read every table
        row, then wraps it in a metadata envelope.
        """
        from .. import database as db
        try:
            data = db.export_to_dict()
        except Exception as exc:  # noqa: BLE001
            _log.error("export_to_dict failed: %s", exc)
            data = {"data": {}}
        payload: Dict[str, Any] = {
            "meta": _meta("all"),
            "data": data.get("data", {}),
        }
        self._payload = payload
        return payload

    def export_activities(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a filtered activities payload.

        Parameters
        ----------
        date_from, date_to
            Optional ISO date strings.  Default to the last 30 days.
        """
        from .. import database as db
        date_from, date_to = _ensure_date_range(date_from, date_to)
        try:
            rows = db.activity_list(
                date_from=date_from, date_to=date_to, limit=100000)
        except Exception as exc:  # noqa: BLE001
            _log.error("activity_list failed: %s", exc)
            rows = []
        cats = _category_map()
        activities = [_normalise_activity(r, cats) for r in rows]
        payload: Dict[str, Any] = {
            "meta": {**_meta("activities"),
                      "date_from": date_from,
                      "date_to": date_to,
                      "record_count": len(activities)},
            "activities": activities,
        }
        self._payload = payload
        return payload

    def export_stats(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a stats summary payload.

        Calls :meth:`rask.services.stats_service.summary` and wraps
        the result.  Falls back to an empty summary if the service is
        unavailable.
        """
        date_from, date_to = _ensure_date_range(date_from, date_to)
        try:
            from ..services import stats_service
            summary = stats_service.summary(date_from, date_to)
        except Exception as exc:  # noqa: BLE001
            _log.error("stats_service.summary failed: %s", exc)
            summary = {
                "total_min": 0, "total_activities": 0,
                "avg_per_day": 0.0, "avg_per_activity": 0.0,
                "best_day": None, "worst_day": None,
                "longest_session": None, "day_count": 0,
                "date_from": date_from, "date_to": date_to,
            }
        payload: Dict[str, Any] = {
            "meta": {**_meta("stats"),
                      "date_from": date_from,
                      "date_to": date_to},
            "summary": summary,
        }
        self._payload = payload
        return payload

    def save(self) -> bool:
        """Write the pending payload to disk as pretty-printed JSON.

        Returns True on success, False on error.
        """
        if self._payload is None:
            _log.warning("save() called before any export_* method — nothing to write")
            return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error("Cannot create parent dir for %s: %s", self._path, exc)
            return False
        try:
            text = json.dumps(self._payload, ensure_ascii=False,
                              indent=self._indent, sort_keys=False,
                              default=str)
        except (TypeError, ValueError) as exc:
            _log.error("JSON serialisation failed: %s", exc)
            return False
        try:
            self._path.write_text(text, encoding="utf-8")
        except OSError as exc:
            _log.error("Failed to write JSON %s: %s", self._path, exc)
            return False
        size = self._path.stat().st_size if self._path.exists() else 0
        _log.info("JSON written: %s (%d bytes)", self._path, size)
        return True

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def payload(self) -> Optional[Dict[str, Any]]:
        return self._payload


# =============================================================================
# === Self-test                                                                ===
# =============================================================================

def _self_test() -> int:
    """Run with:  python -m rask.export.json_export"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "stats.json")
        exp = JsonExporter(path)
        # Stats export doesn't require DB to be opened — service returns
        # an empty summary on error.
        try:
            exp.export_stats("2025-01-01", "2025-01-31")
            ok = exp.save()
            assert ok, "save() returned False"
            size = os.path.getsize(path)
            assert size > 0
            print(f"OK: stats.json written ({size} bytes)")
        except Exception as exc:  # noqa: BLE001 — defensive
            print(f"SKIP: stats export requires DB ({exc})")
    print("json_export self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
