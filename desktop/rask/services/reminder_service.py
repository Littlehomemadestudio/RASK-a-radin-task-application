"""
rask.services.reminder_service
==============================

Scheduled reminders.

A reminder is a (title, time, days-of-week) tuple that fires a
notification when its clock time is reached on a matching day.  The
service runs a periodic scheduler (driven by Tk's ``after()`` loop)
that checks for due reminders every
:data:`config.REMINDER_CHECK_INTERVAL_SEC` seconds.

Day mask conventions (Persian week, Saturday-first):
    bit 0 = Saturday    (mask 1)
    bit 1 = Sunday      (mask 2)
    bit 2 = Monday      (mask 4)
    bit 3 = Tuesday     (mask 8)
    bit 4 = Wednesday   (mask 16)
    bit 5 = Thursday    (mask 32)
    bit 6 = Friday      (mask 64)

A mask of ``127`` (all bits) means "every day"; ``65`` = Sat + Fri
(weekend in Iran).

Reminders are *not* re-fired within the same minute —
``last_fired_iso`` is updated on every fire and ``check_due()``
skips reminders that fired in the last 60 seconds.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_local, today_iso
from ..core.validators import is_valid_hhmm, sanitize_title

__all__ = ["ReminderService", "reminder_service"]

_log = get_logger("services.reminder")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

# Python weekday: Mon=0..Sun=6.
# Persian weekday (Sat-first): Sat=0, Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6.
_PY_TO_PERSIAN = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}


def _persian_weekday_today() -> int:
    """Return today's Persian weekday index (Sat=0..Fri=6)."""
    return _PY_TO_PERSIAN[date.today().weekday()]


def _day_matches_mask(persian_wd: int, mask: int) -> bool:
    """Return True if bit `persian_wd` is set in `mask`."""
    if persian_wd < 0 or persian_wd > 6:
        return False
    return bool(mask & (1 << persian_wd))


def _row_to_reminder(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB reminder row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    for k in ("id", "category_id", "goal_id", "days_mask"):
        if out.get(k) is not None:
            try:
                out[k] = int(out[k])
            except (TypeError, ValueError):
                pass
    for k in ("enabled", "sound"):
        if k in out:
            out[k] = bool(out[k])
    return out


def _rows_to_reminders(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rem = _row_to_reminder(r)
        if rem is not None:
            out.append(rem)
    return out


def _now_iso_local_full() -> str:
    """Return current local time as ``YYYY-MM-DDTHH:MM:SS``."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _parse_iso_local(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO local timestamp (no tz) into a datetime, or ``None``."""
    if not s or not isinstance(s, str):
        return None
    try:
        # Strip fractional seconds / timezone if present.
        s = s.split("+", 1)[0].rstrip("Z")
        if "." in s:
            s = s.split(".", 1)[0]
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# =============================================================================
# === ReminderService                                                        ===
# =============================================================================

class ReminderService:
    """CRUD + scheduler for reminders."""

    def __init__(self) -> None:
        # Tk root widget, set by set_root().  When None, the scheduler
        # is not running.
        self._root: Any = None
        self._scheduler_handle: Optional[str] = None
        self._last_check_minute: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """No-op init for symmetry.  Call ``set_root()`` to start scheduling."""
        _log.debug("ReminderService initialized")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(
        self,
        title: str,
        time_hhmm: str,
        message: Optional[str] = None,
        days_mask: int = 127,
        category_id: Optional[int] = None,
        goal_id: Optional[int] = None,
        enabled: bool = True,
        sound: bool = True,
    ) -> Dict[str, Any]:
        """Create a new reminder.

        Parameters
        ----------
        title : str
            Reminder title (1..200 chars).
        time_hhmm : str
            ``HH:MM`` (24-hour, e.g. ``"09:30"``).
        message : str, optional
            Longer body text.
        days_mask : int
            Bitmask of Persian weekdays (Sat=1..Fri=64).
        category_id, goal_id : int, optional
            Optional associations for UI hint / quick action.
        enabled : bool
            Whether the reminder is active.
        sound : bool
            Whether to play a sound on fire.

        Returns the newly-created reminder dict.
        """
        clean_title = sanitize_title(title)
        if not clean_title:
            raise ValueError("Reminder title must be non-empty")
        if not is_valid_hhmm(time_hhmm):
            raise ValueError(f"Invalid time_hhmm: {time_hhmm!r}")
        if not isinstance(days_mask, int) or days_mask < 0 or days_mask > 127:
            raise ValueError(f"Invalid days_mask: {days_mask!r}")

        try:
            new_id = db.reminder_add(
                title=clean_title,
                time_hhmm=time_hhmm,
                message=message,
                days_mask=days_mask,
                category_id=category_id,
                goal_id=goal_id,
                enabled=enabled,
                sound=sound,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": clean_title})
            raise

        reminder = self.get(new_id)
        if reminder is None:
            reminder = {"id": new_id, "title": clean_title,
                        "time_hhmm": time_hhmm}
        bus.publish("reminder.added", reminder)
        _log.info("Reminder added: id=%s title=%r time=%s",
                  new_id, clean_title, time_hhmm)
        return reminder

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def update(self, id: int, **fields: Any) -> Dict[str, Any]:
        """Update reminder fields.  Returns the updated reminder dict."""
        if not isinstance(id, int) or id <= 0:
            raise ValueError(f"Invalid reminder id: {id!r}")
        existing = self.get(id)
        if existing is None:
            raise KeyError(f"Reminder {id} not found")

        updates: Dict[str, Any] = {}
        if "title" in fields:
            t = sanitize_title(fields["title"])
            if not t:
                raise ValueError("title must be non-empty")
            updates["title"] = t
        if "message" in fields:
            updates["message"] = fields["message"]
        if "time_hhmm" in fields:
            if is_valid_hhmm(fields["time_hhmm"]):
                updates["time_hhmm"] = fields["time_hhmm"]
        if "days_mask" in fields:
            m = fields["days_mask"]
            if isinstance(m, int) and 0 <= m <= 127:
                updates["days_mask"] = m
        if "category_id" in fields:
            cid = fields["category_id"]
            if cid is None or (isinstance(cid, int) and cid > 0):
                updates["category_id"] = cid
        if "goal_id" in fields:
            gid = fields["goal_id"]
            if gid is None or (isinstance(gid, int) and gid > 0):
                updates["goal_id"] = gid
        if "enabled" in fields:
            updates["enabled"] = bool(fields["enabled"])
        if "sound" in fields:
            updates["sound"] = bool(fields["sound"])

        if not updates:
            return existing

        try:
            db.reminder_update(id, **updates)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "updates": updates})
            raise

        updated = self.get(id) or existing
        bus.publish("reminder.updated", updated)
        return updated

    def delete(self, id: int) -> bool:
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.reminder_delete(id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("reminder.deleted", {"id": id})
            _log.info("Reminder deleted: id=%s", id)
        return ok

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            return _row_to_reminder(db.reminder_get(id))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list(self, only_enabled: bool = False) -> List[Dict[str, Any]]:
        try:
            return _rows_to_reminders(
                db.reminder_list(only_enabled=only_enabled))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    # ------------------------------------------------------------------
    # Snooze / dismiss
    # ------------------------------------------------------------------

    def snooze(self, id: int, minutes: int = 10) -> bool:
        """Snooze a reminder for `minutes` minutes.

        Sets ``snooze_until`` to (now + minutes) ISO timestamp.  The
        scheduler will not fire this reminder until ``snooze_until``
        has passed.
        """
        if not isinstance(id, int) or id <= 0:
            return False
        if minutes <= 0:
            minutes = config.REMINDER_DEFAULT_SNOOZE_MIN
        snooze_dt = datetime.now() + timedelta(minutes=minutes)
        snooze_iso = snooze_dt.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            ok = db.reminder_update(id, snooze_until=snooze_iso)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("reminder.snoozed", {
                "id": id, "snooze_until": snooze_iso, "minutes": minutes,
            })
            _log.info("Reminder %s snoozed for %d min", id, minutes)
        return ok

    def dismiss(self, id: int) -> bool:
        """Dismiss a reminder (clears snooze and marks as fired)."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.reminder_update(
                id,
                last_fired_iso=_now_iso_local_full(),
                snooze_until=None,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            bus.publish("reminder.dismissed", {"id": id})
            _log.info("Reminder %s dismissed", id)
        return ok

    # ------------------------------------------------------------------
    # Due checks
    # ------------------------------------------------------------------

    def check_due(self) -> List[Dict[str, Any]]:
        """Return reminders that should fire *now*.

        A reminder fires when ALL of the following hold:
          - ``enabled = True``
          - today's Persian weekday is in ``days_mask``
          - current local time is at-or-after ``time_hhmm``
          - ``snooze_until`` is in the past (or NULL)
          - the reminder has NOT already fired in the same minute

        Does NOT update ``last_fired_iso`` — call :meth:`_fire` for that.
        """
        now = datetime.now()
        now_hhmm = now.strftime("%H:%M")
        today_persian_wd = _persian_weekday_today()
        out: List[Dict[str, Any]] = []

        try:
            reminders = self.list(only_enabled=True)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

        for rem in reminders:
            time_hhmm = rem.get("time_hhmm")
            if not time_hhmm:
                continue
            # Day-of-week check
            mask = int(rem.get("days_mask", 127))
            if not _day_matches_mask(today_persian_wd, mask):
                continue
            # Time check
            if time_hhmm > now_hhmm:
                continue  # not yet
            # Snooze check
            snooze = _parse_iso_local(rem.get("snooze_until"))
            if snooze is not None and snooze > now:
                continue
            # Already-fired-this-minute check
            last_fired = _parse_iso_local(rem.get("last_fired_iso"))
            if last_fired is not None:
                # If fired within the last 60 seconds, skip.
                delta = (now - last_fired).total_seconds()
                if delta < 60:
                    continue
            out.append(rem)
        return out

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def set_root(self, root_widget: Any) -> None:
        """Set the Tk root widget used for ``after()`` scheduling.

        Call this once after the app's main window is created.
        Immediately starts the periodic check loop.
        """
        self._root = root_widget
        if root_widget is not None:
            self._start_loop()

    def start_scheduler(self, root_widget: Any) -> None:
        """Alias for :meth:`set_root` (kept for API parity with spec)."""
        self.set_root(root_widget)

    def stop_scheduler(self) -> None:
        """Stop the periodic check loop."""
        if self._scheduler_handle is not None and self._root is not None:
            try:
                self._root.after_cancel(self._scheduler_handle)
            except Exception:  # noqa: BLE001
                pass
            self._scheduler_handle = None
        _log.debug("Reminder scheduler stopped")

    def _start_loop(self) -> None:
        """Schedule the next ``_tick`` call."""
        if self._root is None:
            return
        interval_ms = config.REMINDER_CHECK_INTERVAL_SEC * 1000
        try:
            self._scheduler_handle = self._root.after(
                interval_ms, self._tick)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _tick(self) -> None:
        """One scheduler tick: check for due reminders and fire them."""
        try:
            due = self.check_due()
            for rem in due:
                self._fire(rem)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        # Re-arm.
        self._start_loop()

    def _fire(self, reminder: Dict[str, Any]) -> bool:
        """Fire a reminder: update last_fired_iso and publish event.

        Returns ``True`` on success.  The actual UI notification is
        handled by subscribers to the ``reminder.triggered`` event
        (typically a toast widget).
        """
        rid = reminder.get("id")
        if not rid:
            return False
        now_iso = _now_iso_local_full()
        try:
            db.reminder_update(rid, last_fired_iso=now_iso,
                                snooze_until=None)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": rid})
            return False

        bus.publish("reminder.triggered", {
            "id": rid,
            "title": reminder.get("title"),
            "message": reminder.get("message"),
            "time_hhmm": reminder.get("time_hhmm"),
            "category_id": reminder.get("category_id"),
            "goal_id": reminder.get("goal_id"),
            "sound": reminder.get("sound", True),
            "fired_at": now_iso,
        })
        _log.info("Reminder fired: id=%s title=%r",
                  rid, reminder.get("title"))
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def next_due(self) -> Optional[Dict[str, Any]]:
        """Return the next reminder that will fire (today or later).

        Useful for the home screen's "next reminder" widget.  Returns
        ``None`` if no reminders are scheduled.
        """
        now = datetime.now()
        now_hhmm = now.strftime("%H:%M")
        today_persian_wd = _persian_weekday_today()
        candidates: List[Dict[str, Any]] = []
        for rem in self.list(only_enabled=True):
            time_hhmm = rem.get("time_hhmm")
            if not time_hhmm:
                continue
            mask = int(rem.get("days_mask", 127))
            # Today + future time?
            if _day_matches_mask(today_persian_wd, mask) and time_hhmm > now_hhmm:
                candidates.append({**rem, "_when": f"today {time_hhmm}",
                                   "_when_sort": time_hhmm})
                continue
            # Search next 7 days for the next matching day.
            for offset in range(1, 8):
                future = date.today() + timedelta(days=offset)
                future_persian_wd = _PY_TO_PERSIAN[future.weekday()]
                if _day_matches_mask(future_persian_wd, mask):
                    candidates.append({
                        **rem,
                        "_when": f"{future.isoformat()} {time_hhmm}",
                        "_when_sort": f"{future.isoformat()}T{time_hhmm}",
                    })
                    break
        if not candidates:
            return None
        candidates.sort(key=lambda r: r["_when_sort"])
        out = dict(candidates[0])
        out.pop("_when_sort", None)
        out["next_when"] = out.pop("_when", None)
        return out


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

reminder_service: ReminderService = ReminderService()
