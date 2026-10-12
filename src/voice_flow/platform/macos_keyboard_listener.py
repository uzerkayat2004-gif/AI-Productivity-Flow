"""App-scoped Quartz listener without pynput's unused Carbon layout read."""
from __future__ import annotations

import importlib
import sys
from typing import Any


def create_keyboard_listener(keyboard_api: Any, **callbacks: Any) -> Any:
    listener_type = keyboard_api.Listener
    if sys.platform != "darwin":
        return listener_type(**callbacks)
    backend = getattr(listener_type, "__module__", "")
    if not backend.startswith("pynput."):
        # Inert collaborators used by the cross-platform hotkey tests.
        return listener_type(**callbacks)
    if backend != "pynput.keyboard._darwin":
        raise RuntimeError("macOS hotkeys require the Darwin pynput backend")
    converter = getattr(listener_type, "_event_to_key", None)
    code = getattr(converter, "__code__", None)
    if code is None or any(name in code.co_names for name in ("_context", "keycode_to_string")):
        raise RuntimeError("macOS hotkeys require pynput's Quartz Unicode event converter")
    mixin = importlib.import_module("pynput._util.darwin").ListenerMixin

    class QuartzKeyboardListener(listener_type):
        def _run(self) -> None:
            # pynput 1.8.2 converts event text directly with Quartz. Its wrapper
            # still fetches unused TIS layout data on the worker thread, which
            # newer HIToolbox versions abort. Keep the original event tap,
            # callbacks, trust checks and stop/runloop lifecycle instead.
            mixin._run(self)

    return QuartzKeyboardListener(**callbacks)
