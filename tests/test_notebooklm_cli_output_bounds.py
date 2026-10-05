"""Local subprocess-output bounds for the native NotebookLM CLI seam."""

from __future__ import annotations

import os
import sys
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

import voice_flow.video_flow_engine.notebooklm.provider as provider_module
from voice_flow.video_flow_engine.notebooklm.models import NotebookLMVideoError
from voice_flow.video_flow_engine.notebooklm.provider import (
    NotebookLMVideoProvider,
    _BoundedPipeCollector,
)


def _fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "fake_notebooklm.py"
    script.write_text(
        """import json, os, sys, time
mode = next((arg for arg in sys.argv if arg.startswith('--fixture=')), '--fixture=json').split('=', 1)[1]
pidfile = os.environ.get('FAKE_CLI_PIDFILE')
if pidfile:
    open(pidfile, 'w', encoding='utf-8').write(str(os.getpid()))
if mode == 'timeout':
    time.sleep(10)
elif mode == 'stdout':
    sys.stdout.write('o' * (32 * 1024 * 1024))
elif mode == 'stderr':
    sys.stderr.write('e' * (32 * 1024 * 1024))
elif mode == 'both':
    for _ in range(512):
        sys.stdout.write('o' * 65536); sys.stdout.flush()
        sys.stderr.write('e' * 65536); sys.stderr.flush()
else:
    print(json.dumps({'notebook_id': 'local-fixture'}))
""",
        encoding="utf-8",
    )
    launcher = tmp_path / "fake_notebooklm.cmd"
    launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    return launcher


def _provider(tmp_path: Path) -> NotebookLMVideoProvider:
    provider = NotebookLMVideoProvider(
        cli_path=_fake_cli(tmp_path),
        profile="test",
        workdir=tmp_path,
        sleep=lambda _seconds: None,
    )
    provider.sync_storage_state = lambda *args, **kwargs: None
    return provider


@pytest.mark.parametrize("fixture", ["stdout", "stderr", "both"])
def test_native_cli_rejects_oversized_output_without_retaining_it(tmp_path: Path, fixture: str) -> None:
    provider = _provider(tmp_path)
    tracemalloc.start()
    tracemalloc.reset_peak()
    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke((f"--fixture={fixture}",), timeout=15)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert caught.value.code == "CLI_OUTPUT_TOO_LARGE"
    assert "output" in caught.value.message.lower()
    assert peak < 12 * 1024 * 1024
    assert provider._active_proc is None


def test_native_cli_keeps_normal_json_and_runner_seam(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider._invoke(("--fixture=json",), timeout=5) == {"notebook_id": "local-fixture"}


def test_native_cli_timeout_cleans_process_tree_and_reader_threads(tmp_path: Path, monkeypatch) -> None:
    provider = _provider(tmp_path)
    baseline_threads = threading.active_count()
    pid_file = tmp_path / "grandchild.pid"
    monkeypatch.setenv("FAKE_CLI_PIDFILE", str(pid_file))
    started = time.monotonic()
    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("--fixture=timeout",), timeout=0.1)
    elapsed = time.monotonic() - started
    assert caught.value.code == "TIMEOUT"
    assert elapsed <= 2.0
    assert provider._active_proc is None
    time.sleep(0.1)
    assert threading.active_count() <= baseline_threads
    if pid_file.is_file():
        import psutil

        assert not psutil.pid_exists(int(pid_file.read_text(encoding="utf-8")))


def test_repeated_native_cli_requests_return_reader_thread_count_to_baseline(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    baseline_threads = threading.active_count()
    for _ in range(4):
        assert provider._invoke(("--fixture=json",), timeout=5)["notebook_id"] == "local-fixture"
    time.sleep(0.1)
    assert threading.active_count() <= baseline_threads


def test_blocked_pipe_reader_is_not_closed_cross_thread() -> None:
    class BlockingStream:
        def __init__(self) -> None:
            self.read_started = threading.Event()
            self.release = threading.Event()
            self.close_called = False

        def read(self, _size: int) -> bytes:
            self.read_started.set()
            self.release.wait()
            return b""

        def close(self) -> None:
            self.close_called = True

    stream = BlockingStream()
    collector = _BoundedPipeCollector(stream, 64, threading.Event())
    collector.start()
    assert stream.read_started.wait(0.5)
    assert not collector.join(0.01)
    assert not stream.close_called
    stream.release.set()
    assert collector.join(0.5)
    assert stream.close_called


def test_exited_process_is_never_targeted_by_tree_cleanup(monkeypatch) -> None:
    class ExitedProcess:
        pid = 12345

        def poll(self):
            return 0

        def kill(self):
            raise AssertionError("an exited PID must not be killed")

    monkeypatch.setattr(
        provider_module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not taskkill exited PID")),
    )
    provider_module._terminate_owned_process_tree(ExitedProcess())
