"""Offline bounds checks for NotebookLM Audio Flow resource seams."""

from __future__ import annotations

import gc
import logging
import sys
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

from voice_flow.audio_notebooklm import NotebookLMAudioSummaryService, m4a_duration_seconds
from voice_flow import audio_notebooklm
from voice_flow.gui.api_server import VoiceFlowApiHandler


def _tiny_m4a() -> bytes:
    payload = bytes([0, 0, 0, 0]) + (0).to_bytes(4, "big") * 2 + (1_000).to_bytes(4, "big") + (30_000).to_bytes(4, "big")
    mvhd = (8 + len(payload)).to_bytes(4, "big") + b"mvhd" + payload
    moov = (8 + len(mvhd)).to_bytes(4, "big") + b"moov" + mvhd
    return (16).to_bytes(4, "big") + b"ftypM4A " + b"isom" + moov


class _OfflineBridge:
    profile = "test"

    def __init__(self, **_kwargs) -> None:
        self.polls = 0

    def check_auth(self, **_kwargs):
        return SimpleNamespace(authenticated=True)

    def create_notebook(self, _title: str):
        return SimpleNamespace(notebook_id="offline-notebook")

    def add_source(self, _notebook_id: str, *, source_text: str, title: str):
        assert source_text and title
        return SimpleNamespace(source_id="offline-source", status="ready")

    def _invoke(self, args, *, timeout: float):
        del timeout
        command = tuple(args)
        if command[:2] == ("generate", "audio"):
            return {"task_id": "offline-task"}
        if command[:2] == ("artifact", "poll"):
            self.polls += 1
            return {"status": "completed", "artifact_id": "offline-artifact"}
        if command[:2] == ("download", "audio"):
            Path(command[2]).write_bytes(_tiny_m4a())
            return {"status": "ok"}
        raise AssertionError(command)


def test_resource_samples_are_best_effort_and_do_not_change_generation(tmp_path: Path, monkeypatch, caplog) -> None:
    class BrokenPsutil:
        @staticmethod
        def Process():
            raise RuntimeError("metrics unavailable")

    monkeypatch.setitem(sys.modules, "psutil", BrokenPsutil)
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=_OfflineBridge,
        sleep=lambda _seconds: None,
    )
    with caplog.at_level(logging.INFO, logger="voice_flow.audio_notebooklm"):
        result = service.generate("bounded offline source", style="single")

    assert Path(result["audio_path"]).is_file()
    samples = [record.message for record in caplog.records if "[AUDIO FLOW RESOURCES]" in record.message]
    assert len(samples) == 4
    assert all("private_bytes': None" in sample for sample in samples)
    assert [sample.split("'stage': '")[1].split("'", 1)[0] for sample in samples] == [
        "start", "after_generation_wait", "after_download", "finish"
    ]


def test_resource_sample_uses_lightweight_process_fields(monkeypatch, caplog) -> None:
    class Process:
        def memory_info(self):
            return SimpleNamespace(private=123, rss=456)

        def num_threads(self):
            return 7

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=Process))
    with caplog.at_level(logging.INFO, logger="voice_flow.audio_notebooklm"):
        audio_notebooklm._log_resource_snapshot("test")
    sample = next(record.message for record in caplog.records if "[AUDIO FLOW RESOURCES]" in record.message)
    assert "'private_bytes': 123" in sample
    assert "'working_set_bytes': 456" in sample
    assert "'thread_count': 7" in sample


def test_m4a_duration_reader_seeks_past_sparse_large_media_without_materializing_it(tmp_path: Path) -> None:
    audio = tmp_path / "sparse-large.m4a"
    free_size = 128 * 1024 * 1024
    with audio.open("wb") as handle:
        handle.write((16).to_bytes(4, "big") + b"ftypM4A " + b"isom")
        handle.write(free_size.to_bytes(4, "big") + b"free")
        handle.seek(16 + free_size)
        handle.write(_tiny_m4a()[16:])

    tracemalloc.start()
    tracemalloc.reset_peak()
    assert m4a_duration_seconds(audio) == 30.0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert audio.stat().st_size > 100 * 1024 * 1024
    assert peak < 300_000


class _TrackingReader:
    def __init__(self, handle, reads: list[int]) -> None:
        self._handle = handle
        self._reads = reads

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *args):
        return self._handle.__exit__(*args)

    def seek(self, *args):
        return self._handle.seek(*args)

    def read(self, size: int = -1):
        self._reads.append(size)
        return self._handle.read(size)


class _TrackingAudio:
    def __init__(self, path: Path, reads: list[int]) -> None:
        self._path = path
        self._reads = reads
        self.name = path.name
        self.suffix = path.suffix

    def stat(self):
        return self._path.stat()

    def open(self, mode: str):
        return _TrackingReader(self._path.open(mode), self._reads)


class _CountingSink:
    def __init__(self) -> None:
        self.bytes_written = 0

    def write(self, chunk: bytes) -> int:
        self.bytes_written += len(chunk)
        return len(chunk)


def _stream_handler(range_header: str = ""):
    handler = object.__new__(VoiceFlowApiHandler)
    handler.headers = {"Range": range_header}
    handler.wfile = _CountingSink()
    handler.statuses = []
    handler.response_headers = {}
    handler.send_response = lambda status: handler.statuses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.__setitem__(name, value)
    handler.end_headers = lambda: None
    handler.send_json_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected error response"))
    return handler


def test_summary_audio_stream_reads_at_most_64k_for_full_and_range_responses(tmp_path: Path) -> None:
    audio = tmp_path / "large.m4a"
    audio.write_bytes(b"x" * (3 * 1024 * 1024 + 17))

    for range_header, expected_length in (("", audio.stat().st_size), ("bytes=100-131271", 131172)):
        reads: list[int] = []
        handler = _stream_handler(range_header)
        tracemalloc.start()
        tracemalloc.reset_peak()
        handler._stream_summary_audio(_TrackingAudio(audio, reads), prefer_mp3=False)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert handler.statuses == [200 if not range_header else 206]
        assert handler.wfile.bytes_written == expected_length
        assert reads and max(reads) <= 64 * 1024
        # Includes the one-time player-helper import on the first request, but
        # remains far below the 3 MiB response body.
        assert peak < 1_000_000


def test_repeated_mocked_generation_does_not_retain_large_source_text(tmp_path: Path) -> None:
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=_OfflineBridge,
        sleep=lambda _seconds: None,
    )
    source = "source " * 14_000  # 98,000 UTF-8 bytes: just below the request limit.
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    for _ in range(12):
        service.generate(source, style="single")
    gc.collect()
    current, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert current - baseline < 1_500_000
