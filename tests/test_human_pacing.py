"""Tests for human-like inter-sentence pause pacing in Audio Flow TTS.

Verifies:
1. _compute_pause_ms returns correct durations for each pause class.
2. classify_pause_after_sentence correctly maps sentences to pause classes.
3. strip_pause_markers removes all private-use pause characters.
4. format_document_structure_for_speech inserts pause markers at paragraph,
   section, and list-item boundaries.
5. Pause markers never leak into TTS synthesis text.
"""

from __future__ import annotations

from voice_flow.structured_reader import (
    PAUSE_PARAGRAPH,
    PAUSE_SECTION,
    PAUSE_LIST_ITEM,
    classify_pause_after_sentence,
    strip_pause_markers,
    format_document_structure_for_speech,
)
from voice_flow.tts_engine import TTSEngine


# ------------------------------------------------------------------
# _compute_pause_ms
# ------------------------------------------------------------------

def test_compute_pause_ms_sentence_boundary() -> None:
    """Regular sentence boundary should yield ~400ms."""
    ms = TTSEngine._compute_pause_ms("sentence")
    assert 300 <= ms <= 500, f"Expected 300-500ms for sentence, got {ms}"


def test_compute_pause_ms_paragraph_boundary() -> None:
    """Paragraph transition should yield ~820ms."""
    ms = TTSEngine._compute_pause_ms("paragraph")
    assert 700 <= ms <= 1000, f"Expected 700-1000ms for paragraph, got {ms}"


def test_compute_pause_ms_section_boundary() -> None:
    """Section/heading boundary should yield ~1100ms."""
    ms = TTSEngine._compute_pause_ms("section")
    assert 900 <= ms <= 1300, f"Expected 900-1300ms for section, got {ms}"


def test_compute_pause_ms_list_item_boundary() -> None:
    """List item boundary should yield ~300ms."""
    ms = TTSEngine._compute_pause_ms("list_item")
    assert 200 <= ms <= 400, f"Expected 200-400ms for list_item, got {ms}"


def test_compute_pause_ms_colon_boundary() -> None:
    """Colon lead-in should yield ~550ms."""
    ms = TTSEngine._compute_pause_ms("colon")
    assert 450 <= ms <= 650, f"Expected 450-650ms for colon, got {ms}"


def test_compute_pause_ms_unknown_defaults_to_sentence() -> None:
    """Unknown pause class falls back to sentence default."""
    ms = TTSEngine._compute_pause_ms("unknown_class")
    assert ms == TTSEngine._compute_pause_ms("sentence")


# ------------------------------------------------------------------
# classify_pause_after_sentence
# ------------------------------------------------------------------

def test_classify_section_marker() -> None:
    result = classify_pause_after_sentence(f"Section: Introduction.{PAUSE_SECTION}")
    assert result == "section"


def test_classify_paragraph_marker() -> None:
    result = classify_pause_after_sentence(f"This is a paragraph.{PAUSE_PARAGRAPH}")
    assert result == "paragraph"


def test_classify_list_item_marker() -> None:
    result = classify_pause_after_sentence(f"First, clean up the code.{PAUSE_LIST_ITEM}")
    assert result == "list_item"


def test_classify_colon_ending() -> None:
    result = classify_pause_after_sentence("Here is the structured breakdown:")
    assert result == "colon"


def test_classify_plain_sentence() -> None:
    result = classify_pause_after_sentence("The system processes audio in real time.")
    assert result == "sentence"


def test_classify_empty_sentence() -> None:
    result = classify_pause_after_sentence("")
    assert result == "sentence"


def test_classify_marker_anywhere_in_sentence() -> None:
    """Markers mid-sentence (after block join) are still detected."""
    result = classify_pause_after_sentence(f"End of block.{PAUSE_PARAGRAPH} Start of next block.")
    assert result == "paragraph"


# ------------------------------------------------------------------
# strip_pause_markers
# ------------------------------------------------------------------

def test_strip_removes_all_markers() -> None:
    text = f"Hello{PAUSE_SECTION} world{PAUSE_PARAGRAPH} foo{PAUSE_LIST_ITEM} bar"
    stripped = strip_pause_markers(text)
    assert PAUSE_SECTION not in stripped
    assert PAUSE_PARAGRAPH not in stripped
    assert PAUSE_LIST_ITEM not in stripped
    assert stripped == "Hello world foo bar"


def test_strip_preserves_normal_text() -> None:
    text = "This is perfectly normal text."
    assert strip_pause_markers(text) == text


# ------------------------------------------------------------------
# Pause markers in formatted output
# ------------------------------------------------------------------

def test_pause_markers_in_multi_paragraph_output() -> None:
    """Multiple paragraphs should be joined with PAUSE_PARAGRAPH markers."""
    raw = "First paragraph here.\n\nSecond paragraph here."
    result = format_document_structure_for_speech(raw)
    assert PAUSE_PARAGRAPH in result, "Expected PAUSE_PARAGRAPH marker between paragraphs"


def test_section_heading_gets_section_marker() -> None:
    """A standalone section heading block should have PAUSE_SECTION appended."""
    raw = "Document Title\n\nOverview\n\nSome content follows here."
    result = format_document_structure_for_speech(raw)
    assert PAUSE_SECTION in result, "Expected PAUSE_SECTION marker after section heading"


def test_bullet_list_gets_list_item_markers() -> None:
    """Bullet list items should have PAUSE_LIST_ITEM markers between them."""
    raw = "Header\n\n- First item\n- Second item\n- Third item"
    result = format_document_structure_for_speech(raw)
    assert PAUSE_LIST_ITEM in result, "Expected PAUSE_LIST_ITEM marker between bullet items"


def test_markers_stripped_before_synthesis() -> None:
    """After strip_pause_markers, no marker characters remain - safe for TTS."""
    raw = "# Main Title\n\nSome paragraph.\n\n## Sub Section\n\n- Item A\n- Item B"
    formatted = format_document_structure_for_speech(raw)
    # Verify markers exist in formatted output
    has_markers = PAUSE_SECTION in formatted or PAUSE_PARAGRAPH in formatted or PAUSE_LIST_ITEM in formatted
    assert has_markers, "Expected at least one pause marker in formatted output"
    # After stripping, no markers remain
    stripped = strip_pause_markers(formatted)
    assert PAUSE_SECTION not in stripped
    assert PAUSE_PARAGRAPH not in stripped
    assert PAUSE_LIST_ITEM not in stripped


def test_full_document_pipeline_splits_all_sentences_with_correct_pauses() -> None:
    """Full end-to-end pipeline: raw markdown splits into all distinct sentences with correct pause classes."""
    from voice_flow.structured_reader import split_spoken_sentences

    raw = (
        "# Main Title\n\n"
        "First paragraph with two sentences. Second sentence here.\n\n"
        "## Sub Section\n\n"
        "Another paragraph.\n\n"
        "- Item A\n"
        "- Item B"
    )
    formatted = format_document_structure_for_speech(raw)
    splits = split_spoken_sentences(formatted)

    assert len(splits) == 7, f"Expected 7 sentences, got {len(splits)}: {splits}"
    assert classify_pause_after_sentence(splits[0]) == "section"
    assert classify_pause_after_sentence(splits[1]) == "sentence"
    assert classify_pause_after_sentence(splits[2]) == "paragraph"
    assert classify_pause_after_sentence(splits[3]) == "section"
    assert classify_pause_after_sentence(splits[4]) == "paragraph"
    assert classify_pause_after_sentence(splits[5]) == "list_item"
    assert classify_pause_after_sentence(splits[6]) == "list_item"


def test_speed_scaling_of_pause_duration() -> None:
    """Pause duration scales inversely with reading speed."""
    from voice_flow.tts_engine import tts_engine
    from voice_flow.storage import storage

    try:
        # At 1.0x speed
        storage.save_setting("audio_flow_speed", 1.0)
        p1 = tts_engine._get_inter_sentence_pause_sec("sentence")
        assert 0.35 <= p1 <= 0.45

        # At 2.0x speed, pause should roughly halve
        storage.save_setting("audio_flow_speed", 2.0)
        p2 = tts_engine._get_inter_sentence_pause_sec("sentence")
        assert 0.18 <= p2 <= 0.25
        assert p2 < p1

        # At 0.5x speed, pause should roughly double
        storage.save_setting("audio_flow_speed", 0.5)
        p05 = tts_engine._get_inter_sentence_pause_sec("sentence")
        assert 0.70 <= p05 <= 0.90
        assert p05 > p1
    finally:
        storage.save_setting("audio_flow_speed", 1.0)

