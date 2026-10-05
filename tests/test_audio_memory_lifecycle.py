"""Actual capture and summary setup seams, without devices or cloud jobs."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import numpy as np

from voice_flow.audio import AudioRecorder, FORCED_CHUNK_OVERLAP_SECONDS
from voice_flow.audio_notebooklm import NotebookLMAudioSummaryError, NotebookLMAudioSummaryService


def test_capture_reuses_owned_frames_and_preserves_reused_driver_data(monkeypatch):
    recorder = AudioRecorder()
    recorder._recording = True
    recorder._native_sr = 16_000
    recorder.begin_stream_input_buffering()
    clock = [1_000.0]
    monkeypatch.setattr("voice_flow.audio.time.monotonic", lambda: clock[0])
    chunks = []
    recorder.on_chunk_closed = lambda chunk, _sr, **_kwargs: chunks.append(chunk)
    driver = np.full((1_024, 1), 0.05, dtype=np.float32)
    for _ in range(170):
        recorder._audio_callback(driver, len(driver), None, None)
        clock[0] += len(driver) / recorder._native_sr
    assert len(recorder._pending_closed_chunks) >= 1
    assert len(recorder._chunk) < len(recorder._buffer)
    copied_prefixes = [frame for frame in recorder._chunk if not any(frame is stored for stored in recorder._buffer)]
    # The deliberately retained 0.4-second overlap has its own bounded copy.
    assert sum(frame.nbytes for frame in copied_prefixes) <= FORCED_CHUNK_OVERLAP_SECONDS * recorder._native_sr * 4
    assert all(frame is stored for frame, stored in zip(recorder._pending_live_frames, recorder._buffer))
    assert not recorder._buffer[0].flags.writeable
    driver.fill(0.9)
    assert float(recorder._buffer[0][0, 0]) == np.float32(0.05)
    frames = []
    recorder.on_audio_frame = lambda frame, _sr: frames.append(frame)
    recorder.flush_stream_input_buffer()
    assert len(frames) == 170
    assert chunks
    complete = recorder.stop()
    assert len(complete) == 170 * 1_024
    assert np.allclose(complete, 0.05)


def test_shutdown_releases_retained_audio_without_starting_a_device():
    recorder = AudioRecorder()
    frame = np.ones((1_024, 1), dtype=np.float32)
    recorder._buffer.append(frame)
    recorder._chunk.append(frame)
    recorder._pending_live_frames.append(frame)
    recorder.close()
    assert not recorder._buffer
    assert not recorder._chunk
    assert not recorder._pending_live_frames


def test_cancelled_queued_summary_never_creates_another_bridge(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    cancelled = threading.Event()
    constructions = []
    errors = []

    class Bridge:
        def __init__(self, **_kwargs):
            constructions.append(self)

        def check_auth(self, **_kwargs):
            entered.set()
            assert release.wait(2.0)
            raise NotebookLMAudioSummaryError("TEST", "end offline setup")

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=Bridge)

    def run(token=None):
        try:
            service.generate("A small offline source.", cancelled=token)
        except NotebookLMAudioSummaryError as error:
            errors.append(error.code)

    first = threading.Thread(target=run)
    second = threading.Thread(target=run, args=(cancelled,))
    first.start()
    assert entered.wait(1.0)
    second.start()
    cancelled.set()
    second.join(timeout=1.0)
    try:
        assert not second.is_alive()
        assert len(constructions) == 1
        assert "cancelled" in errors
    finally:
        release.set()
        first.join(timeout=1.0)
        second.join(timeout=1.0)
    # Failure must release the gate for the next request too.
    run()
    assert len(constructions) == 2
    assert not service._generation_lock.locked()
