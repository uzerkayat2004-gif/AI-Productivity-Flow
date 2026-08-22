"""Visual QA: contact sheets + deterministic checks for generated videos.

Usage: python visual_qa.py <video.mp4> <out_prefix> [--frames N]
Outputs: <out_prefix>-sheet.jpg (contact sheet) and prints QA metrics:
duration, resolution, frame brightness variance (visual monotony detector),
and structure repetition from a sibling creative-direction.json if present.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(video)],
        capture_output=True, text=True,
    )
    data = json.loads(out.stdout or "{}")
    fmt = data.get("format", {})
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "duration": float(fmt.get("duration") or 0),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "codec": video_stream.get("codec_name"),
        "size": int(fmt.get("size") or 0),
    }


def contact_sheet(video: Path, prefix: Path, frames: int = 12) -> Path:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        pattern = str(Path(tmp) / "f%03d.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "quiet", "-i", str(video), "-vf", f"select='not(mod(n\\,max(1\\,floor(tb*{frames}))))',scale=480:-1,tile={frames//2}x2",
             "-frames:v", "1", str(prefix.with_suffix(".sheet.jpg"))],
            capture_output=True,
        )
        # Fallback: even sampling when select expression yields nothing
        if not prefix.with_suffix(".sheet.jpg").is_file():
            subprocess.run(
                ["ffmpeg", "-y", "-v", "quiet", "-i", str(video), "-vf", f"fps={max(1, frames)}/{max(1, probe(video)['duration'])},scale=480:-1,tile={frames//2}x2",
                 "-frames:v", "1", str(prefix.with_suffix(".sheet.jpg"))],
                capture_output=True,
            )
    return prefix.with_suffix(".sheet.jpg")


def brightness_variance(video: Path, samples: int = 12) -> dict:
    if Image is None:
        return {"error": "PIL unavailable"}
    import tempfile
    metrics: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "s%02d.jpg")
        duration = probe(video)["duration"] or 1
        subprocess.run(
            ["ffmpeg", "-y", "-v", "quiet", "-i", str(video), "-vf",
             f"fps={samples}/{duration:.3f},scale=160:-1", out],
            capture_output=True,
        )
        for path in sorted(Path(tmp).glob("s*.jpg")):
            image = Image.open(path).convert("L")
            stat = image.resize((16, 9))
            pixels = list(stat.getdata())
            mean = sum(pixels) / len(pixels)
            metrics.append(sum((p - mean) ** 2 for p in pixels) / len(pixels) ** 0.5)
    if not metrics:
        return {"error": "no frames sampled"}
    import statistics
    consecutive = [abs(a - b) for a, b in zip(metrics, metrics[1:])]
    return {
        "frame_contrast_avg": round(sum(metrics) / len(metrics), 1),
        "frame_to_frame_change_avg": round(sum(consecutive) / len(consecutive), 2) if consecutive else 0,
        "monotony_flag": bool(consecutive) and (sum(consecutive) / len(consecutive)) < 3.0,
    }


def structure_repetition(video: Path) -> dict:
    direction_path = video.parent / "creative-direction.json"
    if not direction_path.is_file():
        return {"treatments": None}
    direction = json.loads(direction_path.read_text(encoding="utf-8"))
    treatments = [s.get("treatment") for s in direction.get("scenes", [])]
    max_run = run = 1
    for previous, current in zip(treatments, treatments[1:]):
        run = run + 1 if current == previous else 1
        max_run = max(max_run, run)
    return {"treatments": treatments, "max_consecutive": max_run}


def main() -> None:
    video = Path(sys.argv[1])
    prefix = Path(sys.argv[2])
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    info = probe(video)
    sheet = contact_sheet(video, prefix, frames)
    report = {
        "video": video.name,
        **info,
        **brightness_variance(video),
        **structure_repetition(video),
        "sheet": str(sheet) if sheet.is_file() else None,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
