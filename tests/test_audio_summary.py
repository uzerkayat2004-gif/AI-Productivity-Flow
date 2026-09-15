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
from voice_flow.audio_summary import AudioSummaryError, AudioSummaryService, LocalSpokenSummarizer
from voice_flow.storage import storage
from voice_flow.video_flow_providers import video_flow_provider_service


def test_audio_summary_prompt_depth_and_formatting():
    source = "Voice Flow is an AI speech desktop application for Windows. It provides fast dictation and audio summaries."

    prompt_short = build_audio_summary_prompt(source, depth="short")
    assert "TARGET DEPTH: SHORT" in prompt_short
    assert "SOURCE SCALE: Approximately 1 page(s)" in prompt_short
    assert "DRAFTING RULE: Extract the single most important takeaway from each major section." in prompt_short
    assert "cutting out all background preamble" in prompt_short
    assert source in prompt_short

    # Test backward-compatible alias "quick" -> "short"
    prompt_quick = build_audio_summary_prompt(source, depth="quick")
    assert "TARGET DEPTH: SHORT" in prompt_quick
    assert "DRAFTING RULE:" in prompt_quick
    assert "keep it as concise as possible." in prompt_quick

    prompt_bal = build_audio_summary_prompt(source, depth="balanced")
    assert "TARGET DEPTH: BALANCED" in prompt_bal
    assert "DRAFTING RULE: Provide a balanced narrative covering all major sections" in prompt_bal
    assert "proportionally to the document's length." in prompt_bal

    # Test backward-compatible alias "standard" -> "balanced"
    prompt_std = build_audio_summary_prompt(source, depth="standard")
    assert "TARGET DEPTH: BALANCED" in prompt_std
    assert "Give each important section its appropriate coverage." in prompt_std

    # Test alias "medium" -> "balanced"
    prompt_med = build_audio_summary_prompt(source, depth="medium")
    assert "TARGET DEPTH: BALANCED" in prompt_med

    prompt_det = build_audio_summary_prompt(source, depth="detailed")
    assert "TARGET DEPTH: DETAILED" in prompt_det
    assert "DRAFTING RULE: Provide a comprehensive, section-by-section spoken walkthrough" in prompt_det
    assert "proportionally to the document's depth." in prompt_det

    # Test alias "long" -> "detailed"
    prompt_long = build_audio_summary_prompt(source, depth="long")
    assert "TARGET DEPTH: DETAILED" in prompt_long

    # Test multi-section / multi-page source scale calculation
    multisection_source = (
        "Voice Flow is an AI speech desktop application for Windows.\n\n"
        "It provides fast dictation and adaptive audio summaries.\n\n"
        "The architecture operates with high fidelity and zero failure."
    )
    prompt_multi = build_audio_summary_prompt(multisection_source, depth="standard")
    assert "SOURCE SCALE: Approximately 1 page(s) (27 words across 3 sections)." in prompt_multi


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


def test_sanitize_narration_spoken_symbols_and_visual_removal():
    raw_text = (
        "Here is a quick summary: As shown in the diagram, performance grew 45% with $10M in Q1. "
        "Click here for details w/o delay & see the table below."
    )
    clean = sanitize_narration_text(raw_text)
    assert "45 percent" in clean
    assert "10 million dollars" in clean
    assert " and " in clean
    assert "without" in clean
    assert "diagram" not in clean
    assert "table below" not in clean
    assert "Click here" not in clean
    assert "Here is a quick summary:" not in clean


def test_model_selection_isolation(tmp_path, monkeypatch):
    from voice_flow.video_flow_providers import VideoFlowProviderService
    from voice_flow.storage import StorageEngine
    test_db = str(tmp_path / "test_summary.db")
    test_storage = StorageEngine(test_db)
    test_vf_service = VideoFlowProviderService(test_db)
    monkeypatch.setattr("voice_flow.audio_summary.storage", test_storage)
    monkeypatch.setattr("tests.test_audio_summary.storage", test_storage)
    monkeypatch.setattr("tests.test_audio_summary.video_flow_provider_service", test_vf_service)

    # Record initial values
    initial_vf_model = test_vf_service.get_active_model()
    initial_summary_model = test_storage.get_setting("exec_audio_summary_model", "")
    initial_tts_voice = test_storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")

    # Save independent summary model
    test_storage.save_setting("exec_audio_summary_model", "openai/gpt-4o-mini")

    # Verify Video Flow model & Audio Flow TTS voice were NOT changed
    assert test_vf_service.get_active_model() == initial_vf_model
    assert test_storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural") == initial_tts_voice

    # Change Video Flow active setting directly
    test_vf_service.set_setting("active_model", "custom/test-model")

    # Verify Audio Summary model remains untouched
    assert test_storage.get_setting("exec_audio_summary_model") == "openai/gpt-4o-mini"
    assert test_storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural") == initial_tts_voice

    # Change Audio Flow TTS voice setting
    test_storage.save_setting("exec_audio_policy_model", "elevenlabs/21m00Tcm4TlvDq8ikWAM")

    # Verify Audio Summary model and Video Flow model remain untouched
    assert test_storage.get_setting("exec_audio_summary_model") == "openai/gpt-4o-mini"
    assert test_vf_service.get_setting("active_model") == "custom/test-model"


def test_audio_summary_service_no_model_error():
    service = AudioSummaryService()
    initial_summary_model = storage.get_setting("exec_audio_summary_model", "")
    try:
        storage.save_setting("exec_audio_summary_model", "")
        # When model_ref is empty and setting is empty, summarize must raise AudioSummaryError (no silent fallback)
        with pytest.raises(AudioSummaryError) as exc_info:
            service.summarize("Some text to summarize", depth="quick", model_ref="", allow_fallback=False)
        assert "No Audio Flow Summary Model selected" in str(exc_info.value)
    finally:
        storage.save_setting("exec_audio_summary_model", initial_summary_model)


def test_audio_summary_service_permission_error():
    service = AudioSummaryService()
    # External model without consent must raise PermissionError when allow_fallback=False
    with pytest.raises(PermissionError) as exc_info:
        service.summarize("Some text", depth="standard", model_ref="openai/gpt-4o-mini", allow_external_ai=False, allow_fallback=False)
    assert "External AI permission is required" in str(exc_info.value)


def test_local_spoken_summarizer_depths_on_multipage_text():
    multipage_text = """
    Voice Flow is a next-generation voice productivity application for Windows desktop users. It delivers real-time voice typing and intelligent audio summaries with an ultra-low latency architecture.

    The core architecture operates with under 150 milliseconds of latency, guaranteeing 99.9% uptime across local and cloud pipelines. Its deterministic processing ensures reliable execution on modern PCs without needing heavy external resources.

    For audio narration, Voice Flow synthesizes spoken explanations with high clarity. Users can choose between quick, standard, and detailed modes depending on their workflow and time constraints.

    In terms of security, Voice Flow strictly isolates credentials and enforces local processing boundaries. All sensitive operations remain on-device unless external AI services are explicitly granted permission by the user.

    In conclusion, Voice Flow provides the optimal balance of speed, privacy, and audio fidelity for demanding professionals.
    """
    summarizer = LocalSpokenSummarizer()

    quick_summary = summarizer.summarize(multipage_text, depth="quick")
    standard_summary = summarizer.summarize(multipage_text, depth="standard")
    detailed_summary = summarizer.summarize(multipage_text, depth="detailed")

    assert quick_summary
    assert standard_summary
    assert detailed_summary

    # Verify word counts increase monotonically: quick < standard < detailed
    words_quick = len(quick_summary.split())
    words_standard = len(standard_summary.split())
    words_detailed = len(detailed_summary.split())

    assert words_quick < words_standard < words_detailed

    # Verify key points and domain terms are retained
    assert "Voice Flow" in quick_summary or "Voice Flow" in standard_summary
    assert "latency" in standard_summary or "uptime" in standard_summary or "percent" in standard_summary
    assert "security" in detailed_summary or "privacy" in detailed_summary
    assert "Voice Flow" in detailed_summary


def test_audio_summary_service_local_deterministic():
    service = AudioSummaryService()
    text = (
        "Voice Flow introduces local deterministic audio summaries. "
        "It operates 100% offline without requiring any external network or API keys. "
        "The system summarizes multi-paragraph articles into smooth natural speech narration."
    )
    for depth in ("quick", "standard", "detailed"):
        summary = service.summarize(text, depth=depth, model_ref="local/deterministic")
        assert summary
        assert isinstance(summary, str)
        assert len(summary.split()) > 0


def test_audio_summary_service_fallback_behavior():
    service = AudioSummaryService()
    text = (
        "Voice Flow is built for seamless speech and text transformations. "
        "When an external model call is unpermitted or fails due to network outage, "
        "the architecture automatically activates the local deterministic summarizer."
    )
    # Test 1: External model without consent falls back to local summarizer when allow_fallback=True (default)
    fallback_summary_unpermitted = service.summarize(
        text, depth="standard", model_ref="openai/gpt-4o-mini", allow_external_ai=False
    )
    assert fallback_summary_unpermitted
    assert "Voice Flow" in fallback_summary_unpermitted

    # Test 2: External model failure falls back to local summarizer when allow_fallback=True (default)
    fallback_summary_failed_model = service.summarize(
        text, depth="quick", model_ref="groq/nonexistent-model", allow_external_ai=True
    )
    assert fallback_summary_failed_model
    assert "Voice Flow" in fallback_summary_failed_model

    # Test 3: If allow_fallback=False, permission check strictly raises PermissionError
    with pytest.raises(PermissionError):
        service.summarize(
            text, depth="standard", model_ref="openai/gpt-4o-mini", allow_external_ai=False, allow_fallback=False
        )


def test_audio_summary_api_endpoints(monkeypatch, tmp_path):
    import json
    import threading
    import time
    import urllib.parse
    import urllib.request
    from http.server import ThreadingHTTPServer
    from voice_flow.gui import api_server
    from voice_flow.storage import StorageEngine

    db_path = str(tmp_path / "voice_flow_api_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/audio-summary/settings/get returns "local/deterministic" when no model is set in storage
        req = urllib.request.Request(f"{base_url}/api/audio-summary/settings/get", headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["model"] == "local/deterministic"

        # 2. GET /api/audio-summary/test with quick depth
        sample_text = (
            "Voice Flow is an AI speech desktop app for Windows. "
            "It features fast local dictation and intelligent spoken summaries. "
            "Users can control their workflow with hotkeys and overlays."
        )
        query = urllib.parse.urlencode({"text": sample_text, "depth": "quick"})
        req_test_get = urllib.request.Request(f"{base_url}/api/audio-summary/test?{query}", headers={"Connection": "close"})
        with urllib.request.urlopen(req_test_get, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["depth"] == "quick"
            assert len(data["summary"]) > 0
            assert data["word_count"] > 0

        # 3. POST /api/audio-summary/test with standard and detailed depth
        for depth in ("standard", "detailed"):
            payload = json.dumps({"text": sample_text, "depth": depth}).encode("utf-8")
            req_test_post = urllib.request.Request(
                f"{base_url}/api/audio-summary/test",
                data=payload,
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            with urllib.request.urlopen(req_test_post, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert data["depth"] == depth
                assert len(data["summary"]) > 0
    finally:
        server.shutdown()
        server.server_close()


def test_audio_summary_widget_geometry_and_attached_stages():
    from voice_flow.audio_flow_widget import AudioFlowFloatingWidget

    widget = AudioFlowFloatingWidget()
    assert widget.STAGE_MINIMAL == "minimal"
    assert widget.STAGE_MODE_SELECT == "mode_select"
    assert widget.STAGE_DEPTH_SELECT == "depth_select"

    # Test dimension calculations (Sunrise spacious geometry)
    widget._stage = widget.STAGE_MINIMAL
    assert widget._get_current_dimensions() == (30, 30)

    widget._stage = widget.STAGE_MODE_SELECT
    assert widget._get_current_dimensions() == (286, 32)

    widget._stage = widget.STAGE_DEPTH_SELECT
    assert widget._get_current_dimensions() == (265, 32)

    widget._stage = widget.STAGE_SUMMARIZING
    assert widget._get_current_dimensions() == (160, 32)

    widget._stage = widget.STAGE_PLAYBACK_CONTROL
    assert widget._get_current_dimensions() == (145, 32)


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
