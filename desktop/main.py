#!/usr/bin/env python3
"""main.py — Entry point for the Rask desktop app.

Usage:
    python main.py

Optional dependencies (auto-detected at runtime):
    pip install cryptography    # for AES-256-GCM encrypted backups + PIN hashing
    pip install reportlab       # for PDF export
    pip install SpeechRecognition pyaudio  # for voice input
"""
from __future__ import annotations
import sys
import traceback


def main() -> int:
    """Launch the Rask desktop app."""
    try:
        # Ensure we're on Python 3.9+
        if sys.version_info < (3, 9):
            print("ERROR: Rask requires Python 3.9 or later.", file=sys.stderr)
            print(f"You're running Python {sys.version}.", file=sys.stderr)
            print("Please upgrade from https://python.org", file=sys.stderr)
            return 1
        # Import and run
        from rask.app import RaskApp
        app = RaskApp()
        app.run()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
