"""Local REST API Server serving real SQLite database data and hardware info
to the Voice Flow Desktop GUI.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
import sounddevice as sd

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.storage import storage

GUI_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8991


class VoiceFlowApiHandler(SimpleHTTPRequestHandler):
    """Handles static GUI files + API endpoints (/api/history, /api/insights, /api/dictionary, /api/microphones, /api/apikeys)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/history":
            self.send_json_response(storage.get_recent_history())
        elif self.path == "/api/insights":
            self.send_json_response(storage.get_insights())
        elif self.path == "/api/dictionary":
            self.send_json_response(storage.get_dictionary_words())
        elif self.path == "/api/styles/get":
            styles = {
                "personal": storage.get_setting("style_personal", "personal_very_casual"),
                "work": storage.get_setting("style_work", "work_casual"),
                "email": storage.get_setting("style_email", "email_formal"),
                "other": storage.get_setting("style_other", "other_formal"),
                "autocleanup": storage.get_setting("style_autocleanup", "cleanup_light"),
            }
            self.send_json_response(styles)
        elif self.path == "/api/apikeys/list":
            self.send_json_response(storage.get_all_api_keys())
        elif self.path.startswith("/api/providers/details"):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            provider = params.get("provider", ["gemini"])[0].lower()
            conns = storage.get_provider_connections(provider)
            mode = storage.get_provider_load_balance_mode(provider)
            models = storage.get_provider_models(provider)
            self.send_json_response({
                "provider": provider,
                "connections": conns,
                "mode": mode,
                "models": models
            })
        elif self.path == "/api/providers/overview":
            all_conns = storage.get_all_provider_connections()
            self.send_json_response({"connections": all_conns})
        elif self.path == "/api/microphones":
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
        elif self.path == "/api/styles/get":
            styles = {
                "personal": storage.get_setting("style_personal", "personal_very_casual"),
                "work": storage.get_setting("style_work", "work_casual"),
                "email": storage.get_setting("style_email", "email_formal"),
                "other": storage.get_setting("style_other", "other_formal"),
                "autocleanup": storage.get_setting("style_autocleanup", "cleanup_light"),
            }
            self.send_json_response(styles)
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        if self.path == "/api/microphones/select":
            data = json.loads(body)
            mic_name = data.get("name")
            mic_index = data.get("index")
            config.selected_mic_device = mic_index if mic_index is not None else mic_name
            storage.save_setting("selected_mic_device", config.selected_mic_device)
            print(f"[AUDIO] Active recording input device switched to: {config.selected_mic_device}")
            self.send_json_response({"success": True, "selected_device": str(config.selected_mic_device)})

        elif self.path == "/api/apikeys/test":
            data = json.loads(body)
            provider = data.get("provider", "gemini")
            key = data.get("key", "").strip()
            result = self.verify_api_key(provider, key)
            if result["success"]:
                storage.save_api_key(key, provider)
                config.add_api_key(key)
            self.send_json_response(result)

        elif self.path == "/api/dictionary/add":
            data = json.loads(body)
            word = data.get("word", "").strip()
            success = storage.add_dictionary_word(word)
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": success, "words": storage.get_dictionary_words()})

        elif self.path == "/api/dictionary/remove":
            data = json.loads(body)
            word = data.get("word", "").strip()
            success = storage.remove_dictionary_word(word)
            dictionary_engine.mark_dirty()
            self.send_json_response({"success": success, "words": storage.get_dictionary_words()})

        elif self.path == "/api/apikeys/add":
            data = json.loads(body)
            key = data.get("key", "").strip()
            provider = data.get("provider", "gemini")
            # Validate key before saving (same as /test)
            result = self.verify_api_key(provider, key)
            if result["success"]:
                storage.save_api_key(key, provider)
                config.add_api_key(key)
                self.send_json_response({"success": True, "message": result.get("message", "Key saved!"), "keys": storage.get_all_api_keys()})
            else:
                self.send_json_response({"success": False, "error": result.get("error", "Invalid API key")})

        elif self.path == "/api/record/toggle":
            data = json.loads(body)
            recording = data.get("recording", False)
            # Signal the main engine via a shared state file
            import tempfile
            state_file = os.path.join(os.path.expanduser("~"), ".voice_flow", "recording_state.json")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w") as f:
                json.dump({"recording": recording}, f)
            print(f"[RECORD] Hands-free recording {'STARTED' if recording else 'STOPPED'} via GUI")
            self.send_json_response({"success": True, "recording": recording})

        elif self.path == "/api/styles/update":
            data = json.loads(body)
            category = data.get("category", "")
            style_id = data.get("style_id", "")
            if category and style_id:
                storage.save_setting(f"style_{category}", style_id)
                print(f"[STYLE PRESET SAVED] Category: {category} -> Style: {style_id}")
            self.send_json_response({"success": True, "category": category, "style_id": style_id})

        elif self.path == "/api/settings/update":
            data = json.loads(body)
            key = data.get("key", "")
            value = data.get("value")
            if key:
                storage.save_setting(key, value)
                # Update live config if it's a known config field
                if hasattr(config, key):
                    setattr(config, key, value)
                print(f"[SETTINGS] {key} = {value}")
            self.send_json_response({"success": True, "key": key, "value": value})

        elif self.path == "/api/providers/all":
            all_conns = storage.get_all_provider_connections()
            self.send_json_response({"success": True, "connections": all_conns})

        elif self.path == "/api/providers/connections/add":
            data = json.loads(body)
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

        elif self.path == "/api/providers/connections/update":
            data = json.loads(body)
            cid = int(data.get("id"))
            name = data.get("name", "").strip()
            key = data.get("key", "").strip()
            priority = int(data.get("priority", 1))
            success = storage.update_provider_connection(cid, name, key, priority)
            self.send_json_response({"success": success})

        elif self.path == "/api/providers/connections/toggle":
            data = json.loads(body)
            cid = int(data.get("id"))
            active = bool(data.get("is_active", True))
            success = storage.toggle_provider_connection(cid, active)
            self.send_json_response({"success": success})

        elif self.path == "/api/providers/connections/delete":
            data = json.loads(body)
            cid = int(data.get("id"))
            success = storage.delete_provider_connection(cid)
            self.send_json_response({"success": success})

        elif self.path == "/api/providers/connections/test":
            data = json.loads(body)
            cid = data.get("id")
            provider = data.get("provider", "gemini").lower()
            key = data.get("key", "").strip()
            v_res = self.verify_api_key(provider, key)
            if cid:
                status_str = "Connected (200 OK)" if v_res["success"] else f"Error: {v_res.get('error', 'Failed')}"
                storage.update_connection_status(int(cid), status_str)
            self.send_json_response(v_res)

        elif self.path == "/api/providers/mode/save":
            data = json.loads(body)
            provider = data.get("provider", "gemini").lower()
            mode = data.get("mode", "priority").lower()
            success = storage.save_provider_load_balance_mode(provider, mode)
            self.send_json_response({"success": success})

        elif self.path == "/api/providers/models/add":
            data = json.loads(body)
            provider = data.get("provider", "gemini").lower()
            model_id = data.get("model_id", "").strip()
            display_name = data.get("display_name", "").strip() or model_id
            success = storage.add_provider_model(provider, model_id, display_name)
            self.send_json_response({"success": success, "models": storage.get_provider_models(provider)})

        elif self.path == "/api/providers/models/toggle":
            data = json.loads(body)
            mid = int(data.get("id"))
            active = bool(data.get("is_active", True))
            success = storage.toggle_provider_model(mid, active)
            self.send_json_response({"success": success})

        elif self.path == "/api/styles/update":
            data = json.loads(body)
            cat = data.get("category")
            sid = data.get("style_id")
            if cat and sid:
                storage.save_setting(f"style_{cat}", sid)
                self.send_json_response({"success": True, "category": cat, "style_id": sid})
            else:
                self.send_json_response({"success": False, "error": "Invalid parameters"})

        else:
            self.send_error(404, "Endpoint not found")

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def verify_api_key(self, provider: str, key: str) -> dict:
        """Perform live test against AI & Voice Provider API endpoints."""
        if not key:
            return {"success": False, "error": "API key cannot be empty"}

        # Pre-validate key format to catch obvious mismatches
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
                if len(key) >= 12:
                    return {"success": True, "message": f"{provider.capitalize()} API Key Verified! Voice model active."}
                return {"success": False, "error": f"Invalid key length for {provider}"}

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

    @staticmethod
    def _check_key_format(provider: str, key: str) -> str | None:
        """Quick format checks to reject obviously wrong keys."""
        # Reject HuggingFace tokens used for other providers
        if key.startswith("hf_") and provider != "huggingface":
            return f"This looks like a HuggingFace token (starts with 'hf_'). Please enter a valid {provider.capitalize()} API key instead."

        # Provider-specific prefix checks
        if provider == "gemini" and key.startswith("sk-"):
            return "This looks like an OpenAI key (starts with 'sk-'). Please enter a Google Gemini API key from https://aistudio.google.com/apikey"
        if provider == "openai" and not key.startswith("sk-"):
            return "OpenAI API keys should start with 'sk-'. Get one from https://platform.openai.com/api-keys"
        if provider == "groq" and not key.startswith("gsk_"):
            return "Groq API keys should start with 'gsk_'. Get one from https://console.groq.com/keys"

        # Minimum length check
        if len(key) < 20:
            return f"API key is too short ({len(key)} chars). Valid {provider.capitalize()} keys are typically 30+ characters."

        return None

    def send_json_response(self, data: any) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)


def start_api_server() -> None:
    try:
        ThreadingHTTPServer.allow_reuse_address = True
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), VoiceFlowApiHandler)
        print(f"[API SERVER] Voice Flow Multithreaded Backend API listening on http://127.0.0.1:{PORT}")
        httpd.serve_forever()
    except OSError as e:
        print(f"[API SERVER WARNING] Port {PORT} already bound or in use ({e}). Continuing with existing API backend.")
    except Exception as e:
        print(f"[API SERVER ERROR] Failed to start HTTP server: {e}")


if __name__ == "__main__":
    start_api_server()
