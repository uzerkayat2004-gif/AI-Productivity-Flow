"""Comprehensive test suite for Microsoft Windows AI TextRewriter and Liquid LFM 2.5 Voice Polishing."""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
import pytest

from voice_flow import (
    downloadable_models,
    lfm_engine,
    windows_ai_rewriter,
    voice_polish_bridge,
)
from voice_flow.storage import storage


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure clean state before and after each test."""
    orig_polish_model = storage.get_setting("voice_flow_polish_model")
    windows_ai_rewriter.set_mock_ready_state(None)
    yield
    windows_ai_rewriter.set_mock_ready_state(None)
    if orig_polish_model is not None:
        storage.save_setting("voice_flow_polish_model", orig_polish_model)
    else:
        storage.save_setting("voice_flow_polish_model", "local/deterministic")
    if hasattr(lfm_engine.polish_with_lfm, "_mock_runner"):
        delattr(lfm_engine.polish_with_lfm, "_mock_runner")
    if hasattr(windows_ai_rewriter.rewrite_text, "_mock_rewriter"):
        delattr(windows_ai_rewriter.rewrite_text, "_mock_rewriter")


class TestWindowsAIRewriter:
    def test_ready_states_and_availability(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        assert windows_ai_rewriter.get_language_model_ready_state() == "Ready"
        assert windows_ai_rewriter.is_windows_ai_available() is True

        windows_ai_rewriter.set_mock_ready_state("NotReady")
        assert windows_ai_rewriter.get_language_model_ready_state() == "NotReady"
        assert windows_ai_rewriter.is_windows_ai_available() is False

        windows_ai_rewriter.set_mock_ready_state("Disabled")
        assert windows_ai_rewriter.get_language_model_ready_state() == "Disabled"
        assert windows_ai_rewriter.is_windows_ai_available() is False

    def test_env_override(self, monkeypatch):
        windows_ai_rewriter.set_mock_ready_state(None)
        monkeypatch.setenv("VOICE_FLOW_WINDOWS_AI_READY_STATE", "Ready")
        assert windows_ai_rewriter.get_language_model_ready_state() == "Ready"
        assert windows_ai_rewriter.is_windows_ai_available() is True

    def test_rewrite_text_empty(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        assert windows_ai_rewriter.rewrite_text("") == ""
        assert windows_ai_rewriter.rewrite_text("   ") == "   "

    def test_rewrite_text_not_ready_returns_none(self):
        windows_ai_rewriter.set_mock_ready_state("NotReady")
        assert windows_ai_rewriter.rewrite_text("um uh hello world") is None

    def test_rewrite_text_mock_rewriter(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        windows_ai_rewriter.rewrite_text._mock_rewriter = lambda t, inst: f"Polished: {t.strip()}"
        assert windows_ai_rewriter.rewrite_text("um test text") == "Polished: um test text"

    def test_catalog_entry(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        cat = windows_ai_rewriter.get_catalog_entry()
        assert cat["full_id"] == "microsoft/windows-ai-text-rewriter"
        assert cat["provider"] == "microsoft"
        assert cat["is_default"] is True
        assert cat["ready_state"] == "Ready"
        assert cat["polish_supported"] is True
        assert cat["polish_unavailable_reason"] == ""

        windows_ai_rewriter.set_mock_ready_state("NotReady")
        cat_not_ready = windows_ai_rewriter.get_catalog_entry()
        assert cat_not_ready["ready_state"] == "NotReady"
        assert cat_not_ready["polish_supported"] is False
        assert cat_not_ready["is_default"] is False
        assert "Copilot+" in cat_not_ready["polish_unavailable_reason"]

    def test_default_polish_model_availability(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        assert storage.get_default_polish_model() == "microsoft/windows-ai-text-rewriter"

        windows_ai_rewriter.set_mock_ready_state("NotReady")
        assert storage.get_default_polish_model() == "local/deterministic"

        windows_ai_rewriter.set_mock_ready_state(None)
        assert storage.get_default_polish_model() == "local/deterministic"


class TestLFMEngine:
    def test_is_lfm_downloaded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert lfm_engine.is_lfm_downloaded() is False

        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"GGUF_TEST_LFM" * 100)
        assert lfm_engine.is_lfm_downloaded() is True
        assert lfm_engine.get_lfm_model_path() == target

    def test_polish_with_lfm_empty(self):
        assert lfm_engine.polish_with_lfm("") == ""
        assert lfm_engine.polish_with_lfm("   ") == "   "

    def test_polish_with_lfm_not_downloaded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert lfm_engine.polish_with_lfm("um uh hello there") is None

    def test_polish_with_lfm_mock_runner(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"GGUF_TEST" * 50)
        lfm_engine.polish_with_lfm._mock_runner = lambda t, inst: f"LFM polished: {t.strip()}"
        assert lfm_engine.polish_with_lfm("uh test") == "LFM polished: uh test"

    def test_catalog_entry(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        entry_undownloaded = lfm_engine.get_catalog_entry()
        assert entry_undownloaded["full_id"] == "local/lfm2.5-350m-qad-q4_0"
        assert entry_undownloaded["downloaded"] is False
        assert entry_undownloaded["polish_supported"] is False
        assert "Download required" in entry_undownloaded["polish_unavailable_reason"]

        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"GGUF_TEST" * 50)
        entry_downloaded = lfm_engine.get_catalog_entry()
        assert entry_downloaded["downloaded"] is True
        assert entry_downloaded["polish_supported"] is True
        assert entry_downloaded["polish_unavailable_reason"] == ""


class TestDownloadableModelsIntegration:
    def test_registry_has_lfm_in_all_and_polish(self):
        assert any(m["id"] == "liquid/lfm2.5-350m-qad-q4_0" for m in downloadable_models.ALL_DOWNLOADABLE_MODELS_REGISTRY)
        assert any(m["id"] == "liquid/lfm2.5-350m-qad-q4_0" for m in downloadable_models.DOWNLOADABLE_POLISH_MODELS_REGISTRY)
        # Verify STT registry does NOT contain LFM
        assert not any(m["id"] == "liquid/lfm2.5-350m-qad-q4_0" for m in downloadable_models.DOWNLOADABLE_STT_MODELS_REGISTRY)

    def test_get_all_models_status_filtering(self):
        stt_only = downloadable_models.get_all_models_status(category="stt")
        assert len(stt_only) == 2
        assert all("stt" in (m.get("category") or m.get("task") or "").lower() for m in stt_only)

        polish_only = downloadable_models.get_all_models_status(category="voice_polishing")
        assert len(polish_only) == 1
        assert polish_only[0]["id"] == "liquid/lfm2.5-350m-qad-q4_0"

        all_models = downloadable_models.get_all_models_status(include_polish=True)
        assert len(all_models) == 3

    def test_downloaded_polish_models(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert len(downloadable_models.get_downloaded_polish_models()) == 0

        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"MOCK_LFM_MODEL" * 100)
        downloaded = downloadable_models.get_downloaded_polish_models()
        assert len(downloaded) == 1
        assert downloaded[0]["id"] == "liquid/lfm2.5-350m-qad-q4_0"


class TestVoicePolishBridge:
    def test_can_execute_model_windows_ai(self):
        windows_ai_rewriter.set_mock_ready_state("Ready")
        assert voice_polish_bridge.can_execute_model("microsoft/windows-ai-text-rewriter") is True
        windows_ai_rewriter.set_mock_ready_state("NotReady")
        assert voice_polish_bridge.can_execute_model("microsoft/windows-ai-text-rewriter") is False

    def test_can_execute_model_lfm(self, monkeypatch, tmp_path):
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        assert voice_polish_bridge.can_execute_model("local/lfm2.5-350m-qad-q4_0") is False

        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"MOCK_LFM_MODEL" * 100)
        assert voice_polish_bridge.can_execute_model("local/lfm2.5-350m-qad-q4_0") is True

    def test_request_polish_dispatch(self, monkeypatch, tmp_path):
        # 1. Windows AI
        windows_ai_rewriter.set_mock_ready_state("Ready")
        windows_ai_rewriter.rewrite_text._mock_rewriter = lambda t, inst: f"Windows AI: {t}"
        res = voice_polish_bridge.request_polish("microsoft/windows-ai-text-rewriter", "hello world", timeout_seconds=5.0)
        assert res == "Windows AI: hello world"

        # 2. LFM
        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"MOCK_LFM_MODEL" * 100)
        lfm_engine.polish_with_lfm._mock_runner = lambda t, inst: f"LFM Engine: {t}"
        res2 = voice_polish_bridge.request_polish("local/lfm2.5-350m-qad-q4_0", "hello world", timeout_seconds=5.0)
        assert res2 == "LFM Engine: hello world"


class TestApiServerIntegration:
    def test_voice_flow_polish_get_includes_both_models(self):
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
        assert "microsoft/windows-ai-text-rewriter" in model_ids
        assert "local/lfm2.5-350m-qad-q4_0" in model_ids
        assert "local/deterministic" in model_ids

    def test_voice_flow_polish_update_allows_both_models(self):
        from voice_flow.gui.api_server import VoiceFlowApiHandler

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        handler.headers = {"Host": "127.0.0.1:8991"}
        responses = []
        handler.send_json_response = lambda data, code=200: responses.append((code, data))

        # Update to windows ai
        body = json.dumps({"model": "microsoft/windows-ai-text-rewriter"}).encode("utf-8")
        handler.path = "/api/voice-flow-polish/update"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()
        code, payload = responses.pop()
        assert code == 200
        assert payload["success"] is True
        assert payload["active_model"] == "microsoft/windows-ai-text-rewriter"

        # Update to lfm
        body2 = json.dumps({"model": "local/lfm2.5-350m-qad-q4_0"}).encode("utf-8")
        handler.path = "/api/voice-flow-polish/update"
        handler.headers["Content-Length"] = str(len(body2))
        handler.rfile = io.BytesIO(body2)
        handler.do_POST()
        code2, payload2 = responses.pop()
        assert code2 == 200
        assert payload2["success"] is True
        assert payload2["active_model"] == "local/lfm2.5-350m-qad-q4_0"

    def test_downloadable_models_select_handles_polish_model(self, monkeypatch, tmp_path):
        from voice_flow.gui.api_server import VoiceFlowApiHandler

        monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: tmp_path)
        target = tmp_path / lfm_engine.LFM_FILENAME
        target.write_bytes(b"MOCK_LFM_MODEL" * 100)

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        handler.headers = {"Host": "127.0.0.1:8991"}
        responses = []
        handler.send_json_response = lambda data, code=200: responses.append((code, data))

        body = json.dumps({"model_id": "liquid/lfm2.5-350m-qad-q4_0"}).encode("utf-8")
        handler.path = "/api/downloadable-models/select"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()

        code, payload = responses.pop()
        assert code == 200
        assert payload["success"] is True
        assert payload["target"] == "voice_flow_polish"
        assert payload["active_model"] == "local/lfm2.5-350m-qad-q4_0"
        assert storage.get_setting("voice_flow_polish_model") == "local/lfm2.5-350m-qad-q4_0"
