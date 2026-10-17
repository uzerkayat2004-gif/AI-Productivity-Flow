"""Whisper must not paste one sentence ten times on boosted room noise.

The fresh-install log decoded base.en with beam=1 and a single temperature,
then pasted "I'm not sure if you have any questions." ten times. These tests
pin the repetition guard, the decode settings, the quiet-chunk stream rule,
and the gain cap that used to turn a 0.07 peak into a 0.75 hallucination.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_flow import downloadable_models
from voice_flow import transcriber as T
from voice_flow.stt_guard import (
    WHISPER_TEMPERATURES,
    guard_transcript,
    prefer_cleaner_transcript,
    repeated_sentence,
)
from voice_flow.stream_stt import StreamTranscriber
from voice_flow.voice_enhance import enhance_for_stt

SR = 16000


@pytest.fixture
def temp_models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr(downloadable_models, "get_models_dir", lambda: models)
    return models
HALLUCINATION = " ".join(["I'm not sure if you have any questions."] * 10)
ROOT = Path(__file__).resolve().parents[1]


def test_exact_repeated_sentence_is_dropped():
    phrase, count = repeated_sentence(HALLUCINATION)
    assert phrase == "i'm not sure if you have any questions"
    assert count == 10
    cleaned, retry = guard_transcript(HALLUCINATION, low_energy=True)
    assert cleaned == ""
    assert retry is True
    # The same loop is dropped even when the buffer is loud: ten copies
    # are not something the user said.
    cleaned_loud, retry_loud = guard_transcript(HALLUCINATION, low_energy=False)
    assert cleaned_loud == ""
    assert retry_loud is True


def test_known_phrase_on_quiet_audio_is_dropped_and_real_speech_is_kept():
    dropped, retry = guard_transcript("Thank you for watching.", low_energy=True)
    assert dropped == "" and retry is True
    kept, retry_kept = guard_transcript("Thank you for watching the demo with me.", low_energy=False)
    assert kept.startswith("Thank you for watching")
    assert retry_kept is False


def test_non_hallucination_loop_collapses_to_one_copy():
    loop = "The meeting is at noon. The meeting is at noon. The meeting is at noon."
    cleaned, retry = guard_transcript(loop)
    assert cleaned.count("The meeting is at noon.") == 1
    assert retry is True


def test_cleaner_stream_wins_only_when_the_full_decode_loops():
    streamed = "Ship the Lenovo notes today."
    assert prefer_cleaner_transcript(streamed, HALLUCINATION) == streamed
    assert prefer_cleaner_transcript(streamed, streamed) == streamed
    assert prefer_cleaner_transcript(HALLUCINATION, HALLUCINATION) == ""


def _noise(seconds: float, peak: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(int(SR * seconds)).astype(np.float32)
    scale = peak / max(float(np.max(np.abs(noise))), 1e-9)
    return (noise * np.float32(scale)).astype(np.float32)


def _speech_clip(seconds: float = 0.6, peak: float = 0.35) -> np.ndarray:
    t = np.arange(int(SR * seconds), dtype=np.float32) / SR
    envelope = np.hanning(t.size).astype(np.float32)
    return (peak * envelope * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)


def _fixture_audio() -> np.ndarray:
    """Room noise with one short voiced burst in the middle."""
    audio = _noise(3.2, 0.07, seed=11)
    speech = _speech_clip()
    start = int(SR * 1.2)
    audio[start:start + speech.size] += speech
    return audio


class _FakeWhisper:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls: list[dict] = []

    def transcribe(self, _audio, **kwargs):
        self.calls.append(kwargs)
        text = self.texts.pop(0) if self.texts else ""
        if not text:
            return [], None
        return [SimpleNamespace(text=text, words=None)], None


def _transcriber(model) -> T.Transcriber:
    tr = object.__new__(T.Transcriber)
    tr.model = model
    tr.nemotron_engine = None
    tr._loading = False
    tr._lock = threading.Lock()
    tr._transcribe_lock = threading.Lock()
    tr._whisper_models = {}
    tr._cloud_stt_breakers = {}
    return tr


def _assert_anti_hallucination_kwargs(kwargs: dict) -> None:
    temps = tuple(kwargs["temperature"])
    assert temps == WHISPER_TEMPERATURES
    assert kwargs["beam_size"] == 5
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["compression_ratio_threshold"] == pytest.approx(2.4)
    assert kwargs["log_prob_threshold"] == pytest.approx(-1.0)
    assert kwargs["no_speech_threshold"] == pytest.approx(0.6)
    assert kwargs["hallucination_silence_threshold"] == pytest.approx(2.0)
    assert kwargs["word_timestamps"] is True
    prompt = kwargs["initial_prompt"]
    assert prompt is None or str(prompt).startswith("Names and terms:")


def test_pipeline_retries_repeated_sentence_and_keeps_the_speech(monkeypatch):
    model = _FakeWhisper([HALLUCINATION, "Ship the Lenovo notes today."])
    tr = _transcriber(model)
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "dictionary_bias_terms", lambda limit=50: [])

    text = tr._transcribe_impl(_fixture_audio(), model_ref="local/faster-whisper-base.en")

    assert "I'm not sure if you have any questions" not in text
    assert text == "Ship the Lenovo notes today."
    assert len(model.calls) == 2
    _assert_anti_hallucination_kwargs(model.calls[0])
    assert tuple(model.calls[1]["temperature"])[0] == pytest.approx(0.2)
    assert model.calls[1]["beam_size"] == 1


def test_low_energy_empty_decode_does_not_run_the_vad_fallback(monkeypatch):
    """The 3.8s far chunk (peak 0.0702) used to take the unfiltered fallback."""
    model = _FakeWhisper([""])
    tr = _transcriber(model)
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "dictionary_bias_terms", lambda limit=50: [])

    text = tr._transcribe_impl(_noise(3.8, 0.0702, seed=3), model_ref="local/faster-whisper-base.en")

    assert text == ""
    assert len(model.calls) == 1
    assert model.calls[0]["vad_filter"] is True


def test_retry_that_also_loops_is_not_pasted(monkeypatch):
    model = _FakeWhisper([HALLUCINATION, HALLUCINATION])
    tr = _transcriber(model)
    monkeypatch.setattr(T.nemotron_engine, "is_nemotron_model", lambda _ref: False)
    monkeypatch.setattr(tr, "_wait_for_model", lambda *a, **k: True)
    monkeypatch.setattr(T, "dictionary_bias_terms", lambda limit=50: [])

    text = tr._transcribe_impl(_fixture_audio(), model_ref="local/faster-whisper-base.en")
    assert text == ""
    assert HALLUCINATION not in text


def test_quiet_empty_chunk_does_not_discard_the_rest_of_the_stream():
    class _QuietThenSpeech:
        def transcribe(self, audio, **_kwargs) -> str:
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak < 0.10:
                return ""
            return "Ship the Lenovo notes today."

    stream = StreamTranscriber(_QuietThenSpeech())
    stream.start_session()
    stream.submit_native(_noise(1.2, 0.07, seed=5), SR)
    stream.submit_native(np.full(SR, 0.4, dtype=np.float32), SR)
    stream.end_session()

    assert stream.collect(timeout=1.0) == "Ship the Lenovo notes today."
    assert stream.had_failures() is False


def test_loud_empty_chunk_is_still_a_stream_failure():
    class _LoudEmpty:
        def transcribe(self, _audio, **_kwargs) -> str:
            return ""

    stream = StreamTranscriber(_LoudEmpty())
    stream.start_session()
    stream.submit_native(np.full(SR, 1.0, dtype=np.float32), SR)
    stream.end_session()
    assert stream.collect(timeout=1.0) == ""
    assert stream.had_failures() is True


def test_stationary_noise_is_not_boosted_to_speech_level():
    noise = _noise(2.0, 0.07, seed=9)
    for profile in ("far", "auto", "normal"):
        out, used = enhance_for_stt(noise, profile=profile)
        peak = float(np.max(np.abs(out)))
        assert peak < 0.35, f"{profile} ({used}) boosted a 0.07 peak to {peak:.3f}"


def test_modulated_room_noise_is_not_lifted_to_speech_level():
    """The far-mic log boosted peak 0.0702 to 0.755. Modulation must not do that."""
    n = SR * 3
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(n).astype(np.float32)
    mod = (0.2 + 0.8 * (0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * np.arange(n) / SR))).astype(np.float32)
    noise *= mod
    noise *= np.float32(0.07 / max(float(np.max(np.abs(noise))), 1e-9))
    for profile in ("far", "auto"):
        out, used = enhance_for_stt(noise, profile=profile)
        peak = float(np.max(np.abs(out)))
        assert peak < 0.35, f"{profile} ({used}) boosted modulated noise to {peak:.3f}"


def _wait_status(model_id: str, wanted: str) -> dict:
    import time

    # The worker records "downloaded" and only then switches the active model.
    # Join it so the assertion does not race that second step.
    for thread in threading.enumerate():
        if thread.name == f"Download-{model_id}":
            thread.join(timeout=5)
    last = {}
    for _ in range(50):
        last = downloadable_models.get_model_status(model_id) or {}
        if last.get("status") == wanted:
            return last
        time.sleep(0.05)
    return last


def test_download_resumes_a_partial_file(temp_models_dir, monkeypatch):
    model_id = "nvidia/nemotron-speech-streaming-en-0.6b"
    spec = downloadable_models.get_model_spec(model_id)
    assert spec is not None
    prefix = b"ALREADY_ON_DISK" * 40
    rest = b"REMAINING_BYTES" * 80
    part = temp_models_dir / f"{spec['filename']}.part"
    part.write_bytes(prefix)
    total = len(prefix) + len(rest)

    response = MagicMock()
    response.status = 206
    response.headers.get.side_effect = lambda name, default=None: (
        str(len(rest)) if name == "Content-Length"
        else f"bytes {len(prefix)}-{total - 1}/{total}" if name == "Content-Range"
        else default
    )
    response.read.side_effect = [rest, b""]
    response.__enter__.return_value = response

    captured = []

    def _urlopen(req, timeout=60, context=None):
        captured.append(req)
        return response

    from voice_flow.storage import storage

    storage.save_setting("voice_flow_stt_model", "local/faster-whisper-base.en")
    monkeypatch.setattr(downloadable_models, "_maybe_repair_nemotron_tokenizer", lambda *a, **k: False)
    try:
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            ok, _msg, _st = downloadable_models.start_model_download(model_id)
            assert ok
            final = _wait_status(model_id, "downloaded")
    finally:
        downloadable_models._ACTIVE_DOWNLOADS.pop(model_id, None)

    assert captured, "download never opened a request"
    request = captured[0]
    range_header = request.get_header("Range") if hasattr(request, "get_header") else None
    assert range_header == f"bytes={len(prefix)}-", range_header
    assert final.get("status") == "downloaded", final.get("error") or final.get("status")
    target = temp_models_dir / spec["filename"]
    assert target.read_bytes() == prefix + rest
    assert not part.exists()
    assert storage.get_setting("voice_flow_stt_model") == "local/nemotron-speech-streaming-en-0.6b"


def test_sha256_mismatch_rejects_the_file_and_match_keeps_it(temp_models_dir, monkeypatch):
    model_id = "superwhisper/s1-mini-q4_k_m"
    original = next(item for item in downloadable_models.ALL_DOWNLOADABLE_MODELS_REGISTRY if item["id"] == model_id)
    saved = original.get("sha256")
    payload = b"POLISH_MODEL_BYTES" * 30
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(downloadable_models, "_maybe_repair_nemotron_tokenizer", lambda *a, **k: False)

    def _response(body: bytes):
        resp = MagicMock()
        resp.status = 200
        resp.headers.get.side_effect = lambda name, default=None: str(len(body)) if name == "Content-Length" else default
        resp.read.side_effect = [body, b""]
        resp.__enter__.return_value = resp
        return resp

    spec = downloadable_models.get_model_spec(model_id)
    assert spec is not None
    target = temp_models_dir / spec["filename"]
    part = temp_models_dir / f"{spec['filename']}.part"

    try:
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert downloadable_models.start_model_download(model_id)[0]
            failed = _wait_status(model_id, "failed")
        assert failed["status"] == "failed"
        assert "SHA-256" in str(failed.get("error"))
        assert not target.exists()
        assert not part.exists()

        downloadable_models._ACTIVE_DOWNLOADS.pop(model_id, None)
        original["sha256"] = digest
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            assert downloadable_models.start_model_download(model_id)[0]
            done = _wait_status(model_id, "downloaded")
        assert done["status"] == "downloaded"
        assert target.read_bytes() == payload
    finally:
        if saved is None:
            original.pop("sha256", None)
        else:
            original["sha256"] = saved
        downloadable_models._ACTIVE_DOWNLOADS.pop(model_id, None)


def test_voice_flow_notice_is_dismissible_and_on_brand():
    html = (ROOT / "src/voice_flow/gui/index.html").read_text(encoding="utf-8")
    css = (ROOT / "src/voice_flow/gui/workspace-ui.css").read_text(encoding="utf-8")
    script = (ROOT / "src/voice_flow/gui/app.js").read_text(encoding="utf-8")
    assert 'class="apf-notice' in html
    assert "vf-first-run-dismiss" in html
    assert "Download Nemotron (700 MB)" in html
    assert "vf-whisper-fallback-chip" in html
    assert "Whisper fallback · Download Nemotron" in html
    assert 'class="vf-first-run-models"' not in html
    assert 'class="action-btn" id="btn-download-nemotron"' not in html
    assert "#ff6b00" in css
    assert "#fff7f2" not in css.split(".apf-notice", 1)[1][:500]
    assert "apf.dismissedNotices" in script
    assert "function dismissApfNotice" in script
