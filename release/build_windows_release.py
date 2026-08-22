"""Build the AI Productivity Flow single-file Windows installer.

Orchestrates: staging assembly (from the prepared build cache) -> staging
preflight -> Inno Setup compile -> SHA256. Run on the build machine after
download_runtimes.py and build_python_runtime.py.

    python release/build_windows_release.py

Output: dist/AI-Productivity-Flow-Setup-x64.exe + .sha256
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = Path(r"C:/Users/Asus/apf-release-build")
STAGING = BUILD / "staging"
DIST = REPO / "dist"
ISCC = Path(r"C:/Program Files (x86)/Inno Setup 6/ISCC.exe")


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


def build_installer() -> Path:
    DIST.mkdir(exist_ok=True)
    iss = REPO / "release" / "installer" / "apf-setup.iss"
    result = subprocess.run(
        [str(ISCC), f"/DSTAGING_ROOT={STAGING}", f"/DDIST_ROOT={DIST}", str(iss)],
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
