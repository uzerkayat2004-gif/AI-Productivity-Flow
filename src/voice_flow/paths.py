"""Filesystem locations for Voice Flow runtime data."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Return the runtime data directory, with an opt-in test/portable override."""
    override = os.environ.get("VOICE_FLOW_DATA_DIR")
    return Path(override).expanduser() if override else Path.home() / ".voice_flow"
