"""Run the installed Whisper fallback on a speech fixture plus noise and silence.

Invoked with the private runtime's python.exe. Prints one JSON object.
"""

from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import numpy as np


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"expected 16-bit WAV, got sample width {sample_width}")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(audio), sample_rate


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    length = int(round(audio.size * target_rate / source_rate))
    if length <= 1:
        return np.zeros(0, dtype=np.float32)
    source_x = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    target_x = np.linspace(0.0, 1.0, length, endpoint=False)
    return np.interp(target_x, source_x, audio).astype(np.float32)


def _mix(speech: np.ndarray, sample_rate: int) -> np.ndarray:
    rng = np.random.default_rng(17)
    lead = np.zeros(int(0.25 * sample_rate), dtype=np.float32)
    gap = np.zeros(int(0.35 * sample_rate), dtype=np.float32)
    noise = (rng.random(int(1.6 * sample_rate)).astype(np.float32) * 2.0 - 1.0) * 0.015
    tail = np.zeros(int(2.2 * sample_rate), dtype=np.float32)
    return np.concatenate([lead, speech, gap, noise, tail]).astype(np.float32)


def main() -> int:
    wav_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    started = time.perf_counter()
    payload: dict = {"wav": str(wav_path)}
    try:
        from voice_flow.config import config
        from voice_flow.stt_guard import repeated_sentence
        from voice_flow.transcriber import Transcriber

        speech, source_rate = _load_wav(wav_path)
        speech = _resample(speech, source_rate, config.sample_rate)
        peak = float(np.max(np.abs(speech))) if speech.size else 0.0
        if peak > 0:
            speech = speech * min(0.9 / peak, 4.0)
        audio = _mix(speech, config.sample_rate)
        payload["fixture_seconds"] = round(len(audio) / config.sample_rate, 3)
        payload["speech_peak"] = round(peak, 4)

        engine = Transcriber()
        load_started = time.perf_counter()
        engine._load_model_bg("base.en")
        deadline = time.perf_counter() + 180
        while time.perf_counter() < deadline:
            if getattr(engine, "model", None) is not None:
                break
            time.sleep(0.25)
        payload["load_seconds"] = round(time.perf_counter() - load_started, 3)
        payload["model_loaded"] = getattr(engine, "model", None) is not None
        if not payload["model_loaded"]:
            payload["error"] = "Whisper model was not ready after 180s"
            payload["pass"] = False
        else:
            decode_started = time.perf_counter()
            text = engine.transcribe(audio, model_ref="local/faster-whisper-base.en")
            payload["decode_seconds"] = round(time.perf_counter() - decode_started, 3)
            text = str(text or "").strip()
            payload["text"] = text
            repeated = repeated_sentence(text)
            payload["repeated_sentence"] = list(repeated) if repeated else None
            lowered = text.lower()
            known = (
                "i'm not sure if you have any questions",
                "thank you for watching",
                "thanks for watching",
            )
            payload["known_hallucination_hits"] = [phrase for phrase in known if phrase in lowered]
            payload["pass"] = bool(text) and repeated is None and not payload["known_hallucination_hits"]
            if not text:
                payload["error"] = "transcriber returned empty text"
            elif repeated is not None:
                payload["error"] = f"repeated sentence x{repeated[1]}: {repeated[0]}"
            elif payload["known_hallucination_hits"]:
                payload["error"] = "known Whisper hallucination phrase in the transcript"
    except Exception as exc:
        payload["pass"] = False
        payload["error"] = f"{type(exc).__name__}: {exc}"
    payload["total_seconds"] = round(time.perf_counter() - started, 3)
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
