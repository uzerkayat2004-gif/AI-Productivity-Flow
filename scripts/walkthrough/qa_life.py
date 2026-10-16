"""Phase LIFE: how a Mac user quits / reopens the app, second copies, login item."""
from __future__ import annotations

import json
import shlex
import time

from qa_common import (EV, HOME, BUNDLE_ID, record, sh, save, api, wait_api, shot, app_tree, fmt_rows, helper,
                       launch_open, kill_all, wipe_user_data, finish, install_watchdog, log)

A = "lifecycle"
APP = "/Applications/AI Productivity Flow.app"


def lsapp() -> str:
    return sh("lsappinfo list | grep -B2 -A12 -i 'productivity' | grep -iE 'productivity|ASN|pid|type|bundleID|executable' | head -40", quiet=True)[1]


def windows() -> list:
    try:
        rows = json.loads(helper("windows") or "[]")
    except Exception:
        return []
    return [{k: w[k] for k in ("owner", "pid", "name", "layer", "x", "y", "w", "h")} for w in rows if "Productivity" in str(w.get("owner"))]


def state(label: str) -> dict:
    return {"procs": fmt_rows(app_tree()), "lsappinfo": lsapp(), "windows": windows(),
            "api": api("/api/version", timeout=2)[0], "shot": shot(label)}


def fresh():
    kill_all()
    wipe_user_data()
    launch_open(APP)
    up = wait_api(120)
    time.sleep(15)
    api("/api/settings/update", {"key": "has_viewed_onboarding", "value": True})
    return up


def main():
    install_watchdog(30)
    try:
        up = fresh()
        s = state("life-running")
        record(A, "running app: processes, LaunchServices entries, windows", "info", json.dumps(s, indent=1)[:3500], s["shot"])
        # 1. Quit Apple Event (= Dock > Quit, Cmd+Q via the app menu) by bundle id.
        sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25)
        time.sleep(20)
        s1 = state("life-after-quit-1")
        record(A, "after Quit #1 (Apple Event to the bundle id)", "ok" if not app_tree() else "fail", json.dumps(s1, indent=1)[:3500], s1["shot"])
        sh(f"osascript -e 'tell application id \"{BUNDLE_ID}\" to quit'", timeout=25)
        time.sleep(20)
        s2 = state("life-after-quit-2")
        record(A, "after Quit #2", "ok" if not app_tree() else "fail", json.dumps(s2, indent=1)[:3500], s2["shot"])
        # Reopen while the engine is still alive (user clicks the app again).
        launch_open(APP)
        time.sleep(15)
        s3 = state("life-reopen-after-quit")
        engines = sum(1 for r in app_tree() if r["cmd"].endswith("ai-productivity-flow-launcher"))
        record(A, "open the app again after Quit", "info", f"engine processes={engines}\n" + json.dumps(s3, indent=1)[:3000], s3["shot"])
        # 2. Cmd+Q in the focused main window.
        kill_all()
        fresh()
        wins = [w for w in windows() if w["h"] > 300]
        if wins:
            w = wins[0]
            helper("click", str(w["x"] + w["w"] / 2), str(w["y"] + 12))
            time.sleep(1)
            helper("key", "12", "cmd")
            time.sleep(20)
            s4 = state("life-after-cmd-q")
            record(A, "Cmd+Q in the main window", "ok" if not app_tree() else "fail", json.dumps(s4, indent=1)[:3500], s4["shot"])
        # 3. Close the window with the red button (Cmd+W).
        kill_all()
        fresh()
        wins = [w for w in windows() if w["h"] > 300]
        if wins:
            w = wins[0]
            helper("click", str(w["x"] + w["w"] / 2), str(w["y"] + 12))
            time.sleep(1)
            helper("key", "13", "cmd")
            time.sleep(15)
            s5 = state("life-after-cmd-w")
            record(A, "close the window (Cmd+W): engine + floating bar keep running?", "info", json.dumps(s5, indent=1)[:3000], s5["shot"])
            # Reopen from Finder/Dock while engine alive.
            launch_open(APP)
            time.sleep(15)
            s6 = state("life-reopen-after-close")
            record(A, "reopen after closing the window", "info", json.dumps(s6, indent=1)[:3000], s6["shot"])
        # 4. Second copy: open the DMG copy (plain open, no -n) while /Applications copy runs.
        kill_all()
        fresh()
        sh("curl -sL -o /tmp/app.dmg https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.2/AI-Productivity-Flow-macOS.dmg && hdiutil attach /tmp/app.dmg -nobrowse -mountpoint /Volumes/APF2", timeout=400)
        launch_open(APP)  # same copy again, plain open
        time.sleep(10)
        n_same = sum(1 for r in app_tree() if r["cmd"].endswith("ai-productivity-flow-launcher"))
        launch_open("/Volumes/APF2/AI Productivity Flow.app")
        time.sleep(20)
        tree = app_tree()
        engines = [r for r in tree if r["cmd"].endswith("ai-productivity-flow-launcher")]
        s7 = state("life-second-copy-from-dmg")
        log_lines = sh("grep -h 'already owns port\\|VOICE FLOW READY\\|Global input listeners started' ~/.voice_flow/logs/*.log | tail -10", quiet=True)[1]
        record(A, "second copy: open /Applications again, then open the DMG copy while it runs",
               "ok" if len(engines) <= 1 else "fail",
               f"engines after re-open of same copy={n_same}; engines after opening DMG copy={len(engines)}\nlog: {log_lines}\n" + json.dumps(s7, indent=1)[:2500], s7["shot"])
        kill_all()
        sh("hdiutil detach /Volumes/APF2 -force", timeout=60)
        # 5. Launch at login toggle.
        fresh()
        on = api("/api/settings/autostart/toggle", {"enabled": True})
        la_on = sh("ls -la ~/Library/LaunchAgents; cat ~/Library/LaunchAgents/*productivity* 2>/dev/null | head -40; launchctl list | grep -i productivity", quiet=True)[1]
        off = api("/api/settings/autostart/toggle", {"enabled": False})
        la_off = sh("ls -la ~/Library/LaunchAgents", quiet=True)[1]
        record(A, "Launch at login on/off", "info", f"on -> {on}\n{la_on[:1500]}\noff -> {off}\n{la_off[:600]}")
        kill_all()
    except BaseException:
        import traceback
        record(A, "phase crashed / watchdog", "error", traceback.format_exc()[-1500:])
        kill_all()
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/; true", quiet=True)
    finish("life")


if __name__ == "__main__":
    main()
