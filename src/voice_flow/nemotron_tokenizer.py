"""Bounded GGUF metadata inspection and Nemotron tokenizer repair helpers.

These helpers operate on model files as streams. They never load tensor weights
into memory and do not import the native Nemotron runtime.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import struct
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO


_HEADER_SIZE = 24
_MAX_METADATA_ENTRIES = 100_000
_MAX_TENSORS = 1_000_000
_MAX_STRING_BYTES = 16 * 1024 * 1024
_MAX_METADATA_BYTES = 16 * 1024 * 1024
_MAX_ARRAY_ITEMS = 100_000
_MAX_PROTO_PIECES = 1_000_000
_COPY_CHUNK = 1024 * 1024
_OFFICIAL_TOKENIZER_URL = (
    "https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/resolve/"
    "ebe59e5a817142986528bbbee5dba8db7b38ed50/"
    "nemotron-speech-streaming-en-0.6b.nemo"
)
_OFFICIAL_TOKENIZER_OFFSET = 21_504
_OFFICIAL_TOKENIZER_SIZE = 251_056
_OFFICIAL_TOKENIZER_SHA256 = "07d4e5a63840a53ab2d4d106d2874768143fb3fbdd47938b3910d2da05bfb0a9"


class GGUFError(ValueError):
    """A malformed or unsupported GGUF/tokenizer input."""


@dataclass(frozen=True)
class GGUFMetadata:
    version: int
    tensor_count: int
    metadata: dict[str, Any]
    alignment: int
    metadata_end: int
    tensor_info_end: int
    data_start: int
    file_size: int


@dataclass(frozen=True)
class RepairResult:
    output_path: Path
    added_metadata: bool
    tensor_data_sha256: str
    file_size: int


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    if size < 0 or size > _MAX_STRING_BYTES:
        raise GGUFError(f"Invalid or excessive field size: {size}")
    value = stream.read(size)
    if len(value) != size:
        raise GGUFError("Truncated GGUF or SentencePiece data")
    return value


def _read_u32(stream: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(stream, 4))[0]


def _read_u64(stream: BinaryIO) -> int:
    return struct.unpack("<Q", _read_exact(stream, 8))[0]


def _read_gguf_string(stream: BinaryIO) -> str:
    size = _read_u64(stream)
    if size > _MAX_STRING_BYTES:
        raise GGUFError(f"GGUF string too large: {size}")
    try:
        return _read_exact(stream, size).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GGUFError("GGUF string is not valid UTF-8") from exc


def _read_scalar(stream: BinaryIO, value_type: int) -> Any:
    formats = {
        0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
        6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d",
    }
    if value_type == 8:
        return _read_gguf_string(stream)
    fmt = formats.get(value_type)
    if fmt is None:
        raise GGUFError(f"Unsupported GGUF metadata value type: {value_type}")
    return struct.unpack(fmt, _read_exact(stream, struct.calcsize(fmt)))[0]


def _read_value(stream: BinaryIO, value_type: int) -> Any:
    if value_type != 9:
        return _read_scalar(stream, value_type)
    item_type = _read_u32(stream)
    count = _read_u64(stream)
    if count > _MAX_ARRAY_ITEMS:
        raise GGUFError(f"GGUF metadata array too large: {count}")
    if item_type == 9:
        raise GGUFError("Nested GGUF arrays are unsupported")
    values = []
    string_bytes = 0
    for _ in range(count):
        item = _read_scalar(stream, item_type)
        if isinstance(item, str):
            string_bytes += len(item.encode("utf-8"))
            if string_bytes > _MAX_METADATA_BYTES:
                raise GGUFError("GGUF metadata string array exceeds the bounded parsing limit")
        values.append(item)
    return values


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def read_gguf_metadata(path: str | os.PathLike[str]) -> GGUFMetadata:
    """Read GGUF header, metadata and tensor index without reading tensor bytes."""
    file_path = Path(path)
    file_size = file_path.stat().st_size
    with file_path.open("rb") as stream:
        if _read_exact(stream, 4) != b"GGUF":
            raise GGUFError("Invalid GGUF magic")
        version = _read_u32(stream)
        if version not in (2, 3):
            raise GGUFError(f"Unsupported GGUF version: {version}")
        tensor_count, metadata_count = struct.unpack("<QQ", _read_exact(stream, 16))
        if tensor_count > _MAX_TENSORS:
            raise GGUFError(f"GGUF tensor count is excessive: {tensor_count}")
        if metadata_count > _MAX_METADATA_ENTRIES:
            raise GGUFError(f"GGUF metadata count is excessive: {metadata_count}")

        metadata: dict[str, Any] = {}
        for _ in range(metadata_count):
            key = _read_gguf_string(stream)
            if key in metadata:
                raise GGUFError(f"Duplicate GGUF metadata key: {key}")
            value_type = _read_u32(stream)
            metadata[key] = _read_value(stream, value_type)
            if stream.tell() - _HEADER_SIZE > _MAX_METADATA_BYTES:
                raise GGUFError("GGUF metadata exceeds the bounded parsing limit")
        metadata_end = stream.tell()

        for _ in range(tensor_count):
            _read_gguf_string(stream)  # tensor name
            dimensions = _read_u32(stream)
            if dimensions > 8:
                raise GGUFError(f"Invalid GGUF tensor dimension count: {dimensions}")
            dims = [_read_u64(stream) for _ in range(dimensions)]
            tensor_type = _read_u32(stream)
            tensor_offset = _read_u64(stream)
            if tensor_type > 1024 or any(dimension == 0 for dimension in dims):
                raise GGUFError("Invalid GGUF tensor descriptor")
            # Tensor extents depend on the GGML type table. Bounds-check the
            # starting offset here; inference validates actual tensor shapes.
            if tensor_offset > file_size:
                raise GGUFError("GGUF tensor offset exceeds file size")
        tensor_info_end = stream.tell()

    alignment_value = metadata.get("general.alignment", 32)
    if isinstance(alignment_value, bool) or not isinstance(alignment_value, int):
        raise GGUFError("general.alignment must be an integer")
    if alignment_value < 1 or alignment_value > (1 << 20) or alignment_value & (alignment_value - 1):
        raise GGUFError(f"Invalid GGUF alignment: {alignment_value}")
    data_start = _align(tensor_info_end, alignment_value)
    if data_start > file_size:
        raise GGUFError("GGUF tensor data start exceeds file size")
    if any(
        not isinstance(value, int) or value < 0 or value > file_size - data_start
        for value in _tensor_offsets(file_path, tensor_count, metadata_end, alignment_value)
    ):
        raise GGUFError("GGUF tensor offset is outside the tensor data section")
    return GGUFMetadata(
        version=version,
        tensor_count=tensor_count,
        metadata=metadata,
        alignment=alignment_value,
        metadata_end=metadata_end,
        tensor_info_end=tensor_info_end,
        data_start=data_start,
        file_size=file_size,
    )


def _tensor_offsets(path: Path, tensor_count: int, metadata_end: int, alignment: int) -> list[int]:
    """Re-read only the tensor table and return offsets for data-section bounds checks."""
    offsets: list[int] = []
    with path.open("rb") as stream:
        stream.seek(metadata_end)
        for _ in range(tensor_count):
            _read_gguf_string(stream)
            dimensions = _read_u32(stream)
            for _ in range(dimensions):
                _read_u64(stream)
            _read_u32(stream)
            offsets.append(_read_u64(stream))
    return offsets


def _read_varint(data: bytes, index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while index < len(data) and shift <= 63:
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, index
        shift += 7
    raise GGUFError("Malformed SentencePiece protobuf varint")


def _skip_wire_value(data: bytes, index: int, wire_type: int) -> int:
    if wire_type == 0:
        _, index = _read_varint(data, index)
        return index
    if wire_type == 1:
        index += 8
    elif wire_type == 2:
        length, index = _read_varint(data, index)
        index += length
    elif wire_type == 5:
        index += 4
    else:
        raise GGUFError(f"Unsupported SentencePiece protobuf wire type: {wire_type}")
    if index > len(data):
        raise GGUFError("Truncated SentencePiece protobuf field")
    return index


def sentencepiece_pieces(model: bytes) -> list[str]:
    """Extract SentencePiece ModelProto.pieces[].piece without protobuf dependencies."""
    pieces: list[str] = []
    index = 0
    while index < len(model):
        tag, index = _read_varint(model, index)
        field_number, wire_type = tag >> 3, tag & 7
        if field_number == 0:
            raise GGUFError("Invalid SentencePiece protobuf field number")
        if field_number == 1 and wire_type == 2:
            length, index = _read_varint(model, index)
            end = index + length
            if end > len(model):
                raise GGUFError("Truncated SentencePiece piece")
            piece = model[index:end]
            index = end
            nested, found_piece = 0, None
            while nested < len(piece):
                nested_tag, nested = _read_varint(piece, nested)
                nested_field, nested_wire = nested_tag >> 3, nested_tag & 7
                if nested_field == 1 and nested_wire == 2:
                    text_length, nested = _read_varint(piece, nested)
                    text_end = nested + text_length
                    if text_end > len(piece) or found_piece is not None:
                        raise GGUFError("Malformed SentencePiece piece text")
                    try:
                        found_piece = piece[nested:text_end].decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise GGUFError("SentencePiece token is not valid UTF-8") from exc
                    nested = text_end
                else:
                    nested = _skip_wire_value(piece, nested, nested_wire)
            if found_piece is None:
                raise GGUFError("SentencePiece entry has no piece text")
            pieces.append(found_piece)
            if len(pieces) > _MAX_PROTO_PIECES:
                raise GGUFError("SentencePiece model has too many pieces")
        else:
            index = _skip_wire_value(model, index, wire_type)
    if not pieces:
        raise GGUFError("SentencePiece model contains no pieces")
    return pieces


def fetch_official_nemotron_tokenizer_model() -> bytes | None:
    """Fetch the small tokenizer range from the pinned official NeMo archive.

    Returns validated SentencePiece bytes, or ``None`` for any transport or
    integrity failure. Importing this module does not perform network access.
    """
    end = _OFFICIAL_TOKENIZER_OFFSET + _OFFICIAL_TOKENIZER_SIZE - 1
    request = urllib.request.Request(
        _OFFICIAL_TOKENIZER_URL,
        headers={
            "Range": f"bytes={_OFFICIAL_TOKENIZER_OFFSET}-{end}",
            "Accept-Encoding": "identity",
            "User-Agent": "Voice-Flow-tokenizer-metadata-repair/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.getcode() != 206:
                return None
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range.strip())
            if not match or tuple(map(int, match.groups()[:2])) != (_OFFICIAL_TOKENIZER_OFFSET, end):
                return None
            if int(match.group(3)) <= end:
                return None
            if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
                return None
            if response.headers.get("Content-Length") not in (None, str(_OFFICIAL_TOKENIZER_SIZE)):
                return None
            model = response.read(_OFFICIAL_TOKENIZER_SIZE + 1)
            if len(model) != _OFFICIAL_TOKENIZER_SIZE:
                return None
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    if hashlib.sha256(model).hexdigest() != _OFFICIAL_TOKENIZER_SHA256:
        return None
    try:
        sentencepiece_pieces(model)
    except GGUFError:
        return None
    return model


def _encode_gguf_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _encode_spm_metadata(model: bytes) -> bytes:
    encoded = base64.b64encode(model).decode("ascii")
    # GGUF metadata entry: key string, STRING value type, string value.
    return _encode_gguf_string("asr.tokenizer.spm_model") + struct.pack("<I", 8) + _encode_gguf_string(encoded)


def _copy_range(source: BinaryIO, destination: BinaryIO, start: int, end: int) -> str:
    source.seek(start)
    digest = hashlib.sha256()
    remaining = end - start
    while remaining:
        chunk = source.read(min(_COPY_CHUNK, remaining))
        if not chunk:
            raise GGUFError("Source file was truncated during copy")
        destination.write(chunk)
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def _hash_range(path: Path, start: int, end: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = end - start
        while remaining:
            chunk = stream.read(min(_COPY_CHUNK, remaining))
            if not chunk:
                raise GGUFError("File was truncated while validating tensor data")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _publish_new_file(temporary: Path, output: Path) -> None:
    """Atomically publish by creating a hard link, which never replaces a target."""
    os.link(temporary, output)
    temporary.unlink()


def prepare_tokenizer_metadata_copy(
    source_path: str | os.PathLike[str],
    tokenizer_model_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> RepairResult:
    """Create a new GGUF copy containing verified native word-boost tokenizer data.

    Existing destinations are never replaced. The source file is never modified.
    """
    source = Path(source_path)
    tokenizer_path = Path(tokenizer_model_path)
    output = Path(output_path)
    if source.resolve() == output.resolve():
        raise GGUFError("Output path must differ from source path")
    if tokenizer_path.stat().st_size > _OFFICIAL_TOKENIZER_SIZE * 2:
        raise GGUFError("Tokenizer model exceeds the bounded input size")
    with tokenizer_path.open("rb") as tokenizer_file:
        model = tokenizer_file.read(_OFFICIAL_TOKENIZER_SIZE * 2 + 1)
    if len(model) > _OFFICIAL_TOKENIZER_SIZE * 2:
        raise GGUFError("Tokenizer model exceeds the bounded input size")
    pieces = sentencepiece_pieces(model)
    parsed = read_gguf_metadata(source)
    vocab = parsed.metadata.get("asr.tokenizer.vocab")
    if not isinstance(vocab, list) or any(not isinstance(token, str) for token in vocab):
        raise GGUFError("GGUF asr.tokenizer.vocab is missing or malformed")
    if vocab != pieces:
        raise GGUFError(f"Tokenizer vocabulary mismatch ({len(vocab)} GGUF tokens, {len(pieces)} SentencePiece tokens)")

    existing = parsed.metadata.get("asr.tokenizer.spm_model")
    if existing is not None:
        if not isinstance(existing, str):
            raise GGUFError("Existing asr.tokenizer.spm_model is not a string")
        try:
            existing_model = base64.b64decode(existing, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise GGUFError("Existing asr.tokenizer.spm_model is invalid base64") from exc
        if existing_model != model:
            raise GGUFError("GGUF already contains a different SentencePiece model")
        return _copy_unchanged(source, output, parsed)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    entry = _encode_spm_metadata(model)
    old_tail_start = parsed.data_start
    new_tensor_info_end = parsed.tensor_info_end + len(entry)
    new_data_start = _align(new_tensor_info_end, parsed.alignment)
    padding = b"\0" * (new_data_start - new_tensor_info_end)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    published = False
    try:
        with os.fdopen(fd, "wb") as destination, source.open("rb") as original:
            original.seek(0)
            destination.write(_read_exact(original, 16))
            # Header contains tensor_count and metadata_count; increment only the latter.
            original.seek(8)
            destination.seek(8)
            destination.write(_read_exact(original, 8))
            original.seek(16)
            destination.seek(16)
            destination.write(struct.pack("<Q", len(parsed.metadata) + 1))
            original.seek(_HEADER_SIZE)
            destination.seek(_HEADER_SIZE)
            _copy_range(original, destination, _HEADER_SIZE, parsed.metadata_end)
            destination.write(entry)
            _copy_range(original, destination, parsed.metadata_end, parsed.tensor_info_end)
            destination.write(padding)
            tensor_digest_hex = _copy_range(original, destination, old_tail_start, parsed.file_size)
            destination.flush()
            os.fsync(destination.fileno())
        # Atomic create without replacing a pre-existing user destination.
        _publish_new_file(temporary, output)
        published = True
        repaired = read_gguf_metadata(output)
        if repaired.metadata.get("asr.tokenizer.spm_model") != base64.b64encode(model).decode("ascii"):
            raise GGUFError("Repaired GGUF metadata failed validation")
        if repaired.data_start != new_data_start or repaired.file_size != output.stat().st_size:
            raise GGUFError("Repaired GGUF layout failed validation")
        if _hash_range(output, repaired.data_start, repaired.file_size) != tensor_digest_hex:
            raise GGUFError("Repaired tensor data hash differs from the source")
        return RepairResult(output, True, tensor_digest_hex, repaired.file_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        # If post-write validation failed, remove only the output created above.
        if published:
            output.unlink(missing_ok=True)
        raise


def _copy_unchanged(source: Path, output: Path, parsed: GGUFMetadata) -> RepairResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    published = False
    try:
        with os.fdopen(fd, "wb") as destination, source.open("rb") as original:
            _copy_range(original, destination, 0, parsed.file_size)
            original.seek(parsed.data_start)
            remaining = parsed.file_size - parsed.data_start
            while remaining:
                chunk = original.read(min(_COPY_CHUNK, remaining))
                if not chunk:
                    raise GGUFError("Source file was truncated during copy")
                digest.update(chunk)
                remaining -= len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        _publish_new_file(temporary, output)
        published = True
        copied = read_gguf_metadata(output)
        if _hash_range(output, copied.data_start, copied.file_size) != digest.hexdigest():
            raise GGUFError("Copied tensor data hash differs from the source")
        return RepairResult(output, False, digest.hexdigest(), parsed.file_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        if published:
            output.unlink(missing_ok=True)
        raise
