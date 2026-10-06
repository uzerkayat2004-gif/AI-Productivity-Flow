#!/usr/bin/env python3
"""Build an unsigned macOS Application Bundle (.app) and zip archive for distribution.

Produces:
    dist/AI Productivity Flow.app
    dist/AI-Productivity-Flow-macOS.zip
    dist/AI-Productivity-Flow-macOS.zip.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
APP_NAME = "AI Productivity Flow"
BUNDLE_DIR = DIST_DIR / f"{APP_NAME}.app"
CONTENTS_DIR = BUNDLE_DIR / "Contents"
MACOS_DIR = CONTENTS_DIR / "MacOS"
RESOURCES_DIR = CONTENTS_DIR / "Resources"
SRC_DIR = REPO_ROOT / "src" / "voice_flow"

# Canonical version
try:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from voice_flow._version import VERSION
except Exception:
    VERSION = "1.0.0"


def create_info_plist() -> None:
    plist_data = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.uzerkayat.aiproductivityflow",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleExecutable": "ai-productivity-flow-launcher",
        "CFBundleIconFile": "AppIcon",
        "LSMinimumSystemVersion": "12.0",
        "NSMicrophoneUsageDescription": "AI Productivity Flow requires microphone access for voice dictation and speech-to-text.",
        "NSAppleEventsUsageDescription": "AI Productivity Flow needs access to paste transcribed text into target applications.",
        "NSSupportsAutomaticGraphicsSwitching": True,
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
    }
    with open(CONTENTS_DIR / "Info.plist", "wb") as f:
        plistlib.dump(plist_data, f)


def create_launcher_script() -> None:
    launcher = MACOS_DIR / "ai-productivity-flow-launcher"
    script = """#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$DIR/Resources/src:$DIR/Resources/runtime/site-packages:$DIR/Resources/runtime/python/lib/python3.11/site-packages:$PYTHONPATH"
export PATH="$DIR/Resources/runtime/python/bin:$PATH"

# 1. Check for bundled private standalone Python runtime
PYTHON=""
if [ -x "$DIR/Resources/runtime/python/bin/python3" ]; then
    PYTHON="$DIR/Resources/runtime/python/bin/python3"
elif [ -x "$DIR/Resources/runtime/bin/python3" ]; then
    PYTHON="$DIR/Resources/runtime/bin/python3"
fi

# 2. Fallback to system / homebrew / user python 3.10+
if [ -z "$PYTHON" ]; then
    for candidate in \\
        /opt/homebrew/bin/python3.12 \\
        /opt/homebrew/bin/python3.11 \\
        /opt/homebrew/bin/python3 \\
        /usr/local/bin/python3.12 \\
        /usr/local/bin/python3.11 \\
        /usr/local/bin/python3 \\
        python3 \\
        /usr/bin/python3; do
        if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                PYTHON="$candidate"
                break
            fi
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "Python 3.10+ is required to run AI Productivity Flow. Please install Python 3.10 or newer from python.org or Homebrew (brew install python@3.12)." buttons {"OK"} default button 1 with icon stop'
    exit 1
fi

# 3. Check architecture compatibility and runtime dependencies
HOST_ARCH="$(uname -m)"
MANIFEST="$DIR/Resources/runtime/build-manifest.json"
BUILD_ARCH=""
if [ -f "$MANIFEST" ]; then
    BUILD_ARCH=$(grep -o '"build_machine": *"[^"]*"' "$MANIFEST" | head -n 1 | cut -d'"' -f4)
fi

if [ "$HOST_ARCH" = "x86_64" ] && [ "$BUILD_ARCH" = "arm64" ]; then
    osascript -e 'display dialog "Notice: The bundled dependencies were packaged for Apple Silicon (arm64), but this Mac uses an Intel processor (x86_64).\\n\\nPlease run the terminal installer to configure native Intel dependencies:\\ncurl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash" buttons {"OK"} default button 1 with icon caution'
    exit 1
elif ! "$PYTHON" -c "import sounddevice, requests, cryptography; from voice_flow.main import main" 2>/dev/null; then
    if [ "$HOST_ARCH" = "x86_64" ] && [ -d "$DIR/Resources/runtime/site-packages" ]; then
        osascript -e 'display dialog "Notice: Native dependencies could not be loaded on this Intel (x86_64) Mac.\\n\\nPlease run the terminal installer to configure native Intel dependencies:\\ncurl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash" buttons {"OK"} default button 1 with icon caution'
        exit 1
    fi
fi

exec "$PYTHON" -m voice_flow.main "$@"
"""
    launcher.write_text(script, encoding="utf-8")
    try:
        launcher.chmod(0o755)
    except Exception:
        pass


def create_app_icon() -> None:
    ico_path = SRC_DIR / "gui" / "assets" / "icon.ico"
    out_icns = RESOURCES_DIR / "AppIcon.icns"
    if ico_path.is_file():
        try:
            from PIL import Image
            img = Image.open(ico_path)
            img.save(out_icns, format="ICNS")
            print(f"Generated {out_icns}")
        except Exception as exc:
            print(f"Warning: could not generate AppIcon.icns: {exc}")


def copy_resources() -> None:
    dst_src = RESOURCES_DIR / "src" / "voice_flow"
    if dst_src.exists():
        shutil.rmtree(dst_src)
    shutil.copytree(
        SRC_DIR,
        dst_src,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.pyd"),
    )


def bundle_runtime_dependencies() -> None:
    """Bundle dependencies into Contents/Resources/runtime/site-packages if present."""
    import json
    import platform

    runtime_dir = RESOURCES_DIR / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target_sp = runtime_dir / "site-packages"

    # Write build manifest for architecture audit
    manifest = {
        "build_platform": platform.platform(),
        "build_machine": platform.machine(),
        "python_version": platform.python_version(),
        "bundled_runtime": True,
        "supported_architectures": [platform.machine()],
    }
    (runtime_dir / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if target_sp.exists() and any(target_sp.iterdir()):
        print(f"Target site-packages already populated at {target_sp}")
        return

    # 1. If a private venv exists in repo root (.venv/lib or .venv/Lib)
    venv_dir = REPO_ROOT / ".venv"
    if venv_dir.is_dir():
        # Unix layout
        for py_dir in (venv_dir / "lib").glob("python3*"):
            sp = py_dir / "site-packages"
            if sp.is_dir():
                print(f"Bundling dependencies from repo .venv (Unix) {sp}...")
                shutil.copytree(
                    sp,
                    target_sp,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "pip*", "setuptools*", "wheel*"),
                )
                return
        # Windows layout
        sp_win = venv_dir / "Lib" / "site-packages"
        if sp_win.is_dir():
            print(f"Bundling dependencies from repo .venv (Windows) {sp_win}...")
            shutil.copytree(
                sp_win,
                target_sp,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "pip*", "setuptools*", "wheel*"),
            )
            return

    # 2. If running inside a virtualenv, bundle from active virtual environment
    if sys.prefix != sys.base_prefix:
        import site
        try:
            sp_list = site.getsitepackages()
        except Exception:
            sp_list = [sys.prefix + "/lib/python" + f"{sys.version_info.major}.{sys.version_info.minor}" + "/site-packages"]
        for sp_str in sp_list:
            sp = Path(sp_str)
            if sp.is_dir() and "site-packages" in sp.name:
                print(f"Bundling dependencies from active virtualenv {sp}...")
                shutil.copytree(
                    sp,
                    target_sp,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "pip*", "setuptools*", "wheel*"),
                )
                return

    # 3. Active Python environment site-packages (hosted toolcache or system Python)
    import site
    try:
        candidate_dirs = [Path(p) for p in site.getsitepackages() if "site-packages" in p]
    except Exception:
        candidate_dirs = []
    for sp in candidate_dirs:
        if sp.is_dir():
            print(f"Bundling dependencies from active Python environment {sp}...")
            shutil.copytree(
                sp,
                target_sp,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "pip*", "setuptools*", "wheel*"),
            )
            break

    # Clean up runner-specific editable links or redundant dist-info
    if target_sp.exists():
        for dead_link in target_sp.glob("*_editable_impl_*"):
            try:
                dead_link.unlink()
            except Exception:
                pass
        for dead_info in target_sp.glob("voice_flow-*.dist-info"):
            try:
                shutil.rmtree(dead_info, ignore_errors=True)
            except Exception:
                pass

    if not target_sp.exists() or not any(target_sp.iterdir()):
        print("Warning: No site-packages found to bundle into macOS app package.")


def package_zip() -> Path:
    zip_path = DIST_DIR / "AI-Productivity-Flow-macOS.zip"
    if zip_path.exists():
        zip_path.unlink()
    print(f"Archiving {BUNDLE_DIR} to {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUNDLE_DIR):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(DIST_DIR)
                rel_posix = rel_path.as_posix()
                is_executable = (
                    rel_posix.startswith(f"{APP_NAME}.app/Contents/MacOS/")
                    or file.endswith(".sh")
                    or file.endswith(".command")
                )
                info = zipfile.ZipInfo(rel_posix)
                info.date_time = (2026, 10, 6, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3  # Unix
                if is_executable:
                    info.external_attr = 0o100755 << 16
                else:
                    info.external_attr = 0o100644 << 16
                zf.writestr(info, full_path.read_bytes())
    size = zip_path.stat().st_size
    print(f"Created {zip_path} ({size} bytes)")

    # Generate SHA-256
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = DIST_DIR / "AI-Productivity-Flow-macOS.zip.sha256"
    sha_path.write_text(f"{sha} *AI-Productivity-Flow-macOS.zip\n", encoding="utf-8")
    print(f"Generated {sha_path} ({sha})")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build macOS Application Bundle")
    parser.add_argument("--bundle-runtime", action="store_true", help="Bundle dependencies into app package")
    args = parser.parse_args()

    print(f"Building {APP_NAME}.app (v{VERSION})...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    MACOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    create_info_plist()
    create_launcher_script()
    create_app_icon()
    copy_resources()
    if args.bundle_runtime:
        bundle_runtime_dependencies()
    zip_path = package_zip()
    print(f"Build complete: {zip_path}")


if __name__ == "__main__":
    main()
