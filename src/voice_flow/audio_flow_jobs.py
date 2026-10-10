"""Bounded, independently cancellable background Audio Flow summary jobs."""
from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable


@dataclass
class AudioFlowJob:
    job_id: str
    text: str
    depth: str
    style: str
    title: str
    run: Callable[["AudioFlowJob"], Any] = field(repr=False)
    status: str = "queued"
    progress: int = 0
    stage: str = "Queued"
    result: Any = None
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    changed: threading.Event = field(default_factory=threading.Event, repr=False)
    notify_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    terminal_notified: bool = False

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()


class AudioFlowJobs:
    """Run at most ``max_workers`` summaries concurrently and retain job state."""

    def __init__(
        self,
        max_workers: int = 2,
        on_change: Callable[[AudioFlowJob], None] | None = None,
        on_evict: Callable[[str], None] | None = None,
        *,
        max_queued: int = 16,
        retained_terminal: int = 20,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._max_workers = max_workers
        self._max_queued = max_queued
        self._retained_terminal = retained_terminal
        self._on_change = on_change
        self._on_evict = on_evict
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._jobs: dict[str, AudioFlowJob] = {}
        self._queue: deque[str] = deque()
        self._closed = False
        self._workers = [
            threading.Thread(target=self._worker, name=f"AudioFlowSummary-{index + 1}", daemon=True)
            for index in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()

    def submit(
        self,
        *,
        job_id: str,
        text: str,
        depth: str,
        style: str,
        title: str,
        run: Callable[[AudioFlowJob], Any],
        before_enqueue: Callable[[], None] | None = None,
    ) -> AudioFlowJob:
        with self._condition:
            if self._closed:
                raise RuntimeError("Audio Flow summary manager is closed")
            if job_id in self._jobs:
                raise ValueError(f"Audio summary job already exists: {job_id}")
            if len(self._queue) >= self._max_queued:
                raise RuntimeError("Audio summary queue is full. Wait for a job to finish.")
            if before_enqueue is not None:
                before_enqueue()
            job = AudioFlowJob(job_id, text, depth, style, title, run)
            self._jobs[job_id] = job
            self._queue.append(job_id)
            self._condition.notify()
        self._notify(job, "queued")
        return job

    def get(self, job_id: str) -> AudioFlowJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self) -> tuple[AudioFlowJob, ...]:
        with self._lock:
            return tuple(self._jobs.values())

    def update_progress(self, job: AudioFlowJob, progress: int, stage: str) -> bool:
        with self._lock:
            if job.status != "running" or job.is_cancelled():
                return False
            job.progress = max(0, min(99, int(progress)))
            job.stage = str(stage)
            job.changed.set()
        self._notify(job, "running")
        return True

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None or job.status not in {"queued", "running"}:
                return False
            job.cancel_event.set()
            job.status = "cancelled"
            job.stage = "Cancelled"
            try:
                self._queue.remove(job_id)
            except ValueError:
                pass
            job.changed.set()
            self._condition.notify_all()
        self._notify(job, "cancelled")
        self._release_source(job)
        self._prune_terminal()
        return True

    def mark_ready(self, job: AudioFlowJob, result: Any) -> bool:
        with self._lock:
            if job.status != "running" or job.is_cancelled():
                if job.status == "running":
                    job.status = "cancelled"
                    job.stage = "Cancelled"
                    job.changed.set()
                else:
                    return False
                cancelled = True
            else:
                cancelled = False
            if cancelled:
                pass
            else:
                job.result = result
                job.status = "ready"
                job.progress = 100
                job.stage = "Audio ready"
                job.changed.set()
            status = job.status
        self._notify(job, status)
        self._release_source(job)
        self._prune_terminal()
        return not cancelled

    def mark_failed(self, job: AudioFlowJob, error: str) -> None:
        with self._lock:
            if job.status != "running":
                return
            job.status = "failed"
            job.error = str(error)
            job.stage = str(error)
            job.changed.set()
            status = job.status
        self._notify(job, status)
        self._release_source(job)
        self._prune_terminal()

    def shutdown(self, timeout: float = 2.0) -> None:
        with self._condition:
            to_cancel: list[str] = []
            if self._closed:
                workers = tuple(self._workers)
            else:
                self._closed = True
                to_cancel = [job.job_id for job in self._jobs.values() if job.status in {"queued", "running"}]
                workers = tuple(self._workers)
        for job_id in to_cancel:
            self.cancel(job_id)
        with self._condition:
            self._queue.clear()
            self._condition.notify_all()
        # Join each worker only for the remaining bounded shutdown budget.
        end_at = time.monotonic() + max(0.0, timeout)
        for worker in workers:
            worker.join(max(0.0, end_at - time.monotonic()))

    def _worker(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                job_id = self._queue.popleft()
                job = self._jobs.get(job_id)
                if job is None or job.status != "queued":
                    continue
                if job.is_cancelled():
                    job.status = "cancelled"
                    job.stage = "Cancelled"
                    job.changed.set()
                    continue
                job.status = "running"
                job.stage = "Preparing summary"
                job.changed.set()
            self._notify(job, "running")
            try:
                result = job.run(job)
                self.mark_ready(job, result)
            except Exception as exc:
                self.mark_failed(job, str(exc))

    def _notify(self, job: AudioFlowJob, expected_status: str) -> None:
        callback = self._on_change
        if callback is None:
            return
        with job.notify_lock:
            with self._lock:
                if job.status != expected_status:
                    return
                if expected_status in {"ready", "failed", "cancelled"}:
                    if job.terminal_notified:
                        return
                    job.terminal_notified = True
                snapshot = copy.copy(job)
            try:
                callback(snapshot)
            except Exception:
                pass

    def _release_source(self, job: AudioFlowJob) -> None:
        job.text = ""
        job.run = lambda _job: None

    def _prune_terminal(self) -> None:
        removed: list[str] = []
        with self._lock:
            terminal = [
                job_id for job_id, job in self._jobs.items()
                if job.status in {"ready", "failed", "cancelled"}
            ]
            excess = len(terminal) - self._retained_terminal
            for job_id in terminal[:max(0, excess)]:
                self._jobs.pop(job_id, None)
                removed.append(job_id)
        if self._on_evict is not None:
            for job_id in removed:
                try:
                    self._on_evict(job_id)
                except Exception:
                    pass
