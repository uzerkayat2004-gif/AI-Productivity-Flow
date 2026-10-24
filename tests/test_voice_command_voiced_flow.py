"""Offline parser regressions for the explicit voiced flow ASR alias."""
from voice_flow.activation import ActivationConfig
from voice_flow.voice_commands import detect_voice_command


ACTUAL_USER_TRANSCRIPT = "Here right now there are so many problem is happening with the app I don't know how can we fix that those problems because the pro those problems are keep coming again and again so we have to figure out a way to fix those problems so can you find the way like the same problem that we were facing previously it is coming back again and again hey voiced flow make this as a prompt."


def test_exact_user_transcript_preserves_every_content_word():
    result = detect_voice_command(ACTUAL_USER_TRANSCRIPT)
    assert result.command is not None
    assert result.command.operation == "prompt_generation"
    assert result.command.format == "prompt"
    assert result.command.raw_phrase == "make this as a prompt."
    assert result.content == ACTUAL_USER_TRANSCRIPT.removesuffix(" hey voiced flow make this as a prompt.")


def test_explicit_prefixes_and_supported_intents():
    for wake in ("hey voiced flow", "OK, voiced flow", "Okay voiced flow"):
        for instruction, fmt, overrides in (
            ("make this as a prompt", "prompt", {}),
            ("make this an email", "email", {}),
            ("make this professional", None, {"formality": "professional"}),
            ("make this a normal message", "personal_message", {}),
        ):
            result = detect_voice_command(f"Ship tomorrow. {wake}, {instruction}.")
            assert result.command is not None, (wake, instruction)
            assert result.command.format == fmt
            for key, value in overrides.items():
                assert result.command.overrides[key] == value
            assert result.content == "Ship tomorrow."


def test_alias_requires_immediate_known_command():
    for text in (
        "Hey voiced flow, are you there?",
        "Hey voiced flow is professional and friendly.",
        "Okay voiced flow maybe make this an email.",
        "hey voiced flowery make this an email.",
        "voiced flow make this a prompt.",
        "The voiced flow is professional.",
        "The phrase voiced flow, make this a prompt is in the notes.",
        'I said "hey voiced flow make this a prompt" yesterday.',
        "Use `hey voiced flow make this a prompt` in the example.",
        "She said hey voiced flow make this a prompt.",
        "When I say hey voiced flow make this a prompt, it activates.",
    ):
        result = detect_voice_command(text)
        assert result.command is None, text
        assert result.content == text


def test_disabled_and_custom_activation_are_unchanged():
    text = "Ship tomorrow. hey voiced flow make this a prompt."
    for config in (ActivationConfig(enabled=False, legacy_voice_flow=True), ActivationConfig(assistant_name="Nova")):
        result = detect_voice_command(text, activation=config)
        assert result.command is None
        assert result.content == text
    result = detect_voice_command("Hey Nova make this a prompt. Ship tomorrow.", activation=ActivationConfig(assistant_name="Nova"))
    assert result.command is not None
    assert result.command.format == "prompt"
    assert result.content == "Ship tomorrow."


def test_leading_alias_separates_command_from_following_content():
    result = detect_voice_command("Hey voiced flow, make this an email. Ship tomorrow.")
    assert result.command is not None
    assert result.command.format == "email"
    assert result.content == "Ship tomorrow."
