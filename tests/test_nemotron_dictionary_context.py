"""NeMo C ABI dictionary context wiring, exercised with a recording DLL."""

from __future__ import annotations

import ctypes
import gc
import threading

import numpy as np

from voice_flow import nemotron_engine


class _RecordingDll:
    def __init__(self, *, short_options: bool = False):
        self.phrases: list[str] = []
        self.boost = None
        self.context_count = None
        self.short_options = short_options

    def nemo_speech_asr_recognition_options_default(self):
        options = nemotron_engine._RecognitionOptions()
        options.size = (
            nemotron_engine._RecognitionOptions.speech_contexts.offset
            if self.short_options
            else ctypes.sizeof(nemotron_engine._RecognitionOptions)
        )
        return options

    def _capture(self, options_pointer):
        options = ctypes.cast(
            options_pointer,
            ctypes.POINTER(nemotron_engine._RecognitionOptions),
        ).contents
        self.context_count = options.speech_context_count
        if options.speech_context_count:
            context = options.speech_contexts[0]
            self.boost = context.boost
            self.phrases = [
                context.phrases[index].decode("utf-8")
                for index in range(context.phrase_count)
            ]

    def nemo_speech_asr_recognize_f32(self, _recognizer, options, _audio, _size, _rate, out):
        self._capture(options)
        out._obj.value = 123
        return 0

    def nemo_speech_asr_result_transcript(self, _result, _index):
        return b"decoded"

    def nemo_speech_asr_result_destroy(self, _result):
        pass

    def nemo_speech_asr_streaming_recognize(self, _recognizer, options, out):
        self._capture(options)
        out._obj.value = 456
        return 0


def _engine(*, speech_context_supported: bool):
    return type("Engine", (), {
        "rec_handle": ctypes.c_void_p(1),
        "spec": {"default_language": "en"},
        "metadata": {"speech_context_supported": speech_context_supported},
        "sample_rate": 16000,
        "lock": threading.RLock(),
    })()


def test_offline_request_uses_pinned_native_context_abi_and_boost(monkeypatch):
    dll = _RecordingDll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.rec_handle = ctypes.c_void_p(1)
    engine.spec = {"default_language": "en"}
    engine.metadata = {"speech_context_supported": True}
    engine.sample_rate = 16000

    text = engine._transcribe_segment(
        np.ones(3200, dtype=np.float32),
        vocabulary=["OpenAI", "Kubernetes", "openai"],
    )

    assert text == "decoded"
    assert dll.context_count == 1
    assert dll.phrases == ["OpenAI", "Kubernetes"]
    assert dll.boost == 3.0


def test_stream_request_keeps_utf8_buffers_alive_for_native_stream(monkeypatch):
    dll = _RecordingDll()
    session = nemotron_engine.NemotronStreamTranscriber(
        vocabulary=["Ada Lovelace", "Éclair"],
        engine=_engine(speech_context_supported=True),
    )

    assert session._open_stream(dll)
    gc.collect()

    assert dll.context_count == 1
    assert dll.phrases == ["Ada Lovelace", "Éclair"]
    assert dll.boost == 3.0
    assert len(session._speech_context_refs) == 3
    context = session._speech_context_refs[0][0]
    assert context.phrases[1].decode("utf-8") == "Éclair"


def test_missing_embedded_sentencepiece_model_skips_native_boost(monkeypatch):
    dll = _RecordingDll()
    monkeypatch.setattr(nemotron_engine, "get_nemo_dll", lambda: dll)
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.rec_handle = ctypes.c_void_p(1)
    engine.spec = {"default_language": "en"}
    engine.metadata = {
        "tokenizer_type": "sentencepiece_bpe",
        "tokenizer_spm_model_embedded": False,
        "speech_context_supported": False,
    }
    engine.sample_rate = 16000

    assert engine._transcribe_segment(
        np.ones(3200, dtype=np.float32), vocabulary=["Kubernetes"]
    ) == "decoded"
    assert dll.context_count == 0

    session = nemotron_engine.NemotronStreamTranscriber(
        vocabulary=["Kubernetes"],
        engine=_engine(speech_context_supported=False),
    )
    assert session._open_stream(dll)
    assert dll.context_count == 0
    assert session._speech_context_refs == ()


def test_older_options_size_and_empty_vocabulary_leave_contexts_unset():
    short = _RecordingDll(short_options=True)
    options = short.nemo_speech_asr_recognition_options_default()
    assert nemotron_engine._attach_speech_context(options, ["OpenAI"]) == ()
    assert options.speech_context_count == 0

    empty = _RecordingDll()
    options = empty.nemo_speech_asr_recognition_options_default()
    assert nemotron_engine._attach_speech_context(options, []) == ()
    assert options.speech_context_count == 0
