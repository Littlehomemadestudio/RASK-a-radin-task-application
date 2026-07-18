"""
rask.features.pomodoro
======================

Pomodoro timer with automatic work/break cycling, activity logging,
and live UI widget.

A Pomodoro cycle consists of:

  1. ``work`` phase (default 25 min)
  2. ``break`` phase (default 5 min)
  3. Repeat ``cycles`` times (default 4)
  4. ``long_break`` phase (default 15 min) at the end of the cycle

When a work phase completes, the service:

  • Auto-creates an activity record (using the current title /
    category_id) via :mod:`rask.services.activity_service`
  • Publishes ``pomodoro.cycle_complete``
  • Starts the next break phase

When a break phase completes, the service:

  • Starts the next work phase, OR
  • Publishes ``pomodoro.finished`` if all cycles are exhausted

State is persisted to the ``kv`` store under the ``pomodoro.state`` key
so the timer survives app restarts.  The UI widget reads the persisted
state on construction and resumes the countdown.

Events published
----------------

  ``pomodoro.started``          — {cycle, phase, ends_at, title, category_id}
  ``pomodoro.phase_changed``    — {cycle, phase, ends_at, previous_phase}
  ``pomodoro.paused``           — {at_iso, remaining_sec}
  ``pomodoro.resumed``          — {at_iso, ends_at, remaining_sec}
  ``pomodoro.stopped``          — {at_iso, completed_cycles, partial_min}
  ``pomodoro.skipped``          — {skipped_phase, next_phase}
  ``pomodoro.cycle_complete``   — {cycle, activity_id, duration_min}
  ``pomodoro.finished``         — {completed_cycles, total_work_min,
                                   total_break_min, ended_at}
  ``pomodoro.tick``             — {remaining_sec, phase, cycle}
                                  (published every 1 s by the widget
                                   driver; the service itself does not
                                   poll — it computes remaining from
                                   ``ends_at`` on demand)

Schema
------

No new SQLite table is needed — Pomodoro state lives in the existing
``kv`` store as a JSON blob under the ``pomodoro.state`` key.  Each
completed work cycle is recorded as an activity row with
``kind="pomodoro"`` (a new value alongside ``manual`` / ``stopwatch``
/ etc.).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import add_days, now_iso_utc, today_iso

__all__ = [
    "PomodoroService",
    "pomodoro_service",
    "PomodoroState",
    "Phase",
]

_log = get_logger("features.pomodoro")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

#: Phases of the Pomodoro cycle.
PHASE_WORK: str = "work"
PHASE_BREAK: str = "break"
PHASE_LONG_BREAK: str = "long_break"
PHASE_IDLE: str = "idle"

#: Default durations (minutes).
DEFAULT_WORK_MIN: int = 25
DEFAULT_BREAK_MIN: int = 5
DEFAULT_LONG_BREAK_MIN: int = 15
DEFAULT_CYCLES: int = 4

#: Kv-store key for persisted state.
STATE_KEY: str = "pomodoro.state"

#: Kv-store key for default settings.
SETTINGS_KEY: str = "pomodoro.settings"


# Type alias used in many places.
Phase = str  # one of PHASE_WORK / PHASE_BREAK / PHASE_LONG_BREAK / PHASE_IDLE


# =============================================================================
# === Data classes                                                           ===
# =============================================================================

@dataclass
class PomodoroSettings:
    """User-configurable Pomodoro durations."""

    work_min: int = DEFAULT_WORK_MIN
    break_min: int = DEFAULT_BREAK_MIN
    long_break_min: int = DEFAULT_LONG_BREAK_MIN
    cycles: int = DEFAULT_CYCLES
    auto_start_breaks: bool = True
    auto_start_work: bool = False
    sound_on_complete: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PomodoroSettings":
        if not d or not isinstance(d, dict):
            return cls()
        return cls(
            work_min=int(d.get("work_min", DEFAULT_WORK_MIN)),
            break_min=int(d.get("break_min", DEFAULT_BREAK_MIN)),
            long_break_min=int(d.get("long_break_min", DEFAULT_LONG_BREAK_MIN)),
            cycles=int(d.get("cycles", DEFAULT_CYCLES)),
            auto_start_breaks=bool(d.get("auto_start_breaks", True)),
            auto_start_work=bool(d.get("auto_start_work", False)),
            sound_on_complete=bool(d.get("sound_on_complete", True)),
        )


@dataclass
class PomodoroState:
    """Snapshot of the running Pomodoro timer at a point in time."""

    phase: Phase = PHASE_IDLE
    cycle: int = 0                 # 0-based index of current work cycle (0..cycles-1)
    cycles_total: int = DEFAULT_CYCLES
    started_at: Optional[str] = None   # ISO datetime when current phase started
    ends_at: Optional[str] = None      # ISO datetime when current phase ends
    paused_at: Optional[str] = None    # ISO datetime when paused (None = running)
    paused_remaining_sec: Optional[int] = None  # remaining when paused
    title: str = ""                # activity title for the current work phase
    category_id: Optional[int] = None
    completed_cycles: int = 0      # number of work phases completed this run
    total_work_min: int = 0        # accumulated work minutes this run
    total_break_min: int = 0       # accumulated break minutes this run
    run_started_at: Optional[str] = None  # ISO datetime when the whole run started

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PomodoroState":
        if not d or not isinstance(d, dict):
            return cls()
        try:
            return cls(**{k: d.get(k) for k in cls().__dataclass_fields__})  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return cls()


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_ts() -> str:
    """Return current UTC ISO datetime."""
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _seconds_until(ends_at: Optional[str]) -> int:
    """Seconds from now until `ends_at`.  Negative if already past."""
    if not ends_at:
        return 0
    end = _parse_iso(ends_at)
    if end is None:
        return 0
    now = datetime.now(timezone.utc)
    delta = (end - now).total_seconds()
    return int(delta)


def _add_minutes_iso(minutes: int) -> str:
    """Return ISO datetime `minutes` from now."""
    now = datetime.now(timezone.utc)
    return (now + _timedelta_minutes(minutes)).isoformat()


def _timedelta_minutes(minutes: int):
    from datetime import timedelta
    return timedelta(minutes=minutes)


def _phase_color(phase: Phase) -> str:
    """Return a hex color for the phase (for UI styling)."""
    if phase == PHASE_WORK:
        return "#D4AF37"        # gold
    if phase == PHASE_BREAK:
        return "#7BC97B"        # green
    if phase == PHASE_LONG_BREAK:
        return "#7B9BC9"        # blue
    return "#9A9A9F"            # idle grey


def _phase_label(phase: Phase, lang: str = "fa") -> str:
    """Return a localized label for the phase."""
    if lang == "fa":
        return {
            PHASE_WORK: "تمرکز",
            PHASE_BREAK: "استراحت کوتاه",
            PHASE_LONG_BREAK: "استراحت بلند",
            PHASE_IDLE: "آماده",
        }.get(phase, phase)
    return {
        PHASE_WORK: "Focus",
        PHASE_BREAK: "Short Break",
        PHASE_LONG_BREAK: "Long Break",
        PHASE_IDLE: "Idle",
    }.get(phase, phase)


# =============================================================================
# === PomodoroService                                                        ===
# =============================================================================

class PomodoroService:
    """Pomodoro timer with auto-cycling and activity logging.

    The service is single-instance (``pomodoro_service`` at module
    scope).  All public methods are safe to call from any thread;
    state mutations are guarded by a re-entrant lock.
    """

    def __init__(self) -> None:
        import threading
        self._lock = threading.RLock()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._settings: PomodoroSettings = self._load_settings()
        self._state: PomodoroState = self._load_state()
        # If we crashed mid-phase, mark as idle so we don't auto-fire.
        if self._state.phase not in (PHASE_IDLE,):
            # We keep the persisted phase so the UI can show "paused",
            # but treat it as paused (no countdown fires).
            if self._state.paused_at is None:
                # If the end time has already passed, advance manually.
                if _seconds_until(self._state.ends_at) <= 0:
                    self._handle_phase_expired(silent=True)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> PomodoroSettings:
        try:
            raw = db.kv_get_json(SETTINGS_KEY, {})
            return PomodoroSettings.from_dict(raw)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return PomodoroSettings()

    def _save_settings(self) -> None:
        try:
            db.kv_set_json(SETTINGS_KEY, self._settings.to_dict())
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _load_state(self) -> PomodoroState:
        try:
            raw = db.kv_get_json(STATE_KEY, {})
            return PomodoroState.from_dict(raw)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return PomodoroState()

    def _save_state(self) -> None:
        try:
            db.kv_set_json(STATE_KEY, self._state.to_dict())
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Public: settings
    # ------------------------------------------------------------------

    def get_settings(self) -> PomodoroSettings:
        """Return the current Pomodoro settings (a copy is fine; it's a dataclass)."""
        return PomodoroSettings(**self._settings.to_dict())

    def update_settings(self, **fields: Any) -> PomodoroSettings:
        """Update one or more settings fields.  Returns the new settings."""
        with self._lock:
            for k, v in fields.items():
                if hasattr(self._settings, k):
                    setattr(self._settings, k, v)
            self._save_settings()
            _log.info("Pomodoro settings updated: %s", list(fields.keys()))
            return self.get_settings()

    # ------------------------------------------------------------------
    # Public: lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        work_min: Optional[int] = None,
        break_min: Optional[int] = None,
        long_break_min: Optional[int] = None,
        cycles: Optional[int] = None,
        *,
        title: str = "",
        category_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a fresh Pomodoro run.

        Overrides any in-progress run.  All parameters are optional and
        default to the saved settings.  Returns the initial state
        snapshot.
        """
        with self._lock:
            if work_min is not None:
                self._settings.work_min = max(1, int(work_min))
            if break_min is not None:
                self._settings.break_min = max(1, int(break_min))
            if long_break_min is not None:
                self._settings.long_break_min = max(1, int(long_break_min))
            if cycles is not None:
                self._settings.cycles = max(1, int(cycles))
            self._save_settings()

            now = _now_ts()
            self._state = PomodoroState(
                phase=PHASE_WORK,
                cycle=0,
                cycles_total=self._settings.cycles,
                started_at=now,
                ends_at=_add_minutes_iso(self._settings.work_min),
                paused_at=None,
                paused_remaining_sec=None,
                title=title or i18n.t("pomodoroDefaultTitle", "fa") or "Pomodoro",
                category_id=category_id,
                completed_cycles=0,
                total_work_min=0,
                total_break_min=0,
                run_started_at=now,
            )
            self._save_state()

            payload = self._state_payload()
            bus.publish("pomodoro.started", payload)
            self._notify_listeners({"event": "started", **payload})
            _log.info("Pomodoro started: title=%r cycles=%d work=%dm",
                      self._state.title, self._settings.cycles,
                      self._settings.work_min)
            return payload

    def pause(self) -> Dict[str, Any]:
        """Pause the current phase.  Returns the paused state."""
        with self._lock:
            if self._state.phase == PHASE_IDLE:
                return self._state_payload()
            if self._state.paused_at is not None:
                return self._state_payload()
            remaining = _seconds_until(self._state.ends_at)
            self._state.paused_at = _now_ts()
            self._state.paused_remaining_sec = max(0, remaining)
            self._save_state()
            payload = self._state_payload()
            bus.publish("pomodoro.paused", payload)
            self._notify_listeners({"event": "paused", **payload})
            _log.info("Pomodoro paused: remaining=%ds", remaining)
            return payload

    def resume(self) -> Dict[str, Any]:
        """Resume a paused phase."""
        with self._lock:
            if self._state.paused_at is None:
                return self._state_payload()
            remaining_sec = int(self._state.paused_remaining_sec or 0)
            from datetime import timedelta
            new_end = (datetime.now(timezone.utc) +
                       timedelta(seconds=remaining_sec)).isoformat()
            self._state.paused_at = None
            self._state.paused_remaining_sec = None
            self._state.ends_at = new_end
            self._save_state()
            payload = self._state_payload()
            bus.publish("pomodoro.resumed", payload)
            self._notify_listeners({"event": "resumed", **payload})
            _log.info("Pomodoro resumed: remaining=%ds", remaining_sec)
            return payload

    def stop(self) -> Dict[str, Any]:
        """Stop the run entirely.  Partial work is logged as an activity."""
        with self._lock:
            if self._state.phase == PHASE_IDLE:
                return self._state_payload()

            # If we were in a work phase, log the partial minutes.
            if self._state.phase == PHASE_WORK:
                elapsed_min = self._compute_partial_work_min()
                if elapsed_min >= 1:
                    self._log_activity(elapsed_min)

            payload = {
                "at_iso": _now_ts(),
                "completed_cycles": self._state.completed_cycles,
                "partial_min": self._compute_partial_work_min(),
                "total_work_min": self._state.total_work_min,
                "total_break_min": self._state.total_break_min,
            }
            self._state = PomodoroState()
            self._save_state()
            bus.publish("pomodoro.stopped", payload)
            self._notify_listeners({"event": "stopped", **payload})
            _log.info("Pomodoro stopped: completed=%d",
                      payload["completed_cycles"])
            return payload

    def skip(self) -> Dict[str, Any]:
        """Skip the current phase and advance to the next."""
        with self._lock:
            if self._state.phase == PHASE_IDLE:
                return self._state_payload()

            prev_phase = self._state.phase
            if prev_phase == PHASE_WORK:
                # Don't log skipped work; user explicitly chose to skip.
                self._advance_to_break(silent=True)
            elif prev_phase in (PHASE_BREAK, PHASE_LONG_BREAK):
                self._advance_to_work(silent=True)

            payload = {
                "skipped_phase": prev_phase,
                "next_phase": self._state.phase,
                **self._state_payload(),
            }
            bus.publish("pomodoro.skipped", payload)
            self._notify_listeners({"event": "skipped", **payload})
            _log.info("Pomodoro skipped: %s -> %s",
                      prev_phase, self._state.phase)
            return payload

    # ------------------------------------------------------------------
    # Public: state inspection
    # ------------------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        """Return a dict describing the current Pomodoro state.

        Keys: ``phase``, ``cycle``, ``cycles_total``, ``started_at``,
        ``ends_at``, ``remaining_sec``, ``paused``, ``title``,
        ``category_id``, ``completed_cycles``, ``progress`` (0..1).
        """
        with self._lock:
            return self._state_payload()

    def is_active(self) -> bool:
        """True if a Pomodoro run is currently in progress (even if paused)."""
        return self._state.phase != PHASE_IDLE

    def is_paused(self) -> bool:
        return self._state.paused_at is not None

    def remaining_sec(self) -> int:
        with self._lock:
            if self._state.paused_at is not None:
                return int(self._state.paused_remaining_sec or 0)
            return max(0, _seconds_until(self._state.ends_at))

    def progress(self) -> float:
        """Return 0..1 representing how far through the current phase we are."""
        with self._lock:
            if self._state.phase == PHASE_IDLE:
                return 0.0
            total = self._phase_duration_sec(self._state.phase)
            if total <= 0:
                return 0.0
            return max(0.0, min(1.0, 1.0 - self.remaining_sec() / total))

    # ------------------------------------------------------------------
    # Listeners (UI hook)
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[Dict[str, Any]], None]) -> Callable[[Dict[str, Any]], None]:
        """Register a callback that is invoked on every state change.

        The callback receives a dict with at least an ``event`` key
        (``started``/``paused``/``resumed``/``stopped``/``skipped``/
        ``phase_changed``/``cycle_complete``/``finished``/``tick``)
        plus the state payload.

        Returns the callback (for use as a decorator).
        """
        with self._lock:
            self._listeners.append(callback)
        return callback

    def remove_listener(self, callback: Callable[[Dict[str, Any]], None]) -> bool:
        with self._lock:
            try:
                self._listeners.remove(callback)
                return True
            except ValueError:
                return False

    def _notify_listeners(self, payload: Dict[str, Any]) -> None:
        # Snapshot under lock, invoke outside.
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(payload)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Pomodoro listener error: %s", exc)

    # ------------------------------------------------------------------
    # Tick: called by UI driver every second
    # ------------------------------------------------------------------

    def tick(self) -> Optional[Dict[str, Any]]:
        """Advance the timer.  Called every second by the UI widget.

        If the current phase has just expired, advances to the next
        phase and returns the ``phase_changed`` payload.  Otherwise
        returns a ``tick`` payload with the new remaining_sec.  Returns
        ``None`` if the timer is idle.
        """
        with self._lock:
            if self._state.phase == PHASE_IDLE:
                return None
            if self._state.paused_at is not None:
                return None

            remaining = _seconds_until(self._state.ends_at)
            if remaining > 0:
                payload = {
                    "event": "tick",
                    "remaining_sec": remaining,
                    "phase": self._state.phase,
                    "cycle": self._state.cycle,
                    "progress": self.progress(),
                }
                # Light-weight: don't notify all listeners on every tick.
                bus.publish("pomodoro.tick", payload)
                return payload

            # Phase has expired — advance.
            return self._handle_phase_expired(silent=False)

    # ------------------------------------------------------------------
    # Internal: phase transitions
    # ------------------------------------------------------------------

    def _handle_phase_expired(self, *, silent: bool) -> Optional[Dict[str, Any]]:
        """Called when the current phase's end time has passed."""
        prev_phase = self._state.phase
        if prev_phase == PHASE_WORK:
            # Log the completed work cycle as an activity.
            duration_min = self._settings.work_min
            activity_id = self._log_activity(duration_min)
            self._state.completed_cycles += 1
            self._state.total_work_min += duration_min

            cycle_payload = {
                "cycle": self._state.cycle,
                "activity_id": activity_id,
                "duration_min": duration_min,
                "completed_cycles": self._state.completed_cycles,
            }
            if not silent:
                bus.publish("pomodoro.cycle_complete", cycle_payload)
                self._notify_listeners({"event": "cycle_complete", **cycle_payload})

            # If all cycles done, go to long break and then finish.
            if self._state.cycle + 1 >= self._state.cycles_total:
                self._advance_to_long_break(silent=silent)
            else:
                self._advance_to_break(silent=silent)

            payload = {
                "event": "phase_changed",
                "previous_phase": prev_phase,
                **self._state_payload(),
            }
            if not silent:
                bus.publish("pomodoro.phase_changed", payload)
                self._notify_listeners(payload)
            return payload

        if prev_phase in (PHASE_BREAK, PHASE_LONG_BREAK):
            duration_min = (self._settings.break_min
                            if prev_phase == PHASE_BREAK
                            else self._settings.long_break_min)
            self._state.total_break_min += duration_min

            # If we just finished a long break, the run is complete.
            if prev_phase == PHASE_LONG_BREAK:
                return self._finish(silent=silent)

            # Otherwise advance to next work cycle.
            self._advance_to_work(silent=silent)
            payload = {
                "event": "phase_changed",
                "previous_phase": prev_phase,
                **self._state_payload(),
            }
            if not silent:
                bus.publish("pomodoro.phase_changed", payload)
                self._notify_listeners(payload)
            return payload

        return None

    def _advance_to_break(self, *, silent: bool) -> None:
        """Move from a completed work phase into the next short break."""
        now = _now_ts()
        self._state.phase = PHASE_BREAK
        self._state.started_at = now
        self._state.ends_at = _add_minutes_iso(self._settings.break_min)
        self._state.paused_at = None
        self._state.paused_remaining_sec = None
        self._save_state()

    def _advance_to_long_break(self, *, silent: bool) -> None:
        """Move from the last work phase into the long break."""
        now = _now_ts()
        self._state.phase = PHASE_LONG_BREAK
        self._state.started_at = now
        self._state.ends_at = _add_minutes_iso(self._settings.long_break_min)
        self._state.paused_at = None
        self._state.paused_remaining_sec = None
        self._save_state()

    def _advance_to_work(self, *, silent: bool) -> None:
        """Move from a completed break into the next work cycle."""
        self._state.cycle += 1
        now = _now_ts()
        self._state.phase = PHASE_WORK
        self._state.started_at = now
        self._state.ends_at = _add_minutes_iso(self._settings.work_min)
        self._state.paused_at = None
        self._state.paused_remaining_sec = None
        self._save_state()

    def _finish(self, *, silent: bool) -> Dict[str, Any]:
        """Mark the entire run as complete."""
        payload = {
            "event": "finished",
            "completed_cycles": self._state.completed_cycles,
            "total_work_min": self._state.total_work_min,
            "total_break_min": self._state.total_break_min,
            "ended_at": _now_ts(),
        }
        self._state = PomodoroState()
        self._save_state()
        if not silent:
            bus.publish("pomodoro.finished", payload)
            self._notify_listeners(payload)
            _log.info("Pomodoro finished: completed=%d work=%dm break=%dm",
                      payload["completed_cycles"],
                      payload["total_work_min"],
                      payload["total_break_min"])
        return payload

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    def _phase_duration_sec(self, phase: Phase) -> int:
        """Return the configured duration (in seconds) for `phase`."""
        if phase == PHASE_WORK:
            return self._settings.work_min * 60
        if phase == PHASE_BREAK:
            return self._settings.break_min * 60
        if phase == PHASE_LONG_BREAK:
            return self._settings.long_break_min * 60
        return 0

    def _compute_partial_work_min(self) -> int:
        """Return the minutes elapsed in the current work phase so far."""
        if self._state.phase != PHASE_WORK:
            return 0
        total = self._settings.work_min * 60
        if total <= 0:
            return 0
        if self._state.paused_at is not None:
            elapsed = total - int(self._state.paused_remaining_sec or 0)
        else:
            elapsed = total - _seconds_until(self._state.ends_at)
        return max(0, elapsed // 60)

    def _log_activity(self, duration_min: int) -> int:
        """Create an activity record for a completed (or partial) work phase.

        Returns the new activity id (0 on failure).
        """
        try:
            from ..services.activity_service import activity_service
            activity = activity_service.add(
                title=self._state.title or "Pomodoro",
                category_id=self._state.category_id,
                duration_min=duration_min,
                date_iso=today_iso(),
                kind="manual",  # Pomodoro-completed work counts as manual
                source="desktop",
                tags=["pomodoro"],
                notes=f"Pomodoro cycle #{self._state.completed_cycles + 1}",
            )
            return int(activity.get("id", 0))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"title": self._state.title,
                                       "duration_min": duration_min})
            return 0

    def _state_payload(self) -> Dict[str, Any]:
        """Build a dict snapshot of the current state for events / UI."""
        return {
            "phase": self._state.phase,
            "cycle": self._state.cycle,
            "cycles_total": self._state.cycles_total,
            "started_at": self._state.started_at,
            "ends_at": self._state.ends_at,
            "paused": self._state.paused_at is not None,
            "paused_at": self._state.paused_at,
            "remaining_sec": self.remaining_sec(),
            "progress": self.progress(),
            "title": self._state.title,
            "category_id": self._state.category_id,
            "completed_cycles": self._state.completed_cycles,
            "total_work_min": self._state.total_work_min,
            "total_break_min": self._state.total_break_min,
            "run_started_at": self._state.run_started_at,
            "phase_label_fa": _phase_label(self._state.phase, "fa"),
            "phase_label_en": _phase_label(self._state.phase, "en"),
            "phase_color": _phase_color(self._state.phase),
        }


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

pomodoro_service: PomodoroService = PomodoroService()


# =============================================================================
# === UI Widget (lazy CustomTkinter import)                                  ===
# =============================================================================

def _import_ctk():
    """Lazy-import customtkinter.  Returns the module or None."""
    try:
        import customtkinter as ctk  # type: ignore
        return ctk
    except Exception:  # noqa: BLE001
        return None


class PomodoroWidget:
    """CustomTkinter widget showing the live Pomodoro timer.

    NOTE: This is implemented as a class factory rather than a
    ``CTkFrame`` subclass so that the module can be imported in a
    headless environment (e.g. CLI / tests).  Call
    :meth:`PomodoroWidget.build` to construct the actual Tk widget.

    The widget shows:
      • Current phase label (color-coded: gold for work, green for break)
      • Large count-down timer (HH:MM:SS)
      • 4-dot cycle indicator (filled = completed)
      • Pause/Resume/Stop/Skip buttons
      • Quick settings (work/break duration)

    The widget auto-ticks every 250 ms via ``widget.after()`` and
    calls :meth:`PomodoroService.tick` once per second (throttled).
    """

    def __init__(self, master: Any = None, *, lang: str = "fa") -> None:
        self.master = master
        self.lang = lang
        self._frame: Any = None
        self._after_id: Optional[str] = None
        self._last_tick_at: float = 0.0

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self) -> Any:
        """Build the Tk frame and start the tick loop.  Returns the frame."""
        ctk = _import_ctk()
        if ctk is None:
            raise RuntimeError("CustomTkinter is not available")
        from .. import config

        f = ctk.CTkFrame(self.master, corner_radius=config.RADIUS_LG,
                          fg_color=config.CHARCOAL)
        self._frame = f

        # --- Phase label ---
        self._phase_label = ctk.CTkLabel(
            f, text="",
            font=ctk.CTkFont(size=config.FONT_SIZE_HEADING_SM,
                              weight=config.FONT_WEIGHT_BOLD),
            text_color=config.GOLD,
        )
        self._phase_label.pack(pady=(config.SPACE_LG, config.SPACE_XS))

        # --- Big countdown ---
        self._countdown_label = ctk.CTkLabel(
            f, text="25:00",
            font=ctk.CTkFont(size=config.FONT_SIZE_HERO,
                              weight=config.FONT_WEIGHT_BLACK),
            text_color=config.TEXT,
        )
        self._countdown_label.pack(pady=(config.SPACE_XS, config.SPACE_MD))

        # --- Cycle dots ---
        self._dots_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._dots_frame.pack(pady=(0, config.SPACE_MD))
        self._dots: list[Any] = []
        for i in range(4):
            dot = ctk.CTkLabel(
                self._dots_frame, text="●",
                font=ctk.CTkFont(size=config.FONT_SIZE_BODY_LG),
                text_color=config.TEXT_MUTED,
            )
            dot.pack(side="left", padx=4)
            self._dots.append(dot)

        # --- Buttons ---
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(pady=(config.SPACE_SM, config.SPACE_LG))
        self._pause_btn = ctk.CTkButton(
            btn_row, text=i18n.t("pause", self.lang) or "توقف",
            width=100, command=self._on_pause_toggle,
            fg_color=config.GOLD, hover_color=config.GOLD_SOFT,
            text_color=config.MATTE_BLACK,
        )
        self._pause_btn.pack(side="left", padx=6)

        self._stop_btn = ctk.CTkButton(
            btn_row, text=i18n.t("stop", self.lang) or "توقف کامل",
            width=100, command=self._on_stop,
            fg_color=config.SURFACE_HI, hover_color=config.SURFACE_HIGHER,
            text_color=config.TEXT,
        )
        self._stop_btn.pack(side="left", padx=6)

        self._skip_btn = ctk.CTkButton(
            btn_row, text=i18n.t("skip", self.lang) or "رد شدن",
            width=80, command=self._on_skip,
            fg_color=config.SURFACE, hover_color=config.SURFACE_HI,
            text_color=config.TEXT_DIM,
        )
        self._skip_btn.pack(side="left", padx=6)

        # --- Settings row ---
        settings_row = ctk.CTkFrame(f, fg_color="transparent")
        settings_row.pack(pady=(0, config.SPACE_MD), fill="x", padx=20)
        ctk.CTkLabel(settings_row,
                      text=i18n.t("work", self.lang) or "کار",
                      text_color=config.TEXT_DIM).pack(side="left", padx=4)
        self._work_entry = ctk.CTkEntry(settings_row, width=40, justify="center")
        self._work_entry.insert(0, str(pomodoro_service.get_settings().work_min))
        self._work_entry.pack(side="left", padx=4)
        ctk.CTkLabel(settings_row,
                      text=i18n.t("break", self.lang) or "استراحت",
                      text_color=config.TEXT_DIM).pack(side="left", padx=4)
        self._break_entry = ctk.CTkEntry(settings_row, width=40, justify="center")
        self._break_entry.insert(0, str(pomodoro_service.get_settings().break_min))
        self._break_entry.pack(side="left", padx=4)

        # Start the tick loop.
        self._refresh()
        self._schedule_tick()
        return f

    # ------------------------------------------------------------------
    # Tick loop
    # ------------------------------------------------------------------

    def _schedule_tick(self) -> None:
        if self._frame is None:
            return
        try:
            self._after_id = self._frame.after(250, self._on_tick)
        except Exception:  # noqa: BLE001
            pass

    def _on_tick(self) -> None:
        try:
            now = time.time()
            # Throttle to ~1Hz for the service.tick() call.
            if now - self._last_tick_at >= 1.0:
                pomodoro_service.tick()
                self._last_tick_at = now
            self._refresh()
        finally:
            self._schedule_tick()

    def _refresh(self) -> None:
        if self._frame is None:
            return
        s = pomodoro_service.state()
        # Phase label
        label = s.get("phase_label_fa") if self.lang == "fa" else s.get("phase_label_en")
        self._phase_label.configure(text=label or "",
                                      text_color=s.get("phase_color") or "#9A9A9F")
        # Countdown
        remaining = int(s.get("remaining_sec") or 0)
        h = remaining // 3600
        m = (remaining % 3600) // 60
        sec = remaining % 60
        if h:
            text = f"{h:02d}:{m:02d}:{sec:02d}"
        else:
            text = f"{m:02d}:{sec:02d}"
        if self.lang == "fa":
            text = i18n.to_fa_digits(text)
        self._countdown_label.configure(text=text)
        # Cycle dots
        completed = int(s.get("completed_cycles") or 0)
        total = int(s.get("cycles_total") or 4)
        # Rebuild dots if cycle count changed.
        if total != len(self._dots):
            for d in self._dots:
                try:
                    d.destroy()
                except Exception:  # noqa: BLE001
                    pass
            self._dots = []
            ctk = _import_ctk()
            from .. import config
            for i in range(total):
                dot = ctk.CTkLabel(
                    self._dots_frame, text="●",
                    font=ctk.CTkFont(size=config.FONT_SIZE_BODY_LG),
                    text_color=config.GOLD if i < completed else config.TEXT_MUTED,
                )
                dot.pack(side="left", padx=4)
                self._dots.append(dot)
        else:
            from .. import config
            for i, dot in enumerate(self._dots):
                dot.configure(text_color=config.GOLD if i < completed
                              else config.TEXT_MUTED)
        # Pause button label
        if s.get("paused"):
            self._pause_btn.configure(text=i18n.t("resume", self.lang) or "ادامه")
        else:
            self._pause_btn.configure(text=i18n.t("pause", self.lang) or "توقف")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_pause_toggle(self) -> None:
        if pomodoro_service.is_paused():
            pomodoro_service.resume()
        else:
            if not pomodoro_service.is_active():
                # Start a fresh run with the current settings.
                try:
                    work = int(self._work_entry.get() or 25)
                    brk = int(self._break_entry.get() or 5)
                except Exception:  # noqa: BLE001
                    work, brk = 25, 5
                pomodoro_service.start(work_min=work, break_min=brk)
            else:
                pomodoro_service.pause()
        self._refresh()

    def _on_stop(self) -> None:
        pomodoro_service.stop()
        self._refresh()

    def _on_skip(self) -> None:
        pomodoro_service.skip()
        self._refresh()

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        if self._after_id is not None:
            try:
                self._frame.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None
        if self._frame is not None:
            try:
                self._frame.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._frame = None


# =============================================================================
# === Dialog (lazy)                                                          ===
# =============================================================================

def show_pomodoro_dialog(parent: Any = None, *, lang: str = "fa") -> Any:
    """Open a modal Pomodoro settings dialog.

    Returns the dialog handle (a ``CTkToplevel``).  Returns ``None``
    if CustomTkinter is unavailable.
    """
    ctk = _import_ctk()
    if ctk is None:
        return None
    from .. import config
    from ..ui.widgets.dialogs import BaseDialog  # type: ignore

    class PomodoroDialog(BaseDialog):  # type: ignore[misc]
        def __init__(self, master, *, lang: str = "fa") -> None:
            self.lang = lang
            super().__init__(master, title=i18n.t("pomodoroSettings", lang) or
                             "تنظیمات پومودورو", lang=lang)

        def _build_body(self, body: Any) -> None:
            s = pomodoro_service.get_settings()
            ctk.CTkLabel(body, text=i18n.t("workDuration", self.lang) or
                         "مدت کار (دقیقه)",
                         text_color=config.TEXT_DIM).pack(pady=(12, 4))
            self.work_entry = ctk.CTkEntry(body, width=120, justify="center")
            self.work_entry.insert(0, str(s.work_min))
            self.work_entry.pack(pady=4)

            ctk.CTkLabel(body, text=i18n.t("breakDuration", self.lang) or
                         "مدت استراحت (دقیقه)",
                         text_color=config.TEXT_DIM).pack(pady=(12, 4))
            self.break_entry = ctk.CTkEntry(body, width=120, justify="center")
            self.break_entry.insert(0, str(s.break_min))
            self.break_entry.pack(pady=4)

            ctk.CTkLabel(body, text=i18n.t("longBreakDuration", self.lang) or
                         "استراحت بلند (دقیقه)",
                         text_color=config.TEXT_DIM).pack(pady=(12, 4))
            self.long_entry = ctk.CTkEntry(body, width=120, justify="center")
            self.long_entry.insert(0, str(s.long_break_min))
            self.long_entry.pack(pady=4)

            ctk.CTkLabel(body, text=i18n.t("cycles", self.lang) or "تعداد دور",
                         text_color=config.TEXT_DIM).pack(pady=(12, 4))
            self.cycles_entry = ctk.CTkEntry(body, width=120, justify="center")
            self.cycles_entry.insert(0, str(s.cycles))
            self.cycles_entry.pack(pady=4)

            self.auto_break_var = ctk.IntVar(value=int(s.auto_start_breaks))
            ctk.CTkCheckBox(body, text=i18n.t("autoStartBreaks", self.lang) or
                            "شروع خودکار استراحت",
                            variable=self.auto_break_var).pack(pady=8)

            self.auto_work_var = ctk.IntVar(value=int(s.auto_start_work))
            ctk.CTkCheckBox(body, text=i18n.t("autoStartWork", self.lang) or
                            "شروع خودکار کار بعد از استراحت",
                            variable=self.auto_work_var).pack(pady=8)

        def _on_save(self) -> None:
            try:
                pomodoro_service.update_settings(
                    work_min=int(self.work_entry.get() or 25),
                    break_min=int(self.break_entry.get() or 5),
                    long_break_min=int(self.long_entry.get() or 15),
                    cycles=int(self.cycles_entry.get() or 4),
                    auto_start_breaks=bool(self.auto_break_var.get()),
                    auto_start_work=bool(self.auto_work_var.get()),
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Pomodoro settings save failed: %s", exc)
            self._close()

    try:
        return PomodoroDialog(parent, lang=lang)
    except Exception as exc:  # noqa: BLE001
        _log.warning("PomodoroDialog could not be opened: %s", exc)
        return None


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.features.pomodoro"""
    failed = 0
    print("=== Pomodoro self-tests ===")
    try:
        # Start, advance, finish cycle
        pomodoro_service.start(work_min=1, break_min=1, long_break_min=1, cycles=2)
        s = pomodoro_service.state()
        assert s["phase"] == PHASE_WORK, f"expected work, got {s['phase']}"
        # Force expire by manipulating ends_at
        pomodoro_service._state.ends_at = _now_ts()  # noqa: SLF001
        pomodoro_service.tick()
        s = pomodoro_service.state()
        assert s["phase"] in (PHASE_BREAK, PHASE_LONG_BREAK), \
            f"expected break, got {s['phase']}"
        # Skip to next work
        pomodoro_service._state.ends_at = _now_ts()  # noqa: SLF001
        pomodoro_service.skip()
        s = pomodoro_service.state()
        assert s["phase"] == PHASE_WORK, f"expected work, got {s['phase']}"
        # Stop
        pomodoro_service.stop()
        s = pomodoro_service.state()
        assert s["phase"] == PHASE_IDLE, f"expected idle, got {s['phase']}"
        print("  OK   lifecycle")
    except AssertionError as e:
        print(f"  FAIL lifecycle: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL lifecycle (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
