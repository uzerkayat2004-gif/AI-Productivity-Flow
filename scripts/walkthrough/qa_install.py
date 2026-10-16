"""Phase INSTALL: get it like a user, Gatekeeper, run locations, lifecycle, uninstall, privacy idle."""
from __future__ import annotations

import json
import os
import re
import shlex
import time
import uuid
from pathlib import Path

from qa_common import *  # noqa: F401,F403
from qa_common import (EV, OUT, HOME, REPO, BUNDLE_ID, record, sh, save, api, wait_api, api_down, shot, app_tree,
                       fmt_rows, plist, launch_open, launch_exec, quit_app, kill_all, wipe_user_data, leftovers,
                       NetCapture, finish, install_watchdog, log, resolve_ips)

A = "install"
ASSETS = ["AI-Productivity-Flow-macOS.dmg", "AI-Productivity-Flow-macOS.zip", "AI-Productivity-Flow-Setup-x64.exe"]
DL = HOME / "Downloads"
APPN = "AI Productivity Flow.app"


def quarantine(path: Path) -> None:
    val = f"0083;{int(time.time()):x};Safari;{str(uuid.uuid4()).upper()}"
    sh(f"xattr -w com.apple.quarantine {shlex.quote(val)} {shlex.quote(str(path))}")


def gk_logs(minutes: int = 2) -> str:
    return sh(f"log show --last {minutes}m --style compact --predicate 'process == \"syspolicyd\" OR process == \"CoreServicesUIAgent\" OR subsystem == \"com.apple.syspolicy.exec\"' 2>/dev/null | grep -iE 'productivity|gatekeeper|notari|malware|translocat|assessment|deny|allow' | tail -60", timeout=60, quiet=True)[1]


def baseline_from_workflow_launch():
    """The workflow's Launch step started /Applications copy (quarantine removed) 20s before us."""
    app = "/Applications/" + APPN
    rows = app_tree()
    record(A, "workflow-launched app is running (baseline)", "ok" if rows else "fail", fmt_rows(rows))
    ls = leftovers()
    record(A, "files created by a first launch from /Applications", "info", ls[:2500], save("first-launch-files.txt", ls))
    rc, out = sh(f"find {shlex.quote(app)} -newer {shlex.quote(str(OUT / 'system.txt'))} -type f | head -50", quiet=True)
    # The workflow installs with `cp -R` after system.txt, so every file is
    # "newer"; only Python bytecode written at runtime is meaningful here.
    out = "\n".join(l for l in out.splitlines() if l.endswith(".pyc") or "__pycache__" in l)
    record(A, "nothing written inside the bundle by first launch (/Applications)", "ok" if not out.strip() else "fail",
           out.strip()[:1500] or "no files in the bundle newer than install time")
    k = kill_all()
    record(A, "stop baseline app", "info", f"left after SIGTERM: {k}")
    wipe = wipe_user_data()
    sh(f"rm -rf {shlex.quote(app)}")
    record(A, "clean slate (removed app + user data)", "info", wipe)


def _ci_build_assets() -> tuple[Path, Path | None] | None:
    """Integration QA (qa/int-*): test the CI-built DMG/zip, not the published release."""
    if not os.environ.get("GITHUB_REF_NAME", "").startswith("qa/int-"):
        return None
    root = Path(os.environ.get("GITHUB_WORKSPACE", "."))
    dmg = root / "app.dmg"
    if not dmg.exists():
        return None
    zips = sorted((root / "dl").glob("*.zip")) if (root / "dl").is_dir() else []
    return dmg, (zips[0] if zips else None)


def downloads():
    DL.mkdir(exist_ok=True)
    ci = _ci_build_assets()
    if ci is not None:
        dmg, z = ci
        sh(f"cp {shlex.quote(str(dmg))} {shlex.quote(str(DL / ASSETS[0]))}", timeout=300)
        if z is not None:
            sh(f"cp {shlex.quote(str(z))} {shlex.quote(str(DL / ASSETS[1]))}", timeout=300)
        sizes = sh(f"ls -la {shlex.quote(str(DL))}", quiet=True)[1]
        record(A, "CI build under test copied to ~/Downloads (release download skipped)", "ok" if (DL / ASSETS[0]).exists() else "fail",
               f"dmg={dmg} zip={z}\n{sizes}")
        return
    rows = []
    for name in ASSETS:
        for suffix in ("", ".sha256"):
            url = f"https://github.com/{REPO}/releases/latest/download/{name}{suffix}"
            rc, out = sh(f"curl -sSL -o {shlex.quote(str(DL / (name + suffix)))} -w '%{{http_code}} %{{url_effective}} %{{size_download}}' {url}", timeout=600, quiet=True)
            rows.append(f"{name}{suffix}: {out.strip()}")
    ok_all = True
    lines = []
    for name in ASSETS:
        rc, actual = sh(f"shasum -a 256 {shlex.quote(str(DL / name))}", quiet=True)
        expected = (DL / (name + ".sha256")).read_text(errors="replace").strip() if (DL / (name + ".sha256")).exists() else ""
        a = actual.split()[0] if actual.split() else ""
        e = expected.split()[0].lower() if expected.split() else ""
        ok = bool(a) and a == e
        ok_all &= ok
        lines.append(f"{name}: actual={a} expected_file='{expected[:120]}' match={ok}")
    v102 = all("/v1.0.2/" in r for r in rows)
    record(A, "anonymous download of every asset via /releases/latest/download", "ok" if v102 and all(" 200 " in r for r in rows) else "fail",
           "\n".join(rows), save("downloads.txt", "\n".join(rows) + "\n\n" + "\n".join(lines)))
    record(A, "sha256 of each asset matches its .sha256 (on the Mac runner)", "ok" if ok_all else "fail", "\n".join(lines))
    rc, out = sh(f"curl -s https://api.github.com/repos/{REPO}/releases/latest | python3 -c \"import json,sys;d=json.load(sys.stdin);print(d.get('tag_name'),d.get('draft'),d.get('prerelease'),[a['name'] for a in d.get('assets',[])], d.get('message'))\"", quiet=True)
    record(A, "GitHub API /releases/latest", "ok" if out.startswith("v1.0.2 False False") else "info", out.strip()[:500])


def bundle_facts(app: str, where: str):
    info = sh(f"/usr/libexec/PlistBuddy -c Print {shlex.quote(app + '/Contents/Info.plist')}", quiet=True)[1]
    save(f"info-plist-{where}.txt", info)
    ver = plist(app, "CFBundleShortVersionString")
    bid = plist(app, "CFBundleIdentifier")
    minos = plist(app, "LSMinimumSystemVersion")
    name = plist(app, "CFBundleName")
    icon = plist(app, "CFBundleIconFile")
    icon_ok = any((Path(app) / "Contents/Resources" / f"{icon}{ext}").exists() for ext in ("", ".icns"))
    record(A, "Info.plist identity", "ok" if ver.startswith("1.0.") and bid == BUNDLE_ID else "fail",
           f"name={name} version={ver} build={plist(app, 'CFBundleVersion')} id={bid} LSMinimumSystemVersion={minos} icon={icon} icon_file_present={icon_ok} LSUIElement={plist(app, 'LSUIElement')!r}",
           f"qa/info-plist-{where}.txt")
    # Architecture of every Mach-O, and the highest minimum macOS any of them needs.
    rc, macho = sh(f"find {shlex.quote(app)} -type f \\( -perm -111 -o -name '*.dylib' -o -name '*.so' \\) -print0 | xargs -0 file | grep Mach-O", timeout=300, quiet=True)
    save(f"macho-files-{where}.txt", macho)
    total = len(macho.splitlines())
    # `file` prints one extra line per slice of a universal binary ("(for
    # architecture x86_64)"); those are slices, not x86_64-only files.
    x86_only = [l for l in macho.splitlines() if "x86_64" in l and "arm64" not in l and "(for architecture" not in l]
    universal = [l for l in macho.splitlines() if "universal" in l]
    rc, minos_out = sh(f"find {shlex.quote(app)} -type f \\( -perm -111 -o -name '*.dylib' -o -name '*.so' \\) -print0 | xargs -0 -n 50 otool -l 2>/dev/null | awk '/^\\//{{f=$0}} /minos/{{print $2, f}}' | sort -V | uniq -c | sort -k2 -V | tail -8", timeout=300, quiet=True)
    save(f"macho-minos-{where}.txt", minos_out)
    record(A, "architecture (Apple Silicon only)", "ok" if total and not x86_only else "fail",
           f"Mach-O files={total}; x86_64-only={len(x86_only)}; universal={len(universal)}; examples: {x86_only[:3]}", f"qa/macho-files-{where}.txt")
    top = minos_out.strip().splitlines()[-1] if minos_out.strip() else ""
    record(A, "highest minimum macOS required by any binary vs LSMinimumSystemVersion", "info",
           f"Info.plist says {minos}; top of otool minos list:\n{minos_out.strip()[-1200:]}", f"qa/macho-minos-{where}.txt")
    exe = plist(app, "CFBundleExecutable")
    rc, out = sh(f"lipo -archs {shlex.quote(app + '/Contents/MacOS/' + exe)}; file {shlex.quote(app + '/Contents/MacOS/' + exe)}", quiet=True)
    record(A, "main executable arch (lipo/file)", "ok" if "arm64" in out and "x86_64" not in out else "fail", out.strip())
    rc, cs = sh(f"codesign -dv --verbose=4 {shlex.quote(app)} 2>&1; echo '--- verify'; codesign --verify --deep --strict --verbose=2 {shlex.quote(app)} 2>&1", timeout=300, quiet=True)
    record(A, f"codesign ({where})", "info", cs.strip()[:1500], save(f"codesign-{where}.txt", cs))
    sz = sh(f"du -sh {shlex.quote(app)}", quiet=True)[1].strip()
    record(A, "app bundle size", "info", sz)


def gatekeeper_quarantined():
    dmg = DL / ASSETS[0]
    z = DL / ASSETS[1]
    quarantine(dmg)
    quarantine(z)
    record(A, "simulated browser quarantine on downloads", "info", sh(f"xattr -l {shlex.quote(str(dmg))} {shlex.quote(str(z))}", quiet=True)[1])
    rc, out = sh(f"hdiutil attach {shlex.quote(str(dmg))} -nobrowse -mountpoint /Volumes/APFQ", timeout=180)
    app = "/Volumes/APFQ/" + APPN
    record(A, "mount quarantined DMG", "ok" if rc == 0 else "fail", out[-600:], save("dmg-listing.txt", sh("ls -la /Volumes/APFQ", quiet=True)[1]))
    bundle_facts(app, "dmg")
    xa = sh(f"xattr -l {shlex.quote(app)}", quiet=True)[1]
    rc, sp = sh(f"spctl --assess --type execute -vv {shlex.quote(app)} 2>&1", quiet=True)
    record(A, "Gatekeeper assessment of the app inside the quarantined DMG (spctl)", "info",
           f"spctl rc={rc}: {sp.strip()}\nxattr on app: {xa.strip() or '(none)'}", save("spctl-dmg.txt", sp + "\n" + xa))
    # Double-click from the DMG window.
    sh("log stream --style compact --predicate 'process == \"syspolicyd\"' > " + shlex.quote(str(EV / "syspolicyd-stream-dmg.txt")) + " 2>&1 & echo $! > /tmp/logstream.pid", quiet=True)
    launch_open(app, new=True)
    time.sleep(14)
    s = shot("gatekeeper-open-from-quarantined-dmg")
    running = app_tree()
    sh("kill $(cat /tmp/logstream.pid) 2>/dev/null", quiet=True)
    record(A, "double-click app inside quarantined DMG", "info",
           f"app processes after 14s:\n{fmt_rows(running)}\napi={api('/api/version', timeout=3)[0]}\nsyspolicyd: {gk_logs()[-1500:]}", s)
    kill_all()
    sh("killall CoreServicesUIAgent 2>/dev/null; true", quiet=True)
    # Drag to Applications (Finder copy keeps quarantine) and open.
    sh(f"ditto {shlex.quote(app)} {shlex.quote('/Applications/' + APPN)}", timeout=300)
    xa2 = sh(f"xattr -l {shlex.quote('/Applications/' + APPN)}", quiet=True)[1]
    rc, sp2 = sh(f"spctl --assess --type execute -vv {shlex.quote('/Applications/' + APPN)} 2>&1", quiet=True)
    launch_open("/Applications/" + APPN)
    time.sleep(14)
    s2 = shot("gatekeeper-open-quarantined-in-Applications")
    running = app_tree()
    record(A, "open quarantined copy in /Applications (what a first-time user hits)", "info",
           f"spctl rc={rc}: {sp2.strip()}\nxattr: {xa2.strip()}\nprocesses after 14s:\n{fmt_rows(running)}\napi={api('/api/version', timeout=3)[0]}\nsyspolicyd: {gk_logs()[-1500:]}", s2)
    kill_all()
    sh("killall CoreServicesUIAgent 2>/dev/null; true", quiet=True)
    sh(f"rm -rf {shlex.quote('/Applications/' + APPN)}")
    sh("hdiutil detach /Volumes/APFQ -force", timeout=60)
    # Zip -> ~/Downloads (Archive Utility marks extracted files quarantined).
    sh(f"cd {shlex.quote(str(DL))} && rm -rf zipx && mkdir zipx && ditto -x -k {shlex.quote(str(z))} zipx", timeout=300)
    found = sh(f"find {shlex.quote(str(DL / 'zipx'))} -maxdepth 2 -name '*.app'", quiet=True)[1].strip().splitlines()
    record(A, "zip extracts to an .app", "ok" if found else "fail", "\n".join(found))
    if found:
        zapp = found[0]
        bundle_facts(zapp, "zip")
        sh(f"xattr -w -r com.apple.quarantine {shlex.quote('0083;%x;Safari;%s' % (int(time.time()), str(uuid.uuid4()).upper()))} {shlex.quote(zapp)}", quiet=True)
        rc, sp3 = sh(f"spctl --assess --type execute -vv {shlex.quote(zapp)} 2>&1", quiet=True)
        launch_open(zapp)
        time.sleep(14)
        s3 = shot("gatekeeper-open-quarantined-from-Downloads-zip")
        running = app_tree()
        record(A, "open quarantined zip app from ~/Downloads", "info",
               f"spctl rc={rc}: {sp3.strip()}\nprocesses:\n{fmt_rows(running)}\napi={api('/api/version', timeout=3)[0]}", s3)
        kill_all()
        sh("killall CoreServicesUIAgent 2>/dev/null; true", quiet=True)
        # Emulate the state after "Open Anyway": Gatekeeper off, quarantine still on -> App Translocation.
        rc, gd = sh("sudo spctl --global-disable 2>&1; spctl --status 2>&1", quiet=True)
        launch_open(zapp)
        up = wait_api(90)
        s4 = shot("quarantined-zip-app-with-gatekeeper-disabled")
        running = app_tree()
        transl = any("AppTranslocation" in r["cmd"] for r in running)
        logs_ok = (HOME / ".voice_flow/logs").exists()
        record(A, "run quarantined app from ~/Downloads after Gatekeeper allows it (App Translocation, read-only path)",
               "ok" if up and logs_ok else "fail",
               f"spctl: {gd.strip()}; api up after {up}s; translocated={transl}; ~/.voice_flow/logs exists={logs_ok}\n{fmt_rows(running)}\nlogs: {sh('ls -la ~/.voice_flow/logs', quiet=True)[1][:800]}", s4)
        tr = quit_app()
        record(A, "quit translocated app", "ok" if tr["all_gone"] else "fail", json.dumps(tr))
        kill_all()
        sh("sudo spctl --global-enable 2>&1; spctl --status", quiet=True)
        sh(f"xattr -dr com.apple.quarantine {shlex.quote(zapp)}", quiet=True)
        wipe_user_data()
        # Unquarantined ~/Downloads copy: must not write inside its own bundle.
        marker = EV / "marker-zip"
        marker.write_text("x")
        time.sleep(1)
        launch_open(zapp)
        up = wait_api(90)
        time.sleep(10)
        s5 = shot("running-from-Downloads")
        rc, newer = sh(f"find {shlex.quote(zapp)} -newer {shlex.quote(str(marker))} | head -40", quiet=True)
        running = app_tree()
        record(A, "run from ~/Downloads (no quarantine): starts, logs outside bundle, bundle untouched",
               "ok" if up and not newer.strip() else "fail",
               f"api up after {up}s; files changed in bundle: {newer.strip() or 'none'}\n{fmt_rows(running)}", s5)
        quit_app()
        kill_all()
        wipe_user_data()


def run_from_dmg():
    dmg = DL / "plain.dmg"
    sh(f"cp {shlex.quote(str(DL / ASSETS[0]))} {shlex.quote(str(dmg))} && xattr -c {shlex.quote(str(dmg))}")
    rc, out = sh(f"hdiutil attach {shlex.quote(str(dmg))} -nobrowse -mountpoint /Volumes/APFD", timeout=180)
    app = "/Volumes/APFD/" + APPN
    launch_open(app)
    up = wait_api(90)
    time.sleep(10)
    s = shot("running-straight-from-mounted-DMG")
    running = app_tree()
    logs = sh("ls -la ~/.voice_flow/logs 2>&1; tail -5 ~/.voice_flow/logs/*.log 2>/dev/null | tail -30", quiet=True)[1]
    crash = sh("ls ~/.voice_flow/*crash* ~/.voice_flow/logs/*crash* 2>/dev/null; ls ~/Library/Logs/DiagnosticReports 2>/dev/null | tail -5", quiet=True)[1]
    record(A, "run straight from the mounted (read-only) DMG", "ok" if up else "fail",
           f"api up after {up}s\n{fmt_rows(running)}\nlogs:\n{logs[:1500]}\ncrash files: {crash.strip() or 'none'}", s)
    q = quit_app()
    record(A, "quit app running from DMG", "ok" if q["all_gone"] else "fail", json.dumps(q))
    kill_all()
    rc, out = sh("hdiutil detach /Volumes/APFD", timeout=60)
    record(A, "eject DMG after quitting (nothing holding it open)", "ok" if rc == 0 else "fail", out.strip()[:500])
    sh("hdiutil detach /Volumes/APFD -force 2>/dev/null; true", quiet=True)
    wipe_user_data()


def applications_lifecycle():
    dmg = DL / "plain.dmg"
    sh(f"hdiutil attach {shlex.quote(str(dmg))} -nobrowse -mountpoint /Volumes/APFI", timeout=180)
    app = "/Applications/" + APPN
    sh(f"ditto /Volumes/APFI/{shlex.quote(APPN)} {shlex.quote(app)}", timeout=300)
    sh("hdiutil detach /Volumes/APFI -force", timeout=60)
    marker = EV / "marker-apps"
    marker.write_text("x")
    time.sleep(1)
    net = NetCapture("idle-first-launch").start()
    t = time.time()
    launch_open(app)
    up = wait_api(120)
    record(A, "first launch from /Applications (fresh user): backend ready", "ok" if up else "fail", f"API answered after {up}s")
    time.sleep(15)
    s = shot("first-launch-Applications-30s")
    tree = app_tree()
    record(A, "process tree after first launch", "info", fmt_rows(tree), s)
    code, ver = api("/api/version")
    record(A, "in-app version", "ok" if isinstance(ver, dict) and ver.get("version") == "1.0.2" else "fail", f"{code} {ver}")
    code, upd = api("/api/updates/check?force=1", timeout=30)
    ok = isinstance(upd, dict) and upd.get("update_available") is False and upd.get("latest_version") in ("1.0.2", "v1.0.2")
    record(A, "update checker on 1.0.2", "ok" if ok else ("info" if isinstance(upd, dict) and "rate limit" in str(upd.get("error")) else "fail"), f"{code} {upd}")
    for p in ("/api/platform/info", "/api/platform/permissions", "/api/onboarding/status", "/api/settings/autostart/status",
              "/api/microphones", "/api/settings/hotkey", "/api/downloadable-models/list", "/api/voice-flow-stt/get",
              "/api/voice-flow-polish/get", "/api/video-flow/catalog"):
        code, body = api(p)
        record(A, f"GET {p}", "ok" if code == 200 else "fail", f"{code} {json.dumps(body, default=str)[:1200]}")
    # Video Flow gate at the API.
    for p in ("/api/video-flow/generate", "/api/video-flow/v3/generate", "/api/video-flow/analyze-source"):
        code, body = api(p, {"text": "Photosynthesis turns light into sugar.", "source": "Photosynthesis turns light into sugar."})
        record(A, f"Video Flow gate POST {p}", "ok" if code == 501 else "fail", f"{code} {body}")
    # Idle network for ~90 s more.
    time.sleep(60)
    n = net.stop()
    ips = sorted({x.split(":")[0] for v in n["pktap"].values() for x in v if not x.startswith("dns:")})[:30]
    record(A, "network while idle after first launch (~2 min)", "info",
           f"lsof app connections: {n['lsof_remote']}\npktap by process: {json.dumps(n['pktap'])[:2500]}\nreverse DNS: {json.dumps(resolve_ips(ips))[:1500]}",
           "qa/net-idle-first-launch-summary.json")
    rc, newer = sh(f"find {shlex.quote(app)} -newer {shlex.quote(str(marker))} | head -40", quiet=True)
    record(A, "nothing written inside /Applications bundle while running", "ok" if not newer.strip() else "fail", newer.strip() or "none")
    la = sh("ls -la ~/Library/LaunchAgents; cat ~/Library/LaunchAgents/*productivity* 2>/dev/null | head -40", quiet=True)[1]
    record(A, "login item / LaunchAgent after first launch", "info", la[:1500])
    # Single instance.
    before = len([r for r in app_tree()])
    launch_open(app, new=True)
    time.sleep(12)
    p2 = launch_exec(app, "second-exec")
    time.sleep(12)
    s2 = shot("after-second-launch-attempts")
    rows = app_tree()
    servers = sh("lsof -nP -iTCP:8991 -sTCP:LISTEN", quiet=True)[1]
    second_rc = p2.poll()
    record(A, "single instance: open -n + direct exec while running", "info",
           f"app processes before={before} after={len(rows)}; second exec exit code={second_rc}\nlisteners on 8991:\n{servers}\n{fmt_rows(rows)}\nsecond exec output: {(EV / 'app-stdout-second-exec.txt').read_text(errors='replace')[-800:]}", s2)
    # Settings persistence across restart.
    sets = [("/api/settings/update", {"key": "vf_theme", "value": "dark"}),
            ("/api/settings/update", {"key": "on_screen_ui_theme", "value": "dark"}),
            ("/api/voice-flow-polish/update", {"polishing_enabled": False}),
            ("/api/dictionary/add", {"word": "Kayat"}),
            ("/api/settings/update", {"key": "audio_flow_speed", "value": 1.25})]
    res = [f"{p} {b} -> {api(p, b)}" for p, b in sets]
    record(A, "change settings before restart", "info", "\n".join(res))
    q = quit_app()
    record(A, "normal Quit (Apple Event, like Cmd+Q / Dock Quit)", "ok" if q["all_gone"] else "fail", json.dumps(q))
    if not q["all_gone"]:
        kill_all()
    launch_open(app)
    up = wait_api(120)
    time.sleep(8)
    got = {k: api(f"/api/settings/get?key={k}")[1] for k in ("vf_theme", "on_screen_ui_theme", "polishing_enabled", "audio_flow_speed")}
    dic = api("/api/dictionary")[1]
    has_kayat = "Kayat" in json.dumps(dic)
    ok = (str(got["vf_theme"].get("value")) == "dark" and str(got["polishing_enabled"].get("value")) in ("False", "false")
          and has_kayat)
    record(A, "settings persist across restart", "ok" if ok else "fail", f"relaunch api={up}s; {got}; dictionary has Kayat={has_kayat}", shot("relaunch-dark-theme"))
    api("/api/settings/update", {"key": "vf_theme", "value": "light"})
    api("/api/voice-flow-polish/update", {"polishing_enabled": True})
    # kill -9 the launcher/main process and see what is orphaned.
    tree = app_tree()
    main = [r for r in tree if "Contents/MacOS" in r["cmd"]]
    record(A, "processes before kill -9", "info", fmt_rows(tree))
    if main:
        for r in main:
            sh(f"kill -9 {r['pid']}", quiet=True)
        time.sleep(15)
        left = app_tree()
        record(A, "after kill -9 of the app's main process(es): leftovers", "ok" if not left else "fail",
               fmt_rows(left) + f"\nport 8991: {sh('lsof -nP -iTCP:8991 -sTCP:LISTEN', quiet=True)[1].strip() or 'free'}", shot("after-kill9"))
    kill_all()
    # Logs.
    lg = sh("ls -la ~/.voice_flow/logs; echo; grep -rniE 'windll|Traceback|Error' ~/.voice_flow/logs | grep -v 'error_message' | head -60", quiet=True)[1]
    wd = sh("grep -rn 'windll' ~/.voice_flow/logs | head -20", quiet=True)[1]
    record(A, "logs live in ~/.voice_flow/logs", "ok" if (HOME / ".voice_flow/logs").exists() else "fail", lg[:3000], save("logs-grep.txt", lg))
    record(A, "no windll errors in Mac logs", "ok" if not wd.strip() else "fail", wd.strip()[:1500] or "0 matches")
    sh(f"mkdir -p {shlex.quote(str(EV / 'voice_flow_logs'))} && cp -R ~/.voice_flow/logs/. {shlex.quote(str(EV / 'voice_flow_logs'))}/ 2>/dev/null; true", quiet=True)
    # Uninstall like a user: drag to Trash.
    sh(f"rm -rf {shlex.quote(app)}")
    lo = leftovers()
    record(A, "leftovers after uninstall (app moved to Trash)", "info", lo[:3500], save("uninstall-leftovers.txt", lo))


def main():
    install_watchdog(31)
    for fn in (baseline_from_workflow_launch, downloads, gatekeeper_quarantined, run_from_dmg, applications_lifecycle):
        try:
            log(f"=== {fn.__name__}")
            fn()
        except Exception:
            import traceback
            record(A, fn.__name__, "error", traceback.format_exc()[-2000:])
            try:
                kill_all()
            except Exception:
                pass
    finish("install")


if __name__ == "__main__":
    main()
