"""No real event hook, Carbon API, microphone or application starts here."""
import sys
from types import SimpleNamespace
import threading

import pytest

from voice_flow.platform import macos_keyboard_listener as factory


def _backend(monkeypatch, platform="darwin"):
    calls = []
    class Listener:
        __module__ = "pynput.keyboard._darwin"
        def __init__(self, **callbacks):
            self.callbacks = callbacks
        def _run(self):
            pytest.fail("obsolete Carbon layout wrapper executed")
        def _event_to_key(self, event):
            return event
        def stop(self):
            calls.append("stop")
    class Mixin:
        def _run(self):
            calls.append(("event-tap", threading.get_ident()))
            self.callbacks["on_press"]("cmd")
            self.callbacks["on_release"]("cmd")
    monkeypatch.setattr(factory.sys, "platform", platform)
    monkeypatch.setattr(factory.importlib, "import_module", lambda name: SimpleNamespace(ListenerMixin=Mixin))
    return SimpleNamespace(Listener=Listener), calls


def test_mac_worker_delegates_event_tap_without_carbon_and_keeps_callbacks(monkeypatch):
    keyboard, calls = _backend(monkeypatch)
    events = []
    listener = factory.create_keyboard_listener(keyboard, on_press=lambda key: events.append(("down", key)),
                                                on_release=lambda key: events.append(("up", key)))
    worker = threading.Thread(target=listener._run)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert calls == [("event-tap", worker.ident)]
    assert events == [("down", "cmd"), ("up", "cmd")]
    listener.stop()
    assert calls[-1] == "stop"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_keep_the_original_listener(monkeypatch, platform):
    keyboard, _ = _backend(monkeypatch, platform)
    monkeypatch.setattr(factory.importlib, "import_module", lambda *args: pytest.fail("Darwin import"))
    assert type(factory.create_keyboard_listener(keyboard, on_press=lambda key: None)) is keyboard.Listener


def test_mac_rejects_context_dependent_older_converter_before_start(monkeypatch):
    keyboard, _ = _backend(monkeypatch)
    def older(self, event):
        return self._context[event]
    monkeypatch.setattr(keyboard.Listener, "_event_to_key", older)
    with pytest.raises(RuntimeError, match="Quartz Unicode"):
        factory.create_keyboard_listener(keyboard)


def test_mac_cannot_select_a_win32_pynput_backend(monkeypatch):
    keyboard, _ = _backend(monkeypatch)
    monkeypatch.setattr(keyboard.Listener, "__module__", "pynput.keyboard._win32")
    with pytest.raises(RuntimeError, match="Darwin pynput"):
        factory.create_keyboard_listener(keyboard)


def test_packaging_pins_the_reviewed_listener_backend():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert '"pynput==1.8.2"' in (root/"pyproject.toml").read_text(encoding="utf-8")
    assert "pynput==1.8.2" in (root/"requirements.txt").read_text(encoding="utf-8")

@pytest.mark.skipif(sys.platform != "darwin", reason="checks the real Darwin converter without starting it")
def test_real_pinned_backend_keeps_converter_and_tap_events():
    from pynput import keyboard
    listener = factory.create_keyboard_listener(keyboard, on_press=lambda key: None,
                                                on_release=lambda key: None)
    assert isinstance(listener, keyboard.Listener)
    assert type(listener)._event_to_key is keyboard.Listener._event_to_key
    assert type(listener)._EVENTS == keyboard.Listener._EVENTS
    assert type(listener)._run is not keyboard.Listener._run
