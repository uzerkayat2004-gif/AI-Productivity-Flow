"""Voice Flow speed fixes for v1.0.7 (local Whisper + local polish).

1. A downloaded polish model (S1-mini / LFM) must never become the speech
   model. v1.0.6 promoted it, so Whisper never loaded and every dictation
   waited ~15 s for nothing.
2. Local polish models stay warm as long as the speech model (was 10 s).
3. A fresh S1 load primes the fixed system prompt so the first polish only
   evaluates the transcript.
4. A local Whisper chunk stream with one late chunk is waited for instead of
   being thrown away and the whole recording decoded a second time.
"""
from __future__ import annotations

import logging
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from voice_flow import downloadable_models, local_model_resources, s1_engine, lfm_engine
from voice_flow import transcriber as T


# --- 1. polish models are never speech models ------------------------------

def _fake_downloaded(monkeypatch, model_ids):
    def status(model_id):
        spec = downloadable_models.get_model_spec(model_id)
        if spec and spec["id"] in model_ids:
            return {**spec, "status": "downloaded", "file_exists": True}
        return {"status": "not_downloaded", "file_exists": False}
    monkeypatch.setattr(downloadable_models, "get_model_status", status)


class _Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_setting(self, key, default=None):
        return self.values.get(key, default)

    def save_setting(self, key, value):
        self.values[key] = value


def test_polish_model_refs_are_recognised():
    for ref in ("local/s1-mini-q4_k_m", "superwhisper/s1-mini-q4_k_m", "local/lfm2.5-350m-qad-q4_0", "s1-mini"):
        assert downloadable_models.is_polish_model_ref(ref), ref
    for ref in ("local/faster-whisper-base.en", "local/nemotron-speech-streaming-en-0.6b", "groq/whisper-large-v3", "", None):
        assert not downloadable_models.is_polish_model_ref(ref), ref


def test_downloaded_polish_model_is_not_promoted_to_speech(monkeypatch):
    from voice_flow import storage as storage_module

    settings = _Settings()
    monkeypatch.setattr(storage_module, "storage", settings)
    _fake_downloaded(monkeypatch, {"liquid/lfm2.5-350m-qad-q4_0", "superwhisper/s1-mini-q4_k_m"})
    loads = []
    tr = object.__new__(T.Transcriber)
    tr._load_model_bg = lambda model: loads.append(model)

    tr._load_active_model_bg()

    assert settings.values.get("voice_flow_stt_model", "local/faster-whisper-base.en") == "local/faster-whisper-base.en"
    assert loads == ["base.en"]
    assert T.Transcriber._local_model_name("local/faster-whisper-base.en") == "base.en"
    assert T.Transcriber._local_model_name("groq/whisper-large-v3") == "base.en"


def test_saved_polish_model_as_speech_is_repaired(monkeypatch):
    from voice_flow import storage as storage_module

    settings = _Settings({"voice_flow_stt_model": "local/s1-mini-q4_k_m"})
    monkeypatch.setattr(storage_module, "storage", settings)
    _fake_downloaded(monkeypatch, {"superwhisper/s1-mini-q4_k_m"})
    loads = []
    tr = object.__new__(T.Transcriber)
    tr._load_model_bg = lambda model: loads.append(model)

    tr._load_active_model_bg()

    assert settings.values["voice_flow_stt_model"] == "local/faster-whisper-base.en"
    assert loads == ["base.en"]
    # A session snapshot taken before the repair still resolves to Whisper.
    assert T.Transcriber._local_model_name("local/s1-mini-q4_k_m") == "base.en"


def test_downloaded_nemotron_is_still_promoted(monkeypatch):
    from voice_flow import storage as storage_module

    settings = _Settings()
    monkeypatch.setattr(storage_module, "storage", settings)
    _fake_downloaded(monkeypatch, {"nvidia/nemotron-speech-streaming-en-0.6b", "superwhisper/s1-mini-q4_k_m"})
    loads = []
    tr = object.__new__(T.Transcriber)
    tr._load_model_bg = lambda model: loads.append(model)

    tr._load_active_model_bg()

    assert settings.values["voice_flow_stt_model"] == "local/nemotron-speech-streaming-en-0.6b"


# --- 2. local polish models stay warm between dictations -------------------

def test_local_polish_models_share_the_speech_warm_window():
    assert s1_engine.S1_WARM_IDLE_SECONDS == local_model_resources.LOCAL_MODEL_IDLE_SECONDS
    assert lfm_engine.LFM_WARM_IDLE_SECONDS == local_model_resources.LOCAL_MODEL_IDLE_SECONDS


def test_polish_lease_is_not_capped_at_thirty_seconds(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(local_model_resources, "_idle_clock", lambda: clock["now"])
    released = []
    local_model_resources.register_idle_cleanup(
        "speed-test-polish", lambda now: released.append(now) or True, kind="polish"
    )
    try:
        lease = local_model_resources.acquire_model_use("polish")
        lease.release_after_idle(s1_engine.S1_WARM_IDLE_SECONDS)
        local_model_resources.cleanup_idle_models(clock["now"] + 31.0)
        with local_model_resources._lock:
            not_before = local_model_resources._cleanup_not_before.get("polish")
        assert not_before == pytest.approx(1000.0 + local_model_resources.LOCAL_MODEL_IDLE_SECONDS)
    finally:
        local_model_resources._callbacks.pop("speed-test-polish", None)
        local_model_resources.cleanup_idle_models(clock["now"] + 10_000.0)


def test_llm_threads_use_physical_cores(monkeypatch):
    import psutil

    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: 4 if not logical else 8)
    assert local_model_resources.local_llm_thread_count() == 4
    assert s1_engine._s1_runtime_batch_settings()["n_threads"] == 4
    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: 16 if not logical else 32)
    assert local_model_resources.local_llm_thread_count() == 8


# --- 3. S1 prompt-cache priming --------------------------------------------

def test_prompt_prefix_is_the_head_of_every_s1_prompt():
    prefix = s1_engine._s1_prompt_prefix()
    assert prefix.endswith("user\n")
    assert s1_engine.S1_SYSTEM_PROMPT in prefix
    full = s1_engine.build_s1_prompt(s1_engine.build_s1_control_line(), "send it on friday")
    assert full.startswith(prefix)


def test_fresh_s1_warm_load_primes_the_prompt_cache(monkeypatch, tmp_path):
    model = tmp_path / s1_engine.S1_FILENAME
    model.write_bytes(b"gguf")
    calls = []

    class FakeLlama:
        def __init__(self, **kwargs):
            calls.append(("load", kwargs.get("n_threads")))

        def __call__(self, prompt, **kwargs):
            calls.append(("prime", prompt, kwargs.get("max_tokens")))
            return {"choices": [{"text": ""}]}

    import sys
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=FakeLlama))
    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: model)
    monkeypatch.setattr(s1_engine, "is_s1_runtime_available", lambda: True)
    monkeypatch.setattr(s1_engine, "_s1_in_process_retry_blocked", lambda _p: False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", None, raising=False)
    try:
        assert s1_engine.warm_s1_model(timeout_seconds=1.0)
        assert calls[0][0] == "load"
        assert calls[1] == ("prime", s1_engine._s1_prompt_prefix(), 1)
        # Already resident: no reload and no second priming pass.
        assert s1_engine.warm_s1_model(timeout_seconds=1.0)
        assert len(calls) == 2
    finally:
        s1_engine.polish_with_s1._cached_llm = None
        s1_engine.polish_with_s1._cached_llm_path = None


# --- 4. a late local chunk is waited for, not re-decoded --------------------

def _run_local_release(monkeypatch, *, model_ref, tail_delay):
    from voice_flow import main as m
    from voice_flow.main import DictationSession, DictationState, VoiceFlowApp
    from voice_flow.stream_stt import StreamTranscriber

    monkeypatch.setattr(m, "POST_RELEASE_WORK_BUDGET_SECONDS", 1.6)
    monkeypatch.setattr(m.storage, "get_setting",
                        lambda key, default=None: False if key in {"polishing_enabled", "voice_flow_mic_profile"} else default)

    whole_buffer_calls = []

    class LocalWhisper:
        def transcribe(self, audio, is_chunk=False, deadline=None, model_ref=None):
            if not is_chunk:
                whole_buffer_calls.append(len(audio))
                return "whole buffer text"
            if audio.size == 1600:  # tail chunk still decoding after release
                time.sleep(tail_delay)
                return "and the tail."
            return "first chunk"

    whisper = LocalWhisper()
    stream = StreamTranscriber(whisper)
    app = object.__new__(VoiceFlowApp)
    style = SimpleNamespace(app_name="Editor", category="smart_clean", style_id="smart_clean", instruction="")

    class Lease:
        def release(self):
            pass

        def release_after_idle(self, seconds, max_seconds=None):
            pass

    session = DictationSession(
        target_hwnd=123, app_title="Editor", app_category="smart_clean", style_id="smart_clean",
        started_at=0.0, resolved_style=style, stt_model_ref=model_ref, polish_model_ref=None,
        model_resource_lease=Lease(),
    )
    app.session = session
    app.state = DictationState.RECORDING
    app._state_lock = threading.RLock()
    app.processing_lock = threading.Lock()
    app._record_watchdog = None
    app._release_timing_session = session
    app._stream_session_owner = session
    app._streaming_stt_enabled = lambda: True
    app._get_current_external_window = lambda: 123
    app._get_effective_destination_hwnd = lambda *a, **k: 123
    app._set_hotkeys_recording_state = lambda *a: None
    app._overlay_call = lambda *a, **k: None
    app._history_update = lambda *a, **k: None
    app._defer_history_insert = lambda *a, **k: None
    app._start_recovery_archive = lambda *a: None
    app._get_cached_setting = lambda key, default=None: default
    app._pending_recovery = {}
    app._cancelled_session_ids = set()
    app.recent_dictations = set()
    app._delivery_session = None
    app.last_successful_transcript = None
    app._stream_stt = stream
    app.transcriber = SimpleNamespace(transcribe=whisper.transcribe, category_hint=None)
    pasted = []
    app.injector = SimpleNamespace(paste_text=lambda text, *a, **k: pasted.append(text) or True)

    audio = (0.2 * np.sin(np.arange(16000 * 3) / 5.0)).astype(np.float32)
    stream.start_session(model_ref=model_ref)
    stream.submit_native(audio[:16000 * 2], 16000)
    deadline = time.monotonic() + 2.0
    while stream.pending_count() and time.monotonic() < deadline:
        time.sleep(0.01)

    class Audio:
        _native_sr = 16000
        stream_input_incomplete = False
        split_silence_seconds = 0.35
        max_chunk_seconds = 8.0
        on_audio_frame = None

        def stop_and_take_open_chunk(self):
            return audio.copy(), np.full(1600, 0.2, dtype=np.float32), 0.0

        def post_roll(self, _seconds):
            pass

    app.audio = Audio()
    RealThread = threading.Thread

    class InlinePipeline:
        def __init__(self, *, target, args=(), kwargs=None, **_ignored):
            self.target, self.args, self.kwargs = target, args, kwargs or {}

        def start(self):
            if getattr(self.target, "__name__", "") == "_process_dictation_pipeline":
                self.target(*self.args, **self.kwargs)
            else:
                RealThread(target=self.target, args=self.args, kwargs=self.kwargs, daemon=True).start()

    monkeypatch.setattr(m.threading, "Thread", InlinePipeline)
    old = logging.getLogger().level
    logging.getLogger().setLevel(logging.ERROR)
    started = time.monotonic()
    try:
        assert app._on_dictation_finish()
    finally:
        logging.getLogger().setLevel(old)
    return pasted, whole_buffer_calls, time.monotonic() - started


def test_local_whisper_waits_for_one_late_chunk_instead_of_redecoding(monkeypatch):
    # Harvest ends ~1.15 s after release; the tail chunk needs 1.6 s.
    pasted, whole_buffer_calls, _elapsed = _run_local_release(
        monkeypatch, model_ref="local/faster-whisper-base.en", tail_delay=1.6,
    )
    assert whole_buffer_calls == []
    assert pasted and "First chunk and the tail" in pasted[0]


def test_cloud_chunk_stream_keeps_its_bounded_harvest(monkeypatch):
    pasted, whole_buffer_calls, _elapsed = _run_local_release(
        monkeypatch, model_ref="groq/whisper-large-v3", tail_delay=1.6,
    )
    assert whole_buffer_calls, "cloud streams still fall back to the complete recording"
    assert pasted and "Whole buffer text" in pasted[0]
