"""voice.py — Voice input for Rask (1:1 mirror of web/js/voice.js).

Uses the `speech_recognition` library (optional) to capture microphone
input and convert it to text. Supports Persian (fa-IR) and English (en-US).

If `speech_recognition` is not installed, or if no microphone is available,
the module degrades gracefully — voice input buttons simply show an error.
"""
from __future__ import annotations
import platform
import shutil
from typing import Callable, Optional


# =====================================================================
# === OPTIONAL DEPENDENCY ===
# =====================================================================
try:
    import speech_recognition as sr
    _SR_AVAILABLE = True
except ImportError:
    _SR_AVAILABLE = False


def voice_available() -> bool:
    """Return True if voice input is available (library + microphone present)."""
    if not _SR_AVAILABLE:
        return False
    try:
        r = sr.Recognizer()
        m = sr.Microphone()
        # Just check we can instantiate
        return True
    except Exception:
        return False


# =====================================================================
# === LISTEN ===
# =====================================================================
def listen(lang: str = "fa",
           on_result: Optional[Callable[[str], None]] = None,
           on_error: Optional[Callable[[str], None]] = None,
           on_start: Optional[Callable[[], None]] = None,
           on_end: Optional[Callable[[], None]] = None,
           timeout: int = 10,
           phrase_time_limit: int = 10) -> None:
    """Listen for a single utterance and convert to text.
    
    Calls on_start when listening begins, on_result(text) when recognized,
    on_error(msg) if it fails, and on_end when finished (always).
    
    This function runs synchronously — caller should run it in a thread
    if blocking the UI is undesirable.
    """
    if not _SR_AVAILABLE:
        if on_error:
            on_error("Voice input unavailable. Install: pip install speech_recognition pyaudio")
        if on_end:
            on_end()
        return
    try:
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            if on_start:
                on_start()
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        # Use Google's free web API (requires internet)
        lang_code = "fa-IR" if lang == "fa" else "en-US"
        try:
            text = r.recognize_google(audio, language=lang_code)
            if on_result:
                on_result(text)
        except sr.UnknownValueError:
            if on_error:
                on_error("Could not understand audio")
        except sr.RequestError as e:
            if on_error:
                on_error(f"Speech recognition service error: {e}")
    except Exception as e:
        if on_error:
            on_error(f"Voice input error: {e}")
    finally:
        if on_end:
            on_end()


# =====================================================================
# === BACKGROUND LISTEN ===
# =====================================================================
def listen_async(lang: str = "fa",
                  on_result: Optional[Callable[[str], None]] = None,
                  on_error: Optional[Callable[[str], None]] = None,
                  on_start: Optional[Callable[[], None]] = None,
                  on_end: Optional[Callable[[], None]] = None) -> Optional[threading.Thread]:
    """Run listen() in a background thread. Returns the Thread object."""
    import threading
    t = threading.Thread(target=listen, args=(lang, on_result, on_error, on_start, on_end),
                         daemon=True)
    t.start()
    return t


# =====================================================================
# === SUPPORTED LANGUAGES ===
# =====================================================================
def supported_languages() -> list[str]:
    """Return list of supported language codes."""
    return ["fa", "en"]


# =====================================================================
# === PLATFORM NOTES ===
# =====================================================================
def install_instructions() -> str:
    """Return platform-specific install instructions for voice support."""
    if platform.system() == "Windows":
        return "pip install SpeechRecognition pyaudio"
    if platform.system() == "Darwin":  # macOS
        return "pip install SpeechRecognition"  # uses built-in microphone
    # Linux
    return "pip install SpeechRecognition pyaudio  # may also need: apt install portaudio19-dev python3-pyaudio"


def microphone_available() -> bool:
    """Check if a microphone input device is available."""
    if not _SR_AVAILABLE:
        return False
    try:
        with sr.Microphone():
            return True
    except Exception:
        return False
