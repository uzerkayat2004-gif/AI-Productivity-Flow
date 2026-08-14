"""Local, bounded audio archive used by history recovery.

The archive deliberately owns all path checks so HTTP/UI code never handles a
client supplied file path.  Files are ordinary 16 kHz mono WAVs and are kept
for fourteen days only.
"""
from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

import numpy as np

from voice_flow.audio import AudioRecorder
from voice_flow.paths import data_dir

AUDIO_RETENTION_SECONDS = 14 * 24 * 60 * 60
MIN_RETRY_SECONDS = 5.0


class AudioArchive:
    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root or data_dir() / "audio").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, audio: np.ndarray) -> str:
        """Atomically persist an already-normalized recording and return its basename."""
        name = f"{int(time.time() * 1000)}-{uuid.uuid4().hex}.wav"
        destination = self.root / name
        fd, temporary = tempfile.mkstemp(prefix=".writing-", suffix=".wav", dir=self.root)
        os.close(fd)
        try:
            AudioRecorder.save_wav(audio, temporary)
            os.replace(temporary, destination)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return name

    def resolve(self, stored_path: str | None) -> Path | None:
        """Resolve only a simple archive filename under this archive root."""
        if not stored_path or Path(stored_path).name != stored_path or not stored_path.endswith(".wav"):
            return None
        try:
            candidate = (self.root / stored_path).resolve()
            candidate.relative_to(self.root)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    def available(self, stored_path: str | None, timestamp: float | None = None) -> bool:
        path = self.resolve(stored_path)
        if not path:
            return False
        return time.time() - (timestamp if timestamp is not None else path.stat().st_mtime) < AUDIO_RETENTION_SECONDS

    def remove(self, stored_path: str | None) -> bool:
        path = self.resolve(stored_path)
        if not path:
            return False
        path.unlink()
        return True

    def purge_expired(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        removed: list[str] = []
        for path in self.root.glob("*.wav"):
            try:
                if now - path.stat().st_mtime >= AUDIO_RETENTION_SECONDS:
                    path.unlink(); removed.append(path.name)
            except OSError:
                continue
        return removed
