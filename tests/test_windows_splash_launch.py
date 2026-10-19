"""QA BRANCH ONLY (never merge): does an installed v1.0.11 update itself to
the latest release with nobody touching it? Replaces the splash test on this
branch so the existing CI Windows job runs it."""
from __future__ import annotations

import os, re, subprocess, time, urllib.request
from pathlib import Path
import pytest

URL = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.11/AI-Productivity-Flow-Setup-x64.exe"
BASE = Path(os.environ.get("RUNNER_TEMP", "C:/qa")) / "apfau"
INSTALL = BASE / "app"
VERSION_FILE = INSTALL / "runtime" / "python" / "Lib" / "site-packages" / "voice_flow" / "_version.py"
LOGS = Path.home() / ".voice_flow" / "logs"


def say(capsys, text):
    with capsys.disabled():
        print(text, flush=True)


def version():
    try:
        m = re.search(r'__version__ = "([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except OSError:
        return "missing"


def procs():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | ForEach-Object { \"$($_.ProcessId) $($_.Name) $($_.CommandLine)\" }"],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l.strip()]


def probe(capsys):
    py = INSTALL / "runtime" / "python" / "python.exe"
    code = ("import json;from voice_flow.update_checker import check_for_updates as c;"
            "from voice_flow import app_updater as a;r=c(force=True);"
            "print('PROBE', json.dumps({k:r.get(k) for k in ('current_version','latest_version','update_available','checked','error')}));"
            "print('PLAN', json.dumps(r.get('update_plan'), default=str)[:1500]);"
            "print('PKG', a.installed_package_dir(), 'STATE', a.update_state_dir(), 'AUTO', a.auto_update_enabled())")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}
    r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, env=env, timeout=120)
    say(capsys, r.stdout[-4000:] + "\nERR " + r.stderr[-3000:])


def dump_logs(capsys):
    say(capsys, f"home={Path.home()} logs_exists={LOGS.is_dir()} files={[str(x) for x in (Path.home()/'.voice_flow').rglob('*.log*')][:30]}")
    for p in sorted((Path.home()/'.voice_flow').rglob("*.log*")):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = [l for l in lines if re.search(r"autoupdate|update|Traceback|Error|STARTUP|READY", l, re.I)]
        say(capsys, f"--- {p.name}: {len(lines)} lines, {len(hits)} relevant")
        for l in hits[-150:]:
            say(capsys, "   " + l[:600])
    upd = INSTALL / "updates"
    if upd.is_dir():
        for f in upd.rglob("*"):
            if f.is_file() and f.stat().st_size < 20000 and f.suffix in (".json", ".log", ".txt", ""):
                say(capsys, f"--- {f}: {f.read_text(encoding='utf-8', errors='replace')[:3000]}")
            elif f.is_file():
                say(capsys, f"--- {f} ({f.stat().st_size} bytes)")


@pytest.mark.timeout(3600)
def test_installed_v1011_updates_itself(capsys):
    BASE.mkdir(parents=True, exist_ok=True)
    exe = BASE / "setup.exe"
    urllib.request.urlretrieve(URL, exe)
    r = subprocess.run([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={INSTALL}", f"/LOG={BASE/'install.log'}"], timeout=1500)
    say(capsys, f"\n===== installed rc={r.returncode} version={version()}")
    time.sleep(20)
    say(capsys, "procs after install (silent setup launches the app itself):\n  " + "\n  ".join(procs()))
    if not any("launch_apf" in p or "voice_flow" in p for p in procs()):
        pyw = INSTALL / "runtime" / "python" / "pythonw.exe"
        subprocess.Popen([str(pyw), str(INSTALL / "launch_apf.pyw")], cwd=str(INSTALL))
        say(capsys, "launched app manually")
    t0 = time.time()
    time.sleep(90)
    probe(capsys)
    seen = version()
    while time.time() - t0 < 900:
        v = version()
        if v != seen:
            say(capsys, f"[{int(time.time()-t0)}s] version changed {seen} -> {v}")
            seen = v
        if v not in ("1.0.11", "missing", "?"):
            break
        time.sleep(10)
    time.sleep(45)
    say(capsys, f"===== FINAL version={version()} after {int(time.time()-t0)}s")
    say(capsys, "procs at end:\n  " + "\n  ".join(procs()))
    dump_logs(capsys)
    assert version() != "1.0.11", "app did not update itself"
    assert any("launch_apf" in p or "voice_flow" in p for p in procs()), "app not running again after update"
