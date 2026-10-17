"""Launch checks for the v1.0.4 bug list that can be verified without a device."""
from __future__ import annotations

import numpy as np

from voice_flow.dictionary_rules import is_proper_noun_entry, term_problem
from voice_flow.nemotron_engine import _merge_overlap_transcripts, _segment_bounds, _speech_pause_ranges
from voice_flow.text_processing import cleanup_text


def test_common_word_names_are_allowed_when_capitalized() -> None:
    for name in ("Bill", "Mark", "May", "Will", "Grace", "Rose", "Hope"):
        assert is_proper_noun_entry(name)
        assert term_problem(name) is None
    assert term_problem("bill") is not None
    assert term_problem("meeting") is not None
    assert term_problem("OK") is not None
    assert term_problem("Bill Gates") is None


def test_filler_removal_drops_the_stray_comma_and_double_space() -> None:
    assert cleanup_text("so, um, I think", "cleanup_light") == "so I think"
    assert cleanup_text("Um, we should ship it", "cleanup_light") == "we should ship it"
    assert cleanup_text("The ER team approved it", "cleanup_light") == "The ER team approved it"


def test_long_audio_splits_only_at_a_real_pause() -> None:
    sr = 16000
    # 14 seconds: loud speech, a 200 ms pause at 6 s, then loud speech again.
    wav = np.ones(14 * sr, dtype=np.float32) * 0.2
    pause_at = 6 * sr
    wav[pause_at: pause_at + int(0.2 * sr)] = 0.0
    pauses = _speech_pause_ranges(wav, sr)
    assert pauses, "the silence gap should be detected"
    bounds = _segment_bounds(len(wav), sr, pauses)
    assert len(bounds) >= 2
    # The cut sits inside the silence, not in the middle of the loud region.
    cut = bounds[0][1]
    assert pause_at <= cut <= pause_at + int(0.2 * sr)


def test_continuous_speech_is_not_split_mid_word() -> None:
    sr = 16000
    wav = np.ones(14 * sr, dtype=np.float32) * 0.2
    # A 100 ms dip, the old splitter's target, is not a pause.
    wav[3 * sr: 3 * sr + int(0.1 * sr)] *= 0.2
    pauses = _speech_pause_ranges(wav, sr)
    bounds = _segment_bounds(len(wav), sr, pauses)
    assert bounds == [(0, len(wav))]


def test_overlap_transcripts_drop_the_repeated_boundary() -> None:
    assert _merge_overlap_transcripts(["hello there friend", "friend how are you"]) == "hello there friend how are you"


def test_downloadable_models_have_checksums() -> None:
    from voice_flow.downloadable_models import ALL_DOWNLOADABLE_MODELS_REGISTRY

    for spec in ALL_DOWNLOADABLE_MODELS_REGISTRY:
        digest = str(spec.get("sha256") or "")
        assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest), spec["id"]


def test_recording_cap_is_five_minutes() -> None:
    from voice_flow.main import MAX_RECORDING_SECONDS

    assert MAX_RECORDING_SECONDS == 5 * 60


def test_polish_success_is_not_labeled_a_fallback() -> None:
    from voice_flow.main import _polish_outcome_label

    assert "fallback" not in _polish_outcome_label("local_model").lower()
    assert _polish_outcome_label("polishing_off") == "Polishing off"
    assert _polish_outcome_label("disabled") == "Basic cleanup applied"


def test_skip_tour_does_not_mark_page_guides_seen() -> None:
    from pathlib import Path

    source = Path("src/voice_flow/gui/app.js").read_text(encoding="utf-8")
    finish = source[source.index("function finishOnboarding(options)"):source.index("// AUDIO FLOW IN-APP GUIDANCE ENGINE")]
    assert "if (skipped)" in finish
    assert finish.index("if (skipped)") < finish.index("startAudioFlowGuide(")
    skipped_branch = finish[finish.index("if (skipped)"):finish.index("startAudioFlowGuide(")]
    assert "af_guided" not in skipped_branch
    assert "vf_guided" not in skipped_branch
    assert "vf_voice_guided" not in skipped_branch


def test_install_script_refuses_intel_and_old_macos() -> None:
    from pathlib import Path

    script = Path("scripts/install.sh").read_text(encoding="utf-8")
    assert "Apple Silicon" in script
    assert "Intel Macs" in script
    assert "Sonoma" in script
    assert '[ "$MACOS_MAJOR" -lt 14 ]' in script


def test_uninstaller_keeps_user_data_unless_asked() -> None:
    from pathlib import Path

    iss = Path("release/installer/apf-setup.iss").read_text(encoding="utf-8")
    assert "\n[Tasks]" not in iss
    uninstall = iss.split("[UninstallDelete]", 1)[1].split("[", 1)[0]
    assert ".voice_flow" not in uninstall
    assert r"{app}\runtime" in uninstall
    assert r'Name: "{app}"' in uninstall
    assert r'Name: "{group}"' in uninstall
    code = iss.split("[Code]", 1)[1]
    assert "CurUninstallStepChanged" in code
    assert "usUninstall" in code
    assert r"{userprofile}\.voice_flow" in code
    assert "MB_DEFBUTTON2" in code
    assert "DelTree" in code
    assert "Remove my data" in code
