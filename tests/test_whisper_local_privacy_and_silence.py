"""Local Whisper: no network once the model exists, no "You" from silence.

Mac QA 2026-10-16 evidence (voice_a2 / voice_b2):

* every Nemotron->Whisper fallback did
  ``GET https://huggingface.co/api/models/Systran/faster-whisper-base.en/revision/main``
  because the lazy fallback built ``WhisperModel("base.en")`` without
  ``local_files_only``;
* 17/24 streamed dictations ended in a stray "You" ("See you tomorrow You.",
  "Thanks you.") because the final streaming chunk was pure trailing silence
  decoded without VAD.
"""
from __future__ import annotations

import socket
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from voice_flow import transcriber as T

SR = 16000


# -- 1. privacy: resolve the on-disk model, never ask the hub ---------------

def _snapshot(tmp_path: Path, complete: bool = True) -> Path:
    snap = tmp_path / "hub" / "models--Systran--faster-whisper-base.en" / "snapshots" / "3d3d5de"
    snap.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json") + (("vocabulary.txt",) if complete else ()):
        (snap / name).write_bytes(b"x")
    return snap


@pytest.fixture
def no_network(monkeypatch):
    attempts: list[object] = []

    def refuse(self, address):
        attempts.append(address)
        raise OSError(f"network forbidden in local-only dictation: {address}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


def test_bundled_model_directory_wins(monkeypatch, tmp_path, no_network):
    bundled = tmp_path / "runtime" / "models" / "whisper" / "base.en"
    bundled.mkdir(parents=True)
    from voice_flow import runtime_env

    monkeypatch.setattr(runtime_env, "whisper_model_path", lambda: bundled)
    assert T.resolve_local_whisper_model("base.en") == (str(bundled), True)
    assert no_network == []


def test_cached_snapshot_resolves_to_its_directory_offline(monkeypatch, tmp_path, no_network):
    snap = _snapshot(tmp_path)
    from voice_flow import runtime_env
    import huggingface_hub

    monkeypatch.setattr(runtime_env, "whisper_model_path", lambda: None)
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache",
                        lambda repo, name, **k: str(snap / name) if repo == "Systran/faster-whisper-base.en" else None)
    assert T.resolve_local_whisper_model("base.en") == (str(snap), True)
    assert no_network == []


def test_incomplete_or_missing_snapshot_is_the_one_time_download(monkeypatch, tmp_path):
    snap = _snapshot(tmp_path, complete=False)
    from voice_flow import runtime_env
    import huggingface_hub

    monkeypatch.setattr(runtime_env, "whisper_model_path", lambda: None)
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda repo, name, **k: str(snap / name))
    assert T.resolve_local_whisper_model("base.en") == ("base.en", False)
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda repo, name, **k: None)
    assert T.resolve_local_whisper_model("tiny.en") == ("tiny.en", False)


class _RecordingWhisper:
    calls: list[tuple[str, dict]] = []

    def __init__(self, ref, **kwargs):
        self.ref = str(ref)
        self.decodes: list[dict] = []
        _RecordingWhisper.calls.append((self.ref, kwargs))

    def transcribe(self, audio, **kwargs):
        self.decodes.append(kwargs)
        return [SimpleNamespace(text="hello world", words=None)], None


def _bare() -> T.Transcriber:
    tr = object.__new__(T.Transcriber)
    tr.model = None
    tr.nemotron_engine = None
    tr._loading = False
    tr._loaded_model_ref = None
    tr._loading_model_ref = None
    tr._lock = threading.Lock()
    tr._transcribe_lock = threading.Lock()
    tr._whisper_models = {}
    return tr


def test_primary_loader_passes_local_directory_with_local_files_only(monkeypatch, tmp_path):
    _RecordingWhisper.calls = []
    monkeypatch.setattr(T, "WhisperModel", _RecordingWhisper)
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(T, "resolve_local_whisper_model", lambda name: (str(tmp_path / name), True))
    _bare()._load_model_bg("base.en")
    assert _RecordingWhisper.calls == [(str(tmp_path / "base.en"), {
        "device": T.config.device, "compute_type": T.config.compute_type,
        "cpu_threads": T.config.cpu_threads, "local_files_only": True,
    })]


def test_nemotron_whisper_fallback_never_reaches_the_hub(monkeypatch, tmp_path):
    """The per-dictation fallback (voice_b2 log lines 520/541) loads offline."""
    _RecordingWhisper.calls = []
    monkeypatch.setattr(T, "WhisperModel", _RecordingWhisper)
    monkeypatch.setattr(T, "resolve_local_whisper_model", lambda name: (str(tmp_path / "snap"), True))
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda ref: "nemotron" in str(ref))
    tr = _bare()
    tr.nemotron_engine = SimpleNamespace(is_warm=True, fatal_error=None, transcribe=lambda *a, **k: "")
    monkeypatch.setattr(tr, "_local_model_name", lambda ref=None: "nemotron-speech-streaming-en-0.6b")
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    t = np.arange(SR * 2) / SR
    audio = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert tr._transcribe_local(audio) == "hello world"
    assert _RecordingWhisper.calls and all(kw.get("local_files_only") is True for _ref, kw in _RecordingWhisper.calls)
    assert _RecordingWhisper.calls[0][0] == str(tmp_path / "snap")


# -- 2. silence hallucination -----------------------------------------------

def test_silent_streaming_chunk_is_not_decoded(monkeypatch):
    model = _RecordingWhisper("x")
    tr = _bare()
    tr.model = model
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_local_model_name", lambda ref=None: "base.en")
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "_speech_regions", lambda audio, params: [])
    assert tr._transcribe_local(np.zeros(int(SR * 1.5), dtype=np.float32), is_chunk=True) == ""
    assert model.decodes == []
    # Room-noise level tail (inaudible) is skipped too.
    noise = (np.random.default_rng(0).standard_normal(int(SR * 1.5)) * 0.0005).astype(np.float32)
    assert tr._transcribe_local(noise, is_chunk=True) == ""
    assert model.decodes == []


def test_streaming_chunk_trailing_silence_is_trimmed_before_decode(monkeypatch):
    seen: list[int] = []

    class Model(_RecordingWhisper):
        def transcribe(self, audio, **kwargs):
            seen.append(int(audio.size))
            return [SimpleNamespace(text="See you tomorrow.", words=None)], None

    tr = _bare()
    tr.model = Model("x")
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_local_model_name", lambda ref=None: "base.en")
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "_speech_regions", lambda audio, params: [(1600, SR)])
    audio = np.full(SR * 3, 0.2, dtype=np.float32)
    assert tr._transcribe_local(audio, is_chunk=True) == "See you tomorrow."
    assert seen == [SR + int(T._CHUNK_TAIL_PAD_SECONDS * SR)]


def test_trim_keeps_leading_audio_and_never_extends():
    audio = np.ones(SR * 2, dtype=np.float32)
    assert T._trim_chunk_trailing_silence(audio, [(8000, 12000)], SR).size == 12000 + int(0.25 * SR)
    assert T._trim_chunk_trailing_silence(audio, [(0, SR * 2)], SR).size == SR * 2
    assert T._trim_chunk_trailing_silence(audio, None, SR).size == SR * 2


def test_real_silero_hears_no_speech_in_silence():
    pytest.importorskip("faster_whisper")
    assert T._speech_regions(np.zeros(int(SR * 1.5), dtype=np.float32), {"threshold": 0.2}) == []


# Evidence strings (voice_a2 bundled-stt-polish-on): text, word placed after speech.
@pytest.mark.parametrize("text,phrase_start,expected", [
    ("See you tomorrow You", 1.9, "See you tomorrow"),
    ("Thanks you", 1.4, "Thanks"),
    ("My agenda for today. You", 2.0, "My agenda for today."),
    ("We discussed pricing, the launch date, and hiring, You.", 3.0, "We discussed pricing, the launch date, and hiring"),
    ("I paid 500 rupees for 2 tickets at 3pm. You", 2.6, "I paid 500 rupees for 2 tickets at 3pm."),
    ("Skrahoel and an aniote review the draft you", 2.8, "Skrahoel and an aniote review the draft"),
])
def test_trailing_you_decoded_in_silence_is_removed(text, phrase_start, expected):
    speech_end = 1.2
    regions = [(0, int(speech_end * SR))]
    words = [(w, 0.1 * i, 0.1 * i + 0.1) for i, w in enumerate(text.split()[:-1])] + [(text.split()[-1], phrase_start, phrase_start + 0.2)]
    assert T.strip_silent_tail_hallucination(text, regions, 3.5, words, SR) == expected


@pytest.mark.parametrize("text,words", [
    # Spoken inside the speech region: a real "Thank you." / "I will call you."
    ("Thank you.", [("Thank", 0.2, 0.5), ("you.", 0.55, 0.9)]),
    ("I will call you.", [("I", 0.1, 0.2), ("will", 0.2, 0.4), ("call", 0.4, 0.7), ("you.", 0.75, 1.1)]),
    ("Thanks for watching.", [("Thanks", 0.1, 0.4), ("for", 0.4, 0.6), ("watching.", 0.6, 1.1)]),
])
def test_spoken_you_inside_speech_is_kept(text, words):
    assert T.strip_silent_tail_hallucination(text, [(0, int(1.2 * SR))], 3.5, words, SR) == text


def test_guard_needs_silent_tail_regions_and_timestamps():
    words = [("See", 0.0, 0.2), ("you", 0.2, 0.4), ("tomorrow", 0.4, 0.9), ("You", 1.5, 1.7)]
    text = "See you tomorrow You"
    # Tail not silent (speech runs to the end).
    assert T.strip_silent_tail_hallucination(text, [(0, int(1.9 * SR))], 2.0, words, SR) == text
    # VAD unavailable / no word timestamps -> never remove anything.
    assert T.strip_silent_tail_hallucination(text, None, 3.0, words, SR) == text
    assert T.strip_silent_tail_hallucination(text, [(0, int(1.0 * SR))], 3.0, None, SR) == text
    # Ordinary text that does not end in a hallucination phrase is untouched.
    assert T.strip_silent_tail_hallucination("Send it today.", [(0, SR)], 3.0, words, SR) == "Send it today."


def test_whole_output_hallucination_on_pure_silence_is_dropped():
    assert T.strip_silent_tail_hallucination("You", [], 1.5, None, SR) == ""
    assert T.strip_silent_tail_hallucination("Thank you.", [], 1.5, None, SR) == ""


def test_guard_runs_a_word_timestamp_pass_only_for_candidates(monkeypatch):
    calls: list[dict] = []

    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append(kwargs)
            words = [SimpleNamespace(word=" Thanks", start=0.1, end=0.5), SimpleNamespace(word=" you", start=1.6, end=1.8)]
            return [SimpleNamespace(text="Thanks you", words=words)], None

    audio = np.zeros(int(SR * 2.5), dtype=np.float32)
    regions = [(0, int(0.8 * SR))]
    out = T.Transcriber._guard_tail_hallucination(Model(), audio, "Thanks you", regions, None, None)
    assert out == "Thanks"
    assert calls and calls[0]["word_timestamps"] is True and calls[0]["vad_filter"] is False


def test_audible_chunk_vad_missed_is_decoded_but_pure_you_is_dropped(monkeypatch):
    class Model(_RecordingWhisper):
        def transcribe(self, audio, **kwargs):
            self.decodes.append(kwargs)
            return [SimpleNamespace(text="You", words=None)], None

    tr = _bare()
    tr.model = Model("x")
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_local_model_name", lambda ref=None: "base.en")
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "_speech_regions", lambda audio, params: [])
    audio = np.full(SR, 0.1, dtype=np.float32)
    assert tr._transcribe_local(audio, is_chunk=True) == ""
    assert len(tr.model.decodes) == 1
