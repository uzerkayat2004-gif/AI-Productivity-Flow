"""Per-job filesystem isolation for Video Flow generation."""

from __future__ import annotations

import re
from pathlib import Path

_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_JOB_SUBDIRS = ("plan", "storyboard", "narova", "audio", "captions", "temp", "logs", "export")


class EngineError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def prepare_job_directory(
    job_id: str,
    *,
    projects_root: Path | None = None,
    project_dir: Path | None = None,
) -> Path:
    if not _SAFE_JOB_ID.fullmatch(job_id) or job_id in {".", ".."}:
        raise EngineError("invalid_job_id", "Job ID contains unsafe path characters")

    root = Path(projects_root or Path.home() / ".voice_flow" / "v3_projects").resolve()
    if project_dir is not None:
        destination = Path(project_dir).resolve()
        if destination.parent != root or destination.name != job_id:
            raise EngineError("invalid_project_dir", "Project directory must be the named job inside projects_root")
    else:
        destination = (root / job_id).resolve()
        if destination.parent != root:
            raise EngineError("invalid_job_id", "Job directory escapes the projects root")

    destination.mkdir(parents=True, exist_ok=True)
    for name in _JOB_SUBDIRS:
        (destination / name).mkdir(exist_ok=True)
    return destination


