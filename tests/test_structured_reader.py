"""Unit tests for Conversational Human Explainer & Narrator Engine."""

import unittest
from voice_flow.structured_reader import (
    process_arrow_pipeline_human,
    format_document_structure_for_speech,
    is_table_layout,
    format_table_for_speech,
)


class TestStructuredReaderExplainer(unittest.TestCase):

    def test_spoken_date_formatting(self):
        text = "Research date: 2026-08-04"
        formatted = format_document_structure_for_speech(text)
        self.assertIn("August 4th, 2026", formatted)

    def test_human_arrow_pipeline(self):
        raw = "idea → plan → recording → editor → variants → approval → publication → analytics → revenue → reuse"
        formatted = process_arrow_pipeline_human(raw)
        self.assertIn("starting with idea, moving to plan, then recording, then editor, then variants, then approval, then publication, then analytics, then revenue, and finally reuse.", formatted)

    def test_conversational_list_ordinals(self):
        raw = """- Small creators need a repeatable way to finish.
- Growing creators need to increase output.
- Professional creators need reliable handoffs."""
        formatted = format_document_structure_for_speech(raw)
        self.assertIn("First, Small creators need a repeatable way to finish.", formatted)
        self.assertIn("Second, Growing creators need to increase output.", formatted)
        self.assertIn("Third, Professional creators need reliable handoffs.", formatted)

    def test_title_and_section_intros(self):
        raw = """Global Creator Needs Research: Problems, Requested Tools, and Maturity Map

Research date: 2026-08-04
Scope: Online content creators across video and social.

Executive conclusion

Creators do not share one universal problem."""

        formatted = format_document_structure_for_speech(raw)
        self.assertIn("Document Title: Global Creator Needs Research: Problems, Requested Tools, and Maturity Map.", formatted)
        self.assertIn("Research date: August 4th, 2026.", formatted)
        self.assertIn("Section: Executive conclusion.", formatted)

    def test_normal_paragraph_no_title(self):
        raw = "Creators do not share one universal problem. Their needs change sharply with operating maturity."
        formatted = format_document_structure_for_speech(raw)
        self.assertNotIn("Document Title:", formatted)
        self.assertEqual(formatted, raw)


if __name__ == "__main__":
    unittest.main()
