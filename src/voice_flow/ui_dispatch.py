"""One owner-thread callback pump per Tk root; workers only touch Python state."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

log = logging.getLogger(__name__)


class UiDispatcher:
    MAX_CALLBACKS = 32
    MAX_SECONDS = 0.004
    ACTIVE_MS = 20
    IDLE_MS = 30

    def __init__(self) -> None:
        self.root: Any = None
        self.owner_id: int | None = None
        self.pending: queue.Queue[Callable[[], None]] = queue.Queue()
        self._timer: Any = None
        self._draining = False
        self._forward: UiDispatcher | None = None
        self._lock = threading.Lock()
        self._epoch = 0

    def attach(self, root: Any) -> UiDispatcher:
        """Called by the root owner only, before entering its event loop."""
        if self._forward is not None:
            return self._forward.attach(root)
        if self.root is not None:
            self._assert_owner()
            if self.root is not root:
                self._unbind()
        shared = getattr(root, "_voice_flow_dispatcher", None)
        if shared is not None and shared is not self:
            shared._assert_owner()
            with self._lock:
                self._forward = shared
                while True:
                    try:
                        shared.pending.put(self.pending.get_nowait())
                    except queue.Empty:
                        break
            return shared
        self.root = root
        self.owner_id = threading.get_ident()
        root._voice_flow_dispatcher = self
        self._arm(self.ACTIVE_MS)
        return self

    def _unbind(self) -> None:
        """Discard work for a replaced root and invalidate its scheduled poll."""
        self._assert_owner()
        if self._timer is not None:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                # A destroyed root cannot cancel Tcl commands anymore.
                pass
        if getattr(self.root, "_voice_flow_dispatcher", None) is self:
            self.root._voice_flow_dispatcher = None
        with self._lock:
            self._epoch += 1
            self._timer = None
            self.root = None
            while True:
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    break

    def is_owner(self) -> bool:
        return self.root is not None and threading.get_ident() == self.owner_id

    def submit(self, callback: Callable[[], None]) -> None:
        with self._lock:
            forward = self._forward
            inline = forward is None and self.is_owner() and not self._draining and self.pending.empty()
            if forward is None and not inline:
                self.pending.put(callback)
        if forward is not None:
            forward.submit(callback)
        elif inline:
            self._invoke(callback)

    def _assert_owner(self) -> None:
        if not self.is_owner():
            raise RuntimeError("UI dispatcher must be serviced by its root owner")

    @staticmethod
    def _invoke(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as exc:
            # Exception messages/callback arguments may contain selected text
            # or provider identities. Record only the exception type.
            log.warning("UI callback failed (%s)", type(exc).__name__)

    def _arm(self, delay: int) -> None:
        self._assert_owner()
        if self._timer is None:
            try:
                epoch = self._epoch
                self._timer = self.root.after(delay, lambda: self._poll(epoch))
            except Exception as exc:
                log.warning("UI callback pump unavailable (%s)", type(exc).__name__)

    def drain(self, max_callbacks: int | None = None) -> None:
        self._assert_owner()
        budget = self.MAX_CALLBACKS if max_callbacks is None else max(0, min(max_callbacks, self.MAX_CALLBACKS))
        epoch = self._epoch
        deadline = time.monotonic() + self.MAX_SECONDS
        self._draining = True
        try:
            for _ in range(budget):
                if epoch != self._epoch or time.monotonic() >= deadline:
                    break
                try:
                    callback = self.pending.get_nowait()
                except queue.Empty:
                    break
                self._invoke(callback)
        finally:
            self._draining = False

    def _poll(self, epoch: int) -> None:
        if epoch != self._epoch:
            return
        self._assert_owner()
        self._timer = None
        self.drain()
        if epoch != self._epoch:
            return
        self._arm(self.IDLE_MS if self.pending.empty() else self.ACTIVE_MS)
