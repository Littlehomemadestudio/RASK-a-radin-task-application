"""
rask.services.backup_service
============================

Encrypted backup / restore.

Wraps :mod:`rask.core.crypto` to provide a high-level API:

  • :meth:`create` — encrypt the DB to a ``.raskbk`` file
  • :meth:`restore` — decrypt a backup file and replace the DB
  • :meth:`list_local` — enumerate backups in :data:`config.BACKUP_DIR`
  • :meth:`delete` — remove a backup file
  • :meth:`rotate` — keep only the N most-recent backups
  • :meth:`verify` — check that a password decrypts the file
  • :meth:`export_metadata` — peek at the header without decryption

Every operation is logged via :func:`rask.database.log_backup` and
publishes events (``backup.created`` / ``backup.restored``).

File-name format: ``config.BACKUP_FILENAME_FMT``
(e.g. ``rask-backup-20250718-143022.raskbk``).

Mirrors ``web/js/backup.js`` byte-for-byte (the crypto format is the
same so backup files are interoperable between desktop and web).
"""
from __future__ import annotations

import os
import struct
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core import crypto
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_utc

__all__ = ["BackupService", "backup_service"]

_log = get_logger("services.backup")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _is_backup_file(p: Path) -> bool:
    """Return True if `p` looks like a Rask backup file."""
    return p.is_file() and p.suffix.lower() == ".raskbk"


def _filename_timestamp() -> str:
    """Return a timestamp string for use in a backup filename."""
    return datetime.now().strftime(config.BACKUP_TIMESTAMP_FMT)


def _file_size(path: Path) -> int:
    """Return file size in bytes (0 if missing)."""
    try:
        return path.stat().st_size
    except (OSError, AttributeError):
        return 0


# =============================================================================
# === BackupService                                                          ===
# =============================================================================

class BackupService:
    """Encrypted backup / restore with rotation."""

    def __init__(self) -> None:
        # Ensure BACKUP_DIR exists.
        try:
            config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """No-op init for symmetry."""
        _log.debug("BackupService initialized (dir=%s)", config.BACKUP_DIR)

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the cryptography package is importable."""
        return crypto.is_available()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, password: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Create an encrypted backup file.

        Parameters
        ----------
        password : str
            Encryption password (≥ 6 chars).
        path : str, optional
            Output file path.  Defaults to
            ``BACKUP_DIR / BACKUP_FILENAME_FMT.format(ts=<now>)``.

        Returns
        -------
        dict
            ``{"path": str, "size": int, "timestamp": str, "success": bool,
              "error": Optional[str]}``
        """
        if not self.is_available():
            msg = "cryptography package not available"
            _log.error(msg)
            db.log_backup("backup", None, None, False, msg)
            return {"path": None, "size": 0, "timestamp": now_iso_utc(),
                    "success": False, "error": msg}

        try:
            raw = db.export_to_dict()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            db.log_backup("backup", None, None, False, str(exc))
            return {"path": None, "size": 0, "timestamp": now_iso_utc(),
                    "success": False, "error": str(exc)}

        # crypto.decrypt_backup requires a top-level "activities" key
        # (it mirrors the web PWA's payload shape).  db.export_to_dict
        # wraps the table data in a "data" sub-dict, so flatten it
        # here before encryption — the meta block is preserved as a
        # sibling key alongside the table arrays.
        if "data" in raw and "activities" not in raw:
            data = dict(raw.get("data", {}))
            # Preserve the meta block if present.
            if "meta" in raw:
                data["_meta_db"] = raw["meta"]
        else:
            data = raw

        # Determine output path.
        if path:
            out_path = Path(path)
        else:
            filename = config.BACKUP_FILENAME_FMT.format(
                ts=_filename_timestamp())
            out_path = config.BACKUP_DIR / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            blob = crypto.encrypt_backup(data, password)
            out_path.write_bytes(blob)
        except crypto.BackupError as exc:
            log_exception(_log, exc, {"path": str(out_path)})
            db.log_backup("backup", str(out_path), None, False, str(exc))
            return {"path": str(out_path), "size": 0,
                    "timestamp": now_iso_utc(),
                    "success": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": str(out_path)})
            db.log_backup("backup", str(out_path), None, False, str(exc))
            return {"path": str(out_path), "size": 0,
                    "timestamp": now_iso_utc(),
                    "success": False, "error": str(exc)}

        size = _file_size(out_path)
        ts = now_iso_utc()
        db.log_backup("backup", str(out_path), size, True, None)

        # Update last_backup setting.
        try:
            from .settings_service import settings_service
            settings_service.set_last_backup_iso(ts)
        except Exception:  # noqa: BLE001
            pass

        # Run rotation to enforce BACKUP_KEEP_LOCAL.
        try:
            self.rotate(keep=config.BACKUP_KEEP_LOCAL)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        result = {
            "path": str(out_path),
            "size": size,
            "timestamp": ts,
            "success": True,
            "error": None,
        }
        bus.publish("backup.created", result)
        _log.info("Backup created: %s (%d bytes)", out_path, size)
        return result

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, path: str, password: str) -> Dict[str, Any]:
        """Restore a backup file, replacing the current DB.

        Returns ``{"success": bool, "error": Optional[str],
        "timestamp": str, "path": str, "record_count": Optional[int]}``.
        """
        if not self.is_available():
            msg = "cryptography package not available"
            db.log_backup("restore", path, None, False, msg)
            return {"success": False, "error": msg,
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}

        p = Path(path)
        if not p.is_file():
            msg = f"Backup file not found: {path}"
            db.log_backup("restore", path, None, False, msg)
            return {"success": False, "error": msg,
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}

        try:
            blob = p.read_bytes()
        except OSError as exc:
            db.log_backup("restore", path, None, False, str(exc))
            return {"success": False, "error": str(exc),
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}

        try:
            payload = crypto.decrypt_backup(blob, password)
        except crypto.WrongPasswordError as exc:
            db.log_backup("restore", path, None, False, "wrong password")
            return {"success": False, "error": "wrong password",
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}
        except crypto.CorruptBackupError as exc:
            db.log_backup("restore", path, None, False, str(exc))
            return {"success": False, "error": str(exc),
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_backup("restore", path, None, False, str(exc))
            return {"success": False, "error": str(exc),
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}

        try:
            db.import_from_dict(payload, replace=True)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            db.log_backup("restore", path, None, False, str(exc))
            return {"success": False, "error": str(exc),
                    "timestamp": now_iso_utc(), "path": path,
                    "record_count": None}

        # Count restored records.
        record_count = 0
        try:
            data = payload.get("data", payload)
            if isinstance(data, dict):
                for table_rows in data.values():
                    if isinstance(table_rows, list):
                        record_count += len(table_rows)
        except Exception:  # noqa: BLE001
            pass

        ts = now_iso_utc()
        db.log_backup("restore", path, _file_size(p), True, None)

        result = {
            "success": True,
            "error": None,
            "timestamp": ts,
            "path": path,
            "record_count": record_count,
        }
        bus.publish("backup.restored", result)
        _log.info("Backup restored from %s (%d records)", path, record_count)
        return result

    # ------------------------------------------------------------------
    # Verify (no DB write)
    # ------------------------------------------------------------------

    def verify(self, path: str, password: str) -> bool:
        """Return True if `password` decrypts the file at `path`."""
        if not self.is_available():
            return False
        p = Path(path)
        if not p.is_file():
            return False
        try:
            blob = p.read_bytes()
            crypto.decrypt_backup(blob, password)
            return True
        except crypto.BackupError:
            return False
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Metadata peek (no decryption)
    # ------------------------------------------------------------------

    def export_metadata(self, path: str) -> Dict[str, Any]:
        """Peek at the backup file header without decryption.

        Returns a dict with ``{valid, version, size, filename,
        created_at}``.  ``valid`` is False if the file is not a
        recognizable Rask backup.
        """
        p = Path(path)
        if not p.is_file():
            return {"valid": False, "error": "file not found",
                    "path": str(p)}
        try:
            size = p.stat().st_size
            mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        except OSError as exc:
            return {"valid": False, "error": str(exc), "path": str(p)}

        try:
            with p.open("rb") as f:
                head = f.read(37)
        except OSError as exc:
            return {"valid": False, "error": str(exc),
                    "path": str(p), "size": size}

        if len(head) < 37 or head[:4] != crypto.MAGIC:
            return {"valid": False, "error": "bad magic bytes",
                    "path": str(p), "size": size}

        version = head[4]
        try:
            ct_len = struct.unpack(">I", head[33:37])[0]
        except struct.error:
            ct_len = 0

        return {
            "valid": True,
            "version": version,
            "size": size,
            "ciphertext_len": ct_len,
            "filename": p.name,
            "path": str(p),
            "created_at": mtime,
        }

    # ------------------------------------------------------------------
    # Listing / deletion / rotation
    # ------------------------------------------------------------------

    def list_local(self) -> List[Dict[str, Any]]:
        """List all backup files in :data:`config.BACKUP_DIR`.

        Returns a list of dicts (newest first):
            ``{"path": str, "filename": str, "size": int,
              "created_at": str, "valid": bool, "version": int}``
        """
        out: List[Dict[str, Any]] = []
        try:
            for entry in config.BACKUP_DIR.iterdir():
                if not _is_backup_file(entry):
                    continue
                meta = self.export_metadata(str(entry))
                out.append({
                    "path": str(entry),
                    "filename": entry.name,
                    "size": meta.get("size", 0),
                    "created_at": meta.get("created_at", ""),
                    "valid": meta.get("valid", False),
                    "version": meta.get("version"),
                })
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

        # Sort by created_at descending (newest first).
        out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return out

    def delete(self, path: str) -> bool:
        """Delete a backup file.  Returns True on success."""
        p = Path(path)
        try:
            if not p.is_file():
                return False
            p.unlink()
            _log.info("Backup deleted: %s", path)
            return True
        except OSError as exc:
            log_exception(_log, exc, {"path": path})
            return False

    def rotate(self, keep: int = 10) -> int:
        """Keep only the `keep` most-recent backups.

        Returns the number of deleted files.
        """
        if keep <= 0:
            return 0
        backups = self.list_local()
        if len(backups) <= keep:
            return 0
        to_delete = backups[keep:]
        deleted = 0
        for b in to_delete:
            if self.delete(b["path"]):
                deleted += 1
        if deleted:
            _log.info("Rotated: deleted %d old backups (kept %d)",
                      deleted, keep)
        return deleted

    # ------------------------------------------------------------------
    # Auto-backup scheduling
    # ------------------------------------------------------------------

    def schedule_auto(self, when: str = "off") -> None:
        """Set the auto-backup frequency.

        `when` is one of: ``"off"``, ``"daily"``, ``"weekly"``,
        ``"monthly"``.  The actual scheduling is performed by the
        app's main loop (it calls :meth:`maybe_run_auto` periodically).
        """
        try:
            from .settings_service import settings_service
            settings_service.set_auto_backup(when)
            _log.info("Auto-backup schedule set to %r", when)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})

    def last_backup(self) -> Optional[Dict[str, Any]]:
        """Return metadata about the most recent backup, or ``None``."""
        backups = self.list_local()
        return backups[0] if backups else None

    def next_scheduled(self) -> Optional[str]:
        """Return the ISO date of the next scheduled auto-backup, or ``None``."""
        try:
            from .settings_service import settings_service
            schedule = settings_service.auto_backup()
        except Exception:  # noqa: BLE001
            return None
        if schedule == "off":
            return None
        last = None
        try:
            from .settings_service import settings_service
            last = settings_service.last_backup_iso()
        except Exception:  # noqa: BLE001
            pass
        if not last:
            # If never backed up, schedule for today.
            return datetime.now().strftime("%Y-%m-%d")
        try:
            last_dt = datetime.fromisoformat(last.split("T")[0])
        except (ValueError, TypeError):
            return None
        if schedule == "daily":
            delta_days = 1
        elif schedule == "weekly":
            delta_days = 7
        elif schedule == "monthly":
            delta_days = 30
        else:
            return None
        next_dt = last_dt + (datetime.now() - last_dt)
        # Round to next occurrence of the schedule.
        from datetime import timedelta
        if schedule == "daily":
            next_dt = datetime.now() + timedelta(days=1)
        elif schedule == "weekly":
            next_dt = datetime.now() + timedelta(days=7)
        elif schedule == "monthly":
            next_dt = datetime.now() + timedelta(days=30)
        return next_dt.strftime("%Y-%m-%d")

    def maybe_run_auto(self) -> Optional[Dict[str, Any]]:
        """Check if an auto-backup is due and run it.

        Returns the result of :meth:`create` if a backup was made, or
        ``None`` if no backup was due.  Called periodically by the
        app's main loop.

        Note: this method does NOT prompt for a password — it uses
        the persisted PIN hash (if available) as the backup password.
        If no PIN is set, auto-backup is skipped.
        """
        try:
            from .settings_service import settings_service
            schedule = settings_service.auto_backup()
        except Exception:  # noqa: BLE001
            return None
        if schedule == "off":
            return None

        next_scheduled = self.next_scheduled()
        if next_scheduled is None:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        if next_scheduled > today:
            return None  # not due yet

        # Need a password — use PIN hash if available.
        try:
            pin = settings_service.pin_hash()
        except Exception:  # noqa: BLE001
            pin = None
        if not pin:
            _log.warning("Auto-backup skipped: no PIN set")
            return None

        return self.create(password=pin)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

backup_service: BackupService = BackupService()
