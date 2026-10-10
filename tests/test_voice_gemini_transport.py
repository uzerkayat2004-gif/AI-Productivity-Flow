"""Voice-only Gemini transport contract tests; no provider request is sent."""

from __future__ import annotations

import json


def test_native_transport_reuses_a_completed_connection_and_preserves_gemini_policy(monkeypatch):
    from voice_flow import voice_gemini_transport as transport

    transport._sessions.clear()
    created = []

    class Response:
        status = 200
        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [
                {"thought": True, "text": "hidden"}, {"text": "She does not know."}
            ]}}]}).encode()

    class Connection:
        sock = None
        def __init__(self, host, timeout):
            created.append((host, timeout))
            self.requests = []
        def request(self, method, path, body, headers):
            self.requests.append((method, path, json.loads(body), headers))
        def connect(self):
            return None
        def getresponse(self):
            return Response()
        def close(self):
            return None

    monkeypatch.setattr(transport.http.client, "HTTPSConnection", Connection)
    for _ in range(2):
        assert transport.request_gemini_polish(api_key="synthetic-key", model="gemini-3.6-flash", prompt="clean this", timeout_seconds=2.5) == "She does not know."

    assert len(created) == 1
    request = next(iter(transport._sessions.values())).connection.requests[0]
    assert request[1].endswith("/gemini-3.6-flash:generateContent")
    assert request[2]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert request[2]["generationConfig"]["maxOutputTokens"] == 4096
    assert request[3]["x-goog-api-key"] == "synthetic-key"


def test_rotated_credential_gets_a_different_connection(monkeypatch):
    from voice_flow import voice_gemini_transport as transport

    transport._sessions.clear()
    created = []

    class Response:
        status = 200
        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'

    class Connection:
        sock = None
        def __init__(self, *_args, **_kwargs):
            created.append(self)
        def request(self, *_args, **_kwargs):
            return None
        def connect(self):
            return None
        def getresponse(self):
            return Response()
        def close(self):
            return None

    monkeypatch.setattr(transport.http.client, "HTTPSConnection", Connection)
    for key in ("first-key", "second-key"):
        assert transport.request_gemini_polish(api_key=key, model="gemini-3.6-flash", prompt="clean", timeout_seconds=1) == "ok"
    assert len(created) == 2


def test_tls_warmup_sends_no_request_and_is_adopted_by_the_first_model_call(monkeypatch):
    from voice_flow import voice_gemini_transport as transport

    transport._sessions.clear()
    transport._warm_connection = None
    created = []

    class Response:
        status = 200
        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'

    class Connection:
        sock = None
        def __init__(self, *_args, **_kwargs):
            created.append(self)
            self.request_count = 0
        def connect(self):
            return None
        def request(self, *_args, **_kwargs):
            self.request_count += 1
        def getresponse(self):
            return Response()
        def close(self):
            return None

    monkeypatch.setattr(transport.http.client, "HTTPSConnection", Connection)
    transport.warm_gemini_connection()
    assert len(created) == 1
    assert created[0].request_count == 0
    assert transport.request_gemini_polish(api_key="key", model="gemini-3.6-flash", prompt="clean", timeout_seconds=1) == "ok"
    assert len(created) == 1
    assert created[0].request_count == 1


def test_reused_closed_connection_uses_the_current_request_timeout(monkeypatch):
    """A peer-closed keep-alive socket reconnects under the new deadline."""
    from voice_flow import voice_gemini_transport as transport

    transport._sessions.clear()
    transport._warm_connection = None
    request_timeouts = []

    class Response:
        status = 200

        def read(self):
            return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'

    class Connection:
        sock = None

        def __init__(self, _host, timeout):
            self.timeout = timeout

        def connect(self):
            return None

        def request(self, _method, _path, body, **_kwargs):
            request_timeouts.append(self.timeout)
            self.payload = json.loads(body)

        def getresponse(self):
            return Response()

        def close(self):
            return None

    monkeypatch.setattr(transport.http.client, "HTTPSConnection", Connection)
    assert transport.request_gemini_polish(
        api_key="key", model="gemini-3.5-flash-lite", prompt="clean", timeout_seconds=2.5
    ) == "ok"
    assert transport.request_gemini_polish(
        api_key="key", model="gemini-3.5-flash-lite", prompt="clean", timeout_seconds=0.2
    ) == "ok"

    assert 0 < request_timeouts[1] <= 0.2
    assert next(iter(transport._sessions.values())).connection.payload["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "low"
    }


def test_three_voice_polish_modes_set_supported_gemini_reasoning_levels():
    from voice_flow import voice_gemini_transport as transport

    assert transport._thinking_level_for("gemini-3.5-flash-lite", "fast") == "minimal"
    # Balanced cleanup uses the supported low tier across Gemini 3 text
    # models; this also keeps 3.7/3.8 on their minimum accepted level.
    assert transport._thinking_level_for("gemini-3.5-flash-lite", "balanced") == "low"
    assert transport._thinking_level_for("gemini-3.5-flash-lite", "quality") == "high"
    # 3.7 Flash rejects minimal, so its fast policy uses its lowest supported
    # tier rather than failing the exact selected model.
    assert transport._thinking_level_for("gemini-3.7-flash", "fast") == "low"
    assert transport._thinking_level_for("gemini-3.7-flash", "balanced") == "low"
    assert transport._thinking_level_for("gemini-3.8-flash", "balanced") == "low"
    assert transport._thinking_level_for("gemini-2.5-flash", "quality") is None


def test_fast_mode_respects_pro_and_new_flash_minimum_levels():
    from voice_flow import voice_gemini_transport as transport
    assert transport._thinking_level_for("gemini-3.1-pro-preview", "fast") == "low"
    assert transport._thinking_level_for("gemini-3.8-flash", "fast") == "low"
