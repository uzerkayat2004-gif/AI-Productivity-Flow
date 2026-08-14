"""Tests for Audio Flow Provider Connection Schema, Real-time Validation, and Failover."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow import storage as storage_module
from voice_flow.storage import StorageEngine
from voice_flow.tts_engine import TTSEngine


class TestAudioProviderManagement(unittest.TestCase):
    def setUp(self):
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        os.unlink(self._tmp_db.name)
        self._engine = StorageEngine(db_path=self._tmp_db.name)
        # Point both storage bindings at the temp engine so no production data is touched.
        import voice_flow.tts_engine as tts_module

        p1 = patch.object(storage_module, "storage", self._engine)
        p1.start()
        self.addCleanup(p1.stop)
        tts_module.storage = self._engine

    def tearDown(self):
        try:
            os.unlink(self._tmp_db.name)
        except OSError:
            pass

    def test_audio_provider_connection_schema(self):
        conn = self._engine.add_audio_provider_connection(
            provider="elevenlabs",
            name="Primary ElevenLabs Key",
            api_key="xi-test-12345",
            priority=0,
            base_url="https://api.elevenlabs.io",
        )
        self.assertIsNotNone(conn.get("id"))
        self.assertEqual(conn["provider"], "elevenlabs")
        self.assertEqual(conn["authType"], "apikey")
        self.assertEqual(conn["name"], "Primary ElevenLabs Key")
        self.assertEqual(conn["is_valid"], 1)

    def test_audio_provider_validation_update(self):
        conn = self._engine.add_audio_provider_connection(
            provider="gemini",
            name="Gemini TTS Key",
            api_key="gemini-test-key",
            priority=1,
        )
        cid = conn["id"]

        # Mark invalid with error
        self._engine.update_audio_provider_connection_validation(cid, False, "HTTP 401: Unauthorized")
        all_conns = self._engine.get_all_audio_provider_connections()
        target = next(c for c in all_conns["gemini"] if c["id"] == cid)
        self.assertEqual(target["is_valid"], 0)
        self.assertEqual(target["last_error"], "HTTP 401: Unauthorized")

        # Mark valid again
        self._engine.update_audio_provider_connection_validation(cid, True, None)
        all_conns = self._engine.get_all_audio_provider_connections()
        target = next(c for c in all_conns["gemini"] if c["id"] == cid)
        self.assertEqual(target["is_valid"], 1)
        self.assertEqual(target["last_tested_status"], "Connected")

    def test_tts_engine_get_active_keys(self):
        with patch("voice_flow.tts_engine.storage") as mock_storage:
            mock_storage.get_audio_provider_connections.return_value = [
                {"id": 1, "api_key": "revoked_key", "is_active": 1, "is_valid": 0},
                {"id": 2, "api_key": "good_key", "is_active": 1, "is_valid": 1},
            ]
            tts = TTSEngine()
            active = tts._get_active_keys_for_provider("elevenlabs")
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["api_key"], "good_key")


if __name__ == "__main__":
    unittest.main()