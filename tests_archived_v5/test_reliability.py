from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from pynput import keyboard

from voice_flow import injector
from voice_flow.hotkeys import InputTriggerListener, WM_MBUTTONDOWN, WM_MBUTTONUP
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp
from voice_flow.audio import AudioRecorder


class FakeHotkeys:
    def __init__(self): self.calls = []
    def set_recording_state(self, *args): self.calls.append(args)


class FakeOverlay:
    def __init__(self): self.calls = []
    def show_recording(self, **kwargs): self.calls.append(("recording", kwargs))
    def show_processing(self): self.calls.append(("processing",))
    def show_ready(self): self.calls.append(("ready",))
    def show_done(self, text): self.calls.append(("done", text))
    def show_error(self, text): self.calls.append(("error", text))


class FakeAudio:
    level = 0.0
    def __init__(self, started=True, audio=None): self.started, self.audio, self.stop_calls = started, audio if audio is not None else np.ones(6400, dtype=np.float32), 0
    def start(self): return self.started
    def stop(self): self.stop_calls += 1; return self.audio
    def cancel(self): pass


class FakeInjector:
    def __init__(self, success=True): self.success, self.calls = success, []
    def paste_text(self, text, hwnd, press_enter=False): self.calls.append((text, hwnd, press_enter)); return self.success


def make_app(audio=None, injector_instance=None):
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.session = None
    app.last_error = None
    app.last_successful_transcript = None
    app.hotkeys = FakeHotkeys()
    app.overlay = FakeOverlay()
    app.audio = audio or FakeAudio()
    app.injector = injector_instance or FakeInjector()
    app._capture_session = lambda: DictationSession(101, "Captured App", "work", "captured style", 1.0)
    return app


class StateMachineTests(unittest.TestCase):
    def test_microphone_failure_is_recoverable_error(self):
        app = make_app(audio=FakeAudio(started=False))
        self.assertFalse(app._on_dictation_start("ptt"))
        self.assertEqual(app.state, DictationState.ERROR)
        self.assertIn("Microphone", app.last_error)
        self.assertEqual(app.overlay.calls[-1][0], "error")

    def test_hub_start_without_external_target_is_rejected_visibly(self):
        app = make_app()
        app._capture_session = lambda: None
        self.assertFalse(app._on_dictation_start("hands_free"))
        self.assertEqual(app.state, DictationState.ERROR)
        self.assertEqual(app.overlay.calls[-1], ("error", "Focus a text field first"))

    def test_capture_uses_one_hwnd_for_title_and_style(self):
        app = make_app()
        app.__dict__.pop("_capture_session")
        fake_windll = SimpleNamespace(user32=SimpleNamespace(GetForegroundWindow=lambda: 555))
        with patch.object(__import__("voice_flow.main", fromlist=["ctypes"]).ctypes, "windll", fake_windll, create=True), \
             patch("voice_flow.main.get_window_title_for_hwnd", return_value="Mail editor") as title, \
             patch("voice_flow.main.style_engine.get_session_style_for_hwnd", return_value=("Outlook", "email", "email_formal", "cleanup_light")) as style:
            session = app._capture_session()
        self.assertEqual(session.target_hwnd, 555)
        title.assert_called_once_with(555)
        style.assert_called_once_with(555)

    def test_processing_rejects_new_recording(self):
        app = make_app()
        app.state = DictationState.PROCESSING
        self.assertFalse(app._on_dictation_start("hands_free"))
        self.assertEqual(app.state, DictationState.PROCESSING)

    def test_concurrent_finish_only_transitions_one_recording_session(self):
        app = make_app(audio=FakeAudio(audio=np.array([], dtype=np.float32)))
        self.assertTrue(app._on_dictation_start("ptt"))
        results = []
        threads = [threading.Thread(target=lambda: results.append(app._on_dictation_finish())) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(1)
        self.assertEqual(results.count(True), 0)  # empty audio is a recoverable failure
        self.assertEqual(app.state, DictationState.ERROR)
        self.assertEqual(app.audio.stop_calls, 1)

    def test_session_target_and_style_are_used_after_focus_changes(self):
        app = make_app()
        session = DictationSession(777, "Original App", "email", "original style", 2.0)
        app.session = session
        app.state = DictationState.PROCESSING
        app.transcriber = SimpleNamespace(transcribe=lambda audio: "hello world")
        with patch("voice_flow.main.polisher.polish", side_effect=lambda text, style: text if style == "original style" else "wrong"), \
             patch("voice_flow.main.dictionary_engine.apply_dictionary_post_processing", side_effect=lambda text: text), \
             patch("voice_flow.main.storage.add_dictation", return_value=SimpleNamespace(id=1)), \
             patch("voice_flow.main.style_engine.get_style_for_current_app", side_effect=AssertionError("must not re-read foreground app")):
            app._process_dictation_pipeline(session, np.ones(6400, dtype=np.float32), 0.4)
        self.assertEqual(app.injector.calls, [("Hello world.", 777, False)])
        self.assertEqual(app.last_successful_transcript, "Hello world.")
        self.assertEqual(app.state, DictationState.IDLE)

    def test_paste_failure_keeps_last_success_and_recovers(self):
        app = make_app(injector_instance=FakeInjector(success=False))
        session = DictationSession(777, "Original App", "email", "style", 2.0)
        app.session, app.state = session, DictationState.PROCESSING
        app.transcriber = SimpleNamespace(transcribe=lambda audio: "hello")
        with patch("voice_flow.main.polisher.polish", return_value="hello"), \
             patch("voice_flow.main.dictionary_engine.apply_dictionary_post_processing", return_value="hello"), \
             patch("voice_flow.main.storage.add_dictation", return_value=SimpleNamespace(id=1)):
            app._process_dictation_pipeline(session, np.ones(6400, dtype=np.float32), 0.4)
        self.assertEqual(app.last_successful_transcript, "Hello.")
        self.assertEqual(app.state, DictationState.ERROR)

    def test_stale_session_cannot_persist_or_paste(self):
        app = make_app()
        stale = DictationSession(1, "Old", "work", "style", 1)
        app.session = DictationSession(2, "New", "email", "style", 2)
        app.state = DictationState.PROCESSING
        app.transcriber = SimpleNamespace(transcribe=lambda _: self.fail("stale work must not run"))
        app._process_dictation_pipeline(stale, np.ones(6400, dtype=np.float32), 0.4)
        self.assertEqual(app.injector.calls, [])


class TriggerTests(unittest.TestCase):
    def wait_dispatch(self, listener):
        listener._dispatch_queue.join()

    def test_middle_double_tap_locks_hands_free_not_single_tap_toggle(self):
        calls = []
        listener = InputTriggerListener(lambda mode: calls.append(("start", mode)) or True, lambda: calls.append(("finish",)) or True, lambda: calls.append(("cancel",)) or True, lambda: calls.append(("lock",)) or True)
        self.addCleanup(listener.stop)
        with patch("voice_flow.hotkeys.time.monotonic", side_effect=[1.0, 1.1, 1.2, 1.3]):
            listener._win32_mouse_filter(WM_MBUTTONDOWN, None)
            listener._win32_mouse_filter(WM_MBUTTONUP, None)
            listener._win32_mouse_filter(0x0209, None)  # WM_MBUTTONDBLCLK
            listener._win32_mouse_filter(WM_MBUTTONUP, None)
        self.wait_dispatch(listener)
        self.assertEqual(calls, [("start", "ptt"), ("lock",)])
        self.assertEqual(listener._recording_mode, "hands_free")

    def test_ctrl_win_space_starts_and_toggles_hands_free(self):
        calls = []
        listener = InputTriggerListener(lambda mode: calls.append(("start", mode)), lambda: calls.append(("finish",)), lambda: None)
        self.addCleanup(listener.stop)
        with patch("voice_flow.hotkeys._is_ctrl_down", return_value=True), \
             patch("voice_flow.hotkeys._is_win_down", return_value=True):
            listener._on_key_press(keyboard.Key.space)
            listener._on_key_release(keyboard.Key.space)
            listener._on_key_press(keyboard.Key.space)
        self.wait_dispatch(listener)
        self.assertEqual(calls, [("start", "hands_free"), ("finish",)])

    def test_escape_cancels_any_recording_mode(self):
        calls = []
        listener = InputTriggerListener(lambda mode: None, lambda: None, lambda: calls.append("cancel"))
        self.addCleanup(listener.stop)
        listener.set_recording_state(True, "hands_free")
        listener._on_key_press(keyboard.Key.esc)
        self.wait_dispatch(listener)
        self.assertEqual(calls, ["cancel"])
        self.assertFalse(listener._is_recording)

    def test_rejected_start_resynchronizes_optimistic_listener_state(self):
        listener = InputTriggerListener(lambda mode: False, lambda: True, lambda: True)
        self.addCleanup(listener.stop)
        listener._dispatch("start", listener._on_start, "ptt")
        listener._is_recording, listener._recording_mode = True, "ptt"
        self.wait_dispatch(listener)
        self.assertFalse(listener._is_recording)

    def test_stop_shuts_down_dispatch_worker_idempotently(self):
        listener = InputTriggerListener(lambda mode: True, lambda: True, lambda: True)
        listener.stop()
        listener.stop()
        self.assertTrue(listener._worker_stopped)
        self.assertFalse(listener._dispatch_worker.is_alive())

    def test_key_repeat_dispatches_copy_once_per_physical_press(self):
        calls = []
        listener = InputTriggerListener(lambda mode: True, lambda: True, lambda: True, on_copy_last=lambda: calls.append("copy") or True)
        self.addCleanup(listener.stop)
        listener._shift_down = listener._alt_down = True
        key = keyboard.KeyCode.from_char("x")
        listener._on_key_press(key)
        listener._on_key_press(key)
        listener._on_key_release(key)
        listener._on_key_press(key)
        self.wait_dispatch(listener)
        self.assertEqual(calls, ["copy", "copy"])


class ClipboardTests(unittest.TestCase):
    def test_invalid_target_leaves_transcript_on_clipboard(self):
        copied = []
        with patch("voice_flow.injector.focus_target_window", return_value=False), \
             patch("voice_flow.injector.pyperclip.copy", side_effect=copied.append):
            self.assertFalse(injector.inject_text("recover me", 123))
        self.assertEqual(copied, ["recover me"])

    def test_invalid_excel_target_keeps_formatted_navigation_text(self):
        copied = []
        with patch("voice_flow.injector.get_window_title_for_hwnd", return_value="Excel"), \
             patch("voice_flow.injector.focus_target_window", return_value=False), \
             patch("voice_flow.injector.pyperclip.copy", side_effect=copied.append):
            self.assertFalse(injector.inject_text("next cell next row", 123))
        self.assertEqual(copied, ["\t \n"])

    def test_target_focus_title_controls_excel_formatting_not_old_foreground(self):
        copied = []
        with patch("voice_flow.injector.get_window_title_for_hwnd", return_value="Notepad"), \
             patch("voice_flow.injector.focus_target_window", return_value=True), \
             patch("voice_flow.injector.get_active_window_title", return_value="Budget - Excel"), \
             patch("voice_flow.injector._send_win32_ctrl_v"), \
             patch("voice_flow.injector.pyperclip.copy", side_effect=copied.append):
            self.assertTrue(injector.inject_text("next cell", 123))
        self.assertEqual(copied, ["\t"])

    def test_nominal_paste_keeps_formatted_transcript_on_clipboard(self):
        copied = []
        with patch("voice_flow.injector._wait_for_modifiers_released"), \
             patch("voice_flow.injector.get_active_window_title", return_value="Excel"), \
             patch("voice_flow.injector._send_win32_ctrl_v"), \
             patch("voice_flow.injector.pyperclip.copy", side_effect=copied.append):
            self.assertTrue(injector.inject_text("next cell", None))
        self.assertEqual(copied, ["\t"])

    def test_focus_cleanup_detaches_threads_after_focus_exception(self):
        attaches = []
        class User32:
            def IsWindow(self, hwnd): return True
            def GetForegroundWindow(self): return 10
            def IsIconic(self, hwnd): return False
            def GetWindowThreadProcessId(self, hwnd, _): return hwnd + 100
            def AttachThreadInput(self, source, dest, attach): attaches.append((source, dest, attach))
            def BringWindowToTop(self, hwnd): pass
            def SetForegroundWindow(self, hwnd): pass
            def SetFocus(self, hwnd): raise RuntimeError("boom")
        fake = SimpleNamespace(user32=User32(), kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 1))
        with patch.object(injector.ctypes, "windll", fake, create=True):
            self.assertFalse(injector.focus_target_window(20))
        self.assertEqual(attaches[-2:], [(110, 120, False), (1, 120, False)])


class AudioLifecycleTests(unittest.TestCase):
    def test_stop_waits_for_blocked_start_before_closing_live_stream(self):
        entered, release = threading.Event(), threading.Event()
        class Stream:
            stopped = closed = False
            def start(self): entered.set(); release.wait(1)
            def stop(self): self.stopped = True
            def close(self): self.closed = True
        stream = Stream()
        recorder = AudioRecorder()
        with patch("voice_flow.audio.sd.query_devices", return_value={"default_samplerate": 16000, "max_input_channels": 1}), \
             patch("voice_flow.audio.sd.InputStream", return_value=stream):
            starter = threading.Thread(target=lambda: recorder.start(device=1))
            starter.start(); self.assertTrue(entered.wait(1))
            stopper = threading.Thread(target=recorder.stop)
            stopper.start()
            self.assertTrue(stopper.is_alive())
            release.set(); starter.join(1); stopper.join(1)
        self.assertTrue(stream.stopped and stream.closed)
        self.assertIsNone(recorder._stream)


class OverlayStateTests(unittest.TestCase):
    def make_visible_bar(self):
        from voice_flow.overlay import FloatingOverlayBar
        callbacks = []
        def after(delay, callback):
            if delay == 0:
                callback()
            else:
                callbacks.append(callback)
        root = SimpleNamespace(
            after=after,
            winfo_screenwidth=lambda: 1000,
            winfo_screenheight=lambda: 800,
        )
        win = SimpleNamespace(
            deiconify=lambda: None, lift=lambda: None, attributes=lambda *args: None,
            geometry=lambda *_args: None,
        )
        bar = FloatingOverlayBar(root=root)
        bar.win = win
        bar._draw = lambda: None
        return bar, callbacks

    def test_paste_error_shows_paste_last_shortcut(self):
        from voice_flow.overlay import FloatingOverlayBar
        texts = []
        bar = FloatingOverlayBar()
        bar.canvas = SimpleNamespace(create_text=lambda *args, **kwargs: texts.append(kwargs["text"]))
        bar.error_message = "Could not paste transcript into the original target"
        bar._draw_error(240, 32)
        self.assertEqual(texts, ["Paste failed — Paste Last: Shift+Alt+Z"])

    def test_stale_animation_generation_does_not_create_a_second_chain(self):
        from voice_flow.overlay import FloatingOverlayBar
        scheduled, draws = [], []
        bar = FloatingOverlayBar()
        bar.state = "RECORDING"
        bar._animation_generation = 4
        bar._draw = lambda: draws.append("draw")
        bar.root = SimpleNamespace(after=lambda delay, callback: scheduled.append(callback))
        bar._animate(4)
        self.assertEqual(len(draws), 1)
        bar._animation_generation = 5  # PTT -> hands-free supersedes old chain
        scheduled.pop()()
        self.assertEqual(len(draws), 1)

    def test_stale_error_timeout_cannot_clobber_new_recording(self):
        bar, callbacks = self.make_visible_bar()
        bar.show_error("Microphone unavailable")
        stale_error_timeout = callbacks.pop(0)
        bar.show_recording(mode="hands_free")
        stale_error_timeout()
        self.assertEqual(bar.state, "RECORDING")

    def test_stale_done_timeout_cannot_clobber_new_recording(self):
        bar, callbacks = self.make_visible_bar()
        bar.show_done("done")
        stale_done_timeout = callbacks.pop(0)
        bar.show_recording(mode="hands_free")
        stale_done_timeout()
        self.assertEqual(bar.state, "RECORDING")


if __name__ == "__main__":
    unittest.main()
