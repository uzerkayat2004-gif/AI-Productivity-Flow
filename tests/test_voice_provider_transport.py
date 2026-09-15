"""Mock sockets exercise the real request adapters without provider access."""
from collections import OrderedDict
import io
import json
from types import SimpleNamespace
import time

import pytest

import voice_flow.polisher as polish
import voice_flow.voice_gemini_transport as gemini
import voice_flow.voice_provider_transport as chat


class FakeConnection:
    created = []
    response = {}

    def __init__(self, host, port=None, timeout=None):
        self.host, self.timeout = host, timeout
        self.sock = SimpleNamespace(settimeout=lambda value: None)
        self.requests = []
        self.created.append(self)

    def connect(self):
        pass

    def request(self, method, path, body, headers):
        self.requests.append((path, json.loads(body), headers))

    def getresponse(self):
        response = io.BytesIO(json.dumps(self.response).encode())
        response.status = 200
        return response

    def close(self):
        self.sock = None


@pytest.fixture(autouse=True)
def isolated_transports(monkeypatch):
    FakeConnection.created = []
    monkeypatch.setattr(gemini, "_sessions", OrderedDict())
    monkeypatch.setattr(gemini, "_warm_connection", None)
    monkeypatch.setattr(chat, "_sessions", OrderedDict())
    monkeypatch.setattr(chat.http.client, "HTTPSConnection", FakeConnection)
    monkeypatch.setattr(chat.http.client, "HTTPConnection", FakeConnection)
    # All credentials below are synthetic and every network boundary is fake.
    monkeypatch.setattr(polish.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polish.storage, "get_all_api_keys", lambda: {"gemini": "synthetic"})
    monkeypatch.setattr(polish.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda model: False)
    monkeypatch.setattr(polish, "_apply_dictionary_safely", lambda text: text)


def test_actual_polisher_reuses_gemini_connection_and_accepts_output():
    text = "Please send the complete report to the review team today."
    FakeConnection.response = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
    engine = polish.TextPolisher()
    outcomes = []
    for _ in range(2):
        started = time.monotonic()
        assert engine.polish(text, model_ref="gemini/gemini-3.7-flash", deadline=started+5, speed_mode="balanced", outcome_callback=outcomes.append) == text
        assert time.monotonic()-started < .5
    assert outcomes == ["ai_accepted", "ai_accepted"]
    assert len(FakeConnection.created) == 1
    assert len(FakeConnection.created[0].requests) == 2
    _, body, headers = FakeConnection.created[0].requests[0]
    assert headers["x-goog-api-key"] == "synthetic"
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


def test_chat_reuses_connection_without_process_startup():
    FakeConnection.response = {"choices": [{"finish_reason": "stop", "message": {"content": "Complete output."}}]}
    args = dict(endpoint="https://test.invalid/v1/chat/completions", api_key="synthetic", model="gpt-5-test", messages=[{"role": "user", "content": "Polish"}], timeout_seconds=1)
    assert chat.request_chat(**args) == ("Complete output.", "ok")
    assert chat.request_chat(**args) == ("Complete output.", "ok")
    assert len(FakeConnection.created) == 1
    body = FakeConnection.created[0].requests[0][1]
    assert body["model"] == "gpt-5-test"
    assert "max_completion_tokens" in body and "temperature" not in body


def test_truncated_provider_results_are_not_published():
    FakeConnection.response = {"choices": [{"finish_reason": "length", "message": {"content": "Missing the ending"}}]}
    assert chat.request_chat(endpoint="https://test.invalid/v1/chat/completions", api_key="synthetic", model="test", messages=[], timeout_seconds=1) == (None, "truncated")
    FakeConnection.response = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "Missing the ending"}]}}]}
    assert gemini.request_gemini_polish(api_key="synthetic", model="gemini-3.7-flash", prompt="Polish", timeout_seconds=1) is None
    assert gemini.last_transport_diagnostic()["status"] == "truncated"


def test_interactive_timeout_does_not_disable_working_key(monkeypatch):
    engine = polish.TextPolisher()
    calls = []

    def timeout(*args, **kwargs):
        calls.append(True)
        engine._last_attempt_status = "timeout"
        return None

    monkeypatch.setattr(engine, "_try_provider_call", timeout)
    for _ in range(2):
        assert engine._polish_with_api_pool("Keep all of these words", {"gemini": "synthetic"}, model_ref="gemini/gemini-3.7-flash", deadline=time.monotonic()+1) is None
    assert len(calls) == 2
    assert not engine._rate_limited_keys


def test_exact_gateway_chat_provider_uses_native_transport(monkeypatch):
    import voice_flow.voice_polish_bridge as bridge
    from voice_flow.video_flow_service import ProviderModelGateway
    gateway = ProviderModelGateway(api_key="synthetic", provider="groq", model_id="selected-model", endpoint="https://test.invalid/v1/chat/completions")
    monkeypatch.setattr(ProviderModelGateway, "_from_video_provider_service", classmethod(lambda *args: gateway))
    monkeypatch.setattr(gateway, "request_isolated", lambda **kwargs: pytest.fail("Spawned a Python worker for a chat request"))
    FakeConnection.response = {"choices": [{"finish_reason": "stop", "message": {"content": "Complete output."}}]}
    assert bridge.request_polish("groq/selected-model", "Polish", timeout_seconds=1) == "Complete output."
    assert FakeConnection.created[0].requests[0][1]["model"] == "selected-model"


def test_busy_chat_connection_returns_immediately():
    FakeConnection.response = {"choices": [{"message": {"content": "Complete"}}]}
    args = dict(endpoint="https://test.invalid/v1/chat/completions", api_key="synthetic", model="selected", messages=[], timeout_seconds=5)
    chat.request_chat(**args)
    connection = next(iter(chat._sessions.values()))
    with connection.lock:
        started = time.monotonic()
        assert chat.request_chat(**args) == (None, "busy")
        assert time.monotonic()-started < .1


def test_cloud_command_pipeline_reaches_ai_after_expired_stt_target(monkeypatch):
    import threading
    import voice_flow.main as main
    base = SimpleNamespace(app_name="Editor", category="smart_clean", style_id="smart_clean", instruction="Keep all requirements.")
    current = main.DictationSession(123, "Editor", "smart_clean", "smart_clean", 0,
        resolved_style=base, stt_model_ref="groq/whisper-large-v3",
        polish_model_ref="gemini/gemini-3.7-flash", polish_speed_mode="fast")
    app = object.__new__(main.VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = main.DictationState.PROCESSING
    app.session = current
    app._post_release_deadline = time.monotonic()-3
    app.transcriber = SimpleNamespace(transcribe=lambda *a, **k: "Hey Voice Flow, make this a prompt: build a calendar with offline support")
    pasted, history = [], []
    app.injector = SimpleNamespace(paste_text=lambda text, *a, **k: pasted.append(text) or True)
    app.overlay = SimpleNamespace(show_error=lambda *a: None, show_done=lambda *a: None)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *a: None)
    app.recent_dictations = set()
    app._defer_history_insert = lambda *a, **k: None
    monkeypatch.setattr(main.storage, "update_dictation", lambda *a, **k: history.append(k) or True)
    monkeypatch.setattr(main, "polisher", polish.TextPolisher())
    monkeypatch.setattr(main, "smart_format", lambda text, *a: text)
    result = "Build a calendar with offline support."
    FakeConnection.response = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": result}]}}]}
    app._process_dictation_pipeline(current, object(), 5, record_id=1, use_streaming=False)
    assert pasted == [result]
    assert any(row.get("polished_text") == result and row.get("error_message") is None for row in history)
    assert len(FakeConnection.created) == 1
    prompt = FakeConnection.created[0].requests[0][1]["contents"][0]["parts"][0]["text"]
    assert "build a calendar with offline support" in prompt
    assert "Hey Voice Flow" not in prompt
