"""Explicit, job-relative provenance for Video Flow V2.1 production.

V2.1 may produce diagnostic attempt artifacts before a later failure selects
V1 or the portable renderer.  This module makes the final engine and artifact
status unambiguous without allowing model data to create paths outside the
job directory.  It has no dependency on the production engine and is safe to
use from both success and fallback paths.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping


class ProductionProvenanceError(ValueError):
    """Raised when provenance is inconsistent or an artifact path is unsafe."""


PROVENANCE_VERSION = "2.1"
ENGINE_V21 = "visual-v2.1"
ENGINE_V2 = "visual-v2"
ENGINE_V1 = "visual-v1"
ENGINE_PORTABLE = "portable-v1"
ENGINE_NAMES = (ENGINE_V21, ENGINE_V2, ENGINE_V1, ENGINE_PORTABLE)

ATTEMPT_STATUSES = ("not_started", "attempted", "running", "succeeded", "failed", "cancelled")
FINAL_STATUSES = ("pending", "final", "failed", "cancelled")
ARTIFACT_STATUSES = ("attempted", "final")
FALLBACK_STAGES = ("planning", "capability_validation", "compile", "render", "browser", "portable_render", "cancellation")

_ENGINE_ALIASES = {
    "v21": ENGINE_V21,
    "v2.1": ENGINE_V21,
    "visual_v2_1": ENGINE_V21,
    "v2": ENGINE_V2,
    "visual_v2": ENGINE_V2,
    "v1": ENGINE_V1,
    "visual_v1": ENGINE_V1,
    "portable": ENGINE_PORTABLE,
    "portable_v1": ENGINE_PORTABLE,
}
_SAFE_REASON = re.compile(r"^[^\x00-\x1f<>]{1,240}$")


def _engine(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionProvenanceError(f"{name} must be a non-empty engine name")
    raw = value.strip().casefold().replace("/", "_").replace("-", "_")
    canonical = _ENGINE_ALIASES.get(raw, value.strip())
    if canonical not in ENGINE_NAMES:
        raise ProductionProvenanceError(f"Unsupported {name}: {value!r}")
    return canonical


def _status(value: Any, values: Iterable[str], name: str) -> str:
    if not isinstance(value, str):
        raise ProductionProvenanceError(f"{name} must be a string")
    canonical = value.strip().casefold().replace("-", "_")
    # Accept common integration spellings but always serialize one canonical
    # status vocabulary so stale artifacts cannot masquerade as final output.
    aliases = {"attempt": "attempted", "complete": "succeeded", "completed": "succeeded", "success": "succeeded"}
    if name == "final_status":
        aliases.update({"complete": "final", "completed": "final", "success": "final", "succeeded": "final"})
    canonical = aliases.get(canonical, canonical)
    allowed = set(values)
    if canonical not in allowed:
        raise ProductionProvenanceError(f"Unsupported {name}: {value!r}")
    return canonical


def _reason(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ProductionProvenanceError(f"{name} must be a string")
    value = value.strip()
    if not _SAFE_REASON.fullmatch(value) or len(value) > 240:
        raise ProductionProvenanceError(f"{name} contains unsafe or oversized text")
    lowered = value.casefold()
    if any(fragment in lowered for fragment in ("api_key", "secret", "token", "password", "sk-")):
        raise ProductionProvenanceError(f"{name} must not contain credentials")
    return value


def _relative_path(value: Any, name: str = "artifact path") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductionProvenanceError(f"{name} must be a non-empty relative path")
    raw = value.strip().replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or raw.startswith("//"):
        raise ProductionProvenanceError(f"{name} must be job-relative")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProductionProvenanceError(f"{name} contains an unsafe traversal")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", part) for part in path.parts):
        raise ProductionProvenanceError(f"{name} contains an unsafe path component")
    return path.as_posix()


@dataclass(frozen=True)
class ArtifactProvenanceV21:
    """A path marker whose path is always relative to the job root."""

    path: str
    status: str
    kind: str = "json"

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _relative_path(self.path))
        object.__setattr__(self, "status", _status(self.status, ARTIFACT_STATUSES, "artifact status"))
        if not isinstance(self.kind, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", self.kind):
            raise ProductionProvenanceError("artifact kind must be a bounded identifier")

    @property
    def is_final(self) -> bool:
        return self.status == "final"

    @property
    def relative_path(self) -> str:
        return self.path

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "status": self.status, "kind": self.kind}


ArtifactRecordV21 = ArtifactProvenanceV21


@dataclass(frozen=True)
class ProductionProvenanceV21:
    """Final truth about which engine produced a job's output."""

    requested_engine: str = ENGINE_V21
    final_engine: str | None = None
    fallback_used: bool = False
    fallback_stage: str | None = None
    fallback_reason: str | None = None
    attempt_status: str = "attempted"
    final_status: str = "pending"
    attempt_artifacts: tuple[ArtifactProvenanceV21, ...] = ()
    final_artifacts: tuple[ArtifactProvenanceV21, ...] = ()
    evaluation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_engine", _engine(self.requested_engine, "requested_engine"))
        if self.final_engine is not None:
            object.__setattr__(self, "final_engine", _engine(self.final_engine, "final_engine"))
        object.__setattr__(self, "attempt_status", _status(self.attempt_status, ATTEMPT_STATUSES, "attempt_status"))
        object.__setattr__(self, "final_status", _status(self.final_status, FINAL_STATUSES, "final_status"))
        if self.fallback_stage is not None:
            stage = self.fallback_stage.strip().casefold().replace("-", "_") if isinstance(self.fallback_stage, str) else ""
            if stage not in FALLBACK_STAGES:
                raise ProductionProvenanceError(f"Unsupported fallback_stage: {self.fallback_stage!r}")
            object.__setattr__(self, "fallback_stage", stage)
        if self.fallback_reason is not None:
            object.__setattr__(self, "fallback_reason", _reason(self.fallback_reason, "fallback_reason"))
        attempt = tuple(self.attempt_artifacts)
        final = tuple(self.final_artifacts)
        if any(not isinstance(item, ArtifactProvenanceV21) for item in (*attempt, *final)):
            raise ProductionProvenanceError("artifact entries must be ArtifactProvenanceV21 values")
        if any(item.status != "attempted" for item in attempt):
            raise ProductionProvenanceError("attempt_artifacts must be marked attempted")
        if any(item.status != "final" for item in final):
            raise ProductionProvenanceError("final_artifacts must be marked final")
        object.__setattr__(self, "attempt_artifacts", attempt)
        object.__setattr__(self, "final_artifacts", final)
        if self.final_status == "cancelled":
            if self.final_engine is not None or self.fallback_used:
                raise ProductionProvenanceError("cancelled jobs cannot claim a final engine or fallback")
            if self.attempt_status != "cancelled":
                raise ProductionProvenanceError("cancelled jobs require attempt_status=cancelled")
        elif self.final_status == "final" and self.final_engine is None:
            raise ProductionProvenanceError("final jobs require final_engine")
        if self.fallback_used:
            if self.final_engine == self.requested_engine:
                raise ProductionProvenanceError("fallback_used cannot be true when engines match")
            if not self.fallback_stage or not self.fallback_reason:
                raise ProductionProvenanceError("fallback requires stage and reason")
        elif self.fallback_stage is not None or self.fallback_reason is not None:
            raise ProductionProvenanceError("fallback stage/reason require fallback_used=true")
        if self.final_engine is not None and self.final_engine != self.requested_engine and not self.fallback_used:
            raise ProductionProvenanceError("different final engine must be marked as fallback")

    @property
    def final(self) -> bool:
        return self.final_status == "final"

    @property
    def is_cancelled(self) -> bool:
        return self.final_status == "cancelled"

    @property
    def attempted_engine(self) -> str:
        return self.requested_engine

    @property
    def final_artifact_paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.final_artifacts)

    def with_attempt_artifact(self, path: str, *, kind: str = "json") -> "ProductionProvenanceV21":
        item = ArtifactProvenanceV21(path, "attempted", kind)
        return replace(self, attempt_artifacts=(*self.attempt_artifacts, item))

    def with_final_artifact(self, path: str, *, kind: str = "json") -> "ProductionProvenanceV21":
        item = ArtifactProvenanceV21(path, "final", kind)
        return replace(self, final_artifacts=(*self.final_artifacts, item))

    def complete(self, *, final_engine: str | None = None) -> "ProductionProvenanceV21":
        engine = self.requested_engine if final_engine is None else _engine(final_engine, "final_engine")
        if engine != self.requested_engine:
            raise ProductionProvenanceError("use fallback() when final engine differs")
        return replace(self, final_engine=engine, attempt_status="succeeded", final_status="final")

    def fallback(self, *, final_engine: str, stage: str, reason: str) -> "ProductionProvenanceV21":
        engine = _engine(final_engine, "final_engine")
        if engine == self.requested_engine:
            raise ProductionProvenanceError("fallback final_engine must differ from requested_engine")
        return replace(
            self,
            final_engine=engine,
            fallback_used=True,
            fallback_stage=stage,
            fallback_reason=reason,
            attempt_status="failed",
            final_status="final",
        )

    def fail_terminal(self, *, stage: str | None = None, reason: str | None = None) -> "ProductionProvenanceV21":
        """Close an attempt as failed with no claimed final engine."""

        if self.final_status == "cancelled":
            raise ProductionProvenanceError("cancelled jobs cannot transition to failed")
        if self.fallback_used:
            resolved_stage = stage or self.fallback_stage or "render"
            resolved_reason = reason or self.fallback_reason or "fallback_failed"
            return replace(
                self,
                final_engine=None,
                fallback_used=True,
                fallback_stage=resolved_stage,
                fallback_reason=resolved_reason,
                attempt_status="failed",
                final_status="failed",
                final_artifacts=(),
            )
        return replace(
            self,
            final_engine=None,
            fallback_used=False,
            fallback_stage=None,
            fallback_reason=None,
            attempt_status="failed",
            final_status="failed",
            final_artifacts=(),
        )

    def failed_terminal(self, *, stage: str | None = None, reason: str | None = None) -> "ProductionProvenanceV21":
        return self.fail_terminal(stage=stage, reason=reason)

    def cancel(self) -> "ProductionProvenanceV21":
        return replace(self, final_engine=None, fallback_used=False, fallback_stage=None, fallback_reason=None, attempt_status="cancelled", final_status="cancelled")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "version": PROVENANCE_VERSION,
            "requested_engine": self.requested_engine,
            "final_engine": self.final_engine,
            "fallback_used": self.fallback_used,
            "fallback_stage": self.fallback_stage,
            "fallback_reason": self.fallback_reason,
            "attempt_status": self.attempt_status,
            "final_status": self.final_status,
            "attempt_artifacts": [item.to_dict() for item in self.attempt_artifacts],
            "final_artifacts": [item.to_dict() for item in self.final_artifacts],
        }
        if self.evaluation is not None:
            result["evaluation"] = self.evaluation
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n"


ProductionProvenance = ProductionProvenanceV21


def new_provenance(requested_engine: str = ENGINE_V21) -> ProductionProvenanceV21:
    return ProductionProvenanceV21(requested_engine=requested_engine)


def successful_provenance(requested_engine: str = ENGINE_V21) -> ProductionProvenanceV21:
    return new_provenance(requested_engine).complete()


def fallback_provenance(
    requested_engine: str = ENGINE_V21,
    *,
    final_engine: str = ENGINE_V1,
    fallback_stage: str = "compile",
    fallback_reason: str = "unsupported_capability",
) -> ProductionProvenanceV21:
    return new_provenance(requested_engine).fallback(final_engine=final_engine, stage=fallback_stage, reason=fallback_reason)


def cancelled_provenance(requested_engine: str = ENGINE_V21) -> ProductionProvenanceV21:
    return new_provenance(requested_engine).cancel()


def failed_terminal_provenance(
    provenance: ProductionProvenanceV21 | None = None,
    *,
    requested_engine: str = ENGINE_V21,
    stage: str | None = None,
    reason: str | None = None,
) -> ProductionProvenanceV21:
    current = new_provenance(requested_engine) if provenance is None else provenance
    return current.fail_terminal(stage=stage, reason=reason)


fallback_failed_provenance = failed_terminal_provenance


# Explicit helper spellings used by engine integration layers.
new_production_provenance = new_provenance
mark_v21_success = successful_provenance
mark_v1_fallback = fallback_provenance
mark_cancelled = cancelled_provenance
mark_failed_terminal = failed_terminal_provenance


def record_attempt_artifact(provenance: ProductionProvenanceV21, path: str, *, kind: str = "json") -> ProductionProvenanceV21:
    return provenance.with_attempt_artifact(path, kind=kind)


def record_final_artifact(provenance: ProductionProvenanceV21, path: str, *, kind: str = "json") -> ProductionProvenanceV21:
    return provenance.with_final_artifact(path, kind=kind)


def safe_job_relative_path(job_root: str | Path, relative_path: str) -> Path:
    """Resolve a job-relative artifact path and prove it stays in ``job_root``."""

    relative = _relative_path(relative_path)
    root = Path(job_root).resolve()
    target = (root / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ProductionProvenanceError("artifact path escapes job root") from exc
    return target


def write_provenance_json(
    job_root: str | Path,
    provenance: ProductionProvenanceV21,
    relative_path: str = "provenance/production-provenance.json",
) -> Path:
    """Write only a JSON provenance artifact inside the supplied job root."""

    if not isinstance(provenance, ProductionProvenanceV21):
        raise ProductionProvenanceError("provenance must be ProductionProvenanceV21")
    target = safe_job_relative_path(job_root, relative_path)
    if target.suffix.casefold() != ".json":
        raise ProductionProvenanceError("provenance artifact must have a .json extension")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(provenance.to_json(), encoding="utf-8", newline="\n")
    return target


write_provenance_artifact = write_provenance_json
write_production_provenance = write_provenance_json
resolve_job_artifact_path = safe_job_relative_path


def read_provenance_json(job_root: str | Path, relative_path: str = "provenance/production-provenance.json") -> ProductionProvenanceV21:
    target = safe_job_relative_path(job_root, relative_path)
    if target.suffix.casefold() != ".json":
        raise ProductionProvenanceError("provenance artifact must have a .json extension")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionProvenanceError("could not read provenance JSON") from exc
    return provenance_from_dict(payload)


def provenance_from_dict(payload: Any) -> ProductionProvenanceV21:
    if not isinstance(payload, Mapping):
        raise ProductionProvenanceError("provenance payload must be an object")
    allowed = {
        "version", "requested_engine", "final_engine", "fallback_used", "fallback_stage", "fallback_reason",
        "attempt_status", "final_status", "attempt_artifacts", "final_artifacts", "evaluation",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ProductionProvenanceError(f"provenance contains unsupported keys: {sorted(unknown)}")
    if payload.get("version", PROVENANCE_VERSION) != PROVENANCE_VERSION:
        raise ProductionProvenanceError("unsupported provenance version")

    def artifacts(key: str) -> tuple[ArtifactProvenanceV21, ...]:
        value = payload.get(key, [])
        if not isinstance(value, (list, tuple)):
            raise ProductionProvenanceError(f"{key} must be an array")
        result: list[ArtifactProvenanceV21] = []
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise ProductionProvenanceError(f"{key}[{index}] must be an object")
            if set(item) - {"path", "status", "kind"} or not {"path", "status"} <= set(item):
                raise ProductionProvenanceError(f"{key}[{index}] has invalid keys")
            result.append(ArtifactProvenanceV21(item["path"], item["status"], item.get("kind", "json")))
        return tuple(result)

    return ProductionProvenanceV21(
        requested_engine=payload.get("requested_engine", ENGINE_V21),
        final_engine=payload.get("final_engine"),
        fallback_used=payload.get("fallback_used", False),
        fallback_stage=payload.get("fallback_stage"),
        fallback_reason=payload.get("fallback_reason"),
        attempt_status=payload.get("attempt_status", "attempted"),
        final_status=payload.get("final_status", "pending"),
        attempt_artifacts=artifacts("attempt_artifacts"),
        final_artifacts=artifacts("final_artifacts"),
        evaluation=payload.get("evaluation"),
    )


__all__ = [
    "ARTIFACT_STATUSES",
    "ATTEMPT_STATUSES",
    "ENGINE_NAMES",
    "ENGINE_PORTABLE",
    "ENGINE_V1",
    "ENGINE_V2",
    "ENGINE_V21",
    "FALLBACK_STAGES",
    "FINAL_STATUSES",
    "ArtifactProvenanceV21",
    "ArtifactRecordV21",
    "ProductionProvenance",
    "ProductionProvenanceError",
    "ProductionProvenanceV21",
    "PROVENANCE_VERSION",
    "cancelled_provenance",
    "mark_cancelled",
    "mark_v1_fallback",
    "mark_v21_success",
    "mark_failed_terminal",
    "new_production_provenance",
    "fallback_provenance",
    "failed_terminal_provenance",
    "fallback_failed_provenance",
    "new_provenance",
    "provenance_from_dict",
    "read_provenance_json",
    "resolve_job_artifact_path",
    "record_attempt_artifact",
    "record_final_artifact",
    "safe_job_relative_path",
    "successful_provenance",
    "write_provenance_artifact",
    "write_provenance_json",
    "write_production_provenance",
]
