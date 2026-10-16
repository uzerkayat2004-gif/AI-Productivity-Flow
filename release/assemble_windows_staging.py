"""Assemble the Windows installer staging tree from official downloads.

Runs on a clean Windows machine (the GitHub Actions ``windows-latest`` runner)
before ``release/build_windows_release.py``. It reproduces the layout that the
build machine used to keep in ``~/apf-release-build/staging``:

    staging/
        LICENSE, THIRD_PARTY_NOTICES.txt
        runtime/
            python/        CPython 3.12.10 (python-build-standalone, incl. Tk + pip)
                           + requirements.txt + narova_tts (+ voice_flow, added later
                           by build_windows_release.refresh_app_package)
            node/          Node.js 20.18.1 (official win-x64 zip)
            hyperframes/   hyperframes@0.7.96 node_modules (installed with the bundled npm)
            narova/tool/   vendored Narova CLI + its node_modules
            ffmpeg/        ffmpeg.exe / ffprobe.exe (gyan.dev essentials 7.1.1) + licenses
            models/whisper/base.en/  faster-whisper base.en at a pinned revision
            webview2/      Microsoft Edge WebView2 Evergreen bootstrapper
            vcredist/      Microsoft VC++ 2015-2022 x64 redistributable
            runtime-manifest.json

Only the repository and official upstream downloads are used. No secrets.

    python release/assemble_windows_staging.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get("APF_BUILD_DIR", Path.home() / "apf-release-build"))
STAGING = BUILD / "staging"
RUNTIME = STAGING / "runtime"
CACHE = BUILD / "downloads"

PYTHON_VERSION = "3.12.10"
PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20250409/"
    "cpython-3.12.10+20250409-x86_64-pc-windows-msvc-install_only.tar.gz"
)
NODE_VERSION = "20.18.1"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
HYPERFRAMES_VERSION = "0.7.96"
FFMPEG_VERSION = "7.1.1"
FFMPEG_URL = (
    f"https://github.com/GyanD/codexffmpeg/releases/download/{FFMPEG_VERSION}/"
    f"ffmpeg-{FFMPEG_VERSION}-essentials_build.zip"
)
WHISPER_REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
WHISPER_BASE = f"https://huggingface.co/Systran/faster-whisper-base.en/resolve/{WHISPER_REVISION}/"
# SHA-256 values recorded in release-packaging/WHISPER_BUNDLE.md.
WHISPER_FILES = {
    "model.bin": "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef",
    "config.json": "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb",
    "tokenizer.json": "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df",
    "vocabulary.txt": "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf",
}
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
# Windows-only packages the app imports that requirements.txt does not list.
WINDOWS_EXTRA_PACKAGES = ["pywinauto", "comtypes", "pywin32", "pycryptodomex"]
# Prebuilt CPU wheel so local S1-mini / LFM polish works out of the box.
LLAMA_CPP_PACKAGE = "llama-cpp-python==0.3.19"
LLAMA_CPP_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"


def log(message: str) -> None:
    print(f"[stage] {message}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.is_file() and target.stat().st_size > 0:
        return target
    tmp = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, 4):
        try:
            log(f"download {url}")
            request = urllib.request.Request(url, headers={"User-Agent": "apf-release-build"})
            with urllib.request.urlopen(request, timeout=300) as response, tmp.open("wb") as out:
                shutil.copyfileobj(response, out, 1024 * 1024)
            tmp.replace(target)
            return target
        except Exception as exc:  # network hiccup: retry, then fail loudly
            log(f"download attempt {attempt} failed: {exc}")
            time.sleep(5 * attempt)
    sys.exit(f"DOWNLOAD FAILED: {url}")


def run(command: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    log("run " + " ".join(str(c) for c in command))
    result = subprocess.run(
        [str(c) for c in command], cwd=str(cwd) if cwd else None,
        env=env, capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"COMMAND FAILED ({result.returncode}): {command}\n"
                 f"{(result.stdout or '')[-3000:]}\n{(result.stderr or '')[-3000:]}")
    return result.stdout


def stage_python() -> Path:
    archive = download(PYTHON_URL, "python-install_only.tar.gz")
    target = RUNTIME / "python"
    if target.exists():
        shutil.rmtree(target)
    with tarfile.open(archive) as tar:
        tar.extractall(RUNTIME)  # archive root folder is "python/"
    python = target / "python.exe"
    if not python.is_file() or not (target / "pythonw.exe").is_file():
        sys.exit(f"PYTHON STAGING FAILED: {python}")
    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    run([python, "-m", "pip", "install", "-r", REPO / "requirements.txt", *WINDOWS_EXTRA_PACKAGES])
    llama = subprocess.run(
        [str(python), "-m", "pip", "install", "--only-binary=:all:",
         "--extra-index-url", LLAMA_CPP_INDEX, LLAMA_CPP_PACKAGE],
        capture_output=True, text=True,
    )
    if llama.returncode != 0:
        log("WARNING: llama-cpp-python wheel unavailable; local polish will need llama-server.\n"
            + (llama.stderr or "")[-1500:])
    # narova_tts (vendored, pure Python) plus its default piper backend.
    site = target / "Lib" / "site-packages"
    narova_py = REPO / "third_party" / "narova" / "tool" / "py"
    shutil.copytree(narova_py / "narova_tts", site / "narova_tts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"), dirs_exist_ok=True)
    piper = subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(narova_py / "requirements.txt")],
        capture_output=True, text=True,
    )
    if piper.returncode != 0:
        # The piper voice backend is optional: the app's Edge TTS voices work
        # without it, and narova_tts imports heavy backends lazily.
        log("WARNING: narova piper backend not installed.\n" + (piper.stderr or "")[-1500:])
    return python


def stage_node() -> Path:
    archive = download(NODE_URL, f"node-v{NODE_VERSION}-win-x64.zip")
    target = RUNTIME / "node"
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(BUILD / "node-extract")
    shutil.move(str(BUILD / "node-extract" / f"node-v{NODE_VERSION}-win-x64"), str(target))
    shutil.rmtree(BUILD / "node-extract", ignore_errors=True)
    node = target / "node.exe"
    if not node.is_file():
        sys.exit("NODE STAGING FAILED")
    return node


def npm(node: Path, args: list[str], cwd: Path) -> None:
    npm_cli = node.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    env = dict(os.environ)
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    run([node, npm_cli, *args, "--no-audit", "--no-fund"], cwd=cwd, env=env)


def stage_hyperframes(node: Path) -> None:
    target = RUNTIME / "hyperframes"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / "package.json").write_text(json.dumps({
        "name": "apf-hyperframes-runtime", "private": True,
        "dependencies": {"hyperframes": HYPERFRAMES_VERSION},
    }, indent=2), encoding="utf-8")
    npm(node, ["install", "--omit=dev"], cwd=target)


def stage_narova(node: Path) -> None:
    source = REPO / "third_party" / "narova"
    target = RUNTIME / "narova"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ("LICENSE", "README.md"):
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)
    shutil.copytree(
        source / "tool", target / "tool",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", "evals", "live-tests", "tests"),
    )
    lock = target / "tool" / "package-lock.json"
    npm(node, ["ci" if lock.is_file() else "install", "--omit=dev"], cwd=target / "tool")


def stage_ffmpeg() -> dict:
    archive = download(FFMPEG_URL, f"ffmpeg-{FFMPEG_VERSION}-essentials_build.zip")
    target = RUNTIME / "ffmpeg"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            base = name.rsplit("/", 1)[-1]
            if name.endswith("/bin/ffmpeg.exe") or name.endswith("/bin/ffprobe.exe"):
                (target / base).write_bytes(zf.read(info))
            elif base in ("LICENSE", "README.txt") and name.count("/") == 1:
                (target / f"license-{base}").write_bytes(zf.read(info))
    ffmpeg = target / "ffmpeg.exe"
    if not ffmpeg.is_file() or not (target / "ffprobe.exe").is_file():
        sys.exit("FFMPEG STAGING FAILED")
    version_line = run([ffmpeg, "-version"]).splitlines()[0]
    return {"version": FFMPEG_VERSION, "source": FFMPEG_URL, "version_line": version_line,
            "ffmpeg_sha256": sha256_file(ffmpeg), "ffprobe_sha256": sha256_file(target / "ffprobe.exe")}


def stage_whisper() -> dict:
    target = RUNTIME / "models" / "whisper" / "base.en"
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, expected in WHISPER_FILES.items():
        path = download(WHISPER_BASE + name, f"whisper-base.en-{name}")
        actual = sha256_file(path)
        if actual != expected:
            sys.exit(f"WHISPER CHECKSUM MISMATCH for {name}: {actual} != {expected}")
        shutil.copy2(path, target / name)
        hashes[name] = actual
    return {"model": "Systran/faster-whisper-base.en", "revision": WHISPER_REVISION, "sha256": hashes}


def stage_installers() -> dict:
    out = {}
    for folder, url, name in (
        ("webview2", WEBVIEW2_URL, "MicrosoftEdgeWebview2Setup.exe"),
        ("vcredist", VCREDIST_URL, "vc_redist.x64.exe"),
    ):
        path = download(url, name)
        dest = RUNTIME / folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest / name)
        out[folder] = {"source": url, "sha256": sha256_file(dest / name)}
    return out


def ensure_inno_setup() -> None:
    iscc = Path(r"C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
    if iscc.is_file():
        return
    choco = shutil.which("choco")
    if not choco:
        sys.exit("Inno Setup 6 is not installed and Chocolatey is unavailable")
    run([choco, "install", "innosetup", "-y", "--no-progress"])
    if not iscc.is_file():
        sys.exit(f"Inno Setup install did not produce {iscc}")


def main() -> None:
    if sys.platform != "win32":
        sys.exit("assemble_windows_staging.py must run on Windows")
    STAGING.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "LICENSE", STAGING / "LICENSE")
    shutil.copy2(REPO / "release" / "THIRD_PARTY_NOTICES.txt", STAGING / "THIRD_PARTY_NOTICES.txt")

    python = stage_python()
    node = stage_node()
    stage_hyperframes(node)
    stage_narova(node)
    ffmpeg_info = stage_ffmpeg()
    whisper_info = stage_whisper()
    installer_info = stage_installers()
    ensure_inno_setup()

    sys.path.insert(0, str(REPO / "src"))
    from voice_flow._version import VERSION

    freeze = run([python, "-m", "pip", "freeze"]).splitlines()
    manifest = {
        "product": "AI Productivity Flow",
        "version": VERSION,
        "build_script": "release/assemble_windows_staging.py + release/build_windows_release.py",
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": {"version": PYTHON_VERSION, "source": PYTHON_URL, "packages": freeze},
        "node": {"version": NODE_VERSION, "source": NODE_URL, "node_sha256": sha256_file(node)},
        "hyperframes": {"version": HYPERFRAMES_VERSION, "license": "Apache-2.0"},
        "narova": {"source": "third_party/narova (vendored, MIT)"},
        "code2video": {"source": "third_party/code2video (vendored, MIT)"},
        "ffmpeg": ffmpeg_info,
        "whisper": whisper_info,
        "render_browser": "provisioned at install time by `hyperframes browser ensure` (not redistributed)",
        **installer_info,
    }
    (RUNTIME / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"staging ready at {STAGING} ({len(freeze)} Python packages)")


if __name__ == "__main__":
    main()
