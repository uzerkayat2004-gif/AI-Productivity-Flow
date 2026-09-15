"""Regression tests for NotebookLM storage_state.json write guards.

Incident being guarded against: a session-less browser context / metadata-only
save path exported ``{"cookies": []}`` over a valid storage_state.json, and the
empty export then propagated to storage_state.backup.json and
storage_state.safe_copy.json — destroying the live session AND the safety net,
so the user had to re-login after every app restart.

Covers:
1. empty-export-does-not-overwrite-valid-state (config guard + self_heal mirror)
2. backup keeps the last known-good (non-empty) state
3. startup auth-check never triggers the account-switch wipe / disconnect
4. placeholder emails ("your Google account") are never persisted
5. login persists across a restart cycle (check_auth validates offline, no overwrite)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from voice_flow.storage import StorageEngine
from voice_flow.video_flow_engine.notebooklm import browser_sync, config, login_flow
from voice_flow.video_flow_engine.notebooklm.provider import (
    NotebookLMVideoProvider,
    _validate_storage_file,
)


def _valid_cookies(token: str = "t0"):
    return [
        {"name": "SID", "value": f"sid_{token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
        {"name": "__Secure-1PSID", "value": f"psid_{token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
    ]


def _write_state(path: Path, cookies, email: str | None = None) -> None:
    data = {"cookies": cookies, "origins": []}
    if email is not None:
        data["notebooklm"] = {"version": 1, "account": {"email": email}}
        data["account"] = {"email": email}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def profile_env(tmp_path, monkeypatch):
    """Isolated profile: all config getters and both storage singletons point at tmp."""
    prof_dir = tmp_path / ".notebooklm" / "profiles" / "prof-guard"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    b_file = prof_dir / "storage_state.backup.json"
    safe_file = prof_dir / "storage_state.safe_copy.json"

    monkeypatch.setattr(config, "get_storage_state_path", lambda *a, **k: st_file)
    monkeypatch.setattr(config, "get_storage_backup_path", lambda *a, **k: b_file)
    monkeypatch.setattr(config, "get_profile_dir", lambda *a, **k: prof_dir)

    db = StorageEngine(str(tmp_path / "vf_guard.db"))
    monkeypatch.setattr("voice_flow.storage.storage", db)
    try:
        from voice_flow.gui import api_server

        monkeypatch.setattr(api_server, "storage", db)
    except Exception:
        pass

    return {"prof_dir": prof_dir, "st": st_file, "backup": b_file, "safe": safe_file, "db": db}


# ---------------------------------------------------------------------------
# 1. Empty export must never overwrite a valid state
# ---------------------------------------------------------------------------


def test_guard_refuses_empty_export_over_valid_state(tmp_path):
    st = tmp_path / "storage_state.json"
    _write_state(st, _valid_cookies("live"), email="user@gmail.com")
    original = st.read_text(encoding="utf-8")

    res = config.write_storage_state_guarded(st, json.dumps({"cookies": [], "origins": []}), source="unit-test")

    assert res["written"] is False
    assert res["reason"] == "empty_cookie_export_rejected"
    # The live state is untouched
    assert st.read_text(encoding="utf-8") == original
    assert _read_state(st)["cookies"]
    # The refused export is archived, never silently dropped
    rejected_dir = tmp_path / "rejected"
    assert rejected_dir.is_dir()
    archived = list(rejected_dir.glob("storage_state.json.*.json"))
    assert archived, "rejected export must be written to the rejected/ folder"


def test_guard_allows_nonempty_export_over_empty_state(tmp_path):
    st = tmp_path / "storage_state.json"
    _write_state(st, [])

    res = config.write_storage_state_guarded(st, json.dumps({"cookies": _valid_cookies("new")}), source="unit-test")

    assert res["written"] is True
    assert len(_read_state(st)["cookies"]) == 2


def test_mirror_guard_preserves_last_known_good_backup(tmp_path):
    backup = tmp_path / "storage_state.backup.json"
    _write_state(backup, _valid_cookies("good"), email="user@gmail.com")
    original = backup.read_text(encoding="utf-8")

    res = config.mirror_storage_state_guarded(
        json.dumps({"cookies": [], "origins": []}),
        tmp_path / "storage_state.json",
        [backup, tmp_path / "storage_state.safe_copy.json"],
        source="unit-test",
    )

    assert backup.read_text(encoding="utf-8") == original
    assert len(_read_state(backup)["cookies"]) == 2
    assert any("storage_state.backup.json" in s.get("path", "") for s in res["skipped"])


def test_mirror_guard_writes_nonempty_content(tmp_path):
    backup = tmp_path / "storage_state.backup.json"
    _write_state(backup, _valid_cookies("old"))

    content = json.dumps({"cookies": _valid_cookies("new"), "origins": []})
    res = config.mirror_storage_state_guarded(
        content, tmp_path / "storage_state.json", [backup], source="unit-test"
    )

    assert res["written"] == [str(backup)]
    assert _read_state(backup)["cookies"][0]["value"] == "sid_new"


# ---------------------------------------------------------------------------
# 2. self_heal must not propagate an emptied main file into the backups
# ---------------------------------------------------------------------------


def _patch_self_heal_success(monkeypatch, tmp_path):
    fake_cli = tmp_path / "notebooklm.exe"
    fake_cli.touch()
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda explicit=None: fake_cli)
    monkeypatch.setattr(login_flow, "_run_login_once", lambda cmd, log_path, timeout: (0, ""))
    monkeypatch.setattr(login_flow, "_login_log_path", lambda: tmp_path / "login.log")


def test_self_heal_does_not_mirror_emptied_state_over_good_backup(profile_env, monkeypatch, tmp_path):
    """Simulates the incident: after a CLI refresh the main file holds 0 cookies.

    self_heal must NOT copy that empty state over the still-valid backup and
    safe_copy — the last known-good session must survive for auto-restore.
    """
    _write_state(profile_env["st"], [], email="user@gmail.com")  # emptied main file
    _write_state(profile_env["backup"], _valid_cookies("good"), email="user@gmail.com")
    _write_state(profile_env["safe"], _valid_cookies("good"), email="user@gmail.com")
    backup_before = profile_env["backup"].read_text(encoding="utf-8")
    safe_before = profile_env["safe"].read_text(encoding="utf-8")

    _patch_self_heal_success(monkeypatch, tmp_path)
    res = login_flow.self_heal(profile="prof-guard")

    assert res["ok"] is True
    assert profile_env["backup"].read_text(encoding="utf-8") == backup_before
    assert profile_env["safe"].read_text(encoding="utf-8") == safe_before
    assert len(_read_state(profile_env["backup"])["cookies"]) == 2


def test_self_heal_still_mirrors_valid_state(profile_env, monkeypatch, tmp_path):
    """Sanity: the guard must not break the legitimate mirror of a real session."""
    _write_state(profile_env["st"], _valid_cookies("fresh"), email="user@gmail.com")

    _patch_self_heal_success(monkeypatch, tmp_path)
    res = login_flow.self_heal(profile="prof-guard")

    assert res["ok"] is True
    assert len(_read_state(profile_env["backup"])["cookies"]) == 2
    assert _read_state(profile_env["safe"])["cookies"][0]["value"] == "sid_fresh"


# ---------------------------------------------------------------------------
# 3. Startup / auth-check paths must never trigger the credential wipe
# ---------------------------------------------------------------------------


def test_startup_auth_check_never_triggers_wipe_or_disconnect(profile_env, monkeypatch, tmp_path):
    """check_auth with an empty cookie jar must fail gracefully WITHOUT wiping
    credentials, deleting backups, or calling disconnect/switch paths."""
    _write_state(profile_env["st"], [])  # empty jar, no backups on disk

    calls: list[str] = []
    monkeypatch.setattr(
        login_flow, "_clean_account_state_for_switch", lambda profile: calls.append("switch_wipe")
    )
    monkeypatch.setattr(login_flow, "disconnect_login", lambda profile=None: calls.append("disconnect"))
    monkeypatch.setattr(login_flow, "start_login", lambda **k: calls.append("start_login"))
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda explicit=None: None)

    provider = NotebookLMVideoProvider(profile="prof-guard", workdir=str(tmp_path))
    status = provider.check_auth(raise_on_error=False)

    assert status.authenticated is False
    assert calls == []
    # Nothing was written or deleted by the startup auth-check
    assert _read_state(profile_env["st"])["cookies"] == []
    assert not profile_env["backup"].exists()
    assert not profile_env["safe"].exists()
    assert not (profile_env["prof_dir"] / "rejected").exists()


def test_wipe_only_reachable_via_explicit_switch(tmp_path, monkeypatch):
    """_clean_account_state_for_switch must stay gated behind an explicit
    switch_account=True request, never a startup/auth-check code path."""
    import inspect

    source = inspect.getsource(login_flow.start_login)
    assert "if switch_account:\n        _clean_account_state_for_switch(profile)" in source


# ---------------------------------------------------------------------------
# 4. Placeholder emails must never be persisted
# ---------------------------------------------------------------------------


def test_placeholder_email_not_persisted_by_record_successful_login(profile_env):
    _write_state(profile_env["st"], _valid_cookies("live"), email="real@gmail.com")

    login_flow.record_successful_login("your Google account", profile="prof-guard")

    st_data = _read_state(profile_env["st"])
    assert st_data["notebooklm"]["account"]["email"] == "real@gmail.com"
    assert st_data["account"]["email"] == "real@gmail.com"
    # The placeholder must not replace the real email in app settings either
    assert profile_env["db"].get_setting("video_flow_notebooklm_email") != "your Google account"


def test_placeholder_email_not_written_when_state_has_no_account(profile_env):
    _write_state(profile_env["st"], _valid_cookies("live"))

    login_flow.record_successful_login("your Google account", profile="prof-guard")

    st_data = _read_state(profile_env["st"])
    assert "account" not in st_data
    assert (st_data.get("notebooklm") or {}).get("account") is None
    assert profile_env["db"].get_setting("video_flow_notebooklm_email") != "your Google account"


def test_real_email_still_persisted_by_record_successful_login(profile_env):
    _write_state(profile_env["st"], _valid_cookies("live"), email="old@gmail.com")

    login_flow.record_successful_login("new@gmail.com", profile="prof-guard")

    st_data = _read_state(profile_env["st"])
    assert st_data["account"]["email"] == "new@gmail.com"
    assert profile_env["db"].get_setting("video_flow_notebooklm_email") == "new@gmail.com"


# ---------------------------------------------------------------------------
# 5. Login persists across app restarts (offline check_auth, no overwrite)
# ---------------------------------------------------------------------------


def test_login_persists_across_restart_cycle(profile_env, monkeypatch, tmp_path):
    """End-to-end: login -> restart -> empty-export attempt -> external wipe of
    the main file; the session and the backup safety net must survive."""
    # 1. Login
    res = browser_sync.save_cookies_to_profile(_valid_cookies("login"), profile="prof-guard", email="user@gmail.com")
    assert res["success"] is True
    st_before = profile_env["st"].read_text(encoding="utf-8")

    # 2. "Restart": a fresh provider instance validates offline without rewriting
    provider = NotebookLMVideoProvider(profile="prof-guard", workdir=str(tmp_path))
    status = provider.check_auth(raise_on_error=False)
    assert status.authenticated is True
    assert profile_env["st"].read_text(encoding="utf-8") == st_before

    # 3. A session-less context tries to export an empty cookie jar
    guard_res = config.write_storage_state_guarded(
        profile_env["st"], json.dumps({"cookies": [], "origins": []}), source="empty-context-export"
    )
    assert guard_res["written"] is False
    provider2 = NotebookLMVideoProvider(profile="prof-guard", workdir=str(tmp_path))
    assert provider2.check_auth(raise_on_error=False).authenticated is True

    # 4. Even if an external actor (e.g. the CLI) empties the main file, the
    #    backup safety net restores it on the next auth check.
    _write_state(profile_env["st"], [])
    provider3 = NotebookLMVideoProvider(profile="prof-guard", workdir=str(tmp_path))
    status3 = provider3.check_auth(raise_on_error=False)
    assert status3.authenticated is True
    assert len(_read_state(profile_env["st"])["cookies"]) == 2
    # And the backup itself was never emptied by the recovery round-trip
    assert len(_read_state(profile_env["backup"])["cookies"]) == 2


def test_validate_storage_file_restores_from_backup_and_keeps_backup_valid(tmp_path):
    target = tmp_path / "storage_state.json"
    backup = tmp_path / "storage_state.backup.json"
    _write_state(target, [])
    _write_state(backup, _valid_cookies("good"), email="user@gmail.com")

    valid, msg, _ = _validate_storage_file(target, backup, auto_restore=True)

    assert valid is True
    assert len(_read_state(target)["cookies"]) == 2
    assert len(_read_state(backup)["cookies"]) == 2


def test_restore_refuses_empty_backup_over_valid_state(tmp_path):
    storage = tmp_path / "storage_state.json"
    backup = tmp_path / "storage_state.backup.json"
    _write_state(storage, _valid_cookies("live"), email="user@gmail.com")
    _write_state(backup, [])

    provider = NotebookLMVideoProvider.__new__(NotebookLMVideoProvider)
    provider.profile = "prof-guard"
    provider.get_storage_path = lambda: storage
    provider.get_backup_path = lambda: backup

    assert provider.restore_storage_state_from_backup() is False
    assert len(_read_state(storage)["cookies"]) == 2
    assert list((tmp_path / "rejected").glob("storage_state.json.*.json"))


# ---------------------------------------------------------------------------
# Guard helper unit tests
# ---------------------------------------------------------------------------


def test_count_valid_cookies_accepts_raw_json_string():
    assert config.count_valid_cookies(json.dumps({"cookies": _valid_cookies()})) == 2
    assert config.count_valid_cookies(_valid_cookies()) == 2
    assert config.count_valid_cookies(json.dumps({"cookies": []})) == 0
    assert config.count_valid_cookies("not-json") == 0


def test_is_placeholder_email():
    assert config.is_placeholder_email("your Google account")
    assert config.is_placeholder_email("YOUR GOOGLE ACCOUNT")
    assert config.is_placeholder_email("")
    assert not config.is_placeholder_email("user@gmail.com")


def test_is_pytest_real_home_path_isolation(profile_env, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_notebooklm_storage_guard.py::test")
    assert config.is_pytest_real_home_path(tmp_path / "storage_state.json") is False
    real_home_profile = Path.home() / ".notebooklm" / "profiles" / "video-flow-experiment" / "storage_state.json"
    assert config.is_pytest_real_home_path(real_home_profile) is True


def test_has_nonempty_cookies(tmp_path):
    st = tmp_path / "storage_state.json"
    _write_state(st, [{"name": "SID", "value": "", "domain": ".google.com"}])
    assert config.has_nonempty_cookies(st) is False
    _write_state(st, _valid_cookies())
    assert config.has_nonempty_cookies(st) is True
    assert config.has_nonempty_cookies(tmp_path / "missing.json") is False


def test_self_heal_pytest_isolation_skips_real_home_mirror(monkeypatch, tmp_path):
    """Under pytest, self_heal must not read/mirror the real ~/.notebooklm profiles."""
    real_profile_st = Path.home() / ".notebooklm" / "profiles" / "vf-guard-should-not-exist" / "storage_state.json"
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_notebooklm_storage_guard.py::test")
    monkeypatch.setattr(config, "get_storage_state_path", lambda *a, **k: real_profile_st)
    monkeypatch.setattr(config, "get_storage_backup_path", lambda *a, **k: real_profile_st.with_name("b.json"))
    _patch_self_heal_success(monkeypatch, tmp_path)

    res = login_flow.self_heal(profile="vf-guard-should-not-exist")

    assert res["ok"] is True
    assert not real_profile_st.with_name("b.json").exists()
