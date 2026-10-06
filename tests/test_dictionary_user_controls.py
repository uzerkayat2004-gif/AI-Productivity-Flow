"""Dictionary UI API contract tests using an isolated loopback database."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine


@pytest.fixture
def dictionary_api(monkeypatch, tmp_path):
    store = StorageEngine(str(tmp_path / "dictionary-controls.db"))
    monkeypatch.setattr(api_server, "storage", store)
    monkeypatch.setattr(api_server.dictionary_engine, "store", store)
    api_server.dictionary_engine.mark_dirty()
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.VoiceFlowApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", store
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def request_json(url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "Connection": "close"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_add_saves_term_and_heard_as_together(dictionary_api):
    url, store = dictionary_api
    status, result = request_json(url, "/api/dictionary/add", {"word": "HyperKube", "heard_as": "Hyper cube"})

    assert status == 200 and result["success"] is True
    assert "HyperKube" in store.get_dictionary_words()
    assert any(item["wrong_text"] == "Hyper cube" and item["correct_text"] == "HyperKube"
               for item in store.get_dictionary_corrections())


def test_heard_as_conflict_fails_without_saving_the_term(dictionary_api):
    url, store = dictionary_api
    store.add_dictionary_correction("Hyper cube", "SomeOtherTerm")

    status, result = request_json(url, "/api/dictionary/add", {"word": "HyperKube", "heard_as": "Hyper cube"})

    assert status == 409 and result["success"] is False
    assert "HyperKube" not in store.get_dictionary_words()
    assert store.get_dictionary_corrections()[0]["correct_text"] == "SomeOtherTerm"


def test_add_rejects_invalid_optional_heard_as_before_writing(dictionary_api):
    url, store = dictionary_api
    status, result = request_json(url, "/api/dictionary/add", {"word": "HyperKube", "heard_as": "x" * 121})

    assert status == 400 and result["success"] is False
    assert "HyperKube" not in store.get_dictionary_words()


def test_ignoring_legacy_capture_keeps_it_stored_and_hides_it_from_review(dictionary_api):
    url, store = dictionary_api
    assert store.add_dictionary_word("legacy-junk", category="Auto-Captured")

    status, result = request_json(url, "/api/dictionary/ignore", {"word": "legacy-junk"})
    raw_status, raw_entries = request_json(url, "/api/dictionary?details=1&include_auto=1")
    review_status, review_entries = request_json(url, "/api/dictionary?details=1&include_auto=1&review=1")

    assert status == 200 and result["success"] is True
    assert raw_status == review_status == 200
    assert any(entry["word"] == "legacy-junk" for entry in raw_entries)
    assert not any(entry["word"] == "legacy-junk" for entry in review_entries)
