"""Runs inside the INSTALLED app's own Python on Windows CI.
Scenario local: plain local Video Flow job (no AI planner, no NotebookLM).
Scenario nlm_refused: NotebookLM path where Google refuses the video (fake CLI),
so the app must retry as Explainer, then make the video locally."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, logging
from pathlib import Path
from types import SimpleNamespace

scenario = sys.argv[1]
work = Path(sys.argv[2]); work.mkdir(parents=True, exist_ok=True)
os.environ["VOICE_FLOW_DATA_DIR"] = str(work / "data")
os.environ.pop("CI", None)
logging.basicConfig(level=logging.INFO, format="LOG %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

import voice_flow, voice_flow.runtime_env as RE, voice_flow.node_component as NC
print("PKG", voice_flow.__file__)
print("INSTALLED", RE.is_installed(), "ROOT", RE.install_root())
print("BUNDLED_NODE", NC.bundled_node_version(), "NEEDS_MANAGED", NC.needs_managed_node())
from voice_flow._version import VERSION
print("VERSION", VERSION)

TEXT = (
    "Solar panels turn sunlight into electricity. Each panel holds many cells made of silicon. "
    "When light hits a cell, it knocks electrons loose, and that flow of electrons is an electric current. "
    "An inverter changes this direct current into the alternating current that homes use. "
    "Panels work best when they face the sun with no shade. They still work on cloudy days, just less. "
    "Most panels last about twenty five years and need little care beyond the odd clean. "
    "Batteries can store extra power from the day so a home can use it at night."
)

calls = []
if scenario == "nlm_refused":
    from voice_flow.video_flow_engine.notebooklm import provider as P
    def runner(command, timeout):
        c = list(command); j = " ".join(c); calls.append(" ".join(c[3:8]))
        def out(p, rc=0): return SimpleNamespace(returncode=rc, stdout=json.dumps(p), stderr="")
        if "auth" in c[3:5]: return out({"status": "ok", "authenticated": True, "checks": {"token_fetch": True}})
        if "source add" in j: return out({"source": {"id": "s1", "title": "t"}})
        if "source wait" in j: return out({"source_id": "s1", "status": "ready"})
        if "generate video" in j: return out({"error": True, "code": "GENERATION_FAILED", "message": "Video generation failed"}, 1)
        if "create" in j: return out({"notebook": {"id": "n1", "title": "x"}})
        if "delete" in j: return out({"success": True})
        return out({"status": "completed"})
    orig = P.NotebookLMVideoProvider.__init__
    def init(self, *a, **k):
        cli = work / "notebooklm.exe"; cli.write_bytes(b"x")
        k["cli_path"] = cli; k["runner"] = runner; k["sleep"] = lambda s: None; k["poll_interval_seconds"] = 0.01
        orig(self, *a, **k)
    P.NotebookLMVideoProvider.__init__ = init
    P.NotebookLMVideoProvider.check_auth = lambda self, *a, **k: P.AuthStatus(status="ok", profile="p", authenticated=True)

from voice_flow.video_flow_service import VideoFlowService
svc = VideoFlowService(projects_root=work / "proj")
kw = dict(source_text=TEXT, mode="summary", title="Solar panels", source_name="", model_ref=None, theme="auto",
          visual_direction="", allow_external_ai=False, allow_local_fallback=True, style="auto")
if scenario == "nlm_refused":
    kw.update(provider="notebooklm", video_engine="notebooklm", format="auto", requested_format="auto")
job = svc.queue(**kw)
t0 = time.time(); last = None
while time.time() - t0 < 1500:
    j = svc.get(job.job_id)
    msg = (str(j.state), j.message)
    if msg != last:
        print(f"PROGRESS {int(time.time()-t0)}s {j.state} | {j.message}", flush=True); last = msg
    if str(j.state).split(".")[-1].lower() in ("complete", "completed", "failed", "cancelled"): break
    time.sleep(2)
j = svc.get(job.job_id)
meta = dict(j.meta or {})
print("FINAL", j.state, "|", j.message)
print("META", json.dumps({k: meta.get(k) for k in sorted(meta) if any(s in k for s in ("error", "fallback", "engine", "provider", "format", "renderer"))}, default=str)[:3000])
print("CLI_CALLS", json.dumps(calls))
mp4 = Path(meta.get("output_path") or meta.get("video_path") or (work / "proj" / job.job_id / "video.mp4"))
print("MP4", mp4, mp4.is_file(), mp4.stat().st_size if mp4.is_file() else 0)
print("MANAGED_NODE", NC.managed_node_executable())
ff = RE.ffmpeg_executable() if hasattr(RE, "ffmpeg_executable") else "ffmpeg"
if mp4.is_file():
    probe = Path(str(ff)).with_name("ffprobe.exe")
    r = subprocess.run([str(probe), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(mp4)], capture_output=True, text=True)
    print("PROBE", r.stdout.replace("\n", " "))
    thumb = work / "thumb.jpg"
    subprocess.run([str(ff), "-y", "-v", "error", "-ss", "3", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=320:-1", "-q:v", "6", str(thumb)])
    if thumb.is_file():
        print("THUMB_B64", base64.b64encode(thumb.read_bytes()).decode())
for logf in (work / "proj").rglob("*.log"):
    print("JOBLOG", logf.name, logf.read_text(errors="replace")[-2500:].replace("\n", " || "))
print("RESULT_OK" if mp4.is_file() and str(j.state) == "complete" else "RESULT_FAIL")
