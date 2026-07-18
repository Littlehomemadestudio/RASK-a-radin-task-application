"""
rask.utils.debug
================

Debugging and introspection helpers for Rask developers.

This module is safe to import in production — all functions are
no-ops unless explicitly enabled via env vars or the developer-mode
setting.  Use these to:

  • Dump the entire application state to a single dict for support tickets
  • Trace individual function calls with arguments, return value, and timing
  • Profile hot spots via :mod:`cProfile`
  • Inspect the live widget tree of a CustomTkinter window
  • Capture screenshots of individual widgets for visual regression tests
  • Watch memory usage growth over time

None of these helpers are wired into the main app flow — they are
opt-in tools for developers diagnosing issues.
"""
from __future__ import annotations

import cProfile
import functools
import gc
import io
import os
import pstats
import sys
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .. import config


# =============================================================================
# === State dump                                                              ===
# =============================================================================

def dump_state() -> dict:
    """Return a comprehensive snapshot of the application state.

    Includes: settings, kv store, db stats, environment info, timer state,
    service status.  Safe to JSON-serialize for inclusion in bug reports.
    """
    state: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": config.APP_NAME,
            "version": config.APP_VERSION,
            "build": config.APP_BUILD,
        },
        "python": {
            "version": sys.version,
            "platform": sys.platform,
            "executable": sys.executable,
        },
        "environment": {
            "DEBUG": config.DEBUG,
            "VERBOSE": config.VERBOSE,
            "PROFILE": config.PROFILE,
            "RASK_DEBUG": os.environ.get("RASK_DEBUG", ""),
            "RASK_VERBOSE": os.environ.get("RASK_VERBOSE", ""),
        },
        "paths": {
            "data_dir": str(config.DATA_DIR),
            "db_path": str(config.DB_PATH),
            "backup_dir": str(config.BACKUP_DIR),
            "export_dir": str(config.EXPORT_DIR),
            "log_dir": str(config.LOG_DIR),
            "cache_dir": str(config.CACHE_DIR),
        },
    }
    # DB stats (best effort)
    try:
        from .. import database
        state["database"] = database.stats()
        state["integrity_check"] = database.integrity_check()
    except Exception as e:
        state["database"] = {"error": str(e)}
    # Settings + KV
    try:
        from .. import database
        state["settings"] = database.setting_list()
        kv_keys = database.kv_keys()
        state["kv"] = {k: database.kv_get(k) for k in kv_keys}
    except Exception as e:
        state["settings"] = {"error": str(e)}
        state["kv"] = {"error": str(e)}
    # Timer state
    try:
        from ..services import timer_service
        state["timer"] = timer_service.state()
    except Exception as e:
        state["timer"] = {"error": str(e)}
    # Services status
    try:
        from ..services import settings_service
        state["language"] = settings_service.language()
        state["theme"] = settings_service.theme()
        state["lock_mode"] = settings_service.lock_mode()
    except Exception as e:
        state["services"] = {"error": str(e)}
    # Memory snapshot
    state["memory"] = {
        "rss_mb": memory_usage(),
        "object_count": len(gc.get_objects()),
    }
    return state


def dump_object(obj: Any, depth: int = 3, max_len: int = 200) -> dict:
    """Introspect an object and return a tree of its attributes.

    Goes `depth` levels deep.  Truncates string values to `max_len`.
    Useful for debugging unexpected state.
    """
    seen: set[int] = set()

    def _walk(o: Any, d: int) -> Any:
        if d <= 0:
            return repr(o)[:max_len]
        if isinstance(o, (str, int, float, bool, type(None))):
            return o
        if isinstance(o, (list, tuple, set, frozenset)):
            if len(o) > 50:
                return f"{type(o).__name__}[{len(o)} items]"
            return [_walk(x, d - 1) for x in list(o)[:50]]
        if isinstance(o, dict):
            return {str(k)[:max_len]: _walk(v, d - 1)
                    for k, v in list(o.items())[:50]}
        oid = id(o)
        if oid in seen:
            return f"<cycle {type(o).__name__}@0x{oid:x}>"
        seen.add(oid)
        try:
            attrs = {}
            for name in dir(o):
                if name.startswith("_"):
                    continue
                try:
                    val = getattr(o, name)
                    if callable(val):
                        continue
                    attrs[name] = _walk(val, d - 1)
                except Exception as e:
                    attrs[name] = f"<error: {e}>"
            return {"__type__": type(o).__name__, **attrs}
        except Exception as e:
            return f"<error: {e}>"

    return _walk(obj, depth)


# =============================================================================
# === Function tracing                                                         ===
# =============================================================================

def trace_function(func: Callable) -> Callable:
    """Decorator that logs each call, args, return value, and timing.

    Only active when config.DEBUG is True.  No-op otherwise.
    """
    if not config.DEBUG:
        return func

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from .logging_utils import get_logger  # type: ignore
        logger = get_logger(func.__module__)
        arg_repr = ", ".join([repr(a)[:100] for a in args[:5]])
        if len(args) > 5:
            arg_repr += f", ... ({len(args)} args total)"
        kw_repr = ", ".join(f"{k}={v!r}"[:100] for k, v in list(kwargs.items())[:5])
        full_args = arg_repr + (", " + kw_repr if kw_repr else "")
        logger.debug(f"→ {func.__qualname__}({full_args})")
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(f"← {func.__qualname__} [{elapsed_ms:.1f}ms] = {result!r}"[:200])
            return result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(f"✗ {func.__qualname__} [{elapsed_ms:.1f}ms] raised {type(e).__name__}: {e}")
            raise

    return wrapper


def trace_module(module_name: str) -> None:
    """Trace ALL functions in a module.  Use sparingly!"""
    import importlib
    mod = importlib.import_module(module_name)
    for name in dir(mod):
        obj = getattr(mod, name)
        if callable(obj) and getattr(obj, "__module__", "") == module_name:
            if not name.startswith("_"):
                setattr(mod, name, trace_function(obj))


# =============================================================================
# === Memory & profiling                                                       ===
# =============================================================================

def memory_usage() -> float:
    """Return current process RSS in MB.  Cross-platform best-effort."""
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / (1024 * 1024)
    except Exception:
        pass
    # Fallback: read /proc/self/status on Linux
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) / 1024  # KB → MB
    except Exception:
        pass
    # Windows fallback via tasklist
    if sys.platform == "win32":
        try:
            import subprocess
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {os.getpid()}",
                 "/FO", "CSV", "/NH"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore")
            # "Name","PID","Session Name","Session#","Mem Usage"
            parts = out.strip().strip('"').split('","')
            if len(parts) >= 5:
                mem_str = parts[4].rstrip(" K").replace(",", "").replace('"', "")
                return int(mem_str) / 1024  # KB → MB
        except Exception:
            pass
    return 0.0


@contextmanager
def memory_snapshot(label: str = ""):
    """Context manager that prints memory delta after the block exits."""
    gc.collect()
    before = memory_usage()
    yield
    gc.collect()
    after = memory_usage()
    delta = after - before
    sign = "+" if delta >= 0 else ""
    print(f"[memory] {label or 'block'}: {sign}{delta:.2f} MB "
          f"(now {after:.2f} MB)")


def start_tracemalloc() -> None:
    """Start tracemalloc for detailed memory tracking."""
    if not tracemalloc.is_tracing():
        tracemalloc.start()


def stop_tracemalloc(top: int = 20) -> list[str]:
    """Stop tracemalloc and return top-N memory offenders."""
    if not tracemalloc.is_tracing():
        return ["tracemalloc not running"]
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.statistics("lineno")
    out = []
    for stat in stats[:top]:
        out.append(str(stat))
    tracemalloc.stop()
    return out


# =============================================================================
# === cProfile helpers                                                          ===
# =============================================================================

_PROFILE: Optional[cProfile.Profile] = None


def start_profiler() -> cProfile.Profile:
    """Start a global cProfile profiler.  Returns the Profile instance."""
    global _PROFILE
    _PROFILE = cProfile.Profile()
    _PROFILE.enable()
    return _PROFILE


def stop_profiler(top: int = 20, sort_by: str = "cumulative") -> str:
    """Stop the global profiler and return a formatted report string."""
    global _PROFILE
    if _PROFILE is None:
        return "Profiler not started"
    _PROFILE.disable()
    buf = io.StringIO()
    stats = pstats.Stats(_PROFILE, stream=buf)
    stats.sort_stats(sort_by)
    stats.print_stats(top)
    _PROFILE = None
    return buf.getvalue()


@contextmanager
def profile_block(label: str = "", top: int = 20):
    """Context manager that profiles the enclosed block."""
    pr = cProfile.Profile()
    pr.enable()
    yield
    pr.disable()
    buf = io.StringIO()
    stats = pstats.Stats(pr, stream=buf)
    stats.sort_stats("cumulative")
    stats.print_stats(top)
    print(f"\n=== Profile: {label or 'block'} ===")
    print(buf.getvalue())


# =============================================================================
# === Logging control                                                          ===
# =============================================================================

def enable_logging_for(module_name: str, level: str = "DEBUG") -> None:
    """Set the logging level of a specific module."""
    import logging
    logger = logging.getLogger(module_name)
    logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))


def enable_debug_logging() -> None:
    """Enable DEBUG logging for all rask.* modules."""
    import logging
    logging.getLogger("rask").setLevel(logging.DEBUG)


def disable_logging() -> None:
    """Set all rask.* loggers to WARNING."""
    import logging
    logging.getLogger("rask").setLevel(logging.WARNING)


# =============================================================================
# === Widget inspection                                                         ===
# =============================================================================

def inspect_widget_tree(root, indent: int = 0, max_depth: int = 10) -> str:
    """Return a string showing the widget tree rooted at `root`.

    Each line: class name + winfo_class + size + child count.
    """
    if indent > max_depth:
        return ""
    lines: list[str] = []
    try:
        cls = type(root).__name__
        try:
            winfo = root.winfo_class()
        except Exception:
            winfo = "?"
        try:
            w = root.winfo_width()
            h = root.winfo_height()
            size = f"{w}x{h}"
        except Exception:
            size = "?x?"
        children = []
        try:
            children = root.winfo_children()
        except Exception:
            pass
        prefix = "  " * indent
        lines.append(f"{prefix}├─ {cls} [{winfo}] {size} ({len(children)} children)")
        for child in children:
            sub = inspect_widget_tree(child, indent + 1, max_depth)
            if sub:
                lines.append(sub)
    except Exception as e:
        lines.append(f"{indent * '  '}├─ <error: {e}>")
    return "\n".join(lines)


def widget_count(root) -> int:
    """Count total widgets in the tree rooted at `root`."""
    try:
        n = 1
        for child in root.winfo_children():
            n += widget_count(child)
        return n
    except Exception:
        return 0


# =============================================================================
# === Screenshot                                                               ===
# =============================================================================

def take_screenshot(widget, path: str, format_: str = "png") -> bool:
    """Screenshot a Tk widget to an image file.

    Uses PIL's ImageGrab which works on Windows and macOS.  On Linux
    requires `xwd` or `python-xlib`.
    """
    try:
        from PIL import ImageGrab  # type: ignore
        widget.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty()
        w = widget.winfo_width()
        h = widget.winfo_height()
        if w <= 1 or h <= 1:
            return False
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        img.save(path, format=format_.upper())
        return True
    except Exception as e:
        print(f"screenshot failed: {e}")
        return False


# =============================================================================
# === Performance counters                                                     ===
# =============================================================================

class PerfCounter:
    """Simple counter + timer for ad-hoc performance tracking.

    Usage:
        counter = PerfCounter("db_queries")
        with counter.measure():
            db.execute(...)
        print(counter.summary())
    """

    def __init__(self, name: str):
        self.name = name
        self.count = 0
        self.total_sec = 0.0
        self.min_sec = float("inf")
        self.max_sec = 0.0

    @contextmanager
    def measure(self):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.count += 1
            self.total_sec += elapsed
            self.min_sec = min(self.min_sec, elapsed)
            self.max_sec = max(self.max_sec, elapsed)

    def avg_sec(self) -> float:
        return self.total_sec / self.count if self.count > 0 else 0

    def summary(self) -> str:
        if self.count == 0:
            return f"[{self.name}] no samples"
        return (f"[{self.name}] count={self.count} "
                f"avg={self.avg_sec() * 1000:.2f}ms "
                f"min={self.min_sec * 1000:.2f}ms "
                f"max={self.max_sec * 1000:.2f}ms "
                f"total={self.total_sec:.2f}s")


# Global registry of perf counters
_PERF_COUNTERS: dict[str, PerfCounter] = {}


def perf_counter(name: str) -> PerfCounter:
    """Get (or create) a named PerfCounter."""
    if name not in _PERF_COUNTERS:
        _PERF_COUNTERS[name] = PerfCounter(name)
    return _PERF_COUNTERS[name]


def all_perf_summaries() -> list[str]:
    """Return summary strings for all named PerfCounters."""
    return [c.summary() for c in _PERF_COUNTERS.values()]


def reset_perf_counters() -> None:
    """Reset all perf counters (e.g. between test runs)."""
    _PERF_COUNTERS.clear()


# =============================================================================
# === Slow-call detector                                                        ===
# =============================================================================

class SlowCallDetector:
    """Detect function calls that take longer than a threshold.

    Usage:
        detector = SlowCallDetector(threshold_ms=100)
        detector.install()  # wraps all rask.* callables
        # ... run app ...
        detector.report()  # prints slow calls
        detector.uninstall()
    """

    def __init__(self, threshold_ms: float = 100):
        self.threshold_sec = threshold_ms / 1000
        self.slow_calls: list[dict] = []
        self._originals: dict[str, Callable] = {}
        self._installed = False

    def install(self, module_prefix: str = "rask") -> None:
        """Wrap all callable attributes in rask.* modules."""
        if self._installed:
            return
        import importlib
        import pkgutil
        try:
            import rask  # type: ignore
        except Exception:
            return
        for finder, name, ispkg in pkgutil.walk_packages(rask.__path__, prefix="rask."):
            try:
                mod = importlib.import_module(name)
            except Exception:
                continue
            for attr_name in dir(mod):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(mod, attr_name)
                except Exception:
                    continue
                if not callable(attr) or isinstance(attr, type):
                    continue
                key = f"{name}.{attr_name}"
                if key in self._originals:
                    continue
                self._originals[key] = attr
                detector = self
                def make_wrapper(k, f):
                    @functools.wraps(f)
                    def wrapper(*args, **kwargs):
                        start = time.perf_counter()
                        try:
                            return f(*args, **kwargs)
                        finally:
                            elapsed = time.perf_counter() - start
                            if elapsed >= detector.threshold_sec:
                                detector.slow_calls.append({
                                    "function": k,
                                    "elapsed_ms": elapsed * 1000,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                    return wrapper
                try:
                    setattr(mod, attr_name, make_wrapper(key, attr))
                except Exception:
                    pass
        self._installed = True

    def uninstall(self) -> None:
        """Restore original unwrapped functions."""
        if not self._installed:
            return
        import importlib
        for key, original in self._originals.items():
            module_path, _, attr_name = key.rpartition(".")
            try:
                mod = importlib.import_module(module_path)
                setattr(mod, attr_name, original)
            except Exception:
                pass
        self._originals.clear()
        self._installed = False

    def report(self, top: int = 50) -> str:
        """Return a formatted report of slow calls."""
        if not self.slow_calls:
            return "No slow calls detected."
        # Aggregate by function
        agg: dict[str, list[float]] = {}
        for call in self.slow_calls:
            agg.setdefault(call["function"], []).append(call["elapsed_ms"])
        rows = []
        for func, times in agg.items():
            rows.append({
                "function": func,
                "count": len(times),
                "total_ms": sum(times),
                "avg_ms": sum(times) / len(times),
                "max_ms": max(times),
            })
        rows.sort(key=lambda r: r["total_ms"], reverse=True)
        lines = [f"Slow call report ({len(self.slow_calls)} calls):"]
        for r in rows[:top]:
            lines.append(f"  {r['function']}: count={r['count']} "
                         f"total={r['total_ms']:.1f}ms "
                         f"avg={r['avg_ms']:.1f}ms "
                         f"max={r['max_ms']:.1f}ms")
        return "\n".join(lines)


# =============================================================================
# === Public API                                                               ===
# =============================================================================

__all__ = [
    "dump_state", "dump_object",
    "trace_function", "trace_module",
    "memory_usage", "memory_snapshot",
    "start_tracemalloc", "stop_tracemalloc",
    "start_profiler", "stop_profiler", "profile_block",
    "enable_logging_for", "enable_debug_logging", "disable_logging",
    "inspect_widget_tree", "widget_count",
    "take_screenshot",
    "PerfCounter", "perf_counter", "all_perf_summaries", "reset_perf_counters",
    "SlowCallDetector",
]
