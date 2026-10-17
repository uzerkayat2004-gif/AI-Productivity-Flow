"""macOS Audio Flow: selection listener, selection capture, hotkey, honest paste.

These run on any OS: every macOS framework call is replaced by a fake, and the
platform checks are patched, so CI on Windows/Linux exercises the Mac paths.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from voice_flow import hotkeys as hotkeys_module
from voice_flow import injector as injector_module
from voice_flow import main as main_module
from voice_flow import mouse_hook as mouse_hook_module
from voice_flow.main import DictationState, VoiceFlowApp
from voice_flow.platform import macos as macos_backend_module


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


# ---------------------------------------------------------------------------
# Mouse listener: macOS drags feed the same selection pipeline as Win32
# ---------------------------------------------------------------------------


class _FakeListener:
    def __init__(self, on_click):
        self.on_click = on_click
        self.daemon = False
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def is_alive(self):
        return self.started and not self.stopped


def _mac_hook(monkeypatch, releases):
    created: list[_FakeListener] = []

    def factory(on_click):
        listener = _FakeListener(on_click)
        created.append(listener)
        return listener

    monkeypatch.setattr(mouse_hook_module, "IS_MACOS", True)
    monkeypatch.setattr(mouse_hook_module, "IS_WINDOWS", False)
    monkeypatch.setattr(mouse_hook_module, "_create_macos_mouse_listener", factory)

    def on_release(x, y, dist, sx, sy):
        releases.append((x, y, round(dist), sx, sy, threading.current_thread().name))

    hook = mouse_hook_module.Win32MouseHook(
        on_start=lambda: None,
        on_finish=lambda: None,
        on_cancel=lambda: None,
        on_mouse_release=on_release,
    )
    return hook, created


def test_mac_start_installs_quartz_listener_instead_of_returning(monkeypatch):
    releases: list = []
    hook, created = _mac_hook(monkeypatch, releases)
    hook.start()
    try:
        assert len(created) == 1 and created[0].started and created[0].daemon
        assert hook.is_healthy()
        hook.start()  # idempotent while alive
        assert len(created) == 1
    finally:
        hook.stop()
    assert created[0].stopped
    assert not hook.is_healthy()


def test_mac_drag_runs_on_selection_worker_and_click_on_control_worker(monkeypatch):
    releases: list = []
    hook, created = _mac_hook(monkeypatch, releases)
    hook.start()
    left = SimpleNamespace(name="left")
    try:
        cb = created[0].on_click
        cb(100.0, 200.0, left, True, False)
        cb(400.4, 260.0, left, False, False)
        assert _wait_until(lambda: len(releases) == 1)
        x, y, dist, sx, sy, thread_name = releases[0]
        assert (x, y, sx, sy) == (400, 260, 100, 200)
        assert dist >= 300
        assert thread_name == "Win32MouseHookSelectionWorker"

        cb(50.0, 50.0, left, True, False)
        cb(52.0, 51.0, left, False, False)
        assert _wait_until(lambda: len(releases) == 2)
        assert releases[1][2] < 16
        assert releases[1][5] == "Win32MouseHookControlWorker"

        # Right/other buttons never reach the selection pipeline.
        cb(10.0, 10.0, SimpleNamespace(name="right"), True, False)
        cb(300.0, 10.0, SimpleNamespace(name="right"), False, False)
        time.sleep(0.1)
        assert len(releases) == 2
    finally:
        hook.stop()


def test_mac_listener_failure_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(mouse_hook_module, "IS_MACOS", True)
    monkeypatch.setattr(mouse_hook_module, "IS_WINDOWS", False)

    def boom(_cb):
        raise RuntimeError("no Quartz")

    monkeypatch.setattr(mouse_hook_module, "_create_macos_mouse_listener", boom)
    hook = mouse_hook_module.Win32MouseHook(lambda: None, lambda: None, lambda: None, on_mouse_release=lambda *a: None)
    hook.start()
    try:
        assert not hook.is_healthy()
        assert "Audio Flow selection widget disabled" in caplog.text
    finally:
        hook.stop()


# ---------------------------------------------------------------------------
# Audio Flow hotkey
# ---------------------------------------------------------------------------


def test_audio_flow_hotkey_parsing():
    assert hotkeys_module.parse_audio_flow_hotkey("Ctrl+Option+L") == (frozenset({"ctrl", "alt"}), "l")
    assert hotkeys_module.parse_audio_flow_hotkey("cmd+shift+space") == (frozenset({"cmd", "shift"}), "space")
    for disabled in ("", None, "none", "off", "L", "Ctrl+Option", "Ctrl+L+K"):
        assert hotkeys_module.parse_audio_flow_hotkey(disabled) is None


def test_platform_defaults_enable_audio_hotkey_only_on_mac(monkeypatch):
    monkeypatch.setattr(hotkeys_module.sys, "platform", "darwin")
    assert hotkeys_module.platform_input_defaults()["audio_flow_hotkey"] == "Ctrl+Option+L"
    monkeypatch.setattr(hotkeys_module.sys, "platform", "win32")
    assert hotkeys_module.platform_input_defaults()["audio_flow_hotkey"] == ""


class _Key:
    def __init__(self, vk=None, char=None):
        self.vk = vk
        self.char = char


def _listener(on_audio_flow):
    listener = object.__new__(hotkeys_module.InputTriggerListener)
    listener._on_audio_flow = on_audio_flow
    listener._audio_flow_hotkey = hotkeys_module.parse_audio_flow_hotkey("Ctrl+Option+L")
    return listener


def test_audio_flow_hotkey_matches_mac_keycode_with_exact_modifiers(monkeypatch):
    monkeypatch.setattr(hotkeys_module.sys, "platform", "darwin")
    listener = _listener(lambda: None)
    l_key = _Key(vk=37, char="\x0c")  # Ctrl turns "l" into a control character
    assert listener._matches_audio_flow_hotkey(l_key, True, True, False, False)
    assert not listener._matches_audio_flow_hotkey(l_key, True, False, False, False)
    assert not listener._matches_audio_flow_hotkey(l_key, True, True, False, True)  # + Cmd
    assert not listener._matches_audio_flow_hotkey(_Key(vk=40, char="\x0b"), True, True, False, False)  # K


def test_audio_flow_hotkey_invokes_callback_safely(caplog):
    calls: list[str] = []
    listener = _listener(lambda: calls.append("read"))
    listener._safe_on_audio_flow()
    assert calls == ["read"]

    def broken():
        raise RuntimeError("tts down")

    listener = _listener(broken)
    listener._safe_on_audio_flow()  # never propagates into the key listener
    assert "Audio Flow hotkey action" in caplog.text


def test_on_key_press_dispatches_audio_flow_hotkey(monkeypatch):
    monkeypatch.setattr(hotkeys_module.sys, "platform", "darwin")
    keyboard = hotkeys_module.keyboard
    if keyboard is None:
        pytest.skip("pynput unavailable")
    fired = threading.Event()
    listener = object.__new__(hotkeys_module.InputTriggerListener)
    listener._on_audio_flow = fired.set
    listener._audio_flow_hotkey = hotkeys_module.parse_audio_flow_hotkey("Ctrl+Option+L")
    listener._lock = threading.Lock()
    listener._pressed_keys = {keyboard.Key.ctrl, keyboard.Key.alt}
    listener._capture_fallback_keys = set()
    listener._is_recording = False
    listener._hotkey_trigger = "cmd_option"
    listener._trigger_mode = "hybrid"
    listener._armed_custom_info = None
    listener._custom_trigger_type = "hold"
    listener._on_start = lambda: pytest.fail("dictation must not start")
    listener._on_key_press(_Key(vk=37, char="\x0c"))
    assert fired.wait(1.0)


def test_main_wires_hotkey_to_audio_flow_pipeline_with_default_mode():
    source = open(main_module.__file__, encoding="utf-8").read()
    assert 'on_audio_flow=lambda: self._process_audio_flow_pipeline(mode="default")' in source


def test_mac_input_listener_start_starts_mouse_listener(monkeypatch):
    monkeypatch.setattr(hotkeys_module, "IS_WINDOWS", False)
    monkeypatch.setattr(hotkeys_module.sys, "platform", "darwin")
    started: list[str] = []
    listener = object.__new__(hotkeys_module.InputTriggerListener)
    listener._stop_event = threading.Event()
    listener._mouse_hook = SimpleNamespace(start=lambda: started.append("mouse"))
    listener._request_macos_hotkey_permissions_once = lambda: None
    listener._start_key_listener = lambda: started.append("keys") or True
    listener._hotkey_trigger = "cmd_option"
    listener.start()
    assert started == ["mouse", "keys"]


# ---------------------------------------------------------------------------
# Selection capture on macOS (main._on_mouse_release_macos)
# ---------------------------------------------------------------------------


class _Overlay:
    def __init__(self):
        self.cleared = 0
        self.selected: list[tuple[str, int]] = []

    def clear_selected_text(self):
        self.cleared += 1

    def set_selected_text(self, text, timeout_ms=15000):
        self.selected.append((text, timeout_ms))


def _mac_app(monkeypatch, injector, owner, hit=None):
    from voice_flow.platform import macos_native

    app = object.__new__(VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = DictationState.IDLE
    app.overlay = _Overlay()
    app.injector = injector
    app._selection_generation = 0
    app.recent_dictations = set()
    app.last_successful_transcript = None
    shown: list = []
    hidden: list = []
    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.storage, "get_setting", lambda _key, default=None: default)
    monkeypatch.setattr(main_module.audio_flow_widget, "show_at", lambda x, y, text: shown.append((x, y, text)))
    monkeypatch.setattr(main_module.audio_flow_widget, "hide", lambda: hidden.append(True))
    monkeypatch.setattr(macos_native, "frontmost_window_owner", lambda: dict(owner))
    def _window_at(x, y, only_pids=None):
        found = dict(hit or {})
        if only_pids is not None and found.get("pid") not in only_pids:
            return {}
        return found

    monkeypatch.setattr(macos_native, "window_owner_at_point", _window_at)
    backend = macos_backend_module.MacOSBackend()
    monkeypatch.setattr("voice_flow.platform.get_backend", lambda: backend)
    return app, shown, hidden


def test_mac_drag_selection_shows_widget_and_keeps_bar_selection(monkeypatch):
    class Injector:
        def get_selected_text_strict(self, target_hwnd=None):
            return "Photosynthesis turns sunlight into sugar."

    app, shown, hidden = _mac_app(monkeypatch, Injector(), {"app": "TextEdit", "pid": 4242})
    app._on_mouse_release(500, 300, 120.0, 380, 300)
    assert _wait_until(lambda: shown)
    assert shown == [(500, 300, "Photosynthesis turns sunlight into sugar.")]
    assert app.overlay.selected == [("Photosynthesis turns sunlight into sugar.", VoiceFlowApp.MAC_SELECTION_TIMEOUT_MS)]
    assert hidden == []


def test_mac_drag_in_own_app_is_never_captured(monkeypatch):
    class Injector:
        def get_selected_text_strict(self, target_hwnd=None):
            pytest.fail("must not read our own windows")

    app, shown, _hidden = _mac_app(monkeypatch, Injector(), {"app": "AI Productivity Flow", "pid": 1})
    app._on_mouse_release(500, 300, 120.0, 380, 300)
    time.sleep(0.25)
    assert shown == []


def test_mac_click_on_own_floating_window_keeps_selection(monkeypatch):
    import os

    app, _shown, hidden = _mac_app(monkeypatch, object(), {"app": "TextEdit", "pid": 4242}, hit={"pid": os.getpid(), "app": "tk"})
    app._on_mouse_release(20, 700, 0.0, 20, 700)
    assert app.overlay.cleared == 0 and hidden == []


def test_mac_click_where_dock_overlay_sits_above_our_window_still_counts_as_ours(monkeypatch):
    """The Dock owns an invisible full-screen window above floating windows:
    the own-window test must ask only about our pid, not the topmost window."""
    import os
    from voice_flow.platform import macos_native

    app, _shown, hidden = _mac_app(monkeypatch, object(), {"app": "TextEdit", "pid": 4242})
    calls = []

    def window_at(x, y, only_pids=None):
        calls.append(only_pids)
        return {"pid": os.getpid(), "app": "tk"} if only_pids == {os.getpid()} else {"pid": 378, "app": "Dock"}

    monkeypatch.setattr(macos_native, "window_owner_at_point", window_at)
    app._on_mouse_release(720, 180, 0.0, 720, 180)
    assert calls == [{os.getpid()}]
    assert app.overlay.cleared == 0 and hidden == []


def test_mac_click_elsewhere_clears_selection(monkeypatch):
    app, _shown, hidden = _mac_app(monkeypatch, object(), {"app": "TextEdit", "pid": 4242}, hit={"pid": 4242, "app": "TextEdit"})
    app._on_mouse_release(20, 300, 0.0, 20, 300)
    assert app.overlay.cleared == 1 and hidden == [True]


def test_mac_click_on_widget_while_it_resizes_keeps_it(monkeypatch):
    """'Make Anyway' on the short-text notice resizes the widget to the depth
    picker; the window server can miss it at the click point. The widget's own
    geometry (with its stage-transition grace) must keep the click ours."""
    app, _shown, hidden = _mac_app(monkeypatch, object(), {"app": "TextEdit", "pid": 4242}, hit={})
    monkeypatch.setattr(main_module.audio_flow_widget, "contains_point", lambda x, y: (x, y) == (1128, 265))
    app._on_mouse_release(1128, 265, 0.0, 1128, 265)
    assert app.overlay.cleared == 0 and hidden == []
    app._on_mouse_release(20, 300, 0.0, 20, 300)
    assert app.overlay.cleared == 1 and hidden == [True]


def test_widget_contains_point_covers_old_frame_during_stage_transition(monkeypatch):
    from voice_flow import audio_flow_widget as afw

    w = object.__new__(afw.AudioFlowFloatingWidget)
    w._is_visible = True
    w.win = object()
    w._pos_x, w._pos_y = 838, 205
    w._stage = w.STAGE_DEPTH_SELECT
    w._prev_dimensions = (384, 96)
    w._last_stage_change_time = time.time()
    assert w.contains_point(1128, 265)  # "Make Anyway" spot, outside the 265x32 picker
    w._last_stage_change_time = time.time() - 5
    assert not w.contains_point(1128, 265)
    assert w.contains_point(964, 221)  # "Balanced"


def test_mac_capture_skipped_while_dictating(monkeypatch):
    class Injector:
        def get_selected_text_strict(self, target_hwnd=None):
            pytest.fail("no capture while recording")

    app, shown, _hidden = _mac_app(monkeypatch, Injector(), {"app": "TextEdit", "pid": 4242})
    app.state = DictationState.RECORDING
    app._on_mouse_release(500, 300, 120.0, 380, 300)
    time.sleep(0.2)
    assert shown == []


# ---------------------------------------------------------------------------
# MacOSBackend.get_selected_text: AX first, Cmd+C fallback restores clipboard
# ---------------------------------------------------------------------------


class _Pasteboard:
    def __init__(self, items, change=5, copy_result=None):
        self.items = items
        self.change = change
        self.copy_result = copy_result
        self.restored = None
        self.current_types: list[str] = ["public.utf8-plain-text"]
        self.current_text = ""

    def changeCount(self):
        return self.change

    def simulate_copy(self):
        if self.copy_result is not None:
            self.change += 1
            self.current_text, self.current_types = self.copy_result

    def types(self):
        return self.current_types

    def stringForType_(self, _kind):
        return self.current_text


@pytest.fixture
def mac_native(monkeypatch):
    from voice_flow.platform import macos_native

    state = SimpleNamespace(info={}, keys=[], owner={"app": "Slack", "pid": 77}, can_post=True, pasteboard=None)

    def send_key_combo(keycode, flags=0, **_kw):
        state.keys.append((keycode, flags))
        if state.pasteboard is not None:
            state.pasteboard.simulate_copy()
        return True

    monkeypatch.setattr(macos_native, "focused_selection_info", lambda: dict(state.info))
    monkeypatch.setattr(macos_native, "send_key_combo", send_key_combo)
    monkeypatch.setattr(macos_native, "frontmost_window_owner", lambda: dict(state.owner))
    monkeypatch.setattr(macos_native, "can_post_events", lambda: state.can_post)
    state.modifiers_released = True
    monkeypatch.setattr(macos_native, "wait_for_modifiers_released", lambda timeout=1.0: state.modifiers_released)
    monkeypatch.setattr(macos_backend_module, "_general_pasteboard", lambda: state.pasteboard)
    monkeypatch.setattr(macos_backend_module, "_pasteboard_snapshot", lambda pb: list(pb.items))

    def restore(pb, snapshot):
        pb.restored = snapshot

    monkeypatch.setattr(macos_backend_module, "_pasteboard_restore", restore)
    return state


def test_selection_uses_accessibility_text_without_keystrokes(mac_native):
    mac_native.info = {"trusted": True, "status": 0, "role": "AXTextArea", "text": "Selected words"}
    assert macos_backend_module.MacOSBackend().get_selected_text() == "Selected words"
    assert mac_native.keys == []


def test_native_text_view_with_no_selection_sends_no_cmd_c(mac_native):
    mac_native.info = {"trusted": True, "status": 0, "role": "AXTextArea", "text": ""}
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.keys == []


def test_without_accessibility_selection_is_empty_and_no_keys(mac_native):
    mac_native.info = {"trusted": False, "status": None, "role": "", "text": ""}
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.keys == []


def test_cmd_c_fallback_reads_text_and_restores_clipboard(mac_native):
    from voice_flow.platform import macos_native

    mac_native.info = {"trusted": True, "status": -25205, "role": "AXGroup", "text": ""}
    snapshot = [{"public.png": b"image-bytes"}]
    mac_native.pasteboard = _Pasteboard(snapshot, copy_result=("Electron selection", ["public.utf8-plain-text"]))
    assert macos_backend_module.MacOSBackend().get_selected_text() == "Electron selection"
    assert mac_native.keys == [(macos_native.KEY_C, macos_native.kCGEventFlagMaskCommand)]
    assert mac_native.pasteboard.restored == snapshot  # the user's image is back


def test_cmd_c_that_copies_nothing_leaves_clipboard_untouched(mac_native):
    mac_native.info = {"trusted": True, "status": -25212, "role": "AXWebArea", "text": ""}
    mac_native.pasteboard = _Pasteboard([{"public.utf8-plain-text": b"keep me"}], copy_result=None)
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.pasteboard.restored is None


def test_cmd_c_copying_files_is_not_read_as_text(mac_native):
    mac_native.info = {"trusted": True, "status": -25205, "role": "AXList", "text": ""}
    mac_native.pasteboard = _Pasteboard([], copy_result=("report.pdf", ["public.file-url", "public.utf8-plain-text"]))
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.pasteboard.restored == []


def test_cmd_c_waits_for_hotkey_modifiers_and_skips_if_still_held(mac_native):
    mac_native.info = {"trusted": True, "status": -25205, "role": "AXGroup", "text": ""}
    mac_native.pasteboard = _Pasteboard([], copy_result=("x", ["public.utf8-plain-text"]))
    mac_native.modifiers_released = False  # user still holds Ctrl+Option
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.keys == []


def test_finder_and_own_app_never_get_cmd_c(mac_native):
    mac_native.info = {"trusted": True, "status": -25205, "role": "AXOutline", "text": ""}
    mac_native.pasteboard = _Pasteboard([], copy_result=("x", ["public.utf8-plain-text"]))
    mac_native.owner = {"app": "Finder", "pid": 9}
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    mac_native.owner = {"app": "AI Productivity Flow", "pid": 10}
    assert macos_backend_module.MacOSBackend().get_selected_text() == ""
    assert mac_native.keys == []


def test_send_paste_reports_failure_without_post_event_permission(mac_native):
    mac_native.can_post = False
    backend = macos_backend_module.MacOSBackend()
    assert backend.send_paste() is False
    assert backend.send_copy() is False
    assert mac_native.keys == []


# ---------------------------------------------------------------------------
# Honest paste on macOS (injector._inject_text_non_windows)
# ---------------------------------------------------------------------------


class _Backend:
    def __init__(self, can_post=True, clipboard="user clipboard"):
        self.can_post = can_post
        self.clipboard = clipboard
        self.pastes = 0
        self.writes: list[str] = []

    def is_own_window_focused(self):
        return False

    def can_post_events(self):
        return self.can_post

    def read_clipboard(self):
        return self.clipboard

    def copy_to_clipboard(self, text):
        self.writes.append(text)
        self.clipboard = text
        return True

    def send_paste(self):
        self.pastes += 1
        return True

    def send_enter(self):
        return True


@pytest.fixture
def fake_backend(monkeypatch):
    holder = {}

    def use(backend):
        holder["b"] = backend
        monkeypatch.setattr("voice_flow.platform.get_backend", lambda: backend)
        return backend

    notices: list[int] = []
    monkeypatch.setattr(injector_module, "_notify_paste_needs_permission", lambda: notices.append(1))
    use.notices = notices
    return use


def test_paste_without_accessibility_keeps_text_on_clipboard_and_reports_failure(fake_backend):
    backend = fake_backend(_Backend(can_post=False))
    assert injector_module._inject_text_non_windows("dictated words") is False
    assert backend.pastes == 0
    time.sleep(0.35)  # no delayed restore may clobber the dictation
    assert backend.clipboard == "dictated words"
    assert injector_module.last_injection_outcome() == "copied_needs_permission"
    assert fake_backend.notices == [1]


def test_paste_with_accessibility_restores_previous_clipboard(fake_backend):
    backend = fake_backend(_Backend(can_post=True, clipboard="older copy"))
    assert injector_module._inject_text_non_windows("dictated words") is True
    assert backend.pastes == 1
    assert _wait_until(lambda: backend.clipboard == "older copy", 1.0)
    assert injector_module.last_injection_outcome() == "pasted"


def test_restore_never_overwrites_a_newer_user_copy(fake_backend):
    backend = fake_backend(_Backend(can_post=True, clipboard="older copy"))
    assert injector_module._inject_text_non_windows("dictated words") is True
    backend.clipboard = "user copied this meanwhile"
    time.sleep(0.4)
    assert backend.clipboard == "user copied this meanwhile"


def test_history_reports_copied_to_clipboard_on_mac(monkeypatch, fake_backend):
    fake_backend(_Backend(can_post=False))
    injector_module._inject_text_non_windows("dictated words")
    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    message, insertion = main_module._paste_failure_details()
    assert insertion == "copied_to_clipboard"
    assert "Cmd+V" in message and "Accessibility" in message
    monkeypatch.setattr(main_module.sys, "platform", "win32")
    assert main_module._paste_failure_details()[1] == "failed"


def _ax_snapshots(monkeypatch, snapshots):
    from voice_flow.platform import macos_native

    seq = list(snapshots)
    monkeypatch.setattr(injector_module.sys, "platform", "darwin")
    monkeypatch.setattr(macos_native, "accessibility_trusted", lambda prompt=False: True)
    monkeypatch.setattr(macos_native, "preflight_post_event_access", lambda: True)
    monkeypatch.setattr(macos_native, "focused_value_snapshot", lambda: dict(seq.pop(0) if len(seq) > 1 else seq[0]))


def test_paste_with_stale_trust_but_ax_disabled_is_reported_as_copied(monkeypatch, fake_backend):
    """AXIsProcessTrusted can stay True after Accessibility is revoked; the live
    AX error (-25211 API disabled) wins and no Cmd+V is sent."""
    backend = fake_backend(_Backend(can_post=True, clipboard="older copy"))
    _ax_snapshots(monkeypatch, [{"focus_status": -25211, "value_status": None, "value": None}])
    assert injector_module._inject_text_non_windows("dictated words") is False
    assert backend.pastes == 0 and backend.clipboard == "dictated words"
    assert injector_module.last_injection_outcome() == "copied_needs_permission"


def test_paste_that_does_not_change_the_field_is_reported_as_copied(monkeypatch, fake_backend):
    backend = fake_backend(_Backend(can_post=True, clipboard="older copy"))
    _ax_snapshots(monkeypatch, [{"focus_status": 0, "value_status": 0, "value": "before"}])
    assert injector_module._inject_text_non_windows("dictated words") is False
    assert backend.pastes == 1
    time.sleep(0.35)
    assert backend.clipboard == "dictated words"  # no restore: the text must stay for Cmd+V
    assert injector_module.last_injection_outcome() == "copied_needs_permission"


def test_paste_that_changes_the_field_is_reported_as_pasted(monkeypatch, fake_backend):
    backend = fake_backend(_Backend(can_post=True, clipboard="older copy"))
    _ax_snapshots(monkeypatch, [
        {"focus_status": 0, "value_status": 0, "value": "before"},
        {"focus_status": 0, "value_status": 0, "value": "before dictated words"},
    ])
    assert injector_module._inject_text_non_windows("dictated words") is True
    assert _wait_until(lambda: backend.clipboard == "older copy", 1.0)
    assert injector_module.last_injection_outcome() == "pasted"


def test_paste_into_unreadable_field_is_trusted(monkeypatch, fake_backend):
    fake_backend(_Backend(can_post=True, clipboard="older copy"))
    _ax_snapshots(monkeypatch, [{"focus_status": 0, "value_status": -25205, "value": None}])
    assert injector_module._inject_text_non_windows("dictated words") is True
    assert injector_module.last_injection_outcome() == "pasted"


def test_mac_hotkey_falls_back_to_selection_captured_by_mouse(monkeypatch):
    class Injector:
        def get_selected_text(self, target_hwnd=None):
            return ""  # live read failed (modifiers still held)

    app, _shown, _hidden = _mac_app(monkeypatch, Injector(), {"app": "TextEdit", "pid": 4242})
    app.overlay.selected_text = "Photosynthesis turns sunlight into sugar."
    app._read_generation_lock = threading.RLock()
    app._active_summary_player_token = None
    app._read_active = False
    errors = []
    app.overlay.show_error = lambda msg: errors.append(msg)
    monkeypatch.setattr(main_module.tts_engine, "is_speaking", lambda: False)
    submitted = []
    app._submit_audio_summary = lambda text, depth: submitted.append(text)
    app._process_audio_flow_pipeline(mode="summary")
    assert submitted == ["Photosynthesis turns sunlight into sugar."] and errors == []


# ---------------------------------------------------------------------------
# Read playback on macOS: progressive Edge path plays with afplay, not winmm
# ---------------------------------------------------------------------------


def test_progressive_read_on_mac_plays_each_sentence_without_winmm(monkeypatch, tmp_path):
    from voice_flow import tts_engine as tts_module

    engine = tts_module.tts_engine
    played: list[str] = []
    started: list[bool] = []

    class _Communicate:
        def __init__(self, text, *_a, **_k):
            self.text = text

        async def stream(self):
            yield {"type": "audio", "data": b"ID3fake-" + self.text.encode()}

    monkeypatch.setitem(__import__("sys").modules, "edge_tts", SimpleNamespace(Communicate=_Communicate))
    import ctypes as _ctypes
    from voice_flow.platform import wincompat

    # Off Windows, wincompat installs a *falsy placeholder* as ctypes.windll
    # (not None), exactly as on a real Mac.
    monkeypatch.setattr(_ctypes, "windll", wincompat._UnavailableWinDLL(), raising=False)
    monkeypatch.setattr(engine, "_get_inter_sentence_pause_sec", lambda _cls: 0.0)

    def fake_play(path, cancelled, on_start=None):
        if on_start:
            on_start()
        played.append(open(path, "rb").read().decode(errors="ignore"))
        return True

    monkeypatch.setattr(engine, "_play_file_blocking", fake_play)
    engine._stop_event.clear()
    session = engine._session
    ok = engine._synthesize_and_play_pipelined(
        ["First sentence here.", "Second sentence here."], "en-US-AvaNeural", lambda: started.append(True), session
    )
    assert ok is True
    assert len(played) == 2 and "First" in played[0] and "Second" in played[1]
    assert started == [True]


# ---------------------------------------------------------------------------
# Widget: Tk 9 Aqua repaint after a resize (menu was invisible and deaf)
# ---------------------------------------------------------------------------


def test_widget_resize_on_mac_schedules_one_pixel_repaint(monkeypatch):
    from voice_flow import audio_flow_widget as widget_module

    monkeypatch.setattr(widget_module.sys, "platform", "darwin")
    widget = widget_module.AudioFlowFloatingWidget()
    scheduled = []
    geometries = []

    class Root:
        def after(self, ms, fn):
            scheduled.append((ms, fn))

        def winfo_screenwidth(self):
            return 1440

        def winfo_screenheight(self):
            return 900

    class Win:
        def geometry(self, g):
            geometries.append(g)

        def config(self, **_k):
            pass

        def deiconify(self):
            pass

        def lift(self):
            pass

        def attributes(self, *_a):
            pass

        def update_idletasks(self):
            pass

        def winfo_x(self):
            return 0

    class Canvas:
        def config(self, **_k):
            pass

    widget.root = Root()
    widget.win = Win()
    widget.canvas = Canvas()
    widget._draw = lambda: None
    widget._ensure_animation = lambda: None
    widget._mac_apply_shape = lambda w, h: None
    widget._is_visible = True
    widget._stage = widget.STAGE_MODE_SELECT
    widget._update_geometry_and_draw()
    assert len(scheduled) == 1
    scheduled[0][1]()  # run the deferred repaint
    assert geometries[-2].startswith("287x32") and geometries[-1].startswith("286x32")
    # plus the follow-up passes (macOS 14: one early nudge could leave it black)
    assert [ms for ms, _fn in scheduled[1:]] == list(widget.MAC_REPAINT_FOLLOWUPS_MS)
    widget._update_geometry_and_draw()  # same size again: no second nudge
    assert len(scheduled) == 1 + len(widget.MAC_REPAINT_FOLLOWUPS_MS)
    before = len(geometries)
    scheduled[1][1]()  # a follow-up pass nudges again and schedules nothing more
    assert geometries[before].startswith("287x32") and geometries[-1].startswith("286x32")
    assert len(scheduled) == 1 + len(widget.MAC_REPAINT_FOLLOWUPS_MS)
    # a follow-up for a size that is no longer current does nothing
    widget._stage = widget.STAGE_DEPTH_SELECT
    before = len(geometries)
    scheduled[2][1]()
    assert len(geometries) == before
