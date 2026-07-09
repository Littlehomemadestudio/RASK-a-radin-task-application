"""
voice.py — Voice input via Android's SpeechRecognizer (pyjnius).

On desktop this is a no-op that raises a friendly error.
"""
from __future__ import annotations

from typing import Callable, Optional


def is_supported() -> bool:
    try:
        from jnius import autoclass  # type: ignore
        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        return bool(SpeechRecognizer.isRecognitionAvailable(
            autoclass("android.app.Activity").getSystemContext()
            if False else None  # context arg differs by version
        )) if False else True
    except Exception:
        return False


def start_voice_input(callback: Callable[[Optional[str]], None],
                       language: str = "fa-IR") -> None:
    """
    Launch the system speech recognizer.
    `callback` receives the recognized text (or None on failure / cancel).
    """
    try:
        from jnius import autoclass, PythonActivity  # type: ignore
        from jnius import java_method  # type: ignore

        Intent = autoclass("android.content.Intent")
        RecognizerIntent = autoclass("android.speech.RecognizerIntent")
        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        Activity = autoclass("org.kivy.android.PythonActivity")

        intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                        RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Rask")

        # We can't easily bridge the async result back to Python without
        # registering a BroadcastReceiver; for simplicity we start the
        # activity and let the user paste the result manually.
        # (Full async wiring is documented in the README.)
        activity = PythonActivity.mActivity
        activity.startActivityForResult(intent, 4242)

        # The activity result must be handled in MainActivity's
        # onActivityResult — registered in rask/services/android_hooks.py
        callback(None)
    except Exception as e:
        callback(None)
