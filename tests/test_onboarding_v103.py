"""v1.0.3 onboarding fixes: tour timing, Skip Tour placement, pause/resume,
per-guide first-open, Mac guide gating, and voiceover loudness/pace consistency."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
GUI = ROOT / "src" / "voice_flow" / "gui"
ASSETS = GUI / "assets" / "onboarding"
APP_JS = (GUI / "app.js").read_text(encoding="utf-8")
INDEX = (GUI / "index.html").read_text(encoding="utf-8")
HERO_JS = (GUI / "onboarding-hero.js").read_text(encoding="utf-8")
TIMELINES = json.loads((ASSETS / "narration_timelines.json").read_text(encoding="utf-8"))
CLIPS = {k: v for k, v in TIMELINES.items() if not k.startswith("_")}


def _fn(name: str) -> str:
    start = APP_JS.index(f"function {name}(")
    end = APP_JS.index("\n}\n", start)
    return APP_JS[start:end]


# ---------- 1. tour advance waits for the voiceover ----------

def test_tour_has_no_fixed_auto_advance_timer() -> None:
    speak = _fn("speakOnboardingNarration")
    assert "16000" not in speak and "setTimeout" not in speak, "auto mode must not run a fixed timer"
    assert 'addEventListener("ended"' in speak and "_onboardingNarrationFinished" in speak


def test_tour_fallback_clock_only_on_audio_failure() -> None:
    speak = _fn("speakOnboardingNarration")
    # fallback is started from the error path and the non-autoplay rejection path only
    assert speak.count("_startOnboardingFallbackClock(") == 2
    assert 'addEventListener("error"' in speak
    assert 'err.name === "NotAllowedError"' in speak and "installOnboardingGestureUnlocker()" in speak
    clock = _fn("_startOnboardingFallbackClock")
    assert "onboardingNarrationPaused" in clock and ".duration" in clock


def test_auto_advance_respects_pause() -> None:
    sched = _fn("_scheduleOnboardingAutoAdvance")
    assert "!onboardingNarrationPaused" in sched and "ONBOARDING_AUTO_ADVANCE_PAD_MS" in sched
    toggle = _fn("toggleOnboardingNarration")
    assert "_clearOnboardingAutoAdvance()" in toggle


def test_scene1_caption_clock_does_not_loop_over_a_pause() -> None:
    assert "% 40.5" not in HERO_JS
    assert "return scene1Visible() && !player;" in HERO_JS


def test_every_beat_and_caption_lands_before_the_audio_ends() -> None:
    for name, clip in CLIPS.items():
        lines = clip["lines"]
        assert lines, name
        assert all(a["start"] < b["start"] for a, b in zip(lines, lines[1:])), name
        assert lines[-1]["start"] < clip["speech_end"] < clip["duration"], name
        for beat, t in clip["beats"].items():
            assert 0 < t < clip["speech_end"], (name, beat)


def test_app_js_generated_block_matches_timelines_json() -> None:
    m = re.search(r"const ONBOARDING_NARRATION_TIMELINES = (\{.*?\});\n// END GENERATED", APP_JS, re.S)
    assert m
    block = json.loads(m.group(1))
    assert set(block) == set(CLIPS)
    for name, clip in CLIPS.items():
        assert block[name]["lines"] == clip["lines"], name
        assert block[name]["duration"] == clip["duration"], name


# ---------- 2. Skip Tour in the bottom-right group ----------

def test_skip_tour_lives_in_each_scenes_bottom_right_group() -> None:
    for k in range(1, 6):
        a = INDEX.index(f'<div class="s{k}-actions">')
        b = INDEX.index("</div>", a)
        group = INDEX[a:b]
        assert "ob-skip-btn" in group, f"scene {k}: Skip Tour not in the actions group"
        assert f'id="scene{k}-auto-btn"' in group and f'id="scene{k}-theme-btn"' in group
    assert INDEX.count('finishOnboarding({ skipped: true })" title="Skip the tour"') == 5
    assert "<!-- Skip Tour Badge -->" not in INDEX


# ---------- 3. pause / resume everywhere ----------

@pytest.mark.parametrize("prefix,flag", [("Video", "_vfGuideNarrationPaused"), ("Voice", "_voiceflowGuideNarrationPaused")])
def test_guide_pause_never_blocks_later_playback(prefix: str, flag: str) -> None:
    play = _fn(f"play{prefix}FlowGuideNarration")
    assert f"if ({flag}) return;" not in play
    assert f"{flag} = false;" in _fn(f"stop{prefix}FlowGuideAudio")


@pytest.mark.parametrize("name", ["toggleAudioFlowGuideAudio", "toggleVideoFlowGuideAudio", "toggleVoiceFlowGuideAudio", "toggleOnboardingNarration"])
def test_toggles_resume_the_same_player(name: str) -> None:
    body = _fn(name)
    assert "player.paused || player.ended" in body
    assert "player.play()" in body and "player.pause()" in body


# ---------- 4. per-guide first open + persisted seen state ----------

def test_guides_start_per_page_for_enrolled_profiles() -> None:
    assert '"vf_onboarding.guides_enrolled"' in APP_JS.split("const PERSISTED_ONBOARDING_FLAGS = [", 1)[1].split("];", 1)[0]
    allowed = _fn("automaticGuidesAllowed")
    assert "eligible === true" in allowed and "guides_enrolled" in allowed and "v2_seen" in allowed
    sched = _fn("scheduleAutomaticGuide")
    assert sched.count("automaticGuidesAllowed(") == 2
    assert "eligible !== true" not in sched
    assert 'setOnboardingFlag("vf_onboarding.guides_enrolled", "1")' in _fn("maybeShowOnboarding")
    assert 'setOnboardingFlag("vf_onboarding.guides_enrolled", "1")' in _fn("replayOnboarding")


def test_seen_flags_flush_to_backend_on_exit() -> None:
    flush = _fn("flushOnboardingFlags")
    assert "keepalive: true" in flush and "ONBOARDING_FLAGS_SETTING_KEY" in flush
    assert 'addEventListener("pagehide", flushOnboardingFlags)' in APP_JS


# ---------- 8. Mac ----------

def test_no_video_flow_guide_on_mac() -> None:
    assert "vf_guide_step4_mac" not in APP_JS
    assert not list(ASSETS.glob("vf_guide_*mac*"))
    assert "vfVideoFlowGatedOnMac()" in _fn("startVideoFlowGuide")
    assert 'feature === "video" && typeof vfVideoFlowGatedOnMac === "function" && vfVideoFlowGatedOnMac()' in _fn("scheduleAutomaticGuide")


def test_mac_clips_exist_for_tour_scene2_and_voice_shortcut() -> None:
    assert "scene_2_mac" in CLIPS and (ASSETS / "scene_2_mac_mixed.mp3").exists()
    assert "coming to Mac soon" in " ".join(l["text"] for l in CLIPS["scene_2_mac"]["lines"])
    mac = " ".join(l["text"] for l in CLIPS["voiceflow_guide_step4_mac"]["lines"])
    assert "Command plus Option" in mac and "Windows" not in mac
    assert "Control plus Windows" in " ".join(l["text"] for l in CLIPS["voiceflow_guide_step4"]["lines"])


# ---------- 5. one voice, one pace, one loudness ----------

def _decode(path: Path) -> tuple[np.ndarray, int]:
    av = pytest.importorskip("av")
    with av.open(str(path)) as c:
        st = c.streams.audio[0]
        sr = st.rate
        chunks = [f.to_ndarray() for f in c.decode(st)]
    x = np.concatenate([ch if ch.ndim == 2 else ch[None, :] for ch in chunks], axis=1).astype(np.float64)
    if x.shape[0] > 2:  # packed interleaved
        x = x.reshape(-1, 2).T
    return x, sr


def _integrated_lufs(x: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770-4 integrated loudness (K-weighting, 400 ms blocks, gating)."""
    signal = pytest.importorskip("scipy.signal")
    # K-weighting filter coefficients for arbitrary sample rates (same derivation as pyloudnorm).
    def shelf(G, Q, fc):
        A = 10 ** (G / 40); w0 = 2 * np.pi * fc / sr; alpha = np.sin(w0) / (2 * Q)
        b = [A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha), -2 * A * ((A - 1) + (A + 1) * np.cos(w0)),
             A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)]
        a = [(A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha, 2 * ((A - 1) - (A + 1) * np.cos(w0)),
             (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha]
        return np.array(b) / a[0], np.array(a) / a[0]
    def highpass(Q, fc):
        w0 = 2 * np.pi * fc / sr; alpha = np.sin(w0) / (2 * Q)
        b = [(1 + np.cos(w0)) / 2, -(1 + np.cos(w0)), (1 + np.cos(w0)) / 2]
        a = [1 + alpha, -2 * np.cos(w0), 1 - alpha]
        return np.array(b) / a[0], np.array(a) / a[0]
    y = x
    for b, a in (shelf(4.0, 1 / np.sqrt(2), 1500.0), highpass(0.5, 38.0)):
        y = signal.lfilter(b, a, y, axis=1)
    block, step = int(0.4 * sr), int(0.1 * sr)
    z = np.array([np.mean(y[:, i:i + block] ** 2, axis=1) for i in range(0, y.shape[1] - block + 1, step)])
    lk = -0.691 + 10 * np.log10(np.sum(z, axis=1) + 1e-20)
    z1 = z[lk > -70]
    rel = -0.691 + 10 * np.log10(np.sum(np.mean(z1, axis=0))) - 10
    z2 = z[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(np.sum(np.mean(z2, axis=0))))


def test_one_voice_one_rate_for_every_clip() -> None:
    meta = TIMELINES["_meta"]
    assert meta["voice"] == "en-US-AndrewMultilingualNeural"
    assert re.fullmatch(r"[+-]\d+%", meta["rate"])
    used = set(re.findall(r'assets/onboarding/(\w+)_mixed\.mp3', APP_JS))
    used |= {f"scene_{i}" for i in range(1, 6)} | {"scene_2_mac"}
    assert used <= set(CLIPS), used - set(CLIPS)


@pytest.mark.parametrize("clip", sorted(CLIPS))
def test_clip_loudness_is_uniform(clip: str) -> None:
    x, sr = _decode(ASSETS / f"{clip}_mixed.mp3")
    lufs = _integrated_lufs(x, sr)
    assert abs(lufs - TIMELINES["_meta"]["target_lufs"]) <= 0.5, f"{clip}: {lufs:.2f} LUFS"
    assert np.max(np.abs(x)) < 0.95, f"{clip}: clipping risk"


def _syllables(word: str) -> int:
    w = word.lower()
    if w.isdigit():
        return len(w)
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def test_clip_pace_is_consistent() -> None:
    """One fixed TTS rate: the syllable rate over each clip's spoken span stays within
    15% of the median (words per minute swings more because word length varies)."""
    rate = {}
    for name, clip in CLIPS.items():
        words = [w for l in clip["lines"] for w in re.findall(r"[A-Za-z0-9']+", l["text"])]
        span = clip["speech_end"] - TIMELINES["_meta"]["lead_in_s"]
        rate[name] = sum(_syllables(w) for w in words) / span
    med = float(np.median(list(rate.values())))
    bad = {k: round(v, 2) for k, v in rate.items() if abs(v - med) / med > 0.15}
    assert not bad, f"median {med:.2f} syllables/s, outliers {bad}"
