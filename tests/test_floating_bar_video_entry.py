from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
    video_x = bar.ready_actions_width - bar.video_action_width + 1
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

    bar.selected_text = "Selected source text"
    bar._is_mouse_over = True
    assert bar._get_zone(1) == "speak"
    assert bar._get_zone(video_x) == "video_flow"
    _click(bar, video_x)
    assert launched_with == ["", "Selected source text"]

    main = (ROOT / "src" / "voice_flow" / "main.py").read_text(encoding="utf-8")
    assert 'self.overlay.on_video_flow = lambda text: self._process_video_flow_pipeline("summary", text)' in main