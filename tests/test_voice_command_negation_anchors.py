"""Provider rewrites must retain explicit negative actions and email requests."""
import pytest
from voice_flow.polisher import _candidate_preserves_content
from types import SimpleNamespace
from unittest.mock import Mock

def _finalize(monkeypatch, phrase, source, rewritten, enabled=True):
    from voice_flow import main, polisher as module
    from voice_flow.effective_style import resolve_effective_style
    from voice_flow.voice_commands import detect_voice_command
    detection = detect_voice_command(f"Hey Voice Flow, {phrase}. {source}")
    from voice_flow.style_engine import STYLE_INSTRUCTIONS
    base = SimpleNamespace(category="other", style_id="other_formal", instruction=STYLE_INSTRUCTIONS["other_formal"])
    effective = resolve_effective_style(base, detection.command)
    session = SimpleNamespace(cleanup_level="cleanup_light", style_id="other_formal", cursor_context=None,
                              polish_model_ref="test/provider", polish_speed_mode="balanced")
    settings = Mock()
    settings.get_setting.side_effect = lambda key, default=None: enabled if key == "polishing_enabled" else default
    settings.get_all_api_keys.return_value = {}
    monkeypatch.setattr(module, "storage", settings)
    monkeypatch.setattr(main, "_polishing_enabled", lambda: enabled)
    engine = module.TextPolisher()
    provider = Mock(return_value=rewritten)
    monkeypatch.setattr(engine, "_polish_with_api_pool", provider)
    monkeypatch.setattr(main, "polisher", engine)
    monkeypatch.setattr("voice_flow.lfm_engine.is_lfm_downloaded", lambda: False)
    monkeypatch.setattr(module, "_apply_dictionary_with_trace", lambda text, trace=None: text)
    monkeypatch.setattr(main.dictionary_engine, "restore_dictionary_spelling", lambda text: text)
    outcomes = []
    result = object.__new__(main.VoiceFlowApp)._finalize_text(detection.content, session, effective=effective,
        command=detection.command, outcome_callback=outcomes.append)
    print(f"Observed {phrase}: {result!r}; outcomes={outcomes}; provider_calls={provider.call_count}")
    return result, outcomes, provider


SOURCE = 'Hi Alex we was reviewing 12 orange folders and cannot remove 3 purple labels please send the updated report by Friday thanks Morgan'
UNSAFE = 'Hi Alex,\n\nWe were reviewing 12 orange folders. Please remove 3 purple labels. The updated report will be sent by Friday.\n\nThanks,\nMorgan'

@pytest.mark.parametrize('task,fmt', [('cleanup', None), ('rewrite', None), ('rewrite', 'email'), ('prompt', 'prompt')])
@pytest.mark.parametrize('negative', ['cannot', 'can not', "can't", 'can’t'])
def test_negative_can_action_cannot_vanish(task, fmt, negative):
    source = SOURCE.replace('cannot', negative)
    assert not _candidate_preserves_content(source, UNSAFE, task=task, command_format=fmt)

@pytest.mark.parametrize('negative', ['cannot', 'can not', "can't", 'can’t'])
def test_equivalent_negative_can_forms_are_safe(negative):
    source = 'We can not remove 3 purple labels while reviewing 12 orange folders.'
    candidate = f'We {negative} remove 3 purple labels while reviewing 12 orange folders.'
    assert _candidate_preserves_content(source, candidate, task='rewrite')

@pytest.mark.parametrize('literal', ['"cannot remove"', '`cannot remove`'])
def test_negative_modal_inside_literal_is_a_mention(literal):
    source = f'We review the phrase {literal} and can remove 3 purple labels.'
    candidate = f'We review the phrase {literal}. We can remove 3 purple labels.'
    assert _candidate_preserves_content(source, candidate, task='rewrite')

@pytest.mark.parametrize('claim', ['The updated report will be sent by Friday.', 'The updated report was sent by Friday.', 'I sent the updated report by Friday.', 'I will send the updated report by Friday.'])
def test_email_request_cannot_become_asserted_delivery(claim):
    source = 'Hi Alex please send the updated report by Friday thanks Morgan.'
    candidate = f'Hi Alex,\n\n{claim}\n\nThanks,\nMorgan.'
    assert not _candidate_preserves_content(source, candidate, task='rewrite', command_format='email')

@pytest.mark.parametrize('request_text', ['Please send the updated report by Friday.', 'Could you send the updated report by Friday?'])
def test_professional_email_request_rewording_remains_safe(request_text):
    source = 'Hi Alex please send the updated report by Friday thanks Morgan.'
    candidate = f'Hi Alex,\n\n{request_text}\n\nThanks,\nMorgan.'
    assert _candidate_preserves_content(source, candidate, task='rewrite', command_format='email')

def test_actual_finalize_rejects_native_negative_action_reversal(monkeypatch):
    result, outcomes, provider = _finalize(monkeypatch, 'make this an email', SOURCE, UNSAFE)
    assert provider.call_count == 1
    assert provider.call_args.kwargs["model_ref"] == "test/provider"
    assert 'ai_accepted' not in outcomes
    assert 'cannot remove 3 purple labels' in result



@pytest.mark.parametrize("negative", ["are unable to", "are not able to"])
def test_equivalent_unable_action_preserves_objects(negative):
    source = "We cannot remove 3 purple labels while reviewing 12 orange folders."
    candidate = f"We {negative} remove 3 purple labels while reviewing 12 orange folders."
    assert _candidate_preserves_content(source, candidate, task="rewrite")


def test_same_verb_negation_cannot_move_to_other_object():
    source = "We cannot remove 3 purple labels but we can remove 12 orange folders."
    candidate = "We can remove 3 purple labels but we cannot remove 12 orange folders."
    assert not _candidate_preserves_content(source, candidate, task="rewrite")


@pytest.mark.parametrize("request_text", ["Would you send the updated report by Friday?", "Send the updated report by Friday."])
def test_email_request_can_be_polite_or_imperative(request_text):
    source = "Hi Alex please send the updated report by Friday thanks Morgan."
    candidate = f"Hi Alex,\n\n{request_text}\n\nThanks,\nMorgan."
    assert _candidate_preserves_content(source, candidate, task="rewrite", command_format="email")



def test_existing_email_commitment_without_request_can_be_preserved():
    source = "Hi Alex the updated report will be sent by Friday thanks Morgan."
    candidate = "Hi Alex,\n\nThe updated report will be sent by Friday.\n\nThanks,\nMorgan."
    assert _candidate_preserves_content(source, candidate, task="rewrite", command_format="email")


def test_quoted_request_is_not_a_prose_request():
    source = 'Hi Alex the phrase "please send the report" is in the template and the report will be sent Friday thanks Morgan.'
    candidate = 'Hi Alex,\n\nThe phrase "please send the report" is in the template. The report will be sent Friday.\n\nThanks,\nMorgan.'
    assert _candidate_preserves_content(source, candidate, task="rewrite", command_format="email")



def test_unable_equivalent_with_separate_positive_same_verb_is_safe():
    source = "We cannot remove 3 purple labels but we can remove 12 orange folders."
    candidate = "We are unable to remove 3 purple labels but we can remove 12 orange folders."
    assert _candidate_preserves_content(source, candidate, task="rewrite")
