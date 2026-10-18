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
import threading
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


def _mac_resources_dir() -> Path:
    """``Contents/Resources`` when this package runs from the macOS .app."""
    return Path(__file__).resolve().parents[2]


def mac_bundle_runtime_dir() -> Path | None:
    """``Contents/Resources/runtime`` of the macOS .app this code runs from.

    The .app layout differs from the Windows install root: this package lives
    in ``Contents/Resources/src/voice_flow`` and the runtime (Python,
    llama-server, NeMo-Speech) in ``Contents/Resources/runtime`` with a
    ``build-manifest.json``. None when not running from a macOS bundle.
    """
    if sys.platform != "darwin":
        return None
    runtime = _mac_resources_dir() / "runtime"
    return runtime if (runtime / "build-manifest.json").is_file() else None


def mac_bundled_llama_server() -> Path | None:
    """The llama-server shipped inside the macOS .app (S1-mini polish), if any."""
    runtime = mac_bundle_runtime_dir()
    if runtime is None:
        return None
    candidate = runtime / "llama" / "llama-server"
    return candidate if candidate.is_file() else None


def mac_bundled_nemo_speech_dylib() -> Path | None:
    """The NeMo-Speech C ABI dylib shipped inside the macOS .app (Nemotron), if any."""
    runtime = mac_bundle_runtime_dir()
    if runtime is None:
        return None
    candidate = runtime / "nemo" / "lib" / "libnemo_speech_asr_c.dylib"
    return candidate if candidate.is_file() else None


def native_worker_python() -> str:
    """Interpreter for the isolated native speech worker.

    On macOS ``sys.executable`` is the app launcher; started with ``-I`` it
    ignores PYTHONHOME and cannot find the standard library, so the worker
    uses the bundled ``python3`` binary instead (it locates its stdlib from
    its own path). Everywhere else this is ``python_executable()``.
    """
    runtime = mac_bundle_runtime_dir()
    if runtime is not None:
        bundled = runtime / "python" / "bin" / "python3"
        if bundled.is_file():
            return str(bundled)
    return python_executable()


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


def _mac_app_runtime_root() -> Path | None:
    """``Contents/Resources/runtime`` of the macOS ``.app``, when running from it.

    The Mac bundle marks its runtime with ``build-manifest.json`` (not
    ``runtime-manifest.json``), so ``runtime_root()`` stays None there and a
    Mac bundle is never treated as a Windows install. Only bundle-shipped
    data (the Whisper model) is resolved through this.
    """
    candidates: list[Path] = []
    override = os.environ.get("AI_PRODUCTIVITY_FLOW_ROOT", "").strip()
    if override:
        candidates.append(Path(override).expanduser().resolve())
    package_root = Path(__file__).resolve().parents[2]
    candidates.append(package_root)
    candidates.extend(package_root.parents)
    for root in candidates:
        runtime = root / "runtime"
        if (runtime / "build-manifest.json").is_file():
            return runtime
    return None


def whisper_model_path() -> Path | None:
    """Bundled faster-whisper base.en model, when installed.

    Windows: ``<install>/runtime/models/whisper/base.en``. macOS ``.app``:
    ``Contents/Resources/runtime/models/whisper/base.en`` (shipped in the DMG
    so the first dictation never downloads anything).
    """
    runtime = runtime_root()
    if runtime is None and sys.platform == "darwin":
        runtime = _mac_app_runtime_root()
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


def _prompts_ready(root: Path) -> bool:
    return (root / "prompts").is_dir()


def code2video_root() -> Path | None:
    """Vendored Code2Video root (contains prompts/).

    Windows installs keep the vendor at ``runtime/code2video`` next to
    ``runtime-manifest.json``. The macOS ``.app`` writes
    ``runtime/build-manifest.json`` and copies the vendor to
    ``Resources/third_party/code2video``. That Mac manifest is accepted here
    only. ``install_root()`` still requires ``runtime-manifest.json`` so a
    Mac bundle is not treated as a Windows install (it does not ship the
    private ffmpeg, Node, or HyperFrames tree).
    """
    runtime = runtime_root()
    if runtime is not None:
        bundled = runtime / "code2video"
        if _prompts_ready(bundled):
            return bundled
        beside = runtime.parent / "third_party" / "code2video"
        if _prompts_ready(beside):
            return beside

    seen: set[Path] = set()
    candidates: list[Path] = []
    override = os.environ.get("AI_PRODUCTIVITY_FLOW_ROOT", "").strip()
    if override:
        candidates.append(Path(override).expanduser().resolve())
    package_root = Path(__file__).resolve().parents[2]
    candidates.append(package_root)
    candidates.extend(package_root.parents)
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        if (root / "runtime" / "build-manifest.json").is_file():
            vendor = root / "third_party" / "code2video"
            if _prompts_ready(vendor):
                return vendor

    dev = Path(__file__).resolve().parents[2] / "third_party" / "code2video"
    return dev if _prompts_ready(dev) else None


def render_browser_cache() -> Path | None:
    """Per-user chrome-headless-shell cache (provisioned via HyperFrames)."""
    home = Path.home()
    for base in (home / ".cache" / "hyperframes" / "chrome" / "chrome-headless-shell",
                 home / ".cache" / "puppeteer" / "chrome-headless-shell"):
        if base.is_dir():
            for exe in base.rglob("chrome-headless-shell.exe"):
                return exe
    return None


# One provisioning run at a time: the background prefetch and a render that
# needs the browser must not download it twice.
_RENDER_BROWSER_LOCK = threading.Lock()
_RENDER_BROWSER_PREFETCH_SCHEDULED = False
# The installer used to run `hyperframes browser ensure` (a ~150 MB Chrome
# download plus thousands of files for Defender to scan) in parallel with the
# first launch of the app. It is now done in the background this long after
# the engine is ready, at idle priority, or on demand by the first render.
RENDER_BROWSER_PREFETCH_DELAY_SECONDS = 600.0


def ensure_render_browser(log=None, *, background: bool = False) -> bool:
    """Provision the pinned render browser if missing (HyperFrames' official
    command; downloads from Google's Chrome for Testing endpoints).

    ``background=True`` runs the download at idle (Windows) or nice +10
    (POSIX) priority. Either way no console window opens.
    """
    if render_browser_cache() is not None or browser_executable() is not None:
        return True
    # HyperFrames needs Node 22. From 1.0.8 the Windows installer bundles
    # Node 20 (so v1.0.6 installs keep getting the small app update) and the
    # app downloads Node 22 into the user data folder; get it first.
    from voice_flow import node_component

    try:
        node_component.ensure_managed_node(background=background)
    except node_component.NodeComponentError as exc:
        if log:
            log(f"render browser provisioning skipped: {exc}")
        return False
    node = node_component.video_node_executable()
    runtime = runtime_root()
    if node is None or runtime is None:
        return False
    cli = runtime / "hyperframes" / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    if not cli.is_file():
        return False
    import subprocess

    with _RENDER_BROWSER_LOCK:
        if render_browser_cache() is not None:
            return True
        kwargs: dict = {"capture_output": True, "text": True, "timeout": 900}
        if sys.platform == "win32":
            from voice_flow.startup_priority import IDLE_PRIORITY_CLASS

            flags = 0x08000000  # CREATE_NO_WINDOW: node.exe is a console app
            if background:
                flags |= IDLE_PRIORITY_CLASS
            kwargs["creationflags"] = flags
        elif background:
            from voice_flow.startup_priority import background_preexec

            kwargs["preexec_fn"] = background_preexec()
        try:
            subprocess.run([str(node), str(cli), "browser", "ensure"], **kwargs)
        except Exception as exc:
            if log:
                log(f"render browser provisioning failed: {exc}")
            return False
    return render_browser_cache() is not None


def schedule_render_browser_prefetch(delay_seconds: float | None = None) -> bool:
    """Prepare Video Flow's Node 22 and render browser later, in the background.

    Only for the installed Windows app, once per process, and only when one
    of them is missing. Returns True when a prefetch was scheduled.
    """
    global _RENDER_BROWSER_PREFETCH_SCHEDULED
    if sys.platform != "win32" or not is_installed():
        return False
    if os.environ.get("VOICE_FLOW_RENDER_BROWSER_PREFETCH", "1").strip().lower() in ("0", "off", "false", "no"):
        return False
    if _RENDER_BROWSER_PREFETCH_SCHEDULED:
        return False
    from voice_flow import node_component

    need_node = node_component.needs_managed_node() and node_component.managed_node_executable() is None
    need_browser = render_browser_cache() is None and browser_executable() is None
    if not need_node and not need_browser:
        return False
    _RENDER_BROWSER_PREFETCH_SCHEDULED = True
    delay = RENDER_BROWSER_PREFETCH_DELAY_SECONDS if delay_seconds is None else float(delay_seconds)

    def _prefetch() -> None:
        # Node 22 first (HyperFrames needs it for `browser ensure`), both idle.
        if need_node and not node_component.prefetch_managed_node():
            return
        if need_browser:
            ensure_render_browser(background=True)

    timer = threading.Timer(delay, _prefetch)
    timer.daemon = True
    timer.name = "apf-render-browser-prefetch"
    timer.start()
    return True


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
