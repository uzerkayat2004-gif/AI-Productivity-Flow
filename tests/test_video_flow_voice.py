"""Video Flow narration voice: shared catalog selection, independent setting.

Edge TTS is the default; cloud voices reuse the app's TTS engine through the
registered "voiceflow" Narova provider. Audio Flow's own voice selection
(exec_audio_policy_model) must never be read or written by Video Flow.
"""

from __future__ import annotations

import json
import wave
import struct
import math
from pathlib import Path
from typing import Any

from voice_flow.video_flow_engine import voice_provider_worker
from voice_flow.video_flow_engine.bridge import (
    DEFAULT_VOICE,
    build_directed_production,
    build_narova_production,
)
from voice_flow.video_flow_engine.narova_runner import _register_voiceflow_provider


def _storyboard() -> dict[str, Any]:
    return {
        "topic": "Why is the sky blue?",
        "sections": [
            {"id": "one", "title": "One", "lecture_lines": ["Line."], "animations": []},
            {"id": "two", "title": "Two", "lecture_lines": ["Line two."], "animations": []},
        ],
    }


def _direction() -> dict[str, Any]:
    return {
        "brief": {},
        "scenes": [
            {"index": 1, "treatment": "hero-title", "title_label": "T", "labels": ["A"]},
            {"index": 2, "treatment": "recap-mosaic", "title_label": "T", "labels": ["B"]},
        ],
    }


def test_default_voice_is_edge_ava() -> None:
    assert DEFAULT_VOICE == "edge/en-US-AvaNeural"
    production = build_narova_production(_storyboard())
    narrator = production["voices"]["narrator"]
    assert narrator["backend"] == "voiceflow"
    assert narrator["speaker"] == DEFAULT_VOICE


def test_custom_voice_flows_through_both_builders() -> None:
    voice = "elevenlabs/21m00Tcm4TlvDq8ikWAM"
    legacy = build_narova_production(_storyboard(), voice=voice)
    directed = build_directed_production(_storyboard(), _direction(), voice=voice)
    for production in (legacy, directed):
        assert production["voices"]["narrator"]["backend"] == "voiceflow"
        assert production["voices"]["narrator"]["speaker"] == voice


def test_blank_voice_falls_back_to_default() -> None:
    production = build_narova_production(_storyboard(), voice="   ")
    assert production["voices"]["narrator"]["speaker"] == DEFAULT_VOICE


def _wav_bytes(seconds: float = 0.05) -> bytes:
    frames = int(24000 * seconds)
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"".join(struct.pack("<h", int(1000 * math.sin(i / 20))) for i in range(frames)))
    return buffer.getvalue()


def test_worker_synthesizes_and_normalizes_to_wav(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(voice_provider_worker, "_edge_bytes", lambda text, voice: _wav_bytes())
    out = tmp_path / "narration" / "01.wav"
    voice_provider_worker.synthesize_to_wav("Hello", "edge/en-US-AvaNeural", out)
    assert out.is_file()
    with wave.open(str(out), "rb") as handle:
        assert handle.getframerate() == 24000
        assert handle.getnchannels() == 1
        assert handle.getnframes() > 0


def test_worker_synthesize_error_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(voice_provider_worker, "_edge_bytes", lambda text, voice: b"")
    response = voice_provider_worker._handle({
        "id": "r1",
        "operation": "synthesize",
        "text": "Hello",
        "speaker": "edge/en-US-AvaNeural",
        "output": str(tmp_path / "out.wav"),
    })
    assert response["id"] == "r1"
    assert response["ok"] is False
    assert "no audio" in response["error"]


def test_worker_handshake_protocol() -> None:
    response = voice_provider_worker._handle({"operation": "hello"})
    assert response == {
        "ok": True,
        "protocol": "narova-tts-provider/v1",
        "provider": "voiceflow",
        "providerVersion": "1.0.0",
    }


def test_provider_manifest_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NAROVA_HOME", str(tmp_path))
    _register_voiceflow_provider()
    manifest_path = tmp_path / "providers" / "voiceflow.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["protocol"] == "narova-tts-provider/v1"
    assert manifest["name"] == "voiceflow"
    assert manifest["capabilities"]["synthesis"] is True
    first_command = manifest["command"]
    _register_voiceflow_provider()
    again = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert again["command"] == first_command
