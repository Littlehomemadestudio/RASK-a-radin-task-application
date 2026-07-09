"""
main.py — Rask app entry point.

Kivy + Buildozer launch this file on Android (and on desktop for testing).
It instantiates the RaskApp which builds the whole UI tree.
"""
import os
import sys
from pathlib import Path

# Make 'rask' package importable both on Android (via buildozer) and on desktop
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kivy.config import Config

# Lock to portrait (matches buildozer.spec)
Config.set("graphics", "orientation", "portrait")
Config.set("graphics", "width", "405")
Config.set("graphics", "height", "810")
Config.set("kivy", "exit_on_escape", "0")
Config.set("input", "mouse", "mouse, multitouch_on_demand")

# RTL hint
Config.set("kivy", "label_emoji", "1")
Config.set("kivy", "default_font", ["Vazirmatn", "assets/fonts/vazirmatn.ttf"])

from kivy.app import App
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

from rask.app import RaskApp


def main():
    # Gold-on-dark window background (visible during transitions)
    Window.clearcolor = get_color_from_hex("#0E0E10")
    app = RaskApp()
    app.run()


if __name__ == "__main__":
    main()
