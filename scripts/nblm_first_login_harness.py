"""Headless reproduction of the NotebookLM first sign-in bug (dev tool, not shipped).

Runs the REAL ``notebooklm login`` (notebooklm-py 0.8.2) in a headless Chromium
whose network is faked with Playwright routes, emulating what Google does today:

* ``https://notebook.google.com/`` answers a signed-out visitor with HTTP 200
  (an anonymous landing page), not a redirect to sign-in.
* ``accounts.google.com/ServiceLogin`` "signs the user in" after a delay and
  redirects through ``/SetSID`` which sets ``SID`` / ``__Secure-1PSID`` /
  ``APISID`` / ``SAPISID`` on ``.google.com`` (optionally ``__Secure-1PSIDTS``
  only later), then returns to the app host.

Usage (in an env with notebooklm-py[browser]==0.8.2 and a Chromium):

    python scripts/nblm_first_login_harness.py --mode baseline   # unpatched CLI
    python scripts/nblm_first_login_harness.py --mode shim       # first_login_shim
    [--no-psidts] [--chromium /usr/bin/chromium]

Prints the cookie NAMES saved to storage_state.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHIM_DIR = HERE.parent / "src" / "voice_flow" / "video_flow_engine" / "notebooklm"


def install_fake_google(chromium: str, *, psidts: bool) -> None:
    from playwright.sync_api._generated import BrowserType

    original = BrowserType.launch_persistent_context

    def launch(self, *args, **kwargs):
        kwargs["headless"] = True
        kwargs.pop("channel", None)
        kwargs["executable_path"] = chromium
        args_list = list(kwargs.get("args") or [])
        kwargs["args"] = args_list + ["--no-sandbox", "--no-proxy-server"]
        context = original(self, *args, **kwargs)
        signed_in = {"value": False}

        def handle(route):
            url = route.request.url
            if url.startswith("https://accounts.google.com/ServiceLogin"):
                # The "human" signs in: a 2 s pause, then Google's redirect chain.
                body = ('<html><head><meta http-equiv="refresh" content="2;url='
                        'https://accounts.google.com/SetSID"></head><body>Sign in</body></html>')
                return route.fulfill(status=200, body=body, content_type="text/html")
            if url.startswith("https://accounts.google.com/SetSID"):
                signed_in["value"] = True
                cookies = ["SID=fake-sid", "__Secure-1PSID=fake-1psid", "HSID=h", "SSID=s",
                           "APISID=a", "SAPISID=sa"]
                if psidts:
                    cookies.append("__Secure-1PSIDTS=fake-ts")
                headers = [("location", "https://notebook.google.com/")]
                for c in cookies:
                    secure = "; Secure" if c.startswith(("__Secure", "SAPISID", "SSID")) else ""
                    headers.append(("set-cookie", f"{c}; Domain=.google.com; Path=/{secure}; HttpOnly; Max-Age=86400"))
                # route.fulfill takes a dict; repeated set-cookie must be joined by newline
                hdrs = {"set-cookie": "\n".join(v for k, v in headers if k == "set-cookie")}
                body = ('<html><head><meta http-equiv="refresh" content="0;url='
                        'https://notebook.google.com/"></head><body>ok</body></html>')
                return route.fulfill(status=200, headers=hdrs, body=body, content_type="text/html")
            if url.startswith("https://accounts.google.com/"):
                return route.fulfill(status=200, body="<html>accounts</html>", content_type="text/html")
            if url.startswith("https://notebook.google.com/") or url.startswith("https://notebooklm.google.com/"):
                if signed_in["value"]:
                    hdrs = {"set-cookie": "OSID=fake-osid; Domain=notebook.google.com; Path=/; Secure; HttpOnly; Max-Age=86400"}
                    return route.fulfill(status=200, headers=hdrs, body="<html>app</html>", content_type="text/html")
                return route.fulfill(status=200, body="<html><title>Gemini Notebook</title>landing</html>",
                                     content_type="text/html")
            return route.fulfill(status=204, body="")

        context.route("**/*", handle)
        return context

    BrowserType.launch_persistent_context = launch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "shim"), required=True)
    parser.add_argument("--no-psidts", action="store_true")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    ns = parser.parse_args()

    home = Path(tempfile.mkdtemp(prefix="nblm-harness-"))
    os.environ["NOTEBOOKLM_HOME"] = str(home)
    storage = home / "storage_state.json"
    install_fake_google(ns.chromium, psidts=not ns.no_psidts)
    # The bundled Playwright browser is not needed: we launch --chromium.
    import notebooklm._auth.browser_capture as _bc
    import notebooklm.cli.services.playwright_login as _pl
    for _mod in (_bc, _pl):
        for _name in ("ensure_playwright_available", "ensure_chromium_installed"):
            if hasattr(_mod, _name):
                setattr(_mod, _name, lambda *a, **k: None)
    argv = ["--storage", str(storage), "login", "--browser", "chromium", "--browser-timeout", "60"]
    code = 0
    try:
        if ns.mode == "shim":
            sys.path.insert(0, str(SHIM_DIR))
            import first_login_shim

            first_login_shim.main(argv)
        else:
            from notebooklm.notebooklm_cli import main as cli_main

            sys.argv = ["notebooklm", *argv]
            cli_main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    names: list[str] = []
    found = sorted(home.rglob("storage_state.json"))
    storage = storage if storage.is_file() else (found[0] if found else storage)
    if storage.is_file():
        data = json.loads(storage.read_text(encoding="utf-8"))
        names = sorted({c.get("name") for c in data.get("cookies", []) if c.get("value")})
    print(json.dumps({"mode": ns.mode, "exit": code, "saved_cookie_names": names,
                      "has_SID": "SID" in names}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
