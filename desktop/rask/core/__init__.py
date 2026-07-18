"""
rask.core
=========

Core utility modules shared across the Rask desktop application.

Submodules
----------
jalali        — Gregorian ↔ Jalali (Persian Solar) calendar conversion
crypto        — AES-256-GCM encrypted backups (compatible with web PWA)
pin           — PBKDF2-SHA256 PIN hashing (compatible with web PWA)
time_utils    — ISO datetime helpers, duration / relative formatting
event_bus     — In-process pub/sub bus
validators    — Input validation helpers
helpers       — Math, color, collection, and id utilities
logging_utils — Structured logging setup and context managers

All modules are pure-Python and depend only on the stdlib plus the
`cryptography` package (for `crypto` and `pin`, with graceful fallback
when it is unavailable).
"""
from __future__ import annotations

__all__ = [
    "jalali",
    "crypto",
    "pin",
    "time_utils",
    "event_bus",
    "validators",
    "helpers",
    "logging_utils",
]
