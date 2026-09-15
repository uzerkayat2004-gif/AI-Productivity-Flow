"""Regression coverage for explicit Voice Flow provider selections.

These tests use only fakes: no credentials, provider requests, or production
database access are permitted here.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

from voice_flow import polisher as polisher_module
from voice_flow import stt_engines
from voice_flow import transcriber as transcriber_module
from voice_flow.polisher import TextPolisher
from voice_flow.transcriber import Transcriber


def _transcriber_without_loader() -> Transcriber:
    instance = Transcriber.__new__(Transcriber)
    instance.model = object()
    instance.category_hint = None
    instance._lock = __import__("threading").Lock()
    instance._transcribe_lock = __import__("threading").Lock()
    instance._loading = False
    return instance


def test_short_dictation_uses_explicit_cloud_stt_model(monkeypatch):
    """A 5-second recording must not silently use local Whisper instead."""
    selected = "deepgram/nova-3"
    calls: list[str] = []
    monkeypatch.setattr(
        transcriber_module.storage if hasattr(transcriber_module, "storage") else __import__("voice_flow.storage", fromlist=["storage"]).storage,
        "get_setting",
        lambda key, default=None: selected if key == "voice_flow_stt_model" else default,
    )
    monkeypatch.setattr(transcriber_module, "enhance_for_stt", lambda audio, *_a, **_k: (audio, "off"))
    monkeypatch.setattr(transcriber_module, "vad_threshold_for", lambda _profile: 0.2)
    monkeypatch.setattr(transcriber_module.stt_engines, "transcribe_cloud", lambda _audio, model, **_kwargs: calls.append(model) or "cloud words")
    monkeypatch.setattr(Transcriber, "_transcribe_local", lambda *_a, **_k: "local words")

    text = _transcriber_without_loader().transcribe(np.ones(16_000 * 5, dtype=np.float32))

    assert text == "cloud words"
    assert calls == [selected]


def test_explicit_polish_model_is_called_before_fast_lane(monkeypatch):
    """Balanced speed must not replace an explicit model with Gemini Lite."""
    selected = "groq/llama-3.3-70b-versatile"
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        polisher_module.storage,
        "get_setting",
        lambda key, default=None: selected if key == "voice_flow_polish_model" else ("balanced" if key == "voice_flow_polish_speed_mode" else default),
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})

    polisher = TextPolisher()
    def fake_call(provider, _key, _system, _content, model=None, timeout=0):
        calls.append((provider, model))
        return "one two three four five six seven eight nine ten"
    monkeypatch.setattr(polisher, "_try_provider_call", fake_call)

    text = polisher._polish_with_api_pool(
        "one two three four five six seven eight nine ten",
        {"gemini": "fake-gemini", "groq": "fake-groq"},
    )

    assert text
    assert calls == [("groq", "llama-3.3-70b-versatile")]


def test_session_polish_model_snapshot_wins_over_later_setting(monkeypatch):
    """A provider change during recording cannot reroute the released text."""
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda *_a, **_k: "gemini/gemini-3.5-flash-lite")
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    polisher = TextPolisher()
    monkeypatch.setattr(
        polisher,
        "_try_provider_call",
        lambda provider, _key, _system, _content, model=None, timeout=0: calls.append((provider, model)) or "one two three four five six seven eight nine ten",
    )

    text = polisher._polish_with_api_pool(
        "one two three four five six seven eight nine ten",
        {"gemini": "later-key", "groq": "snapshot-key"},
        model_ref="groq/llama-3.3-70b-versatile",
    )

    assert text
    assert calls == [("groq", "llama-3.3-70b-versatile")]


def test_explicit_polish_and_force_ai_do_not_bypass_short_phrases(monkeypatch):
    monkeypatch.setattr(polisher_module.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {"groq": "key"})
    monkeypatch.setattr(polisher_module.storage, "get_all_provider_connections", lambda: {})
    monkeypatch.setattr(polisher_module.dictionary_engine, "apply_dictionary_post_processing", lambda text: text)
    polisher = TextPolisher()
    calls: list[str | None] = []
    monkeypatch.setattr(polisher, "_try_provider_call", lambda *_a, model=None, **_k: calls.append(model) or "Make this formal please.")

    assert polisher.polish("make this formal please", model_ref="groq/llama-3.3-70b-versatile")
    assert calls == ["llama-3.3-70b-versatile"]
    calls.clear()
    assert polisher.polish("make this formal please", force_ai=True)
    assert calls == [None]


def test_selected_local_model_is_not_replaced_by_bundled_base(monkeypatch):
    loaded: list[object] = []

    class FakeModel:
        def __init__(self, model_ref, **_kwargs):
            loaded.append(model_ref)

    instance = Transcriber.__new__(Transcriber)
    instance.model = None
    instance._loading = False
    instance._lock = __import__("threading").Lock()
    monkeypatch.setattr(transcriber_module, "WhisperModel", FakeModel)
    monkeypatch.setattr(__import__("voice_flow.runtime_env", fromlist=["runtime_env"]), "whisper_model_path", lambda: "bundled/base.en")

    instance._load_model_bg("local/faster-whisper-tiny.en")

    assert loaded == ["tiny.en"]
    assert instance._loaded_model_ref == "tiny.en"


def test_flux_routes_to_its_own_adapter_without_remapping(monkeypatch):
    """Selecting Flux must invoke Flux, never Deepgram's nova-3 batch path."""
    calls = []
    monkeypatch.setattr(stt_engines, "_key_for", lambda _provider: "fake")
    monkeypatch.setattr(stt_engines, "_deepgram_flux", lambda audio, key, model, **kwargs: calls.append((key, model, kwargs)) or "Flux words")

    text = stt_engines.transcribe_cloud(np.zeros(32, dtype=np.float32), "deepgram/flux-general-en", vocabulary=["Voice Flow"])

    assert text == "Flux words"
    assert calls == [("fake", "flux-general-en", {"vocabulary": ["Voice Flow"], "poll_seconds": 300, "deadline": None})]


def test_flux_waits_for_complete_final_turn_and_sends_controls(monkeypatch):
    """Queued partial turns never escape as a completed dictation."""
    import websockets.sync.client

    class FakeSocket:
        def __init__(self):
            self.sent = []
            self.messages = iter([
                json.dumps({"type": "Connected"}),
                json.dumps({"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 0,
                            "audio_window_end": 0.4, "transcript": "partial words"}),
                json.dumps({"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 1,
                            "audio_window_end": 1.0, "transcript": "complete words"}),
            ])
            self.closed = False
        def send(self, value): self.sent.append(value)
        def recv(self, timeout): return next(self.messages)
        def close(self): self.closed = True

    socket = FakeSocket()
    connection_args = {}
    def fake_connect(url, **kwargs):
        connection_args["url"] = url
        connection_args.update(kwargs)
        return socket
    monkeypatch.setattr(websockets.sync.client, "connect", fake_connect)

    text = stt_engines._deepgram_flux(np.ones(16_000, dtype=np.float32), "fake", "flux-general-en", ["Voice Flow", "voice flow"])

    assert text == "partial words complete words"
    assert "model=flux-general-en" in connection_args["url"]
    assert "encoding=linear16" in connection_args["url"] and "sample_rate=16000" in connection_args["url"]
    assert connection_args["additional_headers"] == {"Authorization": "Token fake"}
    assert socket.sent[-2:] == ['{"type": "ForceEndTurn"}', '{"type": "CloseStream"}']
    frames = socket.sent[:-2]
    assert all(len(frame) == 2560 for frame in frames[:-1])
    assert 0 < len(frames[-1]) <= 2560
    # A float32 1.0 source must become full-scale signed linear16 rather than
    # the near-silent 1-value payload produced by a bare int16 cast.
    assert int.from_bytes(frames[0][:2], "little", signed=True) == 32767
    assert socket.closed


def test_flux_accepts_manual_final_turn_when_audio_window_lags(monkeypatch):
    """Manual EndOfTurn confirms audio received before ForceEndTurn."""
    import websockets.sync.client

    class FakeSocket:
        def send(self, _value): pass
        def recv(self, timeout):
            return json.dumps({"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 0,
                               "audio_window_end": 0.05, "trigger": "manual",
                               "transcript": "spoken words"})
        def close(self): pass

    monkeypatch.setattr(websockets.sync.client, "connect", lambda *_a, **_k: FakeSocket())
    audio = np.concatenate((np.ones(6400, dtype=np.float32), np.zeros(9600, dtype=np.float32)))
    assert stt_engines._deepgram_flux(
        audio, "fake", "flux-general-en", deadline=time.monotonic() + 0.2
    ) == "spoken words"


def test_flux_timeout_never_returns_partial_turn(monkeypatch):
    """Timeout after only a partial event must make the normal fallback run."""
    import websockets.sync.client

    class FakeSocket:
        def __init__(self): self.calls = 0
        def send(self, _value): pass
        def recv(self, timeout):
            self.calls += 1
            if self.calls == 1:
                return json.dumps({"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 0,
                                   "audio_window_end": 0.1, "transcript": "partial words"})
            raise TimeoutError("timed out")
        def close(self): pass
    monkeypatch.setattr(websockets.sync.client, "connect", lambda *_a, **_k: FakeSocket())

    with pytest.raises(stt_engines.STTError, match="connection failed"):
        stt_engines._deepgram_flux(np.ones(16_000, dtype=np.float32), "fake", "flux-general-en")


def test_cloud_join_preserves_time_for_local_fallback(monkeypatch):
    """A timed-out chosen provider cannot consume the full caller deadline."""
    selected = "deepgram/nova-3"
    local_started: list[float] = []
    monkeypatch.setattr(
        __import__("voice_flow.storage", fromlist=["storage"]).storage,
        "get_setting",
        lambda key, default=None: selected if key == "voice_flow_stt_model" else default,
    )
    monkeypatch.setattr(transcriber_module, "enhance_for_stt", lambda audio, *_a, **_k: (audio, "off"))
    monkeypatch.setattr(transcriber_module, "vad_threshold_for", lambda _profile: 0.2)
    monkeypatch.setattr(transcriber_module.stt_engines, "transcribe_cloud", lambda *_a, **_k: time.sleep(0.5) or "")
    monkeypatch.setattr(Transcriber, "_transcribe_local", lambda _self, _audio, **kwargs: local_started.append(time.monotonic()) or "local words")

    deadline = time.monotonic() + 0.4
    text = _transcriber_without_loader().transcribe(np.ones(16_000, dtype=np.float32), deadline=deadline)

    assert text == "local words"
    assert local_started and local_started[0] < deadline
