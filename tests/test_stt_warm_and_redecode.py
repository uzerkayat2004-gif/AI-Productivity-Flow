"""Speech model stays warm with cloud polish; short recordings get a full-context re-decode."""
from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np

from voice_flow import local_model_resources as lmr
from voice_flow import main as vf_main


def test_release_after_idle_default_cap_is_speech_idle_limit():
    # Speech defaults to the two-minute idle limit (release/final-local-oct16);
    # other models keep the 30 s default.
    lease = lmr.acquire_model_use("speech")
    before = lmr.idle_time()
    lease.release_after_idle(600.0)
    assert lmr._cleanup_not_before["speech"] <= before + lmr.LOCAL_MODEL_IDLE_SECONDS + 1.0
    lmr.acquire_model_use("speech").release()  # reset to immediate


def test_release_after_idle_custom_cap_allows_long_warm():
    lease = lmr.acquire_model_use("speech")
    before = lmr.idle_time()
    lease.release_after_idle(600.0, max_seconds=600.0)
    assert lmr._cleanup_not_before["speech"] >= before + 590.0
    lmr.acquire_model_use("speech").release()  # reset to immediate


def test_polish_model_is_local(monkeypatch):
    vals = {}
    monkeypatch.setattr(vf_main.storage, "get_setting", lambda k, d=None: vals.get(k, d))
    vals["voice_flow_polish_model"] = "antigravity/gemini-3.8-flash"
    assert vf_main._polish_model_is_local() is False
    for ref in ("local/s1-mini-q4_k_m", "superwhisper/s1-mini-q4_k_m", ""):
        vals["voice_flow_polish_model"] = ref
        assert vf_main._polish_model_is_local() is True


def _app(transcribe):
    app = object.__new__(vf_main.VoiceFlowApp) if hasattr(vf_main, "VoiceFlowApp") else SimpleNamespace()
    app.transcriber = SimpleNamespace(transcribe=transcribe)
    return app


def _call(app, session, audio, duration, deadline):
    return vf_main.VoiceFlowApp._full_redecode_short_recording(app, session, audio, duration, deadline)


import pytest


@pytest.fixture(autouse=True)
def _polishing_on(monkeypatch):
    monkeypatch.setattr(vf_main, "_polishing_enabled", lambda: True)


def test_redecode_skipped_in_off_mode(monkeypatch):
    monkeypatch.setattr(vf_main, "_polishing_enabled", lambda: False)
    app = _app(lambda *a, **k: "x")
    s = SimpleNamespace(stt_model_ref="local/nemotron-speech-streaming-en-0.6b")
    assert _call(app, s, np.ones(16000, dtype=np.float32), 2.0, time.monotonic() + 4.0) == ""


def test_redecode_used_for_short_nemotron_recording():
    calls = []
    app = _app(lambda audio, deadline=None, model_ref=None: calls.append(model_ref) or "Question.")
    s = SimpleNamespace(stt_model_ref="local/nemotron-speech-streaming-en-0.6b")
    out = _call(app, s, np.ones(16000, dtype=np.float32) * 0.1, 1.0, time.monotonic() + 4.0)
    assert out == "Question." and calls


def test_redecode_skipped_for_long_or_non_nemotron_or_error():
    app = _app(lambda *a, **k: "x")
    audio = np.ones(16000, dtype=np.float32)
    nem = SimpleNamespace(stt_model_ref="local/nemotron-speech-streaming-en-0.6b")
    assert _call(app, nem, audio, 45.0, time.monotonic() + 4.0) == ""
    assert _call(app, SimpleNamespace(stt_model_ref="deepgram/nova-3"), audio, 2.0, time.monotonic() + 4.0) == ""
    assert _call(app, nem, audio, 2.0, time.monotonic()) == ""  # no budget left

    def boom(*a, **k):
        raise RuntimeError("decoder failed")
    assert _call(_app(boom), nem, audio, 2.0, time.monotonic() + 4.0) == ""
    assert _call(_app(lambda *a, **k: ""), nem, audio, 2.0, time.monotonic() + 4.0) == ""
