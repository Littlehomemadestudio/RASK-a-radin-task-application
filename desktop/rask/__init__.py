"""
rask
====

Top-level package for the **Rask** desktop application — a beautiful,
offline-first time-tracking app built on top of CustomTkinter.

Subpackages
-----------
``rask.config``           — central configuration constants
``rask.i18n``             — internationalisation (Persian-first)
``rask.database``         — SQLite persistence layer
``rask.core``             — Jalali calendar, crypto, PIN, time, event-bus, …
``rask.services``         — high-level service layer (activity, goal, …)
``rask.ui``               — CustomTkinter widgets, screens, dialogs, app
``rask.export``           — low-level PDF / CSV / JSON / image exporters
``rask.cli``              — command-line interface module
``rask.check_env``        — runtime environment / dependency probe

Typical usage
-------------
Launch the GUI::

    from rask import RaskApp
    RaskApp().run()

Run a one-off CLI command::

    from rask.cli import main as cli_main
    cli_main(["stats"])

Versioning
----------
The version constants below are kept in sync with
:data:`rask.config.APP_VERSION` and :data:`rask.config.APP_BUILD`.  They
are re-exported here so callers can introspect the installed version
without importing the (much larger) :mod:`rask.config` module.
"""
from __future__ import annotations

__version__: str = "2.0.0"
__author__: str = "Littlehomemade Studio"
__license__: str = "MIT"

# Build identifier (see rask.config.APP_BUILD).  Kept here as a plain
# int so importing ``rask`` does not require importing ``rask.config``
# (which would in turn touch the filesystem to compute paths).
__build__: int = 2025_07_18_001


# -----------------------------------------------------------------------------
# Lazy sub-module re-exports
# -----------------------------------------------------------------------------
# Importing :mod:`rask.config` is cheap (pure data), but :mod:`rask.ui`
# pulls in CustomTkinter at import time which is slow and not always
# available (e.g. inside headless test runners).  We therefore expose
# the most commonly used sub-modules as attributes on the top-level
# ``rask`` package but defer the actual import until first access via
# PEP 562 module-level ``__getattr__``.

from . import config  # noqa: F401,E402 — pure-data module, safe to import
from . import i18n    # noqa: F401,E402 — pure-data + dict catalogues
from . import database  # noqa: F401,E402 — pure sqlite3, side-effect free
from . import core    # noqa: F401,E402 — pure helpers
from . import services  # noqa: F401,E402 — wraps database, lazy deps

# ``ui`` is imported lazily because it transitively imports CustomTkinter
# which can be slow (200ms+) and may not be installed in headless envs.
_LAZY_SUBMODULES: tuple[str, ...] = ("ui", "export", "cli", "check_env")


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """PEP 562 lazy importer for heavy sub-packages.

    ``rask.ui``, ``rask.export``, ``rask.cli`` and ``rask.check_env``
    are only imported on first attribute access.  This keeps
    ``import rask`` fast for CLI / library use cases that don't need
    the GUI stack.
    """
    if name in _LAZY_SUBMODULES:
        import importlib
        mod = importlib.import_module(f".{name}", __name__)
        globals()[name] = mod
        return mod
    # Convenience re-export: ``from rask import RaskApp``
    if name == "RaskApp":
        from .ui.app import RaskApp
        globals()["RaskApp"] = RaskApp
        return RaskApp
    raise AttributeError(f"module 'rask' has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover — introspection helper
    base = list(globals().keys()) + list(_LAZY_SUBMODULES) + ["RaskApp"]
    return sorted(set(base))


__all__ = [
    "config",
    "i18n",
    "database",
    "core",
    "services",
    "ui",
    "export",
    "cli",
    "check_env",
    "RaskApp",
    "__version__",
    "__author__",
    "__license__",
    "__build__",
]
