from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import Mock

from voice_flow.video_flow import VideoFlowService


def _service() -> VideoFlowService:
    service = object.__new__(VideoFlowService)
    service.store = Mock()
    return service


def test_render_prefers_semantic_keyframe_fast_path(tmp_path: Path) -> None:
    service = _service()
    service._render_fast = Mock()
    service._render_full = Mock()

    service._render(
        tmp_path / "manifest.json",
        tmp_path / "public",
        tmp_path / "output.mp4",
        video_id="video-1",
        cancel_event=threading.Event(),
    )

    service._render_fast.assert_called_once()
    service._render_full.assert_not_called()


def test_render_falls_back_when_fast_renderer_is_unavailable(tmp_path: Path) -> None:
    service = _service()
    service._render_fast = Mock(side_effect=RuntimeError("fast renderer unavailable"))
    service._render_full = Mock()

    service._render(
        tmp_path / "manifest.json",
        tmp_path / "public",
        tmp_path / "output.mp4",
        video_id="video-2",
        cancel_event=threading.Event(),
    )

    service._render_full.assert_called_once()
    service.store.update_video.assert_called_once_with(
        "video-2",
        progress=72,
        stage="Using compatibility renderer",
    )


def test_vector_renderer_uses_parallel_semantic_motion_frames() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "video_flow_renderer"
        / "scripts"
        / "render-vector-motion.py"
    ).read_text(encoding="utf-8")

    assert "ThreadPoolExecutor" in script
    assert "render_scene" in script
    assert "motionPlan" in script
    assert "renderWindows" in script
    assert "packed-%08d.jpg" in script
    assert "packed-motion.mp4" in script
    assert '"libx264"' in script
    assert '"procedural-vector-v1"' in script
    assert '"packedFps"' in script
    assert '"motionSampleStep"' in script
    assert 'stable_seed' in script
    assert 'import zlib' in script
    assert 'hash(' not in script

def test_fast_assembler_preserves_motion_islands_without_generic_zoompan() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "voice_flow"
        / "video_flow.py"
    ).read_text(encoding="utf-8")

    assert "render-vector-motion.py" in source
    assert "zoompan" not in source
    assert "motionPlan" in source
