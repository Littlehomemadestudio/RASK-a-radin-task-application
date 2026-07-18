"""
rask.tests.test_pin
===================

Unit tests for :mod:`rask.core.pin` (PBKDF2-SHA256 PIN hashing).

Covers:

  • ``hash_pin`` produces the expected ``pbkdf2_sha256$200000$<salt>$<hash>``
    format with correct field lengths and iteration count.
  • ``verify_pin`` succeeds on the correct PIN and fails on wrong,
    empty, or non-PIN inputs.
  • Different salts produce different hashes for the same PIN.
  • All 4-digit PINs (0000–9999) hash without error (sampled).
  • ``is_pin_format`` accepts valid 4-6 digit PINs and rejects
    everything else (None, int, empty, non-digit, too long / short).
  • ``hash_pin_raw`` and ``verify_pin_raw`` produce / verify raw
    32-byte hashes.
  • Cross-method consistency between ``hash_pin_raw`` and
    ``hashlib.pbkdf2_hmac`` (stdlib fallback path).
  • Malformed stored-hash strings are safely rejected (no exception).
"""
from __future__ import annotations

import hashlib
import unittest

from rask.core import pin
from rask.core.pin import (
    FORMAT_PREFIX,
    HASH_LEN,
    InvalidPinError,
    KDF_HASH,
    KDF_ITERATIONS,
    PIN_MAX_LEN,
    PIN_MIN_LEN,
    SALT_LEN,
    generate_salt,
    hash_pin,
    hash_pin_raw,
    is_available,
    is_pin_format,
    verify_pin,
    verify_pin_raw,
)


# =============================================================================
# === Tests                                                                  ===
# =============================================================================

class TestFormatValidation(unittest.TestCase):
    """is_pin_format accepts 4-6 ASCII digits and rejects everything else."""

    def test_valid_4_digit_pin(self) -> None:
        self.assertTrue(is_pin_format("1234"))

    def test_valid_5_digit_pin(self) -> None:
        self.assertTrue(is_pin_format("12345"))

    def test_valid_6_digit_pin(self) -> None:
        self.assertTrue(is_pin_format("123456"))

    def test_all_zeros(self) -> None:
        self.assertTrue(is_pin_format("0000"))

    def test_all_nines(self) -> None:
        self.assertTrue(is_pin_format("9999"))

    def test_too_short_pin(self) -> None:
        self.assertFalse(is_pin_format("123"))
        self.assertFalse(is_pin_format("12"))
        self.assertFalse(is_pin_format("1"))

    def test_too_long_pin(self) -> None:
        self.assertFalse(is_pin_format("1234567"))
        self.assertFalse(is_pin_format("12345678"))

    def test_non_digit_pin(self) -> None:
        self.assertFalse(is_pin_format("12ab"))
        self.assertFalse(is_pin_format("abcd"))
        self.assertFalse(is_pin_format("12-34"))
        self.assertFalse(is_pin_format("12 34"))

    def test_empty_string(self) -> None:
        self.assertFalse(is_pin_format(""))

    def test_none(self) -> None:
        self.assertFalse(is_pin_format(None))  # type: ignore[arg-type]

    def test_integer_input(self) -> None:
        # Int is not a string — should be rejected.
        self.assertFalse(is_pin_format(1234))  # type: ignore[arg-type]
        self.assertFalse(is_pin_format(12345))  # type: ignore[arg-type]

    def test_list_input(self) -> None:
        self.assertFalse(is_pin_format(["1", "2", "3", "4"]))  # type: ignore[arg-type]

    def test_float_input(self) -> None:
        self.assertFalse(is_pin_format(1234.0))  # type: ignore[arg-type]


class TestHashPin(unittest.TestCase):
    """hash_pin produces the expected format string."""

    def test_format_prefix(self) -> None:
        h = hash_pin("1234")
        self.assertTrue(h.startswith(f"{FORMAT_PREFIX}${KDF_ITERATIONS}$"))

    def test_format_has_four_parts(self) -> None:
        h = hash_pin("1234")
        parts = h.split("$")
        self.assertEqual(len(parts), 4)

    def test_algo_part(self) -> None:
        parts = hash_pin("1234").split("$")
        self.assertEqual(parts[0], FORMAT_PREFIX)

    def test_iterations_part(self) -> None:
        parts = hash_pin("1234").split("$")
        self.assertEqual(int(parts[1]), KDF_ITERATIONS)

    def test_salt_hex_length(self) -> None:
        parts = hash_pin("1234").split("$")
        # 16 bytes -> 32 hex chars
        self.assertEqual(len(parts[2]), SALT_LEN * 2)

    def test_hash_hex_length(self) -> None:
        parts = hash_pin("1234").split("$")
        # 32 bytes -> 64 hex chars
        self.assertEqual(len(parts[3]), HASH_LEN * 2)

    def test_salt_is_hex(self) -> None:
        parts = hash_pin("1234").split("$")
        self.assertTrue(all(c in "0123456789abcdef" for c in parts[2]))

    def test_hash_is_hex(self) -> None:
        parts = hash_pin("1234").split("$")
        self.assertTrue(all(c in "0123456789abcdef" for c in parts[3]))

    def test_short_pin_raises(self) -> None:
        with self.assertRaises(InvalidPinError):
            hash_pin("123")

    def test_long_pin_raises(self) -> None:
        with self.assertRaises(InvalidPinError):
            hash_pin("1234567")

    def test_non_digit_pin_raises(self) -> None:
        with self.assertRaises(InvalidPinError):
            hash_pin("abcd")

    def test_empty_pin_raises(self) -> None:
        with self.assertRaises(InvalidPinError):
            hash_pin("")

    def test_none_pin_raises(self) -> None:
        with self.assertRaises((InvalidPinError, ValueError)):
            hash_pin(None)  # type: ignore[arg-type]


class TestVerifyPin(unittest.TestCase):
    """verify_pin succeeds on correct, fails on wrong."""

    def test_verify_correct_pin(self) -> None:
        h = hash_pin("1234")
        self.assertTrue(verify_pin("1234", h))

    def test_verify_wrong_pin(self) -> None:
        h = hash_pin("1234")
        self.assertFalse(verify_pin("9999", h))

    def test_verify_empty_pin(self) -> None:
        h = hash_pin("1234")
        self.assertFalse(verify_pin("", h))

    def test_verify_with_6_digit_pin(self) -> None:
        h = hash_pin("123456")
        self.assertTrue(verify_pin("123456", h))
        self.assertFalse(verify_pin("123457", h))

    def test_verify_with_5_digit_pin(self) -> None:
        h = hash_pin("54321")
        self.assertTrue(verify_pin("54321", h))
        self.assertFalse(verify_pin("54320", h))

    def test_two_different_pins_produce_different_hashes(self) -> None:
        h1 = hash_pin("1111")
        h2 = hash_pin("2222")
        self.assertNotEqual(h1, h2)
        # Cross-verify
        self.assertFalse(verify_pin("1111", h2))
        self.assertFalse(verify_pin("2222", h1))


class TestSaltRandomness(unittest.TestCase):
    """Different salts produce different hashes for the same PIN."""

    def test_two_hashes_have_different_salts(self) -> None:
        h1 = hash_pin("1234")
        h2 = hash_pin("1234")
        s1 = h1.split("$")[2]
        s2 = h2.split("$")[2]
        self.assertNotEqual(s1, s2)

    def test_two_hashes_have_different_hashes(self) -> None:
        h1 = hash_pin("1234")
        h2 = hash_pin("1234")
        hash1 = h1.split("$")[3]
        hash2 = h2.split("$")[3]
        self.assertNotEqual(hash1, hash2)

    def test_both_hashes_verify(self) -> None:
        h1 = hash_pin("1234")
        h2 = hash_pin("1234")
        self.assertTrue(verify_pin("1234", h1))
        self.assertTrue(verify_pin("1234", h2))

    def test_generate_salt_unique(self) -> None:
        salts = {generate_salt() for _ in range(50)}
        self.assertEqual(len(salts), 50)

    def test_generate_salt_length(self) -> None:
        self.assertEqual(len(generate_salt()), SALT_LEN * 2)


class TestAllFourDigitPins(unittest.TestCase):
    """All 10,000 4-digit PINs (0000–9999) hash without error."""

    def test_sample_100_pins_hash_and_verify(self) -> None:
        """Hash 100 evenly-spaced PINs across the 0000-9999 range."""
        for i in range(0, 10000, 100):  # 100 samples
            pin_str = f"{i:04d}"
            h = hash_pin(pin_str)
            self.assertTrue(verify_pin(pin_str, h),
                            f"PIN {pin_str} failed to verify")
            # Wrong pin should fail.
            wrong = f"{(i + 1) % 10000:04d}"
            if wrong != pin_str:
                self.assertFalse(verify_pin(wrong, h))

    def test_sample_boundary_pins(self) -> None:
        for pin_str in ("0000", "0001", "9998", "9999"):
            h = hash_pin(pin_str)
            self.assertTrue(verify_pin(pin_str, h))

    def test_sample_repeating_digit_pins(self) -> None:
        for digit in "0123456789":
            pin_str = digit * 4
            h = hash_pin(pin_str)
            self.assertTrue(verify_pin(pin_str, h))


class TestHashPinRaw(unittest.TestCase):
    """hash_pin_raw produces raw 32-byte hashes."""

    def test_raw_hash_length(self) -> None:
        salt = bytes(range(SALT_LEN))
        h = hash_pin_raw("1234", salt)
        self.assertEqual(len(h), HASH_LEN)

    def test_raw_hash_is_deterministic(self) -> None:
        salt = bytes(range(SALT_LEN))
        h1 = hash_pin_raw("1234", salt)
        h2 = hash_pin_raw("1234", salt)
        self.assertEqual(h1, h2)

    def test_raw_hash_matches_stdlib_pbkdf2(self) -> None:
        """hash_pin_raw must produce identical bytes to hashlib.pbkdf2_hmac.

        This ensures the stdlib fallback path is byte-compatible with
        the cryptography-backed primary path.
        """
        salt = bytes(range(SALT_LEN))
        actual = hash_pin_raw("1234", salt)
        expected = hashlib.pbkdf2_hmac(
            KDF_HASH, b"1234", salt, KDF_ITERATIONS, HASH_LEN)
        self.assertEqual(actual, expected)

    def test_different_pins_different_raw_hashes(self) -> None:
        salt = bytes(range(SALT_LEN))
        h1 = hash_pin_raw("1111", salt)
        h2 = hash_pin_raw("2222", salt)
        self.assertNotEqual(h1, h2)

    def test_different_salts_different_raw_hashes(self) -> None:
        salt1 = bytes(range(SALT_LEN))
        salt2 = bytes(reversed(range(SALT_LEN)))
        h1 = hash_pin_raw("1234", salt1)
        h2 = hash_pin_raw("1234", salt2)
        self.assertNotEqual(h1, h2)

    def test_raw_hash_rejects_non_string_pin(self) -> None:
        with self.assertRaises(ValueError):
            hash_pin_raw(1234, bytes(SALT_LEN))  # type: ignore[arg-type]

    def test_raw_hash_rejects_bad_salt_length(self) -> None:
        with self.assertRaises(ValueError):
            hash_pin_raw("1234", bytes(SALT_LEN - 1))
        with self.assertRaises(ValueError):
            hash_pin_raw("1234", bytes(SALT_LEN + 1))
        with self.assertRaises(ValueError):
            hash_pin_raw("1234", "not-bytes")  # type: ignore[arg-type]


class TestVerifyPinRaw(unittest.TestCase):
    """verify_pin_raw constant-time comparison."""

    def test_verify_correct(self) -> None:
        salt = bytes(range(SALT_LEN))
        expected = hash_pin_raw("4321", salt)
        self.assertTrue(verify_pin_raw("4321", salt, expected))

    def test_verify_wrong(self) -> None:
        salt = bytes(range(SALT_LEN))
        expected = hash_pin_raw("4321", salt)
        self.assertFalse(verify_pin_raw("1234", salt, expected))

    def test_verify_bad_hash_length(self) -> None:
        salt = bytes(range(SALT_LEN))
        # Wrong-length hash should return False, not raise.
        self.assertFalse(verify_pin_raw("4321", salt, b"too-short"))
        self.assertFalse(verify_pin_raw("4321", salt, b""))

    def test_verify_non_bytes_hash(self) -> None:
        salt = bytes(range(SALT_LEN))
        self.assertFalse(verify_pin_raw("4321", salt, "string-not-bytes"))  # type: ignore[arg-type]


class TestMalformedStoredHash(unittest.TestCase):
    """verify_pin safely rejects malformed stored hashes."""

    def test_garbage_stored(self) -> None:
        self.assertFalse(verify_pin("1234", "garbage"))

    def test_empty_stored(self) -> None:
        self.assertFalse(verify_pin("1234", ""))

    def test_wrong_algo(self) -> None:
        bad = f"argon2${KDF_ITERATIONS}${'00' * SALT_LEN}${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_non_numeric_iterations(self) -> None:
        bad = f"{FORMAT_PREFIX}$not-a-number${'00' * SALT_LEN}${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_zero_iterations(self) -> None:
        bad = f"{FORMAT_PREFIX}$0${'00' * SALT_LEN}${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_negative_iterations(self) -> None:
        bad = f"{FORMAT_PREFIX}$-1${'00' * SALT_LEN}${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_bad_salt_hex(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}$zzzz${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_bad_hash_hex(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}${'00' * SALT_LEN}$zzzz"
        self.assertFalse(verify_pin("1234", bad))

    def test_wrong_salt_length(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}${'00' * (SALT_LEN - 1)}${'00' * HASH_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_wrong_hash_length(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}${'00' * SALT_LEN}${'00' * (HASH_LEN - 1)}"
        self.assertFalse(verify_pin("1234", bad))

    def test_only_three_parts(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}${'00' * SALT_LEN}"
        self.assertFalse(verify_pin("1234", bad))

    def test_five_parts(self) -> None:
        bad = f"{FORMAT_PREFIX}${KDF_ITERATIONS}${'00' * SALT_LEN}${'00' * HASH_LEN}$extra"
        self.assertFalse(verify_pin("1234", bad))

    def test_non_string_stored(self) -> None:
        self.assertFalse(verify_pin("1234", None))  # type: ignore[arg-type]
        self.assertFalse(verify_pin("1234", 1234))  # type: ignore[arg-type]

    def test_non_string_pin(self) -> None:
        h = hash_pin("1234")
        self.assertFalse(verify_pin(1234, h))  # type: ignore[arg-type]
        self.assertFalse(verify_pin(None, h))  # type: ignore[arg-type]


class TestConstants(unittest.TestCase):
    """Module constants match the spec."""

    def test_format_prefix(self) -> None:
        self.assertEqual(FORMAT_PREFIX, "pbkdf2_sha256")

    def test_iterations_value(self) -> None:
        self.assertEqual(KDF_ITERATIONS, 200_000)

    def test_hash_algorithm(self) -> None:
        self.assertEqual(KDF_HASH, "sha256")

    def test_salt_length(self) -> None:
        self.assertEqual(SALT_LEN, 16)

    def test_hash_length(self) -> None:
        self.assertEqual(HASH_LEN, 32)

    def test_pin_min_length(self) -> None:
        self.assertEqual(PIN_MIN_LEN, 4)

    def test_pin_max_length(self) -> None:
        self.assertEqual(PIN_MAX_LEN, 6)

    def test_constants_match_config(self) -> None:
        from rask import config
        self.assertEqual(KDF_ITERATIONS, config.PIN_KDF_ITERATIONS)
        self.assertEqual(KDF_HASH, config.PIN_KDF_HASH)
        self.assertEqual(SALT_LEN, config.PIN_SALT_LEN)
        self.assertEqual(HASH_LEN, config.PIN_KEY_LEN)


class TestAvailabilityAndExceptions(unittest.TestCase):
    """Availability flag and exception hierarchy."""

    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(is_available(), bool)

    def test_invalid_pin_error_is_exception(self) -> None:
        self.assertTrue(issubclass(InvalidPinError, Exception))

    def test_invalid_pin_error_message(self) -> None:
        try:
            hash_pin("abc")
        except InvalidPinError as exc:
            self.assertIn("PIN", str(exc))
        else:
            self.fail("Expected InvalidPinError")


class TestIterationOverride(unittest.TestCase):
    """verify_pin honors the iterations field in the stored hash."""

    def test_verify_with_lower_iterations(self) -> None:
        """A stored hash with lower iterations still verifies."""
        salt = bytes(range(SALT_LEN))
        # Manually compute a hash with 10,000 iterations.
        raw = hashlib.pbkdf2_hmac(KDF_HASH, b"1234", salt, 10_000, HASH_LEN)
        stored = f"{FORMAT_PREFIX}$10000${salt.hex()}${raw.hex()}"
        self.assertTrue(verify_pin("1234", stored))
        self.assertFalse(verify_pin("9999", stored))

    def test_verify_with_higher_iterations(self) -> None:
        salt = bytes(range(SALT_LEN))
        raw = hashlib.pbkdf2_hmac(KDF_HASH, b"1234", salt, 500_000, HASH_LEN)
        stored = f"{FORMAT_PREFIX}$500000${salt.hex()}${raw.hex()}"
        self.assertTrue(verify_pin("1234", stored))


if __name__ == "__main__":
    unittest.main(verbosity=2)
