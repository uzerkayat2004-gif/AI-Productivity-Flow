import json
import queue
import threading
import time

import numpy as np
import pytest

from voice_flow.flux_stream import (
    FluxStreamTranscriber,
    NovaStreamTranscriber,
    _CAPTURE_QUEUE_FRAMES,
    _stream_failure_reason,
)


class Socket:
    def __init__(self, replies):
        self.replies = replies
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = threading.Event()

    def send(self, message):
        self.sent.append(message)
        if isinstance(message, str) and json.loads(message)["type"] == "ForceEndTurn":
            for reply in self.replies:
                self.incoming.put(json.dumps(reply))

    def recv(self, timeout):
        try:
            return self.incoming.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError()

    def close(self):
        self.closed.set()


class SlowCloseSocket(Socket):
    """Simulate a transport whose close handshake outlives a valid result."""

    def close(self):
        time.sleep(0.35)
        super().close()


def final(text, end=0.2, index=0, trigger="manual"):
    return dict(type="TurnInfo", event="EndOfTurn", turn_index=index,
                transcript=text, audio_window_end=end, trigger=trigger)


def run_stream(monkeypatch, replies, socket_type=Socket):
    socket = socket_type(replies)
    monkeypatch.setattr("websockets.sync.client.connect", lambda *args, **kwargs: socket)
    monkeypatch.setattr("voice_flow.stt_engines._key_for", lambda provider: "synthetic-key")
    stream = FluxStreamTranscriber()
    stream.start_session(model_ref="deepgram/flux-general-en")
    stream.submit_frame(np.full((3200, 1), 0.1, dtype=np.float32), 16000)
    stream.end_session(deadline=time.monotonic() + 0.6)
    return stream, socket


def test_live_stream_sends_pcm_once_and_waits_for_complete_forced_turn(monkeypatch):
    stream, socket = run_stream(monkeypatch, [
        final("prefix", 0.05, trigger="model"), final("the complete last sentence")])
    assert stream.collect(timeout=1) == "the complete last sentence"
    assert stream.pending_count() == 0 and not stream.had_failures()
    assert sum(len(item) for item in socket.sent if isinstance(item, bytes)) == 6400
    assert max(np.frombuffer(b"".join(item for item in socket.sent if isinstance(item, bytes)), dtype="<i2")) > 3000
    assert socket.closed.wait(1)


def test_manual_end_of_turn_accepts_the_received_audible_tail(monkeypatch):
    """A manual EndOfTurn is the protocol acknowledgement for ForceEndTurn.

    Flux's audio_window_end can lag the microphone frame it has already
    received.  Requiring it to reach the locally estimated audible tail would
    incorrectly discard the authoritative manual final response.
    """
    stream, socket = run_stream(monkeypatch, [final("complete boundary words", 0.05)])

    assert stream.collect(timeout=1) == "complete boundary words"
    assert sum(len(item) for item in socket.sent if isinstance(item, bytes)) == 6400
    assert any(item == '{"type": "ForceEndTurn"}' for item in socket.sent)
    assert not stream.had_failures()


def test_complete_flux_turn_is_collectable_before_slow_socket_cleanup(monkeypatch):
    stream, socket = run_stream(monkeypatch, [final("ready before close", 0.2)], SlowCloseSocket)
    started = time.monotonic()
    assert stream.collect(timeout=0.2) == "ready before close"
    # A 350ms close handshake must not consume the short release-time lane.
    assert time.monotonic() - started < 0.2
    assert socket.closed.wait(1)


@pytest.mark.parametrize("replies", [
    [final("partial prefix", 0.05, trigger="model")],
    [dict(type="TurnInfo", event="Update", transcript="unfinalized")],
    [dict(type="FatalError", description="connection rejected")],
])
def test_partial_or_failed_stream_never_delivers_text(monkeypatch, replies):
    stream, socket = run_stream(monkeypatch, replies)
    assert stream.collect(timeout=1) == ""
    assert socket.closed.wait(1)
    assert stream.had_failures()


def test_no_active_turn_warning_can_confirm_completed_turns(monkeypatch):
    stream, socket = run_stream(monkeypatch, [
        final("first sentence", 0.1, 0, "model"),
        final("last sentence", 0.2, 1, "model"),
        dict(type="Warning", code="FORCE_END_TURN_NO_ACTIVE_TURN")])
    assert stream.collect(timeout=1) == "first sentence last sentence"
    assert socket.closed.wait(1)


def test_no_active_turn_warning_without_audible_coverage_is_not_a_transcript(monkeypatch):
    stream, socket = run_stream(monkeypatch, [
        final("only a prefix", 0.05, 0, "model"),
        dict(type="Warning", code="FORCE_END_TURN_NO_ACTIVE_TURN")])
    assert stream.collect(timeout=1) == ""
    assert stream.had_failures()
    assert socket.closed.wait(1)


def test_queue_overflow_requests_full_recording_recovery_without_blocking_capture():
    stream = FluxStreamTranscriber()
    frame = np.ones((128, 1), dtype=np.float32)
    for _ in range(_CAPTURE_QUEUE_FRAMES + 44):
        stream.submit_frame(frame, 16000)
    assert stream.had_failures()
    assert stream._queue.qsize() == _CAPTURE_QUEUE_FRAMES


def test_flux_preserves_supported_native_44k1_pcm(monkeypatch):
    socket = Socket([final("native microphone text", 0.2)])
    calls = []
    monkeypatch.setattr("websockets.sync.client.connect", lambda *args, **kwargs: (calls.append((args, kwargs)) or socket))
    monkeypatch.setattr("voice_flow.stt_engines._key_for", lambda provider: "synthetic-key")
    stream = FluxStreamTranscriber()
    stream.start_session(model_ref="deepgram/flux-general-en")
    stream.submit_frame(np.full((8820, 2), 0.1, dtype=np.float32), 44100)
    stream.end_session(deadline=time.monotonic() + 0.6)

    assert stream.collect(timeout=1) == "native microphone text"
    assert "sample_rate=44100" in calls[0][0][0]
    assert sum(len(item) for item in socket.sent if isinstance(item, bytes)) == 8820 * 2


def test_stream_failure_diagnostic_redacts_authorization_values():
    detail = _stream_failure_reason(
        RuntimeError("Authorization: Token test-secret api_key=also-secret Authorization:Bearer bearer-secret 'Authorization': 'Basic basic-secret'")
    )
    assert all(secret not in detail for secret in ("test-secret", "also-secret", "bearer-secret", "basic-secret"))
    assert "<redacted>" in detail


def test_cancelled_stream_cannot_return_late_text(monkeypatch):
    stream, socket = run_stream(monkeypatch, [])
    stream.discard()
    socket.incoming.put(json.dumps(final("late text")))
    assert stream.collect(timeout=1) == ""
    assert stream.had_failures()


class NovaSocket(Socket):
    def send(self, message):
        self.sent.append(message)
        if isinstance(message, str) and json.loads(message).get("type") == "CloseStream":
            for reply in self.replies:
                self.incoming.put(json.dumps(reply))


class SlowCloseNovaSocket(NovaSocket):
    def close(self):
        time.sleep(0.35)
        super().close()


def nova_final(text, start=0.0, duration=0.1):
    return {
        "type": "Results", "is_final": True, "start": start, "duration": duration,
        "channel": {"alternatives": [{"transcript": text}]},
    }


def run_nova(monkeypatch, replies, *, model="deepgram/nova-3-general", socket_type=NovaSocket):
    socket = socket_type(replies)
    calls = []
    monkeypatch.setattr("websockets.sync.client.connect", lambda *args, **kwargs: (calls.append((args, kwargs)) or socket))
    monkeypatch.setattr("voice_flow.stt_engines._key_for", lambda provider: "synthetic-key")
    stream = NovaStreamTranscriber(("Voice Flow",))
    stream.start_session(model_ref=model)
    stream.submit_frame(np.full((4800, 1), 0.1, dtype=np.float32), 48000)
    stream.end_session(deadline=time.monotonic() + 0.6)
    return stream, socket, calls


def test_nova_live_keeps_48k_rate_and_selected_model(monkeypatch):
    stream, socket, calls = run_nova(monkeypatch, [nova_final("native rate text"), {"type": "Metadata"}])
    assert stream.collect(timeout=1) == "native rate text"
    url = calls[0][0][0]
    assert "model=nova-3-general" in url
    assert "encoding=linear16" in url and "sample_rate=48000" in url
    assert "interim_results=false" in url and "endpointing=false" in url
    assert sum(len(item) for item in socket.sent if isinstance(item, bytes)) == 9600
    assert socket.closed.wait(1)


def test_complete_nova_turn_is_collectable_before_slow_socket_cleanup(monkeypatch):
    stream, socket, _ = run_nova(
        monkeypatch,
        [nova_final("ready before close"), {"type": "Metadata"}],
        socket_type=SlowCloseNovaSocket,
    )
    started = time.monotonic()
    assert stream.collect(timeout=0.2) == "ready before close"
    assert time.monotonic() - started < 0.2
    assert socket.closed.wait(1)


@pytest.mark.parametrize("replies", [
    [nova_final("missing server completion")],
    [nova_final("missing tail", duration=0.02), {"type": "Metadata"}],
])
def test_nova_never_accepts_before_completion_and_audible_tail(monkeypatch, replies):
    stream, socket, _ = run_nova(monkeypatch, replies)
    assert stream.collect(timeout=1) == ""
    assert socket.closed.wait(1)
    assert stream.had_failures()
