"""
rask.features.notifications_center
==================================

In-app notification center.

Notifications are short-lived, in-app messages with an optional
action.  They are persisted as a JSON list in the ``kv`` store under
the key ``notifications.center`` and auto-expire after 30 days.

The service subscribes to events on the global event bus and
auto-generates notifications for:

  • ``badge.unlocked``           — "نشان جدید: X"
  • ``goal.progress`` (>=100%)   — "هدف محقق شد: X"
  • ``streak.milestone``         — "زنجیره N روزه!"
  • ``backup.created``           — "پشتیبان ساخته شد"
  • ``reminder.triggered``       — "یادآوری: X"
  • ``pomodoro.finished``        — "پومودورو کامل!"
  • ``focus.ended``              — "جلسه تمرکز تمام شد"
  • ``journal.streak_changed``   — "زنجیره دفترچه N روز"

UI consumers can subscribe to changes via :meth:`NotificationCenter.subscribe`.

Schema
------

Uses the existing ``kv`` table — no new schema needed.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus, STANDARD_EVENTS
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import today_iso

__all__ = [
    "Notification",
    "NotificationCenter",
    "notification_center",
    "KIND_INFO",
    "KIND_SUCCESS",
    "KIND_WARNING",
    "KIND_ERROR",
    "KIND_ACHIEVEMENT",
]

_log = get_logger("features.notifications")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

KIND_INFO: str = "info"
KIND_SUCCESS: str = "success"
KIND_WARNING: str = "warning"
KIND_ERROR: str = "error"
KIND_ACHIEVEMENT: str = "achievement"

#: Kv-store key for the persisted notification list.
STORE_KEY: str = "notifications.center"

#: Auto-expiry in days.
DEFAULT_EXPIRY_DAYS: int = 30

#: Maximum notifications to keep (newest first).
MAX_NOTIFICATIONS: int = 200


# =============================================================================
# === Data class                                                             ===
# =============================================================================

@dataclass
class Notification:
    """A single notification."""

    id: int
    title: str
    body: str
    kind: str = KIND_INFO
    icon: Optional[str] = None
    timestamp: str = ""                # ISO datetime
    read: bool = False
    action_type: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None    # ISO datetime or None for never

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Notification":
        return cls(
            id=int(d.get("id", 0)),
            title=d.get("title", ""),
            body=d.get("body", ""),
            kind=d.get("kind", KIND_INFO),
            icon=d.get("icon"),
            timestamp=d.get("timestamp", ""),
            read=bool(d.get("read", False)),
            action_type=d.get("action_type"),
            action_payload=d.get("action_payload"),
            expires_at=d.get("expires_at"),
        )


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _is_expired(n: Notification) -> bool:
    if not n.expires_at:
        return False
    exp = _parse_iso(n.expires_at)
    if exp is None:
        return False
    return _now_dt() > exp


# =============================================================================
# === NotificationCenter                                                    ===
# =============================================================================

class NotificationCenter:
    """In-app notification center.

    Module-level singleton :data:`notification_center`.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: List[Callable[[str, Notification], None]] = []
        self._next_id: int = 1
        self._notifications: List[Notification] = self._load()
        if self._notifications:
            self._next_id = max(n.id for n in self._notifications) + 1
        self._subscribed: bool = False
        self._auto_subscribe()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> List[Notification]:
        try:
            raw = db.kv_get_json(STORE_KEY, [])
            if not isinstance(raw, list):
                return []
            out: List[Notification] = []
            for item in raw:
                if isinstance(item, dict):
                    try:
                        out.append(Notification.from_dict(item))
                    except Exception:  # noqa: BLE001
                        continue
            # Drop expired.
            out = [n for n in out if not _is_expired(n)]
            return out
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    def _save(self) -> None:
        try:
            db.kv_set_json(STORE_KEY,
                            [n.to_dict() for n in self._notifications])
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, title: str, body: str, kind: str = KIND_INFO,
            icon: Optional[str] = None,
            action_type: Optional[str] = None,
            action_payload: Optional[Dict[str, Any]] = None,
            *, expires_in_days: Optional[int] = DEFAULT_EXPIRY_DAYS,
            publish_event: bool = True) -> int:
        """Add a notification.  Returns the new notification id (0 on failure)."""
        if not title:
            return 0
        with self._lock:
            now = _now_ts()
            expires_at = None
            if expires_in_days is not None and expires_in_days > 0:
                expires_at = (_now_dt() +
                               timedelta(days=expires_in_days)).isoformat()
            nid = self._next_id
            self._next_id += 1
            n = Notification(
                id=nid,
                title=title.strip(),
                body=(body or "").strip(),
                kind=kind,
                icon=icon,
                timestamp=now,
                read=False,
                action_type=action_type,
                action_payload=action_payload,
                expires_at=expires_at,
            )
            self._notifications.insert(0, n)  # newest first
            # Trim to MAX.
            if len(self._notifications) > MAX_NOTIFICATIONS:
                self._notifications = self._notifications[:MAX_NOTIFICATIONS]
            self._save()
            if publish_event:
                bus.publish("notification.added", n.to_dict())
            self._notify_listeners("added", n)
            _log.info("Notification added: id=%d title=%r", nid, n.title)
            return nid

    def mark_read(self, id: int) -> bool:
        with self._lock:
            for n in self._notifications:
                if n.id == id:
                    if not n.read:
                        n.read = True
                        self._save()
                        self._notify_listeners("updated", n)
                    return True
            return False

    def mark_all_read(self) -> int:
        """Mark all as read.  Returns count of newly-read notifications."""
        with self._lock:
            count = 0
            for n in self._notifications:
                if not n.read:
                    n.read = True
                    count += 1
            if count:
                self._save()
                self._notify_listeners("updated_all", None)
            return count

    def delete(self, id: int) -> bool:
        with self._lock:
            for i, n in enumerate(self._notifications):
                if n.id == id:
                    del self._notifications[i]
                    self._save()
                    self._notify_listeners("deleted", n)
                    return True
            return False

    def clear_all(self) -> int:
        """Delete all notifications.  Returns count of deleted."""
        with self._lock:
            count = len(self._notifications)
            self._notifications.clear()
            self._save()
            self._notify_listeners("cleared", None)
            return count

    def clear_read(self) -> int:
        """Delete only read notifications."""
        with self._lock:
            before = len(self._notifications)
            self._notifications = [n for n in self._notifications if not n.read]
            after = len(self._notifications)
            removed = before - after
            if removed:
                self._save()
                self._notify_listeners("cleared_read", None)
            return removed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list(self, unread_only: bool = False, limit: int = 50) -> List[Notification]:
        with self._lock:
            out: List[Notification] = []
            for n in self._notifications:
                if _is_expired(n):
                    continue
                if unread_only and n.read:
                    continue
                out.append(n)
                if len(out) >= limit:
                    break
            return out

    def get(self, id: int) -> Optional[Notification]:
        with self._lock:
            for n in self._notifications:
                if n.id == id:
                    return n
            return None

    def unread_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._notifications
                       if not n.read and not _is_expired(n))

    def total_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._notifications if not _is_expired(n))

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[str, Notification], None]) -> Callable[[str, Notification], None]:
        """Register a listener.  Returns the callback.

        The callback receives (event_kind, notification_or_None).
        event_kind is one of: ``added``, ``updated``, ``updated_all``,
        ``deleted``, ``cleared``, ``cleared_read``.
        """
        with self._lock:
            self._listeners.append(callback)
        return callback

    def unsubscribe(self, callback: Callable[[str, Notification], None]) -> bool:
        with self._lock:
            try:
                self._listeners.remove(callback)
                return True
            except ValueError:
                return False

    def _notify_listeners(self, event_kind: str,
                           n: Optional[Notification]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event_kind, n)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Notification listener error: %s", exc)

    # ------------------------------------------------------------------
    # Auto-generation from events
    # ------------------------------------------------------------------

    def _auto_subscribe(self) -> None:
        """Hook into the event bus to auto-generate notifications."""
        if self._subscribed:
            return
        try:
            bus.subscribe("badge.unlocked", self._on_badge_unlocked)
            bus.subscribe("goal.progress", self._on_goal_progress)
            bus.subscribe("streak.incremented", self._on_streak_incremented)
            bus.subscribe("backup.created", self._on_backup_created)
            bus.subscribe("reminder.triggered", self._on_reminder_triggered)
            bus.subscribe("pomodoro.finished", self._on_pomodoro_finished)
            bus.subscribe("focus.ended", self._on_focus_ended)
            bus.subscribe("journal.streak_changed",
                          self._on_journal_streak_changed)
            bus.subscribe("habit.streak_changed",
                          self._on_habit_streak_changed)
            self._subscribed = True
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_badge_unlocked(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            name = d.get("name_fa") or d.get("name_en") or d.get("key", "")
            self.add(
                title="نشان جدید! 🏆",
                body=f"نشان «{name}» را دریافت کردی.",
                kind=KIND_ACHIEVEMENT,
                icon=d.get("icon", "trophy"),
                action_type="open_badges",
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_goal_progress(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            ratio = float(d.get("ratio") or d.get("progress") or 0)
            if ratio >= 1.0:
                title = d.get("title") or "هدف"
                self.add(
                    title="هدف محقق شد! ✅",
                    body=f"به هدف «{title}» رسیدی.",
                    kind=KIND_SUCCESS,
                    icon="trophy",
                    action_type="open_goals",
                )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_streak_incremented(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            current = int(d.get("current", 0))
            from ..config import STREAK_MILESTONES
            if current in STREAK_MILESTONES:
                self.add(
                    title=f"زنجیره {i18n.to_fa_digits(current)} روزه! 🔥",
                    body=(f"تو زنجیره‌ی {i18n.to_fa_digits(current)} روزه‌ای ساختی. "
                          "به زنجیره‌ات افتخار کن!"),
                    kind=KIND_ACHIEVEMENT,
                    icon="flame",
                )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_backup_created(self, payload: Any) -> None:
        try:
            self.add(
                title="پشتیبان ساخته شد 💾",
                body="پشتیبان رمزنگاری‌شده با موفقیت ایجاد شد.",
                kind=KIND_SUCCESS,
                icon="shield",
                action_type="open_backups",
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_reminder_triggered(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            title = d.get("title", "یادآوری")
            message = d.get("message", "")
            self.add(
                title=f"⏰ {title}",
                body=message or "یادآوری فعال شد.",
                kind=KIND_INFO,
                icon="bell",
                action_type="open_reminders",
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_pomodoro_finished(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            cycles = int(d.get("completed_cycles", 0))
            work_min = int(d.get("total_work_min", 0))
            self.add(
                title="پومودورو کامل! 🍅",
                body=(f"تو {i18n.to_fa_digits(cycles)} دور کار را کامل کردی "
                      f"({i18n.to_fa_digits(work_min)} دقیقه کار مفید)."),
                kind=KIND_ACHIEVEMENT,
                icon="tomato",
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_focus_ended(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            minutes = int(d.get("duration_min", 0))
            if minutes < 5:
                return
            self.add(
                title="جلسه تمرکز تمام شد 🧘",
                body=(f"تو {i18n.to_fa_digits(minutes)} دقیقه تمرکز عمیق داشتی. "
                      f"({i18n.to_fa_digits(d.get('interruption_count', 0))} وقفه)"),
                kind=KIND_SUCCESS,
                icon="focus",
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_journal_streak_changed(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            streak = int(d.get("streak", 0))
            if streak in (3, 7, 14, 30, 60, 100, 365):
                self.add(
                    title=f"زنجیره دفترچه {i18n.to_fa_digits(streak)} روزه! 📔",
                    body="نوشتن روزانه‌ات را ادامه بده — این یک عادت عالی است.",
                    kind=KIND_ACHIEVEMENT,
                    icon="book",
                )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def _on_habit_streak_changed(self, payload: Any) -> None:
        try:
            d = payload if isinstance(payload, dict) else {}
            habit_id = int(d.get("habit_id", 0))
            streak = int(d.get("streak", 0))
            if habit_id <= 0:
                return
            from .habits import habit_service
            habit = habit_service.get_habit(habit_id)
            name = habit.name if habit else "عادت"
            if streak in (7, 14, 30, 60, 100, 365):
                self.add(
                    title=f"زنجیره عادت: {i18n.to_fa_digits(streak)} روز! 🎯",
                    body=(f"عادت «{name}» را {i18n.to_fa_digits(streak)} روز متوالی "
                          "انجام داده‌ای."),
                    kind=KIND_ACHIEVEMENT,
                    icon="target",
                )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

notification_center: NotificationCenter = NotificationCenter()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== notifications_center self-tests ===")
    try:
        before = notification_center.total_count()
        nid = notification_center.add("Test", "Body text", kind=KIND_INFO)
        assert nid > 0
        assert notification_center.total_count() == before + 1
        assert notification_center.unread_count() >= 1
        notification_center.mark_read(nid)
        n = notification_center.get(nid)
        assert n is not None and n.read
        notification_center.delete(nid)
        print("  OK   basic CRUD + listeners")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
