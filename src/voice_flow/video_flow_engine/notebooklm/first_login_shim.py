"""Run ``notebooklm login`` with a first-sign-in guard.

Run as a script by the CLI's own interpreter (``python first_login_shim.py
--profile P login --browser chrome ...``). It must not import ``voice_flow``:
the CLI runtime may not have it on ``sys.path``.

Why this exists (notebooklm-py 0.8.2, ``_auth/browser_capture.py``):

* The personal app host (``notebooklm.google.com`` now 301-redirects to
  ``notebook.google.com``) answers a SIGNED-OUT visitor with an HTTP 200
  "Gemini Notebook" landing page instead of a redirect to accounts.google.com.
* ``run_browser_capture`` navigates there first and, when the page is on the
  app host, prints "Already logged in." and captures cookies straight away.
  It only checks the host, never whether a Google ``SID`` cookie exists.
* For a brand-new user (fresh browser profile) that capture has no ``SID`` and
  no ``__Secure-1PSIDTS``. The CLI exits 0, the app's ``auth check --test``
  then fails with "Missing required cookies: SID, __Secure-1PSIDTS".

notebooklm-py 0.8.5 fixed this upstream (#2467/#2472: steer an SID-less app
landing to ``ServiceLogin`` and wait for a routed ``SID``), but 0.8.5 also moves
to FastMCP 4 / MCP 2, which is too large a change for this release. This shim
backports the behaviour onto 0.8.2:

1. "Already logged in" (and the final landing check) now also require a
   ``SID`` cookie for the app URL.
2. The login wait first steers an SID-less landing page to Google's sign-in
   (``accounts.google.com/ServiceLogin?continue=<app>/``), then, once the app
   host is reached, polls up to 60 s for ``SID`` (and briefly for
   ``__Secure-1PSIDTS``, which Google may set late; the library heals it via
   RotateCookies when SID and a secondary binding exist).

Every step logs ``[nblm-login]`` lines to stderr with cookie NAMES only.
Any patching failure falls back to the unmodified CLI.
"""

from __future__ import annotations

import sys
import time
from typing import Any
from urllib.parse import urlencode, urlparse

LOG_PREFIX = "[nblm-login]"
SID_SETTLE_SECONDS = 60.0
PSIDTS_SETTLE_SECONDS = 10.0
POLL_MS = 500
MAX_STEERS = 2
_AUTH_NAMES = (
    "SID", "__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-3PSID", "__Secure-3PSIDTS",
    "HSID", "SSID", "APISID", "SAPISID", "OSID", "__Secure-OSID", "LSID",
)

_STATE: dict[str, Any] = {"context": None, "steers": 0}


def log(message: str) -> None:
    try:
        sys.stderr.write(f"{LOG_PREFIX} {message}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def cookie_names(cookies: Any) -> list[str]:
    names: set[str] = set()
    for cookie in cookies or []:
        if isinstance(cookie, dict) and cookie.get("name") and cookie.get("value"):
            names.add(str(cookie["name"]))
    return sorted(names)


def auth_names(cookies: Any) -> list[str]:
    present = set(cookie_names(cookies))
    return [name for name in _AUTH_NAMES if name in present]


def has_sid(cookies: Any) -> bool:
    for cookie in cookies or []:
        if not isinstance(cookie, dict) or cookie.get("name") != "SID" or not cookie.get("value"):
            continue
        domain = str(cookie.get("domain") or "").lower().lstrip(".")
        if domain == "google.com" or domain.startswith("google.") or domain.endswith(".google.com"):
            return True
    return False


def _url_cookies(context: Any, url: str) -> list[dict[str, Any]]:
    try:
        return list(context.cookies([url]) if url else context.cookies())
    except Exception:
        return []


def _context_for(page: Any = None) -> Any:
    if page is not None:
        try:
            return page.context
        except Exception:
            pass
    return _STATE.get("context")


def _page_url(page: Any) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def install(bc: Any, *, base_url_fn: Any, accounts_url: str) -> bool:
    """Patch a notebooklm 0.8.2 ``browser_capture`` module. Returns True on success."""
    original_matches = getattr(bc, "url_matches_base_host", None)
    original_wait = getattr(bc, "wait_for_login_landing", None)
    if not callable(original_matches) or not callable(original_wait) or not hasattr(bc, "run_browser_capture"):
        log("library layout not recognised; running the CLI unchanged")
        return False

    def url_matches_base_host(url: str) -> bool:
        if not original_matches(url):
            return False
        # Only the capture decisions inside run_browser_capture ("Already logged
        # in", and the final landing check) need the SID gate. Playwright's
        # wait_for_url predicate must stay a pure host check.
        try:
            caller = sys._getframe(1).f_code.co_name
        except Exception:
            caller = ""
        if caller != "run_browser_capture":
            return True
        context = _STATE.get("context")
        if context is None:
            return True
        cookies = _url_cookies(context, url)
        ok = has_sid(cookies)
        log(f"app host reached ({_host(url)}); auth cookies present: {auth_names(cookies) or 'none'}"
            + ("" if ok else " -> no SID yet, not treating this as signed in"))
        return ok

    def steer_to_sign_in(page: Any, deadline: float) -> None:
        if _STATE["steers"] >= MAX_STEERS:
            return
        remaining_ms = (deadline - time.monotonic()) * 1000
        if remaining_ms <= 0:
            return
        _STATE["steers"] += 1
        continuation = urlencode({"continue": f"{base_url_fn()}/"})
        log("signed-out NotebookLM landing page; opening Google sign-in")
        try:
            page.goto(f"{accounts_url}ServiceLogin?{continuation}", wait_until="commit", timeout=remaining_ms)
        except Exception as exc:  # a superseded navigation is fine; the wait re-reads the URL
            log(f"sign-in navigation did not commit cleanly ({type(exc).__name__}); still waiting")

    def wait_for_login_landing(page: Any, *, timeout_s: float, io: Any = None, **kwargs: Any) -> int:
        deadline = time.monotonic() + float(timeout_s)
        context = _context_for(page)
        tolerated = 0
        url = _page_url(page)
        if original_matches(url) and not has_sid(_url_cookies(context, url)):
            steer_to_sign_in(page, deadline)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                from playwright.sync_api import TimeoutError as PlaywrightTimeout
                log("timed out waiting for Google sign-in; no SID cookie")
                raise PlaywrightTimeout(f"Timeout {float(timeout_s) * 1000:.0f}ms exceeded.")
            tolerated += int(original_wait(page, timeout_s=remaining, io=io, **kwargs) or 0)
            # On the app host. Give Google's redirect chain time to set SID.
            settle_until = min(deadline, time.monotonic() + SID_SETTLE_SECONDS)
            cookies: list[dict[str, Any]] = []
            while True:
                url = _page_url(page)
                cookies = _url_cookies(context, url) if original_matches(url) else []
                if has_sid(cookies) or not original_matches(url) or time.monotonic() >= settle_until:
                    break
                page.wait_for_timeout(POLL_MS)
            if has_sid(cookies):
                psidts_until = min(deadline, time.monotonic() + PSIDTS_SETTLE_SECONDS)
                while "__Secure-1PSIDTS" not in cookie_names(cookies) and time.monotonic() < psidts_until:
                    page.wait_for_timeout(POLL_MS)
                    cookies = _url_cookies(context, _page_url(page))
                names = auth_names(cookies)
                log(f"signed in; auth cookies present: {names}")
                if "__Secure-1PSIDTS" not in names:
                    log("__Secure-1PSIDTS not set yet; the CLI will mint it from SID on first use")
                return tolerated
            if not original_matches(url):
                continue  # left the app host (e.g. user clicked Sign in): wait for the return
            log(f"on {_host(url)} without SID after {SID_SETTLE_SECONDS:.0f}s; auth cookies: "
                f"{auth_names(cookies) or 'none'}")
            if _STATE["steers"] < MAX_STEERS:
                steer_to_sign_in(page, deadline)
                continue
            # Still on the anonymous landing. Wait for the user to click Sign in.
            while original_matches(_page_url(page)) and time.monotonic() < deadline:
                if has_sid(_url_cookies(context, _page_url(page))):
                    break
                page.wait_for_timeout(1000)

    bc.url_matches_base_host = url_matches_base_host
    bc.wait_for_login_landing = wait_for_login_landing
    return True


def _record_contexts() -> None:
    from playwright.sync_api._generated import BrowserType

    original = BrowserType.launch_persistent_context
    if getattr(original, "_nblm_shim", False):
        return

    def launch_persistent_context(self: Any, *args: Any, **kwargs: Any) -> Any:
        context = original(self, *args, **kwargs)
        _STATE["context"] = context
        return context

    launch_persistent_context._nblm_shim = True  # type: ignore[attr-defined]
    BrowserType.launch_persistent_context = launch_persistent_context  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        from notebooklm._auth import browser_capture as bc
        from notebooklm.config import get_base_url

        accounts = str(getattr(bc, "GOOGLE_ACCOUNTS_URL", "") or "https://accounts.google.com/")
        _record_contexts()
        if install(bc, base_url_fn=get_base_url, accounts_url=accounts):
            log("first-sign-in guard active")
    except Exception as exc:
        log(f"guard not installed ({type(exc).__name__}); running the CLI unchanged")
    sys.argv = ["notebooklm", *args]
    try:
        from notebooklm.notebooklm_cli import main as cli_main
    except ImportError:
        # Any other layout: behave exactly like ``python -m notebooklm``.
        import runpy

        runpy.run_module("notebooklm", run_name="__main__", alter_sys=True)
        return
    cli_main()


if __name__ == "__main__":
    main()
