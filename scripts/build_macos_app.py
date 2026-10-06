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
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
ASSETS_DIR = REPO_ROOT / "scripts" / "assets"
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
        "CFBundleVersion": "1",
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


def generate_dmg_background(output_path: Path) -> Path:
    """Generate a high-res branded DMG background image matching website palette."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont
        w, h = 660, 400
        img = Image.new("RGB", (w, h), color="#f7f5ee")
        draw = ImageDraw.Draw(img)

        # Subtle elegant inner border
        draw.rectangle([(12, 12), (w - 12, h - 12)], outline="#e6e0d2", width=2)
        draw.rectangle([(14, 14), (w - 14, h - 14)], outline="#f0ede4", width=1)

        # Header area subtle bar
        draw.rectangle([(16, 16), (w - 16, 68)], fill="#efece3")

        # Fonts
        try:
            font_title = ImageFont.truetype("arial.ttf", 20)
            font_sub = ImageFont.truetype("arial.ttf", 12)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # Title and instruction
        title_text = "AI Productivity Flow"
        sub_text = "Drag AI Productivity Flow into Applications to install"
        draw.text((w // 2, 34), title_text, fill="#1c1d1a", font=font_title, anchor="mm")
        draw.text((w // 2, 54), sub_text, fill="#787367", font=font_sub, anchor="mm")

        # Icon drop landing guide circles
        # Left: App icon at (170, 205)
        # Right: Applications at (490, 205)
        draw.ellipse([(170 - 64, 205 - 64), (170 + 64, 205 + 64)], outline="#e8e2d4", width=2)
        draw.ellipse([(490 - 64, 205 - 64), (490 + 64, 205 + 64)], outline="#e8e2d4", width=2)

        # Center arrow: from x=270 to x=390, y=205 in brand terracotta #d95d1e
        arrow_color = "#d95d1e"
        draw.line([(275, 205), (370, 205)], fill=arrow_color, width=5)
        draw.polygon([(365, 192), (388, 205), (365, 218)], fill=arrow_color)

        # Bottom footer tagline
        footer_text = "From text to video  •  From text to audio  •  From voice to text"
        draw.text((w // 2, 370), footer_text, fill="#999385", font=font_sub, anchor="mm")

        img.save(output_path, "PNG")
        print(f"Generated DMG background image: {output_path}")
        return output_path
    except Exception as exc:
        print(f"Warning: could not generate DMG background image via PIL: {exc}")
        return output_path


def _write_sha256(path: Path) -> Path:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    sha_path = path.with_suffix(path.suffix + ".sha256")
    sha_path.write_text(f"{sha}  {path.name}\n", encoding="utf-8")
    print(f"Generated {sha_path} ({sha})")
    return sha_path


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
    _write_sha256(zip_path)
    return zip_path


def create_dmg(app_bundle: Path, output_dmg: Path, background_img: Path) -> Path:
    """Create a Finder-styled .dmg with app icon, arrow, and Applications shortcut."""
    if output_dmg.exists():
        output_dmg.unlink()
    sha_path = output_dmg.with_suffix(".dmg.sha256")
    if sha_path.exists():
        sha_path.unlink()

    icon_icns = app_bundle / "Contents" / "Resources" / "AppIcon.icns"
    app_name = app_bundle.name

    # 1. Try create-dmg CLI if available (standard macOS brew tool)
    create_dmg_bin = shutil.which("create-dmg")
    if create_dmg_bin:
        print(f"Building DMG with create-dmg: {output_dmg}...")
        cmd = [
            create_dmg_bin,
            "--volname", "AI Productivity Flow",
            "--window-pos", "200", "120",
            "--window-size", "660", "400",
            "--icon-size", "120",
            "--icon", app_name, "170", "205",
            "--hide-extension", app_name,
            "--app-drop-link", "490", "205",
            "--no-internet-enable",
        ]
        if background_img.is_file():
            cmd.extend(["--background", str(background_img)])
        if icon_icns.is_file():
            cmd.extend(["--volicon", str(icon_icns)])
        cmd.extend([str(output_dmg), str(app_bundle)])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if output_dmg.is_file() and output_dmg.stat().st_size > 100000:
            print(f"create-dmg succeeded: {output_dmg} ({output_dmg.stat().st_size} bytes)")
            _write_sha256(output_dmg)
            return output_dmg
        print(f"create-dmg finished (code {proc.returncode}): {proc.stderr[:800]}")

    # 2. Try Python dmgbuild if available
    try:
        import dmgbuild
        print(f"Building DMG with dmgbuild: {output_dmg}...")
        settings_file = output_dmg.parent / "dmg_settings.py"
        settings_content = f"""
filename = {repr(str(output_dmg))}
volume_name = "AI Productivity Flow"
format = "UDZO"
files = [{repr(str(app_bundle))}]
symlinks = {{"Applications": "/Applications"}}
icon_size = 120
window_rect = ((200, 120), (660, 400))
icon_locations = {{
    {repr(app_name)}: (170, 205),
    "Applications": (490, 205),
}}
"""
        if background_img.is_file():
            settings_content += f"background = {repr(str(background_img))}\n"
        if icon_icns.is_file():
            settings_content += f"badge_icon = {repr(str(icon_icns))}\n"

        settings_file.write_text(settings_content, encoding="utf-8")
        try:
            dmgbuild.build_dmg(
                filename=str(output_dmg),
                volume_name="AI Productivity Flow",
                settings_file=str(settings_file),
                look_for_glob=False,
            )
        finally:
            if settings_file.exists():
                settings_file.unlink()

        if output_dmg.is_file():
            print(f"dmgbuild succeeded: {output_dmg} ({output_dmg.stat().st_size} bytes)")
            _write_sha256(output_dmg)
            return output_dmg
    except ImportError:
        pass
    except Exception as exc:
        print(f"dmgbuild failed: {exc}")

    # 3. Fallback to native macOS hdiutil if available
    hdiutil_bin = shutil.which("hdiutil")
    if hdiutil_bin:
        print(f"Building DMG with macOS hdiutil: {output_dmg}...")
        staging = output_dmg.parent / "dmg_staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app_bundle, staging / app_name, symlinks=True)
        try:
            os.symlink("/Applications", staging / "Applications")
        except Exception:
            pass
        proc = subprocess.run(
            [hdiutil_bin, "create", "-volname", "AI Productivity Flow", "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(output_dmg)],
            capture_output=True, text=True,
        )
        shutil.rmtree(staging, ignore_errors=True)
        if proc.returncode == 0 and output_dmg.is_file():
            print(f"hdiutil succeeded: {output_dmg} ({output_dmg.stat().st_size} bytes)")
            _write_sha256(output_dmg)
            return output_dmg
        print(f"hdiutil finished (code {proc.returncode}): {proc.stderr[:800]}")

    print("Notice: No macOS DMG builder (create-dmg, dmgbuild, hdiutil) available on this environment.")
    return output_dmg


def main() -> None:
    parser = argparse.ArgumentParser(description="Build macOS Application Bundle and Installers")
    parser.add_argument("--bundle-runtime", action="store_true", help="Bundle dependencies into app package")
    parser.add_argument("--dmg", action="store_true", default=True, help="Build macOS .dmg installer (default: True)")
    parser.add_argument("--dmg-only", action="store_true", help="Only build/repackage the DMG from existing .app")
    parser.add_argument("--no-dmg", action="store_true", help="Skip building .dmg installer")
    parser.add_argument("--no-zip", action="store_true", help="Skip building .zip archive")
    args = parser.parse_args()

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    bg_img = ASSETS_DIR / "dmg_background.png"
    generate_dmg_background(bg_img)

    dmg_path = DIST_DIR / "AI-Productivity-Flow-macOS.dmg"

    if args.dmg_only:
        if not BUNDLE_DIR.is_dir():
            sys.exit(f"Cannot run --dmg-only: {BUNDLE_DIR} does not exist!")
        create_dmg(BUNDLE_DIR, dmg_path, bg_img)
        return

    print(f"Building {APP_NAME}.app (v{VERSION})...")
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

    if not args.no_zip:
        package_zip()

    if not args.no_dmg:
        create_dmg(BUNDLE_DIR, dmg_path, bg_img)

    print("Build complete.")


if __name__ == "__main__":
    main()

