"""QA driver, run by walkthrough.py with the INSTALLED Mac app's own Python.

Makes one real local Video Flow video (no AI planner, no NotebookLM) with the
toolchain inside the .app (Node 22, HyperFrames, Narova, ffmpeg) and reports
what happened. Usage: python3 vf_mac_driver.py <work dir>
"""
import base64
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

work = Path(sys.argv[1]).resolve()
work.mkdir(parents=True, exist_ok=True)
os.environ["VOICE_FLOW_DATA_DIR"] = str(work / "data")
os.environ.pop("CI", None)
logging.basicConfig(level=logging.INFO, format="LOG %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

import voice_flow
import voice_flow.runtime_env as RE
from voice_flow._version import VERSION

print("PKG", voice_flow.__file__, "VERSION", VERSION, flush=True)
print("APP_RUNTIME", RE.app_runtime_root(), "PACKAGED", RE.is_packaged_app())
for label, exe in (("NODE", RE.node_executable()), ("FFMPEG", RE.ffmpeg_executable()), ("FFPROBE", RE.ffprobe_executable())):
    ver = ""
    if exe:
        try:
            ver = subprocess.run([str(exe), "-version" if "ff" in label.lower() else "--version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        except Exception as exc:
            ver = f"ERR {exc}"
    print(label, exe, ver, flush=True)
print("NAROVA", RE.narova_tool_root())
print("PREFLIGHT", RE.preflight_problems(), flush=True)
t = time.time()
print("RENDER_BROWSER_ENSURE", RE.ensure_render_browser(log=print), RE.render_browser_cache(), f"{time.time()-t:.0f}s", flush=True)

TEXT = (
    "Solar panels turn sunlight into electricity. Each panel holds many cells made of silicon. "
    "When light hits a cell, it knocks electrons loose, and that flow of electrons is an electric current. "
    "An inverter changes this direct current into the alternating current that homes use. "
    "Panels work best when they face the sun with no shade. They still work on cloudy days, just less. "
    "Most panels last about twenty five years and need little care beyond the odd clean."
)

from voice_flow.video_flow_service import VideoFlowService

svc = VideoFlowService(projects_root=work / "proj")
job = svc.queue(source_text=TEXT, mode="summary", title="", source_name="", model_ref=None, theme="auto",
                visual_direction="", allow_external_ai=False, allow_local_fallback=True, style="auto")
print("TITLE", (svc.get(job.job_id).meta or {}).get("title"), flush=True)
t0 = time.time()
last = None
while time.time() - t0 < 1080:
    j = svc.get(job.job_id)
    msg = (str(j.state), j.message)
    if msg != last:
        print(f"PROGRESS {int(time.time()-t0)}s {j.state} | {j.message}", flush=True)
        last = msg
    if str(j.state).split(".")[-1].lower() in ("complete", "completed", "failed", "cancelled"):
        break
    time.sleep(2)
j = svc.get(job.job_id)
meta = dict(j.meta or {})
print("FINAL", j.state, "|", j.message, f"{int(time.time()-t0)}s")
print("META", json.dumps({k: meta.get(k) for k in sorted(meta) if any(s in k for s in ("error", "fallback", "engine", "renderer", "title"))}, default=str)[:3000])
mp4 = Path(meta.get("output_path") or (work / "proj" / job.job_id / "video.mp4"))
ok = mp4.is_file() and mp4.stat().st_size > 0 and str(j.state).split(".")[-1].lower() in ("complete", "completed")
print("MP4", mp4, mp4.is_file(), mp4.stat().st_size if mp4.is_file() else 0)
probe = RE.ffprobe_executable()
if mp4.is_file() and probe:
    r = subprocess.run([str(probe), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(mp4)], capture_output=True, text=True)
    print("PROBE", r.stdout.replace("\n", " "))
    thumb = work / "thumb.jpg"
    subprocess.run([str(RE.ffmpeg_executable()), "-y", "-v", "error", "-ss", "3", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=480:-1", str(thumb)])
for logf in (work / "proj").rglob("*.log"):
    print("JOBLOG", logf.name, logf.read_text(errors="replace")[-3000:].replace("\n", " || "))
print("RESULT_OK" if ok else "RESULT_FAIL", flush=True)
