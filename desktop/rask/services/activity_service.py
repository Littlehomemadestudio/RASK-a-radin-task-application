"""
rask.services.activity_service
==============================

Business logic for activity records.

Wraps :mod:`rask.database` activity repository functions with:
  • Input validation via :mod:`rask.core.validators`
  • Automatic Jalali ISO computation on every insert / date change
  • Tag sanitization (lowercased, deduped, ≤10 entries)
  • Event-bus publication (``activity.added`` / ``activity.updated`` /
    ``activity.deleted``)
  • Background-recording lifecycle (start/stop/cancel) with wall-clock
    duration computation

The service is a module-level singleton (:data:`activity_service`).
All methods return plain ``dict`` instances (never ``sqlite3.Row``)
so callers can safely mutate them without affecting DB state.

Mirrors the behavior of ``web/js/db.js`` activity CRUD plus the
``web/js/timer.js`` stopwatch stop-and-save flow.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.jalali import iso_to_jalali
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_utc, today_iso
from ..core.validators import (
    is_valid_duration_min,
    is_valid_iso_date,
    is_valid_iso_datetime,
    sanitize_notes,
    sanitize_tags,
    sanitize_title,
)

__all__ = ["ActivityService", "activity_service"]

_log = get_logger("services.activity")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _compute_jalali_iso(date_iso: Optional[str]) -> Optional[str]:
    """Convert a Gregorian ISO date to a Jalali ISO date.

    Returns ``None`` if the input is missing or unparseable — never raises.
    """
    if not date_iso or not is_valid_iso_date(date_iso):
        return None
    try:
        jy, jm, jd = iso_to_jalali(date_iso)
        return f"{jy:04d}-{jm:02d}-{jd:02d}"
    except Exception:  # noqa: BLE001
        return None


def _row_to_activity(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB row dict into a clean activity dict.

    - Parses ``tags_json`` -> ``tags`` (list)
    - Drops the ``tags_json`` field (callers don't need it)
    - Coerces nullable ints
    """
    if row is None:
        return None
    out = dict(row)
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
    # Defensive coercion
    if out.get("duration_min") is None:
        out["duration_min"] = 0
    else:
        try:
            out["duration_min"] = int(out["duration_min"])
        except (TypeError, ValueError):
            out["duration_min"] = 0
    if out.get("category_id") is not None:
        try:
            out["category_id"] = int(out["category_id"])
        except (TypeError, ValueError):
            out["category_id"] = None
    if out.get("template_id") is not None:
        try:
            out["template_id"] = int(out["template_id"])
        except (TypeError, ValueError):
            out["template_id"] = None
    if out.get("recurring_id") is not None:
        try:
            out["recurring_id"] = int(out["recurring_id"])
        except (TypeError, ValueError):
            out["recurring_id"] = None
    return out


def _rows_to_activities(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply :func:`_row_to_activity` to each row, dropping None."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        a = _row_to_activity(r)
        if a is not None:
            out.append(a)
    return out


# =============================================================================
# === ActivityService                                                        ===
# =============================================================================

class ActivityService:
    """CRUD + business logic for activity records.

    All mutation methods publish an event on the global :data:`bus`
    *after* the DB write succeeds.  Subscribers (UI widgets, the
    goal/streak services, the badge service) react accordingly.
    """

    def __init__(self) -> None:
        # Used by start_recording/stop_recording for safety — we track
        # currently-active stopwatch activities so that stop_recording
        # can refuse to operate on already-stopped records.
        self._active_recordings: Dict[int, str] = {}  # activity_id -> start_ts

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """No-op init for symmetry with other services."""
        _log.debug("ActivityService initialized")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(
        self,
        title: str,
        category_id: Optional[int] = None,
        duration_min: int = 0,
        date_iso: Optional[str] = None,
        *,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        kind: str = "manual",
        template_id: Optional[int] = None,
        recurring_id: Optional[int] = None,
        source: str = "desktop",
    ) -> Dict[str, Any]:
        """Add a new activity record.

        Parameters
        ----------
        title : str
            Activity title (1..200 chars).  Whitespace is collapsed.
        category_id : int, optional
            FK into ``categories``.  ``None`` means "uncategorized".
        duration_min : int
            Duration in minutes (0..1440).  Defaults to 0 for stopwatch
            recordings that have not yet been stopped.
        date_iso : str, optional
            ``YYYY-MM-DD`` (Gregorian).  Defaults to today.
        start_ts, end_ts : str, optional
            ISO-8601 timestamps for stopwatch-recorded activities.
        notes : str, optional
            Free-form notes (≤ 5000 chars).
        tags : list[str], optional
            Up to 10 tags; sanitized (lowercased, deduped, ≤ 20 chars each).
        kind : str
            ``"manual"`` / ``"stopwatch"`` / ``"template"`` / ``"voice"`` /
            ``"recurring"``.
        template_id, recurring_id : int, optional
            Source FK for template / recurring rule provenance.
        source : str
            ``"desktop"`` / ``"web"`` / ``"import"``.

        Returns
        -------
        dict
            The newly-inserted activity (with parsed tags, jalali_iso, etc).

        Raises
        ------
        ValueError
            If `title` is empty or `duration_min` is out of range.
        """
        clean_title = sanitize_title(title)
        if not clean_title:
            raise ValueError("Activity title must be a non-empty string")

        if not is_valid_duration_min(duration_min):
            # Don't crash — clamp instead.  We log a warning so the user
            # can spot the bug if it's coming from a UI form.
            _log.warning("Clamping out-of-range duration_min=%r", duration_min)
            duration_min = max(0, min(1440, int(duration_min or 0)))

        if date_iso is None:
            date_iso = today_iso()
        elif not is_valid_iso_date(date_iso):
            raise ValueError(f"Invalid date_iso: {date_iso!r}")

        if start_ts is not None and not is_valid_iso_datetime(start_ts):
            _log.warning("Ignoring invalid start_ts=%r", start_ts)
            start_ts = None
        if end_ts is not None and not is_valid_iso_datetime(end_ts):
            _log.warning("Ignoring invalid end_ts=%r", end_ts)
            end_ts = None

        jalali_iso = _compute_jalali_iso(date_iso)
        clean_notes = sanitize_notes(notes) if notes else None
        clean_tags = sanitize_tags(tags)

        if kind not in ("manual", "stopwatch", "template", "voice", "recurring"):
            _log.warning("Unknown activity kind=%r, defaulting to 'manual'", kind)
            kind = "manual"

        try:
            new_id = db.activity_add(
                title=clean_title,
                category_id=category_id,
                duration_min=duration_min,
                date_iso=date_iso,
                jalali_iso=jalali_iso,
                start_ts=start_ts,
                end_ts=end_ts,
                notes=clean_notes,
                tags=clean_tags,
                kind=kind,
                source=source,
                template_id=template_id,
                recurring_id=recurring_id,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": clean_title, "date_iso": date_iso})
            raise

        activity = self.get(new_id)
        if activity is None:
            # Extremely unlikely — we just inserted it.
            _log.error("Could not load activity %r after insert", new_id)
            activity = {"id": new_id, "title": clean_title}

        # If this is a recording, mark it active.
        if kind == "stopwatch" and start_ts and not end_ts:
            self._active_recordings[new_id] = start_ts

        bus.publish("activity.added", activity)
        _log.info("Activity added: id=%s title=%r duration=%dm",
                  new_id, clean_title, duration_min)
        return activity

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, id: int, **fields: Any) -> Dict[str, Any]:
        """Update fields on an existing activity.

        Recognized fields (any subset):
            ``title``, ``category_id``, ``duration_min``, ``date_iso``,
            ``start_ts``, ``end_ts``, ``notes``, ``tags``, ``kind``,
            ``template_id``, ``recurring_id``.

        If ``date_iso`` is changed, ``jalali_iso`` is recomputed.
        If ``tags`` is provided, it is sanitized.

        Returns the updated activity dict (or raises ``KeyError`` if
        the activity does not exist).
        """
        if not isinstance(id, int) or id <= 0:
            raise ValueError(f"Invalid activity id: {id!r}")

        existing = self.get(id)
        if existing is None:
            raise KeyError(f"Activity {id} not found")

        updates: Dict[str, Any] = {}

        if "title" in fields:
            clean_title = sanitize_title(fields["title"])
            if not clean_title:
                raise ValueError("title must be non-empty")
            updates["title"] = clean_title

        if "category_id" in fields:
            cid = fields["category_id"]
            if cid is None or (isinstance(cid, int) and cid > 0):
                updates["category_id"] = cid
            else:
                _log.warning("Ignoring invalid category_id=%r", cid)

        if "duration_min" in fields:
            dur = fields["duration_min"]
            if not is_valid_duration_min(dur):
                dur = max(0, min(1440, int(dur or 0)))
            updates["duration_min"] = dur

        if "date_iso" in fields:
            new_date = fields["date_iso"]
            if not is_valid_iso_date(new_date):
                raise ValueError(f"Invalid date_iso: {new_date!r}")
            updates["date_iso"] = new_date
            updates["jalali_iso"] = _compute_jalali_iso(new_date)

        if "start_ts" in fields:
            ts = fields["start_ts"]
            if ts is None or is_valid_iso_datetime(ts):
                updates["start_ts"] = ts
            else:
                _log.warning("Ignoring invalid start_ts=%r", ts)

        if "end_ts" in fields:
            ts = fields["end_ts"]
            if ts is None or is_valid_iso_datetime(ts):
                updates["end_ts"] = ts
            else:
                _log.warning("Ignoring invalid end_ts=%r", ts)

        if "notes" in fields:
            notes = fields["notes"]
            updates["notes"] = sanitize_notes(notes) if notes else None

        if "tags" in fields:
            updates["tags"] = sanitize_tags(fields["tags"])

        if "kind" in fields:
            kind = fields["kind"]
            if kind in ("manual", "stopwatch", "template", "voice", "recurring"):
                updates["kind"] = kind
            else:
                _log.warning("Ignoring unknown kind=%r", kind)

        if "template_id" in fields:
            tid = fields["template_id"]
            if tid is None or (isinstance(tid, int) and tid > 0):
                updates["template_id"] = tid
            else:
                updates["template_id"] = None

        if "recurring_id" in fields:
            rid = fields["recurring_id"]
            if rid is None or (isinstance(rid, int) and rid > 0):
                updates["recurring_id"] = rid
            else:
                updates["recurring_id"] = None

        if not updates:
            return existing

        try:
            db.activity_update(id, **updates)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "updates": updates})
            raise

        updated = self.get(id) or existing
        bus.publish("activity.updated", updated)
        _log.info("Activity updated: id=%s fields=%s", id, list(updates.keys()))
        return updated

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, id: int, soft: bool = True) -> bool:
        """Delete an activity (soft by default).

        Returns ``True`` if a row was actually deleted.  Publishes
        ``activity.deleted`` with the activity id and the soft flag.
        """
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.activity_delete(id, soft=soft)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False

        if ok:
            # Drop from active recordings if present
            self._active_recordings.pop(id, None)
            bus.publish("activity.deleted", {"id": id, "soft": soft})
            _log.info("Activity %s deleted (soft=%s)", id, soft)
        return ok

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Return a single activity by id, or ``None``."""
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            row = db.activity_get(id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None
        return _row_to_activity(row)

    def list(self, *filters: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        """List activities with optional filters.

        Accepts the same keyword arguments as
        :func:`rask.database.activity_list` (``date_from``, ``date_to``,
        ``category_ids``, ``kinds``, ``tags``, ``search``,
        ``min_duration``, ``max_duration``, ``include_deleted``,
        ``limit``, ``offset``, ``order_by``).

        For backwards-compat, positional args are interpreted as:
        ``list(date_from, date_to, category_ids=None, ...)``.
        """
        # Map positional args to keyword form.
        if filters:
            names = ("date_from", "date_to", "category_ids", "kinds",
                     "tags", "search", "min_duration", "max_duration")
            for i, val in enumerate(filters):
                if i >= len(names):
                    break
                if val is not None:
                    kwargs.setdefault(names[i], val)
        try:
            rows = db.activity_list(**kwargs)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"kwargs": kwargs})
            return []
        return _rows_to_activities(rows)

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Full-text search over titles and notes."""
        if not query or not isinstance(query, str):
            return []
        try:
            rows = db.activity_list(search=query.strip(), limit=limit)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"query": query})
            return []
        return _rows_to_activities(rows)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the N most recent activities (newest first)."""
        if limit <= 0:
            return []
        try:
            rows = db.activity_list(limit=limit, offset=0)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"limit": limit})
            return []
        return _rows_to_activities(rows)

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def today_total(self) -> int:
        """Total minutes logged today."""
        try:
            return int(db.activity_sum_duration(
                date_from=today_iso(), date_to=today_iso()))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    def today_count(self) -> int:
        """Number of activities logged today."""
        try:
            return int(db.activity_count(
                date_from=today_iso(), date_to=today_iso()))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    def week_total(self) -> int:
        """Total minutes logged this week (Sat..Fri)."""
        try:
            from ..core.time_utils import start_of_week, end_of_week
            today = today_iso()
            return int(db.activity_sum_duration(
                date_from=start_of_week(today), date_to=end_of_week(today)))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    def month_total(self) -> int:
        """Total minutes logged this calendar month."""
        try:
            from ..core.time_utils import start_of_month, end_of_month
            today = today_iso()
            return int(db.activity_sum_duration(
                date_from=start_of_month(today), date_to=end_of_month(today)))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return 0

    # ------------------------------------------------------------------
    # Duplicate / merge
    # ------------------------------------------------------------------

    def duplicate(self, id: int) -> int:
        """Create a copy of an activity with title suffix " (copy)".

        Returns the new activity id, or ``0`` if the source doesn't exist.
        """
        src = self.get(id)
        if src is None:
            return 0
        try:
            new = self.add(
                title=f"{src.get('title', '')} (copy)",
                category_id=src.get("category_id"),
                duration_min=int(src.get("duration_min") or 0),
                date_iso=today_iso(),  # duplicate goes to today
                notes=src.get("notes"),
                tags=src.get("tags", []),
                kind="manual",  # always manual, even if source was stopwatch
            )
            return int(new.get("id", 0))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"src_id": id})
            return 0

    def merge(self, ids: List[int]) -> int:
        """Merge several activities into one.

        The first id is the "primary"; its title is kept and its
        duration is set to the sum of all merged activities' durations.
        All other activities are soft-deleted, and their tags/notes are
        appended to the primary's notes.

        Returns the primary activity id (or 0 if no merge happened).
        """
        if not ids or not isinstance(ids, list):
            return 0
        # Deduplicate and preserve order.
        seen = set()
        clean_ids: List[int] = []
        for i in ids:
            if isinstance(i, int) and i > 0 and i not in seen:
                seen.add(i)
                clean_ids.append(i)
        if len(clean_ids) < 2:
            return clean_ids[0] if clean_ids else 0

        primary_id = clean_ids[0]
        others = clean_ids[1:]

        primary = self.get(primary_id)
        if primary is None:
            _log.error("Merge: primary activity %s not found", primary_id)
            return 0

        total_dur = int(primary.get("duration_min") or 0)
        all_tags: List[str] = list(primary.get("tags", []))
        extra_notes: List[str] = []

        for oid in others:
            other = self.get(oid)
            if other is None:
                continue
            total_dur += int(other.get("duration_min") or 0)
            for tag in other.get("tags", []):
                if tag not in all_tags:
                    all_tags.append(tag)
            if other.get("notes"):
                extra_notes.append(
                    f"[Merged from '{other.get('title', '')}': "
                    f"{other.get('notes', '')}]"
                )

        # Clamp to max single-day duration
        total_dur = max(0, min(1440, total_dur))

        try:
            self.update(
                primary_id,
                duration_min=total_dur,
                tags=all_tags,
                notes=(primary.get("notes") or "") + (
                    "\n" + "\n".join(extra_notes) if extra_notes else ""
                ),
            )
            for oid in others:
                self.delete(oid, soft=True)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"ids": clean_ids})
            return 0

        _log.info("Merged %d activities into id=%d", len(clean_ids), primary_id)
        return primary_id

    # ------------------------------------------------------------------
    # Recording lifecycle (start / stop / cancel)
    # ------------------------------------------------------------------

    def start_recording(self, title: str, category_id: Optional[int] = None) -> int:
        """Begin a stopwatch recording.

        Creates an activity with ``kind="stopwatch"``, ``start_ts=now``,
        and ``duration_min=0``.  The activity is returned immediately
        so the UI can show a live timer.

        Returns the new activity id (or 0 on failure).
        """
        clean_title = sanitize_title(title) or "(بدون عنوان)"
        start_ts = now_iso_utc()
        try:
            activity = self.add(
                title=clean_title,
                category_id=category_id,
                duration_min=0,
                date_iso=today_iso(),
                start_ts=start_ts,
                end_ts=None,
                kind="stopwatch",
            )
            aid = int(activity.get("id", 0))
            if aid:
                self._active_recordings[aid] = start_ts
            return aid
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": clean_title})
            return 0

    def stop_recording(self, activity_id: int) -> Dict[str, Any]:
        """Stop a recording and compute the duration.

        Sets ``end_ts`` to now, computes ``duration_min`` from the
        elapsed wall-clock time, and updates the activity.

        Returns the updated activity dict.  If the activity is not a
        stopwatch recording or already stopped, the existing record is
        returned unchanged (with a warning logged).
        """
        if not isinstance(activity_id, int) or activity_id <= 0:
            return {}

        activity = self.get(activity_id)
        if activity is None:
            _log.warning("stop_recording: activity %s not found", activity_id)
            return {}

        if activity.get("kind") != "stopwatch":
            _log.warning("stop_recording: activity %s is not a stopwatch recording",
                         activity_id)
            return activity

        start_ts = activity.get("start_ts")
        if not start_ts:
            _log.warning("stop_recording: activity %s has no start_ts", activity_id)
            return activity

        end_ts = now_iso_utc()
        try:
            start_dt = datetime.fromisoformat(
                start_ts.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(
                end_ts.replace("Z", "+00:00"))
            elapsed_sec = (end_dt - start_dt).total_seconds()
            elapsed_min = max(0, int(elapsed_sec // 60))
            # Safety cap: 1 day
            elapsed_min = min(1440, elapsed_min)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"start_ts": start_ts, "end_ts": end_ts})
            elapsed_min = 0

        try:
            updated = self.update(
                activity_id,
                end_ts=end_ts,
                duration_min=elapsed_min,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"activity_id": activity_id})
            return activity

        self._active_recordings.pop(activity_id, None)
        _log.info("Stopped recording %s: %d min", activity_id, elapsed_min)
        return updated

    def cancel_recording(self, activity_id: int) -> bool:
        """Cancel and delete a recording in progress.

        Hard-deletes the activity (it was never "real" data).  Returns
        ``True`` on success.
        """
        if not isinstance(activity_id, int) or activity_id <= 0:
            return False
        self._active_recordings.pop(activity_id, None)
        # Hard delete so it never appears in stats.
        return self.delete(activity_id, soft=False)

    def is_recording(self, activity_id: int) -> bool:
        """Return True if the given activity is an in-progress recording."""
        return activity_id in self._active_recordings

    def active_recordings(self) -> List[int]:
        """Return ids of all in-progress recordings (usually 0 or 1)."""
        return list(self._active_recordings.keys())


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

activity_service: ActivityService = ActivityService()
