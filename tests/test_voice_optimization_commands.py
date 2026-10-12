from __future__ import annotations

import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from voice_flow.voice_commands import detect_voice_command


def test_bullet_points_phrase_stays_inside_command_and_preserves_payload() -> None:
    text = (
        "Hey Voice Flow, could you turn this into bullet points. "
        "NimbusSDK ships Monday. Keep the rollback disabled."
    )
    result = detect_voice_command(text)
    assert result.command is not None
    assert result.command.format == "bullet_list"
    assert result.content == "NimbusSDK ships Monday. Keep the rollback disabled."


def test_bullet_list_command_boundaries_and_payload_format_words() -> None:
    for command in (
        "Hey Voice Flow, make this a bullet list. NimbusSDK ships Monday.",
        "Hey Voice Flow, turn this into a bulleted list. NimbusSDK ships Monday.",
        "NimbusSDK ships Monday. Hey Voice Flow, make this bullet points",
        "Hey Voice Flow make this bullets NimbusSDK ships Monday",
    ):
        result = detect_voice_command(command)
        assert result.command is not None, command
        assert result.command.format == "bullet_list", command
        assert "NimbusSDK ships Monday" in result.content, command

    payload = (
        "Hey Voice Flow, make this a bullet list. NimbusSDK ships Monday. "
        "The email mentions bullet points and a numbered list."
    )
    result = detect_voice_command(payload)
    assert result.command is not None
    assert result.content == "NimbusSDK ships Monday. The email mentions bullet points and a numbered list."


def test_my_next_dictation_scope_is_next_and_content_survives() -> None:
    text = (
        "Hey Voice Flow, make my next dictation a professional email. "
        "NimbusSDK ships Monday. Keep the rollback disabled."
    )
    result = detect_voice_command(text)
    assert result.command is not None
    assert result.command.scope == "next"
    assert result.command.format == "email"
    assert result.command.overrides["formality"] == "professional"
    assert result.content == "NimbusSDK ships Monday. Keep the rollback disabled."


def test_change_this_into_email_is_a_command() -> None:
    text = (
        "Hey Voice Flow, change this into a professional email. "
        "NimbusSDK ships Monday. Keep the rollback disabled."
    )
    result = detect_voice_command(text)
    assert result.command is not None
    assert result.command.format == "email"
    assert result.command.overrides["formality"] == "professional"
    assert result.content == "NimbusSDK ships Monday. Keep the rollback disabled."


def test_quoted_and_ordinary_format_mentions_remain_dictation() -> None:
    for text in (
        'She said "Hey Voice Flow, turn this into bullet points." NimbusSDK ships Monday.',
        "If I say hey voice flow turn this into bullet points, it is an example. NimbusSDK ships Monday.",
        "Hey Voice Flow, the bullet points in this email mention NimbusSDK ships Monday.",
    ):
        result = detect_voice_command(text)
        assert result.command is None
        assert result.content == text
