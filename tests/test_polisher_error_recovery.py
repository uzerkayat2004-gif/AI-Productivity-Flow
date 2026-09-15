import unittest
from unittest.mock import patch
import time
import os
import sys
import urllib.error

# Ensure src directory is in sys.path
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.polisher import TextPolisher
from voice_flow.storage import storage


class TestPolisherErrorRecovery(unittest.TestCase):
    def setUp(self):
        self.polisher = TextPolisher()
        self.orig_polishing_enabled = storage.get_setting("polishing_enabled", True)
        storage.save_setting("polishing_enabled", True)

    def tearDown(self):
        storage.save_setting("polishing_enabled", self.orig_polishing_enabled)

    def test_timeout_safety(self):
        """A failed selected model makes one bounded request then falls back locally."""
        calls = []

        def get_setting(key, default=None):
            if key == "polishing_enabled":
                return True
            if key == "voice_flow_polish_model":
                return "gemini/gemini-3.5-flash"
            return default

        def failed_call(provider, key, system_prompt, user_payload, model=None, timeout=None):
            calls.append((provider, model, timeout))
            return None

        with (
            patch.object(storage, "get_setting", side_effect=get_setting),
            patch.object(storage, "get_all_api_keys", return_value={"gemini": "fake-key"}),
            patch.object(storage, "get_all_provider_connections", return_value={}),
            # This test exercises legacy-key failover. Keep a real saved OAuth
            # connection from issuing a request while the provider call below
            # is deliberately mocked.
            patch("voice_flow.voice_polish_bridge.can_execute_model", return_value=False),
            # The local model is a separate actor with its own coverage; this
            # test pins the cloud-provider timeout and deterministic fallback.
            patch("voice_flow.lfm_engine.is_lfm_downloaded", return_value=False),
            patch.object(self.polisher, "_try_provider_call", side_effect=failed_call),
        ):
            started = time.perf_counter()
            result = self.polisher.polish("um please test the timeout safety fallback with plenty of additional words here")
            elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.1)
        # A saved model is an explicit execution selection: the historical
        # Lite-first override was intentionally removed.
        self.assertEqual(calls[0][:2], ("gemini", "gemini-3.5-flash"))
        self.assertLessEqual(calls[0][2], 5.0)
        self.assertIn("please test the timeout safety fallback", result.lower().replace(",", "").replace(".", ""))

    def test_invalid_api_key_or_network_failure(self):
        """Test invalid API key or offline network failure falls back gracefully to raw text."""
        api_keys = {"gemini": "INVALID_KEY_12345_EXPLICIT_FAIL"}
        prompt = "test prompt"

        # Authentication failure is a deterministic adapter fixture, never a
        # request to Google's live API with a deliberately invalid credential.
        denied = urllib.error.HTTPError("https://test.invalid", 401, "Unauthorized", {}, None)
        with patch("voice_flow.polisher.urllib.request.urlopen", side_effect=denied):
            result = self.polisher._try_provider_call("gemini", api_keys["gemini"], prompt, prompt)
        self.assertIsNone(result)
        self.assertEqual(self.polisher._last_attempt_status, "http_401")

        # Mock api pool to return None (simulating all provider attempts failed due to network / bad key)
        orig_pool = self.polisher._polish_with_api_pool
        self.polisher._polish_with_api_pool = lambda raw_text, saved_keys, style_instruction: None

        raw_text = "uh hello this is a network error test"
        polished = self.polisher.polish(raw_text)
        self.assertTrue(len(polished) > 0)
        # Normalize punctuation/case for assertion
        self.assertIn("hello this is a network error test", polished.lower().replace(",", "").replace(".", ""))

    def test_built_in_nlp_fallback(self):
        """Test built-in zero-latency NLP fallback when API pool returns None."""
        self.polisher._polish_with_api_pool = lambda raw_text, saved_keys, style_instruction: None
        raw_text = "um ah clean this filler text"
        result = self.polisher.polish(raw_text)
        self.assertEqual(result, "Clean this filler text.")

    def test_truncation_safety_check(self):
        """Test that if AI polisher returns <50% of words, it reverts to raw STT text."""
        # Mock _polish_with_api_pool returning truncated text (1 word out of 8)
        self.polisher._polish_with_api_pool = lambda raw_text, saved_keys, style_instruction: "Truncated."
        raw_text = "one two three four five six seven eight nine ten"
        result = self.polisher.polish(raw_text)
        # Should fallback to raw text (post-processed by dictionary)
        self.assertIn("one two three four five six seven eight", result.lower())


if __name__ == "__main__":
    unittest.main()
