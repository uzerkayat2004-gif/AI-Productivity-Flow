from __future__ import annotations

from types import SimpleNamespace

from voice_flow.overlay import FloatingOverlayBar


class FakeCanvas:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.items: list[tuple[str, tuple, dict]] = []

    def delete(self, *_args, **_kwargs) -> None:
        self.texts.clear()
        self.items.clear()

    def __getattr__(self, name: str):
        if name.startswith("create_"):
            def create(*args, **kwargs):
                self.items.append((name, args, kwargs))
                if name == "create_text" and "text" in kwargs:
                    self.texts.append(str(kwargs["text"]))
            return create
        raise AttributeError(name)


def make_bar() -> tuple[FloatingOverlayBar, FakeCanvas]:
    bar = FloatingOverlayBar()
    canvas = FakeCanvas()
    bar.canvas = canvas
    return bar, canvas


def row_point(bar: FloatingOverlayBar, index: int, *, right: bool = False) -> tuple[int, int]:
    top, bottom, _row = bar._summary_row_geometry()[index]
    x = bar.width - bar.GRIP_W - 8 if right else 80
    return x, (top + bottom) // 2


def test_video_and_multiple_audio_rows_draw_together_and_have_distinct_hits() -> None:
    bar, canvas = make_bar()
    bar.state = "READY"
    bar.selected_text = "highlight to keep"
    generation = bar._selection_generation
    bar.show_video_progress("video-1", 42, "Rendering")
    bar.show_audio_summary_progress(31, "Writing narration", job_id="audio-1")
    bar.show_audio_summary_progress(76, "Synthesizing", job_id="audio-2")

    bar._draw()
    assert any("Video Flow · 42% · Rendering" in text for text in canvas.texts)
    assert any("Audio Flow · 31% · Writing narration" in text for text in canvas.texts)
    assert any("Audio Flow · 76% · Synthesizing" in text for text in canvas.texts)
    assert bar.selected_text == "highlight to keep"
    assert bar._selection_generation == generation

    cancel_ids: list[str] = []
    bar.on_video_cancel = cancel_ids.append
    bar.on_audio_summary_cancel = cancel_ids.append
    for index, expected_zone in enumerate(("summary_cancel:0", "summary_cancel:1", "summary_cancel:2")):
        x, y = row_point(bar, index, right=True)
        assert bar._get_zone(x, y) == expected_zone
    x, y = row_point(bar, 1, right=True)
    bar._on_press(SimpleNamespace(x=x, y=y))
    assert cancel_ids == ["audio-1"]
    assert bar.video_status == "processing"
    assert "audio-1" not in bar._audio_summary_jobs
    assert "audio-2" in bar._audio_summary_jobs
    assert bar.state == "READY"
    assert bar.selected_text == "highlight to keep"


def test_background_rows_preserve_each_voice_foreground_state() -> None:
    for state in ("READY", "RECORDING", "PROCESSING", "READING", "DONE", "ERROR"):
        bar, canvas = make_bar()
        bar.state = state
        bar.selected_text = "selection"
        bar.show_video_progress("v", 20, "Making video")
        bar.show_audio_summary_progress(55, "Making audio", job_id="a")
        bar._draw()
        assert bar.state == state
        assert bar.selected_text == "selection"
        assert any("Video Flow · 20% · Making video" in text for text in canvas.texts)
        assert any("Audio Flow · 55% · Making audio" in text for text in canvas.texts)
        assert len(bar._summary_row_geometry()) == 2


def test_ready_audio_row_activates_and_dismisses_only_that_job() -> None:
    bar, canvas = make_bar()
    bar.state = "READING"
    bar.show_audio_summary_ready("audio-ready")
    bar.show_audio_summary_ready("audio-other")
    bar._draw()
    assert sum("Audio Ready" in text for text in canvas.texts) == 2

    ready_ids: list[str] = []
    bar.on_audio_summary_ready = ready_ids.append
    ready_index = next(i for i, row in enumerate(bar._summary_rows()) if row.get("job_id") == "audio-ready")
    x, y = row_point(bar, ready_index)
    assert bar._get_zone(x, y) == f"summary_activate:{ready_index}"
    bar._on_press(SimpleNamespace(x=x, y=y))
    assert ready_ids == ["audio-ready"]
    assert "audio-ready" not in bar._audio_summary_jobs
    assert "audio-other" in bar._audio_summary_jobs
    assert bar.state == "READING"

    dismiss_index = next(i for i, row in enumerate(bar._summary_rows()) if row.get("job_id") == "audio-other")
    dismiss_x, dismiss_y = row_point(bar, dismiss_index, right=True)
    assert bar._get_zone(dismiss_x, dismiss_y) == f"summary_dismiss:{dismiss_index}"
    bar._on_press(SimpleNamespace(x=dismiss_x, y=dismiss_y))
    assert "audio-other" not in bar._audio_summary_jobs
    assert bar.state == "READING"


def test_background_failure_and_clears_do_not_replace_foreground() -> None:
    bar, _canvas = make_bar()
    bar.state = "RECORDING"
    bar.show_audio_summary_failed("failed-audio", "Offline")
    bar.clear_audio_summary_status("missing-audio")
    assert bar.state == "RECORDING"
    assert "failed-audio" in bar._audio_summary_jobs
    bar.clear_audio_summary_status("failed-audio")
    assert bar.state == "RECORDING"
    assert not bar._audio_summary_jobs


def test_cancel_hit_targets_work_in_voice_and_read_states() -> None:
    for state in ("RECORDING", "READING"):
        bar, _canvas = make_bar()
        bar.state = state
        bar.show_audio_summary_progress(10, "Queued", job_id="one")
        bar.show_audio_summary_progress(20, "Rendering", job_id="two")
        cancelled: list[str] = []
        bar.on_audio_summary_cancel = lambda job_id: cancelled.append(job_id)
        x, y = row_point(bar, 1, right=True)
        bar._on_press(SimpleNamespace(x=x, y=y))
        assert cancelled == ["two"]
        assert bar.state == state
        assert "one" in bar._audio_summary_jobs
        assert "two" not in bar._audio_summary_jobs


def test_foreground_hitboxes_use_foreground_width_when_rows_are_wider() -> None:
    bar, _canvas = make_bar()
    bar.state = "RECORDING"
    bar.show_video_progress("video", 10, "Rendering")
    assert bar._get_zone(170, 12) == "finish"
    assert bar._get_zone(180, 12) == "grip"

    bar.state = "READY"
    bar._is_mouse_over = True
    bar.show_audio_summary_progress(15, "Making audio", job_id="audio")
    # Settings sits at the right side of the 248px voice bar; row width is 280.
    assert bar._get_zone(220, 10) == "settings"
    row_top, _row_bottom, _row = bar._summary_row_geometry()[0]
    assert bar._get_zone(258, row_top + 1) == "summary_cancel:0"


def test_false_or_failed_callbacks_leave_job_rows_available() -> None:
    bar, _canvas = make_bar()
    bar.state = "READING"
    bar.show_audio_summary_progress(100, "Audio ready", job_id="ready-job", title="Research Notes")
    bar.show_audio_summary_ready("ready-job")
    bar._draw()
    assert any("Research Notes Ready" in text for text in bar.canvas.texts)
    bar.on_audio_summary_ready = lambda _job_id: False
    x, y = row_point(bar, 0)
    bar._on_press(SimpleNamespace(x=x, y=y))
    assert "ready-job" in bar._audio_summary_jobs
    assert bar.state == "READING"

    bar.show_audio_summary_progress(60, "Synthesis", job_id="running-job")
    bar.on_audio_summary_cancel = lambda _job_id: False
    x, y = row_point(bar, 1, right=True)
    bar._on_press(SimpleNamespace(x=x, y=y))
    assert "running-job" in bar._audio_summary_jobs
    assert bar.state == "READING"


def test_long_audio_titles_are_clipped_before_ready_and_failure_controls() -> None:
    bar, canvas = make_bar()
    bar.state = "READY"
    long_title = "A Very Long Audio Summary Title That Runs Past The Close Button"
    bar.show_audio_summary_ready("ready-long", title=long_title)
    bar.show_audio_summary_failed("failed-long", "Playback conversion failed", title=long_title)
    bar._draw()

    ready_label = next(text for text in canvas.texts if "Ready — Click to play" in text)
    failed_label = next(text for text in canvas.texts if "failed — click to dismiss" in text)
    assert "A Very Long Audio…" in ready_label
    assert "A Very Long Audio…" in failed_label
    assert len(ready_label) <= 42
    assert len(failed_label) <= 48


def test_row_count_is_bounded_and_both_themes_keep_existing_palette() -> None:
    for dark, expected in ((False, "#FFFFFF"), (True, "#20201f")):
        bar, canvas = make_bar()
        bar.state = "READY"
        bar._is_theme_dark = lambda: dark
        bar.show_video_progress("video", 1, "Rendering")
        for index in range(8):
            bar.show_audio_summary_progress(index, "Synthesizing", job_id=f"audio-running-{index}")
        for index in range(6):
            bar.show_audio_summary_ready(f"audio-final-{index}", title=f"Final {index}")
        bar._draw()
        assert bar.WHITE == expected
        assert len(bar._summary_row_geometry()) == bar.MAX_SUMMARY_ROWS
        row_ids = [row["job_id"] for _top, _bottom, row in bar._summary_row_geometry()]
        assert all(f"audio-running-{index}" in row_ids for index in range(8))
        assert "audio-final-0" not in row_ids
        assert all(f"audio-final-{index}" in row_ids for index in range(2, 6))
        assert bar.height <= bar.idle_height + 4 + bar.MAX_SUMMARY_ROWS * 26 + (bar.MAX_SUMMARY_ROWS - 1) * 2
        assert any(item[2].get("fill") == expected for item in canvas.items if item[0] == "create_polygon")


def test_processing_rows_share_one_animation_timer() -> None:
    class FakeRoot:
        def __init__(self) -> None:
            self.callbacks = []

        def after(self, delay: int, callback):
            self.callbacks.append((delay, callback))
            return len(self.callbacks)

    bar, _canvas = make_bar()
    bar.root = FakeRoot()
    bar.show_video_progress("video", 5, "Rendering")
    bar.show_audio_summary_progress(10, "Synthesizing", job_id="audio-1")
    bar.show_audio_summary_progress(20, "Synthesizing", job_id="audio-2")
    assert len(bar.root.callbacks) == 1
    assert bar.root.callbacks[0][0] == 90


def test_restart_refresh_preserves_background_job_rows_without_tk() -> None:
    bar, _canvas = make_bar()
    bar.state = "READING"
    bar.selected_text = "foreground text"
    bar.video_job_id = "video-running"
    bar.video_status = "processing"
    bar.video_progress = 32
    bar.video_stage = "Rendering"
    bar._audio_summary_jobs["audio-ready"] = {
        "status": "ready", "progress": 100, "stage": "Audio ready", "title": "Notes"
    }
    bar.win = SimpleNamespace(winfo_exists=lambda: True)
    bar._run_on_ui = lambda callback: callback()
    bar._set_bar_size = lambda *_size: None
    bar._position_window = lambda: None
    bar._bring_to_top = lambda: None
    bar.restart_and_refresh()
    assert bar.state == "READY"
    assert bar.selected_text == ""
    assert bar.video_job_id == "video-running"
    assert bar.video_status == "processing"
    assert bar._audio_summary_jobs["audio-ready"]["status"] == "ready"
    assert {row["job_id"] for row in bar._summary_rows()} == {"video-running", "audio-ready"}
