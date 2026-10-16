import json, sys, time
from playwright.sync_api import sync_playwright

import os, subprocess
OUTD = os.path.join(os.environ.get("QA_OUT", "out"), "qa", "site"); os.makedirs(OUTD, exist_ok=True)
subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
URL = "https://aiproductivityflow.site/"
res = []

def run(pw, engine, label, viewport, mobile, ua=None):
    try:
        b = getattr(pw, engine).launch()
    except Exception as e:
        res.append({"engine": engine, "label": label, "error": "launch failed: " + str(e).splitlines()[0][:200]})
        return
    ctx = b.new_context(viewport=viewport, is_mobile=mobile if engine != "firefox" else None, has_touch=mobile,
                        user_agent=ua, accept_downloads=True)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.goto(URL, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(2500)
    r = {"engine": engine, "label": label}
    # Mac download links/buttons, visible ones first
    links = pg.evaluate("""() => [...document.querySelectorAll('a[href*="macOS.dmg"], a[href*="macOS.zip"], [data-os=mac]')].map(a => {
        const rc=a.getBoundingClientRect(); return {text:(a.innerText||'').trim().slice(0,50), href:a.getAttribute('href'), vis: rc.width>0 && rc.height>0 && getComputedStyle(a).visibility!=='hidden'}; })""")
    r["mac_links"] = links
    target = None
    for i, l in enumerate(links):
        if l["vis"] and l["href"] and l["href"].endswith(".dmg"):
            target = i; break
    if target is None:
        # scroll to the download section and retry
        pg.evaluate("() => { const a=document.querySelector('a[href*=\"macOS.dmg\"]'); a && a.scrollIntoView(); }")
        pg.wait_for_timeout(1000)
        target = 0
    loc = pg.locator('a[href*="macOS.dmg"]').nth(0)
    try:
        loc.scroll_into_view_if_needed(timeout=5000)
        with pg.expect_download(timeout=60000) as dl_info:
            loc.click(timeout=10000)
        dl = dl_info.value
        r["download_suggested"] = dl.suggested_filename
        r["download_url"] = dl.url
        dl.cancel()
    except Exception as e:
        r["download_error"] = str(e).splitlines()[0][:300]
    pg.wait_for_timeout(1500)
    st = pg.evaluate("""() => { const m=document.getElementById('installHelp'); return {open: !m.hidden && m.classList.contains('is-open'), os: document.getElementById('ihOs').textContent,
        steps: [...document.querySelectorAll('#ihSteps li')].map(l=>l.innerText), retry: document.getElementById('ihRetry').href}; }""")
    r["popup"] = st
    pg.screenshot(path=f"{OUTD}/{engine}-{label}-popup.png")
    try:
        pg.click("#ihPlay", timeout=5000)
    except Exception as e:
        r["play_click_error"] = str(e).splitlines()[0][:200]
    pg.wait_for_timeout(6500)
    v = pg.evaluate("""() => { const v=document.getElementById('ihVideo'); const tt=[...v.textTracks].map(t=>({mode:t.mode, kind:t.kind, cues: t.cues? t.cues.length: null,
        active: t.activeCues && t.activeCues.length ? t.activeCues[0].text : null}));
        return {src: v.currentSrc, readyState: v.readyState, paused: v.paused, t: v.currentTime, muted: v.muted, volume: v.volume, duration: v.duration,
                audioTracks: v.audioTracks ? v.audioTracks.length : 'n/a', webkitAudioDecodedByteCount: v.webkitAudioDecodedByteCount, mozHasAudio: v.mozHasAudio, tracks: tt, err: v.error && v.error.code}; }""")
    r["video_after_6s"] = v
    pg.screenshot(path=f"{OUTD}/{engine}-{label}-playing.png")
    r["page_errors"] = errs[:5]
    res.append(r)
    b.close()

with sync_playwright() as pw:
    iphone = pw.devices["iPhone 13"]
    for eng in ("chromium", "webkit"):
        run(pw, eng, "desktop", {"width": 1440, "height": 900}, False)
        run(pw, eng, "phone", iphone["viewport"], True, iphone["user_agent"])
json.dump(res, open(f"{OUTD}/site_results.json", "w"), indent=2)
print(json.dumps(res, indent=1)[:9000])
