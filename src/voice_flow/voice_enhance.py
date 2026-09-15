"""Speech enhancement for Voice Flow STT (whisper / far-mic / noisy room).

Every dictation buffer passes through :func:`enhance_for_stt` before the
selected STT model sees it. The chain is deterministic DSP, no ML, no I/O:

1. High-pass filter (~80 Hz) removes rumble, HVAC hum, desk thumps.
2. Noise-floor estimation from the quietest audio windows (10th percentile of
   short-window RMS), then spectral gating: frequency bins that hover at the
   noise floor are attenuated instead of amplified. This is what lets the app
   catch the USER's voice in a shared room instead of the room itself.
3. Adaptive gain: quiet sources (whispering, sitting far away) are brought up
   to dictation level with a much higher gain ceiling than the old fixed 6x
   (up to ~30x), applied AFTER denoising so the noise floor is not boosted
   along with the voice.
4. Everything stays float32 in [-1, 1]; no clipping (gain is peak-normalized).

Profiles tune the chain:

- ``auto`` (default): measures the buffer and picks quiet/far (very low peak)
  vs noisy (low SNR) vs normal. The measurement is cheap windowed RMS math.
- ``whisper``: maximum gain, gentlest gating — soft speech, close mic.
- ``far``: maximum gain + stronger gating — voice dominates less than noise.
- ``noisy``: strongest gating + higher high-pass — shared loud room.
- ``normal``: light touch — healthy close-mic signal, near-zero overhead.

Kill switch: env ``VOICE_FLOW_AUDIO_ENHANCE=0`` restores raw passthrough.
"""
from __future__ import annotations

import logging
import os

import numpy as np

log = logging.getLogger(__name__)

try:  # scipy is a hard dependency of the app already (resample_poly)
    import scipy.signal as sig
except Exception:  # pragma: no cover
    sig = None

from voice_flow.vad import calibrate_vad_parameters

_TARGET_PEAK = 0.85
_NEAR_SILENCE = 1e-4
_MIN_ENHANCE_LEN = 1600  # 0.1 s @ 16 kHz below which we only normalize

_PROFILES: dict[str, dict] = {
    "whisper": {"highpass_hz": 70, "gain_ceiling": 60.0, "gate_strength": 2.2, "gate_floor": 0.05, "vad_threshold": 0.15, "target_rms_db": -14.0},
    "far": {"highpass_hz": 80, "gain_ceiling": 80.0, "gate_strength": 2.5, "gate_floor": 0.02, "vad_threshold": 0.12, "target_rms_db": -13.0},
    "noisy": {"highpass_hz": 100, "gain_ceiling": 16.0, "gate_strength": 2.0, "gate_floor": 0.02, "vad_threshold": 0.35, "target_rms_db": -16.0},
    "normal": {"highpass_hz": 80, "gain_ceiling": 12.0, "gate_strength": 2.0, "gate_floor": 0.05, "vad_threshold": 0.20, "target_rms_db": -16.0},
}


def _window_rms(audio: np.ndarray, sr: int = 16000, window_ms: int = 50) -> np.ndarray:
    """RMS of consecutive non-overlapping ~50 ms windows."""
    size = max(1, int(sr * window_ms / 1000))
    n = (audio.size // size) * size
    if n == 0:
        return np.array([float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0])
    frames = audio[:n].reshape(-1, size)
    return np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))


def _measure(audio: np.ndarray, sr: int = 16000) -> dict:
    """Cheap buffer statistics used by the auto profile and by callers."""
    if audio.size == 0:
        return {"peak": 0.0, "noise_floor": 0.0, "speech_level": 0.0, "snr": 99.0}
    peak = float(np.max(np.abs(audio)))
    rms = _window_rms(audio, sr)
    noise_floor = float(np.percentile(rms, 10)) if rms.size else 0.0
    speech_level = float(np.percentile(rms, 90)) if rms.size else 0.0
    snr = (speech_level / noise_floor) if noise_floor > 1e-6 else 99.0
    return {"peak": peak, "noise_floor": noise_floor, "speech_level": speech_level, "snr": snr}


def _auto_profile(audio: np.ndarray, sr: int = 16000) -> str:
    stats = _measure(audio, sr)
    # Distant speech (~10 feet away): very low peak, with noticeable room noise floor or low SNR
    if stats["peak"] < 0.08:
        if stats["noise_floor"] > 0.0008 or (stats["speech_level"] > 0 and stats["snr"] < 10.0):
            return "far"
        return "whisper"
    if stats["noise_floor"] > 0.004 and stats["speech_level"] > 0.015 and stats["snr"] < 12.0:
        # Speech barely above a LOUD room floor: shared/loud environment.
        return "noisy"
    return "normal"


def _highpass(audio: np.ndarray, sr: int, hz: float) -> np.ndarray:
    if sig is None or audio.size < 64:
        return audio
    try:
        sos = sig.butter(4, min(hz, sr / 2 - 100), btype="highpass", fs=sr, output="sos")
        return sig.sosfilt(sos, audio).astype(np.float32)
    except Exception:
        return audio


def _spectral_gate(audio: np.ndarray, sr: int, strength: float, floor: float) -> np.ndarray:
    """Attenuate frequency bins at the noise floor (spectral subtraction).

    The noise profile comes from the QUIETEST ~20% of time-frames (measured by
    frame energy — typically pauses and room-only moments), averaged per bin.
    A per-bin percentile across all frames is wrong for mixed clips: in a
    recording that is half speech / half room, the quietest frames for most
    bins are the SPEECH segment (where those bins are silent), which collapses
    the profile to zero and silently disables the gate. Speech bins (well above
    the profile) pass untouched; noise bins drop by ``strength``x, floor-retained
    at ``floor`` of their magnitude to avoid musical-noise artifacts.
    """
    if sig is None or audio.size < 1024:
        return audio
    try:
        nperseg = 512
        noverlap = nperseg - 160  # ~10 ms hop at 16 kHz
        _, _, stft = sig.stft(audio, fs=sr, nperseg=nperseg, noverlap=noverlap, padded=False)
        # NaN/Inf quarantine BEFORE the ratio reconstruction: a non-finite
        # stft bin would poison whole output frames through istft (NaNs do not
        # raise — they surface downstream as a silent/garbled buffer).
        stft = np.nan_to_num(stft, nan=0.0, posinf=0.0, neginf=0.0)
        mag = np.abs(stft)
        frame_energy = np.sum(mag.astype(np.float64) ** 2, axis=0)
        quiet = frame_energy <= np.percentile(frame_energy, 20)
        if not np.any(quiet):
            quiet = frame_energy <= np.max(frame_energy)
        noise_profile = np.mean(mag[:, quiet], axis=1, keepdims=True) + 1e-9
        # Signal protection: a bin whose strong frames rise above the noise
        # profile carries speech (or a sustained tone) — subtracting there
        # would eat the signal itself. Only bins that NEVER rise above the
        # noise floor get gated down. This keeps the subtraction honest.
        bin_avg = np.mean(mag, axis=1, keepdims=True)
        noise_bins = bin_avg <= strength * noise_profile * 0.75
        sub = np.maximum(mag - strength * noise_profile, floor * mag)
        gated_mag = np.where(noise_bins, sub, mag)
        # Ratio-form reconstruction: divide the original spectrum by its
        # magnitude and multiply by the gated one — same phase, ~30-40% less
        # compute than exp(i*angle()) and no wrap-around risk.
        _, gated = sig.istft(gated_mag * (stft / np.maximum(mag, 1e-12)), fs=sr, nperseg=nperseg, noverlap=noverlap)
        if gated.size < audio.size:
            # istft output can come up short (length='auto' drops samples that
            # do not fit whole overlap frames); zero-pad so the enhanced buffer
            # keeps the input's sample count and every word boundary stays put.
            gated = np.pad(gated, (0, audio.size - gated.size))
        elif gated.size > audio.size:
            gated = gated[:audio.size]
        return gated.astype(np.float32)
    except Exception:
        return audio


def _relative_voice_gate(audio: np.ndarray, sr: int = 16000, ratio: float = 0.12) -> np.ndarray:
    """Suppress windows far quieter than the dominant voice (close-mic bias).

    In a shared room the user's mouth is the closest, loudest source. Windows
    whose RMS is below ``ratio`` x the dominant (90th percentile) window level
    are faded toward silence, so quieter background talkers between the
    user's phrases stop reaching the model.
    """
    if audio.size < 1600:
        return audio
    try:
        size = max(1, int(sr * 0.025))
        n = (audio.size // size) * size
        if n == 0:
            return audio
        frames = audio[:n].reshape(-1, size)
        rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
        reference = float(np.percentile(rms, 90))
        if reference < 1e-5:
            return audio
        mask = np.clip(rms / (reference * ratio), 0.0, 1.0)
        smooth = np.convolve(mask, np.ones(3) / 3, mode="same")
        # A NaN mask sample would propagate through interp into the whole
        # envelope; sanitize so the gate can only ever attenuate.
        smooth = np.nan_to_num(smooth, nan=0.0, posinf=1.0, neginf=0.0)
        # Interpolate the per-window envelope to sample rate. A constant gain
        # per 25 ms window steps discontinuously at frame boundaries and that
        # step is an audible click right in the dictation signal.
        centers = (np.arange(smooth.size) * size + size / 2.0)
        envelope = np.interp(np.arange(audio.size), centers, smooth).astype(np.float32)
        out = (audio * envelope).astype(np.float32)
        return out
    except Exception:
        return audio


def _soft_knee_limiter(audio: np.ndarray, threshold: float = 0.85, ceiling: float = 0.95) -> np.ndarray:
    """Transparent soft-knee peak limiter that prevents digital clipping."""
    abs_val = np.abs(audio)
    over = abs_val > threshold
    if not np.any(over):
        return audio
    margin = ceiling - threshold
    scale = np.ones_like(audio)
    excess = (abs_val[over] - threshold) / margin
    compressed = threshold + margin * np.tanh(excess)
    scale[over] = compressed / np.maximum(abs_val[over], 1e-12)
    return (audio * scale).astype(np.float32)


def _apply_dynamic_agc(
    audio: np.ndarray,
    sr: int = 16000,
    target_rms_db: float = -15.0,
    gain_ceiling: float = 80.0,
    noise_floor: float = 1e-4,
) -> np.ndarray:
    """Real-time dynamic Automatic Gain Control with soft knee, gain hold, and soft limiter.

    Elevates quiet/distant speech (-18dB to -14dB nominal target) while
    avoiding amplifying stationary background noise, smoothly holds gain
    during brief inter-word pauses to prevent syllable onset clipping, and
    rapidly attenuates loud transients to prevent digital distortion.
    """
    if audio.size < 256:
        return audio

    target_rms = float(10.0 ** (target_rms_db / 20.0))
    frame_len = max(1, int(sr * 0.020))  # 20ms frames
    n_frames = audio.size // frame_len
    if n_frames < 2:
        peak = float(np.max(np.abs(audio)))
        if peak > 1e-5:
            gain = min(gain_ceiling, _TARGET_PEAK / peak)
            return _soft_knee_limiter(audio * gain)
        return audio

    trimmed = audio[: n_frames * frame_len]
    frames = trimmed.reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)).astype(np.float32)

    gate_thresh = max(1.2 * noise_floor, 0.0004)
    hold_frames = int(0.250 / 0.020)  # 250ms gain hold
    hold_counter = 0
    last_speech_gain = 1.0

    target_gains = np.ones(n_frames, dtype=np.float32)
    for i in range(n_frames):
        rms = frame_rms[i]
        if rms > gate_thresh:
            desired = float(np.clip(target_rms / max(rms, 1e-5), 0.5, gain_ceiling))
            # Smooth soft knee transition around the noise gate
            snr_ratio = float(np.clip((rms - gate_thresh) / (gate_thresh + 1e-6), 0.0, 1.0))
            tg = 1.0 + snr_ratio * (desired - 1.0)
            last_speech_gain = tg
            hold_counter = hold_frames
            target_gains[i] = tg
        else:
            if hold_counter > 0:
                hold_counter -= 1
                target_gains[i] = last_speech_gain
            else:
                target_gains[i] = 1.0

    # Time constants:
    # dt = 20ms
    # Fast attack for speech onset: ~15ms
    # Ultra-fast attack for loud transient suppression (gain reduction): ~5ms
    # Smooth decay/release for silence after hold: ~200ms
    dt = 0.020
    alpha_transient = float(np.exp(-dt / 0.005))
    alpha_onset = float(np.exp(-dt / 0.015))
    alpha_release = float(np.exp(-dt / 0.200))

    smoothed_gains = np.zeros(n_frames, dtype=np.float32)
    curr = target_gains[0]
    for i in range(n_frames):
        tg = target_gains[i]
        if tg < curr:
            alpha = alpha_release if tg <= 1.05 else alpha_transient
            curr = alpha * curr + (1.0 - alpha) * tg
        else:
            curr = alpha_onset * curr + (1.0 - alpha_onset) * tg
        smoothed_gains[i] = curr

    frame_centers = (np.arange(n_frames) * frame_len + frame_len / 2.0).astype(np.float32)
    sample_indices = np.arange(audio.size, dtype=np.float32)
    gain_envelope = np.interp(sample_indices, frame_centers, smoothed_gains).astype(np.float32)
    amplified = audio * gain_envelope
    return _soft_knee_limiter(amplified, threshold=0.85, ceiling=0.95)


def enhance_for_stt(audio: np.ndarray, sr: int = 16000, profile: str = "auto") -> tuple[np.ndarray, str]:
    """Enhance a dictation buffer for any STT model.

    Returns ``(enhanced_audio, profile_used)``. Never raises by contract —
    on any internal failure the input is returned unchanged.
    """
    if audio is None or audio.size == 0:
        return audio, "off"
    if os.environ.get("VOICE_FLOW_AUDIO_ENHANCE", "").strip().lower() in {"0", "false", "no", "off"}:
        return audio, "off"

    try:
        audio = np.nan_to_num(np.asarray(audio, dtype=np.float32).flatten(), nan=0.0, posinf=0.0, neginf=0.0)
        stats = _measure(audio, sr)
        if stats["peak"] < _NEAR_SILENCE:
            return audio, "silence"

        resolved = profile if profile in _PROFILES else _auto_profile(audio, sr)
        cfg = _PROFILES.get(resolved, _PROFILES["normal"])

        out = _highpass(audio, sr, cfg["highpass_hz"])
        # Spectral gating attenuates steady noise bins during pauses. If audio is a continuous
        # tone without pauses (snr < 1.15 and peak >= 0.005), skip subtraction to preserve the tone.
        if audio.size >= _MIN_ENHANCE_LEN and (stats["snr"] >= 1.15 or stats["peak"] < 0.005):
            out = _spectral_gate(out, sr, cfg["gate_strength"], cfg["gate_floor"])
            stats_now = _measure(out, sr)
            if resolved == "noisy" and stats_now["snr"] > 2.5:
                out = _relative_voice_gate(out, sr)

        peak_now = float(np.max(np.abs(out)))
        if peak_now < _NEAR_SILENCE:
            # Denoiser collapsed residual noise; do not amplify silence.
            return out, resolved

        # Real-time dynamic Automatic Gain Control (AGC)
        eff_noise_floor = 0.0005 if (stats["snr"] < 1.15 and stats["peak"] >= 0.005) else stats["noise_floor"]
        out = _apply_dynamic_agc(
            out,
            sr=sr,
            target_rms_db=cfg.get("target_rms_db", -15.0),
            gain_ceiling=cfg["gain_ceiling"],
            noise_floor=max(eff_noise_floor, 1e-5),
        )

        out = _soft_knee_limiter(out, threshold=0.85, ceiling=0.95)
        return out.astype(np.float32), resolved
    except Exception:
        log.exception("[ENHANCE] failed; using unenhanced audio")
        return audio, "off"


def vad_threshold_for(profile: str) -> float:
    """Silero VAD threshold paired with the enhancement profile."""
    return _PROFILES.get(profile, _PROFILES["normal"])["vad_threshold"]
