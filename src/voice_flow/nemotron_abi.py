"""Pure ABI definitions. Only the standalone native worker calls load_dll."""
from __future__ import annotations
import ctypes
import os
from typing import Any

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


class _SpeechContext(ctypes.Structure):
    """Per-request phrase boost, matching nemo_speech/asr.h v0.1.0."""

    _fields_ = [
        ("size", ctypes.c_size_t),
        ("phrases", ctypes.POINTER(ctypes.c_char_p)),
        ("phrase_count", ctypes.c_size_t),
        ("boost", ctypes.c_float),
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
        ("speech_contexts", ctypes.POINTER(_SpeechContext)),
        ("speech_context_count", ctypes.c_size_t),
        ("max_alternatives", ctypes.c_int32),
        ("enable_speaker_diarization", ctypes.c_bool),
        ("max_speaker_count", ctypes.c_int32),
    ]


def _make_speech_context(vocabulary: list[str] | tuple[str, ...] | None):
    """Build a per-request native phrase boost and retain all backing memory.

    The returned references must stay alive through the C ABI call. Streaming
    callers retain them for the whole stream because native stream setup may
    keep request context while decoding continues.
    """
    terms: list[str] = []
    seen: set[str] = set()
    used_chars = 0
    for raw in vocabulary or ():
        term = str(raw).strip()
        key = term.casefold()
        if not term or len(term) > 96 or key in seen:
            continue
        extra = len(term) + (2 if terms else 0)
        if used_chars + extra > 499:
            continue
        terms.append(term)
        seen.add(key)
        used_chars += extra
        if len(terms) >= 15:
            break
    if not terms:
        return None, ()

    encoded_phrases = tuple(term.encode("utf-8") for term in terms)
    phrase_array = (ctypes.c_char_p * len(encoded_phrases))(*encoded_phrases)
    contexts = (_SpeechContext * 1)()
    contexts[0].size = ctypes.sizeof(_SpeechContext)
    contexts[0].phrases = phrase_array
    contexts[0].phrase_count = len(encoded_phrases)
    contexts[0].boost = 3.0
    return contexts, (contexts, phrase_array, encoded_phrases)


def _options_support_speech_context(opts: _RecognitionOptions) -> bool:
    """Whether this native library's append-only options struct has both fields."""
    struct_size = int(getattr(opts, "size", 0) or 0)
    ptr_end = _RecognitionOptions.speech_contexts.offset + ctypes.sizeof(ctypes.c_void_p)
    count_end = _RecognitionOptions.speech_context_count.offset + ctypes.sizeof(ctypes.c_size_t)
    return struct_size >= max(ptr_end, count_end)


def _attach_speech_context(opts: _RecognitionOptions, vocabulary):
    """Attach supported phrase boosts and return the references to retain."""
    if not vocabulary or not _options_support_speech_context(opts):
        return ()
    contexts, references = _make_speech_context(vocabulary)
    if contexts is None:
        return ()
    opts.speech_contexts = ctypes.cast(contexts, ctypes.POINTER(_SpeechContext))
    opts.speech_context_count = 1
    return references



_DLL_DIRECTORY = None

def load_dll(path):
    global _DLL_DIRECTORY
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY = os.add_dll_directory(os.path.dirname(path))
    dll = ctypes.CDLL(path)
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

    return dll
