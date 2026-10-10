"""Offline regressions for bounded streaming-audio ownership."""
from __future__ import annotations

import ctypes
import sys
import threading
import time
import types
from unittest.mock import patch

import numpy as np

from voice_flow.stream_stt import STREAM_QUEUE_MAX_BYTES, STREAM_QUEUE_MAX_CHUNKS, StreamTranscriber
from voice_flow.tts_engine import TTSEngine


class _BlockedTranscriber:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio: np.ndarray) -> str:
        if int(audio[0]) == 1:
            self.entered.set()
            assert self.release.wait(3.0)
        return str(int(audio[0]))


def _chunk(marker: int) -> np.ndarray:
    return np.full(16_000, marker, dtype=np.float32)


def test_stt_bounds_waiting_audio_and_marks_overflow_for_whole_recording_fallback() -> None:
    provider = _BlockedTranscriber()
    stream = StreamTranscriber(provider, worker_count=1)
    stream.start_session()
    stream.submit_native(_chunk(1), 16_000)
    assert provider.entered.wait(1.0)

    # Each allocation is independent and immediately handed off.  Before the
    # bound this retained roughly 61 MiB in the unbounded queue.
    for marker in range(2, 1002):
        stream.submit_native(_chunk(marker), 16_000)

    assert stream._queue.qsize() <= STREAM_QUEUE_MAX_CHUNKS
    assert sum(stream._queued_bytes_by_epoch.values()) <= STREAM_QUEUE_MAX_BYTES
    assert stream.pending_count() <= STREAM_QUEUE_MAX_CHUNKS + 1
    assert stream.had_failures() is True

    provider.release.set()
    deadline = time.monotonic() + 1.0
    while stream._queue.qsize() == STREAM_QUEUE_MAX_CHUNKS and time.monotonic() < deadline:
        time.sleep(0.005)
    # This chunk enters after the failed sequence gap.  The invocation gate
    # must skip overflow markers once chunk 33 starts, rather than wedging it.
    stream.submit_native(_chunk(1002), 16_000)
    text = stream.collect(timeout=3.0)
    words = text.split()
    assert words == [str(marker) for marker in range(1, STREAM_QUEUE_MAX_CHUNKS + 2)] + ["1002"]
    assert stream.had_failures() is True


def test_stt_discard_drops_queued_audio_and_stale_worker_cannot_leak_into_next_epoch() -> None:
    provider = _BlockedTranscriber()
    stream = StreamTranscriber(provider, worker_count=1)
    stream.start_session()
    stream.submit_native(_chunk(1), 16_000)
    assert provider.entered.wait(1.0)
    for marker in range(2, 12):
        stream.submit_native(_chunk(marker), 16_000)

    stream.discard()
    assert stream._queue.qsize() == 0
    assert sum(stream._queued_bytes_by_epoch.values()) == 0
    assert stream.pending_count() == 0

    stream.start_session()
    provider.release.set()
    stream.submit_native(_chunk(99), 16_000)
    stream.end_session()
    assert stream.collect(timeout=2.0) == "99"


def test_stt_byte_budget_rejects_large_waiting_chunks_before_the_count_limit() -> None:
    provider = _BlockedTranscriber()
    stream = StreamTranscriber(provider, worker_count=1)
    stream.start_session()
    stream.submit_native(_chunk(1), 16_000)
    assert provider.entered.wait(1.0)

    # Four 4-MiB chunks fit the 16-MiB byte budget, well below the 32 item
    # ceiling.  The fifth must be terminally failed without retention.
    samples_per_chunk = STREAM_QUEUE_MAX_BYTES // 16
    for marker in range(2, 7):
        stream.submit_native(np.full(samples_per_chunk, marker, dtype=np.float32), 16_000)

    assert stream._queue.qsize() == 4
    assert sum(stream._queued_bytes_by_epoch.values()) == STREAM_QUEUE_MAX_BYTES
    assert stream.had_failures() is True
    provider.release.set()
    assert stream.collect(timeout=3.0).split() == ["1", "2", "3", "4", "5"]


def test_stt_rejects_one_oversized_chunk_without_retaining_it() -> None:
    provider = _BlockedTranscriber()
    stream = StreamTranscriber(provider, worker_count=1)
    stream.start_session()
    stream.submit_native(_chunk(1), 16_000)
    assert provider.entered.wait(1.0)

    oversized = np.ones(STREAM_QUEUE_MAX_BYTES // 4 + 1, dtype=np.float32)
    stream.submit_native(oversized, 16_000)
    assert stream._queue.qsize() == 0
    assert sum(stream._queued_bytes_by_epoch.values()) == 0
    assert stream.had_failures() is True
    provider.release.set()
    assert stream.collect(timeout=2.0) == "1"


def test_start_session_serializes_stale_queue_cleanup_before_new_intake() -> None:
    """A submit racing start cleanup must be accepted by the new epoch, not drained."""
    stream = StreamTranscriber(_BlockedTranscriber(), worker_count=1)
    stale = _chunk(7)
    stream._queue.put_nowait((1, 0, (stale, 16_000), stale.nbytes))
    stream._queued_bytes_by_epoch[0] = stale.nbytes
    cleanup_entered = threading.Event()
    release_cleanup = threading.Event()
    start_done = threading.Event()
    submit_done = threading.Event()
    original_get = stream._queue.get_nowait

    def slow_get():
        cleanup_entered.set()
        assert release_cleanup.wait(1.0)
        return original_get()

    with patch.object(stream._queue, "get_nowait", side_effect=slow_get):
        starter = threading.Thread(target=lambda: (stream.start_session(), start_done.set()))
        starter.start()
        assert cleanup_entered.wait(1.0)
        submitter = threading.Thread(target=lambda: (stream.submit_native(_chunk(99), 16_000), submit_done.set()))
        submitter.start()
        assert not submit_done.wait(0.05)
        release_cleanup.set()
        assert start_done.wait(1.0)
        assert submit_done.wait(1.0)
        starter.join(timeout=0.1)
        submitter.join(timeout=0.1)

    stream.end_session()
    assert stream.collect(timeout=1.0) == "99"


def test_discard_serializes_cleanup_before_a_replacement_session_can_accept_audio() -> None:
    provider = _BlockedTranscriber()
    stream = StreamTranscriber(provider, worker_count=1)
    stream.start_session()
    stream.submit_native(_chunk(1), 16_000)
    assert provider.entered.wait(1.0)
    stream.submit_native(_chunk(2), 16_000)
    cleanup_entered = threading.Event()
    release_cleanup = threading.Event()
    discarded = threading.Event()
    restarted = threading.Event()
    original_get = stream._queue.get_nowait

    def slow_get():
        cleanup_entered.set()
        assert release_cleanup.wait(1.0)
        return original_get()

    with patch.object(stream._queue, "get_nowait", side_effect=slow_get):
        cancelling = threading.Thread(target=lambda: (stream.discard(), discarded.set()))
        cancelling.start()
        assert cleanup_entered.wait(1.0)
        replacement = threading.Thread(target=lambda: (stream.start_session(), restarted.set()))
        replacement.start()
        assert not restarted.wait(0.05)
        release_cleanup.set()
        assert discarded.wait(1.0)
        assert restarted.wait(1.0)
        cancelling.join(timeout=0.1)
        replacement.join(timeout=0.1)

    provider.release.set()
    stream.submit_native(_chunk(99), 16_000)
    stream.end_session()
    assert stream.collect(timeout=2.0) == "99"


class _FakeCommunicate:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"fake-mp3"}


class _FakeWinMM:
    def mciSendStringW(self, command, buffer, *_args):
        if command.startswith("status") and buffer is not None:
            buffer.value = "playing"
        return 0


def test_pipelined_tts_stop_unblocks_full_producer_and_cleans_its_temp_audio(monkeypatch, tmp_path) -> None:
    """A stopped consumer must not leave producer blocked in Queue.put()."""
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_FakeCommunicate))
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(winmm=_FakeWinMM()), raising=False)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))

    engine = TTSEngine()
    engine._session = 1
    engine._stop_event.clear()
    timer = threading.Timer(0.15, engine.stop)
    timer.start()
    try:
        assert engine._synthesize_and_play_pipelined(["Sentence."] * 30, "en-US-AvaNeural", session=1)
    finally:
        timer.cancel()

    assert not [path for path in tmp_path.iterdir() if path.suffix == ".mp3"]


def test_replaced_tts_session_keeps_its_alias_when_old_pipeline_cancels(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_FakeCommunicate))
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(winmm=_FakeWinMM()), raising=False)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))

    engine = TTSEngine()
    engine._session = 1
    old_started = threading.Event()
    finished = threading.Event()

    def run_old() -> None:
        engine._synthesize_and_play_pipelined(
            ["Sentence."] * 30,
            "en-US-AvaNeural",
            on_start=old_started.set,
            session=1,
        )
        finished.set()

    old = threading.Thread(target=run_old)
    old.start()
    assert old_started.wait(1.0)
    deadline = time.monotonic() + 1.0
    while len(list(tmp_path.glob("*.mp3"))) < 11 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(list(tmp_path.glob("*.mp3"))) >= 11
    # Model the synchronous session ownership transition in speak(): old work
    # sees a stale token while the new session has already opened its alias.
    engine._session = 2
    engine._active_mci_alias = "new-session-alias"
    assert finished.wait(2.0)
    old.join(timeout=0.1)
    assert not old.is_alive()
    assert engine._active_mci_alias == "new-session-alias"
    assert not [path for path in tmp_path.iterdir() if path.suffix == ".mp3"]
