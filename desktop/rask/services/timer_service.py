"""
rask.services.timer_service
===========================

Background stopwatch / timer.

A single persistent timer that survives app restarts.  State is
persisted to the kv store as JSON:

    {
      "title": str,
      "category_id": int | null,
      "started_at": ISO-8601,    # wall-clock when (re)started
      "paused_at": ISO-8601 | null,
      "accumulated_sec": int,    # total seconds accumulated BEFORE current run
      "paused": bool,            # True if currently paused
    }

The elapsed time is computed on each tick from
``accumulated_sec + (now - started_at)`` when running, and from
``accumulated_sec`` alone when paused.  This "wall-clock accumulator"
pattern is robust to clock changes (NTP adjustments, DST, suspend/resume)
because we never trust a long-running monotonic counter — we always
recompute from wall-clock timestamps.

The UI calls :meth:`tick` once per second (via Tk's ``after()`` loop).
Listeners (callbacks) are invoked with the current elapsed seconds on
each tick.

Mirrors the behavior of ``web/js/timer.js``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    format_timer,
    now_iso_local,
    now_iso_utc,
    today_iso,
)

__all__ = ["TimerService", "timer_service"]

_log = get_logger("services.timer")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _parse_iso_local(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO local timestamp into a datetime (or None)."""
    if not s or not isinstance(s, str):
        return None
    try:
        s = s.split("+", 1)[0].rstrip("Z")
        if "." in s:
            s = s.split(".", 1)[0]
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# =============================================================================
# === TimerService                                                           ===
# =============================================================================

class TimerService:
    """Persistent background stopwatch.

    State is persisted to the kv store under
    :data:`config.TIMER_PERSIST_KEY`.  The timer is single-instance —
    starting a new timer while one is running is a no-op (call
    :meth:`stop` first).
    """

    def __init__(self) -> None:
        self._listeners: List[Callable[[int, bool], None]] = []
        self._root: Any = None
        self._tick_handle: Optional[str] = None
        # Cached state mirror for fast access without DB round-trip.
        self._state_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Load persisted timer state at startup.

        If a timer was running when the app was last closed, it
        continues running (the wall-clock gap is folded into the
        elapsed time automatically).  If it was paused, the elapsed
        time is preserved but the timer remains paused.
        """
        state = self._load_state()
        if state and state.get("started_at"):
            _log.info("Resumed timer: title=%r running=%s",
                      state.get("title"), not state.get("paused"))
        self._state_cache = state

    def init_on_startup(self) -> None:
        """Alias for :meth:`init` (kept for API parity with spec)."""
        self.init()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        """Load persisted state from the kv store."""
        try:
            raw = db.kv_get(config.TIMER_PERSIST_KEY, "")
            if not raw:
                return {}
            state = json.loads(raw)
            if not isinstance(state, dict):
                return {}
            return state
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        """Persist state to the kv store."""
        try:
            db.kv_set(config.TIMER_PERSIST_KEY,
                       json.dumps(state, ensure_ascii=False))
            self._state_cache = dict(state)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _clear_state(self) -> None:
        """Clear persisted state."""
        try:
            db.kv_set(config.TIMER_PERSIST_KEY, "")
            self._state_cache = None
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Start / pause / resume / stop / reset
    # ------------------------------------------------------------------

    def start(self, title: str, category_id: Optional[int] = None) -> Dict[str, Any]:
        """Start a new timer.

        Returns the new state dict (the rich :meth:`state` view, with
        ``running`` / ``paused`` / ``elapsed_sec`` etc.).  If a timer
        is already running, it is returned unchanged (no-op).
        """
        state = self._load_state()
        if state and not state.get("paused"):
            _log.warning("start: timer already running")
            return self.state()

        now = now_iso_local()
        # Preserve accumulated seconds if we're starting fresh after a reset.
        accumulated = 0
        new_state = {
            "title": title or "",
            "category_id": category_id,
            "started_at": now,
            "paused_at": None,
            "accumulated_sec": accumulated,
            "paused": False,
        }
        self._save_state(new_state)
        bus.publish("timer.started", new_state)
        _log.info("Timer started: title=%r", title)
        self._start_tick_loop()
        return self.state()

    def pause(self) -> bool:
        """Pause the running timer.  Returns True on success."""
        state = self._load_state()
        if not state or state.get("paused"):
            return False
        elapsed = self._compute_elapsed_sec(state)
        new_state = dict(state)
        new_state["paused"] = True
        new_state["paused_at"] = now_iso_local()
        new_state["accumulated_sec"] = elapsed
        new_state["started_at"] = None  # not running
        self._save_state(new_state)
        bus.publish("timer.paused", new_state)
        _log.info("Timer paused at %d sec", elapsed)
        return True

    def resume(self) -> bool:
        """Resume a paused timer.  Returns True on success."""
        state = self._load_state()
        if not state or not state.get("paused"):
            return False
        new_state = dict(state)
        new_state["paused"] = False
        new_state["paused_at"] = None
        new_state["started_at"] = now_iso_local()
        # accumulated_sec is preserved (set on pause)
        self._save_state(new_state)
        bus.publish("timer.resumed", new_state)
        _log.info("Timer resumed")
        self._start_tick_loop()
        return True

    def stop(self, save: bool = True) -> Optional[Dict[str, Any]]:
        """Stop the timer.

        Parameters
        ----------
        save : bool
            If ``True`` (default), create an activity from the elapsed
            time and return its dict.  If ``False``, just stop without
            saving (returns ``None``).

        If the elapsed time is < 5 seconds, no activity is created
        (matches the web PWA behavior).
        """
        state = self._load_state()
        if not state:
            return None

        elapsed = self._compute_elapsed_sec(state)
        title = state.get("title", "")
        category_id = state.get("category_id")

        self._clear_state()
        bus.publish("timer.stopped", {"elapsed_sec": elapsed,
                                       "saved": save})
        _log.info("Timer stopped at %d sec (save=%s)", elapsed, save)
        self._stop_tick_loop()

        if not save or elapsed < 5:
            return None

        # Create activity.
        try:
            from .activity_service import activity_service
            now = datetime.now()
            start_dt = now - timedelta(seconds=elapsed)
            activity = activity_service.add(
                title=title or "(بدون عنوان)",
                category_id=category_id,
                duration_min=max(1, elapsed // 60),
                date_iso=today_iso(),
                start_ts=start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                end_ts=now.strftime("%Y-%m-%dT%H:%M:%S"),
                kind="stopwatch",
            )
            return activity
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"elapsed": elapsed})
            return None

    def cancel(self) -> bool:
        """Stop the timer without saving.  Returns True if there was one."""
        state = self._load_state()
        if not state:
            return False
        self._clear_state()
        bus.publish("timer.stopped", {"elapsed_sec": 0, "saved": False,
                                       "cancelled": True})
        self._stop_tick_loop()
        _log.info("Timer cancelled")
        return True

    def reset(self) -> bool:
        """Reset the timer to zero (clears all state)."""
        had_state = bool(self._load_state())
        self._clear_state()
        if had_state:
            bus.publish("timer.stopped", {"elapsed_sec": 0, "saved": False,
                                           "reset": True})
        self._stop_tick_loop()
        self._notify_listeners(0, False)
        _log.info("Timer reset")
        return True

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        """Return the current timer state dict.

        Includes the computed ``elapsed_sec`` for convenience.
        """
        s = self._load_state()
        if not s:
            return {
                "running": False,
                "paused": False,
                "started_at": None,
                "paused_at": None,
                "elapsed_sec": 0,
                "title": "",
                "category_id": None,
                "accumulated_sec": 0,
            }
        return {
            "running": not s.get("paused", False) and bool(s.get("started_at")),
            "paused": bool(s.get("paused")),
            "started_at": s.get("started_at"),
            "paused_at": s.get("paused_at"),
            "elapsed_sec": self._compute_elapsed_sec(s),
            "title": s.get("title", ""),
            "category_id": s.get("category_id"),
            "accumulated_sec": int(s.get("accumulated_sec", 0)),
        }

    def elapsed_seconds(self) -> int:
        """Return the current elapsed seconds (0 if no timer)."""
        state = self._load_state()
        if not state:
            return 0
        return self._compute_elapsed_sec(state)

    def is_running(self) -> bool:
        """Return True if the timer is currently running (not paused)."""
        state = self._load_state()
        return bool(state and not state.get("paused") and state.get("started_at"))

    def is_paused(self) -> bool:
        """Return True if the timer exists and is paused."""
        state = self._load_state()
        return bool(state and state.get("paused"))

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_elapsed(self, lang: str = "fa") -> str:
        """Return the elapsed time as ``HH:MM:SS`` (or ``MM:SS`` if < 1h)."""
        return format_timer(self.elapsed_seconds(), lang)

    # ------------------------------------------------------------------
    # Tick loop (UI-driven)
    # ------------------------------------------------------------------

    def set_root(self, root_widget: Any) -> None:
        """Set the Tk root widget used for the after-loop."""
        self._root = root_widget
        if root_widget is not None and self.is_running():
            self._start_tick_loop()

    def tick(self) -> None:
        """One UI tick: notify listeners with the current elapsed seconds.

        Call this once per second from the UI's ``after()`` loop.
        """
        if not self._load_state():
            return
        elapsed = self.elapsed_seconds()
        running = self.is_running()
        bus.publish("timer.tick", {"elapsed_sec": elapsed, "running": running})
        self._notify_listeners(elapsed, running)

    def _start_tick_loop(self) -> None:
        """Start the periodic tick loop using ``root.after``."""
        if self._root is None:
            return
        if self._tick_handle is not None:
            try:
                self._root.after_cancel(self._tick_handle)
            except Exception:  # noqa: BLE001
                pass
        try:
            self._tick_handle = self._root.after(
                config.TIMER_TICK_MS, self._tick_loop_step)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _stop_tick_loop(self) -> None:
        if self._tick_handle is not None and self._root is not None:
            try:
                self._root.after_cancel(self._tick_handle)
            except Exception:  # noqa: BLE001
                pass
            self._tick_handle = None

    def _tick_loop_step(self) -> None:
        """Internal: called by ``after``.  Ticks and re-arms."""
        try:
            self.tick()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        if self.is_running():
            self._tick_handle = self._root.after(
                config.TIMER_TICK_MS, self._tick_loop_step)
        else:
            self._tick_handle = None

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[int, bool], None]) -> None:
        """Register a listener.  Called as ``callback(elapsed_sec, running)``."""
        if callable(callback) and callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[int, bool], None]) -> None:
        """Unregister a listener."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self, elapsed: int, running: bool) -> None:
        """Notify all listeners with the current elapsed/running state."""
        for cb in list(self._listeners):
            try:
                cb(elapsed, running)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # Internal: elapsed computation
    # ------------------------------------------------------------------

    def _compute_elapsed_sec(self, state: Dict[str, Any]) -> int:
        """Compute elapsed seconds from a state dict.

        Uses the wall-clock accumulator pattern:
          - ``accumulated_sec`` is the total time accumulated BEFORE
            the current run.
          - If ``started_at`` is set and we're not paused, add the
            wall-clock delta from ``started_at`` to now.

        Robust to clock changes because we recompute from wall-clock
        timestamps on every call.
        """
        if not state:
            return 0
        accumulated = int(state.get("accumulated_sec", 0))
        if state.get("paused"):
            return accumulated
        started = _parse_iso_local(state.get("started_at"))
        if started is None:
            return accumulated
        now = datetime.now()
        delta = (now - started).total_seconds()
        # Clamp negative deltas (clock moved backward) to 0.
        delta = max(0, delta)
        # Safety cap: 16 hours
        delta = min(delta, config.TIMER_MAX_HOURS * 3600)
        return accumulated + int(delta)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

timer_service: TimerService = TimerService()
