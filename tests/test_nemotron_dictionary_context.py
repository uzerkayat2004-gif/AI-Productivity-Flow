"""NeMo C ABI dictionary context wiring, exercised with a recording DLL."""

from __future__ import annotations

import ctypes
import gc
import importlib.util
from pathlib import Path
import threading

import numpy as np

from voice_flow import nemotron_engine
from voice_flow import nemotron_abi


class _RecordingDll:
    def __init__(self, *, short_options: bool = False):
        self.phrases: list[str] = []
        self.boost = None
        self.context_count = None
        self.short_options = short_options
        self.abi = nemotron_abi

    def nemo_speech_asr_recognition_options_default(self):
        options = self.abi._RecognitionOptions()
        options.size = (
            self.abi._RecognitionOptions.speech_contexts.offset
            if self.short_options
            else ctypes.sizeof(self.abi._RecognitionOptions)
        )
        return options

    def _capture(self, options_pointer):
        options = ctypes.cast(
            options_pointer,
            ctypes.POINTER(self.abi._RecognitionOptions),
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


class _DomainClient:
    """Exercise child ownership without starting a process or loading a DLL."""
    def __init__(self, dll):
        path = Path(nemotron_engine.__file__).with_name("nemotron_native_worker.py")
        spec = importlib.util.spec_from_file_location("dictionary_native_owner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.owner = module.NativeOwner()
        self.owner.dll = dll
        dll.abi = module.abi
        self.owner.recognizers[1] = ctypes.c_void_p(1)
        self.calls = []

    def call(self, op, **values):
        self.calls.append((op, values.copy()))
        return self.owner.dispatch(op, values)


def _engine(*, speech_context_supported: bool, dll):
    engine = object.__new__(nemotron_engine.NemotronGGUFEngine)
    engine.rec_handle = ctypes.c_void_p(1)
    engine.spec = {"default_language": "en"}
    engine.metadata = {"speech_context_supported": speech_context_supported}
    engine.sample_rate = 16000
    engine.lock = threading.RLock()
    engine.fatal_error = None
    engine._native = _DomainClient(dll)
    return engine


def test_offline_request_uses_pinned_native_context_abi_and_boost(monkeypatch):
    dll = _RecordingDll()
    engine = _engine(speech_context_supported=True, dll=dll)

    text = engine._transcribe_segment(
        np.ones(3200, dtype=np.float32),
        vocabulary=["OpenAI", "Kubernetes", "openai"],
    )

    assert text == "decoded"
    assert dll.context_count == 1
    assert dll.phrases == ["OpenAI", "Kubernetes"]
    assert dll.boost == 3.0
    op, values = engine._native.calls[0]
    assert op == "recognize"
    assert values == {
        "handle": 1, "language": "en", "vocabulary": ("OpenAI", "Kubernetes", "openai"),
        "audio": np.ones(3200, dtype=np.float32).tobytes(), "count": 3200,
        "rate": 16000, "deadline": None,
    }


def test_stream_request_keeps_utf8_buffers_alive_for_native_stream(monkeypatch):
    dll = _RecordingDll()
    session = nemotron_engine.NemotronStreamTranscriber(
        vocabulary=["Ada Lovelace", "Éclair"],
        engine=_engine(speech_context_supported=True, dll=dll),
    )

    assert session._open_stream()
    op, values = session._engine._native.calls[0]
    assert op == "stream_open"
    assert values["handle"] == 1 and values["streaming"] is True
    assert values["language"] == "en"
    assert values["vocabulary"] == ("Ada Lovelace", "Éclair")
    assert callable(values["deadline"]) and values["cancelled"] is session._cancel
    gc.collect()

    assert dll.context_count == 1
    assert dll.phrases == ["Ada Lovelace", "Éclair"]
    assert dll.boost == 3.0
    refs = session._engine._native.owner.streams[session._stream.value][2]
    assert len(refs) == 4  # language bytes plus the three ABI context roots
    context = refs[1][0]
    assert context.phrases[1].decode("utf-8") == "Éclair"


def test_missing_embedded_sentencepiece_model_skips_native_boost(monkeypatch):
    dll = _RecordingDll()
    engine = _engine(speech_context_supported=False, dll=dll)
    engine.metadata.update({
        "tokenizer_type": "sentencepiece_bpe",
        "tokenizer_spm_model_embedded": False,
    })

    assert engine._transcribe_segment(
        np.ones(3200, dtype=np.float32), vocabulary=["Kubernetes"]
    ) == "decoded"
    assert dll.context_count == 0

    session = nemotron_engine.NemotronStreamTranscriber(
        vocabulary=["Kubernetes"],
        engine=_engine(speech_context_supported=False, dll=dll),
    )
    assert session._open_stream()
    assert dll.context_count == 0
    refs = session._engine._native.owner.streams[session._stream.value][2]
    assert refs == [b"en"]


def test_older_options_size_and_empty_vocabulary_leave_contexts_unset():
    short = _RecordingDll(short_options=True)
    options = short.nemo_speech_asr_recognition_options_default()
    assert nemotron_engine._attach_speech_context(options, ["OpenAI"]) == ()
    assert options.speech_context_count == 0

    empty = _RecordingDll()
    options = empty.nemo_speech_asr_recognition_options_default()
    assert nemotron_engine._attach_speech_context(options, []) == ()
    assert options.speech_context_count == 0
