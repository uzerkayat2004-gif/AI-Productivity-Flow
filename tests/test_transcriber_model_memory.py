"""Offline model-residency regressions for :mod:`voice_flow.transcriber`."""
from __future__ import annotations

import gc
import threading
import time
import weakref

import numpy as np

from voice_flow import transcriber as transcriber_module


class _FakeWhisperModel:
    created: list["_FakeWhisperModel"] = []

    def __init__(self, model_ref, **_kwargs) -> None:
        self.model_ref = str(model_ref)
        self.created.append(self)


def _bare_transcriber() -> transcriber_module.Transcriber:
    transcriber = object.__new__(transcriber_module.Transcriber)
    transcriber.model = None
    transcriber.nemotron_engine = None
    transcriber._loading = False
    transcriber._loaded_model_ref = None
    transcriber._loading_model_ref = None
    transcriber._lock = threading.Lock()
    transcriber._transcribe_lock = threading.Lock()
    transcriber._whisper_models = {}
    return transcriber


def test_switching_whisper_models_releases_the_superseded_model(monkeypatch) -> None:
    """The actual loader must not retain every historical Whisper instance."""
    _FakeWhisperModel.created = []
    monkeypatch.setattr(transcriber_module, "WhisperModel", _FakeWhisperModel)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)

    transcriber = _bare_transcriber()
    transcriber._load_model_bg("tiny.en")
    first_ref = weakref.ref(transcriber.model)
    transcriber._load_model_bg("small.en")

    assert transcriber.model is not None
    assert transcriber.model.model_ref == "small.en"
    _FakeWhisperModel.created.clear()
    gc.collect()
    assert first_ref() is None


def test_stale_load_completion_cannot_publish_or_retain_an_old_selection(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    class _BlockingFakeModel(_FakeWhisperModel):
        def __init__(self, model_ref, **kwargs) -> None:
            if str(model_ref) == "tiny.en":
                entered.set()
                assert release.wait(1.0)
            super().__init__(model_ref, **kwargs)

    _BlockingFakeModel.created = []
    monkeypatch.setattr(transcriber_module, "WhisperModel", _BlockingFakeModel)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    transcriber = _bare_transcriber()
    first = threading.Thread(target=transcriber._load_model_bg, args=("tiny.en",))
    first.start()
    assert entered.wait(1.0)
    # The second request must be selected after the first constructor exits;
    # it must never publish tiny.en as the active retained model.
    transcriber._load_model_bg("small.en")
    release.set()
    deadline = time.monotonic() + 2.0
    while (transcriber.model is None or transcriber.model.model_ref != "small.en") and time.monotonic() < deadline:
        time.sleep(0.01)
    first.join(timeout=0.2)
    assert transcriber.model is not None
    assert transcriber.model.model_ref == "small.en"
    assert list(transcriber._whisper_models) == ["small.en"]


def test_same_selected_model_is_reused_without_reconstructing(monkeypatch) -> None:
    _FakeWhisperModel.created = []
    monkeypatch.setattr(transcriber_module, "WhisperModel", _FakeWhisperModel)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    transcriber = _bare_transcriber()
    transcriber._load_model_bg("tiny.en")
    first = transcriber.model
    transcriber._load_model_bg("tiny.en")
    assert transcriber.model is first
    assert len(_FakeWhisperModel.created) == 1


def test_active_decode_keeps_old_model_alive_until_its_segment_generator_finishes(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    class _Segment:
        text = "decoded"

    class _StreamingModel:
        def transcribe(self, *_args, **_kwargs):
            def segments():
                entered.set()
                assert release.wait(1.0)
                yield _Segment()
            return segments(), None

    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    transcriber = _bare_transcriber()
    old = _StreamingModel()
    old_ref = weakref.ref(old)
    transcriber.model = old
    transcriber._loaded_model_ref = "tiny.en"
    transcriber._requested_model_ref = "tiny.en"
    transcriber._wait_for_model = lambda *_args, **_kwargs: True
    del old
    result: list[str] = []
    decoder = threading.Thread(target=lambda: result.append(transcriber._transcribe_local(np.full(3200, 0.2, dtype=np.float32), model_ref="tiny.en")))
    decoder.start()
    assert entered.wait(1.0)
    transcriber._requested_model_ref = "small.en"
    transcriber._publish_whisper_model("small.en", "small.en", _FakeWhisperModel("small.en"))
    gc.collect()
    assert old_ref() is not None
    release.set()
    decoder.join(timeout=1.0)
    assert result == ["decoded"]
    gc.collect()
    assert old_ref() is None


def test_failed_slow_load_cannot_clear_a_newer_selection(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    class _FailingThenWorkingModel(_FakeWhisperModel):
        def __init__(self, model_ref, **kwargs) -> None:
            if str(model_ref) == "tiny.en":
                entered.set()
                assert release.wait(1.0)
                raise RuntimeError("fake tiny load failed")
            super().__init__(model_ref, **kwargs)

    monkeypatch.setattr(transcriber_module, "WhisperModel", _FailingThenWorkingModel)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    transcriber = _bare_transcriber()
    worker = threading.Thread(target=transcriber._load_model_bg, args=("tiny.en",))
    worker.start()
    assert entered.wait(1.0)
    transcriber._load_model_bg("small.en")
    release.set()
    deadline = time.monotonic() + 2.0
    while (transcriber.model is None or transcriber.model.model_ref != "small.en") and time.monotonic() < deadline:
        time.sleep(0.01)
    worker.join(timeout=0.2)
    assert transcriber.model is not None and transcriber.model.model_ref == "small.en"
    assert transcriber._loaded_model_ref == "small.en"
    assert transcriber._loading is False


def test_nemotron_load_does_not_allocate_whisper_fallback(monkeypatch) -> None:
    class _WarmNemotron:
        is_warm = True

    created = []
    monkeypatch.setattr(transcriber_module, "WhisperModel", lambda *args, **kwargs: created.append((args, kwargs)))
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda ref: str(ref).startswith("nemotron"))
    monkeypatch.setattr(transcriber_module.nemotron_engine, "get_nemotron_engine", lambda _ref: _WarmNemotron())
    transcriber = _bare_transcriber()
    transcriber._load_model_bg("nemotron-test")
    assert created == []
    assert transcriber.model is None
    assert transcriber._whisper_models == {}


def test_delayed_loader_handoff_cannot_replace_a_newer_selection(monkeypatch) -> None:
    scheduled = []

    class DelayedThread:
        def __init__(self, *, target, args=(), kwargs=None, **_unused):
            scheduled.append((target, args, kwargs or {}))

        def start(self):
            pass

    monkeypatch.setattr(transcriber_module, "WhisperModel", _FakeWhisperModel)
    monkeypatch.setattr(transcriber_module.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(threading, "Thread", DelayedThread)
    transcriber = _bare_transcriber()
    transcriber._requested_model_ref = "small.en"
    transcriber._load_latest_after("small.en")
    transcriber._load_model_bg("large-v3")
    target, args, kwargs = scheduled.pop()
    target(*args, **kwargs)
    assert transcriber.model.model_ref == "large-v3"
    assert transcriber._requested_model_ref == "large-v3"
    assert list(transcriber._whisper_models) == ["large-v3"]
