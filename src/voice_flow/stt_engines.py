"""Cloud speech-to-text adapters for Voice Flow.

`transcribe_cloud(audio, model_ref)` routes a 16 kHz mono float32 buffer to the
selected provider model ("provider/model_id") and returns the transcript.
Selection is stored independently as `voice_flow_stt_model` (default stays the
bundled local faster-whisper model). Any adapter failure raises STTError so the
caller can fall back to local whisper — dictation must never die.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

import requests
from requests.adapters import HTTPAdapter

log = logging.getLogger(__name__)


class STTError(RuntimeError):
    pass


def _deadline_timeout(deadline: float | None, timeout: float) -> float:
    """Clamp one blocking network/process timeout to an absolute deadline."""
    if deadline is None:
        return float(timeout)
    remaining = float(deadline) - time.monotonic()
    if remaining <= 0.0:
        raise STTError("STT deadline exceeded")
    return min(float(timeout), remaining)


def _to_wav_bytes(audio, sample_rate: int = 16000) -> bytes:
    import numpy as np

    if isinstance(audio, bytes) and audio.startswith(b"RIFF"):
        return audio

    # np.clip leaves NaN/Inf untouched and the int16 cast below turns them
    # into garbage samples; quarantine before encoding.
    arr = np.nan_to_num(np.asarray(audio, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if arr.ndim > 1:
        arr = np.mean(arr, axis=1).astype(np.float32)
    else:
        arr = arr.flatten()

    frames = np.clip(arr, -1.0, 1.0)
    pcm_bytes = (frames * 32767.0).astype("<i2").tobytes()
    num_bytes = len(pcm_bytes)

    # Canonical 44-byte WAV header: zero disk I/O, fast in-memory buffer
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + num_bytes,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        num_bytes,
    )
    return header + pcm_bytes


def _to_flac_bytes(wav_bytes: bytes, deadline: float | None = None) -> bytes | None:
    """Compress 16-bit PCM WAV to FLAC to cut cloud upload time (~50% for speech).

    Small buffers skip conversion entirely: a sub-second ffmpeg spawn costs
    more than the bytes it saves on a short chunk, and the tail chunk of a
    short dictation pays that cost after the button release.

    Returns None when ffmpeg is unavailable or conversion fails, so callers
    transparently fall back to raw WAV upload.
    """
    import os
    import shutil
    import subprocess
    import tempfile

    # ~8s of 16 kHz 16-bit mono audio (32 KB/s).
    FLAC_MIN_WAV_BYTES = 262144
    if len(wav_bytes) < FLAC_MIN_WAV_BYTES:
        return None

    ffmpeg = None
    try:
        from voice_flow import runtime_env

        candidate = getattr(runtime_env, "ffmpeg_executable", None)
        if callable(candidate):
            ffmpeg = candidate()
    except Exception:
        ffmpeg = None
    if not ffmpeg:
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        timeout = _deadline_timeout(deadline, 30.0)
    except STTError:
        # Compression is optional.  Let the caller make its own bounded cloud
        # attempt (or fall back locally) instead of spending more time here.
        return None

    # In-memory pipe fast path: skips disk writes completely
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", "pipe:0", "-c:a", "flac", "-f", "flac", "pipe:1"],
            input=wav_bytes,
            capture_output=True,
            timeout=timeout,
            creationflags=creation_flags,
        )
        if proc.returncode == 0 and proc.stdout and len(proc.stdout) < len(wav_bytes):
            return proc.stdout
    except Exception:
        pass

    # The pipe attempt can consume most or all of an interactive deadline.
    # Never give the disk fallback its original 30-second timeout.
    try:
        timeout = _deadline_timeout(deadline, 30.0)
    except STTError:
        return None

    src_path = os.path.join(
        tempfile.gettempdir(),
        # pid + ns suffix: the whole-buffer pipeline thread and the streaming
        # worker can upload concurrently, and a ms-resolution timestamp alone
        # collides — one call would then convert/delete the other's temp file.
        f"vf_stt_{os.getpid()}_{time.time_ns()}.wav",
    )
    dst_path = src_path[:-4] + ".flac"
    try:
        with open(src_path, "wb") as fh:
            fh.write(wav_bytes)
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", src_path, "-c:a", "flac", dst_path],
            capture_output=True,
            timeout=timeout,
            creationflags=creation_flags,
        )
        if proc.returncode != 0 or not os.path.exists(dst_path):
            return None
        with open(dst_path, "rb") as fh:
            return fh.read()
    except Exception:
        return None
    finally:
        for path in (src_path, dst_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


def _key_for(provider: str) -> str:
    from voice_flow.storage import storage

    for getter in ("get_provider_connections", "get_audio_provider_connections"):
        try:
            rows = getattr(storage, getter)(provider) or []
        except Exception:
            rows = []
        for row in rows:
            if row.get("api_key") and row.get("is_active"):
                return str(row["api_key"])
        # Deliberately NO fallback to inactive rows: a user who toggles a
        # broken/dead connection OFF expects it to stop being used — falling
        # back to rows[0] would keep sending requests with a dead key.
    try:
        keys = storage.get_all_api_keys() or {}
        if keys.get(provider):
            return str(keys[provider])
    except Exception:
        pass
    raise STTError(f"No API key connected for {provider}. Add one on the Providers page.")


def _multipart(fields: dict, files: dict) -> tuple[str, bytes]:
    boundary = "----vfboundary" + str(int(time.time() * 1000))
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fname, data, ctype) in files.items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return boundary, body.getvalue()


_session_lock = threading.Lock()
_stt_session: requests.Session | None = None
_ORIGINAL_URLOPEN = urllib.request.urlopen


def _get_stt_session() -> requests.Session:
    global _stt_session
    if _stt_session is not None:
        return _stt_session
    with _session_lock:
        if _stt_session is not None:
            return _stt_session
        sess = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=30,
            # _send owns one explicit, deadline-aware reconnect attempt.
            # urllib3 retries happen below requests and can replay a POST
            # with the stale per-attempt timeout, multiplying release delay.
            max_retries=0,
            pool_block=False,
        )
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        sess.headers.update({"Connection": "keep-alive"})
        _stt_session = sess
        return _stt_session


_PROVIDER_ORIGINS = {
    "groq": "https://api.groq.com",
    "openai": "https://api.openai.com",
    "deepgram": "https://api.deepgram.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "google": "https://generativelanguage.googleapis.com",
    "elevenlabs": "https://api.elevenlabs.io",
    "assemblyai": "https://api.assemblyai.com",
    "speechmatics": "https://asr.api.speechmatics.com",
    "nvidia": "https://integrate.api.nvidia.com",
    "nvidia_nim": "https://integrate.api.nvidia.com",
}

_PREWARMED_TIMESTAMPS: dict[str, float] = {}
_PREWARM_LOCK = threading.Lock()
PREWARM_DEBOUNCE_SECONDS = 10.0


def prewarm_cloud_stt(model_ref_or_provider: str | None = None, force: bool = False) -> None:
    """Speculatively pre-warm TLS connection pool for cloud STT endpoints."""
    if not model_ref_or_provider:
        return
    provider = str(model_ref_or_provider).partition("/")[0].strip().lower()
    host = _PROVIDER_ORIGINS.get(provider)
    if not host:
        return

    def _do_prewarm() -> None:
        try:
            now = time.monotonic()
            with _PREWARM_LOCK:
                last_warmed = _PREWARMED_TIMESTAMPS.get(host, 0.0)
                if not force and (now - last_warmed < PREWARM_DEBOUNCE_SECONDS):
                    return
                _PREWARMED_TIMESTAMPS[host] = now

            session = _get_stt_session()
            session.head(host, timeout=3.5, headers=UA)
            log.debug("[STT] Pre-warmed TLS connection to %s", host)
        except Exception as exc:
            log.debug("[STT] Pre-warm to %s: %s", host, exc)

    threading.Thread(target=_do_prewarm, name=f"vf-prewarm-{provider}", daemon=True).start()


def _send(
    req: urllib.request.Request,
    timeout: float = 120,
    deadline: float | None = None,
) -> bytes:
    eff_timeout = _deadline_timeout(deadline, timeout)

    # Test-double compatibility: if urllib.request.urlopen was monkeypatched
    if urllib.request.urlopen is not _ORIGINAL_URLOPEN:
        try:
            with urllib.request.urlopen(req, timeout=eff_timeout) as response:
                return response.read()
        except STTError:
            raise
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            raise STTError(f"HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise STTError(f"Connection failed: {exc}") from exc

    # Production fast path: persistent keep-alive connection pool
    try:
        session = _get_stt_session()
        method = req.get_method() if hasattr(req, "get_method") else "POST"
        url = req.full_url if hasattr(req, "full_url") else str(req)
        headers = dict(req.header_items()) if hasattr(req, "header_items") else (dict(req.headers) if hasattr(req, "headers") else {})
        data = req.data if hasattr(req, "data") else None

        if "Connection" not in headers:
            headers["Connection"] = "keep-alive"

        for attempt in range(2):
            try:
                curr_timeout = _deadline_timeout(deadline, timeout)
                resp = session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=curr_timeout,
                )
                if not (200 <= resp.status_code < 300):
                    detail = resp.text[:300] if resp.text else ""
                    raise STTError(f"HTTP {resp.status_code}: {detail}")
                return resp.content
            except STTError:
                raise
            except requests.exceptions.Timeout as exc:
                if deadline is not None and time.monotonic() >= float(deadline) - 0.05:
                    raise STTError("STT deadline exceeded") from exc
                if attempt == 0 and (deadline is None or time.monotonic() < float(deadline) - 1.0):
                    continue
                raise STTError(f"Connection timed out: {exc}") from exc
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as exc:
                if attempt == 0 and (deadline is None or time.monotonic() < float(deadline) - 0.5):
                    log.debug("[STT] Connection drop/reset (%s); retrying on fresh socket...", exc)
                    continue
                raise STTError(f"Connection failed: {exc}") from exc
            except requests.exceptions.RequestException as exc:
                raise STTError(f"Connection failed: {exc}") from exc
    except STTError:
        raise
    except requests.exceptions.Timeout as exc:
        if deadline is not None and time.monotonic() >= float(deadline) - 0.05:
            raise STTError("STT deadline exceeded") from exc
        raise STTError(f"Connection timed out: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise STTError(f"Connection failed: {exc}") from exc
    except Exception as exc:
        # Graceful fallback to urllib.request.urlopen
        try:
            # Refresh the timeout after session setup/failure.  The session
            # path may have used significant time before reaching urllib.
            fallback_timeout = _deadline_timeout(deadline, timeout)
            with urllib.request.urlopen(req, timeout=fallback_timeout) as response:
                return response.read()
        except STTError:
            raise
        except urllib.error.HTTPError as h_exc:
            detail = ""
            try:
                detail = h_exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            raise STTError(f"HTTP {h_exc.code}: {detail}") from h_exc
        except Exception as u_exc:
            raise STTError(f"Connection failed: {u_exc}") from u_exc


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


def _groq(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    fields = {"model": model or "whisper-large-v3-turbo", "response_format": "json", "temperature": "0.0", "language": "en"}
    if vocabulary:
        fields["prompt"] = "Vocabulary: " + ", ".join(vocabulary) + "."
    boundary, body = _multipart(fields, {"file": (fname, data, ctype)})
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "Connection": "keep-alive", **UA},
    )
    return str(json.loads(_send(req, deadline=deadline)).get("text") or "")


def _openai(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    fields = {"model": model or "whisper-1", "response_format": "json", "temperature": "0.0", "language": "en"}
    if vocabulary:
        fields["prompt"] = "Vocabulary: " + ", ".join(vocabulary) + "."
    boundary, body = _multipart(fields, {"file": (fname, data, ctype)})
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "Connection": "keep-alive", **UA},
    )
    return str(json.loads(_send(req, deadline=deadline)).get("text") or "")


def _deepgram(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    model = model or "nova-3"
    url = f"https://api.deepgram.com/v1/listen?model={model}&smart_format=true&language=en"
    if vocabulary:
        # Nova-3 rejects the nova-2-era `keywords` parameter (HTTP 400
        # "Keywords are not supported for Nova-3"), which made every
        # vocabulary-biased request fail. `keyterm` is the supported
        # equivalent: one param per term, phrases allowed, no boost suffix.
        terms: list[str] = []
        for term in vocabulary:
            t = " ".join(str(term).split())
            if len(t) >= 3 and t.lower() not in [x.lower() for x in terms]:
                terms.append(t)
        for t in terms[:12]:
            url += f"&keyterm={urllib.parse.quote(t)}"
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Authorization": f"Token {key}", "Content-Type": ctype, "Accept": "application/json", "Connection": "keep-alive", **UA})
    data = json.loads(_send(req, deadline=deadline))
    # Defensive chain: a 200 with an unexpected shape is empty output,
    # not a provider failure worth tripping the breaker.
    _channels = (data.get("results") or {}).get("channels") or [{}]
    _alts = (_channels[0] if isinstance(_channels[0], dict) else {}).get("alternatives") or [{}]
    return str((_alts[0] if isinstance(_alts[0], dict) else {}).get("transcript") or "")


def _deepgram_flux(audio, key: str, model: str, vocabulary: list[str] | None = None,
                   poll_seconds: int = 300, deadline: float | None = None) -> str:
    """Run Deepgram Flux over v2 WebSocket and return only a complete turn."""
    try:
        import numpy as np
        from websockets.sync.client import connect
    except ImportError as exc:
        raise STTError("Deepgram Flux requires the 'websockets' package.") from exc

    selected_model = str(model or "flux-general-en").strip().lower()
    if selected_model not in {"flux-general-en", "flux-general-multi"}:
        raise STTError(f"Unsupported Deepgram Flux model '{model}'.")
    pcm = np.nan_to_num(np.asarray(audio, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    pcm_bytes = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    duration = len(pcm) / 16000.0
    # Flux can close a forced turn before trailing silence has advanced its
    # audio window.  Requiring the window to reach the end of the raw buffer
    # wrongly discards a valid forced final turn, while accepting an event that
    # ends before the last audible sample can lose spoken words.
    audible = np.flatnonzero(np.abs(pcm) > 0.002)
    required_audio_end = (int(audible[-1]) + 1) / 16000.0 if audible.size else duration
    query = [("model", selected_model), ("encoding", "linear16"), ("sample_rate", "16000"),
             ("eot_threshold", "1.0"), ("eot_timeout_ms", "60000")]
    seen_terms: set[str] = set()
    for term in vocabulary or []:
        normalized = " ".join(str(term).split())
        if normalized and normalized.casefold() not in seen_terms:
            seen_terms.add(normalized.casefold())
            query.append(("keyterm", normalized))
    url = "wss://api.deepgram.com/v2/listen?" + urllib.parse.urlencode(query)
    timeout = _deadline_timeout(deadline, min(float(poll_seconds), 30.0))
    websocket = None
    completed_turns: dict[int, str] = {}
    try:
        websocket = connect(url, additional_headers={"Authorization": f"Token {key}"},
                            open_timeout=timeout, close_timeout=min(2.0, timeout))
        # 2,560 raw bytes is 80ms at 16kHz mono linear16, Flux's recommended frame size.
        for offset in range(0, len(pcm_bytes), 2560):
            _deadline_timeout(deadline, timeout)
            websocket.send(pcm_bytes[offset:offset + 2560])
        websocket.send(json.dumps({"type": "ForceEndTurn"}))
        while True:
            message = websocket.recv(timeout=_deadline_timeout(deadline, timeout))
            if isinstance(message, bytes):
                continue
            try:
                payload = json.loads(message)
            except (TypeError, ValueError) as exc:
                raise STTError("Deepgram Flux returned an invalid message.") from exc
            kind = str(payload.get("type") or "")
            if kind == "Error":
                raise STTError(f"Deepgram Flux error: {payload.get('description') or payload.get('code') or 'unknown error'}")
            if kind == "Warning" and payload.get("code") == "FORCE_END_TURN_NO_ACTIVE_TURN":
                # This acknowledges no active turn, not transcript coverage.
                # The caller must retain its full-recording fallback.
                raise STTError("Deepgram Flux had no active turn to finalize.")
            if kind != "TurnInfo" or payload.get("event") != "EndOfTurn":
                continue
            transcript = str(payload.get("transcript") or "").strip()
            try:
                window_end = float(payload.get("audio_window_end"))
                turn_index = int(payload["turn_index"])
            except (TypeError, ValueError, KeyError) as exc:
                raise STTError("Deepgram Flux EndOfTurn was incomplete.") from exc
            if transcript:
                completed_turns[turn_index] = transcript
            completed_text = " ".join(completed_turns[index] for index in sorted(completed_turns))
            # Deepgram specifies that a manual EndOfTurn transcript reflects
            # every audio frame received before ForceEndTurn. audio_window_end
            # may lag that frame boundary, so it is not an additional gate.
            if str(payload.get("trigger") or "").casefold() == "manual":
                if not completed_text:
                    raise STTError("Deepgram Flux ended the final turn without a transcript.")
                return completed_text
            # A queued natural EndOfTurn can arrive after ForceEndTurn. It is
            # still partial unless it covers every audible sample. Trailing
            # silence need not be reflected in Flux's audio_window_end.
            if window_end + 0.10 < required_audio_end:
                continue
            # ForceEndTurn can legitimately close a trailing silent turn. Its
            # transcript is empty, but previously completed turns are final
            # once this event covers the last audible input sample.
            if not completed_text:
                raise STTError("Deepgram Flux ended the final turn without a transcript.")
            return completed_text
    except STTError:
        raise
    except Exception as exc:
        raise STTError(f"Deepgram Flux connection failed: {exc}") from exc
    finally:
        if websocket is not None:
            try:
                websocket.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                websocket.close()
            except Exception:
                pass


def _elevenlabs(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    boundary, body = _multipart({"model_id": model or "scribe_v1"},
                                {"file": (fname, data, ctype)})
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/speech-to-text", data=body, method="POST",
        headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "Connection": "keep-alive", **UA},
    )
    return str(json.loads(_send(req, deadline=deadline)).get("text") or "")


def _gemini_stt_generation_config(model: str) -> dict[str, object] | None:
    """Return only Gemini STT settings supported by the selected audio model."""
    name = str(model or "").casefold()
    if name.startswith("gemini-2.5-flash"):
        return {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0},
        }
    if name.startswith("gemini-3") and "flash" in name and "image" not in name:
        # Gemini 3.7/3.8 Flash require low as their smallest tier; prior
        # text/audio Flash models support minimal. Keep Pro and image models
        # untouched because these controls are not uniformly supported there.
        level = "low" if any(version in name for version in ("gemini-3.7", "gemini-3.8")) else "minimal"
        return {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingLevel": level},
        }
    return None


def _gemini(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    selected_model = str(model or "gemini-2.5-flash").strip()
    model = urllib.parse.quote(selected_model, safe="")
    instruction = "Transcribe this audio exactly. Return only the transcript text."
    if vocabulary:
        instruction = "Preferred spellings (use exact casing): " + ", ".join(vocabulary) + ". " + instruction
    request_body: dict[str, object] = {
        "contents": [{
            "parts": [
                {"text": instruction},
                {"inline_data": {"mime_type": ctype, "data": base64.b64encode(data).decode("ascii")}},
            ]
        }]
    }
    generation_config = _gemini_stt_generation_config(selected_model)
    if generation_config is not None:
        request_body["generationConfig"] = generation_config
    payload = json.dumps(request_body).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key, "Accept": "application/json", "Connection": "keep-alive", **UA})
    data = json.loads(_send(req, deadline=deadline))
    # Defensive parse: a blocked/safety-filtered answer comes back HTTP 200
    # with candidates == [] (or content absent) — return "" for local
    # fallback instead of raising.
    candidates = data.get("candidates") or []
    candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    if str(candidate.get("finishReason") or "").casefold() in {"safety", "max_tokens", "length"}:
        return ""
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    return " ".join(
        part["text"].strip()
        for part in parts
        if isinstance(part, dict) and not part.get("thought") and isinstance(part.get("text"), str) and part["text"].strip()
    ).strip()


def _assemblyai(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    upload_req = urllib.request.Request(
        "https://api.assemblyai.com/v2/uploads", data=data, method="POST",
        headers={"authorization": key, "Content-Type": "application/octet-stream", "Connection": "keep-alive", **UA},
    )
    upload_url = str(json.loads(_send(upload_req, deadline=deadline)).get("upload_url") or "")
    if not upload_url:
        raise STTError("AssemblyAI upload failed")
    body = json.dumps({
        "audio_url": upload_url,
        "speech_model": model if model and model.startswith(("universal", "conformer")) else "universal",
        "language_code": "en",
    }).encode()
    create_req = urllib.request.Request(
        "https://api.assemblyai.com/v2/transcripts", data=body, method="POST",
        headers={"authorization": key, "Content-Type": "application/json", "Connection": "keep-alive"},
    )
    transcript_id = str(json.loads(_send(create_req, deadline=deadline)).get("id") or "")
    if not transcript_id:
        raise STTError("AssemblyAI transcript creation failed")
    poll_deadline = time.monotonic() + poll_seconds
    if deadline is not None:
        poll_deadline = min(poll_deadline, deadline)
    poll_delay = 0.25
    while time.monotonic() < poll_deadline:
        poll_req = urllib.request.Request(
            f"https://api.assemblyai.com/v2/transcripts/{transcript_id}",
            headers={"authorization": key, "Connection": "keep-alive", **UA},
        )
        info = json.loads(_send(poll_req, timeout=30, deadline=poll_deadline))
        status = str(info.get("status") or "")
        if status == "completed":
            return str(info.get("text") or "")
        if status == "error":
            raise STTError(f"AssemblyAI error: {info.get('error')}")
        remaining = poll_deadline - time.monotonic()
        if remaining <= 0.0:
            break
        time.sleep(min(poll_delay, remaining))
        poll_delay = min(1.0, poll_delay * 2.0)
    raise STTError("AssemblyAI transcription timed out")


def _speechmatics(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    config = json.dumps({
        "type": "transcription",
        "transcription_config": {"language": "en", "operating_point": "enhanced"},
    })
    # Speechmatics multipart: config part carries name="config", audio part name="data_file"
    boundary = "----vfboundary" + str(int(time.time() * 1000))
    body = io.BytesIO()
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"config\"; filename=\"config.json\"\r\nContent-Type: application/json\r\n\r\n".encode())
    body.write(config.encode())
    body.write(b"\r\n")
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"data_file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
    body.write(data)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        "https://asr.api.speechmatics.com/v2/jobs", data=body.getvalue(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "Connection": "keep-alive", **UA},
    )
    job_id = str(json.loads(_send(req, deadline=deadline)).get("id") or "")
    if not job_id:
        raise STTError("Speechmatics job creation failed")
    poll_deadline = time.monotonic() + poll_seconds
    if deadline is not None:
        poll_deadline = min(poll_deadline, deadline)
    poll_delay = 0.25
    while time.monotonic() < poll_deadline:
        poll_req = urllib.request.Request(
            f"https://asr.api.speechmatics.com/v2/jobs/{job_id}",
            headers={"Authorization": f"Bearer {key}", "Connection": "keep-alive", **UA},
        )
        info = json.loads(_send(poll_req, timeout=30, deadline=poll_deadline))
        status = str((info.get("job") or {}).get("status") or "")
        if status == "done":
            text_req = urllib.request.Request(
                f"https://asr.api.speechmatics.com/v2/jobs/{job_id}/transcript?format=txt",
                headers={"Authorization": f"Bearer {key}", "Connection": "keep-alive"},
            )
            return _send(text_req, timeout=30, deadline=poll_deadline).decode("utf-8", errors="replace").strip()
        if status in ("expired", "rejected", "failed"):
            raise STTError(f"Speechmatics job {status}")
        remaining = poll_deadline - time.monotonic()
        if remaining <= 0.0:
            break
        time.sleep(min(poll_delay, remaining))
        poll_delay = min(1.0, poll_delay * 2.0)
    raise STTError("Speechmatics transcription timed out")


def _nvidia(data: bytes, key: str, model: str, fname: str = "audio.wav", ctype: str = "audio/wav", poll_seconds: int = 300, vocabulary: list[str] | None = None, deadline: float | None = None) -> str:
    model_name = model or "nvidia/parakeet-ctc-1.1b"
    fields = {"model": model_name, "response_format": "json"}
    if vocabulary:
        fields["prompt"] = "Vocabulary: " + ", ".join(vocabulary) + "."
    boundary, body = _multipart(fields, {"file": (fname, data, ctype)})
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/audio/transcriptions", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "Connection": "keep-alive", **UA},
    )
    return str(json.loads(_send(req, deadline=deadline)).get("text") or "")


_ADAPTERS = {
    "groq": _groq,
    "openai": _openai,
    "deepgram": _deepgram,
    "elevenlabs": _elevenlabs,
    "gemini": _gemini,
    "google": _gemini,
    "assemblyai": _assemblyai,
    "speechmatics": _speechmatics,
    "nvidia": _nvidia,
    "nvidia_nim": _nvidia,
}


def transcribe_cloud(
    audio,
    model_ref: str,
    poll_seconds: int = 300,
    vocabulary: list[str] | None = None,
    deadline: float | None = None,
) -> str:
    """Route a 16 kHz mono float32 buffer to the selected cloud STT model.

    ``vocabulary`` carries the user's dictionary terms so providers that
    support contextual biasing (Deepgram keywords, Whisper prompt, Gemini
    instruction) hear domain terms correctly — spec §33.
    """
    provider, _, model = str(model_ref or "").partition("/")
    provider = provider.strip().lower()
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise STTError(f"Provider '{provider}' does not support speech-to-text yet.")
    key = _key_for(provider)
    # Flux is a v2 WebSocket service, never a silent nova-3 batch substitute.
    if provider == "deepgram" and model.strip().lower().startswith("flux"):
        return _deepgram_flux(audio, key, model.strip(), vocabulary=vocabulary,
                              poll_seconds=poll_seconds, deadline=deadline)
    wav = _to_wav_bytes(audio)
    # Do not pass a new keyword to legacy test doubles when no deadline is in
    # use; the public no-deadline call remains byte-for-byte compatible.
    flac = _to_flac_bytes(wav, deadline=deadline) if deadline is not None else _to_flac_bytes(wav)
    if flac is not None and len(flac) < len(wav):
        payload, fname, ctype = flac, "audio.flac", "audio/flac"
    else:
        # No FLAC (ffmpeg missing/failed) means a multi-x larger upload that
        # can blow the join budget on long audio — make that visible.
        if len(wav) > 262144:
            log.warning("[STT] FLAC conversion unavailable; uploading raw WAV (%d bytes) — cloud call will be slower.", len(wav))
        payload, fname, ctype = wav, "audio.wav", "audio/wav"
    vocab = [str(v).strip() for v in (vocabulary or []) if v and str(v).strip()][:15]
    adapter_kwargs = {"poll_seconds": poll_seconds, "vocabulary": vocab}
    if deadline is not None:
        adapter_kwargs["deadline"] = deadline
    try:
        return str(adapter(payload, key, model.strip(), fname, ctype, **adapter_kwargs) or "").strip()
    except TypeError:
        return str(adapter(payload, key, model.strip()) or "").strip()
