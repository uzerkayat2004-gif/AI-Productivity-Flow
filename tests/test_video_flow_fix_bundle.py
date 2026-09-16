"""Tests for the Video Flow fix bundle:

- hidden-console kwargs on every Video Flow subprocess spawn
- honest-fallback metadata propagation (engine -> service result -> shim)
- NotebookLM login flow module (v6: CLI-owned sign-in, headless self-heal)
- planning prompt cap (groq HTTP 413 fix)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from voice_flow.video_flow_engine.process_manager import (  # noqa: E402
    ProcessManager,
    hidden_window_kwargs,
)
from voice_flow.video_flow_engine import code2video_runner as c2v  # noqa: E402


IS_NT = os.name == "nt"


@pytest.fixture(autouse=True)
def _isolated_signin_env(tmp_path, monkeypatch):
    """Never touch the real login log, storage DB, or login state in tests."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setattr(login_flow, "_login_log_path", lambda: tmp_path / "login.log")
    monkeypatch.setattr(login_flow, "_storage_email", lambda: None)
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(
            running=False, mode=None, started_at=None, finished_at=None,
            success=None, error=None, note=None, durable=None, log_path=None,
        )
        login_flow._ONLINE_CACHE.update(checked_at=0.0, result=None)
    yield


def _vendor_root() -> Path:
    return Path(c2v.__file__).resolve().parents[3] / "third_party" / "code2video"


# ---------------------------------------------------------------------------
# 1. Hidden consoles
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not IS_NT, reason="Windows-only spawn flags")
def test_hidden_window_kwargs_set_create_no_window():
    kwargs = hidden_window_kwargs()
    assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    si = kwargs["startupinfo"]
    assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert si.wShowWindow == subprocess.SW_HIDE


@pytest.mark.skipif(IS_NT, reason="Non-Windows gets no flags")
def test_hidden_window_kwargs_noop_off_windows():
    assert hidden_window_kwargs() == {}


def test_process_manager_taskkill_uses_hidden_flags(tmp_path):
    """_terminate's taskkill spawn must not open a console window."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    dead = SimpleNamespace(poll=lambda: None, pid=1234, wait=lambda timeout=0: 0, kill=lambda: None)
    with patch("voice_flow.video_flow_engine.process_manager.subprocess.run", side_effect=fake_run):
        ProcessManager._terminate(dead)
    if IS_NT:
        assert captured["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_code2video_runner_popen_hides_console(tmp_path, monkeypatch):
    """The planner worker Popen must carry CREATE_NO_WINDOW on Windows."""
    seen: dict = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            seen.update(kwargs)
            self.pid = 4242

        def communicate(self, timeout=None):
            return '{"ok": true}', ""

        def poll(self):
            return 0

    runner = c2v.Code2VideoRunner(vendor_root=_vendor_root())
    manager = ProcessManager()
    options = {
        "project_dir": tmp_path,
        "job_id": "vf-test",
        "process_manager": manager,
        "allow_external_ai": True,
        "max_tokens": 512,
    }
    monkeypatch.setattr("voice_flow.video_flow_engine.code2video_runner.subprocess.Popen", FakePopen)
    monkeypatch.setattr(c2v, "_extract_json_object", lambda content: {"ok": True})
    monkeypatch.setattr(c2v, "_response_text", lambda response: json.dumps({"ok": True}))
    try:
        runner._request_json("prompt text", tmp_path, options)
    except Exception:
        pass  # validator paths may raise; the Popen kwargs are what we assert
    if IS_NT:
        assert seen.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
        assert seen.get("startupinfo") is not None


# ---------------------------------------------------------------------------
# 2. Planning prompt cap (HTTP 413 fix)
# ---------------------------------------------------------------------------

def test_cap_planning_source_passthrough_short():
    text = "short text"
    assert c2v._cap_planning_source(text) == text


def test_cap_planning_source_trims_long_text():
    text = "A" * 30_000 + "B" * 5_000
    capped = c2v._cap_planning_source(text)
    assert len(capped) <= c2v._PLANNING_SOURCE_MAX_CHARS + 64
    assert capped.startswith("A")
    assert capped.endswith("B" * 8)  # tail preserved
    assert "middle truncated" in capped


def test_compact_outline_json_no_indentation():
    outline = {"topic": "t", "sections": [{"id": "s1", "content": "x" * 50}]}
    compact = c2v._compact_outline_json(outline)
    assert ", " not in compact and ": " not in compact
    assert json.loads(compact) == outline


# ---------------------------------------------------------------------------
# 3. Honest fallback metadata
# ---------------------------------------------------------------------------

def test_engine_run_result_carries_fallback_fields():
    from voice_flow.video_flow_engine.engine import VideoFlowEngine

    source = Path(inspect_source := __file__)  # placeholder silence for linters
    src = Path(VideoFlowEngine.__module__.replace(".", "/") + ".py")
    for base in (REPO_SRC,):
        candidate = base / src
        if candidate.is_file():
            source = candidate
            break
    text = source.read_text(encoding="utf-8")
    # The success path propagates the honest-fallback keys into its result.
    assert 'for _fb_key in ("fallback_reason", "fallback_requested_engine", "fallback_error"):' in text


def test_service_complete_persists_fallback_fields():
    src = REPO_SRC / "voice_flow" / "video_flow_service.py"
    text = src.read_text(encoding="utf-8")
    assert 'for _fb_key in ("fallback_reason", "fallback_requested_engine", "fallback_error"):' in text


def test_shim_video_exposes_fallback_fields():
    from voice_flow.gui.api_server import _shim_video
    from voice_flow.video_flow_contracts import JobV3

    job = JobV3(
        job_id="vf-abc",
        state="complete",
        progress=100.0,
        message="Ready",
        meta={
            "title": "T",
            "output_path": "x",
            "fallback_reason": "notebooklm_auth_expired",
            "fallback_requested_engine": "notebooklm",
            "fallback_error": "login expired",
        },
    )
    data = _shim_video(job)
    assert data["fallback_reason"] == "notebooklm_auth_expired"
    assert data["fallback_requested_engine"] == "notebooklm"
    assert data["fallback_error"] == "login expired"


def test_shim_video_fallback_fields_default_none():
    from voice_flow.gui.api_server import _shim_video
    from voice_flow.video_flow_contracts import JobV3

    job = JobV3(job_id="vf-abc", state="complete", progress=100.0, message="Ready", meta={"title": "T"})
    data = _shim_video(job)
    assert data["fallback_reason"] is None
    assert data["fallback_requested_engine"] is None


def test_engine_auth_fallback_sets_fallback_kwargs():
    src = REPO_SRC / "voice_flow" / "video_flow_engine" / "engine.py"
    text = src.read_text(encoding="utf-8")
    assert 'local_kwargs["fallback_reason"] = "notebooklm_auth_expired"' in text
    assert 'local_kwargs["fallback_requested_engine"] = "notebooklm"' in text


def test_engine_self_heal_retries_after_reauth():
    """Auth expiry must trigger a headless self-heal + one retry BEFORE
    degrading to the local engine (the 'login once' guarantee)."""
    src = REPO_SRC / "voice_flow" / "video_flow_engine" / "engine.py"
    text = src.read_text(encoding="utf-8")
    assert "self_heal" in text
    assert "_voice_flow_retried_after_reauth" in text
    assert "Login refreshed automatically" in text


# ---------------------------------------------------------------------------
# 4. Login flow module (v6: CLI-owned sign-in, headless self-heal)
# ---------------------------------------------------------------------------

def test_login_state_defaults_clean():
    from voice_flow.video_flow_engine.notebooklm import login_flow

    state = login_flow.get_login_state()
    assert state["running"] is False or isinstance(state["running"], bool)
    assert "started_at" in state and "success" in state


def test_verify_online_parses_cli_payload(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    payload = {
        "status": "error",
        "message": "Token fetch failed: Authentication expired or invalid.",
        "account": {"email": "user@example.com"},
        "master_token": {"present": False},
    }
    monkeypatch.setattr(
        login_flow.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), returncode=0),
    )
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    result = login_flow.verify_online(force=True)
    assert result["authenticated"] is False
    assert result["master_token_present"] is False
    assert result["email"] == "user@example.com"


def test_verify_online_ok(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    payload = {"status": "ok", "account": {"email": "a@b.c"}, "master_token": {"present": True}}
    monkeypatch.setattr(
        login_flow.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), returncode=0),
    )
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    result = login_flow.verify_online(force=True)
    assert result["authenticated"] is True
    assert result["master_token_present"] is True


def test_verify_online_cli_missing():
    from voice_flow.video_flow_engine.notebooklm import login_flow

    with patch.object(login_flow, "resolve_notebooklm_cli", return_value=None):
        result = login_flow.verify_online(force=True)
    assert result["authenticated"] is False
    assert result["status"] == "dependency_missing"


def test_verify_online_caches(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    calls = {"n": 0}

    def fake_run(*a, **k):
        calls["n"] += 1
        return SimpleNamespace(stdout=json.dumps({"status": "ok", "account": {"email": "x"}}), returncode=0)

    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    first = login_flow.verify_online(profile="p", force=True)
    second = login_flow.verify_online(profile="p")  # cache hit
    assert calls["n"] == 1
    assert first["authenticated"] == second["authenticated"]


def test_start_login_requires_cli(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    with patch.object(login_flow, "resolve_notebooklm_cli", return_value=None):
        result = login_flow.start_login()
    assert result["launched"] is False
    assert "CLI" in result["error"]


def test_start_login_already_running_no_deadlock(monkeypatch):
    """Regression: the already-running branch called get_login_state() while
    holding the (formerly non-reentrant) _STATE_LOCK and deadlocked forever."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(running=True)
    try:
        result = login_flow.start_login()
    finally:
        with login_flow._STATE_LOCK:
            login_flow._STATE.update(running=False)
    assert result["launched"] is False
    assert result["already_running"] is True
    assert result["state"]["running"] is True


def test_start_login_respects_disable_gate(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setenv("VOICE_FLOW_LOGIN_DISABLE", "1")
    result = login_flow.start_login()
    assert result["launched"] is False
    assert "disabled" in result["error"]


def test_start_login_runs_master_token_mode(monkeypatch):
    """Default sign-in = the CLI's own master-token bootstrap: one command,
    one window, the CLI captures the oauth_token and mints the token itself."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands: list[list[str]] = []

    def fake_run_once(command, log_path, timeout):
        commands.append(command)
        return 0, ""

    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_once)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: "user@example.com")
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile=None: True)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda profile, log_path: 0)
    result = login_flow.start_login(mode="master-token", browser="chrome")
    assert result["launched"] is True
    assert result["mode"] == "master-token"
    import time as _t

    for _ in range(100):
        state = login_flow.get_login_state()
        if not state["running"]:
            break
        _t.sleep(0.05)
    assert commands and "--master-token" in commands[0] and "--account" in commands[0]
    assert "user@example.com" in commands[0]
    state = login_flow.get_login_state()
    assert state["success"] is True
    assert state["durable"] is True


def test_start_login_message_is_one_time(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    class _FakeThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_storage_email", lambda: "a@b.c")
    monkeypatch.setattr(login_flow.threading, "Thread", _FakeThread)
    result = login_flow.start_login(mode="master-token")
    assert result["launched"] is True
    assert "one-time" in result["message"].lower()


def test_start_login_without_email_uses_plain_browser(monkeypatch):
    """No stored account email -> master-token bootstrap is impossible (the
    CLI requires --account), so the plain cookie login runs instead."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands: list[list[str]] = []

    def fake_run_once(command, log_path, timeout):
        commands.append(command)
        return 0, ""

    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_once)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: None)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda profile, log_path: 0)
    result = login_flow.start_login(mode="master-token")
    assert result["mode"] == "browser"
    import time as _t

    for _ in range(100):
        if not login_flow.get_login_state()["running"]:
            break
        _t.sleep(0.05)
    assert commands and "--master-token" not in commands[0]


def test_login_command_shape():
    from voice_flow.video_flow_engine.notebooklm.login_flow import _login_command

    cmd = _login_command(
        Path("C:/cli/notebooklm.exe"), "video-flow-experiment",
        mode="master-token", account_email="a@b.c", browser="chrome", browser_timeout=300,
    )
    assert cmd[0] == str(Path("C:/cli/notebooklm.exe"))
    assert "--profile" in cmd and "login" in cmd
    assert "--master-token" in cmd and "--account" in cmd and "a@b.c" in cmd
    # The CLI owns the whole capture+mint: no token or CDP plumbing is passed.
    assert "--oauth-token" not in cmd and "--cdp-url" not in cmd


def test_login_command_plain_mode():
    from voice_flow.video_flow_engine.notebooklm.login_flow import _login_command

    cmd = _login_command(
        Path("C:/cli/notebooklm.exe"), "p",
        mode="browser", account_email=None, browser="chrome", browser_timeout=300,
    )
    assert "--master-token" not in cmd and "--account" not in cmd


def test_login_command_force_flag():
    from voice_flow.video_flow_engine.notebooklm.login_flow import _login_command

    cmd = _login_command(
        Path("C:/cli/notebooklm.exe"), "p", mode="master-token",
        account_email="new@x.y", browser="chrome", browser_timeout=300, force=True,
    )
    assert "--force" in cmd
    plain = _login_command(
        Path("C:/cli/notebooklm.exe"), "p", mode="master-token",
        account_email="same@x.y", browser="chrome", browser_timeout=300,
    )
    assert "--force" not in plain


def test_master_token_present_and_self_heal(monkeypatch, tmp_path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    profile_dir = tmp_path / "prof"
    profile_dir.mkdir()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_profile", lambda p=None: "video-flow-experiment")
    monkeypatch.setattr(
        login_flow, "_master_token_json_path",
        lambda profile=None: profile_dir / "master_token.json",
    )
    assert login_flow.master_token_present() is False

    # No CLI -> self-heal refuses.
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: None)
    assert login_flow.self_heal()["error"] == "cli_missing"

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/cli/notebooklm.exe"))
    seen = []
    monkeypatch.setattr(
        login_flow, "_run_login_once",
        lambda command, log_path, timeout: (seen.append(command), (0, ""))[1],
    )

    # No token file -> the CLI's layered recovery runs (rotation + L3 browser
    # session recovery), still headless.
    result = login_flow.self_heal()
    assert result["ok"] is True
    assert seen[-1][-3:] == ["refresh", "--verify", "--allow-headless"]

    # Token file present -> direct headless re-mint from the durable token.
    (profile_dir / "master_token.json").write_text("{}", encoding="utf-8")
    assert login_flow.master_token_present() is True
    result = login_flow.self_heal()
    assert result["ok"] is True
    assert seen[-1][-1:] == ["--master-token-refresh"]


def test_terminate_stale_login_scopes_to_profile(monkeypatch, tmp_path):
    """The stale-browser cleaner must only ever match processes whose command
    line carries OUR browser_profile path — never the user's daily browser."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    calls = []
    monkeypatch.setattr(login_flow.os, "name", "nt")
    monkeypatch.setattr(
        login_flow.subprocess, "run",
        lambda *a, **k: calls.append(a) or SimpleNamespace(stdout="111\n222\n", returncode=0),
    )

    killed = login_flow._terminate_stale_login_processes("p", tmp_path / "log.txt")
    assert killed == 2
    kinds = [c[0][0] for c in calls]
    assert kinds[0] == "powershell"
    ps_script = " ".join(calls[0][0])
    assert "browser_profile" in ps_script  # scoping marker present
    assert all(c[0][0] == "taskkill" for c in calls[1:])


def test_redact_command_for_log_hides_oauth_token():
    from voice_flow.video_flow_engine.notebooklm.login_flow import _redact_command_for_log

    cmd = ["notebooklm.exe", "login", "--master-token", "--oauth-token", "SECRET123", "--account", "a@b.c"]
    line = _redact_command_for_log(cmd)
    assert "SECRET123" not in line
    assert "<redacted>" in line
    assert "a@b.c" in line


def test_watch_login_master_token_success(monkeypatch, tmp_path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands = []

    def fake_run_once(command, log_path, timeout):
        commands.append(command)
        return 0, ""

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_once)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: "stored@gmail.com")
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile=None: True)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda profile, log_path: 0)
    monkeypatch.setattr(
        login_flow, "verify_online",
        lambda **k: {"authenticated": True, "email": "stored@gmail.com"},
    )

    login_flow._watch_login(
        "video-flow-experiment", "master-token", "stored@gmail.com",
        "chrome", 300, tmp_path / "log.txt",
    )
    # ONE command: the CLI's own master-token bootstrap. No fallback ran.
    assert len(commands) == 1 and "--master-token" in commands[0]
    state = login_flow.get_login_state()
    assert state["success"] is True and state["durable"] is True
    # A successful, identified sign-in is labelled with the account so the UI
    # can show "Signed in as <email>" (video-flow.js reads login.note and also
    # derives the email from it).
    assert state["email"] == "stored@gmail.com"
    assert state["note"] == "Signed in as stored@gmail.com"


def test_watch_login_falls_back_to_plain_on_mint_failure(monkeypatch, tmp_path):
    """If the durable setup fails, the plain login still restores the session —
    and the state says honestly that the durable setup didn't finish."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands = []

    def fake_run_once(command, log_path, timeout):
        commands.append(command)
        return (1, "boom") if "--master-token" in command else (0, "")

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_once)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: "stored@gmail.com")
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile=None: False)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda profile, log_path: 0)

    login_flow._watch_login(
        "video-flow-experiment", "master-token", "stored@gmail.com",
        "chrome", 300, tmp_path / "log.txt",
    )
    assert len(commands) == 2
    assert "--master-token" in commands[0] and "--master-token" not in commands[1]
    state = login_flow.get_login_state()
    assert state["success"] is True
    assert state["durable"] is False
    assert "durable" in (state["note"] or "").lower()


def test_parse_reset_time_extracts_eta():
    """The 'resets at HH:MM' parser feeds the rate-limit retry ETA."""
    from voice_flow.video_flow_service import _parse_reset_time

    eta = _parse_reset_time("You're almost at your limit. Resets at 3:00 PM")
    assert eta is not None and eta.hour == 15 and eta.minute == 0
    eta2 = _parse_reset_time("resets at 09:30 am")
    assert eta2 is not None and eta2.hour == 9
    assert _parse_reset_time("Rate limited.") is None


def _rate_limited_service(tmp_path, engine_result):
    """Service wired to a fake engine that raises/returns engine_result."""
    import threading as _threading
    from voice_flow.video_flow_contracts import JobV3
    from voice_flow.video_flow_service import VideoFlowService, VideoFlowStore

    store = VideoFlowStore(tmp_path / "jobs.db")
    service = VideoFlowService(
        store=store, projects_root=tmp_path / "projects",
        reconcile_orphans=False, rate_limit_retry_seconds=0.0 if engine_result is None else 3600,
    )

    class _FakeEngine:
        def __init__(self, **kwargs):
            self.cancelled = False

        def cancel(self, job_id):
            self.cancelled = True

        def run(self, job_id, **kwargs):
            if isinstance(engine_result, Exception):
                raise engine_result
            return engine_result

    service._engine_factory = lambda **kwargs: _FakeEngine()
    return service, store


def test_rate_limited_job_auto_retries_once(tmp_path):
    """A NotebookLM RATE_LIMITED failure is retried automatically once after
    the rolling window, then completes or fails honestly — no dead job."""
    from types import SimpleNamespace

    exc = SimpleNamespace(code="RATE_LIMITED", __str__=lambda self: "Error: Rate limited.")
    # Use a real exception so except-handling sees code attr.
    class _RateLimited(Exception):
        code = "RATE_LIMITED"

        def __str__(self):
            return "Error: Rate limited."

    service, store = _rate_limited_service(tmp_path, None)
    calls = {"n": 0}

    class _FlakyEngine:
        def __init__(self, **kwargs):
            pass

        def cancel(self, job_id):
            pass

        def run(self, job_id, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _RateLimited()
            return {
                "video_id": job_id, "state": "ready",
                "video_path": str(tmp_path / "projects" / job_id / "video.mp4"),
                "timings": {},
            }

    service._engine_factory = lambda **kwargs: _FlakyEngine()
    job = service.queue("hello world", video_engine="notebooklm")
    # _complete verifies the rendered file exists; fake it for the retry.
    out_file = tmp_path / "projects" / job.job_id / "video.mp4"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(b"fake mp4")
    # Wait: first run raises -> job parked with ETA, timer scheduled with the
    # tiny test delay; second run completes.
    deadline = __import__("time").time() + 10
    while __import__("time").time() < deadline:
        state = store.get(job.job_id)
        if state and state.state == "complete":
            break
        __import__("time").sleep(0.1)
    final = store.get(job.job_id)
    assert final.state == "complete", f"state={final.state} message={final.message}"
    assert calls["n"] == 2
    meta = final.meta
    assert meta.get("rate_limit_attempts") == 1


def test_rate_limited_second_hit_fails_with_explanation(tmp_path):
    """After the one automatic retry, a second RATE_LIMITED fails with a
    plain-language message instead of retrying forever."""
    import time as _time

    class _RateLimited(Exception):
        code = "RATE_LIMITED"

        def __str__(self):
            return "Error: Rate limited."

    service, store = _rate_limited_service(tmp_path, None)

    class _AlwaysLimited:
        def __init__(self, **kwargs):
            pass

        def cancel(self, job_id):
            pass

        def run(self, job_id, **kwargs):
            raise _RateLimited()

    service._engine_factory = lambda **kwargs: _AlwaysLimited()
    job = service.queue("hello world", video_engine="notebooklm")
    deadline = _time.time() + 10
    while _time.time() < deadline:
        state = store.get(job.job_id)
        if state and state.state == "failed":
            break
        _time.sleep(0.1)
    final = store.get(job.job_id)
    assert final.state == "failed"
    assert "refreshes about every 5 hours" in str(final.meta.get("error_message") or "")


def test_rate_limited_retry_respects_cancellation(tmp_path):
    """A cancelled rate-limited job must NOT be revived by the retry timer."""
    import time as _time

    class _RateLimited(Exception):
        code = "RATE_LIMITED"

        def __str__(self):
            return "Error: Rate limited."

    service, store = _rate_limited_service(tmp_path, None)
    started = _threading_Event_holder()

    class _LimitedOnce:
        def __init__(self, **kwargs):
            pass

        def cancel(self, job_id):
            pass

        def run(self, job_id, **kwargs):
            started.set()
            raise _RateLimited()

    service._engine_factory = lambda **kwargs: _LimitedOnce()
    job = service.queue("hello world", video_engine="notebooklm")
    deadline = _time.time() + 5
    while _time.time() < deadline and not started.is_set():
        _time.sleep(0.05)
    # Parked with ETA -> user cancels.
    service.cancel(job.job_id)
    _time.sleep(0.3)  # allow timer (0s delay) to fire if it would
    final = store.get(job.job_id)
    assert final.state == "cancelled"


def _threading_Event_holder():
    import threading

    return threading.Event()


def test_watch_login_without_email_runs_plain(monkeypatch, tmp_path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands = []

    def fake_run_once(command, log_path, timeout):
        commands.append(command)
        return 0, ""

    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_run_login_once", fake_run_once)
    monkeypatch.setattr(login_flow, "_storage_email", lambda: None)
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda profile, log_path: 0)

    login_flow._watch_login(
        "video-flow-experiment", "browser", None,
        "chrome", 300, tmp_path / "log.txt",
    )
    assert len(commands) == 1 and "--master-token" not in commands[0]
    assert login_flow.get_login_state()["success"] is True
