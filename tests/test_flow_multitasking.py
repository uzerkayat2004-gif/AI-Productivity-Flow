"""Offline regressions for independent Voice and Audio Flow work."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from voice_flow import main as main_module
from voice_flow.main import DictationState, DictationSession, VoiceFlowApp


_WAIT_SECONDS = 2.0


def _wait_for(event: threading.Event) -> None:
    assert event.wait(_WAIT_SECONDS), "background flow did not reach its expected checkpoint"


def _wait_until(predicate) -> None:
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "background flow did not reach its expected result"


class _Overlay:
    def __init__(self) -> None:
        self.cancel_callback = None
        self.progress: list[tuple[int, str]] = []
        self.ready_count = 0
        self.rows: dict[str, tuple[str, object]] = {}

    def show_audio_summary_progress(self, percent: int, stage: str, *, job_id: str = "", title: str = "") -> None:
        self.progress.append((percent, stage))
        self.rows[job_id] = ("progress", (percent, stage, title))

    def show_audio_summary_ready(self, _job_id: str, *, stage: str = "Audio ready") -> None:
        self.progress.append((100, stage))
        self.rows[_job_id] = ("ready", stage)

    def show_audio_summary_failed(self, _job_id: str, message: str) -> None:
        self.progress.append((0, message))
        self.rows[_job_id] = ("failed", message)

    def clear_audio_summary_status(self, job_id: str | None = None) -> None:
        if job_id is None:
            self.rows.clear()
        else:
            self.rows.pop(job_id, None)

    def show_video_progress(self, video_id: str, percent: int, stage: str) -> None:
        self.rows[f"video:{video_id}"] = ("video", (percent, stage))

    def clear_video_status(self, video_id: str) -> None:
        self.rows.pop(f"video:{video_id}", None)

    def restart_and_refresh(self) -> None:
        # Keyed flow rows survive a repaint of the same overlay.
        pass

    def show_ready(self) -> None:
        self.ready_count += 1

    def show_error(self, _message: str) -> None:
        pass

    def show_generating_audio(self, *_args) -> None:
        pass

    def show_reading(self, *_args) -> None:
        pass

    def clear_selected_text(self) -> None:
        pass

    def show_processing(self) -> None:
        pass

    def show_done(self, *_args, **_kwargs) -> None:
        pass


class _BlockingNotebookLM:
    """Hold each fake generation until the test releases it; never use a model."""

    def __init__(self) -> None:
        self.started: dict[str, threading.Event] = {}
        self.release: dict[str, threading.Event] = {}
        self.finished: dict[str, threading.Event] = {}
        self.cancelled: dict[str, list[bool]] = {}
        self.cancel_predicates: dict[str, object] = {}
        self._lock = threading.Lock()

    def generate(self, text: str, *, cancelled, on_progress, **_kwargs):
        with self._lock:
            self.started.setdefault(text, threading.Event()).set()
            release = self.release.setdefault(text, threading.Event())
            finished = self.finished.setdefault(text, threading.Event())
            cancelled_calls = self.cancelled.setdefault(text, [])
            self.cancel_predicates[text] = cancelled
        on_progress({"state": "source_ready"})
        try:
            while not release.wait(0.01):
                cancelled_calls.append(bool(cancelled()))
            cancelled_calls.append(bool(cancelled()))
            return {"audio_path": "fake-audio.m4a", "duration_sec": 1.0}
        finally:
            finished.set()


def _app(monkeypatch, notebook: _BlockingNotebookLM) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app._test_threads = []
    app._launched_players = []
    app._history_updates = []
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.session = None
    app._record_watchdog = None
    app._audio_summary_generation = 0
    app._selection_generation = 0
    app._active_summary_player_token = None
    app.overlay = _Overlay()
    app.injector = SimpleNamespace(get_selected_text=lambda **_kwargs: "", paste_text=lambda *_args, **_kwargs: True)
    app.recent_dictations = set()
    app.last_successful_transcript = None
    app.audio = SimpleNamespace(
        begin_stream_input_buffering=lambda: None,
        start=lambda: True,
        flush_stream_input_buffer=lambda: None,
        discard_stream_input_buffer=lambda: None,
        stop=lambda: np.ones(16000, dtype=np.float32),
        level=0.0,
    )
    app.transcriber = SimpleNamespace(
        prepare_model_async=lambda *_args, **_kwargs: None,
        transcribe=lambda *_args, **_kwargs: "voice dictation delivered",
    )
    app.processing_lock = threading.Lock()
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app._capture_session = lambda: DictationSession(1, "Editor", "smart_clean", "smart_clean", 0.0)
    app._start_stream_for_session = lambda _session: None
    app._start_window_tracker = lambda _session: None
    app._streaming_stt_enabled = lambda: False
    app._get_current_external_window = lambda: None
    app._is_internal_window = lambda _hwnd: False
    app._defer_history_insert = lambda *_args, **_kwargs: None
    app._release_session_model_resource = lambda *_args, **_kwargs: None
    app._set_hotkeys_recording_state = lambda *_args: None
    app._end_stream_session = lambda **_kwargs: None
    app._start_recovery_archive = lambda _buffer, recovery=None: recovery
    app._finalize_text = lambda text, *_args, **_kwargs: text

    original_thread = threading.Thread

    class TrackedThread(original_thread):
        def start(self) -> None:
            app._test_threads.append(self)
            super().start()

    monkeypatch.setattr(main_module.threading, "Thread", TrackedThread)

    def reset_to_idle(session=None):
        with app._state_lock:
            if session is None or app.session is session:
                app.session = None
                app.state = DictationState.IDLE

    app._reset_to_idle = reset_to_idle
    monkeypatch.setattr(main_module, "_warm_voice_gemini_transport", lambda *_args: None)
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.storage, "add_audio_summary_history", lambda **_kwargs: None)
    monkeypatch.setattr(
        main_module.storage,
        "update_audio_summary_history",
        lambda item_id, **kwargs: app._history_updates.append((item_id, dict(kwargs))) or True,
    )
    monkeypatch.setattr(main_module.storage, "record_audio_summary_to_history", lambda **_kwargs: None)
    monkeypatch.setattr(main_module.storage, "add_dictation", lambda *_args, **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(main_module.storage, "update_dictation", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main_module, "detect_voice_command", lambda text: SimpleNamespace(command=None, content=text))
    monkeypatch.setattr(main_module.storage, "_derive_audio_title", lambda text: text[:20])
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: None)
    monkeypatch.setattr(main_module.audio_flow_widget, "set_playing", lambda *_args: None)
    monkeypatch.setattr(main_module.tts_engine, "is_speaking", lambda: False)
    monkeypatch.setattr(main_module.tts_engine, "stop", lambda: None)
    from voice_flow import audio_notebooklm
    monkeypatch.setattr(audio_notebooklm, "audio_notebooklm_service", notebook)
    from voice_flow import audio_summary_player
    monkeypatch.setattr(
        audio_summary_player,
        "launch_summary_audio_player",
        lambda *_args, **_kwargs: app._launched_players.append(_kwargs) or "fake-player",
    )
    monkeypatch.setattr(audio_summary_player, "save_media_to_downloads", lambda *_args, **_kwargs: (None, None))
    try:
        from voice_flow.gui import api_server
        monkeypatch.setattr(api_server, "invalidate_history_cache", lambda: None)
    except Exception:
        pass
    return app


def _start_summary(app: VoiceFlowApp, notebook: _BlockingNotebookLM, text: str) -> None:
    app._process_audio_flow_pipeline(text_override=text, mode="summary")
    _wait_for(notebook.started.setdefault(text, threading.Event()))


def _release_and_join(app: VoiceFlowApp, notebook: _BlockingNotebookLM) -> None:
    for event in notebook.release.values():
        event.set()
    jobs = getattr(app, "_audio_flow_jobs", None)
    if jobs is not None:
        jobs.shutdown(timeout=_WAIT_SECONDS)
    for event in notebook.finished.values():
        assert event.wait(_WAIT_SECONDS), "fake NotebookLM worker did not exit during cleanup"
    for worker in app._test_threads:
        worker.join(_WAIT_SECONDS)
        assert not worker.is_alive(), "flow worker did not exit during cleanup"


def _job_for_text(app: VoiceFlowApp, text: str):
    jobs = app._audio_flow_jobs
    assert jobs is not None
    return next(job for job in jobs.snapshot() if job.text == text)


def test_summary_survives_dictation_start_and_finish(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    pasted: list[str] = []
    app.injector.paste_text = lambda text, *_args, **_kwargs: pasted.append(text) or True
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda _kind: object())

    try:
        _start_summary(app, notebook, "existing summary")
        assert app._on_dictation_start() is True
        assert app._on_dictation_finish() is True
        _wait_until(lambda: "voice dictation delivered" in pasted)
        _wait_until(lambda: app.state == DictationState.IDLE)

        assert notebook.cancel_predicates["existing summary"]() is False, (
            "dictation start/finish cancelled an unrelated NotebookLM summary"
        )
        assert app.state == DictationState.IDLE
    finally:
        _release_and_join(app, notebook)


def test_second_summary_does_not_cancel_first_summary(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    try:
        _start_summary(app, notebook, "first summary")
        _start_summary(app, notebook, "second summary")

        assert notebook.cancel_predicates["first summary"]() is False, (
            "starting a second summary cancelled the first summary"
        )
        assert notebook.cancel_predicates["second summary"]() is False
    finally:
        _release_and_join(app, notebook)


def test_read_start_does_not_cancel_active_summary(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    spoken: list[str] = []

    class FakeTTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_kwargs) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)

    try:
        _start_summary(app, notebook, "active summary")
        app._process_audio_flow_pipeline(text_override="read this aloud", mode="read_verbatim")

        assert notebook.cancel_predicates["active summary"]() is False, (
            "starting Read cancelled an unrelated NotebookLM summary"
        )
        assert spoken == ["read this aloud"]
    finally:
        _release_and_join(app, notebook)


def test_cancel_one_summary_is_job_scoped_and_does_not_resurrect_deleted_history(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    try:
        _start_summary(app, notebook, "cancel me")
        _start_summary(app, notebook, "keep running")
        cancelled_job = _job_for_text(app, "cancel me")
        survivor_job = _job_for_text(app, "keep running")

        assert app.cancel_audio_summary_job(cancelled_job.job_id) is True
        assert cancelled_job.status == "cancelled"
        assert survivor_job.status == "running"
        assert notebook.cancel_predicates["keep running"]() is False
        cancel_updates = [
            values for item_id, values in app._history_updates
            if item_id == cancelled_job.job_id and values.get("status") == "cancelled"
        ]
        assert len(cancel_updates) == 1, "cancel must persist its terminal state before returning"

        # Match the API delete-after-cancel sequence. The provider worker may
        # exit later, but it must not write another history update.
        app._history_updates[:] = [row for row in app._history_updates if row[0] != cancelled_job.job_id]
        notebook.release["cancel me"].set()
        _wait_for(notebook.finished["cancel me"])
        app._audio_flow_jobs.shutdown(timeout=_WAIT_SECONDS)
        assert not any(item_id == cancelled_job.job_id for item_id, _ in app._history_updates)
    finally:
        _release_and_join(app, notebook)


def test_two_summaries_complete_out_of_order_without_autoplay_during_voice(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    try:
        _start_summary(app, notebook, "earlier job")
        _start_summary(app, notebook, "later job")
        earlier = _job_for_text(app, "earlier job")
        later = _job_for_text(app, "later job")
        app.overlay.show_video_progress("video-1", 35, "Rendering")
        app.state = DictationState.RECORDING

        notebook.release["later job"].set()
        _wait_until(lambda: later.status == "ready" and app.overlay.rows.get(later.job_id, (None,))[0] == "ready")
        assert earlier.status == "running"
        assert app._launched_players == []
        assert app.overlay.rows[later.job_id][0] == "ready"
        assert app.overlay.rows["video:video-1"][0] == "video"

        notebook.release["earlier job"].set()
        _wait_until(lambda: earlier.status == "ready" and app.overlay.rows.get(earlier.job_id, (None,))[0] == "ready")
        assert app._launched_players == []
        assert app.state == DictationState.RECORDING
    finally:
        _release_and_join(app, notebook)


def test_summary_completion_does_not_autoplay_over_active_read(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    spoken: list[str] = []

    class FakeTTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **callbacks) -> None:
            spoken.append(text)
            callbacks["on_start"]()

        def stop(self) -> None:
            pass

    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    from voice_flow.audio_explainer import audio_explainer
    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", lambda text: text)
    try:
        _start_summary(app, notebook, "summary beside read")
        app._process_audio_flow_pipeline(text_override="read while summary runs", mode="read_verbatim")
        assert app._read_active is True

        notebook.release["summary beside read"].set()
        summary = _job_for_text(app, "summary beside read")
        _wait_until(lambda: summary.status == "ready" and app.overlay.rows.get(summary.job_id, (None,))[0] == "ready")
        assert app._launched_players == []
        assert app._read_active is True
        assert spoken == ["read while summary runs"]
    finally:
        _release_and_join(app, notebook)


def test_starting_read_closes_only_the_tracked_summary_player(monkeypatch) -> None:
    app = _app(monkeypatch, _BlockingNotebookLM())
    closed: list[str] = []
    spoken: list[str] = []

    class FakeTTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    from voice_flow import audio_summary_player
    monkeypatch.setattr(audio_summary_player, "close_summary_audio_player", lambda token=None: closed.append(token))
    try:
        app._active_summary_player_token = "tracked-player"
        app._process_audio_flow_pipeline(text_override="read selected words", mode="read_verbatim")
        assert closed == ["tracked-player"]
        assert spoken == ["read selected words"]
        assert app._active_summary_player_token is None
    finally:
        _release_and_join(app, _BlockingNotebookLM())


def test_stale_explanatory_read_cannot_start_after_voice_claims_foreground(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    transform_started = threading.Event()
    finish_transform = threading.Event()
    spoken: list[str] = []

    class FakeTTS:
        def is_speaking(self) -> bool:
            return False

        def speak(self, text, **_callbacks) -> None:
            spoken.append(text)

        def stop(self) -> None:
            pass

    monkeypatch.setattr(main_module, "tts_engine", FakeTTS())
    from voice_flow.audio_explainer import audio_explainer

    def delayed_transform(text: str) -> str:
        transform_started.set()
        assert finish_transform.wait(_WAIT_SECONDS)
        return f"spoken {text}"

    monkeypatch.setattr(audio_explainer, "transform_for_human_reading", delayed_transform)
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda _kind: object())
    try:
        app._process_audio_flow_pipeline(text_override="pending explanation", mode="read")
        _wait_for(transform_started)
        old_generation = app._read_generation
        assert app._read_pending is True
        assert app._on_dictation_start() is True
        assert app.state == DictationState.RECORDING

        finish_transform.set()
        _wait_until(lambda: all(not worker.is_alive() for worker in app._test_threads if worker.name == "AudioFlowExplanatoryRead"))
        assert app._read_generation > old_generation
        assert app._read_pending is False
        assert spoken == []
        assert app.state == DictationState.RECORDING
    finally:
        finish_transform.set()
        _release_and_join(app, notebook)


def test_overlay_refresh_keeps_background_summary_and_video_rows(monkeypatch) -> None:
    notebook = _BlockingNotebookLM()
    app = _app(monkeypatch, notebook)
    try:
        _start_summary(app, notebook, "keep through repaint")
        job = _job_for_text(app, "keep through repaint")
        app.overlay.show_video_progress("video-2", 20, "Composing")
        rows_before = dict(app.overlay.rows)

        app.reset_state_and_refresh()

        assert app.overlay.rows == rows_before
        assert job.status == "running"
        assert notebook.cancel_predicates["keep through repaint"]() is False
    finally:
        _release_and_join(app, notebook)


def test_audio_job_queue_is_bounded_and_clears_completed_source() -> None:
    from voice_flow.audio_flow_jobs import AudioFlowJobs

    first_started = threading.Event()
    second_started = threading.Event()
    finish_first = threading.Event()
    finish_second = threading.Event()
    in_progress_history: list[str] = []
    jobs = AudioFlowJobs(max_workers=1, max_queued=1, retained_terminal=1)

    def run_first(_job):
        first_started.set()
        assert finish_first.wait(_WAIT_SECONDS)
        return {"audio_path": "first.m4a"}

    def run_second(_job):
        second_started.set()
        assert finish_second.wait(_WAIT_SECONDS)
        return {"audio_path": "second.m4a"}

    try:
        first = jobs.submit(
            job_id="one", text="private source one", depth="short", style="single", title="One", run=run_first,
        )
        _wait_for(first_started)
        second = jobs.submit(
            job_id="two", text="private source two", depth="short", style="single", title="Two", run=run_second,
        )
        with pytest.raises(RuntimeError, match="queue is full"):
            jobs.submit(
                job_id="three", text="must not be retained", depth="short", style="single", title="Three",
                run=lambda _job: None,
                before_enqueue=lambda: in_progress_history.append("created"),
            )
        assert in_progress_history == []
        assert second.status == "queued"

        finish_first.set()
        _wait_until(lambda: first.status == "ready")
        _wait_for(second_started)
        _wait_until(lambda: first.text == "")
        assert first.text == ""

        finish_second.set()
        _wait_until(lambda: second.status == "ready")
        _wait_until(lambda: second.text == "")
        assert second.text == ""
        assert len(jobs.snapshot()) == 1
    finally:
        finish_first.set()
        finish_second.set()
        jobs.shutdown(timeout=_WAIT_SECONDS)


def test_export_suffix_survives_repeated_and_long_titles(monkeypatch) -> None:
    app = _app(monkeypatch, _BlockingNotebookLM())
    from voice_flow import audio_summary_player
    names: list[str] = []
    monkeypatch.setattr(
        audio_summary_player,
        "save_media_to_downloads",
        lambda _source, filename, **_kwargs: names.append(filename) or (None, None),
    )
    try:
        app._export_audio_summary_copy("ash_job-1234", "Same title", "fake-audio.m4a")
        app._export_audio_summary_copy("ash_job-9876", "Same title", "fake-audio.m4a")
        long_title = "A very long title " * 30
        app._export_audio_summary_copy("ash_job-long1", long_title, "fake-audio.m4a")
        app._export_audio_summary_copy("ash_job-long2", long_title, "fake-audio.m4a")
        assert names[0] != names[1]
        assert names[2] != names[3]
        assert "1234" in names[0]
        assert "long1" in names[2]
    finally:
        _release_and_join(app, _BlockingNotebookLM())


def test_simultaneous_ready_jobs_reserve_only_one_foreground_player(monkeypatch) -> None:
    from voice_flow.audio_flow_jobs import AudioFlowJobs

    app = _app(monkeypatch, _BlockingNotebookLM())
    jobs = AudioFlowJobs(max_workers=2)
    barrier = threading.Barrier(3)
    results: list[bool] = []
    monkeypatch.setattr(main_module.tts_engine, "is_speaking", lambda: False)

    def create_ready(job_id: str):
        return jobs.submit(
            job_id=job_id, text="", depth="short", style="single", title=job_id,
            run=lambda _job: {"audio_path": f"{job_id}.m4a"},
        )

    try:
        first = create_ready("ready-one")
        second = create_ready("ready-two")
        _wait_until(lambda: first.status == second.status == "ready")
        app._audio_flow_jobs = jobs

        def try_open(job_id: str) -> None:
            barrier.wait(_WAIT_SECONDS)
            results.append(app._try_open_audio_summary_job(job_id, automatic=True))

        workers = [threading.Thread(target=try_open, args=(job.job_id,)) for job in (first, second)]
        for worker in workers:
            worker.start()
        barrier.wait(_WAIT_SECONDS)
        for worker in workers:
            worker.join(_WAIT_SECONDS)
            assert not worker.is_alive()

        assert results.count(True) == 1
        assert len(app._launched_players) == 1
    finally:
        jobs.shutdown(timeout=_WAIT_SECONDS)
        app._audio_flow_jobs = None
