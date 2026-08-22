"""Narova external TTS provider worker for Video Flow narration.

Implements the ``narova-tts-provider/v1`` JSONL protocol so Narova's synth
stage can narrate through the app's own TTS stack instead of Piper:

- ``edge`` voices synthesize directly via ``edge_tts`` (free, default); and
- cloud voices route through the shared ``voice_flow.tts_engine`` so keys and
  connections stay exactly where Audio Flow manages them.

Every provider returns raw audio bytes; this worker normalizes them to a
16-bit PCM 24 kHz mono WAV via FFmpeg, which the Narova pipeline requires.

Run standalone (spawned by Narova, never imported by the app):

    python voice_provider_worker.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

PROVIDER_NAME = "voiceflow"
PROVIDER_VERSION = "1.0.0"
PROTOCOL = "narova-tts-provider/v1"
DEFAULT_VOICE = "edge/en-US-AvaNeural"

_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def synthesize_to_wav(text: str, full_voice_id: str, output: Path) -> None:
    """Synthesize ``text`` with ``full_voice_id`` and write a PCM WAV."""
    provider, _, model_id = str(full_voice_id or DEFAULT_VOICE).partition("/")
    provider = (provider or "edge").lower()
    if not model_id:
        model_id = str(full_voice_id or DEFAULT_VOICE)

    if provider == "edge":
        data = _edge_bytes(text, model_id)
    else:
        data = _engine_bytes(text, f"{provider}/{model_id}")
    if not data:
        raise RuntimeError(f"TTS provider {provider!r} returned no audio")

    ffmpeg = None
    try:
        from voice_flow import runtime_env

        bundled = runtime_env.ffmpeg_executable()
        if bundled is not None:
            ffmpeg = str(bundled)
    except Exception:
        pass
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to normalize narration audio")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.audio"
        raw.write_bytes(data)
        wav = Path(tmp) / "raw.wav"
        result = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(raw),
             "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not wav.is_file():
            raise RuntimeError(f"FFmpeg audio conversion failed: {result.stderr[-300:]}")
        _validate_wav(wav)
        # copyfile (not shutil.move): the temp dir and the Narova audio dir can
        # live on different volumes, where move's rename step fails on Windows.
        shutil.copyfile(str(wav), str(output))


def _edge_bytes(text: str, voice: str) -> bytes | None:
    """Direct Edge TTS at neutral rate (Narova owns timing/tempo)."""
    try:
        import edge_tts
    except ImportError:
        return _engine_bytes(text, f"edge/{voice}")

    from voice_flow.tts_engine import resolve_edge_voice

    voice_id = resolve_edge_voice(voice)

    async def _run() -> bytes:
        communicate = edge_tts.Communicate(text, voice_id)
        data = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data.extend(chunk.get("data", b""))
        return bytes(data)

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run())
    finally:
        loop.close()


def _engine_bytes(text: str, full_model_id: str) -> bytes | None:
    """Cloud voices reuse the app's shared TTS engine (keys from Audio Flow)."""
    try:
        from voice_flow import tts_engine
        return tts_engine._synthesize(text, full_model_id)
    except Exception as exc:  # surfaced to Narova as a provider error
        raise RuntimeError(f"TTS synthesis via {full_model_id!r} failed: {exc}") from exc


def _validate_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() < 1:
            raise ValueError("empty WAV stream")


def _handle(request: dict) -> dict:
    response_id = request.get("id")
    operation = str(request.get("operation") or "")
    if operation == "hello":
        return {
            "ok": True,
            "protocol": PROTOCOL,
            "provider": PROVIDER_NAME,
            "providerVersion": PROVIDER_VERSION,
        }
    if operation == "synthesize":
        try:
            text = str(request.get("text") or "")
            speaker = str(request.get("speaker") or DEFAULT_VOICE)
            output = Path(str(request.get("output") or ""))
            if not text:
                raise ValueError("synthesize request has no text")
            if not output.is_absolute():
                raise ValueError("synthesize output must be an absolute path")
            output.parent.mkdir(parents=True, exist_ok=True)
            synthesize_to_wav(text, speaker, output)
            return {"id": response_id, "ok": True, "output": str(output)}
        except Exception as exc:
            return {"id": response_id, "ok": False, "error": str(exc)[:500]}
    return {"id": response_id, "ok": False, "error": f"unsupported operation: {operation!r}"}


def main() -> None:
    # Provider diagnostics go to stderr; stdout is the JSONL protocol only.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"ok": False, "error": "invalid JSON"}) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(request, dict):
            sys.stdout.write(json.dumps({"ok": False, "error": "request must be an object"}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(_handle(request), separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
