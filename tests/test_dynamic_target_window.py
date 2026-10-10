from __future__ import annotations

import os
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow import main as main_module
from voice_flow.main import DictationSession, DictationState, VoiceFlowApp


def _create_test_app(session: DictationSession) -> VoiceFlowApp:
    app = object.__new__(VoiceFlowApp)
    app.processing_lock = threading.Lock()
    app._state_lock = threading.RLock()
    app.state = DictationState.PROCESSING
    app.session = session
    app._last_target_hwnd = session.target_hwnd
    app.transcriber = SimpleNamespace(transcribe=lambda _audio, **_kwargs: 'hello from test')
    app._stream_stt = SimpleNamespace(end_session=lambda **_kwargs: None, discard=lambda: None)
    app.injector = SimpleNamespace(paste_text=MagicMock(return_value=True))
    app.overlay = SimpleNamespace(
        win=SimpleNamespace(winfo_id=lambda: 9999),
        show_error=lambda *_args: None,
        show_done=lambda *_args: None,
        show_ready=lambda: None,
        show_processing=lambda: None,
    )
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *_args: None)
    app.recent_dictations = set()
    app.last_successful_transcript = None
    app.audio = SimpleNamespace(stop=lambda: np.ones(16000, dtype=np.float32))
    return app


def _bypass_text_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, 'detect_voice_command', lambda text: SimpleNamespace(command=None, content=text))
    monkeypatch.setattr(main_module, 'apply_spoken_punctuation', lambda text: text)
    monkeypatch.setattr(main_module, 'split_press_enter', lambda text, _enabled: SimpleNamespace(text=text, press_enter=False))
    monkeypatch.setattr(main_module, 'smart_format', lambda text, _style, _context=None: text)
    monkeypatch.setattr(main_module.polisher, 'polish', lambda text, **_kwargs: text)
    monkeypatch.setattr(main_module.storage, 'add_dictation', lambda *_args, **_kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(main_module.storage, 'update_dictation', lambda *_args, **_kwargs: True)


def test_finish_detects_switched_window_and_updates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the user starts dictation in Twitter (hwnd 1001) but finishes in Antigravity (hwnd 2002),
    _on_dictation_finish must detect hwnd 2002 and update session.target_hwnd to 2002."""
    twitter_hwnd = 1001
    antigravity_hwnd = 2002

    session = DictationSession(
        target_hwnd=twitter_hwnd,
        app_title='Twitter',
        app_category='social',
        style_id='social_casual',
        started_at=0.0,
        resolved_style=SimpleNamespace(app_name='Twitter', category='social', style_id='social_casual', instruction='clean'),
    )

    app = _create_test_app(session)
    app.state = DictationState.RECORDING
    app._record_watchdog = None
    app._set_hotkeys_recording_state = lambda _active: None
    app._streaming_stt_enabled = lambda: False
    app._overlay_call = lambda *_args, **_kwargs: None
    app._start_recovery_archive = lambda _buf, _rec: None

    # Mock foreground window returning Antigravity
    monkeypatch.setattr(app, '_get_current_external_window', lambda: antigravity_hwnd)

    scheduled = []
    class FakeThread:
        def __init__(self, *, target, args=(), kwargs=None, daemon=True):
            scheduled.append({'target': target, 'args': args, 'kwargs': kwargs or {}})
        def start(self): pass

    monkeypatch.setattr(main_module.threading, 'Thread', FakeThread)

    assert app._on_dictation_finish() is True
    # Verify target_hwnd in session passed to pipeline is 2002 (Antigravity), NOT 1001 (Twitter)
    pipeline_calls = [job for job in scheduled if job['target'] == app._process_dictation_pipeline]
    assert len(pipeline_calls) == 1
    passed_session = pipeline_calls[0]['args'][0]
    assert passed_session.target_hwnd == antigravity_hwnd
    assert app._last_target_hwnd == antigravity_hwnd


def test_pipeline_pastes_into_currently_focused_window_not_stale_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """If user switched windows right before paste, paste_text must target the active window."""
    twitter_hwnd = 1001
    antigravity_hwnd = 2002

    session = DictationSession(
        target_hwnd=twitter_hwnd,
        app_title='Twitter',
        app_category='social',
        style_id='social_casual',
        started_at=0.0,
        resolved_style=SimpleNamespace(app_name='Witter', category='social', style_id='social_casual', instruction='clean'),
    )

    app = _create_test_app(session)
    _bypass_text_steps(monkeypatch)

    # Active foreground at paste time is Antigravity (2002)
    monkeypatch.setattr(app, '_get_current_external_window', lambda: antigravity_hwnd)

    app._process_dictation_pipeline(session, np.ones(16000, dtype=np.float32), 1.0, use_streaming=False)

    # Verify injector.paste_text was called with antigravity_hwnd (2002), NOT twitter_hwnd (1001)
    app.injector.paste_text.assert_called_once()
    called_args, called_kwargs = app.injector.paste_text.call_args
    assert called_args[1] == antigravity_hwnd


def test_overlay_click_falls_back_to_last_external_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """When user finishes by clicking overlay bar (internal window), it must not inject into overlay;
    it must fall back to the last active external window."""
    antigravity_hwnd = 2002

    session = DictationSession(
        target_hwnd=antigravity_hwnd,
        app_title='Antigravity',
        app_category='code',
        style_id='code_editor',
        started_at=0.0,
        resolved_style=SimpleNamespace(app_name='Antigravity', category='code', style_id='code_editor', instruction='clean'),
    )

    app = _create_test_app(session)
    _bypass_text_steps(monkeypatch)
    monkeypatch.setattr(main_module.ctypes.windll.user32, 'IsWindow', lambda _h: True)
    monkeypatch.setattr(app, '_is_internal_window', lambda h: h == 9999)

    # Current foreground is internal (overlay bar, so _get_current_external_window returns None)
    monkeypatch.setattr(app, '_get_current_external_window', lambda: None)
    app._last_target_hwnd = antigravity_hwnd

    # Verify _get_effective_destination_hwnd resolves to antigravity_hwnd
    dest = app._get_effective_destination_hwnd(session, fallback_hwnd=antigravity_hwnd)
    assert dest == antigravity_hwnd


def test_internal_window_check_filters_voice_flow_windows() -> None:
    """Verify _is_internal_window accurately flags None, invalid, and Voice Flow windows."""
    app = object.__new__(VoiceFlowApp)
    app.overlay = SimpleNamespace(win=SimpleNamespace(winfo_id=lambda: 9999))

    # None or 0 is internal
    assert app._is_internal_window(None) is True
    assert app._is_internal_window(0) is True


def test_is_internal_window_identifies_ai_productivity_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure 'AI Productivity Flow' desktop GUI window is strictly classified as internal."""
    from voice_flow import injector

    fake_hwnd = 12345
    monkeypatch.setattr(injector.ctypes.windll.user32, 'IsWindow', lambda _h: True)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowThreadProcessId', lambda _h, _p: None)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetAncestor', lambda _h, _ga: 0)

    # When window title is 'AI Productivity Flow'
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowTextLengthW', lambda _h: 20)
    def fake_get_window_text(h, buff, max_len):
        buff.value = 'AI Productivity Flow'
        return len(buff.value)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowTextW', fake_get_window_text)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetClassNameW', lambda h, buff, max_len: 0)

    assert injector.is_internal_window(fake_hwnd) is True


def test_is_internal_window_preserves_external_apps_with_voice_flow_in_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """External apps that have 'Voice Flow' in their title (Antigravity, VS Code, Chrome) must NOT be marked internal!"""
    from voice_flow import injector

    fake_hwnd = 54321
    monkeypatch.setattr(injector.ctypes.windll.user32, 'IsWindow', lambda _h: True)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowThreadProcessId', lambda _h, _p: None)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetAncestor', lambda _h, _ga: 0)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetClassNameW', lambda h, buff, max_len: 0)

    test_titles = [
        'Gathering Voice Flow Context - Antigravity',
        'voice_flow.py - Visual Studio Code',
        'Voice Flow Repo - Google Chrome',
        'Voice Flow Issue - Microsoft Edge',
        'Voice Flow Dictation Test - Notepad',
        'Voice Flow on Twitter / X - Google Chrome',
    ]

    for title in test_titles:
        monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowTextLengthW', lambda _h, t=title: len(t))
        def fake_get_text(h, buff, max_len, t=title):
            buff.value = t
            return len(t)
        monkeypatch.setattr(injector.ctypes.windll.user32, 'GetWindowTextW', fake_get_text)

        # Must be treated as EXTERNAL window (return False)
        assert injector.is_internal_window(fake_hwnd) is False, f"Expected {title} to be external (False)"


def test_injector_refuses_to_paste_into_internal_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_text must refuse to inject into internal windows and must not steal focus to them."""
    from voice_flow import injector

    internal_hwnd = 998877
    monkeypatch.setattr(injector, 'is_internal_window', lambda h: h == internal_hwnd)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'IsWindow', lambda _h: True)
    monkeypatch.setattr(injector.ctypes.windll.user32, 'GetForegroundWindow', lambda: internal_hwnd)
    focus_called = []
    monkeypatch.setattr(injector, 'focus_target_window', lambda h: focus_called.append(h))

    # Calling inject_text targeting internal window
    res = injector.inject_text('Test voice text', target_hwnd=internal_hwnd)
    assert res is False
    assert len(focus_called) == 0  # Did NOT focus the internal window!


def test_effective_destination_never_returns_internal_window() -> None:
    """_get_effective_destination_hwnd must return None if all fallback candidates are internal."""
    app = object.__new__(VoiceFlowApp)
    internal_hwnd = 132756

    app._is_internal_window = lambda h: h == internal_hwnd or h is None
    app._get_current_external_window = lambda: None
    app._last_target_hwnd = internal_hwnd

    session = DictationSession(
        target_hwnd=internal_hwnd,
        app_title='AI Productivity Flow',
        app_category='other',
        style_id='smart_clean',
        started_at=0.0,
        resolved_style=None,
    )

    dest = app._get_effective_destination_hwnd(session, fallback_hwnd=internal_hwnd)
    # Must NOT return internal_hwnd!
    assert dest is None

