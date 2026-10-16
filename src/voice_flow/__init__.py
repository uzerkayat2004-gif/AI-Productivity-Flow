"""AI Productivity Flow — Desktop AI system for Windows and macOS."""

import os
import sys

if sys.platform == "win32":
    # Bound native BLAS thread memory before any dependency imports NumPy.
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from voice_flow._version import VERSION, __version__
from voice_flow.local_summarizer import LocalSpokenSummarizer, local_spoken_summarizer

__all__ = ["LocalSpokenSummarizer", "local_spoken_summarizer", "__version__", "VERSION"]
