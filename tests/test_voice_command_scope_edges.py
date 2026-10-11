import pytest
from voice_flow.voice_commands import detect_voice_command

@pytest.mark.parametrize('suffix,scope,persistent', [('for my next dictation','next',False), ('from now on','current',True)])
@pytest.mark.parametrize('tail', ['', 'Hi Alex. Keep NimbusSDK ready.'])
def test_scope_suffix_consumed(suffix, scope, persistent, tail):
 result = detect_voice_command(f'Hey Voice Flow, make this casual {suffix}. {tail}')
 assert result.content == tail
 assert result.command.scope == scope
 assert result.command.persistent_change is persistent

@pytest.mark.parametrize('usual', ['', 'usual ', 'normal ', 'regular '])
def test_email_context_style_no_residue(usual):
 result = detect_voice_command(f'Hey Voice Flow, use my {usual}email style. Hi Alex.')
 assert result.content == 'Hi Alex.'
 assert result.command.context_reference == 'email'

@pytest.mark.parametrize('text', ['I said Hey Voice Flow, make this casual yesterday.', 'They mentioned Hey Voice Flow, make this formal.', 'We heard Hey Voice Flow, turn this into bullets.'])
def test_clear_attribution_retained(text):
 result = detect_voice_command(text)
 assert result.command is None
 assert result.content == text

@pytest.mark.parametrize('text,content', [
 ('Um, hey Voice Flow, make this casual. Hi Alex.', 'Hi Alex.'),
 ('Hi Alex. Hey Voice Flow, make this casual for my next dictation.', 'Hi Alex.'),
 ('Hey Voice Flow, make this casual for Alex tomorrow.', 'for Alex tomorrow.'),
 ('Hey Voice Flow, make this an email HTTPClient ships Friday.', 'HTTPClient ships Friday.'),
])
def test_legitimate_wake_and_payload_retained(text, content):
 result = detect_voice_command(text)
 assert result.command is not None
 assert result.content == content

@pytest.mark.parametrize('text', ['He wrote `Hey Voice Flow, make this casual.` in code.', 'I said "Hey Voice Flow, make this casual." yesterday.'])
def test_quoted_and_code_wakes_retained(text):
 result = detect_voice_command(text)
 assert result.command is None
 assert result.content == text
