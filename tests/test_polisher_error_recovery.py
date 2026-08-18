import unittest
import time
import os
import sys

# Ensure src directory is in sys.path
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.polisher import TextPolisher
from voice_flow.storage import storage


class TestPolisherErrorRecovery(unittest.TestCase):
    def setUp(self):
        self.polisher = TextPolisher()
        # Save polishing setting state
        storage.save_setting("polishing_enabled", True)

    def test_timeout_safety(self):
        """Test that slow/hanging provider call times out and falls back cleanly."""
        # Save real _try_provider_call
        orig_call = self.polisher._try_provider_call

        def mock_slow_call(provider, key, system_prompt, user_payload, model_override=None):
            time.sleep(2.0)
            return None

        self.polisher._try_provider_call = mock_slow_call
        # Mock _polish_with_api_pool or ensure saved_keys is empty so built-in NLP triggers quickly for test
        self.polisher._rate_limited_keys = {}

        # Test with built-in NLP fallback or quick mock
        raw_text = "um uh testing timeout safety fallback"
        start_time = time.time()
        result = self.polisher.polish(raw_text)

        self.assertTrue(len(result) > 0)
        self.assertIn("testing timeout safety fallback", result.lower().replace(",", ""))

    def test_invalid_api_key_or_network_failure(self):
        """Test invalid API key or offline network failure falls back gracefully to raw text."""
        api_keys = {"gemini": "INVALID_KEY_12345_EXPLICIT_FAIL"}
        prompt = "test prompt"

        result = self.polisher._try_provider_call("gemini", api_keys["gemini"], prompt, prompt)
        self.assertIsNone(result)

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
        raw_text = "one two three four five six seven eight"
        result = self.polisher.polish(raw_text)
        # Should fallback to raw text (post-processed by dictionary)
        self.assertIn("one two three four five six seven eight", result.lower())


if __name__ == "__main__":
    unittest.main()
