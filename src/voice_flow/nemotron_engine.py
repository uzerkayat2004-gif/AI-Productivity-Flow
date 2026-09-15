"""NVIDIA Nemotron Speech-to-Text GGUF inference engine for Voice Flow.

Supports local quantized (Q8_0) GGUF models:
  - nvidia/nemotron-speech-streaming-en-0.6b (FastConformer English 0.6B)
  - nvidia/nemotron-3.5-asr-streaming-0.6b (FastConformer Multilingual 0.6B)

Provides:
  1. Thread-safe singleton in-memory caching to eliminate reload latencies.
  2. Direct in-process C ABI execution via nemo_speech_asr_c.dll (< 40ms load, < 500ms inference).
  3. Direct GGUF header and metadata parsing (vocabulary, mel filterbank, params).
  4. High-speed vectorized log-mel feature extraction (~15-30ms for 5s of audio).
  5. Native CLI execution when nemo-speech binary is installed.
  6. Automatic punctuation and capitalization handling natively.
"""
from __future__ import annotations

import ctypes
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

log = logging.getLogger(__name__)

# Singleton cache for loaded Nemotron engines: model_path_str -> NemotronGGUFEngine
_NEMOTRON_CACHE: dict[str, NemotronGGUFEngine] = {}
_CACHE_LOCK = threading.Lock()

# Global C ABI dynamic library and loader state
_NEMO_DLL: ctypes.CDLL | None = None
_DLL_LOAD_ATTEMPTED: bool = False
_DLL_LOCK = threading.Lock()


# --- C ABI Structures matching NeMo-Speech.cpp (include/nemo_speech/asr.h) ---

class _BackendConfig(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_size_t),
        ("gpu", ctypes.c_int32),
    ]


class _ModelConfig(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_size_t),
        ("path", ctypes.c_char_p),
        ("name", ctypes.c_char_p),
    ]


class _RecognizerConfig(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_size_t),
        ("backend", ctypes.POINTER(_BackendConfig)),
        ("model", ctypes.POINTER(_ModelConfig)),
        ("streaming", ctypes.c_void_p),
        ("decoder", ctypes.c_void_p),
        ("vad", ctypes.c_void_p),
        ("endpointing", ctypes.c_void_p),
        ("postproc", ctypes.c_void_p),
        ("diar", ctypes.c_void_p),
        ("batching", ctypes.c_void_p),
    ]


class _RecognitionOptions(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_size_t),
        ("request_id", ctypes.c_char_p),
        ("language_code", ctypes.c_char_p),
        ("interim_results", ctypes.c_bool),
        ("enable_word_time_offsets", ctypes.c_bool),
        ("enable_automatic_punctuation", ctypes.c_bool),
        ("verbatim_transcripts", ctypes.c_bool),
        ("profanity_filter", ctypes.c_bool),
        ("stop_history_eou_ms", ctypes.c_int32),
        ("speech_contexts", ctypes.c_void_p),
        ("speech_context_count", ctypes.c_size_t),
        ("max_alternatives", ctypes.c_int32),
        ("enable_speaker_diarization", ctypes.c_bool),
        ("max_speaker_count", ctypes.c_int32),
    ]


def _find_nemo_speech_dll() -> Path | None:
    """Find native NeMo-Speech C ABI DLL (nemo_speech_asr_c.dll) if available."""
    candidates = [
        paths.data_dir() / "bin" / "nemo_speech_asr_c.dll",
        paths.data_dir() / "bin" / "libnemo_speech_asr_c.so",
        paths.data_dir() / "models" / "nemo_speech_asr_c.dll",
    ]
    try:
        from voice_flow import runtime_env

        r_root = runtime_env.runtime_root()
        if r_root:
            candidates.extend([
                r_root / "bin" / "nemo_speech_asr_c.dll",
                r_root / "nemo" / "nemo_speech_asr_c.dll",
            ])
    except Exception:
        pass

    for c in candidates:
        if c.is_file():
            return c

    exe_on_path = shutil.which("nemo_speech_asr_c.dll")
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


def get_nemo_dll() -> ctypes.CDLL | None:
    """Retrieve or initialize the NeMo-Speech C ABI DLL with typed signatures."""
    global _NEMO_DLL, _DLL_LOAD_ATTEMPTED
    with _DLL_LOCK:
        if _DLL_LOAD_ATTEMPTED:
            return _NEMO_DLL
        _DLL_LOAD_ATTEMPTED = True

        dll_path = _ensure_nemo_speech_binaries()
        if not dll_path or not dll_path.is_file():
            return None

        try:
            dll_dir = str(dll_path.parent.resolve())
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(dll_dir)

            dll = ctypes.CDLL(str(dll_path))

            dll.nemo_speech_asr_version.restype = ctypes.c_char_p
            dll.nemo_speech_asr_last_error.restype = ctypes.c_char_p
            dll.nemo_speech_asr_recognition_options_default.restype = _RecognitionOptions

            dll.nemo_speech_asr_create.argtypes = [
                ctypes.POINTER(_RecognizerConfig),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            dll.nemo_speech_asr_create.restype = ctypes.c_int

            dll.nemo_speech_asr_destroy.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_destroy.restype = None

            dll.nemo_speech_asr_recognize_f32.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_RecognitionOptions),
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_size_t,
                ctypes.c_int32,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            dll.nemo_speech_asr_recognize_f32.restype = ctypes.c_int

            dll.nemo_speech_asr_result_transcript.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            dll.nemo_speech_asr_result_transcript.restype = ctypes.c_char_p

            dll.nemo_speech_asr_result_destroy.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_result_destroy.restype = None

            # Streaming recognition C ABI exports
            dll.nemo_speech_asr_streaming_recognize.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_RecognitionOptions),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            dll.nemo_speech_asr_streaming_recognize.restype = ctypes.c_int

            dll.nemo_speech_asr_stream_push_f32.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_size_t,
                ctypes.c_int32,
            ]
            dll.nemo_speech_asr_stream_push_f32.restype = ctypes.c_int

            dll.nemo_speech_asr_stream_next.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            dll.nemo_speech_asr_stream_next.restype = ctypes.c_int

            dll.nemo_speech_asr_stream_force_endpoint.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_stream_force_endpoint.restype = ctypes.c_int

            dll.nemo_speech_asr_stream_finish.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_stream_finish.restype = ctypes.c_int

            dll.nemo_speech_asr_stream_close.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_stream_close.restype = None

            dll.nemo_speech_asr_result_is_final.argtypes = [ctypes.c_void_p]
            dll.nemo_speech_asr_result_is_final.restype = ctypes.c_bool

            ver = dll.nemo_speech_asr_version()
            ver_str = ver.decode("utf-8", errors="replace") if ver else "unknown"
            log.info("[NEMOTRON] Loaded native NeMo-Speech C ABI: %s", ver_str)
            _NEMO_DLL = dll
            return _NEMO_DLL
        except Exception as exc:
            log.warning("[NEMOTRON] Failed to load nemo_speech_asr_c.dll: %s", exc, exc_info=True)
            return None


def is_nemotron_model(model_ref: str | None) -> bool:
    """Check if a model reference specifies an NVIDIA Nemotron local model."""
    if not model_ref:
        return False
    norm = str(model_ref).strip().lower()
    return "nemotron" in norm


def clear_engine_cache(model_ref: str | None = None) -> None:
    """Evict cached engine instance(s) from memory and release native recognizer handles."""
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

    def __init__(self, model_path: Path | str, spec: dict[str, Any] | None = None) -> None:
        self.model_path = Path(model_path).resolve()
        self.spec = spec or {}
        self.model_id = self.spec.get("id") or self.model_path.stem
        self.model_name = self.spec.get("name") or self.model_path.name
        self.lock = threading.Lock()

        # Native C ABI Recognizer Handle
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

        # Profiling stats
        self.last_latency_ms: float = 0.0
        self.total_transcriptions: int = 0
        self.total_audio_seconds: float = 0.0

        self._load_and_warm()

    @property
    def is_warm(self) -> bool:
        return self._is_warm

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

            # Load filterbank if available
            if "preprocessor.fb" in self.tensors:
                fb_dims, fb_type, fb_offset = self.tensors["preprocessor.fb"]
                f.seek(self.data_start_offset + fb_offset)
                fb_bytes = f.read(fb_dims[0] * fb_dims[1] * 4)
                self.preprocessor_fb = np.frombuffer(fb_bytes, dtype=np.float32).reshape(fb_dims[1], fb_dims[0])

        # Initialize in-memory native C ABI recognizer
        dll = get_nemo_dll()
        if dll is not None:
            try:
                bcfg = _BackendConfig(size=ctypes.sizeof(_BackendConfig), gpu=-1)
                mcfg = _ModelConfig(
                    size=ctypes.sizeof(_ModelConfig),
                    path=str(self.model_path).encode("utf-8"),
                    name=None,
                )
                rcfg = _RecognizerConfig(
                    size=ctypes.sizeof(_RecognizerConfig),
                    backend=ctypes.pointer(bcfg),
                    model=ctypes.pointer(mcfg),
                    streaming=None,
                    decoder=None,
                    vad=None,
                    endpointing=None,
                    postproc=None,
                    diar=None,
                    batching=None,
                )
                rec = ctypes.c_void_p()
                st = dll.nemo_speech_asr_create(ctypes.byref(rcfg), ctypes.byref(rec))
                if st == 0 and rec.value:
                    self.rec_handle = rec
                    log.info("[NEMOTRON] Created warm in-process C ABI recognizer handle %s", rec.value)
                else:
                    err = dll.nemo_speech_asr_last_error()
                    err_msg = err.decode("utf-8", errors="replace") if err else f"code {st}"
                    log.warning("[NEMOTRON] nemo_speech_asr_create failed: %s", err_msg)
            except Exception as exc:
                log.warning("[NEMOTRON] Exception during C ABI recognizer initialization: %s", exc)

        load_ms = (time.perf_counter() - t0) * 1000
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

    def close(self) -> None:
        """Destroy native recognizer handle and release RAM."""
        with self.lock:
            if getattr(self, "rec_handle", None) and self.rec_handle.value:
                dll = get_nemo_dll()
                if dll is not None:
                    try:
                        dll.nemo_speech_asr_destroy(self.rec_handle)
                    except Exception:
                        pass
                self.rec_handle = ctypes.c_void_p()
            self._is_warm = False

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

    def _transcribe_segment(
        self,
        wav_segment: np.ndarray,
        language: str | None = None,
    ) -> str:
        """Transcribe a single <= 12s audio segment via in-process C ABI."""
        dll = get_nemo_dll()
        if dll is None or not getattr(self, "rec_handle", None) or not self.rec_handle.value:
            return ""
        try:
            opts = dll.nemo_speech_asr_recognition_options_default()
            opts.enable_automatic_punctuation = True
            lang = language or self.spec.get("default_language")
            if not lang or lang == "multilingual":
                try:
                    from voice_flow.config import config
                    lang = getattr(config, "language", "en") or "en"
                except Exception:
                    lang = "en"
            if lang and lang != "multilingual":
                opts.language_code = lang.encode("utf-8")

            audio_ptr = wav_segment.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            res_handle = ctypes.c_void_p()

            st = dll.nemo_speech_asr_recognize_f32(
                self.rec_handle,
                ctypes.byref(opts),
                audio_ptr,
                len(wav_segment),
                self.sample_rate,
                ctypes.byref(res_handle),
            )
            if st == 0 and res_handle.value:
                txt_p = dll.nemo_speech_asr_result_transcript(res_handle, 0)
                seg_text = txt_p.decode("utf-8", errors="replace").strip() if txt_p else ""
                dll.nemo_speech_asr_result_destroy(res_handle)
                return seg_text
            else:
                err = dll.nemo_speech_asr_last_error()
                err_msg = err.decode("utf-8", errors="replace") if err else f"code {st}"
                log.warning("[NEMOTRON] C ABI recognize error: %s", err_msg)
                return ""
        except Exception as exc:
            log.warning("[NEMOTRON] C ABI recognize exception: %s", exc)
            return ""

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

        c_abi_available = False
        dll = get_nemo_dll()
        if dll is not None and getattr(self, "rec_handle", None) and self.rec_handle.value:
            c_abi_available = True

        if c_abi_available:
            with self.lock:
                # If audio is short or is a stream chunk, transcribe directly in-process
                if is_chunk or duration <= 12.0:
                    result = self._transcribe_segment(wav, language=resolved_lang)
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
                            seg = wav[offset:split_point]
                            offset = split_point

                        if seg.size >= int(0.2 * self.sample_rate):
                            part_txt = self._transcribe_segment(seg, language=resolved_lang)
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

        log.info(
            "[NEMOTRON] Transcribed %.2fs audio in %.1fms (is_chunk=%s, warm=True): '%s'",
            duration,
            elapsed_ms,
            is_chunk,
            result[:60] if result else "<silent/speech>",
        )
        return result


def get_nemotron_engine(model_ref_or_path: str | Path | None = None) -> NemotronGGUFEngine | None:
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
    with _CACHE_LOCK:
        cached = _NEMOTRON_CACHE.get(path_key)
        if cached is not None and cached.is_warm:
            return cached

        try:
            engine = NemotronGGUFEngine(model_file, spec=spec)
            _NEMOTRON_CACHE[path_key] = engine
            return engine
        except Exception as exc:
            log.error("[NEMOTRON ERROR] Failed to load Nemotron engine from %s: %s", model_file, exc, exc_info=True)
            return None


class NemotronStreamTranscriber:
    """Live in-process streaming ASR session using native NeMo-Speech C ABI.

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
        self._queue: queue.Queue[tuple[np.ndarray, int] | None] = queue.Queue(maxsize=512)
        self._finish = threading.Event()
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._failed = False
        self._text = ""
        self._accepted = 0
        self._deadline: float | None = None
        self._model_ref: str = ""
        self._worker_thread: threading.Thread | None = None

    def start_session(self, model_ref: str | None = None, deadline: float | None = None) -> None:
        self._model_ref = str(model_ref or "")
        self._deadline = deadline
        if self._engine is None:
            self._engine = get_nemotron_engine(self._model_ref)
        if self._engine is None or not getattr(self._engine, "rec_handle", None) or not self._engine.rec_handle.value:
            log.warning("[NEMOTRON STREAM] Native C ABI engine handle not available; failing stream")
            self._failed = True
            self._done.set()
            return

        dll = get_nemo_dll()
        if dll is None:
            log.warning("[NEMOTRON STREAM] Native C ABI DLL not available; failing stream")
            self._failed = True
            self._done.set()
            return

        self._worker_thread = threading.Thread(target=self._run, name="vf-nemotron-stream", daemon=True)
        self._worker_thread.start()

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
        dll = get_nemo_dll()
        eng = self._engine
        if dll is None or eng is None or not getattr(eng, "rec_handle", None) or not eng.rec_handle.value:
            self._failed = True
            self._done.set()
            return

        stream = ctypes.c_void_p()
        t0 = time.perf_counter()
        try:
            opts = dll.nemo_speech_asr_recognition_options_default()
            opts.enable_automatic_punctuation = True
            opts.interim_results = False

            lang = None
            if eng.spec:
                lang = eng.spec.get("default_language")
            if not lang or lang == "multilingual":
                try:
                    from voice_flow.config import config

                    lang = getattr(config, "language", "en") or "en"
                except Exception:
                    lang = "en"
            if lang and lang != "multilingual":
                opts.language_code = lang.encode("utf-8")

            with eng.lock:
                st = dll.nemo_speech_asr_streaming_recognize(eng.rec_handle, ctypes.byref(opts), ctypes.byref(stream))
            if st != 0 or not stream.value:
                err = dll.nemo_speech_asr_last_error()
                err_msg = err.decode("utf-8", errors="replace") if err else f"code {st}"
                raise RuntimeError(f"nemo_speech_asr_streaming_recognize failed: {err_msg}")

            committed_transcripts: list[str] = []
            interim_latest = ""

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
                if frame.ndim > 1:
                    frame = np.mean(frame, axis=1)
                mono = np.nan_to_num(frame, nan=0.0, posinf=0.0, neginf=0.0)
                if mono.dtype != np.float32:
                    mono = mono.astype(np.float32, copy=False)

                if mono.size > 0:
                    ptr = mono.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                    push_st = dll.nemo_speech_asr_stream_push_f32(stream, ptr, len(mono), int(sr))
                    if push_st != 0:
                        raise RuntimeError(f"Audio frame was not accepted (status {push_st})")

                    res = ctypes.c_void_p()
                    next_st = dll.nemo_speech_asr_stream_next(stream, ctypes.byref(res))
                    if next_st == 0 and res.value:
                        try:
                            is_fin = dll.nemo_speech_asr_result_is_final(res)
                            txt_p = dll.nemo_speech_asr_result_transcript(res, 0)
                            t = txt_p.decode("utf-8", errors="replace").strip() if txt_p else ""
                            if is_fin:
                                if t:
                                    committed_transcripts.append(t)
                                interim_latest = ""
                            else:
                                interim_latest = t
                        finally:
                            dll.nemo_speech_asr_result_destroy(res)

            if self._cancel.is_set():
                raise RuntimeError("Stream was cancelled")
            if self._expired():
                raise TimeoutError("Stream deadline elapsed before all audio was consumed")

            # Finalize audio stream and drain tail
            t_finish = time.perf_counter()
            fin_st = dll.nemo_speech_asr_stream_finish(stream)
            if fin_st != 0:
                raise RuntimeError(f"Audio finalization failed (status {fin_st})")

            while True:
                res = ctypes.c_void_p()
                next_st = dll.nemo_speech_asr_stream_next(stream, ctypes.byref(res))
                if next_st != 0 or not res.value:
                    break
                try:
                    txt_p = dll.nemo_speech_asr_result_transcript(res, 0)
                    t = txt_p.decode("utf-8", errors="replace").strip() if txt_p else ""
                    if t:
                        committed_transcripts.append(t)
                finally:
                    dll.nemo_speech_asr_result_destroy(res)

            if interim_latest and not committed_transcripts:
                committed_transcripts.append(interim_latest)

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
        except Exception as exc:
            self._failed = True
            log.warning("[NEMOTRON STREAM] Streaming session exception: %s; falling back to whole-buffer", exc)
        finally:
            if stream.value:
                try:
                    dll.nemo_speech_asr_stream_close(stream)
                except Exception:
                    pass
            self._done.set()
