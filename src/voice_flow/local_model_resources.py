"""Release inactive local-model resources with one lightweight shared worker."""
from __future__ import annotations

import logging
import threading
import time
import weakref
from typing import Callable, Literal

LOCAL_MODEL_IDLE_SECONDS = 120.0
ModelKind = Literal["speech", "polish"]
_Callback = Callable[[float], bool | None]
_callbacks: dict[str, tuple[_Callback | weakref.WeakMethod, ModelKind | None] | _Callback | weakref.WeakMethod] = {}
_lock = threading.Lock()
_worker: threading.Thread | None = None
_wake = threading.Event()
_active_uses: dict[ModelKind, int] = {"speech": 0, "polish": 0}
_cleanup_requested: set[ModelKind] = set()
_kind_gates: dict[ModelKind, threading.Lock] = {"speech": threading.Lock(), "polish": threading.Lock()}
_cleanup_context = threading.local()
log = logging.getLogger(__name__)
_idle_clock = time.monotonic


def idle_time() -> float:
    """Use the resource clock independently of an inference deadline clock."""
    return _idle_clock()


class ModelUseLease:
    """Idempotent token keeping one local model family available."""

    def __init__(self, kind: ModelKind) -> None:
        self.kind = kind
        self._released = False
        self._release_lock = threading.Lock()

    def release(self) -> None:
        with self._release_lock:
            if self._released:
                return
            self._released = True
        with _lock:
            remaining = max(0, _active_uses[self.kind] - 1)
            _active_uses[self.kind] = remaining
            if remaining == 0:
                _cleanup_requested.add(self.kind)
        _wake.set()

    def __enter__(self) -> "ModelUseLease":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def acquire_model_use(kind: ModelKind) -> ModelUseLease:
    """Keep *kind* resident until the returned lease is released."""
    if kind not in _active_uses:
        raise ValueError(f"Unknown local model kind: {kind!r}")
    with _kind_gates[kind]:
        with _lock:
            _active_uses[kind] += 1
            _cleanup_requested.discard(kind)
    _ensure_worker()
    return ModelUseLease(kind)


def has_active_model_use(kind: ModelKind) -> bool:
    """Return whether a demand lease currently protects *kind*."""
    with _lock:
        return _active_uses.get(kind, 0) > 0


def cleanup_requested(kind: ModelKind) -> bool:
    """Return whether demand ended and prompt cleanup is still outstanding."""
    with _lock:
        return kind in _cleanup_requested and _active_uses.get(kind, 0) == 0


def cleanup_is_forced(kind: ModelKind) -> bool:
    """Return whether the current callback is servicing a demand-end request."""
    return getattr(_cleanup_context, "kind", None) == kind


def notify_models_available(kind: ModelKind) -> None:
    """Retry a pending cleanup after loading or inference leaves a busy section."""
    with _lock:
        pending = kind in _cleanup_requested and _active_uses.get(kind, 0) == 0
    if pending:
        _wake.set()


def request_model_cleanup(kind: ModelKind) -> None:
    """Request prompt cleanup now, or as soon as current users finish."""
    if kind not in _active_uses:
        raise ValueError(f"Unknown local model kind: {kind!r}")
    with _lock:
        _cleanup_requested.add(kind)
    _ensure_worker()
    _wake.set()


def cleanup_idle_models(now: float | None = None) -> None:
    """Run bounded cleanup; individual engines decide whether they are busy."""
    timestamp = idle_time() if now is None else now
    with _lock:
        callbacks: list[tuple[_Callback, ModelKind | None]] = []
        for name, registered in tuple(_callbacks.items()):
            entry, kind = registered if isinstance(registered, tuple) else (registered, None)
            callback = entry() if isinstance(entry, weakref.WeakMethod) else entry
            if callback is None:
                _callbacks.pop(name, None)
            else:
                callbacks.append((callback, kind))
    untagged = [callback for callback, kind in callbacks if kind is None]
    grouped = {
        kind: [callback for callback, callback_kind in callbacks if callback_kind == kind]
        for kind in _active_uses
    }
    for callback in untagged:
        try:
            callback(timestamp)
        except Exception:
            log.debug("Local-model idle cleanup failed", exc_info=True)
    for kind, kind_callbacks in grouped.items():
        if not kind_callbacks:
            continue
        # Serialize the whole family with new demand. A request is complete
        # only after every family callback has had a chance to release memory.
        with _kind_gates[kind]:
            with _lock:
                if _active_uses.get(kind, 0) > 0:
                    continue
                forced = kind in _cleanup_requested
            all_complete = True
            _cleanup_context.kind = kind if forced else None
            for callback in kind_callbacks:
                try:
                    completed = callback(timestamp)
                    if completed is False:
                        all_complete = False
                except Exception:
                    all_complete = False
                    log.debug("Local-model idle cleanup failed", exc_info=True)
            _cleanup_context.kind = None
            if all_complete:
                with _lock:
                    if _active_uses.get(kind, 0) == 0:
                        _cleanup_requested.discard(kind)


def _run() -> None:
    while True:
        _wake.wait(15.0)
        _wake.clear()
        cleanup_idle_models()


def _ensure_worker() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="local-model-idle-cleanup", daemon=True)
            try:
                _worker.start()
            except RuntimeError:
                _worker = None
                log.warning("Could not start local-model idle cleanup worker")


def register_idle_cleanup(name: str, callback: _Callback, *, kind: ModelKind | None = None) -> None:
    """Register a model family once; never create a worker per recording."""
    if kind is not None and kind not in _active_uses:
        raise ValueError(f"Unknown local model kind: {kind!r}")
    registered = weakref.WeakMethod(callback) if getattr(callback, "__self__", None) is not None else callback
    with _lock:
        _callbacks[name] = (registered, kind)
    _ensure_worker()
