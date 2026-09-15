"""Comprehensive tests for NotebookLM browser cookie sync, import, and recovery."""

import json
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
from voice_flow.video_flow_engine.notebooklm import browser_sync, login_flow
from voice_flow.video_flow_engine.notebooklm.browser_sync import (
    auto_sync_from_browser,
    discover_browser_profiles,
    import_cookies,
    parse_cookie_payload,
    save_cookies_to_profile,
    validate_extracted_cookies,
)
from voice_flow.video_flow_engine.notebooklm.provider import (
    NotebookLMVideoProvider,
    _inspect_cookies,
    _validate_storage_file,
)


def _sample_valid_cookies():
    future = time.time() + 86400 * 30
    return [
        {
            "name": "__Secure-1PSID",
            "value": "psid_test_value_12345",
            "domain": ".google.com",
            "path": "/",
            "expires": future,
            "httpOnly": True,
            "secure": True,
        },
        {
            "name": "SID",
            "value": "sid_test_value_67890",
            "domain": ".google.com",
            "path": "/",
            "expires": future,
            "httpOnly": False,
            "secure": False,
        },
        {
            "name": "__Secure-1PSIDTS",
            "value": "psidts_test_value",
            "domain": ".google.com",
            "path": "/",
            "expires": future,
            "httpOnly": True,
            "secure": True,
        },
    ]


class TestCookieParser:
    def test_parse_storage_state_format(self):
        cookies = _sample_valid_cookies()
        payload = {"cookies": cookies, "origins": []}
        parsed = parse_cookie_payload(payload)
        assert len(parsed) == 3
        assert parsed[0]["name"] == "__Secure-1PSID"

    def test_parse_raw_list(self):
        cookies = _sample_valid_cookies()
        parsed = parse_cookie_payload(cookies)
        assert len(parsed) == 3

    def test_parse_cookie_header_string(self):
        header_str = "__Secure-1PSID=my_psid; SID=my_sid; __Secure-1PSIDTS=ts_123; other=ignored"
        parsed = parse_cookie_payload(header_str)
        names = {c["name"] for c in parsed}
        assert "__Secure-1PSID" in names
        assert "SID" in names
        psid_cookie = next(c for c in parsed if c["name"] == "__Secure-1PSID")
        assert psid_cookie["value"] == "my_psid"
        assert psid_cookie["domain"] == ".google.com"

    def test_parse_json_string(self):
        cookies = _sample_valid_cookies()
        json_str = json.dumps(cookies)
        parsed = parse_cookie_payload(json_str)
        assert len(parsed) == 3

    def test_parse_invalid_payload(self):
        assert parse_cookie_payload(None) == []
        assert parse_cookie_payload("") == []
        assert parse_cookie_payload(12345) == []
        assert parse_cookie_payload({"invalid": "format"}) == []


class TestCookieValidator:
    def test_validate_valid_cookies(self):
        cookies = _sample_valid_cookies()
        valid, msg, details = validate_extracted_cookies(cookies)
        assert valid is True
        assert details.get("has_psid") is True
        assert details.get("has_sid") is True
        assert details.get("has_psidts") is True

    def test_validate_missing_sid(self):
        cookies = [
            {"name": "__Secure-1PSID", "value": "xyz", "expires": time.time() + 1000},
        ]
        valid, msg, details = validate_extracted_cookies(cookies)
        assert valid is False
        assert "SID" in msg

    def test_validate_expired_cookie(self):
        cookies = [
            {"name": "__Secure-1PSID", "value": "xyz", "expires": time.time() - 100},
            {"name": "SID", "value": "abc", "expires": time.time() + 1000},
        ]
        valid, msg, details = validate_extracted_cookies(cookies)
        assert valid is False
        assert "expired" in msg.lower()


class TestSaveAndRecovery:
    def test_save_cookies_creates_safe_copy(self, tmp_path, monkeypatch):
        profile_dir = tmp_path / "test_profile"
        profile_dir.mkdir()
        st_file = profile_dir / "storage_state.json"
        bk_file = profile_dir / "storage_state.backup.json"
        safe_file = profile_dir / "storage_state.safe_copy.json"

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path",
            lambda p: st_file,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path",
            lambda p: bk_file,
        )

        res = save_cookies_to_profile(_sample_valid_cookies(), profile="test_profile", email="user@gmail.com")
        assert res["success"] is True
        assert st_file.is_file()
        assert bk_file.is_file()
        assert safe_file.is_file()

        # Verify content
        data = json.loads(safe_file.read_text(encoding="utf-8"))
        assert len(data["cookies"]) == 3
        assert data["account"]["email"] == "user@gmail.com"

    def test_validate_storage_file_restores_from_safe_copy(self, tmp_path):
        target = tmp_path / "storage_state.json"
        backup = tmp_path / "storage_state.backup.json"
        safe_copy = tmp_path / "storage_state.safe_copy.json"

        # Safe copy exists with valid cookies, primary is empty
        safe_copy.write_text(
            json.dumps({"cookies": _sample_valid_cookies(), "account": {"email": "user@gmail.com"}}),
            encoding="utf-8",
        )
        target.write_text(json.dumps({"cookies": []}), encoding="utf-8")

        valid, msg, details = _validate_storage_file(target, backup, auto_restore=True)
        assert valid is True
        # Primary should have been restored
        restored = json.loads(target.read_text(encoding="utf-8"))
        assert len(restored["cookies"]) == 3

    def test_auto_sync_from_browser_restores_safe_copy(self, tmp_path, monkeypatch):
        target = tmp_path / "storage_state.json"
        safe_copy = tmp_path / "storage_state.safe_copy.json"
        safe_copy.write_text(
            json.dumps({"cookies": _sample_valid_cookies(), "account": {"email": "auto@gmail.com"}}),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path",
            lambda p: target,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path",
            lambda p: tmp_path / "storage_state.backup.json",
        )

        res = auto_sync_from_browser(profile="video-flow-experiment")
        assert res["success"] is True
        assert res["email"] == "auto@gmail.com"
        assert target.is_file()

    def test_auto_sync_from_browser_skips_identical_cookies_to_prevent_circular_restore(self, tmp_path, monkeypatch):
        target = tmp_path / "storage_state.json"
        safe_copy = tmp_path / "storage_state.safe_copy.json"
        cookies = _sample_valid_cookies()
        payload = json.dumps({"cookies": cookies, "account": {"email": "dead@gmail.com"}})
        target.write_text(payload, encoding="utf-8")
        safe_copy.write_text(payload, encoding="utf-8")

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path",
            lambda p: target,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path",
            lambda p: tmp_path / "storage_state.backup.json",
        )

        res = auto_sync_from_browser(profile="video-flow-experiment")
        assert res.get("source") != "restored_storage_state.safe_copy.json"

    def test_auto_sync_from_browser_restores_when_candidate_cookies_differ(self, tmp_path, monkeypatch):
        target = tmp_path / "storage_state.json"
        safe_copy = tmp_path / "storage_state.safe_copy.json"
        old_cookies = _sample_valid_cookies()
        new_cookies = _sample_valid_cookies()
        new_cookies[0]["value"] = "new_refreshed_psid_val"

        target.write_text(json.dumps({"cookies": old_cookies, "account": {"email": "user@gmail.com"}}), encoding="utf-8")
        safe_copy.write_text(json.dumps({"cookies": new_cookies, "account": {"email": "user@gmail.com"}}), encoding="utf-8")

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_state_path",
            lambda p: target,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.get_storage_backup_path",
            lambda p: tmp_path / "storage_state.backup.json",
        )

        res = auto_sync_from_browser(profile="video-flow-experiment")
        assert res["success"] is True
        assert res.get("source") == "restored_storage_state.safe_copy.json"
        restored = json.loads(target.read_text(encoding="utf-8"))
        assert restored["cookies"][0]["value"] == "new_refreshed_psid_val"

    def test_validate_storage_file_skips_identical_cookies_backup(self, tmp_path):
        target = tmp_path / "storage_state.json"
        backup = tmp_path / "storage_state.backup.json"
        expired_cookies = [
            {"name": "__Secure-1PSID", "value": "old_psid", "expires": time.time() - 500, "domain": ".google.com", "path": "/"},
            {"name": "SID", "value": "old_sid", "expires": time.time() - 500, "domain": ".google.com", "path": "/"},
        ]
        payload = json.dumps({"cookies": expired_cookies})
        target.write_text(payload, encoding="utf-8")
        backup.write_text(payload, encoding="utf-8")

        valid, msg, details = _validate_storage_file(target, backup, auto_restore=True)
        assert valid is False
        assert "expired" in msg.lower()


class TestSelfHealAndProviderRecovery:
    def test_self_heal_falls_back_to_browser_sync(self, tmp_path, monkeypatch):
        # When CLI path is missing, self_heal should attempt browser_sync
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli",
            lambda explicit=None: None,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser",
            lambda profile=None, preferred_browser=None: {"success": True, "email": "healed@gmail.com"},
        )

        res = login_flow.self_heal(profile="test-profile")
        assert res["ok"] is True
        assert res["healed_via"] == "browser_sync"

    def test_self_heal_falls_back_to_playwright(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL", "1")
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli",
            lambda explicit=None: None,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser",
            lambda profile=None, preferred_browser=None: {"success": False, "error": "No browser profiles"},
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.sync_cookies_with_playwright",
            lambda profile=None, headless=True, timeout_seconds=35: {"success": True, "email": "pw@gmail.com"},
        )

        res = login_flow.self_heal(profile="test-profile")
        assert res["ok"] is True
        assert res.get("healed_via") == "playwright_sync"

    def test_provider_check_auth_auto_recovers(self, tmp_path, monkeypatch):
        st_file = tmp_path / "storage_state.json"
        safe_file = tmp_path / "storage_state.safe_copy.json"
        safe_file.write_text(
            json.dumps({"cookies": _sample_valid_cookies(), "account": {"email": "prov@gmail.com"}}),
            encoding="utf-8",
        )
        # Empty primary
        st_file.write_text(json.dumps({"cookies": []}), encoding="utf-8")

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
            lambda p=None: st_file,
        )
        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path",
            lambda p=None: tmp_path / "storage_state.backup.json",
        )

        provider = NotebookLMVideoProvider(profile="test_profile")
        status = provider.check_auth(raise_on_error=False)
        assert status.authenticated is True
        assert status.status == "ok"


class TestApiServerSyncEndpoints:
    def test_sync_browser_endpoint(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "vf_test.db")
        test_storage = StorageEngine(db_path)
        monkeypatch.setattr(api_server, "storage", test_storage)
        monkeypatch.setattr("voice_flow.storage.storage", test_storage)

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser",
            lambda profile=None, preferred_browser=None: {
                "success": True,
                "profile": profile or "default",
                "email": "synced@gmail.com",
                "cookies_count": 5,
            },
        )

        server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            req = urllib.request.Request(
                f"{base_url}/api/video-flow/notebooklm/auth/sync-browser",
                data=json.dumps({"profile": "test"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert data["email"] == "synced@gmail.com"
                assert data["cookies_count"] == 5
        finally:
            server.shutdown()

    def test_import_cookies_endpoint(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "vf_test.db")
        test_storage = StorageEngine(db_path)
        monkeypatch.setattr(api_server, "storage", test_storage)
        monkeypatch.setattr("voice_flow.storage.storage", test_storage)

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.import_cookies",
            lambda payload, profile=None, email=None: {
                "success": True,
                "profile": profile or "default",
                "email": email or "imported@gmail.com",
                "cookies_count": 3,
            },
        )

        server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            req = urllib.request.Request(
                f"{base_url}/api/video-flow/notebooklm/auth/import-cookies",
                data=json.dumps({"profile": "test", "cookies": _sample_valid_cookies()}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert data["cookies_count"] == 3
        finally:
            server.shutdown()

    def test_browser_profiles_endpoint(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "vf_test.db")
        test_storage = StorageEngine(db_path)
        monkeypatch.setattr(api_server, "storage", test_storage)
        monkeypatch.setattr("voice_flow.storage.storage", test_storage)

        monkeypatch.setattr(
            "voice_flow.video_flow_engine.notebooklm.browser_sync.discover_browser_profiles",
            lambda: [{"browser": "chrome", "human_name": "Main", "email": "test@gmail.com"}],
        )

        server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.1)
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            req = urllib.request.Request(
                f"{base_url}/api/video-flow/notebooklm/auth/browser-profiles",
                headers={"Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["success"] is True
                assert len(data["profiles"]) == 1
                assert data["profiles"][0]["email"] == "test@gmail.com"
        finally:
            server.shutdown()
