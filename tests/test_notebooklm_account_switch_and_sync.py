import json
import pytest
from pathlib import Path
from unittest.mock import patch

from voice_flow.video_flow_engine.notebooklm import login_flow
from voice_flow.video_flow_engine.notebooklm import browser_sync
from voice_flow.video_flow_engine.notebooklm.keepalive import NotebookLMKeepaliveService
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
import voice_flow.google_auth as google_auth


def _sample_cookies(email_token: str = "alice"):
    return [
        {"name": "SID", "value": f"sid_{email_token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
        {"name": "HSID", "value": f"hsid_{email_token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
        {"name": "SSID", "value": f"ssid_{email_token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
        {"name": "__Secure-1PSID", "value": f"psid_{email_token}", "domain": ".google.com", "path": "/", "expires": 253402300799},
    ]


def test_clean_account_state_for_switch(tmp_path, monkeypatch):
    """Test that _clean_account_state_for_switch thoroughly purges old account artifacts."""
    prof_dir = tmp_path / "test-profile"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    b_file = prof_dir / "storage_state.backup.json"
    safe_file = prof_dir / "storage_state.safe_copy.json"
    mt_file = prof_dir / "master_token.json"

    st_file.write_text(json.dumps({"cookies": _sample_cookies("old"), "account": {"email": "old@gmail.com"}}), encoding="utf-8")
    b_file.write_text(json.dumps({"cookies": _sample_cookies("old")}), encoding="utf-8")
    safe_file.write_text(json.dumps({"cookies": _sample_cookies("old"), "account": {"email": "old@gmail.com"}}), encoding="utf-8")
    mt_file.write_text(json.dumps({"account": "old@gmail.com", "token": "abc"}), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: b_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_profile_dir", lambda p: prof_dir)

    login_flow._clean_account_state_for_switch("test-profile")

    assert not b_file.exists()
    assert not safe_file.exists()
    assert not mt_file.exists()

    st_data = json.loads(st_file.read_text(encoding="utf-8"))
    assert st_data["cookies"] == []
    assert "account" not in st_data


def test_browser_sync_rejects_mismatched_email(tmp_path, monkeypatch):
    """Verify auto_sync_from_browser does not use safe copy if email does not match expected_email."""
    target = tmp_path / "storage_state.json"
    safe_copy = tmp_path / "storage_state.safe_copy.json"
    backup = tmp_path / "storage_state.backup.json"

    safe_copy.write_text(
        json.dumps({"cookies": _sample_cookies("alice"), "account": {"email": "alice@gmail.com"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path", lambda p: target)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path", lambda p: backup)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_profile_dir", lambda p: tmp_path)

    # Calling auto_sync with expected_email='bob@gmail.com' must NOT restore alice's safe_copy
    res = browser_sync.auto_sync_from_browser(profile="test", expected_email="bob@gmail.com")
    assert res.get("email") != "alice@gmail.com"


def test_browser_sync_accepts_matching_email(tmp_path, monkeypatch):
    """Verify auto_sync_from_browser successfully restores safe copy when email matches expected_email."""
    target = tmp_path / "storage_state.json"
    safe_copy = tmp_path / "storage_state.safe_copy.json"
    backup = tmp_path / "storage_state.backup.json"

    safe_copy.write_text(
        json.dumps({"cookies": _sample_cookies("alice"), "account": {"email": "alice@gmail.com"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path", lambda p: target)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path", lambda p: backup)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_profile_dir", lambda p: tmp_path)

    res = browser_sync.auto_sync_from_browser(profile="test", expected_email="alice@gmail.com")
    assert res["success"] is True
    assert res["email"] == "alice@gmail.com"
    assert target.is_file()


def test_api_server_storage_read_prefers_valid_cookies_over_stale_setting(tmp_path, monkeypatch):
    """Verify that on startup, valid cookies on disk report authenticated = True even if DB setting was unconfigured."""
    db_path = str(tmp_path / "vf_storage.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "test-prof"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    st_file.write_text(
        json.dumps({"cookies": _sample_cookies("user"), "account": {"email": "user@gmail.com"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: prof_dir / "backup.json")

    auth, email, path, details = api_server._read_notebooklm_storage_state("test-prof")
    assert auth is True
    assert email == "user@gmail.com"
    assert details["cookies_count"] == 4


def test_disconnect_login_marks_unauthenticated(tmp_path, monkeypatch):
    """Verify disconnect_login clears storage state, removes backups, and updates storage."""
    db_path = str(tmp_path / "vf_disc.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "disc-prof"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    b_file = prof_dir / "storage_state.backup.json"
    safe_file = prof_dir / "storage_state.safe_copy.json"

    st_file.write_text(json.dumps({"cookies": _sample_cookies("disc"), "account": {"email": "disc@gmail.com"}}), encoding="utf-8")
    b_file.write_text(json.dumps({"cookies": _sample_cookies("disc")}), encoding="utf-8")
    safe_file.write_text(json.dumps({"cookies": _sample_cookies("disc")}), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: b_file)

    res = login_flow.disconnect_login("disc-prof")
    assert res["success"] is True

    assert not b_file.exists()
    assert not safe_file.exists()
    st_data = json.loads(st_file.read_text(encoding="utf-8"))
    assert st_data["cookies"] == []

    auth, email, _, details = api_server._read_notebooklm_storage_state("disc-prof")
    assert auth is False
    assert email is None
    assert details.get("disconnected") is True


def test_clean_account_state_saves_switched_from_and_removes_browser_dir(tmp_path, monkeypatch):
    """Verify _clean_account_state_for_switch records switched_from in SQLite and deletes browser_profile dir."""
    db_path = str(tmp_path / "vf_switch.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("video_flow_notebooklm_email", "old_account@gmail.com")
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "prof-switch"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    st_file.write_text(json.dumps({"cookies": _sample_cookies("old"), "account": {"email": "old_account@gmail.com"}}), encoding="utf-8")
    b_dir = prof_dir / "browser_profile"
    b_dir.mkdir(parents=True, exist_ok=True)
    (b_dir / "dummy.txt").write_text("browser session data", encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: prof_dir / "backup.json")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow._profile_browser_dir", lambda p: b_dir)

    login_flow._clean_account_state_for_switch("prof-switch")

    assert test_storage.get_setting("video_flow_notebooklm_switched_from") == "old_account@gmail.com"
    assert not b_dir.exists()


def test_auto_sync_rejects_switched_from_account(tmp_path, monkeypatch):
    """Verify auto_sync_from_browser refuses to restore an account that was explicitly switched away from."""
    db_path = str(tmp_path / "vf_switch_rej.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("video_flow_notebooklm_switched_from", "old_account@gmail.com")
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    target = tmp_path / "storage_state.json"
    safe_copy = tmp_path / "storage_state.safe_copy.json"
    backup = tmp_path / "storage_state.backup.json"

    safe_copy.write_text(
        json.dumps({"cookies": _sample_cookies("old"), "account": {"email": "old_account@gmail.com"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path", lambda p: target)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path", lambda p: backup)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.get_profile_dir", lambda p: tmp_path)

    res = browser_sync.auto_sync_from_browser(profile="prof-switch")
    assert res.get("email") != "old_account@gmail.com"


def test_record_successful_login_updates_storage_state_and_clears_switched_from(tmp_path, monkeypatch):
    """Verify record_successful_login writes email into storage_state.json and clears switched_from."""
    db_path = str(tmp_path / "vf_login_success.db")
    test_storage = StorageEngine(db_path)
    test_storage.save_setting("video_flow_notebooklm_switched_from", "old@gmail.com")
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)
    monkeypatch.setattr(api_server, "storage", test_storage)

    prof_dir = tmp_path / "prof-success"
    prof_dir.mkdir(parents=True, exist_ok=True)
    st_file = prof_dir / "storage_state.json"
    b_file = prof_dir / "storage_state.backup.json"
    st_file.write_text(json.dumps({"cookies": _sample_cookies("new")}), encoding="utf-8")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path", lambda p: st_file)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path", lambda p: b_file)

    login_flow.record_successful_login("new_account@gmail.com", profile="prof-success")

    assert test_storage.get_setting("video_flow_notebooklm_switched_from") == ""
    assert test_storage.get_setting("video_flow_notebooklm_email") == "new_account@gmail.com"

    st_data = json.loads(st_file.read_text(encoding="utf-8"))
    assert st_data["account"]["email"] == "new_account@gmail.com"
    assert st_data["notebooklm"]["account"]["email"] == "new_account@gmail.com"

    state = login_flow.get_login_state()
    assert state["email"] == "new_account@gmail.com"
    assert state["success"] is True

