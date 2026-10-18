"""v1.0.11: Video Flow shows the real failure reason and recovers sign-in like Audio Flow."""
from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.engine import VideoFlowEngine


def test_failed_local_fallback_reports_notebooklm_signin(monkeypatch, tmp_path):
    engine = VideoFlowEngine()
    calls = {}

    def fake_run(video_id, **kwargs):
        calls["provider"] = kwargs.get("provider")
        return {"video_id": video_id, "state": "failed", "error_code": "generation_failed",
                "error_message": "planner exploded", "message": "planner exploded"}

    monkeypatch.setattr(engine, "run", fake_run)
    result = engine._auth_fallback_to_local("vid", {"source_text": "x"}, "x", None, None, "t", RuntimeError("auth_expired: expired"))
    assert calls["provider"] == "visual-v2.1"
    assert result["error_code"] == "auth_expired"
    assert "sign in" in result["error_message"].lower()
    assert result["fallback_error"] == "planner exploded"


def test_successful_local_fallback_is_untouched(monkeypatch):
    engine = VideoFlowEngine()
    monkeypatch.setattr(engine, "run", lambda video_id, **k: {"state": "complete", "video_path": "v.mp4"})
    result = engine._auth_fallback_to_local("vid", {}, "x", None, None, "t", RuntimeError("expired"))
    assert result == {"state": "complete", "video_path": "v.mp4"}


def test_recover_auth_tries_browser_sync_after_master_token(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import browser_sync, login_flow

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr(login_flow, "self_heal", lambda profile=None: {"ok": False, "error": "no token"})
    monkeypatch.setattr(browser_sync, "auto_sync_from_browser", lambda profile=None: {"success": True})

    class Status:
        authenticated = True

    class Prov:
        profile = "p"
        def sync_storage_state(self, force=False):
            pass
        def check_auth(self, raise_on_error=True):
            return Status()

    heal = VideoFlowEngine._recover_notebooklm_auth("p", Prov())
    assert heal == {"ok": True, "method": "browser_sync"}


def test_recover_auth_reports_failure(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import login_flow

    monkeypatch.delenv("VOICE_FLOW_TEST_AUTO_HEAL", raising=False)
    monkeypatch.delenv("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL", raising=False)
    monkeypatch.setattr(login_flow, "self_heal", lambda profile=None: {"ok": False, "error": "no token"})
    heal = VideoFlowEngine._recover_notebooklm_auth("p", object())
    assert heal["ok"] is False and heal["error"] == "no token"


def test_job_card_shows_error_message_not_code():
    src = Path("src/voice_flow/gui/api_server.py").read_text(encoding="utf-8")
    assert 'meta.get("error_message")' in src
    assert '"error_code": (meta.get("error_code") or "")' in src
