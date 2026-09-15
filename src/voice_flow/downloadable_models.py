"""Management, file tracking, and background download of local speech-to-text models."""
from __future__ import annotations

import logging
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from voice_flow import paths

log = logging.getLogger(__name__)


def format_mb(byte_count: int | float) -> float:
    """Format byte count into megabytes (float rounded to 1 decimal place)."""
    return round(float(byte_count) / (1024.0 * 1024.0), 1)


def format_speed(speed_bps: float) -> str:
    """Format bytes per second into human-readable speed string."""
    if speed_bps <= 0:
        return ""
    if speed_bps >= 1024.0 * 1024.0:
        return f"{speed_bps / (1024.0 * 1024.0):.1f} MB/s"
    return f"{speed_bps / 1024.0:.0f} KB/s"


def format_eta(eta_seconds: int | float) -> str:
    """Format estimated seconds remaining into a human readable ETA string."""
    if eta_seconds <= 0:
        return ""
    secs = int(eta_seconds)
    if secs < 60:
        return f"{secs}s left"
    mins = secs // 60
    rem_secs = secs % 60
    if mins < 60:
        return f"{mins}m {rem_secs}s left"
    hours = mins // 60
    rem_mins = mins % 60
    return f"{hours}h {rem_mins}m left"


def get_ssl_context() -> ssl.SSLContext:
    """Create a verified SSL context using certifi if available, falling back gracefully."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

DOWNLOADABLE_STT_MODELS_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "nvidia/nemotron-speech-streaming-en-0.6b",
        "name": "Nemotron Speech Streaming English 0.6B",
        "tag": "Speech-to-Text (STT)",
        "task": "stt",
        "category": "stt",
        "format": "Local GGUF",
        "size_mb": 700,
        "size_bytes": 699872960,
        "size_display": "700 MB",
        "repo_url": "https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b",
        "download_url": "https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/resolve/main/nemotron-speech-streaming-en-0.6b.q8_0.gguf",
        "filename": "nemotron-speech-streaming-en-0.6b.q8_0.gguf",
        "languages": ["English (en)"],
        "is_multilingual": False,
        "default_language": "en",
        "full_id": "local/nemotron-speech-streaming-en-0.6b",
        "description": "Speech-to-Text (STT) model: Official NVIDIA Nemotron FastConformer English streaming ASR model quantized to Q8_0 GGUF. Transcribes spoken voice into text in real-time.",
    },
    {
        "id": "nvidia/nemotron-3.5-asr-streaming-0.6b",
        "name": "Nemotron 3.5 ASR Streaming 0.6B",
        "tag": "Speech-to-Text (STT)",
        "task": "stt",
        "category": "stt",
        "format": "Local GGUF",
        "size_mb": 742,
        "size_bytes": 741548352,
        "size_display": "742 MB",
        "repo_url": "https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b",
        "download_url": "https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b/resolve/main/nemotron-3.5-asr-streaming-0.6b.q8_0.gguf",
        "filename": "nemotron-3.5-asr-streaming-0.6b.q8_0.gguf",
        "languages": [
            "English (en)", "Spanish (es)", "German (de)", "French (fr)", "Italian (it)",
            "Arabic (ar)", "Japanese (ja)", "Korean (ko)", "Portuguese (pt)", "Russian (ru)",
            "Hindi (hi)", "Chinese (zh)", "Vietnamese (vi)", "Hebrew (he)", "Dutch (nl)",
            "Czech (cs)", "Danish (da)", "Polish (pl)", "Norwegian (no)", "Swedish (sv)",
            "Thai (th)", "Turkish (tr)", "Bulgarian (bg)", "Greek (el)", "Estonian (et)",
            "Finnish (fi)", "Croatian (hr)", "Hungarian (hu)", "Lithuanian (lt)", "Latvian (lv)",
            "Romanian (ro)", "Slovak (sk)", "Ukrainian (uk)", "Maltese (mt)", "Slovenian (sl)"
        ],
        "is_multilingual": True,
        "default_language": "en",
        "full_id": "local/nemotron-3.5-asr-streaming-0.6b",
        "description": "Speech-to-Text (STT) model: Official NVIDIA Nemotron 3.5 multilingual streaming ASR model quantized to Q8_0 GGUF with 35 supported languages. Transcribes spoken voice into text in real-time.",
    },
]

DOWNLOADABLE_POLISH_MODELS_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "liquid/lfm2.5-350m-qad-q4_0",
        "name": "Liquid LFM 2.5 350M QAD",
        "tag": "Voice Polishing",
        "task": "voice_polishing",
        "category": "voice_polishing",
        "format": "Local GGUF (Q4_0)",
        "size_mb": 219,
        "size_bytes": 219312832,
        "size_display": "219 MB",
        "repo_url": "https://huggingface.co/LiquidAI/LFM2.5-350M-GGUF",
        "download_url": "https://huggingface.co/LiquidAI/LFM2.5-350M-GGUF/resolve/main/LFM2.5-350M-QAD-Q4_0.gguf",
        "filename": "LFM2.5-350M-QAD-Q4_0.gguf",
        "languages": ["English (en)", "Multilingual"],
        "is_multilingual": True,
        "default_language": "en",
        "full_id": "local/lfm2.5-350m-qad-q4_0",
        "description": "Voice Polishing model: Universal fallback tiny 350M local model for ultra-fast local disfluency cleanup (removing 'um', 'uh', hesitations) and grammatical polishing (219 MB). Specifically designed for text polishing after transcription, not for speech-to-text.",
    },
]

ALL_DOWNLOADABLE_MODELS_REGISTRY: list[dict[str, Any]] = [
    *DOWNLOADABLE_STT_MODELS_REGISTRY,
    *DOWNLOADABLE_POLISH_MODELS_REGISTRY,
]

# Backward compatibility alias for speech-to-text registry consumers and existing tests
DOWNLOADABLE_MODELS_REGISTRY: list[dict[str, Any]] = DOWNLOADABLE_STT_MODELS_REGISTRY

_STATE_LOCK = threading.Lock()
_ACTIVE_DOWNLOADS: dict[str, dict[str, Any]] = {}


def get_models_dir() -> Path:
    """Return local directory where downloaded models are stored."""
    target = paths.data_dir() / "models"
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_model_spec(model_id: str) -> dict[str, Any] | None:
    """Find model specification by model_id or full_id or filename."""
    norm = str(model_id or "").strip().lower()
    for m in ALL_DOWNLOADABLE_MODELS_REGISTRY:
        if (
            m["id"].lower() == norm
            or m["full_id"].lower() == norm
            or m["filename"].lower() == norm
            or norm.endswith(m["filename"].lower())
            or norm.endswith(m["id"].split("/")[-1].lower())
        ):
            return dict(m)
    return None


def get_model_status(model_id: str) -> dict[str, Any] | None:
    """Return status, progress, and file info for a single model."""
    spec = get_model_spec(model_id)
    if not spec:
        return None

    target_file = get_models_dir() / spec["filename"]
    file_exists = target_file.is_file() and target_file.stat().st_size > 0

    speed_bps = 0.0
    eta_seconds = 0
    speed_display = ""
    eta_display = ""

    with _STATE_LOCK:
        active = _ACTIVE_DOWNLOADS.get(spec["id"])
        if active and active.get("status") == "downloading":
            status = "downloading"
            progress = float(active.get("progress", 0.0))
            downloaded_bytes = int(active.get("downloaded_bytes", 0))
            total_bytes = int(active.get("total_bytes", spec["size_bytes"]))
            remaining_bytes = max(0, total_bytes - downloaded_bytes)
            speed_bps = float(active.get("speed_bps", 0.0))
            eta_seconds = int(active.get("eta_seconds", 0))
            speed_display = active.get("speed_display") or format_speed(speed_bps)
            eta_display = active.get("eta_display") or format_eta(eta_seconds)
            error = active.get("error")
        elif active and active.get("status") == "failed" and not file_exists:
            status = "failed"
            progress = 0.0
            downloaded_bytes = 0
            total_bytes = int(spec["size_bytes"])
            remaining_bytes = total_bytes
            error = active.get("error")
        elif file_exists:
            status = "downloaded"
            progress = 100.0
            downloaded_bytes = target_file.stat().st_size
            total_bytes = downloaded_bytes
            remaining_bytes = 0
            error = None
        else:
            status = "not_downloaded"
            progress = 0.0
            downloaded_bytes = 0
            total_bytes = int(spec["size_bytes"])
            remaining_bytes = total_bytes
            error = None

    downloaded_mb = format_mb(downloaded_bytes)
    total_mb = format_mb(total_bytes)
    remaining_mb = max(0.0, format_mb(remaining_bytes))

    spec["status"] = status
    spec["progress"] = progress
    spec["downloaded_bytes"] = downloaded_bytes
    spec["total_bytes"] = total_bytes
    spec["remaining_bytes"] = remaining_bytes
    spec["downloaded_mb"] = downloaded_mb
    spec["total_mb"] = total_mb
    spec["remaining_mb"] = remaining_mb
    spec["downloaded_display"] = f"{downloaded_mb:.1f} MB"
    spec["remaining_display"] = f"{remaining_mb:.1f} MB remaining"
    spec["speed_bps"] = speed_bps
    spec["speed_mbps"] = round(speed_bps / (1024.0 * 1024.0), 1)
    spec["speed_display"] = speed_display
    spec["eta_seconds"] = eta_seconds
    spec["eta_display"] = eta_display
    spec["local_path"] = str(target_file) if file_exists else None
    spec["file_exists"] = file_exists
    spec["error"] = error
    return spec


def get_all_models_status(
    category: str | None = None,
    include_polish: bool = False,
) -> list[dict[str, Any]]:
    """Return status for models in the registry, optionally filtered by category."""
    cat_norm = category.strip().lower() if category else None
    if cat_norm in ("all", "any"):
        target_registry = ALL_DOWNLOADABLE_MODELS_REGISTRY
    elif cat_norm in ("polish", "voice_polishing", "polishing"):
        target_registry = DOWNLOADABLE_POLISH_MODELS_REGISTRY
    elif cat_norm in ("stt", "speech_to_text"):
        target_registry = DOWNLOADABLE_STT_MODELS_REGISTRY
    elif include_polish:
        target_registry = ALL_DOWNLOADABLE_MODELS_REGISTRY
    else:
        target_registry = DOWNLOADABLE_MODELS_REGISTRY
    return [get_model_status(m["id"]) for m in target_registry]  # type: ignore[misc]


def get_downloaded_models(category: str | None = None) -> list[dict[str, Any]]:
    """Return models that are fully downloaded and ready for use, optionally filtered by category."""
    results = []
    cat_norm = category.strip().lower() if category else None
    for m in ALL_DOWNLOADABLE_MODELS_REGISTRY:
        if cat_norm:
            m_cat = str(m.get("category") or m.get("task") or "").lower()
            m_tag = str(m.get("tag") or "").lower()
            if cat_norm in ("stt", "speech_to_text") and not ("stt" in m_cat or "stt" in m_tag):
                continue
            if cat_norm in ("polish", "voice_polishing", "polishing") and not ("polish" in m_cat or "polish" in m_tag):
                continue
        status_info = get_model_status(m["id"])
        if status_info and status_info.get("status") == "downloaded" and status_info.get("file_exists"):
            results.append(status_info)
    return results


def get_downloaded_stt_models() -> list[dict[str, Any]]:
    """Return downloaded Speech-to-Text models."""
    return get_downloaded_models(category="stt")


def get_downloaded_polish_models() -> list[dict[str, Any]]:
    """Return downloaded Voice Polishing models."""
    return get_downloaded_models(category="voice_polishing")


def start_model_download(model_id: str) -> tuple[bool, str, dict[str, Any] | None]:
    """Trigger background download of a model."""
    spec = get_model_spec(model_id)
    if not spec:
        return False, f"Model '{model_id}' not found in registry", None

    target_file = get_models_dir() / spec["filename"]
    part_file = get_models_dir() / f"{spec['filename']}.part"

    with _STATE_LOCK:
        active = _ACTIVE_DOWNLOADS.get(spec["id"])
        if active and active.get("status") == "downloading":
            return True, "Download already in progress", get_model_status(spec["id"])

        if target_file.is_file() and target_file.stat().st_size > 0:
            return True, "Model already downloaded", get_model_status(spec["id"])

        cancel_event = threading.Event()
        start_time = time.time()
        _ACTIVE_DOWNLOADS[spec["id"]] = {
            "status": "downloading",
            "progress": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": spec["size_bytes"],
            "remaining_bytes": spec["size_bytes"],
            "speed_bps": 0.0,
            "speed_display": "",
            "eta_seconds": 0,
            "eta_display": "",
            "start_time": start_time,
            "error": None,
            "cancel_event": cancel_event,
        }

    thread = threading.Thread(
        target=_download_worker,
        args=(spec, target_file, part_file, cancel_event),
        name=f"Download-{spec['id']}",
        daemon=True,
    )
    thread.start()

    return True, "Download started", get_model_status(spec["id"])


def _handle_download_error(
    model_id: str,
    part_file: Path,
    expected_size: int,
    error_msg: str,
) -> None:
    """Helper to cleanly record download failure state and delete temporary part file."""
    if part_file.exists():
        try:
            part_file.unlink()
        except OSError:
            pass
    with _STATE_LOCK:
        _ACTIVE_DOWNLOADS[model_id] = {
            "status": "failed",
            "progress": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": expected_size,
            "remaining_bytes": expected_size,
            "speed_bps": 0.0,
            "speed_display": "",
            "eta_seconds": 0,
            "eta_display": "",
            "error": error_msg,
            "cancel_event": None,
        }


def _download_worker(
    spec: dict[str, Any],
    target_file: Path,
    part_file: Path,
    cancel_event: threading.Event,
) -> None:
    """Worker function to stream download from Hugging Face into a .part file."""
    model_id = spec["id"]
    download_url = spec["download_url"]
    expected_size = spec["size_bytes"]

    log.info("[DOWNLOAD] Starting download for %s from %s", model_id, download_url)

    if cancel_event.is_set():
        log.info("[DOWNLOAD] Download for %s was cancelled before starting.", model_id)
        return

    req = urllib.request.Request(
        download_url,
        headers={
            "User-Agent": "VoiceFlow-Desktop/1.0 (Windows NT 10.0; Win64; x64) Mozilla/5.0",
            "Accept": "*/*",
        },
    )

    try:
        # If a partial file already exists from a previous crash, delete it to ensure clean download
        if part_file.exists():
            try:
                part_file.unlink()
            except OSError:
                pass

        if cancel_event.is_set():
            return

        ssl_ctx = get_ssl_context()
        # urllib.request.urlopen handles 301, 302, 303, 307, 308 redirects automatically.
        try:
            resp = urllib.request.urlopen(req, timeout=60, context=ssl_ctx)
        except ssl.SSLError as ssl_err:
            log.warning("[DOWNLOAD] Verified SSL handshake failed (%s), falling back to unverified context...", ssl_err)
            unverified_ctx = ssl.create_default_context()
            unverified_ctx.check_hostname = False
            unverified_ctx.verify_mode = ssl.CERT_NONE
            resp = urllib.request.urlopen(req, timeout=60, context=unverified_ctx)

        with resp:
            content_length = resp.headers.get("Content-Length")
            total_bytes = (
                int(content_length)
                if content_length and content_length.isdigit() and int(content_length) > 0
                else expected_size
            )

            with _STATE_LOCK:
                if model_id in _ACTIVE_DOWNLOADS:
                    _ACTIVE_DOWNLOADS[model_id]["total_bytes"] = total_bytes
                    _ACTIVE_DOWNLOADS[model_id]["remaining_bytes"] = total_bytes
                    _ACTIVE_DOWNLOADS[model_id]["response"] = resp

            downloaded_bytes = 0
            chunk_size = 512 * 1024  # 512 KB
            start_time = time.time()
            speed_samples: list[tuple[float, int]] = [(start_time, 0)]
            last_ui_update_time = 0.0

            with open(part_file, "wb") as pf:
                while True:
                    if cancel_event.is_set():
                        log.info("[DOWNLOAD] Download for %s was cancelled by user.", model_id)
                        break

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    pf.write(chunk)
                    downloaded_bytes += len(chunk)
                    now = time.time()

                    speed_samples.append((now, downloaded_bytes))
                    while len(speed_samples) > 2 and (now - speed_samples[0][0]) > 3.0:
                        speed_samples.pop(0)

                    if now - last_ui_update_time >= 0.1 or (total_bytes > 0 and downloaded_bytes >= total_bytes):
                        dt = speed_samples[-1][0] - speed_samples[0][0]
                        db = speed_samples[-1][1] - speed_samples[0][1]
                        if dt > 0.15 and db > 0:
                            speed_bps = db / dt
                        else:
                            elapsed = now - start_time
                            speed_bps = downloaded_bytes / elapsed if elapsed > 0.05 else 0.0

                        remaining_bytes = max(0, total_bytes - downloaded_bytes)
                        eta_seconds = int(remaining_bytes / speed_bps) if speed_bps > 1024 else 0
                        pct = min(99.9, round((downloaded_bytes / total_bytes) * 100, 1)) if total_bytes > 0 else 0.0

                        with _STATE_LOCK:
                            if model_id in _ACTIVE_DOWNLOADS:
                                _ACTIVE_DOWNLOADS[model_id].update({
                                    "downloaded_bytes": downloaded_bytes,
                                    "total_bytes": total_bytes,
                                    "remaining_bytes": remaining_bytes,
                                    "progress": pct,
                                    "speed_bps": speed_bps,
                                    "speed_display": format_speed(speed_bps),
                                    "eta_seconds": eta_seconds,
                                    "eta_display": format_eta(eta_seconds),
                                })
                        last_ui_update_time = now

        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return

        # Verify that the entire model was downloaded without premature connection drop
        if total_bytes > 0 and downloaded_bytes < total_bytes:
            raise IOError(
                f"Incomplete download: received {downloaded_bytes} of {total_bytes} bytes "
                f"({format_mb(downloaded_bytes)} MB of {format_mb(total_bytes)} MB)"
            )

        # Atomic replacement: replace temporary .part with final destination file
        if target_file.exists():
            try:
                target_file.unlink()
            except OSError:
                pass

        part_file.replace(target_file)

        final_size = target_file.stat().st_size
        if total_bytes > 0 and final_size < total_bytes:
            try:
                target_file.unlink()
            except OSError:
                pass
            raise IOError(f"Model file size verification failed: {final_size} bytes written, expected {total_bytes}")

        log.info(
            "[DOWNLOAD] Completed download for %s (%d bytes saved to %s)",
            model_id,
            final_size,
            target_file,
        )

        with _STATE_LOCK:
            _ACTIVE_DOWNLOADS[model_id] = {
                "status": "downloaded",
                "progress": 100.0,
                "downloaded_bytes": final_size,
                "total_bytes": final_size,
                "remaining_bytes": 0,
                "speed_bps": 0.0,
                "speed_display": "",
                "eta_seconds": 0,
                "eta_display": "",
                "error": None,
                "cancel_event": None,
            }

        # Activate a freshly downloaded model only when it does not overwrite an
        # explicit choice the user already made. Silently replacing a selected
        # cloud model with a local one changed how every later dictation was
        # polished without any indication.
        try:
            from voice_flow.storage import storage
            if spec.get("category") == "voice_polishing" or "polish" in spec.get("tag", "").lower():
                current = str(storage.get_setting("voice_flow_polish_model", "") or "").strip()
                if current in ("", "local/deterministic"):
                    storage.save_setting("voice_flow_polish_model", spec["full_id"])
                    log.info("[DOWNLOAD] Activated downloaded model '%s' as the Polish model (no prior choice).", spec["full_id"])
                else:
                    log.info(
                        "[DOWNLOAD] Downloaded polish model '%s' left inactive; keeping the user's selected model '%s'.",
                        spec["full_id"], current,
                    )
            else:
                current_stt = str(storage.get_setting("voice_flow_stt_model", "") or "").strip()
                if current_stt in ("", "local/faster-whisper-base.en"):
                    storage.save_setting("voice_flow_stt_model", spec["full_id"])
                    log.info("[DOWNLOAD] Activated downloaded model '%s' as the STT model (no prior choice).", spec["full_id"])
                    # Pre-warm the newly downloaded engine in background
                    try:
                        from voice_flow import nemotron_engine
                        threading.Thread(target=nemotron_engine.get_nemotron_engine, args=(spec["full_id"],), daemon=True).start()
                    except Exception:
                        pass
                else:
                    log.info(
                        "[DOWNLOAD] Downloaded STT model '%s' left inactive; keeping the user's selected model '%s'.",
                        spec["full_id"], current_stt,
                    )
        except Exception as e:
            log.warning("[DOWNLOAD] Error setting active model on download: %s", e)

    except urllib.error.HTTPError as exc:
        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return
        err_msg = f"HTTP error {exc.code}: {exc.reason}"
        log.error("[DOWNLOAD] HTTP Error for %s: %s", model_id, err_msg, exc_info=True)
        _handle_download_error(model_id, part_file, expected_size, err_msg)
    except urllib.error.URLError as exc:
        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return
        err_msg = f"Network connection failed: {exc.reason}"
        log.error("[DOWNLOAD] URLError for %s: %s", model_id, err_msg, exc_info=True)
        _handle_download_error(model_id, part_file, expected_size, err_msg)
    except (TimeoutError, socket.timeout) as exc:
        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return
        err_msg = "Download timed out while receiving data from server"
        log.error("[DOWNLOAD] Timeout for %s: %s", model_id, err_msg, exc_info=True)
        _handle_download_error(model_id, part_file, expected_size, err_msg)
    except OSError as exc:
        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return
        err_msg = f"Disk / filesystem error: {exc}"
        log.error("[DOWNLOAD] OSError for %s: %s", model_id, err_msg, exc_info=True)
        _handle_download_error(model_id, part_file, expected_size, err_msg)
    except Exception as exc:
        if cancel_event.is_set():
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            with _STATE_LOCK:
                _ACTIVE_DOWNLOADS.pop(model_id, None)
            return
        err_msg = str(exc)
        log.error("[DOWNLOAD] Download failed for %s: %s", model_id, exc, exc_info=True)
        _handle_download_error(model_id, part_file, expected_size, err_msg)


def cancel_model_download(model_id: str) -> tuple[bool, str]:
    """Cancel an ongoing download."""
    spec = get_model_spec(model_id)
    if not spec:
        return False, f"Model '{model_id}' not found in registry"

    with _STATE_LOCK:
        active = _ACTIVE_DOWNLOADS.get(spec["id"])
        if not active or active.get("status") != "downloading":
            return True, "No active download to cancel"

        cancel_ev = active.get("cancel_event")
        if cancel_ev:
            cancel_ev.set()

        resp = active.get("response")
        if resp:
            try:
                resp.close()
            except Exception:
                pass

        _ACTIVE_DOWNLOADS.pop(spec["id"], None)

    part_file = get_models_dir() / f"{spec['filename']}.part"
    if part_file.exists():
        try:
            part_file.unlink()
        except OSError:
            pass

    return True, "Download cancelled"


def delete_downloaded_model(model_id: str) -> tuple[bool, str]:
    """Delete a downloaded model file and cancel any active download."""
    spec = get_model_spec(model_id)
    if not spec:
        return False, f"Model '{model_id}' not found in registry"

    # Cancel if downloading
    cancel_model_download(spec["id"])

    target_file = get_models_dir() / spec["filename"]
    part_file = get_models_dir() / f"{spec['filename']}.part"

    deleted = False
    if target_file.exists():
        try:
            target_file.unlink()
            deleted = True
            log.info("[DOWNLOAD] Deleted model file: %s", target_file)
        except OSError as exc:
            log.warning("[DOWNLOAD] Could not delete model file %s: %s", target_file, exc)
            return False, f"Could not delete file: {exc}"

    if part_file.exists():
        try:
            part_file.unlink()
        except OSError:
            pass

    with _STATE_LOCK:
        _ACTIVE_DOWNLOADS.pop(spec["id"], None)

    try:
        from voice_flow import nemotron_engine
        nemotron_engine.clear_engine_cache(spec["id"])
    except Exception:
        pass

    # Check if this model is currently active in Voice Flow settings.
    # If so, revert back to safe default.
    try:
        from voice_flow.storage import storage

        if spec.get("category") == "voice_polishing" or "polish" in spec.get("tag", "").lower():
            current_polish = str(storage.get_setting("voice_flow_polish_model", "") or "").strip()
            if (
                current_polish == spec["full_id"]
                or current_polish == f"local/{spec['id']}"
                or current_polish == spec["id"]
                or current_polish.endswith(spec["filename"])
            ):
                from voice_flow import windows_ai_rewriter
                fallback = "microsoft/windows-ai-text-rewriter" if windows_ai_rewriter.is_windows_ai_available() else "local/deterministic"
                storage.save_setting("voice_flow_polish_model", fallback)
                log.info(
                    "[DOWNLOAD] Reset active Polish model to '%s' because %s was deleted",
                    fallback,
                    spec["name"],
                )
        else:
            current_stt = str(storage.get_setting("voice_flow_stt_model", "") or "").strip()
            if (
                current_stt == spec["full_id"]
                or current_stt == f"local/{spec['id']}"
                or current_stt == spec["id"]
                or current_stt.endswith(spec["filename"])
            ):
                storage.save_setting("voice_flow_stt_model", "local/faster-whisper-base.en")
                log.info(
                    "[DOWNLOAD] Reset active STT model to 'local/faster-whisper-base.en' because %s was deleted",
                    spec["name"],
                )
    except Exception as exc:
        log.warning("[DOWNLOAD] Error checking active model setting on delete: %s", exc)

    msg = "Model deleted successfully" if deleted else "Model was not downloaded"
    return True, msg
