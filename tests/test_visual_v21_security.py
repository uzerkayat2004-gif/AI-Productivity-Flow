from __future__ import annotations

from copy import deepcopy
import runpy
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.visual_program_v21 import VisualProgramV21Error, parse_video_visual_program_v21


BENCHMARK = runpy.run_path(str(Path(__file__).parents[1] / "video-flow-v2.1" / "benchmark_v21.py"))


def _payload() -> tuple[dict, dict]:
    record = BENCHMARK["fixture_records"]()[0]
    return deepcopy(record["program"]), record["storyboard"]


@pytest.mark.parametrize(
    ("mutator",),
    [
        (lambda payload: payload["design_bible"].update({"direction": "<script>alert(1)</script>"}),),
        (lambda payload: payload["scenes"][0].update({"html": "<svg><script>alert(1)</script></svg>"}),),
        (lambda payload: payload["scenes"][0]["subjects"][0].update({"semantic_name": "javascript:alert(1)"}),),
        (lambda payload: payload["scenes"][0]["subjects"][0].update({"semantic_name": "C:\\Users\\secret\\file"}),),
        (lambda payload: payload["scenes"][0]["events"][0].update({"parameters": {"command": "powershell -enc SECRET"}}),),
        (lambda payload: payload["scenes"][0]["events"][0].update({"parameters": {"url": "file://C:/secret"}}),),
        (lambda payload: payload["design_bible"]["palette"].update({"accent_family": "#ff0000"}),),
        (lambda payload: payload["scenes"][0].update({"renderer_config": {"three": {"source": "function(){}"}}}),),
    ],
)
def test_untrusted_visual_program_payloads_are_rejected_before_compilation(mutator) -> None:
    payload, storyboard = _payload()
    mutator(payload)
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload, storyboard=storyboard)


def test_unsafe_event_path_and_non_finite_geometry_are_rejected() -> None:
    payload, storyboard = _payload()
    payload["scenes"][0]["events"] = [{"id": "bad", "type": "PATH_MOTION", "subject": "tree", "path": [[0, 0], [float("nan"), 1]]}]
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload, storyboard=storyboard)


def test_raw_markup_code_and_renderer_fields_are_not_in_the_active_contract() -> None:
    payload, storyboard = _payload()
    for field, value in (("svg", "<svg/>"), ("css", "body{color:red}"), ("three", {"objects": []}), ("renderer", {"source": "javascript"})):
        candidate = deepcopy(payload)
        candidate["scenes"][0][field] = value
        with pytest.raises(VisualProgramV21Error):
            parse_video_visual_program_v21(candidate, storyboard=storyboard)


def test_fixture_benchmark_never_calls_external_ai_or_leaks_credentials() -> None:
    results = BENCHMARK["run_benchmarks"]()
    assert all(item["external_ai_called"] is False for item in results)
    serialized = str(results).casefold()
    assert "api_key" not in serialized
    assert "secret" not in serialized
    assert "password" not in serialized


@pytest.mark.parametrize("payload_kind", [
    "position",
    "rotation",
    "scale",
    "path_array",
    "camera_vector",
    "transform_vector",
    "renderer_config",
])
def test_coordinate_and_renderer_owned_payloads_are_rejected(payload_kind: str) -> None:
    payload, storyboard = _payload()
    scene = payload["scenes"][0]
    if payload_kind in {"position", "rotation", "scale"}:
        scene["initial_state"]["objects"]["tree"][payload_kind] = [0, 0, 0]
    elif payload_kind == "path_array":
        scene["events"] = [{"id": "bad_path", "type": "PATH_MOTION", "subject": "tree", "path": [[0, 0], [1, 1]]}]
    elif payload_kind == "camera_vector":
        scene["events"].append({"id": "bad_camera", "type": "CAMERA", "mode": "orbit", "target": "tree", "parameters": {"camera": {"position": [0, 0, 4]}}})
    elif payload_kind == "transform_vector":
        scene["events"][0]["parameters"] = {"transform": {"position": [[0, 0, 0], [1, 1, 1]]}}
    else:
        scene["renderer_config"] = {"position": [0, 0, 0], "three": {"camera": {"position": [0, 0, 4]}}}
    with pytest.raises(VisualProgramV21Error):
        parse_video_visual_program_v21(payload, storyboard=storyboard)

