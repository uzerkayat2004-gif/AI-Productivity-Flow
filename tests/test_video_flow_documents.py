from __future__ import annotations

import base64
import io
import zipfile

import pytest

from voice_flow.video_flow_documents import extract_document_text


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def test_extracts_utf8_text_document() -> None:
    assert extract_document_text("notes.md", _encoded("Hello, Video Flow.".encode())) == "Hello, Video Flow."


def test_extracts_docx_paragraphs_without_writing_to_disk() -> None:
    document_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>
      <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body>
    </w:document>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    assert extract_document_text("research.docx", _encoded(buffer.getvalue())) == "First paragraph\n\nSecond paragraph"


def test_rejects_unknown_document_types() -> None:
    with pytest.raises(ValueError, match="Unsupported document"):
        extract_document_text("program.exe", _encoded(b"not a document"))
