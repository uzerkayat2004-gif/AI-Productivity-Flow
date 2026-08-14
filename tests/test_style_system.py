"""Comprehensive test suite for the Complete Context-Aware Style System."""

from __future__ import annotations

import unittest
from voice_flow.style_models import (
    WritingStyle,
    StyleCategory,
    TextboxContext,
    STYLE_CONFIGS,
    DEFAULT_CATEGORY_STYLES,
)
from voice_flow.style_formatter import style_formatter, TokenProtector
from voice_flow.style_engine import (
    StyleEngine,
    AppClassifier,
    StyleOverrideManager,
    detect_app_category,
)
from voice_flow.text_processing import cleanup_text, apply_style


class TestStylePresets(unittest.TestCase):
    """Tests for the 4 core Style presets: Formal, Casual, Very Casual, Excited."""

    def test_formal_preset(self):
        # Capitalizes sentence beginnings, "I", periods at natural boundaries, question marks
        raw = "hey Sarah just wanted to check if you received the document let me know when you get a chance"
        res = style_formatter.format(raw, style="formal")
        self.assertTrue(res.startswith("Hey Sarah"))
        self.assertTrue(res.endswith("."))

        # Pronoun I capitalization
        raw_i = "yeah i think i will be there tonight"
        res_i = style_formatter.format(raw_i, style="formal")
        self.assertEqual(res_i, "Yeah I think I will be there tonight.")

        # Question detection
        raw_q = "are you free tomorrow"
        res_q = style_formatter.format(raw_q, style="formal")
        self.assertEqual(res_q, "Are you free tomorrow?")

    def test_casual_preset(self):
        # Normal capitalization, lighter punctuation, omits unnecessary trailing period on conversational fragments
        raw = "hey are you free later we can grab coffee if you want"
        res = style_formatter.format(raw, style="casual")
        self.assertTrue(res.startswith("Hey"))
        # Should not force trailing period
        self.assertFalse(res.endswith("."))

    def test_very_casual_preset(self):
        # Lowercase sentence beginnings, lowercase "i", minimal punctuation
        raw = "hey are you coming tonight let me know"
        res = style_formatter.format(raw, style="very_casual")
        self.assertEqual(res, "hey are you coming tonight let me know")

        raw_i = "yeah i think i will check it tonight"
        res_i = style_formatter.format(raw_i, style="very_casual")
        self.assertEqual(res_i, "yeah i think i will check it tonight")

    def test_excited_preset(self):
        # Expressive punctuation on positive/excited boundaries
        raw = "that's amazing congrats i'm really happy for you"
        res = style_formatter.format(raw, style="excited")
        self.assertTrue(res.endswith("!"))
        self.assertTrue(res.startswith("That's"))

        # Neutral / Negative statements do NOT get artificial exclamation marks
        raw_neg = "the server is down again"
        res_neg = style_formatter.format(raw_neg, style="excited")
        self.assertFalse(res_neg.endswith("!"))
        self.assertTrue(res_neg.endswith("."))


class TestContextAwareFormatting(unittest.TestCase):
    """Tests for cursor / textbox context awareness."""

    def test_mid_sentence_insertion(self):
        # User is typing mid-sentence: do NOT capitalize first letter
        ctx = TextboxContext(before="Hey John, I wanted to ask ", trustworthy=True)
        raw = "if you're free tomorrow"
        res = style_formatter.format(raw, style="formal", context=ctx)
        self.assertTrue(res.startswith("if you're free"))
        self.assertFalse(res.startswith("If"))

    def test_new_sentence_insertion(self):
        # User is typing after a period: DO capitalize first letter
        ctx = TextboxContext(before="Sounds good. ", trustworthy=True)
        raw = "i'll call you tomorrow"
        res = style_formatter.format(raw, style="formal", context=ctx)
        self.assertTrue(res.startswith("I'll call"))

    def test_existing_punctuation_no_duplication(self):
        # After text already has a question mark: do NOT duplicate
        ctx = TextboxContext(before="Hey, ", after="?", trustworthy=True)
        raw = "are you free tomorrow"
        res = style_formatter.format(raw, style="formal", context=ctx)
        self.assertFalse(res.endswith("??"))

    def test_boundary_spacing(self):
        # Before text lacks trailing space: add leading space
        ctx1 = TextboxContext(before="hello", after="world", trustworthy=True)
        res1 = style_formatter.format("John", style="casual", context=ctx1)
        self.assertTrue(res1.startswith(" "))
        self.assertTrue(res1.endswith(" "))


class TestTokenProtection(unittest.TestCase):
    """Tests preserving URLs, emails, acronyms, code tokens, and numbers."""

    def test_url_and_email_preservation(self):
        raw = "check https://example.com/test or email john@example.com for info"
        res_vc = style_formatter.format(raw, style="very_casual")
        self.assertIn("https://example.com/test", res_vc)
        self.assertIn("john@example.com", res_vc)

    def test_acronym_preservation(self):
        # Acronyms should stay uppercase even in Very Casual
        raw = "we built an API with JSON and HTTP for the GPT LLM"
        res_vc = style_formatter.format(raw, style="very_casual")
        self.assertIn("API", res_vc)
        self.assertIn("JSON", res_vc)
        self.assertIn("HTTP", res_vc)
        self.assertIn("GPT", res_vc)
        self.assertIn("LLM", res_vc)

    def test_numbers_and_currencies_preservation(self):
        raw = "the price is $1,500 at 2:30 PM with 20% discount on v2.1"
        res = style_formatter.format(raw, style="formal")
        self.assertIn("$1,500", res)
        self.assertIn("2:30 PM", res)
        self.assertIn("20%", res)
        self.assertIn("v2.1", res)

    def test_dictionary_proper_nouns_preservation(self):
        custom_dict = ["Wispr", "OpenAI", "DeepMind", "NextJS"]
        raw = "we tested wispr with openai and deepmind"
        res = style_formatter.format(raw, style="formal", custom_dictionary=custom_dict)
        self.assertIn("Wispr", res)
        self.assertIn("OpenAI", res)
        self.assertIn("DeepMind", res)


class TestAppAndDomainClassification(unittest.TestCase):
    """Tests for application & browser domain classification and user overrides."""

    def setUp(self):
        self.classifier = AppClassifier()

    def test_native_app_classification(self):
        self.assertEqual(self.classifier.classify("WhatsApp", "whatsapp.exe"), "personal")
        self.assertEqual(self.classifier.classify("Slack", "slack.exe"), "work")
        self.assertEqual(self.classifier.classify("Outlook", "outlook.exe"), "email")
        self.assertEqual(self.classifier.classify("VS Code", "code.exe"), "developer")
        self.assertEqual(self.classifier.classify("Notepad", "notepad.exe"), "other")

    def test_browser_domain_classification(self):
        # Browser shell (Google Chrome) with Gmail domain -> Email
        self.assertEqual(self.classifier.classify("Google Chrome", "chrome.exe", domain="mail.google.com"), "email")
        # Browser shell with Slack domain -> Work
        self.assertEqual(self.classifier.classify("Google Chrome", "chrome.exe", domain="app.slack.com"), "work")
        # Browser shell with WhatsApp Web -> Personal
        self.assertEqual(self.classifier.classify("Google Chrome", "chrome.exe", domain="web.whatsapp.com"), "personal")
        # Browser shell with GitHub -> Developer
        self.assertEqual(self.classifier.classify("Google Chrome", "chrome.exe", domain="github.com"), "developer")
        # Unknown website -> Other
        self.assertEqual(self.classifier.classify("Google Chrome", "chrome.exe", domain="example.org"), "other")

    def test_user_overrides_priority(self):
        # Discord is normally Personal, user overrides Discord to Work
        self.classifier.set_app_override("discord.exe", "work")
        self.assertEqual(self.classifier.classify("Discord", "discord.exe"), "work")
        self.classifier.remove_app_override("discord.exe")

        # Custom domain override
        self.classifier.set_domain_override("custom-work-chat.com", "work")
        self.assertEqual(self.classifier.classify("Chrome", "chrome.exe", domain="custom-work-chat.com"), "work")
        self.classifier.remove_domain_override("custom-work-chat.com")


class TestTemporaryStyleOverride(unittest.TestCase):
    """Tests temporary per-dictation style override."""

    def test_temporary_override_lifecycle(self):
        engine = StyleEngine()
        # Normal WhatsApp resolution -> Category Personal (Casual/Very Casual)
        res1 = engine.resolve(None, site_host="web.whatsapp.com", consume_override=False)
        self.assertEqual(res1.category, "personal")

        # Set temporary override to Formal
        engine.override_manager.set_temporary_override("formal")
        res2 = engine.resolve(None, site_host="web.whatsapp.com", consume_override=True)
        self.assertEqual(res2.resolved_style, "formal")

        # Next session should automatically revert to normal category style
        res3 = engine.resolve(None, site_host="web.whatsapp.com", consume_override=True)
        self.assertEqual(res3.resolved_style, engine.get_category_style("personal"))


class TestSeparationOfConcerns(unittest.TestCase):
    """Tests that Style is completely decoupled from Cleanup and Rewriting."""

    def test_cleanup_independence(self):
        raw = "so um basically what i wanted to say is we should launch saturday"
        # Step 1: Cleanup
        cleaned = cleanup_text(raw, level="cleanup_light")
        self.assertNotIn("um", cleaned)

        # Step 2: Very Casual Style on cleaned text
        styled_vc = style_formatter.format(cleaned, style="very_casual")
        self.assertTrue(styled_vc.startswith("so basically") or styled_vc.startswith("what i wanted"))

        # Step 3: Formal Style on cleaned text
        styled_formal = style_formatter.format(cleaned, style="formal")
        self.assertTrue(styled_formal.endswith("."))


if __name__ == "__main__":
    unittest.main()
