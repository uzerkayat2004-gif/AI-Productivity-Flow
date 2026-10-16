"""Stutter-fragment collapse, polish safety acceptance, tail padding, post-roll (B3)."""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.text_processing import collapse_stutter_fragments


@pytest.mark.parametrize("text,expected", [
    ("My. Ag. My agent", "My agent"),
    ("My. Ag. My agent.", "My agent."),
    ("Q? Q. Quest? Question.", "Question?"),
    ("So the the plan is. Is to ship. Ship on Friday.", "So the plan is to ship on Friday."),
    ("Ship. Ship on Friday", "Ship on Friday"),
    ("Yes. Yes I can.", "Yes I can."),
    ("I. I think so.", "I think so."),
    ("It is a. A good plan.", "It is a good plan."),
    ("The the plan is fine.", "The plan is fine."),
    ("Send it to. To Priya by noon.", "Send it to Priya by noon."),
])
def test_stutter_fragments_collapse(text: str, expected: str) -> None:
    assert collapse_stutter_fragments(text) == expected


@pytest.mark.parametrize("text", [
    "I. Am.",
    "Okay. Okay.",
    "Send the report today. Send the report today.",
    "I love it. It works.",
    "We need more time. Time is money.",
    "I'll call Bob. Bob will know.",
    "He had had enough.",
    "No no, that is wrong.",
    "Thanks. See you.",
    "Plan A. Apple will win.",
    "Uz. Ar. Uzair called.",
    "Version 3.5. Ship it.",
    "Call me at 5. 5 is fine.",
    "",
    "hello",
    "first line\nsecond line",
])
def test_legitimate_text_is_unchanged(text: str) -> None:
    assert collapse_stutter_fragments(text) == text


def test_collapse_never_drops_an_unrepeated_word() -> None:
    import re
    samples = [
        "My. Ag. My agent", "Q? Q. Quest? Question.",
        "So the the plan is. Is to ship. Ship on Friday.", "It is a. A good plan.",
    ]
    for text in samples:
        before = {re.sub(r"[^\w']", "", w).lower() for w in text.split()}
        after_words = [re.sub(r"[^\w']", "", w).lower() for w in collapse_stutter_fragments(text).split()]
        # Every remaining word came from the source, and every dropped word
        # is a repeat or a prefix of a word that remains.
        assert set(after_words) <= before
        for word in before - set(after_words):
            assert any(kept.startswith(word) for kept in after_words), (text, word)


@pytest.mark.parametrize("source,candidate", [
    ("Q? Q. Quest? Question.", "Question?"),
    ("So the the plan is. Is to ship. Ship on Friday.", "So the plan is to ship on Friday."),
    ("My. Ag. My agent", "My agent"),
])
def test_polish_safety_accepts_pure_stutter_removal(source: str, candidate: str) -> None:
    from voice_flow.polisher import _candidate_preserves_content
    assert _candidate_preserves_content(source, candidate) is True


@pytest.mark.parametrize("source,candidate", [
    ("I do not know. Not sure.", "I do know. Not sure."),
    ("Send it to John on Friday.", "Send it on Friday."),
    ("Call 5 5 people today.", "Call 5 people today."),
])
def test_polish_safety_still_rejects_real_drops(source: str, candidate: str) -> None:
    from voice_flow.polisher import _only_removes_stutter_fragments, _tokenize_for_fidelity
    assert _only_removes_stutter_fragments(_tokenize_for_fidelity(source), _tokenize_for_fidelity(candidate)) is False


def test_pipeline_applies_collapse_with_polish_on_and_off() -> None:
    import inspect
    from voice_flow import main as main_module
    source = inspect.getsource(main_module.VoiceFlowApp._process_dictation_pipeline)
    collapse_at = source.index("collapse_stutter_fragments(raw_transcript)")
    # Applied before the polish branch splits, so both modes get it.
    assert collapse_at < source.index("if polishing_enabled:")


def test_post_roll_keeps_capturing_then_returns():
    from voice_flow.audio import AudioRecorder
    recorder = object.__new__(AudioRecorder)
    recorder._recording = True
    started = time.monotonic()
    recorder.post_roll(0.12)
    assert 0.1 <= time.monotonic() - started < 0.5
    recorder._recording = False
    started = time.monotonic()
    recorder.post_roll(0.3)
    assert time.monotonic() - started < 0.05


def test_release_post_roll_skips_ui_thread_and_runs_on_worker_thread(monkeypatch):
    from types import SimpleNamespace
    from voice_flow import main as main_module
    calls = []
    app = object.__new__(main_module.VoiceFlowApp)
    app.audio = SimpleNamespace(post_roll=lambda seconds: calls.append(seconds))
    app._release_post_roll()  # pytest runs on the main thread (UI thread in the app)
    assert calls == []
    worker = threading.Thread(target=app._release_post_roll)
    worker.start()
    worker.join(2)
    assert calls == [main_module.RELEASE_POST_ROLL_SECONDS]
    app.audio = SimpleNamespace()  # custom/fake recorders without post_roll are skipped
    worker = threading.Thread(target=app._release_post_roll)
    worker.start()
    worker.join(2)
    assert calls == [main_module.RELEASE_POST_ROLL_SECONDS]


def test_whole_recording_decode_requests_longer_end_of_utterance_history():
    import ctypes
    from voice_flow import nemotron_engine
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.fatal_error = None
    engine.rec_handle = ctypes.c_void_p(1)
    engine.spec, engine.metadata, engine.sample_rate = {"default_language": "en"}, {}, 16000
    seen = {}
    class _Native:
        def call(self, op, **values):
            seen.update(values, op=op)
            return {"status": 0, "result": {"text": b"ok", "final": True}}
    engine._native = _Native()
    import numpy as np
    assert engine._transcribe_segment(np.zeros(3200, dtype=np.float32), language="en") == "ok"
    assert seen["op"] == "recognize" and seen["streaming"] is True
    assert seen["stop_history_eou_ms"] == nemotron_engine.WHOLE_RECORDING_EOU_HISTORY_MS
