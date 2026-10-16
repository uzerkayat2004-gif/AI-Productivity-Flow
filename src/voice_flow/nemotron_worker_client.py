"""Bounded local RPC to the persistent native speech owner; no native imports."""
from __future__ import annotations

import itertools
import multiprocessing
from multiprocessing.connection import Connection
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time


class NativeASRWorkerError(RuntimeError):
    """Native speech is unavailable; preserve the recording instead of retrying."""


class NativeASRBusyError(RuntimeError):
    """A previous stream has not closed; do not collide with its native state."""


WORKER_SCRIPT = Path(__file__).with_name("nemotron_native_worker.py")
_SPAWN_LOCK = threading.Lock()
_GENERATIONS = itertools.count(1)
MAX_AUDIO_BYTES = 64 * 1024 * 1024


class NativeASRClient:
    def __init__(self, dll_path: str, interpreter: str | None = None):
        self.generation = next(_GENERATIONS)
        self.error: NativeASRWorkerError | None = None
        self._lock = threading.Lock()
        self._requests: queue.Queue = queue.Queue(maxsize=64)
        self._audio_bytes = 0
        self._ids = itertools.count(1)
        self._closed = threading.Event()
        parent, child = multiprocessing.Pipe(duplex=True)
        lifetime_child, self._lifetime_writer = multiprocessing.Pipe(duplex=False)
        self._connection = parent
        executable = interpreter or sys.executable
        args = [executable, "-I", "-B", "-u", str(WORKER_SCRIPT), str(child.fileno()), str(lifetime_child.fileno())]
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL, "close_fds": True}
        try:
            with _SPAWN_LOCK:
                if os.name == "nt":
                    startup = subprocess.STARTUPINFO()
                    startup.lpAttributeList = {"handle_list": [child.fileno(), lifetime_child.fileno()]}
                    os.set_handle_inheritable(child.fileno(), True)
                    os.set_handle_inheritable(lifetime_child.fileno(), True)
                    kwargs.update(startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    kwargs["pass_fds"] = (child.fileno(), lifetime_child.fileno())
                try:
                    self._process = subprocess.Popen(args, **kwargs)
                finally:
                    if os.name == "nt":
                        os.set_handle_inheritable(child.fileno(), False)
                        os.set_handle_inheritable(lifetime_child.fileno(), False)
        except Exception as exc:
            parent.close()
            self._lifetime_writer.close()
            raise NativeASRWorkerError("Local speech worker could not start; recording retained") from exc
        finally:
            child.close()
            lifetime_child.close()
        self._thread = threading.Thread(target=self._serve, name="native-asr-rpc", daemon=True)
        try:
            self._thread.start()
        except (RuntimeError, MemoryError) as exc:
            error = self._poison("startup", "RPC thread could not start")
            self._connection.close()
            raise error from exc
        self.dll_path = str(dll_path)

    def _poison(self, stage: str, reason: str) -> NativeASRWorkerError:
        with self._lock:
            if self.error is None:
                self.error = NativeASRWorkerError(f"Local speech worker unavailable ({stage}: {reason}); recording retained")
                self._closed.set()
                self._lifetime_writer.close()
                if self._process.poll() is None:
                    try:
                        self._process.terminate()
                    except OSError:
                        pass
            error = self.error
        # Terminating only our child also unblocks a send/receive stuck in RPC.
        try:
            self._process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
            except OSError:
                pass
            try:
                self._process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        return error

    def _serve(self):
        try:
            while not self._closed.is_set():
                try:
                    task = self._requests.get(timeout=0.02)
                except queue.Empty:
                    continue
                request, done, box, audio_bytes = task
                try:
                    if self._closed.is_set():
                        raise OSError("closed generation")
                    self._connection.send(request)
                    response = self._connection.recv()
                    if self._closed.is_set():
                        raise OSError("closed generation")
                    if not isinstance(response, dict) or response.get("id") != request["id"]:
                        raise ValueError("invalid response")
                    if response.get("generation") != self.generation:
                        raise ValueError("invalid generation")
                    if "protocol_error" in response:
                        code = response.get("failure_code")
                        if code not in ("memory_error", "invalid_request", "native_call_error"):
                            raise ValueError("invalid failure code")
                        box["error"] = self._poison(request["op"], "worker_" + code)
                    else:
                        box["value"] = response["value"]
                except MemoryError:
                    box["error"] = self._poison(request["op"], "ipc_memory_error")
                except (EOFError, OSError):
                    exitcode = self._process.poll()
                    reason = f"worker_exit_{exitcode}" if exitcode is not None else "ipc_error"
                    box["error"] = self._poison(request["op"], reason)
                except (ValueError, KeyError):
                    box["error"] = self._poison(request["op"], "invalid_response")
                finally:
                    with self._lock:
                        self._audio_bytes -= audio_bytes
                    done.set()
        finally:
            self._connection.close()
            while True:
                try:
                    _, done, box, audio_bytes = self._requests.get_nowait()
                except queue.Empty:
                    break
                box["error"] = self.error or NativeASRWorkerError("Local speech worker closed")
                with self._lock:
                    self._audio_bytes -= audio_bytes
                done.set()

    def call(self, op: str, *, deadline=None, cancelled=None, timeout: float = 120.0, **values):
        if self.error:
            raise self.error
        if self._closed.is_set():
            raise NativeASRWorkerError("Local speech worker closed")
        if cancelled is not None and cancelled.is_set():
            raise NativeASRBusyError("Speech operation cancelled before submission; recording retained")
        first_limit = deadline() if callable(deadline) else deadline
        if first_limit is not None and time.monotonic() >= first_limit:
            raise NativeASRBusyError("Speech deadline expired before submission; recording retained")
        audio = values.get("audio", b"")
        if not isinstance(audio, bytes) or len(audio) > MAX_AUDIO_BYTES:
            raise ValueError("invalid audio payload size")
        done, box = threading.Event(), {}
        request = {"id": next(self._ids), "generation": self.generation, "op": op, "values": values}
        absolute = time.monotonic() + timeout
        full = False
        with self._lock:
            if self._closed.is_set():
                raise self.error or NativeASRWorkerError("Local speech worker closed")
            if self._audio_bytes + len(audio) > MAX_AUDIO_BYTES:
                raise NativeASRBusyError("Speech audio queue is full; recording retained")
            self._audio_bytes += len(audio)
            try:
                self._requests.put_nowait((request, done, box, len(audio)))
            except queue.Full:
                self._audio_bytes -= len(audio)
                full = True
        if full:
            raise self._poison(op, "request queue full")
        while True:
            limit = deadline() if callable(deadline) else deadline
            if cancelled is not None and cancelled.is_set():
                raise self._poison(op, "cancelled")
            if time.monotonic() >= min(absolute, limit if limit is not None else absolute):
                raise self._poison(op, "deadline exceeded")
            if self.error:
                raise self.error
            if done.wait(0.02):
                if "error" in box:
                    raise box["error"]
                return box["value"]
            if self._process.poll() is not None:
                raise self._poison(op, f"worker_exit_{self._process.returncode}")

    def close(self):
        if not self._closed.is_set():
            try:
                self.call("shutdown", timeout=0.3)
            except NativeASRWorkerError:
                pass
        with self._lock:
            self._closed.set()
            self._lifetime_writer.close()
        if self._process.poll() is None:
            self._poison("shutdown", "closed")
        self._thread.join(timeout=0.3)
