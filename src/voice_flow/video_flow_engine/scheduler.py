"""Narration alignment and hybrid render scheduling for agent-authored scenes."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


FPS = 24


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _frame(value: Any, maximum: int, default: int = 0) -> int:
    return max(0, min(maximum, int(round(_number(value, default)))))


def _stable_id(value: Any, prefix: str = "scene") -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:12]}"


def _word_frame(timing: Mapping[str, Any], key: str, fps: int) -> int:
    if key in timing:
        return max(0, int(_number(timing.get(key))))
    seconds_key = "offsetSeconds" if key == "startFrame" else "durationSeconds"
    return max(0, int(round(_number(timing.get(seconds_key)) * fps)))


def synchronize_scene(
    scene: Mapping[str, Any],
    *,
    duration_seconds: float | None = None,
    fps: int = FPS,
) -> dict[str, Any]:
    """Attach TTS word boundaries to authored anchors and schedule moving frames.

    Authored node hierarchy and animation expressions are never replaced. Only
    timing metadata is normalized after the real voice duration becomes known.
    """
    result = copy.deepcopy(dict(scene))
    fps = max(1, int(result.get("fps") or fps))
    previous_frames = max(1, int(result.get("durationInFrames") or 1))
    previous_duration = max(0.01, _number(result.get("durationSeconds"), previous_frames / fps))
    actual_duration = max(2.5, _number(duration_seconds, previous_duration))
    duration_frames = max(1, int(round(actual_duration * fps)))
    scale = duration_frames / previous_frames
    result["fps"] = fps
    result["durationSeconds"] = actual_duration
    result["durationInFrames"] = duration_frames
    result.setdefault("id", _stable_id(result))

    authored_anchors = [dict(item) for item in result.get("anchors") or [] if isinstance(item, Mapping)]
    anchor_ids = {str(item.get("id") or "") for item in authored_anchors}
    timings: list[dict[str, Any]] = []
    for index, raw in enumerate(result.get("wordTimings") or []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        start = _word_frame(item, "startFrame", fps)
        word_duration = _word_frame(item, "endFrame", fps)
        end = int(item.get("endFrame") or (start + max(1, word_duration)))
        anchor_id = str(item.get("anchorId") or f"word-{index}")
        item.update({"startFrame": start, "endFrame": min(duration_frames - 1, end), "anchorId": anchor_id})
        timings.append(item)
        if anchor_id not in anchor_ids:
            authored_anchors.append(
                {
                    "id": anchor_id,
                    "start": start,
                    "end": min(duration_frames - 1, end),
                    "tags": ["narration", str(item.get("text") or "")],
                }
            )
            anchor_ids.add(anchor_id)
    result["wordTimings"] = timings

    for anchor in authored_anchors:
        if isinstance(anchor.get("start"), (int, float)):
            anchor["start"] = _frame(_number(anchor["start"]) * scale, duration_frames - 1)
        if isinstance(anchor.get("end"), (int, float)):
            anchor["end"] = _frame(_number(anchor["end"]) * scale, duration_frames - 1)
    result["anchors"] = authored_anchors

    motion_plan = dict(result.get("motionPlan") or {})
    raw_windows = [
        dict(item)
        for item in motion_plan.get("renderWindows") or []
        if isinstance(item, Mapping)
    ]
    windows: list[dict[str, Any]] = []
    for raw in raw_windows:
        if "startRatio" in raw:
            start = _frame(_number(raw.get("startRatio")) * duration_frames, duration_frames - 1)
        else:
            start = _frame(_number(raw.get("startFrame")) * scale, duration_frames - 1)
        if "endRatio" in raw:
            end = _frame(_number(raw.get("endRatio")) * duration_frames, duration_frames - 1)
        else:
            end = _frame(_number(raw.get("endFrame"), start + fps) * scale, duration_frames - 1)
        if end >= start:
            windows.append(
                {
                    **raw,
                    "startFrame": start,
                    "endFrame": end,
                    "startRatio": round(start / duration_frames, 6),
                    "endRatio": round(end / duration_frames, 6),
                    "mode": str(raw.get("mode") or "motion-island"),
                }
            )

    render_class = str(result.get("renderClass") or "motion-island")
    if render_class == "static":
        windows = [{"startFrame": 0, "endFrame": 0, "startRatio": 0.0, "endRatio": 0.0, "mode": "static"}]
    elif not windows:
        # Enter and semantic changes are normally concentrated in the first
        # third; holds are assembled by FFmpeg instead of re-rendered.
        end = min(duration_frames - 1, max(18, int(duration_frames * 0.34)))
        windows = [{"startFrame": 0, "endFrame": end, "startRatio": 0.0, "endRatio": round(end / duration_frames, 6), "mode": "motion-island"}]
    motion_plan["renderWindows"] = _merge_windows(windows, duration_frames)
    transition = dict(motion_plan.get("transition") or result.get("transition") or {})
    transition.setdefault("type", "fade")
    transition.setdefault("kind", transition["type"])
    transition.setdefault("durationInFrames", 6)
    transition.setdefault("durationSeconds", transition["durationInFrames"] / fps)
    motion_plan["transition"] = transition
    result["transition"] = transition
    result["motionPlan"] = motion_plan
    return result


def _merge_windows(windows: list[dict[str, Any]], duration_frames: int) -> list[dict[str, Any]]:
    ordered = sorted(windows, key=lambda item: (int(item["startFrame"]), int(item["endFrame"])))
    merged: list[dict[str, Any]] = []
    for window in ordered:
        if merged and int(window["startFrame"]) <= int(merged[-1]["endFrame"]) + 2:
            merged[-1]["endFrame"] = max(int(merged[-1]["endFrame"]), int(window["endFrame"]))
            merged[-1]["endRatio"] = round(int(merged[-1]["endFrame"]) / duration_frames, 6)
        else:
            merged.append(window)
    return merged


def normalize_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(manifest))
    fps = max(1, int(result.get("fps") or FPS))
    result.update({"engineVersion": "agentic-visual.v1", "fps": fps, "width": int(result.get("width") or 1920), "height": int(result.get("height") or 1080)})
    result["scenes"] = [synchronize_scene(scene, fps=fps) for scene in result.get("scenes") or [] if isinstance(scene, Mapping)]
    return result
