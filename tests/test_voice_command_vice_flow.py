from voice_flow.voice_commands import detect_voice_command


ACTUAL_USER_UTTERANCE = (
    "He right now there is one problem happening with the voice lock feature that when I'm using the voice lock picture "
    "without voice polishing it's working slow previously it was working so fast like it it it was instant as soon as "
    "I released my hotkey it was pasting the text but now it is taking one one and a half second and all can you "
    "check what's happening and fix it hey vice flow make this as a prom."
)


def test_explicit_vice_flow_alias_recognizes_trailing_prompt_command():
    result = detect_voice_command("hey vice flow make this as a prom.")

    assert result.command is not None
    assert result.command.operation == "prompt_generation"
    assert result.command.format == "prompt"
    assert result.content == ""
    assert result.command.raw_phrase == "make this as a prom."


def test_explicit_vice_flow_alias_preserves_full_preceding_issue_report():
    content = (
        "Now there is one issue happening with the voice locker that voice policy incommands are not working. "
        "Can we check what is happening and fix it here?"
    )
    result = detect_voice_command(f"{content} hey vice flow make this as a prom.")

    assert result.command is not None
    assert result.command.operation == "prompt_generation"
    assert result.command.format == "prompt"
    assert result.content == content
    assert result.command.raw_phrase == "make this as a prom."


def test_explicit_vice_flow_alias_is_case_insensitive_and_accepts_ok_prefix():
    for wake in ("HEY VICE FLOW", "Ok, vice flow", "Okay vice-flow"):
        result = detect_voice_command(f"{wake}, make this as a prom.")
        assert result.command is not None, wake
        assert result.command.format == "prompt"


def test_vice_flow_without_explicit_wake_is_ordinary_text():
    for text in (
        "The vice flow is a normal feature name.",
        "vice flow make this as a prom.",
        "The phrase vice flow, make this as a prom appears in the notes.",
    ):
        result = detect_voice_command(text)
        assert result.command is None, text
        assert result.content == text, text


def test_quoted_reported_code_and_url_mentions_are_not_commands():
    cases = (
        'I said "hey vice flow make this as a prom" yesterday.',
        "They reported hey vice flow make this as a prom yesterday.",
        "Use `hey vice flow make this as a prom` as the example.",
        "The URL https://example.test/hey-vice-flow-make-this-as-a-prom is relevant.",
    )
    for text in cases:
        result = detect_voice_command(text)
        assert result.command is None, text
        assert result.content == text, text


def test_explicit_vice_flow_alias_still_requires_known_immediate_continuation():
    for text in (
        "Hey vice flow, are you there?",
        "Hey vice flow is part of the dictation.",
        "Ok vice flow maybe later.",
    ):
        result = detect_voice_command(text)
        assert result.command is None, text
        assert result.content == text, text


def test_actual_user_utterance_reaches_finalizer_and_local_prompt_rewrite(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from voice_flow import main, polisher as polisher_module, s1_engine, storage as storage_module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.style_engine import STYLE_INSTRUCTIONS

    detection = detect_voice_command(ACTUAL_USER_UTTERANCE)
    assert detection.command is not None
    assert detection.command.operation == "prompt_generation"
    assert detection.command.format == "prompt"
    assert detection.command.raw_phrase == "make this as a prom."
    assert detection.content == ACTUAL_USER_UTTERANCE.removesuffix(" hey vice flow make this as a prom.")

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
        polish_model_ref=s1_engine.S1_MODEL_ID,
        polish_speed_mode="balanced",
    )
    fake_storage = Mock()
    fake_storage.get_setting.side_effect = lambda key, default=None: (
        True if key == "polishing_enabled" else default
    )
    fake_storage.get_all_api_keys.return_value = {}
    engine = polisher_module.TextPolisher()
    monkeypatch.setattr(polisher_module, "storage", fake_storage)
    monkeypatch.setattr(storage_module, "storage", fake_storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(main, "polisher", engine)
    guarded_injector = Mock()
    guarded_injector.paste_text.side_effect = AssertionError("finalization must not inject into a desktop app")
    monkeypatch.setattr(main, "ClipboardInjector", Mock(return_value=guarded_injector))

    # Simulate only conservative S1 punctuation cleanup. It inserts a sentence
    # boundary before the dictated polite request without changing its words.
    s1_input = detection.content
    cleaned = s1_input.replace("one one and a half second and all can you", "one one and a half second. Can you")
    cleaned = cleaned.rstrip(" .?!") + "?"
    s1_calls = []

    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda *, task=None, **kwargs: task == "cleanup")

    def fake_s1_polish(raw_text, instruction, **kwargs):
        s1_calls.append((raw_text, kwargs))
        return cleaned

    monkeypatch.setattr(s1_engine, "polish_with_s1", fake_s1_polish)
    monkeypatch.setattr(engine, "_run_bridge_with_timeout", lambda worker, timeout, deadline=None: worker(timeout))
    provider_pool = Mock(side_effect=AssertionError("selected S1 must not use the provider pool"))
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider_pool)

    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        detection.content,
        session,
        effective=effective,
        command=detection.command,
        outcome_callback=outcomes.append,
    )

    assert len(s1_calls) == 1
    assert s1_calls[0][0] == detection.content
    assert s1_calls[0][1]["task"] == "cleanup"
    provider_pool.assert_not_called()
    assert outcomes == ["local_rewrite"]
    assert result.startswith("Context: He right now there is one problem happening with the voice lock feature")
    assert result.startswith("Context: " + cleaned.split(". Can you", 1)[0])
    assert "Task: Check what's happening and fix it." in result
    assert "one one and a half second" in result
    assert "make this as a prom" not in result


def test_actual_user_utterance_polishing_off_keeps_report_as_dictation(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from voice_flow import main, polisher as polisher_module, s1_engine, storage as storage_module

    detection = detect_voice_command(ACTUAL_USER_UTTERANCE)
    assert detection.command is not None
    session = SimpleNamespace(
        cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
        polish_model_ref=s1_engine.S1_MODEL_ID, polish_speed_mode="balanced",
    )
    fake_storage = Mock()
    fake_storage.get_setting.side_effect = lambda key, default=None: False if key == "polishing_enabled" else default
    fake_storage.get_all_api_keys.return_value = {}
    engine = polisher_module.TextPolisher()
    monkeypatch.setattr(polisher_module, "storage", fake_storage)
    monkeypatch.setattr(storage_module, "storage", fake_storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: False)
    monkeypatch.setattr(main, "polisher", engine)
    s1 = Mock(side_effect=AssertionError("polishing OFF must not call S1"))
    provider_pool = Mock(side_effect=AssertionError("polishing OFF must not call a provider"))
    monkeypatch.setattr(s1_engine, "polish_with_s1", s1)
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider_pool)

    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        ACTUAL_USER_UTTERANCE, session, effective=None, command=None,
        outcome_callback=outcomes.append,
    )

    assert outcomes == ["disabled"]
    s1.assert_not_called()
    provider_pool.assert_not_called()
    assert "can you check what's happening and fix it" in result.lower()
    assert "hey vice flow make this as a prom" in result.lower()
    assert "voice lock feature" in result
    assert not result.startswith("Context:")


def test_actual_user_utterance_online_path_forwards_effective_prompt_metadata(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from voice_flow import main, polisher as polisher_module, storage as storage_module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.style_engine import STYLE_INSTRUCTIONS

    detection = detect_voice_command(ACTUAL_USER_UTTERANCE)
    assert detection.command is not None
    base = SimpleNamespace(category="other", style_id="other_formal", instruction=STYLE_INSTRUCTIONS["other_formal"])
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(
        cleanup_level="cleanup_light", style_id=base.style_id, cursor_context=None,
        polish_model_ref="test/remote-model", polish_speed_mode="balanced",
    )
    fake_storage = Mock()
    fake_storage.get_setting.side_effect = lambda key, default=None: True if key == "polishing_enabled" else default
    fake_storage.get_all_api_keys.return_value = {"openai": "offline-test-key"}
    engine = polisher_module.TextPolisher()
    monkeypatch.setattr(polisher_module, "storage", fake_storage)
    monkeypatch.setattr(storage_module, "storage", fake_storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    monkeypatch.setattr(main, "polisher", engine)

    transformed = (
        "Context: He right now there is one problem happening with the voice lock feature that when I'm using the voice "
        "lock picture without voice polishing it's working slow previously it was working so fast like it it it was "
        "instant as soon as I released my hotkey it was pasting the text but now it is taking one one and a half second "
        "and all.\nTask: Check what's happening and fix it."
    )
    pool = Mock(return_value=transformed)
    monkeypatch.setattr(engine, "_polish_with_api_pool", pool)
    polish_calls = []
    original_polish = engine.polish

    def record_polish(*args, **kwargs):
        polish_calls.append(kwargs.copy())
        return original_polish(*args, **kwargs)

    monkeypatch.setattr(engine, "polish", record_polish)
    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(
        detection.content, session, effective=effective, command=detection.command,
        outcome_callback=outcomes.append,
    )

    assert result == transformed
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
