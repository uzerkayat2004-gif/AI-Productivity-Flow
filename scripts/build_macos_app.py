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
    from voice_flow._version import DISPLAY_VERSION, VERSION
except Exception:
    VERSION = "1.0.0"
    DISPLAY_VERSION = "1.0"

# The oldest macOS every bundled Mach-O binary supports. This value is written
# to Info.plist (LSMinimumSystemVersion) and the build fails if any bundled
# binary needs a newer macOS (see verify_bundle_minimum_macos), so README and
# Info.plist cannot drift from the binaries again. The binding constraints are
# the macOS arm64 scipy/numpy wheels (Accelerate builds, minos 14.0) and the
# official llama.cpp release (minos 13.3).
MACOS_MINIMUM = "14.0"

# Official llama.cpp release whose llama-server runs local S1-mini polish on
# macOS (the Windows build uses the in-process llama-cpp-python wheel instead).
LLAMA_CPP_BUILD = "b11696"
LLAMA_CPP_MACOS_ARM64_URL = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_BUILD}/"
    f"llama-{LLAMA_CPP_BUILD}-bin-macos-arm64.tar.gz"
)
LLAMA_CPP_MACOS_ARM64_SHA256 = "6aac007fbe153efefe06250d2cf05d0487583aa0706379082ebef2b05579f649"

# Official NVIDIA NeMo-Speech.cpp C ABI runtime for Nemotron speech (same C ABI
# v1 the Windows app uses with v0.1.0). macOS ships v0.2.0: on a macOS arm64
# runner v0.1.0 needed 25-40 s to recognize 4.8 s of audio (and 35 s for the
# warm-up pass), v0.2.0 takes 0.9-1.3 s with identical text.
NEMO_SPEECH_VERSION = "0.2.0"
NEMO_SPEECH_MACOS_ARM64_URL = (
    f"https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v{NEMO_SPEECH_VERSION}/"
    f"nemo-speech-{NEMO_SPEECH_VERSION}-macos-aarch64-cpu.tar.gz"
)
NEMO_SPEECH_MACOS_ARM64_SHA256 = "6a91355e15d22db6a319144d389d2e1b02f233c1c6808c0da85b6d3283e52296"


def create_info_plist() -> None:
    plist_data = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.uzerkayat.aiproductivityflow",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": DISPLAY_VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleExecutable": "ai-productivity-flow-launcher",
        "CFBundleIconFile": "AppIcon",
        "LSMinimumSystemVersion": MACOS_MINIMUM,
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
# Never write .pyc files into the (signed, often read-only) bundle.
export PYTHONDONTWRITEBYTECODE=1

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


def create_native_launcher(target_arch: str | None = None) -> None:
    """Compile the outer executable without initializing or linking AppKit."""
    if sys.platform != "darwin":
        raise RuntimeError("Native macOS application builds require a macOS host with clang.")
    clang = shutil.which("clang")
    if not clang:
        raise RuntimeError("Native macOS application builds require clang (Xcode command line tools).")
    library = RESOURCES_DIR / "runtime" / "python" / "lib" / "libpython3.11.dylib"
    if not library.is_file():
        raise RuntimeError("Bundled libpython3.11.dylib is required before compiling the native launcher.")
    source = REPO_ROOT / "scripts" / "native_macos_launcher.c"
    if not source.is_file():
        raise RuntimeError("Native macOS launcher source is missing.")
    arch = target_arch or platform.machine().lower()
    arch = "arm64" if arch in ("arm64", "aarch64") else arch
    if arch not in ("arm64", "x86_64"):
        raise RuntimeError(f"Unsupported macOS launcher architecture: {arch}")
    launcher = MACOS_DIR / "ai-productivity-flow-launcher"
    # Compile into a separate file: a compiler failure cannot leave the shell
    # scaffold looking like a successfully compiled distributable executable.
    candidate = launcher.with_name(launcher.name + ".native")
    subprocess.run([
        clang, "-arch", arch, f"-mmacosx-version-min={MACOS_MINIMUM}",
        "-Wall", "-Wextra", "-Werror", str(source), "-o", str(candidate),
    ], check=True)
    if not candidate.is_file() or candidate.read_bytes()[:4] != b"\xcf\xfa\xed\xfe":
        raise RuntimeError("clang did not produce a native 64-bit Mach-O launcher.")
    candidate.chmod(0o755)
    candidate.replace(launcher)


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
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.bundle_code2video import copy_code2video

    vendor_src = REPO_ROOT / "third_party" / "code2video"
    if vendor_src.is_dir():
        copy_code2video(vendor_src, RESOURCES_DIR / "third_party" / "code2video")
        print(f"Bundled Code2Video into {RESOURCES_DIR / 'third_party' / 'code2video'}")
    for notice_name, notice_src in (
        ("LICENSE", REPO_ROOT / "LICENSE"),
        ("THIRD_PARTY_NOTICES.txt", REPO_ROOT / "release" / "THIRD_PARTY_NOTICES.txt"),
    ):
        if notice_src.is_file():
            shutil.copy2(notice_src, RESOURCES_DIR / notice_name)


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


# faster-whisper base.en, pinned to the same revision and SHA-256 values as the
# Windows installer (release/assemble_windows_staging.py and
# release-packaging/WHISPER_BUNDLE.md). Shipping it in the .app means local
# dictation works offline from the very first use: nothing is fetched from
# huggingface.co at runtime.
WHISPER_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
WHISPER_BASE = f"https://huggingface.co/Systran/faster-whisper-base.en/resolve/{WHISPER_REVISION}/"
WHISPER_FILES = {
    "model.bin": "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef",
    "config.json": "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb",
    "tokenizer.json": "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
    "vocabulary.txt": "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_whisper_model(runtime_dir: Path, cache_dir: Path | None = None, fetch=None) -> dict:
    """Copy the pinned Whisper base.en files into ``runtime/models/whisper/base.en``.

    Each file is downloaded once into ``.cache/whisper-base.en`` and verified
    against its SHA-256; a mismatch stops the build.
    """
    cache_dir = cache_dir or (REPO_ROOT / ".cache" / "whisper-base.en")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_dir / "models" / "whisper" / "base.en"
    target.mkdir(parents=True, exist_ok=True)

    def _download(url: str, dest: Path) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Productivity-Flow-Builder"})
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(dest)

    fetch = fetch or _download
    hashes: dict[str, str] = {}
    for name, expected in WHISPER_FILES.items():
        cached = cache_dir / name
        if not cached.is_file() or _sha256_file(cached) != expected:
            print(f"Downloading Whisper base.en {name}...")
            fetch(WHISPER_BASE + name, cached)
        actual = _sha256_file(cached)
        if actual != expected:
            raise RuntimeError(f"WHISPER CHECKSUM MISMATCH for {name}: {actual} != {expected}")
        shutil.copy2(cached, target / name)
        hashes[name] = actual
    total = sum((target / name).stat().st_size for name in WHISPER_FILES)
    print(f"Bundled Whisper base.en ({total / 1_048_576:.1f} MB) into {target}")
    return {"model": "Systran/faster-whisper-base.en", "revision": WHISPER_REVISION, "sha256": hashes}


NOTEBOOKLM_PACKAGE = "notebooklm-py[browser,mcp]==0.8.2"


def ensure_bundled_notebooklm(python_bin: Path) -> None:
    """Install notebooklm into the bundled Mac runtime and require its CLI.

    ``notebooklm`` and ``notebooklm-mcp`` are console scripts of the same
    package. A bundle that ships only the MCP binary cannot sign in. The
    module must import from this runtime, and ``bin/notebooklm`` must exist so
    ``python3 -m notebooklm`` can be launched beside it.
    """
    script = python_bin.parent / "notebooklm"
    probe_code = "import notebooklm, pathlib; print(pathlib.Path(notebooklm.__file__).resolve())"

    def probe() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(python_bin), "-c", probe_code],
            capture_output=True,
            text=True,
            check=False,
        )

    result = probe()
    if result.returncode != 0 or not script.is_file():
        print(f"Installing {NOTEBOOKLM_PACKAGE} into {python_bin}")
        subprocess.run([str(python_bin), "-m", "pip", "install", NOTEBOOKLM_PACKAGE], check=True)
        result = probe()
    module_text = (result.stdout or "").strip()
    if result.returncode != 0 or not script.is_file() or not module_text:
        detail = (result.stderr or result.stdout or "")[-2000:]
        raise RuntimeError(
            "Bundled Mac runtime is missing NotebookLM. "
            f"Expected {script} and a successful import.\n{detail}"
        )
    module = Path(module_text)
    runtime_root = python_bin.resolve().parent.parent
    if runtime_root not in module.parents:
        raise RuntimeError(f"notebooklm imported from outside the bundled runtime: {module}")
    print(f"Bundled NotebookLM CLI: {script}")
    print(f"Bundled NotebookLM module: {module}")


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
    manifest["whisper"] = stage_whisper_model(runtime_dir)
    try:
        from voice_flow.bundled_runtime import mac_runtime
        manifest["runtime"] = mac_runtime()
    except Exception as exc:
        print(f"Warning: could not record the app-update runtime fingerprint: {exc}")
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
                "cryptography", "sentry-sdk>=2.0.0", "openai>=1.40.0,<3"
            ]
            subprocess.run([str(python_bin), "-m", "pip", "install", *packages], check=True)
        ensure_bundled_notebooklm(python_bin)
    else:
        print(f"Host platform is '{sys.platform}'. Skipping pip package installation in Darwin binary on non-Darwin host.")

    sanitize_runtime_libraries(runtime_dir)


# ---------------------------------------------------------------------------
# Native speech/polish engines (macOS arm64)
# ---------------------------------------------------------------------------

def _download_verified(url: str, sha256: str, cache_name: str) -> Path:
    """Download ``url`` once into .cache/engines and verify its pinned SHA-256."""
    cache_dir = REPO_ROOT / ".cache" / "engines"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / cache_name

    def digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    if target.is_file() and digest(target) == sha256:
        return target
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            print(f"Downloading {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Productivity-Flow-Builder"})
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out, 1024 * 1024)
            tmp.replace(target)
            break
        except Exception as exc:  # network hiccup: retry, then fail loudly
            last_error = exc
    else:
        raise RuntimeError(f"Failed to download {url}: {last_error}")
    actual = digest(target)
    if actual != sha256:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {url}: expected {sha256}, got {actual}")
    return target


def _safe_extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            out = (dest / member.name).resolve()
            if not out.is_relative_to(root):
                raise RuntimeError(f"Unsafe path in {archive.name}: {member.name}")
            if member.issym() or member.islnk():
                link = (out.parent / member.linkname).resolve()
                if not link.is_relative_to(root):
                    raise RuntimeError(f"Unsafe link in {archive.name}: {member.name}")
        tar.extractall(dest)


def _rpath_dependencies(binary: Path) -> list[str]:
    """``@rpath/`` library names a Mach-O loads (read from its load commands)."""
    names = []
    for dep in macho_info(binary).get("dylibs", []):
        if dep.startswith("@rpath/") or dep.startswith("@loader_path/"):
            names.append(dep.split("/", 1)[1])
    return names


def _copy_with_rpath_closure(src_dir: Path, roots: list[str], dest_dir: Path) -> list[Path]:
    """Copy ``roots`` from src_dir plus every @rpath dylib they (transitively) load.

    The upstream binaries use ``@loader_path`` rpaths, so keeping them together
    in one directory makes them self-contained. Version symlinks are recreated.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    pending = list(roots)
    seen: set[str] = set()
    copied: list[Path] = []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        src = src_dir / name
        if not src.exists():
            raise RuntimeError(f"{name} is missing from {src_dir}")
        if src.is_symlink():
            real = src.resolve()
            link_target = os.path.relpath(real, src.parent)
            dst = dest_dir / name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(link_target, dst)
            pending.append(real.name)
            continue
        dst = dest_dir / name
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        copied.append(dst)
        pending.extend(_rpath_dependencies(src))
    return copied


def _adhoc_sign(paths: list[Path]) -> None:
    """Strip quarantine/provenance attributes and (re)sign each Mach-O ad hoc.

    arm64 macOS refuses to run unsigned code; the outer bundle signature only
    seals these loose Resources files, it does not sign them.
    """
    if sys.platform != "darwin":
        return
    for path in paths:
        subprocess.run(["xattr", "-c", str(path)], check=False, capture_output=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(path)], check=True, capture_output=True)


def bundle_llama_server(runtime_dir: Path) -> Path:
    """Bundle the official llama.cpp macOS arm64 llama-server for local S1-mini polish.

    Layout: Contents/Resources/runtime/llama/{llama-server, lib*.dylib, LICENSE}.
    The app finds it via runtime_env.mac_bundled_llama_server().
    """
    archive = _download_verified(
        LLAMA_CPP_MACOS_ARM64_URL, LLAMA_CPP_MACOS_ARM64_SHA256,
        f"llama-{LLAMA_CPP_BUILD}-bin-macos-arm64.tar.gz",
    )
    work = DIST_DIR / ".engine-extract" / "llama"
    shutil.rmtree(work, ignore_errors=True)
    _safe_extract(archive, work)
    src_dirs = [p.parent for p in work.rglob("llama-server") if p.is_file()]
    if not src_dirs:
        raise RuntimeError("llama-server not found in the llama.cpp release archive")
    src_dir = src_dirs[0]
    dest = runtime_dir / "llama"
    shutil.rmtree(dest, ignore_errors=True)
    copied = _copy_with_rpath_closure(src_dir, ["llama-server"], dest)
    if (src_dir / "LICENSE").is_file():
        shutil.copy2(src_dir / "LICENSE", dest / "LICENSE-llama.cpp.txt")
    (dest / "VERSION.txt").write_text(
        f"llama.cpp {LLAMA_CPP_BUILD}\n{LLAMA_CPP_MACOS_ARM64_URL}\nsha256 {LLAMA_CPP_MACOS_ARM64_SHA256}\n",
        encoding="utf-8",
    )
    _adhoc_sign(copied)
    shutil.rmtree(work, ignore_errors=True)
    server = dest / "llama-server"
    if sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        proc = subprocess.run([str(server), "--version"], capture_output=True, text=True, timeout=60)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            raise RuntimeError(f"Bundled llama-server does not run: {output[-800:]}")
        print(f"Bundled llama-server verified: {output.splitlines()[-1] if output else 'ok'}")
    print(f"Bundled llama-server ({len(copied)} binaries) into {dest}")
    return server


def bundle_nemo_speech(runtime_dir: Path, python_bin: Path | None = None) -> Path:
    """Bundle the official NeMo-Speech.cpp C ABI dylib for Nemotron speech.

    Layout: Contents/Resources/runtime/nemo/lib/libnemo_speech_asr_c.dylib (+ deps).
    Kept apart from runtime/llama: both ship a different libggml.0.dylib.
    """
    archive = _download_verified(
        NEMO_SPEECH_MACOS_ARM64_URL, NEMO_SPEECH_MACOS_ARM64_SHA256,
        f"nemo-speech-{NEMO_SPEECH_VERSION}-macos-aarch64-cpu.tar.gz",
    )
    work = DIST_DIR / ".engine-extract" / "nemo"
    shutil.rmtree(work, ignore_errors=True)
    _safe_extract(archive, work)
    libs = [p.parent for p in work.rglob("libnemo_speech_asr_c.dylib")]
    if not libs:
        raise RuntimeError("libnemo_speech_asr_c.dylib not found in the NeMo-Speech release archive")
    src_dir = libs[0]
    dest_root = runtime_dir / "nemo"
    shutil.rmtree(dest_root, ignore_errors=True)
    dest = dest_root / "lib"
    copied = _copy_with_rpath_closure(src_dir, ["libnemo_speech_asr_c.dylib"], dest)
    licenses = src_dir.parent / "share" / "licenses" / "nemo-speech"
    if licenses.is_dir():
        shutil.copytree(licenses, dest_root / "licenses", dirs_exist_ok=True)
    (dest_root / "VERSION.txt").write_text(
        f"NeMo-Speech.cpp {NEMO_SPEECH_VERSION} (macos-aarch64-cpu)\n{NEMO_SPEECH_MACOS_ARM64_URL}\n"
        f"sha256 {NEMO_SPEECH_MACOS_ARM64_SHA256}\n",
        encoding="utf-8",
    )
    _adhoc_sign(copied)
    shutil.rmtree(work, ignore_errors=True)
    dylib = dest / "libnemo_speech_asr_c.dylib"
    if (sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64")
            and python_bin is not None and python_bin.is_file()):
        probe = (
            "import ctypes,sys; d=ctypes.CDLL(sys.argv[1]); "
            "d.nemo_speech_asr_version.restype=ctypes.c_char_p; print(d.nemo_speech_asr_version().decode())"
        )
        proc = subprocess.run([str(python_bin), "-I", "-c", probe, str(dylib)],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"Bundled NeMo-Speech dylib does not load: {(proc.stdout + proc.stderr)[-800:]}")
        print(f"Bundled NeMo-Speech C ABI verified: version {proc.stdout.strip()}")
    print(f"Bundled NeMo-Speech ({len(copied)} binaries) into {dest}")
    return dylib


# ---------------------------------------------------------------------------
# Video Flow toolchain (macOS arm64): Node 22, HyperFrames, Narova, ffmpeg
# ---------------------------------------------------------------------------
# Keep aligned with src/voice_flow/bundled_runtime.py (MAC_NODE, MAC_FFMPEG,
# MAC_HYPERFRAMES); the app-update fingerprint must match what is bundled.
VF_NODE_VERSION = "22.23.3"
VF_NODE_URL = f"https://nodejs.org/dist/v{VF_NODE_VERSION}/node-v{VF_NODE_VERSION}-darwin-arm64.tar.gz"
VF_NODE_SHA256 = "23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53"  # nodejs.org SHASUMS256.txt
VF_FFMPEG_VERSION = "9.0.2"
_VF_FFMPEG_BASE = "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2"
VF_FFMPEG_URL = f"{_VF_FFMPEG_BASE}/ffmpeg.zip"
VF_FFMPEG_SHA256 = "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
VF_FFPROBE_URL = f"{_VF_FFMPEG_BASE}/ffprobe.zip"
VF_FFPROBE_SHA256 = "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
VF_HYPERFRAMES_VERSION = "0.7.96"


def _vf_npm(node: Path, args: list[str], cwd: Path) -> None:
    npm_cli = node.parent.parent / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
    env = dict(os.environ)
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    env["PUPPETEER_SKIP_DOWNLOAD"] = "1"  # the render browser is fetched per user, not bundled
    subprocess.run([str(node), str(npm_cli), *args, "--no-audit", "--no-fund"], cwd=str(cwd), env=env, check=True)


def bundle_video_flow_toolchain(runtime_dir: Path, python_bin: Path | None = None) -> dict:
    """Ship what Video Flow's renderer needs inside the .app, like Windows does.

    runtime/node/bin/node      Node 22 (HyperFrames needs >= 22)
    runtime/ffmpeg/ffmpeg|ffprobe  static arm64 builds (martin-riedl.de, GPL)
    runtime/hyperframes/       hyperframes node_modules
    runtime/narova/tool/       vendored Narova CLI
    narova_tts (+ piper) in the bundled Python, for narration.
    The render browser (chrome-headless-shell) is fetched per user on first
    use by ``hyperframes browser ensure``, as on Windows.
    """
    info: dict = {}
    extract = DIST_DIR / ".vf-extract"
    shutil.rmtree(extract, ignore_errors=True)
    extract.mkdir(parents=True, exist_ok=True)

    # Node
    archive = _download_verified(VF_NODE_URL, VF_NODE_SHA256, f"node-v{VF_NODE_VERSION}-darwin-arm64.tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(path=extract)
    node_dir = runtime_dir / "node"
    shutil.rmtree(node_dir, ignore_errors=True)
    shutil.move(str(extract / f"node-v{VF_NODE_VERSION}-darwin-arm64"), str(node_dir))
    for junk in ("include", "share", "CHANGELOG.md", "README.md"):
        target = node_dir / junk
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            target.unlink()
    node = node_dir / "bin" / "node"
    node.chmod(0o755)
    print("Bundled Node:", subprocess.run([str(node), "--version"], capture_output=True, text=True).stdout.strip())
    info["node"] = VF_NODE_VERSION

    # ffmpeg / ffprobe
    ff_dir = runtime_dir / "ffmpeg"
    shutil.rmtree(ff_dir, ignore_errors=True)
    ff_dir.mkdir(parents=True)
    for url, sha, name in ((VF_FFMPEG_URL, VF_FFMPEG_SHA256, "ffmpeg"), (VF_FFPROBE_URL, VF_FFPROBE_SHA256, "ffprobe")):
        zpath = _download_verified(url, sha, f"{name}-{VF_FFMPEG_VERSION}-arm64.zip")
        with zipfile.ZipFile(zpath) as zf:
            member = next(m for m in zf.namelist() if m.rsplit("/", 1)[-1] == name)
            (ff_dir / name).write_bytes(zf.read(member))
        (ff_dir / name).chmod(0o755)
    line = subprocess.run([str(ff_dir / "ffmpeg"), "-version"], capture_output=True, text=True).stdout.splitlines()[:1]
    print("Bundled ffmpeg:", line)
    (ff_dir / "SOURCE.txt").write_text(
        f"ffmpeg/ffprobe {VF_FFMPEG_VERSION} static macOS arm64 builds from {_VF_FFMPEG_BASE}\n"
        "Licensed under the GNU GPL v3 (built with --enable-gpl --enable-version3). Source: https://ffmpeg.org/download.html\n",
        encoding="utf-8",
    )
    info["ffmpeg"] = VF_FFMPEG_VERSION

    # HyperFrames
    hf = runtime_dir / "hyperframes"
    shutil.rmtree(hf, ignore_errors=True)
    hf.mkdir(parents=True)
    (hf / "package.json").write_text(json.dumps({
        "name": "apf-hyperframes-runtime", "private": True,
        "dependencies": {"hyperframes": VF_HYPERFRAMES_VERSION},
    }, indent=2), encoding="utf-8")
    _vf_npm(node, ["install", "--omit=dev"], hf)
    if not (hf / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs").is_file():
        raise RuntimeError("HyperFrames install did not produce bin/hyperframes.mjs")
    info["hyperframes"] = VF_HYPERFRAMES_VERSION

    # Narova CLI
    source = REPO_ROOT / "third_party" / "narova"
    narova = runtime_dir / "narova"
    shutil.rmtree(narova, ignore_errors=True)
    narova.mkdir(parents=True)
    for name in ("LICENSE", "README.md"):
        if (source / name).is_file():
            shutil.copy2(source / name, narova / name)
    shutil.copytree(
        source / "tool", narova / "tool",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", "evals", "live-tests", "tests"),
    )
    manifest = json.loads((narova / "tool" / "package.json").read_text(encoding="utf-8"))
    if manifest.get("dependencies"):
        lock = narova / "tool" / "package-lock.json"
        _vf_npm(node, ["ci" if lock.is_file() else "install", "--omit=dev"], narova / "tool")

    # narova_tts into the bundled Python
    if python_bin is not None and python_bin.is_file():
        site = subprocess.run(
            [str(python_bin), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        narova_py = source / "tool" / "py"
        dest = Path(site) / "narova_tts"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(narova_py / "narova_tts", dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        piper = subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(narova_py / "requirements.txt")],
                               capture_output=True, text=True)
        if piper.returncode != 0:
            print("WARNING: narova piper backend not installed:\n" + (piper.stderr or "")[-1500:])
    shutil.rmtree(extract, ignore_errors=True)
    return info


def bundle_native_engines(target_arch: str | None = None) -> None:
    """Bundle llama-server (S1-mini polish) and NeMo-Speech (Nemotron) for macOS arm64."""
    arch = (target_arch or platform.machine()).lower()
    if arch not in ("arm64", "aarch64"):
        print(f"Skipping native engines: only macOS arm64 is supported (target {arch}).")
        return
    runtime_dir = RESOURCES_DIR / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    bundle_llama_server(runtime_dir)
    bundle_nemo_speech(runtime_dir, runtime_dir / "python" / "bin" / "python3")
    shutil.rmtree(DIST_DIR / ".engine-extract", ignore_errors=True)
    vf = bundle_video_flow_toolchain(runtime_dir, runtime_dir / "python" / "bin" / "python3")
    manifest_path = runtime_dir / "build-manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["video_flow"] = vf
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Warning: could not record the Video Flow toolchain in the manifest: {exc}")


# ---------------------------------------------------------------------------
# Mach-O minimum macOS version audit
# ---------------------------------------------------------------------------

_LC_REQ_DYLD = 0x80000000
_LC_LOAD_DYLIB = 0xC
_LC_LOAD_WEAK_DYLIB = 0x18 | _LC_REQ_DYLD
_LC_REEXPORT_DYLIB = 0x1F | _LC_REQ_DYLD
_LC_RPATH = 0x1C | _LC_REQ_DYLD
_LC_VERSION_MIN_MACOSX = 0x24
_LC_BUILD_VERSION = 0x32
_PLATFORM_MACOS = 1


def _parse_thin_macho(data: bytes, offset: int) -> dict | None:
    import struct

    magic = data[offset:offset + 4]
    if magic == b"\xcf\xfa\xed\xfe":
        header_size = 32
    elif magic == b"\xce\xfa\xed\xfe":
        header_size = 28
    else:
        return None
    if len(data) < offset + header_size:
        return None
    ncmds, sizeofcmds = struct.unpack_from("<II", data, offset + 16)
    pos = offset + header_size
    end = min(len(data), pos + sizeofcmds)
    result: dict = {"minos": None, "dylibs": [], "rpaths": []}
    for _ in range(ncmds):
        if pos + 8 > end:
            break
        cmd, cmdsize = struct.unpack_from("<II", data, pos)
        if cmdsize < 8:
            break
        if cmd == _LC_BUILD_VERSION and pos + 12 <= end:
            plat, minos = struct.unpack_from("<II", data, pos + 8)
            if plat == _PLATFORM_MACOS:
                result["minos"] = (minos >> 16, (minos >> 8) & 0xFF, minos & 0xFF)
        elif cmd == _LC_VERSION_MIN_MACOSX and pos + 12 <= end:
            (version,) = struct.unpack_from("<I", data, pos + 8)
            result["minos"] = (version >> 16, (version >> 8) & 0xFF, version & 0xFF)
        elif cmd in (_LC_LOAD_DYLIB, _LC_LOAD_WEAK_DYLIB, _LC_REEXPORT_DYLIB, _LC_RPATH):
            (name_off,) = struct.unpack_from("<I", data, pos + 8)
            raw = data[pos + name_off:pos + cmdsize]
            name = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
            result["rpaths" if cmd == _LC_RPATH else "dylibs"].append(name)
        pos += cmdsize
    return result


def macho_info(path: Path) -> dict:
    """Minimum macOS (highest across fat slices), loaded dylibs and rpaths of a Mach-O.

    Returns {} for files that are not Mach-O. Pure Python, so it also runs on
    the Linux/Windows test hosts.
    """
    import struct

    try:
        with open(path, "rb") as handle:
            head = handle.read(4)
            if head not in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
                return {}
            data = head + handle.read()
    except OSError:
        return {}
    slices: list[dict] = []
    if data[:4] == b"\xca\xfe\xba\xbe":
        (nfat,) = struct.unpack_from(">I", data, 4)
        if nfat == 0 or nfat > 16:  # also rules out Java class files
            return {}
        for i in range(nfat):
            _cpu, _sub, off, _size, _align = struct.unpack_from(">IIIII", data, 8 + i * 20)
            parsed = _parse_thin_macho(data, off)
            if parsed:
                slices.append(parsed)
    else:
        parsed = _parse_thin_macho(data, 0)
        if parsed:
            slices.append(parsed)
    if not slices:
        return {}
    minos = max((s["minos"] for s in slices if s["minos"]), default=None)
    dylibs = sorted({d for s in slices for d in s["dylibs"]})
    rpaths = sorted({r for s in slices for r in s["rpaths"]})
    return {"minos": minos, "dylibs": dylibs, "rpaths": rpaths}


def _version_tuple(text: str) -> tuple[int, int, int]:
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])  # type: ignore[return-value]


def audit_bundle_minimum_macos(bundle_dir: Path) -> tuple[tuple[int, int, int] | None, list[tuple[str, str]]]:
    """(highest minos found, [(relative path, minos)] sorted newest first)."""
    found: list[tuple[tuple[int, int, int], str]] = []
    for path in bundle_dir.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        info = macho_info(path)
        if info and info.get("minos"):
            found.append((info["minos"], str(path.relative_to(bundle_dir))))
    found.sort(reverse=True)
    highest = found[0][0] if found else None
    return highest, [(rel, ".".join(map(str, v))) for v, rel in found]


def verify_bundle_minimum_macos(bundle_dir: Path, declared: str = MACOS_MINIMUM) -> str | None:
    """Fail the build when a bundled binary needs a newer macOS than Info.plist declares."""
    highest, entries = audit_bundle_minimum_macos(bundle_dir)
    if highest is None:
        print("Minimum macOS audit: no Mach-O binaries found.")
        return None
    limit = _version_tuple(declared)
    too_new = [(rel, v) for rel, v in entries if _version_tuple(v) > limit]
    highest_text = ".".join(map(str, highest))
    print(f"Minimum macOS audit: {len(entries)} Mach-O files, highest minos {highest_text}, "
          f"declared LSMinimumSystemVersion {declared}.")
    for rel, v in entries[:8]:
        print(f"  minos {v}: {rel}")
    if too_new:
        listing = "\n".join(f"  minos {v}: {rel}" for rel, v in too_new[:20])
        raise RuntimeError(
            f"{len(too_new)} bundled binaries need macOS newer than the declared {declared}:\n{listing}\n"
            "Raise MACOS_MINIMUM (and the README) or bundle older-compatible builds."
        )
    manifest = RESOURCES_DIR / "runtime" / "build-manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["minimum_macos"] = declared
            data["highest_binary_minos"] = highest_text
            manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
    return highest_text


def precompile_bundle_bytecode(python_bin: Path | None = None) -> bool:
    """Ship bytecode so the app never compiles into its own bundle at runtime.

    The launcher sets PYTHONDONTWRITEBYTECODE=1. Unchecked-hash .pyc files stay
    valid however the bundle's timestamps change (cp -R from the DMG, unzip),
    so startup speed is kept without writing into the signed bundle.
    """
    python_bin = python_bin or (RESOURCES_DIR / "runtime" / "python" / "bin" / "python3")
    if not python_bin.is_file():
        print("Bytecode precompile skipped: bundled Python not found.")
        return False
    targets = [RESOURCES_DIR / "src", RESOURCES_DIR / "runtime" / "site-packages",
               RESOURCES_DIR / "runtime" / "python" / "lib" / "python3.11"]
    targets = [str(t) for t in targets if t.is_dir()]
    if not targets:
        return False
    proc = subprocess.run(
        # -f rewrites pip's timestamp .pyc files, which go stale when the
        # bundle is copied without preserving modification times.
        [str(python_bin), "-m", "compileall", "-q", "-f", "-j", "0",
         "--invalidation-mode", "unchecked-hash", *targets],
        check=False,
    )
    # A few vendored test fixtures are intentionally invalid Python; that is fine.
    print(f"Precompiled bundle bytecode (compileall exit {proc.returncode}).")
    return True


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

    if args.bundle_runtime and sys.platform != "darwin":
        raise RuntimeError("Native macOS application builds require a macOS host with clang.")

    print(f"Building {APP_NAME}.app (v{VERSION})...")
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    MACOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    create_info_plist()
    create_launcher_script()
    if not args.bundle_runtime:
        print("Resource-only development scaffold: launcher requires a separately supplied runtime; "
              "use --bundle-runtime on macOS for a native distributable app.")
    create_app_icon()
    copy_resources()
    if args.bundle_runtime:
        bundle_runtime_dependencies(target_arch=args.target_arch)
        bundle_native_engines(target_arch=args.target_arch)
        create_native_launcher(target_arch=args.target_arch)
        verify_bundle_minimum_macos(BUNDLE_DIR)
        precompile_bundle_bytecode()

    sign_app_bundle(BUNDLE_DIR)

    if not args.no_zip:
        package_zip()

    if not args.no_dmg:
        create_dmg(BUNDLE_DIR, dmg_path, bg_img)

    print("Build complete.")


if __name__ == "__main__":
    main()
