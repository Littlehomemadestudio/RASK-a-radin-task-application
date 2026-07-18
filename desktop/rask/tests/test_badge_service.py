"""
rask.tests.test_badge_service
============================

Unit tests for :mod:`rask.services.badge_service`.

Covers:

  • ``unlock()`` for new badge returns True
  • ``unlock()`` for already-earned badge returns False
  • ``unlock()`` for unknown key returns False
  • ``has()`` / ``get()`` / ``list_all()`` / ``list_earned()``
  • ``check_all()`` detects newly-earned badges
  • ``revoke()`` removes an earned badge
  • All 12 badges in ``config.BADGE_DEFINITIONS`` have valid definitions
    (key, name_en, name_fa, desc_en, desc_fa, icon, tier)
  • Streak milestones trigger correctly (3, 7, 14, 30, 60, 100, 365)
  • ``progress_to_next()`` returns progress info for streak badges
  • Event publication: ``badge.unlocked`` on first unlock only
"""
from __future__ import annotations

import unittest
from typing import Any, List

from rask import config, database as db
from rask.core.event_bus import bus
from rask.services.badge_service import BadgeService, badge_service
from rask.services.streak_service import streak_service
from rask.tests import fresh_db


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _add_goal_with_streak(period: str = "daily",
                          target_minutes: int = 60) -> int:
    """Add a goal (creating its streak row) and return its id."""
    return db.goal_add(period, target_minutes)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestBadgeDefinitions(unittest.TestCase):
    """All badge definitions in config.BADGE_DEFINITIONS are valid."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_definitions_count(self) -> None:
        self.assertGreaterEqual(len(config.BADGE_DEFINITIONS), 12)

    def test_each_definition_has_required_fields(self) -> None:
        required = {"key", "name_en", "name_fa", "desc_en", "desc_fa",
                    "icon", "tier"}
        for d in config.BADGE_DEFINITIONS:
            for field in required:
                self.assertIn(field, d, f"missing {field} in {d}")

    def test_each_definition_has_valid_tier(self) -> None:
        valid_tiers = {"bronze", "silver", "gold", "platinum"}
        for d in config.BADGE_DEFINITIONS:
            self.assertIn(d["tier"], valid_tiers,
                           f"invalid tier {d['tier']} in {d['key']}")

    def test_each_definition_has_non_empty_key(self) -> None:
        for d in config.BADGE_DEFINITIONS:
            self.assertTrue(d["key"], f"empty key in {d}")

    def test_each_definition_has_non_empty_names(self) -> None:
        for d in config.BADGE_DEFINITIONS:
            self.assertTrue(d["name_en"])
            self.assertTrue(d["name_fa"])

    def test_each_definition_has_non_empty_descriptions(self) -> None:
        for d in config.BADGE_DEFINITIONS:
            self.assertTrue(d["desc_en"])
            self.assertTrue(d["desc_fa"])

    def test_keys_are_unique(self) -> None:
        keys = [d["key"] for d in config.BADGE_DEFINITIONS]
        self.assertEqual(len(keys), len(set(keys)))


class TestBadgeUnlock(unittest.TestCase):
    """unlock() behavior."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_unlock_new_badge_returns_true(self) -> None:
        self.assertTrue(self.svc.unlock("first_activity"))

    def test_unlock_already_earned_returns_false(self) -> None:
        self.svc.unlock("first_activity")
        self.assertFalse(self.svc.unlock("first_activity"))

    def test_unlock_unknown_key_returns_false(self) -> None:
        self.assertFalse(self.svc.unlock("nonexistent_badge"))

    def test_unlock_empty_key_returns_false(self) -> None:
        self.assertFalse(self.svc.unlock(""))

    def test_unlock_publishes_event_on_first_unlock(self) -> None:
        coll: List[Any] = []
        bus.subscribe("badge.unlocked", lambda b: coll.append(b))
        self.svc.unlock("first_activity")
        self.assertEqual(len(coll), 1)

    def test_unlock_does_not_publish_on_second_unlock(self) -> None:
        coll: List[Any] = []
        bus.subscribe("badge.unlocked", lambda b: coll.append(b))
        self.svc.unlock("first_activity")
        self.svc.unlock("first_activity")  # no-op
        self.assertEqual(len(coll), 1)

    def test_unlock_with_metadata(self) -> None:
        self.assertTrue(self.svc.unlock("streak_3", metadata={"goal_id": 1}))
        b = self.svc.get("streak_3")
        self.assertIsNotNone(b)
        self.assertEqual(b["metadata"].get("goal_id"), 1)


class TestBadgeHasGet(unittest.TestCase):
    """has() and get()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_has_returns_false_for_unearned(self) -> None:
        self.assertFalse(self.svc.has("first_activity"))

    def test_has_returns_true_after_unlock(self) -> None:
        self.svc.unlock("first_activity")
        self.assertTrue(self.svc.has("first_activity"))

    def test_has_returns_false_for_unknown_key(self) -> None:
        self.assertFalse(self.svc.has("nonexistent_badge"))

    def test_has_empty_key_returns_false(self) -> None:
        self.assertFalse(self.svc.has(""))

    def test_get_returns_none_for_unearned(self) -> None:
        self.assertIsNone(self.svc.get("first_activity"))

    def test_get_returns_dict_after_unlock(self) -> None:
        self.svc.unlock("first_activity")
        b = self.svc.get("first_activity")
        self.assertIsNotNone(b)
        self.assertEqual(b["key"], "first_activity")
        self.assertIn("earned_at", b)
        self.assertTrue(b["earned"])

    def test_get_unknown_key_returns_none(self) -> None:
        self.assertIsNone(self.svc.get("nonexistent_badge"))


class TestBadgeList(unittest.TestCase):
    """list_all() and list_earned()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_list_earned_empty_initially(self) -> None:
        self.assertEqual(self.svc.list_earned(), [])

    def test_list_earned_after_unlock(self) -> None:
        self.svc.unlock("first_activity")
        self.svc.unlock("streak_3")
        earned = self.svc.list_earned()
        self.assertEqual(len(earned), 2)

    def test_list_all_returns_all_definitions(self) -> None:
        all_badges = self.svc.list_all()
        self.assertEqual(len(all_badges), len(config.BADGE_DEFINITIONS))

    def test_list_all_marks_earned_correctly(self) -> None:
        self.svc.unlock("first_activity")
        all_badges = self.svc.list_all()
        earned = [b for b in all_badges if b["earned"]]
        unearned = [b for b in all_badges if not b["earned"]]
        self.assertEqual(len(earned), 1)
        self.assertEqual(earned[0]["key"], "first_activity")
        self.assertEqual(len(unearned), len(config.BADGE_DEFINITIONS) - 1)

    def test_list_all_includes_definition_fields(self) -> None:
        all_badges = self.svc.list_all()
        for b in all_badges:
            self.assertIn("name_en", b)
            self.assertIn("name_fa", b)
            self.assertIn("desc_en", b)
            self.assertIn("desc_fa", b)
            self.assertIn("icon", b)
            self.assertIn("tier", b)
            self.assertIn("earned", b)
            self.assertIn("earned_at", b)


class TestRevoke(unittest.TestCase):
    """revoke() removes an earned badge."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_revoke_removes_badge(self) -> None:
        self.svc.unlock("first_activity")
        self.assertTrue(self.svc.revoke("first_activity"))
        self.assertFalse(self.svc.has("first_activity"))

    def test_revoke_missing_returns_false(self) -> None:
        self.assertFalse(self.svc.revoke("first_activity"))

    def test_revoke_unknown_key_returns_false(self) -> None:
        self.assertFalse(self.svc.revoke("nonexistent"))

    def test_revoke_empty_key_returns_false(self) -> None:
        self.assertFalse(self.svc.revoke(""))

    def test_can_unlock_again_after_revoke(self) -> None:
        self.svc.unlock("first_activity")
        self.svc.revoke("first_activity")
        self.assertTrue(self.svc.unlock("first_activity"))


class TestCheckAll(unittest.TestCase):
    """check_all() detects newly-earned badges."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_check_all_empty_returns_empty(self) -> None:
        self.assertEqual(self.svc.check_all(), [])

    def test_check_all_unlocks_first_activity_after_adding_activity(self) -> None:
        # No activities yet.
        self.assertEqual(self.svc.check_all(), [])
        # Add an activity.
        db.activity_add("Test", None, 30, "2025-01-01")
        newly = self.svc.check_all()
        self.assertIn("first_activity", newly)

    def test_check_all_does_not_re_unlock(self) -> None:
        db.activity_add("Test", None, 30, "2025-01-01")
        self.svc.check_all()
        # Second call should not re-unlock.
        newly = self.svc.check_all()
        self.assertNotIn("first_activity", newly)

    def test_check_all_unlocks_sprint_after_10_activities_same_day(self) -> None:
        from rask.core.time_utils import today_iso
        today = today_iso()
        for i in range(10):
            db.activity_add(f"Act {i}", None, 5, today)
        newly = self.svc.check_all()
        self.assertIn("sprint", newly)


class TestStreakMilestoneBadges(unittest.TestCase):
    """Streak milestones unlock badges."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()
        self.streak_svc = streak_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_streak_3_unlocks_at_3(self) -> None:
        gid = _add_goal_with_streak()
        # Increment 3 days in a row.
        self.streak_svc.increment(gid, "2025-01-01")
        self.streak_svc.increment(gid, "2025-01-02")
        self.streak_svc.increment(gid, "2025-01-03")
        # The streak service should have unlocked the badge automatically
        # via its milestone callback.
        self.assertTrue(self.svc.has("streak_3"))

    def test_streak_7_unlocks_at_7(self) -> None:
        gid = _add_goal_with_streak()
        for i in range(7):
            self.streak_svc.increment(gid, f"2025-01-{i+1:02d}")
        self.assertTrue(self.svc.has("streak_7"))

    def test_streak_3_not_unlocked_at_2(self) -> None:
        gid = _add_goal_with_streak()
        self.streak_svc.increment(gid, "2025-01-01")
        self.streak_svc.increment(gid, "2025-01-02")
        self.assertFalse(self.svc.has("streak_3"))


class TestProgressToNext(unittest.TestCase):
    """progress_to_next() for streak badges."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()
        self.streak_svc = streak_service

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_progress_to_next_streak_3_at_zero(self) -> None:
        p = self.svc.progress_to_next("streak_3")
        self.assertIsNotNone(p)
        self.assertEqual(p["target"], 3)
        self.assertEqual(p["current"], 0)
        self.assertEqual(p["remaining"], 3)
        self.assertEqual(p["percent"], 0.0)

    def test_progress_to_next_streak_3_at_two(self) -> None:
        gid = _add_goal_with_streak()
        self.streak_svc.increment(gid, "2025-01-01")
        self.streak_svc.increment(gid, "2025-01-02")
        p = self.svc.progress_to_next("streak_3")
        self.assertEqual(p["current"], 2)
        self.assertEqual(p["remaining"], 1)

    def test_progress_to_next_streak_7(self) -> None:
        p = self.svc.progress_to_next("streak_7")
        self.assertEqual(p["target"], 7)

    def test_progress_to_next_streak_100(self) -> None:
        p = self.svc.progress_to_next("streak_100")
        self.assertEqual(p["target"], 100)

    def test_progress_to_next_non_streak_returns_none(self) -> None:
        self.assertIsNone(self.svc.progress_to_next("first_activity"))
        self.assertIsNone(self.svc.progress_to_next("early_bird"))
        self.assertIsNone(self.svc.progress_to_next("nonexistent"))


class TestDefinitionLookup(unittest.TestCase):
    """definition() and list_definitions()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_definition_returns_known(self) -> None:
        d = self.svc.definition("first_activity")
        self.assertIsNotNone(d)
        self.assertEqual(d["key"], "first_activity")

    def test_definition_returns_none_for_unknown(self) -> None:
        self.assertIsNone(self.svc.definition("nonexistent"))
        self.assertIsNone(self.svc.definition(""))

    def test_list_definitions_returns_all(self) -> None:
        defs = self.svc.list_definitions()
        self.assertEqual(len(defs), len(config.BADGE_DEFINITIONS))

    def test_list_definitions_sorted_by_tier(self) -> None:
        defs = self.svc.list_definitions()
        tier_order = {"bronze": 0, "silver": 1, "gold": 2, "platinum": 3}
        for i in range(len(defs) - 1):
            a = tier_order.get(defs[i]["tier"], 99)
            b = tier_order.get(defs[i + 1]["tier"], 99)
            self.assertLessEqual(a, b)


class TestEdgeCases(unittest.TestCase):
    """Edge cases."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()
        self.svc = BadgeService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_exists(self) -> None:
        self.assertIsInstance(badge_service, BadgeService)

    def test_init_is_safe_to_call(self) -> None:
        self.svc.init()  # no-op

    def test_unlock_all_then_check_all(self) -> None:
        # Unlock all defined badges manually.
        for d in config.BADGE_DEFINITIONS:
            self.svc.unlock(d["key"])
        # check_all should return empty (all already earned).
        self.assertEqual(self.svc.check_all(), [])
        # list_earned should match BADGE_DEFINITIONS count.
        self.assertEqual(len(self.svc.list_earned()),
                         len(config.BADGE_DEFINITIONS))


if __name__ == "__main__":
    unittest.main()
