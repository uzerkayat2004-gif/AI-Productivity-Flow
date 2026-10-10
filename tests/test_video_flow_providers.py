from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import voice_flow.video_flow_providers as providers_module
from voice_flow.video_flow_providers import VideoFlowProviderService


# REMOVED 2026-08-31: test_antigravity_oauth_uses_google_consent_popup —
# the Video Flow start_oauth PKCE web branch was deleted; OAuth sign-in now
# goes through /api/video-flow/oauth/authorize + /exchange (9Router design).


def test_antigravity_oauth_connection_makes_models_available_without_desktop_app(tmp_path, monkeypatch):
    monkeypatch.setattr(providers_module, "find_antigravity_executable", lambda: None)
    monkeypatch.setattr(
        providers_module,
        "antigravity_state_path",
        lambda: tmp_path / "missing" / "antigravity_state.pbtxt",
    )
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))

    before = service.oauth_status("antigravity")
    assert before["connected"] is False

    connection = service.add_connection(
        "antigravity",
        name="Antigravity me@example.com",
        secret="oauth-access-token",
        account_id="me@example.com",
    )
    service.update_connection(int(connection["id"]), status="active")

    status = service.oauth_status("antigravity", refresh=True)
    assert status["connected"] is True
    assert status["account_id"] == "me@example.com"

    models = service.list_models("antigravity")
    assert models
    assert all(item["available"] for item in models)

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


def test_active_model_requires_a_connected_enabled_model(tmp_path):
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

    service.set_active_model("gemini/gemini-3.5-flash")
    assert service.get_active_model() == "gemini/gemini-3.5-flash"

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
# REMOVED 2026-08-31: test_antigravity_status_uses_signed_in_cli_without_sidecar_tokens —
# the desktop-app bridge branch of oauth_status("antigravity") was deleted along
# with the old Video Flow OAuth system; account state is now connection-based.

def test_antigravity_catalog_refreshes_stale_cache(tmp_path, monkeypatch) -> None:
    service = VideoFlowProviderService(str(tmp_path / "voice-flow.db"))
    # A stale cached status must not hide a freshly-created active connection:
    # oauth_status for antigravity always recomputes (refresh=True).
    service.set_setting("oauth_status:antigravity", {"connected": False, "label": "stale"})
    connection = service.add_connection(
        "antigravity", name="Antigravity me@example.com", secret="token", account_id="me@example.com",
    )
    service.update_connection(int(connection["id"]), status="active")

    models = [item for item in service.list_models("antigravity") if item["available"]]

    assert len(models) == 6
    assert service.oauth_status("antigravity", refresh=False)["connected"] is True