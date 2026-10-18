"""The check right after a NotebookLM sign-in must let the CLI heal the session.

Offline: every subprocess is faked and every NotebookLM path points at tmp_path.

Background (notebooklm-py 0.8.2, ``_auth/browser_capture.py``): ``notebooklm
login`` saves the captured cookies even when they have no usable
``__Secure-1PSIDTS`` yet and expects the next ordinary command to heal them
from disk. ``auth check --test --passive`` deliberately never heals. The app
used the passive probe as its post-login check, so a sign-in that succeeded in
the browser ended with "Could not verify this saved session".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / "voice-flow"))
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path / "notebooklm"))
    monkeypatch.setenv("NOTEBOOKLM_EXPERIMENT_DIR", str(tmp_path / "experiment"))
    monkeypatch.setenv("VOICE_FLOW_LOGIN_LOG", str(tmp_path / "login.log"))
    from voice_flow.video_flow_engine.notebooklm import config, login_flow

    monkeypatch.setattr(login_flow, "resolve_notebooklm_profile", lambda profile=None: profile or "post-login-test")
    monkeypatch.setattr(config, "is_profile_disconnected", lambda profile=None: False)
    monkeypatch.setattr(login_flow, "_POST_LOGIN_VERIFY_RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("voice_flow.storage.storage.save_setting", lambda key, value: None)
    login_flow._ONLINE_CACHE.clear()
    login_flow._SESSION_GENERATION.clear()
    cli = tmp_path / "notebooklm.exe"
    cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: cli)
    yield


def _payload(status: str, error: str | None = None, **checks) -> str:
    base = {"storage_exists": True, "json_valid": True, "cookies_present": True,
            "sid_cookie": True, "token_fetch": status == "ok"}
    base.update(checks)
    return json.dumps({
        "status": status,
        "account": {"email": "uzair@example.com", "authuser": 0},
        "checks": base,
        "details": {"error": error},
    })


PSIDTS_MISSING = (
    "Token fetch failed: Missing required cookies: __Secure-1PSIDTS\n"
    "This typically means --browser-cookies extraction was incomplete."
)


def test_background_check_stays_passive_and_post_login_check_heals(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    commands: list[list[str]] = []

    def fake_run(argv, **kwargs):
        commands.append(list(argv))
        if "--passive" in argv:
            return subprocess.CompletedProcess(argv, 1, stdout=_payload("error", PSIDTS_MISSING), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=_payload("ok"), stderr="")

    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)

    passive = login_flow.verify_online(profile="post-login-test", force=True)
    assert "--passive" in commands[-1]
    assert passive["authenticated"] is None
    assert passive["definitive"] is False

    healed = login_flow._verify_new_session("post-login-test")
    assert "--passive" not in commands[-1]
    assert commands[-1][-4:] == ["auth", "check", "--test", "--json"]
    assert healed["authenticated"] is True
    assert healed["email"] == "uzair@example.com"


def test_post_login_check_uses_a_longer_timeout_and_retries_once(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    calls: list[float] = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, stdout=_payload("ok"), stderr="")

    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)
    result = login_flow._verify_new_session("post-login-test")
    assert result["authenticated"] is True
    assert len(calls) == 2
    assert min(calls) >= 45.0


def test_definite_sign_out_is_not_retried(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 1, stdout=_payload("error", "Token fetch failed: Authentication expired or invalid."), stderr="",
        )

    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)
    result = login_flow._verify_new_session("post-login-test")
    assert result["authenticated"] is False
    assert len(calls) == 1


def test_watch_login_success_survives_a_passive_only_psidts_gap(monkeypatch, tmp_path):
    """CLI login exits 0; the healing check passes; the UI must not say "Could not verify"."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda *a, **k: 0)
    monkeypatch.setattr(login_flow, "_prepare_browser_profile", lambda *a, **k: None)
    monkeypatch.setattr(login_flow, "_run_login_once", lambda command, *_: (0, ""))
    monkeypatch.setattr(login_flow, "master_token_present", lambda profile=None: False)

    def fake_run(argv, **kwargs):
        if "--passive" in argv:
            return subprocess.CompletedProcess(argv, 1, stdout=_payload("error", PSIDTS_MISSING), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=_payload("ok"), stderr="")

    monkeypatch.setattr(login_flow.subprocess, "run", fake_run)
    login_flow._watch_login("post-login-test", "browser", None, "chrome", 60, tmp_path / "login.log")
    state = login_flow.get_login_state()
    assert state["success"] is True, state
    assert "could not verify" not in str(state.get("error") or "").lower()


def test_inconclusive_check_names_the_reason_and_logs_it(monkeypatch, tmp_path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    reason = (
        "Token fetch failed: Google's CookieMismatch page was reached during this request: "
        "https://accounts.google.com/CookieMismatch, and the chain ended at https://support.google.com/x"
    )
    monkeypatch.setattr(
        login_flow.subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout=_payload("error", reason), stderr=""),
    )
    result = login_flow.verify_online(profile="post-login-test", force=True)
    assert result["status"] == "transient_error"
    assert result["message"].startswith("Could not verify this saved session: ")
    assert "CookieMismatch" in result["message"]
    assert "https://" not in result["message"]
    log = (tmp_path / "login.log").read_text(encoding="utf-8")
    assert "[verify]" in log and "CookieMismatch" in log and "https://" not in log


def test_no_saved_session_asks_the_user_to_sign_in(monkeypatch):
    """A new user has no storage_state.json; that is "not connected", not a failed check."""
    from voice_flow.video_flow_engine.notebooklm import login_flow

    payload = json.dumps({
        "status": "error",
        "checks": {"storage_exists": False, "json_valid": False, "cookies_present": False,
                   "sid_cookie": False, "token_fetch": None},
        "details": {"error": "Storage file not found: C:\\Users\\u\\.notebooklm\\profiles\\p\\storage_state.json"},
    })
    monkeypatch.setattr(
        login_flow.subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout=payload, stderr=""),
    )
    result = login_flow.verify_online(profile="post-login-test", force=True)
    assert result["status"] == "unauthenticated"
    assert result["failure_kind"] == "no_session"
    assert result["definitive"] is True
    assert "Could not verify" not in result["message"]
    assert "Sign in with Google" in result["message"]


def test_generic_cli_crash_is_still_transient(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.setattr(
        login_flow.subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 2, stdout="", stderr="server disconnected"),
    )
    result = login_flow.verify_online(profile="post-login-test", force=True)
    assert result["status"] == "transient_error"
    assert result["failure_kind"] == "cli"
    assert "server disconnected" in result["message"]


def test_cli_child_writes_utf8_to_its_pipes():
    from voice_flow.video_flow_engine.notebooklm import login_flow

    env = login_flow._login_child_env(None)
    assert env["PYTHONIOENCODING"].lower().replace("-", "") == "utf8"
    assert env["PYTHONUTF8"] == "1"
