"""Download, verify, and apply an AI Productivity Flow update.

Small updates replace only the application package when the bundled runtime
(Python, Node, Hyperframes, Narova, ffmpeg, the Whisper model, and the local
AI engine) is unchanged. Anything else uses the full Windows installer or the
macOS disk image.

User data under ``~/.voice_flow`` is never a target of a swap, including the
NotebookLM cookie and keepalive files that live there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from voice_flow._version import VERSION
from voice_flow.bundled_runtime import (
    APP_MANAGED_FIELDS,
    CORE_RUNTIME_FIELDS,
    RUNTIME_FIELDS,
    runtime_for_platform,
)

log = logging.getLogger("voice_flow.app_updater")

APP_UPDATE_NAMES = {
    "win": "AI-Productivity-Flow-app-update-win.zip",
    "mac": "AI-Productivity-Flow-app-update-mac.zip",
}
MANIFEST_NAMES = {
    "win": "AI-Productivity-Flow-app-update-win.manifest.json",
    "mac": "AI-Productivity-Flow-app-update-mac.manifest.json",
}
WINDOWS_INSTALLER_NAME = "AI-Productivity-Flow-Setup-x64.exe"
MAC_DISK_IMAGE_NAME = "AI-Productivity-Flow-macOS.dmg"
MAC_FULL_ZIP_NAME = "AI-Productivity-Flow-macOS.zip"
WINDOWS_INSTALLER_FLAGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]

DOWNLOAD_TIMEOUT_SECONDS = 30.0
MARKER_WAIT_SECONDS = 90.0
CHUNK_BYTES = 64 * 1024


class UpdateError(Exception):
    """A download or install step failed. ``retryable`` is for the UI."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class UpdateCancelled(UpdateError):
    def __init__(self) -> None:
        super().__init__("Download cancelled.", retryable=True)


def current_platform() -> str:
    if sys.platform == "darwin":
        return "mac"
    return "win"


def format_bytes(size: int | None) -> str:
    """Human size for the update row and the progress line."""
    if size is None or size < 0:
        return "unknown size"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def assert_public_release_url(url: str) -> None:
    """Updates may only be fetched from a GitHub release asset."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise UpdateError("Update URL must use https.", retryable=False)
    allowed = host == "github.com" or host.endswith(".githubusercontent.com")
    if not allowed:
        raise UpdateError("Update URL is not a GitHub release asset.", retryable=False)
    if "/releases/download/" not in parsed.path:
        raise UpdateError("Refusing to open anything other than the update file.", retryable=False)


def build_windows_installer_command(installer: str | Path) -> list[str]:
    """Inno Setup command that shows the progress window and relaunches nothing itself.

    ``/SILENT`` keeps the installer's progress window (the branded wizard is
    the interactive path). The script's silent ``[Run]`` entry starts the app
    again after the files are in place. ``/NORESTART`` stops a reboot, and the
    install stays per-user because the script sets ``PrivilegesRequired=lowest``.
    """
    return [str(installer), *WINDOWS_INSTALLER_FLAGS]


def mac_attach_argv(dmg: Path, mountpoint: Path) -> list[str]:
    return ["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mountpoint), str(dmg)]


def mac_detach_argv(mountpoint: Path) -> list[str]:
    return ["/usr/bin/hdiutil", "detach", str(mountpoint), "-quiet"]


def mac_quarantine_argv(bundle: Path) -> list[str]:
    return ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(bundle)]


def mac_relaunch_argv(bundle: Path) -> list[str]:
    return ["/usr/bin/open", str(bundle)]


def parse_sha256_text(text: str) -> str:
    """Accept ``<hex>  filename``, a bare hex digest, or ``SHA256 (name) = hex``."""
    import re

    match = re.search(r"\b([a-fA-F0-9]{64})\b", text or "")
    if not match:
        raise UpdateError("The checksum file was not valid.", retryable=True)
    return match.group(1).lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected_text: str) -> str:
    """Check ``path`` against a checksum asset. Deletes it when it does not match."""
    expected = parse_sha256_text(expected_text)
    actual = sha256_file(path)
    if actual != expected:
        try:
            path.unlink()
        except OSError:
            pass
        raise UpdateError(
            "The download did not match its checksum. It was deleted. Try again.",
            retryable=True,
        )
    return actual


def _asset_by_name(assets: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == name:
            return asset
    return None


def _asset_url(asset: dict[str, Any] | None) -> str:
    if not asset:
        return ""
    return str(asset.get("browser_download_url") or asset.get("url") or "")


def _asset_size(asset: dict[str, Any] | None) -> int | None:
    if not asset or asset.get("size") in (None, ""):
        return None
    try:
        return int(asset["size"])
    except (TypeError, ValueError):
        return None


def simplify_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    simplified = []
    for asset in assets:
        if not isinstance(asset, dict) or not asset.get("name"):
            continue
        simplified.append({
            "name": asset.get("name"),
            "browser_download_url": _asset_url(asset),
            "size": _asset_size(asset) or 0,
        })
    return simplified


def runtime_fingerprint_from_manifest(data: dict[str, Any] | None) -> dict[str, str] | None:
    """Normalize a release manifest or an installed runtime manifest."""
    if not isinstance(data, dict):
        return None
    runtime = data.get("runtime")
    if isinstance(runtime, dict):
        found = {key: str(runtime.get(key) or "") for key in RUNTIME_FIELDS}
        if all(found.values()):
            return found

    partial: dict[str, str] = {}
    python = data.get("python")
    node = data.get("node")
    hyperframes = data.get("hyperframes")
    ffmpeg = data.get("ffmpeg")
    whisper = data.get("whisper")
    if isinstance(python, dict) and python.get("version"):
        partial["python"] = str(python["version"])
    elif data.get("python_version"):
        partial["python"] = str(data["python_version"])
    if isinstance(node, dict) and node.get("version"):
        partial["node"] = str(node["version"])
    if isinstance(hyperframes, dict) and hyperframes.get("version"):
        partial["hyperframes"] = str(hyperframes["version"])
    if isinstance(ffmpeg, dict) and ffmpeg.get("version"):
        partial["ffmpeg"] = str(ffmpeg["version"])
    if isinstance(whisper, dict) and whisper.get("revision"):
        partial["whisper"] = str(whisper["revision"])
    narova = data.get("narova")
    if isinstance(narova, dict) and narova.get("version"):
        partial["narova"] = str(narova["version"])
    engine = data.get("local_ai_engine")
    if isinstance(engine, str) and engine:
        partial["local_ai_engine"] = engine
    elif isinstance(engine, dict) and engine.get("version"):
        name = str(engine.get("name") or "local-ai")
        version = str(engine["version"])
        partial["local_ai_engine"] = version if "==" in version else f"{name}=={version}"
    if all(partial.get(key) for key in RUNTIME_FIELDS):
        return {key: partial[key] for key in RUNTIME_FIELDS}
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _installed_manifest_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        from voice_flow.runtime_env import install_root, mac_bundle_runtime_dir

        root = install_root()
        if root is not None:
            candidates.append(root / "runtime" / "runtime-manifest.json")
            candidates.append(root / "updates" / "app-update-runtime.json")
        runtime = mac_bundle_runtime_dir()
        if runtime is not None:
            candidates.append(runtime / "build-manifest.json")
            candidates.append(runtime.parent / "updates" / "app-update-runtime.json")
    except Exception:
        pass
    return candidates


def installed_runtime_fingerprint(platform: str | None = None) -> dict[str, str]:
    """Runtime versions of this install, preferring the on-disk manifest.

    Fields the install manifest actually records win over the pins compiled
    into this build. Missing fields fall back to those pins so a 1.0.4 install
    whose manifest predates the normalized block can still match a later
    app-only release that did not change the runtime.
    """
    platform = platform or current_platform()
    pins = runtime_for_platform(platform)
    merged = dict(pins)
    for path in _installed_manifest_candidates():
        data = _read_json(path)
        fingerprint = runtime_fingerprint_from_manifest(data)
        if fingerprint:
            return fingerprint
        if not isinstance(data, dict):
            continue
        # Overlay whatever individual fields the older manifest shape has.
        loose = _loose_runtime_fields(data)
        for key, value in loose.items():
            merged[key] = value
    return merged


def _loose_runtime_fields(data: dict[str, Any]) -> dict[str, str]:
    """Pull any runtime fields an older manifest happens to carry."""
    wrapped = runtime_fingerprint_from_manifest(data)
    if wrapped:
        return wrapped
    found: dict[str, str] = {}
    mapping = {
        "python": ("python", "version"),
        "node": ("node", "version"),
        "hyperframes": ("hyperframes", "version"),
        "ffmpeg": ("ffmpeg", "version"),
        "whisper": ("whisper", "revision"),
    }
    for key, (section, field) in mapping.items():
        block = data.get(section)
        if isinstance(block, dict) and block.get(field):
            found[key] = str(block[field])
    if data.get("python_version"):
        found["python"] = str(data["python_version"])
    narova = data.get("narova")
    if isinstance(narova, dict) and narova.get("version"):
        found["narova"] = str(narova["version"])
    engine = data.get("local_ai_engine")
    if isinstance(engine, str) and engine:
        found["local_ai_engine"] = engine
    return found


def runtimes_match(installed: dict[str, str] | None, remote: dict[str, str] | None) -> bool:
    """True when the app zip can run on the installed runtime.

    Only the core fields count (1.0.8+). App-managed pieces such as Node are
    fetched by the app itself when a feature needs a newer one, so a
    difference there no longer forces the full installer.
    """
    if not installed or not remote:
        return False
    return all(installed.get(key) and installed.get(key) == remote.get(key) for key in CORE_RUNTIME_FIELDS)


def changed_runtime_fields(installed: dict[str, str] | None, remote: dict[str, str] | None) -> dict[str, list[str]]:
    """Which fields differ, split into core (full installer) and app-managed."""
    if not installed or not remote:
        return {"core": list(CORE_RUNTIME_FIELDS), "app_managed": []}
    core = [k for k in CORE_RUNTIME_FIELDS if not installed.get(k) or installed.get(k) != remote.get(k)]
    managed = [k for k in APP_MANAGED_FIELDS if installed.get(k) != remote.get(k)]
    return {"core": core, "app_managed": managed}


def select_update_plan(
    assets: list[dict[str, Any]],
    *,
    platform: str,
    installed_runtime: dict[str, str] | None,
    remote_runtime: dict[str, str] | None,
    can_apply_app: bool = True,
) -> dict[str, Any]:
    """Choose the app zip or the full installer for ``platform``.

    The app zip is used only when every runtime field matches and the app can
    write its own install folder. Otherwise the plan is the full installer.
    """
    full_name = WINDOWS_INSTALLER_NAME if platform == "win" else MAC_DISK_IMAGE_NAME
    full_asset = _asset_by_name(assets, full_name)
    if full_asset is None and platform == "mac":
        full_asset = _asset_by_name(assets, MAC_FULL_ZIP_NAME)
        full_name = MAC_FULL_ZIP_NAME if full_asset else full_name
    app_name = APP_UPDATE_NAMES[platform]
    app_asset = _asset_by_name(assets, app_name)
    use_app = bool(
        can_apply_app
        and app_asset
        and _asset_url(app_asset)
        and runtimes_match(installed_runtime, remote_runtime)
    )
    chosen = app_asset if use_app else full_asset
    chosen_name = app_name if use_app else full_name
    if chosen is None:
        return {
            "kind": "none",
            "asset_name": "",
            "download_url": "",
            "sha256_url": "",
            "size_bytes": None,
            "size_label": "unknown size",
            "fallback_url": "",
            "runtime_changed": not use_app,
            "reason": "This release has no downloadable file for this computer.",
            "install_label": "Update now",
        }
    sha = _asset_by_name(assets, chosen_name + ".sha256")
    full_url = _asset_url(full_asset)
    kind = "app" if use_app else "full"
    if use_app:
        reason = "The bundled runtime is unchanged, so this is a small app update."
        install_label = "Restart to update"
    elif not runtimes_match(installed_runtime, remote_runtime):
        reason = "This update includes a runtime change, so the full installer is required."
        install_label = "Restart to install"
    elif not can_apply_app:
        reason = "The app can't replace its own files here, so the full installer is required."
        install_label = "Restart to install"
    else:
        reason = "The full installer will be downloaded."
        install_label = "Restart to install"
    size = _asset_size(chosen)
    download_url = _asset_url(chosen)
    return {
        "kind": kind,
        "platform": platform,
        "asset_name": chosen_name,
        "download_url": download_url,
        "sha256_url": _asset_url(sha),
        "size_bytes": size,
        "size_label": format_bytes(size),
        "fallback_url": download_url if "/releases/download/" in download_url else "",
        "full_fallback_url": full_url if "/releases/download/" in full_url else "",
        "runtime_changed": kind != "app",
        # Data for the update UI (wording is the front end's): which runtime
        # fields differ, split into core ones and app-managed ones the app
        # fetches itself.
        "runtime_changes": changed_runtime_fields(installed_runtime, remote_runtime),
        "reason": reason,
        "install_label": install_label,
    }


def fetch_manifest(url: str, timeout: float = 5.0) -> dict[str, Any]:
    assert_public_release_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"AI-Productivity-Flow/{VERSION} (update-manifest)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise UpdateError("Update manifest was not valid.")
    return payload


def describe_update(
    assets: list[dict[str, Any]],
    *,
    platform: str | None = None,
    installed_runtime: dict[str, str] | None = None,
    remote_runtime: dict[str, str] | None = None,
    fetch_manifest_fn: Callable[[str], dict[str, Any]] | None = None,
    can_apply_app: bool | None = None,
) -> dict[str, Any]:
    """Build the plan attached to an update check, including the download size."""
    platform = platform or current_platform()
    simplified = simplify_assets(assets)
    if installed_runtime is None:
        installed_runtime = installed_runtime_fingerprint(platform)
    if remote_runtime is None:
        manifest_asset = _asset_by_name(simplified, MANIFEST_NAMES[platform])
        manifest_url = _asset_url(manifest_asset)
        if manifest_url:
            try:
                loader = fetch_manifest_fn or fetch_manifest
                remote_runtime = runtime_fingerprint_from_manifest(loader(manifest_url))
            except Exception as exc:
                log.info("Could not read the app-update manifest (%s); using the full installer.", exc)
                remote_runtime = None
    if can_apply_app is None:
        package = installed_package_dir()
        can_apply_app = package is not None and _directory_writable(package)
    plan = select_update_plan(
        simplified,
        platform=platform,
        installed_runtime=installed_runtime,
        remote_runtime=remote_runtime,
        can_apply_app=can_apply_app,
    )
    return {"assets": simplified, "update_plan": plan}


def _network_message(exc: BaseException) -> str:
    text = str(exc).lower()
    reason = getattr(exc, "reason", None)
    reason_text = str(reason).lower() if reason is not None else text
    offline_markers = (
        "network", "unreachable", "name or service not known", "nodename nor servname",
        "temporary failure", "getaddrinfo", "no address", "offline", "errno 8",
        "errno 11001", "failed to establish",
    )
    if any(marker in reason_text or marker in text for marker in offline_markers):
        return "No internet connection. Check your network and try again."
    if "timed out" in text or "timeout" in text:
        return "The download timed out. Try again."
    return "Could not download the update. Check your connection and try again."


def download_file(
    url: str,
    dest: Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    opener: Callable[..., Any] | None = None,
) -> Path:
    """Download ``url`` to ``dest``, resuming a partial file when the server allows it.

    A server that ignores ``Range`` causes a clean restart. Redirects are
    followed by ``urlopen``. A dropped connection leaves the partial file so
    the next attempt can resume.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    existing = partial.stat().st_size if partial.is_file() else 0
    headers = {"User-Agent": f"AI-Productivity-Flow/{VERSION} (update)"}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    open_url = opener or urllib.request.urlopen
    try:
        response = open_url(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and existing > 0:
            # The partial file is already complete, or the range is stale.
            partial.replace(dest)
            if progress:
                progress(dest.stat().st_size, dest.stat().st_size)
            return dest
        raise UpdateError(_network_message(exc)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(_network_message(exc)) from exc

    try:
        status = int(getattr(response, "status", None) or getattr(response, "code", 200) or 200)
        response_headers = getattr(response, "headers", {}) or {}
        if existing > 0 and status != 206:
            existing = 0
        total = _total_size(response_headers, status, existing)
        mode = "ab" if status == 206 and existing > 0 else "wb"
        downloaded = existing if mode == "ab" else 0
        if progress:
            progress(downloaded, total)
        with partial.open(mode) as handle:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled()
                try:
                    chunk = response.read(CHUNK_BYTES)
                except (TimeoutError, OSError) as exc:
                    raise UpdateError(_network_message(exc)) from exc
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
        if total is not None and downloaded < total:
            raise UpdateError(
                f"The download stopped early ({format_bytes(downloaded)} of {format_bytes(total)}). Try again."
            )
        partial.replace(dest)
        if progress:
            progress(dest.stat().st_size, total or dest.stat().st_size)
        return dest
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if callable(getter):
        return str(getter(name) or "")
    return ""


def _total_size(headers: Any, status: int, existing: int) -> int | None:
    content_range = _header(headers, "Content-Range")
    if status == 206 and "/" in content_range:
        total_text = content_range.rsplit("/", 1)[-1].strip()
        if total_text.isdigit():
            return int(total_text)
    length = _header(headers, "Content-Length")
    if length.isdigit():
        reported = int(length)
        return existing + reported if status == 206 else reported
    return None


def _assert_safe_target(path: Path) -> None:
    resolved = path.resolve()
    if ".voice_flow" in resolved.parts:
        raise UpdateError("Refusing to change files in the user data folder.", retryable=False)
    try:
        resolved.relative_to((Path.home() / ".voice_flow").resolve())
    except ValueError:
        return
    raise UpdateError("Refusing to change files in the user data folder.", retryable=False)


def apply_staged_package(staging: Path, target: Path, backup: Path) -> None:
    """Put ``staging`` in ``target``'s place, keeping the previous tree as ``backup``."""
    _assert_safe_target(target)
    _assert_safe_target(backup)
    if not staging.is_dir():
        raise UpdateError("The staged update is missing.", retryable=False)
    if backup.exists():
        shutil.rmtree(backup)
    moved = False
    try:
        if target.exists():
            os.rename(target, backup)
            moved = True
        os.rename(staging, target)
    except OSError as exc:
        if moved and backup.exists() and not target.exists():
            os.rename(backup, target)
        raise UpdateError(f"Could not replace the app files ({exc}).", retryable=False) from exc


def restore_package(target: Path, backup: Path) -> None:
    """Undo a swap. Used when the new build does not stay running."""
    _assert_safe_target(target)
    _assert_safe_target(backup)
    if target.exists():
        shutil.rmtree(target)
    if backup.exists():
        os.rename(backup, target)


def extract_app_zip(zip_path: Path, dest_parent: Path) -> tuple[Path, dict[str, Any]]:
    """Extract a verified app-update zip. Returns the staged package and manifest."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    staged = dest_parent / "voice_flow"
    if staged.exists():
        shutil.rmtree(staged)
    manifest: dict[str, Any] | None = None
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or name.endswith("/"):
                continue
            parts = Path(name).parts
            if ".." in parts or name.startswith("/"):
                raise UpdateError("Update package contains an unsafe path.", retryable=False)
            if name == "manifest.json":
                payload = json.loads(archive.read(info).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise UpdateError("Update manifest was not valid.", retryable=False)
                manifest = payload
                continue
            if not parts or parts[0] != "voice_flow":
                continue
            target = dest_parent.joinpath(*parts)
            _assert_safe_target(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    if manifest is None:
        raise UpdateError("Update package is missing its manifest.", retryable=False)
    if not (staged / "main.py").is_file():
        raise UpdateError("Update package did not contain the app.", retryable=False)
    return staged, manifest


def _directory_writable(path: Path) -> bool:
    parent = path if path.is_dir() else path.parent
    try:
        return parent.is_dir() and os.access(parent, os.W_OK)
    except OSError:
        return False


def installed_package_dir() -> Path | None:
    """The live ``voice_flow`` package inside an install, or None from a source checkout."""
    try:
        from voice_flow.runtime_env import install_root, mac_bundle_runtime_dir
    except Exception:
        return None
    root = install_root()
    if root is not None:
        candidate = root / "runtime" / "python" / "Lib" / "site-packages" / "voice_flow"
        if candidate.is_dir():
            return candidate
    runtime = mac_bundle_runtime_dir()
    if runtime is not None:
        candidate = runtime.parent / "src" / "voice_flow"
        if candidate.is_dir():
            return candidate
    return None


def update_state_dir() -> Path | None:
    package = installed_package_dir()
    if package is None:
        return None
    # Windows: site-packages/voice_flow -> install root is parents[4]
    #   parents: site-packages, Lib, python, runtime, <install>
    # Mac: Resources/src/voice_flow -> Resources is parents[1]
    if package.parent.name == "site-packages":
        return package.parents[4] / "updates"
    return package.parents[1] / "updates"


def _find_app(mount: Path) -> Path | None:
    direct = [path for path in mount.glob("*.app") if path.is_dir()]
    if direct:
        return direct[0]
    for path in mount.rglob("*.app"):
        if path.is_dir():
            return path
    return None


def replace_app_tree(source: Path, dest: Path) -> None:
    """Replace ``dest`` with ``source``, restoring ``dest`` if the copy fails."""
    _assert_safe_target(dest)
    backup = dest.with_name(dest.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if dest.exists():
        os.rename(dest, backup)
    try:
        shutil.copytree(source, dest, symlinks=True)
    except Exception:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        if backup.exists() and not dest.exists():
            os.rename(backup, dest)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def install_mac_image(
    image: Path,
    bundle: Path,
    *,
    run: Callable[..., Any] | None = None,
    replace: Callable[[Path, Path], None] | None = None,
) -> str:
    """Mount a dmg or unpack a zip, replace ``bundle``, and strip quarantine.

    Returns ``replaced`` or ``manual``. ``manual`` means the caller should open
    the downloaded file in Finder instead of quitting.
    """
    if not _directory_writable(bundle):
        return "manual"
    runner = run or subprocess.run
    replacer = replace or replace_app_tree
    if image.suffix.lower() == ".zip":
        work = Path(tempfile.mkdtemp(prefix="apf-mac-zip-"))
        try:
            with zipfile.ZipFile(image) as archive:
                archive.extractall(work)
            app = _find_app(work)
            if app is None:
                return "manual"
            replacer(app, bundle)
        except (OSError, zipfile.BadZipFile):
            return "manual"
        finally:
            shutil.rmtree(work, ignore_errors=True)
        runner(mac_quarantine_argv(bundle), check=False)
        return "replaced"

    mount = Path(tempfile.mkdtemp(prefix="apf-dmg-"))
    try:
        attached = runner(mac_attach_argv(image, mount), check=False)
        if getattr(attached, "returncode", 1) not in (0, None):
            return "manual"
        app = _find_app(mount)
        if app is None:
            return "manual"
        try:
            replacer(app, bundle)
        except OSError:
            return "manual"
        runner(mac_quarantine_argv(bundle), check=False)
        return "replaced"
    finally:
        try:
            runner(mac_detach_argv(mount), check=False)
        except Exception:
            pass
        shutil.rmtree(mount, ignore_errors=True)


def _wait_for_pid(pid: int, timeout: float = 30.0) -> None:
    if not pid or pid == os.getpid():
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)


def _clear_watchdog_flag() -> None:
    try:
        from voice_flow.paths import data_dir

        flag = data_dir() / "watchdog_shutdown.flag"
        flag.unlink(missing_ok=True)
    except Exception:
        pass


def run_pending_update(
    pending: dict[str, Any],
    *,
    wait_for_exit: Callable[[int], None] | None = None,
    launch: Callable[[list[str]], Any] | None = None,
    wait_for_marker: Callable[[Path], bool] | None = None,
) -> str:
    """Apply a staged app update or start the installer after the app has exited.

    Returns ``ok``, ``rolled-back``, or ``manual``.
    """
    waiter = wait_for_exit or _wait_for_pid
    starter = launch or _spawn
    marker_waiter = wait_for_marker or _wait_for_marker
    waiter(int(pending.get("wait_pid") or 0))
    _clear_watchdog_flag()
    kind = pending.get("kind")
    if kind == "installer":
        starter(list(pending.get("command") or []))
        return "ok"
    if kind == "mac-image":
        image = Path(pending["image"])
        bundle = Path(pending["bundle"])
        outcome = install_mac_image(image, bundle)
        if outcome != "replaced":
            _open_path(image)
            _mac_manual_dialog()
            return "manual"
        starter(mac_relaunch_argv(bundle))
        return "ok"
    staging = Path(pending["staging"])
    target = Path(pending["target"])
    backup = Path(pending["backup"])
    marker = Path(pending["success_marker"])
    apply_staged_package(staging, target, backup)
    command = list(pending.get("relaunch") or [])
    proc = starter(command)
    if marker_waiter(marker):
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        try:
            Path(pending["pending_path"]).unlink(missing_ok=True)
        except (KeyError, OSError):
            pass
        return "ok"
    try:
        if proc is not None and getattr(proc, "poll", lambda: None)() is None:
            proc.terminate()
    except Exception:
        pass
    restore_package(target, backup)
    if command:
        starter(command)
    return "rolled-back"


def _spawn(command: list[str]) -> subprocess.Popen[Any] | None:
    if not command:
        return None
    return subprocess.Popen(command, close_fds=True, start_new_session=True)


def _wait_for_marker(marker: Path, timeout: float = MARKER_WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.is_file():
            return True
        time.sleep(0.25)
    return False


def _open_path(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["/usr/bin/open", str(path)], start_new_session=True)
        elif sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)], start_new_session=True)
    except Exception as exc:
        log.warning("Could not open %s: %s", path, exc)


def _mac_manual_dialog() -> None:
    if sys.platform != "darwin":
        return
    message = (
        "AI Productivity Flow could not replace the app in its current folder. "
        "The downloaded disk image is open in Finder. Drag AI Productivity Flow "
        "to the Applications folder, then open it."
    )
    try:
        subprocess.Popen(
            ["/usr/bin/osascript", "-e", f'display dialog "{message}" buttons {{"OK"}} default button 1'],
            start_new_session=True,
        )
    except Exception:
        pass


MANUAL_FINDER_INSTRUCTIONS = (
    "AI Productivity Flow couldn't replace the app in its current folder. "
    "The downloaded disk image is open in Finder. Drag AI Productivity Flow to "
    "the Applications folder, then open it."
)


def confirm_successful_launch() -> bool:
    """The new build reached its ready loop. The helper may delete the backup."""
    pending_path = _pending_path()
    if pending_path is None or not pending_path.is_file():
        return False
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    marker = pending.get("success_marker")
    if not marker:
        return False
    path = Path(marker)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _pending_path() -> Path | None:
    override = os.environ.get("APF_UPDATE_PENDING", "").strip()
    if override:
        return Path(override)
    state = update_state_dir()
    if state is None:
        return None
    return state / "pending.json"


def _release_windows_mutexes() -> None:
    if not sys.platform.startswith("win"):
        return
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handles = []
    try:
        import voice_flow.main as main_mod

        handles.append(getattr(main_mod, "_ENGINE_MUTEX_HANDLE", None))
        main_mod._ENGINE_MUTEX_HANDLE = None
    except Exception:
        pass
    try:
        from voice_flow.gui import desktop_launcher

        handles.append(getattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None))
        desktop_launcher._LAUNCHER_MUTEX_HANDLE = None
    except Exception:
        pass
    for handle in handles:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass


def _request_watchdog_shutdown() -> None:
    try:
        from voice_flow.paths import data_dir

        flag = data_dir() / "watchdog_shutdown.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(f"update at {time.time()}", encoding="utf-8")
    except Exception:
        pass


def _stop_other_suite_processes(helper_pid: int | None) -> None:
    """Stop the window, engine, and watchdog without killing the update helper."""
    exclude = {os.getpid()}
    if helper_pid:
        exclude.add(helper_pid)
    if sys.platform.startswith("win"):
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "AI Productivity Flow")
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            pass
    try:
        import psutil
    except Exception:
        return
    markers = (
        "voice_flow.watchdog",
        "voice_flow.main",
        "voice_flow.gui.desktop_launcher",
        "launch_apf.pyw",
    )
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            if pid in exclude:
                continue
            command = " ".join(proc.info.get("cmdline") or [])
            if "--apply-pending" in command:
                continue
            if "pytest" in command:
                continue
            if any(marker in command for marker in markers):
                proc.terminate()
        except Exception:
            continue
    try:
        from voice_flow import child_processes

        child_processes.shutdown()
    except Exception:
        pass
    try:
        from voice_flow.platform import macos_lifecycle

        macos_lifecycle.release_engine_lock()
    except Exception:
        pass


def _helper_command(pending_path: Path) -> list[str]:
    interpreter = sys.executable
    if sys.platform.startswith("win"):
        try:
            from voice_flow.runtime_env import pythonw_executable

            windowless = pythonw_executable()
            if windowless:
                interpreter = windowless
        except Exception:
            pass
        sibling = Path(sys.executable).with_name("pythonw.exe")
        if interpreter == sys.executable and sibling.is_file():
            interpreter = str(sibling)
    return [
        interpreter,
        "-m",
        "voice_flow.app_updater",
        "--apply-pending",
        str(pending_path),
        "--wait-pid",
        str(os.getpid()),
    ]


def _spawn_helper(pending_path: Path) -> int:
    env = os.environ.copy()
    package_parent = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (package_parent, env.get("PYTHONPATH", "")) if part
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = _helper_command(pending_path)
    kwargs: dict[str, Any] = {
        "env": env,
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        )
        kwargs["creationflags"] = flags
        try:
            return subprocess.Popen(command, **kwargs).pid
        except OSError:
            kwargs["creationflags"] = flags & ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            return subprocess.Popen(command, **kwargs).pid
    kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs).pid


def quit_for_update(helper_pid: int | None = None) -> None:
    """Release the single-instance lock, stop workers, and exit."""
    _request_watchdog_shutdown()
    _stop_other_suite_processes(helper_pid)
    _release_windows_mutexes()
    log.info("Quitting so the update can finish.")
    os._exit(0)


class UpdateManager:
    """One in-app download at a time, with progress the settings page can poll."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.plan: dict[str, Any] | None = None
        self.state = "idle"
        self.downloaded = 0
        self.total: int | None = None
        self.error = ""
        self.path: Path | None = None
        self.message = ""

    def remember(self, plan: dict[str, Any] | None) -> None:
        with self._lock:
            if self.state in {"downloading", "verifying"}:
                return
            self.plan = plan

    def status(self) -> dict[str, Any]:
        with self._lock:
            total = self.total
            downloaded = self.downloaded
            percent = 0.0
            if total:
                percent = max(0.0, min(100.0, (downloaded / total) * 100.0))
            elif self.state in {"ready", "installing", "manual"}:
                percent = 100.0
            label = ""
            if self.state == "downloading":
                if total:
                    label = f"{percent:.0f}% · {format_bytes(downloaded)} of {format_bytes(total)}"
                else:
                    label = f"{format_bytes(downloaded)} downloaded"
            elif self.state == "verifying":
                label = "Checking the download…"
            plan = self.plan or {}
            fallback = ""
            if self.state == "failed":
                fallback = str(plan.get("fallback_url") or "")
            return {
                "success": True,
                "state": self.state,
                "progress": round(percent, 1),
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "downloaded_mb": round(downloaded / (1024 * 1024), 2) if downloaded else 0.0,
                "total_mb": round(total / (1024 * 1024), 2) if total else None,
                "label": label,
                "error": self.error or None,
                "message": self.message or None,
                "can_retry": self.state in {"failed", "cancelled"},
                "can_cancel": self.state == "downloading",
                "can_install": self.state == "ready",
                "install_label": plan.get("install_label") or "Restart to install",
                "fallback_url": fallback,
                "kind": plan.get("kind"),
                "size_label": plan.get("size_label"),
                "asset_name": plan.get("asset_name"),
            }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.state == "downloading":
                return self.status()
            plan = self.plan
            if not plan or not plan.get("download_url"):
                raise UpdateError("No update is ready to download. Check for updates first.")
            url = str(plan["download_url"])
            assert_public_release_url(url)
            if plan.get("sha256_url"):
                assert_public_release_url(str(plan["sha256_url"]))
            self._cancel.clear()
            self.state = "downloading"
            self.downloaded = 0
            self.total = plan.get("size_bytes")
            self.error = ""
            self.path = None
            self.message = ""
            self._thread = threading.Thread(target=self._download, name="AppUpdateDownload", daemon=True)
            self._thread.start()
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        with self._lock:
            if self.state == "downloading":
                self.state = "cancelled"
                self.error = "Download cancelled."
        return self.status()

    def _download(self) -> None:
        plan = self.plan or {}
        name = Path(str(plan.get("asset_name") or "update.bin")).name
        dest_dir = Path(tempfile.gettempdir()) / "AI-Productivity-Flow" / "updates"
        dest = dest_dir / name
        try:
            def _progress(done: int, total: int | None) -> None:
                with self._lock:
                    if self._cancel.is_set():
                        return
                    self.downloaded = done
                    if total:
                        self.total = total

            download_file(str(plan["download_url"]), dest, progress=_progress, cancel_event=self._cancel)
            if self._cancel.is_set():
                with self._lock:
                    self.state = "cancelled"
                    self.error = "Download cancelled."
                return
            with self._lock:
                self.state = "verifying"
            sha_url = str(plan.get("sha256_url") or "")
            if not sha_url:
                dest.unlink(missing_ok=True)
                raise UpdateError("This release did not include a checksum.", retryable=False)
            checksum_path = dest.with_name(dest.name + ".sha256")
            download_file(sha_url, checksum_path, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            verify_sha256(dest, checksum_path.read_text(encoding="utf-8", errors="replace"))
            with self._lock:
                self.path = dest
                self.state = "ready"
                self.downloaded = dest.stat().st_size
                self.total = self.downloaded
                self.message = "Download verified."
        except UpdateCancelled:
            with self._lock:
                self.state = "cancelled"
                self.error = "Download cancelled."
        except UpdateError as exc:
            with self._lock:
                if self.state != "cancelled":
                    self.state = "failed"
                    self.error = str(exc)
        except Exception as exc:
            log.exception("Update download failed")
            with self._lock:
                self.state = "failed"
                self.error = _network_message(exc)

    def begin_install(self) -> dict[str, Any]:
        with self._lock:
            if self.state != "ready" or self.path is None or not self.plan:
                raise UpdateError("Download and verify the update before installing it.")
            plan = dict(self.plan)
            image = self.path
        kind = plan.get("kind")
        if kind == "app":
            return self._begin_app_install(plan, image)
        mac_image = str(image).endswith((".dmg", ".zip")) and plan.get("platform") == "mac"
        if current_platform() == "mac" or mac_image:
            return self._begin_mac_install(plan, image)
        return self._begin_windows_install(image)

    def _begin_windows_install(self, installer: Path) -> dict[str, Any]:
        state = self._ensure_state_dir()
        pending_path = state / "pending.json"
        pending = {
            "kind": "installer",
            "command": build_windows_installer_command(installer),
            "wait_pid": os.getpid(),
            "pending_path": str(pending_path),
        }
        self._write_pending(pending_path, pending)
        helper = _spawn_helper(pending_path)
        self._schedule_quit(helper)
        with self._lock:
            self.state = "installing"
            self.message = "Restarting to install…"
        return {"success": True, "state": "installing", "message": self.message}

    def _begin_mac_install(self, plan: dict[str, Any], image: Path) -> dict[str, Any]:
        bundle = _current_bundle()
        if bundle is None or not _directory_writable(bundle):
            _open_path(image)
            with self._lock:
                self.state = "manual"
                self.message = MANUAL_FINDER_INSTRUCTIONS
            return {"success": True, "state": "manual", "message": MANUAL_FINDER_INSTRUCTIONS}
        state = self._ensure_state_dir()
        pending_path = state / "pending.json"
        pending = {
            "kind": "mac-image",
            "image": str(image),
            "bundle": str(bundle),
            "wait_pid": os.getpid(),
            "pending_path": str(pending_path),
        }
        self._write_pending(pending_path, pending)
        helper = _spawn_helper(pending_path)
        self._schedule_quit(helper)
        with self._lock:
            self.state = "installing"
            self.message = "Restarting to install…"
        return {"success": True, "state": "installing", "message": self.message}

    def _begin_app_install(self, plan: dict[str, Any], archive: Path) -> dict[str, Any]:
        package = installed_package_dir()
        if package is None:
            raise UpdateError(
                "This copy isn't an installed app, so the small update can't be applied.",
                retryable=False,
            )
        if not _directory_writable(package):
            raise UpdateError(
                "The app can't replace its own files. Download the full installer instead.",
                retryable=False,
            )
        state = self._ensure_state_dir()
        staged, manifest = extract_app_zip(archive, state / "staging")
        remote = runtime_fingerprint_from_manifest(manifest)
        installed = installed_runtime_fingerprint(str(plan.get("platform") or current_platform()))
        if not runtimes_match(installed, remote):
            shutil.rmtree(state / "staging", ignore_errors=True)
            with self._lock:
                self.state = "failed"
                self.error = "This package needs a newer runtime. Download the full installer."
                if plan.get("full_fallback_url"):
                    self.plan = dict(plan)
                    self.plan["fallback_url"] = plan["full_fallback_url"]
            raise UpdateError(self.error, retryable=False)
        pending_path = state / "pending.json"
        relaunch = _relaunch_command()
        pending = {
            "kind": "app",
            "staging": str(staged),
            "target": str(package),
            "backup": str(package.with_name("voice_flow.bak")),
            "success_marker": str(state / "update-ok"),
            "relaunch": relaunch,
            "wait_pid": os.getpid(),
            "pending_path": str(pending_path),
        }
        self._write_pending(pending_path, pending)
        helper = _spawn_helper(pending_path)
        self._schedule_quit(helper)
        with self._lock:
            self.state = "installing"
            self.message = "Restarting to update…"
        return {"success": True, "state": "installing", "message": self.message}

    def _ensure_state_dir(self) -> Path:
        state = update_state_dir()
        if state is None:
            state = Path(tempfile.gettempdir()) / "AI-Productivity-Flow" / "updates"
        state.mkdir(parents=True, exist_ok=True)
        return state

    @staticmethod
    def _write_pending(path: Path, pending: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    @staticmethod
    def _schedule_quit(helper_pid: int) -> None:
        timer = threading.Timer(0.4, lambda: quit_for_update(helper_pid))
        timer.daemon = True
        timer.start()


def _current_bundle() -> Path | None:
    try:
        from voice_flow.platform.macos_lifecycle import app_bundle_path
    except Exception:
        return None
    return app_bundle_path()


def _relaunch_command() -> list[str]:
    if current_platform() == "mac":
        bundle = _current_bundle()
        if bundle is not None:
            return mac_relaunch_argv(bundle)
    try:
        from voice_flow.runtime_env import install_root, pythonw_executable

        root = install_root()
        if root is not None:
            launcher = root / "launch_apf.pyw"
            interpreter = pythonw_executable() or sys.executable
            if launcher.is_file():
                return [interpreter, str(launcher)]
    except Exception:
        pass
    return [sys.executable, "-m", "voice_flow.main"]


_manager = UpdateManager()


def get_manager() -> UpdateManager:
    return _manager


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply a staged AI Productivity Flow update")
    parser.add_argument("--apply-pending", type=Path)
    parser.add_argument("--wait-pid", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.apply_pending:
        return 2
    pending = json.loads(args.apply_pending.read_text(encoding="utf-8"))
    if args.wait_pid:
        pending["wait_pid"] = args.wait_pid
    pending.setdefault("pending_path", str(args.apply_pending))
    try:
        outcome = run_pending_update(pending)
    except Exception:
        log.exception("Could not apply the update")
        command = list(pending.get("relaunch") or pending.get("command") or [])
        if command:
            _spawn(command)
        return 1
    return 0 if outcome in {"ok", "manual"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
