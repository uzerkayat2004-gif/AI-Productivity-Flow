"""Regression tests for the 2026-09-02 reliability hardening.

Pins the behaviors that fixed the live latency incidents:
- Deepgram flux models (streaming-only, no batch endpoint) remap to nova-3.
- Inactive/dead provider keys never feed cloud STT.
- The cloud breaker opens after ONE dictation on permanent failures
  (hard 4xx, unsupported provider) with a 30-min cooldown.
- The polish retention floor is 0.80 (faithful grammar fixes pass,
  catastrophic compression still rejected).
"""
from __future__ import annotations

import sys
import os
import threading
import time
import unittest
from unittest.mock import patch

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import voice_flow.stt_engines as engines
from voice_flow.polisher import TextPolisher, _candidate_preserves_content


def _audible(seconds: float = 2.0) -> "object":
    import numpy as np

    t = np.linspace(0, seconds, int(16000 * seconds), endpoint=False, dtype=np.float32)
    return (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _silence(seconds: float = 0.3) -> "object":
    import numpy as np

    return np.zeros(int(16000 * seconds), dtype=np.float32)


class TestDeepgramRouting(unittest.TestCase):
    def _capture_url(self, model: str) -> str:
        captured = {}

        def fake_send(req, timeout=120):
            captured["url"] = req.full_url
            import json as _json

            return _json.dumps(
                {"results": {"channels": [{"alternatives": [{"transcript": "hi"}]}]}}
            ).encode()

        with patch.object(engines, "_send", side_effect=fake_send):
            engines._deepgram(b"x", "key", model, "audio.wav", "audio/wav",
                              poll_seconds=5, vocabulary=["Voice Flow"])
        return captured["url"]

    def test_flux_maps_to_nova3_on_v1(self):
        # Flux is streaming-only (v2/listen is a WebSocket endpoint, POST 405):
        # batch dictation must use the nova-3 batch model instead.
        url = self._capture_url("flux-general-en")
        self.assertIn("/v1/listen", url)
        self.assertIn("model=nova-3", url)
        self.assertNotIn("flux", url)

    def test_bare_flux_maps_to_nova3(self):
        url = self._capture_url("flux")
        self.assertIn("model=nova-3", url)

    def test_nova3_unchanged_with_keyterm(self):
        url = self._capture_url("nova-3")
        self.assertIn("/v1/listen", url)
        self.assertIn("model=nova-3", url)
        self.assertIn("keyterm=Voice%20Flow", url)

    def test_keywords_param_never_sent(self):
        # Nova-3 rejects the nova-2-era keywords param (HTTP 400).
        url = self._capture_url("nova-3")
        self.assertNotIn("keywords=", url)


class TestKeyForActiveOnly(unittest.TestCase):
    def test_inactive_rows_are_skipped(self):
        from voice_flow import storage as storage_mod

        rows = {"get_provider_connections": [{"api_key": "dead", "is_active": 0}],
                "get_audio_provider_connections": [{"api_key": "fake", "is_active": 1}]}
        with (patch.object(storage_mod.storage, "get_provider_connections",
                           return_value=rows["get_provider_connections"]),
              patch.object(storage_mod.storage, "get_audio_provider_connections",
                           return_value=rows["get_audio_provider_connections"]),
              patch.object(storage_mod.storage, "get_all_api_keys",
                           return_value={})):
            self.assertEqual(engines._key_for("deepgram"), "fake")

    def test_no_fallback_to_inactive_rows(self):
        from voice_flow import storage as storage_mod

        with (patch.object(storage_mod.storage, "get_provider_connections",
                           return_value=[{"api_key": "dead", "is_active": 0}]),
              patch.object(storage_mod.storage, "get_audio_provider_connections",
                           return_value=[]),
              patch.object(storage_mod.storage, "get_all_api_keys",
                           return_value={})):
            with self.assertRaises(engines.STTError):
                engines._key_for("deepgram")


class TestBreakerHardFailures(unittest.TestCase):
    def _transcriber(self):
        from voice_flow import transcriber as tmod
        from voice_flow.transcriber import Transcriber

        t = object.__new__(Transcriber)
        t.model = object()
        t._loading = False
        t._lock = threading.Lock()
        t._transcribe_lock = threading.Lock()
        t.category_hint = None
        return t

    def _trip(self, error: str) -> tuple[float, float]:
        t = self._transcriber()
        with (patch("voice_flow.storage.storage.get_setting",
                    return_value="deepgram/flux-general-en"),
              patch("voice_flow.stt_engines.transcribe_cloud",
                    side_effect=engines.STTError(error)),
              patch.object(t, "_transcribe_local", return_value="")):
            t.transcribe(_audible())
        return (getattr(t, "_cloud_stt_failures", 0),
                getattr(t, "_cloud_stt_blocked_until", 0.0))

    def test_hard_4xx_trips_breaker_once_with_long_cooldown(self):
        from voice_flow.transcriber import _CLOUD_BREAKER_HARD_COOLDOWN_S

        failures, blocked_until = self._trip("HTTP 400: Keywords are not supported")
        self.assertEqual(failures, 2)
        remaining = blocked_until - time.time()
        self.assertGreater(remaining, _CLOUD_BREAKER_HARD_COOLDOWN_S - 60)

    def test_unsupported_provider_trips_breaker_once(self):
        failures, _ = self._trip("Provider 'cursor' does not support speech-to-text yet.")
        self.assertEqual(failures, 2)

    def test_transient_failure_keeps_short_cooldown(self):
        from voice_flow.transcriber import (
            _CLOUD_BREAKER_COOLDOWN_S,
            _CLOUD_BREAKER_HARD_COOLDOWN_S,
        )

        t = self._transcriber()
        with (patch("voice_flow.storage.storage.get_setting",
                    return_value="deepgram/flux-general-en"),
              patch("voice_flow.stt_engines.transcribe_cloud",
                    side_effect=engines.STTError("Connection failed: timeout")),
              patch.object(t, "_transcribe_local", return_value="")):
            t.transcribe(_audible())
            # A timeout is not hard: one dictation must NOT open the breaker.
            self.assertEqual(getattr(t, "_cloud_stt_failures", 0), 1)
            self.assertEqual(getattr(t, "_cloud_stt_blocked_until", 0.0), 0.0)
            t.transcribe(_audible())
        self.assertEqual(t._cloud_stt_failures, 2)
        remaining = t._cloud_stt_blocked_until - time.time()
        self.assertGreater(remaining, _CLOUD_BREAKER_COOLDOWN_S - 60)
        self.assertLess(remaining, _CLOUD_BREAKER_HARD_COOLDOWN_S)


class TestRetentionFloor(unittest.TestCase):
    SRC = " ".join(f"word{i}" for i in range(100))

    def _candidate(self, count: int) -> str:
        # First `count - 5` words + the closing 5 (so the tail check passes
        # and only the retention floor decides the outcome).
        head = self.SRC.split()[: count - 5]
        tail = self.SRC.split()[-5:]
        return " ".join(head + tail) + "."

    def test_faithful_polish_at_85_percent_passes(self):
        self.assertTrue(_candidate_preserves_content(self.SRC, self._candidate(85)))

    def test_compression_below_80_percent_rejected(self):
        self.assertFalse(_candidate_preserves_content(self.SRC, self._candidate(79)))

    def test_catastrophic_compression_still_rejected(self):
        # The measured 309->206-word regression must stay rejected.
        src = " ".join(f"alpha{i}" for i in range(309))
        cand = " ".join(f"alpha{i}" for i in range(206))
        self.assertFalse(_candidate_preserves_content(src, cand))


class TestPolisherFastLaneLongText(unittest.TestCase):
    def test_long_transcript_tries_fast_lane_first(self):
        pol = TextPolisher()
        calls = []

        def fake_setting(key, default=None):
            if key == "polishing_enabled":
                return True
            if key == "voice_flow_polish_model":
                return "gemini/gemini-3.7-flash"
            if key == "voice_flow_polish_speed_mode":
                return "balanced"
            return default

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            if model == "gemini-3.5-flash-lite":
                return "This is a faithful polished answer with every word kept."
            return None

        with (patch("voice_flow.polisher.storage.get_setting", side_effect=fake_setting),
              patch("voice_flow.polisher.storage.get_all_api_keys",
                    return_value={"gemini": "k"}),
              patch("voice_flow.polisher.storage.get_all_provider_connections",
                    return_value={}),
              patch.object(pol, "_try_provider_call", side_effect=fake_call)):
            out = pol.polish("um please polish this much longer dictation text with plenty of words")
        # The model the user selected is tried first and must not be skipped
        # for the Lite lane; Lite is still reached as the speed fallback once
        # the selection produced nothing.
        self.assertEqual(calls[0], "gemini-3.7-flash")
        self.assertEqual(calls[1], "gemini-3.5-flash-lite")
        self.assertTrue(out)


if __name__ == "__main__":
    unittest.main()
