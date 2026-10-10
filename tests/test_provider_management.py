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

    @patch("urllib.request.urlopen")
    def test_validate_http_400_invalid_key_rejected(self, mock_urlopen):
        import urllib.error
        import io
        fp = io.BytesIO(b'{"error": {"message": "API_KEY_INVALID", "code": 400}}')
        mock_urlopen.side_effect = urllib.error.HTTPError("https://...", 400, "Bad Request", {}, fp)

        is_valid, err = validate_provider_key("gemini", "AIzaSyFakeInvalidKey")
        self.assertFalse(is_valid)
        self.assertIsNotNone(err)
        self.assertIn("invalid", err.lower())

    @patch("urllib.request.urlopen")
    def test_validate_http_401_unauthorized_rejected(self, mock_urlopen):
        import urllib.error
        import io
        fp = io.BytesIO(b'{"error": "Unauthorized"}')
        mock_urlopen.side_effect = urllib.error.HTTPError("https://...", 401, "Unauthorized", {}, fp)

        is_valid, err = validate_provider_key("openai", "sk-invalid-key")
        self.assertFalse(is_valid)
        self.assertIsNotNone(err)
        self.assertIn("invalid", err.lower())


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


class TestOAuthWorkflow(unittest.TestCase):
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

    def test_start_pkce_flow_antigravity(self):
        from voice_flow.video_flow_oauth import start_pkce_flow
        res = start_pkce_flow(self._engine, "antigravity", port=8991)
        self.assertIn("auth_url", res)
        self.assertIn("accounts.google.com", res["auth_url"])
        # Antigravity uses the reference client_secret flow: no PKCE challenge.
        self.assertNotIn("code_challenge=", res["auth_url"])
        self.assertIn("cloud-platform", res["auth_url"])
        self.assertIn("state=", res["auth_url"])
        self.assertEqual(res["provider"], "antigravity")

    @patch("voice_flow.video_flow_oauth._http_json")
    @patch("voice_flow.video_flow_oauth.load_code_assist_project", return_value="")
    def test_complete_pkce_flow_registers_oauth_connection(self, _mock_project, mock_http_json):
        from voice_flow.video_flow_oauth import start_pkce_flow, complete_pkce_flow
        # 1. Start flow to set pending state
        start_data = start_pkce_flow(self._engine, "antigravity", port=8991)
        state = start_data["state"]

        # 2. Mock token endpoint response
        mock_http_json.return_value = {
            "access_token": "ya29.mock_access_token_12345",
            "refresh_token": "1//mock_refresh_token_67890",
            "expires_in": 3600,
            "id_token": "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6Im5hZWVtLmtheWF0MjAwNEBnbWFpbC5jb20ifQ.signature",
        }

        # 3. Complete flow with authorization code
        res = complete_pkce_flow(self._engine, "antigravity", code="4/mock_auth_code_abc", state=state)
        self.assertTrue(res["success"])
        self.assertEqual(res["email"], "naeem.kayat2004@gmail.com")
        self.assertEqual(res["provider"], "antigravity")

        # 4. Verify stored in provider_connections
        conns = self._engine.get_provider_connections("antigravity")
        self.assertEqual(len(conns), 1)
        self.assertEqual(conns[0]["auth_type"], "oauth")
        self.assertEqual(conns[0]["email"], "naeem.kayat2004@gmail.com")
        self.assertEqual(conns[0]["is_active"], 1)


if __name__ == "__main__":
    unittest.main()
