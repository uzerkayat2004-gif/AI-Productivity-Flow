"""Data models and typed error structures for the NotebookLM Video Flow provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_PROFILE = "video-flow-experiment"
DEFAULT_FORMAT = "brief"
DEFAULT_STYLE = "auto"
VIDEO_FORMATS: frozenset[str] = frozenset({"explainer", "brief", "cinematic", "short"})
VIDEO_STYLES: frozenset[str] = frozenset(
    {
        "auto",
        "custom",
        "classic",
        "whiteboard",
        "kawaii",
        "anime",
        "watercolor",
        "retro-print",
        "heritage",
        "paper-craft",
    }
)
TERMINAL_SUCCESS: frozenset[str] = frozenset({"completed", "ready", "done", "success"})
TERMINAL_FAILURE: frozenset[str] = frozenset({"failed", "cancelled", "removed", "deleted", "error"})


class NotebookLMVideoError(RuntimeError):
    """A typed failure at the NotebookLM provider seam."""

    def __init__(self, code: str, message: str, *, payload: Any = None) -> None:
        self.code = str(code or "NOTEBOOKLM_ERROR")
        self.error_code = self.code
        self.message = str(message)
        self.payload = payload
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class AuthStatus:
    status: str
    profile: str
    storage_path: str | None = None
    authenticated: bool = False
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def error_code(self) -> str | None:
        if not self.authenticated:
            if self.details.get("psidts_expired") or "expired" in str(self.message or "").lower():
                return "auth_expired"
            return "auth_failed"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profile": self.profile,
            "storage_path": self.storage_path,
            "authenticated": self.authenticated,
            "message": self.message,
            "error_code": self.error_code,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class NotebookRef:
    notebook_id: str
    title: str


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    title: str
    status: str
    source_type: str = "text"


@dataclass(frozen=True)
class VideoRequest:
    title: str
    prompt: str
    output_path: Path
    source_file: Path | None = None
    source_url: str | None = None
    source_text: str | None = None
    notebook_id: str | None = None
    source_id: str | None = None
    task_id: str | None = None
    format: str = DEFAULT_FORMAT
    style: str = DEFAULT_STYLE
    style_prompt: str | None = None
    language: str | None = None
    job_id: str = "notebooklm-video"
    timeout_seconds: int = 1_800
    profile: str = DEFAULT_PROFILE
    retain_notebook: bool = True
    reuse_workspace: bool = False
    allow_local_fallback: bool = True
    timings: Mapping[str, float] = field(default_factory=dict)
    document_profile: Mapping[str, Any] | None = None
    target_duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "prompt": self.prompt,
            "output_path": str(self.output_path),
            "source_file": str(self.source_file) if self.source_file else None,
            "source_url": self.source_url,
            "source_text": self.source_text,
            "notebook_id": self.notebook_id,
            "source_id": self.source_id,
            "task_id": self.task_id,
            "format": self.format,
            "style": self.style,
            "style_prompt": self.style_prompt,
            "language": self.language,
            "job_id": self.job_id,
            "timeout_seconds": self.timeout_seconds,
            "profile": self.profile,
            "retain_notebook": self.retain_notebook,
            "reuse_workspace": self.reuse_workspace,
            "allow_local_fallback": self.allow_local_fallback,
            "timings": dict(self.timings),
            "document_profile": dict(self.document_profile) if self.document_profile else None,
            "target_duration_seconds": self.target_duration_seconds,
        }

    def validate(self) -> None:
        if self.format not in VIDEO_FORMATS:
            raise NotebookLMVideoError("VALIDATION", f"Unsupported format '{self.format}'. Must be one of {sorted(VIDEO_FORMATS)}")
        if self.format not in {"cinematic", "short"}:
            if self.style not in VIDEO_STYLES:
                raise NotebookLMVideoError("VALIDATION", f"Unsupported style '{self.style}'. Must be one of {sorted(VIDEO_STYLES)}")
            if self.style == "custom" and (not self.style_prompt or not self.style_prompt.strip()):
                raise NotebookLMVideoError("VALIDATION", "style_prompt is required when style is 'custom'")
        if not self.notebook_id or not self.source_id:
            choices = [self.source_file is not None, bool(self.source_url), self.source_text is not None]
            if sum(choices) != 1:
                raise NotebookLMVideoError("VALIDATION", "Provide exactly one source_file, source_url, or source_text")


@dataclass(frozen=True)
class VideoArtifact:
    notebook_id: str
    task_id: str
    artifact_id: str
    status: str
    output_path: str | None = None
    artifact_url: str | None = None
    format: str = DEFAULT_FORMAT
    style: str | None = None
    profile: str = DEFAULT_PROFILE
    provenance_path: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    timings: Mapping[str, float] = field(default_factory=dict)
    document_profile: Mapping[str, Any] | None = None
    fallback: bool = False
    target_duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "notebook_id": self.notebook_id,
            "task_id": self.task_id,
            "artifact_id": self.artifact_id,
            "status": self.status,
            "output_path": self.output_path,
            "artifact_url": self.artifact_url,
            "format": self.format,
            "style": self.style,
            "profile": self.profile,
            "provenance_path": self.provenance_path,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "timings": dict(self.timings),
            "document_profile": dict(self.document_profile) if self.document_profile else None,
            "fallback": self.fallback,
            "target_duration_seconds": self.target_duration_seconds,
        }
