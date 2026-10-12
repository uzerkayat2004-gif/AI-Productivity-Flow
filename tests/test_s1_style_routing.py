from __future__ import annotations

from types import SimpleNamespace

import pytest

from voice_flow import main, s1_engine
from voice_flow.polisher import TextPolisher
from voice_flow.storage import storage


@pytest.fixture
def polisher(monkeypatch):
    storage.save_setting("polishing_enabled", True)
    engine = TextPolisher()
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda ref: str(ref).startswith("local/s1"))
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(engine, "_run_bridge_with_timeout", lambda callback, timeout, deadline=None: callback(timeout))
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *a, **k: pytest.fail("selected S1 must not use cloud pool"))
    return engine


def test_selected_s1_receives_raw_text_and_effective_email_metadata(polisher, monkeypatch):
    effective = SimpleNamespace(
        instruction="Write as a concise, professional email.",
        style_id="formal",
        category="email",
        format="email",
        task="rewrite",
    )
    observed = {}

    def run(text, instruction, **kwargs):
        observed.update(text=text, instruction=instruction, **kwargs)
        return "Hello team,\n\nI can attend tomorrow.\n\nThanks,\nAlex"

    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)
    monkeypatch.setattr(s1_engine, "polish_with_s1", run)
    outcome = []
    source = "hello team I can attend tomorrow thanks Alex"

    result = polisher.polish(
        source, effective, model_ref="local/s1-mini-q4_k_m", task="rewrite",
        command_format="email", style_id="formal", outcome_callback=outcome.append,
    )

    assert observed["text"] == source
    assert observed["effective"] is effective
    assert observed["effective"].style_id == "formal"
    assert observed["command_format"] == "email"
    assert observed["task"] == "rewrite"
    assert observed["instruction"] == effective.instruction
    assert result.startswith("Hello team")
    assert outcome == ["local_model"]
    assert polisher._last_lfm_bridge_attempted


def test_plain_style_text_is_wrapped_with_style_id_metadata(polisher, monkeypatch):
    observed = {}
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)

    def run(text, instruction, **kwargs):
        observed.update(kwargs)
        return "This is clear."

    monkeypatch.setattr(s1_engine, "polish_with_s1", run)
    result = polisher.polish(
        "this is clear", "Use an excited tone.", model_ref="local/s1-mini-q4_k_m",
        style_id="excited", task="cleanup",
    )
    assert result == "This is clear."
    assert observed["effective"].style_id == "excited"


@pytest.mark.parametrize(
    "candidate",
    [
        "The release is ready.",
        "Hi Alex,\n\nThe release is ready.\n\nThanks,\nNaeem",
        "I can attend on Friday.",
    ],
)
def test_s1_normalizer_rejects_content_loss_or_invention(polisher, monkeypatch, candidate):
    source = "Hello Alex the release is ready thanks Naeem"
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *a, **k: candidate)
    outcomes = []
    result = polisher.polish(
        source, SimpleNamespace(instruction="professional email", style_id="email_formal", category="email", format="email", task="rewrite"),
        model_ref="local/s1-mini-q4_k_m", task="rewrite", command_format="email",
        outcome_callback=outcomes.append,
    )
    assert result != candidate
    assert outcomes == ["command_unfulfilled"]


@pytest.mark.parametrize("task,command_format", [("summarize", None), ("prompt", "prompt")])
def test_unsupported_s1_task_does_not_call_inference_or_cloud(polisher, monkeypatch, task, command_format):
    calls = []
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: False)
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *a, **k: calls.append((a, k)))
    outcomes = []
    result = polisher.polish(
        "please create an outline", "Create a prompt.", model_ref="local/s1-mini-q4_k_m",
        task=task, command_format=command_format, outcome_callback=outcomes.append,
    )
    assert result
    assert calls == []
    assert outcomes == ["command_unfulfilled"]


def test_selected_s1_never_uses_cloud_pool_after_one_failed_local_attempt(polisher, monkeypatch):
    calls = []
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *a, **k: calls.append(1) or None)
    outcomes = []
    result = polisher.polish(
        "Please send the report.", model_ref="local/s1-mini-q4_k_m",
        task="cleanup", outcome_callback=outcomes.append,
    )
    assert result
    assert calls == [1]
    assert outcomes == ["provider_failure"]


def test_polishing_off_skips_all_s1_work(polisher, monkeypatch):
    storage.save_setting("polishing_enabled", False)
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: pytest.fail("must not inspect/load S1"))
    outcomes = []
    result = polisher.polish(
        "hello there", "be excited", model_ref="local/s1-mini-q4_k_m",
        task="rewrite", outcome_callback=outcomes.append,
    )
    assert result == "Hello there."
    assert outcomes == ["disabled"]
    assert not polisher._last_lfm_bridge_attempted


def test_warm_dispatch_is_gated_and_uses_resource_lease(monkeypatch):
    calls = []
    class Lease:
        def release_after_idle(self, seconds):
            calls.append(("release", seconds))

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda ref: ref == "local/s1")
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "warm_s1_model", lambda **kwargs: calls.append(("warm", kwargs)))
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: calls.append(("lease", kind)) or Lease())
    monkeypatch.setattr(main.threading, "Thread", ImmediateThread)

    main._warm_voice_gemini_transport("local/s1")

    assert calls == [("lease", "polish"), ("warm", {"timeout_seconds": 5.0}), ("release", s1_engine.S1_WARM_IDLE_SECONDS)]


def test_warm_dispatch_skips_when_polishing_is_off(monkeypatch):
    monkeypatch.setattr(main, "_polishing_enabled", lambda: False)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda ref: pytest.fail("must not inspect S1 when off"))
    main._warm_voice_gemini_transport("local/s1")


def test_s1_warm_lease_covers_active_capture_and_releases_when_session_ends(monkeypatch):
    calls = []
    class Lease:
        def release_after_idle(self, seconds):
            calls.append(("release", seconds))

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    session = object()
    owner = SimpleNamespace(session=session, state=SimpleNamespace(value="recording"))
    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda ref: ref == "local/s1")
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "warm_s1_model", lambda **kwargs: calls.append(("warm", kwargs)))
    monkeypatch.setattr("voice_flow.local_model_resources.acquire_model_use", lambda kind: calls.append(("lease", kind)) or Lease())
    monkeypatch.setattr(main.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(main.time, "sleep", lambda _seconds: setattr(owner, "state", SimpleNamespace(value="idle")))

    main._warm_voice_gemini_transport("local/s1", session, owner)

    assert calls == [
        ("lease", "polish"),
        ("warm", {"timeout_seconds": 5.0}),
        ("release", s1_engine.S1_WARM_IDLE_SECONDS),
    ]
