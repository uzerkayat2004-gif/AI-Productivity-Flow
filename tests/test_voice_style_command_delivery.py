"""Focused delivery coverage for Voice Flow styles, commands, and local polish."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

from voice_flow import effective_style as effective_style_module
from voice_flow import lfm_engine
from voice_flow.effective_style import resolve_effective_style
from voice_flow import polisher as polisher_module
from voice_flow.polisher import TextPolisher
from voice_flow.style_formatter import style_formatter
from voice_flow.voice_commands import detect_voice_command


def _base_style() -> SimpleNamespace:
    return SimpleNamespace(
        category="developer",
        style_id="developer_casual",
        instruction="Conversational developer notes.",
    )


def test_commands_activate_saved_email_and_temporary_overrides() -> None:
    """Commands are parsed before the model and become its trusted style policy."""
    settings = {
        "style_email": "email_excited",
        "style_email_extra": "Always sign off with Best.",
    }
    with patch.object(
        effective_style_module.storage,
        "get_setting",
        side_effect=lambda key, default=None: settings.get(key, default),
    ):
        professional = resolve_effective_style(
            _base_style(),
            detect_voice_command(
                "Hey Voice Flow, make this a professional email but keep my wording. "
                "NimbusSDK ships Monday."
            ).command,
        )
        short = resolve_effective_style(
            _base_style(),
            detect_voice_command("Hey Voice Flow, make this short. NimbusSDK ships Monday.").command,
        )
        usual_email = resolve_effective_style(
            _base_style(),
            detect_voice_command("Hey Voice Flow, make this my usual email. NimbusSDK ships Monday.").command,
        )

    assert (professional.category, professional.style_id) == ("email", "email_formal")
    assert professional.requires_ai and professional.preserve_wording
    assert "formal email" in professional.instruction.lower()
    assert "do not re-author" in professional.instruction.lower()
    assert (short.style_id, short.requires_ai) == ("developer_casual", True)
    assert "keep the result short" in short.instruction.lower()
    assert (usual_email.category, usual_email.style_id) == ("email", "email_excited")
    assert "always sign off with best" in usual_email.instruction.lower()


def test_successful_local_model_receives_command_effective_instruction(monkeypatch) -> None:
    """The local LFM receives the command-composed policy, not just raw cleanup."""
    command = detect_voice_command(
        "Hey Voice Flow, make this a professional email but keep my wording. "
        "NimbusSDK ships Monday."
    ).command
    assert command is not None
    with patch.object(effective_style_module.storage, "get_setting", return_value="email_excited"):
        effective = resolve_effective_style(_base_style(), command)

    captured: dict[str, object] = {}
    engine = TextPolisher()
    monkeypatch.setattr(
        polisher_module.storage,
        "get_setting",
        lambda key, default=None: True if key == "polishing_enabled" else default,
    )
    monkeypatch.setattr(polisher_module.storage, "get_all_api_keys", lambda: {})
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lfm_engine, "is_lfm_downloaded", lambda: True)
    monkeypatch.setattr(
        lfm_engine,
        "polish_with_lfm",
        lambda text, instruction, *, timeout_seconds: captured.update(
            text=text, instruction=instruction, timeout_seconds=timeout_seconds
        ) or "NimbusSDK ships Monday.",
    )
    monkeypatch.setattr(polisher_module, "_apply_dictionary_safely", lambda text: text)

    outcomes: list[str] = []
    result = engine.polish(
        "NimbusSDK ships Monday.",
        style_instruction=effective.instruction,
        force_ai=effective.requires_ai,
        task=effective.task,
        deadline=time.monotonic() + 5,
        outcome_callback=outcomes.append,
    )

    assert result == "NimbusSDK ships Monday."
    assert captured["text"] == "NimbusSDK ships Monday."
    assert captured["instruction"] == effective.instruction
    assert "formal email" in str(captured["instruction"]).lower()
    assert outcomes == ["local_model"]


def test_style_formatting_preserves_custom_dictionary_casing() -> None:
    """A casual style may change prose casing but retains declared terminology."""
    assert style_formatter.format(
        "nimbussdk ships monday",
        style="email_very_casual",
        custom_dictionary=("NimbusSDK",),
    ) == "NimbusSDK ships monday"
