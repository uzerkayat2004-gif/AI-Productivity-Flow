"""Latency & fail-fast tests for the Voice Flow AI Polishing Engine.

Covers the guarantees that keep dictation snappy even when API keys are
dead, models are deprecated, or the network is slow:
1. Total polish wall-clock time is capped by the latency budget.
2. Dead credentials (HTTP 401/403/404) go into a long cooldown instead of
   being retried on every single dictation.
3. The Exec Voice Flow Policy model is attempted first for its provider.
4. Gemini responses without text (e.g. thinking-only candidates) are treated
   as failures, not silent successes.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import unittest
from unittest import mock

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.config import config
from voice_flow.polisher import TextPolisher
from voice_flow.storage import storage


class _FakeResponse:
    def __init__(self, data: bytes | str):
        self._data = data.encode("utf-8") if isinstance(data, str) else data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._data


class TestPolisherLatency(unittest.TestCase):
    def setUp(self):
        self.polisher = TextPolisher()
        storage.save_setting("polishing_enabled", True)

    def tearDown(self):
        self.polisher._rate_limited_keys = {}
        self.polisher._dead_keys = {}

    def test_latency_budget_caps_total_pool_time(self):
        """Slow provider calls must be cut short by the polish budget."""
        orig_budget = config.polish_budget_s
        config.polish_budget_s = 1.5
        try:
            def slow_call(provider, key, system_prompt, user_payload, model_override=None):
                time.sleep(0.8)
                return None

            self.polisher._try_provider_call = slow_call
            start = time.time()
            result = self.polisher.polish("um uh latency budget test")
            elapsed = time.time() - start
        finally:
            config.polish_budget_s = orig_budget

        self.assertLess(elapsed, 2.2, f"Polish pool exceeded latency budget: {elapsed:.2f}s")
        self.assertIn("latency budget test", result.lower())

    def test_dead_key_long_cooldown(self):
        """HTTP 403 on an OpenAI-style endpoint marks the key dead for 15 minutes."""
        import urllib.error

        key = "dead_key_abcdef"

        def raiser(*args, **kwargs):
            raise urllib.error.HTTPError("https://api.groq.com", 403, "Forbidden", {}, io.BytesIO(b""))

        with mock.patch("voice_flow.polisher.urllib.request.urlopen", side_effect=raiser):
            result = self.polisher._try_provider_call("groq", key, "sys", "user")

        self.assertIsNone(result)
        key_id = self.polisher._cooldown_key(key)
        self.assertIn(key_id, self.polisher._dead_keys)
        remaining = self.polisher._dead_keys[key_id] - time.time()
        self.assertGreater(remaining, 800.0, "Dead key cooldown should be ~15 minutes")
        self.assertTrue(self.polisher._key_in_cooldown(key, time.time()))

    def test_model_404_keeps_key_alive_and_tries_next_model(self):
        """A 404 is a dead model name, not a dead key: the key must stay alive
        and the next model in the provider list must be attempted."""
        import urllib.error

        key = "good_key_123456"
        attempted: list[str] = []

        def raiser(url, data=None, headers=None, timeout=None):
            # Simulate a retired default model answering 404 for this key.
            raise urllib.error.HTTPError("https://api.groq.com", 404, "Model Not Found", {}, io.BytesIO(b""))

        with mock.patch("voice_flow.polisher.urllib.request.urlopen", side_effect=raiser):
            result = self.polisher._try_provider_call("groq", key, "sys", "user")

        self.assertIsNone(result)
        key_id = self.polisher._cooldown_key(key)
        self.assertNotIn(key_id, self.polisher._dead_keys)
        self.assertFalse(self.polisher._key_in_cooldown(key, time.time()))

    def test_cleanup_none_is_true_verbatim(self):
        """cleanup_none must never capitalize or append a period (terminal
        windows, commands, exact snippets)."""
        self.assertEqual(
            self.polisher._deterministic_cleanup("ls -la", "Transcribe verbatim. Keep exact words without editing.", "cleanup_none"),
            "ls -la",
        )
        self.assertEqual(
            self.polisher._deterministic_cleanup("hey joey we still on for coffee", "Transcribe verbatim. Keep exact words without editing.", "cleanup_none"),
            "hey joey we still on for coffee",
        )
        # Non-verbatim levels still capitalize for sentence-style output.
        self.assertEqual(
            self.polisher._deterministic_cleanup("one two three four five", "", "cleanup_medium"),
            "One two three four five.",
        )

    def test_policy_model_is_tried_first_for_its_provider(self):
        """The Exec Voice Flow Policy model must be the first attempt for its provider."""
        storage.save_setting("exec_policy_model", "groq/llama-3.3-70b-specdec")
        calls: list[tuple] = []

        def recording_call(provider, key, system_prompt, user_payload, model_override=None):
            calls.append((provider, model_override))
            return "cleaned policy text"

        self.polisher._try_provider_call = recording_call
        result = self.polisher._polish_with_api_pool("raw policy text", {"groq": "gsk_test"}, style_instruction="")
        storage.save_setting("exec_policy_model", "gemini/gemini-3.6-flash")

        self.assertEqual(result, "cleaned policy text")
        self.assertEqual(calls[0], ("groq", "llama-3.3-70b-specdec"))

    def test_gemini_empty_candidate_is_a_failure(self):
        """200 responses with no text parts (e.g. thinking-only) must yield None."""
        body = json.dumps({
            "candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}]
        })
        with mock.patch("voice_flow.polisher.urllib.request.urlopen", return_value=_FakeResponse(body)):
            result = self.polisher._try_provider_call("gemini", "AIza_test", "sys", "user")

        self.assertIsNone(result)

    def test_oauth_token_and_junk_keys_are_skipped(self):
        """AQ.-prefixed OAuth tokens and junk strings must never hit the network."""
        calls: list[str] = []

        def recording_call(provider, key, system_prompt, user_payload, model_override=None):
            calls.append(key)
            return None

        self.polisher._try_provider_call = recording_call
        start = time.time()
        result = self.polisher._polish_with_api_pool(
            "one two three",
            {"gemini": "AQ.Ab8RN6JEX", "groq": "gsk_valid-looking-key"},
        )
        elapsed = time.time() - start

        self.assertIsNone(result)
        self.assertEqual(calls, ["gsk_valid-looking-key"], "OAuth/junk keys must be skipped before any attempt")
        self.assertLess(elapsed, 0.5)

    def test_all_dead_keys_fall_back_to_deterministic_fast(self):
        """Dead keys in cooldown are skipped instantly; deterministic cleanup still runs."""
        for key in ("gsk_dead1", "gsk_dead2"):
            self.polisher._mark_dead(key)

        def never_called(provider, key, system_prompt, user_payload, model_override=None):
            self.fail("Cooldown keys must never be attempted")

        self.polisher._try_provider_call = never_called
        start = time.time()
        result = self.polisher._polish_with_api_pool(
            "one two three four five",
            {"groq": "gsk_dead1", "gemini": "gsk_dead2"},
        )
        elapsed = time.time() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 0.5, "Cooldown-key skip should be instant")
        self.assertEqual(
            self.polisher._deterministic_cleanup("one two three four five", "", "cleanup_medium"),
            "One two three four five.",
        )


if __name__ == "__main__":
    unittest.main()
