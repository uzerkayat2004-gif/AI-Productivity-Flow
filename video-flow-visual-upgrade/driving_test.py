"""Required mission test: autonomous-driving topic through the real backend.

Posts /api/video-flow/generate, polls status, samples process resource usage,
and prints a final report (job id, timings, peak resources, output path).
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8991"
TEXT = (
    "We're moving toward end-to-end neural networks for autonomous driving. "
    "For years, self-driving stacks were modular: camera perception detected objects, "
    "a planner chose a route, and a controller steered, braking and accelerating. "
    "Each module was engineered separately and errors compounded between them. "
    "Now a single neural network takes raw camera pixels and directly outputs driving "
    "actions: steering angle, acceleration, and braking. It learns from millions of "
    "miles of human driving, so perception, planning, and control are trained together "
    "rather than stitched by hand. The result is fewer hand-tuned rules, simpler "
    "software, and behavior that keeps improving with more data."
)
OUT = Path(__file__).parent / "driving-test-result.json"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def sample_processes() -> dict:
    """Count browsers and sum working sets of pipeline processes via tasklist."""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV"], capture_output=True, text=True, timeout=20
        ).stdout.lower()
    except Exception:
        return {}
    counts = {}
    for key in ("chrome.exe", "node.exe", "python.exe", "pythonw.exe", "ffmpeg.exe"):
        counts[key] = out.count(f'"{key}"')
    return counts


def main() -> None:
    started = time.time()
    result = post(
        "/api/video-flow/generate",
        {
            "source_text": TEXT,
            "mode": "lesson",
            "title": "End-to-end neural networks for autonomous driving",
            "allow_external_ai": True,
        },
    )
    job_id = result.get("job_id") or ""
    print(f"JOB: {job_id}")
    if not job_id:
        print(json.dumps(result, indent=2))
        raise SystemExit(1)

    peak = {"chrome": 0, "node": 0, "python": 0, "ffmpeg": 0}
    last_line = ""
    status: dict = {}
    while time.time() - started < 900:
        time.sleep(10)
        try:
            with urllib.request.urlopen(
                BASE + "/api/video-flow/history", timeout=10
            ) as response:
                history = json.loads(response.read().decode("utf-8"))
            video = next(
                (v for v in (history.get("videos") or []) if v.get("id") == job_id), {}
            )
        except Exception:
            video = {}
        line = f"{video.get('progress')}% {video.get('stage') or video.get('message')} [{video.get('status')}]"
        if line != last_line:
            print(line, flush=True)
            last_line = line
        procs = sample_processes()
        peak["chrome"] = max(peak["chrome"], procs.get("chrome.exe", 0))
        peak["node"] = max(peak["node"], procs.get("node.exe", 0))
        peak["python"] = max(peak["python"], procs.get("python.exe", 0) + procs.get("pythonw.exe", 0))
        peak["ffmpeg"] = max(peak["ffmpeg"], procs.get("ffmpeg.exe", 0))
        if str(video.get("status")) in ("completed", "failed", "cancelled"):
            break

    elapsed = round(time.time() - started, 1)
    final_status = str(video.get("status"))
    playable = bool(video.get("playable"))
    print(f"FINAL: {final_status} | playable: {playable} | elapsed: {elapsed}s")
    print(f"PEAK PROCS: {peak}")
    video_path = Path.home() / ".voice_flow" / "v3_projects" / job_id / "video.mp4"
    print(f"VIDEO: {video_path} exists={video_path.is_file()}")
    OUT.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "status": final_status,
                "playable": playable,
                "elapsed_sec": elapsed,
                "peak_processes": peak,
                "video_path": str(video_path),
                "video_size": video_path.stat().st_size if video_path.is_file() else 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
