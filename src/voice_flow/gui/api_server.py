"""Local REST API Server serving real SQLite database data and hardware info
to the Voice Flow Desktop GUI.
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import asdict
from pathlib import Path
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
from voice_flow.video_flow_oauth import OAuthError
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
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
archive = AudioArchive()

OAUTH_CALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Video Flow — OAuth</title>
<style>body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:grid;place-items:center;min-height:100vh;margin:0}
div.card{text-align:center;padding:32px;border:1px solid #30363d;border-radius:12px;background:#161b22;max-width:460px}
h1{font-size:18px;margin:0 0 8px}p{color:#8b949e;font-size:14px;margin:0 0 16px}
code{display:block;font-family:ui-monospace,Consolas,monospace;font-size:13px;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:14px;word-break:break-all}
button{background:#238636;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
button:hover{background:#2ea043}.hidden{display:none}</style></head>
<body><div class="card">
<h1 id="vf-heading">Finishing sign-in…</h1>
<p id="vf-detail">Your account is being connected to Voice Flow.</p>
<div id="vf-code-card" class="hidden">
<p>This window opened outside Voice Flow, so copy the code below, paste it into the sign-in box in the app, and press <b>Complete sign-in</b>.</p>
<code id="vf-code-value"></code>
<button id="vf-copy">Copy code</button>
</div>
</div>
<script>
(function () {
  var code = __OAUTH_CODE__;
  var state = __OAUTH_STATE__;
  var error = __OAUTH_ERROR__;
  var heading = document.getElementById("vf-heading");
  var detail = document.getElementById("vf-detail");
  var card = document.getElementById("vf-code-card");
  var value = document.getElementById("vf-code-value");
  if (error) {
    heading.textContent = "Sign-in was not completed.";
    detail.textContent = error;
  } else if (code && window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage({type: "OAUTH_CALLBACK_SUCCESS", code: code, state: state}, window.location.origin);
      window.close();
    } catch (err) {
      card.classList.remove("hidden");
      value.textContent = code;
    }
  } else if (code) {
    card.classList.remove("hidden");
    value.textContent = code;
    heading.textContent = "Copy the code, then close this tab";
  } else {
    heading.textContent = "No authorization code received.";
    detail.textContent = "Close this window and press Add account again in Voice Flow.";
  }
  var copy = document.getElementById("vf-copy");
  if (copy) copy.addEventListener("click", function () {
    navigator.clipboard.writeText(value.textContent).then(function () {
      copy.textContent = "Copied ✓";
      window.setTimeout(function () { copy.textContent = "Copy code"; }, 2000);
    });
  });
})();
</script></body></html>"""

runtime_controller = None

OAUTH_CALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Voice Flow — OAuth</title>
<style>body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;display:grid;place-items:center;min-height:100vh;margin:0}
div.card{text-align:center;padding:32px;border:1px solid #30363d;border-radius:12px;background:#161b22;max-width:460px}
h1{font-size:18px;margin:0 0 8px}p{color:#8b949e;font-size:14px;margin:0 0 16px}
code{display:block;font-family:ui-monospace,Consolas,monospace;font-size:13px;background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:14px;word-break:break-all}
button{background:#238636;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
button:hover{background:#2ea043}.hidden{display:none}</style></head>
<body><div class="card">
<h1 id="vf-heading">Finishing sign-in…</h1>
<p id="vf-detail">Your account is being connected to Voice Flow.</p>
<div id="vf-code-card" class="hidden">
<p>This window opened outside Voice Flow, so copy the code below, paste it into the sign-in box in the app, and press <b>Complete sign-in</b>.</p>
<code id="vf-code-value"></code>
<button id="vf-copy">Copy code</button>
</div>
</div>
<script>
(function () {
  var code = __OAUTH_CODE__;
  var state = __OAUTH_STATE__;
  var error = __OAUTH_ERROR__;
  var heading = document.getElementById("vf-heading");
  var detail = document.getElementById("vf-detail");
  var card = document.getElementById("vf-code-card");
  var value = document.getElementById("vf-code-value");
  if (error) {
    heading.textContent = "Sign-in was not completed.";
    detail.textContent = error;
  } else if (code && window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage({type: "OAUTH_CALLBACK_SUCCESS", code: code, state: state}, window.location.origin);
      window.close();
    } catch (err) {
      card.classList.remove("hidden");
      value.textContent = code;
    }
  } else if (code) {
    card.classList.remove("hidden");
    value.textContent = code;
    heading.textContent = "Copy the code, then close this tab";
  } else {
    heading.textContent = "No authorization code received.";
    detail.textContent = "Close this window and press Add account again in Voice Flow.";
  }
  var copy = document.getElementById("vf-copy");
  if (copy) copy.addEventListener("click", function () {
    navigator.clipboard.writeText(value.textContent).then(function () {
      copy.textContent = "Copied ✓";
      window.setTimeout(function () { copy.textContent = "Copy code"; }, 2000);
    });
  });
})();
</script></body></html>"""

PERMANENT_DELETE_CONFIRMATION = "DELETE"


def _create_video_flow_combo(name: str, models: list, strategy: str) -> dict:
    """Create a model combo in the shared provider tables (name + ordered members)."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Combo name is required.")
    members = [str(m).strip() for m in models or [] if str(m).strip()]
    if not members:
        raise ValueError("A combo needs at least one model.")
    if strategy not in ("fallback", "round_robin"):
        strategy = "fallback"
    selectable = video_flow_provider_service.selectable_model_refs()
    unknown = [m for m in members if m not in selectable]
    if unknown:
        raise ValueError("Not selectable: " + ", ".join(unknown))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT id FROM video_flow_combos WHERE name = ?", (clean_name,)).fetchone()
        if existing:
            raise ValueError(f"Combo '{clean_name}' already exists.")
        created_at = conn.execute("SELECT datetime('now')").fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO video_flow_combos (name, strategy, created_at) VALUES (?, ?, ?)",
            (clean_name, strategy, created_at),
        )
        combo_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO video_flow_combo_models (combo_id, model_ref, position) VALUES (?, ?, ?)",
            [(combo_id, m, i) for i, m in enumerate(members)],
        )
    return {"id": combo_id, "name": clean_name, "models": members, "strategy": strategy}


def _delete_video_flow_combo(combo_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM video_flow_combo_models WHERE combo_id = ?", (int(combo_id),))
        cursor = conn.execute("DELETE FROM video_flow_combos WHERE id = ?", (int(combo_id),))
        return cursor.rowcount > 0


def register_runtime_controller(controller) -> None:
    """Register the running engine without making the standalone API import it."""
    global runtime_controller
    runtime_controller = controller


class VoiceFlowApiHandler(SimpleHTTPRequestHandler):
    """Handles static GUI files + API endpoints (/api/history, /api/insights, /api/dictionary, /api/microphones, /api/apikeys)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress HTTP logging to prevent UnicodeEncodeError on Windows console

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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if "code" in urllib.parse.parse_qs(parsed.query) or "error" in urllib.parse.parse_qs(parsed.query):
            # OAuth popup callback landing: Google's loopback redirect arrives
            # at "/?code=...&state=..." with no API path.
            self._serve_oauth_callback()
            return

        if path == "/api/reload-tts":
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
            })
        elif path == "/api/settings/get":
            params = urllib.parse.parse_qs(parsed.query)
            key = (params.get("key", [""])[0] or "").strip()
            allowed_get = {
                "voice_flow_enabled", "audio_flow_enabled", "video_flow_enabled",
                "video_flow_v3_enabled", "polishing_enabled", "press_enter_enabled", "has_viewed_onboarding",
            }
            if key not in allowed_get:
                self.send_json_response({"success": False, "error": "Unknown setting"}, 400)
                return
            default_val = False if key == "has_viewed_onboarding" else True
            self.send_json_response({"success": True, "key": key, "value": bool(storage.get_setting(key, default_val))})
        elif path == "/api/history":
            self.send_json_response(storage.get_recent_history())
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
        elif path == "/api/insights":
            params = urllib.parse.parse_qs(parsed.query)
            range_val = params.get("range", ["all"])[0]
            self.send_json_response(storage.get_insights(range_filter=range_val))
        elif path == "/api/dictionary":
            self.send_json_response(storage.get_dictionary_words())
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
            # The new engine's flat MP4 is both the render and the export.
            self._stream_shim_video(job_id, download=True)
        elif path == "/api/video-flow/v3/export":
            params = urllib.parse.parse_qs(parsed.query)
            job_id = (params.get("id", [""])[0] or "").strip()
            video_file = data_dir() / "v3_projects" / job_id / "video.mp4"
            if re.fullmatch(r"[A-Za-z0-9_\-]+", job_id) and video_file.exists() and video_file.stat().st_size > 0:
                self.send_json_response({
                    "success": True,
                    "job_id": job_id,
                    "export_status": "exported",
                    "download_url": f"/api/video-flow/v3/export/download?id={job_id}",
                })
            else:
                self.send_json_response({"success": False, "job_id": job_id, "export_status": "not_requested"}, 404)
        elif path == "/api/video-flow/v3/runtime-bundle.js":
            bundle_paths = [
                os.path.join(GUI_DIR, "v3-renderer.bundle.js"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(GUI_DIR))), "video_flow_renderer", "dist", "v3-renderer.bundle.js"),
            ]
            bundle_file = next((p for p in bundle_paths if os.path.isfile(p)), None)
            if bundle_file:
                with open(bundle_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "V3 runtime bundle not found")
        elif path == "/api/video-flow/jobs/status" or path.startswith("/api/video-flow/v3/status"):
            params = urllib.parse.parse_qs(parsed.query)
            video_id = (params.get("id", [""])[0] or "").strip()
            job = None
            try:
                job = get_video_flow_service().get(video_id)
            except Exception:
                job = None
            if job is None:
                self.send_json_response({"success": False, "error": "Video not found"}, 404)
            else:
                self.send_json_response({"success": True, "video": _shim_video(job)})
        elif path.startswith("/api/video-flow/videos/file"):
            params = urllib.parse.parse_qs(parsed.query)
            video_id = (params.get("id", [""])[0] or "").strip()
            download = params.get("download", ["0"])[0] == "1"
            self._stream_shim_video(video_id, download=download)
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
        elif path == "/api/video-flow/providers":
            self.send_json_response(video_flow_provider_service.catalog())
        elif path == "/api/video-flow/providers/details":
            params = urllib.parse.parse_qs(parsed.query)
            provider_id = params.get("provider", [""])[0]
            try:
                self.send_json_response(video_flow_provider_service.provider_details(provider_id))
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)
        elif path == "/api/video-flow/providers/oauth/callback":
            self._serve_oauth_callback()
        elif path == "/api/providers/catalog":
            specs = [s.to_dict() for s in get_all_provider_specs()]
            self.send_json_response({"providers": specs})
        elif path == "/api/providers/connections":
            all_conns = storage.get_all_provider_connections()
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
            self.send_json_response(storage.get_all_api_keys())
        elif path == "/api/providers/details":
            params = urllib.parse.parse_qs(parsed.query)
            provider = params.get("provider", ["gemini"])[0].lower()
            conns = storage.get_provider_connections(provider)
            mode = storage.get_provider_load_balance_mode(provider)
            models = storage.get_provider_models(provider)
            # Mask stored secrets; the loopback page never needs the raw key.
            for item in conns:
                if isinstance(item, dict) and item.get("api_key"):
                    item["api_key"] = _mask_secret(str(item["api_key"]))
            self.send_json_response({
                "provider": provider,
                "connections": conns,
                "mode": mode,
                "models": models
            })
        elif path == "/api/providers/overview":
            all_conns = storage.get_all_provider_connections()
            self.send_json_response({"connections": all_conns})
        elif path == "/api/microphones":
            try:
                devices = sd.query_devices()
                mics = []
                seen = set()
                for idx, d in enumerate(devices):
                    if d["max_input_channels"] > 0:
                        name = d["name"].strip()
                        if name not in seen:
                            seen.add(name)
                            mics.append({"index": idx, "name": name})
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
        elif path == "/api/audio-summary/settings/get":
            try:
                model_ref = str(storage.get_setting("exec_audio_summary_model", "") or "")
                consent = bool(storage.get_setting("exec_audio_summary_allow_external_ai", False))
                self.send_json_response({"success": True, "model": model_ref, "consent": consent})
            except Exception as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 500)
        elif path == "/api/audio-providers/overview":
            try:
                data = storage.get_audio_providers_overview()
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
                    conns = storage.get_audio_provider_connections(provider)
                    tts_models = storage.get_tts_models_for_provider(provider)
                    data = {"provider": provider, "connections": conns, "models": tts_models}
                    self.send_json_response(data)
                except Exception as exc:
                    print(f"[AUDIO FLOW] /api/audio-providers/details error: {exc}")
                    self.send_json_response({"success": False, "error": str(exc)}, 500)
            else:
                self.send_json_response({"error": "Missing provider"}, status=400)
        elif path == "/api/styles/get":
            personal = storage.get_setting("style_personal", "casual")
            work = storage.get_setting("style_work", "casual")
            email = storage.get_setting("style_email", "formal")
            developer = storage.get_setting("style_developer", "casual")
            other = storage.get_setting("style_other", "casual")
            autocleanup = storage.get_setting("style_autocleanup", "cleanup_light")
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
        elif path == "/api/settings/get":
            settings = storage.get_all_settings()
            if "polishing_enabled" not in settings:
                settings["polishing_enabled"] = True
            if "audio_flow_enabled" not in settings:
                settings["audio_flow_enabled"] = True
            if "launch_at_login_enabled" not in settings:
                settings["launch_at_login_enabled"] = True
            self.send_json_response(settings)
        else:
            super().do_GET()

    def do_POST(self):
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

        if length < 0 or length > MAX_JSON_BODY_BYTES:
            self.send_json_response({"success": False, "error": "Invalid body length"}, 400 if length < 0 else 413)
            return

        try:
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            data = json.loads(body) if body else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json_response({"success": False, "error": "Invalid JSON body"}, 400)
            return

        if not isinstance(data, dict):
            self.send_json_response({"success": False, "error": "JSON body must be an object"}, 400)
            return

        path = urllib.parse.urlparse(self.path).path

        if path == "/api/microphones/select":
            mic_name = data.get("name")
            mic_index = data.get("index")
            config.selected_mic_device = mic_index if mic_index is not None else mic_name
            storage.save_setting("selected_mic_device", config.selected_mic_device)
            print(f"[AUDIO] Active recording input device switched to: {config.selected_mic_device}")
            self.send_json_response({"success": True, "selected_device": str(config.selected_mic_device)})

        elif path == "/api/apikeys/test":
            provider = data.get("provider", "gemini")
            key = data.get("key", "").strip()
            result = self.verify_api_key(provider, key)
            if result["success"]:
                storage.save_api_key(key, provider)
                config.add_api_key(key)
            self.send_json_response(result)

        elif self.path == "/api/dictionary/add":
            word_value = data.get("word", "")
            if not isinstance(word_value, str):
                self.send_json_response({"success": False, "error": "word must be text"}, 400); return
            word = word_value.strip()
            if "->" in word or "=>" in word:
                self.send_json_response({"success": False, "error": "Snippet arrows have moved to Snippets. Add a trigger and expansion there."}, 400); return
            try:
                storage._validated_text(word, "word", 1, 120)
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400); return
            success = storage.add_dictionary_word(word)
            dictionary_engine.mark_dirty()
            if not success:
                self.send_json_response({"success": False, "error": "That dictionary term already exists"}, 409); return
            self.send_json_response({"success": True, "words": storage.get_dictionary_words()})

        elif path == "/api/dictionary/remove":
            word = data.get("word")
            if not isinstance(word, str) or not word.strip():
                self.send_json_response({"success": False, "error": "Dictionary word must be a non-empty string."}, 400)
                return
            success = storage.remove_dictionary_word(word)
            if not success:
                self.send_json_response({"success": False, "error": "Dictionary entry was not found."}, 404)
                return
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": True, "words": storage.get_dictionary_words()})

        elif path == "/api/history/pin":
            record_id = data.get("id")
            if not record_id:
                self.send_json_response({"success": False, "error": "Missing record id"}, 400)
                return
            try:
                rec_id_int = int(record_id)
                res = storage.toggle_history_pin(rec_id_int)
                self.send_json_response(res)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/history/delete":
            record_id = data.get("id")
            if not record_id:
                self.send_json_response({"success": False, "error": "Missing record id"}, 400)
                return
            try:
                rec_id_int = int(record_id)
                res = storage.delete_history_record(rec_id_int)
                if res:
                    self.send_json_response({"success": True, "id": rec_id_int})
                else:
                    self.send_json_response({"success": False, "error": "Record not found"}, 404)
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/apikeys/add":
            key = data.get("key", "").strip()
            provider = data.get("provider", "gemini")
            result = self.verify_api_key(provider, key)
            if result["success"]:
                storage.save_api_key(key, provider)
                config.add_api_key(key)
                self.send_json_response({"success": True, "message": result.get("message", "Key saved!"), "keys": storage.get_all_api_keys()})
            else:
                self.send_json_response({"success": False, "error": result.get("error", "Invalid API key")})

        elif path == "/api/providers/validate":
            provider = data.get("provider", "").lower()
            api_key = data.get("apiKey", data.get("api_key", ""))
            base_url = data.get("baseUrl", data.get("base_url"))
            name = data.get("name", "")
            priority = data.get("priority", 0)
            org = data.get("organization")
            acc = data.get("accountId")

            is_valid, last_error = validate_provider_key(provider, api_key, base_url)
            conn_dict = storage.add_provider_connection(
                provider=provider,
                name=name,
                api_key=api_key,
                priority=priority,
                base_url=base_url,
                organization=org,
                account_id=acc,
            )
            storage.update_provider_connection_validation(conn_dict["id"], is_valid, last_error)
            self.send_json_response({
                "success": True,
                "isValid": is_valid,
                "lastError": last_error,
                "connection": conn_dict,
            })

        elif path == "/api/providers/test":
            cid = data.get("id")
            if not cid:
                self.send_json_response({"success": False, "error": "Connection ID required"}, 400)
                return
            conns = storage.get_all_provider_connections()
            target_conn = None
            for p_list in conns.values():
                for c in p_list:
                    if c["id"] == cid or str(c.get("uuid_id")) == str(cid):
                        target_conn = c
                        break

            if not target_conn:
                self.send_json_response({"success": False, "error": "Connection not found"}, 404)
                return

            is_valid, last_error = validate_provider_key(
                target_conn["provider"], target_conn["api_key"], target_conn.get("base_url")
            )
            storage.update_provider_connection_validation(target_conn["id"], is_valid, last_error)
            self.send_json_response({
                "success": True,
                "id": cid,
                "isValid": is_valid,
                "lastError": last_error,
            })

        elif path == "/api/providers/toggle":
            cid = data.get("id")
            is_active = data.get("isActive", data.get("is_active", True))
            if not cid:
                self.send_json_response({"success": False, "error": "Connection ID required"}, 400)
                return
            storage.toggle_provider_connection(cid, is_active)
            self.send_json_response({"success": True, "id": cid, "isActive": is_active})

        elif path == "/api/providers/delete":
            cid = data.get("id")
            if not cid:
                self.send_json_response({"success": False, "error": "Connection ID required"}, 400)
                return
            storage.delete_provider_connection(cid)
            self.send_json_response({"success": True, "id": cid})

        elif path == "/api/dictionary/corrections/add":
            try:
                correction = storage.add_dictionary_correction(data.get("wrong_text", ""), data.get("correct_text", ""))
            except sqlite3.IntegrityError:
                self.send_json_response({"success": False, "error": "That heard phrase already exists"}, 409); return
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400); return
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": True, "correction": correction}, 201)

        elif path == "/api/dictionary/corrections/update":
            try:
                correction = storage.update_dictionary_correction(int(data.get("id")), data.get("wrong_text", ""), data.get("correct_text", ""))
            except sqlite3.IntegrityError:
                self.send_json_response({"success": False, "error": "That heard phrase already exists"}, 409); return
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc) or "Invalid correction"}, 400); return
            if correction is None:
                self.send_json_response({"success": False, "error": "Correction not found"}, 404); return
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": True, "correction": correction})

        elif path == "/api/dictionary/corrections/remove":
            try:
                success = storage.remove_dictionary_correction(int(data.get("id")))
            except (TypeError, ValueError):
                self.send_json_response({"success": False, "error": "A valid correction id is required"}, 400); return
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": success}, 200 if success else 404)

        elif path == "/api/record/toggle":
            recording = data.get("recording", False)
            state_file = os.path.join(os.path.expanduser("~"), ".voice_flow", "recording_state.json")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"recording": recording}, f)
            print(f"[RECORD] Hands-free recording {'STARTED' if recording else 'STOPPED'} via GUI")
            self.send_json_response({"success": True, "recording": recording})

        elif path == "/api/styles/update":
            category = data.get("category")
            style_id = data.get("style_id")
            if not isinstance(category, str) or not isinstance(style_id, str):
                self.send_json_response({"success": False, "error": "Invalid parameters"}, 400)
                return
            storage.save_setting(f"style_{category}", style_id)
            print(f"[STYLE PRESET SAVED] Category: {category} -> Style: {style_id}")
            self.send_json_response({"success": True, "category": category, "style_id": style_id})

        elif path == "/api/styles/preview":
            raw_text = data.get("text", "")
            before = data.get("before", "")
            after = data.get("after", "")
            style_req = data.get("style", "formal")
            
            from voice_flow.style_formatter import style_formatter
            from voice_flow.style_models import TextboxContext
            
            ctx = TextboxContext(before=before, after=after, trustworthy=bool(before or after))
            
            all_styles = {
                "formal": style_formatter.format(raw_text, style="formal", context=ctx),
                "casual": style_formatter.format(raw_text, style="casual", context=ctx),
                "very_casual": style_formatter.format(raw_text, style="very_casual", context=ctx),
                "excited": style_formatter.format(raw_text, style="excited", context=ctx),
            }
            formatted = all_styles.get(style_req, all_styles["formal"])
            self.send_json_response({"success": True, "formatted": formatted, "all_styles": all_styles})

        elif path == "/api/styles/overrides/add":
            ov_type = data.get("type", "app")
            identifier = data.get("identifier", "").strip()
            category = data.get("category", "other").strip()
            if not identifier:
                self.send_json_response({"success": False, "error": "Identifier required"}, 400)
                return
            if ov_type == "domain":
                style_engine.classifier.set_domain_override(identifier, category)
            else:
                style_engine.classifier.set_app_override(identifier, category)
            self.send_json_response({"success": True})

        elif path == "/api/styles/overrides/remove":
            ov_type = data.get("type", "app")
            identifier = data.get("identifier", "").strip()
            if ov_type == "domain":
                style_engine.classifier.remove_domain_override(identifier)
            else:
                style_engine.classifier.remove_app_override(identifier)
            self.send_json_response({"success": True})

        elif path == "/api/styles/temporary_override":
            temp_style = data.get("style")
            style_engine.override_manager.set_temporary_override(temp_style)
            self.send_json_response({"success": True, "temporary_override": temp_style})


        elif path == "/api/policy/update":
            model_value = data.get("model_id")
            if not isinstance(model_value, str) or not model_value.strip():
                self.send_json_response({"success": False, "error": "Model ID must be a non-empty string"}, 400)
                return
            model_id = model_value.strip()
            if not storage.save_setting("exec_policy_model", model_id):
                self.send_json_response({"success": False, "error": "Could not persist Voice Flow policy"}, 500)
                return
            print(f"[EXEC VOICE FLOW POLICY] Updated executive polishing model to: {model_id}")
            self.send_json_response({"success": True, "active_model": model_id})

        elif path in ("/api/audio-policy/update", "/api/audio-policy/set"):
            model_value = data.get("model_id", data.get("model"))
            if not isinstance(model_value, str) or not model_value.strip():
                self.send_json_response({"success": False, "error": "Model ID must be a non-empty string"}, 400)
                return
            model_id = model_value.strip()
            if not storage.save_setting("exec_audio_policy_model", model_id):
                self.send_json_response({"success": False, "error": "Could not persist audio policy"}, 500)
                return
            print(f"[AUDIO FLOW POLICY] Updated executive TTS model to: {model_id}")
            self.send_json_response({"success": True, "active_model": model_id})

        elif path == "/api/audio-policy/toggle":
            enabled = data.get("enabled")
            if type(enabled) is not bool:
                self.send_json_response({"success": False, "error": "enabled must be boolean"}, 400)
                return
            if not storage.save_setting("audio_flow_enabled", enabled):
                self.send_json_response({"success": False, "error": "Could not persist Audio Flow setting"}, 500)
                return
            print(f"[AUDIO FLOW POLICY] Toggled Audio Flow state to: {enabled}")
            self.send_json_response({"success": True, "enabled": enabled})

        elif path == "/api/audio-policy/speed":
            speed = data.get("speed")
            if not isinstance(speed, (int, float)) or isinstance(speed, bool) or not math.isfinite(float(speed)) or not 0.5 <= float(speed) <= 3.0:
                self.send_json_response({"success": False, "error": "speed must be a finite value between 0.5 and 3.0"}, 400)
                return
            speed = float(speed)
            if not storage.save_setting("audio_flow_speed", speed):
                self.send_json_response({"success": False, "error": "Could not persist Audio Flow speed"}, 500)
                return
            self.send_json_response({"success": True, "speed": speed})

        elif path == "/api/audio-summary/settings/model":
            model_ref = str(data.get("model_ref", "") or data.get("model", "")).strip()
            # The new-engine planning gateway is Groq-only; accept any ref here
            # and let the engine surface a precise error at generation time.
            if not storage.save_setting("exec_audio_summary_model", model_ref):
                self.send_json_response({"success": False, "error": "Could not persist Audio Flow Summary model"}, 500)
                return
            self.send_json_response({"success": True, "model": model_ref})

        elif path == "/api/audio-summary/settings/consent":
            consent = bool(data.get("consent", False))
            if not storage.save_setting("exec_audio_summary_allow_external_ai", consent):
                self.send_json_response({"success": False, "error": "Could not persist Audio Flow Summary consent"}, 500)
                return
            self.send_json_response({"success": True, "consent": consent})


        elif path == "/api/audio-flow/speak":
            text = data.get("text", "").strip()
            model_override = data.get("model") or data.get("voice")
            if runtime_controller:
                runtime_controller._process_audio_flow_pipeline(
                    text_override=text,
                    model_override=model_override,
                )
            self.send_json_response({"success": True})

        elif path == "/api/audio-flow/stop":
            if runtime_controller:
                runtime_controller._stop_audio_flow_pipeline()
            self.send_json_response({"success": True})

        elif path == "/api/audio-flow/tts-control":
            action = str(data.get("action", "")).lower()
            try:
                import voice_flow.tts_engine as _tts
                if action == "pause":
                    _tts.tts_engine.pause()
                elif action == "resume":
                    _tts.tts_engine.resume()
                elif action == "stop":
                    _tts.tts_engine.stop()
                else:
                    self.send_json_response({"success": False, "error": "Unknown action"}, 400)
                    return
                self.send_json_response({"success": True, "action": action})
            except Exception as e:
                self.send_json_response({"success": False, "error": str(e)}, 500)

        elif path == "/api/audio-providers/connections/add":
            provider = data.get("provider", "")
            name = data.get("name", "Key #1")
            key = data.get("key", "")
            priority = data.get("priority", 0)
            base_url = data.get("baseUrl", data.get("base_url"))
            force_save = data.get("force_save", False)

            v_res = self.verify_tts_api_key(provider, key) if not force_save else {"status": "Not Tested", "valid": None}
            valid_val = v_res.get("valid")
            if valid_val is None:
                is_valid = True
                last_err = None
            else:
                is_valid = bool(valid_val)
                last_err = None if is_valid else v_res.get("status", "Validation Failed")

            result = storage.add_audio_provider_connection(
                provider=provider,
                name=name,
                api_key=key,
                priority=priority,
                base_url=base_url,
            )
            storage.update_audio_provider_connection_validation(result["id"], is_valid, last_err)
            self.send_json_response({"ok": True, "result": result, "verification": v_res})

        elif path == "/api/audio-providers/connections/delete":
            cid = data.get("id")
            storage.delete_audio_provider_connection(cid)
            self.send_json_response({"ok": True})

        elif path == "/api/audio-providers/connections/toggle":
            cid = data.get("id")
            is_active = data.get("is_active", True)
            storage.toggle_audio_provider_connection(cid, is_active)
            self.send_json_response({"ok": True})

        elif path == "/api/audio-providers/master/toggle":
            provider_id = data.get("provider_id") or data.get("provider", "")
            is_active = data.get("is_active", True)
            res = storage.toggle_audio_provider_master(provider_id, is_active)
            self.send_json_response({"ok": True, "result": res})

        elif path == "/api/audio-providers/models/toggle":
            mid = data.get("id")
            is_active = data.get("is_active", True)
            res = storage.toggle_tts_model(mid, is_active)
            self.send_json_response({"ok": True, "result": res})

        elif path == "/api/audio-providers/connections/test":
            provider = data.get("provider", "")
            key = data.get("key", "")
            cid = data.get("id")
            name = data.get("name", "eastus")
            v_res = self.verify_tts_api_key(provider, key, region=name)
            if cid:
                is_valid = bool(v_res.get("valid", False))
                last_err = None if is_valid else v_res.get("status", "Error")
                storage.update_audio_provider_connection_validation(int(cid), is_valid, last_err)
            self.send_json_response(v_res)

        elif path == "/api/video-flow/documents/extract":
            try:
                extracted = extract_document_text(
                    str(data.get("file_name", "")),
                    str(data.get("content_base64", "")),
                )
                self.send_json_response({
                    "success": True,
                    "text": extracted,
                    "characters": len(extracted),
                })
            except (ValueError, RuntimeError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path in ("/api/video-flow/generate", "/api/video-flow/v3/generate"):
            try:
                job = get_video_flow_service().queue(
                    source_text=data.get("source_text"),
                    mode=data.get("mode"),
                    title=data.get("title"),
                    source_name=str(data.get("source_name", "") or ""),
                    model_ref=data.get("model_ref"),
                    theme=data.get("theme"),
                    visual_direction=data.get("visual_direction"),
                    allow_external_ai=bool(data.get("allow_external_ai", False)),
                    voice=data.get("voice"),
                )
                self.send_json_response({"success": True, "video": _shim_video(job), "job_id": job.job_id, "status": _shim_video(job)["status"]}, 202)
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/voice":
            voice = str(data.get("voice", "")).strip()
            if not voice or "/" not in voice:
                self.send_json_response({"success": False, "error": "Select a voice."}, 400)
            else:
                storage.save_setting("video_flow_voice_model", voice)
                self.send_json_response({"success": True, "active_voice": voice})

        elif path == "/api/video-flow/settings/model":
            model_ref = str(data.get("model_ref", "")).strip()
            if not model_ref:
                self.send_json_response({"success": False, "error": "Select a model or combo."}, 400)
            else:
                storage.save_setting("exec_policy_model", model_ref)
                self.send_json_response({"success": True, "active_model": model_ref})

        elif path == "/api/video-flow/v3/export":
            # The new engine renders the final MP4 directly — an export
            # request is satisfied by the existing file.
            export_id = str(data.get("id", "")).strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", export_id):
                self.send_json_response({"success": False, "error": "Invalid video id"}, 400)
                return
            video_file = data_dir() / "v3_projects" / export_id / "video.mp4"
            if video_file.exists() and video_file.stat().st_size > 0:
                self.send_json_response({
                    "success": True,
                    "job_id": export_id,
                    "export_status": "exported",
                    "download_url": f"/api/video-flow/v3/export/download?id={export_id}",
                })
            else:
                job = get_video_flow_service().get(export_id)
                if job is None:
                    self.send_json_response({"success": False, "error": "Video not found"}, 404)
                else:
                    self.send_json_response({"success": False, "job_id": export_id, "export_status": "processing"}, 202)

        elif path == "/api/video-flow/combos/create":
            try:
                combo = _create_video_flow_combo(
                    str(data.get("name", "")),
                    list(data.get("models", [])),
                    str(data.get("strategy", "fallback")),
                )
                self.send_json_response({"success": True, "combo": combo})
            except (ValueError, sqlite3.IntegrityError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/combos/delete":
            deleted = _delete_video_flow_combo(int(data.get("id", 0)))
            self.send_json_response({"success": deleted}, 200 if deleted else 404)

        elif path == "/api/video-flow/videos/delete":
            video_id = str(data.get("id", ""))
            service = get_video_flow_service()
            job = service.get(video_id)
            if not job:
                self.send_json_response({"success": False, "error": "Video not found."}, 404)
                return
            completed = str(job.state or "").lower() in ("complete", "completed", "ready") or job.progress >= 100.0
            if completed and str(data.get("confirmation", "")) != PERMANENT_DELETE_CONFIRMATION:
                self.send_json_response(
                    {"success": False, "error": "Type DELETE to permanently remove this video and its file.", "required_confirmation": PERMANENT_DELETE_CONFIRMATION},
                    403,
                )
                return
            service.delete(job.job_id)
            self.send_json_response({"success": True})

        elif path == "/api/video-flow/videos/retry":
            video_id = str(data.get("id", ""))
            service = get_video_flow_service()
            job = service.get(video_id)
            if not job:
                self.send_json_response({"success": False, "error": "Video not found."}, 404)
                return
            meta = job.meta or {}
            source_text = meta.get("source_text", "")
            if not source_text:
                self.send_json_response({"success": False, "error": "The original request for this video is no longer available; generate again."}, 409)
                return
            new_job = service.queue(
                source_text,
                mode=meta.get("mode", "summary"),
                title=meta.get("title", ""),
                model_ref=meta.get("model_ref"),
                theme=meta.get("theme"),
                visual_direction=meta.get("visual_direction", ""),
                allow_external_ai=bool(meta.get("allow_external_ai", False)),
            )
            self.send_json_response({"success": True, "video": _shim_video(new_job), "job_id": new_job.job_id}, 202)

        elif path == "/api/video-flow/providers/connections/add":
            try:
                provider_id = str(data.get("provider", ""))
                keys = data.get("keys")
                if isinstance(keys, list):
                    added = [
                        video_flow_provider_service.add_connection(
                            provider_id,
                            name=str(item.get("name") or f"Key {index + 1}"),
                            secret=str(item.get("secret") or item.get("key") or ""),
                            priority=int(item.get("priority", index + 1)),
                            metadata=dict(item.get("metadata") or {}),
                        )
                        for index, item in enumerate(keys)
                        if isinstance(item, dict)
                    ]
                    self.send_json_response({"success": True, "connections": added})
                else:
                    connection = video_flow_provider_service.add_connection(
                        provider_id,
                        name=str(data.get("name") or "Connection"),
                        secret=str(data.get("secret") or data.get("key") or ""),
                        priority=int(data.get("priority", 1)),
                        metadata=dict(data.get("metadata") or {}),
                    )
                    self.send_json_response({"success": True, "connection": connection})
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/connections/update":
            try:
                connection = video_flow_provider_service.update_connection(
                    int(data.get("id", 0)),
                    name=data.get("name"),
                    secret=data.get("secret") or data.get("key"),
                    priority=data.get("priority", 1),
                    is_active=data.get("is_active", True),
                    metadata=data.get("metadata"),
                )
                self.send_json_response({"success": bool(connection), "connection": connection}, 200 if connection else 404)
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/connections/delete":
            deleted = video_flow_provider_service.delete_connection(int(data.get("id", 0)))
            self.send_json_response({"success": deleted}, 200 if deleted else 404)

        elif path == "/api/video-flow/providers/connections/toggle":
            connection = video_flow_provider_service.update_connection(
                int(data.get("id", 0)),
                is_active=bool(data.get("is_active", True)),
            )
            self.send_json_response({"success": bool(connection), "connection": connection}, 200 if connection else 404)

        elif path == "/api/video-flow/providers/connections/test":
            try:
                result = video_flow_provider_service.test_connection(int(data.get("id", 0)))
                self.send_json_response(result, 200 if result.get("success") else 400)
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 404)

        elif path == "/api/video-flow/providers/settings":
            provider_id = str(data.get("provider", ""))
            try:
                video_flow_provider_service.provider(provider_id)
                mode = str(data.get("load_balance_mode", "priority"))
                if mode not in {"priority", "round_robin"}:
                    raise ValueError("Load balance mode must be priority or round_robin.")
                video_flow_provider_service.set_setting(f"load_balance:{provider_id}", mode)
                self.send_json_response({"success": True, "load_balance_mode": mode})
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/models/add":
            try:
                model = video_flow_provider_service.add_model(
                    str(data.get("provider", "")),
                    str(data.get("model_id", "")),
                    str(data.get("display_name", "")),
                    list(data.get("capabilities", [])),
                )
                self.send_json_response({"success": True, "model": model})
            except (TypeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/models/toggle":
            changed = video_flow_provider_service.set_model_active(
                int(data.get("id", 0)),
                bool(data.get("is_active", True)),
            )
            self.send_json_response({"success": changed}, 200 if changed else 404)

        elif path == "/api/video-flow/providers/models/delete":
            deleted = video_flow_provider_service.delete_model(int(data.get("id", 0)))
            self.send_json_response({"success": deleted}, 200 if deleted else 404)

        elif path == "/api/video-flow/providers/oauth/start":
            try:
                result = video_flow_provider_service.start_oauth(str(data.get("provider", "")))
                self.send_json_response(result)
            except (OSError, RuntimeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/status":
            try:
                provider_id = str(data.get("provider", ""))
                status = video_flow_provider_service.oauth_status(provider_id, refresh=True)
                self.send_json_response({"success": True, "status": status})
            except ValueError as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/poll":
            try:
                result = video_flow_provider_service.oauth_poll(str(data.get("provider", "")))
                self.send_json_response({"success": True, **result})
            except (OAuthError, RuntimeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/import":
            try:
                connection = video_flow_provider_service.oauth_import(str(data.get("provider", "")))
                self.send_json_response({"success": True, "connection": connection})
            except (OAuthError, RuntimeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/refresh":
            try:
                connection = video_flow_provider_service.oauth_refresh(int(data.get("id", 0)))
                self.send_json_response({"success": True, "connection": connection})
            except (OAuthError, RuntimeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/video-flow/providers/oauth/exchange":
            try:
                connection = video_flow_provider_service.oauth_exchange(
                    str(data.get("provider", "")),
                    str(data.get("code", "")),
                    str(data.get("state", "")),
                    code_verifier=str(data.get("code_verifier", "")),
                )
                self.send_json_response({"success": True, "connection": connection})
            except (OAuthError, RuntimeError, ValueError) as exc:
                self.send_json_response({"success": False, "error": str(exc)}, 400)

        elif path == "/api/settings/update":
            key = data.get("key")
            value = data.get("value")
            allowed_settings = {
                "polishing_enabled": bool,
                "voice_flow_enabled": bool,
                "audio_flow_enabled": bool,
                "video_flow_enabled": bool,
                "press_enter_enabled": bool,
                "has_viewed_onboarding": bool,
                "dictionary_auto_learning_enabled": bool,
                "launch_at_login_enabled": bool,
                "push_to_talk_shortcut": str,
                "selected_mic_device": (str, int),
            }
            if not isinstance(key, str) or key not in allowed_settings:
                self.send_json_response({"success": False, "error": "Unknown setting"}, 400)
                return
            expected_type = allowed_settings[key]
            if key.endswith("_enabled") and type(value) is not bool:
                self.send_json_response({"success": False, "error": "Setting value must be boolean"}, 400)
                return
            if not key.endswith("_enabled") and not isinstance(value, expected_type):
                self.send_json_response({"success": False, "error": "Invalid setting value"}, 400)
                return
            if not storage.save_setting(key, value):
                self.send_json_response({"success": False, "error": "Could not persist setting"}, 500)
                return
            if hasattr(config, key):
                setattr(config, key, value)
            if key == "launch_at_login_enabled":
                try:
                    from voice_flow.gui.desktop_launcher import set_windows_auto_startup
                    set_windows_auto_startup(bool(value))
                except Exception as e:
                    print(f"[SETTINGS] Could not update auto-startup registry: {e}")
            print(f"[SETTINGS] {key} = {value}")
            self.send_json_response({"success": True, "key": key, "value": value})

        elif path == "/api/providers/all":
            all_conns = storage.get_all_provider_connections()
            self.send_json_response({"success": True, "connections": all_conns})

        elif path == "/api/providers/connections/add":
            provider = data.get("provider", "gemini").lower()
            name = data.get("name", "").strip()
            key = data.get("key", "").strip()
            priority = int(data.get("priority", 1))

            v_res = self.verify_api_key(provider, key)
            if v_res["success"]:
                new_conn = storage.add_provider_connection(provider, name, key, priority)
                self.send_json_response({"success": True, "connection": new_conn, "message": "Connection added successfully!"})
            else:
                self.send_json_response({"success": False, "error": v_res.get("error", "Validation failed.")})

        elif path == "/api/providers/connections/update":
            cid = int(data.get("id"))
            name = data.get("name", "").strip()
            key = data.get("key", "").strip()
            priority = int(data.get("priority", 1))
            success = storage.update_provider_connection(cid, name, key, priority)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/toggle":
            cid = int(data.get("id"))
            active = bool(data.get("is_active", True))
            success = storage.toggle_provider_connection(cid, active)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/delete":
            cid = int(data.get("id"))
            success = storage.delete_provider_connection(cid)
            self.send_json_response({"success": success})

        elif path == "/api/providers/connections/test":
            cid = data.get("id")
            provider = data.get("provider", "gemini").lower()
            key = data.get("key", "").strip()
            v_res = self.verify_api_key(provider, key)
            if cid:
                status_str = "Connected (200 OK)" if v_res["success"] else f"Error: {v_res.get('error', 'Failed')}"
                storage.update_connection_status(int(cid), status_str)
            self.send_json_response(v_res)

        elif path == "/api/providers/mode/save":
            provider = data.get("provider", "gemini").lower()
            mode = data.get("mode", "priority").lower()
            success = storage.save_provider_load_balance_mode(provider, mode)
            self.send_json_response({"success": success})

        elif path == "/api/providers/models/add":
            provider = data.get("provider", "gemini").lower()
            model_id = data.get("model_id", "").strip()
            display_name = data.get("display_name", "").strip() or model_id
            success = storage.add_provider_model(provider, model_id, display_name)
            self.send_json_response({"success": success, "models": storage.get_provider_models(provider)})

        elif path == "/api/providers/models/toggle":
            mid = int(data.get("id"))
            active = bool(data.get("is_active", True))
            success = storage.toggle_provider_model(mid, active)
            self.send_json_response({"success": success})

        else:
            self.send_error(404, "Endpoint not found")

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        origin = self.headers.get("Origin")
        if ALLOWED_ORIGINS is not None and origin and origin not in ALLOWED_ORIGINS:
            self.send_json_response({"success": False, "error": "Origin not allowed"}, 403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _stream_shim_video(self, video_id: str, *, download: bool = False) -> None:
        job = get_video_flow_service().get(video_id)
        if job is None:
            self.send_json_response({"success": False, "error": "Video job not found"}, 404); return
        path_str = (job.meta or {}).get("output_path") or str(data_dir() / "v3_projects" / video_id / "video.mp4")
        path = Path(path_str)
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
            self.send_header("Content-Disposition", f'attachment; filename="video_{video_id}.mp4"')
        else:
            self.send_header("Content-Disposition", f'inline; filename="video_{video_id}.mp4"')
        if status == 206: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        origin = self.headers.get("Origin")
        if ALLOWED_ORIGINS is not None and origin in ALLOWED_ORIGINS: self.send_header("Access-Control-Allow-Origin", origin)
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
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Gemini API Key Verified! Model ready for transcription polishing."}

            elif provider == "google":
                # First try Google Cloud TTS endpoint
                url = f"https://texttospeech.googleapis.com/v1/voices?key={key}&languageCode=en-US"
                req = urllib.request.Request(url, headers=ua_headers)
                try:
                    with urllib.request.urlopen(req, timeout=8) as response:
                        if response.status == 200:
                            return {"success": True, "message": "Google Cloud TTS API Key Verified! Text-to-speech ready."}
                except urllib.error.HTTPError:
                    # Fallback test: Google Gemini / Generative Language endpoint
                    alt_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    alt_req = urllib.request.Request(alt_url, headers=ua_headers)
                    with urllib.request.urlopen(alt_req, timeout=8) as response:
                        if response.status == 200:
                            return {"success": True, "message": "Google API Key Verified via Gemini AI Endpoint!"}
                    raise

            elif provider == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Groq API Key Verified! Llama-3.3 model active."}

            elif provider == "elevenlabs":
                url = "https://api.elevenlabs.io/v1/voices"
                headers = {"xi-api-key": key, **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"success": True, "message": "ElevenLabs Voice API Verified! TTS audio generation ready."}

            elif provider == "deepgram":
                url = "https://api.deepgram.com/v1/projects"
                headers = {"Authorization": f"Token {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Deepgram API Verified! Nova-3 speech model active."}

            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {key}", **ua_headers}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as response:
                    if response.status == 200:
                        return {"success": True, "message": "OpenAI API Verified! gpt-4o-mini model ready."}

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

        if len(key) < 20:
            return f"API key is too short ({len(key)} chars). Valid {provider.capitalize()} keys are typically 30+ characters."

        return None

    def send_video_file(self, video_id: str, *, download: bool = False) -> None:
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
        disposition = "attachment" if download else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="{path.name}"')
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
        """Serve the OAuth popup landing page.

        Runs inside the popup: when the provider redirects back with a code, the
        page relays it to the main app window via postMessage and closes itself.
        If the popup was closed early (or never opened), it shows a card with
        the code and a copy button so the user can complete the sign-in in the
        main app's manual fallback field.
        """
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]
        body = (
            OAUTH_CALLBACK_PAGE
            .replace("__OAUTH_CODE__", json.dumps(code))
            .replace("__OAUTH_STATE__", json.dumps(state))
            .replace("__OAUTH_ERROR__", json.dumps(error))
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json_response(self, data: any, status: int = 200) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        origin = self.headers.get("Origin")
        if ALLOWED_ORIGINS is not None and origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.end_headers()
        self.wfile.write(content)


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
    return {
        "id": job.job_id,
        "title": meta.get("title") or job.job_id,
        "status": public_status,
        "stage": job.message or public_status,
        "progress": int(job.progress),
        "playable": playable,
        "mode": meta.get("mode", "summary"),
        "engine_version": "v3-code2video",
        "created_at": getattr(job, "created_at", None) or 0.0,
        "duration_sec": meta.get("duration_sec", 0.0),
        "view_url": f"/api/video-flow/videos/file?id={job.job_id}",
        "download_url": f"/api/video-flow/videos/file?id={job.job_id}&download=1",
        "export_status": "exported" if playable else "not_requested",
        "error": meta.get("error_code", "") if public_status == "failed" else "",
    }


def _video_flow_catalog() -> dict:
    """Build the Video Flow model/theme catalog.

    Provider groups come from the isolated Video Flow provider registry
    (full provider list with real connection statuses, as on GitHub); the
    Groq entry is overlaid with the planning-gateway truth because the new
    engine's gateway reads main-storage connections. Models list the
    planner models the gateway can actually execute.
    """
    active = storage.get_setting("exec_policy_model", "openai/gpt-oss-120b")

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
                "name": "Groq Planning Gateway",
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

    local_group = list(service_catalog.get("local", []))
    if not any(item.get("id") == "local" for item in local_group):
        local_group.append(
            {"id": "local", "name": "Local Code2Video Generator", "category": "local", "status": "connected"}
        )

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
        ]
    except Exception:
        service_models = []

    models = service_models
    service_refs = {m["full_id"] for m in models}

    # Groq planning models run via the main-storage Groq connection even when
    # the isolated provider store has no Groq connection of its own.
    for full_id, display in [
        ("groq/openai/gpt-oss-120b", "Groq — gpt-oss-120b (Code2Video Planner)"),
        ("groq/openai/gpt-oss-20b", "Groq — gpt-oss-20b (fast planner)"),
        ("groq/qwen/qwen3.6-27b", "Groq — qwen3.6-27b (planner)"),
    ]:
        if full_id not in service_refs:
            models.append(
                {
                    "full_id": full_id,
                    "provider": "groq",
                    "provider_name": "Groq",
                    "display_name": display,
                    "available": bool(groq_connected),
                    "is_active": True,
                    "capabilities": ["code2video_planning"],
                }
            )
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

    try:
        combos = [
            {
                "ref": f"combo:{combo['name']}",
                "id": combo["id"],
                "name": combo["name"],
                "models": combo["models"],
                "strategy": combo["strategy"],
            }
            for combo in video_flow_provider_service.list_combos()
        ]
    except Exception:
        combos = []

    return {
        "providers": api_key_group + local_group + oauth_group,
        "provider_groups": {
            "oauth": oauth_group,
            "api_key": api_key_group,
            "local": local_group,
        },
        "models": models,
        "combos": combos,
        "active_model": active,
        "themes": ["auto", "voice-flow", "midnight", "paper", "neon", "ocean", "forest", "sunset", "mono"],
    }


def start_api_server(host: str = "127.0.0.1") -> None:
    try:
        ThreadingHTTPServer.allow_reuse_address = True
        httpd = ThreadingHTTPServer((host, PORT), VoiceFlowApiHandler)
        print(f"[API SERVER] Voice Flow Multithreaded Backend API listening on http://{host}:{PORT}")
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
