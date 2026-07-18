"""
rask.tests.test_backup_service
==============================

Unit tests for :mod:`rask.services.backup_service`.

Covers:

  • ``create()`` writes an encrypted ``.raskbk`` file with valid magic
  • ``restore()`` round-trips data back into a fresh DB
  • ``list_local()`` enumerates files in ``BACKUP_DIR``
  • ``delete()`` removes a file
  • ``rotate()`` keeps only the N newest files
  • ``verify()`` validates password without decrypting into the DB
  • ``export_metadata()`` peeks at the header (magic, version, size,
    ciphertext length)
  • Wrong password fails gracefully (returns False / success=False)
  • Audit log entries are created on create / restore / verify
  • Event-bus publication (``backup.created`` / ``backup.restored``)
"""
from __future__ import annotations

import unittest
from pathlib import Path
from typing import List

from rask import config, database as db
from rask.core import crypto
from rask.core.event_bus import bus
from rask.services.backup_service import BackupService, backup_service
from rask.tests import fresh_db


PASSWORD = "test-password-123"


# =============================================================================
# === Helpers                                                                 ==
# =============================================================================

class _EventCollector:
    def __init__(self) -> None:
        self.events: List[tuple] = []

    def __call__(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))


def _make_backup(svc: BackupService, password: str = PASSWORD) -> str:
    """Create a backup and return its path."""
    result = svc.create(password=password)
    assert result["success"], f"Backup failed: {result.get('error')}"
    return result["path"]


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestBackupCreate(unittest.TestCase):
    """BackupService.create()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_create_returns_success_dict(self) -> None:
        result = self.svc.create(PASSWORD)
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["path"])
        self.assertGreater(result["size"], 0)
        self.assertIsNone(result["error"])

    def test_create_writes_file(self) -> None:
        result = self.svc.create(PASSWORD)
        p = Path(result["path"])
        self.assertTrue(p.is_file())
        self.assertEqual(p.stat().st_size, result["size"])

    def test_create_file_has_raskbk_extension(self) -> None:
        result = self.svc.create(PASSWORD)
        self.assertTrue(result["path"].endswith(".raskbk"))

    def test_create_uses_backup_dir_by_default(self) -> None:
        result = self.svc.create(PASSWORD)
        self.assertIn(str(config.BACKUP_DIR), result["path"])

    def test_create_with_custom_path(self) -> None:
        custom = str(config.BACKUP_DIR / "custom-backup.raskbk")
        result = self.svc.create(PASSWORD, path=custom)
        self.assertTrue(result["success"])
        self.assertEqual(result["path"], custom)

    def test_create_publishes_backup_created_event(self) -> None:
        collector = _EventCollector()
        bus.subscribe("backup.created", collector)
        self.svc.create(PASSWORD)
        self.assertEqual(len(collector.events), 1)

    def test_create_logs_to_db(self) -> None:
        self.svc.create(PASSWORD)
        cur = db.get_conn().execute(
            "SELECT * FROM backups_log WHERE kind='backup' AND success=1")
        rows = cur.fetchall()
        self.assertGreater(len(rows), 0)

    def test_create_writes_valid_magic_bytes(self) -> None:
        result = self.svc.create(PASSWORD)
        with open(result["path"], "rb") as f:
            head = f.read(4)
        self.assertEqual(head, crypto.MAGIC)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestBackupRestore(unittest.TestCase):
    """BackupService.restore() — round-trip."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_restore_round_trips_activities(self) -> None:
        # Seed some data.
        db.activity_add("A", 1, 30, "2025-01-01")
        db.activity_add("B", 1, 60, "2025-01-02")

        # Create a backup.
        path = _make_backup(self.svc)

        # Wipe the DB.
        db.get_conn().execute("DELETE FROM activities")
        db.get_conn().commit()
        self.assertEqual(db.activity_count(), 0)

        # Restore.
        result = self.svc.restore(path, PASSWORD)
        self.assertTrue(result["success"])
        self.assertEqual(db.activity_count(), 2)

    def test_restore_publishes_backup_restored_event(self) -> None:
        path = _make_backup(self.svc)
        collector = _EventCollector()
        bus.subscribe("backup.restored", collector)
        self.svc.restore(path, PASSWORD)
        self.assertEqual(len(collector.events), 1)

    def test_restore_logs_to_db(self) -> None:
        path = _make_backup(self.svc)
        self.svc.restore(path, PASSWORD)
        cur = db.get_conn().execute(
            "SELECT * FROM backups_log WHERE kind='restore' AND success=1")
        rows = cur.fetchall()
        self.assertGreater(len(rows), 0)

    def test_restore_wrong_password_fails_gracefully(self) -> None:
        path = _make_backup(self.svc)
        result = self.svc.restore(path, "wrong-password")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "wrong password")

    def test_restore_nonexistent_file_fails(self) -> None:
        result = self.svc.restore("/nonexistent/path.raskbk", PASSWORD)
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    def test_restore_corrupt_file_fails(self) -> None:
        bad_path = str(config.BACKUP_DIR / "corrupt.raskbk")
        Path(bad_path).write_bytes(b"RASK" + bytes([1]) + b"\x00" * 100)
        result = self.svc.restore(bad_path, PASSWORD)
        self.assertFalse(result["success"])


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestListLocal(unittest.TestCase):
    """BackupService.list_local()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_empty_dir_returns_empty_list(self) -> None:
        self.assertEqual(self.svc.list_local(), [])

    def test_lists_created_backups(self) -> None:
        _make_backup(self.svc)
        _make_backup(self.svc)
        backups = self.svc.list_local()
        self.assertEqual(len(backups), 2)

    def test_list_returns_dicts_with_required_fields(self) -> None:
        _make_backup(self.svc)
        backups = self.svc.list_local()
        for b in backups:
            self.assertIn("path", b)
            self.assertIn("filename", b)
            self.assertIn("size", b)
            self.assertIn("created_at", b)
            self.assertIn("valid", b)

    def test_list_sorted_newest_first(self) -> None:
        import time as _t
        _make_backup(self.svc)
        _t.sleep(1.1)  # Ensure different timestamps.
        _make_backup(self.svc)
        backups = self.svc.list_local()
        self.assertGreaterEqual(backups[0]["created_at"],
                                 backups[1]["created_at"])

    def test_list_ignores_non_raskbk_files(self) -> None:
        # Drop a non-backup file into the backup dir.
        (config.BACKUP_DIR / "not-a-backup.txt").write_text("hello")
        _make_backup(self.svc)
        backups = self.svc.list_local()
        # Only the .raskbk file should be listed.
        self.assertEqual(len(backups), 1)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestBackupDelete(unittest.TestCase):
    """BackupService.delete()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_delete_removes_file(self) -> None:
        path = _make_backup(self.svc)
        self.assertTrue(Path(path).is_file())
        self.assertTrue(self.svc.delete(path))
        self.assertFalse(Path(path).is_file())

    def test_delete_nonexistent_returns_false(self) -> None:
        self.assertFalse(self.svc.delete("/nonexistent/file.raskbk"))

    def test_delete_removes_from_list(self) -> None:
        path = _make_backup(self.svc)
        self.assertEqual(len(self.svc.list_local()), 1)
        self.svc.delete(path)
        self.assertEqual(len(self.svc.list_local()), 0)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestRotate(unittest.TestCase):
    """BackupService.rotate()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_rotate_keeps_n_newest(self) -> None:
        import time as _t
        # Create 5 backups.
        for _ in range(5):
            _make_backup(self.svc)
            _t.sleep(0.05)
        # Rotate to keep 3.
        deleted = self.svc.rotate(keep=3)
        self.assertEqual(deleted, 2)
        self.assertEqual(len(self.svc.list_local()), 3)

    def test_rotate_no_op_when_under_limit(self) -> None:
        _make_backup(self.svc)
        _make_backup(self.svc)
        deleted = self.svc.rotate(keep=10)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.svc.list_local()), 2)

    def test_rotate_keep_zero_returns_zero(self) -> None:
        _make_backup(self.svc)
        self.assertEqual(self.svc.rotate(keep=0), 0)

    def test_rotate_negative_keep_returns_zero(self) -> None:
        _make_backup(self.svc)
        self.assertEqual(self.svc.rotate(keep=-1), 0)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestVerify(unittest.TestCase):
    """BackupService.verify()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_verify_correct_password(self) -> None:
        path = _make_backup(self.svc)
        self.assertTrue(self.svc.verify(path, PASSWORD))

    def test_verify_wrong_password(self) -> None:
        path = _make_backup(self.svc)
        self.assertFalse(self.svc.verify(path, "wrong"))

    def test_verify_nonexistent_file(self) -> None:
        self.assertFalse(self.svc.verify("/nonexistent/file.raskbk", PASSWORD))

    def test_verify_corrupt_file(self) -> None:
        bad_path = str(config.BACKUP_DIR / "bad.raskbk")
        Path(bad_path).write_bytes(b"garbage data")
        self.assertFalse(self.svc.verify(bad_path, PASSWORD))

    def test_verify_does_not_modify_db(self) -> None:
        # Verify should NOT wipe or modify the DB.
        db.activity_add("Test", 1, 30, "2025-01-01")
        path = _make_backup(self.svc)
        self.svc.verify(path, PASSWORD)
        # The activity should still be there.
        self.assertEqual(db.activity_count(), 1)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestExportMetadata(unittest.TestCase):
    """BackupService.export_metadata()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_export_metadata_valid_file(self) -> None:
        path = _make_backup(self.svc)
        meta = self.svc.export_metadata(path)
        self.assertTrue(meta["valid"])
        self.assertEqual(meta["version"], crypto.VERSION)
        self.assertGreater(meta["size"], 0)
        self.assertIn("filename", meta)
        self.assertIn("created_at", meta)

    def test_export_metadata_includes_ciphertext_len(self) -> None:
        path = _make_backup(self.svc)
        meta = self.svc.export_metadata(path)
        self.assertIn("ciphertext_len", meta)
        self.assertGreater(meta["ciphertext_len"], 0)

    def test_export_metadata_nonexistent_file(self) -> None:
        meta = self.svc.export_metadata("/nonexistent/file.raskbk")
        self.assertFalse(meta["valid"])
        self.assertIn("error", meta)

    def test_export_metadata_bad_magic(self) -> None:
        bad_path = str(config.BACKUP_DIR / "bad-magic.raskbk")
        Path(bad_path).write_bytes(b"XXXX" + bytes([1]) + b"\x00" * 50)
        meta = self.svc.export_metadata(bad_path)
        self.assertFalse(meta["valid"])

    def test_export_metadata_does_not_decrypt(self) -> None:
        """export_metadata should work even with the wrong password."""
        path = _make_backup(self.svc)
        # Just verify it returns a valid dict without needing the password.
        meta = self.svc.export_metadata(path)
        self.assertTrue(meta["valid"])

    def test_export_metadata_returns_path(self) -> None:
        path = _make_backup(self.svc)
        meta = self.svc.export_metadata(path)
        self.assertEqual(meta["path"], path)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestLastBackup(unittest.TestCase):
    """last_backup() returns metadata about the most recent backup."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_last_backup_none_when_empty(self) -> None:
        self.assertIsNone(self.svc.last_backup())

    def test_last_backup_returns_metadata(self) -> None:
        _make_backup(self.svc)
        last = self.svc.last_backup()
        self.assertIsNotNone(last)
        self.assertIn("path", last)
        self.assertIn("size", last)


class TestIsAvailable(unittest.TestCase):
    """BackupService.is_available()."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)

    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(self.svc.is_available(), bool)

    def test_is_available_matches_crypto(self) -> None:
        self.assertEqual(self.svc.is_available(), crypto.is_available())


class TestModuleSingleton(unittest.TestCase):
    """Module-level singleton works."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_singleton_is_backup_service(self) -> None:
        self.assertIsInstance(backup_service, BackupService)

    def test_singleton_create_works(self) -> None:
        if not crypto.is_available():
            self.skipTest("cryptography not installed")
        result = backup_service.create(PASSWORD)
        self.assertTrue(result["success"])


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestAuditLogEntries(unittest.TestCase):
    """Audit log entries are created on each operation."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_create_writes_audit_log(self) -> None:
        self.svc.create(PASSWORD)
        cur = db.get_conn().execute(
            "SELECT * FROM backups_log WHERE kind='backup'")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["success"], 1)
        self.assertIsNotNone(rows[0]["file_path"])
        self.assertGreater(rows[0]["file_size"], 0)

    def test_restore_writes_audit_log(self) -> None:
        path = _make_backup(self.svc)
        self.svc.restore(path, PASSWORD)
        cur = db.get_conn().execute(
            "SELECT * FROM backups_log WHERE kind='restore'")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["success"], 1)

    def test_failed_restore_writes_audit_log(self) -> None:
        path = _make_backup(self.svc)
        self.svc.restore(path, "wrong-password")
        cur = db.get_conn().execute(
            "SELECT * FROM backups_log WHERE kind='restore' AND success=0")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)


@unittest.skipUnless(crypto.is_available(),
                     "cryptography package not installed")
class TestPersianDataRoundTrip(unittest.TestCase):
    """Backup / restore round-trips Persian text correctly."""

    def setUp(self) -> None:
        self._ctx = fresh_db()
        self._ctx.__enter__()
        self.svc = BackupService()
        bus.clear()

    def tearDown(self) -> None:
        self._ctx.__exit__(None, None, None)
        bus.clear()

    def test_persian_title_round_trips(self) -> None:
        db.activity_add("تمرکز عمیق", 1, 30, "2025-01-01",
                         notes="یادداشت فارسی")
        path = _make_backup(self.svc)
        # Wipe and restore.
        db.get_conn().execute("DELETE FROM activities")
        db.get_conn().commit()
        self.svc.restore(path, PASSWORD)
        # Verify Persian text is preserved.
        rows = db.activity_list()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "تمرکز عمیق")
        self.assertEqual(rows[0]["notes"], "یادداشت فارسی")

    def test_emoji_round_trips(self) -> None:
        db.activity_add("Deep work 🎯🚀", 1, 30, "2025-01-01")
        path = _make_backup(self.svc)
        db.get_conn().execute("DELETE FROM activities")
        db.get_conn().commit()
        self.svc.restore(path, PASSWORD)
        rows = db.activity_list()
        self.assertEqual(rows[0]["title"], "Deep work 🎯🚀")


if __name__ == "__main__":
    unittest.main(verbosity=2)
