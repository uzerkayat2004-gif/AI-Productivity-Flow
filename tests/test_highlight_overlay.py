"""Unit tests for On-Screen Progressive Yellow Text Highlight Overlay."""

import unittest
from voice_flow.highlight_overlay import YellowHighlightOverlay


class TestYellowHighlightOverlay(unittest.TestCase):

    def test_overlay_initialization(self):
        overlay = YellowHighlightOverlay()
        self.assertFalse(overlay._is_visible)
        self.assertEqual(overlay._percent, 0.0)

    def test_progress_calculation(self):
        overlay = YellowHighlightOverlay()
        overlay.update_progress(sentence_idx=2, total_sentences=5, percent=0.6)
        self.assertEqual(overlay._current_sentence_idx, 2)
        self.assertEqual(overlay._total_sentences, 5)
        self.assertEqual(overlay._percent, 0.6)


if __name__ == "__main__":
    unittest.main()
