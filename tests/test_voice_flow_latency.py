from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import voice_flow.main as main_module
import voice_flow.polisher as polisher_module
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp
from voice_flow.polisher import TextPolisher


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _configure_policy(monkeypatch, model_ref: str) -> None:
    monkeypatch.setattr(
        polisher_module.storage,
        "get_setting",
        lambda key, default=None: model_ref if key == "voice_flow_polish_model" else default,
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)


def test_selected_gemini_model_is_requested_once(monkeypatch) -> None:
    _configure_policy(monkeypatch, "gemini/gemini-3.5-flash")
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _Response({"candidates": [{"content": {"parts": [{"text": "Cleaned text."}]}}]})

    monkeypatch.setattr(polisher_module.urllib.request, "urlopen", fake_urlopen)

    result = TextPolisher()._polish_with_api_pool(
        "clean this text please",
        {"gemini": "fake-key"},
    )

    assert result == "Cleaned text."
    assert len(calls) == 1
    assert "/models/gemini-3.5-flash:generateContent" in calls[0][0].full_url
    assert 0 < calls[0][1] <= polisher_module.AI_POLISH_REQUEST_TIMEOUT_SECONDS
    assert json.loads(calls[0][0].data)["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}


def test_selected_groq_model_is_requested_once(monkeypatch) -> None:
    _configure_policy(monkeypatch, "groq/qwen/qwen3.6-27b")
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _Response({"choices": [{"message": {"content": "Cleaned text."}}]})

    monkeypatch.setattr(polisher_module.urllib.request, "urlopen", fake_urlopen)

    result = TextPolisher()._polish_with_api_pool(
        "clean this text please",
        {"groq": "fake-key"},
    )

    assert result == "Cleaned text."
    assert len(calls) == 1
    assert json.loads(calls[0][0].data.decode("utf-8"))["model"] == "qwen/qwen3.6-27b"
    assert 0 < calls[0][1] <= polisher_module.AI_POLISH_REQUEST_TIMEOUT_SECONDS


def test_failed_preferred_provider_fails_over_to_next_provider(monkeypatch) -> None:
    _configure_policy(monkeypatch, "gemini/gemini-3.5-flash")
    engine = TextPolisher()
    calls = []

    def provider_call(provider, key, system_prompt, user_content, model=None, timeout=None):
        calls.append((provider, model, timeout))
        return "Fallback cleaned." if provider == "groq" else None

    monkeypatch.setattr(engine, "_try_provider_call", provider_call)

    result = engine._polish_with_api_pool(
        "clean this text please",
        {"gemini": "gemini-key", "groq": "groq-key"},
    )

    assert result == "Fallback cleaned."
    assert calls == [
        ("gemini", "gemini-3.5-flash", polisher_module.AI_POLISH_REQUEST_TIMEOUT_SECONDS),
        ("groq", None, polisher_module.AI_POLISH_REQUEST_TIMEOUT_SECONDS),
    ]

def test_polish_budget_stops_provider_fanout_and_uses_local_cleanup(monkeypatch) -> None:
    engine = TextPolisher()
    calls = []
    clock = [0.0]

    def get_setting(key, default=None):
        if key == "polishing_enabled":
            return True
        if key == "voice_flow_polish_model":
            return "gemini/gemini-3.5-flash"
        return default

    monkeypatch.setattr(polisher_module.storage, "get_setting", get_setting)
    monkeypatch.setattr(
        polisher_module.storage,
        "get_all_api_keys",
        lambda: {"gemini": "gemini-key", "groq": "groq-key"},
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(polisher_module.dictionary_engine, "apply_dictionary_post_processing", lambda text: text)
    monkeypatch.setattr(polisher_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr("voice_flow.voice_polish_bridge.can_execute_model", lambda _ref: False)
    # This test pins the cloud-provider budget and the deterministic fallback.
    # The local model is a separate actor with its own coverage; disable it so
    # the assertion describes the intended no-local-model path.
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)

    def failed_call(provider, key, system_prompt, user_content, model=None, timeout=None):
        calls.append((provider, model, timeout))
        clock[0] = polisher_module.AI_POLISH_POOL_BUDGET_SECONDS
        return None

    monkeypatch.setattr(engine, "_try_provider_call", failed_call)

    assert engine.polish("um please clean this latency test with several more words added") == "Please clean this latency test with several more words added."
    # The selected model gets the first attempt; an exhausted budget prevents
    # further provider fanout and retains deterministic cleanup.
    assert calls == [
        ("gemini", "gemini-3.5-flash", polisher_module.AI_POLISH_REQUEST_TIMEOUT_SECONDS)
    ]


def test_pipeline_reuses_captured_style_snapshot(monkeypatch) -> None:
    captured_style = SimpleNamespace(
        app_name="VS Code",
        category="developer",
        style_id="developer_casual",
        instruction="Keep developer wording concise.",
    )
    session = DictationSession(
        target_hwnd=123,
        app_title="VS Code",
        app_category="developer",
        style_id="developer_casual",
        started_at=0.0,
        resolved_style=captured_style,
    )
    seen_styles = []

    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.session = session
    app.transcriber = SimpleNamespace(transcribe=lambda _audio: "hello this is a latency test")
    app.injector = SimpleNamespace(paste_text=lambda *_args, **_kwargs: True)
    app.overlay = SimpleNamespace(show_error=lambda *_args: None, show_done=lambda *_args: None, show_ready=lambda: None)
    app.recent_dictations = set()
    app.last_successful_transcript = None

    monkeypatch.setattr(
        main_module.style_engine,
        "resolve_for_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("style was resolved twice")),
    )
    monkeypatch.setattr(
        main_module.polisher,
        "polish",
        lambda text, style_instruction="", cleanup_level=None, force_ai=False, **_kwargs: seen_styles.append(style_instruction) or text,
    )
    monkeypatch.setattr(main_module, "smart_format", lambda text, _style, _context=None: text)
    monkeypatch.setattr(
        main_module,
        "storage",
        SimpleNamespace(update_dictation=lambda *_args, **_kwargs: True),
    )

    app._process_dictation_pipeline(session, object(), 1.0, record_id=1)

    # The pipeline composes the effective style from the CAPTURED session
    # snapshot (never re-resolving) and passes the instruction text on.
    assert seen_styles == [captured_style.instruction]
    assert app.state == DictationState.IDLE
