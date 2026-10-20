"""v1.0.14: Video Flow names each video after its topic."""
from __future__ import annotations

from pathlib import Path

from voice_flow import video_flow_service as svc
from voice_flow.video_flow_engine.notebooklm.models import VideoArtifact


def test_heading_wins():
    text = "# The Science of Sleep\n\nSleep has four stages. Each one matters."
    assert svc._derive_video_title(text) == "The Science of Sleep"


def test_title_label_line():
    assert svc._derive_video_title("Notes from class\nTitle: Photosynthesis basics\nPlants use light.") == "Photosynthesis basics"


def test_short_first_line_is_a_heading():
    text = "How Black Holes Form\nA black hole forms when a massive star collapses."
    assert svc._derive_video_title(text) == "How Black Holes Form"


def test_filler_lead_is_removed_from_a_sentence():
    text = "In this article, we will explore the history of the Roman Empire and its fall. It lasted centuries."
    title = svc._derive_video_title(text)
    assert title.startswith("The history of the Roman Empire")
    assert not title.lower().startswith("in this article")


def test_long_sentence_is_cut_to_nine_words():
    text = "Quantum computers use qubits that can hold many states at once which changes everything."
    title = svc._derive_video_title(text)
    assert title.endswith("...")
    assert len(title.rstrip(".").split()) == 9


def test_empty_source_has_a_fallback():
    assert svc._derive_video_title("") == "Video Overview"


def test_notebooklm_title_is_used_only_when_real():
    assert svc._notebooklm_topic_title({"artifact": {"artifact_title": "  The Rise and Fall of Rome "}}) == "The Rise and Fall of Rome"
    assert svc._notebooklm_topic_title({"artifact": {"artifact_title": "Video Overview"}}) == ""
    assert svc._notebooklm_topic_title({"artifact": {"artifact_title": None}}) == ""
    assert svc._notebooklm_topic_title(None) == ""


def test_artifact_carries_the_notebooklm_title():
    art = VideoArtifact(notebook_id="n", task_id="t", artifact_id="t", status="completed", artifact_title="Sleep Explained")
    assert art.to_dict()["artifact_title"] == "Sleep Explained"


def test_provider_reads_the_artifact_title(monkeypatch):
    from voice_flow.video_flow_engine.notebooklm import provider as prov

    p = prov.NotebookLMVideoProvider.__new__(prov.NotebookLMVideoProvider)
    calls = []

    def fake_invoke(args, timeout=None, **_):
        calls.append(tuple(args))
        return {"id": "a1", "title": "How Vaccines Work", "status": "completed"}

    monkeypatch.setattr(p, "_invoke", fake_invoke, raising=False)
    assert p.artifact_title("nb1", "a1") == "How Vaccines Work"
    assert calls[0][:4] == ("artifact", "get", "a1", "--notebook")

    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(p, "_invoke", boom, raising=False)
    assert p.artifact_title("nb1", "a1") is None


def test_composer_no_longer_reuses_a_stale_first_line():
    src = (Path(svc.__file__).parent / "video_flow_widget.py").read_text(encoding="utf-8")
    assert 'first_line = source_txt.strip().split("\\n")[0].strip()[:60]' not in src
    assert 'self._controls["title"].set("")' in src


def test_queue_marks_auto_titles_and_complete_renames(tmp_path, monkeypatch):
    """Blank title -> title_auto; NotebookLM's title replaces it on completion."""
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert '"title_auto": title_auto' in src
    assert 'meta_updates["title"] = topic_title' in src
    assert '(current.meta or {}).get("title_auto")' in src
