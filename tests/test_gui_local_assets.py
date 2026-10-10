"""Enforce completeness of local media referenced by the GUI.

All referenced local assets must be present in the repository.
"""

from __future__ import annotations

from scripts.report_missing_gui_assets import missing_gui_assets


def test_asset_scanner_keeps_files_that_exist_in_the_repo():
    missing = missing_gui_assets()
    assert "src/voice_flow/gui/assets/logo.png" not in missing
    assert "src/voice_flow/gui/assets/onboarding/scene_1_mixed.mp3" not in missing
    assert "src/voice_flow/gui/VoiceFlow-Productivity-Card.png" not in missing


def test_all_referenced_local_gui_assets_exist():
    missing = missing_gui_assets()
    print("MISSING_GUI_ASSETS")
    for path in missing:
        print(path)
    assert not missing, "Missing referenced local GUI assets:\n" + "\n".join(missing)
