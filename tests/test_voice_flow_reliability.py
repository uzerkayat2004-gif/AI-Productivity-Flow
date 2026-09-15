"""Regression tests for the 2026-09-01 reliability fixes.

BUG 1: multi-sentence dictations were lost to a regex group(3) crash in
       apply_capitalization_policy.
BUG 2: the polish prompt now mandates real grammar repair.
BUG 3: prompt mode preserves the user's dictated task.
BUG 4: consecutive echo repeats ("hey fix this hey fix this") collapse.
"""
from __future__ import annotations

import os
import sys
import unittest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.style_formatter import apply_capitalization_policy
from voice_flow.text_processing import cleanup_text, collapse_echo_repeats
from voice_flow.style_formatter import FORMAL_STYLE_CONFIG


class TestMultiSentenceCapitalizationRegression(unittest.TestCase):
    """BUG 1: any multi-sentence text used to raise 'no such group' and abort
    the whole pipeline — the user's long dictations vanished (no paste, no
    history)."""

    def test_multi_sentence_text_does_not_crash(self):
        text = "hey so we finished the build. it passed all tests! can you deploy it"
        cfg = FORMAL_STYLE_CONFIG
        out = apply_capitalization_policy(text, cfg, None)
        self.assertIn("Hey so we finished the build. It passed all tests! Can you deploy it", out)

    def test_long_dictation_survives_full_cleanup_chain(self):
        from voice_flow.text_processing import smart_format

        text = (
            "so the plan for tomorrow is simple. we ship the installer first, "
            "then we run the full suite? and after that i will write the release notes "
            "while you prepare the demo! that way everything is ready by monday morning "
            "and nobody has to rush before the launch meeting with the whole team"
        )
        out = smart_format(text, "other_formal")
        # Every sentence start capitalized, no crash, full content preserved.
        self.assertIn("We ship the installer", out)
        self.assertIn("And after that", out)
        self.assertIn("That way everything", out)
        self.assertIn("monday morning", out)

    def test_capitalization_policy_idempotent(self):
        text = "first sentence. second one! third?"
        cfg = FORMAL_STYLE_CONFIG
        once = apply_capitalization_policy(text, cfg, None)
        twice = apply_capitalization_policy(once, cfg, None)
        self.assertEqual(once, twice)


class TestEchoRepeatCollapse(unittest.TestCase):
    """BUG 4: immediate echoes collapse; distant repeats stay."""

    def test_two_word_echo(self):
        self.assertEqual(collapse_echo_repeats("hey fix this hey fix this"), "Hey fix this" if False else "hey fix this")

    def test_three_word_echo(self):
        self.assertEqual(collapse_echo_repeats("send the report send the report please"), "send the report please")

    def test_chain_of_echoes(self):
        self.assertEqual(collapse_echo_repeats("do it do it do it"), "do it")

    def test_distant_repeat_is_kept(self):
        text = "hey fix this in the morning, and remember I asked you to fix this yesterday"
        self.assertEqual(collapse_echo_repeats(text), text)

    def test_single_word_repeat_untouched(self):
        # One-word repeats are ambiguous ("that that") — leave them alone.
        self.assertEqual(collapse_echo_repeats("that that works"), "that that works")

    def test_cleanup_applies_echo_collapse(self):
        self.assertEqual(cleanup_text("hey fix this hey fix this", "cleanup_light"), "hey fix this")


class TestPromptAndGrammarInstructions(unittest.TestCase):
    def test_prompt_mode_instruction_preserves_task(self):
        from voice_flow.effective_style import PROMPT_MODE_INSTRUCTION

        self.assertIn("keep every requirement", PROMPT_MODE_INSTRUCTION)
        self.assertIn("never", PROMPT_MODE_INSTRUCTION.lower())

    def test_polish_prompt_mandates_grammar_repair(self):
        from voice_flow import polisher as pmod

        self.assertIn("fix ALL speech-to-text errors", pmod.POLISHER_SYSTEM_PROMPT)
        self.assertIn("ECHO REPEATS", pmod.POLISHER_SYSTEM_PROMPT)
        # The old contradictory guarantee must be gone.
        self.assertNotIn("strictly preserving 100%", pmod.POLISHER_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
