"""NotebookLM config resolution reuses the live app settings singleton."""
from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.notebooklm import config


class SettingsSingleton:
    def __init__(self):
        self.is_global_singleton = True
        self.settings = {
            "video_flow_notebooklm_cli": None,
            "video_flow_notebooklm_mcp": None,
            "video_flow_notebooklm_profile": None,
        }
        self.repoints = 0

    def repoint_if_needed(self):
        self.repoints += 1

    def get_setting(self, key):
        return self.settings.get(key)


def test_repeated_resolvers_reuse_live_storage_singleton_and_read_edits_immediately(
    monkeypatch, tmp_path: Path
):
    import voice_flow.storage as storage_module

    singleton = SettingsSingleton()
    monkeypatch.setattr(storage_module, "storage", singleton, raising=False)
    constructions = []

    def forbidden_constructor(*args, **kwargs):
        constructions.append((args, kwargs))
        raise AssertionError("resolver constructed a new StorageEngine")

    monkeypatch.setattr(storage_module, "StorageEngine", forbidden_constructor)
    monkeypatch.delenv("NOTEBOOKLM_PROFILE", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_CLI", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_MCP", raising=False)

    cli_a = tmp_path / "first" / "notebooklm.exe"
    cli_b = tmp_path / "second" / "notebooklm.exe"
    mcp_a = tmp_path / "first" / "notebooklm-mcp.exe"
    mcp_b = tmp_path / "second" / "notebooklm-mcp.exe"
    for path in (cli_a, cli_b, mcp_a, mcp_b):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    singleton.settings.update({
        "video_flow_notebooklm_cli": str(cli_a),
        "video_flow_notebooklm_mcp": str(mcp_a),
        "video_flow_notebooklm_profile": "first-profile",
    })
    assert config.resolve_notebooklm_cli() == cli_a.resolve()
    assert config.resolve_notebooklm_mcp() == mcp_a.resolve()
    assert config.resolve_notebooklm_profile() == "first-profile"

    singleton.settings.update({
        "video_flow_notebooklm_cli": str(cli_b),
        "video_flow_notebooklm_mcp": str(mcp_b),
        "video_flow_notebooklm_profile": "second-profile",
    })
    assert config.resolve_notebooklm_cli() == cli_b.resolve()
    assert config.resolve_notebooklm_mcp() == mcp_b.resolve()
    assert config.resolve_notebooklm_profile() == "second-profile"
    assert constructions == []
    assert singleton.repoints == 6


def test_resolver_precedence_keeps_explicit_then_settings_then_environment(
    monkeypatch, tmp_path: Path
):
    import voice_flow.storage as storage_module

    singleton = SettingsSingleton()
    monkeypatch.setattr(storage_module, "storage", singleton, raising=False)
    monkeypatch.setattr(storage_module, "StorageEngine", lambda: (_ for _ in ()).throw(AssertionError()))
    explicit_cli = tmp_path / "explicit.exe"
    stored_cli = tmp_path / "stored.exe"
    environment_cli = tmp_path / "environment.exe"
    for path in (explicit_cli, stored_cli, environment_cli):
        path.touch()
    singleton.settings["video_flow_notebooklm_cli"] = str(stored_cli)
    singleton.settings["video_flow_notebooklm_profile"] = "settings-profile"
    monkeypatch.setenv("NOTEBOOKLM_PROFILE", "environment-profile")
    monkeypatch.setenv("NOTEBOOKLM_CLI", str(environment_cli))

    assert config.resolve_notebooklm_cli(explicit_cli) == explicit_cli.resolve()
    assert config.resolve_notebooklm_cli() == stored_cli.resolve()
    assert config.resolve_notebooklm_profile("explicit-profile") == "explicit-profile"
    assert config.resolve_notebooklm_profile() == "settings-profile"

    singleton.settings["video_flow_notebooklm_cli"] = None
    singleton.settings["video_flow_notebooklm_profile"] = None
    assert config.resolve_notebooklm_cli() == environment_cli.resolve()
    assert config.resolve_notebooklm_profile() == "environment-profile"


def test_login_email_settings_reads_and_writes_reuse_singleton(monkeypatch):
    import voice_flow.storage as storage_module
    from voice_flow.video_flow_engine.notebooklm import login_flow

    singleton = SettingsSingleton()
    singleton.settings["video_flow_notebooklm_email"] = "saved@example.com"
    writes = []
    singleton.save_setting = lambda key, value: writes.append((key, value))
    monkeypatch.setattr(storage_module, "storage", singleton, raising=False)
    monkeypatch.setattr(
        storage_module, "StorageEngine",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("constructed a new StorageEngine")),
    )
    monkeypatch.setattr(config, "get_storage_state_path", lambda profile=None: Path("missing-state.json"))

    assert login_flow._storage_email("profile-without-file") == "saved@example.com"
    login_flow._save_email("updated@example.com")
    assert writes == [("video_flow_notebooklm_email", "updated@example.com")]
    assert singleton.repoints == 2


def test_non_global_storage_handle_is_not_repointed(monkeypatch):
    import voice_flow.storage as storage_module

    explicit_handle = SettingsSingleton()
    explicit_handle.is_global_singleton = False
    explicit_handle.settings["video_flow_notebooklm_profile"] = "temporary-profile"
    monkeypatch.setattr(storage_module, "storage", explicit_handle, raising=False)

    assert config.resolve_notebooklm_profile() == "temporary-profile"
    assert explicit_handle.repoints == 0
