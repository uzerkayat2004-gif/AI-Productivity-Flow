"""AI Productivity Flow — Desktop AI system for Windows and macOS."""

from voice_flow._version import VERSION, __version__
from voice_flow.local_summarizer import LocalSpokenSummarizer, local_spoken_summarizer

__all__ = ["LocalSpokenSummarizer", "local_spoken_summarizer", "__version__", "VERSION"]
