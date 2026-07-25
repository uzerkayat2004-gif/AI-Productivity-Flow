"""Transcription module — uses Windows built-in System.Speech.Recognition via PowerShell.

No model downloads required. Uses the same speech engine that powers Win+H voice typing.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

import numpy as np
from numpy.typing import NDArray

from voice_flow.audio import AudioRecorder
from voice_flow.config import config

log = logging.getLogger(__name__)

# PowerShell script that uses .NET System.Speech.Recognition for dictation.
# This assembly is built into every Windows installation — zero downloads.
_PS_SCRIPT = r"""
param([string]$WavPath, [string]$Culture)

Add-Type -AssemblyName System.Speech

$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($Culture)
$recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$recognizer.SetInputToWaveFile($WavPath)

$results = @()
try {
    while ($true) {
        $result = $recognizer.Recognize()
        if ($null -eq $result) { break }
        $results += $result.Text
    }
} catch {}

$recognizer.Dispose()

# Output as JSON for clean parsing
@{ text = ($results -join ' ') } | ConvertTo-Json -Compress
"""


class Transcriber:
    """Transcribes audio using Windows built-in speech recognition (System.Speech)."""

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe a float32 audio buffer using Windows speech recognition.

        Args:
            audio: 1-D float32 array, 16 kHz mono.

        Returns:
            The transcribed text string, stripped and cleaned.
        """
        if audio.size == 0:
            return ""

        # Save audio to a temporary WAV file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="vf_")
        os.close(tmp_fd)

        try:
            AudioRecorder.save_wav(audio, tmp_path)

            # Call PowerShell with the System.Speech script
            log.info("Recognizing speech with Windows Speech Engine...")
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _PS_SCRIPT,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "WavPath": tmp_path, "Culture": config.language},
            )

            # Parse the result
            if result.returncode != 0:
                log.error("PowerShell recognition failed: %s", result.stderr.strip())
                return ""

            stdout = result.stdout.strip()
            if not stdout:
                log.info("No speech detected.")
                return ""

            data = json.loads(stdout)
            text = data.get("text", "").strip()
            log.info(
                "Transcribed: %s", text[:80] + ("..." if len(text) > 80 else "")
            )
            return text

        except subprocess.TimeoutExpired:
            log.error("Speech recognition timed out.")
            return ""
        except json.JSONDecodeError:
            log.error("Failed to parse recognition output.")
            return ""
        except Exception:
            log.exception("Error during transcription.")
            return ""
        finally:
            # Clean up temp WAV file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
