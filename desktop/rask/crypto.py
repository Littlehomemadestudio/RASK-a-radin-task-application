"""crypto.py — AES-256-GCM encrypted backups + PBKDF2-SHA256 PIN hashing.

1:1 mirror of web/js/backup.js and web/js/biometric.js so that backup files
and PINs are interchangeable between the web and desktop editions.

Backup format (identical to web):
    offset 0:   magic    = b"RASK"
    offset 4:   version  = uint8 (1)
    offset 5:   salt     = 16 bytes (random)
    offset 21:  iv       = 12 bytes (random)
    offset 33:  ciphertext + tag = AES-256-GCM(payload)
    KDF: PBKDF2-HMAC-SHA256, 200k iterations, 32-byte key

PIN format (identical to web):
    stored as:  salt_hex + "$" + hash_hex
    KDF: PBKDF2-HMAC-SHA256, 200k iterations, 32-byte output

If the `cryptography` library is not installed, both modules degrade
gracefully — backups and PINs become unavailable, but the rest of the app
still works.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
from typing import Optional

from . import config


# =====================================================================
# === OPTIONAL DEPENDENCY: cryptography ===
# =====================================================================
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


def crypto_available() -> bool:
    """Return True if the `cryptography` library is available."""
    return _CRYPTO_AVAILABLE


def _require_crypto():
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "Cryptography library not installed. Run: pip install cryptography"
        )


# =====================================================================
# === KEY DERIVATION ===
# =====================================================================
def derive_key(password: str, salt: bytes,
               iterations: int = config.BACKUP_KDF_ITER,
               key_len: int = config.BACKUP_KEY_LEN) -> bytes:
    """Derive a 32-byte AES key from a password + salt using PBKDF2-SHA256."""
    _require_crypto()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=key_len,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def hash_pin(pin: str, salt: Optional[bytes] = None) -> str:
    """Hash a PIN with PBKDF2-SHA256. Returns 'salt_hex$hash_hex'.
    
    If salt is None, a new 16-byte random salt is generated.
    """
    _require_crypto()
    if salt is None:
        salt = secrets.token_bytes(config.PIN_SALT_LEN)
    # Use derive_key with PIN-specific iterations and a 32-byte output
    derived = derive_key(pin, salt, iterations=config.PIN_KDF_ITER, key_len=config.PIN_KEY_LEN)
    return f"{salt.hex()}${derived.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against the stored 'salt_hex$hash_hex' string.
    
    Uses constant-time comparison to prevent timing attacks.
    """
    _require_crypto()
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = derive_key(pin, salt, iterations=config.PIN_KDF_ITER, key_len=config.PIN_KEY_LEN)
    return hmac.compare_digest(derived, expected)


# =====================================================================
# === BACKUP: ENCRYPT ===
# =====================================================================
def encrypt_backup(payload: dict, password: str) -> bytes:
    """Encrypt a JSON-serializable payload with AES-256-GCM.
    
    Returns the binary backup blob (magic + version + salt + iv + ciphertext+tag).
    Format matches web/js/backup.js exactly.
    """
    _require_crypto()
    if len(password) < config.BACKUP_MIN_PWD_LEN:
        raise ValueError("Password too short (minimum 6 characters)")
    salt = secrets.token_bytes(config.BACKUP_SALT_LEN)
    iv = secrets.token_bytes(config.BACKUP_IV_LEN)
    key = derive_key(password, salt)
    aes = AESGCM(key)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = aes.encrypt(iv, plaintext, associated_data=None)
    blob = bytearray()
    blob.extend(config.BACKUP_MAGIC)
    blob.append(config.BACKUP_VERSION)
    blob.extend(salt)
    blob.extend(iv)
    blob.extend(ciphertext)
    return bytes(blob)


# =====================================================================
# === BACKUP: DECRYPT ===
# =====================================================================
def decrypt_backup(blob: bytes, password: str) -> dict:
    """Decrypt a backup blob. Returns the parsed JSON payload.
    
    Raises ValueError if the magic doesn't match, the version is unknown,
    or the password is wrong.
    """
    _require_crypto()
    if len(blob) < 4 + 1 + config.BACKUP_SALT_LEN + config.BACKUP_IV_LEN + 16:
        raise ValueError("Backup file too short / corrupted")
    magic = blob[:4]
    if magic != config.BACKUP_MAGIC:
        raise ValueError("Invalid backup magic (not a Rask backup)")
    version = blob[4]
    if version != config.BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {version}")
    salt = blob[5:5 + config.BACKUP_SALT_LEN]
    iv = blob[5 + config.BACKUP_SALT_LEN:5 + config.BACKUP_SALT_LEN + config.BACKUP_IV_LEN]
    ciphertext = blob[5 + config.BACKUP_SALT_LEN + config.BACKUP_IV_LEN:]
    key = derive_key(password, salt)
    aes = AESGCM(key)
    try:
        plaintext = aes.decrypt(iv, ciphertext, associated_data=None)
    except Exception as e:
        raise ValueError("Wrong password or corrupted backup") from e
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError("Backup payload is not valid JSON") from e


# =====================================================================
# === BACKUP FILE I/O ===
# =====================================================================
def write_backup_file(path, payload: dict, password: str) -> int:
    """Write an encrypted backup to a file. Returns number of bytes written."""
    blob = encrypt_backup(payload, password)
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)


def read_backup_file(path, password: str) -> dict:
    """Read and decrypt a backup file. Returns the parsed payload."""
    with open(path, "rb") as f:
        blob = f.read()
    return decrypt_backup(blob, password)


# =====================================================================
# === PURE-PYTHON FALLBACK HASH (no cryptography needed) ===
# =====================================================================
# This is a slower but functional PBKDF2-SHA256 implementation using only
# hashlib, so the app can still set PINs even without `cryptography` installed.
# Backups, however, REQUIRE cryptography (AES-GCM is not reimplemented here).

def _pbkdf2_sha256_pure(password: bytes, salt: bytes,
                        iterations: int, dklen: int) -> bytes:
    """Pure-Python PBKDF2-HMAC-SHA256 (fallback when cryptography is missing)."""
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen)


def hash_pin_fallback(pin: str, salt: Optional[bytes] = None) -> str:
    """Fallback PIN hashing using only hashlib (no cryptography library)."""
    if salt is None:
        salt = secrets.token_bytes(config.PIN_SALT_LEN)
    derived = _pbkdf2_sha256_pure(
        pin.encode("utf-8"), salt,
        config.PIN_KDF_ITER, config.PIN_KEY_LEN,
    )
    return f"{salt.hex()}${derived.hex()}"


def verify_pin_fallback(pin: str, stored: str) -> bool:
    """Fallback PIN verification using only hashlib."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = _pbkdf2_sha256_pure(
        pin.encode("utf-8"), salt,
        config.PIN_KDF_ITER, config.PIN_KEY_LEN,
    )
    return hmac.compare_digest(derived, expected)


# =====================================================================
# === PUBLIC API (auto-selects fallback) ===
# =====================================================================
def set_pin(pin: str) -> str:
    """Hash a PIN for storage. Uses cryptography if available, else fallback."""
    if len(pin) < config.PIN_MIN_LEN:
        raise ValueError(f"PIN must be at least {config.PIN_MIN_LEN} digits")
    if len(pin) > config.PIN_MAX_LEN:
        raise ValueError(f"PIN must be at most {config.PIN_MAX_LEN} digits")
    if not pin.isdigit():
        raise ValueError("PIN must contain only digits")
    if _CRYPTO_AVAILABLE:
        return hash_pin(pin)
    return hash_pin_fallback(pin)


def check_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against stored hash. Uses cryptography if available."""
    if _CRYPTO_AVAILABLE:
        return verify_pin(pin, stored)
    return verify_pin_fallback(pin, stored)


# =====================================================================
# === SIMPLE HASH (for non-secret checksums) ===
# =====================================================================
def sha256_hex(data: bytes | str) -> str:
    """Return the SHA-256 hex digest of the given data."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def md5_hex(data: bytes | str) -> str:
    """Return the MD5 hex digest (NOT for security — just for checksums)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.md5(data).hexdigest()


# =====================================================================
# === RANDOM UTILITIES ===
# =====================================================================
def random_token(n_bytes: int = 32) -> str:
    """Return a random hex token."""
    return secrets.token_hex(n_bytes)


def random_pin(length: int = 4) -> str:
    """Return a random numeric PIN of the given length."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))
