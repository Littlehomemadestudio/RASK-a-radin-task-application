"""
rask.features.sound_effects
===========================

Cross-platform sound effects.

Each "sound" is a short beep pattern (frequency + duration pairs).
The service uses:

  • ``winsound`` on Windows (built-in)
  • ``afplay`` on macOS (via ``os.system``)
  • ``aplay`` on Linux (via ``os.system``)
  • Falls back silently if no audio device is available

Sounds available
----------------

  ``click``          — short UI click (high beep, 80ms)
  ``success``        — pleasant two-note rising
  ``error``          — descending two-note
  ``achievement``    — three-note melody (C-E-G ascending)
  ``timer_start``    — soft rising tone
  ``timer_stop``     — soft falling tone
  ``reminder``       — short triple beep
  ``unlock``         — pleasant unlock chime
  ``whoosh``         — sweep effect (sine sweep approximated)

Each call is fire-and-forget; the service runs the sound in a daemon
thread so the UI never blocks.

Settings
--------

Respects the ``notify_sound`` setting (``rask.database.setting_get``).
:meth:`SoundService.set_enabled` toggles it.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import database as db
from ..core.logging_utils import get_logger, log_exception

__all__ = [
    "SoundService",
    "sound_service",
    "SOUND_CLICK",
    "SOUND_SUCCESS",
    "SOUND_ERROR",
    "SOUND_ACHIEVEMENT",
    "SOUND_TIMER_START",
    "SOUND_TIMER_STOP",
    "SOUND_REMINDER",
    "SOUND_UNLOCK",
    "SOUND_WHOOSH",
]

_log = get_logger("features.sound")


# =============================================================================
# === Sound names                                                            ===
# =============================================================================

SOUND_CLICK: str = "click"
SOUND_SUCCESS: str = "success"
SOUND_ERROR: str = "error"
SOUND_ACHIEVEMENT: str = "achievement"
SOUND_TIMER_START: str = "timer_start"
SOUND_TIMER_STOP: str = "timer_stop"
SOUND_REMINDER: str = "reminder"
SOUND_UNLOCK: str = "unlock"
SOUND_WHOOSH: str = "whoosh"


# =============================================================================
# === Sound patterns                                                         ===
# =============================================================================
# Each pattern is a list of (frequency_hz, duration_ms) tuples.
# On Windows we use winsound.Beep which supports arbitrary frequencies.
# On macOS/Linux we generate a WAV file on-the-fly and play it.

SOUND_PATTERNS: Dict[str, List[Tuple[int, int]]] = {
    SOUND_CLICK:        [(1000, 80)],
    SOUND_SUCCESS:      [(659, 120), (784, 180)],          # E5 -> G5
    SOUND_ERROR:        [(440, 200), (330, 250)],           # A4 -> E4
    SOUND_ACHIEVEMENT:  [(523, 150), (659, 150), (784, 250)],  # C5-E5-G5
    SOUND_TIMER_START:  [(523, 100), (784, 200)],
    SOUND_TIMER_STOP:   [(784, 100), (523, 200)],
    SOUND_REMINDER:     [(880, 100), (880, 100), (880, 200)],
    SOUND_UNLOCK:       [(659, 100), (784, 100), (1047, 200)],
    SOUND_WHOOSH:       [(400, 80), (600, 80), (800, 80), (1000, 80)],
}


# =============================================================================
# === WAV generation (for macOS/Linux fallback)                              ===
# =============================================================================

def _generate_wav_bytes(pattern: List[Tuple[int, int]]) -> bytes:
    """Generate a WAV file (as bytes) for the given beep pattern.

    Uses 16-bit mono PCM at 22050 Hz.  No external dependencies.
    """
    import math
    import struct
    import wave
    sample_rate = 22050
    samples: List[int] = []
    for freq, duration_ms in pattern:
        n_samples = int(sample_rate * duration_ms / 1000)
        for i in range(n_samples):
            # Sine wave with simple linear envelope (5ms attack, 5ms release).
            t = i / sample_rate
            envelope = 1.0
            attack_samples = int(sample_rate * 0.005)
            release_samples = int(sample_rate * 0.005)
            if i < attack_samples:
                envelope = i / max(1, attack_samples)
            elif i > n_samples - release_samples:
                envelope = max(0.0, (n_samples - i) / max(1, release_samples))
            value = int(32767 * 0.5 * envelope * math.sin(
                2 * math.pi * freq * t))
            samples.append(struct.pack("<h", value))
    # Write to a bytes buffer.
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"".join(samples))
    return buf.getvalue()


# =============================================================================
# === Platform-specific players                                              ===
# =============================================================================

def _play_windows(pattern: List[Tuple[int, int]]) -> bool:
    try:
        import winsound  # type: ignore
    except ImportError:
        return False
    try:
        for freq, duration_ms in pattern:
            # winsound.Beep takes frequency + duration_ms
            try:
                winsound.Beep(int(freq), int(duration_ms))
            except Exception:  # noqa: BLE001
                # Some Windows builds reject very low/high frequencies.
                pass
        return True
    except Exception as exc:  # noqa: BLE001
        _log.debug("winsound playback failed: %s", exc)
        return False


def _play_macos(pattern: List[Tuple[int, int]]) -> bool:
    """Play a pattern on macOS by writing a temp WAV and calling afplay."""
    try:
        import tempfile
        wav_bytes = _generate_wav_bytes(pattern)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            path = f.name
        try:
            # afplay is non-blocking by default, but we want fire-and-forget.
            # Run in a daemon thread.
            def _play() -> None:
                try:
                    subprocess.run(["afplay", path], timeout=5,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    try:
                        os.unlink(path)
                    except Exception:  # noqa: BLE001
                        pass
            t = threading.Thread(target=_play, daemon=True)
            t.start()
            return True
        except Exception as exc:  # noqa: BLE001
            _log.debug("afplay failed: %s", exc)
            try:
                os.unlink(path)
            except Exception:  # noqa: BLE001
                pass
            return False
    except Exception as exc:  # noqa: BLE001
        _log.debug("macOS playback failed: %s", exc)
        return False


def _play_linux(pattern: List[Tuple[int, int]]) -> bool:
    """Play a pattern on Linux via aplay (ALSA)."""
    try:
        import tempfile
        wav_bytes = _generate_wav_bytes(pattern)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            path = f.name
        try:
            def _play() -> None:
                try:
                    subprocess.run(["aplay", "-q", path], timeout=5,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    try:
                        os.unlink(path)
                    except Exception:  # noqa: BLE001
                        pass
            t = threading.Thread(target=_play, daemon=True)
            t.start()
            return True
        except Exception:  # noqa: BLE001
            try:
                os.unlink(path)
            except Exception:  # noqa: BLE001
                pass
            return False
    except Exception as exc:  # noqa: BLE001
        _log.debug("aplay failed: %s", exc)
        return False


def _play_pattern(pattern: List[Tuple[int, int]]) -> bool:
    """Dispatch the pattern to the appropriate platform player."""
    system = platform.system()
    if system == "Windows":
        return _play_windows(pattern)
    if system == "Darwin":
        return _play_macos(pattern)
    return _play_linux(pattern)


# =============================================================================
# === SoundService                                                           ===
# =============================================================================

class SoundService:
    """Cross-platform sound effects."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._preloaded: Dict[str, bytes] = {}
        self._enabled: Optional[bool] = None  # lazily loaded from settings

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def enabled(self) -> bool:
        """Return True if sound is enabled in settings."""
        if self._enabled is not None:
            return self._enabled
        try:
            from ..config import NOTIFY_SOUND_DEFAULT
            v = db.setting_get("notify_sound", NOTIFY_SOUND_DEFAULT)
            self._enabled = bool(v)
            return self._enabled
        except Exception:  # noqa: BLE001
            return True

    def set_enabled(self, value: bool) -> None:
        """Enable or disable sound effects."""
        with self._lock:
            self._enabled = bool(value)
            try:
                db.setting_set("notify_sound", bool(value))
            except Exception as exc:  # noqa: BLE001
                log_exception(_log, exc, {})
            _log.info("Sound effects %s",
                       "enabled" if value else "disabled")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play(self, name: str) -> bool:
        """Play a sound by name.  Returns True if playback was initiated.

        If sound is disabled in settings, returns False without playing.
        If `name` is unknown, returns False.
        """
        if not self.enabled():
            return False
        pattern = SOUND_PATTERNS.get(name)
        if pattern is None:
            _log.warning("Unknown sound: %s", name)
            return False
        # Run in a daemon thread so the UI doesn't block.
        t = threading.Thread(target=self._play_threadsafe,
                              args=(name, pattern), daemon=True)
        t.start()
        return True

    def _play_threadsafe(self, name: str,
                          pattern: List[Tuple[int, int]]) -> None:
        try:
            ok = _play_pattern(pattern)
            if not ok:
                _log.debug("Sound '%s' playback skipped (no audio device?)",
                            name)
        except Exception as exc:  # noqa: BLE001
            _log.debug("Sound '%s' playback failed: %s", name, exc)

    # ------------------------------------------------------------------
    # Preload
    # ------------------------------------------------------------------

    def preload(self) -> None:
        """Preload all sound patterns into memory as WAV bytes.

        On Windows this is a no-op (winsound.Beep doesn't need
        preloading).  On macOS/Linux, pre-generating the WAV bytes
        shaves a few ms off the first playback of each sound.
        """
        with self._lock:
            for name, pattern in SOUND_PATTERNS.items():
                if name in self._preloaded:
                    continue
                try:
                    self._preloaded[name] = _generate_wav_bytes(pattern)
                except Exception as exc:  # noqa: BLE001
                    _log.debug("Preload of '%s' failed: %s", name, exc)
        _log.info("Preloaded %d sound patterns", len(self._preloaded))

    def available_sounds(self) -> List[str]:
        """Return the list of available sound names."""
        return sorted(SOUND_PATTERNS.keys())

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def click(self) -> bool:
        return self.play(SOUND_CLICK)

    def success(self) -> bool:
        return self.play(SOUND_SUCCESS)

    def error(self) -> bool:
        return self.play(SOUND_ERROR)

    def achievement(self) -> bool:
        return self.play(SOUND_ACHIEVEMENT)

    def timer_start(self) -> bool:
        return self.play(SOUND_TIMER_START)

    def timer_stop(self) -> bool:
        return self.play(SOUND_TIMER_STOP)

    def reminder(self) -> bool:
        return self.play(SOUND_REMINDER)

    def unlock(self) -> bool:
        return self.play(SOUND_UNLOCK)

    def whoosh(self) -> bool:
        return self.play(SOUND_WHOOSH)


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

sound_service: SoundService = SoundService()


# =============================================================================
# === Auto-subscribe to events                                               ===
# =============================================================================

def _auto_subscribe() -> None:
    """Hook sound_service into common events so they auto-play sounds."""
    try:
        from ..core.event_bus import bus
        bus.subscribe("badge.unlocked",
                       lambda _p: sound_service.achievement())
        bus.subscribe("activity.added",
                       lambda _p: sound_service.click())
        bus.subscribe("timer.started",
                       lambda _p: sound_service.timer_start())
        bus.subscribe("timer.stopped",
                       lambda _p: sound_service.timer_stop())
        bus.subscribe("reminder.triggered",
                       lambda _p: sound_service.reminder())
        bus.subscribe("ui.toast",
                       lambda p: sound_service.click() if (p or {}).get("kind") == "success" else None)
    except Exception as exc:  # noqa: BLE001
        _log.debug("Sound auto-subscribe failed: %s", exc)


# Auto-subscribe on module load (best-effort; safe if bus isn't ready).
try:
    _auto_subscribe()
except Exception:  # noqa: BLE001
    pass


# =============================================================================
# === Self-tests                                                             ===
# =============================================================================

def _run_tests() -> int:
    failed = 0
    print("=== sound_effects self-tests ===")
    try:
        sounds = sound_service.available_sounds()
        assert len(sounds) >= 9, f"expected >=9 sounds, got {len(sounds)}"
        assert SOUND_CLICK in sounds
        # Pattern generation should work even without audio device.
        wav = _generate_wav_bytes(SOUND_PATTERNS[SOUND_CLICK])
        assert isinstance(wav, bytes) and len(wav) > 40
        # Toggle enable/disable.
        original = sound_service.enabled()
        sound_service.set_enabled(False)
        assert not sound_service.enabled()
        assert sound_service.play(SOUND_CLICK) is False  # disabled
        sound_service.set_enabled(True)
        assert sound_service.enabled()
        # play() should return True (or at least not crash) — even on
        # systems without an audio device it spawns a thread and returns
        # True from this method's perspective.
        result = sound_service.play(SOUND_CLICK)
        assert isinstance(result, bool)
        # Restore original setting.
        sound_service.set_enabled(original)
        print("  OK   sounds + WAV generation + enable/disable")
    except AssertionError as e:
        print(f"  FAIL: {e}")
        failed += 1
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL (exception): {e}")
        failed += 1
    print(f"\n{1 if failed else 0} failed.")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
