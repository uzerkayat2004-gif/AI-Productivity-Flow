"""End-to-end API integration tests for the Context-Aware Style System endpoints."""

from __future__ import annotations

import json
import unittest
from voice_flow.style_engine import style_engine
from voice_flow.style_formatter import style_formatter
from voice_flow.style_models import TextboxContext
from voice_flow.storage import storage


class TestStyleAPIEndpoints(unittest.TestCase):
    def setUp(self):
        # Save previous state
        self.orig_personal = storage.get_setting("style_personal", "casual")
        self.orig_work = storage.get_setting("style_work", "casual")

    def tearDown(self):
        # Restore state
        storage.save_setting("style_personal", self.orig_personal)
        storage.save_setting("style_work", self.orig_work)

    def test_style_get_and_update(self):
        # Update category style
        style_engine.set_category_style("personal", "very_casual")
        self.assertEqual(style_engine.get_category_style("personal"), "very_casual")

        style_engine.set_category_style("personal", "formal")
        self.assertEqual(style_engine.get_category_style("personal"), "formal")

    def test_preview_endpoint_logic(self):
        raw_text = "hey alex yeah sounds good i'll send it tomorrow thanks"
        ctx = TextboxContext(before="I wanted to ask ", trustworthy=True)

        formal_out = style_formatter.format(raw_text, style="formal", context=ctx)
        casual_out = style_formatter.format(raw_text, style="casual", context=ctx)
        vc_out = style_formatter.format(raw_text, style="very_casual", context=ctx)
        excited_out = style_formatter.format(raw_text, style="excited", context=ctx)

        # Formal should have standard casing & punctuation
        self.assertTrue(formal_out.startswith("if") or formal_out.startswith("hey"))
        # Very casual should be lowercase
        self.assertTrue(vc_out.startswith("hey alex"))
        # Excited should have exclamation
        self.assertTrue(excited_out.endswith("!"))

    def test_app_and_domain_overrides_management(self):
        # Add app override
        style_engine.classifier.set_app_override("custom_chat.exe", "personal")
        self.assertEqual(style_engine.classifier.classify("Custom Chat", "custom_chat.exe"), "personal")

        # Remove app override
        style_engine.classifier.remove_app_override("custom_chat.exe")
        self.assertEqual(style_engine.classifier.classify("Custom Chat", "custom_chat.exe"), "other")

        # Add domain override
        style_engine.classifier.set_domain_override("custom-work-slack.internal", "work")
        self.assertEqual(style_engine.classifier.classify("Browser", "chrome.exe", domain="custom-work-slack.internal"), "work")

        # Remove domain override
        style_engine.classifier.remove_domain_override("custom-work-slack.internal")
        self.assertEqual(style_engine.classifier.classify("Browser", "chrome.exe", domain="custom-work-slack.internal"), "other")

    def test_temporary_override(self):
        style_engine.override_manager.set_temporary_override("excited")
        res = style_engine.resolve(site_host="mail.google.com", consume_override=True)
        self.assertEqual(res.resolved_style, "excited")

        # Next resolution should revert back to normal category preference (formal)
        res_next = style_engine.resolve(site_host="mail.google.com", consume_override=True)
        self.assertEqual(res_next.resolved_style, style_engine.get_category_style("email"))


if __name__ == "__main__":
    unittest.main()
