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
        return True

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

    class NSRunningApplication:
        @staticmethod
        def runningApplicationWithProcessIdentifier_(pid):
            return apps.get(pid)

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
