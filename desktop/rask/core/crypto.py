"""
rask.core.crypto
================

AES-256-GCM encrypted backup / restore for the Rask desktop app.

The on-disk binary format is **byte-for-byte compatible** with the web
PWA's ``web/js/backup.js`` so that backup files can be exchanged freely
between the two products:

    +-----------+----------+----------------------------------+
    | offset    | length   | contents                         |
    +===========+==========+==================================+
    | 0         | 4        | magic bytes  b"RASK"             |
    | 4         | 1        | version byte (currently 1)       |
    | 5         | 16       | PBKDF2 salt                      |
    | 21        | 12       | AES-GCM nonce / IV               |
    | 33        | 4        | ciphertext length (uint32 BE)    |
    | 37        | N        | ciphertext + 16-byte GCM auth tag|
    +-----------+----------+----------------------------------+

Key derivation: PBKDF2-HMAC-SHA256, 200,000 iterations, 32-byte key.
Cipher: AES-256-GCM (authenticated encryption).

The ``cryptography`` package is required.  If it is missing, every
public function raises :class:`BackupUnavailable` with a helpful
installation hint — Rask will still run, but encrypted backups will be
disabled.  PIN hashing (in ``rask.core.pin``) provides a stdlib fallback.
"""
from __future__ import annotations

import json
import os
import struct
import time
from typing import Any, Dict, Optional, Tuple, Union

from .. import config

__all__ = [
    "BackupError",
    "BackupUnavailable",
    "WrongPasswordError",
    "CorruptBackupError",
    "MAGIC",
    "VERSION",
    "encrypt_backup",
    "decrypt_backup",
    "derive_key",
    "generate_salt",
    "generate_iv",
    "is_available",
]

# =============================================================================
# === Constants (mirror web/js/backup.js)                                    ===
# =============================================================================

#: 4-byte file magic at the start of every backup.
MAGIC: bytes = config.BACKUP_MAGIC  # b"RASK"

#: Backup format version (currently 1).
VERSION: int = config.BACKUP_VERSION

#: PBKDF2 iteration count.
KDF_ITERATIONS: int = config.BACKUP_KDF_ITERATIONS  # 200_000

#: PBKDF2 hash algorithm name (as accepted by ``cryptography``).
KDF_HASH: str = config.BACKUP_KDF_HASH  # "sha256"

#: Salt length in bytes.
SALT_LEN: int = config.BACKUP_SALT_LEN  # 16

#: AES-GCM IV / nonce length in bytes.
IV_LEN: int = config.BACKUP_IV_LEN  # 12

#: Derived AES key length in bytes (AES-256).
KEY_LEN: int = config.BACKUP_KEY_LEN  # 32

#: Length of the GCM authentication tag appended to the ciphertext.
GCM_TAG_LEN: int = 16

#: Minimum password length (mirror web/js/backup.js convention).
MIN_PASSWORD_LEN: int = 6


# =============================================================================
# === Exceptions                                                             ===
# =============================================================================

class BackupError(Exception):
    """Base class for all backup-related errors."""


class BackupUnavailable(BackupError):
    """Raised when the ``cryptography`` package is not installed.

    Rask can still run without it — only encrypted backup / restore
    is disabled.  Catch this to show a friendly message in the UI.
    """


class WrongPasswordError(BackupError):
    """Raised when decryption fails due to an incorrect password.

    AES-GCM's authentication tag also catches corrupted ciphertext,
    so this is raised for both wrong-password and tampering cases.
    """


class CorruptBackupError(BackupError):
    """Raised when the backup blob is structurally invalid.

    Causes include: bad magic bytes, unsupported version, truncated
    header, or a ciphertext-length field that exceeds the blob.
    """


# =============================================================================
# === Optional cryptography import                                          ===
# =============================================================================

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without cryptography
    _CRYPTO_AVAILABLE = False
    AESGCM = None  # type: ignore[assignment,misc]
    PBKDF2HMAC = None  # type: ignore[assignment,misc]
    hashes = None  # type: ignore[assignment]


def is_available() -> bool:
    """Return True if the ``cryptography`` package is importable."""
    return _CRYPTO_AVAILABLE


def _require_crypto() -> None:
    """Raise :class:`BackupUnavailable` if ``cryptography`` is missing."""
    if not _CRYPTO_AVAILABLE:
        raise BackupUnavailable(
            "The 'cryptography' package is required for encrypted backups. "
            "Install it with:  pip install cryptography"
        )


# =============================================================================
# === Key / IV / salt generation                                            ===
# =============================================================================

def generate_salt() -> bytes:
    """Return a cryptographically secure random 16-byte salt.

    Uses ``os.urandom`` for portability — the same source the web PWA
    uses via ``crypto.getRandomValues``.
    """
    return os.urandom(SALT_LEN)


def generate_iv() -> bytes:
    """Return a cryptographically secure random 12-byte AES-GCM nonce.

    A fresh IV **must** be used for every encryption; reusing an IV
    with the same key catastrophically breaks AES-GCM's authenticity
    guarantees.
    """
    return os.urandom(IV_LEN)


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte AES-256 key from `password` and `salt`.

    Uses PBKDF2-HMAC-SHA256 with 200,000 iterations — identical to
    the web PWA so backup files are interoperable.

    Parameters
    ----------
    password : str
        User-supplied passphrase.  Empty / ``None`` raises ``ValueError``.
    salt : bytes
        16-byte salt.  Length is enforced.

    Returns
    -------
    bytes
        32-byte raw AES-256 key.
    """
    _require_crypto()
    if not password:
        raise ValueError("password must be a non-empty string")
    if not isinstance(salt, (bytes, bytearray)) or len(salt) != SALT_LEN:
        raise ValueError(f"salt must be {SALT_LEN} bytes, got {len(salt) if salt else 0}")
    kdf = PBKDF2HMAC(  # type: ignore[misc]
        algorithm=hashes.SHA256(),  # type: ignore[union-attr]
        length=KEY_LEN,
        salt=bytes(salt),
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


# =============================================================================
# === Encrypt / decrypt                                                      ===
# =============================================================================

def _build_header(salt: bytes, iv: bytes, ct_len: int) -> bytes:
    """Pack the fixed-length backup header (37 bytes)."""
    return (
        MAGIC
        + bytes([VERSION])
        + bytes(salt)
        + bytes(iv)
        + struct.pack(">I", ct_len)
    )


def _parse_header(blob: bytes) -> Tuple[bytes, bytes, int, int]:
    """Parse the backup header; return ``(salt, iv, ct_len, body_offset)``.

    Raises :class:`CorruptBackupError` on any structural problem.
    """
    if len(blob) < 37:
        raise CorruptBackupError(
            f"Backup blob too short: {len(blob)} bytes (need ≥ 37)"
        )
    if blob[:4] != MAGIC:
        raise CorruptBackupError(
            "Not a Rask backup file (bad magic bytes)."
        )
    ver = blob[4]
    if ver != VERSION:
        raise CorruptBackupError(
            f"Unsupported backup version {ver} (expected {VERSION})."
        )
    salt = bytes(blob[5:5 + SALT_LEN])
    iv = bytes(blob[5 + SALT_LEN:5 + SALT_LEN + IV_LEN])
    ct_len = struct.unpack(">I", blob[33:37])[0]
    body_offset = 37
    if body_offset + ct_len > len(blob):
        raise CorruptBackupError(
            f"Ciphertext length {ct_len} exceeds blob body "
            f"({len(blob) - body_offset} bytes available)."
        )
    return salt, iv, ct_len, body_offset


def encrypt_backup(data: Dict[str, Any], password: str) -> bytes:
    """Encrypt `data` into a Rask backup blob.

    The dict is JSON-serialized with a ``_meta`` block recording the
    format version and export timestamp, then AES-256-GCM encrypted.

    Parameters
    ----------
    data : dict
        Arbitrary JSON-serializable payload (typically the output of
        ``rask.database.export_all``).
    password : str
        User passphrase.  Must be ≥ 6 characters (matches the web UI's
        minimum to avoid trivially-weak passwords).

    Returns
    -------
    bytes
        The packed backup blob (header + ciphertext + auth tag).

    Raises
    ------
    BackupUnavailable
        If ``cryptography`` is not installed.
    ValueError
        If `password` is too short or `data` is not JSON-serializable.
    """
    _require_crypto()
    if not isinstance(data, dict):
        raise ValueError(f"data must be a dict, got {type(data).__name__}")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(
            f"password must be at least {MIN_PASSWORD_LEN} characters"
        )

    # Augment the payload with a meta block (mirror web/js/backup.js).
    payload = dict(data)
    payload["_meta"] = {
        "version": VERSION,
        "app_version": config.APP_VERSION,
        "exported_at": _now_iso_utc(),
    }

    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    salt = generate_salt()
    iv = generate_iv()
    key = derive_key(password, salt)

    # AESGCM.encrypt appends the 16-byte tag to the ciphertext.
    aead = AESGCM(key)  # type: ignore[misc]
    ciphertext = aead.encrypt(iv, plaintext, associated_data=None)

    header = _build_header(salt, iv, len(ciphertext))
    return header + ciphertext


def decrypt_backup(blob: bytes, password: str) -> Dict[str, Any]:
    """Decrypt a Rask backup blob and return the payload dict.

    Parameters
    ----------
    blob : bytes
        Bytes previously produced by :func:`encrypt_backup` (or by the
        web PWA's ``RaskBackup.exportToBytes``).
    password : str
        User passphrase.  Must match the one used to encrypt.

    Returns
    -------
    dict
        The decrypted payload, with the ``_meta`` block left in place
        (callers can read or strip it as they like).

    Raises
    ------
    BackupUnavailable
        If ``cryptography`` is not installed.
    CorruptBackupError
        If the blob is structurally invalid (bad magic, version, length).
    WrongPasswordError
        If the password is wrong OR the ciphertext has been tampered
        with — AES-GCM's authentication tag cannot distinguish the two.
    """
    _require_crypto()
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise ValueError(f"blob must be bytes-like, got {type(blob).__name__}")
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")

    blob = bytes(blob)
    salt, iv, ct_len, body_off = _parse_header(blob)
    ciphertext = blob[body_off:body_off + ct_len]

    key = derive_key(password, salt)
    aead = AESGCM(key)  # type: ignore[misc]
    try:
        plaintext = aead.decrypt(iv, ciphertext, associated_data=None)
    except Exception as exc:
        # AESGCM raises InvalidTag for both wrong password and tampered
        # ciphertext — we collapse them into WrongPasswordError to
        # match the web PWA's user-facing message.
        raise WrongPasswordError(
            "Wrong password or corrupted backup file."
        ) from exc

    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CorruptBackupError(
            "Decrypted payload is not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise CorruptBackupError(
            f"Decrypted payload is not a dict (got {type(payload).__name__})."
        )
    if "activities" not in payload:
        # Mirror the web PWA's sanity check — Rask backups always carry
        # an "activities" array (possibly empty).
        raise CorruptBackupError(
            "Invalid backup payload: missing 'activities' key."
        )
    return payload


# =============================================================================
# === Internal helpers                                                       ===
# =============================================================================

def _now_iso_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    """Round-trip tests — run with:  python -m rask.core.crypto"""
    tests_passed = 0
    tests_failed = 0

    def check(label: str, got, expected) -> None:
        nonlocal tests_passed, tests_failed
        if got == expected:
            tests_passed += 1
            print(f"  OK   {label}")
        else:
            tests_failed += 1
            print(f"  FAIL {label}: got {got!r}, expected {expected!r}")

    if not is_available():
        print("cryptography not installed — skipping round-trip tests.")
        print("(BackupUnavailable is raised correctly; see below.)")
        try:
            encrypt_backup({"activities": []}, "password")
            check("BackupUnavailable raised", False, True)
        except BackupUnavailable:
            check("BackupUnavailable raised", True, True)
        return 0

    print("=== Round-trip tests ===")

    # 1. Basic round trip.
    payload = {
        "activities": [
            {"id": 1, "title": "Test", "duration_min": 30, "date_iso": "2025-01-01"},
        ],
        "categories": [],
        "goals": [],
    }
    blob = encrypt_backup(payload, "secret123")
    check("blob starts with magic", blob[:4], MAGIC)
    check("blob version byte", blob[4], VERSION)
    check("blob salt length", len(blob[5:21]), SALT_LEN)
    check("blob IV length", len(blob[21:33]), IV_LEN)
    ct_len = struct.unpack(">I", blob[33:37])[0]
    check("ct_len = total - 37", ct_len, len(blob) - 37)

    restored = decrypt_backup(blob, "secret123")
    check("restored == original (activities)",
          restored["activities"], payload["activities"])
    check("restored has _meta", "_meta" in restored, True)
    check("restored _meta version", restored["_meta"]["version"], VERSION)

    # 2. Wrong password.
    try:
        decrypt_backup(blob, "wrong-password")
        check("wrong password raises", False, True)
    except WrongPasswordError:
        check("wrong password raises", True, True)

    # 3. Corrupt magic.
    bad_magic = b"XXXX" + blob[4:]
    try:
        decrypt_backup(bad_magic, "secret123")
        check("bad magic raises", False, True)
    except CorruptBackupError:
        check("bad magic raises", True, True)

    # 4. Corrupt version.
    bad_ver = MAGIC + bytes([99]) + blob[5:]
    try:
        decrypt_backup(bad_ver, "secret123")
        check("bad version raises", False, True)
    except CorruptBackupError:
        check("bad version raises", True, True)

    # 5. Truncated blob.
    try:
        decrypt_backup(blob[:20], "secret123")
        check("truncated blob raises", False, True)
    except CorruptBackupError:
        check("truncated blob raises", True, True)

    # 6. Short password.
    try:
        encrypt_backup(payload, "abc")
        check("short password raises", False, True)
    except ValueError:
        check("short password raises", True, True)

    # 7. Tampered ciphertext (flip last byte).
    tampered = blob[:-1] + bytes([blob[-1] ^ 0x01])
    try:
        decrypt_backup(tampered, "secret123")
        check("tampered ciphertext raises", False, True)
    except WrongPasswordError:
        check("tampered ciphertext raises", True, True)

    # 8. Empty activities list is valid.
    empty = encrypt_backup({"activities": []}, "password1")
    check("empty activities round-trip",
          decrypt_backup(empty, "password1")["activities"], [])

    # 9. Missing 'activities' key fails the sanity check.
    bad_payload = encrypt_backup({"foo": "bar"}, "password1")
    try:
        decrypt_backup(bad_payload, "password1")
        check("missing activities raises", False, True)
    except CorruptBackupError:
        check("missing activities raises", True, True)

    # 10. derive_key is deterministic.
    salt = bytes(range(SALT_LEN))
    k1 = derive_key("test-password", salt)
    k2 = derive_key("test-password", salt)
    check("derive_key deterministic", k1, k2)
    check("derive_key length", len(k1), KEY_LEN)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
