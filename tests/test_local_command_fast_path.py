"""Simple format commands can use the real local cleanup path immediately."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("phrase, content, marker", [
    ("make this bullet points", "Review the budget. Call Alex. Send the report Friday.", "- Review the budget"),
])
def test_lfm_format_only_commands_do_not_wait_for_generation(monkeypatch, phrase, content, marker):
    from voice_flow import main, polisher as polisher_module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.voice_commands import detect_voice_command
    detection = detect_voice_command(f"Hey Voice Flow, {phrase}. {content}")
    base = SimpleNamespace(category="other", style_id="other_formal", instruction="Standard punctuation.")
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="local/lfm2.5-350m-qad-q4_0", polish_speed_mode="balanced")
    settings = Mock()
    settings.get_setting.side_effect = lambda key, default=None: True if key == "polishing_enabled" else default
    settings.get_all_api_keys.return_value = {}
    monkeypatch.setattr(polisher_module, "storage", settings)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: True)
    engine = polisher_module.TextPolisher()
    provider = Mock(return_value=None)
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider)
    monkeypatch.setattr(main, "polisher", engine)
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)
    dictionary = Mock(side_effect=lambda text, trace=None: text)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", dictionary)
    monkeypatch.setattr(main.dictionary_engine, "restore_dictionary_spelling", lambda text: text)
    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(detection.content, session, effective=effective,
        command=detection.command, outcome_callback=outcomes.append)
    provider.assert_not_called()
    dictionary.assert_called_once()
    assert outcomes == ["local_format"] and marker in result


def test_successful_ai_candidate_receives_protected_very_casual_register(monkeypatch):
    from voice_flow import polisher as module
    settings = Mock()
    settings.get_setting.side_effect = lambda key, default=None: True if key == "polishing_enabled" else default
    settings.get_all_api_keys.return_value = {}
    monkeypatch.setattr(module, "storage", settings)
    monkeypatch.setattr(module, "_apply_dictionary_with_trace", lambda text, trace: text)
    engine = module.TextPolisher()
    monkeypatch.setattr(engine, "_polish_with_api_pool", Mock(return_value="Please check HTTPClient today."))
    outcomes = []
    result = engine.polish("Please check HTTPClient today.", "minimal developer text in lowercase with protected code tokens",
        force_ai=True, model_ref="test/provider", outcome_callback=outcomes.append)
    assert result == "please check HTTPClient today" and outcomes == ["ai_accepted"]


def test_bullet_boundaries_inside_quotes_and_code_stay_literal():
    from voice_flow.main import _format_dictated_bullets
    source = 'Review "Do not. Call Alex; Send it"; Send the report using `call(); prepare()`.'
    result = _format_dictated_bullets(source)
    assert result == '- Review "Do not. Call Alex; Send it"\n- Send the report using `call(); prepare()`.'
