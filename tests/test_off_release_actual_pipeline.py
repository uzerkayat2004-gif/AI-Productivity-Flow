"""Isolated full release-to-paste probe with real pipeline/finalizer and a fake native ABI."""

from native_fixture_client import bind_native
import ctypes
import logging
import threading
from types import SimpleNamespace

import numpy as np

from voice_flow import main as m
from voice_flow import nemotron_engine as native
from voice_flow import polisher as polisher_module
from voice_flow.dictionary import dictionary_engine
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp
from voice_flow.voice_enhance import enhance_for_stt


class FakeClock:
    def __init__(self, *, next_cost=0.0025, load_cost=0.0):
        self.now = 1000.0
        self.release = threading.Event()
        self.next_calls = 0
        self.cost_per_next = next_cost
        self.load_cost = load_cost

    def monotonic(self):
        return self.now

    def perf_counter(self):
        return self.now

    def time(self):
        return self.now

    def charge_native_next(self):
        if not self.release.is_set():
            self.release.wait(2)
        self.next_calls += 1
        self.now += self.cost_per_next


class FakeDll:
    def __init__(self, clock, transcript="synthetic release transcript", complete=True):
        self.clock = clock
        self.transcript = transcript
        self.complete = complete
        self.finished = False
        self.delivered = False
        self.frame_pushes = 0

    def nemo_speech_asr_stream_push_f32(self, stream, ptr, length, rate):
        self.frame_pushes += 1
        return 0

    def nemo_speech_asr_stream_next(self, stream, result_ptr):
        self.clock.charge_native_next()
        if self.finished and not self.delivered:
            ctypes.cast(result_ptr, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(2)
            self.delivered = True
            return 0
        return 1

    def nemo_speech_asr_stream_finish(self, stream):
        self.finished = True
        return 0

    def nemo_speech_asr_result_is_final(self, result):
        return self.complete

    def nemo_speech_asr_result_transcript(self, result, index):
        return self.transcript.encode()

    def nemo_speech_asr_result_destroy(self, result):
        pass

    def nemo_speech_asr_stream_close(self, stream):
        pass


class FakeEngine:
    def __init__(self):
        self.rec_handle = ctypes.c_void_p(1)
        self.spec = {}
        self.lock = threading.Lock()
        self.streams = 0

    def acquire_stream(self):
        self.streams += 1

    def release_stream(self):
        self.streams -= 1


def replay(monkeypatch, *, incomplete=False, next_cost=0.0025, load_cost=0.0):
    clock = FakeClock(next_cost=next_cost, load_cost=load_cost)
    dll = FakeDll(clock, complete=not incomplete)
    monkeypatch.setattr(m, "time", clock)
    monkeypatch.setattr(native, "time", clock)
    monkeypatch.setattr(polisher_module, "time", clock)
    monkeypatch.setattr(m.storage, "get_setting", lambda key, default=None: False if key in {"polishing_enabled", "voice_flow_mic_profile"} else default)

    dictionary_calls = []
    original_dictionary = dictionary_engine.apply_dictionary_post_processing
    def observe_dictionary(text, *args, **kwargs):
        dictionary_calls.append(True)
        return original_dictionary(text, *args, **kwargs)
    monkeypatch.setattr(dictionary_engine, "apply_dictionary_post_processing", observe_dictionary)

    enhancement_calls = []
    original_enhancer = native.LiveSpeechEnhancer
    class ObservedEnhancer(original_enhancer):
        def process(self, audio, sample_rate):
            enhancement_calls.append(len(audio))
            return super().process(audio, sample_rate)
    monkeypatch.setattr(native, "LiveSpeechEnhancer", ObservedEnhancer)

    frame = np.full(160, 0.02, dtype=np.float32)
    audio = np.tile(frame, 32)
    app = object.__new__(VoiceFlowApp)
    style = SimpleNamespace(app_name="Editor", category="smart_clean", style_id="smart_clean", instruction="")
    class RecordingSpeechLease:
        def __init__(self):
            self.actions = []
            self.released = False
        def release(self):
            if self.released:
                return
            self.released = True
            self.actions.append(("release",))
        def release_after_idle(self, seconds):
            if self.released:
                return
            self.released = True
            self.actions.append(("release_after_idle", seconds))
    lease = RecordingSpeechLease()
    session = DictationSession(
        target_hwnd=123,
        app_title="Editor",
        app_category="smart_clean",
        style_id="smart_clean",
        started_at=0.0,
        resolved_style=style,
        stt_model_ref="local/nemotron-speech-streaming-en-0.6b",
        polish_model_ref=None,
        model_resource_lease=lease,
    )
    app.session = session
    app.state = DictationState.RECORDING
    app._state_lock = threading.RLock()
    app.processing_lock = threading.Lock()
    app._record_watchdog = None
    app._release_timing_session = session
    app._stream_session_owner = session
    app._streaming_stt_enabled = lambda: True
    app._get_current_external_window = lambda: 123
    app._get_effective_destination_hwnd = lambda *args, **kwargs: 123
    app._set_hotkeys_recording_state = lambda *args: None
    app._overlay_call = lambda *args, **kwargs: None
    history_metadata = []
    def update_history(_record_id, **kwargs):
        metadata = kwargs.get("processing_metadata")
        if metadata:
            history_metadata.append(metadata)
    app._history_update = update_history
    app._defer_history_insert = lambda *args, **kwargs: None
    app._start_recovery_archive = lambda *args: None
    app._get_cached_setting = lambda key, default=None: default
    app._pending_recovery = {}
    app._cancelled_session_ids = set()
    app.recent_dictations = set()
    app._delivery_session = None
    app.last_successful_transcript = None

    engine = None if load_cost else bind_native(FakeEngine(), dll, opened=True)
    if load_cost:
        def load_engine(_model_ref, **_kwargs):
            assert clock.release.wait(2.0)
            clock.now += clock.load_cost
            return bind_native(FakeEngine(), dll, opened=True)
        monkeypatch.setattr(native, "get_nemotron_engine", load_engine)
    stream = native.NemotronStreamTranscriber(engine=engine)
    monkeypatch.setattr(stream, "_open_stream", lambda client: setattr(stream._stream, "value", 42) or True)
    app._stream_stt = stream
    stream.start_session(model_ref=session.stt_model_ref)
    for _ in range(32):
        stream.submit_frame(frame, 16000)
    assert stream.accepted_count() == 32

    class Audio:
        _native_sr = 16000
        stream_input_incomplete = incomplete
        split_silence_seconds = 0.35
        max_chunk_seconds = 8.0
        on_audio_frame = None

        def stop_and_take_open_chunk(self):
            clock.release.set()
            tail = np.zeros(137, dtype=np.float32)
            return audio.copy(), tail, 0.0

    app.audio = Audio()
    transcriber_calls = []
    def fallback_transcribe(received, **kwargs):
        transcriber_calls.append(True)
        assert np.array_equal(received, audio)
        enhance_for_stt(received, sr=16000, profile="off")
        return "synthetic release transcript"
    app.transcriber = SimpleNamespace(transcribe=fallback_transcribe, category_hint=None)
    pasted = []
    app.injector = SimpleNamespace(paste_text=lambda text, *args, **kwargs: pasted.append(text) or True)

    # Keep the real stream worker asynchronous while executing the real release
    # pipeline inline; no device, network, process, or live model is involved.
    RealThread = threading.Thread
    class PipelineInlineThread:
        def __init__(self, *, target, args=(), kwargs=None, **ignored):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}
        def start(self):
            if getattr(self.target, "__name__", "") == "_process_dictation_pipeline":
                self.target(*self.args, **self.kwargs)
            else:
                RealThread(target=self.target, args=self.args, kwargs=self.kwargs, daemon=True).start()
    monkeypatch.setattr(m.threading, "Thread", PipelineInlineThread)

    old_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.ERROR)
    try:
        assert app._on_dictation_finish()
    finally:
        logging.getLogger().setLevel(old_level)

    assert pasted == ["Synthetic release transcript."]
    assert dictionary_calls, "the actual OFF finalizer must apply the dictionary pass"
    assert app.state == DictationState.IDLE
    return {
        "release_to_paste_ms": (clock.now - 1000.0) * 1000,
        "native_next_calls": clock.next_calls,
        "simulated_load_ms": clock.load_cost * 1000,
        "native_frame_pushes": dll.frame_pushes,
        "enhancement_calls": len(enhancement_calls),
        "dictionary_calls": len(dictionary_calls),
        "fallback_calls": len(transcriber_calls),
        "lease_actions": lease.actions,
        "processing_metadata": history_metadata[-1] if history_metadata else {},
    }


def test_actual_off_release_path_reports_pending_cold_first_use_load(monkeypatch):
    result = replay(monkeypatch, next_cost=0.0, load_cost=1.25)
    print("cold_first_use_metrics=" + repr(result))
    assert result["native_frame_pushes"] == 32
    assert result["fallback_calls"] == 0
    assert result["simulated_load_ms"] == 1250
    assert result["release_to_paste_ms"] == 1250
    assert result["lease_actions"] == [("release_after_idle", m.NEMOTRON_OFF_BURST_IDLE_GRACE_SECONDS)]


def test_actual_off_release_path_with_warm_native_stream_is_fast(monkeypatch):
    result = replay(monkeypatch, next_cost=0.0, load_cost=0.0)
    print("warm_stream_metrics=" + repr(result))
    assert result["native_frame_pushes"] == 32
    assert result["fallback_calls"] == 0
    assert result["dictionary_calls"] == 2  # names before polish + shortcuts after
    assert result["processing_metadata"]["polish"]["outcome"] == "disabled"
    assert result["processing_metadata"]["command"]["status"] == "disabled"
    assert result["lease_actions"] == [("release_after_idle", m.NEMOTRON_OFF_BURST_IDLE_GRACE_SECONDS)]
    assert result["release_to_paste_ms"] < 1000, result


def test_actual_off_release_path_recovers_incomplete_stream_with_full_buffer(monkeypatch):
    result = replay(monkeypatch, incomplete=True)
    print("incomplete_stream_metrics=" + repr(result))
    assert result["fallback_calls"] == 1
    assert result["dictionary_calls"] == 2  # names before polish + shortcuts after
    assert result["lease_actions"] == [("release_after_idle", m.NEMOTRON_OFF_BURST_IDLE_GRACE_SECONDS)]
    assert result["release_to_paste_ms"] < 1000, result

