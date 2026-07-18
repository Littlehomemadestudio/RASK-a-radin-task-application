"""
rask.core.event_bus
===================

In-process publish/subscribe event bus for the Rask desktop app.

The bus is intentionally minimal — no threading, no async, no external
dependencies.  It exists so that UI widgets, services, and the data
layer can communicate without holding direct references to each other.

A module-level :data:`bus` singleton is provided for convenience; use
it everywhere in the app so all subscribers see the same bus.

Standard event names are listed in :data:`STANDARD_EVENTS` to encourage
consistency.  Arbitrary event names are also accepted (the bus does not
enforce the catalog), but sticking to the standard names keeps logs
greppable and refactorings safe.

Example
-------
    >>> from rask.core.event_bus import bus
    >>> received = []
    >>> bus.subscribe("activity.added", lambda a: received.append(a))
    >>> bus.publish("activity.added", {"id": 1, "title": "Test"})
    >>> received
    [{'id': 1, 'title': 'Test'}]

Thread safety
-------------
The bus uses a plain ``dict`` of ``list``s.  All mutations and reads
happen under a re-entrant lock, so it is safe to subscribe / publish
from any thread.  Callbacks are invoked **synchronously** on the
publishing thread — long-running work should be dispatched to a worker
queue inside the callback.
"""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Dict, List, Optional, Set

__all__ = [
    "EventBus",
    "bus",
    "STANDARD_EVENTS",
]

# =============================================================================
# === Standard event names                                                  ===
# =============================================================================

#: Catalog of event names used throughout the app.  The bus accepts any
#: string, but using these constants prevents typos and makes log
#: greps reliable.
STANDARD_EVENTS: List[str] = [
    # Activity CRUD.
    "activity.added",
    "activity.updated",
    "activity.deleted",
    # Goal CRUD + progress.
    "goal.added",
    "goal.updated",
    "goal.deleted",
    "goal.progress",
    # Streak updates.
    "streak.incremented",
    "streak.reset",
    # Badges.
    "badge.unlocked",
    # Stopwatch / timer lifecycle.
    "timer.started",
    "timer.paused",
    "timer.resumed",
    "timer.stopped",
    "timer.tick",
    # Settings + locale.
    "settings.changed",
    "language.changed",
    "theme.changed",
    # Backup / restore.
    "backup.created",
    "backup.restored",
    # Reminders.
    "reminder.triggered",
    "reminder.dismissed",
    "reminder.snoozed",
    # UI events.
    "ui.tab_changed",
    "ui.dialog_opened",
    "ui.dialog_closed",
    "ui.toast",
    # Data lifecycle.
    "data.imported",
    "data.cleared",
]


# Type alias: callbacks accept any args and may return anything (return
# values are ignored by the bus).
EventCallback = Callable[..., Any]


# =============================================================================
# === EventBus                                                              ===
# =============================================================================

class EventBus:
    """A minimal thread-safe pub/sub event bus.

    Each event name maps to a list of callbacks.  Callbacks are
    invoked in the order they were subscribed.  Exceptions inside a
    callback are caught and logged to ``stderr`` — they do not prevent
    subsequent callbacks from running.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventCallback]] = {}
        self._lock = threading.RLock()
        # Per-bus exception hook.  Override to integrate with the app's
        # logging pipeline.  Signature: (event, callback, exc) -> None.
        self.on_callback_error: Optional[
            Callable[[str, EventCallback, BaseException], None]
        ] = None

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, event: str, callback: EventCallback) -> EventCallback:
        """Register `callback` to be invoked when `event` is published.

        Returns the callback (so the decorator pattern works):

            @bus.subscribe("activity.added", _)
            def on_activity_added(activity): ...

        Subscribing the same callback twice will cause it to be called
        twice on publish — the bus does not dedupe.
        """
        if not isinstance(event, str) or not event:
            raise ValueError(f"event must be a non-empty string, got {event!r}")
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback).__name__}")
        with self._lock:
            self._subscribers.setdefault(event, []).append(callback)
        return callback

    def unsubscribe(self, event: str, callback: EventCallback) -> bool:
        """Remove `callback` from the subscribers of `event`.

        Returns True if the callback was found and removed, False
        otherwise.  If `callback` was subscribed multiple times, only
        the first occurrence is removed.
        """
        if not isinstance(event, str) or not event:
            return False
        with self._lock:
            subs = self._subscribers.get(event)
            if not subs:
                return False
            try:
                subs.remove(callback)
            except ValueError:
                return False
            if not subs:
                del self._subscribers[event]
            return True

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, event: str, *args: Any, **kwargs: Any) -> int:
        """Invoke every subscriber for `event` with `args` / `kwargs`.

        Returns the number of callbacks invoked.  Exceptions inside
        individual callbacks are caught and routed to
        :attr:`on_callback_error` (or printed to stderr by default);
        they do not stop subsequent callbacks or propagate to the
        caller.

        Re-entrant publishes (a callback publishing the same or another
        event) are safe — the lock is re-entrant.
        """
        if not isinstance(event, str) or not event:
            return 0
        # Snapshot the subscriber list under the lock so iteration
        # outside the lock is safe even if a callback (un)subscribes.
        with self._lock:
            subs = list(self._subscribers.get(event, ()))
        count = 0
        for cb in subs:
            try:
                cb(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — broad on purpose
                self._handle_error(event, cb, exc)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def clear(self, event: Optional[str] = None) -> int:
        """Remove subscribers.

        - If `event` is given, only that event's subscribers are cleared.
        - If `event` is ``None``, the entire bus is reset.

        Returns the number of callbacks that were removed.
        """
        with self._lock:
            if event is None:
                removed = sum(len(s) for s in self._subscribers.values())
                self._subscribers.clear()
                return removed
            subs = self._subscribers.pop(event, [])
            return len(subs)

    def subscriber_count(self, event: str) -> int:
        """Return the number of subscribers currently registered for `event`."""
        with self._lock:
            return len(self._subscribers.get(event, []))

    def events(self) -> List[str]:
        """Return a sorted list of event names that have ≥1 subscriber."""
        with self._lock:
            return sorted(self._subscribers.keys())

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error(
        self, event: str, callback: EventCallback, exc: BaseException
    ) -> None:
        """Route a callback exception to the configured error hook."""
        if self.on_callback_error is not None:
            try:
                self.on_callback_error(event, callback, exc)
                return
            except Exception:  # noqa: BLE001
                pass  # fall through to default
        # Default: print to stderr (avoid circular import with logging_utils).
        import sys
        print(
            f"[EventBus] callback error in event {event!r}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        with self._lock:
            n_events = len(self._subscribers)
            n_subs = sum(len(s) for s in self._subscribers.values())
        return f"<EventBus events={n_events} subscribers={n_subs}>"


# =============================================================================
# === Module-level singleton                                                ===
# =============================================================================

#: The shared bus used throughout Rask.  Import this directly:
#:
#:     from rask.core.event_bus import bus
bus: EventBus = EventBus()


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.event_bus"""
    tests_passed = 0
    tests_failed = 0

    def check(label: str, got, expected) -> None:
        nonlocal tests_passed, tests_failed
        if got == expected:
            tests_passed += 1
            print(f"  OK   {label}")
        else:
            tests_failed += 1
            print(f"  FAIL {label}: got {got!r}, expected {expected!r}")

    print("=== Basic subscribe / publish ===")
    eb = EventBus()
    received = []
    eb.subscribe("test.event", lambda x: received.append(x))
    n = eb.publish("test.event", 42)
    check("publish count", n, 1)
    check("callback invoked", received, [42])

    print("\n=== Multiple subscribers, ordered ===")
    eb = EventBus()
    order = []
    eb.subscribe("e", lambda: order.append("a"))
    eb.subscribe("e", lambda: order.append("b"))
    eb.subscribe("e", lambda: order.append("c"))
    eb.publish("e")
    check("callbacks in order", order, ["a", "b", "c"])

    print("\n=== Unsubscribe ===")
    eb = EventBus()
    calls = []
    cb1 = lambda: calls.append(1)  # noqa: E731
    cb2 = lambda: calls.append(2)  # noqa: E731
    eb.subscribe("e", cb1)
    eb.subscribe("e", cb2)
    eb.publish("e")
    check("both called", calls, [1, 2])
    eb.unsubscribe("e", cb1)
    calls.clear()
    eb.publish("e")
    check("only cb2 called after unsub", calls, [2])
    check("unsubscribe missing returns False",
          eb.unsubscribe("e", cb1), False)

    print("\n=== kwargs forwarding ===")
    eb = EventBus()
    captured = {}
    eb.subscribe("e", lambda **kw: captured.update(kw))
    eb.publish("e", a=1, b="two")
    check("kwargs forwarded", captured, {"a": 1, "b": "two"})

    print("\n=== Exception isolation ===")
    eb = EventBus()
    # Silence the default stderr output during this test.
    import io, contextlib
    err_buf = io.StringIO()
    calls = []
    eb.subscribe("e", lambda: calls.append("before"))
    eb.subscribe("e", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    eb.subscribe("e", lambda: calls.append("after"))
    with contextlib.redirect_stderr(err_buf):
        n = eb.publish("e")
    check("all callbacks attempted", n, 3)
    check("before ran", "before" in calls, True)
    check("after ran despite earlier exception", "after" in calls, True)
    check("error logged to stderr", "RuntimeError" in err_buf.getvalue(), True)

    print("\n=== Custom error hook ===")
    eb = EventBus()
    hook_calls = []
    eb.on_callback_error = lambda ev, cb, exc: hook_calls.append((ev, type(exc).__name__))
    eb.subscribe("e", lambda: (_ for _ in ()).throw(ValueError("x")))
    eb.publish("e")
    check("custom hook invoked", hook_calls, [("e", "ValueError")])

    print("\n=== Clear ===")
    eb = EventBus()
    eb.subscribe("a", lambda: None)
    eb.subscribe("b", lambda: None)
    eb.subscribe("b", lambda: None)
    check("clear single event", eb.clear("a"), 1)
    check("b still has 2", eb.subscriber_count("b"), 2)
    check("clear all", eb.clear(), 2)
    check("empty after clear all", eb.events(), [])

    print("\n=== Empty / unknown events ===")
    eb = EventBus()
    check("publish unknown event", eb.publish("nope"), 0)
    check("subscriber_count unknown", eb.subscriber_count("nope"), 0)

    print("\n=== STANDARD_EVENTS catalog ===")
    check("has activity.added", "activity.added" in STANDARD_EVENTS, True)
    check("has timer.tick", "timer.tick" in STANDARD_EVENTS, True)
    check("has ui.toast", "ui.toast" in STANDARD_EVENTS, True)
    check("catalog has 29 events", len(STANDARD_EVENTS), 29)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
