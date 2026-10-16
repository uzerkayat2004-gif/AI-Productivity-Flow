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


class NativeASRAbandonedError(NativeASRBusyError):
    """The caller's soft deadline or cancellation fired before the reply.

    The worker stays alive: the in-flight native call finishes in the
    background and its reply is discarded. Only a native call that outlives
    its own hard ``timeout`` (a genuinely hung worker) poisons the client.
    """


WORKER_SCRIPT = Path(__file__).with_name("nemotron_native_worker.py")
_SPAWN_LOCK = threading.Lock()
_GENERATIONS = itertools.count(1)
MAX_AUDIO_BYTES = 64 * 1024 * 1024
# Cleanup operations run even when their caller already gave up: skipping a
# close would leak native state that makes every later stream "busy".
_ALWAYS_RUN_OPS = frozenset({"stream_close", "recognizer_close", "shutdown"})


class NativeASRClient:
    def __init__(self, dll_path: str, interpreter: str | None = None):
        self.generation = next(_GENERATIONS)
        self.error: NativeASRWorkerError | None = None
        self._lock = threading.Lock()
        self._requests: queue.Queue = queue.Queue(maxsize=64)
        self._audio_bytes = 0
        self._ids = itertools.count(1)
        self._closed = threading.Event()
        # (op, started monotonic, hard timeout) of the request being executed.
        self._inflight: tuple[str, float, float] | None = None
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
                    with self._lock:
                        if box.get("abandoned") and request["op"] not in _ALWAYS_RUN_OPS:
                            # The caller gave up before submission reached the
                            # worker; never run work nobody is waiting for.
                            box["error"] = NativeASRAbandonedError("Speech request abandoned before execution")
                            continue
                        box["started"] = time.monotonic()
                        self._inflight = (request["op"], box["started"], box.get("timeout", 120.0))
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
                        if box.get("abandoned") and request["op"] == "stream_open":
                            self._close_orphan_stream(response["value"])
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
                        self._inflight = None
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

    def _stalled_inflight(self, now: float):
        """Return the op of an executing request that outlived its hard timeout."""
        inflight = self._inflight
        if inflight is not None and now - inflight[1] >= inflight[2]:
            return inflight[0]
        return None

    def _close_orphan_stream(self, value) -> None:
        """Close a stream whose opener abandoned the call (RPC thread only)."""
        handle = value.get("handle") if isinstance(value, dict) else None
        if not handle:
            return
        request = {"id": next(self._ids), "generation": self.generation,
                   "op": "stream_close", "values": {"handle": handle}}
        self._connection.send(request)
        response = self._connection.recv()
        if not isinstance(response, dict) or response.get("id") != request["id"]:
            raise ValueError("invalid response")

    def call(self, op: str, *, deadline=None, cancelled=None, timeout: float = 120.0, **values):
        """Run one worker operation.

        ``deadline`` and ``cancelled`` are *soft*: when either fires the call
        raises :class:`NativeASRAbandonedError` (a ``NativeASRBusyError``) and
        the worker keeps running; an already-executing native call completes in
        the background and its reply is dropped. ``timeout`` is the *hard*
        bound on native execution time, measured from when the worker starts
        the request (not while it waits in the queue). Only that hard bound, a
        dead process or a protocol error poisons this client.
        """
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
        done, box = threading.Event(), {"timeout": float(timeout)}
        request = {"id": next(self._ids), "generation": self.generation, "op": op, "values": values}
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
                raise NativeASRBusyError("Speech request queue is full; recording retained")

        def abandon(reason: str):
            with self._lock:
                box["abandoned"] = True
            return NativeASRAbandonedError(f"Speech {op} {reason}; worker kept alive, recording retained")

        while True:
            now = time.monotonic()
            limit = deadline() if callable(deadline) else deadline
            if cancelled is not None and cancelled.is_set():
                raise abandon("cancelled")
            if limit is not None and now >= limit:
                raise abandon("deadline exceeded")
            started = box.get("started")
            if started is not None and now - started >= timeout:
                raise self._poison(op, "hard timeout")
            stalled = self._stalled_inflight(now)
            if stalled is not None:
                # An earlier (possibly abandoned) native call is hung.
                raise self._poison(stalled, "hard timeout")
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
                self.call("shutdown", timeout=0.3, deadline=time.monotonic() + 1.0)
            except (NativeASRWorkerError, NativeASRBusyError):
                pass
        with self._lock:
            self._closed.set()
            self._lifetime_writer.close()
        if self._process.poll() is None:
            self._poison("shutdown", "closed")
        self._thread.join(timeout=0.3)
