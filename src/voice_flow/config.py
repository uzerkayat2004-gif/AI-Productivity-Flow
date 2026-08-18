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
    # Benchmarked on 12-thread CPUs: 8 threads beats 4 by ~25%; leaving 4 threads
    # of headroom keeps the GUI, audio capture, and watchdog responsive.
    cpu_threads: int = field(default_factory=lambda: max(2, min(8, (os.cpu_count() or 8) - 4)))

    # --- Speed & Accuracy Settings ---
    beam_size: int = 1  # 1 = ultra-fast greedy decoding (<0.5s STT)
    temperature: float = 0.0  # 0.0 = deterministic, zero hallucination

    # --- Whisper Anti-Hallucination & Repetition Control ---
    no_speech_threshold: float = 0.6  # Segments scored below this are treated as silence
    compression_ratio_threshold: float = 2.4  # Drop segments that compress too well (hallucinated tails)
    repetition_penalty: float = 1.2  # Discourage pathological word repetition loops

    # --- Auto Punctuation From Natural Pauses ---
    auto_punctuation_enabled: bool = True
    pause_sentence_gap_s: float = 0.55  # Silence gap that becomes a period
    pause_paragraph_gap_s: float = 1.0  # Silence gap that becomes a paragraph break

    # --- Spoken Number Normalization ("twenty five" -> "25") ---
    number_normalization_enabled: bool = True

    # --- AI Polish Latency Budget ---
    polish_api_timeout_s: float = 1.5  # Hard per-request timeout for polish LLM calls
    polish_budget_s: float = 2.5  # Total wall-clock budget for all polish API attempts

    # --- Noise & Background Voice Filtering ---
    vad_threshold: float = 0.20  # Lower = catches softer speech and natural pauses
    min_speech_duration_ms: int = 80
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
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.execute("SELECT api_key FROM api_keys ORDER BY id ASC")
                return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def add_api_key(self, api_key: str) -> bool:
        """Add new API key to database."""
        if not api_key or not api_key.strip():
            return False
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO api_keys (api_key, created_at) VALUES (?, datetime('now'))",
                    (api_key.strip(),),
                )
                conn.commit()
                return True
        except Exception:
            return False


# Singleton config instance
config = Config()
