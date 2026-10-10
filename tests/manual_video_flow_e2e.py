"""Controlled end-to-end readiness probe for the production Video Flow service.

This is intentionally a manual diagnostic, not part of the default test suite.
It uses a fresh store, a harmless synthetic source, the active configured model,
Edge TTS, and the same render path as the desktop application.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from voice_flow.video_flow import VideoFlowService, VideoFlowStore


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "scratch" / f"video-flow-readiness-{datetime.now():%Y%m%d-%H%M%S}"


def walk_nodes(node: Any) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    result = [node]
    for child in node.get("children") or []:
        result.extend(walk_nodes(child))
    return result


def main() -> int:
    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    store = VideoFlowStore(
        db_path=str(RUN_ROOT / "readiness.db"),
        output_root=RUN_ROOT / "videos",
    )
    service = VideoFlowService(store)
    model_ref = sys.argv[1] if len(sys.argv) > 1 else str(service.catalog().get("active_model") or "")
    if not model_ref or model_ref == "local/deterministic":
        raise RuntimeError("Select a connected AI model before running the Video Flow readiness probe.")
    job = service.queue(
        source_text=(
            "A liquid rocket engine turbopump raises propellant pressure before combustion. "
            "Fuel and oxidizer enter through separate inlets and must never mix inside the pump. "
            "A turbine on the shared shaft spins two pump stages; the rotating impellers add energy "
            "to the fluids while stationary diffusers convert velocity into pressure. The high-pressure "
            "propellants then travel through separate feed lines toward the injector and combustion chamber. "
            "A useful explanation should reveal the shaft, turbine, impellers, diffusers, inlets, and outlets "
            "as one spatial assembly and show the two isolated flow paths."
        ),
        mode="summary",
        title="How a Rocket Turbopump Works — 3D Cutaway",
        source_name="synthetic-rocket-turbopump.txt",
        model_ref=model_ref,
        theme="auto",
        visual_direction=(
            "Author a clean technical 3D cutaway, not a dashboard, card layout, notebook, or cartoon. "
            "Use depth, an exploded assembly, a restrained camera orbit, and two clearly separated colored "
            "propellant paths. At least one explanatory scene must use render_class webgl-3d with one or more "
            "three nodes because spatial depth and assembly are essential to this topic. Keep labels sparse."
        ),
        allow_external_ai=True,
    )
    video_id = str(job["id"])
    print(json.dumps({"event": "queued", "video_id": video_id, "run_root": str(RUN_ROOT)}), flush=True)

    deadline = time.monotonic() + 15 * 60
    last_stage = ""
    row: dict[str, Any] = job
    while time.monotonic() < deadline:
        row = store.get_video(video_id) or {}
        stage = f"{row.get('status')}:{row.get('progress')}:{row.get('stage')}"
        if stage != last_stage:
            print(json.dumps({"event": "progress", "state": stage}), flush=True)
            last_stage = stage
        if row.get("status") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1)
    else:
        service.cancel(video_id)
        row = store.get_video(video_id) or row
        row["error"] = "Diagnostic timed out after 15 minutes."

    summary: dict[str, Any] = {
        "video_id": video_id,
        "status": row.get("status"),
        "error": row.get("error"),
        "output_path": row.get("output_path"),
        "duration_sec": row.get("duration_sec"),
        "run_root": str(RUN_ROOT),
    }
    manifest_path = Path(str(row.get("manifest_path") or ""))
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes = list(manifest.get("scenes") or [])
        nodes = [node for scene in scenes for node in walk_nodes(scene.get("root"))]
        summary.update(
            {
                "engine_version": manifest.get("engineVersion"),
                "planning_model": manifest.get("planningModel"),
                "scene_count": len(scenes),
                "render_classes": [scene.get("renderClass") for scene in scenes],
                "root_types": [str((scene.get("root") or {}).get("type") or "") for scene in scenes],
                "three_node_count": sum(1 for node in nodes if node.get("type") == "three"),
                "word_timing_count": sum(len(scene.get("wordTimings") or []) for scene in scenes),
                "audio_scene_count": sum(1 for scene in scenes if scene.get("audioFile")),
                "qa_passed": bool((manifest.get("qaReport") or {}).get("passed")),
                "diversity_accepted": bool((manifest.get("diversityReport") or {}).get("accepted", True)),
                "fingerprint_signature": (manifest.get("creativeFingerprint") or {}).get("signature"),
                "genre": (manifest.get("creativeTreatment") or {}).get("genre"),
                "visual_world": (manifest.get("creativeTreatment") or {}).get("visual_world"),
            }
        )
    output_path = Path(str(row.get("output_path") or ""))
    summary["output_exists"] = output_path.is_file()
    summary["output_bytes"] = output_path.stat().st_size if output_path.is_file() else 0
    report_path = RUN_ROOT / "readiness-report.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"event": "result", **summary}, ensure_ascii=False), flush=True)

    required = (
        summary.get("status") == "completed"
        and summary.get("engine_version") == "agentic-visual.v1"
        and int(summary.get("three_node_count") or 0) > 0
        and int(summary.get("word_timing_count") or 0) > 0
        and summary.get("output_exists")
    )
    return 0 if required else 1


if __name__ == "__main__":
    sys.exit(main())
