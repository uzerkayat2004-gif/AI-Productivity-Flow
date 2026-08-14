"""Tests for Provider Registry, Schema, Validation Probes, and Failover Routing."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow import storage as storage_module
from voice_flow.provider_registry import (
    PROVIDERS_REGISTRY,
    get_all_provider_specs,
    get_provider_spec,
)
from voice_flow.provider_validation import validate_provider_key
from voice_flow.storage import StorageEngine


class TestProviderRegistry(unittest.TestCase):
    def test_registry_specs(self):
        tokenrouter = get_provider_spec("tokenrouter")
        self.assertIsNotNone(tokenrouter)
        self.assertEqual(tokenrouter.id, "tokenrouter")
        self.assertEqual(tokenrouter.category, "apikey")
        self.assertEqual(tokenrouter.transport.format, "openai")

        all_specs = get_all_provider_specs()
        self.assertGreaterEqual(len(all_specs), 8)
        provider_ids = {s.id for s in all_specs}
        self.assertIn("openai", provider_ids)
        self.assertIn("deepseek", provider_ids)
        self.assertIn("tokenrouter", provider_ids)

    def test_to_dict_schema(self):
        spec = get_provider_spec("openai")
        d = spec.to_dict()
        self.assertEqual(d["id"], "openai")
        self.assertIn("display", d)
        self.assertIn("transport", d)
        self.assertEqual(d["category"], "apikey")


class TestProviderValidation(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_validate_success_200(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        is_valid, err = validate_provider_key("openai", "sk-test-valid-key")
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_validate_empty_key(self):
        is_valid, err = validate_provider_key("openai", "   ")
        self.assertFalse(is_valid)
        self.assertIn("empty", err.lower())


class TestStorageConnections(unittest.TestCase):
    def setUp(self):
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        os.unlink(self._tmp_db.name)
        self._engine = StorageEngine(db_path=self._tmp_db.name)
        p = patch.object(storage_module, "storage", self._engine)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        try:
            os.unlink(self._tmp_db.name)
        except OSError:
            pass

    def test_add_and_query_connection(self):
        conn = self._engine.add_provider_connection(
            provider="tokenrouter",
            name="Primary TokenRouter Key",
            api_key="tr-1234567890",
            priority=1,
            base_url="https://api.tokenrouter.com/v1/chat/completions",
        )
        self.assertIsNotNone(conn.get("id"))
        self.assertEqual(conn["provider"], "tokenrouter")
        self.assertEqual(conn["authType"], "apikey")
        self.assertEqual(conn["name"], "Primary TokenRouter Key")

        all_conns = self._engine.get_all_provider_connections()
        self.assertIn("tokenrouter", all_conns)
        target_conn = next(c for c in all_conns["tokenrouter"] if c["id"] == conn["id"])
        self.assertEqual(target_conn["name"], "Primary TokenRouter Key")


if __name__ == "__main__":
    unittest.main()
