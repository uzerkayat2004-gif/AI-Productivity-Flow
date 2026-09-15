from __future__ import annotations

from voice_flow.overlay import FloatingOverlayBar


class _Canvas:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.fills: list[str] = []
        self.lines: list[tuple[object, ...]] = []

    def delete(self, *args, **kwargs):
        pass

    def create_text(self, *args, **kwargs):
        text = kwargs.get("text")
        if text is not None:
            self.texts.append(str(text))
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_rectangle(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_oval(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_polygon(self, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())

    def create_line(self, *args, **kwargs):
        self.lines.append(args)
        fill = kwargs.get("fill")
        if fill is not None:
            self.fills.append(str(fill).lower())


def _bar_with_canvas() -> tuple[FloatingOverlayBar, _Canvas]:
    bar = FloatingOverlayBar()
    canvas = _Canvas()
    bar.canvas = canvas
    return bar, canvas


def test_audio_and_video_active_states_use_product_labels() -> None:
    bar, canvas = _bar_with_canvas()
    bar._draw_reading(240, 32)
    assert any("Audio Flow" in text for text in canvas.texts)

    canvas.texts.clear()
    bar.video_status = "processing"
    bar._draw_video_status(294, 32, compact=False)
    assert any("Video Flow" in text for text in canvas.texts)


def test_working_state_does_not_expose_error_copy_or_decorative_lines() -> None:
    bar, canvas = _bar_with_canvas()
    bar.error_message = "Dangerous provider failure"
    bar._draw_error(180, 32)
    assert canvas.texts == ["Working"]
    assert canvas.lines == []


def test_hover_bar_uses_the_orange_product_accent() -> None:
    bar, canvas = _bar_with_canvas()
    bar.state = "READY"
    bar._is_mouse_over = True
    bar.width = bar.ready_actions_width
    bar._hover_zone = "video_flow"
    bar._draw_ready(bar.width, bar.hover_height)
    assert any(str(color).lower() in {"#ff6b00", "#ff6a00"} for color in canvas.fills)


def test_video_processing_progress_strip_layout_and_geometry() -> None:
    bar, canvas = _bar_with_canvas()
    bar.state = "READY"
    bar.video_status = "processing"
    bar.video_progress = 45
    bar.video_job_id = "job-123"

    w, h = bar._target_size()
    assert (w, h) == (bar.video_progress_width, bar.video_progress_height)
    assert w >= 260
    assert h >= 24

    bar._draw()
    assert "Video Flow" in canvas.texts
    assert "45%" in canvas.texts

    # Test hit zones for progress rail
    grip_x = bar.width - 5
    cancel_x = bar.width - bar.GRIP_W - 8
    assert bar._get_zone(grip_x) == "grip"
    assert bar._get_zone(cancel_x) == "video_cancel"


def test_video_failed_state_pill_dimensions_and_interactions() -> None:
    from types import SimpleNamespace
    bar, canvas = _bar_with_canvas()
    bar.state = "READY"
    bar.video_status = "failed"
    bar.video_stage = "Render timeout"
    bar.video_job_id = "job-failed-1"

    w, h = bar._target_size()
    assert (w, h) == (bar.video_failed_width, bar.video_status_height)
    assert w >= 190
    assert h >= 24

    bar._draw()
    assert any("Video failed" in t for t in canvas.texts)
    assert "!" in canvas.texts

    # Hit zones
    cancel_x = bar.width - bar.GRIP_W - 8
    status_x = 50
    assert bar._get_zone(cancel_x) == "video_cancel"
    assert bar._get_zone(status_x) == "video_status"

    # Clicking status zone triggers show_error and clears video_status
    bar.show_error = lambda msg: setattr(bar, "_error_shown", msg)
    bar._on_press(SimpleNamespace(x=status_x, y=h // 2))
    assert getattr(bar, "_error_shown", None) == "Render timeout"
    assert bar.video_status == ""


def test_video_ready_state_pill_dimensions_and_interactions() -> None:
    from types import SimpleNamespace
    bar, canvas = _bar_with_canvas()
    bar.state = "READY"
    bar.video_status = "ready"
    bar.video_job_id = "job-ready-1"

    w, h = bar._target_size()
    assert (w, h) == (bar.video_ready_width, bar.video_status_height)
    assert (w, h) == (280, 26)
    assert w >= 180
    assert h >= 24

    bar._draw()
    assert any("Video Ready" in t for t in canvas.texts)
    assert "▶ Video Ready — Click to play" in canvas.texts

    # Hit zones and clicking opens video player
    status_x = 50
    assert bar._get_zone(status_x) == "video_status"

    ready_jobs: list[str] = []
    bar.on_video_ready = ready_jobs.append
    bar._on_press(SimpleNamespace(x=status_x, y=h // 2))
    assert ready_jobs == ["job-ready-1"]
    assert bar.video_status == ""


def test_main_queue_monitor_and_open_player_flow() -> None:
    from unittest.mock import MagicMock, patch
    from types import SimpleNamespace
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.FloatingOverlayBar") as mock_bar_cls, \
         patch("voice_flow.main.storage") as mock_storage, \
         patch("voice_flow.main.video_flow_widget") as mock_widget, \
         patch("voice_flow.video_flow_service.get_video_flow_service") as mock_get_service:

        mock_storage.get_setting.return_value = True
        mock_storage.get_recent_history.return_value = []

        fake_overlay = MagicMock()
        mock_bar_cls.return_value = fake_overlay

        app = VoiceFlowApp()
        app.overlay = fake_overlay

        # Verify overlay.on_video_ready calls video_flow_widget.open_player
        assert app.overlay.on_video_ready is not None
        app.overlay.on_video_ready("test-vid-123")
        mock_widget.open_player.assert_called_once_with("test-vid-123")

        # Setup mock job in service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_job = SimpleNamespace(
            job_id="vid-xyz",
            state="rendering",
            progress=55.0,
            message="Rendering scene 2",
            meta={},
        )
        mock_service.queue.return_value = mock_job
        mock_service.get.return_value = mock_job

        # Test queueing from screen
        with patch("threading.Thread") as mock_thread:
            result = app._queue_video_from_screen({"source_text": "Sample text", "mode": "summary"})
            assert result == {"id": "vid-xyz"}
            assert app.video_stage == "Queued"
            fake_overlay.show_video_progress.assert_called_with("vid-xyz", 0, "Queued")
            mock_thread.assert_called_once()

        # Test _monitor_video_flow_job updates progress smoothly and transitions to ready
        calls = []
        fake_overlay.show_video_progress.side_effect = lambda vid, prog, st: calls.append((vid, prog, st))

        job_states = [
            SimpleNamespace(job_id="vid-xyz", state="rendering", progress=55.0, message="Rendering scene 2", meta={}),
            SimpleNamespace(job_id="vid-xyz", state="complete", progress=100.0, message="Complete", meta={}),
        ]

        def fake_get(vid):
            if job_states:
                return job_states.pop(0)
            return SimpleNamespace(job_id="vid-xyz", state="complete", progress=100.0, message="Complete", meta={})

        mock_service.get.side_effect = fake_get

        with patch("time.sleep", return_value=None):
            app._monitor_video_flow_job("vid-xyz")

        assert len(calls) >= 1
        assert calls[0] == ("vid-xyz", 55.0, "Rendering scene 2")
        fake_overlay.show_video_ready.assert_called_once_with("vid-xyz")
        assert app.video_stage == "Video ready"


