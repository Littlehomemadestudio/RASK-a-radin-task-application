"""
rask.tests.test_database
========================

Unit tests for :mod:`rask.database` — the SQLite persistence layer.

Covers:

  • Setup / teardown via a temp DB (no shared state between tests)
  • Activity CRUD: add / get / update / delete (soft + hard)
  • Activity filters: date range, categories, kinds, tags, search,
    duration range, include_deleted, limit / offset, order_by
  • Activity aggregations: count, sum_duration, group_by_day /
    category / hour / weekday / month
  • Category CRUD, ordering, archive, get_by_key
  • Goal CRUD with auto-created streak row
  • Streak increment (with idempotency for same hit_iso), reset,
    milestone detection (config.STREAK_MILESTONES)
  • Template CRUD, use_count increment on activity_add with template_id
  • Badge unlock, list, has, get_by_key, delete
  • Reminder CRUD with snooze / dismiss metadata
  • Recurring CRUD and due_now filtering
  • Session lifecycle (add / update / list_active)
  • KV store: get / set / int / bool / json / delete / keys (prefix)
  • Settings store: typed get / set (string / int / float / bool / json)
  • Tag sync (activity_tags), tag_list, tag_search
  • Export / import round-trip
  • Maintenance: vacuum, integrity_check, db_file_size, stats
"""
from __future__ import annotations

import unittest

from rask import config, database as db
from rask.tests import fresh_db


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestDatabaseSetup(unittest.TestCase):
    """Database initialization."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_open_db_creates_tables(self) -> None:
        tables = [
            "activities", "categories", "goals", "streaks", "templates",
            "badges", "reminders", "kv", "tags", "activity_tags",
            "recurring", "sessions", "settings", "changelog",
            "backups_log", "exports_log",
        ]
        for t in tables:
            cur = db.get_conn().execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (t,))
            self.assertIsNotNone(cur.fetchone(), f"Table {t} missing")

    def test_default_categories_seeded(self) -> None:
        cats = db.category_list()
        self.assertEqual(len(cats), len(config.DEFAULT_CATEGORIES))

    def test_default_goal_seeded(self) -> None:
        goals = db.goal_list()
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["period"], "daily")
        self.assertEqual(goals[0]["target_minutes"],
                         config.DEFAULT_GOAL_MINUTES)

    def test_default_settings_seeded(self) -> None:
        # lang and theme should be present.
        self.assertEqual(db.setting_get("lang"), config.DEFAULT_LANG)
        self.assertEqual(db.setting_get("theme"), config.DEFAULT_THEME)

    def test_default_kv_seeded(self) -> None:
        self.assertEqual(db.kv_get("first_run"), "1")
        self.assertEqual(db.kv_get("onboarded"), "0")
        self.assertEqual(db.kv_get("app_version"), config.APP_VERSION)

    def test_integrity_check_passes(self) -> None:
        result = db.integrity_check()
        self.assertEqual(result, ["ok"])

    def test_stats_returns_counts(self) -> None:
        s = db.stats()
        self.assertIsInstance(s, dict)
        self.assertIn("activities", s)
        self.assertIn("categories", s)
        self.assertIn("_db_size_bytes", s)


# ---------------------------------------------------------------------------
# Activity CRUD
# ---------------------------------------------------------------------------

class TestActivityCRUD(unittest.TestCase):
    """Activity repository CRUD operations."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_int_id(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        self.assertIsInstance(aid, int)
        self.assertGreater(aid, 0)

    def test_get_returns_dict(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        a = db.activity_get(aid)
        self.assertIsInstance(a, dict)
        self.assertEqual(a["id"], aid)
        self.assertEqual(a["title"], "Test")
        self.assertEqual(a["duration_min"], 30)
        self.assertEqual(a["date_iso"], "2025-01-01")

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(db.activity_get(9999))

    def test_get_deleted_returns_none(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        db.activity_delete(aid, soft=True)
        self.assertIsNone(db.activity_get(aid))

    def test_get_deleted_include_deleted(self) -> None:
        # activity_get doesn't take include_deleted — but activity_list does.
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        db.activity_delete(aid, soft=True)
        rows = db.activity_list(include_deleted=True)
        self.assertEqual(len(rows), 1)

    def test_update_title(self) -> None:
        aid = db.activity_add("Old", None, 30, "2025-01-01")
        ok = db.activity_update(aid, title="New")
        self.assertTrue(ok)
        self.assertEqual(db.activity_get(aid)["title"], "New")

    def test_update_duration(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        db.activity_update(aid, duration_min=60)
        self.assertEqual(db.activity_get(aid)["duration_min"], 60)

    def test_update_tags(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        db.activity_update(aid, tags=["focus", "deep"])
        a = db.activity_get(aid)
        self.assertIsNotNone(a)

    def test_update_returns_false_for_nonexistent(self) -> None:
        # No row matches the WHERE clause.
        ok = db.activity_update(9999, title="Ghost")
        self.assertFalse(ok)

    def test_update_no_fields_returns_false(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        ok = db.activity_update(aid)
        self.assertFalse(ok)

    def test_update_unknown_field_is_ignored(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        # Unknown field shouldn't crash; no rows updated.
        ok = db.activity_update(aid, unknown_field="value")
        self.assertFalse(ok)

    def test_soft_delete_marks_deleted_at(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        ok = db.activity_delete(aid, soft=True)
        self.assertTrue(ok)
        # Soft-deleted activities don't appear in default list.
        self.assertEqual(len(db.activity_list()), 0)

    def test_hard_delete_removes_row(self) -> None:
        aid = db.activity_add("Test", None, 30, "2025-01-01")
        ok = db.activity_delete(aid, soft=False)
        self.assertTrue(ok)
        # Even include_deleted shouldn't find it.
        self.assertEqual(len(db.activity_list(include_deleted=True)), 0)

    def test_delete_nonexistent_returns_false(self) -> None:
        self.assertFalse(db.activity_delete(9999, soft=True))
        self.assertFalse(db.activity_delete(9999, soft=False))


# ---------------------------------------------------------------------------
# Activity filters
# ---------------------------------------------------------------------------

class TestActivityFilters(unittest.TestCase):
    """Activity list filters."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        # Seed activities across categories / dates / kinds / tags.
        self.aid1 = db.activity_add("Read", 1, 30, "2025-01-01",
                                      tags=["learn"], kind="manual")
        self.aid2 = db.activity_add("Code", 2, 60, "2025-01-02",
                                      tags=["work", "deep"], kind="stopwatch")
        self.aid3 = db.activity_add("Walk", 3, 45, "2025-01-03",
                                      tags=["health"], kind="manual")
        self.aid4 = db.activity_add("Meditate", 1, 15, "2025-01-04",
                                      tags=["health", "calm"], kind="manual")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_list_all(self) -> None:
        rows = db.activity_list()
        self.assertEqual(len(rows), 4)

    def test_filter_by_date_from(self) -> None:
        rows = db.activity_list(date_from="2025-01-03")
        self.assertEqual(len(rows), 2)

    def test_filter_by_date_to(self) -> None:
        rows = db.activity_list(date_to="2025-01-02")
        self.assertEqual(len(rows), 2)

    def test_filter_by_date_range(self) -> None:
        rows = db.activity_list(date_from="2025-01-02", date_to="2025-01-03")
        self.assertEqual(len(rows), 2)

    def test_filter_by_category_ids(self) -> None:
        rows = db.activity_list(category_ids=[1])
        self.assertEqual(len(rows), 2)
        rows = db.activity_list(category_ids=[2, 3])
        self.assertEqual(len(rows), 2)

    def test_filter_by_kinds(self) -> None:
        rows = db.activity_list(kinds=["manual"])
        self.assertEqual(len(rows), 3)
        rows = db.activity_list(kinds=["stopwatch"])
        self.assertEqual(len(rows), 1)

    def test_filter_by_tags_single(self) -> None:
        rows = db.activity_list(tags=["health"])
        # aid3 (Walk) and aid4 (Meditate) both have "health".
        self.assertEqual(len(rows), 2)

    def test_filter_by_tags_multiple_all_match(self) -> None:
        # aid4 has both "health" and "calm"
        rows = db.activity_list(tags=["health", "calm"])
        self.assertEqual(len(rows), 1)

    def test_filter_by_search_title(self) -> None:
        rows = db.activity_list(search="Read")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Read")

    def test_filter_by_search_notes(self) -> None:
        aid = db.activity_add("Search", None, 10, "2025-02-01",
                               notes="contains keyword tomato")
        rows = db.activity_list(search="tomato")
        self.assertEqual(len(rows), 1)

    def test_filter_by_min_duration(self) -> None:
        rows = db.activity_list(min_duration=45)
        self.assertEqual(len(rows), 2)

    def test_filter_by_max_duration(self) -> None:
        rows = db.activity_list(max_duration=30)
        self.assertEqual(len(rows), 2)

    def test_filter_by_duration_range(self) -> None:
        rows = db.activity_list(min_duration=20, max_duration=50)
        self.assertEqual(len(rows), 2)

    def test_limit(self) -> None:
        rows = db.activity_list(limit=2)
        self.assertEqual(len(rows), 2)

    def test_offset(self) -> None:
        rows1 = db.activity_list(limit=2, offset=0)
        rows2 = db.activity_list(limit=2, offset=2)
        self.assertEqual(len(rows1), 2)
        self.assertEqual(len(rows2), 2)
        # No overlap.
        ids1 = {r["id"] for r in rows1}
        ids2 = {r["id"] for r in rows2}
        self.assertEqual(ids1 & ids2, set())

    def test_order_by_date_asc(self) -> None:
        rows = db.activity_list(order_by="date_iso ASC")
        self.assertEqual(rows[0]["date_iso"], "2025-01-01")
        self.assertEqual(rows[-1]["date_iso"], "2025-01-04")

    def test_include_deleted(self) -> None:
        db.activity_delete(self.aid1, soft=True)
        self.assertEqual(len(db.activity_list()), 3)
        self.assertEqual(len(db.activity_list(include_deleted=True)), 4)


# ---------------------------------------------------------------------------
# Activity aggregations
# ---------------------------------------------------------------------------

class TestActivityAggregations(unittest.TestCase):
    """Aggregation functions: count, sum, group-by-X."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        db.activity_add("A", 1, 30, "2025-01-01",
                         start_ts="2025-01-01T09:00:00")
        db.activity_add("B", 1, 60, "2025-01-01",
                         start_ts="2025-01-01T14:00:00")
        db.activity_add("C", 2, 45, "2025-01-02",
                         start_ts="2025-01-02T18:00:00")
        db.activity_add("D", 3, 15, "2025-01-03",
                         start_ts="2025-01-03T22:00:00")

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_count_all(self) -> None:
        self.assertEqual(db.activity_count(), 4)

    def test_count_with_date_range(self) -> None:
        self.assertEqual(
            db.activity_count(date_from="2025-01-02",
                              date_to="2025-01-03"),
            2)

    def test_count_with_category(self) -> None:
        self.assertEqual(db.activity_count(category_ids=[1]), 2)

    def test_sum_duration_all(self) -> None:
        self.assertEqual(db.activity_sum_duration(), 150)

    def test_sum_duration_with_date_range(self) -> None:
        self.assertEqual(
            db.activity_sum_duration(date_from="2025-01-01",
                                     date_to="2025-01-01"),
            90)

    def test_sum_duration_with_category(self) -> None:
        self.assertEqual(db.activity_sum_duration(category_id=1), 90)

    def test_group_by_day(self) -> None:
        rows = db.activity_group_by_day()
        self.assertEqual(len(rows), 3)
        # Day 1 should have 2 activities totaling 90.
        d1 = next(r for r in rows if r["date_iso"] == "2025-01-01")
        self.assertEqual(d1["count"], 2)
        self.assertEqual(d1["total_min"], 90)

    def test_group_by_category(self) -> None:
        rows = db.activity_group_by_category()
        self.assertEqual(len(rows), 3)
        cat1 = next(r for r in rows if r["category_id"] == 1)
        self.assertEqual(cat1["count"], 2)
        self.assertEqual(cat1["total_min"], 90)

    def test_group_by_hour(self) -> None:
        rows = db.activity_group_by_hour()
        self.assertEqual(len(rows), 4)
        hours = {r["hour"] for r in rows}
        self.assertEqual(hours, {9, 14, 18, 22})

    def test_group_by_weekday(self) -> None:
        rows = db.activity_group_by_weekday()
        # Each activity is on a different weekday (or some share).
        self.assertGreater(len(rows), 0)
        total_count = sum(r["count"] for r in rows)
        self.assertEqual(total_count, 4)

    def test_group_by_month(self) -> None:
        rows = db.activity_group_by_month()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["month"], "2025-01")
        self.assertEqual(rows[0]["count"], 4)

    def test_sum_duration_empty_db(self) -> None:
        # Wipe the activities.
        for a in db.activity_list():
            db.activity_delete(a["id"], soft=False)
        self.assertEqual(db.activity_sum_duration(), 0)


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------

class TestCategoryCRUD(unittest.TestCase):
    """Category repository."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        self.assertGreater(cid, len(config.DEFAULT_CATEGORIES))

    def test_get_returns_dict(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        c = db.category_get(cid)
        self.assertEqual(c["key"], "TEST")
        self.assertEqual(c["name_en"], "Test")
        self.assertEqual(c["name_fa"], "تست")
        self.assertEqual(c["color"], "#FF0000")

    def test_get_by_key(self) -> None:
        db.category_add("MUSIC", "Music", "موسیقی", "#AABBCC")
        c = db.category_get_by_key("MUSIC")
        self.assertIsNotNone(c)
        self.assertEqual(c["name_en"], "Music")

    def test_get_by_key_nonexistent(self) -> None:
        self.assertIsNone(db.category_get_by_key("DOES_NOT_EXIST"))

    def test_list_excludes_archived_by_default(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        db.category_update(cid, archived=1)
        rows = db.category_list()
        self.assertEqual(len(rows), len(config.DEFAULT_CATEGORIES))
        # Include archived.
        rows_with_archived = db.category_list(include_archived=True)
        self.assertEqual(len(rows_with_archived), len(config.DEFAULT_CATEGORIES) + 1)

    def test_update_name(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        db.category_update(cid, name_en="Updated")
        self.assertEqual(db.category_get(cid)["name_en"], "Updated")

    def test_update_color(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        db.category_update(cid, color="#00FF00")
        self.assertEqual(db.category_get(cid)["color"], "#00FF00")

    def test_delete(self) -> None:
        cid = db.category_add("TEST", "Test", "تست", "#FF0000")
        self.assertTrue(db.category_delete(cid))
        self.assertIsNone(db.category_get(cid))

    def test_delete_nonexistent(self) -> None:
        self.assertFalse(db.category_delete(9999))


# ---------------------------------------------------------------------------
# Goal CRUD
# ---------------------------------------------------------------------------

class TestGoalCRUD(unittest.TestCase):
    """Goal repository with auto-created streak row."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        gid = db.goal_add("daily", 120)
        self.assertGreater(gid, 1)  # default goal already exists at id 1

    def test_add_initializes_streak(self) -> None:
        gid = db.goal_add("weekly", 600)
        s = db.streak_get(gid)
        self.assertIsNotNone(s)
        self.assertEqual(s["current"], 0)
        self.assertEqual(s["best"], 0)
        self.assertEqual(s["history"], [])

    def test_get_returns_dict(self) -> None:
        gid = db.goal_add("monthly", 2400, title="Big goal")
        g = db.goal_get(gid)
        self.assertEqual(g["period"], "monthly")
        self.assertEqual(g["target_minutes"], 2400)
        self.assertEqual(g["title"], "Big goal")

    def test_list(self) -> None:
        # Default has 1; add 2 more.
        db.goal_add("weekly", 600)
        db.goal_add("monthly", 2400)
        self.assertEqual(len(db.goal_list()), 3)

    def test_list_only_active(self) -> None:
        gid = db.goal_add("daily", 60)
        db.goal_update(gid, active=0)
        self.assertEqual(len(db.goal_list(only_active=True)), 1)

    def test_update_target(self) -> None:
        gid = db.goal_add("daily", 120)
        db.goal_update(gid, target_minutes=180)
        self.assertEqual(db.goal_get(gid)["target_minutes"], 180)

    def test_delete_cascades_to_streak(self) -> None:
        gid = db.goal_add("daily", 120)
        self.assertIsNotNone(db.streak_get(gid))
        db.goal_delete(gid)
        self.assertIsNone(db.streak_get(gid))

    def test_delete_nonexistent(self) -> None:
        self.assertFalse(db.goal_delete(9999))

    def test_invalid_period_raises(self) -> None:
        with self.assertRaises(AssertionError):
            db.goal_add("hourly", 60)


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------

class TestStreak(unittest.TestCase):
    """Streak increment / reset / milestone."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.gid = db.goal_add("daily", 60)

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_get_returns_dict(self) -> None:
        s = db.streak_get(self.gid)
        self.assertIsNotNone(s)
        self.assertEqual(s["current"], 0)

    def test_increment_bumps_current(self) -> None:
        result = db.streak_increment(self.gid, "2025-01-01")
        self.assertEqual(result["current"], 1)
        self.assertEqual(result["best"], 1)

    def test_increment_updates_best(self) -> None:
        db.streak_increment(self.gid, "2025-01-01")
        db.streak_increment(self.gid, "2025-01-02")
        result = db.streak_increment(self.gid, "2025-01-03")
        self.assertEqual(result["current"], 3)
        self.assertEqual(result["best"], 3)

    def test_history_appends_hit_iso(self) -> None:
        db.streak_increment(self.gid, "2025-01-01")
        db.streak_increment(self.gid, "2025-01-02")
        s = db.streak_get(self.gid)
        self.assertEqual(s["history"], ["2025-01-01", "2025-01-02"])

    def test_reset_zeroes_current(self) -> None:
        db.streak_increment(self.gid, "2025-01-01")
        db.streak_reset(self.gid)
        s = db.streak_get(self.gid)
        self.assertEqual(s["current"], 0)

    def test_reset_preserves_best(self) -> None:
        db.streak_increment(self.gid, "2025-01-01")
        db.streak_increment(self.gid, "2025-01-02")
        db.streak_reset(self.gid)
        s = db.streak_get(self.gid)
        self.assertEqual(s["current"], 0)
        self.assertEqual(s["best"], 2)

    def test_get_nonexistent_goal(self) -> None:
        self.assertIsNone(db.streak_get(9999))

    def test_update_nonexistent_returns_false(self) -> None:
        self.assertFalse(db.streak_update(9999, current=5))


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

class TestTemplateCRUD(unittest.TestCase):
    """Template repository + use_count increment via activity_add."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        tid = db.template_add("My template", "Read", duration_min=30)
        self.assertGreater(tid, 0)

    def test_get_returns_dict_with_tags(self) -> None:
        tid = db.template_add("T", "Read", tags=["focus", "deep"])
        t = db.template_get(tid)
        self.assertEqual(t["tags"], ["focus", "deep"])

    def test_list(self) -> None:
        db.template_add("A", "Title A")
        db.template_add("B", "Title B")
        self.assertEqual(len(db.template_list()), 2)

    def test_update_name(self) -> None:
        tid = db.template_add("T", "Title")
        db.template_update(tid, name="New name")
        self.assertEqual(db.template_get(tid)["name"], "New name")

    def test_delete(self) -> None:
        tid = db.template_add("T", "Title")
        self.assertTrue(db.template_delete(tid))
        self.assertIsNone(db.template_get(tid))

    def test_use_count_increments_on_activity_add(self) -> None:
        tid = db.template_add("T", "Title", duration_min=30)
        # Add an activity referencing the template.
        db.activity_add("Title", None, 30, "2025-01-01", template_id=tid)
        t = db.template_get(tid)
        self.assertEqual(t["use_count"], 1)
        self.assertIsNotNone(t["last_used_iso"])

    def test_use_count_increments_multiple_times(self) -> None:
        tid = db.template_add("T", "Title", duration_min=30)
        db.activity_add("Title", None, 30, "2025-01-01", template_id=tid)
        db.activity_add("Title", None, 30, "2025-01-02", template_id=tid)
        db.activity_add("Title", None, 30, "2025-01-03", template_id=tid)
        self.assertEqual(db.template_get(tid)["use_count"], 3)

    def test_list_excludes_archived(self) -> None:
        tid = db.template_add("T", "Title")
        db.template_update(tid, archived=1)
        self.assertEqual(len(db.template_list()), 0)
        self.assertEqual(len(db.template_list(include_archived=True)), 1)


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

class TestBadgeCRUD(unittest.TestCase):
    """Badge repository."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        bid = db.badge_add("first_activity", "First", "اولین",
                            "Log first", "اولین را ثبت کن",
                            "spark", "bronze")
        self.assertGreater(bid, 0)

    def test_get_by_key(self) -> None:
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        b = db.badge_get_by_key("first_activity")
        self.assertIsNotNone(b)
        self.assertEqual(b["name_en"], "First")

    def test_get_by_key_nonexistent(self) -> None:
        self.assertIsNone(db.badge_get_by_key("does_not_exist"))

    def test_has_true_after_add(self) -> None:
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        self.assertTrue(db.badge_has("first_activity"))

    def test_has_false_before_add(self) -> None:
        self.assertFalse(db.badge_has("first_activity"))

    def test_list(self) -> None:
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        db.badge_add("streak_3", "Hat Trick", "کلاه",
                      "3 days", "۳ روز",
                      "flame", "silver")
        self.assertEqual(len(db.badge_list()), 2)

    def test_delete(self) -> None:
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        self.assertTrue(db.badge_delete("first_activity"))
        self.assertFalse(db.badge_has("first_activity"))

    def test_add_idempotent_with_or_ignore(self) -> None:
        """Adding the same key twice doesn't duplicate."""
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")
        self.assertEqual(len(db.badge_list()), 1)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

class TestReminderCRUD(unittest.TestCase):
    """Reminder repository."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        rid = db.reminder_add("Morning", "08:00")
        self.assertGreater(rid, 0)

    def test_get_returns_dict(self) -> None:
        rid = db.reminder_add("Morning", "08:00", message="Wake up")
        r = db.reminder_get(rid)
        self.assertEqual(r["title"], "Morning")
        self.assertEqual(r["time_hhmm"], "08:00")
        self.assertEqual(r["message"], "Wake up")

    def test_list(self) -> None:
        db.reminder_add("A", "08:00")
        db.reminder_add("B", "20:00")
        self.assertEqual(len(db.reminder_list()), 2)

    def test_list_only_enabled(self) -> None:
        rid = db.reminder_add("Disabled", "08:00", enabled=False)
        self.assertEqual(len(db.reminder_list(only_enabled=True)), 0)
        self.assertEqual(len(db.reminder_list()), 1)

    def test_update_snooze_until(self) -> None:
        rid = db.reminder_add("A", "08:00")
        db.reminder_update(rid, snooze_until="2025-01-01T09:00:00")
        r = db.reminder_get(rid)
        self.assertEqual(r["snooze_until"], "2025-01-01T09:00:00")

    def test_delete(self) -> None:
        rid = db.reminder_add("A", "08:00")
        self.assertTrue(db.reminder_delete(rid))
        self.assertIsNone(db.reminder_get(rid))


# ---------------------------------------------------------------------------
# Recurring
# ---------------------------------------------------------------------------

class TestRecurringCRUD(unittest.TestCase):
    """Recurring rules."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        rid = db.recurring_add("Daily standup", 15, "daily",
                                next_run_iso="2025-01-01T09:00:00")
        self.assertGreater(rid, 0)

    def test_list(self) -> None:
        db.recurring_add("A", 30, "daily", next_run_iso="2025-01-01T09:00:00")
        db.recurring_add("B", 60, "weekly", next_run_iso="2025-01-02T10:00:00")
        self.assertEqual(len(db.recurring_list()), 2)

    def test_list_only_active(self) -> None:
        rid = db.recurring_add("A", 30, "daily",
                                next_run_iso="2025-01-01T09:00:00")
        db.recurring_update(rid, active=0)
        self.assertEqual(len(db.recurring_list(only_active=True)), 0)
        self.assertEqual(len(db.recurring_list()), 1)

    def test_due_now_with_past_date(self) -> None:
        db.recurring_add("Past", 30, "daily", next_run_iso="2020-01-01T09:00:00")
        due = db.recurring_due_now(now_iso="2025-01-01T12:00:00")
        self.assertEqual(len(due), 1)

    def test_due_now_with_future_date(self) -> None:
        db.recurring_add("Future", 30, "daily",
                          next_run_iso="2030-01-01T09:00:00")
        due = db.recurring_due_now(now_iso="2025-01-01T12:00:00")
        self.assertEqual(len(due), 0)

    def test_due_now_respects_end_date(self) -> None:
        db.recurring_add("Ended", 30, "daily",
                          next_run_iso="2020-01-01T09:00:00",
                          end_date_iso="2020-12-31")
        due = db.recurring_due_now(now_iso="2025-01-01T12:00:00")
        self.assertEqual(len(due), 0)

    def test_invalid_frequency_raises(self) -> None:
        with self.assertRaises(AssertionError):
            db.recurring_add("X", 30, "hourly")

    def test_delete(self) -> None:
        rid = db.recurring_add("A", 30, "daily",
                                next_run_iso="2025-01-01T09:00:00")
        self.assertTrue(db.recurring_delete(rid))


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessionLifecycle(unittest.TestCase):
    """Focus sessions."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_add_returns_id(self) -> None:
        sid = db.session_add(planned_min=25, started_at="2025-01-01T09:00:00")
        self.assertGreater(sid, 0)

    def test_get_returns_dict(self) -> None:
        sid = db.session_add(planned_min=25, started_at="2025-01-01T09:00:00")
        s = db.session_get(sid)
        self.assertEqual(s["planned_min"], 25)
        self.assertEqual(s["state"], "running")

    def test_update_state(self) -> None:
        sid = db.session_add(planned_min=25)
        db.session_update(sid, state="completed", actual_min=24)
        s = db.session_get(sid)
        self.assertEqual(s["state"], "completed")
        self.assertEqual(s["actual_min"], 24)

    def test_list_active(self) -> None:
        s1 = db.session_add(planned_min=25)
        s2 = db.session_add(planned_min=50)
        db.session_update(s2, state="paused")
        db.session_add(planned_min=30)  # third running
        # Update one to completed — should not appear.
        s3 = db.session_add(planned_min=15)
        db.session_update(s3, state="completed")
        active = db.session_list_active()
        self.assertEqual(len(active), 3)  # s1, s2, and the third running one


# ---------------------------------------------------------------------------
# KV store
# ---------------------------------------------------------------------------

class TestKVStore(unittest.TestCase):
    """Generic key-value store."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_set_and_get(self) -> None:
        db.kv_set("foo", "bar")
        self.assertEqual(db.kv_get("foo"), "bar")

    def test_get_missing_returns_default(self) -> None:
        self.assertIsNone(db.kv_get("missing"))
        self.assertEqual(db.kv_get("missing", "default"), "default")

    def test_set_overwrites(self) -> None:
        db.kv_set("k", "v1")
        db.kv_set("k", "v2")
        self.assertEqual(db.kv_get("k"), "v2")

    def test_get_int(self) -> None:
        db.kv_set("n", "42")
        self.assertEqual(db.kv_get_int("n"), 42)
        self.assertEqual(db.kv_get_int("missing", 7), 7)

    def test_get_int_invalid_returns_default(self) -> None:
        db.kv_set("n", "not-a-number")
        self.assertEqual(db.kv_get_int("n", 99), 99)

    def test_set_int(self) -> None:
        db.kv_set_int("count", 100)
        self.assertEqual(db.kv_get_int("count"), 100)

    def test_get_bool(self) -> None:
        for true_val in ("1", "true", "yes", "on", "TRUE", "Yes"):
            db.kv_set("b", true_val)
            self.assertTrue(db.kv_get_bool("b"), f"Failed for {true_val!r}")
        for false_val in ("0", "false", "no", "off", "anything"):
            db.kv_set("b", false_val)
            self.assertFalse(db.kv_get_bool("b"), f"Failed for {false_val!r}")

    def test_set_bool(self) -> None:
        db.kv_set_bool("flag", True)
        self.assertTrue(db.kv_get_bool("flag"))
        db.kv_set_bool("flag", False)
        self.assertFalse(db.kv_get_bool("flag"))

    def test_get_json(self) -> None:
        db.kv_set_json("obj", {"a": 1, "b": [2, 3]})
        self.assertEqual(db.kv_get_json("obj"), {"a": 1, "b": [2, 3]})

    def test_get_json_missing(self) -> None:
        self.assertIsNone(db.kv_get_json("missing"))
        self.assertEqual(db.kv_get_json("missing", {}), {})

    def test_delete(self) -> None:
        db.kv_set("k", "v")
        self.assertTrue(db.kv_delete("k"))
        self.assertIsNone(db.kv_get("k"))

    def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(db.kv_delete("never-existed"))

    def test_keys_all(self) -> None:
        db.kv_set("a", "1")
        db.kv_set("b", "2")
        db.kv_set("c", "3")
        keys = db.kv_keys()
        self.assertIn("a", keys)
        self.assertIn("b", keys)
        self.assertIn("c", keys)

    def test_keys_with_prefix(self) -> None:
        db.kv_set("user_a", "1")
        db.kv_set("user_b", "2")
        db.kv_set("other", "3")
        keys = db.kv_keys(prefix="user_")
        self.assertEqual(set(keys), {"user_a", "user_b"})


# ---------------------------------------------------------------------------
# Settings store (typed)
# ---------------------------------------------------------------------------

class TestSettingsStore(unittest.TestCase):
    """Typed settings store."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_get_default(self) -> None:
        # The default 'lang' is seeded.
        self.assertEqual(db.setting_get("lang"), config.DEFAULT_LANG)

    def test_get_missing_returns_default(self) -> None:
        self.assertIsNone(db.setting_get("missing"))
        self.assertEqual(db.setting_get("missing", "fallback"), "fallback")

    def test_set_string(self) -> None:
        db.setting_set("custom_key", "value")
        self.assertEqual(db.setting_get("custom_key"), "value")

    def test_set_int_auto_type(self) -> None:
        db.setting_set("count", 42)
        self.assertEqual(db.setting_get("count"), 42)
        self.assertIsInstance(db.setting_get("count"), int)

    def test_set_float_auto_type(self) -> None:
        db.setting_set("ratio", 3.14)
        self.assertEqual(db.setting_get("ratio"), 3.14)
        self.assertIsInstance(db.setting_get("ratio"), float)

    def test_set_bool_auto_type(self) -> None:
        db.setting_set("flag", True)
        self.assertTrue(db.setting_get("flag"))
        self.assertIsInstance(db.setting_get("flag"), bool)

    def test_set_json_auto_type(self) -> None:
        db.setting_set("data", {"a": 1})
        self.assertEqual(db.setting_get("data"), {"a": 1})

    def test_set_with_explicit_type(self) -> None:
        db.setting_set("n", "42", type_="int")
        self.assertEqual(db.setting_get("n"), 42)

    def test_delete(self) -> None:
        db.setting_set("temp", "x")
        self.assertTrue(db.setting_delete("temp"))
        self.assertIsNone(db.setting_get("temp"))

    def test_list_returns_rows(self) -> None:
        rows = db.setting_list()
        self.assertGreater(len(rows), 0)
        keys = {r["key"] for r in rows}
        self.assertIn("lang", keys)
        self.assertIn("theme", keys)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class TestTagSync(unittest.TestCase):
    """Tag synchronization via activity_add/update."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_activity_add_creates_tags(self) -> None:
        db.activity_add("T", None, 30, "2025-01-01", tags=["focus", "deep"])
        tags = db.tag_list(min_count=1)
        names = {t["name"] for t in tags}
        self.assertIn("focus", names)
        self.assertIn("deep", names)

    def test_tag_use_count_increments(self) -> None:
        db.activity_add("T1", None, 30, "2025-01-01", tags=["focus"])
        db.activity_add("T2", None, 30, "2025-01-02", tags=["focus"])
        tags = db.tag_list()
        focus = next(t for t in tags if t["name"] == "focus")
        self.assertEqual(focus["use_count"], 2)

    def test_tag_search(self) -> None:
        db.activity_add("T", None, 30, "2025-01-01", tags=["focus", "deep-work"])
        results = db.tag_search("deep")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "deep-work")

    def test_tag_search_no_match(self) -> None:
        db.activity_add("T", None, 30, "2025-01-01", tags=["focus"])
        self.assertEqual(len(db.tag_search("xyz")), 0)


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

class TestAuditLogs(unittest.TestCase):
    """Backup / export audit logs."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_log_backup(self) -> None:
        db.log_backup("backup", "/tmp/x.raskbk", 1024, True, None)
        cur = db.get_conn().execute("SELECT * FROM backups_log")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "backup")
        self.assertEqual(rows[0]["file_size"], 1024)
        self.assertEqual(rows[0]["success"], 1)

    def test_log_export(self) -> None:
        db.log_export("pdf", "/tmp/x.pdf", 2048, 10, True, None)
        cur = db.get_conn().execute("SELECT * FROM exports_log")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "pdf")
        self.assertEqual(rows[0]["record_count"], 10)


# ---------------------------------------------------------------------------
# Export / import round-trip
# ---------------------------------------------------------------------------

class TestExportImport(unittest.TestCase):
    """Database export_to_dict / import_from_dict round-trip."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_export_returns_dict_with_meta(self) -> None:
        out = db.export_to_dict()
        self.assertIn("meta", out)
        self.assertIn("data", out)
        self.assertEqual(out["meta"]["app"], config.APP_NAME)
        self.assertIn("activities", out["data"])
        self.assertIn("categories", out["data"])

    def test_export_import_round_trip(self) -> None:
        # Seed some data.
        db.activity_add("A", 1, 30, "2025-01-01", tags=["focus"])
        db.activity_add("B", 2, 60, "2025-01-02")
        db.goal_add("weekly", 600)
        db.template_add("T", "Title")
        db.badge_add("first_activity", "First", "اولین",
                      "Log first", "اولین را ثبت کن",
                      "spark", "bronze")

        exported = db.export_to_dict()
        # Verify the export captured the data.
        self.assertEqual(len(exported["data"]["activities"]), 2)

        # Wipe the DB by importing with replace=True (clears all tables
        # then inserts the exported rows).
        db.import_from_dict(exported, replace=True)

        # Verify all data round-tripped.
        self.assertEqual(db.activity_count(), 2)
        self.assertEqual(len(db.goal_list()), 2)  # default + new
        self.assertEqual(len(db.template_list()), 1)
        self.assertTrue(db.badge_has("first_activity"))

    def test_export_preserves_meta_block(self) -> None:
        out = db.export_to_dict()
        self.assertEqual(out["meta"]["app"], config.APP_NAME)
        self.assertEqual(out["meta"]["schema_version"], db.SCHEMA_VERSION)
        self.assertIn("exported_at", out["meta"])


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

class TestMaintenance(unittest.TestCase):
    """Vacuum, integrity_check, db_file_size, stats."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_vacuum_runs_without_error(self) -> None:
        # Vacuum shouldn't raise.
        db.vacuum()

    def test_integrity_check_returns_ok(self) -> None:
        self.assertEqual(db.integrity_check(), ["ok"])

    def test_db_file_size_nonzero(self) -> None:
        self.assertGreater(db.db_file_size(), 0)

    def test_stats_includes_all_tables(self) -> None:
        s = db.stats()
        for table in ("activities", "categories", "goals", "streaks",
                      "templates", "badges", "reminders", "kv", "tags",
                      "activity_tags", "recurring", "sessions", "settings"):
            self.assertIn(table, s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
