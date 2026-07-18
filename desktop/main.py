#!/usr/bin/env python3
"""main.py — Rask desktop entry point.

Run with:  python main.py
A 1:1 desktop port of the Rask web PWA — gold-on-dark, offline-first,
all 7 features (smart logging, goals/streaks, time aggregation, stats,
widgets/notifications, backup/lock, splash+onboarding).
"""
import sys
import os

# Allow running this file directly: add parent of `rask/` package to sys.path
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from rask.app import RaskApp


def main():
    app = RaskApp()
    app.run()


if __name__ == "__main__":
    main()
