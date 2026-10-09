"""Report onboarding media that the GUI references but the repo does not contain.

The absence is expected until those files are added from the owner's machine.
The report stays non-blocking so CI remains green.
"""

from __future__ import annotations

import pytest

from scripts.report_missing_gui_assets import missing_gui_assets


def test_asset_scanner_keeps_files_that_exist_in_the_repo():
    missing = missing_gui_assets()
    assert "src/voice_flow/gui/assets/logo.png" not in missing
    assert "src/voice_flow/gui/assets/onboarding/scene_1_mixed.mp3" not in missing
    assert "src/voice_flow/gui/VoiceFlow-Productivity-Card.png" not in missing


def test_missing_onboarding_media_is_reported_without_failing_ci():
    missing = missing_gui_assets()
    print("MISSING_GUI_ASSETS")
    for path in missing:
        print(path)
    if missing:
        pytest.xfail(
            "expected until onboarding media is committed:\n" + "\n".join(missing)
        )
