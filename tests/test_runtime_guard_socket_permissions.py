"""Permission-denied port ownership must never authorize killing unknown owners."""

import errno
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import psutil
import pytest

from voice_flow import runtime_guard


@pytest.fixture
def guarded_probe(monkeypatch):
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **_: False)
    monkeypatch.setattr(runtime_guard, "runtime_is_engine_ready", lambda **_: False)
    def denied(**kwargs):
        raise psutil.AccessDenied(pid=23028)
    monkeypatch.setattr(psutil, "net_connections", denied)
    terminate = MagicMock(side_effect=AssertionError("unknown owners must not be terminated"))
    monkeypatch.setattr(runtime_guard, "terminate_voice_flow_listeners", terminate)
    probe = MagicMock()
    factory = MagicMock(return_value=probe)
    probe.__enter__.return_value = probe
    monkeypatch.setattr(runtime_guard.socket, "socket", factory)
    return probe, factory, terminate


def test_denied_inspection_free_port_allows_engine_startup(guarded_probe):
    probe, factory, terminate = guarded_probe
    result = runtime_guard.prepare_runtime_port(host="127.0.0.1", port=43210, require_engine=True)
    assert result.status == "available"
    assert result.terminated_pids == ()
    probe.bind.assert_called_once_with(("127.0.0.1", 43210))
    probe.setsockopt.assert_not_called()
    probe.__exit__.assert_called_once()
    terminate.assert_not_called()


@pytest.mark.parametrize("error", [OSError(errno.EADDRINUSE, "occupied"), PermissionError("denied"), OSError(errno.EAFNOSUPPORT, "unsupported")])
def test_denied_inspection_occupied_or_indeterminate_port_is_protected(guarded_probe, error):
    probe, _, terminate = guarded_probe
    probe.bind.side_effect = error
    assert runtime_guard.prepare_runtime_port(port=43210).status == "occupied"
    terminate.assert_not_called()
    probe.__exit__.assert_called_once()


def test_missing_listener_pid_uses_protected_probe(monkeypatch, guarded_probe):
    probe, _, terminate = guarded_probe
    monkeypatch.setattr(psutil, "net_connections", lambda **_: [SimpleNamespace(
        laddr=SimpleNamespace(ip="127.0.0.1", port=43210), status=psutil.CONN_LISTEN, pid=None)])
    probe.bind.side_effect = OSError(errno.EADDRINUSE, "occupied")
    assert runtime_guard.prepare_runtime_port(port=43210).status == "occupied"
    terminate.assert_not_called()


def test_readiness_after_permission_failure_reuses_runtime(monkeypatch, guarded_probe):
    _, factory, terminate = guarded_probe
    readiness = iter([False, True])
    monkeypatch.setattr(runtime_guard, "runtime_is_engine_ready", lambda **_: next(readiness))
    assert runtime_guard.prepare_runtime_port(port=43210, require_engine=True).status == "compatible"
    factory.assert_not_called()
    terminate.assert_not_called()


def test_permission_loss_during_grace_never_terminates_original_pid(monkeypatch, guarded_probe):
    probe, _, terminate = guarded_probe
    calls = iter([[1234], PermissionError("visibility lost")])
    def inspect(*args):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(runtime_guard, "listener_pids", inspect)
    monkeypatch.setattr(runtime_guard.time, "sleep", lambda _: None)
    probe.bind.side_effect = OSError(errno.EADDRINUSE, "occupied")
    assert runtime_guard.prepare_runtime_port(port=43210).status == "occupied"
    terminate.assert_not_called()


@pytest.mark.parametrize("occupied", [False, True])
def test_permission_fallback_with_real_disposable_loopback_port(monkeypatch, occupied):
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **_: False)
    def denied(**kwargs):
        raise psutil.AccessDenied()
    monkeypatch.setattr(psutil, "net_connections", denied)
    terminate = MagicMock(side_effect=AssertionError("must not terminate"))
    monkeypatch.setattr(runtime_guard, "terminate_voice_flow_listeners", terminate)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
        owner.bind(("127.0.0.1", 0))
        port = owner.getsockname()[1]
        assert port not in {8991, 8992}
        if occupied:
            owner.listen()
        else:
            owner.close()
        result = runtime_guard.prepare_runtime_port(host="127.0.0.1", port=port)
        assert result.status == ("occupied" if occupied else "available")
        if occupied:
            assert owner.getsockname()[1] == port
    terminate.assert_not_called()
