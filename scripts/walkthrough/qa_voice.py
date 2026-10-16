"""Phases VOICE_A (bundled STT, hotkey, paste, dictionary, polish on/off, history) and
VOICE_B (model downloads + failure/retry, Nemotron, S1 / llama-server, cloud without key, process cleanup).
Audio goes in through a BlackHole loopback set as the default input."""
from __future__ import annotations

import difflib
import json
import os
import re
import shlex
import sys
import threading
import time
from pathlib import Path

from qa_common import (EV, OUT, HOME, BUNDLE_ID, record, sh, save, api, wait_api, shot, app_tree, fmt_rows, helper,
                       launch_open, quit_app, kill_all, wipe_user_data, leftovers, NetCapture, finish, install_watchdog,
                       log, count_llama, ps_rows, resolve_ips)

APP = "/Applications/AI Productivity Flow.app"
CLIPS = EV / "clips"
CLIPS.mkdir(exist_ok=True)

# id, text spoken, checks: list of (kind, value). kind: has / lacks (case-insensitive substring on final text)
SENTENCES = [
    ("short1", "My agenda for today.", [("has", "agenda")]),
    ("short2", "Call Mom.", [("has", "call")]),
    ("short3", "Okay.", []),
    ("short4", "Yes, send it.", [("has", "send")]),
    ("period_word", "The trial period ends in May.", [("has", "period"), ("has", "ends in may")]),
    ("comma_word", "Please send a comma separated list of names.", [("has", "comma"), ("has", "separated")]),
    ("newline_word", "We launched a new line of products this week.", [("has", "new line"), ("has", "products")]),
    ("qmark_word", "He had a question mark on his face.", [("has", "question mark")]),
    ("spoken_punct", "Send the report today period Then call me comma please", [("lacks", " period"), ("has", "report")]),
    ("names1", "Uzair Kayat will join the meeting with Priya.", [("has", "priya")]),
    ("names2", "Ask Rahul and Ananya to review the draft.", [("has", "review the draft")]),
    ("stutter1", "My, my, my agenda is ready.", [("has", "agenda"), ("lacks", "ag. ")]),
    ("stutter2", "I I I think we should, we should move the meeting.", [("has", "move the meeting")]),
    ("stutter3", "The the question is, is it done?", [("has", "question")]),
    ("long1", "Tomorrow morning I will review the quarterly report, then meet the design team at eleven, "
              "and after lunch I will send the final summary to everyone on the project.", [("has", "quarterly report"), ("has", "design team")]),
    ("long2", "Please remember to buy milk, eggs, bread, and coffee on the way home, and also pick up the "
              "package from the post office before it closes at six in the evening.", [("has", "post office"), ("has", "coffee")]),
    ("long3", "The new feature lets you dictate anywhere on your Mac. Hold the shortcut, speak naturally, "
              "and release it. The text appears where your cursor is.", [("has", "dictate"), ("has", "cursor")]),
    ("apostrophe", "It's Uzair's notes, don't lose them.", [("has", "don't"), ("has", "notes")]),
    ("numbers", "I paid five hundred rupees for two tickets at three p.m.", [("has", "tickets")]),
    ("email", "Hey voice flow, make this an email to Priya about the launch on Sunday.", [("has", "launch")]),
    ("summarize", "We discussed pricing, the launch date, and hiring. Hey voice flow, summarize this.", [("has", "pricing")]),
    ("react_word", "I will react to the email later today.", [("lacks", "React to")]),
    ("short5", "Thanks.", []),
    ("short6", "See you tomorrow.", [("has", "tomorrow")]),
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower()).split().__str__()


def similarity(a: str, b: str) -> float:
    wa = re.sub(r"[^a-z0-9' ]+", " ", a.lower()).split()
    wb = re.sub(r"[^a-z0-9' ]+", " ", b.lower()).split()
    return round(difflib.SequenceMatcher(None, wa, wb).ratio(), 2)


def setup_audio(area: str) -> str | None:
    rc, out = sh("HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install --cask blackhole-2ch 2>&1 | tail -5; "
                 "HOMEBREW_NO_AUTO_UPDATE=1 brew install switchaudio-osx 2>&1 | tail -3; sudo killall -9 coreaudiod; sleep 6; "
                 "SwitchAudioSource -a -t input; SwitchAudioSource -a -t output", timeout=600)
    rc1, o1 = sh("SwitchAudioSource -t input -s 'BlackHole 2ch'; SwitchAudioSource -t output -s 'BlackHole 2ch'; "
                 "SwitchAudioSource -c -t input; SwitchAudioSource -c -t output", timeout=30)
    ok = o1.count("BlackHole") >= 2
    record(area, "BlackHole loopback as default mic + speaker on the runner", "ok" if ok else "fail", (out[-800:] + "\n" + o1)[-1500:])
    return "BlackHole 2ch" if ok else None


def make_clips(area: str) -> dict:
    voices = sh("say -v '?' | grep -E 'en_(US|IN|GB)' | head -40", quiet=True)[1]
    pick = []
    for v in ("Samantha", "Rishi", "Daniel", "Alex", "Fred"):
        if re.search(rf"^{v}\s", voices, re.M):
            pick.append(v)
    if not pick:
        pick = [""]
    files = {}
    for i, (cid, text, _) in enumerate(SENTENCES):
        voice = pick[i % len(pick)]
        f = CLIPS / f"{cid}.aiff"
        sh(f"say {('-v ' + shlex.quote(voice)) if voice else ''} -r 175 -o {shlex.quote(str(f))} {shlex.quote(text)}", quiet=True)
        files[cid] = (str(f), voice)
    record(area, "TTS clips generated with macOS say", "ok" if all(Path(f).exists() for f, _ in files.values()) else "fail",
           f"voices used={pick}; {len(files)} clips; available en voices:\n{voices[:800]}")
    return files


def latest_history_id() -> int:
    code, h = api("/api/history?limit=5")
    rows = h if isinstance(h, list) else (h.get("history") or h.get("items") or []) if isinstance(h, dict) else []
    ids = [int(r.get("id", 0)) for r in rows if isinstance(r, dict)]
    return max(ids) if ids else 0


def history_after(last: int, timeout: float = 40) -> dict | None:
    t = time.time()
    while time.time() - t < timeout:
        code, h = api("/api/history?limit=5")
        rows = h if isinstance(h, list) else (h.get("history") or h.get("items") or []) if isinstance(h, dict) else []
        new = [r for r in rows if isinstance(r, dict) and int(r.get("id", 0)) > last]
        if new:
            r = max(new, key=lambda x: int(x["id"]))
            st = str(r.get("status") or "")
            if st not in ("processing", "recording", "pending", "transcribing"):
                return r
        time.sleep(0.5)
    return None


class RssSampler:
    def __init__(self):
        self.peak = {}
        self.max_llama = 0
        self.samples = []
        self.ev = threading.Event()

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()
        return self

    def loop(self):
        while not self.ev.is_set():
            tree = app_tree()
            tot = sum(r["rss_kb"] for r in tree) / 1024
            cpu = sum(r["cpu"] for r in tree)
            ll = sum(1 for r in tree if "llama-server" in r["cmd"])
            ll_all = count_llama()
            self.max_llama = max(self.max_llama, ll_all)
            self.samples.append((round(time.time(), 1), round(tot, 1), round(cpu, 1), ll_all))
            for r in tree:
                key = re.sub(r"\s+", " ", r["cmd"])[:90]
                self.peak[key] = max(self.peak.get(key, 0), round(r["rss_kb"] / 1024, 1))
            self.ev.wait(2)

    def stop(self):
        self.ev.set()
        tots = [s[1] for s in self.samples] or [0]
        cpus = [s[2] for s in self.samples] or [0]
        return {"samples": len(self.samples), "peak_total_rss_mb": max(tots), "peak_total_cpu_pct": max(cpus),
                "max_llama_server_count": self.max_llama, "peak_rss_by_process_mb": self.peak}


def textedit_open(area: str) -> int | None:
    p = Path("/tmp/paste-target.txt")
    p.write_text("")
    sh("killall TextEdit 2>/dev/null; sleep 1; open -a TextEdit /tmp/paste-target.txt; sleep 4", quiet=True)
    pid = sh("pgrep -x TextEdit", quiet=True)[1].strip().splitlines()
    wins = json.loads(helper("windows") or "[]")
    te = [w for w in wins if w.get("owner") == "TextEdit" and w.get("h", 0) > 100]
    if te:
        w = te[0]
        helper("click", str(w["x"] + w["w"] / 2), str(w["y"] + w["h"] / 2))
        time.sleep(1)
    record(area, "TextEdit opened as the paste target", "ok" if pid else "fail", f"pid={pid} window={te[:1]}", shot("textedit-target"))
    return int(pid[0]) if pid else None


def textedit_text(pid: int | None) -> str:
    if not pid:
        return ""
    return helper("axtext", str(pid))


def dictate(cid: str, clip: str, mode: str = "api", tail: float = 0.8) -> tuple[dict | None, float]:
    last = latest_history_id()
    t = time.time()
    if mode == "hotkey":
        helper("cmdopt", "down")
    else:
        api("/api/record/toggle", {"recording": True})
    time.sleep(0.6)
    sh(f"afplay {shlex.quote(clip)}", timeout=60, quiet=True)
    time.sleep(tail)
    t_release = time.time()
    if mode == "hotkey":
        helper("cmdopt", "up")
    else:
        api("/api/record/toggle", {"recording": False})
    row = history_after(last, 45)
    return row, round(time.time() - t_release, 2)


def run_set(area: str, files: dict, ids: list[str], label: str, mode: str = "api", te_pid: int | None = None) -> dict:
    stats = {"total": 0, "success": 0, "failed": 0, "no_history": 0, "check_fail": 0, "pasted": 0}
    rows = []
    for cid in ids:
        text, checks = next((t, c) for i, t, c in SENTENCES if i == cid)
        before_te = textedit_text(te_pid) if te_pid else ""
        row, latency = dictate(cid, files[cid][0], mode)
        stats["total"] += 1
        if not row:
            stats["no_history"] += 1
            st = api("/api/overlay/status")[1]
            record(area, f"{label}: {cid}", "fail", f"no history entry within 45s; overlay={st}", shot(f"{label}-{cid}-nohistory"))
            rows.append({"id": cid, "result": None})
            continue
        final = str(row.get("polished_text") or row.get("raw_text") or "")
        raw = str(row.get("raw_text") or "")
        status = str(row.get("status"))
        ok_status = status in ("success", "completed", "pasted")
        failed_checks = []
        for kind, val in checks:
            hit = val.lower() in final.lower()
            if (kind == "has" and not hit) or (kind == "lacks" and hit):
                failed_checks.append(f"{kind} {val!r}")
        sim = similarity(text, final)
        after_te = textedit_text(te_pid) if te_pid else ""
        pasted = bool(te_pid) and len(after_te) > len(before_te)
        stats["pasted"] += int(pasted)
        if ok_status:
            stats["success"] += 1
        else:
            stats["failed"] += 1
        if failed_checks:
            stats["check_fail"] += 1
        rows.append({"id": cid, "said": text, "raw": raw, "final": final, "status": status, "insertion": row.get("insertion_status"),
                     "error": row.get("error_message"), "similarity": sim, "release_to_history_s": latency,
                     "failed_checks": failed_checks, "pasted_into_textedit": pasted})
        record(area, f"{label}: {cid}", "ok" if ok_status and not failed_checks else ("warn" if ok_status else "fail"),
               f"said={text!r}\nraw={raw!r}\nfinal={final!r}\nstatus={status} insertion={row.get('insertion_status')} err={row.get('error_message')} "
               f"sim={sim} release->history={latency}s pasted={pasted} checks_failed={failed_checks}")
        time.sleep(1.0)
    save(f"dictations-{label}.json", json.dumps(rows, indent=2))
    record(area, f"{label}: summary", "ok" if stats["success"] == stats["total"] else "fail", json.dumps(stats), f"qa/dictations-{label}.json")
    return stats


def start_app_fresh(area: str) -> bool:
    kill_all()
    wipe_user_data()
    launch_open(APP)
    up = wait_api(120)
    time.sleep(12)
    record(area, "fresh launch for voice tests", "ok" if up else "fail", f"api after {up}s", shot("voice-fresh-launch"))
    # dismiss onboarding so it does not steal focus
    api("/api/settings/update", {"key": "has_viewed_onboarding", "value": True})
    return bool(up)


def select_mic(area: str, name: str | None):
    code, mics = api("/api/microphones")
    names = [d.get("name") for d in (mics.get("devices") or [])] if isinstance(mics, dict) else []
    res = api("/api/microphones/select", {"name": name}) if name else (None, "no BlackHole")
    record(area, "select BlackHole as the app microphone", "ok" if res[0] == 200 else "fail", f"devices={names}; select -> {res}")
    perm = api("/api/platform/permissions")[1]
    record(area, "permission report on runner", "info", json.dumps(perm)[:1500])


# ----------------------------------------------------------------------------
def phase_a():
    A = "voice"
    mic = setup_audio(A)
    files = make_clips(A)
    if not start_app_fresh(A):
        return
    select_mic(A, mic)
    record(A, "STT + polish defaults", "info", f"stt={api('/api/voice-flow-stt/get')[1]}\npolish={api('/api/voice-flow-polish/get')[1]}\nhotkey={api('/api/settings/hotkey')[1]}")
    te = textedit_open(A)
    net = NetCapture("voice-local").start()
    rss = RssSampler().start()
    ids = [s[0] for s in SENTENCES]
    stats = run_set(A, files, ids, "bundled-stt-polish-on", "api", te)
    s1 = shot("textedit-after-dictations")
    record(A, "TextEdit content after dictations (Accessibility read)", "info", textedit_text(te)[-2500:], s1)
    # Hotkey (real Cmd+Option modifier events).
    hk = run_set(A, files, ["short1", "names1", "long3"], "hotkey-cmd-option", "hotkey", te)
    shot("after-hotkey-dictations")
    # Back-to-back with minimal gap.
    b2b = {"ok": 0, "n": 0}
    for cid in ["short2", "short4", "short5", "short6", "stutter1", "short1", "short2", "short4"]:
        row, lat = dictate(cid, files[cid][0], "api", tail=0.3)
        b2b["n"] += 1
        b2b["ok"] += int(bool(row) and str(row.get("status")) == "success")
    record(A, "back-to-back burst (8 dictations, 0.3 s tail, no pause)", "ok" if b2b["ok"] == b2b["n"] else "fail", json.dumps(b2b))
    # Polish off.
    api("/api/voice-flow-polish/update", {"polishing_enabled": False})
    off = run_set(A, files, ["period_word", "stutter2", "spoken_punct", "email", "apostrophe"], "polish-off", "api", te)
    api("/api/voice-flow-polish/update", {"polishing_enabled": True})
    # Dictionary.
    adds = [api("/api/dictionary/add", {"word": w}) for w in ("Uzair", "Kayat", "Ananya")]
    hp = api("/api/dictionary/add", {"word": "Priya", "heard_as": "Pria"})
    bad = [api("/api/dictionary/add", {"word": w}) for w in ("the", "Hey", "React")]
    record(A, "dictionary add names / heard-as / refused words", "info",
           f"adds={[a[0] for a in adds]} heard_as={hp[0]} {str(hp[1])[:200]}\nrefused-check: {[(b[0], str(b[1])[:120]) for b in bad]}")
    d = run_set(A, files, ["names1", "names2", "react_word", "long1"], "dictionary-on", "api", te)
    # History via the real UI: apostrophes render, no JS errors.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.webkit.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.goto("http://127.0.0.1:8991/index.html")
            pg.wait_for_timeout(5000)
            pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} try { switchPage('home'); } catch(e){} }")
            pg.wait_for_timeout(2500)
            p = SHOTS_PATH = str(EV / "shots" / "history-home-webkit.png")
            pg.screenshot(path=p, full_page=True)
            txt = pg.evaluate("() => (document.getElementById('page-home')||document.body).innerText")
            has = "don't" in txt or "don’t" in txt or "Uzair's" in txt or "It's" in txt
            record(A, "History in the UI shows apostrophe dictations without JS errors", "ok" if has and not errs else "fail",
                   f"apostrophe text visible={has}; js errors={errs[:5]}", "qa/shots/history-home-webkit.png")
            b.close()
    except Exception as exc:
        record(A, "History UI check", "error", repr(exc))
    n = net.stop()
    r = rss.stop()
    ips = sorted({x.split(":")[0] for v in n["pktap"].values() for x in v if not x.startswith("dns:")})[:30]
    record(A, "network during local-only dictation", "info",
           f"lsof app connections: {n['lsof_remote']}\npktap: {json.dumps(n['pktap'])[:2500]}\nrdns: {json.dumps(resolve_ips(ips))[:1200]}", "qa/net-voice-local-summary.json")
    record(A, "RAM/CPU during dictation (bundled STT)", "info", json.dumps(r)[:2500])
    # Permissions: reset TCC for the bundle and see what the app reports + what a dictation does.
    rc, out = sh(f"tccutil reset Microphone {BUNDLE_ID}; tccutil reset Accessibility {BUNDLE_ID}; tccutil reset ListenEvent {BUNDLE_ID}")
    time.sleep(2)
    perm = api("/api/platform/permissions")[1]
    row, _ = dictate("short1", files["short1"][0], "api")
    record(A, "after tccutil reset (mic/AX/Input Monitoring) for the bundle id", "info",
           f"tccutil: {out.strip()[:300]}\nreport: {json.dumps(perm)[:900]}\nnext dictation: {json.dumps(row, default=str)[:600]}", shot("after-tcc-reset"))
    lg = sh("ls -la ~/.voice_flow/logs; grep -hiE 'permission|accessib|microphone|paste|TCC' ~/.voice_flow/logs/*.log | tail -40", quiet=True)[1]
    save("voice-a-permission-log-lines.txt", lg)
    q = quit_app()
    record(A, "quit after voice tests", "ok" if q["all_gone"] else "fail", json.dumps(q))
    kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; "
       f"grep -rn windll ~/.voice_flow/logs | head", quiet=True)


def wait_download(model_id: str, timeout: float, area: str, label: str) -> dict:
    t = time.time()
    last = {}
    while time.time() - t < timeout:
        code, st = api(f"/api/downloadable-models/status?model_id={model_id}")
        if code != 200:
            code, lst = api("/api/downloadable-models/list")
            st = next((m for m in (lst.get("models") if isinstance(lst, dict) else lst) or [] if isinstance(m, dict) and m.get("id") == model_id), lst)
        last = st if isinstance(st, dict) else {"raw": st}
        flat = json.dumps(last).lower()
        m = last.get("model", last) if isinstance(last, dict) else {}
        status = str(m.get("status") or m.get("state") or "")
        if status in ("downloaded", "ready", "installed", "completed") or m.get("downloaded") is True:
            break
        if status in ("error", "failed", "cancelled"):
            break
        time.sleep(3)
    last["_elapsed_s"] = round(time.time() - t, 1)
    return last


def dl_status(st) -> str:
    m = st.get("model", st) if isinstance(st, dict) else {}
    return str(m.get("status") or "") if isinstance(m, dict) else ""


def phase_b():
    A = "models"
    mic = setup_audio(A)
    files = make_clips(A)
    if not start_app_fresh(A):
        return
    select_mic(A, mic)
    rc, df = sh("df -h ~ | tail -1", quiet=True)
    record(A, "free disk before downloads", "info", df.strip())
    code, lst = api("/api/downloadable-models/list")
    save("models-list.json", json.dumps(lst, indent=2))
    record(A, "downloadable models list", "ok" if code == 200 else "fail", json.dumps(lst)[:1500], "qa/models-list.json")
    net = NetCapture("downloads").start()
    rss = RssSampler().start()
    nid = "nvidia/nemotron-speech-streaming-en-0.6b"
    t = time.time()
    r = api("/api/downloadable-models/download", {"model_id": nid})
    st = wait_download(nid, 600, A, "nemotron")
    record(A, "download Nemotron 0.6B in the app", "ok" if dl_status(st) == "downloaded" else "fail",
           f"start={r}\nfinal={json.dumps(st)[:800]}")
    # S1 with a network cut mid-download, then retry.
    sid = "superwhisper/s1-mini-q4_k_m"
    api("/api/downloadable-models/download", {"model_id": sid})
    blocked_ips = []
    t0 = time.time()
    while time.time() - t0 < 90:
        st = api(f"/api/downloadable-models/status?model_id={sid}")[1]
        done = json.dumps(st)
        m = re.search(r'"downloaded_bytes": (\d+)', done)
        if m and int(m.group(1)) > 40_000_000:
            break
        time.sleep(1)
    pids = ",".join(str(r["pid"]) for r in app_tree())
    lo = sh(f"lsof -nP -iTCP -sTCP:ESTABLISHED -a -p {pids}", quiet=True)[1]
    for line in lo.splitlines():
        mm = re.search(r"->([0-9.]+):443", line)
        if mm:
            blocked_ips.append(mm.group(1))
    for host in ("huggingface.co", "cdn-lfs.hf.co", "cdn-lfs-us-1.hf.co", "cas-bridge.xethub.hf.co", "cas-server.xethub.hf.co", "transfer.xethub.hf.co"):
        rc, o = sh(f"dig +short {host} | grep -E '^[0-9.]+$'", quiet=True)
        blocked_ips += o.split()
    blocked_ips = sorted(set(blocked_ips) - {"127.0.0.1"})
    Path("/tmp/pf.conf").write_text("".join(f"block drop out quick proto tcp from any to {ip}\n" for ip in blocked_ips))
    rc, pf = sh("sudo pfctl -E -f /tmp/pf.conf 2>&1 | tail -3; sudo pfctl -s rules | head -5")
    before_cut = api(f"/api/downloadable-models/status?model_id={sid}")[1]
    time.sleep(85)
    during = api(f"/api/downloadable-models/status?model_id={sid}")[1]
    s_cut = shot("download-network-cut")
    record(A, "S1 download: cut network mid-download (pf block of the download hosts for 85 s)", "info",
           f"blocked {len(blocked_ips)} IPs: {blocked_ips[:12]}\npf: {pf.strip()[:400]}\nbefore: {json.dumps(before_cut)[:500]}\nafter 85s: {json.dumps(during)[:700]}", s_cut)
    sh("sudo pfctl -F rules 2>&1; sudo pfctl -d 2>&1", quiet=True)
    time.sleep(5)
    st_mid = api(f"/api/downloadable-models/status?model_id={sid}")[1]
    retry = api("/api/downloadable-models/download", {"model_id": sid})
    st = wait_download(sid, 600, A, "s1")
    size = sh("ls -la ~/.voice_flow/models 2>/dev/null; find ~/.voice_flow -name '*.gguf' -exec ls -la {} \\; ; find ~/.voice_flow -name '*.part' -o -name '*.tmp' | head", quiet=True)[1]
    ok = dl_status(st) == "downloaded"
    record(A, "S1 download retry after the network comes back", "ok" if ok else "fail",
           f"status after unblock: {json.dumps(st_mid)[:400]}\nretry -> {retry}\nfinal: {json.dumps(st)[:600]}\nfiles:\n{size[:1500]}")
    n = net.stop()
    record(A, "network during model downloads", "info", f"lsof: {n['lsof_remote'][:40]}\npktap: {json.dumps(n['pktap'])[:2000]}", "qa/net-downloads-summary.json")
    # Nemotron dictations.
    r1 = api("/api/voice-flow-stt/update", {"model_id": "local/nemotron-speech-streaming-en-0.6b"})
    record(A, "select Nemotron as speech model", "ok" if r1[0] == 200 else "fail", str(r1))
    time.sleep(15)
    te = textedit_open(A)
    net2 = NetCapture("nemotron-s1-local").start()
    ids = [s[0] for s in SENTENCES][:20]
    stats_n = run_set(A, files, ids, "nemotron-polish-deterministic", "api", te)
    # S1 polish.
    r2 = api("/api/voice-flow-polish/update", {"polishing_enabled": True, "model": "local/s1-mini-q4_k_m"})
    record(A, "select S1-mini as polish model", "ok" if r2[0] == 200 else "fail", str(r2))
    llama_counts = []
    s1ids = ["stutter1", "stutter2", "period_word", "spoken_punct", "names1", "long1", "apostrophe", "email", "summarize", "short3"]
    rows = []
    for cid in s1ids:
        row_stats = run_set(A, files, [cid], f"s1-{cid}", "api", te)
        llama_counts.append(count_llama())
    record(A, "llama-server count after each S1 dictation", "ok" if max(llama_counts or [0]) <= 1 else "fail",
           f"counts={llama_counts}; peak seen by sampler={rss.max_llama}\n{fmt_rows([r for r in ps_rows() if 'llama-server' in r['cmd']])}")
    n2 = net2.stop()
    ips = sorted({x.split(":")[0] for v in n2["pktap"].values() for x in v if not x.startswith("dns:")})[:30]
    record(A, "network during Nemotron + S1 local dictation", "info",
           f"lsof: {n2['lsof_remote']}\npktap: {json.dumps(n2['pktap'])[:2000]}\nrdns: {json.dumps(resolve_ips(ips))[:1000]}", "qa/net-nemotron-s1-local-summary.json")
    # Cloud model without a key.
    c1 = api("/api/voice-flow-polish/update", {"polishing_enabled": True, "model": "gemini/gemini-2.5-flash"})
    c2 = api("/api/voice-flow-stt/update", {"model_id": "groq/whisper-large-v3"})
    row, _ = dictate("short1", files["short1"][0], "api")
    st_overlay = api("/api/overlay/status")[1]
    record(A, "cloud polish / cloud STT selected without any key", "info",
           f"polish select -> {c1}\nstt select -> {c2}\ndictation -> {json.dumps(row, default=str)[:900]}\noverlay={st_overlay}", shot("cloud-no-key"))
    api("/api/voice-flow-stt/update", {"model_id": "local/nemotron-speech-streaming-en-0.6b"})
    api("/api/voice-flow-polish/update", {"polishing_enabled": True, "model": "local/s1-mini-q4_k_m"})
    r = rss.stop()
    record(A, "RAM/CPU peak (downloads + Nemotron + S1)", "info", json.dumps(r)[:3000])
    save("rss-samples.json", json.dumps(r, indent=2))
    # Quit cleanliness, then kill -9.
    before = fmt_rows(app_tree())
    q = quit_app(45)
    record(A, "normal Quit with Nemotron worker + llama-server running: leftovers", "ok" if q["all_gone"] else "fail",
           f"before:\n{before}\nafter: {json.dumps(q)}")
    kill_all()
    launch_open(APP)
    wait_api(120)
    time.sleep(10)
    row, _ = dictate("long1", files["long1"][0], "api")
    tree = app_tree()
    record(A, "relaunch + one S1 dictation (process tree)", "info", f"{json.dumps(row, default=str)[:400]}\n{fmt_rows(tree)}")
    main = [r for r in tree if "Contents/MacOS" in r["cmd"]]
    for r_ in main:
        sh(f"kill -9 {r_['pid']}", quiet=True)
    time.sleep(20)
    left = app_tree()
    record(A, "after kill -9 of the main app process: orphans (llama-server/worker)", "ok" if not left else "fail",
           fmt_rows(left) + f"\nllama-server count={count_llama()}\nport 8080: {sh('lsof -nP -iTCP:8080 -sTCP:LISTEN', quiet=True)[1].strip() or 'free'}")
    kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/", quiet=True)


def main(which: str):
    install_watchdog(32)
    try:
        phase_a() if which == "voice_a" else phase_b()
    except BaseException:
        import traceback
        record("voice", "phase crashed / watchdog", "error", traceback.format_exc()[-2000:])
        try:
            kill_all()
            sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/", quiet=True)
        except Exception:
            pass
    finish(which)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "voice_a")
