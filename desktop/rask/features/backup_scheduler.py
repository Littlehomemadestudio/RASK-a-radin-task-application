"""
rask.features.backup_scheduler
==============================

Periodic backup scheduler.

Wraps :class:`rask.services.backup_service.BackupService` with a
CustomTkinter-friendly scheduler that:

  • Periodically (every 30 minutes) checks if a backup is due
  • Respects the user's auto-backup setting (off / daily / weekly /
    monthly) via ``settings_service.auto_backup()``
  • Caches the backup password (asks the user once via a UI dialog,
    stores a hash in the kv store, prompts to re-enter if invalid)
  • Logs every check / run via :meth:`backup_service.create`
  • Publishes events when a backup is created or skipped

The scheduler is designed to be started from the main app's boot
sequence:

    from rask.features.backup_scheduler import backup_scheduler
    backup_scheduler.start(root_widget)  # root is the CTk app

And stopped on shutdown:

    backup_scheduler.stop()

Events
------

  ``backup_scheduler.started``  — {interval_sec}
  ``backup_scheduler.stopped``  — {}
  ``backup_scheduler.checked``  — {due: bool, next_run: str | None}
  ``backup_scheduler.skipped``  — {reason: str}
  ``backup_scheduler.run_started`` — {}
  ``backup_scheduler.run_completed`` — {success: bool, path: str | None,
                                          error: str | None}
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from .. import database as db
from .. import i18n
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception

__all__ = [
    "BackupScheduler",
    "backup_scheduler",
    "PASSWORD_HASH_KEY",
    "DEFAULT_INTERVAL_SEC",
]

_log = get_logger("features.backup_scheduler")


# =============================================================================
# === Constants                                                              ===
# =============================================================================

#: Kv-store key for the cached backup password hash.
PASSWORD_HASH_KEY: str = "backup_scheduler.password_hash"

#: Default check interval (30 min).
DEFAULT_INTERVAL_SEC: int = 30 * 60

#: How long to cache the password in memory (4 hours).
PASSWORD_CACHE_TTL_SEC: int = 4 * 60 * 60


# =============================================================================
# === Helpers                                                                ===
# =============================================================================

def _hash_password(password: str) -> str:
    """SHA-256 hash a password (for verification, not storage of the
    password itself)."""
    if not password:
        return ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# =============================================================================
# === BackupScheduler                                                        ===
# =============================================================================

class BackupScheduler:
    """Periodic backup scheduler.

    Module-level singleton :data:`backup_scheduler`.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._root: Any = None
        self._interval_sec: int = DEFAULT_INTERVAL_SEC
        self._after_id: Optional[str] = None
        self._running: bool = False
        # In-memory password cache.
        self._cached_password: Optional[str] = None
        self._cached_password_at: float = 0.0
        self._password_prompt_callback: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, root_widget: Any = None,
              *, interval_sec: Optional[int] = None) -> None:
        """Start the scheduler.  `root_widget` is the CTk app instance
        (used to schedule ``after()`` callbacks).  If `root_widget` is
        ``None``, the scheduler runs in a daemon thread instead.
        """
        with self._lock:
            if self._running:
                _log.warning("BackupScheduler already running")
                return
            self._root = root_widget
            if interval_sec is not None:
                self._interval_sec = max(60, int(interval_sec))
            self._running = True
            bus.publish("backup_scheduler.started",
                        {"interval_sec": self._interval_sec})
            _log.info("BackupScheduler started (interval=%ds)",
                       self._interval_sec)
            if root_widget is not None:
                self._schedule_next_ctk()
            else:
                t = threading.Thread(target=self._thread_loop, daemon=True)
                t.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._after_id is not None and self._root is not None:
                try:
                    self._root.after_cancel(self._after_id)
                except Exception:  # noqa: BLE001
                    pass
                self._after_id = None
            bus.publish("backup_scheduler.stopped", {})
            _log.info("BackupScheduler stopped")

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_next_ctk(self) -> None:
        """Schedule the next check using CTk's after()."""
        if not self._running or self._root is None:
            return
        try:
            ms = self._interval_sec * 1000
            self._after_id = self._root.after(ms, self._on_tick_ctk)
        except Exception as exc:  # noqa: BLE001
            _log.warning("CTk after() failed: %s", exc)

    def _on_tick_ctk(self) -> None:
        try:
            self.check_and_run()
        finally:
            if self._running:
                self._schedule_next_ctk()

    def _thread_loop(self) -> None:
        while self._running:
            try:
                self.check_and_run()
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
            # Sleep in small chunks so we can exit quickly on stop().
            slept = 0.0
            while slept < self._interval_sec and self._running:
                time.sleep(min(1.0, self._interval_sec - slept))
                slept += 1.0

    # ------------------------------------------------------------------
    # Check + run
    # ------------------------------------------------------------------

    def check_and_run(self) -> Optional[Dict[str, Any]]:
        """Check if a backup is due and run it if so.

        Returns the backup result dict if a backup was made, or
        ``None`` if no backup was due / scheduler is disabled.
        """
        with self._lock:
            if not self._running:
                return None
            try:
                from ..services.settings_service import settings_service
                schedule = settings_service.auto_backup()
            except Exception:  # noqa: BLE001
                schedule = "off"
            if schedule == "off":
                bus.publish("backup_scheduler.checked",
                            {"due": False, "next_run": None, "reason": "off"})
                return None
            next_run = self.next_run()
            today = datetime.now().strftime("%Y-%m-%d %H:%M")
            due = (next_run is None) or (next_run <= today)
            bus.publish("backup_scheduler.checked",
                        {"due": due, "next_run": next_run})
            if not due:
                bus.publish("backup_scheduler.skipped",
                            {"reason": "not_due_yet",
                             "next_run": next_run})
                return None
            # Get the password.
            password = self._get_password()
            if not password:
                bus.publish("backup_scheduler.skipped",
                            {"reason": "no_password"})
                _log.info("Auto-backup skipped: no password available")
                return None
            # Run the backup.
            bus.publish("backup_scheduler.run_started", {})
            try:
                from ..services.backup_service import backup_service
                result = backup_service.create(password)
                success = bool(result.get("success"))
                path = result.get("path")
                error = result.get("error")
                bus.publish("backup_scheduler.run_completed",
                            {"success": success, "path": path,
                             "error": error})
                if success:
                    _log.info("Auto-backup created: %s", path)
                    # Update the last-backup timestamp.
                    try:
                        from ..services.settings_service import settings_service
                        settings_service.set_last_backup_iso(
                            datetime.utcnow().isoformat())
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    _log.warning("Auto-backup failed: %s", error)
                    # If the password was invalid, clear the cache so
                    # the user is re-prompted next time.
                    if "password" in (error or "").lower():
                        self._cached_password = None
                        self._cached_password_at = 0.0
                return result
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
                bus.publish("backup_scheduler.run_completed",
                            {"success": False, "path": None,
                             "error": str(exc)})
                return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def set_password(self, password: str) -> None:
        """Cache a backup password (in memory + hash in kv store)."""
        with self._lock:
            self._cached_password = password
            self._cached_password_at = time.time()
            try:
                db.kv_set(PASSWORD_HASH_KEY, _hash_password(password))
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})

    def clear_password(self) -> None:
        """Clear the cached password."""
        with self._lock:
            self._cached_password = None
            self._cached_password_at = 0.0
            try:
                db.kv_delete(PASSWORD_HASH_KEY)
            except Exception:  # noqa: BLE001
                pass

    def has_password(self) -> bool:
        """Return True if a password is cached (in memory) and not expired."""
        with self._lock:
            if not self._cached_password:
                return False
            age = time.time() - self._cached_password_at
            if age > PASSWORD_CACHE_TTL_SEC:
                return False
            return True

    def _get_password(self) -> Optional[str]:
        """Return the cached password, or None if not available / expired."""
        with self._lock:
            if self._cached_password and (
                    time.time() - self._cached_password_at < PASSWORD_CACHE_TTL_SEC):
                return self._cached_password
            # No cached password — return None (the UI is responsible
            # for prompting the user).
            return None

    def set_password_prompt_callback(self,
                                       cb: Callable[[str], None]) -> None:
        """Register a callback that the scheduler will invoke when it
        needs a password.

        The callback receives a "reason" string ("initial" / "expired"
        / "invalid") and is expected to call :meth:`set_password` when
        the user provides one.  This decoupling lets the scheduler
        work headlessly (no callback) or with a UI dialog.
        """
        with self._lock:
            self._password_prompt_callback = cb

    # ------------------------------------------------------------------
    # Schedule queries
    # ------------------------------------------------------------------

    def next_run(self) -> Optional[str]:
        """Return the ISO datetime of the next scheduled backup.

        Returns ``None`` if auto-backup is off.
        """
        try:
            from ..services.backup_service import backup_service
            return backup_service.next_scheduled()
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..services.settings_service import settings_service
            schedule = settings_service.auto_backup()
        except Exception:  # noqa: BLE001
            return None
        if schedule == "off":
            return None
        try:
            last = settings_service.last_backup_iso()
        except Exception:  # noqa: BLE001
            last = None
        if not last:
            return datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            last_dt = datetime.fromisoformat(last.split("T")[0])
        except (ValueError, TypeError):
            return None
        if schedule == "daily":
            delta = timedelta(days=1)
        elif schedule == "weekly":
            delta = timedelta(days=7)
        elif schedule == "monthly":
            delta = timedelta(days=30)
        else:
            return None
        return (last_dt + delta).strftime("%Y-%m-%d %H:%M")

    def last_run(self) -> Optional[str]:
        """Return the ISO datetime of the last backup, or None."""
        try:
            from ..services.settings_service import settings_service
            return settings_service.last_backup_iso()
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._running

    def interval_sec(self) -> int:
        return self._interval_sec


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

backup_scheduler: BackupScheduler = BackupScheduler()


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== backup_scheduler self-tests ===")
    try:
        assert not backup_scheduler.is_running()
        # Start with thread mode (no root_widget).
        backup_scheduler.start(interval_sec=60)
        assert backup_scheduler.is_running()
        backup_scheduler.stop()
        assert not backup_scheduler.is_running()
        # Password caching.
        backup_scheduler.set_password("test123")
        assert backup_scheduler.has_password()
        backup_scheduler.clear_password()
        assert not backup_scheduler.has_password()
        print("  OK   lifecycle + password caching")
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
