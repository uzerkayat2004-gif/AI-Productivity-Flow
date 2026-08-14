"""On-Screen Progressive Yellow Text Highlight Overlay."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class YellowHighlightOverlay:
    """Provides visual on-screen progressive sentence highlighting during TTS playback."""

    def __init__(self) -> None:
        self._is_visible: bool = False
        self._percent: float = 0.0
        self._current_sentence_idx: int = 0
        self._total_sentences: int = 0
        self._current_sentence_text: str = ""

    def show(self) -> None:
        self._is_visible = True

    def hide(self) -> None:
        self._is_visible = False
        self._percent = 0.0

    def update_progress(self, sentence_idx: int, total_sentences: int, percent: float, text: str = "") -> None:
        self._current_sentence_idx = sentence_idx
        self._total_sentences = total_sentences
        self._percent = max(0.0, min(1.0, float(percent)))
        self._current_sentence_text = text


yellow_highlight_overlay = YellowHighlightOverlay()
