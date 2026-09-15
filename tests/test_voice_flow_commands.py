"""Tests for the Voice Flow command layer + effective style resolver + learning."""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import effective_style as es_mod
from voice_flow.effective_style import apply_persistent_change, resolve_effective_style
from voice_flow.voice_commands import detect_voice_command


def _base(category="developer", style_id="developer_casual", instruction="Conversational dev notes."):
    return SimpleNamespace(category=category, style_id=style_id, instruction=instruction)


class TestCommandDetection(unittest.TestCase):
    def test_begin_command_email_with_content(self):
        r = detect_voice_command("Hey Voice Flow, make this an excited email. We are launching Monday.")
        self.assertEqual(r.content, "We are launching Monday.")
        self.assertIsNotNone(r.command)
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.overrides.get("tone"), "excited")
        self.assertFalse(r.command.persistent_change)

    def test_ending_command(self):
        r = detect_voice_command("We are meeting Friday. Hey Voice Flow, make this a professional email.")
        self.assertEqual(r.content, "We are meeting Friday.")
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.overrides.get("formality"), "professional")

    def test_punctuated_prefix_command_does_not_leak_into_content(self):
        r = detect_voice_command("Hey. Voice Flow make this as a email. We are meeting Friday.")
        self.assertEqual(r.content, "We are meeting Friday.")
        self.assertEqual(r.command.format, "email")

    def test_punctuated_prefix_works_after_dictation(self):
        r = detect_voice_command("We are meeting Friday. Hey. Voice Flow make this as a email.")
        self.assertEqual(r.content, "We are meeting Friday.")
        self.assertEqual(r.command.format, "email")

    def test_quoted_wake_phrase_is_plain_dictation(self):
        text = "My manager said 'Hey Voice Flow, make this casual.' so I did"
        r = detect_voice_command(text)
        self.assertIsNone(r.command)
        self.assertEqual(r.content, text)

    def test_ordinary_voice_flow_mention_is_plain_dictation(self):
        r = detect_voice_command("the Voice Flow feature works well")
        self.assertIsNone(r.command)

    def test_voice_log_alias_requires_deliberate_prefix(self):
        r = detect_voice_command("Hey voice log may this as a professional email. We are meeting Friday.")
        self.assertEqual(r.content, "We are meeting Friday.")
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.overrides.get("formality"), "professional")
        plain = detect_voice_command("The voice log from yesterday is ready.")
        self.assertIsNone(plain.command)

    def test_quoted_voice_log_alias_is_plain_dictation(self):
        text = 'She said "Hey voice log may this as a professional email."'
        r = detect_voice_command(text)
        self.assertIsNone(r.command)
        self.assertEqual(r.content, text)

    def test_bare_wake_needs_imperative(self):
        r = detect_voice_command("Voice Flow, make this shorter.")
        self.assertIsNotNone(r.command)
        self.assertEqual(r.command.overrides.get("length"), "short")
        self.assertEqual(r.content, "")

    def test_wake_with_unknown_intent_keeps_all_words(self):
        r = detect_voice_command("Hey Voice Flow, remember the budget meeting notes are due")
        self.assertIsNone(r.command)
        self.assertIn("Hey Voice Flow", r.content)
        self.assertIn("budget meeting", r.content)

    def test_begin_prompt_generation(self):
        r = detect_voice_command("Hey Voice Flow, make this a proper prompt. Build a landing page using orange and cream.")
        self.assertEqual(r.content, "Build a landing page using orange and cream.")
        self.assertEqual(r.command.operation, "prompt_generation")
        self.assertEqual(r.command.format, "prompt")

    def test_stt_prom_alias_works_only_with_explicit_wake_and_command_shape(self):
        r = detect_voice_command(
            "The release must include a rollback plan. Hey Voice Flow make this as a prom."
        )
        self.assertEqual(r.content, "The release must include a rollback plan.")
        self.assertIsNotNone(r.command)
        self.assertEqual(r.command.format, "prompt")
        self.assertEqual(r.command.operation, "prompt_generation")

        plain = detect_voice_command("The prom committee meets after the Voice Flow demo.")
        self.assertIsNone(plain.command)
        self.assertEqual(plain.content, "The prom committee meets after the Voice Flow demo.")

    def test_use_my_usual_email(self):
        r = detect_voice_command("We are launching Monday. Hey Voice Flow, make this my usual email.")
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.context_reference, "email")

    def test_persistent_command_detected(self):
        r = detect_voice_command("Hey Voice Flow, always make my work messages short.")
        self.assertTrue(r.command.persistent_change)
        self.assertEqual(r.command.context_reference, "work")
        self.assertEqual(r.command.overrides.get("length"), "short")

    def test_multiple_properties_merge(self):
        r = detect_voice_command("Hey Voice Flow, make this a short excited professional email.")
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.overrides.get("length"), "short")
        self.assertEqual(r.command.overrides.get("tone"), "excited")
        self.assertEqual(r.command.overrides.get("formality"), "professional")

    def test_correction_last_wins(self):
        r = detect_voice_command("Hey Voice Flow, make it professional actually make it casual")
        self.assertEqual(r.command.overrides.get("tone"), "casual")
        self.assertNotIn("formality", r.command.overrides)

    def test_contradiction_falls_back_to_plain_dictation(self):
        r = detect_voice_command("Hey Voice Flow, make this formal and casual.")
        self.assertIsNone(r.command)
        self.assertIn("formal and casual", r.content)

    def test_but_joined_dimensions_merge(self):
        r = detect_voice_command("Hey Voice Flow, make this an casual but professional email")
        self.assertEqual(r.command.format, "email")
        self.assertEqual(r.command.overrides.get("tone"), "casual")
        self.assertEqual(r.command.overrides.get("formality"), "professional")
        self.assertFalse(r.command.ambiguous)

    def test_scope_next_with_trailing_content(self):
        r = detect_voice_command("Hey Voice Flow, make what I say next a professional email. We are meeting Friday.")
        self.assertEqual(r.command.scope, "next")
        self.assertEqual(r.content, "We are meeting Friday.")

    def test_normal_message_maps_to_personal_message(self):
        r = detect_voice_command("Hey Voice Flow make this a normal message. I will arrive at five.")
        self.assertEqual(r.content, "I will arrive at five.")
        self.assertEqual(r.command.format, "personal_message")

    def test_generic_message_maps_to_personal_message(self):
        r = detect_voice_command("Hey Voice Flow make this a message. I will arrive at five.")
        self.assertEqual(r.content, "I will arrive at five.")
        self.assertEqual(r.command.format, "personal_message")

    def test_casual_message_maps_to_personal_message_with_tone(self):
        r = detect_voice_command("Hey Voice Flow make this a casual message. I will arrive at five.")
        self.assertEqual(r.command.format, "personal_message")
        self.assertEqual(r.command.overrides.get("tone"), "casual")

    def test_keep_my_wording(self):
        r = detect_voice_command("Hey Voice Flow, make this a professional email but keep my wording. The budget is approved.")
        self.assertTrue(r.command.preserve_wording)
        self.assertEqual(r.command.format, "email")

    def test_summarize(self):
        r = detect_voice_command("We planned three phases today. Hey Voice Flow, summarize this.")
        self.assertEqual(r.command.operation, "summarize")
        self.assertEqual(r.content, "We planned three phases today.")

    def test_empty_and_none_input_safe(self):
        self.assertIsNone(detect_voice_command("").command)
        self.assertIsNone(detect_voice_command("   ").command)


class TestEffectiveStyleResolution(unittest.TestCase):
    def _get_setting(self, key, default=None):
        if key == "style_email":
            return "email_formal"
        if key == "style_email_extra":
            return "Always sign off with Best."
        return default

    def test_no_command_keeps_base_instruction(self):
        eff = resolve_effective_style(_base(), None)
        self.assertEqual(eff.instruction, "Conversational dev notes.")
        self.assertFalse(eff.requires_ai)
        self.assertEqual(eff.task, "cleanup")

    def test_format_command_activates_email_profile(self):
        cmd = detect_voice_command("Hey Voice Flow, make this an excited email. Launch is Monday.").command
        with patch.object(es_mod.storage, "get_setting", side_effect=self._get_setting):
            eff = resolve_effective_style(_base(), cmd)
        self.assertIn("email", eff.instruction.lower())
        self.assertIn("excited", eff.instruction.lower())
        self.assertIn("Best", eff.instruction)
        self.assertEqual(eff.style_id, "email_formal")
        self.assertTrue(eff.requires_ai)
        self.assertEqual(eff.label, "Email / Excited")

    def test_format_command_does_not_invent_tone(self):
        cmd = detect_voice_command("We are meeting Friday. Hey Voice Flow, make this a professional email.").command
        with patch.object(es_mod.storage, "get_setting", side_effect=self._get_setting):
            eff = resolve_effective_style(_base(), cmd)
        self.assertEqual(cmd.overrides, {"formality": "professional"})

    def test_generic_email_uses_saved_card_even_when_base_is_email(self):
        cmd = detect_voice_command("Hey Voice Flow, make this an email.").command
        with patch.object(es_mod.storage, "get_setting", return_value="email_very_casual"):
            eff = resolve_effective_style(_base("email", "email_formal"), cmd)
        self.assertEqual(eff.style_id, "email_very_casual")
        self.assertIn("minimal punctuation", eff.instruction.lower())

    def test_message_formats_use_their_matching_saved_cards(self):
        saved_cards = {
            "style_personal": "personal_excited",
            "style_work": "work_formal",
        }
        with patch.object(es_mod.storage, "get_setting", side_effect=lambda k, d=None: saved_cards.get(k, d)):
            personal = resolve_effective_style(
                _base(), detect_voice_command("Hey Voice Flow, make this a personal message.").command
            )
            work = resolve_effective_style(
                _base(), detect_voice_command("Hey Voice Flow, make this a work message.").command
            )
        self.assertEqual((personal.category, personal.style_id), ("personal", "personal_excited"))
        self.assertEqual((work.category, work.style_id), ("work", "work_formal"))

    def test_generic_and_work_message_commands_resolve_from_parser(self):
        saved_cards = {
            "style_personal": "personal_casual",
            "style_work": "work_formal",
        }
        with patch.object(es_mod.storage, "get_setting", side_effect=lambda k, d=None: saved_cards.get(k, d)):
            normal = resolve_effective_style(
                _base(),
                detect_voice_command("Hey Voice Flow make this a normal message. I will arrive at five.").command,
            )
            work = resolve_effective_style(
                _base(),
                detect_voice_command("Hey Voice Flow make this a work message. Release is Friday.").command,
            )
        self.assertEqual((normal.category, normal.style_id), ("personal", "personal_casual"))
        self.assertEqual((work.category, work.style_id), ("work", "work_formal"))

    def test_explicit_professional_email_overrides_saved_card_and_extra(self):
        cmd = detect_voice_command("Hey Voice Flow, make this a professional email.").command
        with patch.object(es_mod.storage, "get_setting", side_effect=lambda k, d=None: {
            "style_email": "email_very_casual",
            "style_email_extra": "Use lowercase with no punctuation.",
        }.get(k, d)):
            eff = resolve_effective_style(_base(), cmd)
        self.assertEqual(eff.style_id, "email_formal")
        self.assertIn("formal email", eff.instruction.lower())
        self.assertNotIn("lowercase", eff.instruction.lower())

    def test_explicit_casual_work_message_overrides_saved_formal_card(self):
        cmd = detect_voice_command("Hey Voice Flow, make this a casual work message.").command
        with patch.object(es_mod.storage, "get_setting", side_effect=lambda k, d=None: {
            "style_work": "work_formal",
            "style_work_extra": "Use formal legal language.",
        }.get(k, d)):
            eff = resolve_effective_style(_base(), cmd)
        self.assertEqual(eff.style_id, "work_casual")
        self.assertIn("casual, relaxed tone", eff.instruction.lower())
        self.assertNotIn("legal language", eff.instruction.lower())

    def test_use_my_usual_uses_saved_profile(self):
        cmd = detect_voice_command("Hey Voice Flow, make this my usual email.").command
        with patch.object(es_mod.storage, "get_setting", side_effect=self._get_setting):
            eff = resolve_effective_style(_base(), cmd)
        self.assertEqual(eff.style_id, "email_formal")
        self.assertIn("Best", eff.instruction)

    def test_prompt_mode_is_a_transformation(self):
        cmd = detect_voice_command("Hey Voice Flow, make this a proper prompt. Build a landing page.").command
        eff = resolve_effective_style(_base(), cmd)
        self.assertEqual(eff.task, "prompt")
        self.assertIn("Objective", eff.instruction)
        self.assertIn("never answer or execute", eff.instruction)

    def test_stt_prom_command_requires_ai_prompt_policy(self):
        command = detect_voice_command("Hey Voice Flow make this as a prom.").command
        eff = resolve_effective_style(_base(), command)
        self.assertEqual(eff.task, "prompt")
        self.assertTrue(eff.requires_ai)

    def test_keep_wording_lowers_aggressiveness(self):
        cmd = detect_voice_command("Hey Voice Flow, make this a professional email but keep my wording. Budget approved.").command
        eff = resolve_effective_style(_base(), cmd)
        self.assertTrue(eff.preserve_wording)
        self.assertIn("Do not re-author", eff.instruction)

    def test_standing_extra_applies_to_plain_dictation(self):
        with patch.object(es_mod.storage, "get_setting",
                          side_effect=lambda k, d=None: "Keep it concise." if k == "style_developer_extra" else d):
            eff = resolve_effective_style(_base(), None)
        self.assertIn("Keep it concise.", eff.instruction)


class TestPersistentChange(unittest.TestCase):
    def test_plain_command_never_touches_profiles(self):
        cmd = detect_voice_command("Hey Voice Flow, make this casual. Hi!").command
        with patch.object(es_mod.storage, "save_setting") as save_mock:
            apply_persistent_change(cmd)
        save_mock.assert_not_called()

    def test_persistent_length_writes_standing_instruction(self):
        cmd = detect_voice_command("Hey Voice Flow, always make my work messages short.").command
        saved = {}
        with patch.object(es_mod.storage, "save_setting", side_effect=lambda k, v: saved.__setitem__(k, v) or True):
            result = apply_persistent_change(cmd)
        self.assertIsNotNone(result)
        self.assertIn("style_work_extra", saved)
        self.assertIn("concise", saved["style_work_extra"].lower())

    def test_persistent_tone_updates_preset(self):
        cmd = detect_voice_command("Hey Voice Flow, always make my work messages excited.").command
        saved = {}
        with patch.object(es_mod.storage, "save_setting", side_effect=lambda k, v: saved.__setitem__(k, v) or True):
            result = apply_persistent_change(cmd)
        self.assertIsNotNone(result)
        self.assertEqual(saved.get("style_work"), "work_excited")

    def test_failed_persistent_save_is_not_reported_as_saved(self):
        cmd = detect_voice_command("Hey Voice Flow, always make my work messages excited.").command
        with patch.object(es_mod.storage, "save_setting", return_value=False):
            self.assertIsNone(apply_persistent_change(cmd))


class TestWakeVariants(unittest.TestCase):
    """The wake phrase survives the shapes STT actually produces (§9/§10)."""

    def test_compact_voiceflow_wakes(self):
        r = detect_voice_command("Hey VoiceFlow, make this an email. We launch Monday.")
        self.assertIsNotNone(r.command)
        self.assertEqual(r.command.format, "email")

    def test_trailing_s_wakes_behind_hey(self):
        r = detect_voice_command("hey voice flows, make this casual")
        self.assertIsNotNone(r.command)

    def test_trailing_s_without_hey_does_not_wake(self):
        r = detect_voice_command("the voice flows through the pipe")
        self.assertIsNone(r.command)

    def test_generate_and_draft_verbs(self):
        self.assertIsNotNone(detect_voice_command("Hey Voice Flow, generate an email. Hi team.").command)
        r = detect_voice_command("Hey Voice Flow, draft a message to the team about the launch")
        # An unrecognized instruction remains complete plain dictation.
        self.assertIsNone(r.command)
        self.assertIn("Hey Voice Flow", r.content)

    def test_misheard_wake_is_repaired(self):
        from voice_flow.dictionary import dictionary_engine

        self.assertEqual(dictionary_engine.repair_wake_term("Wiseflow, make this an email."),
                         "Voice Flow, make this an email.")
        self.assertEqual(dictionary_engine.repair_wake_term("the voice with flow app"),
                         "the Voice Flow app")
        r = detect_voice_command(dictionary_engine.repair_wake_term("Wiseflow, make this an excited email. Launch Monday."))
        self.assertIsNotNone(r.command)
        self.assertEqual(r.command.format, "email")


class TestLearnedVocabularyStorage(unittest.TestCase):
    def _db(self):
        import tempfile
        from voice_flow.storage import StorageEngine

        path = os.path.join(tempfile.mkdtemp(), "lex.db")
        return StorageEngine(db_path=path)

    def test_candidate_promotes_and_appears_in_suggestions(self):
        st = self._db()
        self.assertFalse(st.record_lexicon_candidate("LangGraph", "land graph"))
        self.assertFalse(st.record_lexicon_candidate("LangGraph", "land graph"))
        self.assertTrue(st.record_lexicon_candidate("LangGraph", "land graph"))  # 3rd promotes
        items = st.get_lexicon_suggestions()
        self.assertEqual([i["term"] for i in items], ["LangGraph"])
        self.assertEqual(items[0]["evidence"], 3)

    def test_raw_candidates_do_not_surface(self):
        st = self._db()
        st.record_lexicon_candidate("Kubernetes", "coobernetees")
        self.assertEqual(st.get_lexicon_suggestions(), [])

    def test_approval_activates_dictionary_word(self):
        st = self._db()
        st.record_lexicon_candidate("LangGraph", "land graph")
        st.record_lexicon_candidate("LangGraph", "land graph")
        st.record_lexicon_candidate("LangGraph", "land graph")
        cid = st.get_lexicon_suggestions()[0]["id"]
        self.assertTrue(st.set_lexicon_candidate_state(cid, "active"))
        self.assertIn("LangGraph", st.get_dictionary_words())

    def test_migration_promotes_autocaptured_once(self):
        st = self._db()
        st.add_dictionary_word("GitHub", category="Auto-Captured")
        promoted = st.migrate_learned_vocabulary()
        self.assertGreaterEqual(promoted, 1)
        terms = [i["term"] for i in st.get_lexicon_suggestions()]
        self.assertIn("GitHub", terms)
        # idempotent
        self.assertEqual(st.migrate_learned_vocabulary(), 0)

    def test_migration_does_not_pollute_corrections_or_dictionary(self):
        st = self._db()
        st.migrate_learned_vocabulary()
        # Wake repairs are static patterns, not corrections/rows: storing them
        # would pollute STT hints and override user casing entries.
        self.assertEqual(st.get_dictionary_corrections(), [])


class TestCorrectionLearningExtraction(unittest.TestCase):
    def test_multiword_mishearing_yields_pair(self):
        from voice_flow.correction_learning import extract_correction_pairs

        pairs = extract_correction_pairs(
            "we will use land graph for the routing",
            "We will use LangGraph for the routing",
        )
        self.assertIn(("LangGraph", "land graph"), pairs)

    def test_sentence_capitalization_is_not_a_term(self):
        from voice_flow.correction_learning import extract_correction_pairs

        pairs = extract_correction_pairs(
            "hey joey we still on for coffee",
            "Hey Joey we still on for coffee",
        )
        self.assertEqual(pairs, [])

    def test_common_words_do_not_become_candidates(self):
        from voice_flow.correction_learning import extract_correction_pairs

        pairs = extract_correction_pairs(
            "send the meeting update today please",
            "Send the Meeting Update today please",
        )
        self.assertEqual(pairs, [])


class TestPolishRoutingQuality(unittest.TestCase):
    """The user's selected polish model must actually run (provider aliases),
    long dictations must not be served by the compressing lite model, and
    plain-dictation compression must be rejected."""

    LONG_TEXT = (
        "The issue where the message generation takes too much time has returned. "
        "Additionally it is completely altering the wording and the output quality is "
        "currently very poor and I am not satisfied with the output of the features. "
        "Please investigate and find a permanent solution for this so that regardless of "
        "the changes it makes it generates proper content for every request type. The main "
        "concern is that even when no specific instructions are provided the quality stays poor. "
    ) * 2

    def _polisher(self):
        from voice_flow import polisher as pmod
        return pmod.TextPolisher(), pmod

    def test_oauth_selection_never_aliases_to_a_gemini_api_key(self):
        pol, pmod = self._polisher()
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append((provider, model))
            return "polished output"

        with (
            patch.object(pmod.storage, "get_setting", side_effect=lambda k, d=None: "antigravity/gemini-3.7-flash" if k == "voice_flow_polish_model" else d),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pmod.storage, "get_all_provider_connections", return_value={}),
            patch("voice_flow.voice_polish_bridge.can_execute_model", return_value=True),
            patch("voice_flow.voice_polish_bridge.request_polish", return_value=None),
            patch.object(pol, "_try_provider_call", side_effect=fake_call),
        ):
            pol.polish(self.LONG_TEXT)
        self.assertEqual(calls, [])

    def test_long_transcript_skips_fast_lane(self):
        pol, pmod = self._polisher()
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            return "polished output"

        with (
            patch.object(pmod.storage, "get_setting", side_effect=lambda k, d=None: "antigravity/gemini-3.7-flash" if k == "voice_flow_polish_model" else d),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pmod.storage, "get_all_provider_connections", return_value={}),
            patch.object(pol, "_try_provider_call", side_effect=fake_call),
        ):
            pol.polish(self.LONG_TEXT)
        self.assertNotIn("gemini-3.5-flash-lite", calls)

    def test_plain_polish_rejects_compressed_output(self):
        pol, pmod = self._polisher()
        src = self.LONG_TEXT
        compressed = " ".join(src.split()[: len(src.split()) * 2 // 3])  # 33% loss

        def fake_pool(raw_text, saved_keys, style_instruction, **kwargs):
            return compressed

        with (
            patch.object(pmod.storage, "get_setting", return_value=True),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pol, "_polish_with_api_pool", side_effect=fake_pool),
        ):
            out = pol.polish(src)
        # The lossless deterministic fallback keeps every content word.
        for word in set(src.split()):
            if word.lower() not in {"um", "uh", "like"} and len(word) > 2:
                self.assertIn(word.lower().strip(".,!?"), out.lower())

    def test_command_transform_allows_restructure(self):
        pol, pmod = self._polisher()
        src = "we need to ship the installer first and then run the full test suite before the release"
        reformatted = "Objective: ship the installer. Then: run the full test suite before release."

        def fake_pool(raw_text, saved_keys, style_instruction, **kwargs):
            return reformatted

        with (
            patch.object(pmod.storage, "get_setting", return_value=True),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pol, "_polish_with_api_pool", side_effect=fake_pool),
            patch.object(pmod, "_candidate_preserves_content", return_value=True),
        ):
            out = pol.polish(src, force_ai=True)
        # The command transform is accepted under the lenient gate.
        self.assertIn("Objective", out)

    def test_short_transcript_uses_selected_model(self):
        pol, pmod = self._polisher()
        calls = []

        def fake_call(provider, key, system_prompt, user_content, model=None, timeout=None):
            calls.append(model)
            return "polished fast output"

        with (
            patch.object(pmod.storage, "get_setting", side_effect=lambda k, d=None: "gemini/gemini-3.7-flash" if k == "voice_flow_polish_model" else d),
            patch.object(pmod.storage, "get_all_api_keys", return_value={"gemini": "k"}),
            patch.object(pmod.storage, "get_all_provider_connections", return_value={}),
            patch.object(pol, "_try_provider_call", side_effect=fake_call),
        ):
            pol.polish("please polish this medium dictation text with a few more words")
        self.assertEqual(calls[0], "gemini-3.7-flash")



if __name__ == "__main__":
    unittest.main()
