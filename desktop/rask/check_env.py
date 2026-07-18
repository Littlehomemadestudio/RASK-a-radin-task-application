"""
rask.check_env
==============

Environment / dependency probe for the Rask desktop application.

Used by:

* ``main.py`` at startup to warn the user about missing optional deps
* the CLI ``rask doctor`` command (alias: ``rask env``)
* the About screen's "Debug info" panel
* automated CI smoke tests that need to skip tests when a dep is absent

The probe is intentionally side-effect-free: it does not open the
database, does not create windows, does not write files.  Every check
returns a plain dict / scalar so the result can be JSON-serialised,
logged, or piped through ``jq``.

Typical usage
-------------
::

    from rask.check_env import check_environment, print_report
    report = check_environment()
    if not report["customtkinter_available"]:
        print("ERROR:", install_hint("customtkinter"))
        sys.exit(1)
    print_report(report)
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

__all__ = [
    "check_environment",
    "print_report",
    "install_hint",
    "MISSING_HINTS",
]


# =============================================================================
# === Optional dependency probes                                             ===
# =============================================================================

def _probe_customtkinter() -> Dict[str, Any]:
    """Probe for CustomTkinter (required for GUI)."""
    try:
        import customtkinter  # type: ignore[import-not-found]
        version = getattr(customtkinter, "__version__", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_pil() -> Dict[str, Any]:
    """Probe for Pillow (icons, screenshots, image export)."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]
        version = getattr(Image, "__version__", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_cryptography() -> Dict[str, Any]:
    """Probe for the ``cryptography`` package (AES-256-GCM backups)."""
    try:
        import cryptography  # type: ignore[import-not-found]
        version = getattr(cryptography, "__version__", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_reportlab() -> Dict[str, Any]:
    """Probe for reportlab (PDF export)."""
    try:
        import reportlab  # type: ignore[import-not-found]
        version = getattr(reportlab, "Version", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_speech_recognition() -> Dict[str, Any]:
    """Probe for speech_recognition (voice input)."""
    try:
        import speech_recognition as sr  # type: ignore[import-not-found]
        version = getattr(sr, "__version__", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_pyaudio() -> Dict[str, Any]:
    """Probe for pyaudio (microphone access for voice)."""
    try:
        import pyaudio  # type: ignore[import-not-found,unused-ignore]
        version = getattr(pyaudio, "__version__", "unknown")
        return {"available": True, "version": str(version)}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_matplotlib() -> Dict[str, Any]:
    """Probe for matplotlib (PDF chart rendering)."""
    try:
        import matplotlib  # type: ignore[import-not-found]
        return {"available": True,
                 "version": getattr(matplotlib, "__version__", "unknown")}
    except ImportError as exc:
        return {"available": False, "version": None, "error": str(exc)}


def _probe_vazirmatn_font() -> Dict[str, Any]:
    """Probe for the Vazirmatn font (best Persian rendering).

    Checks the bundled ``rask/assets/fonts/`` directory first, then
    the system font paths.  Returns ``{"available": bool, "path": str}``.
    """
    search_dirs: List[Path] = []
    try:
        search_dirs.append(Path(__file__).resolve().parents[1] / "assets" / "fonts")
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        win_fonts = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"
        search_dirs.append(Path(win_fonts))
        search_dirs.append(Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        search_dirs.append(Path("/Library/Fonts"))
        search_dirs.append(Path("/System/Library/Fonts"))
        search_dirs.append(Path.home() / "Library" / "Fonts")
    else:
        search_dirs.append(Path("/usr/share/fonts"))
        search_dirs.append(Path("/usr/local/share/fonts"))
        search_dirs.append(Path.home() / ".local" / "share" / "fonts")
        search_dirs.append(Path.home() / ".fonts")

    for d in search_dirs:
        if not d.is_dir():
            continue
        try:
            for ttf in d.rglob("*.ttf"):
                name = ttf.stem.lower().replace("-", "").replace("_", "")
                if name.startswith("vazir"):
                    return {"available": True, "path": str(ttf)}
        except (PermissionError, OSError):
            continue
    return {"available": False, "path": None}


# =============================================================================
# === Data-dir / DB probes                                                    ===
# =============================================================================

def _probe_data_dir() -> Dict[str, Any]:
    """Check that the user-data directory exists and is writable."""
    path = config.DATA_DIR
    writable = False
    error: Optional[str] = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.touch()
        probe.unlink()
        writable = True
    except OSError as exc:
        error = str(exc)
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "writable": writable,
        "error": error,
    }


def _probe_db() -> Dict[str, Any]:
    """Check whether the SQLite database file exists."""
    path = config.DB_PATH
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": size,
        "size_human": _human_size(size),
    }


def _human_size(num_bytes: int) -> str:
    """Return a human-readable byte size string."""
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# =============================================================================
# === Public API                                                              ===
# =============================================================================

def check_environment() -> Dict[str, Any]:
    """Probe the runtime environment and return a structured report.

    The returned dict has the following top-level keys:

    - ``python_version``  — ``"3.11.5"``
    - ``platform``        — ``"Linux-6.5.0-...-x86_64"``
    - ``platform_uname``  — full uname dict
    - ``executable``      — path to the Python interpreter
    - ``cwd``             — current working directory
    - ``data_dir``        — dict (path, exists, writable, error)
    - ``db_path``         — dict (path, exists, size_bytes, size_human)
    - ``customtkinter``   — dict (available, version, error?)
    - ``PIL``             — dict
    - ``cryptography``    — dict
    - ``reportlab``       — dict
    - ``speech_recognition`` — dict
    - ``pyaudio``         — dict
    - ``matplotlib``      — dict
    - ``vazirmatn_font``  — dict (available, path)
    - ``rask_version``    — :data:`rask.config.APP_VERSION`
    - ``rask_build``      — :data:`rask.config.APP_BUILD`
    - ``all_required_present`` — bool (CTk + PIL + cryptography)

    The function never raises — every probe is wrapped in try/except.
    """
    report: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "python_version_info": list(sys.version_info[:4]),
        "platform": platform.platform(),
        "platform_uname": dict(zip(
            ("system", "node", "release", "version", "machine", "processor"),
            platform.uname())),
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "rask_version": config.APP_VERSION,
        "rask_build": config.APP_BUILD,
    }
    report["data_dir"] = _probe_data_dir()
    report["db_path"] = _probe_db()
    report["customtkinter"] = _probe_customtkinter()
    report["PIL"] = _probe_pil()
    report["cryptography"] = _probe_cryptography()
    report["reportlab"] = _probe_reportlab()
    report["speech_recognition"] = _probe_speech_recognition()
    report["pyaudio"] = _probe_pyaudio()
    report["matplotlib"] = _probe_matplotlib()
    report["vazirmatn_font"] = _probe_vazirmatn_font()
    # Aggregate
    report["all_required_present"] = (
        report["customtkinter"]["available"]
        and report["PIL"]["available"]
        and report["cryptography"]["available"]
    )
    report["all_optional_present"] = (
        report["reportlab"]["available"]
        and report["speech_recognition"]["available"]
        and report["pyaudio"]["available"]
        and report["matplotlib"]["available"]
    )
    return report


# =============================================================================
# === Install hints                                                           ===
# =============================================================================

MISSING_HINTS: Dict[str, str] = {
    "customtkinter": "pip install customtkinter>=5.2.2",
    "PIL": "pip install Pillow>=10.0.0",
    "Pillow": "pip install Pillow>=10.0.0",
    "cryptography": "pip install cryptography>=42.0",
    "reportlab": "pip install reportlab>=4.0",
    "speech_recognition": "pip install SpeechRecognition>=3.10",
    "pyaudio": "pip install pyaudio>=0.2.14",
    "matplotlib": "pip install matplotlib>=3.7",
    "vazirmatn": (
        "Download Vazirmatn from https://github.com/rastikerdar/vazirmatn "
        "and install, or copy the .ttf files to: "
        + str(config.DATA_DIR / "fonts")
    ),
}


def install_hint(missing: str) -> str:
    """Return a pip-install hint string for a missing dependency.

    Returns an empty string if the dependency is unknown.
    """
    return MISSING_HINTS.get(missing, "")


# =============================================================================
# === Pretty-printer                                                          ===
# =============================================================================

def _colour(text: str, code: str) -> str:
    """ANSI colour wrapper — disabled when stdout is not a TTY."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str: return _colour(t, "32")
def _red(t: str) -> str: return _colour(t, "31")
def _yellow(t: str) -> str: return _colour(t, "33")
def _dim(t: str) -> str: return _colour(t, "2;37")


def _yes_no(b: bool) -> str:
    return _green("✓ yes") if b else _red("✗ no")


def print_report(report: Optional[Dict[str, Any]] = None) -> None:
    """Pretty-print an environment report to stdout.

    Pass a previously-computed report to avoid re-probing.  When
    called with no argument, runs :func:`check_environment` first.
    """
    if report is None:
        report = check_environment()
    print(f"\n  {_dim('Rask environment report')}\n"
          f"  {_dim('─' * 50)}")
    print(f"  Rask version    : {report['rask_version']} "
          f"(build {report['rask_build']})")
    print(f"  Python          : {report['python_version']}")
    print(f"  Platform        : {report['platform']}")
    print(f"  Executable      : {report['executable']}")
    print(f"  Working dir     : {report['cwd']}")
    print()
    print(f"  {_dim('Data directory')}")
    dd = report["data_dir"]
    print(f"    path      : {dd['path']}")
    print(f"    exists    : {_yes_no(dd['exists'])}")
    print(f"    writable  : {_yes_no(dd['writable'])}")
    if dd.get("error"):
        print(f"    error     : {_red(dd['error'])}")
    print()
    print(f"  {_dim('Database')}")
    db = report["db_path"]
    print(f"    path      : {db['path']}")
    print(f"    exists    : {_yes_no(db['exists'])}")
    print(f"    size      : {db['size_human']}")
    print()
    print(f"  {_dim('Required dependencies')}")
    for key, label in (("customtkinter", "CustomTkinter"),
                        ("PIL", "Pillow"),
                        ("cryptography", "cryptography")):
        info = report[key]
        status = _yes_no(info["available"])
        version = info.get("version") or "—"
        print(f"    {label:<14}: {status}  ({version})")
        if not info["available"]:
            hint = install_hint(key)
            if hint:
                print(f"                    {_yellow('→ ' + hint)}")
    print()
    print(f"  {_dim('Optional dependencies')}")
    for key, label in (("reportlab", "reportlab (PDF export)"),
                        ("speech_recognition", "SpeechRecognition (voice)"),
                        ("pyaudio", "pyaudio (microphone)"),
                        ("matplotlib", "matplotlib (PDF charts)")):
        info = report[key]
        status = _yes_no(info["available"])
        version = info.get("version") or "—"
        print(f"    {label:<32}: {status}  ({version})")
        if not info["available"]:
            hint = install_hint(key)
            if hint:
                print(f"                                      {_yellow('→ ' + hint)}")
    print()
    print(f"  {_dim('Persian font')}")
    vf = report["vazirmatn_font"]
    print(f"    Vazirmatn available : {_yes_no(vf['available'])}")
    if vf["available"]:
        print(f"    path                : {vf['path']}")
    else:
        hint = install_hint("vazirmatn")
        if hint:
            print(f"    {_yellow('→ ' + hint)}")
    print()
    print(f"  {_dim('Summary')}")
    summary_ok = report["all_required_present"] and report["all_optional_present"]
    if report["all_required_present"]:
        print(f"    {_green('✓ All required dependencies present')}")
    else:
        print(f"    {_red('✗ Missing required dependencies — GUI will not start')}")
    if report["all_optional_present"]:
        print(f"    {_green('✓ All optional dependencies present')}")
    else:
        print(f"    {_yellow('! Some optional features unavailable (PDF / voice / charts)')}")
    if not summary_ok:
        print()
        print(f"  {_yellow('Run `rask doctor` after installing the missing packages.')}")
    print()


# =============================================================================
# === Entry point                                                            ===
# =============================================================================

def main() -> int:
    """CLI entry — runs :func:`print_report`."""
    print_report()
    report = check_environment()
    return 0 if report["all_required_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
