"""Safe local extraction for documents accepted by the Video Flow composer."""

from __future__ import annotations

import base64
import binascii
import html
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".rtf"}
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | {".docx", ".pdf"}

# Output / expansion budgets (defense in depth behind the 8 MB input cap).
MAX_EXTRACTED_TEXT_CHARS = 2_000_000
MAX_PDF_PAGES = 200
MAX_PDF_CHARS_PER_PAGE = 50_000
MAX_DOCX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_DOCX_ARCHIVE_MEMBERS = 1000
MAX_DOCUMENT_XML_BYTES = 32 * 1024 * 1024
_MAX_FILENAME_CHARS = 255


def extract_document_text(file_name: str, encoded_content: str) -> str:
    """Decode and extract a supported document without writing it to disk."""
    name = file_name if isinstance(file_name, str) else str(file_name or "")
    _validate_file_name(name)
    suffix = Path(name).suffix.lower()
    if suffix not in DOCUMENT_EXTENSIONS:
        raise ValueError("Unsupported document. Use TXT, Markdown, CSV, JSON, HTML, XML, RTF, DOCX, or PDF.")
    payload = encoded_content if isinstance(encoded_content, str) else str(encoded_content or "")
    # Tolerate data-URL prefixes ("data:...;base64,...") and MIME
    # line-wrapped base64; both previously raised "not valid base64".
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    payload = re.sub(r"\s+", "", payload)
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("Document payload is not valid base64.") from exc
    # Validate wire size BEFORE decoding to text: base64 inflates ~33%, so a
    # text-length check alone would let ~10.6 MB of heap through the 8 MB cap.
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document is larger than 8 MB.")
    if not raw:
        raise ValueError("Document is empty.")

    if suffix == ".docx":
        text = _extract_docx(raw)
    elif suffix == ".pdf":
        text = _extract_pdf(raw)
    else:
        text = _extract_text(raw, suffix)
    if len(text) > MAX_EXTRACTED_TEXT_CHARS:
        raise ValueError("Document text exceeds the extraction limit.")
    clean = text.replace("\x00", "").strip()
    if not clean:
        raise ValueError("No readable text was found in the document.")
    return clean


def _validate_file_name(name: str) -> None:
    """Reject filenames that are empty, traversal/absolute, or overlong.

    The name is only used for suffix dispatch (never a filesystem path),
    but rejecting traversal patterns here keeps hostile names out of logs,
    UI labels, and any future caller that does join paths with them.
    """
    if not name or not name.strip():
        raise ValueError("Document file name is required.")
    if len(name) > _MAX_FILENAME_CHARS:
        raise ValueError("Document file name is too long.")
    if "\x00" in name:
        raise ValueError("Document file name is invalid.")
    normalized = name.replace("\\", "/").strip()
    if (
        normalized.startswith("/")
        or normalized.startswith("~/")
        or normalized == "~"
        or ".." in normalized.split("/")
        or ":" in normalized
        or re.search(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)", normalized.split("/")[-1])
    ):
        raise ValueError("Document file name is invalid.")


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_ARCHIVE_MEMBERS:
                raise ValueError("The DOCX archive has too many entries.")
            # Zip-bomb guard: cap total uncompressed size before extracting.
            total_uncompressed = sum(m.file_size for m in members)
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("The DOCX archive expands beyond the extraction limit.")
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise ValueError("The DOCX file is damaged or not a Word document.") from exc
            if info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise ValueError("The DOCX document part is too large.")
            document = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError("The DOCX file is damaged or not a Word document.") from exc
    _reject_xml_bombs(document)
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("The DOCX file is damaged or not a Word document.") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(namespace + "p"):
        pieces = [node.text or "" for node in paragraph.iter(namespace + "t")]
        joined = "".join(pieces).strip()
        if joined:
            paragraphs.append(joined)
            if sum(len(p) for p in paragraphs) > MAX_EXTRACTED_TEXT_CHARS:
                raise ValueError("Document text exceeds the extraction limit.")
    return "\n\n".join(paragraphs)


def _reject_xml_bombs(document: bytes) -> None:
    """Reject entity-expansion (billion laughs) and external-entity payloads.

    xml.etree does not resolve external entities, but internal entity
    expansion ("billion laughs") can still exhaust memory, so any
    <!ENTITY declaration is refused outright.
    """
    head = document[:1_048_576].lstrip()
    if re.search(rb"(?i)<!ENTITY\b", head):
        raise ValueError("The DOCX file contains unsafe XML entities.")
    if re.search(rb"(?i)<!DOCTYPE[^>]*\[", head):
        raise ValueError("The DOCX file contains an unsafe XML doctype.")


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires the pypdf package.") from exc
    try:
        reader = PdfReader(io.BytesIO(raw))
        if getattr(reader, "is_encrypted", False):
            raise ValueError("The PDF is encrypted and cannot be read.")
        pages = []
        total = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            extracted = (page.extract_text() or "").strip()
            if not extracted:
                continue
            if len(extracted) > MAX_PDF_CHARS_PER_PAGE:
                extracted = extracted[:MAX_PDF_CHARS_PER_PAGE]
            total += len(extracted)
            if total > MAX_EXTRACTED_TEXT_CHARS:
                raise ValueError("Document text exceeds the extraction limit.")
            pages.append(extracted)
        return "\n\n".join(pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The PDF could not be read. Scanned PDFs need OCR before Video Flow can use them.") from exc


def _extract_text(raw: bytes, suffix: str) -> str:
    if b"\x00" in raw[:8192]:
        # Binary content mislabelled with a text suffix (executables,
        # images, null-padded blobs) — refuse instead of emitting mojibake.
        raise ValueError("No readable text was found in the document.")
    text = raw.decode("utf-8-sig", errors="replace")
    if suffix == ".json":
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, RecursionError, ValueError):
            return text
    if suffix in {".html", ".htm", ".xml"}:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|br)>", "\n", text)
        return html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    if suffix == ".rtf":
        text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
        text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
        return text.replace("{", "").replace("}", "")
    return text
