from __future__ import annotations

import os
import sys

import numpy as np

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.audio import AudioRecorder
from voice_flow.text_processing import split_press_enter
from voice_flow.polisher import TextPolisher
from voice_flow.transcriber import Transcriber


def test_api_polisher_cannot_change_explicit_terminal_punctuation(monkeypatch) -> None:
    polisher = TextPolisher()
    monkeypatch.setattr("voice_flow.polisher.storage.get_setting", lambda key, default=None: default)
    monkeypatch.setattr("voice_flow.polisher.storage.get_all_api_keys", lambda: {"gemini": "test-key"})
    monkeypatch.setattr(polisher, "_polish_with_api_pool", lambda *_args: "What is the status.")
    monkeypatch.setattr("voice_flow.polisher.dictionary_engine.apply_dictionary_post_processing", lambda text: text)
    assert polisher.polish("what is the status?") == "What is the status?"


def test_negative_press_enter_mentions_are_not_actions() -> None:
    for text in (
        "please don't ever press enter",
        "please never ever press enter",
    ):
        result = split_press_enter(text, enabled=True)
        assert result.press_enter is False
        assert result.text == text



def test_vad_failure_uses_direct_audio_fallback(monkeypatch) -> None:
    transcriber = object.__new__(Transcriber)
    transcriber.model = type("Model", (), {})()
    audio = np.ones(4000, dtype=np.float32)

    class Segment:
        text = "fallback words"

    calls = []

    def transcribe(data, **kwargs):
        calls.append(kwargs.get("vad_filter"))
        if kwargs.get("vad_filter"):
            raise RuntimeError("vad failed")
        return iter([Segment()]), None

    transcriber.model.transcribe = transcribe
    monkeypatch.setattr(
        "voice_flow.transcriber.dictionary_engine.get_initial_prompt",
        lambda: "",
    )
    monkeypatch.setattr("voice_flow.transcriber.config.sample_rate", 16000)
    assert transcriber.transcribe(audio) == "fallback words"
    assert calls == [True, False]


def test_resample_failure_discards_audio(monkeypatch) -> None:
    recorder = object.__new__(AudioRecorder)
    recorder._native_sr = 44100
    recorder._buffer = [np.ones((4410, 1), dtype=np.float32)]
    recorder._lock = __import__("threading").Lock()
    recorder._lifecycle_lock = __import__("threading").RLock()
    recorder._recording = True
    recorder._stream = None
    monkeypatch.setattr(
        "voice_flow.audio.sig.resample_poly",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad resampler")),
    )
    result = recorder.stop()
    assert result.size == 0
