from __future__ import annotations

from PIL import Image, ImageDraw

from scripts.check_mac_smoke_artifacts import (
    is_mostly_blank,
    logs_mention_win32_keyboard_hook,
)


def test_white_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "white"))


def test_black_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "black"))


def test_colored_content_is_not_mostly_blank():
    image = Image.new("RGB", (200, 200), "#f7f0e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 60, 140, 90), fill="#f97316")
    draw.rectangle((60, 100, 135, 125), fill="#2563eb")
    draw.rectangle((70, 132, 150, 145), fill="#6d28d9")
    for x in range(65, 136, 12):
        draw.rectangle((x, 108, x + 5, 115), fill="#1c1917")
    assert not is_mostly_blank(image)


def test_win32_keyboard_hook_log_is_detected():
    assert logs_mention_win32_keyboard_hook("Win32 keyboard hook stopped")
    assert not logs_mention_win32_keyboard_hook("pynput listener started")
