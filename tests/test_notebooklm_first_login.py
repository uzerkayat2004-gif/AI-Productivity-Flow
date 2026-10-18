"""First-time NotebookLM sign-in: the signed-out landing page must not be captured.

Root cause (notebooklm-py 0.8.2, ``_auth/browser_capture.py``): the app host
answers a signed-out visitor with HTTP 200, and ``run_browser_capture`` treats
any app-host landing as "Already logged in", so a brand-new user's session is
saved without ``SID`` / ``__Secure-1PSIDTS``. ``first_login_shim`` backports
the 0.8.5 fix. These tests drive the shim with fake Playwright objects that
simulate Google's timing (delayed cookies, no PSIDTS, cookies only on
``.google.com``). ``scripts/nblm_first_login_harness.py`` runs the real CLI
headlessly for an end-to-end check.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.notebooklm import login_flow

SHIM_PATH = Path(login_flow.__file__).with_name("first_login_shim.py")
APP = "https://notebook.google.com/"


def _load_shim():
    spec = importlib.util.spec_from_file_location("first_login_shim_under_test", SHIM_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _cookie(name, domain=".google.com"):
    return {"name": name, "value": f"v-{name}", "domain": domain, "path": "/"}


GOOGLE_SESSION = [_cookie(n) for n in ("SID", "__Secure-1PSID", "HSID", "SSID", "APISID", "SAPISID")]


class FakeContext:
    """Cookies appear only after sign-in, optionally a few polls later."""

    def __init__(self, page):
        self.page = page
        self.signed_in = False
        self.delay_polls = 0
        self.with_psidts = True
        self.psidts_delay_polls = 0
        self.polls = 0

    def cookies(self, urls=None):
        if not self.signed_in or self.polls < self.delay_polls:
            return []
        jar = list(GOOGLE_SESSION)
        if self.with_psidts and self.polls >= self.psidts_delay_polls:
            jar.append(_cookie("__Secure-1PSIDTS"))
        jar.append(_cookie("OSID", domain="notebook.google.com"))
        return jar


class FakePage:
    def __init__(self, url=APP):
        self.url = url
        self.context = FakeContext(self)
        self.gotos: list[str] = []
        self.waited_ms = 0

    def goto(self, url, **kwargs):
        self.gotos.append(url)
        # The user completes Google sign-in; Google returns to the app host.
        self.context.signed_in = True
        self.url = APP

    def wait_for_timeout(self, ms):
        self.waited_ms += ms
        self.context.polls += 1


def _fake_bc(original_wait=None):
    bc = types.SimpleNamespace()
    bc.GOOGLE_ACCOUNTS_URL = "https://accounts.google.com/"
    bc.url_matches_base_host = lambda url: (url or "").startswith(APP)
    bc.wait_for_login_landing = original_wait or (lambda page, *, timeout_s, io=None: 0)
    bc.run_browser_capture = lambda *a, **k: None
    return bc


@pytest.fixture()
def shim():
    module = _load_shim()
    module.POLL_MS = 1
    return module


def _install(shim, bc, page):
    assert shim.install(bc, base_url_fn=lambda: "https://notebook.google.com", accounts_url=bc.GOOGLE_ACCOUNTS_URL)
    shim._STATE["context"] = page.context


def test_signed_out_landing_is_not_already_logged_in(shim):
    bc, page = _fake_bc(), FakePage()
    _install(shim, bc, page)

    def run_browser_capture():  # same frame name the gate keys on
        return bc.url_matches_base_host(page.url)

    assert run_browser_capture() is False
    # Playwright's wait predicate (any other caller) stays a pure host check.
    assert bc.url_matches_base_host(page.url) is True
    page.context.signed_in = True
    assert run_browser_capture() is True


def test_first_sign_in_steers_to_google_and_waits_for_delayed_sid(shim, capsys):
    bc, page = _fake_bc(), FakePage()
    _install(shim, bc, page)
    page.context.delay_polls = 5  # SID lands a few polls after the app host

    bc.wait_for_login_landing(page, timeout_s=30)

    assert len(page.gotos) == 1
    assert page.gotos[0].startswith("https://accounts.google.com/ServiceLogin?continue=")
    assert "notebook.google.com" in page.gotos[0]
    assert shim.has_sid(page.context.cookies([APP]))
    err = capsys.readouterr().err
    assert "[nblm-login] signed-out NotebookLM landing page" in err
    assert "[nblm-login] signed in; auth cookies present:" in err
    assert "v-SID" not in err  # names only, never values


def test_missing_psidts_is_not_fatal(shim, capsys):
    bc, page = _fake_bc(), FakePage()
    _install(shim, bc, page)
    page.context.with_psidts = False

    assert bc.wait_for_login_landing(page, timeout_s=30) == 0
    err = capsys.readouterr().err
    assert "__Secure-1PSIDTS not set yet" in err


def test_late_psidts_is_waited_for_briefly(shim, capsys):
    bc, page = _fake_bc(), FakePage()
    _install(shim, bc, page)
    page.context.psidts_delay_polls = 3

    bc.wait_for_login_landing(page, timeout_s=30)
    err = capsys.readouterr().err
    assert "__Secure-1PSIDTS" in err.split("signed in; auth cookies present:")[1]
    assert "not set yet" not in err


def test_cookies_only_on_dot_google_com_count(shim):
    assert shim.has_sid([_cookie("SID", ".google.com")])
    assert shim.has_sid([_cookie("SID", "google.com")])
    assert shim.has_sid([_cookie("SID", ".google.co.in")])
    assert not shim.has_sid([_cookie("SID", ".youtube.com")])
    assert not shim.has_sid([{"name": "SID", "value": "", "domain": ".google.com"}])
    assert not shim.has_sid([_cookie("__Secure-1PSID")])


def test_already_signed_in_profile_is_not_steered(shim):
    bc, page = _fake_bc(), FakePage()
    page.context.signed_in = True
    _install(shim, bc, page)

    bc.wait_for_login_landing(page, timeout_s=30)
    assert page.gotos == []


def test_no_sid_ever_times_out_instead_of_saving_an_empty_session(shim):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    bc, page = _fake_bc(), FakePage()
    page.goto = lambda url, **kw: page.gotos.append(url)  # sign-in never completes
    _install(shim, bc, page)
    shim.SID_SETTLE_SECONDS = 0.01

    with pytest.raises(PlaywrightTimeout):
        bc.wait_for_login_landing(page, timeout_s=0.3)
    assert len(page.gotos) <= shim.MAX_STEERS


def test_unknown_library_layout_runs_cli_unchanged(shim):
    assert shim.install(types.SimpleNamespace(), base_url_fn=lambda: APP, accounts_url="x") is False


def test_shim_patches_the_real_notebooklm_library_when_installed(shim):
    bc = pytest.importorskip("notebooklm._auth.browser_capture")
    original = bc.url_matches_base_host, bc.wait_for_login_landing
    try:
        assert shim.install(bc, base_url_fn=lambda: APP, accounts_url=bc.GOOGLE_ACCOUNTS_URL)
    finally:
        bc.url_matches_base_host, bc.wait_for_login_landing = original


# ---- app side ---------------------------------------------------------------

PY = "C:/App/runtime/python/python.exe"


def test_browser_login_runs_through_the_guard():
    argv = [PY, "-m", "notebooklm", "--profile", "p", "login", "--browser", "chrome", "--fresh"]
    wrapped = login_flow._with_first_login_guard(argv)
    assert wrapped[0] == PY
    assert Path(wrapped[1]) == SHIM_PATH
    assert wrapped[2:] == argv[3:]


@pytest.mark.parametrize("extra", [["--master-token"], ["--browser-cookies", "chrome"]])
def test_other_login_modes_are_not_wrapped(extra):
    argv = [PY, "-m", "notebooklm", "--profile", "p", "login", *extra]
    assert login_flow._with_first_login_guard(argv) == argv


def test_non_login_commands_are_not_wrapped():
    argv = [PY, "-m", "notebooklm", "--profile", "p", "auth", "check", "--test", "--json"]
    assert login_flow._with_first_login_guard(argv) == argv


def test_guard_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("VOICE_FLOW_NBLM_LOGIN_GUARD", "0")
    argv = [PY, "-m", "notebooklm", "--profile", "p", "login"]
    assert login_flow._with_first_login_guard(argv) == argv


def test_spawn_uses_the_guard(monkeypatch, tmp_path):
    scripts = tmp_path / "runtime" / "python" / "Scripts"
    scripts.mkdir(parents=True)
    cli = scripts / "notebooklm.exe"
    cli.write_text("")
    (tmp_path / "runtime" / "python" / "python.exe").write_text("")
    seen = {}

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        return types.SimpleNamespace(pid=1)

    monkeypatch.setattr(login_flow.subprocess, "Popen", fake_popen)
    login_flow.spawn_notebooklm_process([str(cli), "--profile", "p", "login", "--browser", "chrome"])
    assert Path(seen["argv"][1]) == SHIM_PATH
    assert seen["argv"][2:] == ["--profile", "p", "login", "--browser", "chrome"]


def test_missing_sid_message_is_plain_and_offers_try_again():
    msg = login_flow._post_login_failure_message({
        "failure_kind": None,
        "details_message": "Token fetch failed: Missing required cookies: SID, __Secure-1PSIDTS\nhint",
    })
    assert "new session" not in msg
    assert "Try again" in msg


def test_missing_psidts_only_keeps_the_detailed_message():
    msg = login_flow._post_login_failure_message({
        "details_message": "Token fetch failed: Missing required cookies: __Secure-1PSIDTS",
    })
    assert "__Secure-1PSIDTS" in msg


def test_session_cookie_names_never_include_values(monkeypatch, tmp_path):
    st = tmp_path / "storage_state.json"
    st.write_text('{"cookies": [{"name": "SID", "value": "secret"}, {"name": "OSID", "value": "x"},'
                  ' {"name": "__Secure-1PSIDTS", "value": ""}]}')
    from voice_flow.video_flow_engine.notebooklm import config

    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: st)
    names = login_flow._session_cookie_names("p")
    assert names == ["SID", "OSID"]
    assert "secret" not in repr(names)
