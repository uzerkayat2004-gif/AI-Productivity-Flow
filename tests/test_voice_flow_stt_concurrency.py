"""Focused regressions for Voice Flow streaming STT latency and deadlines."""
from __future__ import annotations

import os
import sys
import threading
import tempfile
import time
from unittest.mock import patch

import numpy as np

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.stream_stt import StreamTranscriber
from voice_flow.audio import AudioRecorder
from voice_flow.storage import storage


def _chunk(marker: float) -> np.ndarray:
    return np.full((1600,), marker, dtype=np.float32)


class _SlowMarkerTranscriber:
    def __init__(self, delay: float = 0.25) -> None:
        self.delay = delay

    def transcribe(self, audio: np.ndarray) -> str:
        time.sleep(self.delay)
        return "first" if float(audio[0]) == 1.0 else "second"


class _OutOfOrderTranscriber:
    def transcribe(self, audio: np.ndarray) -> str:
        # The second chunk completes first, which must not make the assembled
        # transcript reorder words.
        time.sleep(0.24 if float(audio[0]) == 1.0 else 0.02)
        return "first" if float(audio[0]) == 1.0 else "second"


class _FailFirstTranscriber:
    def transcribe(self, audio: np.ndarray) -> str:
        return "" if float(audio[0]) == 1.0 else "second-only"


class _DeadlineTranscriber:
    def __init__(self) -> None:
        self.deadlines: list[float | None] = []

    def transcribe(
        self,
        _audio: np.ndarray,
        *,
        is_chunk: bool = False,
        deadline: float | None = None,
    ) -> str:
        assert is_chunk
        self.deadlines.append(deadline)
        return "deadline-aware"


class _SnapshotTranscriber:
    def __init__(self) -> None:
        self.models: list[str | None] = []

    def transcribe(self, _audio: np.ndarray, *, model_ref: str | None = None) -> str:
        self.models.append(model_ref)
        return "snapshot"


class _SeamTranscriber:
    def transcribe(self, audio: np.ndarray) -> str:
        labels = {
            1.0: "we test overlap",
            2.0: "test overlap continues",
            3.0: "unrelated ending",
            4.0: "again",
            5.0: "again",
        }
        return labels[float(audio[0])]


def test_stream_chunks_run_concurrently_with_bounded_latency() -> None:
    transcriber = _SlowMarkerTranscriber()
    stream = StreamTranscriber(transcriber)
    stream.start_session()
    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(2.0), 16000)
    stream.end_session()

    started = time.monotonic()
    text = stream.collect(timeout=0.42)
    elapsed = time.monotonic() - started

    assert text == "first second"
    assert elapsed < 0.42
    assert stream.pending_count() == 0


def test_stream_tracks_every_chunk_accepted_during_the_session() -> None:
    stream = StreamTranscriber(_SlowMarkerTranscriber(delay=0.01))
    stream.start_session()
    assert stream.accepted_count() == 0

    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(2.0), 16000)
    assert stream.accepted_count() == 2

    stream.end_session()
    assert stream.collect(timeout=0.2) == "first second"
    assert stream.accepted_count() == 2

    stream.start_session()
    assert stream.accepted_count() == 0
    stream.submit_native(_chunk(1.0), 16000)
    stream.discard()
    assert stream.accepted_count() == 0


def test_stream_preserves_order_when_workers_finish_out_of_order() -> None:
    stream = StreamTranscriber(_OutOfOrderTranscriber())
    stream.start_session()
    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(2.0), 16000)
    stream.end_session()

    # The fast second result is retained until the first result is terminal.
    assert stream.collect(timeout=0.08) == ""
    assert stream.pending_count() == 1
    assert stream.collect(timeout=0.35) == "first second"
    assert stream.pending_count() == 0
    assert stream.collect(timeout=0.01) == ""


def test_failed_early_chunk_stays_sticky_after_later_success() -> None:
    stream = StreamTranscriber(_FailFirstTranscriber())
    stream.start_session()
    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(2.0), 16000)
    stream.end_session()

    # The later success is returned, but it is not a complete transcript: the
    # first accepted chunk failed and must force the caller's whole-buffer
    # fallback even though no work remains pending.
    assert stream.collect(timeout=0.5) == "second-only"
    assert stream.pending_count() == 0
    assert stream.had_failures() is True

    stream.start_session()
    assert stream.had_failures() is False


def test_stream_passes_absolute_deadline_to_deadline_aware_transcriber() -> None:
    transcriber = _DeadlineTranscriber()
    stream = StreamTranscriber(transcriber)
    stream.start_session()
    deadline = time.monotonic() + 1.0
    stream.end_session(deadline=deadline)
    stream.submit_native(_chunk(1.0), 16000, force=True)

    assert stream.collect(timeout=0.5, deadline=deadline) == "deadline-aware"
    assert transcriber.deadlines == [deadline]


def test_stream_uses_the_model_snapshot_captured_at_session_start() -> None:
    transcriber = _SnapshotTranscriber()
    stream = StreamTranscriber(transcriber)
    stream.start_session(model_ref="deepgram/nova-3")
    stream.submit_native(_chunk(1.0), 16_000)
    stream.end_session()

    assert stream.collect(timeout=0.5) == "snapshot"
    assert transcriber.models == ["deepgram/nova-3"]


def test_stream_removes_only_verified_explicit_forced_overlap() -> None:
    stream = StreamTranscriber(_SeamTranscriber())
    stream.start_session()
    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(2.0), 16000, overlap_prefix_seconds=0.75)
    stream.end_session()

    assert stream.collect(timeout=0.5) == "we test overlap continues"
    assert stream.had_failures() is False


def test_unverified_forced_overlap_marks_stream_incomplete_for_whole_buffer_recovery() -> None:
    stream = StreamTranscriber(_SeamTranscriber())
    stream.start_session()
    stream.submit_native(_chunk(1.0), 16000)
    stream.submit_native(_chunk(3.0), 16000, overlap_prefix_seconds=0.75)
    stream.end_session()

    assert stream.collect(timeout=0.5) == "we test overlap unrelated ending"
    assert stream.had_failures() is True


def test_ordinary_repeated_words_are_never_deduplicated() -> None:
    stream = StreamTranscriber(_SeamTranscriber())
    stream.start_session()
    stream.submit_native(_chunk(4.0), 16000)
    stream.submit_native(_chunk(5.0), 16000)
    stream.end_session()

    assert stream.collect(timeout=0.5) == "again again"
    assert stream.had_failures() is False


def test_transcriber_cloud_join_is_clamped_to_absolute_deadline() -> None:
    from voice_flow import transcriber as transcriber_module

    transcriber = object.__new__(transcriber_module.Transcriber)
    transcriber.model = object()
    transcriber._loading = False
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    audio = np.full((3200,), 0.05, dtype=np.float32)

    def slow_cloud(*_args, **_kwargs) -> str:
        time.sleep(0.5)
        return "late cloud text"

    with (
        patch.object(transcriber_module, "enhance_for_stt", return_value=(audio, "normal")),
        patch.object(storage, "get_setting", return_value="deepgram/nova-3"),
        patch.object(transcriber_module.stt_engines, "transcribe_cloud", side_effect=slow_cloud),
        patch.object(transcriber, "_transcribe_local", return_value="local fallback"),
    ):
        started = time.monotonic()
        out = transcriber.transcribe(audio, is_chunk=True, deadline=started + 0.08)
        elapsed = time.monotonic() - started

    assert out == "local fallback"
    assert elapsed < 0.25


def test_model_warm_wait_honors_absolute_deadline() -> None:
    from voice_flow.transcriber import Transcriber

    transcriber = object.__new__(Transcriber)
    transcriber.model = None
    transcriber._loading = True
    transcriber._lock = threading.Lock()

    started = time.monotonic()
    assert transcriber._wait_for_model(started + 0.05) is False
    assert time.monotonic() - started < 0.2


def test_audio_callback_quarantines_non_finite_driver_samples() -> None:
    recorder = AudioRecorder()
    recorder._recording = True
    recorder._native_sr = 16000
    recorder._audio_callback(
        np.array([[np.nan], [np.inf], [0.05]], dtype=np.float32),
        3,
        None,
        None,
    )

    assert np.isfinite(np.concatenate(recorder._buffer)).all()
    assert np.isfinite(recorder.level)


def test_save_wav_quarantines_non_finite_samples() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "capture.wav")
        AudioRecorder.save_wav(np.array([np.nan, np.inf, -np.inf, 0.1], dtype=np.float32), output)
        assert os.path.getsize(output) > 44
