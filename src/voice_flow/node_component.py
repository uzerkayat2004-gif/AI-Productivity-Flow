"""Node.js 22 for Video Flow, as an app-managed download (Windows).

HyperFrames 0.7.96 refuses to start on Node < 22. v1.0.7 fixed that by
bundling Node 22.23.3 in the installer, but that changed the bundled runtime
fingerprint, so every v1.0.6 install was offered the full 527 MB installer
instead of the ~50 MB app update.

From 1.0.8 the installer keeps bundling Node 20.18.1 (the version every
v1.0.6 install already has) and the app fetches the pinned Node 22 win-x64
zip into the user data folder when it is needed:

* in the background at idle priority some minutes after start-up, chained
  in front of the render browser prefetch, or
* on demand before the first full-fidelity (HyperFrames) render.

The zip is SHA-256 pinned (same pin as release/assemble_windows_staging.py
used for v1.0.7). Nothing here touches the install folder or the system PATH,
and nothing raises past :func:`ensure_managed_node` except
:class:`NodeComponentError`, whose message is safe to show the user.

macOS does not bundle Node, and development runs use the system Node, so on
those this module reports ``not_needed`` and does nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# Pinned download. From https://nodejs.org/dist/v22.23.3/SHASUMS256.txt
MANAGED_NODE_VERSION = "22.23.3"
MANAGED_NODE_ARCHIVE = f"node-v{MANAGED_NODE_VERSION}-win-x64.zip"
MANAGED_NODE_URL = f"https://nodejs.org/dist/v{MANAGED_NODE_VERSION}/{MANAGED_NODE_ARCHIVE}"
MANAGED_NODE_SHA256 = "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"
MANAGED_NODE_TOP_DIR = f"node-v{MANAGED_NODE_VERSION}-win-x64"
# hyperframes@0.7.96 package.json: "engines": {"node": ">=22"}.
HYPERFRAMES_MIN_NODE_MAJOR = 22
# Same delay as the render browser prefetch (runtime_env).
NODE_PREFETCH_DELAY_SECONDS = 600.0
_MARKER = "component.json"
_MAX_ARCHIVE_BYTES = 200 * 1024 * 1024  # the real zip is ~34 MB

_LOCK = threading.Lock()
_STATUS_LOCK = threading.Lock()
_STATUS: dict[str, Any] = {
    "state": "unknown",
    "version": MANAGED_NODE_VERSION,
    "downloaded_bytes": 0,
    "total_bytes": None,
    "error": "",
}


class NodeComponentError(RuntimeError):
    """A failure with a message that can be shown to the user as-is."""


def _set_status(**fields: Any) -> None:
    with _STATUS_LOCK:
        _STATUS.update(fields)


def _version_tuple(text: str | None) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in str(text or "").strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def components_root() -> Path:
    from voice_flow.paths import data_dir

    return data_dir() / "components"


def managed_node_dir() -> Path:
    return components_root() / "node" / MANAGED_NODE_VERSION


def managed_node_executable() -> Path | None:
    """The downloaded Node 22, when it is complete and matches the pin."""
    folder = managed_node_dir()
    exe = folder / "node.exe"
    marker = folder / _MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != MANAGED_NODE_VERSION or data.get("archive_sha256") != MANAGED_NODE_SHA256:
        return None
    return exe if exe.is_file() else None


def bundled_node_version() -> str:
    """Node version the installer put in ``runtime/node`` ("" when none)."""
    from voice_flow import runtime_env

    runtime = runtime_env.runtime_root()
    if runtime is None:
        return ""
    try:
        data = json.loads((runtime / "runtime-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        node = data.get("node")
        if isinstance(node, dict) and node.get("version"):
            return str(node["version"])
        block = data.get("runtime")
        if isinstance(block, dict) and block.get("node"):
            return str(block["node"])
    from voice_flow.bundled_runtime import WINDOWS_NODE

    return WINDOWS_NODE


def needs_managed_node() -> bool:
    """True on an installed Windows app whose bundled Node is too old for HyperFrames."""
    if sys.platform != "win32":
        return False
    from voice_flow import runtime_env

    if not runtime_env.is_installed():
        return False
    version = _version_tuple(bundled_node_version())
    return not version or version[0] < HYPERFRAMES_MIN_NODE_MAJOR


def video_node_executable() -> Path | None:
    """Node for Narova / HyperFrames: the managed Node 22 when the bundled one is too old."""
    from voice_flow import runtime_env

    if needs_managed_node():
        managed = managed_node_executable()
        if managed is not None:
            return managed
    return runtime_env.node_executable()


def component_status() -> dict[str, Any]:
    """Plain status for the UI/API. Wording is left to the front end."""
    needed = needs_managed_node()
    ready = managed_node_executable() is not None
    with _STATUS_LOCK:
        status = dict(_STATUS)
    if not needed:
        status["state"] = "not_needed"
    elif ready:
        status["state"] = "ready"
    elif status.get("state") not in ("downloading", "failed"):
        status["state"] = "missing"
    status["needed"] = needed
    status["ready"] = ready or not needed
    status["bundled_version"] = bundled_node_version()
    return status


def _lower_current_thread_priority() -> None:
    """Background mode for this thread on Windows (CPU and I/O)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        THREAD_MODE_BACKGROUND_BEGIN = 0x00010000
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_MODE_BACKGROUND_BEGIN)
    except Exception:
        log.debug("Could not lower the Node download thread priority", exc_info=True)


def _restore_current_thread_priority() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        THREAD_MODE_BACKGROUND_END = 0x00020000
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_MODE_BACKGROUND_END)
    except Exception:
        pass


def _download(url: str, target: Path, progress: Callable[[int, int | None], None] | None,
              timeout: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Productivity-Flow"})
    done = 0
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as out:
        length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
        total = int(length) if length and str(length).isdigit() else None
        _set_status(total_bytes=total, downloaded_bytes=0)
        last = 0.0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if done > _MAX_ARCHIVE_BYTES:
                raise NodeComponentError("The Node.js download was larger than expected, so it was stopped.")
            now = time.monotonic()
            if now - last > 0.25:
                last = now
                _set_status(downloaded_bytes=done)
                if progress:
                    progress(done, total)
    _set_status(downloaded_bytes=done)
    if progress:
        progress(done, done)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(archive: Path, dest: Path) -> Path:
    """Extract the Node zip safely; returns the ``node-v…-win-x64`` folder."""
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ":" in name or ".." in Path(name).parts:
                raise NodeComponentError("The Node.js download had an unsafe file path, so it was not used.")
            target = (dest / name).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise NodeComponentError("The Node.js download had an unsafe file path, so it was not used.")
        bundle.extractall(dest)
    top = dest / MANAGED_NODE_TOP_DIR
    if not (top / "node.exe").is_file():
        raise NodeComponentError("The Node.js download did not contain node.exe.")
    return top


def ensure_managed_node(
    progress: Callable[[int, int | None], None] | None = None,
    *,
    background: bool = False,
    url: str = MANAGED_NODE_URL,
    expected_sha256: str = MANAGED_NODE_SHA256,
    timeout: float = 60.0,
    force: bool = False,
) -> Path | None:
    """Make sure Node 22 is available for Video Flow.

    Returns the managed ``node.exe``, or None when it is not needed (Mac,
    development, or a bundled Node that is already new enough). ``force``
    skips the need check (tests). Raises :class:`NodeComponentError` with a
    plain message on any failure; never anything else.
    """
    if not force and not needs_managed_node():
        return None
    existing = managed_node_executable()
    if existing is not None:
        _set_status(state="ready", error="")
        return existing
    if background:
        _lower_current_thread_priority()
    try:
        with _LOCK:
            existing = managed_node_executable()
            if existing is not None:
                _set_status(state="ready", error="")
                return existing
            return _install(progress, url=url, expected_sha256=expected_sha256, timeout=timeout)
    finally:
        if background:
            _restore_current_thread_priority()


def _install(progress, *, url: str, expected_sha256: str, timeout: float) -> Path:
    _set_status(state="downloading", error="", downloaded_bytes=0, total_bytes=None)
    root = components_root() / "node"
    work = root / f".download-{os.getpid()}-{threading.get_ident()}"
    try:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        archive = work / (MANAGED_NODE_ARCHIVE + ".part")
        try:
            _download(url, archive, progress, timeout)
        except NodeComponentError:
            raise
        except Exception as exc:
            log.info("Node.js %s download failed: %s", MANAGED_NODE_VERSION, exc)
            raise NodeComponentError(
                "Couldn't download Node.js for Video Flow. Check your internet connection and try again."
            ) from exc
        actual = _sha256(archive)
        if actual.lower() != expected_sha256.lower():
            log.warning("Node.js archive checksum mismatch: %s", actual)
            raise NodeComponentError(
                "The Node.js download didn't pass its security check, so it was not used. Try again later."
            )
        extracted = _extract(archive, work / "x")
        final = managed_node_dir()
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(final))
        (final / _MARKER).write_text(json.dumps({
            "version": MANAGED_NODE_VERSION,
            "archive": MANAGED_NODE_ARCHIVE,
            "archive_sha256": expected_sha256.lower(),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2), encoding="utf-8")
        exe = managed_node_executable()
        if exe is None:
            raise NodeComponentError("Node.js for Video Flow could not be set up.")
        _set_status(state="ready", error="")
        log.info("Node.js %s for Video Flow is ready at %s", MANAGED_NODE_VERSION, exe)
        return exe
    except NodeComponentError as exc:
        _set_status(state="failed", error=str(exc))
        raise
    except Exception as exc:  # disk full, permissions, bad zip…
        log.warning("Node.js %s setup failed: %s", MANAGED_NODE_VERSION, exc)
        message = "Node.js for Video Flow could not be set up. Check free disk space and try again."
        _set_status(state="failed", error=message)
        raise NodeComponentError(message) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prefetch_managed_node() -> bool:
    """Background entry point: never raises. True when Node 22 is ready or not needed."""
    try:
        ensure_managed_node(background=True)
        return True
    except NodeComponentError as exc:
        log.info("Background Node.js download did not finish: %s", exc)
        return False
    except Exception:
        log.debug("Background Node.js download failed", exc_info=True)
        return False
