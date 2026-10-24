from types import SimpleNamespace

import pytest

from voice_flow import polisher as polish_module
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("off_finalizer_helpers", Path(__file__).with_name("test_voice_command_finalization.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
finalizer = _helpers.finalizer


def off_finalize(monkeypatch, text, level="cleanup_light"):
    monkeypatch.setattr(polish_module.storage, "get_setting", lambda key, default=None: False if key == "polishing_enabled" else default)
    engine = polish_module.TextPolisher()
    def forbidden(*args, **kwargs):
        pytest.fail("OFF cleanup attempted model execution")
    monkeypatch.setattr(engine, "_polish_with_api_pool", forbidden)
    monkeypatch.setattr(polish_module.storage, "get_all_api_keys", forbidden)
    session = SimpleNamespace(cleanup_level=level, style_id="smart_clean", cursor_context=None,
                              polish_model_ref="gemini/synthetic", polish_speed_mode="quality")
    return finalizer(engine)._finalize_text(text, session)


@pytest.mark.parametrize(("source", "expected"), [
    ("umm, please send 12 files", "Please send 12 files."),
    ("uhhh, do not send it", "Do not send it."),
    ("hmmm, keep the final word", "Keep the final word."),
    ("Um. please send it", "Please send it."),
    ("uhh! send it now", "Send it now."),
    ("Keep the final word, umm", "Keep the final word."),
    ("Keep this. uh. do not remove the end", "Keep this. Do not remove the end."),
])
def test_off_hesitations_leave_clean_prose(monkeypatch, source, expected):
    assert off_finalize(monkeypatch, source) == expected


@pytest.mark.parametrize("source", [
    "Keep 12 mm and 5 um units",  # The ambiguous unit spellings are content.
    "I don't like it so so much",
    "Keep very very good and no no no",
    'Keep `umm` and "uhhh" and https://example.com/umm',
    "The ER and UM teams agree",
    "Keep 2.5 um and -3 um",
    "UM. Keep the ER report",
])
def test_off_preserves_content(monkeypatch, source):
    assert off_finalize(monkeypatch, source) == source + "."


def test_off_cleanup_none_is_verbatim(monkeypatch):
    source = "umm, i is keeping 12 mm and this ending"
    assert off_finalize(monkeypatch, source, "cleanup_none") == source


@pytest.mark.parametrize("source", [
    "If it were ready, we would ship it.",
    "I wish she were here.",
])
def test_off_preserves_subjunctive_grammar(monkeypatch, source):
    assert off_finalize(monkeypatch, source) == source


def test_off_keeps_unambiguous_plural_agreement_repair(monkeypatch):
    assert off_finalize(monkeypatch, "they was ready") == "They were ready."
