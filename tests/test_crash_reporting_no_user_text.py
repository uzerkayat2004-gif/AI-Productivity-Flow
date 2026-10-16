"""End-to-end: real sentry_sdk + capture transport, user text must never reach an event.

Regression for the v1.0.2 audit: the old scrubber leaked dictated text through
stack-frame locals, exception messages and logging breadcrumbs.
"""

from __future__ import annotations

import json
import logging
import threading
from unittest.mock import patch

import pytest

sentry_sdk = pytest.importorskip("sentry_sdk")
from sentry_sdk.transport import Transport  # noqa: E402

from voice_flow import crash_reporting  # noqa: E402

SENTENCE = "Please wire four thousand dollars to Priya before Friday"


class CaptureTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def flush(self, timeout, callback=None):
        return None

    def kill(self):
        return None


def _payloads(transport):
    out = []
    for envelope in transport.envelopes:
        for item in envelope.items:
            out.append(item.payload.get_bytes().decode("utf-8", "replace"))
    return out


@pytest.fixture()
def capture(monkeypatch):
    transport = CaptureTransport()
    real_init = sentry_sdk.init

    def init_with_capture(*args, **kwargs):
        kwargs["dsn"] = "https://public@example.invalid/1"
        kwargs["transport"] = transport
        return real_init(*args, **kwargs)

    monkeypatch.setattr(sentry_sdk, "init", init_with_capture)
    assert crash_reporting.init_crash_reporting(force=True) is True
    yield transport
    crash_reporting.shutdown_crash_reporting()


def _dictate_and_fail(text: str) -> None:
    user_clipboard = f"clipboard: {text}"  # noqa: F841 - local var must not leak
    logging.getLogger("voice_flow.polisher").warning("Local S1 model cleaned: '%s'", text)
    logging.getLogger("voice_flow.polisher").info("Polishing %s", user_clipboard)
    raise ValueError(f"could not polish {text!r}")


def test_user_text_never_reaches_sentry(capture):
    try:
        _dictate_and_fail(SENTENCE)
    except ValueError:
        sentry_sdk.capture_exception()
    logging.getLogger("voice_flow.main").error("Dictation failed for: %s", SENTENCE)
    sentry_sdk.capture_message(f"manual message {SENTENCE}")
    sentry_sdk.flush(timeout=2)

    payloads = _payloads(capture)
    assert payloads, "expected at least the exception event to be captured"
    blob = "\n".join(payloads)
    assert "Priya" not in blob
    assert "four thousand" not in blob
    assert SENTENCE not in blob

    events = [json.loads(p) for p in payloads if p.startswith("{")]
    exc_events = [e for e in events if e.get("exception")]
    assert exc_events, "exception event should still be reported (type + location only)"
    exc = exc_events[0]["exception"]["values"][-1]
    assert exc["type"] == "ValueError"
    assert exc["value"] == "[redacted]"
    for frame in exc["stacktrace"]["frames"]:
        assert "vars" not in frame
    for event in events:
        assert not event.get("breadcrumbs") or not event["breadcrumbs"].get("values")
        assert "server_name" not in event


def test_opt_out_closes_client(capture):
    assert sentry_sdk.get_client().is_active()
    assert crash_reporting.shutdown_crash_reporting() is True
    assert not sentry_sdk.get_client().is_active()
    before = len(capture.envelopes)
    sentry_sdk.capture_message("after opt-out")
    sentry_sdk.flush(timeout=1)
    assert len(capture.envelopes) == before


def test_api_toggle_saves_before_applying(monkeypatch):
    """Toggle order: save the setting first, then init (on) or shut down (off)."""
    from pathlib import Path

    source = Path(crash_reporting.__file__).with_name("gui").joinpath("api_server.py").read_text(encoding="utf-8")
    save_at = source.index("if not storage.save_setting(key, val):")
    toggle_at = source.index('if key == "anonymous_crash_reports":')
    assert save_at < toggle_at
    assert "shutdown_crash_reporting()" in source[toggle_at: toggle_at + 600]
