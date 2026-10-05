"""Comprehensive unit and integration tests for Audio Flow Human Explanatory Read Mode."""

from __future__ import annotations

from unittest.mock import MagicMock
import json
import threading
import re
import time
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
    assert "The text begins with this central concern:" in explanation
    assert PAUSE_SECTION in explanation
    assert "zero latency" in explanation


def test_offline_structured_read_walks_each_main_section_without_readback():
    source = """The desktop application is designed to stay in the background, so people do not need a separate dashboard.

1. Voice Flow (Speech to Text):
   - Mouse and keyboard gestures start dictation.
   - The active application changes the formatting of the result.
2. Audio Flow (Text to Spoken Speech):
   - Selected text is played as synchronized speech.
   - A floating player provides controls and several speech providers.
3. Video Flow (Text to Grounded Explainer Video):
   - Evidence grounding plans the scenes.
   - Rendering combines visuals, narration, and automated checks.
4. Platform Infrastructure:
   - Provider connections and keys stay in local protected storage.
"""
    explanation = audio_explainer.explain_offline(source)
    words = lambda value: re.findall(r"[a-z0-9]+", value.lower())
    source_grams = {tuple(words(source)[i:i + 8]) for i in range(len(words(source)) - 7)}
    copied_share = sum(
        tuple(words(explanation)[i:i + 8]) in source_grams
        for i in range(len(words(explanation)) - 7)
    ) / max(1, len(words(explanation)) - 7)

    assert len(explanation.split()) < len(source.split())
    assert copied_share < 0.35
    assert " covers " not in explanation.lower()
    for phrase in (
        "Voice Flow turns speech into text",
        "Selected content can be read aloud",
        "grounded explainer video",
        "provider connections",
        "background",
    ):
        assert phrase.lower() in explanation.lower()


def test_offline_structured_read_summarizes_codebase_locations_without_speaking_paths():
    source = """4. Codebase Locations:
   - Repository: C:\\Users\\Example\\project\\src
   - Development scripts: C:\\Users\\Example\\scripts\\tools
"""
    explanation = audio_explainer.explain_offline(source)

    assert "repository and development-script locations" in explanation.lower()
    assert "c:" not in explanation.lower()
    assert "users" not in explanation.lower()


def test_offline_structured_read_does_not_invent_details_from_generic_cue_words():
    source = """1. Scheduling:
   - A scheduled trigger starts the nightly job.
2. Input:
   - Push-to-talk is available through a hold control.
3. Data:
   - The database provider stores records.
4. Status:
   - A status widget displays the current result.
"""
    explanation = audio_explainer.explain_offline(source).lower()

    assert "scheduled trigger" in explanation
    assert "push-to-talk" in explanation
    assert "database provider" in explanation
    assert "mouse gesture" not in explanation
    assert "keyboard gesture" not in explanation
    assert "continuous dictation" not in explanation
    assert "speech engines" not in explanation
    assert "floating controls" not in explanation


def test_offline_structured_read_requires_evidence_for_combined_template_claims():
    source = """1. Transcript:
   - Local transcription records the meeting.
2. Playback:
   - Selected playback starts when requested.
3. Status:
   - An overlay shows a brief status.
4. Evidence:
   - Evidence is collected for review.
5. Rendering:
   - Rendering prepares the visual output.
"""
    explanation = audio_explainer.explain_offline(source).lower()

    assert "places the result in the active application" not in explanation
    assert "progress stays synchronized" not in explanation
    assert "floating controls" not in explanation
    assert "important entities" not in explanation
    assert "narration, and automated quality checks" not in explanation


def test_offline_structured_read_normalizes_markdown_labels_and_arrows():
    source = """1. 🎙️ **Voice Flow (Speech → Text)**:
   - Mouse and Ctrl gestures start dictation.
   - Push-to-talk uses a longer hold, while a tap toggles continuous dictation.
   - Local transcription sends the result to the active application.
"""
    explanation = audio_explainer.explain_offline(source).lower()

    assert "voice flow turns speech into text" in explanation
    assert "voice flow (speech" not in explanation
    assert "🎙" not in explanation


FRONTIER_SAFETY_SOURCE = """The world deserves confidence that American companies developing increasingly capable AI will act responsibly, especially as the trajectory of progress has steepened. Every frontier lab must deliver on this, and there is no reason any of us should come to work if we cannot. We welcome a federal framework that sets consistent safety requirements for frontier AI. But we do not believe we need to wait for an anti-trust exemption or legislation to begin the work of providing this confidence. Consistent rules to manage frontier risk so that we can maximize the benefits are a good idea, and we are excited by ideas like independent auditors. Years ago, companies like ours developed things like Responsible Scaling Policies and Preparedness Frameworks. Those were good for that moment, and focused primarily on the deployment of completed models, not what happens during their development process. Today's shift to focusing on safe development and evaluation will need new tools. For example, at OpenAI we now formulate explicit safety cases in advance of frontier reinforcement learning runs we expect to significantly increase capability, in addition to the safety work we have long done in advance of model releases. We hope that other companies will learn from our approaches and propose their own; we think shared standards for misalignment, monitoring, and safety will lead to better outcomes. We look forward to collaborating with our colleagues across the industry to formulate the best version of these. When we talk about pacing, we do not mean stopping. Progress has been rapid and will continue to be. But it should be slower than it otherwise could be; interventions like safety cases and monitoring have significant costs. Pacing will be well worth this cost; no amount of American competitive pressure should justify recklessness, or let capabilities get ahead of alignment and monitoring. Where we will need the help of our government is for international coordination. But first we should do what we can ourselves."""


def test_offline_read_builds_source_grounded_frontier_safety_walkthrough():
    """The deterministic Read fallback must explain the whole argument, not echo it."""
    explanation = audio_explainer.explain_offline(FRONTIER_SAFETY_SOURCE)
    assert "The text begins with this central concern:" in explanation
    assert "Here is an explanation" not in explanation
    assert explanation != audio_explainer.normalize_spoken_text(FRONTIER_SAFETY_SOURCE)
    # Benchmark main themes: confidence, shared rules, development-time safety,
    # pacing, and international coordination all remain audible.
    for phrase in ("American companies", "independent auditors", "Responsible Scaling Policies", "OpenAI", "safety cases", "Pacing", "international coordination"):
        assert phrase.lower() in explanation.lower()
    assert "mandatory checkpoint" not in explanation.lower()


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
            self.called = threading.Event()

        def is_speaking(self):
            return False

        def speak(self, text, **kwargs):
            self.last_spoken = text
            self.kwargs = kwargs
            self.called.set()

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

    assert mock_tts.called.wait(1.0)
    assert mock_tts.last_spoken is not None
    assert "In this message, the sender shares feedback" in mock_tts.last_spoken
    assert "making the note card and text significantly bigger" in mock_tts.last_spoken


def test_read_with_ai_human_explanatory_transform(monkeypatch):
    """Verify read_with_ai calls Gemini to produce natural human explanatory narration and caches it."""
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
    def fake_gemini(model_id, api_key, prompt, source_words):
        calls.append((model_id, api_key, prompt))
        return "Hey, I've tested the audio flow feature and noticed the note section is quite small. Could you make it a bit larger?"

    monkeypatch.setattr(audio_explainer, "_call_gemini_read", fake_gemini)

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


def test_read_gemini_transport_has_bounded_budget_low_thinking_and_safe_parsing(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": "First part. "}, {"text": "Second part."}]}}]}).encode()

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("voice_flow.audio_explainer.urllib.request.urlopen", fake_open)
    result = audio_explainer._call_gemini_read("gemini-3.5-flash-lite", "test-key", "prompt", 300)

    assert result == "First part. Second part."
    assert captured["timeout"] == 6.5
    config = captured["payload"]["generationConfig"]
    assert config["maxOutputTokens"] == 800
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}


def test_read_gemini_parser_ignores_thoughts_and_rejects_incomplete_candidates():
    parsed = audio_explainer._extract_gemini_text(
        {"candidates": [{"content": {"parts": [{"text": "Internal", "thought": True}, {"text": "Spoken script."}]}}]}
    )
    assert parsed == "Spoken script."
    for finish_reason in ("MAX_TOKENS", "SAFETY", "RECITATION"):
        with pytest.raises(ValueError, match=finish_reason):
            audio_explainer._extract_gemini_text({"candidates": [{"finishReason": finish_reason, "content": {"parts": [{"text": "partial"}]}}]})


def test_read_timeout_cooldown_applies_to_the_model_not_only_one_selection(monkeypatch):
    monkeypatch.setattr(storage, "get_all_api_keys", lambda: {"gemini": "mock"})
    model_id = "gemini-3.5-flash-lite"
    audio_explainer._ai_cooldowns[model_id] = time.monotonic() + 20
    monkeypatch.setattr(audio_explainer, "_call_gemini_read", lambda *_args: pytest.fail("cooldown should skip the request"))

    try:
        assert audio_explainer.read_with_ai("A different selected passage with enough words to be valid.", model_id=model_id) is None
    finally:
        audio_explainer._ai_cooldowns.pop(model_id, None)


def test_read_cache_is_versioned_and_rejects_unsafe_model_text(monkeypatch):
    """A stale cache key or invented strict requirement cannot reach TTS."""
    seen_keys = []
    monkeypatch.setattr(storage, "get_all_api_keys", lambda: {"gemini": "mock"})
    monkeypatch.setattr(storage, "get_audio_summary_cache", lambda key: seen_keys.append(key) or None)
    monkeypatch.setattr(storage, "set_audio_summary_cache", lambda *args: pytest.fail("unsafe script was cached"))
    monkeypatch.setattr(audio_explainer, "_call_gemini_read", lambda *args: "This is a mandatory checkpoint before training.")

    assert audio_explainer.read_with_ai("OpenAI suggests safety cases before training.") is None
    assert seen_keys and "v7" not in seen_keys[0]  # hashes intentionally conceal the key material


def test_long_model_script_must_cover_more_than_the_opening_theme():
    incomplete = (
        "The statement says frontier AI companies should act responsibly and support a federal framework. "
        "It argues that labs should build confidence before laws arrive."
    )
    assert not audio_explainer._is_safe_explanation(FRONTIER_SAFETY_SOURCE, incomplete)


def test_model_coverage_allows_an_incidental_trailing_signoff():
    source = (
        "The project opens with a stable input plan. "
        "It handles requests through a local workflow. "
        "The first section explains dependable capture. "
        "The middle section stores records for later review. "
        "It also synchronizes useful activity information. "
        "That work gives operators a clear history. "
        "The final section covers secure deployment and recovery. "
        "It keeps the service available during changes. "
        "Those safeguards complete the operational design. "
        "I am completely ready please hand over tasks."
    )
    candidate = (
        "The plan describes stable local input and dependable capture. "
        "It stores records and synchronizes activity history for review. "
        "It closes with secure deployment, recovery, and operational safeguards."
    )

    assert audio_explainer._is_safe_explanation(source, candidate)


def test_model_cannot_turn_general_obligation_into_mandatory_checkpoint():
    source = (
        "Every frontier lab must act responsibly. OpenAI formulates safety cases before frontier "
        "reinforcement learning runs. Pacing does not mean stopping."
    )
    candidate = (
        "OpenAI safety cases are a strict, mandatory checkpoint before every AI training run. "
        "Pacing does not mean stopping."
    )
    assert not audio_explainer._is_safe_explanation(source, candidate)


def test_model_may_omit_incidental_numbers_but_cannot_invent_or_alter_them():
    source = (
        "The report lists a 28 day activity view and a 0.30 second input threshold. "
        "It also describes local storage and playback controls for the user."
    )
    omitted = "The report describes activity trends, local storage, and playback controls for the user."
    equivalent = "The report uses a 0.3 second threshold with local storage and playback controls."
    altered = "The report uses a 30 second input threshold with local storage and playback controls."

    assert audio_explainer._is_safe_explanation(source, omitted)
    assert audio_explainer._is_safe_explanation(source, equivalent)
    assert not audio_explainer._is_safe_explanation(source, altered)
    assert not audio_explainer._is_safe_explanation(
        "The job runs for 30 days with local storage and playback controls.",
        "The job runs for 3 days with local storage and playback controls.",
    )


def test_model_cannot_broaden_actor_scope_or_replace_geography():
    source = (
        "At Acme, we formulate a safety case before a capability run. "
        "American competitive pressure does not justify recklessness."
    )
    candidate = (
        "At Acme and across all labs, safety cases are formulated before capability runs. "
        "Global market pressure does not justify recklessness."
    )
    assert not audio_explainer._is_safe_explanation(source, candidate)


def test_external_ai_string_false_does_not_call_provider(monkeypatch):
    monkeypatch.setattr(storage, "get_setting", lambda key, default=None: "false" if key == "audio_flow_allow_external_ai" else default)
    monkeypatch.setattr(audio_explainer, "read_with_ai", lambda *args, **kwargs: pytest.fail("provider should be disabled"))
    narrated = audio_explainer.transform_for_human_reading(FRONTIER_SAFETY_SOURCE)
    assert "The text begins with this central concern:" in narrated


def test_explicit_local_explainer_does_not_route_read_to_gemini(monkeypatch):
    def setting(key, default=None):
        if key == "audio_flow_read_mode":
            return "explanatory"
        if key == "audio_flow_allow_external_ai":
            return True
        if key == "audio_flow_explainer_model":
            return "local/deterministic"
        return default

    monkeypatch.setattr(storage, "get_setting", setting)
    monkeypatch.setattr(audio_explainer, "read_with_ai", lambda *args, **kwargs: pytest.fail("Gemini should not run"))
    narrated = audio_explainer.transform_for_human_reading(FRONTIER_SAFETY_SOURCE)
    assert "The text begins with this central concern:" in narrated
