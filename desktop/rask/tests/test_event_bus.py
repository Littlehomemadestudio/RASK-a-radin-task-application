"""
rask.tests.test_event_bus
=========================

Unit tests for :mod:`rask.core.event_bus`.

Covers:

  • ``subscribe()`` + ``publish()`` basic flow
  • Multiple subscribers (order preserved, count returned)
  • ``unsubscribe()`` (returns True/False appropriately)
  • ``clear()`` (single-event + whole-bus)
  • Publish with positional + keyword arguments
  • Exception in one subscriber does NOT break subsequent subscribers
  • Custom ``on_callback_error`` hook receives the exception
  • Thread safety: parallel subscribe / publish from multiple threads
  • Edge cases: empty event name, non-callable callback, re-entrant
    publish from inside a callback
  • ``STANDARD_EVENTS`` catalog is non-empty and contains the
    well-known event names
"""
from __future__ import annotations

import threading
import time
import unittest
from typing import Any, List, Tuple

from rask.core.event_bus import EventBus, STANDARD_EVENTS, bus


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestSubscribePublish(unittest.TestCase):
    """Basic subscribe / publish flow."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_subscribe_and_publish_single_arg(self) -> None:
        received: List[Any] = []
        self.eb.subscribe("test.event", lambda x: received.append(x))
        n = self.eb.publish("test.event", 42)
        self.assertEqual(n, 1)
        self.assertEqual(received, [42])

    def test_publish_returns_subscriber_count(self) -> None:
        self.eb.subscribe("e", lambda: None)
        self.eb.subscribe("e", lambda: None)
        self.assertEqual(self.eb.publish("e"), 2)

    def test_publish_unknown_event_returns_zero(self) -> None:
        self.assertEqual(self.eb.publish("does.not.exist"), 0)

    def test_publish_with_no_args(self) -> None:
        called: List[bool] = []
        self.eb.subscribe("ping", lambda: called.append(True))
        self.eb.publish("ping")
        self.assertEqual(called, [True])

    def test_publish_with_multiple_positional_args(self) -> None:
        received: List[Tuple[Any, ...]] = []
        self.eb.subscribe("multi", lambda *a: received.append(a))
        self.eb.publish("multi", 1, "two", 3.0)
        self.assertEqual(received, [(1, "two", 3.0)])

    def test_publish_with_kwargs(self) -> None:
        captured: dict = {}
        self.eb.subscribe("kw", lambda **kw: captured.update(kw))
        self.eb.publish("kw", a=1, b="two")
        self.assertEqual(captured, {"a": 1, "b": "two"})

    def test_publish_with_args_and_kwargs(self) -> None:
        captured: List[Tuple[Any, ...]] = []
        kwargs_captured: dict = {}
        self.eb.subscribe(
            "mixed",
            lambda *a, **kw: (captured.append(a), kwargs_captured.update(kw)),
        )
        self.eb.publish("mixed", 1, 2, x=10, y=20)
        self.assertEqual(captured, [(1, 2)])
        self.assertEqual(kwargs_captured, {"x": 10, "y": 20})

    def test_subscribe_returns_callback(self) -> None:
        cb = lambda x: None  # noqa: E731
        ret = self.eb.subscribe("e", cb)
        self.assertIs(ret, cb)


class TestMultipleSubscribers(unittest.TestCase):
    """Multiple subscribers are called in order."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_subscribers_called_in_order(self) -> None:
        order: List[str] = []
        self.eb.subscribe("e", lambda: order.append("a"))
        self.eb.subscribe("e", lambda: order.append("b"))
        self.eb.subscribe("e", lambda: order.append("c"))
        self.eb.publish("e")
        self.assertEqual(order, ["a", "b", "c"])

    def test_same_callback_subscribed_twice_called_twice(self) -> None:
        calls: List[int] = []
        cb = lambda: calls.append(1)  # noqa: E731
        self.eb.subscribe("e", cb)
        self.eb.subscribe("e", cb)
        self.eb.publish("e")
        self.assertEqual(calls, [1, 1])

    def test_subscriber_count(self) -> None:
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("b", lambda: None)
        self.assertEqual(self.eb.subscriber_count("a"), 2)
        self.assertEqual(self.eb.subscriber_count("b"), 1)
        self.assertEqual(self.eb.subscriber_count("c"), 0)


class TestUnsubscribe(unittest.TestCase):
    """Unsubscribe behavior."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_unsubscribe_removes_callback(self) -> None:
        calls: List[int] = []
        cb = lambda: calls.append(1)  # noqa: E731
        self.eb.subscribe("e", cb)
        self.assertTrue(self.eb.unsubscribe("e", cb))
        self.eb.publish("e")
        self.assertEqual(calls, [])

    def test_unsubscribe_only_removes_first_occurrence(self) -> None:
        calls: List[int] = []
        cb = lambda: calls.append(1)  # noqa: E731
        self.eb.subscribe("e", cb)
        self.eb.subscribe("e", cb)
        self.assertTrue(self.eb.unsubscribe("e", cb))
        self.eb.publish("e")
        self.assertEqual(calls, [1])

    def test_unsubscribe_missing_returns_false(self) -> None:
        self.assertFalse(self.eb.unsubscribe("e", lambda: None))

    def test_unsubscribe_from_empty_event_returns_false(self) -> None:
        self.assertFalse(self.eb.unsubscribe("nope", lambda: None))

    def test_unsubscribe_after_clear_returns_false(self) -> None:
        cb = lambda: None  # noqa: E731
        self.eb.subscribe("e", cb)
        self.eb.clear()
        self.assertFalse(self.eb.unsubscribe("e", cb))


class TestClear(unittest.TestCase):
    """clear() behavior."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_clear_single_event(self) -> None:
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("b", lambda: None)
        removed = self.eb.clear("a")
        self.assertEqual(removed, 2)
        self.assertEqual(self.eb.subscriber_count("a"), 0)
        self.assertEqual(self.eb.subscriber_count("b"), 1)

    def test_clear_all(self) -> None:
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("b", lambda: None)
        self.eb.subscribe("b", lambda: None)
        removed = self.eb.clear()
        self.assertEqual(removed, 3)
        self.assertEqual(self.eb.events(), [])

    def test_clear_nonexistent_returns_zero(self) -> None:
        self.assertEqual(self.eb.clear("nope"), 0)

    def test_clear_empty_bus_returns_zero(self) -> None:
        self.assertEqual(self.eb.clear(), 0)

    def test_events_lists_active_event_names(self) -> None:
        self.eb.subscribe("alpha", lambda: None)
        self.eb.subscribe("beta", lambda: None)
        events = self.eb.events()
        self.assertEqual(events, ["alpha", "beta"])


class TestExceptionIsolation(unittest.TestCase):
    """One callback's exception does not break others."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_exception_does_not_break_subsequent(self) -> None:
        calls: List[str] = []
        self.eb.subscribe("e", lambda: calls.append("before"))
        self.eb.subscribe("e", self._raise)
        self.eb.subscribe("e", lambda: calls.append("after"))
        n = self.eb.publish("e")
        self.assertEqual(n, 3)
        self.assertIn("before", calls)
        self.assertIn("after", calls)

    def test_exception_does_not_break_prior(self) -> None:
        calls: List[str] = []
        self.eb.subscribe("e", self._raise)
        self.eb.subscribe("e", lambda: calls.append("after"))
        self.eb.publish("e")
        self.assertEqual(calls, ["after"])

    def test_custom_error_hook_invoked(self) -> None:
        hook_calls: List[Tuple[str, str]] = []
        self.eb.on_callback_error = lambda ev, cb, exc: hook_calls.append(
            (ev, type(exc).__name__))
        self.eb.subscribe("e", self._raise)
        self.eb.publish("e")
        self.assertEqual(hook_calls, [("e", "RuntimeError")])

    def test_custom_error_hook_suppresses_stderr(self) -> None:
        # If the hook itself succeeds, the default stderr fallback
        # should not run.
        hook_calls: List[str] = []
        self.eb.on_callback_error = lambda ev, cb, exc: hook_calls.append("ok")
        self.eb.subscribe("e", self._raise)
        self.eb.publish("e")
        self.assertEqual(hook_calls, ["ok"])

    @staticmethod
    def _raise() -> None:
        raise RuntimeError("boom")


class TestReEntrantPublish(unittest.TestCase):
    """A callback can publish another (or the same) event."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_callback_publishes_other_event(self) -> None:
        log: List[str] = []

        def on_first() -> None:
            log.append("first")
            self.eb.publish("second")

        self.eb.subscribe("first", on_first)
        self.eb.subscribe("second", lambda: log.append("second"))
        self.eb.publish("first")
        self.assertEqual(log, ["first", "second"])

    def test_callback_publishes_same_event_with_depth_guard(self) -> None:
        # Use a counter to stop the recursion.
        state = {"n": 0}
        log: List[int] = []

        def on_e() -> None:
            state["n"] += 1
            log.append(state["n"])
            if state["n"] < 3:
                self.eb.publish("e")

        self.eb.subscribe("e", on_e)
        self.eb.publish("e")
        self.assertEqual(log, [1, 2, 3])


class TestThreadSafety(unittest.TestCase):
    """Concurrent subscribe / publish from multiple threads."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_concurrent_publish_and_subscribe(self) -> None:
        # 5 threads each publishing 200 events; one subscriber
        # increments a counter under a lock.
        counter = {"n": 0}
        lock = threading.Lock()

        def cb() -> None:
            with lock:
                counter["n"] += 1

        self.eb.subscribe("tick", cb)

        def worker() -> None:
            for _ in range(200):
                self.eb.publish("tick")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(counter["n"], 1000)

    def test_concurrent_subscribe_different_callbacks(self) -> None:
        # 10 threads each subscribe a unique callback to the same event.
        received: List[int] = []
        lock = threading.Lock()

        def make_cb(i: int):
            def cb() -> None:
                with lock:
                    received.append(i)
            return cb

        def worker(i: int) -> None:
            self.eb.subscribe("e", make_cb(i))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(self.eb.subscriber_count("e"), 10)
        self.eb.publish("e")
        self.assertEqual(sorted(received), list(range(10)))

    def test_concurrent_unsubscribe_during_publish(self) -> None:
        # Subscribe 50 callbacks, then have one thread publish while
        # another unsubscribes.  Should not raise.
        callbacks = [lambda: None for _ in range(50)]
        for cb in callbacks:
            self.eb.subscribe("e", cb)

        errors: List[BaseException] = []

        def publisher() -> None:
            try:
                for _ in range(100):
                    self.eb.publish("e")
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def unsuber() -> None:
            try:
                for cb in callbacks:
                    self.eb.unsubscribe("e", cb)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=publisher)
        t2 = threading.Thread(target=unsuber)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(errors, [])


class TestEdgeCases(unittest.TestCase):
    """Edge cases and validation."""

    def setUp(self) -> None:
        self.eb = EventBus()

    def test_subscribe_empty_event_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.eb.subscribe("", lambda: None)

    def test_subscribe_non_callable_raises(self) -> None:
        with self.assertRaises(TypeError):
            self.eb.subscribe("e", "not callable")  # type: ignore[arg-type]

    def test_publish_empty_event_returns_zero(self) -> None:
        self.assertEqual(self.eb.publish(""), 0)

    def test_publish_non_string_event_returns_zero(self) -> None:
        self.assertEqual(self.eb.publish(None), 0)  # type: ignore[arg-type]
        self.assertEqual(self.eb.publish(123), 0)  # type: ignore[arg-type]

    def test_unsubscribe_non_string_event_returns_false(self) -> None:
        self.assertFalse(self.eb.unsubscribe(None, lambda: None))  # type: ignore[arg-type]

    def test_repr_shows_counts(self) -> None:
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("a", lambda: None)
        self.eb.subscribe("b", lambda: None)
        r = repr(self.eb)
        self.assertIn("events=2", r)
        self.assertIn("subscribers=3", r)


class TestStandardEvents(unittest.TestCase):
    """The STANDARD_EVENTS catalog."""

    def test_catalog_is_non_empty(self) -> None:
        self.assertGreater(len(STANDARD_EVENTS), 10)

    def test_catalog_contains_known_events(self) -> None:
        known = [
            "activity.added", "activity.updated", "activity.deleted",
            "goal.added", "goal.progress", "streak.incremented",
            "streak.reset", "badge.unlocked", "timer.started",
            "timer.stopped", "timer.tick", "settings.changed",
            "language.changed", "theme.changed", "backup.created",
            "backup.restored", "reminder.triggered", "reminder.dismissed",
            "reminder.snoozed", "ui.toast", "data.imported", "data.cleared",
        ]
        for ev in known:
            self.assertIn(ev, STANDARD_EVENTS)

    def test_all_entries_are_strings(self) -> None:
        for ev in STANDARD_EVENTS:
            self.assertIsInstance(ev, str)
            self.assertTrue(ev)

    def test_no_duplicates(self) -> None:
        self.assertEqual(len(STANDARD_EVENTS), len(set(STANDARD_EVENTS)))


class TestGlobalBus(unittest.TestCase):
    """The module-level ``bus`` singleton."""

    def setUp(self) -> None:
        # Clean state before each test.
        bus.clear()

    def tearDown(self) -> None:
        bus.clear()

    def test_bus_is_event_bus_instance(self) -> None:
        self.assertIsInstance(bus, EventBus)

    def test_bus_subscribe_and_publish(self) -> None:
        received: List[Any] = []
        bus.subscribe("test.bus", lambda x: received.append(x))
        bus.publish("test.bus", "hello")
        self.assertEqual(received, ["hello"])

    def test_bus_clear_resets_state(self) -> None:
        bus.subscribe("e", lambda: None)
        bus.subscribe("e", lambda: None)
        self.assertEqual(bus.subscriber_count("e"), 2)
        bus.clear()
        self.assertEqual(bus.subscriber_count("e"), 0)


if __name__ == "__main__":
    unittest.main()
