"""Transcription module -- uses Windows built-in System.Speech.Recognition.

No model downloads required. Uses the same speech engine already on every Windows PC.
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

# PowerShell script saved to a temp file and invoked with -File.
# Uses the DEFAULT recognizer (auto-selects the best installed culture).
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$wavPath = $env:VF_WAV_PATH

try {
    Add-Type -AssemblyName System.Speech

    # Use default recognizer (auto-selects installed culture)
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine

    # Load free-form dictation grammar
    $dictGrammar = New-Object System.Speech.Recognition.DictationGrammar
    $recognizer.LoadGrammar($dictGrammar)

    # Set input to WAV file
    $recognizer.SetInputToWaveFile($wavPath)

    # Recognize all utterances in the file
    $results = @()
    while ($true) {
        $result = $recognizer.Recognize()
        if ($null -eq $result) { break }
        if ($result.Text -and $result.Confidence -gt 0.15) {
            $results += $result.Text
        }
    }

    $recognizer.Dispose()

    $text = ($results -join ' ').Trim()

    # Output JSON on a single line
    $output = @{ text = $text; error = '' }
    [System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output ($output | ConvertTo-Json -Compress)
} catch {
    $output = @{ text = ''; error = $_.Exception.Message }
    Write-Output ($output | ConvertTo-Json -Compress)
}
"""


class Transcriber:
    """Transcribes audio using Windows built-in speech recognition (System.Speech)."""

    def __init__(self) -> None:
        self._script_path: str | None = None

    def _ensure_script(self) -> str:
        """Write the PowerShell script to a temp file once and reuse it."""
        if self._script_path and os.path.exists(self._script_path):
            return self._script_path

        fd, path = tempfile.mkstemp(suffix=".ps1", prefix="vf_recognize_")
        os.close(fd)
        with open(path, "w", encoding="utf-8-sig") as f:  # BOM for PowerShell
            f.write(_PS_SCRIPT)
        self._script_path = path
        return path

    def transcribe(self, audio: NDArray[np.float32]) -> str:
        """Transcribe a float32 audio buffer using Windows speech recognition.

        Args:
            audio: 1-D float32 array, 16 kHz mono.

        Returns:
            The transcribed text string, stripped and cleaned.
        """
        if audio.size == 0:
            log.warning("Empty audio buffer, nothing to transcribe.")
            return ""

        duration = len(audio) / config.sample_rate
        if duration < 0.5:
            log.warning("Audio too short (%.1fs), skipping.", duration)
            return ""

        log.info("Audio duration: %.1f seconds", duration)

        # Save audio to a temporary WAV file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="vf_")
        os.close(tmp_fd)

        try:
            AudioRecorder.save_wav(audio, tmp_path)
            wav_size = os.path.getsize(tmp_path)
            log.info("WAV file: %d bytes", wav_size)

            if wav_size < 100:
                log.error("WAV file too small, recording may have failed.")
                return ""

            # Ensure script file exists
            script_path = self._ensure_script()

            # Build environment with WAV path
            env = {**os.environ}
            env["VF_WAV_PATH"] = tmp_path

            # Run PowerShell with -File (avoids encoding/escaping issues)
            log.info("Recognizing speech with Windows Speech Engine...")
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-File", script_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )

            if result.stderr and result.stderr.strip():
                log.warning("PowerShell stderr: %s", result.stderr.strip()[:200])

            if result.returncode != 0:
                log.error(
                    "PowerShell failed (exit %d): %s",
                    result.returncode,
                    result.stderr.strip()[:200],
                )
                return ""

            stdout = result.stdout.strip()
            if not stdout:
                log.info("No output from speech recognition.")
                return ""

            data = json.loads(stdout)

            error = data.get("error", "")
            if error:
                log.error("Speech engine error: %s", error)
                return ""

            text = data.get("text", "").strip()
            if text:
                log.info("Transcribed: %s", text[:80] + ("..." if len(text) > 80 else ""))
            else:
                log.info("No speech detected in audio.")
            return text

        except subprocess.TimeoutExpired:
            log.error("Speech recognition timed out after 30s.")
            return ""
        except json.JSONDecodeError as e:
            log.error("Failed to parse recognition output: %s", e)
            return ""
        except Exception:
            log.exception("Error during transcription.")
            return ""
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
