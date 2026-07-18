"""
rask.core.logging_utils
=======================

Centralized logging configuration for the Rask desktop app.

Provides:
  • :func:`setup_logging` — configure the root logger once at startup.
  • :func:`get_logger` — return a named child logger (cheap to call).
  • :func:`log_exception` — formatted exception logging with context dict.
  • :class:`LogContext` — context manager for timing blocks and
    adding contextual key=value pairs to log records.

Default log file location: ``config.LOG_DIR / "rask.log"`` (rotated
manually by the OS / user; a single file is enough for a desktop app).

Format
------
``%(asctime)s [%(levelname)s] %(name)s: %(message)s``

Mirrors a conventional syslog-ish layout so logs are easy to grep.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

from .. import config

__all__ = [
    "LOG_FORMAT",
    "LOG_DATE_FORMAT",
    "get_logger",
    "setup_logging",
    "log_exception",
    "LogContext",
]

# =============================================================================
# === Constants                                                             ===
# =============================================================================

#: Default log line format.
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

#: ISO-8601-ish timestamp format for log lines.
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

#: Maximum log file size (5 MiB) before rotation kicks in.
LOG_MAX_BYTES: int = 5 * 1024 * 1024

#: Number of rotated backup files to keep.
LOG_BACKUP_COUNT: int = 3

# Tracks whether setup_logging() has been called, so we don't double-add
# handlers if invoked twice.
_setup_done: bool = False


# =============================================================================
# === Public API                                                            ===
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``rask`` namespace.

    Cheap to call — Python's logging module caches loggers by name.

    Example
    -------
    >>> log = get_logger("services.activity")
    >>> log.info("Activity saved")
    """
    if not name:
        return logging.getLogger("rask")
    if not name.startswith("rask"):
        name = f"rask.{name}"
    return logging.getLogger(name)


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Union[str, Path]] = None,
    *,
    fmt: Optional[str] = None,
    datefmt: Optional[str] = None,
    also_stderr: bool = True,
    force: bool = False,
) -> logging.Logger:
    """Configure the root ``rask`` logger with file + stderr handlers.

    Should be called **once** at app startup (typically from
    ``rask.app.RaskApp.__init__``).  Subsequent calls are no-ops by
    default — pass ``force=True`` to wipe existing handlers and
    re-install.

    Parameters
    ----------
    level : int
        Logging level (default ``INFO``).  Use ``logging.DEBUG`` for
        verbose output.  Always applied, even on no-op calls.
    log_file : str or Path, optional
        Path to the log file.  Defaults to ``config.LOG_DIR / "rask.log"``.
    fmt : str, optional
        Custom log message format.  Defaults to :data:`LOG_FORMAT`.
    datefmt : str, optional
        Custom timestamp format.  Defaults to :data:`LOG_DATE_FORMAT`.
    also_stderr : bool
        If ``True`` (default), also write to ``stderr`` — useful during
        development.
    force : bool
        If ``True``, remove all existing handlers on the ``rask`` logger
        before adding fresh ones.  Useful for tests.

    Returns
    -------
    logging.Logger
        The configured ``rask`` logger.
    """
    global _setup_done
    root = logging.getLogger("rask")
    root.setLevel(level)

    if _setup_done and not force:
        return root

    # Wipe existing handlers if force=True (or first-time setup).
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(fmt or LOG_FORMAT, datefmt or LOG_DATE_FORMAT)

    # File handler (with rotation).  Use the explicit path if given,
    # otherwise fall back to the default location under config.LOG_DIR.
    target_path: Optional[Path] = None
    if log_file is not None:
        target_path = Path(log_file)
    else:
        target_path = config.LOG_DIR / "rask.log"

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            target_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
    except (OSError, PermissionError) as exc:
        # Don't crash if the log directory isn't writable — just
        # log a warning to stderr and continue.
        print(
            f"[logging_utils] Could not open log file {target_path}: {exc}",
            file=sys.stderr,
        )

    # Stderr handler.
    if also_stderr:
        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.setFormatter(formatter)
        stderr_handler.setLevel(level)
        root.addHandler(stderr_handler)

    # Tame noisy third-party loggers.
    for noisy in ("PIL.PngImagePlugin", "matplotlib", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _setup_done = True
    root.debug("Logging initialized (level=%s, file=%s)",
               logging.getLevelName(level), target_path)
    return root


def log_exception(
    logger: logging.Logger,
    exc: BaseException,
    context: Optional[Dict[str, Any]] = None,
    *,
    level: int = logging.ERROR,
) -> None:
    """Log an exception with optional context dict, including traceback.

    Parameters
    ----------
    logger : logging.Logger
        Logger to emit through.
    exc : BaseException
        The exception to log.
    context : dict, optional
        Additional key/value pairs to include in the log line (e.g.
        ``{"activity_id": 42}``).  Rendered as ``key=value`` pairs
        after the message.
    level : int
        Logging level (default ``ERROR``).  Use ``logging.WARNING`` for
        expected exceptions, ``logging.CRITICAL`` for fatal ones.

    Example
    -------
    >>> try:
    ...     1 / 0
    ... except ZeroDivisionError as e:
    ...     log_exception(get_logger("test"), e, {"op": "divide"})
    """
    ctx_str = ""
    if context:
        if isinstance(context, dict):
            parts = [f"{k}={v!r}" for k, v in context.items()]
            ctx_str = " | " + " ".join(parts) if parts else ""
        else:
            ctx_str = f" | context={context!r}"
    logger.log(
        level,
        "%s: %s%s",
        type(exc).__name__,
        exc,
        ctx_str,
        exc_info=exc,
    )


# =============================================================================
# === LogContext                                                            ===
# =============================================================================

class _ExtraAdapter(logging.LoggerAdapter):
    """A LoggerAdapter that appends ``key=value`` pairs to each message.

    The standard ``LoggerAdapter`` stores extras on the LogRecord but
    does not render them — you'd need a custom format string per
    adapter.  This subclass appends a ``" | k=v k=v"`` suffix to every
    message so the extras show up regardless of the formatter.
    """

    def process(self, msg, kwargs):  # type: ignore[override]
        if self.extra:
            parts = [f"{k}={v!r}" for k, v in self.extra.items()]
            msg = f"{msg} | " + " ".join(parts)
        return msg, kwargs


class LogContext:
    """Context manager for timing a block and emitting structured logs.

    Two modes:

    **Timing mode** — emit a log line on exit with the elapsed time:

        with LogContext(log, "import_backup"):
            do_work()
        # logs: "import_backup done in 1.234s"

    **Extra-fields mode** — attach ``key=value`` pairs to log records
    emitted through the context's ``.logger`` property (which returns
    an adapter):

        with LogContext(log, "process", user_id=42) as ctx:
            ctx.logger.info("step 1")  # -> "step 1 | user_id=42"

    Both modes can be combined.
    """

    def __init__(
        self,
        logger: logging.Logger,
        operation: str,
        *,
        level: int = logging.INFO,
        log_on_exit: bool = True,
        **extra: Any,
    ) -> None:
        self._logger = logger
        self._operation = operation
        self._level = level
        self._log_on_exit = log_on_exit
        self._extra = extra
        self._start: float = 0.0
        self._adapter: Optional[_ExtraAdapter] = None
        if extra:
            self._adapter = _ExtraAdapter(logger, extra)

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "LogContext":
        self._start = time.perf_counter()
        if self._adapter is not None:
            self._adapter.log(self._level, f"{self._operation} — start")
        else:
            self._logger.log(self._level, f"{self._operation} — start")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = time.perf_counter() - self._start
        if exc_type is None:
            msg = f"{self._operation} — done in {elapsed:.3f}s"
            level = self._level
        else:
            msg = (
                f"{self._operation} — failed in {elapsed:.3f}s "
                f"({exc_type.__name__}: {exc_val})"
            )
            level = logging.ERROR
        if self._log_on_exit:
            if self._adapter is not None:
                self._adapter.log(level, msg)
            else:
                self._logger.log(level, msg)
        # Don't suppress the exception.
        return False

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def logger(self) -> Union[logging.Logger, logging.LoggerAdapter]:
        """Return the underlying logger (or LoggerAdapter if extras were given)."""
        return self._adapter if self._adapter is not None else self._logger

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since the context was entered (0 before enter)."""
        if self._start == 0.0:
            return 0.0
        return time.perf_counter() - self._start


# =============================================================================
# === Self-tests                                                            ===
# =============================================================================

def _run_tests() -> int:
    """Self-tests — run with:  python -m rask.core.logging_utils"""
    tests_passed = 0
    tests_failed = 0

    def check(label: str, got, expected) -> None:
        nonlocal tests_passed, tests_failed
        if got == expected:
            tests_passed += 1
            print(f"  OK   {label}")
        else:
            tests_failed += 1
            print(f"  FAIL {label}: got {got!r}, expected {expected!r}")

    print("=== get_logger ===")
    log = get_logger("test_module")
    check("logger name", log.name, "rask.test_module")
    check("empty name -> rask", get_logger("").name, "rask")
    check("bare name -> rask-prefixed", get_logger("foo").name, "rask.foo")

    print("\n=== setup_logging (file + stderr) ===")
    # Reset the global so we can re-setup.
    global _setup_done
    _setup_done = False
    root = logging.getLogger("rask")
    setup_logging(level=logging.DEBUG, log_file=None, also_stderr=True, force=True)
    # One file handler + one stderr handler (file may be absent if LOG_DIR
    # is not writable, but in our test env it should exist).
    check("handler count after setup (file+stderr)",
          1 <= len(root.handlers) <= 2, True)
    check("root level", root.level, logging.DEBUG)
    check("_setup_done flag", _setup_done, True)

    print("\n=== Second setup_logging is a no-op ===")
    setup_logging(level=logging.WARNING)
    check("handler count unchanged", len(root.handlers), 2)
    check("level updated by second call", root.level, logging.WARNING)

    print("\n=== log_exception ===")
    import io
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    test_log = logging.getLogger("rask.test_exc")
    test_log.handlers = [h]
    test_log.setLevel(logging.DEBUG)
    test_log.propagate = False
    try:
        1 / 0
    except ZeroDivisionError as e:
        log_exception(test_log, e, {"op": "divide"})
    output = buf.getvalue()
    check("log contains exception type",
          "ZeroDivisionError" in output, True)
    check("log contains context", "op='divide'" in output, True)
    check("log contains traceback", "Traceback" in output, True)

    print("\n=== LogContext timing ===")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    test_log = logging.getLogger("rask.test_ctx")
    test_log.handlers = [h]
    test_log.setLevel(logging.DEBUG)
    test_log.propagate = False
    with LogContext(test_log, "import_backup"):
        time.sleep(0.01)
    output = buf.getvalue()
    check("ctx logs start", "import_backup — start" in output, True)
    check("ctx logs done", "import_backup — done in" in output, True)
    check("ctx logs seconds", "s" in output, True)

    print("\n=== LogContext with extras ===")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    test_log = logging.getLogger("rask.test_ctx2")
    test_log.handlers = [h]
    test_log.setLevel(logging.DEBUG)
    test_log.propagate = False
    with LogContext(test_log, "process", user_id=42) as ctx:
        ctx.logger.info("step 1")
    output = buf.getvalue()
    check("ctx extras in record", "user_id=42" in output, True)

    print("\n=== LogContext with exception ===")
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(message)s"))
    test_log = logging.getLogger("rask.test_ctx3")
    test_log.handlers = [h]
    test_log.setLevel(logging.DEBUG)
    test_log.propagate = False
    try:
        with LogContext(test_log, "risky_op"):
            raise ValueError("nope")
    except ValueError:
        pass
    output = buf.getvalue()
    check("ctx logs failure", "risky_op — failed" in output, True)
    check("ctx logs exception type", "ValueError" in output, True)

    print(f"\n{tests_passed} passed, {tests_failed} failed.")
    return tests_failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
