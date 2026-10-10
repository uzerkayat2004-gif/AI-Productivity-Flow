"""Automated macOS walkthrough of the installed AI Productivity Flow app.

Three layers, all fail-soft (a failing step is recorded, never fatal):
  1. Native: screenshots of the real pywebview window and the Tk floating bar,
     plus synthetic mouse clicks/hover where the runner allows them.
  2. UI: the app's real UI + real backend, loaded from the app's own local
     server (127.0.0.1:8991) in Playwright WebKit (the engine behind WKWebView).
  3. API: feature paths that need no microphone (simulated hotkey/recording,
     floating-bar theme, overlay show/hide, permissions, providers...).

usage: walkthrough.py OUT_DIR NATIVE_HELPER
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8991"
OUT = Path(sys.argv[1]).resolve()
HELPER = sys.argv[2]
SHOTS = OUT / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[dict] = []
console: list[dict] = []
http_errors: list[dict] = []
_n = 0


def record(step: str, status: str, note: str = "", shot: str | None = None, **extra) -> None:
    row = {"step": step, "status": status, "note": str(note)[:600], "shot": shot, **extra}
    results.append(row)
    try:
        (OUT / "results.json").write_text(json.dumps(results, indent=2, default=str))
    except Exception:
        pass
    print(f"[{status:>7}] {step}: {row['note']}", flush=True)


def next_name(label: str) -> str:
    global _n
    _n += 1
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)[:60]
    return f"{_n:03d}-{safe}.png"


def native_shot(label: str) -> str:
    name = next_name("native-" + label)
    subprocess.run(["screencapture", "-x", str(SHOTS / name)], check=False)
    return name


def helper(*args: str) -> str:
    try:
        return subprocess.run([HELPER, *args], capture_output=True, text=True, timeout=20).stdout
    except Exception as exc:
        return f"ERR {exc}"


def api(path: str, body: dict | None = None, timeout: float = 20.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:200].decode(errors="replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, str(e)
    except Exception as e:
        return None, repr(e)


def wait_api(seconds: int = 120) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        code, _ = api("/api/runtime", timeout=2)
        if code == 200:
            return True
        time.sleep(2)
    return False


def app_windows() -> list[dict]:
    try:
        rows = json.loads(helper("windows") or "[]")
    except Exception:
        return []
    return [r for r in rows if r.get("name") == "AI Productivity Flow" or "Productivity" in str(r.get("owner"))
            or "python" in str(r.get("owner")).lower()]


def main_window() -> dict | None:
    wins = [w for w in app_windows() if w.get("layer") == 0 and w.get("h", 0) > 300]
    return max(wins, key=lambda w: w["w"] * w["h"]) if wins else None


def bar_windows() -> list[dict]:
    return [w for w in app_windows() if w.get("h", 0) < 120 and w.get("w", 0) < 400]


def crop_bar(src: str, label: str, bar: dict | None) -> str | None:
    try:
        from PIL import Image
        im = Image.open(SHOTS / src).convert("RGB")
        if bar:
            x, y, w, h = bar["x"], bar["y"], bar["w"], bar["h"]
        else:
            x, y, w, h = im.size[0] / 2 - 150, im.size[1] - 120, 300, 60
        box = (int(x - 30), int(y - 20), int(x + w + 30), int(y + h + 20))
        c = im.crop(box)
        c = c.resize((c.size[0] * 4, c.size[1] * 4), Image.NEAREST)
        name = next_name("bar-crop-" + label)
        c.save(SHOTS / name)
        return name
    except Exception as exc:
        record(f"crop {label}", "error", exc)
        return None


def bar_pixels(src: str, bar: dict | None) -> dict:
    try:
        from PIL import Image
        im = Image.open(SHOTS / src).convert("RGB")
        if not bar:
            return {}
        cx, cy = int(bar["x"] + bar["w"] / 2), int(bar["y"] + bar["h"] / 2)
        return {"center": im.getpixel((cx, cy)), "left_quarter": im.getpixel((int(bar["x"] + bar["w"] / 4), cy)),
                "corner": im.getpixel((int(bar["x"] + 1), int(bar["y"] + 1)))}
    except Exception as exc:
        return {"error": repr(exc)}


def describe_color(rgb) -> str:
    try:
        lum = sum(rgb[:3]) / 3
    except Exception:
        return "?"
    return "dark" if lum < 80 else ("light" if lum > 170 else "mid")


def floating_bar(label: str, hover: bool = False) -> None:
    bars = bar_windows()
    bar = min(bars, key=lambda b: b["w"] * b["h"]) if bars else None
    if hover and bar:
        helper("move", str(bar["x"] + bar["w"] / 2), str(bar["y"] + bar["h"] / 2))
        time.sleep(1.5)
        bars = bar_windows()
        bar = max(bars, key=lambda b: b["w"] * b["h"]) if bars else bar
    shot = native_shot("bar-" + label)
    crop = crop_bar(shot, label, bar)
    px = bar_pixels(shot, bar)
    code, status = api("/api/overlay/status")
    color = describe_color(px.get("center")) if px.get("center") else "?"
    record(f"floating bar: {label}", "info" if bar else "missing",
           f"window={bar and {k: bar[k] for k in ('x','y','w','h','alpha','owner')}} color={color} pixels={px} status={status}",
           crop or shot, bar_color=color)
    if hover:
        helper("move", "200", "200")
        time.sleep(1.0)


# ----------------------------------------------------------------------------
def visible_onboarding_next(page):
    """Return (kind, bbox) of the visible forward button on the current tour slide."""
    return page.evaluate("""() => {
      const ov = document.getElementById('onboarding-overlay');
      if (!ov || ov.classList.contains('hidden')) return null;
      const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > 0 && r.top < innerHeight; };
      const btns = [...ov.querySelectorAll('button,[onclick]')].filter(vis);
      const cur = (typeof onboardingSlide === 'number') ? onboardingSlide : -1;
      const pick = btns.find(b => (b.getAttribute('onclick')||'').includes('startOnboardingTour'))
        || btns.find(b => (b.getAttribute('onclick')||'').includes(`gotoOnboardingSlide(${cur+1})`) && !b.closest('.onboarding-dots'))
        || btns.find(b => /finishOnboarding/.test(b.getAttribute('onclick')||'') && !/skip/i.test(b.className + b.textContent));
      if (!pick) return null;
      const r = pick.getBoundingClientRect();
      return {text: pick.textContent.trim().slice(0,60), onclick: pick.getAttribute('onclick'), x: r.x + r.width/2, y: r.y + r.height/2, slide: cur};
    }""")


def ui_state(page) -> dict:
    return page.evaluate("""() => ({
      slide: (typeof onboardingSlide === 'number') ? onboardingSlide : null,
      onboardingVisible: !!document.getElementById('onboarding-overlay') && !document.getElementById('onboarding-overlay').classList.contains('hidden'),
      theme: document.documentElement.getAttribute('data-theme'),
      page: (typeof currentPageId !== 'undefined') ? currentPageId : null,
      toasts: [...document.querySelectorAll('.toast, .vf-toast, [class*=toast]')].map(t => t.textContent.trim()).filter(Boolean).slice(-3),
      openModals: [...document.querySelectorAll('[id$=modal], .modal-overlay, .vf-modal-overlay')].filter(m => { const s = getComputedStyle(m); return s.display !== 'none' && s.visibility !== 'hidden' && m.getBoundingClientRect().height > 0; }).map(m => m.id || m.className).slice(0, 5),
    })""")


def shot(page, label: str, full: bool = False) -> str:
    name = next_name(label)
    try:
        page.screenshot(path=str(SHOTS / name), full_page=full)
    except Exception as exc:
        record(f"screenshot {label}", "error", exc)
    return name


def errors_since(mark: int) -> list[str]:
    return [c["text"][:200] for c in console[mark:] if c["type"] in ("error", "pageerror")]


def step(page, label: str, js: str | None = None, wait: float = 1.5, full: bool = False, check=None):
    mark = len(console)
    herr = len(http_errors)
    try:
        if js:
            page.evaluate(js)
        page.wait_for_timeout(int(wait * 1000))
        name = shot(page, label, full)
        st = ui_state(page)
        errs = errors_since(mark)
        bad_http = http_errors[herr:]
        ok = True
        note = ""
        if check:
            ok, note = check(page, st)
        status = "ok" if ok and not errs else ("js-error" if errs else "fail")
        record(label, status, f"{note} state={st} console_errors={errs[:3]} http_errors={bad_http[:3]}", name)
        return st
    except Exception as exc:
        record(label, "error", "".join(traceback.format_exception_only(type(exc), exc)).strip(), shot(page, label + "-error"))
        return None


def page_check(page_id):
    def _c(page, st):
        vis = page.evaluate(f"""() => {{ const el = document.getElementById('page-{page_id}');
          if (!el) return 'missing'; const s = getComputedStyle(el); const t = el.innerText.trim();
          return s.display === 'none' ? 'hidden' : ('visible:' + t.length + ':' + t.slice(0,80).replace(/\\s+/g,' ')); }}""")
        return str(vis).startswith("visible"), f"page={vis}"
    return _c


def lock_click(page, label: str, selector: str, wait: float = 2.0, win: dict | None = None, check=None):
    """Click the same element natively (real WKWebView window) and in WebKit, screenshot both."""
    loc = page.locator(selector).first
    try:
        loc.wait_for(state="visible", timeout=4000)
        box = loc.bounding_box()
    except Exception as exc:
        record(label, "fail", f"element not visible in WebKit: {selector} ({type(exc).__name__})", shot(page, label + "-missing"))
        return None
    nshot = None
    if win and box:
        helper("click", str(win["x"] + box["x"] + box["width"] / 2), str(win["y"] + 28 + box["y"] + box["height"] / 2))
        time.sleep(wait)
        nshot = native_shot(label)
        helper("move", "1010", "300")
    mark, herr = len(console), len(http_errors)
    blocked = ""
    try:
        loc.click(timeout=5000)
    except Exception as exc:
        blocked = "real click blocked: " + str(exc).splitlines()[0][:200]
    page.wait_for_timeout(int(wait * 1000))
    name = shot(page, label)
    st = ui_state(page)
    errs = errors_since(mark)
    ok, note = (True, "")
    if check:
        ok, note = check(page, st)
    status = "fail" if (blocked or not ok) else ("js-error" if errs else "ok")
    record(label, status, f"{blocked} {note} native_shot={nshot} state={st} console_errors={errs[:3]} http_errors={http_errors[herr:][:3]}", name, native=nshot)
    return st


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not wait_api():
        record("backend API reachable", "fail", "127.0.0.1:8991 never answered /api/runtime")
        return 1
    record("backend API reachable", "ok", api("/api/runtime")[1])
    for p in ("/api/version", "/api/platform/info", "/api/platform/permissions", "/api/overlay/status",
              "/api/microphones", "/api/settings/hotkey", "/api/providers/overview", "/api/audio-providers/overview",
              "/api/video-flow/status", "/api/video-flow/providers", "/api/styles/catalog", "/api/insights",
              "/api/history", "/api/dictionary", "/api/downloadable-models/list", "/api/audio-flow/history",
              "/api/video-flow/history", "/api/settings/autostart/status", "/api/updates/check",
              "/api/video-flow/notebooklm/status", "/api/auth/status"):
        code, body = api(p)
        record(f"API GET {p}", "ok" if code == 200 else "fail", f"HTTP {code}: {json.dumps(body, default=str)[:400]}")

    time.sleep(3)
    win = main_window()
    record("native window found", "ok" if win else "fail", json.dumps(win), native_shot("start"))
    record("AXIsProcessTrusted (runner)", "info", helper("trusted").strip())
    floating_bar("rest-start")
    floating_bar("hover-start", hover=True)

    with sync_playwright() as pw:
        try:
            browser = pw.webkit.launch(timeout=90000)
            record("Playwright WebKit launch", "ok", browser.version)
        except Exception as exc:
            record("Playwright WebKit launch", "fail", f"{exc!r} -> falling back to Chromium")
            browser = pw.chromium.launch(timeout=90000)
        vw, vh = (int(win["w"]), int(win["h"] - 28)) if win else (1160, 732)
        ctx = browser.new_context(viewport={"width": vw, "height": vh})
        page = ctx.new_page()
        page.on("console", lambda m: console.append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: console.append({"type": "pageerror", "text": str(e)}))
        page.on("response", lambda r: http_errors.append(f"{r.status} {r.url.replace(BASE, '')}") if r.status >= 400 else None)
        page.on("requestfailed", lambda r: http_errors.append(f"FAILED {r.url.replace(BASE, '')} {r.failure}"))
        page.goto(BASE + "/index.html", wait_until="load")
        page.wait_for_timeout(6000)

        # ---- Onboarding tour, in WebKit and (where clicks work) natively in lockstep
        st = step(page, "tour scene 1 (welcome)", wait=0.5,
                  check=lambda p, s: (s["onboardingVisible"], "tour visible"))
        native_clicks_work = None
        for i in range(8):
            nxt = visible_onboarding_next(page)
            if not nxt:
                break
            before = native_shot(f"tour-native-before-{i+1}")
            if win and native_clicks_work is not False:
                helper("click", str(win["x"] + nxt["x"]), str(win["y"] + 28 + nxt["y"]))
                time.sleep(2.5)
                after = native_shot(f"tour-native-after-click-{i+1}")
                if native_clicks_work is None:
                    try:
                        from PIL import Image, ImageChops
                        a = Image.open(SHOTS / before).convert("RGB"); b = Image.open(SHOTS / after).convert("RGB")
                        diff = ImageChops.difference(a, b).getbbox()
                        native_clicks_work = diff is not None and (diff[2] - diff[0]) * (diff[3] - diff[1]) > 40000
                    except Exception:
                        native_clicks_work = False
                    record("native synthetic click on tour 'Next'", "ok" if native_clicks_work else "blocked",
                           f"clicked '{nxt['text']}' at window offset ({nxt['x']:.0f},{nxt['y']:.0f}); big screen change={native_clicks_work}", after)
            st = step(page, f"tour click '{nxt['text'][:30]}' (from scene {nxt['slide']+1})",
                      js=f"(() => {{ const b=[...document.querySelectorAll('#onboarding-overlay [onclick]')].find(e => e.getAttribute('onclick')==={json.dumps(nxt['onclick'])} && e.getBoundingClientRect().width>0); b && b.click(); }})()",
                      wait=2.5)
            if st and not st["onboardingVisible"]:
                break
        tour_done = st and not st["onboardingVisible"]
        record("tour reaches the end and closes", "ok" if tour_done else "fail", f"last state={st}")
        # Right after the tour the app auto-starts the Audio Flow feature guide.
        page.wait_for_timeout(1500)
        guide = page.evaluate("""() => { const o=document.getElementById('audioflow-guide-overlay');
          const c=document.getElementById('af-guide-card'); if (!o) return 'missing';
          const s=getComputedStyle(o); const cs=c?getComputedStyle(c):null;
          return {hiddenClass:o.classList.contains('hidden'), display:s.display, position:s.position, zIndex:s.zIndex,
                  cardPosition: cs&&cs.position, cardBackground: cs&&cs.backgroundColor,
                  bodyLocked: document.body.classList.contains('af-guide-active'),
                  guideCssRules: [...document.styleSheets].reduce((n,sh)=>{ try { return n+[...sh.cssRules].filter(r=>(r.selectorText||'').includes('af-guide')).length; } catch(e){ return n; } },0)}; }""")
        record("Audio Flow feature guide after tour", "info", f"{guide}", native_shot("after-tour-guide"))
        shot(page, "after-tour-guide-webkit")
        lock_click(page, "after tour: click 'Video Flow' in sidebar (is app usable?)", ".sidebar .nav-item[data-page=videoflow]",
                   win=win, check=lambda p, s: (s["page"] == "videoflow", f"page={s['page']}"))
        lock_click(page, "close the Audio Flow guide (its X button)", ".af-guide-close-btn", win=win,
                   check=lambda p, s: (p.evaluate("!document.body.classList.contains('af-guide-active')"), "guide closed"))
        page.evaluate("() => { try { stopAudioFlowGuide(); } catch(e){} const b=[...document.querySelectorAll('button')].find(b=>/No Thanks/i.test(b.textContent) && b.getBoundingClientRect().width>0); b && b.click(); }")
        page.wait_for_timeout(800)
        step(page, "main app after onboarding", wait=1.5)

        # Replay from the sidebar + Skip Tour, as a user would (native + WebKit)
        lock_click(page, "replay tour (sidebar 'Welcome Tour')", ".sidebar .nav-item[onclick*=replayOnboarding]", win=win,
                   check=lambda p, s: (s["onboardingVisible"], "tour visible again"))
        lock_click(page, "Skip Tour", "#onboarding-overlay .scene1-skip-badge:visible", win=win,
                   check=lambda p, s: (not s["onboardingVisible"], "tour closed by Skip"))
        page.evaluate("() => { try { stopAudioFlowGuide(); } catch(e){} const b=[...document.querySelectorAll('button')].find(b=>/No Thanks/i.test(b.textContent) && b.getBoundingClientRect().width>0); b && b.click(); }")
        # Also visit each scene directly (covers scenes the Next path may skip)
        page.evaluate("replayOnboarding()")
        for i in range(5):
            step(page, f"tour scene {i+1} (direct)", js=f"gotoOnboardingSlide({i})", wait=2.0,
                 check=lambda p, s, i=i: (s["slide"] == i, f"slide={s['slide']}"))
        page.evaluate("finishOnboarding()")
        page.evaluate("() => { try { stopAudioFlowGuide(); } catch(e){} const b=[...document.querySelectorAll('button')].find(b=>/No Thanks/i.test(b.textContent) && b.getBoundingClientRect().width>0); b && b.click(); }")
        page.wait_for_timeout(800)

        # ---- The native window is now stuck behind the unstyled guide. Restart the app
        # (what a stuck user would do) so the native sidebar can be exercised.
        app_path = os.environ.get("APP_PATH")
        if app_path and win:
            subprocess.run(["pkill", "-f", "AI Productivity Flow.app/Contents"], check=False)
            t0 = time.time()
            while time.time() - t0 < 30 and subprocess.run(["pgrep", "-f", "AI Productivity Flow.app/Contents"], capture_output=True).returncode == 0:
                time.sleep(1)
            still = subprocess.run(["pgrep", "-fl", "AI Productivity Flow.app/Contents"], capture_output=True, text=True).stdout
            subprocess.run(["pkill", "-9", "-f", "AI Productivity Flow.app/Contents"], check=False)
            while time.time() - t0 < 60 and subprocess.run(["lsof", "-nP", "-iTCP:8991", "-sTCP:LISTEN"], capture_output=True).returncode == 0:
                time.sleep(1)
            record("quit app before restart", "info", f"exited after SIGTERM in {time.time()-t0:.0f}s; still running after 30s: {still.strip()[:300] or 'none'}")
            exe = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print CFBundleExecutable", f"{app_path}/Contents/Info.plist"],
                                 capture_output=True, text=True).stdout.strip()
            ok, win2 = False, None
            for attempt in (1, 2):
                subprocess.Popen([f"{app_path}/Contents/MacOS/{exe}"], stdout=open(OUT / f"app-stdout-relaunch{attempt}.txt", "w"),
                                 stderr=subprocess.STDOUT, start_new_session=True)
                ok = wait_api(90)
                time.sleep(12)
                win2 = main_window()
                record(f"restart app (stuck-user path), attempt {attempt}", "ok" if ok and win2 else "fail",
                       f"api={ok} window={win2}", native_shot(f"after-restart-{attempt}"))
                if ok and win2:
                    break
                time.sleep(10)
            if win2:
                win = win2
            floating_bar("rest-after-restart")
            if not (ok and win2):
                raise RuntimeError("app did not come back after restart; skipping native sidebar checks")
            page.reload(wait_until="load")
            page.wait_for_timeout(5000)
            page.evaluate("() => { try { stopAudioFlowGuide(); } catch(e){} try { switchPage('audioflow'); } catch(e){} }")
            page.wait_for_timeout(800)

        # ---- real sidebar clicks, native + WebKit side by side
        for pid in ["audioflow", "videoflow", "home", "insights", "dictionary", "style", "providers"]:
            lock_click(page, f"sidebar click {pid}", f".sidebar .nav-item[data-page={pid}]", win=win,
                       check=lambda p, s, pid=pid: (s["page"] == pid, f"page={s['page']}"))
        lock_click(page, "sidebar click Settings", ".sidebar .nav-item[onclick*=openSettings]", win=win,
                   check=lambda p, s: ("settings-modal" in s["openModals"], f"modals={s['openModals']}"))
        for tab in ("system", "account", "general"):
            lock_click(page, f"settings tab {tab}", f"#settings-nav-{tab}", win=win)
        page.keyboard.press("Escape")
        page.evaluate("try { closeSettings(); } catch(e){}")
        page.wait_for_timeout(800)
        if win:
            helper("click", "1000", "200")  # click empty area; Escape may not reach the native window
        lock_click(page, "sidebar dark-mode toggle", "#theme-toggle-nav", win=win,
                   check=lambda p, s: (s["theme"] == "dark", f"theme={s['theme']}"))
        lock_click(page, "sidebar light-mode toggle", "#theme-toggle-nav", win=win,
                   check=lambda p, s: (s["theme"] == "light", f"theme={s['theme']}"))

        # ---- every page, light then dark
        pages = ["audioflow", "videoflow", "home", "insights", "dictionary", "style", "providers"]
        for theme in ("light", "dark"):
            if theme == "dark":
                step(page, "dark mode toggle", js="toggleTheme()", wait=1.5,
                     check=lambda p, s: (s["theme"] == "dark", f"theme={s['theme']}"))
            for pid in pages:
                step(page, f"page {pid} ({theme})", js=f"switchPage('{pid}')", wait=2.0, full=True, check=page_check(pid))
            for tab in ("general", "system", "account"):
                step(page, f"settings {tab} ({theme})", js=f"openSettings('{tab}')", wait=1.8)
            page.evaluate("closeSettings()")
        step(page, "light mode toggle back", js="toggleTheme()", wait=1.5,
             check=lambda p, s: (s["theme"] == "light", f"theme={s['theme']}"))

        # ---- dialogs / sub-pages
        dialogs = [
            ("hotkey / shortcut dialog", "openSettings('general'); openShortcutDialog()"),
            ("microphone dialog", "openMicrophoneDialog()"),
            ("account dialog", "openAccountModal('account')"),
            ("macOS permissions dialog", "(() => { const m=document.getElementById('vf-macos-permissions-modal'); initMacOSPermissionsOnboarding(); setTimeout(()=>{ if (m && m.style.display!=='flex') { m.style.display='flex'; } }, 800); })()"),
            ("Voice Flow model picker", "switchPage('providers'); openVoiceFlowModelPicker()"),
            ("Voice Flow add connection", "switchPage('providers'); openAddConnectionModal()"),
            ("Audio Flow voice model picker", "switchPage('audioflow'); openAudioVoiceModelPicker()"),
            ("Audio Flow summary model picker", "switchPage('audioflow'); openAudioSummaryModelPicker()"),
            ("Audio Flow add connection", "switchPage('audioflow'); openAddAudioConnectionModal()"),
            ("Video Flow model picker", "switchPage('videoflow'); openVideoModelPicker()"),
            ("Video Flow add connection", "switchPage('videoflow'); openVideoConnectionModal()"),
        ]
        for label, js in dialogs:
            st = step(page, label, js=js, wait=2.0)
            page.keyboard.press("Escape")
            page.evaluate("""() => {
              const vis = m => { const s = getComputedStyle(m); return s.display !== 'none' && s.visibility !== 'hidden' && m.getBoundingClientRect().height > 0; };
              document.querySelectorAll('[id$=modal]').forEach(m => { if (!vis(m) || m.id === 'settings-modal') return;
                for (const f of ['closeSubModal', 'closeVideoModal']) { try { window[f](m.id); } catch(e){} } });
              for (const f of ['closeSharedModelPicker', 'closeAccountModal', 'hideMacOSPermissionsModal', 'closeOAuthModal', 'closeSettings']) { try { window[f](); } catch(e){} }
              document.querySelectorAll('[id$=modal]').forEach(m => { if (vis(m) && m.id !== 'settings-modal') m.style.display='none'; }); }""")
            page.wait_for_timeout(400)

        # ---- Video Flow: paste text and press generate (needs provider/NotebookLM)
        sample = ("Photosynthesis is how plants turn sunlight, water and carbon dioxide into sugar and oxygen. "
                  "It happens in the chloroplasts. Light reactions make ATP; the Calvin cycle builds glucose.")
        step(page, "Video Flow: paste sample text", js=f"""switchPage('videoflow'); const t=document.getElementById('vf-source-input');
             if (t) {{ t.value={json.dumps(sample)}; t.dispatchEvent(new Event('input', {{bubbles:true}})); }}""", wait=1.5, full=True)
        step(page, "Video Flow: generate (as shipped)", js="generateVideoFlow()", wait=4.0, full=True)
        btn = page.evaluate("() => { const b=document.getElementById('vf-generate-button'); return b ? {disabled: b.disabled, text: b.textContent.trim().slice(0,40)} : null; }")
        record("Video Flow: Generate button after the click", "info", f"{btn}")
        step(page, "Video Flow: generate (test workaround: define vfSelectedStyle)",
             js="window.vfSelectedStyle = window.vfSelectedStyle || 'auto'; const b=document.getElementById('vf-generate-button'); if (b) b.disabled=false; generateVideoFlow()",
             wait=10.0, full=True)
        code, body = api("/api/video-flow/jobs/status")
        record("Video Flow job status after generate", "info", f"HTTP {code}: {json.dumps(body, default=str)[:500]}")

        # ---- Hands-free recording / simulated hotkey via the same API the UI uses
        for theme in ("light", "dark"):
            code, body = api("/api/settings/on-screen-ui-theme", {"theme": theme})
            record(f"floating bar theme -> {theme}", "ok" if code == 200 else "fail", f"HTTP {code}: {body}")
            time.sleep(1.5)
            floating_bar(f"theme-{theme}-rest")
            floating_bar(f"theme-{theme}-hover", hover=True)
        api("/api/settings/on-screen-ui-theme", {"theme": "light"})
        code, body = api("/api/record/toggle", {"recording": True})
        record("simulated dictation start (record toggle on)", "ok" if code == 200 else "fail", f"HTTP {code}: {body}")
        for t in (1, 3):
            time.sleep(t)
            floating_bar(f"recording-{t}s")
        code, body = api("/api/record/toggle", {"recording": False})
        record("simulated dictation stop (record toggle off)", "ok" if code == 200 else "fail", f"HTTP {code}: {body}")
        time.sleep(3)
        floating_bar("after-recording")
        step(page, "Voice Flow home after simulated dictation", js="switchPage('home')", wait=2.0, full=True)

        # ---- overlay controls
        for ep in ("/api/overlay/hide", "/api/overlay/show", "/api/overlay/reset-position"):
            code, body = api(ep, {})
            time.sleep(1.5)
            record(f"API POST {ep}", "ok" if code == 200 else "fail", f"HTTP {code}: {body}")
            floating_bar(ep.rsplit('/', 1)[-1])

        # ---- click the floating bar itself ("Click to speak")
        bars = bar_windows()
        if bars:
            b = bars[0]
            helper("move", str(b["x"] + b["w"] / 2), str(b["y"] + b["h"] / 2))
            time.sleep(1.0)
            helper("click", str(b["x"] + b["w"] / 2), str(b["y"] + b["h"] / 2))
            time.sleep(2.0)
            code, st = api("/api/overlay/status")
            record("native click on the floating bar", "info", f"overlay status after click={st}")
            floating_bar("after-bar-click")
            api("/api/record/toggle", {"recording": False})

        # ---- native window at the end (did the real app window survive all this?)
        record("native window at end", "info", json.dumps(main_window()), native_shot("end"))
        browser.close()
    return 0


if __name__ == "__main__":
    import signal

    def _timeout(*_):
        raise TimeoutError("walkthrough watchdog (25 min) fired")
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(25 * 60)
    rc = 1
    try:
        rc = main()
    except Exception:
        record("walkthrough crashed", "error", traceback.format_exc())
    finally:
        (OUT / "results.json").write_text(json.dumps(results, indent=2, default=str))
        (OUT / "console.json").write_text(json.dumps(console, indent=2))
        (OUT / "http-errors.json").write_text(json.dumps(http_errors, indent=2))
        counts: dict[str, int] = {}
        for r in results:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        lines = ["# macOS walkthrough summary", "", f"counts: {counts}", "", "| # | step | status | shot | note |", "|---|---|---|---|---|"]
        for i, r in enumerate(results, 1):
            lines.append(f"| {i} | {r['step']} | {r['status']} | {r['shot'] or ''} | {r['note'][:220].replace('|', '/')} |")
        (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    sys.exit(0)
