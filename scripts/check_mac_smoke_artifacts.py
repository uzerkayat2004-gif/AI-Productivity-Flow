"""Validate artifacts emitted by the macOS GUI smoke test."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image


def logs_mention_win32_keyboard_hook(text: str) -> bool:
    """Return whether app output contains a Win32 keyboard hook message."""
    return "Win32 keyboard hook" in text


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
    stdout = (out_dir / "app-stdout.txt").read_text(encoding="utf-8", errors="replace") if (out_dir / "app-stdout.txt").exists() else ""
    stderr = (out_dir / "app-stderr.txt").read_text(encoding="utf-8", errors="replace") if (out_dir / "app-stderr.txt").exists() else ""
    if logs_mention_win32_keyboard_hook(stdout) or logs_mention_win32_keyboard_hook(stderr):
        print("macOS smoke failure: app log mentions Win32 keyboard hook.", file=sys.stderr)
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
