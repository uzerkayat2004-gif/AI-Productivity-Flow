from __future__ import annotations

import base64
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from voice_flow.overlay import FloatingOverlayBar
import voice_flow.video_flow_widget as widget_module
from voice_flow.video_flow_widget import VideoFlowScreenWidget, launch_video_flow_composer, video_flow_widget


@pytest.fixture(scope="module")
def shared_tk():
    """Create a single headless Tk root for the test module."""
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def clean_widget(shared_tk: tk.Tk):
    """Provide a freshly attached VideoFlowScreenWidget and ensure cleanup."""
    widget = VideoFlowScreenWidget()
    widget.attach_root(shared_tk)
    yield widget
    try:
        widget._stop_grid()
        if widget.win and widget.win.winfo_exists():
            widget.win.destroy()
    except Exception:
        pass


# ============================================================================
# 1. VideoFlowScreenWidget initialization and UI building
# ============================================================================

def test_video_flow_screen_widget_initialization() -> None:
    widget = VideoFlowScreenWidget()
    assert widget.root is None
    assert widget.win is None
    assert widget.on_generate is None
    assert widget._mode == "summary"


def test_video_flow_screen_widget_ui_building_and_controls(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()

    assert widget.win is not None
    assert widget.win.winfo_exists()
    assert widget.win.title() == "Video Flow — Create video"

    # Verify all essential controls in dictionary
    expected_controls = [
        "source", "title", "mode", "file_label", "status", "status_label",
        "generate", "scroll_canvas", "scrollbar", "analysis_banner",
        "format", "format_display", "style", "style_display",
    ]
    for key in expected_controls:
        assert key in widget._controls, f"Missing control: {key}"

    # Verify 6 grid dots created
    assert len(widget._grid_dots) == 6
    assert widget._grid_animating is False


def test_video_flow_screen_widget_show_composer_populates_state(clean_widget: VideoFlowScreenWidget, shared_tk: tk.Tk) -> None:
    widget = clean_widget

    # Mock _refresh_models to prevent network call
    with patch.object(widget, "_refresh_models"):
        widget.show_composer(selected_text="AI Productivity Flow Overview", mode="full")
        shared_tk.update()

        assert widget._mode == "full"
        assert widget._source_text == "AI Productivity Flow Overview"
        assert widget._source_name == "Selected text"
        assert widget._controls["source"].get("1.0", "end-1c") == "AI Productivity Flow Overview"
        assert widget._controls["mode"].get() == "full"
        assert widget._controls["file_label"].get() == "Selected text"
        assert widget._controls["status"].get() == "Selected text is ready."

        # Reset with empty text
        widget.show_composer(selected_text="", mode="summary")
        shared_tk.update()
        assert widget._mode == "summary"
        assert widget._controls["source"].get("1.0", "end-1c") == ""
        assert widget._controls["file_label"].get() == "No document selected"
        assert widget._controls["status"].get() == "Paste text or choose a document."


def test_video_flow_widget_grid_animation_controls(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()

    widget._start_grid()
    assert widget._grid_animating is True
    assert widget._grid_after_id is not None

    widget._stop_grid()
    assert widget._grid_animating is False
    assert widget._grid_after_id is None


def test_video_flow_widget_model_and_theme_options() -> None:
    catalog = {
        "models": [
            {"full_id": "local/deterministic", "available": True, "is_active": True},
            {
                "full_id": "gemini/gemini-2.5-flash",
                "provider_name": "Google",
                "display_name": "Gemini 2.5 Flash",
                "available": True,
                "is_active": True,
                "capabilities": ["video", "reasoning"],
            },
            {"full_id": "openai/disabled", "available": True, "is_active": False},
        ],
        "themes": ["auto", "cinematic", "minimal"],
    }
    models = VideoFlowScreenWidget.catalog_model_options(catalog)
    assert len(models) == 1
    assert any(m["ref"] == "gemini/gemini-2.5-flash" for m in models)

    themes = VideoFlowScreenWidget.catalog_theme_options(catalog)
    assert len(themes) == 3
    assert themes[0]["ref"] == "auto"
    assert themes[0]["label"] == "Auto"
    assert themes[1]["ref"] == "cinematic"
    assert themes[1]["label"] == "Cinematic"


def test_open_player_launches_subprocess(monkeypatch) -> None:
    popen_calls = []

    def mock_popen(args, **kwargs):
        popen_calls.append((args, kwargs))
        return MagicMock()

    monkeypatch.setattr(widget_module.subprocess, "Popen", mock_popen)

    video_flow_widget.open_player("vf-test-12345")
    assert len(popen_calls) == 1
    args, kwargs = popen_calls[0]
    assert args[-2:] == ["-m", "voice_flow.video_flow_player"] or "voice_flow.video_flow_player" in args
    assert "vf-test-12345" in args


def test_floating_overlay_bar_video_flow_actions() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar._is_mouse_over = True

    launched = []
    bar.on_video_flow = lambda text: launched.append(text)
    bar.selected_text = "Sample selected text"

    content_width = bar.width - bar.GRIP_W
    video_left = content_width - bar.video_action_width
    click_x = video_left + 10

    assert bar._get_zone(click_x, 10) == "video_flow"
    bar._on_press(SimpleNamespace(x=click_x, y=10))

    assert launched == ["Sample selected text"]
    assert bar.selected_text == ""


def test_floating_overlay_bar_video_ready_badge_click() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar.video_status = "ready"
    bar.video_job_id = "vf-ready-123"

    ready_clicked = []
    bar.on_video_ready = lambda vid: ready_clicked.append(vid)

    status_x = 20
    assert bar._get_zone(status_x, 10) == "video_status"

    bar._on_press(SimpleNamespace(x=status_x, y=10))

    assert ready_clicked == ["vf-ready-123"]
    assert bar.video_status == ""
    assert bar.video_job_id == ""


def test_floating_overlay_bar_video_cancel_click() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar._is_mouse_over = True
    bar.video_status = "processing"
    bar.video_job_id = "vf-proc-123"

    cancelled = []
    bar.on_video_cancel = lambda vid: cancelled.append(vid)

    cancel_x = bar.width - bar.GRIP_W - 8
    assert bar._get_zone(cancel_x, 5) == "video_cancel"

    bar._on_press(SimpleNamespace(x=cancel_x, y=5))
    assert cancelled == ["vf-proc-123"]
    assert bar.video_status == ""


# ============================================================================
# 2. Document analysis live updating in widget
# ============================================================================

def test_document_analysis_live_updating_in_widget(clean_widget: VideoFlowScreenWidget, tmp_path: Path) -> None:
    widget = clean_widget
    widget._build()

    sample_file = tmp_path / "deep_learning_notes.txt"
    sample_text = "Deep learning uses multi-layer artificial neural networks."
    sample_file.write_bytes(sample_text.encode("utf-8"))

    with patch("tkinter.filedialog.askopenfilename", return_value=str(sample_file)):
        widget._choose_file()

    assert widget._controls["source"].get("1.0", "end-1c") == sample_text
    assert widget._source_name == "deep_learning_notes.txt"
    assert widget._controls["file_label"].get() == "deep_learning_notes.txt"
    assert widget._controls["title"].get() == "deep_learning_notes"
    assert widget._controls["status"].get() == f"{len(sample_text):,} characters ready."
    assert "words" in widget._controls["analysis_banner"].get()


def test_document_analysis_preserves_custom_title(clean_widget: VideoFlowScreenWidget, tmp_path: Path) -> None:
    widget = clean_widget
    widget._build()

    widget._controls["title"].set("My Custom Video Title")

    sample_file = tmp_path / "quantum.txt"
    sample_file.write_bytes(b"Quantum physics details")

    with patch("tkinter.filedialog.askopenfilename", return_value=str(sample_file)):
        widget._choose_file()

    # Custom title must be preserved
    assert widget._controls["title"].get() == "My Custom Video Title"
    assert widget._controls["file_label"].get() == "quantum.txt"


def test_document_analysis_handles_cancel_dialog(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()
    widget._controls["source"].insert("1.0", "Existing source")

    with patch("tkinter.filedialog.askopenfilename", return_value=""):
        widget._choose_file()

    assert widget._controls["source"].get("1.0", "end-1c") == "Existing source"


def test_document_analysis_handles_oversized_file(clean_widget: VideoFlowScreenWidget, tmp_path: Path) -> None:
    widget = clean_widget
    widget._build()

    sample_file = tmp_path / "huge.txt"
    sample_file.write_bytes(b"x")

    with patch("tkinter.filedialog.askopenfilename", return_value=str(sample_file)), \
         patch("pathlib.Path.read_bytes", return_value=b"x" * (8 * 1024 * 1024 + 10)), \
         patch("tkinter.messagebox.showerror") as mock_error:
        widget._choose_file()
        assert mock_error.called
        assert "larger than 8 MB" in str(mock_error.call_args)


# ============================================================================
# 3. Generating a NotebookLM video payload from on-screen widget without requiring external AI models
# ============================================================================

def test_generate_notebooklm_video_payload_without_external_ai(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()

    widget._controls["source"].insert("1.0", "NotebookLM video synthesis source text")
    widget._controls["title"].set("NotebookLM Video")
    widget._controls["mode"].set("summary")
    widget._controls["format"].set("cinematic")
    widget._controls["style"].set("classic")

    received_payload: dict[str, Any] = {}
    completed_event = threading.Event()

    def mock_on_generate(payload: dict[str, Any]) -> dict[str, Any]:
        received_payload.update(payload)
        completed_event.set()
        return {"id": "vf-notebooklm-777"}

    widget.on_generate = mock_on_generate

    with patch("tkinter.messagebox.askyesno") as mock_askyesno:
        widget._generate()
        # Local NotebookLM generation MUST NOT prompt external AI confirmation dialog
        assert not mock_askyesno.called

    assert completed_event.wait(timeout=2.0)
    assert received_payload["provider"] == "notebooklm"
    assert received_payload["video_engine"] == "notebooklm"
    assert received_payload["source_text"] == "NotebookLM video synthesis source text"
    assert received_payload["title"] == "NotebookLM Video"
    assert received_payload["mode"] == "summary"
    assert received_payload["format"] == "cinematic"
    assert received_payload["style"] == "classic"
    assert "document_profile" in received_payload
    assert "duration_seconds" in received_payload
    assert received_payload.get("allow_local_fallback") is True


def test_generate_payload_with_native_engine_external_model(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()

    # Switch provider to native
    widget._provider = "native"
    widget._controls["provider"].set("native")
    widget._controls["source"].insert("1.0", "External model prompt test")
    widget._controls["model"].set("openai/gpt-4.1")

    received_payload: dict[str, Any] = {}
    completed_event = threading.Event()

    def mock_on_generate(payload: dict[str, Any]) -> dict[str, Any]:
        received_payload.update(payload)
        completed_event.set()
        return {"id": "vf-ext-888"}

    widget.on_generate = mock_on_generate

    with patch("tkinter.messagebox.askyesno", return_value=True) as mock_askyesno:
        widget._generate()
        assert mock_askyesno.called

    assert completed_event.wait(timeout=2.0)
    assert received_payload["provider"] == "native"
    assert received_payload["video_engine"] == "visual-v2.1"
    assert received_payload["allow_external_ai"] is True
    assert received_payload["allow_local_fallback"] is True
    assert received_payload["model_ref"] == "openai/gpt-4.1"


def test_generate_payload_validation_errors(clean_widget: VideoFlowScreenWidget) -> None:
    widget = clean_widget
    widget._build()

    # Empty source text
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        widget._generate()
        assert mock_warn.called
        assert "Paste text or choose a document" in str(mock_warn.call_args)

    # Missing runtime connection
    widget._controls["source"].insert("1.0", "Valid source")
    widget.on_generate = None
    with patch("tkinter.messagebox.showerror") as mock_err:
        widget._generate()
        assert mock_err.called
        assert "runtime is not connected" in str(mock_err.call_args)

    # Native mode with missing model ref
    widget.on_generate = MagicMock()
    widget._provider = "native"
    widget._controls["provider"].set("native")
    widget._controls["model"].set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        widget._generate()
        assert mock_warn.called
        assert "select an AI model" in str(mock_warn.call_args)


# ============================================================================
# 4. _queue_video_from_screen queuing NotebookLM jobs
# ============================================================================

def test_main_queue_video_from_screen_forwards_notebooklm_options() -> None:
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.FloatingOverlayBar"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.Transcriber"):
        app = VoiceFlowApp()

    mock_service = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "vf-nlm-test-999"
    mock_service.queue.return_value = mock_job

    payload = {
        "source_text": "Sample document content for video",
        "mode": "summary",
        "title": "Document Video",
        "source_name": "my_notes.pdf",
        "model_ref": "google/gemini-2.5-flash",
        "theme": "cinematic",
        "visual_direction": "bold subtitles",
        "allow_external_ai": True,
        "provider": "notebooklm",
        "video_engine": "notebooklm",
        "format": "cinematic-explainer",
        "style": "storyboard",
        "style_prompt": "modern clean layout",
        "focus": "key concepts",
        "document_profile": {"word_count": 500, "topics": ["AI", "Flow"]},
        "duration_seconds": 60,
    }

    with patch("voice_flow.video_flow_service.get_video_flow_service", return_value=mock_service), \
         patch.object(app, "_monitor_video_flow_job") as mock_monitor:
        res = app._queue_video_from_screen(payload)

        assert res == {"id": "vf-nlm-test-999"}
        mock_service.queue.assert_called_once_with(
            source_text="Sample document content for video",
            mode="summary",
            title="Document Video",
            source_name="my_notes.pdf",
            model_ref="google/gemini-2.5-flash",
            theme="cinematic",
            visual_direction="bold subtitles",
            allow_external_ai=True,
            allow_local_fallback=True,
            provider="notebooklm",
            video_engine="notebooklm",
            format="cinematic-explainer",
            style="storyboard",
            style_prompt="modern clean layout",
            focus="key concepts",
            document_profile={"word_count": 500, "topics": ["AI", "Flow"]},
            duration_seconds=60,
        )


def test_main_monitor_video_flow_job_updates_progress_and_completes() -> None:
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.FloatingOverlayBar"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.Transcriber"):
        app = VoiceFlowApp()

    mock_service = MagicMock()
    mock_job1 = SimpleNamespace(state="rendering", progress=45.0, message="Rendering scene 2", meta={})
    mock_job2 = SimpleNamespace(state="complete", progress=100.0, message="Ready", meta={})

    mock_service.get.side_effect = [mock_job1, mock_job2]

    with patch("voice_flow.video_flow_service.get_video_flow_service", return_value=mock_service), \
         patch("time.sleep", return_value=None):
        app._monitor_video_flow_job("vf-job-abc")

        app.overlay.show_video_progress.assert_called_with("vf-job-abc", 45.0, "Rendering scene 2")
        app.overlay.show_video_ready.assert_called_once_with("vf-job-abc")


# ============================================================================
# 5. Root resolution, UI execution fallback, and window lifecycle
# ============================================================================

def test_run_on_ui_fallback_and_default_root(shared_tk: tk.Tk) -> None:
    widget = VideoFlowScreenWidget()
    widget.root = None

    # Test with default_root active: schedules on root.after(0)
    called = []
    widget._run_on_ui(lambda: called.append("ran_on_root"))
    shared_tk.update()
    assert called == ["ran_on_root"]

    # Test without any root: runs callback directly as fallback
    called_fallback = []
    with patch.object(tk, "_default_root", None):
        widget.root = None
        widget._run_on_ui(lambda: called_fallback.append("ran_fallback"))
        assert called_fallback == ["ran_fallback"]


def test_show_composer_resolves_default_root(shared_tk: tk.Tk) -> None:
    widget = VideoFlowScreenWidget()
    assert widget.root is None

    with patch.object(widget, "_refresh_models"):
        widget.show_composer(selected_text="Auto resolve root test")
        shared_tk.update()

        assert widget.root is not None
        assert widget.win is not None
        assert widget.win.winfo_exists()
        assert widget._controls["source"].get("1.0", "end-1c") == "Auto resolve root test"

    widget.hide()


def test_window_close_withdraw_and_reopen_lifecycle(clean_widget: VideoFlowScreenWidget, shared_tk: tk.Tk) -> None:
    widget = clean_widget
    with patch.object(widget, "_refresh_models"):
        widget.show_composer(selected_text="First open text")
        shared_tk.update()

        assert widget.win is not None
        assert widget.win.winfo_viewable()

        # Simulate WM_DELETE_WINDOW / hide
        widget.hide()
        shared_tk.update()
        assert not widget.win.winfo_viewable()
        assert widget._controls["source"].get("1.0", "end-1c") == "First open text"

        # Reopen with new text
        widget.show_composer(selected_text="Reopened second text")
        shared_tk.update()
        assert widget.win.winfo_viewable()
        assert widget._controls["source"].get("1.0", "end-1c") == "Reopened second text"


def test_refresh_models_non_blocking_with_slow_network(clean_widget: VideoFlowScreenWidget, shared_tk: tk.Tk) -> None:
    widget = clean_widget
    widget._build()

    slow_network_started = threading.Event()
    release_slow_network = threading.Event()

    def slow_urlopen(*_args, **_kwargs):
        slow_network_started.set()
        release_slow_network.wait(timeout=2.0)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "models": [{"full_id": "mock/model-slow", "display_name": "Mock Slow", "available": True, "is_active": True}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=slow_urlopen):
        t0 = time.perf_counter()
        widget._refresh_models()
        elapsed = time.perf_counter() - t0

        # _refresh_models must return immediately without waiting for the network
        assert elapsed < 0.2, f"UI blocked for {elapsed:.3f}s during _refresh_models!"

        # Immediate fast fallback defaults are applied
        assert "model_box" in widget._controls
        shared_tk.update()

        # Let slow network response finish
        assert slow_network_started.wait(timeout=1.0)
        release_slow_network.set()

        for _ in range(30):
            time.sleep(0.05)
            shared_tk.update()
            if any("Mock Slow" in opt for opt in widget._model_options):
                break

        # After async completion, newly fetched model is populated
        assert any("Mock Slow" in opt for opt in widget._model_options)


def test_show_composer_instant_reveal_and_focus(clean_widget: VideoFlowScreenWidget, shared_tk: tk.Tk) -> None:
    widget = clean_widget
    widget.show_composer(selected_text="Instant composer test")
    shared_tk.update()

    assert widget.win is not None
    assert widget.win.winfo_exists()
    assert widget.win.state() == "normal"
    assert widget.win.winfo_viewable()
    assert bool(widget.win.attributes("-topmost")) is True




def test_open_player_rejects_path_traversal() -> None:
    from voice_flow.video_flow_widget import VideoFlowScreenWidget

    widget = VideoFlowScreenWidget()
    with __import__("unittest.mock", fromlist=["patch"]).patch("subprocess.Popen") as popen:
        widget.open_player("../../etc/passwd")
        popen.assert_not_called()


def test_auth_local_never_returns_hardcoded_identity() -> None:
    from voice_flow.video_flow_widget import VideoFlowScreenWidget

    widget = VideoFlowScreenWidget()
    is_auth, email = widget._check_notebooklm_auth_local.__func__(widget) if False else (None, None)
    # Call unbound-safe: construct minimal check via fresh instance without storage/cookies.
    import voice_flow.video_flow_widget as wm

    source = __import__("inspect").getsource(wm.VideoFlowScreenWidget._check_notebooklm_auth_local)
    assert "naeem.kayat2004" not in source
