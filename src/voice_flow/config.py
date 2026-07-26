"""Configuration and constants for Voice Flow."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field

DB_PATH = os.path.join(os.path.expanduser("~"), ".voice_flow", "voice_flow.db")


@dataclass
class Config:
    """User-configurable settings."""

    # --- Speech Recognition ---
    model_size: str = "base.en"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = field(default_factory=lambda: max(2, min(4, (os.cpu_count() or 8) // 2)))

    # --- Speed & Accuracy Settings ---
    beam_size: int = 1  # 1 = ultra-fast greedy decoding (<0.5s STT)
    temperature: float = 0.0  # 0.0 = deterministic, zero hallucination

    # --- Noise & Background Voice Filtering ---
    vad_threshold: float = 0.30
    min_speech_duration_ms: int = 100
    noise_gate_rms: float = 0.001

    # --- Audio Hardware Input Selection ---
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1024
    selected_mic_device: str | int | None = None  # Selected hardware mic device index/name

    # --- Clipboard Injection ---
    clipboard_restore_delay_ms: int = 250  # Delay before restoring clipboard after paste

    # --- Hotkeys & Shortcuts ---
    push_to_talk_shortcut: str = "Ctrl+Win"
    hands_free_shortcut: str = "Middle Click / Ctrl+Win"

    # --- Overlay Bar ---
    bar_width: int = 360
    bar_height: int = 52
    bar_bottom_margin: int = 60
    bar_corner_radius: int = 26
    bar_bg: str = "#161627"
    bar_fg: str = "#e8e8f0"
    bar_accent: str = "#ff6b00"  # Vibrant orange accent
    bar_cancel_color: str = "#ff6b6b"
    bar_finish_color: str = "#51cf66"
    bar_font_family: str = "Segoe UI"
    bar_font_size: int = 11
    done_display_ms: int = 1500

    # --- Waveform ---
    waveform_bar_count: int = 15
    waveform_max_amplitude: int = 14

    def get_api_keys(self) -> list[str]:
        """Fetch list of user API keys from database."""
        if not os.path.exists(DB_PATH):
            return []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute("SELECT api_key FROM api_keys ORDER BY id ASC")
            keys = [row[0] for row in cursor.fetchall()]
            conn.close()
            return keys
        except Exception:
            return []

    def add_api_key(self, api_key: str) -> bool:
        """Add new API key to database."""
        if not api_key or not api_key.strip():
            return False
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT OR IGNORE INTO api_keys (api_key, created_at) VALUES (?, datetime('now'))",
                (api_key.strip(),),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False


# Singleton config instance
config = Config()
