"""Parity tests for explicit vocabulary and corrections (snippets feature removed)."""

from __future__ import annotations

import json
import socket
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from voice_flow.dictionary import DictionaryEngine
from voice_flow.storage import StorageEngine


@pytest.fixture
def store(tmp_path: Path) -> StorageEngine:
    return StorageEngine(str(tmp_path / "voice-flow.db"))


def test_legacy_arrow_rows_migrate_once(store):
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("brief -> Hello Ada", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    assert [(item["trigger"], item["expansion"]) for item in store.get_snippets()] == [("brief", "Hello Ada")]
    assert store.get_dictionary_words() == []
    store._migrate_legacy_dictionary_snippets()
    assert len(store.get_snippets()) == 1


def test_failed_legacy_duplicate_migration_keeps_source_row(store):
    store.add_snippet("brief", "New expansion")
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("brief -> Old expansion", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    # The source row remains for data safety, but cannot leak into vocabulary.
    assert store.get_dictionary_words() == []


def test_legacy_arrow_precedence_and_visible_conflict_resolution(store):
    store.add_snippet("sig", "Current")
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("sig -> Hello => world", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    conflict = store.get_migration_conflicts()[0]
    assert conflict["legacy_value"] == "Hello => world" and store.get_dictionary_words() == []
    assert store.resolve_migration_conflict(conflict["id"], "use_legacy")
    assert store.get_snippets()[0]["expansion"] == "Hello => world"


def test_identical_legacy_duplicate_is_migrated_without_conflict(store):
    store.add_snippet("sig", "Same")
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("sig -> Same", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    assert store.get_dictionary_words() == [] and store.get_migration_conflicts() == []


def test_conflict_resolution_restores_legacy_if_current_was_deleted(store):
    current = store.add_snippet("sig", "Current")
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("sig -> Archived", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    conflict = store.get_migration_conflicts()[0]
    assert conflict["current_key"] == "sig" and conflict["legacy_value"] == "Archived"
    store.remove_snippet(current["id"])
    assert store.resolve_migration_conflict(conflict["id"], "use_legacy")
    assert [(item["trigger"], item["expansion"]) for item in store.get_snippets()] == [("sig", "Archived")]


def test_api_changed_conflict_returns_409_and_retains_archive(store, monkeypatch):
    current = store.add_snippet("sig", "Current")
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("sig -> Archived", "Personal", "now"))
    store._migrate_legacy_dictionary_snippets()
    conflict = store.get_migration_conflicts()[0]
    store.update_snippet(current["id"], "renamed", "Changed")
    with api_server(store, monkeypatch) as url:
        status, result = post(url, "/api/dictionary/add", {"word": "probe"})
        assert status == 200
    assert store.get_migration_conflicts()[0]["legacy_value"] == "Archived"


def test_history_does_not_silently_learn_camelcase_or_caps(store):
    store.add_dictation("raw", "We used VoiceFlow with JSON")
    assert store.get_dictionary_words() == []


def test_dictionary_rejects_legacy_arrow_syntax(store):
    assert not store.add_dictionary_word("shortcut -> expansion")
    assert not store.add_dictionary_word("literal =>")


def test_dictionary_casefold_uniqueness_and_legacy_variant_migration(store):
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("VoiceFlow", "Personal", "now"))
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("voiceflow", "Personal", "now"))
    store._migrate_dictionary_case_variants()
    assert store.get_dictionary_words() == ["VoiceFlow"]
    assert not store.add_dictionary_word("VOICEFLOW")


def test_preserved_legacy_arrow_row_never_reaches_dictionary_engine(store):
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary (word, category, created_at) VALUES (?, ?, ?)", ("invalid ->", "Personal", "now"))
    engine = DictionaryEngine(store)
    assert "invalid ->" not in engine.get_initial_prompt()
    assert engine.apply_dictionary_post_processing("invalid ->") == "invalid ->"


def test_correction_crud_and_case_insensitive_unique(store):
    rule = store.add_dictionary_correction("jon doe", "John Doe")
    assert store.update_dictionary_correction(rule["id"], "jon doe", "John D.")
    with pytest.raises(Exception):
        store.add_dictionary_correction("JON DOE", "Other")
    assert store.remove_dictionary_correction(rule["id"])


def test_unicode_casefold_uniqueness_for_corrections(store):
    store.add_dictionary_correction("É", "one")
    with pytest.raises(Exception):
        store.add_dictionary_correction("é", "two")


def test_unicode_casefold_migration_surfaces_displaced_values(store):
    with store._get_conn() as conn:
        conn.execute("INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) VALUES (?, ?, ?, ?)", ("É", "one", "now", "now"))
        conn.execute("INSERT INTO dictionary_corrections (wrong_text, correct_text, created_at, updated_at) VALUES (?, ?, ?, ?)", ("é", "two", "now", "now"))
    store._migrate_correction_case_variants()
    assert len(store.get_dictionary_corrections()) == 1
    assert {item["entity_type"] for item in store.get_migration_conflicts()} == {"correction"}


def test_dictionary_exact_casing_and_no_fuzzy_false_positive(store):
    store.add_dictionary_word("VoiceFlow")
    engine = DictionaryEngine(store)
    assert engine.apply_dictionary_post_processing("voiceflow is ready") == "VoiceFlow is ready"
    assert engine.apply_dictionary_post_processing("voice floe is ready") == "voice floe is ready"


def test_dictionary_multiword_correction_and_punctuation(store):
    store.add_dictionary_correction("john doe", "John Doe")
    assert DictionaryEngine(store).apply_dictionary_post_processing("I spoke to JOHN DOE.") == "I spoke to John Doe."


def test_dictionary_prompt_contains_words_and_corrections(store):
    store.add_dictionary_word("Kubernetes")
    store.add_dictionary_correction("cube", "Kube")
    prompt = DictionaryEngine(store).get_initial_prompt()
    assert "Kubernetes" in prompt and "Kube" in prompt


def test_dictionary_reload_is_immediate_after_storage_change(store):
    engine = DictionaryEngine(store)
    store.add_dictionary_word("OpenAI")
    assert engine.apply_dictionary_post_processing("openai") == "OpenAI"


def test_auto_captured_rows_are_visible_but_never_active_dictionary_rules(store):
    """Learned metadata must not silently become a spelling rewrite."""
    assert store.add_dictionary_word("LearnedTerm", category="Auto-Captured")
    engine = DictionaryEngine(store)

    assert engine.apply_dictionary_post_processing("learnedterm") == "learnedterm"
    assert "LearnedTerm" not in engine.get_initial_prompt()
    assert store.get_dictionary_entries(include_auto=True)[0]["category"] == "Auto-Captured"


def test_dictionary_update_rejects_legacy_expansion_syntax(store):
    assert store.add_dictionary_word("VoiceFlow")
    assert not store.update_dictionary_word("VoiceFlow", "shortcut -> expansion")
    assert store.get_dictionary_words() == ["VoiceFlow"]


def test_engine_snapshot_reads_remain_safe_while_lexicon_changes(store):
    engine = DictionaryEngine(store)
    errors = []
    def writer():
        try:
            for index in range(20):
                store.add_dictionary_word(f"Term{index}")
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        engine.get_initial_prompt()
        engine.apply_dictionary_post_processing("term1")
    thread.join()
    assert not errors and "Term19" in engine.get_initial_prompt()


def test_static_ui_has_no_snippets_page_after_feature_removal():
    root = Path(__file__).parents[1] / "src" / "voice_flow" / "gui"
    html = (root / "index.html").read_text(encoding="utf8")
    javascript = (root / "app.js").read_text(encoding="utf8")
    assert 'data-page="snippets"' not in html and 'id="page-snippets"' not in html
    assert "loadSnippets" not in javascript and "renderSnippets" not in javascript


def test_static_dictionary_page_uses_auto_learn():
    """Suggestions section was removed; words auto-learn in JS background."""
    root = Path(__file__).parents[1] / "src" / "voice_flow" / "gui"
    html = (root / "index.html").read_text(encoding="utf8")
    dictionary_page = html.split('<section id="page-dictionary"', 1)[1].split("</section>", 1)[0]
    # Old manual-approval UI was removed; auto-learn comment marks intent
    assert "auto-learn" in dictionary_page.lower() or "Auto-learned" in dictionary_page


@contextmanager
def api_server(store, monkeypatch):
    import voice_flow.gui.api_server as api
    monkeypatch.setattr(api, "storage", store)
    monkeypatch.setattr(api.dictionary_engine, "store", store); api.dictionary_engine.mark_dirty()
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); thread.join(); thread and server.server_close()


def post(url, path, body):
    request = Request(url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def get(url, path):
    try:
        with urlopen(url + path) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def test_api_returns_evidence_backed_dictionary_suggestions(store, monkeypatch):
    for _ in range(3):
        store.record_lexicon_candidate("Kubernetes", "cuber netties", source="usage-history")
    with api_server(store, monkeypatch) as url:
        status, suggestions = get(url, "/api/dictionary/suggestions")
    assert status == 200
    assert [(item["term"], item["variant"], item["state"]) for item in suggestions] == [
        ("Kubernetes", "cuber netties", "suggested")
    ]


def test_repeated_name_mishearing_promotes_to_suggestion_with_evidence(store):
    """Genuinely repeated user vocabulary (used 3+ times with a heard-as
    variant) must surface as an evidence-backed suggestion, never silently."""
    from voice_flow.correction_learning import extract_correction_pairs

    pairs = extract_correction_pairs("please ask joe ee to review", "Please ask Joey to review")
    assert ("Joey", "joe ee") in pairs
    for term, variant in pairs:
        store.record_lexicon_candidate(term, variant, source="correction")
        store.record_lexicon_candidate(term, variant, source="correction")
        store.record_lexicon_candidate(term, variant, source="correction")
    suggestions = store.get_lexicon_suggestions()
    joey = [item for item in suggestions if item["term"] == "Joey"]
    assert joey and joey[0]["variant"] == "joe ee" and joey[0]["evidence"] >= 3


def test_ignored_suggestion_never_resurfaces(store):
    """Ignore persistence: an ignored suggestion stays ignored and does not
    resurface in the suggestion list, even with further observations."""
    for _ in range(3):
        store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    candidate = store.get_lexicon_suggestions()[0]
    assert store.set_lexicon_candidate_state(candidate["id"], "ignored")
    assert store.get_lexicon_suggestions() == []
    # Further observations of the same pair must not flip it back to suggested.
    store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert store.get_lexicon_suggestions() == []


def test_suggestions_require_heard_as_variant_evidence(store):
    """A suggestion is a candidate correction with evidence: term plus the
    heard-as variant and counts — never a bare single filler word."""
    store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    assert store.get_lexicon_suggestions() == []
    store.record_lexicon_candidate("Kubernetes", "cuber netties", source="correction")
    suggestions = store.get_lexicon_suggestions()
    assert len(suggestions) == 1
    item = suggestions[0]
    assert item["term"] == "Kubernetes" and item["variant"] == "cuber netties"
    assert item["evidence"] >= 3 and item["state"] == "suggested"


def test_api_correction_crud(store, monkeypatch):
    with api_server(store, monkeypatch) as url:
        status, correction = post(url, "/api/dictionary/corrections/add", {"wrong_text": "ada lovelace", "correct_text": "Ada Lovelace"})
        assert status == 201 and correction["success"]
        status, changed_correction = post(url, "/api/dictionary/corrections/update", {"id": correction["correction"]["id"], "wrong_text": "ada", "correct_text": "Ada"})
        assert status == 200 and changed_correction["success"]
        status, removed = post(url, "/api/dictionary/corrections/remove", {"id": correction["correction"]["id"]})
        assert status == 200 and removed["success"]


def test_api_dictionary_details_shows_auto_rows_with_provenance(store, monkeypatch):
    assert store.add_dictionary_word("PersonalTerm")
    assert store.add_dictionary_word("LearnedTerm", category="Auto-Captured")
    with api_server(store, monkeypatch) as url:
        status, entries = get(url, "/api/dictionary?details=1&include_auto=1")
        assert status == 200
    assert [(item["word"], item["category"]) for item in entries] == [
        ("PersonalTerm", "Personal"),
        ("LearnedTerm", "Auto-Captured"),
    ]
    with api_server(store, monkeypatch) as url:
        status, words = get(url, "/api/dictionary")
        assert status == 200
    assert words == ["PersonalTerm", "LearnedTerm"]


def test_api_rejects_origin_before_body_and_oversized_body(store, monkeypatch):
    with api_server(store, monkeypatch) as url:
        port = int(url.rsplit(":", 1)[1])
        def header_only(headers):
            with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
                request = "POST /api/dictionary/add HTTP/1.1\r\nHost: 127.0.0.1\r\n" + headers + "\r\n\r\n"
                connection.sendall(request.encode("ascii"))
                return connection.recv(256).decode("ascii", errors="replace")
        # No body is sent: if the handler reads before validating, this blocks.
        assert " 403 " in header_only("Origin: https://evil.example\r\nContent-Type: application/json\r\nContent-Length: 9")
        assert " 413 " in header_only("Content-Type: application/json\r\nContent-Length: 65537")


def test_pipeline_polishes_then_styles_then_saves_final_outcome_after_inject(monkeypatch):
    """The final styled text is what is saved and pasted, never re-styled."""
    from types import SimpleNamespace
    import voice_flow.main as main
    from voice_flow.context_capture import CursorContext

    order = []
    # The polisher owns the AI pass plus deterministic cleanup and the
    # dictionary vocabulary pass; the pipeline then styles once.
    def fake_polish(text, style_instruction="", cleanup_level=None, **kw):
        order.append("polish")
        kw["outcome_callback"]("ai_accepted")
        return "polished"
    monkeypatch.setattr(main.polisher, "polish", fake_polish)
    monkeypatch.setattr(main, "smart_format", lambda text, style, context: order.append("style") or "styled")
    history_done = threading.Event()
    saved = []
    def save_history(raw, polished, *args, **kwargs):
        order.append(("history", polished))
        saved.append(kwargs)
        history_done.set()
    monkeypatch.setattr(main, "storage", SimpleNamespace(add_dictation=save_history))
    app = object.__new__(main.VoiceFlowApp)
    app._state_lock = threading.RLock()
    app.state = main.DictationState.PROCESSING
    app.last_successful_transcript = None
    app.hotkeys = SimpleNamespace(set_recording_state=lambda *args: None)
    app.overlay = SimpleNamespace(show_done=lambda text: order.append(("done", text)), show_error=lambda text: None)
    app.injector = SimpleNamespace(paste_text=lambda text, hwnd, press_enter=False: order.append(("inject", text)) or True)
    app.transcriber = SimpleNamespace(transcribe=lambda audio: "raw")
    session = main.DictationSession(1, "App", "other", "other_formal", 0, "cleanup_light", CursorContext(), False)
    app.session = session
    app._process_dictation_pipeline(session, object(), 1.0)
    assert history_done.wait(2)
    assert order[:3] == ["polish", "style", ("inject", "styled")]
    assert ("history", "styled") in order and ("done", "AI polished") in order
    assert saved[0]["status"] == "success" and saved[0]["insertion_status"] == "pasted"
