from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import numpy as np

from voice_flow.dictionary import DictionaryEngine
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
import voice_flow.style_engine as style_engine_module


@pytest.fixture
def voice_api(monkeypatch, tmp_path):
    """A hermetic loopback server backed by an isolated Voice Flow database."""
    store = StorageEngine(str(tmp_path / "voice-features.db"))
    monkeypatch.setattr(api_server, "storage", store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", store
    server.shutdown()
    server.server_close()


def _request(url: str, payload: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_insights_count_only_completed_dictations_and_not_retries(tmp_path):
    store = StorageEngine(str(tmp_path / "metrics.db"))
    completed = store.add_dictation("one two", "one two", duration_sec=2, status="success")
    failed = store.add_dictation("failed words", "failed words", duration_sec=2, status="transcription_failed")
    pending = store.add_dictation("pending words", "pending words", duration_sec=2, status="processing")
    retry = store.add_dictation("retry words", "retry words", duration_sec=2, status="success")
    assert store.update_dictation(retry.id, retry_count=1)
    assert store.update_dictation(failed.id, retry_count=1)

    insights = store.get_insights()

    assert insights["dictation_count"] == 2
    assert insights["total_words"] == 4
    assert insights["dictionary_fixes"] == 0
    assert completed.id != pending.id


def test_insights_exclude_paste_failures_and_count_a_retried_success_once(tmp_path):
    store = StorageEngine(str(tmp_path / "metric-statuses.db"))
    ready = store.add_dictation("ready text", "ready text", duration_sec=2, status="success", insertion_status="ready_to_paste")
    retried = store.add_dictation("", "", duration_sec=2, status="processing")
    assert store.update_dictation(retried.id, status="transcription_failed", retry_count=1)
    assert store.update_dictation(retried.id, raw_text="retry worked", polished_text="retry worked", status="success", retry_count=2, insertion_status="ready_to_paste")
    store.add_dictation("paste failed text", "paste failed text", duration_sec=2, status="paste_failed", insertion_status="failed")

    insights = store.get_insights()

    assert ready.id != retried.id
    assert insights["dictation_count"] == 2
    assert insights["total_words"] == 4


def test_style_endpoint_rejects_cross_category_preset_and_preserves_saved_choice(voice_api):
    base_url, store = voice_api
    status, response = _request(
        f"{base_url}/api/styles/update",
        {"category": "work", "style_id": "email_formal"},
    )
    assert status == 400
    assert response["success"] is False
    assert store.get_setting("style_work") is None

    status, response = _request(
        f"{base_url}/api/styles/update",
        {"category": "work", "style_id": "casual"},
    )
    assert status == 200
    assert response["style_id"] == "work_casual"
    _, loaded = _request(f"{base_url}/api/styles/get")
    assert loaded["styles"]["work"] == "work_casual"


def test_dictionary_edits_refresh_an_existing_engine_and_protect_urls(tmp_path):
    store = StorageEngine(str(tmp_path / "dictionary.db"))
    engine = DictionaryEngine(store)

    assert store.add_dictionary_word("VoiceFlow")
    assert engine.apply_dictionary_post_processing("voiceflow is ready") == "VoiceFlow is ready"
    assert engine.apply_dictionary_post_processing("visit https://voiceflow.example") == "visit https://voiceflow.example"
    assert store.add_dictionary_correction("acme", "AcmeAPI")
    assert engine.apply_dictionary_post_processing("acme is ready") == "AcmeAPI is ready"
    # Explicit corrections must obey the same protected-content boundary as
    # dictionary terms. A host name is user data, not spoken vocabulary.
    assert (
        engine.apply_dictionary_post_processing("visit https://example.test/acme")
        == "visit https://example.test/acme"
    )


def test_dictionary_mutation_response_keeps_the_same_snippet_snapshot_as_get(voice_api):
    base_url, store = voice_api
    store.add_snippet("addr", "42 Galaxy Way")

    status, changed = _request(f"{base_url}/api/dictionary/add", {"word": "VoiceFlow"})
    assert status == 200
    assert changed["words"] == ["VoiceFlow", "addr -> 42 Galaxy Way"]
    _, snapshot = _request(f"{base_url}/api/dictionary")
    assert changed["words"] == snapshot


def test_saved_category_style_drives_the_resolved_runtime_instruction(monkeypatch, tmp_path):
    store = StorageEngine(str(tmp_path / "styles.db"))
    monkeypatch.setattr(style_engine_module, "storage", store)
    engine = style_engine_module.StyleEngine()
    store.save_setting("style_work", "work_excited")

    resolved = engine.resolve(site_host="app.slack.com")

    assert resolved.category == "work"
    assert resolved.style_id == "work_excited"
    assert resolved.instruction == style_engine_module.STYLE_INSTRUCTIONS["work_excited"]


def test_voice_polish_selected_model_round_trips_without_catalog_mutation(voice_api):
    base_url, store = voice_api
    selected = "gemini/gemini-2.5-flash"
    status, saved = _request(
        f"{base_url}/api/voice-flow-polish/update",
        {"model": selected, "speed_mode": "fast"},
    )
    assert status == 200
    assert saved["active_model"] == selected
    assert store.get_setting("voice_flow_polish_model") == selected
    _, loaded = _request(f"{base_url}/api/voice-flow-polish/get")
    assert loaded["active_model"] == selected
    assert loaded["speed_mode"] == "fast"


def test_voice_stt_selected_model_round_trips(voice_api):
    base_url, store = voice_api
    selected = "deepgram/nova-3"

    status, saved = _request(
        f"{base_url}/api/voice-flow-stt/update",
        {"model_id": selected},
    )

    assert status == 200
    assert saved == {"success": True, "active_model": selected}
    assert store.get_setting("voice_flow_stt_model") == selected
    _, loaded = _request(f"{base_url}/api/voice-flow-stt/get")
    assert loaded["active_model"] == selected


def test_polish_catalog_uses_voice_credentials_and_has_one_local_choice(voice_api):
    base_url, store = voice_api
    store.add_provider_connection("gemini", "Synthetic test", "synthetic-key")
    store.add_provider_model("gemini", "gemini-catalog-test", "Synthetic polish model")
    _, loaded = _request(f"{base_url}/api/voice-flow-polish/get")
    refs = [model["full_id"] for model in loaded["models"]]
    assert refs.count("local/deterministic") == 1
    assert "gemini/gemini-catalog-test" in refs
    assert not any("Code2Video" in model["display_name"] for model in loaded["models"])
