"""Configuration and constants for Voice Flow."""

from dataclasses import dataclass


@dataclass
class Config:
    """User-configurable settings."""

    # --- Speech Recognition ---
    model_size: str = "base.en"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"

    # --- Noise & Background Voice Filtering ---
    # Higher VAD threshold (0.65) ignores distant background voices and chatter
    vad_threshold: float = 0.65
    min_speech_duration_ms: int = 250
    # Dynamic Noise Gate RMS threshold -- audio below this energy level is treated as background noise
    noise_gate_rms: float = 0.008

    # --- Audio ---
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1024  # frames per audio callback

    # --- Overlay Bar ---
    bar_width: int = 360
    bar_height: int = 52
    bar_bottom_margin: int = 60  # px from bottom of screen
    bar_corner_radius: int = 26
    bar_bg: str = "#161627"
    bar_fg: str = "#e8e8f0"
    bar_accent: str = "#7c6cf6"  # purple accent for waveform
    bar_cancel_color: str = "#ff6b6b"
    bar_finish_color: str = "#51cf66"
    bar_font_family: str = "Segoe UI"
    bar_font_size: int = 11
    done_display_ms: int = 2000  # how long "Done" shows before fade-out

    # --- Waveform ---
    waveform_bar_count: int = 15
    waveform_max_amplitude: int = 14  # max vertical displacement

    # --- Clipboard ---
    clipboard_restore_delay_ms: int = 100  # delay before restoring clipboard


# Singleton config instance
config = Config()
