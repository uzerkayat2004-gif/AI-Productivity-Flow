"""Offline tests for optional Nemotron tokenizer repair in the download worker."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from voice_flow import downloadable_models


MODEL_ID = "nvidia/nemotron-speech-streaming-en-0.6b"


def test_optional_repair_publishes_validated_copy_without_changing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "model.gguf.part"
    source.write_bytes(b"original GGUF bytes")
    calls: list[tuple[Path, Path, bytes]] = []

    monkeypatch.setattr(
        "voice_flow.nemotron_tokenizer.read_gguf_metadata",
        lambda path: SimpleNamespace(metadata={
            "asr.tokenizer.type": "sentencepiece_bpe",
            "asr.tokenizer.vocab": ["▁hello"],
        }),
    )
    monkeypatch.setattr(
        "voice_flow.nemotron_tokenizer.fetch_official_nemotron_tokenizer_model",
        lambda: b"validated tokenizer model",
    )

    def prepare(source_path: Path, tokenizer_path: Path, output_path: Path):
        calls.append((source_path, tokenizer_path, tokenizer_path.read_bytes()))
        output_path.write_bytes(b"repaired GGUF bytes")
        return SimpleNamespace(output_path=output_path, added_metadata=True)

    monkeypatch.setattr("voice_flow.nemotron_tokenizer.prepare_tokenizer_metadata_copy", prepare)

    assert downloadable_models._maybe_repair_nemotron_tokenizer(source, MODEL_ID) is True
    assert source.read_bytes() == b"repaired GGUF bytes"
    assert calls and calls[0][0] == source
    assert calls[0][2] == b"validated tokenizer model"
    assert not calls[0][1].exists()  # temporary tokenizer is cleaned after publishing


def test_optional_repair_failure_preserves_original_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "model.gguf.part"
    source.write_bytes(b"original GGUF bytes")
    monkeypatch.setattr(
        "voice_flow.nemotron_tokenizer.read_gguf_metadata",
        lambda path: SimpleNamespace(metadata={
            "asr.tokenizer.type": "sentencepiece_bpe",
            "asr.tokenizer.vocab": ["▁hello"],
        }),
    )
    monkeypatch.setattr(
        "voice_flow.nemotron_tokenizer.fetch_official_nemotron_tokenizer_model",
        lambda: b"validated tokenizer model",
    )

    def fail_prepare(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr("voice_flow.nemotron_tokenizer.prepare_tokenizer_metadata_copy", fail_prepare)

    assert downloadable_models._maybe_repair_nemotron_tokenizer(source, MODEL_ID) is False
    assert source.read_bytes() == b"original GGUF bytes"


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_completed_download_survives_optional_repair_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repair_succeeds: bool,
) -> None:
    models = tmp_path / "empty-model-dir"
    models.mkdir()
    monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: models)
    spec = downloadable_models.get_model_spec(MODEL_ID)
    assert spec is not None
    target = models / spec["filename"]
    part = models / f"{spec['filename']}.part"
    original = b"offline mocked GGUF payload"
    repaired = b"offline mocked repaired GGUF payload"
    response = MagicMock()
    response.headers.get.return_value = str(len(original))
    response.read.side_effect = [original, b""]
    response.__enter__.return_value = response
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: response)

    repair_calls: list[tuple[Path, str]] = []

    def repair(path: Path, model_id: str) -> bool:
        repair_calls.append((path, model_id))
        if repair_succeeds:
            path.write_bytes(repaired)
            return True
        return False

    monkeypatch.setattr(downloadable_models, "_maybe_repair_nemotron_tokenizer", repair)

    # Avoid changing the user's real settings or starting a model warmup thread.
    from voice_flow.storage import storage
    monkeypatch.setattr(storage, "get_setting", lambda key, default=None: "cloud/explicit-choice")
    monkeypatch.setattr(storage, "save_setting", lambda *args, **kwargs: None)

    with downloadable_models._STATE_LOCK:
        downloadable_models._ACTIVE_DOWNLOADS[MODEL_ID] = {"status": "downloading"}
    downloadable_models._download_worker(spec, target, part, threading.Event())

    assert repair_calls == [(part, MODEL_ID)]
    assert not part.exists()
    assert target.read_bytes() == (repaired if repair_succeeds else original)
    with downloadable_models._STATE_LOCK:
        assert downloadable_models._ACTIVE_DOWNLOADS[MODEL_ID]["status"] == "downloaded"
        downloadable_models._ACTIVE_DOWNLOADS.pop(MODEL_ID, None)
