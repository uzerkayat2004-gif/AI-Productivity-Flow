from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from voice_flow.gui import api_server, desktop_launcher
from voice_flow.gui.api_server import VoiceFlowApiHandler
from voice_flow.runtime_contract import RUNTIME_CONTRACT_VERSION
from voice_flow import runtime_guard


def test_api_exposes_current_runtime_contract() -> None:
    original_controller = api_server.runtime_controller
    api_server.register_runtime_controller(None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
    server.daemon_threads = True
    server.block_on_close = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/runtime",
            headers={"Connection": "close"},
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            payload = json.load(response)
        assert payload["contract_version"] == RUNTIME_CONTRACT_VERSION
        assert payload["features"]["video_flow_providers"] is True
        assert payload["features"]["agentic_video_flow"] is True
        assert payload["engine_ready"] is False
        assert runtime_guard.runtime_is_compatible(port=server.server_port) is True
        assert runtime_guard.runtime_is_engine_ready(port=server.server_port) is False

        api_server.register_runtime_controller(object())
        assert runtime_guard.runtime_is_engine_ready(port=server.server_port) is True
    finally:
        api_server.register_runtime_controller(original_controller)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_desktop_readiness_requires_current_runtime_contract(monkeypatch) -> None:
    monkeypatch.setattr(desktop_launcher, "runtime_is_compatible", lambda **_: False)
    assert desktop_launcher.is_api_server_ready() is False

    monkeypatch.setattr(desktop_launcher, "runtime_is_compatible", lambda **_: True)
    assert desktop_launcher.is_api_server_ready() is True


def test_prepare_runtime_reclaims_only_incompatible_voice_flow_listener(monkeypatch) -> None:
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **_: False)
    listeners = iter(([8123], []))
    monkeypatch.setattr(runtime_guard, "listener_pids", lambda *_: next(listeners, []))
    monkeypatch.setattr(runtime_guard, "terminate_voice_flow_listeners", lambda pids, **_: pids)

    result = runtime_guard.prepare_runtime_port(port=8991)

    assert result.status == "reclaimed"
    assert result.terminated_pids == (8123,)


def test_prepare_runtime_never_terminates_compatible_runtime(monkeypatch) -> None:
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **_: True)
    monkeypatch.setattr(
        runtime_guard,
        "terminate_voice_flow_listeners",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not terminate")),
    )

    result = runtime_guard.prepare_runtime_port(port=8991)

    assert result.status == "compatible"


def test_prepare_runtime_reclaims_compatible_fallback_when_engine_is_required(monkeypatch) -> None:
    monkeypatch.setattr(runtime_guard, "runtime_is_engine_ready", lambda **_: False, raising=False)
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **_: True)
    listeners = iter(([8123], []))
    monkeypatch.setattr(runtime_guard, "listener_pids", lambda *_: next(listeners, []))
    monkeypatch.setattr(runtime_guard, "terminate_voice_flow_listeners", lambda pids, **_: pids)

    result = runtime_guard.prepare_runtime_port(port=8991, require_engine=True)

    assert result.status == "reclaimed"
    assert result.terminated_pids == (8123,)
