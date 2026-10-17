"""llama-server lifetime, identity and loopback-proxy regressions (M-R-1, M-R-2, B6)."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil
import pytest

from voice_flow import child_processes, local_http, vf1_engine
from voice_flow.vf1_engine import LlamaServerManager, VF1Engine, VF1EngineConfig

POSIX = os.name != "nt"
FAKE_SERVER = Path(__file__).with_name("fake_llama_server.py")
SRC_DIR = Path(vf1_engine.__file__).resolve().parents[1]


def _alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _wait_dead(pid: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _pids(log: Path, count: int = 1, timeout: float = 5.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists():
            pids = [int(x) for x in log.read_text().split()]
            if len(pids) >= count:
                return pids
        time.sleep(0.05)
    return [int(x) for x in log.read_text().split()] if log.exists() else []


@pytest.fixture
def fake_binary(tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text(f"#!{sys.executable}\n" + FAKE_SERVER.read_text(encoding="utf-8"), encoding="utf-8")
    binary.chmod(0o755)
    return binary


@pytest.fixture
def model(tmp_path):
    path = tmp_path / "s1-mini-q4_k_m.gguf"
    path.write_bytes(b"GGUF")
    return path


@pytest.fixture
def manager(tmp_path, monkeypatch):
    log = tmp_path / "spawns.log"
    monkeypatch.setenv("FAKE_LLAMA_LOG", str(log))
    monkeypatch.delenv("FAKE_LLAMA_DELAY", raising=False)
    mgr = LlamaServerManager(run_dir=tmp_path / "run")
    mgr.spawn_log = log  # type: ignore[attr-defined]
    yield mgr
    mgr.stop()
    for pid in _pids(log, 0, 0):
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


class _Server:
    """Loopback HTTP server recording every request line it receives."""

    def __init__(self, handler_body):
        self.requests: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _reply(self):
                outer.requests.append(f"{self.command} {self.path} {self.headers.get('Host')}")
                code, payload = handler_body(self)
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _reply
            do_POST = _reply

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


posix_only = pytest.mark.skipif(not POSIX, reason="POSIX process-group / sh guard path")


# --------------------------------------------------------------------- M-R-1
@posix_only
def test_spawns_on_private_port_and_stop_kills_server(manager, fake_binary, model):
    assert manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=10)
    assert manager.port and manager.port != 8080
    assert manager.alias and manager.alias.startswith("voiceflow-s1-")
    assert manager.is_ready()
    (pid,) = _pids(manager.spawn_log)
    assert manager.pid_file.is_file()
    manager.stop()
    assert _wait_dead(pid)
    assert not manager.pid_file.exists()


@posix_only
def test_no_orphan_after_parent_sigkill(tmp_path, fake_binary, model):
    log = tmp_path / "spawns.log"
    script = textwrap.dedent(
        f"""
        import sys, time
        from pathlib import Path
        from voice_flow.vf1_engine import LlamaServerManager
        m = LlamaServerManager(run_dir=Path({str(tmp_path / 'run')!r}))
        ok = m.ensure_running(binary=Path({str(fake_binary)!r}), model_path=Path({str(model)!r}), ready_timeout=10)
        print("READY" if ok else "FAILED", flush=True)
        time.sleep(120)
        """
    )
    env = dict(os.environ, FAKE_LLAMA_LOG=str(log), PYTHONPATH=os.pathsep.join([str(SRC_DIR), os.environ.get("PYTHONPATH", "")]))
    parent = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert parent.stdout.readline().strip() == "READY"
        (server_pid,) = _pids(log)
        assert _alive(server_pid)
        parent.send_signal(signal.SIGKILL)
        # Deliberately not reaped yet: a zombie parent must not keep it alive.
        assert _wait_dead(server_pid, timeout=8), "llama-server outlived its killed parent"
        parent.wait(timeout=5)
    finally:
        if parent.poll() is None:
            parent.kill()
        for pid in _pids(log, 0, 0):
            if _alive(pid):
                os.kill(pid, signal.SIGKILL)


@posix_only
def test_stale_server_from_dead_app_is_killed_on_next_start(tmp_path, manager, fake_binary, model):
    # Simulate a server left behind by an app that died before its guard ran.
    alias = "voiceflow-s1-deadbeefdeadbeef"
    stale = subprocess.Popen(
        [str(fake_binary), "-m", str(model), "--port", "0", "--alias", alias],
        env=dict(os.environ, FAKE_LLAMA_DELAY="60"),
    )
    try:
        manager.run_dir.mkdir(parents=True, exist_ok=True)
        dead_owner = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_owner.wait()
        manager.pid_file.write_text(json.dumps({"pid": stale.pid, "owner_pid": dead_owner.pid, "alias": alias}))
        # An unrelated process must never be touched.
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        assert manager.kill_stale_from_pid_file() == [stale.pid]
        assert stale.wait(timeout=5) is not None
        assert bystander.poll() is None
        bystander.kill()
    finally:
        if stale.poll() is None:
            stale.kill()


@posix_only
def test_slow_start_is_shared_not_spawned_twice(manager, fake_binary, model, monkeypatch):
    monkeypatch.setenv("FAKE_LLAMA_DELAY", "1.5")
    results: list[bool] = []

    def start():
        results.append(manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=15))

    threads = [threading.Thread(target=start) for _ in range(3)]
    for t in threads:
        t.start()
        time.sleep(0.2)
    for t in threads:
        t.join(timeout=30)
    assert results == [True, True, True]
    assert manager.spawn_count == 1
    assert len(_pids(manager.spawn_log)) == 1
    # Already running: a later call reuses it.
    assert manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=5)
    assert manager.spawn_count == 1


@posix_only
def test_readiness_timeout_kills_what_it_started(manager, fake_binary, model, monkeypatch):
    monkeypatch.setenv("FAKE_LLAMA_DELAY", "60")
    assert manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=1.5) is False
    (pid,) = _pids(manager.spawn_log)
    assert _wait_dead(pid)
    assert manager.process is None
    assert child_processes.tracked() == [] or all(p.poll() is not None for p in child_processes.tracked())


@posix_only
def test_idle_stop_and_s1_idle_hook(manager, fake_binary, model, monkeypatch):
    from voice_flow import s1_engine

    assert manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=10)
    (pid,) = _pids(manager.spawn_log)
    assert manager.stop_if_idle(120.0) is False  # just used
    monkeypatch.setattr(vf1_engine, "_llama_server_manager", manager)
    monkeypatch.setattr(s1_engine, "_LLM_LOCK", threading.Lock())
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_last_used", 0.0, raising=False)
    assert s1_engine._release_idle_s1(s1_engine.LOCAL_MODEL_IDLE_SECONDS + 1.0) is True
    assert manager.process is None
    assert _wait_dead(pid)


@posix_only
def test_exit_hook_kills_tracked_process_group():
    proc = subprocess.Popen(
        ["/bin/sh", "-c", "sleep 60 & echo $!; wait"],
        stdout=subprocess.PIPE, text=True, **child_processes.new_tree_popen_kwargs(),
    )
    grandchild = int(proc.stdout.readline())
    child_processes.track(proc, "test")
    child_processes.kill_all(timeout=2)
    assert proc.poll() is not None
    assert _wait_dead(grandchild, 5)


@posix_only
def test_video_flow_process_manager_tracks_and_kills_tree():
    from voice_flow.video_flow_engine.process_manager import ProcessManager

    proc = subprocess.Popen(
        ["/bin/sh", "-c", "sleep 60 & echo $!; wait"],
        stdout=subprocess.PIPE, text=True, **child_processes.new_tree_popen_kwargs(),
    )
    grandchild = int(proc.stdout.readline())
    manager = ProcessManager()
    manager.register("job", proc)
    assert proc in child_processes.tracked()
    manager.cancel_job("job")
    assert _wait_dead(grandchild, 5)
    manager.unregister("job", proc)
    assert proc not in child_processes.tracked()


def test_windows_job_object_assignment_path(monkeypatch):
    calls: dict = {}

    class FakeKernel32:
        def CreateJobObjectW(self, attrs, name):
            calls["create"] = (attrs, name)
            return 4321

        def SetInformationJobObject(self, job, info_class, info_ref, size):
            calls["set"] = (job, info_class, info_ref._obj.BasicLimitInformation.LimitFlags, size)
            return 1

        def AssignProcessToJobObject(self, job, handle):
            calls["assign"] = (job, handle)
            return 1

        def CloseHandle(self, handle):
            calls["close"] = handle
            return 1

    monkeypatch.setattr(child_processes.sys, "platform", "win32")
    monkeypatch.setattr(child_processes, "_load_kernel32", lambda: FakeKernel32())
    monkeypatch.setattr(child_processes, "_job_handle", None)
    monkeypatch.setattr(child_processes, "_job_failed", False)
    proc = types.SimpleNamespace(pid=999, _handle=77)
    assert child_processes.assign_to_kill_on_close_job(proc) is True
    assert calls["create"] == (None, None)
    job, info_class, flags, size = calls["set"]
    assert job == 4321 and info_class == 9 and size > 0
    assert flags & child_processes.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert flags & child_processes.JOB_OBJECT_LIMIT_BREAKAWAY_OK
    assert calls["assign"] == (4321, 77)
    assert "close" not in calls  # job handle must stay open for the app lifetime
    # The job is created once and reused.
    calls.clear()
    assert child_processes.assign_to_kill_on_close_job(types.SimpleNamespace(pid=1000, _handle=78))
    assert "create" not in calls and calls["assign"] == (4321, 78)


def test_job_object_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(child_processes.sys, "platform", "linux")
    monkeypatch.setattr(child_processes, "_load_kernel32", lambda: pytest.fail("must not load kernel32"))
    assert child_processes.assign_to_kill_on_close_job(types.SimpleNamespace(pid=1, _handle=1)) is False


# --------------------------------------------------------------------- M-R-2
def test_health_check_rejects_foreign_server_on_port():
    foreign = _Server(lambda req: (200, {"status": "ok", "data": [{"id": "some-other-model"}]}))
    try:
        assert not vf1_engine.verify_llama_server_identity(
            "127.0.0.1", foreign.port, "voiceflow-s1-0123456789abcdef", "/models/s1-mini-q4_k_m.gguf"
        )
        engine = VF1Engine(VF1EngineConfig(server_port=foreign.port))
        monkey_manager = LlamaServerManager()
        engine._server_manager = lambda: monkey_manager  # type: ignore[method-assign]
        assert engine.is_server_healthy() is False
        # Dictation is never sent to an unverified port.
        assert engine._run_llama_server_inference("secret dictation", time.perf_counter() + 2) == ""
        assert not any("/completion" in line for line in foreign.requests)
    finally:
        foreign.close()


def test_identity_accepts_matching_alias_and_rejects_loading():
    state = {"loading": True}

    def handler(req):
        if state["loading"]:
            return 503, {"error": {"message": "Loading model"}}
        return 200, {"data": [{"id": "voiceflow-s1-feedfacefeedface"}]}

    server = _Server(handler)
    try:
        assert not vf1_engine.verify_llama_server_identity("127.0.0.1", server.port, "voiceflow-s1-feedfacefeedface", None)
        state["loading"] = False
        assert vf1_engine.verify_llama_server_identity("127.0.0.1", server.port, "voiceflow-s1-feedfacefeedface", None)
    finally:
        server.close()


@posix_only
def test_ensure_running_fails_closed_when_port_is_taken(manager, fake_binary, model):
    foreign = _Server(lambda req: (200, {"status": "ok"}))
    try:
        assert manager.ensure_running(binary=fake_binary, model_path=model, port=foreign.port, ready_timeout=3) is False
        assert manager.process is None
    finally:
        foreign.close()


def test_default_config_uses_no_fixed_port():
    assert VF1EngineConfig().server_port == 0
    assert VF1EngineConfig().trust_external_server is False


def test_no_in_process_copy_while_server_process_alive(monkeypatch):
    engine = VF1Engine(VF1EngineConfig(backend="auto", auto_start_server=False))
    fake_manager = types.SimpleNamespace(process_alive=lambda: True, is_ready=lambda: False)
    engine._server_manager = lambda: fake_manager  # type: ignore[method-assign]
    from voice_flow import s1_engine

    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: pytest.fail("in-process path must not run"))
    assert engine._run_native_inference("prompt", time.perf_counter() + 1) == ""


# ---------------------------------------------------------- S1 backend state
def test_s1_server_fallback_is_used_after_failed_in_process_warm(monkeypatch, tmp_path):
    from voice_flow import s1_engine

    constructed = []

    class BrokenLlama:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            raise RuntimeError("cannot load")

    model_path = tmp_path / "model.gguf"
    monkeypatch.setattr(s1_engine, "get_s1_model_path", lambda: model_path)
    monkeypatch.setattr(s1_engine, "is_s1_runtime_available", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **_k: True)
    monkeypatch.setattr(s1_engine, "_LLM_LOCK", threading.Lock())
    monkeypatch.setattr(s1_engine, "register_idle_cleanup", lambda *_a, **_k: None)
    monkeypatch.setattr(s1_engine, "idle_time", lambda: 0.0)
    monkeypatch.setattr(s1_engine, "_s1_server_ready", lambda: True)
    monkeypatch.setattr(s1_engine, "_polish_chunk_with_server", lambda chunk, *_a: "Hello there.")
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_cached_llm_path", None, raising=False)
    monkeypatch.setattr(s1_engine.polish_with_s1, "_s1_server_backend_path", None, raising=False)
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=BrokenLlama))

    assert s1_engine.warm_s1_model(timeout_seconds=1.0) is True
    assert s1_engine.polish_with_s1._cached_llm_path is None
    assert s1_engine._polish_with_s1_impl("hello there") == "Hello there."
    assert s1_engine._polish_with_s1_impl("hello there") == "Hello there."
    assert len(constructed) == 1  # in-process load is not retried (one backend)


# ------------------------------------------------------------------- B6 proxy
@pytest.fixture
def proxy_and_target(monkeypatch):
    proxy = _Server(lambda req: (200, {"via": "proxy"}))
    target = _Server(lambda req: (200, {"via": "direct", "contract_version": None}))
    for key in ("NO_PROXY", "no_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy.port}")
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.port}")
    yield proxy, target
    proxy.close()
    target.close()


def test_localhost_calls_ignore_http_proxy_env(proxy_and_target):
    proxy, target = proxy_and_target
    # Sanity: a default urllib opener built now would route loopback via the proxy.
    with urllib.request.build_opener().open(f"http://127.0.0.1:{target.port}/x", timeout=3) as resp:
        assert json.load(resp)["via"] == "proxy"
    proxy.requests.clear()

    with local_http.open_local(f"http://127.0.0.1:{target.port}/health", timeout=3) as resp:
        assert json.load(resp)["via"] == "direct"
    opener = urllib.request.build_opener(local_http.LoopbackBypassProxyHandler())
    with opener.open(f"http://localhost:{target.port}/api/runtime", timeout=3) as resp:
        assert json.load(resp)["via"] == "direct"
    # Remote hosts still use the configured proxy.
    with opener.open("http://example.invalid/remote", timeout=3) as resp:
        assert json.load(resp)["via"] == "proxy"
    assert [line.split()[1] for line in proxy.requests] == ["http://example.invalid/remote"]


def test_runtime_guard_and_llama_identity_bypass_proxy(proxy_and_target):
    from voice_flow import runtime_guard

    proxy, target = proxy_and_target
    runtime_guard._runtime_payload(host="127.0.0.1", port=target.port, timeout=2)
    vf1_engine.verify_llama_server_identity("127.0.0.1", target.port, "voiceflow-s1-x", None)
    assert proxy.requests == []
    assert target.requests


def test_open_local_refuses_remote_urls():
    with pytest.raises(ValueError):
        local_http.open_local("http://example.com/", timeout=1)


def test_child_environment_bypasses_proxy_for_loopback(monkeypatch):
    from voice_flow.video_flow_engine import code2video_runner, narova_runner

    monkeypatch.setenv("NO_PROXY", "corp.example")
    env = local_http.no_proxy_environment()
    assert env["NO_PROXY"].split(",")[:2] == ["corp.example", "127.0.0.1"]
    assert "localhost" in env["no_proxy"]
    for module in (narova_runner, code2video_runner):
        child_env = module._safe_environment()
        assert "127.0.0.1" in child_env["NO_PROXY"] and "localhost" in child_env["no_proxy"]


@posix_only
def test_llama_server_child_gets_no_proxy_env(manager, fake_binary, model):
    assert manager.ensure_running(binary=fake_binary, model_path=model, ready_timeout=10)
    (pid,) = _pids(manager.spawn_log)
    env = psutil.Process(pid).environ()
    assert "127.0.0.1" in env.get("NO_PROXY", "")
