#!/usr/bin/env python3
"""Build an unsigned macOS Application Bundle (.app) and zip for distribution.

Produces:
    dist/Voice Flow.app
    dist/VoiceFlow-macOS-unsigned.zip
"""

from __future__ import annotations

import os
import plistlib
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
APP_NAME = "Voice Flow"
BUNDLE_DIR = DIST_DIR / f"{APP_NAME}.app"
CONTENTS_DIR = BUNDLE_DIR / "Contents"
MACOS_DIR = CONTENTS_DIR / "MacOS"
RESOURCES_DIR = CONTENTS_DIR / "Resources"
SRC_DIR = REPO_ROOT / "src" / "voice_flow"


def create_info_plist() -> None:
    plist_data = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.voiceflow.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleExecutable": "voice-flow-launcher",
        "CFBundleIconFile": "AppIcon",
        "LSMinimumSystemVersion": "12.0",
        "NSMicrophoneUsageDescription": "Voice Flow requires microphone access for voice dictation and speech-to-text.",
        "NSAppleEventsUsageDescription": "Voice Flow needs access to paste transcribed text into target applications.",
        "NSSupportsAutomaticGraphicsSwitching": True,
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
    }
    with open(CONTENTS_DIR / "Info.plist", "wb") as f:
        plistlib.dump(plist_data, f)


def create_launcher_script() -> None:
    launcher = MACOS_DIR / "voice-flow-launcher"
    script = """#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$DIR/Resources/src:$PYTHONPATH"

# Prefer python3 in PATH or common installation locations
PYTHON=""
for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "Python 3 is required to run Voice Flow. Please install Python 3." buttons {"OK"} default button 1 with icon stop'
    exit 1
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


def package_zip() -> Path:
    zip_path = DIST_DIR / "VoiceFlow-macOS-unsigned.zip"
    if zip_path.exists():
        zip_path.unlink()
    print(f"Archiving {BUNDLE_DIR} to {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUNDLE_DIR):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(DIST_DIR)
                zf.write(full_path, arcname=str(rel_path))
    print(f"Created {zip_path} ({zip_path.stat().st_size} bytes)")
    return zip_path


def main() -> None:
    print(f"Building {APP_NAME}.app...")
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    MACOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    create_info_plist()
    create_launcher_script()
    create_app_icon()
    copy_resources()
    zip_path = package_zip()
    print(f"Build complete: {zip_path}")


if __name__ == "__main__":
    main()
