from __future__ import annotations

import base64
import hashlib
import struct
from pathlib import Path

import pytest

import voice_flow.nemotron_tokenizer as tokenizer_module
from voice_flow.nemotron_tokenizer import (
    GGUFError,
    fetch_official_nemotron_tokenizer_model,
    prepare_tokenizer_metadata_copy,
    read_gguf_metadata,
    sentencepiece_pieces,
)


def _varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _protobuf_piece(token: str) -> bytes:
    raw = token.encode("utf-8")
    inner = b"\x0a" + _varint(len(raw)) + raw
    return b"\x0a" + _varint(len(inner)) + inner


def _gguf_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _gguf_metadata(key: str, kind: int, payload: bytes) -> bytes:
    return _gguf_string(key) + struct.pack("<I", kind) + payload


def _synthetic_gguf(path: Path, vocab: list[str], *, spm: bytes | None = None) -> bytes:
    metadata = [
        _gguf_metadata("general.alignment", 5, struct.pack("<i", 32)),
        _gguf_metadata(
            "asr.tokenizer.vocab",
            9,
            struct.pack("<IQ", 8, len(vocab)) + b"".join(_gguf_string(token) for token in vocab),
        ),
    ]
    if spm is not None:
        metadata.append(_gguf_metadata("asr.tokenizer.spm_model", 8, _gguf_string(base64.b64encode(spm).decode("ascii"))))
    tensors = bytearray()
    for name, offset in (("tensor.one", 0), ("tensor.two", 4)):
        tensors += _gguf_string(name)
        tensors += struct.pack("<I", 1)  # dimensions
        tensors += struct.pack("<Q", 1)
        tensors += struct.pack("<I", 0)  # F32
        tensors += struct.pack("<Q", offset)
    header = b"GGUF" + struct.pack("<IQQ", 3, 2, len(metadata))
    prefix = header + b"".join(metadata) + tensors
    prefix += b"\0" * ((-len(prefix)) % 32)
    tensor_bytes = b"ABCDEFGH"
    path.write_bytes(prefix + tensor_bytes)
    return tensor_bytes


def test_sentencepiece_minimal_parser_reads_piece_strings() -> None:
    model = _protobuf_piece("▁hello") + _protobuf_piece("world")
    assert sentencepiece_pieces(model) == ["▁hello", "world"]


def test_repair_adds_only_metadata_and_preserves_tensor_data(tmp_path: Path) -> None:
    source = tmp_path / "source.gguf"
    tokenizer = tmp_path / "tokenizer.model"
    output = tmp_path / "prepared.gguf"
    original_tensor_bytes = _synthetic_gguf(source, ["▁hello", "world"])
    original_bytes = source.read_bytes()
    original_index = read_gguf_metadata(source)
    model = _protobuf_piece("▁hello") + _protobuf_piece("world")
    tokenizer.write_bytes(model)

    result = prepare_tokenizer_metadata_copy(source, tokenizer, output)

    parsed = read_gguf_metadata(output)
    assert result.added_metadata is True
    assert parsed.tensor_count == 2
    assert parsed.metadata["asr.tokenizer.vocab"] == ["▁hello", "world"]
    assert parsed.metadata["asr.tokenizer.spm_model"] == base64.b64encode(model).decode("ascii")
    assert output.read_bytes()[parsed.data_start:] == original_tensor_bytes
    assert output.read_bytes()[parsed.metadata_end:parsed.tensor_info_end] == original_bytes[
        original_index.metadata_end:original_index.tensor_info_end
    ]
    assert result.tensor_data_sha256 == hashlib.sha256(original_tensor_bytes).hexdigest()
    assert source.read_bytes() == original_bytes
    assert len(parsed.metadata) == 3


def test_repair_refuses_any_vocabulary_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.gguf"
    tokenizer = tmp_path / "tokenizer.model"
    output = tmp_path / "prepared.gguf"
    _synthetic_gguf(source, ["▁hello", "not-world"])
    tokenizer.write_bytes(_protobuf_piece("▁hello") + _protobuf_piece("world"))

    with pytest.raises(GGUFError, match="vocabulary mismatch"):
        prepare_tokenizer_metadata_copy(source, tokenizer, output)
    assert not output.exists()


def test_oversized_metadata_header_is_rejected_before_allocating(tmp_path: Path) -> None:
    malformed = tmp_path / "oversized.gguf"
    malformed.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 100_001))

    with pytest.raises(GGUFError, match="metadata count is excessive"):
        read_gguf_metadata(malformed)


def test_repair_is_idempotent_for_matching_embedded_model(tmp_path: Path) -> None:
    model = _protobuf_piece("▁hello") + _protobuf_piece("world")
    source = tmp_path / "already-repaired.gguf"
    tokenizer = tmp_path / "tokenizer.model"
    output = tmp_path / "copy.gguf"
    _synthetic_gguf(source, ["▁hello", "world"], spm=model)
    tokenizer.write_bytes(model)

    result = prepare_tokenizer_metadata_copy(source, tokenizer, output)

    assert result.added_metadata is False
    assert output.read_bytes() == source.read_bytes()


class _RangeResponse:
    def __init__(self, data: bytes, *, status: int = 206, content_range: str | None = None) -> None:
        self._data = data
        self._status = status
        self.headers = {
            "Content-Range": content_range or f"bytes 10-{9 + len(data)}/999999",
            "Content-Length": str(len(data)),
            "Content-Encoding": "identity",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self, size: int) -> bytes:
        return self._data[:size]


def _configure_fake_range(monkeypatch, data: bytes, *, status: int = 206, content_range: str | None = None) -> None:
    monkeypatch.setattr(tokenizer_module, "_OFFICIAL_TOKENIZER_OFFSET", 10)
    monkeypatch.setattr(tokenizer_module, "_OFFICIAL_TOKENIZER_SIZE", len(data))
    monkeypatch.setattr(tokenizer_module, "_OFFICIAL_TOKENIZER_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(
        tokenizer_module.urllib.request,
        "urlopen",
        lambda request, timeout: _RangeResponse(data, status=status, content_range=content_range),
    )


def test_pinned_range_fetch_requires_exact_partial_response_and_hash(monkeypatch) -> None:
    model = _protobuf_piece("token")
    _configure_fake_range(monkeypatch, model)

    assert fetch_official_nemotron_tokenizer_model() == model


@pytest.mark.parametrize(
    ("status", "content_range", "wrong_hash"),
    [
        (200, None, False),
        (206, "bytes 11-20/999999", False),
        (206, None, True),
    ],
)
def test_pinned_range_fetch_rejects_unverified_responses(monkeypatch, status, content_range, wrong_hash) -> None:
    model = _protobuf_piece("token")
    _configure_fake_range(monkeypatch, model, status=status, content_range=content_range)
    if wrong_hash:
        monkeypatch.setattr(tokenizer_module, "_OFFICIAL_TOKENIZER_SHA256", "0" * 64)

    assert fetch_official_nemotron_tokenizer_model() is None


def test_oversized_tokenizer_file_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "source.gguf"
    tokenizer = tmp_path / "too-large.model"
    output = tmp_path / "prepared.gguf"
    _synthetic_gguf(source, ["token"])
    tokenizer.write_bytes(b"x" * (tokenizer_module._OFFICIAL_TOKENIZER_SIZE * 2 + 1))

    with pytest.raises(GGUFError, match="bounded input size"):
        prepare_tokenizer_metadata_copy(source, tokenizer, output)
    assert not output.exists()


def test_repair_never_replaces_an_existing_destination(tmp_path: Path) -> None:
    model = _protobuf_piece("token")
    source = tmp_path / "source.gguf"
    tokenizer = tmp_path / "tokenizer.model"
    output = tmp_path / "prepared.gguf"
    _synthetic_gguf(source, ["token"])
    tokenizer.write_bytes(model)
    output.write_bytes(b"keep me")

    with pytest.raises(FileExistsError):
        prepare_tokenizer_metadata_copy(source, tokenizer, output)
    assert output.read_bytes() == b"keep me"
