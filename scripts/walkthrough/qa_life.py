"""Phase LIFE (fix/mac-lifecycle verification): quit, close, reopen, second copy,
login item, bytecode in bundle. Second copy uses the DMG under test (/Volumes/APF)."""
from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path

from qa_common import (EV, HOME, BUNDLE_ID, record, sh, api, wait_api, shot, app_tree, fmt_rows, helper,
                       launch_open, kill_all, wipe_user_data, finish, install_watchdog, log)

A = "lifecycle"
APP = "/Applications/AI Productivity Flow.app"
DMG_APP = "/Volumes/APF/AI Productivity Flow.app"


def lsapp() -> str:
    return sh("lsappinfo list | grep -B2 -A12 -i 'productivity' | grep -iE 'productivity|ASN|pid|type|bundleID|executable' | head -40", quiet=True)[1]


def all_windows() -> list:
    try:
        rows = json.loads(helper("windows") or "[]")
    except Exception:
        return []
    return [{k: w.get(k) for k in ("owner", "pid", "name", "layer", "x", "y", "w", "h")} for w in rows
            if "Productivity" in str(w.get("owner"))]


def main_windows() -> list:
    return [w for w in all_windows() if (w.get("h") or 0) > 300 and (w.get("layer") or 0) == 0]


def status_items() -> list:
    return [w for w in all_windows() if (w.get("layer") or 0) == 25]


def engines() -> list:
    return [r for r in app_tree() if r["cmd"].endswith("ai-productivity-flow-launcher")]


def zombies() -> list:
    return [r for r in app_tree() if "defunct" in r["cmd"] or r["cmd"].strip() in ("(ai-productivity-)", "<defunct>")]


def state(label: str) -> dict:
    return {"procs": fmt_rows(app_tree()), "windows": all_windows(), "lsappinfo": lsapp()[:800],
            "api": api("/api/version", timeout=2)[0], "shot": shot(label)}


def wait_gone(seconds: float = 20.0) -> float | None:
    t = time.time()
    while time.time() - t < seconds:
        if not app_tree():
            return round(time.time() - t, 1)
        time.sleep(0.5)
    return None


def fresh(app: str = APP):
    kill_all()
    wipe_user_data()
    launch_open(app)
    up = wait_api(120)
    api("/api/settings/update", {"key": "has_viewed_onboarding", "value": True})
    for _ in range(30):
        if main_windows():
            break
        time.sleep(1)
    time.sleep(3)
    return up


def quit_check(step: str, action, label: str) -> None:
    before = fmt_rows(app_tree())
    t0 = time.time()
    action()
    gone = wait_gone(20)
    s = state(label)
    note = {"seconds_to_exit": gone, "before": before, "after": s}
    record(A, step, "ok" if gone is not None and gone <= 10 else "fail", json.dumps(note, indent=1)[:3500], s["shot"])


def bar_window():
    cur = [w for w in all_windows() if (w.get("h") or 0) < 120 and (w.get("layer") or 0) not in (25,)
           and (w.get("layer") or 0) < 100 and (w.get("w") or 0) > 40]
    return cur[0] if cur else None


def menu_windows() -> list:
    return [w for w in all_windows() if (w.get("layer") or 0) >= 100]


def dismiss_menu() -> None:
    helper("key", "53")  # Escape
    time.sleep(0.5)
    if menu_windows():
        helper("click", "60", "400")  # click on the empty desktop
        time.sleep(0.8)


def open_bar_menu(kind: str, tries: int = 2):
    """Hover then right-/Control-click the bar; returns (menu windows, tried, log)."""
    tried = []
    menus = []
    b = bar_window()
    if not b:
        return None, tried, ""
    helper("move", str(b["x"] + b["w"] / 2), str(b["y"] + b["h"] / 2))
    time.sleep(1.5)
    for _ in range(tries):
        b = bar_window() or b
        tried.append({"kind": kind, "bar": b})
        helper(kind, str(b["x"] + b["w"] / 2), str(b["y"] + b["h"] / 2))
        time.sleep(1.5)
        menus = menu_windows()
        if menus:
            break
        dismiss_menu()
    lg = sh("grep -h 'Floating bar menu\\|Secondary click' ~/.voice_flow/logs/*.log | tail -4", quiet=True)[1]
    return menus, tried, lg


def bar_menu_check(kind: str, step: str, label: str) -> None:
    menus, tried, lg = open_bar_menu(kind)
    if menus is None:
        record(A, step, "error", "floating bar window not found")
        return
    sm = shot(label)
    record(A, step, "ok" if menus else "fail",
           json.dumps({"tried": tried, "menu_windows": menus, "log": lg}, indent=1)[:2000], sm)
    dismiss_menu()
    if menu_windows():
        record(A, step + " (menu dismissed again)", "fail", json.dumps(menu_windows()))


def focus_main_window() -> bool:
    wins = main_windows()
    if not wins:
        return False
    w = wins[0]
    helper("click", str(w["x"] + w["w"] / 2), str(w["y"] + 12))
    time.sleep(1)
    return True


def main():
    install_watchdog(30)
    marker = EV / "bundle-marker"
    marker.write_text("x")
    try:
        # 1. Apple Event quit (= Dock > Quit) by bundle id: ONE quit must end everything.
        fresh()
        s = state("life-running")
        record(A, "running app: processes, windows (incl. menu bar item)", "info", json.dumps(s, indent=1)[:3500], s["shot"])
        quit_check("Quit Apple Event (Dock > Quit) ends engine, window, helpers in one go",
                   lambda: sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25), "after-quit-ae")

        # 2. Cmd+Q in the focused main window.
        fresh()
        if focus_main_window():
            quit_check("Cmd+Q in the main window ends everything", lambda: helper("key", "12", "cmd"), "after-cmd-q")
        else:
            record(A, "Cmd+Q in the main window ends everything", "error", "no main window found")

        # 3. Cmd+W: window closes, engine stays, no zombie, menu bar item + bar menu, reopen works.
        fresh()
        if focus_main_window():
            helper("key", "13", "cmd")
            time.sleep(6)
            s5 = state("after-cmd-w")
            eng = engines()
            ok = bool(eng) and not main_windows() and not zombies()
            record(A, "Cmd+W closes only the window; engine keeps running; no <defunct> child", "ok" if ok else "fail",
                   json.dumps({"engines": len(eng), "zombies": fmt_rows(zombies()), **s5}, indent=1)[:3500], s5["shot"])
            items = status_items()
            record(A, "menu bar status item visible after closing the window (way back + Quit)",
                   "ok" if items else "fail", json.dumps(items, indent=1)[:1500])
            # Floating bar menu: right-click and Control-click are separate checks.
            bar_menu_check("rclick", "floating bar right-click opens Open/Quit menu", "bar-right-click-menu")
            bar_menu_check("ctrlclick", "floating bar Control-click opens Open/Quit menu", "bar-ctrl-click-menu")
            # Reopen like a user (Finder / Launchpad).
            launch_open(APP)
            reopened = False
            for _ in range(20):
                if main_windows():
                    reopened = True
                    break
                time.sleep(1)
            s6 = state("reopen-after-close")
            record(A, "open the app again after closing the window shows the window (one engine)",
                   "ok" if reopened and len(engines()) == 1 else "fail",
                   json.dumps({"engines": len(engines()), **s6}, indent=1)[:3000], s6["shot"])
            # Quit from the menu bar item (System Events; needs Accessibility for osascript).
            eng = engines()
            if eng and items:
                pid = eng[0]["pid"]
                script = ("tell application \"System Events\" to tell (first process whose unix id is %d) to "
                          "tell menu bar item 1 of menu bar 2\nclick\ndelay 0.5\nclick menu item \"Quit AI Productivity Flow\" of menu 1\nend tell") % pid
                quit_check("menu bar item > Quit AI Productivity Flow ends everything",
                           lambda: sh("osascript -e " + shlex.quote(script), timeout=25), "after-status-quit")
            if app_tree():
                kill_all()
        else:
            record(A, "Cmd+W closes only the window", "error", "no main window found")

        # 4. Second copy: the DMG under test while the /Applications copy runs.
        fresh()
        if not Path(DMG_APP).exists():
            sh("hdiutil attach app.dmg -nobrowse -mountpoint /Volumes/APF", timeout=120)
        launch_open(APP)  # same copy again
        time.sleep(8)
        n_same = len(engines())
        launch_open(DMG_APP)
        time.sleep(20)
        eng = engines()
        s7 = state("second-copy-from-dmg")
        log_lines = sh("grep -h 'already running\\|VOICE FLOW READY\\|Global input listeners started' ~/.voice_flow/logs/*.log | tail -10", quiet=True)[1]
        ok = n_same == 1 and len(eng) == 1 and bool(main_windows())
        record(A, "second copy (DMG under test) while /Applications copy runs: one engine, window shown",
               "ok" if ok else "fail",
               f"engines after re-open of same copy={n_same}; after opening DMG copy={len(eng)}\nlog: {log_lines}\n"
               + json.dumps(s7, indent=1)[:2500], s7["shot"])
        quit_check("Quit after the second-copy attempt ends everything",
                   lambda: sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25), "after-quit-2nd")
        kill_all()

        # 4b. Quit chosen from the floating bar menu ends everything.
        fresh()
        menus, tried, lg = open_bar_menu("ctrlclick")
        if menus:
            m = menus[0]
            quit_check("floating bar menu > Quit AI Productivity Flow ends everything",
                       lambda: helper("click", str(m["x"] + m["w"] / 2), str(m["y"] + m["h"] - 14)), "after-bar-menu-quit")
        else:
            record(A, "floating bar menu > Quit AI Productivity Flow ends everything", "error",
                   "menu did not open: " + json.dumps({"tried": tried, "log": lg})[:1500])
        kill_all()

        # 4c. Settings > Restart: old engine pid ends, one new engine comes up, then Quit ends everything.
        fresh()
        old = [r["pid"] for r in engines()]
        rs = api("/api/app/restart", {})
        new_eng, back = [], False
        t0 = time.time()
        while time.time() - t0 < 60:
            time.sleep(1)
            cur = [r["pid"] for r in engines()]
            if cur and not set(cur) & set(old) and api("/api/version", timeout=2)[0] == 200:
                new_eng = cur
                break
        for _ in range(30):
            if main_windows():
                back = True
                break
            time.sleep(1)
        time.sleep(3)
        s8 = state("after-restart")
        rlog = sh("grep -h 'RESTART\\|QUIT' ~/.voice_flow/logs/*.log | tail -8", quiet=True)[1]
        old_alive = [p for p in old if sh(f"kill -0 {p} 2>/dev/null", quiet=True)[0] == 0]
        ok = bool(new_eng) and len(engines()) == 1 and not old_alive and back
        record(A, "Settings > Restart ends the old engine (by pid) and starts exactly one new one with its window",
               "ok" if ok else "fail",
               json.dumps({"restart_api": rs, "old_engine": old, "old_alive": old_alive, "new_engine": new_eng,
                           "seconds": round(time.time() - t0, 1), "window_back": back, "log": rlog, **s8}, indent=1)[:3500], s8["shot"])
        quit_check("Quit after Settings > Restart ends everything",
                   lambda: sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25), "after-restart-quit")
        kill_all()

        # 4d. A running helper child of the engine (Audio Summary player process) is ended by Quit.
        fresh()
        child_note, child_pids = {}, []
        try:
            import sqlite3
            import uuid
            media = HOME / ".voice_flow" / "audio_summaries"
            media.mkdir(parents=True, exist_ok=True)
            wav = media / "qa-life-child.wav"
            sh(f"say -o /tmp/qa-life.aiff 'This is a long test summary. ' 'It keeps talking for a while so the player stays open.'; "
               f"afconvert -f WAVE -d LEI16 /tmp/qa-life.aiff {shlex.quote(str(wav))}", timeout=60, quiet=True)
            db = sh("find ~/.voice_flow -name 'voice_flow.db' | head -1", quiet=True)[1].strip()
            sid = "qa-life-" + uuid.uuid4().hex[:6]
            con = sqlite3.connect(db)
            con.execute("insert into audio_summary_history (id,title,text_snippet,full_text,depth,audio_path,duration_sec,status,progress,created_at) values (?,?,?,?,?,?,?,?,?,datetime('now'))",
                        (sid, "QA child", "x", "x", "balanced", str(wav), 6.0, "ready", 100))
            con.commit()
            con.close()
            child_note["play"] = api("/api/audio-flow/history/play", {"id": sid})
            eng = [r["pid"] for r in engines()]
            for _ in range(20):
                time.sleep(1)
                child_pids = [r["pid"] for r in app_tree() if "audio_summary_player" in r["cmd"] and r["ppid"] in eng]
                if child_pids:
                    break
            child_note["engine"] = eng
            child_note["children_before_quit"] = sh("ps -o pid,ppid,command -p " + ",".join(map(str, child_pids or [0])), quiet=True)[1][:800]
        except Exception as exc:
            child_note["error"] = str(exc)
        if child_pids:
            quit_check("Quit with a running helper child (Audio Summary player) ends everything",
                       lambda: sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25), "after-child-quit")
            left = [p for p in child_pids if sh(f"kill -0 {p} 2>/dev/null", quiet=True)[0] == 0]
            qlog = sh("grep -h 'QUIT\\]' ~/.voice_flow/logs/*.log | tail -4", quiet=True)[1]
            record(A, "helper child spawned by the engine is gone after Quit", "ok" if not left else "fail",
                   json.dumps({**child_note, "child_pids": child_pids, "still_alive": left, "quit_log": qlog}, indent=1)[:2500])
        else:
            record(A, "helper child spawned by the engine is gone after Quit", "error",
                   "could not start a helper child: " + json.dumps(child_note)[:2000])
        kill_all()

        # 5. Launch at login: bundle-id plist, legacy migrated, no second engine started.
        fresh()
        legacy = HOME / "Library/LaunchAgents/com.voiceflow.app.plist"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        on = api("/api/settings/autostart/toggle", {"enabled": True})
        time.sleep(6)
        la_on = sh("ls -la ~/Library/LaunchAgents; launchctl list | grep -i productivity", quiet=True)[1]
        n_eng = len(engines())
        new_ok = (HOME / "Library/LaunchAgents/com.uzerkayat.aiproductivityflow.plist").exists() and not legacy.exists()
        off = api("/api/settings/autostart/toggle", {"enabled": False})
        time.sleep(2)
        still = len(engines())
        la_off = sh("ls -la ~/Library/LaunchAgents", quiet=True)[1]
        record(A, "Launch at login uses com.uzerkayat.aiproductivityflow.plist; toggling starts/kills nothing",
               "ok" if new_ok and n_eng == 1 and still == 1 and not (HOME / "Library/LaunchAgents/com.uzerkayat.aiproductivityflow.plist").exists() else "fail",
               f"on -> {on}\nengines after on={n_eng}, after off={still}\n{la_on[:1200]}\noff -> {off}\n{la_off[:600]}")
        # Legacy migration at startup.
        kill_all()
        legacy.write_text('<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key><string>com.voiceflow.app</string></dict></plist>')
        launch_open(APP)
        wait_api(120)
        time.sleep(3)
        mig = (HOME / "Library/LaunchAgents/com.uzerkayat.aiproductivityflow.plist").exists() and not legacy.exists()
        record(A, "legacy com.voiceflow.app login item migrated at startup", "ok" if mig else "fail",
               sh("ls -la ~/Library/LaunchAgents", quiet=True)[1][:800])
        api("/api/settings/autostart/toggle", {"enabled": False})

        # 6. Startup console noise: /api/me optional probe.
        code, body = api("/api/me?optional=1")
        record(A, "/api/me?optional=1 when not signed in is 200 (no console 401)", "ok" if code == 200 else "fail", f"{code} {body}")
        kill_all()

        # 7. Nothing written inside the bundle; signature intact.
        written = sh(f"find {shlex.quote(APP)} -newer {shlex.quote(str(marker))} \\( -name '*.pyc' -o -name '__pycache__' \\) | head -20", quiet=True)[1].strip()
        record(A, "no .pyc / __pycache__ written into the app bundle while running", "ok" if not written else "fail", written or "(none)")
        rc, cs = sh(f"codesign --verify --deep --strict {shlex.quote(APP)} 2>&1", quiet=True)
        record(A, "bundle signature still valid after all runs", "ok" if rc == 0 else "fail", cs[:800])
        left = fmt_rows(app_tree())
        record(A, "no app processes left at the end", "ok" if left == "(none)" else "fail", left)
    except BaseException:
        import traceback
        record(A, "phase crashed / watchdog", "error", traceback.format_exc()[-1500:])
        kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; true", quiet=True)
    finish("life")


if __name__ == "__main__":
    main()
