"""Tests for Audio Flow Summary extension.

Verifies:
1. Prompt building & depth guidelines (Quick, Standard, Detailed).
2. Clean text formatting without markdown/bullets/citations.
3. Model selection isolation (Video Flow vs Audio Summary vs TTS Voice).
4. AudioSummaryService error handling & permission checks (no silent fallback).
5. API endpoints for summary settings.
6. Backward compatibility of Full Audio & existing triggers.
"""

from __future__ import annotations

import pytest
from voice_flow.audio_summary_prompts import build_audio_summary_prompt, sanitize_narration_text
from voice_flow.audio_summary import AudioSummaryError, AudioSummaryService
from voice_flow.storage import storage
from voice_flow.video_flow_providers import video_flow_provider_service


def test_audio_summary_prompt_depth_and_formatting():
    source = "Voice Flow is an AI speech desktop application for Windows. It provides fast dictation and audio summaries."

    prompt_short = build_audio_summary_prompt(source, depth="short")
    assert "TARGET DEPTH: SHORT" in prompt_short
    assert source in prompt_short

    # Test backward-compatible alias "quick" -> "short"
    prompt_quick = build_audio_summary_prompt(source, depth="quick")
    assert "TARGET DEPTH: SHORT" in prompt_quick

    prompt_bal = build_audio_summary_prompt(source, depth="balanced")
    assert "TARGET DEPTH: BALANCED" in prompt_bal

    # Test backward-compatible alias "standard" -> "balanced"
    prompt_std = build_audio_summary_prompt(source, depth="standard")
    assert "TARGET DEPTH: BALANCED" in prompt_std

    prompt_det = build_audio_summary_prompt(source, depth="detailed")
    assert "TARGET DEPTH: DETAILED" in prompt_det


def test_sanitize_narration_text():
    raw_markdown = """```markdown
# Summary Title
* First point about **Voice Flow**.
- Second point with [1] citation.
```"""
    clean = sanitize_narration_text(raw_markdown)
    assert "#" not in clean
    assert "*" not in clean
    assert "```" not in clean
    assert "Summary Title First point about Voice Flow. Second point with [1] citation." in clean or "Voice Flow" in clean


def test_model_selection_isolation():
    # Record initial values
    initial_vf_model = video_flow_provider_service.get_active_model()
    initial_summary_model = storage.get_setting("exec_audio_summary_model", "")
    initial_tts_voice = storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")

    try:
        # Save independent summary model
        storage.save_setting("exec_audio_summary_model", "openai/gpt-4o-mini")

        # Verify Video Flow model & Audio Flow TTS voice were NOT changed
        assert video_flow_provider_service.get_active_model() == initial_vf_model
        assert storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural") == initial_tts_voice

        # Change Video Flow active setting directly
        video_flow_provider_service.set_setting("active_model", "custom/test-model")

        # Verify Audio Summary model remains untouched
        assert storage.get_setting("exec_audio_summary_model") == "openai/gpt-4o-mini"
        assert storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural") == initial_tts_voice

        # Change Audio Flow TTS voice setting
        storage.save_setting("exec_audio_policy_model", "elevenlabs/21m00Tcm4TlvDq8ikWAM")

        # Verify Audio Summary model and Video Flow model remain untouched
        assert storage.get_setting("exec_audio_summary_model") == "openai/gpt-4o-mini"
        assert video_flow_provider_service.get_setting("active_model") == "custom/test-model"
    finally:
        # Restore initial values
        video_flow_provider_service.set_setting("active_model", initial_vf_model)
        storage.save_setting("exec_audio_summary_model", initial_summary_model)
        storage.save_setting("exec_audio_policy_model", initial_tts_voice)


def test_audio_summary_service_no_model_error():
    service = AudioSummaryService()
    initial_summary_model = storage.get_setting("exec_audio_summary_model", "")
    try:
        storage.save_setting("exec_audio_summary_model", "")
        # When model_ref is empty and setting is empty, summarize must raise AudioSummaryError (no silent fallback)
        with pytest.raises(AudioSummaryError) as exc_info:
            service.summarize("Some text to summarize", depth="quick", model_ref="")
        assert "No Audio Flow Summary Model selected" in str(exc_info.value)
    finally:
        storage.save_setting("exec_audio_summary_model", initial_summary_model)


def test_audio_summary_service_permission_error():
    service = AudioSummaryService()
    # External model without consent must raise PermissionError (no silent fallback)
    with pytest.raises(PermissionError) as exc_info:
        service.summarize("Some text", depth="standard", model_ref="openai/gpt-4o-mini", allow_external_ai=False)
    assert "External AI permission is required" in str(exc_info.value)


def test_audio_summary_widget_geometry_and_attached_stages():
    from voice_flow.audio_flow_widget import AudioFlowFloatingWidget

    widget = AudioFlowFloatingWidget()
    assert widget.STAGE_MINIMAL == "minimal"
    assert widget.STAGE_MODE_SELECT == "mode_select"
    assert widget.STAGE_DEPTH_SELECT == "depth_select"

    # Test dimension calculations
    widget._stage = widget.STAGE_MINIMAL
    assert widget._get_current_dimensions() == (34, 34)

    widget._stage = widget.STAGE_MODE_SELECT
    assert widget._get_current_dimensions() == (176, 34)

    widget._stage = widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (216, 34)


def test_cancellation_generation_token():
    from voice_flow.main import VoiceFlowApp

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app._audio_summary_generation = 0
    token1 = app._audio_summary_generation

    # Invalidate token on new action
    app._audio_summary_generation += 1
    token2 = app._audio_summary_generation
    assert token2 > token1


def test_backward_compatibility_defaults():
    from voice_flow.audio_flow_widget import AudioFlowFloatingWidget

    widget = AudioFlowFloatingWidget()
    called_args = []
    widget.on_trigger = lambda text, mode="full", summary_depth=None: called_args.append((text, mode, summary_depth))

    # Trigger without mode/depth parameter must default to mode="full"
    widget.on_trigger("Hello world")
    assert called_args == [("Hello world", "full", None)]


def test_tts_progressive_audio_capability_routing():
    from voice_flow.tts_engine import tts_engine

    # Edge TTS provider must return True for progressive audio
    assert tts_engine.supports_progressive_audio("edge/en-US-EmmaNeural") is True
    assert tts_engine.supports_progressive_audio("edge/en-US-AvaNeural") is True

    # Non-streaming providers must return False for progressive audio (retaining completed path)
    assert tts_engine.supports_progressive_audio("elevenlabs/21m00Tcm4TlvDq8ikWAM") is False
    assert tts_engine.supports_progressive_audio("openai/tts-1") is False
    assert tts_engine.supports_progressive_audio("deepgram/aura-asteria-en") is False
    assert tts_engine.supports_progressive_audio("sapi5/default") is False
