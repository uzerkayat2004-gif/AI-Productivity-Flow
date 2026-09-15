"""Audio capture module — captures native microphone hardware input and resamples to 16kHz for Whisper STT."""

from __future__ import annotations

import logging
import threading
import time
import wave
from typing import TYPE_CHECKING

import numpy as np
import scipy.signal as sig
import sounddevice as sd

if TYPE_CHECKING:
    from numpy.typing import NDArray

from voice_flow.config import config
from voice_flow.vad import AdaptiveVAD

log = logging.getLogger(__name__)

# The saved mic name can go stale (renamed/unplugged device) and then fails
# the per-start query every time before the default-device fallback kicks in.
# Warn once so the first occurrence stays visible in diagnostics; later starts
# fall back silently instead of spamming the log.
_stale_device_warned_once = False

# Chunk-split tuning: a pause this quiet for this long closes the current
# streaming chunk; nonstop speech is force-split at the hard cap.
# _SILENCE_RMS calibrated to 0.0012 so distant speech (~10ft away) is not truncated.
_SILENCE_RMS = 0.0012
SPLIT_SILENCE_SECONDS = 0.35
MIN_CHUNK_SECONDS = 0.30
# Continuous speech needs work to begin before release. Forced chunks retain
# a small audio prefix for the next chunk; StreamTranscriber receives explicit
# metadata and verifies that overlap before joining text.
MAX_CHUNK_SECONDS = float(getattr(config, "max_chunk_seconds", 8.0) or 8.0)
FORCED_CHUNK_OVERLAP_SECONDS = 0.40
MAX_STARTUP_STREAM_BUFFER_SECONDS = 5.0


class AudioRecorder:
    """Captures microphone audio into a buffer at hardware rate and resamples to 16kHz."""

    def __init__(self) -> None:
        self._buffer: list[NDArray[np.float32]] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()
        # Serializes stream construction/start against stop/close.  The audio
        # callback still uses _lock only, so it cannot block device teardown.
        self._lifecycle_lock = threading.RLock()
        self._level: float = 0.0  # 0.0–1.0 normalized RMS
        self._native_sr: int = 44100
        self._native_ch: int = 1
        # Streaming chunk state (see stream_stt.StreamTranscriber). The audio
        # callback accumulates the open chunk and closes it on silence; closed
        # chunks are handed to on_chunk_closed (native-rate array + samplerate)
        # by VoiceFlowApp for background transcription while recording.
        self._chunk: list[NDArray[np.float32]] = []
        self._chunk_start_mono: float | None = None
        self._last_voice_mono: float | None = None
        self._chunk_voice_samples = 0
        # Duration at the front of the open chunk that was copied from the
        # preceding forced chunk.  It is carried with the *next* dispatch,
        # rather than inferred later from transcript wording.
        self._chunk_overlap_prefix_seconds = 0.0
        self.on_chunk_closed = None  # Callable[[NDArray, int], None] | None
        self.on_audio_frame = None  # Nonblocking live-provider queue intake.
        # Startup may open the microphone before a remote streaming provider
        # finishes arming. Keep those first frames and any closed chunks in
        # order, then replay them into the newly armed provider. This is a
        # bounded, per-recording buffer; it is never an always-listening mic.
        self._buffer_stream_input = False
        self._pending_live_frames: list[NDArray[np.float32]] = []
        self._pending_closed_chunks: list[tuple[NDArray[np.float32], float]] = []
        self._pending_stream_events: list[tuple[str, NDArray[np.float32], float]] = []
        self._startup_stream_buffered_samples = 0
        self._startup_stream_overflow = False
        self._vad = AdaptiveVAD(min_speech_rms=_SILENCE_RMS)

    # -- public API --

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def level(self) -> float:
        """Current audio RMS level (0.0–1.0), used for waveform animation."""
        return self._level

    def start(self, device: str | int | None = None) -> bool:
        """Start capture and return whether the input stream was opened successfully."""
        global _stale_device_warned_once
        with self._lifecycle_lock:
            with self._lock:
                if self._recording:
                    return True
                self._buffer.clear()
                chunk_list = getattr(self, "_chunk", None)
                if chunk_list is None:
                    chunk_list = self._chunk = []
                chunk_list.clear()
                self._chunk_start_mono = None
                self._last_voice_mono = None
                self._chunk_voice_samples = 0
                self._level = 0.0
                # Preserve an explicit startup-buffering request. VoiceFlowApp
                # arms begin_stream_input_buffering() BEFORE calling start(), so
                # clearing the flag here silently discarded every frame that
                # arrived before the provider sink was installed — the opening
                # words of the dictation. Only reset the buffer when buffering
                # was not requested for this capture.
                if not getattr(self, "_buffer_stream_input", False):
                    self._pending_live_frames.clear()
                    self._pending_closed_chunks.clear()
                    self._pending_stream_events.clear()
                    self._startup_stream_buffered_samples = 0
                    self._startup_stream_overflow = False
                if getattr(self, "_vad", None) is not None:
                    self._vad.reset()

            # Ensure any previous stream is cleanly closed so the mic is never held open when idle
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            target_device = device if device is not None else config.selected_mic_device
            target_sr = int(getattr(config, "sample_rate", 16000) or 16000)
            target_ch = 1
            stream = None

            # 1. Attempt native 16000Hz 1ch capture directly (eliminates heavy CPU resampling)
            kwargs = {
                "samplerate": target_sr,
                "channels": target_ch,
                "dtype": "float32",
                "blocksize": 1024,
                "callback": self._audio_callback,
            }
            if target_device is not None:
                kwargs["device"] = target_device

            try:
                stream = sd.InputStream(**kwargs)
                self._native_sr = target_sr
                self._native_ch = target_ch
            except Exception as e:
                # Handle stale/disconnected configured device
                if target_device is not None:
                    if not _stale_device_warned_once:
                        _stale_device_warned_once = True
                        log.warning("[AUDIO] Configured mic '%s' unavailable (%s); resetting to system default device.", target_device, e)
                    kwargs.pop("device", None)
                    config.selected_mic_device = None
                    try:
                        from voice_flow.storage import storage
                        storage.save_setting("selected_mic_device", None)
                    except Exception:
                        pass
                    # Retry at 16000Hz on default device
                    try:
                        stream = sd.InputStream(**kwargs)
                        self._native_sr = target_sr
                        self._native_ch = target_ch
                    except Exception:
                        stream = None

                # 2. If 16000Hz was rejected by the driver, query and use hardware default rate
                if stream is None:
                    try:
                        dev_info = sd.query_devices(kwargs.get("device") if kwargs.get("device") is not None else sd.default.device[0], kind="input")
                        hw_sr = int(dev_info.get("default_samplerate", 44100))
                        hw_ch = max(1, min(2, int(dev_info.get("max_input_channels", 1))))
                    except Exception:
                        hw_sr, hw_ch = 44100, 1
                    kwargs["samplerate"] = hw_sr
                    kwargs["channels"] = hw_ch
                    self._native_sr = hw_sr
                    self._native_ch = hw_ch
                    try:
                        stream = sd.InputStream(**kwargs)
                    except Exception as e2:
                        log.error("[AUDIO] Failed to open input stream at hardware rate (%d Hz): %s", hw_sr, e2)
            if stream is None:
                log.error("[AUDIO] Failed to start input stream", exc_info=True)
                with self._lock:
                    self._recording = False
                return False
            with self._lock:
                self._recording = True
            try:
                stream.start()
            except Exception as e:
                # start() failing after construction must not leave the
                # recorder flagged as recording with no stream — the next
                # start() would early-return True and dictation would capture
                # nothing until process restart.
                log.error("[AUDIO] Input stream failed to start: %s", e)
                try:
                    stream.close()
                except Exception:
                    pass
                with self._lock:
                    self._recording = False
                return False
            self._stream = stream
            log.info("[AUDIO] Started hardware input stream (%d Hz, %d ch)", self._native_sr, self._native_ch)
            return True

    def stop(self) -> NDArray[np.float32]:
        """Stop recording and return the resampled 16kHz 1-D float32 audio array."""
        audio, _tail, _overlap = self._stop_capture(take_open_chunk=False)
        return audio

    def stop_and_take_open_chunk(self) -> tuple[NDArray[np.float32], NDArray[np.float32] | None, float]:
        """Quiesce capture, then return complete audio and its final stream tail.

        The input stream is stopped before the tail is copied, so a late device
        callback cannot race the terminal chunk harvest.  The full recording
        and tail intentionally come from separate buffers: the former remains
        the lossless whole-recording recovery path.
        """
        return self._stop_capture(take_open_chunk=True)

    def _stop_capture(self, *, take_open_chunk: bool) -> tuple[NDArray[np.float32], NDArray[np.float32] | None, float]:
        """Quiesce device callbacks, close the microphone stream, and atomically snapshot capture buffers."""
        with self._lifecycle_lock:
            with self._lock:
                stream = getattr(self, "_stream", None)
                self._stream = None

            # Stop and close the hardware stream outside _lock so no deadlock can occur
            # with any active audio callback. Closing the stream releases the Windows
            # microphone device completely, so the taskbar mic icon turns off.
            if stream is not None:
                try:
                    stream.stop()
                except Exception as e:
                    log.debug("[AUDIO] Error stopping stream: %s", e)
                try:
                    stream.close()
                except Exception as e:
                    log.debug("[AUDIO] Error closing stream: %s", e)

            with self._lock:
                # stop() quiesces callbacks. Until it returns, the driver's
                # final frame still belongs to this recording and its stream.
                self._recording = False
                self._level = 0.0
                # Bare instances (object.__new__) may predate the streaming chunk
                # state — materialize it instead of raising.
                chunk_list = getattr(self, "_chunk", None)
                if chunk_list is None:
                    chunk_list = self._chunk = []
                tail = None
                tail_overlap = 0.0
                if take_open_chunk and chunk_list:
                    tail = np.concatenate(chunk_list, axis=0)
                    tail_overlap = float(getattr(self, "_chunk_overlap_prefix_seconds", 0.0) or 0.0)
                chunk_list.clear()
                self._chunk_start_mono = None
                self._last_voice_mono = None
                self._chunk_voice_samples = 0
                self._chunk_overlap_prefix_seconds = 0.0
                if not self._buffer:
                    return np.array([], dtype=np.float32), tail, tail_overlap
                raw = np.concatenate(self._buffer, axis=0)
                self._buffer.clear()

        # Convert multi-channel to 1D mono
        if raw.ndim > 1:
            mono = np.mean(raw, axis=1).astype(np.float32)
        else:
            mono = raw.flatten().astype(np.float32)

        if mono.size == 0:
            return np.array([], dtype=np.float32), tail, tail_overlap

        # Environmental Noise Gate: only reject true near-silence (muted mic / dead air).
        # Faint speech from ~10ft away typically arrives at ~0.0010 - 0.0030 peak;
        # the gate is calibrated to 0.0008 so distant speech is retained for enhancement.
        max_amp = float(np.max(np.abs(mono)))
        if max_amp < 0.0008:
            log.info("[AUDIO] Peak amplitude (%.4f) below near-silence gate (0.0008); nothing captured.", max_amp)
            return np.array([], dtype=np.float32), tail, tail_overlap

        # Resample from native sample rate to 16000 Hz for Whisper
        target_sr = config.sample_rate  # 16000
        if self._native_sr != target_sr:
            try:
                resampled = sig.resample_poly(mono, target_sr, self._native_sr).astype(np.float32)
                log.info("[AUDIO] Resampled %d samples from %d Hz -> 16000 Hz (%d samples)", len(mono), self._native_sr, len(resampled))
                return resampled, tail, tail_overlap
            except Exception as e:
                log.warning("Polyphase resample failed (%s), discarding unusable audio buffer", e)
                return np.array([], dtype=np.float32), tail, tail_overlap
        return mono, tail, tail_overlap

    def cancel(self) -> None:
        """Stop recording and discard the buffer."""
        self.stop()

    def close(self) -> None:
        """Explicitly stop and tear down the hardware audio stream."""
        with self._lifecycle_lock:
            with self._lock:
                self._recording = False
                self._level = 0.0
                stream = getattr(self, "_stream", None)
                self._stream = None
            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass

    def begin_stream_input_buffering(self) -> None:
        """Buffer initial capture until the session's stream is armed.

        This must run before ``start``.  It intentionally retains copies of
        callback data so provider setup cannot clip the first spoken words.
        """
        with self._lock:
            self._buffer_stream_input = True
            self._pending_live_frames = []
            self._pending_closed_chunks = []
            self._pending_stream_events = []
            self._startup_stream_buffered_samples = 0
            self._startup_stream_overflow = False

    def flush_stream_input_buffer(self) -> None:
        """Replay startup frames and chunks after the provider is ready."""
        with self._lock:
            frames = self._pending_live_frames
            chunks = self._pending_closed_chunks
            self._pending_live_frames = []
            self._pending_closed_chunks = []
            self._buffer_stream_input = False
            frame_sink = self.on_audio_frame
            native_sr = self._native_sr
        # Invoke consumers outside the recorder lock. They may enqueue work
        # or synchronously fail, neither of which may stall mic callbacks.
        if frame_sink is not None:
            for frame in frames:
                try:
                    frame_sink(frame, native_sr)
                except Exception:
                    log.exception("Buffered live audio intake failed; full recording retained")
        for chunk, overlap_prefix_seconds in chunks:
            try:
                self._emit_closed_chunk(chunk, overlap_prefix_seconds)
            except Exception as exc:
                log.debug("[AUDIO] Buffered chunk dispatch failed: %s", exc)

    def discard_stream_input_buffer(self) -> None:
        """Forget a startup buffer when stream setup fails or is cancelled."""
        with self._lock:
            self._buffer_stream_input = False
            self._pending_live_frames = []
            self._pending_closed_chunks = []

    def take_open_chunk(self) -> NDArray[np.float32] | None:
        """Return the still-open streaming chunk (native rate) and reset chunk
        state, without touching the main buffer. Called at dictation finish
        BEFORE stop() so the tail chunk can be transcribed too."""
        with self._lock:
            chunk_list = getattr(self, "_chunk", None)
            if chunk_list is None:
                chunk_list = self._chunk = []
            if not chunk_list:
                self._chunk_start_mono = None
                self._last_voice_mono = None
                return None
            chunk = np.concatenate(chunk_list, axis=0)
            chunk_list.clear()
            self._chunk_start_mono = None
            self._last_voice_mono = None
            self._chunk_voice_samples = 0
            self._chunk_overlap_prefix_seconds = 0.0
            return chunk

    @staticmethod
    def save_wav(audio: NDArray[np.float32], path: str) -> None:
        """Save a float32 audio array as a 16-bit PCM WAV file."""
        safe_audio = np.nan_to_num(np.asarray(audio, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        audio_clipped = np.clip(safe_audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(config.sample_rate)
            wf.writeframes(audio_int16.tobytes())

    # -- internal --

    def _emit_closed_chunk(self, chunk: NDArray[np.float32], overlap_prefix_seconds: float = 0.0) -> None:
        """Dispatch without requiring older two-argument callback consumers.

        The overlap is metadata, never inferred from similar transcript words:
        only the stream collector may remove a verified forced-boundary repeat.
        """
        callback = self.on_chunk_closed
        if callback is None:
            return
        try:
            callback(chunk, self._native_sr, overlap_prefix_seconds=overlap_prefix_seconds)
        except TypeError as exc:
            if "overlap_prefix_seconds" not in str(exc):
                raise
            callback(chunk, self._native_sr)

    def _audio_callback(
        self,
        indata: NDArray[np.float32],
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Called by sounddevice for each audio block."""
        with self._lock:
            if not self._recording:
                return
            # Device drivers should provide finite float32 samples, but a
            # transient NaN/Inf must not poison the level meter, silence split,
            # or the archived buffer when a driver misbehaves.
            safe_indata = np.nan_to_num(indata, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
            self._buffer.append(safe_indata.copy())
            frame_sink = getattr(self, "on_audio_frame", None)
            if getattr(self, "_buffer_stream_input", False):
                pending_frames = getattr(self, "_pending_live_frames", None)
                if pending_frames is None:
                    pending_frames = self._pending_live_frames = []
                pending_frames.append(safe_indata.copy())
            elif frame_sink is not None:
                try:
                    frame_sink(safe_indata, self._native_sr)
                except Exception:
                    log.exception("Live audio intake failed; full recording retained")
            rms = float(np.sqrt(np.mean(safe_indata**2)))
            self._level = min(1.0, rms / 0.08)

            # Streaming chunk splitting: accumulate into the open chunk; when
            # the mic has been quiet for SPLIT_SILENCE_SECONDS (or the chunk
            # hit the hard cap), close it and hand it to the streamer. The
            # callback never transcribes — dispatch happens in VoiceFlowApp.
            now_mono = time.monotonic()
            if getattr(self, "_chunk", None) is None:
                self._chunk = []
                self._chunk_start_mono = None
                self._last_voice_mono = None
                self._chunk_voice_samples = 0
            self._chunk.append(safe_indata.copy())
            if self._chunk_start_mono is None:
                self._chunk_start_mono = now_mono
            chunk_secs = now_mono - self._chunk_start_mono
            vad = getattr(self, "_vad", None)
            if vad is not None:
                is_active, is_hangover = vad.update(safe_indata, rms)
            else:
                is_active = (rms >= _SILENCE_RMS)
                is_hangover = False

            if is_active:
                self._last_voice_mono = now_mono
                self._chunk_voice_samples += frames
            elif is_hangover:
                self._last_voice_mono = now_mono
            voice_secs = self._chunk_voice_samples / max(1, self._native_sr)
            silence_secs = (now_mono - self._last_voice_mono) if self._last_voice_mono is not None else 0.0
            split_silence = getattr(self, "split_silence_seconds", SPLIT_SILENCE_SECONDS)
            max_chunk = getattr(self, "max_chunk_seconds", MAX_CHUNK_SECONDS)
            reached_end = silence_secs >= split_silence
            hit_cap = chunk_secs >= max_chunk
            if reached_end or hit_cap:
                # Sub-threshold chunks (a brief "done" between long utterances)
                # are NOT discarded on a silence split: their audio stays in the
                # open chunk so the words ride into the next dispatch or the
                # tail harvest. Dropping them lost real words whenever other
                # chunks already produced text (the whole-buffer fallback never
                # ran).
                keep_for_next = voice_secs > 0 and not hit_cap and voice_secs < MIN_CHUNK_SECONDS
                if keep_for_next:
                    # Restart the silence/cap windows; keep the voice counter so
                    # the retained audio counts toward the next dispatch gate.
                    self._chunk_start_mono = now_mono
                    self._last_voice_mono = None
                    return
                chunk = np.concatenate(self._chunk, axis=0)
                # Metadata belongs to the chunk being dispatched.  A forced
                # split below seeds a distinct prefix for the following one.
                overlap_prefix_seconds = float(getattr(self, "_chunk_overlap_prefix_seconds", 0.0) or 0.0)
                if hit_cap:
                    overlap_samples = min(
                        chunk.shape[0],
                        max(0, int(round(FORCED_CHUNK_OVERLAP_SECONDS * self._native_sr))),
                    )
                    overlap = chunk[-overlap_samples:].copy() if overlap_samples else None
                    self._chunk = [overlap] if overlap is not None and overlap.size else []
                    # Start the new chunk's age at its overlap length, so each
                    # forced dispatch adds roughly MAX_CHUNK_SECONDS of fresh
                    # speech instead of firing again after the overlap alone.
                    next_overlap_seconds = overlap_samples / max(1, self._native_sr)
                    self._chunk_start_mono = now_mono - next_overlap_seconds
                    self._last_voice_mono = now_mono if overlap_samples else None
                    self._chunk_voice_samples = overlap_samples
                    self._chunk_overlap_prefix_seconds = next_overlap_seconds
                else:
                    self._chunk.clear()
                    self._chunk_start_mono = None
                    self._last_voice_mono = None
                    self._chunk_voice_samples = 0
                    self._chunk_overlap_prefix_seconds = 0.0
                # A silence split below MIN_CHUNK_SECONDS already returned above
                # (keep_for_next), so reaching here means either a normal
                # dispatch or a hard cap. A capped chunk that carries any voice
                # must be dispatched rather than dropped: dropping it lost the
                # words whenever sibling chunks already produced text and the
                # whole-buffer fallback therefore never ran.
                if voice_secs > 0 and self.on_chunk_closed is not None:
                    if getattr(self, "_buffer_stream_input", False):
                        pending_chunks = getattr(self, "_pending_closed_chunks", None)
                        if pending_chunks is None:
                            pending_chunks = self._pending_closed_chunks = []
                        pending_chunks.append((chunk, overlap_prefix_seconds))
                    else:
                        try:
                            self._emit_closed_chunk(chunk, overlap_prefix_seconds)
                        except Exception as exc:
                            log.debug("[AUDIO] Chunk dispatch failed: %s", exc)
