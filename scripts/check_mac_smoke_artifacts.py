"""Validate artifacts emitted by the macOS GUI smoke test."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from PIL import Image


_APP_WINDOW_MARKERS = ("ai productivity flow", "voice flow")
_BROWSER_PROCESS_NAMES = (
    "safari",
    "google chrome",
    "chromium",
    "firefox",
    "microsoft edge",
    "brave",
    "opera",
    "orion",
)
_EXACT_BROWSER_PROCESSES = _BROWSER_PROCESS_NAMES + ("arc", "chrome")


def logs_mention_win32_keyboard_hook(text: str) -> bool:
    """Return whether app output contains a Win32 keyboard hook message."""
    return "Win32 keyboard hook" in text


def app_exited(alive_text: str) -> bool:
    """Return whether the smoke loop recorded that the app process quit."""
    return "EXITED" in alive_text


def logs_mention_system_browser_fallback(text: str) -> bool:
    """Return whether the launcher gave up on a native window."""
    return "using the system browser" in text.lower()


def _mentions_app_window(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _APP_WINDOW_MARKERS)


def _is_browser_process(name: str) -> bool:
    lowered = " ".join(name.strip().lower().split())
    if lowered in _EXACT_BROWSER_PROCESSES:
        return True
    return any(token in lowered for token in _BROWSER_PROCESS_NAMES)


def window_report_problem(text: str) -> str | None:
    """Return a failure reason when the UI is in a browser or has no app window."""
    stripped = (text or "").strip()
    if not stripped:
        return "no app window"

    app_seen = False
    browser_hit: str | None = None
    structured = False
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        process, _, windows = line.partition(":")
        process = process.strip()
        windows = windows.strip()
        if not process:
            continue
        structured = True
        has_app = _mentions_app_window(process) or _mentions_app_window(windows)
        if _is_browser_process(process) and has_app:
            browser_hit = process
        elif not _is_browser_process(process) and has_app:
            app_seen = True
    if structured:
        if browser_hit:
            return f"app UI opened in {browser_hit}"
        if not app_seen:
            return "no app window"
        return None

    lowered = stripped.lower()
    if (
        "google chrome" in lowered
        or "microsoft edge" in lowered
        or re.search(r"\b(safari|firefox|chromium|opera|orion)\b", lowered)
    ):
        return "app UI opened in a browser"
    if not _mentions_app_window(stripped):
        return "no app window"
    return None


def is_mostly_blank(image: Image.Image) -> bool:
    """Apply the screenshot blankness gate to the central 50 percent crop."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    left, top = width // 4, height // 4
    right, bottom = width - left, height - top
    crop = rgb.crop((left, top, right, bottom))

    count = 0
    mean = 0.0
    squared_delta_sum = 0.0
    near_white = 0
    near_black = 0
    pixels = crop.load()
    for y_pos in range(crop.height):
        for x_pos in range(crop.width):
            red, green, blue = pixels[x_pos, y_pos]
            luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            count += 1
            delta = luminance - mean
            mean += delta / count
            squared_delta_sum += delta * (luminance - mean)
            if min(red, green, blue) >= 245:
                near_white += 1
            if max(red, green, blue) <= 18:
                near_black += 1

    if not count:
        return True
    luminance_stddev = math.sqrt(squared_delta_sum / count)
    return (
        luminance_stddev < 12.0
        or near_white / count >= 0.92
        or near_black / count >= 0.92
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/check_mac_smoke_artifacts.py OUT_DIR", file=sys.stderr)
        return 2

    out_dir = Path(argv[1])
    def _read(name: str) -> str:
        path = out_dir / name
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    stdout = _read("app-stdout.txt")
    stderr = _read("app-stderr.txt")
    if logs_mention_win32_keyboard_hook(stdout) or logs_mention_win32_keyboard_hook(stderr):
        print("macOS smoke failure: app log mentions Win32 keyboard hook.", file=sys.stderr)
        return 1

    if app_exited(_read("alive.txt")):
        print("macOS smoke failure: app exited before the smoke window ended.", file=sys.stderr)
        return 1

    window_problem = window_report_problem(_read("windows.txt"))
    if window_problem:
        print(f"macOS smoke failure: {window_problem}.", file=sys.stderr)
        return 1

    launcher_log = "\n".join((
        _read("gui_launcher.log"),
        stdout,
        stderr,
    ))
    if logs_mention_system_browser_fallback(launcher_log):
        print("macOS smoke failure: launcher fell back to the system browser.", file=sys.stderr)
        return 1

    screenshot_path = out_dir / "screen-30s.png"
    if not screenshot_path.is_file():
        print("macOS smoke failure: missing out/screen-30s.png.", file=sys.stderr)
        return 1
    try:
        with Image.open(screenshot_path) as screenshot:
            if is_mostly_blank(screenshot):
                print("macOS smoke failure: screen-30s.png is mostly blank.", file=sys.stderr)
                return 1
    except Exception as exc:
        print(f"macOS smoke failure: could not read screen-30s.png: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
