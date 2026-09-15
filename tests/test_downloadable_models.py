"""Tests for Voice Flow Downloadable Models (Nemotron STT GGUF models)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from voice_flow import downloadable_models
from voice_flow.storage import storage


@pytest.fixture
def temp_models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect models dir to a temporary directory."""
    m_dir = tmp_path / "models"
    m_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: m_dir)
    return m_dir


def test_registry_contains_required_models():
    """Verify registry specifications for both NVIDIA Nemotron models."""
    registry = downloadable_models.DOWNLOADABLE_MODELS_REGISTRY
    assert len(registry) == 2

    m1 = next((m for m in registry if m["id"] == "nvidia/nemotron-speech-streaming-en-0.6b"), None)
    assert m1 is not None
    assert m1["name"] == "Nemotron Speech Streaming English 0.6B"
    assert m1["size_mb"] == 700
    assert m1["size_display"] == "700 MB"
    assert m1["format"] == "Local GGUF"
    assert m1["tag"] == "Speech-to-Text (STT)"
    assert m1["languages"] == ["English (en)"]
    assert not m1["is_multilingual"]
    assert "huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b" in m1["repo_url"]
    assert m1["filename"] == "nemotron-speech-streaming-en-0.6b.q8_0.gguf"

    m2 = next((m for m in registry if m["id"] == "nvidia/nemotron-3.5-asr-streaming-0.6b"), None)
    assert m2 is not None
    assert m2["name"] == "Nemotron 3.5 ASR Streaming 0.6B"
    assert m2["size_mb"] == 742
    assert m2["size_display"] == "742 MB"
    assert m2["format"] == "Local GGUF"
    assert m2["tag"] == "Speech-to-Text (STT)"
    assert m2["is_multilingual"]
    assert len(m2["languages"]) == 35
    assert "English (en)" in m2["languages"]
    assert "Spanish (es)" in m2["languages"]
    assert "French (fr)" in m2["languages"]
    assert "German (de)" in m2["languages"]
    assert "huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b" in m2["repo_url"]
    assert m2["filename"] == "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf"


def test_model_status_lifecycle(temp_models_dir: Path):
    """Test status transitions: not_downloaded -> downloaded -> deleted."""
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"

    # Initial state: not downloaded
    status = downloadable_models.get_model_status(m_id)
    assert status is not None
    assert status["status"] == "not_downloaded"
    assert not status["file_exists"]
    assert status["progress"] == 0.0

    # Simulate completed download by writing file
    target_file = temp_models_dir / status["filename"]
    target_file.write_bytes(b"GGUF_MOCK_DATA" * 1024)

    status_after = downloadable_models.get_model_status(m_id)
    assert status_after["status"] == "downloaded"
    assert status_after["file_exists"]
    assert status_after["progress"] == 100.0
    assert status_after["downloaded_bytes"] == target_file.stat().st_size

    # Verify get_downloaded_models includes it
    downloaded_list = downloadable_models.get_downloaded_models()
    assert any(m["id"] == m_id for m in downloaded_list)

    # Set as active STT model in storage
    storage.save_setting("voice_flow_stt_model", status["full_id"])
    assert storage.get_setting("voice_flow_stt_model") == status["full_id"]

    # Delete model
    ok, msg = downloadable_models.delete_downloaded_model(m_id)
    assert ok
    assert not target_file.exists()

    status_del = downloadable_models.get_model_status(m_id)
    assert status_del["status"] == "not_downloaded"
    assert not status_del["file_exists"]

    # Storage active model should revert back to faster-whisper default
    assert storage.get_setting("voice_flow_stt_model") == "local/faster-whisper-base.en"


def test_stt_catalog_only_includes_downloaded_models(temp_models_dir: Path):
    """Verify that STT catalog (/api/voice-flow-stt/get) includes models ONLY after download."""
    # Ensure neither model is downloaded
    downloaded_init = downloadable_models.get_downloaded_models()
    assert len(downloaded_init) == 0

    m1 = downloadable_models.get_model_spec("nvidia/nemotron-speech-streaming-en-0.6b")
    assert m1 is not None

    # Simulate downloading m1
    (temp_models_dir / m1["filename"]).write_bytes(b"GGUF_DATA" * 500)

    downloaded = downloadable_models.get_downloaded_models()
    assert len(downloaded) == 1
    assert downloaded[0]["id"] == m1["id"]

    # Storage method check
    assert len(storage.get_downloaded_stt_models()) == 1


def test_download_worker_and_cancellation(temp_models_dir: Path):
    """Test start_model_download and cancel_model_download."""
    m_id = "nvidia/nemotron-3.5-asr-streaming-0.6b"
    spec = downloadable_models.get_model_spec(m_id)
    assert spec is not None

    # Mock urllib.request.urlopen to simulate a streaming response
    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "1000000"
    mock_resp.read.side_effect = [b"A" * 10000, b"B" * 10000, b""]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok
        assert st["status"] == "downloading"

        # Cancel download
        cancel_ok, cancel_msg = downloadable_models.cancel_model_download(m_id)
        assert cancel_ok

        part_file = temp_models_dir / f"{spec['filename']}.part"
        assert not part_file.exists()


def test_api_server_downloadable_models_endpoints(temp_models_dir: Path):
    """Test HTTP API handler integration via real do_GET and do_POST dispatch."""
    import io
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
    handler.headers = {"Host": "127.0.0.1:8991"}
    response_data = []

    def mock_send_json(data, code=200):
        response_data.append((code, data))

    handler.send_json_response = mock_send_json

    # 1. GET /api/downloadable-models
    handler.path = "/api/downloadable-models"
    handler.do_GET()
    assert len(response_data) == 1
    code, payload = response_data.pop()
    assert code == 200
    assert payload["success"] is True
    assert len(payload["models"]) == 2

    # 2. Select before download should fail via /api/downloadable-models/select
    body = json.dumps({"model_id": "nvidia/nemotron-speech-streaming-en-0.6b"}).encode("utf-8")
    handler.path = "/api/downloadable-models/select"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    code, err_payload = response_data.pop()
    assert code == 400
    assert "downloaded before selecting" in err_payload["error"]

    # 3. Download, then select should succeed
    spec = downloadable_models.get_model_spec("nvidia/nemotron-speech-streaming-en-0.6b")
    target_file = temp_models_dir / spec["filename"]
    target_file.write_bytes(b"GGUF" * 200)

    handler.path = "/api/downloadable-models/select"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    code, ok_payload = response_data.pop()
    assert code == 200
    assert ok_payload["active_model"] == spec["full_id"]
    assert storage.get_setting("voice_flow_stt_model") == spec["full_id"]


def test_stt_update_rejects_undownloaded_model(temp_models_dir: Path):
    """POST /api/voice-flow-stt/update must reject downloadable models not yet present on disk."""
    import io
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
    handler.headers = {"Host": "127.0.0.1:8991"}
    responses = []
    handler.send_json_response = lambda data, code=200: responses.append((code, data))

    # Attempt to select Nemotron model when NOT downloaded
    body = json.dumps({"model_id": "local/nemotron-speech-streaming-en-0.6b"}).encode("utf-8")
    handler.path = "/api/voice-flow-stt/update"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.do_POST()

    status, payload = responses.pop()
    assert status == 400
    assert "downloaded before selecting" in payload["error"]

    # Now simulate download and re-try: should succeed
    spec = downloadable_models.get_model_spec("local/nemotron-speech-streaming-en-0.6b")
    (temp_models_dir / spec["filename"]).write_bytes(b"GGUF_ACTIVE" * 50)

    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    status, payload = responses.pop()
    assert status == 200
    assert payload["active_model"] == "local/nemotron-speech-streaming-en-0.6b"
    assert storage.get_setting("voice_flow_stt_model") == "local/nemotron-speech-streaming-en-0.6b"


def test_stt_get_heals_deleted_model_to_default(temp_models_dir: Path):
    """GET /api/voice-flow-stt/get should automatically revert active_model if file was deleted."""
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
    handler.headers = {"Host": "127.0.0.1:8991"}
    responses = []
    handler.send_json_response = lambda data, code=200: responses.append((code, data))

    # Set active setting to Nemotron, but file does not exist on disk
    storage.save_setting("voice_flow_stt_model", "local/nemotron-speech-streaming-en-0.6b")

    handler.path = "/api/voice-flow-stt/get"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    # Should self-heal back to default faster-whisper
    assert payload["active_model"] == "local/faster-whisper-base.en"
    assert storage.get_setting("voice_flow_stt_model") == "local/faster-whisper-base.en"


def test_cancel_download_closes_socket(temp_models_dir: Path):
    """Test that cancel_model_download closes the response stream socket immediately."""
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"
    started = threading.Event()

    def fake_read(size):
        started.set()
        time.sleep(0.05)
        return b"CHUNK"

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.headers.get.return_value = "500000"
    mock_resp.read.side_effect = fake_read

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok
        # Wait until download worker has opened socket and is actively reading
        assert started.wait(timeout=2.0)
        # Call cancel
        cancel_ok, cancel_msg = downloadable_models.cancel_model_download(m_id)
        assert cancel_ok
        # Ensure mock_resp.close() was called to interrupt reading
        mock_resp.close.assert_called()


def test_handler_routes_full_pipeline(temp_models_dir: Path):
    """Test actual do_GET and do_POST dispatcher methods on VoiceFlowApiHandler."""
    import io
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
    handler.headers = {"Host": "127.0.0.1:8991"}
    responses = []

    def mock_send(data, status=200):
        responses.append((status, data))

    handler.send_json_response = mock_send

    # Test GET /api/downloadable-models
    handler.path = "/api/downloadable-models"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    assert payload["success"] is True
    assert len(payload["models"]) == 2

    # Test GET /api/downloadable-models/status?id=nvidia/nemotron-speech-streaming-en-0.6b
    handler.path = "/api/downloadable-models/status?id=nvidia/nemotron-speech-streaming-en-0.6b"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    assert payload["success"] is True
    assert payload["model"]["id"] == "nvidia/nemotron-speech-streaming-en-0.6b"

    # Test GET /api/voice-flow-stt/get when NOT downloaded: model should NOT be in STT list
    handler.path = "/api/voice-flow-stt/get"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    assert payload["success"] is True
    stt_models = [m["full_id"] for m in payload["models"]]
    assert "local/nemotron-speech-streaming-en-0.6b" not in stt_models

    # Now write a mock file so it is downloaded
    spec = downloadable_models.get_model_spec("nvidia/nemotron-speech-streaming-en-0.6b")
    (temp_models_dir / spec["filename"]).write_bytes(b"GGUF_TEST" * 50)

    # Re-run GET /api/voice-flow-stt/get: NOW it MUST appear in STT list!
    handler.path = "/api/voice-flow-stt/get"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    stt_models = [m["full_id"] for m in payload["models"]]
    assert "local/nemotron-speech-streaming-en-0.6b" in stt_models

    # Test POST /api/downloadable-models/select
    body = json.dumps({"model_id": "nvidia/nemotron-speech-streaming-en-0.6b"}).encode("utf-8")
    handler.path = "/api/downloadable-models/select"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    status, payload = responses.pop()
    assert status == 200
    assert payload["success"] is True
    assert payload["active_model"] == "local/nemotron-speech-streaming-en-0.6b"

    # Test POST /api/downloadable-models/delete
    body = json.dumps({"model_id": "nvidia/nemotron-speech-streaming-en-0.6b"}).encode("utf-8")
    handler.path = "/api/downloadable-models/delete"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    status, payload = responses.pop()
    assert status == 200
    assert payload["success"] is True

    # Re-check STT catalog: model must no longer appear in STT catalog after delete
    handler.path = "/api/voice-flow-stt/get"
    handler.do_GET()
    status, payload = responses.pop()
    assert status == 200
    stt_models = [m["full_id"] for m in payload["models"]]
    assert "local/nemotron-speech-streaming-en-0.6b" not in stt_models
    assert storage.get_setting("voice_flow_stt_model") == "local/faster-whisper-base.en"


def test_progress_tracking_metrics_and_formatting(temp_models_dir: Path):
    """Verify detailed progress metrics (MB downloaded, MB remaining, speed, ETA)."""
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"

    # Status before download
    st = downloadable_models.get_model_status(m_id)
    assert st is not None
    assert st["downloaded_mb"] == 0.0
    assert st["total_mb"] == 667.5 or st["total_mb"] == 700.0 or st["total_mb"] > 600
    assert st["remaining_mb"] > 0
    assert "MB remaining" in st["remaining_display"]
    assert st["downloaded_display"] == "0.0 MB"

    # Helper formatters unit check
    assert downloadable_models.format_mb(1048576) == 1.0
    assert downloadable_models.format_mb(104857600) == 100.0
    assert downloadable_models.format_speed(1048576 * 8.5) == "8.5 MB/s"
    assert downloadable_models.format_speed(512 * 1024) == "512 KB/s"
    assert downloadable_models.format_eta(45) == "45s left"
    assert downloadable_models.format_eta(125) == "2m 5s left"
    assert downloadable_models.format_eta(3700) == "1h 1m left"


def test_download_worker_streams_and_completes(temp_models_dir: Path):
    """Verify download worker writes chunks, calculates progress, and completes atomically."""
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"
    spec = downloadable_models.get_model_spec(m_id)
    assert spec is not None

    data_chunk1 = b"NEMOTRON_CHUNK_1" * 1000
    data_chunk2 = b"NEMOTRON_CHUNK_2" * 1000
    total_data = data_chunk1 + data_chunk2

    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = str(len(total_data))
    mock_resp.read.side_effect = [data_chunk1, data_chunk2, b""]
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok

        target_file = temp_models_dir / spec["filename"]
        # Wait for download thread to finish
        for _ in range(50):
            time.sleep(0.05)
            curr = downloadable_models.get_model_status(m_id)
            if curr and curr["status"] == "downloaded":
                break

        final_st = downloadable_models.get_model_status(m_id)
        assert final_st["status"] == "downloaded"
        assert final_st["file_exists"] is True
        assert final_st["progress"] == 100.0
        assert final_st["downloaded_bytes"] == len(total_data)
        assert final_st["remaining_bytes"] == 0
        assert target_file.exists()
        assert target_file.read_bytes() == total_data


def test_download_error_handling_records_failure(temp_models_dir: Path):
    """Verify network or HTTP errors are recorded cleanly with part file cleanup."""
    import urllib.error
    m_id = "nvidia/nemotron-3.5-asr-streaming-0.6b"
    spec = downloadable_models.get_model_spec(m_id)
    assert spec is not None

    http_err = urllib.error.HTTPError(
        url=spec["download_url"],
        code=404,
        msg="Not Found",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok

        # Wait for thread to record failure
        for _ in range(50):
            time.sleep(0.05)
            curr = downloadable_models.get_model_status(m_id)
            if curr and curr["status"] == "failed":
                break

        fail_st = downloadable_models.get_model_status(m_id)
        assert fail_st["status"] == "failed"
        assert fail_st["error"] is not None
        assert "404" in fail_st["error"]
        assert not (temp_models_dir / f"{spec['filename']}.part").exists()


def test_truncated_download_prevents_corrupt_file(temp_models_dir: Path):
    """Verify that a premature connection drop / truncated download is rejected and not saved as completed."""
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"
    spec = downloadable_models.get_model_spec(m_id)
    assert spec is not None

    # Server claims total is 100,000 bytes, but only provides 10,000 bytes before EOF
    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = "100000"
    mock_resp.read.side_effect = [b"PARTIAL_DATA" * 500, b""]
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok

        for _ in range(50):
            time.sleep(0.05)
            curr = downloadable_models.get_model_status(m_id)
            if curr and curr["status"] == "failed":
                break

        fail_st = downloadable_models.get_model_status(m_id)
        assert fail_st["status"] == "failed"
        assert "Incomplete download" in fail_st["error"]
        # Destination file must NOT exist on disk!
        assert not (temp_models_dir / spec["filename"]).exists()
        # Part file must have been cleaned up!
        assert not (temp_models_dir / f"{spec['filename']}.part").exists()


def test_ssl_fallback_on_ssl_error(temp_models_dir: Path):
    """Verify fallback to unverified SSL context if standard SSL handshake encounters an error."""
    import ssl
    m_id = "nvidia/nemotron-speech-streaming-en-0.6b"
    spec = downloadable_models.get_model_spec(m_id)
    assert spec is not None

    payload = b"GGUF_SSL_TEST" * 100
    successful_resp = MagicMock()
    successful_resp.headers.get.return_value = str(len(payload))
    successful_resp.read.side_effect = [payload, b""]
    successful_resp.__enter__.return_value = successful_resp

    # First call with verified ctx raises SSLError; second call succeeds
    with patch("urllib.request.urlopen", side_effect=[ssl.SSLError("CERTIFICATE_VERIFY_FAILED"), successful_resp]) as mock_urlopen:
        ok, msg, st = downloadable_models.start_model_download(m_id)
        assert ok

        for _ in range(50):
            time.sleep(0.05)
            curr = downloadable_models.get_model_status(m_id)
            if curr and curr["status"] == "downloaded":
                break

        final_st = downloadable_models.get_model_status(m_id)
        assert final_st["status"] == "downloaded"
        assert final_st["downloaded_bytes"] == len(payload)
        assert (temp_models_dir / spec["filename"]).exists()
        assert mock_urlopen.call_count == 2


def test_html_modal_hierarchy_and_clean_nesting():
    """Verify that download-model-confirm-modal is a root modal and NOT nested inside another modal."""
    from html.parser import HTMLParser
    index_path = Path(__file__).resolve().parent.parent / "src" / "voice_flow" / "gui" / "index.html"
    content = index_path.read_text(encoding="utf-8")

    class HierarchyChecker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.download_parents = []
            self.delete_parents = []

        def handle_starttag(self, tag, attrs):
            if tag in ('meta', 'link', 'img', 'br', 'hr', 'input'):
                return
            d = dict(attrs)
            el_id = d.get("id", "")
            self.stack.append((tag, el_id))
            if el_id == "download-model-confirm-modal":
                self.download_parents = list(self.stack[:-1])
            elif el_id == "delete-model-confirm-modal":
                self.delete_parents = list(self.stack[:-1])

        def handle_endtag(self, tag):
            if tag in ('meta', 'link', 'img', 'br', 'hr', 'input'):
                return
            if self.stack:
                self.stack.pop()

    checker = HierarchyChecker()
    checker.feed(content)

    # download-model-confirm-modal must NOT be inside voice-custom-provider-modal!
    download_parent_ids = [p[1] for p in checker.download_parents]
    assert "voice-custom-provider-modal" not in download_parent_ids
    assert "page-providers" not in download_parent_ids

    # delete-model-confirm-modal must NOT be inside voice-custom-provider-modal!
    delete_parent_ids = [p[1] for p in checker.delete_parents]
    assert "voice-custom-provider-modal" not in delete_parent_ids
    assert "page-providers" not in delete_parent_ids


