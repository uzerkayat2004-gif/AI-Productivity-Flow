"""Small, controllable player for NotebookLM Audio Flow summaries.

The player is deliberately separate from the main dashboard so a generated
summary can be scrubbed without changing the system-wide Read TTS controls.
Media is exposed through an opaque, short-lived identifier; the browser never
receives a local filesystem path.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

# Ensure src and project root directories are in sys.path
_current_file = Path(__file__).resolve()
_src_dir = str(_current_file.parent.parent)
_project_root = str(_current_file.parent.parent.parent)

for _p in (_src_dir, _project_root):
    if _p and _p not in sys.path and os.path.exists(_p):
        sys.path.insert(0, _p)

# Ensure virtualenv site-packages are loaded even when invoked via base pythonw
_venv_site = Path(_project_root) / ".venv" / "Lib" / "site-packages"
if _venv_site.is_dir():
    try:
        import site
        site.addsitedir(str(_venv_site))
    except Exception:
        pass

from voice_flow.paths import data_dir

_MEDIA_TTL_SECONDS = 60 * 60 * 6
_media_lock = threading.RLock()
_media: dict[str, tuple[Path, float, str]] = {}
_player_processes: dict[str, subprocess.Popen] = {}


def clean_media_title(
    title: str | None,
    source_text: str | None = None,
    prompt: str | None = None,
    default: str = "Media",
    max_length: int = 120,
) -> str:
    """Recover and sanitize a media title, handling truncation, replacement characters, and illegal symbols."""
    raw = str(title or "").strip()

    # If title is truncated with '...' or contains replacement chars '\ufffd', attempt recovery
    is_truncated = raw.endswith("...") or raw.endswith("…") or (len(raw) > 20 and raw.endswith(".."))
    has_replacement = "\ufffd" in raw or "\ufffe" in raw

    if (is_truncated or has_replacement or not raw) and (source_text or prompt):
        text_source = str(source_text or prompt or "").strip()
        lines = [ln.strip() for ln in text_source.splitlines() if ln.strip()]
        if lines:
            first_line = re.sub(r"^#+\s*", "", lines[0]).strip()
            if first_line and len(first_line) >= 4:
                raw_prefix = re.sub(r"[^a-zA-Z0-9]", "", raw[:25]).lower()
                cand_prefix = re.sub(r"[^a-zA-Z0-9]", "", first_line[:25]).lower()
                if not raw or not raw_prefix or raw_prefix in cand_prefix or cand_prefix in raw_prefix:
                    raw = first_line

    # Clean Unicode replacement characters and dashes
    raw = raw.replace("\ufffd", " - ").replace("\ufffe", " ")
    raw = re.sub(r"[\u2010-\u2015]", "-", raw)  # normalize Unicode dashes/hyphens
    raw = re.sub(r"[\u2018\u2019]", "'", raw)  # smart quotes
    raw = re.sub(r'[\u201c\u201d]', '"', raw)

    # Remove characters illegal across Windows / macOS / Linux filesystems
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw)
    # Remove trailing ellipsis or dots
    cleaned = re.sub(r"\.{2,}$", "", cleaned).strip(" .")
    # Clean whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")
    # Clean redundant dashes
    cleaned = re.sub(r"\s*-\s*", " - ", cleaned)
    cleaned = re.sub(r"(\s*-\s*)+", " - ", cleaned)
    cleaned = cleaned.strip(" -_.")

    if not cleaned:
        cleaned = default

    # Windows reserved filenames (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    base_upper = cleaned.upper()
    if base_upper in {"CON", "PRN", "AUX", "NUL"} or re.match(r"^(COM|LPT)[1-9]$", base_upper):
        cleaned = f"{cleaned}_file"

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" ._-")

    return cleaned or default


def safe_media_filename(
    title: str | None,
    default: str = "Audio_Summary",
    ext: str = ".mp3",
    max_length: int = 120,
    source_text: str | None = None,
    prompt: str | None = None,
) -> str:
    """Format and sanitize a media title into a clean OS-safe download filename."""
    cleaned = clean_media_title(
        title,
        source_text=source_text,
        prompt=prompt,
        default=default,
        max_length=max_length,
    )
    clean_ext = ext if ext.startswith(".") else f".{ext}"
    if not cleaned.lower().endswith(clean_ext.lower()):
        cleaned = f"{cleaned}{clean_ext}"
    return cleaned



def ensure_mp3_audio(audio_path: Path | str) -> Path:
    """Ensure a genuine MP3 version of an audio file exists, converting with ffmpeg if needed."""
    p = Path(audio_path).expanduser().resolve()
    if not p.is_file():
        return p
    if p.suffix.lower() == ".mp3":
        return p
    mp3_path = p.with_suffix(".mp3")
    if mp3_path.is_file() and mp3_path.stat().st_size > 0:
        return mp3_path
    try:
        import shutil
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            cmd = [
                ffmpeg_bin, "-y", "-i", str(p),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(mp3_path),
            ]
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            res = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=flags)
            if res.returncode == 0 and mp3_path.is_file() and mp3_path.stat().st_size > 0:
                return mp3_path
    except Exception:
        pass
    return p


def get_user_downloads_dir() -> Path:
    """Return the user's primary Downloads directory across Windows / macOS / Linux.
    
    On Windows, accurately respects user-redirected Downloads folders (e.g. D:\\Downloads)
    via Windows Shell Known Folder API (FOLDERID_Downloads) and Registry User Shell Folders.
    """
    if sys.platform.startswith("win"):
        try:
            from ctypes import wintypes
            import uuid
            # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
            folderid = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}").bytes_le
            buf = wintypes.LPWSTR()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.c_char_p(folderid), 0, None, ctypes.byref(buf))
            if res == 0 and buf.value:
                p = Path(buf.value)
                if p.is_dir():
                    return p
        except Exception:
            pass

        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            val, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            if val:
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
        except Exception:
            pass

        try:
            profile = os.environ.get("USERPROFILE")
            if profile:
                p = Path(profile) / "Downloads"
                if p.is_dir():
                    return p
        except Exception:
            pass
    dl = Path.home() / "Downloads"
    if dl.is_dir():
        return dl
    return Path.home()


def get_user_videos_dir() -> Path:
    """Return the user's primary Videos directory across Windows / macOS / Linux.

    On Windows, accurately respects user-redirected Videos folders (e.g. D:\\Videos)
    via Windows Shell Known Folder API and Registry User Shell Folders.
    """
    if sys.platform.startswith("win"):
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            for key_name in ("My Video", "{352481E8-33BE-4251-BA85-6007CAEDCF9D}", "{1898EB52-7CD9-451B-AD22-04E9C05B4737}"):
                try:
                    val, _ = winreg.QueryValueEx(k, key_name)
                    if val:
                        p = Path(os.path.expandvars(val))
                        if p.is_dir():
                            return p
                except Exception:
                    pass
        except Exception:
            pass

        try:
            from ctypes import wintypes
            import uuid
            folderid = uuid.UUID("{1898EB52-7CD9-451B-AD22-04E9C05B4737}").bytes_le
            buf = wintypes.LPWSTR()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.c_char_p(folderid), 0, None, ctypes.byref(buf))
            if res == 0 and buf.value:
                p = Path(buf.value)
                if p.is_dir():
                    return p
        except Exception:
            pass

        try:
            profile = os.environ.get("USERPROFILE")
            if profile:
                p = Path(profile) / "Videos"
                if p.is_dir():
                    return p
        except Exception:
            pass

    vid = Path.home() / "Videos"
    if vid.is_dir():
        return vid
    return get_user_downloads_dir()


def get_user_music_dir() -> Path:
    """Return the user's primary Music directory across Windows / macOS / Linux.

    On Windows, accurately respects user-redirected Music folders (e.g. D:\\Music)
    via Registry User Shell Folders and Windows Shell Known Folder API.
    """
    if sys.platform.startswith("win"):
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            for key_name in ("My Music", "{4BD8D570-50BA-4FF6-A5EE-3821B30E4027}", "{A0C69A7B-04C8-4E47-9B0E-6B3BA0E80138}"):
                try:
                    val, _ = winreg.QueryValueEx(k, key_name)
                    if val:
                        p = Path(os.path.expandvars(val))
                        if p.is_dir():
                            return p
                except Exception:
                    pass
        except Exception:
            pass

        try:
            from ctypes import wintypes
            import uuid
            folderid = uuid.UUID("{4BD8D570-50BA-4FF6-A5EE-3821B30E4027}").bytes_le
            buf = wintypes.LPWSTR()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.c_char_p(folderid), 0, None, ctypes.byref(buf))
            if res == 0 and buf.value:
                p = Path(buf.value)
                if p.is_dir():
                    return p
        except Exception:
            pass

        try:
            profile = os.environ.get("USERPROFILE")
            if profile:
                p = Path(profile) / "Music"
                if p.is_dir():
                    return p
        except Exception:
            pass

    mus = Path.home() / "Music"
    if mus.is_dir():
        return mus
    return get_user_downloads_dir()


def save_media_to_downloads(
    source_path: Path | str,
    filename: str,
    copy_to_media_folder: bool = True,
) -> tuple[Path, str]:
    """Copy source_path into the user's Downloads folder with collision handling.
    Also copies video files to the user's Videos folder and audio files to the Music folder."""
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Source media file not found: {source_path}")
    dl_dir = get_user_downloads_dir()
    dl_dir.mkdir(parents=True, exist_ok=True)
    clean_name = safe_media_filename(filename, default="media", ext=src.suffix)
    target = dl_dir / clean_name
    stem = target.stem
    ext = target.suffix
    counter = 1
    while target.is_file():
        try:
            if target.stat().st_size == src.stat().st_size:
                break
        except Exception:
            pass
        target = dl_dir / f"{stem} ({counter}){ext}"
        counter += 1
    import shutil
    shutil.copy2(src, target)

    if copy_to_media_folder:
        try:
            ext_lower = src.suffix.lower()
            media_dir: Path | None = None
            if ext_lower in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
                media_dir = get_user_videos_dir()
            elif ext_lower in {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}:
                media_dir = get_user_music_dir()
            if media_dir and media_dir.resolve() != dl_dir.resolve():
                media_dir.mkdir(parents=True, exist_ok=True)
                media_target = media_dir / target.name
                shutil.copy2(src, media_target)
        except Exception:
            pass

    return target, target.name


def register_summary_audio(audio_path: str | Path, *, depth: str = "balanced", token: str | None = None) -> str:
    """Return an opaque local-player ID for a generated summary audio file."""
    candidate = Path(audio_path).expanduser().resolve()
    media_root = (data_dir() / "audio_summaries").resolve()
    if not candidate.is_file() or media_root not in candidate.parents:
        raise ValueError("Summary audio must be a generated file in the Audio Flow media folder.")
    if candidate.suffix.lower() not in {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".webm"}:
        raise ValueError("Unsupported summary audio format.")
    tok = str(token or "").strip() or secrets.token_urlsafe(24)
    with _media_lock:
        _purge_expired_locked()
        _media[tok] = (candidate, time.monotonic() + _MEDIA_TTL_SECONDS, str(depth or "balanced"))
    return tok


def resolve_summary_audio(token: str) -> tuple[Path, str] | None:
    """Resolve a previously registered token, refusing expired or deleted files."""
    with _media_lock:
        _purge_expired_locked()
        item = _media.get(str(token or ""))
        if item:
            path, _expires, depth = item
            if path.is_file():
                return (path, depth)

    # Check persisted audio summary history so past summaries remain playable
    try:
        from voice_flow.storage import storage
        hist = storage.get_audio_summary_history_by_id(str(token or ""))
        if hist:
            if hist.get("status") in ("failed", "cancelled") and not hist.get("audio_path"):
                return None
            media_root = (data_dir() / "audio_summaries").resolve()
            audio_cand: Path | None = None
            if hist.get("audio_path"):
                cand = Path(hist["audio_path"]).expanduser().resolve()
                if cand.is_file():
                    audio_cand = cand
                elif (media_root / cand.name).is_file():
                    audio_cand = media_root / cand.name
            if not audio_cand or not audio_cand.is_file():
                # Check candidate filenames matching the token or ID
                tok_clean = str(token or "").replace("ash_", "").strip()
                for ext in (".m4a", ".mp3", ".wav", ".ogg", ".webm", ".mp4"):
                    for test_name in (f"{token}{ext}", f"{tok_clean}{ext}"):
                        test_p = media_root / test_name
                        if test_p.is_file():
                            audio_cand = test_p
                            break
                    if audio_cand:
                        break
            if not audio_cand or not audio_cand.is_file():
                # Check candidate filenames matching snippet text hash
                snippet = (hist.get("text_snippet") or hist.get("full_text") or "").strip()
                if snippet:
                    import hashlib
                    h = hashlib.md5(snippet.encode("utf-8")).hexdigest()
                    for ext in (".mp3", ".m4a"):
                        test_p = media_root / f"{h}{ext}"
                        if test_p.is_file():
                            audio_cand = test_p
                            break
            if audio_cand and audio_cand.is_file():
                # Self-heal history record if path had differed
                try:
                    storage.update_audio_summary_history(hist["id"], audio_path=str(audio_cand), status="ready")
                except Exception:
                    pass
                return (audio_cand, hist.get("depth", "balanced"))
    except Exception:
        pass
    return None


def close_summary_audio_player(token: str | None = None) -> None:
    """Stop a spawned player and revoke its media capability."""
    with _media_lock:
        tokens = [token] if token else list(set(_player_processes) | set(_media))
        for item in tokens:
            if not item:
                continue
            proc = _player_processes.pop(item, None)
            _media.pop(item, None)
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass


def _purge_expired_locked() -> None:
    now = time.monotonic()
    for token, (path, expires, _depth) in list(_media.items()):
        if expires <= now or not path.is_file():
            _media.pop(token, None)


def player_url(token: str, *, base_url: str = "http://127.0.0.1:8991", depth: str = "balanced", title: str = "", style: str = "", autoplay: bool = True) -> str:
    params = {"id": token, "depth": depth}
    if title:
        params["title"] = title
    if style:
        params["style"] = style
    if autoplay:
        params["autoplay"] = "1"
    try:
        from voice_flow.storage import storage
        theme = str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower()
        if theme in ("dark", "light"):
            params["theme"] = theme
    except Exception:
        pass
    page = "audio-summary-player.classic.html" if style == "classic" else "audio-summary-player.html"
    return f"{base_url.rstrip('/')}/{page}?{urllib.parse.urlencode(params)}"


def launch_summary_audio_player(
    audio_path: str | Path,
    *,
    depth: str = "balanced",
    title: str = "",
    base_url: str = "http://127.0.0.1:8991",
    token: str | None = None,
    style: str = "",
    autoplay: bool = True,
) -> str:
    """Open the dedicated summary player and return its opaque media ID."""
    close_summary_audio_player()
    token = register_summary_audio(audio_path, depth=depth, token=token)
    url = player_url(token, base_url=base_url, depth=depth, title=title, style=style, autoplay=autoplay)
    env = os.environ.copy()
    env["VOICE_FLOW_API_BASE"] = base_url.rstrip("/")

    # Ensure PYTHONPATH contains src and venv site-packages
    curr_pythonpath = env.get("PYTHONPATH", "")
    new_pythonpath_parts = [_src_dir, str(_venv_site)]
    if curr_pythonpath:
        new_pythonpath_parts.append(curr_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(new_pythonpath_parts)

    python_bin = sys.executable
    if sys.platform.startswith("win"):
        candidates = [
            Path(_project_root) / ".venv" / "Scripts" / "pythonw.exe",
            Path(_project_root) / ".venv" / "Scripts" / "python.exe",
            Path(r"C:\Users\Asus\.gemini\antigravity\scratch\voice-flow\.venv\Scripts\pythonw.exe"),
            Path(r"C:\Users\Asus\.gemini\antigravity\scratch\voice-flow\.venv\Scripts\python.exe"),
            Path(r"C:\Users\Asus\.zcode\workspace\default\AI-Productivity-Flow\.venv\Scripts\pythonw.exe"),
            Path(r"C:\Users\Asus\.zcode\workspace\default\AI-Productivity-Flow\.venv\Scripts\python.exe"),
            Path(sys.executable).with_name("pythonw.exe"),
            Path(sys.executable),
        ]
        for cand in candidates:
            if cand.is_file():
                python_bin = str(cand)
                break
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            [python_bin, "-m", "voice_flow.audio_summary_player", token, depth, title],
            cwd=_src_dir,
            creationflags=flags,
            close_fds=True,
            env=env,
        )
        with _media_lock:
            _player_processes[token] = proc
        return token
    except OSError as exc:
        try:
            log_file = Path(data_dir()) / "audio_player_error.log"
            log_file.write_text(f"Failed to spawn audio player: {exc}\n", encoding="utf-8")
        except Exception:
            pass
        return token


CLASSIC_PLAYER_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Audio Flow Summary</title>
  <link rel="icon" type="image/x-icon" href="/assets/favicon.ico">
  <link rel="shortcut icon" href="/assets/favicon.ico">
  <link rel="icon" type="image/png" sizes="32x32" href="/assets/icon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/assets/icon-16.png">
  <script>
    if (!window.__API_BASE__) {
      const _p = new URLSearchParams(location.search);
      window.__API_BASE__ = _p.get('api') || (location.origin && location.origin !== 'null' && !location.origin.startsWith('file:') ? location.origin : 'http://127.0.0.1:8991');
    }
  </script>
  <style>
    :root {
      color-scheme: light;
      font-family: "Segoe UI Variable", "Segoe UI", Inter, -apple-system, sans-serif;
      --orange: #FF6A00;
      --orange-deep: #E85D04;
      --orange-soft: #FFE3D0;
      --orange-faint: #FFF5EE;
      --white: #FFFFFF;
      --offwhite: #FFF9F5;
      --ink: #241708;
      --ink-muted: #7A6354;
      --border: rgba(255, 106, 0, 0.22);
      --border-light: rgba(255, 106, 0, 0.12);
      --green: #12B76A;
      --red: #F04438;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      width: 100%; height: 100%; overflow: hidden;
      background: radial-gradient(circle at 10% 0%, #FFF5EE 0%, #FFFFFF 52%, #FFF0E5 100%);
      color: var(--ink);
      user-select: none;
      -webkit-user-select: none;
    }

    .pywebview-drag-region, .drag-region {
      -webkit-app-region: drag;
      cursor: grab;
    }
    .pywebview-drag-region:active, .drag-region:active {
      cursor: grabbing;
    }
    button, input, a, .no-drag {
      -webkit-app-region: no-drag;
      user-select: auto;
      cursor: default;
    }

    #app {
      position: relative;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* Top App Header with App Logo, Brand, Depth Pill, and History Toggle */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 10px;
      background: rgba(255, 255, 255, 0.94);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(14px);
      z-index: 10;
      flex-shrink: 0;
    }
    .brand-group {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .brand-logo {
      width: 17px;
      height: 17px;
      object-fit: contain;
      filter: drop-shadow(0 1px 3px rgba(255, 106, 0, 0.4));
      border-radius: 4px;
    }
    .brand-title {
      font-size: 10.5px;
      font-weight: 900;
      letter-spacing: 1.2px;
      color: var(--orange-deep);
    }
    .depth-badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1.5px 6px;
      border-radius: 999px;
      font-size: 8.5px;
      font-weight: 800;
      letter-spacing: 0.3px;
      background: var(--orange-faint);
      color: var(--orange-deep);
      border: 1px solid var(--border);
      text-transform: uppercase;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .btn-hdr {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border: 1px solid var(--border);
      background: var(--white);
      color: var(--ink);
      border-radius: 7px;
      padding: 2.5px 7px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }
    .btn-hdr:hover {
      background: var(--orange-faint);
      border-color: var(--orange);
      color: var(--orange-deep);
    }
    .btn-hdr.active {
      background: var(--orange);
      border-color: var(--orange-deep);
      color: var(--white);
    }
    .hist-badge {
      background: var(--orange-deep);
      color: var(--white);
      font-size: 8.5px;
      font-weight: 800;
      border-radius: 999px;
      padding: 1px 5px;
      min-width: 14px;
      text-align: center;
    }
    .btn-hdr.active .hist-badge {
      background: var(--white);
      color: var(--orange-deep);
    }

    /* Main Player Stage */
    main {
      flex: 1;
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 8px 14px 7px;
      overflow: hidden;
      min-height: 0;
    }

    /* Info Row & Titles */
    .summary-info {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .summary-title {
      font-size: 13.5px;
      font-weight: 800;
      color: var(--ink);
      line-height: 1.25;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .summary-sub {
      font-size: 10.5px;
      color: var(--ink-muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .status-row {
      display: flex;
      align-items: center;
      gap: 5px;
      margin-top: 2px;
      font-size: 10px;
      font-weight: 600;
      color: var(--ink-muted);
    }
    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--orange);
      transition: background-color 0.2s;
    }
    .status-dot.playing {
      background: var(--green);
      box-shadow: 0 0 8px rgba(18, 183, 106, 0.65);
      animation: pulseDot 1.4s infinite ease-in-out;
    }
    .status-dot.paused {
      background: var(--orange);
    }
    .status-dot.error {
      background: var(--red);
    }
    @keyframes pulseDot {
      0%, 100% { transform: scale(0.9); opacity: 0.8; }
      50% { transform: scale(1.3); opacity: 1.0; }
    }

    /* Dynamic Waveform Visualizer */
    .waveform-visualizer {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 2.5px;
      height: 18px;
      margin: 1px 0 2px;
    }
    .wave-bar {
      width: 3px;
      height: 3px;
      border-radius: 2px;
      background: var(--orange-soft);
      transition: height 0.1s ease, background-color 0.2s;
    }
    .waveform-visualizer.active .wave-bar {
      background: linear-gradient(180deg, var(--orange), var(--orange-deep));
      animation: waveDance 1.1s ease-in-out infinite alternate;
    }
    .wave-bar:nth-child(2n) { animation-delay: 0.08s; }
    .wave-bar:nth-child(3n) { animation-delay: 0.16s; }
    .wave-bar:nth-child(4n) { animation-delay: 0.24s; }
    .wave-bar:nth-child(5n) { animation-delay: 0.32s; }
    .wave-bar:nth-child(6n) { animation-delay: 0.40s; }
    @keyframes waveDance {
      0% { height: 3px; }
      100% { height: 16px; }
    }

    /* Timeline & Progress Bar */
    .scrubber-wrap {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .timeline {
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      height: 5px;
      border-radius: 999px;
      background: var(--orange-soft);
      outline: none;
      cursor: pointer;
      position: relative;
      transition: height 0.15s;
    }
    .timeline:hover {
      height: 7px;
    }
    .timeline::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 13px;
      height: 13px;
      border-radius: 50%;
      background: var(--white);
      border: 2.5px solid var(--orange-deep);
      box-shadow: 0 1px 4px rgba(232, 93, 4, 0.4);
      cursor: pointer;
      transition: transform 0.1s ease;
    }
    .timeline::-webkit-slider-thumb:hover {
      transform: scale(1.2);
    }
    .times {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      font-weight: 700;
      color: var(--ink-muted);
      font-variant-numeric: tabular-nums;
    }

    /* Playback Controls Row */
    .controls-row {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin: 1px 0;
    }
    .btn-ctrl {
      border: 1px solid var(--border);
      background: var(--white);
      color: var(--ink);
      border-radius: 10px;
      width: 36px;
      height: 30px;
      font-size: 11px;
      font-weight: 800;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s ease;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }
    .btn-ctrl:hover {
      border-color: var(--orange);
      background: var(--orange-faint);
      color: var(--orange-deep);
      transform: translateY(-1px);
    }
    .btn-ctrl:active {
      transform: translateY(1px);
    }
    .btn-play {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: none;
      background: linear-gradient(135deg, var(--orange) 0%, var(--orange-deep) 100%);
      color: var(--white);
      font-size: 16px;
      box-shadow: 0 4px 14px rgba(232, 93, 4, 0.38);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .btn-play:hover {
      transform: scale(1.06);
      box-shadow: 0 6px 18px rgba(232, 93, 4, 0.48);
    }
    .btn-play:active {
      transform: scale(0.96);
    }

    /* Speed and action footer */
    footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 3px;
      border-top: 1px solid var(--border-light);
      flex-shrink: 0;
    }
    .speed-group {
      display: flex;
      align-items: center;
      gap: 2px;
    }
    .btn-speed {
      border: 1px solid var(--border);
      background: var(--white);
      color: var(--ink-muted);
      border-radius: 5px;
      padding: 1px 4.5px;
      font-size: 9px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.12s ease;
    }
    .btn-speed:hover {
      border-color: var(--orange);
      color: var(--orange-deep);
      background: var(--orange-faint);
    }
    .btn-speed.active {
      background: var(--orange-deep);
      border-color: var(--orange-deep);
      color: var(--white);
    }
    .btn-dl {
      font-size: 9.5px;
      font-weight: 700;
      color: var(--orange-deep);
      text-decoration: none;
      padding: 2px 6px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--white);
      display: inline-flex;
      align-items: center;
      gap: 3px;
      transition: all 0.12s ease;
      cursor: pointer;
    }
    .btn-dl:hover {
      background: var(--orange-faint);
      border-color: var(--orange);
    }

    /* History Slide-Out Drawer matching Video Flow style */
    .history-drawer {
      position: absolute;
      inset: 0;
      background: rgba(255, 255, 255, 0.98);
      backdrop-filter: blur(16px);
      z-index: 50;
      display: flex;
      flex-direction: column;
      transform: translateY(100%);
      transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.12);
    }
    .history-drawer.open {
      transform: translateY(0);
    }
    .drawer-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      background: var(--white);
      flex-shrink: 0;
    }
    .drawer-title {
      font-size: 11.5px;
      font-weight: 800;
      color: var(--ink);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .drawer-close {
      border: 1px solid var(--border);
      background: var(--white);
      border-radius: 6px;
      padding: 2px 7px;
      font-size: 10.5px;
      font-weight: 700;
      cursor: pointer;
      color: var(--ink-muted);
    }
    .drawer-close:hover {
      color: var(--red);
      border-color: var(--red);
      background: #FFF2F2;
    }

    .drawer-content {
      flex: 1;
      overflow-y: auto;
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .drawer-content::-webkit-scrollbar {
      width: 5px;
    }
    .drawer-content::-webkit-scrollbar-thumb {
      background: var(--border);
      border-radius: 4px;
    }

    /* History Cards matching Video Flow pattern */
    .af-card {
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .af-card:hover {
      border-color: var(--orange);
      box-shadow: 0 3px 10px rgba(232, 93, 4, 0.08);
    }
    .af-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }
    .af-mode-chip {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 8.5px;
      font-weight: 800;
      background: var(--orange-faint);
      color: var(--orange-deep);
      border: 1px solid var(--border);
      text-transform: uppercase;
    }
    .af-card-time {
      font-size: 9.5px;
      color: var(--ink-muted);
    }
    .af-card-snippet {
      font-size: 11px;
      line-height: 1.3;
      color: var(--ink);
      font-weight: 600;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .af-card-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 2px;
      padding-top: 3px;
      border-top: 1px solid var(--border-light);
    }
    .af-card-actions-left {
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .af-btn-action {
      border: 1px solid var(--border);
      background: var(--white);
      color: var(--ink);
      border-radius: 6px;
      padding: 2px 7px;
      font-size: 10px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 3px;
      transition: all 0.12s ease;
    }
    .af-btn-action:hover {
      border-color: var(--orange);
      background: var(--orange-faint);
      color: var(--orange-deep);
    }
    .af-btn-action.play-btn {
      background: var(--orange);
      color: var(--white);
      border-color: var(--orange-deep);
    }
    .af-btn-action.play-btn:hover {
      background: var(--orange-deep);
    }
    .af-btn-action.danger:hover {
      color: var(--red);
      border-color: var(--red);
      background: #FFF2F2;
    }

    .empty-history {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 28px 12px;
      text-align: center;
      color: var(--ink-muted);
    }
    .empty-history-icon {
      font-size: 22px;
      opacity: 0.6;
    }
  </style>
</head>
<body>
  <div id="app">
    <!-- Header with logo, brand, depth badge, and history toggle -->
    <header class="pywebview-drag-region drag-region">
      <div class="brand-group pywebview-drag-region drag-region">
        <img src="/assets/logo.png" alt="Voice Flow" class="brand-logo" onerror="this.src='/assets/icon-32.png'">
        <span class="brand-title">AUDIO FLOW</span>
        <span class="depth-badge" id="depth">BALANCED</span>
      </div>
      <div class="header-actions no-drag">
        <button id="toggle-history" class="btn-hdr" onclick="toggleHistoryDrawer()" title="View audio summary history">
          <span>📜 History</span>
          <span id="hist-count" class="hist-badge">0</span>
        </button>
      </div>
    </header>

    <!-- Main Player Stage -->
    <main class="pywebview-drag-region drag-region">
      <div class="summary-info pywebview-drag-region drag-region">
        <h1 class="summary-title" id="player-title">Audio Overview</h1>
        <p class="summary-sub" id="player-snippet">Source-grounded spoken summary</p>
        <div class="status-row">
          <span class="status-dot" id="status-dot"></span>
          <span id="status">Loading audio…</span>
        </div>
      </div>

      <!-- Waveform Animation -->
      <div class="waveform-visualizer pywebview-drag-region drag-region" id="visualizer">
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
        <div class="wave-bar"></div>
      </div>

      <!-- Timeline scrubber -->
      <div class="scrubber-wrap no-drag">
        <input class="timeline" id="seek" type="range" min="0" max="0" value="0" step="0.1" aria-label="Seek audio">
        <div class="times">
          <span id="current">0:00</span>
          <span id="duration">0:00</span>
        </div>
      </div>

      <!-- Control buttons -->
      <div class="controls-row no-drag">
        <button class="btn-ctrl" id="back" title="Back 5 seconds">↶ 5</button>
        <button class="btn-play" id="play" title="Play">▶</button>
        <button class="btn-ctrl" id="forward" title="Forward 5 seconds">5 ↷</button>
        <button class="btn-ctrl" id="stop" title="Stop">■</button>
      </div>

      <!-- Speed Selector & Media download -->
      <footer class="no-drag">
        <div class="speed-group">
          <button class="btn-speed" data-rate="0.75">0.75×</button>
          <button class="btn-speed active" data-rate="1">1×</button>
          <button class="btn-speed" data-rate="1.25">1.25×</button>
          <button class="btn-speed" data-rate="1.5">1.5×</button>
          <button class="btn-speed" data-rate="1.75">1.75×</button>
          <button class="btn-speed" data-rate="2">2×</button>
        </div>
        <a class="btn-dl" id="download-btn" href="#" download title="Download audio as MP3">↓ MP3</a>
      </footer>
    </main>

    <!-- History Drawer (Toggle in / out) -->
    <div class="history-drawer no-drag" id="history-drawer">
      <div class="drawer-header">
        <div class="drawer-title">
          <span>🎧 Audio History</span>
          <span class="hist-badge" id="drawer-count">0</span>
        </div>
        <button class="drawer-close" onclick="toggleHistoryDrawer(false)">✕ Close</button>
      </div>
      <div class="drawer-content" id="history-list">
        <!-- Rendered history cards -->
      </div>
    </div>
  </div>

  <audio id="audio" preload="metadata"></audio>

  <script>
    const params = new URLSearchParams(location.search);
    const audioId = params.get('id') || '';
    const depthParam = params.get('depth') || 'balanced';
    const titleParam = params.get('title') || '';

    const audio = document.getElementById('audio');
    const play = document.getElementById('play');
    const seek = document.getElementById('seek');
    const status = document.getElementById('status');
    const statusDot = document.getElementById('status-dot');
    const currentEl = document.getElementById('current');
    const durationEl = document.getElementById('duration');
    const visualizer = document.getElementById('visualizer');
    const downloadBtn = document.getElementById('download-btn');
    const depthEl = document.getElementById('depth');
    const titleEl = document.getElementById('player-title');
    const snippetEl = document.getElementById('player-snippet');
    const historyDrawer = document.getElementById('history-drawer');
    const toggleHistBtn = document.getElementById('toggle-history');
    const histCountEl = document.getElementById('hist-count');
    const drawerCountEl = document.getElementById('drawer-count');
    const historyListEl = document.getElementById('history-list');

    let historyRecords = [];
    let isDrawerOpen = false;

    // Set initial depth & labels
    const formatDepth = d => {
      const s = String(d || 'balanced').toLowerCase().replace('_', ' ').replace('-', ' ');
      if (s.includes('short') || s.includes('quick')) return '⚡ Short';
      if (s.includes('deep')) return '◈ Deep Dive';
      return '✦ Balanced';
    };
    depthEl.textContent = formatDepth(depthParam);
    if (titleParam) {
      titleEl.textContent = titleParam;
      snippetEl.textContent = "NotebookLM spoken audio overview";
    }

    const fmt = s => {
      s = Math.max(0, Math.floor(s || 0));
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    };

    function safeMediaFilename(title, defaultName = 'Audio Summary', ext = '.mp3') {
      let cleaned = String(title || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().replace(/^[. ]+|[. ]+$/g, '');
      if (!cleaned) cleaned = defaultName;
      const upper = cleaned.toUpperCase();
      if (['CON', 'PRN', 'AUX', 'NUL'].includes(upper) || /^(COM|LPT)[1-9]$/.test(upper)) {
        cleaned += '_file';
      }
      if (cleaned.length > 120) cleaned = cleaned.slice(0, 120).trim().replace(/[. ]+$/, '');
      if (!ext.startsWith('.')) ext = '.' + ext;
      if (!cleaned.toLowerCase().endsWith(ext.toLowerCase())) {
        cleaned += ext;
      }
      return cleaned;
    }

    function loadAudioSource(id, depthLabel, snippetText, customTitle) {
      if (!id) {
        status.textContent = 'Summary unavailable';
        statusDot.className = 'status-dot error';
        return;
      }
      const apiBase = (window.__API_BASE__ || '').replace(/\/$/, '');
      const currentTitle = customTitle || titleParam || (titleEl ? titleEl.textContent : '') || snippetText || 'Audio Summary';
      const cleanFileName = safeMediaFilename(currentTitle, 'Audio Summary', '.mp3');
      const mediaUrl = `${apiBase}/api/audio-flow/summary/media?id=${encodeURIComponent(id)}`;
      audio.src = mediaUrl;
      audio.load();
      downloadBtn.href = `${mediaUrl}&download=1&format=mp3&title=${encodeURIComponent(currentTitle)}`;
      downloadBtn.download = cleanFileName;
      downloadBtn.title = `Download "${currentTitle}" as MP3`;
      if (depthLabel) depthEl.textContent = formatDepth(depthLabel);
      if (snippetText) {
        snippetEl.textContent = snippetText;
      }
    }

    loadAudioSource(audioId, depthParam, titleParam);

    audio.addEventListener('loadedmetadata', () => {
      seek.max = audio.duration || 0;
      durationEl.textContent = fmt(audio.duration);
      status.textContent = 'Ready';
      statusDot.className = 'status-dot';
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.then(() => {
          status.textContent = 'Playing';
          statusDot.className = 'status-dot playing';
          visualizer.classList.add('active');
        }).catch(() => {
          status.textContent = 'Ready — press Play to begin';
          statusDot.className = 'status-dot';
          visualizer.classList.remove('active');
        });
      }
    });

    audio.addEventListener('timeupdate', () => {
      seek.value = audio.currentTime || 0;
      currentEl.textContent = fmt(audio.currentTime);
      const pct = (audio.duration > 0) ? (audio.currentTime / audio.duration * 100) : 0;
      seek.style.background = `linear-gradient(90deg, var(--orange) ${pct}%, var(--orange-soft) ${pct}%)`;
    });

    audio.addEventListener('play', () => {
      play.textContent = '❚❚';
      play.title = 'Pause';
      status.textContent = 'Playing';
      statusDot.className = 'status-dot playing';
      visualizer.classList.add('active');
    });

    audio.addEventListener('pause', () => {
      play.textContent = '▶';
      play.title = 'Resume';
      if (audio.currentTime > 0 && !audio.ended) {
        status.textContent = 'Paused';
        statusDot.className = 'status-dot paused';
      }
      visualizer.classList.remove('active');
    });

    audio.addEventListener('ended', () => {
      status.textContent = 'Finished';
      statusDot.className = 'status-dot';
      seek.value = 0;
      visualizer.classList.remove('active');
    });

    audio.addEventListener('error', () => {
      const code = audio.error ? audio.error.code : 0;
      let msg = 'Audio is unavailable';
      if (code === 4) msg = 'Audio format not supported or media not found';
      else if (code === 2) msg = 'Network error loading audio';
      else if (code === 3) msg = 'Audio decode error';
      status.textContent = msg;
      statusDot.className = 'status-dot error';
      visualizer.classList.remove('active');
    });

    play.onclick = () => {
      if (audio.paused) {
        const p = audio.play();
        if (p !== undefined) {
          p.catch(err => {
            console.warn('Audio play failed:', err);
            status.textContent = 'Playback error: ' + (err.message || 'cannot play');
            statusDot.className = 'status-dot error';
          });
        }
      } else {
        audio.pause();
      }
    };

    seek.oninput = () => {
      if (Number.isFinite(audio.duration)) {
        audio.currentTime = Number(seek.value);
      }
    };

    document.getElementById('back').onclick = () => {
      if (Number.isFinite(audio.duration)) audio.currentTime = Math.max(0, audio.currentTime - 5);
    };

    document.getElementById('forward').onclick = () => {
      if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration, audio.currentTime + 5);
    };

    document.getElementById('stop').onclick = () => {
      audio.pause();
      audio.currentTime = 0;
      status.textContent = 'Stopped';
      statusDot.className = 'status-dot';
      visualizer.classList.remove('active');
    };

    document.querySelectorAll('[data-rate]').forEach(btn => {
      btn.onclick = () => {
        audio.playbackRate = Number(btn.dataset.rate);
        document.querySelectorAll('[data-rate]').forEach(b => b.classList.toggle('active', b === btn));
      };
    });

    // Native smooth window dragging support
    document.addEventListener('mousedown', (e) => {
      if (e.target.closest('button, input, a, .no-drag, .af-card, .drawer-content, .timeline')) return;
      if (e.button === 0 && window.pywebview?.api?.start_drag) {
        window.pywebview.api.start_drag();
      }
    });

    // History Toggle & Management
    function toggleHistoryDrawer(forceState) {
      if (typeof forceState === 'boolean') {
        isDrawerOpen = forceState;
      } else {
        isDrawerOpen = !isDrawerOpen;
      }
      historyDrawer.classList.toggle('open', isDrawerOpen);
      toggleHistBtn.classList.toggle('active', isDrawerOpen);
      if (isDrawerOpen) {
        fetchHistory();
      }
    }

    async function fetchHistory() {
      try {
        const apiBase = (window.__API_BASE__ || '').replace(/\/$/, '');
        const res = await fetch(`${apiBase}/api/audio-flow/history`);
        if (!res.ok) return;
        const data = await res.json();
        if (data && Array.isArray(data.summaries)) {
          historyRecords = data.summaries;
          renderHistoryList();
        }
      } catch (_) {}
    }

    function renderHistoryList() {
      const count = historyRecords.length;
      histCountEl.textContent = count;
      drawerCountEl.textContent = count;

      if (!count) {
        historyListEl.innerHTML = `
          <div class="empty-history">
            <div class="empty-history-icon">🎧</div>
            <strong style="font-size:12px;">No audio summaries yet</strong>
            <span style="font-size:10.5px;">Summaries you create will appear here for easy playback.</span>
          </div>`;
        return;
      }

      const apiBase = (window.__API_BASE__ || '').replace(/\/$/, '');
      historyListEl.innerHTML = historyRecords.map(item => {
        const dFmt = formatDepth(item.depth);
        let dateStr = '';
        try {
          const d = new Date(item.created_at);
          dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
                    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        } catch (_) {
          dateStr = item.created_at || '';
        }
        const snippetSafe = (item.text_snippet || 'Audio summary').replace(/"/g, '&quot;');
        const itemTitle = item.title || item.text_snippet || 'Audio summary';
        const titleSafe = itemTitle.replace(/"/g, '&quot;');
        const cleanItemFile = safeMediaFilename(itemTitle, 'Audio Summary', '.mp3');
        const dlUrl = `${apiBase}/api/audio-flow/summary/media?id=${encodeURIComponent(item.id)}&download=1&format=mp3&title=${encodeURIComponent(itemTitle)}`;
        return `
          <div class="af-card" data-id="${item.id}">
            <div class="af-card-header">
              <span class="af-mode-chip">${dFmt}</span>
              <span class="af-card-time">${dateStr}</span>
            </div>
            <div class="af-card-snippet" title="${titleSafe}">${snippetSafe}</div>
            <div class="af-card-actions">
              <span style="font-size:10px;color:var(--ink-muted);font-weight:700;">${item.duration_sec ? fmt(item.duration_sec) : ''}</span>
              <div class="af-card-actions-left">
                <button class="af-btn-action play-btn" onclick="playFromHistory('${item.id}', '${item.depth}', '${snippetSafe}', '${titleSafe.replace(/'/g, "\\'")}')">▶ Play</button>
                <a class="af-btn-action" href="${dlUrl}" download="${cleanItemFile}" title="Download '${titleSafe}' as MP3">↓ MP3</a>
                <button class="af-btn-action danger" onclick="deleteHistoryItem('${item.id}')" title="Delete">⌫</button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    window.playFromHistory = (id, depth, snippet, title) => {
      const activeTitle = title || snippet || 'Audio Summary';
      loadAudioSource(id, depth, snippet, activeTitle);
      titleEl.textContent = activeTitle.slice(0, 42) + (activeTitle.length > 42 ? '…' : '');
      toggleHistoryDrawer(false);
      audio.play().catch(() => {});
    };

    window.deleteHistoryItem = async (id) => {
      if (!confirm('Delete this audio summary from history?')) return;
      try {
        const apiBase = (window.__API_BASE__ || '').replace(/\/$/, '');
        const res = await fetch(`${apiBase}/api/audio-flow/history/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id }),
        });
        if (res.ok) {
          historyRecords = historyRecords.filter(r => r.id !== id);
          renderHistoryList();
        }
      } catch (_) {}
    };

    // Fetch initial count
    fetchHistory();
  </script>
</body>
</html>
"""
_gui_dir = Path(__file__).resolve().parent / "gui"


def get_player_html(classic: bool = False) -> str:
    """Return HTML content for the audio summary player (modern by default, or classic)."""
    filename = "audio-summary-player.classic.html" if classic else "audio-summary-player.html"
    p = _gui_dir / filename
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            pass
    return CLASSIC_PLAYER_HTML


PLAYER_HTML = get_player_html(classic=False)


class AudioSummaryPlayerApi:
    """Python bridge exposed to JS in webview to enable silky-smooth native OS window dragging."""

    def __init__(self, window=None) -> None:
        pass

    def start_drag(self) -> bool:
        """Trigger native Win32 window dragging so user can move the window smoothly anywhere."""
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            hwnd = _get_player_hwnd()
            if hwnd:
                user32 = ctypes.windll.user32
                user32.ReleaseCapture()
                user32.PostMessageW(hwnd, 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
                return True
        except Exception:
            pass
        return False


def _get_player_hwnd(window=None) -> int | None:
    """Find native HWND for the audio summary player window safely without Python.NET interop issues."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    user32 = ctypes.windll.user32

    # 1. Direct title match
    hwnd = user32.FindWindowW(None, "Audio Flow Summary")
    if hwnd:
        return hwnd

    # 2. Match by current process PID and window title substring
    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    candidates = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _enum_proc(h, _l):
        p = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value
                if "Audio Flow" in title or "Summary" in title:
                    candidates.append(h)
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
    except Exception:
        pass
    if candidates:
        return candidates[0]
    return None


def _apply_player_icon(window=None) -> None:
    """Explicitly assign our application icon to the native window HWND and taskbar on Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from voice_flow.installer import get_icon_path

        ico = get_icon_path()
        if not ico.exists():
            return
        ico_path = str(ico.resolve())
        user32 = ctypes.windll.user32
        hwnd = _get_player_hwnd(window)

        if not hwnd:
            return

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        sm_cx = user32.GetSystemMetrics(49)  # SM_CXSMICON
        sm_cy = user32.GetSystemMetrics(50)  # SM_CYSMICON
        lg_cx = user32.GetSystemMetrics(11)  # SM_CXICON
        lg_cy = user32.GetSystemMetrics(12)  # SM_CYICON

        hicon_sm = user32.LoadImageW(0, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE)
        hicon_lg = user32.LoadImageW(0, ico_path, IMAGE_ICON, lg_cx, lg_cy, LR_LOADFROMFILE)

        if hicon_sm:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
        if hicon_lg:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
    except Exception:
        pass


def main() -> None:
    if len(sys.argv) < 2:
        return

    # Windows AppUserModelID matching desktop launcher so taskbar groups properly and uses our icon
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("antigravity.voiceflow.desktop.1.0")
        except Exception:
            pass

    token = sys.argv[1]
    depth = sys.argv[2] if len(sys.argv) >= 3 else "balanced"
    title = sys.argv[3] if len(sys.argv) >= 4 else ""
    base_url = os.environ.get("VOICE_FLOW_API_BASE", "http://127.0.0.1:8991").rstrip("/")
    url = player_url(token, base_url=base_url, depth=depth, title=title)

    ico_str = None
    try:
        from voice_flow.installer import get_icon_path
        ico = get_icon_path()
        if ico.exists():
            ico_str = str(ico.resolve())
    except Exception:
        pass

    try:
        import webview

        api = AudioSummaryPlayerApi()
        bg_color = "#0c0d12"
        try:
            from voice_flow.storage import storage
            theme = str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower()
            if theme == "light":
                bg_color = "#FFFFFF"
        except Exception:
            pass

        # Compact, sleek dimensions: 430 x 310 (min 360 x 260)
        win = webview.create_window(
            "Audio Flow Summary",
            url=url,
            width=430,
            height=310,
            min_size=(360, 260),
            resizable=True,
            on_top=True,
            background_color=bg_color,
            js_api=api,
        )

        def _on_shown():
            _apply_player_icon()

        try:
            win.events.shown += _on_shown
        except Exception:
            pass

        if ico_str:
            webview.start(icon=ico_str, debug=False, private_mode=False)
        else:
            webview.start(debug=False, private_mode=False)
    except Exception as exc:
        try:
            import traceback
            log_file = Path(data_dir()) / "audio_player_error.log"
            log_file.write_text(f"Audio summary player error: {exc}\n{traceback.format_exc()}\n", encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    main()
