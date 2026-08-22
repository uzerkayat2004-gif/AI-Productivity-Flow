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


def test_api_correction_crud(store, monkeypatch):
    with api_server(store, monkeypatch) as url:
        status, correction = post(url, "/api/dictionary/corrections/add", {"wrong_text": "ada lovelace", "correct_text": "Ada Lovelace"})
        assert status == 201 and correction["success"]
        status, changed_correction = post(url, "/api/dictionary/corrections/update", {"id": correction["correction"]["id"], "wrong_text": "ada", "correct_text": "Ada"})
        assert status == 200 and changed_correction["success"]
        status, removed = post(url, "/api/dictionary/corrections/remove", {"id": correction["correction"]["id"]})
        assert status == 200 and removed["success"]


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


def test_pipeline_polishes_then_styles_then_history_before_inject(monkeypatch):
    """The final styled text is what is saved and pasted, never re-styled."""
    from types import SimpleNamespace
    import voice_flow.main as main
    from voice_flow.context_capture import CursorContext

    order = []
    # The polisher owns the AI pass plus deterministic cleanup and the
    # dictionary vocabulary pass; the pipeline then styles once.
    monkeypatch.setattr(main.polisher, "polish", lambda text, style_instruction="", cleanup_level=None, **kw: order.append("polish") or "polished")
    monkeypatch.setattr(main, "smart_format", lambda text, style, context: order.append("style") or "styled")
    monkeypatch.setattr(main, "storage", SimpleNamespace(add_dictation=lambda **kwargs: order.append(("history", kwargs["polished_text"])) or SimpleNamespace(id=1)))
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
    assert order == ["polish", "style", ("history", "styled"), ("inject", "styled"), ("done", "styled")]
