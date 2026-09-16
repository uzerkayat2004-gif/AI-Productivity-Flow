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
import queue
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
from voice_flow.structured_reader import (
    format_document_structure_for_speech,
    split_spoken_sentences,
    classify_pause_after_sentence,
    strip_pause_markers,
)

log = logging.getLogger(__name__)


def _sanitize_error_msg(error: Any) -> str:
    """Sanitize error strings to guarantee no API keys, tokens, or private secrets leak into logs or UI."""
    msg = str(error or "")
    msg = re.sub(r'(?i)(?:key|api_key|secret|token)=([A-Za-z0-9_\-]+)', r'key=[REDACTED]', msg)
    msg = re.sub(r'(?i)(?:bearer\s+)([A-Za-z0-9_\-\.]{8,})', r'Bearer [REDACTED]', msg)
    msg = re.sub(r'(?i)(?:xi-api-key[:=]\s*)([A-Za-z0-9_\-\.]{8,})', r'xi-api-key: [REDACTED]', msg)
    return msg


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
        try:
            from voice_flow.audio_explainer import expand_spoken_abbreviations
            text = expand_spoken_abbreviations(text)
        except Exception:
            pass
        return text.strip()

    def __init__(self) -> None:
        self._is_speaking = False
        self._is_paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._session = 0
        self._speech_thread: threading.Thread | None = None
        self._player_proc: Any = None
        self._active_mci_alias: str | None = None
        self._sentences: list[str] = []
        self._current_sentence_idx = 0

    def is_speaking(self) -> bool:
        return self._is_speaking

    def is_paused(self) -> bool:
        return self._is_paused

    def pause(self) -> None:
        """Pause speech audio playback in place (resumable via resume())."""
        if not self._is_speaking or self._is_paused:
            return
        self._is_paused = True
        self._pause_event.set()
        if self._active_mci_alias:
            try:
                import ctypes
                ctypes.windll.winmm.mciSendStringW(f"pause {self._active_mci_alias}", None, 0, 0)
            except Exception:
                pass

    def resume(self) -> None:
        """Resume speech audio playback after pause()."""
        if not self._is_paused:
            return
        self._is_paused = False
        self._pause_event.clear()
        if self._active_mci_alias:
            try:
                import ctypes
                ctypes.windll.winmm.mciSendStringW(f"resume {self._active_mci_alias}", None, 0, 0)
            except Exception:
                pass

    def stop(self) -> None:
        """Immediately stop speech audio playback."""
        self._stop_event.set()
        self._pause_event.clear()
        self._is_speaking = False
        self._is_paused = False
        if self._active_mci_alias:
            try:
                import ctypes
                ctypes.windll.winmm.mciSendStringW(f"close {self._active_mci_alias}", None, 0, 0)
            except Exception:
                pass
            self._active_mci_alias = None
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

    def set_speed(self, speed: float) -> None:
        """Set the speech speed for the next TTS synthesis (baked into neural voice generation)."""
        speed_clamped = max(0.5, min(3.0, float(speed)))
        storage.save_setting("audio_flow_speed", speed_clamped)
        log.info("Set Audio Flow speed to %.2fx (applied on next synthesis)", speed_clamped)

    def supports_progressive_audio(self, full_model_id: str) -> bool:
        """Return True if the provider adapter supports progressive audio streaming."""
        parts = full_model_id.split("/", 1)
        provider = parts[0].lower() if len(parts) > 1 else "edge"
        return provider == "edge"

    def _synthesize_and_play_progressive(
        self,
        clean_text: str,
        full_model_id: str,
        on_start: Callable[[], None] | None = None,
        session: int = 0,
    ) -> bool:
        """Synthesize and play audio progressively using fast Windows MCI playback."""
        if session != self._session:
            return False

        parts = full_model_id.split("/", 1)
        model_id = parts[1] if len(parts) > 1 else full_model_id
        resolved_voice = resolve_edge_voice(model_id)
        voice_name = self._detect_voice_for_text(clean_text, resolved_voice)

        sentences = split_spoken_sentences(clean_text)
        if not sentences:
            sentences = [clean_text]

        if len(sentences) > 1 and len(clean_text) > 100:
            return self._synthesize_and_play_pipelined(sentences, voice_name, on_start, session)

        return self._synthesize_and_play_single_progressive(clean_text, voice_name, on_start, session)

    # ------------------------------------------------------------------
    # Human-like inter-sentence pause timing
    # ------------------------------------------------------------------
    _PAUSE_MS = {
        "sentence":   400,     # Regular sentence boundary — natural breath
        "paragraph":  820,     # Paragraph transition — longer breath + thought shift
        "section":    1100,    # Section / heading boundary — clear topic change
        "list_item":  300,     # Between list items — quick rhythmic gap
        "colon":      550,     # After a colon lead-in — anticipation pause
    }

    @staticmethod
    def _compute_pause_ms(pause_class: str) -> int:
        """Return the inter-sentence silence duration in milliseconds for *pause_class*.

        Mirrors how a skilled human reader naturally paces their speech:
        - Short breathing pauses between regular sentences (~400 ms)
        - Longer pauses at paragraph boundaries (~820 ms)
        - Prominent pauses after section headings (~1100 ms)
        - Quick rhythmic gaps between list items (~300 ms)
        - Anticipation pauses after colon lead-ins (~550 ms)
        """
        return TTSEngine._PAUSE_MS.get(pause_class, 400)

    def _get_speed_factor(self) -> float:
        """Return the current user-configured audio speed multiplier (0.5x - 3.0x)."""
        try:
            return max(0.5, min(3.0, float(storage.get_setting("audio_flow_speed", 1.0))))
        except Exception:
            return 1.0

    def _get_inter_sentence_pause_sec(self, pause_class: str) -> float:
        """Calculate pause duration in seconds scaled inversely by reading speed."""
        base_ms = self._compute_pause_ms(pause_class)
        speed = self._get_speed_factor()
        scaled_ms = max(150, min(2000, int(base_ms / speed)))
        return scaled_ms / 1000.0

    def _synthesize_and_play_pipelined(
        self,
        sentences: list[str],
        voice_name: str,
        on_start: Callable[[], None] | None = None,
        session: int = 0,
    ) -> bool:
        """Pipelined multi-sentence streaming playback for ultra-low latency Time-To-First-Audio."""
        if session != self._session or self._stop_event.is_set():
            return False

        def _cancelled() -> bool:
            return self._stop_event.is_set() or session != self._session

        import edge_tts
        import ctypes

        winmm = getattr(getattr(ctypes, "windll", None), "winmm", None)
        rate_str = self._get_speed_rate_str()
        pitch_str = "+0Hz"

        audio_queue: queue.Queue[tuple[int, str | None, bool, str]] = queue.Queue(maxsize=10)
        temp_files_to_clean: list[str] = []

        def _producer():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                for idx, sentence in enumerate(sentences):
                    if _cancelled():
                        break

                    # Classify the structural pause BEFORE stripping markers
                    pause_class = classify_pause_after_sentence(sentence)
                    # Strip pause markers so TTS engine never sees them
                    synth_text = strip_pause_markers(sentence).strip()
                    if not synth_text:
                        audio_queue.put((idx, None, idx == len(sentences) - 1, pause_class))
                        continue

                    valid_v = resolve_edge_voice(self._detect_voice_for_text(synth_text, voice_name))
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
                        s_path = tmp_f.name
                    temp_files_to_clean.append(s_path)

                    data = bytearray()
                    try:
                        communicate = edge_tts.Communicate(synth_text, valid_v, rate=rate_str, pitch=pitch_str)
                        async def _get_chunk():
                            async for chunk in communicate.stream():
                                if _cancelled():
                                    break
                                if chunk.get("type") == "audio" and chunk.get("data"):
                                    data.extend(chunk["data"])
                        loop.run_until_complete(_get_chunk())
                    except Exception as pe:
                        log.debug("Pipelined sentence synthesis warning for idx %d: %s", idx, pe)

                    if _cancelled():
                        break

                    if data:
                        with open(s_path, "wb") as fp:
                            fp.write(data)
                        audio_queue.put((idx, s_path, idx == len(sentences) - 1, pause_class))
                    else:
                        audio_queue.put((idx, None, idx == len(sentences) - 1, pause_class))
            finally:
                loop.close()
                audio_queue.put((-1, None, True, "sentence"))

        prod_thread = threading.Thread(target=_producer, daemon=True)
        prod_thread.start()

        started_fired = False
        played_any = False

        try:
            while not _cancelled():
                try:
                    idx, s_path, is_last, pause_class = audio_queue.get(timeout=20.0)
                except queue.Empty:
                    break

                if idx == -1 or _cancelled():
                    break

                if not s_path or not os.path.exists(s_path):
                    if is_last:
                        break
                    continue

                if not started_fired:
                    started_fired = True
                    if on_start:
                        on_start()

                alias = f"vf_pipe_{time.time_ns()}_{idx}"
                self._active_mci_alias = alias
                safe_path = s_path.replace("\\", "/")

                open_res = winmm.mciSendStringW(f'open "{safe_path}" type MPEGVideo alias {alias}', None, 0, 0)
                if open_res == 0:
                    winmm.mciSendStringW(f'play {alias}', None, 0, 0)
                    if self._is_paused:
                        winmm.mciSendStringW(f'pause {alias}', None, 0, 0)

                    played_any = True
                    buf = ctypes.create_unicode_buffer(128)
                    while not _cancelled():
                        winmm.mciSendStringW(f'status {alias} mode', buf, 128, 0)
                        status = buf.value.lower()
                        if status not in ("playing", "paused"):
                            break
                        time.sleep(0.04)

                    winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                    self._active_mci_alias = None
                    if not _cancelled() and not is_last:
                        # Context-aware pause: human-like breathing rhythm with speed scaling
                        pause_sec = self._get_inter_sentence_pause_sec(pause_class)
                        deadline = time.perf_counter() + pause_sec
                        while time.perf_counter() < deadline and not _cancelled():
                            if self._is_paused:
                                time.sleep(0.04)
                                continue
                            time.sleep(0.02)
                else:
                    log.warning("Pipelined MCI open failed for sentence %d with code %d", idx, open_res)

                if is_last or _cancelled():
                    break

            return played_any
        finally:
            self._active_mci_alias = None
            for p in temp_files_to_clean:
                try:
                    if os.path.exists(p):
                        time.sleep(0.02)
                        os.remove(p)
                except Exception:
                    pass

    def _synthesize_and_play_single_progressive(
        self,
        clean_text: str,
        voice_name: str,
        on_start: Callable[[], None] | None = None,
        session: int = 0,
    ) -> bool:
        """Synthesize and play single chunk progressively using Windows MCI."""
        if session != self._session or self._stop_event.is_set():
            return False

        clean_text = strip_pause_markers(clean_text).strip()
        if not clean_text:
            return False

        def _cancelled() -> bool:
            return self._stop_event.is_set() or session != self._session

        alias = f"vf_audio_{time.time_ns()}"
        self._active_mci_alias = alias
        tmp_path: str | None = None

        try:
            import edge_tts
            import ctypes

            winmm = getattr(getattr(ctypes, "windll", None), "winmm", None)
            rate_str = self._get_speed_rate_str()
            pitch_str = "+0Hz"

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_f:
                tmp_path = tmp_f.name

            safe_path = tmp_path.replace("\\", "/")

            playback_started = False
            playback_completed_cleanly = False

            async def _stream_and_play_async():
                nonlocal playback_started, playback_completed_cleanly
                valid_v = resolve_edge_voice(voice_name)
                communicate = edge_tts.Communicate(
                    clean_text, valid_v, rate=rate_str, pitch=pitch_str
                )
                data = bytearray()

                async for chunk in communicate.stream():
                    if _cancelled():
                        break
                    if chunk.get("type") == "audio":
                        chunk_bytes = chunk.get("data", b"")
                        if chunk_bytes:
                            data.extend(chunk_bytes)

                if _cancelled():
                    return

                if not data:
                    return

                with open(tmp_path, "wb") as fp:
                    fp.write(data)

                if _cancelled():
                    return

                playback_started = True
                if on_start:
                    on_start()

                open_res = winmm.mciSendStringW(f'open "{safe_path}" type MPEGVideo alias {alias}', None, 0, 0)
                if open_res == 0:
                    winmm.mciSendStringW(f'play {alias}', None, 0, 0)
                    if self._is_paused:
                        winmm.mciSendStringW(f'pause {alias}', None, 0, 0)
                    buf = ctypes.create_unicode_buffer(128)
                    while not _cancelled():
                        winmm.mciSendStringW(f'status {alias} mode', buf, 128, 0)
                        status = buf.value.lower()
                        if status not in ("playing", "paused"):
                            break
                        time.sleep(0.05)
                    if not _cancelled():
                        playback_completed_cleanly = True
                else:
                    log.warning("MCI open failed with code %d", open_res)

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_stream_and_play_async())
            finally:
                loop.close()

            return playback_started or playback_completed_cleanly
        except Exception as e:
            log.warning("Fast progressive audio error: %s", e)
            return False
        finally:
            if hasattr(self, "_active_mci_alias") and self._active_mci_alias == alias:
                try:
                    import ctypes
                    ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                except Exception:
                    pass
                self._active_mci_alias = None
            try:
                if tmp_path and os.path.exists(tmp_path):
                    time.sleep(0.05)
                    os.remove(tmp_path)
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
        # Invalidate any still-running previous speak() so it cannot overlap
        # playback, fire stale callbacks, or clobber _is_speaking afterwards.
        self._session += 1
        session = self._session
        self._stop_event.clear()
        self._pause_event.clear()
        self._is_speaking = True
        self._is_paused = False

        def _worker():
            def _cancelled() -> bool:
                return self._stop_event.is_set() or session != self._session

            started = [False]
            errored = [False]

            def _fire_on_start() -> None:
                if not started[0]:
                    started[0] = True
                    if on_start:
                        on_start()

            try:
                preprocessed = self._preprocess_text(text)
                clean_text = format_document_structure_for_speech(preprocessed)

                sentences = split_spoken_sentences(clean_text)
                if not sentences:
                    sentences = [clean_text]

                self._sentences = sentences
                self._current_sentence_idx = 0
                active_model = model_override or storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural")

                log.info("Audio Flow: Synthesizing continuous text (%d chars, %d sentences)", len(clean_text), len(sentences))

                # Progressive playback route for streaming-capable providers
                if self.supports_progressive_audio(active_model):
                    success = self._synthesize_and_play_progressive(clean_text, active_model, _fire_on_start, session)
                    if _cancelled():
                        return
                    if success:
                        return
                    log.warning("Progressive audio path completed or failed; falling back to completed audio path if needed")

                if _cancelled():
                    return

                # Fallback / non-streaming completed audio path
                _fire_on_start()

                audio_bytes = self._synthesize(clean_text, active_model)

                if _cancelled():
                    return

                if audio_bytes:
                    self._play_audio(audio_bytes, session)
                else:
                    log.warning("Audio Flow synthesis returned empty audio.")
                    if on_error and not _cancelled():
                        errored[0] = True
                        on_error("TTS synthesis failed: no audio generated.")

            except Exception as e:
                log.error("Audio Flow TTS error: %s", e)
                if on_error and session == self._session:
                    errored[0] = True
                    on_error(str(e))
            finally:
                if session == self._session:
                    self._is_speaking = False
                    self._is_paused = False
                    # on_error and on_done are mutually exclusive terminal
                    # callbacks: firing on_done after on_error would immediately
                    # flip the caller's error UI back to the ready state.
                    if on_done and not errored[0]:
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

    def _model_is_enabled(self, provider: str, model_id: str) -> bool:
        """Honor provider/model toggles before any network request is made."""
        if provider in {"edge", "offline", "sapi", "sapi5", "windows"}:
            state = storage.get_tts_model_active("edge" if provider == "edge" else "offline", model_id)
            return state is not False
        if provider.startswith("custom-"):
            for cp in getattr(storage, "get_audio_flow_custom_providers", lambda: [])():
                if cp.get("id") != provider:
                    continue
                if not cp.get("is_active", True):
                    return False
                for model in cp.get("models") or []:
                    if str(model.get("model_id") or "") == model_id:
                        return bool(model.get("is_active", True))
                return False
            return False
        state = storage.get_tts_model_active(provider, model_id)
        return state is not False

    def _synthesize(self, text: str, full_model_id: str) -> bytes | None:
        text = strip_pause_markers(text).strip()
        parts = full_model_id.split("/", 1)
        provider = parts[0].lower() if len(parts) > 1 else "edge"
        model_id = parts[1] if len(parts) > 1 else full_model_id

        if not self._model_is_enabled(provider, model_id):
            log.error("Audio Flow: Refusing to use disabled or missing model '%s'.", full_model_id)
            return None

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
        elif provider == "fish":
            return self._synthesize_fish(text, model_id)
        elif provider in {"offline", "sapi", "sapi5", "windows"}:
            return self._synthesize_sapi(text)
        elif provider.startswith("custom-"):
            res = self._synthesize_custom(text, provider, model_id)
            if res:
                return res
            log.warning("Audio Flow: Custom provider '%s' failed, falling back to Edge TTS", provider)
            return None
        else:
            log.warning("Audio Flow: Unknown or unconfigured TTS provider '%s', falling back to Edge TTS", provider)
            return None

    def _get_speed_rate_str(self) -> str:
        speed = float(storage.get_setting("audio_flow_speed", 1.0))
        pct = int(round((speed - 1.0) * 100))
        return f"{'+' if pct >= 0 else ''}{pct}%"

    def _synthesize_sapi(self, text: str) -> bytes | None:
        """Offline zero-network fallback using Windows SAPI Speech API or macOS say."""
        tmp_path = None
        if sys.platform == "darwin":
            try:
                from voice_flow.platform import get_backend
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                    tmp_path = tmp_f.name
                ok = get_backend().system_tts_to_file(text, tmp_path)
                if ok and os.path.exists(tmp_path):
                    with open(tmp_path, "rb") as fp:
                        data = fp.read()
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    return data
            except Exception as e:
                log.debug("macOS native TTS error: %s", e)
            return None
        try:
            import win32com.client
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                tmp_path = tmp_f.name

            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            filestream = win32com.client.Dispatch("SAPI.SpFileStream")
            filestream.Format.Type = 38  # SAFT44kHz16BitMono
            filestream.Open(tmp_path, 3, False)
            speaker.AudioOutputStream = filestream

            speed = float(storage.get_setting("audio_flow_speed", 1.0))
            rate_val = max(-10, min(10, int((speed - 1.0) * 6)))
            speaker.Rate = rate_val
            speaker.Speak(text)
            filestream.Close()

            if os.path.exists(tmp_path):
                with open(tmp_path, "rb") as fp:
                    data = fp.read()
                return data
        except Exception as e:
            log.debug("SAPI COM synthesis error: %s; trying powershell SAPI fallback", e)
            try:
                import subprocess
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                    tmp_path = tmp_f.name
                escaped_text = text.replace("'", "''").replace('"', '`"')
                safe_wav = tmp_path.replace("\\", "/")
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Speech; "
                    f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$synth.SetOutputToWaveFile('{safe_wav}'); "
                    f"$synth.Speak('{escaped_text}'); "
                    f"$synth.Dispose()"
                )
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True,
                    timeout=10,
                    creationflags=0x08000000
                )
                if res.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                    with open(tmp_path, "rb") as fp:
                        data = fp.read()
                    return data
            except Exception as pe:
                log.warning("PowerShell SAPI synthesis error: %s", pe)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        return None

    def _synthesize_edge_tts(self, text: str, voice_name: str | None = None) -> bytes | None:
        # Every cloud-provider fallback calls this with only the text. Resolve
        # the user's configured Edge voice here so the fallback speaks with the
        # right voice instead of raising a missing-argument TypeError.
        if not voice_name:
            voice_name = self._get_fallback_edge_voice()
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
                res = loop.run_until_complete(_main())
                if res:
                    return res
            finally:
                loop.close()
        except Exception as e:
            log.warning("Edge-TTS synthesis error: %s; falling back to offline SAPI", e)

        return self._synthesize_sapi(text)

    def _get_active_keys_for_provider(self, provider: str) -> list[dict[str, Any]]:
        if provider.startswith("custom-"):
            custom_keys = []
            try:
                for cp in getattr(storage, "get_audio_flow_custom_providers", lambda: [])():
                    if cp.get("id") == provider:
                        configured_keys = cp.get("api_keys") or []
                        for idx, k in enumerate(configured_keys):
                            if isinstance(k, dict) and k.get("is_active", True) and str(k.get("key") or "").strip():
                                custom_keys.append({"id": k.get("id") or idx, "api_key": str(k.get("key")).strip(), "is_active": 1, "is_valid": 1, "name": k.get("name")})
                        # Legacy one-key providers predate api_keys. Once a key
                        # list exists, disabling every entry must remain final;
                        # never resurrect the mirrored top-level api_key.
                        if not configured_keys and str(cp.get("api_key") or "").strip():
                            custom_keys.append({"id": "legacy", "api_key": str(cp.get("api_key")).strip(), "is_active": 1, "is_valid": 1, "name": cp.get("name")})
                        break
            except Exception:
                pass
            all_keys = custom_keys
        else:
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

        # Audio Flow Round-Robin Support
        mode = "priority"
        if hasattr(storage, "get_audio_provider_load_balance_mode"):
            mode = storage.get_audio_provider_load_balance_mode(provider)
        if (mode == "round_robin" or mode == "round-robin") and len(active) > 1:
            cursor_key = f"audio_provider_cursor_{provider}"
            cursor = int(storage.get_setting(cursor_key, 0) or 0) % len(active)
            storage.save_setting(cursor_key, cursor + 1)
            active = active[cursor:] + active[:cursor]
        return active

    def _synthesize_custom(self, text: str, provider: str, voice_id: str) -> bytes | None:
        cp_entry = None
        for cp in getattr(storage, "get_audio_flow_custom_providers", lambda: [])():
            if cp.get("id") == provider:
                cp_entry = cp
                break
        if not cp_entry:
            return None
        active_keys = self._get_active_keys_for_provider(provider)
        if not active_keys:
            log.warning("Audio Flow: Custom TTS provider '%s' has no enabled key.", provider)
            return None
        base_url = str(cp_entry.get("base_url") or "").rstrip("/")
        api_fmt = str(cp_entry.get("api_format") or "openai").lower()
        custom_headers = cp_entry.get("headers") if isinstance(cp_entry.get("headers"), dict) else {}
        for conn in active_keys:
            key = str(conn.get("api_key") or "")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VoiceFlow/2.0",
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                **custom_headers,
            }
            try:
                if api_fmt == "elevenlabs":
                    headers["xi-api-key"] = key
                    url = f"{base_url}/v1/text-to-speech/{voice_id}"
                    data = json.dumps({"text": text}).encode("utf-8")
                else:
                    url = f"{base_url}/audio/speech" if not base_url.endswith("/speech") else base_url
                    data = json.dumps({
                        "model": voice_id or "tts-1",
                        "input": text,
                        "voice": "alloy",
                    }).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    status_code = getattr(resp, "status", None) or getattr(resp, "code", None) or (resp.getcode() if hasattr(resp, "getcode") else 200)
                    audio = resp.read() if status_code in (200, 201) else b""
                    if audio:
                        return audio
            except Exception as e:
                log.warning("Audio Flow: Custom TTS provider '%s' connection '%s' failed: %s", provider, conn.get("name") or conn.get("id"), e)
        return None

    def _synthesize_elevenlabs(self, text: str, voice_id: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("elevenlabs")
        if not active_keys:
            log.warning("ElevenLabs TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        model_family = "eleven_multilingual_v2"
        try:
            row = storage.get_tts_model_family("elevenlabs", voice_id)
            if row:
                model_family = row
        except Exception:
            pass
        payload = json.dumps({
            "text": text,
            "model_id": model_family,
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
        return self._synthesize_edge_tts(text)

    def _synthesize_deepgram(self, text: str, model_name: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("deepgram")
        if not active_keys:
            log.warning("Deepgram TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text)

        endpoint = "/v2/speak" if model_name.lower().startswith("flux") else "/v1/speak"
        url = f"https://api.deepgram.com{endpoint}?model={model_name}"
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
        return self._synthesize_edge_tts(text)

    def _synthesize_openai(self, text: str, model_voice_spec: str) -> bytes | None:
        active_keys = self._get_active_keys_for_provider("openai")
        if not active_keys:
            log.warning("OpenAI TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text)

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
        return self._synthesize_edge_tts(text)

    def _synthesize_google(self, text: str, model_id: str) -> bytes | None:
        """Synthesize speech using Google Cloud TTS REST API with API key."""
        active_keys = self._get_active_keys_for_provider("google")
        if not active_keys:
            log.warning("Google Cloud TTS: No active API key configured, falling back to Edge TTS")
            return self._synthesize_edge_tts(text)

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
                clean_body = _sanitize_error_msg(body)
                log.error("Google Cloud TTS HTTP %s error: %s — %s", e.code, e.reason, clean_body)
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("Google Cloud TTS synthesis error: %s", _sanitize_error_msg(e))

        log.warning("Google Cloud TTS: all keys failed, falling back to Edge TTS")
        return self._synthesize_edge_tts(text)

    def _synthesize_gemini(self, text: str, model_voice_spec: str) -> bytes | None:
        """Synthesize speech using Gemini TTS (generativelanguage.googleapis.com)."""
        active_keys = self._get_active_keys_for_provider("gemini")
        if not active_keys:
            log.warning("Gemini TTS: No active API key configured, falling back to Edge TTS")
            return None

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
                log.error("Gemini TTS HTTP %s error: %s", e.code, _sanitize_error_msg(e.reason))
                if cid:
                    is_valid = e.code not in (401, 403)
                    storage.update_audio_provider_connection_validation(cid, is_valid, f"HTTP {e.code}")
            except Exception as e:
                log.error("Gemini TTS error: %s", _sanitize_error_msg(e))

        log.warning("Gemini TTS: all keys failed, falling back to Edge TTS")
        return None

    def _synthesize_fish(self, text: str, voice_id: str) -> bytes | None:
        """Synthesize with Fish Audio and fail over through enabled keys."""
        active_keys = self._get_active_keys_for_provider("fish")
        if not active_keys:
            log.warning("Fish Audio: No active API key configured.")
            return None
        payload = json.dumps({"text": text, "reference_id": voice_id or "default", "format": "mp3"}).encode("utf-8")
        for conn in active_keys:
            api_key = str(conn.get("api_key") or "").strip()
            req = urllib.request.Request(
                "https://api.fish.audio/v1/tts",
                data=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "VoiceFlow/1.0"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    audio = resp.read()
                    if audio:
                        return audio
            except Exception as exc:
                log.warning("Fish Audio connection '%s' failed: %s", conn.get("name") or conn.get("id"), exc)
        return None

    def _synthesize_nvidia(self, text: str, model_name: str) -> bytes | None:
        """Synthesize speech using enabled NVIDIA keys with configured routing.

        NVIDIA Riva TTS is a SELF-HOSTED NIM (gRPC 50051 / HTTP 9000). NVIDIA's
        public cloud catalog exposes no TTS models and has no /v1/audio/speech
        route, so the endpoint must come from the connection's base_url.
        """
        active_keys = self._get_active_keys_for_provider("nvidia")
        if not active_keys:
            log.warning("NVIDIA TTS: No active API key configured.")
            return None

        fam, _, voice = model_name.partition(":")
        fam = (fam or model_name).strip()
        voice = (voice or fam).strip()

        for conn in active_keys:
            api_key = str(conn.get("api_key") or "").strip()
            cid = conn.get("id")
            base = str(conn.get("base_url") or conn.get("baseUrl") or "").strip().rstrip("/")
            if not base:
                log.error(
                    "NVIDIA TTS: no base URL configured for connection '%s'. "
                    "Riva TTS is self-hosted (default http://localhost:9000) — set the "
                    "provider's base URL to your Riva NIM endpoint.",
                    conn.get("name") or cid,
                )
                continue
            url = base if base.endswith("/v1/audio/speech") else f"{base}/v1/audio/speech"
            # Riva's HTTP API selects the voice by name, not by catalog model id.
            payload = json.dumps({
                "text": text,
                "voice_name": voice,
                "language_code": "en-US",
                "encoding": "LINEAR_PCM",
                "sample_rate_hz": 44100,
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "VoiceFlow/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    audio = resp.read()
                    if audio:
                        if isinstance(cid, int) and cid > 0:
                            storage.update_audio_provider_connection_validation(cid, True, None)
                        log.info("NVIDIA TTS: synthesis succeeded (%d bytes)", len(audio))
                        return audio
            except urllib.error.HTTPError as exc:
                body = exc.read(500).decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                log.error("NVIDIA TTS HTTP %s error: %s — %s", exc.code, exc.reason, body)
                if isinstance(cid, int) and cid > 0:
                    storage.update_audio_provider_connection_validation(cid, exc.code not in (401, 403), f"HTTP {exc.code}")
            except Exception as exc:
                log.error("NVIDIA TTS connection '%s' failed: %s", conn.get("name") or cid, exc)
        return None

    def _play_audio(self, audio_bytes: bytes, session: int = 0) -> None:
        """Play audio_bytes via MCI (pausable), falling back to PowerShell MediaPlayer."""
        if not audio_bytes or self._stop_event.is_set() or session != self._session:
            return

        # Detect format by magic bytes: WAV starts with RIFF, MP3 with ID3 or 0xFF 0xFB
        is_wav = audio_bytes[:4] == b"RIFF"
        suffix = ".wav" if is_wav else ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        safe_path = tmp_path.replace("\\", "/")
        alias = f"vf_audio_{time.time_ns()}"
        mci_played = False

        if sys.platform == "darwin":
            try:
                import subprocess
                self._player_proc = subprocess.Popen(["afplay", safe_path])
                while self._player_proc.poll() is None:
                    if self._stop_event.is_set() or session != self._session:
                        self._player_proc.terminate()
                        break
                    time.sleep(0.05)
            except Exception as e:
                log.error("macOS afplay playback error: %s", e)
            finally:
                self._player_proc = None
                try:
                    if os.path.exists(tmp_path):
                        time.sleep(0.1)
                        os.remove(tmp_path)
                except Exception:
                    pass
            return

        try:
            import ctypes

            winmm = getattr(getattr(ctypes, "windll", None), "winmm", None)
            if not winmm:
                raise RuntimeError("winmm is not available")
            self._active_mci_alias = alias
            mci_type = "type waveaudio" if is_wav else "type MPEGVideo"
            open_res = winmm.mciSendStringW(f'open "{safe_path}" {mci_type} alias {alias}', None, 0, 0)
            if open_res == 0:
                mci_played = True
                winmm.mciSendStringW(f'play {alias}', None, 0, 0)
                if self._is_paused:
                    winmm.mciSendStringW(f'pause {alias}', None, 0, 0)
                buf = ctypes.create_unicode_buffer(128)
                while not (self._stop_event.is_set() or session != self._session):
                    winmm.mciSendStringW(f'status {alias} mode', buf, 128, 0)
                    if buf.value.lower() not in ("playing", "paused"):
                        break
                    time.sleep(0.05)
            else:
                log.warning("MCI open failed with code %d; using PowerShell playback", open_res)
        except Exception as e:
            log.error("MCI playback error: %s", e)
        finally:
            if self._active_mci_alias == alias:
                try:
                    import ctypes
                    ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                except Exception:
                    pass
                self._active_mci_alias = None

        if mci_played or self._stop_event.is_set() or session != self._session:
            try:
                if os.path.exists(tmp_path):
                    time.sleep(0.1)
                    os.remove(tmp_path)
            except Exception:
                pass
            return

        # Codec fallback: MCI cannot open this format; MediaPlayer is not pausable.
        try:
            import subprocess

            ps_template = (
                'Add-Type -AssemblyName presentationCore\n'
                '$path = [System.IO.Path]::GetFullPath("__SAFE_PATH__")\n'
                '$p = New-Object System.Windows.Media.MediaPlayer\n'
                '$p.Open([System.Uri]$path)\n'
                '$timeout = 0\n'
                'while (-not $p.NaturalDuration.HasTimeSpan -and $timeout -lt 200) {\n'
                '    Start-Sleep -Milliseconds 50\n'
                '    $timeout++\n'
                '}\n'
                'if ($p.NaturalDuration.HasTimeSpan) {\n'
                '    Start-Sleep -Milliseconds 100\n'
                '    $p.Play()\n'
                '    Start-Sleep -Milliseconds 50\n'
                '    while ($p.NaturalDuration.HasTimeSpan -and ($p.Position -lt $p.NaturalDuration.TimeSpan)) {\n'
                '        Start-Sleep -Milliseconds 50\n'
                '    }\n'
                '    Start-Sleep -Milliseconds 100\n'
                '}\n'
                '$p.Close()\n'
            )

            ps_code = ps_template.replace("__SAFE_PATH__", safe_path)
            encoded_cmd = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")

            self._player_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )

            while self._player_proc.poll() is None:
                if self._stop_event.is_set() or session != self._session:
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


