import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from voice_flow.video_flow_providers import VideoFlowProviderService, PROVIDER_BY_ID, DEFAULT_MODELS
from voice_flow.gui.api_server import VoiceFlowApiHandler


class TestModelAndProviderTesting(unittest.TestCase):
    """Verify provider and model testing across Video, Voice, and Audio flow."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp_dir.name) / "test_vf.db")
        self.service = VideoFlowProviderService(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_gemini_seed_and_custom_models(self):
        """Confirm Gemini has verified primary route and can add modern flash models."""
        gemini_models = [m[1] for m in DEFAULT_MODELS if m[0] == "gemini"]
        self.assertIn("gemini-3.5-flash", gemini_models)
        m36 = self.service.add_model("gemini", "gemini/gemini-3.6-flash", "Gemini 3.6 Flash")
        self.assertEqual(m36["model_id"], "gemini-3.6-flash")
        m37 = self.service.add_model("gemini", "gemini/gemini-3.7-flash", "Gemini 3.7 Flash")
        self.assertEqual(m37["model_id"], "gemini-3.7-flash")

    def test_video_flow_providers_strip_only_prefix(self):
        """Multi-segment model IDs must not be truncated when adding custom models."""
        model = self.service.add_model("openrouter", "openrouter/poolside/laguna-s-2.1:free", "Laguna Free")
        self.assertEqual(model["model_id"], "poolside/laguna-s-2.1:free")
        self.assertEqual(model["full_id"], "openrouter/poolside/laguna-s-2.1:free")

        model_together = self.service.add_model("together", "together/meta-llama/Llama-3.3-70B-Instruct-Turbo")
        self.assertEqual(model_together["model_id"], "meta-llama/Llama-3.3-70B-Instruct-Turbo")

        model_nvidia = self.service.add_model("nvidia_nim", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
        self.assertEqual(model_nvidia["model_id"], "nvidia/nemotron-3-ultra-550b-a55b")

    def test_verify_model_by_kind_prefix_stripping(self):
        """verify_model_by_kind must only strip provider prefix if it matches."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        captured_requests = []

        def mock_urlopen(req, timeout=30):
            captured_requests.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "choices": [{
                    "message": {"content": "pong", "role": "assistant"},
                    "finish_reason": "stop"
                }]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Test openrouter multi-segment ID
            res = handler.verify_model_by_kind("openrouter", "sk-test", "openrouter/poolside/laguna-s-2.1:free")
            self.assertTrue(res["success"])
            last_req = captured_requests[-1]
            self.assertEqual(last_req.full_url, "https://openrouter.ai/api/v1/chat/completions")
            self.assertEqual(last_req.headers.get("Http-referer"), "http://localhost:8991")
            self.assertEqual(last_req.headers.get("X-title"), "Voice Flow")
            payload = json.loads(last_req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "poolside/laguna-s-2.1:free")

            # Test together multi-segment ID
            res = handler.verify_model_by_kind("together", "tok-test", "together/meta-llama/Llama-3.3-70B-Instruct-Turbo")
            self.assertTrue(res["success"])
            last_req = captured_requests[-1]
            self.assertEqual(last_req.full_url, "https://api.together.xyz/v1/chat/completions")
            payload = json.loads(last_req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "meta-llama/Llama-3.3-70B-Instruct-Turbo")

            # Test nvidia_nim multi-segment ID
            res = handler.verify_model_by_kind("nvidia_nim", "nvapi-test", "nvidia/nemotron-3-ultra-550b-a55b")
            self.assertTrue(res["success"])
            last_req = captured_requests[-1]
            self.assertEqual(last_req.full_url, "https://integrate.api.nvidia.com/v1/chat/completions")
            payload = json.loads(last_req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "nvidia/nemotron-3-ultra-550b-a55b")

    def test_verify_model_gemini_metadata_probe(self):
        """Gemini probe verifies model existence and generateContent method in response."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen(req, timeout=15):
            self.assertIn("generativelanguage.googleapis.com", req.full_url)
            self.assertIn("gemini-3.7-flash", req.full_url)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "name": "models/gemini-3.7-flash",
                "supportedGenerationMethods": ["generateContent", "countTokens"]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("gemini", "AIzaSyFakeKey", "gemini/gemini-3.7-flash")
            self.assertTrue(res["success"])
            self.assertIsNone(res.get("error"))

    def test_verify_model_reasoning_tokens_support(self):
        """Models outputting thinking/reasoning without standard content must succeed."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen(req, timeout=30):
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "choices": [{
                    "message": {"content": "", "reasoning_content": "Pondering the query...", "role": "assistant"},
                    "finish_reason": "stop"
                }]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("deepseek", "sk-deepseek", "deepseek-reasoner")
            self.assertTrue(res["success"])

    def test_verify_model_by_kind_error_diagnostics(self):
        """Ensure HTTPError bodies are parsed to retain provider-specific error details."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        err_body = json.dumps({
            "error": {
                "message": "Resource has been exhausted (e.g. check quota).",
                "code": 429
            }
        }).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="https://api.test",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=BytesIO(err_body)
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = handler.verify_model_by_kind("groq", "gsk-key", "llama-3.3-70b-versatile")
            self.assertFalse(res["success"])
            self.assertIn("Quota exhausted", res["error"])
            self.assertIn("Resource has been exhausted", res["error"])

    def test_video_flow_test_connection_decryption(self):
        """test_connection must decrypt secret via resolve_connection_secret."""
        created = self.service.add_connection("gemini", name="Test Gemini", secret="AIzaSyPlainTextTestKey")
        conn_id = created["id"]

        def mock_urlopen(req, timeout=30):
            self.assertIn("AIzaSyPlainTextTestKey", req.full_url)
            self.assertEqual(timeout, 30)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({"models": [{"name": "models/gemini-3.6-flash"}]}).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = self.service.test_connection(conn_id)
            self.assertTrue(res["success"])
            self.assertIn(res["status"], ("connected", "active"))

    def test_oauth_connection_healthy_for_claude_cursor_kiro_copilot(self):
        """OAuth provider connections report active when healthy."""
        created = self.service.add_connection("claude_code", name="Claude CLI", secret="claude-cli-token")
        conn_id = created["id"]

        with patch.object(self.service, "connection_is_healthy", return_value=True):
            res = self.service.test_connection(conn_id)
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "active")

    def test_gemini_fallback_probe_on_404(self):
        """When GET /models/{model} returns 404, fallback to live generateContent probe."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        call_count = 0

        def mock_urlopen(req, timeout=30):
            nonlocal call_count
            call_count += 1
            if ":generateContent" in req.full_url:
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = json.dumps({
                    "candidates": [{"content": {"parts": [{"text": "Hello!"}]}}]
                }).encode("utf-8")
                resp.__enter__.return_value = resp
                return resp
            else:
                # First call is GET /models/{model}
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=404,
                    msg="Not Found",
                    hdrs={},
                    fp=BytesIO(b'{"error": {"message": "models/gemini-experimental not found"}}')
                )

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("gemini", "AIzaSyFakeKey", "gemini-experimental")
            self.assertTrue(res["success"])
            self.assertEqual(call_count, 2)

    def test_openai_reasoning_model_retry_on_max_tokens_error(self):
        """When OpenAI returns 400 for max_tokens, auto-retry with max_completion_tokens."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        attempts = []

        def mock_urlopen(req, timeout=30):
            payload = json.loads(req.data.decode("utf-8"))
            attempts.append(payload)
            if "max_tokens" in payload:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=400,
                    msg="Bad Request",
                    hdrs={},
                    fp=BytesIO(b'{"error": {"message": "Unsupported parameter: max_tokens is not supported with this model. Use max_completion_tokens instead."}}')
                )
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "choices": [{
                    "message": {"content": "42", "role": "assistant"},
                    "finish_reason": "stop"
                }]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Pass model that defaults to max_tokens, then provider rejects and prompts max_completion_tokens
            res = handler.verify_model_by_kind("groq", "gsk-key", "custom-llm")
            self.assertTrue(res["success"])
            self.assertEqual(len(attempts), 2)
            self.assertIn("max_completion_tokens", attempts[-1])

    def test_openai_tts_model_vs_voice_probe(self):
        """OpenAI TTS verification distinguishes between model IDs and voice names."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        captured = []

        def mock_urlopen(req, timeout=20):
            payload = json.loads(req.data.decode("utf-8"))
            captured.append(payload)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = b"RIFFFAKEAUDIO"
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Test with model tts-1-hd
            res = handler.verify_model_by_kind("openai", "sk-fake", "tts-1-hd", kind="tts")
            self.assertTrue(res["success"])
            self.assertEqual(captured[-1]["model"], "tts-1-hd")
            self.assertEqual(captured[-1]["voice"], "alloy")

            # Test with voice name 'shimmer'
            res = handler.verify_model_by_kind("openai", "sk-fake", "shimmer", kind="tts")
            self.assertTrue(res["success"])
            self.assertEqual(captured[-1]["model"], "tts-1")
            self.assertEqual(captured[-1]["voice"], "shimmer")

    def test_anthropic_model_probe(self):
        """Anthropic model probe sends proper messages payload and headers."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        captured_reqs = []

        def mock_urlopen(req, timeout=30):
            captured_reqs.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "content": [{"type": "text", "text": "Hello Anthropic"}]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("anthropic", "sk-ant-fake", "claude-3-7-sonnet-20250219")
            self.assertTrue(res["success"])
            req = captured_reqs[-1]
            self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
            self.assertEqual(req.headers.get("X-api-key"), "sk-ant-fake")
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "claude-3-7-sonnet-20250219")


    def test_verify_provider_model_gemini_fallback(self):
        """verify_provider_model Gemini fallback probe works on 404."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen(req, timeout=30):
            if ":generateContent" in req.full_url:
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = json.dumps({"candidates": []}).encode("utf-8")
                resp.__enter__.return_value = resp
                return resp
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=404,
                msg="Not Found",
                hdrs={},
                fp=BytesIO(b'{"error": {"message": "Model not found"}}')
            )

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_provider_model("gemini", "AIzaFake", "gemini-2.5-flash-preview")
            self.assertTrue(res["success"])

    def test_verify_provider_model_openai_reasoning(self):
        """verify_provider_model uses max_completion_tokens for reasoning models."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        captured = []

        def mock_urlopen(req, timeout=20):
            payload = json.loads(req.data.decode("utf-8"))
            captured.append(payload)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_provider_model("openai", "sk-fake", "o1-mini")
            self.assertTrue(res["success"])
            self.assertIn("max_completion_tokens", captured[-1])
            self.assertNotIn("max_tokens", captured[-1])

    def test_verify_model_by_kind_vertex_ai_endpoints(self):
        """Vertex AI must probe aiplatform.googleapis.com models endpoint, supporting both API keys and OAuth tokens."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        captured = []

        def mock_urlopen(req, timeout=15):
            captured.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({"name": "publishers/google/models/gemini-2.5-flash"}).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Test with standard API key
            res1 = handler.verify_model_by_kind("vertex_ai", "AIzaSyFakeKey", "vx/gemini-2.5-flash")
            self.assertTrue(res1["success"])
            self.assertIn("aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash?key=AIzaSyFakeKey", captured[-1].full_url)

            # Test with OAuth bearer token
            res2 = handler.verify_model_by_kind("vertex_ai", "ya29.fake-oauth-token", "publishers/google/models/gemini-2.5-flash")
            self.assertTrue(res2["success"])
            self.assertIn("aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash", captured[-1].full_url)
            self.assertNotIn("?key=", captured[-1].full_url)
            self.assertEqual(captured[-1].headers.get("Authorization"), "Bearer ya29.fake-oauth-token")

    def test_verify_model_by_kind_openrouter_preserves_multisegment_catalog_id(self):
        """OpenRouter must preserve upstream provider/org prefix like openai/gpt-4o."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        captured = []

        def mock_urlopen(req, timeout=30):
            captured.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "pong", "role": "assistant"}}]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("openrouter", "sk-or-fake", "openai/gpt-4o")
            self.assertTrue(res["success"])
            payload = json.loads(captured[-1].data.decode("utf-8"))
            self.assertEqual(payload["model"], "openai/gpt-4o")

            # With leading openrouter/ prefix
            res2 = handler.verify_model_by_kind("openrouter", "sk-or-fake", "openrouter/anthropic/claude-3.5-sonnet")
            self.assertTrue(res2["success"])
            payload2 = json.loads(captured[-1].data.decode("utf-8"))
            self.assertEqual(payload2["model"], "anthropic/claude-3.5-sonnet")

    def test_openai_reasoning_model_retry_on_quoted_parameter_error(self):
        """Auto-retry on 400 when error message contains quoted 'max_tokens' or alternative phrasing."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        attempts = []

        def mock_urlopen(req, timeout=30):
            payload = json.loads(req.data.decode("utf-8"))
            attempts.append(payload)
            if "max_tokens" in payload:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=400,
                    msg="Bad Request",
                    hdrs={},
                    fp=BytesIO(b'{"error": {"message": "Unsupported parameter: \'max_tokens\' is not supported with this model. Use \'max_completion_tokens\' instead."}}')
                )
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "ok", "role": "assistant"}}]
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("groq", "gsk-key", "gpt-o3-test")
            self.assertTrue(res["success"])
            self.assertEqual(len(attempts), 2)
            self.assertIn("max_completion_tokens", attempts[-1])

    def test_antigravity_prefix_stripping_and_custom_model_add(self):
        """Antigravity custom model add must cleanly strip antigravity/, agy/, models/ and chained prefixes."""
        m1 = self.service.add_model("antigravity", "antigravity/gemini-3.8-flash", "Gemini 3.8 Flash")
        self.assertEqual(m1["model_id"], "gemini-3.8-flash")
        self.assertEqual(m1["full_id"], "antigravity/gemini-3.8-flash")
        self.assertIn("vision", m1["capabilities"])
        self.assertIn("reasoning", m1["capabilities"])

        m2 = self.service.add_model("antigravity", "agy/gemini-3.8-flash", "Gemini 3.8 Flash")
        self.assertEqual(m2["model_id"], "gemini-3.8-flash")

        m3 = self.service.add_model("antigravity", "antigravity/models/gemini-3.8-flash")
        self.assertEqual(m3["model_id"], "gemini-3.8-flash")
        self.assertEqual(m3["full_id"], "antigravity/gemini-3.8-flash")

        m4 = self.service.add_model("antigravity", "agy/antigravity/models/gemini-3.8-flash")
        self.assertEqual(m4["model_id"], "gemini-3.8-flash")

    def test_verify_model_by_kind_antigravity_flash_38_fallback(self):
        """When gemini-3.8-flash is not yet in fetchAvailableModels, fall back to family quota."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        captured = []

        def mock_urlopen(req, timeout=12):
            captured.append(req)
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "models": {
                    "gemini-2.5-flash": {"quotaInfo": {"remainingFraction": 0.85}},
                    "claude-3-5-sonnet": {"quotaInfo": {"remainingFraction": 1.0}}
                }
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "antigravity/gemini-3.8-flash")
            self.assertTrue(res["success"])
            self.assertIsNone(res.get("error"))
            self.assertEqual(captured[-1].full_url, "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels")
            self.assertEqual(captured[-1].headers.get("Authorization"), "Bearer ya29.fake-token")

            # Also verify agy/ prefix
            res2 = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "agy/gemini-3.8-flash")
            self.assertTrue(res2["success"])

            # Also verify models/ prefix
            res3 = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "antigravity/models/gemini-3.8-flash")
            self.assertTrue(res3["success"])

    def test_verify_model_by_kind_antigravity_quota_exhaustion(self):
        """When family quota is 0.0, return quota exhausted error."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen(req, timeout=12):
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "models": {
                    "gemini-2.5-flash": {"quotaInfo": {"remainingFraction": 0.0}},
                    "gemini-2.5-pro": {"quotaInfo": {"remainingFraction": 0.0}}
                }
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "gemini-3.8-flash")
            self.assertFalse(res["success"])
            self.assertIn("quota exhausted", res.get("error", "").lower())

    def test_verify_model_by_kind_antigravity_refresh_on_401(self):
        """When access token is expired (401), verify_model_by_kind refreshes and retries."""
        import urllib.error
        from io import BytesIO
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)
        call_count = 0

        def mock_urlopen(req, timeout=12):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=401,
                    msg="Unauthorized",
                    hdrs={},
                    fp=BytesIO(b'{"error": "invalid_token"}')
                )
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "models": {
                    "gemini-2.5-flash": {"quotaInfo": {"remainingFraction": 0.9}}
                }
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        mock_conn = {
            "id": 99,
            "provider": "antigravity",
            "is_active": True,
            "secret": "enc-old-token",
            "refresh_token": "rt-12345",
            "metadata": {"project_id": "proj-xyz"}
        }

        with patch("urllib.request.urlopen", side_effect=mock_urlopen), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.list_connections", return_value=[mock_conn]), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.get_connection", return_value=mock_conn), \
             patch("voice_flow.video_flow_oauth.decrypt_token", return_value="old-token"), \
             patch("voice_flow.gui.api_server._http_json", return_value={"access_token": "new-token", "expires_in": 3600}), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.update_connection") as mock_update:
            res = handler.verify_model_by_kind("antigravity", "", "gemini-3.8-flash")
            self.assertTrue(res["success"])
            self.assertEqual(call_count, 2)
            mock_update.assert_called_once()

    def test_antigravity_rejects_nonexistent_japanese_model(self):
        """Antigravity must reject non-existent models like japanese-3.8 despite valid quota on other models."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen(req, timeout=12):
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "models": {
                    "gemini-2.5-flash": {"quotaInfo": {"remainingFraction": 0.95}},
                    "gemini-2.5-pro": {"quotaInfo": {"remainingFraction": 0.80}}
                }
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "japanese-3.8")
            self.assertFalse(res["success"])
            self.assertFalse(res["ok"])
            self.assertIn("not available in your Antigravity subscription", res.get("error", ""))

            # Also test prefix stripped version
            res2 = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "antigravity/japanese-3.8")
            self.assertFalse(res2["success"])
            self.assertFalse(res2["ok"])
            self.assertIn("not available in your Antigravity subscription", res2.get("error", ""))

    def test_verify_model_by_kind_returns_diagnostics_and_latency(self):
        """verify_model_by_kind returns standardized success, ok, latency_ms, and message/error keys."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        def mock_urlopen_antigravity(req, timeout=12):
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = json.dumps({
                "models": {
                    "gemini-2.5-flash": {"quotaInfo": {"remainingFraction": 0.85}}
                }
            }).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen_antigravity):
            res = handler.verify_model_by_kind("antigravity", "ya29.fake-token", "gemini-2.5-flash")
            self.assertTrue(res["success"])
            self.assertTrue(res["ok"])
            self.assertIsInstance(res["latency_ms"], int)
            self.assertGreaterEqual(res["latency_ms"], 1)
            self.assertIn("quota remaining", res.get("message", "").lower())
            self.assertIsNone(res.get("error"))

        res_fail = handler.verify_model_by_kind("groq", "gsk-key", "")
        self.assertFalse(res_fail["success"])
        self.assertFalse(res_fail["ok"])
        self.assertIsInstance(res_fail["latency_ms"], int)
        self.assertEqual(res_fail["error"], "Enter a model ID first.")

    def test_verify_model_by_kind_openai_codex_branches(self):
        """verify_model_by_kind handles openai_codex with valid/invalid models and quota calculation."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        # Case 1: No active connection
        with patch("voice_flow.video_flow_providers.video_flow_provider_service.list_connections", return_value=[]), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.start_oauth", return_value={"imported": False}):
            res_no_conn = handler.verify_model_by_kind("openai_codex", "", "gpt-5.4")
            self.assertFalse(res_no_conn["success"])
            self.assertFalse(res_no_conn["ok"])
            self.assertIn("No active ChatGPT account connected", res_no_conn["error"])

        # Case 2: Active connection with valid model
        mock_conn = {"id": 1, "provider": "openai_codex", "is_active": True, "secret": "mock-tok"}
        mock_usage = {
            "plan_type": "plus",
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 25.0}
            }
        }
        mock_models = {"models": [{"slug": "gpt-5.4", "visibility": "show"}]}

        def mock_urlopen_codex(req, timeout=10):
            resp = MagicMock()
            resp.status = 200
            if "models" in req.full_url:
                resp.read.return_value = json.dumps(mock_models).encode("utf-8")
            else:
                resp.read.return_value = json.dumps(mock_usage).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        with patch("voice_flow.video_flow_providers.video_flow_provider_service.list_connections", return_value=[mock_conn]), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.pick_best_connection", return_value=mock_conn), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.get_connection", return_value=mock_conn), \
             patch("voice_flow.video_flow_providers.video_flow_provider_service.resolve_connection_secret", return_value="dec-tok"), \
             patch("urllib.request.urlopen", side_effect=mock_urlopen_codex):
            res_valid = handler.verify_model_by_kind("openai_codex", "", "gpt-5.4")
            self.assertTrue(res_valid["success"])
            self.assertTrue(res_valid["ok"])
            self.assertEqual(res_valid["remaining_pct"], 75.0)
            self.assertIn("ChatGPT Plus subscription active", res_valid["message"])

            # Case 3: Invalid model not in available_models or codex_supported_models
            res_invalid = handler.verify_model_by_kind("openai_codex", "", "japanese-3.8")
            self.assertFalse(res_invalid["success"])
            self.assertFalse(res_invalid["ok"])
            self.assertIn("is not available in the ChatGPT Codex distribution", res_invalid["error"])

    def test_verify_model_by_kind_oauth_cli_providers(self):
        """verify_model_by_kind checks session health for claude_code, cursor, kiro, copilot."""
        handler = VoiceFlowApiHandler.__new__(VoiceFlowApiHandler)

        for provider in ("claude_code", "cursor", "kiro", "copilot"):
            mock_conn = {"id": 1, "provider": provider, "is_active": True}

            # Healthy session
            with patch("voice_flow.video_flow_providers.video_flow_provider_service.list_connections", return_value=[mock_conn]), \
                 patch("voice_flow.video_flow_providers.video_flow_provider_service.pick_best_connection", return_value=mock_conn), \
                 patch("voice_flow.video_flow_providers.video_flow_provider_service.connection_is_healthy", return_value=True):
                res_ok = handler.verify_model_by_kind(provider, "", "claude-3-7-sonnet")
                self.assertTrue(res_ok["success"])
                self.assertTrue(res_ok["ok"])
                self.assertIn("subscription active", res_ok["message"])

            # Expired session
            with patch("voice_flow.video_flow_providers.video_flow_provider_service.list_connections", return_value=[mock_conn]), \
                 patch("voice_flow.video_flow_providers.video_flow_provider_service.pick_best_connection", return_value=mock_conn), \
                 patch("voice_flow.video_flow_providers.video_flow_provider_service.connection_is_healthy", return_value=False):
                res_exp = handler.verify_model_by_kind(provider, "", "claude-3-7-sonnet")
                self.assertFalse(res_exp["success"])
                self.assertFalse(res_exp["ok"])
                self.assertIn("session is expired or invalid", res_exp["error"])


if __name__ == "__main__":
    unittest.main()

