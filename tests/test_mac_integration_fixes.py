"""Regression tests for the v1.0.3 macOS integration follow-ups.

a. Paste after a click on our bar/widget: focus goes back to the user's app.
b. Wake-phrase mishearings seen on macOS ("Hey boy, slow", "hay voice flow").
c. macOS keeps the speech model warm between dictations.

Every macOS framework call is faked so these run on any OS.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

from voice_flow import injector as injector_module
from voice_flow import main as main_module
from voice_flow.platform import macos as macos_backend_module
from voice_flow.voice_commands import detect_voice_command, remove_activation_phrases


# ---------------------------------------------------------------------------
# a. focus restore before Cmd+V
# ---------------------------------------------------------------------------


class _Backend:
    def __init__(self, events):
        self.events = events
        self.clipboard = "older"

    def is_own_window_focused(self):
        return False

    def can_post_events(self):
        return True

    def restore_paste_target_focus(self):
        self.events.append("restore")
        return {"restored": True}

    def read_clipboard(self):
        return self.clipboard

    def copy_to_clipboard(self, text):
        self.clipboard = text
        return True

    def send_paste(self):
        self.events.append("paste")
        return True

    def send_enter(self):
        return True


def test_injector_restores_target_focus_before_snapshot_and_paste(monkeypatch):
    from voice_flow.platform import macos_native

    events: list[str] = []
    backend = _Backend(events)
    monkeypatch.setattr("voice_flow.platform.get_backend", lambda: backend)
    monkeypatch.setattr(injector_module.sys, "platform", "darwin")
    monkeypatch.setattr(macos_native, "accessibility_trusted", lambda prompt=False: True)
    monkeypatch.setattr(macos_native, "preflight_post_event_access", lambda: True)

    snaps = iter([{"focus_status": 0, "value_status": 0, "value": "a"}] + [{"focus_status": 0, "value_status": 0, "value": "a words"}] * 50)

    def snapshot():
        events.append("snapshot")
        return next(snaps)

    monkeypatch.setattr(macos_native, "focused_value_snapshot", snapshot)
    assert injector_module._inject_text_non_windows("words") is True
    assert events[:3] == ["restore", "snapshot", "paste"]


class _App:
    def __init__(self, pid, registry):
        self.pid = pid
        self.registry = registry
        self.activated = 0

    def processIdentifier(self):
        return self.pid

    def activateWithOptions_(self, _options):
        self.activated += 1
        self.registry["front"] = self
        self.registry["active"] = self
        return True

    def isActive(self):
        return self.registry.get("active", self.registry.get("front")) is self

    def bundleURL(self):
        return None


def _fake_appkit(monkeypatch, front_pid, target_pid):
    registry: dict = {}
    apps = {target_pid: _App(target_pid, registry)}
    if front_pid:
        apps[front_pid] = _App(front_pid, registry)
    registry["front"] = apps.get(front_pid)
    yielded: list = []

    class NSWorkspace:
        @staticmethod
        def sharedWorkspace():
            return NSWorkspace

        @staticmethod
        def frontmostApplication():
            return registry["front"]

    if os.getpid() not in apps:
        apps[os.getpid()] = _App(os.getpid(), registry)

    class NSRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(pid):
            return apps.get(pid)

        @staticmethod
        def currentApplication():
            return apps[os.getpid()]

    class _NSApp:
        def yieldActivationToApplication_(self, app):
            yielded.append(app.pid)

    class NSApplication:
        @staticmethod
        def sharedApplication():
            return _NSApp()

    mod = types.ModuleType("AppKit")
    mod.NSWorkspace = NSWorkspace
    mod.NSRunningApplication = NSRunningApplication
    mod.NSApplication = NSApplication
    mod.NSApplicationActivateIgnoringOtherApps = 2
    monkeypatch.setitem(sys.modules, "AppKit", mod)
    monkeypatch.setattr(macos_backend_module, "IS_MACOS", True)
    monkeypatch.setattr(macos_backend_module.native, "frontmost_window_owner",
                        lambda: {"app": "TextEdit", "title": "af.txt", "pid": target_pid})
    return apps, yielded


def test_restore_focus_reactivates_users_app_when_engine_is_active(monkeypatch):
    target = os.getpid() + 1000
    apps, yielded = _fake_appkit(monkeypatch, os.getpid(), target)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["restored"] is True
    assert apps[target].activated == 1
    assert yielded == [target]


def test_restore_focus_does_nothing_when_users_app_is_already_active(monkeypatch):
    target = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, target, target)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["restored"] is False
    assert apps[target].activated == 0


def test_restore_focus_never_activates_our_own_window_process(monkeypatch):
    other = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, os.getpid(), other)
    monkeypatch.setattr(macos_backend_module.native, "frontmost_window_owner",
                        lambda: {"app": "AI Productivity Flow", "title": "", "pid": other})
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    assert backend.restore_paste_target_focus(timeout=0.2)["restored"] is False
    assert apps[other].activated == 0


def test_restore_focus_is_a_noop_off_macos(monkeypatch):
    monkeypatch.setattr(macos_backend_module, "IS_MACOS", False)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    assert backend.restore_paste_target_focus() == {"restored": False}


# ---------------------------------------------------------------------------
# b. wake-phrase mishearings keep every word
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transcript, kept",
    [
        ("Hey boy, slow make this an email to Bria about the launch on Sunday",
         "Make this an email to Bria about the launch on Sunday"),
        ("Discussed pricing the launch date and hiring hay voice flow summarize this",
         "Discussed pricing the launch date and hiring. Summarize this"),
        ("Voice slow, make this an email to Priya.", "Make this an email to Priya."),
    ],
)
def test_misheard_wake_phrases_are_commands_and_keep_the_words(transcript, kept):
    assert detect_voice_command(transcript).command is not None
    assert remove_activation_phrases(transcript) == kept


@pytest.mark.parametrize(
    "transcript",
    [
        "Hey boy, slow down please.",
        "We fed the hay to the horses.",
        "I need some hay voice flow is great.",
        "Her voice slowly faded.",
        "His voice slow and steady made everyone calm.",
        "The horse ate hay. Voice slow is a bad name.",
    ],
)
def test_ordinary_speech_is_not_a_wake_phrase(transcript):
    assert detect_voice_command(transcript).command is None
    assert remove_activation_phrases(transcript) == transcript


def test_unfulfilled_command_label_says_text_was_kept():
    label = main_module._polish_outcome_label("command_unfulfilled")
    assert "full text was kept" in label


# ---------------------------------------------------------------------------
# c. macOS keeps the speech model warm between dictations
# ---------------------------------------------------------------------------


class _Lease:
    def __init__(self):
        self.calls: list = []

    def release(self):
        self.calls.append(("release",))

    def release_after_idle(self, seconds, max_seconds=None):
        self.calls.append(("idle", seconds))


def _release(monkeypatch, platform):
    monkeypatch.setattr(main_module.sys, "platform", platform)
    monkeypatch.setattr(main_module, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(main_module, "_polish_model_is_local", lambda: True)
    lease = _Lease()
    session = {"model_resource_lease": lease, "stt_model_ref": "local/faster-whisper-base.en"}
    main_module.VoiceFlowApp._release_session_model_resource(session)
    return lease.calls


def test_mac_keeps_whisper_warm_after_a_dictation(monkeypatch):
    assert _release(monkeypatch, "darwin") == [("idle", main_module.MAC_SPEECH_WARM_SECONDS)]
    assert main_module.MAC_SPEECH_WARM_SECONDS > 0


def test_windows_still_releases_whisper_immediately(monkeypatch):
    assert _release(monkeypatch, "win32") == [("release",)]


def test_restore_focus_reactivates_users_app_when_no_app_is_active(monkeypatch):
    """Escape on our widget menu can leave no active app: Cmd+V must not go nowhere."""
    target = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, 0, target)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["active_pid"] == 0
    assert report["restored"] is True
    assert apps[target].activated == 1


def test_restore_focus_leaves_another_active_app_alone(monkeypatch):
    """A different app holding activation (e.g. a Spotlight-style panel) keeps it."""
    target = os.getpid() + 1000
    other = os.getpid() + 2000
    apps, _ = _fake_appkit(monkeypatch, other, target)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    assert backend.restore_paste_target_focus(timeout=0.2)["restored"] is False
    assert apps[target].activated == 0


# ---------------------------------------------------------------------------
# frontmost_window_owner must look past menu-bar extras / overlays
# ---------------------------------------------------------------------------

def _fake_window_list(monkeypatch, windows):
    """Fake CoreGraphics/CoreFoundation for frontmost_window_owner()."""
    from voice_flow.platform import macos_native as native

    keys = {"kCGWindowOwnerName": 101, "kCGWindowName": 102, "kCGWindowOwnerPID": 103, "kCGWindowLayer": 104}
    field = {101: "owner", 102: "title", 103: "pid", 104: "layer"}
    tokens: dict[int, object] = {}

    class _Fn:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    def dict_get(entry, ref):
        win = windows[entry - 1]
        name = field[ref.value]
        if name not in win:
            return 0
        token = 1000 + entry * 10 + (ref.value - 100)
        tokens[token] = win[name]
        return token

    def number_get(value, _type, out_ref):
        out_ref._obj.value = int(tokens[value])
        return True

    symbols = {
        "CGWindowListCopyWindowInfo": _Fn(lambda *_a: 1),
        "CFArrayGetCount": _Fn(lambda _arr: len(windows)),
        "CFArrayGetValueAtIndex": _Fn(lambda _arr, i: i + 1),
        "CFDictionaryGetValue": _Fn(dict_get),
        "CFNumberGetValue": _Fn(number_get),
    }
    monkeypatch.setattr(native, "IS_MACOS", True)
    monkeypatch.setattr(native._loader, "symbol", lambda _fw, name, optional=False: symbols.get(name))
    monkeypatch.setattr(native._loader, "data_symbol", lambda _fw, name, optional=False: keys.get(name))
    monkeypatch.setattr(native, "cfstring_to_python", lambda token: str(tokens[token]))
    monkeypatch.setattr(native, "cf_release", lambda _ref: None)
    return native


def test_frontmost_window_owner_skips_many_overlay_windows(monkeypatch):
    """macOS 14 CI: >20 menu-bar extras / Dock / our bar, widget, menu, toast sat
    above TextEdit's window; the old 20-entry cap returned {} so paste focus
    restore and AX reads silently gave up (Cmd+V landed nowhere)."""
    overlays = [{"owner": f"Extra{i}", "title": "Item-0", "pid": 300 + i, "layer": 25} for i in range(24)]
    overlays += [{"owner": "AI Productivity Flow", "title": "", "pid": 5291, "layer": 19} for _ in range(4)]
    windows = overlays + [{"owner": "TextEdit", "title": "af.txt", "pid": 5740, "layer": 0}]
    native = _fake_window_list(monkeypatch, windows)
    assert native.frontmost_window_owner() == {"app": "TextEdit", "title": "af.txt", "pid": 5740}


def test_frontmost_window_owner_empty_when_no_normal_window(monkeypatch):
    windows = [{"owner": "Dock", "title": "Dock", "pid": 324, "layer": 20}]
    native = _fake_window_list(monkeypatch, windows)
    assert native.frontmost_window_owner() == {}


def test_restore_focus_when_engine_is_active_but_menu_bar_still_shows_users_app(monkeypatch):
    """macOS 14 CI (it4 af2 38978817743): after Escape on the widget menu our
    accessory app held keyboard activation while frontmostApplication (menu-bar
    owner) still said TextEdit; no restore ran and Cmd+V reached us."""
    target = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, target, target)
    registry = apps[target].registry
    registry["active"] = apps[os.getpid()]
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["own_active"] is True
    assert report["restored"] is True
    assert apps[target].activated == 1


def test_restore_focus_when_no_app_is_active_but_menu_bar_names_users_app(monkeypatch):
    target = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, target, target)
    apps[target].registry["active"] = None
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["restored"] is True
    assert apps[target].activated == 1


# ---------------------------------------------------------------------------
# macOS 14 CI it6 af2 (38982431970): cached AppKit state (worker thread) said
# TextEdit was active; LaunchServices had no front app -> restore skipped.
# ---------------------------------------------------------------------------

def test_restore_focus_trusts_launchservices_when_appkit_state_is_stale(monkeypatch):
    target = os.getpid() + 1000
    apps, _ = _fake_appkit(monkeypatch, target, target)
    apps[target].registry["active"] = apps[target]  # stale: TextEdit "active"
    calls = {"n": 0}

    def ls_front():
        calls["n"] += 1
        return 0 if calls["n"] == 1 else target  # none front, then TextEdit after activation

    monkeypatch.setattr(macos_backend_module, "_launchservices_front_pid", ls_front)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.3)
    assert report["ls_front_pid"] == 0
    assert report["restored"] is True
    assert apps[target].activated == 1


def test_restore_focus_launchservices_names_another_app_leaves_it_alone(monkeypatch):
    target = os.getpid() + 1000
    other = os.getpid() + 2000
    apps, _ = _fake_appkit(monkeypatch, 0, target)
    monkeypatch.setattr(macos_backend_module, "_launchservices_front_pid", lambda: other)
    backend = macos_backend_module.MacOSBackend.__new__(macos_backend_module.MacOSBackend)
    report = backend.restore_paste_target_focus(timeout=0.2)
    assert report["restored"] is False
    assert report["skipped"] == "another app is active"
    assert apps[target].activated == 0


def test_frontmost_window_owner_skips_window_server_layer0_window(monkeypatch):
    """macOS 14 CI it7 af2 (38985457171): after Escape on the widget menu a
    layer-0 Window Server window was first, restore targeted pid 138 and skipped."""
    windows = [
        {"owner": "AI Productivity Flow", "title": "", "pid": 8196, "layer": 19},
        {"owner": "Window Server", "title": "", "pid": 138, "layer": 0},
        {"owner": "TextEdit", "title": "af.txt", "pid": 5740, "layer": 0},
    ]
    native = _fake_window_list(monkeypatch, windows)
    assert native.frontmost_window_owner() == {"app": "TextEdit", "title": "af.txt", "pid": 5740}


def test_launchservices_front_pid_parses_lsappinfo(monkeypatch):
    """it8 af2: `lsappinfo info -only pid front` is not valid, so every paste saw
    'no front app', waited the full timeout and used `open -a`. Ask for the
    front ASN first, then its pid."""
    calls = []

    def fake_run(cmd, **_kw):
        calls.append(cmd)
        if cmd[1] == "front":
            return types.SimpleNamespace(returncode=0, stdout="ASN:0x0-0x2a02a:\n")
        return types.SimpleNamespace(returncode=0, stdout='"pid"=15208\n')

    monkeypatch.setattr(macos_backend_module, "IS_MACOS", True)
    monkeypatch.setattr(macos_backend_module.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(macos_backend_module.subprocess, "run", fake_run)
    assert macos_backend_module._launchservices_front_pid() == 15208
    assert calls[1] == ["/usr/bin/lsappinfo", "info", "-only", "pid", "ASN:0x0-0x2a02a:"]

    monkeypatch.setattr(macos_backend_module.subprocess, "run",
                        lambda cmd, **_kw: types.SimpleNamespace(returncode=0, stdout="[ NULL ]\n"))
    assert macos_backend_module._launchservices_front_pid() == 0

    monkeypatch.setattr(macos_backend_module.subprocess, "run",
                        lambda cmd, **_kw: types.SimpleNamespace(
                            returncode=0, stdout="ASN:0x0-0x1:\n" if cmd[1] == "front" else "garbage"))
    assert macos_backend_module._launchservices_front_pid() is None
