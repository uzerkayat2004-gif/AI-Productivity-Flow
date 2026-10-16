"""Phase AF: Audio Flow on Mac from a clean start: can a user trigger Read/Summary from selected text,
and do Play/Download in Audio Summary History work for a title with apostrophes."""
from __future__ import annotations

import json
import shlex
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from qa_common import (EV, HOME, record, sh, api, wait_api, shot, app_tree, fmt_rows, helper,
                       launch_open, kill_all, wipe_user_data, finish, install_watchdog)

A = "audioflow"
APP = "/Applications/AI Productivity Flow.app"
BASE = "http://127.0.0.1:8991"


def appwins():
    try:
        return [w for w in json.loads(helper("windows") or "[]") if "Productivity" in str(w.get("owner"))]
    except Exception:
        return []


def main():
    install_watchdog(25)
    try:
        kill_all()
        wipe_user_data()
        launch_open(APP)
        wait_api(120)
        time.sleep(12)
        api("/api/settings/update", {"key": "has_viewed_onboarding", "value": True})
        record(A, "settings relevant to Audio Flow", "info",
               f"audio_flow_enabled={api('/api/settings/get?key=audio_flow_enabled')[1]} default_mode={api('/api/settings/get?key=exec_audio_flow_default_mode')[1]} overlay={api('/api/overlay/status')[1]}")
        text = ("Photosynthesis is how plants turn sunlight, water and carbon dioxide into sugar and oxygen. "
                "It happens in the chloroplasts. The Calvin cycle then builds glucose. ") * 3
        Path("/tmp/af.txt").write_text(text)
        sh("open -a TextEdit /tmp/af.txt; sleep 5", quiet=True)
        te = [w for w in json.loads(helper("windows") or "[]") if w.get("owner") == "TextEdit" and w.get("h", 0) > 100]
        before = appwins()
        if te:
            w = te[0]
            helper("drag", str(w["x"] + 12), str(w["y"] + 62), str(w["x"] + w["w"] - 40), str(w["y"] + 110))
            time.sleep(3)
            s1 = shot("af-after-drag-selection")
            after = appwins()
            ov = api("/api/overlay/status")[1]
            new = [x for x in after if x not in before]
            record(A, "select text with the mouse in TextEdit: does a Listen button / widget appear?", "ok" if new else "fail",
                   f"overlay={ov}\nnew app windows after selection={new}\nall app windows={after}", s1)
            bars = [x for x in after if x.get("h", 0) < 140]
            if bars:
                b = min(bars, key=lambda x: x["w"] * x["h"])
                helper("move", str(b["x"] + b["w"] / 2), str(b["y"] + b["h"] / 2))
                time.sleep(2)
                s2 = shot("af-bar-hover-after-selection")
                record(A, "hover the floating bar with text selected", "info", f"windows={appwins()}", s2)
                bars2 = [x for x in appwins() if x.get("h", 0) < 140]
                big = max(bars2, key=lambda x: x["w"] * x["h"]) if bars2 else b
                helper("click", str(big["x"] + big["w"] / 2), str(big["y"] + big["h"] / 2))
                time.sleep(4)
                ov2 = api("/api/overlay/status")[1]
                s3 = shot("af-after-bar-click")
                record(A, "click the floating bar with text selected (Windows: reads the selection)", "ok" if "READ" in json.dumps(ov2) else "fail",
                       f"overlay after click={ov2} (RECORDING = it started dictation instead of reading)", s3)
                time.sleep(2)
                api("/api/record/toggle", {"recording": False})
                helper("key", "53")  # Esc
                time.sleep(4)
        lg = sh("grep -hiE 'MOUSE HOOK|AUDIO FLOW|selection|Select text' ~/.voice_flow/logs/*.log | tail -20", quiet=True)[1]
        record(A, "log lines about selection / Audio Flow", "info", lg.strip() or "(none)")
        sh("killall TextEdit 2>/dev/null; true", quiet=True)
        # History item with apostrophes, audio in the real media folder.
        media = HOME / ".voice_flow" / "audio_summaries"
        media.mkdir(parents=True, exist_ok=True)
        mp3 = media / "qa-apostrophe.mp3"
        sh(f"{sys.executable} -m pip install -q edge-tts >/dev/null 2>&1; {sys.executable} -m edge_tts --text \"It's Uzair's summary test.\" --write-media {shlex.quote(str(mp3))}", timeout=120)
        sid = "qa-" + uuid.uuid4().hex[:8]
        title = "It's Uzair's notes — don't skip"
        db = sh("find ~/.voice_flow -name 'voice_flow.db' | head -1", quiet=True)[1].strip()
        con = sqlite3.connect(db)
        con.execute("insert into audio_summary_history (id,title,text_snippet,full_text,depth,audio_path,duration_sec,status,progress,created_at) values (?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (sid, title, "It's a test", "It's a test", "balanced", str(mp3), 3.0, "ready", 100))
        con.commit()
        con.close()
        record(A, "seeded Audio Summary History item", "info", f"id={sid} title={title!r} mp3 exists={mp3.exists()} size={mp3.stat().st_size if mp3.exists() else 0}")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = __import__('qa_browser').launch(pw)
            ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
            pg = ctx.new_page()
            errs, reqs = [], []
            pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("request", lambda r: reqs.append(r.method + " " + r.url.replace(BASE, "")) if "audio" in r.url else None)
            pg.goto(BASE + "/index.html")
            pg.wait_for_timeout(6000)
            pg.evaluate("() => { try { finishOnboarding(); } catch(e){} try { stopAudioFlowGuide(); } catch(e){} try { switchPage('audioflow'); } catch(e){} }")
            pg.wait_for_timeout(2000)
            pg.evaluate("() => { const h=[...document.querySelectorAll('#page-audioflow *')].find(e=>/Audio Summary History/.test(e.textContent||'') && e.children.length<6 && e.getBoundingClientRect().height>0); h && h.click(); }")
            pg.wait_for_timeout(2500)
            pg.screenshot(path=str(EV / "shots" / "af-history-open.png"))
            visible = pg.evaluate("() => document.getElementById('page-audioflow').innerText.includes(\"Uzair\")")
            e0 = len(errs)
            ok_play = pg.evaluate("""() => { const b=[...document.querySelectorAll('[onclick^=playAudioSummary]')][0]; if (!b) return 'no play button'; b.click(); return b.getAttribute('onclick'); }""")
            pg.wait_for_timeout(5000)
            s4 = shot("af-native-after-play")
            dl_res = None
            try:
                with pg.expect_download(timeout=15000) as d:
                    pg.evaluate("() => { const b=[...document.querySelectorAll('[onclick^=downloadAudioSummary]')][0]; b && b.click(); }")
                dl_res = d.value.suggested_filename
            except Exception as exc:
                dl_res = "no browser download event: " + str(exc).splitlines()[0][:150]
            pg.wait_for_timeout(4000)
            pg.screenshot(path=str(EV / "shots" / "af-history-after-play-download.png"))
            toasts = pg.evaluate("() => [...document.querySelectorAll('[class*=toast]')].map(t=>t.innerText.trim()).filter(Boolean).slice(-4)")
            dls = sh("ls -la ~/Downloads | grep -i -E 'uzair|summary|mp3' ", quiet=True)[1]
            players = [w for w in appwins() if w.get("h", 0) > 150]
            record(A, "Audio Summary History with apostrophe title: Play + Download", "ok" if not errs[e0:] and ("player" in json.dumps(reqs) or players) else "fail",
                   f"title visible={visible}; play onclick={ok_play}\nrequests={reqs[-8:]}\njs errors={errs[e0:][:4]}\ndownload={dl_res}\ntoasts={toasts}\n~/Downloads: {dls.strip()}\napp windows={players}",
                   "qa/shots/af-history-after-play-download.png")
            b.close()
        sh("pkill -f audio_summary_player; true", quiet=True)
        kill_all()
    except BaseException:
        import traceback
        record(A, "phase crashed", "error", traceback.format_exc()[-1500:])
        kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; true", quiet=True)
    finish("af")


if __name__ == "__main__":
    main()
