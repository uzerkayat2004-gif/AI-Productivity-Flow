"""Evidence assembly for Video Flow source understanding.

``EvidenceBuilder`` is intentionally provider-independent.  It performs the
deterministic work locally (source normalization, stable spans, lightweight
claim/entity/relationship extraction) and accepts optional retrieval and
vision adapters for inputs that need external interpretation.  Adapters are
injected per builder or per call, so the default path never performs network
requests or sends source material anywhere.
"""

from __future__ import annotations

import inspect
import re
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import (
    ClaimType,
    ContextSufficiency,
    EntityType,
    EvidenceArtifact,
    EvidenceClaim,
    EvidenceEntity,
    EvidenceRelationship,
    EvidenceSpan,
    JsonDict,
    NormalizedSource,
    Provenance,
    RelationshipType,
    SourceChunk,
    SourceInput,
    SourceKind,
    Uncertainty,
    as_json_dict,
    content_hash,
    normalize_source_kind,
    stable_id,
    utc_now,
)
from .sources import (
    RetrievalAdapter,
    SourceNormalizer,
    VisionAdapter,
    normalize_source,
)


_HEDGE_WORDS = re.compile(r"\b(?:may|might|could|possibly|likely|unlikely|appears?|suggests?|estimated?|approximately|roughly|unclear|uncertain|around)\b", re.I)
_NUMBER_PATTERN = re.compile(
    r"(?<![\w])(?P<raw>(?:[$€£₹]\s*)?[-+]?\d[\d,]*(?:\.\d+)?(?:\s?%|\s?(?:percent|per cent|[kKmMbBtT]))?)(?![\w])"
)
_DATE_PATTERN = re.compile(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b")
_ACRONYM_PATTERN = re.compile(r"\b[A-Z][A-Z0-9&_-]{1,}\b")
_PROPER_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&'_-]*(?:\s+[A-Z][A-Za-z0-9&'_-]*){0,3}\b")
_RELATION_PATTERN = re.compile(
    r"(?P<left>[A-Za-z0-9][A-Za-z0-9 &'/_-]{1,80}?)\s+"
    r"(?P<predicate>causes?|leads? to|results? in|depends? on|supports?|contradicts?|contains?|includes?|"
    r"compares? with|compared with|versus|vs\.?|is part of|belongs? to)\s+"
    r"(?P<right>[A-Za-z0-9][A-Za-z0-9 &'/_-]{1,80}?)(?:[.!?,;]|$)",
    re.I,
)
_STOP_ENTITY_WORDS = {
    "A", "An", "And", "As", "At", "But", "By", "For", "From", "If", "In", "It", "Its", "Of", "On", "Or", "The", "This", "That", "Then", "To", "We", "When", "With", "You",
}


def _text(value: Any, limit: int = 8000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _list_strings(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or ():
        item = _text(value)
        if item and item not in result:
            result.append(item)
    return result


def _mapping_value(data: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return default


def _adapter_name(adapter: Any, fallback: str) -> str:
    return _text(getattr(adapter, "name", None) or getattr(adapter, "__name__", None) or fallback, 160)


def _invoke_adapter(adapter: Any, methods: Sequence[str], first_arg: Any, **kwargs: Any) -> tuple[Any, str]:
    """Call a duck-typed adapter without requiring one concrete SDK shape."""

    target: Callable[..., Any] | None = None
    method_name = "callable"
    for name in methods:
        candidate = getattr(adapter, name, None)
        if callable(candidate):
            target = candidate
            method_name = name
            break
    if target is None and callable(adapter):
        target = adapter
    if target is None:
        raise TypeError(f"Adapter does not expose any of: {', '.join(methods)}")

    # Prefer keyword-rich calls, then progressively simpler signatures.  This
    # supports a tiny lambda in a test as well as a production adapter that
    # wants the full provenance context.
    attempts = (
        lambda: target(first_arg, **kwargs),
        lambda: target(first_arg),
        lambda: target(**kwargs),
        lambda: target(),
    )
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            return attempt(), method_name
        except TypeError as exc:
            last_error = exc
            continue
    raise last_error or TypeError("Adapter invocation failed")


def _provenance_items(source: NormalizedSource) -> list[Provenance]:
    items: list[Provenance] = []
    for raw in source.provenance:
        if isinstance(raw, Provenance):
            items.append(raw)
        elif isinstance(raw, Mapping):
            items.append(Provenance(**{key: value for key, value in raw.items() if key in Provenance.__dataclass_fields__}))
    if not items:
        items.append(Provenance(source_id=source.id, adapter="unknown", method="normalize", content_hash=source.normalized_hash))
    return items


def _span_items(source: NormalizedSource) -> list[EvidenceSpan]:
    items: list[EvidenceSpan] = []
    for raw in source.evidence_spans:
        if isinstance(raw, EvidenceSpan):
            items.append(raw)
        elif isinstance(raw, Mapping):
            items.append(EvidenceSpan(**{key: value for key, value in raw.items() if key in EvidenceSpan.__dataclass_fields__}))
    return items


def _chunk_items(source: NormalizedSource) -> list[SourceChunk]:
    items: list[SourceChunk] = []
    for raw in source.chunks:
        if isinstance(raw, SourceChunk):
            items.append(raw)
        elif isinstance(raw, Mapping):
            items.append(SourceChunk(**{key: value for key, value in raw.items() if key in SourceChunk.__dataclass_fields__}))
    return items


def _normalization_from_retrieval(
    original: SourceInput,
    result: Any,
    *,
    normalizer: SourceNormalizer,
    adapter: Any,
    query: str,
    chunk_chars: int,
    chunk_overlap: int,
) -> tuple[NormalizedSource | None, dict[str, Any], list[str]]:
    diagnostics: list[str] = []
    info: dict[str, Any] = {"attempted": True, "adapter": _adapter_name(adapter, "retrieval"), "method": "", "success": False, "network_accessed": True}
    if result is None or result is False:
        info.update({"success": False, "empty": True})
        diagnostics.append("Retrieval adapter returned no content.")
        return None, info, diagnostics
    info["success"] = True
    info["result_type"] = type(result).__name__
    # A retrieval adapter may return a complete canonical source, an input
    # object, or a response-shaped mapping/string.
    if isinstance(result, NormalizedSource):
        normalized = result
    else:
        payload: Any = result
        if isinstance(result, Mapping):
            nested = _mapping_value(result, "source", "input", "document")
            if isinstance(nested, (NormalizedSource, SourceInput)):
                payload = nested
            else:
                payload = _mapping_value(result, "text", "content", "body", "html", "markdown", "data", default="")
                info.update({str(key): value for key, value in result.items() if key in {"title", "content_type", "status", "etag", "retrieved_at", "url"} and isinstance(value, (str, int, float, bool))})
        if isinstance(payload, SourceInput):
            retrieval_input = payload
            if not retrieval_input.name:
                retrieval_input.name = original.name
            if not retrieval_input.uri:
                retrieval_input.uri = original.uri or _text(original.value)
        else:
            retrieval_input = SourceInput(kind=SourceKind.TEXT.value, value=payload, name=original.name, uri=original.uri or _text(original.value), metadata={"retrieved_from": original.uri or _text(original.value), "query": query})
        try:
            normalized = normalizer.normalize(retrieval_input, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
        except Exception as exc:
            diagnostics.append(f"Retrieved content could not be normalized: {exc}")
            info["success"] = False
            return None, info, diagnostics
    # Keep URL identity and append a retrieval provenance record; this is what
    # lets a future cache replace the adapter without changing source refs.
    original_uri = original.uri or _text(original.value)
    normalized.uri = original_uri
    normalized.source_name = normalized.source_name or original.name
    normalized.source_type = SourceKind.URL.value
    parent_id = stable_id("source", {"kind": SourceKind.URL.value, "uri": original_uri})
    retrieval_prov = Provenance(
        source_id=normalized.id,
        kind="retrieval",
        adapter=_adapter_name(adapter, "retrieval"),
        method=_text(info.get("method") or "retrieve"),
        uri=original_uri,
        content_hash=normalized.normalized_hash,
        parent_ids=[parent_id],
        metadata={"query": query, "network_accessed": True},
    )
    normalized.provenance = [*normalized.provenance, retrieval_prov]
    normalized.uncertainty = [item for item in normalized.uncertainty if not (isinstance(item, Uncertainty) and item.kind == "missing_context")]
    normalized.metadata.update({"retrieved": True, "network_accessed": True, "retrieval_adapter": _adapter_name(adapter, "retrieval")})
    info["source_id"] = normalized.id
    info["content_hash"] = normalized.normalized_hash
    return normalized, info, diagnostics


def _normalization_from_vision(
    original: SourceInput,
    base: NormalizedSource,
    result: Any,
    *,
    normalizer: SourceNormalizer,
    adapter: Any,
    chunk_chars: int,
    chunk_overlap: int,
) -> tuple[NormalizedSource | None, dict[str, Any], list[str], list[Any]]:
    diagnostics: list[str] = []
    info: dict[str, Any] = {"attempted": True, "adapter": _adapter_name(adapter, "vision"), "method": "", "success": False, "network_accessed": False}
    structured: list[Any] = []
    if result is None or result is False:
        diagnostics.append("Vision adapter returned no observations.")
        info["empty"] = True
        return None, info, diagnostics, structured
    info.update({"success": True, "result_type": type(result).__name__})
    if isinstance(result, Mapping):
        structured.extend(result.get("claims") or [])
        structured.extend(result.get("observations") or [])
        visual_text = _mapping_value(result, "text", "description", "transcript", "ocr", "content", default="")
        info.update({str(key): value for key, value in result.items() if key in {"model", "provider", "confidence", "width", "height"} and isinstance(value, (str, int, float, bool))})
    elif isinstance(result, (list, tuple)):
        structured.extend(result)
        visual_text = " ".join(_text(item if not isinstance(item, Mapping) else _mapping_value(item, "text", "description", default=""), 2000) for item in result)
    else:
        visual_text = _text(result, 100_000)
    visual_text = _text(visual_text, 100_000)
    if not visual_text:
        diagnostics.append("Vision adapter produced no textual observation.")
        info["success"] = False
        return None, info, diagnostics, structured
    try:
        # Normalize the OCR/description locally, then preserve the image's
        # source identity and image provenance on the resulting text spans.
        text_input = SourceInput(kind=SourceKind.TEXT.value, value=visual_text, name=original.name, uri=original.uri, metadata={**original.metadata, "derived_from": base.id, "vision": True})
        normalized = normalizer.normalize(text_input, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
    except Exception as exc:
        diagnostics.append(f"Vision observation could not be normalized: {exc}")
        info["success"] = False
        return None, info, diagnostics, structured
    old_id = normalized.id
    normalized.id = base.id
    normalized.source_type = base.source_type
    normalized.original_hash = base.original_hash
    normalized.uri = base.uri or original.uri
    normalized.source_name = base.source_name or original.name
    for chunk in _chunk_items(normalized):
        chunk.source_id = base.id
        chunk.id = stable_id("chunk", {"source": base.id, "index": chunk.index, "start": chunk.start, "text": chunk.text})
    for span in _span_items(normalized):
        span.source_id = base.id
        span.id = stable_id("span", {"source": base.id, "start": span.start, "end": span.end, "quote": span.text})
        span.locator = span.locator or "vision:observation"
    vision_prov = Provenance(source_id=base.id, kind="vision", adapter=_adapter_name(adapter, "vision"), method=_text(info.get("method") or "analyze"), uri=base.uri, content_hash=content_hash(visual_text), parent_ids=[base.id], metadata={"network_accessed": False})
    normalized.provenance = [*_provenance_items(base), vision_prov]
    normalized.metadata.update({"vision_observation": True, "vision_adapter": _adapter_name(adapter, "vision"), "vision_text_hash": content_hash(visual_text)})
    normalized.uncertainty = [item for item in base.uncertainty if not (isinstance(item, Uncertainty) and item.kind == "missing_context")]
    info.update({"source_id": normalized.id, "text_characters": len(visual_text), "content_hash": content_hash(visual_text)})
    return normalized, info, diagnostics, structured


def _number_records(text: str, *, source_ref: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in _NUMBER_PATTERN.finditer(text):
        raw = match.group("raw").strip()
        numeric = re.sub(r"[^0-9.+-]", "", raw.replace(",", ""))
        try:
            value: int | float = float(numeric)
            if value.is_integer():
                value = int(value)
        except ValueError:
            value = None
        unit = "%" if "%" in raw or "percent" in raw.lower() or "per cent" in raw.lower() else ""
        records.append({"id": stable_id("number", {"raw": raw, "source": source_ref}), "raw": raw, "value": value, "unit": unit, "source_ref": source_ref})
    return records


def _claim_type(value: Any, *, default: str = ClaimType.SOURCE_FACT.value) -> str:
    raw = value.value if isinstance(value, ClaimType) else str(value or default).upper().replace("-", "_")
    aliases = {"FACT": ClaimType.SOURCE_FACT.value, "SOURCE": ClaimType.SOURCE_FACT.value, "EXPLANATION": ClaimType.MODEL_EXPLANATION.value, "INFERRED": ClaimType.INFERENCE.value}
    raw = aliases.get(raw, raw)
    return raw if raw in {item.value for item in ClaimType} else ClaimType.UNKNOWN.value


def _claim_uncertainty(text: str, *, source_ref: str) -> Uncertainty | None:
    if not _HEDGE_WORDS.search(text):
        return None
    return Uncertainty(level="medium", score=0.55, reason="Source wording contains uncertainty or approximation.", scope="claim", kind="hedged_language", sources=[source_ref])


def _entity_type(label: str, context: str = "") -> str:
    lower = label.lower()
    if _DATE_PATTERN.fullmatch(label.strip()):
        return EntityType.DATE.value
    if _NUMBER_PATTERN.fullmatch(label.strip()):
        return EntityType.NUMBER.value
    if any(word in lower for word in ("inc", "corp", "company", "ltd", "university", "institute", "team", "agency")):
        return EntityType.ORGANIZATION.value
    if any(word in lower for word in ("api", "python", "sql", "http", "gpu", "software", "model", "algorithm", "database", "network")):
        return EntityType.TECHNOLOGY.value
    if any(word in lower for word in ("percent", "%", "rate", "score", "growth", "revenue", "cost", "temperature", "number", "metric")):
        return EntityType.METRIC.value
    if len(label.split()) >= 2 and all(part[:1].isupper() for part in label.split() if part):
        return EntityType.CONCEPT.value
    return EntityType.CONCEPT.value if context else EntityType.UNKNOWN.value


def _entity_candidates(text: str) -> list[tuple[str, int, int, str]]:
    candidates: OrderedDict[str, tuple[str, int, int, str]] = OrderedDict()
    for pattern in (_ACRONYM_PATTERN, _PROPER_PATTERN, _DATE_PATTERN, _NUMBER_PATTERN):
        for match in pattern.finditer(text):
            label = _text(match.group(0), 120).strip(" ,.;:()[]{}")
            if not label or label in _STOP_ENTITY_WORDS or len(label) < 2:
                continue
            if pattern is _PROPER_PATTERN and label.split()[0] in _STOP_ENTITY_WORDS:
                continue
            key = re.sub(r"\s+", " ", label).lower()
            if key not in candidates:
                candidates[key] = (label, match.start(), match.end(), _entity_type(label, text))
    return list(candidates.values())


def _entity_for_fragment(fragment: str, entities: Sequence[EvidenceEntity], *, create: bool = False) -> EvidenceEntity | None:
    clean = _text(fragment, 180).strip(" ,.;:()[]{}")
    if not clean:
        return None
    lower = clean.lower()
    for entity in entities:
        if entity.label.lower() == lower or entity.label.lower() in lower or lower in entity.label.lower():
            return entity
    if not create:
        return None
    entity = EvidenceEntity(label=clean, entity_type=_entity_type(clean, clean), confidence=0.55)
    entities.append(entity)  # type: ignore[arg-type]
    return entity


def _relationship_type(predicate: str) -> str:
    lower = predicate.lower().strip()
    if re.search(r"cause|lead|result", lower):
        return RelationshipType.CAUSES.value if "cause" in lower else RelationshipType.LEADS_TO.value
    if "depend" in lower:
        return RelationshipType.DEPENDS_ON.value
    if "support" in lower:
        return RelationshipType.SUPPORTS.value
    if "contradict" in lower:
        return RelationshipType.CONTRADICTS.value
    if "compar" in lower or lower in {"vs", "versus"}:
        return RelationshipType.COMPARES.value
    if "part of" in lower or "belong" in lower:
        return RelationshipType.PART_OF.value
    if "contain" in lower or "include" in lower:
        return RelationshipType.MENTIONS.value
    return RelationshipType.UNKNOWN.value


def _structured_items(result: Sequence[Any], key: str) -> list[Any]:
    values: list[Any] = []
    for item in result:
        if isinstance(item, Mapping):
            nested = item.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
                values.extend(nested)
    return values


class EvidenceBuilder:
    """Build a grounded evidence artifact from any supported input.

    Parameters can be supplied once at construction or overridden on each
    ``build`` call.  The method accepts both typed ``SourceInput`` objects and
    ergonomic strings/mappings/bytes, while preserving a single canonical
    output shape.
    """

    def __init__(
        self,
        retrieval_adapter: Any | None = None,
        vision_adapter: Any | None = None,
        *,
        source_normalizer: SourceNormalizer | None = None,
        normalizer: SourceNormalizer | None = None,
        chunk_chars: int = 1200,
        chunk_overlap: int = 100,
        max_claims: int = 250,
        max_entities: int = 400,
        max_relationships: int = 400,
    ) -> None:
        self.retrieval_adapter = retrieval_adapter
        self.vision_adapter = vision_adapter
        self.normalizer = source_normalizer or normalizer or SourceNormalizer()
        self.chunk_chars = max(100, int(chunk_chars))
        self.chunk_overlap = max(0, min(int(chunk_overlap), self.chunk_chars // 2))
        self.max_claims = max(1, int(max_claims))
        self.max_entities = max(1, int(max_entities))
        self.max_relationships = max(1, int(max_relationships))

    def build(
        self,
        source: Any,
        query: str | None = None,
        retrieval_adapter: Any | None = None,
        vision_adapter: Any | None = None,
        *,
        context: Any = None,
        kind: str | None = None,
        source_type: str | None = None,
        input_type: str | None = None,
        source_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        max_claims: int | None = None,
        max_entities: int | None = None,
        max_relationships: int | None = None,
        strict: bool = False,
        include_source_text: bool = True,
        **options: Any,
    ) -> JsonDict:
        """Return a JSON-serializable evidence artifact.

        ``retrieval_adapter`` and ``vision_adapter`` are deliberately explicit
        seams.  Adapter errors become diagnostics and uncertainty by default;
        ``strict=True`` raises after preserving the original exception type,
        which is useful for integration tests and fail-closed pipelines.
        """

        diagnostics: list[str] = []
        retrieval_info: dict[str, Any] = {"attempted": False, "success": False, "network_accessed": False}
        vision_info: dict[str, Any] = {"attempted": False, "success": False, "network_accessed": False}
        structured_vision: list[Any] = []
        chosen_retrieval = retrieval_adapter if retrieval_adapter is not None else options.pop("retriever", None) or options.pop("retrieval", None) or self.retrieval_adapter
        chosen_vision = vision_adapter if vision_adapter is not None else options.pop("vision", None) or options.pop("ocr_adapter", None) or self.vision_adapter
        raw_input = SourceInput.from_any(source, kind=kind or source_type or input_type, **dict(metadata or {}))
        if source_name and not raw_input.name:
            raw_input.name = _text(source_name, 400)
        query_text = _text(query, 2000)
        try:
            normalized = self.normalizer.normalize(raw_input, chunk_chars=self.chunk_chars, chunk_overlap=self.chunk_overlap, **options)
        except Exception as exc:
            if strict:
                raise
            diagnostics.append(f"Source normalization failed: {exc}")
            # Keep the failure JSON-safe and referentially stable.
            fallback_input = SourceInput(kind=raw_input.kind, value="", name=raw_input.name, uri=raw_input.uri, metadata=raw_input.metadata)
            normalized = NormalizedSource(id=stable_id("source", {"kind": fallback_input.kind, "value": str(source)}), source_type=fallback_input.kind, source_name=fallback_input.name, uri=fallback_input.uri, text="", original_hash=content_hash(str(source)), normalized_hash=content_hash(""), uncertainty=[Uncertainty(level="high", score=1.0, reason=str(exc), scope="source", kind="normalization_failure")], metadata={"normalization_failed": True})

        # URL retrieval is never implicit.  Only a supplied adapter can add
        # network-derived context.
        if normalized.source_type == SourceKind.URL.value and chosen_retrieval is not None:
            retrieval_info["attempted"] = True
            try:
                retrieved, method = _invoke_adapter(chosen_retrieval, ("retrieve", "fetch", "get", "search"), raw_input.uri or _text(raw_input.value), source=raw_input, query=query_text, context=context)
                retrieval_info["method"] = method
                candidate, info, adapter_diagnostics = _normalization_from_retrieval(raw_input, retrieved, normalizer=self.normalizer, adapter=chosen_retrieval, query=query_text, chunk_chars=self.chunk_chars, chunk_overlap=self.chunk_overlap)
                retrieval_info.update(info)
                diagnostics.extend(adapter_diagnostics)
                if candidate is not None:
                    normalized = candidate
            except Exception as exc:
                retrieval_info.update({"success": False, "error": str(exc)[:500], "adapter": _adapter_name(chosen_retrieval, "retrieval")})
                diagnostics.append(f"Retrieval adapter failed: {exc}")
                if strict:
                    raise

        # Image/screenshot interpretation is similarly opt-in.
        if normalized.source_type in {SourceKind.IMAGE.value, SourceKind.SCREENSHOT.value} and chosen_vision is not None:
            vision_info["attempted"] = True
            try:
                observed, method = _invoke_adapter(chosen_vision, ("analyze", "describe", "ocr", "recognize", "extract"), raw_input.value, source=raw_input, query=query_text, context=context, metadata=normalized.metadata)
                vision_info["method"] = method
                candidate, info, adapter_diagnostics, structured_vision = _normalization_from_vision(raw_input, normalized, observed, normalizer=self.normalizer, adapter=chosen_vision, chunk_chars=self.chunk_chars, chunk_overlap=self.chunk_overlap)
                vision_info.update(info)
                diagnostics.extend(adapter_diagnostics)
                if candidate is not None:
                    normalized = candidate
            except Exception as exc:
                vision_info.update({"success": False, "error": str(exc)[:500], "adapter": _adapter_name(chosen_vision, "vision")})
                diagnostics.append(f"Vision adapter failed: {exc}")
                if strict:
                    raise

        spans = _span_items(normalized)
        provenance = _provenance_items(normalized)
        claims = self._claims(normalized, spans, provenance, structured_vision, limit=max_claims or self.max_claims)
        entities = self._entities(normalized, spans, claims, structured_vision, limit=max_entities or self.max_entities)
        relationships = self._relationships(normalized, spans, entities, claims, structured_vision, limit=max_relationships or self.max_relationships)
        context_result = self._context_sufficiency(normalized, query_text, context, retrieval_info, vision_info)
        all_uncertainty = self._uncertainties(normalized, context_result, claims, retrieval_info, vision_info)
        artifact = EvidenceArtifact(
            normalized_source=normalized,
            context_sufficiency=context_result,
            claims=claims,
            entities=entities,
            relationships=relationships,
            evidence_spans=spans,
            provenance=provenance,
            uncertainty=all_uncertainty,
            diagnostics=diagnostics,
            retrieval=retrieval_info,
            vision=vision_info,
            metadata={
                "built_at": utc_now(),
                "input_kind": raw_input.kind,
                "query": query_text,
                "include_source_text": bool(include_source_text),
                "source_characters": len(normalized.text),
                "chunk_count": len(_chunk_items(normalized)),
                "claim_count": len(claims),
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "network_accessed": bool(retrieval_info.get("network_accessed")),
                **dict(metadata or {}),
            },
        )
        result = artifact.to_dict()
        if not include_source_text:
            try:
                result["normalized_source"]["text"] = ""
            except (KeyError, TypeError):
                pass
        return result

    @staticmethod
    def _claims(source: NormalizedSource, spans: Sequence[EvidenceSpan], provenance: Sequence[Provenance], structured: Sequence[Any], *, limit: int) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        seen: set[str] = set()
        prov_ids = [item.id for item in provenance]
        for span in spans:
            text = _text(span.text, 8000)
            if len(re.sub(r"\W", "", text)) < 3:
                continue
            key = re.sub(r"\s+", " ", text).lower()
            if key in seen:
                continue
            seen.add(key)
            uncertainty = _claim_uncertainty(text, source_ref=span.id)
            claims.append(EvidenceClaim(text=text, claim_type=ClaimType.SOURCE_FACT.value, source_refs=[span.id], evidence_span_ids=[span.id], confidence=0.94 if uncertainty is None else 0.72, uncertainty=uncertainty, provenance_ids=prov_ids, numbers=_number_records(text, source_ref=span.id), metadata={"source_id": source.id}))
            if len(claims) >= limit:
                break
        # Structured adapter claims augment (but never replace) local source
        # claims.  Their explicit type is preserved for QA and narration.
        for raw in structured:
            if len(claims) >= limit:
                break
            if isinstance(raw, Mapping):
                text = _mapping_value(raw, "text", "claim", "statement", "description", default="")
                claim_type = _claim_type(_mapping_value(raw, "claim_type", "type", "classification", default=ClaimType.SOURCE_FACT.value))
                confidence = _mapping_value(raw, "confidence", "score", default=0.65)
                refs = _list_strings(_mapping_value(raw, "source_refs", "evidence", "references", default=[]))
                metadata = {str(key): value for key, value in raw.items() if key not in {"text", "claim", "statement", "description", "claim_type", "type", "classification", "confidence", "score", "source_refs", "evidence", "references"}}
            else:
                text, claim_type, confidence, refs, metadata = _text(raw), ClaimType.MODEL_EXPLANATION.value, 0.55, [], {"adapter_observation": True}
            text = _text(text)
            if not text:
                continue
            key = re.sub(r"\s+", " ", text).lower()
            if key in seen:
                continue
            seen.add(key)
            span = next((item for item in spans if item.id in refs), None)
            claims.append(EvidenceClaim(text=text, claim_type=claim_type, source_refs=refs or ([span.id] if span else []), evidence_span_ids=[span.id] if span else [], confidence=float(confidence or 0.0), uncertainty=None if claim_type in {ClaimType.SOURCE_FACT.value, ClaimType.UNKNOWN.value} else Uncertainty(level="medium", score=0.45, reason="Adapter-derived interpretation is not a verbatim source fact.", scope="claim", kind="derived_observation"), provenance_ids=prov_ids, numbers=_number_records(text, source_ref=span.id if span else ""), metadata=metadata))
        return claims

    @staticmethod
    def _entities(source: NormalizedSource, spans: Sequence[EvidenceSpan], claims: Sequence[EvidenceClaim], structured: Sequence[Any], *, limit: int) -> list[EvidenceEntity]:
        entities_by_key: OrderedDict[str, EvidenceEntity] = OrderedDict()
        span_by_id = {span.id: span for span in spans}
        for span in spans:
            for label, start, end, entity_type in _entity_candidates(span.text):
                key = re.sub(r"\s+", " ", label).lower()
                if key in entities_by_key:
                    entity = entities_by_key[key]
                else:
                    entity = EvidenceEntity(label=label, entity_type=entity_type, source_refs=[span.id], confidence=0.72 if entity_type != EntityType.UNKNOWN.value else 0.52, provenance_ids=[])
                    entities_by_key[key] = entity
                if span.id not in entity.source_refs:
                    entity.source_refs.append(span.id)
                if len(entities_by_key) >= limit:
                    break
            if len(entities_by_key) >= limit:
                break
        for raw in structured:
            if len(entities_by_key) >= limit:
                break
            if not isinstance(raw, Mapping):
                continue
            label = _mapping_value(raw, "label", "name", "entity", "text", default="")
            label = _text(label, 200)
            if not label:
                continue
            key = re.sub(r"\s+", " ", label).lower()
            entity = entities_by_key.get(key)
            if entity is None:
                entity = EvidenceEntity(label=label, entity_type=_mapping_value(raw, "entity_type", "type", default=EntityType.UNKNOWN.value), source_refs=_list_strings(_mapping_value(raw, "source_refs", "evidence", default=[])), confidence=float(_mapping_value(raw, "confidence", "score", default=0.6) or 0.0), attributes=dict(_mapping_value(raw, "attributes", "metadata", default={}) or {}))
                entities_by_key[key] = entity
        return list(entities_by_key.values())[:limit]

    @staticmethod
    def _relationships(source: NormalizedSource, spans: Sequence[EvidenceSpan], entities: list[EvidenceEntity], claims: Sequence[EvidenceClaim], structured: Sequence[Any], *, limit: int) -> list[EvidenceRelationship]:
        relationships: OrderedDict[str, EvidenceRelationship] = OrderedDict()
        for span in spans:
            sentence = span.text
            for match in _RELATION_PATTERN.finditer(sentence):
                left = _entity_for_fragment(match.group("left"), entities, create=False)
                right = _entity_for_fragment(match.group("right"), entities, create=False)
                if left is None or right is None or left.id == right.id:
                    # Restrict auto relations to entities that appear in this
                    # sentence; avoid inventing links between distant spans.
                    local = [entity for entity in entities if entity.label.lower() in sentence.lower()]
                    if len(local) >= 2:
                        left, right = local[0], local[1]
                if left is None or right is None or left.id == right.id:
                    continue
                predicate = _text(match.group("predicate"), 80).lower()
                relation = EvidenceRelationship(subject_id=left.id, predicate=predicate, object_id=right.id, relationship_type=_relationship_type(predicate), source_refs=[span.id], evidence_span_ids=[span.id], confidence=0.8, metadata={"extraction": "pattern"})
                relationships.setdefault(relation.id, relation)
            if len(relationships) >= limit:
                break
        for raw in structured:
            if len(relationships) >= limit:
                break
            if not isinstance(raw, Mapping):
                continue
            subject = _mapping_value(raw, "subject_id", "subject", "from", "source", default="")
            object_ = _mapping_value(raw, "object_id", "object", "to", "target", default="")
            predicate = _text(_mapping_value(raw, "predicate", "relation", "relationship", "type", default="related_to"), 100)
            left = _entity_for_fragment(str(subject), entities, create=True)
            right = _entity_for_fragment(str(object_), entities, create=True)
            if left is None or right is None:
                continue
            relation = EvidenceRelationship(subject_id=left.id, predicate=predicate, object_id=right.id, relationship_type=_relationship_type(predicate), source_refs=_list_strings(_mapping_value(raw, "source_refs", "evidence", "references", default=[])), confidence=float(_mapping_value(raw, "confidence", "score", default=0.65) or 0.0), metadata={"extraction": "adapter"})
            relationships.setdefault(relation.id, relation)
        return list(relationships.values())[:limit]

    @staticmethod
    def _context_sufficiency(source: NormalizedSource, query: str, context: Any, retrieval: Mapping[str, Any], vision: Mapping[str, Any]) -> ContextSufficiency:
        available: list[str] = []
        required: list[str] = []
        missing: list[str] = []
        if query:
            required.append("query_context")
            available.append("query_context")
        if source.text.strip():
            available.extend(["source_text", "evidence_spans"])
        if retrieval.get("success"):
            available.append("retrieved_content")
        if vision.get("success"):
            available.append("vision_observation")
        if source.source_type == SourceKind.URL.value:
            required.append("retrieved_content")
            if not retrieval.get("success"):
                missing.append("retrieved_content")
        if source.source_type in {SourceKind.IMAGE.value, SourceKind.SCREENSHOT.value}:
            required.append("visual_interpretation")
            if not vision.get("success"):
                missing.append("visual_interpretation")
        if context:
            available.append("caller_context")
        if not source.text.strip() and not context:
            missing.append("readable_content")
        score = 0.0
        if source.text.strip():
            score += 0.65
        if context:
            score += 0.15
        if retrieval.get("success") or vision.get("success"):
            score += 0.2
        score = min(1.0, score)
        if not missing and score >= 0.75:
            status = "sufficient"
        elif source.text.strip() or context or retrieval.get("success") or vision.get("success"):
            status = "partial"
        else:
            status = "insufficient"
        reason = "Context contains grounded readable material."
        if missing:
            reason = "Missing: " + ", ".join(missing) + "."
        return ContextSufficiency(status=status, score=score, query=query, required=required, available=available, missing=missing, reason=reason, uncertainty=[Uncertainty(level="high" if status == "insufficient" else "medium", score=1.0 - score, reason=reason, scope="context", kind="missing_context")] if missing else [])

    @staticmethod
    def _uncertainties(source: NormalizedSource, context: ContextSufficiency, claims: Sequence[EvidenceClaim], retrieval: Mapping[str, Any], vision: Mapping[str, Any]) -> list[Uncertainty]:
        result: list[Uncertainty] = []
        for raw in source.uncertainty:
            item = raw if isinstance(raw, Uncertainty) else Uncertainty(**{key: value for key, value in raw.items() if key in Uncertainty.__dataclass_fields__}) if isinstance(raw, Mapping) else Uncertainty(reason=str(raw), scope="source")
            result.append(item)
        for raw in context.uncertainty:
            item = raw if isinstance(raw, Uncertainty) else Uncertainty(**{key: value for key, value in raw.items() if key in Uncertainty.__dataclass_fields__}) if isinstance(raw, Mapping) else Uncertainty(reason=str(raw), scope="context")
            result.append(item)
        for claim in claims:
            if claim.uncertainty is not None:
                item = claim.uncertainty if isinstance(claim.uncertainty, Uncertainty) else Uncertainty(**{key: value for key, value in claim.uncertainty.items() if key in Uncertainty.__dataclass_fields__}) if isinstance(claim.uncertainty, Mapping) else Uncertainty(reason=str(claim.uncertainty), scope="claim")
                result.append(item)
        if retrieval.get("error"):
            result.append(Uncertainty(level="high", score=0.9, reason=str(retrieval["error"]), scope="retrieval", kind="adapter_failure"))
        if vision.get("error"):
            result.append(Uncertainty(level="high", score=0.9, reason=str(vision["error"]), scope="vision", kind="adapter_failure"))
        unique: OrderedDict[str, Uncertainty] = OrderedDict()
        for item in result:
            key = stable_id("uncertainty", {"level": item.level, "scope": item.scope, "reason": item.reason, "kind": item.kind})
            unique.setdefault(key, item)
        return list(unique.values())


EvidenceEngine = EvidenceBuilder
build_evidence = EvidenceBuilder().build


__all__ = [
    "EvidenceBuilder", "EvidenceEngine", "build_evidence",
    "RetrievalAdapter", "VisionAdapter",
]
