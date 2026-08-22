"""Isolated 3D visibility probe: one particle-field scene, real code path."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("C:/Users/Asus/.gemini/antigravity/scratch/voice-flow")
sys.path.insert(0, str(ROOT / "src"))

from voice_flow.video_flow_engine import scene_author  # noqa: E402
from voice_flow.video_flow_engine.bridge import build_directed_production  # noqa: E402

out = ROOT / "video-flow-visual-upgrade" / "particle-probe"
(out / "narova").mkdir(parents=True, exist_ok=True)

storyboard = {
    "topic": "Lidar point cloud",
    "sections": [
        {"id": "field", "title": "Lidar point cloud", "learning_goal": "spatial",
         "lecture_lines": ["A spinning lidar builds a live point cloud of the road."], "animations": []}
    ],
}
direction = {
    "brief": {"motion": "crisp", "background": "gradient", "accent_shift": 0},
    "scenes": [{"index": 1, "id": "field", "treatment": "particle-field",
                "metaphor": "point cloud", "labels": ["Live point cloud", "Depth per point"]}],
}
production = build_directed_production(storyboard, direction, title="probe", mode="summary")
assert production["renderer"] == "hyperframes", production["renderer"]
assert any(o.get("type") == "particles" for o in production["scenes"][0]["three"]["objects"])
assert "vfd-clear" in production["scenes"][0]["body"]
assert production["scenes"][0]["three"].get("background"), "three background missing"
(out / "production.json").write_text(json.dumps(production, indent=1), encoding="utf-8")

narova_dir = out / "narova"
config = dict(production)
files = config.pop("_files", {})
(narova_dir / "reel.config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
(narova_dir / "theme.css").write_text(files["theme.css"], encoding="utf-8")

node = "node"
cli = str(ROOT / "third_party" / "narova" / "tool" / "bin" / "narova.js")
venv_py = Path.home() / ".narova" / "venv" / "Scripts" / "python.exe"
env = {k: v for k, v in __import__("os").environ.items()
       if k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
                "LOCALAPPDATA", "APPDATA", "NAROVA_PYTHON")}
env["NAROVA_PYTHON"] = str(venv_py if venv_py.is_file() else sys.executable)
env["PYTHONIOENCODING"] = "utf-8"
for args in (
    ["check", "--project", str(narova_dir), "--renderer", "hyperframes"],
    ["synth", "--project", str(narova_dir), "--renderer", "hyperframes"],
    ["compose", "--project", str(narova_dir), "--renderer", "hyperframes"],
    ["build", "--project", str(narova_dir), "--renderer", "hyperframes", "--fps", "30", "--quality", "standard"],
):
    print("+", args[0], flush=True)
    r = subprocess.run([node, cli, *args], cwd=narova_dir, capture_output=True, text=True, shell=False, env=env)
    log = out / f"{args[0]}.log"
    log.write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        print(r.stdout[-1500:])
        print(r.stderr[-1500:])
        raise SystemExit(f"{args[0]} failed")

video = narova_dir / "out" / "video.mp4"
print("video:", video, video.stat().st_size if video.is_file() else "MISSING")
mid = subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video)],
    capture_output=True, text=True,
)
dur = float(json.loads(mid.stdout)["format"]["duration"]) / 2
subprocess.run(
    ["ffmpeg", "-y", "-v", "quiet", "-ss", str(dur), "-i", str(video), "-frames:v", "1", "-q:v", "2",
     str(out / "particle-probe-frame.jpg")],
    check=True,
)
print("frame:", out / "particle-probe-frame.jpg")
