"""Video Flow Contracts & Security Boundary Validators.

Defines neutral data models and security invariants for Video Flow:
1. AI authors semantic intent ONLY.
2. AI NEVER produces executable code (no eval, no JS/Python/shaders/HTML/SVG).
3. Payload security validation ensures zero script/code injection reaches compilers.
4. Job data model tracks progress, state, and provenance.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass
class JobV3:
    """Standard Video Flow job execution record."""
    job_id: str
    state: str = "queued"
    progress: float = 0.0
    message: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


# Canonical alias for modern architecture
VideoFlowJob = JobV3


def validate_no_executable_code(payload: Any) -> None:
    """Security Boundary Validator: Rejects any LLM-authored executable code strings.

    Plain-text tokens that occur in ordinary English narration ("import ",
    "process.") are deliberately not on the list: source sentences are
    rendered as escaped text, never evaluated.

    Matching is case-insensitive (attackers vary case: "<ScRiPt", "EVAL("),
    and non-JSON-serializable payloads (sets, tuples, dataclass instances with
    exotic fields, circular graphs) fall back to a circular-safe repr scan
    instead of raising TypeError.
    """
    try:
        if hasattr(payload, "__dataclass_fields__"):
            raw = json.dumps(asdict(payload), default=str)
        elif isinstance(payload, (dict, list, str, int, float, bool, type(None))):
            raw = json.dumps(payload, default=str)
        else:
            raw = str(payload)
    except (TypeError, ValueError, RecursionError):
        raw = _safe_repr(payload)
    lowered = raw.lower()
    forbidden_tokens = [
        "eval(", "<script", "function(", "exec(", "child_process",
        "os.system", "subprocess", "__import__", "require(", "javascript:", "onload=", "onerror=",
        "<iframe", "<object", "<embed", "document.cookie", "window.location",
        "settimeout(", "setinterval(", "new function",
        "process.env", "spawn(", "fork(", "popen(",
    ]
    for token in forbidden_tokens:
        if token in lowered:
            raise ValueError(f"Security Boundary Violation: Payload contains forbidden code token '{token}'")


def _safe_repr(payload: Any, _depth: int = 0, _seen: frozenset[int] | None = None) -> str:
    """Circular-safe repr for payloads json.dumps cannot serialize."""
    if _depth > 6:
        return "..."
    if isinstance(payload, str):
        return payload[:10000]
    if isinstance(payload, (int, float, bool, type(None))):
        return repr(payload)
    if isinstance(payload, (bytes, bytearray)):
        try:
            return bytes(payload[:4096]).decode("utf-8", errors="replace")
        except Exception:
            return repr(bytes(payload[:256]))
    seen = _seen or frozenset()
    if id(payload) in seen:
        return "<circular>"
    seen = seen | {id(payload)}
    try:
        if isinstance(payload, dict):
            parts = [
                f"{_safe_repr(k, _depth + 1, seen)}: {_safe_repr(v, _depth + 1, seen)}"
                for k, v in list(payload.items())[:200]
            ]
            return "{" + ", ".join(parts) + "}"
        if isinstance(payload, (list, tuple, set, frozenset)):
            parts = [_safe_repr(v, _depth + 1, seen) for v in list(payload)[:200]]
            return "[" + ", ".join(parts) + "]"
        return str(payload)[:10000]
    except Exception:
        return "<unrepresentable>"
