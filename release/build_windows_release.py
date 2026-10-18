"""Build the AI Productivity Flow single-file Windows installer.

Orchestrates: staging assembly (from the prepared build cache) -> staging
preflight -> Inno Setup compile -> SHA256. Run on the build machine after
download_runtimes.py and build_python_runtime.py.

    python release/build_windows_release.py

Output: dist/AI-Productivity-Flow-Setup-x64.exe + .sha256
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get("APF_BUILD_DIR", Path.home() / "apf-release-build"))
STAGING = BUILD / "staging"
DIST = REPO / "dist"
ISCC = Path(r"C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
NOTEBOOKLM_PACKAGE = "notebooklm-py[browser,mcp]==0.8.2"


def notebooklm_runtime_executables(runtime: Path) -> list[Path]:
    """NotebookLM console scripts required by the packaged private Python."""
    scripts = runtime / "python" / "Scripts"
    return [scripts / "notebooklm.exe", scripts / "notebooklm-mcp.exe"]


def ensure_notebooklm_runtime(staging: Path) -> bool:
    """Provision NotebookLM into the staging private Python when needed.

    This is deliberately a build-time operation. It never touches the build
    machine's global Python or a user's environment, and it never runs from the
    application sign-in path. Returns True when a provision step was run.
    """
    runtime = staging / "runtime"
    required = notebooklm_runtime_executables(runtime)
    if all(path.is_file() for path in required):
        return False

    python = runtime / "python" / "python.exe"
    if not python.is_file():
        sys.exit(
            "NOTEBOOKLM RUNTIME PROVISION FAILED — staging private Python is missing: "
            f"{python}"
        )

    uv = shutil.which("uv")
    if uv:
        command = [uv, "pip", "install", "--python", str(python), NOTEBOOKLM_PACKAGE]
    else:
        command = [str(python), "-m", "pip", "install", NOTEBOOKLM_PACKAGE]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "")[-2000:]
        sys.exit(
            "NOTEBOOKLM RUNTIME PROVISION FAILED — could not install "
            f"{NOTEBOOKLM_PACKAGE} into {python}.\n{output}"
        )

    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        sys.exit(
            "NOTEBOOKLM RUNTIME PROVISION FAILED — package installation completed "
            "but required console scripts are missing:\n  " + "\n  ".join(missing)
        )
    print("NotebookLM runtime provisioned in staging private Python")
    return True


def refresh_code2video_vendor(staging: Path) -> None:
    """Re-sync vendored Code2Video into staging without secrets or bytecode."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from scripts.bundle_code2video import copy_code2video

    source = REPO / "third_party" / "code2video"
    if not source.is_dir():
        sys.exit(f"CODE2VIDEO VENDOR MISSING — expected {source}")
    destination = staging / "runtime" / "code2video"
    copy_code2video(source, destination)
    prompt = destination / "prompts" / "stage1.py"
    if not prompt.is_file():
        sys.exit(f"CODE2VIDEO VENDOR COPY FAILED — missing {prompt}")
    print(f"Code2Video vendor synced to {destination}")


def ensure_openai_runtime(staging: Path) -> None:
    """Install openai into the staging private Python when it is missing.

    Code2Video's vendored gpt_request.py imports the official client. Shipping
    that dependency in the private interpreter keeps the Windows installer on
    the same contract as the macOS bundle, which installs requirements.txt.
    """
    python = staging / "runtime" / "python" / "python.exe"
    if not python.is_file():
        sys.exit(
            "OPENAI RUNTIME PROVISION FAILED — staging private Python is missing: "
            f"{python}"
        )
    probe = subprocess.run(
        [str(python), "-c", "import openai"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        print("openai already importable in staging private Python")
        return

    package = "openai>=1.40.0,<3"
    uv = shutil.which("uv")
    if uv:
        command = [uv, "pip", "install", "--python", str(python), package]
    else:
        command = [str(python), "-m", "pip", "install", package]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "")[-2000:]
        sys.exit(
            "OPENAI RUNTIME PROVISION FAILED — could not install "
            f"{package} into {python}.\n{output}"
        )
    print("openai provisioned in staging private Python")


def refresh_app_package(staging: Path) -> None:
    """Re-sync the app package from the repo so the installer always carries
    the current source (the python runtime snapshot may predate edits)."""
    import shutil

    site = staging / "runtime" / "python" / "Lib" / "site-packages"
    dst = site / "voice_flow"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(REPO / "src" / "voice_flow", dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    check = subprocess.run(
        [str(staging / "runtime" / "python" / "python.exe"), "-c",
         "import voice_flow.runtime_env as r; print('installed =', r.is_installed()); "
         "print('voice_flow OK')"],
        capture_output=True, text=True,
    )
    print(check.stdout.strip())
    if check.returncode != 0:
        sys.exit("voice_flow import check failed in staging:\n" + check.stderr[-1500:])


# --- Install-size and first-launch work --------------------------------------
# The v1.0.4 installer wrote 33,157 files (1.7 GB). Windows Defender scans each
# new file, so on a modest laptop the file count, not the byte count, decides
# how long "Installing..." takes. These files are never used at runtime.
_PRUNE_DIR_NAMES = {"tests", "test", "SelfTest"}  # inside third-party packages only
_PRUNE_SUFFIXES = (".pyi", ".map", ".d.ts", ".d.mts", ".d.cts")
_KEEP_DOC_PREFIXES = ("license", "licence", "notice", "copying", "authors", "patents", "third")
# Packages whose tests folders are real runtime modules. None known today;
# listed here so a future exception is one line.
_PRUNE_KEEP_PACKAGES: set[str] = set()


def _site_packages(staging: Path) -> Path:
    return staging / "runtime" / "python" / "Lib" / "site-packages"


def prune_staging_for_install(staging: Path) -> dict:
    """Delete files the app never loads: package test suites, type stubs,
    source maps, TypeScript declarations and non-license Markdown in the Node
    trees. Licenses and notices are always kept. Safe to run more than once.
    pip and the C headers are left in staging (later build steps may need
    them) and are excluded from the installer by apf-setup.iss instead.
    """
    removed = {"test_dirs": 0, "files": 0}
    runtime = staging / "runtime"
    site = _site_packages(staging)
    if site.is_dir():
        for package in sorted(p for p in site.iterdir() if p.is_dir()):
            if package.name in _PRUNE_KEEP_PACKAGES or package.name == "voice_flow":
                continue
            for folder in sorted(package.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if folder.is_dir() and folder.name in _PRUNE_DIR_NAMES and folder.exists():
                    removed["files"] += sum(1 for f in folder.rglob("*") if f.is_file())
                    shutil.rmtree(folder, ignore_errors=True)
                    removed["test_dirs"] += 1
    for path in list(runtime.rglob("*")) if runtime.is_dir() else []:
        if not path.is_file():
            continue
        name = path.name.lower()
        drop = name.endswith(_PRUNE_SUFFIXES)
        if not drop and name.endswith((".md", ".markdown")) and "node_modules" in path.parts:
            drop = not name.startswith(_KEEP_DOC_PREFIXES)
        if drop:
            try:
                path.unlink()
                removed["files"] += 1
            except OSError:
                pass
    print(f"Pruned staging: {removed['test_dirs']} test folders, {removed['files']} files removed")
    return removed


def compileall_commands(python: Path, staging: Path) -> list[list[str]]:
    """compileall runs that ship bytecode with the installer.

    Up to 1.0.6 the app package was copied without .pyc files, so the first
    launch compiled ~150 voice_flow modules (and parts of the stdlib) in two
    processes at once, each new .pyc being written and scanned. The macOS
    build already precompiles (scripts/build_macos_app.py).
    - stdlib + third party: default timestamp mode; Inno Setup keeps file
      times, and up-to-date .pyc files from pip are skipped.
    - voice_flow and narova_tts: checked-hash, so the .pyc stays valid when
      an app-only update or a zip changes file times, and is never used
      for a source file whose content changed.
    """
    lib = staging / "runtime" / "python" / "Lib"
    site = _site_packages(staging)
    commands = [[str(python), "-m", "compileall", "-q", "-j", "0", str(lib)]]
    own = [str(site / name) for name in ("voice_flow", "narova_tts") if (site / name).is_dir()]
    if own:
        commands.append([str(python), "-m", "compileall", "-q", "-f", "-j", "0",
                         "--invalidation-mode", "checked-hash", *own])
    return commands


def precompile_runtime_bytecode(staging: Path) -> None:
    python = staging / "runtime" / "python" / "python.exe"
    if not python.is_file():
        sys.exit(f"BYTECODE PRECOMPILE FAILED — staging private Python is missing: {python}")
    for command in compileall_commands(python, staging):
        result = subprocess.run(command, capture_output=True, text=True)
        # A few third-party fixtures are intentionally invalid Python; compileall
        # then exits 1 but still compiles everything else.
        print(f"compileall exit {result.returncode}: {' '.join(command[3:6])}...")
    site = _site_packages(staging)
    compiled = list((site / "voice_flow").rglob("*.cpython-312.pyc"))
    if len(compiled) < 50:
        sys.exit(f"BYTECODE PRECOMPILE FAILED — only {len(compiled)} voice_flow .pyc files")
    print(f"Precompiled bytecode ({len(compiled)} voice_flow modules)")


def preflight(staging: Path) -> None:
    runtime = staging / "runtime"
    required = [
        runtime / "python" / "pythonw.exe",
        *notebooklm_runtime_executables(runtime),
        runtime / "python" / "Lib" / "site-packages" / "voice_flow" / "main.py",
        runtime / "python" / "Lib" / "site-packages" / "narova_tts" / "pipeline.py",
        runtime / "node" / "node.exe",
        runtime / "ffmpeg" / "ffmpeg.exe",
        runtime / "ffmpeg" / "ffprobe.exe",
        runtime / "hyperframes" / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs",
        runtime / "narova" / "tool" / "bin" / "narova.js",
        runtime / "narova" / "tool" / "src" / "hf.js",
        runtime / "code2video" / "prompts" / "stage1.py",
        runtime / "models" / "whisper" / "base.en" / "model.bin",
        runtime / "webview2" / "MicrosoftEdgeWebview2Setup.exe",
        runtime / "vcredist" / "vc_redist.x64.exe",
        runtime / "runtime-manifest.json",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        sys.exit("STAGING PREFLIGHT FAILED — missing:\n  " + "\n  ".join(missing))
    print("staging preflight OK ({} components)".format(len(required)))

    # Preflight the vendored hf.js still parses under the bundled node.
    node = str(runtime / "node" / "node.exe")
    check = subprocess.run([node, "--check", str(runtime / "narova" / "tool" / "src" / "hf.js")],
                           capture_output=True, text=True)
    if check.returncode != 0:
        sys.exit("hf.js syntax check failed under bundled node:\n" + check.stderr[-800:])
    print("hf.js syntax OK under bundled node")

    # Preflight runtime Python dependencies are present and importable.
    python = str(runtime / "python" / "python.exe")
    check_deps = subprocess.run(
        [python, "-c", "import requests, webview, sounddevice, faster_whisper, edge_tts, cryptography, websockets, notebooklm, openai; print('runtime dependencies OK')"],
        capture_output=True, text=True,
    )
    if check_deps.returncode != 0:
        sys.exit("runtime python dependencies verification failed in staging:\n" + check_deps.stderr[-800:])
    print("runtime python dependencies verified in staging")


def build_installer() -> Path:
    DIST.mkdir(exist_ok=True)
    iss = REPO / "release" / "installer" / "apf-setup.iss"
    result = subprocess.run(
        [str(ISCC), f"/DREPO_ROOT={REPO}", f"/DSTAGING_ROOT={STAGING}", f"/DDIST_ROOT={DIST}", str(iss)],
        capture_output=True, text=True,
    )
    print(result.stdout[-2000:])
    if result.returncode != 0:
        sys.exit("ISCC failed:\n" + result.stderr[-2000:])
    return DIST / "AI-Productivity-Flow-Setup-x64.exe"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    refresh_app_package(STAGING)
    refresh_code2video_vendor(STAGING)
    ensure_notebooklm_runtime(STAGING)
    ensure_openai_runtime(STAGING)
    prune_staging_for_install(STAGING)
    precompile_runtime_bytecode(STAGING)
    preflight(STAGING)
    installer = build_installer()
    size_mb = installer.stat().st_size / (1024 * 1024)
    digest = sha256_file(installer)
    (installer.with_suffix(".exe.sha256")).write_text(
        f"{digest}  AI-Productivity-Flow-Setup-x64.exe\n", encoding="utf-8")
    print(f"INSTALLER OK: {installer} ({size_mb:.1f} MB)")
    print(f"sha256: {digest}")


if __name__ == "__main__":
    main()
