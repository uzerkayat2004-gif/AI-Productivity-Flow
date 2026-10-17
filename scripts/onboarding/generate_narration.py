"""Regenerate every onboarding voiceover from scripts/onboarding/narration_script.py.

Pipeline (one voice, one rate, one loudness for every clip):
  1. edge-tts speaks all caption lines of a clip as one take and reports word timings.
  2. The voice is gain-normalised to TARGET_LUFS (ITU-R BS.1770, pyloudnorm).
  3. <clip>_mixed.mp3 = LEAD_IN_S silence + voice + TAIL_S, over bgm_calmant.mp3 at a
     FIXED gain (BGM_BELOW_VOICE_DB under the voice target, from the same bgm offset 0,
     0.4 s fade-in, 0.6 s fade-out), then a tiny final trim back to TARGET_LUFS.
     <clip>_raw.mp3 is the voice alone (same lead-in), also at TARGET_LUFS.
  4. Caption lines and highlight beats are written from the word timings into
     assets/onboarding/narration_timelines.json and the generated block in app.js,
     so subtitles and visual beats always match the audio.

Usage:  python scripts/onboarding/generate_narration.py [clip ...]
Needs:  edge-tts, numpy, pyloudnorm, ffmpeg on PATH (developer tools, not app runtime).
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln

sys.path.insert(0, str(Path(__file__).parent))
import narration_script as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src" / "voice_flow" / "gui" / "assets" / "onboarding"
APP_JS = ROOT / "src" / "voice_flow" / "gui" / "app.js"
SR = 44100
WORK = Path("/tmp/apf_narration")


async def _speak(text: str, out_mp3: Path) -> list[dict]:
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, S.VOICE, rate=S.RATE, boundary="WordBoundary")
    with open(out_mp3, "wb") as fh:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"start": chunk["offset"] / 1e7, "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                              "text": chunk["text"]})
    return words


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)


def _encode_once(sig: np.ndarray, path: Path) -> None:
    pcm = np.clip(sig, -1.0, 1.0).astype(np.float32).tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", str(SR), str(path)], input=pcm, check=True)


def measured_lufs(path: Path) -> float:
    """Integrated loudness of the encoded file, measured by ffmpeg's EBU R128 filter."""
    err = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def _encode(sig: np.ndarray, path: Path) -> None:
    """Encode, then correct the gain so the MP3 itself measures TARGET_LUFS."""
    _encode_once(sig, path)
    for _ in range(2):
        delta = S.TARGET_LUFS - measured_lufs(path)
        if abs(delta) < 0.05:
            return
        sig = sig * (10 ** (delta / 20))
        _encode_once(sig, path)


_METER = pyln.Meter(SR)


def lufs(sig: np.ndarray) -> float:
    return float(_METER.integrated_loudness(sig))


def _gain(sig, target):
    return sig * (10 ** ((target - lufs(sig)) / 20))


def _norm_word(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _line_spans(lines: list[str], words: list[dict]) -> list[tuple[int, int]]:
    """Map each caption line to its [first, last] word index in the boundary list."""
    spans, wi = [], 0
    for line in lines:
        tokens = [t for t in (_norm_word(x) for x in re.split(r"[\s\-\u2014]+", line)) if t]
        first = wi
        consumed = 0
        joined = ""
        target = "".join(tokens)
        while wi < len(words) and len(joined) < len(target):
            joined += _norm_word(words[wi]["text"])
            wi += 1
            consumed += 1
        if joined != target:
            raise RuntimeError(f"word alignment failed for line {line!r}: got {joined!r} want {target!r}")
        spans.append((first, wi - 1))
    return spans


_BGM = None
_BGM_GAIN = None


def _bgm(n: int) -> np.ndarray:
    global _BGM, _BGM_GAIN
    if _BGM is None:
        _BGM = _decode(ASSETS / "bgm_calmant.mp3")
        # One fixed gain for every clip, computed from the whole music track.
        _BGM_GAIN = 10 ** (((S.TARGET_LUFS - S.BGM_BELOW_VOICE_DB) - lufs(_BGM)) / 20)
    seg = _BGM[:n].copy() * _BGM_GAIN
    fi, fo = int(0.4 * SR), int(0.6 * SR)
    seg[:fi] *= np.linspace(0, 1, fi)[:, None]
    seg[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return seg


def build(clip: str) -> dict:
    spec = S.CLIPS[clip]
    lines = spec["lines"]
    WORK.mkdir(parents=True, exist_ok=True)
    tts_mp3 = WORK / f"{clip}_tts.mp3"
    words = asyncio.run(_speak(" ".join(lines), tts_mp3))
    voice = _decode(tts_mp3)
    # Trim edge-tts leading silence to the first word, keep a uniform LEAD_IN_S.
    first = max(0.0, words[0]["start"] - 0.05)
    cut = int(first * SR)
    voice = voice[cut:]
    shift = S.LEAD_IN_S - first / 1.0
    last_end = words[-1]["end"] - first
    voice = voice[: int((last_end + 0.25) * SR)]
    voice = _gain(voice, S.TARGET_LUFS)
    lead = np.zeros((int(S.LEAD_IN_S * SR), 2))
    tail = np.zeros((int(S.TAIL_S * SR), 2))
    raw = np.concatenate([lead, voice])
    v_full = np.concatenate([lead, voice, tail])
    mix = v_full + _bgm(len(v_full))
    trim_db = S.TARGET_LUFS - lufs(mix)
    mix *= 10 ** (trim_db / 20)
    peak = float(np.max(np.abs(mix)))
    if peak > 0.89:  # keep >= 1 dB headroom
        raise RuntimeError(f"{clip}: peak {peak:.2f} too hot")
    _encode(mix, ASSETS / f"{clip}_mixed.mp3")
    _encode(_gain(raw, S.TARGET_LUFS), ASSETS / f"{clip}_raw.mp3")

    t = lambda s: round(s + shift, 2)  # noqa: E731  boundary time -> clip time
    spans = _line_spans(lines, words)
    timeline = []
    for i, (a, b) in enumerate(spans):
        start = t(words[a]["start"]) - (0.15 if i else 0.0)
        timeline.append({"start": round(max(0.0, start), 2), "end": t(words[b]["end"]), "text": lines[i]})
    # Captions hold until the next line starts (no blank gaps), last one to the end.
    for i in range(len(timeline) - 1):
        timeline[i]["end"] = timeline[i + 1]["start"]
    duration = round(len(mix) / SR, 3)
    timeline[-1]["end"] = round(duration, 2)
    beats = {}
    for name, (word, line_idx) in (spec.get("beats") or {}).items():
        a, b = spans[line_idx]
        hit = next(i for i in range(a, b + 1) if _norm_word(words[i]["text"]).startswith(word))
        beats[name] = t(words[hit]["start"])
    return {
        "duration": duration,
        "speech_end": t(words[-1]["end"]),
        "words": len(words),
        "lines": timeline,
        "beats": beats,
        "bgm_trim_db": round(trim_db, 3),
    }


def write_outputs(results: dict) -> None:
    path = ASSETS / "narration_timelines.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(results)
    data = {k: data[k] for k in S.CLIPS if k in data}
    meta = {"voice": S.VOICE, "rate": S.RATE, "target_lufs": S.TARGET_LUFS,
            "bgm_below_voice_db": S.BGM_BELOW_VOICE_DB, "lead_in_s": S.LEAD_IN_S}
    path.write_text(json.dumps({"_meta": meta, **data}, indent=2) + "\n")
    # Legacy per-guide timeline files keep their shapes (tests + docs read them).
    af = {str(i): data[f"af_guide_step{i}"]["lines"] for i in range(1, 5) if f"af_guide_step{i}" in data}
    vf = {f"step{i}": data[f"vf_guide_step{i}"]["lines"] for i in range(1, 5) if f"vf_guide_step{i}" in data}
    vo = {str(i): data[f"voiceflow_guide_step{i}"]["lines"] for i in range(1, 5) if f"voiceflow_guide_step{i}" in data}
    if "voiceflow_guide_step4_mac" in data:
        vo["4_mac"] = data["voiceflow_guide_step4_mac"]["lines"]
    for name, obj in (("af_guide_timelines.json", af), ("vf_guide_timelines.json", vf), ("voiceflow_guide_timelines.json", vo)):
        (ASSETS / name).write_text(json.dumps(obj, indent=2) + "\n")
    # Generated block in app.js: captions, beats and durations the GUI syncs to.
    compact = {k: {"duration": v["duration"], "speechEnd": v["speech_end"], "lines": v["lines"], "beats": v["beats"]}
               for k, v in data.items()}
    block = ("// BEGIN GENERATED NARRATION TIMELINES (scripts/onboarding/generate_narration.py; do not edit by hand)\n"
             f"const ONBOARDING_NARRATION_TIMELINES = {json.dumps(compact, indent=2)};\n"
             "// END GENERATED NARRATION TIMELINES")
    js = APP_JS.read_text(encoding="utf-8")
    pat = re.compile(r"// BEGIN GENERATED NARRATION TIMELINES.*?// END GENERATED NARRATION TIMELINES", re.S)
    if not pat.search(js):
        raise SystemExit("app.js has no generated narration block")
    APP_JS.write_text(pat.sub(lambda _m: block, js), encoding="utf-8")


def main(argv: list[str]) -> None:
    clips = argv or list(S.CLIPS)
    results = {}
    for clip in clips:
        r = build(clip)
        results[clip] = r
        print(f"{clip:28s} {r['duration']:6.2f}s words={r['words']:3d} speech_end={r['speech_end']:.2f} trim={r['bgm_trim_db']:+.3f} dB")
    write_outputs(results)


if __name__ == "__main__":
    main(sys.argv[1:])
