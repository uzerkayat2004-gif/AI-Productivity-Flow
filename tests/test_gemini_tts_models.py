"""Tests for Gemini 3.8 Flash TTS and Gemini 3.8 Flash-Lite TTS integration in Audio Flow."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow import storage as storage_module
from voice_flow.storage import StorageEngine
from voice_flow.tts_engine import TTSEngine


class TestGeminiTTSModels(unittest.TestCase):
    def setUp(self):
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        os.unlink(self._tmp_db.name)
        self._engine = StorageEngine(db_path=self._tmp_db.name)

        import voice_flow.tts_engine as tts_module
        p1 = patch.object(storage_module, "storage", self._engine)
        p1.start()
        self.addCleanup(p1.stop)

        self._orig_tts_storage = tts_module.storage
        tts_module.storage = self._engine
        self.addCleanup(setattr, tts_module, "storage", self._orig_tts_storage)

    def tearDown(self):
        try:
            os.unlink(self._tmp_db.name)
        except OSError:
            pass

    def test_gemini_38_models_seeded_in_catalog(self):
        """Verify that Gemini 3.8 Flash TTS and 3.8 Flash-Lite TTS are seeded into tts_models."""
        models = self._engine.get_tts_models_for_provider("gemini")
        model_ids = [m["model_id"] for m in models]

        # Verify Gemini 3.8 Flash TTS voices are present
        self.assertIn("gemini-3.8-flash-tts:Kore", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Puck", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Zephyr", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Orus", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Aoede", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Charon", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Fenrir", model_ids)
        self.assertIn("gemini-3.8-flash-tts:Leda", model_ids)

        # Verify Gemini 3.8 Flash-Lite TTS voices are present
        self.assertIn("gemini-3.8-flash-lite-tts:Kore", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Puck", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Zephyr", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Orus", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Aoede", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Charon", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Fenrir", model_ids)
        self.assertIn("gemini-3.8-flash-lite-tts:Leda", model_ids)

        # Verify labels indicate latest / fast & light
        flash_kore = next(m for m in models if m["model_id"] == "gemini-3.8-flash-tts:Kore")
        self.assertIn("Gemini 3.8 Flash TTS", flash_kore["display_name"])
        self.assertIn("Latest", flash_kore["display_name"])

        lite_kore = next(m for m in models if m["model_id"] == "gemini-3.8-flash-lite-tts:Kore")
        self.assertIn("Gemini 3.8 Flash-Lite TTS", lite_kore["display_name"])
        self.assertIn("Fast & Light", lite_kore["display_name"])

    def test_audio_policy_options_include_gemini_38_when_connected(self):
        """When Gemini API key is configured, policy options must include 3.8 models."""
        self._engine.add_audio_provider_connection(
            provider="gemini",
            name="My Gemini Key",
            api_key="AIzaSyFakeTestKey123",
            priority=1,
        )
        opts = self._engine.get_exec_audio_policy_options()
        grouped = {g["provider"]: g for g in opts.get("grouped_models", [])}
        self.assertIn("gemini", grouped)

        gemini_model_ids = [m["full_id"] for m in grouped["gemini"]["models"]]
        self.assertIn("gemini/gemini-3.8-flash-tts:Kore", gemini_model_ids)
        self.assertIn("gemini/gemini-3.8-flash-lite-tts:Zephyr", gemini_model_ids)

    def test_synthesize_gemini_38_flash_tts_request(self):
        """Verify _synthesize_gemini sends correct REST request for gemini-3.8-flash-tts."""
        self._engine.add_audio_provider_connection(
            provider="gemini",
            name="Gemini Key",
            api_key="AIzaSySecretApiKey",
            priority=1,
        )
        tts = TTSEngine()

        # Mock API response returning raw 24kHz PCM audio
        raw_pcm = b"\x00\x00" * 2400  # 0.1s of silence (16-bit 24kHz)
        import base64
        b64_audio = base64.b64encode(raw_pcm).decode("ascii")
        mock_response_body = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "audio/pcm;rate=24000",
                            "data": b64_audio,
                        }
                    }]
                }
            }]
        }

        captured_requests = []

        class MockHTTPResponse:
            def __init__(self, data: bytes):
                self._data = data
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return MockHTTPResponse(json.dumps(mock_response_body).encode("utf-8"))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            audio_result = tts._synthesize_gemini("Hello from Gemini TTS!", "gemini-3.8-flash-tts:Zephyr")

        self.assertIsNotNone(audio_result)
        self.assertEqual(len(captured_requests), 1)
        req = captured_requests[0]

        # Verify model in URL
        self.assertIn("gemini-3.8-flash-tts:generateContent", req.full_url)
        self.assertIn("key=AIzaSySecretApiKey", req.full_url)

        # Verify request body
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "Hello from Gemini TTS!")
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Zephyr")

        # Verify the returned audio is a valid WAV container wrapping the 24kHz PCM
        with wave.open(io.BytesIO(audio_result), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 24000)

    def test_synthesize_gemini_38_flash_lite_tts_request(self):
        """Verify _synthesize_gemini works with gemini-3.8-flash-lite-tts."""
        self._engine.add_audio_provider_connection(
            provider="gemini",
            name="Gemini Key",
            api_key="AIzaSySecretApiKey",
            priority=1,
        )
        tts = TTSEngine()

        # Mock response returning WAV audio
        fake_wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        import base64
        b64_audio = base64.b64encode(fake_wav_bytes).decode("ascii")
        mock_response_body = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": b64_audio,
                        }
                    }]
                }
            }]
        }

        captured_requests = []
        def fake_urlopen(req, timeout=None):
            captured_requests.append(req)
            return MagicMock(read=lambda: json.dumps(mock_response_body).encode("utf-8"), __enter__=lambda s: s, __exit__=lambda *a: None)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            audio_result = tts._synthesize_gemini("Speed test", "gemini-3.8-flash-lite-tts:Orus")

        self.assertIsNotNone(audio_result)
        self.assertEqual(audio_result, fake_wav_bytes)
        req = captured_requests[0]
        self.assertIn("gemini-3.8-flash-lite-tts:generateContent", req.full_url)
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Orus")

    def test_verify_model_probe_gemini_tts(self):
        """Verify API server verify_model_by_kind accurately probes Gemini TTS models."""
        from voice_flow.gui.api_server import VoiceFlowApiHandler
        import base64

        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        fake_audio_b64 = base64.b64encode(b"RIFF\x24\x00\x00\x00WAVEfakeaudio").decode("ascii")
        mock_body = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": fake_audio_b64,
                        }
                    }]
                }
            }]
        }

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_body).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            # 1. Explicit kind='tts'
            res = handler.verify_model_by_kind("gemini", key="AIzaSyTestKey", model_id="gemini-3.8-flash-tts:Kore", kind="tts")
            self.assertTrue(res["success"])
            self.assertIn("verified successfully", res["message"])

            # 2. Auto kind detection from model name containing ':Kore' or 'tts'
            res_auto = handler.verify_model_by_kind("gemini", key="AIzaSyTestKey", model_id="gemini-3.8-flash-lite-tts:Puck", kind="auto")
            self.assertTrue(res_auto["success"])
            self.assertIn("verified successfully", res_auto["message"])


if __name__ == "__main__":
    unittest.main()
