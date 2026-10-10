"""User-visible regressions: missing words and AI commands silently skipped."""
import time
import threading
from types import SimpleNamespace

import pytest

import voice_flow.main as main
import voice_flow.polisher as polishing
from voice_flow.voice_commands import detect_voice_command


class _CompleteStream:
    def collect(self, **kwargs):
        return "incomplete prefix"

    def pending_count(self):
        return 0

    def end_session(self):
        pass

    def discard(self):
        pass


class _FailedStream(_CompleteStream):
    def had_failures(self):
        return True


def _app(current):
    app = object.__new__(main.VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = main.DictationState.PROCESSING
    app.session = current
    app.transcriber = SimpleNamespace(transcribe=lambda *a, **k: "whole buffer")
    app.overlay = SimpleNamespace(show_error=lambda *a: None, show_done=lambda *a: None)
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *a: None)
    app.recent_dictations = set()
    return app


def session():
    return main.DictationSession(
        123, "Editor", "smart_clean", "smart_clean", 0.0,
        resolved_style=SimpleNamespace(app_name="Editor", category="smart_clean",
                                       style_id="smart_clean", instruction="Keep the content."),
    )


def test_failed_stream_is_never_pasted_when_complete_recovery_fails(monkeypatch):
    current = session()
    app = _app(current)
    app._stream_stt = _FailedStream()
    app.transcriber = SimpleNamespace(transcribe=lambda *a, **k: "")
    pasted = []
    app.injector = SimpleNamespace(paste_text=lambda text, *a, **k: pasted.append(text) or True)
    monkeypatch.setattr(main.storage, "update_dictation", lambda *a, **k: True)
    app._process_dictation_pipeline(current, object(), 1.0, record_id=1, use_streaming=True)
    assert not pasted
    assert app.state == main.DictationState.IDLE


def test_failure_during_final_drain_requires_complete_recovery(monkeypatch):
    class LateFailure(_CompleteStream):
        calls = 0

        def collect(self, **kwargs):
            self.calls += 1
            return "first words" if self.calls == 1 else ""

        def pending_count(self):
            return 1 if self.calls == 1 else 0

        def had_failures(self):
            return self.calls > 1

    current = session()
    app = _app(current)
    app._stream_stt = LateFailure()
    pasted = []
    app.injector = SimpleNamespace(paste_text=lambda text, *a, **k: pasted.append(text) or True)
    monkeypatch.setattr(main.storage, "update_dictation", lambda *a, **k: True)
    monkeypatch.setattr(main.polisher, "polish", lambda text, **k: text)
    monkeypatch.setattr(main, "smart_format", lambda text, *a: text)
    app._process_dictation_pipeline(current, object(), 1.0, record_id=1, use_streaming=True)
    assert pasted == ["whole buffer"]


def test_polish_gets_usable_time_after_slow_cloud_transcription():
    now = time.monotonic()
    deadline = main._polish_deadline(now - 3, "balanced", 25, cloud_stt=True)
    assert deadline - now >= 2.5


def test_polishing_off_preserves_repetitions_and_meaningful_words(monkeypatch):
    monkeypatch.setattr(polishing.storage, "get_setting", lambda key, default=None: False if key == "polishing_enabled" else default)
    monkeypatch.setattr(polishing, "_apply_dictionary_safely", lambda text: text)
    engine = polishing.TextPolisher()
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *a, **k: pytest.fail("OFF sent a remote request"))
    text = "The ER team said very good very good. I like you and you know the answer."
    assert engine.polish(text, cleanup_level="cleanup_high") == text


@pytest.mark.parametrize("source,candidate", [
    ("Please do not delete the backup before we finish the review today.", "Please do delete the backup before we finish the review today."),
    ("Send 25 files to the review team before Friday morning please.", "Send files to the review team before Friday morning please."),
])
def test_cleanup_rejects_lost_negation_or_quantity(source, candidate):
    assert not polishing._candidate_preserves_content(source, candidate)


def test_provider_error_status_crosses_worker_boundary():
    engine = polishing.TextPolisher()

    def denied(*args, **kwargs):
        engine._last_attempt_status = "http_401"
        return None

    engine._try_provider_call = denied
    assert engine._try_provider_call_with_deadline("groq", "fake", "policy", "words", None, 1, time.monotonic()+1) is None
    assert engine._last_attempt_status == "http_401"


def test_unrecognized_wake_phrase_preserves_dictation_words():
    text = "Hey Voice Flow, the microphone sounds different today."
    parsed = detect_voice_command(text)
    assert parsed.command is None
    assert parsed.content == text


@pytest.mark.parametrize("phrase", [
    "Hey Voice Flow, make this a prompt: build a calendar with offline support",
    "Hey Voice Flow, make this a prompt, build a calendar with offline support",
    "Build a calendar with offline support. Hey Voice Flow, make this as a prom.",
])
def test_prompt_command_keeps_inline_content(phrase):
    parsed = detect_voice_command(phrase)
    assert parsed.command is not None
    assert parsed.command.operation == "prompt_generation"
    assert "build a calendar with offline support" in parsed.content.lower()


@pytest.mark.parametrize("verb", ["polish", "rewrite", "clean up"])
def test_simple_cleanup_commands_request_ai(verb):
    from voice_flow.effective_style import resolve_effective_style
    parsed = detect_voice_command(f"Hey Voice Flow, {verb} this. Keep the complete wording.")
    assert parsed.command is not None
    effective = resolve_effective_style(session().resolved_style, parsed.command)
    assert effective.requires_ai
    assert parsed.content == "Keep the complete wording."


def test_literal_prom_dress_does_not_become_a_prompt_command():
    text = "Hey Voice Flow, make this a prom dress for the school play."
    parsed = detect_voice_command(text)
    assert parsed.command is None
    assert parsed.content == text


def test_stop_retains_final_driver_frame_in_archive_and_live_stream():
    import numpy as np
    from voice_flow.audio import AudioRecorder
    recorder = AudioRecorder()
    recorder._recording = True
    recorder._native_sr = 16000
    seen = []
    recorder.on_audio_frame = lambda frame, sr: seen.append(frame)
    frame = np.full((1024, 1), .04, dtype=np.float32)
    recorder._audio_callback(frame, 1024, None, None)
    recorder._stream = SimpleNamespace(
        stop=lambda: recorder._audio_callback(frame, 1024, None, None), close=lambda: None,
    )
    full, tail, _ = recorder.stop_and_take_open_chunk()
    assert full.size == 2048
    assert tail.size == 2048
    assert len(seen) == 2
    assert not recorder.is_recording


@pytest.mark.parametrize("failure", ["deadline", "push", "finish"])
def test_native_stream_failure_cannot_publish_partial_success(monkeypatch, failure):
    import ctypes
    import numpy as np
    import voice_flow.nemotron_engine as native

    class DLL:
        finished = False
        emitted = False

        def nemo_speech_asr_recognition_options_default(self):
            return native._RecognitionOptions()

        def nemo_speech_asr_streaming_recognize(self, handle, opts, output):
            output._obj.value = 1
            return 0

        def nemo_speech_asr_stream_push_f32(self, *args):
            return 1 if failure == "push" else 0

        def nemo_speech_asr_stream_finish(self, *args):
            self.finished = True
            return 1 if failure == "finish" else 0

        def nemo_speech_asr_stream_next(self, handle, output):
            if self.finished and not self.emitted:
                output._obj.value = 2
                self.emitted = True
            return 0

        def nemo_speech_asr_result_transcript(self, *args):
            return b"Only the first words"

        def nemo_speech_asr_result_is_final(self, *args):
            return True

        def nemo_speech_asr_result_destroy(self, *args):
            pass

        def nemo_speech_asr_stream_close(self, *args):
            pass

    dll = DLL()
    monkeypatch.setattr(native, "get_nemo_dll", lambda: dll)
    engine = SimpleNamespace(rec_handle=ctypes.c_void_p(1), spec={}, lock=threading.Lock())
    stream = native.NemotronStreamTranscriber(engine=engine)
    stream.submit_frame(np.ones(1600, dtype=np.float32), 16000)
    stream.end_session(deadline=time.monotonic()-1 if failure == "deadline" else None)
    stream._run()
    assert stream.had_failures()
    assert not stream.completed_successfully()
    assert stream.collect(0) == ""
