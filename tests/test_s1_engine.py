"""Comprehensive unit and integration tests for S1-mini by Superwhisper Voice Polishing Engine."""
from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path
import pytest

from voice_flow import (
    downloadable_models,
    s1_engine,
    lfm_engine,
    voice_polish_bridge,
)
from voice_flow.storage import storage


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure clean state before and after each test."""
    orig_polish_model = storage.get_setting("voice_flow_polish_model")
    orig_standing = storage.get_setting("style_standing_instruction")
    storage.save_setting("style_standing_instruction", "")
    yield
    if orig_polish_model is not None:
        storage.save_setting("voice_flow_polish_model", orig_polish_model)
    else:
        storage.save_setting("voice_flow_polish_model", "local/deterministic")
    storage.save_setting("style_standing_instruction", "")
    if hasattr(s1_engine.polish_with_s1, "_mock_runner"):
        delattr(s1_engine.polish_with_s1, "_mock_runner")


class TestS1RegistryAndSpecs:
    def test_s1_registry_entry_metadata(self):
        """Verify S1-mini entry in DOWNLOADABLE_POLISH_MODELS_REGISTRY matches requirements."""
        s1 = next((m for m in downloadable_models.DOWNLOADABLE_POLISH_MODELS_REGISTRY if m["id"] == "superwhisper/s1-mini-q4_k_m"), None)
        assert s1 is not None
        assert s1["name"] == "S1-mini by Superwhisper"
        assert s1["tag"] == "Voice Polishing"
        assert s1["task"] == "voice_polishing"
        assert s1["category"] == "voice_polishing"
        assert s1["format"] == "Local GGUF (Q4_K_M)"
        assert s1["size_mb"] == 462
        assert s1["size_bytes"] == 484219808
        assert s1["size_display"] == "484 MB"
        assert s1["sha256"] == "3b41ebe2502cbd03e811d5d16b022f5ab551eda58d62597d152f89535003c634"
        assert s1["languages"] == ["English (en)"]
        assert s1["is_multilingual"] is False
        assert s1["default_language"] == "en"
        assert s1["full_id"] == "local/s1-mini-q4_k_m"
        assert s1["filename"] == "s1-mini-q4_k_m.gguf"
        assert "superwhisper/s1-mini-GGUF" in s1["repo_url"]

    def test_s1_and_lfm_registry_coexistence(self):
        """S1-mini sits beside Liquid LFM 2.5 in polish registry; neither is in STT registry."""
        polish_ids = [m["id"] for m in downloadable_models.DOWNLOADABLE_POLISH_MODELS_REGISTRY]
        assert "liquid/lfm2.5-350m-qad-q4_0" in polish_ids
        assert "superwhisper/s1-mini-q4_k_m" in polish_ids
        assert len(polish_ids) == 2

        stt_ids = [m["id"] for m in downloadable_models.DOWNLOADABLE_STT_MODELS_REGISTRY]
        assert "superwhisper/s1-mini-q4_k_m" not in stt_ids
        assert "liquid/lfm2.5-350m-qad-q4_0" not in stt_ids

    def test_get_model_spec_disambiguation(self):
        """Disambiguation aliases resolve cleanly and never cross-match."""
        s1_spec = downloadable_models.get_model_spec("s1-mini")
        assert s1_spec is not None
        assert s1_spec["id"] == "superwhisper/s1-mini-q4_k_m"

        s1_spec_full = downloadable_models.get_model_spec("local/s1-mini-q4_k_m")
        assert s1_spec_full is not None
        assert s1_spec_full["id"] == "superwhisper/s1-mini-q4_k_m"

        s1_spec_file = downloadable_models.get_model_spec("s1-mini-q4_k_m.gguf")
        assert s1_spec_file is not None
        assert s1_spec_file["id"] == "superwhisper/s1-mini-q4_k_m"

        lfm_spec = downloadable_models.get_model_spec("lfm2.5-350m")
        assert lfm_spec is not None
        assert lfm_spec["id"] == "liquid/lfm2.5-350m-qad-q4_0"

        lfm_spec_full = downloadable_models.get_model_spec("local/lfm2.5-350m-qad-q4_0")
        assert lfm_spec_full is not None
        assert lfm_spec_full["id"] == "liquid/lfm2.5-350m-qad-q4_0"

    def test_is_s1_model_ref_aliases(self):
        assert s1_engine.is_s1_model_ref("local/s1-mini-q4_k_m")
        assert s1_engine.is_s1_model_ref("superwhisper/s1-mini-q4_k_m")
        assert s1_engine.is_s1_model_ref("s1-mini-q4_k_m")
        assert s1_engine.is_s1_model_ref("s1-mini")
        assert s1_engine.is_s1_model_ref(" S1-MINI ")
        assert not s1_engine.is_s1_model_ref("liquid/lfm2.5-350m-qad-q4_0")
        assert not s1_engine.is_s1_model_ref("local/deterministic")
        assert not s1_engine.is_s1_model_ref("")
        assert not s1_engine.is_s1_model_ref(None)


class TestS1PromptAndControlLine:
    def test_build_s1_control_line_defaults(self):
        ctrl = s1_engine.build_s1_control_line()
        assert ctrl == "[Styling: semi-formal] [Structure: prose] [Context: general]"

    def test_build_s1_control_line_styles(self):
        # casual maps to semi-formal so initial letters are not lowercased
        ctrl_casual = s1_engine.build_s1_control_line(style_id="casual")
        assert "[Styling: semi-formal]" in ctrl_casual

        # very_casual maps to casual (all lowercase)
        ctrl_vc = s1_engine.build_s1_control_line(style_id="very_casual")
        assert "[Styling: casual]" in ctrl_vc

        # standard formal maps to semi-formal to preserve contractions
        ctrl_formal = s1_engine.build_s1_control_line(style_id="formal")
        assert "[Styling: semi-formal]" in ctrl_formal

        # explicit override formal maps to formal
        ctrl_explicit_formal = s1_engine.build_s1_control_line(
            style_id="formal",
            overrides={"tone": "formal"},
        )
        assert "[Styling: formal]" in ctrl_explicit_formal

        ctrl_prof = s1_engine.build_s1_control_line(
            overrides={"formality": "professional"},
        )
        assert "[Styling: formal]" in ctrl_prof

    def test_build_s1_control_line_structure_and_context(self):
        ctrl_list = s1_engine.build_s1_control_line(command_format="bullet_list")
        assert "[Structure: lists]" in ctrl_list
        assert "[Context: general]" in ctrl_list

        ctrl_email = s1_engine.build_s1_control_line(command_format="email")
        assert "[Structure: prose]" in ctrl_email
        assert "[Context: email]" in ctrl_email

    def test_build_s1_prompt_chatml_and_empty_think(self):
        ctrl = "[Styling: semi-formal] [Structure: prose] [Context: general]"
        text = "um hello world"
        prompt = s1_engine.build_s1_prompt(ctrl, text)

        assert prompt.startswith(f"<|im_start|>system\n{s1_engine.S1_SYSTEM_PROMPT}<|im_end|>\n")
        assert f"<|im_start|>user\n{ctrl}\n{text}<|im_end|>\n" in prompt
        assert prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


class TestS1CanHandle:
    def test_can_handle_clean_dictation(self):
        assert s1_engine.s1_can_handle(text="Hey team let's meet tomorrow morning.")

    def test_rejects_summarize_operation(self):
        cmd = types.SimpleNamespace(operation="summarize", format="prose", persistent_change=False, ambiguous=False)
        assert not s1_engine.s1_can_handle(command=cmd, text="Summarize this article.")

    def test_rejects_prompt_generation(self):
        cmd = types.SimpleNamespace(operation="prompt_generation", format="prompt", persistent_change=False, ambiguous=False)
        assert not s1_engine.s1_can_handle(command=cmd, text="Generate a prompt for image generation.")

    def test_rejects_unsupported_formats(self):
        for fmt in ("prompt", "linkedin_post", "note", "work_message", "personal_message"):
            cmd = types.SimpleNamespace(operation="rewrite", format=fmt, persistent_change=False, ambiguous=False)
            assert not s1_engine.s1_can_handle(command=cmd, text="Some text to format."), f"Should reject {fmt}"

    def test_rejects_persistent_change_and_ambiguous(self):
        cmd1 = types.SimpleNamespace(operation="rewrite", format="prose", persistent_change=True, ambiguous=False)
        assert not s1_engine.s1_can_handle(command=cmd1, text="Text")

        cmd2 = types.SimpleNamespace(operation="rewrite", format="prose", persistent_change=False, ambiguous=True)
        assert not s1_engine.s1_can_handle(command=cmd2, text="Text")

    def test_rejects_custom_standing_instructions(self):
        storage.save_setting("style_standing_instruction", "Always add signature at the end")
        assert not s1_engine.s1_can_handle(text="Some text")

    def test_rejects_non_english(self):
        # Russian/Cyrillic
        assert not s1_engine.s1_can_handle(text="Привет, как дела? Это тестовое сообщение.")
        # Spanish/French with accents is largely ascii letters unless heavy, but German/Greek/Japanese:
        assert not s1_engine.s1_can_handle(text="こんにちは世界、これはテストです。")


class TestJoinedNumbersGuard:
    def test_preserves_joined_numbers_or(self):
        # When numbers are kept, guard passes
        assert s1_engine.check_joined_numbers_guard(
            "I will arrive at 3 or 4 PM",
            "I will arrive at 3 or 4 PM.",
        )

    def test_rejects_dropped_number_joined_by_or(self):
        # S1 mistakenly resolves "3 or 4" into "4", dropping 3
        assert not s1_engine.check_joined_numbers_guard(
            "I will arrive at 3 or 4 PM",
            "I will arrive at 4 PM.",
        )

    def test_rejects_dropped_number_joined_by_and(self):
        assert not s1_engine.check_joined_numbers_guard(
            "Send items 10 and 20 today",
            "Send item 20 today.",
        )

    def test_allows_dropping_when_self_correction_marker_present(self):
        # "no wait" is a genuine self-correction marker
        assert s1_engine.check_joined_numbers_guard(
            "I will arrive at 3 PM, no wait, 4 PM",
            "I will arrive at 4 PM.",
        )

        assert s1_engine.check_joined_numbers_guard(
            "Meet me on Friday, I mean Thursday",
            "Meet me on Thursday.",
        )

        assert s1_engine.check_joined_numbers_guard(
            "Table 5, actually table 6",
            "Table 6.",
        )


class TestS1EngineLifecycle:
    def test_catalog_entry_downloaded_status(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        cat_not_downloaded = s1_engine.get_catalog_entry()
        assert cat_not_downloaded["full_id"] == "local/s1-mini-q4_k_m"
        assert cat_not_downloaded["downloaded"] is False
        assert cat_not_downloaded["polish_supported"] is False
        assert "Download required" in cat_not_downloaded["polish_unavailable_reason"]

        target = tmp_path / s1_engine.S1_FILENAME
        target.write_bytes(b"GGUF_TEST_S1" * 100)
        cat_downloaded = s1_engine.get_catalog_entry()
        assert cat_downloaded["downloaded"] is True
        assert cat_downloaded["polish_supported"] is True
        assert cat_downloaded["polish_unavailable_reason"] == ""

    def test_polish_with_s1_mock_runner(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / s1_engine.S1_FILENAME
        target.write_bytes(b"GGUF_TEST" * 50)
        s1_engine.polish_with_s1._mock_runner = lambda t, inst: f"S1 polished: {t.strip()}"
        result = s1_engine.polish_with_s1("uh friday no wait thursday")
        assert result == "S1 polished: uh friday no wait thursday"

    def test_polish_with_s1_empty(self):
        assert s1_engine.polish_with_s1("") == ""
        assert s1_engine.polish_with_s1("   ") == "   "

    def test_polish_with_s1_not_downloaded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert s1_engine.polish_with_s1("hello world") is None


class TestVoicePolishBridgeAndApiServer:
    def test_bridge_can_execute_s1(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert not voice_polish_bridge.can_execute_model("local/s1-mini-q4_k_m")
        assert not voice_polish_bridge.can_execute_model("superwhisper/s1-mini-q4_k_m")

        target = tmp_path / s1_engine.S1_FILENAME
        target.write_bytes(b"GGUF_S1_BRIDGE" * 50)
        assert voice_polish_bridge.can_execute_model("local/s1-mini-q4_k_m")
        assert voice_polish_bridge.can_execute_model("superwhisper/s1-mini-q4_k_m")

    def test_bridge_request_polish_s1(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / s1_engine.S1_FILENAME
        target.write_bytes(b"GGUF_S1_BRIDGE" * 50)
        s1_engine.polish_with_s1._mock_runner = lambda t, inst: f"Cleaned by S1: {t}"

        res = voice_polish_bridge.request_polish("local/s1-mini-q4_k_m", "test text", timeout_seconds=5.0)
        assert res == "Cleaned by S1: test text"

    def test_api_server_get_includes_s1(self):
        from voice_flow.gui.api_server import VoiceFlowApiHandler

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        handler.headers = {"Host": "127.0.0.1:8991"}
        responses = []
        handler.send_json_response = lambda data, code=200: responses.append((code, data))

        handler.path = "/api/voice-flow-polish/get"
        handler.do_GET()

        assert len(responses) == 1
        code, payload = responses.pop()
        assert code == 200
        assert payload["success"] is True
        model_ids = [m["full_id"] for m in payload["models"]]
        assert "local/s1-mini-q4_k_m" in model_ids
        assert "local/lfm2.5-350m-qad-q4_0" in model_ids
        assert "microsoft/windows-ai-text-rewriter" in model_ids

    def test_api_server_update_allows_s1(self):
        from voice_flow.gui.api_server import VoiceFlowApiHandler

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        handler.headers = {"Host": "127.0.0.1:8991"}
        responses = []
        handler.send_json_response = lambda data, code=200: responses.append((code, data))

        body = json.dumps({"model": "local/s1-mini-q4_k_m"}).encode("utf-8")
        handler.path = "/api/voice-flow-polish/update"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()

        code, payload = responses.pop()
        assert code == 200
        assert payload["success"] is True
        assert payload["active_model"] == "local/s1-mini-q4_k_m"
        assert storage.get_setting("voice_flow_polish_model") == "local/s1-mini-q4_k_m"

    def test_api_server_downloadable_select_s1(self, monkeypatch, tmp_path):
        from voice_flow.gui.api_server import VoiceFlowApiHandler

        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / s1_engine.S1_FILENAME
        target.write_bytes(b"GGUF_TEST_S1" * 100)

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        handler.headers = {"Host": "127.0.0.1:8991"}
        responses = []
        handler.send_json_response = lambda data, code=200: responses.append((code, data))

        body = json.dumps({"model_id": "superwhisper/s1-mini-q4_k_m"}).encode("utf-8")
        handler.path = "/api/downloadable-models/select"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()

        code, payload = responses.pop()
        assert code == 200
        assert payload["success"] is True
        assert payload["target"] == "voice_flow_polish"
        assert payload["active_model"] == "local/s1-mini-q4_k_m"
        assert storage.get_setting("voice_flow_polish_model") == "local/s1-mini-q4_k_m"
