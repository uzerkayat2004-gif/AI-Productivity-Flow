"""Offline regressions for identifier spelling in deterministic fallbacks."""
from unittest.mock import Mock

import pytest

from voice_flow import polisher as polisher_module
from voice_flow.text_processing import is_protected_literal, lowercase_prose_text, sentence_case_text, smart_format


@pytest.mark.parametrize("identifier", ["HTTPClient", "OpenAI", "iPhone", "parseJSON", "userID", "className"])
def test_internal_case_identifiers_are_literal(identifier):
    assert is_protected_literal(identifier)
    assert lowercase_prose_text(f"CHECK {identifier} Today") == f"check {identifier} today"
    assert sentence_case_text(f"{identifier} is ready") == f"{identifier} is ready"


def test_provider_failed_very_casual_fallback_preserves_identifiers(monkeypatch):
    storage = Mock()
    storage.get_setting.side_effect = lambda name, default=None: True if name == "polishing_enabled" else default
    storage.get_all_api_keys.return_value = {}
    monkeypatch.setattr(polisher_module, "storage", storage)
    monkeypatch.setattr(polisher_module, "_apply_dictionary_with_trace", lambda text, trace: text)
    engine = polisher_module.TextPolisher()
    provider = Mock(return_value=None)
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider)
    outcomes = []
    source = r"Please check HTTPClient at https://Example.com/CaseSensitive and C:\Work\CaseFile.txt today"
    result = engine.polish(source, "very_casual lowercase", "cleanup_light", force_ai=True,
                           model_ref="test/unavailable", outcome_callback=outcomes.append)
    assert result == r"please check HTTPClient at https://Example.com/CaseSensitive and C:\Work\CaseFile.txt today"
    provider.assert_called_once()
    assert outcomes == ["provider_failure"]


def test_ordinary_titlecase_and_spoken_words_still_lowercase():
    assert lowercase_prose_text("Please Check The Report Today. HELLO World!") == "please check the report today. hello world!"
    assert not is_protected_literal("Today")
    assert not is_protected_literal("HELLO")
    assert lowercase_prose_text("Check HTTPClient, parseJSON! Today.") == "check HTTPClient, parseJSON! today."
    assert polisher_module.TextPolisher._deterministic_cleanup(
        "Please Check The Report Today.", "very_casual lowercase", "cleanup_light"
    ) == "please check the report today"


def test_final_style_pass_preserves_acronym_identifiers_and_file_paths():
    source = r"Please check HTTPClient and parseJSON at https://Example.com/CaseSensitive from C:\Work\CaseFile.txt today."
    result = smart_format(source, "developer_very_casual")
    assert result == r"please check HTTPClient and parseJSON at https://Example.com/CaseSensitive from C:\Work\CaseFile.txt today"
