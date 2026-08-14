"""Source adapters and deterministic normalization for Video Flow.

Adapters in this module are intentionally local and side-effect free.  URL
inputs are metadata until a caller injects a retrieval adapter; image inputs
are metadata until a caller injects a vision adapter.  This keeps the default
desktop app offline while giving integrations a stable seam for richer
ingestion later.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable
from urllib.parse import urlparse

from .contracts import (
    EvidenceSpan,
    NormalizedSource,
    Provenance,
    SourceChunk,
    SourceInput,
    SourceKind,
    Uncertainty,
    content_hash,
    normalize_source_kind,
    stable_id,
    utc_now,
)


MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
DEFAULT_CHUNK_CHARS = 1_200
DEFAULT_CHUNK_OVERLAP = 100
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico"}
_DOCUMENT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xml", ".rtf",
    ".docx", ".pdf", ".log", ".yaml", ".yml", ".toml",
}


@runtime_checkable
class SourceAdapter(Protocol):
    """Adapter protocol implemented by local and future source handlers."""

    name: str

    def can_handle(self, source: SourceInput) -> bool:
        ...

    def normalize(self, source: SourceInput, **kwargs: Any) -> NormalizedSource:
        ...


@runtime_checkable
class RetrievalAdapter(Protocol):
    """A caller-owned, explicitly injected URL retrieval seam.

    Implementations may expose ``retrieve``, ``fetch``, or be callable; the
    evidence builder supports all three shapes.  No implementation here makes
    a network request.
    """

    def retrieve(self, url: str, **kwargs: Any) -> Any:
        ...


@runtime_checkable
class VisionAdapter(Protocol):
    """A caller-owned image/OCR/vision seam."""

    def analyze(self, image: Any, **kwargs: Any) -> Any:
        ...


class SourceAdapterError(ValueError):
    """Raised when a source is understood but cannot be normalized safely."""


class UnsupportedSourceError(SourceAdapterError):
    pass


def _safe_text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    # Keep evidence offsets predictable: trim only line transport noise, not
    # interior spaces or punctuation that may carry meaning.
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text[:limit]


def _language_hint(text: str) -> str:
    if not text.strip():
        return "und"
    # This is deliberately conservative.  A later language detector can
    # replace the hint without changing the contract.
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return "und"
    ascii_letters = sum(char.isascii() for char in letters)
    return "en" if ascii_letters / max(1, len(letters)) >= 0.88 else "und"


def _structure_hints(text: str) -> dict[str, Any]:
    lines = text.splitlines() if text else []
    headings: list[str] = []
    bullets = 0
    numbered = 0
    tables = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,6}\s+", stripped):
            headings.append(re.sub(r"^#{1,6}\s+", "", stripped)[:200])
        if re.match(r"^(?:[-*+]\s+|•\s+)", stripped):
            bullets += 1
        if re.match(r"^\d+[.)]\s+", stripped):
            numbered += 1
        if stripped.count("|") >= 2 or "\t" in line:
            tables += 1
    return {
        "line_count": len(lines),
        "paragraph_count": len([item for item in re.split(r"\n\s*\n", text) if item.strip()]),
        "heading_count": len(headings),
        "headings": headings[:50],
        "bullet_count": bullets,
        "numbered_item_count": numbered,
        "table_like_line_count": tables,
    }


def _sentence_ranges(text: str) -> list[tuple[int, int]]:
    """Find stable, human-readable spans without a heavyweight NLP package."""

    if not text:
        return []
    ranges: list[tuple[int, int]] = []
    # A line break is a useful boundary for bullets/headings; punctuation is a
    # boundary unless it is likely part of a decimal or abbreviation.
    pattern = re.compile(r"[^\n.!?]+(?:[.!?]+(?=\s|$)|(?=\n|$))", re.MULTILINE)
    for match in pattern.finditer(text):
        start, end = match.span()
        snippet = text[start:end].strip()
        if not snippet:
            continue
        leading = len(text[start:end]) - len(text[start:end].lstrip())
        trailing = len(text[start:end].rstrip())
        start += leading
        end = start + max(0, trailing - leading)
        if end > start:
            ranges.append((start, end))
    if not ranges and text.strip():
        start = len(text) - len(text.lstrip())
        end = len(text.rstrip())
        ranges.append((start, end))
    return ranges


def _make_spans(source_id: str, text: str, *, locator_prefix: str = "text") -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for index, (start, end) in enumerate(_sentence_ranges(text)[:500]):
        quote = text[start:end]
        spans.append(
            EvidenceSpan(
                id=stable_id("span", {"source": source_id, "start": start, "end": end, "quote": quote}),
                source_id=source_id,
                start=start,
                end=end,
                text=quote,
                locator=f"{locator_prefix}:{index}",
            )
        )
    return spans


def _make_chunks(
    source_id: str,
    text: str,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[SourceChunk]:
    if not text:
        return []
    max_chars = max(100, int(max_chars))
    overlap = max(0, min(int(overlap), max_chars // 2))
    chunks: list[SourceChunk] = []
    cursor = 0
    index = 0
    while cursor < len(text):
        limit = min(len(text), cursor + max_chars)
        end = limit
        if limit < len(text):
            # Prefer paragraph, line, then whitespace boundaries to splitting a
            # number or a quote in the middle.
            candidates = [text.rfind("\n\n", cursor + max_chars // 2, limit), text.rfind("\n", cursor + max_chars // 2, limit), text.rfind(" ", cursor + max_chars // 2, limit)]
            end = max([candidate for candidate in candidates if candidate > cursor] or [limit])
            if end <= cursor:
                end = limit
        raw_start, raw_end = cursor, end
        chunk_text = text[raw_start:raw_end].strip()
        left_trim = len(text[raw_start:raw_end]) - len(text[raw_start:raw_end].lstrip())
        right_trim = len(text[raw_start:raw_end].rstrip())
        actual_start = raw_start + left_trim
        actual_end = raw_start + right_trim
        if chunk_text:
            chunks.append(SourceChunk(source_id=source_id, index=index, text=chunk_text, start=actual_start, end=actual_end, overlap=overlap if index else 0))
            index += 1
        if end >= len(text):
            break
        cursor = max(end - overlap, cursor + 1)
    return chunks


def _provenance(
    source: SourceInput,
    *,
    source_id: str,
    adapter: str,
    method: str,
    payload_hash: str,
    metadata: Mapping[str, Any] | None = None,
) -> Provenance:
    return Provenance(
        source_id=source_id,
        kind="source",
        adapter=adapter,
        method=method,
        uri=source.uri,
        retrieved_at=utc_now(),
        content_hash=payload_hash,
        metadata={**dict(source.metadata or {}), **dict(metadata or {})},
    )


def _normalized(
    source: SourceInput,
    *,
    text: str,
    original_payload: Any,
    adapter: str,
    method: str,
    source_type: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    uncertainty: Sequence[Uncertainty] | None = None,
    locator_prefix: str = "text",
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> NormalizedSource:
    clean = _safe_text(text)
    kind = normalize_source_kind(source_type or source.kind)
    original_hash = content_hash(original_payload)
    # Source ID intentionally uses content and URI, not adapter name, so a
    # retrieved URL and a cached retrieval remain referentially compatible.
    source_id = stable_id("source", {"kind": kind, "hash": original_hash, "uri": source.uri})
    provenance = _provenance(source, source_id=source_id, adapter=adapter, method=method, payload_hash=original_hash, metadata=metadata)
    chunks = _make_chunks(source_id, clean, max_chars=max_chars, overlap=overlap)
    spans = _make_spans(source_id, clean, locator_prefix=locator_prefix)
    result = NormalizedSource(
        id=source_id,
        source_type=kind,
        source_name=source.name,
        uri=source.uri,
        original_hash=original_hash,
        normalized_hash=content_hash(clean),
        text=clean,
        language=_language_hint(clean),
        chunks=chunks,
        structure_hints=_structure_hints(clean),
        evidence_spans=spans,
        provenance=[provenance],
        uncertainty=list(uncertainty or []),
        metadata={**dict(source.metadata or {}), **dict(metadata or {})},
    )
    return result


class TextSourceAdapter:
    name = "local.text"

    def can_handle(self, source: SourceInput) -> bool:
        return normalize_source_kind(source.kind) == SourceKind.TEXT.value

    def normalize(self, source: SourceInput, **kwargs: Any) -> NormalizedSource:
        text = source.value
        if isinstance(text, Mapping):
            text = text.get("text") or text.get("content") or ""
        clean = _safe_text(text)
        if not clean:
            raise SourceAdapterError("Text source is empty.")
        return _normalized(
            source,
            text=clean,
            original_payload=text,
            adapter=self.name,
            method="normalize_text",
            metadata={"transport": "text"},
            max_chars=kwargs.get("chunk_chars", DEFAULT_CHUNK_CHARS),
            overlap=kwargs.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP),
        )


class UrlSourceAdapter:
    name = "local.url"

    def can_handle(self, source: SourceInput) -> bool:
        return normalize_source_kind(source.kind) == SourceKind.URL.value

    def normalize(self, source: SourceInput, **kwargs: Any) -> NormalizedSource:
        url = _safe_text(source.uri or source.value, limit=8192)
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise SourceAdapterError("URL source must use an absolute http(s) URL.")
        safe_uri = parsed._replace(fragment="").geturl()
        source = SourceInput(kind=SourceKind.URL.value, value=url, name=source.name or parsed.netloc, mime_type=source.mime_type, uri=safe_uri, encoding=source.encoding, metadata=source.metadata)
        unresolved = [Uncertainty(level="high", score=0.9, reason="URL content has not been retrieved; inject a RetrievalAdapter to ground evidence.", scope="source", kind="missing_context")]
        return _normalized(
            source,
            text="",
            original_payload=safe_uri,
            adapter=self.name,
            method="validate_url",
            metadata={"retrieval_required": True, "network_accessed": False, "hostname": parsed.hostname or ""},
            uncertainty=unresolved,
            locator_prefix="url",
            max_chars=kwargs.get("chunk_chars", DEFAULT_CHUNK_CHARS),
            overlap=kwargs.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP),
        )


def _coerce_bytes(value: Any, *, encoding: str | None = None, max_bytes: int = MAX_DOCUMENT_BYTES) -> bytes:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, (bytearray, memoryview)):
        raw = bytes(value)
    elif isinstance(value, Path):
        try:
            raw = value.read_bytes()
        except OSError as exc:
            raise SourceAdapterError(f"Could not read source file: {exc}") from exc
    elif isinstance(value, str):
        candidate = Path(value)
        if not encoding and candidate.exists() and candidate.is_file():
            try:
                raw = candidate.read_bytes()
            except OSError as exc:
                raise SourceAdapterError(f"Could not read source file: {exc}") from exc
        else:
            raw = value.encode("utf-8")
        if encoding and encoding.lower().replace("-", "") in {"base64", "b64"}:
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise SourceAdapterError("Document payload is not valid base64.") from exc
    else:
        raise SourceAdapterError("Document payload must be bytes, a path, or text.")
    if len(raw) > max_bytes:
        raise SourceAdapterError(f"Source exceeds the {max_bytes // (1024 * 1024)} MB safety limit.")
    if not raw:
        raise SourceAdapterError("Source payload is empty.")
    return raw


class ImageSourceAdapter:
    name = "local.image"

    def can_handle(self, source: SourceInput) -> bool:
        kind = normalize_source_kind(source.kind)
        if kind in {SourceKind.IMAGE.value, SourceKind.SCREENSHOT.value}:
            return True
        mime = str(source.mime_type or "").lower()
        return mime.startswith("image/")

    def normalize(self, source: SourceInput, **kwargs: Any) -> NormalizedSource:
        raw = _coerce_bytes(source.value, encoding=source.encoding, max_bytes=kwargs.get("max_bytes", MAX_IMAGE_BYTES))
        image_metadata: dict[str, Any] = {"byte_size": len(raw), "network_accessed": False, "vision_required": True}
        # Pillow is already a Video Flow dependency, but imports stay optional
        # so source contracts can be used in a minimal worker process.
        try:
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as image:
                image_metadata.update({"format": str(image.format or "").lower(), "width": int(image.width), "height": int(image.height), "mode": str(image.mode or "")})
        except Exception:
            image_metadata.setdefault("format", str(source.mime_type or "").removeprefix("image/") or "unknown")
        # Keep the raw payload out of the artifact.  Vision adapters can still
        # receive it via ``source.value`` in EvidenceBuilder.
        unresolved = [Uncertainty(level="high", score=0.85, reason="Image meaning and text require an injected VisionAdapter.", scope="source", kind="missing_context")]
        source_type = SourceKind.SCREENSHOT.value if normalize_source_kind(source.kind) == SourceKind.SCREENSHOT.value else SourceKind.IMAGE.value
        return _normalized(
            source,
            text="",
            original_payload=raw,
            adapter=self.name,
            method="inspect_image",
            source_type=source_type,
            metadata=image_metadata,
            uncertainty=unresolved,
            locator_prefix="image",
            max_chars=kwargs.get("chunk_chars", DEFAULT_CHUNK_CHARS),
            overlap=kwargs.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP),
        )


class DocumentSourceAdapter:
    name = "local.document"

    def __init__(self, extractor: Callable[[str, str], str] | None = None) -> None:
        self.extractor = extractor

    def can_handle(self, source: SourceInput) -> bool:
        kind = normalize_source_kind(source.kind)
        if kind in {SourceKind.DOCUMENT.value, SourceKind.PDF.value}:
            return True
        suffix = Path(source.name or str(source.value or "")).suffix.lower()
        return suffix in _DOCUMENT_EXTENSIONS or str(source.mime_type or "").lower() in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

    def normalize(self, source: SourceInput, **kwargs: Any) -> NormalizedSource:
        file_name = source.name or str(source.value if isinstance(source.value, Path) else "source.txt")
        suffix = Path(file_name).suffix.lower()
        if not suffix:
            mime = str(source.mime_type or "").lower()
            suffix = ".pdf" if mime == "application/pdf" else ".txt"
            file_name += suffix
        raw = _coerce_bytes(source.value, encoding=source.encoding, max_bytes=kwargs.get("max_bytes", MAX_DOCUMENT_BYTES))
        encoded = base64.b64encode(raw).decode("ascii")
        try:
            if self.extractor:
                text = self.extractor(file_name, encoded)
            else:
                # Reuse the established Video Flow extractor when available.
                from voice_flow.video_flow_documents import extract_document_text

                text = extract_document_text(file_name, encoded)
        except ImportError:
            text = self._fallback_text(raw, suffix)
        except RuntimeError:
            # pypdf is optional in some worker environments.  A PDF without
            # extraction support remains explicitly uncertain, never invented.
            if suffix == ".pdf":
                text = ""
            else:
                text = self._fallback_text(raw, suffix)
        except (ValueError, UnicodeError) as exc:
            if suffix == ".pdf":
                text = ""
            else:
                raise SourceAdapterError(str(exc)) from exc
        clean = _safe_text(text)
        uncertainties: list[Uncertainty] = []
        if not clean:
            uncertainties.append(Uncertainty(level="high", score=0.95, reason="No readable text was extracted; scanned or encrypted documents may need OCR.", scope="source", kind="extraction_failure"))
        metadata = {"file_name": file_name, "suffix": suffix, "byte_size": len(raw), "network_accessed": False, "extraction": "local"}
        source_type = SourceKind.PDF.value if suffix == ".pdf" else SourceKind.DOCUMENT.value
        return _normalized(
            source,
            text=clean,
            original_payload=raw,
            adapter=self.name,
            method="extract_document",
            source_type=source_type,
            metadata=metadata,
            uncertainty=uncertainties,
            locator_prefix="document",
            max_chars=kwargs.get("chunk_chars", DEFAULT_CHUNK_CHARS),
            overlap=kwargs.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP),
        )

    @staticmethod
    def _fallback_text(raw: bytes, suffix: str) -> str:
        if suffix in {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xml", ".rtf", ".log", ".yaml", ".yml", ".toml"}:
            return raw.decode("utf-8-sig", errors="replace")
        return ""


class SourceNormalizer:
    """Registry-backed source normalization with safe local defaults."""

    def __init__(self, adapters: Sequence[SourceAdapter] | None = None) -> None:
        self.adapters: list[SourceAdapter] = list(adapters or (TextSourceAdapter(), UrlSourceAdapter(), ImageSourceAdapter(), DocumentSourceAdapter()))

    def register(self, adapter: SourceAdapter, *, first: bool = False) -> None:
        if first:
            self.adapters.insert(0, adapter)
        else:
            self.adapters.append(adapter)

    def adapter_for(self, source: SourceInput) -> SourceAdapter:
        for adapter in self.adapters:
            try:
                if adapter.can_handle(source):
                    return adapter
            except Exception:
                continue
        raise UnsupportedSourceError(f"Unsupported source kind: {source.kind}")

    def normalize(self, source: Any, *, kind: str | None = None, **kwargs: Any) -> NormalizedSource:
        normalized_input = SourceInput.from_any(source, kind=kind)
        adapter = self.adapter_for(normalized_input)
        return adapter.normalize(normalized_input, **kwargs)


DefaultSourceNormalizer = SourceNormalizer


def normalize_source(source: Any, *, kind: str | None = None, normalizer: SourceNormalizer | None = None, **kwargs: Any) -> NormalizedSource:
    """Convenience function for callers that do not need a custom registry."""

    return (normalizer or SourceNormalizer()).normalize(source, kind=kind, **kwargs)


class NoopRetrievalAdapter:
    """Explicitly offline adapter useful in tests and local-only deployments."""

    name = "none"

    def retrieve(self, url: str, **_: Any) -> None:
        return None


class NoopVisionAdapter:
    name = "none"

    def analyze(self, image: Any, **_: Any) -> None:
        return None


__all__ = [
    "MAX_DOCUMENT_BYTES", "MAX_IMAGE_BYTES", "MAX_TEXT_CHARS",
    "SourceAdapter", "RetrievalAdapter", "VisionAdapter", "SourceAdapterError", "UnsupportedSourceError",
    "TextSourceAdapter", "UrlSourceAdapter", "ImageSourceAdapter", "DocumentSourceAdapter",
    "SourceNormalizer", "DefaultSourceNormalizer", "normalize_source",
    "NoopRetrievalAdapter", "NoopVisionAdapter",
]
