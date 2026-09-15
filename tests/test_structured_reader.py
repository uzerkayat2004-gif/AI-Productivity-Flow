"""Unit tests for Conversational Human Explainer & Narrator Engine."""

import unittest
from voice_flow.structured_reader import (
    process_arrow_pipeline_human,
    format_document_structure_for_speech,
    is_table_layout,
    format_table_for_speech,
    split_spoken_sentences,
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

    def test_spoken_times_currencies_and_metrics(self):
        raw = "The release call is at 14:30. Price is $49.99 with $2.5M ARR, 15% discount, and 120ms latency on 16GB RAM."
        formatted = format_document_structure_for_speech(raw)
        self.assertIn("2:30 PM", formatted)
        self.assertIn("49 dollars and 99 cents", formatted)
        self.assertIn("2.5 million dollars", formatted)
        self.assertIn("15 percent", formatted)
        self.assertIn("120 milliseconds", formatted)
        self.assertIn("16 gigabytes", formatted)

    def test_extended_ordinals_beyond_fifteen(self):
        items = "\n".join([f"- Feature item number {i+1}" for i in range(25)])
        formatted = format_document_structure_for_speech(items)
        self.assertIn("First, Feature item number 1.", formatted)
        self.assertIn("Fifteenth, Feature item number 15.", formatted)
        self.assertIn("Sixteenth, Feature item number 16.", formatted)
        self.assertIn("Twenty-First, Feature item number 21.", formatted)
        self.assertIn("Twenty-Fifth, Feature item number 25.", formatted)

    def test_markdown_links_and_comparisons_speech(self):
        raw = "Check [Documentation](https://voiceflow.ai/docs). If retries != 0 && speed >= 2x, run at 1920x1080."
        formatted = format_document_structure_for_speech(raw)
        self.assertIn("Check Documentation.", formatted)
        self.assertIn("retries is not equal to 0 and speed is greater than or equal to 2 times", formatted)
        self.assertIn("1920 by 1080", formatted)

    def test_split_spoken_sentences_abbreviations_and_decimals(self):
        text = (
            "Dr. Smith visited Washington, D.C. on Jan. 15 to discuss the U.S. economy with Mr. Davis (e.g., inflation vs. growth). "
            "The estimated budget deficit reached $3.14 trillion, representing a 4.5% year-over-year increase. "
            "President George W. Bush signed earlier legislation. "
            '"We delivered 100% reliability," confirmed Dr. Adams. '
            "Finally, the project completed on schedule."
        )
        sentences = split_spoken_sentences(text)
        self.assertEqual(len(sentences), 5)
        self.assertIn("Dr. Smith visited Washington, D.C. on Jan. 15", sentences[0])
        self.assertIn("$3.14 trillion", sentences[1])
        self.assertIn("George W. Bush", sentences[2])
        self.assertIn('"We delivered 100% reliability," confirmed Dr. Adams.', sentences[3])
        self.assertEqual(sentences[4], "Finally, the project completed on schedule.")


if __name__ == "__main__":
    unittest.main()

