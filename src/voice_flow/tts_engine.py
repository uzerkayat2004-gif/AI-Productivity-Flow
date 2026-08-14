from __future__ import annotations
import re

_VOICE_MAPPING = {
    "edge ava": "en-US-AvaNeural",
    "ava": "en-US-AvaNeural",
    "edge andrew": "en-US-AndrewNeural",
    "andrew": "en-US-AndrewNeural",
    "edge emma": "en-US-EmmaNeural",
    "emma": "en-US-EmmaNeural",
    "edge brian": "en-US-BrianNeural",
    "brian": "en-US-BrianNeural",
    "edge ana": "en-US-AnaNeural",
    "ana": "en-US-AnaNeural",
    "edge guy": "en-US-GuyNeural",
    "guy": "en-US-GuyNeural",
    "edge aria": "en-US-AriaNeural",
    "aria": "en-US-AriaNeural",
    "edge jenny": "en-US-JennyNeural",
    "jenny": "en-US-JennyNeural",
    "edge steffan": "en-US-SteffanNeural",
    "steffan": "en-US-SteffanNeural",
    "edge christopher": "en-US-ChristopherNeural",
    "christopher": "en-US-ChristopherNeural",
    "edge eric": "en-US-EricNeural",
    "eric": "en-US-EricNeural",
    "edge roger": "en-US-RogerNeural",
    "roger": "en-US-RogerNeural",
}


def resolve_edge_voice(voice_str: str) -> str:
    if not voice_str:
        return "en-US-AvaNeural"
    clean = voice_str.replace("edge/", "").strip()
    if re.match(r"^[a-z]{2}-[A-Z]{2}-\w+Neural$", clean):
        return clean
    clean_lower = clean.lower()
    for key, valid_id in _VOICE_MAPPING.items():
        if key in clean_lower:
            return valid_id
    return "en-US-AvaNeural"


"""Unified Text-To-Speech (TTS) Engine for Audio Flow.

Supports:
- Microsoft Edge Neural TTS (100% Free, zero API key required)
- ElevenLabs Voice API (Multilingual v2, Turbo)
- Deepgram Aura Speech API (Asteria, Luna, Zeus)
- OpenAI TTS API (Alloy, Echo, Nova, Fable)
- Windows Native SAPI5 Fallback (100% Offline)
"""

import asyncio
import io
import logging
import os
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.parse
import json
import base64
from typing import Callable, Any

from voice_flow.config import config
from voice_flow.storage import storage
from voice_flow.structured_reader import format_document_structure_for_speech

log = logging.getLogger(__name__)


class TTSEngine:
    """Thread-safe Text-to-Speech synthesis and playback engine for Audio Flow."""

    @staticmethod
    def _preprocess_text(raw: str) -> str:
        """Clean up selected text into smooth prose before structured parsing."""
        if not raw or not raw.strip():
            return raw

        text = raw.strip()
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"-\n\s*", "", text)
        for old, new in [("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                         ("–", "-"), ("—", ", "), ("…", "..."), (" ", " ")]:
            text = text.replace(old, new)
        text = re.sub(r"\[[\d,\s\-]+\]", "", text)
        return text.strip()

    def __init__(self) -> None:
        self._is_speaking = False
        self._is_paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._speech_thread: threading.Thread | None = None
        self._player_proc: Any = None
        self._sentences: list[str] = []
        self._current_sentence_idx = 0

    def is_speaking(self) -> bool:
        return self._is_speaking

    def is_paused(self) -> bool:
        return self._is_paused

    def pause(self) -> None:
        """Pause speech audio playback."""
        self._is_paused = True
        self._pause_event.set()
        if self._player_proc is not None:
            try:
                self._player_proc.terminate()
            except Exception:
                pass

    def resume(self) -> None:
        """Resume speech audio playback."""
        self._is_paused = False
        self._pause_event.clear()

    def stop(self) -> None:
        """Immediately stop speech audio playback."""
        self._stop_event.set()
        self._pause_event.clear()
        self._is_speaking = False
        self._is_paused = False
        if self._player_proc is not None:
            try:
                self._player_proc.terminate()
            except Exception:
                pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _get_fallback_edge_voice(self) -> str:
        active_model = storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")
        if active_model.startswith("edge/"):
            return resolve_edge_voice(active_model.split("/", 1)[1])
        return "en-US-AvaNeural"

    def speak(
        self,
        text: str,
        model_override: str | None = None,
        on_start: Callable[[], None] | None = None,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Synthesize and play entire formatted text as a single smooth, continuous human reading."""
        if not text or not text.strip():
            if on_error:
                on_error("No text selected to read.")
            return

        self.stop()
        self._stop_event.clear()
        self._pause_event.clear()
        self._is_speaking = True
        self._is_paused = False

        def _worker():
            try:
                if on_start:
                    on_start()

                preprocessed = self._preprocess_text(text)
                clean_text = format_document_structure_for_speech(preprocessed)

                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if s.strip()]
                if not sentences:
                    sentences = [clean_text]

                self._sentences = sentences
                self._current_sentence_idx = 0
                active_model = model_override or storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")

                log.info("Audio Flow: Synthesizing continuous text (%d chars, %d sentences)", len(clean_text), len(sentences))

                audio_bytes = self._synthesize(clean_text, active_model)

                if self._stop_event.is_set():
                    return

                if audio_bytes:
                    self._play_audio(audio_bytes)
                else:
                    log.warning("Audio Flow synthesis returned empty audio.")

            except Exception as e:
                log.error("Audio Flow TTS error: %s", e)
                if on_error:
                    on_error(str(e))
            finally:
                self._is_speaking = False
                self._is_paused = False
                if on_done:
                    on_done()

        self._speech_thread = threading.Thread(target=_worker, daemon=True)
        self._speech_thread.start()

    @staticmethod
    def _detect_voice_for_text(text: str, default_voice: str) -> str:
        """Auto-detect voice by dominant Unicode script."""
        devanagari = 0
        arabic = 0
        cjk = 0
        hangul = 0
        latin = 0
        total = 0

        for ch in text:
            cp = ord(ch)
            if cp < 128 and ch.isalpha():
                latin += 1
                total += 1
            elif 0x0900 <= cp <= 0x097F:
                devanagari += 1
                total += 1
            elif 0x0600 <= cp <= 0x06FF:
                arabic += 1
                total += 1
            elif 0x4E00 <= cp <= 0x9FFF:
                cjk += 1
                total += 1
            elif 0xAC00 <= cp <= 0xD7AF:
                hangul += 1
                total += 1

        if total == 0:
            return default_voice

        threshold = total * 0.3
        if devanagari > threshold:
            return "hi-IN-SwaraNeural"
        if arabic > threshold:
            return "ar-SA-ZariyahNeural"
        if cjk > threshold:
            return "zh-CN-XiaoxiaoNeural"
        if hangul > threshold:
            return "ko-KR-SunHiNeural"

        return default_voice

    def _synthesize(self, text: str, full_model_id: str) -> bytes | None:
        parts = full_model_id.split("/", 1)
        provider = parts[0].lower() if len(parts) > 1 else "edge"
        model_id = parts[1] if len(parts) > 1 else full_model_id

        if provider == "edge":
            resolved_voice = resolve_edge_voice(model_id)
            voice = self._detect_voice_for_text(text, resolved_voice)
            return self._synthesize_edge_tts(text, voice)
        elif provider == "elevenlabs":
            return self._synthesize_elevenlabs(text, model_id)
        elif provider == "deepgram":
            return self._synthesize_deepgram(text, model_id)
        elif provider == "openai":
            return self._synthesize_openai(text, model_id)
        elif provider == "google":
            return self._synthesize_google(text, model_id)
        elif provider == "gemini":
            return self._synthesize_gemini(text, model_id)
        elif provider == "nvidia":
            return self._synthesize_nvidia(text, model_id)
        else:
            log.warning("Audio Flow: Unknown or unconfigured TTS provider '%s', falling back to Edge TTS", provider)
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _get_speed_rate_str(self) -> str:
        speed = float(storage.get_setting("audio_flow_speed", 1.0))
        pct = int(round((speed - 1.0) * 100))
        return f"{'+' if pct >= 0 else ''}{pct}%"

    def _synthesize_edge_tts(self, text: str, voice_name: str) -> bytes | None:
        try:
            import edge_tts

            rate_str = self._get_speed_rate_str()
            pitch_str = "+0Hz"

            async def _main():
                valid_v = resolve_edge_voice(voice_name)
                communicate = edge_tts.Communicate(
                    text, valid_v, rate=rate_str, pitch=pitch_str
                )
                data = bytearray()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        data.extend(chunk["data"])
                return bytes(data)

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(_main())
            finally:
                loop.close()
        except Exception as e:
            log.warning("Edge-TTS synthesis error: %s", e)
            return None

    def _get_active_keys_for_provider(self, provider: str) -> list[dict[str, Any]]:
        all_keys = storage.get_audio_provider_connections(provider)
        active = [
            k for k in all_keys
            if k.get("is_active", 1) and k.get("is_valid", 1) and k.get("api_key", "").strip()
        ]
        if not active:
            # Fall back to any active key if is_valid flag is not yet set
            active = [
                k for k in all_keys
                if k.get("is_active", 1) and k.get("api_key", "").strip()
            ]
        return active

    def _synthesize_elevenlabs(self, text: str, voice_id: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("elevenlabs")
        if not active_keys:
            log.warning("ElevenLabs TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        payload = json.dumps({
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }).encode("utf-8")

        for k in active_keys:
            api_key = k["api_key"].strip()
            cid = k.get("id")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "xi-api-key": api_key,
                    "User-Agent": "VoiceFlow/1.0"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    log.info("ElevenLabs TTS: synthesis succeeded (%d bytes)", len(data))
                    if cid:
                        storage.update_audio_provider_connection_validation(cid, True, None)
                    return data
            except urllib.error.HTTPError as e:
                body = e.read(500).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                log.error("ElevenLabs TTS HTTP %s error: %s — %s", e.code, e.reason, body)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("ElevenLabs TTS error: %s", e)

        log.warning("ElevenLabs TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _synthesize_deepgram(self, text: str, model_name: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("deepgram")
        if not active_keys:
            log.warning("Deepgram TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        url = f"https://api.deepgram.com/v1/speak?model={model_name}"
        payload = json.dumps({"text": text}).encode("utf-8")

        for k in active_keys:
            api_key = k["api_key"].strip()
            cid = k.get("id")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Token {api_key}",
                    "User-Agent": "VoiceFlow/1.0"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    log.info("Deepgram TTS: synthesis succeeded (%d bytes)", len(data))
                    if cid:
                        storage.update_audio_provider_connection_validation(cid, True, None)
                    return data
            except urllib.error.HTTPError as e:
                body = e.read(500).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                log.error("Deepgram TTS HTTP %s error: %s — %s", e.code, e.reason, body)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("Deepgram TTS error: %s", e)

        log.warning("Deepgram TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _synthesize_openai(self, text: str, model_voice_spec: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("openai")
        if not active_keys:
            log.warning("OpenAI TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        spec_parts = model_voice_spec.split(":", 1)
        model = spec_parts[0] if spec_parts[0] else "tts-1"
        voice = spec_parts[1] if len(spec_parts) > 1 else "alloy"
        speed = float(storage.get_setting("audio_flow_speed", 1.0))

        url = "https://api.openai.com/v1/audio/speech"
        payload = json.dumps({
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed
        }).encode("utf-8")

        for k in active_keys:
            api_key = k["api_key"].strip()
            cid = k.get("id")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "VoiceFlow/1.0"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                    log.info("OpenAI TTS: synthesis succeeded (%d bytes)", len(data))
                    if cid:
                        storage.update_audio_provider_connection_validation(cid, True, None)
                    return data
            except urllib.error.HTTPError as e:
                body = e.read(500).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                log.error("OpenAI TTS HTTP %s error: %s — %s", e.code, e.reason, body)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("OpenAI TTS error: %s", e)

        log.warning("OpenAI TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _synthesize_google(self, text: str, model_id: str) -> bytes | None:
        """Synthesize speech using Google Cloud TTS REST API with API key."""
        active_keys = self._get_active_keys_for_provider("google")
        if not active_keys:
            log.warning("Google Cloud TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        speed = float(storage.get_setting("audio_flow_speed", 1.0))
        speaking_rate = speed
        pitch = 0.0

        for k in active_keys:
            api_key = k["api_key"].strip()
            cid = k.get("id")
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
            payload = json.dumps({
                "input": {"text": text},
                "voice": {
                    "languageCode": "en-US",
                    "name": model_id,
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": speaking_rate,
                    "pitch": pitch,
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "VoiceFlow/1.0"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))
                    audio_content = response_data.get("audioContent")
                    if audio_content:
                        log.info("Google Cloud TTS: synthesis succeeded (model=%s)", model_id)
                        if cid:
                            storage.update_audio_provider_connection_validation(cid, True, None)
                        return base64.b64decode(audio_content)
                    log.warning("Google Cloud TTS: response had no audioContent. Response: %s", str(response_data)[:300])
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read(500).decode("utf-8", errors="replace")
                except Exception:
                    pass
                log.error("Google Cloud TTS HTTP %s error: %s — %s", e.code, e.reason, body)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("Google Cloud TTS synthesis error: %s", e)

        log.warning("Google Cloud TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _synthesize_gemini(self, text: str, model_voice_spec: str) -> bytes | None:
        """Synthesize speech using Gemini TTS (generativelanguage.googleapis.com)."""
        active_keys = self._get_active_keys_for_provider("gemini")
        if not active_keys:
            log.warning("Gemini TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        # model_voice_spec format: "gemini-2.5-flash-preview-tts:Kore"
        spec_parts = model_voice_spec.split(":", 1)
        model = spec_parts[0].strip() if spec_parts[0].strip() else "gemini-2.5-flash-preview-tts"
        voice = spec_parts[1].strip() if len(spec_parts) > 1 else "Kore"

        for k in active_keys:
            api_key = k["api_key"].strip()
            cid = k.get("id")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = json.dumps({
                "contents": [{
                    "parts": [{"text": text}]
                }],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": voice
                            }
                        }
                    }
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "VoiceFlow/1.0"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))
                    candidates = response_data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        for part in parts:
                            inline_data = part.get("inlineData", {})
                            mime_type = inline_data.get("mimeType", "")
                            if mime_type.startswith("audio/"):
                                audio_b64 = inline_data.get("data")
                                if audio_b64:
                                    raw_bytes = base64.b64decode(audio_b64)
                                    log.info("Gemini TTS: synthesis succeeded (model=%s, voice=%s, mime=%s, bytes=%d)", model, voice, mime_type, len(raw_bytes))
                                    if cid:
                                        storage.update_audio_provider_connection_validation(cid, True, None)
                                    if "L16" in mime_type or "pcm" in mime_type.lower():
                                        import wave
                                        rate = 24000
                                        for seg in mime_type.split(";"):
                                            seg = seg.strip()
                                            if seg.startswith("rate="):
                                                try:
                                                    rate = int(seg[5:])
                                                except ValueError:
                                                    pass
                                        buf = io.BytesIO()
                                        with wave.open(buf, "wb") as wf:
                                            wf.setnchannels(1)   # mono
                                            wf.setsampwidth(2)   # 16-bit
                                            wf.setframerate(rate)
                                            wf.writeframes(raw_bytes)
                                        return buf.getvalue()
                                    return raw_bytes
            except urllib.error.HTTPError as e:
                log.error("Gemini TTS HTTP %s error: %s", e.code, e.reason)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("Gemini TTS error: %s", e)

        log.warning("Gemini TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _synthesize_nvidia(self, text: str, model_name: str) -> bytes | None:
        """Synthesize speech using NVIDIA NIM / Riva REST API."""
        all_keys = storage.get_audio_provider_connections("nvidia")
        api_key = None
        for k in all_keys:
            if k.get("api_key", "").strip():
                api_key = k["api_key"].strip()
                break
        if not api_key:
            log.warning("NVIDIA TTS: No API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

        model_id = "nvidia/chatterbox-multilingual-tts" if "chatterbox" in model_name.lower() else "nvidia/riva-tts"
        url = "https://ai.api.nvidia.com/v1/audio/speech" if "chatterbox" in model_name.lower() else "https://integrate.api.nvidia.com/v1/audio/speech"
        payload = json.dumps({
            "model": model_id,
            "input": text,
            "voice": model_name
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "VoiceFlow/1.0"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                log.info("NVIDIA TTS: synthesis succeeded (%d bytes)", len(data))
                return data
        except urllib.error.HTTPError as e:
            body = e.read(500).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            log.error("NVIDIA TTS HTTP %s error: %s — %s", e.code, e.reason, body)
        except urllib.error.URLError as e:
            log.error("NVIDIA TTS network error: %s", e.reason)
        except Exception as e:
            log.error("NVIDIA TTS error: %s", e)

        log.warning("NVIDIA TTS: falling back to Edge TTS")
        return self._synthesize_edge_tts(text, self._get_fallback_edge_voice())

    def _play_audio(self, audio_bytes: bytes) -> None:
        """Play audio_bytes via Windows MediaPlayer."""
        if not audio_bytes or self._stop_event.is_set():
            return

        # Detect format by magic bytes: WAV starts with RIFF, MP3 with ID3 or 0xFF 0xFB
        is_wav = audio_bytes[:4] == b"RIFF"
        suffix = ".wav" if is_wav else ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        safe_path = tmp_path.replace("\\", "/")

        try:
            import subprocess

            ps_template = (
                'Add-Type -AssemblyName presentationCore\n'
                '$p = New-Object System.Windows.Media.MediaPlayer\n'
                '$p.Open([System.Uri]"__SAFE_PATH__")\n'
                '$timeout = 0\n'
                'while (-not $p.NaturalDuration.HasTimeSpan -and $timeout -lt 30) {\n'
                '    Start-Sleep -Milliseconds 50\n'
                '    $timeout++\n'
                '}\n'
                'Start-Sleep -Milliseconds 100\n'
                '$p.Play()\n'
                'Start-Sleep -Milliseconds 50\n'
                'while ($p.NaturalDuration.HasTimeSpan -and ($p.Position -lt $p.NaturalDuration.TimeSpan)) {\n'
                '    Start-Sleep -Milliseconds 50\n'
                '}\n'
                'Start-Sleep -Milliseconds 100\n'
                '$p.Close()\n'
            )

            ps_code = ps_template.replace("__SAFE_PATH__", safe_path)
            encoded_cmd = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")

            self._player_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )

            while self._player_proc.poll() is None:
                if self._stop_event.is_set():
                    self._player_proc.terminate()
                    break
                time.sleep(0.05)

        except Exception as e:
            log.error("Audio playback error: %s", e)
        finally:
            self._player_proc = None
            try:
                if os.path.exists(tmp_path):
                    time.sleep(0.1)
                    os.remove(tmp_path)
            except Exception:
                pass


tts_engine = TTSEngine()


