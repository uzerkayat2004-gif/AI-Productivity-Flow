"""Safe local extraction for documents accepted by the Video Flow composer."""

from __future__ import annotations

import base64
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


def extract_document_text(file_name: str, encoded_content: str) -> str:
    """Decode and extract a supported document without writing it to disk."""
    suffix = Path(file_name).suffix.lower()
    if suffix not in DOCUMENT_EXTENSIONS:
        raise ValueError("Unsupported document. Use TXT, Markdown, CSV, JSON, HTML, XML, RTF, DOCX, or PDF.")
    try:
        raw = base64.b64decode(encoded_content, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Document payload is not valid base64.") from exc
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
    clean = text.replace("\x00", "").strip()
    if not clean:
        raise ValueError("No readable text was found in the document.")
    return clean


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            document = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("The DOCX file is damaged or not a Word document.") from exc
    root = ElementTree.fromstring(document)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(namespace + "p"):
        pieces = [node.text or "" for node in paragraph.iter(namespace + "t")]
        joined = "".join(pieces).strip()
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires the pypdf package.") from exc
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            if extracted:
                pages.append(extracted)
        return "\n\n".join(pages)
    except Exception as exc:
        raise ValueError("The PDF could not be read. Scanned PDFs need OCR before Video Flow can use them.") from exc


def _extract_text(raw: bytes, suffix: str) -> str:
    text = raw.decode("utf-8-sig", errors="replace")
    if suffix == ".json":
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
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
