"""Silence-segmented streaming transcription for Voice Flow.

The recorder closes chunks at natural pauses and submits them here while the
user is still speaking.  A small, fixed worker pool overlaps independent
cloud requests and resampling work, while the collector exposes only a
contiguous, input-ordered prefix.  That gives release-time latency close to
the slowest outstanding chunk instead of the sum of every chunk's latency,
without allowing an out-of-order result to reorder words.

The class deliberately keeps the old one-argument transcriber contract.  New
transcribers can accept ``is_chunk`` and an absolute monotonic ``deadline``;
plain test doubles and alternate engines continue to receive only audio.
"""
from __future__ import annotations

import inspect
import logging
import queue
import re
import threading
import time

import numpy as np
import scipy.signal as sig

log = logging.getLogger(__name__)

# Two workers are enough to overlap the usual speech chunks without creating a
# request storm or contending excessively on the single local Whisper model.
# Keep this fixed and intentionally small: cloud providers are unreliable and
# an unbounded queue/worker fan-out would turn a long dictation into a thundering
# herd after release.
# NOTE (2026-09-10): reducing this default to 1 was tried and reverted — the
# repo's own concurrency tests (test_voice_flow_stt_concurrency.py) require
# two chunks to overlap, and the pool cap plus engine lock already bound
# local-model contention. Cloud chunks still benefit from the overlap.
STREAM_WORKER_COUNT = 2

_Task = tuple[int, int, tuple[np.ndarray, int]]
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def _chunk_to_16k(chunk: np.ndarray, native_sr: int) -> np.ndarray:
    """Native-rate (possibly multichannel) chunk -> 16 kHz mono float32."""
    if chunk.ndim > 1:
        mono = np.mean(chunk, axis=1).astype(np.float32)
    else:
        mono = chunk.flatten().astype(np.float32)
    if mono.size == 0:
        return mono
    if native_sr and native_sr != 16000:
        try:
            return sig.resample_poly(mono, 16000, native_sr).astype(np.float32)
        except Exception:
            # Never hand back native-rate audio labeled as 16 kHz — the model
            # would transcribe time-warped garbage and pollute the joined
            # transcript. An empty result marks the chunk failed so the
            # whole-buffer fallback keeps ownership of these words.
            return np.zeros(0, dtype=np.float32)
    return mono


class StreamTranscriber:
    """Background-transcribes recorder chunks as they close during a session.

    Results are terminally accounted for per sequence number.  This is more
    precise than deriving pending work from ``seq - results - failures``:
    collection may consume an early result while a later chunk is still in
    flight, and a cancelled worker may finish after the next session starts.
    """

    def __init__(self, transcriber: object, worker_count: int = STREAM_WORKER_COUNT) -> None:
        self._transcriber = transcriber
        self._accepts_is_chunk = False
        self._accepts_deadline = False
        self._accepts_model_ref = False
        try:
            signature = inspect.signature(self._transcriber.transcribe)
            params = signature.parameters.values()
            accepts_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
            self._accepts_is_chunk = accepts_kwargs or "is_chunk" in signature.parameters
            self._accepts_deadline = accepts_kwargs or "deadline" in signature.parameters
            self._accepts_model_ref = accepts_kwargs or "model_ref" in signature.parameters
        except (AttributeError, TypeError, ValueError):
            # Some extension-backed callables do not expose a signature.  Keep
            # the conservative one-argument behavior for those callables.
            pass

        self._queue: "queue.Queue[_Task | None]" = queue.Queue()
        self._workers: list[threading.Thread] = []
        # Compatibility for diagnostics/tests that used the old single worker
        # attribute.  It always points at the first live pool worker.
        self._worker: threading.Thread | None = None
        self._worker_count = max(1, min(int(worker_count), 4))
        self._worker_lock = threading.Lock()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)

        # Terminal results keyed by sequence.  An empty value is a terminal
        # failure, not an unfinished task; retaining the key lets the ordered
        # collector advance past a failed chunk without reordering later text.
        self._completed: dict[int, str] = {}
        # Kept for compatibility with the previous implementation and useful
        # in debugging; collection removes entries as they are emitted.
        self._results: list[tuple[int, str]] = []
        self._pending: dict[int, float] = {}
        self._durations: list[tuple[int, float]] = []
        self._overlap_prefixes: dict[int, float] = {}
        self._seq = 0
        self._accepted_count = 0
        # Sequence gate for invocation order only.  Workers wait until the
        # previous chunk has *started* (not finished), so transcriber fakes and
        # adapters that assign request-local state see deterministic order
        # while the actual network/model work still overlaps.
        self._started_seq = 0
        self._next_emit_seq = 1
        self._failed = 0
        # Sticky for the lifetime of a session.  ``collect()`` may consume the
        # empty terminal marker for a failed chunk and leave only later text;
        # callers still need to know that the assembled text is incomplete.
        self._had_failures = False
        self._last_emitted_text = ""
        self._session_active = False
        self._deadline: float | None = None
        # The model selection is captured at key-down by VoiceFlowApp.  Chunk
        # workers must not reread the Providers setting after the user has
        # changed it for the next dictation.
        self._model_ref: str | None = None

        # Session epoch: worker results carry the epoch they were produced
        # under, so late results from a previous session can never leak into a
        # current transcript after cancel/restart.
        self._epoch = 0

    # -- session lifecycle --

    def start_session(
        self,
        deadline: float | None = None,
        model_ref: str | None = None,
    ) -> None:
        """Start a fresh ordered session and ensure the bounded pool is alive."""
        with self._condition:
            self._completed.clear()
            self._results.clear()
            self._pending.clear()
            self._durations.clear()
            self._overlap_prefixes.clear()
            self._seq = 0
            self._accepted_count = 0
            self._started_seq = 0
            self._next_emit_seq = 1
            self._failed = 0
            self._had_failures = False
            self._last_emitted_text = ""
            self._epoch += 1
            self._deadline = deadline
            self._model_ref = model_ref or None
            self._session_active = True
            self._condition.notify_all()

        # Chunks queued by a cancelled previous session would otherwise be
        # transcribed here and pollute this one (their epoch no longer matches,
        # but the CPU/network work would still be wasted).
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        with self._worker_lock:
            self._workers = [worker for worker in self._workers if worker.is_alive()]
            while len(self._workers) < self._worker_count:
                worker = threading.Thread(
                    target=self._work_loop,
                    name=f"vf-stream-stt-{len(self._workers) + 1}",
                    daemon=True,
                )
                self._workers.append(worker)
                worker.start()
            self._worker = self._workers[0] if self._workers else None

    def set_deadline(self, deadline: float | None) -> None:
        """Set the absolute monotonic deadline for current-session work."""
        with self._condition:
            self._deadline = deadline
            self._condition.notify_all()

    def end_session(self, deadline: float | None = None) -> None:
        """Stop accepting callback chunks, optionally setting release deadline."""
        with self._condition:
            self._session_active = False
            if deadline is not None:
                self._deadline = deadline
            self._condition.notify_all()

    # -- chunk intake --

    def submit_native(
        self,
        chunk: np.ndarray,
        native_sr: int,
        force: bool = False,
        deadline: float | None = None,
        overlap_prefix_seconds: float = 0.0,
    ) -> None:
        """Queue a native-rate chunk captured by the audio callback thread.

        ``force=True`` bypasses the active-session check — used for the final
        tail chunk harvested at dictation finish.  A deadline supplied on a
        tail takes precedence for the current session.
        """
        if chunk is None or chunk.size == 0:
            return
        with self._condition:
            if not self._session_active and not force:
                return
            if deadline is not None:
                self._deadline = deadline
            self._seq += 1
            self._accepted_count += 1
            seq = self._seq
            epoch = self._epoch
            duration = chunk.shape[0] / max(1, int(native_sr))
            self._pending[seq] = duration
            self._durations.append((seq, duration))
            self._overlap_prefixes[seq] = max(0.0, float(overlap_prefix_seconds or 0.0))
        try:
            self._queue.put_nowait((seq, epoch, (chunk, native_sr)))
        except Exception:
            # Keep the sequence terminally accounted for if the queue ever
            # rejects an item; otherwise a gap would hold every later result.
            with self._condition:
                self._pending.pop(seq, None)
                self._durations = [d for d in self._durations if d[0] != seq]
                self._overlap_prefixes.pop(seq, None)
                if epoch == self._epoch:
                    self._completed[seq] = ""
                    self._failed += 1
                    self._had_failures = True
                    if seq == self._started_seq + 1:
                        self._started_seq = seq
                    self._condition.notify_all()

    def pending_count(self) -> int:
        """Chunks accepted but not yet terminal (queued or running)."""
        with self._lock:
            return len(self._pending)

    def accepted_count(self) -> int:
        """Chunks accepted during this session, including completed chunks."""
        with self._lock:
            return self._accepted_count

    def pending_secs(self) -> float:
        """Audio seconds still awaiting transcription (backlog size probe)."""
        with self._lock:
            return float(sum(self._pending.values()))

    def had_failures(self) -> bool:
        """Whether any accepted chunk failed during the current session.

        This remains true after collection drains the failed marker, allowing
        the pipeline to reject a seemingly complete later-chunk transcript
        and use its whole-buffer fallback instead.
        """
        with self._lock:
            return bool(self._had_failures)

    # -- collection --

    @staticmethod
    def _remove_verified_overlap(previous: str, current: str) -> str | None:
        """Remove a conservative word overlap at an explicitly marked seam.

        A two-word match is the smallest repeat that is strong enough to avoid
        deleting a user's ordinary repeated phrase.  This function is called
        only for audio chunks whose overlap was explicitly created by the
        recorder's forced-boundary mechanism.
        """
        previous_words = [match.group(0).casefold() for match in _WORD_RE.finditer(previous)]
        current_matches = list(_WORD_RE.finditer(current))
        current_words = [match.group(0).casefold() for match in current_matches]
        maximum = min(len(previous_words), len(current_words))
        for size in range(maximum, 1, -1):
            if previous_words[-size:] == current_words[:size]:
                return current[current_matches[size - 1].end():].lstrip()
        return None

    def _drain_ready_locked(self) -> list[str]:
        """Consume the contiguous terminal prefix in input sequence order."""
        parts: list[str] = []
        while self._next_emit_seq <= self._seq and self._next_emit_seq in self._completed:
            seq = self._next_emit_seq
            text = self._completed.pop(seq)
            overlap_prefix_seconds = self._overlap_prefixes.pop(seq, 0.0)
            if text:
                source_text = text
                if overlap_prefix_seconds > 0.0:
                    deduplicated = self._remove_verified_overlap(self._last_emitted_text, text)
                    if deduplicated is None:
                        # The seam exists in audio but could not be proven in
                        # text.  Keep its text for diagnostics, but reject the
                        # assembled stream so the lossless whole recording is
                        # transcribed once instead of risking word loss/duplication.
                        self._had_failures = True
                    else:
                        text = deduplicated
                parts.append(text)
                # Keep the original chunk transcript for the next seam.  Its
                # audio, rather than the already-joined display text, is what
                # physically overlaps the following forced chunk.
                self._last_emitted_text = source_text
            self._results = [item for item in self._results if item[0] != seq]
            self._next_emit_seq += 1

        # Once every accepted chunk has been emitted (success or failure), the
        # next submit starts cleanly without carrying old sequence numbers.
        if not self._pending and not self._completed:
            self._seq = 0
            self._started_seq = 0
            self._next_emit_seq = 1
            self._failed = 0
            self._durations.clear()
            self._overlap_prefixes.clear()
        return parts

    def collect(
        self,
        timeout: float = 3.0,
        deadline: float | None = None,
    ) -> str:
        """Wait up to *timeout* and return newly ready text in input order.

        The explicit deadline and the session deadline are absolute monotonic
        timestamps.  Both clamp the wait; a ready ordered prefix is still
        returned even when the deadline has just elapsed.  Results that finish
        out of order remain buffered until their predecessors become terminal.
        """
        timeout_deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            session_deadline = self._deadline
        wait_deadline = timeout_deadline
        if session_deadline is not None:
            wait_deadline = min(wait_deadline, session_deadline)
        if deadline is not None:
            wait_deadline = min(wait_deadline, deadline)

        collected: list[str] = []
        while True:
            with self._condition:
                parts = self._drain_ready_locked()
                if parts:
                    # Preserve the historical collect() contract: when a
                    # caller asks for a batch, wait for all currently accepted
                    # chunks (or the timeout) so ordinary fast chunks arrive
                    # in one string.  The loop still drains only a contiguous
                    # prefix, so an out-of-order result cannot escape early.
                    collected.extend(parts)
                if not self._pending:
                    # No accepted work remains.  This also handles an empty
                    # session and terminal failures whose empty markers were
                    # consumed above.
                    return " ".join(collected).strip()
                remaining = wait_deadline - time.monotonic()
                if remaining <= 0:
                    return " ".join(collected).strip()
                self._condition.wait(timeout=remaining)

    def discard(self) -> None:
        """Throw away everything queued and collected (session cancelled)."""
        with self._condition:
            self._session_active = False
            self._completed.clear()
            self._results.clear()
            self._pending.clear()
            self._durations.clear()
            self._overlap_prefixes.clear()
            self._seq = 0
            self._accepted_count = 0
            self._next_emit_seq = 1
            self._failed = 0
            self._started_seq = 0
            self._had_failures = False
            self._last_emitted_text = ""
            self._deadline = None
            self._model_ref = None
            self._epoch += 1
            self._condition.notify_all()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    # -- worker --

    def _call_transcriber(
        self,
        audio16: np.ndarray,
        deadline: float | None,
        model_ref: str | None,
    ) -> str:
        kwargs: dict[str, object] = {}
        if self._accepts_is_chunk:
            kwargs["is_chunk"] = True
        if self._accepts_deadline and deadline is not None:
            kwargs["deadline"] = deadline
        if self._accepts_model_ref and model_ref:
            kwargs["model_ref"] = model_ref
        return str(self._transcriber.transcribe(audio16, **kwargs) or "").strip()

    def _work_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            seq, epoch, (chunk, native_sr) = item
            text = ""
            chunk_exception = False
            try:
                # Check before doing resampling/import work. A cancelled
                # session should not spend CPU on stale callback chunks. Gate
                # only invocation order; once a sequence starts, later workers
                # proceed immediately and perform the expensive call in
                # parallel.
                with self._condition:
                    if epoch != self._epoch:
                        continue
                    while epoch == self._epoch and seq != self._started_seq + 1:
                        self._condition.wait(timeout=0.05)
                    if epoch != self._epoch:
                        continue
                    self._started_seq = seq
                    deadline = self._deadline
                    model_ref = self._model_ref
                    self._condition.notify_all()
                audio16 = _chunk_to_16k(chunk, native_sr)
                if audio16.size:
                    text = self._call_transcriber(audio16, deadline, model_ref)
            except Exception as exc:
                chunk_exception = True
                log.warning("[STREAM STT] Chunk %d transcription failed: %s", seq, exc)

            with self._condition:
                if epoch != self._epoch:
                    # Result from a superseded session — drop it.  Its pending
                    # entry was already cleared by start_session/discard.
                    continue
                self._pending.pop(seq, None)
                self._durations = [d for d in self._durations if d[0] != seq]
                self._completed[seq] = text
                if text:
                    self._results.append((seq, text))
                else:
                    # An empty result is NOT a failure when the chunk is
                    # inaudible or low-level room noise: the ASR engine legitimately returns "" for
                    # non-speech. Treating that as a failure poisons the
                    # whole stream on every user trailing-off tail chunk and
                    # forces a full whole-buffer re-decode on the main thread.
                    aud = locals().get("audio16")
                    inaudible = False
                    if aud is not None:
                        try:
                            import numpy as _np  # cheap local re-check
                            peak = float(_np.max(_np.abs(aud))) if aud.size > 0 else 0.0
                            rms = float(_np.sqrt(_np.mean(aud**2))) if aud.size > 0 else 0.0
                            if rms < 0.035 or peak < 0.08:
                                inaudible = True
                        except Exception:
                            inaudible = False
                    if chunk_exception or not inaudible:
                        self._failed += 1
                        self._had_failures = True
                self._condition.notify_all()
