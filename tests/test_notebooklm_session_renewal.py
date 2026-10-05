"""Offline regression tests for NotebookLM session renewal.

Every subprocess and filesystem root is isolated: these tests must never inspect
or modify the developer's real NotebookLM profile.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_notebooklm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / "voice-flow"))
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path / "notebooklm"))
    monkeypatch.setenv("NOTEBOOKLM_EXPERIMENT_DIR", str(tmp_path / "experiment"))
    monkeypatch.setenv("VOICE_FLOW_LOGIN_LOG", str(tmp_path / "login.log"))

    from voice_flow.video_flow_engine.notebooklm import config, keepalive, login_flow

    monkeypatch.setattr(login_flow, "resolve_notebooklm_profile", lambda profile=None: profile or "renewal-test")
    monkeypatch.setattr(keepalive, "resolve_notebooklm_profile", lambda profile=None: profile or "renewal-test")
    monkeypatch.setattr(config, "is_profile_disconnected", lambda profile=None: False)
    login_flow._ONLINE_CACHE.clear()
    login_flow._SESSION_GENERATION.clear()
    login_flow._SELF_HEAL_LOCKS.clear()
    login_flow._SELF_HEAL_RESULTS.clear()
    keepalive._GLOBAL_KEEPALIVES.clear()
    keepalive._GLOBAL_KEEPALIVE = None
    yield
    for service in list(keepalive._GLOBAL_KEEPALIVES.values()):
        service.stop(timeout=1)
    keepalive._GLOBAL_KEEPALIVES.clear()
    keepalive._GLOBAL_KEEPALIVE = None


def test_verify_online_generic_cli_failure_is_transient_and_not_cached_as_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(
        login_flow.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 2, stdout="", stderr="server disconnected"),
    )

    saved: list[tuple[str, object]] = []
    monkeypatch.setattr("voice_flow.storage.storage.save_setting", lambda key, value: saved.append((key, value)))

    result = login_flow.verify_online(profile="renewal-test", force=True, timeout=0.1)

    assert result["status"] == "transient_error"
    assert result["authenticated"] is None
    assert result["definitive"] is False
    assert result["failure_kind"] == "cli"
    assert ("video_flow_notebooklm_authenticated", False) not in saved


@pytest.mark.parametrize("error,kind", [
    ("Token fetch failed: Authentication expired or invalid.", "auth"),
    ("Token fetch failed: getaddrinfo failed", "network"),
])
def test_pinned_cli_nested_diagnostic_error_is_classified(monkeypatch, tmp_path, error, kind):
    import json
    from voice_flow.video_flow_engine.notebooklm import login_flow
    cli = tmp_path / "notebooklm.exe"
    cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: cli)
    monkeypatch.setattr(login_flow.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 1, stdout=json.dumps({
            "status": "error", "checks": {"token_fetch": False}, "details": {"error": error},
        }), stderr="",
    ))
    result = login_flow.verify_online(profile="renewal-test", force=True)
    assert result["failure_kind"] == kind
    assert result["definitive"] is (kind == "auth")
    assert result["authenticated"] is (False if kind == "auth" else None)


def test_verify_online_success_message_containing_connection_stays_authenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(
        login_flow.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, stdout='{"status":"ok","message":"Connection verified"}', stderr=""
        ),
    )

    result = login_flow.verify_online(profile="renewal-test", force=True)

    assert result["status"] == "ok"
    assert result["authenticated"] is True
    assert result["definitive"] is True


def test_refresh_requests_coalesce_to_one_silent_cli_attempt(monkeypatch: pytest.MonkeyPatch):
    from voice_flow.video_flow_engine.notebooklm import keepalive

    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def refresh(*, profile: str):
        calls.append(profile)
        entered.set()
        assert release.wait(2)
        return {"ok": True, "profile": profile, "classification": "authenticated"}

    service = keepalive.get_keepalive_service("renewal-test")
    service._refresh_func = refresh

    first = keepalive.request_session_refresh("renewal-test", background=True, force=True)
    assert entered.wait(1)
    second = keepalive.request_session_refresh("renewal-test", background=True, force=True)
    release.set()

    deadline = time.time() + 2
    while keepalive.get_session_refresh_state("renewal-test")["in_progress"] and time.time() < deadline:
        time.sleep(0.01)

    assert first["dispatched"] is True
    assert second["coalesced"] is True
    assert calls == ["renewal-test"]
    assert keepalive.get_session_refresh_state("renewal-test")["state"] == "authenticated"


def test_older_online_check_cannot_overwrite_newer_refresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    began = threading.Event()
    finish = threading.Event()

    def delayed_check(*args, **kwargs):
        began.set()
        assert finish.wait(2)
        return subprocess.CompletedProcess(
            args[0], 1, stdout='{"status":"error","message":"Authentication expired"}', stderr=""
        )

    monkeypatch.setattr(login_flow.subprocess, "run", delayed_check)
    result_box: list[dict] = []
    thread = threading.Thread(
        target=lambda: result_box.append(login_flow.verify_online(profile="renewal-test", force=True)), daemon=True
    )
    thread.start()
    assert began.wait(1)

    login_flow.note_session_refreshed("renewal-test")
    finish.set()
    thread.join(2)

    assert result_box[0]["status"] == "stale"
    assert result_box[0]["authenticated"] is None
    assert login_flow.get_online_verification_cache("renewal-test") is None


def test_definite_refresh_failure_recovers_only_from_matching_persistent_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from voice_flow.video_flow_engine.notebooklm import browser_sync, login_flow

    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(login_flow, "_login_log_path", lambda: tmp_path / "login.log")
    monkeypatch.setattr(login_flow, "_run_login_once", lambda *args, **kwargs: (1, ""))
    monkeypatch.setattr(login_flow, "_storage_email", lambda profile=None: "person@example.com")
    checks = iter([
        {"authenticated": False, "definitive": True, "failure_kind": "auth"},
        {"authenticated": True, "definitive": True, "status": "ok"},
    ])
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: next(checks))
    recoveries: list[dict[str, object]] = []
    monkeypatch.setattr(
        browser_sync,
        "refresh_from_persistent_browser",
        lambda **kwargs: recoveries.append(kwargs) or {"success": True, "email": "person@example.com"},
    )

    result = login_flow.self_heal(profile="renewal-test", timeout=12)

    assert result["ok"] is True
    assert result["classification"] == "authenticated"
    assert recoveries == [{
        "profile": "renewal-test", "expected_email": "person@example.com", "timeout_seconds": 35
    }]


def test_reset_epoch_keeps_new_login_state_when_old_refresh_finishes(monkeypatch: pytest.MonkeyPatch):
    from voice_flow.video_flow_engine.notebooklm import keepalive

    entered = threading.Event()
    release = threading.Event()
    service = keepalive.get_keepalive_service("renewal-test")
    service._refresh_func = lambda **kwargs: (
        entered.set(), release.wait(2), {"ok": True, "classification": "authenticated"}
    )[-1]

    keepalive.request_session_refresh("renewal-test", background=True, force=True)
    assert entered.wait(1)
    keepalive.reset_session_refresh_state("renewal-test", state="authenticated")
    duplicate = keepalive.request_session_refresh("renewal-test", background=True, force=True)
    release.set()
    deadline = time.time() + 2
    while keepalive.get_session_refresh_state("renewal-test")["in_progress"] and time.time() < deadline:
        time.sleep(0.01)

    assert duplicate["coalesced"] is True
    assert keepalive.get_session_refresh_state("renewal-test")["state"] == "authenticated"


def test_newer_login_generation_discards_delayed_self_heal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: fake_cli)
    monkeypatch.setattr(login_flow, "_login_log_path", lambda: tmp_path / "login.log")
    entered = threading.Event()
    release = threading.Event()

    def delayed_refresh(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return 0, ""

    monkeypatch.setattr(login_flow, "_run_login_once", delayed_refresh)
    results: list[dict] = []
    worker = threading.Thread(
        target=lambda: results.append(login_flow.self_heal(profile="renewal-test", timeout=12)), daemon=True
    )
    worker.start()
    assert entered.wait(1)
    login_flow.note_session_refreshed("renewal-test")
    release.set()
    worker.join(2)

    assert results[0]["stale"] is True
    assert results[0]["classification"] == "transient_error"


def test_storage_email_prefers_exact_profile_identity_over_stale_global_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import json
    from voice_flow.video_flow_engine.notebooklm import config, login_flow

    state = tmp_path / "profile-a" / "storage_state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"notebooklm": {"account": {"email": "actual@example.com"}}}))
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: state)

    class Settings:
        def get_setting(self, key):
            assert key == "video_flow_notebooklm_email"
            return "stale-test@gmail.com"

    monkeypatch.setattr("voice_flow.storage.StorageEngine", Settings)

    assert login_flow._storage_email("profile-a") == "actual@example.com"


@pytest.mark.parametrize("state_data", [
    {"notebooklm": {"account": {"email": "your Google account"}}},
    {"account": {"email": ""}},
    {},
])
def test_storage_email_falls_back_when_profile_identity_is_missing_or_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state_data: dict
):
    import json
    from voice_flow.video_flow_engine.notebooklm import config, login_flow

    state = tmp_path / "profile-a" / "storage_state.json"
    state.parent.mkdir()
    state.write_text(json.dumps(state_data))
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: state)

    class Settings:
        def get_setting(self, key):
            assert key == "video_flow_notebooklm_email"
            return "fallback@example.com"

    monkeypatch.setattr("voice_flow.storage.StorageEngine", Settings)

    assert login_flow._storage_email("profile-a") == "fallback@example.com"


def test_storage_email_keeps_profile_identities_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import json
    from voice_flow.video_flow_engine.notebooklm import config, login_flow

    states = {}
    for profile, email in (("profile-a", "a@example.com"), ("profile-b", "b@example.com")):
        state = tmp_path / profile / "storage_state.json"
        state.parent.mkdir()
        state.write_text(json.dumps({"account": {"email": email}}))
        states[profile] = state
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: states[profile])

    class Settings:
        def get_setting(self, key):
            return "stale-global@example.com"

    monkeypatch.setattr("voice_flow.storage.StorageEngine", Settings)

    assert login_flow._storage_email("profile-a") == "a@example.com"
    assert login_flow._storage_email("profile-b") == "b@example.com"
