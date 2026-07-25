"""Local REST API Server serving real SQLite database data and hardware info
to the Voice Flow Desktop GUI.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import sounddevice as sd

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow.storage import storage

GUI_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8991


class VoiceFlowApiHandler(SimpleHTTPRequestHandler):
    """Handles static GUI files + API endpoints (/api/history, /api/insights, /api/dictionary, /api/mics)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=GUI_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/history":
            self.send_json_response(storage.get_recent_history())
        elif self.path == "/api/insights":
            self.send_json_response(storage.get_insights())
        elif self.path == "/api/dictionary":
            self.send_json_response(storage.get_dictionary_words())
        elif self.path == "/api/microphones":
            try:
                devices = sd.query_devices()
                mics = [d["name"] for d in devices if d["max_input_channels"] > 0]
                self.send_json_response(mics)
            except Exception:
                self.send_json_response(["Default System Microphone"])
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        if self.path == "/api/dictionary/add":
            data = json.loads(body)
            word = data.get("word", "").strip()
            success = storage.add_dictionary_word(word)
            dictionary_engine.refresh_words()
            self.send_json_response({"success": success, "words": storage.get_dictionary_words()})

        elif self.path == "/api/dictionary/remove":
            data = json.loads(body)
            word = data.get("word", "").strip()
            success = storage.remove_dictionary_word(word)
            dictionary_engine.refresh_words()
            self.send_json_response({"success": success, "words": storage.get_dictionary_words()})

        elif self.path == "/api/apikeys/add":
            data = json.loads(body)
            key = data.get("key", "").strip()
            success = config.add_api_key(key)
            self.send_json_response({"success": success, "keys": config.get_api_keys()})

        else:
            self.send_error(404, "Endpoint not found")

    def send_json_response(self, data: any) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)


def start_api_server() -> None:
    httpd = HTTPServer(("127.0.0.1", PORT), VoiceFlowApiHandler)
    print(f"[API SERVER] Voice Flow Backend API listening on http://127.0.0.1:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    start_api_server()
