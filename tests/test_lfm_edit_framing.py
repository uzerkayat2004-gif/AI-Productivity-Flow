"""Adapter framing regression; actual model quality is measured separately."""
from voice_flow.lfm_engine import _build_local_messages, _extract_transcript, _trusted_instruction
from voice_flow.polisher import POLISHER_SYSTEM_PROMPT, _command_system_prompt


def test_wrapped_cleanup_keeps_complete_style_and_literal_input():
    raw = 'can you restart the server after the backup finishes\nKeep "Input: value" exactly.'
    instruction = "Use complete sentences. Keep the user's technical terminology."
    wrapped = f"{POLISHER_SYSTEM_PROMPT}\n\nStyle instruction: {instruction}\n\n<input_transcript>\n{raw}\n</input_transcript>"
    transcript, policy = _extract_transcript(wrapped)
    trusted = _trusted_instruction("", policy)
    messages = _build_local_messages(transcript, trusted, policy)
    assert instruction in messages[0]["content"]
    assert messages[1]["content"] == f"Input: {raw}\nOutput:"
    assert "never answer" in messages[0]["content"]


def test_explicit_commands_do_not_receive_cleanup_examples():
    for task, instruction in (("rewrite", "Format as a bullet list."), ("prompt", "Create a prompt for an AI assistant.")):
        raw = "Keep Alex and Morgan. Retain 12 labels."
        messages = _build_local_messages(raw, instruction, _command_system_prompt(task, False))
        assert messages[1]["content"] == raw
        assert instruction in messages[0]["content"]
        assert "yesterday i goes home" not in messages[0]["content"]


def test_saved_email_profile_retains_existing_email_policy():
    messages = _build_local_messages("Hi Alex please send the report thanks Morgan.",
        "Format as a formal email draft.", POLISHER_SYSTEM_PROMPT)
    assert messages[1]["content"].startswith("Hi Alex")
    assert "yesterday i goes home" not in messages[0]["content"]
