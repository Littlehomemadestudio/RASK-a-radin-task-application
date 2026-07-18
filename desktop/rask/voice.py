"""voice.py — Voice input (mirror of web/js/voice.js).

Uses the `speech_recognition` package if available; otherwise reports unsupported.
Falls back gracefully — the rest of the app still works without it.
"""
from __future__ import annotations
from typing import Callable, Optional


def supported() -> bool:
    try:
        import speech_recognition  # noqa: F401
        return True
    except Exception:
        return False


def listen(lang: str, on_result: Callable[[str], None],
           on_error: Optional[Callable[[str], None]] = None,
           on_end: Optional[Callable[[], None]] = None) -> None:
    """Blocks until one phrase is recognized or an error occurs. Runs in a worker thread."""
    if not supported():
        if on_error:
            on_error("Speech recognition not installed. Run: pip install speech_recognition")
        return
    import threading
    import speech_recognition as sr

    def _worker():
        try:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=10, phrase_time_limit=10)
            text = r.recognize_google(audio, language="fa-IR" if lang == "fa" else "en-US")
            on_result(text)
        except Exception as e:
            if on_error:
                on_error(str(e))
        finally:
            if on_end:
                on_end()

    threading.Thread(target=_worker, daemon=True).start()
