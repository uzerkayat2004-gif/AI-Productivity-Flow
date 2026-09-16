"""Local REST API Server serving real SQLite database data and hardware info
to the Voice Flow Desktop GUI.
"""

from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any
if sys.stdout is None:
    class DummyWriter:
        encoding = "utf-8"
        errors = "replace"
        def write(self, x): pass
        def flush(self): pass
        def isatty(self): return False
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
import sounddevice as sd

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.provider_registry import get_all_provider_specs, get_provider_spec
from voice_flow.provider_validation import validate_provider_key
from voice_flow.storage import storage
from voice_flow.style_engine import (
    CATEGORY_DEFAULTS,
    STYLE_OPTIONS,
    STYLE_PRESETS,
    STYLE_PRESETS_BY_CATEGORY,
    style_engine,
)
from voice_flow.native_settings import get_launch_at_login, set_launch_at_login
from voice_flow.storage import DB_PATH
from voice_flow.video_flow_oauth import (
    ANTIGRAVITY_CLIENT_ID,
    ANTIGRAVITY_CLIENT_SECRET,
    OAuthError,
    _http_json,
    clear_pending,
    encrypt_token,
    load_code_assist_project,
    load_pending,
)
from voice_flow.video_flow_providers import video_flow_provider_service
from voice_flow.paths import data_dir
from voice_flow.recovery import AudioArchive, AUDIO_RETENTION_SECONDS, MIN_RETRY_SECONDS
from voice_flow.video_flow_documents import extract_document_text
from voice_flow.runtime_contract import RUNTIME_CONTRACT_VERSION, RUNTIME_FEATURES
from voice_flow.runtime_guard import runtime_is_compatible
from voice_flow.video_flow_service import get_video_flow_service

GUI_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8991
MAX_JSON_BODY_BYTES = 64 * 1024
MAX_VAULT_BODY_BYTES = 10 * 1024 * 1024
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", "http://127.0.0.1:3000", "http://localhost:3000", "app://voice-flow"}
# Providers the STT engine (stt_engines._ADAPTERS) can route to. The STT
# picker must not offer anything outside this set: a saved unsupported model
# fails at dictation time and silently falls back to local whisper.
STT_CAPABLE_PROVIDERS = {"groq", "openai", "deepgram", "elevenlabs", "gemini", "google", "assemblyai", "speechmatics", "nvidia", "nvidia_nim"}
# Settings the generic /api/settings/update endpoint must not touch — a wrong
# value here corrupts catalogs/migrations; each has its own endpoint instead.
PROTECTED_SETTING_KEYS = {
    "seed_version",
    "dictionary_revision",
    "lexicon_migration_v1",
    "voice_flow_stt_model",
    "voice_flow_polish_model",
}
SAFE_JOB_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]+$")


def _polishing_enabled() -> bool:
    """Read the persisted switch without treating a legacy string as truthy."""
    try:
        value = storage.get_setting("polishing_enabled", True)
    except Exception:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return value == 1

PROVIDER_ALIASES = {
    "agy": "antigravity",
    "codex": "openai_codex",
    "chatgpt": "openai_codex",
    "nim": "nvidia_nim",
    "nvidia": "nvidia_nim",
    "vx": "vertex_ai",
    "vertex": "vertex_ai",
    "zen": "opencode_zen",
    "claude-code": "claude_code",
    "claude": "anthropic",
    "lmstudio": "lm_studio",
    "llamacpp": "llama_cpp",
    "google": "gemini",
    "googleai": "gemini",
    "together_ai": "together",
    "mistral_ai": "mistral",
    "deepseek_ai": "deepseek",
}


def _canonical_provider_for_kind(provider: str, kind: str = "auto") -> str:
    """Normalize provider aliases without collapsing distinct TTS services."""
    raw = str(provider or "").strip().lower()
    if str(kind or "auto").strip().lower() == "tts":
        # Google Cloud TTS and Gemini TTS use different endpoints/catalogs.
        # NVIDIA TTS is stored as "nvidia"; nvidia_nim/nim are the LLM aliases,
        # but callers sometimes pass them with kind="tts" — map both so the
        # NVIDIA TTS branch is actually reached.
        return {"googleai": "gemini", "nim": "nvidia", "nvidia_nim": "nvidia"}.get(raw, raw)
    return PROVIDER_ALIASES.get(raw, raw)


archive = AudioArchive()

_API_CACHE: dict[str, tuple[float, Any]] = {}
_API_CACHE_LOCK = threading.Lock()
_API_CACHE_TTL = 5.0


def _get_cached_response(key: str, fallback_keys: tuple[str, ...] = ()) -> tuple[bool, Any]:
    """Retrieve an unexpired entry from _API_CACHE if present."""
    now = time.time()
    with _API_CACHE_LOCK:
        for k in (key, *fallback_keys):
            if k in _API_CACHE:
                ts, data = _API_CACHE[k]
                if now - ts < _API_CACHE_TTL:
                    return True, data
                _API_CACHE.pop(k, None)
    return False, None


def _set_cached_response(keys: tuple[str, ...], data: Any) -> None:
    """Store an entry in _API_CACHE under the given keys."""
    now = time.time()
    with _API_CACHE_LOCK:
        for k in keys:
            _API_CACHE[k] = (now, data)


def invalidate_history_cache(key: str | None = None) -> None:
    """Clear or expire in-memory cached entries for history and insights."""
    with _API_CACHE_LOCK:
        if key is not None:
            _API_CACHE.pop(key, None)
            return
        keys_to_clear = [
            k for k in list(_API_CACHE.keys())
            if any(k.startswith(prefix) for prefix in ("/api/history", "history", "/api/insights", "insights"))
        ]
        if keys_to_clear:
            for k in keys_to_clear:
                _API_CACHE.pop(k, None)
        else:
            _API_CACHE.clear()


def _sync_active_storage() -> None:
    """Re-point the GUI storage singleton to the active account database.

    Called before every history/insights/dictionary read so that after an
    account login/logout/switch the dashboard always reads the same canonical
    database the dictation engine writes to. Only the app-wide singleton is
    re-pointed; tests substitute their own temp-backed engines and must stay
    isolated."""
    try:
        if not getattr(storage, "is_global_singleton", False):
            return
        if storage.repoint_if_needed():
            invalidate_history_cache()
    except Exception:
        pass

OAUTH_CALLBACK_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Authorization Successful</title>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f172a;
    color: #f8fafc;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    margin: 0;
  }
  .card {
    text-align: center;
    padding: 40px 32px;
    background: #1e293b;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    max-width: 420px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
  }
  .icon-circle {
    width: 64px;
    height: 64px;
    background: rgba(34, 197, 94, 0.15);
    border: 2px solid #22c55e;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 20px;
    color: #22c55e;
    font-size: 28px;
  }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 8px; color: #f8fafc; }
  p { font-size: 14px; color: #94a3b8; margin: 0 0 16px; line-height: 1.5; }
  code {
    display: block;
    font-family: ui-monospace, Consolas, monospace;
    font-size: 12px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px;
    margin: 16px 0;
    word-break: break-all;
    color: #cbd5e1;
  }
  button {
    background: #2563eb;
    color: #fff;
    border: 0;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }
  button:hover { background: #1d4ed8; }
  .hidden { display: none; }
</style>
</head>
<body>
<div class="card">
  <div class="icon-circle" id="vf-icon">✓</div>
  <h1 id="vf-heading">Authorization Successful!</h1>
  <p id="vf-detail">This window will close automatically...</p>
  <div id="vf-code-card" class="hidden">
    <p>Copy the authorization code below and paste it into Voice Flow:</p>
    <code id="vf-code-value"></code>
    <button id="vf-copy">Copy Code</button>
  </div>
</div>
<script>
(function () {
  var code = __OAUTH_CODE__;
  var state = __OAUTH_STATE__;
  var error = __OAUTH_ERROR__;
  var heading = document.getElementById("vf-heading");
  var detail = document.getElementById("vf-detail");
  var icon = document.getElementById("vf-icon");
  var card = document.getElementById("vf-code-card");
  var value = document.getElementById("vf-code-value");

  if (error) {
    icon.textContent = "✕";
    icon.style.borderColor = "#ef4444";
    icon.style.color = "#ef4444";
    icon.style.background = "rgba(239, 68, 68, 0.15)";
    heading.textContent = "Authorization Failed";
    detail.textContent = error;
  } else if (code) {
    // 9Router relay: hand the callback to the app through every available
    // channel — postMessage to the opener (popup mode), BroadcastChannel and
    // localStorage (system-browser tabs / desktop WebView windows that share
    // the same origin storage). The app exchanges the code server-side.
    var callbackData = { type: "oauth_callback", code: code, state: state, fullUrl: window.location.href, timestamp: Date.now() };
    if (window.opener && !window.opener.closed) {
      try { window.opener.postMessage({ type: "oauth_callback", data: callbackData }, window.location.origin); } catch (e) {}
      try { window.opener.postMessage({ type: "oauth_callback", data: callbackData }, "*"); } catch (e) {}
      try { window.opener.postMessage({ type: "OAUTH_CALLBACK_SUCCESS", code: code, state: state }, "*"); } catch (e) {}
    }
    try {
      var channel = new BroadcastChannel("oauth_callback");
      channel.postMessage({ type: "oauth_callback", code: code, state: state });
      channel.close();
    } catch (e) {}
    try {
      localStorage.setItem("oauth_callback", JSON.stringify(callbackData));
    } catch (e) {}
    heading.textContent = "Authorization Successful!";
    detail.textContent = "Completing sign-in...";
    // Popup mode: the opener (the app) completes the exchange itself and
    // closes this window, so fetching here would race it for the single-use
    // code. Only if the app clearly never finished does this page fall back
    // to self-completing; orphan tabs (no live opener) always self-complete.
    function selfComplete() {
      fetch("/api/video-flow/oauth/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code, state: state })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res && res.success) {
        var n = 3;
        detail.textContent = "Account connected (" + (res.email || "sign-in complete") + "). Closing in " + n + "...";
        var iv = setInterval(function () {
          n -= 1;
          if (n > 0) {
            detail.textContent = "Account connected. Closing in " + n + "...";
          } else {
            clearInterval(iv);
            try { window.close(); } catch (e) {}
            detail.textContent = "Account connected. You can close this window.";
          }
        }, 1000);
      } else {
        heading.textContent = "Sign-in could not be completed";
        detail.textContent = (res && res.error) || "Unknown error - use Copy Code below.";
        card.classList.remove("hidden");
        value.textContent = code;
      }
    }).catch(function () {
      card.classList.remove("hidden");
      value.textContent = code;
    });
    }
    if (window.opener && !window.opener.closed) {
      detail.textContent = "Finishing sign-in...";
      setTimeout(function () {
        if (!window.closed && window.opener && !window.opener.closed) {
          selfComplete();
        }
      }, 10000);
      return;
    }
    selfComplete();
  } else {
    heading.textContent = "No Authorization Code Received";
    detail.textContent = "Please close this window and try signing in again.";
  }

  var copyBtn = document.getElementById("vf-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      navigator.clipboard.writeText(value.textContent).then(function () {
        copyBtn.textContent = "Copied ✓";
        setTimeout(function () { copyBtn.textContent = "Copy Code"; }, 2000);
      });
    });
  }
})();
</script>
</body>
</html>"""

runtime_controller = None
PERMANENT_DELETE_CONFIRMATION = "DELETE"


def register_runtime_controller(controller) -> None:
    """Register the running engine without making the standalone API import it."""
    global runtime_controller
    runtime_controller = controller


def _read_notebooklm_storage_state(profile: str) -> tuple[bool, str | None, str | None, dict]:
    """Fast non-blocking read of local NotebookLM storage_state.json with retry on transient locks.

    Returns: (authenticated, email, storage_path_str, details)
    """
    home = Path.home()
    candidates: list[Path] = []
    canonical_exp: Path | None = None
    try:
        from voice_flow.video_flow_engine.notebooklm.config import (
            get_storage_state_path,
            get_storage_backup_path,
            CANONICAL_EXPERIMENT_STORAGE,
            DEFAULT_PROFILE,
        )
        p_path = get_storage_state_path(profile)
        if p_path and p_path not in candidates:
            candidates.append(p_path)
        b_path = get_storage_backup_path(profile)
        if b_path and b_path not in candidates:
            candidates.append(b_path)
        safe_path = p_path.with_name("storage_state.safe_copy.json")
        if safe_path and safe_path not in candidates:
            candidates.append(safe_path)
        canonical_exp = CANONICAL_EXPERIMENT_STORAGE
    except Exception:
        pass

    is_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not is_test:
        fallback_candidates = [
            home / ".notebooklm" / "profiles" / profile / "storage_state.json",
            home / ".notebooklm" / "profiles" / profile / "storage_state.backup.json",
            home / ".notebooklm" / "profiles" / profile / "storage_state.safe_copy.json",
        ]
        if profile == "default":
            fallback_candidates.extend([
                home / ".notebooklm" / "storage_state.json",
                home / ".notebooklm" / "storage_state.backup.json",
                home / ".notebooklm" / "storage_state.safe_copy.json",
            ])
        for p in fallback_candidates:
            if p not in candidates:
                candidates.append(p)

        if profile in ("video-flow-experiment", "default") and canonical_exp and canonical_exp not in candidates:
            candidates.append(canonical_exp)

    default_path = str(candidates[0]) if candidates else str(home / ".notebooklm" / "profiles" / profile / "storage_state.json")
    saved_email = storage.get_setting("video_flow_notebooklm_email")
    auth_setting = storage.get_setting("video_flow_notebooklm_authenticated")
    switched_from = storage.get_setting("video_flow_notebooklm_switched_from")
    if switched_from:
        switched_from = str(switched_from).strip().lower()

    explicit_disconnected = storage.get_setting("video_flow_notebooklm_disconnected")
    if explicit_disconnected in (True, "true", "True", 1, "1"):
        return False, None, default_path, {"disconnected": True}


    def _cookie_is_auth(cookie):
        if not isinstance(cookie, dict) or cookie.get("name") not in (
            "SID", "HSID", "SSID", "OSID", "__Secure-1PSID", "__Secure-3PSID"
        ):
            return False
        try:
            expires = float(cookie.get("expires") or 0)
        except (TypeError, ValueError):
            expires = 0
        return expires <= 0 or expires > time.time()

    last_existing_path = None
    for storage_path in candidates:
        if storage_path.is_file():
            last_existing_path = str(storage_path)
            state_data = None
            # Retry up to 3 times to handle momentary Windows file locks / writes
            for attempt in range(3):
                try:
                    with open(storage_path, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                    if isinstance(state_data, dict):
                        break
                except (PermissionError, OSError, json.JSONDecodeError):
                    if attempt < 2:
                        time.sleep(0.05)
                    continue
                except Exception:
                    break

            if isinstance(state_data, dict):
                cookies = state_data.get("cookies", [])
                nlm_info = state_data.get("notebooklm")
                account_info = (nlm_info.get("account") if isinstance(nlm_info, dict) else None) or state_data.get("account") or {}
                email = (account_info.get("email") if isinstance(account_info, dict) else None) or state_data.get("email") or saved_email

                if switched_from and email and str(email).strip().lower() == switched_from:
                    continue

                has_auth_cookies = any(_cookie_is_auth(c) for c in cookies) if isinstance(cookies, list) else False
                has_master = False
                try:
                    from voice_flow.video_flow_engine.notebooklm.login_flow import master_token_present
                    has_master = master_token_present(profile)
                except Exception:
                    has_master = False

                if has_auth_cookies or has_master or (email and auth_setting in (True, "true", "True", 1, "1")) or (email and auth_setting not in (False, "false", "False", 0, "0") and cookies):
                    # Auto-heal primary storage_state.json if reading from backup or safe copy
                    try:
                        primary_path = candidates[0]
                        if primary_path != storage_path:
                            primary_empty = True
                            if primary_path.is_file():
                                try:
                                    prim_d = json.loads(primary_path.read_text(encoding="utf-8"))
                                    if isinstance(prim_d, dict) and prim_d.get("cookies"):
                                        primary_empty = False
                                except Exception:
                                    pass
                            if primary_empty:
                                primary_path.parent.mkdir(parents=True, exist_ok=True)
                                primary_path.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
                    except Exception:
                        pass

                    psidts_exp = False
                    try:
                        from voice_flow.video_flow_engine.notebooklm.config import is_session_near_expiry
                        psidts_exp = is_session_near_expiry(profile)
                    except Exception:
                        pass

                    details = {
                        "account": {"email": email} if email else {},
                        "cookies_count": len(cookies) if isinstance(cookies, list) else 0,
                        "storage_path": str(storage_path),
                        "master_token_present": has_master,
                        "psidts_expired": psidts_exp,
                    }
                    try:
                        storage.save_setting("video_flow_notebooklm_authenticated", True)
                        if email:
                            storage.save_setting("video_flow_notebooklm_email", email)
                    except Exception:
                        pass
                    return True, email, str(storage_path), details

    default_path = last_existing_path or str(home / ".notebooklm" / "profiles" / profile / "storage_state.json")
    return False, None, default_path, {"disconnected": True}


def strip_redundant_model_prefix(provider: str, model_id: str) -> str:
    """Strip redundant provider prefixes while preserving required upstream namespaces."""
    provider = (provider or "").lower().strip()
    provider = PROVIDER_ALIASES.get(provider, provider)
    mid = (model_id or "").strip()
    if not mid:
        return ""

    # Specific multi-tenant / aggregator providers that require preserving namespaces:
    if provider == "openrouter":
        while mid.lower().startswith("openrouter/"):
            mid = mid[len("openrouter/"):].strip()
        return mid

    if provider in ("together", "together_ai"):
        while mid.lower().startswith(("together/", "together_ai/")):
            pfx = "together_ai/" if mid.lower().startswith("together_ai/") else "together/"
            mid = mid[len(pfx):].strip()
        return mid

    if provider in ("nvidia_nim", "nim", "nvidia"):
        # Strip nvidia_nim/ and nim/ but PRESERVE nvidia/ (upstream namespace)
        while mid.lower().startswith(("nvidia_nim/", "nim/")):
            pfx = "nvidia_nim/" if mid.lower().startswith("nvidia_nim/") else "nim/"
            mid = mid[len(pfx):].strip()
        return mid

    if provider == "cloudflare":
        # Strip cloudflare/ and cf/ but PRESERVE @cf/
        while mid.lower().startswith(("cloudflare/", "cf/")):
            pfx = "cloudflare/" if mid.lower().startswith("cloudflare/") else "cf/"
            mid = mid[len(pfx):].strip()
        return mid

    if provider.startswith("custom-"):
        pfx = f"{provider}/".lower()
        if mid.lower().startswith(pfx):
            mid = mid[len(pfx):].strip()
        return mid

    # Standard providers: build candidate prefixes to strip
    prefixes = [provider]
    for alias, canonical in PROVIDER_ALIASES.items():
        if canonical == provider and alias not in prefixes:
            if provider in ("nvidia_nim", "nim", "nvidia") and alias == "nvidia":
                continue
            prefixes.append(alias)

    if provider in ("gemini", "google", "googleai"):
        prefixes.extend(["gemini", "google", "googleai", "models"])
    elif provider in ("vertex_ai", "vx", "vertex"):
        prefixes.extend(["vertex_ai", "vx", "vertex", "publishers/google/models", "models"])
    elif provider in ("antigravity", "agy"):
        prefixes.extend(["antigravity", "agy", "models"])
    elif provider in ("openai_codex", "codex", "chatgpt"):
        prefixes.extend(["openai_codex", "chatgpt", "codex"])
    elif provider in ("anthropic", "claude"):
        prefixes.extend(["anthropic", "claude"])
    elif provider in ("deepseek", "deepseek_ai"):
        prefixes.extend(["deepseek", "deepseek_ai"])
    elif provider in ("mistral", "mistral_ai"):
        prefixes.extend(["mistral", "mistral_ai"])
    elif provider == "groq":
        prefixes.extend(["groq"])
    elif provider == "openai":
        prefixes.extend(["openai"])

    # Iteratively strip matched prefixes followed by "/"
    while True:
        stripped = False
        for pfx in prefixes:
            if not pfx:
                continue
            pfx_slash = pfx.lower() if pfx.endswith("/") else f"{pfx.lower()}/"
            if mid.lower().startswith(pfx_slash):
                mid = mid[len(pfx_slash):].strip()
                stripped = True
                break
        if not stripped:
            break

    if provider in ("gemini", "google", "googleai", "vertex_ai", "vx", "vertex", "antigravity", "agy"):
        while mid.lower().startswith("models/"):
            mid = mid[len("models/"):].strip()

    return mid


_MIC_VIRTUAL_PATTERNS = (
    "sound mapper",
    "primary sound",
    "stereo mix",
    "what u hear",
    "loopback",
    "pc speaker",
)


def _is_physical_microphone(name: str) -> bool:
    """True when a PortAudio device name looks like a real microphone.

    Filters out Windows virtual aliases (Sound Mapper, Primary Sound
    Capture), loopback taps (Stereo Mix), output endpoints leaked as
    inputs (PC Speaker), and WDM-KS raw driver strings
    (``Input (@System32\\drivers\\...)``) / empty ``Input ()`` ghosts.
    """
    low = (name or "").strip().lower()
    if not low or low in ("input", "input ()"):
        return False
    if "@system32" in low or ".sys" in low or "%1" in low:
        return False
    return not any(pat in low for pat in _MIC_VIRTUAL_PATTERNS)


class VoiceFlowApiHandler(SimpleHTTPRequestHandler):
    """Handles static GUI files + API endpoints (/api/history, /api/insights, /api/dictionary, /api/microphones, /api/apikeys)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress HTTP logging to prevent UnicodeEncodeError on Windows console

    def _server_port(self) -> int:
        try:
            address = self.server.server_address
            if isinstance(address, tuple):
                return int(address[1])
        except Exception:
            pass
        return 8991

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    def _discard_small_request_body(self) -> None:
        """Drain a bounded already-sent body after rejecting its headers."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if 0 < length <= MAX_JSON_BODY_BYTES:
                previous_timeout = self.connection.gettimeout()
                try:
                    self.connection.settimeout(0.05)
                    self.rfile.read(min(length, MAX_JSON_BODY_BYTES))
                except (TimeoutError, OSError):
                    pass
                finally:
                    self.connection.settimeout(previous_timeout)
        except (TypeError, ValueError):
            return

    def _host_is_allowed(self) -> bool:
        """DNS-rebinding guard: loopback Host only (port optional).

        Defensive by design: handlers built via __new__ in unit tests have no
        .headers, and some clients send a bare "127.0.0.1" Host -- both must
        pass through (missing headers / bare loopback host are allowed).
        """
        try:
            headers = getattr(self, "headers", None)
            if headers is None:
                return True
            host = (headers.get("Host") or "").lower().strip()
            if not host:
                return True
            bare = host.split(":")[0].strip().strip("[]")
            if bare in ("127.0.0.1", "localhost"):
                return True
            _port = self._server_port()
            return host in (f"127.0.0.1:{_port}", f"localhost:{_port}")
        except Exception:
            return True

    def _stream_summary_audio(
        self,
        audio_path: Path,
        *,
        is_download: bool = False,
        title: str | None = None,
        prefer_mp3: bool = True,
    ) -> None:
        """Serve an already-registered local summary with bounded HTTP Range support, exact title naming, and MP3 conversion."""
        try:
            from voice_flow.audio_summary_player import ensure_mp3_audio, safe_media_filename

            # If downloading or prefer_mp3, convert to genuine MP3
            if is_download or prefer_mp3:
                converted = ensure_mp3_audio(audio_path)
                if converted and converted.is_file() and converted.stat().st_size > 0:
                    audio_path = converted

            total = audio_path.stat().st_size
            if total <= 0:
                raise OSError("empty audio")
            start, end = 0, total - 1
            range_header = (self.headers.get("Range") or "").strip()
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                if not match:
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{total}"); self.end_headers(); return
                raw_start, raw_end = match.groups()
                if not raw_start:
                    suffix = int(raw_end or "0")
                    if suffix <= 0:
                        self.send_response(416); self.send_header("Content-Range", f"bytes */{total}"); self.end_headers(); return
                    start = max(0, total - suffix)
                else:
                    start = int(raw_start)
                    end = int(raw_end) if raw_end else end
                if start >= total or end < start:
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{total}"); self.end_headers(); return
                end = min(end, total - 1)
            length = end - start + 1

            ext = audio_path.suffix.lower()
            if ext == ".mp3":
                mime = "audio/mpeg"
            elif ext == ".m4a":
                mime = "audio/mp4"
            else:
                mime = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"

            self.send_response(206 if range_header else 200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("X-Content-Type-Options", "nosniff")
            if is_download:
                target_ext = ".mp3" if (ext == ".mp3" or prefer_mp3) else ext
                download_name = safe_media_filename(title or audio_path.stem, default="Audio Summary", ext=target_ext)
                quoted_name = urllib.parse.quote(download_name)
                ascii_name = re.sub(r"[^\x20-\x7E]", "_", download_name)
                self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted_name}')
            else:
                self.send_header("Content-Disposition", f'inline; filename="{audio_path.name}"')
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")
            self.send_header("Content-Security-Policy", "default-src 'none'; media-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.end_headers()
            with audio_path.open("rb") as media:
                media.seek(start)
                remaining = length
                while remaining:
                    chunk = media.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (OSError, ValueError):
            self.send_json_response({"success": False, "error": "Summary audio is unavailable"}, 404)

    def do_GET(self):
        global video_flow_provider_service
        if not self._host_is_allowed():
            self.send_json_response({"success": False, "error": "Invalid Host header"}, 403)
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Google sign-in (Video Flow authentication section). Must run before
        # the generic ?code= sniffer below: its callback also lands with
        # code+state in the query but serves its own flow.
        if path == "/auth/google":
            from voice_flow.google_auth import handle_google_signin
            handle_google_signin(self, port=self._server_port())
            return
        if path == "/auth/google/callback":
            from voice_flow.google_auth import handle_google_callback
            handle_google_callback(self, port=self._server_port())
            return
        if path == "/callback":
            from voice_flow.google_auth import handle_browser_callback
            handle_browser_callback(self, port=self._server_port())
            return
        if path == "/api/me":
            from voice_flow.google_auth import handle_me
            handle_me(self)
            return
        if path == "/api/platform/permissions":
            from voice_flow.platform import get_backend
            report = get_backend().permission_report()
            self.send_json_response({"success": True, **report.to_dict()})
            return
        if path == "/api/auth/status":
            _sync_active_storage()
            from voice_flow.account_manager import get_account_manager
            am = get_account_manager()
            active = am.get_active_account()
            accounts = am.list_accounts()
            is_placeholder = bool(active and active.get("email") == "primary@flow.local" and not active.get("google_id"))
            if not is_placeholder:
                filtered_accounts = [a for a in accounts if not (a.get("email") == "primary@flow.local" and not a.get("google_id"))]
            else:
                filtered_accounts = accounts
            self.send_json_response({
                "success": True,
                "authenticated": bool(active and not is_placeholder),
                "is_guest": is_placeholder,
                "active_account": active,
                "accounts": filtered_accounts,
            })
            return

        if path == "/api/auth/google/status":
            from voice_flow.google_auth import check_pairing_status
            from voice_flow.account_manager import get_account_manager
            qs = urllib.parse.parse_qs(parsed.query)
            token = str(qs.get("pair_token", [""])[0])
            st = check_pairing_status(token)
            am = get_account_manager()
            active = am.get_active_account()
            accounts = am.list_accounts()
            is_placeholder = bool(active and active.get("email") == "primary@flow.local" and not active.get("google_id"))
            if not is_placeholder:
                filtered_accounts = [a for a in accounts if not (a.get("email") == "primary@flow.local" and not a.get("google_id"))]
            else:
                filtered_accounts = accounts
            self.send_json_response({
                "success": True,
                "claimed": bool(st.get("claimed")),
                "authenticated": bool(active and not is_placeholder),
                "is_guest": is_placeholder,
                "active_account": active,
                "accounts": filtered_accounts,
            })
            return

        if "code" in urllib.parse.parse_qs(parsed.query):
            # OAuth popup callback landing: Google's loopback redirect arrives
            # at "/?code=...&state=..." with no API path.
            self._serve_oauth_callback()
            return

        if path in ("/audio-summary-player.html", "/audio-summary-player.classic.html"):
            from voice_flow.audio_summary_player import get_player_html
            q = urllib.parse.parse_qs(parsed.query)
            style_param = (q.get("style", [""])[0] or "").lower()
            is_classic = path.endswith(".classic.html") or style_param == "classic"
            raw_html = get_player_html(classic=is_classic)
            api_base = f"http://127.0.0.1:{self._server_port()}"
            injected_html = raw_html.replace(
                "<head>",
                f'<head><script>window.__API_BASE__ = "{api_base}";</script>',
                1,
            )
            body = injected_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/audio-flow/summary/media":
            q = urllib.parse.parse_qs(parsed.query)
            token = (q.get("id", [""])[0] or "").strip()
            is_dl = bool(q.get("download", ["0"])[0] in ("1", "true"))
            title_param = (q.get("title", [""])[0] or "").strip()
            from voice_flow.audio_summary_player import resolve_summary_audio
            resolved = resolve_summary_audio(token)
            if not resolved:
                self.send_json_response({"success": False, "error": "Summary audio is unavailable"}, 404)
                return
            audio_title = title_param or None
            if not audio_title:
                try:
                    hist_entry = storage.get_audio_summary_history_by_id(token)
                    if hist_entry:
                        audio_title = hist_entry.get("title") or hist_entry.get("text_snippet")
                except Exception:
                    pass
            self._stream_summary_audio(resolved[0], is_download=is_dl, title=audio_title)
            return

        if path == "/api/audio-flow/summary/status":
            token = (urllib.parse.parse_qs(parsed.query).get("id", [""])[0] or "").strip()
            from voice_flow.audio_summary_player import resolve_summary_audio
            self.send_json_response({"success": bool(resolve_summary_audio(token))}, 200 if resolve_summary_audio(token) else 404)
            return

        if path in ("/", "/index.html"):
            index_file = Path(GUI_DIR) / "index.html"
            if index_file.exists():
                theme = str(storage.get_setting("vf_theme", "dark") or "dark").strip().lower()
                if theme not in ("dark", "light"):
                    theme = "dark"
                raw_html = index_file.read_text(encoding="utf-8")
                # Pre-inject data-theme directly onto the root <html> element
                def _inject_theme_tag(m):
                    clean_attrs = re.sub(r'data-theme=["\'][^"\']*["\']', '', m.group(1)).strip()
                    if clean_attrs:
                        return f'<html {clean_attrs} data-theme="{theme}">'
                    return f'<html data-theme="{theme}">'
                raw_html = re.sub(r'<html\b([^>]*)>', _inject_theme_tag, raw_html, count=1)
                polishing_enabled = _polishing_enabled()
                if polishing_enabled:
                    raw_html = re.sub(
                        r'(<input[^>]*id=["\']toggle-polishing["\'][^>]*)>',
                        lambda m: (m.group(1) if re.search(r'\schecked(?=[\s/>]|$)', m.group(1)) else f"{m.group(1)} checked") + ">",
                        raw_html,
                        count=1,
                    )
                else:
                    raw_html = re.sub(
                        r'(<input[^>]*id=["\']toggle-polishing["\'][^>]*)>',
                        lambda m: re.sub(r'\s*\bchecked(?=[\s/>]|$)', '', m.group(1)) + ">",
                        raw_html,
                        count=1,
                    )
                body = raw_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", f"vf_theme={theme}; Path=/; Max-Age=31536000; SameSite=Lax")
                self.end_headers()
                self.wfile.write(body)
                return

        if path == "/api/reload-tts":
            if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
                self.send_json_response({"success": False, "error": "Cross-site requests are not allowed"}, 403)
                return
            try:
                # Reset the live singleton in place. importlib.reload would
                # mint a second TTSEngine while every `from ... import
                # tts_engine` snapshot (main.py, this server) keeps the old
                # instance — a split-brain where stop/pause miss live speech.
                # Provider settings are read from storage per synthesis, so
                # the reset engine picks up changes on the next speak().
                from voice_flow.tts_engine import tts_engine as _engine
                _engine.stop()
                self.send_json_response({"ok": True, "msg": "tts_engine reset (in place)"})
            except Exception as e:
                self.send_json_response({"ok": False, "error": str(e)})
        elif path == "/api/runtime":
            self.send_json_response({
                "name": "AI Productivity Flow",
                "contract_version": RUNTIME_CONTRACT_VERSION,
                "features": RUNTIME_FEATURES,
                "engine_ready": runtime_controller is not None,
            })
        elif path == "/api/overlay/status":
            overlay = getattr(runtime_controller, "overlay", None) if runtime_controller else None
            active = bool(getattr(overlay, "visible", True))
            state = str(getattr(overlay, "state", "READY"))
            dock = str(getattr(overlay, "dock", "bottom"))
            self.send_json_response({
                "active": active,
                "state": state,
                "dock": dock,
            })
        elif path in ("/api/overlay/show", "/api/overlay/reset-position"):
            overlay = getattr(runtime_controller, "overlay", None) if runtime_controller else None
            if overlay:
                if hasattr(overlay, "show"):
                    overlay.show()
                elif hasattr(overlay, "show_ready"):
                    overlay.show_ready()
                if hasattr(overlay, "reset_position"):
                    overlay.reset_position()
            self.send_json_response({"success": True, "message": "Floating bar shown and position reset"})
        elif path == "/api/settings/autostart/status":
            try:
                from voice_flow.installer import is_autostart_enabled
                stored = storage.get_setting("autostart_enabled", None)
                if stored is None:
                    enabled = is_autostart_enabled()
                    storage.save_setting("autostart_enabled", enabled)
                else:
                    enabled = bool(stored)
                self.send_json_response({"success": True, "enabled": enabled})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc), "enabled": False}, 500)
        elif path == "/api/settings/hotkey":
            settings = storage.get_hotkey_settings() if hasattr(storage, "get_hotkey_settings") else {
                "hotkey_trigger": storage.get_setting("hotkey_trigger", "ctrl_win"),
                "custom_hotkey": storage.get_setting("custom_hotkey", "Alt+Space"),
                "dictation_trigger_mode": storage.get_setting("dictation_trigger_mode", "hybrid"),
                "middle_click_enabled": bool(storage.get_setting("middle_click_enabled", True)),
                "ctrl_key_dictation_enabled": bool(storage.get_setting("ctrl_key_dictation_enabled", False)),
                "push_to_talk_shortcut": storage.get_setting("push_to_talk_shortcut", "Ctrl+Win"),
            }
            self.send_json_response({"success": True, **settings})
        elif path == "/api/settings/get":
            params = urllib.parse.parse_qs(parsed.query)
            key = (params.get("key", [""])[0] or "").strip()
            if not key:
                self.send_json_response({"success": False, "error": "Missing key parameter"}, 400)
                return
            if re.search(r"token|secret|password|api[_-]?key|credential", key, re.IGNORECASE):
                self.send_json_response({"success": False, "error": "Protected setting key"}, 403)
                return
            defaults = {
                "voice_flow_enabled": True,
                "audio_flow_enabled": True,
                "video_flow_enabled": True,
                "polishing_enabled": True,
                "press_enter_enabled": True,
                "has_viewed_onboarding": False,
                "has_celebrated_first_dictation": False,
                "click_to_paste_enabled": False,
                "push_to_talk_shortcut": "Ctrl+Win",
                "hotkey_trigger": "ctrl_win",
                "custom_hotkey": "Alt+Space",
                "custom_trigger_type": "hold",
                "middle_click_enabled": True,
                "ctrl_key_dictation_enabled": False,
                "dictation_trigger_mode": "hybrid",
                "autostart_enabled": True,
                "show_in_taskbar": True,
                "selected_mic_device": "",
                "voice_flow_polish_model": "local/deterministic",
                "voice_flow_polish_speed_mode": "balanced",
                "audio_flow_speed": 1.0,
            }
            default_val = defaults.get(key, None)
            val = storage.get_setting(key, default_val)
            self.send_json_response({"success": True, "key": key, "value": val})
        elif path == "/api/settings/theme":
            theme = str(storage.get_setting("vf_theme", "light") or "light").strip().lower()
            if theme not in ("dark", "light"):
                theme = "light"
            self.send_json_response({"success": True, "theme": theme})
        elif path == "/api/history":
            _sync_active_storage()
            hit, cached = _get_cached_response("/api/history", ("history",))
            if hit:
                self.send_json_response(cached)
            else:
                data = storage.get_recent_history()
                _set_cached_response(("/api/history", "history"), data)
                self.send_json_response(data)
        elif path == "/api/history/audio":
            try:
                record_id = int(urllib.parse.parse_qs(parsed.query).get("id", [""])[0])
            except (TypeError, ValueError):
                self.send_json_response({"success": False, "error": "Valid history id required"}, 400); return
            row = storage.get_history_record(record_id)
            path_ = archive.resolve(row.get("audio_path") if row else None)
            if not row or not path_ or not archive.available(row.get("audio_path"), _timestamp_epoch(row.get("timestamp"))):
                self.send_json_response({"success": False, "error": "Audio is unavailable"}, 404); return
            try:
                body = path_.read_bytes()
                self.send_response(200); self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Disposition", f'attachment; filename="voice-flow-{record_id}.wav"')
                self.send_header("Content-Length", str(len(body))); self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers(); self.wfile.write(body)
            except OSError:
                self.send_json_response({"success": False, "error": "Audio is unavailable"}, 404)
        elif path == "/api/dictionary/corrections":
            self.send_json_response(storage.get_dictionary_corrections())
        elif path == "/api/dictionary/suggestions":
            try:
                self.send_json_response(storage.get_lexicon_suggestions(20))
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/insights":
            _sync_active_storage()
            params = urllib.parse.parse_qs(parsed.query)
            range_val = params.get("range", ["all"])[0]
            if range_val == "all":
                cache_keys = ("/api/insights", "/api/insights:all", "insights", "insights:all")
            else:
                cache_keys = (f"/api/insights:{range_val}", f"insights:{range_val}", f"/api/insights?range={range_val}")
            hit, cached = _get_cached_response(cache_keys[0], cache_keys[1:])
            if hit:
                self.send_json_response(cached)
            else:
                data = storage.get_insights(range_filter=range_val)
                _set_cached_response(cache_keys, data)
                self.send_json_response(data)
        elif path == "/api/dictionary":
            _sync_active_storage()
            details = urllib.parse.parse_qs(parsed.query).get("details", [""])[0] in ("1", "true")
            include_auto = urllib.parse.parse_qs(parsed.query).get("include_auto", [""])[0] in ("1", "true")
            if details:
                self.send_json_response(storage.get_dictionary_entries(
                    include_auto=include_auto,
                    include_snippets=True,
                ))
            else:
                # Preserve the established lightweight string-list contract
                # for integrations while exposing every saved row.  Active
                # dictionary processing still excludes Auto-Captured rows;
                # the Dictionary UI uses ?details=1 to show provenance.
                self.send_json_response(storage.get_dictionary_words(
                    include_auto=True,
                    include_snippets=True,
                ))
        # ---- Video Flow shim (new engine; original public shape) ----
        elif path == "/api/video-flow/v3/program":
            params = urllib.parse.parse_qs(parsed.query)
            job_id = (params.get("id", [""])[0] or "").strip()
            # The Code2Video→Narova engine bakes narration/captions into a flat
            # MP4; there is no layered V3 program. The player's guard treats a
            # failed fetch as "play the MP4 directly".
            self.send_json_response({"success": False, "error": "Program data is not available for engine-rendered videos."}, 404)
        elif path == "/api/video-flow/v3/audio":
            params = urllib.parse.parse_qs(parsed.query)
            job_id = (params.get("id", [""])[0] or "").strip()
            scene_id = (params.get("scene", [""])[0] or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", job_id) or (scene_id and not re.fullmatch(r"[A-Za-z0-9_\-]+", scene_id)):
                self.send_error(404, "Audio file not found")
                return
            audio_dir = data_dir() / "v3_projects" / job_id / "audio"
            if scene_id:
                audio_path = audio_dir / f"{scene_id}.mp3"
            else:
                audio_path = next(iter(sorted(audio_dir.glob("*.mp3"))), None)
            if not audio_path or not audio_path.exists():
                self.send_error(404, "Audio file not found")
                return
            with open(audio_path, "rb") as af:
                data = af.read()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif path in ("/api/video-flow/v3/video", "/api/video-flow/v3/export/download"):
            params = urllib.parse.parse_qs(parsed.query)
            job_id = (params.get("id", [""])[0] or "").strip()
            req_title = (params.get("title", [""])[0] or "").strip() or None
            # The new engine's flat MP4 is both the render and the export.
            self._stream_shim_video(job_id, download=True, title=req_title)
        elif path == "/api/video-flow/v3/export":
            params = urllib.parse.parse_qs(parsed.query)
            job_id = (params.get("id", [""])[0] or "").strip()
            video_file = data_dir() / "v3_projects" / job_id / "video.mp4"
            if re.fullmatch(r"[A-Za-z0-9_\-]+", job_id) and video_file.exists() and video_file.stat().st_size > 0:
                dl_title_qs = ""
                try:
                    v_job = get_video_flow_service().get(job_id)
                    if v_job and v_job.meta and v_job.meta.get("title"):
                        dl_title_qs = f"&title={urllib.parse.quote(str(v_job.meta['title']))}"
                except Exception:
                    pass
                self.send_json_response({
                    "success": True,
                    "job_id": job_id,
                    "export_status": "exported",
                    "download_url": f"/api/video-flow/v3/export/download?id={job_id}{dl_title_qs}",
                })
            else:
                self.send_json_response({"success": False, "job_id": job_id, "export_status": "not_requested"}, 404)
        elif path in ("/api/video-flow/jobs/status", "/api/video-flow/status") or path.startswith("/api/video-flow/v3/status"):
            params = urllib.parse.parse_qs(parsed.query)
            video_id = (params.get("id", [""])[0] or params.get("job_id", [""])[0] or "").strip()
            job = None
            try:
                job = get_video_flow_service().get(video_id)
            except Exception:
                job = None
            if job is None:
                self.send_json_response({"success": False, "error": "Video not found"}, 404)
            else:
                video_data = _shim_video(job)
                self.send_json_response({
                    "success": True,
                    "video": video_data,
                    "timings": (job.meta or {}).get("timings") or {},
                })
        elif path.startswith("/api/video-flow/videos/thumb"):
            params = urllib.parse.parse_qs(parsed.query)
            video_id = (params.get("id", [""])[0] or "").strip()
            self.send_video_thumb(video_id)
        elif path.startswith("/api/video-flow/videos/file") or re.match(r"^/api/video-flow/videos/([^/]+)/file", path):
            m = re.match(r"^/api/video-flow/videos/([^/]+)/file", path)
            params = urllib.parse.parse_qs(parsed.query)
            if m:
                video_id = urllib.parse.unquote(m.group(1)).strip()
            else:
                video_id = (params.get("id", [""])[0] or "").strip()
            download = params.get("download", ["0"])[0] in ("1", "true")
            req_title = (params.get("title", [""])[0] or "").strip() or None
            self._stream_shim_video(video_id, download=download, title=req_title)
        elif path == "/api/video-flow/catalog":
            self.send_json_response(_video_flow_catalog())
        elif path == "/api/video-flow/voice":
            # Narration voice for Video Flow only: same TTS catalog Audio
            # Flow uses, independent selection (Audio Flow keeps its own).
            try:
                policy = storage.get_exec_audio_policy_options()
                self.send_json_response({
                    "success": True,
                    "active_voice": storage.get_setting("video_flow_voice_model", "edge/en-US-AvaNeural"),
                    "models": policy.get("models", []),
                    "grouped_models": policy.get("grouped_models", []),
                })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/history":
            self.send_json_response({"videos": [_shim_video(job) for job in get_video_flow_service().list()]})
        elif path == "/api/audio-flow/history":
            try:
                summaries = storage.get_audio_summary_history(limit=50)
                for s in summaries:
                    s_title = str(s.get("title") or s.get("text_snippet") or "Audio Summary").strip()
                    title_enc = urllib.parse.quote(s_title)
                    s["media_url"] = f"/api/audio-flow/summary/media?id={urllib.parse.quote(str(s['id']))}"
                    s["download_url"] = f"/api/audio-flow/summary/media?id={urllib.parse.quote(str(s['id']))}&download=1&format=mp3&title={title_enc}"
                self.send_json_response({"success": True, "summaries": summaries})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/providers":
            self.send_json_response(video_flow_provider_service.catalog())
        elif path == "/api/video-flow/providers/details":
            params = urllib.parse.parse_qs(parsed.query)
            provider_id = params.get("provider", [""])[0]
            try:
                self.send_json_response(video_flow_provider_service.provider_details(provider_id))
            except ValueError as exc:
                if provider_id.startswith("custom-"):
                    entry = next((cp for cp in storage.get_video_flow_custom_providers()
                                  if cp.get("id") == provider_id), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    else:
                        key = str(entry.get("api_key") or "")
                        masked = (key[:3] + "..." + key[-4:]) if len(key) > 8 else ("Key saved" if key else "")
                        models = []
                        for idx, m in enumerate(entry.get("models") or []):
                            mid = str(m.get("model_id") or "")
                            models.append({
                                "id": "m-" + str(idx), "provider": provider_id,
                                "model_id": mid,
                                "display_name": str(m.get("display_name") or mid),
                                "full_id": provider_id + "/" + mid,
                                "capabilities": [],
                                "is_active": m.get("is_active", True), "custom": True,
                                "available": bool(key),
                            })
                        self.send_json_response({
                            "provider": {"id": provider_id,
                                         "name": str(entry.get("name") or provider_id),
                                         "category": "api_key", "auth": "api_key",
                                         "prefix": provider_id, "icon": "\U0001f510",
                                         "description": "Custom OpenAI-compatible endpoint.",
                                         "get_key_url": "", "connection_count": 1,
                                         "active_count": 1,
                                         "status": "connected" if key else "disconnected"},
                            "connections": [
                                {
                                    "id": "c-" + str(ci),
                                    "provider": provider_id,
                                    "name": str(c.get("name") or (str(entry.get("name") or provider_id) + " key")),
                                    "auth_type": "api_key",
                                    "priority": ci + 1,
                                    "is_active": c.get("is_active", True),
                                    "status": c.get("status") or ("connected" if c.get("key") else "untested"),
                                    "metadata": {"base_url": str(entry.get("base_url") or "")},
                                    "secret_hint": ((str(c.get("key"))[:3] + "..." + str(c.get("key"))[-4:]) if len(str(c.get("key") or "")) > 8 else ("Key saved" if c.get("key") else "")),
                                    "has_secret": bool(c.get("key")),
                                }
                                for ci, c in enumerate(entry.get("api_keys") or (
                                    [{"name": str(entry.get("name") or provider_id) + " key",
                                      "key": key, "is_active": True,
                                      "status": "connected" if key else "untested"}] if key else []))
                            ],
                            "models": models,
                            "load_balance_mode": video_flow_provider_service.get_setting(f"load_balance:{provider_id}", str(entry.get("load_balance_mode") or "priority"))})
                else:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
        elif path == "/api/video-flow/notebooklm/status":
            try:
                from voice_flow.video_flow_engine.notebooklm import (
                    resolve_notebooklm_cli,
                    resolve_notebooklm_mcp,
                    resolve_notebooklm_profile,
                )
                params = urllib.parse.parse_qs(parsed.query)
                cli_param = None  # never accept client-supplied CLI paths (filesystem probe)
                profile_param = params.get("profile", [None])[0]
                cli_path = resolve_notebooklm_cli(cli_param)
                mcp_path = resolve_notebooklm_mcp()
                profile = resolve_notebooklm_profile(profile_param)
                if not cli_path and not mcp_path:
                    self.send_json_response({
                        "success": True,
                        "available": False,
                        "authenticated": False,
                        "status": "dependency_missing",
                        "profile": profile,
                        "cli_path": None,
                        "mcp_path": None,
                        "mcp_available": False,
                        "message": "NotebookLM CLI is not installed or configured.",
                    })
                else:
                    authenticated, email, storage_path, details = _read_notebooklm_storage_state(profile)
                    if not authenticated and not details.get("disconnected") and not os.environ.get("PYTEST_CURRENT_TEST"):
                        auth_saved = storage.get_setting("video_flow_notebooklm_authenticated")
                        saved_email = storage.get_setting("video_flow_notebooklm_email")
                        if auth_saved and auth_saved not in (False, "false", "False", 0, "0"):
                            try:
                                from voice_flow.video_flow_engine.notebooklm import browser_sync
                                sync_res = browser_sync.auto_sync_from_browser(
                                    profile=profile,
                                    expected_email=saved_email,
                                )
                                if sync_res.get("success"):
                                    authenticated, email, storage_path, details = _read_notebooklm_storage_state(profile)
                            except Exception:
                                pass
                    if authenticated and not details.get("disconnected") and not os.environ.get("PYTEST_CURRENT_TEST"):
                        try:
                            from voice_flow.video_flow_engine.notebooklm.config import is_session_near_expiry
                            if details.get("psidts_expired") or is_session_near_expiry(profile, threshold_seconds=86400.0):
                                from voice_flow.video_flow_engine.notebooklm import trigger_keepalive_now
                                trigger_keepalive_now(profile=profile, force=True, background=True)
                        except Exception:
                            pass
                    online_verified = None
                    if details.get("disconnected") or not authenticated:
                        authenticated = False
                        email = None
                        online_verified = False
                    elif params.get("verify", ["0"])[0] in ("1", "true"):
                        try:
                            from voice_flow.video_flow_engine.notebooklm import login_flow

                            force = params.get("force", ["0"])[0] in ("1", "true")
                            verification = login_flow.verify_online(profile=profile, force=force)
                            status_verdict = str(verification.get("status") or "").lower()
                            raw_details = (
                                str(verification.get("details_message") or "")
                                + " "
                                + str(verification.get("message") or "")
                                + " "
                                + str(verification.get("error") or "")
                            ).lower()
                            is_network_err = any(
                                token in raw_details
                                for token in (
                                    "timed out",
                                    "timeout",
                                    "connection",
                                    "network",
                                    "unreachable",
                                    "socket",
                                    "getaddrinfo",
                                )
                            )
                            is_auth_revocation = (
                                status_verdict in ("unauthenticated", "revoked", "expired")
                                or any(
                                    token in raw_details
                                    for token in (
                                        "auth_expired",
                                        "authentication expired",
                                        "auth expired",
                                        "expired or invalid",
                                        "not authenticated",
                                        "login expired",
                                        "unauthenticated",
                                        "401",
                                        "revoked",
                                        "re-authenticate",
                                        "psidts",
                                    )
                                )
                            )
                            if status_verdict == "ok" and verification.get("authenticated"):
                                online_verified = True
                                if not email and verification.get("email"):
                                    email = verification.get("email")
                            elif not is_network_err and (is_auth_revocation or verification.get("authenticated") is False):
                                # Before declaring unauthenticated, attempt a silent headless refresh
                                healed = False
                                if not os.environ.get("PYTEST_CURRENT_TEST"):
                                    try:
                                        from voice_flow.video_flow_engine.notebooklm import browser_sync
                                        heal_res = browser_sync.sync_cookies_with_playwright(
                                            profile=profile,
                                            headless=True,
                                            expected_email=email,
                                            timeout_seconds=15,
                                        )
                                        if heal_res.get("success"):
                                            verification = login_flow.verify_online(profile=profile, force=True)
                                            if str(verification.get("status") or "").lower() == "ok":
                                                online_verified = True
                                                authenticated = True
                                                email = verification.get("email") or heal_res.get("email") or email
                                                healed = True
                                    except Exception:
                                        pass
                                if not healed:
                                    online_verified = False
                                    # Never log out the user if storage_state has cookies
                                    if not (storage_path and Path(storage_path).is_file() and details.get("cookies_count", 0) > 0):
                                        authenticated = False
                            else:
                                online_verified = None
                        except Exception:
                            online_verified = None

                    # Calculate cookie health and expiration
                    cookie_health = {"status": "healthy", "expires_in_seconds": None, "message": "Session healthy"}
                    if authenticated and storage_path and Path(storage_path).is_file():
                        try:
                            st_obj = json.loads(Path(storage_path).read_text(encoding="utf-8"))
                            cookies = st_obj.get("cookies", [])
                            now_ts = time.time()
                            min_expiry = None
                            for c in cookies:
                                c_name = c.get("name") or ""
                                if c_name in ("__Secure-1PSIDTS", "SID", "__Secure-1PSID") and not c_name.endswith("RTS"):
                                    exp = float(c.get("expires") or 0)
                                    if exp > 0:
                                        rem = exp - now_ts
                                        if min_expiry is None or rem < min_expiry:
                                            min_expiry = rem
                            if min_expiry is not None:
                                cookie_health["expires_in_seconds"] = max(0, int(min_expiry))
                                if min_expiry <= 0:
                                    cookie_health["status"] = "expiring_soon"
                                    cookie_health["message"] = "Token refresh recommended — click Sync Browser to refresh"
                                elif min_expiry < 7200:  # under 2 hours
                                    mins = max(1, int(min_expiry // 60))
                                    cookie_health["status"] = "expiring_soon"
                                    cookie_health["message"] = f"Session expiring in {mins}m — click Sync Browser to refresh"
                        except Exception:
                            pass
                    if online_verified is False and not authenticated:
                        cookie_health["status"] = "expired"
                        cookie_health["message"] = "Session disconnected — click Sync Browser or Log in to connect"

                    message = (
                        "Authenticated successfully" if authenticated
                        else ("Session disconnected — click Log in to NotebookLM" if details.get("disconnected")
                              else ("Google session is no longer valid — sign in again" if online_verified is False
                                    else "NotebookLM is not connected — please log in"))
                    )
                    try:
                        from voice_flow.video_flow_engine.notebooklm import login_flow

                        master_token_present = login_flow.master_token_present(profile)
                    except Exception:
                        master_token_present = None

                    try:
                        from voice_flow.video_flow_engine.notebooklm import get_keepalive_status
                        keepalive_info = get_keepalive_status()
                    except Exception:
                        keepalive_info = {"running": False}

                    if authenticated and master_token_present is False:
                        message = (
                            "Signed in, but one-time durable setup is not finished — "
                            "click Sign in once to stop repeated logins"
                        )
                    self.send_json_response({
                        "success": True,
                        "available": True,
                        "authenticated": authenticated,
                        "online_verified": online_verified,
                        "master_token_present": master_token_present,
                        "status": "ok" if authenticated else "unauthenticated",
                        "profile": profile,
                        "email": email,
                        "cli_path": str(cli_path) if cli_path else None,
                        "mcp_path": str(mcp_path) if mcp_path else None,
                        "mcp_available": bool(mcp_path),
                        "keepalive": keepalive_info,
                        "storage_path": storage_path,
                        "cookie_health": cookie_health,
                        "message": message,
                        "details": details,
                    })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/notebooklm/auth/state":
            try:
                from voice_flow.video_flow_engine.notebooklm import login_flow

                self.send_json_response({"success": True, "login": login_flow.get_login_state()})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/notebooklm/auth/browser-profiles":
            try:
                from voice_flow.video_flow_engine.notebooklm import browser_sync

                profiles = browser_sync.discover_browser_profiles()
                self.send_json_response({"success": True, "profiles": profiles})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/notebooklm/mcp/status":
            try:
                from voice_flow.video_flow_engine.notebooklm import get_mcp_server_info
                params = urllib.parse.parse_qs(parsed.query)
                profile = params.get("profile", [None])[0]
                info = get_mcp_server_info(profile=profile)
                self.send_json_response({"success": True, "mcp": info})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/notebooklm/mcp/config":
            try:
                from voice_flow.video_flow_engine.notebooklm import generate_mcp_config
                params = urllib.parse.parse_qs(parsed.query)
                profile = params.get("profile", [None])[0]
                cfg = generate_mcp_config(profile=profile)
                self.send_json_response({"success": True, "config": cfg})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/notebooklm/mcp/notebooks":
            try:
                from voice_flow.video_flow_engine.notebooklm import NotebookLMMcpClient
                params = urllib.parse.parse_qs(parsed.query)
                profile = params.get("profile", [None])[0]
                client = NotebookLMMcpClient(profile=profile)
                notebooks = client.list_notebooks()
                self.send_json_response({"success": True, "notebooks": notebooks, "count": len(notebooks)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
        elif path == "/api/video-flow/notebooklm/keepalive/status":
            try:
                from voice_flow.video_flow_engine.notebooklm import get_keepalive_status
                self.send_json_response({"success": True, "keepalive": get_keepalive_status()})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path in ("/api/video-flow/notebooklm/keepalive/refresh", "/api/video-flow/notebooklm/keepalive/check"):
            try:
                from voice_flow.video_flow_engine.notebooklm import get_keepalive_service
                params = urllib.parse.parse_qs(parsed.query)
                profile = params.get("profile", [None])[0]
                force = params.get("force", ["0"])[0] in ("1", "true")
                background = params.get("background", ["0"])[0] in ("1", "true")
                service = get_keepalive_service(profile)
                if background:
                    res = service.trigger_now(force=force, background=True)
                else:
                    res = service.run_once(force=force)
                self.send_json_response({"success": True, "result": res, "keepalive": service.status()})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/providers/catalog":
            specs = [s.to_dict() for s in get_all_provider_specs()]
            self.send_json_response({"providers": specs})
        elif path == "/api/providers/connections":
            all_conns = storage.get_all_provider_connections()
            # get_all_provider_connections() returns {provider: [conn, ...]}, so
            # the masking loop must walk the nested lists. Iterating the dict
            # directly yielded provider-name strings and leaked every key.
            for conns in (all_conns or {}).values():
                for item in conns:
                    if isinstance(item, dict):
                        if item.get("api_key"):
                            item["api_key"] = _mask_secret(str(item["api_key"]))
                        item.pop("data_json", None)
            self.send_json_response({"connections": all_conns})
        elif path == "/api/styles/catalog":
            catalog = {}
            for cat, presets_dict in STYLE_PRESETS_BY_CATEGORY.items():
                catalog[cat] = [
                    {"id": p.id, "name": p.name, "instruction": p.instruction}
                    for p in presets_dict.values()
                ]
            self.send_json_response(catalog)
        elif path == "/api/styles/effective":
            resolved = style_engine.last_resolved_style
            if resolved:
                self.send_json_response({
                    "app_name": resolved.app_name,
                    "category": resolved.category,
                    "style_id": resolved.style_id,
                    "style_label": resolved.style_label,
                    "provider_instruction": resolved.provider_instruction,
                })
            else:
                self.send_json_response({"app_name": None, "category": None, "style_id": None, "style_label": None})


        elif path == "/api/apikeys/list":
            _raw_keys = storage.get_all_api_keys()
            self.send_json_response({p: _mask_secret(str(k)) for p, k in _raw_keys.items()})
        elif path == "/api/providers/details":
            params = urllib.parse.parse_qs(parsed.query)
            provider = params.get("provider", ["gemini"])[0].lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                key = str(entry.get("api_key") or "")
                models = []
                for idx, m in enumerate(entry.get("models") or []):
                    mid = str(m.get("model_id") or "")
                    models.append({
                        "id": "m-" + str(idx),
                        "provider": provider,
                        "model_id": mid,
                        "display_name": str(m.get("display_name") or mid),
                        "full_id": provider + "/" + mid,
                        "capabilities": [],
                        "is_active": m.get("is_active", True),
                        "custom": True,
                        "available": bool(key),
                    })
                conns = [
                    {
                        "id": "c-" + str(ci),
                        "provider": provider,
                        "name": str(c.get("name") or (str(entry.get("name") or provider) + " key")),
                        "auth_type": "api_key",
                        "priority": ci + 1,
                        "is_active": c.get("is_active", True),
                        "status": c.get("status") or ("connected" if c.get("key") else "untested"),
                        "last_tested_status": c.get("status") or ("Connected" if c.get("key") else "Not Tested"),
                        "metadata": {"base_url": str(entry.get("base_url") or "")},
                        "secret_hint": ((str(c.get("key"))[:3] + "..." + str(c.get("key"))[-4:]) if len(str(c.get("key") or "")) > 8 else ("Key saved" if c.get("key") else "")),
                        "has_secret": bool(c.get("key")),
                    }
                    for ci, c in enumerate(entry.get("api_keys") or (
                        [{"name": str(entry.get("name") or provider) + " key", "key": key, "is_active": True, "status": "connected" if key else "untested"}] if key else []
                    ))
                ]
                mode = storage.get_provider_load_balance_mode(provider)
                self.send_json_response({
                    "provider": {
                        "id": provider,
                        "name": str(entry.get("name") or provider),
                        "category": "api_key",
                        "auth": "api_key",
                        "prefix": provider,
                        "icon": "🔌",
                        "description": "Custom API endpoint.",
                        "get_key_url": "",
                        "connection_count": len(conns),
                        "status": "connected" if key else "disconnected",
                    },
                    "connections": conns,
                    "mode": mode,
                    "load_balance_mode": mode,
                    "models": models,
                })
                return

            conns = storage.get_provider_connections(provider)
            mode = storage.get_provider_load_balance_mode(provider)
            models = storage.get_provider_models(provider)
            # Mask stored secrets; the loopback page never needs the raw key.
            for item in conns:
                if isinstance(item, dict):
                    if item.get("api_key"):
                        item["api_key"] = _mask_secret(str(item["api_key"]))
                    # data_json embeds the raw {"apiKey": ...} payload, which
                    # would otherwise defeat the mask applied above.
                    item.pop("data_json", None)
            self.send_json_response({
                "provider": provider,
                "connections": conns,
                "mode": mode,
                "load_balance_mode": mode,
                "models": models
            })
        elif path == "/api/providers/overview":
            all_conns = storage.get_all_provider_connections()
            for conns in (all_conns or {}).values():
                for item in conns:
                    if isinstance(item, dict):
                        if item.get("api_key"):
                            item["api_key"] = _mask_secret(str(item["api_key"]))
                        item.pop("data_json", None)
            for cp in storage.get_voice_flow_custom_providers():
                pid = cp.get("id")
                has_key = bool(str(cp.get("api_key") or "").strip()) or any(bool(k.get("key")) for k in (cp.get("api_keys") or []))
                all_conns[pid] = [
                    {"id": "c-0", "name": cp.get("name"), "is_active": True if has_key else False, "api_key": "Key saved" if has_key else ""}
                ]
            self.send_json_response({"connections": all_conns, "custom_providers": _public_custom_providers(storage.get_voice_flow_custom_providers())})
        elif path == "/api/microphones":
            try:
                devices = sd.query_devices()
                # One row per physical mic: group aliases of the same
                # hardware (MME/DirectSound/WASAPI copies share a
                # normalized name) and report the most stable host API
                # for capture. WDM-KS kernel rows are excluded outright
                # (raw ghosts like "Microphone Array 1/2", "Input
                # (@System32...)"), as are virtual aliases, loopback
                # taps and output endpoints leaked as inputs.
                hostapis = [h["name"] for h in sd.query_hostapis()]
                # DirectSound first: a name that exists on exactly one
                # device resolves unambiguously in audio.py (WASAPI's
                # "Headset (CP60)" collides with 3 same-name rows).
                api_rank = {"Windows DirectSound": 0, "MME": 1,
                            "Windows WASAPI": 2}

                def _canon(name: str) -> str:
                    # Normalize one physical mic across host APIs.
                    # PortAudio MME truncates names at 31 chars
                    # ("Microphone Array (Realtek(R) Au"), so restore the
                    # common truncated prefix before stripping suffixes.
                    n = (name or "").strip()
                    if n == "Microphone Array (Realtek(R) Au":
                        n = "Microphone Array (Realtek(R) Audio)"
                    n = re.sub(r"\s*\(\s*Realtek\(R\)\s*(Au dio|Audio?)\s*\)\s*$",
                               "", n, flags=re.IGNORECASE).strip()
                    # WDM-KS "… HD Audio Mic input" is the SAME Realtek
                    # array/mic as the MME/DirectSound "… (Realtek(R)
                    # Audio)"; collapse both to the bare kind.
                    n = re.sub(r"\s*\(?\s*Realtek HD Audio Mic input(\s+with SST)?\s*\)?\s*$",
                               "", n, flags=re.IGNORECASE).strip()
                    n = re.sub(r"\s*\(\s*Realtek HD Audio Mic input(\s+with SST)?\s*\)\s*$",
                               "", n, flags=re.IGNORECASE).strip()
                    n = re.sub(r"\s*\d+\s*(\(.*\))?\s*$", lambda m: (" " + m.group(1)) if m.group(1) else "", n).strip()
                    return n or name.strip()

                best: dict[str, dict] = {}
                for idx, d in enumerate(devices):
                    if d["max_input_channels"] <= 0:
                        continue
                    raw = d["name"].strip()
                    if not _is_physical_microphone(raw):
                        continue
                    api = hostapis[d["hostapi"]] if 0 <= d["hostapi"] < len(hostapis) else ""
                    if api not in api_rank:
                        continue
                    key = _canon(raw).lower()
                    rank = api_rank.get(api, 9)
                    cur = best.get(key)
                    entry = {"index": idx, "name": cur["name"] if cur else raw,
                             "api": api, "_rank": rank,
                             "channels": int(d["max_input_channels"]),
                             "rate": float(d["default_samplerate"])}
                    if cur is None or rank < cur["_rank"]:
                        entry["name"] = raw
                        best[key] = entry
                # NOTE: no per-request open-probe here — inside the live
                # backend process a second open can refuse while the
                # recorder holds the device, which wrongly empties the
                # list. Static rules above (virtual-name + WDM-KS
                # exclusion) already drop the ghosts; selection of a
                # dead row falls back to the system default in audio.py.
                mics = [{"index": e["index"], "name": e["name"]}
                        for _, e in sorted(best.items(),
                                           key=lambda kv: (kv[1]["_rank"], kv[0]))]
                # Keep legacy keys ("selected_microphone", "n_device",
                # "selected_mic_device") pointing at a surviving row so an
                # earlier pick of a now-hidden alias keeps working.
                if mics:
                    names = {m["name"] for m in mics}
                    canon = {_canon(m["name"]).lower(): m for m in mics}
                    for _key in ("selected_mic_device", "selected_microphone"):
                        saved = storage.get_setting(_key, None)
                        if saved in (None, "") or saved in names:
                            continue
                        hit = canon.get(_canon(str(saved)).lower())
                        if hit is not None:
                            storage.save_setting(_key, hit["name"])
                            if _key == "selected_microphone":
                                storage.save_setting("n_device", hit["index"])
                self.send_json_response(mics)
            except Exception:
                self.send_json_response([])
        elif path == "/api/policy/get":
            policy = storage.get_exec_policy_options()
            self.send_json_response({"success": True, "policy": policy})
        elif path == "/api/audio-policy/get":
            try:
                policy = storage.get_exec_audio_policy_options()
                self.send_json_response({"success": True, "policy": policy})
            except Exception as exc:
                print(f"[AUDIO FLOW] /api/audio-policy/get error: {exc}")
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/voice-flow-stt/get":
            models = [{
                "full_id": "local/faster-whisper-base.en",
                "label": "Local Whisper base.en (offline · default)",
                "provider": "local",
                "provider_name": "Local Models",
                "display_name": "Whisper base.en",
                "capabilities": [],
            }]
            try:
                from voice_flow import downloadable_models
                for dm in downloadable_models.get_downloaded_models():
                    models.append({
                        "full_id": dm["full_id"],
                        "label": f"{dm['name']} ({dm['size_display']} · GGUF)",
                        "provider": "local",
                        "provider_name": "Local Models",
                        "display_name": dm["name"],
                        "capabilities": ["stt", "local", "offline", "streaming"],
                    })
            except Exception as d_err:
                print(f"[STT] Downloaded models catalog error: {d_err}")
            try:
                overview = storage.get_all_provider_connections()
                for provider, conns in (overview or {}).items():
                    if not any(c.get("is_active") for c in (conns or [])):
                        continue
                    # Only providers the STT engine can actually route to —
                    # offering others guarantees a failed dictation and a
                    # silent local-whisper fallback.
                    if provider not in STT_CAPABLE_PROVIDERS:
                        continue
                    for m in storage.get_provider_models(provider):
                        if m.get("is_active") in (0, False):
                            continue
                        mid = str(m.get("model_id") or "").strip()
                        # Display-name junk (e.g. "gemini 3.5 Transcribe") is
                        # not a callable API id — never offer it for STT.
                        if not mid or any(ch.isspace() for ch in mid):
                            continue
                        # Custom models may have been saved with a provider
                        # prefix; strip it so full_id is always provider/model.
                        if mid.lower().startswith(provider.lower() + "/"):
                            mid = mid[len(provider) + 1:].strip()
                        if any(ch.isspace() for ch in mid):
                            continue
                        models.append({
                            "full_id": f"{provider}/{mid}",
                            "label": f"{provider} — {m.get('display_name') or mid}",
                            "provider": provider,
                            "provider_name": provider,
                            "display_name": m.get("display_name") or mid,
                            "capabilities": [],
                        })
            except Exception:
                pass
            active = storage.get_setting("voice_flow_stt_model", "local/faster-whisper-base.en")
            # If active model is a downloadable local model that is not downloaded, self-heal to default
            try:
                from voice_flow import downloadable_models
                spec = downloadable_models.get_model_spec(active)
                if spec:
                    target_file = downloadable_models.get_models_dir() / spec["filename"]
                    if not target_file.is_file() or target_file.stat().st_size == 0:
                        active = "local/faster-whisper-base.en"
                        storage.save_setting("voice_flow_stt_model", active)
                elif active == "local/faster-whisper-base.en":
                    downloaded = downloadable_models.get_downloaded_models()
                    if downloaded:
                        active = downloaded[0]["full_id"]
                        storage.save_setting("voice_flow_stt_model", active)
            except Exception:
                pass
            # Read real failover data from the live transcriber instance
            failover_count = 0
            last_failover = None
            breaker_status = {}
            try:
                app = getattr(self.server, "_voice_flow_app", None)
                if app is not None:
                    transcriber = getattr(app, "transcriber", None)
                    if transcriber is not None:
                        failover_count = getattr(transcriber, "_failover_count", 0)
                        last_failover = getattr(transcriber, "_last_failover_info", None)
                        breakers = getattr(transcriber, "_cloud_stt_breakers", None)
                        if isinstance(breakers, dict) and active in breakers:
                            f_count, blocked_until = breakers[active]
                            breaker_status = {
                                "failures": f_count,
                                "blocked_until": blocked_until,
                                "is_open": f_count >= 2 and time.time() < blocked_until,
                            }
            except Exception:
                pass
            payload = {
                "active_model": active,
                "polishing_enabled": _polishing_enabled(),
                "models": models,
                "grouped_models": [],
                "failover_count": failover_count,
                "last_failover": last_failover,
                "breaker_status": breaker_status,
            }
            payload["policy"] = dict(payload)
            self.send_json_response({"success": True, **payload})
        elif path in ("/api/downloadable-models", "/api/downloadable-models/list"):
            try:
                from voice_flow import downloadable_models
                params = urllib.parse.parse_qs(parsed.query)
                cat = params.get("category", [""])[0].lower()
                all_flag = params.get("all", [""])[0].lower() in ("true", "1", "yes")
                include_polish = all_flag or cat in ("all", "voice_polishing", "polish")
                models = downloadable_models.get_all_models_status(
                    category=cat if cat not in ("all", "") else None,
                    include_polish=include_polish,
                )
                self.send_json_response({"success": True, "models": models})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path.startswith("/api/downloadable-models/status"):
            try:
                from voice_flow import downloadable_models
                params = urllib.parse.parse_qs(parsed.query)
                model_id = params.get("id", [""])[0] or params.get("model_id", [""])[0]
                if model_id:
                    st = downloadable_models.get_model_status(model_id)
                    if st:
                        self.send_json_response({"success": True, "model": st})
                    else:
                        self.send_json_response({"success": False, "error": "Model not found"}, 404)
                else:
                    self.send_json_response({"success": True, "models": downloadable_models.get_all_models_status(include_polish=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/custom-providers/list":
            self.send_json_response({"success": True, "providers": _public_custom_providers(storage.get_video_flow_custom_providers())})

        elif path == "/api/voice-flow-polish/get":
            from voice_flow import windows_ai_rewriter, lfm_engine
            win_entry = windows_ai_rewriter.get_catalog_entry()
            lfm_entry = lfm_engine.get_catalog_entry()
            models = [
                win_entry,
                lfm_entry,
                {
                    "full_id": "local/deterministic",
                    "label": "Local Deterministic Cleanup (offline · fallback)",
                    "provider": "local",
                    "provider_name": "Local",
                    "display_name": "Local Deterministic",
                    "capabilities": ["offline", "local"],
                    "polish_supported": True,
                    "polish_unavailable_reason": "",
                },
            ]
            try:
                # Video Flow owns this catalog.  Keep every connected text
                # model visible, including an OAuth model for which Voice
                # Flow has no execution adapter yet; the picker marks those
                # entries disabled instead of silently hiding a connection.
                from voice_flow.voice_polish_bridge import can_execute_model
                for item in video_flow_provider_service.list_models():
                    full_id = str(item.get("full_id") or "").strip()
                    low = full_id.lower()
                    if not full_id or not item.get("available"):
                        continue
                    if any(part in low for part in ("whisper", "audio", "stt", "speech", "tts", "transcrib", "scribe", "embedding")):
                        continue
                    label = item.get("display_name") or full_id
                    supported = can_execute_model(full_id) or (item.get("provider") in ("antigravity", "agy") and bool(item.get("available")))
                    models.append({"full_id": full_id, "label": label,
                                   "provider": item.get("provider"),
                                   "provider_name": item.get("provider_name") or item.get("provider"),
                                   "display_name": label,
                                   "capabilities": item.get("capabilities") or [],
                                   "polish_supported": supported,
                                   "polish_unavailable_reason": "Polishing is not supported by this connection" if not supported else ""})

                # Custom providers are stored separately from the standard
                # Video Flow provider-model table.  Include their active
                # models when an active custom key is present, and use the
                # same bridge capability check as the standard catalog.
                for custom in storage.get_video_flow_custom_providers() or []:
                    provider = str(custom.get("id") or "").strip()
                    if not provider:
                        continue
                    has_key = bool(str(custom.get("api_key") or "").strip()) or any(
                        bool(key.get("is_active")) and bool(str(key.get("key") or "").strip())
                        for key in (custom.get("api_keys") or []) if isinstance(key, dict)
                    )
                    if not has_key:
                        continue
                    for item in custom.get("models") or []:
                        if not isinstance(item, dict) or item.get("is_active") is False:
                            continue
                        model_id = str(item.get("model_id") or item.get("id") or "").strip()
                        full_id = f"{provider}/{model_id}" if model_id else ""
                        if not full_id or any(model["full_id"] == full_id for model in models):
                            continue
                        supported = can_execute_model(full_id)
                        label = str(item.get("display_name") or item.get("name") or model_id)
                        models.append({"full_id": full_id, "label": label,
                                       "provider": provider,
                                       "provider_name": custom.get("name") or provider,
                                       "display_name": label, "capabilities": ["custom"],
                                       "polish_supported": supported,
                                       "polish_unavailable_reason": "Polishing is not supported by this connection" if not supported else ""})

                # Voice Flow's older custom-provider list remains a valid
                # compatibility route.  It is separate storage from Video
                # Flow's custom list, so add non-duplicate active models that
                # use one of the formats TextPolisher already supports.
                for custom in storage.get_voice_flow_custom_providers() or []:
                    provider = str(custom.get("id") or "").strip()
                    api_format = str(custom.get("api_format") or "openai").lower()
                    if not provider or api_format not in {"openai", "gemini", "anthropic"}:
                        continue
                    has_key = bool(str(custom.get("api_key") or "").strip()) or any(
                        bool(key.get("is_active")) and bool(str(key.get("key") or "").strip())
                        for key in (custom.get("api_keys") or []) if isinstance(key, dict)
                    )
                    if not has_key:
                        continue
                    for item in custom.get("models") or []:
                        if not isinstance(item, dict) or item.get("is_active") is False:
                            continue
                        model_id = str(item.get("model_id") or item.get("id") or "").strip()
                        full_id = f"{provider}/{model_id}" if model_id else ""
                        if not full_id or any(model["full_id"] == full_id for model in models):
                            continue
                        label = str(item.get("display_name") or item.get("name") or model_id)
                        models.append({"full_id": full_id, "label": label, "provider": provider,
                                       "provider_name": custom.get("name") or provider,
                                       "display_name": label, "capabilities": ["custom", "legacy"],
                                       "polish_supported": True, "polish_unavailable_reason": ""})

                # Existing Voice Flow API-key entries remain usable through
                # the legacy pool.  Keep them as compatibility choices, but
                # do not use them to hide the Video Flow catalog above.
                from voice_flow.polisher import OPENAI_COMPATIBLE_PROVIDERS
                legacy_supported = {"gemini", "anthropic", *OPENAI_COMPATIBLE_PROVIDERS}
                for provider, key in storage.get_all_api_keys().items():
                    if not key or provider not in legacy_supported:
                        continue
                    for item in storage.get_provider_models(provider):
                        if isinstance(item, str):
                            item = {"model_id": item}
                        model_id = str(item.get("model_id") or item.get("id") or "").strip()
                        if item.get("is_active") is False or not model_id:
                            continue
                        full_id = f"{provider}/{model_id.removeprefix(provider + '/') }"
                        low = full_id.lower()
                        if any(part in low for part in ("whisper", "audio", "stt", "speech", "tts", "transcrib", "scribe", "embedding")) or any(m["full_id"] == full_id for m in models):
                            continue
                        label = item.get("display_name") or item.get("name") or model_id
                        models.append({"full_id": full_id, "label": label, "provider": provider,
                                       "provider_name": provider, "display_name": label, "capabilities": []})
            except Exception:
                pass
            default_polish = storage.get_default_polish_model() if hasattr(storage, "get_default_polish_model") else "local/deterministic"
            active = storage.get_setting("voice_flow_polish_model", default_polish)
            if not active:
                active = default_polish
            polishing_enabled = _polishing_enabled()
            speed_mode = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
            self.send_json_response({"success": True, "active_model": active, "models": models, "polishing_enabled": polishing_enabled, "speed_mode": speed_mode})

        elif path == "/api/audio-summary/settings/get":
            try:
                model_ref = str(storage.get_setting("exec_audio_summary_model", "") or "").strip()
                if not model_ref:
                    model_ref = "local/deterministic"
                consent = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))
                self.send_json_response({"success": True, "model": model_ref, "consent": consent})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path in ("/api/video-flow/custom-providers/list", "/api/videoflow/custom-providers/list"):
            self.send_json_response({"success": True, "providers": _public_custom_providers(storage.get_video_flow_custom_providers())})
        elif path in ("/api/voice-flow/custom-providers/list", "/api/providers/custom/list", "/api/voiceflow/custom-providers/list"):
            self.send_json_response({"success": True, "providers": _public_custom_providers(storage.get_voice_flow_custom_providers())})
        elif path in ("/api/audio-flow/custom-providers/list", "/api/audio-providers/custom/list", "/api/audioflow/custom-providers/list"):
            self.send_json_response({"success": True, "providers": _public_custom_providers(storage.get_audio_flow_custom_providers())})
        elif path == "/api/audio-summary/test":
            try:
                params = urllib.parse.parse_qs(parsed.query)
                text = (params.get("text", [""])[0] or "").strip()
                depth = (params.get("depth", ["standard"])[0] or "standard").strip()
                model_ref = params.get("model", [None])[0] or params.get("model_ref", [None])[0]
                if not text:
                    self.send_json_response({"success": False, "error": "Missing 'text' query parameter."}, 400)
                    return
                if not model_ref:
                    model_ref = str(storage.get_setting("exec_audio_summary_model", "local/deterministic") or "local/deterministic").strip()
                allow_consent = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))
                from voice_flow.audio_summary import audio_summary_service
                summary = audio_summary_service.summarize(text=text, depth=depth, model_ref=model_ref, allow_external_ai=allow_consent, allow_fallback=True)
                self.send_json_response({
                    "success": True,
                    "summary": summary,
                    "depth": depth,
                    "model": model_ref or "local/deterministic",
                    "word_count": len(summary.split()),
                })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/audio-providers/overview":
            try:
                data = list(storage.get_audio_providers_overview())
                for cp in storage.get_audio_flow_custom_providers():
                    has_key = bool(str(cp.get("api_key") or "").strip()) or any(bool(k.get("key")) for k in (cp.get("api_keys") or []))
                    data.append({
                        "id": cp.get("id"),
                        "name": cp.get("name"),
                        "logo": "🔊",
                        "connection_count": len(cp.get("api_keys") or ([1] if has_key else [])),
                        "is_connected": has_key,
                        "custom": True,
                    })
                self.send_json_response(data)
            except Exception as exc:
                print(f"[AUDIO FLOW] /api/audio-providers/overview error: {exc}")
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path.startswith("/api/audio-providers/details"):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            provider = params.get("provider", [None])[0]
            if provider:
                try:
                    if provider.startswith("custom-"):
                        entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                        if entry is None:
                            self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                            return
                        key = str(entry.get("api_key") or "")
                        models = []
                        for idx, m in enumerate(entry.get("models") or []):
                            mid = str(m.get("model_id") or "")
                            models.append({
                                "id": "m-" + str(idx),
                                "provider": provider,
                                "model_id": mid,
                                "display_name": str(m.get("display_name") or mid),
                                "full_id": provider + "/" + mid,
                                "capabilities": [],
                                "is_active": m.get("is_active", True),
                                "custom": True,
                                "available": bool(key),
                            })
                        conns = [
                            {
                                "id": "c-" + str(ci),
                                "provider": provider,
                                "name": str(c.get("name") or (str(entry.get("name") or provider) + " key")),
                                "auth_type": "api_key",
                                "priority": ci + 1,
                                "is_active": c.get("is_active", True),
                                "status": c.get("status") or ("connected" if c.get("key") else "untested"),
                                "last_tested_status": c.get("status") or ("Connected" if c.get("key") else "Not Tested"),
                                "metadata": {"base_url": str(entry.get("base_url") or "")},
                                "secret_hint": ((str(c.get("key"))[:3] + "..." + str(c.get("key"))[-4:]) if len(str(c.get("key") or "")) > 8 else ("Key saved" if c.get("key") else "")),
                                "has_secret": bool(c.get("key")),
                            }
                            for ci, c in enumerate(entry.get("api_keys") or (
                                [{"name": str(entry.get("name") or provider) + " key", "key": key, "is_active": True, "status": "connected" if key else "untested"}] if key else []
                            ))
                        ]
                        mode = storage.get_audio_provider_load_balance_mode(provider)
                        self.send_json_response({
                            "provider": {
                                "id": provider,
                                "name": str(entry.get("name") or provider),
                                "category": "api_key",
                                "icon": "🔊",
                                "description": "Custom TTS endpoint",
                                "status": "connected" if key else "disconnected",
                                "connection_count": len(conns),
                            },
                            "connections": conns,
                            "models": models,
                            "mode": mode,
                            "load_balance_mode": mode,
                        })
                        return

                    conns = storage.get_audio_provider_connections(provider)
                    for _item in conns:
                        if isinstance(_item, dict):
                            if _item.get("api_key"):
                                _item["api_key"] = _mask_secret(str(_item["api_key"]))
                            _item.pop("data_json", None)
                    tts_models = storage.get_tts_models_for_provider(provider)
                    mode = storage.get_audio_provider_load_balance_mode(provider)
                    data = {"provider": provider, "connections": conns, "models": tts_models, "mode": mode, "load_balance_mode": mode}
                    self.send_json_response(data)
                except Exception as exc:
                    print(f"[AUDIO FLOW] /api/audio-providers/details error: {exc}")
                    self.send_json_response({"success": False, "error": str(exc)}, 500)
            else:
                self.send_json_response({"error": "Missing provider"}, status=400)
        elif path == "/api/styles/get":
            p_val = str(storage.get_setting("style_personal", "personal_very_casual"))
            personal = p_val if "_" in p_val else f"personal_{p_val}"
            w_val = str(storage.get_setting("style_work", "work_casual"))
            work = w_val if "_" in w_val else f"work_{w_val}"
            e_val = str(storage.get_setting("style_email", "email_formal"))
            email = e_val if "_" in e_val else f"email_{e_val}"
            d_val = str(storage.get_setting("style_developer", "developer_casual"))
            developer = d_val if "_" in d_val else f"developer_{d_val}"
            o_val = str(storage.get_setting("style_other", "other_formal"))
            other = o_val if "_" in o_val else f"other_{o_val}"
            ac_val = str(storage.get_setting("style_autocleanup", "cleanup_light"))
            autocleanup = ac_val if "_" in ac_val else f"cleanup_{ac_val}"
            context_enabled = storage.get_setting("style_context_enabled", True)
            
            app_overrides = storage.get_setting("style_app_overrides", "{}")
            if isinstance(app_overrides, str):
                try: app_overrides = json.loads(app_overrides)
                except Exception: app_overrides = {}
                
            domain_overrides = storage.get_setting("style_domain_overrides", "{}")
            if isinstance(domain_overrides, str):
                try: domain_overrides = json.loads(domain_overrides)
                except Exception: domain_overrides = {}
                
            active_res = style_engine.resolve(consume_override=False)
            
            self.send_json_response({
                "success": True,
                "styles": {
                    "personal": personal,
                    "work": work,
                    "email": email,
                    "developer": developer,
                    "other": other,
                    "autocleanup": autocleanup
                },
                "app_overrides": app_overrides,
                "domain_overrides": domain_overrides,
                "context_enabled": context_enabled,
                "active_app": {
                    "app_name": active_res.app_name,
                    "category": active_res.category,
                    "style": active_res.resolved_style,
                    "description": active_res.config.description
                }
            })
        elif path in ("/api/settings/all", "/api/settings/get"):
            settings = storage.get_all_settings()
            if "polishing_enabled" not in settings:
                settings["polishing_enabled"] = True
            if "audio_flow_enabled" not in settings:
                settings["audio_flow_enabled"] = True
            self.send_json_response({"success": True, "settings": settings})
        elif path == "/api/providers/oauth/start":
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            provider = params.get("provider", ["antigravity"])[0].lower()
            port = self.server.server_address[1] if hasattr(self.server, "server_address") and isinstance(self.server.server_address, tuple) else 8991
            from voice_flow.video_flow_oauth import start_pkce_flow
            try:
                flow_data = start_pkce_flow(storage, provider, port=port)
                self.send_json_response({"success": True, **flow_data})
            except OAuthError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/video-flow/oauth/authorize":
            provider = (urllib.parse.parse_qs(parsed.query).get("provider", ["antigravity"])[0] or "antigravity").lower()
            try:
                # The Google console whitelists the canonical loopback
                # redirect http://127.0.0.1:8991/callback, so always mint the
                # pending session + consent URL against port 8991 regardless
                # of the ephemeral port this server instance runs on.
                res = video_flow_provider_service.start_oauth(provider, port=PORT)
                auth_url = res.get("authUrl") or res.get("auth_url") or ""
                state = res.get("state") or ""
                redirect_uri = res.get("redirectUri") or res.get("redirect_uri") or f"http://127.0.0.1:{PORT}/callback"
                self.send_json_response({"success": True, "authUrl": auth_url, "state": state, "redirectUri": redirect_uri, **res})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
        else:
            if path.startswith("/api/"):
                self.send_json_response({"success": False, "error": f"API endpoint '{path}' not found."}, 404)
                return
            super().do_GET()

    def do_POST(self):
        global video_flow_provider_service
        if not self._host_is_allowed():
            self.send_json_response({"success": False, "error": "Invalid Host header"}, 403)
            return
        origin = self.headers.get("Origin")
        if ALLOWED_ORIGINS is not None and origin and origin not in ALLOWED_ORIGINS:
            self._discard_small_request_body()
            self.send_json_response({"success": False, "error": "Origin not allowed"}, 403)
            return

        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            self.send_json_response({"success": False, "error": "Invalid Content-Length"}, 400)
            return

        max_allowed = MAX_VAULT_BODY_BYTES if self.path.startswith("/api/auth/vault/import") else MAX_JSON_BODY_BYTES
        if length < 0 or length > max_allowed:
            # Drain a bounded prefix of the rejected body so a huge upload
            # cannot stall the connection for the next keep-alive request.
            if length > max_allowed:
                try:
                    self.connection.settimeout(0.05)
                    try:
                        self.rfile.read(min(length, max_allowed))
                    except (TimeoutError, OSError):
                        pass
                except Exception:
                    pass
                finally:
                    try:
                        self.close_connection = True
                    except Exception:
                        pass
            self.send_json_response({"success": False, "error": "Invalid body length"}, 400 if length < 0 else 413)
            return

        try:
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            data = json.loads(body) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json_response({"success": False, "error": "Invalid JSON body"}, 400)
            return

        if not isinstance(data, dict):
            self.send_json_response({"success": False, "error": "JSON body must be an object"}, 400)
            return

        path = urllib.parse.urlparse(self.path).path

        if path == "/auth/logout":
            from voice_flow.google_auth import handle_logout
            handle_logout(self)
            return
        if path == "/auth/google/open":
            from voice_flow.google_auth import handle_google_open
            self.send_json_response(handle_google_open(self, port=self._server_port()))
            return
        if path == "/auth/desktop/session":
            from voice_flow.google_auth import handle_desktop_session
            handle_desktop_session(self, str(data.get("pair_token") or ""))
            return

        if path == "/api/platform/permissions/open":
            from voice_flow.platform import get_backend
            key = str(data.get("key") or "").strip()
            ok = get_backend().open_permission_settings(key)
            self.send_json_response({"success": ok})
            return

        # Multi-Account Authentication & Profile Management
        if path == "/api/auth/google/start":
            from voice_flow.google_auth import start_google_account_auth
            res = start_google_account_auth(port=self._server_port())
            self.send_json_response(res)
            return

        if path == "/api/auth/register":
            from voice_flow.account_manager import get_account_manager
            email = str(data.get("email") or "").strip()
            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            avatar_color = data.get("avatar_color")
            try:
                am = get_account_manager()
                res = am.register_account(email=email, username=username, password=password, avatar_color=avatar_color)
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 400)
            return

        if path == "/api/auth/login":
            from voice_flow.account_manager import get_account_manager
            email_or_username = str(data.get("email") or data.get("username") or "").strip()
            password = str(data.get("password") or "")
            try:
                am = get_account_manager()
                res = am.authenticate_account(email_or_username=email_or_username, password=password)
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 401)
            return

        if path == "/api/auth/switch":
            from voice_flow.account_manager import get_account_manager
            account_id = str(data.get("account_id") or "").strip()
            if not account_id:
                self.send_json_response({"success": False, "error": "account_id is required"}, 400)
                return
            try:
                am = get_account_manager()
                res = am.switch_account(account_id)
                accounts = [a for a in (res.get("accounts") or am.list_accounts()) if not (a.get("email") == "primary@flow.local" and not a.get("google_id"))]
                self.send_json_response({
                    "success": True,
                    "active_account": res.get("active_account"),
                    "accounts": accounts,
                })
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 400)
            return

        if path == "/api/auth/update-profile":
            from voice_flow.account_manager import get_account_manager
            account_id = str(data.get("account_id") or "").strip()
            username = data.get("username")
            avatar_color = data.get("avatar_color")
            new_password = data.get("new_password")
            current_password = data.get("current_password")
            try:
                am = get_account_manager()
                if not account_id:
                    act = am.get_active_account()
                    account_id = act["id"] if act else ""
                res = am.update_profile(
                    account_id=account_id,
                    username=username,
                    avatar_color=avatar_color,
                    new_password=new_password,
                    current_password=current_password,
                )
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 400)
            return

        if path == "/api/auth/logout":
            from voice_flow.account_manager import get_account_manager
            token = data.get("session_token")
            am = get_account_manager()
            am.logout_account(token)
            self.send_json_response({"success": True})
            return

        if path == "/api/auth/vault/export":
            from voice_flow.account_manager import get_account_manager
            passphrase = str(data.get("passphrase") or "")
            account_id = str(data.get("account_id") or "").strip()
            try:
                am = get_account_manager()
                if not account_id:
                    act = am.get_active_account()
                    account_id = act["id"] if act else ""
                vault = am.export_vault(account_id, passphrase)
                self.send_json_response({"success": True, "vault": vault})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 400)
            return

        if path == "/api/auth/vault/import":
            from voice_flow.account_manager import get_account_manager
            passphrase = str(data.get("passphrase") or "")
            vault_data = data.get("vault_data") or data.get("vault") or {}
            account_id = str(data.get("account_id") or "").strip()
            try:
                am = get_account_manager()
                if not account_id:
                    act = am.get_active_account()
                    account_id = act["id"] if act else ""
                res = am.import_vault(account_id, passphrase, vault_data)
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 400)
            return

        if path == "/api/providers/all":
            all_conns = storage.get_all_provider_connections()
            # Same nested-dict masking fix as /api/providers/connections.
            for conns in (all_conns or {}).values():
                for item in conns:
                    if isinstance(item, dict):
                        if item.get("api_key"):
                            item["api_key"] = _mask_secret(str(item["api_key"]))
                        item.pop("data_json", None)
            self.send_json_response({"success": True, "connections": all_conns})

        elif path == "/api/providers/connections/add":
            provider = data.get("provider", "gemini").lower()
            name = data.get("name", "").strip()
            key = data.get("key", "").strip()
            try:
                priority = int(data.get("priority", 1))
            except (TypeError, ValueError):
                priority = 1

            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                if not conns and str(entry.get("api_key") or ""):
                    conns = [{"name": str(entry.get("name") or provider) + " key",
                              "key": str(entry.get("api_key")),
                              "is_active": True, "priority": 1, "status": "untested"}]
                new_conn = {
                    # Positional and stable: renumbered on deletion, so every
                    # surviving connection stays addressable as c-<position>.
                    "id": f"c-{len(conns)}",
                    "name": name or f"{entry.get('name') or provider} key #{len(conns) + 1}",
                    "key": key,
                    "priority": priority or (len(conns) + 1),
                    "is_active": True,
                    "status": "untested",
                }
                conns.append(new_conn)
                entry["api_keys"] = conns
                if not entry.get("api_key"):
                    entry["api_key"] = key
                storage.add_voice_flow_custom_provider(entry)
                public_conn = {**new_conn, "key": "", "has_secret": bool(new_conn.get("key"))}
                self.send_json_response({"success": True, "connection": public_conn, "message": "Connection added successfully!"})
                return

            v_res = self.verify_api_key(provider, key)
            if v_res["success"]:
                new_conn = storage.add_provider_connection(provider, name, key, priority)
                public_conn = {k: v for k, v in new_conn.items() if k not in {"api_key", "data"}}
                public_conn["has_secret"] = bool(key)
                self.send_json_response({"success": True, "connection": public_conn, "message": "Connection added successfully!"})
            else:
                self.send_json_response({"success": False, "error": v_res.get("error", "Validation failed.")})

        elif path == "/api/providers/connections/update":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("c-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                cidx = _find_conn_index(conns, cid_raw)
                if 0 <= cidx < len(conns):
                    c = conns[cidx]
                    if str(data.get("name") or "").strip():
                        c["name"] = str(data.get("name")).strip()
                    if str(data.get("key") or data.get("secret") or "").strip():
                        c["key"] = str(data.get("key") or data.get("secret")).strip()
                    if data.get("priority"):
                        try:
                            c["priority"] = int(data.get("priority"))
                        except Exception:
                            pass
                    if conns:
                        entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                    entry["api_keys"] = conns
                    storage.add_voice_flow_custom_provider(entry)
                    self.send_json_response({"success": True})
                    return
                self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                return

            cid = int(data.get("id"))
            name = data.get("name", "").strip()
            key = data.get("key", "").strip()
            priority = int(data.get("priority", 1))
            if not key:
                # Empty key on edit means "keep the saved key" — never wipe it.
                try:
                    with sqlite3.connect(storage.db_path) as conn:
                        row = conn.execute("SELECT api_key FROM provider_connections WHERE id = ?", (cid,)).fetchone()
                        key = (row[0] or "").strip() if row else ""
                except Exception:
                    key = ""
            success = storage.update_provider_connection(cid, name, key, priority)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/toggle":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("c-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                cidx = _find_conn_index(conns, cid_raw)
                if 0 <= cidx < len(conns):
                    conns[cidx]["is_active"] = bool(data.get("is_active", True))
                    if conns:
                        entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                    entry["api_keys"] = conns
                    storage.add_voice_flow_custom_provider(entry)
                    self.send_json_response({"success": True})
                    return
                self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                return

            cid = int(data.get("id"))
            active = bool(data.get("is_active", True))
            success = storage.toggle_provider_connection(cid, active)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/delete":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw == "custom":
                providers = storage.delete_voice_flow_custom_provider(provider)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            if cid_raw.startswith("c-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                cidx = _find_conn_index(conns, cid_raw)
                if 0 <= cidx < len(conns):
                    conns.pop(cidx)
                    entry["api_keys"] = conns
                    entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                    storage.add_voice_flow_custom_provider(entry)
                    self.send_json_response({"success": True})
                    return
                self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                return

            cid = int(data.get("id"))
            success = storage.delete_provider_connection(cid)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/test":
            cid = data.get("id")
            cid_raw = str(cid or "")
            provider = str(data.get("provider") or "gemini").lower()
            key = str(data.get("key") or "").strip()

            if cid_raw.startswith("c-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry:
                    conns = entry.get("api_keys") or []
                    cidx = _find_conn_index(conns, cid_raw)
                    if 0 <= cidx < len(conns) and not key:
                        key = str(conns[cidx].get("key") or "")
                    if not key:
                        key = str(entry.get("api_key") or "")
                    first_model = str(((entry.get("models") or [{}])[0].get("model_id") or "")).strip()
                    probe_kind = "stt" if re.search(r"whisper|transcri|stt|speech|scribe|nova", first_model, re.IGNORECASE) else "llm"
                    probe = self._probe_custom_endpoint_direct(
                        base_url=str(entry.get("base_url") or ""),
                        api_key=key,
                        api_format=str(entry.get("api_format") or "openai").lower(),
                        model_id=first_model or "gpt-4o-mini",
                        kind=probe_kind,
                        headers=entry.get("headers"),
                    )
                    valid = bool(probe.get("success"))
                    err = str(probe.get("error") or "Validation failed.")
                    if 0 <= cidx < len(conns):
                        conns[cidx]["status"] = "connected" if valid else "error"
                        conns[cidx]["last_tested_status"] = "Connected" if valid else f"Error: {err}"
                        entry["api_keys"] = conns
                        storage.add_voice_flow_custom_provider(entry)
                    if valid:
                        self.send_json_response({"success": True, "valid": True, "status": "active", "message": probe.get("message") or "Custom provider verified!"})
                    else:
                        self.send_json_response({"success": False, "valid": False, "status": "error", "error": err})
                    return

            if not key and cid:
                conns = storage.get_all_provider_connections()
                for p_list in conns.values():
                    for c in p_list:
                        if str(c.get("id")) == str(cid) or str(c.get("uuid_id")) == str(cid):
                            key = c.get("api_key", "").strip()
                            provider = provider or c.get("provider", "").lower()
                            break
                    if key:
                        break
                if not key:
                    try:
                        vf_c = video_flow_provider_service.get_connection(int(cid), public=False)
                        if vf_c:
                            provider = provider or vf_c.get("provider", "").lower()
                            key = video_flow_provider_service.resolve_connection_secret(vf_c)
                    except Exception:
                        pass
            if not key and provider:
                try:
                    pconns = storage.get_provider_connections(provider)
                    for c in pconns:
                        if c.get("is_active") and c.get("api_key"):
                            key = c["api_key"].strip()
                            break
                except Exception:
                    pass
                if not key:
                    try:
                        vf_conns = video_flow_provider_service.list_connections(provider)
                        for c in vf_conns:
                            if c.get("is_active"):
                                sec = video_flow_provider_service.resolve_connection_secret(c)
                                if sec:
                                    key = sec
                                    break
                    except Exception:
                        pass
            if provider in ("antigravity", "openai_codex", "claude_code", "cursor", "kiro", "copilot") and not key:
                healthy = False
                try:
                    vf_conns = video_flow_provider_service.list_connections(provider)
                    for c in vf_conns:
                        if c.get("is_active") and video_flow_provider_service.connection_is_healthy(c):
                            healthy = True
                            break
                except Exception:
                    pass
                if healthy:
                    v_res = {"success": True, "message": f"{provider.capitalize()} session active and valid."}
                else:
                    v_res = {"success": False, "error": f"{provider.capitalize()} session expired or disconnected."}
            elif not key:
                v_res = {"success": False, "error": "API key cannot be empty"}
            else:
                v_res = self.verify_api_key(provider, key)
            if cid:
                status_str = "Connected (200 OK)" if v_res.get("success") else f"Error: {v_res.get('error', 'Failed')}"
                try:
                    storage.update_connection_status(int(cid), status_str)
                except Exception:
                    pass
            self.send_json_response(v_res)

        elif path == "/api/audio-summary/test":
            try:
                text = str(data.get("text") or "").strip()
                depth = str(data.get("depth") or "standard").strip()
                model_ref = data.get("model") or data.get("model_ref")
                if not text:
                    self.send_json_response({"success": False, "error": "Missing 'text' parameter."}, 400)
                    return
                if not model_ref:
                    model_ref = str(storage.get_setting("exec_audio_summary_model", "local/deterministic") or "local/deterministic").strip()
                allow_consent = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))
                from voice_flow.audio_summary import audio_summary_service
                summary = audio_summary_service.summarize(text=text, depth=depth, model_ref=model_ref, allow_external_ai=allow_consent, allow_fallback=True)
                self.send_json_response({
                    "success": True,
                    "summary": summary,
                    "depth": depth,
                    "model": model_ref or "local/deterministic",
                    "word_count": len(summary.split()),
                })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/providers/oauth/complete":
            provider = str(data.get("provider") or "antigravity").lower()
            code = str(data.get("code") or "").strip()
            state = data.get("state")
            callback_url = str(data.get("callback_url") or "").strip()

            if callback_url:
                try:
                    parsed_cb = urllib.parse.urlparse(callback_url)
                    cb_params = urllib.parse.parse_qs(parsed_cb.query)
                    if "code" in cb_params:
                        code = cb_params["code"][0]
                    if "state" in cb_params:
                        state = cb_params["state"][0]
                except Exception:
                    pass

            if not code:
                self.send_json_response({"success": False, "error": "Missing authorization code or callback URL."}, 400)
                return

            from voice_flow.video_flow_oauth import complete_pkce_flow
            try:
                res = complete_pkce_flow(storage, provider, code=code, state=state)
                # Tell the relay page the app already consumed this code, so a
                # no-opener fallback fetch would not retry the single-use code.
                try:
                    if state:
                        storage.save_setting(f"oauth_completed_state:{state}", time.time())
                except Exception:
                    pass
                self.send_json_response(res)
            except OAuthError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path in ("/api/providers/mode/save", "/api/audio-providers/mode/save", "/api/audio-flow/providers/settings", "/api/audio-providers/settings"):
            provider = data.get("provider", "gemini").lower()
            raw_mode = str(data.get("mode") or data.get("load_balance_mode") or "priority").strip().lower().replace("-", "_").replace(" ", "_")
            mode = "round_robin" if raw_mode == "round_robin" else "priority"
            if path in ("/api/audio-providers/mode/save", "/api/audio-flow/providers/settings", "/api/audio-providers/settings"):
                success = storage.save_audio_provider_load_balance_mode(provider, mode)
            else:
                success = storage.save_provider_load_balance_mode(provider, mode)
            self.send_json_response({"success": bool(success), "mode": mode, "load_balance_mode": mode})

        elif path == "/api/video-flow/providers/models/add":
            provider = str(data.get("provider") or "").lower().strip()
            provider = PROVIDER_ALIASES.get(provider, provider)
            model_id = str(data.get("model_id") or "").strip()
            model_id = strip_redundant_model_prefix(provider, model_id)
            if not provider or not model_id:
                self.send_json_response({"success": False, "error": "Provider and model_id are required."}, 400)
                return

            if data.get("verify") or data.get("validate"):
                v_res = self.verify_model_by_kind(provider, key=data.get("key", ""), model_id=model_id, kind=data.get("kind", "llm"))
                if not v_res.get("success"):
                    self.send_json_response({"success": False, "error": v_res.get("error") or "Model verification failed."}, 400)
                    return

            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers()
                              if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                entry["models"] = (entry.get("models") or []) + [{
                    "id": _new_custom_item_id("m"),
                    "model_id": model_id,
                    "display_name": str(data.get("display_name") or "").strip() or model_id,
                    "context_window": 128000, "max_output_tokens": 8192,
                    "input_types": ["text"], "output_types": ["text"],
                }]
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            display_name = str(data.get("display_name") or "").strip()
            try:
                added = video_flow_provider_service.add_model(provider, model_id, display_name)
                try:
                    storage.add_provider_model(provider, added["model_id"], added["display_name"])
                except Exception:
                    pass
                self.send_json_response({"success": True, "model": added, "models": video_flow_provider_service.list_models(provider, include_inactive=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/models/enable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = True
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                models = video_flow_provider_service.list_models(provider, include_inactive=True)
                for model_row in models:
                    video_flow_provider_service.set_model_active(model_row["id"], True)
                self.send_json_response({"success": True, "count": len(models)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/providers/models/disable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = False
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                models = video_flow_provider_service.list_models(provider, include_inactive=True)
                for model_row in models:
                    video_flow_provider_service.set_model_active(model_row["id"], False)
                self.send_json_response({"success": True, "count": len(models)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/providers/models/delete":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers()
                              if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Model not found."}, 404)
                    return
                models = entry.get("models") or []
                idx = _find_model_index(models, cid_raw)
                if idx < 0 or idx >= len(models):
                    self.send_json_response({"success": False, "error": "Model not found."}, 404)
                    return
                models.pop(idx)
                entry["models"] = models
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            try:
                cid = int(data.get("id"))
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
                return
            ok = video_flow_provider_service.delete_model(cid)
            if ok:
                self.send_json_response({"success": True})
            else:
                self.send_json_response({"success": False, "error": "Model not found or not custom."}, 404)

        elif path in ("/api/providers/models/add", "/api/models/add"):
            provider = (data.get("provider") or "gemini").lower().strip()
            provider = PROVIDER_ALIASES.get(provider, provider)
            model_id = (data.get("model_id") or "").strip()
            model_id = strip_redundant_model_prefix(provider, model_id)
            display_name = (data.get("display_name") or "").strip() or model_id.replace("-", " ").replace("_", " ").title()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id is required."}, 400)
                return

            if data.get("verify") or data.get("validate"):
                v_res = self.verify_model_by_kind(provider, key=data.get("key", ""), model_id=model_id, kind=data.get("kind", "auto"))
                if not v_res.get("success"):
                    self.send_json_response({"success": False, "error": v_res.get("error") or "Model verification failed."}, 400)
                    return
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                if not model_id:
                    self.send_json_response({"success": False, "error": "model_id is required."}, 400)
                    return
                models = entry.get("models") or []
                models.append({
                    "id": _new_custom_item_id("m"),
                    "model_id": model_id,
                    "display_name": display_name,
                    "is_active": True,
                    "custom": True,
                })
                entry["models"] = models
                storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "models": models})
                return
            success = storage.add_provider_model(provider, model_id, display_name)
            if provider == "antigravity":
                try:
                    video_flow_provider_service.add_model(provider, model_id, display_name)
                except Exception:
                    pass
            self.send_json_response({"success": success, "models": storage.get_provider_models(provider)})

        elif path in ("/api/providers/models/delete", "/api/models/delete"):
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                # Custom models carry opaque ids (m-<hex>). Parsing the suffix as
                # an int raised ValueError, was swallowed, and the handler still
                # returned success — so delete silently did nothing.
                idx = _find_model_index(models, cid_raw)
                if idx >= 0:
                    models.pop(idx)
                else:
                    mid = str(data.get("model_id") or cid_raw)
                    models = [m for m in models if str(m.get("model_id")) != mid]
                entry["models"] = models
                storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "models": models})
                return
            mid = data.get("id") or data.get("model_id")
            success = storage.delete_provider_model(mid, provider=provider)
            self.send_json_response({"success": success})

        elif path in (
            "/api/providers/models/test",
            "/api/models/test",
            "/api/video-flow/providers/models/test",
            "/api/video-flow/models/test",
            "/api/audio-providers/models/test",
            "/api/audio-flow/providers/models/test",
            "/api/audio-models/test",
        ):
            provider = (data.get("provider") or "").lower().strip()
            model_id = (data.get("model_id") or data.get("model") or data.get("model_ref") or "").strip()
            kind = (data.get("kind") or "auto").strip().lower()
            if kind == "auto" and (path.startswith("/api/audio-") or path.startswith("/api/audio")):
                kind = "tts"
            key = (data.get("key") or data.get("api_key") or "").strip()

            if "/" in model_id and not provider:
                provider, model_id = model_id.split("/", 1)
                provider = provider.lower().strip()

            provider = _canonical_provider_for_kind(provider, kind)
            model_id = strip_redundant_model_prefix(provider, model_id)
            if provider in ("gemini", "google", "googleai") and kind == "stt":
                kind = "llm"

            if provider == "antigravity":
                # Antigravity models are called through the account's OAuth
                # token (Cloud Code API) or the agy bridge — never a static
                # API key. Validate accordingly, 9Router-style: per-model
                # quota via fetchAvailableModels, with refresh-on-401.
                import time as _time
                t0 = _time.time()
                token = ""
                conn_row = None
                proj = ""
                if key and not key.startswith("antigravity-"):
                    token = key
                if not token:
                    try:
                        from voice_flow.video_flow_oauth import decrypt_token
                        conns = video_flow_provider_service.list_connections("antigravity")
                        for c in sorted(conns, key=lambda x: int(x.get("id") or 0), reverse=True):
                            if not c.get("is_active"):
                                continue
                            try:
                                row = video_flow_provider_service.get_connection(int(c["id"]), public=False)
                                secret = str(row.get("secret") or "")
                            except Exception:
                                secret = ""
                            if secret and "cli-bridge" not in secret:
                                token = decrypt_token(video_flow_provider_service, secret) or secret
                                conn_row = c
                                proj = (row.get("metadata") or {}).get("project_id") or ""
                                if conn_row.get("metadata") and conn_row["metadata"].get("project_id"):
                                    proj = conn_row["metadata"].get("project_id")
                                if token:
                                    break
                    except Exception:
                        token = ""
                if not token:
                    try:
                        pconns = storage.get_provider_connections("antigravity")
                        for pc in sorted(pconns, key=lambda x: int(x.get("id") or 0), reverse=True):
                            if pc.get("is_active") and pc.get("api_key"):
                                token = str(pc.get("api_key") or "").strip()
                                if token:
                                    break
                    except Exception:
                        pass

                def _quota(tok):
                    import urllib.request as _ureq
                    body = {"project": proj} if proj else {}
                    req = _ureq.Request(
                        "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
                        data=json.dumps(body).encode("utf-8"),
                        headers={
                            "Authorization": "Bearer " + tok,
                            "Content-Type": "application/json",
                            "User-Agent": "antigravity/ide/2.1.1 win32/x64",
                            "X-Client-Name": "antigravity",
                            "X-Client-Version": "2.1.1",
                            "x-request-source": "local",
                        },
                        method="POST",
                    )
                    with _ureq.urlopen(req, timeout=12) as resp:
                        return json.loads(resp.read().decode("utf-8", errors="replace")).get("models") or {}

                if token and not token.startswith("antigravity-"):
                    try:
                        try:
                            models = _quota(token)
                        except Exception as e401:
                            txt = str(e401)
                            if "401" not in txt and "Unauthorized" not in txt:
                                raise
                            # Access token expired (~1h lifetime): refresh once
                            # with the stored refresh_token, persist the new
                            # token, then retry the quota check.
                            rt = ""
                            if conn_row is not None:
                                try:
                                    priv = video_flow_provider_service.get_connection(int(conn_row["id"]), public=False)
                                    try:
                                        from voice_flow.video_flow_oauth import decrypt_token as _vf_decrypt_token
                                        rt = _vf_decrypt_token(video_flow_provider_service, str(priv.get("refresh_token") or ""))
                                    except Exception:
                                        rt = ""
                                    if not rt:
                                        rt = str((priv.get("metadata") or {}).get("refresh_token") or "")
                                except Exception:
                                    rt = ""
                            if not rt:
                                raise OAuthError("Antigravity token expired and no refresh token stored. Reconnect the account.")
                            tok = _http_json(
                                "https://oauth2.googleapis.com/token",
                                data={
                                    "grant_type": "refresh_token",
                                    "client_id": ANTIGRAVITY_CLIENT_ID,
                                    "client_secret": ANTIGRAVITY_CLIENT_SECRET,
                                    "refresh_token": rt,
                                },
                            )
                            new_access = str(tok.get("access_token") or "")
                            if not new_access:
                                raise OAuthError("Token refresh failed. Reconnect the account.")
                            exp = int(time.time()) + int(tok.get("expires_in") or 3600)
                            if conn_row is not None:
                                try:
                                    meta = dict((conn_row.get("metadata") or {}))
                                    meta["expires_at"] = exp
                                    video_flow_provider_service.update_connection(
                                        int(conn_row["id"]),
                                        secret=encrypt_token(video_flow_provider_service, new_access),
                                        expires_at=str(exp),
                                        metadata=meta,
                                    )
                                except Exception:
                                    pass
                            token = new_access
                            models = _quota(token)

                        mid = (model_id or "").lower().split("/")[-1].strip()
                        if not mid:
                            self.send_json_response({
                                "success": False, "ok": False,
                                "error": "Enter a model ID first.",
                            })
                            return

                        if not re.fullmatch(r"[A-Za-z0-9@._:/-]+", mid):
                            self.send_json_response({
                                "success": False, "ok": False,
                                "error": f"Invalid model ID '{model_id}'. Use only alphanumeric characters, dashes, dots, and slashes.",
                            })
                            return

                        best = None
                        for key_q, info in models.items():
                            k = key_q.lower()
                            if k == mid or k.startswith(mid) or mid.startswith(k):
                                q = (info or {}).get("quotaInfo") or {}
                                if q.get("remainingFraction") is not None:
                                    frac = float(q.get("remainingFraction") or 0)
                                    best = frac if best is None else max(best, frac)
                        if best is None:
                            family_prefix = mid.split("-")[0] if "-" in mid else mid
                            if family_prefix in ("gemini", "claude"):
                                family_fractions = [
                                    float((info or {}).get("quotaInfo", {}).get("remainingFraction"))
                                    for key_q, info in models.items()
                                    if key_q.lower().startswith(family_prefix)
                                    and isinstance(info, dict)
                                    and (info.get("quotaInfo") or {}).get("remainingFraction") is not None
                                ]
                                if family_fractions:
                                    best = max(family_fractions)
                        if best is None:
                            self.send_json_response({
                                "success": False, "ok": False,
                                "latency_ms": int((_time.time() - t0) * 1000),
                                "error": f"Model '{model_id}' is not available in your Antigravity subscription.",
                            })
                            return

                        if best <= 0:
                            self.send_json_response({
                                "success": False, "ok": False,
                                "error": "No credits left for this model on your Antigravity subscription (quota exhausted).",
                            })
                        else:
                            self.send_json_response({
                                "success": True, "ok": True,
                                "latency_ms": int((_time.time() - t0) * 1000),
                                "remaining_pct": round(best * 100, 1),
                                "message": "Antigravity subscription active - " + str(round(best * 100, 1)) + "% quota remaining for this model.",
                            })
                    except OAuthError as exc:
                        self.send_json_response({
                            "success": False, "ok": False,
                            "error": str(exc)[:220],
                        })
                    except Exception as exc:
                        self.send_json_response({"success": False, "ok": False, "error": str(exc)[:220]})
                else:
                    try:
                        from voice_flow.video_flow_providers import antigravity_bridge_status
                        if antigravity_bridge_status().get("ready"):
                            self.send_json_response({
                                "success": True, "ok": True, "latency_ms": int((_time.time() - t0) * 1000),
                                "message": "Antigravity app bridge active (agy CLI session).",
                            })
                        else:
                            self.send_json_response({
                                "success": False, "ok": False,
                                "error": "No active Antigravity account. Add an account first.",
                            })
                    except Exception as exc:
                        self.send_json_response({"success": False, "ok": False, "error": str(exc)[:200]})
                return

            if provider == "openai_codex":
                import time as _time
                import urllib.request as _ureq
                import urllib.error as _uerr
                from datetime import datetime, timezone
                t0 = _time.time()
                active_conns = [c for c in video_flow_provider_service.list_connections("openai_codex") if c.get("is_active")]
                if not active_conns:
                    try:
                        imp_res = video_flow_provider_service.start_oauth("openai_codex")
                        if imp_res.get("imported"):
                            active_conns = [c for c in video_flow_provider_service.list_connections("openai_codex") if c.get("is_active")]
                    except Exception:
                        pass
                if not active_conns:
                    self.send_json_response({
                        "success": False,
                        "ok": False,
                        "error": "No active ChatGPT account connected. Sign in using the Authentication section.",
                    }, 400)
                    return

                best_conn = video_flow_provider_service.pick_best_connection("openai_codex")
                c = best_conn or active_conns[0]
                conn_id = int(c["id"])
                priv = video_flow_provider_service.get_connection(conn_id, public=False) or c
                token = ""
                try:
                    from voice_flow.video_flow_oauth import decrypt_token as _vf_decrypt_token, _extract_jwt_claim as _vf_extract_claim
                    token = video_flow_provider_service.resolve_connection_secret(priv)
                    if not token:
                        secret = str(priv.get("secret") or "")
                        token = _vf_decrypt_token(video_flow_provider_service, secret) or secret
                except Exception:
                    token = str(priv.get("secret") or "")

                chatgpt_account_id = (
                    (priv.get("metadata") or {}).get("chatgpt_account_id")
                    or _vf_extract_claim(token, "chatgpt_account_id")
                    or (c.get("account_id") if c.get("account_id") and "@" not in str(c.get("account_id")) else "")
                )
                account_display = c.get("account_id") or "ChatGPT Account"

                codex_supported_models = {
                    "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4-mini", "gpt-5.6-sol", "gpt-5.3-codex-spark", "gpt-5.4"
                }

                def _probe_codex(tok, acc_id):
                    headers = {
                        "Authorization": f"Bearer {tok}",
                        "originator": "codex_cli_rs",
                        "User-Agent": "codex_cli_rs/0.0.0",
                        "Accept": "application/json",
                    }
                    if acc_id:
                        headers["ChatGPT-Account-Id"] = acc_id

                    live_models = set(codex_supported_models)
                    try:
                        req_m = _ureq.Request(
                            "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
                            headers=headers,
                            method="GET"
                        )
                        with _ureq.urlopen(req_m, timeout=5) as resp_m:
                            m_data = json.loads(resp_m.read().decode("utf-8"))
                            for m in m_data.get("models") or []:
                                slug = m.get("slug")
                                if slug and m.get("visibility") != "hide":
                                    live_models.add(slug)
                    except Exception:
                        pass

                    req_u = _ureq.Request(
                        "https://chatgpt.com/backend-api/wham/usage",
                        headers=headers,
                        method="GET"
                    )
                    with _ureq.urlopen(req_u, timeout=10) as resp_u:
                        usage = json.loads(resp_u.read().decode("utf-8"))
                    return usage, live_models

                try:
                    try:
                        usage_data, available_models = _probe_codex(token, chatgpt_account_id)
                    except _uerr.HTTPError as e401:
                        if e401.code == 401:
                            video_flow_provider_service.oauth_refresh(conn_id)
                            priv = video_flow_provider_service.get_connection(conn_id, public=False) or c
                            token = video_flow_provider_service.resolve_connection_secret(priv)
                            if not token:
                                secret = str(priv.get("secret") or "")
                                token = _vf_decrypt_token(video_flow_provider_service, secret) or secret
                            chatgpt_account_id = (
                                (priv.get("metadata") or {}).get("chatgpt_account_id")
                                or _vf_extract_claim(token, "chatgpt_account_id")
                                or chatgpt_account_id
                            )
                            usage_data, available_models = _probe_codex(token, chatgpt_account_id)
                        else:
                            raise

                    if model_id and model_id not in available_models and model_id not in codex_supported_models:
                        self.send_json_response({
                            "success": False,
                            "ok": False,
                            "latency_ms": int((_time.time() - t0) * 1000),
                            "error": f"Model '{model_id}' is not available in the ChatGPT Codex distribution. Supported models: {', '.join(sorted(codex_supported_models))}.",
                        })
                        return

                    plan_type = usage_data.get("plan_type") or _vf_extract_claim(token, "chatgpt_plan_type") or "free"
                    rate_limit = usage_data.get("rate_limit") or {}
                    allowed = rate_limit.get("allowed", True)
                    limit_reached = rate_limit.get("limit_reached", False)
                    primary = rate_limit.get("primary_window") or {}
                    secondary = rate_limit.get("secondary_window") or {}

                    # Persist chatgpt_account_id and plan_type in metadata if missing
                    try:
                        meta = dict(priv.get("metadata") or {})
                        meta_updated = False
                        if chatgpt_account_id and not meta.get("chatgpt_account_id"):
                            meta["chatgpt_account_id"] = chatgpt_account_id
                            meta_updated = True
                        if plan_type and not meta.get("chatgpt_plan_type"):
                            meta["chatgpt_plan_type"] = plan_type
                            meta_updated = True
                        if meta_updated:
                            video_flow_provider_service.update_connection(conn_id, metadata=meta)
                    except Exception:
                        pass

                    used_pct = max(primary.get("used_percent") or 0, secondary.get("used_percent") or 0)
                    remaining_pct = max(0, 100 - used_pct)

                    if (secondary.get("used_percent") or 0) > (primary.get("used_percent") or 0) and secondary.get("reset_at"):
                        reset_at = secondary.get("reset_at")
                    else:
                        reset_at = primary.get("reset_at") or secondary.get("reset_at")

                    reset_time_str = ""
                    if reset_at:
                        try:
                            dt = datetime.fromtimestamp(float(reset_at), tz=timezone.utc).astimezone()
                            reset_time_str = dt.strftime("%Y-%m-%d %H:%M %Z")
                        except Exception:
                            reset_time_str = str(reset_at)

                    latency_ms = int((_time.time() - t0) * 1000)

                    if limit_reached or not allowed or remaining_pct <= 0:
                        err_msg = f"ChatGPT {plan_type.capitalize()} plan quota limit reached (0% remaining)."
                        if reset_time_str:
                            err_msg += f" Resets at {reset_time_str}."
                        err_msg += " Upgrade your ChatGPT subscription or wait for the quota window to reset."
                        self.send_json_response({
                            "success": False,
                            "ok": False,
                            "latency_ms": latency_ms,
                            "plan_type": plan_type,
                            "remaining_pct": 0,
                            "error": err_msg,
                        })
                    else:
                        m_label = f" ({model_id})" if model_id else ""
                        self.send_json_response({
                            "success": True,
                            "ok": True,
                            "latency_ms": latency_ms,
                            "plan_type": plan_type,
                            "remaining_pct": remaining_pct,
                            "message": f"ChatGPT {plan_type.capitalize()} subscription active{m_label} — {remaining_pct}% quota remaining.",
                        })
                except Exception as exc:
                    latency_ms = int((_time.time() - t0) * 1000)
                    if isinstance(exc, _uerr.HTTPError):
                        err_detail = ""
                        try:
                            err_body = exc.read().decode("utf-8", errors="replace")
                            err_json = json.loads(err_body)
                            err_field = err_json.get("error")
                            if isinstance(err_field, dict):
                                err_detail = err_field.get("message") or err_body
                            elif isinstance(err_field, str):
                                err_detail = err_field
                            elif err_json.get("detail"):
                                err_detail = str(err_json["detail"])
                        except Exception:
                            pass
                        self.send_json_response({
                            "success": False,
                            "ok": False,
                            "latency_ms": latency_ms,
                            "error": f"ChatGPT verification error ({exc.code}): {err_detail or exc.reason}",
                        })
                    else:
                        self.send_json_response({
                            "success": False,
                            "ok": False,
                            "latency_ms": latency_ms,
                            "error": f"ChatGPT test failed: {exc}",
                        })
                return

            if provider in ("claude_code", "cursor", "kiro", "copilot"):
                import time as _time
                t0 = _time.time()
                provider_cfg = {}
                try:
                    provider_cfg = video_flow_provider_service.provider(provider) or {}
                except Exception:
                    pass
                provider_name = provider_cfg.get("name") or provider.replace("_", " ").title()

                target_conn = None
                conn_id = data.get("connection_id") or data.get("id")
                if conn_id:
                    try:
                        target_conn = video_flow_provider_service.get_connection(int(conn_id), public=False)
                    except Exception:
                        pass

                if not target_conn:
                    active_conns = [c for c in video_flow_provider_service.list_connections(provider) if c.get("is_active")]
                    if active_conns:
                        target_conn = video_flow_provider_service.pick_best_connection(provider) or active_conns[0]

                if not target_conn or not target_conn.get("is_active"):
                    self.send_json_response({
                        "success": False,
                        "ok": False,
                        "latency_ms": 0,
                        "error": f"No active {provider_name} account connected. Sign in using the Authentication section.",
                    }, 400)
                    return

                try:
                    is_healthy = video_flow_provider_service.connection_is_healthy(target_conn)
                    latency_ms = int(round((_time.time() - t0) * 1000))
                    if is_healthy:
                        m_label = f" ({model_id})" if model_id else ""
                        self.send_json_response({
                            "success": True,
                            "ok": True,
                            "latency_ms": max(1, latency_ms),
                            "message": f"{provider_name} subscription active{m_label}. Session verified.",
                        })
                    else:
                        self.send_json_response({
                            "success": False,
                            "ok": False,
                            "latency_ms": latency_ms,
                            "error": f"{provider_name} session is expired or invalid. Please re-authenticate.",
                        })
                except Exception as exc:
                    latency_ms = int(round((_time.time() - t0) * 1000))
                    self.send_json_response({
                        "success": False,
                        "ok": False,
                        "latency_ms": latency_ms,
                        "error": f"{provider_name} verification error: {exc}",
                    })
                return

            resolved_base_url = ""
            if not key and provider:
                conn_id = data.get("connection_id") or data.get("id")

                prov_cands = [provider]
                for k_alias, v_alias in PROVIDER_ALIASES.items():
                    if v_alias == provider and k_alias not in prov_cands:
                        prov_cands.append(k_alias)
                if provider in ("gemini", "google", "googleai"):
                    for p_alt in ("gemini", "google", "googleai"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("openai", "openai_codex", "codex", "chatgpt"):
                    for p_alt in ("openai", "openai_codex", "codex"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("anthropic", "claude", "claude_code"):
                    for p_alt in ("anthropic", "claude"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("nvidia_nim", "nim", "nvidia"):
                    for p_alt in ("nvidia_nim", "nim", "nvidia"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("together", "together_ai"):
                    for p_alt in ("together", "together_ai"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("mistral", "mistral_ai"):
                    for p_alt in ("mistral", "mistral_ai"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("deepseek", "deepseek_ai"):
                    for p_alt in ("deepseek", "deepseek_ai"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)
                elif provider in ("vertex_ai", "vx", "vertex"):
                    for p_alt in ("vertex_ai", "vx", "vertex"):
                        if p_alt not in prov_cands:
                            prov_cands.append(p_alt)

                # 1. If a specific connection ID is provided, resolve it directly
                if conn_id:
                    try:
                        cid = int(conn_id)
                        vf_c = video_flow_provider_service.get_connection(cid, public=False)
                        if vf_c:
                            secret = video_flow_provider_service.resolve_connection_secret(vf_c)
                            if secret:
                                key = secret
                                resolved_base_url = str((vf_c.get("metadata") or {}).get("base_url") or "")
                    except Exception:
                        pass
                    if not key:
                        for p in prov_cands:
                            try:
                                for c in storage.get_provider_connections(p):
                                    if str(c.get("id")) == str(conn_id) and c.get("api_key"):
                                        key = c["api_key"]
                                        resolved_base_url = str(c.get("baseUrl") or c.get("base_url") or "")
                                        break
                            except Exception:
                                pass
                            if key:
                                break
                    if not key:
                        for p in prov_cands:
                            try:
                                for c in storage.get_audio_provider_connections(p):
                                    if str(c.get("id")) == str(conn_id) and c.get("api_key"):
                                        key = c["api_key"]
                                        resolved_base_url = str(c.get("baseUrl") or c.get("base_url") or "")
                                        break
                            except Exception:
                                pass
                            if key:
                                break

                # 2. If source is video_flow or path is /api/video-flow or kind is video, check Video Flow first
                is_vf = (
                    data.get("source") == "video_flow"
                    or path.startswith("/api/video-flow")
                    or kind == "video"
                )
                if not key and is_vf:
                    for p in prov_cands:
                        try:
                            vf_conns = video_flow_provider_service.active_connections(p)
                            for c in vf_conns:
                                secret = video_flow_provider_service.resolve_connection_secret(c)
                                if secret:
                                    key = secret
                                    resolved_base_url = str((c.get("metadata") or {}).get("base_url") or "")
                                    break
                        except Exception:
                            pass
                        if key:
                            break

                # 3. Audio flow / TTS
                if not key and kind == "tts":
                    for p in prov_cands:
                        try:
                            conns = storage.get_audio_provider_connections(p)
                            for c in conns:
                                if c.get("is_active") and c.get("api_key"):
                                    key = c["api_key"]
                                    resolved_base_url = str(c.get("baseUrl") or c.get("base_url") or "")
                                    break
                        except Exception:
                            pass
                        if key:
                            break

                # 4. Standard Voice Flow connections
                if not key:
                    for p in prov_cands:
                        try:
                            conns = storage.get_provider_connections(p)
                            for c in conns:
                                if c.get("is_active") and c.get("api_key"):
                                    key = c["api_key"]
                                    resolved_base_url = str(c.get("baseUrl") or c.get("base_url") or "")
                                    break
                        except Exception:
                            pass
                        if key:
                            break

                # 5. Video Flow connections fallback
                if not key:
                    for p in prov_cands:
                        try:
                            vf_conns = video_flow_provider_service.active_connections(p)
                            for c in vf_conns:
                                secret = video_flow_provider_service.resolve_connection_secret(c)
                                if secret:
                                    key = secret
                                    resolved_base_url = str((c.get("metadata") or {}).get("base_url") or "")
                                    break
                        except Exception:
                            pass
                        if key:
                            break

                # 6. Audio Flow connections fallback
                if not key:
                    for p in prov_cands:
                        try:
                            conns = storage.get_audio_provider_connections(p)
                            for c in conns:
                                if c.get("is_active") and c.get("api_key"):
                                    key = c["api_key"]
                                    resolved_base_url = str(c.get("baseUrl") or c.get("base_url") or "")
                                    break
                        except Exception:
                            pass
                        if key:
                            break

                # 7. Primary API keys store (storage.get_all_api_keys)
                if not key:
                    try:
                        all_stored = storage.get_all_api_keys() or {}
                        for p in prov_cands:
                            if all_stored.get(p):
                                key = all_stored[p]
                                break
                    except Exception:
                        pass

                # 8. Custom providers
                if not key and provider.startswith("custom-"):
                    try:
                        all_custom = (
                            storage.get_voice_flow_custom_providers()
                            + storage.get_audio_flow_custom_providers()
                            + storage.get_video_flow_custom_providers()
                        )
                        for cp in all_custom:
                            if cp.get("id") == provider:
                                for ak in cp.get("api_keys", []):
                                    if ak.get("is_active", True) and ak.get("key"):
                                        key = ak["key"]
                                        break
                                if not key:
                                    key = cp.get("api_key", "")
                                resolved_base_url = str(cp.get("base_url") or "")
                                break
                    except Exception:
                        pass

                # 9. Environment variables fallback
                if not key:
                    env_candidates = [
                        f"{provider.upper()}_API_KEY",
                        f"{provider.upper()}_KEY",
                        f"{provider.upper()}_TOKEN",
                    ]
                    if provider in ("gemini", "google", "googleai"):
                        env_candidates.extend(["GEMINI_API_KEY", "GOOGLE_API_KEY"])
                    elif provider in ("openai", "openai_codex", "codex", "chatgpt"):
                        env_candidates.extend(["OPENAI_API_KEY"])
                    elif provider in ("anthropic", "claude"):
                        env_candidates.extend(["ANTHROPIC_API_KEY"])
                    elif provider in ("nvidia_nim", "nim", "nvidia"):
                        env_candidates.extend(["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"])
                    elif provider in ("vertex_ai", "vx", "vertex"):
                        env_candidates.extend(["VERTEX_AI_API_KEY", "VERTEX_API_KEY", "VERTEX_AI_KEY"])
                    elif provider in ("together", "together_ai"):
                        env_candidates.extend(["TOGETHER_API_KEY", "TOGETHERAI_API_KEY"])
                    elif provider == "elevenlabs":
                        env_candidates.extend(["ELEVENLABS_API_KEY", "ELEVEN_API_KEY", "XI_API_KEY"])
                    elif provider == "deepgram":
                        env_candidates.extend(["DEEPGRAM_API_KEY"])
                    for env_var in env_candidates:
                        val = os.environ.get(env_var, "").strip()
                        if val:
                            key = val
                            break

            if provider in ("local", "offline", "deterministic") or model_id in ("local/deterministic", "deterministic"):
                self.send_json_response({"success": True, "ok": True, "latency_ms": 0, "message": "Local model available (offline)"})
            elif not key and not provider.startswith("custom-") and provider not in ("edge", "sapi", "sapi5", "windows", "ollama", "lm_studio", "llama_cpp", "antigravity", "openai_codex", "codex", "chatgpt", "claude_code", "cursor", "kiro", "copilot"):
                p_display = provider.replace("_", " ").title()
                self.send_json_response({
                    "success": False,
                    "ok": False,
                    "latency_ms": 0,
                    "error": f"No active API key configured for provider '{provider}'. Please configure an API key for {p_display} first in Settings/Providers.",
                }, 400)
            else:
                _t0 = time.time()
                v_res = self.verify_model_by_kind(provider, key, model_id, kind=kind, base_url=resolved_base_url)
                _latency_ms = int(round((time.time() - _t0) * 1000))
                if not isinstance(v_res, dict):
                    v_res = {"success": bool(v_res), "error": None}
                v_res.setdefault("success", False)
                v_res["ok"] = bool(v_res.get("success"))
                if not v_res.get("latency_ms"):
                    v_res["latency_ms"] = _latency_ms
                self.send_json_response(v_res)

        elif path in ("/api/video-flow/generate", "/api/video-flow/v3/generate"):
            try:
                data.setdefault("provider", "notebooklm")
                data.setdefault("engine", "notebooklm")
                data.setdefault("video_engine", "notebooklm")
                service = get_video_flow_service()
                job = service.queue(**data)
                self.send_json_response({"success": True, "job_id": job.job_id, "video": _shim_video(job)}, 202)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/app/restart":
            try:
                from voice_flow.lifecycle import restart_suite
                ok = restart_suite(runtime_controller)
                if ok:
                    self.send_json_response({
                        "success": True,
                        "message": "Voice Flow suite is deeply restarting cleanly..."
                    })
                else:
                    # A restart sequence is already in flight; a second one
                    # would kill the suite the first sequence just relaunched.
                    self.send_json_response({
                        "success": False,
                        "message": "A restart is already in progress.",
                        "error": "restart_already_in_progress"
                    }, 409)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/settings/autostart/toggle":
            try:
                enabled = bool(data.get("enabled", False))
                from voice_flow.installer import set_autostart
                ok = set_autostart(enabled)
                storage.save_setting("autostart_enabled", enabled)
                msg = "Auto-startup enabled (Windows boot)." if enabled else "Auto-startup disabled."
                self.send_json_response({"success": ok, "enabled": enabled, "message": msg})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/storage/clear-audio-cache":
            try:
                deleted_count = 0
                if hasattr(archive, "root") and archive.root.is_dir():
                    for wav in archive.root.glob("*.wav"):
                        try:
                            wav.unlink(missing_ok=True)
                            deleted_count += 1
                        except Exception:
                            pass
                self.send_json_response({
                    "success": True,
                    "deleted_count": deleted_count,
                    "message": f"Cleared {deleted_count} cached audio recording(s)."
                })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path in ("/api/overlay/show", "/api/overlay/hide", "/api/overlay/toggle", "/api/overlay/reset-position", "/api/overlay/dock"):
            overlay = getattr(runtime_controller, "overlay", None) if runtime_controller else None
            if overlay:
                if path == "/api/overlay/show":
                    if hasattr(overlay, "show"):
                        overlay.show()
                    if hasattr(overlay, "reset_position"):
                        overlay.reset_position()
                elif path == "/api/overlay/reset-position" and hasattr(overlay, "reset_position"):
                    overlay.reset_position()
                elif path == "/api/overlay/hide" and hasattr(overlay, "hide"):
                    overlay.hide()
                elif path == "/api/overlay/toggle":
                    if hasattr(overlay, "win") and overlay.win and hasattr(overlay, "hide") and getattr(overlay, "_visible", True):
                        overlay.hide()
                    elif hasattr(overlay, "show"):
                        overlay.show()
                elif path == "/api/overlay/dock" and hasattr(overlay, "set_dock"):
                    overlay.set_dock(data.get("dock", "bottom"))
            self.send_json_response({"success": True})

        elif path in (
            "/api/video-flow/notebooklm/auth/check",
            "/api/video-flow/notebooklm/auth/login",
            "/api/video-flow/notebooklm/auth/start",
            "/api/video-flow/notebooklm/auth/sync",
            "/api/video-flow/notebooklm/sync",
            "/api/video-flow/notebooklm/auth/sync-browser",
            "/api/video-flow/notebooklm/auth/import-cookies",
            "/api/video-flow/notebooklm/auth/disconnect",
            "/api/video-flow/notebooklm/disconnect",
            "/api/video-flow/notebooklm/mcp/refresh",
            "/api/video-flow/notebooklm/mcp/health",
            "/api/video-flow/notebooklm/keepalive/start",
            "/api/video-flow/notebooklm/keepalive/stop",
            "/api/video-flow/notebooklm/keepalive/refresh",
            "/api/video-flow/notebooklm/keepalive/check",
        ):
            # POST auth/start|login|sync = launch Chrome sign-in / session extraction
            # POST auth/check = online verification against Google
            # POST auth/disconnect = disconnect session and mark unauthenticated
            # POST mcp/refresh = run durable session refresh
            # POST mcp/health = check MCP server connectivity and status
            # POST keepalive/start|stop|refresh = manage background refresh daemon
            try:
                from voice_flow.video_flow_engine.notebooklm import (
                    NotebookLMMcpClient,
                    get_keepalive_service,
                    get_keepalive_status,
                    login_flow,
                    start_keepalive_daemon,
                    stop_keepalive_daemon,
                )

                if path in ("/api/video-flow/notebooklm/auth/disconnect", "/api/video-flow/notebooklm/disconnect"):
                    stop_keepalive_daemon()
                    result = login_flow.disconnect_login(profile=data.get("profile"))
                    try:
                        storage.save_setting("video_flow_notebooklm_authenticated", False)
                        storage.save_setting("video_flow_notebooklm_email", "")
                        storage.save_setting("video_flow_notebooklm_disconnected", True)
                    except Exception:
                        pass
                    self.send_json_response({"success": True, **result})
                elif path == "/api/video-flow/notebooklm/auth/check":
                    req_prof = (data.get("profile") if isinstance(data, dict) else None) or "video-flow-experiment"
                    prof_auth, prof_email, _, prof_det = _read_notebooklm_storage_state(req_prof)
                    if not prof_auth or prof_det.get("disconnected"):
                        self.send_json_response({
                            "success": True,
                            "auth": {
                                "authenticated": False,
                                "status": "unauthenticated",
                                "message": "NotebookLM is not connected — please log in first",
                                "email": None,
                                "master_token_present": False,
                                "online": False,
                            },
                        })
                    else:
                        verification = login_flow.verify_online(profile=req_prof, force=True)
                        self.send_json_response({
                            "success": True,
                            "auth": {
                                "authenticated": verification.get("authenticated", False),
                                "status": verification.get("status", "error"),
                                "message": verification.get("message", ""),
                                "email": verification.get("email") or prof_email,
                                "master_token_present": verification.get("master_token_present", False),
                                "online": True,
                            },
                        })
                elif path in ("/api/video-flow/notebooklm/auth/sync", "/api/video-flow/notebooklm/sync"):
                    result = login_flow.start_login(
                        profile=data.get("profile"),
                        account_email=data.get("account_email") or data.get("account"),
                        mode="cli",
                        browser=str(data.get("browser") or "chrome"),
                        browser_timeout=max(60, min(int(data.get("browser_timeout") or 300), 900)),
                        switch_account=bool(data.get("switch_account")),
                    )
                    self.send_json_response({"success": bool(result.get("launched")), **result}, 400 if not result.get("launched") else 200)
                elif path == "/api/video-flow/notebooklm/mcp/refresh":
                    profile = data.get("profile")
                    res = login_flow.ensure_fresh_session(profile=profile, force=True)
                    self.send_json_response({"success": bool(res.get("ok")), "refresh": res})
                elif path == "/api/video-flow/notebooklm/mcp/health":
                    profile = data.get("profile")
                    client = NotebookLMMcpClient(profile=profile)
                    health = client.check_health()
                    self.send_json_response({"success": True, "health": health})
                elif path == "/api/video-flow/notebooklm/keepalive/start":
                    interval = max(300, int(data.get("interval_seconds") or 1200))
                    started = start_keepalive_daemon(profile=data.get("profile"), interval_seconds=interval)
                    self.send_json_response({"success": True, "started": started, "keepalive": get_keepalive_status()})
                elif path == "/api/video-flow/notebooklm/keepalive/stop":
                    stopped = stop_keepalive_daemon()
                    self.send_json_response({"success": True, "stopped": stopped, "keepalive": get_keepalive_status()})
                elif path in ("/api/video-flow/notebooklm/keepalive/refresh", "/api/video-flow/notebooklm/keepalive/check"):
                    target_prof = data.get("profile") if isinstance(data, dict) else None
                    service = get_keepalive_service(target_prof)
                    force = bool(data.get("force")) if isinstance(data, dict) else False
                    background = bool(data.get("background")) if isinstance(data, dict) else False
                    if background:
                        res = service.trigger_now(force=force, background=True)
                    else:
                        res = service.run_once(force=force)
                    self.send_json_response({"success": bool(res.get("success", res.get("dispatched", False))), "result": res, "keepalive": service.status()})
                elif path == "/api/video-flow/notebooklm/auth/sync-browser":
                    from voice_flow.video_flow_engine.notebooklm import browser_sync
                    profile = data.get("profile")
                    preferred_browser = data.get("browser")
                    expected_email = data.get("email") or data.get("expected_email")
                    if not expected_email:
                        _, active_email, _, _ = _read_notebooklm_storage_state(profile)
                        if active_email:
                            expected_email = active_email
                        else:
                            try:
                                stored_em = storage.get_setting("video_flow_notebooklm_email")
                                if stored_em and str(stored_em).strip():
                                    expected_email = str(stored_em).strip()
                            except Exception:
                                pass
                    try:
                        res = browser_sync.auto_sync_from_browser(
                            profile=profile,
                            preferred_browser=preferred_browser,
                            expected_email=expected_email,
                        )
                    except TypeError:
                        res = browser_sync.auto_sync_from_browser(
                            profile=profile,
                            preferred_browser=preferred_browser,
                        )
                    if res.get("success"):
                        try:
                            storage.save_setting("video_flow_notebooklm_disconnected", False)
                            storage.save_setting("video_flow_notebooklm_authenticated", True)
                            if res.get("email"):
                                storage.save_setting("video_flow_notebooklm_email", res.get("email"))
                        except Exception:
                            pass
                    self.send_json_response(res, 200 if res.get("success") else 400)
                elif path == "/api/video-flow/notebooklm/auth/import-cookies":
                    from voice_flow.video_flow_engine.notebooklm import browser_sync
                    profile = data.get("profile")
                    payload = data.get("cookies") or data.get("payload") or data.get("data")
                    email = data.get("email")
                    res = browser_sync.import_cookies(payload, profile=profile, email=email)
                    self.send_json_response(res, 200 if res.get("success") else 400)
                else:
                    result = login_flow.start_login(
                        profile=data.get("profile"),
                        account_email=data.get("account_email") or data.get("account"),
                        mode=data.get("mode") or "browser",
                        browser=str(data.get("browser") or "chrome"),
                        browser_timeout=max(60, min(int(data.get("browser_timeout") or 300), 900)),
                        switch_account=bool(data.get("switch_account")),
                        port=self._server_port(),
                        direct=bool(data.get("direct", True)),
                        cookie_payload=data.get("cookies") or data.get("payload"),
                    )
                    self.send_json_response({"success": bool(result.get("launched")), **result}, 400 if not result.get("launched") else 200)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/video-flow/cancel", "/api/video-flow/videos/cancel", "/api/video-flow/jobs/cancel"):
            video_id = str(data.get("id") or data.get("video_id") or data.get("job_id") or "").strip()
            if video_id and not SAFE_JOB_ID_REGEX.fullmatch(video_id):
                self.send_json_response({"success": False, "error": "Invalid video id."}, 400)
                return
            try:
                service = get_video_flow_service()
                if not video_id and hasattr(service, "list"):
                    for j in service.list(10):
                        if str(getattr(j, "state", "") or "").lower() not in ("complete", "completed", "ready", "failed", "cancelled", "canceled"):
                            video_id = getattr(j, "job_id", "")
                            break
                if not video_id:
                    self.send_json_response({"success": False, "error": "No active video job to cancel"}, 400)
                else:
                    if hasattr(service, "cancel"):
                        service.cancel(video_id)
                    self.send_json_response({"success": True, "id": video_id, "status": "cancelled"})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path in ("/api/video-flow/videos/delete", "/api/video-flow/combos/delete"):
            video_id = str(data.get("id") or data.get("video_id") or "").strip()
            if not video_id:
                self.send_json_response({"success": False, "error": "Video id required"}, 400)
            elif not SAFE_JOB_ID_REGEX.fullmatch(video_id):
                self.send_json_response({"success": False, "error": "Invalid video id."}, 400)
            else:
                try:
                    service = get_video_flow_service()
                    if hasattr(service, "cancel"):
                        service.cancel(video_id)
                    if hasattr(service, "delete"):
                        service.delete(video_id)
                    self.send_json_response({"success": True, "id": video_id})
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/providers/models/toggle":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers()
                              if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                idx = _find_model_index(models, cid_raw)
                if idx < 0 or idx >= len(models):
                    self.send_json_response({"success": False, "error": "Model not found."}, 404)
                    return
                models[idx]["is_active"] = bool(data.get("is_active", True)) if "is_active" in data else not models[idx].get("is_active", True)
                entry["models"] = models
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            try:
                cid = int(data.get("id"))
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
                return
            video_flow_provider_service.set_model_active(cid, bool(data.get("is_active", True)))
            self.send_json_response({"success": True})

        elif path in ("/api/providers/models/toggle", "/api/models/toggle"):
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                idx = _find_model_index(models, cid_raw)
                if 0 <= idx < len(models):
                    models[idx]["is_active"] = bool(data.get("is_active", True)) if "is_active" in data else not models[idx].get("is_active", True)
                    entry["models"] = models
                    storage.add_voice_flow_custom_provider(entry)
                    self.send_json_response({"success": True})
                    return
                self.send_json_response({"success": False, "error": "Model not found."}, 404)
                return
            try:
                mid = int(data.get("id"))
                active = bool(data.get("is_active", True))
                success = storage.toggle_provider_model(mid, active)
                self.send_json_response({"success": success})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/audio-providers/models/add":
            provider = (data.get("provider") or "").lower().strip()
            provider = _canonical_provider_for_kind(provider, "tts")
            model_id = (data.get("model_id") or "").strip()
            model_id = strip_redundant_model_prefix(provider, model_id)
            display_name = (data.get("display_name") or "").strip() or model_id
            if not provider or not model_id:
                self.send_json_response({"success": False, "error": "provider and model_id are required."}, 400)
                return

            if data.get("verify") or data.get("validate"):
                v_res = self.verify_model_by_kind(provider, key=data.get("key", ""), model_id=model_id, kind="tts")
                if not v_res.get("success"):
                    self.send_json_response({"success": False, "error": v_res.get("error") or "Voice model verification failed."}, 400)
                    return
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                models.append({
                    "id": _new_custom_item_id("m"),
                    "model_id": model_id,
                    "display_name": display_name,
                    "is_active": True,
                    "custom": True,
                })
                entry["models"] = models
                storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "models": models})
                return
            success = storage.add_tts_model(provider, model_id, display_name)
            self.send_json_response({"success": success})

        elif path in ("/api/audio-providers/models/delete", "/api/audio-models/delete"):
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                idx = _find_model_index(models, cid_raw)
                if 0 <= idx < len(models):
                    models.pop(idx)
                else:
                    mid = str(data.get("model_id") or cid_raw)
                    models = [m for m in models if str(m.get("model_id")) != mid]
                entry["models"] = models
                storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "models": models})
                return
            mid = data.get("id") or data.get("model_id")
            success = storage.delete_tts_model(mid, provider=provider)
            self.send_json_response({"success": success})

        elif path == "/api/audio-providers/models/toggle":
            cid_raw = str(data.get("id") or "")
            provider = str(data.get("provider") or "").strip().lower()
            if cid_raw.startswith("m-") or provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                models = entry.get("models") or []
                idx = _find_model_index(models, cid_raw)
                if 0 <= idx < len(models):
                    models[idx]["is_active"] = bool(data.get("is_active", True)) if "is_active" in data else not models[idx].get("is_active", True)
                    entry["models"] = models
                    storage.add_audio_flow_custom_provider(entry)
                    self.send_json_response({"success": True})
                    return
                self.send_json_response({"success": False, "error": "Model not found."}, 404)
                return
            try:
                mid = int(data.get("id"))
                active = bool(data.get("is_active", True))
                success = storage.toggle_tts_model(mid, active)
                self.send_json_response({"success": success})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/video-flow/settings/model", "/api/models/save", "/api/models/select"):
            model_id = str(data.get("model") or data.get("model_id") or data.get("model_ref") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_ref is required."}, 400)
                return
            catalog_models = _video_flow_catalog().get("models") or []
            match = next((item for item in catalog_models if str(item.get("full_id") or "") == model_id), None)
            if model_id != "local/deterministic" and not match:
                # A model the user added to their own provider list is a valid
                # selection even though it is not in the Video Flow catalog
                # (that catalog only lists connected providers' models). Accept
                # an explicitly configured provider/model rather than rejecting
                # the user's own addition.
                if not _model_is_user_configured(model_id):
                    self.send_json_response({"success": False, "error": "This model is not in the Video Flow catalog."}, 400)
                    return
            if match and (match.get("is_active") is False or match.get("available") is False):
                self.send_json_response({"success": False, "error": "This model is disabled or its provider is not connected."}, 400)
                return
            storage.save_setting("video_flow_selected_model", model_id)
            storage.save_setting("exec_policy_model", model_id)
            self.send_json_response({"success": True, "model": model_id})

        elif path in ("/api/audio-summary/settings/model", "/api/audio-summary/model/save"):
            model_id = str(data.get("model") or data.get("model_id") or data.get("model_ref") or "").strip()
            storage.save_setting("exec_audio_summary_model", model_id)
            self.send_json_response({"success": True, "model": model_id})

        elif path == "/api/audio-summary/settings/consent":
            consent = bool(data.get("consent", data.get("allow_external_ai", False)))
            storage.save_setting("exec_audio_summary_allow_external_ai", consent)
            self.send_json_response({"success": True, "consent": consent})

        elif path == "/api/settings/hotkey":
            if not isinstance(data, dict):
                self.send_json_response({"success": False, "error": "Invalid request body: JSON object required"}, 400)
                return
            payload = dict(data)
            if "trigger" in payload and "hotkey_trigger" not in payload:
                payload["hotkey_trigger"] = payload["trigger"]
            if "hotkey" in payload and "custom_hotkey" not in payload:
                payload["custom_hotkey"] = payload["hotkey"]
            if "mode" in payload and "dictation_trigger_mode" not in payload:
                payload["dictation_trigger_mode"] = payload["mode"]

            valid_triggers = {"ctrl_win", "single_ctrl", "double_ctrl", "alt_space", "alt_tab", "middle_click", "custom"}
            if "hotkey_trigger" in payload and payload["hotkey_trigger"] is not None:
                trig = str(payload["hotkey_trigger"]).lower().strip()
                if trig not in valid_triggers:
                    self.send_json_response({"success": False, "error": f"Invalid hotkey trigger: '{trig}'"}, 400)
                    return
                payload["hotkey_trigger"] = trig

            valid_modes = {"hybrid", "ptt_only", "toggle_only", "disabled"}
            if "dictation_trigger_mode" in payload and payload["dictation_trigger_mode"] is not None:
                m = str(payload["dictation_trigger_mode"]).lower().strip()
                if m not in valid_modes:
                    self.send_json_response({"success": False, "error": f"Invalid dictation trigger mode: '{m}'"}, 400)
                    return
                payload["dictation_trigger_mode"] = m

            valid_custom_types = {"double_tap", "hold", "mouse_button", "toggle"}
            if "custom_trigger_type" in payload and payload["custom_trigger_type"] is not None:
                ct = str(payload["custom_trigger_type"]).lower().strip()
                if ct in valid_custom_types:
                    payload["custom_trigger_type"] = ct

            updated = storage.save_hotkey_settings(payload) if hasattr(storage, "save_hotkey_settings") else {}
            # Live reload hook to switch active triggers immediately without restarting
            try:
                if runtime_controller is not None:
                    if hasattr(runtime_controller, "reload_hotkeys"):
                        runtime_controller.reload_hotkeys(updated)
                    elif hasattr(runtime_controller, "hotkeys") and runtime_controller.hotkeys is not None:
                        runtime_controller.hotkeys.reload_config(updated)
            except Exception as exc:
                log.warning("Could not live reload hotkeys: %s", exc)

            self.send_json_response({"success": True, "message": "Hotkey settings updated and reloaded", "settings": updated})

        elif path == "/api/settings/update":
            key = str(data.get("key") or "").strip()
            val = data.get("value")
            if not key:
                self.send_json_response({"success": False, "error": "Missing setting key"}, 400)
            elif re.search(r"token|secret|password|api[_-]?key|credential", key, re.IGNORECASE):
                # Never let HTTP requests plant credential-shaped settings:
                # GET /api/settings/all would expose them to any local page.
                self.send_json_response({"success": False, "error": "Protected setting key"}, 400)
            elif key in PROTECTED_SETTING_KEYS:
                # Overwriting e.g. seed_version forces a catalog re-seed that
                # wipes user-added models; these keys have dedicated endpoints.
                self.send_json_response({"success": False, "error": "Protected setting; use its dedicated endpoint."}, 403)
            else:
                # AI polishing is a Boolean safety switch.  Accepting a
                # truthy string such as "false" makes a saved Off setting
                # silently turn back on after a reload.
                if key == "polishing_enabled" and not isinstance(val, bool):
                    self.send_json_response({"success": False, "error": "polishing_enabled must be a boolean"}, 400)
                    return
                if not storage.save_setting(key, val):
                    self.send_json_response({"success": False, "error": "Could not save setting"}, 500)
                    return
                if key == "autostart_enabled":
                    try:
                        from voice_flow.installer import set_autostart
                        set_autostart(bool(val))
                    except Exception:
                        pass
                if key == "show_in_taskbar":
                    # The desktop launcher only reads this preference while it is
                    # building the window, so toggling it used to persist the value
                    # and change nothing until the next app start. Re-apply the
                    # native window style immediately so the switch takes effect.
                    try:
                        from voice_flow.gui.desktop_launcher import _apply_taskbar_visibility
                        _apply_taskbar_visibility(None, bool(val))
                    except Exception:
                        pass
                if key in ("hotkey_trigger", "custom_hotkey", "dictation_trigger_mode", "middle_click_enabled", "ctrl_key_dictation_enabled", "push_to_talk_shortcut"):
                    try:
                        if hasattr(storage, "save_hotkey_settings"):
                            storage.save_hotkey_settings({key: val})
                        if runtime_controller is not None:
                            if hasattr(runtime_controller, "reload_hotkeys"):
                                runtime_controller.reload_hotkeys({key: val})
                            elif hasattr(runtime_controller, "hotkeys") and runtime_controller.hotkeys is not None:
                                runtime_controller.hotkeys.reload_config({key: val})
                    except Exception:
                        pass
                self.send_json_response({"success": True, "key": key, "value": val})

        elif path == "/api/voice-flow-polish/update":
            resp_payload = {"success": True}
            if "polishing_enabled" in data or "enabled" in data:
                p_val = data.get("polishing_enabled") if "polishing_enabled" in data else data.get("enabled")
                if not isinstance(p_val, bool):
                    self.send_json_response({"success": False, "error": "polishing_enabled must be a boolean"}, 400)
                    return
                if not storage.save_setting("polishing_enabled", p_val):
                    self.send_json_response({"success": False, "error": "Could not save polishing setting"}, 500)
                    return
                resp_payload["polishing_enabled"] = p_val
            if "speed_mode" in data:
                sm = str(data.get("speed_mode") or "").strip()
                if sm:
                    storage.save_setting("voice_flow_polish_speed_mode", sm)
                    resp_payload["speed_mode"] = sm
                else:
                    resp_payload["speed_mode"] = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
            else:
                resp_payload["speed_mode"] = storage.get_setting("voice_flow_polish_speed_mode", "balanced")
            model_id = str(data.get("model") or data.get("model_id") or data.get("model_ref") or "").strip()
            if model_id:
                # A connected catalog entry without a Voice polish adapter is
                # intentionally visible-but-disabled.  Do not report a
                # successful save for a model the runtime cannot execute.
                if model_id not in ("local/deterministic", "microsoft/windows-ai-text-rewriter", "windows/text-rewriter", "local/lfm2.5-350m-qad-q4_0", "liquid/lfm2.5-350m-qad-q4_0"):
                    try:
                        from voice_flow.voice_polish_bridge import can_execute_model
                        is_video_catalog_model = any(
                            str(item.get("full_id") or "") == model_id
                            for item in video_flow_provider_service.list_models()
                        )
                        if is_video_catalog_model and not can_execute_model(model_id) and not model_id.lower().startswith(("antigravity/", "agy/")):
                            self.send_json_response({"success": False, "error": "Polishing is not supported by this connection"}, 400)
                            return
                    except Exception:
                        # Catalog lookup failures must not invalidate the
                        # established legacy Voice Flow compatibility path.
                        pass
                storage.save_setting("voice_flow_polish_model", model_id)
                resp_payload["active_model"] = model_id
            else:
                default_polish = storage.get_default_polish_model() if hasattr(storage, "get_default_polish_model") else "local/deterministic"
                resp_payload["active_model"] = storage.get_setting("voice_flow_polish_model", default_polish)
            self.send_json_response(resp_payload)

        elif path == "/api/video-flow/voice":
            voice = str(data.get("voice") or data.get("model") or data.get("voice_model") or "").strip()
            if voice:
                storage.save_setting("video_flow_voice_model", voice)
            self.send_json_response({"success": True, "active_voice": voice or storage.get_setting("video_flow_voice_model", "edge/en-US-AvaNeural")})

        elif path in ("/api/audio-providers/connections/add", "/api/audio-providers/connections/update", "/api/audio-providers/connections/delete", "/api/audio-providers/connections/toggle", "/api/audio-providers/connections/test"):
            if path == "/api/audio-providers/connections/add":
                provider = data.get("provider", "elevenlabs").lower()
                name = data.get("name", "").strip()
                key = data.get("key", "").strip()
                try:
                    priority = int(data.get("priority", 1))
                except (TypeError, ValueError):
                    priority = 1
                if provider.startswith("custom-"):
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                        return
                    conns = entry.get("api_keys") or []
                    if not conns and str(entry.get("api_key") or ""):
                        conns = [{"name": str(entry.get("name") or provider) + " key",
                                  "key": str(entry.get("api_key")),
                                  "is_active": True, "priority": 1, "status": "untested"}]
                    new_conn = {
                        "id": _new_custom_item_id("c"),
                        "name": name or f"{entry.get('name') or provider} key #{len(conns) + 1}",
                        "key": key,
                        "priority": priority or (len(conns) + 1),
                        "is_active": True,
                        "status": "untested",
                    }
                    conns.append(new_conn)
                    entry["api_keys"] = conns
                    if not entry.get("api_key"):
                        entry["api_key"] = key
                    storage.add_audio_flow_custom_provider(entry)
                    public_conn = {**new_conn, "key": "", "has_secret": bool(new_conn.get("key"))}
                    self.send_json_response({"success": True, "connection": public_conn, "message": "Connection added successfully!"})
                    return

                v_res = self.verify_tts_api_key(provider, key)
                if v_res.get("valid"):
                    new_conn = storage.add_audio_provider_connection(provider, name, key, priority)
                    storage.update_audio_provider_connection_validation(int(new_conn["id"]), True, None)
                    public_conn = {k: v for k, v in new_conn.items() if k not in {"api_key", "data"}}
                    public_conn["is_valid"] = 1
                    public_conn["last_tested_status"] = "Connected"
                    public_conn["has_secret"] = bool(key)
                    self.send_json_response({"success": True, "connection": public_conn, "message": "Connection added successfully!"})
                else:
                    self.send_json_response({"success": False, "error": v_res.get("status", "Validation failed.")})
            elif path == "/api/audio-providers/connections/update":
                cid_raw = str(data.get("id") or "")
                provider = str(data.get("provider") or "").strip().lower()
                if cid_raw.startswith("c-") or provider.startswith("custom-"):
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                        return
                    conns = entry.get("api_keys") or []
                    cidx = _find_conn_index(conns, cid_raw)
                    if 0 <= cidx < len(conns):
                        c = conns[cidx]
                        if str(data.get("name") or "").strip():
                            c["name"] = str(data.get("name")).strip()
                        if str(data.get("key") or data.get("secret") or "").strip():
                            c["key"] = str(data.get("key") or data.get("secret")).strip()
                        if data.get("priority"):
                            try:
                                c["priority"] = int(data.get("priority"))
                            except Exception:
                                pass
                        if conns:
                            entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                        entry["api_keys"] = conns
                        storage.add_audio_flow_custom_provider(entry)
                        self.send_json_response({"success": True})
                        return
                    self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                    return

                cid = int(data.get("id"))
                name = data.get("name", "").strip()
                key = data.get("key", "").strip()
                priority = int(data.get("priority", 1))
                if not key:
                    try:
                        with sqlite3.connect(storage.db_path) as conn:
                            row = conn.execute("SELECT api_key FROM audio_provider_connections WHERE id = ?", (cid,)).fetchone()
                            key = (row[0] or "").strip() if row else ""
                    except Exception:
                        key = ""
                success = storage.update_audio_provider_connection(cid, name, key, priority)
                self.send_json_response({"success": success})
            elif path == "/api/audio-providers/connections/toggle":
                cid_raw = str(data.get("id") or "")
                provider = str(data.get("provider") or "").strip().lower()
                if cid_raw.startswith("c-") or provider.startswith("custom-"):
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                        return
                    conns = entry.get("api_keys") or []
                    cidx = _find_conn_index(conns, cid_raw)
                    if 0 <= cidx < len(conns):
                        conns[cidx]["is_active"] = bool(data.get("is_active", True))
                        if conns:
                            entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                        entry["api_keys"] = conns
                        storage.add_audio_flow_custom_provider(entry)
                        self.send_json_response({"success": True})
                        return
                    self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                    return

                cid = int(data.get("id"))
                active = bool(data.get("is_active", True))
                success = storage.toggle_audio_provider_connection(cid, active)
                self.send_json_response({"success": success})
            elif path == "/api/audio-providers/connections/delete":
                cid_raw = str(data.get("id") or "")
                provider = str(data.get("provider") or "").strip().lower()
                if cid_raw == "custom":
                    providers = storage.delete_audio_flow_custom_provider(provider)
                    self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                    return
                if cid_raw.startswith("c-") or provider.startswith("custom-"):
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                        return
                    conns = entry.get("api_keys") or []
                    cidx = _find_conn_index(conns, cid_raw)
                    if 0 <= cidx < len(conns):
                        conns.pop(cidx)
                        entry["api_keys"] = conns
                        entry["api_key"] = str(next((k["key"] for k in conns if k.get("is_active") and k.get("key")), ""))
                        storage.add_audio_flow_custom_provider(entry)
                        self.send_json_response({"success": True})
                        return
                    self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                    return

                cid = int(data.get("id"))
                success = storage.delete_audio_provider_connection(cid)
                self.send_json_response({"success": success})
            elif path == "/api/audio-providers/connections/test":
                cid = data.get("id")
                cid_raw = str(cid or "")
                provider = str(data.get("provider") or "elevenlabs").lower()
                key = str(data.get("key") or "").strip()

                if cid_raw.startswith("c-") or provider.startswith("custom-"):
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                    if entry:
                        conns = entry.get("api_keys") or []
                        cidx = _find_conn_index(conns, cid_raw)
                        if 0 <= cidx < len(conns) and not key:
                            key = str(conns[cidx].get("key") or "")
                        if not key:
                            key = str(entry.get("api_key") or "")
                        v_res = self.verify_tts_api_key(provider, key)
                        valid = bool(v_res.get("valid"))
                        status_str = v_res.get("status") or ("Connected (200 OK)" if valid else "Failed")
                        if 0 <= cidx < len(conns):
                            conns[cidx]["status"] = "connected" if valid else "error"
                            conns[cidx]["last_tested_status"] = status_str
                            entry["api_keys"] = conns
                            storage.add_audio_flow_custom_provider(entry)
                        self.send_json_response({"success": valid, "valid": valid, "status": status_str})
                        return

                if not key and cid:
                    conns = storage.get_all_audio_provider_connections()
                    for p_list in conns.values():
                        for c in p_list:
                            if str(c.get("id")) == str(cid) or str(c.get("uuid_id")) == str(cid):
                                key = c.get("api_key", "").strip()
                                provider = provider or c.get("provider", "").lower()
                                break
                        if key:
                            break
                if not key and provider:
                    try:
                        aconns = storage.get_audio_provider_connections(provider)
                        for c in aconns:
                            if c.get("is_active") and c.get("api_key"):
                                key = c["api_key"].strip()
                                break
                    except Exception:
                        pass
                if not key:
                    v_res = {"status": "Error: API key cannot be empty", "valid": False}
                else:
                    v_res = self.verify_tts_api_key(provider, key)
                if cid:
                    storage.update_audio_provider_connection_status(int(cid), v_res.get("status", "Unknown"))
                self.send_json_response({"success": v_res.get("valid", False), "valid": v_res.get("valid", False), "status": v_res.get("status")})

        elif path in ("/api/video-flow/providers/connections/add", "/api/video-flow/providers/connections/update", "/api/video-flow/providers/connections/delete", "/api/video-flow/providers/connections/toggle", "/api/video-flow/providers/connections/test"):
            if path == "/api/video-flow/providers/connections/delete" and str(data.get("id") or "") == "custom":
                provider = str(data.get("provider") or "").strip().lower()
                providers = storage.delete_video_flow_custom_provider(provider)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            if str(data.get("provider") or "").startswith("custom-"):
                cprov = str(data.get("provider") or "").strip().lower()
                entry = next((cp for cp in storage.get_video_flow_custom_providers()
                              if cp.get("id") == cprov), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                if not conns and str(entry.get("api_key") or ""):
                    # Seed the original single key as the first connection so
                    # adding a second key keeps both.
                    conns = [{"name": str(entry.get("name") or cprov) + " key",
                              "key": str(entry.get("api_key")),
                              "is_active": True, "status": "untested"}]
                if conns and not entry.get("api_key"):
                    entry["api_key"] = str(conns[0].get("key") or "")
                if path == "/api/video-flow/providers/connections/add":
                    bulk_keys = data.get("keys") if isinstance(data.get("keys"), list) else []
                    if bulk_keys:
                        for item in bulk_keys:
                            if isinstance(item, dict) and str(item.get("secret") or item.get("key") or "").strip():
                                conns.append({
                                    "id": _new_custom_item_id("c"),
                                    "name": str(item.get("name") or ("Key " + str(len(conns) + 1))),
                                    "key": str(item.get("secret") or item.get("key") or ""),
                                    "priority": len(conns) + 1,
                                    "is_active": True, "status": "untested",
                                })
                    else:
                        conns.append({
                            "id": _new_custom_item_id("c"),
                            "name": str(data.get("name") or "Key"),
                            "key": str(data.get("secret") or data.get("key") or ""),
                            "priority": int(data["priority"]) if str(data.get("priority") or "").strip().lstrip("-").isdigit() else (len(conns) + 1),
                            "is_active": True, "status": "untested",
                        })
                elif path == "/api/video-flow/providers/connections/update":
                    cidx = _find_conn_index(conns, data.get("id"))
                    if cidx < 0 or cidx >= len(conns):
                        self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                        return
                    c = conns[cidx]
                    if str(data.get("name") or ""): c["name"] = str(data.get("name"))
                    if str(data.get("secret") or data.get("key") or ""): c["key"] = str(data.get("secret") or data.get("key"))
                    if data.get("priority") and str(data.get("priority")).strip().lstrip("-").isdigit(): c["priority"] = int(data["priority"])
                elif path == "/api/video-flow/providers/connections/toggle":
                    cidx = _find_conn_index(conns, data.get("id"))
                    if cidx < 0 or cidx >= len(conns):
                        self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                        return
                    conns[cidx]["is_active"] = bool(data.get("is_active", True))
                elif path == "/api/video-flow/providers/connections/delete":
                    cidx = _find_conn_index(conns, data.get("id"))
                    if cidx < 0 or cidx >= len(conns):
                        self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                        return
                    conns.pop(cidx)
                elif path == "/api/video-flow/providers/connections/test":
                    cidx = _find_conn_index(conns, data.get("id"))
                    if cidx < 0 or cidx >= len(conns):
                        self.send_json_response({"success": False, "error": "Connection not found."}, 404)
                        return
                    ckey = str(conns[cidx].get("key") or "")
                    res = self._probe_custom_endpoint_direct(
                        base_url=str(entry.get("base_url") or ""),
                        api_key=ckey,
                        api_format=str(entry.get("api_format") or "openai").lower(),
                        model_id=((entry.get("models") or [{}])[0].get("model_id") or ""),
                        kind="llm",
                        headers=entry.get("headers"),
                    )
                    if res.get("success"):
                        conns[cidx]["status"] = "connected"
                        saved = {"success": True, "status": "active"}
                    else:
                        conns[cidx]["status"] = "error"
                        saved = {"success": False, "status": "error", "error": str(res.get("error") or "Test failed")[:200]}
                    if conns:
                        entry["api_key"] = str(next((c["key"] for c in conns if c.get("is_active") and c.get("key")), ""))
                    storage.add_video_flow_custom_provider(entry)
                    self.send_json_response(saved)
                    return
                else:
                    self.send_json_response({"success": True})
                    return
                entry["api_key"] = str(next((c["key"] for c in conns if c.get("is_active") and c.get("key")), ""))
                entry["api_keys"] = conns
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return

            if path == "/api/video-flow/providers/connections/add":
                provider = str(data.get("provider") or "").lower()
                name = str(data.get("name") or "")
                secret = str(data.get("secret") or data.get("key") or "")
                try:
                    priority = int(data.get("priority") or 1)
                except (TypeError, ValueError) as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                    return
                metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                if not provider:
                    self.send_json_response({"success": False, "error": "Provider is required."}, 400)
                    return
                bulk_added = 0
                for item in (data.get("keys") if isinstance(data.get("keys"), list) else []):
                    if isinstance(item, dict) and str(item.get("secret") or item.get("key") or "").strip():
                        try:
                            video_flow_provider_service.add_connection(provider, name=str(item.get("name") or "Key"), secret=str(item.get("secret") or item.get("key")), priority=int(item.get("priority") or (bulk_added + 1)), metadata=metadata)
                            bulk_added += 1
                        except Exception:
                            pass
                if bulk_added:
                    self.send_json_response({"success": True, "added": bulk_added, "message": f"{bulk_added} connections added successfully!"})
                    return
                try:
                    conn_row = video_flow_provider_service.add_connection(provider, name=name, secret=secret, priority=priority, metadata=metadata)
                    self.send_json_response({"success": True, "connection": conn_row, "message": "Connection added successfully!"})
                except ValueError as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)
            elif path == "/api/video-flow/providers/connections/update":
                try:
                    cid = int(data.get("id"))
                except (TypeError, ValueError) as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                    return
                changes = {}
                if "name" in data and str(data.get("name") or "").strip():
                    changes["name"] = str(data.get("name"))
                if ("secret" in data or "key" in data) and isinstance(data.get("secret", data.get("key")), str) and str(data.get("secret", data.get("key")) or ""):
                    changes["secret"] = str(data.get("secret", data.get("key")))
                if "priority" in data:
                    try:
                        changes["priority"] = int(data.get("priority"))
                    except (TypeError, ValueError):
                        pass
                if isinstance(data.get("metadata"), dict):
                    changes["metadata"] = data.get("metadata")
                if "is_active" in data:
                    changes["is_active"] = bool(data.get("is_active"))
                result = video_flow_provider_service.update_connection(cid, **changes)
                if result is not None:
                    self.send_json_response({"success": True})
                else:
                    self.send_json_response({"success": False, "error": "Connection not found."}, 404)
            elif path == "/api/video-flow/providers/connections/toggle":
                try:
                    cid = int(data.get("id"))
                except (TypeError, ValueError) as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                    return
                video_flow_provider_service.update_connection(cid, is_active=bool(data.get("is_active", True)))
                self.send_json_response({"success": True})
            elif path == "/api/video-flow/providers/connections/delete":
                try:
                    cid = int(data.get("id"))
                except (TypeError, ValueError) as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                    return
                ok = video_flow_provider_service.delete_connection(cid)
                self.send_json_response({"success": ok})
            elif path == "/api/video-flow/providers/connections/test":
                if str(data.get("id") or "") == "custom":
                    cprov = str(data.get("provider") or "").strip().lower()
                    entry = next((cp for cp in storage.get_video_flow_custom_providers()
                                  if cp.get("id") == cprov), None)
                    if entry is None:
                        self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                        return
                    res = self._probe_custom_endpoint_direct(
                        base_url=str(entry.get("base_url") or ""),
                        api_key=str(entry.get("api_key") or ""),
                        api_format=str(entry.get("api_format") or "openai").lower(),
                        model_id=((entry.get("models") or [{}])[0].get("model_id") or "test"),
                        kind="llm",
                        headers=entry.get("headers"),
                    )
                    if res.get("success"):
                        self.send_json_response({"success": True, "status": "active"})
                    else:
                        _msg = str(res.get("error") or "Test failed")
                        if "401" in _msg:
                            _msg = "Invalid API key (rejected by the provider). Paste the key exactly as shown in the provider dashboard."
                        self.send_json_response({"success": False, "status": "error", "error": _msg[:220]})
                    return
                try:
                    cid = int(data.get("id"))
                except (TypeError, ValueError) as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                    return
                try:
                    result = video_flow_provider_service.test_connection(cid)
                    if not isinstance(result, dict):
                        result = {"success": bool(result)}
                    if "success" not in result:
                        result = {"success": True, **result}
                    self.send_json_response(result)
                except ValueError as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)})
        elif path == "/api/video-flow/providers/connections/reorder":
            provider_str = str(data.get("provider") or "").strip().lower()
            order = [str(cid) for cid in (data.get("connection_ids") or [])]
            if provider_str.startswith("custom-") or any(cid.startswith("c-") for cid in order):
                entry = None
                if provider_str:
                    entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == provider_str), None)
                if entry is None:
                    for cp in storage.get_video_flow_custom_providers():
                        c_ids = [str(c.get("id") or f"c-{i}") for i, c in enumerate(cp.get("api_keys") or [])]
                        if any(cid in c_ids for cid in order):
                            entry = cp
                            break
                if entry is None and len(storage.get_video_flow_custom_providers()) == 1:
                    entry = storage.get_video_flow_custom_providers()[0]
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                entry["api_keys"] = _reorder_conns(conns, order)
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            try:
                connection_ids = data.get("connection_ids") or []
                for idx, cid in enumerate(connection_ids):
                    video_flow_provider_service.update_connection(int(cid), priority=idx + 1)
                self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/settings":
            provider = str(data.get("provider") or "").lower()
            if not provider:
                self.send_json_response({"success": False, "error": "Provider is required."}, 400)
                return
            raw_mode = str(data.get("load_balance_mode") or "").strip().lower().replace("-", "_").replace(" ", "_")
            mode = "round_robin" if raw_mode == "round_robin" else "priority"
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == provider), None)
                if entry:
                    entry["load_balance_mode"] = mode
                    storage.add_video_flow_custom_provider(entry)
            video_flow_provider_service.set_setting(f"load_balance:{provider}", mode)
            self.send_json_response({"success": True, "load_balance_mode": mode})


        elif path == "/api/video-flow/oauth/start":
            provider = str(data.get("provider") or "").strip().lower()
            if not provider:
                self.send_json_response({"success": False, "error": "provider is required."}, 400)
                return
            try:
                result = video_flow_provider_service.start_oauth(provider, port=self._server_port())
                flow = result.get("flow", "cli") if isinstance(result, dict) else "cli"
                self.send_json_response({"success": True, "flow": flow, **(result if isinstance(result, dict) else {})})
            except (ValueError, RuntimeError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/oauth/device-poll":
            provider = str(data.get("provider") or "").strip().lower()
            device_auth_id = str(data.get("device_auth_id") or "").strip()
            user_code = str(data.get("user_code") or "").strip()
            if not provider:
                self.send_json_response({"success": False, "error": "provider is required."}, 400)
                return
            try:
                result = video_flow_provider_service.poll_device_flow(
                    provider,
                    device_auth_id=device_auth_id,
                    user_code=user_code,
                )
                is_err = isinstance(result, dict) and result.get("status") == "error"
                self.send_json_response({"success": not is_err, **(result if isinstance(result, dict) else {})})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path in ("/api/video-flow/oauth/exchange", "/api/video-flow/oauth/complete"):
            state_probe = str(data.get("state") or "").strip()
            provider = str(data.get("provider") or "").strip().lower()
            if not provider:
                provider = str(video_flow_provider_service.get_setting(f"oauth_pending_state:{state_probe}", "") or "").strip().lower()
            code = str(data.get("code") or "").strip()
            state = str(data.get("state") or "").strip()
            redirect_uri = str(data.get("redirect_uri") or "").strip()
            if not code or not state:
                self.send_json_response({"success": False, "error": "Missing authorization code or state."}, 400)
                return

            if not provider:
                for p in ("antigravity", "gemini", "openai_codex", "claude_code"):
                    pending = load_pending(video_flow_provider_service, p)
                    if isinstance(pending, dict) and pending.get("state") == state:
                        provider = p
                        break
            if not provider:
                provider = "antigravity"

            # Check if this connection was already registered by proactive server-side GET /callback
            active_conns = [c for c in video_flow_provider_service.list_connections(provider) if c.get("is_active")]
            if active_conns:
                latest = active_conns[-1]
                _focus_app_window()
                self.send_json_response({"success": True, "email": latest.get("account_id") or "", "connection": latest})
                return

            try:
                res = _complete_video_flow_oauth(
                    video_flow_provider_service,
                    provider,
                    code,
                    state=state,
                    redirect_uri=redirect_uri or f"http://127.0.0.1:{PORT}/callback",
                )
                _focus_app_window()
                self.send_json_response({"success": True, **res})
            except (OAuthError, ValueError, RuntimeError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/open-browser":
            auth_url = str(data.get("auth_url") or "").strip()
            if not auth_url.startswith("http"):
                self.send_json_response({"success": False, "error": "auth_url required"}, 400)
            else:
                from voice_flow.video_flow_oauth import launch_system_browser
                opened = launch_system_browser(auth_url)
                self.send_json_response({"success": True, "opened": bool(opened)})

        elif path in ("/api/video-flow/custom-providers/add", "/api/videoflow/custom-providers/add"):
            name = str(data.get("name") or "").strip()
            base_url = str(data.get("base_url") or "").strip()
            api_key = str(data.get("api_key") or "").strip()
            models = data.get("models") or []
            api_format = str(data.get("api_format") or "openai")
            pid = str(data.get("id") or f"custom-{name.lower().replace(' ', '-')}")
            entry = {
                "id": pid,
                "name": name,
                "base_url": base_url,
                "api_key": api_key,
                "api_format": api_format,
                "models": models,
            }
            if "headers" in data:
                headers = data["headers"]
                if isinstance(headers, str):
                    try:
                        headers = json.loads(headers)
                    except Exception:
                        self.send_json_response({"success": False, "error": "headers must be a JSON object."}, 400)
                        return
                if headers is not None and not isinstance(headers, dict):
                    self.send_json_response({"success": False, "error": "headers must be a JSON object."}, 400)
                    return
                if isinstance(headers, dict):
                    for hk, hv in headers.items():
                        if not isinstance(hk, str) or not isinstance(hv, str):
                            self.send_json_response({"success": False, "error": "headers must map strings to strings."}, 400)
                            return
                        if re.search(r"authorization|proxy-authorization|cookie", hk, re.IGNORECASE):
                            self.send_json_response({"success": False, "error": "headers must not carry credentials."}, 400)
                            return
                    entry["headers"] = headers
            try:
                providers = storage.add_video_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/video-flow/custom-providers/update", "/api/videoflow/custom-providers/update"):
            pid = str(data.get("id") or "").strip()
            if not pid:
                self.send_json_response({"success": False, "error": "Custom provider 'id' is required for update."}, 400)
                return
            if "headers" in data and data["headers"] is not None:
                headers = data["headers"]
                if isinstance(headers, str):
                    try:
                        headers = json.loads(headers)
                    except Exception:
                        self.send_json_response({"success": False, "error": "headers must be a JSON object."}, 400)
                        return
                    data = dict(data)
                    data["headers"] = headers
                if not isinstance(data.get("headers"), dict):
                    self.send_json_response({"success": False, "error": "headers must be a JSON object."}, 400)
                    return
                for hk, hv in data["headers"].items():
                    if not isinstance(hk, str) or not isinstance(hv, str):
                        self.send_json_response({"success": False, "error": "headers must map strings to strings."}, 400)
                        return
                    if re.search(r"authorization|proxy-authorization|cookie", hk, re.IGNORECASE):
                        self.send_json_response({"success": False, "error": "headers must not carry credentials."}, 400)
                        return
            try:
                providers = storage.update_video_flow_custom_provider(data)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/video-flow/custom-providers/delete", "/api/videoflow/custom-providers/delete"):
            pid = str(data.get("id") or "").strip()
            providers = storage.delete_video_flow_custom_provider(pid)
            self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})

        elif path in ("/api/video-flow/custom-providers/test", "/api/videoflow/custom-providers/test"):
            self._handle_custom_provider_test(data, flow="video")

        elif path in ("/api/voice-flow/custom-providers/add", "/api/voiceflow/custom-providers/add", "/api/providers/custom/add"):
            name = str(data.get("name") or "").strip()
            base_url = str(data.get("base_url") or "").strip()
            api_key = str(data.get("api_key") or "").strip()
            models = data.get("models") or []
            api_format = str(data.get("api_format") or "openai")
            pid = str(data.get("id") or f"custom-{name.lower().replace(' ', '-')}")
            entry = {
                "id": pid,
                "name": name,
                "base_url": base_url,
                "api_key": api_key,
                "api_format": api_format,
                "models": models,
            }
            if "headers" in data:
                entry["headers"] = data["headers"]
            try:
                providers = storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/voice-flow/custom-providers/update", "/api/voiceflow/custom-providers/update", "/api/providers/custom/update"):
            pid = str(data.get("id") or "").strip()
            if not pid:
                self.send_json_response({"success": False, "error": "Custom provider 'id' is required for update."}, 400)
                return
            try:
                providers = storage.update_voice_flow_custom_provider(data)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/voice-flow/custom-providers/delete", "/api/voiceflow/custom-providers/delete", "/api/providers/custom/delete"):
            pid = str(data.get("id") or "").strip()
            providers = storage.delete_voice_flow_custom_provider(pid)
            self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})

        elif path in ("/api/voice-flow/custom-providers/test", "/api/voiceflow/custom-providers/test", "/api/providers/custom/test"):
            self._handle_custom_provider_test(data, flow="voice")

        elif path in ("/api/audio-flow/custom-providers/add", "/api/audioflow/custom-providers/add", "/api/audio-providers/custom/add"):
            name = str(data.get("name") or "").strip()
            base_url = str(data.get("base_url") or "").strip()
            api_key = str(data.get("api_key") or "").strip()
            models = data.get("models") or []
            api_format = str(data.get("api_format") or "openai")
            pid = str(data.get("id") or f"custom-{name.lower().replace(' ', '-')}")
            entry = {
                "id": pid,
                "name": name,
                "base_url": base_url,
                "api_key": api_key,
                "api_format": api_format,
                "models": models,
            }
            if "headers" in data:
                entry["headers"] = data["headers"]
            try:
                providers = storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/audio-flow/custom-providers/update", "/api/audioflow/custom-providers/update", "/api/audio-providers/custom/update"):
            pid = str(data.get("id") or "").strip()
            if not pid:
                self.send_json_response({"success": False, "error": "Custom provider 'id' is required for update."}, 400)
                return
            try:
                providers = storage.update_audio_flow_custom_provider(data)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers, reveal_headers=True)})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/audio-flow/custom-providers/delete", "/api/audioflow/custom-providers/delete", "/api/audio-providers/custom/delete"):
            pid = str(data.get("id") or "").strip()
            providers = storage.delete_audio_flow_custom_provider(pid)
            self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})

        elif path in ("/api/audio-flow/custom-providers/test", "/api/audioflow/custom-providers/test", "/api/audio-providers/custom/test"):
            self._handle_custom_provider_test(data, flow="audio")

        elif path == "/api/settings/theme":
            theme = str(data.get("theme", "") or "").strip().lower()
            if theme not in ("light", "dark"):
                self.send_json_response({"success": False, "error": "Theme must be light or dark"}, 400)
            else:
                storage.save_setting("vf_theme", theme)
                self.send_json_response({"success": True, "theme": theme})

        elif path == "/api/voice-flow-stt/update":
            model_id = str(data.get("model_id") or data.get("model") or data.get("model_ref") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id required"}, 400)
            else:
                stt_provider = model_id.split("/", 1)[0].strip().lower()
                if stt_provider != "local" and stt_provider not in STT_CAPABLE_PROVIDERS:
                    self.send_json_response({"success": False, "error": f"Provider '{stt_provider}' does not support speech-to-text."}, 400)
                else:
                    if stt_provider != "local":
                        model_name = model_id.split("/", 1)[1] if "/" in model_id else ""
                        model_state = storage.get_provider_model_active(stt_provider, model_name)
                        if model_state is False:
                            self.send_json_response({"success": False, "error": "This speech model is disabled."}, 400)
                            return
                    try:
                        from voice_flow import downloadable_models
                        spec = downloadable_models.get_model_spec(model_id)
                        if spec:
                            target_file = downloadable_models.get_models_dir() / spec["filename"]
                            if not target_file.is_file() or target_file.stat().st_size == 0:
                                self.send_json_response({"success": False, "error": "Model must be downloaded before selecting it"}, 400)
                                return
                    except Exception:
                        pass
                    storage.save_setting("voice_flow_stt_model", model_id)
                    # Verify the save succeeded by reading back
                    verified = storage.get_setting("voice_flow_stt_model", "")
                    print(f"[STT MODEL] User changed STT model to '{model_id}' via API (verified in storage: '{verified}')")
                    try:
                        from voice_flow import nemotron_engine
                        if nemotron_engine.is_nemotron_model(model_id):
                            threading.Thread(target=nemotron_engine.get_nemotron_engine, args=(model_id,), daemon=True).start()
                    except Exception:
                        pass
                    # Pre-warm cloud TLS connection when switching to a cloud model
                    if stt_provider != "local" and stt_provider in STT_CAPABLE_PROVIDERS:
                        try:
                            from voice_flow import stt_engines
                            stt_engines.prewarm_cloud_stt(model_id, force=True)
                        except Exception:
                            pass
                    # Clear any circuit-breaker state and failover counters for the
                    # newly selected model so the user gets a clean start
                    try:
                        app = getattr(self.server, "_voice_flow_app", None)
                        if app is not None:
                            transcriber = getattr(app, "transcriber", None)
                            if transcriber is not None:
                                breakers = getattr(transcriber, "_cloud_stt_breakers", None)
                                if isinstance(breakers, dict) and model_id in breakers:
                                    breakers[model_id] = (0, 0.0)
                                    print(f"[STT MODEL] Cleared circuit breaker for '{model_id}'")
                                # Reset failover tracking on explicit model switch
                                transcriber._last_failover_info = None
                                transcriber._failover_count = 0
                    except Exception:
                        pass
                    self.send_json_response({"success": True, "active_model": model_id})

        elif path == "/api/downloadable-models/download":
            model_id = str(data.get("model_id") or data.get("id") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id required"}, 400)
            else:
                try:
                    from voice_flow import downloadable_models
                    ok, msg, mstatus = downloadable_models.start_model_download(model_id)
                    if ok:
                        self.send_json_response({"success": True, "message": msg, "model": mstatus})
                    else:
                        self.send_json_response({"success": False, "error": msg}, 400)
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/downloadable-models/cancel":
            model_id = str(data.get("model_id") or data.get("id") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id required"}, 400)
            else:
                try:
                    from voice_flow import downloadable_models
                    ok, msg = downloadable_models.cancel_model_download(model_id)
                    self.send_json_response({"success": ok, "message": msg})
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/downloadable-models/delete":
            model_id = str(data.get("model_id") or data.get("id") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id required"}, 400)
            else:
                try:
                    from voice_flow import downloadable_models
                    ok, msg = downloadable_models.delete_downloaded_model(model_id)
                    if ok:
                        self.send_json_response({"success": True, "message": msg})
                    else:
                        self.send_json_response({"success": False, "error": msg}, 400)
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/downloadable-models/select":
            model_id = str(data.get("model_id") or data.get("id") or "").strip()
            if not model_id:
                self.send_json_response({"success": False, "error": "model_id required"}, 400)
            else:
                try:
                    from voice_flow import downloadable_models
                    spec = downloadable_models.get_model_spec(model_id)
                    if not spec:
                        self.send_json_response({"success": False, "error": "Model not found in downloadable catalog"}, 404)
                    else:
                        target_file = downloadable_models.get_models_dir() / spec["filename"]
                        if not target_file.is_file() or target_file.stat().st_size == 0:
                            self.send_json_response({"success": False, "error": "Model must be downloaded before selecting it"}, 400)
                        else:
                            is_polish = spec.get("category") == "voice_polishing" or "polish" in str(spec.get("tag") or "").lower()
                            if is_polish:
                                storage.save_setting("voice_flow_polish_model", spec["full_id"])
                                self.send_json_response({"success": True, "active_model": spec["full_id"], "target": "voice_flow_polish"})
                            else:
                                storage.save_setting("voice_flow_stt_model", spec["full_id"])
                                try:
                                    from voice_flow import nemotron_engine
                                    threading.Thread(target=nemotron_engine.get_nemotron_engine, args=(spec["full_id"],), daemon=True).start()
                                except Exception:
                                    pass
                                self.send_json_response({"success": True, "active_model": spec["full_id"], "target": "voice_flow_stt"})
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/history/pin":
            record_id = data.get("id")
            if not record_id:
                self.send_json_response({"success": False, "error": "Missing record id"}, 400)
            else:
                try:
                    rec_id_int = int(record_id)
                    res = storage.toggle_history_pin(rec_id_int)
                    invalidate_history_cache()
                    self.send_json_response(res)
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/history/delete":
            record_id = data.get("id")
            if not record_id:
                self.send_json_response({"success": False, "error": "Missing record id"}, 400)
            else:
                try:
                    rec_id_int = int(record_id)
                    res = storage.delete_history_record(rec_id_int)
                    if res:
                        invalidate_history_cache()
                        self.send_json_response({"success": True, "id": rec_id_int})
                    else:
                        self.send_json_response({"success": False, "error": "Record not found"}, 404)
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/audio-flow/history/play":
            item_id = str(data.get("id") or "").strip()
            if not item_id:
                self.send_json_response({"success": False, "error": "Missing audio summary id"}, 400)
            else:
                try:
                    hist = storage.get_audio_summary_history_by_id(item_id)
                    from voice_flow.audio_summary_player import (
                        launch_summary_audio_player,
                        resolve_summary_audio,
                    )
                    resolved = resolve_summary_audio(item_id)
                    audio_path = resolved[0] if resolved else (hist.get("audio_path") if hist else None)
                    if not audio_path or not Path(audio_path).is_file():
                        media_dir = (data_dir() / "audio_summaries").resolve()
                        cand_files = sorted(
                            list(media_dir.glob("*.m4a")) + list(media_dir.glob("*.mp3")),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        if cand_files:
                            audio_path = cand_files[0]
                    if not audio_path or not Path(audio_path).is_file():
                        self.send_json_response({"success": False, "error": "Audio summary file not found on disk"}, 404)
                    else:
                        depth = str(data.get("depth") or (hist.get("depth") if hist else "balanced") or "balanced")
                        title = str(data.get("title") or (hist.get("title") if hist else "Audio Summary") or "Audio Summary")
                        base_url = f"http://127.0.0.1:{self._server_port()}"
                        token = launch_summary_audio_player(
                            audio_path,
                            depth=depth,
                            title=title,
                            base_url=base_url,
                            token=item_id,
                        )
                        self.send_json_response({
                            "success": True,
                            "token": token,
                            "mode": "native_window",
                            "player_url": f"{base_url}/audio-summary-player.html?id={urllib.parse.quote(token)}&depth={urllib.parse.quote(depth)}&title={urllib.parse.quote(title)}",
                        })
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/audio-flow/history/delete":
            summary_id = str(data.get("id") or "").strip()
            if not summary_id:
                self.send_json_response({"success": False, "error": "Missing summary id"}, 400)
            else:
                try:
                    res = storage.delete_audio_summary_history(summary_id)
                    self.send_json_response({"success": bool(res), "id": summary_id})
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/history/clear":
            try:
                if hasattr(storage, "clear_history"):
                    storage.clear_history()
                elif hasattr(storage, "_get_conn"):
                    with storage._get_conn() as conn:
                        conn.execute("DELETE FROM history")
                        conn.commit()
                invalidate_history_cache()
                self.send_json_response({"success": True})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/dictionary/suggestions/decide":
            try:
                cid = int(data.get("id"))
            except (TypeError, ValueError):
                self.send_json_response({"success": False, "error": "Invalid suggestion id"}, 400)
                return
            state = str(data.get("state") or "").strip().lower()
            if state not in ("active", "ignored"):
                self.send_json_response({"success": False, "error": "state must be active or ignored"}, 400)
                return
            ok = storage.set_lexicon_candidate_state(cid, state)
            self.send_json_response({"success": bool(ok)})

        elif path == "/api/dictionary/add":
            word_value = data.get("word") or data.get("text") or ""
            if not isinstance(word_value, str) or not word_value.strip():
                self.send_json_response({"success": False, "error": "Dictionary word must be a non-empty string."}, 400)
            else:
                success = storage.add_dictionary_word(word_value)
                if not success:
                    self.send_json_response({"success": False, "error": "Word already exists or invalid."}, 400)
                else:
                    dictionary_engine.mark_dirty()
                    self.send_json_response({"success": True, "words": storage.get_dictionary_words(include_auto=True, include_snippets=True)})

        elif path == "/api/dictionary/update":

            old_word = data.get("old_word") or data.get("old") or ""

            new_word = data.get("new_word") or data.get("new") or data.get("word") or ""

            if not str(old_word).strip() or not str(new_word).strip():

                self.send_json_response({"success": False, "error": "Both the current and the new term are required."}, 400)

            else:

                success = storage.update_dictionary_word(str(old_word), str(new_word))

                if not success:

                    self.send_json_response({"success": False, "error": "Dictionary entry was not found or the new term is invalid."}, 404)

                else:

                    dictionary_engine.mark_dirty()

                    self.send_json_response({"success": True, "words": storage.get_dictionary_words(include_auto=True, include_snippets=True)})



        elif path in ("/api/dictionary/remove", "/api/dictionary/delete"):
            word = data.get("word") or data.get("text") or data.get("id")
            if word is None or (isinstance(word, str) and not word.strip()):
                self.send_json_response({"success": False, "error": "Dictionary entry required."}, 400)
            else:
                success = storage.remove_dictionary_word(str(word))
                if not success:
                    self.send_json_response({"success": False, "error": "Dictionary entry was not found."}, 404)
                else:
                    dictionary_engine.mark_dirty()
                    self.send_json_response({"success": True, "words": storage.get_dictionary_words(include_auto=True, include_snippets=True)})

        elif path == "/api/dictionary/corrections/add":
            wrong = str(data.get("wrong_text") or "").strip()
            correct = str(data.get("correct_text") or "").strip()
            if not wrong or not correct:
                self.send_json_response({"success": False, "error": "wrong_text and correct_text are required."}, 400)
            else:
                try:
                    c = storage.add_dictionary_correction(wrong, correct)
                    dictionary_engine.mark_dirty()
                    self.send_json_response({"success": True, "correction": c}, 201)
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 400)

        elif path == "/api/dictionary/corrections/update":
            cid = data.get("id")
            wrong = str(data.get("wrong_text") or "").strip()
            correct = str(data.get("correct_text") or "").strip()
            if not cid or not wrong or not correct:
                self.send_json_response({"success": False, "error": "id, wrong_text, and correct_text are required."}, 400)
            else:
                try:
                    c = storage.update_dictionary_correction(int(cid), wrong, correct)
                    dictionary_engine.mark_dirty()
                    self.send_json_response({"success": True, "correction": c})
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 400)

        elif path in ("/api/dictionary/corrections/remove", "/api/dictionary/corrections/delete"):
            cid = data.get("id")
            if not cid:
                self.send_json_response({"success": False, "error": "Correction id required."}, 400)
            else:
                try:
                    success = storage.remove_dictionary_correction(int(cid))
                    if success:
                        dictionary_engine.mark_dirty()
                        self.send_json_response({"success": True})
                    else:
                        self.send_json_response({"success": False, "error": "Correction not found."}, 404)
                except Exception as e:
                    self.send_json_response({"success": False, "error": str(e)}, 400)

        elif path == "/api/record/toggle":
            try:
                # Frontend sends { recording: bool } (app.js toggleHandsFreeRecording).
                value = data.get("recording", data.get("value", data.get("enabled")))
                if value is None:
                    self.send_json_response({"success": False, "error": "Missing 'recording' boolean."}, 400)
                else:
                    value = bool(value)
                    storage.save_setting("recording", value)
                    self.send_json_response({"success": True, "recording": value})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/apikeys/test":
            try:
                provider = str(data.get("provider") or "gemini").lower()
                key = str(data.get("key") or "").strip()
                # Live verification only; nothing is persisted.
                v_res = self.verify_api_key(provider, key)
                self.send_json_response(v_res)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/styles/update":
            try:
                # Frontend sends { category, style_id } (app.js selectStyleCard);
                # GET /api/styles/get reads the same style_<category> settings.
                category = str(data.get("category") or "").strip().lower()
                style_id = str(data.get("style_id") or data.get("style") or "").strip()
                valid_categories = ("personal", "work", "email", "developer", "other", "autocleanup")
                if not style_id:
                    self.send_json_response({"success": False, "error": "style_id is required."}, 400)
                elif category not in valid_categories:
                    self.send_json_response({"success": False, "error": f"Unknown style category '{category}'."}, 400)
                else:
                    # The page sends full card ids, but older callers may
                    # send a canonical suffix ("casual"). Persist one valid
                    # category-owned card id so it resolves identically after
                    # a restart and cannot silently select another category.
                    if category == "autocleanup" and not style_id.startswith("cleanup_"):
                        style_id = f"cleanup_{style_id}"
                    elif category != "autocleanup" and not style_id.startswith(f"{category}_"):
                        style_id = f"{category}_{style_id}"
                    preset = STYLE_PRESETS.get(style_id)
                    if preset is None or preset.category != category:
                        self.send_json_response({"success": False, "error": f"Unknown style '{style_id}' for {category}."}, 400)
                        return
                    storage.save_setting(f"style_{category}", style_id)
                    self.send_json_response({"success": True, "category": category, "style_id": style_id})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/microphones/select":
            try:
                # Frontend sends { name, index } (app.js selectMicrophoneDevice).
                name = str(data.get("name") or data.get("device_id") or "").strip()
                index = data.get("index", data.get("device_index"))
                if (not name) and (index is None):
                    self.send_json_response({"success": False, "error": "Microphone name or index required."}, 400)
                else:
                    storage.save_setting("selected_microphone", name or index)
                    if index is not None:
                        storage.save_setting("n_device", index)
                    # The recorder engine restores its device from
                    # "selected_mic_device" (main.py -> config -> audio.start).
                    # Write the same pick there — prefer the device name (it
                    # survives re-enumeration; an index does not), fall back
                    # to the index when the frontend sent no name.
                    storage.save_setting("selected_mic_device", name or index)
                    # Apply live: dictation started right now must use the
                    # newly picked device, not wait for a restart.
                    try:
                        from voice_flow.config import config as _cfg
                        _cfg.selected_mic_device = name or index
                    except Exception:
                        pass
                    self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/providers/connections/reorder":
            provider = str(data.get("provider") or "").strip().lower()
            connection_ids = data.get("connection_ids") or []
            order = [str(cid) for cid in connection_ids]
            if provider.startswith("custom-") or any(cid.startswith("c-") for cid in order):
                entry = None
                if provider:
                    entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    for cp in storage.get_voice_flow_custom_providers():
                        c_ids = [str(c.get("id") or f"c-{i}") for i, c in enumerate(cp.get("api_keys") or [])]
                        if any(cid in c_ids for cid in order):
                            entry = cp
                            break
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                entry["api_keys"] = _reorder_conns(conns, order)
                providers = storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            try:
                # Priority-only rewrite; names/keys are never touched here.
                conn = sqlite3.connect(storage.db_path)
                try:
                    for idx, cid in enumerate(connection_ids):
                        conn.execute("UPDATE provider_connections SET priority = ? WHERE id = ?", (idx + 1, int(cid)))
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True})
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/providers/models/enable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = True
                storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                conn = sqlite3.connect(storage.db_path)
                try:
                    cursor = conn.execute("UPDATE provider_models SET is_active = 1 WHERE provider = ?", (provider,))
                    count = cursor.rowcount
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True, "count": count})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/providers/models/disable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = False
                storage.add_voice_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                conn = sqlite3.connect(storage.db_path)
                try:
                    cursor = conn.execute("UPDATE provider_models SET is_active = 0 WHERE provider = ?", (provider,))
                    count = cursor.rowcount
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True, "count": count})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-policy/update":
            try:
                model_id = str(data.get("model_id") or data.get("model") or data.get("model_ref") or "").strip()
                if not model_id:
                    self.send_json_response({"success": False, "error": "model_id is required."}, 400)
                else:
                    provider, sep, voice_id = model_id.partition("/")
                    provider = provider.strip().lower() if sep else "edge"
                    voice_id = voice_id.strip() if sep else model_id
                    selectable = True
                    if provider.startswith("custom-"):
                        entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                        selectable = bool(entry and entry.get("is_active", True) and any(
                            str(m.get("model_id") or "") == voice_id and m.get("is_active", True)
                            for m in (entry.get("models") or [])
                        ))
                    else:
                        state = storage.get_tts_model_active(provider, voice_id)
                        selectable = state is not False and (state is not None or provider in {"edge", "offline", "sapi", "sapi5", "windows"})
                    if not selectable:
                        self.send_json_response({"success": False, "error": "This voice is disabled or no longer available."}, 400)
                        return
                    # Key read back as "active_model" by GET /api/audio-policy/get.
                    storage.save_setting("exec_audio_policy_model", model_id)
                    self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-policy/toggle":
            try:
                # Frontend sends { enabled: bool } (app.js toggleAudioFlowSetting).
                enabled = bool(data.get("enabled", data.get("value", data.get("is_active", True))))
                # Key read back as "audio_flow_enabled" by GET /api/audio-policy/get.
                storage.save_setting("audio_flow_enabled", enabled)
                self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-policy/speed":
            try:
                speed = float(data.get("speed"))
                # Key read back as "audio_flow_speed" by GET /api/audio-policy/get.
                storage.save_setting("audio_flow_speed", speed)
                self.send_json_response({"success": True})
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-providers/connections/reorder":
            provider = str(data.get("provider") or "").strip().lower()
            connection_ids = data.get("connection_ids") or []
            order = [str(cid) for cid in connection_ids]
            if provider.startswith("custom-") or any(cid.startswith("c-") for cid in order):
                entry = None
                if provider:
                    entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    for cp in storage.get_audio_flow_custom_providers():
                        c_ids = [str(c.get("id") or f"c-{i}") for i, c in enumerate(cp.get("api_keys") or [])]
                        if any(cid in c_ids for cid in order):
                            entry = cp
                            break
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                conns = entry.get("api_keys") or []
                entry["api_keys"] = _reorder_conns(conns, order)
                providers = storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "providers": _public_custom_providers(providers)})
                return
            try:
                # Priority-only rewrite on the audio connections table.
                conn = sqlite3.connect(storage.db_path)
                try:
                    for idx, cid in enumerate(connection_ids):
                        conn.execute("UPDATE audio_provider_connections SET priority = ? WHERE id = ?", (idx + 1, int(cid)))
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True})
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-providers/models/enable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = True
                storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                conn = sqlite3.connect(storage.db_path)
                try:
                    cursor = conn.execute("UPDATE tts_models SET is_active = 1 WHERE provider = ?", (provider,))
                    count = cursor.rowcount
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True, "count": count})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-providers/models/disable-all":
            provider = str(data.get("provider") or "").lower()
            if provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry is None:
                    self.send_json_response({"success": False, "error": "Custom provider not found."}, 404)
                    return
                for m in entry.get("models") or []:
                    m["is_active"] = False
                storage.add_audio_flow_custom_provider(entry)
                self.send_json_response({"success": True, "count": len(entry.get("models") or [])})
                return
            try:
                conn = sqlite3.connect(storage.db_path)
                try:
                    cursor = conn.execute("UPDATE tts_models SET is_active = 0 WHERE provider = ?", (provider,))
                    count = cursor.rowcount
                    conn.commit()
                finally:
                    conn.close()
                self.send_json_response({"success": True, "count": count})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/providers/master/toggle":
            provider_id = str(data.get("provider_id") or data.get("provider") or "").strip().lower()
            is_active = bool(data.get("is_active", data.get("value", True)))
            if not provider_id:
                self.send_json_response({"success": False, "error": "provider_id required"}, 400)
                return
            try:
                storage.toggle_provider_master(provider_id, is_active)
                self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/audio-providers/master/toggle":
            try:
                # Frontend sends { provider_id, is_active } (app.js toggleAudioProviderMaster).
                provider = str(data.get("provider_id") or data.get("provider") or "").strip().lower()
                if not provider:
                    self.send_json_response({"success": False, "error": "provider_id is required."}, 400)
                else:
                    active = bool(data.get("is_active", data.get("value", True)))
                    # Flips every audio_provider_connections row and tts_models row for the provider.
                    storage.toggle_audio_provider_master(provider, active)
                    self.send_json_response({"success": True})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/analyze-source":
            try:
                raw_text = data.get("source_text", "")
                if raw_text is None:
                    raw_text = ""
                if not isinstance(raw_text, str):
                    self.send_json_response({"success": False, "error": "source_text must be a string."}, 400)
                    return
                source_text = raw_text
                requested_format = data.get("requested_format") or data.get("format")
                if requested_format is not None and not isinstance(requested_format, str):
                    self.send_json_response({"success": False, "error": "requested_format must be a string."}, 400)
                    return
                clean_format = str(requested_format or "").strip().lower()
                if clean_format not in ("", "auto", "auto-adaptive", "default", "recommended",
                                        "brief", "short", "explainer", "cinematic"):
                    self.send_json_response({"success": False, "error": "Unknown format. Use auto, brief, short, explainer, or cinematic."}, 400)
                    return
                task = data.get("task") or data.get("focus") or data.get("visual_direction")
                title = data.get("title")
                mode = data.get("mode")
                for key in ("task", "title", "mode", "focus", "visual_direction"):
                    if data.get(key) is not None and not isinstance(data.get(key), str):
                        self.send_json_response({"success": False, "error": f"{key} must be a string."}, 400)
                        return
                source_path = data.get("source_path") or data.get("source_file")
                if source_path is not None:
                    if not isinstance(source_path, str):
                        self.send_json_response({"success": False, "error": "source_path must be a string."}, 400)
                        return
                    if "\x00" in source_path or ".." in source_path.replace("\\", "/").split("/"):
                        self.send_json_response({"success": False, "error": "Invalid source_path."}, 400)
                        return
                # Same analyzer the /api/video-flow/generate pre-step uses
                from voice_flow.video_flow_engine.notebooklm import analyze_document_source, compute_format_duration
                profile = analyze_document_source(
                    text=source_text,
                    source_path=source_path,
                    requested_format=requested_format,
                    task=task,
                    title=title,
                    mode=mode,
                    focus=data.get("focus"),
                    visual_direction=data.get("visual_direction"),
                )
                # Single source of truth: word counts and section/density signals
                # come from the profiler, never from ad-hoc local recounts.
                words = profile.word_count
                num_sec = profile.section_count
                density_s = getattr(profile, "density_score", 1.0)
                concept_c = getattr(profile, "concept_count", 0)
                effective_wc = getattr(profile, "effective_word_count", 0) or None
                redundancy_s = getattr(profile, "redundancy_score", 0.0)
                brief_seconds, _ = compute_format_duration(words, "brief", num_sections=num_sec, density_score=density_s, concept_count=concept_c, effective_word_count=effective_wc, redundancy_score=redundancy_s)
                short_seconds, _ = compute_format_duration(words, "short", num_sections=num_sec, density_score=density_s, concept_count=concept_c, effective_word_count=effective_wc, redundancy_score=redundancy_s)
                explainer_seconds, _ = compute_format_duration(words, "explainer", num_sections=num_sec, density_score=density_s, concept_count=concept_c, effective_word_count=effective_wc, redundancy_score=redundancy_s)
                cinematic_seconds, _ = compute_format_duration(words, "cinematic", num_sections=num_sec, density_score=density_s, concept_count=concept_c, effective_word_count=effective_wc, redundancy_score=redundancy_s)
                page_count = max(1, int(round(profile.estimated_pages))) if profile.word_count > 0 else 0
                self.send_json_response({
                    "success": True,
                    "word_count": profile.word_count,
                    "char_count": profile.char_count,
                    "page_count": page_count,
                    "section_count": profile.section_count,
                    "sections": list(profile.sections),
                    "target_seconds": profile.target_duration_seconds,
                    "target_formatted": profile.target_duration_display,
                    "brief_seconds": brief_seconds,
                    "short_seconds": short_seconds,
                    "explainer_seconds": explainer_seconds,
                    "cinematic_seconds": cinematic_seconds,
                    "resolved_format": profile.recommended_format,
                    "content_type": profile.content_type,
                    "detected_intent": profile.detected_intent,
                    "density_score": profile.density_score,
                    "content_value_rating": profile.content_value_rating,
                    "concept_count": profile.concept_count,
                    "effective_word_count": profile.effective_word_count,
                    "redundancy_score": profile.redundancy_score,
                    "substantive_concepts": list(profile.substantive_concepts),
                    "truncated": bool(getattr(profile, "truncated", False)),
                    "analysis_char_count": int(getattr(profile, "analysis_char_count", 0) or 0),
                })
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/documents/extract":
            try:
                # Frontend sends { file_name, content_base64 } (video-flow.js loadVideoSourceFile).
                raw_name = data.get("file_name") or data.get("name") or ""
                if raw_name is not None and not isinstance(raw_name, str):
                    self.send_json_response({"success": False, "error": "file_name must be a string."}, 400)
                    return
                file_name = str(raw_name or "").strip()
                if "\x00" in file_name or ".." in file_name.replace("\\", "/").split("/"):
                    self.send_json_response({"success": False, "error": "Invalid file_name."}, 400)
                    return
                encoded = str(data.get("content_base64") or data.get("content") or "").strip()
                if encoded:
                    # Same extractor the Video Flow composer relies on
                    # (module-top import from voice_flow.video_flow_documents).
                    text = extract_document_text(file_name, encoded)
                elif data.get("text") is not None:
                    if not isinstance(data.get("text"), str):
                        self.send_json_response({"success": False, "error": "text must be a string."}, 400)
                        return
                    text = str(data.get("text"))
                else:
                    self.send_json_response({"success": False, "error": "content_base64 or text is required."}, 400)
                    return
                self.send_json_response({"success": True, "text": text, "chars": len(text)})
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)

        elif path == "/api/video-flow/videos/retry":
            video_id = str(data.get("id") or data.get("video_id") or "").strip()
            if not video_id:
                self.send_json_response({"success": False, "error": "Video id required"}, 400)
            elif not SAFE_JOB_ID_REGEX.fullmatch(video_id):
                self.send_json_response({"success": False, "error": "Invalid video id."}, 400)
            else:
                try:
                    service = get_video_flow_service()
                    job = service.get(video_id)
                    if job is None:
                        self.send_json_response({"success": False, "error": "Video not found"}, 404)
                        return
                    if str(job.state or "").lower() not in ("complete", "completed", "ready", "failed", "cancelled", "canceled"):
                        self.send_json_response({"success": False, "error": "Video is still processing - cancel it before retrying."}, 409)
                        return
                    # Re-queue from the original request echo persisted in meta
                    # (video_flow_service.queue stores it for exactly this purpose).
                    meta = dict(job.meta or {})
                    kwargs = {}
                    for key in ("mode", "title", "source_name", "model_ref", "theme", "visual_direction",
                                "allow_external_ai", "allow_local_fallback", "voice", "duration_seconds",
                                "video_engine", "provider", "format", "style", "style_prompt", "language",
                                "focus", "source_url", "source_file", "profile", "notebook_id", "source_id", "task_id"):
                        if meta.get(key) is not None:
                            kwargs[key] = meta.get(key)
                    new_job = service.queue(str(meta.get("source_text") or ""), **kwargs)
                    self.send_json_response({"success": True, "job_id": new_job.job_id, "video": _shim_video(new_job)}, 202)
                except ValueError as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 400)
                except Exception as exc:
                    self.send_json_response({"success": False, "error": str(exc)}, 500)

        else:
            self.send_json_response({"success": False, "error": f"API endpoint '{path}' not found."}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        origin = self.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            self.send_json_response({"success": False, "error": "Origin not allowed"}, 403)
            return
        self.send_response(204)
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _stream_shim_video(self, video_id: str, *, download: bool = False, title: str | None = None) -> None:
        if not video_id or not SAFE_JOB_ID_REGEX.fullmatch(video_id):
            self.send_json_response({"success": False, "error": "Invalid video job id"}, 400); return
        job = get_video_flow_service().get(video_id)
        path = None
        if job is not None:
            path_str = (job.meta or {}).get("output_path")
            path = Path(path_str) if path_str else None
        if not path or not path.is_file():
            candidates = [
                data_dir() / "v3_projects" / video_id / "video.mp4",
                data_dir() / "v3_projects" / video_id / "narova" / "out" / "video.mp4",
                data_dir() / "v3_projects" / video_id / "narova" / "project" / "out" / "video.mp4",
                data_dir() / "v3_projects" / video_id / "out" / "video.mp4",
                data_dir() / "notebooklm" / "videos" / f"{video_id}.mp4",
                data_dir() / "notebooklm" / video_id / "video.mp4",
                data_dir() / "notebooklm_videos" / f"{video_id}.mp4",
            ]
            meta = (job.meta or {}) if job is not None else {}
            if meta.get("video_path"):
                candidates.append(Path(str(meta.get("video_path"))))
            if isinstance(meta.get("artifact"), dict) and meta["artifact"].get("output_path"):
                candidates.append(Path(str(meta["artifact"]["output_path"])))
            if isinstance(meta.get("provenance"), dict) and meta["provenance"].get("output_path"):
                candidates.append(Path(str(meta["provenance"]["output_path"])))
            for cand in candidates:
                if cand and cand.is_file():
                    path = cand
                    break
            if not path or not path.is_file():
                proj_dir = data_dir() / "v3_projects" / video_id
                if proj_dir.is_dir():
                    found = list(proj_dir.rglob("video.mp4")) or list(proj_dir.rglob("concat.mp4"))
                    if found:
                        path = found[0]
        try:
            data_root = data_dir().resolve()
            if path is not None:
                resolved = path.resolve()
                if data_root != resolved and data_root not in resolved.parents:
                    path = None
        except OSError:
            path = None
        if not path or not path.is_file():
            self.send_json_response({"success": False, "error": "Video is not ready"}, 404); return
        try:
            size = path.stat().st_size
        except OSError:
            self.send_json_response({"success": False, "error": "Video is not ready"}, 404); return

        if size <= 0:
            self.send_json_response({"success": False, "error": "Video is not ready"}, 404); return
        start, end, status = 0, size - 1, 200
        requested_range = self.headers.get("Range")
        if requested_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range.strip())
            if not match or not (match.group(1) or match.group(2)):
                self._send_range_not_satisfiable(size); return
            try:
                if not match.group(1):
                    suffix = int(match.group(2))
                    if suffix <= 0: raise ValueError
                    start = max(0, size - suffix)
                    end = size - 1
                else:
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else size - 1
            except ValueError:
                self._send_range_not_satisfiable(size); return
            if start >= size or start > end:
                self._send_range_not_satisfiable(size); return
            end = min(end, size - 1); status = 206
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("X-Content-Type-Options", "nosniff")
        if download:
            from voice_flow.audio_summary_player import safe_media_filename
            vid_title = (title or "").strip()
            if not vid_title and job is not None:
                meta = job.meta or {}
                vid_title = (meta.get("title") or meta.get("prompt") or "").strip()
            download_name = safe_media_filename(vid_title or f"video_{video_id}", default=f"video_{video_id}", ext=".mp4")
            quoted_name = urllib.parse.quote(download_name)
            ascii_name = re.sub(r"[^\x20-\x7E]", "_", download_name)
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted_name}')
        else:
            self.send_header("Content-Disposition", f'inline; filename="video_{video_id}.mp4"')
        if status == 206: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        origin = self.headers.get("Origin")
        if ALLOWED_ORIGINS is not None and origin in ALLOWED_ORIGINS: self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")
        self.end_headers()
        try:
            with path.open("rb") as handle:
                handle.seek(start); remaining = end - start + 1
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except OSError:
            return

    def _send_range_not_satisfiable(self, size: int) -> None:
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_custom_provider_test(self, data: dict[str, Any], flow: str = "voice") -> None:
        is_audio = (flow == "audio")
        # The edit modal sends `edit_id` (and deliberately blanks `api_key` to
        # mean "keep the stored key"). Reading only id/provider left `pid` empty,
        # so no entry was found and the probe ran with no credential at all.
        pid = str(data.get("id") or data.get("provider") or data.get("edit_id") or "").strip()
        entry = None
        if pid.startswith("custom-"):
            if is_audio:
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == pid), None)
            elif flow == "video":
                entry = next((cp for cp in storage.get_video_flow_custom_providers() if cp.get("id") == pid), None)
            else:
                entry = next((cp for cp in storage.get_voice_flow_custom_providers() if cp.get("id") == pid), None)
            if not entry:
                all_cps = (
                    storage.get_voice_flow_custom_providers()
                    + storage.get_audio_flow_custom_providers()
                    + storage.get_video_flow_custom_providers()
                )
                entry = next((cp for cp in all_cps if cp.get("id") == pid), None)

        base_url = str(data.get("base_url") or (entry.get("base_url") if entry else "") or "").strip()
        # Resolve a usable credential: explicit request key, else the entry's
        # first enabled api_keys[] entry, else the legacy top-level api_key.
        _entry_keys = (entry.get("api_keys") if entry else None) or []
        _first_enabled = ""
        for _k in _entry_keys:
            if isinstance(_k, dict) and _k.get("is_active", True) and str(_k.get("key") or "").strip():
                _first_enabled = str(_k.get("key")).strip()
                break
        api_key = str(
            data.get("api_key")
            or data.get("key")
            or _first_enabled
            or (entry.get("api_key") if entry else "")
            or ""
        ).strip()
        api_format = str(data.get("api_format") or (entry.get("api_format") if entry else "openai") or "openai").strip().lower()
        models = data.get("models") or (entry.get("models") if entry else [])
        model_id = str(data.get("model_id") or data.get("model") or "").strip()
        if not model_id and models:
            first_m = models[0]
            model_id = str(first_m.get("model_id") if isinstance(first_m, dict) else first_m)
        if not model_id:
            model_id = "default" if is_audio else "gpt-4o"
        raw_headers = data.get("headers") or (entry.get("headers") if entry else {})

        if not base_url:
            self.send_json_response({"success": False, "ok": False, "error": "Base URL is required to test provider."}, 400)
            return

        probe_kind = "tts" if is_audio else ("stt" if "stt" in str(data.get("kind") or "").lower() else "llm")
        _t0 = time.time()
        v_res = self._probe_custom_endpoint_direct(base_url, api_key, api_format, model_id, probe_kind, raw_headers)
        _latency = int(round((time.time() - _t0) * 1000))
        if not isinstance(v_res, dict):
            v_res = {"success": bool(v_res), "error": None}
        v_res.setdefault("success", False)
        v_res["ok"] = bool(v_res.get("success"))
        if "latency_ms" not in v_res:
            v_res["latency_ms"] = _latency
        self.send_json_response(v_res)

    def _probe_custom_endpoint_direct(
        self,
        base_url: str,
        api_key: str,
        api_format: str,
        model_id: str,
        kind: str = "llm",
        headers: Any = None,
    ) -> dict[str, Any]:
        base = (base_url or "").rstrip("/")
        ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoiceFlow/2.0"}
        custom_h: dict[str, str] = {}
        if isinstance(headers, dict):
            custom_h = {str(k): str(v) for k, v in headers.items()}
        elif isinstance(headers, str) and headers.strip():
            try:
                parsed = json.loads(headers)
                if isinstance(parsed, dict):
                    custom_h = {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                pass

        def _clean_err(status: int, raw: str) -> str:
            try:
                p = json.loads(raw)
                if isinstance(p, dict):
                    err = p.get("error")
                    if isinstance(err, dict):
                        return err.get("message") or str(err)
                    elif isinstance(err, str):
                        return err
                    return p.get("message") or p.get("detail") or f"HTTP {status}"
            except Exception:
                pass
            return (raw.strip() if raw and len(raw) < 250 else f"HTTP {status}")

        try:
            if kind == "stt":
                if api_format not in {"openai", "openai_compatible"}:
                    return {"success": False, "error": f"Custom STT testing is not implemented for '{api_format}' format."}
                boundary = "----VoiceFlowProbe" + secrets.token_hex(8)
                silent_wav = self._create_silent_wav(duration_ms=250)
                body = b"".join([
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model_id}\r\n".encode("utf-8"),
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"),
                    silent_wav,
                    f"\r\n--{boundary}--\r\n".encode("utf-8"),
                ])
                hdrs = {"Content-Type": f"multipart/form-data; boundary={boundary}", **ua, **custom_h}
                if api_key:
                    hdrs["Authorization"] = f"Bearer {api_key}"
                url = base if base.endswith("/audio/transcriptions") else f"{base}/audio/transcriptions"
                req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                    if resp.status in (200, 201) and raw:
                        return {"success": True, "message": "STT transcription endpoint verified"}
                    return {"success": False, "error": "STT endpoint returned no response." if resp.status in (200, 201) else f"HTTP {resp.status}"}

            if kind == "tts":
                if api_format == "elevenlabs":
                    url = f"{base}/v1/voices"
                    hdrs = {"xi-api-key": api_key, **ua, **custom_h}
                    req = urllib.request.Request(url, headers=hdrs, method="GET")
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        if resp.status in (200, 201):
                            return {"success": True, "message": "ElevenLabs TTS endpoint verified"}
                        return {"success": False, "error": f"HTTP {resp.status}"}
                else:
                    hdrs = {"Content-Type": "application/json", **ua, **custom_h}
                    if api_key:
                        hdrs["Authorization"] = f"Bearer {api_key}"
                    # A /models response proves only that authentication works.
                    # A TTS connection test must exercise the speech endpoint and
                    # receive non-empty audio from the requested model.
                    url = f"{base}/audio/speech" if not base.endswith("/speech") else base
                    body = json.dumps({"model": model_id or "tts-1", "input": "test", "voice": "alloy"}).encode("utf-8")
                    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        audio = resp.read()
                        if resp.status in (200, 201) and audio:
                            return {"success": True, "message": "TTS speech synthesis verified", "audio_bytes": len(audio)}
                        if resp.status in (200, 201):
                            return {"success": False, "error": "TTS endpoint returned no audio."}
                        return {"success": False, "error": f"HTTP {resp.status}"}

            elif api_format == "anthropic":
                hdrs = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", **ua, **custom_h}
                body = json.dumps({"model": model_id or "claude-3-haiku-20240307", "max_tokens": 8, "messages": [{"role": "user", "content": "ping"}]}).encode("utf-8")
                req = urllib.request.Request(f"{base}/v1/messages", data=body, headers=hdrs, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        return {"success": True, "message": "Anthropic messages endpoint verified"}
                    return {"success": False, "error": f"HTTP {resp.status}"}

            elif api_format == "gemini":
                delim = "&" if "?" in base else "?"
                url = f"{base}/models{delim}key={api_key}"
                hdrs = {"x-goog-api-key": api_key, **ua, **custom_h}
                req = urllib.request.Request(url, headers=hdrs, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        return {"success": True, "message": "Gemini models endpoint verified"}
                    return {"success": False, "error": f"HTTP {resp.status}"}

            else:
                hdrs = {"Content-Type": "application/json", **ua, **custom_h}
                if api_key:
                    hdrs["Authorization"] = f"Bearer {api_key}"
                try:
                    req_m = urllib.request.Request(f"{base}/models", headers=hdrs, method="GET")
                    with urllib.request.urlopen(req_m, timeout=8) as resp_m:
                        if resp_m.status in (200, 201):
                            return {"success": True, "message": "OpenAI models endpoint verified"}
                except Exception:
                    pass
                body = json.dumps({
                    "model": model_id or "gpt-4o",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 4,
                }).encode("utf-8")
                req = urllib.request.Request(f"{base}/chat/completions", data=body, headers=hdrs, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        return {"success": True, "message": "OpenAI chat completions endpoint verified"}
                    return {"success": False, "error": f"HTTP {resp.status}"}

        except urllib.error.HTTPError as he:
            raw = ""
            try:
                raw = he.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return {"success": False, "error": _clean_err(he.code, raw)}
        except Exception as exc:
            return {"success": False, "error": str(exc)[:220]}

    def verify_api_key(self, provider: str, key: str) -> dict:
        """Perform live test against AI & Voice Provider API endpoints."""
        if not key:
            return {"success": False, "error": "API key cannot be empty"}

        format_error = self._check_key_format(provider, key)
        if format_error:
            return {"success": False, "error": format_error}

        ua_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                req = urllib.request.Request(url, headers=ua_headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Gemini API Key Verified! Model ready for transcription polishing."}

            elif provider == "google":
                # First try Google Cloud TTS endpoint
                url = f"https://texttospeech.googleapis.com/v1/voices?key={key}&languageCode=en-US"
                req = urllib.request.Request(url, headers=ua_headers)
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        if response.status == 200:
                            return {"success": True, "message": "Google Cloud TTS API Key Verified! Text-to-speech ready."}
                except urllib.error.HTTPError:
                    # Fallback test: Google Gemini / Generative Language endpoint
                    alt_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    alt_req = urllib.request.Request(alt_url, headers=ua_headers)
                    with urllib.request.urlopen(alt_req, timeout=30) as response:
                        if response.status == 200:
                            return {"success": True, "message": "Google API Key Verified via Gemini AI Endpoint!"}
                    raise

            elif provider == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Groq API Key Verified! Llama-3.3 model active."}

            elif provider == "elevenlabs":
                url = "https://api.elevenlabs.io/v1/voices"
                headers = {"xi-api-key": key, **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "ElevenLabs Voice API Verified! TTS audio generation ready."}

            elif provider == "deepgram":
                url = "https://api.deepgram.com/v1/projects"
                headers = {"Authorization": f"Token {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Deepgram API Verified! Nova-3 speech model active."}

            elif provider == "assemblyai":
                url = "https://api.assemblyai.com/v2/transcripts?limit=1"
                req = urllib.request.Request(url, headers={"authorization": key, **ua_headers})
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "AssemblyAI API Verified! Universal speech-to-text ready."}

            elif provider == "speechmatics":
                url = "https://asr.api.speechmatics.com/v2/engines"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", **ua_headers})
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Speechmatics API Verified! Speech-to-text ready."}

            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "OpenAI API Verified! gpt-4o-mini model ready."}

            elif provider in ("nvidia", "nvidia_nim"):
                url = "https://integrate.api.nvidia.com/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200:
                        return {"success": True, "message": "NVIDIA NIM API Verified! Parakeet & Canary speech models ready."}

            else:
                is_valid, last_error = validate_provider_key(provider, key)
                if is_valid:
                    return {"success": True, "message": f"{provider.capitalize()} API Key Verified!"}
                return {"success": False, "error": last_error or f"Could not verify {provider} API key."}

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            if e.code == 400 and "API_KEY_INVALID" in error_body:
                return {"success": False, "error": f"Invalid {provider.capitalize()} API key. Please get a valid key from the provider's dashboard."}
            if e.code == 401:
                return {"success": False, "error": f"Invalid {provider.capitalize()} API key (HTTP 401 Unauthorized). Please check your key."}
            if e.code in (403, 429):
                return {"success": False, "error": f"{provider.capitalize()} API returned HTTP {e.code} (rate-limited or forbidden). Check key permissions or try again later."}
            return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": f"Connection failed: {e}. Check your internet and try again."}

        return {"success": False, "error": "Verification failed."}

    def _create_silent_wav(self, duration_ms: int = 250, sample_rate: int = 16000) -> bytes:
        channels = 1
        bits_per_sample = 16
        sample_count = max(1, int(sample_rate * duration_ms / 1000))
        data_size = sample_count * channels * (bits_per_sample // 8)
        import struct
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,
            1,
            channels,
            sample_rate,
            sample_rate * channels * (bits_per_sample // 8),
            channels * (bits_per_sample // 8),
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + (b"\x00" * data_size)

    def verify_model_by_kind(self, provider: str, key: str = "", model_id: str = "", kind: str = "auto", base_url: str = "") -> dict:
        """Live probe per model kind (llm / stt / tts) with clean provider errors matching 9Router."""
        _t0 = time.time()

        def _latency() -> int:
            return max(1, int(round((time.time() - _t0) * 1000)))

        def _success(msg: str = "", **extra) -> dict:
            res = {
                "success": True,
                "ok": True,
                "latency_ms": _latency(),
                "error": None,
            }
            if msg:
                res["message"] = msg
            res.update(extra)
            return res

        def _failure(err: str, **extra) -> dict:
            res = {
                "success": False,
                "ok": False,
                "latency_ms": _latency(),
                "error": str(err),
            }
            res.update(extra)
            return res

        ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        model_id = (model_id or "").strip()
        provider = (provider or "").lower().strip()
        provider = _canonical_provider_for_kind(provider, kind)
        model_id = strip_redundant_model_prefix(provider, model_id)
        if not model_id:
            return _failure("Enter a model ID first.")

        low = model_id.lower()
        if kind in ("auto", "", None):
            # NOTE: "nova" is deliberately NOT here — it is an OpenAI TTS voice,
            # and matching it as STT misroutes that model. Deepgram is already
            # forced to STT below.
            stt_kw = ("whisper", "transcri", "stt", "universal", "scribe", "speechmatics", "listen",
                      "parakeet", "canary", "asr")
            if provider in ("deepgram", "assemblyai", "speechmatics"):
                kind = "stt"
            elif provider in ("gemini", "google", "googleai", "anthropic", "claude"):
                kind = "llm"
            elif provider in ("nvidia", "nvidia_nim") and any(k in low for k in stt_kw):
                # NVIDIA hosts real STT models (Parakeet / Canary); without this
                # they were probed as LLMs and always failed.
                kind = "stt"
            elif any(k in low for k in stt_kw):
                kind = "stt"
            elif provider in ("edge", "elevenlabs", "fish", "cartesia", "playht", "sapi", "sapi5", "windows") or provider.startswith("audio-"):
                kind = "tts"
            else:
                kind = "llm"
        elif provider in ("gemini", "google", "googleai", "anthropic", "claude") and kind == "stt":
            kind = "llm"

        def _clean(status, raw):
            parsed = None
            try:
                parsed = json.loads(raw)
            except Exception:
                pass
            msg = None
            if isinstance(parsed, dict):
                err = parsed.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("code")
                elif isinstance(err, str):
                    msg = err
                if not msg:
                    msg = parsed.get("message") or parsed.get("msg") or parsed.get("detail")
                    if isinstance(msg, dict):
                        msg = msg.get("message")
                if not msg and parsed.get("errors") and isinstance(parsed["errors"], list):
                    msg = parsed["errors"][0].get("message")
            if not msg and raw and len(raw) < 300:
                msg = raw.strip()
            if not msg:
                msg = f"Provider returned HTTP {status}"
            if status == 401:
                return "Invalid API key or token expired (HTTP 401)" + (f": {msg}" if msg and "401" not in str(msg) else "")
            if status == 403:
                return "Forbidden - check API key permissions (HTTP 403)" + (f": {msg}" if msg and "403" not in str(msg) else "")
            if status == 429:
                return "Quota exhausted / Rate limit reached (HTTP 429)" + (f": {msg}" if msg and "429" not in str(msg) else "")
            if status == 404:
                return f"The model '{model_id}' does not exist or you do not have access to it (HTTP 404)" + (f": {msg}" if msg and "404" not in str(msg) else "")
            if status == 503:
                return "Provider model is experiencing high demand or temporary outage (HTTP 503)" + (f": {msg}" if msg and "503" not in str(msg) else "")
            return str(msg)[:280]

        def _err_text(http_err):
            try:
                raw = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            return _clean(http_err.code, raw)

        try:
            # -------------------------------------------------------------
            # A. CUSTOM LOCAL / REMOTE PROVIDERS
            # -------------------------------------------------------------
            if provider.startswith("custom-"):
                entry = None
                try:
                    all_cp = (
                        storage.get_voice_flow_custom_providers()
                        + storage.get_audio_flow_custom_providers()
                        + storage.get_video_flow_custom_providers()
                    )
                    for cp in all_cp:
                        if cp.get("id") == provider:
                            entry = cp
                            break
                except Exception:
                    pass
                if not entry:
                    return _failure("Custom provider no longer exists.")
                base = str(base_url or entry.get("base_url") or "").rstrip("/")
                configured_keys = entry.get("api_keys") or []
                keys_sorted = sorted(
                    configured_keys,
                    key=lambda item: (item.get("priority") if isinstance(item.get("priority"), int) else 99),
                )
                keys_active = [str(k.get("key") or "").strip() for k in keys_sorted
                               if k.get("is_active") and str(k.get("key") or "").strip()]
                legacy_key = str(entry.get("api_key") or "").strip() if not configured_keys else ""
                ckey = key.strip() if key and key.strip() else (keys_active[0] if keys_active else legacy_key)
                if not ckey and not str(entry.get("base_url") or "").lower().startswith(("http://127.0.0.1", "http://localhost")):
                    return _failure("No enabled API key is available for this custom provider.")
                fmt = str(entry.get("api_format") or "openai").lower()
                custom_h: dict[str, str] = {}
                hdrs_val = entry.get("headers")
                if isinstance(hdrs_val, dict):
                    custom_h = {str(k): str(v) for k, v in hdrs_val.items()}
                elif isinstance(hdrs_val, str) and hdrs_val.strip():
                    try:
                        parsed = json.loads(hdrs_val)
                        if isinstance(parsed, dict):
                            custom_h = {str(k): str(v) for k, v in parsed.items()}
                    except Exception:
                        pass
                if kind == "tts":
                    if fmt == "elevenlabs":
                        url = f"{base}/v1/text-to-speech/{urllib.parse.quote(model_id or 'default')}"
                        body = json.dumps({"text": "test"}).encode()
                        headers = {"xi-api-key": ckey, "Content-Type": "application/json", **ua, **custom_h}
                    else:
                        url = base if (base.endswith("/speech") or base.endswith("/audio/speech")) else f"{base}/audio/speech"
                        body = json.dumps({"model": model_id or "tts-1", "input": "test", "voice": "alloy"}).encode()
                        headers = {"Authorization": f"Bearer {ckey}", "Content-Type": "application/json", **ua, **custom_h}
                    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as response:
                        raw = response.read()
                        status = response.status
                    if status != 200:
                        return _failure(_clean(status, raw))
                    return _success("Custom TTS model verified successfully.")
                if fmt == "anthropic":
                    body = json.dumps({"model": model_id, "max_tokens": 16,
                                       "messages": [{"role": "user", "content": "hi"}]}).encode()
                    anth_url = base if base.endswith("/messages") else (base + "/messages" if base.endswith("/v1") else f"{base}/v1/messages")
                    req = urllib.request.Request(
                        anth_url, data=body, method="POST",
                        headers={"x-api-key": ckey, "anthropic-version": "2023-06-01",
                                 "Content-Type": "application/json", **ua, **custom_h})
                    with urllib.request.urlopen(req, timeout=45) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        status = response.status
                    if status != 200:
                        return _failure(_clean(status, raw))
                    return _success("Custom Anthropic model verified successfully.")
                if fmt == "gemini":
                    delim = "&" if "?" in base else "?"
                    url = f"{base}/models/{model_id}:generateContent{delim}key={ckey}" if ":generateContent" not in base else f"{base}{delim}key={ckey}"
                    body = json.dumps({"contents": [{"parts": [{"text": "hi"}]}]}).encode()
                    headers = {"Content-Type": "application/json", "x-goog-api-key": ckey, **ua, **custom_h}
                    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
                    with urllib.request.urlopen(req, timeout=45) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        status = response.status
                    if status != 200:
                        return _failure(_clean(status, raw))
                    return _success("Custom Gemini model verified successfully.")

                # default: OpenAI-compatible
                chat_url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
                is_r = bool(re.search(r"^(o[1-9]|gpt-5|chatgpt)", model_id, re.I) or re.search(r"(?:^|/)(o1|o3|o4)(?:-|$)", model_id, re.I))
                payload_c = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                }
                if is_r:
                    payload_c["max_completion_tokens"] = 64
                else:
                    payload_c["max_tokens"] = 64
                body = json.dumps(payload_c).encode()
                req = urllib.request.Request(
                    chat_url, data=body, method="POST",
                    headers={"Authorization": f"Bearer {ckey}", "Content-Type": "application/json", **ua, **custom_h})
                try:
                    with urllib.request.urlopen(req, timeout=45) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        status = response.status
                    if status != 200:
                        return _failure(_clean(status, raw))
                    return _success("Custom model verified successfully.")
                except urllib.error.HTTPError as cp_http_err:
                    err_txt = cp_http_err.read().decode("utf-8", errors="replace")
                    if cp_http_err.code == 400 and ("max_tokens" in err_txt.lower() or "max_completion_tokens" in err_txt.lower()):
                        alt_payload = dict(payload_c)
                        if "max_tokens" in alt_payload:
                            alt_payload.pop("max_tokens")
                            alt_payload["max_completion_tokens"] = 64
                        else:
                            alt_payload.pop("max_completion_tokens")
                            alt_payload["max_tokens"] = 64
                        alt_body = json.dumps(alt_payload).encode()
                        alt_req = urllib.request.Request(
                            chat_url, data=alt_body, method="POST",
                            headers={"Authorization": f"Bearer {ckey}", "Content-Type": "application/json", **ua, **custom_h})
                        with urllib.request.urlopen(alt_req, timeout=45) as alt_resp:
                            if alt_resp.status == 200:
                                return _success("Custom model verified successfully.")
                    return _failure(_clean(cp_http_err.code, err_txt))

            # -------------------------------------------------------------
            # B. SPEECH-TO-TEXT (STT) PROBES
            # -------------------------------------------------------------
            if kind == "stt":
                silent_wav = self._create_silent_wav(duration_ms=250)

                # 1. Deepgram STT Listen API
                if provider == "deepgram":
                    url = f"https://api.deepgram.com/v1/listen?model={urllib.parse.quote(model_id or 'nova-2')}"
                    req = urllib.request.Request(
                        url, data=silent_wav, method="POST",
                        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav", **ua})
                    with urllib.request.urlopen(req, timeout=20) as response:
                        if response.status == 200:
                            return _success(f"Deepgram STT model '{model_id}' verified.")
                        raw = response.read().decode("utf-8", errors="replace")
                        return _failure(_clean(response.status, raw))

                # 2. AssemblyAI STT — upload then create a transcript so the
                #    requested model is actually exercised. Uploading alone
                #    returned success for ANY model id (false positive).
                elif provider == "assemblyai":
                    up_url = "https://api.assemblyai.com/v2/upload"
                    up_req = urllib.request.Request(
                        up_url, data=silent_wav, method="POST",
                        headers={"Authorization": key, "Content-Type": "application/octet-stream", **ua})
                    with urllib.request.urlopen(up_req, timeout=20) as up_res:
                        if up_res.status != 200:
                            return _failure(_clean(up_res.status, up_res.read().decode("utf-8", errors="replace")))
                        upload_url = str(json.loads(up_res.read().decode("utf-8", errors="replace")).get("upload_url") or "")
                    if not upload_url:
                        return _failure("AssemblyAI upload succeeded but returned no upload_url.")
                    tr_body = json.dumps({"audio_url": upload_url, "speech_model": model_id}).encode()
                    tr_req = urllib.request.Request(
                        "https://api.assemblyai.com/v2/transcript", data=tr_body, method="POST",
                        headers={"Authorization": key, "Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(tr_req, timeout=25) as tr_res:
                        raw = tr_res.read().decode("utf-8", errors="replace")
                        if tr_res.status in (200, 201):
                            return _success(f"AssemblyAI STT model '{model_id}' verified.")
                        return _failure(_clean(tr_res.status, raw))

                # 3. Speechmatics STT — /v2/jobs is the real authenticated route;
                #    /v2/job_configs returns 404 for every request.
                elif provider == "speechmatics":
                    url = "https://asr.api.speechmatics.com/v2/jobs"
                    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", **ua})
                    with urllib.request.urlopen(req, timeout=20) as response:
                        if response.status in (200, 201):
                            return _success(f"Speechmatics STT model '{model_id}' verified.")
                        raw = response.read().decode("utf-8", errors="replace")
                        return _failure(_clean(response.status, raw))

                # 4. ElevenLabs STT (speech-to-text)
                elif provider == "elevenlabs":
                    base = (base_url or "https://api.elevenlabs.io").rstrip("/")
                    boundary = "----VoiceFlowBoundary" + str(int(time.time() * 1000))
                    form_parts = [
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\n{model_id or 'scribe_v1'}\r\n".encode("utf-8"),
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"),
                        silent_wav,
                        f"\r\n--{boundary}--\r\n".encode("utf-8"),
                    ]
                    req = urllib.request.Request(
                        f"{base}/v1/speech-to-text", data=b"".join(form_parts), method="POST",
                        headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}", **ua})
                    with urllib.request.urlopen(req, timeout=25) as response:
                        if response.status == 200:
                            return _success(f"ElevenLabs STT model '{model_id}' verified.")
                        raw = response.read().decode("utf-8", errors="replace")
                        return _failure(_clean(response.status, raw))

                # 5. NVIDIA STT (Parakeet / Canary) — self-hosted NIM, so honour
                #    a configured base_url; the public catalog has no STT route.
                elif provider in ("nvidia", "nvidia_nim"):
                    nv_base = str(base_url or "").strip().rstrip("/")
                    if not nv_base:
                        return _failure(
                            "NVIDIA STT runs as a self-hosted NIM (default http://localhost:9000). "
                            "Set this provider's base URL to your NIM endpoint to test it."
                        )
                    boundary = "----VoiceFlowBoundary" + str(int(time.time() * 1000))
                    form_parts = [
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model_id}\r\n".encode("utf-8"),
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"),
                        silent_wav,
                        f"\r\n--{boundary}--\r\n".encode("utf-8"),
                    ]
                    req = urllib.request.Request(
                        f"{nv_base}/v1/audio/transcriptions", data=b"".join(form_parts), method="POST",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}", **ua})
                    with urllib.request.urlopen(req, timeout=25) as response:
                        if response.status == 200:
                            return _success(f"NVIDIA STT model '{model_id}' verified.")
                        raw = response.read().decode("utf-8", errors="replace")
                        return _failure(_clean(response.status, raw))

                # 6. Gemini / Google Provider (multimodal / LLM generation, not OpenAI STT)
                elif provider in ("gemini", "google", "googleai"):
                    pass

                # 7. Groq Whisper / OpenAI Whisper / Standard Transcriptions
                elif provider in ("groq", "openai") or base_url:
                    base = base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")
                    boundary = "----VoiceFlowBoundary" + str(int(time.time() * 1000))
                    c_type = f"multipart/form-data; boundary={boundary}"

                    form_parts = [
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model_id or 'whisper-large-v3-turbo'}\r\n".encode("utf-8"),
                        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"),
                        silent_wav,
                        f"\r\n--{boundary}--\r\n".encode("utf-8"),
                    ]
                    body = b"".join(form_parts)
                    req = urllib.request.Request(
                        f"{base}/audio/transcriptions", data=body, method="POST",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": c_type, **ua})
                    with urllib.request.urlopen(req, timeout=20) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        if response.status == 200:
                            return _success(f"{provider.capitalize()} Whisper STT model '{model_id}' verified.")
                        return _failure(_clean(response.status, raw))

                else:
                    return _failure(f"Provider '{provider}' does not support audio transcription (STT).")

            # -------------------------------------------------------------
            # C. TEXT-TO-SPEECH (TTS) PROBES
            # -------------------------------------------------------------
            if kind == "tts":
                if provider == "edge":
                    known = storage.get_tts_models_for_provider("edge")
                    if not any(str(item.get("model_id") or "") == model_id for item in known):
                        return _failure(f"Edge voice '{model_id}' is not in the installed voice catalog.")
                    return _success(f"Edge voice '{model_id}' is available.")
                if provider in ("offline", "sapi", "sapi5", "windows"):
                    return _success("Windows offline SAPI voice is available.")

                audio = None
                if provider == "elevenlabs":
                    m_lower = (model_id or "").strip().lower()
                    if m_lower.startswith(("eleven_", "eleven-")):
                        body = json.dumps({"text": "Test.", "model_id": model_id}).encode()
                        voice_target = "21m00Tcm4TlvDq8ikWAM"
                    else:
                        body = json.dumps({"text": "Test.", "model_id": "eleven_multilingual_v2"}).encode()
                        voice_target = urllib.parse.quote(model_id or "21m00Tcm4TlvDq8ikWAM")
                    req = urllib.request.Request(
                        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_target}",
                        data=body, method="POST",
                        headers={"xi-api-key": key, "Content-Type": "application/json", **ua})
                    try:
                        with urllib.request.urlopen(req, timeout=20) as res:
                            audio = res.read()
                            if res.status != 200:
                                return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))
                    except urllib.error.HTTPError as el_err:
                        if el_err.code in (400, 404):
                            chk = self.verify_provider_model(provider, key, model_id)
                            if chk.get("success"):
                                return _success(f"ElevenLabs voice '{model_id}' verified.")
                        raise

                elif provider == "openai":
                    m_lower = (model_id or "").strip().lower()
                    openai_voices = {"alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"}
                    openai_tts_models = {"tts-1", "tts-1-hd", "gpt-4o-audio-preview"}
                    if ":" in model_id:
                        target_model, target_voice = [part.strip() for part in model_id.split(":", 1)]
                    elif m_lower in openai_tts_models or m_lower.startswith("tts-"):
                        target_model = model_id
                        target_voice = "alloy"
                    elif m_lower in openai_voices:
                        target_model = "tts-1"
                        target_voice = model_id
                    else:
                        target_model = model_id or "tts-1"
                        target_voice = "alloy"
                    body = json.dumps({"model": target_model, "input": "Test.", "voice": target_voice, "response_format": "mp3"}).encode()
                    req = urllib.request.Request(
                        "https://api.openai.com/v1/audio/speech", data=body, method="POST",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **ua})
                    try:
                        with urllib.request.urlopen(req, timeout=20) as res:
                            audio = res.read()
                            if res.status != 200:
                                return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))
                    except urllib.error.HTTPError as speech_err:
                        if speech_err.code == 400 and target_model != "tts-1":
                            retry_body = json.dumps({"model": "tts-1", "input": "Test.", "voice": model_id, "response_format": "mp3"}).encode()
                            retry_req = urllib.request.Request(
                                "https://api.openai.com/v1/audio/speech", data=retry_body, method="POST",
                                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **ua})
                            with urllib.request.urlopen(retry_req, timeout=20) as res2:
                                audio = res2.read()
                                if res2.status != 200:
                                    return _failure(_clean(res2.status, audio.decode("utf-8", errors="replace")))
                        else:
                            raise

                elif provider == "deepgram":
                    body = json.dumps({"text": "Test."}).encode()
                    voice_target = urllib.parse.quote(model_id or "aura-asteria-en")
                    req = urllib.request.Request(
                        f"https://api.deepgram.com/v1/speak?model={voice_target}",
                        data=body, method="POST",
                        headers={"Authorization": f"Token {key}", "Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=20) as res:
                        audio = res.read()
                        if res.status != 200:
                            return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))

                elif provider == "google":
                    body = json.dumps({
                        "input": {"text": "Test."},
                        "voice": {"languageCode": "en-US", "name": model_id},
                        "audioConfig": {"audioEncoding": "MP3"},
                    }).encode()
                    req = urllib.request.Request(
                        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={urllib.parse.quote(key)}",
                        data=body, method="POST", headers={"Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=20) as res:
                        raw = json.loads(res.read().decode("utf-8", errors="replace"))
                        audio_b64 = str(raw.get("audioContent") or "")
                        if res.status != 200 or not audio_b64:
                            return _failure("Google Cloud TTS returned no audio.")
                        audio = base64.b64decode(audio_b64)

                elif provider == "gemini":
                    model_name, _, voice_name = model_id.partition(":")
                    body = json.dumps({
                        "contents": [{"parts": [{"text": "Test."}]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name or "Kore"}}},
                        },
                    }).encode()
                    req = urllib.request.Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model_name)}:generateContent?key={urllib.parse.quote(key)}",
                        data=body, method="POST", headers={"Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=30) as res:
                        raw = json.loads(res.read().decode("utf-8", errors="replace"))
                        parts = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
                        audio_b64 = next((str((part.get("inlineData") or {}).get("data") or "") for part in parts if (part.get("inlineData") or {}).get("data")), "")
                        if res.status != 200 or not audio_b64:
                            return _failure("Gemini TTS returned no audio.")
                        audio = base64.b64decode(audio_b64)

                elif provider in ("nvidia", "nvidia_nim"):
                    # NVIDIA Riva TTS is a SELF-HOSTED NIM (gRPC 50051 / HTTP 9000).
                    # NVIDIA's public catalog (integrate.api.nvidia.com) exposes no
                    # TTS models and has no /v1/audio/* route, so probing a fixed
                    # cloud URL can only ever 404. Honour a configured base_url,
                    # and otherwise report the real requirement instead of a
                    # misleading "model does not exist".
                    nv_base = str(base_url or "").strip().rstrip("/")
                    if not nv_base:
                        return _failure(
                            "NVIDIA Riva TTS runs as a self-hosted NIM (default http://localhost:9000). "
                            "Set this provider's base URL to your Riva endpoint to test it."
                        )
                    fam, _, voice = model_id.partition(":")
                    target_url = nv_base if nv_base.endswith("/v1/audio/speech") else f"{nv_base}/v1/audio/speech"
                    # Riva's HTTP API takes the voice name explicitly rather than
                    # a catalog model id.
                    body = json.dumps({
                        "text": "Test.",
                        "voice_name": voice or fam or "English-US.Female-1",
                        "language_code": "en-US",
                        "encoding": "LINEAR_PCM",
                        "sample_rate_hz": 44100,
                    }).encode()
                    req = urllib.request.Request(
                        target_url, data=body, method="POST",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=20) as res:
                        audio = res.read()
                        if res.status != 200:
                            return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))

                elif provider == "fish":
                    body = json.dumps({"text": "Test.", "reference_id": model_id or "default", "format": "mp3"}).encode()
                    req = urllib.request.Request(
                        "https://api.fish.audio/v1/tts", data=body, method="POST",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=20) as res:
                        audio = res.read()
                        if res.status != 200:
                            return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))

                elif provider == "cartesia":
                    body = json.dumps({
                        "model_id": "sonic-english",
                        "transcript": "Test.",
                        "voice": {"mode": "id", "id": model_id or "694f934f-9150-4126-a6d6-916a80c384d7"},
                        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000}
                    }).encode()
                    req = urllib.request.Request(
                        "https://api.cartesia.ai/tts/bytes", data=body, method="POST",
                        headers={"X-API-Key": key, "Cartesia-Version": "2024-06-10", "Content-Type": "application/json", **ua})
                    with urllib.request.urlopen(req, timeout=20) as res:
                        audio = res.read()
                        if res.status != 200:
                            return _failure(_clean(res.status, audio.decode("utf-8", errors="replace")))

                else:
                    tts_res = self.verify_tts_api_key(provider, key)
                    ok = bool(tts_res.get("valid"))
                    if ok:
                        return _success(f"{provider.capitalize()} TTS verified successfully.")
                    return _failure(str(tts_res.get("status") or "TTS verification failed"))

                if not audio or len(audio) == 0:
                    return _failure("TTS endpoint returned 0 bytes of audio.")
                return _success(f"{provider.capitalize()} voice '{model_id}' verified successfully.")

            # -------------------------------------------------------------
            # D. LLM / TEXT GENERATION PROBES
            # -------------------------------------------------------------
            if provider in ("antigravity", "agy"):
                target_model = (model_id or "gemini-3.8-flash").strip()
                while True:
                    cleaned = False
                    for pfx in ("antigravity/", "agy/", "models/"):
                        if target_model.lower().startswith(pfx):
                            target_model = target_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                if not target_model:
                    target_model = "gemini-3.8-flash"

                token = key.strip() if key and not key.startswith("antigravity-") else ""
                proj = ""
                conn_row = None
                if not token:
                    try:
                        from voice_flow.video_flow_oauth import decrypt_token
                        conns = video_flow_provider_service.list_connections("antigravity")
                        for c in sorted(conns, key=lambda x: int(x.get("id") or 0), reverse=True):
                            if not c.get("is_active"):
                                continue
                            try:
                                row = video_flow_provider_service.get_connection(int(c["id"]), public=False)
                                secret = str(row.get("secret") or "")
                            except Exception:
                                secret = ""
                            if secret and "cli-bridge" not in secret:
                                token = decrypt_token(video_flow_provider_service, secret) or secret
                                conn_row = c
                                proj = (row.get("metadata") or {}).get("project_id") or ""
                                if conn_row.get("metadata") and conn_row["metadata"].get("project_id"):
                                    proj = conn_row["metadata"].get("project_id")
                                if token:
                                    break
                    except Exception:
                        token = ""
                if not token:
                    try:
                        pconns = storage.get_provider_connections("antigravity")
                        for pc in sorted(pconns, key=lambda x: int(x.get("id") or 0), reverse=True):
                            if pc.get("is_active") and pc.get("api_key"):
                                token = str(pc.get("api_key") or "").strip()
                                if token:
                                    break
                    except Exception:
                        pass

                if token and not token.startswith("antigravity-"):
                    try:
                        def _fetch_models(t):
                            body = json.dumps({"project": proj} if proj else {}).encode("utf-8")
                            req = urllib.request.Request(
                                "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
                                data=body,
                                headers={
                                    "Authorization": "Bearer " + t,
                                    "Content-Type": "application/json",
                                    "User-Agent": "antigravity/ide/2.1.1 win32/x64",
                                    "X-Client-Name": "antigravity",
                                    "X-Client-Version": "2.1.1",
                                    "x-request-source": "local",
                                },
                                method="POST",
                            )
                            with urllib.request.urlopen(req, timeout=12) as resp:
                                return json.loads(resp.read().decode("utf-8", errors="replace")).get("models") or {}

                        try:
                            models_data = _fetch_models(token)
                        except urllib.error.HTTPError as he:
                            if he.code == 401 and conn_row is not None:
                                rt = ""
                                try:
                                    priv = video_flow_provider_service.get_connection(int(conn_row["id"]), public=False)
                                    from voice_flow.video_flow_oauth import decrypt_token as _vf_dec
                                    rt = _vf_dec(video_flow_provider_service, str(priv.get("refresh_token") or ""))
                                    if not rt:
                                        rt = str((priv.get("metadata") or {}).get("refresh_token") or "")
                                except Exception:
                                    rt = ""
                                if rt:
                                    tok_res = _http_json(
                                        "https://oauth2.googleapis.com/token",
                                        data={
                                            "grant_type": "refresh_token",
                                            "client_id": ANTIGRAVITY_CLIENT_ID,
                                            "client_secret": ANTIGRAVITY_CLIENT_SECRET,
                                            "refresh_token": rt,
                                        },
                                    )
                                    new_access = str(tok_res.get("access_token") or "")
                                    if new_access:
                                        token = new_access
                                        try:
                                            exp = int(time.time()) + int(tok_res.get("expires_in") or 3600)
                                            meta = dict((conn_row.get("metadata") or {}))
                                            meta["expires_at"] = exp
                                            video_flow_provider_service.update_connection(
                                                int(conn_row["id"]),
                                                secret=encrypt_token(video_flow_provider_service, new_access),
                                                expires_at=str(exp),
                                                metadata=meta,
                                            )
                                        except Exception:
                                            pass
                                        models_data = _fetch_models(token)
                                    else:
                                        return _failure("Antigravity token expired and refresh failed.")
                                else:
                                    return _failure("Antigravity token expired. Reconnect the account.")
                            else:
                                return _failure(_err_text(he))

                        mid = target_model.lower()
                        best = None
                        for key_q, info in models_data.items():
                            k = key_q.lower()
                            if k == mid or k.startswith(mid) or mid.startswith(k):
                                q = (info or {}).get("quotaInfo") or {}
                                if q.get("remainingFraction") is not None:
                                    frac = float(q.get("remainingFraction") or 0)
                                    best = frac if best is None else max(best, frac)
                        if best is None:
                            family_prefix = mid.split("-")[0] if "-" in mid else mid
                            if family_prefix in ("gemini", "claude"):
                                family_fractions = [
                                    float((info or {}).get("quotaInfo", {}).get("remainingFraction"))
                                    for key_q, info in models_data.items()
                                    if key_q.lower().startswith(family_prefix)
                                    and isinstance(info, dict)
                                    and (info.get("quotaInfo") or {}).get("remainingFraction") is not None
                                ]
                                if family_fractions:
                                    best = max(family_fractions)
                        if best is None:
                            return _failure(f"Model '{target_model}' is not available in your Antigravity subscription.")
                        if best <= 0:
                            return _failure("No credits left for this model on your Antigravity subscription (quota exhausted).")
                        return _success(
                            f"Antigravity subscription active — {round(best * 100, 1)}% quota remaining for this model.",
                            remaining_pct=round(best * 100, 1),
                        )
                    except urllib.error.HTTPError as he:
                        return _failure(_err_text(he))
                    except Exception as e:
                        return _failure(str(e)[:220])
                else:
                    try:
                        from voice_flow.video_flow_providers import antigravity_bridge_status
                        if antigravity_bridge_status().get("ready"):
                            return _success("Antigravity app bridge active (agy CLI session).")
                        return _failure("No active Antigravity account. Add an account first.")
                    except Exception as exc:
                        return _failure(str(exc)[:200])

            elif provider in ("openai_codex", "codex", "chatgpt"):
                target_model = (model_id or "gpt-5.4").strip()
                active_conns = [c for c in video_flow_provider_service.list_connections("openai_codex") if c.get("is_active")]
                if not active_conns:
                    try:
                        imp_res = video_flow_provider_service.start_oauth("openai_codex")
                        if imp_res.get("imported"):
                            active_conns = [c for c in video_flow_provider_service.list_connections("openai_codex") if c.get("is_active")]
                    except Exception:
                        pass
                if not active_conns:
                    return _failure("No active ChatGPT account connected. Sign in using the Authentication section.")

                best_conn = video_flow_provider_service.pick_best_connection("openai_codex")
                c = best_conn or active_conns[0]
                conn_id = int(c["id"])
                priv = video_flow_provider_service.get_connection(conn_id, public=False) or c
                token = ""
                try:
                    from voice_flow.video_flow_oauth import decrypt_token as _vf_decrypt_token, _extract_jwt_claim as _vf_extract_claim
                    token = video_flow_provider_service.resolve_connection_secret(priv)
                    if not token:
                        secret = str(priv.get("secret") or "")
                        token = _vf_decrypt_token(video_flow_provider_service, secret) or secret
                except Exception:
                    token = str(priv.get("secret") or "")

                chatgpt_account_id = (
                    (priv.get("metadata") or {}).get("chatgpt_account_id")
                    or _vf_extract_claim(token, "chatgpt_account_id")
                    or (c.get("account_id") if c.get("account_id") and "@" not in str(c.get("account_id")) else "")
                )
                codex_supported_models = {
                    "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4-mini", "gpt-5.6-sol", "gpt-5.3-codex-spark", "gpt-5.4"
                }

                def _probe_codex_inner(tok, acc_id):
                    headers = {
                        "Authorization": f"Bearer {tok}",
                        "originator": "codex_cli_rs",
                        "User-Agent": "codex_cli_rs/0.0.0",
                        "Accept": "application/json",
                    }
                    if acc_id:
                        headers["ChatGPT-Account-Id"] = acc_id

                    live_models = set(codex_supported_models)
                    try:
                        req_m = urllib.request.Request(
                            "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
                            headers=headers,
                            method="GET"
                        )
                        with urllib.request.urlopen(req_m, timeout=5) as resp_m:
                            m_data = json.loads(resp_m.read().decode("utf-8"))
                            for m in m_data.get("models") or []:
                                slug = m.get("slug")
                                if slug and m.get("visibility") != "hide":
                                    live_models.add(slug)
                    except Exception:
                        pass

                    req_u = urllib.request.Request(
                        "https://chatgpt.com/backend-api/wham/usage",
                        headers=headers,
                        method="GET"
                    )
                    with urllib.request.urlopen(req_u, timeout=10) as resp_u:
                        usage = json.loads(resp_u.read().decode("utf-8"))
                    return usage, live_models

                try:
                    try:
                        usage_data, available_models = _probe_codex_inner(token, chatgpt_account_id)
                    except urllib.error.HTTPError as e401:
                        if e401.code == 401:
                            video_flow_provider_service.oauth_refresh(conn_id)
                            priv = video_flow_provider_service.get_connection(conn_id, public=False) or c
                            token = video_flow_provider_service.resolve_connection_secret(priv)
                            usage_data, available_models = _probe_codex_inner(token, chatgpt_account_id)
                        else:
                            raise

                    if target_model and target_model not in available_models and target_model not in codex_supported_models:
                        return _failure(f"Model '{target_model}' is not available in the ChatGPT Codex distribution. Supported models: {', '.join(sorted(codex_supported_models))}.")

                    plan_type = usage_data.get("plan_type") or _vf_extract_claim(token, "chatgpt_plan_type") or "free"
                    rate_limit = usage_data.get("rate_limit") or {}
                    allowed = rate_limit.get("allowed", True)
                    limit_reached = rate_limit.get("limit_reached", False)
                    primary = rate_limit.get("primary_window") or {}
                    secondary = rate_limit.get("secondary_window") or {}
                    used_pct = max(primary.get("used_percent") or 0, secondary.get("used_percent") or 0)
                    remaining_pct = max(0, 100 - used_pct)
                    if limit_reached or not allowed or remaining_pct <= 0:
                        return _failure(
                            f"ChatGPT {plan_type.capitalize()} plan quota limit reached (0% remaining). Upgrade your subscription or wait for the quota window to reset.",
                            plan_type=plan_type,
                            remaining_pct=0,
                        )
                    return _success(
                        f"ChatGPT {plan_type.capitalize()} subscription active ({target_model}) — {remaining_pct}% quota remaining.",
                        plan_type=plan_type,
                        remaining_pct=remaining_pct,
                    )
                except Exception as exc:
                    return _failure(f"ChatGPT verification error: {exc}")

            elif provider in ("claude_code", "cursor", "kiro", "copilot"):
                provider_cfg = {}
                try:
                    provider_cfg = video_flow_provider_service.provider(provider) or {}
                except Exception:
                    pass
                provider_name = provider_cfg.get("name") or provider.replace("_", " ").title()
                target_conn = None
                active_conns = [c for c in video_flow_provider_service.list_connections(provider) if c.get("is_active")]
                if active_conns:
                    target_conn = video_flow_provider_service.pick_best_connection(provider) or active_conns[0]
                if not target_conn or not target_conn.get("is_active"):
                    return _failure(f"No active {provider_name} account connected. Sign in using the Authentication section.")
                try:
                    is_healthy = video_flow_provider_service.connection_is_healthy(target_conn)
                    if is_healthy:
                        return _success(f"{provider_name} subscription active ({model_id}). Session verified.")
                    return _failure(f"{provider_name} session is expired or invalid. Please re-authenticate.")
                except Exception as exc:
                    return _failure(f"{provider_name} verification error: {exc}")

            elif provider in ("gemini", "google", "googleai"):
                target_model = (model_id or "gemini-2.5-flash").strip()
                while True:
                    cleaned = False
                    for pfx in ("gemini/", "google/", "googleai/", "models/"):
                        if target_model.lower().startswith(pfx):
                            target_model = target_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                if not target_model:
                    target_model = "gemini-2.5-flash"

                # Step 1: Probe GET /v1beta/models/{target_model}
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(target_model)}?key={key}"
                req = urllib.request.Request(url, headers=ua)
                try:
                    with urllib.request.urlopen(req, timeout=15) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        if response.status == 200:
                            parsed = json.loads(raw)
                            methods = parsed.get("supportedGenerationMethods") or []
                            if not methods or "generateContent" in methods:
                                return _success(f"Gemini model '{target_model}' verified and ready for generation.")
                            else:
                                return _failure(f"Model '{target_model}' exists but does not support generation (supports: {', '.join(methods)}).")
                except urllib.error.HTTPError as get_err:
                    if get_err.code in (401, 403):
                        return _failure(_err_text(get_err))
                except Exception:
                    pass

                # Step 2: Fallback to active generateContent POST probe
                gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(target_model)}:generateContent?key={key}"
                gen_body = json.dumps({
                    "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                    "generationConfig": {"maxOutputTokens": 10},
                }).encode("utf-8")
                gen_req = urllib.request.Request(gen_url, data=gen_body, method="POST", headers={"Content-Type": "application/json", **ua})
                try:
                    with urllib.request.urlopen(gen_req, timeout=20) as gen_resp:
                        gen_raw = gen_resp.read().decode("utf-8", errors="replace")
                        if gen_resp.status == 200:
                            return _success(f"Gemini model '{target_model}' verified successfully.")
                        return _failure(_clean(gen_resp.status, gen_raw))
                except urllib.error.HTTPError as gen_err:
                    return _failure(_err_text(gen_err))

            elif provider in ("vertex_ai", "vx", "vertex"):
                target_model = (model_id or "gemini-2.5-flash").strip()
                while True:
                    cleaned = False
                    for pfx in ("vx/", "vertex_ai/", "vertex/", "publishers/google/models/", "models/"):
                        if target_model.lower().startswith(pfx):
                            target_model = target_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                if not target_model:
                    target_model = "gemini-2.5-flash"

                vx_headers = dict(ua)
                if key.startswith("ya29."):
                    vx_headers["Authorization"] = f"Bearer {key}"
                    vx_base = "https://aiplatform.googleapis.com/v1/publishers/google/models"
                    q_suffix = ""
                else:
                    vx_base = "https://aiplatform.googleapis.com/v1/publishers/google/models"
                    q_suffix = f"?key={urllib.parse.quote(key)}" if key else ""

                vx_url = f"{vx_base}/{urllib.parse.quote(target_model)}{q_suffix}"
                vx_req = urllib.request.Request(vx_url, headers=vx_headers)
                try:
                    with urllib.request.urlopen(vx_req, timeout=15) as vx_resp:
                        if vx_resp.status == 200:
                            return _success(f"Vertex AI model '{target_model}' verified successfully.")
                except urllib.error.HTTPError as vx_err:
                    if vx_err.code in (401, 403):
                        return _failure(_err_text(vx_err))
                except Exception:
                    pass

                # Step 2: Fallback generateContent for Vertex
                vx_gen_url = f"{vx_base}/{urllib.parse.quote(target_model)}:generateContent{q_suffix}"
                vx_gen_body = json.dumps({
                    "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                    "generationConfig": {"maxOutputTokens": 10},
                }).encode("utf-8")
                vx_gen_headers = {"Content-Type": "application/json", **vx_headers}
                vx_gen_req = urllib.request.Request(vx_gen_url, data=vx_gen_body, method="POST", headers=vx_gen_headers)
                try:
                    with urllib.request.urlopen(vx_gen_req, timeout=20) as vx_gen_resp:
                        if vx_gen_resp.status == 200:
                            return _success(f"Vertex AI model '{target_model}' verified successfully.")
                        return _failure(_clean(vx_gen_resp.status, vx_gen_resp.read().decode("utf-8", errors="replace")))
                except urllib.error.HTTPError as vx_gen_err:
                    return _failure(_err_text(vx_gen_err))

            elif provider in ("anthropic", "claude"):
                url = "https://api.anthropic.com/v1/messages"
                target_model = (model_id or "claude-3-5-haiku-20241022").strip()
                while True:
                    cleaned = False
                    for pfx in ("anthropic/", "claude/"):
                        if target_model.lower().startswith(pfx):
                            target_model = target_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                body = json.dumps({
                    "model": target_model,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hi"}]
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=body, method="POST",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", **ua})
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        status = response.status
                        if status != 200:
                            return _failure(_clean(status, raw))
                        return _success(f"Anthropic model '{target_model}' verified successfully.")
                except urllib.error.HTTPError as ant_err:
                    return _failure(_err_text(ant_err))

            else:
                # Standard OpenAI-compatible format across all providers
                base = "https://api.openai.com/v1"
                headers = {"Content-Type": "application/json", **ua}
                if key:
                    headers["Authorization"] = f"Bearer {key}"

                if provider == "groq":
                    base = "https://api.groq.com/openai/v1"
                elif provider in ("deepseek", "deepseek_ai"):
                    base = "https://api.deepseek.com/v1"
                elif provider in ("mistral", "mistral_ai"):
                    base = "https://api.mistral.ai/v1"
                elif provider == "openrouter":
                    base = "https://openrouter.ai/api/v1"
                    headers["HTTP-Referer"] = "http://localhost:8991"
                    headers["X-Title"] = "Voice Flow"
                elif provider in ("together", "together_ai"):
                    base = "https://api.together.xyz/v1"
                elif provider in ("nvidia_nim", "nim", "nvidia"):
                    base = "https://integrate.api.nvidia.com/v1"
                elif provider in ("opencode_zen", "zen"):
                    base = "https://opencode.ai/zen/v1"
                elif provider == "ollama":
                    base = base_url or "http://127.0.0.1:11434/v1"
                elif provider in ("lm_studio", "lmstudio"):
                    base = base_url or "http://127.0.0.1:1234/v1"
                elif provider in ("llama_cpp", "llamacpp"):
                    base = base_url or "http://127.0.0.1:8080/v1"
                elif provider == "cloudflare":
                    cf_account = ""
                    try:
                        for c in video_flow_provider_service.list_connections("cloudflare"):
                            m = c.get("metadata") or {}
                            if m.get("account_id"):
                                cf_account = m["account_id"]
                                break
                    except Exception:
                        pass
                    if cf_account:
                        base = f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/v1"
                    else:
                        base = "https://api.cloudflare.com/client/v4/ai/v1"

                # Respect user-configured base_url if explicitly specified
                if base_url:
                    base = base_url

                endpoint = base if base.endswith("/chat/completions") else f"{base.rstrip('/')}/chat/completions"

                target_model = model_id.strip()
                if provider == "openrouter":
                    while target_model.lower().startswith("openrouter/"):
                        target_model = target_model[len("openrouter/"):].strip()
                elif provider in ("together", "together_ai"):
                    while target_model.lower().startswith(("together/", "together_ai/")):
                        pfx = "together_ai/" if target_model.lower().startswith("together_ai/") else "together/"
                        target_model = target_model[len(pfx):].strip()
                elif provider in ("nvidia_nim", "nim", "nvidia"):
                    while target_model.lower().startswith(("nvidia_nim/", "nim/")):
                        pfx = "nvidia_nim/" if target_model.lower().startswith("nvidia_nim/") else "nim/"
                        target_model = target_model[len(pfx):].strip()
                elif provider == "cloudflare":
                    while target_model.lower().startswith(("cloudflare/", "cf/")):
                        pfx = "cloudflare/" if target_model.lower().startswith("cloudflare/") else "cf/"
                        target_model = target_model[len(pfx):].strip()
                else:
                    pfx = f"{provider}/".lower()
                    while target_model.lower().startswith(pfx):
                        target_model = target_model[len(pfx):].strip()
                    for alias, canonical in PROVIDER_ALIASES.items():
                        if canonical == provider:
                            if provider in ("nvidia_nim", "nim", "nvidia") and alias == "nvidia":
                                continue
                            a_pfx = f"{alias}/".lower()
                            while target_model.lower().startswith(a_pfx):
                                target_model = target_model[len(a_pfx):].strip()

                is_reasoning_model = bool(
                    re.search(r"^(o[1-9]|gpt-5|chatgpt)", target_model, re.I)
                    or re.search(r"(?:^|/)(o1|o3|o4)(?:-|$)", target_model, re.I)
                    or "reasoning" in target_model.lower()
                    or "r1" in target_model.lower()
                )

                payload_dict = {
                    "model": target_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                }
                if is_reasoning_model or provider == "openai":
                    payload_dict["max_completion_tokens"] = 100
                else:
                    payload_dict["max_tokens"] = 64

                def _send_chat_req(p_dict):
                    body = json.dumps(p_dict).encode("utf-8")
                    req = urllib.request.Request(endpoint, data=body, method="POST", headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        status = response.status
                    return status, raw

                try:
                    status, raw = _send_chat_req(payload_dict)
                except urllib.error.HTTPError as chat_err:
                    err_raw = ""
                    try:
                        err_raw = chat_err.read().decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    err_lower = err_raw.lower()
                    retried = False
                    if chat_err.code == 400:
                        # Case 1: Provider rejected max_tokens (e.g. OpenAI o1/o3 reasoning model)
                        if "max_tokens" in payload_dict and (
                            "max_completion_tokens" in err_lower
                            or "max_tokens" in err_lower
                            or "unsupported_parameter" in err_lower
                            or "unsupported parameter" in err_lower
                            or "extra inputs are not permitted" in err_lower
                        ):
                            payload_dict.pop("max_tokens", None)
                            payload_dict["max_completion_tokens"] = 100
                            retried = True
                        # Case 2: Provider rejected max_completion_tokens (e.g. gpt-3.5 or legacy endpoint)
                        elif "max_completion_tokens" in payload_dict and (
                            "max_completion_tokens" in err_lower
                            or "max_tokens" in err_lower
                            or "unrecognized parameter" in err_lower
                            or "unknown parameter" in err_lower
                            or "extra inputs are not permitted" in err_lower
                            or "unexpected keyword" in err_lower
                        ):
                            payload_dict.pop("max_completion_tokens", None)
                            payload_dict["max_tokens"] = 64
                            retried = True
                        # Case 3: Provider rejected stream parameter
                        elif "stream" in payload_dict and "stream" in err_lower:
                            payload_dict.pop("stream", None)
                            retried = True

                    if retried:
                        try:
                            status, raw = _send_chat_req(payload_dict)
                        except urllib.error.HTTPError as retry_err:
                            err2_raw = ""
                            try:
                                err2_raw = retry_err.read().decode("utf-8", errors="replace")
                            except Exception:
                                pass
                            if retry_err.code == 400 and "token" in err2_raw.lower():
                                p3 = dict(payload_dict)
                                p3.pop("max_tokens", None)
                                p3.pop("max_completion_tokens", None)
                                try:
                                    status, raw = _send_chat_req(p3)
                                except urllib.error.HTTPError as err3:
                                    return _failure(_err_text(err3))
                            else:
                                return _failure(_err_text(retry_err))
                    else:
                        return _failure(_clean(chat_err.code, err_raw))

                if status != 200:
                    return _failure(_clean(status, raw))
                parsed = None
                try:
                    parsed = json.loads(raw)
                except Exception:
                    pass
                choices = (parsed or {}).get("choices") or []
                if not choices and not (parsed or {}).get("id"):
                    return _failure("Provider returned no completion choices for this model.")
                first_choice = choices[0] if choices else {}
                content = str((first_choice.get("message") or {}).get("content") or "").strip()
                has_reasoning = bool(
                    (first_choice.get("message") or {}).get("reasoning_content")
                    or (first_choice.get("message") or {}).get("reasoning")
                    or (first_choice.get("message") or {}).get("thinking")
                    or ((parsed or {}).get("usage") or {}).get("completion_tokens", 0) > 0
                    or ((parsed or {}).get("usage") or {}).get("total_tokens", 0) > 0
                )
                finish_reason = str(first_choice.get("finish_reason") or "").lower()
                if not content and not has_reasoning and finish_reason not in ("length", "stop", "completed"):
                    return _failure("Model returned empty response content.")
                return _success(f"{provider.capitalize()} model '{target_model}' verified successfully.")

        except urllib.error.HTTPError as e:
            return _failure(_err_text(e))
        except Exception as e:
            err_msg = str(e)
            if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                return _failure("Request timed out. Check internet connection or model availability.")
            return _failure(f"Connection failed: {err_msg}")

    def verify_provider_model(self, provider: str, key: str, model_id: str) -> dict:
        """Live per-model probe: verifies the SPECIFIC model works with this key.

        Unlike verify_api_key (which only validates the key against a generic
        provider endpoint), this calls the actual model so a nonexistent,
        renamed, or non-generation model never reports green.
        """
        ua_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        model_id = (model_id or "").strip()
        provider = (provider or "").lower().strip()
        provider = PROVIDER_ALIASES.get(provider, provider)
        model_id = strip_redundant_model_prefix(provider, model_id)

        def _http_error_text(http_err) -> str:
            try:
                body = http_err.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                err = data.get("error")
                msg = None
                if isinstance(err, dict):
                    msg = err.get("message")
                elif isinstance(err, str):
                    msg = err
                if not msg and isinstance(data.get("detail"), dict):
                    msg = data["detail"].get("message")
                if not msg:
                    msg = data.get("message") or data.get("detail")
                if msg:
                    return f"HTTP {http_err.code}: {msg}"
                return f"HTTP {http_err.code}: {body[:200]}"
            except Exception:
                return f"HTTP {http_err.code}: {http_err.reason}"

        try:
            if provider == "gemini":
                if not model_id:
                    return self.verify_api_key(provider, key)
                clean_model = model_id
                while True:
                    cleaned = False
                    for pfx in ("gemini/", "google/", "googleai/", "models/"):
                        if clean_model.lower().startswith(pfx):
                            clean_model = clean_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                if not clean_model:
                    clean_model = "gemini-2.5-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(clean_model)}?key={key}"
                req = urllib.request.Request(url, headers=ua_headers)
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        if response.status == 200:
                            meta = json.loads(response.read().decode("utf-8", errors="replace"))
                            methods = meta.get("supportedGenerationMethods") or []
                            if methods and "generateContent" not in methods:
                                return {"success": False, "error": f"Model '{model_id}' exists but does not support text generation (supports: {', '.join(methods)})."}
                            return {"success": True, "error": None}
                except urllib.error.HTTPError as gemini_err:
                    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(clean_model)}:generateContent?key={key}"
                    gen_body = json.dumps({"contents": [{"parts": [{"text": "hi"}]}]}).encode("utf-8")
                    gen_req = urllib.request.Request(gen_url, data=gen_body, headers={"Content-Type": "application/json", **ua_headers}, method="POST")
                    try:
                        with urllib.request.urlopen(gen_req, timeout=30) as gen_resp:
                            if gen_resp.status == 200:
                                return {"success": True, "error": None}
                    except urllib.error.HTTPError as fallback_err:
                        raise fallback_err from gemini_err
                    raise gemini_err
            elif provider in ("openai", "groq", "deepseek", "mistral", "openrouter", "together", "together_ai", "nvidia", "nvidia_nim"):
                if not model_id:
                    return self.verify_api_key(provider, key)
                base = "https://api.openai.com/v1"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **ua_headers}
                if provider == "groq":
                    base = "https://api.groq.com/openai/v1"
                elif provider in ("deepseek", "deepseek_ai"):
                    base = "https://api.deepseek.com/v1"
                elif provider in ("mistral", "mistral_ai"):
                    base = "https://api.mistral.ai/v1"
                elif provider == "openrouter":
                    base = "https://openrouter.ai/api/v1"
                    headers["HTTP-Referer"] = "http://localhost:8991"
                    headers["X-Title"] = "Voice Flow"
                elif provider in ("together", "together_ai"):
                    base = "https://api.together.xyz/v1"
                elif provider in ("nvidia", "nvidia_nim"):
                    base = "https://integrate.api.nvidia.com/v1"

                target_model = model_id.strip()
                if provider == "openrouter":
                    while target_model.lower().startswith("openrouter/"):
                        target_model = target_model[len("openrouter/"):].strip()
                elif provider in ("together", "together_ai"):
                    while target_model.lower().startswith(("together/", "together_ai/")):
                        pfx = "together_ai/" if target_model.lower().startswith("together_ai/") else "together/"
                        target_model = target_model[len(pfx):].strip()
                else:
                    pfx = f"{provider}/".lower()
                    while target_model.lower().startswith(pfx):
                        target_model = target_model[len(pfx):].strip()

                is_reasoning_model = bool(
                    re.search(r"^(o[1-9]|gpt-5|chatgpt)", target_model, re.I)
                    or re.search(r"(?:^|/)(o1|o3|o4)(?:-|$)", target_model, re.I)
                    or "reasoning" in target_model.lower()
                    or "r1" in target_model.lower()
                )
                payload_dict = {
                    "model": target_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                }
                if is_reasoning_model or provider == "openai":
                    payload_dict["max_completion_tokens"] = 100
                else:
                    payload_dict["max_tokens"] = 64

                def _send_probe(p_dict):
                    body = json.dumps(p_dict).encode("utf-8")
                    req = urllib.request.Request(
                        f"{base}/chat/completions", data=body, method="POST",
                        headers=headers,
                    )
                    with urllib.request.urlopen(req, timeout=20) as response:
                        return response.status, response.read().decode("utf-8", errors="replace")

                try:
                    status, _ = _send_probe(payload_dict)
                    if status == 200:
                        return {"success": True, "error": None}
                except urllib.error.HTTPError as chat_err:
                    err_raw = ""
                    try:
                        err_raw = chat_err.read().decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    err_lower = err_raw.lower()
                    retried = False
                    if chat_err.code == 400:
                        if "max_tokens" in payload_dict and (
                            "max_completion_tokens" in err_lower
                            or "max_tokens" in err_lower
                            or "unsupported_parameter" in err_lower
                            or "unsupported parameter" in err_lower
                            or "extra inputs are not permitted" in err_lower
                        ):
                            payload_dict.pop("max_tokens", None)
                            payload_dict["max_completion_tokens"] = 100
                            retried = True
                        elif "max_completion_tokens" in payload_dict and (
                            "max_completion_tokens" in err_lower
                            or "max_tokens" in err_lower
                            or "unrecognized parameter" in err_lower
                            or "unknown parameter" in err_lower
                            or "extra inputs are not permitted" in err_lower
                            or "unexpected keyword" in err_lower
                        ):
                            payload_dict.pop("max_completion_tokens", None)
                            payload_dict["max_tokens"] = 64
                            retried = True
                    if retried:
                        status, _ = _send_probe(payload_dict)
                        if status == 200:
                            return {"success": True, "error": None}
                    raise chat_err
            elif provider in ("anthropic", "claude"):
                if not model_id:
                    return self.verify_api_key(provider, key)
                target_model = model_id.strip()
                while True:
                    cleaned = False
                    for pfx in ("anthropic/", "claude/"):
                        if target_model.lower().startswith(pfx):
                            target_model = target_model[len(pfx):].strip()
                            cleaned = True
                    if not cleaned:
                        break
                body = json.dumps({
                    "model": target_model,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hi"}],
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=body, method="POST",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", **ua_headers},
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    if response.status == 200:
                        return {"success": True, "error": None}
            elif provider == "elevenlabs":
                found = None
                for list_url in ("https://api.elevenlabs.io/v1/models", "https://api.elevenlabs.io/v1/voices"):
                    req = urllib.request.Request(list_url, headers={"xi-api-key": key, **ua_headers})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status != 200:
                            continue
                        items = json.loads(response.read().decode("utf-8", errors="replace"))
                        if isinstance(items, dict):
                            items = items.get("models") or items.get("voices") or []
                        for item in items or []:
                            if not isinstance(item, dict):
                                continue
                            for id_field in ("model_id", "voice_id", "name"):
                                val = str(item.get(id_field, "")).strip().lower()
                                if val and val == model_id.lower():
                                    found = True
                                    break
                            if found:
                                break
                    if found:
                        break
                if found:
                    return {"success": True, "error": None}
                if not model_id:
                    return {"success": True, "error": None}
                return {"success": False, "error": f"Model or voice '{model_id}' is not available on your ElevenLabs account."}
            elif provider == "deepgram":
                url = "https://api.deepgram.com/v1/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Token {key}", **ua_headers})
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        if not model_id:
                            return {"success": True, "error": None}
                        data = json.loads(response.read().decode("utf-8", errors="replace"))
                        names = set()
                        for m in (data.get("stt_models") or []) + (data.get("tts_models") or []):
                            if isinstance(m, dict):
                                names.add(str(m.get("name", "")).lower())
                                names.add(str(m.get("canonical_name", "")).lower())
                        names.discard("")
                        if model_id.lower() in names or any(model_id.lower() in n for n in names):
                            return {"success": True, "error": None}
                        return {"success": False, "error": f"Model '{model_id}' was not found in your Deepgram model list."}
            else:
                return self.verify_api_key(provider, key)
        except urllib.error.HTTPError as e:
            return {"success": False, "error": _http_error_text(e)}
        except Exception as e:
            return {"success": False, "error": f"Connection failed: {e}. Check your internet and try again."}

        return {"success": False, "error": f"Could not verify model '{model_id}'."}

    def verify_tts_api_key(self, provider: str, key: str, region: str = "eastus") -> dict:
        """Perform live test against TTS Provider API endpoints."""
        if not key:
            return {"status": "Error: API key cannot be empty", "valid": False}

        ua_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            if provider == "google":
                url = f"https://texttospeech.googleapis.com/v1/voices?key={key}&languageCode=en-US"
                req = urllib.request.Request(url, headers=ua_headers)
                try:
                    with urllib.request.urlopen(req, timeout=8) as response:
                        if response.status == 200:
                            return {"status": "Connected (200 OK)", "valid": True}
                except urllib.error.HTTPError:
                    alt_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    alt_req = urllib.request.Request(alt_url, headers=ua_headers)
                    with urllib.request.urlopen(alt_req, timeout=8) as response:
                        if response.status == 200:
                            return {"status": "Connected via Gemini (200 OK)", "valid": True}
                    raise

            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                req = urllib.request.Request(url, headers=ua_headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "azure":
                url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"
                headers = {"Ocp-Apim-Subscription-Key": key, **ua_headers}
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "fish":
                url = "https://api.fish.audio/model"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "nvidia":
                url = "https://integrate.api.nvidia.com/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "elevenlabs":
                url = "https://api.elevenlabs.io/v1/voices"
                headers = {"xi-api-key": key, **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "deepgram":
                url = "https://api.deepgram.com/v1/projects"
                headers = {"Authorization": f"Token {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"status": "Connected (200 OK)", "valid": True}

            elif provider.startswith("custom-"):
                entry = next((cp for cp in storage.get_audio_flow_custom_providers() if cp.get("id") == provider), None)
                if entry:
                    first_m = ((entry.get("models") or [{}])[0].get("model_id") or "")
                    res = self._probe_custom_endpoint_direct(
                        base_url=str(entry.get("base_url") or ""),
                        api_key=key,
                        api_format=str(entry.get("api_format") or "openai").lower(),
                        model_id=first_m,
                        kind="tts",
                        headers=entry.get("headers"),
                    )
                    valid = bool(res.get("success"))
                    msg = "Connected (200 OK)" if valid else (res.get("error") or "Verification failed")
                    return {"status": msg, "valid": valid}
                valid, msg = validate_provider_key(provider, key)
                return {"status": msg if valid else (msg or "Validation failed"), "valid": valid}

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"status": "Invalid API key — please check your key from the provider dashboard", "valid": False}
            if e.code == 403:
                return {"status": "API key lacks required permissions", "valid": False}
            if e.code == 429:
                return {"status": "Rate limited — try again in a moment", "valid": False}
            if e.code >= 500:
                return {"status": "Provider server error — try again later", "valid": False}
            return {"status": f"HTTP {e.code}: {e.reason}", "valid": False}
        except urllib.error.URLError:
            return {"status": "Cannot reach provider — check your internet connection", "valid": False}
        except Exception:
            return {"status": "Verification failed — check your key and try again", "valid": False}

        return {"status": "Error: Verification failed", "valid": False}

    @staticmethod
    def _check_key_format(provider: str, key: str) -> str | None:
        """Quick format checks to reject obviously wrong keys."""
        if key.startswith("hf_") and provider != "huggingface":
            return f"This looks like a HuggingFace token (starts with 'hf_'). Please enter a valid {provider.capitalize()} API key instead."

        if provider == "gemini" and key.startswith("sk-"):
            return "This looks like an OpenAI key (starts with 'sk-'). Please enter a Google Gemini API key from https://aistudio.google.com/apikey"
        if provider == "google" and key.startswith("sk-"):
            return "This looks like an OpenAI key (starts with 'sk-'). Please enter a Google Cloud TTS API key from https://console.cloud.google.com/apis/credentials"
        if provider == "openai" and not key.startswith("sk-"):
            return "OpenAI API keys should start with 'sk-'. Get one from https://platform.openai.com/api-keys"
        if provider == "groq" and not key.startswith("gsk_"):
            return "Groq API keys should start with 'gsk_'. Get one from https://console.groq.com/keys"
        if provider in ("nvidia", "nvidia_nim") and not key.startswith("nvapi-"):
            return "NVIDIA API keys should start with 'nvapi-'. Get one from https://build.nvidia.com/settings/api-keys"

        if len(key) < 20:
            return f"API key is too short ({len(key)} chars). Valid {provider.capitalize()} keys are typically 30+ characters."

        return None

    def send_video_thumb(self, video_id: str) -> None:
        """Serve a cached first-frame JPEG thumbnail for a completed video."""
        import subprocess
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", video_id or ""):
            self.send_error(404, "Video not found")
            return
        try:
            job = get_video_flow_service().get(video_id)
            path = None
            if job is not None:
                meta = job.meta or {}
                candidates = [meta.get("output_path"), meta.get("video_path")]
                if isinstance(meta.get("artifact"), dict):
                    candidates.append(meta["artifact"].get("output_path"))
                if isinstance(meta.get("provenance"), dict):
                    candidates.append(meta["provenance"].get("output_path"))
                for cand in candidates:
                    if cand:
                        cand_path = Path(str(cand))
                        if cand_path.is_file():
                            path = cand_path
                            break
        except Exception:
            path = None
        if not path:
            self.send_error(404, "Video not found")
            return
        # Confine thumbnails to the app data dir: job meta paths are
        # service-written, but a stale/foreign row must never let this
        # endpoint read or write outside the data dir.
        try:
            data_root = data_dir().resolve()
            resolved = path.resolve()
            if data_root != resolved and data_root not in resolved.parents:
                self.send_error(404, "Video not found")
                return
        except OSError:
            self.send_error(404, "Video not found")
            return
        thumb = path.parent / "thumb.jpg"
        if not thumb.is_file():
            ffmpeg = None
            try:
                from voice_flow.runtime_env import ffmpeg_executable
                ffmpeg = ffmpeg_executable()
            except Exception:
                ffmpeg = None
            if not ffmpeg:
                import shutil
                ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                self.send_error(404, "Thumbnail unavailable")
                return
            try:
                subprocess.run(
                    [str(ffmpeg), "-y", "-loglevel", "error", "-ss", "0", "-i", str(path),
                     "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(thumb)],
                    timeout=25,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                self.send_error(404, "Thumbnail unavailable")
                return
        if not thumb.is_file():
            self.send_error(404, "Thumbnail unavailable")
            return
        body = thumb.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def send_video_file(self, video_id: str, *, download: bool = False, title: str | None = None) -> None:
        path = video_flow_service.file_for(video_id)
        if not path:
            self.send_error(404, "Video not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
        size = path.stat().st_size
        start = 0
        end = max(0, size - 1)
        status = 200
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes=") and "," not in range_header:
            try:
                raw_start, raw_end = range_header.removeprefix("bytes=").split("-", 1)
                if raw_start:
                    start = int(raw_start)
                if raw_end:
                    end = min(end, int(raw_end))
                if start < 0 or start > end or start >= size:
                    raise ValueError
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        if download:
            from voice_flow.audio_summary_player import safe_media_filename
            vid_title = (title or "").strip()
            download_name = safe_media_filename(vid_title or path.stem, default=f"video_{video_id}", ext=".mp4")
            quoted_name = urllib.parse.quote(download_name)
            ascii_name = re.sub(r"[^\x20-\x7E]", "_", download_name)
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted_name}')
        else:
            self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)
    def _serve_oauth_callback(self) -> None:
        """Serve the OAuth popup/browser landing page and proactively exchange code server-side."""
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]

        if code and state and not error:
            try:
                from voice_flow.video_flow_oauth import complete_pkce_flow, load_pending
                provider_id = str(video_flow_provider_service.get_setting(f"oauth_pending_state:{state}", "") or "").strip().lower()
                if not provider_id:
                    for p in ("antigravity", "gemini", "openai_codex", "claude_code"):
                        p_pending = load_pending(video_flow_provider_service, p)
                        if isinstance(p_pending, dict) and p_pending.get("state") == state:
                            provider_id = p
                            break
                if not provider_id:
                    provider_id = "antigravity"

                complete_pkce_flow(
                    video_flow_provider_service,
                    provider_id,
                    code,
                    state=state,
                    redirect_uri=f"http://127.0.0.1:{self._server_port()}/callback",
                )
                _focus_app_window()
            except Exception:
                pass

        def _js_literal(value):
            return json.dumps(value).replace("</", "<\\/")
        body = (
            OAUTH_CALLBACK_PAGE
            .replace("__OAUTH_CODE__", _js_literal(code))
            .replace("__OAUTH_STATE__", _js_literal(state))
            .replace("__OAUTH_ERROR__", _js_literal(error))
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_response(self, data: any, status: int = 200) -> None:
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            if self.headers and str(self.headers.get("Connection", "")).lower() == "close":
                self.send_header("Connection", "close")
                self.close_connection = True
            origin = self.headers.get("Origin") if self.headers else None
            if origin and origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(content)
            self.wfile.flush()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass
        except Exception:
            pass



def _complete_video_flow_oauth(service, provider_id, code, state=None, redirect_uri=None):
    """9Router-style client_secret token exchange, resolved via this module.

    State is validated against the pending session BEFORE any network call
    (wrong state -> "OAuth state mismatch" without touching Google). All
    HTTP goes through this module's _http_json / load_code_assist_project
    names so tests can monkeypatch api_server._http_json.
    """
    from voice_flow.video_flow_oauth import (
        OAuthError as _OAuthError,
        clear_pending as _clear_pending,
        decrypt_token as _decrypt_unused,
        encrypt_token as _encrypt_token,
        load_pending as _load_pending,
        oauth_config as _oauth_config,
    )
    del _decrypt_unused
    config = _oauth_config(provider_id)
    pending = _load_pending(service, provider_id)
    if not pending or not isinstance(pending, dict) or str(pending.get("state") or "") != str(state or ""):
        raise _OAuthError("OAuth state mismatch. Start the sign-in flow again.")
    verifier = str(pending.get("verifier") or "")
    saved_redirect = str(pending.get("redirect_uri") or "")
    target_redirect = redirect_uri or saved_redirect or f"http://127.0.0.1:{PORT}/callback"

    token_url = config.token_url or "https://oauth2.googleapis.com/token"
    client_id = config.client_id or ANTIGRAVITY_CLIENT_ID
    client_secret = config.client_secret or ANTIGRAVITY_CLIENT_SECRET
    payload = {
        "client_id": client_id,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": target_redirect,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if config.pkce and verifier:
        payload["code_verifier"] = verifier

    token_resp = _http_json(token_url, data=payload)
    if not isinstance(token_resp, dict):
        token_resp = {}
    if token_resp.get("error"):
        _clear_pending(service, provider_id)
        raise _OAuthError(f"OAuth token exchange failed: {token_resp.get('error_description') or token_resp.get('error')}")
    access_token = str(token_resp.get("access_token") or "")
    refresh_token = str(token_resp.get("refresh_token") or "")
    id_token = str(token_resp.get("id_token") or "")
    expires_in = int(token_resp.get("expires_in") or 3600)
    if not access_token:
        _clear_pending(service, provider_id)
        raise _OAuthError("OAuth exchange returned no access token.")

    user_email = ""
    if id_token and "." in id_token:
        try:
            import base64 as _b64
            import json as _json
            parts = id_token.split(".")
            claims = _json.loads(_b64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            user_email = claims.get("email") or ""
        except Exception:
            pass
    if not user_email:
        try:
            userinfo = _http_json(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            ) or {}
            user_email = userinfo.get("email") or ""
        except Exception:
            pass

    project_id = load_code_assist_project(access_token) if provider_id == "antigravity" else ""
    account_id = user_email or f"{provider_id}_oauth_{int(time.time())}"
    provider_label = "Antigravity" if provider_id == "antigravity" else str(provider_id)
    name = f"{provider_label} {account_id}" if account_id else f"{provider_label} account"
    metadata = {"source": "oauth"}
    if project_id:
        metadata["project_id"] = project_id

    connection = None
    try:
        for existing in service.list_connections(provider_id):
            if str(existing.get("account_id") or "").strip() == account_id and account_id:
                changes = {
                    "name": name[:100],
                    "secret": _encrypt_token(service, access_token) if access_token else "",
                    "status": "active",
                    "metadata": metadata,
                }
                if refresh_token:
                    changes["refresh_token"] = _encrypt_token(service, refresh_token)
                if expires_in:
                    changes["expires_at"] = str(time.time() + int(expires_in))
                service.update_connection(int(existing["id"]), **changes)
                connection = service.get_connection(int(existing["id"])) or {}
                break
    except Exception:
        connection = None
    if connection is None:
        try:
            expires_at = str(time.time() + int(expires_in)) if expires_in else ""
        except Exception:
            expires_at = ""
        created = service.add_connection(
            provider_id,
            name=name[:100],
            secret=_encrypt_token(service, access_token) if access_token else "",
            account_id=account_id,
            refresh_token=_encrypt_token(service, refresh_token) if refresh_token else "",
            expires_at=expires_at,
            metadata=metadata,
        )
        conn_id = int(created["id"]) if isinstance(created, dict) and created.get("id") else None
        if conn_id is not None and hasattr(service, "update_connection"):
            try:
                service.update_connection(conn_id, status="active")
            except Exception:
                pass
        connection = service.get_connection(int(conn_id)) if conn_id is not None else None
        if connection is None:
            connection = created if isinstance(created, dict) else {}

    _clear_pending(service, provider_id)
    return {
        "success": True,
        "provider": provider_id,
        "email": user_email or account_id,
        "account_id": account_id,
        "connection_id": connection.get("id") if isinstance(connection, dict) else None,
        "connection": connection,
        "project_id": project_id,
        "status": "active",
    }


def _focus_app_window() -> None:
    """Bring the Voice Flow desktop window forward after OAuth completes."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "AI Productivity Flow")
        if not hwnd:
            hwnd = user32.FindWindowW(None, "Voice Flow")
        if not hwnd:
            hwnd = user32.FindWindowW(None, "Voice Flow - AI Speech Desktop App")
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _mask_secret(secret: str) -> str:
    if not secret or len(secret) < 8:
        return "********"
    return secret[:3] + "..." + secret[-4:]


def _shim_video(job) -> dict:
    """Map internal JobV3 record to the original public shape expected by the frontend."""
    meta = job.meta or {}
    state_str = str(job.state or "processing").lower()
    if state_str in ("complete", "completed", "ready"):
        public_status = "completed"
    elif state_str == "failed":
        public_status = "failed"
    elif state_str == "cancelled":
        public_status = "cancelled"
    else:
        public_status = "processing"
    playable = public_status == "completed" or job.progress >= 100.0
    provenance = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else None
    final_engine = provenance.get("final_engine") if provenance else None
    return {
        "id": job.job_id,
        "title": meta.get("title") or job.job_id,
        "status": public_status,
        "stage": job.message or public_status,
        "progress": int(job.progress),
        "playable": playable,
        "mode": meta.get("mode", "summary"),
        "engine_version": final_engine or "v3-code2video",
        "created_at": getattr(job, "created_at", None) or 0.0,
        "duration_sec": meta.get("duration_sec", meta.get("duration_seconds", 0.0)),
        "provenance": meta.get("provenance"),
        "timings": meta.get("timings") or getattr(job, "timings", None),
        # Honest-fallback context: the requested engine could not be used and a
        # local engine rendered instead. None on normal jobs.
        "fallback_reason": meta.get("fallback_reason"),
        "fallback_requested_engine": meta.get("fallback_requested_engine"),
        "fallback_error": meta.get("fallback_error"),
        "meta": {key: meta.get(key) for key in ("timings", "timing") if meta.get(key) is not None},
        "view_url": f"/api/video-flow/videos/file?id={job.job_id}",
        "download_url": f"/api/video-flow/videos/file?id={job.job_id}&download=1" + (f"&title={urllib.parse.quote(str(meta.get('title') or ''))}" if meta.get("title") else ""),
        "export_status": "exported" if playable else "not_requested",
        "error": meta.get("error_code", "") if public_status == "failed" else "",
    }


def _new_custom_item_id(prefix: str) -> str:
    """Create a stable opaque id for custom keys/models.

    Positional ids such as c-1 become ambiguous after deleting a middle item and
    adding another one. Opaque ids survive reorder/delete cycles and prevent an
    edit action from targeting the wrong credential.
    """
    clean_prefix = "m" if prefix == "m" else "c"
    return f"{clean_prefix}-{secrets.token_hex(8)}"


def _model_is_user_configured(model_id: str) -> bool:
    """Whether ``model_id`` is a model the user added to a provider list.

    The Video Flow catalog only lists models belonging to *connected*
    providers, so a model added through the provider-model endpoints (or a
    custom provider's model) would otherwise be rejected as unknown when the
    user selects it.
    """
    ref = str(model_id or "").strip()
    if not ref or "/" not in ref:
        return False
    provider, _, model = ref.partition("/")
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        return False
    try:
        for row in storage.get_provider_models(provider):
            if str(row.get("model_id") or "").strip() == model:
                return True
    except Exception:
        pass
    try:
        for cp in storage.get_video_flow_custom_providers():
            if str(cp.get("id") or "").strip().lower() != provider:
                continue
            for m in cp.get("models") or []:
                if str(m.get("model_id") or "").strip() == model:
                    return True
    except Exception:
        pass
    return False


def _public_custom_providers(providers, reveal_headers: bool = False):
    """Mask custom-provider credentials and secret-bearing headers.

    ``reveal_headers`` is used only by the add/update responses, which echo
    back the values the caller just submitted; list responses always mask.
    """
    public = []
    for cp in providers or []:
        entry = dict(cp) if isinstance(cp, dict) else {}
        keys = entry.get("api_keys") if isinstance(entry.get("api_keys"), list) else []
        entry["has_secret"] = bool(entry.get("api_key")) or any(
            bool(k.get("key")) for k in keys if isinstance(k, dict))
        entry["api_key"] = ""
        entry["api_keys"] = [{**k, "key": ""} for k in keys if isinstance(k, dict)]
        raw_headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
        sensitive_header = re.compile(r"authorization|api[-_]?key|token|secret|cookie", re.IGNORECASE)
        entry["has_secret_headers"] = any(
            bool(value) and sensitive_header.search(str(name))
            for name, value in raw_headers.items()
        )
        entry["headers"] = (
            {str(name): value for name, value in raw_headers.items()}
            if reveal_headers else
            {str(name): ("" if sensitive_header.search(str(name)) else value)
             for name, value in raw_headers.items()}
        )
        public.append(entry)
    return public


def _find_conn_index(conns: list[dict], cid_raw: Any) -> int:
    if not conns:
        return -1
    cid_str = str(cid_raw or "").strip()
    if not cid_str:
        return -1
    for i, c in enumerate(conns):
        if str(c.get("id") or "") == cid_str:
            return i
    if cid_str.startswith("c-"):
        try:
            idx = int(cid_str.split("-", 1)[1])
            if 0 <= idx < len(conns):
                return idx
        except (ValueError, IndexError):
            pass
    try:
        idx = int(cid_str)
        if 0 <= idx < len(conns):
            return idx
    except ValueError:
        pass
    return -1


def _find_model_index(models: list[dict], mid_raw: Any) -> int:
    if not models:
        return -1
    mid_str = str(mid_raw or "").strip()
    if not mid_str:
        return -1
    for i, m in enumerate(models):
        if str(m.get("id") or "") == mid_str:
            return i
    for i, m in enumerate(models):
        if str(m.get("model_id") or "") == mid_str:
            return i
    if mid_str.startswith("m-"):
        try:
            idx = int(mid_str.split("-", 1)[1])
            if 0 <= idx < len(models):
                return idx
        except (ValueError, IndexError):
            pass
    try:
        idx = int(mid_str)
        if 0 <= idx < len(models):
            return idx
    except ValueError:
        pass
    return -1


def _reorder_conns(conns: list[dict], order: list[Any]) -> list[dict]:
    if not conns:
        return []
    conn_map: dict[str, dict] = {}
    for i, c in enumerate(conns):
        cid = str(c.get("id") or f"c-{i}")
        conn_map[cid] = c
        conn_map[f"c-{i}"] = c
        conn_map[str(i)] = c
    new_conns = []
    seen = set()
    for o in order:
        o_str = str(o).strip()
        c = conn_map.get(o_str)
        if c is not None and id(c) not in seen:
            new_conns.append(c)
            seen.add(id(c))
    for c in conns:
        if id(c) not in seen:
            new_conns.append(c)
            seen.add(id(c))
    for i, c in enumerate(new_conns):
        c["priority"] = i + 1
    return new_conns


def _video_flow_catalog() -> dict:
    """Build the Video Flow model/theme catalog.

    Provider groups come from the isolated Video Flow provider registry
    (full provider list with real connection statuses, as on GitHub); the
    Groq entry is overlaid with the planning-gateway truth because the new
    engine's gateway reads main-storage connections. Models list the
    planner models the gateway can actually execute.
    """
    active = storage.get_setting("video_flow_selected_model", "") or storage.get_setting("exec_policy_model", "openai/gpt-oss-120b")

    try:
        service_catalog = video_flow_provider_service.catalog()
    except Exception:
        service_catalog = {}

    groq_connections = [c for c in storage.get_provider_connections("groq") if c.get("is_active")]
    groq_connected = any(str(c.get("api_key") or "").strip() for c in groq_connections)

    def _overlay_groq(entry: dict) -> dict:
        merged = dict(entry)
        merged.update(
            {
                "name": "Groq",
                "status": "connected" if groq_connected else "disconnected",
                "active_count": len(groq_connections),
            }
        )
        return merged

    api_key_group = [
        _overlay_groq(item) if item.get("id") == "groq" else item
        for item in service_catalog.get("api_key", [])
    ]
    if not any(item.get("id") == "groq" for item in api_key_group):
        api_key_group.insert(0, _overlay_groq({"id": "groq", "category": "api_key"}))

    # Local Providers section removed (user request) — replaced by Custom Providers.
    local_group = []

    local_group = []
    oauth_group = list(service_catalog.get("oauth", []))

    # The picker is fed from the Video Flow provider page's own model catalog
    # (connected providers' models), plus the Groq planning gateway models
    # (which read the main-storage Groq connection) and the local generator.
    try:
        service_models = [
            {
                "full_id": m["full_id"],
                "provider": m.get("provider"),
                "provider_name": m.get("provider_name") or m.get("provider"),
                "display_name": m.get("display_name") or m["full_id"],
                "available": bool(m.get("available")),
                "is_active": m.get("is_active", True),
                "capabilities": m.get("capabilities") or [],
            }
            for m in video_flow_provider_service.list_models()
            if m.get("is_active", True) is not False
        ]
    except Exception:
        service_models = []

    # 9Router planning-gateway internals (gpt-oss) are not catalog models
    models = [m for m in service_models if "gpt-oss" not in str(m.get("full_id", ""))]
    service_refs = {m["full_id"] for m in models}

    models.append(
        {
            "full_id": "local/deterministic",
            "provider": "local",
            "provider_name": "Local",
            "display_name": "Local Code2Video Generator (offline)",
            "available": True,
            "is_active": True,
            "capabilities": ["offline"],
        }
    )

    # Custom providers: their models appear in the Video Flow LLM catalog
    try:
        for cp in storage.get_video_flow_custom_providers():
            has_key = bool(str(cp.get("api_key") or "").strip())
            api_key_group.append({
                "id": cp.get("id"),
                "name": cp.get("name"),
                "category": "api_key",
                "status": "connected" if has_key else "disconnected",
                "active_count": len(cp.get("models") or []),
            })
            for m in cp.get("models") or []:
                full_id = f"{cp['id']}/{m.get('model_id')}"
                if not any(x.get("full_id") == full_id for x in models):
                    models.append({
                        "full_id": full_id,
                        "provider": cp.get("id"),
                        "provider_name": cp.get("name"),
                        "display_name": m.get("model_id"),
                        "available": True,
                        "is_active": m.get("is_active", True),
                        "capabilities": ["custom"],
                    })
    except Exception:
        pass

    return {
        "providers": api_key_group + local_group + oauth_group,
        "provider_groups": {
            "oauth": oauth_group,
            "api_key": api_key_group,
            "local": [],
        },
        "models": models,
        "active_model": active,
        "themes": ["auto", "voice-flow", "midnight", "paper", "neon", "ocean", "forest", "sunset", "mono"],
    }


def start_api_server(host: str = "127.0.0.1") -> None:
    # Merge any fragmented databases from the pre-account / multi-account era
    # into the active database before serving reads, so Insights and History
    # show the user's real totals. Idempotent and non-fatal.
    try:
        if storage.repoint_if_needed():
            invalidate_history_cache()
        from voice_flow.consolidate import consolidate_engine, CONSOLIDATION_MARKER_KEY
        summary = consolidate_engine(storage, dry_run=False)
        if summary.get("merged_history"):
            print(f"[API SERVER] Consolidated {summary['merged_history']} history rows into {summary['target']}")
    except Exception as exc:
        print(f"[API SERVER] Skipped database consolidation: {exc}")
    try:
        ThreadingHTTPServer.allow_reuse_address = True
        httpd = ThreadingHTTPServer((host, PORT), VoiceFlowApiHandler)
        print(f"[API SERVER] Voice Flow Multithreaded Backend API listening on http://{host}:{PORT}")
        try:
            from voice_flow.video_flow_engine.notebooklm import start_keepalive_daemon, trigger_keepalive_now
            start_keepalive_daemon()
            trigger_keepalive_now(force=False, background=True)
        except Exception:
            pass
        httpd.serve_forever()
    except OSError as e:
        if runtime_is_compatible(port=PORT):
            print(f"[API SERVER] A compatible Voice Flow backend already owns port {PORT}.")
        else:
            print(f"[API SERVER ERROR] Port {PORT} is occupied by an incompatible runtime ({e}).")
    except Exception as e:
        print(f"[API SERVER ERROR] Failed to start HTTP server: {e}")


if __name__ == "__main__":
    start_api_server()
