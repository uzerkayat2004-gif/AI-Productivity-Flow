#!/usr/bin/env python3
"""Build an unsigned or ad-hoc signed macOS Application Bundle (.app), dmg, and zip for distribution.

Produces:
    dist/AI Productivity Flow.app
    dist/AI-Productivity-Flow-macOS.dmg
    dist/AI-Productivity-Flow-macOS.dmg.sha256
    dist/AI-Productivity-Flow-macOS.zip
    dist/AI-Productivity-Flow-macOS.zip.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
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

PYTHON="$DIR/Resources/runtime/python/bin/python3"

if [ ! -x "$PYTHON" ]; then
    osascript -e 'display dialog "AI Productivity Flow requires its bundled runtime. Please reinstall the app." buttons {"OK"} default button 1 with icon stop'
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


def sanitize_runtime_libraries(runtime_dir: Path) -> None:
    """Verify that no .so or .dylib in runtime links to /opt/homebrew or local build paths."""
    otool = shutil.which("otool")
    found_homebrew = []
    for binary in runtime_dir.rglob("*"):
        if binary.suffix in (".so", ".dylib") or (binary.is_file() and os.access(binary, os.X_OK)):
            if binary.is_symlink():
                continue
            if otool:
                try:
                    res = subprocess.run([otool, "-L", str(binary)], capture_output=True, text=True, check=False)
                    for line in res.stdout.splitlines():
                        dep = line.strip().split(" ")[0]
                        if "/opt/homebrew" in dep or "/usr/local/opt" in dep:
                            found_homebrew.append((binary.name, dep))
                except Exception:
                    pass
            else:
                try:
                    data = binary.read_bytes()
                    if b"/opt/homebrew" in data:
                        found_homebrew.append((binary.name, "/opt/homebrew reference"))
                except Exception:
                    pass

    if found_homebrew:
        print(f"Warning: Detected {len(found_homebrew)} external homebrew dependencies:")
        for name, dep in found_homebrew[:10]:
            print(f"  {name}: {dep}")
    else:
        print("Runtime dependency sanitation verified: zero Homebrew linkages found.")


def bundle_runtime_dependencies(target_arch: str | None = None) -> None:
    """Download and bundle standalone Python 3.11 runtime and dependencies into Contents/Resources/runtime."""
    runtime_dir = RESOURCES_DIR / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not target_arch:
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            target_arch = "aarch64"
        else:
            target_arch = "x86_64"

    manifest = {
        "build_platform": platform.platform(),
        "build_machine": platform.machine(),
        "target_arch": target_arch,
        "python_version": "3.11.17",
        "bundled_runtime": True,
        "supported_architectures": [target_arch],
    }
    (runtime_dir / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    python_dir = runtime_dir / "python"
    python_bin = python_dir / "bin" / "python3"

    if python_bin.is_file() and os.access(python_bin, os.X_OK):
        print(f"Bundled standalone Python already exists at {python_bin}")
    else:
        release_tag = "20261003"
        download_url = (
            f"https://github.com/astral-sh/python-build-standalone/releases/download/"
            f"{release_tag}/cpython-3.11.17+{release_tag}-{target_arch}-apple-darwin-install_only.tar.gz"
        )
        tar_cache_dir = REPO_ROOT / ".cache" / "python-standalone"
        tar_cache_dir.mkdir(parents=True, exist_ok=True)
        tar_filename = f"cpython-3.11.17_{release_tag}_{target_arch}_apple-darwin_install_only.tar.gz"
        tar_path = tar_cache_dir / tar_filename

        if not tar_path.is_file() or tar_path.stat().st_size < 1000000:
            print(f"Downloading standalone Python 3.11 for {target_arch}-apple-darwin from {download_url}...")
            req = urllib.request.Request(download_url, headers={"User-Agent": "AI-Productivity-Flow-Builder"})
            try:
                with urllib.request.urlopen(req) as resp, open(tar_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                print(f"Downloaded {tar_path.stat().st_size} bytes to {tar_path}")
            except Exception as e:
                print(f"Direct download with tag {release_tag} failed: {e}. Querying latest release...")
                try:
                    probe_req = urllib.request.Request(
                        "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest",
                        headers={"User-Agent": "AI-Productivity-Flow-Builder"},
                    )
                    with urllib.request.urlopen(probe_req) as probe_resp:
                        rel_info = json.loads(probe_resp.read().decode())
                        for asset in rel_info.get("assets", []):
                            name = asset.get("name", "")
                            if (
                                "3.11" in name
                                and f"{target_arch}-apple-darwin" in name
                                and "install_only" in name
                                and "stripped" not in name
                            ):
                                download_url = asset["browser_download_url"]
                                break
                    print(f"Retrying download from {download_url}...")
                    req2 = urllib.request.Request(download_url, headers={"User-Agent": "AI-Productivity-Flow-Builder"})
                    with urllib.request.urlopen(req2) as resp2, open(tar_path, "wb") as out_f2:
                        shutil.copyfileobj(resp2, out_f2)
                except Exception as e2:
                    raise RuntimeError(f"Failed to download standalone Python 3.11: {e2}") from e2

        print(f"Extracting standalone Python runtime into {runtime_dir}...")
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=runtime_dir)

    if python_bin.exists():
        try:
            python_bin.chmod(0o755)
        except Exception:
            pass

    # Install pip and dependencies when running on matching macOS host
    if sys.platform == "darwin":
        print(f"Upgrading pip in bundled Python ({python_bin})...")
        subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        print("Installing application requirements into bundled Python runtime...")
        req_file = REPO_ROOT / "requirements.txt"
        if req_file.is_file():
            subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(req_file)], check=True)
        else:
            packages = [
                "faster-whisper", "sounddevice", "numpy", "scipy", "pynput",
                "pyperclip", "pyautogui", "pywebview", "pyobjc-core",
                "pyobjc-framework-Cocoa", "pyobjc-framework-WebKit", "pystray", "pillow",
                "psutil", "edge-tts", "pypdf", "websockets", "requests",
                "cryptography", "sentry-sdk>=2.0.0"
            ]
            subprocess.run([str(python_bin), "-m", "pip", "install", *packages], check=True)
    else:
        print(f"Host platform is '{sys.platform}'. Skipping pip package installation in Darwin binary on non-Darwin host.")

    sanitize_runtime_libraries(runtime_dir)


def sign_app_bundle(bundle_dir: Path) -> bool:
    """Sign the application bundle using Developer ID if available, otherwise ad-hoc (-)."""
    codesign_bin = shutil.which("codesign")
    if not codesign_bin:
        print("codesign binary not found; skipping code signing.")
        return False

    identity = os.environ.get("DEVELOPER_ID_APPLICATION") or "-"
    print(f"Signing {bundle_dir.name} with identity '{identity}'...")
    cmd = [codesign_bin, "--force", "--deep", "--sign", identity, str(bundle_dir)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"Successfully signed {bundle_dir.name}")
            return True
        else:
            print(f"Warning: codesign returned code {proc.returncode}: {proc.stderr.strip()}")
            return False
    except Exception as exc:
        print(f"Warning: codesign execution failed: {exc}")
        return False


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


def _package_zip_fallback(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUNDLE_DIR):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(DIST_DIR)
                rel_posix = rel_path.as_posix()
                is_executable = (
                    rel_posix.startswith(f"{APP_NAME}.app/Contents/MacOS/")
                    or "/bin/" in rel_posix
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


def package_zip() -> Path:
    zip_path = DIST_DIR / "AI-Productivity-Flow-macOS.zip"
    if zip_path.exists():
        zip_path.unlink()
    print(f"Archiving {BUNDLE_DIR} to {zip_path}...")
    zip_bin = shutil.which("zip")
    if zip_bin and sys.platform != "win32":
        cmd = [zip_bin, "-r", "-y", str(zip_path), BUNDLE_DIR.name]
        proc = subprocess.run(cmd, cwd=DIST_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"Warning: zip command failed ({proc.returncode}): {proc.stderr}. Falling back to zipfile.")
            _package_zip_fallback(zip_path)
    else:
        _package_zip_fallback(zip_path)

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
format_version = 2
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
    parser.add_argument("--target-arch", choices=["aarch64", "x86_64"], default=None, help="Target macOS architecture (aarch64 or x86_64)")
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
        sign_app_bundle(BUNDLE_DIR)
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
        bundle_runtime_dependencies(target_arch=args.target_arch)

    sign_app_bundle(BUNDLE_DIR)

    if not args.no_zip:
        package_zip()

    if not args.no_dmg:
        create_dmg(BUNDLE_DIR, dmg_path, bg_img)

    print("Build complete.")


if __name__ == "__main__":
    main()
