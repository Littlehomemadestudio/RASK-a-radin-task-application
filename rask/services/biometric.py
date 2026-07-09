"""
biometric.py — App lock via Android BiometricPrompt or PIN.

Exposes:
  - is_biometric_available()
  - authenticate_biometric(on_success, on_failure)
  - verify_pin(pin) -> bool
  - setup_pin(pin)
  - has_pin() -> bool
  - clear_lock()
"""
from __future__ import annotations

from typing import Callable, Optional

from rask import config as cfg
from rask.data import database as db
from rask.utils.crypto import hash_pin, verify_pin


def lock_mode() -> str:
    return db.pref_get(cfg.PREF_LOCK_MODE, cfg.LOCK_NONE)


def set_lock_mode(mode: str) -> None:
    db.pref_set(cfg.PREF_LOCK_MODE, mode)


def has_pin() -> bool:
    return bool(db.pref_get(cfg.PREF_PIN_HASH, ""))


def setup_pin(pin: str) -> None:
    salt, h = hash_pin(pin)
    db.pref_set(cfg.PREF_PIN_HASH, h)
    db.pref_set(cfg.PREF_PIN_SALT, salt)
    set_lock_mode(cfg.LOCK_PIN)


def verify_pin(pin: str) -> bool:
    h = db.pref_get(cfg.PREF_PIN_HASH, "")
    salt = db.pref_get(cfg.PREF_PIN_SALT, "")
    if not h or not salt:
        return False
    return verify_pin(pin, salt, h)


def clear_lock() -> None:
    db.pref_set(cfg.PREF_LOCK_MODE, cfg.LOCK_NONE)
    db.pref_set(cfg.PREF_PIN_HASH, "")
    db.pref_set(cfg.PREF_PIN_SALT, "")


# === Biometric ===

def is_biometric_available() -> bool:
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        BiometricManager = autoclass("androidx.biometric.BiometricManager")
        ctx = Context.mActivity.getApplicationContext()
        bm = getattr(BiometricManager, "from")(ctx)
        return bm.canAuthenticate(
            BiometricManager.Authenticators.BIOMETRIC_WEAK
        ) == BiometricManager.BIOMETRIC_SUCCESS
    except Exception:
        return False


def authenticate_biometric(on_success: Callable[[], None],
                            on_failure: Callable[[str], None]) -> bool:
    """Returns True if the prompt was shown, False if unavailable."""
    try:
        from jnius import autoclass, PythonActivity  # type: ignore
        BiometricPrompt = autoclass("androidx.biometric.BiometricPrompt")
        PromptInfo = autoclass("androidx.biometric.BiometricPrompt$PromptInfo")
        Executor = autoclass("java.util.concurrent.Executors")

        activity = PythonActivity.mActivity
        executor = Executor.newSingleThreadExecutor()

        # Build prompt info
        info_builder = PromptInfo.Builder()
        info_builder.setTitle("Rask")
        info_builder.setSubtitle("Unlock with biometrics")
        info_builder.setNegativeButtonText("Cancel")
        info = info_builder.build()

        # BiometricPrompt requires Activity + Executor + callback
        # The callback is a Java class implementing BiometricPrompt.AuthenticationCallback.
        # Without a custom Java helper class, we cannot register a Python callback
        # directly — the call below is a best-effort that may fail silently.
        # Full implementation requires the Java helper in java-src/.
        prompt = BiometricPrompt(activity, executor, None)  # callback omitted
        prompt.authenticate(info)
        return True
    except Exception as e:
        on_failure(str(e))
        return False
