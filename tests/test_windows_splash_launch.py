"""QA BRANCH ONLY (never merge): Windows check for the Mac Video Flow branch.
Installs published v1.0.13, lays this branch's voice_flow package over it (what
the app update does), then makes a real Video Flow video with the installed
runtime and boots the app's API server. Replaces the splash test on this branch
so the existing CI Windows job runs it."""
from __future__ import annotations

import hashlib, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
import pytest

URL = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.13/AI-Productivity-Flow-Setup-x64.exe"
ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "walkthrough" / "vf_mac_driver.py"
BASE = Path(os.environ.get("RUNNER_TEMP", "C:/qa")) / "apfqa"
INSTALL = BASE / "app"
PY = INSTALL / "runtime" / "python" / "python.exe"
SITE = INSTALL / "runtime" / "python" / "Lib" / "site-packages" / "voice_flow"


def say(capsys, text):
    with capsys.disabled():
        print(text, flush=True)


@pytest.fixture(scope="module")
def installed():
    BASE.mkdir(parents=True, exist_ok=True)
    exe = BASE / "setup.exe"
    if not exe.is_file():
        urllib.request.urlretrieve(URL, exe)
    r = subprocess.run([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={INSTALL}", f"/LOG={BASE/'install.log'}"], timeout=1500)
    time.sleep(10)
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe", "/T"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T"], capture_output=True)
    pkg = SITE if SITE.is_dir() else next(INSTALL.rglob("voice_flow/_version.py")).parent
    shutil.copytree(ROOT / "src" / "voice_flow", pkg, dirs_exist_ok=True)
    return {"rc": r.returncode, "pkg": str(pkg)}


def _env():
    return {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}


@pytest.mark.timeout(3000)
def test_local_video_on_windows_with_this_branch(installed, capsys):
    say(capsys, f"\n===== installer rc {installed['rc']} pkg {installed['pkg']} python {PY.is_file()}")
    t0 = time.time()
    p = subprocess.run([str(PY), str(DRIVER), str(BASE / "vf")], capture_output=True, text=True, timeout=2400, env=_env(), cwd=str(BASE))
    out = (p.stdout or "") + "\nSTDERR:\n" + (p.stderr or "")[-6000:]
    for line in out.splitlines():
        if line.startswith("LOG INFO") and "video_flow_engine" not in line:
            continue
        say(capsys, f"[vf] {line[:3000]}")
    say(capsys, f"===== rc={p.returncode} wall={int(time.time()-t0)}s")
    assert "RESULT_OK" in out


@pytest.mark.timeout(600)
def test_api_server_boots_and_answers(installed, capsys):
    code = (
        "import json,threading,time,urllib.request\n"
        "from voice_flow.gui import api_server as A\n"
        "from voice_flow._version import VERSION\n"
        "threading.Thread(target=A.start_api_server,daemon=True).start()\n"
        "print('VERSION',VERSION,'PORT',A.PORT)\n"
        "time.sleep(8)\n"
        "for p in ('/api/version','/api/platform/info','/api/video-flow/providers','/api/video-flow/notebooklm/status','/api/audio-providers/overview'):\n"
        "    try:\n"
        "        r=urllib.request.urlopen('http://127.0.0.1:%d%s'%(A.PORT,p),timeout=20); print('GET',p,r.status,r.read()[:200])\n"
        "    except Exception as e: print('GET',p,'ERR',e)\n"
    )
    p = subprocess.run([str(PY), "-c", code], capture_output=True, text=True, timeout=300, env=_env(), cwd=str(BASE))
    say(capsys, p.stdout[-5000:] + "\nERR " + p.stderr[-4000:])
    assert "VERSION" in p.stdout
