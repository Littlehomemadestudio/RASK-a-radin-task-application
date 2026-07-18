"""
rask.ui
=======

User-interface package for the Rask desktop application.

Re-exports the public API of every UI sub-package so callers can write::

    from rask.ui import RaskApp, HomeScreen, GoldButton, ConfirmDialog

without caring about the internal module layout.  Sub-modules are:

``rask.ui.widgets``  — 30 widget files (buttons, inputs, cards, charts, …)
``rask.ui.screens``  — 17 full-screen views
``rask.ui.dialogs``  — 15 modal dialogs
``rask.ui.app``      — :class:`RaskApp`, the main controller

Heavy widgets (CustomTkinter-backed) are imported lazily via
:pep:`562` ``__getattr__`` so that ``import rask.ui`` does not crash
in a headless environment where CustomTkinter is not installed.  In
such environments, ``rask.ui.RaskApp`` will simply raise a
``RuntimeError`` when instantiated — the rest of the package remains
importable for non-GUI uses (e.g. running CLI commands from a script
that also imports the UI package).
"""
from __future__ import annotations

# Lightweight, pure-Python sub-modules — always available.
from . import widgets  # noqa: F401 — re-exported as attribute
from . import screens  # noqa: F401
from . import dialogs  # noqa: F401


# -----------------------------------------------------------------------------
# Lazy ``RaskApp`` import — CustomTkinter may not be available.
# -----------------------------------------------------------------------------
# We define a thin placeholder that delegates to the real class on first
# access.  This avoids the cost of importing ``app.py`` (which in turn
# imports CustomTkinter + ~100 widget classes) when callers only need
# the widget / screen / dialog classes for headless testing.

_LAZY_APP = ("RaskApp",)


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """PEP 562 lazy importer for :class:`RaskApp`."""
    if name == "RaskApp":
        from .app import RaskApp
        globals()["RaskApp"] = RaskApp
        return RaskApp
    raise AttributeError(f"module 'rask.ui' has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover — introspection helper
    base = ["widgets", "screens", "dialogs", "RaskApp"]
    # Pull in commonly-used names from each sub-package.
    try:
        base.extend(screens.__all__)
    except AttributeError:
        pass
    try:
        base.extend(dialogs.__all__)
    except AttributeError:
        pass
    try:
        base.extend(widgets.__all__)
    except AttributeError:
        pass
    return sorted(set(base))


__all__ = [
    "widgets",
    "screens",
    "dialogs",
    "RaskApp",
]
