"""NVIDIA Nemotron Speech-to-Text GGUF inference engine for Voice Flow.

Supports local quantized (Q8_0) GGUF models:
  - nvidia/nemotron-speech-streaming-en-0.6b (FastConformer English 0.6B)
  - nvidia/nemotron-3.5-asr-streaming-0.6b (FastConformer Multilingual 0.6B)

Provides:
  1. Thread-safe singleton in-memory caching to eliminate reload latencies.
  2. Persistent isolated C ABI execution via nemo_speech_asr_c.dll (< 40ms load, < 500ms inference).
  3. Direct GGUF header and metadata parsing (vocabulary, mel filterbank, params).
  4. High-speed vectorized log-mel feature extraction (~15-30ms for 5s of audio).
  5. Native CLI execution when nemo-speech binary is installed.
  6. Automatic punctuation and capitalization handling natively.
"""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from collections import deque
import io
import logging
import os
import queue
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
import wave
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from voice_flow import paths
from voice_flow.local_model_resources import (
    LOCAL_MODEL_IDLE_SECONDS,
    acquire_model_use,
    cleanup_is_forced,
    cleanup_requested,
    notify_models_available,
    register_idle_cleanup,
)
from voice_flow.voice_enhance import LiveSpeechEnhancer

log = logging.getLogger(__name__)

# Singleton cache for loaded Nemotron engines: model_path_str -> NemotronGGUFEngine
_NEMOTRON_CACHE: dict[str, NemotronGGUFEngine] = {}
_CACHE_LOCK = threading.Lock()
# Native construction can reserve several GiB before an engine is published.
# Serialize that cold path separately from the short cache registry lock.
_CONSTRUCTION_LOCK = threading.Lock()


def _evict_idle_engines(now: float) -> bool:
    if not _CACHE_LOCK.acquire(blocking=False):
        return False
    try:
        candidates = tuple(_NEMOTRON_CACHE.items())
    finally:
        _CACHE_LOCK.release()
    busy = False
    force = cleanup_is_forced("speech")
    for key, engine in candidates:
        release = getattr(engine, "release_if_idle", None)
        if callable(release) and release(now, force=force):
            with _CACHE_LOCK:
                if _NEMOTRON_CACHE.get(key) is engine:
                    _NEMOTRON_CACHE.pop(key, None)
            log.info("[NEMOTRON] Released inactive speech model memory")
        elif cleanup_requested("speech"):
            busy = True
    return not busy

# Global C ABI dynamic library and loader state
_NEMO_DLL: ctypes.CDLL | None = None
_DLL_LOAD_ATTEMPTED: bool = False
_DLL_LOCK = threading.Lock()


# --- C ABI Structures matching NeMo-Speech.cpp (include/nemo_speech/asr.h) ---

from voice_flow.nemotron_abi import (
    _BackendConfig, _ModelConfig, _RecognizerConfig, _SpeechContext,
    _RecognitionOptions, _make_speech_context, _options_support_speech_context,
    _attach_speech_context,
    NEMOTRON_CONTEXT_BOOST,
)
from voice_flow.nemotron_worker_client import NativeASRClient, NativeASRWorkerError, NativeASRBusyError

# Trailing silence appended before stream_finish and before a whole-recording
# decode. A tight key release otherwise leaves the last word without the
# right context the recognizer needs ("Uzair" -> "Uz. Ar.", "Priya" -> "Priy");
# 500 ms fixed it in real-model tests.
TRAILING_SILENCE_SECONDS = 0.5
# Whole-recording decodes run through the warmed cache-aware (streaming)
# encoder. The native library also has an offline path
# (nemo_speech_asr_recognize_f32), but it allocates a second encoder (~+750 MB
# worker RSS measured on the q8_0 model) and did not merge stutter false
# starts any better in tests, so it is not used. A longer end-of-utterance
# history keeps short hesitations from being finalized as their own
# punctuated segments in that whole-recording pass.
WHOLE_RECORDING_EOU_HISTORY_MS = 2000

_FAILED_MODELS: dict[str, NativeASRWorkerError] = {}
_FAILED_AT: dict[str, float] = {}
_RETRY_ACTIONS = deque(maxlen=16)
_FAILURE_LOCK = threading.Lock()


@contextmanager
def _bounded_lock(lock, deadline=None, cancelled=None, timeout=120.0):
    absolute = time.monotonic() + timeout
    while True:
        limit = deadline() if callable(deadline) else deadline
        if cancelled is not None and cancelled.is_set():
            raise NativeASRBusyError("Speech operation cancelled; recording retained")
        if time.monotonic() >= min(absolute, limit if limit is not None else absolute):
            raise NativeASRBusyError("Speech operation deadline elapsed; recording retained")
        if lock.acquire(timeout=0.02):
            break
    try:
        yield
    finally:
        lock.release()


def retry_failed_model(model_ref, action):
    """Grant at most one retry for an explicit new capture/history action."""
    from voice_flow import downloadable_models
    spec = downloadable_models.get_model_spec(model_ref)
    model_file = (downloadable_models.get_models_dir() / spec["filename"]
                  if spec else Path(model_ref))
    key = str(model_file.resolve())
    with _FAILURE_LOCK:
        if any(old_key == key and old_action is action for old_key, old_action in _RETRY_ACTIONS):
            return False
        _RETRY_ACTIONS.append((key, action))
        if key not in _FAILED_MODELS:
            return True
        if time.monotonic() - _FAILED_AT.get(key, time.monotonic()) < 5.0:
            raise _FAILED_MODELS[key]
    if not _CONSTRUCTION_LOCK.acquire(blocking=False):
        raise NativeASRBusyError("Local speech worker is still closing; recording retained")
    try:
        with _CACHE_LOCK:
            engine = _NEMOTRON_CACHE.get(key)
        if engine is not None:
            if not engine.lock.acquire(blocking=False):
                raise NativeASRBusyError("Local speech worker is still closing; recording retained")
            try:
                if engine._active_streams:
                    raise NativeASRBusyError("Local speech stream is still closing; recording retained")
                engine.close()
            finally:
                engine.lock.release()
        with _CACHE_LOCK:
            _NEMOTRON_CACHE.pop(key, None)
        with _FAILURE_LOCK:
            _FAILED_MODELS.pop(key, None)
            _FAILED_AT.pop(key, None)
        return True
    finally:
        _CONSTRUCTION_LOCK.release()


def _find_nemo_speech_dll() -> Path | None:
    """Find native NeMo-Speech C ABI DLL/dylib (nemo_speech_asr_c) if available."""
    candidates = [
        paths.data_dir() / "bin" / "nemo_speech_asr_c.dll",
        paths.data_dir() / "bin" / "libnemo_speech_asr_c.dylib",
        paths.data_dir() / "bin" / "libnemo_speech_asr_c.so",
        paths.data_dir() / "models" / "nemo_speech_asr_c.dll",
        paths.data_dir() / "models" / "libnemo_speech_asr_c.dylib",
    ]
    try:
        from voice_flow import runtime_env

        r_root = runtime_env.runtime_root()
        if r_root:
            candidates.extend([
                r_root / "bin" / "nemo_speech_asr_c.dll",
                r_root / "bin" / "libnemo_speech_asr_c.dylib",
                r_root / "nemo" / "nemo_speech_asr_c.dll",
                r_root / "nemo" / "libnemo_speech_asr_c.dylib",
            ])
    except Exception:
        pass

    for c in candidates:
        if c.is_file():
            return c

    for name in ("nemo_speech_asr_c.dll", "libnemo_speech_asr_c.dylib", "libnemo_speech_asr_c.so"):
        exe_on_path = shutil.which(name)
        if exe_on_path:
            return Path(exe_on_path)
    return None


def _ensure_nemo_speech_binaries() -> Path | None:
    """Ensure nemo-speech Windows binaries are available, downloading if missing."""
    existing = _find_nemo_speech_dll()
    if existing:
        return existing

    if os.name != "nt":
        return None

    bin_dir = paths.data_dir() / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target_dll = bin_dir / "nemo_speech_asr_c.dll"
    if target_dll.is_file():
        return target_dll

    zip_url = "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.1.0/nemo-speech-0.1.0-windows-x86_64-cpu.zip"
    try:
        log.info("[NEMOTRON] Downloading NeMo-Speech native runtime (4.7MB)...")
        req = urllib.request.Request(zip_url, headers={"User-Agent": "VoiceFlow"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        for member in zf.infolist():
            if member.filename.startswith("bin/") and not member.is_dir():
                fname = Path(member.filename).name
                out_file = bin_dir / fname
                with zf.open(member) as sf, open(out_file, "wb") as df:
                    df.write(sf.read())
        log.info("[NEMOTRON] Successfully unpacked NeMo-Speech native runtime to %s", bin_dir)
        if target_dll.is_file():
            return target_dll
    except Exception as exc:
        log.warning("[NEMOTRON] Could not auto-download NeMo-Speech native runtime: %s", exc)

    return None


def get_nemo_dll():
    """Native loading is forbidden in the application process."""
    raise RuntimeError("Native ASR is owned by its isolated worker")


def is_nemotron_model(model_ref: str | None) -> bool:
    """Check if a model reference specifies an NVIDIA Nemotron local model."""
    if not model_ref:
        return False
    norm = str(model_ref).strip().lower()
    return "nemotron" in norm


def clear_engine_cache(model_ref: str | None = None) -> None:
    """Evict cached engine instance(s) from memory and release native recognizer handles."""
    with _FAILURE_LOCK:
        if model_ref is None:
            _FAILED_MODELS.clear()
            _FAILED_AT.clear()
        else:
            for key in tuple(_FAILED_MODELS):
                if str(model_ref).strip().lower() in key.lower():
                    _FAILED_MODELS.pop(key, None)
                    _FAILED_AT.pop(key, None)
    with _CACHE_LOCK:
        if model_ref is None:
            for eng in list(_NEMOTRON_CACHE.values()):
                try:
                    eng.close()
                except Exception:
                    pass
            _NEMOTRON_CACHE.clear()
            log.info("[NEMOTRON] Cleared all cached Nemotron engines")
        else:
            norm = str(model_ref).strip().lower()
            to_del = [k for k in _NEMOTRON_CACHE if norm in k.lower()]
            for k in to_del:
                eng = _NEMOTRON_CACHE.pop(k, None)
                if eng:
                    try:
                        eng.close()
                    except Exception:
                        pass
            if to_del:
                log.info("[NEMOTRON] Evicted engine for '%s'", model_ref)


class NemotronGGUFEngine:
    """Warm, thread-safe Nemotron ASR engine loaded from a local GGUF file."""

    def __init__(self, model_path: Path | str, spec: dict[str, Any] | None = None, *, deadline=None, cancelled=None) -> None:
        self.model_path = Path(model_path).resolve()
        self.spec = spec or {}
        self.model_id = self.spec.get("id") or self.model_path.stem
        self.model_name = self.spec.get("name") or self.model_path.name
        self.lock = threading.RLock()

        self._native = None
        self.fatal_error = None
        self._startup_deadline = deadline
        self._startup_cancelled = cancelled
        self._streams_idle = threading.Event()
        self._streams_idle.set()
        # Opaque worker token; never a native pointer in this process.
        self.rec_handle: ctypes.c_void_p = ctypes.c_void_p()

        # Parsed GGUF metadata & state
        self.metadata: dict[str, Any] = {}
        self.tensors: dict[str, tuple[list[int], int, int]] = {}  # name -> (dims, type, offset)
        self.vocab: list[str] = []
        self.blank_id: int = 1024
        self.preprocessor_fb: np.ndarray | None = None  # (128, 257) mel filterbank
        self.sample_rate: int = 16000
        self.n_fft: int = 512
        self.hop_length: int = 160  # 10ms at 16kHz
        self.win_length: int = 400  # 25ms at 16kHz
        self.num_features: int = 128
        self.preemph: float = 0.97
        self.data_start_offset: int = 0
        self._is_warm: bool = False
        self._active_streams = 0
        self._evict_when_idle = False
        self._last_used = time.monotonic()

        # Profiling stats
        self.last_latency_ms: float = 0.0
        self.total_transcriptions: int = 0
        self.total_audio_seconds: float = 0.0
        self.total_decode_seconds: float = 0.0

        self._load_and_warm()

    @property
    def is_warm(self) -> bool:
        return self._is_warm and self.fatal_error is None

    def _load_and_warm(self) -> None:
        """Parse GGUF header, index tensors, extract vocab & filterbank into RAM, and create C ABI handle."""
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Nemotron model file not found: {self.model_path}")

        file_size = self.model_path.stat().st_size
        if file_size < 1024 * 1024:
            raise ValueError(f"Nemotron model file too small or incomplete ({file_size} bytes): {self.model_path}")

        t0 = time.perf_counter()
        with open(self.model_path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                raise ValueError(f"Invalid GGUF magic in {self.model_path}: {magic}")

            version = struct.unpack("<I", f.read(4))[0]
            if version not in (2, 3):
                raise ValueError(f"Unsupported GGUF version {version} in {self.model_path}")

            tensor_count = struct.unpack("<Q", f.read(8))[0]
            kv_count = struct.unpack("<Q", f.read(8))[0]

            def _read_str() -> str:
                slen = struct.unpack("<Q", f.read(8))[0]
                return f.read(slen).decode("utf-8", errors="replace")

            def _skip_val(vtype: int) -> None:
                if vtype in (0, 1, 7):
                    f.seek(1, 1)
                elif vtype in (2, 3):
                    f.seek(2, 1)
                elif vtype in (4, 5, 6):
                    f.seek(4, 1)
                elif vtype in (10, 11, 12):
                    f.seek(8, 1)
                elif vtype == 8:
                    slen = struct.unpack("<Q", f.read(8))[0]
                    f.seek(slen, 1)
                elif vtype == 9:
                    atype = struct.unpack("<I", f.read(4))[0]
                    alen = struct.unpack("<Q", f.read(8))[0]
                    if atype == 8:
                        for _ in range(alen):
                            slen = struct.unpack("<Q", f.read(8))[0]
                            f.seek(slen, 1)
                    else:
                        sz = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}.get(atype, 1)
                        f.seek(alen * sz, 1)

            # Read KV metadata
            for _ in range(kv_count):
                key = _read_str()
                vtype = struct.unpack("<I", f.read(4))[0]
                if key == "asr.tokenizer.vocab":
                    atype = struct.unpack("<I", f.read(4))[0]
                    alen = struct.unpack("<Q", f.read(8))[0]
                    self.vocab = [_read_str() for _ in range(alen)]
                elif key == "asr.rnnt.blank_id":
                    self.blank_id = struct.unpack("<I", f.read(4))[0]
                elif key == "asr.preprocessor.sample_rate":
                    self.sample_rate = struct.unpack("<I", f.read(4))[0]
                elif key == "asr.preprocessor.n_fft":
                    self.n_fft = struct.unpack("<I", f.read(4))[0]
                elif key == "asr.preprocessor.features":
                    self.num_features = struct.unpack("<I", f.read(4))[0]
                elif key == "asr.preprocessor.preemph":
                    self.preemph = struct.unpack("<f", f.read(4))[0]
                elif key == "general.architecture":
                    self.metadata["architecture"] = _read_str()
                elif key == "general.name":
                    self.metadata["name"] = _read_str()
                elif key == "asr.tokenizer.type":
                    self.metadata["tokenizer_type"] = _read_str()
                elif key == "asr.tokenizer.spm_model":
                    # Current NeMo-Speech GGUFs embed the serialized
                    # SentencePiece proto separately from the readable vocab.
                    # The native RNNT word booster needs this proto to tokenize
                    # arbitrary user terms; a token list alone is insufficient.
                    self.metadata["tokenizer_spm_model_embedded"] = bool(_read_str())
                else:
                    _skip_val(vtype)

            # Read tensor index
            for _ in range(tensor_count):
                tname = _read_str()
                ndims = struct.unpack("<I", f.read(4))[0]
                dims = [struct.unpack("<Q", f.read(8))[0] for _ in range(ndims)]
                ttype = struct.unpack("<I", f.read(4))[0]
                offset = struct.unpack("<Q", f.read(8))[0]
                self.tensors[tname] = (dims, ttype, offset)

            # Alignment padding for tensor binary data (default 32 bytes)
            cur = f.tell()
            pad = (32 - (cur % 32)) % 32
            self.data_start_offset = cur + pad

            # Load filterbank if available.
            if "preprocessor.fb" in self.tensors:
                fb_dims, fb_type, fb_offset = self.tensors["preprocessor.fb"]
                f.seek(self.data_start_offset + fb_offset)
                fb_bytes = f.read(fb_dims[0] * fb_dims[1] * 4)
                self.preprocessor_fb = np.frombuffer(fb_bytes, dtype=np.float32).reshape(fb_dims[1], fb_dims[0])

        self.metadata["speech_context_supported"] = (
            self.metadata.get("tokenizer_type") == "sentencepiece_bpe"
            and self.metadata.get("tokenizer_spm_model_embedded", False)
        )
        if self.vocab and not self.metadata["speech_context_supported"]:
            log.info(
                "[NEMOTRON] This GGUF has token strings but no embedded SentencePiece model; "
                "native dictionary boosting is unavailable for this model."
            )

        dll_path = _ensure_nemo_speech_binaries()
        if dll_path is not None:
            from voice_flow import runtime_env
            try:
                self._native = NativeASRClient(str(dll_path), runtime_env.python_executable())
            except NativeASRWorkerError as exc:
                self._mark_native_failure(exc)
                raise
            created = self._native_call("create", deadline=self._startup_deadline,
                                        cancelled=self._startup_cancelled,
                                        dll_path=str(dll_path), model_path=str(self.model_path))
            if created["status"] == 0 and created["handle"]:
                self.rec_handle = ctypes.c_void_p(created["handle"])
                log.info("[NEMOTRON] Created warm isolated native recognizer")
            else:
                self._native.close()
                self._native = None
                error = NativeASRWorkerError(f"Local speech initialization failed (status {created['status']}); recording retained")
                self._mark_native_failure(error)
                raise error

        load_ms = (time.perf_counter() - t0) * 1000
        # Run one short silent pass so the first real dictation does not pay
        # first-inference cost (weight paging, graph/allocator setup) inside its
        # release drain. This is what made the very first stream of a session
        # noticeably slower than every later one.
        try:
            self._warm_inference_pass()
        except NativeASRWorkerError:
            raise
        except Exception as exc:
            log.debug("[NEMOTRON] Warm inference pass skipped: %s", exc)
        self._is_warm = True
        log.info(
            "[NEMOTRON] Loaded & warmed model '%s' (%d tensors, %d vocab, %.1fMB) in %.1fms (c_abi=%s)",
            self.model_name,
            len(self.tensors),
            len(self.vocab),
            file_size / (1024.0 * 1024.0),
            load_ms,
            bool(self.rec_handle.value),
        )

    def _mark_native_failure(self, exc):
        self.fatal_error = exc
        self._is_warm = False
        self.rec_handle = ctypes.c_void_p()
        with _FAILURE_LOCK:
            _FAILED_MODELS[str(self.model_path)] = exc
            _FAILED_AT[str(self.model_path)] = time.monotonic()

    def _native_call(self, op, **values):
        if self.fatal_error:
            raise self.fatal_error
        try:
            return self._native.call(op, **values)
        except NativeASRWorkerError as exc:
            self._mark_native_failure(exc)
            raise

    def _warm_inference_pass(self) -> None:
        if self._native is not None and self.rec_handle.value:
            response = self._native_call("warm", handle=self.rec_handle.value, streaming=True,
                                         deadline=self._startup_deadline, cancelled=self._startup_cancelled)
            if response["status"] != 0:
                error = NativeASRWorkerError(f"Local speech warmup failed (status {response['status']}); recording retained")
                self._mark_native_failure(error)
                self._native.close()
                self._native = None
                raise error

    def close(self) -> None:
        with self.lock:
            if self._active_streams:
                self._evict_when_idle = True
                return
            if self._native is not None:
                self._native.close()
                self._native = None
            self.rec_handle = ctypes.c_void_p()
            self._is_warm = False

    def acquire_stream(self) -> None:
        with self.lock:
            self._active_streams += 1
            self._streams_idle.clear()
            self._last_used = time.monotonic()

    def release_stream(self) -> None:
        should_close = False
        with self.lock:
            self._active_streams = max(0, self._active_streams - 1)
            if not self._active_streams:
                self._streams_idle.set()
            self._last_used = time.monotonic()
            should_close = self._active_streams == 0 and self._evict_when_idle
        if should_close:
            self.close()
        notify_models_available("speech")

    def realtime_factor(self) -> float | None:
        """Observed whole-recording decode seconds per audio second, if known."""
        audio = float(getattr(self, "total_audio_seconds", 0.0) or 0.0)
        if audio < 1.0:
            return None
        return float(getattr(self, "total_decode_seconds", 0.0) or 0.0) / audio

    def touch(self) -> None:
        # Advisory recency only: stream/model leases own lifetime. Cache getters
        # must not wait behind an in-flight native call while holding _CACHE_LOCK.
        self._last_used = time.monotonic()

    def release_if_idle(self, now: float, *, force: bool = False) -> bool:
        """Release unused native arenas without interrupting active speech."""
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self._active_streams:
                return False
            if not force and now - getattr(self, "_last_used", now) < LOCAL_MODEL_IDLE_SECONDS:
                return False
            self.close()
            return True
        finally:
            self.lock.release()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def extract_mel_features(self, audio: np.ndarray) -> np.ndarray:
        """Extract 128-dim log mel spectrogram matching FastConformer preprocessor."""
        if audio.size == 0:
            return np.zeros((0, self.num_features), dtype=np.float32)

        wav = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        preemph_wav = np.append(wav[0], wav[1:] - self.preemph * wav[:-1])

        if len(preemph_wav) < self.win_length:
            pad_len = self.win_length - len(preemph_wav)
            preemph_wav = np.pad(preemph_wav, (0, pad_len), mode="constant")

        num_frames = 1 + (len(preemph_wav) - self.win_length) // self.hop_length
        if num_frames <= 0:
            return np.zeros((0, self.num_features), dtype=np.float32)

        window = np.hanning(self.win_length).astype(np.float32)
        shape = (num_frames, self.win_length)
        strides = (preemph_wav.strides[0] * self.hop_length, preemph_wav.strides[0])
        frames = np.lib.stride_tricks.as_strided(preemph_wav, shape=shape, strides=strides) * window

        stft = np.fft.rfft(frames, n=self.n_fft, axis=1)
        power_spec = (np.abs(stft) ** 2).astype(np.float32)

        if self.preprocessor_fb is not None and self.preprocessor_fb.shape == (self.num_features, 257):
            mel = np.dot(power_spec, self.preprocessor_fb.T)
        else:
            mel = power_spec[:, :self.num_features]

        log_mel = np.log(np.maximum(mel, 1e-5)).astype(np.float32)
        return log_mel

    def _find_nemo_speech_executable(self) -> Path | None:
        """Find native NeMo-Speech.cpp CLI executable if available."""
        exe_on_path = shutil.which("nemo-speech")
        if exe_on_path:
            return Path(exe_on_path)

        candidates = [
            paths.data_dir() / "bin" / "nemo-speech.exe",
            paths.data_dir() / "bin" / "nemo-speech",
            paths.data_dir() / "models" / "nemo-speech.exe",
            paths.data_dir() / "models" / "nemo-speech",
            self.model_path.parent / "nemo-speech.exe",
        ]
        try:
            from voice_flow import runtime_env

            r_root = runtime_env.runtime_root()
            if r_root:
                candidates.extend([
                    r_root / "bin" / "nemo-speech.exe",
                    r_root / "bin" / "nemo-speech",
                    r_root / "nemo" / "nemo-speech.exe",
                ])
        except Exception:
            pass

        for c in candidates:
            if c.is_file():
                return c
        return None

    def _transcribe_native_cli(self, audio: np.ndarray, exe_path: Path, deadline: float | None = None) -> str | None:
        """Transcribe audio using native nemo-speech executable CLI."""
        temp_wav = Path(tempfile.gettempdir()) / f"vf_nemo_{os.getpid()}_{time.time_ns()}.wav"
        try:
            scaled = np.clip(audio, -1.0, 1.0)
            int_pcm = (scaled * 32767.0).astype(np.int16)
            with wave.open(str(temp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(int_pcm.tobytes())

            timeout = 30.0
            if deadline is not None:
                remaining = max(0.1, deadline - time.monotonic())
                timeout = min(timeout, remaining)

            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            cmd = [str(exe_path), "transcribe", str(temp_wav), "--model", str(self.model_path), "--quiet"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=creation_flags,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
            log.warning("[NEMOTRON] CLI error (code %d): %s", proc.returncode, proc.stderr.strip()[:200])
            return None
        except Exception as exc:
            log.warning("[NEMOTRON] CLI execution exception: %s", exc)
            return None
        finally:
            try:
                if temp_wav.is_file():
                    temp_wav.unlink()
            except OSError:
                pass

    def decode_tokens(self, token_ids: list[int]) -> str:
        """Reconstruct plain text with spaces and punctuation from SentencePiece tokens."""
        pieces: list[str] = []
        for tid in token_ids:
            if 0 <= tid < len(self.vocab):
                token = self.vocab[tid]
                if token not in ("<unk>", "<pad>", "<s>", "</s>", "<blank>"):
                    pieces.append(token)
        raw = "".join(pieces)
        clean = raw.replace("\u2581", " ").strip()
        return clean

    def _transcribe_segment(self, wav_segment, language=None, vocabulary=None, deadline=None) -> str:
        if self.fatal_error:
            raise self.fatal_error
        if self._native is None or not self.rec_handle.value:
            return ""
        lang = language or self.spec.get("default_language")
        if not lang or lang == "multilingual":
            from voice_flow.config import config
            lang = getattr(config, "language", "en") or "en"
        # Reuse the warmed cache-aware encoder instead of allocating a
        # separate offline encoder for whole-recording recovery.
        response = self._native_call(
            "recognize", handle=self.rec_handle.value,
            streaming=True,
            language=lang if lang != "multilingual" else None,
            vocabulary=tuple(vocabulary or ()) if self.metadata.get("speech_context_supported", False) else (),
            audio=np.ascontiguousarray(wav_segment, dtype=np.float32).tobytes(),
            count=len(wav_segment), rate=self.sample_rate, deadline=deadline,
            stop_history_eou_ms=WHOLE_RECORDING_EOU_HISTORY_MS,
        )
        if response.get("busy"):
            raise NativeASRBusyError("Previous speech stream is still closing; recording retained")
        result = response.get("result")
        if response.get("status") != 0 or not isinstance(result, dict) or result.get("final") is not True:
            # A failed later segment must abort the whole recording rather
            # than allowing the long-recording loop to publish earlier text.
            raise NativeASRWorkerError("Local speech recognition incomplete (recognize_incomplete); recording retained")
        return result["text"].decode("utf-8", errors="replace").strip()

    def transcribe(
        self,
        audio: np.ndarray,
        is_chunk: bool = False,
        deadline: float | None = None,
        vocabulary: list[str] | None = None,
        language: str | None = None,
    ) -> str:
        """Transcribe audio buffer with minimal latency (< 500ms warm in-process)."""
        if audio is None or audio.size == 0:
            return ""

        duration = len(audio) / float(self.sample_rate)
        if duration < 0.15:
            return ""

        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak < 0.002:
            return ""

        resolved_lang = language or self.spec.get("default_language")
        if not resolved_lang or resolved_lang == "multilingual":
            try:
                from voice_flow.config import config
                resolved_lang = getattr(config, "language", "en") or "en"
            except Exception:
                resolved_lang = "en"

        t0 = time.perf_counter()
        result = ""

        wav = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0)
        if wav.dtype != np.float32:
            wav = wav.astype(np.float32, copy=False)
        # Whole recordings end with padded silence so a tight release keeps
        # the last word; only the final decoded segment receives it.
        tail_pad = (
            np.zeros(int(TRAILING_SILENCE_SECONDS * self.sample_rate), dtype=np.float32)
            if not is_chunk and TRAILING_SILENCE_SECONDS > 0 else None
        )

        if self.fatal_error:
            raise self.fatal_error
        c_abi_available = self._native is not None and bool(self.rec_handle.value)
        if c_abi_available:
            limit = deadline if deadline is not None else time.monotonic() + 120.0
            while not self._streams_idle.wait(0.02):
                if self.fatal_error:
                    raise self.fatal_error
                if time.monotonic() >= limit:
                    raise NativeASRBusyError("Previous speech stream is still closing; recording retained")

        if c_abi_available:
            with _bounded_lock(self.lock, deadline):
                self._last_used = time.monotonic()
                # If audio is short or is a stream chunk, transcribe directly in-process
                if is_chunk or duration <= 12.0:
                    segment = wav if tail_pad is None else np.concatenate([wav, tail_pad])
                    result = self._transcribe_segment(segment, language=resolved_lang, vocabulary=vocabulary, deadline=deadline)
                else:
                    # Long whole-buffer audio (> 12.0s): chunk into ~4s segments at silence points
                    # to avoid FastConformer O(T^2) quadratic self-attention blowup on CPU.
                    chunk_samples = 4 * self.sample_rate
                    n_samples = len(wav)
                    offset = 0
                    transcripts: list[str] = []

                    while offset < n_samples:
                        remaining = n_samples - offset
                        if remaining <= chunk_samples:
                            seg = wav[offset:]
                            offset = n_samples
                        else:
                            # Search in [offset + 2.5s, offset + 4.0s] for the quietest window (split point)
                            search_start = offset + int(2.5 * self.sample_rate)
                            search_end = min(n_samples, offset + chunk_samples)
                            if search_end > search_start + 1600:
                                search_slice = np.abs(wav[search_start:search_end])
                                w_size = 1600  # 100ms
                                num_w = len(search_slice) // w_size
                                if num_w > 0:
                                    w_energies = [float(np.mean(search_slice[i * w_size:(i + 1) * w_size])) for i in range(num_w)]
                                    best_w = int(np.argmin(w_energies))
                                    split_point = search_start + best_w * w_size + (w_size // 2)
                                else:
                                    split_point = offset + chunk_samples
                            else:
                                split_point = offset + chunk_samples
                            # Keep a short final remainder in the preceding
                            # segment. The native decoder rejects segments
                            # below 200 ms, and silently skipping one after
                            # earlier text succeeded loses a trailing word.
                            min_segment_samples = int(0.2 * self.sample_rate)
                            if 0 < n_samples - split_point < min_segment_samples:
                                split_point = n_samples
                            seg = wav[offset:split_point]
                            offset = split_point

                        if offset >= n_samples and tail_pad is not None:
                            seg = np.concatenate([seg, tail_pad])
                        if seg.size >= int(0.2 * self.sample_rate):
                            part_txt = self._transcribe_segment(seg, language=resolved_lang, vocabulary=vocabulary, deadline=deadline)
                            if part_txt:
                                transcripts.append(part_txt)

                    result = " ".join(transcripts).strip()
        elif not result:
            # Strategy 2: Native CLI execution ONLY if C ABI handle is unavailable
            exe_path = self._find_nemo_speech_executable()
            if exe_path:
                cli_res = self._transcribe_native_cli(wav, exe_path, deadline=deadline)
                if cli_res is not None:
                    result = cli_res

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.last_latency_ms = elapsed_ms
        self.total_transcriptions += 1
        self.total_audio_seconds += duration
        self.total_decode_seconds = getattr(self, "total_decode_seconds", 0.0) + elapsed_ms / 1000.0

        log.info(
            "[NEMOTRON] Transcribed %.2fs audio in %.1fms (is_chunk=%s, warm=True): '%s'",
            duration,
            elapsed_ms,
            is_chunk,
            result[:60] if result else "<silent/speech>",
        )
        return result


def get_cached_nemotron_engine(model_ref_or_path: str | Path | None = None) -> NemotronGGUFEngine | None:
    """Retrieve an already warm singleton NemotronGGUFEngine without constructing a cold one."""
    from voice_flow import downloadable_models

    model_id_str = str(model_ref_or_path or "").strip()
    if not model_id_str or model_id_str.lower() in ("default", "none"):
        model_id_str = "nvidia/nemotron-speech-streaming-en-0.6b"

    spec = downloadable_models.get_model_spec(model_id_str)
    if not spec:
        path = Path(model_id_str)
        if path.is_file() and path.suffix.lower() == ".gguf":
            model_file = path
        else:
            return None
    else:
        model_file = downloadable_models.get_models_dir() / spec["filename"]

    if not model_file.is_file() or model_file.stat().st_size == 0:
        return None

    path_key = str(model_file.resolve())
    with _FAILURE_LOCK:
        if path_key in _FAILED_MODELS:
            raise _FAILED_MODELS[path_key]
    with _CACHE_LOCK:
        cached = _NEMOTRON_CACHE.get(path_key)
        if cached is not None and cached.is_warm:
            touch = getattr(cached, "touch", None)
            if callable(touch):
                touch()
            return cached
    return None


def get_nemotron_engine(model_ref_or_path: str | Path | None = None, *, deadline=None, cancelled=None) -> NemotronGGUFEngine | None:
    """Retrieve or instantiate a warm singleton NemotronGGUFEngine."""
    from voice_flow import downloadable_models

    model_id_str = str(model_ref_or_path or "").strip()
    if not model_id_str or model_id_str.lower() in ("default", "none"):
        model_id_str = "nvidia/nemotron-speech-streaming-en-0.6b"

    spec = downloadable_models.get_model_spec(model_id_str)
    if not spec:
        path = Path(model_id_str)
        if path.is_file() and path.suffix.lower() == ".gguf":
            model_file = path
        else:
            return None
    else:
        model_file = downloadable_models.get_models_dir() / spec["filename"]

    if not model_file.is_file() or model_file.stat().st_size == 0:
        log.warning("[NEMOTRON] Model file does not exist at %s", model_file)
        return None

    path_key = str(model_file.resolve())
    with _FAILURE_LOCK:
        if path_key in _FAILED_MODELS:
            raise _FAILED_MODELS[path_key]
    with _CACHE_LOCK:
        cached = _NEMOTRON_CACHE.get(path_key)
        if cached is not None and cached.is_warm:
            touch = getattr(cached, "touch", None)
            if callable(touch):
                touch()
            return cached

    replaced: list[NemotronGGUFEngine] = []
    with _bounded_lock(_CONSTRUCTION_LOCK, deadline, cancelled):
        with _FAILURE_LOCK:
            if path_key in _FAILED_MODELS:
                raise _FAILED_MODELS[path_key]
        # Another capture/stream worker may have completed the same cold load
        # while this caller waited. Recheck before reserving native memory.
        with _CACHE_LOCK:
            cached = _NEMOTRON_CACHE.get(path_key)
            if cached is not None and cached.is_warm:
                touch = getattr(cached, "touch", None)
                if callable(touch):
                    touch()
                return cached
        try:
            engine = NemotronGGUFEngine(model_file, spec=spec, deadline=deadline, cancelled=cancelled)
        except NativeASRWorkerError as exc:
            with _FAILURE_LOCK:
                _FAILED_MODELS[path_key] = exc
                _FAILED_AT.setdefault(path_key, time.monotonic())
            raise
        except Exception as exc:
            log.error("[NEMOTRON ERROR] Failed to load Nemotron engine from %s: %s", model_file, exc, exc_info=True)
            return None
        with _CACHE_LOCK:
            _NEMOTRON_CACHE[path_key] = engine
            for old_key, old_engine in list(_NEMOTRON_CACHE.items()):
                if old_key != path_key:
                    _NEMOTRON_CACHE.pop(old_key, None)
                    replaced.append(old_engine)
    # Closing a replaced recognizer can call native code; never do it while a
    # cache or construction lock is held.
    for old_engine in replaced:
        old_engine.close()
    register_idle_cleanup("nemotron", _evict_idle_engines, kind="speech")
    return engine


class NemotronStreamTranscriber:
    """Live isolated streaming ASR session using native NeMo-Speech C ABI.

    Audio frames from the microphone are queued and pushed incrementally into
    the C ABI stream (nemo_speech_asr_stream_push_f32). The FastConformer
    streaming encoder decodes concurrently in 160ms steps while the user speaks.
    Upon release, only the residual tail needs finishing, yielding transcripts
    in ~150-250ms instead of 3000ms+.
    """

    live_frames = True

    def __init__(self, vocabulary: tuple[str, ...] | list[str] = (), engine: NemotronGGUFEngine | None = None) -> None:
        self._vocabulary = tuple(vocabulary)
        self._engine = engine
        self._speech_context_refs: tuple[Any, ...] = ()
        self._queue: queue.Queue[tuple[np.ndarray, int] | None] = queue.Queue(maxsize=512)
        self._finish = threading.Event()
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._failed = False
        self.fatal_error = None
        self._text = ""
        self._accepted = 0
        self._deadline: float | None = None
        self._model_ref: str = ""
        self._worker_thread: threading.Thread | None = None
        self._model_lease = None
        # Native streaming context, opened by start_session.
        self._stream: Any = ctypes.c_void_p()

    def start_session(self, model_ref: str | None = None, deadline: float | None = None) -> None:
        self._model_ref = str(model_ref or "")
        self._deadline = deadline
        self._model_lease = acquire_model_use("speech")
        self._worker_thread = threading.Thread(target=self._run, name="vf-nemotron-stream", daemon=True)
        try:
            self._worker_thread.start()
        except Exception:
            if self._model_lease:
                self._model_lease.release()
                self._model_lease = None
            self._failed = True
            self._done.set()

    def _native_call(self, op, **values):
        return self._engine._native_call(op, deadline=lambda: self._deadline,
                                         cancelled=self._cancel, **values)

    def _open_stream(self, _client=None) -> bool:
        eng = self._engine
        lang = eng.spec.get("default_language") if eng.spec else None
        if not lang or lang == "multilingual":
            from voice_flow.config import config
            lang = getattr(config, "language", "en") or "en"
        response = self._native_call(
            "stream_open", handle=eng.rec_handle.value, streaming=True,
            language=lang if lang != "multilingual" else None,
            vocabulary=self._vocabulary if eng.metadata.get("speech_context_supported", False) else (),
        )
        self._stream = ctypes.c_void_p(response["handle"])
        return response["status"] == 0 and bool(response["handle"])

    def submit_frame(self, frame: np.ndarray, native_sr: int) -> None:
        if self._finish.is_set() or self._cancel.is_set() or self._done.is_set():
            return
        try:
            self._queue.put_nowait((frame.copy(), int(native_sr)))
            self._accepted += 1
        except queue.Full:
            self._failed = True
            self._cancel.set()

    def submit_native(self, *args: Any, **kwargs: Any) -> None:
        pass

    def end_session(self, deadline: float | None = None) -> None:
        if deadline is not None:
            self._deadline = deadline
        self._finish.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    def accepted_count(self) -> int:
        return self._accepted

    def pending_count(self) -> int:
        return int(not self._done.is_set())

    def had_failures(self) -> bool:
        if not self._failed and not self._cancel.is_set() and not self._done.is_set() and self._worker_thread:
            self._done.wait(0.05)
        return self._failed or self._cancel.is_set()

    def completed_successfully(self) -> bool:
        return self._done.is_set() and not self.had_failures() and bool(self._text)

    def collect(self, timeout: float = 3.0, deadline: float | None = None) -> str:
        remaining = max(0.0, timeout)
        for limit in (deadline, self._deadline):
            if limit is not None:
                remaining = min(remaining, max(0.0, limit - time.monotonic()))
        self._done.wait(remaining)
        return self._text if self._done.is_set() and not self.had_failures() else ""

    def discard(self) -> None:
        self._cancel.set()
        self._finish.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    def _expired(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline

    def _run(self) -> None:
        eng = self._engine
        stream = ctypes.c_void_p()
        stream_acquired = False
        committed_transcripts: list[str] = []
        interim_latest = ""
        last_sr = 0
        t0 = time.perf_counter()
        mic_profile = "auto"
        try:
            from voice_flow.storage import storage

            mic_profile = str(storage.get_setting("voice_flow_mic_profile", "auto") or "auto")
        except Exception:
            pass
        live_enhancer = LiveSpeechEnhancer(profile=mic_profile)
        try:
            if self._cancel.is_set() or self._expired():
                raise RuntimeError("Stream was cancelled before model loading")
            if eng is None:
                eng = get_nemotron_engine(self._model_ref, deadline=lambda: self._deadline, cancelled=self._cancel)
                self._engine = eng
            client = eng._native if eng is not None else None
            if self._cancel.is_set() or self._expired():
                raise RuntimeError("Stream was cancelled during model loading")
            if client is None or eng is None or not getattr(eng, "rec_handle", None) or not eng.rec_handle.value:
                raise RuntimeError("Native C ABI engine handle not available")
            with _bounded_lock(eng.lock, lambda: self._deadline, self._cancel):
                if not eng.rec_handle.value:
                    raise RuntimeError("Native recognizer was evicted before stream setup")
                eng.acquire_stream()
                stream_acquired = True
                self._stream = ctypes.c_void_p()
                if not self._open_stream(client):
                    stream = self._stream
                    raise RuntimeError("Native C ABI stream could not be opened")
            stream = self._stream

            while not self._cancel.is_set() and not self._expired():
                try:
                    item = self._queue.get(timeout=0.03)
                except queue.Empty:
                    if self._finish.is_set():
                        break
                    continue

                if item is None:
                    break

                frame, sr = item
                last_sr = sr
                if frame.ndim > 1:
                    frame = np.mean(frame, axis=1)
                mono = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
                if mono.dtype != np.float32:
                    mono = mono.astype(np.float32, copy=False)

                if mono.size > 0:
                    # Condition only the per-stream copy.  AudioRecorder keeps
                    # the complete raw frames for whole-recording recovery.
                    mono = live_enhancer.process(mono, sr)
                    response = self._native_call("stream_push_next", handle=stream.value,
                                                 audio=np.ascontiguousarray(mono).tobytes(),
                                                 count=len(mono), rate=int(sr))
                    if response["status"] != 0 and response.get("result") is None:
                        # next may report no result; only an explicit push error fails input.
                        if response.get("push_failed"):
                            raise RuntimeError("Audio frame was not accepted")
                    result = response.get("result")
                    if result:
                        t = result["text"].decode("utf-8", errors="replace").strip()
                        if result["final"]:
                            if t:
                                committed_transcripts.append(t)
                                interim_latest = ""
                        else:
                            interim_latest = t

            if self._cancel.is_set():
                raise RuntimeError("Stream was cancelled")
            if self._expired():
                if committed_transcripts or interim_latest:
                    log.warning("[NEMOTRON STREAM] Stream deadline elapsed, but harvesting %d transcripts", len(committed_transcripts))
                    if interim_latest and not committed_transcripts:
                        committed_transcripts.append(interim_latest)
                    self._text = " ".join(committed_transcripts).strip()
                    self._failed = True
                    return
                raise TimeoutError("Stream deadline elapsed before all audio was consumed")

            # Pad the tail so the last word gets right context before finish.
            if TRAILING_SILENCE_SECONDS > 0 and self._accepted:
                pad_sr = int(last_sr or 16000)
                pad = np.zeros(int(TRAILING_SILENCE_SECONDS * pad_sr), dtype=np.float32)
                response = self._native_call("stream_push_next", handle=stream.value,
                                             audio=pad.tobytes(), count=len(pad), rate=pad_sr)
                result = response.get("result")
                if result:
                    t = result["text"].decode("utf-8", errors="replace").strip()
                    if result["final"]:
                        if t:
                            committed_transcripts.append(t)
                            interim_latest = ""
                    elif t:
                        interim_latest = t

            # Finalize audio stream and drain tail
            t_finish = time.perf_counter()
            fin_st = self._native_call("stream_finish", handle=stream.value)["status"]
            if fin_st != 0:
                raise RuntimeError(f"Audio finalization failed (status {fin_st})")

            while True:
                if self._cancel.is_set():
                    self._failed = True
                    log.warning("[NEMOTRON STREAM] Stream cancelled during drain")
                    break
                if self._expired():
                    self._failed = True
                    log.warning("[NEMOTRON STREAM] Stream deadline elapsed during drain")
                    break
                response = self._native_call("stream_next", handle=stream.value)
                result = response.get("result")
                if response["status"] != 0 or result is None:
                    break
                t = result["text"].decode("utf-8", errors="replace").strip()
                if result["final"]:
                    if t:
                        committed_transcripts.append(t)
                        interim_latest = ""
                elif t:
                    interim_latest = t

            if interim_latest:
                # A final interim may contain words that the last committed
                # result does not (for example, "hello welcome" after a
                # committed "hello"). Preserve it for diagnostics, but never
                # publish it as a complete stream transcript: the caller must
                # recover from the full captured recording instead.
                if not committed_transcripts:
                    committed_transcripts.append(interim_latest)
                self._failed = True
                log.warning(
                    "[NEMOTRON STREAM] Stream finished with unfinalized interim text; requesting whole-recording recovery"
                )

            self._text = " ".join(committed_transcripts).strip()
            drain_ms = (time.perf_counter() - t_finish) * 1000
            total_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "[NEMOTRON STREAM] Done in %.1fms (release_drain=%.1fms, frames=%d): '%s'",
                total_ms,
                drain_ms,
                self._accepted,
                self._text[:60] if self._text else "<empty>",
            )
        except NativeASRWorkerError as exc:
            # Only a dead/poisoned worker is fatal for the recording. A soft
            # cancel/deadline (NativeASRBusyError) just ends this stream; the
            # worker stays alive so whole-recording recovery can still run.
            self.fatal_error = exc
            self._failed = True
            self._text = ""
        except NativeASRBusyError as exc:
            self._failed = True
            self._text = ""
            log.info("[NEMOTRON STREAM] Stream ended without a complete result (%s); whole-recording recovery owns the transcript", exc)
        except Exception as exc:
            if committed_transcripts or interim_latest:
                if interim_latest and not committed_transcripts:
                    committed_transcripts.append(interim_latest)
                self._text = " ".join(committed_transcripts).strip()
                # Keep partial text for diagnostics, but force the caller to
                # use whole-buffer fallback when any queued audio was lost.
                self._failed = True
                log.info(
                    "[NEMOTRON STREAM] Salvaged %d committed transcripts despite exception (%s): '%s'",
                    len(committed_transcripts),
                    exc,
                    self._text[:60],
                )
            else:
                self._failed = True
                log.warning("[NEMOTRON STREAM] Streaming session exception: %s; falling back to whole-buffer", exc)
        finally:
            if stream.value and eng is not None and eng._native is not None and not eng.fatal_error:
                try:
                    # Cleanup ignores user cancellation but remains bounded.
                    eng._native_call("stream_close", handle=stream.value, timeout=0.3)
                except NativeASRWorkerError as exc:
                    self.fatal_error = exc
                    self._failed = True
                except Exception:
                    pass
            self._speech_context_refs = ()
            if stream_acquired and eng is not None:
                eng.release_stream()
            lease = self._model_lease
            self._model_lease = None
            if lease is not None:
                lease.release()
            notify_models_available("speech")
            self._done.set()
