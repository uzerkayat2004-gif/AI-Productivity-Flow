"""Voice Flow — Wispr Flow-like voice dictation for Windows."""

__version__ = "1.0.0"

from voice_flow.local_summarizer import LocalSpokenSummarizer, local_spoken_summarizer

__all__ = ["LocalSpokenSummarizer", "local_spoken_summarizer", "__version__"]
