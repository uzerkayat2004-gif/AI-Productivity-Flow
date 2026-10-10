"""Provenance tracking, technical media inspection, and secret redaction for NotebookLM."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import NotebookLMVideoError, SourceRef, VideoArtifact, VideoRequest

logger = logging.getLogger(__name__)
PROVIDER_VERSION = "notebooklm-py==0.8.1"


def sha256_hash(text_or_bytes: str | bytes) -> str:
    data = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes
    return hashlib.sha256(data).hexdigest()


def probe_media_file(path: Path | str) -> dict[str, Any]:
    """Run ffprobe safely on a media artifact to extract technical streams info."""
    path_obj = Path(path).resolve()
    if not path_obj.is_file() or path_obj.stat().st_size <= 0:
        return {}
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,duration,r_frame_rate",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path_obj),
        ]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "check": False,
            "timeout": 15,
        }
        import os
        import sys
        if os.name == "nt" or sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(cmd, **kwargs)
        if res.returncode != 0:
            return {}
        info = json.loads(res.stdout)
        streams = info.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        format_info = info.get("format", {})
        
        duration = float(format_info.get("duration") or video_stream.get("duration") or 0.0)
        return {
            "duration_seconds": duration,
            "width": int(video_stream.get("width") or 0) or None,
            "height": int(video_stream.get("height") or 0) or None,
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": audio_stream.get("codec_name"),
            "r_frame_rate": video_stream.get("r_frame_rate"),
            "size_bytes": int(format_info.get("size") or path_obj.stat().st_size),
        }
    except Exception as exc:
        logger.debug("ffprobe failed on %s: %s", path_obj, exc)
        return {"size_bytes": path_obj.stat().st_size}


def redact_secrets(obj: Any) -> Any:
    """Recursively scrub any sensitive keys or values from metadata."""
    if isinstance(obj, Mapping):
        clean = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(secret in k_lower for secret in ("cookie", "token", "auth", "secret", "password", "bearer", "credential")):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = redact_secrets(v)
        return clean
    elif isinstance(obj, list):
        return [redact_secrets(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_secrets(item) for item in obj)
    elif isinstance(obj, str):
        if any(secret in obj.lower() for secret in ("bearer ", "session_id=", "auth_token=")):
            return "[REDACTED_TEXT]"
        return obj
    return obj


def write_notebooklm_provenance(
    project_dir: Path,
    request: VideoRequest,
    artifact: VideoArtifact | None,
    *,
    source: SourceRef | None = None,
    started_at: str,
    error: NotebookLMVideoError | Exception | None = None,
    timings: Mapping[str, float] | None = None,
    document_profile: Mapping[str, Any] | None = None,
) -> Path:
    """Write sanitized production provenance record for NotebookLM video job."""
    prov_dir = project_dir / "provenance"
    prov_dir.mkdir(parents=True, exist_ok=True)
    prov_path = prov_dir / "production-provenance.json"
    prov_json_path = prov_dir / "provenance.json"

    source_type = "unknown"
    source_hash = ""
    if request.source_file:
        source_type = "file"
        try:
            source_hash = sha256_hash(Path(request.source_file).read_bytes())
        except Exception:
            pass
    elif request.source_url:
        source_type = "url"
        source_hash = sha256_hash(request.source_url)
    elif request.source_text:
        source_type = "text"
        source_hash = sha256_hash(request.source_text)

    media_info = {}
    if artifact and artifact.output_path and Path(artifact.output_path).is_file():
        media_info = probe_media_file(artifact.output_path)

    resolved_timings: dict[str, float] = {}
    if timings:
        resolved_timings = dict(timings)
    elif artifact and getattr(artifact, "timings", None):
        resolved_timings = dict(artifact.timings)
    elif request and getattr(request, "timings", None):
        resolved_timings = dict(request.timings)

    resolved_profile: dict[str, Any] | None = None
    if document_profile:
        resolved_profile = dict(document_profile)
    elif artifact and getattr(artifact, "document_profile", None):
        resolved_profile = dict(artifact.document_profile)
    elif request and getattr(request, "document_profile", None):
        resolved_profile = dict(request.document_profile)

    # Additively persist duration keys in document_profile (never dropping existing keys).
    _target_duration = getattr(request, "target_duration_seconds", None)
    if _target_duration is None and artifact is not None:
        _target_duration = getattr(artifact, "target_duration_seconds", None)
    if _target_duration is None and resolved_profile:
        _target_duration = resolved_profile.get("target_duration_seconds")
    _actual_duration = media_info.get("duration_seconds")
    if _actual_duration is None and artifact is not None:
        _actual_duration = getattr(artifact, "duration_seconds", None)
    _undershoot: float | None = None
    try:
        if _target_duration is not None and _actual_duration is not None:
            _undershoot = float(_target_duration) - float(_actual_duration)
    except (TypeError, ValueError):
        _undershoot = None
    if _target_duration is not None or _actual_duration is not None or _undershoot is not None:
        if resolved_profile is None:
            resolved_profile = {}
        else:
            resolved_profile = dict(resolved_profile)
        if _target_duration is not None and "target_duration_seconds" not in resolved_profile:
            resolved_profile["target_duration_seconds"] = _target_duration
        if _actual_duration is not None and "duration_actual_seconds" not in resolved_profile:
            resolved_profile["duration_actual_seconds"] = _actual_duration
        if _undershoot is not None and "duration_undershoot" not in resolved_profile:
            resolved_profile["duration_undershoot"] = _undershoot

    fallback_flag = bool(getattr(artifact, "fallback", False)) if artifact else False

    provenance_record = {
        "version": "2.1",
        "provider": "notebooklm",
        "provider_package": PROVIDER_VERSION,
        "job_id": request.job_id,
        "profile": request.profile,
        "requested_format": request.format,
        "requested_style": request.style,
        "language": request.language,
        "notebook_id": artifact.notebook_id if artifact else request.notebook_id,
        "source_id": source.source_id if source else request.source_id,
        "source_type": source_type,
        "source_hash": source_hash,
        "task_id": artifact.task_id if artifact else request.task_id,
        "artifact_id": artifact.artifact_id if artifact else None,
        "status": artifact.status if artifact else ("failed" if error else "unknown"),
        "output_path": str(artifact.output_path) if artifact and artifact.output_path else None,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "media": media_info,
        "timings": resolved_timings,
        "document_profile": resolved_profile,
        "fallback": fallback_flag,
        "error": {
            "code": getattr(error, "code", type(error).__name__) if error else None,
            "message": str(error) if error else None,
        } if error else None,
    }

    sanitized = redact_secrets(provenance_record)
    content = json.dumps(sanitized, indent=2, ensure_ascii=False)
    prov_path.write_text(content, encoding="utf-8")
    prov_json_path.write_text(content, encoding="utf-8")
    return prov_path
