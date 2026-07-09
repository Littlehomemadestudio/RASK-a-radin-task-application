"""
crypto.py — Hashing helpers for PIN storage.

PBKDF2-SHA256 with 16-byte salt + 200k iterations, output 32 bytes hex.
"""
from __future__ import annotations

import hashlib
import os
import secrets


def hash_pin(pin: str) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex)."""
    salt = os.urandom(16)
    h = _derive(pin, salt)
    return salt.hex(), h.hex()


def verify_pin(pin: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    return secrets.compare_digest(_derive(pin, salt), expected)


def _derive(pin: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000, 32)
