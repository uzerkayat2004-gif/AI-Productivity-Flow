from types import SimpleNamespace

import pytest

from voice_flow.command_rewrites import try_local_command_rewrite
from voice_flow.effective_style import resolve_effective_style
from voice_flow.style_engine import STYLE_INSTRUCTIONS
from voice_flow.voice_commands import detect_voice_command


def _rewrite(text, command_text="make this a prompt"):
    command = detect_voice_command(f"Hey Voice Flow, {command_text}.").command
    base = SimpleNamespace(
        category="other",
        style_id="other_formal",
        instruction=STYLE_INSTRUCTIONS["other_formal"],
    )
    effective = resolve_effective_style(base, command)
    return try_local_command_rewrite(
        text,
        task=effective.task,
        command_format=command.format,
        style_id=effective.style_id,
        instruction=effective.instruction,
        overrides=command.overrides,
    )


def test_can_we_check_question_becomes_an_actionable_task():
    source = "Can we check what is happening and fix it here?"
    result = _rewrite(source)
    assert result == "Task: Check what is happening and fix it here."
    assert result != f"Task: {source}"


@pytest.mark.parametrize("source,expected", [
    ("Could you please build a Python tool?", "Task: Build a Python tool."),
    ("Would we create a validator?", "Task: Create a validator."),
    ("Can you write a review?", "Task: Write a review."),
    ("Could we design a form?", "Task: Design a form."),
    ("Would you implement the requested check?", "Task: Implement the requested check."),
])
def test_supported_modal_forms_and_action_verbs(source, expected):
    context = "The team has a backlog for this release."
    result = _rewrite(f"{context} {source}")
    assert result == f"Context: {context}\n{expected}"


def test_user_issue_context_is_separated_from_transformed_request():
    context = (
        "Now there is one issue happening with the voice locker that voice policy incommands are not working."
    )
    source = f"{context} Can we check what is happening and fix it here?"
    result = _rewrite(source)
    assert result == (
        f"Context: {context}\nTask: Check what is happening and fix it here."
    )
    assert "Can we check" not in result
    assert "fix it here" in result


NATIVE_USER_CONTEXT_CANDIDATE = (
    "He right now there is one problem happening with the voice lock feature that when I'm using the voice lock picture "
    "without voice polishing it's working slow. Previously it was working so fast, like it was instant as soon as I "
    "released my hotkey. It was pasting the text, but now it is taking one and a half second, and all can you check "
    "what's happening and fix it?"
)


def test_captured_native_candidate_splits_only_terminal_asr_and_all_request():
    result = _rewrite(NATIVE_USER_CONTEXT_CANDIDATE)

    assert result == (
        "Context: He right now there is one problem happening with the voice lock feature that when I'm using the voice "
        "lock picture without voice polishing it's working slow. Previously it was working so fast, like it was instant "
        "as soon as I released my hotkey. It was pasting the text, but now it is taking one and a half second, and all.\n"
        "Task: Check what's happening and fix it."
    )
    assert "one and a half second" in result
    assert "what's happening and fix it" in result
    assert "Can you" not in result


@pytest.mark.parametrize("source", [
    "If the backup finishes, and all can you check it?",
    "Unless the reviewer approves, and all could you fix it?",
    'The report says "and all can you check it?" as an example.',
    "They reported, and all can you check what happened?",
    "Can we not delete the backup and all?",
    "May I delete the backup and all?",
])
def test_run_on_asr_boundary_does_not_promote_reported_conditional_or_permission_text(source):
    assert _rewrite(source) is None


def test_newline_is_a_supported_context_sentence_boundary():
    context = "The voice policy commands are not working."
    result = _rewrite(f"{context}\nCan we check the issue?")
    assert result == f"Context: {context}\nTask: Check the issue."


@pytest.mark.parametrize("source", [
    "Can we not delete the backup?",
    "Could you please not change HTTPClient?",
    "Can we fix it if the migration succeeds?",
    "Would you review it unless the approval is missing?",
    "Can we check whether the service is running?",
    "May I delete the old files?",
])
def test_negated_conditional_and_permission_questions_are_not_rewritten(source):
    assert _rewrite(source) is None


@pytest.mark.parametrize("source", [
    'The sample says "Can we check the status?" exactly.',
    "Keep `Can we check the status?` as the code sample.",
    "The URL https://example.test/Can-we-check?mode=1 is in the report.",
])
def test_request_like_text_inside_protected_literals_is_not_rewritten(source):
    assert _rewrite(source) is None


def test_protected_context_and_decimal_remain_exact_around_real_request():
    context = 'Use version 2.5 and keep `parseJSON` from https://Example.test/Case unchanged.'
    result = _rewrite(f"{context} Could you please review it?")
    assert result == f"Context: {context}\nTask: Review it."
    assert "2.5" in result
    assert "`parseJSON`" in result
    assert "https://Example.test/Case" in result


@pytest.mark.parametrize("source,literals", [
    (
        "Could you review `parseJSON` at https://Example.test/Case?",
        ("`parseJSON`", "https://Example.test/Case?"),
    ),
    (
        'Could you review "blue mode" in version 2.5 using C:\\Work\\CaseFile.txt?',
        ('"blue mode"', "2.5", r"C:\Work\CaseFile.txt"),
    ),
])
def test_protected_request_tail_is_restored_before_validation(source, literals):
    result = _rewrite(source)
    assert result is not None
    assert result.startswith("Task: Review ")
    for literal in literals:
        assert literal in result


def test_length_override_is_outside_the_finite_transform_scope():
    assert _rewrite("Can we check what is happening and fix it here?", "make this a short prompt") is None


def test_captured_candidate_runs_through_real_finalizer_after_mocked_s1_cleanup(monkeypatch):
    from unittest.mock import Mock

    from voice_flow import main, polisher as polisher_module, s1_engine, storage as storage_module

    utterance = (
        "He right now there is one problem happening with the voice lock feature that when I'm using the voice lock picture "
        "without voice polishing it's working slow previously it was working so fast like it it it was instant as soon as "
        "I released my hotkey it was pasting the text but now it is taking one one and a half second and all can you "
        "check what's happening and fix it hey vice flow make this as a prom."
    )
    from voice_flow.voice_commands import detect_voice_command
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.style_engine import STYLE_INSTRUCTIONS

    detection = detect_voice_command(utterance)
    assert detection.command is not None
    assert detection.command.format == "prompt"
    base = SimpleNamespace(
        category="other", style_id="other_formal", instruction=STYLE_INSTRUCTIONS["other_formal"]
    )
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(
        cleanup_level="cleanup_light", style_id=base.style_id, cursor_context=None,
        polish_model_ref=s1_engine.S1_MODEL_ID, polish_speed_mode="balanced",
    )
    fake_storage = Mock()
    fake_storage.get_setting.side_effect = lambda key, default=None: True if key == "polishing_enabled" else default
    fake_storage.get_all_api_keys.return_value = {}
    engine = polisher_module.TextPolisher()
    monkeypatch.setattr(polisher_module, "storage", fake_storage)
    monkeypatch.setattr(storage_module, "storage", fake_storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(main, "polisher", engine)
    injector = Mock()
    injector.paste_text.side_effect = AssertionError("finalization must not inject into a desktop app")
    monkeypatch.setattr(main, "ClipboardInjector", Mock(return_value=injector))

    # This is the exact completion captured from the bounded native diagnostic.
    candidate = NATIVE_USER_CONTEXT_CANDIDATE
    s1_calls = []
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda *, task=None, **kwargs: task == "cleanup")

    def fake_s1_polish(raw_text, instruction, **kwargs):
        s1_calls.append((raw_text, kwargs))
        return candidate

    monkeypatch.setattr(s1_engine, "polish_with_s1", fake_s1_polish)
    monkeypatch.setattr(engine, "_run_bridge_with_timeout", lambda worker, timeout, deadline=None: worker(timeout))
    provider_pool = Mock(side_effect=AssertionError("selected S1 must not use the provider pool"))
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider_pool)

    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        detection.content, session, effective=effective, command=detection.command,
        outcome_callback=outcomes.append,
    )

    assert len(s1_calls) == 1
    assert s1_calls[0][1]["task"] == "cleanup"
    provider_pool.assert_not_called()
    assert outcomes == ["local_rewrite"]
    assert result.startswith("Context: He right now there is one problem happening")
    assert "one and a half second" in result
    assert "Task: Check what's happening and fix it." in result
