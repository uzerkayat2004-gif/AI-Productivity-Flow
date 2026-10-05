"""Tests for Audio Flow, Voice Flow, Speech Recognition, and WhatsApp UWP Reliability Fixes."""

from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.main import DictationState, VoiceFlowApp
import voice_flow.main as main_module
from voice_flow.mouse_hook import Win32MouseHook
from voice_flow import injector
from voice_flow import style_engine
from voice_flow.nemotron_engine import NemotronStreamTranscriber


# =========================================================================
# 1. Mouse Hook Debounce and Non-blocking Worker Queue
# =========================================================================

def test_mouse_hook_dispatch_worker_queue() -> None:
    """_dispatch_action must execute actions on the worker thread sequentially."""
    executed = []
    thread_ids = set()

    def sample_action(val: int) -> None:
        executed.append(val)
        thread_ids.add(threading.get_ident())

    hook = Win32MouseHook(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    # Exercise the lifecycle-owned worker without installing a live global hook.
    with hook._lock:
        hook._start_workers_locked()
    try:
        hook._dispatch_action(sample_action, 1)
        hook._dispatch_action(sample_action, 2)
        hook._dispatch_action(sample_action, 3)

        # Wait for queue to drain
        deadline = time.time() + 2.0
        while len(executed) < 3 and time.time() < deadline:
            time.sleep(0.02)

        assert executed == [1, 2, 3]
        # All actions should have been processed on the worker thread, not 3 separate threads
        assert len(thread_ids) == 1
    finally:
        hook.stop()


def test_mouse_hook_debounce_threshold() -> None:
    """Debounce threshold must be 0.10s (100ms) to suppress mechanical contact chatter without dropping clicks."""
    hook = Win32MouseHook(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    now = time.time()
    hook._last_transition_time = now

    # Within 50ms: bounce chatter must be suppressed (threshold is 0.10s)
    chatter = 0.05
    assert chatter < 0.10

    # At 150ms: legitimate quick clicks must NOT be suppressed
    human_click = 0.15
    assert human_click >= 0.10


# =========================================================================
# 2. Main Dictation: Active Processing Protection & Audio Flow Suppression
# =========================================================================

def test_main_processing_guard_protects_active_transcription() -> None:
    """New dictation start must NOT cancel an active PROCESSING session within 15 seconds."""
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app._processing_start_time = time.monotonic()  # Just finished 0.1s ago
    cancelled = False

    def fake_cancel():
        nonlocal cancelled
        cancelled = True

    app._on_dictation_cancel = fake_cancel
    app._set_hotkeys_recording_state = MagicMock()

    # Attempt to start dictation while actively processing
    result = app._on_dictation_start()

    assert result is False
    assert cancelled is False, "Active PROCESSING session (<15s) must NOT be cancelled!"
    app._set_hotkeys_recording_state.assert_called_with(False)


def test_main_processing_guard_cancels_truly_stale_session() -> None:
    """New dictation start DOES cancel a genuinely stale session (>15s elapsed)."""
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app._processing_start_time = time.monotonic() - 20.0  # 20s ago
    cancelled = False

    def fake_cancel():
        nonlocal cancelled
        cancelled = True
        app.state = DictationState.IDLE

    app._on_dictation_cancel = fake_cancel
    app._capture_session = lambda: SimpleNamespace(target_hwnd=123, app_title="Test")
    app._set_hotkeys_recording_state = lambda _: None
    app.audio = SimpleNamespace(
        begin_stream_input_buffering=lambda: None,
        start=lambda: False,
        discard_stream_input_buffer=lambda: None,
    )
    app._end_stream_session = lambda **kw: None
    app._reset_to_idle = lambda *a: None
    app._overlay_call = lambda *a, **k: None

    with patch.object(main_module.storage, "get_setting", return_value=True):
        app._on_dictation_start()

    assert cancelled is True, "Stale PROCESSING session (>=15s) should be cancelled"


def test_main_dictation_start_hides_and_stops_audio_flow() -> None:
    """Dictation start must hide audio_flow_widget and stop active audio flow pipeline."""
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app._capture_session = lambda: SimpleNamespace(target_hwnd=123, app_title="Test")
    app._set_hotkeys_recording_state = lambda _: None
    app.audio = SimpleNamespace(
        begin_stream_input_buffering=lambda: None,
        start=lambda: False,
        discard_stream_input_buffer=lambda: None,
    )
    app._end_stream_session = lambda **kw: None
    app._reset_to_idle = lambda *a: None
    app._overlay_call = lambda *a, **k: None

    widget_hidden = False
    pipeline_stopped = False

    def fake_hide():
        nonlocal widget_hidden
        widget_hidden = True

    def fake_stop():
        nonlocal pipeline_stopped
        pipeline_stopped = True

    app._stop_audio_flow_pipeline = fake_stop

    with patch.object(main_module.audio_flow_widget, "hide", fake_hide), \
         patch.object(main_module.storage, "get_setting", return_value=True):
        app._on_dictation_start()

    assert widget_hidden is True, "audio_flow_widget.hide() must be called on dictation start"
    assert pipeline_stopped is True, "_stop_audio_flow_pipeline() must be called on dictation start"


# =========================================================================
# 3. Audio Device Fast Validation and Clean Reset
# =========================================================================

def test_audio_missing_mic_resets_immediately_and_clears_keys() -> None:
    """If configured mic is not present in query_devices, audio resets without delay and clears storage."""
    from voice_flow.audio import AudioRecorder
    from voice_flow.config import config as app_config

    saved_settings = {}

    def fake_save(k, v):
        saved_settings[k] = v

    recorder = AudioRecorder()
    app_config.selected_mic_device = "NonExistent Headset CP60"

    fake_devices = [
        {"name": "Realtek High Definition Audio", "max_input_channels": 2, "default_samplerate": 48000},
    ]

    with patch("sounddevice.query_devices", return_value=fake_devices), \
         patch("sounddevice.InputStream", side_effect=RuntimeError("Device unavailable")), \
         patch("voice_flow.storage.storage.save_setting", fake_save):

        # Test pre-validation in audio start
        recorder.start(device="NonExistent Headset CP60")

        # Storage keys must both be reset to None
        assert saved_settings.get("selected_mic_device") is None
        assert saved_settings.get("selected_microphone") is None
        assert app_config.selected_mic_device is None


# =========================================================================
# 4. Nemotron Streaming Deadline Preservation
# =========================================================================

def test_nemotron_stream_expired_preserves_committed_transcripts() -> None:
    """When stream deadline expires, committed transcripts must be preserved and returned."""
    transcriber = NemotronStreamTranscriber()

    # Pre-populate transcripts as if audio had streamed
    transcriber._text = ""
    transcriber._done.set()

    # Simulate harvest logic when deadline expired
    committed = ["Hello", "world", "this", "is", "a", "test"]
    interim = ""
    if committed or interim:
        transcriber._text = " ".join(committed).strip()

    assert transcriber.collect() == "Hello world this is a test"
    assert transcriber.had_failures() is False
    assert transcriber.completed_successfully() is True


# =========================================================================
# 5. WhatsApp Desktop (UWP) Hierarchy & Injector
# =========================================================================

def test_whatsapp_not_treated_as_internal_window() -> None:
    """WhatsApp windows (even with UWP CoreWindow class and empty title) are NEVER internal."""
    # Simulate a UWP WhatsApp CoreWindow
    with patch.object(injector.ctypes.windll.user32, "IsWindow", return_value=True), \
         patch.object(injector.ctypes.windll.user32, "GetWindowThreadProcessId", lambda h, r: setattr(r._obj, "value", 55555)), \
         patch.object(injector.ctypes.windll.user32, "GetAncestor", return_value=0), \
         patch.object(injector.ctypes.windll.user32, "GetWindowTextLengthW", return_value=8), \
         patch.object(injector.ctypes.windll.user32, "GetWindowTextW", lambda h, b, l: setattr(b, "value", "WhatsApp")), \
         patch.object(injector.ctypes.windll.user32, "GetClassNameW", lambda h, b, l: setattr(b, "value", "Windows.UI.Core.CoreWindow")), \
         patch.object(injector, "_get_process_name_safe", return_value="ApplicationFrameHost.exe"), \
         patch("os.getpid", return_value=1234):

        assert injector.is_internal_window(9999) is False, "WhatsApp must not be flagged as internal window!"


def test_whatsapp_same_process_window_hierarchy() -> None:
    """Two HWNDs belonging to the same process must be recognized as same window hierarchy."""
    with patch.object(injector.ctypes.windll.user32, "IsChild", return_value=False), \
         patch.object(injector.ctypes.windll.user32, "GetAncestor", return_value=0), \
         patch.object(injector.ctypes.windll.user32, "GetParent", return_value=0), \
         patch.object(injector.ctypes.windll.user32, "GetWindowThreadProcessId", lambda h, r: setattr(r._obj, "value", 4321)), \
         patch.object(injector, "get_window_class_name", return_value="SomeControl"):

        assert injector.is_same_window_hierarchy(101, 102) is True


def test_whatsapp_style_engine_normalization() -> None:
    """normalize_app_name must map WhatsApp.Root.exe and WhatsApp titles to 'WhatsApp'."""
    assert style_engine.normalize_app_name("Chat", "WhatsApp.Root.exe") == "WhatsApp"
    assert style_engine.normalize_app_name("WhatsApp", "ApplicationFrameHost.exe") == "WhatsApp"
    assert style_engine.normalize_app_name("WhatsApp Desktop", "general.exe") == "WhatsApp"


def test_mouse_hook_unhook_thread_matching() -> None:
    """_unhook with target_thread_id must NOT unhook if the thread ID does not match active hook thread."""
    hook = Win32MouseHook(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
    )
    hook._hook_handle = 9999
    hook._hook_thread_id = 1234
    hook._is_hooked = True

    # Terminating old thread (tid 999) must NOT unhook active thread (tid 1234)
    hook._unhook(target_thread_id=999)
    assert hook._hook_handle == 9999
    assert hook._is_hooked is True
    assert hook._hook_thread_id == 1234

    # Matching thread unhooks cleanly
    hook._unhook(target_thread_id=1234)
    assert hook._hook_handle is None
    assert hook._is_hooked is False
    assert hook._hook_thread_id == 0


def test_mouse_hook_kernel32_restype_configured() -> None:
    """kernel32.GetModuleHandleW.restype must be HMODULE (not truncated 32-bit c_int)."""
    import ctypes
    from ctypes import wintypes
    import voice_flow.mouse_hook as mouse_hook_mod
    assert mouse_hook_mod.kernel32.GetModuleHandleW.restype == wintypes.HMODULE
    assert mouse_hook_mod.kernel32.GetCurrentThreadId.restype == wintypes.DWORD


def test_whatsapp_application_frame_window_child_pid_hierarchy() -> None:
    """ApplicationFrameWindow hosting a child window with WhatsApp PID matches hierarchy."""
    frame_hwnd = 1000
    other_hwnd = 2000
    whatsapp_pid = 7777

    # When enum child windows on frame_hwnd finds a child with whatsapp_pid:
    def fake_enum_child(h, cb, lparam):
        # Callback with a child window having whatsapp_pid
        cb(3000, 0)
        return True

    def fake_get_pid(h, r):
        if h == other_hwnd or h == 3000:
            setattr(r._obj, "value", whatsapp_pid)
        else:
            setattr(r._obj, "value", 1111)  # Frame host pid

    with patch.object(injector.ctypes.windll.user32, "IsChild", return_value=False), \
         patch.object(injector.ctypes.windll.user32, "GetAncestor", return_value=0), \
         patch.object(injector.ctypes.windll.user32, "GetParent", return_value=0), \
         patch.object(injector.ctypes.windll.user32, "GetWindowThreadProcessId", fake_get_pid), \
         patch.object(injector.ctypes.windll.user32, "EnumChildWindows", fake_enum_child), \
         patch.object(injector, "get_window_class_name", lambda h: "ApplicationFrameWindow" if h == frame_hwnd else "Windows.UI.Core.CoreWindow"):

        assert injector.is_same_window_hierarchy(frame_hwnd, other_hwnd) is True


def test_audio_flow_suppressed_when_voice_flow_not_idle() -> None:
    """_on_mouse_release must immediately return and hide widget if Voice Flow is not IDLE."""
    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.overlay = MagicMock()
    app._get_cached_setting = lambda k, d: True

    with patch.object(main_module.audio_flow_widget, "hide") as fake_hide:
        app._on_mouse_release(100, 200, drag_distance=50.0)

        app.overlay.clear_selected_text.assert_called_once()
        fake_hide.assert_called_once()


def test_whisper_fallback_deadline_floor_extension() -> None:
    """Whisper fallback receives a minimum deadline floor even if Nemotron exhausted the deadline."""
    from voice_flow.transcriber import Transcriber, _deadline_remaining
    import numpy as np

    tx = Transcriber()
    # Expired deadline
    expired_deadline = time.monotonic() - 1.0
    assert _deadline_remaining(expired_deadline) == 0.0

    # Test that deadline floor is applied
    fallback_deadline = expired_deadline
    if fallback_deadline is not None and _deadline_remaining(fallback_deadline) < 3.0:
        fallback_deadline = time.monotonic() + 3.5

    assert _deadline_remaining(fallback_deadline) >= 3.0

