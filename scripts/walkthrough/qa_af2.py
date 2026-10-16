"""Phase AF2 (fix/mac-audio-flow verification): Audio Flow end to end on a real Mac.

Select text in TextEdit -> Listen widget appears -> Read plays (afplay) -> hotkey stop/read ->
floating bar click reads the selection -> Summary job submitted -> paste honesty with and
without Accessibility. TCC is pre-approved for the bundle id like the voice phases do."""
from __future__ import annotations

import json
import shlex
import time
from pathlib import Path

from qa_common import (EV, BUNDLE_ID, record, sh, api, wait_api, shot, helper, launch_open, kill_all,
                       wipe_user_data, finish, install_watchdog, save)
import qa_voice

A = "audioflow"
APP = "/Applications/AI Productivity Flow.app"
PY = f"{APP}/Contents/Resources/runtime/python/bin/python3"
PYPATH = f"{APP}/Contents/Resources/src:{APP}/Contents/Resources/runtime/site-packages"
TEXT = ("Photosynthesis is how plants turn sunlight, water and carbon dioxide into sugar and oxygen. "
        "It happens in the chloroplasts. The Calvin cycle then builds glucose. ") * 3
CTRL_OPT_L = ("37", "ctrl,alt")
PASTE_LOG_PATTERN = "Accessibility is not granted|Cmd.V|INJECTOR"


def wins() -> list[dict]:
    try:
        return json.loads(helper("windows") or "[]")
    except Exception:
        return []


def appwins() -> list[dict]:
    return [w for w in wins() if "Productivity" in str(w.get("owner"))]


def floating() -> list[dict]:
    # Layer 25 = the menu-bar status item (v1.0.3), not the bar or widget.
    return [w for w in appwins() if w.get("h", 0) < 140 and w.get("layer", 0) != 25]


def key(w: dict) -> tuple:
    return (round(w["x"]), round(w["y"]), round(w["w"]), round(w["h"]))


def overlay() -> dict:
    st = api("/api/overlay/status")[1]
    return st if isinstance(st, dict) else {"raw": st}


def wait_for(pred, timeout: float, step: float = 0.3):
    t = time.time()
    while time.time() - t < timeout:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return None


def afplay_running() -> bool:
    return bool(sh("pgrep -x afplay", quiet=True)[1].strip())


def log_lines(pattern: str, n: int = 15) -> str:
    return sh(f"grep -hiE {shlex.quote(pattern)} ~/.voice_flow/logs/*.log | tail -{n}", quiet=True)[1].strip()


def textedit_window() -> dict | None:
    te = [w for w in wins() if w.get("owner") == "TextEdit" and w.get("h", 0) > 100]
    return te[0] if te else None


def open_textedit_with_text() -> dict | None:
    Path("/tmp/af.txt").write_text(TEXT)
    sh("killall TextEdit 2>/dev/null; sleep 1; open -a TextEdit /tmp/af.txt; sleep 5", quiet=True)
    return textedit_window()


def drag_select(w: dict) -> tuple[float, float]:
    x1, y1 = w["x"] + 12, w["y"] + 62
    x2, y2 = w["x"] + w["w"] - 40, w["y"] + 110
    helper("click", str(w["x"] + w["w"] / 2), str(w["y"] + 300))  # focus + clear old selection
    time.sleep(0.8)
    helper("drag", str(x1), str(y1), str(x2), str(y2))
    return x2, y2


def find_widget(before: list[dict], end: tuple[float, float]) -> dict | None:
    old = {key(w) for w in before}
    new = [w for w in floating() if key(w) not in old and w.get("w", 0) <= 60]
    if not new:
        return None
    return min(new, key=lambda w: abs(w["x"] - end[0]) + abs(w["y"] - end[1]))


def reading_started(timeout: float = 45) -> tuple[str | None, bool]:
    state = wait_for(lambda: (overlay().get("state") if overlay().get("state") in ("READING", "GENERATING_AUDIO", "GENERATING") else None), timeout)
    played = bool(wait_for(afplay_running, timeout))
    return state, played


def stop_reading() -> dict:
    helper("chord", *CTRL_OPT_L)  # pressing the Audio Flow hotkey while speaking stops playback
    stopped = bool(wait_for(lambda: not afplay_running(), 8))
    return {"afplay_gone": stopped, "overlay": overlay()}


def native_probe(label: str, point: tuple[float, float]) -> None:
    code = (
        "import json,sys\n"
        "from voice_flow.platform import macos_native as n\n"
        f"x,y={point[0]!r},{point[1]!r}\n"
        "print(json.dumps({'ax_trusted_probe_process': n.accessibility_trusted(), 'can_post_events_probe_process': n.can_post_events(),"
        "'frontmost': n.frontmost_window_owner(), 'window_at_point': n.window_owner_at_point(x,y),"
        "'focused_selection_info': n.focused_selection_info()}, default=str))\n"
    )
    rc, out = sh(f"PYTHONPATH={shlex.quote(PYPATH)} {shlex.quote(PY)} -c {shlex.quote(code)}", timeout=60)
    record(A, f"native ctypes probe with the bundled Python ({label})", "ok" if rc == 0 and "window_at_point" in out else "fail", out.strip()[-1500:])


def phase_selection_widget_and_read() -> None:
    w = open_textedit_with_text()
    if not w:
        record(A, "open TextEdit", "fail", json.dumps(wins())[:1500], shot("no-textedit"))
        return
    before = floating()
    end = drag_select(w)
    time.sleep(2.5)
    widget = find_widget(before, end)
    s1 = shot("af2-after-drag-selection")
    record(A, "select text by dragging in TextEdit: Listen widget appears", "ok" if widget else "fail",
           f"widget={widget}\nfloating before={before}\nfloating after={floating()}\nlog: {log_lines('Selection captured|MOUSE HOOK|Accessibility')}", s1)
    native_probe("selection active", (w["x"] + 60, w["y"] + 80))
    if not widget:
        # Diagnostics: engine threads (is the Quartz tap thread alive?) + app log.
        pids = sh("pgrep -f 'ai-productivity-flow-launcher$'", quiet=True)[1].split()
        for p in pids[:2]:
            sh(f"sample {p} 1 -file {shlex.quote(str(EV / ('sample-noselection-' + p + '.txt')))} >/dev/null 2>&1", quiet=True, timeout=30)
        save("af2-noselection-log.txt", log_lines("MOUSE HOOK|AUDIO FLOW|INPUT|Accessibility|trusted", 60))
        return
    helper("click", str(widget["x"] + widget["w"] / 2), str(widget["y"] + widget["h"] / 2))
    time.sleep(1.5)
    menu = [x for x in floating() if 200 <= x.get("w", 0) <= 320 and x.get("h", 0) <= 40]
    s2 = shot("af2-widget-mode-menu")
    record(A, "click the Listen widget: Read / Summary menu opens", "ok" if menu else "fail", f"menu={menu}\nfloating={floating()}", s2)
    if not menu:
        return
    m = menu[0]
    helper("click", str(m["x"] + 54), str(m["y"] + m["h"] / 2))  # Read
    state, played = reading_started()
    s3 = shot("af2-read-playing")
    record(A, "Read: selected text is read aloud (overlay READING + afplay playing)", "ok" if state and played else "fail",
           f"overlay state={state} afplay={played} overlay={overlay()}\nlog: {log_lines('Audio Flow reading|Audio Flow:|TTS error|synthesis|afplay|playback')}", s3)
    res = stop_reading()
    record(A, "Audio Flow hotkey (Ctrl+Option+L) while reading stops playback", "ok" if res["afplay_gone"] else "fail",
           json.dumps(res) + "\nlog: " + log_lines("Audio Flow hotkey", 5))


def phase_hotkey_read() -> None:
    w = textedit_window() or open_textedit_with_text()
    if not w:
        record(A, "hotkey read: TextEdit window", "fail", "missing")
        return
    drag_select(w)
    time.sleep(2.0)
    helper("chord", *CTRL_OPT_L)
    state, played = reading_started()
    s = shot("af2-hotkey-read")
    record(A, "Audio Flow hotkey (Ctrl+Option+L) with text selected reads it aloud", "ok" if state and played else "fail",
           f"overlay state={state} afplay={played}\nlog: {log_lines('Audio Flow hotkey|Audio Flow reading|Select text|Audio Flow:|AUDIO FLOW|MACOS')}", s)
    stop_reading()
    time.sleep(1.5)


def phase_bar_click() -> None:
    w = textedit_window() or open_textedit_with_text()
    if not w:
        record(A, "bar click: TextEdit window", "fail", "missing")
        return
    before = floating()
    end = drag_select(w)
    time.sleep(2.5)
    widget = find_widget(before, end)
    bars = [x for x in floating() if not widget or key(x) != key(widget)]
    bars = [x for x in bars if x.get("w", 0) >= 40]
    if not bars:
        record(A, "click the floating bar with text selected", "fail", f"no bar window; floating={floating()}", shot("af2-no-bar"))
        return
    bar = max(bars, key=lambda x: x["y"])
    helper("click", str(bar["x"] + max(12, bar["w"] * 0.25)), str(bar["y"] + bar["h"] / 2))
    state, played = reading_started()
    rec = overlay()
    s = shot("af2-bar-click")
    record(A, "click the floating bar with text selected: reads the selection (not dictation)",
           "ok" if state and played and rec.get("state") != "RECORDING" else "fail",
           f"bar={bar} overlay state={state} afplay={played} overlay now={rec}\nlog: {log_lines('Audio Flow reading|dictation|RECORD', 8)}", s)
    stop_reading()
    api("/api/record/toggle", {"recording": False})
    time.sleep(1.5)


def phase_summary() -> None:
    w = textedit_window() or open_textedit_with_text()
    if not w:
        return
    code, hist0 = api("/api/audio-flow/history")
    before = floating()
    end = drag_select(w)
    time.sleep(2.5)
    widget = find_widget(before, end)
    if not widget:
        record(A, "Summary: widget after selection", "fail", f"floating={floating()}", shot("af2-summary-no-widget"))
        return
    helper("click", str(widget["x"] + widget["w"] / 2), str(widget["y"] + widget["h"] / 2))
    time.sleep(1.5)
    menu = [x for x in floating() if 200 <= x.get("w", 0) <= 320 and x.get("h", 0) <= 40]
    if not menu:
        record(A, "Summary: mode menu", "fail", f"floating={floating()}", shot("af2-summary-no-menu"))
        return
    m = menu[0]
    helper("click", str(m["x"] + 166), str(m["y"] + m["h"] / 2))  # Summary
    time.sleep(1.5)
    s1 = shot("af2-summary-after-click")
    cards = floating()
    warn = [x for x in cards if 340 <= x.get("w", 0) <= 420 and 70 <= x.get("h", 0) <= 120]
    if warn:
        c = warn[0]
        helper("click", str(c["x"] + 290), str(c["y"] + c["h"] - 20))  # "Make Anyway"
        time.sleep(1.5)
    depth = [x for x in floating() if 240 <= x.get("w", 0) <= 290 and x.get("h", 0) <= 40]
    record(A, "Summary: depth picker shown (after short-text notice if any)", "ok" if depth else "fail",
           f"short notice={warn} depth={depth} floating={floating()}", s1)
    if not depth:
        return
    d = depth[0]
    helper("click", str(d["x"] + 126), str(d["y"] + d["h"] / 2))  # Balanced
    time.sleep(8)
    code, hist = api("/api/audio-flow/history")
    items = (hist.get("summaries") or hist.get("items")) if isinstance(hist, dict) else hist
    items = items if isinstance(items, list) else []
    newest = items[:2]
    s2 = shot("af2-summary-submitted")
    record(A, "Summary: job submitted from the selection (needs NotebookLM sign-in to finish)",
           "ok" if any("photosynthesis" in json.dumps(i).lower() for i in newest) else "fail",
           f"history newest={json.dumps(newest, default=str)[:1200]}\noverlay={overlay()}\nlog: {log_lines('summary|NotebookLM|AUDIO FLOW', 12)}", s2)


def phase_paste_after_widget_click() -> None:
    """Integration (a): a click on the Audio Flow widget makes our app active;
    the next dictation must still paste into TextEdit (focus restored)."""
    clip = str(qa_voice.CLIPS / "af2-paste.aiff")
    if not Path(clip).exists():
        sh(f"say -r 175 -o {shlex.quote(clip)} 'Send the report today.'", quiet=True)
    w = textedit_window() or open_textedit_with_text()
    if not w:
        record(A, "paste after widget click: TextEdit window", "fail", "missing")
        return
    pid_s = sh("pgrep -x TextEdit", quiet=True)[1].strip().splitlines()
    pid = int(pid_s[0]) if pid_s else None
    before_f = floating()
    end = drag_select(w)
    time.sleep(2.5)
    widget = find_widget(before_f, end)
    if widget:
        helper("click", str(widget["x"] + widget["w"] / 2), str(widget["y"] + widget["h"] / 2))
        time.sleep(1.5)
        helper("key", "53")  # Escape closes the menu (goes to the active app)
        time.sleep(1.0)
    front = sh("lsappinfo info -only name `lsappinfo front`", quiet=True)[1].strip()
    before = qa_voice.textedit_text(pid)
    row, _ = qa_voice.dictate("af2-paste", clip, "api")
    time.sleep(1.5)
    after = qa_voice.textedit_text(pid)
    ok = bool(widget) and bool(row) and row.get("insertion_status") == "pasted" and after != before and "report" in after.lower()
    record(A, "paste right after clicking the Audio Flow widget lands in TextEdit (focus restored)",
           "ok" if ok else "fail",
           f"widget={widget}\nfrontmost app before dictation: {front}\nrow={json.dumps(row, default=str)[:600]}\n"
           f"TextEdit before={before[-160:]!r}\nafter={after[-200:]!r}\nlog: " + log_lines("focus restore|INJECTOR", 6),
           shot("af2-paste-after-widget"))


def revoke_paste_tcc() -> str:
    """Never-granted state for paste: drop Accessibility + PostEvent from BOTH TCC databases."""
    out = []
    for db in (str(Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"), "/Library/Application Support/com.apple.TCC/TCC.db"):
        q = (f"DELETE FROM access WHERE client='{BUNDLE_ID}' AND service IN ('kTCCServiceAccessibility','kTCCServicePostEvent');"
             f"SELECT service||'='||auth_value FROM access WHERE client='{BUNDLE_ID}';")
        rc, o = sh(f"sudo sqlite3 {shlex.quote(db)} {shlex.quote(q)}", quiet=True)
        out.append(f"{db.split('/')[1]} rc={rc} left={o.strip().replace(chr(10), ',')}")
    sh(f"tccutil reset Accessibility {BUNDLE_ID}; tccutil reset PostEvent {BUNDLE_ID}; sudo killall tccd 2>/dev/null; killall tccd 2>/dev/null; sleep 2", quiet=True)
    return "\n".join(out)


def restart_app(mic: str | None) -> float | None:
    kill_all()
    time.sleep(2)
    launch_open(APP)
    up = wait_api(120)
    time.sleep(10)
    qa_voice.click_allow_if_prompt(A)
    if mic:
        api("/api/microphones/select", {"name": mic})
    return up


def phase_paste_honesty(mic: str | None = None) -> None:
    clip = str(qa_voice.CLIPS / "af2-paste.aiff")
    sh(f"say -r 175 -o {shlex.quote(clip)} 'Send the report today.'", quiet=True)
    # 1) never granted: no Accessibility / PostEvent rows anywhere, fresh app process
    tcc = revoke_paste_tcc()
    up = restart_app(mic)
    perm = api("/api/platform/permissions")[1]
    ax = next((p for p in (perm.get("permissions") or []) if p.get("key") == "accessibility"), {}) if isinstance(perm, dict) else {}
    record(A, "no-Accessibility state: TCC rows removed from both databases, app restarted", "ok" if up and ax.get("granted") is False else "fail",
           f"{tcc}\napi after {up}s\naccessibility={ax}")
    pid = qa_voice.textedit_open(A)
    before = qa_voice.textedit_text(pid)
    sh("printf 'ORIGINAL-CLIPBOARD' | pbcopy", quiet=True)
    row, _ = qa_voice.dictate("af2-paste", clip, "api")
    time.sleep(1.5)
    after = qa_voice.textedit_text(pid)
    clipboard = sh("pbpaste", quiet=True)[1]
    final = str((row or {}).get("polished_text") or (row or {}).get("raw_text") or "")
    honest = bool(row) and row.get("insertion_status") == "copied_to_clipboard" and row.get("status") == "paste_failed"
    kept = bool(final) and final.strip() == clipboard.strip()
    record(A, "paste WITHOUT Accessibility: honest status, text kept on clipboard, TextEdit untouched",
           "ok" if honest and kept and after == before else "fail",
           f"row={json.dumps(row, default=str)[:700]}\nclipboard={clipboard!r}\nTextEdit before={before!r} after={after!r}\n"
           "log: " + log_lines(PASTE_LOG_PATTERN, 6), shot("af2-paste-no-ax"))
    # 2) with Accessibility again (fresh process): real paste + clipboard restored
    qa_voice.grant_tcc(A)
    restart_app(mic)
    pid = qa_voice.textedit_open(A)
    sh("printf 'ORIGINAL-CLIPBOARD-2' | pbcopy", quiet=True)
    before = qa_voice.textedit_text(pid)
    row, _ = qa_voice.dictate("af2-paste", clip, "api")
    time.sleep(1.5)
    after = qa_voice.textedit_text(pid)
    clipboard = sh("pbpaste", quiet=True)[1]
    ok = bool(row) and row.get("insertion_status") == "pasted" and len(after) > len(before) and clipboard.strip() == "ORIGINAL-CLIPBOARD-2"
    record(A, "paste WITH Accessibility: pasted into TextEdit and user clipboard restored", "ok" if ok else "fail",
           f"row={json.dumps(row, default=str)[:600]}\nclipboard={clipboard!r}\nTextEdit after={after[-200:]!r}\n"
           "log: " + log_lines(PASTE_LOG_PATTERN, 6), shot("af2-paste-with-ax"))


def main():
    install_watchdog(34)
    try:
        mic = qa_voice.setup_audio(A)  # BlackHole in/out + TCC pre-approval for the bundle id
        kill_all()
        wipe_user_data()
        launch_open(APP)
        up = wait_api(120)
        time.sleep(12)
        api("/api/settings/update", {"key": "has_viewed_onboarding", "value": True})
        qa_voice.click_allow_if_prompt(A)
        record(A, "app up; macOS selection listener started", "ok" if "Quartz mouse listener started" in log_lines("MOUSE HOOK", 5) else "fail",
               f"api after {up}s\nlog: {log_lines('MOUSE HOOK|INPUT', 8)}\nperm={json.dumps(api('/api/platform/permissions')[1])[:800]}")
        for step in (phase_selection_widget_and_read, phase_hotkey_read, phase_bar_click, phase_summary):
            try:
                step()
            except Exception:
                import traceback
                record(A, f"{step.__name__} crashed", "error", traceback.format_exc()[-1500:])
        try:
            qa_voice.select_mic(A, mic)
            try:
                phase_paste_after_widget_click()
            except Exception:
                import traceback
                record(A, "paste after widget click crashed", "error", traceback.format_exc()[-1500:])
            phase_paste_honesty(mic)
        except Exception:
            import traceback
            record(A, "paste honesty crashed", "error", traceback.format_exc()[-1500:])
        save("af2-app-log-tail.txt", sh("tail -300 ~/.voice_flow/logs/voice_flow_debug.log", quiet=True)[1])
        kill_all()
    except BaseException:
        import traceback
        record(A, "phase crashed", "error", traceback.format_exc()[-1500:])
        kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; true", quiet=True)
    finish("af2")


if __name__ == "__main__":
    main()
