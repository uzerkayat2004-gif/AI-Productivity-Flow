"""Unit and integration tests for Cloud STT Model Acceleration.

Tests verify:
- Connection pooling via requests.Session & HTTPAdapter
- Fast in-memory WAV generation without disk I/O
- Fast in-memory FLAC piping without disk I/O
- Pre-warming / speculative TLS handshake logic
- Header optimization (Keep-Alive, Accept, temperature=0.0)
- Backward compatibility with legacy monkeypatched urlopen
- Correct error mapping to STTError with HTTP status preservation
"""
import io
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import requests

from voice_flow import stt_engines
from voice_flow.stt_engines import (
    STTError,
    _ADAPTERS,
    _get_stt_session,
    _groq,
    _openai,
    _deepgram,
    _gemini,
    _elevenlabs,
    _nvidia,
    _send,
    _to_flac_bytes,
    _to_wav_bytes,
    prewarm_cloud_stt,
    transcribe_cloud,
)


class TestCloudSTTAcceleration(unittest.TestCase):
    def setUp(self):
        # Reset pre-warm timestamps between tests
        stt_engines._PREWARMED_TIMESTAMPS.clear()

    def test_session_uses_connection_pool_and_keep_alive(self):
        session = _get_stt_session()
        self.assertIsInstance(session, requests.Session)
        adapter_https = session.adapters.get("https://")
        self.assertIsNotNone(adapter_https)
        self.assertIsInstance(adapter_https, requests.adapters.HTTPAdapter)
        self.assertGreaterEqual(adapter_https._pool_connections, 10)
        self.assertGreaterEqual(adapter_https._pool_maxsize, 20)
        self.assertEqual(session.headers.get("Connection"), "keep-alive")

    def test_to_wav_bytes_creates_canonical_in_memory_wav(self):
        # 0.5s of 16kHz audio = 8000 samples
        audio = np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 8000)).astype(np.float32)
        wav_bytes = _to_wav_bytes(audio, sample_rate=16000)

        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])
        self.assertIn(b"fmt ", wav_bytes[:24])
        self.assertIn(b"data", wav_bytes[:44])
        # Verify with standard wave module
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), 8000)

    def test_to_wav_bytes_returns_existing_wav_directly(self):
        existing_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        result = _to_wav_bytes(existing_wav)
        self.assertEqual(result, existing_wav)

    def test_prewarm_cloud_stt_triggers_head_request_for_provider(self):
        session = _get_stt_session()
        with patch.object(session, "head") as mock_head:
            prewarm_cloud_stt("groq/whisper-large-v3-turbo")
            # Wait briefly for daemon thread
            time.sleep(0.15)
            mock_head.assert_called_once()
            called_url = mock_head.call_args[0][0]
            self.assertEqual(called_url, "https://api.groq.com")

    def test_prewarm_cloud_stt_debounces_within_keepalive_window(self):
        session = _get_stt_session()
        with patch.object(session, "head") as mock_head:
            prewarm_cloud_stt("openai/whisper-1")
            time.sleep(0.15)
            # Immediate second call should be debounced
            prewarm_cloud_stt("openai/whisper-1")
            time.sleep(0.15)
            self.assertEqual(mock_head.call_count, 1)

    def test_send_fast_path_uses_session_request(self):
        session = _get_stt_session()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"text": "fast cloud transcription"}'

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=b"dummy-audio-data",
            headers={"Authorization": "Bearer test-key"},
            method="POST",
        )

        with patch.object(session, "request", return_value=mock_resp) as mock_req:
            output = _send(req)
            self.assertEqual(output, b'{"text": "fast cloud transcription"}')
            mock_req.assert_called_once()
            _, kwargs = mock_req.call_args
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(kwargs["url"], "https://api.groq.com/openai/v1/audio/transcriptions")
            self.assertEqual(kwargs["headers"].get("Connection"), "keep-alive")

    def test_send_maps_http_error_to_stterror_with_status_code(self):
        session = _get_stt_session()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid API Key provided"

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=b"data",
            method="POST",
        )

        with patch.object(session, "request", return_value=mock_resp):
            with self.assertRaises(STTError) as ctx:
                _send(req)
            self.assertIn("HTTP 401: Invalid API Key provided", str(ctx.exception))

    def test_send_respects_monkeypatched_urlopen(self):
        """When legacy test suites monkeypatch urllib.request.urlopen, _send honors it."""
        mock_urlopen = MagicMock()
        mock_context = MagicMock()
        mock_context.read.return_value = b'{"text": "legacy mocked response"}'
        mock_urlopen.return_value.__enter__.return_value = mock_context

        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=b"data")

        with patch("urllib.request.urlopen", mock_urlopen):
            output = _send(req)
            self.assertEqual(output, b'{"text": "legacy mocked response"}')
            mock_urlopen.assert_called_once()

    def test_groq_adapter_includes_temperature_zero_and_keep_alive(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return b'{"text": "groq success"}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            text = _groq(b"WAV", "fake-key", "whisper-large-v3-turbo")
            self.assertEqual(text, "groq success")
            req = captured_req["req"]
            self.assertEqual(req.headers.get("Connection"), "keep-alive")
            self.assertEqual(req.headers.get("Accept"), "application/json")
            body_text = req.data.decode("utf-8", errors="ignore")
            self.assertIn('name="temperature"', body_text)
            self.assertIn('0.0', body_text)

    def test_openai_adapter_includes_temperature_zero_and_keep_alive(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return b'{"text": "openai success"}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            text = _openai(b"WAV", "fake-key", "whisper-1")
            self.assertEqual(text, "openai success")
            req = captured_req["req"]
            self.assertEqual(req.headers.get("Connection"), "keep-alive")
            self.assertEqual(req.headers.get("Accept"), "application/json")
            body_text = req.data.decode("utf-8", errors="ignore")
            self.assertIn('name="temperature"', body_text)

    def test_deepgram_adapter_includes_keep_alive(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return b'{"results": {"channels": [{"alternatives": [{"transcript": "deepgram success"}]}]}}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            text = _deepgram(b"WAV", "fake-key", "nova-3")
            self.assertEqual(text, "deepgram success")
            req = captured_req["req"]
            self.assertEqual(req.headers.get("Connection"), "keep-alive")
            self.assertEqual(req.headers.get("Accept"), "application/json")

    def test_gemini_adapter_includes_keep_alive(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return b'{"candidates": [{"content": {"parts": [{"text": "gemini success"}]}}]}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            text = _gemini(b"WAV", "fake-key", "gemini-2.5-flash")
            self.assertEqual(text, "gemini success")
            req = captured_req["req"]
            self.assertEqual(req.headers.get("Connection"), "keep-alive")
            self.assertEqual(req.headers.get("Accept"), "application/json")

    def test_gemini_stt_uses_minimum_supported_thinking_and_ignores_thought_parts(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"thought": True, "text": "internal reasoning"},
                {"text": "exact transcript"},
            ]}}]}).encode()

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            self.assertEqual(_gemini(b"WAV", "fake-key", "gemini-3.7-flash"), "exact transcript")

        body = json.loads(captured_req["req"].data)
        self.assertEqual(body["generationConfig"], {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingLevel": "low"},
        })

    def test_gemini_stt_uses_flash_budget_zero_and_rejects_truncated_output(self):
        captured_req = {}

        def mock_send(req, deadline=None):
            captured_req["req"] = req
            return b'{"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "missing ending"}]}}]}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            self.assertEqual(_gemini(b"WAV", "fake-key", "gemini-2.5-flash"), "")

        body = json.loads(captured_req["req"].data)
        self.assertEqual(body["generationConfig"], {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0},
        })

    def test_gemini_stt_thinking_levels_do_not_touch_pro_or_image_models(self):
        config = stt_engines._gemini_stt_generation_config
        self.assertEqual(config("gemini-3.5-flash")["thinkingConfig"], {"thinkingLevel": "minimal"})
        self.assertEqual(config("gemini-3.6-flash")["thinkingConfig"], {"thinkingLevel": "minimal"})
        self.assertEqual(config("gemini-3.8-flash")["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertIsNone(config("gemini-3.1-pro-preview"))
        self.assertIsNone(config("gemini-3.5-flash-image"))

    def test_send_retries_and_recovers_on_dropped_pooled_connection(self):
        session = _get_stt_session()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"text": "recovered after reconnect"}'

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=b"data",
            method="POST",
        )

        # Attempt 1: socket drop / ConnectionError; Attempt 2: success
        with patch.object(
            session,
            "request",
            side_effect=[
                requests.exceptions.ConnectionError("Remote end closed connection without response"),
                mock_resp,
            ],
        ) as mock_req:
            output = _send(req)
            self.assertEqual(output, b'{"text": "recovered after reconnect"}')
            self.assertEqual(mock_req.call_count, 2)

    def test_groq_and_openai_include_language_en(self):
        captured_reqs = []

        def mock_send(req, deadline=None):
            captured_reqs.append(req)
            return b'{"text": "success"}'

        with patch("voice_flow.stt_engines._send", side_effect=mock_send):
            _groq(b"WAV", "fake-key", "whisper-large-v3-turbo")
            _openai(b"WAV", "fake-key", "whisper-1")

        self.assertEqual(len(captured_reqs), 2)
        groq_body = captured_reqs[0].data.decode("utf-8", errors="ignore")
        openai_body = captured_reqs[1].data.decode("utf-8", errors="ignore")
        self.assertIn('name="language"', groq_body)
        self.assertIn('en', groq_body)
        self.assertIn('name="language"', openai_body)
        self.assertIn('en', openai_body)

    def test_prewarm_cloud_stt_force_bypasses_debounce(self):
        session = _get_stt_session()
        with patch.object(session, "head") as mock_head:
            prewarm_cloud_stt("groq/whisper-large-v3-turbo")
            time.sleep(0.15)
            # Second call with force=True should NOT be debounced
            prewarm_cloud_stt("groq/whisper-large-v3-turbo", force=True)
            time.sleep(0.15)
            self.assertEqual(mock_head.call_count, 2)

    def test_cloud_session_tunes_audio_chunk_thresholds(self):
        from voice_flow.audio import AudioRecorder
        from voice_flow.main import VoiceFlowApp

        app = object.__new__(VoiceFlowApp)
        app.audio = AudioRecorder()
        app._state_lock = threading.Lock()
        app._cancelled_session_ids = set()
        app._streaming_stt_enabled = lambda: False
        app._set_hotkeys_recording_state = lambda _: None

        session = MagicMock()
        session.stt_model_ref = "groq/whisper-large-v3-turbo"

        with patch("voice_flow.stt_engines.prewarm_cloud_stt") as mock_prewarm:
            app._start_stream_for_session(session)
            mock_prewarm.assert_called_with("groq/whisper-large-v3-turbo", force=True)
            self.assertEqual(app.audio.split_silence_seconds, 0.28)
            self.assertEqual(app.audio.max_chunk_seconds, 4.0)

        app._reset_to_idle()
        self.assertEqual(app.audio.split_silence_seconds, 0.35)
        self.assertEqual(app.audio.max_chunk_seconds, 8.0)


if __name__ == "__main__":
    unittest.main()
