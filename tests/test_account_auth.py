"""Automated tests for Voice Flow Account Authentication, Multi-Account Isolation,
and Cross-Device Encrypted Vault Sync (.flowvault).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

import voice_flow.account_manager as am_module
from voice_flow.account_manager import (
    AccountManager,
    hash_password,
    verify_password,
)
from voice_flow.storage import StorageEngine, storage


@pytest.fixture
def temp_env():
    """Create an isolated temporary environment for accounts and vaults."""
    temp_dir = Path(tempfile.mkdtemp(prefix="vf_auth_test_"))
    yield temp_dir
    try:
        shutil.rmtree(str(temp_dir), ignore_errors=True)
    except Exception:
        pass


def test_password_hashing():
    """Verify PBKDF2-HMAC-SHA256 password hashing, salt uniqueness, and constant-time verification."""
    p1 = "correct_horse_battery_staple"
    h1, s1 = hash_password(p1)
    h2, s2 = hash_password(p1)

    # Salts must be random and distinct
    assert s1 != s2
    assert h1 != h2

    # Verification must succeed for correct password
    assert verify_password(p1, h1, s1) is True
    assert verify_password(p1, h2, s2) is True

    # Verification must fail for incorrect password
    assert verify_password("wrong_password", h1, s1) is False
    assert verify_password("", h1, s1) is False
    assert verify_password("CORRECT_HORSE_BATTERY_STAPLE", h1, s1) is False


def test_account_manager_registration_and_login(temp_env):
    """Verify registration validation, login authentication, and sessions."""
    am = AccountManager(base_dir=temp_env)

    # Default primary account should be auto-created
    active = am.get_active_account()
    assert active is not None
    assert active["id"] == "acc_primary"

    # Validation: invalid email
    with pytest.raises(ValueError, match="valid email"):
        am.register_account("invalid_email", "Alice", "password123")

    # Validation: short password
    with pytest.raises(ValueError, match="at least 4 characters"):
        am.register_account("alice@example.com", "Alice", "12")

    # Successful registration
    res1 = am.register_account("alice@example.com", "Alice", "secret1234", avatar_color="#3b82f6")
    assert res1["success"] is True
    alice = res1["account"]
    assert alice["email"] == "alice@example.com"
    assert alice["username"] == "Alice"
    assert alice["avatar_color"] == "#3b82f6"
    assert res1["session_token"] is not None

    # Duplicate email rejection
    with pytest.raises(ValueError, match="already exists"):
        am.register_account("alice@example.com", "Alice Duplicate", "different1234")

    # Login with valid credentials
    login_res = am.authenticate_account("alice@example.com", "secret1234")
    assert login_res["success"] is True
    assert login_res["account"]["id"] == alice["id"]
    assert am.get_active_account_id() == alice["id"]

    # Login with username case-insensitive
    login_user = am.authenticate_account("alice", "secret1234")
    assert login_user["success"] is True

    # Login with invalid password
    with pytest.raises(ValueError, match="Invalid email/username or password"):
        am.authenticate_account("alice@example.com", "wrongpassword")


def test_multi_account_data_isolation(temp_env):
    """Verify strict data isolation between accounts (API keys, dictionary, and settings)."""
    am = AccountManager(base_dir=temp_env)

    reg_a = am.register_account("user_a@flow.local", "User A", "pass_a_123")
    id_a = reg_a["account"]["id"]
    reg_b = am.register_account("user_b@flow.local", "User B", "pass_b_123")
    id_b = reg_b["account"]["id"]

    # 1. Switch to Account A and add data
    am.switch_account(id_a)
    db_path_a = str(am.get_account_db_path(id_a))
    storage_a = StorageEngine(db_path_a)

    storage_a.save_setting("theme_color", "orange_dark")
    storage_a.add_dictionary_word("QuantumMechanics", "Physics")
    storage_a.add_provider_connection(
        provider="groq",
        name="Alice Groq",
        api_key="gsk_alice_groq_key",
    )

    assert storage_a.get_setting("theme_color") == "orange_dark"
    dict_a = storage_a.get_dictionary_words()
    assert "QuantumMechanics" in dict_a
    conns_a = [c["api_key"] for c in storage_a.get_provider_connections("groq")]
    assert "gsk_alice_groq_key" in conns_a

    # 2. Switch to Account B and verify Account A data is NOT present
    am.switch_account(id_b)
    db_path_b = str(am.get_account_db_path(id_b))
    storage_b = StorageEngine(db_path_b)

    assert storage_b.get_setting("theme_color") != "orange_dark"
    dict_b = storage_b.get_dictionary_words()
    assert "QuantumMechanics" not in dict_b
    conns_b = [c["api_key"] for c in storage_b.get_provider_connections("groq")]
    assert "gsk_alice_groq_key" not in conns_b

    # Add Account B specific data
    storage_b.save_setting("theme_color", "blue_light")
    storage_b.add_dictionary_word("Neurobiology", "Biology")
    storage_b.add_provider_connection(
        provider="openai",
        name="Bob OpenAI",
        api_key="sk_bob_openai_key",
    )

    # 3. Switch back to Account A and verify Account A data is still completely intact
    am.switch_account(id_a)
    assert storage_a.get_setting("theme_color") == "orange_dark"
    dict_a_recheck = storage_a.get_dictionary_words()
    assert "QuantumMechanics" in dict_a_recheck
    assert "Neurobiology" not in dict_a_recheck
    conns_a_recheck = [c["api_key"] for c in storage_a.get_provider_connections("groq")]
    assert "gsk_alice_groq_key" in conns_a_recheck
    openai_conns_in_a = [c["api_key"] for c in storage_a.get_provider_connections("openai")]
    assert "sk_bob_openai_key" not in openai_conns_in_a


def test_zero_data_loss_migration(temp_env):
    """Verify that an existing pre-auth voice_flow.db is adopted as primary account without losing any data."""
    legacy_db = temp_env / "voice_flow.db"
    legacy_storage = StorageEngine(str(legacy_db))
    legacy_storage.save_setting("pre_migration_key", "active_value")
    legacy_storage.add_dictionary_word("LegacyWord", "Custom")
    legacy_storage.add_provider_connection(
        provider="groq",
        name="Existing Working Key",
        api_key="gsk_existing_legacy_12345",
    )
    with sqlite3.connect(str(legacy_db)) as c:
        c.execute("PRAGMA wal_checkpoint(FULL)")

    # Initialize AccountManager on this directory
    am = AccountManager(base_dir=temp_env)

    active = am.get_active_account()
    assert active["id"] == "acc_primary"

    # Verify primary account inherited the existing database
    primary_db = am.get_account_db_path("acc_primary")
    assert primary_db.exists()

    primary_storage = StorageEngine(str(primary_db))
    assert primary_storage.get_setting("pre_migration_key") == "active_value"
    words = primary_storage.get_dictionary_words()
    assert "LegacyWord" in words
    keys = [c["api_key"] for c in primary_storage.get_provider_connections("groq")]
    assert "gsk_existing_legacy_12345" in keys


def test_encrypted_vault_sync(temp_env):
    """Verify AES-256-GCM + PBKDF2 .flowvault encryption, tamper resistance, and cross-account restore."""
    am = AccountManager(base_dir=temp_env)

    reg_src = am.register_account("source@flow.local", "Source User", "source_pass_123")
    src_id = reg_src["account"]["id"]
    src_storage = StorageEngine(str(am.get_account_db_path(src_id)))
    src_storage.save_setting("favorite_model", "whisper-large-v3")
    src_storage.add_dictionary_word("Bioinformatics", "Science")
    src_storage.add_provider_connection(provider="groq", name="Vault Groq", api_key="gsk_vault_export_test")

    # Export vault
    passphrase = "my_strong_vault_passphrase_2026"
    vault_export = am.export_vault(src_id, passphrase)

    assert vault_export["flowvault_version"] == 1
    assert "salt_hex" in vault_export
    assert "nonce_hex" in vault_export
    assert "ciphertext_b64" in vault_export
    assert vault_export["account_username"] == "Source User"

    # Attempt to import with wrong passphrase must fail
    reg_dest = am.register_account("dest@flow.local", "Dest User", "dest_pass_123")
    dest_id = reg_dest["account"]["id"]

    with pytest.raises(ValueError, match="Decryption failed"):
        am.import_vault(dest_id, "wrong_passphrase", vault_export)

    # Import with correct passphrase must succeed
    import_res = am.import_vault(dest_id, passphrase, vault_export)
    assert import_res["success"] is True
    stats = import_res["stats"]
    assert stats["settings"] > 0
    assert stats["provider_connections"] == 1
    assert stats["dictionary"] == 1

    # Verify destination database received the data
    dest_storage = StorageEngine(str(am.get_account_db_path(dest_id)))
    assert dest_storage.get_setting("favorite_model") == "whisper-large-v3"
    dest_words = dest_storage.get_dictionary_words()
    assert "Bioinformatics" in dest_words
    dest_keys = [c["api_key"] for c in dest_storage.get_provider_connections("groq")]
    assert "gsk_vault_export_test" in dest_keys


def test_api_server_auth_routes(temp_env):
    """Integration test verifying REST API endpoints for authentication and vault sync."""
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    # Setup isolated test account manager
    test_am = AccountManager(base_dir=temp_env)
    old_singleton = am_module._account_manager
    am_module._account_manager = test_am

    # Repoint global storage to test primary DB
    primary_db = str(test_am.get_account_db_path("acc_primary"))
    storage.switch_account(primary_db)

    class TestServer(HTTPServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    server = TestServer(("127.0.0.1", 0), VoiceFlowApiHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/auth/status
        req = urllib.request.Request(f"{base_url}/api/auth/status")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["active_account"]["id"] == "acc_primary"

        # 2. POST /api/auth/register
        reg_payload = json.dumps({
            "username": "API Test User",
            "email": "api_test@flow.local",
            "password": "api_password_123",
            "avatar_color": "#10b981",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/register",
            data=reg_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            new_acc_id = data["account"]["id"]

        # 3. POST /api/auth/login
        login_payload = json.dumps({
            "email": "api_test@flow.local",
            "password": "api_password_123",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/login",
            data=login_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["account"]["email"] == "api_test@flow.local"

        # 4. POST /api/auth/switch back to primary
        switch_payload = json.dumps({"account_id": "acc_primary"}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/switch",
            data=switch_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["active_account"]["id"] == "acc_primary"

        # 5. POST /api/auth/vault/export
        export_payload = json.dumps({
            "account_id": "acc_primary",
            "passphrase": "vault_api_pass_123",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/vault/export",
            data=export_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            exported_vault = data["vault"]

        # 6. POST /api/auth/vault/import into new_acc_id
        import_payload = json.dumps({
            "account_id": new_acc_id,
            "passphrase": "vault_api_pass_123",
            "vault_data": exported_vault,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/vault/import",
            data=import_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True

        # 7. POST /api/auth/logout
        logout_payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/auth/logout",
            data=logout_payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8991"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True

        # 8. GET /api/auth/google/status
        req = urllib.request.Request(f"{base_url}/api/auth/google/status?pair_token=dummy_pair")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "claimed" in data
    finally:
        server.shutdown()
        server.server_close()
        am_module._account_manager = old_singleton


def test_google_account_auth(temp_env):
    """Verify authenticate_or_register_google auto-creates accounts and switches profiles."""
    am = AccountManager(base_dir=temp_env)

    # 1. Google sign-in with brand new user
    res1 = am.authenticate_or_register_google("newuser@gmail.com", "Google User 1")
    assert res1["success"] is True
    assert res1["account"]["email"] == "newuser@gmail.com"
    assert res1["account"]["username"] == "Google User 1"
    assert am.get_active_account_id() == res1["account"]["id"]

    # 2. Add custom data to this Google user's profile
    storage1 = StorageEngine(str(am.get_account_db_path(res1["account"]["id"])))
    storage1.save_setting("test_google_pref", "val123")

    # 3. Google sign-in again with same email should log in, not duplicate
    res2 = am.authenticate_or_register_google("newuser@gmail.com", "Updated Name")
    assert res2["account"]["id"] == res1["account"]["id"]
    # Verify data persisted
    storage2 = StorageEngine(str(am.get_account_db_path(res2["account"]["id"])))
    assert storage2.get_setting("test_google_pref") == "val123"


def test_active_db_path_resolution_across_restarts(temp_env, monkeypatch):
    """Verify that StorageEngine() without arguments automatically connects to active account DB."""
    am = AccountManager(base_dir=temp_env)
    old_singleton = am_module._account_manager
    am_module._account_manager = am

    try:
        # Default active is acc_primary
        primary_id = am.get_active_account_id()
        assert primary_id == "acc_primary"

        # Simulating fresh app startup: StorageEngine() with no args
        s1 = StorageEngine()
        assert s1.db_path == str(am.get_account_db_path("acc_primary"))
        s1.save_setting("test_restart_key", "primary_val")

        # Register and switch to account 2
        reg2 = am.register_account("user2@flow.local", "User Two", "pass1234")
        acc2_id = reg2["account"]["id"]
        am.switch_account(acc2_id)

        # Simulating another fresh app startup under user 2
        s2 = StorageEngine()
        assert s2.db_path == str(am.get_account_db_path(acc2_id))
        assert s2.get_setting("test_restart_key") is None
        s2.save_setting("test_restart_key", "user2_val")

        # Verify data isolation and persistence
        assert s2.get_setting("test_restart_key") == "user2_val"
        s1_check = StorageEngine(str(am.get_account_db_path("acc_primary")))
        assert s1_check.get_setting("test_restart_key") == "primary_val"
    finally:
        am_module._account_manager = old_singleton


def test_full_browser_google_callback_flow(temp_env, monkeypatch):
    """Verify end-to-end Google OAuth callback: /callback -> AccountManager -> pairing claimed."""
    import time
    from http.server import ThreadingHTTPServer
    from unittest.mock import patch
    from voice_flow.gui.api_server import VoiceFlowApiHandler
    from voice_flow import google_auth

    test_am = AccountManager(base_dir=temp_env)
    old_singleton = am_module._account_manager
    am_module._account_manager = test_am

    server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Start Google auth
        with patch.object(google_auth, "open_system_browser", return_value=True):
            start_res = google_auth.start_google_account_auth(port=port)
            assert start_res["success"] is True
            pair_token = start_res["pair_token"]
            auth_url = start_res["url"]
            assert "openid" in auth_url

            # Extract state from auth_url
            parsed_url = urllib.parse.urlparse(auth_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            state = query_params["state"][0]
            assert state.startswith("vfacct:")

        # 2. Check initial pairing status (should be pending)
        req = urllib.request.Request(f"{base_url}/api/auth/google/status?pair_token={pair_token}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["claimed"] is False

        # 3. Simulate Google redirect callback to /callback
        mock_tokens = {"access_token": "mock_access_token_123", "refresh_token": "mock_refresh_123", "expires_in": 3600}
        mock_userinfo = {
            "id": "google_uid_998877",
            "email": "sarah.connor@gmail.com",
            "name": "Sarah Connor",
            "picture": "https://example.com/sarah.jpg",
        }

        with patch.object(google_auth, "_provider_token_exchange", return_value=mock_tokens), \
             patch.object(google_auth, "_provider_userinfo", return_value=mock_userinfo):

            cb_url = f"{base_url}/callback?code=mock_code_abc&state={urllib.parse.quote(state)}"
            req_cb = urllib.request.Request(cb_url)
            with urllib.request.urlopen(req_cb) as resp:
                assert resp.status == 200
                html = resp.read().decode("utf-8")
                assert "Signed in as sarah.connor@gmail.com" in html

        # 4. Check polling status: must be claimed now
        req_status = urllib.request.Request(f"{base_url}/api/auth/google/status?pair_token={pair_token}")
        with urllib.request.urlopen(req_status) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["claimed"] is True
            assert data["active_account"]["email"] == "sarah.connor@gmail.com"
            assert data["active_account"]["username"] == "Sarah Connor"

        # 5. Verify AccountManager state
        active_acc = test_am.get_active_account()
        assert active_acc["email"] == "sarah.connor@gmail.com"
    finally:
        server.shutdown()
        server.server_close()
        am_module._account_manager = old_singleton


def test_google_account_switching_and_client_config(temp_env, monkeypatch):
    """Verify Google client configuration resolution and multi-Google account switching."""
    from voice_flow.google_auth import (
        account_client_config,
        PROVIDER_GOOGLE_PUBLIC_CLIENT_ID,
        PROVIDER_ANTIGRAVITY_CLIENT_ID,
    )

    # 1. Default config must NOT be Antigravity; it must be public Google client
    monkeypatch.delenv("GOOGLE_ACCOUNT_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    cfg_default = account_client_config()
    assert cfg_default["client_id"] == PROVIDER_GOOGLE_PUBLIC_CLIENT_ID
    assert cfg_default["client_id"] != PROVIDER_ANTIGRAVITY_CLIENT_ID

    # 2. Custom env config must take precedence
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "custom-12345.example.test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "custom_secret_xyz")
    cfg_custom = account_client_config()
    assert cfg_custom["client_id"] == "custom-12345.example.test"
    assert cfg_custom["client_secret"] == "custom_secret_xyz"

    # 3. Google Account registration & upgrade of placeholder
    am = AccountManager(base_dir=temp_env)
    initial = am.get_active_account()
    assert initial["id"] == "acc_primary"
    assert initial["email"] == "primary@flow.local"

    # First Google sign-in upgrades acc_primary
    res1 = am.authenticate_or_register_google(
        email="first.google@gmail.com",
        username="First Google",
        google_id="gid_111",
        avatar_url="https://lh3.googleusercontent.com/first.jpg",
    )
    assert res1["success"] is True
    acc1 = res1["account"]
    assert acc1["id"] == "acc_primary"
    assert acc1["email"] == "first.google@gmail.com"
    assert acc1["username"] == "First Google"
    assert acc1["google_id"] == "gid_111"
    assert acc1["avatar_url"] == "https://lh3.googleusercontent.com/first.jpg"

    # Second Google sign-in creates separate account
    res2 = am.authenticate_or_register_google(
        email="second.google@gmail.com",
        username="Second Google",
        google_id="gid_222",
        avatar_url="https://lh3.googleusercontent.com/second.jpg",
    )
    assert res2["success"] is True
    acc2 = res2["account"]
    assert acc2["id"] != "acc_primary"
    assert acc2["email"] == "second.google@gmail.com"
    assert am.get_active_account_id() == acc2["id"]

    # Switching accounts back to first Google account
    switch_res = am.switch_account("acc_primary")
    assert switch_res["success"] is True
    assert am.get_active_account_id() == "acc_primary"
    assert switch_res["active_account"]["email"] == "first.google@gmail.com"

    # Logout deactivates session
    am.logout_account()
    assert am.get_active_account_id() == ""


def test_settings_ui_order_and_switch_account_contract():
    """Verify that settings tabs are ordered General -> System -> Account,
    '+ Add Account' is replaced with 'Switch Account', and modal elements are wired.
    """
    root = Path(__file__).resolve().parent.parent
    html = (root / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    js = (root / "src" / "voice_flow" / "gui" / "app.js").read_text(encoding="utf-8")
    css = (root / "src" / "voice_flow" / "gui" / "usability.css").read_text(encoding="utf-8")

    # 1. Check sidebar nav order: General -> System -> Account
    nav_start = html.index('class="settings-side-nav"')
    nav_end = html.index('</div>', nav_start)
    nav_chunk = html[nav_start:nav_end]

    idx_gen = nav_chunk.index("switchSettingsTab('general'")
    idx_sys = nav_chunk.index("switchSettingsTab('system'")
    idx_acc = nav_chunk.index("switchSettingsTab('account'")
    assert idx_gen < idx_sys < idx_acc, f"Expected General -> System -> Account in nav, got indices {idx_gen}, {idx_sys}, {idx_acc}"

    # 2. Check modal-body tab container order: General -> System -> Account
    pos_tab_gen = html.index('id="set-tab-general"')
    pos_tab_sys = html.index('id="set-tab-system"')
    pos_tab_acc = html.index('id="set-tab-account"')
    assert pos_tab_gen < pos_tab_sys < pos_tab_acc, "Expected set-tab-general before set-tab-system before set-tab-account in DOM"

    # 3. Check that 'Add Account' button in profile actions is removed
    account_tab = html[pos_tab_acc:html.index('<!-- SETTINGS SUB-MODAL', pos_tab_acc)]
    assert "Add Account" not in account_tab, "Found 'Add Account' in account tab; expected replacement with 'Switch Account'"

    # 4. Check that 'Switch Account' button is wired
    assert 'onclick="handleSwitchAccountAction()"' in account_tab
    assert 'Switch Account' in account_tab
    assert 'account-switch-action-btn' in account_tab
    assert '.account-switch-action-btn' in css

    # 5. Check sub-modal and JS functions
    assert 'id="account-switch-sub-modal"' in html
    assert 'id="modal-account-switch-list"' in html
    assert 'async function handleSwitchAccountAction()' in js
    assert 'function openSwitchAccountModal(' in js
    assert 'async function handleSwitchAccountFromModal(' in js

    # 6. Check DOM IDs for navigation buttons
    assert 'id="settings-nav-general"' in html
    assert 'id="settings-nav-system"' in html
    assert 'id="settings-nav-account"' in html

    # 7. Check theme safety: no un-tokenized --text-color in switch modal
    switch_modal_html = html[html.index('id="account-switch-sub-modal"'):html.index('id="modal-add-connection"')]
    assert "var(--text-color)" not in switch_modal_html, "Found undefined var(--text-color); must use design system tokens"
    assert 'closeSubModal("account-switch-sub-modal")' in js
    assert "vfLoadProviders" in js


def test_end_to_end_switch_account_and_signout_data_isolation(temp_env):
    """End-to-end verification that Switch Account and Sign Out carry each account's
    data (API keys, dictionary, styles, history, settings) completely intact and isolated.
    """
    am = AccountManager(base_dir=temp_env)
    old_singleton = am_module._account_manager
    am_module._account_manager = am

    try:
        # 1. Connect Account A (e.g. via Google sign in)
        res_a = am.authenticate_or_register_google(
            email="user_alpha@gmail.com",
            username="Alpha User",
            google_id="gid_alpha_123",
        )
        id_a = res_a["account"]["id"]
        assert am.get_active_account_id() == id_a

        # Write data to Account A
        storage_a = StorageEngine(str(am.get_account_db_path(id_a)))
        storage_a.save_setting("dictation_mode", "smart_hybrid")
        storage_a.save_setting("theme_accent", "orange")
        storage_a.add_dictionary_word("AlphaAlgorithm", "Technology")
        storage_a.add_provider_connection(
            provider="groq",
            name="Alpha Groq",
            api_key="gsk_alpha_secret_key_111",
        )
        with storage_a._get_conn() as conn:
            conn.execute(
                """INSERT INTO history
                   (timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode)
                   VALUES ('2026-09-17 10:00:00', 'Alpha test raw', 'Alpha test polished.', 'CodeEditor', 4.5, 4, 120, 'smart_clean')"""
            )
            conn.commit()

        # Verify Account A storage has data
        assert storage_a.get_setting("dictation_mode") == "smart_hybrid"
        assert "AlphaAlgorithm" in storage_a.get_dictionary_words()
        alpha_keys = [c["api_key"] for c in storage_a.get_provider_connections("groq")]
        assert "gsk_alpha_secret_key_111" in alpha_keys
        with storage_a._get_conn() as conn:
            h_count = conn.execute("SELECT COUNT(*) FROM history WHERE raw_text = 'Alpha test raw'").fetchone()[0]
            assert h_count == 1

        # 2. Connect Account B
        res_b = am.authenticate_or_register_google(
            email="user_beta@gmail.com",
            username="Beta User",
            google_id="gid_beta_456",
        )
        id_b = res_b["account"]["id"]
        assert id_b != id_a
        assert am.get_active_account_id() == id_b

        # Account B must start fresh - no Account A data leaked
        storage_b = StorageEngine(str(am.get_account_db_path(id_b)))
        assert storage_b.get_setting("dictation_mode") is None
        assert "AlphaAlgorithm" not in storage_b.get_dictionary_words()
        beta_groq_keys = [c["api_key"] for c in storage_b.get_provider_connections("groq")]
        assert "gsk_alpha_secret_key_111" not in beta_groq_keys
        with storage_b._get_conn() as conn:
            h_count = conn.execute("SELECT COUNT(*) FROM history WHERE raw_text = 'Alpha test raw'").fetchone()[0]
            assert h_count == 0

        # Write Account B specific data
        storage_b.save_setting("dictation_mode", "strict_ptt")
        storage_b.save_setting("theme_accent", "emerald")
        storage_b.add_dictionary_word("BetaBiophysics", "Science")
        storage_b.add_provider_connection(
            provider="openai",
            name="Beta OpenAI",
            api_key="sk_beta_secret_key_222",
        )
        with storage_b._get_conn() as conn:
            conn.execute(
                """INSERT INTO history
                   (timestamp, raw_text, polished_text, app_name, duration_sec, word_count, wpm_speed, style_mode)
                   VALUES ('2026-09-17 11:00:00', 'Beta test raw', 'Beta test polished.', 'Browser', 3.0, 3, 90, 'casual')"""
            )
            conn.commit()

        # 3. Switch back to Account A using am.switch_account()
        switch_to_a = am.switch_account(id_a)
        assert switch_to_a["success"] is True
        assert am.get_active_account_id() == id_a

        # Account A carries ALL its original data intact
        assert storage_a.get_setting("dictation_mode") == "smart_hybrid"
        assert storage_a.get_setting("theme_accent") == "orange"
        assert "AlphaAlgorithm" in storage_a.get_dictionary_words()
        assert "BetaBiophysics" not in storage_a.get_dictionary_words()
        a_groq = [c["api_key"] for c in storage_a.get_provider_connections("groq")]
        assert "gsk_alpha_secret_key_111" in a_groq
        a_openai = [c["api_key"] for c in storage_a.get_provider_connections("openai")]
        assert "sk_beta_secret_key_222" not in a_openai
        with storage_a._get_conn() as conn:
            h_count_a = conn.execute("SELECT COUNT(*) FROM history WHERE raw_text = 'Alpha test raw'").fetchone()[0]
            assert h_count_a == 1
            h_count_b = conn.execute("SELECT COUNT(*) FROM history WHERE raw_text = 'Beta test raw'").fetchone()[0]
            assert h_count_b == 0

        # 4. Switch back to Account B using am.switch_account()
        switch_to_b = am.switch_account(id_b)
        assert switch_to_b["success"] is True
        assert am.get_active_account_id() == id_b

        # Account B carries ALL its data intact
        assert storage_b.get_setting("dictation_mode") == "strict_ptt"
        assert storage_b.get_setting("theme_accent") == "emerald"
        assert "BetaBiophysics" in storage_b.get_dictionary_words()
        assert "AlphaAlgorithm" not in storage_b.get_dictionary_words()
        b_openai = [c["api_key"] for c in storage_b.get_provider_connections("openai")]
        assert "sk_beta_secret_key_222" in b_openai

        # 5. Test Sign Out (am.logout_account)
        logout_ok = am.logout_account()
        assert logout_ok is True
        assert am.get_active_account_id() == ""

        # Global storage must repoint back to clean default DB, not Account B's DB
        assert Path(storage.db_path) == temp_env / "voice_flow.db"
        default_storage = StorageEngine(str(temp_env / "voice_flow.db"))
        assert "AlphaAlgorithm" not in default_storage.get_dictionary_words()
        assert "BetaBiophysics" not in default_storage.get_dictionary_words()
        default_groq = [c["api_key"] for c in default_storage.get_provider_connections("groq")]
        assert "gsk_alpha_secret_key_111" not in default_groq

        # 6. Re-switch / log back into Account A: all data is immediately available again
        relogin_a = am.switch_account(id_a)
        assert relogin_a["success"] is True
        assert am.get_active_account_id() == id_a
        assert Path(storage.db_path) == am.get_account_db_path(id_a)
        assert "AlphaAlgorithm" in storage.get_dictionary_words()
        recheck_keys = [c["api_key"] for c in storage.get_provider_connections("groq")]
        assert "gsk_alpha_secret_key_111" in recheck_keys
    finally:
        am_module._account_manager = old_singleton
        try:
            from voice_flow.storage import resolve_active_db_path
            storage.switch_account(resolve_active_db_path())
        except Exception:
            pass


def test_switch_and_logout_invalidates_history_cache(temp_env):
    """Verify that switching accounts or signing out purges the in-memory API history cache."""
    import time
    from voice_flow.gui.api_server import _API_CACHE, _API_CACHE_LOCK
    am = AccountManager(base_dir=temp_env)
    old_singleton = am_module._account_manager
    am_module._account_manager = am
    try:
        reg_a = am.register_account("alpha_cache@flow.local", "Alpha Cache", "pass123")
        reg_b = am.register_account("beta_cache@flow.local", "Beta Cache", "pass456")
        id_a = reg_a["account"]["id"]
        id_b = reg_b["account"]["id"]

        # Populate cache with dummy history item for Account A
        with _API_CACHE_LOCK:
            _API_CACHE["/api/history?limit=50"] = (time.time(), {"records": [{"id": 1, "raw_text": "cached A"}]})
            _API_CACHE["/api/insights?days=7"] = (time.time(), {"wpm": 120})

        assert "/api/history?limit=50" in _API_CACHE

        # Switch to Account B -> must purge history and insights cache
        am.switch_account(id_b)
        assert "/api/history?limit=50" not in _API_CACHE
        assert "/api/insights?days=7" not in _API_CACHE

        # Repopulate and test logout -> must also purge
        with _API_CACHE_LOCK:
            _API_CACHE["/api/history?limit=50"] = (time.time(), {"records": [{"id": 2, "raw_text": "cached B"}]})
        assert "/api/history?limit=50" in _API_CACHE

        am.logout_account()
        assert "/api/history?limit=50" not in _API_CACHE
    finally:
        am_module._account_manager = old_singleton
        try:
            from voice_flow.storage import resolve_active_db_path
            storage.switch_account(resolve_active_db_path())
        except Exception:
            pass




