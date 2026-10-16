"""Phase UI: original walkthrough (tour, guides, pages, settings, bar) + onboarding persistence,
Video Flow Mac gate everywhere, Audio Flow on Mac (selection trigger, voices, summaries, history
with apostrophes), NotebookLM page, permissions UI."""
from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

from qa_common import (EV, OUT, HOME, BUNDLE_ID, record, sh, save, api, wait_api, shot, app_tree, fmt_rows, helper,
                       launch_open, quit_app, kill_all, finish, install_watchdog, log)

A = "ui"
APP = os.environ.get("APP_PATH", "/Applications/AI Productivity Flow.app")
BASE = "http://127.0.0.1:8991"


def run_original():
    t = time.time()
    p = subprocess.run([sys.executable, str(Path(__file__).with_name("walkthrough_orig.py")), str(OUT), str(OUT / "apf-native")],
                       capture_output=True, text=True, timeout=22 * 60)
    (EV / "walkthrough-orig-stdout.txt").write_text(p.stdout + "\n" + p.stderr)
    summ = (OUT / "SUMMARY.md").read_text() if (OUT / "SUMMARY.md").exists() else ""
    counts = re.search(r"counts: (.*)", summ)
    fails = [l for l in summ.splitlines() if "| fail |" in l or "| error |" in l or "| js-error |" in l]
    record(A, "original walkthrough (tour, guides, pages, settings, dialogs, floating bar)", "ok" if not fails else "fail",
           f"took {time.time()-t:.0f}s; counts {counts.group(1) if counts else '?'}\nfailed rows:\n" + "\n".join(fails)[:2500], "SUMMARY.md")


def page_ctx(pw, fresh=True):
    b = pw.webkit.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 860})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    return b, pg, errs


def pshot(pg, label):
    name = f"ui-{re.sub(r'[^A-Za-z0-9_-]+', '-', label)[:60]}.png"
    try:
        pg.screenshot(path=str(EV / "shots" / name), full_page=False)
    except Exception:
        pass
    return f"qa/shots/{name}"


def onboarding_persistence(pw):
    flags = api("/api/settings/get?key=onboarding_seen_flags")[1]
    ob = api("/api/onboarding/status")[1]
    record(A, "onboarding flags saved in the backend after the walkthrough", "info", f"flags={flags}\nonboarding/status={ob}")
    # A brand-new WebView profile (empty localStorage) must not replay the tour/guides.
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(9000)
    st = pg.evaluate("""() => ({tour: !!document.getElementById('onboarding-overlay') && !document.getElementById('onboarding-overlay').classList.contains('hidden'),
        guide: document.body.classList.contains('af-guide-active') || !!document.querySelector('.vf-guide-active, body.vf-guide-active')})""")
    s = pshot(pg, "fresh-webview-profile-after-onboarding")
    record(A, "fresh WebView profile: tour and guides stay dismissed (flags come from backend)", "ok" if not st["tour"] and not st["guide"] else "fail",
           f"{st} js_errors={errs[:3]}", s)
    b.close()
    # Real restart: native window must not show the tour again.
    q = quit_app()
    if not q["all_gone"]:
        kill_all()
    launch_open(APP)
    up = wait_api(120)
    time.sleep(20)
    s2 = shot("native-after-restart-no-tour")
    flags2 = api("/api/settings/get?key=onboarding_seen_flags")[1]
    record(A, "after app restart: native window (tour should not reappear)", "info", f"api={up}s flags={flags2}", s2)
    # Replay from sidebar then Skip, restart again, seen flags persist.
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(6000)
    pg.evaluate("() => { try { replayOnboarding(); } catch(e){} }")
    pg.wait_for_timeout(2000)
    s3 = pshot(pg, "replay-tour")
    pg.evaluate("() => { const b=document.querySelector('#onboarding-overlay .scene1-skip-badge'); b && b.click(); }")
    pg.wait_for_timeout(2500)
    vis = pg.evaluate("() => !document.getElementById('onboarding-overlay').classList.contains('hidden')")
    record(A, "Replay tour then Skip", "ok" if not vis else "fail", f"tour visible after skip={vis}; errors={errs[:3]}", s3)
    b.close()


def video_gate(pw):
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(6000)
    pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} }")
    side = pg.evaluate("""() => { const n=document.querySelector('.sidebar .nav-item[data-page=videoflow]'); if(!n) return null;
        const s=getComputedStyle(n); return {text:n.innerText.trim(), cls:n.className, opacity:s.opacity, title:n.title||n.getAttribute('aria-label')||'', disabled:n.getAttribute('aria-disabled')}; }""")
    s1 = pshot(pg, "sidebar-video-flow-item")
    record(A, "Video Flow gate: sidebar item", "info", json.dumps(side), s1)
    pg.evaluate("() => { try { switchPage('videoflow'); } catch(e){} }")
    pg.wait_for_timeout(2500)
    txt = pg.evaluate("() => (document.getElementById('page-videoflow')||document.body).innerText")
    s2 = pshot(pg, "video-flow-page-banner")
    has_note = "coming to Mac soon" in txt
    record(A, "Video Flow gate: page banner on Mac", "ok" if has_note else "fail", txt[:600], s2)
    btn = pg.evaluate("() => { const b=document.getElementById('vf-generate-button'); return b ? {disabled:b.disabled, text:b.innerText.trim()} : null; }")
    pg.evaluate("() => { try { generateVideoFlow(); } catch(e){} }")
    pg.wait_for_timeout(3000)
    toasts = pg.evaluate("() => [...document.querySelectorAll('[class*=toast]')].map(t=>t.innerText.trim()).filter(Boolean).slice(-3)")
    jobs = api("/api/video-flow/jobs/status")[1]
    record(A, "Video Flow gate: Create button / generate", "ok" if (not btn or btn.get("disabled")) or "Mac" in json.dumps(toasts) else "info",
           f"button={btn} toasts={toasts} jobs={str(jobs)[:300]} js_errors={errs[:3]}", pshot(pg, "video-flow-generate-attempt"))
    # Tour card about Video Flow.
    pg.evaluate("() => { try { replayOnboarding(); } catch(e){} }")
    found = None
    for i in range(6):
        pg.evaluate(f"() => {{ try {{ gotoOnboardingSlide({i}); }} catch(e){{}} }}")
        pg.wait_for_timeout(1500)
        t = pg.evaluate("() => document.getElementById('onboarding-overlay').innerText")
        if "Video" in t and ("Mac" in t):
            found = (i, t[:500])
            break
    s3 = pshot(pg, "tour-video-card")
    record(A, "Video Flow gate: tour card mentions Mac", "ok" if found else "fail", str(found), s3)
    pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} }")
    b.close()


def audio_flow(pw):
    # Voices list and online labels.
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(6000)
    pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} try { switchPage('audioflow'); } catch(e){} }")
    pg.wait_for_timeout(2500)
    s0 = pshot(pg, "audio-flow-page")
    pg.evaluate("() => { try { openAudioVoiceModelPicker(); } catch(e){} }")
    pg.wait_for_timeout(2500)
    voices_txt = pg.evaluate("() => [...document.querySelectorAll('[id*=picker], [class*=picker], [id*=modal]')].filter(e=>e.getBoundingClientRect().height>0).map(e=>e.innerText).join('\\n---\\n').slice(0, 6000)")
    s1 = pshot(pg, "audio-voice-picker")
    save("audio-voice-picker.txt", voices_txt)
    online = len(re.findall(r"online", voices_txt, re.I))
    record(A, "Audio Flow voice picker: online voices labelled", "ok" if online else "fail",
           f"'online' labels found={online}; text head:\n{voices_txt[:1200]}", s1)
    pg.keyboard.press("Escape")
    b.close()
    # Summary through the local deterministic model (no network).
    text = ("Photosynthesis is how plants turn sunlight, water and carbon dioxide into sugar and oxygen. "
            "It happens in the chloroplasts. The light reactions make ATP and NADPH. The Calvin cycle then uses them "
            "to build glucose. Without photosynthesis, there would be almost no oxygen in the air.") * 2
    code, body = api("/api/audio-summary/test", {"text": text, "depth": "standard"}, timeout=90)
    record(A, "Audio Flow summary (local default model)", "ok" if code == 200 and isinstance(body, dict) and body.get("summary") else "fail",
           f"{code} {json.dumps(body)[:900]}")
    # Real trigger on Mac: select text in TextEdit with the mouse, then click the floating bar.
    Path("/tmp/af.txt").write_text("Audio Flow test paragraph. " + text)
    sh("killall TextEdit 2>/dev/null; sleep 1; open -a TextEdit /tmp/af.txt; sleep 5", quiet=True)
    wins = json.loads(helper("windows") or "[]")
    te = [w for w in wins if w.get("owner") == "TextEdit" and w.get("h", 0) > 100]
    note = "no TextEdit window"
    if te:
        w = te[0]
        x1, y1 = w["x"] + 20, w["y"] + 70
        helper("drag", str(x1), str(y1), str(w["x"] + w["w"] - 30), str(y1 + 60))
        time.sleep(2.5)
        s2 = shot("after-mouse-text-selection-in-TextEdit")
        ov = api("/api/overlay/status")[1]
        bars = [x for x in json.loads(helper("windows") or "[]") if x.get("owner") == "AI Productivity Flow" and x.get("h", 0) < 140 and x.get("layer", 0) != 25]
        note = f"overlay after selection={ov}\napp small windows={bars}"
        record(A, "Audio Flow on Mac: select text with the mouse (should offer Listen)", "info", note, s2)
        # Cmd+A then click the bar's speak zone.
        helper("key", "0", "cmd")
        time.sleep(1)
        bar = min(bars, key=lambda x: x["w"] * x["h"]) if bars else None
        if bar:
            helper("move", str(bar["x"] + bar["w"] / 2), str(bar["y"] + bar["h"] / 2))
            time.sleep(1.5)
            bars2 = [x for x in json.loads(helper("windows") or "[]") if x.get("owner") == "AI Productivity Flow" and x.get("h", 0) < 140 and x.get("layer", 0) != 25]
            big = max(bars2, key=lambda x: x["w"] * x["h"]) if bars2 else bar
            s3 = shot("bar-hover-with-selection")
            helper("click", str(big["x"] + big["w"] / 2), str(big["y"] + big["h"] / 2))
            time.sleep(6)
            s4 = shot("after-click-bar-with-selection")
            ov2 = api("/api/overlay/status")[1]
            af_hist = api("/api/audio-flow/history")[1]
            lg = sh("grep -hE 'AUDIO FLOW|MOUSE HOOK|Select text|Audio Flow' ~/.voice_flow/logs/*.log | tail -15", quiet=True)[1]
            record(A, "Audio Flow on Mac: Cmd+A selection + click floating bar", "info",
                   f"overlay={ov2}\naudio history={json.dumps(af_hist)[:500]}\nlog lines:\n{lg}", s4)
            api("/api/record/toggle", {"recording": False})
    lg = sh("grep -hE 'MOUSE HOOK|mouse hook' ~/.voice_flow/logs/*.log | tail -5", quiet=True)[1]
    record(A, "mouse-selection hook status on Mac (log)", "info", lg.strip() or "no MOUSE HOOK lines")
    sh("killall TextEdit 2>/dev/null; true", quiet=True)


def audio_history_apostrophes(pw):
    db = sh("find ~/.voice_flow -name '*.db' -size +10k | head -5", quiet=True)[1].split()
    mp3 = EV / "af-sample.mp3"
    sh(f"{sys.executable} -m pip install -q edge-tts >/dev/null 2>&1; {sys.executable} -m edge_tts --text \"It's Uzair's summary test.\" --write-media {shlex.quote(str(mp3))}", timeout=120)
    if not mp3.exists():
        sh(f"say -o /tmp/af.aiff \"It's Uzair's summary test\"; afconvert -f mp4f -d aac /tmp/af.aiff {shlex.quote(str(EV / 'af-sample.m4a'))}", quiet=True)
        mp3 = EV / "af-sample.m4a"
    dest = HOME / ".voice_flow" / "qa_audio"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / mp3.name
    sh(f"cp {shlex.quote(str(mp3))} {shlex.quote(str(target))}", quiet=True)
    sid = "qa-" + uuid.uuid4().hex[:8]
    inserted = []
    for path in db:
        try:
            con = sqlite3.connect(path)
            tabs = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            if "audio_summary_history" in tabs:
                con.execute("insert into audio_summary_history (id,title,text_snippet,full_text,depth,audio_path,duration_sec,status,progress,created_at) values (?,?,?,?,?,?,?,?,?,datetime('now'))",
                            (sid, "It's Uzair's notes — don't skip", "It's a test", "It's a test", "balanced", str(target), 3.0, "ready", 100))
                con.commit()
                inserted.append(path)
            con.close()
        except Exception as exc:
            inserted.append(f"{path}: {exc}")
    record(A, "seed one Audio Flow history item with apostrophes in the title", "info", f"db={inserted} audio={target}")
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(6000)
    pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} try { switchPage('audioflow'); } catch(e){} }")
    pg.wait_for_timeout(3000)
    txt = pg.evaluate("() => document.getElementById('page-audioflow').innerText")
    shown = "Uzair" in txt
    s = pshot(pg, "audio-history-apostrophe")
    btns = pg.evaluate("""() => [...document.querySelectorAll('#page-audioflow button, #page-audioflow [onclick]')].filter(b=>b.getBoundingClientRect().width>0)
        .map(b=>({t:(b.innerText||b.title||b.getAttribute('aria-label')||'').trim().slice(0,30), oc:(b.getAttribute('onclick')||'').slice(0,120)})).filter(x=>/play|download/i.test(x.t+x.oc)).slice(0,6)""")
    before = len(errs)
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url) if "audio" in r.url else None)
    for kind in ("play", "download"):
        pg.evaluate(f"""() => {{ const b=[...document.querySelectorAll('#page-audioflow button, #page-audioflow [onclick]')].find(b=>b.getBoundingClientRect().width>0 && /{kind}/i.test((b.innerText||'')+(b.title||'')+(b.getAttribute('aria-label')||'')+(b.getAttribute('onclick')||'')));
            b && b.click(); }}""")
        pg.wait_for_timeout(3500)
    s2 = pshot(pg, "audio-history-after-play-download")
    play_api = api("/api/audio-flow/history/play", {"id": sid})
    record(A, "Audio Flow history: apostrophe title renders, Play/Download work", "ok" if shown and len(errs) == before and reqs else "fail",
           f"shown={shown} buttons={btns} new_js_errors={errs[before:][:4]} audio requests={reqs[:6]} play api={str(play_api)[:300]}", s2)
    med = api(f"/api/audio-flow/summary/media?id={sid}")
    record(A, "Audio Flow media endpoint for the item", "ok" if med[0] == 200 else "fail", str(med)[:300])
    time.sleep(3)
    shot("native-after-audio-play")
    sh("pkill -f audio_summary_player 2>/dev/null; true", quiet=True)
    # NotebookLM settings.
    pg.evaluate("() => { try { openSettings('account'); } catch(e){} }")
    pg.wait_for_timeout(1500)
    nlm = pg.evaluate("() => [...document.querySelectorAll('*')].filter(e=>/NotebookLM/i.test(e.innerText||'') && e.children.length<4 && e.getBoundingClientRect().height>0).map(e=>e.innerText.trim()).slice(0,6)")
    s3 = pshot(pg, "settings-account-notebooklm")
    st = api("/api/video-flow/notebooklm/status")
    record(A, "NotebookLM settings visible / status API", "info", f"ui snippets={nlm} status={str(st)[:400]} js_errors={errs[-3:]}", s3)
    b.close()


def permissions_ui(pw):
    b, pg, errs = page_ctx(pw)
    pg.goto(BASE + "/index.html")
    pg.wait_for_timeout(6000)
    pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} }")
    pg.evaluate("(() => { const m=document.getElementById('vf-macos-permissions-modal'); try { initMacOSPermissionsOnboarding(); } catch(e){} setTimeout(()=>{ if (m) m.style.display='flex'; }, 800); })()")
    pg.wait_for_timeout(2500)
    t = pg.evaluate("() => { const m=document.getElementById('vf-macos-permissions-modal'); return m ? m.innerText : 'missing'; }")
    s = pshot(pg, "macos-permissions-dialog")
    record(A, "macOS permissions dialog content", "info", t[:1200], s)
    b.close()
    rc, out = sh(f"tccutil reset All {BUNDLE_ID}")
    rep = api("/api/platform/permissions")[1]
    record(A, "permission report after tccutil reset All <bundle id>", "info", f"{out.strip()[:200]}\n{json.dumps(rep)[:1000]}")


def main():
    install_watchdog(33)
    try:
        run_original()
    except Exception:
        import traceback
        record(A, "original walkthrough", "error", traceback.format_exc()[-1500:])
    # The original walkthrough may have restarted the app; make sure it is up.
    if wait_api(5) is None:
        launch_open(APP)
        wait_api(120)
        time.sleep(10)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        for fn in (video_gate, audio_flow, audio_history_apostrophes, permissions_ui, onboarding_persistence):
            try:
                log(f"=== {fn.__name__}")
                fn(pw)
            except BaseException:
                import traceback
                record(A, fn.__name__, "error", traceback.format_exc()[-1500:])
                if "watchdog" in traceback.format_exc():
                    break
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; true", quiet=True)
    wd = sh("grep -rn windll ~/.voice_flow/logs | head -20", quiet=True)[1]
    record(A, "no windll errors in logs after UI walkthrough", "ok" if not wd.strip() else "fail", wd.strip()[:1500] or "0 matches")
    finish("ui")


if __name__ == "__main__":
    main()
