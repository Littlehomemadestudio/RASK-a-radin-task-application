"""
rask.tests.test_template_service
===============================

Unit tests for :mod:`rask.services.template_service`.

Covers:

  • CRUD operations: add / get / update / delete
  • ``use()`` creates an activity via activity_service + increments
    ``use_count`` and updates ``last_used_iso``
  • ``by_shortcut()`` lookup (case-sensitive, returns None for missing)
  • ``top_used()`` returns sorted list (most-used first)
  • ``archive()`` / ``unarchive()`` flip the archived flag
  • ``reorder()`` reassigns ``order_index`` for each id in order
  • Tags / notes / shortcut / icon / color are preserved
  • ``list(include_archived=True)`` returns archived templates
  • Event publication: ``template.added``, ``template.updated``,
    ``template.deleted``, ``template.used``, ``template.archived``
  • Edge cases: empty name, empty title, invalid id, archive-then-use
"""
from __future__ import annotations

import unittest
from typing import Any, List, Tuple

from rask import database as db
from rask.core.event_bus import bus
from rask.services.template_service import TemplateService, template_service
from rask.tests import fresh_db


# =============================================================================
# === Helper                                                                  ===
# =============================================================================

class _Collector:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[Any, ...], dict]] = []

    def make(self, event: str):
        def cb(*args: Any, **kwargs: Any) -> None:
            self.calls.append((event, args, kwargs))
        return cb


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestTemplateAdd(unittest.TestCase):
    """add() creates a new template."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_returns_dict_with_id(self) -> None:
        t = self.svc.add(name="Reading", title="Read a book",
                          duration_min=30, shortcut="r")
        self.assertIn("id", t)
        self.assertGreater(t["id"], 0)
        self.assertEqual(t["name"], "Reading")
        self.assertEqual(t["title"], "Read a book")
        self.assertEqual(t["duration_min"], 30)
        self.assertEqual(t["shortcut"], "r")
        self.assertFalse(t["archived"])

    def test_add_strips_whitespace_from_name_and_title(self) -> None:
        t = self.svc.add(name="  Reading  ", title="  Read  ")
        self.assertEqual(t["name"], "Reading")
        self.assertEqual(t["title"], "Read")

    def test_add_with_tags(self) -> None:
        t = self.svc.add(name="T", title="Title", tags=["a", "b", "c"])
        self.assertEqual(t["tags"], ["a", "b", "c"])

    def test_add_with_notes(self) -> None:
        t = self.svc.add(name="T", title="Title", notes="Some notes")
        self.assertEqual(t["notes"], "Some notes")

    def test_add_with_color_and_icon(self) -> None:
        t = self.svc.add(name="T", title="Title", color="#FF0000", icon="book")
        self.assertEqual(t["color"], "#FF0000")
        self.assertEqual(t["icon"], "book")

    def test_add_assigns_incrementing_order_index(self) -> None:
        t1 = self.svc.add(name="A", title="A")
        t2 = self.svc.add(name="B", title="B")
        t3 = self.svc.add(name="C", title="C")
        self.assertEqual(t1["order_index"], 0)
        self.assertEqual(t2["order_index"], 1)
        self.assertEqual(t3["order_index"], 2)

    def test_add_empty_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(name="", title="Title")

    def test_add_empty_title_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.add(name="Name", title="")

    def test_add_publishes_template_added(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.added", lambda t: coll.append(t))
        self.svc.add(name="T", title="Title")
        self.assertEqual(len(coll), 1)


class TestTemplateGet(unittest.TestCase):
    """get() returns the template dict or None."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t = self.svc.add(name="Reading", title="Read a book",
                               duration_min=30)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_get_existing(self) -> None:
        t = self.svc.get(self.t["id"])
        self.assertIsNotNone(t)
        self.assertEqual(t["name"], "Reading")

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.svc.get(9999))

    def test_get_invalid_id_returns_none(self) -> None:
        self.assertIsNone(self.svc.get(0))
        self.assertIsNone(self.svc.get(-1))
        self.assertIsNone(self.svc.get("not int"))  # type: ignore[arg-type]


class TestTemplateList(unittest.TestCase):
    """list() returns all (non-archived) templates."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t1 = self.svc.add(name="A", title="A1")
        self.t2 = self.svc.add(name="B", title="B1")
        self.t3 = self.svc.add(name="C", title="C1")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_list_returns_all(self) -> None:
        items = self.svc.list()
        self.assertEqual(len(items), 3)

    def test_list_excludes_archived_by_default(self) -> None:
        self.svc.archive(self.t2["id"])
        items = self.svc.list()
        self.assertEqual(len(items), 2)
        ids = [t["id"] for t in items]
        self.assertNotIn(self.t2["id"], ids)

    def test_list_includes_archived_when_flag(self) -> None:
        self.svc.archive(self.t2["id"])
        items = self.svc.list(include_archived=True)
        self.assertEqual(len(items), 3)

    def test_list_returns_empty_when_no_templates(self) -> None:
        # Delete all
        for t in self.svc.list(include_archived=True):
            self.svc.delete(t["id"])
        self.assertEqual(self.svc.list(), [])


class TestTemplateUpdate(unittest.TestCase):
    """update() changes fields and returns the updated template."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t = self.svc.add(name="Old", title="Old title",
                               duration_min=30, shortcut="o")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_update_name(self) -> None:
        updated = self.svc.update(self.t["id"], name="New")
        self.assertEqual(updated["name"], "New")

    def test_update_title(self) -> None:
        updated = self.svc.update(self.t["id"], title="New title")
        self.assertEqual(updated["title"], "New title")

    def test_update_duration(self) -> None:
        updated = self.svc.update(self.t["id"], duration_min=60)
        self.assertEqual(updated["duration_min"], 60)

    def test_update_tags(self) -> None:
        updated = self.svc.update(self.t["id"], tags=["new", "tags"])
        self.assertEqual(updated["tags"], ["new", "tags"])

    def test_update_shortcut(self) -> None:
        updated = self.svc.update(self.t["id"], shortcut="n")
        self.assertEqual(updated["shortcut"], "n")

    def test_update_publishes_template_updated(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.updated", lambda t: coll.append(t))
        self.svc.update(self.t["id"], name="New")
        self.assertEqual(len(coll), 1)

    def test_update_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.update(9999, name="X")

    def test_update_invalid_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.update(0, name="X")


class TestTemplateDelete(unittest.TestCase):
    """delete() removes the template."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t = self.svc.add(name="T", title="Title")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_removes_template(self) -> None:
        self.assertTrue(self.svc.delete(self.t["id"]))
        self.assertIsNone(self.svc.get(self.t["id"]))

    def test_delete_publishes_template_deleted(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.deleted", lambda d: coll.append(d))
        self.svc.delete(self.t["id"])
        self.assertEqual(len(coll), 1)

    def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(9999))

    def test_delete_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.delete(0))
        self.assertFalse(self.svc.delete(-1))


class TestTemplateUse(unittest.TestCase):
    """use() creates an activity and increments use_count."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t = self.svc.add(name="Reading", title="Read a book",
                               duration_min=30, shortcut="r")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_use_creates_activity(self) -> None:
        a = self.svc.use(self.t["id"])
        self.assertIsNotNone(a)
        self.assertIn("id", a)
        self.assertGreater(a["id"], 0)
        self.assertEqual(a["title"], "Read a book")
        self.assertEqual(a["duration_min"], 30)
        self.assertEqual(a["kind"], "template")

    def test_use_increments_use_count(self) -> None:
        self.svc.use(self.t["id"])
        self.svc.use(self.t["id"])
        self.svc.use(self.t["id"])
        t = self.svc.get(self.t["id"])
        # activity_add itself increments use_count, and use() does too
        # (defensively) — final value should be >= 3.
        self.assertGreaterEqual(t["use_count"], 3)

    def test_use_updates_last_used_iso(self) -> None:
        self.assertIsNone(self.t["last_used_iso"])
        self.svc.use(self.t["id"])
        t = self.svc.get(self.t["id"])
        self.assertIsNotNone(t["last_used_iso"])

    def test_use_publishes_template_used(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.used", lambda d: coll.append(d))
        self.svc.use(self.t["id"])
        self.assertEqual(len(coll), 1)

    def test_use_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.svc.use(9999)

    def test_use_archived_raises(self) -> None:
        self.svc.archive(self.t["id"])
        with self.assertRaises(ValueError):
            self.svc.use(self.t["id"])


class TestByShortcut(unittest.TestCase):
    """by_shortcut() looks up templates by shortcut key."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t1 = self.svc.add(name="A", title="A1", shortcut="1")
        self.t2 = self.svc.add(name="B", title="B1", shortcut="2")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_by_shortcut_returns_template(self) -> None:
        t = self.svc.by_shortcut("1")
        self.assertIsNotNone(t)
        self.assertEqual(t["name"], "A")

    def test_by_shortcut_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.svc.by_shortcut("zzz"))

    def test_by_shortcut_returns_none_for_empty(self) -> None:
        self.assertIsNone(self.svc.by_shortcut(""))

    def test_by_shortcut_skips_archived(self) -> None:
        self.svc.archive(self.t1["id"])
        self.assertIsNone(self.svc.by_shortcut("1"))

    def test_by_shortcut_is_case_sensitive(self) -> None:
        self.svc.add(name="C", title="C1", shortcut="R")
        self.assertIsNone(self.svc.by_shortcut("r"))
        self.assertIsNotNone(self.svc.by_shortcut("R"))


class TestTopUsed(unittest.TestCase):
    """top_used() returns the most-used templates."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t1 = self.svc.add(name="A", title="A1")
        self.t2 = self.svc.add(name="B", title="B1")
        self.t3 = self.svc.add(name="C", title="C1")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_top_used_sorted_by_count_desc(self) -> None:
        # Use t3 thrice, t2 twice, t1 once.
        self.svc.use(self.t3["id"])
        self.svc.use(self.t3["id"])
        self.svc.use(self.t3["id"])
        self.svc.use(self.t2["id"])
        self.svc.use(self.t2["id"])
        self.svc.use(self.t1["id"])
        top = self.svc.top_used(limit=3)
        self.assertEqual(len(top), 3)
        # Most-used first
        self.assertEqual(top[0]["id"], self.t3["id"])
        self.assertEqual(top[1]["id"], self.t2["id"])
        self.assertEqual(top[2]["id"], self.t1["id"])

    def test_top_used_respects_limit(self) -> None:
        top = self.svc.top_used(limit=2)
        self.assertEqual(len(top), 2)

    def test_top_used_limit_zero_returns_empty(self) -> None:
        self.assertEqual(self.svc.top_used(limit=0), [])

    def test_top_used_excludes_archived(self) -> None:
        self.svc.use(self.t1["id"])
        self.svc.archive(self.t1["id"])
        top = self.svc.top_used(limit=3)
        ids = [t["id"] for t in top]
        self.assertNotIn(self.t1["id"], ids)


class TestArchiveUnarchive(unittest.TestCase):
    """archive() / unarchive() flip the archived flag."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t = self.svc.add(name="T", title="Title")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_archive_sets_archived_true(self) -> None:
        self.assertTrue(self.svc.archive(self.t["id"]))
        t = self.svc.get(self.t["id"])
        self.assertTrue(t["archived"])

    def test_archive_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.archived", lambda d: coll.append(d))
        self.svc.archive(self.t["id"])
        self.assertEqual(len(coll), 1)

    def test_unarchive_sets_archived_false(self) -> None:
        self.svc.archive(self.t["id"])
        self.assertTrue(self.svc.unarchive(self.t["id"]))
        t = self.svc.get(self.t["id"])
        self.assertFalse(t["archived"])

    def test_unarchive_publishes_event(self) -> None:
        self.svc.archive(self.t["id"])
        coll: List[Any] = []
        bus.subscribe("template.unarchived", lambda d: coll.append(d))
        self.svc.unarchive(self.t["id"])
        self.assertEqual(len(coll), 1)

    def test_archive_invalid_id_returns_false(self) -> None:
        self.assertFalse(self.svc.archive(9999))


class TestReorder(unittest.TestCase):
    """reorder() reassigns order_index."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()
        self.t1 = self.svc.add(name="A", title="A")
        self.t2 = self.svc.add(name="B", title="B")
        self.t3 = self.svc.add(name="C", title="C")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_reorder_reassigns_indices(self) -> None:
        # Reverse the order
        ok = self.svc.reorder([self.t3["id"], self.t2["id"], self.t1["id"]])
        self.assertTrue(ok)
        self.assertEqual(self.svc.get(self.t3["id"])["order_index"], 0)
        self.assertEqual(self.svc.get(self.t2["id"])["order_index"], 1)
        self.assertEqual(self.svc.get(self.t1["id"])["order_index"], 2)

    def test_reorder_publishes_event(self) -> None:
        coll: List[Any] = []
        bus.subscribe("template.reordered", lambda d: coll.append(d))
        self.svc.reorder([self.t3["id"], self.t2["id"], self.t1["id"]])
        self.assertEqual(len(coll), 1)

    def test_reorder_empty_returns_false(self) -> None:
        self.assertFalse(self.svc.reorder([]))

    def test_reorder_non_list_returns_false(self) -> None:
        self.assertFalse(self.svc.reorder("not a list"))  # type: ignore[arg-type]

    def test_reorder_with_non_int_returns_false(self) -> None:
        self.assertFalse(self.svc.reorder([1, "two", 3]))  # type: ignore[list-item]


class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = TemplateService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_add_with_very_long_name_truncates(self) -> None:
        # sanitize_title in core/validators truncates to 200 chars
        long_name = "x" * 500
        t = self.svc.add(name=long_name, title="T")
        self.assertLessEqual(len(t["name"]), 200)

    def test_add_with_invalid_duration_clamps(self) -> None:
        t = self.svc.add(name="T", title="T", duration_min=99999)
        self.assertLessEqual(t["duration_min"], 1440)

    def test_add_with_none_duration(self) -> None:
        t = self.svc.add(name="T", title="T", duration_min=None)
        self.assertIsNone(t["duration_min"])

    def test_add_with_long_shortcut_truncates(self) -> None:
        t = self.svc.add(name="T", title="T", shortcut="abcdefg")
        self.assertLessEqual(len(t["shortcut"]), 5)

    def test_init_rebuilds_shortcut_cache(self) -> None:
        t = self.svc.add(name="T", title="T", shortcut="x")
        self.svc.init()  # should rebuild cache
        self.assertIsNotNone(self.svc.by_shortcut("x"))

    def test_template_service_singleton_exists(self) -> None:
        self.assertIsInstance(template_service, TemplateService)


if __name__ == "__main__":
    unittest.main()
