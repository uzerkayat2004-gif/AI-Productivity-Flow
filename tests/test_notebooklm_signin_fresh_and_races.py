"""NotebookLM sign-in for new users, broken old sessions, macOS and races.

Uzair, v1.0.6 (Oct 18, 2026): a brand-new user clicked "Sign in with Google"
and got "Could not verify this saved session"; on macOS sign-in never worked.

Most tests here run the real sign-in code end to end against a *fake*
``notebooklm`` CLI: a tiny Python package launched exactly the way the app
launches the real one (``<runtime>/bin/python3 -m notebooklm`` on macOS,
``<runtime>/python.exe -m notebooklm`` on Windows). Its ``auth check`` answers
reuse the JSON the real notebooklm-py 0.8.2 printed offline for the same
cases (no storage file; cookies without ``__Secure-1PSIDTS``).
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.notebooklm import config, login_flow

PROFILE = "signin-test"

FAKE_CLI = r'''
import json, os, shutil, sys, time
from pathlib import Path

args = sys.argv[1:]
profile = "default"
if args[:1] == ["--profile"]:
    profile, args = args[1], args[2:]
home = Path(os.environ["NOTEBOOKLM_HOME"])
pdir = home / "profiles" / profile
storage = pdir / "storage_state.json"
browser = pdir / "browser_profile"
scenario = os.environ.get("FAKE_NLM_SCENARIO", "ok")
with (home / "calls.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\n")
EMAIL = "uzair@example.com"
FAR = time.time() + 86400 * 30

def cookies(psidts=True):
    names = ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID"]
    if psidts:
        names.append("__Secure-1PSIDTS")
    return [{"name": n, "value": "v-" + n, "domain": ".google.com", "path": "/", "expires": FAR,
             "httpOnly": True, "secure": True, "sameSite": "Lax"} for n in names]

def save(state):
    pdir.mkdir(parents=True, exist_ok=True)
    storage.write_text(json.dumps(state), encoding="utf-8")

if args and args[0] == "login":
    if "--fresh" in args and browser.exists():
        shutil.rmtree(browser)
    browser.mkdir(parents=True, exist_ok=True)
    print("Opening Chrome for Google login...")
    print("Using persistent profile: " + str(browser))
    if scenario == "window_closed":
        print("Browser closed during login. Please keep the window open.", file=sys.stderr)
        sys.exit(1)
    if (browser / "old_google_session").exists():
        # The persistent profile still holds an old Google session: the CLI
        # lands on NotebookLM without showing the sign-in page.
        print("Already logged in.")
        save({"cookies": cookies(psidts=False), "stale": True,
              "notebooklm": {"account": {"email": EMAIL}}})
    else:
        print("Waiting for login (up to 5 minutes)...")
        print("Login detected.")
        if scenario == "no_save":
            sys.exit(0)
        # A new capture often has no usable PSIDTS yet (the CLI heals it on
        # the next non-passive command).
        save({"cookies": cookies(psidts=False), "notebooklm": {"account": {"email": EMAIL}}})
        print("Saved the captured session, but it has no usable __Secure-1PSIDTS", file=sys.stderr)
    print("Authentication saved to: " + str(storage))
    sys.exit(0)

if args[:2] == ["auth", "check"]:
    passive = "--passive" in args
    base = {"storage_path": str(storage), "cookies_found": [], "cookie_domains": []}
    if not storage.exists():
        base["error"] = "Storage file not found: " + str(storage)
        print(json.dumps({"status": "error", "account": None, "checks": {
            "storage_exists": False, "json_valid": False, "cookies_present": False,
            "sid_cookie": False, "token_fetch": None}, "details": base}))
        sys.exit(1)
    state = json.loads(storage.read_text(encoding="utf-8"))
    names = {c["name"] for c in state.get("cookies", [])}
    if state.get("stale") or scenario == "google_rejects":
        base["error"] = ("Token fetch failed: Authentication expired or invalid. "
                         "Final URL: https://accounts.google.com/ServiceLogin?continue=x")
        print(json.dumps({"status": "error", "account": {"email": EMAIL}, "checks": {
            "storage_exists": True, "json_valid": True, "cookies_present": True,
            "sid_cookie": True, "token_fetch": False}, "details": base}))
        sys.exit(1)
    if "__Secure-1PSIDTS" not in names:
        if passive or scenario == "heal_fails":
            base["error"] = ("Token fetch failed: Missing required cookies: __Secure-1PSIDTS\n"
                             "This typically means --browser-cookies extraction was incomplete.")
            print(json.dumps({"status": "error", "account": {"email": EMAIL}, "checks": {
                "storage_exists": True, "json_valid": True, "cookies_present": False,
                "sid_cookie": False, "token_fetch": False}, "details": base}))
            sys.exit(1)
        state["cookies"] = cookies(psidts=True)   # non-passive check heals from disk
        save(state)
    print(json.dumps({"status": "ok", "account": {"email": EMAIL, "authuser": 0},
                      "checks": {"storage_exists": True, "token_fetch": True}, "details": base}))
    sys.exit(0)

print("unexpected command: " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _make_runtime(root: Path, layout: str) -> Path:
    """Create the app's private runtime layout and return the CLI script path."""
    if layout == "mac":
        bindir = root / "AI Productivity Flow.app" / "Contents" / "Resources" / "runtime" / "python" / "bin"
        bindir.mkdir(parents=True)
        (bindir / "python3").symlink_to(sys.executable)
        cli = bindir / "notebooklm"
    else:
        pydir = root / "runtime" / "python"
        (pydir / "Scripts").mkdir(parents=True)
        (pydir / "python.exe").symlink_to(sys.executable)
        cli = pydir / "Scripts" / "notebooklm.exe"
    cli.write_text("#!/fake/shebang/from/the/build/machine\n", encoding="utf-8")
    return cli


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "notebooklm"
    home.mkdir()
    fake_pkg = tmp_path / "fakecli" / "notebooklm"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")
    (fake_pkg / "__main__.py").write_text(textwrap.dedent(FAKE_CLI), encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(fake_pkg.parent))
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(home))
    monkeypatch.delenv("NOTEBOOKLM_PROFILES_DIR", raising=False)
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / "voice-flow"))
    monkeypatch.setenv("VOICE_FLOW_LOGIN_LOG", str(tmp_path / "notebooklm-login.log"))
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setenv("FAKE_NLM_SCENARIO", "ok")
    monkeypatch.setattr(login_flow, "resolve_notebooklm_profile", lambda profile=None: profile or PROFILE)
    monkeypatch.setattr(config, "is_profile_disconnected", lambda profile=None: False)
    monkeypatch.setattr(login_flow, "_POST_LOGIN_VERIFY_RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("voice_flow.storage.storage.save_setting", lambda key, value: None)
    monkeypatch.setattr(login_flow, "resolve_interactive_browser", lambda preferred=None: "chrome")
    # The real _run_login_once is used; only its name changes so the pytest
    # guard in _watch_login (which refuses to open real browsers) lets it run.
    real_run = login_flow._run_login_once

    def run_login_once_for_test(*args, **kwargs):
        return real_run(*args, **kwargs)

    monkeypatch.setattr(login_flow, "_run_login_once", run_login_once_for_test)
    login_flow._ONLINE_CACHE.clear()
    login_flow._SESSION_GENERATION.clear()
    login_flow._FRESH_NEXT.clear()
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(running=False, success=None, error=None, started_at=None)
    yield {"home": home, "tmp": tmp_path, "pdir": home / "profiles" / PROFILE}
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(running=False)


def _use_cli(monkeypatch, cli: Path) -> None:
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: cli)


def _calls(home: Path) -> list[list[str]]:
    path = home / "calls.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wait_for_login(timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = login_flow.get_login_state()
        if not state.get("running"):
            return state
        time.sleep(0.05)
    pytest.fail("sign-in did not finish")


@pytest.mark.parametrize("layout", ["windows", "mac"])
def test_new_user_gets_a_fresh_login_and_ends_connected(env, monkeypatch, layout):
    """No session at all: Sign in opens a clean login, the new capture is
    healed by the non-passive check, and the user ends up Connected."""
    _use_cli(monkeypatch, _make_runtime(env["tmp"], layout))
    # A browser profile left behind by an earlier, abandoned attempt.
    leftover = env["pdir"] / "browser_profile"
    leftover.mkdir(parents=True)
    (leftover / "Cookies").write_text("old", encoding="utf-8")

    assert login_flow._saved_session_kind(PROFILE) == "none"
    started = login_flow.start_login(profile=PROFILE, mode="cli")
    assert started["launched"] is True
    assert started["fresh_login"] is True and started["fresh_reason"] == "new_user"

    state = _wait_for_login()
    assert state["success"] is True, state
    assert state["email"] == "uzair@example.com"
    assert "could not verify" not in str(state.get("error") or "").lower()

    calls = _calls(env["home"])
    logins = [c for c in calls if c[:1] == ["login"]]
    checks = [c for c in calls if c[:2] == ["auth", "check"]]
    assert len(logins) == 1 and "--fresh" in logins[0]
    # The post-login check is the healing one, never --passive.
    assert checks and all("--passive" not in c for c in checks)
    stored = json.loads((env["pdir"] / "storage_state.json").read_text(encoding="utf-8"))
    assert "__Secure-1PSIDTS" in {c["name"] for c in stored["cookies"]}
    # The old browser profile was moved aside, not silently reused.
    backups = list((env["pdir"] / "stale-sessions").glob("*/browser_profile/Cookies"))
    assert len(backups) == 1
    log = Path(os.environ["VOICE_FLOW_LOGIN_LOG"]).read_text(encoding="utf-8")
    assert "[env] platform=" in log and "reason=new_user" in log
    # The CLI was launched through the bundled interpreter, never the shim.
    spawn_lines = [line for line in log.splitlines() if line.startswith("[spawn]")]
    # Browser logins run through the first-sign-in guard; everything else is
    # ``python -m notebooklm``. Never the console-script shim.
    assert spawn_lines and all(
        (" -m notebooklm " in line or "first_login_shim.py " in line) for line in spawn_lines
    )


def test_new_user_status_check_is_quiet(env, monkeypatch):
    """Before any sign-in, a check says "not connected", not "could not verify"."""
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    result = login_flow.verify_online(profile=PROFILE, force=True)
    assert result["failure_kind"] == "no_session"
    assert result["definitive"] is True
    assert "could not verify" not in result["message"].lower()


def test_reused_stale_browser_session_is_replaced_by_a_fresh_login(env, monkeypatch):
    """The CLI captured an old Google session from its browser profile
    ("Already logged in.") and Google rejects it: the app backs it up and opens
    a fresh sign-in in the same click instead of failing."""
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    pdir = env["pdir"]
    (pdir / "browser_profile").mkdir(parents=True)
    (pdir / "browser_profile" / "old_google_session").write_text("x", encoding="utf-8")
    # A saved session whose state is unknown: reconnect reuses it first.
    (pdir / "storage_state.json").write_text(json.dumps({"cookies": [
        {"name": "SID", "value": "old", "domain": ".google.com"}]}), encoding="utf-8")
    assert login_flow._saved_session_kind(PROFILE) == "saved"

    started = login_flow.start_login(profile=PROFILE, mode="cli")
    assert started["fresh_login"] is False
    state = _wait_for_login()

    assert state["success"] is True, state
    logins = [c for c in _calls(env["home"]) if c[:1] == ["login"]]
    assert len(logins) == 2
    assert "--fresh" not in logins[0] and "--fresh" in logins[1]
    backup = list((pdir / "stale-sessions").glob("*/storage_state.json"))
    assert backup, "the rejected session must be backed up, not deleted"
    assert json.loads(backup[0].read_text(encoding="utf-8")).get("stale") is True
    log = Path(os.environ["VOICE_FLOW_LOGIN_LOG"]).read_text(encoding="utf-8")
    assert "reason=reused_session_failed" in log


def test_broken_old_session_starts_fresh_and_is_backed_up(env, monkeypatch):
    """A saved session that Google already rejected is cleared (backed up)
    before the sign-in window opens."""
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    pdir = env["pdir"]
    pdir.mkdir(parents=True)
    (pdir / "storage_state.json").write_text(json.dumps({"cookies": [
        {"name": "SID", "value": "old", "domain": ".google.com"}], "stale": True}), encoding="utf-8")
    rejected = login_flow.verify_online(profile=PROFILE, force=True)
    assert rejected["authenticated"] is False and rejected["failure_kind"] == "auth"
    assert login_flow._saved_session_kind(PROFILE) == "broken"

    started = login_flow.start_login(profile=PROFILE, mode="cli")
    assert started["fresh_login"] is True and started["fresh_reason"] == "broken_session"
    state = _wait_for_login()
    assert state["success"] is True, state
    logins = [c for c in _calls(env["home"]) if c[:1] == ["login"]]
    assert len(logins) == 1 and "--fresh" in logins[0]
    assert list((pdir / "stale-sessions").glob("*/storage_state.json"))


def test_failed_check_after_real_sign_in_names_the_reason_and_next_click_is_fresh(env, monkeypatch):
    """Google sign-in finished but the session cannot be confirmed: the toast
    gives the reason (not "saved session"), and the next click starts clean."""
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    monkeypatch.setenv("FAKE_NLM_SCENARIO", "heal_fails")
    login_flow.start_login(profile=PROFILE, mode="cli")
    state = _wait_for_login()
    assert state["success"] is False
    assert "saved session" not in state["error"].lower()
    assert "could not confirm the new session" in state["error"]
    assert "__Secure-1PSIDTS" in state["error"]
    # One login only: a user who just signed in is not sent round again.
    assert len([c for c in _calls(env["home"]) if c[:1] == ["login"]]) == 1
    assert login_flow._FRESH_NEXT.get(PROFILE) == "previous_attempt_failed"

    monkeypatch.setenv("FAKE_NLM_SCENARIO", "ok")
    again = login_flow.start_login(profile=PROFILE, mode="cli")
    assert again["fresh_login"] is True
    assert _wait_for_login()["success"] is True
    assert PROFILE not in login_flow._FRESH_NEXT


def test_cli_exit_zero_without_a_saved_session_says_so(env, monkeypatch):
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    monkeypatch.setenv("FAKE_NLM_SCENARIO", "no_save")
    login_flow.start_login(profile=PROFILE, mode="cli")
    state = _wait_for_login()
    assert state["success"] is False
    assert "no NotebookLM session was saved" in state["error"]
    assert "not connected yet" not in state["error"]


def test_closed_window_is_not_reported_as_a_session_problem(env, monkeypatch):
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    monkeypatch.setenv("FAKE_NLM_SCENARIO", "window_closed")
    login_flow.start_login(profile=PROFILE, mode="cli")
    state = _wait_for_login()
    assert state["success"] is False
    assert "saved session" not in state["error"].lower()
    assert len([c for c in _calls(env["home"]) if c[:1] == ["login"]]) == 1


# --- races -----------------------------------------------------------------


def test_background_refresh_cannot_overwrite_the_login_detail(env, monkeypatch):
    """The CLI-run detail is per thread: a keepalive refresh finishing in
    another thread no longer replaces the sign-in's exit code and flags."""
    login_flow._remember_login_detail(exit_code=0, window_opened=True, cancelled=False,
                                      elapsed=12.0, output="Already logged in.")
    other = threading.Thread(target=lambda: login_flow._remember_login_detail(
        exit_code=1, window_opened=None, cancelled=True, elapsed=0.5, output="refresh failed"))
    other.start()
    other.join()
    detail = login_flow._current_login_detail()
    assert detail["exit_code"] == 0 and detail["cancelled"] is False
    assert detail["reused_browser_session"] is True


def test_sign_in_stops_an_in_flight_background_refresh(env, monkeypatch):
    killed = []

    class Proc:
        pid = 4242

        def poll(self):
            return None

    proc = Proc()
    monkeypatch.setattr(login_flow, "_kill_process_tree", lambda p: killed.append(p))
    with login_flow._BACKGROUND_CLI_LOCK:
        login_flow._BACKGROUND_CLI_PROCESSES[proc.pid] = (PROFILE, proc)
        login_flow._BACKGROUND_CLI_PROCESSES[4343] = ("another-profile", Proc())
    try:
        assert login_flow._stop_background_cli(PROFILE) == 1
        assert killed == [proc]
    finally:
        with login_flow._BACKGROUND_CLI_LOCK:
            login_flow._BACKGROUND_CLI_PROCESSES.clear()


def test_check_started_before_sign_in_cannot_publish_a_verdict(env, monkeypatch):
    """A background check still running when Sign in is clicked is fenced."""
    release = threading.Event()
    entered = threading.Event()

    class Result:
        returncode = 1
        stdout = json.dumps({"status": "error", "details": {"error": "Authentication expired"}})
        stderr = ""

    def slow_run(*_a, **_k):
        entered.set()
        release.wait(5)
        return Result()

    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    monkeypatch.setattr(login_flow.subprocess, "run", slow_run)
    out = {}
    worker = threading.Thread(target=lambda: out.update(login_flow.verify_online(profile=PROFILE, force=True)))
    worker.start()
    assert entered.wait(5)
    login_flow.note_session_refreshed(PROFILE)  # what _watch_login does first
    release.set()
    worker.join(5)
    assert out["status"] == "stale"
    assert PROFILE not in login_flow._ONLINE_CACHE


def test_second_click_while_signing_in_joins_the_open_attempt(env, monkeypatch):
    _use_cli(monkeypatch, _make_runtime(env["tmp"], "windows"))
    spawned = []
    monkeypatch.setattr(login_flow, "_watch_login", lambda *a, **k: spawned.append(a))
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(running=True)
    result = login_flow.start_login(profile=PROFILE, mode="cli")
    assert result["already_running"] is True and result["launched"] is True
    assert spawned == []


# --- macOS ------------------------------------------------------------------


def test_mac_dangling_singleton_lock_is_removed(tmp_path):
    browser = tmp_path / "browser_profile"
    browser.mkdir()
    (browser / "SingletonLock").symlink_to("Old-MacBook.local-4711")  # dangling, as Chrome writes it
    (browser / "SingletonSocket").symlink_to(tmp_path / "gone" / "socket")
    assert not (browser / "SingletonLock").exists()  # why the old check missed it
    login_flow._remove_browser_lock_files(browser)
    assert not os.path.lexists(browser / "SingletonLock")
    assert not os.path.lexists(browser / "SingletonSocket")


@pytest.mark.parametrize("name,expected", [
    ("chrome.exe", True), ("msedge.exe", True), ("Google Chrome", True),
    ("Google Chrome Helper (Renderer)", True), ("Chromium", True), ("Microsoft Edge", True),
    ("chrome", True), ("Safari", False), ("python3", False), ("Finder", False),
])
def test_sign_in_browser_names_cover_mac(name, expected):
    assert login_flow._is_sign_in_browser_process_name(name) is expected


def test_mac_leftover_sign_in_chrome_is_terminated(env, monkeypatch):
    marker = str(login_flow._profile_browser_dir(PROFILE))
    killed = []

    class FakeProc:
        def __init__(self, pid, name, cmdline):
            self.info = {"pid": pid, "name": name, "cmdline": cmdline}

        def kill(self):
            killed.append(self.info["pid"])

    procs = [
        FakeProc(10, "Google Chrome", ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                                        f"--user-data-dir={marker}"]),
        FakeProc(11, "Google Chrome", ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]),
        FakeProc(12, "Google Chrome", ["chrome", f"--user-data-dir={marker}_evil"]),
    ]
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda *_a, **_k: procs)
    assert login_flow._terminate_stale_login_processes(PROFILE) == 1
    assert killed == [10]  # the user's own Chrome and look-alike paths are untouched


def test_mac_chrome_only_counts_where_playwright_launches_it(tmp_path, monkeypatch):
    monkeypatch.setattr(login_flow.sys, "platform", "darwin")
    monkeypatch.setattr(login_flow.os, "name", "posix")
    monkeypatch.setattr(login_flow.shutil, "which", lambda _n: None)
    apps = tmp_path / "Applications"
    apps.mkdir()
    monkeypatch.setattr(login_flow, "_MAC_APPLICATIONS_DIR", apps)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home" / "Applications" / "Google Chrome.app").mkdir(parents=True)
    # ~/Applications is invisible to Playwright's "chrome" channel.
    assert login_flow._browser_installed("chrome") is False
    assert login_flow.resolve_interactive_browser("chrome") == "chromium"
    (apps / "Google Chrome.app").mkdir()
    assert login_flow._browser_installed("chrome") is True
    assert login_flow.resolve_interactive_browser("chrome") == "chrome"


def test_mac_bundle_cli_runs_through_bundled_python3(tmp_path):
    cli = _make_runtime(tmp_path, "mac")
    argv = login_flow._cli_argv([str(cli), "--profile", PROFILE, "login"])
    assert argv[0] == str(cli.parent / "python3")
    assert argv[1:3] == ["-m", "notebooklm"]


def test_mac_quarantine_is_cleared_once_from_the_runtime(tmp_path, monkeypatch):
    cli = _make_runtime(tmp_path, "mac")
    xattr = tmp_path / "xattr"
    xattr.write_text("", encoding="utf-8")
    calls = []

    class Done:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

    def fake_run(argv, **_k):
        calls.append(argv)
        return Done(0)

    monkeypatch.setattr(login_flow.sys, "platform", "darwin")
    monkeypatch.setattr(login_flow, "_MAC_XATTR", xattr)
    monkeypatch.setattr(login_flow, "_MAC_QUARANTINE_DONE", False)
    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)
    log = tmp_path / "login.log"
    login_flow._mac_clear_runtime_quarantine(cli, log)
    login_flow._mac_clear_runtime_quarantine(cli, log)
    assert calls[0][:3] == [str(xattr), "-p", "com.apple.quarantine"]
    assert calls[1] == [str(xattr), "-dr", "com.apple.quarantine", str(cli.parent.parent)]
    assert len(calls) == 2  # once per app run
    assert "[mac] cleared quarantine" in log.read_text(encoding="utf-8")


def test_post_login_messages_never_mention_a_saved_session():
    for kind in ("network", "no_session", "auth", "cli", "token_extraction", None):
        text = login_flow._post_login_failure_message({"failure_kind": kind, "details_message": "x"})
        assert "saved session" not in text.lower()
