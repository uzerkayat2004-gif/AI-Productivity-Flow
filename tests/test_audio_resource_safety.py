"""Bounded-resource regressions for capture ownership and NotebookLM scheduling."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from voice_flow import audio as audio_module
from voice_flow.audio import AudioRecorder
from voice_flow.audio_notebooklm import NotebookLMAudioSummaryError, NotebookLMAudioSummaryService


def test_forced_chunk_shares_owned_frames_and_survives_driver_reuse(monkeypatch):
    """The archive/chunk views share one safe copy; emitted audio survives reuse."""
    ticks = iter(float(index) for index in range(12))
    monkeypatch.setattr(audio_module.time, "monotonic", lambda: next(ticks))
    recorder = AudioRecorder()
    recorder._recording = True
    recorder._native_sr = 16_000
    recorder._native_ch = 1
    recorder._vad = None
    recorder.max_chunk_seconds = 8.0
    delivered = []
    recorder.on_chunk_closed = lambda chunk, _sr, **_kwargs: delivered.append(chunk)

    driver_frame = np.full((16_000, 1), 0.1, dtype=np.float32)
    for _ in range(9):
        driver_frame.fill(0.1)
        recorder._audio_callback(driver_frame, 16_000, None, None)
        driver_frame.fill(0.0)  # sounddevice may reuse this memory after return

    assert delivered and np.allclose(delivered[0], 0.1)
    assert len(recorder._buffer) == 9
    # The currently-open forced-overlap chunk is intentionally a new slice;
    # all ordinary retained frames are shared references, not duplicate copies.
    assert recorder._buffer[0].flags.writeable is False
    assert sum(frame.nbytes for frame in recorder._buffer) == 9 * 16_000 * 4


def test_close_releases_all_retained_capture_views():
    recorder = AudioRecorder()
    recorder._recording = True
    frame = np.ones((8, 1), dtype=np.float32)
    recorder._buffer.append(frame)
    recorder._chunk.append(frame)
    recorder._pending_live_frames.append(frame)
    recorder._pending_closed_chunks.append((frame, 0.0))
    recorder._pending_stream_events.append(("frame", frame, 0.0))
    recorder.close()
    assert not recorder._buffer
    assert not recorder._chunk
    assert not recorder._pending_live_frames
    assert not recorder._pending_closed_chunks
    assert not recorder._pending_stream_events


def test_cancelled_waiter_never_enters_second_notebooklm_generation(monkeypatch, tmp_path):
    """A queued stale request exits before it can perform bridge setup."""
    service = NotebookLMAudioSummaryService(root_dir=tmp_path)
    first_entered = threading.Event()
    release_first = threading.Event()
    cancelled = threading.Event()
    executions = []

    def fake_generate_locked(*_args, **_kwargs):
        executions.append(threading.get_ident())
        first_entered.set()
        release_first.wait(1.0)
        return {"audio_path": "unused"}

    monkeypatch.setattr(service, "_generate_locked", fake_generate_locked)
    first = threading.Thread(target=lambda: service.generate("first source"))
    first.start()
    assert first_entered.wait(0.25)

    result = []

    def stale_request():
        try:
            service.generate("stale source", cancelled=cancelled.is_set)
        except NotebookLMAudioSummaryError as exc:
            result.append(exc.code)

    second = threading.Thread(target=stale_request)
    second.start()
    time.sleep(0.08)
    cancelled.set()
    second.join(0.5)
    release_first.set()
    first.join(0.5)

    assert result == ["cancelled"]
    assert len(executions) == 1
