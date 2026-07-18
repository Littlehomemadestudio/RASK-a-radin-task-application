"""
rask.services.badge_service
===========================

Achievement badges.

Badges are defined once in :data:`config.BADGE_DEFINITIONS` and earned
at runtime by meeting certain conditions.  This service:

  • Lists all defined badges (with an ``earned`` flag)
  • Unlocks a badge (idempotent — returns ``True`` only when newly earned)
  • Runs ``check_all()`` to scan current state for newly-unlockable
    badges (e.g. after a new activity is added)

Badge definitions are kept in code (not the DB) so they can evolve with
the app.  Earned badges are persisted in the ``badges`` table.

Mirrors the badge-award calls sprinkled through ``web/js/timer.js``
and ``web/js/db.js``.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import (
    add_days,
    end_of_week,
    start_of_week,
    today_iso,
)

__all__ = ["BadgeService", "badge_service"]

_log = get_logger("services.badge")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _definition_map() -> Dict[str, Dict[str, Any]]:
    """Return a dict mapping badge key -> definition dict."""
    return {b["key"]: b for b in config.BADGE_DEFINITIONS}


def _row_to_badge(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB badge row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    raw = out.pop("metadata_json", None)
    if isinstance(raw, str) and raw:
        try:
            out["metadata"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            out["metadata"] = {}
    elif isinstance(raw, dict):
        out["metadata"] = dict(raw)
    else:
        out["metadata"] = {}
    out["earned"] = True
    return out


# =============================================================================
# === BadgeService                                                           ===
# =============================================================================

class BadgeService:
    """Achievement badges with unlock detection."""

    def __init__(self) -> None:
        self._definitions: Dict[str, Dict[str, Any]] = _definition_map()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """No-op init for symmetry."""
        _log.debug("BadgeService initialized (%d definitions)",
                    len(self._definitions))

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def definition(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the definition dict for `key`, or ``None`` if unknown."""
        if not key:
            return None
        d = self._definitions.get(key)
        return dict(d) if d else None

    def list_definitions(self) -> List[Dict[str, Any]]:
        """Return all badge definitions (sorted by tier then key)."""
        tier_order = {"bronze": 0, "silver": 1, "gold": 2, "platinum": 3}
        out = [dict(d) for d in self._definitions.values()]
        out.sort(key=lambda b: (
            tier_order.get(b.get("tier", ""), 99),
            b.get("key", ""),
        ))
        return out

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def has(self, key: str) -> bool:
        """Return ``True`` if the badge `key` has been earned."""
        if not key:
            return False
        try:
            return db.badge_has(key)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return False

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the earned badge record for `key`, or ``None``.

        Note: returns ``None`` even for *defined* but not-yet-earned
        badges.  Use :meth:`definition` for definition lookup and
        :meth:`list_all` for the combined view.
        """
        if not key:
            return None
        try:
            row = db.badge_get_by_key(key)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return None
        return _row_to_badge(row)

    def list_earned(self) -> List[Dict[str, Any]]:
        """Return all earned badges (newest first)."""
        try:
            rows = db.badge_list()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []
        out: List[Dict[str, Any]] = []
        for r in rows:
            b = _row_to_badge(r)
            if b is not None:
                out.append(b)
        return out

    def list_all(self) -> List[Dict[str, Any]]:
        """Return ALL defined badges, with ``earned`` and ``earned_at`` fields.

        Earned badges include their full DB record (``earned_at``,
        ``metadata``); unearned badges include the definition plus
        ``earned=False``.

        The list is sorted by tier then name for stable display.
        """
        earned_map: Dict[str, Dict[str, Any]] = {
            b["key"]: b for b in self.list_earned()
        }
        out: List[Dict[str, Any]] = []
        for d in self.list_definitions():
            key = d["key"]
            if key in earned_map:
                row = dict(earned_map[key])
                row["earned"] = True
                row.setdefault("name_en", d.get("name_en"))
                row.setdefault("name_fa", d.get("name_fa"))
                row.setdefault("desc_en", d.get("desc_en"))
                row.setdefault("desc_fa", d.get("desc_fa"))
                row.setdefault("icon", d.get("icon"))
                row.setdefault("tier", d.get("tier"))
                out.append(row)
            else:
                row = dict(d)
                row["earned"] = False
                row["earned_at"] = None
                row["metadata"] = {}
                out.append(row)
        return out

    # ------------------------------------------------------------------
    # Unlock
    # ------------------------------------------------------------------

    def unlock(self, key: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Unlock badge `key`.

        Returns ``True`` if the badge was newly unlocked, ``False`` if
        it was already earned or the key is unknown.

        Publishes ``badge.unlocked`` on first unlock.
        """
        if not key:
            return False
        d = self._definitions.get(key)
        if not d:
            _log.warning("unlock: unknown badge key %r", key)
            return False

        if self.has(key):
            return False

        try:
            db.badge_add(
                key=key,
                name_en=d.get("name_en", ""),
                name_fa=d.get("name_fa", ""),
                desc_en=d.get("desc_en", ""),
                desc_fa=d.get("desc_fa", ""),
                icon=d.get("icon", ""),
                tier=d.get("tier", ""),
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return False

        record = self.get(key) or {"key": key}
        bus.publish("badge.unlocked", record)
        _log.info("Badge unlocked: %s (%s)", key, d.get("name_en", ""))
        return True

    def revoke(self, key: str) -> bool:
        """Revoke (delete) an earned badge.

        Mainly useful for testing.  Returns ``True`` if a row was
        deleted.
        """
        if not key:
            return False
        try:
            return db.badge_delete(key)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"key": key})
            return False

    # ------------------------------------------------------------------
    # Aggregate checks
    # ------------------------------------------------------------------

    def check_all(self) -> List[str]:
        """Scan current state and unlock any newly-earned badges.

        Returns a list of newly-unlocked badge keys (may be empty).

        Called periodically (e.g. after every activity mutation) by
        the orchestrator.  Each individual check is wrapped in
        try/except so a single broken check cannot prevent the others
        from running.
        """
        newly: List[str] = []
        checks = (
            ("first_activity", self._check_first_activity),
            ("early_bird", self._check_early_bird),
            ("night_owl", self._check_night_owl),
            ("marathon", self._check_marathon),
            ("sprint", self._check_sprint),
            ("polyglot", self._check_polyglot),
            ("goal_master", self._check_goal_master),
            ("streak_3", self._check_streak_3),
            ("streak_7", self._check_streak_7),
            ("streak_14", self._check_streak_14),
            ("streak_30", self._check_streak_30),
            ("streak_60", self._check_streak_60),
            ("streak_100", self._check_streak_100),
            ("streak_365", self._check_streak_365),
            ("consistency", self._check_consistency),
        )
        for key, check in checks:
            try:
                if not self.has(key) and check():
                    if self.unlock(key):
                        newly.append(key)
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"check": key})
        if newly:
            _log.info("check_all unlocked %d badges: %s",
                      len(newly), newly)
        return newly

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    def progress_to_next(self, key: str) -> Optional[Dict[str, Any]]:
        """Return progress info toward the next milestone for `key`.

        For streak-based badges (``streak_3``, ``streak_7``, etc.) this
        returns ``{"current": N, "target": M, "percent": P}``.  For
        non-streak badges, returns ``None``.
        """
        if not key:
            return None
        # Streak badges
        if key.startswith("streak_"):
            try:
                target = int(key.split("_", 1)[1])
            except (IndexError, ValueError):
                return None
            # Use the highest current streak across all goals.
            try:
                from .streak_service import streak_service
                best_current = 0
                for g in db.goal_list(only_active=True):
                    cur = streak_service.current(g["id"])
                    if cur > best_current:
                        best_current = cur
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {"key": key})
                best_current = 0
            percent = min(1.0, best_current / target) if target else 0.0
            return {
                "current": best_current,
                "target": target,
                "percent": round(percent * 100, 1),
                "remaining": max(0, target - best_current),
            }
        return None

    # ------------------------------------------------------------------
    # Individual badge checks
    # ------------------------------------------------------------------
    # Each returns True if the badge should be unlocked.

    def _check_first_activity(self) -> bool:
        """First Step: log at least one activity."""
        try:
            return db.activity_count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _check_early_bird(self) -> bool:
        """Early Bird: any activity with start_ts before 06:00 local."""
        try:
            # Search recent activities for an early start.
            rows = db.activity_list(limit=200, kinds=None)
            for a in rows:
                st = a.get("start_ts")
                if not st:
                    continue
                try:
                    dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
                    if dt.hour < 6:
                        return True
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return False

    def _check_night_owl(self) -> bool:
        """Night Owl: any activity with start_ts at or after 00:00 and before 05:00."""
        try:
            rows = db.activity_list(limit=200)
            for a in rows:
                st = a.get("start_ts")
                if not st:
                    continue
                try:
                    dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
                    # "After midnight" -> 00:00..05:00
                    if 0 <= dt.hour < 5:
                        return True
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return False

    def _check_marathon(self) -> bool:
        """Marathon: 5+ hours (300 min) of activity in a single day."""
        try:
            today = today_iso()
            # Check the last 365 days.
            for offset in range(0, 365):
                d = add_days(today, -offset)
                total = db.activity_sum_duration(date_from=d, date_to=d)
                if total >= 300:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _check_sprint(self) -> bool:
        """Sprint: 10+ activities in a single day."""
        try:
            today = today_iso()
            for offset in range(0, 90):
                d = add_days(today, -offset)
                cnt = db.activity_count(date_from=d, date_to=d)
                if cnt >= 10:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _check_polyglot(self) -> bool:
        """Renaissance: log all 7 distinct categories in one week."""
        try:
            today = today_iso()
            start = start_of_week(today)
            end = end_of_week(today)
            rows = db.activity_group_by_category(date_from=start, date_to=end)
            distinct = sum(1 for r in rows if r.get("category_id") is not None)
            return distinct >= 7
        except Exception:  # noqa: BLE001
            return False

    def _check_goal_master(self) -> bool:
        """Goal Master: hit a daily goal 30 times (sum across all daily goals)."""
        try:
            from .streak_service import streak_service
            total_hits = 0
            for g in db.goal_list(only_active=True):
                if g.get("period") != "daily":
                    continue
                history = streak_service.history(g["id"])
                total_hits += len(history)
            return total_hits >= 30
        except Exception:  # noqa: BLE001
            return False

    def _check_streak_3(self) -> bool:
        return self._max_streak_any_goal() >= 3

    def _check_streak_7(self) -> bool:
        return self._max_streak_any_goal() >= 7

    def _check_streak_14(self) -> bool:
        return self._max_streak_any_goal() >= 14

    def _check_streak_30(self) -> bool:
        return self._max_streak_any_goal() >= 30

    def _check_streak_60(self) -> bool:
        return self._max_streak_any_goal() >= 60

    def _check_streak_100(self) -> bool:
        return self._max_streak_any_goal() >= 100

    def _check_streak_365(self) -> bool:
        return self._max_streak_any_goal() >= 365

    def _check_consistency(self) -> bool:
        """Consistency: 60-day streak (alias for streak_60)."""
        return self._max_streak_any_goal() >= 60

    def _max_streak_any_goal(self) -> int:
        """Return the highest ``current`` streak across all goals."""
        try:
            from .streak_service import streak_service
            best = 0
            for g in db.goal_list():
                cur = streak_service.current(g["id"])
                if cur > best:
                    best = cur
            return best
        except Exception:  # noqa: BLE001
            return 0


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

badge_service: BadgeService = BadgeService()
