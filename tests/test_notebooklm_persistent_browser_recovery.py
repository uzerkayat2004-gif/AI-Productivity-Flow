import json
import sys
import time
import pytest
from types import ModuleType

from voice_flow.video_flow_engine.notebooklm import browser_sync


def _cookie(name, value, *, expires=-1):
    return {
        "name": name,
        "value": value,
        "domain": ".google.com",
        "path": "/",
        "expires": expires,
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    }


class _Page:
    url = "https://notebooklm.google.com/"

    def goto(self, *_args, **_kwargs):
        return None

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def evaluate(self, *_args, **_kwargs):
        return "person@example.com"

    def content(self):
        return ""


class _Context:
    def __init__(self, live_cookies):
        self.pages = [_Page()]
        self.live_cookies = list(live_cookies)
        self.added = []

    def cookies(self, *_args):
        return list(self.live_cookies)

    def add_cookies(self, cookies):
        self.added.extend(cookies)
        by_key = {(c["name"], c["domain"], c.get("path", "/")): c for c in self.live_cookies}
        for cookie in cookies:
            by_key[(cookie["name"], cookie["domain"], cookie.get("path", "/"))] = cookie
        self.live_cookies = list(by_key.values())

    def storage_state(self):
        return {"cookies": list(self.live_cookies), "origins": []}

    def close(self):
        return None


def _install_playwright(monkeypatch, context, launches):
    class Chromium:
        def launch_persistent_context(self, **kwargs):
            launches.append(kwargs)
            return context

    class Playwright:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    package = ModuleType("playwright")
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: Playwright()
    package.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_sync_does_not_overwrite_fresh_live_google_cookies_with_old_storage(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    (profile_dir / "browser_profile").mkdir(parents=True)
    storage = profile_dir / "storage_state.json"
    storage.write_text(json.dumps({"cookies": [
        _cookie("SID", "old-sid", expires=time.time() + 3600),
        _cookie("__Secure-1PSID", "old-psid", expires=time.time() + 3600),
        _cookie("NID", "stored-only-session", expires=-1),
    ]}), encoding="utf-8")
    context = _Context([
        _cookie("SID", "fresh-sid", expires=-1),
        _cookie("__Secure-1PSID", "fresh-psid", expires=time.time() + 86400),
    ])
    launches = []
    _install_playwright(monkeypatch, context, launches)
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: profile_dir)
    monkeypatch.setattr(browser_sync, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr(browser_sync, "get_storage_backup_path", lambda _profile=None: profile_dir / "missing.json")
    monkeypatch.setattr(browser_sync.config, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr(browser_sync.config, "get_storage_backup_path", lambda _profile=None: profile_dir / "missing.json")
    monkeypatch.setattr(browser_sync, "save_cookies_to_profile", lambda cookies, **kwargs: {
        "success": True,
        "cookies": cookies,
        "email": kwargs.get("email"),
    })

    result = browser_sync.sync_cookies_with_playwright(
        profile="owned", browser="chrome", headless=True, expected_email="person@example.com"
    )

    assert result["success"] is True
    captured = {c["name"]: c["value"] for c in result["cookies"]}
    assert captured["SID"] == "fresh-sid"
    assert captured["__Secure-1PSID"] == "fresh-psid"
    assert {c["name"] for c in context.added} == {"NID"}


def test_persistent_recovery_uses_only_owned_chrome_and_never_seeds_failed_jar(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    (profile_dir / "browser_profile").mkdir(parents=True)
    storage = profile_dir / "storage_state.json"
    storage.write_text(json.dumps({"cookies": [
        _cookie("SID", "known-dead-sid", expires=time.time() + 3600),
        _cookie("__Secure-1PSID", "known-dead-psid", expires=time.time() + 3600),
    ]}), encoding="utf-8")
    canonical_context = profile_dir / "context.json"
    canonical_master_token = profile_dir / "master_token.json"
    canonical_context.write_text('{"owner":"canonical-context"}', encoding="utf-8")
    canonical_master_token.write_text('{"owner":"canonical-master-token"}', encoding="utf-8")
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: profile_dir)
    monkeypatch.setattr(browser_sync, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state", lambda: {"running": False})
    monkeypatch.setattr(browser_sync.config, "is_profile_disconnected", lambda _profile=None: False)
    calls = []
    def fake_reauth(**kwargs):
        calls.append(kwargs)
        candidate = kwargs["storage_path"]
        assert candidate.name == "storage_state.json"
        assert candidate.parent.parent == profile_dir
        assert candidate.parent.name.startswith("storage_state.recovery.")
        assert not candidate.exists()
        assert not (candidate.parent / "context.json").exists()
        assert not (candidate.parent / "master_token.json").exists()
        candidate.write_text(json.dumps({
            "cookies": [_cookie("SID", "live-sid"), _cookie("__Secure-1PSID", "live-psid")],
            "account": {"email": "person@example.com"},
        }), encoding="utf-8")
        (candidate.parent / "context.json").write_text('{"owner":"scratch"}', encoding="utf-8")
        (candidate.parent / "context.json.lock").write_text("owned context lock", encoding="utf-8")
        (candidate.parent / ".context.json.lock").write_text("owned hidden context lock", encoding="utf-8")
        (candidate.parent / "master_token.json").write_text('{"owner":"scratch"}', encoding="utf-8")
        (candidate.parent / "master_token.json.lock").write_text("owned master-token lock", encoding="utf-8")
        (candidate.parent / ".master_token.json.lock").write_text("owned hidden master-token lock", encoding="utf-8")
        candidate.with_name(f".{candidate.name}.lock").write_text("owned lock", encoding="utf-8")
        return {"success": True, "reason": "verified", "detected_email": "person@example.com"}
    monkeypatch.setattr(browser_sync, "_run_cli_headless_reauth", fake_reauth)

    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", timeout_seconds=4)

    assert result["success"] is True
    assert result["source"] == "persistent_browser_recovery"
    assert calls[0]["profile"] == "owned"
    assert calls[0]["browser_profile"] == profile_dir / "browser_profile"
    assert calls[0]["timeout_seconds"] == 4
    assert calls[0]["storage_path"].parent.parent == profile_dir
    assert calls[0]["storage_path"].parent.name.startswith("storage_state.recovery.")
    assert calls[0]["storage_path"] != storage
    assert not calls[0]["storage_path"].exists()
    assert not calls[0]["storage_path"].parent.exists()
    assert canonical_context.read_text(encoding="utf-8") == '{"owner":"canonical-context"}'
    assert canonical_master_token.read_text(encoding="utf-8") == '{"owner":"canonical-master-token"}'


def test_persistent_recovery_rejects_unknown_account(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    (profile_dir / "browser_profile").mkdir(parents=True)
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: profile_dir)
    storage = profile_dir / "storage_state.json"
    original = b'{"canonical":"must-stay"}'
    storage.write_bytes(original)
    monkeypatch.setattr(browser_sync, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state", lambda: {"running": False})
    candidate_paths = []
    def fake_reauth(**kwargs):
        candidate_paths.append(kwargs["storage_path"])
        kwargs["storage_path"].write_text(json.dumps({
            "cookies": [_cookie("SID", "live-sid"), _cookie("__Secure-1PSID", "live-psid")],
        }), encoding="utf-8")
        return {"success": True, "reason": "verified"}
    monkeypatch.setattr(browser_sync, "_run_cli_headless_reauth", fake_reauth)

    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", timeout_seconds=0)

    assert result["success"] is False
    assert result["reason"] == "account_unverified"
    assert storage.read_bytes() == original
    assert not candidate_paths[0].exists()


def test_missing_owned_browser_profile_requires_signin(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: tmp_path / "missing")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state", lambda: {"running": False})

    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", 4)

    assert result == {
        "success": False,
        "reason": "needs_signin",
        "capture_reason": "missing_profile",
        "profile": "owned",
    }


def test_persistent_recovery_rejection_never_commits_candidate(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    (profile_dir / "browser_profile").mkdir(parents=True)
    storage = profile_dir / "storage_state.json"
    original = b'{"canonical":"original"}'
    storage.write_bytes(original)
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: profile_dir)
    monkeypatch.setattr(browser_sync, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state", lambda: {"running": False})
    candidates = []

    def mismatched(**kwargs):
        candidates.append(kwargs["storage_path"])
        kwargs["storage_path"].write_text(json.dumps({
            "cookies": [_cookie("SID", "other-sid"), _cookie("__Secure-1PSID", "other-psid")],
        }), encoding="utf-8")
        return {"success": True, "reason": "verified", "detected_email": "other@example.com"}

    monkeypatch.setattr(browser_sync, "_run_cli_headless_reauth", mismatched)
    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", 4)

    assert result["reason"] == "email_mismatch"
    assert storage.read_bytes() == original
    assert not candidates[0].exists()

    monkeypatch.setattr(
        browser_sync,
        "_run_cli_headless_reauth",
        lambda **kwargs: {"success": False, "reason": "passive_verify_failed"},
    )
    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", 4)
    assert result["reason"] == "passive_verify_failed"
    assert storage.read_bytes() == original


def test_generation_change_during_capture_prevents_commit_and_cleans_scratch(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profile"
    (profile_dir / "browser_profile").mkdir(parents=True)
    storage = profile_dir / "storage_state.json"
    original = b'{"canonical":"pre-switch"}'
    storage.write_bytes(original)
    generation = {"value": 4}
    scratch_paths = []
    monkeypatch.setattr(browser_sync, "get_profile_dir", lambda _profile=None: profile_dir)
    monkeypatch.setattr(browser_sync, "get_storage_state_path", lambda _profile=None: storage)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state", lambda: {"running": False})
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.get_session_generation",
        lambda _profile=None: generation["value"],
        raising=False,
    )
    monkeypatch.setattr(browser_sync.config, "is_profile_disconnected", lambda _profile=None: False)

    def delayed_capture(**kwargs):
        candidate = kwargs["storage_path"]
        lock = candidate.with_name(f".{candidate.name}.lock")
        scratch_paths.extend((candidate, lock))
        candidate.write_text(json.dumps({
            "cookies": [_cookie("SID", "new-sid"), _cookie("__Secure-1PSID", "new-psid")],
        }), encoding="utf-8")
        lock.touch()
        generation["value"] += 1
        return {"success": True, "reason": "verified", "detected_email": "person@example.com"}

    monkeypatch.setattr(browser_sync, "_run_cli_headless_reauth", delayed_capture)
    result = browser_sync.refresh_from_persistent_browser("owned", "person@example.com", 4)

    assert result == {
        "success": False, "reason": "stale_generation", "transient": True, "profile": "owned"
    }
    assert storage.read_bytes() == original
    assert all(not path.exists() for path in scratch_paths)


@pytest.mark.parametrize("json_indent", [None, 2])
def test_cli_runtime_recovery_is_chrome_only_and_passively_verified(tmp_path, monkeypatch, json_indent):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli = runtime / "notebooklm.exe"
    python = runtime / "python.exe"
    cli.touch()
    python.touch()
    commands = []

    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli",
        lambda: cli,
    )

    def fake_run(command, timeout):
        commands.append((command, timeout))
        if command[0] == str(python):
            compile(command[3], "<headless-recovery>", "exec")
            assert "browser='chrome'" in command[3]
            return 0, json.dumps({
                "status": "success", "reason": "captured", "detected_email": "person@example.com"
            })
        return 0, json.dumps({"status": "ok", "details": {"account": {"email": "person@example.com"}}}, indent=json_indent)

    monkeypatch.setattr(browser_sync, "_run_bounded_process", fake_run)
    result = browser_sync._run_cli_headless_reauth(
        profile="owned",
        storage_path=tmp_path / "storage_state.json",
        browser_profile=tmp_path / "browser_profile",
        timeout_seconds=12,
    )

    assert result["success"] is True
    assert result["detected_email"] == "person@example.com"
    assert commands[1][0][-5:] == ["auth", "check", "--test", "--passive", "--json"]
    assert commands[1][0][1:3] == ["--storage", str(tmp_path / "storage_state.json")]


def test_cli_runtime_resolves_release_interpreter_one_level_above_scripts(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime" / "python"
    scripts = runtime / "Scripts"
    scripts.mkdir(parents=True)
    cli = scripts / "notebooklm.exe"
    python = runtime / "python.exe"
    cli.touch()
    python.touch()
    commands = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli", lambda: cli
    )
    def fake_run(command, timeout):
        commands.append(command)
        if command[0] == str(python):
            return 0, json.dumps({
                "status": "success", "reason": "ok", "detected_email": "person@example.com"
            })
        return 0, json.dumps({"status": "ok"})
    monkeypatch.setattr(browser_sync, "_run_bounded_process", fake_run)

    result = browser_sync._run_cli_headless_reauth(
        profile="owned", storage_path=tmp_path / "candidate.json",
        browser_profile=tmp_path / "browser_profile", timeout_seconds=12,
    )

    assert result["success"] is True
    assert commands[0][0] == str(python)


def test_cli_capture_and_passive_verify_share_one_deadline(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli = runtime / "notebooklm.exe"
    python = runtime / "python.exe"
    cli.touch()
    python.touch()
    timeouts = []
    ticks = iter((100.0, 100.0, 107.0))
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli", lambda: cli
    )
    monkeypatch.setattr(browser_sync.time, "monotonic", lambda: next(ticks))

    def fake_run(command, timeout):
        timeouts.append(timeout)
        if command[0] == str(python):
            return 0, json.dumps({
                "status": "success", "reason": "ok", "detected_email": "person@example.com"
            })
        return 0, json.dumps({"status": "ok"})

    monkeypatch.setattr(browser_sync, "_run_bounded_process", fake_run)
    result = browser_sync._run_cli_headless_reauth(
        profile="owned", storage_path=tmp_path / "candidate.json",
        browser_profile=tmp_path / "browser_profile", timeout_seconds=12,
    )

    assert result["success"] is True
    assert timeouts == [12.0, 5.0]


def test_zero_exit_malformed_passive_verification_is_failure(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli = runtime / "notebooklm.exe"
    python = runtime / "python.exe"
    cli.touch()
    python.touch()
    calls = {"count": 0}
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.resolve_notebooklm_cli", lambda: cli
    )

    def fake_run(command, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return 0, json.dumps({
                "status": "success", "reason": "ok", "detected_email": "person@example.com"
            })
        return 0, "not-json despite exit zero"

    monkeypatch.setattr(browser_sync, "_run_bounded_process", fake_run)
    result = browser_sync._run_cli_headless_reauth(
        profile="owned", storage_path=tmp_path / "candidate.json",
        browser_profile=tmp_path / "browser_profile", timeout_seconds=12,
    )

    assert result["success"] is False
    assert result["reason"] == "passive_verify_failed"
