"""Full release-to-paste replay; all device/provider/time boundaries are fake."""

from native_fixture_client import bind_native
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from voice_flow import main as m
from voice_flow.main import VoiceFlowApp, DictationSession, DictationState


def replay(monkeypatch, *, failed_stream=False, stop_seconds=0.0, fresh_pipeline=False):
    now = [100.0]
    timings = {}
    original_info = m.log.info
    def capture_info(message, *args, **kwargs):
        if message.startswith("[VOICE LATENCY]"):
            timings["logged_release_ms"] = args[-1]
        original_info(message, *args, **kwargs)
    monkeypatch.setattr(m.log, "info", capture_info)
    monkeypatch.setattr(m, 'time', SimpleNamespace(monotonic=lambda: now[0], perf_counter=lambda: now[0]))
    monkeypatch.setattr(m.storage, 'get_setting', lambda key, default=None: False if key == 'polishing_enabled' else default)
    monkeypatch.setattr(m, 'apply_spoken_punctuation', lambda text: text)
    monkeypatch.setattr(m, 'split_press_enter', lambda text, enabled: SimpleNamespace(text=text, press_enter=False))
    app = object.__new__(VoiceFlowApp)
    session = DictationSession(target_hwnd=123, app_title='Editor', app_category='smart_clean', style_id='smart_clean', started_at=0., resolved_style=SimpleNamespace(app_name='Editor', category='smart_clean', style_id='smart_clean', instruction=''))
    app.session = session
    app.state = DictationState.RECORDING
    app._state_lock = threading.RLock()
    app.processing_lock = threading.Lock()
    app._record_watchdog = None
    app._get_current_external_window = lambda: 123
    app._get_effective_destination_hwnd = lambda *args, **kwargs: 123
    app._set_hotkeys_recording_state = lambda *args: None
    app._streaming_stt_enabled = lambda: True
    app._overlay_call = lambda *args, **kwargs: None
    app._history_update = lambda *args, **kwargs: None
    app._defer_history_insert = lambda *args, **kwargs: None
    app._start_recovery_archive = lambda *args: None
    app._get_cached_setting = lambda key, default=None: default
    app._finalize_text = lambda text, *args, **kwargs: text
    audio = np.linspace(.01, .1, 16000, dtype=np.float32)
    def stop():
        now[0] += stop_seconds
        timings['stop'] = stop_seconds
        return audio, audio[-1600:].copy(), 0.
    app.audio = SimpleNamespace(_native_sr=16000, stop_and_take_open_chunk=stop, stream_input_incomplete=False)
    def collect(timeout=0., **kwargs):
        if failed_stream:
            now[0] += timeout
            timings['harvest'] = timings.get('harvest', 0.) + timeout
            return ''
        return 'beginning middle ending'
    app._stream_stt = SimpleNamespace(live_frames=True, accepted_count=lambda: 1, submit_native=lambda *args, **kwargs: None, end_session=lambda **kwargs: None, collect=collect, pending_count=lambda: int(failed_stream), had_failures=lambda: failed_stream, discard=lambda: None)
    def transcribe(received, **kwargs):
        assert np.array_equal(received, audio)
        now[0] += .1
        timings['fallback'] = .1
        return 'beginning middle ending'
    app.transcriber = SimpleNamespace(transcribe=transcribe)
    def paste(text, *args, **kwargs):
        assert text == 'beginning middle ending'
        timings['release_to_paste'] = now[0] - 100.
        return True
    app.injector = SimpleNamespace(paste_text=paste)
    class InlineThread:
        def __init__(self, *, target, args=(), kwargs=None, **ignored):
            self.call = lambda: target(*args, **(kwargs or {}))
        def start(self):
            self.call()
    monkeypatch.setattr(m.threading, 'Thread', InlineThread)
    if fresh_pipeline:
        app.state = DictationState.PROCESSING
        app._release_started_at = 5.0
        app._release_timing_session = object()
        app._process_dictation_pipeline(session, audio, 1.0, use_streaming=False)
    else:
        assert app._on_dictation_finish()
    assert 'release_to_paste' in timings
    return timings


def test_ready_off_release_to_paste_is_immediate(monkeypatch):
    timings = replay(monkeypatch)
    assert timings['release_to_paste'] < .2, timings


def test_known_failed_live_stream_does_not_delay_complete_recovery(monkeypatch):
    timings = replay(monkeypatch, failed_stream=True)
    assert timings['release_to_paste'] < .2, timings


def test_harness_includes_capture_stop_before_pipeline(monkeypatch):
    timings = replay(monkeypatch, stop_seconds=2.3)
    assert timings['release_to_paste'] == pytest.approx(2.3)


@pytest.mark.parametrize("conditioning", ["identity", "quiet", "off", "rate_change"])
def test_native_frames_preserve_conditioned_pcm_and_short_final_tail(monkeypatch, conditioning):
    """Real worker preserves per-frame conditioning, ordering and final 137 samples."""
    import ctypes
    from voice_flow import nemotron_engine as native
    received = []
    class Engine:
        rec_handle = ctypes.c_void_p(1)
        spec = {}
        lock = threading.Lock()
        def acquire_stream(self): pass
        def release_stream(self): pass
    class Dll:
        finished = False
        delivered = False
        def nemo_speech_asr_stream_push_f32(self, stream, ptr, length, rate):
            received.append(np.ctypeslib.as_array(ptr, shape=(length,)).copy())
            return 0
        def nemo_speech_asr_stream_next(self, stream, ptr):
            if self.finished and not self.delivered:
                ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(2)
                self.delivered = True
                return 0
            return 1
        def nemo_speech_asr_stream_finish(self, stream): self.finished = True; return 0
        def nemo_speech_asr_result_is_final(self, result): return True
        def nemo_speech_asr_result_transcript(self, *args): return b'beginning middle ending'
        def nemo_speech_asr_result_destroy(self, result): pass
        def nemo_speech_asr_stream_close(self, stream): pass
    dll = Dll()
    monkeypatch.setattr(native, 'notify_models_available', lambda *args: None)
    if conditioning in {'identity', 'rate_change'}:
        monkeypatch.setattr(native, 'LiveSpeechEnhancer', lambda **kwargs: SimpleNamespace(process=lambda audio, rate: audio))
        baseline = SimpleNamespace(process=lambda audio, rate: audio)
    else:
        from voice_flow.voice_enhance import LiveSpeechEnhancer
        profile = 'far' if conditioning == 'quiet' else 'off'
        monkeypatch.setattr(native, 'LiveSpeechEnhancer', lambda **kwargs: LiveSpeechEnhancer(profile=profile))
        baseline = LiveSpeechEnhancer(profile=profile)
    stream = native.NemotronStreamTranscriber(engine=Engine())
    bind_native(stream._engine, dll, opened=True)
    monkeypatch.setattr(stream, '_open_stream', lambda client: setattr(stream._stream, 'value', 42) or True)
    frames = [np.full(160, (i + 1) / 100., dtype=np.float32) for i in range(40)]
    if conditioning == 'quiet':
        frames = [frame * .002 for frame in frames]
    frames.append(np.linspace(.001, .004, 137, dtype=np.float32))
    rates = [16000] * len(frames)
    if conditioning == 'rate_change':
        rates[20] = 8000
    expected = np.concatenate([baseline.process(frame.copy(), rate).copy() for frame, rate in zip(frames, rates)])
    for frame, rate in zip(frames, rates):
        stream.submit_frame(frame, rate)
    stream.end_session()
    stream._run()
    # The last push is the trailing-silence pad added before stream_finish.
    pad = received[-1]
    assert pad.size == int(native.TRAILING_SILENCE_SECONDS * rates[-1]) and not np.any(pad)
    np.testing.assert_array_equal(np.concatenate(received[:-1]), expected)
    assert stream.collect(timeout=0.) == 'beginning middle ending'


def test_fresh_processing_attempt_does_not_log_previous_release_timer(monkeypatch):
    timings = replay(monkeypatch, fresh_pipeline=True)
    assert timings["release_to_paste"] == pytest.approx(.1)
    assert timings["logged_release_ms"] == pytest.approx(100.)
