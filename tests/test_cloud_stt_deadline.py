"""Deterministic deadline contracts for cloud STT transport."""

from __future__ import annotations

import json
import urllib.request

import pytest
import requests

from voice_flow import stt_engines


def test_session_disables_hidden_urllib3_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """The explicit _send reconnect loop is the only retry owner for POSTs."""
    previous = stt_engines._stt_session
    monkeypatch.setattr(stt_engines, "_stt_session", None)
    session = stt_engines._get_stt_session()
    assert session.adapters["https://"].max_retries.total == 0
    monkeypatch.setattr(stt_engines, "_stt_session", previous)


def test_send_refreshes_deadline_before_urllib_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    seen: list[float] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"ok"

    def fail_session():
        clock[0] += 0.4
        raise RuntimeError("session setup failed")

    def fallback(_request, *, timeout):
        seen.append(timeout)
        return Response()

    monkeypatch.setattr(stt_engines.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(stt_engines, "_get_stt_session", fail_session)
    monkeypatch.setattr(stt_engines.urllib.request, "urlopen", fallback)
    # Keep the production branch active even though its fallback is mocked.
    monkeypatch.setattr(stt_engines, "_ORIGINAL_URLOPEN", fallback)

    request = urllib.request.Request("https://example.test/stt", data=b"audio", method="POST")
    assert stt_engines._send(request, timeout=30.0, deadline=101.0) == b"ok"
    assert seen == [pytest.approx(0.6)]


@pytest.mark.parametrize("adapter_name", ["_assemblyai", "_speechmatics"])
def test_batch_polling_uses_early_backoff_and_poll_deadline(monkeypatch: pytest.MonkeyPatch, adapter_name: str) -> None:
    clock = [200.0]
    sleeps: list[float] = []
    deadlines: list[float | None] = []
    adapter = getattr(stt_engines, adapter_name)

    if adapter_name == "_assemblyai":
        responses = [
            {"upload_url": "https://upload.test/audio"},
            {"id": "job-1"},
            {"status": "processing"},
            {"status": "completed", "text": "complete transcript"},
        ]
    else:
        responses = [
            {"id": "job-1"},
            {"job": {"status": "running"}},
            {"job": {"status": "done"}},
            b"complete transcript",
        ]

    def send(_request, timeout=120, deadline=None):
        deadlines.append(deadline)
        value = responses.pop(0)
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(stt_engines.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(stt_engines.time, "sleep", sleep)
    monkeypatch.setattr(stt_engines, "_send", send)

    assert adapter(b"audio", "key", "model", poll_seconds=30, deadline=230.0) == "complete transcript"
    assert sleeps == [0.25]
    # Setup requests retain the caller deadline; every status/text request is
    # bounded by the stricter poll deadline.
    assert deadlines[-2:] == [230.0, 230.0]

