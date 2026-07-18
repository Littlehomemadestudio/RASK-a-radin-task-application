"""
rask.services.recurring_service
===============================

Recurring activity rules.

A recurring rule generates activities automatically:
  - ``daily``    — one activity per day
  - ``weekly``   — one activity per matching weekday (via ``days_mask``)
  - ``monthly``  — one activity per month (on the day-of-month of creation)

The :meth:`process_due` method is called periodically by the scheduler
(typically once per minute).  It finds rules whose ``next_run_iso`` is
in the past, creates an activity for each, and updates
``last_run_iso`` / ``next_run_iso``.

Pause/resume support lets the user temporarily suspend a rule without
losing its configuration.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_local, today_iso
from ..core.validators import (
    is_valid_duration_min,
    is_valid_hhmm,
    is_valid_iso_date,
    sanitize_notes,
    sanitize_title,
)

__all__ = ["RecurringService", "recurring_service"]

_log = get_logger("services.recurring")


VALID_FREQUENCIES = ("daily", "weekly", "monthly")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _row_to_rule(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB recurring row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    for k in ("id", "category_id", "duration_min", "days_mask"):
        if out.get(k) is not None:
            try:
                out[k] = int(out[k])
            except (TypeError, ValueError):
                pass
    if "active" in out:
        out["active"] = bool(out["active"])
    return out


def _rows_to_rules(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rule = _row_to_rule(r)
        if rule is not None:
            out.append(rule)
    return out


# =============================================================================
# === RecurringService                                                       ===
# =============================================================================

class RecurringService:
    """CRUD + scheduler for recurring activity rules."""

    def __init__(self) -> None:
        # Tracks ids of rules processed in the current minute to avoid
        # double-creation if process_due() is called twice quickly.
        self._processed_this_minute: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """No-op init for symmetry.  Call :meth:`process_due` periodically."""
        _log.debug("RecurringService initialized")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(
        self,
        title: str,
        duration_min: int,
        frequency: str,
        category_id: Optional[int] = None,
        days_mask: int = 127,
        time_hhmm: Optional[str] = None,
        end_date_iso: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new recurring rule.

        Parameters
        ----------
        title : str
            Title for generated activities (1..200 chars).
        duration_min : int
            Duration in minutes (0..1440).
        frequency : str
            ``"daily"`` / ``"weekly"`` / ``"monthly"``.
        category_id : int, optional
            FK into ``categories``.
        days_mask : int
            For weekly rules, bitmask of Persian weekdays (Sat=1..Fri=64).
            Ignored for daily / monthly rules.
        time_hhmm : str, optional
            Time of day the activity should be logged (``HH:MM``).
            If omitted, the current time is used at creation.
        end_date_iso : str, optional
            Stop recurring after this date.
        notes : str, optional
            Notes to attach to generated activities.

        Returns the newly-created rule dict.
        """
        clean_title = sanitize_title(title)
        if not clean_title:
            raise ValueError("Title must be non-empty")
        if frequency not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {VALID_FREQUENCIES}")
        if not is_valid_duration_min(duration_min):
            raise ValueError(f"duration_min out of range: {duration_min}")
        if time_hhmm is not None and not is_valid_hhmm(time_hhmm):
            raise ValueError(f"Invalid time_hhmm: {time_hhmm!r}")
        if end_date_iso is not None and not is_valid_iso_date(end_date_iso):
            raise ValueError(f"Invalid end_date_iso: {end_date_iso!r}")
        if not isinstance(days_mask, int) or days_mask < 0 or days_mask > 127:
            raise ValueError(f"Invalid days_mask: {days_mask!r}")

        clean_notes = sanitize_notes(notes) if notes else None

        # Compute the first next_run_iso.
        first_run = self._compute_first_run(frequency, days_mask, time_hhmm)

        try:
            new_id = db.recurring_add(
                title=clean_title,
                duration_min=duration_min,
                frequency=frequency,
                category_id=category_id,
                days_mask=days_mask,
                time_hhmm=time_hhmm,
                end_date_iso=end_date_iso,
                next_run_iso=first_run,
                notes=clean_notes,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": clean_title})
            raise

        rule = self.get(new_id)
        if rule is None:
            rule = {"id": new_id, "title": clean_title,
                    "frequency": frequency}
        bus.publish("recurring.added", rule)
        _log.info("Recurring rule added: id=%s title=%r freq=%s",
                  new_id, clean_title, frequency)
        return rule

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def update(self, id: int, **fields: Any) -> Dict[str, Any]:
        """Update rule fields.  Returns the updated rule dict."""
        if not isinstance(id, int) or id <= 0:
            raise ValueError(f"Invalid rule id: {id!r}")
        existing = self.get(id)
        if existing is None:
            raise KeyError(f"Recurring rule {id} not found")

        updates: Dict[str, Any] = {}
        if "title" in fields:
            t = sanitize_title(fields["title"])
            if not t:
                raise ValueError("title must be non-empty")
            updates["title"] = t
        if "category_id" in fields:
            cid = fields["category_id"]
            if cid is None or (isinstance(cid, int) and cid > 0):
                updates["category_id"] = cid
        if "duration_min" in fields:
            d = fields["duration_min"]
            if is_valid_duration_min(d):
                updates["duration_min"] = int(d)
        if "frequency" in fields:
            if fields["frequency"] in VALID_FREQUENCIES:
                updates["frequency"] = fields["frequency"]
                # Recompute next run on frequency change.
                updates["next_run_iso"] = self._compute_first_run(
                    fields["frequency"],
                    int(existing.get("days_mask", 127)),
                    existing.get("time_hhmm"),
                )
        if "days_mask" in fields:
            m = fields["days_mask"]
            if isinstance(m, int) and 0 <= m <= 127:
                updates["days_mask"] = m
        if "time_hhmm" in fields:
            t = fields["time_hhmm"]
            if t is None or is_valid_hhmm(t):
                updates["time_hhmm"] = t
        if "end_date_iso" in fields:
            e = fields["end_date_iso"]
            if e is None or is_valid_iso_date(e):
                updates["end_date_iso"] = e
        if "notes" in fields:
            updates["notes"] = sanitize_notes(fields["notes"]) \
                if fields["notes"] else None
        if "active" in fields:
            updates["active"] = bool(fields["active"])

        if not updates:
            return existing

        try:
            db.recurring_update(id, **updates)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "updates": updates})
            raise

        updated = self.get(id) or existing
        bus.publish("recurring.updated", updated)
        return updated

    def delete(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.recurring_delete(id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("recurring.deleted", {"id": id})
            _log.info("Recurring rule deleted: id=%s", id)
        return ok

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            # No db.recurring_get helper — use list + filter.
            for r in db.recurring_list():
                if r.get("id") == id:
                    return _row_to_rule(r)
            return None
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list(self, only_active: bool = False) -> List[Dict[str, Any]]:
        try:
            return _rows_to_rules(
                db.recurring_list(only_active=only_active))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    # ------------------------------------------------------------------
    # Pause / resume
    # ------------------------------------------------------------------

    def pause(self, id: int) -> bool:
        """Pause a rule (set ``active = False``)."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.recurring_update(id, active=0)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("recurring.paused", {"id": id})
        return ok

    def resume(self, id: int) -> bool:
        """Resume a paused rule (set ``active = True``).

        Also re-computes ``next_run_iso`` in case it's stale.
        """
        if not isinstance(id, int) or id <= 0:
            return False
        rule = self.get(id)
        if rule is None:
            return False
        next_run = self._compute_first_run(
            rule.get("frequency", "daily"),
            int(rule.get("days_mask", 127)),
            rule.get("time_hhmm"),
        )
        try:
            ok = db.recurring_update(id, active=1, next_run_iso=next_run)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("recurring.resumed", {"id": id, "next_run_iso": next_run})
        return ok

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def process_due(self) -> List[Dict[str, Any]]:
        """Process all due recurring rules.

        For each due rule:
          1. Create an activity via :mod:`activity_service` with
             ``kind="recurring"``, ``recurring_id=rule.id``, today's date.
          2. Update ``last_run_iso`` and recompute ``next_run_iso``.

        Returns the list of created activity dicts (may be empty).

        Idempotent within a single minute — calling twice within 60
        seconds will not create duplicate activities for the same rule.
        """
        out: List[Dict[str, Any]] = []
        try:
            due_rules = db.recurring_due_now()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

        if not due_rules:
            return []

        # Lazy import to avoid circular dependency.
        from .activity_service import activity_service

        now_iso = now_iso_local()
        # Clear the processed-this-minute cache if the minute has changed.
        cache_minute = now_iso[:16]  # YYYY-MM-DDTHH:MM
        if cache_minute != self._cache_minute_key():
            self._processed_this_minute.clear()

        for rule_row in due_rules:
            rule = _row_to_rule(rule_row)
            if rule is None:
                continue
            rid = rule.get("id")
            if not rid:
                continue
            if rid in self._processed_this_minute:
                continue

            # Check end date
            end_date = rule.get("end_date_iso")
            if end_date and end_date < today_iso():
                # Past end date — auto-deactivate.
                try:
                    db.recurring_update(rid, active=0)
                except Exception as exc:  # noqa: BLE001
                    log_exception(_log, exc, {"id": rid})
                continue

            try:
                activity = activity_service.add(
                    title=rule.get("title", ""),
                    category_id=rule.get("category_id"),
                    duration_min=int(rule.get("duration_min", 0)),
                    date_iso=today_iso(),
                    notes=rule.get("notes"),
                    kind="recurring",
                    recurring_id=rid,
                )
                out.append(activity)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"rule_id": rid})
                continue

            # Compute next run.
            next_run = self.compute_next_run(rule)
            try:
                db.recurring_update(
                    rid,
                    last_run_iso=now_iso,
                    next_run_iso=next_run,
                )
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"rule_id": rid})

            self._processed_this_minute[rid] = cache_minute
            _log.info("Recurring rule %s fired -> activity %s",
                      rid, activity.get("id"))

        if out:
            bus.publish("recurring.processed", {
                "count": len(out),
                "rule_ids": [a.get("recurring_id") for a in out
                             if a.get("recurring_id")],
            })
        return out

    def _cache_minute_key(self) -> str:
        """Return the current minute as ``YYYY-MM-DDTHH:MM``."""
        return datetime.now().strftime("%Y-%m-%dT%H:%M")

    # ------------------------------------------------------------------
    # Next-run computation
    # ------------------------------------------------------------------

    def compute_next_run(self, rule: Dict[str, Any]) -> str:
        """Compute the next run ISO timestamp for `rule`.

        Mirrors :meth:`_compute_first_run` but starts from today + 1
        period (so the rule doesn't immediately re-fire).
        """
        freq = rule.get("frequency", "daily")
        days_mask = int(rule.get("days_mask", 127))
        time_hhmm = rule.get("time_hhmm")
        return self._compute_first_run(freq, days_mask, time_hhmm,
                                         start_from_tomorrow=True)

    def _compute_first_run(
        self,
        frequency: str,
        days_mask: int,
        time_hhmm: Optional[str],
        *,
        start_from_tomorrow: bool = False,
    ) -> str:
        """Compute the first/next run timestamp for a rule.

        For daily: today (or tomorrow) at `time_hhmm`.
        For weekly: the next matching weekday at `time_hhmm`.
        For monthly: today (or tomorrow) next month at `time_hhmm`.
        """
        now = datetime.now()
        target_time = now
        if time_hhmm:
            try:
                hh, mm = time_hhmm.split(":")
                target_time = now.replace(
                    hour=int(hh), minute=int(mm), second=0, microsecond=0)
            except (ValueError, TypeError):
                target_time = now
        # If start_from_tomorrow, advance one day before searching.
        if start_from_tomorrow:
            target_time = target_time + timedelta(days=1)
            # If we crossed a day boundary, normalize the time.
            if time_hhmm:
                try:
                    hh, mm = time_hhmm.split(":")
                    target_time = target_time.replace(
                        hour=int(hh), minute=int(mm), second=0,
                        microsecond=0)
                except (ValueError, TypeError):
                    pass

        # If the target time has already passed today and we're not
        # forcing tomorrow, push to the next matching period.
        if not start_from_tomorrow and target_time <= now:
            target_time = target_time + timedelta(days=1)

        if frequency == "daily":
            return target_time.strftime("%Y-%m-%dT%H:%M:%S")

        if frequency == "weekly":
            # Find the next matching Persian weekday.
            # Persian weekday: Sat=0..Fri=6.
            # Python weekday: Mon=0..Sun=6.
            py_to_persian = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}
            for offset in range(8):
                candidate = target_time + timedelta(days=offset)
                persian_wd = py_to_persian[candidate.weekday()]
                if days_mask & (1 << persian_wd):
                    return candidate.strftime("%Y-%m-%dT%H:%M:%S")
            # Fallback (shouldn't happen with mask > 0)
            return target_time.strftime("%Y-%m-%dT%H:%M:%S")

        if frequency == "monthly":
            # Same day-of-month next month.
            day = target_time.day
            if target_time.month == 12:
                next_month = target_time.replace(
                    year=target_time.year + 1, month=1, day=1)
            else:
                next_month = target_time.replace(
                    month=target_time.month + 1, day=1)
            # Clamp day to last day of next_month.
            if next_month.month == 12:
                last_day = 31
            else:
                last_day = (next_month.replace(
                    month=next_month.month + 1, day=1)
                    - timedelta(days=1)).day
            next_run = next_month.replace(day=min(day, last_day))
            return next_run.strftime("%Y-%m-%dT%H:%M:%S")

        # Fallback
        return target_time.strftime("%Y-%m-%dT%H:%M:%S")


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

recurring_service: RecurringService = RecurringService()
