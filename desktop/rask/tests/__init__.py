"""
rask.tests
==========

Comprehensive test suite for the Rask desktop application.

Organized as 15 ``test_*.py`` modules covering:

  • Core utilities — Jalali calendar, crypto, PIN hashing, time
    formatting, validators, helpers
  • Persistence layer — database CRUD, aggregations, settings
  • Service layer — activity, goal, stats, backup, export, timer
  • End-to-end integration workflows

Run the whole suite with::

    python -m rask.tests.run_tests

Or run a single module with::

    python -m rask.tests.test_jalali
    python -m rask.tests.test_crypto

Tests use only the standard-library ``unittest`` framework plus
``unittest.mock`` for stubs — no third-party test runner is required.
All tests are headless (no Tkinter display) and use temporary
databases / files created via the ``tempfile`` module.

The :func:`fresh_db` helper (re-exported here for convenience) creates
a brand-new empty SQLite database in a temp directory and wires
``rask.config.DB_PATH`` / ``rask.database`` to use it.  Each test that
touches the database should call it in ``setUp``.
"""
from __future__ import annotations

import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .. import config
from .. import database as db


__all__ = ["fresh_db", "isolated_config"]


_lock = threading.RLock()


@contextmanager
def fresh_db() -> Iterator[Path]:
    """Yield a fresh empty DB path, wired into ``rask.config`` / ``rask.database``.

    The DB is created in a temp directory, schema is applied via
    :func:`rask.database.open_db`, and on exit the connection is closed
    and the temp directory is removed.

    Example
    -------
    >>> with fresh_db() as db_path:
    ...     db.activity_add("Test", None, 30, "2025-01-01")
    ...     assert db.activity_count() == 1
    """
    with _lock:
        # Close any cached connection from a previous test.
        try:
            db.close_all()
        except Exception:  # noqa: BLE001
            pass

        with tempfile.TemporaryDirectory(prefix="rask-test-") as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "test.db"
            # Also rebind the parent directories so that backup/export
            # services write into the temp dir.
            old_db_path = config.DB_PATH
            old_backup_dir = config.BACKUP_DIR
            old_export_dir = config.EXPORT_DIR
            old_log_dir = config.LOG_DIR
            old_cache_dir = config.CACHE_DIR
            old_data_dir = config.DATA_DIR

            config.DB_PATH = db_path
            config.BACKUP_DIR = tmp_path / "backups"
            config.EXPORT_DIR = tmp_path / "exports"
            config.LOG_DIR = tmp_path / "logs"
            config.CACHE_DIR = tmp_path / "cache"
            config.DATA_DIR = tmp_path
            for d in (config.BACKUP_DIR, config.EXPORT_DIR,
                      config.LOG_DIR, config.CACHE_DIR):
                try:
                    d.mkdir(parents=True, exist_ok=True)
                except Exception:  # noqa: BLE001
                    pass

            # Open + seed the new DB.
            db.open_db()

            try:
                yield db_path
            finally:
                # Restore config and close the connection.
                try:
                    db.close_all()
                except Exception:  # noqa: BLE001
                    pass
                config.DB_PATH = old_db_path
                config.BACKUP_DIR = old_backup_dir
                config.EXPORT_DIR = old_export_dir
                config.LOG_DIR = old_log_dir
                config.CACHE_DIR = old_cache_dir
                config.DATA_DIR = old_data_dir


@contextmanager
def isolated_config(**overrides: object) -> Iterator[None]:
    """Temporarily override attributes on :mod:`rask.config`.

    Restores the original values on exit, even if the test raises.
    """
    saved: dict[str, object] = {}
    try:
        for k, v in overrides.items():
            saved[k] = getattr(config, k)
            setattr(config, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(config, k, v)
