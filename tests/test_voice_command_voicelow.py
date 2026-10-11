from voice_flow.voice_commands import detect_voice_command


def _assert_prompt_command(result, payload):
    assert result.command is not None
    assert result.command.operation == "prompt_generation"
    assert result.command.format == "prompt"
    assert result.content == payload
    assert "voicelow" not in result.content.casefold()
    assert "voice low" not in result.content.casefold()
    assert "make this as a good prompt" not in result.content.casefold()


def test_voicelow_prompt_with_payload_at_beginning():
    payload = "Build a bakery website with orange and cream."
    result = detect_voice_command(f"Voicelow, make this as a good prompt? {payload}")
    _assert_prompt_command(result, payload)


def test_voice_low_prompt_after_payload():
    payload = "Build a bakery website with orange and cream."
    result = detect_voice_command(f"{payload} Voice low, make this as a good prompt")
    _assert_prompt_command(result, payload)


def test_explicit_wake_prefix_accepts_literal_voicelow_asr_aliases():
    payload = "Build a bakery website with orange and cream."
    for wake in ("Hey Voicelow", "Hey, Voice low", "Ok Voicelow", "Okay Voice low"):
        result = detect_voice_command(f"{wake}, make this as a good prompt? {payload}")
        _assert_prompt_command(result, payload)


def test_voicelow_unpunctuated_prompt_keeps_exact_payload():
    payload = "Build a bakery website with orange and cream"
    result = detect_voice_command(f"Voicelow make this as a good prompt {payload}")
    _assert_prompt_command(result, payload)


def test_full_reported_issue_becomes_prompt_command_without_losing_report():
    payload = (
        "Now there is one issue happening with the voice locker that voice policy incommands are not working. "
        "Can we check what is happening and fix it here?"
    )
    result = detect_voice_command(
        f"{payload} Voicelow, make this as a good prompt?"
    )
    _assert_prompt_command(result, payload)


def test_voicelow_alias_requires_command_shape_and_clause_boundary():
    cases = (
        "The voice low setting is enabled.",
        "Voicelow is the name of the audio file.",
        "Open https://example.test/Voicelow",
        "The file voice-low.txt is attached.",
        'I said "Voicelow, make this as a good prompt." yesterday.',
        "They mentioned Voicelow, make this as a good prompt yesterday.",
        "Hey Voice low, are you there?",
        "We discussed the voice low, make this as a good prompt yesterday.",
        "Voicelows make this as a good prompt.",
    )
    for text in cases:
        result = detect_voice_command(text)
        assert result.command is None, text
        assert result.content == text, text


def test_voice_low_command_inside_code_remains_dictation():
    text = "Use `Voicelow, make this as a good prompt` as the sample string."
    result = detect_voice_command(text)
    assert result.command is None
    assert result.content == text
