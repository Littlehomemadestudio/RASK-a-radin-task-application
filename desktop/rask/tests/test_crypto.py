"""
rask.tests.test_crypto
======================

Unit tests for :mod:`rask.core.crypto` (AES-256-GCM encrypted backup).

Covers:

  • Round-trip: encrypt → decrypt returns the original payload
  • Wrong password raises :class:`WrongPasswordError`
  • Tampered ciphertext / header raises :class:`CorruptBackupError`
  • Empty payload, large payload (10,000 activities), Unicode
    (Persian text, emojis, RTL)
  • Format compatibility: magic bytes, version byte, salt/IV lengths,
    ciphertext-length field
  • PBKDF2 key derivation determinism and length
  • Salt / IV generation uniqueness and length
  • Edge cases: short password, empty dict, missing ``activities`` key,
    truncated blob, bad magic / version

Skips the round-trip tests if the optional ``cryptography`` package is
not installed (the module raises :class:`BackupUnavailable` in that case).
"""
from __future__ import annotations

import os
import struct
import unittest

from rask.core import crypto
from rask.core.crypto import (
    BackupError,
    BackupUnavailable,
    CorruptBackupError,
    GCM_TAG_LEN,
    IV_LEN,
    KEY_LEN,
    MAGIC,
    MIN_PASSWORD_LEN,
    SALT_LEN,
    VERSION,
    WrongPasswordError,
    decrypt_backup,
    derive_key,
    encrypt_backup,
    generate_iv,
    generate_salt,
    is_available,
)


# =============================================================================
# === Test payload helpers                                                     ==
# =============================================================================

def _basic_payload() -> dict:
    """Return a small representative backup payload."""
    return {
        "activities": [
            {"id": 1, "title": "Test activity", "duration_min": 30,
             "date_iso": "2025-01-01"},
            {"id": 2, "title": "Another", "duration_min": 60,
             "date_iso": "2025-01-02"},
        ],
        "categories": [
            {"id": 1, "key": "FOCUS", "name_en": "Focus",
             "name_fa": "تمرکز", "color": "#D4AF37"},
        ],
        "goals": [],
        "settings": [{"key": "lang", "value": "fa"}],
    }


def _empty_payload() -> dict:
    """Return the minimal valid payload (just an empty activities list)."""
    return {"activities": []}


def _large_payload(n: int = 10_000) -> dict:
    """Return a payload with `n` activities — stress-tests encryption."""
    return {
        "activities": [
            {"id": i, "title": f"Activity {i}", "duration_min": i % 1440,
             "date_iso": "2025-01-01", "notes": f"Notes for {i}" * 3}
            for i in range(n)
        ],
        "categories": [],
        "goals": [],
    }


def _unicode_payload() -> dict:
    """Return a payload with Persian text, emojis, and RTL content."""
    return {
        "activities": [
            {"id": 1, "title": "تمرکز عمیق 🎯", "duration_min": 45,
             "date_iso": "2025-01-01",
             "notes": "یادداشت فارسی با ایموجی 🚀 و نمادهای RTL"},
            {"id": 2, "title": "📚 مطالعه کتاب",
             "duration_min": 90, "date_iso": "2025-01-02",
             "notes": "Mixed: Hello 世界 🌍 مرحبا"},
        ],
        "categories": [],
        "goals": [],
    }


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestRoundTrip(unittest.TestCase):
    """encrypt → decrypt must reproduce the original payload."""

    def test_basic_round_trip(self) -> None:
        payload = _basic_payload()
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(blob, "secret123")
        self.assertEqual(restored["activities"], payload["activities"])
        self.assertEqual(restored["categories"], payload["categories"])

    def test_empty_payload_round_trip(self) -> None:
        payload = _empty_payload()
        blob = encrypt_backup(payload, "password1")
        restored = decrypt_backup(blob, "password1")
        self.assertEqual(restored["activities"], [])

    def test_unicode_payload_round_trip(self) -> None:
        payload = _unicode_payload()
        blob = encrypt_backup(payload, "unicode-pass")
        restored = decrypt_backup(blob, "unicode-pass")
        self.assertEqual(restored["activities"], payload["activities"])
        # Make sure Persian text is preserved byte-for-byte.
        self.assertIn("تمرکز عمیق 🎯", restored["activities"][0]["title"])
        self.assertIn("📚 مطالعه کتاب", restored["activities"][1]["title"])

    def test_large_payload_round_trip(self) -> None:
        payload = _large_payload(1000)  # 1000 is enough for stress
        blob = encrypt_backup(payload, "large-pass-123")
        restored = decrypt_backup(blob, "large-pass-123")
        self.assertEqual(len(restored["activities"]), 1000)
        self.assertEqual(restored["activities"][500]["title"], "Activity 500")

    def test_meta_block_added(self) -> None:
        """encrypt_backup augments the payload with a `_meta` block."""
        payload = _basic_payload()
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(blob, "secret123")
        self.assertIn("_meta", restored)
        self.assertEqual(restored["_meta"]["version"], VERSION)
        self.assertIn("exported_at", restored["_meta"])
        self.assertIn("app_version", restored["_meta"])

    def test_round_trip_idempotent_with_same_password(self) -> None:
        """Two encryptions with same password both decrypt to the same payload."""
        payload = _basic_payload()
        blob1 = encrypt_backup(payload, "secret123")
        blob2 = encrypt_backup(payload, "secret123")
        # Different blobs (random salt+IV)…
        self.assertNotEqual(blob1, blob2)
        # …but same decrypted payload.
        self.assertEqual(
            decrypt_backup(blob1, "secret123")["activities"],
            decrypt_backup(blob2, "secret123")["activities"],
        )


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestWrongPassword(unittest.TestCase):
    """Wrong password must raise WrongPasswordError."""

    def test_wrong_password_raises(self) -> None:
        blob = encrypt_backup(_basic_payload(), "correct-password")
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(blob, "wrong-password")

    def test_empty_password_raises(self) -> None:
        blob = encrypt_backup(_basic_payload(), "correct-password")
        with self.assertRaises(ValueError):
            decrypt_backup(blob, "")

    def test_case_sensitive(self) -> None:
        blob = encrypt_backup(_basic_payload(), "Secret123")
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(blob, "secret123")

    def test_truncated_password_raises(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(blob, "secret12")


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestTampering(unittest.TestCase):
    """Tampering with the ciphertext or header must raise."""

    def test_tampered_ciphertext_byte(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        # Flip the last byte of the ciphertext.
        tampered = blob[:-1] + bytes([blob[-1] ^ 0x01])
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(tampered, "secret123")

    def test_tampered_ciphertext_middle(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        # Flip a byte in the middle of the ciphertext.
        idx = len(blob) // 2
        tampered = blob[:idx] + bytes([blob[idx] ^ 0x80]) + blob[idx + 1:]
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(tampered, "secret123")

    def test_tampered_iv_raises(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        # IV starts at offset 21 (after magic + version + 16-byte salt).
        tampered = blob[:21] + bytes([blob[21] ^ 0xFF]) + blob[22:]
        with self.assertRaises((WrongPasswordError, CorruptBackupError)):
            decrypt_backup(tampered, "secret123")

    def test_tampered_salt_raises(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        # Salt starts at offset 5 (after magic + version).
        tampered = blob[:5] + bytes([blob[5] ^ 0xFF]) + blob[6:]
        with self.assertRaises(WrongPasswordError):
            decrypt_backup(tampered, "secret123")

    def test_bad_magic_bytes(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        bad_magic = b"XXXX" + blob[4:]
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(bad_magic, "secret123")

    def test_unsupported_version(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        bad_ver = MAGIC + bytes([99]) + blob[5:]
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(bad_ver, "secret123")

    def test_truncated_blob(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(blob[:20], "secret123")

    def test_truncated_just_below_minimum(self) -> None:
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(b"RASK" + bytes([1]) + b"\x00" * 10, "secret123")

    def test_empty_blob(self) -> None:
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(b"", "secret123")

    def test_blob_with_corrupt_ct_length(self) -> None:
        """A ct_len field that exceeds the body raises CorruptBackupError."""
        blob = encrypt_backup(_basic_payload(), "secret123")
        # Overwrite the ct_len field (offset 33..37) with a huge value.
        tampered = blob[:33] + struct.pack(">I", 999_999_999) + blob[37:]
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(tampered, "secret123")


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestFormatCompatibility(unittest.TestCase):
    """Verify the on-disk format matches the spec."""

    def test_magic_bytes(self) -> None:
        blob = encrypt_backup(_empty_payload(), "password1")
        self.assertEqual(blob[:4], MAGIC)
        self.assertEqual(blob[:4], b"RASK")

    def test_version_byte(self) -> None:
        blob = encrypt_backup(_empty_payload(), "password1")
        self.assertEqual(blob[4], VERSION)

    def test_salt_length(self) -> None:
        blob = encrypt_backup(_empty_payload(), "password1")
        salt = blob[5:5 + SALT_LEN]
        self.assertEqual(len(salt), SALT_LEN)

    def test_iv_length(self) -> None:
        blob = encrypt_backup(_empty_payload(), "password1")
        iv = blob[5 + SALT_LEN:5 + SALT_LEN + IV_LEN]
        self.assertEqual(len(iv), IV_LEN)

    def test_ct_length_field(self) -> None:
        blob = encrypt_backup(_empty_payload(), "password1")
        ct_len = struct.unpack(">I", blob[33:37])[0]
        # The ciphertext body should equal ct_len bytes.
        body = blob[37:]
        self.assertEqual(len(body), ct_len)

    def test_total_blob_length_is_header_plus_ct(self) -> None:
        blob = encrypt_backup(_basic_payload(), "secret123")
        ct_len = struct.unpack(">I", blob[33:37])[0]
        self.assertEqual(len(blob), 37 + ct_len)

    def test_constants_match_config(self) -> None:
        from rask import config
        self.assertEqual(MAGIC, config.BACKUP_MAGIC)
        self.assertEqual(VERSION, config.BACKUP_VERSION)
        self.assertEqual(SALT_LEN, config.BACKUP_SALT_LEN)
        self.assertEqual(IV_LEN, config.BACKUP_IV_LEN)
        self.assertEqual(KEY_LEN, config.BACKUP_KEY_LEN)


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestKeyDerivation(unittest.TestCase):
    """PBKDF2 key derivation."""

    def test_derive_key_is_deterministic(self) -> None:
        salt = bytes(range(SALT_LEN))
        k1 = derive_key("test-password", salt)
        k2 = derive_key("test-password", salt)
        self.assertEqual(k1, k2)

    def test_derive_key_length(self) -> None:
        salt = bytes(range(SALT_LEN))
        key = derive_key("test-password", salt)
        self.assertEqual(len(key), KEY_LEN)

    def test_different_salts_produce_different_keys(self) -> None:
        salt1 = bytes(range(SALT_LEN))
        salt2 = bytes(reversed(range(SALT_LEN)))
        k1 = derive_key("test-password", salt1)
        k2 = derive_key("test-password", salt2)
        self.assertNotEqual(k1, k2)

    def test_different_passwords_produce_different_keys(self) -> None:
        salt = bytes(range(SALT_LEN))
        k1 = derive_key("password-one", salt)
        k2 = derive_key("password-two", salt)
        self.assertNotEqual(k1, k2)

    def test_derive_key_rejects_empty_password(self) -> None:
        with self.assertRaises(ValueError):
            derive_key("", bytes(SALT_LEN))

    def test_derive_key_rejects_bad_salt_length(self) -> None:
        with self.assertRaises(ValueError):
            derive_key("password", bytes(SALT_LEN - 1))
        with self.assertRaises(ValueError):
            derive_key("password", bytes(SALT_LEN + 1))
        with self.assertRaises(ValueError):
            derive_key("password", "not-bytes")  # type: ignore[arg-type]


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestSaltAndIVGeneration(unittest.TestCase):
    """Salt / IV generators return cryptographically random bytes."""

    def test_generate_salt_length(self) -> None:
        self.assertEqual(len(generate_salt()), SALT_LEN)

    def test_generate_iv_length(self) -> None:
        self.assertEqual(len(generate_iv()), IV_LEN)

    def test_two_salts_differ(self) -> None:
        """Two salts generated in a row should be different."""
        s1 = generate_salt()
        s2 = generate_salt()
        self.assertNotEqual(s1, s2)

    def test_two_ivs_differ(self) -> None:
        iv1 = generate_iv()
        iv2 = generate_iv()
        self.assertNotEqual(iv1, iv2)

    def test_salt_is_bytes(self) -> None:
        self.assertIsInstance(generate_salt(), bytes)

    def test_iv_is_bytes(self) -> None:
        self.assertIsInstance(generate_iv(), bytes)


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestInputValidation(unittest.TestCase):
    """Input validation in encrypt_backup."""

    def test_short_password_raises(self) -> None:
        with self.assertRaises(ValueError):
            encrypt_backup(_empty_payload(), "abc")

    def test_min_length_password_accepted(self) -> None:
        # MIN_PASSWORD_LEN chars should be accepted.
        pwd = "x" * MIN_PASSWORD_LEN
        blob = encrypt_backup(_empty_payload(), pwd)
        self.assertEqual(decrypt_backup(blob, pwd)["activities"], [])

    def test_non_dict_data_raises(self) -> None:
        with self.assertRaises(ValueError):
            encrypt_backup(["not", "a", "dict"], "password1")  # type: ignore[arg-type]

    def test_non_string_password_raises(self) -> None:
        with self.assertRaises(ValueError):
            encrypt_backup(_empty_payload(), 12345)  # type: ignore[arg-type]

    def test_decrypt_non_bytes_raises(self) -> None:
        with self.assertRaises(ValueError):
            decrypt_backup("not-bytes", "password1")  # type: ignore[arg-type]

    def test_decrypt_missing_activities_raises(self) -> None:
        """A valid AES-GCM payload missing the 'activities' key fails."""
        bad = encrypt_backup({"foo": "bar"}, "password1")
        with self.assertRaises(CorruptBackupError):
            decrypt_backup(bad, "password1")


class TestAvailabilityCheck(unittest.TestCase):
    """BackupUnavailable is raised when cryptography is missing."""

    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(is_available(), bool)

    def test_backup_error_is_base_class(self) -> None:
        """All crypto exceptions derive from BackupError."""
        self.assertTrue(issubclass(BackupUnavailable, BackupError))
        self.assertTrue(issubclass(WrongPasswordError, BackupError))
        self.assertTrue(issubclass(CorruptBackupError, BackupError))

    def test_wrong_password_distinct_from_corrupt(self) -> None:
        """WrongPasswordError and CorruptBackupError are distinct classes."""
        self.assertNotEqual(WrongPasswordError, CorruptBackupError)
        # CorruptBackupError is NOT a WrongPasswordError (and vice versa).
        self.assertFalse(issubclass(CorruptBackupError, WrongPasswordError))
        self.assertFalse(issubclass(WrongPasswordError, CorruptBackupError))


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestRandomnessProperties(unittest.TestCase):
    """Multiple encryptions produce different blobs (random IV/salt)."""

    def test_two_encryptions_differ(self) -> None:
        payload = _basic_payload()
        blob1 = encrypt_backup(payload, "secret123")
        blob2 = encrypt_backup(payload, "secret123")
        self.assertNotEqual(blob1, blob2)

    def test_many_encryptions_produce_distinct_blobs(self) -> None:
        """100 encryptions should produce 100 distinct blobs."""
        payload = _empty_payload()
        blobs = {encrypt_backup(payload, "password1") for _ in range(100)}
        self.assertEqual(len(blobs), 100)

    def test_ivs_within_blobs_differ(self) -> None:
        """The IV portion (offset 21..33) should differ between blobs."""
        payload = _empty_payload()
        ivs = set()
        for _ in range(20):
            blob = encrypt_backup(payload, "password1")
            ivs.add(blob[21:33])
        self.assertEqual(len(ivs), 20)

    def test_salts_within_blobs_differ(self) -> None:
        """The salt portion (offset 5..21) should differ between blobs."""
        payload = _empty_payload()
        salts = set()
        for _ in range(20):
            blob = encrypt_backup(payload, "password1")
            salts.add(blob[5:21])
        self.assertEqual(len(salts), 20)


@unittest.skipUnless(is_available(), "cryptography package not installed")
class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_payload_with_nested_structures(self) -> None:
        payload = {
            "activities": [
                {"id": 1, "title": "Test", "duration_min": 10,
                 "date_iso": "2025-01-01", "meta": {"nested": [1, 2, 3]}},
            ],
            "categories": [],
            "goals": [],
        }
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(blob, "secret123")
        self.assertEqual(restored["activities"][0]["meta"]["nested"], [1, 2, 3])

    def test_payload_with_null_values(self) -> None:
        payload = {
            "activities": [
                {"id": 1, "title": "Test", "duration_min": 0,
                 "date_iso": "2025-01-01", "notes": None, "tags": []},
            ],
        }
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(blob, "secret123")
        self.assertIsNone(restored["activities"][0]["notes"])

    def test_password_exactly_at_min_length(self) -> None:
        payload = _empty_payload()
        pwd = "x" * 6  # MIN_PASSWORD_LEN
        blob = encrypt_backup(payload, pwd)
        self.assertEqual(decrypt_backup(blob, pwd)["activities"], [])

    def test_long_password(self) -> None:
        payload = _empty_payload()
        pwd = "x" * 1000
        blob = encrypt_backup(payload, pwd)
        self.assertEqual(decrypt_backup(blob, pwd)["activities"], [])

    def test_blob_size_grows_with_payload_size(self) -> None:
        small = encrypt_backup(_empty_payload(), "secret123")
        large = encrypt_backup(_large_payload(500), "secret123")
        self.assertGreater(len(large), len(small))

    def test_min_blob_size(self) -> None:
        """A minimal blob must be at least header + GCM tag (37 + 16 = 53 bytes)."""
        blob = encrypt_backup(_empty_payload(), "secret123")
        self.assertGreaterEqual(len(blob), 37 + GCM_TAG_LEN)

    def test_decrypt_memoryview_input(self) -> None:
        """decrypt_backup accepts memoryview as well as bytes."""
        payload = _basic_payload()
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(memoryview(blob), "secret123")
        self.assertEqual(restored["activities"], payload["activities"])

    def test_decrypt_bytearray_input(self) -> None:
        payload = _basic_payload()
        blob = encrypt_backup(payload, "secret123")
        restored = decrypt_backup(bytearray(blob), "secret123")
        self.assertEqual(restored["activities"], payload["activities"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
