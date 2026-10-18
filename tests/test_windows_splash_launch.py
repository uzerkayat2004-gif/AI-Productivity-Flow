"""QA BRANCH ONLY (never merge): real Windows Video Flow end-to-end on the
published v1.0.12 installer. Replaces the splash test on this branch so the
existing CI Windows job runs it."""
from __future__ import annotations

import hashlib, os, subprocess, sys, time, urllib.request
from pathlib import Path
import pytest

URL = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.12/AI-Productivity-Flow-Setup-x64.exe"
DRIVER = Path(__file__).resolve().parent / "qa" / "vf_win_driver.py"
BASE = Path(os.environ.get("RUNNER_TEMP", "C:/qa")) / "apfqa"
INSTALL = BASE / "app"


def say(capsys, text):
    with capsys.disabled():
        print(text, flush=True)


@pytest.fixture(scope="module")
def installed():
    BASE.mkdir(parents=True, exist_ok=True)
    exe = BASE / "setup.exe"
    if not exe.is_file():
        urllib.request.urlretrieve(URL, exe)
    sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    t0 = time.time()
    r = subprocess.run([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={INSTALL}", f"/LOG={BASE/'install.log'}"], timeout=1500)
    return {"sha": sha, "rc": r.returncode, "secs": int(time.time() - t0)}


def _run(capsys, installed, scenario):
    py = INSTALL / "runtime" / "python" / "python.exe"
    say(capsys, f"\n===== SCENARIO {scenario} | installer sha {installed['sha'][:16]} rc {installed['rc']} {installed['secs']}s | python exists {py.is_file()}")
    assert py.is_file(), "installed python missing"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}
    t0 = time.time()
    p = subprocess.run([str(py), str(DRIVER), scenario, str(BASE / scenario)], capture_output=True, text=True, timeout=1700, env=env, cwd=str(BASE))
    out = (p.stdout or "") + "\nSTDERR:\n" + (p.stderr or "")[-6000:]
    for line in out.splitlines():
        if line.startswith("LOG INFO") and "voice_flow.video_flow_engine" not in line and "node" not in line.lower():
            continue
        say(capsys, f"[{scenario}] {line[:4000]}")
    say(capsys, f"===== {scenario} rc={p.returncode} wall={int(time.time()-t0)}s")
    return out


@pytest.mark.timeout(3600)
def test_local_video_on_installed_windows_app(installed, capsys):
    out = _run(capsys, installed, "local")
    assert "RESULT_OK" in out


@pytest.mark.timeout(3600)
def test_notebooklm_refused_then_local_video(installed, capsys):
    out = _run(capsys, installed, "nlm_refused")
    assert "RESULT_OK" in out
