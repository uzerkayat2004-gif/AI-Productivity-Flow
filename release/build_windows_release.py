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
