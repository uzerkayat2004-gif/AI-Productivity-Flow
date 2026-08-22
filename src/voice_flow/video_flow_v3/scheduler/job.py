"""Generic job tracking — no engine logic.

Future engine should reuse this for progress/cancellation.
Not imported by placeholder engine; kept for boundary completeness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class JobV3:
    job_id: str
    state: str = "queued"
    progress: float = 0.0
    message: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
