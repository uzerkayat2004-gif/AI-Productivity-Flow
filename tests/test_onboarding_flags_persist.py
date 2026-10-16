"""M-UI-1: onboarding "seen" flags must survive app restarts.

pywebview 6 defaults to private_mode=True (fresh profile, localStorage wiped
each launch). The main window now passes private_mode=False, and the flags are
mirrored to the backend settings so a reset WebView profile does not replay
guides. "Replay onboarding" still clears them.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from voice_flow.gui import desktop_launcher
from voice_flow.storage import storage

APP_JS = (Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui" / "app.js").read_text(encoding="utf-8")


def test_main_window_keeps_webview_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine import notebooklm

    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)
    monkeypatch.setattr(notebooklm, "start_keepalive_daemon", lambda: False)
    monkeypatch.setattr(notebooklm, "trigger_keepalive_now", lambda *a, **k: False)
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    mock_webview = MagicMock()
    mock_webview.create_window.return_value = MagicMock()
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    desktop_launcher.launch_desktop_gui()

    mock_webview.start.assert_called_once()
    _, kwargs = mock_webview.start.call_args
    assert kwargs.get("private_mode") is False


def test_every_webview_start_disables_private_mode() -> None:
    src = Path(desktop_launcher.__file__).read_text(encoding="utf-8")
    calls = re.findall(r"webview\.start\(([^)]*)\)", src)
    assert calls
    assert all("private_mode=False" in c for c in calls), calls


def _persisted_flags() -> list[str]:
    block = re.search(r"const PERSISTED_ONBOARDING_FLAGS = \[(.*?)\];", APP_JS, re.S)
    assert block, "PERSISTED_ONBOARDING_FLAGS missing"
    return re.findall(r'"([^"]+)"', block.group(1))


def test_guide_and_onboarding_flags_are_mirrored_to_backend() -> None:
    flags = _persisted_flags()
    for key in ("hasViewedOnboarding", "vf_onboarding.done", "vf_onboarding.af_guided",
                "vf_onboarding.vf_guided", "vf_onboarding.vf_voice_guided"):
        assert key in flags
    assert 'const ONBOARDING_FLAGS_SETTING_KEY = "onboarding_seen_flags";' in APP_JS
    # Eligibility (which gates every automatic guide) waits for hydration.
    eligibility = APP_JS[APP_JS.index("function loadOnboardingEligibility()"):]
    eligibility = eligibility[: eligibility.index("\n}\n")]
    assert "await hydrateOnboardingFlags();" in eligibility


def test_replay_onboarding_clears_every_guide_flag() -> None:
    replay = APP_JS[APP_JS.index("function replayOnboarding()"):]
    replay = replay[: replay.index("\n}\n")]
    for key in ("vf_onboarding.done", "hasViewedOnboarding", "vf_onboarding.af_guided",
                "vf_onboarding.vf_guided", "vf_onboarding.vf_voice_guided"):
        assert f'setOnboardingFlag("{key}", "")' in replay
    assert '"has_viewed_onboarding", value: false' in replay


def test_backend_setting_round_trips_flag_object() -> None:
    flags = {"vf_onboarding.af_guided": "1", "hasViewedOnboarding": ""}
    assert storage.save_setting("onboarding_seen_flags", flags) is True
    assert storage.get_setting("onboarding_seen_flags") == flags
