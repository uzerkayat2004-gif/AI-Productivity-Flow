"""Integration and unit tests for Style Engine, Text Formatting, Polisher, and Pipeline Integration."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure src is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_flow.style_engine import (
    StylePreset,
    ResolvedStyle,
    STYLE_OPTIONS,
    CATEGORY_DEFAULTS,
    detect_app_category,
    StyleEngine,
)
from voice_flow.text_processing import apply_style, split_press_enter, apply_spoken_punctuation
from voice_flow.polisher import TextPolisher, _candidate_preserves_content


class TestAppCategorization(unittest.TestCase):
    def test_app_categories(self):
        # Slack -> Work
        self.assertEqual(detect_app_category("Slack - Workspace", "slack.exe"), "work")
        # Teams -> Work
        self.assertEqual(detect_app_category("Microsoft Teams", "teams.exe"), "work")
        # Discord -> Personal
        self.assertEqual(detect_app_category("Discord | #general", "discord.exe"), "personal")
        # WhatsApp -> Personal
        self.assertEqual(detect_app_category("WhatsApp", "chrome.exe"), "personal")
        # Claude -> Other
        self.assertEqual(detect_app_category("Claude", "chrome.exe"), "other")
        self.assertEqual(detect_app_category("Claude Code", "cmd.exe"), "other")
        # ChatGPT -> Other
        self.assertEqual(detect_app_category("ChatGPT", "chrome.exe"), "other")
        # Unknown app -> other (canonical fallback category)
        self.assertEqual(detect_app_category("Notepad", "notepad.exe"), "other")


class TestStyleResolution(unittest.TestCase):
    @patch("voice_flow.style_engine.storage")
    def test_valid_style_resolution(self, mock_storage):
        mock_storage.get_setting.side_effect = lambda key, default: "work_excited" if key == "style_work" else default
        engine = StyleEngine()
        resolved = engine.resolve_for_target(None)
        # Assuming get_active_app_info returns General App -> autocleanup
        self.assertIsInstance(resolved, ResolvedStyle)

    @patch("voice_flow.style_engine.storage")
    @patch("voice_flow.style_engine.get_app_info_for_hwnd")
    def test_cross_category_fallback(self, mock_get_app_info, mock_storage):
        mock_get_app_info.return_value = ("Slack", "slack.exe")  # category: work
        # Stored setting is a personal style ID (cross-category invalid)
        mock_storage.get_setting.return_value = "personal_very_casual"

        engine = StyleEngine()
        resolved = engine.resolve_for_target(12345)

        self.assertEqual(resolved.category, "work")
        self.assertEqual(resolved.style_id, CATEGORY_DEFAULTS["work"])
        self.assertEqual(resolved.style_id, "work_casual")


class TestTextFormatting(unittest.TestCase):
    def test_cleanup_none_verbatim(self):
        # cleanup_none should be a true verbatim no-op
        raw = "um hello world"
        self.assertEqual(apply_style(raw, "cleanup_none"), "um hello world")

    def test_very_casual_lowercasing(self):
        # Convert text to lowercase, but PRESERVE explicit spoken punctuation (?, !)
        raw = "Hello World?"
        formatted = apply_style(raw, "personal_very_casual")
        self.assertEqual(formatted, "hello world?")

        raw_excl = "Hello World!"
        formatted_excl = apply_style(raw_excl, "personal_very_casual")
        self.assertEqual(formatted_excl, "hello world!")

    def test_explicit_spoken_punctuation_preserved(self):
        # Spoken punctuation precedence: preserve explicit terminal marks
        spoken = apply_spoken_punctuation("is this working question mark")
        self.assertTrue(spoken.endswith("?"))
        styled = apply_style(spoken, "work_formal")
        self.assertTrue(styled.endswith("?"))
        self.assertFalse(styled.endswith("?."))


class TestPolisherDeterministicPipeline(unittest.TestCase):
    @patch("voice_flow.polisher.storage")
    @patch("voice_flow.polisher.dictionary_engine")
    def test_finalize_routing(self, mock_dict_engine, mock_storage):
        mock_storage.get_setting.side_effect = lambda key, default: False if key == "polishing_enabled" else default
        mock_dict_engine.apply_dictionary_post_processing.side_effect = lambda text: text + " [dict_applied]"

        polisher = TextPolisher()
        resolved_style = ResolvedStyle("Slack", "work", "work_casual", "Casual", "Format as clear chat text.")
        res = polisher.polish("hello world", resolved_style)

        self.assertIn("[dict_applied]", res)
        self.assertTrue(res.startswith("Hello world"))


if __name__ == "__main__":
    unittest.main()
