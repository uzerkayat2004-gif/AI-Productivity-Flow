from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from voice_flow.overlay import FloatingOverlayBar


ROOT = Path(__file__).resolve().parents[1]


def _click(bar: FloatingOverlayBar, x: int) -> None:
    bar._is_mouse_over = True
    bar._on_press(SimpleNamespace(x=x, y=0))


def test_compact_video_flow_action_launches_with_or_without_selection() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    assert bar._get_zone(1) == "speak"
    bar.width = bar.ready_actions_width
    bar._is_mouse_over = True
    video_x = bar.ready_actions_width - bar.GRIP_W - bar.settings_action_width - 10
    started: list[bool] = []
    launched_with: list[str] = []
    bar.on_start_click = lambda: started.append(True)
    bar.on_video_flow = launched_with.append

    assert bar._get_zone(1) == "speak"
    assert bar._get_zone(video_x) == "video_flow"
    _click(bar, 1)
    _click(bar, video_x)
    assert started == [True]
    assert launched_with == [""]

def test_selection_triggers_instant_video_button_without_hover() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar._is_mouse_over = False
    assert bar._selection_expanded is False

    # Default rest mode is idle width
    target_w, target_h = bar._target_size()
    assert target_w == bar.idle_width

    # When user selects text:
    bar.set_selected_text("Instant video text")
    assert bar.selected_text == "Instant video text"
    assert bar._selection_expanded is True

    # Bar targets expanded size even without mouse hover:
    target_w, target_h = bar._target_size()
    assert target_w == bar.ready_actions_width
    bar.width = target_w

    # Zone calculation allows video_flow click directly without hover
    video_x = bar.ready_actions_width - bar.GRIP_W - bar.settings_action_width - 10
    assert bar._get_zone(video_x) == "video_flow"

    # Clicking video zone triggers video flow with selected text and collapses selection
    launched: list[str] = []
    bar.on_video_flow = launched.append
    bar._on_press(SimpleNamespace(x=video_x, y=0))

    assert launched == ["Instant video text"]
    assert bar.selected_text == ""
    assert bar._selection_expanded is False


def test_overlay_contains_point_accuracy() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.win = MagicMock()
    bar.win.winfo_rootx.return_value = 100
    bar.win.winfo_rooty.return_value = 200
    bar.width = 48
    bar.height = 10
    bar._last_drawn_width = 48
    bar._is_mouse_over = False
    bar._selection_expanded = False

    # Inside idle bar bounds (with 4px margin)
    assert bar.contains_point(100, 200) is True
    assert bar.contains_point(96, 196) is True  # -4 margin
    assert bar.contains_point(148 + 4, 210 + 4) is True  # +4 margin
    assert bar.contains_point(90, 200) is False  # Outside left
    assert bar.contains_point(200, 200) is False  # Outside right in rest mode

    # When selection expanded, area accurately extends to ready_actions_width & hover_height
    bar._selection_expanded = True
    assert bar.contains_point(100 + bar.ready_actions_width - 10, 200 + bar.hover_height - 2) is True
    assert bar.contains_point(100 + bar.ready_actions_width + 10, 200) is False

    # When hover expanded
    bar._selection_expanded = False
    bar._is_mouse_over = True
    assert bar.contains_point(100 + bar.ready_actions_width - 10, 200 + bar.hover_height - 2) is True


def test_on_press_video_flow_safe_with_none_or_empty_selection() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    video_x = bar.ready_actions_width - bar.GRIP_W - bar.settings_action_width - 10

    launched: list[str] = []
    bar.on_video_flow = launched.append

    # None selected text
    bar.selected_text = None  # type: ignore[assignment]
    _click(bar, video_x)
    assert launched == [""]

    # Empty string selected text
    launched.clear()
    bar.selected_text = ""
    _click(bar, video_x)
    assert launched == [""]


def test_process_video_flow_pipeline_opens_composer_without_text() -> None:
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.FloatingOverlayBar"), \
         patch("voice_flow.main.storage") as mock_storage, \
         patch("voice_flow.main.video_flow_widget") as mock_widget:

        mock_storage.get_setting.return_value = True
        mock_storage.get_recent_history.return_value = []

        app = VoiceFlowApp()
        app.overlay = MagicMock()
        with patch.object(app, "_capture_selected_text_for_video", return_value=""):
            # Trigger video flow pipeline with no text override and no captured selection
            app._process_video_flow_pipeline("summary", text_override="")

            # Must NOT show error "Select text to make a video"
            app.overlay.show_error.assert_not_called()
            # Must STILL open composer with empty string
            mock_widget.show_composer.assert_called_once_with("", "summary", anchor_bar=app.overlay)

            mock_widget.show_composer.reset_mock()
            app._process_video_flow_pipeline("full", text_override=None)
            app.overlay.show_error.assert_not_called()
            mock_widget.show_composer.assert_called_once_with("", "full", anchor_bar=app.overlay)


def test_video_flow_hitbox_zero_misrouting_even_when_mouse_over_desynced() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar._is_mouse_over = False
    bar._selection_expanded = False

    video_x = bar.ready_actions_width - bar.GRIP_W - bar.settings_action_width - 10
    speak_calls: list[bool] = []
    video_calls: list[str] = []
    bar.on_start = lambda: speak_calls.append(True)
    bar.on_start_click = lambda: speak_calls.append(True)
    bar.on_video_flow = video_calls.append

    # Must return video_flow even with _is_mouse_over = False (desynced)
    assert bar._get_zone(video_x) == "video_flow"

    # Clicking must trigger on_video_flow and NEVER misroute to speak
    bar._on_press(SimpleNamespace(x=video_x, y=0))
    assert video_calls == [""]
    assert speak_calls == []


def test_video_flow_hitbox_reliable_during_transition_widths() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar._is_mouse_over = True

    # 1 pixel below ready_actions_width (e.g. 247 during animation or DPI scaling)
    bar.width = bar.ready_actions_width - 1
    content_width = bar.width - bar.GRIP_W
    settings_left = content_width - bar.settings_action_width
    video_left = settings_left - bar.video_action_width
    assert bar._get_zone(video_left) == "video_flow"
    assert bar._get_zone(settings_left - 1) == "video_flow"
    assert bar._get_zone(content_width - 1) == "settings"

    # Transition width 200
    bar.width = 200
    content_width = bar.width - bar.GRIP_W
    settings_left = content_width - bar.settings_action_width
    video_left = settings_left - bar.video_action_width
    assert bar._get_zone(video_left) == "video_flow"
    assert bar._get_zone(video_left - 4) == "video_flow"


def test_video_flow_hitbox_padding_and_grip_boundaries() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    grip_left = bar.ready_actions_width - bar.GRIP_W
    content_width = grip_left
    settings_left = content_width - bar.settings_action_width
    video_left = settings_left - bar.video_action_width

    # Generous padding: video_left - 4 is in video_flow zone
    assert bar._get_zone(video_left - 4) == "video_flow"
    # video_left - 5 is in speak zone
    assert bar._get_zone(video_left - 5) == "speak"

    # Right edge padding up to settings and grip boundary
    assert bar._get_zone(settings_left - 1) == "video_flow"
    assert bar._get_zone(settings_left) == "settings"
    assert bar._get_zone(grip_left - 1) == "settings"
    assert bar._get_zone(grip_left) == "grip"


def test_video_flow_press_preserves_mouse_over_state() -> None:
    bar = FloatingOverlayBar()
    bar.state = "READY"
    bar.width = bar.ready_actions_width
    bar._is_mouse_over = True

    video_x = bar.ready_actions_width - bar.video_action_width + 10
    bar.on_video_flow = MagicMock()

    bar._on_press(SimpleNamespace(x=video_x, y=0))
    bar.on_video_flow.assert_called_once_with("")
    # Mouse over state must NOT be desynced on video_flow click
    assert bar._is_mouse_over is True


def test_process_video_flow_pipeline_with_text_override_bypasses_capture() -> None:
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.FloatingOverlayBar"), \
         patch("voice_flow.main.storage") as mock_storage, \
         patch("voice_flow.main.video_flow_widget") as mock_widget:

        mock_storage.get_setting.return_value = True
        mock_storage.get_recent_history.return_value = []

        app = VoiceFlowApp()
        app.overlay = MagicMock()
        with patch.object(app, "_capture_selected_text_for_video") as mock_capture:
            app._process_video_flow_pipeline("summary", text_override="Highlighted tutorial text")

            # Must NOT call capture when text_override is provided
            mock_capture.assert_not_called()
            mock_widget.show_composer.assert_called_once_with("Highlighted tutorial text", "summary", anchor_bar=app.overlay)


def test_queue_video_from_screen_enforces_allow_local_fallback() -> None:
    from voice_flow.main import VoiceFlowApp

    with patch("voice_flow.main.AudioRecorder"), \
         patch("voice_flow.main.InputTriggerListener"), \
         patch("voice_flow.main.FloatingOverlayBar"), \
         patch("voice_flow.main.storage") as mock_storage:

        mock_storage.get_setting.return_value = True
        mock_storage.get_recent_history.return_value = []

        app = VoiceFlowApp()
        app.overlay = MagicMock()

        mock_service = MagicMock()
        mock_job = MagicMock()
        mock_job.job_id = "vf-fallback-test-123"
        mock_service.queue.return_value = mock_job

        payload = {
            "source_text": "Sample text for video fallback test",
            "mode": "summary",
            "title": "Fallback Video Test",
            "provider": "notebooklm",
        }

        with patch("voice_flow.video_flow_service.get_video_flow_service", return_value=mock_service), \
             patch.object(app, "_monitor_video_flow_job"):
            result = app._queue_video_from_screen(payload)

            assert result == {"id": "vf-fallback-test-123"}
            assert payload.get("allow_local_fallback") is True

            _, kwargs = mock_service.queue.call_args
            assert kwargs.get("allow_local_fallback") is True
            assert kwargs.get("source_text") == "Sample text for video fallback test"
            assert kwargs.get("provider") == "notebooklm"
