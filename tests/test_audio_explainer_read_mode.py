"""Comprehensive unit and integration tests for Audio Flow Human Explanatory Read Mode."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from voice_flow.audio_explainer import (
    audio_explainer,
    expand_spoken_abbreviations,
    declutter_spoken_text,
    AudioExplainer,
)
from voice_flow.structured_reader import PAUSE_SECTION, PAUSE_PARAGRAPH
from voice_flow.storage import storage
from voice_flow import main as main_module
from voice_flow.main import DictationState, VoiceFlowApp


def test_abbreviation_expansions():
    """Verify common Latinisms, technical acronyms, and shortcuts expand to spoken words."""
    assert expand_spoken_abbreviations("e.g. review PR") == "for example review pull request"
    assert expand_spoken_abbreviations("i.e. fix UI") == "that is fix user interface"
    assert expand_spoken_abbreviations("w/ 50% discount") == "with 50% discount"
    assert expand_spoken_abbreviations("w/o errors") == "without errors"
    assert expand_spoken_abbreviations("press Ctrl+C to copy") == "press control plus C to copy"
    assert expand_spoken_abbreviations("press Ctrl+V to paste") == "press control plus V to paste"
    assert expand_spoken_abbreviations("check DB and API") == "check database and A P I"
    assert expand_spoken_abbreviations("improve TTS quality") == "improve text to speech quality"
    assert expand_spoken_abbreviations("run CLI and SDK") == "run command line interface and S D K"
    assert expand_spoken_abbreviations("planned for Q3") == "planned for quarter 3"
    assert expand_spoken_abbreviations("released v2.0") == "released version 2.0"


def test_declutter_colloquial_stutter():
    """Verify stuttering, repetition, and rambling fillers are cleanly untangled."""
    dirty = "Now the the UI and all those stuffs are great. Do one thing make it bigger like like right now."
    cleaned = declutter_spoken_text(dirty)
    assert "the the" not in cleaned
    assert "and all those stuffs" not in cleaned
    assert "like like" not in cleaned
    assert "do one thing" not in cleaned
    assert "please make it bigger" in cleaned


def test_offline_user_feedback_explanation():
    """Verify feedback messages are framed conversationally with intent and key takeaways."""
    sample = (
        "Hey right now I have tested the audio flow feature but still it is not human like. "
        "Can you make the read mode also like an explanation type so it reads like a human?"
    )
    explanation = audio_explainer.explain_offline(sample)
    assert "In this message, the sender shares feedback" in explanation
    assert "Audio Flow feature" in explanation
    assert "word-for-word" in explanation or "explanation-style presentation" in explanation
    assert PAUSE_SECTION in explanation


def test_offline_note_sizing_feedback_explanation():
    """Verify feedback about notice card sizing is recognized and highlighted."""
    sample = (
        "Hey can you check the audio flow popup? Make the note thing little bit bigger "
        "because right now it is so small and I cannot read it."
    )
    explanation = audio_explainer.explain_offline(sample)
    assert "In this message, the sender shares feedback" in explanation
    assert "making the note card and text significantly bigger" in explanation
    assert PAUSE_SECTION in explanation


def test_offline_question_explanation():
    """Verify questions receive an explanatory conversational lead-in."""
    q = "How do I configure the voice speed in Voice Flow?"
    explanation = audio_explainer.explain_offline(q)
    assert "This question asks about" in explanation
    assert "voice speed" in explanation
    assert PAUSE_SECTION in explanation


def test_offline_code_snippet_explanation():
    """Verify code snippets are framed as implementation logic rather than raw punctuation."""
    code = "def process_data(items):\n    return [item.strip() for item in items]"
    explanation = audio_explainer.explain_offline(code)
    assert "This code snippet outlines" in explanation
    assert "def process_data" in explanation
    assert PAUSE_SECTION in explanation


def test_offline_documentation_explanation():
    """Verify multi-sentence articles receive structured human-explained delivery."""
    doc = (
        "Voice Flow is an open-source speech productivity system for Windows. "
        "It supports rapid voice dictation and high-fidelity audio narration. "
        "The architecture is designed for zero latency and offline reliability."
    )
    explanation = audio_explainer.explain_offline(doc)
    assert "Here is an explanation of the Voice Flow application." in explanation
    assert PAUSE_SECTION in explanation
    assert "zero latency" in explanation


def test_transform_for_human_reading_respects_verbatim_setting(monkeypatch):
    """Verify user can toggle between human explanatory reading and raw verbatim speech."""
    sample = "Please review the PR for the UI updates w/ 10% speedup."

    # Explanatory mode (default)
    monkeypatch.setattr(storage, "get_setting", lambda key, default=None: "explanatory" if key == "audio_flow_read_mode" else default)
    exp = audio_explainer.transform_for_human_reading(sample)
    assert "pull request" in exp
    assert "user interface" in exp

    # Verbatim mode
    monkeypatch.setattr(storage, "get_setting", lambda key, default=None: "verbatim" if key == "audio_flow_read_mode" else default)
    verb = audio_explainer.transform_for_human_reading(sample)
    assert "pull request" in verb
    assert "Here is an explanation" not in verb


def test_main_pipeline_read_mode_invokes_human_explanatory_transform(monkeypatch):
    """Verify Audio Flow pipeline in main.py transforms text for human reading before calling TTS."""
    class MockTTS:
        def __init__(self):
            self.last_spoken = None
            self.kwargs = None

        def is_speaking(self):
            return False

        def speak(self, text, **kwargs):
            self.last_spoken = text
            self.kwargs = kwargs

        def stop(self):
            pass

    mock_tts = MockTTS()
    monkeypatch.setattr(main_module, "tts_engine", mock_tts)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda key, default=None: True if key == "audio_flow_enabled" else default)

    app = object.__new__(VoiceFlowApp)
    app._state_lock = MagicMock()
    app.state = DictationState.IDLE
    app.overlay = MagicMock()
    app.injector = MagicMock()
    app.recent_dictations = set()
    app.last_successful_transcript = None
    app._audio_summary_generation = 0
    app._is_voice_flow_dictation = lambda text: False

    input_text = (
        "Hey right now I have tried the audio flow feature. "
        "Do one thing make the note thing little bit bigger because it is so small."
    )
    app._process_audio_flow_pipeline(text_override=input_text, mode="read")

    assert mock_tts.last_spoken is not None
    assert "In this message, the sender shares feedback" in mock_tts.last_spoken
    assert "making the note card and text significantly bigger" in mock_tts.last_spoken


def test_read_with_ai_human_explanatory_transform(monkeypatch):
    """Verify read_with_ai calls Gemini to produce natural human explanatory narration and caches it."""
    from voice_flow.audio_summary import audio_summary_service

    # Local in-memory cache for isolation
    mem_cache = {}
    monkeypatch.setattr(storage, "get_audio_summary_cache", lambda key: mem_cache.get(key))
    monkeypatch.setattr(
        storage,
        "set_audio_summary_cache",
        lambda key, text_hash, depth, model, summary, cached_at: mem_cache.update({key: {"summary_text": summary}}),
    )

    monkeypatch.setattr(storage, "get_all_api_keys", lambda: {"gemini": "mock_gemini_key"})
    monkeypatch.setattr(
        storage,
        "get_setting",
        lambda key, default=None: True if key in ("audio_flow_allow_external_ai", "exec_audio_summary_allow_external_ai") else default,
    )

    calls = []
    def fake_gemini(model_id, api_key, prompt):
        calls.append((model_id, api_key, prompt))
        return "Hey, I've tested the audio flow feature and noticed the note section is quite small. Could you make it a bit larger?"

    monkeypatch.setattr(audio_summary_service, "_call_gemini", fake_gemini)

    sample = "Hey right now I have tested the audio flow feature. Make the note thing little bit bigger because it is so small for mock testing."

    # First call triggers Gemini
    narrated = audio_explainer.transform_for_human_reading(sample)
    assert len(calls) == 1
    assert "Hey, I've tested the audio flow feature" in narrated
    assert "In this message, the sender shares feedback" not in narrated

    # Second call uses cache without re-invoking Gemini
    cached = audio_explainer.transform_for_human_reading(sample)
    assert len(calls) == 1
    assert cached == narrated

