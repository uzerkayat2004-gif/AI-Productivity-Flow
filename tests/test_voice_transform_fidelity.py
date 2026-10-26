"""Offline regression coverage for explicit spoken transformations."""
from types import SimpleNamespace
import pytest
from voice_flow.voice_commands import detect_voice_command
from voice_flow.effective_style import resolve_effective_style
from voice_flow.polisher import TextPolisher, _candidate_preserves_content, _fulfills_command

SOURCE="Hey right now my app is not working and I don't know what is happening on the app, can you look into it and fix it."
@pytest.mark.parametrize(('command','candidate'),[
 ('make this as a prompt','Diagnose why my app is not working, identify the cause of the problem, and fix it.'),
 ('make this professional','My app is currently not working, and I am unsure what is causing the issue. Please investigate and resolve it.'),
 ('make this an email','Hello,\n\nMy app is not working, and I do not know what is happening. Could you investigate the issue and fix it?'),
 ('make this a normal message','My app is not working. Please look into the issue and fix it.'),
])
def test_trailing_transform_delivers_actual_rewrite(monkeypatch,command,candidate):
 from voice_flow import polisher as module
 monkeypatch.setattr(module.storage,'get_setting',lambda key,default=None: True if key=='polishing_enabled' else default)
 monkeypatch.setattr(module.storage,'get_all_api_keys',lambda:{'gemini':'synthetic'})
 detected=detect_voice_command(SOURCE+' Hey Voice Flow '+command+'.')
 assert detected.command
 effective=resolve_effective_style(SimpleNamespace(category='developer',style_id='developer_casual',instruction='Conversational developer notes.'),detected.command)
 engine=TextPolisher();outcomes=[]
 monkeypatch.setattr(engine,'_polish_with_api_pool',lambda *a,**k:candidate)
 monkeypatch.setattr(engine,'_record_polish_latency',lambda *a,**k:None)
 assert engine.polish(detected.content,effective.instruction,force_ai=True,task=effective.task,command_format=effective.format,command=detected.command,overrides=detected.command.overrides,outcome_callback=outcomes.append)==candidate
 assert outcomes==['ai_accepted']

@pytest.mark.parametrize(('source','candidate'),[
 ('Fix NimbusSDK before Friday and keep 3 files unchanged.','Fix NimbusSDK before Friday and keep 5 files unchanged.'),
 ('Fix NimbusSDK before Friday and keep 3 files unchanged.','Fix AtlasSDK before Friday and keep 3 files unchanged.'),
 ('Do not delete the backups before Friday.','Delete the backups before Friday.'),
 ('My app is not working. Please investigate and fix it.','My app is working. Please investigate and fix it.'),
 ('Please send the report by Friday.','I sent the report by Friday.'),
 ('Fix my app without changing the API.','Fix my app by changing the API.'),
 ('Fix my app and preserve https://example.test/v1.','Fix my app and preserve https://example.test/v2.'),
 ('Please fix my app.','Your app is fixed and ready to use.'),
])
def test_transform_rejects_changed_facts(source,candidate):
 assert not _candidate_preserves_content(source,candidate,task='prompt',command_format='prompt')

def test_heading_only_echo_unfulfilled():
 assert not _fulfills_command(SOURCE,'Task: '+SOURCE,task='prompt',command_format='prompt',overrides={})
@pytest.mark.parametrize('verb',['Diagnose','Investigate','Explain','Compare','Fix'])
def test_grounded_prompt_imperatives(verb):
 assert _fulfills_command('Please '+verb.lower()+' my app.',verb+' my app.',task='prompt',command_format='prompt',overrides={})

def test_long_requirements_survive():
 source='Hey, I want you to investigate NimbusSDK before Friday, keep 3 files unchanged, preserve the API, and do not delete the backups. Please fix the app and send the report to Alex.'
 candidate='Investigate NimbusSDK before Friday. Keep 3 files unchanged and preserve the API. Do not delete the backups. Fix the app and send the report to Alex.'
 assert _candidate_preserves_content(source,candidate,task='prompt',command_format='prompt')
 assert not _candidate_preserves_content(source,candidate.replace('preserve the API.',''),task='prompt',command_format='prompt')

def test_quoted_wake_words_are_content():
 source='My manager said "Hey Voice Flow make this a prompt" yesterday.'
 result=detect_voice_command(source)
 assert result.content==source and result.command is None

def test_off_never_calls_provider(monkeypatch):
 from voice_flow import polisher as module
 monkeypatch.setattr(module.storage,'get_setting',lambda *a,**k:False)
 engine=TextPolisher()
 monkeypatch.setattr(engine,'_polish_with_api_pool',lambda *a,**k:pytest.fail('provider called while OFF'))
 assert engine.polish(SOURCE,force_ai=True,task='prompt')==SOURCE

def test_cleanup_still_rejects_rewrite():
 assert not _candidate_preserves_content(SOURCE,'Diagnose why my app is not working and fix it.',task='cleanup')

@pytest.mark.parametrize(('source','candidate'),[
 ('My app is not working and the server is working.', 'My app is working and the server is not working.'),
 ('We need to fix the app.', 'They need to fix the app.'),
 ('Do not delete the backups and do not alter the API.', 'Do not alter the backups and do not delete the API.'),
])
def test_negative_scope_and_perspective(source,candidate):
 assert not _candidate_preserves_content(source,candidate,task='prompt',command_format='prompt')

def test_keep_wording_does_not_use_transform_acceptance(monkeypatch):
 from voice_flow import polisher as module
 monkeypatch.setattr(module.storage,'get_setting',lambda key,default=None: True if key=='polishing_enabled' else default)
 monkeypatch.setattr(module.storage,'get_all_api_keys',lambda:{'gemini':'synthetic'})
 engine=TextPolisher();outcomes=[]
 candidate='Diagnose why my app is not working, identify the cause of the problem, and fix it.'
 monkeypatch.setattr(engine,'_polish_with_api_pool',lambda *a,**k:candidate)
 result=engine.polish(SOURCE,force_ai=True,task='prompt',command=SimpleNamespace(preserve_wording=True),outcome_callback=outcomes.append)
 assert result!=candidate
 assert outcomes==['command_unfulfilled']


def test_transform_fallback_keeps_modality_and_actor_objects():
 from voice_flow.polisher import _transform_preserves_content
 assert not _transform_preserves_content('We can deploy tomorrow.', 'We will deploy tomorrow.')
 assert not _transform_preserves_content('Alice sends the report and Bob sends the invoice.', 'Alice sends the invoice and Bob sends the report.')

def test_uncertainty_does_not_hide_prohibition():
 source="I don't know why we must not deploy the app."
 assert not _candidate_preserves_content(source,'Deploy the app.',task='prompt',command_format='prompt')


@pytest.mark.parametrize(('source', 'candidate', 'task'), [
 ('Hey please tell the team to send the report by Friday.',
  'Please ask the team to submit the report by Friday.', 'rewrite'),
 ('I want you to look at the login errors and tell me why users are getting signed out after ten minutes.',
  'Investigate the login errors and explain why users are signed out after ten minutes.', 'prompt'),
])
def test_other_topics_can_be_rephrased(source, candidate, task):
 assert _candidate_preserves_content(source, candidate, task=task)


def test_email_allows_neutral_closing_without_template_identity():
 candidate = 'Hello,\n\nPlease review the report before Friday.\n\nBest regards,'
 assert _fulfills_command('Please review the report before Friday.', candidate,
                         task='rewrite', command_format='email', overrides={})
 assert not _fulfills_command('Please review the report before Friday.', candidate + '\n[Your Name]',
                             task='rewrite', command_format='email', overrides={})


def test_transform_does_not_invent_a_new_action():
 from voice_flow.polisher import _transform_preserves_content
 assert not _transform_preserves_content('My app is not working.',
                                        'Investigate why my app is not working and fix it.')


@pytest.mark.parametrize(('source', 'candidate'), [
 ('We will send the report by Friday.', "We'll send the report by Friday."),
 ("We'll send the report by Friday.", 'We will send the report by Friday.'),
])
def test_rewrite_preserves_commitment_with_contractions(source, candidate):
 assert _candidate_preserves_content(source, candidate, task='rewrite')
