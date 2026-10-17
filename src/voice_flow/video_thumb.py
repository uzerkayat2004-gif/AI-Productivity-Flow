"""Pick a non-blank preview frame for a finished video.

NotebookLM videos often open on a white title card. Seeking a few seconds in,
and skipping a near-white frame, keeps the library thumbnail from looking blank.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

THUMB_SEEK_SECONDS = (1.5, 3.0, 8.0)
NEAR_WHITE_YAVG = 245.0


def frame_is_near_white(yavg: float | None, *, threshold: float = NEAR_WHITE_YAVG) -> bool:
    """True when the average luma is a blank white frame."""
    if yavg is None:
        return False
    try:
        return float(yavg) >= float(threshold)
    except (TypeError, ValueError):
        return False


def parse_yavg(ffmpeg_text: str) -> float | None:
    """Read lavfi.signalstats.YAVG from ffmpeg metadata output."""
    for line in (ffmpeg_text or "").splitlines():
        if "YAVG" not in line:
            continue
        tail = line.split("YAVG", 1)[-1]
        digits: list[str] = []
        started = False
        for ch in tail:
            if ch.isdigit() or (ch == "." and started):
                digits.append(ch)
                started = True
            elif started:
                break
        if digits:
            try:
                return float("".join(digits))
            except ValueError:
                return None
    return None


def _run(cmd: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def probe_yavg(ffmpeg: str, image: Path) -> float | None:
    proc = _run(
        [str(ffmpeg), "-hide_banner", "-i", str(image), "-vf", "signalstats,metadata=print", "-f", "null", "-"],
        timeout=20,
    )
    return parse_yavg((proc.stderr or "") + "\n" + (proc.stdout or ""))


def write_preview_thumb(ffmpeg: str, video: Path, thumb: Path) -> bool:
    """Write thumb.jpg from the first seek that is not a near-white frame."""
    thumb.parent.mkdir(parents=True, exist_ok=True)
    last_ok = False
    for seek in THUMB_SEEK_SECONDS:
        try:
            proc = _run(
                [
                    str(ffmpeg), "-y", "-loglevel", "error",
                    "-ss", str(seek), "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(thumb),
                ],
                timeout=25,
            )
        except Exception:
            continue
        if proc.returncode != 0 or not thumb.is_file() or thumb.stat().st_size < 32:
            continue
        last_ok = True
        yavg = None
        try:
            yavg = probe_yavg(ffmpeg, thumb)
        except Exception:
            yavg = None
        if not frame_is_near_white(yavg):
            return True
    return last_ok and thumb.is_file()
