"""Canonical, JSON-safe contracts for Video Flow source evidence.

The renderer and future planning stages should be able to consume these
objects without knowing whether the input started life as pasted text, a web
URL, an image, or a document.  The project intentionally does not require a
schema library for this foundation: the small ``JsonModel``/``JsonDict``
helpers below provide the useful subset of a model API while keeping the
package importable in a minimal local installation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Sequence


SCHEMA_VERSION = "video-flow.evidence.v1"


class SourceKind(str, Enum):
    """Input families supported by the source normalizer."""

    TEXT = "text"
    URL = "url"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    PDF = "pdf"


class ClaimType(str, Enum):
    """Grounding classes used by narration and QA stages."""

    SOURCE_FACT = "SOURCE_FACT"
    MODEL_EXPLANATION = "MODEL_EXPLANATION"
    ANALOGY = "ANALOGY"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class EntityType(str, Enum):
    CONCEPT = "concept"
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    PRODUCT = "product"
    TECHNOLOGY = "technology"
    METRIC = "metric"
    NUMBER = "number"
    DATE = "date"
    UNKNOWN = "unknown"


class RelationshipType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CAUSES = "causes"
    LEADS_TO = "leads_to"
    PART_OF = "part_of"
    COMPARES = "compares"
    DEPENDS_ON = "depends_on"
    MENTIONS = "mentions"
    CO_OCCURS = "co_occurs"
    DEPICTS = "depicts"
    UNKNOWN = "unknown"


_SOURCE_KIND_ALIASES = {
    "plain_text": SourceKind.TEXT.value,
    "selected_text": SourceKind.TEXT.value,
    "pasted_text": SourceKind.TEXT.value,
    "markdown": SourceKind.TEXT.value,
    "web": SourceKind.URL.value,
    "webpage": SourceKind.URL.value,
    "http": SourceKind.URL.value,
    "https": SourceKind.URL.value,
    "photo": SourceKind.IMAGE.value,
    "screenshot_image": SourceKind.IMAGE.value,
    "ocr": SourceKind.IMAGE.value,
    "file": SourceKind.DOCUMENT.value,
    "doc": SourceKind.DOCUMENT.value,
    "docx": SourceKind.DOCUMENT.value,
    "pdf_file": SourceKind.PDF.value,
}


def normalize_source_kind(value: Any, *, default: str = SourceKind.TEXT.value) -> str:
    """Return a stable source kind while accepting common caller aliases."""

    if isinstance(value, SourceKind):
        value = value.value
    text = str(value or default).strip().lower().replace("-", "_")
    return _SOURCE_KIND_ALIASES.get(text, text if text in {item.value for item in SourceKind} else default)


def stable_hash(value: Any, *, length: int = 24) -> str:
    """Hash arbitrary JSON-ish values deterministically.

    Bytes are hashed as bytes and mappings are serialized with sorted keys.  A
    short digest is sufficient for IDs while the full content hash is retained
    where provenance needs it.
    """

    if isinstance(value, bytes):
        payload = value
    else:
        payload = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[: max(8, int(length))]


def content_hash(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = str(value or "").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def stable_id(prefix: str, value: Any, *, length: int = 16) -> str:
    return f"{prefix}_{stable_hash(value, length=length)}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    """Recursively coerce a value into values accepted by ``json.dumps``."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, JsonModel):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if is_dataclass(value):
        return {str(key): _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class JsonDict(dict):
    """A normal ``dict`` with convenient model-like serialization methods.

    Being an actual dict matters: callers can pass a builder result directly
    to ``json.dumps`` while still using ``result.to_dict()`` or
    ``result.model_dump()`` when a model-shaped API is more convenient.
    """

    def to_dict(self) -> "JsonDict":
        return _json_safe(self)

    def model_dump(self, *, mode: str = "json", **_: Any) -> "JsonDict":
        return self.to_dict()

    def dict(self, **_: Any) -> "JsonDict":  # pragma: no cover - compatibility alias
        return self.to_dict()

    def to_json(self, **kwargs: Any) -> str:
        options = {"ensure_ascii": False, "sort_keys": True, **kwargs}
        return json.dumps(self.to_dict(), **options)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class JsonModel:
    """Dataclass mixin used by canonical nested artifacts."""

    schema_version: ClassVar[str] = SCHEMA_VERSION

    def to_dict(self) -> JsonDict:
        raw = _json_safe(asdict(self))
        return JsonDict(raw)

    def model_dump(self, *, mode: str = "json", **_: Any) -> JsonDict:
        return self.to_dict()

    def dict(self, **_: Any) -> JsonDict:  # pragma: no cover - compatibility alias
        return self.to_dict()

    def to_json(self, **kwargs: Any) -> str:
        options = {"ensure_ascii": False, "sort_keys": True, **kwargs}
        return json.dumps(self.to_dict(), **options)


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _string_list(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or ():
        text = _clean_text(value)
        if text and text not in result:
            result.append(text)
    return result


@dataclass
class SourceInput(JsonModel):
    """Transport-neutral input accepted by all source adapters.

    ``value`` may be text, a URL, bytes, a local path, base64 text, or a small
    mapping supplied by an integration.  Adapters deliberately do not expose
    the raw value in canonical artifacts; only hashes and safe metadata leave
    the ingestion boundary.
    """

    kind: str = SourceKind.TEXT.value
    value: Any = ""
    name: str = ""
    mime_type: str | None = None
    uri: str | None = None
    encoding: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = normalize_source_kind(self.kind)
        self.name = _clean_text(self.name)
        self.mime_type = _clean_text(self.mime_type) or None
        self.uri = _clean_text(self.uri) or None
        self.encoding = _clean_text(self.encoding).lower() or None
        self.metadata = dict(self.metadata or {})

    @property
    def source_type(self) -> str:
        return self.kind

    @property
    def content(self) -> Any:
        return self.value

    @classmethod
    def from_any(cls, value: Any, *, kind: str | None = None, **metadata: Any) -> "SourceInput":
        if isinstance(value, cls):
            if kind or metadata:
                return cls(
                    kind=kind or value.kind,
                    value=value.value,
                    name=value.name,
                    mime_type=value.mime_type,
                    uri=value.uri,
                    encoding=value.encoding,
                    metadata={**value.metadata, **metadata},
                )
            return value
        if isinstance(value, Mapping):
            raw_kind = kind or value.get("kind") or value.get("type") or value.get("source_type")
            raw_value = value.get("value")
            if raw_value is None:
                for key in ("content", "text", "url", "uri", "data", "bytes", "path", "payload"):
                    if key in value:
                        raw_value = value[key]
                        break
            inferred_kind = normalize_source_kind(raw_kind, default="") if raw_kind else ""
            if not inferred_kind:
                inferred_kind = cls._infer_kind(raw_value, value.get("mime_type"), value.get("name"))
            reserved = {"kind", "type", "source_type", "value", "content", "text", "url", "uri", "data", "bytes", "path", "payload", "name", "mime_type", "encoding", "metadata"}
            extras = {str(key): item for key, item in value.items() if key not in reserved}
            extras.update(dict(value.get("metadata") or {}))
            extras.update(metadata)
            return cls(
                kind=inferred_kind,
                value=raw_value if raw_value is not None else "",
                name=str(value.get("name") or ""),
                mime_type=value.get("mime_type") or value.get("content_type"),
                uri=value.get("uri") or value.get("url"),
                encoding=value.get("encoding"),
                metadata=extras,
            )
        if isinstance(value, (bytes, bytearray, memoryview)):
            return cls(kind=kind or SourceKind.DOCUMENT.value, value=bytes(value), metadata=metadata)
        if isinstance(value, Path):
            return cls(kind=kind or cls._infer_kind(value, None, str(value)), value=value, name=value.name, metadata=metadata)
        text = _clean_text(value)
        inferred = kind or cls._infer_kind(text, None, "")
        return cls(kind=inferred, value=value if value is not None else "", metadata=metadata)

    @staticmethod
    def _infer_kind(value: Any, mime_type: Any = None, name: Any = None) -> str:
        mime = str(mime_type or "").lower()
        if mime.startswith("image/"):
            return SourceKind.IMAGE.value
        if mime == "application/pdf":
            return SourceKind.PDF.value
        if mime.startswith("text/"):
            return SourceKind.TEXT.value
        candidate = str(value or name or "").strip()
        if re.match(r"^https?://\S+$", candidate, re.I):
            return SourceKind.URL.value
        try:
            path = Path(candidate)
            if path.exists() and path.is_file():
                suffix = path.suffix.lower()
                if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}:
                    return SourceKind.IMAGE.value
                if suffix == ".pdf":
                    return SourceKind.PDF.value
                if suffix:
                    return SourceKind.DOCUMENT.value
        except (OSError, ValueError):
            pass
        return SourceKind.TEXT.value


UniversalInput = SourceInput
InputSpec = SourceInput
SourceType = SourceKind
InputKind = SourceKind


@dataclass
class Provenance(JsonModel):
    """How an artifact or observation came into existence."""

    id: str = ""
    source_id: str = ""
    kind: str = "source"
    adapter: str = ""
    method: str = ""
    uri: str | None = None
    locator: str | None = None
    retrieved_at: str | None = None
    content_hash: str = ""
    parent_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = self.id or stable_id("prov", {"source": self.source_id, "kind": self.kind, "adapter": self.adapter, "method": self.method, "locator": self.locator})
        self.kind = _clean_text(self.kind) or "source"
        self.adapter = _clean_text(self.adapter)
        self.method = _clean_text(self.method)
        self.uri = _clean_text(self.uri) or None
        self.locator = _clean_text(self.locator) or None
        self.retrieved_at = _clean_text(self.retrieved_at) or None
        self.parent_ids = _string_list(self.parent_ids)
        self.metadata = dict(self.metadata or {})


@dataclass
class Uncertainty(JsonModel):
    """Explicit uncertainty; absence of evidence is never silently certainty."""

    level: str = "unknown"
    score: float | None = None
    reason: str = ""
    scope: str = ""
    kind: str = "unknown"
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.level = _clean_text(self.level).lower() or "unknown"
        if self.level not in {"none", "low", "medium", "high", "unknown"}:
            self.level = "unknown"
        if self.score is not None:
            try:
                self.score = min(1.0, max(0.0, float(self.score)))
            except (TypeError, ValueError):
                self.score = None
        self.reason = _clean_text(self.reason)
        self.scope = _clean_text(self.scope)
        self.kind = _clean_text(self.kind).lower() or "unknown"
        self.sources = _string_list(self.sources)
        self.metadata = dict(self.metadata or {})


@dataclass
class EvidenceSpan(JsonModel):
    """Stable quote and character offsets into a normalized source."""

    id: str = ""
    source_id: str = ""
    start: int = 0
    end: int = 0
    text: str = ""
    quote_hash: str = ""
    locator: str | None = None
    confidence: float = 1.0
    provenance_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.text = _clean_text(self.text)
        self.start = max(0, int(self.start or 0))
        self.end = max(self.start, int(self.end or self.start))
        self.quote_hash = self.quote_hash or content_hash(self.text)
        self.id = self.id or stable_id("span", {"source": self.source_id, "start": self.start, "end": self.end, "quote": self.quote_hash})
        self.locator = _clean_text(self.locator) or None
        try:
            self.confidence = min(1.0, max(0.0, float(self.confidence)))
        except (TypeError, ValueError):
            self.confidence = 0.0
        self.provenance_ids = _string_list(self.provenance_ids)


@dataclass
class SourceChunk(JsonModel):
    id: str = ""
    source_id: str = ""
    index: int = 0
    text: str = ""
    start: int = 0
    end: int = 0
    section: str | None = None
    overlap: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.index = max(0, int(self.index or 0))
        self.text = _clean_text(self.text)
        self.start = max(0, int(self.start or 0))
        self.end = max(self.start, int(self.end or self.start))
        self.overlap = max(0, int(self.overlap or 0))
        self.section = _clean_text(self.section) or None
        self.id = self.id or stable_id("chunk", {"source": self.source_id, "index": self.index, "start": self.start, "text": self.text})
        self.metadata = dict(self.metadata or {})


@dataclass
class NormalizedSource(JsonModel):
    """Canonical source artifact shared by all adapters."""

    schema_version: str = SCHEMA_VERSION
    id: str = ""
    source_type: str = SourceKind.TEXT.value
    source_name: str = ""
    uri: str | None = None
    original_hash: str = ""
    normalized_hash: str = ""
    text: str = ""
    language: str = "und"
    chunks: list[SourceChunk | dict[str, Any]] = field(default_factory=list)
    structure_hints: dict[str, Any] = field(default_factory=dict)
    evidence_spans: list[EvidenceSpan | dict[str, Any]] = field(default_factory=list)
    provenance: list[Provenance | dict[str, Any]] = field(default_factory=list)
    uncertainty: list[Uncertainty | dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_type = normalize_source_kind(self.source_type)
        self.source_name = _clean_text(self.source_name)
        self.uri = _clean_text(self.uri) or None
        self.text = str(self.text or "")
        self.language = _clean_text(self.language).lower() or "und"
        self.original_hash = self.original_hash or content_hash(self.text)
        self.normalized_hash = self.normalized_hash or content_hash(self.text)
        self.id = self.id or stable_id("source", {"type": self.source_type, "hash": self.normalized_hash, "uri": self.uri})
        self.chunks = [item if isinstance(item, (SourceChunk, Mapping)) else SourceChunk(text=str(item)) for item in self.chunks]
        self.evidence_spans = [item if isinstance(item, (EvidenceSpan, Mapping)) else EvidenceSpan(source_id=self.id, text=str(item)) for item in self.evidence_spans]
        self.provenance = [item if isinstance(item, (Provenance, Mapping)) else Provenance(source_id=self.id, metadata={"value": item}) for item in self.provenance]
        self.uncertainty = [item if isinstance(item, (Uncertainty, Mapping)) else Uncertainty(reason=str(item), scope="source") for item in self.uncertainty]
        self.structure_hints = dict(self.structure_hints or {})
        self.metadata = dict(self.metadata or {})

    @property
    def kind(self) -> str:
        return self.source_type

    @property
    def source_id(self) -> str:
        return self.id


@dataclass
class ContextSufficiency(JsonModel):
    status: str = "unknown"
    score: float = 0.0
    query: str = ""
    required: list[str] = field(default_factory=list)
    available: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: str = ""
    uncertainty: list[Uncertainty | dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = _clean_text(self.status).lower() or "unknown"
        if self.status not in {"sufficient", "partial", "insufficient", "unknown"}:
            self.status = "unknown"
        try:
            self.score = min(1.0, max(0.0, float(self.score)))
        except (TypeError, ValueError):
            self.score = 0.0
        self.query = _clean_text(self.query)
        self.required = _string_list(self.required)
        self.available = _string_list(self.available)
        self.missing = _string_list(self.missing)
        self.reason = _clean_text(self.reason)
        self.uncertainty = [item if isinstance(item, (Uncertainty, Mapping)) else Uncertainty(reason=str(item), scope="context") for item in self.uncertainty]


@dataclass
class EvidenceClaim(JsonModel):
    id: str = ""
    text: str = ""
    claim_type: str = ClaimType.SOURCE_FACT.value
    source_refs: list[str] = field(default_factory=list)
    evidence_span_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty: Uncertainty | dict[str, Any] | None = None
    provenance_ids: list[str] = field(default_factory=list)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.text = _clean_text(self.text)
        raw_type = self.claim_type.value if isinstance(self.claim_type, ClaimType) else str(self.claim_type or ClaimType.UNKNOWN.value).upper()
        self.claim_type = raw_type if raw_type in {item.value for item in ClaimType} else ClaimType.UNKNOWN.value
        self.source_refs = _string_list(self.source_refs)
        self.evidence_span_ids = _string_list(self.evidence_span_ids)
        self.provenance_ids = _string_list(self.provenance_ids)
        try:
            self.confidence = min(1.0, max(0.0, float(self.confidence)))
        except (TypeError, ValueError):
            self.confidence = 0.0
        if self.uncertainty is not None and not isinstance(self.uncertainty, (Uncertainty, Mapping)):
            self.uncertainty = Uncertainty(reason=str(self.uncertainty), scope="claim")
        self.numbers = [dict(item) if isinstance(item, Mapping) else {"value": str(item)} for item in self.numbers]
        self.metadata = dict(self.metadata or {})
        self.id = self.id or stable_id("claim", {"text": self.text, "type": self.claim_type, "refs": self.source_refs})


@dataclass
class EvidenceEntity(JsonModel):
    id: str = ""
    label: str = ""
    entity_type: str = EntityType.UNKNOWN.value
    source_refs: list[str] = field(default_factory=list)
    mention_span_ids: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    uncertainty: Uncertainty | dict[str, Any] | None = None
    provenance_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.label = _clean_text(self.label)
        raw_type = self.entity_type.value if isinstance(self.entity_type, EntityType) else str(self.entity_type or EntityType.UNKNOWN.value).lower()
        self.entity_type = raw_type if raw_type in {item.value for item in EntityType} else EntityType.UNKNOWN.value
        self.source_refs = _string_list(self.source_refs)
        self.mention_span_ids = _string_list(self.mention_span_ids)
        self.provenance_ids = _string_list(self.provenance_ids)
        try:
            self.confidence = min(1.0, max(0.0, float(self.confidence)))
        except (TypeError, ValueError):
            self.confidence = 0.0
        if self.uncertainty is not None and not isinstance(self.uncertainty, (Uncertainty, Mapping)):
            self.uncertainty = Uncertainty(reason=str(self.uncertainty), scope="entity")
        self.attributes = dict(self.attributes or {})
        self.id = self.id or stable_id("entity", self.label.lower())


@dataclass
class EvidenceRelationship(JsonModel):
    id: str = ""
    subject_id: str = ""
    predicate: str = ""
    object_id: str = ""
    relationship_type: str = RelationshipType.UNKNOWN.value
    source_refs: list[str] = field(default_factory=list)
    evidence_span_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    uncertainty: Uncertainty | dict[str, Any] | None = None
    provenance_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.subject_id = _clean_text(self.subject_id)
        self.predicate = _clean_text(self.predicate)
        self.object_id = _clean_text(self.object_id)
        raw_type = self.relationship_type.value if isinstance(self.relationship_type, RelationshipType) else str(self.relationship_type or RelationshipType.UNKNOWN.value).lower()
        self.relationship_type = raw_type if raw_type in {item.value for item in RelationshipType} else RelationshipType.UNKNOWN.value
        self.source_refs = _string_list(self.source_refs)
        self.evidence_span_ids = _string_list(self.evidence_span_ids)
        self.provenance_ids = _string_list(self.provenance_ids)
        try:
            self.confidence = min(1.0, max(0.0, float(self.confidence)))
        except (TypeError, ValueError):
            self.confidence = 0.0
        if self.uncertainty is not None and not isinstance(self.uncertainty, (Uncertainty, Mapping)):
            self.uncertainty = Uncertainty(reason=str(self.uncertainty), scope="relationship")
        self.metadata = dict(self.metadata or {})
        self.id = self.id or stable_id("rel", {"s": self.subject_id, "p": self.predicate, "o": self.object_id, "refs": self.source_refs})


@dataclass
class EvidenceArtifact(JsonModel):
    """Top-level result returned by :class:`EvidenceBuilder`."""

    schema_version: str = SCHEMA_VERSION
    id: str = ""
    normalized_source: NormalizedSource | dict[str, Any] | None = None
    context_sufficiency: ContextSufficiency | dict[str, Any] | None = None
    claims: list[EvidenceClaim | dict[str, Any]] = field(default_factory=list)
    entities: list[EvidenceEntity | dict[str, Any]] = field(default_factory=list)
    relationships: list[EvidenceRelationship | dict[str, Any]] = field(default_factory=list)
    evidence_spans: list[EvidenceSpan | dict[str, Any]] = field(default_factory=list)
    provenance: list[Provenance | dict[str, Any]] = field(default_factory=list)
    uncertainty: list[Uncertainty | dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    retrieval: dict[str, Any] = field(default_factory=dict)
    vision: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = self.id or stable_id("evidence", {"source": getattr(self.normalized_source, "id", None), "claims": [getattr(item, "id", item) for item in self.claims]})
        self.claims = [item if isinstance(item, (EvidenceClaim, Mapping)) else EvidenceClaim(text=str(item)) for item in self.claims]
        self.entities = [item if isinstance(item, (EvidenceEntity, Mapping)) else EvidenceEntity(label=str(item)) for item in self.entities]
        self.relationships = [item if isinstance(item, (EvidenceRelationship, Mapping)) else EvidenceRelationship(predicate=str(item)) for item in self.relationships]
        self.evidence_spans = [item if isinstance(item, (EvidenceSpan, Mapping)) else EvidenceSpan(text=str(item)) for item in self.evidence_spans]
        self.provenance = [item if isinstance(item, (Provenance, Mapping)) else Provenance(metadata={"value": item}) for item in self.provenance]
        self.uncertainty = [item if isinstance(item, (Uncertainty, Mapping)) else Uncertainty(reason=str(item)) for item in self.uncertainty]
        self.diagnostics = _string_list(self.diagnostics)
        self.retrieval = dict(self.retrieval or {})
        self.vision = dict(self.vision or {})
        self.metadata = dict(self.metadata or {})


EvidenceBundle = EvidenceArtifact
EvidenceReference = EvidenceSpan


def as_json_dict(value: Any) -> JsonDict:
    """Public serialization helper used by adapters and API boundaries."""

    result = _json_safe(value)
    return result if isinstance(result, JsonDict) else JsonDict(result if isinstance(result, Mapping) else {"value": result})


__all__ = [
    "SCHEMA_VERSION",
    "SourceKind", "SourceType", "InputKind",
    "ClaimType", "EntityType", "RelationshipType",
    "SourceInput", "UniversalInput", "InputSpec",
    "Provenance", "Uncertainty", "EvidenceSpan", "SourceChunk", "NormalizedSource",
    "ContextSufficiency", "EvidenceClaim", "EvidenceEntity", "EvidenceRelationship",
    "EvidenceArtifact", "EvidenceBundle", "EvidenceReference",
    "JsonDict", "JsonModel", "as_json_dict", "stable_hash", "content_hash", "stable_id", "utc_now",
    "normalize_source_kind",
]
