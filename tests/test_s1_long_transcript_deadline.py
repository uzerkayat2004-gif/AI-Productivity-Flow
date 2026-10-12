from __future__ import annotations

from types import SimpleNamespace

import pytest

from voice_flow import main, polish_latency, s1_engine


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def perf_counter(self):
        return self.now


@pytest.mark.parametrize("word_count", [10, 80, 120])
def test_selected_s1_deadline_allows_transcript_normalization(monkeypatch, word_count):
    """Exercise the app's deadline, finalizer, and selected-S1 polisher path without llama_cpp."""
    clock = FakeClock()
    monkeypatch.setattr(main.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(main.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(polish_latency, "observed_latency", lambda _model_ref: 0.574)
    monkeypatch.setattr(main, "smart_format", lambda text, *_args: text)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda model_ref: model_ref == "local/s1-mini-q4_k_m")
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **_kwargs: True)

    source = "Please review " + " ".join(f"item{index}" for index in range(word_count - 4)) + " with Alice."
    observed_timeouts = []
    expected_runtime = 0.5 + (len(source.split()) / 60.0)

    def fake_s1(text, _instruction="", *, timeout_seconds, **_kwargs):
        observed_timeouts.append(timeout_seconds)
        if timeout_seconds < expected_runtime:
            clock.now += timeout_seconds
            main.polisher._last_attempt_status = "timeout"
            return None
        clock.now += expected_runtime
        main.polisher._last_attempt_status = "ok"
        return text

    monkeypatch.setattr(s1_engine, "polish_with_s1", fake_s1)

    def inline_bounded_bridge(callback, timeout, deadline=None):
        available = min(timeout, (deadline - clock.monotonic()) if deadline is not None else timeout)
        if available < 0.05:
            main.polisher._last_attempt_status = "timeout"
            return None
        result = callback(available)
        return result

    monkeypatch.setattr(main.polisher, "_run_bridge_with_timeout", inline_bounded_bridge)
    deadline = main._polish_deadline(
        clock.monotonic() + 4.0,
        "balanced",
        len(source.split()),
        cloud_stt=False,
        polish_model_ref="local/s1-mini-q4_k_m",
    )
    outcomes = []
    session = SimpleNamespace(
        cleanup_level="cleanup_light",
        style_id="smart_clean",
        cursor_context=None,
        polish_model_ref="local/s1-mini-q4_k_m",
        polish_speed_mode="balanced",
    )

    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        source,
        session,
        deadline=deadline,
        outcome_callback=outcomes.append,
    )

    assert result
    assert observed_timeouts
    assert outcomes == ["local_model"]
    if word_count == 10:
        assert clock.now - 100.0 < 1.0


def test_s1_timeout_records_actual_elapsed_and_mode(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(main.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(main.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(polish_latency, "observed_latency", lambda _model_ref: 0.574)
    monkeypatch.setattr(main, "smart_format", lambda text, *_args: text)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda model_ref: model_ref == "local/s1-mini-q4_k_m")
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **_kwargs: True)
    source = "Please review " + " ".join(f"item{index}" for index in range(76)) + " with Alice."
    reported = []
    monkeypatch.setattr(polish_latency, "record_timeout", lambda model, **kwargs: reported.append((model, kwargs)))

    def fake_s1(_text, _instruction="", *, timeout_seconds, **_kwargs):
        clock.now += timeout_seconds
        main.polisher._last_attempt_status = "timeout"
        return None

    monkeypatch.setattr(s1_engine, "polish_with_s1", fake_s1)
    monkeypatch.setattr(
        main.polisher,
        "_run_bridge_with_timeout",
        lambda callback, timeout, deadline=None: callback(
            min(timeout, deadline - clock.monotonic() if deadline is not None else timeout)
        ),
    )
    session = SimpleNamespace(
        cleanup_level="cleanup_light", style_id="smart_clean", cursor_context=None,
        polish_model_ref="local/s1-mini-q4_k_m", polish_speed_mode="fast",
    )
    deadline = clock.monotonic() + 1.0
    outcomes = []

    object.__new__(main.VoiceFlowApp)._finalize_text(
        source, session, deadline=deadline, outcome_callback=outcomes.append,
    )

    assert outcomes == ["timeout"]
    assert reported and reported[0][0] == s1_engine.S1_MODEL_ID
    assert reported[0][1]["mode"] == "fast"
    assert reported[0][1]["elapsed"] == pytest.approx(0.75)


def test_s1_fidelity_rejection_does_not_train_timeout_profile(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(main.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(main.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(polish_latency, "observed_latency", lambda _model_ref: 0.574)
    monkeypatch.setattr(main, "smart_format", lambda text, *_args: text)
    monkeypatch.setattr(main.storage, "get_setting", lambda key, default=None: True if key == "polishing_enabled" else default)
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda model_ref: model_ref == "local/s1-mini-q4_k_m")
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **_kwargs: True)
    monkeypatch.setattr(polish_latency, "record_timeout", lambda *_args, **_kwargs: pytest.fail("fidelity rejection is not a timeout"))
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *_args, **_kwargs: "It costs 25 dollars.")
    monkeypatch.setattr(main.polisher, "_run_bridge_with_timeout", lambda callback, timeout, deadline=None: callback(timeout))
    session = SimpleNamespace(
        cleanup_level="cleanup_light", style_id="smart_clean", cursor_context=None,
        polish_model_ref="local/s1-mini-q4_k_m", polish_speed_mode="balanced",
    )
    outcomes = []

    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        "It costs twenty dollars.", session,
        deadline=main._polish_deadline(clock.monotonic() + 4, "balanced", 4, cloud_stt=False,
                                       polish_model_ref="local/s1-mini-q4_k_m"),
        outcome_callback=outcomes.append,
    )

    assert result
    assert outcomes == ["fidelity_reject"]


@pytest.mark.parametrize(
    ("mode", "expected_s1_ceiling"),
    [("fast", 3.4), ("balanced", 5.4), ("quality", 8.4)],
)
def test_s1_mode_floor_does_not_change_cloud_profile_ceiling(monkeypatch, mode, expected_s1_ceiling):
    monkeypatch.setattr(polish_latency, "observed_latency", lambda _model_ref: 0.574)

    assert polish_latency.ceiling_for("gemini/flash", mode=mode, word_count=120) == 2.0
    assert polish_latency.ceiling_for("local/s1-mini-q4_k_m", mode=mode, word_count=120) == expected_s1_ceiling
