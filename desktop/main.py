#!/usr/bin/env python3
"""main.py — Entry point for the Rask desktop application.

Handles:

* Python version check (3.9+ required)
* Optional-dependency probes with friendly install hints
* Logging configuration (rotating file + stderr)
* Special startup modes:
    ``--reset``       — wipe all user data (after confirmation)
    ``--vacuum``      — vacuum the DB and exit
    ``--export-all``  — export all data as JSON and exit
    ``--cli ARGS...`` — run a CLI sub-command instead of the GUI
* Construction of :class:`rask.ui.RaskApp` and entry into the
  CustomTkinter main loop
* Last-resort exception handler that prints a readable error and
  writes the traceback to the log file

Usage
-----
::

    python main.py                     # launch the GUI
    python main.py --lang en           # force English UI
    python main.py --theme light       # force light theme
    python main.py --debug             # verbose logging
    python main.py --profile           # enable profiling
    python main.py --vacuum            # vacuum DB and exit
    python main.py --reset             # wipe data and exit
    python main.py --export-all out.json
    python main.py --cli stats         # run `rask stats`
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import Optional, Sequence

__version__ = "2.0.0"


# =============================================================================
# === Python version check                                                   ===
# =============================================================================

def _check_python_version() -> bool:
    """Verify Python 3.9+.  Returns True if compatible."""
    if sys.version_info < (3, 9):
        sys.stderr.write(
            f"ERROR: Rask requires Python 3.9 or later.\n"
            f"You are running Python {sys.version.split()[0]}.\n"
            f"Please upgrade from https://python.org\n"
        )
        return False
    return True


# =============================================================================
# === Dependency probe                                                       ===
# =============================================================================

def _check_dependencies() -> bool:
    """Warn the user about missing optional dependencies.

    Returns True if all **required** dependencies are present.
    Optional deps (reportlab, speech_recognition, pyaudio) emit a
    warning but don't prevent startup.
    """
    try:
        from rask.check_env import check_environment, install_hint
    except ImportError:
        # check_env itself failed to import — that's a bigger problem
        sys.stderr.write(
            "ERROR: rask.check_env module is missing or broken.\n"
            "Your rask installation may be incomplete.\n")
        return False
    report = check_environment()
    missing_required = []
    if not report["customtkinter"]["available"]:
        missing_required.append("customtkinter")
    if not report["PIL"]["available"]:
        missing_required.append("Pillow")
    if not report["cryptography"]["available"]:
        missing_required.append("cryptography")
    if missing_required:
        sys.stderr.write(
            "\nERROR: Missing required dependencies:\n")
        for dep in missing_required:
            hint = install_hint(dep) or f"pip install {dep}"
            sys.stderr.write(f"  - {dep}: {hint}\n")
        sys.stderr.write(
            "\nInstall them and try again:\n"
            f"  pip install -r requirements.txt\n\n")
        return False
    # Warn about missing optional deps
    missing_optional = []
    if not report["reportlab"]["available"]:
        missing_optional.append(("reportlab", "PDF export"))
    if not report["speech_recognition"]["available"]:
        missing_optional.append(("speech_recognition", "voice input"))
    if not report["pyaudio"]["available"]:
        missing_optional.append(("pyaudio", "microphone access"))
    if missing_optional:
        sys.stderr.write("\nNote: Some optional features are unavailable:\n")
        for dep, feature in missing_optional:
            sys.stderr.write(f"  - {feature} requires '{dep}' "
                              f"({install_hint(dep)})\n")
        sys.stderr.write("\n")
    if not report["vazirmatn_font"]["available"]:
        sys.stderr.write(
            "Note: Vazirmatn font not found — Persian rendering will fall "
            "back to Tahoma/Arial.\n"
            "Download from https://github.com/rastikerdar/vazirmatn\n\n")
    return True


# =============================================================================
# === Special startup modes                                                  ===
# =============================================================================

def _run_vacuum() -> int:
    """Vacuum the SQLite database and exit."""
    from rask import database as db
    from rask.core.logging_utils import setup_logging
    setup_logging()
    try:
        db.open_db()
        db.vacuum()
        size = db.db_file_size()
        print(f"Database vacuumed. New size: {size:,} bytes "
              f"({_human_size(size)}).")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _run_reset() -> int:
    """Wipe all user data after interactive confirmation."""
    from rask import database as db
    from rask.core.logging_utils import setup_logging
    setup_logging()
    print("\nWARNING: this will permanently delete ALL your Rask data:")
    from rask import config
    print(f"  - Database: {config.DB_PATH}")
    print(f"  - Backups : {config.BACKUP_DIR}")
    print(f"  - Exports : {config.EXPORT_DIR}")
    print(f"  - Logs    : {config.LOG_DIR}")
    print()
    if not _confirm("Type 'yes' to confirm and wipe everything: "):
        print("Aborted.")
        return 0
    try:
        db.open_db()
        conn = db.get_conn()
        for t in ("activity_tags", "tags", "activities", "sessions",
                   "recurring", "reminders", "badges", "templates",
                   "streaks", "goals", "categories", "settings", "kv"):
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:  # noqa: BLE001
                pass
        conn.commit()
        db.open_db()  # re-seed defaults
        print("All data wiped. Default categories and settings re-seeded.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _run_export_all(out_path: str) -> int:
    """Export the entire database as a JSON file and exit."""
    from rask import database as db
    from rask.core.logging_utils import setup_logging
    setup_logging()
    try:
        db.open_db()
        from rask.export.json_export import JsonExporter
        exp = JsonExporter(out_path)
        exp.export_all()
        ok = exp.save()
        if ok:
            print(f"Exported all data to {out_path}")
            return 0
        print(f"ERROR: export failed", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


def _run_cli(cli_args: Sequence[str]) -> int:
    """Dispatch to the CLI sub-command instead of the GUI."""
    from rask.cli import run_command
    return run_command(list(cli_args))


def _confirm(prompt: str) -> bool:
    """Read a yes/no confirmation from stdin.  Defaults to No."""
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes", "ye", "yep", "yeah")


def _human_size(num_bytes: int) -> str:
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# =============================================================================
# === GUI launch                                                             ===
# =============================================================================

def _launch_gui(args: argparse.Namespace) -> int:
    """Construct :class:`RaskApp` and enter its main loop."""
    # Apply overrides to settings BEFORE creating the app, so the
    # splash screen honours them from the very first frame.
    from rask import database as db
    from rask.core.logging_utils import setup_logging
    setup_logging(level=10 if args.debug else 20, also_stderr=args.debug)
    db.open_db()
    if args.lang or args.theme:
        from rask.services import settings_service
        if args.lang:
            settings_service.set_language(args.lang)
        if args.theme:
            settings_service.set_theme(args.theme)
    # Optional profiling
    if args.profile:
        try:
            import cProfile, pstats  # type: ignore[import-not-found]
            import io
            profiler = cProfile.Profile()
            profiler.enable()
        except ImportError:
            profiler = None
    else:
        profiler = None
    try:
        from rask.ui import RaskApp
    except ImportError as exc:
        sys.stderr.write(
            f"ERROR: could not import RaskApp — CustomTkinter is probably "
            f"not installed.\n  {exc}\n")
        return 1
    try:
        app = RaskApp()
        app.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 — top-level handler
        sys.stderr.write(f"\nERROR: {exc}\n")
        traceback.print_exc()
        # Try to log it too
        try:
            from rask.core.logging_utils import get_logger
            get_logger("main").exception("Unhandled error: %s", exc)
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        if profiler is not None:
            profiler.disable()
            buf = io.StringIO()
            ps = pstats.Stats(profiler, stream=buf).sort_stats("cumulative")
            ps.print_stats(30)
            print(buf.getvalue())
    return 0


# =============================================================================
# === Argument parser                                                         ===
# =============================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for ``main.py``."""
    parser = argparse.ArgumentParser(
        prog="rask",
        description="Rask — beautiful offline time-tracking desktop app.",
        epilog="Run with --cli <command> for non-GUI operations "
                "(see `rask --cli help` for the command list).",
    )
    parser.add_argument("--lang",
                         choices=("fa", "en", "ar", "tr", "ru", "de",
                                   "fr", "es", "zh", "ja"),
                         help="Override the UI language for this session")
    parser.add_argument("--theme",
                         choices=("dark", "light", "system"),
                         help="Override the colour theme for this session")
    parser.add_argument("--debug", action="store_true",
                         help="Enable verbose debug logging")
    parser.add_argument("--profile", action="store_true",
                         help="Profile the app's main loop and print stats")
    parser.add_argument("--reset", action="store_true",
                         help="Wipe ALL user data (interactive confirm)")
    parser.add_argument("--vacuum", action="store_true",
                         help="Vacuum the SQLite database and exit")
    parser.add_argument("--export-all", metavar="PATH",
                         help="Export all data as JSON to PATH and exit")
    parser.add_argument("--cli", nargs=argparse.REMAINDER,
                         metavar="ARGS...",
                         help="Run a CLI sub-command instead of the GUI "
                              "(e.g. --cli stats)")
    parser.add_argument("--version", action="version",
                         version=f"Rask v{__version__}")
    return parser


# =============================================================================
# === Main entry point                                                        ===
# =============================================================================

def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point.  Returns the process exit code."""
    if not _check_python_version():
        return 1
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    # CLI dispatch (no GUI)
    if args.cli is not None:
        return _run_cli(args.cli)
    if args.vacuum:
        return _run_vacuum()
    if args.reset:
        return _run_reset()
    if args.export_all:
        return _run_export_all(args.export_all)
    # GUI launch — probe deps first
    if not _check_dependencies():
        return 1
    return _launch_gui(args)


if __name__ == "__main__":
    sys.exit(main())
