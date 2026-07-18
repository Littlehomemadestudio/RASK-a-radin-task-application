"""
rask.core.pin
=============

PIN hashing and verification for Rask's app-lock feature.

PINs are 4-6 digit numeric codes used to unlock the desktop app.
They are never stored in plaintext — only a PBKDF2-SHA256 hash with a
per-PIN random salt is persisted.  The hash format is identical to
Django's ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`` so the
hash strings are easy to inspect and migrate.

The web PWA uses the same KDF parameters (PBKDF2-SHA256, 200,000
iterations, 16-byte salt, 32-byte derived key) but stores the salt
and hash separately in IndexedDB.  This module's ``hash_pin`` produces
the same 32-byte hash given the same PIN and salt — so a hash
generated here can be verified by the web app (and vice-versa) if you
extract the salt and hash hex from the format string.

The ``cryptography`` package is preferred for hashing (uses OpenSSL
under the hood), but a pure-stdlib fallback via
``hashlib.pbkdf2_hmac`` is used when ``cryptography`` is missing —
both produce identical bytes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Optional

from .. import config

__all__ = [
    "PinError",
    "InvalidPinError",
    "hash_pin",
    "verify_pin",
    "generate_salt",
    "is_pin_format",
    "hash_pin_raw",
    "verify_pin_raw",
    "is_available",
]

# =============================================================================
# === Constants (mirror web/js/biometric.js)                                ===
# =============================================================================

#: PBKDF2 iteration count — matches the web PWA exactly.
KDF_ITERATIONS: int = config.PIN_KDF_ITERATIONS  # 200_000

#: PBKDF2 hash algorithm name (accepted by both ``cryptography`` and ``hashlib``).
KDF_HASH: str = config.PIN_KDF_HASH  # "sha256"

#: Salt length in bytes.
SALT_LEN: int = config.PIN_SALT_LEN  # 16

#: Derived hash length in bytes (256 bits).
HASH_LEN: int = config.PIN_KEY_LEN  # 32

#: Minimum PIN length (digits).
PIN_MIN_LEN: int = 4

#: Maximum PIN length (digits).
PIN_MAX_LEN: int = 6

#: Format prefix for stored hashes.
FORMAT_PREFIX: str = "pbkdf2_sha256"


# =============================================================================
# === Optional cryptography import                                          ===
# =============================================================================

try:
    from cryptography.hazmat.primitives import hashes as _c_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False
    PBKDF2HMAC = None  # type: ignore[assignment,misc]
    _c_hashes = None  # type: ignore[assignment]


def is_available() -> bool:
    """Return True if the ``cryptography`` package is importable.

    PIN hashing works without it (via ``hashlib``) — this flag exists
    only so callers can choose the faster OpenSSL-backed path when
    available.
    """
    return _CRYPTO_AVAILABLE


# =============================================================================
# === Exceptions                                                            ===
# =============================================================================

class PinError(Exception):
    """Base class for PIN-related errors."""


class InvalidPinError(PinError):
    """Raised when a PIN fails format validation (wrong length / non-digit)."""


# =============================================================================
# === Validation                                                            ===
# =============================================================================

def is_pin_format(s: object) -> bool:
    """Return True if `s` is a syntactically valid PIN.

    A valid PIN is a string of 4-6 ASCII digits.  Persian digits are
    NOT accepted here — convert them first with ``i18n.to_en_digits``.

    Examples
    --------
    >>> is_pin_format("1234")
    True
    >>> is_pin_format("12345")
    True
    >>> is_pin_format("123")
    False
    >>> is_pin_format("12ab")
    False
    >>> is_pin_format("")
    False
    >>> is_pin_format(None)
    False
    """
    if not isinstance(s, str):
        return False
    if not s.isdigit():
        return False
    return PIN_MIN_LEN <= len(s) <= PIN_MAX_LEN


def _validate_pin(pin: str) -> None:
    """Raise :class:`InvalidPinError` if `pin` is not a valid PIN."""
    if not is_pin_format(pin):
        raise InvalidPinError(
            f"PIN must be {PIN_MIN_LEN}-{PIN_MAX_LEN} digits, got {pin!r}"
        )


# =============================================================================
# === Salt generation                                                       ===
# =============================================================================

def generate_salt() -> str:
    """Return a fresh random 16-byte salt as a lowercase hex string.

    The string is 32 characters long (16 bytes × 2 hex chars per byte).

    Example
    -------
    >>> len(generate_salt())
    32
    """
    return secrets.token_hex(SALT_LEN)


def _decode_salt(salt_hex: str) -> bytes:
    """Decode a hex salt string to raw bytes; raise on malformed input."""
    if not isinstance(salt_hex, str):
        raise ValueError(f"salt must be a hex string, got {type(salt_hex).__name__}")
    try:
        raw = bytes.fromhex(salt_hex)
    except ValueError as exc:
        raise ValueError(f"Invalid salt hex: {salt_hex!r}") from exc
    if len(raw) != SALT_LEN:
        raise ValueError(
            f"Salt must decode to {SALT_LEN} bytes, got {len(raw)}"
        )
    return raw


# =============================================================================
# === Raw hashing (used by both hash_pin and verify_pin)                    ===
# =============================================================================

def hash_pin_raw(pin: str, salt: bytes) -> bytes:
    """Compute the raw 32-byte PBKDF2-SHA256 hash of `pin` with `salt`.

    Uses ``cryptography`` when available (OpenSSL-backed, faster),
    otherwise falls back to ``hashlib.pbkdf2_hmac`` (pure-stdlib,
    same byte output).  Both paths use 200,000 iterations to match
    the web PWA exactly.

    Parameters
    ----------
    pin : str
        The PIN string.  Not validated here — callers should call
        :func:`is_pin_format` first if validation is desired.
    salt : bytes
        16-byte salt.  Length is enforced.

    Returns
    -------
    bytes
        32-byte raw hash.
    """
    if not isinstance(pin, str):
        raise ValueError(f"pin must be str, got {type(pin).__name__}")
    if not isinstance(salt, (bytes, bytearray)) or len(salt) != SALT_LEN:
        raise ValueError(
            f"salt must be {SALT_LEN} bytes, got "
            f"{len(salt) if isinstance(salt, (bytes, bytearray)) else 'non-bytes'}"
        )
    salt = bytes(salt)
    pw_bytes = pin.encode("utf-8")

    if _CRYPTO_AVAILABLE:
        kdf = PBKDF2HMAC(  # type: ignore[misc]
            algorithm=_c_hashes.SHA256(),  # type: ignore[union-attr]
            length=HASH_LEN,
            salt=salt,
            iterations=KDF_ITERATIONS,
        )
        return kdf.derive(pw_bytes)
    # Stdlib fallback — identical output to cryptography's PBKDF2HMAC.
    return hashlib.pbkdf2_hmac(KDF_HASH, pw_bytes, salt, KDF_ITERATIONS, HASH_LEN)


def verify_pin_raw(pin: str, salt: bytes, expected_hash: bytes) -> bool:
    """Constant-time PIN verification against a raw salt + hash.

    Parameters
    ----------
    pin : str
        The PIN to test.
    salt : bytes
        16-byte salt originally used to hash the PIN.
    expected_hash : bytes
        32-byte expected hash.

    Returns
    -------
    bool
        ``True`` if the PIN matches, ``False`` otherwise.  Uses
        :func:`hmac.compare_digest` to prevent timing attacks.
    """
    if not isinstance(expected_hash, (bytes, bytearray)) or len(expected_hash) != HASH_LEN:
        return False
    actual = hash_pin_raw(pin, salt)
    return hmac.compare_digest(actual, bytes(expected_hash))


# =============================================================================
# === Public formatted-hash API                                             ===
# =============================================================================

def hash_pin(pin: str) -> str:
    """Hash a PIN and return a portable format string.

    The returned format is identical to Django's PBKDF2 password
    storage:

        ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``

    Parameters
    ----------
    pin : str
        The PIN to hash.  Must be 4-6 ASCII digits — see
        :func:`is_pin_format`.

    Returns
    -------
    str
        The formatted hash string.  Store this in the database; pass
        it back to :func:`verify_pin` for verification.

    Raises
    ------
    InvalidPinError
        If `pin` fails format validation.

    Example
    -------
    >>> h = hash_pin("1234")
    >>> h.startswith("pbkdf2_sha256$200000$")
    True
    >>> verify_pin("1234", h)
    True
    >>> verify_pin("9999", h)
    False
    """
    _validate_pin(pin)
    salt_hex = generate_salt()
    salt = _decode_salt(salt_hex)
    raw_hash = hash_pin_raw(pin, salt)
    return f"{FORMAT_PREFIX}${KDF_ITERATIONS}${salt_hex}${raw_hash.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a stored format string.

    Parameters
    ----------
    pin : str
        The PIN to test (any string is accepted — non-PIN strings
        will simply fail to match).
    stored : str
        The format string previously produced by :func:`hash_pin`.

    Returns
    -------
    bool
        ``True`` if `pin` matches `stored`, ``False`` otherwise.
        Also returns ``False`` if `stored` is malformed (no exception
        is raised — this is the safe default for authentication).
    """
    if not isinstance(pin, str) or not isinstance(stored, str):
        return False
    if not pin:
        return False
    parts = stored.split("$")
    if len(parts) != 4:
        return False
    algo, iter_str, salt_hex, hash_hex = parts
    if algo != FORMAT_PREFIX:
        return False
    try:
        iterations = int(iter_str)
    except ValueError:
        return False
    if iterations < 1:
        return False
    try:
        salt = _decode_salt(salt_hex)
    except ValueError:
        return False
    try:
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    if len(expected) != HASH_LEN:
        return False

    # Use the iterations from the stored string (not the current
    # KDF_ITERATIONS) so old hashes remain verifiable after a config
    # bump.  Note: this requires computing the hash inline rather than
    # calling hash_pin_raw (which uses the constant).
    actual = hashlib.pbkdf2_hmac(
        KDF_HASH, pin.encode("utf-8"), salt, iterations, HASH_LEN
    )
    return hmac.compare_digest(actual, expected)


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.pin"""
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

    print("=== Format validation ===")
    check("is_pin_format('1234')", is_pin_format("1234"), True)
    check("is_pin_format('123456')", is_pin_format("123456"), True)
    check("is_pin_format('123')", is_pin_format("123"), False)
    check("is_pin_format('1234567')", is_pin_format("1234567"), False)
    check("is_pin_format('12ab')", is_pin_format("12ab"), False)
    check("is_pin_format('')", is_pin_format(""), False)
    check("is_pin_format(None)", is_pin_format(None), False)
    check("is_pin_format(1234)", is_pin_format(1234), False)

    print("\n=== Hash + verify round trip ===")
    h = hash_pin("1234")
    parts = h.split("$")
    check("hash has 4 parts", len(parts), 4)
    check("hash algo prefix", parts[0], FORMAT_PREFIX)
    check("hash iterations", int(parts[1]), KDF_ITERATIONS)
    check("salt hex length", len(parts[2]), SALT_LEN * 2)
    check("hash hex length", len(parts[3]), HASH_LEN * 2)

    check("verify correct pin", verify_pin("1234", h), True)
    check("verify wrong pin", verify_pin("9999", h), False)
    check("verify empty pin", verify_pin("", h), False)

    print("\n=== Cross-method consistency ===")
    # hash_pin_raw and hashlib should produce identical bytes.
    salt = bytes(range(SALT_LEN))
    raw1 = hash_pin_raw("1234", salt)
    raw2 = hashlib.pbkdf2_hmac(
        KDF_HASH, b"1234", salt, KDF_ITERATIONS, HASH_LEN
    )
    check("hash_pin_raw == hashlib.pbkdf2_hmac", raw1, raw2)
    check("raw hash length", len(raw1), HASH_LEN)

    print("\n=== Constant-time verification ===")
    expected = hash_pin_raw("4321", salt)
    check("verify_pin_raw correct",
          verify_pin_raw("4321", salt, expected), True)
    check("verify_pin_raw wrong",
          verify_pin_raw("1234", salt, expected), False)
    check("verify_pin_raw bad hash len",
          verify_pin_raw("4321", salt, b"short"), False)

    print("\n=== Salt generation ===")
    s1 = generate_salt()
    s2 = generate_salt()
    check("salt hex length", len(s1), SALT_LEN * 2)
    check("two salts differ (randomness)", s1 != s2, True)

    print("\n=== Invalid PIN raises ===")
    try:
        hash_pin("123")
        check("short pin raises", False, True)
    except InvalidPinError:
        check("short pin raises", True, True)
    try:
        hash_pin("abcd")
        check("non-digit pin raises", False, True)
    except InvalidPinError:
        check("non-digit pin raises", True, True)

    print("\n=== Malformed stored hash ===")
    check("garbage stored", verify_pin("1234", "garbage"), False)
    check("empty stored", verify_pin("1234", ""), False)
    check("wrong algo", verify_pin("1234", "argon2$1000$abcd$efgh"), False)
    check("bad salt hex",
          verify_pin("1234", f"{FORMAT_PREFIX}$200000$zz${'00' * HASH_LEN}"),
          False)
    check("bad hash hex",
          verify_pin("1234", f"{FORMAT_PREFIX}$200000${'00' * SALT_LEN}$zz"),
          False)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
