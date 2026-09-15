"""One bounded Flux connection per recording, fed directly by capture frames.

The microphone only copies into a bounded queue. Network work runs outside its
callback; incomplete turns, disconnects and queue overflow fail closed so the
coordinator can recover from its untouched full recording.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from urllib.parse import urlencode

import numpy as np

from voice_flow import stt_engines

log = logging.getLogger(__name__)
_CONNECTION_SLOTS = threading.BoundedSemaphore(2)
_CAPTURE_QUEUE_FRAMES = 512
# Flux's ``audio_window_end`` is advisory and can lag the microphone frame it
# has already received, so a manual EndOfTurn must not be rejected for small
# clock differences. A materially uncovered tail, however, means the final
# words were not transcribed and the transcript must not be pasted as if
# complete. The tolerance sits well above the observed advisory lag and well
# below a real missing word.
_FLUX_TAIL_TOLERANCE_SECONDS = 0.5
_AUTH_VALUE_RE = re.compile(
    r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)(?:(?:token|bearer|basic)\s+)?[^,;\s'\"\]\}]+"
)


def _stream_failure_reason(exc: BaseException) -> str:
    """Return a short useful diagnostic without leaking an authorization header."""
    detail = str(exc).replace("\n", " ").strip()
    # Some websocket libraries include the request headers in connection
    # exceptions.  Diagnostics must be useful without ever writing a key.
    detail = _AUTH_VALUE_RE.sub(r"\1<redacted>", detail)
    detail = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1<redacted>", detail)
    if len(detail) > 180:
        detail = detail[:177] + "..."
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


class NovaStreamTranscriber:
    """One bounded Deepgram v1 live-listen session for a Nova-3 recording.

    Deepgram's live API consumes raw linear16 at the recorder's native rate.
    We deliberately do not resample or submit silence-delimited chunks here:
    one session owns the complete recording and a failed/incomplete session
    returns no text, leaving the lossless whole-buffer recovery path in charge.
    """

    live_frames = True

    def __init__(self, vocabulary=()):
        self._vocabulary = tuple(vocabulary)
        # A native 48 kHz device emits ~47 callbacks per second.  A bounded
        # 512-frame queue gives the initial TLS/WebSocket handshake roughly
        # eleven seconds before capture has to fail closed, without blocking
        # the audio callback or retaining an unbounded recording.
        self._queue = queue.Queue(maxsize=_CAPTURE_QUEUE_FRAMES)
        self._finish = threading.Event()
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._failed = False
        self._text = ""
        self._accepted = 0
        self._deadline = None
        self._model = ""

    def start_session(self, model_ref=None, deadline=None):
        provider, separator, model = str(model_ref or "").partition("/")
        if provider.casefold() != "deepgram" or not separator or not model.casefold().startswith("nova-3"):
            raise ValueError("A supported Deepgram Nova-3 model is required")
        # Preserve the selected Deepgram model id (for example nova-3-general)
        # rather than silently substituting a different accuracy/locale tier.
        self._model = model
        self._deadline = deadline
        threading.Thread(target=self._run, name="vf-nova-live", daemon=True).start()

    def submit_frame(self, frame, native_sr):
        if self._finish.is_set() or self._cancel.is_set() or self._done.is_set():
            return
        try:
            self._queue.put_nowait((frame.copy(), int(native_sr)))
            self._accepted += 1
        except queue.Full:
            self._failed = True
            self._cancel.set()

    def submit_native(self, *args, **kwargs):
        # Capture frames already include every closed chunk and final tail.
        pass

    def end_session(self, deadline=None):
        if deadline is not None:
            self._deadline = deadline
        self._finish.set()

    def accepted_count(self):
        return self._accepted

    def pending_count(self):
        return int(not self._done.is_set())

    def had_failures(self):
        return self._failed or self._cancel.is_set()

    def collect(self, timeout=3.0, deadline=None):
        remaining = max(0.0, timeout)
        for limit in (deadline, self._deadline):
            if limit is not None:
                remaining = min(remaining, max(0.0, limit - time.monotonic()))
        self._done.wait(remaining)
        return self._text if self._done.is_set() and not self.had_failures() else ""

    def discard(self):
        self._cancel.set()
        self._finish.set()

    def _expired(self):
        return self._deadline is not None and time.monotonic() >= self._deadline

    @staticmethod
    def _pcm(frame):
        mono = np.mean(frame, axis=1) if frame.ndim > 1 else frame
        mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)
        return mono, (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def _run(self):
        websocket = None
        sender = None
        slot = _CONNECTION_SLOTS.acquire(blocking=False)
        try:
            if not slot:
                raise RuntimeError("Previous live connections are still closing")
            first = None
            while first is None and not self._cancel.is_set():
                try:
                    first = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._finish.is_set() or self._expired():
                        raise RuntimeError("No live audio available")
            if first is None:
                return
            from websockets.sync.client import connect

            rate = first[1]
            if rate <= 0:
                raise RuntimeError("Invalid microphone sample rate")
            query = [("model", self._model), ("encoding", "linear16"),
                     ("sample_rate", str(rate)), ("interim_results", "false"),
                     ("endpointing", "false"), ("smart_format", "true")]
            query.extend(("keyterm", term) for term in dict.fromkeys(self._vocabulary) if term)
            websocket = connect("wss://api.deepgram.com/v1/listen?" + urlencode(query),
                                additional_headers={"Authorization": "Token " + stt_engines._key_for("deepgram")},
                                open_timeout=5.0, close_timeout=0.25, max_queue=32)
            sent_close = threading.Event()
            state = {"required_end": 0.0, "error": False}

            def send_audio():
                samples = 0
                item = first
                try:
                    while not self._cancel.is_set() and not self._expired():
                        if item is not None:
                            frame, sample_rate = item
                            if sample_rate != rate:
                                raise RuntimeError("Microphone rate changed mid-recording")
                            mono, pcm = self._pcm(frame)
                            audible = np.flatnonzero(np.abs(mono) > 0.002)
                            if audible.size:
                                state["required_end"] = (samples + int(audible[-1]) + 1) / rate
                            samples += len(mono)
                            if pcm:
                                websocket.send(pcm)
                        try:
                            item = self._queue.get(timeout=0.02)
                        except queue.Empty:
                            item = None
                            if self._finish.is_set():
                                # CloseStream asks v1/listen to flush its final Results and
                                # terminal Metadata response.  Neither interim nor merely
                                # is_final output is accepted before that completion marker.
                                sent_close.set()
                                websocket.send(json.dumps({"type": "CloseStream"}))
                                return
                except Exception:
                    state["error"] = True
                    self._cancel.set()

            sender = threading.Thread(target=send_audio, name="vf-nova-send", daemon=True)
            sender.start()
            final_parts = []
            covered_end = 0.0
            completed = False
            while not self._cancel.is_set() and not self._expired():
                try:
                    message = websocket.recv(timeout=0.1)
                except TimeoutError:
                    continue
                if isinstance(message, bytes):
                    continue
                payload = json.loads(message)
                kind = payload.get("type")
                if kind in {"Error", "FatalError"}:
                    raise RuntimeError("Nova live stream rejected")
                if kind == "Results" and payload.get("is_final"):
                    alternatives = ((payload.get("channel") or {}).get("alternatives") or [{}])
                    text = str((alternatives[0] if isinstance(alternatives[0], dict) else {}).get("transcript") or "").strip()
                    if text:
                        final_parts.append(text)
                    start = float(payload.get("start") or 0.0)
                    duration = float(payload.get("duration") or 0.0)
                    covered_end = max(covered_end, start + duration)
                elif kind == "Metadata":
                    completed = True
                if sent_close.is_set() and completed:
                    if covered_end + 0.02 < state["required_end"]:
                        raise RuntimeError("Nova final response did not cover audible tail")
                    text = " ".join(final_parts).strip()
                    if not text or state["error"]:
                        raise RuntimeError("Nova returned no complete transcript")
                    self._text = text
                    # The transcript is complete and has passed tail coverage.
                    # Do not make the release path wait for a bounded socket
                    # close or sender join below; the connection slot remains
                    # owned until that cleanup finishes in ``finally``.
                    self._done.set()
                    return
            raise RuntimeError("Live transcription cancelled or timed out")
        except Exception as exc:
            self._failed = True
            log.warning("[STREAM STT] Nova live session unavailable (%s); full recording retained", _stream_failure_reason(exc))
        finally:
            if websocket is not None:
                try:
                    websocket.close()
                except Exception:
                    pass
            if sender is not None:
                sender.join(timeout=0.5)
            self._done.set()
            if slot:
                _CONNECTION_SLOTS.release()


class FluxStreamTranscriber:
    live_frames = True

    def __init__(self, vocabulary=()):
        self._vocabulary = tuple(vocabulary)
        self._queue = queue.Queue(maxsize=_CAPTURE_QUEUE_FRAMES)
        self._finish = threading.Event()
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._failed = False
        self._text = ""
        self._accepted = 0
        self._deadline = None

    def start_session(self, model_ref=None, deadline=None):
        self._model = str(model_ref or "").partition("/")[2]
        if self._model not in {"flux-general-en", "flux-general-multi"}:
            raise ValueError("A supported Flux model is required")
        self._deadline = deadline
        threading.Thread(target=self._run, name="vf-flux-live", daemon=True).start()

    def submit_frame(self, frame, native_sr):
        if self._finish.is_set() or self._cancel.is_set() or self._done.is_set():
            return
        try:
            self._queue.put_nowait((frame.copy(), int(native_sr)))
            self._accepted += 1
        except queue.Full:
            self._failed = True
            self._cancel.set()

    def submit_native(self, *args, **kwargs):
        # Closed chunks and the tail already arrived through submit_frame.
        pass

    def end_session(self, deadline=None):
        if deadline is not None:
            self._deadline = deadline
        self._finish.set()

    def accepted_count(self):
        return self._accepted

    def pending_count(self):
        return int(not self._done.is_set())

    def had_failures(self):
        return self._failed or self._cancel.is_set()

    def collect(self, timeout=3.0, deadline=None):
        remaining = max(0.0, timeout)
        for limit in (deadline, self._deadline):
            if limit is not None:
                remaining = min(remaining, max(0.0, limit - time.monotonic()))
        self._done.wait(remaining)
        return self._text if self._done.is_set() and not self.had_failures() else ""

    def discard(self):
        self._cancel.set()
        self._finish.set()

    def _expired(self):
        return self._deadline is not None and time.monotonic() >= self._deadline

    def _run(self):
        websocket = None
        sender = None
        slot = _CONNECTION_SLOTS.acquire(blocking=False)
        try:
            if not slot:
                raise RuntimeError("Previous Flux connections are still closing")
            first = None
            while first is None and not self._cancel.is_set():
                try:
                    first = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._finish.is_set() or self._expired():
                        raise RuntimeError("No live audio available")
            if first is None:
                return
            from websockets.sync.client import connect

            rate = first[1]
            query = [("model", self._model), ("encoding", "linear16"), ("sample_rate", str(rate)),
                     ("eot_threshold", "1.0"), ("eot_timeout_ms", "60000")]
            query.extend(("keyterm", term) for term in dict.fromkeys(self._vocabulary) if term)
            websocket = connect("wss://api.deepgram.com/v2/listen?" + urlencode(query),
                                additional_headers={"Authorization": "Token " + stt_engines._key_for("deepgram")},
                                open_timeout=5.0, close_timeout=0.25, max_queue=32)
            sent_final = threading.Event()
            state = {"required_end": 0.0, "error": False}

            def send_audio():
                samples = 0
                pending = bytearray()
                frame_bytes = max(2, round(rate * 0.08) * 2)
                item = first
                try:
                    while not self._cancel.is_set() and not self._expired():
                        if item is not None:
                            frame, sample_rate = item
                            if sample_rate != rate:
                                raise RuntimeError("Microphone rate changed mid-recording")
                            mono = np.mean(frame, axis=1) if frame.ndim > 1 else frame
                            mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)
                            audible = np.flatnonzero(np.abs(mono) > 0.002)
                            if audible.size:
                                state["required_end"] = (samples + int(audible[-1]) + 1) / rate
                            samples += len(mono)
                            pending.extend((np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes())
                            while len(pending) >= frame_bytes:
                                websocket.send(bytes(pending[:frame_bytes]))
                                del pending[:frame_bytes]
                        try:
                            item = self._queue.get(timeout=0.02)
                        except queue.Empty:
                            item = None
                            if self._finish.is_set():
                                if pending:
                                    websocket.send(bytes(pending))
                                # Set before send: the receive thread can observe
                                # the reply immediately after the socket write.
                                sent_final.set()
                                websocket.send(json.dumps({"type": "ForceEndTurn"}))
                                return
                except Exception:
                    state["error"] = True
                    self._cancel.set()

            sender = threading.Thread(target=send_audio, name="vf-flux-send", daemon=True)
            sender.start()
            turns = {}
            covered_end = 0.0
            while not self._cancel.is_set() and not self._expired():
                try:
                    message = websocket.recv(timeout=0.1)
                except TimeoutError:
                    continue
                if isinstance(message, bytes):
                    continue
                payload = json.loads(message)
                kind = payload.get("type")
                if kind in {"Error", "FatalError"}:
                    raise RuntimeError("Flux rejected the live stream")
                if kind == "TurnInfo" and payload.get("event") == "EndOfTurn":
                    turns[int(payload["turn_index"])] = str(payload.get("transcript") or "").strip()
                    try:
                        covered_end = max(covered_end, float(payload["audio_window_end"]))
                    except (TypeError, ValueError, KeyError):
                        pass
                    if not (sent_final.is_set() and payload.get("trigger") == "manual"):
                        continue
                    # ForceEndTurn is sent only after the sender has flushed
                    # every accepted microphone frame.  Deepgram documents a
                    # manual EndOfTurn as the transcript of all audio received
                    # before that control message, so it is authoritative.
                    # ``audio_window_end`` is advisory and can lag that frame
                    # boundary, so only a materially uncovered audible tail is
                    # treated as an incomplete final transcript.  Accepting
                    # silently dropped the closing words; rejecting on the
                    # advisory lag forced a full-recording replay.
                    if covered_end + _FLUX_TAIL_TOLERANCE_SECONDS < state["required_end"]:
                        continue
                elif kind == "Warning" and payload.get("code") == "FORCE_END_TURN_NO_ACTIVE_TURN":
                    # A warning contains no transcript. It can only release
                    # already-finalized turns after their server windows cover
                    # every audible frame we sent before ForceEndTurn.
                    if not sent_final.is_set() or covered_end + 0.02 < state["required_end"]:
                        raise RuntimeError("Flux had no active turn to finalize")
                else:
                    continue
                text = " ".join(turns[index] for index in sorted(turns) if turns[index])
                if not text or state["error"]:
                    raise RuntimeError("Flux returned no complete transcript")
                self._text = text
                # A valid forced turn is ready for insertion now. Closing
                # a websocket can block briefly on some Windows networks,
                # so publish before bounded cleanup while retaining the
                # concurrency slot until cleanup is actually complete.
                self._done.set()
                return
            raise RuntimeError("Live transcription cancelled or timed out")
        except Exception as exc:
            self._failed = True
            # Keep credentials and provider response bodies out of diagnostics.
            log.warning("[STREAM STT] Flux live session unavailable (%s); full recording retained", _stream_failure_reason(exc))
        finally:
            if websocket is not None:
                try:
                    websocket.close()
                except Exception:
                    pass
            if sender is not None:
                sender.join(timeout=0.5)
            self._done.set()
            if slot:
                _CONNECTION_SLOTS.release()
