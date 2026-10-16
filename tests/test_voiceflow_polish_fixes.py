"""Regression tests for the app-side Voice Flow polish fixes.

Covers: task-aware S1 output budget, no chunking of whole-text tasks,
task-aware validation and timeout on the S1 path, extra command-fulfilment
checks, saved-rule precedence and the global standing instruction.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from voice_flow import effective_style, polisher as polisher_mod, s1_engine
from voice_flow.polisher import TextPolisher, _fulfills_command, _local_model_timeout_seconds
from voice_flow.storage import storage


@pytest.fixture(autouse=True)
def _clean_settings():
    keys = ["style_standing_instruction", "style_email_extra", "style_work_extra", "style_other_extra"]
    saved = {k: storage.get_setting(k, "") for k in keys}
    for k in keys:
        storage.save_setting(k, "")
    yield
    for k, v in saved.items():
        storage.save_setting(k, v or "")


# ---------------------------------------------------------------- budget
def test_cleanup_budget_is_unchanged():
    assert s1_engine._s1_output_token_budget(100) == 178
    assert s1_engine._s1_output_token_budget(100, task="cleanup") == 178
    assert s1_engine._s1_output_token_budget(100, task="rewrite", overrides={"tone": "excited"}) == 178


def test_expanding_formats_get_more_room_and_summaries_shrink():
    assert s1_engine._s1_output_token_budget(100, task="rewrite", command_format="email") == 328
    assert s1_engine._s1_output_token_budget(100, task="rewrite", command_format="bullet_list") == 328
    assert s1_engine._s1_output_token_budget(100, task="rewrite", overrides={"length": "detailed"}) == 378
    assert s1_engine._s1_output_token_budget(100, task="summarize") == 148
    assert s1_engine._s1_output_token_budget(100, task="rewrite", overrides={"length": "short"}) == 148


class _FakeLLM:
    def __init__(self):
        self.calls = []

    def tokenize(self, data):
        return data.decode("utf-8").split()

    def __call__(self, prompt, **kwargs):
        self.calls.append(kwargs)
        return {"choices": [{"text": "ok", "finish_reason": "stop"}]}


def test_chunk_call_uses_task_budget_and_context_clamp():
    import time

    llm = _FakeLLM()
    words = " ".join(["word"] * 50)
    s1_engine._polish_chunk_with_s1(llm, words, "[c]", time.monotonic() + 30)
    s1_engine._polish_chunk_with_s1(llm, words, "[c]", time.monotonic() + 30, task="rewrite", command_format="email")
    assert llm.calls[0]["max_tokens"] == int(50 * 1.3) + 48
    assert llm.calls[1]["max_tokens"] == 50 * 2 + 128
    huge = " ".join(["word"] * 3000)
    s1_engine._polish_chunk_with_s1(llm, huge, "[c]", time.monotonic() + 30, task="rewrite", command_format="email")
    assert llm.calls[2]["max_tokens"] <= s1_engine._S1_CONTEXT_TOKENS - 3000


def test_whole_text_tasks_are_not_chunked():
    assert s1_engine._task_allows_chunking("cleanup", None)
    assert s1_engine._task_allows_chunking("rewrite", None)
    for task, fmt in [("summarize", None), ("prompt", None), ("rewrite", "email"),
                      ("rewrite", "bullet_list"), ("rewrite", "linkedin_post"), ("format", "note")]:
        assert not s1_engine._task_allows_chunking(task, fmt)


# ---------------------------------------------------------------- timeout
def test_local_timeout_is_task_aware():
    short = "send the report to Maya tomorrow"
    long = " ".join(["word"] * 320)
    assert _local_model_timeout_seconds(short, task="cleanup") == polisher_mod.AI_POLISH_REQUEST_TIMEOUT_SECONDS
    assert _local_model_timeout_seconds(short, task="rewrite", overrides={"tone": "excited"}) == 5.0
    assert _local_model_timeout_seconds(short, task="rewrite", command_format="email") == polisher_mod.AI_POLISH_LONG_TIMEOUT_SECONDS
    assert _local_model_timeout_seconds(long, task="cleanup") == polisher_mod.AI_POLISH_LONG_TIMEOUT_SECONDS


# ---------------------------------------------------------------- S1 path validation
@pytest.fixture
def s1_polisher(monkeypatch):
    storage.save_setting("polishing_enabled", True)
    engine = TextPolisher()
    seen = {"timeouts": [], "checks": []}
    monkeypatch.setattr(s1_engine, "is_s1_model_ref", lambda ref: str(ref).startswith("local/s1"))
    monkeypatch.setattr(s1_engine, "is_s1_downloaded", lambda: True)
    monkeypatch.setattr(s1_engine, "s1_can_handle", lambda **kwargs: True)

    def bridge(callback, timeout, deadline=None):
        seen["timeouts"].append(timeout)
        return callback(timeout)

    monkeypatch.setattr(engine, "_run_bridge_with_timeout", bridge)
    monkeypatch.setattr(engine, "_polish_with_api_pool", lambda *a, **k: pytest.fail("S1 must stay local"))
    real = s1_engine.normalization_preserves_content

    def check(source, candidate, **kwargs):
        seen["checks"].append(kwargs)
        return real(source, candidate, **kwargs)

    monkeypatch.setattr(s1_engine, "normalization_preserves_content", check)
    return engine, seen


def test_s1_command_is_validated_with_its_task(s1_polisher, monkeypatch):
    engine, seen = s1_polisher
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *a, **k: "Hello team,\n\nI can attend tomorrow.\n\nThanks,\nAlex")
    effective = SimpleNamespace(instruction="Email.", style_id="email_formal", category="email", format="email", task="rewrite")
    engine.polish("hello team I can attend tomorrow thanks Alex", effective, model_ref="local/s1-mini-q4_k_m",
                  task="rewrite", command_format="email")
    assert seen["checks"][-1]["task"] == "rewrite"
    assert seen["timeouts"][-1] == polisher_mod.AI_POLISH_LONG_TIMEOUT_SECONDS


def test_s1_cleanup_stays_on_strict_cleanup_gate(s1_polisher, monkeypatch):
    engine, seen = s1_polisher
    source = "i will send the report to maya tomorrow morning"
    monkeypatch.setattr(s1_engine, "polish_with_s1", lambda *a, **k: "I will send the report to Maya tomorrow morning, and also buy milk.")
    outcome = []
    result = engine.polish(source, "Format text.", model_ref="local/s1-mini-q4_k_m", task="cleanup",
                           outcome_callback=outcome.append)
    assert seen["checks"][-1]["task"] == "cleanup"
    assert seen["checks"][-1]["allow_compression"] is False
    assert seen["timeouts"][-1] == polisher_mod.AI_POLISH_REQUEST_TIMEOUT_SECONDS
    assert "milk" not in result
    assert outcome == ["fidelity_reject"]


# ---------------------------------------------------------------- fulfilment
def test_work_and_personal_messages_reject_email_furniture():
    src = "tell the team the build is green and we ship friday"
    assert _fulfills_command(src, "The build is green and we ship Friday.", task="rewrite", overrides={}, command_format="work_message")
    assert not _fulfills_command(src, "Subject: Build\nThe build is green.", task="rewrite", overrides={}, command_format="work_message")
    assert not _fulfills_command(src, "The build is green.\n\nBest regards", task="rewrite", overrides={}, command_format="personal_message")


def test_placeholders_are_never_a_finished_command():
    src = "write to the client that the invoice is paid"
    assert not _fulfills_command(src, "Hi [Recipient Name],\nThe invoice is paid.", task="rewrite", overrides={}, command_format="email")
    assert not _fulfills_command(src, "The invoice is paid. [Your Name]", task="rewrite", overrides={}, command_format="note")
    # Cleanup keeps whatever the user literally said.
    assert _fulfills_command("sign it [your name]", "Sign it [your name].", task="cleanup", overrides={}, command_format=None)


def test_summary_must_be_shorter_than_long_source():
    src = " ".join(["we discussed the launch plan and the budget for the next quarter in detail"] * 3)
    assert not _fulfills_command(src, src, task="summarize", overrides={}, command_format=None)
    assert _fulfills_command(src, "Launch plan and next-quarter budget.", task="summarize", overrides={}, command_format=None)
    assert _fulfills_command("short one", "short one", task="summarize", overrides={}, command_format=None)


def test_linkedin_echo_is_not_a_post():
    src = " ".join(f"point{i}" for i in range(45))
    assert not _fulfills_command(src, src, task="rewrite", overrides={}, command_format="linkedin_post")
    post = "Big news.\n\n" + src
    assert _fulfills_command(src, post, task="rewrite", overrides={}, command_format="linkedin_post")


# ---------------------------------------------------------------- precedence
def _base(category="email"):
    return SimpleNamespace(category=category, style_id=f"{category}_very_casual", instruction="Base.")


def test_register_override_keeps_unrelated_saved_rules():
    storage.save_setting("style_email_extra", "Always write in lowercase. Never use emoji.")
    command = SimpleNamespace(format=None, context_reference=None, overrides={"formality": "professional"},
                              operation="rewrite", preserve_wording=False, label=lambda: "")
    eff = effective_style.resolve_effective_style(_base(), command)
    assert "Never use emoji." in eff.instruction
    assert "lowercase" not in eff.instruction.lower()
    assert eff.style_id == "email_formal"


def test_without_register_override_all_saved_rules_apply():
    storage.save_setting("style_email_extra", "Always write in lowercase. Never use emoji.")
    command = SimpleNamespace(format=None, context_reference=None, overrides={"length": "short"},
                              operation="rewrite", preserve_wording=False, label=lambda: "")
    eff = effective_style.resolve_effective_style(_base(), command)
    assert "Always write in lowercase." in eff.instruction and "Never use emoji." in eff.instruction


def test_global_standing_instruction_is_delivered():
    storage.save_setting("style_standing_instruction", "Never use emoji.")
    plain = effective_style.resolve_effective_style(_base("other"), None)
    assert "Never use emoji." in plain.instruction
    command = SimpleNamespace(format="email", context_reference=None, overrides={},
                              operation="rewrite", preserve_wording=False, label=lambda: "")
    eff = effective_style.resolve_effective_style(_base("other"), command)
    assert "Never use emoji." in eff.instruction
    # S1 still declines what it cannot honour.
    assert not s1_engine.s1_can_handle(effective=eff, text="hello there", task=eff.task)


# ---------------------------------------------------------------- email command fallback
USER_EMAIL = ("He robot, I am emailing you this exec message because from two days I'm facing so many "
              "problems with grobot that its usage is not good so can you guys please look into this matter "
              "why my usage is not proper and all and can you fix my problems.")


def test_users_misheard_greeting_becomes_email_layout():
    from voice_flow.text_processing import format_email_command_fallback
    out = format_email_command_fallback(USER_EMAIL)
    assert out.startswith("Hey robot,\n\nI am emailing you")
    assert out.rstrip().endswith("fix my problems.")
    assert _fulfills_command(USER_EMAIL, out, task="rewrite", overrides={}, command_format="email")


@pytest.mark.parametrize("source,start", [
    ("Hey robot, please check my usage.", "Hey robot,\n\n"),
    ("Hi team, the build is green.", "Hi team,\n\n"),
    ("Hello Grok Bot, can you fix this.", "Hello Grok Bot,\n\n"),
])
def test_greetings_with_hey_and_multiword_names(source, start):
    from voice_flow.text_processing import format_email_command_fallback
    assert format_email_command_fallback(source).startswith(start)


def test_no_greeting_email_splits_sentences_without_inventing_words():
    from voice_flow.text_processing import format_email_command_fallback
    src = "The invoice is paid. Please confirm the receipt. Thanks for the quick turnaround."
    out = format_email_command_fallback(src)
    assert out == "The invoice is paid. Please confirm the receipt.\n\nThanks for the quick turnaround."
    assert format_email_command_fallback("Just one long sentence about the report") is None


def test_he_said_is_never_turned_into_a_greeting():
    from voice_flow.text_processing import format_dictated_email, format_email_command_fallback, cleanup_text
    assert format_email_command_fallback("He said, the build is broken") is None
    assert format_dictated_email("He robot, hi") is None  # strict helper unchanged
    assert "Hey" not in cleanup_text("He said, the build is broken", "cleanup_medium")


# ---------------------------------------------------------------- wake mishearings
USER_WHY_SLOW = ("He console team I have been using cursor from three days I have just purchased cursor pro "
                 "subscription three days ago and right now I am using it with like third party models "
                 "can you guys look into this matter and can you help me with this problem "
                 "hey why slow make this as a good email?")


def test_why_slow_trailing_email_command_is_detected():
    from voice_flow.voice_commands import detect_voice_command
    d = detect_voice_command(USER_WHY_SLOW)
    assert d.command is not None and d.command.format == "email"
    assert "why slow" not in d.content.lower() and "make this" not in d.content.lower()
    assert d.content.rstrip().endswith("problem")


@pytest.mark.parametrize("phrase", ["hey why slow", "hey voice slow", "hey boys flow", "ok voice flo", "hey nice flow"])
def test_wake_mishearings_with_command(phrase):
    from voice_flow.voice_commands import detect_voice_command
    d = detect_voice_command(f"please check the report today {phrase} make this an email")
    assert d.command is not None and d.command.format == "email"


@pytest.mark.parametrize("text", [
    "why slow is the app today",
    "hey why slow is the app today",
    "hey why slow the app is",
    "the boys flow through the hall",
    "hey nice flow on that track",
    "it feels like a voice slow motion clip",
])
def test_wake_mishearings_without_command_stay_dictation(text):
    from voice_flow.voice_commands import detect_voice_command
    d = detect_voice_command(text)
    assert d.command is None
    assert d.content == text


def test_why_slow_email_reaches_email_layout():
    from voice_flow.voice_commands import detect_voice_command
    from voice_flow.text_processing import format_email_command_fallback
    content = detect_voice_command(USER_WHY_SLOW).content
    cleaned = content.strip().rstrip("?") + "."
    out = format_email_command_fallback(cleaned)
    assert out is not None and out.startswith("Hey console team,\n\n")
    assert _fulfills_command(cleaned, out, task="rewrite", overrides={}, command_format="email")


def test_unpunctuated_he_greeting_never_matches_reported_speech():
    from voice_flow.text_processing import format_email_command_fallback
    assert format_email_command_fallback("He said I should send it") is None
    assert format_email_command_fallback("He team I have an update.").startswith("Hey team,\n\nI have")
