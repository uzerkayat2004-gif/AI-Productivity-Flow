"""Per-job filesystem isolation for Video Flow generation."""

from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_JOB_SUBDIRS = ("plan", "storyboard", "narova", "audio", "captions", "temp", "logs", "export")
_RESERVED_WINDOWS = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


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
    # Windows reserved device names (CON, NUL, COM1…) resolve outside the
    # directory tree or to devices: reject even with an extension/suffix.
    stem = job_id.split(".")[0].lower()
    if stem in _RESERVED_WINDOWS:
        raise EngineError("invalid_job_id", "Job ID uses a reserved device name")

    root = Path(projects_root or Path.home() / ".voice_flow" / "v3_projects").resolve()
    if project_dir is not None:
        destination = Path(project_dir).resolve()
        if destination.parent != root or destination.name != job_id:
            raise EngineError("invalid_project_dir", "Project directory must be the named job inside projects_root")
    else:
        destination = (root / job_id).resolve()
        if destination.parent != root:
            raise EngineError("invalid_job_id", "Job directory escapes the projects root")

    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EngineError("invalid_project_dir", f"Could not create job directory: {exc}") from exc
    # Re-resolve after creation: a pre-existing symlink at the job path
    # would otherwise redirect all job I/O outside projects_root.
    try:
        if not destination.is_dir() or destination.resolve() != destination or os.path.islink(destination):
            raise EngineError("invalid_project_dir", "Project directory must be a real directory inside projects_root")
    except EngineError:
        raise
    except OSError as exc:
        raise EngineError("invalid_project_dir", f"Could not verify job directory: {exc}") from exc
    for name in _JOB_SUBDIRS:
        (destination / name).mkdir(exist_ok=True)
    return destination


def confined_path(job_dir: Path, *parts: str) -> Path:
    """Resolve ``parts`` under ``job_dir`` and prove containment.

    All job file I/O should route through here so a traversal in a scene
    title, voice id, or artifact name can never escape the per-job dir.
    """
    root = Path(job_dir).resolve()
    target = root.joinpath(*[str(part) for part in parts]).resolve()
    if target != root and root not in target.parents:
        raise EngineError("invalid_project_dir", "Job file path escapes the job directory")
    return target


