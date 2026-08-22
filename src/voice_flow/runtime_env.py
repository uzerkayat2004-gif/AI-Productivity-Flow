"""Central runtime path resolution: development vs installed application.

The installed application owns every runtime component it needs:

    <install_root>/
        app/                     # this Python package tree (site-packages style)
        runtime/
            python/              # private CPython (python.exe / pythonw.exe)
            node/                # private Node.js
            ffmpeg/              # ffmpeg.exe / ffprobe.exe
            browser/             # Chrome for Testing (HyperFrames rendering)
            models/whisper/base.en/
            narova/              # vendored Narova tool (JS CLI + modules)
            code2video/          # vendored Code2Video prompts
            runtime-manifest.json

In development the same modules resolve from the repository (``third_party``)
and the system PATH. Nothing here mutates the system PATH; callers receive
absolute paths and use them explicitly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_MANIFEST_NAME = "runtime-manifest.json"


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get("AI_PRODUCTIVITY_FLOW_ROOT", "").strip()
    if override:
        roots.append(Path(override).expanduser().resolve())
    # voice_flow/runtime_env.py -> package dir -> app dir -> install root
    package_parent = Path(__file__).resolve().parents[2]
    roots.extend(parent for parent in package_parent.parents)
    return roots


def install_root() -> Path | None:
    """The installed application root, or None when running from source."""
    for root in _candidate_roots():
        if (root / "runtime" / _MANIFEST_NAME).is_file():
            return root
    return None


def is_installed() -> bool:
    return install_root() is not None


def runtime_root() -> Path | None:
    root = install_root()
    return (root / "runtime") if root else None


def _runtime_binary(subdir: str, name: str) -> Path | None:
    runtime = runtime_root()
    if runtime is None:
        return None
    candidate = runtime / subdir / name
    return candidate if candidate.is_file() else None


def python_executable() -> str:
    """Best silent interpreter for this application (installed: private)."""
    runtime = runtime_root()
    if runtime is not None:
        bundled = runtime / "python" / "python.exe"
        if bundled.is_file():
            return str(bundled)
    return sys.executable


def pythonw_executable() -> str | None:
    """Windowless interpreter, or None when the caller should fall back."""
    runtime = runtime_root()
    if runtime is not None:
        bundled = runtime / "python" / "pythonw.exe"
        if bundled.is_file():
            return str(bundled)
        return None
    return None


def node_executable() -> Path | None:
    return _runtime_binary("node", "node.exe")


def ffmpeg_executable() -> Path | None:
    return _runtime_binary("ffmpeg", "ffmpeg.exe")


def ffprobe_executable() -> Path | None:
    return _runtime_binary("ffmpeg", "ffprobe.exe")


def whisper_model_path() -> Path | None:
    """Bundled faster-whisper base.en model, when installed."""
    runtime = runtime_root()
    if runtime is None:
        return None
    model = runtime / "models" / "whisper" / "base.en"
    required = model / "model.bin"
    return model if required.is_file() else None


def browser_executable() -> Path | None:
    """Bundled Chrome for Testing executable, when installed."""
    runtime = runtime_root()
    if runtime is None:
        return None
    browser_dir = runtime / "browser"
    if not browser_dir.is_dir():
        return None
    for pattern in ("chrome-win64/chrome.exe", "chrome-win/chrome.exe", "chrome.exe"):
        candidate = browser_dir / pattern
        if candidate.is_file():
            return candidate
    return None


def narova_tool_root() -> Path | None:
    """Vendored Narova tool root (contains tool/bin/narova.js)."""
    runtime = runtime_root()
    if runtime is not None:
        root = runtime / "narova"
        return root if (root / "tool" / "bin" / "narova.js").is_file() else None
    dev = Path(__file__).resolve().parents[2] / "third_party" / "narova"
    return dev if (dev / "tool" / "bin" / "narova.js").is_file() else None


def code2video_root() -> Path | None:
    """Vendored Code2Video root (contains prompts/)."""
    runtime = runtime_root()
    if runtime is not None:
        root = runtime / "code2video"
        return root if (root / "prompts").is_dir() else None
    dev = Path(__file__).resolve().parents[2] / "third_party" / "code2video"
    return dev if (dev / "prompts").is_dir() else None


def render_browser_cache() -> Path | None:
    """Per-user chrome-headless-shell cache (provisioned via HyperFrames)."""
    home = Path.home()
    for base in (home / ".cache" / "hyperframes" / "chrome" / "chrome-headless-shell",
                 home / ".cache" / "puppeteer" / "chrome-headless-shell"):
        if base.is_dir():
            for exe in base.rglob("chrome-headless-shell.exe"):
                return exe
    return None


def ensure_render_browser(log=None) -> bool:
    """Provision the pinned render browser if missing (HyperFrames' official
    command; downloads from Google's Chrome for Testing endpoints)."""
    if render_browser_cache() is not None or browser_executable() is not None:
        return True
    node = node_executable()
    runtime = runtime_root()
    if node is None or runtime is None:
        return False
    cli = runtime / "hyperframes" / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    if not cli.is_file():
        return False
    import subprocess

    try:
        subprocess.run(
            [str(node), str(cli), "browser", "ensure"],
            capture_output=True, text=True, timeout=900,
        )
    except Exception as exc:
        if log:
            log(f"render browser provisioning failed: {exc}")
        return False
    return render_browser_cache() is not None


def preflight_problems() -> list[str]:
    """Missing/unusable packaged components (empty list = healthy)."""
    runtime = runtime_root()
    if runtime is None:
        return []
    problems: list[str] = []
    checks = {
        "python-runtime": runtime / "python" / "pythonw.exe",
        "node-runtime": runtime / "node" / "node.exe",
        "ffmpeg": runtime / "ffmpeg" / "ffmpeg.exe",
        "ffprobe": runtime / "ffmpeg" / "ffprobe.exe",
        "speech-model": runtime / "models" / "whisper" / "base.en" / "model.bin",
    }
    # The render browser is provisioned per user (not packaged): healthy when
    # the cache OR a bundled copy exists; otherwise auto-provisionable.
    if browser_executable() is None and render_browser_cache() is None:
        problems.append("render-browser")
    for label, path in checks.items():
        if path is None or not Path(path).is_file():
            problems.append(label)
    return problems
