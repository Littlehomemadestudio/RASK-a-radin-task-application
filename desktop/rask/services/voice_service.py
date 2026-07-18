"""
rask.services.voice_service
===========================

Voice (speech-to-text) input.

Uses the ``speech_recognition`` Python package (which wraps several
backends — Google Web Speech API, Sphinx, etc.) and ``pyaudio`` for
microphone access.  Both are optional dependencies; if either is
missing, :meth:`is_available` returns ``False`` and all operations
gracefully no-op.

The default backend is Google's Web Speech API, which is the same
backend used by the web PWA's ``window.SpeechRecognition``.  Persian
is the default language code (``fa-IR``).

Mirrors ``web/js/voice.js``.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception

__all__ = ["VoiceService", "voice_service"]

_log = get_logger("services.voice")


# =============================================================================
# === Optional dependencies                                                 ===
# =============================================================================

try:
    import speech_recognition as sr  # type: ignore[import-not-found]
    _SR_AVAILABLE = True
except ImportError:  # pragma: no cover
    sr = None  # type: ignore[assignment]
    _SR_AVAILABLE = False

try:
    import pyaudio  # noqa: F401  # type: ignore[import-not-found]
    _PYAUDIO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYAUDIO_AVAILABLE = False


# =============================================================================
# === Language code mapping                                                  ===
# =============================================================================

_LANGUAGE_CODES: dict[str, str] = {
    "fa": "fa-IR",
    "en": "en-US",
    "ar": "ar-SA",
    "tr": "tr-TR",
    "ru": "ru-RU",
    "de": "de-DE",
    "fr": "fr-FR",
    "es": "es-ES",
    "zh": "zh-CN",
    "ja": "ja-JP",
}


def _resolve_lang_code(lang: str) -> str:
    """Return the BCP-47 language code for `lang` (e.g. 'fa' -> 'fa-IR')."""
    if not lang:
        return "fa-IR"
    if "-" in lang:
        return lang
    return _LANGUAGE_CODES.get(lang, "en-US")


# =============================================================================
# === VoiceService                                                           ===
# =============================================================================

class VoiceService:
    """Speech-to-text wrapper around ``speech_recognition``."""

    def __init__(self) -> None:
        self._recognizer: Any = None
        self._listening: bool = False
        # The current microphone (lazy-initialized).
        self._mic: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Initialize the recognizer if available."""
        if not self.is_available():
            _log.info("Voice service unavailable "
                      "(speech_recognition/pyaudio not installed)")
            return
        try:
            self._recognizer = sr.Recognizer()
            _log.debug("VoiceService initialized")
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            self._recognizer = None

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if both ``speech_recognition`` and ``pyaudio``
        are importable and a recognizer could be created.
        """
        return _SR_AVAILABLE and _PYAUDIO_AVAILABLE and self._recognizer is not None

    # ------------------------------------------------------------------
    # Microphone listen
    # ------------------------------------------------------------------

    def listen(
        self,
        callback: Callable[[str], None],
        lang: str = "fa",
        *,
        on_error: Optional[Callable[[str], None]] = None,
        on_end: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Start listening to the microphone.

        When speech is recognized, `callback` is invoked with the
        transcribed text.  If an error occurs, `on_error` (if given)
        is called with an error message.  When listening ends (either
        after a phrase or due to silence), `on_end` (if given) is
        called.

        This method is **synchronous** — it blocks until recognition
        completes.  For non-blocking behavior, call it from a worker
        thread.

        Returns ``True`` if listening started successfully.
        """
        if not self.is_available():
            msg = "Voice recognition not available"
            _log.warning(msg)
            if on_error:
                try:
                    on_error(msg)
                except Exception:  # noqa: BLE001
                    pass
            return False

        lang_code = _resolve_lang_code(lang)
        bus.publish("voice.listening", {"lang": lang_code})

        try:
            with sr.Microphone() as source:
                # Calibrate for ambient noise (1 second).
                self._recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = self._recognizer.listen(source)
        except KeyboardInterrupt:
            _log.info("Voice listening interrupted by user")
            bus.publish("voice.error", {"error": "interrupted"})
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    pass
            return False
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            bus.publish("voice.error", {"error": str(exc)})
            if on_error:
                try:
                    on_error(str(exc))
                except Exception:  # noqa: BLE001
                    pass
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    pass
            return False

        # Recognize via Google Web Speech API.
        try:
            text = self._recognizer.recognize_google(audio, language=lang_code)
        except sr.UnknownValueError:
            _log.info("Voice: could not understand audio")
            bus.publish("voice.error", {"error": "could not understand"})
            if on_error:
                try:
                    on_error("could not understand")
                except Exception:  # noqa: BLE001
                    pass
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    pass
            return True
        except sr.RequestError as exc:
            log_exception(_log, exc, {})
            bus.publish("voice.error", {"error": str(exc)})
            if on_error:
                try:
                    on_error(str(exc))
                except Exception:  # noqa: BLE001
                    pass
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    pass
            return False
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            bus.publish("voice.error", {"error": str(exc)})
            if on_error:
                try:
                    on_error(str(exc))
                except Exception:  # noqa: BLE001
                    pass
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    pass
            return False

        bus.publish("voice.result", {"text": text, "lang": lang_code})
        try:
            callback(text)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        if on_end:
            try:
                on_end()
            except Exception:  # noqa: BLE001
                pass
        return True

    def stop(self) -> None:
        """Stop any in-progress listening.

        The ``speech_recognition`` library doesn't expose a clean
        stop API — this method signals intent and lets the current
        ``listen()`` call return on its own.  A subsequent call to
        :meth:`listen` will start fresh.
        """
        self._listening = False
        _log.debug("Voice stop requested")

    def cancel(self) -> None:
        """Cancel voice input (alias for :meth:`stop`)."""
        self.stop()

    # ------------------------------------------------------------------
    # File-based recognition
    # ------------------------------------------------------------------

    def recognize_file(self, path: str, lang: str = "fa") -> str:
        """Recognize speech from an audio file (wav, aiff, flac).

        Returns the transcribed text (empty string on failure).
        """
        if not self.is_available():
            _log.warning("recognize_file: voice not available")
            return ""
        if not path:
            return ""

        lang_code = _resolve_lang_code(lang)
        try:
            with sr.AudioFile(path) as source:
                audio = self._recognizer.record(source)
            text = self._recognizer.recognize_google(audio, language=lang_code)
            bus.publish("voice.result", {"text": text, "lang": lang_code,
                                           "source": "file", "path": path})
            return text
        except sr.UnknownValueError:
            _log.info("recognize_file: could not understand audio")
            return ""
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"path": path})
            bus.publish("voice.error", {"error": str(exc),
                                          "source": "file", "path": path})
            return ""


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

voice_service: VoiceService = VoiceService()
