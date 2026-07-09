"""
build_apk.py — Rask APK builder.

Run:
    python build_apk.py            # builds release AAB
    python build_apk.py --debug    # builds debug APK
    python build_apk.py --apk      # builds release APK (sideload)
    python build_apk.py --clean    # clean build cache then build

This script:
1. Verifies Python and pip are present.
2. Installs buildozer + cython + virtualenv into a local venv.
3. Generates any missing assets (icons, splash, fonts).
4. Invokes buildozer to produce an .aab (or .apk) under bin/.
5. Prints the path to the final artifact.

Buildozer auto-downloads the Android SDK + NDK on first run, so you do NOT need
Android Studio / Gradle / any JDK installed locally — only Python and a C compiler.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
BIN_DIR = VENV_DIR / ("Scripts" if platform.system() == "Windows" else "bin")
ARTIFACTS_DIR = ROOT / "bin"

PYTHON_REQUIREMENTS = [
    "buildozer==1.5.0",
    "Cython==0.29.36",
    "virtualenv==20.26.1",
    "pip>=23.0",
    "setuptools>=68.0",
    "wheel>=0.40",
    "sh==2.0.7",
]


def log(msg: str) -> None:
    print(f"\033[1;33m[rask-build]\033[0m {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    log(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(cwd or ROOT), env=env)


def ensure_system_deps() -> None:
    """Verify build prerequisites. Buildozer needs a C compiler + git."""
    missing = []
    for tool in ("git", "cc"):
        if shutil.which(tool) is None:
            missing.append(tool)
    if missing:
        log(f"Missing system tools: {', '.join(missing)}")
        if platform.system() == "Linux":
            log("Install with:  sudo apt-get install -y autoconf libtool pkg-config "
                "zlib1g-dev libncurses5-dev libtinfo5 cmake libffi-dev libssl-dev "
                "build-essential git ccache openjdk-17-jdk")
        sys.exit(1)
    if platform.system() == "Linux":
        for pkg in ("java", "javac"):
            if shutil.which(pkg) is None:
                log("JDK not found. Buildozer bundles a JDK by default, but if the "
                    "build fails, install OpenJDK 17.")
                break


def ensure_venv() -> Path:
    if not VENV_DIR.exists():
        log(f"Creating virtualenv at {VENV_DIR}")
        venv.create(VENV_DIR, with_pip=True, clear=True)
    pip = str(BIN_DIR / "pip")
    run([pip, "install", "--upgrade", *PYTHON_REQUIREMENTS])
    return BIN_DIR


def generate_assets() -> None:
    """Generate placeholder icons, splash and download a Persian font if missing."""
    icons_dir = ROOT / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Try to generate icon programmatically with Pillow (no network needed)
    icon_png = icons_dir / "ic_launcher.png"
    if not icon_png.exists():
        try:
            from PIL import Image, ImageDraw  # type: ignore
            log("Generating launcher icon (512x512)...")
            img = Image.new("RGBA", (512, 512), (14, 14, 16, 255))
            draw = ImageDraw.Draw(img)
            # Gold ring
            draw.ellipse((96, 96, 416, 416), outline=(212, 175, 55, 255), width=18)
            # Center R
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 240
                )
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), "R", font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((512 - tw) / 2 - bbox[0], (512 - th) / 2 - bbox[1]),
                      "R", fill=(212, 175, 55, 255), font=font)
            img.save(icon_png, "PNG")
        except ImportError:
            log("Pillow not available in host Python — skipping icon generation. "
                "Place a 512x512 PNG at assets/icons/ic_launcher.png manually.")

    # Splash
    presplash_dir = ROOT / "presplash"
    presplash_dir.mkdir(parents=True, exist_ok=True)
    splash = presplash_dir / "presplash.png"
    if not splash.exists():
        try:
            from PIL import Image, ImageDraw
            log("Generating presplash (1080x1920)...")
            img = Image.new("RGBA", (1080, 1920), (14, 14, 16, 255))
            draw = ImageDraw.Draw(img)
            draw.ellipse((390, 760, 690, 1060), outline=(212, 175, 55, 255), width=12)
            img.save(splash, "PNG")
        except ImportError:
            pass

    # Persian font
    font_dir = ROOT / "assets" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    font_path = font_dir / "vazirmatn.ttf"
    if not font_path.exists():
        # Look for system Vazirmatn first
        candidates = [
            "/usr/share/fonts/truetype/vazirmatn/Vazirmatn-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                shutil.copy(c, font_path)
                log(f"Using system font: {c}")
                break
        if not font_path.exists():
            log("No Persian font found on system. The build will still succeed; "
                "Persian glyphs will fall back to Kivy's default font.")


def build(buildozer: Path, mode: str, clean: bool) -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    if clean:
        log("Cleaning build directories...")
        for d in (".buildozer", "bin"):
            p = ROOT / d
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    if mode == "debug":
        cmd = [str(buildozer), "android", "debug"]
    elif mode == "apk":
        cmd = [str(buildozer), "android", "release"]
    else:  # release aab (default)
        cmd = [str(buildozer), "android", "release"]

    env = os.environ.copy()
    env["BUILDOZER_WARN_ON_ROOT"] = "1"
    env["ANDROID_HOME"] = env.get("ANDROID_HOME", str(ROOT / ".buildozer" / "android" / "platform" / "android-sdk"))

    rc = run(cmd, env=env)
    if rc != 0:
        log("BUILD FAILED. See logs above.")
        sys.exit(rc)

    # Locate artifacts
    artifacts = sorted(ARTIFACTS_DIR.glob("*.aab")) if mode == "release" else sorted(ARTIFACTS_DIR.glob("*.apk"))
    if not artifacts:
        log("No artifact produced. Check logs.")
        sys.exit(1)

    log("=== BUILD COMPLETE ===")
    for a in artifacts:
        size_mb = a.stat().st_size / 1024 / 1024
        print(f"  {a}  ({size_mb:.2f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Rask APK/AAB")
    parser.add_argument("--debug", action="store_true", help="Build debug APK")
    parser.add_argument("--apk", action="store_true", help="Build release APK (sideload)")
    parser.add_argument("--clean", action="store_true", help="Wipe .buildozer/ and bin/ before building")
    parser.add_argument("--deps-only", action="store_true", help="Only install buildozer; do not build")
    args = parser.parse_args()

    if args.debug and args.apk:
        parser.error("--debug and --apk are mutually exclusive")

    ensure_system_deps()
    bin_dir = ensure_venv()
    generate_assets()

    if args.deps_only:
        log("Dependencies installed. Skipping build.")
        return

    mode = "debug" if args.debug else ("apk" if args.apk else "release")
    buildozer = bin_dir / "buildozer"
    build(buildozer, mode, args.clean)


if __name__ == "__main__":
    main()
