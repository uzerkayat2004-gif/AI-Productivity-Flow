from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import voice_flow.video_flow_providers as providers_module
from voice_flow.video_flow_providers import VideoFlowProviderService


def test_antigravity_oauth_finds_standard_windows_user_install(tmp_path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "Programs" / "Antigravity" / "Antigravity.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    launches: list[list[str]] = []

    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr("voice_flow.video_flow_providers.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "voice_flow.video_flow_providers.subprocess.Popen",
        lambda command, **_kwargs: launches.append(command),
    )

    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    result = service.start_oauth("antigravity")

    assert result["success"] is True
    assert launches == [[str(executable)]]

def test_video_flow_provider_policy_is_complete_and_isolated(tmp_path):
    db_path = tmp_path / "voice-flow.db"
    service = VideoFlowProviderService(str(db_path))

    catalog = service.catalog()
    assert [provider["id"] for provider in catalog["oauth"]] == [
        "claude_code",
        "antigravity",
        "openai_codex",
    ]
    assert len(catalog["api_key"]) >= 10
    assert {provider["id"] for provider in catalog["local"]} == {
        "ollama",
        "lm_studio",
        "llama_cpp",
    }

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "video_flow_provider_connections" in tables
    assert "provider_connections" not in tables

    model_ids = {
        (model["provider"], model["model_id"])
        for model in catalog["models"]
    }
    assert {
        ("openai", "gpt-5.6-sol"),
        ("openai", "gpt-5.6-terra"),
        ("openai", "gpt-5.6-luna"),
        ("anthropic", "claude-sonnet-5"),
        ("anthropic", "claude-opus-5"),
        ("vertex_ai", "gemini-3.1-pro"),
        ("nvidia_nim", "nvidia/nemotron-3-ultra-550b-a55b"),
        ("opencode_zen", "nemotron-3-ultra-free"),
        ("openrouter", "openrouter/free"),
    } <= model_ids


def test_custom_model_gets_automatic_provider_prefix(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    model = service.add_model("vertex_ai", "vx/gemini-4.0-pro", "Gemini 4 Pro")

    assert model["model_id"] == "gemini-4.0-pro"
    assert model["full_id"] == "vx/gemini-4.0-pro"
    assert model["provider_prefix"] == "vx"
    assert model["custom"] is True


def test_api_key_is_never_returned_by_provider_responses(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    connection = service.add_connection(
        "gemini",
        name="Production key",
        secret="super-secret-value",
        priority=2,
    )
    details = service.provider_details("gemini")

    assert connection["has_secret"] is True
    assert "secret" not in connection
    assert "api_key" not in connection
    assert "super-secret-value" not in repr(details)
    assert service.active_connections("gemini")[0]["secret"] == "super-secret-value"


def test_video_flow_selected_model_setting_is_dedicated(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    connection = service.add_connection(
        "gemini", name="Production key", secret="super-secret-value"
    )
    service.update_connection(connection["id"], status="connected")

    service.set_active_model("gemini/gemini-3.5-flash")

    assert service.get_active_model() == "gemini/gemini-3.5-flash"
    with sqlite3.connect(service.db_path) as conn:
        row = conn.execute(
            "SELECT value FROM video_flow_provider_settings WHERE key = 'active_model'"
        ).fetchone()
    assert row == ('"gemini/gemini-3.5-flash"',)


def test_active_model_requires_a_connected_enabled_model_or_existing_combo(tmp_path):
    db_path = tmp_path / "voice-flow.db"
    service = VideoFlowProviderService(str(db_path))

    with pytest.raises(ValueError, match="connected, enabled"):
        service.set_active_model("gemini/gemini-3.5-flash")
    with pytest.raises(ValueError, match="connected, enabled"):
        service.set_active_model("combo:missing")

    connection = service.add_connection(
        "gemini", name="Production key", secret="super-secret-value"
    )
    service.update_connection(connection["id"], status="connected")

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS video_flow_combos (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS video_flow_combo_models (combo_id INTEGER NOT NULL, model_ref TEXT NOT NULL, position INTEGER NOT NULL)")
        conn.execute("INSERT OR REPLACE INTO video_flow_combos (id, name) VALUES (1, 'remote')")
        conn.execute("INSERT INTO video_flow_combo_models (combo_id, model_ref, position) VALUES (1, 'gemini/gemini-3.5-flash', 0)")
        conn.commit()

    service.set_active_model("combo:remote")
    assert service.get_active_model() == "combo:remote"

    service.update_connection(connection["id"], is_active=False)
    assert service.get_active_model() == "local/deterministic"


def test_removed_builtin_model_falls_back_to_local_planner(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    service.set_setting("active_model", "gemini/gemini-2.5-flash")

    assert service.get_active_model() == "local/deterministic"


def test_models_include_capability_badges(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    models = service.catalog()["models"]

    assert models
    assert any("vision" in model["capabilities"] for model in models)
    assert any("reasoning" in model["capabilities"] for model in models)


def test_unknown_provider_is_rejected(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    with pytest.raises(ValueError, match="Unknown Video Flow provider"):
        service.add_model("voice-flow-global-provider", "model")


def test_catalog_upgrade_removes_stale_defaults_but_preserves_custom_models(tmp_path):
    db_path = tmp_path / "voice-flow.db"
    VideoFlowProviderService(str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO video_flow_provider_models
            (provider, model_id, display_name, capabilities_json, is_active, custom, created_at)
            VALUES ('openai', 'retired-default', 'Retired', '[]', 1, 0, 'now')"""
        )
        conn.execute(
            """INSERT INTO video_flow_provider_models
            (provider, model_id, display_name, capabilities_json, is_active, custom, created_at)
            VALUES ('openai', 'my-private-model', 'Private', '[]', 1, 1, 'now')"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO video_flow_provider_settings (key, value) VALUES ('seed_catalog_version', '\"legacy\"')"
        )
        conn.commit()

    upgraded = VideoFlowProviderService(str(db_path))
    ids = {model["model_id"] for model in upgraded.list_models("openai", include_inactive=True)}

    assert "retired-default" not in ids
    assert "my-private-model" in ids

def test_gemini_seed_catalog_only_advertises_the_verified_primary_route(tmp_path):
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    gemini_defaults = {
        model["model_id"]
        for model in service.list_models("gemini")
        if not model["custom"]
    }

    assert gemini_defaults == {"gemini-3.5-flash"}
def test_antigravity_status_uses_signed_in_cli_without_sidecar_tokens(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "antigravity_state.pbtxt"
    state_file.write_text("state", encoding="utf-8")
    monkeypatch.setattr(providers_module, "find_antigravity_executable", lambda: tmp_path / "Antigravity.exe")
    monkeypatch.setattr(providers_module, "antigravity_state_path", lambda: state_file)
    monkeypatch.setattr(providers_module, "find_antigravity_cli", lambda: tmp_path / "agy.exe")

    status = VideoFlowProviderService(str(tmp_path / "voice-flow.db")).oauth_status("antigravity")

    assert status["connected"] is True
    assert status["bridge_ready"] is True
    assert status["bridge"]["source"] == "cli"
    assert status["bridge"]["csrf_configured"] is False

def test_antigravity_catalog_refreshes_stale_bridge_cache(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "antigravity_state.pbtxt"
    state_file.write_text("state", encoding="utf-8")
    monkeypatch.setattr(providers_module, "find_antigravity_executable", lambda: tmp_path / "Antigravity.exe")
    monkeypatch.setattr(providers_module, "antigravity_state_path", lambda: state_file)
    monkeypatch.setattr(providers_module, "find_antigravity_cli", lambda: tmp_path / "agy.exe")
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    service.set_setting("oauth_status:antigravity", {"connected": True, "bridge_ready": False, "label": "stale"})

    models = [item for item in service.list_models("antigravity") if item["available"]]

    assert len(models) == 6