"""crypto.py — PIN hashing + AES-256-GCM encrypted backup (mirror of biometric.js + backup.js).

PIN: PBKDF2-SHA256, 200k iterations, 16-byte salt, 32-byte derived hash, hex-encoded.
Backup: magic 'RASK' + version 1 + 16-byte salt + 12-byte IV + 4-byte ct_len + ciphertext.
        Key derived via PBKDF2-SHA256 (200k iter, 32 bytes) for AES-256-GCM.
"""
from __future__ import annotations
import hashlib
import json
import os
import secrets
import struct
from typing import Any, Dict, Tuple
from . import config
from . import database


def _pbkdf2(password: str, salt: bytes, iterations: int, length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, length)


# === PIN ===
def hash_pin(pin: str, salt: bytes) -> bytes:
    return _pbkdf2(pin, salt, config.PIN_KDF_ITER, 32)


def bytes_to_hex(b: bytes) -> str:
    return b.hex()


def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


def setup_pin(pin: str) -> None:
    if len(pin) < config.PIN_MIN_LEN:
        raise ValueError("PIN too short")
    salt = secrets.token_bytes(config.PIN_SALT_LEN)
    h = hash_pin(pin, salt)
    database.kv_set("pin_salt", bytes_to_hex(salt))
    database.kv_set("pin_hash", bytes_to_hex(h))
    database.kv_set("lock_mode", "pin")


def verify_pin(pin: str) -> bool:
    salt_hex = database.kv_get("pin_salt", "")
    hash_hex = database.kv_get("pin_hash", "")
    if not salt_hex or not hash_hex:
        return False
    salt = hex_to_bytes(salt_hex)
    expected = hex_to_bytes(hash_hex)
    actual = hash_pin(pin, salt)
    return secrets.compare_digest(actual, expected)


def clear_lock() -> None:
    database.kv_set("lock_mode", "none")
    database.kv_set("pin_hash", "")
    database.kv_set("pin_salt", "")


# === Biometric (webauthn stand-in) ===
def is_biometric_available() -> bool:
    """On desktop there is no WebAuthn; we return False so the UI behaves like the web fallback."""
    return False


def setup_biometric() -> None:
    raise RuntimeError("Biometric unavailable on desktop")


def authenticate_biometric() -> bool:
    return False


# === AES-256-GCM backup ===
# We use cryptography's AESGCM (matches Web Crypto's AES-GCM with 12-byte IV exactly).


def _aesgcm_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).encrypt(iv, plaintext, associated_data=None)


def _aesgcm_decrypt(key: bytes, iv: bytes, ct: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(iv, ct, associated_data=None)


def _derive_backup_key(password: str, salt: bytes) -> bytes:
    return _pbkdf2(password, salt, config.BACKUP_KDF_ITER, 32)


def export_to_bytes(password: str) -> bytes:
    payload: Dict[str, Any] = database.export_all()
    payload["_meta"] = {
        "version": config.BACKUP_VERSION,
        "app_version": config.APP_VERSION,
        "exported_at": _now_iso(),
    }
    plaintext = json.dumps(payload).encode("utf-8")
    salt = secrets.token_bytes(config.BACKUP_SALT_LEN)
    iv = secrets.token_bytes(config.BACKUP_IV_LEN)
    key = _derive_backup_key(password, salt)
    ct = _aesgcm_encrypt(key, iv, plaintext)
    out = bytearray()
    out += config.BACKUP_MAGIC
    out += bytes([config.BACKUP_VERSION])
    out += salt
    out += iv
    out += struct.pack(">I", len(ct))
    out += ct
    return bytes(out)


def import_from_bytes(data: bytes, password: str) -> Dict[str, Any]:
    if len(data) < 4 + 1 + config.BACKUP_SALT_LEN + config.BACKUP_IV_LEN + 4:
        raise ValueError("Backup file too short / corrupted.")
    if data[:4] != config.BACKUP_MAGIC:
        raise ValueError("Not a Rask backup file (bad magic).")
    off = 4
    ver = data[off]; off += 1
    if ver != config.BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version {ver}.")
    salt = data[off:off + config.BACKUP_SALT_LEN]; off += config.BACKUP_SALT_LEN
    iv = data[off:off + config.BACKUP_IV_LEN]; off += config.BACKUP_IV_LEN
    (ct_len,) = struct.unpack(">I", data[off:off + 4]); off += 4
    ct = data[off:off + ct_len]
    key = _derive_backup_key(password, salt)
    try:
        plaintext = _aesgcm_decrypt(key, iv, ct)
    except Exception:
        raise ValueError("Wrong password or corrupted file.")
    payload = json.loads(plaintext.decode("utf-8"))
    if not payload or "activities" not in payload:
        raise ValueError("Invalid backup payload.")
    database.replace_all(payload)
    return payload


def export_to_file(path: str, password: str) -> None:
    data = export_to_bytes(password)
    with open(path, "wb") as f:
        f.write(data)


def import_from_file(path: str, password: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        data = f.read()
    return import_from_bytes(data, password)


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat()
