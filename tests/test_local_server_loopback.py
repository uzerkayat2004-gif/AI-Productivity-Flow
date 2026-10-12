from __future__ import annotations

import ast
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from voice_flow.local_server import LoopbackHTTPServer, require_loopback_host
from voice_flow import runtime_guard

ROOT = Path(__file__).resolve().parents[1]
BAD_HOSTS = ("0.0.0.0", "192.168.1.10", "::", "::1", "localhost", "machine.local", "")


def _api_entrypoint():
    # Execute the real entrypoint with isolated fake dependencies: importing the
    # full API initializes storage/providers, which this binding test does not need.
    tree = ast.parse((ROOT / "src/voice_flow/gui/api_server.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "start_api_server")
    namespace = {"require_loopback_host": require_loopback_host, "PORT": 8991,
                 "LoopbackHTTPServer": LoopbackHTTPServer, "VoiceFlowApiHandler": BaseHTTPRequestHandler}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "isolated_api_entrypoint", "exec"), namespace)
    return namespace["start_api_server"], namespace


@pytest.mark.parametrize("host", BAD_HOSTS)
def test_api_rejects_nonloopback_before_storage_or_socket(host):
    entrypoint, namespace = _api_entrypoint()
    class ForbiddenStorage:
        def repoint_if_needed(self):
            pytest.fail("storage consulted before host validation")
    namespace["storage"] = ForbiddenStorage()
    namespace["LoopbackHTTPServer"] = lambda *args: pytest.fail("server created before host validation")
    with pytest.raises(ValueError, match="127.0.0.1"):
        entrypoint(host)


def test_default_api_binds_numeric_loopback(monkeypatch):
    import sys
    entrypoint, namespace = _api_entrypoint()
    namespace["storage"] = SimpleNamespace(repoint_if_needed=lambda: False)
    monkeypatch.setitem(sys.modules, "voice_flow.consolidate", SimpleNamespace(
        consolidate_engine=lambda *args, **kwargs: {}, CONSOLIDATION_MARKER_KEY="fixture"))
    monkeypatch.setitem(sys.modules, "voice_flow.video_flow_engine.notebooklm", SimpleNamespace(
        start_keepalive_daemon=lambda: None, trigger_keepalive_now=lambda **kwargs: None))
    addresses = []
    class StopBeforeServing(BaseException):
        pass
    class FakeServer:
        def __init__(self, address, handler):
            addresses.append(address)
        def serve_forever(self):
            raise StopBeforeServing
    namespace["LoopbackHTTPServer"] = FakeServer
    with pytest.raises(StopBeforeServing):
        entrypoint()
    assert addresses == [("127.0.0.1", 8991)]


@pytest.mark.parametrize("host", BAD_HOSTS)
def test_server_bind_defense_rejects_before_kernel_bind(monkeypatch, host):
    monkeypatch.setattr(socket.socket, "bind", lambda *args: pytest.fail("unsafe kernel bind"))
    with pytest.raises(ValueError, match="127.0.0.1"):
        LoopbackHTTPServer((host, 0), BaseHTTPRequestHandler)


def test_real_ephemeral_server_bind_never_discovers_hostname(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("server startup performed hostname lookup")
    monkeypatch.setattr(socket, "getfqdn", forbidden)
    monkeypatch.setattr(socket, "gethostname", forbidden)
    server = LoopbackHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    try:
        assert server.server_address[0] == server.server_name == "127.0.0.1"
        assert server.server_port == server.server_address[1] != 0
    finally:
        server.server_close()


@pytest.mark.parametrize("host", BAD_HOSTS)
def test_runtime_rejects_bad_host_before_client_probe_or_socket(monkeypatch, host):
    monkeypatch.setattr(runtime_guard.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("unsafe client probe"))
    monkeypatch.setattr(runtime_guard.socket, "socket", lambda *args: pytest.fail("unsafe socket creation"))
    monkeypatch.setattr(runtime_guard, "listener_pids", lambda *args: pytest.fail("unsafe owner probe"))
    for action in (
        lambda: runtime_guard.runtime_is_compatible(host=host),
        lambda: runtime_guard.runtime_is_engine_ready(host=host),
        lambda: runtime_guard.prepare_runtime_port(host=host),
        lambda: runtime_guard._unprivileged_port_result(host, 0),
    ):
        with pytest.raises(ValueError, match="127.0.0.1"):
            action()


def test_permission_denied_fallback_binds_default_loopback(monkeypatch):
    addresses = []
    class FakeSocket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def bind(self, address):
            addresses.append(address)
    def denied(**kwargs):
        raise PermissionError("fixture owner inspection denied")
    monkeypatch.setattr(runtime_guard, "_prepare_runtime_port_with_pids", denied)
    monkeypatch.setattr(runtime_guard, "runtime_is_compatible", lambda **kwargs: False)
    monkeypatch.setattr(runtime_guard.socket, "socket", lambda family, kind: FakeSocket())
    assert runtime_guard.prepare_runtime_port(port=0).status == "available"
    assert addresses == [("127.0.0.1", 0)]


def _unsafe_literal_binds(source):
    unsafe = []
    wildcard = {"", "*", "0.0.0.0", "::"}
    for call in ast.walk(ast.parse(source)):
        if not isinstance(call, ast.Call):
            continue
        name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
        if name == "bind" or name.endswith("HTTPServer") or name.endswith("TCPServer") or name.endswith("UDPServer"):
            address = call.args[0] if call.args else None
            if isinstance(address, (ast.Tuple, ast.List)) and address.elts:
                host = address.elts[0]
                if isinstance(host, ast.Constant) and isinstance(host.value, str) and host.value in wildcard:
                    unsafe.append(call.lineno)
        if name == "run" and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "uvicorn":
            for keyword in call.keywords:
                if keyword.arg == "host" and isinstance(keyword.value, ast.Constant) and keyword.value.value in wildcard:
                    unsafe.append(call.lineno)
        if name in ("Popen", "run") and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "subprocess":
            command = call.args[0] if call.args else None
            if isinstance(command, (ast.Tuple, ast.List)):
                values = [item.value if isinstance(item, ast.Constant) else None for item in command.elts]
                if not any(isinstance(value, str) and value.replace("\\", "/").rsplit("/", 1)[-1] in ("uvicorn", "uvicorn.exe") for value in values):
                    continue
                for index, value in enumerate(values):
                    if value == "--host" and index + 1 < len(values) and values[index + 1] in wildcard:
                        unsafe.append(call.lineno)
                    if isinstance(value, str) and value.startswith("--host=") and value.split("=", 1)[1] in wildcard:
                        unsafe.append(call.lineno)
    return unsafe


@pytest.mark.parametrize("source", [
    'sock.bind(("0.0.0.0", 9000))', 'HTTPServer(("::", 9000), handler)',
    'UDPServer(("0.0.0.0", 5353), handler)', 'uvicorn.run(app, host="0.0.0.0")', 'subprocess.Popen(["uvicorn", "module:app", "--host", "0.0.0.0"])',
])
def test_source_audit_detects_new_unsafe_literal_binding(source):
    assert _unsafe_literal_binds(source)


def test_source_audit_allows_owner_detection_and_provider_configuration():
    assert not _unsafe_literal_binds('accepted_hosts = {"127.0.0.1", "0.0.0.0", "::"}\nprovider_url = "http://192.168.1.10:9000"\n')


def test_app_source_has_no_literal_wildcard_server_bindings():
    failures = []
    for path in (ROOT / "src/voice_flow").rglob("*.py"):
        for line in _unsafe_literal_binds(path.read_text(encoding="utf-8")):
            failures.append(f"{path.relative_to(ROOT)}:{line}")
    assert not failures, "Unsafe server bind sites: " + ", ".join(failures)


def test_desktop_webview_explicitly_disables_internal_http_server():
    tree = ast.parse((ROOT / "src/voice_flow/gui/desktop_launcher.py").read_text(encoding="utf-8"))
    starts = [call for call in ast.walk(tree) if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "webview" and call.func.attr == "start"]
    assert starts
    assert all(any(keyword.arg == "http_server" and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False for keyword in call.keywords) for call in starts)
