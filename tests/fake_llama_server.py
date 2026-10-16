"""Stand-in for llama-server used by the lifetime tests.

Understands the flags vf1_engine passes (-m, --host, --port, --alias, ...).
FAKE_LLAMA_DELAY: seconds before the port is bound (slow cold start).
FAKE_LLAMA_LOG: file that gets one "<pid>" line per started process.
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _arg(name: str, default: str = "") -> str:
    argv = sys.argv[1:]
    for i, value in enumerate(argv):
        if value == name and i + 1 < len(argv):
            return argv[i + 1]
    return default


def main() -> None:
    host = _arg("--host", "127.0.0.1")
    port = int(_arg("--port", "8080"))
    alias = _arg("--alias", "")
    model = _arg("-m", "")
    log_path = os.environ.get("FAKE_LLAMA_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
    time.sleep(float(os.environ.get("FAKE_LLAMA_DELAY", "0") or 0))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            elif self.path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": alias or model, "object": "model"}]})
            elif self.path == "/props":
                self._send(200, {"model_path": model, "model_alias": alias})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if self.path == "/completion":
                self._send(200, {"content": "fake completion", "timings": {}})
            else:
                self._send(404, {"error": "not found"})

    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
