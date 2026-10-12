from types import SimpleNamespace
from unittest.mock import Mock

from voice_flow import main, polisher as polisher_module, s1_engine, storage as storage_module
from voice_flow.effective_style import resolve_effective_style
from voice_flow.style_engine import STYLE_INSTRUCTIONS
from voice_flow.voice_commands import detect_voice_command


USER_UTTERANCE = (
    "Now there is one issue happening with the voice locker that voice policy incommands are not working. "
    "Can we check what is happening and fix it here? "
    "Voicelow, make this as a good prompt?"
)
EXPECTED_PROMPT = (
    "Context: Now there is one issue happening with the voice locker that voice policy incommands are not working.\n"
    "Task: Check what is happening and fix it here."
)


def _inputs(model_ref, *, enabled=True):
    detection = detect_voice_command(USER_UTTERANCE)
    assert detection.command is not None
    assert detection.content.startswith("Now there is one issue")
    base = SimpleNamespace(
        category="other",
        style_id="other_formal",
        instruction=STYLE_INSTRUCTIONS["other_formal"],
    )
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(
        cleanup_level="cleanup_light",
        style_id=base.style_id,
        cursor_context=None,
        polish_model_ref=model_ref,
        polish_speed_mode="balanced",
    )
    fake_storage = Mock()
    fake_storage.get_setting.side_effect = lambda key, default=None: (
        enabled if key == "polishing_enabled" else default
    )
    fake_storage.get_all_api_keys.return_value = {}
    engine = polisher_module.TextPolisher()
    return detection, effective, session, fake_storage, engine


def _patch_local_environment(monkeypatch, fake_storage, engine, *, enabled=True):
    monkeypatch.setattr(polisher_module, "storage", fake_storage)
    monkeypatch.setattr(storage_module, "storage", fake_storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: enabled)
    monkeypatch.setattr(main, "polisher", engine)
    guarded_injector = Mock()
    guarded_injector.paste_text.side_effect = AssertionError("finalization must not inject into a desktop app")
    monkeypatch.setattr(main, "ClipboardInjector", Mock(return_value=guarded_injector))


def _finalize(detection, effective, session, outcomes, attempt_outcomes=None):
    return object.__new__(main.VoiceFlowApp)._finalize_text(
        detection.content,
        session,
        effective=effective,
        command=detection.command,
        outcome_callback=outcomes.append,
        attempt_outcome_callback=(attempt_outcomes.append if attempt_outcomes is not None else None),
    )


def test_user_example_routes_through_one_mocked_s1_cleanup_then_local_prompt(monkeypatch):
    detection, effective, session, fake_storage, engine = _inputs(s1_engine.S1_MODEL_ID)
    _patch_local_environment(monkeypatch, fake_storage, engine)
    s1_calls = []

    def fake_s1_can_handle(*, task=None, **kwargs):
        return task == "cleanup"

    def fake_s1_polish(raw_text, instruction, **kwargs):
        s1_calls.append((raw_text, instruction, kwargs))
        return raw_text

    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", fake_s1_can_handle)
    monkeypatch.setattr(s1_engine, "polish_with_s1", fake_s1_polish)
    monkeypatch.setattr(engine, "_run_bridge_with_timeout", lambda worker, timeout, deadline=None: worker(timeout))
    pool = Mock(side_effect=AssertionError("selected S1 must not enter the provider pool"))
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)

    outcomes = []
    attempt_outcomes = []
    result = _finalize(detection, effective, session, outcomes, attempt_outcomes)

    assert len(s1_calls) == 1
    assert s1_calls[0][0] == detection.content
    assert s1_calls[0][2]["task"] == "cleanup"
    pool.assert_not_called()
    assert outcomes == ["local_rewrite"]
    # Phase 1.1: S1 only ran its cleanup pass for a prompt command, so that
    # attempt is reported as not fulfilling the command; the local prompt
    # rewrite then completes it (final outcome above is unchanged).
    assert attempt_outcomes == ["command_unfulfilled"]
    assert result == EXPECTED_PROMPT


def test_user_example_with_online_selection_keeps_prompt_and_style_metadata(monkeypatch):
    detection, effective, session, fake_storage, engine = _inputs("test/remote-model")
    _patch_local_environment(monkeypatch, fake_storage, engine)
    pool = Mock(return_value=EXPECTED_PROMPT)
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    polish_calls = []
    original_polish = engine.polish

    def record_polish(*args, **kwargs):
        polish_calls.append(kwargs.copy())
        return original_polish(*args, **kwargs)

    monkeypatch.setattr(engine, "polish", record_polish)
    outcomes = []
    result = _finalize(detection, effective, session, outcomes)

    assert result == EXPECTED_PROMPT
    assert outcomes == ["ai_accepted"]
    assert len(polish_calls) == 1
    assert polish_calls[0]["style_instruction"] == effective.instruction
    assert polish_calls[0]["style_id"] == effective.style_id
    assert polish_calls[0]["task"] == "prompt"
    assert polish_calls[0]["command_format"] == "prompt"
    assert polish_calls[0]["command"] is detection.command
    assert pool.call_count == 1
    assert pool.call_args.args[2] == effective.instruction
    assert "actionable instructions" in pool.call_args.kwargs["system_prompt"]


def test_user_example_with_polishing_off_does_not_call_s1_or_rewrite(monkeypatch):
    detection, effective, session, fake_storage, engine = _inputs(s1_engine.S1_MODEL_ID, enabled=False)
    _patch_local_environment(monkeypatch, fake_storage, engine, enabled=False)
    s1 = Mock(side_effect=AssertionError("polishing OFF must not call S1"))
    pool = Mock(side_effect=AssertionError("polishing OFF must not call a provider"))
    monkeypatch.setattr(s1_engine, "polish_with_s1", s1)
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    outcomes = []

    result = _finalize(detection, effective, session, outcomes)

    assert outcomes == ["disabled"]
    s1.assert_not_called()
    pool.assert_not_called()
    assert "Can we check what is happening and fix it here?" in result
    assert not result.startswith("Context:")
