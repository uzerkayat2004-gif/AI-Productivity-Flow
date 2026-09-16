"""Comprehensive unit and integration tests for NotebookLM MCP integration,
durable token refresh, keepalive daemon, and official direct web authentication.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from voice_flow.google_auth import (
    NOTEBOOKLM_ACCOUNT_CHOOSER_URL,
    NOTEBOOKLM_OFFICIAL_LOGIN_URL,
    start_notebooklm_browser_flow,
)
from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
from voice_flow.video_flow_engine.notebooklm import (
    NotebookLMKeepaliveService,
    NotebookLMMcpClient,
    NotebookLMService,
    NotebookLMVideoError,
    NotebookLMVideoProvider,
    generate_mcp_config,
    get_keepalive_service,
    get_keepalive_status,
    get_mcp_server_info,
    get_notebooklm_service,
    resolve_notebooklm_mcp,
    start_keepalive_daemon,
    stop_keepalive_daemon,
    trigger_keepalive_now,
)
from voice_flow.video_flow_engine.notebooklm.config import (
    get_master_token_path,
    is_session_near_expiry,
    resolve_notebooklm_profile,
)
from voice_flow.video_flow_engine.notebooklm.keepalive import (
    DEFAULT_KEEPALIVE_INTERVAL_SECONDS,
)
from voice_flow.video_flow_engine.notebooklm.login_flow import (
    ensure_fresh_session,
    master_token_present,
    self_heal,
    start_login,
)


class MockCliRunner:
    """Mock runner for testing CLI and MCP invocations."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.commands: list[list[str]] = []

    def __call__(self, command, timeout=60.0):
        self.commands.append(list(command))
        if not self.responses:
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        resp = self.responses.pop(0)
        return SimpleNamespace(
            returncode=resp.get("returncode", 0),
            stdout=json.dumps(resp.get("payload", {})),
            stderr=resp.get("stderr", ""),
        )


# ==============================================================================
# 1. Authentication Flow & Official Web URLs
# ==============================================================================

def test_start_notebooklm_browser_flow_direct_official_urls(monkeypatch):
    """Verify direct=True opens official Google NotebookLM web URL instead of OAuth consent."""
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    # Standard sign-in: official login URL
    res_normal = start_notebooklm_browser_flow(port=8991, direct=True, switch_account=False)
    assert res_normal["success"] is True
    assert res_normal["opened"] is True
    assert len(opened_urls) == 1
    assert opened_urls[0] == NOTEBOOKLM_OFFICIAL_LOGIN_URL
    assert "notebooklm.google.com" in opened_urls[0]
    assert "o/oauth2/v2/auth" not in opened_urls[0]

    # Switch account: account chooser URL
    res_switch = start_notebooklm_browser_flow(port=8991, direct=True, switch_account=True)
    assert res_switch["success"] is True
    assert len(opened_urls) == 2
    assert opened_urls[1] == NOTEBOOKLM_ACCOUNT_CHOOSER_URL
    assert "AccountChooser" in opened_urls[1]
    assert "continue=https%3A%2F%2Fnotebooklm.google.com%2F" in opened_urls[1]


def test_start_login_direct_mode(monkeypatch):
    """Verify start_login with direct=True dispatches direct Google NotebookLM URL."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    opened_urls = []
    monkeypatch.setattr("voice_flow.google_auth.open_system_browser", lambda url: opened_urls.append(url) or True)

    res = start_login(profile="video-flow-experiment", direct=True, switch_account=True)
    assert res["launched"] is True
    assert res["mode"] == "browser"
    assert res["direct_login_url"] == NOTEBOOKLM_ACCOUNT_CHOOSER_URL
    assert len(opened_urls) == 1
    assert opened_urls[0] == NOTEBOOKLM_ACCOUNT_CHOOSER_URL


# ==============================================================================
# 2. Session Freshness, Cookie Expiration, and Durable Master Token
# ==============================================================================

def test_is_session_near_expiry_detection(tmp_path, monkeypatch):
    """Test is_session_near_expiry correctly identifies missing, expired, and fresh session cookies."""
    storage_file = tmp_path / "storage_state.json"
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: storage_file,
    )

    # 1. Missing file -> near expiry
    assert is_session_near_expiry("test-prof") is True

    # 2. File with missing PSIDTS -> near expiry
    now = time.time()
    storage_file.write_text(
        json.dumps({
            "cookies": [
                {"name": "SID", "value": "sid123", "expires": now + 1000000},
                {"name": "__Secure-1PSID", "value": "psid123", "expires": now + 1000000},
            ]
        }),
        encoding="utf-8",
    )
    assert is_session_near_expiry("test-prof") is True

    # 3. File with expired PSIDTS -> near expiry
    storage_file.write_text(
        json.dumps({
            "cookies": [
                {"name": "SID", "value": "sid123", "expires": now + 1000000},
                {"name": "__Secure-1PSIDTS", "value": "psidts123", "expires": now - 60},
            ]
        }),
        encoding="utf-8",
    )
    assert is_session_near_expiry("test-prof") is True

    # 4. File with fresh PSIDTS (e.g. 5 days remaining) -> fresh
    storage_file.write_text(
        json.dumps({
            "cookies": [
                {"name": "SID", "value": "sid123", "expires": now + 1000000},
                {"name": "__Secure-1PSID", "value": "psid123", "expires": now + 1000000},
                {"name": "__Secure-1PSIDTS", "value": "psidts123", "expires": now + 500000},
            ]
        }),
        encoding="utf-8",
    )
    assert is_session_near_expiry("test-prof") is False

    # 5. File modified > 24 hours ago (e.g. laptop closed for days) -> near expiry even if nominal cookie exp is far
    old_time = now - (86400 * 2)  # 2 days ago
    os.utime(storage_file, (old_time, old_time))
    assert is_session_near_expiry("test-prof") is True


def test_ensure_fresh_session_skips_when_fresh(tmp_path, monkeypatch):
    """Verify ensure_fresh_session does nothing if cookies are already fresh and force=False."""
    now = time.time()
    storage_file = tmp_path / "storage_state.json"
    storage_file.write_text(
        json.dumps({
            "cookies": [
                {"name": "SID", "value": "sid123", "expires": now + 1000000},
                {"name": "__Secure-1PSIDTS", "value": "psidts123", "expires": now + 500000},
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: storage_file,
    )

    heal_called = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda profile=None: heal_called.append(True) or {"ok": True},
    )

    res = ensure_fresh_session(profile="test-prof", force=False)
    assert res["ok"] is True
    assert res["refreshed"] is False
    assert len(heal_called) == 0

    # With force=True, it refreshes
    res_force = ensure_fresh_session(profile="test-prof", force=True)
    assert res_force["ok"] is True
    assert res_force["refreshed"] is True
    assert len(heal_called) == 1


# ==============================================================================
# 3. Background Keepalive Service
# ==============================================================================

def test_keepalive_service_lifecycle():
    """Verify NotebookLMKeepaliveService starts, reports status, runs once, and stops cleanly."""
    refresh_runs = []

    def mock_refresh(profile=None):
        refresh_runs.append(profile)
        return {"ok": True, "profile": profile}

    service = NotebookLMKeepaliveService(
        profile="test-keepalive",
        interval_seconds=300,
        refresh_func=mock_refresh,
    )

    assert not service.is_running()
    stat = service.status()
    assert stat["running"] is False
    assert stat["run_count"] == 0

    # Run once forced
    res = service.run_once(force=True)
    assert res["ran"] is True
    assert res["success"] is True
    assert len(refresh_runs) == 1

    # Start service
    started = service.start(interval_seconds=300)
    assert started is True
    assert service.is_running()

    # Second start is idempotent
    assert not service.start()

    # Stop service
    stopped = service.stop()
    assert stopped is True
    assert not service.is_running()


def test_global_keepalive_module_functions():
    """Verify start_keepalive_daemon, stop_keepalive_daemon, and get_keepalive_status."""
    stop_keepalive_daemon()
    stat_before = get_keepalive_status()
    assert isinstance(stat_before, dict)

    started = start_keepalive_daemon(interval_seconds=300)
    assert started is True

    stat_active = get_keepalive_status()
    assert stat_active["running"] is True

    stopped = stop_keepalive_daemon()
    assert stopped is True
    assert get_keepalive_status()["running"] is False


def test_keepalive_startup_refresh_updates_last_success(monkeypatch):
    """Verify that starting keepalive executes an immediate startup refresh and updates last_success."""
    monkeypatch.setattr("voice_flow.storage.StorageEngine.get_setting", lambda self, k, d=None: False if "disconnect" in k else d)
    runs = []

    def mock_refresh(profile=None):
        runs.append(time.time())
        return {"ok": True, "profile": profile}

    service = NotebookLMKeepaliveService(
        profile="test-startup-refresh",
        interval_seconds=300,
        refresh_func=mock_refresh,
    )

    stat_init = service.status()
    assert stat_init["last_success"] == 0.0
    assert stat_init["run_count"] == 0

    # Start the daemon - should run immediately upon boot without waiting 30 seconds
    started = service.start(interval_seconds=300)
    assert started is True

    # Give thread a brief moment to run the immediate check
    deadline = time.time() + 3.0
    while time.time() < deadline and service.status()["last_success"] == 0.0:
        time.sleep(0.05)

    stat_after = service.status()
    assert stat_after["last_success"] > 0.0
    assert stat_after["run_count"] >= 1
    assert len(runs) >= 1

    service.stop()


def test_keepalive_clock_jump_wake_detection(monkeypatch):
    """Verify that a system clock jump (e.g. laptop lid opened after days) triggers immediate refresh."""
    monkeypatch.setattr("voice_flow.storage.StorageEngine.get_setting", lambda self, k, d=None: False if "disconnect" in k else d)
    runs = []

    def mock_refresh(profile=None):
        runs.append(time.time())
        return {"ok": True, "profile": profile}

    service = NotebookLMKeepaliveService(
        profile="test-wake-jump",
        interval_seconds=600,
        refresh_func=mock_refresh,
    )

    started = service.start()
    assert started is True

    # Wait for initial boot check
    deadline = time.time() + 2.0
    while time.time() < deadline and len(runs) < 1:
        time.sleep(0.05)

    assert len(runs) >= 1
    init_run_count = len(runs)

    # Now simulate a system wake event: trigger run_once or trigger_now
    res = service.trigger_now(force=True, background=False)
    assert res["ran"] is True
    assert res["success"] is True
    assert len(runs) == init_run_count + 1

    service.stop()


def test_trigger_keepalive_now_background_and_sync():
    """Verify trigger_keepalive_now handles synchronous and asynchronous background execution."""
    runs = []

    def mock_refresh(profile=None):
        runs.append(time.time())
        return {"ok": True, "profile": profile}

    service = get_keepalive_service("test-trigger-now")
    service._refresh_func = mock_refresh

    # 1. Synchronous trigger
    res_sync = trigger_keepalive_now("test-trigger-now", force=True, background=False)
    assert res_sync["ran"] is True
    assert res_sync["success"] is True
    assert len(runs) == 1

    # 2. Background trigger
    res_bg = trigger_keepalive_now("test-trigger-now", force=True, background=True)
    assert res_bg["dispatched"] is True

    deadline = time.time() + 2.0
    while time.time() < deadline and len(runs) < 2:
        time.sleep(0.05)
    assert len(runs) == 2



# ==============================================================================
# 4. MCP Configuration, Server, and Client Bridge
# ==============================================================================

def test_generate_mcp_config_and_server_info(tmp_path):
    """Verify generate_mcp_config produces standard format and get_mcp_server_info reports status."""
    cfg_file = tmp_path / "mcp-config.json"
    cfg = generate_mcp_config(profile="video-flow-experiment", config_path=cfg_file)

    assert "mcpServers" in cfg
    assert "notebooklm" in cfg["mcpServers"]
    entry = cfg["mcpServers"]["notebooklm"]
    assert "--profile" in entry["args"]
    assert "video-flow-experiment" in entry["args"]
    assert cfg_file.is_file()

    info = get_mcp_server_info(profile="video-flow-experiment")
    assert "available" in info
    assert "authenticated" in info
    assert info["profile"] == "video-flow-experiment"


def test_mcp_client_bridge_operations():
    """Verify NotebookLMMcpClient creates notebooks, lists notebooks, and invokes CLI."""
    runner = MockCliRunner([
        {"payload": {"notebooks": [{"id": "nb-101", "title": "Project Alpha"}]}},
        {"payload": {"notebook": {"id": "nb-102", "title": "Project Beta"}}},
    ])

    fake_cli = Path(tempfile.gettempdir()) / "mock_notebooklm.exe"
    fake_cli.write_bytes(b"stub")

    client = NotebookLMMcpClient(
        profile="video-flow-experiment",
        cli_path=fake_cli,
        runner=runner,
    )

    # 1. list_notebooks
    notebooks = client.list_notebooks()
    assert len(notebooks) == 1
    assert notebooks[0]["id"] == "nb-101"
    assert "list" in runner.commands[0]

    # 2. create_notebook
    created = client.create_notebook("Project Beta")
    assert created["id"] == "nb-102"
    assert "create" in runner.commands[1]
    assert "Project Beta" in runner.commands[1]


def test_mcp_client_auto_heals_on_auth_expired(monkeypatch):
    """Verify NotebookLMMcpClient catches auth_expired, auto-heals via self_heal, and retries."""
    runner = MockCliRunner([
        # First call fails with auth expired
        {"returncode": 1, "stderr": "Error: Google session expired or invalid (__Secure-1PSIDTS expired)"},
        # Second call after self-heal succeeds
        {"returncode": 0, "payload": {"notebooks": [{"id": "nb-recovered", "title": "Recovered"}]}},
    ])

    fake_cli = Path(tempfile.gettempdir()) / "mock_notebooklm.exe"
    fake_cli.write_bytes(b"stub")

    heal_calls = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.mcp_client.is_session_near_expiry",
        lambda profile=None: False,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda profile=None: heal_calls.append(profile) or {"ok": True},
    )

    client = NotebookLMMcpClient(
        profile="video-flow-experiment",
        cli_path=fake_cli,
        runner=runner,
    )

    notebooks = client.list_notebooks()
    assert len(notebooks) == 1
    assert notebooks[0]["id"] == "nb-recovered"
    assert len(heal_calls) == 1  # Self heal was triggered reactively and recovered the call!


# ==============================================================================
# 5. Provider Auto-Heal Integration
# ==============================================================================

def test_provider_auto_heals_on_auth_expired(monkeypatch):
    """Verify NotebookLMVideoProvider._invoke auto-heals and retries when CLI returns auth expired."""
    fake_runner = MockCliRunner([
        {"returncode": 1, "stderr": "Google account login expired. Please sign in to NotebookLM."},
        {"returncode": 0, "payload": {"notebook": {"id": "nb-auto-healed", "title": "Auto Healed"}}},
    ])

    fake_cli = Path(tempfile.gettempdir()) / "mock_notebooklm.exe"
    fake_cli.write_bytes(b"stub")

    heal_invocations = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda profile=None: heal_invocations.append(profile) or {"ok": True},
    )

    provider = NotebookLMVideoProvider(
        cli_path=fake_cli,
        profile="video-flow-experiment",
        runner=fake_runner,
    )

    created = provider.create_notebook("Auto Healed")
    assert created.notebook_id == "nb-auto-healed"
    assert len(heal_invocations) == 1
    assert len(fake_runner.commands) == 2


# ==============================================================================
# 6. High-Level Service & API Server MCP Endpoints
# ==============================================================================

def test_notebooklm_service_facade():
    """Verify NotebookLMService coordinates status, keepalive, and MCP client."""
    service = get_notebooklm_service("video-flow-experiment")
    assert service.profile == "video-flow-experiment"

    status = service.get_status()
    assert "available" in status
    assert "authenticated" in status
    assert "keepalive" in status
    assert "master_token_present" in status

    cfg = service.get_mcp_config()
    assert "mcpServers" in cfg


def test_api_server_mcp_endpoints(monkeypatch, tmp_path):
    """HTTP integration test verifying all new MCP and keepalive endpoints in api_server."""
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)

    db_path = str(tmp_path / "vf_mcp_test.db")
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, "storage", test_storage)
    monkeypatch.setattr("voice_flow.storage.storage", test_storage)

    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. GET /api/video-flow/notebooklm/mcp/status
        req = urllib.request.Request(f"{base_url}/api/video-flow/notebooklm/mcp/status", headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert "mcp" in data

        # 2. GET /api/video-flow/notebooklm/mcp/config
        req_cfg = urllib.request.Request(f"{base_url}/api/video-flow/notebooklm/mcp/config", headers={"Connection": "close"})
        with urllib.request.urlopen(req_cfg, timeout=10) as resp:
            data_cfg = json.loads(resp.read().decode("utf-8"))
            assert data_cfg["success"] is True
            assert "config" in data_cfg

        # 3. GET /api/video-flow/notebooklm/keepalive/status
        req_ka = urllib.request.Request(f"{base_url}/api/video-flow/notebooklm/keepalive/status", headers={"Connection": "close"})
        with urllib.request.urlopen(req_ka, timeout=10) as resp:
            data_ka = json.loads(resp.read().decode("utf-8"))
            assert data_ka["success"] is True
            assert "keepalive" in data_ka

        # 4. POST /api/video-flow/notebooklm/keepalive/start
        req_start = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/keepalive/start",
            data=json.dumps({"interval_seconds": 600}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(req_start, timeout=10) as resp:
            data_start = json.loads(resp.read().decode("utf-8"))
            assert data_start["success"] is True
            assert data_start["started"] is True

        # 5. POST /api/video-flow/notebooklm/keepalive/stop
        req_stop = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/keepalive/stop",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(req_stop, timeout=10) as resp:
            data_stop = json.loads(resp.read().decode("utf-8"))
            assert data_stop["success"] is True
            assert data_stop["stopped"] is True

        # 6. POST /api/video-flow/notebooklm/keepalive/refresh
        req_ref = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/keepalive/refresh",
            data=json.dumps({"force": False}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(req_ref, timeout=10) as resp:
            data_ref = json.loads(resp.read().decode("utf-8"))
            assert data_ref["success"] is True
            assert "keepalive" in data_ref
            assert "result" in data_ref

        # 7. GET /api/video-flow/notebooklm/keepalive/refresh
        req_get_ref = urllib.request.Request(
            f"{base_url}/api/video-flow/notebooklm/keepalive/refresh",
            headers={"Connection": "close"},
        )
        with urllib.request.urlopen(req_get_ref, timeout=10) as resp:
            data_get_ref = json.loads(resp.read().decode("utf-8"))
            assert data_get_ref["success"] is True
            assert "keepalive" in data_get_ref

    finally:
        server.shutdown()
        server.server_close()


def test_keepalive_loop_clock_jump_triggers_refresh(monkeypatch):
    """Verify that a time jump > 5s inside the loop directly triggers wake refresh."""
    runs = []
    def mock_refresh(profile=None):
        runs.append(time.time())
        return {"ok": True, "profile": profile}

    service = NotebookLMKeepaliveService(
        profile="test-loop-jump",
        interval_seconds=600,
        refresh_func=mock_refresh,
    )

    # Fake time progression: boot check, then a 10s jump on the next tick
    orig_time = time.time
    t = [1000.0]

    def fake_time():
        return t[0]

    def fake_sleep(dur):
        # Jump time by 10s during the sleep call (simulating lid close/open)
        t[0] += 10.0

    monkeypatch.setattr("time.time", fake_time)
    monkeypatch.setattr("time.sleep", fake_sleep)

    # Run loop directly in a worker thread and stop it once a wake refresh occurs
    thread = threading.Thread(target=service._run_loop, daemon=True)
    thread.start()

    deadline = orig_time() + 2.0
    while orig_time() < deadline and len(runs) < 2:
        orig_time_mod = __import__("time")
        orig_time_mod.sleep(0.05)

    service.stop()
    thread.join(timeout=1.0)
    assert len(runs) >= 2  # 1 boot check + 1 wake detection check


def test_playwright_sync_skips_expired_cookies_during_seeding(tmp_path, monkeypatch):
    """Verify sync_cookies_with_playwright seeds only non-expired cookies into Playwright."""
    from voice_flow.video_flow_engine.notebooklm.browser_sync import sync_cookies_with_playwright

    now = time.time()
    st_path = tmp_path / "storage_state.json"
    st_path.write_text(json.dumps({
        "cookies": [
            {"name": "SID", "value": "valid_sid", "expires": now + 10000},
            {"name": "__Secure-1PSIDTS", "value": "expired_ts", "expires": now - 3600},
            {"name": "__Secure-1PSID", "value": "valid_psid", "expires": now + 10000},
        ]
    }), encoding="utf-8")

    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda prof=None: st_path,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_backup_path",
        lambda prof=None: tmp_path / "storage_state.backup.json",
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_profile_dir",
        lambda prof=None: tmp_path,
    )
    monkeypatch.setattr(
        "voice_flow.storage.storage.get_setting",
        lambda k, default=None: None,
    )

    added_cookies = []

    class DummyContext:
        pages = []
        def add_cookies(self, cookies):
            added_cookies.extend(cookies)
        def new_page(self):
            class DummyPage:
                url = "https://notebooklm.google.com/"
                def goto(self, *a, **kw): pass
                def wait_for_load_state(self, *a, **kw): pass
                def evaluate(self, *a, **kw): return "test@gmail.com"
                def content(self): return ""
            return DummyPage()
        def storage_state(self):
            return {
                "cookies": [
                    {"name": "SID", "value": "valid_sid", "domain": ".google.com"},
                    {"name": "__Secure-1PSID", "value": "valid_psid", "domain": ".google.com"},
                    {"name": "__Secure-1PSIDTS", "value": "fresh_ts", "domain": ".google.com"},
                ]
            }
        def close(self): pass

    class DummyChromium:
        def launch_persistent_context(self, *a, **kw):
            return DummyContext()

    class DummyPlaywright:
        chromium = DummyChromium()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    import sys
    from types import ModuleType
    mock_pw_mod = ModuleType("playwright")
    mock_sync_api = ModuleType("playwright.sync_api")
    mock_sync_api.sync_playwright = lambda: DummyPlaywright()
    mock_pw_mod.sync_api = mock_sync_api
    monkeypatch.setitem(sys.modules, "playwright", mock_pw_mod)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mock_sync_api)

    res = sync_cookies_with_playwright(profile="test-pw-seed", headless=True)
    assert res["success"] is True
    added_names = [c["name"] for c in added_cookies]
    assert "SID" in added_names
    assert "__Secure-1PSID" in added_names
    # The expired timestamp cookie must have been filtered out and NOT added
    assert "__Secure-1PSIDTS" not in added_names


def test_desktop_launcher_poke_keepalive_sends_background_flag(monkeypatch):
    """Verify desktop_launcher._poke_keepalive_refresh dispatches with background=True."""
    from voice_flow.gui.desktop_launcher import _poke_keepalive_refresh

    captured_requests = []

    class DummyResponse:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout=None):
        captured_requests.append(req)
        return DummyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    _poke_keepalive_refresh()
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert "/api/video-flow/notebooklm/keepalive/refresh" in req.full_url
    assert req.method == "POST"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload.get("background") is True
