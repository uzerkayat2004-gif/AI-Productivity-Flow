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


def test_rejects_path_traversal_file_name() -> None:
    for bad in ("../../etc/passwd.txt", "..\secret.txt", "/abs/path.txt", "C:\evil.txt", ""):
        with pytest.raises(ValueError, match="file name|Unsupported"):
            extract_document_text(bad, _encoded(b"hello"))


def test_rejects_binary_mislabeled_as_text() -> None:
    blob = b"\x7fELF\x02\x01" + b"\x00" * 64 + b"binary-body"
    with pytest.raises(ValueError, match="No readable text"):
        extract_document_text("notes.txt", _encoded(blob))


def test_rejects_docx_zip_bomb() -> None:
    document_xml = b"""<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hi</w:t></w:r></w:p></w:body></w:document>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("big.bin", b"\x00", compress_type=zipfile.ZIP_STORED)
        for info in archive.infolist():
            if info.filename == "big.bin":
                info.file_size = 128 * 1024 * 1024
    with pytest.raises(ValueError, match="expands|damaged"):
        extract_document_text("bomb.docx", _encoded(buffer.getvalue()))


def test_rejects_docx_xml_entity_bomb() -> None:
    document_xml = (
        b"""<?xml version="1.0"?><!DOCTYPE lolz ["""
        b"""<!ENTITY lol "lollollollol">"""
        b"""]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">"""
        b"""<w:body><w:p><w:r><w:t>&lol;</w:t></w:r></w:p></w:body></w:document>"""
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    with pytest.raises(ValueError, match="unsafe XML|damaged"):
        extract_document_text("entity.docx", _encoded(buffer.getvalue()))


def test_tolerates_data_url_and_wrapped_base64() -> None:
    raw = "Hello, Video Flow.".encode()
    standard = _encoded(raw)
    wrapped = "\n".join(standard[i : i + 64] for i in range(0, len(standard), 64))
    assert extract_document_text("notes.md", wrapped) == "Hello, Video Flow."
    assert extract_document_text("notes.md", "data:text/plain;base64," + standard) == "Hello, Video Flow."


def test_enforces_wire_size_cap() -> None:
    import voice_flow.video_flow_documents as docs

    big = b"a" * (docs.MAX_DOCUMENT_BYTES + 1)
    with pytest.raises(ValueError, match="larger than 8 MB"):
        extract_document_text("notes.txt", _encoded(big))
