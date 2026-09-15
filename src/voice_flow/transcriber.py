"""Ultra-fast, high-accuracy local transcription module using faster-whisper
with dictionary prompt-biasing, dual-pass VAD+fallback, and multi-core CPU execution.
"""

from __future__ import annotations

import logging
import threading
import time

from pathlib import Path

from faster_whisper import WhisperModel
import numpy as np
from numpy.typing import NDArray

from voice_flow.config import config
from voice_flow.dictionary import dictionary_engine
from voice_flow import nemotron_engine
from voice_flow import stt_engines
from voice_flow.voice_enhance import enhance_for_stt, vad_threshold_for, calibrate_vad_parameters

log = logging.getLogger(__name__)

# Guards the cloud-STT circuit-breaker counters. The stream worker and the
# dictation pipeline both call into transcribe() concurrently, so the
# check-and-update of the model-scoped breaker map must be atomic (the unlocked
# read-modify-write could clobber a concurrent failure count and never trip).
_CLOUD_BREAKER_LOCK = threading.Lock()
_CLOUD_BREAKER_STRIKES = 2  # consecutive failures before the cooldown opens
_CLOUD_BREAKER_COOLDOWN_S = 300.0  # transient failures / timeouts
# Hard 4xx (bad model, dead key) fails identically on every retry — a 5-minute
# cooldown re-burned two dictations every 5 minutes on an incompatible model,
# so incompatible-request failures get a much longer penalty.
_CLOUD_BREAKER_HARD_COOLDOWN_S = 1800.0
# Do not spend an interactive caller's entire deadline waiting for a selected
# cloud engine.  The local decoder needs a small, predictable window to return
# the transcript when the selected service is slow or unavailable.
_CLOUD_LOCAL_FALLBACK_RESERVE_S = 0.25


def _apply_noise_gate_and_normalize(audio: NDArray[np.float32]) -> NDArray[np.float32]:
    """Normalize primary speaker voice to optimal peak amplitude safely."""
    if audio.size == 0:
        return audio

    if audio.dtype == np.float32 and audio.ndim <= 1:
        peak = float(np.max(np.abs(audio)))
        if 0.0 < peak <= 1.0:
            return audio

    clean = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0)
    max_amp = float(np.max(np.abs(clean)))

    if max_amp > 0.001:
        scale = min(6.0, 0.85 / max_amp)
        return (clean * scale).astype(np.float32)

    return clean


def _has_audible_audio(audio: NDArray[np.float32]) -> bool:
    """True when the buffer carries any signal worth a second decode pass."""
    if audio.size == 0:
        return False
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio**2)))
    return peak > 0.015 and rms > 0.003


def _cloud_join_timeout(audio_duration: float) -> float:
    """Adaptive worker-join cap for cloud STT.

    Upload+transcribe of long recordings needs more than a fixed 8s (a 90s
    WAV upload alone can exceed it), and falling back to CPU whisper on a
    2-minute file costs 8-17s anyway — waiting a little longer for the fast
    cloud engine is usually the right trade.
    """
    return min(18.0, 8.0 + max(0.0, audio_duration) / 12.0)


def _cloud_chunk_join_timeout(audio_duration: float) -> float:
    """Join cap for cloud STT on STREAMING CHUNKS (additive to the pinned
    whole-buffer curve above, which stays byte-for-byte identical).

    Chunk calls pay the same fixed overhead (connect, TLS, upload, provider
    queueing) but the shallow whole-buffer slope timed out on long chunks:
    live logs (2026-09-02) show nova-3 exceeding the ~11.8s join (8s +
    45/12) on a ~45s chunk twice while short chunks succeed in 2.7-5s, so
    the late result was discarded and the audio re-transcribed locally at
    full cost. A steeper slope closes that gap. The 18s ceiling is kept
    equal to the whole-buffer cap on purpose: the pipeline's harvest budget
    (min(18, 8 + dictation/12)) never waits longer than that for a chunk,
    so a join beyond 18s could only produce results that get discarded.
    """
    return min(18.0, 9.0 + max(0.0, audio_duration) / 4.0)


def _deadline_remaining(deadline: float | None, cap: float | None = None) -> float:
    """Return seconds available before an absolute monotonic deadline."""
    if deadline is None:
        return float(cap) if cap is not None else float("inf")
    remaining = max(0.0, float(deadline) - time.monotonic())
    return min(remaining, float(cap)) if cap is not None else remaining


class Transcriber:
    """Pre-loaded Whisper model with dictionary prompt biasing, dual-pass
    VAD+fallback transcription, and instant non-blocking init."""

    def __init__(self) -> None:
        self.model: WhisperModel | None = None
        self.nemotron_engine: nemotron_engine.NemotronGGUFEngine | None = None
        self.category_hint: str | None = None  # app category for vocab hinting
        self._loading = False
        self._loaded_model_ref: str | None = None
        self._loading_model_ref: str | None = None
        self._lock = threading.Lock()
        self._transcribe_lock = threading.Lock()
        self._whisper_models: dict[str, WhisperModel] = {}
        self._mic_profile_cache: tuple[str, float] | None = None
        # Cloud-to-local failover tracking: lets the UI know when a fallback
        # happened so it can display a notification and offer a "retry cloud" button.
        self._last_failover: dict | None = None  # {cloud_model, reason, timestamp}
        self._failover_lock = threading.Lock()
        # Start pre-warming the active speech model asynchronously in background
        threading.Thread(target=self._load_active_model_bg, daemon=True).start()

    def _load_active_model_bg(self) -> None:
        """Pre-warm whichever local speech model is currently set in storage."""
        active_stt = ""
        try:
            from voice_flow.storage import storage
            active_stt = str(storage.get_setting("voice_flow_stt_model", "local/faster-whisper-base.en") or "").strip()
            # If active_stt is default faster-whisper but user has downloaded a local Nemotron model,
            # auto-promote the downloaded Nemotron model so the app immediately uses it!
            if not active_stt or active_stt == "local/faster-whisper-base.en":
                from voice_flow import downloadable_models
                downloaded = downloadable_models.get_downloaded_models()
                if downloaded:
                    active_stt = downloaded[0]["full_id"]
                    storage.save_setting("voice_flow_stt_model", active_stt)
                    log.info("[MODEL] Auto-promoted downloaded model '%s' to active STT model", active_stt)
        except Exception:
            pass
        if active_stt and not active_stt.lower().startswith("local/"):
            try:
                stt_engines.prewarm_cloud_stt(active_stt)
            except Exception:
                pass
        requested = self._local_model_name(active_stt) if active_stt else None
        self._load_model_bg(requested)

    @staticmethod
    def _local_model_name(model_ref: str | None = None) -> str:
        """Resolve a selected local provider id to the engine's model id.

        If a cloud model (e.g. groq/..., deepgram/..., gemini/...) is passed,
        resolve to the preferred local fallback model (downloaded Nemotron or
        config.model_size) so the local engine stays warm and ready for instant
        fallback without attempting to load cloud models locally.
        """
        selected = str(model_ref or "").strip()
        if not selected:
            try:
                from voice_flow.storage import storage
                selected = str(storage.get_setting("voice_flow_stt_model", "") or "").strip()
            except Exception:
                selected = ""
        provider, separator, model = selected.partition("/")
        if separator:
            if provider.casefold() == "local":
                selected = model.strip()
            else:
                # Cloud model: resolve fallback to the preferred local model
                selected = ""
        if selected.casefold().startswith("faster-whisper-"):
            selected = selected[len("faster-whisper-"):]
        if not selected:
            # Check for downloaded Nemotron/local model first, else fallback to config.model_size
            try:
                from voice_flow import downloadable_models
                downloaded = downloadable_models.get_downloaded_models()
                if downloaded:
                    dm_full = downloaded[0].get("full_id", "")
                    p, s, m = dm_full.partition("/")
                    if s and p.casefold() == "local":
                        selected = m.strip()
                    else:
                        selected = dm_full
            except Exception:
                pass
        return selected or str(config.model_size)

    def _load_model_bg(self, model_ref: str | None = None) -> None:
        requested_model = self._local_model_name(model_ref)
        with self._lock:
            if getattr(self, "_loaded_model_ref", None) == requested_model:
                if nemotron_engine.is_nemotron_model(requested_model) and getattr(self, "nemotron_engine", None) is not None:
                    return
                if getattr(self, "model", None) is not None:
                    return
            if self._loading and self._loading_model_ref == requested_model:
                return
            self._loading = True
            self._loading_model_ref = requested_model

        try:
            log.info("[MODEL] Loading speech model ('%s') with %d CPU threads in background...", requested_model, config.cpu_threads)

            # Check if requested model is an NVIDIA Nemotron GGUF model
            if nemotron_engine.is_nemotron_model(requested_model):
                eng = nemotron_engine.get_nemotron_engine(requested_model)
                if eng and eng.is_warm:
                    with self._lock:
                        self.nemotron_engine = eng
                        self._loaded_model_ref = requested_model
                        self._loading = False
                        self._loading_model_ref = None
                    log.info("[MODEL] Ultra-fast Nemotron GGUF speech engine ready (warm in memory)!")
                    return
                else:
                    log.warning("[MODEL] Nemotron GGUF engine unavailable for '%s', falling back to whisper", requested_model)

            resolved_model_ref: object = requested_model
            try:
                from voice_flow import runtime_env

                bundled = runtime_env.whisper_model_path()
                # The bundled runtime only contains base.en. Selecting tiny,
                # small, or another local model must load that exact model.
                if bundled is not None and (resolved_model_ref == "base.en" or requested_model.casefold() == "base.en"):
                    resolved_model_ref = str(bundled)
            except Exception:
                pass

            # Check in-memory whisper cache to eliminate reload latency
            cache_key = str(resolved_model_ref)
            with self._lock:
                if not hasattr(self, "_whisper_models") or self._whisper_models is None:
                    self._whisper_models = {}
                cached_model = self._whisper_models.get(cache_key)
            if cached_model is not None:
                with self._lock:
                    self.model = cached_model
                    self._loaded_model_ref = requested_model
                    self._loading = False
                    self._loading_model_ref = None
                log.info("[MODEL] Reused cached Whisper model ('%s')", cache_key)
                return

            # Check local HF hub cache to prevent blocking network queries
            is_local = not isinstance(resolved_model_ref, str) or Path(str(resolved_model_ref)).is_dir()
            if not is_local and isinstance(resolved_model_ref, str):
                try:
                    from huggingface_hub import try_to_load_from_cache
                    cached_snap = try_to_load_from_cache(f"Systran/faster-whisper-{resolved_model_ref}", "model.bin")
                    if cached_snap is not None:
                        is_local = True
                except Exception:
                    pass

            model_inst = WhisperModel(
                resolved_model_ref,
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
                local_files_only=is_local,
            )
            with self._lock:
                self._whisper_models[cache_key] = model_inst
                self.model = model_inst
                self._loaded_model_ref = requested_model
                self._loading = False
                self._loading_model_ref = None
            log.info("[MODEL] Ultra-fast speech engine ready!")
        except Exception as e:
            log.error("[MODEL ERROR] Failed to load speech model: %s", e, exc_info=True)
            with self._lock:
                self._loading = False
                self._loading_model_ref = None

    def transcribe(
        self,
        audio: NDArray[np.float32],
        is_chunk: bool = False,
        deadline: float | None = None,
        model_ref: str | None = None,
    ) -> str:
        """Transcribe audio with dictionary initial_prompt biasing and dual-pass accuracy.

        ``is_chunk=True`` marks a streaming-chunk call: the cloud worker gets
        the chunk-specific join budget, and a join timeout where the HTTP
        worker is STILL RUNNING counts neither as a breaker strike nor as a
        finished chunk (the worker keeps going and its result is still
        collected by a later ``StreamTranscriber.collect``). ``deadline`` is
        an absolute ``time.monotonic()`` timestamp supplied by the release
        pipeline; every network/model warm-up wait honors it.
        """
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        category = getattr(self, "category_hint", None)
        # Input conditioning BEFORE any model (cloud or local): whisper-level
        # sources are amplified, rumble/HVAC noise is filtered, room noise is
        # gated down, and a paired VAD threshold keeps the shared-room chatter
        # out. Profile auto-detects (whisper / far / noisy / normal) unless the
        # user pinned one via the voice_flow_mic_profile setting.
        enhance_profile = "auto"
        try:
            now = time.monotonic()
            cached = getattr(self, "_mic_profile_cache", None)
            if cached is not None and isinstance(cached, tuple) and len(cached) == 2:
                profile_val, timestamp = cached
                cur_time = time.time() if timestamp > 1e8 else now
                if 0 <= (cur_time - timestamp) < 5.0:
                    enhance_profile = profile_val
                else:
                    cached = None
            if cached is None:
                try:
                    from voice_flow.storage import storage as _storage

                    enhance_profile = str(_storage.get_setting("voice_flow_mic_profile", "auto") or "auto")
                except Exception:
                    enhance_profile = "auto"
                self._mic_profile_cache = (enhance_profile, now)
            input_peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            audio, enhance_profile = enhance_for_stt(audio, config.sample_rate, profile=enhance_profile)
            if enhance_profile not in ("off", "silence"):
                log.info("[ENHANCE] profile=%s (peak in %.4f -> out %.3f)", enhance_profile,
                         input_peak, float(np.max(np.abs(audio))) if audio.size else 0.0)
            self._last_vad_threshold = vad_threshold_for(enhance_profile) if enhance_profile not in ("off", "silence") else 0.20
            self._last_vad_parameters = calibrate_vad_parameters(enhance_profile) if enhance_profile not in ("off", "silence") else calibrate_vad_parameters("normal")
        except Exception:
            self._last_vad_threshold = 0.20
            self._last_vad_parameters = calibrate_vad_parameters("normal")

        # Selected speech-to-text engine (Providers page). A non-local value is
        # an explicit user choice: route this dictation to that exact adapter,
        # including short utterances. Local Whisper is only the resilient
        # fallback when that bounded attempt cannot return text.
        # A circuit breaker trips after 2 consecutive cloud failures/empties and
        # routes straight to local whisper for a cooldown (300s, or 30 min for
        # hard HTTP-4xx rejections), so a slow or broken cloud engine can never
        # add long delays to every dictation.
        stt_model = ""
        try:
            from voice_flow.storage import storage
            stt_model = str(model_ref or storage.get_setting("voice_flow_stt_model", "local/faster-whisper-base.en") or "").strip()
        except Exception:
            stt_model = str(model_ref or "")
        stt_provider = stt_model.partition("/")[0].strip().lower()
        # Explicit dispatch log so users and developers can verify which model
        # the backend is ACTUALLY routing to on each dictation.
        print(f"[STT MODEL DISPATCH] Using model='{stt_model}' provider='{stt_provider}' (model_ref arg='{model_ref}')")
        log.info("[STT MODEL DISPATCH] Using model='%s' provider='%s' (model_ref arg='%s')", stt_model, stt_provider, model_ref)
        if stt_model and stt_provider != "local":
            now = time.time()
            with _CLOUD_BREAKER_LOCK:
                breakers = getattr(self, "_cloud_stt_breakers", None)
                if not isinstance(breakers, dict):
                    breakers = {}
                    self._cloud_stt_breakers = breakers
                failures, blocked_until = breakers.get(stt_model, (0, 0.0))
                breaker_open = failures >= 2 and now < blocked_until
                if not breaker_open and failures >= 2:
                    failures = 0  # cooldown expired — retry the cloud engine
                    breakers[stt_model] = (0, 0.0)
            if breaker_open:
                log.info("[STT] Cloud engine '%s' is in cooldown for another %.0fs after repeated failures; using local whisper.",
                         stt_model, max(0.0, blocked_until - now))
            else:
                result_box: dict = {}

                def _cloud_call():
                    try:
                        kwargs = {"vocabulary": self._stt_hint_terms(category)}
                        if deadline is not None:
                            kwargs["deadline"] = deadline
                        try:
                            result_box["text"] = stt_engines.transcribe_cloud(audio, stt_model, **kwargs)
                        except TypeError as exc:
                            # Preserve compatibility with one-generation test
                            # doubles and third-party adapters that predate the
                            # optional deadline keyword.
                            if deadline is None or "deadline" not in str(exc).lower():
                                raise
                            kwargs.pop("deadline", None)
                            result_box["text"] = stt_engines.transcribe_cloud(audio, stt_model, **kwargs)
                    except Exception as exc:
                        result_box["error"] = str(exc)

                audio_duration = len(audio) / max(1, config.sample_rate)
                # Chunks use the steeper chunk budget (live logs: nova-3 blew
                # through the shallow whole-buffer slope on ~45s chunks while
                # the whole-buffer curve itself stays pinned by tests).
                cloud_timeout = (
                    _cloud_chunk_join_timeout(audio_duration)
                    if is_chunk
                    else _cloud_join_timeout(audio_duration)
                )
                worker: threading.Thread | None = None
                # Retain a short local-fallback window when there is a caller
                # deadline.  Otherwise a cloud join can consume every last
                # millisecond and turn a recoverable provider failure into a
                # dropped dictation.
                join_timeout = _deadline_remaining(deadline, cloud_timeout)
                if deadline is not None:
                    join_timeout = max(0.0, join_timeout - _CLOUD_LOCAL_FALLBACK_RESERVE_S)
                if join_timeout > 0.0:
                    worker = threading.Thread(target=_cloud_call, daemon=True)
                    worker.start()
                    worker.join(timeout=join_timeout)
                else:
                    result_box["error"] = "STT deadline reserved for local fallback"
                cloud_text = str(result_box.get("text") or "").strip()
                reason = str(result_box.get("error") or "")
                worker_alive = worker is not None and worker.is_alive()
                # A chunk whose join budget expired while the HTTP worker is
                # STILL RUNNING is a slow provider, not a failed one: no
                # breaker strike, no cooldown — two slow chunks mid-dictation
                # must not push every later dictation to local whisper.
                chunk_still_running = is_chunk and worker_alive and not cloud_text
                # Permanent failures trip the breaker on the FIRST dictation:
                # HTTP 4xx (dead key, rejected request — the provider's answer
                # is deterministic) and unsupported providers (adapter lookup
                # fails before any request is sent). 408/429 are transient and
                # count normally.
                hard_failure = (
                    reason.startswith("HTTP 4") or "does not support speech-to-text" in reason
                ) and not (
                    reason.startswith("HTTP 408") or reason.startswith("HTTP 429")
                )
                deadline_failure = "deadline" in reason.lower()
                with _CLOUD_BREAKER_LOCK:
                    # Re-read the counter HERE: `failures` was captured before
                    # the network call, and the stream worker (chunks) and the
                    # pipeline thread (whole buffer) transcribe concurrently —
                    # counting from the stale value silently drops one of two
                    # simultaneous failures and the breaker opens late.
                    breakers = getattr(self, "_cloud_stt_breakers", {})
                    if not isinstance(breakers, dict):
                        breakers = {}
                        self._cloud_stt_breakers = breakers
                    current_failures, _ = breakers.get(stt_model, (0, 0.0))
                    if cloud_text:
                        breakers[stt_model] = (0, 0.0)
                        new_failures = 0
                    elif chunk_still_running or deadline_failure:
                        new_failures = current_failures  # neutral: no strike, no reset
                    elif worker_alive or not hard_failure:
                        new_failures = current_failures + 1
                    else:
                        new_failures = _CLOUD_BREAKER_STRIKES
                    # Hard 4xx gets the long cooldown; everything else the short one.
                    cooldown = _CLOUD_BREAKER_HARD_COOLDOWN_S if (
                        not cloud_text and not chunk_still_running and not worker_alive and hard_failure
                    ) else _CLOUD_BREAKER_COOLDOWN_S
                    if new_failures >= _CLOUD_BREAKER_STRIKES and not chunk_still_running and not deadline_failure:
                        breakers[stt_model] = (new_failures, now + cooldown)
                    elif not cloud_text and not (chunk_still_running or deadline_failure):
                        breakers[stt_model] = (new_failures, 0.0)
                if cloud_text:
                    log.info("[STT] Cloud engine '%s' used.", stt_model)
                    self._last_failover_info = None  # clear: cloud succeeded
                    return cloud_text
                # Record the failover event for API / UI exposure
                failover_reason = reason or "empty text"
                if chunk_still_running:
                    failover_reason = f"chunk join budget exceeded ({cloud_timeout:.1f}s)"
                elif worker_alive:
                    failover_reason = f"timeout after {cloud_timeout:.1f}s"
                self._last_failover_info = {
                    "cloud_model": stt_model,
                    "reason": failover_reason,
                    "failure_count": new_failures if not chunk_still_running else 0,
                    "breaker_open": new_failures >= _CLOUD_BREAKER_STRIKES and not chunk_still_running and not deadline_failure,
                    "timestamp": now,
                }
                self._failover_count = getattr(self, "_failover_count", 0) + 1
                print(f"[STT FAILOVER] Cloud model '{stt_model}' failed ({failover_reason}); falling back to local model (failover #{self._failover_count})")
                if chunk_still_running:
                    log.warning("[STT] Cloud engine '%s' exceeded the %.1fs chunk join budget but is still running; using local whisper for this chunk (no breaker strike).", stt_model, cloud_timeout)
                elif worker_alive:
                    log.warning("[STT] Cloud engine '%s' timed out after %.1fs (failure %d/2); using local whisper.", stt_model, cloud_timeout, new_failures)
                elif new_failures >= _CLOUD_BREAKER_STRIKES:
                    log.warning("[STT] Cloud engine '%s' returned empty text%s (failure %d/2%s); using local whisper for %.0fs.",
                                stt_model, f": {reason}" if reason else "", new_failures,
                                ", hard 4xx" if hard_failure else "", cooldown)
                else:
                    log.warning("[STT] Cloud engine '%s' returned empty text%s (failure %d/2); using local whisper.",
                                stt_model, f": {reason}" if reason else "", new_failures)

        local_model = self._local_model_name(stt_model) if stt_provider == "local" else None
        if not self._wait_for_model(deadline, model_ref=local_model):
            log.error("Speech model failed to initialize in time.")
            return ""

        return self._transcribe_local(audio, category=category, deadline=deadline, model_ref=local_model, is_chunk=is_chunk)

    def _wait_for_model(self, deadline: float | None = None, model_ref: str | None = None) -> bool:
        """Wait for the background model load without crossing *deadline*."""
        requested_model = self._local_model_name(model_ref)

        is_loading = getattr(self, "_loading", False)
        # 1. Fast path: Nemotron model already warm or in singleton cache (only if not actively loading)
        if not is_loading and nemotron_engine.is_nemotron_model(requested_model):
            if (
                getattr(self, "nemotron_engine", None) is not None
                and self.nemotron_engine.is_warm
                and getattr(self, "_loaded_model_ref", None) == requested_model
            ):
                return True
            eng = nemotron_engine.get_nemotron_engine(requested_model)
            if eng and eng.is_warm:
                with self._lock:
                    self.nemotron_engine = eng
                    self._loaded_model_ref = requested_model
                    self._loading = False
                    self._loading_model_ref = None
                return True

        # 2. Fast path: Whisper model already loaded
        if not is_loading and getattr(self, "model", None) is not None and getattr(self, "_loaded_model_ref", requested_model) == requested_model:
            return True

        # Start a requested model load without replacing an in-flight loader.
        requested_load_started = False
        if not getattr(self, "_loading", False):
            threading.Thread(target=self._load_model_bg, args=(requested_model,), name="vf-model-load", daemon=True).start()
            requested_load_started = True

        log.info("Speech model still warming up, waiting for initialization...")
        started = time.monotonic()
        first_wait_until = started + 15.0
        if deadline is not None:
            first_wait_until = min(first_wait_until, deadline)

        def _is_ready() -> bool:
            if getattr(self, "_loading", False):
                return False
            if nemotron_engine.is_nemotron_model(requested_model):
                return (
                    getattr(self, "nemotron_engine", None) is not None
                    and self.nemotron_engine.is_warm
                    and getattr(self, "_loaded_model_ref", None) == requested_model
                )
            return (
                getattr(self, "model", None) is not None
                and getattr(self, "_loaded_model_ref", requested_model) == requested_model
            )

        while not _is_ready():
            if not getattr(self, "_loading", False) and not requested_load_started:
                threading.Thread(
                    target=self._load_model_bg,
                    args=(requested_model,),
                    name="vf-model-switch",
                    daemon=True,
                ).start()
                requested_load_started = True
            remaining = first_wait_until - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.05, remaining))

        return _is_ready()

    def _stt_hint_terms(self, category: str | None) -> list[str]:
        """Dictionary terms for cloud STT contextual biasing (spec §33)."""
        try:
            return dictionary_engine.get_stt_hint_terms(category)
        except Exception:
            return []

    def _transcribe_local(
        self,
        audio: NDArray[np.float32],
        category: str | None = None,
        deadline: float | None = None,
        model_ref: str | None = None,
        is_chunk: bool = False,
    ) -> str:
        """Local decode: Nemotron GGUF or faster-whisper with dictionary biasing."""
        requested_model = self._local_model_name(model_ref)
        if not self._wait_for_model(deadline, model_ref=requested_model):
            log.error("Speech model failed to initialize in time.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.2:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        # The buffer was already enhanced once in transcribe() (whisper/
        # far-mic/noisy-room conditioning); light normalization optimal for local models.
        if audio.dtype == np.float32 and audio.ndim <= 1 and audio.size > 0:
            peak = float(np.max(np.abs(audio)))
            clean_audio = audio if 0.0 < peak <= 1.0 else _apply_noise_gate_and_normalize(audio)
        else:
            clean_audio = _apply_noise_gate_and_normalize(audio)

        # Route to Nemotron GGUF engine if active. Nemotron's C ABI options
        # struct carries speech-context fields and its transcribe() already
        # accepts a ``vocabulary`` keyword (currently unused inside the
        # engine, which is outside this change's scope), so dictionary hint
        # terms are passed here: engines that predate the keyword keep
        # working via the TypeError retry, and a future engine that wires
        # speech contexts picks the terms up with no dictation-side change.
        # Deterministic trigger->replacement post-processing below still
        # applies on this path, so explicit terms take effect regardless.
        if nemotron_engine.is_nemotron_model(requested_model):
            eng = getattr(self, "nemotron_engine", None) or nemotron_engine.get_nemotron_engine(requested_model)
            if eng and eng.is_warm:
                nemotron_vocabulary = self._stt_hint_terms(category) or None
                try:
                    text = eng.transcribe(
                        clean_audio,
                        is_chunk=is_chunk,
                        deadline=deadline,
                        vocabulary=nemotron_vocabulary,
                        language=getattr(config, "language", "en") or "en",
                    )
                except TypeError:
                    text = eng.transcribe(
                        clean_audio,
                        is_chunk=is_chunk,
                        deadline=deadline,
                        language=getattr(config, "language", "en") or "en",
                    )
                if text:
                    return dictionary_engine.apply_dictionary_post_processing(text)
                if not _has_audible_audio(clean_audio):
                    return ""
                log.warning("[STT] Nemotron produced empty output for audible audio; checking Whisper fallback.")
                if getattr(self, "model", None) is None:
                    with self._lock:
                        whisper_dict = getattr(self, "_whisper_models", {}) or {}
                        self.model = whisper_dict.get("base.en") or next(iter(whisper_dict.values()), None)
                    if getattr(self, "model", None) is None:
                        log.info("[STT] Local Whisper fallback not loaded; skipping second pass.")
                        return ""

        vad_params = getattr(self, "_last_vad_parameters", None)
        if not vad_params:
            vad_params = calibrate_vad_parameters("normal")

        # Get dictionary initial prompt biasing
        initial_prompt = dictionary_engine.get_initial_prompt(category)

        log.info("Transcribing %.1fs audio on %d CPU threads (beam=%d)...", duration, config.cpu_threads, config.beam_size)

        result = ""
        # Guard: constructors that bypass __init__ (e.g. tests) may lack the lock;
        # create it lazily so transcription is always thread-safe.
        if not hasattr(self, "_transcribe_lock"):
            self._transcribe_lock = threading.Lock()
        # Streaming workers may reach local fallback concurrently. Whisper's
        # model is protected by this lock, but an unbounded acquire here would
        # let a queued chunk cross the release deadline while waiting for an
        # earlier decode. Keep old blocking behavior without a deadline and
        # make deadline-bound calls truthful.
        lock = self._transcribe_lock
        if deadline is None:
            acquired = lock.acquire()
        else:
            remaining = _deadline_remaining(deadline)
            acquired = remaining > 0.0 and lock.acquire(timeout=remaining)
        if not acquired:
            log.warning("[STT] Local decode skipped because its deadline elapsed while waiting for the model lock.")
            return ""
        try:
            try:
                segments, _ = self.model.transcribe(
                    clean_audio,
                    beam_size=config.beam_size,
                    temperature=config.temperature,
                    language=config.language,
                    initial_prompt=initial_prompt,
                    vad_filter=True,
                    # Long-dictation accuracy: carrying hallucinated context
                    # across windows is what makes mid-text "break" (repeated
                    # or drifting words) on long recordings, and whispers of
                    # silence invent text. Per-segment temperatures keep the
                    # fallback decode stable.
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                    log_prob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                    vad_parameters=vad_params,
                )
                parts = [s.text.strip() for s in segments if s.text.strip()]
                result = " ".join(parts).strip()
            except Exception as e:
                log.warning("[VAD] VAD pass encountered error (%s), attempting direct fallback...", e)
                result = ""

            # Dual-pass fallback if VAD returned empty text or failed. The
            # audibility gate compares the pre-normalization buffer peak:
            # normalization can inflate near-silence past the threshold and
            # trigger a pointless (slow) second decode on silence.
            if not result and _has_audible_audio(audio) and _deadline_remaining(deadline) > 0.0:
                log.info("[FALLBACK] Running direct audio pass without VAD filter...")
                try:
                    fallback_segments, _ = self.model.transcribe(
                        clean_audio,
                        beam_size=config.beam_size,
                        temperature=config.temperature,
                        language=config.language,
                        initial_prompt=initial_prompt,
                        vad_filter=False,
                        condition_on_previous_text=False,
                    )
                    parts = [s.text.strip() for s in fallback_segments if s.text.strip()]
                    result = " ".join(parts).strip()
                except Exception as e:
                    log.error("[FALLBACK] Direct transcription pass failed: %s", e)

        finally:
            lock.release()

        # Trigger->replacement post-processing on the local path (Nemotron +
        # faster-whisper, both passes): an explicit dictionary entry such as a
        # user's name is an exact-match rewrite of what STT produced, so it
        # applies here at decode time and again in the polisher — both passes
        # are idempotent, and a dictionary failure must never lose audio text.
        if result:
            try:
                rewritten = dictionary_engine.apply_dictionary_post_processing(result)
                if isinstance(rewritten, str) and rewritten:
                    return rewritten
            except Exception:
                log.warning("[STT] Dictionary post-processing unavailable; keeping raw transcript.")
        return result
