"""
rask.utils
==========

Utility scripts and helpers for the Rask desktop application.

This package contains developer-facing tools that are NOT part of the
core app runtime but are useful for:

  • Database inspection and migration (``migrations``,
    ``db_inspector``)
  • Demo / seed data generation (``seed_data``)
  • Data analysis (``data_analyzer``)
  • Export templates (``export_templates``)
  • Persian / English formatting helpers (``formatters``)
  • Extra input validators (``validators_extra``)
  • CLI pretty-printing helpers (``cli_helpers``)
  • Debugging and profiling (``debug``)

Importing this package is cheap — submodules are loaded lazily on
first access to avoid pulling in optional dependencies (e.g.
``matplotlib`` for chart helpers) when they aren't needed.

Quick example
-------------

    >>> from rask.utils.formatters import format_minutes_long
    >>> format_minutes_long(150, lang="fa")
    '۲ ساعت و ۳۰ دقیقه'

    >>> from rask.utils.db_inspector import inspect
    >>> report = inspect()  # returns dict of DB stats
"""
from __future__ import annotations

__all__ = [
    "migrations",
    "seed_data",
    "db_inspector",
    "data_analyzer",
    "export_templates",
    "formatters",
    "validators_extra",
    "cli_helpers",
    "debug",
]

__version__: str = "1.0.0"
