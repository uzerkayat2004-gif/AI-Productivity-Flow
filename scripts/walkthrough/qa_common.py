"""Shared helpers for the v1.0.2 final pre-launch QA phases (CI only, not shipped)."""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8991"
REPO = os.environ.get("GITHUB_REPOSITORY", "uzerkayat2004-gif/AI-Productivity-Flow")
APP_NAME = "AI Productivity Flow"
BUNDLE_ID = "com.uzerkayat.aiproductivityflow"
HOME = Path.home()
OUT = Path(os.environ.get("QA_OUT", "out")).resolve()
EV = OUT / "qa"
EV.mkdir(parents=True, exist_ok=True)
SHOTS = EV / "shots"
SHOTS.mkdir(exist_ok=True)
HELPER = os.environ.get("QA_HELPER", str(OUT / "apf-native"))
RESULTS: list[dict] = []
T0 = time.time()
_n = 0


def ts() -> str:
    return f"{time.time() - T0:7.1f}s"


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    print(line, flush=True)
    with open(EV / "qa-log.txt", "a") as f:
        f.write(line + "\n")


def record(area: str, step: str, status: str, note="", evidence=None) -> None:
    row = {"t": round(time.time() - T0, 1), "area": area, "step": step, "status": status,
           "note": str(note)[:3000], "evidence": evidence}
    RESULTS.append(row)
    (EV / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"QA[{status:>6}] {area} | {step} | {str(note)[:900]}", flush=True)


def sh(cmd: str, timeout: float = 120, quiet: bool = False) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired as e:
        out = f"TIMEOUT after {timeout}s: {(e.stdout or b'')[:2000]!r}"
        rc = -999
    with open(EV / "cmds.log", "a") as f:
        f.write(f"\n$ {cmd}\n[rc={rc}]\n{out[-20000:]}\n")
    if not quiet:
        print(f"$ {cmd} -> rc={rc}\n{out[-1500:]}", flush=True)
    return rc, out


def save(name: str, text: str) -> str:
    p = EV / name
    p.write_text(text)
    return str(p.relative_to(OUT))


def api(path: str, body=None, timeout: float = 20.0, method: str | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method or ("GET" if body is None else "POST"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:300].decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300].decode(errors="replace")
    except Exception as e:
        return None, repr(e)


def wait_api(seconds: float = 120) -> float | None:
    t = time.time()
    while time.time() - t < seconds:
        code, _ = api("/api/version", timeout=2)
        if code == 200:
            return time.time() - t
        time.sleep(1)
    return None


def api_down(seconds: float = 30) -> bool:
    t = time.time()
    while time.time() - t < seconds:
        code, _ = api("/api/version", timeout=1)
        if code is None:
            return True
        time.sleep(1)
    return False


def shot(label: str) -> str:
    global _n
    _n += 1
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", label)[:70]
    name = f"{_n:03d}-{safe}.png"
    subprocess.run(["screencapture", "-x", str(SHOTS / name)], check=False)
    return f"qa/shots/{name}"


def helper(*args: str, timeout: float = 20) -> str:
    try:
        return subprocess.run([HELPER, *args], capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception as exc:
        return f"ERR {exc}"


PS_FMT = "pid=,ppid=,rss=,pcpu=,etime=,command="


def ps_rows() -> list[dict]:
    out = subprocess.run(["ps", "-axww", "-o", PS_FMT], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "rss_kb": int(parts[2]),
                         "cpu": float(parts[3]), "etime": parts[4], "cmd": parts[5]})
        except ValueError:
            pass
    return rows


INTEREST = re.compile(r"AI Productivity Flow|ai-productivity-flow|llama-server|nemotron|voice_flow|\bnode\b|ffmpeg|narova|AppTranslocation", re.I)


def app_tree() -> list[dict]:
    rows = ps_rows()
    me = os.getpid()
    # "playwright": the QA's own Playwright driver is a `node` process; counting
    # it as the app made quit_app() never "all gone" and kill_all() killed the
    # driver ("Connection closed while reading from the driver", ui it4).
    roots = {r["pid"] for r in rows if INTEREST.search(r["cmd"]) and "qa_" not in r["cmd"] and "walkthrough" not in r["cmd"]
             and "playwright" not in r["cmd"].lower() and "ms-playwright" not in r["cmd"]
             and "screencapture" not in r["cmd"] and r["pid"] != me and "pgrep" not in r["cmd"] and "lsof" not in r["cmd"]
             and "tcpdump" not in r["cmd"]}
    changed = True
    while changed:
        changed = False
        for r in rows:
            if r["ppid"] in roots and r["pid"] not in roots and "lsof" not in r["cmd"]:
                roots.add(r["pid"])
                changed = True
    return [r for r in rows if r["pid"] in roots]


def fmt_rows(rows) -> str:
    return "\n".join(f"{r['pid']:>6} {r['ppid']:>6} {r['rss_kb']/1024:8.1f}MB {r['cpu']:5.1f}% {r['etime']:>10} {r['cmd'][:260]}" for r in rows) or "(none)"


def count_llama() -> int:
    # Count llama-server executables only: the app's POSIX parent-watch guard is a
    # /bin/sh whose argv also contains the llama-server path.
    return sum(1 for r in ps_rows()
               if r["cmd"].split(" -m ")[0].rstrip().endswith("llama-server") and not r["cmd"].startswith("/bin/sh"))


def plist(app: str, key: str) -> str:
    return subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Print {key}", f"{app}/Contents/Info.plist"],
                          capture_output=True, text=True).stdout.strip()


def launch_open(app: str, new: bool = False) -> tuple[int, str]:
    return sh(f"open {'-n ' if new else ''}{shlex.quote(app)}", timeout=30)


def launch_exec(app: str, tag: str):
    exe = plist(app, "CFBundleExecutable")
    f = open(EV / f"app-stdout-{tag}.txt", "w")
    return subprocess.Popen([f"{app}/Contents/MacOS/{exe}"], stdout=f, stderr=subprocess.STDOUT, start_new_session=True)


def quit_app(timeout: float = 40) -> dict:
    """Quit like a user (Cmd+Q / Dock Quit = Apple Event quit) and report what is left."""
    t = time.time()
    rc, out = sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=20)
    gone = False
    while time.time() - t < timeout:
        if not app_tree():
            gone = True
            break
        time.sleep(1)
    left = app_tree()
    return {"osascript_rc": rc, "osascript_out": out.strip()[:300], "all_gone": gone,
            "seconds": round(time.time() - t, 1), "left": fmt_rows(left)}


def kill_all(sig: int = 15, wait: float = 20) -> str:
    for r in app_tree():
        try:
            os.kill(r["pid"], sig)
        except Exception:
            pass
    t = time.time()
    while time.time() - t < wait and app_tree():
        time.sleep(1)
    left = app_tree()
    for r in left:
        try:
            os.kill(r["pid"], 9)
        except Exception:
            pass
    time.sleep(1)
    return fmt_rows(left)


def wipe_user_data() -> str:
    paths = [HOME / ".voice_flow", HOME / ".narova",
             HOME / "Library/Application Support/AI Productivity Flow",
             HOME / f"Library/Application Support/{BUNDLE_ID}",
             HOME / f"Library/Caches/{BUNDLE_ID}", HOME / f"Library/Preferences/{BUNDLE_ID}.plist",
             HOME / f"Library/WebKit/{BUNDLE_ID}", HOME / f"Library/HTTPStorages/{BUNDLE_ID}",
             HOME / f"Library/Saved Application State/{BUNDLE_ID}.savedState",
             HOME / "Library/LaunchAgents/com.uzerkayat.aiproductivityflow.plist"]
    for p in HOME.glob("Library/LaunchAgents/*"):
        if "productivity" in p.name.lower() or "voiceflow" in p.name.lower() or "voice_flow" in p.name.lower():
            paths.append(p)
    done = []
    for p in paths:
        if p.exists() or p.is_symlink():
            sh(f"rm -rf {shlex.quote(str(p))}", quiet=True)
            done.append(str(p))
    return "removed: " + ", ".join(done)


def leftovers() -> str:
    cmd = ("ls -la ~/.voice_flow ~/.narova 2>&1 | head -80; du -sh ~/.voice_flow 2>/dev/null; "
           "echo '--- Library matches'; find ~/Library -maxdepth 3 \\( -iname '*productivity*' -o -iname '*voice_flow*' -o -iname '*voiceflow*' -o -iname '*uzerkayat*' \\) 2>/dev/null; "
           "echo '--- LaunchAgents'; ls -la ~/Library/LaunchAgents 2>&1; "
           "echo '--- processes'; ps -axww -o pid,ppid,command | grep -Ei 'productivity|llama-server|nemotron|voice_flow|narova' | grep -v grep")
    return sh(cmd, quiet=True)[1]


class NetCapture:
    """tcpdump on pktap with per-process metadata (-k), plus lsof sampling of app pids."""

    def __init__(self, name: str):
        self.name = name
        self.pcap_txt = EV / f"net-{name}-tcpdump.txt"
        self.lsof_txt = EV / f"net-{name}-lsof.txt"
        self.proc = None
        self.stop_ev = threading.Event()
        self.thread = None
        self.seen: dict[str, set] = {}

    def start(self):
        try:
            self.proc = subprocess.Popen(
                ["sudo", "tcpdump", "-i", "pktap,all", "-k", "NP", "-nn", "-l", "-q",
                 "(tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0) or udp port 53 or udp port 443"],
                stdout=open(self.pcap_txt, "w"), stderr=subprocess.STDOUT)
        except Exception as exc:
            log(f"tcpdump failed: {exc}")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        with open(self.lsof_txt, "w") as f:
            while not self.stop_ev.is_set():
                pids = [str(r["pid"]) for r in app_tree()]
                if pids:
                    out = subprocess.run(["lsof", "-nP", "-i", "-a", "-p", ",".join(pids)], capture_output=True, text=True).stdout
                    for line in out.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 9 and "->" in parts[8]:
                            remote = parts[8].split("->", 1)[1]
                            key = f"{parts[0]} {remote} {parts[-1] if parts[-1].startswith('(') else ''}"
                            if key not in self.seen:
                                self.seen[key] = set()
                                f.write(f"[{ts()}] {line}\n")
                                f.flush()
                self.stop_ev.wait(1.5)

    def stop(self) -> dict:
        self.stop_ev.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.proc:
            subprocess.run(["sudo", "pkill", "-f", f"tcpdump -i pktap"], check=False)
            time.sleep(1)
        txt = self.pcap_txt.read_text(errors="replace") if self.pcap_txt.exists() else ""
        summary = summarize_pktap(txt)
        (EV / f"net-{self.name}-summary.json").write_text(json.dumps(summary, indent=2))
        return {"lsof_remote": sorted(self.seen), "pktap": summary}


def summarize_pktap(txt: str) -> dict:
    """Group tcpdump -k lines by process: {proc: [dst:port ...]} and DNS names asked."""
    by_proc: dict[str, set] = {}
    for line in txt.splitlines():
        m = re.search(r"proc ([^,)]+)", line)
        proc = m.group(1).strip() if m else "?"
        dst = re.search(r"> ([0-9a-fA-F:.]+)\.(\d+):", line)
        dns = re.search(r"\? ([A-Za-z0-9.-]+)\. ", line) or re.search(r" A{1,4}\? ([A-Za-z0-9.-]+)", line)
        item = None
        if dns:
            item = "dns:" + dns.group(1)
        elif dst:
            item = f"{dst.group(1)}:{dst.group(2)}"
        if item:
            by_proc.setdefault(proc, set()).add(item)
    return {k: sorted(v)[:200] for k, v in by_proc.items()}


def resolve_ips(ips: list[str]) -> dict:
    res = {}
    for ip in ips:
        rc, out = sh(f"host {ip} | head -2", timeout=10, quiet=True)
        res[ip] = out.strip()[:200]
    return res


def finish(phase: str) -> None:
    counts: dict[str, int] = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = [f"# QA phase {phase}", "", f"counts: {counts}", "", "| t | area | step | status | evidence | note |", "|---|---|---|---|---|---|"]
    for r in RESULTS:
        note = r["note"][:400].replace("|", "/").replace("\n", " ")
        lines.append(f"| {r['t']} | {r['area']} | {r['step']} | {r['status']} | {r['evidence'] or ''} | {note} |")
    (EV / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


def guarded(area: str, step: str):
    """Decorator: run a step, record crash as status=error, never raise."""
    def deco(fn):
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception:
                record(area, step, "error", traceback.format_exc()[-1500:])
                return None
        return run
    return deco


def install_watchdog(minutes: float) -> None:
    def _t(*_):
        raise TimeoutError(f"QA watchdog {minutes} min fired")
    signal.signal(signal.SIGALRM, _t)
    signal.alarm(int(minutes * 60))
