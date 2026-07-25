"""Configuration and constants for Voice Flow."""

from dataclasses import dataclass, field


@dataclass
class Config:
    """User-configurable settings."""

    # --- Whisper Model ---
    model_size: str = "base"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"

    # --- Audio ---
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1024  # frames per audio callback

    # --- Overlay Bar ---
    bar_width: int = 320
    bar_height: int = 48
    bar_bottom_margin: int = 60  # px from bottom of screen
    bar_corner_radius: int = 24
    bar_bg: str = "#1a1a2e"
    bar_fg: str = "#e0e0e0"
    bar_accent: str = "#6c63ff"  # purple accent for waveform
    bar_cancel_color: str = "#ff6b6b"
    bar_finish_color: str = "#51cf66"
    bar_done_color: str = "#6c63ff"
    bar_font_family: str = "Segoe UI"
    bar_font_size: int = 11
    fade_duration_ms: int = 300  # fade in/out duration
    done_display_ms: int = 2000  # how long "Done" shows before fade-out

    # --- Waveform ---
    waveform_dot_count: int = 9
    waveform_dot_radius: int = 3
    waveform_dot_spacing: int = 8
    waveform_max_amplitude: int = 10  # max vertical displacement

    # --- Clipboard ---
    clipboard_restore_delay_ms: int = 100  # delay before restoring clipboard


# Singleton config instance
config = Config()
